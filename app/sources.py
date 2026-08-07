"""Prelievo del codice dei moduli dai repository upstream.

apps.odoo.com non offre un download automatizzabile: il pulsante "Download" è un
handler JavaScript che invia un form protetto da reCAPTCHA v3. Il codice dei
moduli gratuiti è però pubblico e la scheda dello store dichiara il repository di
origine, quindi si preleva da lì: licenza esplicita e nessun gate da aggirare.
"""

from __future__ import annotations

import ast
import io
import logging
import os
import re
import shutil
import tarfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import httpx

from .config import Settings
from .exceptions import SourceUnavailable, UpstreamError
from .http_client import RateLimiter

logger = logging.getLogger(__name__)

# I nomi finiscono in un percorso su disco: si validano qui, dove il danno sarebbe
# concreto, anche se i router li hanno già filtrati con SERIES_PATTERN.
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")

GITHUB_HOSTS = {"github.com", "www.github.com"}


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"


@dataclass
class ExtractedModule:
    path: Path
    file_count: int
    bytes_extracted: int
    manifest: dict = field(default_factory=dict)


def parse_github_repo(website: str | None) -> RepoRef:
    """Ricava owner/repo dal campo `website` della scheda del modulo."""
    if not website or not website.strip():
        raise SourceUnavailable(
            "La scheda del modulo non dichiara alcun repository di origine"
        )

    raw = website.strip()
    if "://" not in raw:
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in GITHUB_HOSTS:
        raise SourceUnavailable(
            f"Il modulo dichiara '{website}', che non è un repository GitHub: "
            "il prelievo automatico non è supportato"
        )

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise SourceUnavailable(f"'{website}' non identifica un repository GitHub")

    owner, name = parts[0], parts[1]
    if name.endswith(".git"):
        name = name[:-4]
    if not SAFE_NAME_RE.match(owner) or not SAFE_NAME_RE.match(name):
        raise SourceUnavailable(f"'{website}' contiene un nome di repository non valido")

    return RepoRef(owner=owner, name=name)


class GitHubFetcher:
    """Client verso codeload.github.com.

    Separato da `HttpFetcher`: quello è legato ad apps.odoo.com (base_url fissa,
    1 rps, `Accept: text/html`) e nessuno di quei vincoli ha senso qui.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._limiter = RateLimiter(settings.github_rate_limit_rps)

        headers = {"User-Agent": settings.user_agent, "Accept": "application/x-gzip"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        # Il client è iniettabile perché i test possano usare httpx.MockTransport:
        # il percorso binario non passa da HtmlCache e non ha altri punti di innesto.
        self._client = client or httpx.AsyncClient(
            timeout=settings.github_timeout,
            follow_redirects=True,
            headers=headers,
        )

    async def close(self) -> None:
        await self._client.aclose()

    def archive_url(self, repo: RepoRef, ref: str) -> str:
        base = self._settings.github_base_url.rstrip("/")
        return f"{base}/{repo.owner}/{repo.name}/tar.gz/refs/heads/{ref}"

    async def fetch_archive(self, repo: RepoRef, ref: str) -> bytes:
        """Scarica il tarball del branch, interrompendo appena supera il tetto."""
        url = self.archive_url(repo, ref)
        limit = self._settings.max_archive_bytes
        buffer = bytearray()

        await self._limiter.acquire()
        try:
            async with self._client.stream("GET", url) as response:
                if response.status_code == 404:
                    raise SourceUnavailable(
                        f"Il branch '{ref}' non esiste in {repo.url}"
                    )
                if response.status_code >= 400:
                    raise UpstreamError(
                        f"GitHub ha risposto {response.status_code} su {url}"
                    )

                async for chunk in response.aiter_bytes():
                    buffer.extend(chunk)
                    if len(buffer) > limit:
                        raise SourceUnavailable(
                            f"L'archivio di {repo.url} supera il tetto di {limit} byte"
                        )
        except httpx.HTTPError as exc:
            raise UpstreamError(f"GitHub non raggiungibile: {exc}") from exc

        return bytes(buffer)


def extract_module(
    archive: bytes,
    technical_name: str,
    destination: Path,
    *,
    settings: Settings,
) -> ExtractedModule:
    """Estrae la sola cartella del modulo dal tarball, rifiutando archivi ostili.

    `tarfile` non protegge da solo: ogni membro va validato prima di scrivere
    qualunque cosa su disco. Si scrive in una cartella temporanea e si sostituisce
    la destinazione solo alla fine, così un archivio rifiutato a metà non lascia
    un modulo mutilato.
    """
    if not SAFE_NAME_RE.match(technical_name):
        raise SourceUnavailable(f"Nome tecnico non valido: '{technical_name}'")

    allowed = settings.max_extracted_bytes
    if archive:
        # Un archivio piccolo che si espande enormemente è una tar-bomb.
        allowed = min(allowed, int(len(archive) * settings.max_compression_ratio))

    destination = destination.resolve()
    staging = destination.parent / f".{technical_name}.incoming"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    total = 0
    files = 0

    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            for member in tar:
                relative = _module_relative_path(member.name, technical_name)
                if relative is None:
                    continue

                _reject_unsafe(member, relative)

                target = staging / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue

                total += member.size
                if total > allowed:
                    raise SourceUnavailable(
                        f"Il modulo estratto supera il tetto di {allowed} byte: "
                        "archivio rifiutato"
                    )

                source = tar.extractfile(member)
                if source is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as handle:
                    shutil.copyfileobj(source, handle, 64 * 1024)
                files += 1

        if files == 0:
            raise SourceUnavailable(
                f"L'archivio non contiene la cartella '{technical_name}'"
            )

        manifest = read_manifest(staging)

        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return ExtractedModule(
        path=destination,
        file_count=files,
        bytes_extracted=total,
        manifest=manifest,
    )


def read_manifest(module_path: Path) -> dict:
    """Legge `__manifest__.py` con literal_eval: non esegue il codice del modulo."""
    manifest_file = module_path / "__manifest__.py"
    if not manifest_file.is_file():
        return {}
    try:
        parsed = ast.literal_eval(
            manifest_file.read_text(encoding="utf-8", errors="replace")
        )
    except (ValueError, SyntaxError, MemoryError, RecursionError) as exc:
        logger.warning("__manifest__.py illeggibile in %s: %s", module_path, exc)
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _module_relative_path(name: str, technical_name: str) -> PurePosixPath | None:
    """Percorso del membro dentro il modulo, o None se il membro non lo riguarda.

    I tarball di GitHub incapsulano tutto in una cartella `<repo>-<ref>/`, quindi
    il modulo è al secondo livello. I membri fuori dal modulo vengono ignorati:
    è normale che il repository contenga altro, inclusi i symlink di `setup/`
    che gli OCA generano per ogni addon.
    """
    parts = PurePosixPath(name).parts
    if len(parts) < 2 or parts[1] != technical_name:
        return None
    return PurePosixPath(*parts[2:]) if len(parts) > 2 else PurePosixPath()


def _reject_unsafe(member: tarfile.TarInfo, relative: PurePosixPath) -> None:
    if member.issym() or member.islnk():
        raise SourceUnavailable(
            f"L'archivio contiene un link ('{member.name}'): rifiutato"
        )
    if not (member.isfile() or member.isdir()):
        raise SourceUnavailable(
            f"L'archivio contiene un membro di tipo non consentito ('{member.name}')"
        )
    if relative.is_absolute() or ".." in relative.parts:
        raise SourceUnavailable(
            f"L'archivio contiene un percorso che esce dalla cartella "
            f"del modulo ('{member.name}'): rifiutato"
        )
