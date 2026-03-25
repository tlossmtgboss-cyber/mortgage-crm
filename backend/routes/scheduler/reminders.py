"""
Scheduler Reminder Routes - CRUD for reminder templates and send history.

Endpoints:
  - GET    /reminders/templates                List org's reminder templates
  - POST   /reminders/templates                Create custom template
  - PUT    /reminders/templates/{id}           Update template
  - DELETE /reminders/templates/{id}           Delete template
  - GET    /reminders/log                      View reminder send history
  - POST   /reminders/test                     Send test reminder
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timezone
from typing import Optional
import logging
import re

from routes.scheduler._helpers import get_current_user, get_models, _get_org_id, _audit_log
from db import get_db

logger = logging.getLogger(__name__)

# SEC-007: Email format validation for test endpoints
_EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

router = APIRouter()


# ============================================================================
# LIST TEMPLATES
# ============================================================================

@router.get("/reminders/templates")
async def list_reminder_templates(
    request: Request,
    include_inactive: bool = Query(False, description="Include deactivated templates"),
    db: Session = Depends(get_db),
):
    """List all reminder templates for the authenticated user's organization."""
    from database.models.reminder_config import ReminderTemplate

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    query = db.query(ReminderTemplate).filter(
        ReminderTemplate.organization_id == org_id,
    )

    if not include_inactive:
        query = query.filter(ReminderTemplate.is_active == True)

    templates = query.order_by(ReminderTemplate.timing_minutes.desc()).all()

    return {
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "channel": t.channel,
                "timing_minutes": t.timing_minutes,
                "timing_label": _timing_label(t.timing_minutes),
                "subject_template": t.subject_template,
                "body_template": t.body_template,
                "is_active": t.is_active,
                "appointment_type_id": t.appointment_type_id,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in templates
        ],
        "total": len(templates),
    }


# ============================================================================
# CREATE TEMPLATE
# ============================================================================

@router.post("/reminders/templates", status_code=201)
async def create_reminder_template(
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a new reminder template for the organization."""
    from database.models.reminder_config import ReminderTemplate

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    body = await request.json()

    # Validate required fields
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    channel = body.get("channel", "email")
    if channel not in ("email", "sms", "both"):
        raise HTTPException(status_code=400, detail="channel must be email, sms, or both")

    timing_minutes = body.get("timing_minutes")
    if timing_minutes is None or not isinstance(timing_minutes, int) or timing_minutes < 1:
        raise HTTPException(status_code=400, detail="timing_minutes must be a positive integer")

    body_template = (body.get("body_template") or "").strip()
    if not body_template:
        raise HTTPException(status_code=400, detail="body_template is required")

    # Cap at 50 templates per org to prevent abuse
    existing_count = (
        db.query(ReminderTemplate)
        .filter(ReminderTemplate.organization_id == org_id)
        .count()
    )
    if existing_count >= 50:
        raise HTTPException(status_code=400, detail="Maximum of 50 reminder templates per organization")

    template = ReminderTemplate(
        organization_id=org_id,
        name=name,
        channel=channel,
        timing_minutes=timing_minutes,
        subject_template=(body.get("subject_template") or "").strip() or None,
        body_template=body_template,
        is_active=body.get("is_active", True),
        appointment_type_id=body.get("appointment_type_id"),
    )
    db.add(template)
    db.flush()

    _audit_log(
        db, org_id, getattr(user, "id", None), "created",
        "reminder_template", template.id,
        changes={"name": template.name, "channel": template.channel},
        request=request,
    )
    db.commit()

    return {
        "id": template.id,
        "name": template.name,
        "channel": template.channel,
        "timing_minutes": template.timing_minutes,
        "timing_label": _timing_label(template.timing_minutes),
        "subject_template": template.subject_template,
        "body_template": template.body_template,
        "is_active": template.is_active,
        "appointment_type_id": template.appointment_type_id,
        "created_at": template.created_at.isoformat() if template.created_at else None,
    }


# ============================================================================
# UPDATE TEMPLATE
# ============================================================================

@router.put("/reminders/templates/{template_id}")
async def update_reminder_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update an existing reminder template."""
    from database.models.reminder_config import ReminderTemplate

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    template = (
        db.query(ReminderTemplate)
        .filter(
            ReminderTemplate.id == template_id,
            ReminderTemplate.organization_id == org_id,
        )
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    body = await request.json()
    changes = {}

    if "name" in body:
        name = (body["name"] or "").strip()
        if name:
            changes["name"] = {"old": template.name, "new": name}
            template.name = name

    if "channel" in body:
        channel = body["channel"]
        if channel not in ("email", "sms", "both"):
            raise HTTPException(status_code=400, detail="channel must be email, sms, or both")
        changes["channel"] = {"old": template.channel, "new": channel}
        template.channel = channel

    if "timing_minutes" in body:
        timing = body["timing_minutes"]
        if not isinstance(timing, int) or timing < 1:
            raise HTTPException(status_code=400, detail="timing_minutes must be a positive integer")
        changes["timing_minutes"] = {"old": template.timing_minutes, "new": timing}
        template.timing_minutes = timing

    if "subject_template" in body:
        template.subject_template = (body["subject_template"] or "").strip() or None

    if "body_template" in body:
        bt = (body["body_template"] or "").strip()
        if bt:
            template.body_template = bt

    if "is_active" in body:
        changes["is_active"] = {"old": template.is_active, "new": body["is_active"]}
        template.is_active = bool(body["is_active"])

    if "appointment_type_id" in body:
        template.appointment_type_id = body["appointment_type_id"]

    if changes:
        _audit_log(
            db, org_id, getattr(user, "id", None), "updated",
            "reminder_template", template.id,
            changes=changes,
            request=request,
        )

    db.commit()

    return {
        "id": template.id,
        "name": template.name,
        "channel": template.channel,
        "timing_minutes": template.timing_minutes,
        "timing_label": _timing_label(template.timing_minutes),
        "subject_template": template.subject_template,
        "body_template": template.body_template,
        "is_active": template.is_active,
        "appointment_type_id": template.appointment_type_id,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


# ============================================================================
# DELETE TEMPLATE
# ============================================================================

@router.delete("/reminders/templates/{template_id}")
async def delete_reminder_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete a reminder template. Associated logs are preserved (SET NULL)."""
    from database.models.reminder_config import ReminderTemplate

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    template = (
        db.query(ReminderTemplate)
        .filter(
            ReminderTemplate.id == template_id,
            ReminderTemplate.organization_id == org_id,
        )
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template_name = template.name
    template.is_active = False

    _audit_log(
        db, org_id, getattr(user, "id", None), "deleted",
        "reminder_template", template_id,
        changes={"name": template_name},
        request=request,
    )
    db.commit()

    return {"success": True, "deleted_id": template_id}


# ============================================================================
# VIEW SEND HISTORY
# ============================================================================

@router.get("/reminders/log")
async def list_reminder_logs(
    request: Request,
    appointment_id: Optional[int] = Query(None, description="Filter by appointment"),
    status: Optional[str] = Query(None, description="Filter by status (sent/failed/skipped)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """View reminder send history with optional filters."""
    from database.models.reminder_config import ReminderLog, ReminderTemplate

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    models = get_models()
    Appointment = models["Appointment"]

    # Join through appointment to enforce org isolation
    query = (
        db.query(ReminderLog)
        .join(Appointment, Appointment.id == ReminderLog.appointment_id)
        .filter(Appointment.organization_id == org_id)
    )

    if appointment_id:
        query = query.filter(ReminderLog.appointment_id == appointment_id)

    if status:
        if status not in ("sent", "failed", "skipped"):
            raise HTTPException(status_code=400, detail="status must be sent, failed, or skipped")
        query = query.filter(ReminderLog.status == status)

    total = query.count()
    logs = query.order_by(desc(ReminderLog.sent_at)).offset(offset).limit(limit).all()

    return {
        "logs": [
            {
                "id": log.id,
                "appointment_id": log.appointment_id,
                "template_id": log.template_id,
                "channel": log.channel,
                "status": log.status,
                "sent_at": log.sent_at.isoformat() if log.sent_at else None,
                "error_message": log.error_message,
                "external_id": log.external_id,
                "recipient_email": log.recipient_email,
                "recipient_phone": log.recipient_phone,
            }
            for log in logs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ============================================================================
# SEND TEST REMINDER
# ============================================================================

@router.post("/reminders/test")
async def send_test_reminder(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Send a test reminder using a template with sample data.

    Body:
        template_id: int - template to test
        email: str (optional) - override recipient email
        phone: str (optional) - override recipient phone
    """
    from database.models.reminder_config import ReminderTemplate
    from services.reminder_service import ReminderService

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    body = await request.json()
    template_id = body.get("template_id")
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id is required")

    template = (
        db.query(ReminderTemplate)
        .filter(
            ReminderTemplate.id == template_id,
            ReminderTemplate.organization_id == org_id,
        )
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Build sample variables
    sample_vars = {
        "client_name": "Jane Doe",
        "appointment_type": "Discovery Call",
        "date": "March 15, 2026",
        "time": "2:00 PM",
        "lo_name": f"{getattr(user, 'first_name', 'Test')} {getattr(user, 'last_name', 'User')}".strip(),
        "location": "Video Call",
        "join_url": "https://meet.example.com/test-meeting",
        "cancel_url": "https://app.perenniaai.com/appointments/0/cancel",
        "reschedule_url": "https://app.perenniaai.com/appointments/0/reschedule",
    }

    rendered_subject = ReminderService.render_template(template.subject_template or "", sample_vars)
    rendered_body = ReminderService.render_template(template.body_template, sample_vars)

    results = []

    # Send via configured channels
    override_email = body.get("email") or getattr(user, "email", None)
    override_phone = body.get("phone")

    # SEC-007: Validate email format before sending
    if override_email:
        if not _EMAIL_REGEX.match(override_email) or len(override_email) > 254:
            raise HTTPException(status_code=422, detail="Invalid email format")

    if template.channel in ("email", "both") and override_email:
        email_result = ReminderService._send_email(override_email, rendered_subject, rendered_body)
        results.append({"channel": "email", "to": override_email, **email_result})

    if template.channel in ("sms", "both") and override_phone:
        sms_result = ReminderService._send_sms(override_phone, rendered_body)
        results.append({"channel": "sms", "to": override_phone, **sms_result})

    if not results:
        return {
            "success": False,
            "message": "No recipient provided for the template's channel(s)",
            "preview": {
                "subject": rendered_subject,
                "body": rendered_body,
            },
        }

    return {
        "success": any(r.get("success") for r in results),
        "results": results,
        "preview": {
            "subject": rendered_subject,
            "body": rendered_body,
        },
    }


# ============================================================================
# HELPERS
# ============================================================================

def _timing_label(minutes: int) -> str:
    """Convert minutes to human-readable label."""
    if minutes >= 1440:
        days = minutes // 1440
        return f"{days} day{'s' if days > 1 else ''} before"
    elif minutes >= 60:
        hours = minutes // 60
        return f"{hours} hour{'s' if hours > 1 else ''} before"
    else:
        return f"{minutes} minute{'s' if minutes > 1 else ''} before"
