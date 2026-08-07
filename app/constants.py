"""Valori accettati dallo store, esposti come enum per validazione e OpenAPI."""

from enum import StrEnum

# Lo store espone anche le release online intermedie (`saas-19.4`) negli URL dei
# moduli, pur non offrendole nel filtro `series`: i parametri di serie accettano
# quindi sia `18.0` sia `saas-19.4`.
SERIES_PATTERN = r"^(?:saas-)?\d+\.\d+$"

# Serie maggiori filtrabili sullo store, dalla più recente alla più vecchia.
SERIES: tuple[str, ...] = (
    "19.0",
    "18.0",
    "17.0",
    "16.0",
    "15.0",
    "14.0",
    "13.0",
    "12.0",
    "11.0",
    "10.0",
    "9.0",
    "8.0",
    "7.0",
    "6.1",
    "6.0",
    "5.0",
)


class PriceFilter(StrEnum):
    free = "free"
    paid = "paid"

    @property
    def upstream(self) -> str:
        return "Free" if self is PriceFilter.free else "Paid"


class Order(StrEnum):
    """Slug amichevoli mappati sui valori attesi da apps.odoo.com."""

    relevance = "relevance"
    downloads = "downloads"
    newest = "newest"
    ratings = "ratings"
    name = "name"
    best_sellers = "best_sellers"
    purchases = "purchases"
    price_desc = "price_desc"
    price_asc = "price_asc"

    @property
    def upstream(self) -> str:
        return _ORDER_UPSTREAM[self.value]


_ORDER_UPSTREAM = {
    "relevance": "Relevance",
    "downloads": "Downloads",
    "newest": "Newest",
    "ratings": "Ratings",
    "name": "Name",
    "best_sellers": "Best Sellers",
    "purchases": "Purchases",
    "price_desc": "Highest Price",
    "price_asc": "Lowest Price",
}


# Categorie ufficiali: slug usato dall'API -> etichetta esatta usata nell'URL dello store.
CATEGORY_LABELS: dict[str, str] = {
    "accounting": "Accounting",
    "discuss": "Discuss",
    "document_management": "Document Management",
    "ecommerce": "eCommerce",
    "extra_tools": "Extra Tools",
    "human_resources": "Human Resources",
    "industries": "Industries",
    "localization": "Localization",
    "manufacturing": "Manufacturing",
    "marketing": "Marketing",
    "point_of_sale": "Point of Sale",
    "productivity": "Productivity",
    "project": "Project",
    "purchases": "Purchases",
    "sales": "Sales",
    "tutorial": "Tutorial",
    "warehouse": "Warehouse",
    "website": "Website",
}


class Category(StrEnum):
    accounting = "accounting"
    discuss = "discuss"
    document_management = "document_management"
    ecommerce = "ecommerce"
    extra_tools = "extra_tools"
    human_resources = "human_resources"
    industries = "industries"
    localization = "localization"
    manufacturing = "manufacturing"
    marketing = "marketing"
    point_of_sale = "point_of_sale"
    productivity = "productivity"
    project = "project"
    purchases = "purchases"
    sales = "sales"
    tutorial = "tutorial"
    warehouse = "warehouse"
    website = "website"

    @property
    def label(self) -> str:
        return CATEGORY_LABELS[self.value]


# Simboli di valuta visti sullo store, per ricostruire il codice ISO
# (il microdata priceCurrency della pagina è un template non renderizzato e va ignorato).
CURRENCY_SYMBOLS: dict[str, str] = {
    "€": "EUR",
    "$": "USD",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "CHF": "CHF",
}
