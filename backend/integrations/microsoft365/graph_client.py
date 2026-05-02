"""Thin async wrapper over Microsoft Graph with retry, backoff, and 429 handling."""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx
from sqlalchemy.orm import Session

from .auth import get_valid_access_token
from .config import GRAPH_BASE_URL, get_settings
from .models import MSAccount

log = logging.getLogger(__name__)


class GraphAPIError(Exception):
    def __init__(self, status: int, message: str, body: Any = None):
        super().__init__(f"Graph {status}: {message}")
        self.status = status
        self.body = body


class GraphClient:
    """Per-account async Graph client.

    Use as an async context manager:
        async with GraphClient(db, account) as gc:
            me = await gc.get("/me")
    """

    def __init__(self, db: Session, account: MSAccount):
        self.db = db
        self.account = account
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None

    async def __aenter__(self) -> "GraphClient":
        self._client = httpx.AsyncClient(
            base_url=GRAPH_BASE_URL,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
        self._token = await get_valid_access_token(self.db, self.account)
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        absolute_url: bool = False,
    ) -> httpx.Response:
        assert self._client is not None and self._token is not None
        s = get_settings()

        url = path
        attempt = 0
        backoff = s.graph_initial_backoff_ms / 1000

        while True:
            attempt += 1
            req_headers = {
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                **(headers or {}),
            }
            try:
                if absolute_url:
                    resp = await self._client.request(
                        method, url, params=params, json=json, headers=req_headers,
                    )
                else:
                    resp = await self._client.request(
                        method, path, params=params, json=json, headers=req_headers,
                    )
            except httpx.TransportError as exc:
                if attempt >= s.graph_max_retries:
                    raise GraphAPIError(0, f"Transport error after retries: {exc}") from exc
                await asyncio.sleep(backoff + random.uniform(0, 0.1))
                backoff = min(backoff * 2, s.graph_max_backoff_ms / 1000)
                continue

            if resp.status_code < 400:
                return resp

            if resp.status_code == 401 and attempt == 1:
                self._token = await get_valid_access_token(self.db, self.account)
                continue

            if resp.status_code in (429, 503):
                if attempt >= s.graph_max_retries:
                    raise GraphAPIError(resp.status_code, "Throttled", _safe_body(resp))
                retry_after = float(resp.headers.get("Retry-After", "0"))
                wait = max(retry_after, backoff)
                log.warning(
                    "Graph throttled (status=%s) attempt=%s — sleeping %.2fs",
                    resp.status_code, attempt, wait,
                )
                await asyncio.sleep(wait + random.uniform(0, 0.25))
                backoff = min(backoff * 2, s.graph_max_backoff_ms / 1000)
                continue

            if 500 <= resp.status_code < 600 and attempt < s.graph_max_retries:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, s.graph_max_backoff_ms / 1000)
                continue

            raise GraphAPIError(resp.status_code, resp.reason_phrase, _safe_body(resp))

    async def get(self, path: str, *, params: dict | None = None) -> dict:
        resp = await self._request("GET", path, params=params)
        return resp.json()

    async def get_absolute(self, url: str) -> dict:
        resp = await self._request("GET", url, absolute_url=True)
        return resp.json()

    async def post(self, path: str, *, json: Any) -> dict:
        resp = await self._request("POST", path, json=json)
        return resp.json() if resp.content else {}

    async def patch(self, path: str, *, json: Any) -> dict:
        resp = await self._request("PATCH", path, json=json)
        return resp.json() if resp.content else {}

    async def delete(self, path: str) -> None:
        await self._request("DELETE", path)

    async def iterate(
        self, path: str, *, params: dict | None = None, max_pages: int = 50
    ) -> list[dict]:
        results: list[dict] = []
        page = await self.get(path, params=params)
        for _ in range(max_pages):
            results.extend(page.get("value", []))
            next_link = page.get("@odata.nextLink")
            if not next_link:
                break
            page = await self.get_absolute(next_link)
        return results


def _safe_body(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text[:500]
