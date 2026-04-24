"""
监控调度核心。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from ai_service import close_ai_service, get_ai_service
from config import get_config
from logger import get_monitor_logger
from market import close_fetcher, get_fetcher
from models import PriceState
from notifier import close_notifier, get_notifier
from onchain import normalize_onchain_payload
from reporting import ReportService
from rules import RuleEngine
from storage import close_storage, get_storage


class MonitorEngine:
    """核心监控引擎。"""

    def __init__(self):
        self.config = get_config()
        self.logger = get_monitor_logger()

        self.fetcher = get_fetcher()
        self.ai_service = get_ai_service()
        self.notifier = get_notifier()
        self.rule_engine = RuleEngine()
        self.storage = None
        self.report_service: Optional[ReportService] = None

        self.price_states: Dict[str, PriceState] = {}
        self.watch_list: Set[str] = set(self.config.monitor.watch_list)
        self.running = False
        self.paused = False

        self.start_time: Optional[datetime] = None
        self.failure_count = 0
        self.last_success_time: Optional[datetime] = None
        self._last_health_check_at: Optional[datetime] = None

        self._on_alert_callbacks: List[Callable] = []
        self._on_price_update_callbacks: List[Callable] = []

    async def initialize(self) -> None:
        self.storage = await get_storage()
        self.report_service = ReportService(self.storage)
        await self.storage.seed_watch_list(self.watch_list)
        await self._restore_watch_list()
        await self._restore_states()
        self.logger.info(f"监控引擎初始化完成，监听币种: {sorted(self.watch_list)}")

    async def _restore_watch_list(self) -> None:
        if not self.storage:
            return

        stored_symbols = await self.storage.get_watch_list()
        if stored_symbols:
            self.watch_list = set(stored_symbols)

    async def _restore_states(self) -> None:
        if not self.storage:
            return

        states = await self.storage.get_all_symbol_states()
        for symbol, state in states.items():
            if symbol not in self.watch_list:
                continue
            self.price_states[symbol] = PriceState(
                symbol=symbol,
                last_price=state["last_price"],
                last_alert_time=state["last_alert_time"],
            )
            self.logger.info(f"恢复 {symbol} 状态: 价格 {state['last_price']}")

    async def add_symbol(self, symbol: str) -> None:
        normalized = symbol.upper()
        if normalized not in self.watch_list:
            self.watch_list.add(normalized)
            self.price_states[normalized] = PriceState(symbol=normalized)
            if self.storage:
                await self.storage.add_watch_symbol(normalized)
            self.logger.info(f"添加监控币种: {normalized}")

    async def remove_symbol(self, symbol: str) -> None:
        normalized = symbol.upper()
        if normalized in self.watch_list:
            self.watch_list.discard(normalized)
            self.price_states.pop(normalized, None)
            if self.storage:
                await self.storage.remove_watch_symbol(normalized)
            self.logger.info(f"移除监控币种: {normalized}")

    def on_alert(self, callback: Callable) -> None:
        self._on_alert_callbacks.append(callback)

    def on_price_update(self, callback: Callable) -> None:
        self._on_price_update_callbacks.append(callback)

    async def _trigger_callbacks(self, callbacks: List[Callable], payload: Dict[str, Any]) -> None:
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(payload)
                else:
                    callback(payload)
            except Exception as exc:
                self.logger.error(f"回调执行失败: {exc}")

    async def check_prices(self) -> Dict[str, Dict[str, Any]]:
        """抓取行情并计算各币种状态。"""
        results: Dict[str, Dict[str, Any]] = {}
        snapshots = await self.fetcher.get_all_snapshots()

        if not snapshots:
            self.failure_count += 1
            self.logger.warning(f"获取市场数据失败，连续失败次数: {self.failure_count}")
            return results

        self.failure_count = 0
        self.last_success_time = datetime.now()

        price_records = []
        for symbol in sorted(self.watch_list):
            pair_name = f"{symbol}USDT"
            snapshot = snapshots.get(pair_name)
            if snapshot is None:
                self.logger.warning(f"未找到交易对: {pair_name}")
                continue

            state = self.price_states.setdefault(symbol, PriceState(symbol=symbol))
            change = state.update_price(snapshot.price)

            result = {
                "symbol": symbol,
                "pair": pair_name,
                "price": snapshot.price,
                "change": change,
                "trend": state.get_trend(),
                "should_alert": False,
                "alert_level": None,
                "snapshot": snapshot,
            }

            decision = self.rule_engine.evaluate_market(
                snapshot=snapshot,
                change_percent=change,
                thresholds=self.config.monitor.thresholds,
                config=self.config.monitor,
            )
            result["alert_level"] = decision.level
            result["rule_reasons"] = decision.reasons
            result["rule_tags"] = decision.tags

            if decision.should_alert and state.can_alert(self.config.monitor.cooldown):
                result["should_alert"] = True

            price_records.append((symbol, snapshot.price, change))
            await self._trigger_callbacks(self._on_price_update_callbacks, result)
            results[symbol] = result

        if self.storage and price_records:
            await self.storage.save_prices(price_records)

        return results

    async def process_alert(self, result: Dict[str, Any]) -> bool:
        symbol = result["symbol"]
        price = result["price"]
        change = result["change"]
        level = result["alert_level"]
        snapshot = result.get("snapshot")
        rule_reasons = result.get("rule_reasons") or []
        rule_tags = result.get("rule_tags") or []

        _, style = self.config.monitor.thresholds.get_level(change)
        insight = await self.ai_service.generate_insight(
            symbol=symbol,
            price=price,
            change_percent=change,
            level=level,
            style=style,
            snapshot=snapshot,
            context={"rule_reasons": rule_reasons, "rule_tags": rule_tags},
        )

        success = await self.notifier.send_alert(symbol, price, change, level, insight.comment)
        if not success:
            return False

        state = self.price_states.get(symbol)
        if state:
            state.mark_alerted()

        if self.storage:
            await self.storage.save_alert(
                symbol,
                price,
                change,
                level,
                insight.comment,
                insight=insight,
                rule_reasons=rule_reasons,
                rule_tags=rule_tags,
            )
            await self.storage.update_symbol_state(symbol, price, datetime.now())

        await self._trigger_callbacks(
            self._on_alert_callbacks,
            {
                "symbol": symbol,
                "price": price,
                "change": change,
                "level": level,
                "ai_comment": insight.comment,
                "sentiment": insight.sentiment,
                "event_type": insight.event_type,
                "risk_hint": insight.risk_hint,
                "suggested_action": insight.suggested_action,
                "confidence": insight.confidence,
                "rule_reasons": rule_reasons,
                "rule_tags": rule_tags,
                "sent_at": datetime.now().isoformat(),
            },
        )
        return True

    async def process_onchain_payload(self, payload: Any, source: str = "webhook") -> Dict[str, Any]:
        """处理链上 webhook，支持单条或批量 JSON。"""
        events = normalize_onchain_payload(payload, source=source)
        processed = []
        alerts = []

        for event in events:
            decision = self.rule_engine.evaluate_onchain(event, self.config.onchain)
            insight = None
            sent = False

            if decision.should_alert and decision.level:
                insight = await self.ai_service.generate_onchain_insight(
                    event,
                    decision.level,
                    context={"rule_reasons": decision.reasons, "rule_tags": decision.tags},
                )
                sent = await self.notifier.send_onchain_alert(
                    symbol=event.symbol,
                    event_type=event.event_type,
                    amount_usd=event.amount_usd,
                    level=decision.level,
                    ai_comment=insight.comment,
                )
                alerts.append(
                    {
                        "event_id": event.event_id,
                        "sent": sent,
                        "level": decision.level,
                        "symbol": event.symbol,
                    }
                )

            if self.storage:
                await self.storage.save_onchain_event(
                    event,
                    rule_level=decision.level,
                    rule_reasons=decision.reasons,
                    rule_tags=decision.tags,
                    insight=insight,
                )

            processed.append(
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "symbol": event.symbol,
                    "should_alert": decision.should_alert,
                    "level": decision.level,
                    "reasons": decision.reasons,
                    "tags": decision.tags,
                }
            )

        return {
            "processed": len(processed),
            "alerts_triggered": len([item for item in alerts if item["sent"]]),
            "events": processed,
            "alerts": alerts,
            "timestamp": datetime.now().isoformat(),
        }

    async def generate_daily_report(
        self,
        lookback_hours: Optional[int] = None,
        send: bool = False,
    ) -> Dict[str, Any]:
        if self.report_service is None:
            if not self.storage:
                self.storage = await get_storage()
            self.report_service = ReportService(self.storage)
        report = await self.report_service.generate_daily_report(lookback_hours)
        if send:
            report["sent"] = await self.notifier.send_report(report)
        return report

    async def run_once(self) -> Dict[str, Any]:
        results = await self.check_prices()
        alerts = []
        for symbol, result in results.items():
            if result.get("should_alert"):
                success = await self.process_alert(result)
                alerts.append({"symbol": symbol, "success": success, "level": result["alert_level"]})

        return {
            "total_checked": len(results),
            "alerts_triggered": len([item for item in alerts if item["success"]]),
            "alerts": alerts,
            "timestamp": datetime.now().isoformat(),
            "results": results,
        }

    async def run_forever(self) -> None:
        self.running = True
        self.start_time = datetime.now()
        self.logger.info(f"监控引擎启动，间隔: {self.config.monitor.interval} 秒")

        while self.running:
            try:
                if not self.paused:
                    summary = await self.run_once()
                    self._print_status(summary)
                    if self._should_run_health_check():
                        await self._health_check()
                    if self._should_generate_daily_report():
                        await self.generate_daily_report(send=True)

                await asyncio.sleep(self.config.monitor.interval)
            except asyncio.CancelledError:
                self.logger.info("监控循环被取消")
                break
            except Exception as exc:
                self.failure_count += 1
                self.logger.exception(f"监控循环异常: {exc}")
                await asyncio.sleep(5)

    def _print_status(self, summary: Dict[str, Any]) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(
            f"[{timestamp}] {'⏸️ 暂停' if self.paused else '✅ 运行中'} | "
            f"检查: {summary['total_checked']} | 报警: {summary['alerts_triggered']}"
        )
        for symbol, result in summary.get("results", {}).items():
            price = result.get("price", 0.0)
            change = result.get("change", 0.0)
            emoji = "📈" if change > 0 else "📉" if change < 0 else "➖"
            print(f"  {emoji} {symbol}: ${price:,.4f} ({change:+.2f}%)")

    def _should_run_health_check(self) -> bool:
        if not self.config.health_check.enabled:
            return False

        now = datetime.now()
        if self._last_health_check_at is None:
            self._last_health_check_at = now
            return True

        elapsed = (now - self._last_health_check_at).total_seconds()
        if elapsed >= self.config.health_check.interval:
            self._last_health_check_at = now
            return True
        return False

    def _should_generate_daily_report(self) -> bool:
        reporting = self.config.reporting
        if not reporting.enabled or not reporting.auto_send:
            return False

        now = datetime.now()
        if now.hour != reporting.daily_hour or now.minute >= max(1, self.config.monitor.interval // 60 + 1):
            return False

        key = now.strftime("%Y-%m-%d")
        if getattr(self, "_last_report_date", None) == key:
            return False

        self._last_report_date = key
        return True

    async def _health_check(self) -> None:
        if self.failure_count < self.config.health_check.max_failures:
            return

        self.logger.error(f"连续失败 {self.failure_count} 次，触发健康检查")
        await self.notifier.send_health_check(
            {
                "healthy": False,
                "uptime": str(datetime.now() - self.start_time) if self.start_time else "N/A",
                "last_check": self.last_success_time.isoformat() if self.last_success_time else "N/A",
                "issues": f"连续失败 {self.failure_count} 次",
            }
        )

        if self.config.health_check.auto_restart:
            self.logger.info("执行轻量自恢复：重建市场抓取会话")
            await self.fetcher.clear_cache()
            self.failure_count = 0

    def pause(self) -> None:
        self.paused = True
        self.logger.info("监控已暂停")

    def resume(self) -> None:
        self.paused = False
        self.logger.info("监控已恢复")

    def stop(self) -> None:
        self.running = False
        self.logger.info("监控引擎停止")

    def get_status(self) -> Dict[str, Any]:
        uptime = str(datetime.now() - self.start_time) if self.start_time else None
        return {
            "running": self.running,
            "paused": self.paused,
            "uptime": uptime,
            "watch_list": sorted(self.watch_list),
            "watch_list_count": len(self.watch_list),
            "failure_count": self.failure_count,
            "last_success": self.last_success_time.isoformat() if self.last_success_time else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
        }

    async def cleanup(self) -> None:
        self.logger.info("开始清理资源")
        if self.storage:
            for symbol, state in self.price_states.items():
                if state.last_price is None:
                    continue
                await self.storage.update_symbol_state(symbol, state.last_price, state.last_alert_time)
            await self.storage.cleanup_old_data(self.config.storage.history_retention_days)

        await close_fetcher()
        close_ai_service()
        await close_notifier()
        await close_storage()
        self.logger.info("资源清理完成")
