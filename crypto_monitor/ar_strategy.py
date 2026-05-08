"""
AR/AO 五维自适应策略引擎。

当前版本聚焦“监控与信号”而不是自动下单：趋势层、均值回归层和执行建议
已经可计算；叙事、资金费率和做市层先以结构化占位输出，后续接入 AO/GitHub/
社媒与合约资金费率数据源即可收敛成完整闭环。
"""
from __future__ import annotations

from statistics import mean, pstdev
from typing import List, Optional

from config import ARStrategyConfig, get_config
from models import ARStrategySignal, BinanceKline


class ARStrategyEngine:
    """根据 Binance Kline 生成 AR/AO 专用策略信号。"""

    def __init__(self, config: Optional[ARStrategyConfig] = None):
        self.config = config or get_config().ar_strategy

    def evaluate(self, symbol: str, klines: List[BinanceKline], timeframe: str = "1w") -> ARStrategySignal:
        chronological = sorted(klines, key=lambda item: item.open_time)
        closes = [item.close for item in chronological]
        signal = ARStrategySignal(
            symbol=symbol.upper(),
            timeframe=timeframe,
            key_resistance=self.config.key_resistance,
            step_in_slices=self.config.step_in_slices,
            layers=self._base_layers(),
        )

        min_required = max(self.config.ma_slow, self.config.macd_slow + self.config.macd_signal)
        if len(closes) < min_required:
            signal.signal = "INSUFFICIENT_DATA"
            signal.reasons.append(f"need at least {min_required} klines, got {len(closes)}")
            return signal

        signal.close = closes[-1]
        signal.ma_fast = self._sma(closes, self.config.ma_fast)
        signal.ma_slow = self._sma(closes, self.config.ma_slow)
        signal.macd, signal.macd_signal = self._macd(
            closes,
            fast_period=self.config.macd_fast,
            slow_period=self.config.macd_slow,
            signal_period=self.config.macd_signal,
        )
        signal.rsi = self._rsi(closes, self.config.rsi_period)
        signal.bollinger_width = self._bollinger_width(
            closes,
            period=self.config.bollinger_period,
            stddev_multiplier=self.config.bollinger_stddev,
        )

        previous_fast = self._sma(closes[:-1], self.config.ma_fast)
        previous_slow = self._sma(closes[:-1], self.config.ma_slow)
        previous_macd, previous_macd_signal = self._macd(
            closes[:-1],
            fast_period=self.config.macd_fast,
            slow_period=self.config.macd_slow,
            signal_period=self.config.macd_signal,
        )

        score = 0.0
        reasons: List[str] = []
        bullish_trend = signal.ma_fast is not None and signal.ma_slow is not None and signal.ma_fast > signal.ma_slow
        bearish_trend = signal.ma_fast is not None and signal.ma_slow is not None and signal.ma_fast < signal.ma_slow

        if bullish_trend:
            score += 35
            signal.trend = "bullish"
            reasons.append(f"MA{self.config.ma_fast} above MA{self.config.ma_slow}")
        elif bearish_trend:
            score -= 35
            signal.trend = "bearish"
            reasons.append(f"MA{self.config.ma_fast} below MA{self.config.ma_slow}")
        else:
            signal.trend = "range"

        if (
            bullish_trend
            and previous_fast is not None
            and previous_slow is not None
            and previous_fast <= previous_slow
        ):
            score += 25
            reasons.append(f"MA{self.config.ma_fast}/MA{self.config.ma_slow} golden cross")

        if signal.macd is not None and signal.macd_signal is not None:
            if signal.macd > signal.macd_signal:
                score += 20
                reasons.append("MACD above signal line")
            elif signal.macd < signal.macd_signal:
                score -= 20
                reasons.append("MACD below signal line")

            if (
                previous_macd is not None
                and previous_macd_signal is not None
                and previous_macd <= previous_macd_signal
                and signal.macd > signal.macd_signal
            ):
                score += 20
                if signal.macd < 0:
                    score += 10
                    reasons.append("MACD low-zone golden cross")
                else:
                    reasons.append("MACD golden cross")

        if signal.close is not None and signal.close >= self.config.key_resistance:
            score += 15
            reasons.append(f"close above key resistance {self.config.key_resistance}")
            if len(closes) >= 2 and closes[-2] < self.config.key_resistance:
                score += 15
                reasons.append("fresh resistance breakout")

        if bullish_trend and signal.rsi is not None and signal.rsi < 30:
            score += 15
            reasons.append("bullish trend pullback with RSI oversold")
        elif signal.rsi is not None and signal.rsi > 75:
            score -= 10
            reasons.append("RSI overheated")

        signal.score = max(-100.0, min(100.0, score))
        signal.signal = self._classify(signal.score)
        signal.reasons = reasons or ["no strong AR strategy edge detected"]
        signal.layers = self._layers(signal)
        return signal

    def _base_layers(self) -> dict[str, dict[str, object]]:
        return {
            "narrative_filter": {
                "status": "pending_data_source",
                "inputs": ["AO storage growth", "GitHub activity", "social weight"],
            },
            "trend_following": {"status": "pending"},
            "mean_reversion": {"status": "pending"},
            "hedging_arb": {
                "status": "pending_data_source",
                "funding_rate_threshold": self.config.funding_rate_threshold,
            },
            "market_making": {"status": "pending_orderbook_data"},
        }

    def _layers(self, signal: ARStrategySignal) -> dict[str, dict[str, object]]:
        layers = self._base_layers()
        layers["trend_following"] = {
            "status": "active",
            "trend": signal.trend,
            "ma_fast": signal.ma_fast,
            "ma_slow": signal.ma_slow,
            "macd": signal.macd,
            "macd_signal": signal.macd_signal,
            "breakout": bool(signal.close is not None and signal.close >= self.config.key_resistance),
        }
        layers["mean_reversion"] = {
            "status": "active",
            "rsi": signal.rsi,
            "bollinger_width": signal.bollinger_width,
            "pullback_buy_zone": bool(signal.trend == "bullish" and signal.rsi is not None and signal.rsi < 30),
        }
        layers["hedging_arb"] = {
            "status": "pending_data_source",
            "funding_rate_threshold": self.config.funding_rate_threshold,
            "action": "spot_long_perp_short_when_funding_rate_gt_threshold",
        }
        layers["market_making"] = {
            "status": "pending_orderbook_data",
            "action": "enable_micro_grid_only_in_range_market",
        }
        return layers

    @staticmethod
    def _classify(score: float) -> str:
        if score >= 70:
            return "BUY_STEP_IN"
        if score >= 45:
            return "WATCH_BUY"
        if score <= -45:
            return "RISK_OFF"
        return "NEUTRAL"

    @staticmethod
    def _sma(values: List[float], period: int) -> Optional[float]:
        if len(values) < period:
            return None
        return mean(values[-period:])

    @staticmethod
    def _ema(values: List[float], period: int) -> List[float]:
        if len(values) < period:
            return []
        multiplier = 2 / (period + 1)
        ema_values = [mean(values[:period])]
        for value in values[period:]:
            ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])
        return ema_values

    def _macd(
        self,
        values: List[float],
        fast_period: int,
        slow_period: int,
        signal_period: int,
    ) -> tuple[Optional[float], Optional[float]]:
        if len(values) < slow_period + signal_period:
            return None, None
        fast_ema = self._ema(values, fast_period)
        slow_ema = self._ema(values, slow_period)
        macd_line = [fast - slow for fast, slow in zip(fast_ema[-len(slow_ema):], slow_ema)]
        signal_line = self._ema(macd_line, signal_period)
        if not signal_line:
            return None, None
        return macd_line[-1], signal_line[-1]

    @staticmethod
    def _rsi(values: List[float], period: int) -> Optional[float]:
        if len(values) <= period:
            return None
        deltas = [values[index] - values[index - 1] for index in range(1, len(values))]
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
    def _bollinger_width(values: List[float], period: int, stddev_multiplier: float) -> Optional[float]:
        if len(values) < period:
            return None
        window = values[-period:]
        avg = mean(window)
        if avg == 0:
            return None
        stdev = pstdev(window)
        upper = avg + stddev_multiplier * stdev
        lower = avg - stddev_multiplier * stdev
        return (upper - lower) / avg
