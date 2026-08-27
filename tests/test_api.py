"""Test degli endpoint con la cache pre-popolata: nessuna richiesta di rete."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.models import ModuleDetail, Price, Rating

from .conftest import fixture


async def test_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["scheduler_running"] is False


async def test_categorie(client):
    response = await client.get("/api/v1/categories")
    assert response.status_code == 200
    categories = response.json()
    assert len(categories) == 18
    assert {"slug": "point_of_sale", "label": "Point of Sale"}.items() <= categories[
        [c["slug"] for c in categories].index("point_of_sale")
    ].items()


async def test_serie_e_ordinamenti(client):
    assert "19.0" in (await client.get("/api/v1/series")).json()
    assert "best_sellers" in (await client.get("/api/v1/orders")).json()


async def test_dettaglio_modulo(client, app_and_services, seed_cache):
    _, services = app_and_services
    url = services.catalog.module_url("19.0", "web_responsive")
    await seed_cache(url, fixture("detail_web_responsive_19.html"))

    response = await client.get("/api/v1/modules/19.0/web_responsive")
    assert response.status_code == 200

    body = response.json()
    assert body["name"] == "Web Responsive"
    assert body["license"] == "LGPL-3"
    assert body["dependencies"] == ["mail"]
    assert body["from_cache"] is True
    assert body["stale"] is False


async def test_modulo_inesistente(client, app_and_services, seed_cache):
    _, services = app_and_services
    url = services.catalog.module_url("19.0", "modulo_inesistente")
    await seed_cache(url, fixture("detail_not_found.html"), status=404)

    response = await client.get("/api/v1/modules/19.0/modulo_inesistente")
    assert response.status_code == 404
    assert "modulo_inesistente" in response.json()["detail"]


async def test_serie_malformata(client):
    response = await client.get("/api/v1/modules/diciotto/web_responsive")
    assert response.status_code == 422


async def test_ricerca(client, app_and_services, seed_cache):
    _, services = app_and_services
    url = services.catalog.listing_url(q="whatsapp")
    await seed_cache(url, fixture("listing_browse_downloads.html"))

    response = await client.get("/api/v1/search", params={"q": "whatsapp"})
    assert response.status_code == 200

    body = response.json()
    assert body["returned"] == 20
    assert body["per_page"] == 20
    assert body["query"]["q"] == "whatsapp"
    assert body["total_estimated"] > 20_000
    assert body["items"][0]["technical_name"]


async def test_ricerca_rispetta_il_limite(client, app_and_services, seed_cache):
    _, services = app_and_services
    await seed_cache(
        services.catalog.listing_url(q="whatsapp"), fixture("listing_browse_downloads.html")
    )

    response = await client.get("/api/v1/search", params={"q": "whatsapp", "limit": 5})
    assert response.json()["returned"] == 5


async def test_ricerca_per_autore_usa_il_filtro_upstream(client, app_and_services, seed_cache):
    _, services = app_and_services
    url = services.catalog.listing_url(author="Cybrosys Techno Solutions")
    await seed_cache(url, fixture("listing_browse_downloads.html"))

    response = await client.get("/api/v1/authors/Cybrosys Techno Solutions")
    assert response.status_code == 200
    assert response.json()["query"]["author"] == "Cybrosys Techno Solutions"


async def test_versioni(client, app_and_services, seed_cache):
    _, services = app_and_services
    await seed_cache(
        services.catalog.module_url("19.0", "web_responsive"),
        fixture("detail_web_responsive_19.html"),
    )

    response = await client.get(
        "/api/v1/modules/web_responsive/versions", params={"series": "19.0"}
    )
    assert response.status_code == 200

    body = response.json()
    assert body["technical_name"] == "web_responsive"
    assert "9.0" in body["series_available"]
    assert body["versions"][0]["series"] == "19.0"


async def test_costruzione_url_listing(app_and_services):
    _, services = app_and_services
    from app.constants import Category, Order, PriceFilter

    url = services.catalog.listing_url(
        page=2, category=Category.point_of_sale, order=Order.downloads, price=PriceFilter.free
    )
    assert "/apps/modules/category/Point%20of%20Sale/browse/page/2" in url
    assert "order=Downloads" in url
    assert "price=Free" in url


class TestSnapshot:
    def _detail(self, downloads: int) -> ModuleDetail:
        return ModuleDetail(
            technical_name="web_responsive",
            series="19.0",
            name="Web Responsive",
            url="https://apps.odoo.com/apps/modules/19.0/web_responsive",
            price=Price(is_free=True),
            rating=Rating(value=5.0, votes=31),
            downloads_total=downloads,
        )

    async def test_un_punto_al_giorno(self, app_and_services):
        _, services = app_and_services
        today = datetime.now(UTC).date()

        await services.stats.record(self._detail(100), on=today)
        await services.stats.record(self._detail(150), on=today)

        trend = await services.stats.trend("web_responsive", "19.0")
        assert len(trend.points) == 1
        assert trend.points[0].downloads_total == 150

    async def test_un_solo_punto_non_produce_delta(self, app_and_services):
        _, services = app_and_services
        await services.stats.record(self._detail(100))

        trend = await services.stats.trend("web_responsive", "19.0")
        assert trend.delta_downloads is None
        assert trend.avg_downloads_per_day is None

    async def test_delta_e_media(self, app_and_services):
        _, services = app_and_services
        today = date.today()

        await services.stats.record(self._detail(100), on=today - timedelta(days=10))
        await services.stats.record(self._detail(300), on=today)

        trend = await services.stats.trend("web_responsive", "19.0")
        assert trend.delta_downloads == 200
        assert trend.avg_downloads_per_day == 20.0
        assert trend.first_seen == today - timedelta(days=10)

    async def test_watchlist(self, client, app_and_services, seed_cache):
        _, services = app_and_services
        await seed_cache(
            services.catalog.module_url("19.0", "web_responsive"),
            fixture("detail_web_responsive_19.html"),
        )

        created = await client.post(
            "/api/v1/watchlist", json={"technical_name": "web_responsive", "series": "19.0"}
        )
        assert created.status_code == 201
        watch_id = created.json()["id"]

        listed = await client.get("/api/v1/watchlist")
        assert len(listed.json()) == 1

        assert (await client.delete(f"/api/v1/watchlist/{watch_id}")).status_code == 204
        assert (await client.delete(f"/api/v1/watchlist/{watch_id}")).status_code == 404


async def test_ricerca_deduplica_le_pagine_ripetute(client, app_and_services, seed_cache):
    """Oltre l'ultimo blocco lo store ripete i risultati invece di esaurirli."""
    _, services = app_and_services
    listing = fixture("listing_browse_downloads.html")
    for offset in range(3):
        await seed_cache(
            services.catalog.listing_url(q="mcp", page=1 + offset), listing
        )

    response = await client.get("/api/v1/search", params={"q": "mcp", "limit": 60})
    assert response.status_code == 200

    items = response.json()["items"]
    chiavi = [(i["technical_name"], i["series"]) for i in items]
    assert len(chiavi) == len(set(chiavi))
    assert len(chiavi) == 20
