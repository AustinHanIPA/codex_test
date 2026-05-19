"""
情绪分析 Hydrator。

使用 AI 服务或简单规则为内容项添加情绪标注。
"""
from __future__ import annotations

import re
from typing import List

from pipeline.base import BaseHydrator
from pipeline.models import ContentItem, PipelineContext


# 简单关键词情绪词典
BULLISH_KEYWORDS = [
    "moon", "pump", "bullish", "ath", "breakout", "🚀", "📈",
    "surge", "rally", "buy", "long", "profit", "explosive",
    "涨", "暴涨", "看多", "利好", "突破",
]

BEARISH_KEYWORDS = [
    "dump", "crash", "bearish", "rug", "scam", "sell", "short",
    "📉", "💀", "collapse", "drop", "fear", "panic",
    "跌", "暴跌", "看空", "利空", "崩盘", "清算",
]


class SentimentHydrator(BaseHydrator):
    """补充情绪分析数据。"""

    hydrator_name = "sentiment"

    def __init__(self, ai_service=None):
        """
        Args:
            ai_service: AI 服务实例，用于高级情绪分析。
                        如果为 None 则使用基于关键词的简单分析。
        """
        self._ai_service = ai_service

    async def hydrate(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """为内容项补充情绪分析。"""
        for item in items:
            if item.filtered:
                continue
            if item.sentiment is not None:
                continue  # 已经有了

            sentiment, score = self._analyze_sentiment(item)
            item.sentiment = sentiment
            item.sentiment_score = score

        return items

    def _analyze_sentiment(self, item: ContentItem) -> tuple[str, float]:
        """基于关键词的情绪分析。"""
        text = f"{item.title} {item.body}".lower()

        bullish_count = sum(
            1 for keyword in BULLISH_KEYWORDS if keyword.lower() in text
        )
        bearish_count = sum(
            1 for keyword in BEARISH_KEYWORDS if keyword.lower() in text
        )

        total = bullish_count + bearish_count
        if total == 0:
            return "neutral", 0.0

        score = (bullish_count - bearish_count) / max(total, 1)
        score = max(-1.0, min(1.0, score))

        if score > 0.2:
            return "bullish", score
        elif score < -0.2:
            return "bearish", score
        else:
            return "neutral", score
