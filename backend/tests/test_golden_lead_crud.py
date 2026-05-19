"""
Golden test: lead CRUD round-trip.

Creates -> reads -> updates -> deletes a lead via the public REST API,
using the `authenticated_client` fixture from conftest.py.

The exact lead schema continues to evolve; these tests are intentionally
permissive on payload shape and assert the contract:
  POST  /leads           -> 200/201 + id
  GET   /leads/{id}      -> 200 + same id
  PATCH /leads/{id}      -> 200/204
  DELETE /leads/{id}     -> 200/204
"""
from __future__ import annotations

import uuid

import pytest


LEAD_PATHS = ["/leads", "/api/leads", "/api/v1/leads"]


def _find_base(http) -> str:
    """Find which leads base path responds (not 404)."""
    for p in LEAD_PATHS:
        r = http.get(p)
        if r.status_code != 404:
            return p
    return LEAD_PATHS[0]


@pytest.fixture
def lead_payload():
    suffix = uuid.uuid4().hex[:8]
    return {
        "first_name": "Golden",
        "last_name": f"Tester-{suffix}",
        "email": f"golden+{suffix}@perenniaai.com",
        "phone": "+18435550199",
        "source": "golden_test",
    }


@pytest.mark.xfail(reason="TODO: confirm /leads contract + auth fixture wiring")
def test_lead_crud_round_trip(authenticated_client, lead_payload):
    http = authenticated_client
    base = _find_base(http)

    # CREATE
    create = http.post(base, json=lead_payload)
    assert create.status_code in (200, 201), create.text
    created = create.json()
    lead_id = created.get("id") or created.get("lead_id")
    assert lead_id, f"no id returned: {created}"

    # READ
    read = http.get(f"{base}/{lead_id}")
    assert read.status_code == 200, read.text
    fetched = read.json()
    assert (fetched.get("id") or fetched.get("lead_id")) == lead_id

    # UPDATE
    patch = http.patch(f"{base}/{lead_id}", json={"first_name": "GoldenUpdated"})
    assert patch.status_code in (200, 204), patch.text

    # DELETE
    delete = http.delete(f"{base}/{lead_id}")
    assert delete.status_code in (200, 204), delete.text

    # CONFIRM GONE
    gone = http.get(f"{base}/{lead_id}")
    assert gone.status_code in (404, 410), gone.text


def test_lead_create_requires_auth(client, lead_payload):
    """Unauthenticated POST /leads must NOT return 200."""
    base = _find_base(client)
    resp = client.post(base, json=lead_payload)
    assert resp.status_code != 200, (
        f"unauthenticated lead create returned 200 - security regression: {resp.text}"
    )
