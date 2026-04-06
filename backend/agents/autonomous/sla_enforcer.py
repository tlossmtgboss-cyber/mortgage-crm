"""
SLA Enforcer Agent

Runs every 30 minutes.
Monitors stage-to-stage transition times against SLA targets.
Proactive escalation at multiple thresholds:
  - 50% SLA elapsed  → "watch"    → notify processor + LO
  - 75% SLA elapsed  → "at_risk"  → notify processor + LO + branch_manager
  - 100% SLA elapsed → "breach"   → notify all above + admin
  - 100% + disclosure deadline within 24h → "critical" → same as breach, priority critical
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Stage SLA targets (business days a loan should spend in each stage)
# --------------------------------------------------------------------------- #
SLA_TARGETS_DAYS = {
    "APPLICATION": 3,
    "DISCLOSED": 7,
    "PROCESSING": 7,
    "SUBMITTED": 2,
    "UNDERWRITING": 5,
    "UW_RECEIVED": 5,
    "CONDITIONAL_APPROVAL": 5,
    "APPROVED": 3,
    "CTC": 3,
    "CLEAR_TO_CLOSE": 3,
    "DOCS": 3,
    "DOCS_OUT": 5,
}

# --------------------------------------------------------------------------- #
# Multi-threshold escalation matrix
# --------------------------------------------------------------------------- #
# Each threshold defines:
#   pct        – fraction of SLA target that triggers the level
#   notify     – role keys to notify (resolved to real user IDs at runtime)
#   priority   – task/notification priority
#   condition  – optional extra condition that must also be true
ESCALATION_THRESHOLDS = {
    "on_track": {"pct": 0.0, "notify": [], "priority": "low"},
    "watch": {"pct": 0.50, "notify": ["processor", "lo"], "priority": "medium"},
    "at_risk": {"pct": 0.75, "notify": ["processor", "lo", "branch_manager"], "priority": "high"},
    "breach": {"pct": 1.00, "notify": ["processor", "lo", "branch_manager", "admin"], "priority": "critical"},
    "critical": {
        "pct": 1.00,
        "notify": ["processor", "lo", "branch_manager", "admin"],
        "priority": "critical",
        "condition": "disclosure_deadline_within_24h",
    },
}

# Ordered from most severe to least so we can pick the highest matching level
_THRESHOLD_ORDER = ["critical", "breach", "at_risk", "watch", "on_track"]

# Stages where a disclosure deadline is relevant (LE must be sent within 3 biz days)
_DISCLOSURE_RELEVANT_STAGES = {"APPLICATION", "DISCLOSED"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _classify_loan(
    days_in_stage: float,
    sla_days: int,
    has_disclosure_pressure: bool,
) -> str:
    """Return the highest escalation level this loan qualifies for."""
    pct_elapsed = days_in_stage / sla_days if sla_days else 0.0

    for level in _THRESHOLD_ORDER:
        cfg = ESCALATION_THRESHOLDS[level]
        if pct_elapsed < cfg["pct"]:
            continue
        # Extra condition gate
        condition = cfg.get("condition")
        if condition == "disclosure_deadline_within_24h" and not has_disclosure_pressure:
            continue
        return level

    return "on_track"


def _resolve_recipients(
    db: Session,
    organization_id: int,
    loan_officer_id: Optional[int],
    role_keys: List[str],
) -> List[int]:
    """Map abstract role keys to concrete user IDs for this loan/org."""
    user_ids: List[int] = []

    for role in role_keys:
        if role == "lo" and loan_officer_id:
            user_ids.append(loan_officer_id)
        elif role == "processor" and loan_officer_id:
            # Processor is stored as a name on the loan, not a FK.
            # Fall back to LO so the notification is not lost.
            user_ids.append(loan_officer_id)
        elif role == "branch_manager":
            row = db.execute(text("""
                SELECT u.id FROM users u
                WHERE u.organization_id = :org_id
                  AND u.role IN ('branch_manager', 'manager')
                  AND u.is_active = true
                ORDER BY CASE u.role WHEN 'branch_manager' THEN 1 ELSE 2 END
                LIMIT 1
            """), {"org_id": organization_id}).fetchone()
            if row:
                user_ids.append(row[0])
        elif role == "admin":
            row = db.execute(text("""
                SELECT u.id FROM users u
                WHERE u.organization_id = :org_id
                  AND u.role = 'admin'
                  AND u.is_active = true
                LIMIT 1
            """), {"org_id": organization_id}).fetchone()
            if row:
                user_ids.append(row[0])

    # Deduplicate while preserving order
    seen: set = set()
    unique: List[int] = []
    for uid in user_ids:
        if uid not in seen:
            seen.add(uid)
            unique.append(uid)
    return unique


def _already_notified_at_level(
    db: Session,
    loan_id: int,
    level: str,
    cooldown_hours: int = 12,
) -> bool:
    """Check whether a notification/task already exists for this loan+level
    within the cooldown window so we don't spam."""
    tag = f"SLA {level}"
    row = db.execute(text("""
        SELECT id FROM tasks
        WHERE loan_id = :loan_id
          AND title LIKE :tag
          AND created_at > CURRENT_TIMESTAMP - MAKE_INTERVAL(hours => :hours)
        LIMIT 1
    """), {"loan_id": str(loan_id), "tag": f"%{tag}%", "hours": cooldown_hours}).fetchone()
    return row is not None


def _create_task(
    db: Session,
    organization_id: int,
    loan_id: int,
    assigned_to_id: int,
    title: str,
    description: str,
    priority: str,
) -> None:
    """Insert a task record for the SLA escalation."""
    db.execute(text("""
        INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                           priority, status, due_date, created_at, organization_id)
        VALUES (:title, :desc, :assigned, :loan_id,
                :priority, 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
    """), {
        "title": title,
        "desc": description,
        "assigned": str(assigned_to_id),
        "loan_id": str(loan_id),
        "priority": priority,
        "org_id": organization_id,
    })


def _send_notification(
    db: Session,
    organization_id: int,
    user_id: int,
    level: str,
    loan_number: str,
    borrower_name: str,
    stage: str,
    days: int,
    sla: int,
) -> None:
    """Insert an in-app notification for a single recipient."""
    level_labels = {
        "watch": "SLA Watch",
        "at_risk": "SLA At Risk",
        "breach": "SLA Breach",
        "critical": "SLA Critical",
    }
    label = level_labels.get(level, f"SLA {level}")
    pct = int((days / sla) * 100) if sla else 0

    db.execute(text("""
        INSERT INTO notifications
            (user_id, organization_id, type, title, message, link, is_read, created_at)
        VALUES
            (:uid, :org_id, 'sla_warning', :title, :message, :link, false, NOW())
    """), {
        "uid": user_id,
        "org_id": organization_id,
        "title": f"{label}: {borrower_name}",
        "message": (
            f"Loan {loan_number} ({borrower_name}) has been in {stage} "
            f"for {days}d — {pct}% of the {sla}d SLA target."
        ),
        "link": f"/pipeline/loans/{loan_number}",
    })


# --------------------------------------------------------------------------- #
# Main agent
# --------------------------------------------------------------------------- #

@autonomous_agent(
    name="sla_enforcer",
    description="Proactive SLA monitoring with multi-threshold escalation (watch → at_risk → breach → critical)",
    frequency=AgentFrequency.EVERY_30_MIN,
    max_runtime_seconds=60,
)
def sla_enforcer(
    db: Session,
    organization_id: int,
    org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Monitor every active loan against stage SLA targets and escalate
    progressively at 50%, 75%, and 100% thresholds.  A special 'critical'
    level fires when a breached loan also has a disclosure deadline within
    24 hours."""

    # ------------------------------------------------------------------ #
    # 1.  Fetch all active loans with time-in-stage and disclosure dates
    # ------------------------------------------------------------------ #
    loans = db.execute(text("""
        SELECT l.id,
               l.loan_number,
               l.borrower_name,
               l.stage,
               l.loan_officer_id,
               CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
               EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400.0 AS days_in_stage,
               l.initial_disclosures_sent_date,
               l.created_at AS loan_created_at
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN (
              'FUNDED', 'CANCELLED', 'DENIED', 'DEAD',
              'WITHDRAWN', 'DOES_NOT_QUALIFY', 'NURTURE'
          )
          AND l.stage_changed_at IS NOT NULL
    """), {"org_id": organization_id}).fetchall()

    # Counters for the summary
    actions = 0
    notifications_sent = 0
    by_level: Dict[str, int] = {"watch": 0, "at_risk": 0, "breach": 0, "critical": 0}

    # ------------------------------------------------------------------ #
    # 2.  Evaluate each loan against SLA thresholds
    # ------------------------------------------------------------------ #
    for loan in loans:
        loan_id = loan[0]
        loan_number = loan[1]
        borrower_name = loan[2] or "Unknown"
        stage = loan[3]
        lo_id = loan[4]
        lo_name = loan[5] or "Unassigned"
        days_in_stage = float(loan[6] or 0)
        disclosures_sent_date = loan[7]
        loan_created_at = loan[8]

        sla = SLA_TARGETS_DAYS.get(stage)
        if not sla:
            continue

        # Determine whether disclosure deadline pressure exists.
        # TRID requires initial disclosures within 3 business days of application.
        has_disclosure_pressure = False
        if stage in _DISCLOSURE_RELEVANT_STAGES and disclosures_sent_date is None and loan_created_at:
            # Approximate 3 business days as ~4.2 calendar days
            deadline_approx = loan_created_at + timedelta(days=4.2)
            now = datetime.now(timezone.utc)
            # Make deadline_approx tz-aware if loan_created_at was naive
            if deadline_approx.tzinfo is None:
                deadline_approx = deadline_approx.replace(tzinfo=timezone.utc)
            if (deadline_approx - now).total_seconds() < 86400:  # within 24h
                has_disclosure_pressure = True

        level = _classify_loan(days_in_stage, sla, has_disclosure_pressure)
        if level == "on_track":
            continue

        # Skip if already notified at this level within the cooldown window
        if _already_notified_at_level(db, loan_id, level):
            continue

        # ------------------------------------------------------------------ #
        # 3.  Resolve recipients and create task + notifications
        # ------------------------------------------------------------------ #
        cfg = ESCALATION_THRESHOLDS[level]
        recipients = _resolve_recipients(db, organization_id, lo_id, cfg["notify"])
        if not recipients:
            logger.warning(
                "SLA enforcer: no recipients resolved for loan %s level %s",
                loan_number, level,
            )
            continue

        days_int = int(days_in_stage)
        pct = int((days_in_stage / sla) * 100)
        priority = cfg["priority"]

        level_label = {
            "watch": "SLA watch (50%)",
            "at_risk": "SLA at-risk (75%)",
            "breach": "SLA breach (100%)",
            "critical": "SLA critical — disclosure deadline imminent",
        }.get(level, f"SLA {level}")

        title = f"SLA {level}: {borrower_name} — {days_int}d in {stage} ({pct}%)"
        description = (
            f"Loan {loan_number} ({borrower_name}) has been in {stage} for "
            f"{days_int} days, which is {pct}% of the {sla}-day SLA target. "
            f"LO: {lo_name}. Escalation level: {level_label}."
        )
        if has_disclosure_pressure:
            description += (
                " WARNING: Initial disclosures have NOT been sent and the "
                "TRID 3-business-day deadline is within 24 hours."
            )

        # Assign the task to the first (most relevant) recipient
        _create_task(
            db, organization_id, loan_id, recipients[0],
            title, description, priority,
        )
        actions += 1

        # Send in-app notifications to all recipients
        for uid in recipients:
            try:
                _send_notification(
                    db, organization_id, uid, level,
                    loan_number, borrower_name, stage,
                    days_int, sla,
                )
                notifications_sent += 1
            except Exception as e:
                logger.error(
                    "SLA enforcer: notification insert failed for user %s loan %s: %s",
                    uid, loan_number, e,
                )

        by_level[level] = by_level.get(level, 0) + 1

    # ------------------------------------------------------------------ #
    # 4.  Commit
    # ------------------------------------------------------------------ #
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("SLA enforcer commit failed: %s", e)

    total_escalated = sum(by_level.values())
    return {
        "summary": (
            f"{total_escalated} loans escalated "
            f"(watch={by_level['watch']}, at_risk={by_level['at_risk']}, "
            f"breach={by_level['breach']}, critical={by_level['critical']})"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications_sent,
        "loans_reviewed": len(loans),
        "escalations": total_escalated,
        "by_level": by_level,
    }
