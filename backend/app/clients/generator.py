"""
Client for the Timetable Generator's read-only Allocator endpoints
(/api/integrations/allocator/), authenticated with this system's own key
(X-API-Key = GENERATOR_API_KEY here, ALLOCATOR_API_KEY there).

The Director opens each term in the Generator, and departments enter their
teaching here against it. Once the Director publishes a version, the
Generator also says when and where each class meets, which departments see
on their pages and downloads.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.errors import ApiError

logger = logging.getLogger(__name__)

PREFIX = "/api/integrations/allocator"


class GeneratorClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=settings.generator_base_url.rstrip("/"),
            timeout=settings.generator_timeout_seconds,
            headers={"X-API-Key": settings.generator_api_key, "Accept": "application/json"},
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str) -> Any:
        try:
            response = self._http.get(PREFIX + path)
        except httpx.HTTPError as exc:
            logger.warning("Generator GET %s failed: %s", path, exc)
            raise ApiError(
                503,
                "GENERATOR_UNAVAILABLE",
                "The Timetable Generator could not be reached. Try again shortly.",
            ) from exc
        if response.status_code in (401, 403):
            logger.error("The Generator refused the Allocator's key (%s -> %s)", path, response.status_code)
            raise ApiError(
                503,
                "GENERATOR_MISCONFIGURED",
                "The Allocator is not set up to reach the Timetable Generator. Contact the administrator.",
            )
        if response.status_code == 404:
            raise ApiError(404, "NOT_FOUND", "The Timetable Generator has no such term.")
        if response.status_code >= 400:
            logger.warning("Generator GET %s answered %s", path, response.status_code)
            raise ApiError(
                503, "GENERATOR_UNAVAILABLE", "The Timetable Generator could not answer. Try again."
            )
        body = response.json()
        return body.get("data") if isinstance(body, dict) and "success" in body else body

    def terms(self) -> list[dict[str, Any]]:
        return list(self._get("/terms") or [])

    def times(self, term_id: str) -> dict[str, Any]:
        """The Director's latest published version: when and where each class (by key) meets."""
        return dict(self._get(f"/terms/{term_id}/times") or {})


_client: GeneratorClient | None = None
_client_lock = threading.Lock()


def get_generator() -> GeneratorClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = GeneratorClient(get_settings())
        return _client


def set_generator(client: GeneratorClient | None) -> None:
    """Swaps the shared client (tests)."""
    global _client
    with _client_lock:
        _client = client
