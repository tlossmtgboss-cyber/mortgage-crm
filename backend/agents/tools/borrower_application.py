"""
Borrower Application Agent Tools

8 @mortgage_tool tools for the borrower-facing AI assistant.
All tools are scoped to a single borrower's application via organization_id.
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from agents.tools.base import mortgage_tool, get_db, execute_query, execute_single

logger = logging.getLogger(__name__)


@mortgage_tool(
    name="get_application_state",
    description="Fetch the borrower's in-progress URLA application sections, completion percentage, and current step",
    agent_roles=["borrower_application_agent"],
)
def get_application_state(application_id: str, organization_id: int) -> Dict[str, Any]:
    db = get_db()
    try:
        app_row = execute_single(
            db,
            "SELECT id, status, current_step, completion_pct, created_at, updated_at "
            "FROM pos_applications WHERE id = :app_id AND organization_id = :org_id",
            {"app_id": application_id, "org_id": organization_id},
        )
        if not app_row:
            return {"error": "Application not found"}

        sections = execute_query(
            db,
            "SELECT section_key, is_complete, data, updated_at "
            "FROM pos_application_sections WHERE application_id = :app_id "
            "ORDER BY section_key",
            {"app_id": application_id},
        )

        section_summaries = {}
        for s in sections:
            data = s[2] or {}
            field_count = len([v for v in data.values() if v is not None and v != ""])
            section_summaries[s[0]] = {
                "is_complete": s[1],
                "fields_filled": field_count,
                "last_updated": s[3].isoformat() if s[3] else None,
            }

        return {
            "application_id": str(app_row[0]),
            "status": app_row[1],
            "current_step": app_row[2],
            "completion_pct": app_row[3],
            "created_at": app_row[4].isoformat() if app_row[4] else None,
            "sections": section_summaries,
        }
    finally:
        db.close()


@mortgage_tool(
    name="get_loan_status",
    description="Pull real-time loan milestones: stage, appraisal status, title status, closing date, conditions",
    agent_roles=["borrower_application_agent"],
)
def get_loan_status(loan_id: int, organization_id: int) -> Dict[str, Any]:
    db = get_db()
    try:
        row = execute_single(
            db,
            "SELECT id, stage, loan_type, loan_amount, purchase_price, "
            "property_address, closing_date, appraisal_ordered_date, "
            "appraisal_received_date, appraisal_value, "
            "title_ordered_date, title_received_date, title_company, "
            "updated_at "
            "FROM loans WHERE id = :loan_id AND organization_id = :org_id",
            {"loan_id": loan_id, "org_id": organization_id},
        )
        if not row:
            return {"error": "Loan not found"}

        conditions = {}
        try:
            cond_rows = execute_query(
                db,
                "SELECT status, COUNT(*) FROM loan_conditions "
                "WHERE loan_id = :loan_id GROUP BY status",
                {"loan_id": loan_id},
            )
            conditions = {r[0]: r[1] for r in cond_rows} if cond_rows else {}
        except Exception as e:
            logger.warning("loan_conditions query fallback: %s", e)

        return {
            "loan_id": row[0],
            "stage": row[1],
            "loan_type": row[2],
            "loan_amount": float(row[3]) if row[3] else None,
            "purchase_price": float(row[4]) if row[4] else None,
            "property_address": row[5],
            "closing_date": row[6].isoformat() if row[6] else None,
            "appraisal": {
                "ordered_date": row[7].isoformat() if row[7] else None,
                "received_date": row[8].isoformat() if row[8] else None,
                "value": float(row[9]) if row[9] else None,
            },
            "title": {
                "ordered_date": row[10].isoformat() if row[10] else None,
                "received_date": row[11].isoformat() if row[11] else None,
                "company": row[12],
            },
            "conditions": conditions,
        }
    finally:
        db.close()


@mortgage_tool(
    name="get_lo_availability",
    description="Fetch 3-5 available calendar slots for the assigned LO",
    agent_roles=["borrower_application_agent"],
)
async def get_lo_availability(
    lo_user_id: int,
    organization_id: int,
    duration_minutes: int = 30,
    days_ahead: int = 5,
) -> Dict[str, Any]:
    try:
        from services.appointment.service import AppointmentService
        from db import SessionLocal
        from datetime import date as date_type

        start = date_type.today()
        end = start + timedelta(days=days_ahead)

        db = SessionLocal()
        try:
            svc = AppointmentService(db=db, organization_id=organization_id)
            slots_raw = await svc.get_available_slots(
                lo_id=lo_user_id,
                start_date=start,
                end_date=end,
                duration_minutes=duration_minutes,
            )
            slots = []
            for slot in (slots_raw or [])[:5]:
                slots.append({
                    "start": str(slot.get("start", "")),
                    "end": str(slot.get("end", "")),
                    "date": str(slot.get("date", "")),
                    "day": slot.get("day", ""),
                })
            return {
                "lo_user_id": lo_user_id,
                "available_slots": slots,
                "slot_count": len(slots),
                "duration_minutes": duration_minutes,
            }
        finally:
            db.close()
    except Exception as e:
        logger.error("get_lo_availability failed: %s", e)
        return {"error": str(e), "available_slots": []}


@mortgage_tool(
    name="book_lo_meeting",
    description="Book a meeting with the assigned LO at a specific time slot",
    agent_roles=["borrower_application_agent"],
)
async def book_lo_meeting(
    lo_user_id: int,
    organization_id: int,
    slot_start: str,
    borrower_name: str,
    borrower_email: str = "",
    borrower_phone: str = "",
    duration_minutes: int = 30,
    topic: str = "Application review",
) -> Dict[str, Any]:
    try:
        from services.appointment.service import AppointmentService
        from services.event_bus import event_bus, Event, EventType
        from db import SessionLocal
        from dateutil import parser as dtparser

        scheduled_start = dtparser.parse(slot_start)
        db = SessionLocal()
        try:
            svc = AppointmentService(db=db, organization_id=organization_id)
            result = await svc.create_appointment(
                data={
                    "title": f"Application Review — {borrower_name}",
                    "scheduled_start": scheduled_start.isoformat(),
                    "duration_minutes": duration_minutes,
                    "assigned_user_id": lo_user_id,
                    "attendee_email": borrower_email,
                    "attendee_name": borrower_name,
                    "attendee_phone": borrower_phone,
                    "meeting_type": "consultation",
                    "meeting_mode": "phone",
                    "description": topic,
                },
                source="borrower_application_agent",
                requester_user_id=lo_user_id,
            )
            db.commit()

            appointment_id = (
                getattr(result, "appointment_id", None)
                or (result.get("appointment_id") if isinstance(result, dict) else None)
            )

            await event_bus.publish(Event(
                type=EventType.MEETING_BOOKED,
                data={
                    "appointment_id": appointment_id,
                    "lo_user_id": lo_user_id,
                    "borrower_name": borrower_name,
                    "borrower_email": borrower_email,
                    "scheduled_start": slot_start,
                    "topic": topic,
                },
                org_id=str(organization_id),
                source="borrower_application_agent",
            ))

            return {
                "booked": True,
                "appointment_id": appointment_id,
                "scheduled_start": slot_start,
                "duration_minutes": duration_minutes,
                "borrower_name": borrower_name,
            }
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        logger.error("book_lo_meeting failed: %s", e)
        return {"booked": False, "error": str(e)}


@mortgage_tool(
    name="propose_alternate_window",
    description="Widen the calendar search window if borrower wants different times",
    agent_roles=["borrower_application_agent"],
)
async def propose_alternate_window(
    lo_user_id: int,
    organization_id: int,
    start_date: str,
    end_date: str,
    duration_minutes: int = 30,
) -> Dict[str, Any]:
    try:
        from services.appointment.service import AppointmentService
        from db import SessionLocal
        from dateutil import parser as dtparser

        start = dtparser.parse(start_date).date()
        end = dtparser.parse(end_date).date()

        db = SessionLocal()
        try:
            svc = AppointmentService(db=db, organization_id=organization_id)
            slots_raw = await svc.get_available_slots(
                lo_id=lo_user_id,
                start_date=start,
                end_date=end,
                duration_minutes=duration_minutes,
            )
            slots = []
            for slot in (slots_raw or [])[:5]:
                slots.append({
                    "start": str(slot.get("start", "")),
                    "end": str(slot.get("end", "")),
                    "date": str(slot.get("date", "")),
                    "day": slot.get("day", ""),
                })
            return {"available_slots": slots, "slot_count": len(slots)}
        finally:
            db.close()
    except Exception as e:
        logger.error("propose_alternate_window failed: %s", e)
        return {"error": str(e), "available_slots": []}


@mortgage_tool(
    name="prompt_document_upload",
    description="Return a structured prompt directing the borrower to upload a specific document type",
    agent_roles=["borrower_application_agent"],
)
def prompt_document_upload(
    document_type: str,
    reason: str,
    application_id: str,
) -> Dict[str, Any]:
    doc_labels = {
        "pay_stubs": "Recent Pay Stubs (last 30 days)",
        "w2": "W-2 Forms (last 2 years)",
        "tax_returns": "Federal Tax Returns (last 2 years)",
        "bank_statements": "Bank Statements (last 2 months)",
        "gift_letter": "Gift Letter",
        "lease_agreement": "Lease Agreement(s)",
        "divorce_decree": "Divorce Decree / Property Settlement",
        "government_id": "Government-Issued Photo ID",
        "profit_loss": "Year-to-Date Profit & Loss Statement",
        "business_license": "Business License",
        "award_letter": "Pension/Social Security Award Letter",
    }
    label = doc_labels.get(document_type, document_type.replace("_", " ").title())

    return {
        "action": "prompt_upload",
        "document_type": document_type,
        "label": label,
        "reason": reason,
        "upload_url": f"/portal/documents/upload?app={application_id}&type={document_type}",
    }


@mortgage_tool(
    name="emit_crm_event",
    description="Publish APPLICATION_ESCALATION, DOCUMENT_SUGGESTED, or APPLICATION_STALL events to the CRM event bus",
    agent_roles=["borrower_application_agent"],
)
async def emit_crm_event(
    event_type: str,
    organization_id: int,
    application_id: str,
    contact_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    from services.event_bus import event_bus, Event, EventType

    type_map = {
        "APPLICATION_ESCALATION": EventType.APPLICATION_ESCALATION,
        "DOCUMENT_SUGGESTED": EventType.DOCUMENT_SUGGESTED,
        "APPLICATION_STALL": EventType.APPLICATION_STALL,
    }
    resolved_type = type_map.get(event_type)
    if not resolved_type:
        return {"error": f"Unknown event type: {event_type}"}

    await event_bus.publish(Event(
        type=resolved_type,
        data={
            "application_id": application_id,
            "contact_id": contact_id,
            **data,
        },
        org_id=str(organization_id),
        source="borrower_application_agent",
    ))

    return {"published": True, "event_type": event_type}


@mortgage_tool(
    name="recall_borrower_context",
    description="Query prior conversation history and borrower profile for cross-session continuity",
    agent_roles=["borrower_application_agent"],
)
def recall_borrower_context(
    application_id: str,
    organization_id: int,
    limit: int = 10,
) -> Dict[str, Any]:
    db = get_db()
    try:
        messages = execute_query(
            db,
            "SELECT role, content, confidence, created_at "
            "FROM pos_ai_qa_messages WHERE application_id = :app_id "
            "ORDER BY created_at DESC LIMIT :lim",
            {"app_id": application_id, "lim": limit},
        )
        history = []
        for m in reversed(messages or []):
            history.append({
                "role": m[0],
                "content": m[1][:500],
                "confidence": m[2],
                "created_at": m[3].isoformat() if m[3] else None,
            })
        return {"message_count": len(history), "history": history}
    finally:
        db.close()
