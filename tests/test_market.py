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

    def test_normalize_dex_pair(self):
        fetcher = MarketDataFetcher()
        snapshot = fetcher._normalize_dex_pair(
            {
                "baseToken": {"symbol": "SOL"},
                "quoteToken": {"symbol": "USDC"},
                "priceUsd": "150.5",
                "volume": {"h24": 123456.7},
                "priceChange": {"h24": "4.5"},
                "liquidity": {"usd": 98765.4},
                "marketCap": 123000000,
            }
        )

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.pair, "SOLUSDT")
        self.assertEqual(snapshot.provider, "dexscreener")
        self.assertAlmostEqual(snapshot.price, 150.5)
        self.assertAlmostEqual(snapshot.liquidity_usd, 98765.4)
        self.assertAlmostEqual(snapshot.market_cap, 123000000)


if __name__ == "__main__":
    unittest.main()
