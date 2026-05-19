"""
市场数据源。

从现有 MarketDataFetcher 拉取实时价格变动，包装成 ContentItem。
这是从原有系统迁移过来的核心数据源。
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pipeline.base import BaseSource
from pipeline.models import ContentItem, ContentType, PipelineContext
from models import MarketSnapshot


class MarketSource(BaseSource):
    """市场行情数据源 - 价格异动转化为内容项。"""

    source_name = "market"

    def __init__(self, fetcher=None, threshold_percent: float = 1.0):
        """
        Args:
            fetcher: MarketDataFetcher 实例。
            threshold_percent: 价格变动超过该阈值才生成内容项。
        """
        self._fetcher = fetcher
        self.threshold_percent = threshold_percent

    async def fetch(self, context: PipelineContext) -> List[ContentItem]:
        """从市场数据中拉取显著价格变动。"""
        if self._fetcher is None:
            return []

        items: List[ContentItem] = []
        try:
            snapshots: Dict[str, MarketSnapshot] = await self._fetcher.get_all_snapshots()
            symbols = context.topic_symbols or context.user_profile.watch_symbols

            for pair, snapshot in snapshots.items():
                # 如果指定了关注币种，则只关注相关的
                if symbols and snapshot.symbol not in [s.upper() for s in symbols]:
                    continue

                # 只有超过阈值的才生成内容
                change = snapshot.price_change_percent_24h
                if change is not None and abs(change) >= self.threshold_percent:
                    item = self._snapshot_to_content(snapshot)
                    if item:
                        items.append(item)
        except Exception:
            pass

        return items

    def _snapshot_to_content(self, snapshot: MarketSnapshot) -> Optional[ContentItem]:
        """将市场快照转化为 ContentItem。"""
        change = snapshot.price_change_percent_24h or 0.0
        direction = "📈" if change > 0 else "📉"
        title = f"{direction} {snapshot.symbol} {change:+.2f}% | ${snapshot.price:,.4f}"

        body = (
            f"{snapshot.symbol} 24h 变化 {change:+.2f}%，"
            f"当前价格 ${snapshot.price:,.4f}，"
            f"成交量 ${snapshot.volume_24h:,.0f}" if snapshot.volume_24h else ""
        )

        risk_tags = []
        if snapshot.market_cap and snapshot.market_cap < 1_000_000:
            risk_tags.append("small-cap")
        if snapshot.liquidity_usd and snapshot.liquidity_usd < 50_000:
            risk_tags.append("low-liquidity")
        if abs(change) >= 10:
            risk_tags.append("extreme-volatility")

        return ContentItem(
            content_id=f"market:{snapshot.pair}:{datetime.now().strftime('%Y%m%d%H%M')}",
            content_type=ContentType.PRICE_MOVEMENT,
            source=self.source_name,
            title=title,
            body=body,
            symbols=[snapshot.symbol],
            published_at=datetime.now(),
            price_change_percent=change,
            volume_24h=snapshot.volume_24h,
            market_cap=snapshot.market_cap,
            risk_tags=risk_tags,
            raw=snapshot.raw,
            metadata={
                "pair": snapshot.pair,
                "provider": snapshot.provider,
                "liquidity_usd": snapshot.liquidity_usd,
            },
        )
