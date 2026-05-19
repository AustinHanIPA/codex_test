"""
存储持久化副作用。

将推荐管线的结果持久化到 SQLite（复用现有 Storage 模块）。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from logger import get_storage_logger
from pipeline.base import BaseSideEffect
from pipeline.models import ContentItem, PipelineContext
from storage import Storage, get_storage


class StorageEffect(BaseSideEffect):
    """将管线推荐结果持久化到本地数据库。"""

    effect_name = "storage_persist"

    def __init__(self, storage: Optional[Storage] = None):
        self._storage = storage
        self.logger = get_storage_logger()

    async def _get_storage(self) -> Storage:
        if self._storage is None:
            self._storage = await get_storage()
        return self._storage

    async def execute(
        self, items: List[ContentItem], context: PipelineContext
    ) -> None:
        """持久化推荐结果。"""
        if not items:
            return

        storage = await self._get_storage()

        # 1. 保存推荐条目到专用表（新表）
        await self._ensure_recommendations_table(storage)

        for item in items:
            await self._save_recommendation(storage, item, context)

        # 2. 如果有价格相关条目，也写入 price_history
        price_items = [it for it in items if it.price_change_percent is not None]
        if price_items:
            records = [
                (it.symbols[0] if it.symbols else "UNKNOWN", 0.0, it.price_change_percent, it.volume_24h)
                for it in price_items
            ]
            await storage.save_prices(records)

        self.logger.info(f"持久化 {len(items)} 条推荐结果")

    async def _ensure_recommendations_table(self, storage: Storage) -> None:
        """确保 recommendations 表存在。"""
        await storage.db.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id TEXT NOT NULL,
                content_type TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT,
                body TEXT,
                url TEXT,
                author TEXT,
                symbols TEXT,
                score_final REAL,
                score_hotness REAL,
                score_credibility REAL,
                score_impact REAL,
                score_relevance REAL,
                risk_tags TEXT,
                sentiment TEXT,
                query TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await storage.db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_recommendations_created_at
            ON recommendations(created_at)
            """
        )
        await storage.db.commit()

    async def _save_recommendation(
        self, storage: Storage, item: ContentItem, context: PipelineContext
    ) -> None:
        """保存单条推荐到数据库。"""
        await storage.db.execute(
            """
            INSERT INTO recommendations
            (content_id, content_type, source, title, body, url, author,
             symbols, score_final, score_hotness, score_credibility,
             score_impact, score_relevance, risk_tags, sentiment, query)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.content_id,
                item.content_type.value,
                item.source,
                item.title,
                item.body[:500] if item.body else None,
                item.url,
                item.author,
                json.dumps(item.symbols, ensure_ascii=False),
                item.score_final,
                item.score_hotness,
                item.score_credibility,
                item.score_impact,
                item.score_relevance,
                json.dumps(item.risk_tags, ensure_ascii=False),
                item.sentiment,
                context.query,
            ),
        )
        await storage.db.commit()
