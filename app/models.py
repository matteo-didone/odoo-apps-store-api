"""Modelli di risposta dell'API."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class Price(BaseModel):
    is_free: bool = True
    amount: float | None = None
    currency: str | None = Field(
        default=None, description="Codice ISO se riconosciuto, altrimenti il simbolo"
    )


class Rating(BaseModel):
    value: float | None = Field(default=None, ge=0, le=5)
    votes: int = 0
    reviews: int | None = None


class Availability(BaseModel):
    odoo_online: bool | None = None
    odoo_sh: bool | None = None
    on_premise: bool | None = None


class ModuleCard(BaseModel):
    """Modulo così come compare nelle liste di ricerca."""

    technical_name: str
    series: str
    name: str
    summary: str | None = None
    authors: list[str] = []
    price: Price = Price()
    rating: Rating = Rating()
    downloads_total: int | None = None
    downloads_last_month: int | None = None
    # I moduli a pagamento espongono gli acquisti al posto dei download.
    purchases: int | None = None
    purchases_last_month: int | None = None
    icon_url: str | None = None
    url: str


class ModuleDetail(ModuleCard):
    """Scheda completa del modulo."""

    module_id: int | None = None
    description_html: str | None = None
    license: str | None = None
    website: str | None = None
    dependencies: list[str] = []
    lines_of_code: int | None = None
    availability: Availability = Availability()
    latest_version: str | None = None
    cover_url: str | None = None
    available_series: list[str] = []
    fetched_at: datetime | None = None
    from_cache: bool = False
    stale: bool = Field(
        default=False,
        description="True se servito da cache scaduta perché l'upstream non risponde",
    )
    parse_warnings: list[str] = []


class SearchQuery(BaseModel):
    q: str | None = None
    series: str | None = None
    price: str | None = None
    category: str | None = None
    author: str | None = None
    order: str | None = None


class SearchResponse(BaseModel):
    items: list[ModuleCard]
    page: int
    per_page: int
    returned: int
    total_pages: int | None = None
    total_estimated: int | None = None
    has_next: bool = False
    query: SearchQuery
    source_urls: list[str] = []
    from_cache: bool = False
    stale: bool = False


class VersionInfo(BaseModel):
    series: str
    url: str
    version: str | None = None
    name: str | None = None
    price: Price | None = None
    downloads_total: int | None = None


class ModuleVersionsResponse(BaseModel):
    technical_name: str
    series_available: list[str]
    versions: list[VersionInfo] = []
    detailed: bool = False


class CategoryInfo(BaseModel):
    slug: str
    label: str
    url: str


class TrendPoint(BaseModel):
    date: date
    downloads_total: int | None = None
    downloads_last_month: int | None = None
    purchases: int | None = None
    rating_value: float | None = None
    rating_votes: int | None = None
    price_amount: float | None = None
    latest_version: str | None = None


class TrendResponse(BaseModel):
    technical_name: str
    series: str
    points: list[TrendPoint] = []
    first_seen: date | None = None
    last_seen: date | None = None
    delta_downloads: int | None = None
    avg_downloads_per_day: float | None = None
    note: str = (
        "Lo store non pubblica alcuno storico: i punti partono dal primo giorno in cui "
        "questa API ha letto il modulo."
    )


class WatchlistCreate(BaseModel):
    technical_name: str = Field(pattern=r"^[A-Za-z0-9_.\-]+$")
    series: str = Field(pattern=r"^(?:saas-)?\d+\.\d+$")


class WatchlistItem(BaseModel):
    id: int
    technical_name: str
    series: str
    created_at: datetime


class ModuleSource(BaseModel):
    """Modulo il cui codice è stato prelevato dal repository upstream."""

    technical_name: str
    series: str
    repo_url: str
    ref: str = Field(description="Branch del repository da cui è stato preso il codice")
    path: str
    name: str | None = None
    version: str | None = None
    license: str | None = None
    author: str | None = None
    depends: list[str] = []
    file_count: int
    bytes_extracted: int
    archive_sha256: str
    fetched_at: datetime


class SourceListResponse(BaseModel):
    items: list[ModuleSource]
    count: int
    source_dir: str


class SourceFile(BaseModel):
    path: str = Field(description="Percorso relativo alla radice del modulo")
    size: int


class SourceFilesResponse(BaseModel):
    technical_name: str
    series: str
    file_count: int
    files: list[SourceFile]


class SourceFileContent(BaseModel):
    technical_name: str
    series: str
    path: str
    size: int
    content: str
    truncated: bool = False


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    upstream: str
    cache_entries: int
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float
    snapshots: int
    watchlist: int
    sources: int = 0
    scheduler_running: bool
