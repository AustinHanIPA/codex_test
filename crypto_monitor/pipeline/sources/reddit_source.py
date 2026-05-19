"""
Reddit 数据源。

从 Reddit 加密货币相关 subreddit 拉取帖子。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from pipeline.base import BaseSource
from pipeline.models import ContentItem, ContentType, PipelineContext


# 默认关注的加密货币相关 subreddit
DEFAULT_SUBREDDITS = [
    "cryptocurrency",
    "CryptoMarkets",
    "Bitcoin",
    "ethereum",
    "solana",
    "defi",
]


class RedditSource(BaseSource):
    """Reddit 帖子数据源。"""

    source_name = "reddit"

    def __init__(
        self,
        api_url: str = "",
        timeout: int = 10,
        max_results: int = 40,
        subreddits: Optional[List[str]] = None,
    ):
        self.api_url = api_url or "https://www.reddit.com"
        self.timeout = timeout
        self.max_results = max_results
        self.subreddits = subreddits or DEFAULT_SUBREDDITS

    async def fetch(self, context: PipelineContext) -> List[ContentItem]:
        """从 Reddit 拉取加密货币相关帖子。"""
        items: List[ContentItem] = []
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={"User-Agent": "CryptoMonitor/2.0"},
            ) as session:
                for subreddit in self.subreddits[:4]:
                    posts = await self._fetch_subreddit(session, subreddit)
                    symbols = context.topic_symbols or context.user_profile.watch_symbols
                    for post in posts:
                        item = self._normalize_post(post, subreddit, symbols)
                        if item:
                            items.append(item)
        except Exception:
            pass

        return items[:self.max_results]

    async def _fetch_subreddit(
        self, session: aiohttp.ClientSession, subreddit: str
    ) -> List[Dict[str, Any]]:
        """获取 subreddit 热门帖子。"""
        url = f"{self.api_url}/r/{subreddit}/hot.json"
        params = {"limit": 15, "raw_json": 1}

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    children = data.get("data", {}).get("children", [])
                    return [child.get("data", {}) for child in children]
        except Exception:
            pass
        return []

    def _normalize_post(
        self, post: Dict[str, Any], subreddit: str, symbols: List[str]
    ) -> Optional[ContentItem]:
        """将 Reddit 帖子归一化为 ContentItem。"""
        title = post.get("title") or ""
        if not title:
            return None

        post_id = post.get("id") or post.get("name") or ""
        content_id = f"reddit:{post_id or hashlib.md5(title.encode()).hexdigest()[:12]}"

        selftext = post.get("selftext") or ""
        url = post.get("url") or f"https://reddit.com{post.get('permalink', '')}"

        published_at = None
        created_utc = post.get("created_utc")
        if created_utc:
            try:
                published_at = datetime.fromtimestamp(float(created_utc))
            except (ValueError, TypeError, OSError):
                pass

        # 匹配相关币种
        text_combined = f"{title} {selftext}".upper()
        matched_symbols = [s for s in symbols if s.upper() in text_combined]

        return ContentItem(
            content_id=content_id,
            content_type=ContentType.REDDIT_POST,
            source=self.source_name,
            title=title,
            body=selftext[:500],
            url=url,
            author=post.get("author") or "",
            author_followers=int(post.get("ups") or 0),  # 用 upvotes 近似影响力
            symbols=matched_symbols,
            published_at=published_at,
            raw=post,
            metadata={
                "subreddit": subreddit,
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "upvote_ratio": post.get("upvote_ratio", 0),
            },
        )
