"""
Twitter/X 数据源。

从 Twitter/X 拉取加密货币相关热点推文。
支持通过配置的 API 端点或 RSS 代理获取数据。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from pipeline.base import BaseSource
from pipeline.models import ContentItem, ContentType, PipelineContext


class TwitterSource(BaseSource):
    """Twitter/X 热点数据源。"""

    source_name = "twitter"

    def __init__(
        self,
        api_url: str = "",
        bearer_token: str = "",
        timeout: int = 10,
        max_results: int = 50,
    ):
        self.api_url = api_url
        self.bearer_token = bearer_token
        self.timeout = timeout
        self.max_results = max_results

    async def fetch(self, context: PipelineContext) -> List[ContentItem]:
        """从 Twitter 拉取与关注币种相关的热点推文。"""
        if not self.api_url:
            return []

        symbols = context.topic_symbols or context.user_profile.watch_symbols
        if not symbols:
            return []

        items: List[ContentItem] = []
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as session:
                for symbol in symbols[:5]:  # 限制并发
                    tweets = await self._search_tweets(session, symbol)
                    for tweet in tweets:
                        item = self._normalize_tweet(tweet, symbol)
                        if item:
                            items.append(item)
        except Exception:
            pass

        return items[:self.max_results]

    async def _search_tweets(
        self, session: aiohttp.ClientSession, symbol: str
    ) -> List[Dict[str, Any]]:
        """搜索指定币种的推文。"""
        headers = {}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        params = {
            "query": f"${symbol} OR #{symbol} crypto",
            "max_results": 20,
            "sort_order": "relevancy",
        }

        try:
            async with session.get(
                self.api_url, headers=headers, params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data") or data.get("tweets") or []
        except Exception:
            pass
        return []

    def _normalize_tweet(
        self, tweet: Dict[str, Any], symbol: str
    ) -> Optional[ContentItem]:
        """将推文数据归一化为 ContentItem。"""
        text = tweet.get("text") or tweet.get("content") or ""
        if not text:
            return None

        tweet_id = str(tweet.get("id") or tweet.get("tweet_id") or "")
        content_id = f"twitter:{tweet_id or hashlib.md5(text.encode()).hexdigest()[:12]}"

        author = tweet.get("author") or tweet.get("user") or {}
        author_name = ""
        followers = 0
        if isinstance(author, dict):
            author_name = author.get("username") or author.get("name") or ""
            followers = int(author.get("followers_count") or 0)
        elif isinstance(author, str):
            author_name = author

        published_at = None
        created = tweet.get("created_at") or tweet.get("published_at")
        if created:
            try:
                published_at = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return ContentItem(
            content_id=content_id,
            content_type=ContentType.TWITTER_POST,
            source=self.source_name,
            title=text[:80],
            body=text,
            url=tweet.get("url") or f"https://x.com/i/status/{tweet_id}" if tweet_id else "",
            author=author_name,
            author_followers=followers,
            symbols=[symbol.upper()],
            published_at=published_at,
            raw=tweet,
        )
