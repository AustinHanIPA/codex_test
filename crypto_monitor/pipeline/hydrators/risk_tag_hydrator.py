"""
风险标签 Hydrator。

基于多维度规则为内容项打上风险标签。
"""
from __future__ import annotations

from typing import List, Set

from pipeline.base import BaseHydrator
from pipeline.models import ContentItem, ContentType, PipelineContext


# 已知高风险特征
SCAM_KEYWORDS = [
    "guaranteed profit", "100x", "1000x", "free airdrop",
    "send to receive", "double your", "whitelist spot",
    "guaranteed returns", "risk free", "稳赚", "保本",
    "翻倍", "内部消息",
]

# 低流动性阈值
LOW_LIQUIDITY_THRESHOLD_USD = 50_000
# 小市值阈值
SMALL_CAP_THRESHOLD_USD = 1_000_000
# 极端波动阈值
EXTREME_VOLATILITY_THRESHOLD = 15.0


class RiskTagHydrator(BaseHydrator):
    """为内容项补充风险标签。"""

    hydrator_name = "risk_tags"

    async def hydrate(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """扫描内容并打上风险标签。"""
        for item in items:
            if item.filtered:
                continue

            new_tags = self._evaluate_risks(item)
            # 合并标签（去重）
            existing = set(item.risk_tags)
            for tag in new_tags:
                if tag not in existing:
                    item.risk_tags.append(tag)

        return items

    def _evaluate_risks(self, item: ContentItem) -> List[str]:
        """评估内容的各类风险。"""
        tags: List[str] = []

        # 1. 检测诈骗关键词
        text = f"{item.title} {item.body}".lower()
        for keyword in SCAM_KEYWORDS:
            if keyword.lower() in text:
                tags.append("potential-scam")
                break

        # 2. 小市值风险
        if item.market_cap and item.market_cap < SMALL_CAP_THRESHOLD_USD:
            tags.append("small-cap")

        # 3. 低流动性风险
        liquidity = item.metadata.get("liquidity_usd")
        if liquidity and liquidity < LOW_LIQUIDITY_THRESHOLD_USD:
            tags.append("low-liquidity")

        # 4. 极端波动
        if item.price_change_percent and abs(item.price_change_percent) >= EXTREME_VOLATILITY_THRESHOLD:
            tags.append("extreme-volatility")

        # 5. Meme 币标记
        category = item.metadata.get("project_category", "").lower()
        if "meme" in category:
            tags.append("meme-coin")

        # 6. 新币（上线不足7天）标记
        if item.content_type == ContentType.ONCHAIN_ALERT:
            event_type = item.metadata.get("event_type", "")
            if event_type == "NewPairCreated":
                tags.append("new-token")

        # 7. 匿名来源
        if not item.author and item.content_type in (
            ContentType.TWITTER_POST,
            ContentType.KOL_OPINION,
        ):
            tags.append("anonymous-source")

        return tags
