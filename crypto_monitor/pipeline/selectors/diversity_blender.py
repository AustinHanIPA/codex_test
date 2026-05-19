"""
多样性混排器。

在 WeightedSelector 的基础上进一步保证内容多样性：
- 来源多样性：防止单一来源刷屏
- 币种多样性：覆盖更多用户关注的币种
- 内容类型多样性：平衡新闻、KOL观点、链上异动等
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Set

from pipeline.base import BaseSelector
from pipeline.models import ContentItem, PipelineContext


class DiversityBlender(BaseSelector):
    """
    多样性混排选择器。

    使用轮询机制保证内容来源、币种和类型的多样性。
    diversity_ratio 控制多样性的强度（0 = 纯得分排序，1 = 完全均分来源）。
    """

    def __init__(
        self,
        max_per_source: int = 5,
        max_per_symbol: int = 4,
        diversity_ratio: float | None = None,
    ):
        self.max_per_source = max_per_source
        self.max_per_symbol = max_per_symbol
        self.diversity_ratio_override = diversity_ratio

    async def select(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """多样性混排选择。"""
        active_items = [item for item in items if not item.filtered]

        if not active_items:
            return []

        # 使用 context 中的 diversity_ratio（或初始化覆盖值）
        diversity_ratio = self.diversity_ratio_override or context.diversity_ratio
        max_items = context.max_items

        # 如果 diversity_ratio 为 0，退化为纯得分排序
        if diversity_ratio <= 0:
            active_items.sort(key=lambda x: x.score_final, reverse=True)
            return active_items[:max_items]

        # 混排：得分排序部分 + 多样性部分
        score_slots = int(max_items * (1 - diversity_ratio))
        diversity_slots = max_items - score_slots

        # === 得分部分：按 score_final 降序 ===
        active_items.sort(key=lambda x: x.score_final, reverse=True)
        score_selected = active_items[:score_slots]
        selected_ids: Set[str] = {item.content_id for item in score_selected}

        # === 多样性部分：轮询不同来源/类型 ===
        remaining = [it for it in active_items if it.content_id not in selected_ids]
        diversity_selected = self._round_robin_select(
            remaining, diversity_slots, selected_ids
        )

        # 合并
        result = score_selected + diversity_selected

        # 最终限流：单来源上限
        result = self._apply_source_cap(result)

        # 单币种上限
        result = self._apply_symbol_cap(result)

        return result[:max_items]

    def _round_robin_select(
        self,
        candidates: List[ContentItem],
        slots: int,
        already_selected: Set[str],
    ) -> List[ContentItem]:
        """从各来源轮询选取以保证多样性。"""
        # 按来源分组
        by_source: Dict[str, List[ContentItem]] = defaultdict(list)
        for item in candidates:
            by_source[item.source].append(item)

        selected: List[ContentItem] = []
        source_keys = list(by_source.keys())
        idx = 0

        while len(selected) < slots and source_keys:
            source = source_keys[idx % len(source_keys)]
            bucket = by_source[source]

            if bucket:
                item = bucket.pop(0)
                if item.content_id not in already_selected:
                    selected.append(item)
                    already_selected.add(item.content_id)
            else:
                source_keys.remove(source)
                if not source_keys:
                    break
                continue

            idx += 1

        return selected

    def _apply_source_cap(self, items: List[ContentItem]) -> List[ContentItem]:
        """限制单一来源的数量上限。"""
        source_count: Dict[str, int] = defaultdict(int)
        result: List[ContentItem] = []

        for item in items:
            if source_count[item.source] < self.max_per_source:
                result.append(item)
                source_count[item.source] += 1

        return result

    def _apply_symbol_cap(self, items: List[ContentItem]) -> List[ContentItem]:
        """限制单一币种的数量上限。"""
        symbol_count: Dict[str, int] = defaultdict(int)
        result: List[ContentItem] = []

        for item in items:
            # 检查该 item 关联的任一币种是否已超限
            if not item.symbols:
                result.append(item)
                continue

            over_limit = any(
                symbol_count[s.upper()] >= self.max_per_symbol
                for s in item.symbols
            )

            if not over_limit:
                result.append(item)
                for s in item.symbols:
                    symbol_count[s.upper()] += 1

        return result
