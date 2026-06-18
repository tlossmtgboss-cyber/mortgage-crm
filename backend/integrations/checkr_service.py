"""
Checkr Background Check Integration.
Set CHECKR_API_KEY (Railway env var) to activate.
Without the key all functions return a graceful fallback dict.
Checkr REST API v1: https://api.checkr.com/v1/
"""

import os
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

_CHECKR_BASE = "https://api.checkr.com/v1"
_API_KEY = os.environ.get("CHECKR_API_KEY", "")


async def create_background_check(
    candidate: dict,
    package: str = "tasker_standard",
) -> dict:
    """
    Create a Checkr invitation (candidate self-completes the check via the returned URL).
    candidate dict keys used: email, first_name, last_name, dob (optional, ISO date str).
    Returns {"report_id", "invitation_url", "status"} or fallback dict.
    """
    if not _API_KEY:
        logger.info("CHECKR_API_KEY not set — background check skipped")
        return {
            "report_id": None,
            "invitation_url": None,
            "fallback": True,
            "reason": "Background check not configured",
        }

    payload = {
        "package": package,
        "candidate": {
            "email": candidate.get("email", ""),
            "first_name": candidate.get("first_name", ""),
            "last_name": candidate.get("last_name", ""),
        },
    }
    if candidate.get("dob"):
        payload["candidate"]["dob"] = candidate["dob"]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_CHECKR_BASE}/invitations",
                auth=(_API_KEY, ""),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "report_id": data.get("id"),
            "invitation_url": data.get("invitation_url"),
            "status": "pending",
        }

    except httpx.HTTPStatusError as exc:
        logger.error("Checkr API error %s: %s", exc.response.status_code, exc.response.text)
        return {
            "report_id": None,
            "invitation_url": None,
            "fallback": True,
            "reason": f"Checkr API error: {exc.response.status_code}",
        }
    except Exception as exc:
        logger.exception("Unexpected Checkr error: %s", exc)
        return {
            "report_id": None,
            "invitation_url": None,
            "fallback": True,
            "reason": str(exc),
        }


async def get_report_status(report_id: str) -> dict:
    """
    Fetch a Checkr report by ID.
    Returns {"status", "completed_at", "result"}.
    Statuses: pending | clear | consider | suspended | dispute | pre_adverse_action | adverse_action | canceled.
    """
    if not _API_KEY or not report_id:
        return {"status": "unknown", "completed_at": None, "result": ""}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{_CHECKR_BASE}/reports/{report_id}",
                auth=(_API_KEY, ""),
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "status": data.get("status", "pending"),
            "completed_at": data.get("completed_at"),
            "result": data.get("result", ""),
        }

    except Exception as exc:
        logger.exception("Error fetching Checkr report %s: %s", report_id, exc)
        return {"status": "unknown", "completed_at": None, "result": ""}


async def handle_webhook(payload: dict) -> dict:
    """
    Parse a Checkr webhook payload.
    Handles report.completed (and related) events.
    Returns {"report_id", "status", "candidate_id"}.
    """
    event_type = payload.get("type", "")
    data = payload.get("data", {})
    object_data = data.get("object", data)  # Checkr wraps data in object key sometimes

    report_id = object_data.get("id", "")
    status = object_data.get("status", "")
    candidate_id = object_data.get("candidate_id")

    return {
        "report_id": report_id,
        "status": status,
        "candidate_id": candidate_id,
        "event_type": event_type,
    }
