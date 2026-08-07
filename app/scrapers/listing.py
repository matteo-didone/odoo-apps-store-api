"""Parser delle pagine /apps/modules/browse."""

from __future__ import annotations

from dataclasses import dataclass, field

from selectolax.parser import HTMLParser, Node

from ..models import ModuleCard
from .common import (
    MODULE_HREF_RE,
    absolute_url,
    background_image_url,
    clean_text,
    max_page,
    node_text,
    parse_counter,
    parse_price_node,
    parse_rating_node,
    split_authors,
)


@dataclass(slots=True)
class ListingResult:
    cards: list[ModuleCard] = field(default_factory=list)
    total_pages: int | None = None
    warnings: list[str] = field(default_factory=list)


def parse_listing(html: str, base_url: str) -> ListingResult:
    tree = HTMLParser(html)
    result = ListingResult(total_pages=max_page(html) or 1)

    for entry in tree.css("div.loempia_app_entry"):
        card = _parse_entry(entry, base_url)
        if card is not None:
            result.cards.append(card)

    if not result.cards and "loempia_app_entry" not in html:
        result.warnings.append(
            "Nessuna scheda trovata: il markup di apps.odoo.com potrebbe essere cambiato"
        )
    return result


def _parse_entry(entry: Node, base_url: str) -> ModuleCard | None:
    link = entry.css_first("a[href]")
    if link is None:
        return None
    href = link.attributes.get("href") or ""
    match = MODULE_HREF_RE.search(href)
    if match is None:
        return None

    heading = entry.css_first("h5")
    name = clean_text(heading.attributes.get("title")) if heading is not None else None
    name = name or node_text(heading) or match.group("name")

    counters = _parse_counters(entry)

    return ModuleCard(
        technical_name=match.group("name"),
        series=match.group("series"),
        name=name,
        summary=node_text(entry.css_first("p.loempia_panel_summary")),
        authors=split_authors(node_text(entry.css_first(".loempia_panel_author"))),
        price=parse_price_node(entry.css_first(".loempia_panel_price")),
        rating=parse_rating_node(entry.css_first("span.loempia_rating_stars")),
        downloads_total=counters.get("downloads_total"),
        downloads_last_month=counters.get("downloads_last_month"),
        purchases=counters.get("purchases_total"),
        purchases_last_month=counters.get("purchases_last_month"),
        icon_url=_icon_url(entry, base_url),
        url=absolute_url(href, base_url) or href,
    )


def _parse_counters(entry: Node) -> dict[str, int | None]:
    """Una scheda mostra i download se gratuita, gli acquisti se a pagamento."""
    counters: dict[str, int | None] = {}
    for node in entry.css("span[title]"):
        kind, total, last_month = parse_counter(node.attributes.get("title"))
        if kind is None:
            continue
        counters[f"{kind}_total"] = total
        counters[f"{kind}_last_month"] = last_month
    return counters


def _icon_url(entry: Node, base_url: str) -> str | None:
    icon = entry.css_first("img.loempia_app_entry_icon")
    if icon is not None:
        return absolute_url(icon.attributes.get("src"), base_url)
    cover = entry.css_first(".loempia_app_entry_top div[style]")
    return background_image_url(cover, base_url)
