"""
Mobile-Optimized API Routes

Lightweight endpoints designed for mobile clients with minimal payloads,
single-request aggregation, and battery-friendly patterns.  Each endpoint
returns only the fields the mobile UI actually renders — no bloat.

Endpoints:
  GET  /api/v1/mobile/dashboard         - Aggregated home screen data (one round-trip)
  GET  /api/v1/mobile/pipeline           - Lightweight pipeline loan cards
  GET  /api/v1/mobile/leads              - Lightweight lead cards
  GET  /api/v1/mobile/notifications      - Paginated notifications
  POST /api/v1/mobile/quick-lead         - Speed-to-lead capture (minimal fields)
  GET  /api/v1/mobile/rate-lock-alerts   - Expiring rate lock alerts

Registration:
  In main.py:
    from routes.mobile_api_routes import register_mobile_api_routes
    register_mobile_api_routes(app=app, get_db=get_db, get_current_user=get_current_user)
"""

from datetime import datetime, timezone, timedelta
import logging
from typing import Optional, List

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, case, cast, String, and_, or_, text, literal_column, select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model imports (avoids circular import at module load time)
# ---------------------------------------------------------------------------
_models_loaded = False
_Loan = None
_Lead = None
_Task = None
_AITask = None
_Activity = None
_Notification = None
_Appointment = None
_User = None


def _ensure_models():
    global _models_loaded, _Loan, _Lead, _Task, _AITask, _Activity
    global _Notification, _Appointment, _User
    if _models_loaded:
        return
    from database.models import Loan, Lead, Task, AITask, Activity, Notification, User
    from database.models.scheduler import Appointment
    _Loan = Loan
    _Lead = Lead
    _Task = Task
    _AITask = AITask
    _Activity = Activity
    _Notification = Notification
    _Appointment = Appointment
    _User = User
    _models_loaded = True


# Terminal loan stages excluded from active pipeline counts
TERMINAL_STAGES = (
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY"
)

# Stages that indicate a loan is near closing
CLOSING_STAGES = ("CTC", "CLEAR_TO_CLOSE", "DOCS", "DOCS_OUT", "CLOSING")


# ---------------------------------------------------------------------------
# Pydantic schemas — minimal shapes for mobile payloads
# ---------------------------------------------------------------------------

class QuickLeadCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    source: Optional[str] = Field("mobile_app", max_length=50)
    notes: Optional[str] = Field(None, max_length=500)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _relative_time(dt: Optional[datetime]) -> str:
    """Return human-friendly relative time string (e.g. '2h ago')."""
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    # Handle naive datetimes
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    return dt.strftime("%m/%d/%Y")


def _format_time_12h(dt: Optional[datetime]) -> str:
    """Format datetime to '10:00 AM' style."""
    if dt is None:
        return ""
    return dt.strftime("%-I:%M %p")


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_mobile_api_routes(app, get_db, get_current_user, **kwargs):
    """
    Register mobile-optimized API routes.

    All endpoints require authentication via get_current_user and enforce
    tenant isolation via the user's organization_id.
    """

    # =================================================================
    # 1. GET /api/v1/mobile/dashboard
    # =================================================================
    @app.get("/api/v1/mobile/dashboard", tags=["Mobile"])
    async def mobile_dashboard(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Aggregated mobile home screen data in a single request.

        Returns pipeline summary, task count, unread notifications,
        urgent alerts, today's schedule, and recent activity.
        """
        _ensure_models()
        org_id = current_user.organization_id
        user_id = current_user.id
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # --- Pipeline summary (single aggregate query) ---
        pipeline_row = db.query(
            func.count(_Loan.id).label("active"),
            func.count(
                case(
                    (cast(_Loan.stage, String).in_(CLOSING_STAGES), _Loan.id),
                    else_=None,
                )
            ).label("closing_soon"),
            func.coalesce(func.sum(_Loan.amount), 0).label("volume"),
        ).filter(
            _Loan.organization_id == org_id,
            cast(_Loan.stage, String).notin_(TERMINAL_STAGES),
        ).first()

        pipeline = {
            "active": pipeline_row.active or 0,
            "closing_soon": pipeline_row.closing_soon or 0,
            "volume": float(pipeline_row.volume or 0),
        }

        # --- Tasks due today ---
        tasks_due = db.query(func.count(_Task.id)).filter(
            _Task.organization_id == org_id,
            _Task.owner_id == user_id,
            _Task.status == "pending",
            _Task.due_date >= today_start,
            _Task.due_date < today_end,
        ).scalar() or 0

        # --- Unread notifications ---
        unread_count = db.query(func.count(_Notification.id)).filter(
            _Notification.user_id == user_id,
            _Notification.is_read == False,  # noqa: E712
        ).scalar() or 0

        # --- Urgent alerts: expiring rate locks (within 48 hours) ---
        lock_cutoff = now + timedelta(hours=48)
        lock_alerts_q = db.query(
            _Loan.id,
            _Loan.loan_number,
            _Loan.borrower_name,
            _Loan.lock_expiration_date,
        ).filter(
            _Loan.organization_id == org_id,
            cast(_Loan.stage, String).notin_(TERMINAL_STAGES),
            _Loan.lock_expiration_date.isnot(None),
            _Loan.lock_expiration_date > now,
            _Loan.lock_expiration_date <= lock_cutoff,
        ).order_by(_Loan.lock_expiration_date.asc()).limit(10).all()

        urgent_alerts = []
        for loan in lock_alerts_q:
            lock_dt = loan.lock_expiration_date
            if lock_dt.tzinfo is None:
                lock_dt = lock_dt.replace(tzinfo=timezone.utc)
            hours_remaining = max(0, int((lock_dt - now).total_seconds() / 3600))
            urgent_alerts.append({
                "type": "rate_lock",
                "loan_number": loan.loan_number,
                "hours_remaining": hours_remaining,
                "borrower": loan.borrower_name,
            })

        # --- Today's schedule (appointments) ---
        try:
            schedule_q = db.query(
                _Appointment.id,
                _Appointment.title,
                _Appointment.meeting_type,
                _Appointment.scheduled_start,
                _Appointment.attendee_name,
            ).filter(
                _Appointment.organization_id == org_id,
                _Appointment.assigned_user_id == user_id,
                _Appointment.scheduled_start >= today_start,
                _Appointment.scheduled_start < today_end,
                _Appointment.status.notin_(["cancelled", "rescheduled"]),
            ).order_by(_Appointment.scheduled_start.asc()).limit(10).all()

            today_schedule = [
                {
                    "time": _format_time_12h(appt.scheduled_start),
                    "type": str(appt.meeting_type.value) if appt.meeting_type else "meeting",
                    "contact": appt.attendee_name or appt.title,
                    "id": str(appt.id),
                }
                for appt in schedule_q
            ]
        except Exception as e:
            logger.debug(f"Schedule query skipped (table may not exist): {e}")
            today_schedule = []

        # --- Recent activity (last 10) ---
        recent_q = db.query(
            _Activity.type,
            _Activity.content,
            _Activity.created_at,
            _Activity.lead_id,
            _Activity.loan_id,
        ).filter(
            _Activity.organization_id == org_id,
            _Activity.user_id == user_id,
        ).order_by(_Activity.created_at.desc()).limit(10).all()

        recent_activity = [
            {
                "type": str(act.type.value) if hasattr(act.type, "value") else str(act.type),
                "summary": (act.content or "")[:120],
                "time": _relative_time(act.created_at),
                "entity_id": str(act.loan_id or act.lead_id or ""),
            }
            for act in recent_q
        ]

        return {
            "pipeline": pipeline,
            "tasks_due_today": tasks_due,
            "unread_notifications": unread_count,
            "urgent_alerts": urgent_alerts,
            "today_schedule": today_schedule,
            "recent_activity": recent_activity,
        }

    # =================================================================
    # 2. GET /api/v1/mobile/pipeline
    # =================================================================
    @app.get("/api/v1/mobile/pipeline", tags=["Mobile"])
    async def mobile_pipeline(
        stage: Optional[str] = Query(None, description="Filter by loan stage (e.g. PROCESSING)"),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Lightweight pipeline loan cards optimized for mobile list view.
        Only returns fields the mobile card renders.
        """
        _ensure_models()
        org_id = current_user.organization_id
        now = datetime.now(timezone.utc)

        filters = [
            _Loan.organization_id == org_id,
            cast(_Loan.stage, String).notin_(TERMINAL_STAGES),
        ]
        if stage:
            filters.append(cast(_Loan.stage, String) == stage.upper())

        # Aggregate for the header
        agg = db.query(
            func.count(_Loan.id).label("count"),
            func.coalesce(func.sum(_Loan.amount), 0).label("total_volume"),
        ).filter(*filters).first()

        # Loan cards
        loans_q = db.query(
            _Loan.id,
            _Loan.loan_number,
            _Loan.borrower_name,
            _Loan.amount,
            _Loan.stage,
            _Loan.stage_changed_at,
            _Loan.property_city,
            _Loan.loan_type,
            _Loan.ai_insights,
        ).filter(*filters).order_by(
            _Loan.stage_changed_at.asc().nullsfirst(),
        ).offset(offset).limit(limit).all()

        loans = []
        for ln in loans_q:
            days_in_stage = 0
            if ln.stage_changed_at:
                sca = ln.stage_changed_at
                if sca.tzinfo is None:
                    sca = sca.replace(tzinfo=timezone.utc)
                days_in_stage = max(0, (now - sca).days)

            loans.append({
                "id": str(ln.id),
                "loan_number": ln.loan_number,
                "borrower_name": ln.borrower_name,
                "amount": float(ln.amount or 0),
                "days_in_stage": days_in_stage,
                "next_action": (ln.ai_insights or "")[:120],
                "property_city": ln.property_city or "",
                "loan_type": ln.loan_type or "",
            })

        return {
            "stage": stage.upper() if stage else "ALL",
            "count": agg.count or 0,
            "total_volume": float(agg.total_volume or 0),
            "loans": loans,
        }

    # =================================================================
    # 3. GET /api/v1/mobile/leads
    # =================================================================
    @app.get("/api/v1/mobile/leads", tags=["Mobile"])
    async def mobile_leads(
        filter: Optional[str] = Query(None, description="Filter: hot, new, mine, all"),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Lightweight lead cards for mobile list view.
        Supports 'hot' (score >= 70), 'new' (stage=New), 'mine' (owner=current user).
        """
        _ensure_models()
        org_id = current_user.organization_id
        user_id = current_user.id
        now = datetime.now(timezone.utc)

        filters = [_Lead.organization_id == org_id]

        if filter == "hot":
            filters.append(_Lead.ai_score >= 70)
        elif filter == "new":
            filters.append(cast(_Lead.stage, String) == "New")
        elif filter == "mine":
            filters.append(_Lead.owner_id == user_id)
        # 'all' or None => no extra filter

        total = db.query(func.count(_Lead.id)).filter(*filters).scalar() or 0

        leads_q = db.query(
            _Lead.id,
            _Lead.first_name,
            _Lead.last_name,
            _Lead.phone,
            _Lead.email,
            _Lead.ai_score,
            _Lead.source,
            _Lead.last_contact,
            _Lead.loan_purpose,
            _Lead.stage,
        ).filter(*filters).order_by(
            _Lead.ai_score.desc().nullslast(),
            _Lead.last_contact.desc().nullslast(),
        ).offset(offset).limit(limit).all()

        leads = []
        for ld in leads_q:
            score = ld.ai_score or 0
            if score >= 80:
                grade = "A"
            elif score >= 60:
                grade = "B"
            elif score >= 40:
                grade = "C"
            else:
                grade = "D"

            leads.append({
                "id": str(ld.id),
                "name": f"{ld.first_name or ''} {ld.last_name or ''}".strip() or "Unknown",
                "phone": ld.phone or "",
                "email": ld.email or "",
                "score": score,
                "grade": grade,
                "source": ld.source or "",
                "last_contact": _relative_time(ld.last_contact),
                "loan_purpose": ld.loan_purpose or "",
                "stage": str(ld.stage) if ld.stage else "",
            })

        return {
            "filter": filter or "all",
            "count": total,
            "leads": leads,
        }

    # =================================================================
    # 4. GET /api/v1/mobile/notifications
    # =================================================================
    @app.get("/api/v1/mobile/notifications", tags=["Mobile"])
    async def mobile_notifications(
        unread_only: bool = Query(False, description="Only return unread notifications"),
        limit: int = Query(30, ge=1, le=100),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Paginated notifications optimized for mobile list view.
        Returns lightweight notification objects with unread count.
        """
        _ensure_models()
        user_id = current_user.id

        filters = [_Notification.user_id == user_id]
        if unread_only:
            filters.append(_Notification.is_read == False)  # noqa: E712

        total = db.query(func.count(_Notification.id)).filter(*filters).scalar() or 0

        unread_total = db.query(func.count(_Notification.id)).filter(
            _Notification.user_id == user_id,
            _Notification.is_read == False,  # noqa: E712
        ).scalar() or 0

        notifs_q = db.query(
            _Notification.id,
            _Notification.type,
            _Notification.title,
            _Notification.message,
            _Notification.link,
            _Notification.is_read,
            _Notification.created_at,
        ).filter(*filters).order_by(
            _Notification.created_at.desc(),
        ).offset(offset).limit(limit).all()

        notifications = [
            {
                "id": str(n.id),
                "type": n.type or "",
                "title": n.title or "",
                "message": (n.message or "")[:200],
                "link": n.link or "",
                "is_read": n.is_read,
                "time": _relative_time(n.created_at),
            }
            for n in notifs_q
        ]

        return {
            "total": total,
            "unread_count": unread_total,
            "notifications": notifications,
            "has_more": (offset + limit) < total,
        }

    # =================================================================
    # 5. POST /api/v1/mobile/quick-lead
    # =================================================================
    @app.post("/api/v1/mobile/quick-lead", tags=["Mobile"], status_code=201)
    async def mobile_quick_lead(
        payload: QuickLeadCreate,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """
        Minimal-field lead capture for speed-to-lead from mobile.
        Creates a new lead assigned to the current user with stage 'New'.
        """
        _ensure_models()
        org_id = current_user.organization_id
        user_id = current_user.id

        lead = _Lead(
            organization_id=org_id,
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            name=f"{payload.first_name.strip()} {payload.last_name.strip()}",
            phone=payload.phone.strip() if payload.phone else None,
            email=payload.email.strip().lower() if payload.email else None,
            source=payload.source or "mobile_app",
            notes=payload.notes,
            stage="New",
            owner_id=user_id,
            ai_score=50,
            lead_received_date=datetime.now(timezone.utc),
        )

        db.add(lead)
        await db.flush()

        from services.client_file_service import ensure_client_file
        ensure_client_file(db, lead)

        await db.commit()
        await db.refresh(lead)

        # Fire SLA tracking for the new lead (best-effort)
        try:
            from services.sla_tracking_service import track_lead_created
            track_lead_created(db, lead)
        except Exception as e:
            logger.debug(f"SLA tracking for new lead skipped: {e}")

        return {
            "id": str(lead.id),
            "name": lead.name,
            "stage": lead.stage,
            "created": True,
        }

    # =================================================================
    # 6. GET /api/v1/mobile/rate-lock-alerts
    # =================================================================
    @app.get("/api/v1/mobile/rate-lock-alerts", tags=["Mobile"])
    async def mobile_rate_lock_alerts(
        hours: int = Query(72, ge=1, le=720, description="Window in hours to look ahead"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Rate lock expiration alerts for the mobile alert banner.
        Returns loans with locks expiring within the given window,
        sorted by urgency (soonest first).
        """
        _ensure_models()
        org_id = current_user.organization_id
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours)

        alerts_q = db.query(
            _Loan.id,
            _Loan.loan_number,
            _Loan.borrower_name,
            _Loan.amount,
            _Loan.lock_expiration_date,
            _Loan.rate,
            _Loan.loan_type,
            _Loan.stage,
        ).filter(
            _Loan.organization_id == org_id,
            cast(_Loan.stage, String).notin_(TERMINAL_STAGES),
            _Loan.lock_expiration_date.isnot(None),
            _Loan.lock_expiration_date <= cutoff,
        ).order_by(
            _Loan.lock_expiration_date.asc(),
        ).limit(50).all()

        alerts = []
        for loan in alerts_q:
            lock_dt = loan.lock_expiration_date
            if lock_dt.tzinfo is None:
                lock_dt = lock_dt.replace(tzinfo=timezone.utc)
            delta = lock_dt - now
            hours_remaining = max(0, int(delta.total_seconds() / 3600))
            is_expired = delta.total_seconds() <= 0

            alerts.append({
                "id": str(loan.id),
                "loan_number": loan.loan_number,
                "borrower": loan.borrower_name,
                "amount": float(loan.amount or 0),
                "rate": float(loan.rate or 0),
                "loan_type": loan.loan_type or "",
                "stage": str(loan.stage) if loan.stage else "",
                "lock_expires": lock_dt.isoformat(),
                "hours_remaining": hours_remaining,
                "is_expired": is_expired,
                "urgency": "expired" if is_expired else "critical" if hours_remaining <= 24 else "warning",
            })

        return {
            "window_hours": hours,
            "total": len(alerts),
            "expired_count": len([a for a in alerts if a["is_expired"]]),
            "alerts": alerts,
        }

    logger.info(
        "Mobile API routes registered: dashboard, pipeline, leads, "
        "notifications, quick-lead, rate-lock-alerts"
    )
