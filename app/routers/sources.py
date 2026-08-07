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

router = APIRouter(tags=["sources"])

TECHNICAL_NAME = Path(
    ...,
    pattern=r"^[A-Za-z0-9_.\-]+$",
    description="Module technical name, e.g. `web_responsive`",
)
SERIES_PATH = Path(..., pattern=SERIES_PATTERN, description="Odoo series, e.g. `18.0`")


@router.get("/sources", response_model=SourceListResponse, summary="Modules already fetched")
async def list_sources(source: SourceService = Depends(get_source)) -> SourceListResponse:
    return await source.list()


@router.post(
    "/sources/{series}/{technical_name}",
    response_model=ModuleSource,
    summary="Fetch a free module's source",
    description=(
        "The code comes from the repository declared on the store listing, not from "
        "apps.odoo.com: the store serves downloads only behind reCAPTCHA and cannot be "
        "driven by an automated client. Free modules only."
    ),
)
async def fetch_source(
    series: str = SERIES_PATH,
    technical_name: str = TECHNICAL_NAME,
    ref: str | None = Query(
        default=None,
        pattern=r"^[A-Za-z0-9_.\-/]+$",
        description="Repository branch; the series is used when omitted",
    ),
    force: bool = Query(default=False, description="Refetch even if already present"),
    source: SourceService = Depends(get_source),
) -> ModuleSource:
    return await source.fetch(series, technical_name, ref=ref, force=force)


@router.get(
    "/sources/{series}/{technical_name}/files",
    response_model=SourceFilesResponse,
    summary="File listing of the fetched module",
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
    summary="Contents of a file in the fetched module",
)
async def read_file(
    series: str = SERIES_PATH,
    technical_name: str = TECHNICAL_NAME,
    path: str = Query(..., description="Path relative to the module root"),
    source: SourceService = Depends(get_source),
) -> SourceFileContent:
    return await source.read_file(series, technical_name, path)
