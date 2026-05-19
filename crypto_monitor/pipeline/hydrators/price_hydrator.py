"""
价格变化 Hydrator。

为内容项补充关联币种的价格变动信息。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pipeline.base import BaseHydrator
from pipeline.models import ContentItem, PipelineContext
from models import MarketSnapshot


class PriceHydrator(BaseHydrator):
    """补充价格变动数据。"""

    hydrator_name = "price"

    def __init__(self, fetcher=None):
        """
        Args:
            fetcher: MarketDataFetcher 实例。
        """
        self._fetcher = fetcher
        self._cache: Dict[str, MarketSnapshot] = {}

    async def hydrate(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """为每条内容补充其关联币种的价格变化。"""
        if not self._fetcher:
            return items

        # 刷新缓存
        await self._refresh_cache()

        for item in items:
            if item.filtered:
                continue
            if item.price_change_percent is not None:
                continue  # 已经有了

            # 取第一个关联币种的价格数据
            for symbol in item.symbols:
                pair = f"{symbol.upper()}USDT"
                snapshot = self._cache.get(pair)
                if snapshot:
                    item.price_change_percent = snapshot.price_change_percent_24h
                    item.market_cap = item.market_cap or snapshot.market_cap
                    item.volume_24h = item.volume_24h or snapshot.volume_24h
                    break

        return items

    async def _refresh_cache(self) -> None:
        """刷新市场数据缓存。"""
        try:
            snapshots = await self._fetcher.get_all_snapshots()
            self._cache = snapshots
        except Exception:
            pass
