"""
核心领域模型。

这些数据结构把市场抓取、AI 洞察和监控状态从实现细节里抽离出来，
让监控链路像 api-doc-inspect 一样围绕结构化产物流转。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class MarketSnapshot:
    """单个交易对的市场快照。"""

    pair: str
    symbol: str
    price: float
    price_change_percent_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AIInsight:
    """AI 输出的结构化短评。"""

    comment: str
    sentiment: str = "neutral"
    risk_hint: str = ""
    raw_text: str = ""


@dataclass
class PriceState:
    """运行时价格状态，用于冷却和趋势判断。"""

    symbol: str
    last_price: Optional[float] = None
    last_alert_time: Optional[datetime] = None
    recent_changes: List[float] = field(default_factory=list)

    def update_price(self, price: float) -> float:
        """更新价格并返回相较上次采样的波动百分比。"""
        if self.last_price in (None, 0):
            self.last_price = price
            self.recent_changes = [0.0]
            return 0.0

        change = ((price - self.last_price) / self.last_price) * 100
        self.last_price = price
        self.recent_changes.append(change)
        self.recent_changes = self.recent_changes[-5:]
        return change

    def can_alert(self, cooldown: int) -> bool:
        """判断是否已经过了冷却期。"""
        if self.last_alert_time is None:
            return True
        elapsed = (datetime.now() - self.last_alert_time).total_seconds()
        return elapsed >= cooldown

    def mark_alerted(self) -> None:
        """记录最近一次报警时间。"""
        self.last_alert_time = datetime.now()

    def get_trend(self) -> str:
        """给出最近趋势方向。"""
        if not self.recent_changes:
            return "flat"

        latest = self.recent_changes[-1]
        if latest > 0:
            return "up"
        if latest < 0:
            return "down"
        return "flat"
