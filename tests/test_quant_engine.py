import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crypto_monitor"))

from quant_engine import QuantEngine


class QuantEngineTests(unittest.TestCase):
    def test_generates_quant_signal(self):
        history = [
            {"price": 100 + i, "volume_24h": 1000 + i}
            for i in range(40)
        ]
        signal = QuantEngine().evaluate("BTC", 150.0, list(reversed(history)), current_volume=5000)

        self.assertEqual(signal.symbol, "BTC")
        self.assertIn(signal.signal, {"BUY", "STRONG_BUY", "NEUTRAL"})
        self.assertIsNotNone(signal.rsi)
        self.assertIsNotNone(signal.macd)
        self.assertGreaterEqual(signal.volume_spike or 0, 3)


if __name__ == "__main__":
    unittest.main()
