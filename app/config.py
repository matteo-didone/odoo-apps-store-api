"""Configurazione applicativa, sovrascrivibile da variabili d'ambiente ODOO_STORE_*."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ODOO_STORE_",
        extra="ignore",
    )

    # --- upstream ---
    base_url: str = "https://apps.odoo.com"
    # Va sostituito con un contatto reale via ODOO_STORE_USER_AGENT: è la cortesia
    # minima verso un sito che si sta interrogando in automatico.
    user_agent: str = "odoo-store-api/0.1 (+https://apps.odoo.com; contact: you@example.com)"
    request_timeout: float = 20.0

    # --- buone maniere verso apps.odoo.com ---
    rate_limit_rps: float = 1.0
    max_concurrency: int = 4
    max_retries: int = 3

    # --- cache (secondi) ---
    ttl_listing: int = 3600
    ttl_detail: int = 21600
    ttl_static: int = 86400
    ttl_not_found: int = 900

    # --- persistenza ---
    db_path: str = "data/store.sqlite3"

    # --- sorgenti dei moduli ---
    # Lo store non permette il download automatico (il pulsante è dietro reCAPTCHA v3):
    # il codice si preleva dal repository upstream dichiarato nella scheda del modulo.
    source_dir: str = "data/modules"
    github_base_url: str = "https://codeload.github.com"
    github_token: str | None = None
    github_rate_limit_rps: float = 5.0
    github_timeout: float = 60.0
    max_archive_bytes: int = 64 * 1024 * 1024
    max_extracted_bytes: int = 256 * 1024 * 1024
    max_compression_ratio: float = 120.0

    # --- snapshot / trend ---
    enable_scheduler: bool = True
    snapshot_hour: int = 3
    snapshot_minute: int = 0

    # --- api ---
    cors_origins: list[str] = ["*"]
    max_search_limit: int = 100

    @property
    def page_size(self) -> int:
        """Schede per pagina servite da apps.odoo.com. Non è configurabile lato loro."""
        return 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
