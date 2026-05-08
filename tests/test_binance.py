import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crypto_monitor"))

from binance import BinanceKlineFetcher


class BinanceKlineFetcherTests(unittest.TestCase):
    def test_parse_kline_payload(self):
        kline = BinanceKlineFetcher.parse_kline([
            1700000000000,
            "1.0",
            "1.5",
            "0.9",
            "1.2",
            "100",
            1700003599999,
            "120",
            42,
            "60",
            "72",
            "0",
        ])

        self.assertEqual(kline.open_time, 1700000000000)
        self.assertEqual(kline.close_time, 1700003599999)
        self.assertEqual(kline.close, 1.2)
        self.assertEqual(kline.trades, 42)

    def test_base_url_path_supports_nginx_prefix(self):
        self.assertEqual(
            BinanceKlineFetcher._klines_url("http://proxy/binance"),
            "http://proxy/binance/api/v3/klines",
        )
        self.assertEqual(
            BinanceKlineFetcher._klines_url("http://proxy/binance/api/v3"),
            "http://proxy/binance/api/v3/klines",
        )

    def test_rotates_base_urls(self):
        fetcher = BinanceKlineFetcher(base_urls=["http://a", "http://b"])

        self.assertEqual(fetcher._next_base_url(), "http://a")
        self.assertEqual(fetcher._next_base_url(), "http://b")
        self.assertEqual(fetcher._next_base_url(), "http://a")


if __name__ == "__main__":
    unittest.main()
