"""
Speed-to-Lead Routes — 60-second auto-response trigger on new lead creation

When a new lead is created (via API, webhook, or Salesforce sync), this module:
  1. Routes the lead to the best available LO (via lead_routing_routes)
  2. Initiates an auto-call to the lead within 60 seconds (via Telnyx/Vapi)
  3. Sends an instant SMS acknowledgment
  4. Logs all speed-to-lead events for metrics

Trigger mechanisms:
  - POST /api/v1/speed-to-lead/trigger (called internally after lead creation)
  - Webhook: POST /api/v1/speed-to-lead/webhook (for external lead sources)
"""

import os
import asyncio
import logging
from datetime import datetime, time as dt_time, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
import httpx

from db import get_db
from routes.auth_deps import current_user_flexible_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/speed-to-lead", tags=["Speed to Lead"])

# TCPA quiet hours: no calls/SMS before 8am or after 9pm borrower local time
TCPA_START = dt_time(8, 0)
TCPA_END = dt_time(21, 0)

# State → timezone mapping (subset covering all US states)
STATE_TIMEZONES = {
    "HI": "Pacific/Honolulu", "AK": "America/Anchorage",
    "WA": "America/Los_Angeles", "OR": "America/Los_Angeles", "CA": "America/Los_Angeles",
    "NV": "America/Los_Angeles", "ID": "America/Boise", "MT": "America/Denver",
    "WY": "America/Denver", "UT": "America/Denver", "CO": "America/Denver",
    "AZ": "America/Phoenix", "NM": "America/Denver",
    "ND": "America/Chicago", "SD": "America/Chicago", "NE": "America/Chicago",
    "KS": "America/Chicago", "OK": "America/Chicago", "TX": "America/Chicago",
    "MN": "America/Chicago", "IA": "America/Chicago", "MO": "America/Chicago",
    "AR": "America/Chicago", "LA": "America/Chicago", "WI": "America/Chicago",
    "IL": "America/Chicago", "MS": "America/Chicago", "AL": "America/Chicago",
    "TN": "America/Chicago",
    "MI": "America/New_York", "IN": "America/Indiana/Indianapolis",
    "OH": "America/New_York", "KY": "America/New_York", "WV": "America/New_York",
    "VA": "America/New_York", "NC": "America/New_York", "SC": "America/New_York",
    "GA": "America/New_York", "FL": "America/New_York",
    "PA": "America/New_York", "NY": "America/New_York", "NJ": "America/New_York",
    "CT": "America/New_York", "RI": "America/New_York", "MA": "America/New_York",
    "VT": "America/New_York", "NH": "America/New_York", "ME": "America/New_York",
    "DE": "America/New_York", "MD": "America/New_York", "DC": "America/New_York",
}


def _is_tcpa_quiet_hours(state: Optional[str] = None) -> bool:
    """Check if it's currently outside TCPA permissible hours in the borrower's timezone."""
    try:
        import pytz
        tz_name = STATE_TIMEZONES.get((state or "").upper(), "America/New_York")
        tz = pytz.timezone(tz_name)
        local_now = datetime.now(tz).time()
        return local_now < TCPA_START or local_now >= TCPA_END
    except Exception:
        # If timezone check fails, default to conservative (allow)
        return False


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TriggerRequest(BaseModel):
    lead_id: int
    skip_call: bool = False
    skip_sms: bool = False


class WebhookLeadPayload(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    loan_type: Optional[str] = None
    loan_amount: Optional[float] = None
    state: Optional[str] = None
    organization_id: Optional[int] = None


# ---------------------------------------------------------------------------
# SMS helper
# ---------------------------------------------------------------------------

async def _send_sms(to: str, from_: str, body: str):
    """Send SMS via the centralized Telnyx chokepoint (with compliance)."""
    try:
        from telephony.sms import send_sms_verified_async

        result = await send_sms_verified_async(
            to=to,
            from_=from_,
            text=body,
        )
        if result.get("status") not in ("sent",):
            logger.error("SMS send blocked/failed for ...%s: %s", to[-4:] if to else "?", result.get("reason", ""))
    except Exception as e:
        logger.exception("SMS send error: %s", e)


# ---------------------------------------------------------------------------
# Call helper (Telnyx outbound)
# ---------------------------------------------------------------------------

async def _initiate_call(to: str, from_: str, connection_id: str, webhook_url: str) -> Optional[str]:
    """Start an outbound Telnyx call. Returns call_control_id or None."""
    telnyx_key = os.getenv("TELNYX_API_KEY", "")

    payload = {
        "to": to,
        "from": from_,
        "connection_id": connection_id,
        "answering_machine_detection": "detect",
        "webhook_url": webhook_url,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.telnyx.com/v2/calls",
                json=payload,
                headers={"Authorization": f"Bearer {telnyx_key}", "Content-Type": "application/json"},
            )
        if resp.status_code < 400:
            data = resp.json().get("data", {})
            return data.get("call_control_id")
        else:
            logger.error("Outbound call failed %s: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.exception("Outbound call error: %s", e)

    return None


# ---------------------------------------------------------------------------
# Core speed-to-lead flow (runs as background task)
# ---------------------------------------------------------------------------

async def _execute_speed_to_lead(
    db_url: str,
    lead_id: int,
    skip_call: bool = False,
    skip_sms: bool = False,
):
    """
    Background task: route lead → SMS → call within 60 seconds.
    Uses its own DB session since it runs outside the request lifecycle.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Fetch lead
        lead = db.execute(text("""
            SELECT id, first_name, last_name, phone, email, organization_id,
                   loan_type, state, source, owner_id
            FROM leads WHERE id = :lid
        """), {"lid": lead_id}).fetchone()

        if not lead:
            logger.warning("Speed-to-lead: lead %s not found", lead_id)
            return

        org_id = lead.organization_id
        now = datetime.now(timezone.utc)

        # Log event start
        _log_stl_event(db, lead_id, org_id, "started", None)

        # Step 1: Route lead if not already assigned
        assigned_lo_id = lead.owner_id
        if not assigned_lo_id:
            try:
                from routes.lead_routing_routes import route_lead
                result = route_lead(
                    db, org_id,
                    loan_type=lead.loan_type,
                    state=lead.state,
                    source=lead.source,
                )
                if result:
                    assigned_lo_id = result["lo_id"]
                    db.execute(text("""
                        UPDATE leads SET owner_id = :lo_id, updated_at = :now
                        WHERE id = :lid
                    """), {"lo_id": assigned_lo_id, "now": now, "lid": lead_id})
                    db.commit()
                    _log_stl_event(db, lead_id, org_id, "routed", {"lo_id": assigned_lo_id, "reason": result["reason"]})
            except Exception as e:
                logger.exception("Lead routing failed for lead %s: %s", lead_id, e)
                db.rollback()

        # TCPA quiet hours check — block calls/SMS outside 8am-9pm borrower local time
        borrower_state = getattr(lead, "state", None)
        if _is_tcpa_quiet_hours(borrower_state):
            _log_stl_event(db, lead_id, org_id, "tcpa_blocked", {"state": borrower_state})
            logger.info("Speed-to-lead blocked by TCPA quiet hours for lead %s (state=%s)", lead_id, borrower_state)
            return

        # Step 2: Send immediate SMS acknowledgment
        if not skip_sms and lead.phone:
            # Check opt-out
            opted_out = False
            try:
                from routes.sms_compliance_routes import is_opted_out
                opted_out = is_opted_out(db, lead.phone, org_id)
            except Exception:
                pass

            if not opted_out:
                from_number = os.getenv("TELNYX_FROM_NUMBER", "")
                sms_body = (
                    f"Hi {lead.first_name or 'there'}! Thanks for your interest in mortgage options. "
                    f"A loan officer will be reaching out shortly. "
                    f"Reply STOP to opt out."
                )
                await _send_sms(to=lead.phone, from_=from_number, body=sms_body)
                _log_stl_event(db, lead_id, org_id, "sms_sent", {"phone": lead.phone[-4:]})

        # Step 3: Initiate outbound call
        if not skip_call and lead.phone:
            from_number = os.getenv("TELNYX_FROM_NUMBER", "")
            connection_id = os.getenv("TELNYX_CONNECTION_ID", "")
            base_url = os.getenv("API_BASE_URL", "")
            if base_url and not base_url.startswith("http"):
                base_url = f"https://{base_url}"
            webhook_url = f"{base_url}/api/v1/telephony/amd-callback" if base_url else ""

            call_id = await _initiate_call(
                to=lead.phone,
                from_=from_number,
                connection_id=connection_id,
                webhook_url=webhook_url,
            )

            if call_id:
                _log_stl_event(db, lead_id, org_id, "call_initiated", {"call_control_id": call_id})
                # Log call in call_logs
                try:
                    db.execute(text("""
                        INSERT INTO call_logs (call_sid, phone_number, direction, status,
                            organization_id, agent_id, created_at)
                        VALUES (:sid, :phone, 'outbound', 'initiated', :org_id, :lo_id, :now)
                    """), {
                        "sid": call_id, "phone": lead.phone,
                        "org_id": org_id, "lo_id": assigned_lo_id, "now": now,
                    })
                    db.commit()
                except Exception:
                    db.rollback()
            else:
                _log_stl_event(db, lead_id, org_id, "call_failed", {})

        _log_stl_event(db, lead_id, org_id, "completed", {
            "elapsed_ms": int((datetime.now(timezone.utc) - now).total_seconds() * 1000)
        })

    except Exception as e:
        logger.exception("Speed-to-lead failed for lead %s: %s", lead_id, e)
    finally:
        db.close()
        engine.dispose()


def _log_stl_event(db: Session, lead_id: int, org_id: Optional[int], event: str, meta: Optional[dict]):
    """Log a speed-to-lead event (best-effort)."""
    try:
        db.execute(text("""
            INSERT INTO speed_to_lead_events (lead_id, organization_id, event, meta, created_at)
            VALUES (:lid, :org_id, :event, :meta, :now)
        """), {
            "lid": lead_id, "org_id": org_id, "event": event,
            "meta": str(meta)[:2000] if meta else None,
            "now": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception:
        db.rollback()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/trigger")
async def trigger_speed_to_lead(
    body: TriggerRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """
    Trigger speed-to-lead flow for a newly created lead.
    Call this from lead creation endpoints.
    """
    org_id = getattr(current_user, "organization_id", None)

    # Verify lead exists and belongs to org
    lead = db.execute(text("""
        SELECT id, phone FROM leads WHERE id = :lid AND organization_id = :org_id
    """), {"lid": body.lead_id, "org_id": org_id}).fetchone()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.phone:
        return {"status": "skipped", "reason": "Lead has no phone number"}

    # Get DATABASE_URL for background task
    db_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")

    background_tasks.add_task(
        _execute_speed_to_lead,
        db_url=db_url,
        lead_id=body.lead_id,
        skip_call=body.skip_call,
        skip_sms=body.skip_sms,
    )

    return {"status": "triggered", "lead_id": body.lead_id}


@router.post("/webhook")
async def speed_to_lead_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    External webhook for new leads from third-party sources.
    Creates the lead and triggers the speed-to-lead flow.
    """
    # Validate API key
    api_key = request.headers.get("X-API-Key", "")
    expected_key = os.getenv("SPEED_TO_LEAD_WEBHOOK_KEY", "")
    if not expected_key or api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    payload = await request.json()
    body = WebhookLeadPayload(**payload)

    if not body.phone and not body.email:
        raise HTTPException(status_code=400, detail="Phone or email required")

    org_id = body.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="organization_id required")

    now = datetime.now(timezone.utc)

    # Check for duplicate (same phone + org in last 24 hours)
    if body.phone:
        dup = db.execute(text("""
            SELECT id FROM leads
            WHERE phone = :phone AND organization_id = :org_id
                AND created_at >= :cutoff
            LIMIT 1
        """), {"phone": body.phone, "org_id": org_id, "cutoff": now}).fetchone()

        if dup:
            return {"status": "duplicate", "lead_id": dup.id}

    # Create lead
    result = db.execute(text("""
        INSERT INTO leads (first_name, last_name, email, phone, source,
            loan_type, loan_amount, state, organization_id, stage, created_at, updated_at)
        VALUES (:fn, :ln, :email, :phone, :source, :lt, :la, :state, :org_id, 'New', :now, :now)
        RETURNING id
    """), {
        "fn": body.first_name, "ln": body.last_name, "email": body.email,
        "phone": body.phone, "source": body.source or "webhook",
        "lt": body.loan_type, "la": body.loan_amount, "state": body.state,
        "org_id": org_id, "now": now,
    })
    lead_id = result.fetchone().id
    db.commit()

    # Trigger speed-to-lead flow
    db_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
    background_tasks.add_task(
        _execute_speed_to_lead,
        db_url=db_url,
        lead_id=lead_id,
    )

    return {"status": "created", "lead_id": lead_id}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@router.get("/metrics")
async def speed_to_lead_metrics(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Get speed-to-lead performance metrics."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    try:
        stats = db.execute(text("""
            SELECT
                COUNT(DISTINCT lead_id) as total_leads,
                COUNT(CASE WHEN event = 'sms_sent' THEN 1 END) as sms_sent,
                COUNT(CASE WHEN event = 'call_initiated' THEN 1 END) as calls_made,
                COUNT(CASE WHEN event = 'routed' THEN 1 END) as routed,
                COUNT(CASE WHEN event = 'completed' THEN 1 END) as completed
            FROM speed_to_lead_events
            WHERE organization_id = :org_id
                AND created_at >= CURRENT_DATE - :days
        """), {"org_id": org_id, "days": days}).fetchone()

        return {
            "period_days": days,
            "total_leads_triggered": stats.total_leads if stats else 0,
            "sms_sent": stats.sms_sent if stats else 0,
            "calls_made": stats.calls_made if stats else 0,
            "leads_routed": stats.routed if stats else 0,
            "completed": stats.completed if stats else 0,
        }
    except Exception:
        return {"period_days": days, "total_leads_triggered": 0, "note": "Events table not yet created"}
