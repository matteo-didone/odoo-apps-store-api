# Odoo Apps Store API

**English** · [Italiano](README.it.md)

An **unofficial** REST API that lets you query the [Odoo Apps Store](https://apps.odoo.com/apps)
as if it had one, and pull the source code of free modules from their upstream repositories.

Odoo publishes no API for the store. This service reads the site's pages, normalizes them
into JSON, and caches them in SQLite behind a conservative rate limit.

> Independent project. Not affiliated with Odoo S.A.

```bash
curl -s "http://localhost:8000/api/v1/modules/19.0/web_responsive" | jq
```
```json
{
  "technical_name": "web_responsive",
  "series": "19.0",
  "name": "Web Responsive",
  "authors": ["LasLabs", "Tecnativa", "ITerra", "Onestein", "Odoo Community Association (OCA)"],
  "price": { "is_free": true, "amount": null, "currency": null },
  "rating": { "value": 5.0, "votes": 31, "reviews": 44 },
  "downloads_total": 39927,
  "license": "LGPL-3",
  "website": "https://github.com/OCA/web",
  "dependencies": ["mail"],
  "lines_of_code": 3403,
  "availability": { "odoo_online": false, "odoo_sh": true, "on_premise": true },
  "latest_version": "19.0.1.1.0",
  "available_series": ["19.0", "18.0", "17.0", "16.0", "15.0", "14.0", "13.0", "12.0", "11.0", "9.0"]
}
```

## What you can do with it

- **Search the catalog** using the same filters as the website (free text, series, category,
  author, free/paid, sort order) and get JSON instead of HTML.
- **Read a module's full listing**: license, dependencies, lines of code, compatibility with
  Odoo Online / Odoo.sh / On-Premise, rating, price, downloads.
- **Compare series**: which Odoo versions a module supports, at which version number and price.
- **Track downloads over time**, which the store does not allow: no history is published,
  so the service builds its own by sampling.
- **Download a free module's source** from the repository declared on its listing, read its
  manifest, and browse its files through the API.

Typical uses: monitoring your own published modules or a competitor's, evaluating a module
before installing it, checking which series an addon has already been ported to, or feeding
an internal dashboard.

## Getting started

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```
```bash
.venv/bin/uvicorn app.main:app --reload
```

- Interactive documentation (Swagger UI): <http://localhost:8000/docs>
- OpenAPI schema: <http://localhost:8000/openapi.json>
- Full endpoint reference: **[docs/api.md](docs/api.md)**

With Docker:

```bash
docker compose up --build
```

Before any real use, put a working contact address in the User-Agent — it is the least you
owe a site you are querying automatically:

```bash
cp .env.example .env
```

## Endpoints

Everything lives under `/api/v1`. Parameters and responses are covered in detail in
[docs/api.md](docs/api.md).

### Catalog

| Method | Path | Description |
|---|---|---|
| `GET` | `/search` | search with `q`, `series`, `price`, `category`, `author`, `order`, `page`, `limit` |
| `GET` | `/modules/{series}/{technical_name}` | full listing; `?refresh=true` bypasses the cache |
| `GET` | `/modules/{technical_name}/versions` | series the module exists on; `?detailed=true` adds version, price, downloads |
| `GET` | `/authors/{author}` | modules by a publisher (exact name) |
| `GET` | `/categories` · `/series` · `/orders` | accepted filter values |

### Statistics

| Method | Path | Description |
|---|---|---|
| `GET` | `/stats/{series}/{technical_name}` | counter history, with delta and daily average |
| `GET` `POST` `DELETE` | `/watchlist[/{id}]` | modules resampled automatically every day |
| `POST` | `/watchlist/refresh` | run a sampling pass right now |

### Sources

| Method | Path | Description |
|---|---|---|
| `POST` | `/sources/{series}/{technical_name}` | fetch the source; `?ref=` picks the branch, `?force=true` refetches |
| `GET` | `/sources` | modules already fetched locally |
| `GET` | `/sources/{series}/{technical_name}/files` | file listing with sizes |
| `GET` | `/sources/{series}/{technical_name}/file?path=` | contents of a single file |

### Service

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | status, cache size and hit rate, snapshot and source counts |

### Examples

The five most downloaded WhatsApp modules for Odoo 18:

```bash
curl -s "http://localhost:8000/api/v1/search?q=whatsapp&series=18.0&order=downloads&limit=5" | jq '.items[] | {technical_name, downloads_total, price}'
```

The best selling paid modules in Point of Sale:

```bash
curl -s "http://localhost:8000/api/v1/search?price=paid&category=point_of_sale&order=purchases&limit=10" | jq '.items[] | {name, purchases, price}'
```

Which series `report_xlsx` has been ported to, with version numbers:

```bash
curl -s "http://localhost:8000/api/v1/modules/report_xlsx/versions?detailed=true" | jq '.versions[] | {series, version}'
```

Fetch a free module's source and read its manifest:

```bash
curl -s -X POST "http://localhost:8000/api/v1/sources/18.0/llm_mcp_server" | jq '{repo_url, version, license, file_count, depends}'
```

### Filter values

- `series`: `19.0` through `5.0` (including `6.1`). The intermediate online releases that
  appear in store URLs are also accepted, e.g. `saas-19.4`.
- `price`: `free`, `paid`.
- `order`: `relevance`, `downloads`, `newest`, `ratings`, `name`, `best_sellers`,
  `purchases`, `price_desc`, `price_asc`.
- `category`: `accounting`, `discuss`, `document_management`, `ecommerce`, `extra_tools`,
  `human_resources`, `industries`, `localization`, `manufacturing`, `marketing`,
  `point_of_sale`, `productivity`, `project`, `purchases`, `sales`, `tutorial`,
  `warehouse`, `website`.

## How it works

```
                  ┌─ SQLite cache ─(miss)→ 1 rps rate limiter → apps.odoo.com
client → FastAPI ─┼─ daily counter snapshot → module_snapshots table
                  └─ tarball fetch → codeload.github.com → data/modules/
```

**Cache.** Every HTML page lands in SQLite. Default TTLs: listings 1 h, module pages 6 h,
static pages 24 h, 404s 15 min. If upstream goes down, the expired copy is served with
`stale: true` in the response instead of an error.

**Rate limit.** One request per second to apps.odoo.com, at most 4 in flight, with
exponential backoff on 429 and 5xx. The store's `robots.txt` disallows `?search=`, `?order=`
and `?page=` URLs for crawlers, so this API is built for targeted queries — not for crawling
the catalog's ~83,000 listings.

**Snapshots.** Every listing actually read from upstream records one data point per day
(downloads, purchases, rating, price, version). Trends therefore start the day a module is
first read: the store publishes neither history nor a module's last-updated date. For a
module you genuinely care about, add it to the watchlist and a daily job (03:00 by default)
resamples it for you.

**Sources.** The store's Download button is a JavaScript handler behind reCAPTCHA v3, so it
cannot be driven by an automated client. The source of free modules is public, though, and
each listing declares its origin repository — so the service pulls the tarball from there.
Only free modules and only GitHub repositories are supported; archives are validated member
by member (no links, no paths escaping the module directory, caps on size and compression
ratio) and extracted into a staging directory that replaces the destination only once
extraction succeeds.

## Known limits, all inherited from the source

| Field | Where it is available | Why |
|---|---|---|
| `summary` | listings only | the module page does not carry it |
| `downloads_last_month` | listings only | same |
| `purchases` | paid modules | free listings show downloads, paid ones show purchases |
| `latest_version` | free modules only | the store does not publish a paid module's version before purchase |
| `downloads_total` | per module, not per series | the same figure appears on every series |

Currency is derived from the symbol next to the price: the page's `priceCurrency` microdata
holds an unrendered Odoo template and has to be ignored.

Source fetching works only for free modules whose *Website* field points at GitHub. For
anything else the API returns `400` explaining which of the two conditions is missing.

## Configuration

Everything is overridable through `ODOO_STORE_*` environment variables or a `.env` file
(see [.env.example](.env.example)). The ones that matter most:

| Variable | Default | Purpose |
|---|---|---|
| `ODOO_STORE_USER_AGENT` | placeholder | **customize this**: identifies who is querying the store |
| `ODOO_STORE_RATE_LIMIT_RPS` | `1.0` | requests per second to apps.odoo.com |
| `ODOO_STORE_TTL_LISTING` / `_DETAIL` | `3600` / `21600` | cache freshness, in seconds |
| `ODOO_STORE_DB_PATH` | `data/store.sqlite3` | cache, snapshots, and the source index |
| `ODOO_STORE_SOURCE_DIR` | `data/modules` | where fetched source code is stored |
| `ODOO_STORE_GITHUB_TOKEN` | — | raises GitHub's rate limit from 60 to 5,000 requests/hour |
| `ODOO_STORE_ENABLE_SCHEDULER` | `true` | daily watchlist sampling job |

## Development

```bash
.venv/bin/python -m pytest
```
```bash
.venv/bin/ruff check app tests scripts
```

The parsers run against real HTML saved in `tests/fixtures/`, and source fetching against
tarballs built in memory: the suite never touches the network.

**If a parser test fails, the store's markup has most likely changed.** Refresh the fixtures
and adjust the parser to the new values:

```bash
.venv/bin/python scripts/refresh_fixtures.py
```

### Layout

```
app/
  config.py        settings (ODOO_STORE_* env vars)
  constants.py     series, categories, sort orders, currencies
  models.py        Pydantic response models
  http_client.py   rate limiter and retries for apps.odoo.com
  cache.py         SQLite cache with stale-if-error
  db.py            SQLite schema
  sources.py       GitHub client, tarball extraction, manifest reading
  scrapers/        listing.py, detail.py, common.py
  services/        catalog.py, stats.py, source.py
  routers/         modules.py, catalog.py, stats.py, sources.py
docs/api.md        full endpoint reference
tests/             parsers on real HTML, endpoints on a preloaded cache, synthetic tarballs
scripts/           refresh_fixtures.py
```

The delicate part of this project is the parsers: `app/scrapers/detail.py` prefers
schema.org microdata over the theme's CSS classes, because microdata survives the site's
restyles better. A field that cannot be found never raises — it lands in `parse_warnings`,
so the response stays usable and the problem stays visible.

## Responsible use

The data comes from public pages, and the service identifies itself through a configurable
User-Agent while throttling its own requests. Before raising `ODOO_STORE_RATE_LIMIT_RPS`,
it is worth asking whether you really need to: the cache already covers most use cases.

Source code pulled from upstream repositories remains under its authors' license, which the
service reports in the `license` field without altering it.

## License

MIT — see [LICENSE](LICENSE).
