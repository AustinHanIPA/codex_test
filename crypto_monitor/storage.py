"""
数据持久化模块
支持 SQLite 存储历史价格、报警记录与监控名单。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import aiosqlite

from config import get_config
from logger import get_storage_logger


PriceRecord = Tuple[str, float, Optional[float]]


class Storage:
    """异步存储服务。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_config().storage.sqlite.path
        self.logger = get_storage_logger()
        self._db: Optional[aiosqlite.Connection] = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        return self._db

    async def connect(self) -> None:
        if self._db is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self.db_path)
            await self._init_tables()
            self.logger.info(f"数据库连接成功: {self.db_path}")

    async def close(self) -> None:
        if self._db:
            await self.db.close()
            self._db = None
            self.logger.info("数据库连接已关闭")

    async def _init_tables(self) -> None:
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                change_percent REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                change_percent REAL NOT NULL,
                alert_level TEXT NOT NULL,
                ai_comment TEXT,
                telegram_message_id INTEGER,
                sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS symbol_state (
                symbol TEXT PRIMARY KEY,
                last_price REAL NOT NULL,
                last_alert_time DATETIME,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist_symbols (
                symbol TEXT PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await self.db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_price_history_symbol
            ON price_history(symbol)
            """
        )
        await self.db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_price_history_timestamp
            ON price_history(timestamp)
            """
        )
        await self.db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_alerts_symbol
            ON alerts(symbol)
            """
        )
        await self.db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_alerts_sent_at
            ON alerts(sent_at)
            """
        )

        await self.db.commit()
        self.logger.debug("数据表初始化完成")

    async def save_price(
        self,
        symbol: str,
        price: float,
        change_percent: Optional[float] = None,
    ) -> None:
        await self.save_prices([(symbol, price, change_percent)])

    async def save_prices(self, records: Sequence[PriceRecord]) -> None:
        if not records:
            return

        await self.db.executemany(
            """
            INSERT INTO price_history (symbol, price, change_percent)
            VALUES (?, ?, ?)
            """,
            records,
        )
        await self.db.commit()

    async def save_alert(
        self,
        symbol: str,
        price: float,
        change_percent: float,
        alert_level: str,
        ai_comment: Optional[str] = None,
        telegram_message_id: Optional[int] = None,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO alerts
            (symbol, price, change_percent, alert_level, ai_comment, telegram_message_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (symbol, price, change_percent, alert_level, ai_comment, telegram_message_id),
        )
        await self.db.commit()
        self.logger.info(f"保存报警记录: {symbol} {change_percent:+.2f}% [{alert_level}]")

    async def update_symbol_state(
        self,
        symbol: str,
        last_price: float,
        last_alert_time: Optional[datetime] = None,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO symbol_state (symbol, last_price, last_alert_time, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol) DO UPDATE SET
                last_price = excluded.last_price,
                last_alert_time = excluded.last_alert_time,
                updated_at = CURRENT_TIMESTAMP
            """,
            (symbol, last_price, last_alert_time),
        )
        await self.db.commit()

    async def get_symbol_state(self, symbol: str) -> Optional[Dict[str, Any]]:
        async with self.db.execute(
            "SELECT last_price, last_alert_time FROM symbol_state WHERE symbol = ?",
            (symbol,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "last_price": row[0],
                    "last_alert_time": datetime.fromisoformat(row[1]) if row[1] else None,
                }
            return None

    async def get_all_symbol_states(self) -> Dict[str, Dict[str, Any]]:
        states: Dict[str, Dict[str, Any]] = {}
        async with self.db.execute(
            "SELECT symbol, last_price, last_alert_time FROM symbol_state"
        ) as cursor:
            async for row in cursor:
                states[row[0]] = {
                    "last_price": row[1],
                    "last_alert_time": datetime.fromisoformat(row[2]) if row[2] else None,
                }
        return states

    async def seed_watch_list(self, symbols: Iterable[str]) -> None:
        normalized = sorted({symbol.upper() for symbol in symbols if symbol})
        if not normalized:
            return

        await self.db.executemany(
            """
            INSERT OR IGNORE INTO watchlist_symbols (symbol)
            VALUES (?)
            """,
            [(symbol,) for symbol in normalized],
        )
        await self.db.commit()

    async def get_watch_list(self) -> List[str]:
        async with self.db.execute(
            "SELECT symbol FROM watchlist_symbols ORDER BY symbol ASC"
        ) as cursor:
            rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def add_watch_symbol(self, symbol: str) -> None:
        normalized = symbol.upper()
        await self.db.execute(
            """
            INSERT OR IGNORE INTO watchlist_symbols (symbol)
            VALUES (?)
            """,
            (normalized,),
        )
        await self.db.commit()

    async def remove_watch_symbol(self, symbol: str) -> None:
        normalized = symbol.upper()
        await self.db.execute(
            "DELETE FROM watchlist_symbols WHERE symbol = ?",
            (normalized,),
        )
        await self.db.commit()

    async def get_price_history(
        self,
        symbol: str,
        hours: int = 24,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        since = datetime.now() - timedelta(hours=hours)
        async with self.db.execute(
            """
            SELECT price, change_percent, timestamp
            FROM price_history
            WHERE symbol = ? AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (symbol, since.isoformat(), limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {"price": row[0], "change_percent": row[1], "timestamp": row[2]}
            for row in rows
        ]

    async def get_alert_history(
        self,
        symbol: Optional[str] = None,
        hours: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        since = datetime.now() - timedelta(hours=hours)

        if symbol:
            query = """
                SELECT symbol, price, change_percent, alert_level, ai_comment, sent_at
                FROM alerts
                WHERE symbol = ? AND sent_at >= ?
                ORDER BY sent_at DESC
                LIMIT ?
            """
            params = (symbol, since.isoformat(), limit)
        else:
            query = """
                SELECT symbol, price, change_percent, alert_level, ai_comment, sent_at
                FROM alerts
                WHERE sent_at >= ?
                ORDER BY sent_at DESC
                LIMIT ?
            """
            params = (since.isoformat(), limit)

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "symbol": row[0],
                "price": row[1],
                "change_percent": row[2],
                "alert_level": row[3],
                "ai_comment": row[4],
                "sent_at": row[5],
            }
            for row in rows
        ]

    async def cleanup_old_data(self, retention_days: int = 30) -> None:
        cutoff = datetime.now() - timedelta(days=retention_days)

        result = await self.db.execute(
            "DELETE FROM price_history WHERE timestamp < ?",
            (cutoff.isoformat(),),
        )
        price_deleted = result.rowcount

        result = await self.db.execute(
            "DELETE FROM alerts WHERE sent_at < ?",
            (cutoff.isoformat(),),
        )
        alert_deleted = result.rowcount

        await self.db.commit()
        self.logger.info(
            f"清理过期数据完成: 价格记录 {price_deleted} 条, 报警记录 {alert_deleted} 条"
        )

    async def get_statistics(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}

        async with self.db.execute("SELECT COUNT(*) FROM price_history") as cursor:
            row = await cursor.fetchone()
            stats["total_prices"] = row[0] if row else 0

        async with self.db.execute("SELECT COUNT(*) FROM alerts") as cursor:
            row = await cursor.fetchone()
            stats["total_alerts"] = row[0] if row else 0

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        async with self.db.execute(
            "SELECT COUNT(*) FROM alerts WHERE sent_at >= ?",
            (today.isoformat(),),
        ) as cursor:
            row = await cursor.fetchone()
            stats["today_alerts"] = row[0] if row else 0

        async with self.db.execute("SELECT COUNT(*) FROM symbol_state") as cursor:
            row = await cursor.fetchone()
            stats["monitored_symbols"] = row[0] if row else 0

        async with self.db.execute("SELECT COUNT(*) FROM watchlist_symbols") as cursor:
            row = await cursor.fetchone()
            stats["watchlist_symbols"] = row[0] if row else 0

        return stats


_storage: Optional[Storage] = None


async def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = Storage()
        await _storage.connect()
    return _storage


async def close_storage() -> None:
    global _storage
    if _storage:
        await _storage.close()
        _storage = None
