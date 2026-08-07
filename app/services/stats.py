"""Snapshot dei contatori e serie storiche.

Lo store non pubblica alcuno storico: i trend nascono dai campionamenti fatti
da questa API, quindi partono dal giorno della prima lettura.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime

from ..db import Database
from ..models import ModuleDetail, TrendPoint, TrendResponse, WatchlistItem

logger = logging.getLogger(__name__)


class StatsService:
    def __init__(self, db: Database):
        self._db = db

    # -------------------------------------------------------------- snapshot

    async def record(self, detail: ModuleDetail, *, on: date | None = None) -> None:
        """Un campionamento al giorno per (modulo, serie); l'ultimo sovrascrive."""
        if not detail.technical_name or not detail.series:
            return
        snapshot_date = (on or datetime.now(UTC).date()).isoformat()
        await self._db.execute(
            """
            INSERT INTO module_snapshots (
                technical_name, series, snapshot_date, downloads_total,
                downloads_last_month, purchases, rating_value, rating_votes,
                price_amount, price_currency, latest_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (technical_name, series, snapshot_date) DO UPDATE SET
                downloads_total      = excluded.downloads_total,
                downloads_last_month = excluded.downloads_last_month,
                purchases            = excluded.purchases,
                rating_value         = excluded.rating_value,
                rating_votes         = excluded.rating_votes,
                price_amount         = excluded.price_amount,
                price_currency       = excluded.price_currency,
                latest_version       = excluded.latest_version,
                created_at           = excluded.created_at
            """,
            (
                detail.technical_name,
                detail.series,
                snapshot_date,
                detail.downloads_total,
                detail.downloads_last_month,
                detail.purchases,
                detail.rating.value,
                detail.rating.votes,
                detail.price.amount,
                detail.price.currency,
                detail.latest_version,
                time.time(),
            ),
        )

    async def trend(
        self, technical_name: str, series: str, *, days: int | None = None
    ) -> TrendResponse:
        rows = await self._db.fetch_all(
            """
            SELECT snapshot_date, downloads_total, downloads_last_month, purchases,
                   rating_value, rating_votes, price_amount, latest_version
            FROM module_snapshots
            WHERE technical_name = ? AND series = ?
            ORDER BY snapshot_date ASC
            """,
            (technical_name, series),
        )

        points = [
            TrendPoint(
                date=date.fromisoformat(row["snapshot_date"]),
                downloads_total=row["downloads_total"],
                downloads_last_month=row["downloads_last_month"],
                purchases=row["purchases"],
                rating_value=row["rating_value"],
                rating_votes=row["rating_votes"],
                price_amount=row["price_amount"],
                latest_version=row["latest_version"],
            )
            for row in rows
        ]
        if days is not None:
            points = points[-days:]

        response = TrendResponse(technical_name=technical_name, series=series, points=points)
        if points:
            response.first_seen = points[0].date
            response.last_seen = points[-1].date
            first, last = points[0], points[-1]
            # Con un solo campionamento non c'è ancora un delta: meglio null che zero.
            if len(points) > 1 and None not in (first.downloads_total, last.downloads_total):
                response.delta_downloads = last.downloads_total - first.downloads_total
                elapsed = (last.date - first.date).days
                if elapsed > 0:
                    response.avg_downloads_per_day = round(response.delta_downloads / elapsed, 2)
        return response

    # ------------------------------------------------------------- watchlist

    async def add_watch(self, technical_name: str, series: str) -> WatchlistItem:
        now = time.time()
        await self._db.execute(
            """
            INSERT INTO watchlist (technical_name, series, created_at) VALUES (?, ?, ?)
            ON CONFLICT (technical_name, series) DO NOTHING
            """,
            (technical_name, series, now),
        )
        row = await self._db.fetch_one(
            "SELECT id, technical_name, series, created_at FROM watchlist "
            "WHERE technical_name = ? AND series = ?",
            (technical_name, series),
        )
        return _to_watchlist_item(row)

    async def list_watch(self) -> list[WatchlistItem]:
        rows = await self._db.fetch_all(
            "SELECT id, technical_name, series, created_at FROM watchlist ORDER BY id"
        )
        return [_to_watchlist_item(row) for row in rows]

    async def remove_watch(self, watch_id: int) -> bool:
        cursor = await self._db.execute("DELETE FROM watchlist WHERE id = ?", (watch_id,))
        return cursor.rowcount > 0

    async def refresh_watchlist(self, catalog) -> int:
        """Rilegge dall'upstream tutti i moduli osservati e ne registra lo snapshot."""
        watched = await self.list_watch()
        done = 0
        for item in watched:
            try:
                await catalog.get_module(item.series, item.technical_name, force_refresh=True)
                done += 1
            except Exception:  # noqa: BLE001 - un modulo rimosso non deve fermare il giro
                logger.exception(
                    "Snapshot fallito per %s/%s", item.series, item.technical_name
                )
        logger.info("Watchlist aggiornata: %s/%s moduli", done, len(watched))
        return done


def _to_watchlist_item(row) -> WatchlistItem:
    return WatchlistItem(
        id=row["id"],
        technical_name=row["technical_name"],
        series=row["series"],
        created_at=datetime.fromtimestamp(row["created_at"], UTC),
    )
