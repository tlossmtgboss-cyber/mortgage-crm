"""
Telnyx SMS Helper — **Single chokepoint** for ALL outbound SMS.

Every SMS in the system MUST flow through ``send_sms_verified()`` (or its
backward-compatible alias ``send_sms()``).  This guarantees:

1. TCPA / DNC compliance gate (fail-closed by default)
2. Audit-trail logging when compliance is bypassed

The telnyx v2 Python SDK (v4.x) uses a client-based API::

    client = telnyx.Telnyx(api_key=...)
    client.messages.send(to=..., from_=..., text=..., ...)

Direct callers of the Telnyx HTTP API or SDK outside this module are
considered violations of the SMS architecture.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any, Dict, List, Optional

from telephony.phone_utils import normalize_phone as _normalize_phone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level lazy singleton for the Telnyx client
# ---------------------------------------------------------------------------
_client = None
_client_lock = threading.Lock()


def _get_client(api_key: Optional[str] = None):
    """Return a Telnyx client, creating one lazily if needed.

    If *api_key* is provided it takes precedence; otherwise the
    ``TELNYX_API_KEY`` environment variable is used.
    """
    global _client

    key = (api_key or os.getenv("TELNYX_API_KEY", "")).strip()
    if not key:
        return None

    # Fast path — already initialised with the same key
    if _client is not None and getattr(_client, "api_key", None) == key:
        return _client

    with _client_lock:
        # Double-check after acquiring lock
        if _client is not None and getattr(_client, "api_key", None) == key:
            return _client
        try:
            import telnyx
            _client = telnyx.Telnyx(api_key=key, timeout=10.0)
            return _client
        except Exception:
            logger.exception("Failed to initialise Telnyx client")
            return None


# ---------------------------------------------------------------------------
# Raw send (private) — only used by the verified chokepoint
# ---------------------------------------------------------------------------

def _send_sms_raw(
    *,
    to: str,
    from_: str,
    text: str,
    messaging_profile_id: Optional[str] = None,
    media_urls: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an SMS via the Telnyx v2 SDK.  **Private** — all external
    callers should use ``send_sms_verified()`` instead.

    This function:
    - Does NOT run compliance checks
    - DOES call the Telnyx SDK

    Returns ``{"id": "<message_id>", "status": "sent"}``.
    """
    client = _get_client(api_key)
    if client is None:
        raise RuntimeError("Telnyx client not available — check TELNYX_API_KEY")

    kwargs: Dict[str, Any] = {
        "to": to,
        "from_": from_,
        "text": text,
    }
    if messaging_profile_id:
        kwargs["messaging_profile_id"] = messaging_profile_id
    if media_urls:
        kwargs["media_urls"] = media_urls

    response = client.messages.send(**kwargs)

    # The v4.x SDK returns MessageSendResponse with .data.id (not .id)
    data = getattr(response, "data", None)
    msg_id = getattr(data, "id", None) or "unknown"
    if msg_id == "unknown":
        logger.warning("Telnyx SDK response missing message ID — delivery tracking will be unreliable (to=...%s)", to[-4:])
    return {"id": str(msg_id), "status": "sent"}


# ---------------------------------------------------------------------------
# Raw async send via HTTP (for callers that need async, no SDK dependency)
# ---------------------------------------------------------------------------

async def _send_sms_raw_async(
    *,
    to: str,
    from_: str,
    text: str,
    messaging_profile_id: Optional[str] = None,
    media_urls: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Async SMS send via Telnyx HTTP API.  **Private** — use
    ``send_sms_verified_async()`` for the compliance-enforcing variant.

    Returns ``{"id": "<message_id>", "status": "sent"}``.
    """
    import httpx

    key = (api_key or os.getenv("TELNYX_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("Telnyx API key not available — check TELNYX_API_KEY")

    payload: Dict[str, Any] = {
        "to": to,
        "from": from_,
        "text": text,
    }
    if messaging_profile_id:
        payload["messaging_profile_id"] = messaging_profile_id
    if media_urls:
        payload["media_urls"] = media_urls

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.telnyx.com/v2/messages",
            json=payload,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        )

    if resp.status_code >= 400:
        raise RuntimeError(f"Telnyx send failed {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    msg_id = data.get("data", {}).get("id", "unknown")
    if msg_id == "unknown":
        logger.warning("Telnyx HTTP response missing message ID — delivery tracking will be unreliable (to=...%s)", to[-4:])
    return {"id": str(msg_id), "status": "sent"}


# ---------------------------------------------------------------------------
# Archive helper — writes to delivery log + SMS panel (best-effort)
# ---------------------------------------------------------------------------

def _record_to_panel(
    msg_id: str,
    to_phone: str,
    from_phone: str,
    message_body: str,
    lead_id: Optional[int] = None,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
) -> None:
    """Best-effort write to sms_delivery_log + sms_panel_messages.

    Called by send_sms_verified() and send_sms_verified_async() after a
    successful send.  Callers that already write via record_message_sent()
    will hit ON CONFLICT (id) DO NOTHING — no duplicates.
    """
    try:
        from db import SessionLocal
        _db = SessionLocal()
        try:
            from integrations.sms_delivery_tracker import record_message_sent
            record_message_sent(
                _db, str(msg_id), to_phone, from_phone,
                message_body,
                lead_id=lead_id,
                user_id=user_id,
                organization_id=organization_id,
            )
            _db.commit()
        except Exception:
            try:
                _db.rollback()
            except Exception:
                pass
        finally:
            _db.close()
    except Exception as e:
        logger.debug("SMS archive record skipped: %s", e)


# ---------------------------------------------------------------------------
# Public API — VERIFIED (compliance-enforcing chokepoint)
# ---------------------------------------------------------------------------

def send_sms_verified(
    *,
    to: str,
    from_: Optional[str] = None,
    text: str,
    messaging_profile_id: Optional[str] = None,
    media_urls: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    # Compliance context
    user_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db=None,
    bypass_compliance: bool = False,
) -> Dict[str, Any]:
    """**The single mandatory SMS chokepoint.**  ALL outbound SMS in the
    system MUST flow through this function (or its async variant).

    Steps:
    1. Normalize phone number
    2. Run compliance gate (check_sms_compliance) — fail-closed
    3. Call the actual Telnyx send
    4. Return result with message_id for tracking

    Parameters
    ----------
    to : str
        Destination phone number (any format, normalized to E.164).
    from_ : str, optional
        Sending phone number (E.164).  Defaults to ``TELNYX_FROM_NUMBER``.
    text : str
        Message body.
    messaging_profile_id : str, optional
        Telnyx messaging profile ID.  Defaults to ``TELNYX_MESSAGING_PROFILE_ID``.
    media_urls : list[str], optional
        Media URLs for MMS.
    api_key : str, optional
        Telnyx API key override.
    user_id : int, optional
        ID of the user triggering the send (audit trail).
    lead_id : int, optional
        ID of the lead being messaged (compliance lookup).
    organization_id : int, optional
        Org ID for tenant-scoped DNC/consent checks.
    db : Session, optional
        SQLAlchemy session for compliance queries.  If None, compliance
        gate is skipped with a warning (not silently — logged).
    bypass_compliance : bool
        If True, log a warning but still send.  Use ONLY for legally
        required messages (opt-out confirmations, etc.).

    Returns
    -------
    dict
        ``{"id": "<message_id>", "status": "sent"}`` on success, or
        ``{"id": None, "status": "blocked", "reason": "..."}`` if blocked.
    """
    # Defaults from environment
    from_ = from_ or os.getenv("TELNYX_FROM_NUMBER", os.getenv("TELNYX_PHONE_NUMBER", ""))
    messaging_profile_id = messaging_profile_id or os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")

    if not from_:
        raise ValueError("SMS sender phone number not configured — set TELNYX_FROM_NUMBER or TELNYX_PHONE_NUMBER")

    # Normalize destination phone
    normalized = _normalize_phone(to)
    if not normalized:
        return {"id": None, "status": "blocked", "reason": f"Invalid phone number: {to}"}

    # --- Compliance gate ---
    if bypass_compliance:
        logger.warning(
            "SMS compliance BYPASSED for ...%s by user_id=%s lead_id=%s org_id=%s",
            normalized[-4:],
            user_id,
            lead_id,
            organization_id,
        )
    elif db is not None:
        try:
            from integrations.sms_compliance_gate import check_sms_compliance

            compliance = check_sms_compliance(
                db,
                normalized,
                text,
                lead_id=lead_id,
                user_id=user_id,
                organization_id=organization_id,
            )
            if not compliance.allowed:
                logger.info(
                    "SMS to ...%s blocked by compliance: %s",
                    normalized[-4:],
                    compliance.reason,
                )
                return {
                    "id": None,
                    "status": "blocked",
                    "reason": compliance.reason,
                }
        except Exception as e:
            # Fail-closed: if compliance check errors, block the send
            logger.error("Compliance check error, blocking SMS to ...%s: %s", normalized[-4:], e)
            return {
                "id": None,
                "status": "blocked",
                "reason": f"Compliance check error: {e}",
            }
    else:
        # No DB session provided — create a temporary one for compliance
        try:
            from db import SessionLocal
            _temp_db = SessionLocal()
            try:
                from integrations.sms_compliance_gate import check_sms_compliance

                compliance = check_sms_compliance(
                    _temp_db, normalized, text,
                    lead_id=lead_id, user_id=user_id,
                    organization_id=organization_id,
                )
                if not compliance.allowed:
                    logger.info(
                        "SMS to ...%s blocked by compliance (temp session): %s",
                        normalized[-4:], compliance.reason,
                    )
                    return {
                        "id": None,
                        "status": "blocked",
                        "reason": compliance.reason,
                    }
            finally:
                _temp_db.close()
        except Exception as e:
            logger.error(
                "Compliance check error (temp session), blocking SMS to ...%s: %s",
                normalized[-4:], e,
            )
            return {
                "id": None,
                "status": "blocked",
                "reason": f"Compliance check error: {e}",
            }

    # --- Actual send ---
    result = _send_sms_raw(
        to=normalized,
        from_=from_,
        text=text,
        messaging_profile_id=messaging_profile_id or None,
        media_urls=media_urls,
        api_key=api_key,
    )

    # --- Archive: write to delivery log + SMS panel (best-effort) ---
    if result.get("status") == "sent":
        _record_to_panel(
            result.get("id", ""), normalized, from_, text,
            lead_id=lead_id, user_id=user_id,
            organization_id=organization_id,
        )

    return result


async def send_sms_verified_async(
    *,
    to: str,
    from_: Optional[str] = None,
    text: str,
    messaging_profile_id: Optional[str] = None,
    media_urls: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    # Compliance context
    user_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db=None,
    bypass_compliance: bool = False,
) -> Dict[str, Any]:
    """Async variant of ``send_sms_verified()``.  Same compliance
    enforcement, but uses httpx for the Telnyx API call so it can
    be awaited without blocking the event loop.
    """
    # Defaults from environment
    from_ = from_ or os.getenv("TELNYX_FROM_NUMBER", os.getenv("TELNYX_PHONE_NUMBER", ""))
    messaging_profile_id = messaging_profile_id or os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")

    if not from_:
        raise ValueError("SMS sender phone number not configured — set TELNYX_FROM_NUMBER or TELNYX_PHONE_NUMBER")

    # Normalize destination phone
    normalized = _normalize_phone(to)
    if not normalized:
        return {"id": None, "status": "blocked", "reason": f"Invalid phone number: {to}"}

    # --- Compliance gate (same logic as sync version) ---
    if bypass_compliance:
        logger.warning(
            "SMS compliance BYPASSED (async) for ...%s by user_id=%s lead_id=%s org_id=%s",
            normalized[-4:],
            user_id,
            lead_id,
            organization_id,
        )
    elif db is not None:
        try:
            from integrations.sms_compliance_gate import check_sms_compliance

            compliance = check_sms_compliance(
                db,
                normalized,
                text,
                lead_id=lead_id,
                user_id=user_id,
                organization_id=organization_id,
            )
            if not compliance.allowed:
                logger.info(
                    "SMS to ...%s blocked by compliance: %s",
                    normalized[-4:],
                    compliance.reason,
                )
                return {
                    "id": None,
                    "status": "blocked",
                    "reason": compliance.reason,
                }
        except Exception as e:
            logger.error("Compliance check error, blocking SMS to ...%s: %s", normalized[-4:], e)
            return {
                "id": None,
                "status": "blocked",
                "reason": f"Compliance check error: {e}",
            }
    else:
        try:
            from db import SessionLocal
            _temp_db = SessionLocal()
            try:
                from integrations.sms_compliance_gate import check_sms_compliance

                compliance = check_sms_compliance(
                    _temp_db, normalized, text,
                    lead_id=lead_id, user_id=user_id,
                    organization_id=organization_id,
                )
                if not compliance.allowed:
                    logger.info(
                        "SMS (async) to ...%s blocked by compliance (temp session): %s",
                        normalized[-4:], compliance.reason,
                    )
                    return {
                        "id": None,
                        "status": "blocked",
                        "reason": compliance.reason,
                    }
            finally:
                _temp_db.close()
        except Exception as e:
            logger.error(
                "Compliance check error (temp session, async), blocking SMS to ...%s: %s",
                normalized[-4:], e,
            )
            return {
                "id": None,
                "status": "blocked",
                "reason": f"Compliance check error: {e}",
            }

    # --- Actual send (async HTTP) ---
    result = await _send_sms_raw_async(
        to=normalized,
        from_=from_,
        text=text,
        messaging_profile_id=messaging_profile_id or None,
        media_urls=media_urls,
        api_key=api_key,
    )

    # --- Archive: write to delivery log + SMS panel (best-effort) ---
    if result.get("status") == "sent":
        _record_to_panel(
            result.get("id", ""), normalized, from_, text,
            lead_id=lead_id, user_id=user_id,
            organization_id=organization_id,
        )

    return result


# ---------------------------------------------------------------------------
# Backward-compatible alias — ``send_sms`` now routes through the
# compliance chokepoint.  Existing callers that do
# ``from telephony.sms import send_sms`` get compliance for free.
# ---------------------------------------------------------------------------

def send_sms(
    *,
    to: str,
    from_: str = "",
    text: str,
    messaging_profile_id: Optional[str] = None,
    media_urls: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    # New optional compliance params (old callers just ignore them)
    user_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db=None,
    bypass_compliance: bool = False,
) -> Dict[str, Any]:
    """Backward-compatible wrapper — delegates to ``send_sms_verified()``.

    Existing callers that pass ``to``, ``from_``, ``text`` continue to work
    unchanged.  New callers should prefer ``send_sms_verified()`` directly
    for explicit compliance context.
    """
    return send_sms_verified(
        to=to,
        from_=from_ or None,
        text=text,
        messaging_profile_id=messaging_profile_id,
        media_urls=media_urls,
        api_key=api_key,
        user_id=user_id,
        lead_id=lead_id,
        organization_id=organization_id,
        db=db,
        bypass_compliance=bypass_compliance,
    )
