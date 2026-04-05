"""
Calendar-Pipeline Bridge

Connects the Smart Calendar and loan pipeline into a unified workflow:

1. Appointment COMPLETED + APPLICATION_WALKTHROUGH → auto-create Loan from Lead
2. Loan hits CONDITIONAL_APPROVAL → auto-suggest CLOSING_PREP appointment

This makes the calendar a genuine workflow hub, not just a scheduling tool.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def on_appointment_completed(db: Session, appointment) -> dict:
    """
    Called after an appointment status transitions to COMPLETED.
    If the meeting type is APPLICATION_WALKTHROUGH and the appointment
    has a lead but no loan, auto-create a Loan record.

    Returns dict with action taken (or reason skipped).
    """
    from database.models.scheduler import MeetingType

    meeting_type = appointment.meeting_type

    # Only trigger on application-related meeting types
    application_types = {
        MeetingType.APPLICATION_WALKTHROUGH,
        MeetingType.PRE_APPROVAL_REVIEW,
    }

    if meeting_type not in application_types:
        return {"action": "skipped", "reason": f"meeting_type {meeting_type} not application-related"}

    if not appointment.lead_id:
        return {"action": "skipped", "reason": "no lead_id on appointment"}

    if appointment.loan_id:
        return {"action": "skipped", "reason": f"loan already linked (loan_id={appointment.loan_id})"}

    # Check if this lead already has a loan (via loan_number link)
    existing_loan = db.execute(text("""
        SELECT l.id FROM loans l
        JOIN leads ld ON ld.loan_number = l.loan_number
            AND ld.loan_number IS NOT NULL AND ld.loan_number != ''
        WHERE ld.id = :lead_id
        LIMIT 1
    """), {"lead_id": appointment.lead_id}).fetchone()

    if existing_loan:
        # Link the appointment to the existing loan
        appointment.loan_id = existing_loan[0]
        return {"action": "linked", "loan_id": existing_loan[0], "reason": "lead already had a loan"}

    # Fetch lead data to populate the new loan
    lead = db.execute(text("""
        SELECT id, first_name, last_name, email, phone,
               loan_amount, loan_type, loan_purpose,
               property_type, address, city, state, zip_code,
               property_value, down_payment, credit_score,
               owner_id, organization_id
        FROM leads
        WHERE id = :lead_id
    """), {"lead_id": appointment.lead_id}).fetchone()

    if not lead:
        return {"action": "skipped", "reason": f"lead {appointment.lead_id} not found"}

    # Build loan data from lead
    lead_id = lead[0]
    borrower_name = f"{lead[1] or ''} {lead[2] or ''}".strip() or "Unknown Borrower"
    borrower_email = lead[3]
    borrower_phone = lead[4]
    loan_amount = float(lead[5] or 0)
    loan_type = lead[6] or "Conventional"
    loan_purpose = lead[7]
    property_type = lead[8]
    property_address_parts = [p for p in [lead[9], lead[10], lead[11], lead[12]] if p]
    property_address = ", ".join(property_address_parts) if property_address_parts else None
    purchase_price = float(lead[13] or 0) or loan_amount
    down_payment = float(lead[14] or 0)
    owner_id = lead[16]
    organization_id = lead[17]

    # Use the appointment's assigned LO if available, otherwise the lead's owner
    loan_officer_id = appointment.assigned_user_id or owner_id

    # Ensure we have an org (fall back to appointment org)
    if not organization_id:
        organization_id = appointment.organization_id

    loan_number = f"APP-{str(lead_id).zfill(6)}"

    # Check for duplicate loan_number
    dup = db.execute(text(
        "SELECT id FROM loans WHERE loan_number = :ln"
    ), {"ln": loan_number}).fetchone()

    if dup:
        # Loan already exists for this lead — link it
        appointment.loan_id = dup[0]
        return {"action": "linked", "loan_id": dup[0], "reason": "loan_number already exists"}

    now = datetime.now(timezone.utc)

    result = db.execute(text("""
        INSERT INTO loans (
            loan_number, borrower_name, borrower_email, borrower_phone,
            stage, program, loan_type, loan_purpose, amount,
            purchase_price, down_payment, term,
            property_address, property_type,
            loan_officer_id, organization_id,
            application_date, stage_changed_at,
            days_in_stage, sla_status,
            created_at, updated_at
        )
        VALUES (
            :loan_number, :borrower_name, :borrower_email, :borrower_phone,
            'APPLICATION', :program, :loan_type, :loan_purpose, :amount,
            :purchase_price, :down_payment, 360,
            :property_address, :property_type,
            :loan_officer_id, :organization_id,
            :now, :now,
            0, 'on-track',
            :now, :now
        )
        RETURNING id
    """), {
        "loan_number": loan_number,
        "borrower_name": borrower_name,
        "borrower_email": borrower_email,
        "borrower_phone": borrower_phone,
        "program": loan_type,
        "loan_type": loan_type,
        "loan_purpose": loan_purpose,
        "amount": loan_amount if loan_amount > 0 else 0,
        "purchase_price": purchase_price if purchase_price > 0 else None,
        "down_payment": down_payment if down_payment > 0 else None,
        "property_address": property_address,
        "property_type": property_type,
        "loan_officer_id": loan_officer_id,
        "organization_id": organization_id,
        "now": now,
    })

    loan_row = result.fetchone()
    loan_id = loan_row[0] if loan_row else None

    if loan_id:
        # Link the appointment to the new loan
        appointment.loan_id = loan_id

        # Update lead: set loan_number and advance stage
        db.execute(text("""
            UPDATE leads
            SET loan_number = :loan_number,
                stage = 'Application',
                stage_changed_at = :now,
                updated_at = :now
            WHERE id = :lead_id
        """), {"loan_number": loan_number, "now": now, "lead_id": lead_id})

        # Log the bridge action as an activity
        db.execute(text("""
            INSERT INTO activities (lead_id, type, content, created_at, organization_id)
            VALUES (:lead_id, 'System', :content, :now, :org_id)
        """), {
            "lead_id": lead_id,
            "content": f"Loan {loan_number} auto-created from completed {appointment.meeting_type.value} appointment",
            "now": now,
            "org_id": organization_id,
        })

        logger.info(
            f"Calendar-Pipeline Bridge: Created loan {loan_id} ({loan_number}) "
            f"from appointment {appointment.id} for lead {lead_id}"
        )

    return {
        "action": "created",
        "loan_id": loan_id,
        "loan_number": loan_number,
        "lead_id": lead_id,
    }


def on_loan_stage_change(db: Session, loan_id: int, new_stage: str, organization_id: int) -> dict:
    """
    Called when a loan's stage changes.
    When stage hits CONDITIONAL_APPROVAL, auto-suggest a CLOSING_PREP appointment
    by creating a task for the LO.

    Returns dict with action taken (or reason skipped).
    """
    if new_stage != "CONDITIONAL_APPROVAL":
        return {"action": "skipped", "reason": f"stage {new_stage} does not trigger bridge"}

    loan = db.execute(text("""
        SELECT id, loan_number, borrower_name, borrower_email, borrower_phone,
               loan_officer_id, closing_date, property_address
        FROM loans
        WHERE id = :loan_id AND organization_id = :org_id
    """), {"loan_id": loan_id, "org_id": organization_id}).fetchone()

    if not loan:
        return {"action": "skipped", "reason": f"loan {loan_id} not found"}

    lo_id = loan[5]
    if not lo_id:
        return {"action": "skipped", "reason": "no loan officer assigned"}

    # Check if we already suggested a closing appointment recently
    existing = db.execute(text("""
        SELECT id FROM tasks
        WHERE loan_id = :loan_id
          AND title LIKE '%closing prep appointment%'
          AND created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
        LIMIT 1
    """), {"loan_id": str(loan_id)}).fetchone()

    if existing:
        return {"action": "skipped", "reason": "closing prep task already exists"}

    now = datetime.now(timezone.utc)
    closing_date = loan[6]
    property_address = loan[7] or "TBD"

    # Suggest scheduling 5-7 days before closing if closing date is set
    if closing_date:
        suggested_date = closing_date - timedelta(days=7)
        date_note = f"Suggested: {suggested_date.strftime('%m/%d/%Y')} (7 days before closing {closing_date.strftime('%m/%d/%Y')})"
    else:
        date_note = "Closing date not yet set — schedule once available"

    db.execute(text("""
        INSERT INTO tasks (
            title, description, assigned_to_id, loan_id,
            priority, status, due_date, created_at, organization_id
        )
        VALUES (
            :title, :desc, :lo_id, :loan_id,
            'high', 'pending', :due_date, :now, :org_id
        )
    """), {
        "title": f"Schedule closing prep appointment — {loan[2]}",
        "desc": (
            f"Loan {loan[1]} ({loan[2]}) received conditional approval. "
            f"Property: {property_address}. "
            f"Schedule a CLOSING_PREP appointment to review conditions, "
            f"closing disclosure, and required documents. {date_note}"
        ),
        "lo_id": str(lo_id),
        "loan_id": str(loan_id),
        "due_date": closing_date - timedelta(days=10) if closing_date else now + timedelta(days=3),
        "now": now,
        "org_id": organization_id,
    })

    logger.info(
        f"Calendar-Pipeline Bridge: Suggested closing prep appointment "
        f"for loan {loan_id} ({loan[1]}) — conditional approval reached"
    )

    return {
        "action": "task_created",
        "loan_id": loan_id,
        "loan_number": loan[1],
        "message": f"Closing prep appointment suggested for {loan[2]}",
    }
