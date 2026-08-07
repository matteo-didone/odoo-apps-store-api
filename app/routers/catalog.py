"""Categorie, autori e valori ammessi dai filtri."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from ..constants import SERIES, SERIES_PATTERN, Category, Order, PriceFilter
from ..dependencies import get_catalog
from ..models import CategoryInfo, SearchResponse
from ..services import CatalogService

router = APIRouter(tags=["catalogo"])


@router.get("/categories", response_model=list[CategoryInfo], summary="Categorie ufficiali")
async def categories(catalog: CatalogService = Depends(get_catalog)) -> list[CategoryInfo]:
    return catalog.categories()


@router.get("/series", response_model=list[str], summary="Serie Odoo pubblicate sullo store")
async def series() -> list[str]:
    return list(SERIES)


@router.get("/orders", response_model=list[str], summary="Criteri di ordinamento accettati")
async def orders() -> list[str]:
    return [order.value for order in Order]


@router.get(
    "/authors/{author}",
    response_model=SearchResponse,
    summary="Moduli pubblicati da un autore",
)
async def by_author(
    author: str = Path(
        ..., description="Nome esatto del publisher, es. `Cybrosys Techno Solutions`"
    ),
    series: str | None = Query(default=None, pattern=SERIES_PATTERN),
    price: PriceFilter | None = Query(default=None),
    category: Category | None = Query(default=None),
    order: Order | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int | None = Query(default=None, ge=1, le=100),
    catalog: CatalogService = Depends(get_catalog),
) -> SearchResponse:
    return await catalog.search(
        author=author,
        series=series,
        price=price,
        category=category,
        order=order,
        page=page,
        limit=limit,
    )
