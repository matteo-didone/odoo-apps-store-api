"""I parser girano su HTML reale salvato da apps.odoo.com.

Se un test qui fallisce dopo un aggiornamento dei fixture, il markup dello store
è cambiato: è il segnale per correggere i parser prima che l'API restituisca dati vuoti.
"""

from __future__ import annotations

from app.scrapers import parse_detail, parse_listing

from .conftest import BASE_URL, fixture


class TestListing:
    def test_estrae_venti_schede(self):
        result = parse_listing(fixture("listing_browse_downloads.html"), BASE_URL)
        assert len(result.cards) == 20
        assert not result.warnings

    def test_include_le_release_online_saas(self):
        """Lo store mescola serie maggiori e release online tipo `saas-19.4`."""
        result = parse_listing(fixture("listing_browse_downloads.html"), BASE_URL)
        saas = [card for card in result.cards if card.series.startswith("saas-")]
        assert saas, "le schede saas-* non devono essere scartate"
        assert all(card.technical_name for card in saas)

    def test_paginazione(self):
        result = parse_listing(fixture("listing_browse_downloads.html"), BASE_URL)
        assert result.total_pages is not None
        assert result.total_pages > 1000

    def test_scheda_gratuita(self):
        result = parse_listing(fixture("listing_browse_downloads.html"), BASE_URL)
        card = next(c for c in result.cards if c.technical_name == "web_responsive")

        assert card.series == "19.0"
        assert card.name == "Web Responsive"
        assert card.summary == "Responsive web client, community-supported"
        assert card.price.is_free is True
        assert card.price.amount is None
        assert card.downloads_total == 39925
        assert card.downloads_last_month == 454
        assert card.rating.value == 5.0
        assert card.rating.votes == 31
        assert "LasLabs" in card.authors
        assert "Tecnativa" in card.authors
        assert card.url == f"{BASE_URL}/apps/modules/19.0/web_responsive"

    def test_autori_troncati_senza_ellissi(self):
        result = parse_listing(fixture("listing_browse_downloads.html"), BASE_URL)
        card = next(c for c in result.cards if c.technical_name == "web_responsive")
        assert "…" not in card.authors

    def test_scheda_a_pagamento(self):
        result = parse_listing(fixture("listing_paid_18.html"), BASE_URL)
        paid = [c for c in result.cards if not c.price.is_free]

        assert paid, "la pagina filtrata price=Paid deve contenere moduli a pagamento"
        assert all(c.price.amount and c.price.amount > 0 for c in paid)
        assert all(c.price.currency == "EUR" for c in paid)

    def test_i_moduli_a_pagamento_espongono_gli_acquisti(self):
        """Nelle liste i moduli a pagamento mostrano `Total Purchases`, non i download."""
        result = parse_listing(fixture("listing_paid_18.html"), BASE_URL)
        with_purchases = [c for c in result.cards if c.purchases is not None]

        assert with_purchases
        assert all(c.downloads_total is None for c in with_purchases)
        assert all(c.purchases_last_month is not None for c in with_purchases)

    def test_icona_sempre_presente(self):
        result = parse_listing(fixture("listing_browse_downloads.html"), BASE_URL)
        assert all(card.icon_url and card.icon_url.startswith("https://") for card in result.cards)


class TestDetailFree:
    def detail(self):
        return parse_detail(
            fixture("detail_web_responsive_19.html"),
            BASE_URL,
            series="19.0",
            technical_name="web_responsive",
        )

    def test_anagrafica(self):
        detail = self.detail()
        assert detail.technical_name == "web_responsive"
        assert detail.name == "Web Responsive"
        assert detail.series == "19.0"
        assert detail.module_id == 323217
        assert detail.latest_version == "19.0.1.1.0"
        assert not detail.parse_warnings

    def test_autori(self):
        detail = self.detail()
        assert detail.authors[:2] == ["LasLabs", "Tecnativa"]
        assert "Odoo Community Association (OCA)" in detail.authors
        assert len(detail.authors) == len(set(detail.authors))

    def test_prezzo_e_rating(self):
        detail = self.detail()
        assert detail.price.is_free is True
        assert detail.rating.value == 5.0
        assert detail.rating.votes == 31
        assert detail.rating.reviews == 44

    def test_informazioni_tecniche(self):
        detail = self.detail()
        assert detail.license == "LGPL-3"
        assert detail.website == "https://github.com/OCA/web"
        assert detail.dependencies == ["mail"]
        assert detail.lines_of_code == 3403
        assert detail.downloads_total == 39925

    def test_disponibilita(self):
        detail = self.detail()
        assert detail.availability.odoo_online is False
        assert detail.availability.odoo_sh is True
        assert detail.availability.on_premise is True

    def test_serie_disponibili(self):
        detail = self.detail()
        assert detail.available_series[0] == "19.0"
        assert "9.0" in detail.available_series
        assert detail.available_series == sorted(
            detail.available_series, key=lambda s: [int(p) for p in s.split(".")], reverse=True
        )

    def test_descrizione(self):
        detail = self.detail()
        assert detail.description_html
        assert "web_responsive" in detail.description_html


class TestDetailPaid:
    def detail(self):
        return parse_detail(
            fixture("detail_common_connector_library_18.html"),
            BASE_URL,
            series="18.0",
            technical_name="common_connector_library",
        )

    def test_prezzo(self):
        detail = self.detail()
        assert detail.price.is_free is False
        assert detail.price.amount == 49.0
        assert detail.price.currency == "EUR"

    def test_acquisti_e_id(self):
        detail = self.detail()
        assert detail.module_id == 212895
        assert detail.purchases and detail.purchases > 0

    def test_copertina(self):
        detail = self.detail()
        assert detail.cover_url and detail.cover_url.startswith("https://")
