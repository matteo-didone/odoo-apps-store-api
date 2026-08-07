"""Ricerca e schede dei moduli."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from ..constants import SERIES_PATTERN, Category, Order, PriceFilter
from ..dependencies import get_catalog
from ..models import ModuleDetail, ModuleVersionsResponse, SearchResponse
from ..services import CatalogService

router = APIRouter(tags=["modules"])

TECHNICAL_NAME = Path(
    ...,
    pattern=r"^[A-Za-z0-9_.\-]+$",
    description="Module technical name, e.g. `web_responsive`",
)
SERIES_PATH = Path(
    ..., pattern=SERIES_PATTERN, description="Odoo series, e.g. `18.0` or `saas-19.4`"
)


@router.get("/search", response_model=SearchResponse, summary="Search modules")
async def search(
    q: str | None = Query(default=None, description="Free text"),
    series: str | None = Query(default=None, pattern=SERIES_PATTERN, description="Odoo series"),
    price: PriceFilter | None = Query(default=None),
    category: Category | None = Query(default=None),
    author: str | None = Query(default=None, description="Exact publisher name"),
    order: Order | None = Query(default=None),
    page: int = Query(default=1, ge=1, description="Starting page (20 results per page)"),
    limit: int | None = Query(
        default=None, ge=1, le=100, description="Total results; above 20 it reads several pages"
    ),
    catalog: CatalogService = Depends(get_catalog),
) -> SearchResponse:
    return await catalog.search(
        q=q,
        series=series,
        price=price,
        category=category,
        author=author,
        order=order,
        page=page,
        limit=limit,
    )


# Deve restare prima di /modules/{series}/{technical_name}: quella rotta
# matcherebbe anche /modules/<nome>/versions.
@router.get(
    "/modules/{technical_name}/versions",
    response_model=ModuleVersionsResponse,
    summary="Odoo series the module is published on",
)
async def get_versions(
    technical_name: str = TECHNICAL_NAME,
    series: str | None = Query(
        default=None,
        pattern=SERIES_PATTERN,
        description="Series to start from; discovered with a search when omitted",
    ),
    detailed: bool = Query(
        default=False, description="Enrich each series with version, price, and downloads"
    ),
    catalog: CatalogService = Depends(get_catalog),
) -> ModuleVersionsResponse:
    return await catalog.get_versions(technical_name, series=series, detailed=detailed)


@router.get(
    "/modules/{series}/{technical_name}",
    response_model=ModuleDetail,
    summary="Full module listing",
)
async def get_module(
    series: str = SERIES_PATH,
    technical_name: str = TECHNICAL_NAME,
    refresh: bool = Query(default=False, description="Ignore the cache and re-read from upstream"),
    catalog: CatalogService = Depends(get_catalog),
) -> ModuleDetail:
    return await catalog.get_module(series, technical_name, force_refresh=refresh)
