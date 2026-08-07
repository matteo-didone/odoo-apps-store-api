"""Logica applicativa: costruzione URL, orchestrazione fetch/parse, persistenza."""

from .catalog import CatalogService
from .source import SourceService
from .stats import StatsService

__all__ = ["CatalogService", "SourceService", "StatsService"]
