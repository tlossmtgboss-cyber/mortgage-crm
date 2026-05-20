"""Perennia AI — official Python SDK.

Minimal read-only client for the public REST surface. The full SDK will
grow alongside the public API, but the contract guaranteed today is:

    >>> from perennia_ai import Client
    >>> client = Client(api_key="sk_live_...")
    >>> client.leads.list()
    >>> client.leads.get("lead_123")
    >>> client.loans.list()
    >>> client.loans.get(42)
    >>> client.calls.list()

All requests use a ``Bearer`` token (``Authorization: Bearer <api_key>``)
and target ``https://api.perenniaai.com`` by default. Pass
``base_url=...`` to point at a staging or self-hosted instance.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Union
from urllib.parse import urlencode

try:  # Optional dependency — only imported when actually making requests.
    import urllib.request as _urlreq
    import urllib.error as _urlerr
    import json as _json
except ImportError:  # pragma: no cover
    _urlreq = None  # type: ignore[assignment]


__version__ = "0.1.0"
__all__ = ["Client", "PerenniaError"]

DEFAULT_BASE_URL = "https://api.perenniaai.com"
USER_AGENT = f"perennia-ai-python/{__version__}"


class PerenniaError(Exception):
    """Base error for SDK failures (network, HTTP, or decoding)."""

    def __init__(self, message: str, *, status: Optional[int] = None,
                 body: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.body = body


# ---------------------------------------------------------------------------
# Low-level HTTP helper
# ---------------------------------------------------------------------------
class _HTTP:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self.base_url + path
        if params:
            url += "?" + urlencode({k: v for k, v in params.items() if v is not None})
        req = _urlreq.Request(url, headers=self._headers(), method="GET")
        try:
            with _urlreq.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read().decode("utf-8")
                return _json.loads(payload) if payload else None
        except _urlerr.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise PerenniaError(
                f"HTTP {exc.code} for {path}", status=exc.code, body=body,
            ) from exc
        except _urlerr.URLError as exc:
            raise PerenniaError(f"Network error: {exc}") from exc


# ---------------------------------------------------------------------------
# Resource namespaces
# ---------------------------------------------------------------------------
class _Leads:
    def __init__(self, http: _HTTP):
        self._http = http

    def list(self, *, limit: int = 50, cursor: Optional[str] = None) -> Any:
        return self._http.get("/api/v1/leads", params={"limit": limit, "cursor": cursor})

    def get(self, lead_id: Union[str, int]) -> Any:
        return self._http.get(f"/api/v1/leads/{lead_id}")


class _Loans:
    def __init__(self, http: _HTTP):
        self._http = http

    def list(self, *, stage: Optional[str] = None, limit: int = 50) -> Any:
        return self._http.get(
            "/api/v1/loans", params={"stage": stage, "limit": limit},
        )

    def get(self, loan_id: Union[str, int]) -> Any:
        return self._http.get(f"/api/v1/loans/{loan_id}")


class _Calls:
    def __init__(self, http: _HTTP):
        self._http = http

    def list(self, *, limit: int = 50, since: Optional[str] = None) -> Any:
        return self._http.get(
            "/api/v1/calls", params={"limit": limit, "since": since},
        )


# ---------------------------------------------------------------------------
# Public client
# ---------------------------------------------------------------------------
class Client:
    """Perennia AI API client.

    Parameters
    ----------
    api_key:
        Bearer token issued from the Perennia dashboard.
    base_url:
        Override for self-hosted or staging deployments.
    timeout:
        Per-request timeout in seconds (default: 30s).
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ):
        if not api_key:
            raise ValueError("api_key is required")
        self._http = _HTTP(base_url=base_url, api_key=api_key, timeout=timeout)
        self.leads = _Leads(self._http)
        self.loans = _Loans(self._http)
        self.calls = _Calls(self._http)

    @property
    def base_url(self) -> str:
        return self._http.base_url

    @property
    def api_key(self) -> str:
        return self._http.api_key
