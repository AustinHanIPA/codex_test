"""
旧闻过滤器。

过滤已经过时的新闻和信息，确保推荐内容的时效性。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from pipeline.base import BaseFilter
from pipeline.models import ContentItem, ContentType, PipelineContext


# 不同内容类型的最大时效（小时）
DEFAULT_MAX_AGE_HOURS = {
    ContentType.NEWS: 24,
    ContentType.TWITTER_POST: 12,
    ContentType.REDDIT_POST: 48,
    ContentType.YOUTUBE_VIDEO: 72,
    ContentType.KOL_OPINION: 24,
    ContentType.ONCHAIN_ALERT: 6,
    ContentType.PRICE_MOVEMENT: 1,
    ContentType.RISK_WARNING: 12,
}


class StaleFilter(BaseFilter):
    """旧闻过滤器。"""

    filter_name = "stale"

    def __init__(self, max_age_hours: int | None = None):
        """
        Args:
            max_age_hours: 全局最大时效（小时）。如果设置，覆盖类型默认值。
        """
        self.max_age_hours = max_age_hours

    async def apply(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """过滤过时内容。"""
        now = datetime.now()
        result: List[ContentItem] = []
        stale_count = 0

        for item in items:
            if item.filtered:
                result.append(item)
                continue

            if self._is_stale(item, now):
                item.is_stale = True
                item.filtered = True
                item.filter_reason = "stale: content too old"
                stale_count += 1
            else:
                result.append(item)

        context.filter_stats["stale_removed"] = stale_count
        return result

    def _is_stale(self, item: ContentItem, now: datetime) -> bool:
        """判断内容是否过时。"""
        if item.published_at is None:
            return False  # 没有时间戳的不过滤

        # 处理时区
        published = item.published_at
        if published.tzinfo is not None:
            published = published.replace(tzinfo=None)

        max_hours = self.max_age_hours
        if max_hours is None:
            max_hours = DEFAULT_MAX_AGE_HOURS.get(item.content_type, 24)

        age = now - published
        return age > timedelta(hours=max_hours)
