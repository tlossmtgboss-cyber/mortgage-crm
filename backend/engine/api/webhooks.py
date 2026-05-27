"""CIE webhook endpoints — receive call events from providers.

NOTE: Production deployments should apply rate limiting at the reverse-proxy
or middleware layer (e.g., nginx limit_req, Cloudflare rate rules).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from engine.config import cie_settings
from engine.models import CIECallRecord
from engine.sources import get_adapter
from engine.sources.base import NormalizedCall
from engine.cipher import encrypt_field
from engine.api.crm import resolve_call_context
from engine.api.schemas import WebhookResponse

logger = logging.getLogger(__name__)
router = APIRouter()

_REPLAY_WINDOW_SECONDS = 600
_REPLAY_MAX_ENTRIES = 10_000
_replay_cache: OrderedDict[str, float] = OrderedDict()
_replay_lock = threading.Lock()


def _check_replay(call_id: str) -> bool:
    """Return True if this call_id was already seen within the replay window."""
    now = time.monotonic()
    with _replay_lock:
        while _replay_cache:
            oldest_key, oldest_ts = next(iter(_replay_cache.items()))
            if now - oldest_ts > _REPLAY_WINDOW_SECONDS:
                _replay_cache.pop(oldest_key)
            else:
                break

        if call_id in _replay_cache:
            return True

        if len(_replay_cache) >= _REPLAY_MAX_ENTRIES:
            _replay_cache.popitem(last=False)

        _replay_cache[call_id] = now
        return False


@router.post(
    "/webhooks/{provider}",
    response_model=WebhookResponse,
    status_code=202,
)
async def receive_webhook(
    provider: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Validate, normalize, persist, and queue a call for analysis."""
    if not cie_settings.ENABLED:
        raise HTTPException(503, "Call Intelligence Engine is disabled")

    # Validate provider
    try:
        adapter = get_adapter(provider)
    except ValueError:
        raise HTTPException(400, f"Unknown provider: {provider}")

    # Read body + signature verify
    body = await request.body()
    headers = dict(request.headers)

    secret = ""
    if provider == "vapi":
        secret = cie_settings.VAPI_WEBHOOK_SECRET
    elif provider == "telnyx":
        secret = cie_settings.TELNYX_WEBHOOK_SECRET

    try:
        adapter.validate_signature(body, headers, secret)
    except ValueError as e:
        raise HTTPException(401, str(e))

    # Parse + normalize
    import json
    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON payload")

    nc: NormalizedCall = adapter.normalize(payload)

    if not nc.external_call_id:
        raise HTTPException(400, "Missing call ID in payload")

    if _check_replay(nc.external_call_id):
        return WebhookResponse(
            call_record_id=None,
            message="Duplicate webhook ignored",
        )

    # Resolve tenant — for Vapi, extract from assistant mapping
    org_id = await _resolve_org_id(provider, payload, db)
    if not org_id:
        raise HTTPException(400, "Could not resolve organization for this call")

    # Idempotency — skip if already persisted
    existing = (
        db.query(CIECallRecord.id)
        .filter(
            CIECallRecord.external_call_id == nc.external_call_id,
            CIECallRecord.organization_id == org_id,
        )
        .first()
    )
    if existing:
        return WebhookResponse(
            call_record_id=existing[0],
            message="Already received",
        )

    # Resolve CRM context
    ctx = resolve_call_context(nc.phone_from or "", org_id, db)

    # Check minimum duration
    too_short = (
        nc.duration_seconds is not None
        and nc.duration_seconds < cie_settings.MIN_ANALYZABLE_SECONDS
    )

    # Persist call record
    record = CIECallRecord(
        external_call_id=nc.external_call_id,
        provider=nc.provider,
        direction=nc.direction,
        phone_from=encrypt_field(nc.phone_from) if nc.phone_from else None,
        phone_to=encrypt_field(nc.phone_to) if nc.phone_to else None,
        started_at=nc.started_at,
        ended_at=nc.ended_at,
        duration_seconds=nc.duration_seconds,
        transcript_encrypted=encrypt_field(nc.transcript) if nc.transcript else None,
        recording_url_encrypted=encrypt_field(nc.recording_url) if nc.recording_url else None,
        raw_payload=payload,
        contact_id=ctx.contact_id,
        loan_id=ctx.loan_id,
        lead_id=ctx.lead_id,
        owner_user_id=ctx.user_id,
        processing_status="too_short" if too_short else "pending",
        organization_id=org_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Dispatch Celery task (unless too short)
    if not too_short:
        try:
            from engine.worker.tasks import process_call_pipeline
            process_call_pipeline.delay(str(record.id))
        except Exception as e:
            logger.error("CIE: failed to dispatch Celery task: %s", e)
            record.processing_status = "failed"
            record.processing_error = f"Task dispatch failed: {e}"
            db.commit()

    return WebhookResponse(
        call_record_id=record.id,
        message="Too short for analysis" if too_short else "Queued for processing",
    )


async def _resolve_org_id(
    provider: str,
    payload: dict[str, Any],
    db: Session,
) -> int | None:
    """Resolve the organization_id from the webhook payload."""
    if provider == "vapi":
        msg = payload.get("message", payload)
        call = msg.get("call", msg)
        assistant_id = call.get("assistantId")
        if assistant_id:
            from sqlalchemy import text
            row = db.execute(
                text("SELECT organization_id FROM vapi_assistants WHERE assistant_id = :aid LIMIT 1"),
                {"aid": assistant_id},
            ).first()
            if row:
                return row[0]
    elif provider == "telnyx":
        data = payload.get("data", payload)
        event_payload = data.get("payload", data)
        to_number = event_payload.get("to")
        if to_number:
            try:
                from sqlalchemy import text
                row = db.execute(
                    text("SELECT organization_id FROM telnyx_phone_numbers WHERE phone_number = :num LIMIT 1"),
                    {"num": to_number},
                ).first()
                if row:
                    return row[0]
            except Exception:
                logger.debug("telnyx_phone_numbers lookup failed; table may not exist")
                db.rollback()
    return None
