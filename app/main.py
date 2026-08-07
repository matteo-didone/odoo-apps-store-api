"""Entry point FastAPI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import get_settings
from .dependencies import Services, get_services
from .exceptions import ParseError, SourceUnavailable, StoreNotFound, UpstreamError
from .models import HealthResponse
from .routers import catalog, modules, sources, stats

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"

DESCRIPTION = """
API REST **non ufficiale** per interrogare l'[Odoo Apps Store](https://apps.odoo.com/apps).

Odoo non espone alcuna API pubblica per lo store: questo servizio legge le pagine
del sito, le normalizza in JSON e le tiene in cache SQLite. Le richieste verso
apps.odoo.com sono limitate a **1 al secondo** con al massimo 4 richieste in parallelo.

Progetto indipendente, senza alcuna affiliazione con Odoo S.A.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    services = await Services.create(settings)
    app.state.services = services

    if settings.enable_scheduler:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            services.stats.refresh_watchlist,
            trigger=CronTrigger(hour=settings.snapshot_hour, minute=settings.snapshot_minute),
            args=[services.catalog],
            id="snapshot_watchlist",
            replace_existing=True,
        )
        scheduler.start()
        services.scheduler = scheduler
        logger.info(
            "Campionamento watchlist pianificato ogni giorno alle %02d:%02d",
            settings.snapshot_hour,
            settings.snapshot_minute,
        )

    try:
        yield
    finally:
        await services.close()


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="Odoo Apps Store API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(modules.router, prefix=API_PREFIX)
    application.include_router(catalog.router, prefix=API_PREFIX)
    application.include_router(stats.router, prefix=API_PREFIX)
    application.include_router(sources.router, prefix=API_PREFIX)

    @application.exception_handler(SourceUnavailable)
    async def handle_source_unavailable(
        request: Request, exc: SourceUnavailable
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": exc.message})

    @application.exception_handler(StoreNotFound)
    async def handle_not_found(request: Request, exc: StoreNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": exc.message})

    @application.exception_handler(UpstreamError)
    async def handle_upstream(request: Request, exc: UpstreamError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"detail": exc.message, "retry_after": exc.retry_after},
            headers={"Retry-After": str(exc.retry_after)},
        )

    @application.exception_handler(ParseError)
    async def handle_parse(request: Request, exc: ParseError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "detail": exc.message,
                "hint": "Il markup di apps.odoo.com è probabilmente cambiato: aggiornare i parser",
            },
        )

    @application.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"name": "Odoo Apps Store API", "version": __version__, "docs": "/docs"}

    @application.get(f"{API_PREFIX}/health", response_model=HealthResponse, tags=["servizio"])
    async def health(services: Services = Depends(get_services)) -> HealthResponse:
        return HealthResponse(
            version=__version__,
            upstream=services.settings.base_url,
            cache_entries=await services.db.scalar("SELECT COUNT(*) FROM http_cache") or 0,
            cache_hits=services.cache.hits,
            cache_misses=services.cache.misses,
            cache_hit_rate=services.cache.hit_rate,
            snapshots=await services.db.scalar("SELECT COUNT(*) FROM module_snapshots") or 0,
            watchlist=await services.db.scalar("SELECT COUNT(*) FROM watchlist") or 0,
            sources=await services.source.count(),
            scheduler_running=bool(services.scheduler and services.scheduler.running),
        )

    return application


app = create_app()
