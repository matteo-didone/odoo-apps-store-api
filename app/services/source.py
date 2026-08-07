"""Prelievo e indicizzazione del codice dei moduli gratuiti."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from ..config import Settings
from ..db import Database
from ..exceptions import SourceUnavailable, StoreNotFound
from ..models import (
    ModuleSource,
    SourceFile,
    SourceFileContent,
    SourceFilesResponse,
    SourceListResponse,
)
from ..sources import GitHubFetcher, extract_module, parse_github_repo
from .catalog import CatalogService

logger = logging.getLogger(__name__)

# I file sorgente si leggono a video: oltre questa soglia si tronca invece di
# spedire un blob illeggibile.
MAX_INLINE_FILE_BYTES = 512 * 1024


class SourceService:
    def __init__(
        self,
        db: Database,
        fetcher: GitHubFetcher,
        catalog: CatalogService,
        settings: Settings,
    ):
        self._db = db
        self._fetcher = fetcher
        self._catalog = catalog
        self._settings = settings

    @property
    def root(self) -> Path:
        return Path(self._settings.source_dir)

    def module_path(self, series: str, technical_name: str) -> Path:
        return self.root / series / technical_name

    # ---------------------------------------------------------------- prelievo

    async def fetch(
        self,
        series: str,
        technical_name: str,
        *,
        ref: str | None = None,
        force: bool = False,
    ) -> ModuleSource:
        """Preleva il codice dal repository dichiarato nella scheda dello store."""
        if not force:
            existing = await self.get(series, technical_name)
            if existing is not None:
                return existing

        detail = await self._catalog.get_module(series, technical_name)

        if not detail.price.is_free:
            raise SourceUnavailable(
                f"'{technical_name}' è a pagamento: il codice non viene prelevato"
            )

        repo = parse_github_repo(detail.website)
        branch = ref or series
        archive = await self._fetcher.fetch_archive(repo, branch)
        checksum = hashlib.sha256(archive).hexdigest()

        destination = self.module_path(series, technical_name)
        # L'estrazione è bloccante: fuori dall'event loop.
        extracted = await asyncio.to_thread(
            extract_module,
            archive,
            technical_name,
            destination,
            settings=self._settings,
        )

        manifest = extracted.manifest
        depends = manifest.get("depends") or []
        if not isinstance(depends, list):
            depends = []

        record = ModuleSource(
            technical_name=technical_name,
            series=series,
            repo_url=repo.url,
            ref=branch,
            path=str(extracted.path),
            name=_as_text(manifest.get("name")) or detail.name,
            version=_as_text(manifest.get("version")) or detail.latest_version,
            license=_as_text(manifest.get("license")) or detail.license,
            author=_as_text(manifest.get("author")) or ", ".join(detail.authors),
            depends=[str(item) for item in depends],
            file_count=extracted.file_count,
            bytes_extracted=extracted.bytes_extracted,
            archive_sha256=checksum,
            fetched_at=datetime.now(UTC),
        )

        await self._persist(record)
        logger.info(
            "Prelevato %s/%s da %s@%s (%s file)",
            series,
            technical_name,
            repo.url,
            branch,
            extracted.file_count,
        )
        return record

    async def _persist(self, record: ModuleSource) -> None:
        await self._db.execute(
            """
            INSERT INTO module_sources (
                technical_name, series, repo_url, ref, path, name, version,
                license, author, depends, file_count, bytes_extracted,
                archive_sha256, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (technical_name, series) DO UPDATE SET
                repo_url = excluded.repo_url,
                ref = excluded.ref,
                path = excluded.path,
                name = excluded.name,
                version = excluded.version,
                license = excluded.license,
                author = excluded.author,
                depends = excluded.depends,
                file_count = excluded.file_count,
                bytes_extracted = excluded.bytes_extracted,
                archive_sha256 = excluded.archive_sha256,
                fetched_at = excluded.fetched_at
            """,
            (
                record.technical_name,
                record.series,
                record.repo_url,
                record.ref,
                record.path,
                record.name,
                record.version,
                record.license,
                record.author,
                json.dumps(record.depends),
                record.file_count,
                record.bytes_extracted,
                record.archive_sha256,
                time.time(),
            ),
        )

    # ----------------------------------------------------------------- lettura

    async def get(self, series: str, technical_name: str) -> ModuleSource | None:
        row = await self._db.fetch_one(
            "SELECT * FROM module_sources WHERE technical_name = ? AND series = ?",
            (technical_name, series),
        )
        if row is None:
            return None
        # Un record che punta a una cartella sparita è rumore, non un risultato.
        if not Path(row["path"]).is_dir():
            return None
        return _row_to_model(row)

    async def list(self) -> SourceListResponse:
        rows = await self._db.fetch_all(
            "SELECT * FROM module_sources ORDER BY series DESC, technical_name"
        )
        items = [_row_to_model(row) for row in rows if Path(row["path"]).is_dir()]
        return SourceListResponse(
            items=items, count=len(items), source_dir=str(self.root)
        )

    async def files(self, series: str, technical_name: str) -> SourceFilesResponse:
        base = await self._require_module(series, technical_name)
        entries = [
            SourceFile(path=str(item.relative_to(base)), size=item.stat().st_size)
            for item in sorted(base.rglob("*"))
            if item.is_file()
        ]
        return SourceFilesResponse(
            technical_name=technical_name,
            series=series,
            file_count=len(entries),
            files=entries,
        )

    async def read_file(
        self, series: str, technical_name: str, relative_path: str
    ) -> SourceFileContent:
        base = await self._require_module(series, technical_name)
        target = (base / relative_path).resolve()

        # Il percorso arriva da query string: va confinato dentro il modulo.
        if not target.is_relative_to(base):
            raise SourceUnavailable(
                f"Il percorso '{relative_path}' esce dalla cartella del modulo"
            )
        if not target.is_file():
            raise StoreNotFound(
                f"'{relative_path}' non esiste in {series}/{technical_name}"
            )

        size = target.stat().st_size
        raw = target.read_bytes()[:MAX_INLINE_FILE_BYTES]
        return SourceFileContent(
            technical_name=technical_name,
            series=series,
            path=relative_path,
            size=size,
            content=raw.decode("utf-8", errors="replace"),
            truncated=size > MAX_INLINE_FILE_BYTES,
        )

    async def _require_module(self, series: str, technical_name: str) -> Path:
        record = await self.get(series, technical_name)
        if record is None:
            raise StoreNotFound(
                f"Il codice di {series}/{technical_name} non è ancora stato prelevato"
            )
        return Path(record.path).resolve()

    async def count(self) -> int:
        return await self._db.scalar("SELECT COUNT(*) FROM module_sources") or 0


def _row_to_model(row) -> ModuleSource:
    return ModuleSource(
        technical_name=row["technical_name"],
        series=row["series"],
        repo_url=row["repo_url"],
        ref=row["ref"],
        path=row["path"],
        name=row["name"],
        version=row["version"],
        license=row["license"],
        author=row["author"],
        depends=json.loads(row["depends"] or "[]"),
        file_count=row["file_count"],
        bytes_extracted=row["bytes_extracted"],
        archive_sha256=row["archive_sha256"],
        fetched_at=datetime.fromtimestamp(row["fetched_at"], UTC),
    )


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
