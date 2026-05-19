"""
Query Hydration 查询扩展。

管线的第一步：将用户请求（或空请求）扩展为完整的 PipelineContext，
包含用户画像、关注币种列表和相关参数。

职责：
1. 加载用户画像
2. 扩展 query -> topic_symbols（如 "BTC 新闻" -> symbols=["BTC"]）
3. 根据配置生成初始上下文
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from config import get_config
from logger import get_monitor_logger
from pipeline.models import (
    ContentType,
    PipelineContext,
    RiskLevel,
    UserProfile,
)
from storage import Storage, get_storage


class QueryHydrator:
    """
    查询扩展器。

    将原始请求（query / 无请求的定时触发）扩展为完整的 PipelineContext。
    """

    def __init__(self, storage: Optional[Storage] = None):
        self._storage = storage
        self.logger = get_monitor_logger()

    async def _get_storage(self) -> Storage:
        if self._storage is None:
            self._storage = await get_storage()
        return self._storage

    async def hydrate(
        self,
        query: str = "",
        user_id: str = "default",
        overrides: Optional[Dict] = None,
    ) -> PipelineContext:
        """
        将请求扩展为管线上下文。

        Args:
            query: 用户查询（如 "BTC 利好消息"），定时任务时为空字符串
            user_id: 用户ID，用于加载画像
            overrides: 覆盖默认配置的参数字典
        """
        # 1. 加载用户画像
        profile = await self._load_user_profile(user_id)

        # 2. 解析 query 中的 symbols
        query_symbols = self._extract_symbols_from_query(query)

        # 3. 合并关注列表：查询中的 + 画像中的
        topic_symbols = list(set(query_symbols + profile.watch_symbols))

        # 4. 构建上下文
        config = get_config()
        pipeline_cfg = config.config.get("pipeline", {}) if hasattr(config, 'config') else {}

        context = PipelineContext(
            query=query,
            topic_symbols=topic_symbols,
            user_profile=profile,
            max_items=pipeline_cfg.get("max_items", 20),
            diversity_ratio=pipeline_cfg.get("diversity_ratio", 0.3),
        )

        # 5. 应用 overrides
        if overrides:
            if "max_items" in overrides:
                context.max_items = overrides["max_items"]
            if "diversity_ratio" in overrides:
                context.diversity_ratio = overrides["diversity_ratio"]
            if "extra_symbols" in overrides:
                context.topic_symbols = list(
                    set(context.topic_symbols + overrides["extra_symbols"])
                )

        self.logger.info(
            f"Query Hydration 完成: query='{query}', "
            f"symbols={context.topic_symbols[:5]}, "
            f"max_items={context.max_items}"
        )

        return context

    async def _load_user_profile(self, user_id: str) -> UserProfile:
        """从配置和数据库加载用户画像。"""
        config = get_config()

        # 从 config.yaml 获取 watch_symbols
        watch_symbols = [s.upper() for s in config.symbols]

        # 从数据库 watchlist 补充
        try:
            storage = await self._get_storage()
            db_symbols = await storage.get_watch_list()
            watch_symbols = list(set(watch_symbols + db_symbols))
        except Exception as exc:
            self.logger.warning(f"加载 watchlist 失败: {exc}")

        # 风险偏好从配置读取
        risk_pref_str = getattr(config, "risk_preference", "moderate")
        try:
            risk_pref = RiskLevel(risk_pref_str)
        except ValueError:
            risk_pref = RiskLevel.MODERATE

        return UserProfile(
            user_id=user_id,
            watch_symbols=watch_symbols,
            risk_preference=risk_pref,
            preferred_content_types=[],  # 默认关注所有类型
            blocked_symbols=[],
            blocked_sources=[],
        )

    @staticmethod
    def _extract_symbols_from_query(query: str) -> List[str]:
        """从查询文本中提取币种符号。"""
        if not query:
            return []

        # 匹配常见币种写法：$BTC, BTC, btc
        # 支持主流币种关键词
        known_symbols = {
            "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "DOT",
            "AVAX", "LINK", "MATIC", "UNI", "AAVE", "ATOM", "NEAR",
            "FTM", "OP", "ARB", "APT", "SUI", "SEI", "TIA", "JUP",
            "WIF", "PEPE", "BONK", "SHIB", "FLOKI", "WLD", "INJ",
            "FET", "RNDR", "AR", "FIL", "MINA",
        }

        symbols: List[str] = []

        # 匹配 $SYMBOL 格式
        dollar_matches = re.findall(r"\$([A-Za-z]{2,10})", query)
        for m in dollar_matches:
            symbols.append(m.upper())

        # 匹配已知币种（大小写不敏感）
        query_upper = query.upper()
        for symbol in known_symbols:
            if symbol in query_upper:
                # 确保是独立词（非子串）
                pattern = rf"\b{re.escape(symbol)}\b"
                if re.search(pattern, query_upper):
                    symbols.append(symbol)

        return list(set(symbols))
