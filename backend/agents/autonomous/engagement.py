"""
Engagement Agents

Real-time and frequent engagement-focused autonomous agents:
1. speed_to_lead — Every 2 min, ensure new leads contacted within 60s target
2. appointment_prep — Every 15 min, prep materials before appointments
3. borrower_status_updater — Hourly, proactive milestone updates to borrowers
4. referral_thank_you — Hourly, thank referral partners for new leads
5. drip_campaign_engine — Every 15 min, trigger next drip message in sequences
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytz
from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency
from agents.autonomous.memory_context import get_lo_memory_context, get_org_directives, should_skip_contact

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _now_in_tz(tz_name: str) -> datetime:
    """Return the current wall-clock time in the given timezone."""
    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone("America/New_York")
    return datetime.now(tz)


def _is_business_hours(tz_name: str, start_hour: int = 8, end_hour: int = 21) -> bool:
    """True if the current local time is between start_hour and end_hour."""
    now = _now_in_tz(tz_name)
    return start_hour <= now.hour < end_hour


def _insert_task(
    db: Session,
    *,
    title: str,
    description: str,
    assigned_to_id: Optional[str],
    lead_id: Optional[str] = None,
    loan_id: Optional[str] = None,
    priority: str = "medium",
    status: str = "pending",
    due_date_expr: str = "CURRENT_DATE",
    organization_id: int,
    gateway=None,
) -> None:
    """Insert a task row with standard columns."""
    params = {
        "title": title[:500],
        "desc": description[:4000],
        "assigned_to_id": assigned_to_id,
        "lead_id": lead_id,
        "loan_id": loan_id,
        "priority": priority,
        "status": status,
        "org_id": organization_id,
    }
    def _do():
        db.execute(text(f"""
            INSERT INTO tasks (title, description, assigned_to_id, lead_id, loan_id,
                               priority, status, due_date, created_at, organization_id)
            VALUES (:title, :desc, :assigned_to_id, :lead_id, :loan_id,
                    :priority, :status, {due_date_expr}, CURRENT_TIMESTAMP, :org_id)
        """), params)
    if gateway:
        gateway.propose(
            "create_task", _do,
            target_entity="lead" if lead_id else ("loan" if loan_id else None),
            target_id=lead_id or loan_id,
            description=title[:200],
            payload=params,
        )
    else:
        _do()


def _insert_activity(
    db: Session,
    *,
    lead_id: Optional[str],
    activity_type: str,
    content: str,
    organization_id: int,
    gateway=None,
) -> None:
    """Insert an activity log entry."""
    params = {
        "lead_id": lead_id,
        "type": activity_type,
        "content": content[:4000],
        "org_id": organization_id,
    }
    def _do():
        db.execute(text("""
            INSERT INTO activities (lead_id, type, content, created_at, organization_id)
            VALUES (:lead_id, :type, :content, CURRENT_TIMESTAMP, :org_id)
        """), params)
    if gateway:
        gateway.propose(
            "create_activity", _do,
            target_entity="lead" if lead_id else None,
            target_id=lead_id,
            description=content[:200],
            payload=params,
        )
    else:
        _do()


# ---------------------------------------------------------------------------
# 1. Speed-to-Lead Enforcer
# ---------------------------------------------------------------------------

_URGENCY_LABELS = {
    "hot": "HOT — Has phone, email, and loan amount. High-intent buyer.",
    "warm": "WARM — Has phone or email but incomplete profile.",
    "cold": "COLD — Minimal contact info. Needs enrichment before outreach.",
}


def _score_lead_urgency(phone: Optional[str], email: Optional[str], loan_amount: Any) -> str:
    """Classify a lead as hot / warm / cold based on available data."""
    has_phone = bool(phone and phone.strip())
    has_email = bool(email and email.strip())
    has_loan_amount = loan_amount is not None and float(loan_amount or 0) > 0
    if has_phone and has_email and has_loan_amount:
        return "hot"
    if has_phone or has_email:
        return "warm"
    return "cold"


def _pick_round_robin_lo(db: Session, organization_id: int) -> Optional[Tuple[int, str]]:
    """Select the active LO with the fewest open leads for round-robin assignment.

    Returns (user_id, first_name) or None.
    """
    row = db.execute(text("""
        SELECT u.id, u.first_name
        FROM users u
        LEFT JOIN (
            SELECT owner_id, COUNT(*) AS cnt
            FROM leads
            WHERE organization_id = :org_id
              AND stage NOT IN ('Funded','Dead','Cancelled','Denied','Withdrawn','Does Not Qualify')
            GROUP BY owner_id
        ) lc ON lc.owner_id = u.id
        WHERE u.organization_id = :org_id
          AND u.is_active = true
          AND u.role IN ('loan_officer', 'manager', 'branch_manager')
        ORDER BY COALESCE(lc.cnt, 0), u.id
        LIMIT 1
    """), {"org_id": organization_id}).fetchone()
    if row:
        return (row[0], row[1])
    return None


@autonomous_agent(
    name="speed_to_lead",
    description="Ensure new leads get first contact attempt within 60 seconds",
    frequency=AgentFrequency.EVERY_2_MIN,
    max_runtime_seconds=30,
)
def speed_to_lead(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Find leads created in last 5 min with no outreach and create channel-specific tasks.

    Logic:
    - Score urgency (hot/warm/cold) based on available contact data
    - Auto-assign unowned leads via round-robin by pipeline load
    - Create separate tasks per channel (call, SMS, email) when info is available
    - Skip task creation outside business hours (8 AM - 9 PM org tz) but still log activity
    - Record response-time metrics and a Speed-to-Lead Alert activity
    """
    actions = 0
    notifications = 0
    outside_hours = not _is_business_hours(org_timezone)

    untouched = db.execute(text("""
        SELECT l.id, l.first_name, l.last_name, l.phone, l.email,
               l.owner_id, l.source, l.loan_amount, l.created_at
        FROM leads l
        WHERE l.organization_id = :org_id
          AND l.created_at > CURRENT_TIMESTAMP - INTERVAL '5 minutes'
          AND l.last_contact IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM tasks t
              WHERE t.lead_id = l.id
                AND t.title LIKE 'Speed-to-lead%'
                AND t.created_at > CURRENT_TIMESTAMP - INTERVAL '10 minutes'
          )
          AND NOT EXISTS (
              SELECT 1 FROM activities a
              WHERE a.lead_id = l.id
                AND a.type IN ('Call', 'SMS', 'Email')
          )
        ORDER BY l.created_at
    """), {"org_id": organization_id}).fetchall()

    # Cache the round-robin LO pick for this run (avoids repeated queries)
    rr_lo: Optional[Tuple[int, str]] = None
    rr_resolved = False

    for lead in untouched:
        lead_id = str(lead[0])
        first_name = lead[1] or "Lead"
        last_name = lead[2] or ""
        phone = lead[3]
        email = lead[4]
        owner_id = lead[5]
        source = lead[6] or "unknown source"
        loan_amount = lead[7]
        created_at = lead[8]

        # Load LO memory for channel preferences
        lo_memory = get_lo_memory_context(db, owner_id, organization_id) if owner_id else {}

        urgency = _score_lead_urgency(phone, email, loan_amount)
        urgency_label = _URGENCY_LABELS[urgency]
        priority = "critical" if urgency == "hot" else ("high" if urgency == "warm" else "medium")

        # Calculate response-time metric
        if created_at:
            elapsed = datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else datetime.now(timezone.utc) - created_at
            elapsed_min = round(elapsed.total_seconds() / 60, 1)
        else:
            elapsed_min = 0

        # Auto-assign if unowned
        assigned_id = str(owner_id) if owner_id else None
        assigned_note = ""
        if not assigned_id:
            if not rr_resolved:
                rr_lo = _pick_round_robin_lo(db, organization_id)
                rr_resolved = True
            if rr_lo:
                assigned_id = str(rr_lo[0])
                assigned_note = f" (auto-assigned to {rr_lo[1]} via round-robin)"
                # Update the lead's owner_id
                db.execute(text("""
                    UPDATE leads SET owner_id = :lo_id, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :lead_id AND organization_id = :org_id
                """), {"lo_id": rr_lo[0], "lead_id": lead_id, "org_id": organization_id})

        # Log activity regardless of business hours
        _insert_activity(
            db,
            lead_id=lead_id,
            activity_type="System",
            content=(
                f"Speed-to-Lead Alert | {urgency.upper()} | {elapsed_min} min since creation | "
                f"Source: {source}{assigned_note}"
            ),
            organization_id=organization_id,
            gateway=gateway,
        )

        # Outside business hours: log activity but defer contact tasks
        if outside_hours:
            _insert_task(
                db,
                title=f"Speed-to-lead: Contact {first_name} {last_name} at start of business",
                description=(
                    f"New {urgency.upper()} lead from {source}.{assigned_note}\n"
                    f"{urgency_label}\n"
                    f"Response time so far: {elapsed_min} min (arrived outside business hours).\n"
                    f"Phone: {phone or 'N/A'} | Email: {email or 'N/A'} | "
                    f"Loan amount: ${float(loan_amount):,.0f}" if loan_amount else
                    f"New {urgency.upper()} lead from {source}.{assigned_note}\n"
                    f"{urgency_label}\n"
                    f"Response time so far: {elapsed_min} min (arrived outside business hours).\n"
                    f"Phone: {phone or 'N/A'} | Email: {email or 'N/A'} | Loan amount: N/A"
                ),
                assigned_to_id=assigned_id,
                lead_id=lead_id,
                priority=priority,
                due_date_expr="CURRENT_DATE + 1",
                organization_id=organization_id,
                gateway=gateway,
            )
            actions += 1
            continue

        # Business hours: create channel-specific tasks
        base_desc = (
            f"{urgency_label}\n"
            f"Source: {source}{assigned_note}\n"
            f"Response time: {elapsed_min} min since lead arrived.\n"
            f"Loan amount: {'${:,.0f}'.format(float(loan_amount)) if loan_amount else 'N/A'}"
        )

        if phone and phone.strip() and not should_skip_contact(lo_memory, "call"):
            _insert_task(
                db,
                title=f"Speed-to-lead: Call {first_name} {last_name} NOW",
                description=f"CALL {phone} immediately.\n{base_desc}",
                assigned_to_id=assigned_id,
                lead_id=lead_id,
                priority=priority,
                organization_id=organization_id,
                gateway=gateway,
            )
            actions += 1

        if phone and phone.strip() and not should_skip_contact(lo_memory, "sms"):
            _insert_task(
                db,
                title=f"Speed-to-lead: Text {first_name} {last_name}",
                description=(
                    f"Send intro SMS to {phone}.\n"
                    f"Suggested: 'Hi {first_name}, this is [Name] with [Company]. "
                    f"I received your inquiry and would love to help. When is a good time to chat?'\n"
                    f"{base_desc}"
                ),
                assigned_to_id=assigned_id,
                lead_id=lead_id,
                priority="high" if urgency == "hot" else "medium",
                organization_id=organization_id,
                gateway=gateway,
            )
            actions += 1

        if email and email.strip() and not should_skip_contact(lo_memory, "email"):
            _insert_task(
                db,
                title=f"Speed-to-lead: Email {first_name} {last_name}",
                description=(
                    f"Send intro email to {email}.\n"
                    f"Include: personal greeting, next steps, your direct line.\n"
                    f"{base_desc}"
                ),
                assigned_to_id=assigned_id,
                lead_id=lead_id,
                priority="high" if urgency == "hot" else "medium",
                organization_id=organization_id,
                gateway=gateway,
            )
            actions += 1

        # Fallback if no contact info at all
        if not (phone and phone.strip()) and not (email and email.strip()):
            _insert_task(
                db,
                title=f"Speed-to-lead: Enrich contact info for {first_name} {last_name}",
                description=(
                    f"No phone or email on file. Research and add contact info ASAP.\n"
                    f"{base_desc}"
                ),
                assigned_to_id=assigned_id,
                lead_id=lead_id,
                priority="high",
                organization_id=organization_id,
                gateway=gateway,
            )
            actions += 1

        notifications += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Speed-to-lead commit failed: {e}")

    qualifier = " (after-hours deferrals)" if outside_hours else ""
    return {
        "summary": f"{actions} speed-to-lead tasks for {len(untouched)} leads{qualifier}",
        "actions_taken": actions,
        "notifications_sent": notifications,
    }


# ---------------------------------------------------------------------------
# 2. Appointment Prep Agent
# ---------------------------------------------------------------------------

# Documents commonly needed per appointment type
_DOCS_BY_APPOINTMENT_TYPE = {
    "initial_consultation": [
        "Photo ID", "Most recent pay stubs (30 days)", "W-2s (2 years)",
        "Bank statements (2 months)", "Tax returns (2 years, if self-employed)",
    ],
    "pre_approval": [
        "Credit authorization form", "Income documentation", "Asset statements",
        "Gift letter (if applicable)",
    ],
    "application": [
        "Signed 1003 application", "Purchase contract", "Earnest money receipt",
        "Homeowners insurance quote",
    ],
    "closing": [
        "Photo ID (must match closing docs)", "Cashier's check / wire confirmation",
        "Proof of homeowners insurance", "Final walkthrough confirmation",
    ],
}

# Fallback for unrecognized types
_DEFAULT_DOCS = ["Loan file", "Most recent credit report", "Rate lock confirmation"]


@autonomous_agent(
    name="appointment_prep",
    description="Send prep materials 2 hours before appointments",
    frequency=AgentFrequency.EVERY_15_MIN,
    max_runtime_seconds=60,
)
def appointment_prep(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Create detailed prep tasks for appointments starting in the next 2 hours.

    Includes:
    - Lead financial snapshot (loan amount, credit score, loan purpose)
    - Existing loan pipeline status
    - Document checklist based on appointment type
    - Recent activities for conversation context
    - Borrower-facing prep reminder (what they should bring)
    """
    actions = 0

    upcoming = db.execute(text("""
        SELECT sa.id, sa.title, sa.scheduled_start, sa.assigned_user_id, sa.lead_id,
               sa.meeting_type AS appointment_type, sa.meeting_type,
               l.first_name, l.last_name, l.email, l.phone,
               l.loan_amount, l.credit_score, l.loan_purpose, l.stage AS lead_stage
        FROM scheduler_appointments sa
        LEFT JOIN leads l ON l.id = sa.lead_id
        WHERE sa.organization_id = :org_id
          AND sa.scheduled_start BETWEEN CURRENT_TIMESTAMP + INTERVAL '90 minutes'
                                AND CURRENT_TIMESTAMP + INTERVAL '2 hours 15 minutes'
          AND sa.status NOT IN ('cancelled', 'no_show', 'completed')
    """), {"org_id": organization_id}).fetchall()

    for appt in upcoming:
        appt_id = appt[0]
        appt_title = appt[1] or "Meeting"
        start_time = appt[2]
        lo_user_id = appt[3]
        lead_id = appt[4]
        appt_type = (appt[5] or "").lower().strip()
        meeting_type = appt[6] or "in_person"
        first_name = appt[7] or ""
        last_name = appt[8] or ""
        lead_email = appt[9]
        lead_phone = appt[10]
        loan_amount = appt[11]
        credit_score = appt[12]
        loan_purpose = appt[13]
        lead_stage = appt[14]
        lead_name = f"{first_name} {last_name}".strip() or "borrower"

        # Dedup: skip if prep task already exists for this appointment
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE title LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '3 hours'
            LIMIT 1
        """), {"pattern": f"%Prep for appt #{appt_id}%"}).fetchone()
        if existing:
            continue

        # --- Gather enrichment data ---

        # Existing loans for this lead
        loan_info_lines: List[str] = []
        if lead_id:
            loans = db.execute(text("""
                SELECT loan_number, stage, amount, rate, loan_type, closing_date
                FROM loans
                WHERE organization_id = :org_id
                  AND (borrower_email = :email OR borrower_name ILIKE :name_pattern)
                ORDER BY created_at DESC
                LIMIT 5
            """), {
                "org_id": organization_id,
                "email": lead_email or "",
                "name_pattern": f"%{first_name}%{last_name}%" if first_name else "%%",
            }).fetchall()
            for ln in loans:
                amt_str = f"${float(ln[2]):,.0f}" if ln[2] else "N/A"
                rate_str = f"{float(ln[3]):.3f}%" if ln[3] else "N/A"
                close_str = str(ln[5]) if ln[5] else "TBD"
                loan_info_lines.append(
                    f"  - #{ln[0] or '?'}: {ln[1]} | {amt_str} | {rate_str} | {ln[4] or 'N/A'} | Close: {close_str}"
                )

        loans_section = "\n".join(loan_info_lines) if loan_info_lines else "  No existing loans on file."

        # Recent activities (last 5)
        activity_lines: List[str] = []
        if lead_id:
            activities = db.execute(text("""
                SELECT type, content, created_at
                FROM activities
                WHERE lead_id = :lead_id AND organization_id = :org_id
                ORDER BY created_at DESC
                LIMIT 5
            """), {"lead_id": str(lead_id), "org_id": organization_id}).fetchall()
            for act in activities:
                date_str = str(act[2])[:16] if act[2] else "?"
                snippet = (act[1] or "")[:120]
                activity_lines.append(f"  - [{date_str}] {act[0]}: {snippet}")

        activities_section = "\n".join(activity_lines) if activity_lines else "  No recent activities."

        # Document checklist
        doc_list = _DOCS_BY_APPOINTMENT_TYPE.get(appt_type, _DEFAULT_DOCS)
        docs_section = "\n".join(f"  [ ] {d}" for d in doc_list)

        # Financial snapshot
        fin_lines = []
        if loan_amount:
            fin_lines.append(f"Loan amount: ${float(loan_amount):,.0f}")
        if credit_score:
            fin_lines.append(f"Credit score: {credit_score}")
        if loan_purpose:
            fin_lines.append(f"Purpose: {loan_purpose}")
        if lead_stage:
            fin_lines.append(f"Lead stage: {lead_stage}")
        financial_section = " | ".join(fin_lines) if fin_lines else "No financial data on file."

        # --- LO prep task ---
        lo_desc = (
            f"Appointment: {appt_title} at {start_time} ({meeting_type})\n"
            f"Borrower: {lead_name} | {lead_email or 'no email'} | {lead_phone or 'no phone'}\n\n"
            f"FINANCIAL SNAPSHOT\n{financial_section}\n\n"
            f"LOAN HISTORY\n{loans_section}\n\n"
            f"DOCUMENT CHECKLIST ({appt_type or 'general'})\n{docs_section}\n\n"
            f"RECENT ACTIVITY (conversation context)\n{activities_section}"
        )

        _insert_task(
            db,
            title=f"Prep for appt #{appt_id} with {lead_name}",
            description=lo_desc,
            assigned_to_id=str(lo_user_id),
            lead_id=str(lead_id) if lead_id else None,
            priority="high",
            organization_id=organization_id,
            gateway=gateway,
        )
        actions += 1

        # --- Borrower-facing prep reminder task ---
        if lead_id:
            borrower_docs = _DOCS_BY_APPOINTMENT_TYPE.get(appt_type, _DEFAULT_DOCS)
            borrower_doc_list = "\n".join(f"  - {d}" for d in borrower_docs)
            borrower_desc = (
                f"Remind {lead_name} about their upcoming {appt_type or 'appointment'} "
                f"at {start_time}.\n\n"
                f"WHAT TO BRING / HAVE READY:\n{borrower_doc_list}\n\n"
                f"Contact: {lead_email or 'N/A'} | {lead_phone or 'N/A'}\n"
                f"Meeting type: {meeting_type}"
            )
            _insert_task(
                db,
                title=f"Send prep reminder to {lead_name} for appt #{appt_id}",
                description=borrower_desc,
                assigned_to_id=str(lo_user_id),
                lead_id=str(lead_id),
                priority="medium",
                organization_id=organization_id,
                gateway=gateway,
            )
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Appointment prep commit failed: {e}")

    return {
        "summary": f"{actions} prep tasks created for {len(upcoming)} upcoming appointments",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 3. Borrower Status Updater
# ---------------------------------------------------------------------------

# Borrower-friendly messages and estimated remaining business days per stage
_MILESTONE_CONFIG: Dict[str, Dict[str, Any]] = {
    "DISCLOSED": {
        "message": "Great news — your loan disclosures have been sent! Please review and sign them at your earliest convenience.",
        "est_days_remaining": 35,
    },
    "SUBMITTED": {
        "message": "Your loan file has been submitted to underwriting. Our team is reviewing everything now.",
        "est_days_remaining": 25,
    },
    "UNDERWRITING": {
        "message": "Your loan is actively in underwriting review. We'll keep you posted on any updates.",
        "est_days_remaining": 22,
    },
    "CONDITIONAL_APPROVAL": {
        "message": "Exciting update — your loan has received conditional approval! We may need a few more items to finalize.",
        "est_days_remaining": 15,
    },
    "APPROVED": {
        "message": "Your loan is fully approved! We're now moving toward the closing stage.",
        "est_days_remaining": 10,
    },
    "CTC": {
        "message": "You are Clear to Close! Your closing documents are being prepared.",
        "est_days_remaining": 7,
    },
    "CLEAR_TO_CLOSE": {
        "message": "Clear to Close confirmed. We're scheduling your closing date now.",
        "est_days_remaining": 5,
    },
    "DOCS_OUT": {
        "message": "Closing documents have been sent to the title company. You're almost at the finish line!",
        "est_days_remaining": 3,
    },
    "FUNDED": {
        "message": "Congratulations — your loan has funded! Welcome to your new home.",
        "est_days_remaining": 0,
    },
}


@autonomous_agent(
    name="borrower_status_updater",
    description="Proactive status updates to borrowers on milestone changes",
    frequency=AgentFrequency.HOURLY,
    max_runtime_seconds=60,
)
def borrower_status_updater(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Find loans that hit milestones in the last hour and create notification tasks.

    Enhancements:
    - Maps each stage to a borrower-friendly message template
    - Includes estimated remaining timeline
    - Detects communication preference from lead record (phone vs email)
    - Creates a separate realtor notification task when referral_source exists
    - Logs milestone as an audit-trail activity
    """
    actions = 0
    notifications = 0

    milestone_stages = list(_MILESTONE_CONFIG.keys())

    milestones = db.execute(text("""
        SELECT lo.id, lo.loan_number, lo.borrower_name, lo.borrower_email,
               lo.borrower_phone, lo.loan_officer_id, lo.stage, lo.amount,
               lo.closing_date,
               ld.source AS lead_source, ld.phone AS lead_phone, ld.email AS lead_email,
               ld.id AS lead_id
        FROM loans lo
        LEFT JOIN leads ld ON ld.email = lo.borrower_email
            AND ld.organization_id = lo.organization_id
        WHERE lo.organization_id = :org_id
          AND lo.stage_changed_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
          AND lo.stage = ANY(:stages)
    """), {"org_id": organization_id, "stages": milestone_stages}).fetchall()

    for loan in milestones:
        loan_id = str(loan[0])
        loan_number = loan[1] or "N/A"
        borrower_name = loan[2] or "Borrower"
        borrower_email = loan[3]
        borrower_phone = loan[4]
        lo_id = str(loan[5]) if loan[5] else None
        stage = loan[6]
        amount = loan[7]
        closing_date = loan[8]
        referral_source = loan[9]
        lead_phone = loan[10]
        lead_email = loan[11]
        lead_id = str(loan[12]) if loan[12] else None

        # Dedup check
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id
              AND title LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '4 hours'
            LIMIT 1
        """), {"loan_id": loan_id, "pattern": f"%borrower update%{stage}%"}).fetchone()
        if existing:
            continue

        config = _MILESTONE_CONFIG.get(stage, {})
        friendly_message = config.get("message", f"Your loan status has been updated to {stage}.")
        est_days = config.get("est_days_remaining", "unknown")

        # Determine communication preference from available contact data
        has_phone = bool(borrower_phone or lead_phone)
        has_email = bool(borrower_email or lead_email)
        if has_phone and has_email:
            channel_note = "Borrower has phone AND email — send via preferred channel (email recommended for milestone updates)."
        elif has_email:
            channel_note = "Email only — send status update via email."
        elif has_phone:
            channel_note = "Phone only — call or text the borrower with this update."
        else:
            channel_note = "No contact info on file — check loan file for current contact details."

        contact_email = borrower_email or lead_email or "N/A"
        contact_phone = borrower_phone or lead_phone or "N/A"

        timeline_note = (
            f"Estimated ~{est_days} business days to closing."
            if est_days and est_days != "unknown" and est_days > 0
            else ("Loan is funded — no remaining timeline." if stage == "FUNDED" else "Timeline estimate unavailable.")
        )

        amount_str = f"${float(amount):,.0f}" if amount else "N/A"
        closing_str = str(closing_date) if closing_date else "TBD"

        # --- Borrower notification task ---
        _insert_task(
            db,
            title=f"Send borrower update: {borrower_name} reached {stage}",
            description=(
                f"MILESTONE: {stage}\n"
                f"Loan #{loan_number} | {amount_str} | Closing: {closing_str}\n\n"
                f"SUGGESTED MESSAGE TO BORROWER:\n\"{friendly_message}\"\n\n"
                f"TIMELINE: {timeline_note}\n\n"
                f"CONTACT: {contact_email} | {contact_phone}\n"
                f"{channel_note}"
            ),
            assigned_to_id=lo_id,
            loan_id=loan_id,
            lead_id=lead_id,
            priority="high" if stage in ("FUNDED", "CTC", "CLEAR_TO_CLOSE") else "medium",
            organization_id=organization_id,
            gateway=gateway,
        )
        actions += 1
        notifications += 1

        # --- Realtor / referral partner notification task ---
        if referral_source:
            _insert_task(
                db,
                title=f"Update realtor/partner: {borrower_name} reached {stage}",
                description=(
                    f"Referral source: {referral_source}\n"
                    f"Loan #{loan_number} for {borrower_name} | {amount_str}\n\n"
                    f"STATUS: {stage} — {friendly_message}\n"
                    f"TIMELINE: {timeline_note}\n\n"
                    f"Closing date: {closing_str}\n"
                    f"Keep the referral partner informed to maintain the relationship."
                ),
                assigned_to_id=lo_id,
                loan_id=loan_id,
                lead_id=lead_id,
                priority="medium",
                organization_id=organization_id,
                gateway=gateway,
            )
            actions += 1
            notifications += 1

        # --- Audit-trail activity ---
        if lead_id:
            _insert_activity(
                db,
                lead_id=lead_id,
                activity_type="Milestone",
                content=f"Loan #{loan_number} reached {stage}. {timeline_note}",
                organization_id=organization_id,
                gateway=gateway,
            )

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Borrower status updater commit failed: {e}")

    return {
        "summary": f"{actions} milestone notification tasks ({notifications} notifications) for {len(milestones)} loans",
        "actions_taken": actions,
        "notifications_sent": notifications,
    }


# ---------------------------------------------------------------------------
# 4. Referral Thank-You Agent
# ---------------------------------------------------------------------------

_CO_MARKETING_SUGGESTIONS = {
    1: "First referral! Send a personal thank-you note or small gift. Offer to set up a co-branded pre-approval flyer.",
    2: "Second referral. Propose a joint open-house or client appreciation event.",
    3: "Growing relationship. Suggest a recurring monthly coffee meeting to discuss pipeline.",
    5: "Strong partner. Propose co-marketing budget: joint social media ads or direct mail campaign.",
    10: "Top referral source. Consider a formal referral agreement and co-branded landing page.",
}


def _co_marketing_suggestion(referral_count: int) -> str:
    """Return a co-marketing suggestion based on referral volume."""
    for threshold in sorted(_CO_MARKETING_SUGGESTIONS.keys(), reverse=True):
        if referral_count >= threshold:
            return _CO_MARKETING_SUGGESTIONS[threshold]
    return _CO_MARKETING_SUGGESTIONS[1]


@autonomous_agent(
    name="referral_thank_you",
    description="Send thank-you tasks to LOs when referral partners send new leads",
    frequency=AgentFrequency.HOURLY,
    max_runtime_seconds=60,
)
def referral_thank_you(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Create enriched thank-you tasks for referral-sourced leads received today.

    Enhancements:
    - Calculate lifetime value (total funded loan volume) from same referral source
    - Include LO's conversion rate from this source
    - Differentiate priority: first referral = high (relationship-building), repeat = medium
    - Suggest co-marketing next steps based on referral count
    - Log a "Referral Received" activity on the lead
    """
    actions = 0

    referral_leads = db.execute(text("""
        SELECT l.id, l.first_name, l.last_name, l.source, l.owner_id,
               l.loan_amount, l.loan_purpose
        FROM leads l
        WHERE l.organization_id = :org_id
          AND l.created_at >= CURRENT_DATE
          AND l.source ILIKE '%referral%'
          AND NOT EXISTS (
              SELECT 1 FROM tasks t
              WHERE t.lead_id = l.id
                AND t.title LIKE 'Thank referral%'
          )
    """), {"org_id": organization_id}).fetchall()

    for lead in referral_leads:
        lead_id = str(lead[0])
        first_name = lead[1] or "Lead"
        last_name = lead[2] or ""
        source = lead[3] or ""
        owner_id = lead[4]
        referral_source = source or "referral partner"
        loan_amount = lead[5]
        loan_purpose = lead[6]

        # --- Lifetime value from this referral source ---
        ltv_row = db.execute(text("""
            SELECT COUNT(*) AS funded_count,
                   COALESCE(SUM(lo.amount), 0) AS total_volume
            FROM loans lo
            JOIN leads ld ON ld.email = lo.borrower_email AND ld.organization_id = lo.organization_id
            WHERE ld.organization_id = :org_id
              AND ld.source ILIKE :ref_src
              AND lo.stage = 'FUNDED'
        """), {"org_id": organization_id, "ref_src": f"%{referral_source}%"}).fetchone()

        funded_count = ltv_row[0] if ltv_row else 0
        total_volume = float(ltv_row[1]) if ltv_row else 0.0

        # --- Conversion rate from this source ---
        source_stats = db.execute(text("""
            SELECT COUNT(*) AS total_leads,
                   SUM(CASE WHEN stage IN ('Funded', 'FUNDED') THEN 1 ELSE 0 END) AS converted
            FROM leads
            WHERE organization_id = :org_id
              AND (referral_source ILIKE :ref_src OR source ILIKE :ref_src)
        """), {"org_id": organization_id, "ref_src": f"%{referral_source}%"}).fetchone()

        total_from_source = source_stats[0] if source_stats else 0
        converted_from_source = source_stats[1] if source_stats else 0
        conversion_rate = (
            round((converted_from_source / total_from_source) * 100, 1)
            if total_from_source > 0 else 0
        )

        # --- Priority: first referral = high, repeat = medium ---
        is_first_referral = total_from_source <= 1
        priority = "high" if is_first_referral else "medium"
        relationship_note = (
            "FIRST REFERRAL from this source — prioritize relationship-building!"
            if is_first_referral
            else f"Repeat partner — {total_from_source} total referrals."
        )

        # --- Co-marketing suggestion ---
        co_marketing = _co_marketing_suggestion(total_from_source)

        amount_str = f"${float(loan_amount):,.0f}" if loan_amount else "N/A"
        volume_str = f"${total_volume:,.0f}" if total_volume > 0 else "$0"

        _insert_task(
            db,
            title=f"Thank referral partner for {first_name} {last_name}",
            description=(
                f"New referral from: {referral_source}\n"
                f"Lead: {first_name} {last_name} | {loan_purpose or 'N/A'} | {amount_str}\n\n"
                f"RELATIONSHIP: {relationship_note}\n"
                f"LIFETIME VALUE: {funded_count} funded loans | {volume_str} total volume\n"
                f"CONVERSION RATE: {conversion_rate}% ({converted_from_source}/{total_from_source} leads)\n\n"
                f"SUGGESTED NEXT STEP:\n{co_marketing}\n\n"
                f"Send a personalized thank-you and status update on this lead."
            ),
            assigned_to_id=str(owner_id) if owner_id else None,
            lead_id=lead_id,
            priority=priority,
            organization_id=organization_id,
            gateway=gateway,
        )
        actions += 1

        # --- Log activity ---
        _insert_activity(
            db,
            lead_id=lead_id,
            activity_type="Referral",
            content=(
                f"Referral received from {referral_source}. "
                f"Lifetime: {funded_count} funded / {volume_str} volume / {conversion_rate}% conversion."
            ),
            organization_id=organization_id,
            gateway=gateway,
        )

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Referral thank-you commit failed: {e}")

    return {
        "summary": f"{actions} referral thank-you tasks created",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 5. Drip Campaign Engine
# ---------------------------------------------------------------------------

# Drip phase definitions
_DRIP_PHASES = {
    "phase_1": {
        "label": "Phase 1 — High-Frequency Follow-Up",
        "day_range": (1, 7),
        "min_interval_days": 1,
        "priority": "high",
        "message_type": "Direct follow-up",
        "templates": [
            "Personal check-in: 'Hi {name}, just following up on your inquiry. Do you have 5 minutes to chat about your options?'",
            "Value-add: 'Hi {name}, I put together a quick rate comparison for you. Want me to send it over?'",
            "Urgency: 'Hi {name}, rates shifted this week. Let me show you how it affects your purchasing power.'",
        ],
    },
    "phase_2": {
        "label": "Phase 2 — Weekly Educational Content",
        "day_range": (8, 30),
        "min_interval_days": 5,
        "priority": "medium",
        "message_type": "Educational / rate update",
        "templates": [
            "Market update: Share this week's rate trends and what they mean for {name}'s scenario.",
            "Educational: Send '{name}' an article on the {purpose} process and common pitfalls.",
            "Testimonial: Share a recent success story similar to {name}'s situation.",
        ],
    },
    "phase_3": {
        "label": "Phase 3 — Monthly Nurture",
        "day_range": (31, 90),
        "min_interval_days": 21,
        "priority": "low",
        "message_type": "Market update / stay top-of-mind",
        "templates": [
            "Monthly market digest: Send {name} the local housing market summary and rate forecast.",
            "Seasonal: 'Hi {name}, spring/summer/fall/winter is a great time for {purpose}. Thinking about it?'",
            "Re-engagement: 'Hi {name}, just checking in. Has anything changed with your plans? I am here whenever you are ready.'",
        ],
    },
}


def _determine_drip_phase(days_since_last_contact: int) -> Optional[str]:
    """Return the phase key for a lead based on days since last contact."""
    for phase_key, config in _DRIP_PHASES.items():
        low, high = config["day_range"]
        if low <= days_since_last_contact <= high:
            return phase_key
    return None


def _pick_template(phase_key: str, lead_name: str, loan_purpose: str) -> str:
    """Pick a template from the phase, filling in name and purpose."""
    import hashlib
    templates = _DRIP_PHASES[phase_key]["templates"]
    # Deterministic pick based on lead name so the same lead doesn't get the same template
    idx = int(hashlib.md5(lead_name.encode()).hexdigest(), 16) % len(templates)
    template = templates[idx]
    return template.format(name=lead_name, purpose=loan_purpose or "home purchase")


@autonomous_agent(
    name="drip_campaign_engine",
    description="Trigger next drip messages for active sequences",
    frequency=AgentFrequency.EVERY_15_MIN,
    max_runtime_seconds=90,
)
def drip_campaign_engine(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Segment nurture leads into drip phases and create targeted outreach tasks.

    Logic:
    - Phase 1 (1-7d): high-frequency direct follow-up, min 1-day gap
    - Phase 2 (8-30d): weekly educational content and rate updates, min 5-day gap
    - Phase 3 (31-90d): monthly market updates and re-engagement, min 21-day gap
    - Detect engagement signals (recent activities) and escalate engaged leads to Phase 1
    - Respect opt-out via STOP activities
    - Track drip sequence position in task description
    """
    actions = 0
    escalated = 0
    skipped_opt_out = 0

    # Fetch nurture-eligible leads
    nurture_leads = db.execute(text("""
        SELECT l.id, l.first_name, l.last_name, l.email, l.phone,
               l.owner_id, l.stage, l.last_contact, l.loan_purpose,
               l.ai_score, l.created_at,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - COALESCE(l.last_contact, l.created_at))) AS days_since
        FROM leads l
        WHERE l.organization_id = :org_id
          AND l.stage IN ('Nurture', 'Follow Up', 'Contacted')
          AND COALESCE(l.last_contact, l.created_at) < CURRENT_TIMESTAMP - INTERVAL '1 day'
          AND COALESCE(l.last_contact, l.created_at) > CURRENT_TIMESTAMP - INTERVAL '90 days'
          AND (l.email IS NOT NULL OR l.phone IS NOT NULL)
        ORDER BY l.ai_score DESC NULLS LAST
        LIMIT 50
    """), {"org_id": organization_id}).fetchall()

    for lead in nurture_leads:
        lead_id = str(lead[0])
        first_name = lead[1] or "Lead"
        last_name = lead[2] or ""
        email = lead[3]
        phone = lead[4]
        owner_id = lead[5]
        stage = lead[6]
        loan_purpose = lead[8] or "home purchase"
        ai_score = lead[9]
        days_since = int(lead[11] or 0)
        lead_name = f"{first_name} {last_name}".strip()

        # --- Check opt-out ---
        opt_out = db.execute(text("""
            SELECT id FROM activities
            WHERE lead_id = :lead_id
              AND organization_id = :org_id
              AND (type ILIKE '%opt%out%' OR type = 'STOP'
                   OR content ILIKE '%unsubscribe%' OR content ILIKE '%opt out%'
                   OR content ILIKE '%stop%' OR content ILIKE '%do not contact%')
            LIMIT 1
        """), {"lead_id": lead_id, "org_id": organization_id}).fetchone()
        if opt_out:
            skipped_opt_out += 1
            continue

        # --- Check for engagement signals (re-engagement in last 3 days) ---
        recent_engagement = db.execute(text("""
            SELECT COUNT(*) FROM activities
            WHERE lead_id = :lead_id
              AND organization_id = :org_id
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '3 days'
              AND type IN ('Email Open', 'Link Click', 'Website Visit', 'Form Submit', 'Inbound Call', 'Inbound SMS')
        """), {"lead_id": lead_id, "org_id": organization_id}).scalar() or 0

        # Escalate engaged leads back to Phase 1
        effective_days = days_since
        escalation_note = ""
        if recent_engagement > 0 and days_since > 7:
            effective_days = 3  # Treat as Phase 1
            escalation_note = f" [ESCALATED from day {days_since} — {recent_engagement} engagement signal(s) detected]"
            escalated += 1

        # --- Determine phase ---
        phase_key = _determine_drip_phase(effective_days)
        if not phase_key:
            continue  # Outside all phase windows (< 1 day or > 90 days)

        phase_config = _DRIP_PHASES[phase_key]

        # --- Dedup: check interval since last drip task ---
        min_interval = phase_config["min_interval_days"]
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE lead_id = :lead_id
              AND title LIKE 'Drip:%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '1 day' * :interval
            LIMIT 1
        """), {"lead_id": lead_id, "interval": min_interval}).fetchone()
        if existing:
            continue

        # --- Build task (respect LO channel preferences) ---
        drip_lo_memory = get_lo_memory_context(db, owner_id, organization_id) if owner_id else {}
        template = _pick_template(phase_key, first_name, loan_purpose)
        if email and not should_skip_contact(drip_lo_memory, "email"):
            channel = "email"
            contact_info = email
        elif phone and not should_skip_contact(drip_lo_memory, "sms"):
            channel = "SMS"
            contact_info = phone
        else:
            channel = "outreach"
            contact_info = email or phone or "no contact info"

        desc = (
            f"{phase_config['label']}{escalation_note}\n"
            f"Message type: {phase_config['message_type']}\n"
            f"Days since last contact: {days_since} | Effective phase day: {effective_days}\n"
            f"AI score: {ai_score or 'N/A'} | Stage: {stage} | Purpose: {loan_purpose}\n"
            f"Channel: {channel} ({contact_info})\n\n"
            f"SUGGESTED MESSAGE:\n{template}\n\n"
            f"DRIP POSITION: {phase_key.replace('_', ' ').title()} / Day {days_since} of 90"
        )

        _insert_task(
            db,
            title=f"Drip: {phase_config['message_type']} to {first_name} ({days_since}d)",
            description=desc,
            assigned_to_id=str(owner_id) if owner_id else None,
            lead_id=lead_id,
            priority=phase_config["priority"],
            organization_id=organization_id,
            gateway=gateway,
        )
        actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Drip campaign commit failed: {e}")

    return {
        "summary": (
            f"{actions} drip tasks created from {len(nurture_leads)} nurture leads "
            f"({escalated} escalated, {skipped_opt_out} opted out)"
        ),
        "actions_taken": actions,
        "notifications_sent": 0,
    }
