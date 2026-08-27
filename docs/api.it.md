# Riferimento API

[English](api.md) · **Italiano**

Tutti gli endpoint stanno sotto `/api/v1`. Le risposte sono JSON UTF-8.
Lo schema OpenAPI generato è su `/openapi.json`, la console interattiva su `/docs`.

- [Convenzioni](#convenzioni)
- [Catalogo](#catalogo) — `search`, `modules`, `versions`, `authors`, `categories`
- [Statistiche](#statistiche) — `stats`, `watchlist`
- [Sorgenti](#sorgenti) — `sources`
- [Servizio](#servizio) — `health`
- [Errori](#errori)
- [Tipi di dato](#tipi-di-dato)

## Convenzioni

**Serie.** Ovunque compaia `{series}` vale il pattern `^(?:saas-)?\d+\.\d+$`: le serie
maggiori (`19.0` … `5.0`, incluso `6.1`) e le release online intermedie che lo store usa
negli URL (`saas-19.4`). Una serie malformata dà `422`, una serie inesistente per quel
modulo dà `404`.

**Nome tecnico.** `{technical_name}` accetta `^[A-Za-z0-9_.\-]+$`, es. `web_responsive`.

**Cache.** Le risposte che nascono da una pagina dello store portano `from_cache` e
`stale`. `stale: true` significa che l'upstream non rispondeva e si è servita una copia
scaduta: i dati sono vecchi ma utilizzabili.

**Paginazione.** Lo store serve 20 schede per pagina e non è configurabile. `page` sceglie
la pagina di partenza; `limit` può superare 20 e in quel caso il servizio legge più pagine
consecutive (fino a `ODOO_STORE_MAX_SEARCH_LIMIT`, default 100), rispettando il rate limit.

---

## Catalogo

### `GET /search`

Ricerca nel catalogo con i filtri del sito.

| Parametro | Tipo | Default | Note |
|---|---|---|---|
| `q` | string | — | testo libero |
| `series` | string | — | es. `18.0` |
| `price` | `free` \| `paid` | — | |
| `category` | slug | — | vedi [`GET /categories`](#get-categories) |
| `author` | string | — | nome esatto del publisher |
| `order` | slug | `relevance` lato store | vedi [`GET /orders`](#get-orders) |
| `page` | int ≥ 1 | `1` | pagina di partenza |
| `limit` | int 1–100 | `20` | oltre 20 legge più pagine |

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

`total_estimated` è `total_pages × 20`: è una stima, l'ultima pagina è quasi sempre
incompleta. `source_urls` elenca le pagine dello store effettivamente lette, utile per
verificare a mano cosa ha visto il servizio.

Gli elementi di `items` sono [ModuleCard](#modulecard).

### `GET /modules/{series}/{technical_name}`

Scheda completa. Restituisce un [ModuleDetail](#moduledetail).

| Parametro | Tipo | Default | Note |
|---|---|---|---|
| `refresh` | bool | `false` | ignora la cache e rilegge dall'upstream |

```bash
curl -s "http://localhost:8000/api/v1/modules/19.0/web_responsive"
```

Ogni lettura che arriva davvero dall'upstream (non da cache) registra uno snapshot dei
contatori, che alimenta [`GET /stats`](#get-statsseriestechnical_name).

### `GET /modules/{technical_name}/versions`

Su quali serie Odoo esiste il modulo. La pagina di dettaglio elenca già i collegamenti
alle altre serie, quindi la forma base costa una sola richiesta allo store.

| Parametro | Tipo | Default | Note |
|---|---|---|---|
| `series` | string | — | serie da cui partire; se omessa viene individuata con una ricerca |
| `detailed` | bool | `false` | legge ogni serie per riempire `version`, `name`, `price`, `downloads_total` |

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

Con `detailed=true` il servizio fa una richiesta per serie: su un modulo presente su
dodici serie sono dodici letture, servite a 1 rps se non sono in cache.

### `GET /authors/{author}`

Moduli di un publisher. Il nome deve essere quello esatto che compare sullo store
(`Cybrosys Techno Solutions`, non `cybrosys`). Accetta gli stessi filtri di `/search`
tranne `q`, e restituisce la stessa struttura.

```bash
curl -s "http://localhost:8000/api/v1/authors/Cybrosys%20Techno%20Solutions?limit=5"
```

### `GET /categories`

Le 18 categorie ufficiali, con lo slug da usare nel filtro `category` e l'URL sullo store.

```json
[ { "slug": "point_of_sale", "label": "Point of Sale",
    "url": "https://apps.odoo.com/apps/modules/category/Point%20of%20Sale/browse" } ]
```

### `GET /series`

Le serie maggiori filtrabili, dalla più recente. Non include le `saas-*`, che esistono
negli URL dello store ma non nel suo filtro.

### `GET /orders`

Gli slug di ordinamento accettati: `relevance`, `downloads`, `newest`, `ratings`, `name`,
`best_sellers`, `purchases`, `price_desc`, `price_asc`.

`downloads` ordina per download **dell'ultimo mese**, non per totale storico: risponde a
«cosa stanno installando adesso», non a «cosa è stato installato di più». Lo store non offre
un ordinamento su `downloads_total`, quindi per la classifica storica bisogna ordinare lato
client — escludendo prima i moduli a pagamento, che espongono `purchases` e lasciano
`downloads_total` a `null`:

```bash
curl -s "http://localhost:8000/api/v1/search?q=whatsapp&series=18.0&limit=100" \
  | jq '[.items[] | select(.downloads_total != null)] | sort_by(-.downloads_total)'
```

---

## Statistiche

Lo store pubblica solo il valore corrente dei contatori: nessuno storico, nemmeno la data
di aggiornamento di un modulo. La serie storica è quindi costruita da questa API
campionando, e **parte dal primo giorno in cui il modulo è stato letto**.

### `GET /stats/{series}/{technical_name}`

| Parametro | Tipo | Default | Note |
|---|---|---|---|
| `days` | int ≥ 1 | — | ultimi N campionamenti |
| `sample_now` | bool | `true` | legge il modulo prima di rispondere, così c'è sempre almeno un punto |

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
  "note": "Lo store non pubblica alcuno storico: …"
}
```

`delta_downloads` e `avg_downloads_per_day` restano `null` finché non ci sono almeno due
campionamenti in giorni diversi: con un punto solo un delta sarebbe zero e ingannevole.

`downloads_last_month` è sempre `null` qui, perché la pagina di dettaglio non lo riporta:
quel dato esiste solo nelle liste.

### `GET /watchlist` · `POST /watchlist` · `DELETE /watchlist/{id}`

I moduli in watchlist vengono ricampionati da un job giornaliero (default 03:00,
configurabile con `ODOO_STORE_SNAPSHOT_HOUR`). È il modo per avere una serie storica
continua senza dover interrogare a mano.

```bash
curl -s -X POST "http://localhost:8000/api/v1/watchlist" \
  -H 'Content-Type: application/json' \
  -d '{"technical_name":"web_responsive","series":"19.0"}'
```

`POST` verifica che il modulo esista davvero e registra subito il primo punto.
Ripetere la stessa coppia non crea duplicati. `DELETE` su un id inesistente dà `404`.

### `POST /watchlist/refresh`

Forza subito un giro di campionamento su tutta la watchlist, rileggendo ogni modulo
dall'upstream. Risponde `{"refreshed": N}`. Un modulo che nel frattempo è stato rimosso
dallo store viene saltato senza fermare il giro.

---

## Sorgenti

Lo store serve il download solo dietro reCAPTCHA v3, quindi non è interrogabile da un
client automatico. Il codice dei moduli **gratuiti** è però pubblico e la scheda dichiara
il repository di origine: il servizio preleva il tarball da lì, con licenza esplicita e
senza aggirare alcun controllo.

### `POST /sources/{series}/{technical_name}`

| Parametro | Tipo | Default | Note |
|---|---|---|---|
| `ref` | string | la serie stessa | branch del repository, es. `18.0` |
| `force` | bool | `false` | ripreleva anche se già presente in locale |

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

`name`, `version`, `license`, `author` e `depends` vengono dal `__manifest__.py` del
modulo, letto con `ast.literal_eval`: il codice del modulo **non** viene eseguito. Quando
il manifest non li dichiara si ricade sui valori della scheda dello store.

Senza `force`, un modulo già presente viene restituito dall'indice senza ricontattare
GitHub. Il branch usato di default è il nome della serie, che è la convenzione degli
addon Odoo; per repository che usano altri nomi c'è `ref`.

Risponde `400` quando il prelievo non è possibile: modulo a pagamento, scheda senza
repository, repository non GitHub, archivio che non supera i controlli di sicurezza.

### `GET /sources`

Moduli già prelevati. Un record il cui percorso su disco è sparito non viene elencato.

```json
{ "items": [ { "technical_name": "llm_mcp_server", "…": "…" } ], "count": 1, "source_dir": "data/modules" }
```

### `GET /sources/{series}/{technical_name}/files`

Elenco ricorsivo dei file, ordinato, con dimensione in byte.

```json
{
  "technical_name": "llm_mcp_server", "series": "18.0", "file_count": 38,
  "files": [ { "path": "README.md", "size": 10670 }, { "path": "__manifest__.py", "size": 2214 } ]
}
```

`404` se il modulo non è ancora stato prelevato.

### `GET /sources/{series}/{technical_name}/file`

| Parametro | Tipo | Note |
|---|---|---|
| `path` | string, obbligatorio | percorso relativo alla radice del modulo |

```bash
curl -s "http://localhost:8000/api/v1/sources/18.0/llm_mcp_server/file?path=__manifest__.py"
```
```json
{ "technical_name": "llm_mcp_server", "series": "18.0", "path": "__manifest__.py",
  "size": 2214, "content": "{\n    'name': 'LLM MCP Server',\n …", "truncated": false }
```

Oltre 512 KB il contenuto viene troncato e `truncated` diventa `true`; `size` resta la
dimensione reale del file. Un `path` che tenta di uscire dalla cartella del modulo dà
`400`, un file inesistente dà `404`.

---

## Servizio

### `GET /health`

```json
{
  "status": "ok", "version": "0.1.0", "upstream": "https://apps.odoo.com",
  "cache_entries": 19, "cache_hits": 2, "cache_misses": 19, "cache_hit_rate": 0.095,
  "snapshots": 10, "watchlist": 1, "sources": 1, "scheduler_running": true
}
```

I contatori `cache_hits` / `cache_misses` sono dall'avvio del processo, non persistenti.

---

## Errori

| Codice | Quando | Corpo |
|---|---|---|
| `400` | prelievo del codice non possibile (modulo a pagamento, repository assente o non GitHub, archivio rifiutato, percorso fuori dal modulo) | `{"detail": "…"}` |
| `404` | modulo o serie inesistenti sullo store, sorgente non ancora prelevata, id di watchlist inesistente | `{"detail": "…"}` |
| `422` | parametro malformato (serie, nome tecnico, valori fuori range) | formato standard FastAPI |
| `502` | apps.odoo.com o GitHub irraggiungibili, oppure markup cambiato | `{"detail": "…", "retry_after": 30}` più header `Retry-After` |

Un `502` da markup cambiato porta anche `hint`, che invita ad aggiornare i parser: è il
segnale che il sito è stato ristrutturato e i fixture di test vanno riscaricati.

Nota: se una pagina è in cache e l'upstream cade, non si riceve un `502` ma la risposta
precedente con `stale: true`.

---

## Tipi di dato

### ModuleCard

Modulo come compare nelle liste di ricerca.

| Campo | Tipo | Note |
|---|---|---|
| `technical_name` | string | es. `web_responsive` |
| `series` | string | serie della scheda |
| `name` | string | titolo commerciale |
| `summary` | string \| null | presente solo nelle liste |
| `authors` | string[] | può essere troncato dallo store con un'ellissi, che viene scartata |
| `price` | [Price](#price) | |
| `rating` | [Rating](#rating) | |
| `downloads_total` | int \| null | moduli gratuiti |
| `downloads_last_month` | int \| null | moduli gratuiti |
| `purchases` | int \| null | moduli a pagamento |
| `purchases_last_month` | int \| null | moduli a pagamento |
| `icon_url` | string \| null | icona o immagine di copertina |
| `url` | string | pagina sullo store |

Una scheda espone i download **oppure** gli acquisti, mai entrambi: lo store mostra i
primi per i moduli gratuiti e i secondi per quelli a pagamento.

### ModuleDetail

Estende `ModuleCard` con i campi della pagina di dettaglio.

| Campo | Tipo | Note |
|---|---|---|
| `module_id` | int \| null | id interno `loempia.module` |
| `description_html` | string \| null | descrizione completa, HTML |
| `license` | string \| null | es. `LGPL-3`, `OPL-1` |
| `website` | string \| null | repository dichiarato; è la fonte usata dal prelievo sorgenti |
| `dependencies` | string[] | nomi tecnici dei moduli Odoo richiesti |
| `lines_of_code` | int \| null | dipendenze incluse |
| `availability` | [Availability](#availability) | |
| `latest_version` | string \| null | es. `19.0.1.1.0`; `null` sui moduli a pagamento |
| `cover_url` | string \| null | |
| `available_series` | string[] | serie su cui il modulo esiste, dalla più recente |
| `fetched_at` | datetime | quando la pagina è stata letta |
| `from_cache` | bool | |
| `stale` | bool | copia scaduta servita perché l'upstream non rispondeva |
| `parse_warnings` | string[] | campi che il parser non ha trovato; vuoto in condizioni normali |

`summary` e `downloads_last_month`, ereditati da `ModuleCard`, sono sempre `null` qui:
la pagina di dettaglio non li riporta.

### Price

```json
{ "is_free": false, "amount": 49.0, "currency": "EUR" }
```

`currency` è il codice ISO quando il simbolo è riconosciuto (`€`, `$`, `£`, `¥`, `₹`),
altrimenti il simbolo stesso. Il microdata `priceCurrency` della pagina non è utilizzabile:
contiene un template Odoo non renderizzato.

### Rating

```json
{ "value": 5.0, "votes": 31, "reviews": 44 }
```

`value` è da 1 a 5 e può valere `.5`; è `null` se nessuno ha votato. `votes` conta i voti,
`reviews` i commenti, che sono di più perché includono le risposte dell'autore.

### Availability

```json
{ "odoo_online": false, "odoo_sh": true, "on_premise": true }
```

`null` su un campo significa che la pagina non lo dichiarava.

### ModuleSource

Vedi l'esempio in [`POST /sources`](#post-sourcesseriestechnical_name). `path` è il
percorso assoluto sul filesystem del servizio, `archive_sha256` l'impronta del tarball
scaricato: serve a capire se un nuovo prelievo ha davvero portato codice diverso.
