# Odoo Apps Store API

[English](README.md) · **Italiano**

API REST **non ufficiale** per interrogare l'[Odoo Apps Store](https://apps.odoo.com/apps)
come se avesse un'API, e per prelevare il codice dei moduli gratuiti dal loro repository.

Odoo non pubblica alcuna API per lo store. Questo servizio legge le pagine del sito,
le normalizza in JSON e le tiene in cache su SQLite, con un rate limit conservativo
verso l'upstream.

> Progetto indipendente. Nessuna affiliazione con Odoo S.A.

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

## Cosa ci si fa

- **Cercare nel catalogo** con gli stessi filtri del sito (testo, serie, categoria, autore,
  gratuito/a pagamento, ordinamento) ottenendo JSON invece di HTML.
- **Leggere la scheda completa** di un modulo: licenza, dipendenze, righe di codice,
  compatibilità con Odoo Online / Odoo.sh / On-Premise, rating, prezzo, download.
- **Confrontare le serie**: su quali versioni di Odoo un modulo esiste, con quale numero
  di versione e a che prezzo.
- **Tracciare i download nel tempo**, cosa che lo store non permette: nessuno storico è
  pubblicato, quindi il servizio se lo costruisce campionando.
- **Scaricare il codice di un modulo gratuito** dal repository dichiarato nella scheda,
  leggerne il manifest e sfogliarne i file via API.

Casi d'uso tipici: monitorare i propri moduli pubblicati o quelli dei concorrenti, valutare
un modulo prima di installarlo, verificare su quali serie un addon è già stato portato,
alimentare una dashboard interna.

## Avvio

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```
```bash
.venv/bin/uvicorn app.main:app --reload
```

- Documentazione interattiva (Swagger UI): <http://localhost:8000/docs>
- Schema OpenAPI: <http://localhost:8000/openapi.json>
- Riferimento completo degli endpoint: **[docs/api.it.md](docs/api.it.md)**

Con Docker — non serve altro, `.env` è opzionale e i default bastano per partire:

```bash
docker compose up --build
```

Prima di usarlo sul serio, imposta un contatto reale nello User-Agent — è la cortesia
minima verso un sito interrogato in automatico:

```bash
cp .env.example .env
```

## Endpoint

Tutti sotto il prefisso `/api/v1`. Parametri e risposte in dettaglio in [docs/api.it.md](docs/api.it.md).

### Catalogo

| Metodo | Path | Descrizione |
|---|---|---|
| `GET` | `/search` | ricerca con filtri `q`, `series`, `price`, `category`, `author`, `order`, `page`, `limit` |
| `GET` | `/modules/{series}/{technical_name}` | scheda completa; `?refresh=true` bypassa la cache |
| `GET` | `/modules/{technical_name}/versions` | serie su cui il modulo esiste; `?detailed=true` aggiunge versione, prezzo e download |
| `GET` | `/authors/{author}` | moduli di un publisher (nome esatto) |
| `GET` | `/categories` · `/series` · `/orders` | valori ammessi dai filtri |

### Statistiche

| Metodo | Path | Descrizione |
|---|---|---|
| `GET` | `/stats/{series}/{technical_name}` | serie storica dei contatori, con delta e media giornaliera |
| `GET` `POST` `DELETE` | `/watchlist[/{id}]` | moduli ricampionati ogni giorno in automatico |
| `POST` | `/watchlist/refresh` | forza subito un giro di campionamento |

### Sorgenti

| Metodo | Path | Descrizione |
|---|---|---|
| `POST` | `/sources/{series}/{technical_name}` | preleva il codice; `?ref=` sceglie il branch, `?force=true` ripreleva |
| `GET` | `/sources` | moduli già prelevati in locale |
| `GET` | `/sources/{series}/{technical_name}/files` | elenco dei file con dimensione |
| `GET` | `/sources/{series}/{technical_name}/file?path=` | contenuto di un singolo file |

### Servizio

| Metodo | Path | Descrizione |
|---|---|---|
| `GET` | `/health` | stato, dimensione ed efficacia della cache, numero di snapshot e sorgenti |

### Esempi

I cinque moduli WhatsApp per Odoo 18 più installati in questo momento
(`order=downloads` ordina per download dell'ultimo mese, non per totale storico):

```bash
curl -s "http://localhost:8000/api/v1/search?q=whatsapp&series=18.0&order=downloads&limit=5" | jq '.items[] | {technical_name, downloads_last_month, price}'
```

I moduli a pagamento più venduti nel Point of Sale:

```bash
curl -s "http://localhost:8000/api/v1/search?price=paid&category=point_of_sale&order=purchases&limit=10" | jq '.items[] | {name, purchases, price}'
```

Su quali serie è stato portato `report_xlsx`, con il numero di versione:

```bash
curl -s "http://localhost:8000/api/v1/modules/report_xlsx/versions?detailed=true" | jq '.versions[] | {series, version}'
```

Preleva il codice di un modulo gratuito e leggine il manifest:

```bash
curl -s -X POST "http://localhost:8000/api/v1/sources/18.0/llm_mcp_server" | jq '{repo_url, version, license, file_count, depends}'
```

### Valori dei filtri

- `series`: `19.0` … `5.0` (incluso `6.1`). Sono accettate anche le release online
  intermedie che compaiono negli URL dello store, es. `saas-19.4`.
- `price`: `free`, `paid`.
- `order`: `relevance`, `downloads`, `newest`, `ratings`, `name`, `best_sellers`,
  `purchases`, `price_desc`, `price_asc`.
- `category`: `accounting`, `discuss`, `document_management`, `ecommerce`, `extra_tools`,
  `human_resources`, `industries`, `localization`, `manufacturing`, `marketing`,
  `point_of_sale`, `productivity`, `project`, `purchases`, `sales`, `tutorial`,
  `warehouse`, `website`.

## Come funziona

```
                  ┌─ cache SQLite ─(miss)→ rate limiter 1 rps → apps.odoo.com
client → FastAPI ─┼─ snapshot giornaliero dei contatori → tabella module_snapshots
                  └─ prelievo tarball → codeload.github.com → data/modules/
```

**Cache.** Ogni pagina HTML finisce su SQLite. TTL predefiniti: liste 1 h, dettagli 6 h,
pagine statiche 24 h, 404 15 min. Se l'upstream non risponde viene servita la copia
scaduta con `stale: true` nella risposta, invece di un errore.

**Rate limit.** Una richiesta al secondo verso apps.odoo.com, massimo 4 in parallelo,
retry esponenziale su 429 e 5xx. Il `robots.txt` dello store vieta agli spider le URL
con `?search=`, `?order=` e `?page=`: questa API è pensata per query mirate, non per
crawlare le ~83.000 schede del catalogo.

**Snapshot.** Ogni lettura reale di una scheda registra un punto giornaliero (download,
acquisti, rating, prezzo, versione). I trend partono quindi dal giorno della prima
lettura: lo store non pubblica né storico né data di aggiornamento dei moduli. Per un
modulo che interessa davvero conviene metterlo in watchlist, così un job giornaliero
(default 03:00) lo ricampiona da solo.

**Sorgenti.** Il pulsante "Download" dello store è un handler JavaScript protetto da
reCAPTCHA v3, quindi non è interrogabile da un client automatico. Il codice dei moduli
gratuiti è però pubblico e la scheda dichiara il repository di origine: il servizio
preleva il tarball da lì. Sono ammessi i soli moduli gratuiti e i soli repository GitHub;
gli archivi vengono validati membro per membro (niente link, niente percorsi che escono
dalla cartella del modulo, tetti su dimensione e rapporto di compressione) ed estratti in
una cartella temporanea che sostituisce la destinazione solo a estrazione riuscita.

## Limiti noti, tutti dovuti alla sorgente

| Campo | Dove è disponibile | Perché |
|---|---|---|
| `summary` | solo nelle liste | la pagina di dettaglio non lo riporta |
| `downloads_last_month` | solo nelle liste | idem |
| `purchases` | moduli a pagamento | le schede gratuite mostrano i download, quelle a pagamento gli acquisti |
| `latest_version` | solo moduli gratuiti | per i moduli a pagamento lo store non pubblica la versione prima dell'acquisto |
| `downloads_total` | dato di modulo, non di serie | lo stesso valore compare su tutte le serie |

La valuta viene dedotta dal simbolo accanto al prezzo: il microdata `priceCurrency`
della pagina contiene un template Odoo non renderizzato e va ignorato.

Il prelievo dei sorgenti funziona solo per moduli gratuiti il cui campo *Website* punta
a GitHub. Per gli altri l'API risponde `400` spiegando quale delle due condizioni manca.

## Configurazione

Tutto si sovrascrive con variabili `ODOO_STORE_*` o con un file `.env`
(vedi [.env.example](.env.example)). Le più utili:

| Variabile | Default | A cosa serve |
|---|---|---|
| `ODOO_STORE_USER_AGENT` | placeholder | **da personalizzare**: identifica chi sta interrogando lo store |
| `ODOO_STORE_RATE_LIMIT_RPS` | `1.0` | richieste al secondo verso apps.odoo.com |
| `ODOO_STORE_TTL_LISTING` / `_DETAIL` | `3600` / `21600` | freschezza della cache, in secondi |
| `ODOO_STORE_DB_PATH` | `data/store.sqlite3` | cache, snapshot e indice dei sorgenti |
| `ODOO_STORE_SOURCE_DIR` | `data/modules` | dove finisce il codice prelevato |
| `ODOO_STORE_GITHUB_TOKEN` | — | alza il rate limit GitHub da 60 a 5000 richieste/ora |
| `ODOO_STORE_ENABLE_SCHEDULER` | `true` | job giornaliero di campionamento della watchlist |

## Sviluppo

```bash
.venv/bin/python -m pytest
```
```bash
.venv/bin/ruff check app tests scripts
```

I parser girano su HTML reale salvato in `tests/fixtures/` e il prelievo da GitHub su
tarball costruiti in memoria: la suite non tocca la rete.

**Se un test dei parser fallisce, il markup dello store è probabilmente cambiato.**
Si riscaricano i fixture e si adegua il parser ai valori nuovi:

```bash
.venv/bin/python scripts/refresh_fixtures.py
```

### Struttura

```
app/
  config.py        impostazioni (env ODOO_STORE_*)
  constants.py     serie, categorie, ordinamenti, valute
  models.py        modelli di risposta Pydantic
  http_client.py   rate limiter + retry verso apps.odoo.com
  cache.py         cache SQLite con stale-if-error
  db.py            schema SQLite
  sources.py       client GitHub, estrazione tarball, lettura manifest
  scrapers/        listing.py, detail.py, common.py
  services/        catalog.py, stats.py, source.py
  routers/         modules.py, catalog.py, stats.py, sources.py
docs/api.it.md     riferimento completo degli endpoint
tests/             parser su HTML reale, endpoint con cache pre-popolata, tarball finti
scripts/           refresh_fixtures.py
```

Il punto delicato del progetto sono i parser: `app/scrapers/detail.py` preferisce i
microdata schema.org alle classi CSS del tema, perché sopravvivono meglio ai restyling
del sito. Un campo che non si trova non solleva mai un'eccezione: finisce in
`parse_warnings`, così la risposta resta utilizzabile e il problema resta visibile.

## Uso responsabile

I dati provengono da pagine pubbliche e il servizio si identifica con uno User-Agent
configurabile, limitando le proprie richieste. Prima di alzare
`ODOO_STORE_RATE_LIMIT_RPS` vale la pena chiedersi se serva davvero: la cache copre già
la maggior parte dei casi d'uso.

Il codice prelevato dai repository resta sotto la licenza dei rispettivi autori, che il
servizio riporta nel campo `license` senza modificarla.

## Licenza

MIT — vedi [LICENSE](LICENSE).
