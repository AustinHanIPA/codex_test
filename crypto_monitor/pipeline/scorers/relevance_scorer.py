"""
用户兴趣匹配分 Scorer。

基于用户画像（关注币种、风险偏好、历史行为）计算个性化匹配度。
"""
from __future__ import annotations

from typing import List, Set

from pipeline.base import BaseScorer
from pipeline.models import ContentItem, ContentType, PipelineContext, RiskLevel


class RelevanceScorer(BaseScorer):
    """用户兴趣匹配评分器。"""

    scorer_name = "relevance"

    async def score(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """计算每条内容与用户兴趣的匹配度 (0~100)。"""
        profile = context.user_profile

        for item in items:
            if item.filtered:
                continue
            item.score_relevance = self._calculate_relevance(item, context)

        return items

    def _calculate_relevance(
        self, item: ContentItem, context: PipelineContext
    ) -> float:
        """
        匹配度 = 币种匹配 + 内容类型偏好 + 风险偏好匹配 + 历史行为相关性
        """
        profile = context.user_profile
        score = 0.0

        # 1. 币种匹配（最重要）
        score += self._symbol_match_score(item, profile.watch_symbols)

        # 2. 内容类型偏好
        score += self._content_type_match(item, profile.preferred_content_types)

        # 3. 风险偏好匹配
        score += self._risk_preference_match(item, profile.risk_preference)

        # 4. 话题/查询相关性
        score += self._query_relevance(item, context)

        # 5. 黑名单扣分
        score -= self._blacklist_penalty(item, profile.blocked_symbols)

        return max(0.0, min(100.0, score))

    @staticmethod
    def _symbol_match_score(item: ContentItem, watch_symbols: List[str]) -> float:
        """币种匹配度。"""
        if not watch_symbols or not item.symbols:
            return 20.0  # 给一个基础分

        watch_set: Set[str] = {s.upper() for s in watch_symbols}
        item_set: Set[str] = {s.upper() for s in item.symbols}

        # 完全匹配
        matches = watch_set & item_set
        if matches:
            # 匹配数量越多分越高
            return min(50.0, 30.0 + len(matches) * 10.0)

        return 10.0  # 不在关注列表但不扣太多

    @staticmethod
    def _content_type_match(
        item: ContentItem, preferred_types: List[ContentType]
    ) -> float:
        """内容类型偏好匹配。"""
        if not preferred_types:
            return 15.0  # 没有偏好设置，给中等分

        if item.content_type in preferred_types:
            return 20.0

        return 5.0

    @staticmethod
    def _risk_preference_match(item: ContentItem, risk_level: RiskLevel) -> float:
        """风险偏好匹配。"""
        has_risk = bool(item.risk_tags)

        if risk_level == RiskLevel.CONSERVATIVE:
            # 保守型用户不喜欢高风险内容
            if has_risk:
                risky_tags = {"extreme-volatility", "meme-coin", "new-token", "low-liquidity"}
                if set(item.risk_tags) & risky_tags:
                    return 0.0
            return 15.0

        elif risk_level == RiskLevel.AGGRESSIVE:
            # 激进型用户偏好高波动和新项目
            if "extreme-volatility" in item.risk_tags:
                return 20.0
            if "meme-coin" in item.risk_tags or "new-token" in item.risk_tags:
                return 15.0
            return 10.0

        else:  # MODERATE
            return 10.0

    @staticmethod
    def _query_relevance(item: ContentItem, context: PipelineContext) -> float:
        """话题/查询相关性。"""
        if not context.query:
            return 0.0

        query_lower = context.query.lower()
        text = f"{item.title} {item.body}".lower()

        # 简单包含检查
        if query_lower in text:
            return 15.0

        # 词汇重叠
        query_words = set(query_lower.split())
        text_words = set(text.split())
        overlap = query_words & text_words
        if overlap:
            return min(10.0, len(overlap) * 3.0)

        return 0.0

    @staticmethod
    def _blacklist_penalty(item: ContentItem, blocked_symbols: List[str]) -> float:
        """黑名单扣分。"""
        if not blocked_symbols:
            return 0.0

        blocked_set = {s.upper() for s in blocked_symbols}
        item_symbols = {s.upper() for s in item.symbols}

        if blocked_set & item_symbols:
            return 50.0  # 重大扣分

        return 0.0
