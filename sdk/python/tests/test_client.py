"""Tests for the Perennia AI Python SDK skeleton."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# Allow running this test directly: add sibling perennia_ai package to path.
_SDK_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SDK_DIR))

from perennia_ai import Client, PerenniaError  # noqa: E402


def test_client_init_requires_api_key():
    """An empty api_key must raise ValueError — never silently accept."""
    with pytest.raises(ValueError):
        Client(api_key="")
    c = Client(api_key="sk_test_123")
    assert c.api_key == "sk_test_123"
    assert c.base_url == "https://api.perenniaai.com"


def test_leads_list_signature_and_url():
    """leads.list(limit=...) must hit /api/v1/leads with a Bearer header."""
    c = Client(api_key="sk_test_xyz", base_url="https://api.test")
    captured = {}

    class _FakeResp:
        def read(self): return b'{"data": []}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        return _FakeResp()

    with patch("perennia_ai._urlreq.urlopen", side_effect=_fake_urlopen):
        result = c.leads.list(limit=25)

    assert result == {"data": []}
    assert "/api/v1/leads" in captured["url"]
    assert "limit=25" in captured["url"]


def test_auth_header_is_bearer_token():
    """Every request must carry Authorization: Bearer <api_key>."""
    c = Client(api_key="sk_live_secret", base_url="https://api.test")
    captured = {}

    class _FakeResp:
        def read(self): return b'{}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.headers)
        return _FakeResp()

    with patch("perennia_ai._urlreq.urlopen", side_effect=_fake_urlopen):
        c.loans.list()

    # urllib normalizes header capitalization (e.g. "Authorization").
    auth = {k.lower(): v for k, v in captured["headers"].items()}.get("authorization")
    assert auth == "Bearer sk_live_secret"


def test_http_error_raises_perennia_error():
    """A 404 from the server must surface as PerenniaError with status+body."""
    import urllib.error
    c = Client(api_key="sk_test", base_url="https://api.test")

    def _raise_404(req, timeout=None):
        err = urllib.error.HTTPError(
            req.full_url, 404, "Not Found", {}, None,
        )
        # urllib's HTTPError.read() is what we read in the SDK.
        err.read = lambda: b'{"error": "not found"}'
        raise err

    with patch("perennia_ai._urlreq.urlopen", side_effect=_raise_404):
        with pytest.raises(PerenniaError) as excinfo:
            c.loans.get(999)
    assert excinfo.value.status == 404
    assert "not found" in (excinfo.value.body or "").lower()
