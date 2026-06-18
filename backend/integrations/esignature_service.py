"""
E-Signature Service — provider-agnostic offer letter signing.
Supports HelloSign/Dropbox Sign (default) via ESIGN_PROVIDER env var.
Set HELLOSIGN_API_KEY to activate; without it the service returns a graceful fallback.
"""

import os
import hmac
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

_HELLOSIGN_BASE = "https://api.hellosign.com/v3"
_PROVIDER = os.environ.get("ESIGN_PROVIDER", "hellosign")
_API_KEY = os.environ.get("HELLOSIGN_API_KEY", "")


def _build_offer_letter_text(offer_data: dict, candidate_name: str, org_name: str) -> str:
    """Produce a plain-text offer letter body (used as the document sent for signing)."""
    role = offer_data.get("role_title", "the position")
    salary = offer_data.get("salary_amount", "")
    salary_type = offer_data.get("salary_type", "salary")
    start_date = offer_data.get("start_date", "TBD")
    emp_type = offer_data.get("employment_type", "full_time").replace("_", " ").title()
    benefits = offer_data.get("benefits_summary", "As discussed.")
    pto = offer_data.get("pto_days", "")

    compensation_line = f"${salary:,} ({salary_type})" if isinstance(salary, int) else str(salary)

    return f"""OFFER OF EMPLOYMENT

Date: {datetime.now(timezone.utc).strftime('%B %d, %Y')}

Dear {candidate_name},

{org_name} is pleased to offer you the position of {role} on a {emp_type} basis.

Compensation: {compensation_line}
{"PTO: " + str(pto) + " days per year" if pto else ""}
Benefits: {benefits}
Start Date: {start_date}

This offer is contingent upon satisfactory completion of all required verifications.

By signing below you acknowledge and accept the terms of this offer.

_________________________          ________________
{candidate_name} (Candidate)              Date
"""


async def create_offer_envelope(
    offer_data: dict,
    candidate_email: str,
    candidate_name: str,
    org_name: str,
) -> dict:
    """
    Send an offer letter for e-signature via HelloSign.
    Returns {"envelope_id", "signing_url", "expires_at"} on success,
    or {"envelope_id": None, "signing_url": None, "fallback": True, "reason": ...} when unconfigured.
    """
    if not _API_KEY:
        logger.warning("HELLOSIGN_API_KEY not set — e-signature skipped")
        return {
            "envelope_id": None,
            "signing_url": None,
            "fallback": True,
            "reason": "E-signature not configured",
        }

    letter_text = _build_offer_letter_text(offer_data, candidate_name, org_name)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_HELLOSIGN_BASE}/signature_request/send",
                auth=(_API_KEY, ""),
                data={
                    "title": f"Offer Letter — {offer_data.get('role_title', 'Position')}",
                    "subject": f"Your offer from {org_name}",
                    "message": f"Please review and sign your offer letter from {org_name}.",
                    "signers[0][email_address]": candidate_email,
                    "signers[0][name]": candidate_name,
                    "files[0][name]": "offer_letter.txt",
                    "files[0][content_type]": "text/plain",
                    "files[0][content]": letter_text,
                    "signing_redirect_url": os.environ.get(
                        "ESIGN_REDIRECT_URL", "https://app.perenniaai.com/recruiting/offers"
                    ),
                },
            )
            resp.raise_for_status()
            body = resp.json()

        sig_request = body.get("signature_request", {})
        envelope_id = sig_request.get("signature_request_id")

        # Grab first signer's signing URL
        signing_url = None
        signers = sig_request.get("signatures", [])
        if signers:
            signing_url = signers[0].get("sign_url")

        return {
            "envelope_id": envelope_id,
            "signing_url": signing_url,
            "expires_at": expires_at,
        }

    except httpx.HTTPStatusError as exc:
        logger.error("HelloSign API error %s: %s", exc.response.status_code, exc.response.text)
        return {
            "envelope_id": None,
            "signing_url": None,
            "fallback": True,
            "reason": f"HelloSign API error: {exc.response.status_code}",
        }
    except Exception as exc:
        logger.exception("Unexpected error calling HelloSign: %s", exc)
        return {
            "envelope_id": None,
            "signing_url": None,
            "fallback": True,
            "reason": str(exc),
        }


async def get_envelope_status(envelope_id: str) -> dict:
    """
    Poll HelloSign for signature request status.
    Returns {"status", "signed_at"}.
    """
    if not _API_KEY or not envelope_id:
        return {"status": "unknown", "signed_at": None}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{_HELLOSIGN_BASE}/signature_request/{envelope_id}",
                auth=(_API_KEY, ""),
            )
            resp.raise_for_status()
            sig_req = resp.json().get("signature_request", {})

        is_complete = sig_req.get("is_complete", False)
        is_declined = sig_req.get("is_declined", False)

        if is_complete:
            status = "signed"
            # completedAt not always present; fall back to None
            signed_at = sig_req.get("completed_at")
            if isinstance(signed_at, (int, float)):
                signed_at = datetime.fromtimestamp(signed_at, tz=timezone.utc).isoformat()
        elif is_declined:
            status = "declined"
            signed_at = None
        else:
            # Check if any signer has viewed
            signatures = sig_req.get("signatures", [])
            viewed = any(s.get("last_viewed_at") for s in signatures)
            status = "viewed" if viewed else "sent"
            signed_at = None

        return {"status": status, "signed_at": signed_at}

    except Exception as exc:
        logger.exception("Error fetching envelope status %s: %s", envelope_id, exc)
        return {"status": "unknown", "signed_at": None}


async def handle_webhook_event(payload: dict) -> dict:
    """
    Parse a HelloSign webhook payload.
    Returns {"event_type", "envelope_id", "signed"}.
    """
    event = payload.get("event", {})
    event_type = event.get("event_type", "")
    sig_req = payload.get("signature_request", {})
    envelope_id = sig_req.get("signature_request_id", "")

    signed = event_type == "signature_request_signed"

    return {
        "event_type": event_type,
        "envelope_id": envelope_id,
        "signed": signed,
    }


def verify_webhook_signature(raw_body: bytes, header_sig: str) -> bool:
    """Verify X-HelloSign-Signature HMAC-SHA256 header."""
    if not _API_KEY:
        return False
    expected = hmac.new(_API_KEY.encode(), raw_body, hashlib.sha256).hexdigest()  # type: ignore[attr-defined]
    return hmac.compare_digest(expected, header_sig or "")
