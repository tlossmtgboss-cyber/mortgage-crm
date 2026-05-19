"""
Slybroadcast Webhook Routes (TCPA-D4)

Receives delivery-status callbacks from Slybroadcast's ringless voicemail
gateway and updates the matching VoicemailDrop record.

Slybroadcast posts standard application/x-www-form-urlencoded fields:
    c_uid          - Slybroadcast campaign / session id
    c_audio        - URL of the audio file that was played
    c_record_audio - Delivery status (DELIVERED, FAILED, INVALID, ...)
    c_phone        - Recipient phone number (10 or 11 digits)
    c_date         - Date/time of delivery attempt
    c_callerid     - Caller ID used for the drop

The handler is intentionally defensive — Slybroadcast retries on any non-2xx
response, so we always return 200 and log internal errors instead of raising.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from db import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voicemail", tags=["Slybroadcast Webhook"])


# Statuses Slybroadcast reports that should trigger retry consideration
_FAILURE_STATUSES = {
    "FAILED",
    "FAIL",
    "INVALID",
    "INVALID_NUMBER",
    "REJECTED",
    "ERROR",
    "BUSY",
    "NO_VOICEMAIL",
    "TIMEOUT",
}

# How many delivery attempts before we stop retrying
_MAX_RETRY_ATTEMPTS = 3


def _normalize_status(raw: Optional[str]) -> str:
    if not raw:
        return ""
    return raw.strip().upper().replace(" ", "_")


def _looks_like_failure(status: str) -> bool:
    if not status:
        return False
    status_upper = status.upper()
    if status_upper in _FAILURE_STATUSES:
        return True
    # Heuristic fallback: anything containing FAIL/ERROR/INVALID
    return any(token in status_upper for token in ("FAIL", "ERROR", "INVALID", "REJECT"))


@router.post("/slybroadcast/callback")
async def slybroadcast_callback(request: Request):
    """
    Slybroadcast delivery-status webhook.

    Returns 200 with {"ok": True} regardless of internal outcome to prevent
    Slybroadcast from retrying on application-level errors (provider retries
    on any non-2xx response).
    """
    payload: dict = {}
    try:
        # Slybroadcast posts form-encoded data, but we accept JSON too for testing.
        ctype = (request.headers.get("content-type") or "").lower()
        if "application/json" in ctype:
            try:
                payload = await request.json()
            except Exception as _exc:  # noqa: BLE001
                logger.exception("unhandled exception")
                payload = {}
        else:
            try:
                form = await request.form()
                payload = {k: v for k, v in form.items()}
            except Exception as _exc:  # noqa: BLE001
                # Last-ditch: try JSON anyway
                logger.exception("unhandled exception")
                try:
                    payload = await request.json()
                except Exception as _exc:  # noqa: BLE001
                    logger.exception("unhandled exception")
                    payload = {}
    except Exception as parse_err:
        logger.warning("slybroadcast webhook: failed to parse payload: %s", parse_err)
        payload = {}

    c_uid = payload.get("c_uid") or payload.get("session_id") or payload.get("campaign_id")
    c_status_raw = payload.get("c_record_audio") or payload.get("status")
    c_phone = payload.get("c_phone")
    c_audio = payload.get("c_audio")
    c_date = payload.get("c_date")
    c_callerid = payload.get("c_callerid")

    status_norm = _normalize_status(c_status_raw)

    logger.info(
        "slybroadcast webhook: c_uid=%s status=%s phone_last4=%s",
        c_uid,
        status_norm or "<none>",
        str(c_phone)[-4:] if c_phone else "????",
    )

    if not c_uid:
        # Nothing we can correlate against — ack and bail.
        return JSONResponse(status_code=200, content={"ok": True, "note": "no_c_uid"})

    db: Optional[Session] = None
    try:
        db = SessionLocal()

        # Lazy import — avoids circular import at module load time.
        try:
            import main as _main
            VoicemailDrop = _main.VoicemailDrop
            VoicemailEvent = getattr(_main, "VoicemailEvent", None)
        except Exception as imp_err:
            logger.warning("slybroadcast webhook: VoicemailDrop import failed: %s", imp_err)
            return JSONResponse(status_code=200, content={"ok": True, "note": "model_unavailable"})

        drop = (
            db.query(VoicemailDrop)
            .filter(VoicemailDrop.rvm_session_id == str(c_uid))
            .first()
        )
        if not drop:
            logger.info(
                "slybroadcast webhook: no VoicemailDrop matched rvm_session_id=%s",
                c_uid,
            )
            return JSONResponse(status_code=200, content={"ok": True, "note": "drop_not_found"})

        # Map Slybroadcast status -> internal status string.
        is_failure = _looks_like_failure(status_norm)
        if is_failure:
            drop.status = "failed"
            drop.error_code = status_norm[:50]
            drop.error_message = f"Slybroadcast reported {status_norm}"[:500]
        elif status_norm in ("DELIVERED", "OK", "SUCCESS", "COMPLETED"):
            drop.status = "delivered"
            drop.delivered_at = datetime.now(timezone.utc)
        else:
            # Informational update — preserve current status but record dispo
            pass

        # Persist Slybroadcast disposition code regardless of branch.
        if status_norm:
            drop.rvm_dispo_code = status_norm[:50]

        # Retry logic: use delivery_attempts as the retry counter
        # (VoicemailDrop has no dedicated retry_count column).
        retry_action = "none"
        if is_failure:
            current_attempts = int(drop.delivery_attempts or 0)
            if current_attempts < _MAX_RETRY_ATTEMPTS:
                # No worker queue exists yet — log per spec.
                logger.info(
                    "slybroadcast webhook: retry scheduled for drop_id=%s "
                    "(attempt %s of %s)",
                    drop.id,
                    current_attempts + 1,
                    _MAX_RETRY_ATTEMPTS,
                )
                drop.retry_scheduled_at = datetime.now(timezone.utc)
                retry_action = "scheduled"
            else:
                logger.info(
                    "slybroadcast webhook: drop_id=%s exhausted retries (%s)",
                    drop.id,
                    current_attempts,
                )
                retry_action = "exhausted"

        # Write an event row if the model is available.
        if VoicemailEvent is not None:
            try:
                event = VoicemailEvent(
                    voicemail_drop_id=drop.id,
                    event_type="slybroadcast_callback",
                    event_data={
                        "status": status_norm,
                        "c_uid": str(c_uid),
                        "c_phone_last4": str(c_phone)[-4:] if c_phone else None,
                        "c_audio": (str(c_audio)[:300] if c_audio else None),
                        "c_date": str(c_date) if c_date else None,
                        "c_callerid": str(c_callerid) if c_callerid else None,
                        "retry_action": retry_action,
                    },
                )
                db.add(event)
            except Exception as evt_err:
                logger.warning("slybroadcast webhook: failed to insert event: %s", evt_err)

        try:
            db.commit()
        except Exception as commit_err:
            logger.error("slybroadcast webhook: commit failed: %s", commit_err)
            try:
                db.rollback()
            except Exception as _exc:  # noqa: BLE001
                pass

        return JSONResponse(status_code=200, content={"ok": True})

    except Exception as exc:
        # Never 500 — Slybroadcast retries non-2xx and we don't want duplicate updates.
        logger.exception("slybroadcast webhook: unexpected error: %s", exc)
        return JSONResponse(status_code=200, content={"ok": True, "note": "internal_error"})
    finally:
        if db is not None:
            try:
                db.close()
            except Exception as _exc:  # noqa: BLE001
                pass
