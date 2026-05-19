"""
Golden test: pipeline endpoint performance + structure.

GET /pipeline must:
  - return within 2 seconds (perf SLA for the LO daily dashboard)
  - include leads / active / mum buckets in the response

The 2-second budget is generous; the actual production SLA is sub-500ms.
"""
from __future__ import annotations

import time

import pytest


PIPELINE_PATHS = [
    "/pipeline",
    "/api/pipeline",
    "/api/v1/pipeline",
    "/dashboard/pipeline",
]

EXPECTED_BUCKETS = {"leads", "active", "mum"}


def _find_pipeline(http):
    for p in PIPELINE_PATHS:
        r = http.get(p)
        if r.status_code != 404:
            return p, r
    return PIPELINE_PATHS[0], None


@pytest.mark.xfail(
    reason="TODO: pipeline endpoint requires authenticated session + seeded loans"
)
def test_pipeline_returns_within_two_seconds(authenticated_client):
    http = authenticated_client
    path, _probe = _find_pipeline(http)

    start = time.perf_counter()
    resp = http.get(path)
    elapsed = time.perf_counter() - start

    assert resp.status_code == 200, resp.text
    assert elapsed < 2.0, f"GET {path} took {elapsed:.2f}s (>2s SLA)"


@pytest.mark.xfail(
    reason="TODO: confirm pipeline payload shape once endpoint is wired in tests"
)
def test_pipeline_response_contains_expected_buckets(authenticated_client):
    http = authenticated_client
    path, _ = _find_pipeline(http)

    resp = http.get(path)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Accept either flat keys or nested under "buckets" / "categories"
    keyset = set()
    if isinstance(body, dict):
        keyset.update(k.lower() for k in body.keys())
        for nest_key in ("buckets", "categories", "pipeline"):
            nested = body.get(nest_key)
            if isinstance(nested, dict):
                keyset.update(k.lower() for k in nested.keys())

    missing = EXPECTED_BUCKETS - keyset
    assert not missing, f"pipeline payload missing buckets {missing}; got keys {keyset}"
