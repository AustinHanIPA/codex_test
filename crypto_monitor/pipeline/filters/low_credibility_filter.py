"""
低可信来源过滤器。

过滤来自低可信度来源的内容，减少噪音。
"""
from __future__ import annotations

from typing import List, Set

from pipeline.base import BaseFilter
from pipeline.models import ContentItem, ContentType, PipelineContext


# 需要最低粉丝数才能通过的内容类型
FOLLOWER_THRESHOLDS = {
    ContentType.TWITTER_POST: 500,
    ContentType.KOL_OPINION: 1000,
}

# Reddit 最低 score 阈值
REDDIT_MIN_SCORE = 5

# YouTube 无需关注者限制（视频本身即有价值）


class LowCredibilityFilter(BaseFilter):
    """低可信来源过滤器。"""

    filter_name = "low_credibility"

    def __init__(
        self,
        min_followers: int = 500,
        blocked_sources: Set[str] | None = None,
    ):
        self.min_followers = min_followers
        self._blocked = blocked_sources or set()

    async def apply(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """过滤低可信来源的内容。"""
        # 合并用户黑名单
        user_blocked = set(context.user_profile.blocked_sources)
        all_blocked = self._blocked | user_blocked

        result: List[ContentItem] = []
        low_cred_count = 0

        for item in items:
            if item.filtered:
                result.append(item)
                continue

            if self._is_low_credibility(item, all_blocked):
                item.is_low_credibility = True
                item.filtered = True
                item.filter_reason = "low_credibility: source not trustworthy"
                low_cred_count += 1
            else:
                result.append(item)

        context.filter_stats["low_credibility_removed"] = low_cred_count
        return result

    def _is_low_credibility(
        self, item: ContentItem, blocked: Set[str]
    ) -> bool:
        """判断来源是否为低可信度。"""
        # 1. 检查黑名单
        if item.author.lower() in blocked:
            return True
        if item.source in blocked:
            return True

        # 2. Twitter/KOL 粉丝数检查
        threshold = FOLLOWER_THRESHOLDS.get(item.content_type)
        if threshold and item.author_followers < threshold:
            return True

        # 3. Reddit score 检查
        if item.content_type == ContentType.REDDIT_POST:
            score = item.metadata.get("score", 0)
            if score < REDDIT_MIN_SCORE:
                return True

        # 4. 匿名来源 + 无互动量
        if not item.author and item.author_followers == 0:
            if item.content_type in (ContentType.TWITTER_POST, ContentType.KOL_OPINION):
                return True

        return False
