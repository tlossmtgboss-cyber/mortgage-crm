"""
Recovery Opt-Out Routes

Public and authenticated endpoints for managing no-show recovery opt-outs.

Public endpoints (no auth required):
    GET  /api/v1/scheduler/recovery/opt-out/{token}  - Opt-out via signed link
    POST /api/v1/scheduler/recovery/opt-out           - Opt-out via form/API

Authenticated endpoints (LO/admin):
    GET    /api/v1/scheduler/recovery/opt-outs         - List opt-outs for org
    DELETE /api/v1/scheduler/recovery/opt-out/{email}  - Remove opt-out (re-subscribe)
    GET    /api/v1/scheduler/recovery/chronic-no-shows - List chronic no-show contacts
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scheduler-recovery"])

# Module-level auth function, set via set_dependencies()
_get_current_user_func = None


def set_dependencies(get_current_user_func=None, **kwargs):
    """Set auth dependency from parent module."""
    global _get_current_user_func
    if get_current_user_func:
        _get_current_user_func = get_current_user_func


async def get_current_user(request, db):
    """Get current authenticated user."""
    if _get_current_user_func:
        return await _get_current_user_func(request, db)
    raise HTTPException(status_code=401, detail="Auth not configured")


# ============================================================================
# PUBLIC ENDPOINTS (no auth)
# ============================================================================

@router.get("/api/v1/scheduler/recovery/opt-out/{token}", response_class=HTMLResponse)
async def opt_out_via_link(
    token: str,
    db: Session = Depends(get_db),
):
    """
    Public endpoint: process opt-out from a signed link in a recovery email.

    The token is a JWT containing the email and organization_id.
    Returns a simple HTML confirmation page.
    """
    from services.no_show_recovery import (
        verify_opt_out_token,
        no_show_recovery_service,
    )

    payload = verify_opt_out_token(token)

    if not payload:
        return HTMLResponse(
            content=_render_opt_out_page(
                success=False,
                message="This opt-out link has expired or is invalid. "
                        "Please contact us directly if you'd like to unsubscribe.",
            ),
            status_code=400,
        )

    email = payload["email"]
    org_id = payload["org_id"]
    appt_id = payload.get("appt_id")

    result = no_show_recovery_service.record_opt_out(
        db=db,
        email=email,
        organization_id=org_id,
        reason="Opted out via email link",
        source="link",
        appointment_id=appt_id,
    )
    db.commit()

    return HTMLResponse(
        content=_render_opt_out_page(
            success=True,
            message="You have been unsubscribed from appointment follow-up "
                    "messages. We respect your preference and will not send "
                    "further recovery messages.",
        ),
        status_code=200,
    )


@router.post("/api/v1/scheduler/recovery/opt-out")
async def opt_out_via_api(
    email: str = Query(..., description="Email to opt out"),
    token: str = Query(..., description="Signed verification token"),
    reason: Optional[str] = Query(None, description="Optional reason"),
    db: Session = Depends(get_db),
):
    """
    Public endpoint: opt out via API/form POST with a signed token.

    Used by SMS STOP handling or custom opt-out forms.
    """
    from services.no_show_recovery import (
        verify_opt_out_token,
        no_show_recovery_service,
    )

    payload = verify_opt_out_token(token)

    if not payload:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired opt-out token",
        )

    if payload["email"] != email:
        raise HTTPException(
            status_code=400,
            detail="Email does not match token",
        )

    result = no_show_recovery_service.record_opt_out(
        db=db,
        email=email,
        organization_id=payload["org_id"],
        reason=reason or "Opted out via API",
        source="link",
        appointment_id=payload.get("appt_id"),
    )
    db.commit()

    return {
        "status": "success",
        "message": "You have been unsubscribed from recovery messages.",
        "detail": result,
    }


@router.post("/api/v1/scheduler/recovery/sms-stop")
async def handle_sms_stop(
    phone: str = Query(..., description="Phone number that sent STOP"),
    organization_id: int = Query(..., description="Organization ID"),
    db: Session = Depends(get_db),
):
    """
    Internal endpoint: called by SMS webhook handler when a STOP reply
    is received during a recovery sequence.

    Looks up the attendee email by phone number from recent appointments
    and records the opt-out.
    """
    from services.no_show_recovery import no_show_recovery_service

    _models = no_show_recovery_service._get_models()
    Appointment = _models["Appointment"]

    # Find the most recent appointment with this phone number
    appointment = db.query(Appointment).filter(
        Appointment.attendee_phone == phone,
        Appointment.organization_id == organization_id,
    ).order_by(Appointment.created_at.desc()).first()

    if not appointment or not appointment.attendee_email:
        logger.warning(
            f"SMS STOP from {phone} but no matching appointment found "
            f"in org {organization_id}"
        )
        return {
            "status": "warning",
            "message": "No matching appointment found for this phone number",
        }

    result = no_show_recovery_service.record_opt_out(
        db=db,
        email=appointment.attendee_email,
        organization_id=organization_id,
        phone=phone,
        reason="Replied STOP to recovery SMS",
        source="sms_stop",
        appointment_id=appointment.id,
    )
    db.commit()

    return {
        "status": "success",
        "message": "Opt-out recorded from SMS STOP",
        "detail": result,
    }


# ============================================================================
# AUTHENTICATED ENDPOINTS (LO/admin)
# ============================================================================

@router.get("/api/v1/scheduler/recovery/opt-outs")
async def list_opt_outs(
    request,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List all opt-out records for the current user's organization.
    Requires authentication.
    """
    from database.models.recovery_opt_out import RecoveryOptOut

    user = await get_current_user(request, db)
    org_id = getattr(user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")

    query = db.query(RecoveryOptOut).filter(
        RecoveryOptOut.organization_id == org_id,
    ).order_by(RecoveryOptOut.opted_out_at.desc())

    total = query.count()
    records = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "opt_outs": [
            {
                "id": r.id,
                "email": r.email,
                "phone": r.phone,
                "opted_out_at": r.opted_out_at.isoformat() if r.opted_out_at else None,
                "reason": r.reason,
                "source": r.opt_out_source,
            }
            for r in records
        ],
    }


@router.delete("/api/v1/scheduler/recovery/opt-out/{email}")
async def remove_opt_out(
    email: str,
    request,
    db: Session = Depends(get_db),
):
    """
    Remove an opt-out record (re-subscribe an attendee).
    Requires authentication. Only affects the current user's organization.
    """
    from services.no_show_recovery import no_show_recovery_service

    user = await get_current_user(request, db)
    org_id = getattr(user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")

    removed = no_show_recovery_service.remove_opt_out(db, email, org_id)
    db.commit()

    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"No opt-out record found for {email}",
        )

    return {
        "status": "success",
        "message": f"Opt-out removed for {email}. Recovery messages re-enabled.",
    }


@router.get("/api/v1/scheduler/recovery/chronic-no-shows")
async def list_chronic_no_shows(
    request,
    db: Session = Depends(get_db),
    days: int = Query(90, ge=30, le=365, description="Lookback window in days"),
    threshold: int = Query(3, ge=2, le=10, description="Minimum no-show count"),
):
    """
    List contacts flagged as chronic no-shows within the given window.
    Requires authentication.
    """
    from smart_scheduler_models import AppointmentStatus
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func

    user = await get_current_user(request, db)
    org_id = getattr(user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")

    from services.no_show_recovery import no_show_recovery_service

    _models = no_show_recovery_service._get_models()
    Appointment = _models["Appointment"]

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Group by attendee_email, count no-shows
    chronic = (
        db.query(
            Appointment.attendee_email,
            Appointment.attendee_name,
            Appointment.attendee_phone,
            func.count(Appointment.id).label("no_show_count"),
            func.max(Appointment.no_show_at).label("last_no_show"),
        )
        .filter(
            Appointment.organization_id == org_id,
            Appointment.status == AppointmentStatus.NO_SHOW,
            Appointment.no_show_at >= cutoff,
            Appointment.attendee_email.isnot(None),
        )
        .group_by(
            Appointment.attendee_email,
            Appointment.attendee_name,
            Appointment.attendee_phone,
        )
        .having(func.count(Appointment.id) >= threshold)
        .order_by(func.count(Appointment.id).desc())
        .all()
    )

    return {
        "window_days": days,
        "threshold": threshold,
        "total": len(chronic),
        "contacts": [
            {
                "email": row.attendee_email,
                "name": row.attendee_name,
                "phone": row.attendee_phone,
                "no_show_count": row.no_show_count,
                "last_no_show": row.last_no_show.isoformat() if row.last_no_show else None,
                "is_opted_out": no_show_recovery_service.is_opted_out(
                    db, row.attendee_email, org_id
                ),
            }
            for row in chronic
        ],
    }


# ============================================================================
# HTML rendering helper
# ============================================================================

def _render_opt_out_page(success: bool, message: str) -> str:
    """Render a simple HTML opt-out confirmation page."""
    import html as html_module

    safe_message = html_module.escape(message)
    icon = "&#10003;" if success else "&#10007;"
    icon_color = "#10b981" if success else "#ef4444"
    title = "Unsubscribed" if success else "Error"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Perennia AI</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f6f9fc;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }}
        .card {{
            background: white;
            border-radius: 16px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.08);
            padding: 48px;
            max-width: 480px;
            text-align: center;
        }}
        .icon {{
            font-size: 48px;
            color: {icon_color};
            margin-bottom: 16px;
        }}
        h1 {{
            color: #111827;
            font-size: 24px;
            margin: 0 0 16px 0;
        }}
        p {{
            color: #6b7280;
            font-size: 16px;
            line-height: 1.6;
        }}
        .footer {{
            margin-top: 32px;
            color: #9ca3af;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">{icon}</div>
        <h1>{title}</h1>
        <p>{safe_message}</p>
        <p class="footer">Perennia AI</p>
    </div>
</body>
</html>"""
