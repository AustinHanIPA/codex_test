"""
新闻聚合数据源。

从加密货币新闻聚合 API 拉取实时新闻。
支持 CryptoPanic, CoinDesk RSS 等接口。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from pipeline.base import BaseSource
from pipeline.models import ContentItem, ContentType, PipelineContext


class NewsSource(BaseSource):
    """加密货币新闻聚合数据源。"""

    source_name = "news"

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        timeout: int = 10,
        max_results: int = 50,
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.timeout = timeout
        self.max_results = max_results

    async def fetch(self, context: PipelineContext) -> List[ContentItem]:
        """从新闻聚合 API 拉取新闻。"""
        if not self.api_url:
            return []

        symbols = context.topic_symbols or context.user_profile.watch_symbols
        items: List[ContentItem] = []

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as session:
                articles = await self._fetch_news(session, symbols)
                for article in articles:
                    item = self._normalize_article(article, symbols)
                    if item:
                        items.append(item)
        except Exception:
            pass

        return items[:self.max_results]

    async def _fetch_news(
        self, session: aiohttp.ClientSession, symbols: List[str]
    ) -> List[Dict[str, Any]]:
        """拉取新闻列表。"""
        params: Dict[str, Any] = {"filter": "hot", "public": "true"}
        if self.api_key:
            params["auth_token"] = self.api_key
        if symbols:
            params["currencies"] = ",".join(symbols[:10])

        try:
            async with session.get(self.api_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("results") or data.get("articles") or data.get("data") or []
        except Exception:
            pass
        return []

    def _normalize_article(
        self, article: Dict[str, Any], symbols: List[str]
    ) -> Optional[ContentItem]:
        """将新闻文章归一化为 ContentItem。"""
        title = article.get("title") or ""
        if not title:
            return None

        article_id = str(article.get("id") or article.get("slug") or "")
        content_id = f"news:{article_id or hashlib.md5(title.encode()).hexdigest()[:12]}"

        body = article.get("body") or article.get("description") or article.get("summary") or ""
        url = article.get("url") or article.get("link") or ""
        source_name = ""
        source_info = article.get("source")
        if isinstance(source_info, dict):
            source_name = source_info.get("title") or source_info.get("name") or ""
        elif isinstance(source_info, str):
            source_name = source_info

        published_at = None
        published = article.get("published_at") or article.get("publishedAt") or article.get("created_at")
        if published:
            try:
                published_at = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # 匹配相关币种
        currencies = article.get("currencies") or []
        matched_symbols = []
        if currencies:
            for curr in currencies:
                if isinstance(curr, dict):
                    code = curr.get("code") or curr.get("symbol")
                    if code:
                        matched_symbols.append(str(code).upper())
                elif isinstance(curr, str):
                    matched_symbols.append(curr.upper())
        if not matched_symbols:
            text_combined = f"{title} {body}".upper()
            matched_symbols = [s for s in symbols if s.upper() in text_combined]

        return ContentItem(
            content_id=content_id,
            content_type=ContentType.NEWS,
            source=self.source_name,
            title=title,
            body=body[:500],
            url=url,
            author=source_name,
            symbols=matched_symbols,
            published_at=published_at,
            raw=article,
            metadata={
                "votes": article.get("votes") or {},
                "kind": article.get("kind") or "news",
            },
        )
