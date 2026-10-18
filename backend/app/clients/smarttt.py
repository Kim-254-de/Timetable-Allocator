"""
Client for SMARTTT's Allocator endpoints (/api/v1/integrations/allocator/),
authenticated with this system's own shared key (X-API-Key).

SMARTTT is the truth for the published timetable and for who teaches what.
Reads are cached for at most SMARTTT_CACHE_SECONDS (<= 60 s); writes clear
the cache, and callers that are about to check something before a write
pass `fresh=True`.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

PREFIX = "/api/v1/integrations/allocator"


class SmartttError(Exception):
    """Base class; `message` is safe to show to users."""

    message = "The timetable system (SMARTTT) could not be reached. Please try again shortly."


class SmartttUnavailable(SmartttError):
    pass


class SmartttMisconfigured(SmartttError):
    """SMARTTT refused our key: ALLOCATOR_API_KEY there and SMARTTT_API_KEY here differ."""

    message = "The Allocator is not connected to SMARTTT correctly. Please contact the system administrator."


class SmartttNotFound(SmartttError):
    def __init__(self, detail: str = "Not found in SMARTTT."):
        super().__init__(detail)
        self.message = detail


class SmartttRefused(SmartttError):
    """SMARTTT refused a write (400/409): `code` and `body` say why."""

    def __init__(self, status: int, body: dict[str, Any]):
        super().__init__(body.get("detail") or "SMARTTT refused the change.")
        self.status = status
        self.code = str(body.get("code") or "refused")
        self.body = body
        self.message = str(body.get("detail") or "SMARTTT refused the change.")


class _TTLCache:
    def __init__(self) -> None:
        self._data: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple[str, tuple[tuple[str, str], ...]], ttl: float) -> Any | None:
        with self._lock:
            hit = self._data.get(key)
            if hit is None or time.monotonic() - hit[0] > ttl:
                return None
            return hit[1]

    def put(self, key: tuple[str, tuple[tuple[str, str], ...]], value: Any) -> None:
        with self._lock:
            self._data[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class SmartttClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self._settings = settings
        self._cache = _TTLCache()
        self._http = httpx.Client(
            base_url=settings.smarttt_base_url.rstrip("/"),
            timeout=settings.smarttt_timeout_seconds,
            headers={"X-API-Key": settings.smarttt_api_key, "Accept": "application/json"},
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def clear_cache(self) -> None:
        self._cache.clear()

    # -- plumbing ------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        clean = {k: str(v) for k, v in (params or {}).items() if v is not None}
        try:
            response = self._http.request(method, PREFIX + path, params=clean, json=json)
        except httpx.HTTPError as exc:
            logger.warning("SMARTTT %s %s failed: %s", method, path, exc)
            raise SmartttUnavailable() from exc
        if response.status_code in (401, 403):
            logger.error(
                "SMARTTT refused the Allocator's API key (%s %s -> %s)", method, path, response.status_code
            )
            raise SmartttMisconfigured()
        if response.status_code >= 500:
            logger.warning("SMARTTT %s %s answered %s", method, path, response.status_code)
            raise SmartttUnavailable()
        return response

    def _get(self, path: str, params: dict[str, Any] | None = None, *, fresh: bool = False) -> Any:
        key = (path, tuple(sorted((k, str(v)) for k, v in (params or {}).items() if v is not None)))
        ttl = self._settings.smarttt_cache_seconds
        if not fresh and ttl:
            cached = self._cache.get(key, ttl)
            if cached is not None:
                return cached
        response = self._request("GET", path, params=params)
        if response.status_code == 404:
            raise SmartttNotFound(_detail(response) or "Not found in SMARTTT.")
        if response.status_code >= 400:
            raise SmartttRefused(response.status_code, _body(response))
        data = response.json()
        if ttl:
            self._cache.put(key, data)
        return data

    # -- sign-in ---------------------------------------------------------------

    def authenticate(self, identifier: str, password: str) -> dict[str, Any] | None:
        """The identity for a correct SMARTTT login, None for wrong credentials."""
        response = self._request(
            "POST", "/authenticate/", json={"identifier": identifier, "password": password}
        )
        if response.status_code >= 400:
            raise SmartttRefused(response.status_code, _body(response))
        body = response.json()
        if not body.get("authenticated"):
            return None
        body.pop("authenticated", None)
        return dict(body)

    def identity(self, account_id: str) -> dict[str, Any] | None:
        """The current identity for an account, None when it is gone or inactive."""
        response = self._request("GET", "/identity/", params={"account_id": account_id})
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise SmartttRefused(response.status_code, _body(response))
        return dict(response.json())

    # -- reads -----------------------------------------------------------------

    def terms(self) -> list[dict[str, Any]]:
        return list(self._get("/terms/")["terms"])

    def departments(self) -> list[dict[str, Any]]:
        return list(self._get("/departments/")["departments"])

    def sections(self, department_id: int, term_id: str | None, *, fresh: bool = False) -> dict[str, Any]:
        return dict(self._get("/sections/", {"department": department_id, "term": term_id}, fresh=fresh))

    def section(self, key: str, term_id: str | None, *, fresh: bool = False) -> dict[str, Any]:
        return dict(self._get(f"/sections/{_path(key)}/", {"term": term_id}, fresh=fresh))

    def lecturers(
        self, department_id: int | None, term_id: str | None, *, fresh: bool = False
    ) -> list[dict[str, Any]]:
        data = self._get("/lecturers/", {"department": department_id, "term": term_id}, fresh=fresh)
        return list(data["lecturers"])

    def lecturer_sessions(
        self, lecturer_id: str, term_id: str | None, *, fresh: bool = False
    ) -> dict[str, Any]:
        return dict(self._get(f"/lecturers/{_path(lecturer_id)}/sessions/", {"term": term_id}, fresh=fresh))

    # -- writes ----------------------------------------------------------------

    def set_lecturer(
        self, key: str, term_id: str, lecturer_id: str | None, expected_lecturer_id: str | None
    ) -> dict[str, Any]:
        """
        Sets the section's lecturer in SMARTTT, which re-checks clashes and
        weekly hours under a lock. Raises SmartttRefused (code lecturer_clash,
        max_hours, stale, unknown_lecturer) when it says no.
        """
        try:
            response = self._request(
                "PATCH",
                f"/sections/{_path(key)}/lecturer/",
                params={"term": term_id},
                json={"lecturer_id": lecturer_id, "expected_lecturer_id": expected_lecturer_id},
            )
        finally:
            self._cache.clear()
        if response.status_code == 404:
            raise SmartttNotFound(_detail(response) or "No such class in this term.")
        if response.status_code >= 400:
            raise SmartttRefused(response.status_code, _body(response))
        return dict(response.json())


def _path(segment: str) -> str:
    return quote(segment, safe="")


def _body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {"detail": response.text[:200]}
    return body if isinstance(body, dict) else {"detail": str(body)[:200]}


def _detail(response: httpx.Response) -> str:
    return str(_body(response).get("detail") or "")


_client: SmartttClient | None = None
_client_lock = threading.Lock()


def get_smarttt() -> SmartttClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = SmartttClient(get_settings())
        return _client


def set_smarttt(client: SmartttClient | None) -> None:
    """Swaps the shared client (tests)."""
    global _client
    with _client_lock:
        _client = client
