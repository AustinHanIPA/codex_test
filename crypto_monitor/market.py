"""
市场数据模块。

基于 aiohttp 维护长连接池，统一返回结构化市场快照。
"""
from __future__ import annotations

import asyncio
import aiohttp
from typing import Dict, Optional

from config import get_config
from logger import get_market_logger
from models import MarketSnapshot


class MarketDataFetcher:
    """异步市场数据抓取器。"""

    def __init__(self):
        self.config = get_config().market
        self.logger = get_market_logger()
        self._session: Optional[aiohttp.ClientSession] = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    def _normalize_snapshot(self, item: dict) -> Optional[MarketSnapshot]:
        pair = item.get("symbol") or item.get("pair") or ""
        if not pair:
            return None

        price_value = item.get("price") or item.get("lastPrice") or item.get("last_price")
        try:
            price = float(price_value)
        except (TypeError, ValueError):
            return None

        symbol = pair[:-4] if pair.endswith("USDT") else pair

        def _to_float(key: str) -> Optional[float]:
            value = item.get(key)
            if value in (None, ""):
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        return MarketSnapshot(
            pair=pair,
            symbol=symbol,
            price=price,
            price_change_percent_24h=_to_float("priceChangePercent"),
            volume_24h=_to_float("quoteVolume") or _to_float("volume"),
            market_cap=_to_float("marketCap"),
            raw=item,
        )

    async def get_all_snapshots(self) -> Dict[str, MarketSnapshot]:
        """获取全部交易对快照。"""
        session = self._ensure_session()
        url = self.config.base_url
        attempts = max(1, self.config.max_retries)

        payload = None
        for attempt in range(1, attempts + 1):
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        payload = await response.json()
                        break

                    self.logger.error(
                        f"市场数据请求失败: HTTP {response.status} (attempt {attempt}/{attempts})"
                    )
            except Exception as exc:
                self.logger.error(f"获取市场数据异常: {exc} (attempt {attempt}/{attempts})")

            if attempt < attempts:
                await asyncio.sleep(self.config.retry_delay)

        if payload is None:
            return {}

        if isinstance(payload, dict):
            items = payload.get("data") or payload.get("symbols") or []
            if not isinstance(items, list):
                items = [payload]
        elif isinstance(payload, list):
            items = payload
        else:
            self.logger.error(f"市场数据格式异常: {type(payload)!r}")
            return {}

        snapshots: Dict[str, MarketSnapshot] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            snapshot = self._normalize_snapshot(item)
            if snapshot is not None:
                snapshots[snapshot.pair] = snapshot

        return snapshots

    async def get_all_prices(self) -> Dict[str, float]:
        """兼容旧接口，仅返回价格映射。"""
        snapshots = await self.get_all_snapshots()
        return {pair: snapshot.price for pair, snapshot in snapshots.items()}

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self.logger.info("市场数据会话已关闭")

    async def clear_cache(self) -> None:
        """通过重建会话实现轻量自恢复。"""
        await self.close()
        self._session = None


_fetcher: Optional[MarketDataFetcher] = None


def get_fetcher() -> MarketDataFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = MarketDataFetcher()
    return _fetcher


async def close_fetcher() -> None:
    global _fetcher
    if _fetcher:
        await _fetcher.close()
        _fetcher = None
