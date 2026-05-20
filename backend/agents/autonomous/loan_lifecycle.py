"""
Loan Lifecycle Agents

Agents that manage the loan-to-close process with full production-grade logic:
1. condition_chase — Hourly, follow up on outstanding underwriting conditions
   with urgency tiers, closing-date pressure, and borrower-specific doc tasks
2. closing_countdown — Every 30 min, milestone-based pre-closing checklist
   with readiness scoring and compliance gap detection
3. application_followup — Every 30 min, completion-scored application nudges
   with field-level gap analysis and manager escalation
4. post_close_survey — Daily 9 AM, multi-step post-funding outreach sequence
   (survey → review → referral) with deduplication and realtor thank-you
5. credit_refresh — Daily 8 AM, tiered credit/appraisal expiration alerts
   with close-velocity estimation and LO batch grouping
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Terminal stages — loans that should never be processed by lifecycle agents
# ---------------------------------------------------------------------------
TERMINAL_STAGES = (
    "FUNDED", "CANCELLED", "DENIED", "DEAD",
    "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
)

_TERMINAL_CLAUSE = (
    "l.stage NOT IN ("
    "'FUNDED','CANCELLED','DENIED','DEAD',"
    "'WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'"
    ")"
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _insert_task(
    db: Session,
    *,
    title: str,
    description: str,
    assigned_to_id: Optional[int],
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    priority: str = "medium",
    status: str = "pending",
    due_date_expr: str = "CURRENT_DATE",
    organization_id: int,
    gateway=None,
) -> None:
    """Insert a task row with standard columns."""
    def _do():
        db.execute(text(f"""
            INSERT INTO tasks (title, description, assigned_to_id, lead_id, loan_id,
                               priority, status, due_date, created_at, organization_id)
            VALUES (:title, :desc, :assigned_to_id, :lead_id, :loan_id,
                    :priority, :status, {due_date_expr}, CURRENT_TIMESTAMP, :org_id)
        """), {
            "title": title[:255],
            "desc": description[:4000],
            "assigned_to_id": str(assigned_to_id) if assigned_to_id else None,
            "lead_id": str(lead_id) if lead_id else None,
            "loan_id": str(loan_id) if loan_id else None,
            "priority": priority,
            "status": status,
            "org_id": organization_id,
        })
    if gateway:
        gateway.propose(
            "create_task", _do,
            target_entity="lead" if lead_id else ("loan" if loan_id else None),
            target_id=str(lead_id or loan_id) if (lead_id or loan_id) else None,
            description=title[:200],
        )
    else:
        _do()


def _insert_activity(
    db: Session,
    *,
    activity_type: str,
    content: str,
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    user_id: Optional[int] = None,
    organization_id: int,
    gateway=None,
) -> None:
    """Insert an activity log entry for audit trail."""
    def _do():
        db.execute(text("""
            INSERT INTO activities (type, content, loan_id, lead_id, user_id,
                                    created_at, organization_id)
            VALUES (:type, :content, :loan_id, :lead_id, :user_id,
                    CURRENT_TIMESTAMP, :org_id)
        """), {
            "type": activity_type,
            "content": content[:4000],
            "loan_id": loan_id,
            "lead_id": lead_id,
            "user_id": user_id,
            "org_id": organization_id,
        })
    if gateway:
        gateway.propose(
            "create_activity", _do,
            target_entity="lead" if lead_id else ("loan" if loan_id else None),
            target_id=str(lead_id or loan_id) if (lead_id or loan_id) else None,
            description=content[:200],
        )
    else:
        _do()


def _insert_notification(
    db: Session,
    *,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
    organization_id: int,
    gateway=None,
) -> None:
    """Insert an in-app notification."""
    def _do():
        db.execute(text("""
            INSERT INTO notifications (user_id, organization_id, type, title,
                                       message, link, is_read, created_at)
            VALUES (:uid, :org_id, :type, :title, :message, :link, false, NOW())
        """), {
            "uid": user_id,
            "org_id": organization_id,
            "type": notification_type,
            "title": title[:255],
            "message": message[:2000],
            "link": link,
        })
    if gateway:
        gateway.propose(
            "create_notification", _do,
            target_entity="user",
            target_id=str(user_id),
            description=title[:200],
        )
    else:
        _do()


def _has_recent_task(
    db: Session,
    loan_id: int,
    title_pattern: str,
    cooldown_hours: int = 48,
) -> bool:
    """Check whether a matching task already exists within the cooldown window."""
    row = db.execute(text("""
        SELECT id FROM tasks
        WHERE loan_id = :loan_id
          AND title LIKE :pattern
          AND created_at > CURRENT_TIMESTAMP - MAKE_INTERVAL(hours => :hours)
        LIMIT 1
    """), {
        "loan_id": str(loan_id),
        "pattern": f"%{title_pattern}%",
        "hours": cooldown_hours,
    }).fetchone()
    return row is not None


def _has_recent_activity(
    db: Session,
    loan_id: int,
    user_id: Optional[int],
    hours: int = 48,
) -> bool:
    """Check if there has been any recent activity on a loan by a specific user."""
    if not user_id:
        return False
    row = db.execute(text("""
        SELECT id FROM activities
        WHERE loan_id = :loan_id
          AND user_id = :user_id
          AND created_at > CURRENT_TIMESTAMP - MAKE_INTERVAL(hours => :hours)
        LIMIT 1
    """), {
        "loan_id": loan_id,
        "user_id": user_id,
        "hours": hours,
    }).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# 1. Condition Chase Agent
# ---------------------------------------------------------------------------

# Stage-specific condition context tells the LO exactly what to chase
_CONDITION_CONTEXT = {
    "CONDITIONAL_APPROVAL": {
        "label": "Underwriting conditions",
        "borrower_docs": (
            "pay stubs, bank statements, LOE (letter of explanation), "
            "updated tax returns, gift letter"
        ),
        "internal_action": "Follow up with underwriter for condition list status",
    },
    "APPROVED": {
        "label": "Prior-to-doc conditions",
        "borrower_docs": (
            "final pay stub, updated bank statement, "
            "homeowners insurance declaration page, flood cert"
        ),
        "internal_action": "Verify all PTD conditions cleared with processor",
    },
    "SUSPENDED": {
        "label": "Suspension conditions (additional documentation required)",
        "borrower_docs": (
            "additional income docs, asset verification, "
            "updated credit supplement, 4506-C, VOE"
        ),
        "internal_action": "Review suspension letter and contact UW for path to reinstatement",
    },
}


@autonomous_agent(
    name="condition_chase",
    description="Follow up on outstanding underwriting conditions with urgency tiers and closing-date pressure",
    frequency=AgentFrequency.HOURLY,
    max_runtime_seconds=90,
)
def condition_chase(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Create tiered follow-up tasks for loans with outstanding conditions.

    Urgency tiers based on days_in_stage:
      3-5d  = medium (routine follow-up)
      5-10d = high   (escalated outreach)
      10d+  = critical (manager escalation)

    Closing-date proximity overrides tier upward when closing is within 14 days.
    Creates two tasks per loan: one LO action task and one borrower doc checklist.
    Logs an activity on the loan for the audit trail.
    """
    actions = 0
    notifications = 0
    by_tier: Dict[str, int] = {"medium": 0, "high": 0, "critical": 0}

    # ----- Fetch loans in condition-bearing stages with 3+ days stale -----
    stale_conditions = db.execute(text("""
        SELECT l.id,
               l.loan_number,
               l.borrower_name,
               l.borrower_email,
               l.borrower_phone,
               l.loan_officer_id,
               l.stage,
               l.closing_date,
               COALESCE(l.days_in_stage,
                   EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.stage_changed_at))::int, 0
               ) AS days_in_stage,
               CONCAT(u.first_name, ' ', u.last_name) AS lo_name
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage IN ('CONDITIONAL_APPROVAL', 'APPROVED', 'SUSPENDED')
          AND l.stage_changed_at < CURRENT_TIMESTAMP - INTERVAL '3 days'
    """), {"org_id": organization_id}).fetchall()

    for loan in stale_conditions:
        (loan_id, loan_number, borrower_name, borrower_email, borrower_phone,
         lo_id, stage, closing_date, days_in_stage, lo_name) = loan

        days = int(days_in_stage or 0)

        # ----- Determine urgency tier -----
        if days >= 10:
            tier = "critical"
        elif days >= 5:
            tier = "high"
        else:
            tier = "medium"

        # Closing-date pressure: if closing within 14 days, bump tier
        closing_pressure = False
        days_to_close = None
        if closing_date:
            try:
                if hasattr(closing_date, 'date'):
                    close_dt = closing_date.date() if hasattr(closing_date, 'date') else closing_date
                else:
                    close_dt = closing_date
                days_to_close_val = (close_dt - datetime.now(timezone.utc).date()).days if hasattr(close_dt, '__sub__') else None
                if days_to_close_val is not None:
                    days_to_close = days_to_close_val
                    if days_to_close <= 14:
                        closing_pressure = True
                        if days_to_close <= 7:
                            tier = "critical"
                        elif tier == "medium":
                            tier = "high"
            except Exception:
                pass

        # ----- Dedup: skip if LO action task created recently -----
        if _has_recent_task(db, loan_id, "condition chase", cooldown_hours=24 if tier == "critical" else 48):
            continue

        # ----- Build context from stage -----
        ctx = _CONDITION_CONTEXT.get(stage, {
            "label": f"Outstanding conditions ({stage})",
            "borrower_docs": "outstanding documents per condition list",
            "internal_action": "Review condition list and follow up",
        })

        # ----- LO action task with specific steps -----
        closing_note = ""
        if closing_pressure and days_to_close is not None:
            closing_note = (
                f" CLOSING IN {days_to_close} DAYS — treat as urgent. "
                f"Coordinate with processor and title company immediately."
            )

        escalation_note = ""
        if days >= 10:
            escalation_note = " ESCALATION: 10+ days stale — loop in branch manager for resolution."

        lo_task_desc = (
            f"Loan {loan_number} ({borrower_name}) has been in {stage} for {days} days.\n\n"
            f"Condition type: {ctx['label']}\n\n"
            f"Action steps:\n"
            f"1. Call borrower ({borrower_phone or 'no phone'}) to request: {ctx['borrower_docs']}\n"
            f"2. {ctx['internal_action']}\n"
            f"3. Email borrower ({borrower_email or 'no email'}) with itemized list of needed docs\n"
            f"4. Update loan notes with condition status after each contact"
            f"{escalation_note}{closing_note}"
        )

        _insert_task(
            db,
            title=f"Condition chase [{tier.upper()}]: {borrower_name} — {days}d in {stage}",
            description=lo_task_desc,
            assigned_to_id=lo_id,
            loan_id=loan_id,
            priority=tier,
            due_date_expr="CURRENT_DATE" if tier == "critical" else "CURRENT_DATE + 1",
            organization_id=organization_id,
            gateway=gateway,
        )
        actions += 1

        # ----- Borrower-facing doc request task -----
        if not _has_recent_task(db, loan_id, "borrower docs needed", cooldown_hours=72):
            borrower_task_desc = (
                f"Documents needed from {borrower_name} for loan {loan_number}:\n\n"
                f"Stage: {stage} — {ctx['label']}\n"
                f"Documents to provide: {ctx['borrower_docs']}\n\n"
                f"Contact: {borrower_email or 'N/A'} | {borrower_phone or 'N/A'}\n"
                f"Days waiting: {days}"
            )

            _insert_task(
                db,
                title=f"Borrower docs needed: {borrower_name} ({loan_number})",
                description=borrower_task_desc,
                assigned_to_id=lo_id,
                loan_id=loan_id,
                priority=tier,
                due_date_expr="CURRENT_DATE",
                organization_id=organization_id,
                gateway=gateway,
            )
            actions += 1

        # ----- Activity log for audit trail -----
        _insert_activity(
            db,
            activity_type="Note",
            content=(
                f"[Condition Chase Agent] Auto-generated follow-up. "
                f"Loan in {stage} for {days}d. Urgency: {tier}. "
                f"Closing pressure: {'YES' if closing_pressure else 'No'}."
            ),
            loan_id=loan_id,
            user_id=lo_id,
            organization_id=organization_id,
            gateway=gateway,
        )

        # ----- Notification for critical tier -----
        if tier == "critical" and lo_id:
            _insert_notification(
                db,
                user_id=lo_id,
                notification_type="condition_chase",
                title=f"CRITICAL: {borrower_name} conditions stale {days}d",
                message=(
                    f"Loan {loan_number} has been in {stage} for {days} days. "
                    f"{'Closing in ' + str(days_to_close) + ' days. ' if days_to_close else ''}"
                    f"Immediate action required."
                ),
                link=f"/pipeline/loans/{loan_number}",
                organization_id=organization_id,
                gateway=gateway,
            )
            notifications += 1

        by_tier[tier] = by_tier.get(tier, 0) + 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Condition chase commit failed: %s", e)

    total = sum(by_tier.values())
    return {
        "summary": (
            f"{total} loans chased ({actions} tasks created): "
            f"medium={by_tier['medium']}, high={by_tier['high']}, critical={by_tier['critical']}"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications,
        "loans_reviewed": len(stale_conditions),
        "by_tier": by_tier,
    }


# ---------------------------------------------------------------------------
# 2. Closing Countdown Agent
# ---------------------------------------------------------------------------

# Checklist items keyed by days-to-close threshold.
# Items are cumulative: a loan at 3 days gets the 7d, 5d, AND 3d items.
_CLOSING_CHECKLIST: List[Tuple[int, str, str, str]] = [
    # (days_threshold, task_key, title_suffix, description)
    (7, "title_clear", "Verify title is clear",
     "Confirm title search complete and clear. Contact title company for status if not received."),
    (7, "insurance_bound", "Verify homeowners insurance bound",
     "Confirm hazard insurance policy bound and declaration page received. Contact insurance agent if missing."),
    (7, "appraisal_current", "Verify appraisal docs current",
     "Check appraisal_docs_expire_date. If expired or expiring before close, order rush refresh."),
    (5, "cd_sent", "Confirm Closing Disclosure sent",
     "TRID requires CD delivered 3 business days before closing. Verify cd_sent_to_borrower_date is populated."),
    (5, "cashiers_check", "Verify cash-to-close amount",
     "Calculate final cash-to-close and confirm with borrower. Include earnest money credit, seller concessions, prorations."),
    (3, "walkthrough", "Final walkthrough scheduled",
     "Confirm final walkthrough date/time with borrower and real estate agent. Typically 24-48 hours before closing."),
    (3, "closing_agent", "Closing agent confirmed",
     "Verify closing agent/attorney assigned and confirmed. Send closing package if not already sent."),
    (3, "wire_instructions", "Wire instructions verified",
     "Confirm wire instructions sent to borrower. Warn about wire fraud — verbal verification only, never email changes."),
    (1, "final_doc_review", "Final document review",
     "Review entire closing package for accuracy: loan amount, rate, fees, names, property address, vesting."),
    (1, "all_parties_confirmed", "Confirm all closing parties",
     "Verify attendance: borrower(s), seller, real estate agent(s), closing attorney. Confirm time and location."),
]


@autonomous_agent(
    name="closing_countdown",
    description="Milestone-based pre-closing checklist with readiness scoring and compliance detection",
    frequency=AgentFrequency.EVERY_30_MIN,
    max_runtime_seconds=90,
)
def closing_countdown(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Create granular closing checklist tasks based on days-to-close.

    For each loan closing within 7 days:
    - Creates individual checklist tasks for each milestone appropriate to the timeline
    - Detects compliance gaps (CD not sent with closing in 3 days = CRITICAL)
    - Creates borrower-facing reminder with what to bring to closing
    - Calculates and returns closing readiness score per loan
    """
    actions = 0
    notifications = 0
    readiness_scores: List[Dict[str, Any]] = []

    # ----- Fetch loans closing within 7 days -----
    closing_soon = db.execute(text("""
        SELECT l.id,
               l.loan_number,
               l.borrower_name,
               l.borrower_email,
               l.borrower_phone,
               l.loan_officer_id,
               l.closing_date,
               l.cd_sent_to_borrower_date,
               l.appraisal_docs_expire_date,
               l.title_received_date,
               l.insurance_received_date,
               l.stage,
               l.amount,
               l.property_address,
               (l.closing_date::date - CURRENT_DATE) AS days_to_close,
               CONCAT(u.first_name, ' ', u.last_name) AS lo_name
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.closing_date::date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7
          AND l.stage NOT IN (
              'FUNDED','CANCELLED','DENIED','DEAD',
              'WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'
          )
        ORDER BY l.closing_date ASC
    """), {"org_id": organization_id}).fetchall()

    for loan in closing_soon:
        (loan_id, loan_number, borrower_name, borrower_email, borrower_phone,
         lo_id, closing_date, cd_sent_date, appraisal_expire_date,
         title_received_date, insurance_received_date, stage, amount,
         property_address, days_to_close_raw, lo_name) = loan

        days_to_close = int(days_to_close_raw or 0)

        # ----- Generate applicable checklist items -----
        items_created = 0
        items_applicable = 0

        for threshold, task_key, title_suffix, description in _CLOSING_CHECKLIST:
            if days_to_close > threshold:
                continue

            items_applicable += 1

            # Dedup: check if this specific checklist item already exists
            dedup_key = f"closing:{task_key}"
            if _has_recent_task(db, loan_id, dedup_key, cooldown_hours=24):
                items_created += 1  # Count as "complete" for readiness score
                continue

            # Determine priority based on proximity
            if days_to_close <= 1:
                priority = "critical"
            elif days_to_close <= 3:
                priority = "high"
            else:
                priority = "medium"

            full_desc = (
                f"{description}\n\n"
                f"Loan: {loan_number} | Borrower: {borrower_name}\n"
                f"Closing: {closing_date} ({days_to_close} days)\n"
                f"Property: {property_address or 'N/A'}"
            )

            _insert_task(
                db,
                title=f"[closing:{task_key}] {title_suffix} — {borrower_name} ({days_to_close}d)",
                description=full_desc,
                assigned_to_id=lo_id,
                loan_id=loan_id,
                priority=priority,
                due_date_expr=f"CURRENT_DATE + {max(0, days_to_close - 1)}",
                organization_id=organization_id,
                gateway=gateway,
            )
            items_created += 1
            actions += 1

        # ----- Compliance gap detection -----
        # TRID: CD must be sent 3 business days before closing
        if days_to_close <= 3 and cd_sent_date is None:
            if not _has_recent_task(db, loan_id, "COMPLIANCE: CD not sent", cooldown_hours=12):
                _insert_task(
                    db,
                    title=f"COMPLIANCE: CD not sent — {borrower_name} closing in {days_to_close}d",
                    description=(
                        f"CRITICAL TRID VIOLATION RISK: Closing Disclosure has NOT been sent "
                        f"for loan {loan_number} ({borrower_name}) and closing is in {days_to_close} days.\n\n"
                        f"TRID requires CD delivery 3 business days before closing. "
                        f"If CD cannot be sent immediately, closing must be rescheduled.\n\n"
                        f"Action: Send CD immediately or contact compliance officer."
                    ),
                    assigned_to_id=lo_id,
                    loan_id=loan_id,
                    priority="critical",
                    due_date_expr="CURRENT_DATE",
                    organization_id=organization_id,
                    gateway=gateway,
                )
                actions += 1

                # Critical compliance notification
                if lo_id:
                    _insert_notification(
                        db,
                        user_id=lo_id,
                        notification_type="compliance_alert",
                        title=f"TRID RISK: CD not sent, closing in {days_to_close}d",
                        message=(
                            f"Loan {loan_number} ({borrower_name}) is closing in {days_to_close} "
                            f"days but the Closing Disclosure has not been sent. "
                            f"TRID requires 3 business days. Take immediate action."
                        ),
                        link=f"/pipeline/loans/{loan_number}",
                        organization_id=organization_id,
                        gateway=gateway,
                    )
                    notifications += 1

        # ----- Borrower closing reminder -----
        if days_to_close <= 3 and not _has_recent_task(db, loan_id, "borrower closing prep", cooldown_hours=72):
            borrower_reminder = (
                f"Send closing prep reminder to {borrower_name} ({borrower_email or 'no email'}):\n\n"
                f"Items to bring to closing:\n"
                f"- Valid government-issued photo ID (driver's license or passport)\n"
                f"- Cashier's check or wire confirmation for cash-to-close\n"
                f"- Proof of homeowners insurance\n"
                f"- Any outstanding documents requested by lender\n\n"
                f"Closing details:\n"
                f"- Date: {closing_date}\n"
                f"- Property: {property_address or 'TBD'}\n"
                f"- Loan: {loan_number}\n\n"
                f"Remind borrower: NEVER change wire instructions received by email. "
                f"Always verify wire details by phone using a known number."
            )

            _insert_task(
                db,
                title=f"[borrower closing prep] Send closing reminder: {borrower_name}",
                description=borrower_reminder,
                assigned_to_id=lo_id,
                loan_id=loan_id,
                priority="high",
                due_date_expr="CURRENT_DATE",
                organization_id=organization_id,
                gateway=gateway,
            )
            actions += 1

        # ----- Calculate readiness score -----
        readiness_pct = int((items_created / items_applicable * 100)) if items_applicable > 0 else 100
        readiness_scores.append({
            "loan_number": loan_number,
            "borrower_name": borrower_name,
            "days_to_close": days_to_close,
            "readiness_pct": readiness_pct,
            "items_complete": items_created,
            "items_total": items_applicable,
        })

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Closing countdown commit failed: %s", e)

    avg_readiness = (
        int(sum(r["readiness_pct"] for r in readiness_scores) / len(readiness_scores))
        if readiness_scores else 0
    )

    return {
        "summary": (
            f"{len(closing_soon)} loans closing within 7d, {actions} checklist tasks created, "
            f"avg readiness {avg_readiness}%"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications,
        "loans_closing_soon": len(closing_soon),
        "readiness_scores": readiness_scores,
        "avg_readiness_pct": avg_readiness,
    }


# ---------------------------------------------------------------------------
# 3. Application Follow-up Agent
# ---------------------------------------------------------------------------

# Fields used to calculate application completion score.
# Each tuple: (column_name, weight, label_for_missing_list)
_COMPLETION_FIELDS: List[Tuple[str, int, str]] = [
    ("amount", 15, "Loan amount"),
    ("loan_type", 10, "Loan type (Conventional/FHA/VA/USDA)"),
    ("loan_purpose", 10, "Loan purpose (Purchase/Refinance)"),
    ("property_address", 10, "Property address"),
    ("property_type", 5, "Property type"),
    ("purchase_price", 10, "Purchase price"),
    ("down_payment", 5, "Down payment amount"),
    ("borrower_email", 10, "Borrower email"),
    ("borrower_phone", 10, "Borrower phone number"),
    ("rate", 5, "Interest rate"),
    ("closing_date", 5, "Target closing date"),
    ("property_state", 5, "Property state"),
]
_TOTAL_WEIGHT = sum(w for _, w, _ in _COMPLETION_FIELDS)


@autonomous_agent(
    name="application_followup",
    description="Completion-scored application nudges with field-level gap analysis and manager escalation",
    frequency=AgentFrequency.EVERY_30_MIN,
    max_runtime_seconds=90,
)
def application_followup(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Find applications stuck in APPLICATION stage and create targeted follow-ups.

    - Calculates completion score based on populated fields
    - Segments: <50% = needs full intake call, 50-80% = missing key docs, 80%+ = ready to submit
    - Lists specific missing fields in task description
    - Checks for recent LO contact to avoid over-contacting
    - Escalates to manager if stalled 7+ days with no LO activity
    - Compares to org average time-to-disclose to flag outliers
    """
    actions = 0
    notifications = 0
    by_segment: Dict[str, int] = {"needs_intake": 0, "missing_docs": 0, "ready_to_submit": 0}

    # ----- Compute org average days from APPLICATION to DISCLOSED -----
    avg_row = db.execute(text("""
        SELECT AVG(EXTRACT(DAY FROM (l.stage_changed_at - l.application_date)))
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.application_date IS NOT NULL
          AND l.stage_changed_at IS NOT NULL
          AND l.stage != 'APPLICATION'
          AND l.application_date > CURRENT_TIMESTAMP - INTERVAL '90 days'
    """), {"org_id": organization_id}).fetchone()
    org_avg_days_to_disclose = float(avg_row[0]) if avg_row and avg_row[0] else 5.0

    # Build the column select dynamically for completion scoring
    col_names = ", ".join(f"l.{col}" for col, _, _ in _COMPLETION_FIELDS)

    stalled = db.execute(text(f"""
        SELECT l.id,
               l.loan_number,
               l.borrower_name,
               l.borrower_email,
               l.borrower_phone,
               l.loan_officer_id,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - COALESCE(l.application_date, l.created_at)))::int AS days_old,
               CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
               {col_names}
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage = 'APPLICATION'
          AND COALESCE(l.application_date, l.created_at) < CURRENT_TIMESTAMP - INTERVAL '48 hours'
          AND COALESCE(l.application_date, l.created_at) > CURRENT_TIMESTAMP - INTERVAL '30 days'
        ORDER BY COALESCE(l.application_date, l.created_at) ASC
    """), {"org_id": organization_id}).fetchall()

    # Column index offsets: 0=id, 1=loan_number, ..., 7=lo_name, then completion fields
    FIELD_START_IDX = 8

    for loan in stalled:
        loan_id = loan[0]
        loan_number = loan[1]
        borrower_name = loan[2]
        borrower_email = loan[3]
        borrower_phone = loan[4]
        lo_id = loan[5]
        days_old = int(loan[6] or 0)
        lo_name = loan[7]

        # ----- Calculate completion score -----
        score = 0
        missing_fields: List[str] = []
        for i, (col, weight, label) in enumerate(_COMPLETION_FIELDS):
            val = loan[FIELD_START_IDX + i]
            if val is not None and str(val).strip():
                score += weight
            else:
                missing_fields.append(label)

        completion_pct = int((score / _TOTAL_WEIGHT) * 100) if _TOTAL_WEIGHT > 0 else 0

        # ----- Segment -----
        if completion_pct < 50:
            segment = "needs_intake"
            segment_label = "Needs full intake call"
            segment_action = "Schedule a full intake call to collect all application data."
            priority = "high"
        elif completion_pct < 80:
            segment = "missing_docs"
            segment_label = "Missing key information"
            segment_action = "Contact borrower to collect the specific missing items listed below."
            priority = "high" if days_old >= 5 else "medium"
        else:
            segment = "ready_to_submit"
            segment_label = "Nearly complete — ready to submit"
            segment_action = "Review application for accuracy and submit to processing."
            priority = "medium"

        # ----- Dedup check -----
        cooldown = 24 if days_old >= 7 else 48
        if _has_recent_task(db, loan_id, "app follow-up", cooldown_hours=cooldown):
            continue

        # ----- Check recent LO contact (avoid over-contacting) -----
        lo_recently_active = _has_recent_activity(db, loan_id, lo_id, hours=48)
        if lo_recently_active and days_old < 5:
            continue  # LO is working the file, don't nag yet

        # ----- Is this an outlier? -----
        is_outlier = days_old > (org_avg_days_to_disclose * 2) if org_avg_days_to_disclose > 0 else False

        # ----- Build task description -----
        missing_list = "\n".join(f"  - {f}" for f in missing_fields) if missing_fields else "  (all fields populated)"
        outlier_note = (
            f"\n\nOUTLIER: This application has been open {days_old}d vs org average "
            f"of {org_avg_days_to_disclose:.1f}d to disclose."
        ) if is_outlier else ""

        contact_note = ""
        if lo_recently_active:
            contact_note = "\n\nNote: LO has recent activity on this loan — review before re-contacting."

        task_desc = (
            f"Application {loan_number} ({borrower_name}) — {days_old} days in APPLICATION\n"
            f"Completion: {completion_pct}% — {segment_label}\n\n"
            f"Action: {segment_action}\n\n"
            f"Missing fields:\n{missing_list}"
            f"{contact_note}{outlier_note}\n\n"
            f"Contact: {borrower_email or 'N/A'} | {borrower_phone or 'N/A'}"
        )

        _insert_task(
            db,
            title=f"App follow-up [{completion_pct}%]: {borrower_name} ({days_old}d stalled)",
            description=task_desc,
            assigned_to_id=lo_id,
            loan_id=loan_id,
            priority=priority,
            due_date_expr="CURRENT_DATE",
            organization_id=organization_id,
            gateway=gateway,
        )
        actions += 1
        by_segment[segment] = by_segment.get(segment, 0) + 1

        # ----- Manager escalation for 7+ day stalls with no LO activity -----
        if days_old >= 7 and not lo_recently_active:
            manager_row = db.execute(text("""
                SELECT u.id FROM users u
                WHERE u.organization_id = :org_id
                  AND u.role IN ('branch_manager', 'manager', 'admin')
                  AND u.is_active = true
                ORDER BY CASE u.role
                    WHEN 'branch_manager' THEN 1
                    WHEN 'manager' THEN 2
                    ELSE 3
                END
                LIMIT 1
            """), {"org_id": organization_id}).fetchone()

            if manager_row and not _has_recent_task(db, loan_id, "ESCALATION: stalled app", cooldown_hours=72):
                manager_id = manager_row[0]
                _insert_task(
                    db,
                    title=f"ESCALATION: stalled app — {borrower_name} ({days_old}d, {completion_pct}%)",
                    description=(
                        f"Application {loan_number} ({borrower_name}) has been in APPLICATION "
                        f"for {days_old} days with no recent LO activity.\n\n"
                        f"LO: {lo_name or 'Unassigned'}\n"
                        f"Completion: {completion_pct}%\n"
                        f"Org avg time-to-disclose: {org_avg_days_to_disclose:.1f}d\n\n"
                        f"Recommend: Review with LO and determine if file should be advanced, "
                        f"nurtured, or marked as dead."
                    ),
                    assigned_to_id=manager_id,
                    loan_id=loan_id,
                    priority="high",
                    due_date_expr="CURRENT_DATE",
                    organization_id=organization_id,
                    gateway=gateway,
                )
                actions += 1

                _insert_notification(
                    db,
                    user_id=manager_id,
                    notification_type="app_escalation",
                    title=f"Stalled app: {borrower_name} ({days_old}d)",
                    message=(
                        f"Loan {loan_number} by {lo_name or 'Unassigned'} has been in APPLICATION "
                        f"for {days_old}d with no LO activity. {completion_pct}% complete."
                    ),
                    link=f"/pipeline/loans/{loan_number}",
                    organization_id=organization_id,
                    gateway=gateway,
                )
                notifications += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Application followup commit failed: %s", e)

    return {
        "summary": (
            f"{len(stalled)} stalled applications reviewed, {actions} tasks created "
            f"(intake={by_segment['needs_intake']}, missing={by_segment['missing_docs']}, "
            f"ready={by_segment['ready_to_submit']})"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications,
        "applications_reviewed": len(stalled),
        "by_segment": by_segment,
        "org_avg_days_to_disclose": round(org_avg_days_to_disclose, 1),
    }


# ---------------------------------------------------------------------------
# 4. Post-Close Survey Agent
# ---------------------------------------------------------------------------

# Multi-step outreach sequence keyed by days since funding.
# Each step: (days_after_funding, step_key, title, description_template)
_OUTREACH_SEQUENCE: List[Tuple[int, str, str, str]] = [
    (3, "satisfaction_survey", "Send satisfaction survey",
     ("Send a satisfaction survey to {borrower_name} for loan {loan_number}.\n\n"
      "LO: {lo_name}\n"
      "Funded: {funded_date}\n"
      "Property: {property_address}\n"
      "Amount: ${amount}\n\n"
      "Include:\n"
      "- Overall satisfaction rating (1-10)\n"
      "- Communication quality\n"
      "- Would they recommend? (NPS)\n"
      "- Open feedback field\n\n"
      "Use personalized email — reference their specific property and loan details.")),
    (7, "review_request", "Request online review",
     ("Request an online review from {borrower_name} for loan {loan_number}.\n\n"
      "LO: {lo_name}\n\n"
      "Send personalized message with direct links to:\n"
      "- Google Business review (LO's profile)\n"
      "- Zillow lender review\n"
      "- Yelp review (if applicable)\n\n"
      "Key: Keep it personal. Reference their home at {property_address} "
      "and thank them for choosing {lo_name}.\n\n"
      "Tip: Borrowers who gave 9-10 NPS scores are most likely to leave reviews.")),
    (14, "referral_ask", "Send referral request",
     ("Follow up with {borrower_name} to request referrals for loan {loan_number}.\n\n"
      "LO: {lo_name}\n\n"
      "Message should include:\n"
      "- Thank them for their business\n"
      "- Ask if they know anyone buying, selling, or refinancing\n"
      "- Offer a warm introduction format (\"I'd love to help anyone you know\")\n"
      "- Include LO's contact card / scheduling link\n\n"
      "Funded: {funded_date} | Property: {property_address}")),
]


@autonomous_agent(
    name="post_close_survey",
    description="Multi-step post-funding outreach: satisfaction survey, review request, referral ask",
    frequency=AgentFrequency.DAILY_9AM,
    max_runtime_seconds=90,
)
def post_close_survey(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Execute multi-step post-close outreach sequence for funded loans.

    Sequence:
      Day 3  — Satisfaction survey
      Day 7  — Online review request (Google, Zillow)
      Day 14 — Referral ask

    Also:
    - Creates realtor thank-you task if source was a real estate agent referral
    - Checks previous tasks to determine which step the borrower is on
    - Calculates NPS-eligible volume for org metrics
    """
    actions = 0
    notifications = 0
    steps_created: Dict[str, int] = {"satisfaction_survey": 0, "review_request": 0, "referral_ask": 0}

    # ----- Fetch recently funded loans (within 21 days for full sequence coverage) -----
    funded_loans = db.execute(text("""
        SELECT l.id,
               l.loan_number,
               l.borrower_name,
               l.borrower_email,
               l.borrower_phone,
               l.loan_officer_id,
               l.funded_date,
               l.stage_changed_at,
               l.amount,
               l.property_address,
               l.realtor_agent,
               CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - COALESCE(l.funded_date, l.stage_changed_at)))::int AS days_since_funded
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND COALESCE(l.funded_date, l.stage_changed_at) IS NOT NULL
          AND COALESCE(l.funded_date, l.stage_changed_at) > CURRENT_TIMESTAMP - INTERVAL '21 days'
        ORDER BY COALESCE(l.funded_date, l.stage_changed_at) DESC
    """), {"org_id": organization_id}).fetchall()

    for loan in funded_loans:
        (loan_id, loan_number, borrower_name, borrower_email, borrower_phone,
         lo_id, funded_date, stage_changed_at, amount, property_address,
         realtor_agent, lo_name, days_since_funded) = loan

        days_since = int(days_since_funded or 0)
        effective_funded_date = funded_date or stage_changed_at

        # Format amount for display
        amount_str = f"{float(amount):,.2f}" if amount else "N/A"

        # ----- Determine which outreach step is appropriate -----
        for step_days, step_key, step_title, desc_template in _OUTREACH_SEQUENCE:
            # Only create the step if we are within the right window
            # (step_days to step_days + 4 days — gives a 4-day creation window)
            if days_since < step_days or days_since > step_days + 4:
                continue

            # Dedup: has this step already been created?
            if _has_recent_task(db, loan_id, step_key, cooldown_hours=168):  # 7 day cooldown
                continue

            # Format description with loan-specific details
            desc = desc_template.format(
                borrower_name=borrower_name or "Borrower",
                loan_number=loan_number,
                lo_name=lo_name or "Your Loan Officer",
                funded_date=effective_funded_date,
                property_address=property_address or "their new property",
                amount=amount_str,
            )

            priority = "medium" if step_key == "satisfaction_survey" else "low"

            _insert_task(
                db,
                title=f"[{step_key}] {step_title}: {borrower_name} ({loan_number})",
                description=desc,
                assigned_to_id=lo_id,
                loan_id=loan_id,
                priority=priority,
                due_date_expr="CURRENT_DATE + 1",
                organization_id=organization_id,
                gateway=gateway,
            )
            actions += 1
            steps_created[step_key] = steps_created.get(step_key, 0) + 1

        # ----- Realtor thank-you task -----
        if realtor_agent and days_since >= 3 and days_since <= 7:
            if not _has_recent_task(db, loan_id, "realtor thank-you", cooldown_hours=168):
                _insert_task(
                    db,
                    title=f"[realtor thank-you] Thank {realtor_agent}: {borrower_name} closed",
                    description=(
                        f"Send a thank-you to realtor {realtor_agent} for the "
                        f"{borrower_name} transaction ({loan_number}).\n\n"
                        f"Property: {property_address or 'N/A'}\n"
                        f"Amount: ${amount_str}\n"
                        f"Funded: {effective_funded_date}\n\n"
                        f"Include:\n"
                        f"- Personal thank-you note\n"
                        f"- Remind them of your availability for future clients\n"
                        f"- Consider a small gift or handwritten card for top referral partners"
                    ),
                    assigned_to_id=lo_id,
                    loan_id=loan_id,
                    priority="low",
                    due_date_expr="CURRENT_DATE + 2",
                    organization_id=organization_id,
                    gateway=gateway,
                )
                actions += 1

    # ----- Calculate NPS-eligible volume -----
    nps_eligible = db.execute(text("""
        SELECT COUNT(*) FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND COALESCE(l.funded_date, l.stage_changed_at) > CURRENT_TIMESTAMP - INTERVAL '30 days'
    """), {"org_id": organization_id}).scalar() or 0

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Post-close survey commit failed: %s", e)

    return {
        "summary": (
            f"{len(funded_loans)} funded loans processed, {actions} outreach tasks created "
            f"(survey={steps_created['satisfaction_survey']}, "
            f"review={steps_created['review_request']}, "
            f"referral={steps_created['referral_ask']})"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications,
        "funded_loans_processed": len(funded_loans),
        "steps_created": steps_created,
        "nps_eligible_volume_30d": nps_eligible,
    }


# ---------------------------------------------------------------------------
# 5. Credit Refresh Agent
# ---------------------------------------------------------------------------

# Tiered alert thresholds for document expiration
_EXPIRY_TIERS: List[Tuple[int, str, str]] = [
    (3, "critical", "CRITICAL"),
    (7, "high", "HIGH"),
    (14, "high", "MEDIUM"),
    (30, "medium", "INFO"),
]

# Average stage durations (calendar days) for close-velocity estimation
_AVG_STAGE_DURATION = {
    "APPLICATION": 5,
    "DISCLOSED": 7,
    "PROCESSING": 7,
    "SUBMITTED": 3,
    "UNDERWRITING": 5,
    "UW_RECEIVED": 5,
    "CONDITIONAL_APPROVAL": 5,
    "APPROVED": 3,
    "CTC": 3,
    "CLEAR_TO_CLOSE": 3,
    "CLOSING": 2,
    "DOCS": 3,
    "DOCS_OUT": 5,
}

# Ordered stages for velocity calculation
_STAGE_ORDER = [
    "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
    "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED",
    "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT",
]


def _estimate_days_to_close(current_stage: str) -> int:
    """Estimate calendar days from current stage to funding based on average durations."""
    try:
        idx = _STAGE_ORDER.index(current_stage)
    except ValueError:
        return 30  # Unknown stage, assume 30 days

    remaining = 0
    for stage in _STAGE_ORDER[idx:]:
        remaining += _AVG_STAGE_DURATION.get(stage, 3)
    return remaining


def _get_expiry_tier(days_remaining: int) -> Tuple[str, str]:
    """Return (priority, label) for the given days remaining."""
    for threshold, priority, label in _EXPIRY_TIERS:
        if days_remaining <= threshold:
            return priority, label
    return "low", "OK"


@autonomous_agent(
    name="credit_refresh",
    description="Tiered credit/appraisal expiration alerts with close-velocity estimation and LO batch grouping",
    frequency=AgentFrequency.DAILY_8AM,
    max_runtime_seconds=90,
)
def credit_refresh(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Monitor credit and appraisal document expiration dates.

    - Checks both credit_docs_expire_date and appraisal_docs_expire_date
    - Creates tiered alerts: 30d = info, 14d = medium, 7d = high, 3d = critical
    - Estimates whether loan can close before expiration based on stage velocity
    - Includes estimated refresh cost in task description when expiration is likely
    - Groups alerts by LO for efficient batch ordering
    - Tracks total exposure (sum of loan amounts with expiring docs)
    """
    actions = 0
    notifications = 0
    total_exposure = 0.0
    by_tier: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    lo_batches: Dict[int, List[Dict[str, Any]]] = {}  # lo_id -> list of expiring loans

    # ----- Fetch loans with expiration dates within 30 days -----
    expiring = db.execute(text("""
        SELECT l.id,
               l.loan_number,
               l.borrower_name,
               l.borrower_email,
               l.loan_officer_id,
               l.stage,
               l.amount,
               l.credit_docs_expire_date,
               l.appraisal_docs_expire_date,
               l.closing_date,
               (l.credit_docs_expire_date::date - CURRENT_DATE) AS credit_days_left,
               (l.appraisal_docs_expire_date::date - CURRENT_DATE) AS appraisal_days_left,
               CONCAT(u.first_name, ' ', u.last_name) AS lo_name
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN (
              'FUNDED','CANCELLED','DENIED','DEAD',
              'WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'
          )
          AND (
              (l.credit_docs_expire_date IS NOT NULL
               AND l.credit_docs_expire_date::date BETWEEN CURRENT_DATE AND CURRENT_DATE + 30)
              OR
              (l.appraisal_docs_expire_date IS NOT NULL
               AND l.appraisal_docs_expire_date::date BETWEEN CURRENT_DATE AND CURRENT_DATE + 30)
          )
        ORDER BY LEAST(
            COALESCE(l.credit_docs_expire_date, '2099-12-31'::date),
            COALESCE(l.appraisal_docs_expire_date, '2099-12-31'::date)
        ) ASC
    """), {"org_id": organization_id}).fetchall()

    for loan in expiring:
        (loan_id, loan_number, borrower_name, borrower_email, lo_id, stage,
         amount, credit_expire, appraisal_expire, closing_date,
         credit_days_raw, appraisal_days_raw, lo_name) = loan

        loan_amount = float(amount) if amount else 0.0
        est_days_to_close = _estimate_days_to_close(stage or "APPLICATION")

        # ----- Process credit doc expiration -----
        if credit_days_raw is not None:
            credit_days = int(credit_days_raw)
            if 0 <= credit_days <= 30:
                priority, tier_label = _get_expiry_tier(credit_days)

                can_close_before = credit_days >= est_days_to_close

                if not _has_recent_task(db, loan_id, "credit refresh", cooldown_hours=168 if credit_days > 14 else 72 if credit_days > 7 else 24):
                    # Estimate refresh cost
                    cost_note = ""
                    if not can_close_before:
                        cost_note = (
                            f"\n\nESTIMATED REFRESH COST: ~$30-65 per borrower for credit refresh.\n"
                            f"Based on current stage ({stage}), estimated {est_days_to_close}d to close "
                            f"but credit expires in {credit_days}d. Refresh is REQUIRED."
                        )

                    _insert_task(
                        db,
                        title=f"Credit refresh [{tier_label}]: {borrower_name} — {credit_days}d remaining",
                        description=(
                            f"Credit report for {borrower_name} ({loan_number}) expires {credit_expire}.\n"
                            f"Days remaining: {credit_days}\n"
                            f"Current stage: {stage}\n"
                            f"Estimated days to close: {est_days_to_close}\n"
                            f"Can close before expiry: {'YES' if can_close_before else 'NO — refresh needed'}\n"
                            f"Loan amount: ${loan_amount:,.2f}"
                            f"{cost_note}\n\n"
                            f"Action: {'Monitor — on track to close before expiry.' if can_close_before else 'Order credit refresh immediately to avoid pipeline delay.'}"
                        ),
                        assigned_to_id=lo_id,
                        loan_id=loan_id,
                        priority=priority,
                        due_date_expr=f"CURRENT_DATE + {max(0, credit_days - 2)}",
                        organization_id=organization_id,
                        gateway=gateway,
                    )
                    actions += 1
                    by_tier[priority] = by_tier.get(priority, 0) + 1
                    total_exposure += loan_amount

                    # Track for LO batch grouping
                    if lo_id:
                        lo_batches.setdefault(lo_id, []).append({
                            "type": "credit",
                            "loan_number": loan_number,
                            "borrower_name": borrower_name,
                            "days_left": credit_days,
                            "amount": loan_amount,
                        })

                    # Critical notification
                    if credit_days <= 3 and lo_id:
                        _insert_notification(
                            db,
                            user_id=lo_id,
                            notification_type="credit_expiring",
                            title=f"CRITICAL: Credit expires in {credit_days}d — {borrower_name}",
                            message=(
                                f"Credit report for {borrower_name} ({loan_number}) expires "
                                f"{credit_expire}. Order refresh immediately."
                            ),
                            link=f"/pipeline/loans/{loan_number}",
                            organization_id=organization_id,
                            gateway=gateway,
                        )
                        notifications += 1

        # ----- Process appraisal doc expiration -----
        if appraisal_days_raw is not None:
            appraisal_days = int(appraisal_days_raw)
            if 0 <= appraisal_days <= 30:
                priority, tier_label = _get_expiry_tier(appraisal_days)

                can_close_before = appraisal_days >= est_days_to_close

                if not _has_recent_task(db, loan_id, "appraisal expir", cooldown_hours=168 if appraisal_days > 14 else 72 if appraisal_days > 7 else 24):
                    cost_note = ""
                    if not can_close_before:
                        cost_note = (
                            f"\n\nESTIMATED REFRESH COST: ~$150-500 for appraisal update/recertification.\n"
                            f"Based on current stage ({stage}), estimated {est_days_to_close}d to close "
                            f"but appraisal expires in {appraisal_days}d. Refresh is REQUIRED.\n"
                            f"Note: Appraisal update (same appraiser) ~$150-200; "
                            f"new appraisal ~$400-500+."
                        )

                    _insert_task(
                        db,
                        title=f"Appraisal expiring [{tier_label}]: {borrower_name} — {appraisal_days}d remaining",
                        description=(
                            f"Appraisal for {borrower_name} ({loan_number}) expires {appraisal_expire}.\n"
                            f"Days remaining: {appraisal_days}\n"
                            f"Current stage: {stage}\n"
                            f"Estimated days to close: {est_days_to_close}\n"
                            f"Can close before expiry: {'YES' if can_close_before else 'NO — refresh needed'}\n"
                            f"Loan amount: ${loan_amount:,.2f}"
                            f"{cost_note}\n\n"
                            f"Action: {'Monitor — on track to close before expiry.' if can_close_before else 'Order appraisal update/recertification immediately.'}"
                        ),
                        assigned_to_id=lo_id,
                        loan_id=loan_id,
                        priority=priority,
                        due_date_expr=f"CURRENT_DATE + {max(0, appraisal_days - 3)}",
                        organization_id=organization_id,
                        gateway=gateway,
                    )
                    actions += 1
                    by_tier[priority] = by_tier.get(priority, 0) + 1

                    if lo_id:
                        lo_batches.setdefault(lo_id, []).append({
                            "type": "appraisal",
                            "loan_number": loan_number,
                            "borrower_name": borrower_name,
                            "days_left": appraisal_days,
                            "amount": loan_amount,
                        })

                    if appraisal_days <= 3 and lo_id:
                        _insert_notification(
                            db,
                            user_id=lo_id,
                            notification_type="appraisal_expiring",
                            title=f"CRITICAL: Appraisal expires in {appraisal_days}d — {borrower_name}",
                            message=(
                                f"Appraisal for {borrower_name} ({loan_number}) expires "
                                f"{appraisal_expire}. Order refresh immediately."
                            ),
                            link=f"/pipeline/loans/{loan_number}",
                            organization_id=organization_id,
                            gateway=gateway,
                        )
                        notifications += 1

    # ----- Create LO batch summary tasks for LOs with 2+ expiring docs -----
    batch_tasks = 0
    for lo_id, items in lo_batches.items():
        if len(items) < 2:
            continue

        if _has_recent_task(db, 0, f"batch doc refresh LO:{lo_id}", cooldown_hours=168):
            # Use loan_id=0 check is not ideal; check by title pattern across org
            existing = db.execute(text("""
                SELECT id FROM tasks
                WHERE organization_id = :org_id
                  AND title LIKE :pattern
                  AND created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
                LIMIT 1
            """), {"org_id": organization_id, "pattern": f"%batch doc refresh LO:{lo_id}%"}).fetchone()
            if existing:
                continue

        items_sorted = sorted(items, key=lambda x: x["days_left"])
        item_lines = "\n".join(
            f"  - [{it['type'].upper()}] {it['borrower_name']} ({it['loan_number']}) "
            f"— {it['days_left']}d left, ${it['amount']:,.2f}"
            for it in items_sorted
        )
        batch_total = sum(it["amount"] for it in items)

        _insert_task(
            db,
            title=f"[batch doc refresh LO:{lo_id}] {len(items)} docs expiring — ${batch_total:,.0f} exposure",
            description=(
                f"You have {len(items)} documents expiring within 30 days:\n\n"
                f"{item_lines}\n\n"
                f"Total pipeline exposure: ${batch_total:,.2f}\n\n"
                f"Consider ordering all refreshes in a single batch for efficiency. "
                f"Contact your credit vendor for bulk pricing."
            ),
            assigned_to_id=lo_id,
            priority="high" if any(it["days_left"] <= 7 for it in items) else "medium",
            due_date_expr="CURRENT_DATE + 1",
            organization_id=organization_id,
            gateway=gateway,
        )
        batch_tasks += 1
        actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Credit refresh commit failed: %s", e)

    return {
        "summary": (
            f"{len(expiring)} loans with expiring docs, {actions} tasks created "
            f"(critical={by_tier['critical']}, high={by_tier['high']}, "
            f"medium={by_tier['medium']}), ${total_exposure:,.0f} exposure"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications,
        "loans_with_expiring_docs": len(expiring),
        "by_tier": by_tier,
        "total_exposure": round(total_exposure, 2),
        "lo_batch_tasks": batch_tasks,
        "los_with_multiple_expiring": len([lo for lo, items in lo_batches.items() if len(items) >= 2]),
    }
