"""Prelievo e lettura del codice dei moduli gratuiti."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from ..constants import SERIES_PATTERN
from ..dependencies import get_source
from ..models import (
    ModuleSource,
    SourceFileContent,
    SourceFilesResponse,
    SourceListResponse,
)
from ..services import SourceService

router = APIRouter(tags=["sorgenti"])

TECHNICAL_NAME = Path(
    ...,
    pattern=r"^[A-Za-z0-9_.\-]+$",
    description="Nome tecnico del modulo, es. `web_responsive`",
)
SERIES_PATH = Path(..., pattern=SERIES_PATTERN, description="Serie Odoo, es. `18.0`")


@router.get("/sources", response_model=SourceListResponse, summary="Moduli già prelevati")
async def list_sources(source: SourceService = Depends(get_source)) -> SourceListResponse:
    return await source.list()


@router.post(
    "/sources/{series}/{technical_name}",
    response_model=ModuleSource,
    summary="Preleva il codice di un modulo gratuito",
    description=(
        "Il codice arriva dal repository dichiarato nella scheda dello store, non "
        "da apps.odoo.com: lo store serve il download solo dietro reCAPTCHA e non è "
        "interrogabile da un client automatico. Sono ammessi i soli moduli gratuiti."
    ),
)
async def fetch_source(
    series: str = SERIES_PATH,
    technical_name: str = TECHNICAL_NAME,
    ref: str | None = Query(
        default=None,
        pattern=r"^[A-Za-z0-9_.\-/]+$",
        description="Branch del repository; se omesso viene usata la serie",
    ),
    force: bool = Query(default=False, description="Ripreleva anche se già presente"),
    source: SourceService = Depends(get_source),
) -> ModuleSource:
    return await source.fetch(series, technical_name, ref=ref, force=force)


@router.get(
    "/sources/{series}/{technical_name}/files",
    response_model=SourceFilesResponse,
    summary="Elenco dei file del modulo prelevato",
)
async def list_files(
    series: str = SERIES_PATH,
    technical_name: str = TECHNICAL_NAME,
    source: SourceService = Depends(get_source),
) -> SourceFilesResponse:
    return await source.files(series, technical_name)


@router.get(
    "/sources/{series}/{technical_name}/file",
    response_model=SourceFileContent,
    summary="Contenuto di un file del modulo prelevato",
)
async def read_file(
    series: str = SERIES_PATH,
    technical_name: str = TECHNICAL_NAME,
    path: str = Query(..., description="Percorso relativo alla radice del modulo"),
    source: SourceService = Depends(get_source),
) -> SourceFileContent:
    return await source.read_file(series, technical_name, path)
