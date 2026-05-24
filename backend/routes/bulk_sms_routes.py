"""
Bulk SMS Campaign Routes — Campaign builder + rate-limited sender

Provides endpoints for creating, previewing, executing, listing, and cancelling
bulk SMS campaigns against lead segments built from smart filters.

Compliance:
- TCPA quiet hours (8 AM - 9 PM in recipient's local timezone)
- SMS opt-out / DNC check before every send
- Rate limited to 1 msg/sec for 10DLC throughput compliance
- Tenant isolation on all queries
"""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, time, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db, get_db_with_tenant
from routes.auth_deps import current_user_flexible_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sms", tags=["Bulk SMS"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TELNYX_FROM_NUMBER = os.getenv("TELNYX_FROM_NUMBER", "")
TELNYX_MESSAGING_PROFILE_ID = os.getenv(
    "TELNYX_MESSAGING_PROFILE_ID", ""
)
TELNYX_API_KEY = os.getenv("TELNYX_API_KEY", "")

QUIET_HOURS_START = time(21, 0)  # 9 PM local
QUIET_HOURS_END = time(8, 0)    # 8 AM local

# US state -> IANA timezone (primary timezone for each state)
STATE_TIMEZONE_MAP = {
    "AL": "America/Chicago", "AK": "America/Anchorage", "AZ": "America/Phoenix",
    "AR": "America/Chicago", "CA": "America/Los_Angeles", "CO": "America/Denver",
    "CT": "America/New_York", "DE": "America/New_York", "FL": "America/New_York",
    "GA": "America/New_York", "HI": "Pacific/Honolulu", "ID": "America/Boise",
    "IL": "America/Chicago", "IN": "America/Indiana/Indianapolis", "IA": "America/Chicago",
    "KS": "America/Chicago", "KY": "America/New_York", "LA": "America/Chicago",
    "ME": "America/New_York", "MD": "America/New_York", "MA": "America/New_York",
    "MI": "America/Detroit", "MN": "America/Chicago", "MS": "America/Chicago",
    "MO": "America/Chicago", "MT": "America/Denver", "NE": "America/Chicago",
    "NV": "America/Los_Angeles", "NH": "America/New_York", "NJ": "America/New_York",
    "NM": "America/Denver", "NY": "America/New_York", "NC": "America/New_York",
    "ND": "America/Chicago", "OH": "America/New_York", "OK": "America/Chicago",
    "OR": "America/Los_Angeles", "PA": "America/New_York", "RI": "America/New_York",
    "SC": "America/New_York", "SD": "America/Chicago", "TN": "America/Chicago",
    "TX": "America/Chicago", "UT": "America/Denver", "VT": "America/New_York",
    "VA": "America/New_York", "WA": "America/Los_Angeles", "WV": "America/New_York",
    "WI": "America/Chicago", "WY": "America/Denver", "DC": "America/New_York",
}

# In-memory campaign cancellation flags (campaign_id -> True means cancelled).
# Kept as a fast-path cache; the DB status column is the authoritative source
# so cancellation survives server restarts.
_cancelled_campaigns: Dict[str, bool] = {}

# How often (in messages) to check the DB for cancellation during execution.
# The in-memory dict is checked on every iteration; the DB is only hit every
# N messages to avoid excessive queries during large campaigns.
_CANCEL_CHECK_INTERVAL = 50

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CampaignFilters(BaseModel):
    stages: Optional[List[str]] = None
    source: Optional[str] = None
    loan_type: Optional[str] = None
    state: Optional[str] = None
    score_min: Optional[int] = None
    score_max: Optional[int] = None
    owner_id: Optional[int] = None
    created_after: Optional[str] = None   # ISO date string
    created_before: Optional[str] = None  # ISO date string


class CampaignCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    message_template: str = Field(..., min_length=1, max_length=1600)
    filters: CampaignFilters = Field(default_factory=CampaignFilters)
    scheduled_at: Optional[str] = None  # ISO datetime; None = send now

    @field_validator("message_template")
    @classmethod
    def validate_message_length(cls, v: str) -> str:
        if len(v) > 1600:
            raise ValueError(
                f"Message template is too long ({len(v)} chars). Max is 1600 chars."
            )
        return v


class CampaignPreviewRequest(BaseModel):
    message_template: str = Field(..., min_length=1, max_length=1600)
    filters: CampaignFilters = Field(default_factory=CampaignFilters)


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def render_template(template: str, lead: dict) -> str:
    """Replace {{field}} placeholders with lead data."""
    def _replace(match):
        key = match.group(1).strip()
        value = lead.get(key)
        return str(value) if value is not None else ""

    return re.sub(r"\{\{([^}]+)\}\}", _replace, template)


# ---------------------------------------------------------------------------
# Filter query builder
# ---------------------------------------------------------------------------

def _build_filter_query(
    filters: CampaignFilters,
    org_id: int,
    *,
    count_only: bool = False,
    preview_limit: int = 0,
) -> tuple:
    """Build a parameterized SQL query for leads matching the campaign filters.

    Returns (sql_string, params_dict).
    """
    conditions = [
        "l.organization_id = :org_id",
        "l.phone IS NOT NULL",
        "l.phone != ''",
    ]
    params: Dict = {"org_id": org_id}

    if filters.stages:
        # Build stage placeholders for IN clause (text() doesn't support tuple binding)
        stage_placeholders = ", ".join(f":stage_{i}" for i in range(len(filters.stages)))
        conditions.append(f"l.stage IN ({stage_placeholders})")
        for i, stage in enumerate(filters.stages):
            params[f"stage_{i}"] = stage
    if filters.source:
        conditions.append("l.source = :source")
        params["source"] = filters.source
    if filters.loan_type:
        conditions.append("l.loan_type = :loan_type")
        params["loan_type"] = filters.loan_type
    if filters.state:
        conditions.append("l.state = :state")
        params["state"] = filters.state
    if filters.score_min is not None:
        conditions.append("l.ai_score >= :score_min")
        params["score_min"] = filters.score_min
    if filters.score_max is not None:
        conditions.append("l.ai_score <= :score_max")
        params["score_max"] = filters.score_max
    if filters.owner_id is not None:
        conditions.append("l.owner_id = :owner_id")
        params["owner_id"] = filters.owner_id
    if filters.created_after:
        conditions.append("l.created_at >= :created_after")
        params["created_after"] = filters.created_after
    if filters.created_before:
        conditions.append("l.created_at <= :created_before")
        params["created_before"] = filters.created_before

    where_clause = " AND ".join(conditions)

    if count_only:
        sql = f"SELECT COUNT(*) as cnt FROM leads l WHERE {where_clause}"
    elif preview_limit > 0:
        sql = (
            f"SELECT l.id, l.first_name, l.last_name, l.phone, l.email, "
            f"l.stage, l.source, l.loan_type, l.state, l.ai_score "
            f"FROM leads l WHERE {where_clause} "
            f"ORDER BY l.ai_score DESC NULLS LAST, l.created_at DESC "
            f"LIMIT :preview_limit"
        )
        params["preview_limit"] = preview_limit
    else:
        sql = (
            f"SELECT l.id, l.first_name, l.last_name, l.phone, l.email, "
            f"l.stage, l.source, l.loan_type, l.state, l.ai_score "
            f"FROM leads l WHERE {where_clause} "
            f"ORDER BY l.id"
        )

    return sql, params


# ---------------------------------------------------------------------------
# Compliance helpers
# ---------------------------------------------------------------------------

def _is_opted_out(db: Session, phone: str, org_id: int) -> bool:
    """Check SMS opt-out status. Imports from the canonical compliance module."""
    try:
        from routes.sms_compliance_routes import is_opted_out
        return is_opted_out(db, phone, org_id)
    except ImportError:
        pass
    # Fallback: direct query against sms_consent table
    try:
        row = db.execute(
            text("SELECT opted_out FROM sms_consent WHERE phone = :phone AND organization_id = :org_id"),
            {"phone": phone, "org_id": org_id},
        ).fetchone()
        return bool(row and row.opted_out)
    except Exception as e:
        logger.error("Opt-out check failed (fail-closed): %s", e)
        return True  # Fail closed for TCPA safety


def _is_on_dnc(db: Session, phone: str, org_id: int) -> bool:
    """Check if phone is on the internal DNC list."""
    try:
        row = db.execute(
            text(
                "SELECT id FROM dnc_numbers "
                "WHERE phone_number = :phone AND organization_id = :org_id "
                "LIMIT 1"
            ),
            {"phone": phone, "org_id": org_id},
        ).fetchone()
        return row is not None
    except Exception as e:
        logger.error("DNC check failed (fail-closed): %s", e)
        return True  # Fail closed


def _is_quiet_hours(state: Optional[str]) -> bool:
    """Check if it is currently outside TCPA permissible hours in the lead's timezone."""
    tz_name = STATE_TIMEZONE_MAP.get((state or "").upper(), "America/New_York")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/New_York")
    now_local = datetime.now(tz).time()
    # Quiet if before 8 AM or at/after 9 PM
    return now_local < QUIET_HOURS_END or now_local >= QUIET_HOURS_START


def _normalize_phone(phone: str) -> Optional[str]:
    """Normalize to E.164 (+1XXXXXXXXXX)."""
    if not phone:
        return None
    digits = re.sub(r"[^\d]", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if phone.startswith("+") and len(digits) >= 10:
        return f"+{digits}"
    return None


# ---------------------------------------------------------------------------
# Campaign DB helpers
# ---------------------------------------------------------------------------

def _create_campaign_record(
    db: Session,
    name: str,
    message_template: str,
    filters: dict,
    user_id: int,
    org_id: int,
    estimated_recipients: int,
    scheduled_at: Optional[str],
) -> str:
    """Insert a campaign record and return its ID."""
    campaign_id = str(uuid.uuid4())
    status = "scheduled" if scheduled_at else "pending"
    try:
        db.execute(
            text("""
                INSERT INTO bulk_sms_campaigns
                  (id, name, message_template, filter_criteria, status,
                   estimated_recipients, user_id, organization_id,
                   scheduled_at, created_at, updated_at)
                VALUES
                  (:id, :name, :template, :filters, :status,
                   :est, :user_id, :org_id,
                   :scheduled_at, NOW(), NOW())
            """),
            {
                "id": campaign_id,
                "name": name,
                "template": message_template,
                "filters": json.dumps(filters),
                "status": status,
                "est": estimated_recipients,
                "user_id": user_id,
                "org_id": org_id,
                "scheduled_at": scheduled_at,
            },
        )
        db.commit()
        return campaign_id
    except Exception as e:
        db.rollback()
        logger.exception("Failed to create campaign record: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create campaign")


def _update_campaign_status(db: Session, campaign_id: str, status: str, **extra_fields):
    """Update campaign status and optional extra columns."""
    sets = ["status = :status", "updated_at = NOW()"]
    params: Dict = {"id": campaign_id, "status": status}
    for col, val in extra_fields.items():
        sets.append(f"{col} = :{col}")
        params[col] = val
    try:
        query = "UPDATE bulk_sms_campaigns SET " + ", ".join(sets) + " WHERE id = :id"
        db.execute(
            text(query),
            params,
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to update campaign %s: %s", campaign_id, e)


def _increment_campaign_counter(db: Session, campaign_id: str, column: str):
    """Atomically increment a counter column on the campaign."""
    ALLOWED_COLUMNS = {"sent_count", "delivered_count", "failed_count", "opted_out_count", "reply_count"}
    if column not in ALLOWED_COLUMNS:
        raise ValueError(f"Invalid counter column: {column}")
    try:
        query = "UPDATE bulk_sms_campaigns SET " + column + " = COALESCE(" + column + ", 0) + 1, updated_at = NOW() WHERE id = :id"
        db.execute(
            text(query),
            {"id": campaign_id},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to increment %s for campaign %s: %s", column, campaign_id, e)


# ---------------------------------------------------------------------------
# Telnyx SMS sender
# ---------------------------------------------------------------------------

async def _send_sms_telnyx(to: str, body: str) -> Optional[str]:
    """Send a single SMS via the centralized Telnyx chokepoint.

    Returns the Telnyx message_id on success, None on failure/block.
    Note: bulk campaign sends already run compliance in the caller loop,
    but the chokepoint provides defense-in-depth.
    """
    try:
        from telephony.sms import send_sms_verified_async

        result = await send_sms_verified_async(
            to=to,
            from_=TELNYX_FROM_NUMBER,
            text=body,
            messaging_profile_id=TELNYX_MESSAGING_PROFILE_ID,
        )
        if result.get("status") == "sent":
            return result.get("id")
        logger.warning("Bulk SMS to ...%s blocked/failed: %s", to[-4:] if to else "?", result.get("reason", ""))
        return None
    except Exception as e:
        logger.exception("Telnyx SMS send error: %s", e)
        return None


# ---------------------------------------------------------------------------
# Campaign execution (background task)
# ---------------------------------------------------------------------------

async def _execute_campaign(campaign_id: str, org_id: int, user_id: int):
    """Run the campaign send loop in the background.

    Uses get_db_with_tenant for RLS-scoped DB sessions since this runs
    outside the FastAPI request lifecycle.
    """
    logger.info("Starting campaign execution: %s", campaign_id)

    # Load campaign details and sender name for panel messages
    sender_name = "Campaign"
    with get_db_with_tenant(org_id) as db:
        campaign = db.execute(
            text("SELECT message_template, filter_criteria FROM bulk_sms_campaigns WHERE id = :id"),
            {"id": campaign_id},
        ).fetchone()
        if not campaign:
            logger.error("Campaign %s not found", campaign_id)
            return

        message_template = campaign.message_template
        filter_criteria = campaign.filter_criteria
        if isinstance(filter_criteria, str):
            filter_criteria = json.loads(filter_criteria)

        # Resolve sender display name for SMS Archive panel
        try:
            user_row = db.execute(
                text("SELECT first_name, last_name FROM users WHERE id = :uid"),
                {"uid": user_id},
            ).fetchone()
            if user_row:
                sender_name = f"{user_row.first_name or ''} {user_row.last_name or ''}".strip() or "Campaign"
        except Exception:
            pass  # keep default "Campaign"

        # Mark as sending
        _update_campaign_status(db, campaign_id, "sending")

        # Query all matching leads
        filters = CampaignFilters(**filter_criteria)
        sql, params = _build_filter_query(filters, org_id)
        leads = db.execute(text(sql), params).fetchall()
        columns = ["id", "first_name", "last_name", "phone", "email",
                    "stage", "source", "loan_type", "state", "ai_score"]

    total = len(leads)
    sent_count = 0
    failed_count = 0
    opted_out_count = 0
    dnc_skipped_count = 0
    quiet_hours_skipped = 0

    messages_processed = 0
    for row in leads:
        # Check cancellation — fast path via in-memory cache
        if _cancelled_campaigns.get(campaign_id):
            logger.info("Campaign %s cancelled (in-memory), stopping after %d/%d", campaign_id, sent_count, total)
            break

        # Check cancellation — persistent DB check every N messages
        # so cancellation survives server restarts / deploys
        if messages_processed > 0 and messages_processed % _CANCEL_CHECK_INTERVAL == 0:
            with get_db_with_tenant(org_id) as db:
                cancel_row = db.execute(
                    text("SELECT status FROM bulk_sms_campaigns WHERE id = :cid"),
                    {"cid": campaign_id},
                ).fetchone()
                if cancel_row and cancel_row.status == "cancelled":
                    _cancelled_campaigns[campaign_id] = True  # update cache
                    logger.info("Campaign %s cancelled (DB), stopping after %d/%d", campaign_id, sent_count, total)
                    break
        messages_processed += 1

        lead = dict(zip(columns, row))
        phone_raw = lead.get("phone", "")
        phone = _normalize_phone(phone_raw)

        if not phone:
            failed_count += 1
            with get_db_with_tenant(org_id) as db:
                _increment_campaign_counter(db, campaign_id, "failed_count")
            continue

        # Compliance checks with a fresh DB session
        with get_db_with_tenant(org_id) as db:
            # 1. Opt-out check
            if _is_opted_out(db, phone, org_id):
                opted_out_count += 1
                _increment_campaign_counter(db, campaign_id, "opted_out_count")
                continue

            # 2. DNC check
            if _is_on_dnc(db, phone, org_id):
                dnc_skipped_count += 1
                _increment_campaign_counter(db, campaign_id, "dnc_skipped_count")
                continue

        # 3. TCPA quiet hours check (no DB needed)
        if _is_quiet_hours(lead.get("state")):
            quiet_hours_skipped += 1
            with get_db_with_tenant(org_id) as db:
                _increment_campaign_counter(db, campaign_id, "quiet_hours_skipped")
            continue

        # 4. Render message
        rendered = render_template(message_template, lead)

        # 5. Send via Telnyx
        message_id = await _send_sms_telnyx(phone, rendered)

        with get_db_with_tenant(org_id) as db:
            if message_id:
                sent_count += 1
                _increment_campaign_counter(db, campaign_id, "sent_count")
                # Log the individual send
                try:
                    db.execute(
                        text("""
                            INSERT INTO bulk_sms_sends
                              (campaign_id, lead_id, phone, telnyx_message_id,
                               status, sent_at)
                            VALUES
                              (:cid, :lid, :phone, :mid, 'sent', NOW())
                        """),
                        {
                            "cid": campaign_id,
                            "lid": lead["id"],
                            "phone": phone,
                            "mid": message_id,
                        },
                    )
                    db.commit()
                except Exception as e:
                    db.rollback()
                    logger.warning("Failed to log send for campaign %s: %s", campaign_id, e)

                # Also write to sms_panel_messages so the SMS Archive tab can see it
                try:
                    import uuid as _uuid
                    db.execute(text("""
                        INSERT INTO sms_panel_messages
                            (id, phone, organization_id, direction, body,
                             sender_name, sender_user_id, status,
                             media_urls, telnyx_message_id, created_at)
                        VALUES
                            (:id, :phone, :org_id, 'outbound', :body,
                             :sender_name, :sender_user_id, 'sent',
                             '[]'::jsonb, :telnyx_id, NOW())
                        ON CONFLICT (id) DO NOTHING
                    """), {
                        "id": str(_uuid.uuid4()),
                        "phone": phone,
                        "org_id": org_id,
                        "body": rendered[:2000],
                        "sender_name": sender_name,
                        "sender_user_id": user_id,
                        "telnyx_id": message_id or "",
                    })
                    db.commit()
                except Exception as panel_err:
                    logger.warning("Failed to write campaign SMS to panel_messages: %s", panel_err)
                    db.rollback()
            else:
                failed_count += 1
                _increment_campaign_counter(db, campaign_id, "failed_count")

        # 6. Rate limit: 1 msg/sec for 10DLC compliance
        await asyncio.sleep(1.0)

    # Finalize campaign — check both in-memory flag and DB for cancellation
    was_cancelled = _cancelled_campaigns.get(campaign_id)
    if not was_cancelled:
        with get_db_with_tenant(org_id) as db:
            status_row = db.execute(
                text("SELECT status FROM bulk_sms_campaigns WHERE id = :cid"),
                {"cid": campaign_id},
            ).fetchone()
            if status_row and status_row.status == "cancelled":
                was_cancelled = True
    final_status = "cancelled" if was_cancelled else "completed"
    with get_db_with_tenant(org_id) as db:
        # Write final stats definitively (incremental counters may have raced)
        try:
            db.execute(
                text("""
                    UPDATE bulk_sms_campaigns SET
                        status = :status,
                        total_recipients = :total,
                        sent_count = :sent,
                        failed_count = :failed,
                        opted_out_count = :opted_out,
                        dnc_skipped_count = :dnc,
                        quiet_hours_skipped = :quiet,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": campaign_id,
                    "status": final_status,
                    "total": total,
                    "sent": sent_count,
                    "failed": failed_count,
                    "opted_out": opted_out_count,
                    "dnc": dnc_skipped_count,
                    "quiet": quiet_hours_skipped,
                },
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to finalize campaign %s: %s", campaign_id, e)

    # Clean up cancellation flag
    _cancelled_campaigns.pop(campaign_id, None)

    logger.info(
        "Campaign %s %s: %d sent, %d failed, %d opted-out, %d DNC, %d quiet-hours of %d total",
        campaign_id, final_status, sent_count, failed_count,
        opted_out_count, dnc_skipped_count, quiet_hours_skipped, total,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/campaigns/preview")
async def preview_campaign(
    body: CampaignPreviewRequest,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Preview a campaign: returns recipient count and sample leads with rendered messages."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")

    # Get count
    count_sql, count_params = _build_filter_query(body.filters, org_id, count_only=True)
    row = db.execute(text(count_sql), count_params).fetchone()
    total_count = row.cnt if row else 0

    # Get sample recipients (first 10)
    sample_sql, sample_params = _build_filter_query(
        body.filters, org_id, preview_limit=10
    )
    sample_rows = db.execute(text(sample_sql), sample_params).fetchall()

    columns = ["id", "first_name", "last_name", "phone", "email",
                "stage", "source", "loan_type", "state", "ai_score"]
    sample_leads = []
    for r in sample_rows:
        lead = dict(zip(columns, r))
        rendered = render_template(body.message_template, lead)
        sample_leads.append({
            "id": lead["id"],
            "name": f"{lead.get('first_name') or ''} {lead.get('last_name') or ''}".strip(),
            "phone": lead["phone"],
            "stage": lead["stage"],
            "ai_score": lead["ai_score"],
            "rendered_message": rendered,
        })

    return {
        "total_recipients": total_count,
        "sample_recipients": sample_leads,
        "message_length": len(render_template(body.message_template, {"first_name": "Jane"})),
        "filters_applied": body.filters.model_dump(exclude_none=True),
    }


@router.post("/campaigns")
async def create_campaign(
    body: CampaignCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Create a bulk SMS campaign.

    If scheduled_at is null, the campaign starts executing immediately as a
    background task. Otherwise it is recorded with status 'scheduled' for
    a future scheduler to pick up.
    """
    org_id = getattr(current_user, "organization_id", None)
    user_id = getattr(current_user, "id", None)
    if not org_id or not user_id:
        raise HTTPException(status_code=403, detail="Organization context required")

    # Get estimated recipient count
    count_sql, count_params = _build_filter_query(body.filters, org_id, count_only=True)
    row = db.execute(text(count_sql), count_params).fetchone()
    estimated = row.cnt if row else 0

    if estimated == 0:
        raise HTTPException(
            status_code=400,
            detail="No leads match the filter criteria. Adjust your filters and try again.",
        )

    # Create the campaign record
    campaign_id = _create_campaign_record(
        db=db,
        name=body.name,
        message_template=body.message_template,
        filters=body.filters.model_dump(exclude_none=True),
        user_id=user_id,
        org_id=org_id,
        estimated_recipients=estimated,
        scheduled_at=body.scheduled_at,
    )

    # If send_now (no schedule), kick off background execution
    if not body.scheduled_at:
        background_tasks.add_task(_execute_campaign, campaign_id, org_id, user_id)

    return {
        "campaign_id": campaign_id,
        "name": body.name,
        "status": "scheduled" if body.scheduled_at else "pending",
        "estimated_recipients": estimated,
        "scheduled_at": body.scheduled_at,
        "message": (
            f"Campaign created with {estimated} estimated recipients. "
            + ("Sending now." if not body.scheduled_at else f"Scheduled for {body.scheduled_at}.")
        ),
    }


@router.get("/campaigns/{campaign_id}")
async def get_campaign_status(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Get the current status and stats of a campaign."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")

    row = db.execute(
        text("""
            SELECT
                id, name, status, message_template,
                estimated_recipients, total_recipients,
                sent_count, delivered_count, failed_count, opted_out_count,
                dnc_skipped_count, quiet_hours_skipped,
                scheduled_at, created_at, completed_at,
                user_id
            FROM bulk_sms_campaigns
            WHERE id = :id AND organization_id = :org_id
        """),
        {"id": campaign_id, "org_id": org_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "campaign_id": row.id,
        "name": row.name,
        "status": row.status,
        "message_template": row.message_template,
        "estimated_recipients": row.estimated_recipients,
        "total_recipients": row.total_recipients or 0,
        "sent": row.sent_count or 0,
        "delivered": row.delivered_count or 0,
        "failed": row.failed_count or 0,
        "opted_out_skipped": row.opted_out_count or 0,
        "dnc_skipped": row.dnc_skipped_count or 0,
        "quiet_hours_skipped": row.quiet_hours_skipped or 0,
        "scheduled_at": str(row.scheduled_at) if row.scheduled_at else None,
        "created_at": str(row.created_at) if row.created_at else None,
        "completed_at": str(row.completed_at) if row.completed_at else None,
    }


@router.get("/campaigns")
async def list_campaigns(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """List campaigns for the current organization with summary stats."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")

    rows = db.execute(
        text("""
            SELECT
                id, name, status,
                estimated_recipients, sent_count, delivered_count, failed_count,
                opted_out_count, dnc_skipped_count,
                scheduled_at, created_at, completed_at
            FROM bulk_sms_campaigns
            WHERE organization_id = :org_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"org_id": org_id, "limit": limit, "offset": offset},
    ).fetchall()

    total_row = db.execute(
        text("SELECT COUNT(*) as cnt FROM bulk_sms_campaigns WHERE organization_id = :org_id"),
        {"org_id": org_id},
    ).fetchone()

    campaigns = []
    for r in rows:
        campaigns.append({
            "campaign_id": r.id,
            "name": r.name,
            "status": r.status,
            "estimated_recipients": r.estimated_recipients,
            "sent": r.sent_count or 0,
            "delivered": r.delivered_count or 0,
            "failed": r.failed_count or 0,
            "opted_out_skipped": r.opted_out_count or 0,
            "dnc_skipped": r.dnc_skipped_count or 0,
            "scheduled_at": str(r.scheduled_at) if r.scheduled_at else None,
            "created_at": str(r.created_at) if r.created_at else None,
            "completed_at": str(r.completed_at) if r.completed_at else None,
        })

    return {
        "campaigns": campaigns,
        "total": total_row.cnt if total_row else 0,
        "limit": limit,
        "offset": offset,
    }


@router.post("/campaigns/{campaign_id}/cancel")
async def cancel_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Cancel a running or scheduled campaign."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")

    row = db.execute(
        text("SELECT status FROM bulk_sms_campaigns WHERE id = :id AND organization_id = :org_id"),
        {"id": campaign_id, "org_id": org_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if row.status in ("completed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is already {row.status} and cannot be cancelled",
        )

    # Set the cancellation flag so the background loop stops (fast path)
    _cancelled_campaigns[campaign_id] = True

    # Always persist cancellation to the DB so it survives server restarts.
    # For "sending" campaigns, the execution loop will detect this on its
    # next DB check interval and stop gracefully.
    _update_campaign_status(db, campaign_id, "cancelled")

    return {
        "campaign_id": campaign_id,
        "status": "cancelling" if row.status == "sending" else "cancelled",
        "message": (
            "Campaign cancellation requested. In-flight messages may still be delivered."
            if row.status == "sending"
            else "Campaign cancelled."
        ),
    }


# ---------------------------------------------------------------------------
# Table creation (self-healing for first deploy)
# ---------------------------------------------------------------------------

def _ensure_tables(db: Session):
    """Create the bulk_sms_campaigns and bulk_sms_sends tables if they don't exist.

    Uses CREATE TABLE IF NOT EXISTS for idempotency.
    """
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS bulk_sms_campaigns (
                id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                message_template TEXT NOT NULL,
                filter_criteria TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                estimated_recipients INTEGER DEFAULT 0,
                total_recipients INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                delivered_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                opted_out_count INTEGER DEFAULT 0,
                dnc_skipped_count INTEGER DEFAULT 0,
                quiet_hours_skipped INTEGER DEFAULT 0,
                user_id INTEGER,
                organization_id INTEGER NOT NULL,
                scheduled_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bulk_sms_campaigns_org
            ON bulk_sms_campaigns (organization_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bulk_sms_campaigns_status
            ON bulk_sms_campaigns (status)
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS bulk_sms_sends (
                id SERIAL PRIMARY KEY,
                campaign_id VARCHAR(36) NOT NULL REFERENCES bulk_sms_campaigns(id),
                lead_id INTEGER,
                phone VARCHAR(20) NOT NULL,
                telnyx_message_id VARCHAR(100),
                status VARCHAR(20) DEFAULT 'sent',
                sent_at TIMESTAMP DEFAULT NOW(),
                delivered_at TIMESTAMP,
                error_message TEXT
            )
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bulk_sms_sends_campaign
            ON bulk_sms_sends (campaign_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bulk_sms_sends_telnyx_msg
            ON bulk_sms_sends (telnyx_message_id)
        """))
        db.commit()
        logger.info("Bulk SMS campaign tables verified")
    except Exception as e:
        db.rollback()
        logger.warning("Bulk SMS table creation skipped: %s", e)


# Run table creation on module load (idempotent)
try:
    from db import SessionLocal
    _init_db = SessionLocal()
    try:
        _ensure_tables(_init_db)
    finally:
        _init_db.close()
except Exception as e:
    logger.warning("Deferred bulk SMS table creation: %s", e)
