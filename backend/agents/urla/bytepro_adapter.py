"""
Perennia AI — BytePro LOS Adapter
=================================
Pushes finalized URLA applications to BytePro via its ULAD import endpoint.

Exposes a single entry point `push_to_bytepro(app, loan_officer)` that:
  1. Serializes the URLAApplication to a ULAD-shaped dict
  2. Transforms to BytePro's expected JSON contract
  3. POSTs to the BytePro API with retry + idempotency
  4. Returns { bytepro_loan_number, status, error }

Configuration:
  BYTEPRO_API_BASE_URL         e.g. https://api.bytepro.perennia.ai
  BYTEPRO_API_KEY              Perennia's service account key
  BYTEPRO_TENANT_ID_HEADER     Header name used by BytePro for tenant scoping
"""
from __future__ import annotations

import os
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from .models import URLAApplication, Section9_LoanOriginator


logger = logging.getLogger("urla.bytepro")


@dataclass
class LoanOfficer:
    name: str
    nmlsr_id: str
    email: str
    phone: str
    organization_name: str = "The Tim Loss Team"
    organization_nmlsr_id: str = ""


@dataclass
class PushResult:
    success: bool
    bytepro_loan_number: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[dict] = None


class BytProConfig:
    def __init__(self):
        self.base_url = os.getenv("BYTEPRO_API_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("BYTEPRO_API_KEY", "")
        self.tenant_header = os.getenv("BYTEPRO_TENANT_ID_HEADER", "X-Tenant-ID")
        self.timeout_seconds = float(os.getenv("BYTEPRO_TIMEOUT", "15"))
        self.max_retries = int(os.getenv("BYTEPRO_MAX_RETRIES", "2"))

    def assert_ready(self) -> None:
        if not self.base_url or not self.api_key:
            raise RuntimeError(
                "BytePro config missing. Set BYTEPRO_API_BASE_URL and BYTEPRO_API_KEY."
            )


async def push_to_bytepro(
    app: URLAApplication,
    loan_officer: LoanOfficer,
    config: Optional[BytProConfig] = None,
) -> PushResult:
    """
    Push a finalized URLA to BytePro.

    The app is expected to already pass `app.validate_complete()` before calling.
    The caller is responsible for populating Section 9 (loan originator) from
    the assigned LO — we do that here if it hasn't been done yet.
    """
    cfg = config or BytProConfig()
    cfg.assert_ready()

    # Populate Section 9 from the assigned LO
    if not app.section_9:
        app.section_9 = Section9_LoanOriginator()
    app.section_9.loan_originator_name = loan_officer.name
    app.section_9.loan_originator_nmlsr_id = loan_officer.nmlsr_id
    app.section_9.loan_originator_email = loan_officer.email
    app.section_9.loan_originator_phone = loan_officer.phone
    app.section_9.loan_originator_organization_name = loan_officer.organization_name
    app.section_9.loan_originator_organization_nmlsr_id = loan_officer.organization_nmlsr_id

    # Build BytePro payload
    payload = _build_bytepro_payload(app)

    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
        cfg.tenant_header: app.tenant_id,
        "X-Idempotency-Key": app.loan_id,  # BytePro should dedupe on retry
        "X-Source-System": "perennia-urla-voice-agent",
    }

    url = f"{cfg.base_url}/v1/loans/import-ulad"

    last_error: Optional[str] = None
    async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
        for attempt in range(1, cfg.max_retries + 1):
            try:
                logger.info(
                    "Pushing URLA to BytePro",
                    extra={"loan_id": app.loan_id, "attempt": attempt},
                )
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200 or resp.status_code == 201:
                    data = resp.json()
                    return PushResult(
                        success=True,
                        bytepro_loan_number=data.get("bytepro_loan_number"),
                        status=data.get("status", "IMPORTED"),
                        raw_response=data,
                    )
                # Don't retry on 4xx
                if 400 <= resp.status_code < 500:
                    return PushResult(
                        success=False,
                        error=f"BytePro rejected payload ({resp.status_code}): {resp.text[:500]}",
                        raw_response=_try_json(resp),
                    )
                last_error = f"BytePro {resp.status_code}: {resp.text[:500]}"
            except httpx.HTTPError as e:
                last_error = f"BytePro transport error: {e}"
                logger.warning("BytePro push failed, will retry", extra={"error": str(e)})

            # Exponential backoff before retry
            await asyncio.sleep(min(2 ** attempt, 4))

    return PushResult(success=False, error=last_error or "Unknown BytePro error")


# ---------------------------------------------------------------------------
# Payload construction — maps URLAApplication to BytePro's expected schema.
# If BytePro uses MISMO XML in your environment, swap this for an XML serializer.
# Kept as JSON here because BytePro v23+ accepts JSON with ULAD field names.
# ---------------------------------------------------------------------------

def _build_bytepro_payload(app: URLAApplication) -> dict:
    return {
        "source": "perennia-voice-urla",
        "source_loan_id": app.loan_id,
        "tenant_id": app.tenant_id,
        "application_channel": "TELEPHONE",
        "captured_at": app.updated_at.isoformat() if app.updated_at else datetime.now(timezone.utc).isoformat(),
        "finalized_at": app.finalized_at.isoformat() if app.finalized_at else None,
        "caller_phone": app.caller_phone,
        "ulad": app.to_ulad_dict(),
        "verbal_consent": {
            "captured": bool(app.section_6 and app.section_6.verbal_consent_given),
            "timestamp": (
                app.section_6.verbal_consent_timestamp.isoformat()
                if app.section_6 and app.section_6.verbal_consent_timestamp
                else None
            ),
            "recording_url": (
                app.section_6.verbal_consent_recording_url
                if app.section_6 else None
            ),
        },
    }


def _try_json(resp: httpx.Response) -> Optional[dict]:
    try:
        return resp.json()
    except Exception as _exc:  # noqa: BLE001
        return None
