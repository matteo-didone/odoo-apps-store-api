"""Interrogazione dello store: ricerca, dettaglio, versioni, categorie, autori."""

from __future__ import annotations

import asyncio
import logging
import math

from ..cache import HtmlCache
from ..config import Settings
from ..constants import CATEGORY_LABELS, Category, Order, PriceFilter
from ..exceptions import StoreNotFound
from ..http_client import HttpFetcher
from ..models import (
    CategoryInfo,
    ModuleDetail,
    ModuleVersionsResponse,
    SearchQuery,
    SearchResponse,
    VersionInfo,
)
from ..scrapers import parse_detail, parse_listing

logger = logging.getLogger(__name__)


class CatalogService:
    def __init__(
        self,
        cache: HtmlCache,
        fetcher: HttpFetcher,
        settings: Settings,
        stats: object | None = None,
    ):
        self._cache = cache
        self._fetcher = fetcher
        self._settings = settings
        self._stats = stats

    # ------------------------------------------------------------------ URL

    def listing_url(
        self,
        *,
        page: int = 1,
        q: str | None = None,
        series: str | None = None,
        price: PriceFilter | None = None,
        category: Category | None = None,
        author: str | None = None,
        order: Order | None = None,
    ) -> str:
        path = "/apps/modules"
        if category is not None:
            path += f"/category/{category.label}"
        path += "/browse"
        if page > 1:
            path += f"/page/{page}"

        params: dict[str, str] = {}
        if q:
            params["search"] = q
        if order is not None:
            params["order"] = order.upstream
        if series:
            params["series"] = series
        if price is not None:
            params["price"] = price.upstream
        if author:
            params["author"] = author
        return self._fetcher.build_url(path, params)

    def module_url(self, series: str, technical_name: str) -> str:
        return self._fetcher.build_url(f"/apps/modules/{series}/{technical_name}")

    # --------------------------------------------------------------- ricerca

    async def search(
        self,
        *,
        q: str | None = None,
        series: str | None = None,
        price: PriceFilter | None = None,
        category: Category | None = None,
        author: str | None = None,
        order: Order | None = None,
        page: int = 1,
        limit: int | None = None,
    ) -> SearchResponse:
        page_size = self._settings.page_size
        limit = min(limit or page_size, self._settings.max_search_limit)
        pages_needed = max(1, math.ceil(limit / page_size))

        urls = [
            self.listing_url(
                page=page + offset,
                q=q,
                series=series,
                price=price,
                category=category,
                author=author,
                order=order,
            )
            for offset in range(pages_needed)
        ]

        fetched = await asyncio.gather(
            *(self._cache.get(url, self._settings.ttl_listing) for url in urls)
        )

        cards = []
        total_pages: int | None = None
        for item in fetched:
            if item.status == 404:
                continue
            result = parse_listing(item.text, self._settings.base_url)
            cards.extend(result.cards)
            if result.total_pages is not None:
                total_pages = max(total_pages or 0, result.total_pages)

        cards = cards[:limit]
        last_page_fetched = page + pages_needed - 1
        total_estimated = total_pages * page_size if total_pages else None

        return SearchResponse(
            items=cards,
            page=page,
            per_page=page_size,
            returned=len(cards),
            total_pages=total_pages,
            total_estimated=total_estimated,
            has_next=bool(total_pages and last_page_fetched < total_pages),
            query=SearchQuery(
                q=q,
                series=series,
                price=price.value if price else None,
                category=category.value if category else None,
                author=author,
                order=order.value if order else None,
            ),
            source_urls=urls,
            from_cache=all(item.from_cache for item in fetched),
            stale=any(item.stale for item in fetched),
        )

    # -------------------------------------------------------------- dettaglio

    async def get_module(
        self, series: str, technical_name: str, *, force_refresh: bool = False
    ) -> ModuleDetail:
        url = self.module_url(series, technical_name)
        fetched = await self._cache.get(
            url, self._settings.ttl_detail, force_refresh=force_refresh
        )
        if fetched.status == 404:
            raise StoreNotFound(
                f"Il modulo '{technical_name}' non esiste per la serie {series}"
            )

        detail = parse_detail(
            fetched.text,
            self._settings.base_url,
            series=series,
            technical_name=technical_name,
        )
        detail.fetched_at = fetched.fetched_at
        detail.from_cache = fetched.from_cache
        detail.stale = fetched.stale

        # Lo snapshot ha senso solo su una lettura reale dall'upstream.
        if self._stats is not None and not fetched.from_cache and not fetched.stale:
            try:
                await self._stats.record(detail)
            except Exception:  # noqa: BLE001 - lo snapshot non deve mai far fallire la risposta
                logger.exception("Snapshot non registrato per %s/%s", series, technical_name)

        return detail

    async def get_versions(
        self,
        technical_name: str,
        *,
        series: str | None = None,
        detailed: bool = False,
    ) -> ModuleVersionsResponse:
        known_series = series or await self._discover_series(technical_name)
        detail = await self.get_module(known_series, technical_name)

        available = detail.available_series or [detail.series]
        versions = [
            VersionInfo(series=item, url=self.module_url(item, technical_name))
            for item in available
        ]

        if detailed:
            details = await asyncio.gather(
                *(self.get_module(item, technical_name) for item in available),
                return_exceptions=True,
            )
            for version, result in zip(versions, details, strict=True):
                if isinstance(result, ModuleDetail):
                    version.version = result.latest_version
                    version.name = result.name
                    version.price = result.price
                    version.downloads_total = result.downloads_total

        return ModuleVersionsResponse(
            technical_name=technical_name,
            series_available=available,
            versions=versions,
            detailed=detailed,
        )

    async def _discover_series(self, technical_name: str) -> str:
        """Senza serie nota, la ricerca per nome tecnico ne individua una qualsiasi."""
        found = await self.search(q=technical_name, limit=self._settings.page_size)
        for card in found.items:
            if card.technical_name == technical_name:
                return card.series
        raise StoreNotFound(
            f"Nessun modulo '{technical_name}' trovato sull'Odoo Apps Store"
        )

    # -------------------------------------------------------------- cataloghi

    def categories(self) -> list[CategoryInfo]:
        return [
            CategoryInfo(
                slug=slug,
                label=label,
                url=self._fetcher.build_url(f"/apps/modules/category/{label}/browse"),
            )
            for slug, label in CATEGORY_LABELS.items()
        ]
