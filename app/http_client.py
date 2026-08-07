"""Client HTTP verso apps.odoo.com: rate limit, concorrenza limitata e retry."""

from __future__ import annotations

import asyncio
import logging
import random
import time

import httpx

from .config import Settings
from .exceptions import UpstreamError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class RateLimiter:
    """Distanzia le richieste di almeno 1/rps secondi, indipendentemente dalla concorrenza."""

    def __init__(self, rps: float):
        self._min_interval = 1.0 / rps if rps > 0 else 0.0
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self) -> None:
        if not self._min_interval:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._last + self._min_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._last = now


class HttpFetcher:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._limiter = RateLimiter(settings.rate_limit_rps)
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._client = httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=settings.request_timeout,
            follow_redirects=True,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    def build_url(self, path: str, params: dict[str, str] | None = None) -> str:
        """URL assoluto e stabile, usato anche come chiave di cache."""
        request = self._client.build_request("GET", path, params=params or None)
        return str(request.url)

    async def get(self, url: str) -> httpx.Response:
        """GET con backoff esponenziale sugli errori transitori. Il 404 non è un errore."""
        last_error: Exception | None = None

        for attempt in range(self._settings.max_retries):
            async with self._semaphore:
                await self._limiter.acquire()
                try:
                    response = await self._client.get(url)
                except httpx.HTTPError as exc:
                    last_error = exc
                    logger.warning("Errore di rete su %s (tentativo %s): %s", url, attempt + 1, exc)
                else:
                    if response.status_code not in RETRYABLE_STATUS:
                        return response
                    last_error = UpstreamError(
                        f"apps.odoo.com ha risposto {response.status_code}"
                    )
                    logger.warning(
                        "Status %s su %s (tentativo %s)", response.status_code, url, attempt + 1
                    )
                    retry_after = _retry_after_seconds(response)
                    if retry_after is not None:
                        await asyncio.sleep(retry_after)
                        continue

            if attempt < self._settings.max_retries - 1:
                await asyncio.sleep(2**attempt + random.uniform(0, 0.3))

        raise UpstreamError(
            f"apps.odoo.com non raggiungibile dopo "
            f"{self._settings.max_retries} tentativi: {last_error}"
        )


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return min(float(raw), 30.0)
    except ValueError:
        return None
