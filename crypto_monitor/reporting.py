"""
报告生成模块。

先生成可落库的 Markdown 日报，后续可以把同一份内容推送到 Notion。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import get_config
from logger import get_monitor_logger
from storage import Storage


class ReportService:
    """基于已持久化事件生成日报。"""

    def __init__(self, storage: Storage):
        self.config = get_config().reporting
        self.storage = storage
        self.logger = get_monitor_logger()

    async def generate_daily_report(self, lookback_hours: Optional[int] = None) -> Dict[str, Any]:
        hours = lookback_hours or self.config.default_lookback_hours
        alerts = await self.storage.get_alert_history(hours=hours, limit=200)
        onchain_events = await self.storage.get_onchain_events(hours=hours, limit=200)

        if self.config.major_only:
            alerts = [item for item in alerts if item.get("alert_level") == "major"]
            onchain_events = [item for item in onchain_events if item.get("rule_level") == "major"]

        title = f"Crypto Monitor Daily Report - {datetime.now().strftime('%Y-%m-%d')}"
        content = self._render_markdown(title, hours, alerts, onchain_events)
        report_id = await self.storage.save_report("daily", title, content, hours)
        file_path = self._write_report_file(title, content)

        return {
            "id": report_id,
            "title": title,
            "content": content,
            "file_path": str(file_path),
            "alerts_count": len(alerts),
            "onchain_events_count": len(onchain_events),
            "lookback_hours": hours,
            "generated_at": datetime.now().isoformat(),
        }

    def _render_markdown(
        self,
        title: str,
        hours: int,
        alerts: List[Dict[str, Any]],
        onchain_events: List[Dict[str, Any]],
    ) -> str:
        lines = [
            f"# {title}",
            "",
            f"- Lookback: {hours} hours",
            f"- Market alerts: {len(alerts)}",
            f"- Onchain events: {len(onchain_events)}",
            "",
            "## Market Alerts",
        ]

        if alerts:
            for item in alerts:
                lines.append(
                    "- "
                    f"{item.get('symbol')} {item.get('change_percent'):+.2f}% "
                    f"[{item.get('alert_level')}] "
                    f"{item.get('ai_comment') or ''}"
                )
                if item.get("risk_hint"):
                    lines.append(f"  Risk: {item['risk_hint']}")
        else:
            lines.append("- No major market alerts.")

        lines.extend(["", "## Onchain Events"])
        if onchain_events:
            for item in onchain_events:
                amount_usd = item.get("amount_usd")
                amount_text = f"${amount_usd:,.2f}" if amount_usd is not None else "unknown amount"
                lines.append(
                    "- "
                    f"{item.get('event_type')} {item.get('symbol') or ''} "
                    f"{amount_text} [{item.get('rule_level')}] "
                    f"{item.get('ai_comment') or item.get('description') or ''}"
                )
                if item.get("tx_signature"):
                    lines.append(f"  Tx: {item['tx_signature']}")
        else:
            lines.append("- No major onchain events.")

        lines.extend(["", f"Generated at: {datetime.now().isoformat()}"])
        return "\n".join(lines)

    def _write_report_file(self, title: str, content: str) -> Path:
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        slug = title.lower().replace(" ", "-")
        path = output_dir / f"{slug}.md"
        path.write_text(content, encoding="utf-8")
        self.logger.info(f"日报已生成: {path}")
        return path
