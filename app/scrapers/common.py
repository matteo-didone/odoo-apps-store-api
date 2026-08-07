"""Helper condivisi dai parser: numeri, prezzi, rating, URL."""

from __future__ import annotations

import re
from html import unescape

from selectolax.parser import Node

from ..constants import CURRENCY_SYMBOLS
from ..models import Price, Rating

# Oltre alle serie maggiori lo store pubblica le release online intermedie
# (`saas-19.4`), che compaiono negli URL ma non nel filtro `series`.
SERIES_RE = r"(?:saas-)?\d+\.\d+"
MODULE_HREF_RE = re.compile(
    rf"/apps/modules/(?P<series>{SERIES_RE})/(?P<name>[A-Za-z0-9_.\-]+)"
)
# Le schede mostrano i download per i moduli gratuiti e gli acquisti per quelli a pagamento.
COUNTER_TITLE_RE = re.compile(
    r"Total\s+(?P<kind>Downloads|Purchases):\s*(?P<total>[\d.,\s]+?)\s*,"
    r"\s*Last month:\s*(?P<last_month>[\d.,\s]+)",
    re.I,
)
VOTES_RE = re.compile(r"(\d+)\s*vote", re.I)
BACKGROUND_URL_RE = re.compile(r"url\(\s*['\"]?(?P<url>[^'\")]+)['\"]?\s*\)")
PAGE_RE = re.compile(r"/page/(\d+)")


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = re.sub(r"\s+", " ", unescape(value)).strip()
    return collapsed or None


def node_text(node: Node | None) -> str | None:
    if node is None:
        return None
    return clean_text(node.text(deep=True, separator=" "))


def to_int(value: str | None) -> int | None:
    """Interi come '39.925', '39,925' o '39 925' arrivano tutti a 39925."""
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def to_float(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", value)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def absolute_url(url: str | None, base_url: str) -> str | None:
    """Normalizza gli href relativi e i protocol-relative del CDN Odoo."""
    if not url:
        return None
    url = unescape(url.strip())
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        return f"{base_url.rstrip('/')}{url}"
    return f"{base_url.rstrip('/')}/{url}"


def background_image_url(node: Node | None, base_url: str) -> str | None:
    if node is None:
        return None
    style = node.attributes.get("style") or ""
    match = BACKGROUND_URL_RE.search(style)
    return absolute_url(match.group("url"), base_url) if match else None


def parse_counter(title: str | None) -> tuple[str | None, int | None, int | None]:
    """Legge 'Total Downloads: X, Last month: Y' (o la variante Purchases).

    Restituisce (`downloads`|`purchases`, totale, ultimo mese).
    """
    if not title:
        return None, None, None
    match = COUNTER_TITLE_RE.search(unescape(title))
    if not match:
        return None, None, None
    kind = "purchases" if match.group("kind").lower() == "purchases" else "downloads"
    return kind, to_int(match.group("total")), to_int(match.group("last_month"))


def parse_price_node(node: Node | None) -> Price:
    """Il blocco prezzo vale 'FREE' oppure un `span.oe_currency_value` più il simbolo."""
    if node is None:
        return Price(is_free=True)

    amount_node = node.css_first("span.oe_currency_value")
    if amount_node is None:
        return Price(is_free=True)

    raw_amount = node_text(amount_node)
    amount = to_float(raw_amount)
    if amount is None:
        return Price(is_free=True)

    full_text = node_text(node) or ""
    symbol = full_text.replace(raw_amount or "", "").strip()
    return Price(is_free=amount == 0, amount=amount, currency=normalize_currency(symbol))


def normalize_currency(symbol: str | None) -> str | None:
    if not symbol:
        return None
    symbol = symbol.strip()
    for candidate, iso in CURRENCY_SYMBOLS.items():
        if candidate in symbol:
            return iso
    return symbol or None


def parse_rating_node(node: Node | None) -> Rating:
    """Ricostruisce il voto dal numero di stelle piene/mezze e dal tooltip dei voti."""
    if node is None:
        return Rating()

    value = 0.0
    seen_star = False
    for star in node.css("span"):
        classes = set((star.attributes.get("class") or "").split())
        if "fa-star" in classes:
            value += 1.0
            seen_star = True
        elif "fa-star-half-o" in classes or "fa-star-half" in classes:
            value += 0.5
            seen_star = True
        elif "fa-star-o" in classes:
            seen_star = True

    votes_match = VOTES_RE.search(unescape(node.attributes.get("title") or ""))
    votes = int(votes_match.group(1)) if votes_match else 0

    return Rating(value=value if seen_star else None, votes=votes)


def split_authors(raw: str | None) -> list[str]:
    """Le liste autori arrivano come 'A, B, …' con ellissi quando sono troncate."""
    if not raw:
        return []
    parts = [clean_text(part) for part in raw.split(",")]
    return [part for part in parts if part and part not in {"…", "...", "..", "."}]


def max_page(html: str) -> int | None:
    """L'ultimo numero nel paginatore è la miglior stima del totale pagine."""
    pages = [int(match) for match in PAGE_RE.findall(html)]
    return max(pages) if pages else None
