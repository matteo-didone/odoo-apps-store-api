"""Serie storiche dei contatori e gestione della watchlist."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from ..constants import SERIES_PATTERN
from ..dependencies import get_catalog, get_stats
from ..models import TrendResponse, WatchlistCreate, WatchlistItem
from ..services import CatalogService, StatsService

router = APIRouter(tags=["statistics"])

TECHNICAL_NAME = Path(..., pattern=r"^[A-Za-z0-9_.\-]+$")
SERIES_PATH = Path(..., pattern=SERIES_PATTERN, description="Odoo series, e.g. `18.0`")


@router.get(
    "/stats/{series}/{technical_name}",
    response_model=TrendResponse,
    summary="Download trend over time",
)
async def trend(
    series: str = SERIES_PATH,
    technical_name: str = TECHNICAL_NAME,
    days: int | None = Query(default=None, ge=1, description="Last N samples"),
    sample_now: bool = Query(
        default=True, description="Read the module first, so there is always at least one point"
    ),
    stats: StatsService = Depends(get_stats),
    catalog: CatalogService = Depends(get_catalog),
) -> TrendResponse:
    if sample_now:
        await catalog.get_module(series, technical_name)
    return await stats.trend(technical_name, series, days=days)


@router.get("/watchlist", response_model=list[WatchlistItem], summary="Watched modules")
async def list_watchlist(stats: StatsService = Depends(get_stats)) -> list[WatchlistItem]:
    return await stats.list_watch()


@router.post(
    "/watchlist",
    response_model=WatchlistItem,
    status_code=status.HTTP_201_CREATED,
    summary="Add a module to automatic sampling",
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
    summary="Remove a module from the watchlist",
)
async def remove_watchlist(watch_id: int, stats: StatsService = Depends(get_stats)) -> Response:
    if not await stats.remove_watch(watch_id):
        raise HTTPException(status_code=404, detail=f"Watchlist id {watch_id} does not exist")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/watchlist/refresh", summary="Run a sampling pass right now")
async def refresh_watchlist(
    stats: StatsService = Depends(get_stats),
    catalog: CatalogService = Depends(get_catalog),
) -> dict[str, int]:
    return {"refreshed": await stats.refresh_watchlist(catalog)}
