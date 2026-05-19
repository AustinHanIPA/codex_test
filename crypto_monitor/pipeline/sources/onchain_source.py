"""
链上数据源。

从链上监控 webhook 历史和实时事件中拉取巨鲸转账、新池创建等链上异动。
复用现有 onchain 模块的归一化逻辑，包装成 ContentItem。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pipeline.base import BaseSource
from pipeline.models import ContentItem, ContentType, PipelineContext


class OnchainSource(BaseSource):
    """链上数据源 - 巨鲸转账、新池创建、流动性变化等。"""

    source_name = "onchain"

    def __init__(self, storage=None):
        """
        Args:
            storage: Storage 实例，用于从数据库读取历史链上事件。
        """
        self._storage = storage

    async def fetch(self, context: PipelineContext) -> List[ContentItem]:
        """从存储中读取近期链上事件并转为 ContentItem。"""
        if self._storage is None:
            return []

        items: List[ContentItem] = []
        try:
            events = await self._storage.get_onchain_events(hours=24, limit=100)
            for event in events:
                item = self._normalize_event(event, context)
                if item:
                    items.append(item)
        except Exception:
            pass

        return items

    def _normalize_event(
        self, event: Dict[str, Any], context: PipelineContext
    ) -> Optional[ContentItem]:
        """将链上事件归一化为 ContentItem。"""
        event_id = event.get("event_id") or ""
        event_type = event.get("event_type") or "unknown"
        symbol = event.get("symbol") or ""
        amount_usd = event.get("amount_usd")

        content_id = f"onchain:{event_id}"
        title = self._build_title(event_type, symbol, amount_usd)
        body = event.get("description") or event.get("ai_comment") or title

        published_at = None
        observed = event.get("observed_at") or event.get("created_at")
        if observed:
            try:
                published_at = datetime.fromisoformat(str(observed))
            except (ValueError, TypeError):
                pass

        risk_tags = []
        if amount_usd and amount_usd >= 100000:
            risk_tags.append("whale-transfer")
        if event_type in ("NewPairCreated",):
            risk_tags.append("new-pair")

        return ContentItem(
            content_id=content_id,
            content_type=ContentType.ONCHAIN_ALERT,
            source=self.source_name,
            title=title,
            body=body,
            symbols=[symbol.upper()] if symbol else [],
            published_at=published_at,
            risk_tags=risk_tags,
            raw=event,
            metadata={
                "event_type": event_type,
                "amount_usd": amount_usd,
                "direction": event.get("direction"),
                "address": event.get("address"),
                "counterparty": event.get("counterparty"),
                "tx_signature": event.get("tx_signature"),
                "rule_level": event.get("rule_level"),
            },
        )

    @staticmethod
    def _build_title(event_type: str, symbol: str, amount_usd: Optional[float]) -> str:
        amount_text = f"${amount_usd:,.0f}" if amount_usd is not None else "未知金额"
        token = symbol or "未知代币"
        type_labels = {
            "WhaleTransfer": "🐳 巨鲸转账",
            "NewPairCreated": "🆕 新池创建",
            "LiquidityLocked": "🔒 流动性锁定",
            "LiquidityBurned": "🔥 流动性销毁",
            "Swap": "🔄 大额兑换",
        }
        label = type_labels.get(event_type, f"📡 {event_type}")
        return f"{label}: {token} {amount_text}"
