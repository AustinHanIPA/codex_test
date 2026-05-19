"""
项目方背景 Hydrator。

为内容项补充关联项目的背景信息（团队、融资、生态等）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pipeline.base import BaseHydrator
from pipeline.models import ContentItem, PipelineContext


# 静态项目信息库（后续可替换为 API 或数据库）
PROJECT_DATABASE: Dict[str, Dict[str, Any]] = {
    "BTC": {
        "name": "Bitcoin",
        "category": "Layer 1",
        "launched": "2009",
        "consensus": "PoW",
        "max_supply": "21M",
        "background": "去中心化数字黄金，全球市值最大的加密货币",
    },
    "ETH": {
        "name": "Ethereum",
        "category": "Layer 1 / Smart Contract",
        "launched": "2015",
        "consensus": "PoS",
        "background": "智能合约平台，DeFi 与 NFT 生态基石",
    },
    "SOL": {
        "name": "Solana",
        "category": "Layer 1",
        "launched": "2020",
        "consensus": "PoH + PoS",
        "background": "高性能公链，主打高 TPS 低费用",
    },
    "WIF": {
        "name": "dogwifhat",
        "category": "Meme",
        "launched": "2023",
        "chain": "Solana",
        "background": "Solana 生态 Meme 币",
    },
    "PEPE": {
        "name": "Pepe",
        "category": "Meme",
        "launched": "2023",
        "chain": "Ethereum",
        "background": "以 Pepe 青蛙为主题的 Meme 币",
    },
    "AR": {
        "name": "Arweave",
        "category": "Storage / DePIN",
        "launched": "2018",
        "consensus": "SPoRA",
        "background": "永久存储协议，一次付费永久存储数据",
    },
    "BOME": {
        "name": "BOOK OF MEME",
        "category": "Meme",
        "launched": "2024",
        "chain": "Solana",
        "background": "Solana 生态 Meme 币，基于 Arweave 永久存储",
    },
}


class ProjectHydrator(BaseHydrator):
    """补充项目方背景信息。"""

    hydrator_name = "project_background"

    def __init__(self, project_db: Optional[Dict[str, Dict[str, Any]]] = None):
        self._project_db = project_db or PROJECT_DATABASE

    async def hydrate(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """为内容项补充项目背景信息。"""
        for item in items:
            if item.filtered:
                continue
            if item.project_background:
                continue  # 已经有了

            for symbol in item.symbols:
                project_info = self._project_db.get(symbol.upper())
                if project_info:
                    item.project_background = project_info.get("background", "")
                    item.metadata["project_category"] = project_info.get("category", "")
                    item.metadata["project_chain"] = project_info.get("chain", "")
                    break

        return items
