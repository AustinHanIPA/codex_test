import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crypto_monitor"))

from storage import Storage


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


if __name__ == "__main__":
    unittest.main()
