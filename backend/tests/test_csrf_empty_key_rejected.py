"""Regression tests for the CSRF X-API-Key bypass hardening.

Verifies that the X-API-Key CSRF bypass cannot be triggered by:
  - an empty / missing X-API-Key header
  - a short (< 32 char) X-API-Key header
  - any header value when the service key env var is unset

and that a correctly configured key still bypasses CSRF.
"""

import asyncio

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from middleware.csrf_protection import CSRFProtectionMiddleware


def _make_middleware():
    return CSRFProtectionMiddleware(Starlette())


def _make_request(headers: dict) -> Request:
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()
    ]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/leads/",
        "headers": raw_headers,
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "scheme": "https",
        "server": ("testserver", 443),
    }
    return Request(scope)


async def _dispatch(mw: CSRFProtectionMiddleware, request: Request) -> Response:
    async def call_next(_req):
        return Response(status_code=200)

    return await mw.dispatch(request, call_next)


def _run(coro):
    return asyncio.run(coro)


def test_empty_api_key_with_unset_env_is_rejected(monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.delenv("CRM_API_KEY", raising=False)
    mw = _make_middleware()
    resp = _run(_dispatch(mw, _make_request({"X-API-Key": ""})))
    assert resp.status_code == 403


def test_short_api_key_is_rejected(monkeypatch):
    # A short configured key must not be matchable via a short header either.
    monkeypatch.setenv("ADMIN_API_KEY", "short")
    monkeypatch.delenv("CRM_API_KEY", raising=False)
    mw = _make_middleware()
    resp = _run(_dispatch(mw, _make_request({"X-API-Key": "short"})))
    assert resp.status_code == 403


def test_arbitrary_long_key_with_unset_env_is_rejected(monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.delenv("CRM_API_KEY", raising=False)
    mw = _make_middleware()
    resp = _run(_dispatch(mw, _make_request({"X-API-Key": "x" * 40})))
    assert resp.status_code == 403


def test_valid_api_key_bypasses_csrf(monkeypatch):
    valid_key = "k" * 40
    monkeypatch.setenv("ADMIN_API_KEY", valid_key)
    monkeypatch.delenv("CRM_API_KEY", raising=False)
    mw = _make_middleware()
    resp = _run(_dispatch(mw, _make_request({"X-API-Key": valid_key})))
    assert resp.status_code == 200
