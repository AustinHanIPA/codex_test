"""
热度分 Scorer。

基于内容的互动量、传播速度、时效性等维度计算热度。
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import List

from pipeline.base import BaseScorer
from pipeline.models import ContentItem, ContentType, PipelineContext


class HotnessScorer(BaseScorer):
    """热度评分器。"""

    scorer_name = "hotness"

    # 时间衰减半衰期（小时）
    HALF_LIFE_HOURS = 6.0

    async def score(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """计算每条内容的热度分 (0~100)。"""
        now = datetime.now()

        for item in items:
            if item.filtered:
                continue
            item.score_hotness = self._calculate_hotness(item, now)

        return items

    def _calculate_hotness(self, item: ContentItem, now: datetime) -> float:
        """
        热度 = 基础互动分 × 时间衰减因子 × 内容类型加权

        基础互动分 = log(1 + engagement)
        时间衰减 = 2^(-age_hours / half_life)
        """
        # 1. 基础互动分
        engagement = self._get_engagement(item)
        base_score = math.log1p(engagement) * 10

        # 2. 时间衰减
        time_decay = self._time_decay(item, now)

        # 3. 内容类型加权
        type_weight = self._type_weight(item.content_type)

        # 4. 价格波动加成
        volatility_bonus = 0.0
        if item.price_change_percent:
            volatility_bonus = min(abs(item.price_change_percent) * 2, 20)

        raw_score = base_score * time_decay * type_weight + volatility_bonus
        return max(0.0, min(100.0, raw_score))

    def _get_engagement(self, item: ContentItem) -> float:
        """获取内容互动量。"""
        engagement = float(item.author_followers)

        # Reddit 特有指标
        if item.content_type == ContentType.REDDIT_POST:
            score = item.metadata.get("score", 0)
            comments = item.metadata.get("num_comments", 0)
            engagement = float(score + comments * 2)

        # KOL 互动量
        if item.content_type == ContentType.KOL_OPINION:
            engagement = float(
                item.metadata.get("engagement", 0) or item.author_followers
            )

        return max(1.0, engagement)

    def _time_decay(self, item: ContentItem, now: datetime) -> float:
        """时间衰减因子。"""
        if item.published_at is None:
            return 0.5  # 没有时间戳给中等权重

        published = item.published_at
        if published.tzinfo is not None:
            published = published.replace(tzinfo=None)

        age_hours = (now - published).total_seconds() / 3600
        if age_hours < 0:
            age_hours = 0

        return math.pow(2, -age_hours / self.HALF_LIFE_HOURS)

    @staticmethod
    def _type_weight(content_type: ContentType) -> float:
        """不同内容类型的热度权重。"""
        weights = {
            ContentType.ONCHAIN_ALERT: 1.5,      # 链上异动热度高
            ContentType.PRICE_MOVEMENT: 1.3,     # 价格变动热度高
            ContentType.KOL_OPINION: 1.2,        # KOL 观点
            ContentType.NEWS: 1.0,               # 新闻基准
            ContentType.TWITTER_POST: 0.9,       # 推特
            ContentType.REDDIT_POST: 0.8,        # Reddit
            ContentType.YOUTUBE_VIDEO: 0.7,      # YouTube 时效性较低
            ContentType.RISK_WARNING: 1.4,       # 风险提醒优先
        }
        return weights.get(content_type, 1.0)
