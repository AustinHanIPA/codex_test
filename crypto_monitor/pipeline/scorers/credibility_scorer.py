"""
可信度分 Scorer。

基于来源可靠性、作者声誉、信息交叉验证等维度评估可信度。
"""
from __future__ import annotations

import math
from typing import Dict, List

from pipeline.base import BaseScorer
from pipeline.models import ContentItem, ContentType, PipelineContext


# 来源可信度基准分
SOURCE_CREDIBILITY_BASE: Dict[str, float] = {
    "onchain": 90.0,     # 链上数据客观可查
    "market": 85.0,      # 市场数据客观
    "news": 70.0,        # 新闻有编辑审核
    "reddit": 50.0,      # Reddit 社区内容
    "twitter": 45.0,     # Twitter 噪音较大
    "youtube": 55.0,     # YouTube 视频有门槛
    "kol": 60.0,         # KOL 有声誉约束
}


class CredibilityScorer(BaseScorer):
    """可信度评分器。"""

    scorer_name = "credibility"

    async def score(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """计算每条内容的可信度分 (0~100)。"""
        for item in items:
            if item.filtered:
                continue
            item.score_credibility = self._calculate_credibility(item)

        return items

    def _calculate_credibility(self, item: ContentItem) -> float:
        """
        可信度 = 来源基准分 + 作者声誉加分 + 内容质量加分 - 风险扣分

        最终归一化到 0~100。
        """
        # 1. 来源基准分
        base = SOURCE_CREDIBILITY_BASE.get(item.source, 50.0)

        # 2. 作者声誉加分
        author_bonus = self._author_reputation_bonus(item)

        # 3. 内容质量加分
        quality_bonus = self._content_quality_bonus(item)

        # 4. 风险扣分
        risk_penalty = self._risk_penalty(item)

        raw_score = base + author_bonus + quality_bonus - risk_penalty
        return max(0.0, min(100.0, raw_score))

    @staticmethod
    def _author_reputation_bonus(item: ContentItem) -> float:
        """基于作者粉丝数/声誉的加分。"""
        if item.author_followers <= 0:
            return 0.0

        # 对数增长，避免超大 V 过度占优
        bonus = math.log10(item.author_followers) * 5
        return min(bonus, 25.0)

    @staticmethod
    def _content_quality_bonus(item: ContentItem) -> float:
        """基于内容质量的加分。"""
        bonus = 0.0

        # 有具体数据支撑
        if item.price_change_percent is not None:
            bonus += 5.0
        if item.volume_24h is not None:
            bonus += 3.0

        # 有多来源交叉验证
        if len(item.symbols) > 0 and item.project_background:
            bonus += 5.0

        # 内容长度合理（不是过短的噪音）
        body_len = len(item.body)
        if body_len >= 50:
            bonus += 3.0
        if body_len >= 200:
            bonus += 2.0

        # KOL 认证
        if item.metadata.get("is_verified"):
            bonus += 10.0

        return min(bonus, 20.0)

    @staticmethod
    def _risk_penalty(item: ContentItem) -> float:
        """风险标签导致的扣分。"""
        penalty = 0.0

        risk_penalties = {
            "potential-scam": 30.0,
            "anonymous-source": 15.0,
            "low-liquidity": 10.0,
            "extreme-volatility": 5.0,
            "new-token": 10.0,
        }

        for tag in item.risk_tags:
            penalty += risk_penalties.get(tag, 0.0)

        return min(penalty, 50.0)
