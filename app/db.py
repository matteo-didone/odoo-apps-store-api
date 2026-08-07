"""Accesso a SQLite: cache HTTP, snapshot dei contatori e watchlist."""

from __future__ import annotations

import os
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (
    url         TEXT PRIMARY KEY,
    status      INTEGER NOT NULL,
    body        TEXT NOT NULL,
    fetched_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS module_snapshots (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    technical_name       TEXT NOT NULL,
    series               TEXT NOT NULL,
    snapshot_date        TEXT NOT NULL,
    downloads_total      INTEGER,
    downloads_last_month INTEGER,
    purchases            INTEGER,
    rating_value         REAL,
    rating_votes         INTEGER,
    price_amount         REAL,
    price_currency       TEXT,
    latest_version       TEXT,
    created_at           REAL NOT NULL,
    UNIQUE (technical_name, series, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_module
    ON module_snapshots (technical_name, series, snapshot_date);

CREATE TABLE IF NOT EXISTS watchlist (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    technical_name TEXT NOT NULL,
    series         TEXT NOT NULL,
    created_at     REAL NOT NULL,
    UNIQUE (technical_name, series)
);

CREATE TABLE IF NOT EXISTS module_sources (
    technical_name  TEXT NOT NULL,
    series          TEXT NOT NULL,
    repo_url        TEXT NOT NULL,
    ref             TEXT NOT NULL,
    path            TEXT NOT NULL,
    name            TEXT,
    version         TEXT,
    license         TEXT,
    author          TEXT,
    depends         TEXT,
    file_count      INTEGER NOT NULL,
    bytes_extracted INTEGER NOT NULL,
    archive_sha256  TEXT NOT NULL,
    fetched_at      REAL NOT NULL,
    PRIMARY KEY (technical_name, series)
);
"""


class Database:
    """Wrapper sottile su una singola connessione aiosqlite condivisa dall'app."""

    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self._conn is not None:
            return
        if self.path != ":memory:":
            directory = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(directory, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database non connesso: chiamare connect() prima dell'uso")
        return self._conn

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Cursor:
        cursor = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cursor

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        async with self.conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())

    async def scalar(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        row = await self.fetch_one(sql, params)
        return row[0] if row else None
