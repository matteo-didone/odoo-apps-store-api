"""Serie storiche dei contatori e gestione della watchlist."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from ..constants import SERIES_PATTERN
from ..dependencies import get_catalog, get_stats
from ..models import TrendResponse, WatchlistCreate, WatchlistItem
from ..services import CatalogService, StatsService

router = APIRouter(tags=["statistiche"])

TECHNICAL_NAME = Path(..., pattern=r"^[A-Za-z0-9_.\-]+$")
SERIES_PATH = Path(..., pattern=SERIES_PATTERN, description="Serie Odoo, es. `18.0`")


@router.get(
    "/stats/{series}/{technical_name}",
    response_model=TrendResponse,
    summary="Andamento dei download nel tempo",
)
async def trend(
    series: str = SERIES_PATH,
    technical_name: str = TECHNICAL_NAME,
    days: int | None = Query(default=None, ge=1, description="Ultimi N campionamenti"),
    sample_now: bool = Query(
        default=True, description="Legge il modulo prima di rispondere, così c'è sempre un punto"
    ),
    stats: StatsService = Depends(get_stats),
    catalog: CatalogService = Depends(get_catalog),
) -> TrendResponse:
    if sample_now:
        await catalog.get_module(series, technical_name)
    return await stats.trend(technical_name, series, days=days)


@router.get("/watchlist", response_model=list[WatchlistItem], summary="Moduli osservati")
async def list_watchlist(stats: StatsService = Depends(get_stats)) -> list[WatchlistItem]:
    return await stats.list_watch()


@router.post(
    "/watchlist",
    response_model=WatchlistItem,
    status_code=status.HTTP_201_CREATED,
    summary="Aggiunge un modulo al campionamento automatico",
)
async def add_watchlist(
    payload: WatchlistCreate,
    stats: StatsService = Depends(get_stats),
    catalog: CatalogService = Depends(get_catalog),
) -> WatchlistItem:
    # Verifica che il modulo esista davvero e registra subito il primo punto.
    await catalog.get_module(payload.series, payload.technical_name)
    return await stats.add_watch(payload.technical_name, payload.series)


@router.delete(
    "/watchlist/{watch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Rimuove un modulo dalla watchlist",
)
async def remove_watchlist(watch_id: int, stats: StatsService = Depends(get_stats)) -> Response:
    if not await stats.remove_watch(watch_id):
        raise HTTPException(status_code=404, detail=f"Watchlist id {watch_id} inesistente")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/watchlist/refresh", summary="Forza subito un giro di campionamento")
async def refresh_watchlist(
    stats: StatsService = Depends(get_stats),
    catalog: CatalogService = Depends(get_catalog),
) -> dict[str, int]:
    return {"refreshed": await stats.refresh_watchlist(catalog)}
