"""Ricerca e schede dei moduli."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from ..constants import SERIES_PATTERN, Category, Order, PriceFilter
from ..dependencies import get_catalog
from ..models import ModuleDetail, ModuleVersionsResponse, SearchResponse
from ..services import CatalogService

router = APIRouter(tags=["moduli"])

TECHNICAL_NAME = Path(
    ...,
    pattern=r"^[A-Za-z0-9_.\-]+$",
    description="Nome tecnico del modulo, es. `web_responsive`",
)
SERIES_PATH = Path(..., pattern=SERIES_PATTERN, description="Serie Odoo, es. `18.0` o `saas-19.4`")


@router.get("/search", response_model=SearchResponse, summary="Cerca moduli")
async def search(
    q: str | None = Query(default=None, description="Testo libero"),
    series: str | None = Query(default=None, pattern=SERIES_PATTERN, description="Serie Odoo"),
    price: PriceFilter | None = Query(default=None),
    category: Category | None = Query(default=None),
    author: str | None = Query(default=None, description="Nome esatto del publisher"),
    order: Order | None = Query(default=None),
    page: int = Query(default=1, ge=1, description="Pagina di partenza (20 risultati per pagina)"),
    limit: int | None = Query(
        default=None, ge=1, le=100, description="Risultati totali; oltre 20 legge più pagine"
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
    summary="Serie Odoo su cui il modulo è pubblicato",
)
async def get_versions(
    technical_name: str = TECHNICAL_NAME,
    series: str | None = Query(
        default=None,
        pattern=SERIES_PATTERN,
        description="Serie da cui partire; se omessa viene individuata via ricerca",
    ),
    detailed: bool = Query(
        default=False, description="Arricchisce ogni serie con versione, prezzo e download"
    ),
    catalog: CatalogService = Depends(get_catalog),
) -> ModuleVersionsResponse:
    return await catalog.get_versions(technical_name, series=series, detailed=detailed)


@router.get(
    "/modules/{series}/{technical_name}",
    response_model=ModuleDetail,
    summary="Scheda completa di un modulo",
)
async def get_module(
    series: str = SERIES_PATH,
    technical_name: str = TECHNICAL_NAME,
    refresh: bool = Query(default=False, description="Ignora la cache e rilegge dall'upstream"),
    catalog: CatalogService = Depends(get_catalog),
) -> ModuleDetail:
    return await catalog.get_module(series, technical_name, force_refresh=refresh)
