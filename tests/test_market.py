import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crypto_monitor"))

from market import MarketDataFetcher


class MarketDataFetcherTests(unittest.TestCase):
    def test_normalize_snapshot(self):
        fetcher = MarketDataFetcher()
        snapshot = fetcher._normalize_snapshot(
            {
                "symbol": "BTCUSDT",
                "price": "65000.12",
                "priceChangePercent": "3.1",
                "quoteVolume": "9999999.5",
            }
        )

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.symbol, "BTC")
        self.assertEqual(snapshot.pair, "BTCUSDT")
        self.assertAlmostEqual(snapshot.price, 65000.12)
        self.assertAlmostEqual(snapshot.price_change_percent_24h, 3.1)
        self.assertAlmostEqual(snapshot.volume_24h, 9999999.5)


if __name__ == "__main__":
    unittest.main()
