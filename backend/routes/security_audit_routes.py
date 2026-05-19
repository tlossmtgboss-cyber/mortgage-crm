"""
Security Audit Log Routes

Receives hash-chained security audit events from the iOS AuditLogger and
persists them to the audit_events table via the audit_event() service.

Endpoint:
  POST /api/v1/security/audit-log — batch-receive audit entries from iOS app

The iOS AuditLogger syncs events in batches of up to 50. Each entry carries
a SHA-256 hash chain for tamper evidence. Chain linkage is verified server-side;
per-entry hash verification is advisory (cross-platform JSON serialization
differences between Swift and Python may cause benign mismatches).

Payload format (from AuditLogger.swift):
    {
        "entries": [
            {
                "id": "UUID-string",
                "timestamp": 1712764800.123,
                "event": "auth.success",
                "details": {"key": "value"},
                "deviceInfo": {
                    "model": "iPhone",
                    "osVersion": "17.4",
                    "appVersion": "1.0.0"
                },
                "synced": true,
                "previousHash": "sha256-hex-string",
                "hash": "sha256-hex-string"
            }
        ]
    }
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user_flexible
from db import get_db
from services.audit_events import audit_event
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/security", tags=["security"])


# =============================================================================
# Request / Response Models — match AuditLogger.swift AuditEntry exactly
# =============================================================================


class DeviceInfo(BaseModel):
    model: str
    osVersion: str
    appVersion: str


class AuditEntryPayload(BaseModel):
    """One audit entry as serialized by iOS AuditLogger.swift."""
    id: str
    timestamp: float  # TimeInterval (seconds since epoch)
    event: str  # e.g. "auth.success", "biometric.prompt"
    details: Dict[str, str] = Field(default_factory=dict)
    deviceInfo: DeviceInfo
    synced: bool = False
    previousHash: str = ""
    hash: str = ""


class AuditLogRequest(BaseModel):
    """Batch payload sent by AuditLogger.syncToBackend()."""
    entries: List[AuditEntryPayload]


class AuditLogResponse(BaseModel):
    status: str = "ok"
    received: int
    persisted: int = 0
    chain_valid: Optional[bool] = None


# =============================================================================
# Valid event types from AuditLogger.swift EventType enum
# =============================================================================

VALID_EVENT_TYPES = {
    # Authentication
    "auth.attempt", "auth.success", "auth.failure",
    "auth.token_refresh", "auth.session_start", "auth.session_end", "auth.logout",
    # Biometric
    "biometric.prompt", "biometric.success", "biometric.failure",
    # Device Security
    "security.integrity_check", "security.device_compromised",
    "security.pin_failure", "security.pin_success", "security.violation",
    # Data Access
    "data.access", "data.document_view", "data.document_upload",
    "data.pii_viewed", "data.export",
    # Feature Access
    "feature.access", "feature.blocked",
    # CarPlay
    "carplay.connected", "carplay.disconnected", "carplay.call_initiated",
    # App Lifecycle
    "app.foreground", "app.background", "app.terminated",
}


# =============================================================================
# Hash Chain Verification
# =============================================================================


def _compute_entry_hash(entry: AuditEntryPayload) -> str:
    """Recompute SHA-256 hash matching AuditLogger.swift's entryDictForHashing.

    The dict includes: id, timestamp, event, details, deviceInfo, previousHash.
    Serialized with sorted keys — same as Swift's JSONSerialization .sortedKeys.
    """
    dict_for_hash = {
        "id": entry.id,
        "timestamp": entry.timestamp,
        "event": entry.event,
        "details": entry.details,
        "deviceInfo": {
            "model": entry.deviceInfo.model,
            "osVersion": entry.deviceInfo.osVersion,
            "appVersion": entry.deviceInfo.appVersion,
        },
        "previousHash": entry.previousHash,
    }
    serialized = json.dumps(dict_for_hash, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _verify_chain(entries: List[AuditEntryPayload]) -> bool:
    """Verify hash chain linkage within a batch.

    Each entry's previousHash must equal the preceding entry's hash.
    The first entry's previousHash is trusted (it may reference an
    entry outside this batch, or the genesis hash).

    Per-entry hash recomputation is advisory — cross-platform JSON
    serialization differences (e.g. float formatting) may cause benign
    mismatches, so only chain linkage failures mark the chain invalid.
    """
    if not entries:
        return True

    valid = True
    for i, entry in enumerate(entries):
        # Check chain linkage (skip first — its previousHash is external)
        if i > 0 and entry.previousHash != entries[i - 1].hash:
            logger.warning(
                "[SecurityAudit] Chain linkage broken at index %d: "
                "entry.previousHash=%s != prev.hash=%s",
                i,
                entry.previousHash[:16],
                entries[i - 1].hash[:16],
            )
            valid = False

        # Recompute hash for tamper detection (advisory only)
        recomputed = _compute_entry_hash(entry)
        if recomputed != entry.hash:
            logger.warning(
                "[SecurityAudit] Hash mismatch at index %d (id=%s, event=%s) "
                "— possible cross-platform serialization difference",
                i, entry.id, entry.event,
            )

    return valid


def _derive_outcome(ios_event: str) -> str:
    """Derive audit_event outcome from iOS event type string."""
    if "failure" in ios_event or "compromised" in ios_event or "violation" in ios_event:
        return "failure"
    if "blocked" in ios_event:
        return "denied"
    return "success"


# =============================================================================
# Route
# =============================================================================


@router.post("/audit-log", response_model=AuditLogResponse)
async def receive_audit_log(
    body: AuditLogRequest,
    request: Request,
    user=Depends(get_current_user_flexible),
    db: AsyncSession = Depends(get_async_db),
):
    """Receive batched security audit events from the iOS AuditLogger.

    Validates hash chain integrity, persists each event to the audit_events
    table via the audit_event() service, and returns acknowledgement so the
    iOS client can mark entries as synced.

    Auth is flexible (get_current_user_flexible) to handle partially-
    authenticated states — e.g. audit events logged during login flow.
    """
    entries = body.entries
    if not entries:
        return AuditLogResponse(status="ok", received=0, persisted=0, chain_valid=True)

    # Extract actor info from authenticated user (may be None)
    actor_id = getattr(user, "id", None) if user else None
    actor_email = getattr(user, "email", None) if user else None
    actor_role = getattr(user, "role", None) if user else None
    org_id = getattr(user, "organization_id", None) if user else None

    client_ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")

    # Verify hash chain integrity
    chain_valid = _verify_chain(entries)
    if not chain_valid:
        logger.warning(
            "[SecurityAudit] Received %d entries with BROKEN hash chain "
            "from user=%s org=%s",
            len(entries), actor_email or actor_id, org_id,
        )

    # Log high-severity events at warning level for observability
    for entry in entries:
        if entry.event not in VALID_EVENT_TYPES:
            logger.warning(
                "[SecurityAudit] Unknown event type '%s' from user=%s",
                entry.event, actor_email or actor_id,
            )
        if entry.event in (
            "security.device_compromised",
            "security.violation",
            "security.pin_failure",
            "auth.failure",
            "biometric.failure",
        ):
            logger.warning(
                "[SecurityAudit] SECURITY event=%s user=%s device=%s/%s details=%s",
                entry.event, actor_email or actor_id,
                entry.deviceInfo.model, entry.deviceInfo.osVersion,
                entry.details,
            )

    # Persist each entry via audit_event() service
    persisted = 0
    for entry in entries:
        # Convert iOS timestamp to datetime
        try:
            client_occurred_at = datetime.fromtimestamp(entry.timestamp, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            client_occurred_at = datetime.now(timezone.utc)

        # Build metadata with device info and hash chain fields
        meta = {
            "source": "ios_app",
            "ios_entry_id": entry.id,
            "device_model": entry.deviceInfo.model,
            "device_os": entry.deviceInfo.osVersion,
            "app_version": entry.deviceInfo.appVersion,
            "hash": entry.hash,
            "previous_hash": entry.previousHash,
            "chain_valid": chain_valid,
            "client_occurred_at": client_occurred_at.isoformat(),
        }
        if entry.details:
            meta["details"] = dict(entry.details)

        outcome = _derive_outcome(entry.event)

        # Map iOS event type to server event type (store original as-is;
        # the audit_events.event_type column is a free-form string)
        server_event_type = f"MOBILE_{entry.event.upper().replace('.', '_')}"

        try:
            audit_event(
                db,
                event_type=server_event_type,
                outcome=outcome,
                actor_id=actor_id,
                actor_email=actor_email,
                actor_role=actor_role,
                org_id=org_id,
                resource_type="mobile_device",
                resource_id=f"{entry.deviceInfo.model}/{entry.deviceInfo.osVersion}",
                ip=client_ip,
                user_agent=ua,
                metadata=meta,
            )
            persisted += 1
        except Exception as e:
            logger.exception(
                "[SecurityAudit] Failed to persist entry %s (event=%s): %s",
                entry.id, entry.event, e,
            )

    # Commit the batch
    try:
        await db.commit()
    except Exception as e:
        logger.exception("[SecurityAudit] Failed to commit audit batch: %s", e)
        try:
            await db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass
        return AuditLogResponse(
            status="ok", received=len(entries), persisted=0, chain_valid=chain_valid,
        )

    logger.info(
        "[SecurityAudit] Persisted %d/%d iOS audit entries for user=%s",
        persisted, len(entries), actor_email or actor_id or "anonymous",
    )

    return AuditLogResponse(
        status="ok",
        received=len(entries),
        persisted=persisted,
        chain_valid=chain_valid,
    )


# =============================================================================
# Registration helper
# =============================================================================


def register_security_audit_routes(app):
    """Mount the security audit router on the FastAPI app."""
    app.include_router(router)
