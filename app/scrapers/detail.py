"""Parser della pagina /apps/modules/<serie>/<nome_tecnico>.

Strategia: microdata schema.org quando disponibile (più stabile delle classi CSS
del tema), classi come fallback. Un campo mancante non è mai un'eccezione: finisce
in `parse_warnings` così un cambio di markup si nota subito.
"""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser, Node

from ..models import Availability, ModuleDetail, Price, Rating
from .common import (
    SERIES_RE,
    absolute_url,
    background_image_url,
    clean_text,
    node_text,
    normalize_currency,
    to_float,
    to_int,
)

ODOO_SH_VERSION_RE = re.compile(r"/loempia/download/odoo-sh/[^/]+/([\w.\-+]+)")
DEPENDENCY_TECHNICAL_RE = re.compile(r"\(([A-Za-z0-9_.\-]+)\)\s*$")
SERIES_IN_HREF_TEMPLATE = rf"/apps/modules/({SERIES_RE})/{{name}}(?=[\"'?#]|$)"

AVAILABILITY_LABELS = {
    "odoo online": "odoo_online",
    "odoo.sh": "odoo_sh",
    "on premise": "on_premise",
}


def parse_detail(
    html: str,
    base_url: str,
    *,
    series: str | None = None,
    technical_name: str | None = None,
) -> ModuleDetail:
    tree = HTMLParser(html)
    warnings: list[str] = []

    info = _parse_technical_table(tree, warnings)

    resolved_name = info.get("technical_name") or technical_name
    if not resolved_name:
        warnings.append("Nome tecnico non trovato nella pagina")
        resolved_name = ""

    resolved_series = _parse_series(tree) or series
    if not resolved_series:
        warnings.append("Serie Odoo non trovata nella pagina")
        resolved_series = series or ""

    title = tree.css_first('h1[itemprop="name"]')
    name = node_text(title)
    if not name:
        warnings.append("Titolo del modulo non trovato")
        name = resolved_name

    downloads_total = _counter(tree, "Downloads")
    purchases = _counter(tree, "Purchases")

    return ModuleDetail(
        technical_name=resolved_name,
        series=resolved_series,
        name=name,
        summary=None,  # lo store espone il summary solo nelle liste, non nel dettaglio
        authors=_parse_authors(tree),
        price=_parse_price(tree),
        rating=_parse_rating(tree),
        downloads_total=downloads_total,
        downloads_last_month=None,  # idem: dato presente solo nelle liste
        purchases=purchases,
        icon_url=_parse_icon(tree, base_url),
        cover_url=background_image_url(tree.css_first("div.loempia_app_cover"), base_url),
        url=f"{base_url.rstrip('/')}/apps/modules/{resolved_series}/{resolved_name}",
        module_id=_parse_module_id(tree),
        description_html=_parse_description(tree),
        license=info.get("license"),
        website=info.get("website"),
        dependencies=info.get("dependencies", []),
        lines_of_code=info.get("lines_of_code"),
        availability=info.get("availability", Availability()),
        latest_version=_parse_latest_version(html),
        available_series=_parse_available_series(html, resolved_name, resolved_series),
        parse_warnings=warnings,
    )


def _parse_authors(tree: HTMLParser) -> list[str]:
    authors = [
        node_text(node)
        for node in tree.css('span[itemprop="author"] span[itemprop="name"]')
    ]
    seen: list[str] = []
    for author in authors:
        if author and author not in seen:
            seen.append(author)
    return seen


def _parse_price(tree: HTMLParser) -> Price:
    amount: float | None = None

    meta = tree.css_first('meta[itemprop="price"]')
    if meta is not None:
        amount = to_float(meta.attributes.get("content"))

    if amount is None:
        hidden = tree.css_first("input.js_product_price")
        if hidden is not None:
            amount = to_float(hidden.attributes.get("value"))

    if amount is None or amount == 0:
        return Price(is_free=True)

    # `priceCurrency` nel microdata è un template non renderizzato: la valuta
    # va letta dal simbolo accanto all'importo.
    currency = None
    value_node = tree.css_first("span.oe_currency_value")
    if value_node is not None and value_node.parent is not None:
        raw_value = node_text(value_node) or ""
        symbol = (node_text(value_node.parent) or "").replace(raw_value, "").strip()
        currency = normalize_currency(symbol)

    return Price(is_free=False, amount=amount, currency=currency)


def _parse_rating(tree: HTMLParser) -> Rating:
    def meta_value(prop: str) -> str | None:
        node = tree.css_first(f'meta[itemprop="{prop}"]')
        return node.attributes.get("content") if node is not None else None

    value = to_float(meta_value("ratingValue"))
    votes = to_int(meta_value("ratingCount")) or 0
    reviews = to_int(meta_value("reviewCount"))
    return Rating(value=value, votes=votes, reviews=reviews)


def _parse_icon(tree: HTMLParser, base_url: str) -> str | None:
    icon = tree.css_first('img[itemprop="image"]')
    if icon is not None:
        return absolute_url(icon.attributes.get("src"), base_url)
    og = tree.css_first('meta[property="og:image"]')
    return absolute_url(og.attributes.get("content"), base_url) if og is not None else None


def _parse_module_id(tree: HTMLParser) -> int | None:
    for selector in ("input.js_module_id", 'input[name="module_id"]'):
        node = tree.css_first(selector)
        if node is not None:
            module_id = to_int(node.attributes.get("value"))
            if module_id:
                return module_id
    return None


def _parse_series(tree: HTMLParser) -> str | None:
    node = tree.css_first('[itemprop="softwareVersion"]')
    text = node_text(node)
    if not text:
        return None
    match = re.search(rf"({SERIES_RE})", text)
    return match.group(1) if match else None


def _parse_latest_version(html: str) -> str | None:
    match = ODOO_SH_VERSION_RE.search(html)
    return match.group(1) if match else None


def _parse_description(tree: HTMLParser) -> str | None:
    for selector in ("div#desc", "#module-description"):
        node = tree.css_first(selector)
        if node is not None:
            inner = node.html
            if inner:
                return inner.strip()
    return None


def _counter(tree: HTMLParser, label: str) -> int | None:
    """I contatori del pannello sono `<span title="Downloads"><i/> 39925</span>`."""
    for node in tree.css(f'span[title="{label}"]'):
        value = to_int(node_text(node))
        if value is not None:
            return value
    return None


def _parse_available_series(html: str, technical_name: str, current: str) -> list[str]:
    if not technical_name:
        return [current] if current else []
    pattern = re.compile(SERIES_IN_HREF_TEMPLATE.format(name=re.escape(technical_name)))
    found = {match for match in pattern.findall(html)}
    if current:
        found.add(current)
    return sorted(found, key=_series_sort_key, reverse=True)


def _series_sort_key(series: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in series.removeprefix("saas-").split("."))
    except ValueError:
        return (0,)


def _parse_technical_table(tree: HTMLParser, warnings: list[str]) -> dict:
    table = tree.css_first("#technical_info")
    if table is None:
        warnings.append("Tabella delle informazioni tecniche non trovata")
        return {}

    info: dict = {"dependencies": [], "availability": Availability()}

    for row in table.css("tr"):
        cells = row.css("td")
        if len(cells) < 2:
            continue
        key = (node_text(cells[0]) or "").lower()
        value_cell = cells[1]

        if key.startswith("technical name"):
            info["technical_name"] = node_text(value_cell)
        elif key.startswith("license"):
            info["license"] = node_text(value_cell)
        elif key.startswith("website"):
            link = value_cell.css_first("a[href]")
            info["website"] = (
                link.attributes.get("href") if link is not None else node_text(value_cell)
            )
        elif key.startswith("odoo apps dependencies"):
            info["dependencies"] = _parse_dependencies(value_cell)
        elif key.startswith("lines of code"):
            info["lines_of_code"] = to_int(node_text(value_cell))
        elif key.startswith("availability"):
            info["availability"] = _parse_availability(value_cell)

    return info


def _parse_dependencies(cell: Node) -> list[str]:
    """'Discuss (mail)' -> 'mail'; se manca la parentesi si tiene l'etichetta."""
    dependencies: list[str] = []
    for span in cell.css("span"):
        label = node_text(span)
        if not label:
            continue
        match = DEPENDENCY_TECHNICAL_RE.search(label)
        dependency = match.group(1) if match else label
        if dependency not in dependencies:
            dependencies.append(dependency)
    return dependencies


def _parse_availability(cell: Node) -> Availability:
    availability = Availability()
    # Solo i div foglia: quello contenitore ripete tutte e tre le etichette.
    # `css()` di selectolax include il nodo stesso, quindi un solo match = foglia.
    for block in cell.css("div"):
        if len(block.css("div")) > 1:
            continue
        label = (clean_text(block.text(deep=True, separator=" ")) or "").lower()
        field = next((f for text, f in AVAILABILITY_LABELS.items() if text in label), None)
        if field is None or getattr(availability, field) is not None:
            continue
        icon = block.css_first("i")
        classes = set((icon.attributes.get("class") or "").split()) if icon is not None else set()
        if "fa-check" in classes:
            setattr(availability, field, True)
        elif "fa-times" in classes:
            setattr(availability, field, False)
    return availability
