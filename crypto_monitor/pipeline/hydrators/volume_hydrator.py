"""
成交量 Hydrator。

为内容项补充成交量异动信息。
"""
from __future__ import annotations

from typing import Dict, List

from pipeline.base import BaseHydrator
from pipeline.models import ContentItem, PipelineContext


class VolumeHydrator(BaseHydrator):
    """补充成交量信息和异动检测。"""

    hydrator_name = "volume"

    def __init__(self, storage=None):
        """
        Args:
            storage: Storage 实例，用于获取历史成交量数据。
        """
        self._storage = storage

    async def hydrate(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """为内容项补充成交量异动信息。"""
        if not self._storage:
            return items

        # 获取各币种近期平均成交量
        volume_baselines: Dict[str, float] = {}

        for item in items:
            if item.filtered:
                continue
            if item.volume_24h is None:
                continue

            for symbol in item.symbols:
                if symbol not in volume_baselines:
                    volume_baselines[symbol] = await self._get_baseline_volume(symbol)

                baseline = volume_baselines.get(symbol, 0)
                if baseline > 0 and item.volume_24h > 0:
                    spike_ratio = item.volume_24h / baseline
                    if spike_ratio >= 2.0:
                        if "volume-spike" not in item.risk_tags:
                            item.risk_tags.append("volume-spike")
                        item.metadata["volume_spike_ratio"] = round(spike_ratio, 2)

        return items

    async def _get_baseline_volume(self, symbol: str) -> float:
        """获取币种近期平均成交量作为基线。"""
        try:
            history = await self._storage.get_price_history(symbol, hours=72, limit=50)
            volumes = [
                h["volume_24h"]
                for h in history
                if h.get("volume_24h") and h["volume_24h"] > 0
            ]
            if volumes:
                return sum(volumes) / len(volumes)
        except Exception:
            pass
        return 0.0
