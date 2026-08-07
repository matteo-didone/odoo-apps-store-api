"""Contenitore dei servizi condivisi e dipendenze FastAPI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Request

from .cache import HtmlCache
from .config import Settings
from .db import Database
from .http_client import HttpFetcher
from .services import CatalogService, SourceService, StatsService
from .sources import GitHubFetcher

if TYPE_CHECKING:  # pragma: no cover
    from apscheduler.schedulers.asyncio import AsyncIOScheduler


@dataclass
class Services:
    settings: Settings
    db: Database
    fetcher: HttpFetcher
    cache: HtmlCache
    catalog: CatalogService
    stats: StatsService
    github: GitHubFetcher
    source: SourceService
    scheduler: AsyncIOScheduler | None = None

    @classmethod
    async def create(cls, settings: Settings) -> Services:
        db = Database(settings.db_path)
        await db.connect()
        fetcher = HttpFetcher(settings)
        cache = HtmlCache(db, fetcher, settings)
        stats = StatsService(db)
        catalog = CatalogService(cache, fetcher, settings, stats=stats)
        github = GitHubFetcher(settings)
        source = SourceService(db, github, catalog, settings)
        return cls(
            settings=settings,
            db=db,
            fetcher=fetcher,
            cache=cache,
            catalog=catalog,
            stats=stats,
            github=github,
            source=source,
        )

    async def close(self) -> None:
        if self.scheduler is not None and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        await self.fetcher.close()
        await self.github.close()
        await self.db.close()


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_catalog(request: Request) -> CatalogService:
    return get_services(request).catalog


def get_stats(request: Request) -> StatsService:
    return get_services(request).stats


def get_source(request: Request) -> SourceService:
    return get_services(request).source
