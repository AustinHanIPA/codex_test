"""
KOL（Key Opinion Leader）数据源。

从知名 KOL 的公开发言中拉取观点和分析。
可以对接 Twitter 大 V 专属列表或自建 KOL 数据库。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from pipeline.base import BaseSource
from pipeline.models import ContentItem, ContentType, PipelineContext


# 默认 KOL 列表（可通过配置覆盖）
DEFAULT_KOL_IDS = [
    # 示例: {"name": "Cobie", "platform": "twitter", "id": "..."}
]


class KOLSource(BaseSource):
    """KOL 发言数据源。"""

    source_name = "kol"

    def __init__(
        self,
        api_url: str = "",
        kol_list: Optional[List[Dict[str, str]]] = None,
        timeout: int = 10,
        max_results: int = 30,
    ):
        self.api_url = api_url
        self.kol_list = kol_list or DEFAULT_KOL_IDS
        self.timeout = timeout
        self.max_results = max_results

    async def fetch(self, context: PipelineContext) -> List[ContentItem]:
        """从 KOL 数据源拉取发言。"""
        if not self.api_url or not self.kol_list:
            return []

        items: List[ContentItem] = []
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as session:
                posts = await self._fetch_kol_posts(session, context)
                for post in posts:
                    item = self._normalize_kol_post(post, context)
                    if item:
                        items.append(item)
        except Exception:
            pass

        return items[:self.max_results]

    async def _fetch_kol_posts(
        self, session: aiohttp.ClientSession, context: PipelineContext
    ) -> List[Dict[str, Any]]:
        """拉取 KOL 发言列表。"""
        symbols = context.topic_symbols or context.user_profile.watch_symbols
        params: Dict[str, Any] = {}
        if symbols:
            params["symbols"] = ",".join(symbols[:10])

        try:
            async with session.get(self.api_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("posts") or data.get("data") or []
        except Exception:
            pass
        return []

    def _normalize_kol_post(
        self, post: Dict[str, Any], context: PipelineContext
    ) -> Optional[ContentItem]:
        """将 KOL 发言归一化为 ContentItem。"""
        text = post.get("text") or post.get("content") or post.get("body") or ""
        if not text:
            return None

        post_id = str(post.get("id") or "")
        content_id = f"kol:{post_id or hashlib.md5(text.encode()).hexdigest()[:12]}"

        author_name = post.get("author") or post.get("kol_name") or post.get("username") or ""
        followers = int(post.get("followers") or post.get("followers_count") or 0)

        published_at = None
        created = post.get("created_at") or post.get("published_at")
        if created:
            try:
                published_at = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # 提取关联币种
        symbols = post.get("symbols") or post.get("currencies") or []
        if not symbols:
            all_symbols = context.topic_symbols or context.user_profile.watch_symbols
            text_upper = text.upper()
            symbols = [s for s in all_symbols if s.upper() in text_upper]

        return ContentItem(
            content_id=content_id,
            content_type=ContentType.KOL_OPINION,
            source=self.source_name,
            title=text[:80],
            body=text,
            url=post.get("url") or "",
            author=author_name,
            author_followers=followers,
            symbols=symbols,
            published_at=published_at,
            raw=post,
            metadata={
                "platform": post.get("platform") or "twitter",
                "engagement": post.get("engagement") or post.get("likes", 0),
                "is_verified": post.get("is_verified", False),
            },
        )
