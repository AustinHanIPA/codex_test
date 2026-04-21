"""
市场数据模块
支持多交易所数据获取、重试机制、缓存优化
"""
import asyncio
import time
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import get_config
from logger import get_market_logger


class MarketDataFetcher:
    """
    市场数据获取器
    支持重试机制、请求限流、数据缓存
    """
    
    def __init__(self):
        """初始化市场数据获取器"""
        self.config = get_config().market
        self.logger = get_market_logger()
        
        # 创建带重试机制的session
        self.session = self._create_session()
        
        # 缓存
        self._cache: Dict[str, Any] = {}
        self._cache_time: float = 0
        self._cache_ttl: float = 1.0  # 缓存有效期（秒）
    
    def _create_session(self) -> requests.Session:
        """创建带重试机制的requests session"""
        session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.retry_delay,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def get_all_prices(self, use_cache: bool = True) -> Optional[Dict[str, float]]:
        """
        获取全市场交易对价格
        
        Args:
            use_cache: 是否使用缓存
        
        Returns:
            价格映射字典，格式: {"BTCUSDT": 60000.0, ...}
        """
        # 检查缓存
        if use_cache and self._cache and (time.time() - self._cache_time < self._cache_ttl):
            self.logger.debug("使用缓存的市场数据")
            return self._cache
        
        try:
            self.logger.debug(f"请求市场数据: {self.config.base_url}")
            
            response = self.session.get(
                self.config.base_url,
                timeout=self.config.timeout
            )
            
            if response.status_code != 200:
                self.logger.warning(f"市场数据请求失败: HTTP {response.status_code}")
                return self._cache if self._cache else None
            
            data = response.json()
            
            # 将列表转换为字典，实现O(1)查询
            price_map = {}
            for item in data:
                symbol = item.get('symbol', '')
                price_str = item.get('price', '0')
                try:
                    price_map[symbol] = float(price_str)
                except (ValueError, TypeError):
                    continue
            
            # 更新缓存
            self._cache = price_map
            self._cache_time = time.time()
            
            self.logger.debug(f"获取到 {len(price_map)} 个交易对价格")
            return price_map
            
        except requests.exceptions.Timeout:
            self.logger.error("市场数据请求超时")
            return self._cache if self._cache else None
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"市场数据请求异常: {e}")
            return self._cache if self._cache else None
            
        except Exception as e:
            self.logger.exception(f"市场数据处理异常: {e}")
            return self._cache if self._cache else None
    
    def get_price(self, symbol: str, use_cache: bool = True) -> Optional[float]:
        """
        获取单个交易对价格
        
        Args:
            symbol: 交易对名称（如 BTCUSDT）
            use_cache: 是否使用缓存
        
        Returns:
            价格，获取失败返回None
        """
        price_map = self.get_all_prices(use_cache=use_cache)
        if price_map:
            return price_map.get(symbol)
        return None
    
    def get_prices(
        self, 
        symbols: List[str], 
        use_cache: bool = True
    ) -> Dict[str, Optional[float]]:
        """
        批量获取多个交易对价格
        
        Args:
            symbols: 交易对名称列表
            use_cache: 是否使用缓存
        
        Returns:
            价格映射字典
        """
        price_map = self.get_all_prices(use_cache=use_cache)
        if not price_map:
            return {s: None for s in symbols}
        
        return {s: price_map.get(s) for s in symbols}
    
    def clear_cache(self):
        """清空缓存"""
        self._cache = {}
        self._cache_time = 0
        self.logger.debug("市场数据缓存已清空")
    
    def close(self):
        """关闭session"""
        self.session.close()
        self.logger.debug("市场数据session已关闭")


class MarketDataAsyncFetcher:
    """
    异步市场数据获取器
    基于aiohttp实现，适合高并发场景
    """
    
    def __init__(self):
        """初始化异步市场数据获取器"""
        self.config = get_config().market
        self.logger = get_market_logger()
        
        # 缓存
        self._cache: Dict[str, Any] = {}
        self._cache_time: float = 0
        self._cache_ttl: float = 1.0
    
    async def get_all_prices(self, use_cache: bool = True) -> Optional[Dict[str, float]]:
        """
        异步获取全市场交易对价格
        
        Args:
            use_cache: 是否使用缓存
        
        Returns:
            价格映射字典
        """
        # 检查缓存
        if use_cache and self._cache and (time.time() - self._cache_time < self._cache_ttl):
            return self._cache
        
        try:
            import aiohttp
            
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.config.base_url) as response:
                    if response.status != 200:
                        self.logger.warning(f"市场数据请求失败: HTTP {response.status}")
                        return self._cache if self._cache else None
                    
                    data = await response.json()
                    
                    # 转换为价格映射
                    price_map = {}
                    for item in data:
                        symbol = item.get('symbol', '')
                        price_str = item.get('price', '0')
                        try:
                            price_map[symbol] = float(price_str)
                        except (ValueError, TypeError):
                            continue
                    
                    # 更新缓存
                    self._cache = price_map
                    self._cache_time = time.time()
                    
                    return price_map
                    
        except asyncio.TimeoutError:
            self.logger.error("市场数据请求超时")
            return self._cache if self._cache else None
            
        except Exception as e:
            self.logger.error(f"市场数据请求异常: {e}")
            return self._cache if self._cache else None
    
    def clear_cache(self):
        """清空缓存"""
        self._cache = {}
        self._cache_time = 0


# 全局实例
_fetcher: Optional[MarketDataFetcher] = None


def get_fetcher() -> MarketDataFetcher:
    """获取全局市场数据获取器"""
    global _fetcher
    if _fetcher is None:
        _fetcher = MarketDataFetcher()
    return _fetcher


def close_fetcher():
    """关闭全局市场数据获取器"""
    global _fetcher
    if _fetcher:
        _fetcher.close()
        _fetcher = None
