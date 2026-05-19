"""
去重过滤器。

基于 content_id 和内容相似度去重，避免用户看到重复信息。
同时考虑用户已经看过的内容（seen_content_ids）。
"""
from __future__ import annotations

import hashlib
from typing import List, Set

from pipeline.base import BaseFilter
from pipeline.models import ContentItem, PipelineContext


class DuplicateFilter(BaseFilter):
    """去重过滤器。"""

    filter_name = "duplicate"

    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold

    async def apply(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """去除重复内容项。"""
        seen_ids: Set[str] = set(context.user_profile.seen_content_ids)
        seen_hashes: Set[str] = set()
        result: List[ContentItem] = []
        duplicates = 0

        for item in items:
            # 1. 检查 content_id 重复
            if item.content_id in seen_ids:
                item.is_duplicate = True
                item.filtered = True
                item.filter_reason = "duplicate: already seen"
                duplicates += 1
                continue

            # 2. 检查内容哈希重复（标题相似度）
            content_hash = self._compute_hash(item)
            if content_hash in seen_hashes:
                item.is_duplicate = True
                item.filtered = True
                item.filter_reason = "duplicate: similar content"
                duplicates += 1
                continue

            seen_ids.add(item.content_id)
            seen_hashes.add(content_hash)
            result.append(item)

        context.filter_stats["duplicate_removed"] = duplicates
        return result

    @staticmethod
    def _compute_hash(item: ContentItem) -> str:
        """计算内容的近似哈希（基于归一化标题）。"""
        # 简单的归一化：小写 + 去除特殊字符 + 取前 50 字符
        normalized = item.title.lower().strip()
        # 去除常见前缀符号
        for prefix in ["🚨", "📈", "📉", "🐳", "🆕", "🔥", "💀"]:
            normalized = normalized.replace(prefix, "")
        normalized = normalized.strip()[:50]
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()
