"""Cache SQLite delle pagine HTML, con fallback stale-if-error."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from .config import Settings
from .db import Database
from .exceptions import UpstreamError
from .http_client import HttpFetcher

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Fetched:
    url: str
    status: int
    text: str
    fetched_at: datetime
    from_cache: bool = False
    stale: bool = False


class HtmlCache:
    def __init__(self, db: Database, fetcher: HttpFetcher, settings: Settings):
        self._db = db
        self._fetcher = fetcher
        self._settings = settings
        self.hits = 0
        self.misses = 0

    async def get(self, url: str, ttl: int, *, force_refresh: bool = False) -> Fetched:
        cached = await self._read(url)

        if cached and not force_refresh:
            effective_ttl = self._settings.ttl_not_found if cached.status == 404 else ttl
            if time.time() - cached.fetched_at.timestamp() < effective_ttl:
                self.hits += 1
                return cached

        self.misses += 1
        try:
            response = await self._fetcher.get(url)
        except UpstreamError:
            if cached:
                logger.warning("Upstream KO su %s: servo la copia in cache (stale)", url)
                cached.stale = True
                return cached
            raise

        fetched = Fetched(
            url=url,
            status=response.status_code,
            text=response.text,
            fetched_at=datetime.now(UTC),
        )
        # Anche i 404 vanno in cache (con TTL breve) per non martellare l'upstream.
        if fetched.status in (200, 404):
            await self._write(fetched)
        elif cached:
            cached.stale = True
            return cached
        return fetched

    async def _read(self, url: str) -> Fetched | None:
        row = await self._db.fetch_one(
            "SELECT url, status, body, fetched_at FROM http_cache WHERE url = ?", (url,)
        )
        if row is None:
            return None
        return Fetched(
            url=row["url"],
            status=row["status"],
            text=row["body"],
            fetched_at=datetime.fromtimestamp(row["fetched_at"], UTC),
            from_cache=True,
        )

    async def _write(self, fetched: Fetched) -> None:
        await self._db.execute(
            """
            INSERT INTO http_cache (url, status, body, fetched_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                status = excluded.status,
                body = excluded.body,
                fetched_at = excluded.fetched_at
            """,
            (fetched.url, fetched.status, fetched.text, fetched.fetched_at.timestamp()),
        )

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 3) if total else 0.0
