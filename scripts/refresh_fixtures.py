#!/usr/bin/env python3
"""Riscarica i fixture HTML usati dai test dei parser.

Da lanciare quando i test falliscono per un cambio di markup dello store:

    python scripts/refresh_fixtures.py

Poi si rileggono i test e si adegua il parser ai valori nuovi.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

BASE_URL = "https://apps.odoo.com"
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
USER_AGENT = "odoo-store-api/0.1 (aggiornamento fixture di test)"

PAGES: dict[str, str] = {
    "listing_browse_downloads.html": "/apps/modules/browse?order=Downloads",
    "listing_paid_18.html": "/apps/modules/browse?price=Paid&series=18.0&order=Downloads",
    "detail_web_responsive_19.html": "/apps/modules/19.0/web_responsive",
    "detail_common_connector_library_18.html": "/apps/modules/18.0/common_connector_library",
    "detail_not_found.html": "/apps/modules/19.0/questo_non_esiste_xyz",
}


def download(path: str) -> tuple[int, str]:
    request = Request(f"{BASE_URL}{path}", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # il 404 arriva come HTTPError ed è un caso atteso
        status = getattr(exc, "status", None) or getattr(exc, "code", 0)
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        if status:
            return status, body
        raise


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, path in PAGES.items():
        status, body = download(path)
        (FIXTURES / name).write_text(body, encoding="utf-8")
        print(f"{status} {len(body):>7} byte  {name}")
        time.sleep(1)  # una richiesta al secondo, come fa il servizio
    return 0


if __name__ == "__main__":
    sys.exit(main())
