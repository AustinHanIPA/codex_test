"""
YouTube 数据源。

从 YouTube 拉取加密货币相关视频内容。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from pipeline.base import BaseSource
from pipeline.models import ContentItem, ContentType, PipelineContext


class YouTubeSource(BaseSource):
    """YouTube 视频数据源。"""

    source_name = "youtube"

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        timeout: int = 10,
        max_results: int = 30,
    ):
        self.api_url = api_url or "https://www.googleapis.com/youtube/v3/search"
        self.api_key = api_key
        self.timeout = timeout
        self.max_results = max_results

    async def fetch(self, context: PipelineContext) -> List[ContentItem]:
        """从 YouTube 拉取与关注币种相关的视频。"""
        if not self.api_key:
            return []

        symbols = context.topic_symbols or context.user_profile.watch_symbols
        if not symbols:
            return []

        items: List[ContentItem] = []
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as session:
                query = " OR ".join([f"{s} crypto" for s in symbols[:3]])
                videos = await self._search_videos(session, query)
                for video in videos:
                    item = self._normalize_video(video, symbols)
                    if item:
                        items.append(item)
        except Exception:
            pass

        return items[:self.max_results]

    async def _search_videos(
        self, session: aiohttp.ClientSession, query: str
    ) -> List[Dict[str, Any]]:
        """搜索 YouTube 视频。"""
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "date",
            "maxResults": min(self.max_results, 50),
            "key": self.api_key,
        }

        try:
            async with session.get(self.api_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("items") or []
        except Exception:
            pass
        return []

    def _normalize_video(
        self, video: Dict[str, Any], symbols: List[str]
    ) -> Optional[ContentItem]:
        """将 YouTube 视频数据归一化为 ContentItem。"""
        snippet = video.get("snippet") or {}
        video_id_obj = video.get("id") or {}
        video_id = video_id_obj.get("videoId") if isinstance(video_id_obj, dict) else str(video_id_obj)

        title = snippet.get("title") or ""
        if not title:
            return None

        content_id = f"youtube:{video_id or hashlib.md5(title.encode()).hexdigest()[:12]}"
        description = snippet.get("description") or ""

        published_at = None
        published = snippet.get("publishedAt")
        if published:
            try:
                published_at = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # 从标题和描述中匹配相关币种
        text_combined = f"{title} {description}".upper()
        matched_symbols = [s for s in symbols if s.upper() in text_combined]

        return ContentItem(
            content_id=content_id,
            content_type=ContentType.YOUTUBE_VIDEO,
            source=self.source_name,
            title=title,
            body=description[:500],
            url=f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
            author=snippet.get("channelTitle") or "",
            symbols=matched_symbols or symbols[:1],
            published_at=published_at,
            raw=video,
        )
