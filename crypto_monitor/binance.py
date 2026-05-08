"""
Binance REST Kline 数据接入。

该模块为 AR/AO 策略提供历史 K 线分页拉取能力，并通过 `base_urls`
预留 Nginx/多 VM 代理池入口。默认只依赖 `aiohttp`，方便在当前轻量服务里运行。
"""
from __future__ import annotations

import asyncio
from typing import Any, Iterable, List, Optional
from urllib.parse import urljoin

import aiohttp

from config import get_config
from logger import get_monitor_logger
from models import BinanceKline


class BinanceKlineFetcher:
    """异步 Binance Kline 拉取器，支持分页和 base_url 轮询。"""

    def __init__(
        self,
        base_urls: Optional[Iterable[str]] = None,
        timeout: int = 10,
        max_retries: int = 3,
        retry_delay: int = 1,
        page_limit: int = 1000,
    ):
        self.base_urls = [item.rstrip("/") for item in (base_urls or []) if item]
        if not self.base_urls:
            self.base_urls = ["https://api.binance.com"]
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.retry_delay = max(0, retry_delay)
        self.page_limit = min(max(1, page_limit), 1000)
        self.logger = get_monitor_logger()
        self._session: Optional[aiohttp.ClientSession] = None
        self._base_url_index = 0

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    def _next_base_url(self) -> str:
        base_url = self.base_urls[self._base_url_index % len(self.base_urls)]
        self._base_url_index += 1
        return base_url

    @staticmethod
    def _klines_url(base_url: str) -> str:
        base = base_url.rstrip("/")
        if base.endswith("/api/v3"):
            return urljoin(f"{base}/", "klines")
        return urljoin(f"{base}/", "api/v3/klines")

    async def fetch_klines_page(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[BinanceKline]:
        """拉取单页 K 线。"""
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit or self.page_limit, 1000),
        }
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            base_url = self._next_base_url()
            url = self._klines_url(base_url)
            try:
                session = await self._ensure_session()
                async with session.get(url, params=params) as response:
                    response.raise_for_status()
                    payload = await response.json()
                    return [self.parse_kline(item) for item in payload]
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError) as exc:
                last_error = exc
                self.logger.warning(
                    "Binance Kline 拉取失败 attempt=%s/%s base_url=%s symbol=%s interval=%s error=%s",
                    attempt,
                    self.max_retries,
                    base_url,
                    symbol,
                    interval,
                    exc,
                )
                if attempt < self.max_retries and self.retry_delay:
                    await asyncio.sleep(self.retry_delay)

        raise RuntimeError(f"Binance Kline 拉取失败: {last_error}")

    async def fetch_all_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> List[BinanceKline]:
        """分页拉取全部历史 K 线。"""
        page_limit = min(limit or self.page_limit, 1000)
        next_start = start_time
        all_klines: List[BinanceKline] = []
        pages = 0

        while True:
            page = await self.fetch_klines_page(
                symbol=symbol,
                interval=interval,
                start_time=next_start,
                end_time=end_time,
                limit=page_limit,
            )
            if not page:
                break

            pages += 1
            all_klines.extend(page)
            if len(page) < page_limit:
                break
            if max_pages is not None and pages >= max_pages:
                break

            candidate_start = page[-1].close_time + 1
            if next_start is not None and candidate_start <= next_start:
                break
            if end_time is not None and candidate_start >= end_time:
                break
            next_start = candidate_start

        return all_klines

    @staticmethod
    def parse_kline(item: list[Any]) -> BinanceKline:
        """把 Binance 原始数组转成领域模型。"""
        if len(item) < 6:
            raise ValueError("invalid Binance kline payload")
        return BinanceKline(
            open_time=int(item[0]),
            open=float(item[1]),
            high=float(item[2]),
            low=float(item[3]),
            close=float(item[4]),
            volume=float(item[5]),
            close_time=int(item[6]) if len(item) > 6 else int(item[0]),
            quote_volume=float(item[7]) if len(item) > 7 else 0.0,
            trades=int(item[8]) if len(item) > 8 else 0,
            taker_buy_base_volume=float(item[9]) if len(item) > 9 else 0.0,
            taker_buy_quote_volume=float(item[10]) if len(item) > 10 else 0.0,
            raw=list(item),
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


_binance_fetcher: Optional[BinanceKlineFetcher] = None


def get_binance_fetcher() -> BinanceKlineFetcher:
    global _binance_fetcher
    if _binance_fetcher is None:
        config = get_config()
        _binance_fetcher = BinanceKlineFetcher(
            base_urls=config.binance.base_urls,
            timeout=config.binance.timeout,
            max_retries=config.binance.max_retries,
            retry_delay=config.binance.retry_delay,
            page_limit=config.binance.page_limit,
        )
    return _binance_fetcher


async def close_binance_fetcher() -> None:
    global _binance_fetcher
    if _binance_fetcher:
        await _binance_fetcher.close()
        _binance_fetcher = None
