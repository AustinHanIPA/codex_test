"""
加权综合选择器。

依据各维度评分的加权综合计算最终得分，按得分排序截取 Top-N。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from pipeline.base import BaseSelector
from pipeline.models import ContentItem, PipelineContext


@dataclass
class ScoreWeights:
    """各维度评分的权重配置。"""
    hotness: float = 0.25
    credibility: float = 0.25
    impact: float = 0.30
    relevance: float = 0.20

    def normalize(self) -> "ScoreWeights":
        """归一化权重使其总和为 1.0。"""
        total = self.hotness + self.credibility + self.impact + self.relevance
        if total == 0:
            return ScoreWeights(0.25, 0.25, 0.25, 0.25)
        return ScoreWeights(
            hotness=self.hotness / total,
            credibility=self.credibility / total,
            impact=self.impact / total,
            relevance=self.relevance / total,
        )


class WeightedSelector(BaseSelector):
    """
    加权综合选择器。

    将 hotness / credibility / impact / relevance 四维评分
    按可配置权重计算 score_final，按最终得分降序排列后截取 Top-N。
    """

    def __init__(self, weights: ScoreWeights | None = None):
        self.weights = (weights or ScoreWeights()).normalize()

    async def select(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """综合打分 + 排序 + 截取。"""
        # 1. 计算最终综合得分
        active_items = [item for item in items if not item.filtered]

        for item in active_items:
            item.score_final = (
                item.score_hotness * self.weights.hotness
                + item.score_credibility * self.weights.credibility
                + item.score_impact * self.weights.impact
                + item.score_relevance * self.weights.relevance
            )

        # 2. 按综合得分降序排列
        active_items.sort(key=lambda x: x.score_final, reverse=True)

        # 3. 截取 Top-N
        max_items = context.max_items
        selected = active_items[:max_items]

        return selected
