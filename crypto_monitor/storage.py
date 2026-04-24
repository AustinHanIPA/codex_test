"""
数据持久化模块
支持 SQLite 存储历史价格、报警记录与监控名单。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import aiosqlite

from config import get_config
from logger import get_storage_logger
from models import AIInsight, OnchainEvent


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
                sentiment TEXT,
                event_type TEXT DEFAULT 'price_movement',
                risk_hint TEXT,
                suggested_action TEXT,
                confidence REAL DEFAULT 0,
                rule_reasons TEXT,
                rule_tags TEXT,
                telegram_message_id INTEGER,
                sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await self._ensure_alert_columns()

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
            CREATE TABLE IF NOT EXISTS onchain_events (
                event_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                event_type TEXT NOT NULL,
                symbol TEXT,
                address TEXT,
                counterparty TEXT,
                amount REAL,
                amount_usd REAL,
                direction TEXT,
                tx_signature TEXT,
                description TEXT,
                rule_level TEXT,
                rule_reasons TEXT,
                rule_tags TEXT,
                ai_comment TEXT,
                sentiment TEXT,
                risk_hint TEXT,
                suggested_action TEXT,
                confidence REAL DEFAULT 0,
                observed_at DATETIME,
                raw TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                lookback_hours INTEGER,
                generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
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
        await self.db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_onchain_events_created_at
            ON onchain_events(created_at)
            """
        )
        await self.db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_onchain_events_symbol
            ON onchain_events(symbol)
            """
        )

        await self.db.commit()
        self.logger.debug("数据表初始化完成")

    async def _ensure_alert_columns(self) -> None:
        async with self.db.execute("PRAGMA table_info(alerts)") as cursor:
            rows = await cursor.fetchall()
        existing = {row[1] for row in rows}
        columns = {
            "sentiment": "TEXT",
            "event_type": "TEXT DEFAULT 'price_movement'",
            "risk_hint": "TEXT",
            "suggested_action": "TEXT",
            "confidence": "REAL DEFAULT 0",
            "rule_reasons": "TEXT",
            "rule_tags": "TEXT",
        }
        for name, column_type in columns.items():
            if name not in existing:
                await self.db.execute(f"ALTER TABLE alerts ADD COLUMN {name} {column_type}")

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
        insight: Optional[AIInsight] = None,
        rule_reasons: Optional[Sequence[str]] = None,
        rule_tags: Optional[Sequence[str]] = None,
    ) -> None:
        comment = ai_comment or (insight.comment if insight else None)
        await self.db.execute(
            """
            INSERT INTO alerts
            (
                symbol, price, change_percent, alert_level, ai_comment,
                sentiment, event_type, risk_hint, suggested_action, confidence,
                rule_reasons, rule_tags, telegram_message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                price,
                change_percent,
                alert_level,
                comment,
                insight.sentiment if insight else None,
                insight.event_type if insight else "price_movement",
                insight.risk_hint if insight else None,
                insight.suggested_action if insight else None,
                insight.confidence if insight else 0.0,
                json.dumps(list(rule_reasons or []), ensure_ascii=False),
                json.dumps(list(rule_tags or []), ensure_ascii=False),
                telegram_message_id,
            ),
        )
        await self.db.commit()
        self.logger.info(f"保存报警记录: {symbol} {change_percent:+.2f}% [{alert_level}]")

    async def save_onchain_event(
        self,
        event: OnchainEvent,
        rule_level: Optional[str] = None,
        rule_reasons: Optional[Sequence[str]] = None,
        rule_tags: Optional[Sequence[str]] = None,
        insight: Optional[AIInsight] = None,
    ) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO onchain_events
            (
                event_id, source, event_type, symbol, address, counterparty,
                amount, amount_usd, direction, tx_signature, description,
                rule_level, rule_reasons, rule_tags, ai_comment, sentiment,
                risk_hint, suggested_action, confidence, observed_at, raw
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.source,
                event.event_type,
                event.symbol,
                event.address,
                event.counterparty,
                event.amount,
                event.amount_usd,
                event.direction,
                event.tx_signature,
                event.description,
                rule_level,
                json.dumps(list(rule_reasons or []), ensure_ascii=False),
                json.dumps(list(rule_tags or []), ensure_ascii=False),
                insight.comment if insight else None,
                insight.sentiment if insight else None,
                insight.risk_hint if insight else None,
                insight.suggested_action if insight else None,
                insight.confidence if insight else 0.0,
                event.observed_at or datetime.now().isoformat(),
                json.dumps(event.raw, ensure_ascii=False),
            ),
        )
        await self.db.commit()

    async def save_report(
        self,
        report_type: str,
        title: str,
        content: str,
        lookback_hours: int,
    ) -> int:
        cursor = await self.db.execute(
            """
            INSERT INTO reports (report_type, title, content, lookback_hours)
            VALUES (?, ?, ?, ?)
            """,
            (report_type, title, content, lookback_hours),
        )
        await self.db.commit()
        return int(cursor.lastrowid)

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
                SELECT symbol, price, change_percent, alert_level, ai_comment, sent_at,
                       sentiment, event_type, risk_hint, suggested_action, confidence,
                       rule_reasons, rule_tags
                FROM alerts
                WHERE symbol = ? AND sent_at >= ?
                ORDER BY sent_at DESC
                LIMIT ?
            """
            params = (symbol, since.isoformat(), limit)
        else:
            query = """
                SELECT symbol, price, change_percent, alert_level, ai_comment, sent_at,
                       sentiment, event_type, risk_hint, suggested_action, confidence,
                       rule_reasons, rule_tags
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
                "sentiment": row[6],
                "event_type": row[7],
                "risk_hint": row[8],
                "suggested_action": row[9],
                "confidence": row[10],
                "rule_reasons": self._loads_json_list(row[11]),
                "rule_tags": self._loads_json_list(row[12]),
            }
            for row in rows
        ]

    async def get_onchain_events(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        since = datetime.now() - timedelta(hours=hours)
        async with self.db.execute(
            """
            SELECT event_id, source, event_type, symbol, address, counterparty,
                   amount, amount_usd, direction, tx_signature, description,
                   rule_level, rule_reasons, rule_tags, ai_comment, sentiment,
                   risk_hint, suggested_action, confidence, observed_at, created_at
            FROM onchain_events
            WHERE created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (since.isoformat(), limit),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "event_id": row[0],
                "source": row[1],
                "event_type": row[2],
                "symbol": row[3],
                "address": row[4],
                "counterparty": row[5],
                "amount": row[6],
                "amount_usd": row[7],
                "direction": row[8],
                "tx_signature": row[9],
                "description": row[10],
                "rule_level": row[11],
                "rule_reasons": self._loads_json_list(row[12]),
                "rule_tags": self._loads_json_list(row[13]),
                "ai_comment": row[14],
                "sentiment": row[15],
                "risk_hint": row[16],
                "suggested_action": row[17],
                "confidence": row[18],
                "observed_at": row[19],
                "created_at": row[20],
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

        result = await self.db.execute(
            "DELETE FROM onchain_events WHERE created_at < ?",
            (cutoff.isoformat(),),
        )
        onchain_deleted = result.rowcount

        await self.db.commit()
        self.logger.info(
            f"清理过期数据完成: 价格记录 {price_deleted} 条, 报警记录 {alert_deleted} 条, "
            f"链上事件 {onchain_deleted} 条"
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

        async with self.db.execute("SELECT COUNT(*) FROM onchain_events") as cursor:
            row = await cursor.fetchone()
            stats["total_onchain_events"] = row[0] if row else 0

        async with self.db.execute("SELECT COUNT(*) FROM reports") as cursor:
            row = await cursor.fetchone()
            stats["total_reports"] = row[0] if row else 0

        return stats

    @staticmethod
    def _loads_json_list(value: Optional[str]) -> List[str]:
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return []


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
