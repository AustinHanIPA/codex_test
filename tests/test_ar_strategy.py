import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crypto_monitor"))

from ar_strategy import ARStrategyEngine
from config import ARStrategyConfig
from models import BinanceKline


def make_kline(index: int, close: float) -> BinanceKline:
    return BinanceKline(
        open_time=index * 60000,
        open=close,
        high=close * 1.02,
        low=close * 0.98,
        close=close,
        volume=1000,
        close_time=index * 60000 + 59999,
    )


class ARStrategyEngineTests(unittest.TestCase):
    def test_detects_bullish_step_in_signal(self):
        config = ARStrategyConfig(key_resistance=2.645, step_in_slices=3)
        closes = [1.0 + i * 0.04 for i in range(40)]
        closes[-2] = 2.60
        closes[-1] = 2.75
        klines = [make_kline(index, close) for index, close in enumerate(closes)]

        signal = ARStrategyEngine(config).evaluate("ARUSDT", klines)

        self.assertEqual(signal.symbol, "ARUSDT")
        self.assertEqual(signal.trend, "bullish")
        self.assertIn(signal.signal, {"WATCH_BUY", "BUY_STEP_IN"})
        self.assertEqual(signal.step_in_slices, 3)
        self.assertTrue(any("resistance" in reason for reason in signal.reasons))
        self.assertEqual(signal.layers["trend_following"]["status"], "active")

    def test_returns_insufficient_data(self):
        signal = ARStrategyEngine(ARStrategyConfig()).evaluate(
            "ARUSDT",
            [make_kline(index, 1.0) for index in range(5)],
        )

        self.assertEqual(signal.signal, "INSUFFICIENT_DATA")
        self.assertIn("need at least", signal.reasons[0])


if __name__ == "__main__":
    unittest.main()
