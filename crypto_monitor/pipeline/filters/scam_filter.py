"""
诈骗币过滤器。

识别并过滤疑似诈骗/rug pull 的内容。
"""
from __future__ import annotations

from typing import List, Set

from pipeline.base import BaseFilter
from pipeline.models import ContentItem, PipelineContext


# 已知诈骗特征
SCAM_PATTERNS = [
    "guaranteed profit",
    "guaranteed returns",
    "risk free",
    "send to receive",
    "double your money",
    "double your crypto",
    "free airdrop claim now",
    "connect wallet to claim",
    "whitelist guaranteed",
    "dm for access",
    "稳赚不赔",
    "保本高收益",
    "内部消息必涨",
]

# 已知诈骗来源黑名单
BLACKLISTED_SOURCES: Set[str] = set()

# 高风险币种模式（新创建 + 无背景）
HONEYPOT_TAGS = {"potential-scam", "new-token"}


class ScamFilter(BaseFilter):
    """诈骗/Rug 过滤器。"""

    filter_name = "scam"

    def __init__(
        self,
        blacklisted_sources: Set[str] | None = None,
        strict_mode: bool = False,
    ):
        self._blacklisted = blacklisted_sources or BLACKLISTED_SOURCES
        self.strict_mode = strict_mode

    async def apply(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """过滤疑似诈骗内容。"""
        result: List[ContentItem] = []
        scam_count = 0

        for item in items:
            if item.filtered:
                result.append(item)
                continue

            if self._is_scam(item):
                item.is_scam = True
                item.filtered = True
                item.filter_reason = "scam: suspected fraudulent content"
                scam_count += 1
            else:
                result.append(item)

        context.filter_stats["scam_removed"] = scam_count
        return result

    def _is_scam(self, item: ContentItem) -> bool:
        """判断内容是否为诈骗。"""
        # 1. 来源黑名单
        if item.author.lower() in self._blacklisted:
            return True
        if item.source in self._blacklisted:
            return True

        # 2. 内容中的诈骗模式
        text = f"{item.title} {item.body}".lower()
        scam_hits = sum(1 for pattern in SCAM_PATTERNS if pattern.lower() in text)
        if scam_hits >= 2:
            return True

        # 3. 风险标签检测
        risk_tags = set(item.risk_tags)
        if "potential-scam" in risk_tags:
            if self.strict_mode:
                return True
            # 宽松模式下需要额外条件
            if item.author_followers < 100:
                return True

        return False
