"""
通知服务模块
支持 Telegram 通知、通知限流与异步发送。
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp

from config import get_config
from logger import get_notifier_logger


class RateLimiter:
    """
    通知限流器
    防止消息刷屏
    """

    def __init__(self, max_per_minute: int = 5, min_interval: int = 60):
        self.max_per_minute = max_per_minute
        self.min_interval = min_interval
        self._send_times: List[float] = []
        self._last_send_time: Dict[str, float] = defaultdict(float)

    def can_send(self, target: str = "default") -> bool:
        now = time.time()
        self._send_times = [t for t in self._send_times if now - t < 60]

        if len(self._send_times) >= self.max_per_minute:
            return False

        last_time = self._last_send_time.get(target, 0)
        if now - last_time < self.min_interval:
            return False

        return True

    def record_send(self, target: str = "default") -> None:
        now = time.time()
        self._send_times.append(now)
        self._last_send_time[target] = now

    def get_wait_time(self, target: str = "default") -> float:
        now = time.time()
        last_time = self._last_send_time.get(target, 0)
        interval_wait = max(0.0, self.min_interval - (now - last_time))

        self._send_times = [t for t in self._send_times if now - t < 60]
        if len(self._send_times) >= self.max_per_minute:
            oldest = min(self._send_times)
            rate_wait = max(0.0, 60 - (now - oldest))
        else:
            rate_wait = 0.0

        return max(interval_wait, rate_wait)


class TelegramNotifier:
    """Telegram 异步通知服务。"""

    def __init__(self):
        self.config = get_config().notification
        self.logger = get_notifier_logger()
        self.rate_limiter = RateLimiter(
            max_per_minute=self.config.rate_limit.max_per_minute,
            min_interval=self.config.rate_limit.min_interval,
        )
        self._session: Optional[aiohttp.ClientSession] = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.telegram.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def send_message(
        self,
        text: str,
        parse_mode: Optional[str] = None,
        disable_notification: bool = False,
    ) -> bool:
        if not self.config.telegram.enabled:
            self.logger.debug("Telegram 通知已禁用")
            return False

        config = get_config()
        url = f"{self.config.telegram.base_url}/bot{config.tg_bot_token}/sendMessage"
        payload = {
            "chat_id": config.tg_chat_id,
            "text": text,
            "disable_notification": disable_notification,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        session = self._ensure_session()
        retriable_statuses = {429, 500, 502, 503, 504}
        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            try:
                self.logger.debug(f"发送 Telegram 消息，尝试 {attempt}/{max_attempts}")
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("ok"):
                            self.logger.info("Telegram 消息发送成功")
                            return True
                        self.logger.error(f"Telegram API 错误: {data.get('description')}")
                        return False

                    response_text = await response.text()
                    self.logger.error(
                        f"Telegram 请求失败: HTTP {response.status}, body={response_text[:200]}"
                    )
                    if response.status not in retriable_statuses:
                        return False
            except asyncio.TimeoutError:
                self.logger.error("Telegram 请求超时")
            except aiohttp.ClientError as exc:
                self.logger.error(f"Telegram 请求异常: {exc}")
            except Exception as exc:
                self.logger.exception(f"Telegram 发送异常: {exc}")
                return False

            if attempt < max_attempts:
                await asyncio.sleep(attempt)

        return False

    async def send_alert(
        self,
        symbol: str,
        price: float,
        change_percent: float,
        level: str,
        ai_comment: str,
    ) -> bool:
        if not self.rate_limiter.can_send(symbol):
            wait_time = self.rate_limiter.get_wait_time(symbol)
            self.logger.warning(f"通知限流中，{symbol} 需等待 {wait_time:.1f} 秒")
            return False

        direction = "📈" if change_percent > 0 else "📉"
        level_emoji = {"minor": "🔔", "moderate": "⚠️", "major": "🚨"}.get(level, "🔔")
        message = f"""{level_emoji} **{symbol} 异动警报**

{direction} 现价: ${price:,.4f}
📊 波动: {change_percent:+.2f}%
🎯 级别: {level.upper()}

💭 {ai_comment}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        success = await self.send_message(message, parse_mode="Markdown")
        if success:
            self.rate_limiter.record_send(symbol)
        return success

    async def send_onchain_alert(
        self,
        symbol: str,
        event_type: str,
        amount_usd: Optional[float],
        level: str,
        ai_comment: str,
    ) -> bool:
        target = f"onchain:{symbol or event_type}"
        if not self.rate_limiter.can_send(target):
            wait_time = self.rate_limiter.get_wait_time(target)
            self.logger.warning(f"链上通知限流中，{target} 需等待 {wait_time:.1f} 秒")
            return False

        level_emoji = {"minor": "🔔", "moderate": "⚠️", "major": "🚨"}.get(level, "🔔")
        amount_text = f"${amount_usd:,.2f}" if amount_usd is not None else "未知"
        message = f"""{level_emoji} **链上事件警报**

事件: {event_type}
代币: {symbol or '未知'}
金额: {amount_text}
级别: {level.upper()}

💭 {ai_comment}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        success = await self.send_message(message, parse_mode="Markdown")
        if success:
            self.rate_limiter.record_send(target)
        return success

    async def send_daily_summary(self, summary: Dict) -> bool:
        message = f"""📊 **每日行情汇总**

📈 监控币种: {summary.get('symbols_count', 0)}
🔔 今日报警: {summary.get('today_alerts', 0)}
💰 价格记录: {summary.get('total_prices', 0)}

{summary.get('top_gainers', '')}
{summary.get('top_losers', '')}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return await self.send_message(message, parse_mode="Markdown")

    async def send_report(self, report: Dict) -> bool:
        content = str(report.get("content") or "")
        max_len = 3500
        if len(content) > max_len:
            content = content[:max_len] + "\n\n...报告内容已截断，请查看本地 Markdown 文件。"
        return await self.send_message(content, parse_mode="Markdown")

    async def send_health_check(self, status: Dict) -> bool:
        status_emoji = "✅" if status.get("healthy", False) else "❌"
        message = f"""{status_emoji} **系统健康检查**

运行状态: {'正常' if status.get('healthy') else '异常'}
运行时间: {status.get('uptime', 'N/A')}
最后检查: {status.get('last_check', 'N/A')}

问题: {status.get('issues', '无')}
"""
        return await self.send_message(message, parse_mode="Markdown")

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self.logger.debug("Telegram session 已关闭")


class Notifier:
    """统一通知服务。"""

    def __init__(self):
        self.logger = get_notifier_logger()
        self.telegram = TelegramNotifier()

    async def send_alert(
        self,
        symbol: str,
        price: float,
        change_percent: float,
        level: str,
        ai_comment: str,
    ) -> bool:
        return await self.telegram.send_alert(symbol, price, change_percent, level, ai_comment)

    async def send_daily_summary(self, summary: Dict) -> bool:
        return await self.telegram.send_daily_summary(summary)

    async def send_report(self, report: Dict) -> bool:
        return await self.telegram.send_report(report)

    async def send_health_check(self, status: Dict) -> bool:
        return await self.telegram.send_health_check(status)

    async def send_onchain_alert(
        self,
        symbol: str,
        event_type: str,
        amount_usd: Optional[float],
        level: str,
        ai_comment: str,
    ) -> bool:
        return await self.telegram.send_onchain_alert(
            symbol=symbol,
            event_type=event_type,
            amount_usd=amount_usd,
            level=level,
            ai_comment=ai_comment,
        )

    async def close(self) -> None:
        await self.telegram.close()


_notifier: Optional[Notifier] = None


def get_notifier() -> Notifier:
    global _notifier
    if _notifier is None:
        _notifier = Notifier()
    return _notifier


async def close_notifier() -> None:
    global _notifier
    if _notifier:
        await _notifier.close()
        _notifier = None
