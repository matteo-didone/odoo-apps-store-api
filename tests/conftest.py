from __future__ import annotations

import io
import tarfile
import time
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.sources import GitHubFetcher

FIXTURES = Path(__file__).parent / "fixtures"
BASE_URL = "https://apps.odoo.com"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


@pytest.fixture
def base_url() -> str:
    return BASE_URL


@pytest_asyncio.fixture
async def app_and_services(tmp_path, monkeypatch):
    """App isolata su un DB temporaneo, senza scheduler e senza rete."""
    monkeypatch.setenv("ODOO_STORE_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("ODOO_STORE_ENABLE_SCHEDULER", "false")
    # Senza questo i test scriverebbero i moduli prelevati dentro il repo.
    monkeypatch.setenv("ODOO_STORE_SOURCE_DIR", str(tmp_path / "modules"))
    get_settings.cache_clear()

    from app.main import create_app

    application = create_app()
    async with application.router.lifespan_context(application):
        yield application, application.state.services

    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(app_and_services):
    application, _ = app_and_services
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def tarball():
    """Costruisce un tarball nella forma che restituisce GitHub.

    GitHub incapsula tutto in una cartella `<repo>-<ref>/`, quindi il modulo sta
    al secondo livello: i test devono riprodurre quella forma.
    """

    def _build(
        files: dict[str, bytes],
        *,
        symlinks: dict[str, str] | None = None,
        top: str = "web-19.0",
    ) -> bytes:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for name, data in files.items():
                info = tarfile.TarInfo(f"{top}/{name}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            for name, target in (symlinks or {}).items():
                info = tarfile.TarInfo(f"{top}/{name}")
                info.type = tarfile.SYMTYPE
                info.linkname = target
                tar.addfile(info)
        return buffer.getvalue()

    return _build


@pytest.fixture
def mock_github(app_and_services):
    """Sostituisce il client GitHub con un MockTransport.

    Il percorso binario non passa da HtmlCache, quindi `seed_cache` non lo copre:
    il client iniettabile di GitHubFetcher è l'unico punto di innesto.
    """
    _, services = app_and_services

    def _install(handler) -> GitHubFetcher:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        fetcher = GitHubFetcher(services.settings, client=client)
        services.github = fetcher
        services.source._fetcher = fetcher
        return fetcher

    return _install


@pytest.fixture
def serve_archive(mock_github):
    """Fa rispondere GitHub con un archivio fisso, registrando gli URL richiesti."""
    requested: list[str] = []

    def _serve(archive: bytes, status: int = 200):
        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(status, content=archive)

        mock_github(handler)
        return requested

    return _serve


@pytest_asyncio.fixture
def seed_cache(app_and_services):
    """Inserisce una pagina HTML in cache così i test non toccano la rete."""
    _, services = app_and_services

    async def _seed(url: str, body: str, status: int = 200) -> None:
        await services.db.execute(
            "INSERT OR REPLACE INTO http_cache (url, status, body, fetched_at) VALUES (?, ?, ?, ?)",
            (url, status, body, time.time()),
        )

    return _seed
