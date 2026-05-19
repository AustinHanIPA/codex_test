"""
潜在影响分 Scorer。

评估内容对市场可能产生的影响程度。
"""
from __future__ import annotations

from typing import List

from pipeline.base import BaseScorer
from pipeline.models import ContentItem, ContentType, PipelineContext


class ImpactScorer(BaseScorer):
    """潜在影响评分器。"""

    scorer_name = "impact"

    async def score(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """计算每条内容的潜在影响分 (0~100)。"""
        for item in items:
            if item.filtered:
                continue
            item.score_impact = self._calculate_impact(item)

        return items

    def _calculate_impact(self, item: ContentItem) -> float:
        """
        潜在影响 = 事件严重度 × 市值权重 × 波动信号 + 鲸鱼活动加分
        """
        score = 0.0

        # 1. 事件类型基础影响分
        score += self._event_base_impact(item)

        # 2. 价格波动信号
        score += self._volatility_signal(item)

        # 3. 成交量异动
        score += self._volume_signal(item)

        # 4. 鲸鱼/大额活动
        score += self._whale_signal(item)

        # 5. KOL 影响力权重
        score += self._kol_influence(item)

        # 6. 情绪极性
        score += self._sentiment_signal(item)

        return max(0.0, min(100.0, score))

    @staticmethod
    def _event_base_impact(item: ContentItem) -> float:
        """事件类型的基础影响分。"""
        base_scores = {
            ContentType.ONCHAIN_ALERT: 40.0,
            ContentType.PRICE_MOVEMENT: 35.0,
            ContentType.RISK_WARNING: 45.0,
            ContentType.KOL_OPINION: 25.0,
            ContentType.NEWS: 30.0,
            ContentType.TWITTER_POST: 15.0,
            ContentType.REDDIT_POST: 10.0,
            ContentType.YOUTUBE_VIDEO: 10.0,
        }
        return base_scores.get(item.content_type, 15.0)

    @staticmethod
    def _volatility_signal(item: ContentItem) -> float:
        """价格波动对影响的贡献。"""
        if item.price_change_percent is None:
            return 0.0

        abs_change = abs(item.price_change_percent)
        if abs_change >= 10:
            return 25.0
        elif abs_change >= 5:
            return 15.0
        elif abs_change >= 3:
            return 10.0
        elif abs_change >= 1:
            return 5.0
        return 0.0

    @staticmethod
    def _volume_signal(item: ContentItem) -> float:
        """成交量异动对影响的贡献。"""
        spike = item.metadata.get("volume_spike_ratio")
        if spike and spike >= 5:
            return 15.0
        elif spike and spike >= 3:
            return 10.0
        elif spike and spike >= 2:
            return 5.0
        return 0.0

    @staticmethod
    def _whale_signal(item: ContentItem) -> float:
        """鲸鱼活动对影响的贡献。"""
        if item.content_type != ContentType.ONCHAIN_ALERT:
            return 0.0

        amount_usd = item.metadata.get("amount_usd")
        if amount_usd is None:
            return 0.0

        if amount_usd >= 1_000_000:
            return 20.0
        elif amount_usd >= 500_000:
            return 15.0
        elif amount_usd >= 100_000:
            return 10.0
        return 0.0

    @staticmethod
    def _kol_influence(item: ContentItem) -> float:
        """KOL 影响力贡献。"""
        if item.content_type not in (ContentType.KOL_OPINION, ContentType.TWITTER_POST):
            return 0.0

        followers = item.author_followers
        if followers >= 1_000_000:
            return 15.0
        elif followers >= 100_000:
            return 10.0
        elif followers >= 10_000:
            return 5.0
        return 0.0

    @staticmethod
    def _sentiment_signal(item: ContentItem) -> float:
        """情绪极端性对影响的贡献。"""
        if item.sentiment_score is None:
            return 0.0

        # 极端情绪（无论正负）都意味着更大影响
        abs_sentiment = abs(item.sentiment_score)
        if abs_sentiment >= 0.8:
            return 10.0
        elif abs_sentiment >= 0.5:
            return 5.0
        return 0.0
