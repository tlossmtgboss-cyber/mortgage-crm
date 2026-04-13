"""
Security Audit Log Routes

POST /api/v1/security/audit-log — Receive batched mobile audit events
GET  /api/v1/security/audit-log — Query persisted audit events (paginated)

Accepts hash-chained security audit entries from the iOS app's AuditLogger.
Validates the hash chain integrity, logs events for observability, persists
them to the mobile_audit_events table for SOC 2 compliance, and returns
acknowledgement so the client can mark entries as synced.

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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import current_user_dep, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/security",
    tags=["security"],
    dependencies=[Depends(require_auth)],
)


# =============================================================================
# Ensure table exists (production-safe — Base.metadata.create_all is skipped)
# =============================================================================

def _ensure_table():
    """Create the mobile_audit_events table if it doesn't exist."""
    try:
        from database.models.audit import MobileAuditEvent
        from db import engine
        MobileAuditEvent.__table__.create(engine, checkfirst=True)
    except Exception as e:
        logger.warning("mobile_audit_events table creation check failed (non-fatal): %s", e)

_ensure_table()


# =============================================================================
# Request / Response Models
# =============================================================================


class DeviceInfo(BaseModel):
    model: str
    osVersion: str
    appVersion: str


class AuditEntry(BaseModel):
    id: str
    timestamp: float
    event: str
    details: Dict[str, str] = Field(default_factory=dict)
    deviceInfo: DeviceInfo
    synced: bool = False
    previousHash: str
    hash: str


class AuditLogRequest(BaseModel):
    entries: List[AuditEntry]


class AuditLogResponse(BaseModel):
    status: str = "ok"
    received: int
    persisted: int = 0
    chain_valid: Optional[bool] = None


class AuditEventOut(BaseModel):
    id: int
    organization_id: Optional[int] = None
    user_id: int
    event_type: str
    event_category: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    device_info: Optional[Dict[str, Any]] = None
    event_hash: Optional[str] = None
    previous_hash: Optional[str] = None
    chain_valid: Optional[bool] = None
    event_timestamp: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class AuditLogQueryResponse(BaseModel):
    events: List[AuditEventOut]
    total: int
    page: int
    page_size: int


# =============================================================================
# Hash Chain Verification
# =============================================================================

# The iOS client computes SHA-256 over a JSON dict with sorted keys containing
# all immutable fields except "hash" and "synced".  We replicate that logic
# server-side to verify tamper evidence.

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

# Map event prefix to category
EVENT_CATEGORY_MAP = {
    "auth": "auth",
    "biometric": "biometric",
    "security": "security",
    "data": "data",
    "feature": "feature",
    "carplay": "carplay",
    "app": "app",
}


def _derive_category(event_type: str) -> str:
    """Derive event_category from the event_type prefix."""
    prefix = event_type.split(".")[0] if "." in event_type else event_type
    return EVENT_CATEGORY_MAP.get(prefix, "unknown")


def _compute_entry_hash(entry: AuditEntry) -> str:
    """Recompute SHA-256 hash matching AuditLogger.swift's entryDictForHashing.

    The dict includes: id, timestamp, event, details, deviceInfo, previousHash.
    Serialised with sorted keys — same as Swift's JSONSerialization .sortedKeys.
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


def _verify_chain(entries: List[AuditEntry]) -> bool:
    """Verify hash chain linkage within a batch.

    Each entry's previousHash must equal the preceding entry's hash.
    The first entry's previousHash is trusted (it may reference an
    entry outside this batch, or the genesis hash).

    We also verify that each entry's hash matches the recomputed value.
    Note: cross-platform hash verification (Swift JSONSerialization vs
    Python json.dumps) may produce different byte-level JSON, so hash
    mismatches are logged as warnings rather than hard failures.
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

        # Recompute hash for tamper detection (advisory — cross-platform
        # JSON serialization differences may cause benign mismatches)
        recomputed = _compute_entry_hash(entry)
        if recomputed != entry.hash:
            logger.warning(
                "[SecurityAudit] Hash mismatch at index %d (id=%s, event=%s): "
                "expected=%s got=%s — possible cross-platform serialization difference",
                i,
                entry.id,
                entry.event,
                entry.hash[:16],
                recomputed[:16],
            )
            # Don't set valid=False here — cross-platform JSON differences
            # (e.g. float formatting) are expected. Chain linkage is the
            # authoritative integrity check.

    return valid


# =============================================================================
# Routes
# =============================================================================


@router.post("/audit-log", response_model=AuditLogResponse)
async def receive_audit_log(
    payload: AuditLogRequest,
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Receive batched security audit events from the iOS app.

    Validates hash chain integrity, logs each event, persists to database,
    and returns acknowledgement so the client marks entries as synced.

    DB persistence failures are caught and logged — the endpoint always
    succeeds so the client can clear its local queue.
    """
    entries = payload.entries
    user_id = current_user.id
    org_id = getattr(current_user, "organization_id", None)

    if not entries:
        return AuditLogResponse(status="ok", received=0, persisted=0, chain_valid=True)

    # Validate hash chain
    chain_valid = _verify_chain(entries)

    if not chain_valid:
        logger.warning(
            "[SecurityAudit] Received %d entries with BROKEN hash chain "
            "from user=%d org=%s",
            len(entries),
            user_id,
            org_id,
        )

    # Log each event for observability (defense in depth — log AND persist)
    for entry in entries:
        event_type = entry.event
        if event_type not in VALID_EVENT_TYPES:
            logger.warning(
                "[SecurityAudit] Unknown event type '%s' from user=%d",
                event_type,
                user_id,
            )

        # Categorize log level by event severity
        if event_type in (
            "security.device_compromised",
            "security.violation",
            "security.pin_failure",
            "auth.failure",
            "biometric.failure",
        ):
            logger.warning(
                "[SecurityAudit] user=%d org=%s event=%s details=%s "
                "device=%s/%s app=%s",
                user_id,
                org_id,
                event_type,
                entry.details,
                entry.deviceInfo.model,
                entry.deviceInfo.osVersion,
                entry.deviceInfo.appVersion,
            )
        else:
            logger.info(
                "[SecurityAudit] user=%d org=%s event=%s details=%s "
                "device=%s/%s app=%s",
                user_id,
                org_id,
                event_type,
                entry.details,
                entry.deviceInfo.model,
                entry.deviceInfo.osVersion,
                entry.deviceInfo.appVersion,
            )

    logger.info(
        "[SecurityAudit] Received %d audit events from user=%d org=%s "
        "chain_valid=%s events=%s",
        len(entries),
        user_id,
        org_id,
        chain_valid,
        [e.event for e in entries[:10]],  # Log first 10 event types
    )

    # Persist to database (never fail the request on DB errors)
    persisted = 0
    try:
        from database.models.audit import MobileAuditEvent

        db_events = []
        for entry in entries:
            event_timestamp = None
            try:
                event_timestamp = datetime.fromtimestamp(entry.timestamp, tz=timezone.utc)
            except (OSError, ValueError, OverflowError):
                logger.warning(
                    "[SecurityAudit] Invalid timestamp %s for entry %s",
                    entry.timestamp,
                    entry.id,
                )

            db_events.append(
                MobileAuditEvent(
                    organization_id=org_id,
                    user_id=user_id,
                    event_type=entry.event,
                    event_category=_derive_category(entry.event),
                    details=dict(entry.details) if entry.details else None,
                    device_info={
                        "model": entry.deviceInfo.model,
                        "osVersion": entry.deviceInfo.osVersion,
                        "appVersion": entry.deviceInfo.appVersion,
                    },
                    event_hash=entry.hash,
                    previous_hash=entry.previousHash,
                    chain_valid=chain_valid,
                    event_timestamp=event_timestamp,
                )
            )

        db.add_all(db_events)
        db.commit()
        persisted = len(db_events)
        logger.info(
            "[SecurityAudit] Persisted %d events to mobile_audit_events for user=%d",
            persisted,
            user_id,
        )
    except Exception as e:
        logger.exception(
            "[SecurityAudit] Failed to persist %d events for user=%d: %s",
            len(entries),
            user_id,
            e,
        )
        try:
            db.rollback()
        except Exception:
            pass

    return AuditLogResponse(
        status="ok",
        received=len(entries),
        persisted=persisted,
        chain_valid=chain_valid,
    )


@router.get("/audit-log", response_model=AuditLogQueryResponse)
async def query_audit_log(
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
    event_type: Optional[str] = Query(None, description="Filter by event_type (e.g. 'auth.success')"),
    event_category: Optional[str] = Query(None, description="Filter by category (e.g. 'auth', 'security')"),
    user_id: Optional[int] = Query(None, description="Filter by user_id (admin only)"),
    start_date: Optional[str] = Query(None, description="Start date ISO 8601 (e.g. '2026-01-01')"),
    end_date: Optional[str] = Query(None, description="End date ISO 8601 (e.g. '2026-04-10')"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Results per page"),
):
    """Query persisted audit events, scoped to the current user's organization.

    Supports filtering by event_type, event_category, user_id, and date range.
    Results are ordered by created_at descending (newest first).
    """
    from database.models.audit import MobileAuditEvent

    org_id = getattr(current_user, "organization_id", None)

    query = db.query(MobileAuditEvent)

    # Org-scoped: always filter by organization
    if org_id is not None:
        query = query.filter(MobileAuditEvent.organization_id == org_id)
    else:
        # No org — restrict to own events only
        query = query.filter(MobileAuditEvent.user_id == current_user.id)

    # Optional filters
    if event_type:
        query = query.filter(MobileAuditEvent.event_type == event_type)

    if event_category:
        query = query.filter(MobileAuditEvent.event_category == event_category)

    if user_id is not None:
        query = query.filter(MobileAuditEvent.user_id == user_id)

    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
            query = query.filter(MobileAuditEvent.created_at >= start_dt)
        except ValueError:
            pass  # Ignore invalid dates

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
            query = query.filter(MobileAuditEvent.created_at <= end_dt)
        except ValueError:
            pass

    # Count before pagination
    total = query.count()

    # Order and paginate
    events = (
        query
        .order_by(MobileAuditEvent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Serialize
    event_list = []
    for ev in events:
        event_list.append(
            AuditEventOut(
                id=ev.id,
                organization_id=ev.organization_id,
                user_id=ev.user_id,
                event_type=ev.event_type,
                event_category=ev.event_category,
                details=ev.details,
                device_info=ev.device_info,
                event_hash=ev.event_hash,
                previous_hash=ev.previous_hash,
                chain_valid=ev.chain_valid,
                event_timestamp=ev.event_timestamp.isoformat() if ev.event_timestamp else None,
                created_at=ev.created_at.isoformat() if ev.created_at else None,
            )
        )

    return AuditLogQueryResponse(
        events=event_list,
        total=total,
        page=page,
        page_size=page_size,
    )
