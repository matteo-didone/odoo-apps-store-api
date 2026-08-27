# API reference

**English** · [Italiano](api.it.md)

Every endpoint lives under `/api/v1`. Responses are UTF-8 JSON.
The generated OpenAPI schema is at `/openapi.json`, the interactive console at `/docs`.

- [Conventions](#conventions)
- [Catalog](#catalog) — `search`, `modules`, `versions`, `authors`, `categories`
- [Statistics](#statistics) — `stats`, `watchlist`
- [Sources](#sources) — `sources`
- [Service](#service) — `health`
- [Errors](#errors)
- [Data types](#data-types)

## Conventions

**Series.** Wherever `{series}` appears, the pattern is `^(?:saas-)?\d+\.\d+$`: the major
series (`19.0` through `5.0`, including `6.1`) plus the intermediate online releases the
store uses in its URLs (`saas-19.4`). A malformed series returns `422`; a series that does
not exist for that module returns `404`.

**Technical name.** `{technical_name}` accepts `^[A-Za-z0-9_.\-]+$`, e.g. `web_responsive`.

**Cache.** Responses derived from a store page carry `from_cache` and `stale`.
`stale: true` means upstream was unreachable and an expired copy was served: the data is
old but usable.

**Pagination.** The store serves 20 listings per page and that is not configurable. `page`
picks the starting page; `limit` may exceed 20, in which case the service reads consecutive
pages (up to `ODOO_STORE_MAX_SEARCH_LIMIT`, 100 by default) while respecting the rate limit.

---

## Catalog

### `GET /search`

Search the catalog using the site's own filters.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `q` | string | — | free text |
| `series` | string | — | e.g. `18.0` |
| `price` | `free` \| `paid` | — | |
| `category` | slug | — | see [`GET /categories`](#get-categories) |
| `author` | string | — | exact publisher name |
| `order` | slug | store-side `relevance` | see [`GET /orders`](#get-orders) |
| `page` | int ≥ 1 | `1` | starting page |
| `limit` | int 1–100 | `20` | above 20, reads multiple pages |

```bash
curl -s "http://localhost:8000/api/v1/search?q=whatsapp&series=18.0&order=downloads&limit=3"
```
```json
{
  "items": [ { "technical_name": "odoo_whatsapp_integration", "series": "18.0", "…": "…" } ],
  "page": 1,
  "per_page": 20,
  "returned": 3,
  "total_pages": 23,
  "total_estimated": 460,
  "has_next": true,
  "query": { "q": "whatsapp", "series": "18.0", "price": null, "category": null, "author": null, "order": "downloads" },
  "source_urls": ["https://apps.odoo.com/apps/modules/browse?search=whatsapp&order=Downloads&series=18.0"],
  "from_cache": false,
  "stale": false
}
```

`total_estimated` is `total_pages × 20`: an estimate, since the last page is almost always
partial. `source_urls` lists the store pages actually read, which is handy for checking by
hand what the service saw.

Items in `items` are [ModuleCard](#modulecard) objects.

### `GET /modules/{series}/{technical_name}`

The full listing. Returns a [ModuleDetail](#moduledetail).

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `refresh` | bool | `false` | ignore the cache and re-read from upstream |

```bash
curl -s "http://localhost:8000/api/v1/modules/19.0/web_responsive"
```

Every read that genuinely comes from upstream (not from cache) records a counter snapshot,
which is what feeds [`GET /stats`](#get-statsseriestechnical_name).

### `GET /modules/{technical_name}/versions`

Which Odoo series the module exists on. The module page already links to its other series,
so the basic form costs a single request to the store.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `series` | string | — | series to start from; if omitted it is discovered with a search |
| `detailed` | bool | `false` | reads every series to fill in `version`, `name`, `price`, `downloads_total` |

```bash
curl -s "http://localhost:8000/api/v1/modules/report_xlsx/versions?detailed=true"
```
```json
{
  "technical_name": "report_xlsx",
  "series_available": ["19.0", "18.0", "17.0", "16.0", "15.0"],
  "versions": [
    { "series": "19.0", "url": "https://apps.odoo.com/apps/modules/19.0/report_xlsx",
      "version": "19.0.1.0.2", "name": "Base report xlsx",
      "price": { "is_free": true, "amount": null, "currency": null },
      "downloads_total": 36850 }
  ],
  "detailed": true
}
```

With `detailed=true` the service makes one request per series: for a module present on
twelve series that is twelve reads, served at 1 rps when they are not already cached.

### `GET /authors/{author}`

Modules by a publisher. The name must match the store exactly (`Cybrosys Techno Solutions`,
not `cybrosys`). It accepts the same filters as `/search` except `q`, and returns the same
structure.

```bash
curl -s "http://localhost:8000/api/v1/authors/Cybrosys%20Techno%20Solutions?limit=5"
```

### `GET /categories`

The 18 official categories, with the slug to use in the `category` filter and the store URL.

```json
[ { "slug": "point_of_sale", "label": "Point of Sale",
    "url": "https://apps.odoo.com/apps/modules/category/Point%20of%20Sale/browse" } ]
```

### `GET /series`

The major filterable series, newest first. It excludes the `saas-*` releases, which exist in
store URLs but not in its filter.

### `GET /orders`

The accepted sort slugs: `relevance`, `downloads`, `newest`, `ratings`, `name`,
`best_sellers`, `purchases`, `price_desc`, `price_asc`.

`downloads` sorts by downloads **in the last month**, not by the lifetime total: it answers
"what are people installing now", not "what has been installed the most". The store offers no
sort on `downloads_total`, so ranking by lifetime downloads means sorting client-side — and
filtering out the paid modules first, since they carry `purchases` and leave `downloads_total`
at `null`:

```bash
curl -s "http://localhost:8000/api/v1/search?q=whatsapp&series=18.0&limit=100" \
  | jq '[.items[] | select(.downloads_total != null)] | sort_by(-.downloads_total)'
```

---

## Statistics

The store publishes only the current value of its counters: no history, not even a module's
last-updated date. The time series is therefore built by this API through sampling, and
**starts the day the module was first read**.

### `GET /stats/{series}/{technical_name}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `days` | int ≥ 1 | — | last N samples |
| `sample_now` | bool | `true` | reads the module before answering, so there is always at least one point |

```json
{
  "technical_name": "web_responsive",
  "series": "19.0",
  "points": [
    { "date": "2026-08-07", "downloads_total": 39927, "downloads_last_month": null,
      "purchases": null, "rating_value": 5.0, "rating_votes": 31,
      "price_amount": null, "latest_version": "19.0.1.1.0" }
  ],
  "first_seen": "2026-08-07",
  "last_seen": "2026-08-07",
  "delta_downloads": null,
  "avg_downloads_per_day": null,
  "note": "The store publishes no history: these points start …"
}
```

`delta_downloads` and `avg_downloads_per_day` stay `null` until there are at least two
samples on different days: with a single point a delta would be zero and misleading.

`downloads_last_month` is always `null` here, because the module page does not carry it —
that figure exists only in listings.

### `GET /watchlist` · `POST /watchlist` · `DELETE /watchlist/{id}`

Watchlisted modules are resampled by a daily job (03:00 by default, configurable through
`ODOO_STORE_SNAPSHOT_HOUR`). This is how you get a continuous time series without polling
by hand.

```bash
curl -s -X POST "http://localhost:8000/api/v1/watchlist" \
  -H 'Content-Type: application/json' \
  -d '{"technical_name":"web_responsive","series":"19.0"}'
```

`POST` verifies the module actually exists and records the first data point immediately.
Repeating the same pair creates no duplicate. `DELETE` on an unknown id returns `404`.

### `POST /watchlist/refresh`

Runs a sampling pass over the whole watchlist right now, re-reading each module from
upstream. Responds with `{"refreshed": N}`. A module that has since been pulled from the
store is skipped without aborting the pass.

---

## Sources

The store serves downloads only behind reCAPTCHA v3, so they cannot be driven by an
automated client. The source of **free** modules is public, though, and each listing
declares its origin repository: the service pulls the tarball from there, under an explicit
license and without circumventing any control.

### `POST /sources/{series}/{technical_name}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `ref` | string | the series itself | repository branch, e.g. `18.0` |
| `force` | bool | `false` | refetch even if already present locally |

```bash
curl -s -X POST "http://localhost:8000/api/v1/sources/18.0/llm_mcp_server"
```
```json
{
  "technical_name": "llm_mcp_server",
  "series": "18.0",
  "repo_url": "https://github.com/apexive/odoo-llm",
  "ref": "18.0",
  "path": "/srv/data/modules/18.0/llm_mcp_server",
  "name": "LLM MCP Server",
  "version": "18.0.1.3.2",
  "license": "LGPL-3",
  "author": "Apexive Solutions LLC",
  "depends": ["base", "llm", "llm_tool", "web_json_editor"],
  "file_count": 38,
  "bytes_extracted": 1481614,
  "archive_sha256": "29885b008482a5f8ee0609af8c5da08160a2dbbcf24f8c202c14ceff7c94579e",
  "fetched_at": "2026-08-07T14:06:53.042640Z"
}
```

`name`, `version`, `license`, `author`, and `depends` come from the module's
`__manifest__.py`, read with `ast.literal_eval`: the module's code is **not** executed.
When the manifest omits them, the store listing's values are used instead.

Without `force`, a module already on disk is returned from the index without contacting
GitHub again. The default branch is the series name, which is the Odoo addon convention;
`ref` covers repositories that use different names.

Returns `400` when the fetch is not possible: paid module, listing without a repository,
non-GitHub repository, or an archive that fails the safety checks.

### `GET /sources`

Modules already fetched. A record whose directory has disappeared from disk is not listed.

```json
{ "items": [ { "technical_name": "llm_mcp_server", "…": "…" } ], "count": 1, "source_dir": "data/modules" }
```

### `GET /sources/{series}/{technical_name}/files`

Recursive, sorted file listing with sizes in bytes.

```json
{
  "technical_name": "llm_mcp_server", "series": "18.0", "file_count": 38,
  "files": [ { "path": "README.md", "size": 10670 }, { "path": "__manifest__.py", "size": 2214 } ]
}
```

`404` if the module has not been fetched yet.

### `GET /sources/{series}/{technical_name}/file`

| Parameter | Type | Notes |
|---|---|---|
| `path` | string, required | path relative to the module root |

```bash
curl -s "http://localhost:8000/api/v1/sources/18.0/llm_mcp_server/file?path=__manifest__.py"
```
```json
{ "technical_name": "llm_mcp_server", "series": "18.0", "path": "__manifest__.py",
  "size": 2214, "content": "{\n    'name': 'LLM MCP Server',\n …", "truncated": false }
```

Past 512 KB the content is truncated and `truncated` becomes `true`; `size` remains the
file's real size. A `path` that tries to escape the module directory returns `400`, a
missing file returns `404`.

---

## Service

### `GET /health`

```json
{
  "status": "ok", "version": "0.1.0", "upstream": "https://apps.odoo.com",
  "cache_entries": 19, "cache_hits": 2, "cache_misses": 19, "cache_hit_rate": 0.095,
  "snapshots": 10, "watchlist": 1, "sources": 1, "scheduler_running": true
}
```

`cache_hits` and `cache_misses` count from process start; they are not persisted.

---

## Errors

| Code | When | Body |
|---|---|---|
| `400` | source fetch not possible (paid module, missing or non-GitHub repository, rejected archive, path outside the module) | `{"detail": "…"}` |
| `404` | module or series not on the store, source not fetched yet, unknown watchlist id | `{"detail": "…"}` |
| `422` | malformed parameter (series, technical name, out-of-range values) | standard FastAPI format |
| `502` | apps.odoo.com or GitHub unreachable, or markup changed | `{"detail": "…", "retry_after": 30}` plus a `Retry-After` header |

A `502` caused by changed markup also carries `hint`, suggesting the parsers be updated:
that is the signal that the site was restructured and the test fixtures need refreshing.

Note: if a page is cached and upstream goes down, you do not get a `502` — you get the
previous response with `stale: true`.

---

## Data types

### ModuleCard

A module as it appears in search listings.

| Field | Type | Notes |
|---|---|---|
| `technical_name` | string | e.g. `web_responsive` |
| `series` | string | the listing's series |
| `name` | string | display name |
| `summary` | string \| null | present in listings only |
| `authors` | string[] | the store may truncate this with an ellipsis, which is discarded |
| `price` | [Price](#price) | |
| `rating` | [Rating](#rating) | |
| `downloads_total` | int \| null | free modules |
| `downloads_last_month` | int \| null | free modules |
| `purchases` | int \| null | paid modules |
| `purchases_last_month` | int \| null | paid modules |
| `icon_url` | string \| null | icon or cover image |
| `url` | string | page on the store |

A listing exposes downloads **or** purchases, never both: the store shows the former for
free modules and the latter for paid ones.

### ModuleDetail

Extends `ModuleCard` with the fields from the module page.

| Field | Type | Notes |
|---|---|---|
| `module_id` | int \| null | internal `loempia.module` id |
| `description_html` | string \| null | full description, as HTML |
| `license` | string \| null | e.g. `LGPL-3`, `OPL-1` |
| `website` | string \| null | declared repository; this is what source fetching uses |
| `dependencies` | string[] | technical names of the required Odoo modules |
| `lines_of_code` | int \| null | dependencies included |
| `availability` | [Availability](#availability) | |
| `latest_version` | string \| null | e.g. `19.0.1.1.0`; `null` for paid modules |
| `cover_url` | string \| null | |
| `available_series` | string[] | series the module exists on, newest first |
| `fetched_at` | datetime | when the page was read |
| `from_cache` | bool | |
| `stale` | bool | expired copy served because upstream was unreachable |
| `parse_warnings` | string[] | fields the parser could not find; empty under normal conditions |

`summary` and `downloads_last_month`, inherited from `ModuleCard`, are always `null` here:
the module page does not carry them.

### Price

```json
{ "is_free": false, "amount": 49.0, "currency": "EUR" }
```

`currency` is the ISO code when the symbol is recognized (`€`, `$`, `£`, `¥`, `₹`), and the
raw symbol otherwise. The page's `priceCurrency` microdata is unusable: it contains an
unrendered Odoo template.

### Rating

```json
{ "value": 5.0, "votes": 31, "reviews": 44 }
```

`value` ranges from 1 to 5 and can end in `.5`; it is `null` when nobody has voted. `votes`
counts ratings and `reviews` counts comments, which is higher because it includes the
author's replies.

### Availability

```json
{ "odoo_online": false, "odoo_sh": true, "on_premise": true }
```

A `null` field means the page did not state it.

### ModuleSource

See the example under [`POST /sources`](#post-sourcesseriestechnical_name). `path` is the
absolute path on the service's filesystem, and `archive_sha256` is the fingerprint of the
downloaded tarball: useful for telling whether a refetch actually brought different code.
