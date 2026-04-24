import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crypto_monitor"))

from config import get_config
from storage import Storage
from models import AIInsight, OnchainEvent
from reporting import ReportService


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test.db"
        self.storage = Storage(db_path=str(db_path))
        await self.storage.connect()

    async def asyncTearDown(self):
        await self.storage.close()
        self.temp_dir.cleanup()

    async def test_watch_list_persistence(self):
        await self.storage.seed_watch_list(["btc", "SOL"])
        self.assertEqual(await self.storage.get_watch_list(), ["BTC", "SOL"])

        await self.storage.add_watch_symbol("pepe")
        self.assertEqual(await self.storage.get_watch_list(), ["BTC", "PEPE", "SOL"])

        await self.storage.remove_watch_symbol("sol")
        self.assertEqual(await self.storage.get_watch_list(), ["BTC", "PEPE"])

    async def test_batch_save_prices_updates_statistics(self):
        await self.storage.save_prices(
            [
                ("BTC", 65000.0, 1.25),
                ("ETH", 3200.0, -0.75),
            ]
        )

        stats = await self.storage.get_statistics()
        self.assertEqual(stats["total_prices"], 2)

    async def test_save_onchain_event_updates_statistics(self):
        event = OnchainEvent(
            event_id="tx-1",
            source="test",
            event_type="WhaleTransfer",
            symbol="SOL",
            amount_usd=125000.0,
            address="wallet-a",
        )
        insight = AIInsight(
            comment="🚨 巨鲸转账",
            sentiment="neutral",
            event_type="WhaleTransfer",
            confidence=0.9,
        )

        await self.storage.save_onchain_event(
            event,
            rule_level="major",
            rule_reasons=["whale transfer >= 50000.00 USD"],
            rule_tags=["whale-transfer"],
            insight=insight,
        )

        stats = await self.storage.get_statistics()
        self.assertEqual(stats["total_onchain_events"], 1)

        events = await self.storage.get_onchain_events(hours=24)
        self.assertEqual(events[0]["event_id"], "tx-1")
        self.assertEqual(events[0]["rule_tags"], ["whale-transfer"])
        self.assertTrue(await self.storage.has_onchain_event("tx-1"))

    async def test_notification_delivery_persistence(self):
        await self.storage.save_notification_delivery(
            event_kind="onchain_alert",
            target_id="tx-1",
            channel="telegram",
            target="SOL",
            status="failed",
            error="telegram send failed",
            metadata={"level": "major"},
        )

        deliveries = await self.storage.get_notification_deliveries(target_id="tx-1")
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0]["status"], "failed")
        self.assertEqual(deliveries[0]["metadata"], {"level": "major"})

        stats = await self.storage.get_statistics()
        self.assertEqual(stats["total_notification_deliveries"], 1)
        self.assertEqual(stats["failed_notification_deliveries"], 1)

    async def test_daily_report_generation(self):
        get_config().reporting.output_dir = str(Path(self.temp_dir.name) / "reports")
        await self.storage.save_alert(
            "BTC",
            65000.0,
            4.2,
            "major",
            insight=AIInsight(comment="🚀 放量突破", sentiment="bullish", confidence=0.8),
            rule_reasons=["price change +4.20% >= major threshold"],
            rule_tags=["momentum"],
        )

        report = await ReportService(self.storage).generate_daily_report(lookback_hours=24)

        self.assertEqual(report["alerts_count"], 1)
        self.assertIn("BTC", report["content"])
        self.assertTrue(Path(report["file_path"]).exists())


if __name__ == "__main__":
    unittest.main()
