"""
轻量量化分析引擎。

MVP 先用纯 Python 实现 RSI、Bollinger Bands、MACD 和成交额异动，
避免让运行环境强依赖 pandas；后续可以无缝替换为 pandas 向量化版本。
"""
from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional

from models import QuantSignal


class QuantEngine:
    """根据价格历史生成结构化交易信号。"""

    def evaluate(
        self,
        symbol: str,
        current_price: float,
        history: List[Dict[str, Any]],
        current_volume: Optional[float] = None,
    ) -> QuantSignal:
        chronological = list(reversed(history))
        prices = [self._to_float(item.get("price")) for item in chronological]
        prices = [item for item in prices if item is not None]
        prices.append(current_price)

        volumes = [self._to_float(item.get("volume_24h")) for item in chronological]
        volumes = [item for item in volumes if item is not None]

        signal = QuantSignal(symbol=symbol)
        signal.rsi = self._rsi(prices)
        signal.bollinger_position = self._bollinger_position(prices)
        signal.macd, signal.macd_signal = self._macd(prices)
        signal.volume_spike = self._volume_spike(volumes, current_volume)
        signal.score, signal.reasons = self._score(signal)
        signal.signal = self._classify(signal.score)
        return signal

    def _score(self, signal: QuantSignal) -> tuple[float, List[str]]:
        score = 0.0
        reasons: List[str] = []

        if signal.rsi is not None:
            if signal.rsi <= 30:
                score += 30
                reasons.append(f"RSI oversold: {signal.rsi:.2f}")
            elif signal.rsi >= 70:
                score -= 30
                reasons.append(f"RSI overbought: {signal.rsi:.2f}")

        if signal.bollinger_position is not None:
            if signal.bollinger_position <= 0:
                score += 20
                reasons.append("price near/below lower Bollinger band")
            elif signal.bollinger_position >= 1:
                score -= 20
                reasons.append("price near/above upper Bollinger band")

        if signal.macd is not None and signal.macd_signal is not None:
            if signal.macd > signal.macd_signal:
                score += 25
                reasons.append("MACD above signal line")
            elif signal.macd < signal.macd_signal:
                score -= 25
                reasons.append("MACD below signal line")

        if signal.volume_spike is not None and signal.volume_spike >= 3:
            direction = self._volume_direction(signal, score)
            score += 20 * direction
            reasons.append(f"volume spike {signal.volume_spike:.2f}x")

        return max(-100.0, min(100.0, score)), reasons

    @staticmethod
    def _volume_direction(signal: QuantSignal, score: float) -> int:
        if signal.macd is not None and signal.macd_signal is not None:
            return 1 if signal.macd >= signal.macd_signal else -1
        return 1 if score >= 0 else -1

    @staticmethod
    def _classify(score: float) -> str:
        if score >= 70:
            return "STRONG_BUY"
        if score >= 35:
            return "BUY"
        if score <= -70:
            return "STRONG_SELL"
        if score <= -35:
            return "SELL"
        return "NEUTRAL"

    @staticmethod
    def _rsi(prices: List[float], period: int = 14) -> Optional[float]:
        if len(prices) <= period:
            return None

        deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        recent = deltas[-period:]
        gains = [delta for delta in recent if delta > 0]
        losses = [-delta for delta in recent if delta < 0]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _bollinger_position(prices: List[float], period: int = 20) -> Optional[float]:
        if len(prices) < period:
            return None
        window = prices[-period:]
        avg = mean(window)
        stdev = pstdev(window)
        if stdev == 0:
            return 0.5
        lower = avg - 2 * stdev
        upper = avg + 2 * stdev
        return (prices[-1] - lower) / (upper - lower)

    def _macd(self, prices: List[float]) -> tuple[Optional[float], Optional[float]]:
        if len(prices) < 35:
            return None, None
        ema12 = self._ema(prices, 12)
        ema26 = self._ema(prices, 26)
        macd_line = [fast - slow for fast, slow in zip(ema12[-len(ema26):], ema26)]
        if len(macd_line) < 9:
            return None, None
        signal_line = self._ema(macd_line, 9)
        return macd_line[-1], signal_line[-1]

    @staticmethod
    def _ema(values: List[float], period: int) -> List[float]:
        if len(values) < period:
            return []
        multiplier = 2 / (period + 1)
        ema_values = [mean(values[:period])]
        for value in values[period:]:
            ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])
        return ema_values

    @staticmethod
    def _volume_spike(volumes: List[float], current_volume: Optional[float], period: int = 20) -> Optional[float]:
        if current_volume is None or len(volumes) < period:
            return None
        baseline = mean(volumes[-period:])
        if baseline <= 0 or math.isclose(baseline, 0):
            return None
        return current_volume / baseline

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
