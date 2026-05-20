"""
Daily Operations Agents

Scheduled agents that run once or twice daily:
1. evening_recap — 6 PM daily end-of-day summary for each LO
2. daily_task_generator — 8 AM auto-create recurring standard tasks
3. rate_alert — 8 AM detect rate movements and notify LOs + borrowers
4. birthday_anniversary — 9 AM trigger birthday/home anniversary outreach
5. daily_metrics_snapshot — 9 PM capture daily metrics for trend analysis
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------
TERMINAL_STAGES = (
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN",
    "DOES_NOT_QUALIFY", "NURTURE",
)
_TERMINAL_SQL = "('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE')"
_ACTIVE_FILTER = f"l.stage NOT IN {_TERMINAL_SQL}"

# Loan stages ordered by pipeline progression (for velocity calculation)
PIPELINE_STAGE_ORDER = [
    "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
    "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED",
    "SUSPENDED", "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT",
]


def _safe_float(val, default: float = 0.0) -> float:
    """Safely coerce a DB value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default: int = 0) -> int:
    """Safely coerce a DB value to int."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# 1. Evening Recap
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="evening_recap",
    description="End-of-day pipeline recap and tomorrow's preview for each LO",
    frequency=AgentFrequency.DAILY_6PM,
    max_runtime_seconds=120,
)
def evening_recap(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """
    Comprehensive end-of-day recap per LO:
    - Win/loss metrics (funded vs fallen-out today)
    - Stage progressions that occurred today
    - Comparison to 30-day rolling average activity
    - Pipeline velocity (avg days-in-stage for active loans)
    - Detailed activity log for historical trending
    """
    actions = 0
    lo_details: List[Dict[str, Any]] = []

    # ── Fetch active LOs ──────────────────────────────────────────────────
    los = db.execute(text("""
        SELECT u.id, u.first_name, u.last_name, u.email
        FROM users u
        WHERE u.organization_id = :org_id AND u.is_active = true
          AND u.role IN ('loan_officer', 'manager', 'admin', 'branch_manager')
    """), {"org_id": organization_id}).fetchall()

    for lo in los:
        lo_id = lo[0]
        lo_name = f"{lo[1] or ''} {lo[2] or ''}".strip() or lo[3] or f"LO#{lo_id}"

        # ── Today's completed tasks ───────────────────────────────────────
        completed_tasks = _safe_int(db.execute(text("""
            SELECT COUNT(*) FROM tasks
            WHERE owner_id = :lo_id AND status = 'completed'
              AND updated_at >= CURRENT_DATE
              AND organization_id = :org_id
        """), {"lo_id": str(lo_id), "org_id": organization_id}).scalar())

        # ── Today's new leads ─────────────────────────────────────────────
        new_leads = _safe_int(db.execute(text("""
            SELECT COUNT(*) FROM leads
            WHERE owner_id = :lo_id AND created_at >= CURRENT_DATE
              AND organization_id = :org_id
        """), {"lo_id": str(lo_id), "org_id": organization_id}).scalar())

        # ── Loans funded today ────────────────────────────────────────────
        funded_today = db.execute(text("""
            SELECT l.id, l.loan_number, l.borrower_name, l.amount
            FROM loans l
            WHERE l.loan_officer_id = :lo_id AND l.stage = 'FUNDED'
              AND l.stage_changed_at >= CURRENT_DATE
              AND l.organization_id = :org_id
        """), {"lo_id": str(lo_id), "org_id": organization_id}).fetchall()

        funded_count = len(funded_today)
        funded_volume = sum(_safe_float(r[3]) for r in funded_today)

        # ── Loans fallen out today ────────────────────────────────────────
        fallen_out = db.execute(text("""
            SELECT l.id, l.loan_number, l.borrower_name, l.stage
            FROM loans l
            WHERE l.loan_officer_id = :lo_id
              AND l.stage IN ('CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
              AND l.stage_changed_at >= CURRENT_DATE
              AND l.organization_id = :org_id
        """), {"lo_id": str(lo_id), "org_id": organization_id}).fetchall()

        fallen_count = len(fallen_out)

        # ── Stage progressions today ──────────────────────────────────────
        stage_progressions = db.execute(text("""
            SELECT sh.from_stage, sh.to_stage, l.loan_number, l.borrower_name
            FROM stage_history sh
            JOIN loans l ON l.id = sh.loan_id
            WHERE sh.changed_at >= CURRENT_DATE
              AND l.loan_officer_id = :lo_id
              AND sh.entity_type = 'loan'
              AND sh.organization_id = :org_id
            ORDER BY sh.changed_at
        """), {"lo_id": str(lo_id), "org_id": organization_id}).fetchall()

        progression_count = len(stage_progressions)
        progression_details = [
            f"{r[2]} ({r[3]}): {r[0] or 'NEW'} -> {r[1]}"
            for r in stage_progressions[:10]  # cap detail lines
        ]

        # ── 30-day rolling average ────────────────────────────────────────
        rolling_avg = db.execute(text("""
            SELECT
                COALESCE(AVG(daily_tasks), 0) AS avg_tasks,
                COALESCE(AVG(daily_leads), 0) AS avg_leads,
                COALESCE(AVG(daily_funded), 0) AS avg_funded
            FROM (
                SELECT
                    d.dt::date AS day,
                    COUNT(DISTINCT t.id) AS daily_tasks,
                    COUNT(DISTINCT ld.id) AS daily_leads,
                    COUNT(DISTINCT ln.id) AS daily_funded
                FROM generate_series(
                    CURRENT_DATE - INTERVAL '30 days', CURRENT_DATE - INTERVAL '1 day', '1 day'
                ) AS d(dt)
                LEFT JOIN tasks t
                    ON t.owner_id = :lo_id
                    AND t.status = 'completed'
                    AND t.updated_at::date = d.dt::date
                    AND t.organization_id = :org_id
                LEFT JOIN leads ld
                    ON ld.owner_id = :lo_id
                    AND ld.created_at::date = d.dt::date
                    AND ld.organization_id = :org_id
                LEFT JOIN loans ln
                    ON ln.loan_officer_id = :lo_id
                    AND ln.stage = 'FUNDED'
                    AND ln.stage_changed_at::date = d.dt::date
                    AND ln.organization_id = :org_id
                GROUP BY d.dt::date
            ) daily_stats
        """), {"lo_id": str(lo_id), "org_id": organization_id}).fetchone()

        avg_tasks = round(_safe_float(rolling_avg[0]), 1) if rolling_avg else 0
        avg_leads = round(_safe_float(rolling_avg[1]), 1) if rolling_avg else 0
        avg_funded = round(_safe_float(rolling_avg[2]), 2) if rolling_avg else 0

        # ── Pipeline velocity (avg days-in-stage for active loans) ────────
        velocity = db.execute(text("""
            SELECT l.stage,
                   COUNT(*) AS cnt,
                   AVG(EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.stage_changed_at))) AS avg_days
            FROM loans l
            WHERE l.loan_officer_id = :lo_id
              AND l.stage NOT IN (
                  'FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'
              )
              AND l.stage_changed_at IS NOT NULL
              AND l.organization_id = :org_id
            GROUP BY l.stage
            ORDER BY avg_days DESC
        """), {"lo_id": str(lo_id), "org_id": organization_id}).fetchall()

        velocity_lines = [
            f"  {r[0]}: {_safe_int(r[1])} loans, avg {_safe_float(r[2]):.1f}d"
            for r in velocity
        ]

        # ── Tomorrow's appointments ───────────────────────────────────────
        tomorrow_appts = _safe_int(db.execute(text("""
            SELECT COUNT(*) FROM scheduler_appointments
            WHERE assigned_user_id = :lo_id
              AND scheduled_start >= CURRENT_DATE + 1
              AND scheduled_start < CURRENT_DATE + 2
              AND status NOT IN ('cancelled','no_show','rescheduled')
              AND organization_id = :org_id
        """), {"lo_id": str(lo_id), "org_id": organization_id}).scalar())

        # ── Skip LOs with zero activity ───────────────────────────────────
        has_activity = (
            completed_tasks or new_leads or funded_count
            or fallen_count or progression_count
        )
        if not has_activity:
            continue

        # ── Build comparison strings ──────────────────────────────────────
        task_delta = completed_tasks - avg_tasks
        task_cmp = f"({'+' if task_delta >= 0 else ''}{task_delta:.0f} vs 30d avg {avg_tasks:.0f})"
        lead_delta = new_leads - avg_leads
        lead_cmp = f"({'+' if lead_delta >= 0 else ''}{lead_delta:.0f} vs avg {avg_leads:.0f})"

        # ── Build recap content ───────────────────────────────────────────
        lines = [f"Evening recap for {lo_name}:"]
        lines.append(f"  Tasks completed: {completed_tasks} {task_cmp}")
        lines.append(f"  New leads: {new_leads} {lead_cmp}")
        lines.append(f"  Funded today: {funded_count} (${funded_volume:,.0f})"
                      f"{' vs 30d avg ' + str(avg_funded) if avg_funded else ''}")
        if fallen_count:
            fallen_names = ", ".join(f"{r[2]} ({r[3]})" for r in fallen_out[:5])
            lines.append(f"  Fallen out: {fallen_count} — {fallen_names}")
        if progression_details:
            lines.append(f"  Stage progressions ({progression_count}):")
            for p in progression_details:
                lines.append(f"    {p}")
        if velocity_lines:
            lines.append("  Pipeline velocity:")
            lines.extend(velocity_lines)
        lines.append(f"  Tomorrow: {tomorrow_appts} appointments")

        recap_content = "\n".join(lines)

        # ── Store structured recap as activity ────────────────────────────
        recap_json = json.dumps({
            "agent": "evening_recap",
            "lo_id": lo_id,
            "lo_name": lo_name,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "tasks_completed": completed_tasks,
            "new_leads": new_leads,
            "funded_count": funded_count,
            "funded_volume": funded_volume,
            "fallen_out_count": fallen_count,
            "stage_progressions": progression_count,
            "avg_30d_tasks": avg_tasks,
            "avg_30d_leads": avg_leads,
            "avg_30d_funded": avg_funded,
            "velocity": {r[0]: {"count": _safe_int(r[1]), "avg_days": round(_safe_float(r[2]), 1)} for r in velocity},
            "tomorrow_appts": tomorrow_appts,
        })

        _recap_content = recap_content
        _recap_json = recap_json
        def _do_recap_activity(c=_recap_content, m=_recap_json):
            db.execute(text("""
                INSERT INTO activities (lead_id, type, content, user_metadata, created_at, organization_id)
                VALUES (NULL, 'Note', :content, :metadata, CURRENT_TIMESTAMP, :org_id)
            """), {
                "content": c,
                "metadata": m,
                "org_id": organization_id,
            })
        if gateway:
            gateway.propose(
                "create_activity", _do_recap_activity,
                target_entity=None, target_id=None,
                description=f"Evening recap for LO {lo_name}"[:200],
                payload={"content": _recap_content, "metadata": _recap_json, "org_id": organization_id},
            )
        else:
            _do_recap_activity()

        lo_details.append({
            "lo_id": lo_id,
            "lo_name": lo_name,
            "funded": funded_count,
            "fallen_out": fallen_count,
            "progressions": progression_count,
        })
        actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("evening_recap commit failed org=%s: %s", organization_id, e)
        raise

    return {
        "summary": f"Recapped {actions} LOs: {sum(d['funded'] for d in lo_details)} funded, "
                   f"{sum(d['fallen_out'] for d in lo_details)} fallen out",
        "actions_taken": actions,
        "notifications_sent": 0,
        "lo_details": lo_details,
    }


# ---------------------------------------------------------------------------
# 2. Daily Task Generator
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="daily_task_generator",
    description="Auto-create standard recurring daily tasks for LOs",
    frequency=AgentFrequency.DAILY_8AM,
    max_runtime_seconds=60,
)
def daily_task_generator(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """
    Generate pipeline-aware, stage-specific tasks:
    - Loans stuck 3+ days in UNDERWRITING/PROCESSING -> call UW/processor
    - APPLICATION-stage loans missing documents -> doc collection tasks
    - Follow-up tasks for completed appointments with no next action
    - Prioritized by loan amount and days in stage
    - Skips LOs who are out of office today
    """
    actions = 0
    skipped_ooo = 0

    # ── Detect LOs who are out of office today ────────────────────────────
    ooo_lo_ids: set = set()
    try:
        ooo_rows = db.execute(text("""
            SELECT DISTINCT sa.assigned_user_id
            FROM scheduler_appointments sa
            WHERE sa.organization_id = :org_id
              AND sa.scheduled_start <= CURRENT_DATE + 1
              AND sa.scheduled_end >= CURRENT_DATE
              AND sa.status NOT IN ('cancelled', 'rescheduled')
              AND (
                  LOWER(sa.title) LIKE '%out of office%'
                  OR LOWER(sa.title) LIKE '%ooo%'
                  OR LOWER(sa.title) LIKE '%pto%'
                  OR LOWER(sa.title) LIKE '%vacation%'
                  OR LOWER(sa.title) LIKE '%day off%'
                  OR (
                      sa.duration_minutes >= 420
                      AND LOWER(sa.title) LIKE '%off%'
                  )
              )
        """), {"org_id": organization_id}).fetchall()
        ooo_lo_ids = {r[0] for r in ooo_rows if r[0] is not None}
    except Exception as e:
        logger.warning("daily_task_generator: OOO detection failed: %s", e)

    def _lo_is_available(lo_id: int) -> bool:
        if lo_id in ooo_lo_ids:
            return False
        return True

    # ── Helper: check for duplicate task today ────────────────────────────
    def _task_exists_today(lo_id: int, title_pattern: str, loan_id: int = None) -> bool:
        params: Dict[str, Any] = {"lo_id": str(lo_id), "pattern": title_pattern, "org_id": organization_id}
        loan_clause = ""
        if loan_id is not None:
            loan_clause = "AND loan_id = :loan_id"
            params["loan_id"] = str(loan_id)
        row = db.execute(text(f"""
            SELECT id FROM tasks
            WHERE owner_id = :lo_id
              AND title LIKE :pattern
              AND created_at >= CURRENT_DATE
              AND organization_id = :org_id
              {loan_clause}
            LIMIT 1
        """), params).fetchone()
        return row is not None

    # ── 1. Loans stuck in processing/underwriting stages ──────────────────
    stuck_loans = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.stage, l.amount,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) AS days_in_stage,
               l.processor, l.underwriter
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage IN ('PROCESSING', 'SUBMITTED', 'UNDERWRITING', 'UW_RECEIVED',
                          'CONDITIONAL_APPROVAL', 'SUSPENDED')
          AND l.stage_changed_at IS NOT NULL
          AND EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) >= 3
          AND l.loan_officer_id IS NOT NULL
        ORDER BY l.amount DESC NULLS LAST, days_in_stage DESC
    """), {"org_id": organization_id}).fetchall()

    for loan in stuck_loans:
        lo_id = loan[3]
        if not _lo_is_available(lo_id):
            skipped_ooo += 1
            continue

        loan_id = loan[0]
        loan_num = loan[1] or "N/A"
        borrower = loan[2] or "Unknown"
        stage = loan[4]
        amount = _safe_float(loan[5])
        days = _safe_int(loan[6])
        processor = loan[7] or "processor"
        underwriter = loan[8] or "underwriter"

        # Stage-specific action verbiage
        if stage in ("UNDERWRITING", "UW_RECEIVED"):
            action = f"Call {underwriter} for status on UW conditions"
            title = f"UW follow-up: {borrower} ({loan_num}) — {days}d in {stage}"
        elif stage == "CONDITIONAL_APPROVAL":
            action = f"Review outstanding conditions and push {processor} for clear-to-close"
            title = f"Conditions follow-up: {borrower} ({loan_num}) — {days}d"
        elif stage == "SUSPENDED":
            action = f"Escalate suspension: contact {underwriter} to identify resolution path"
            title = f"Suspended loan: {borrower} ({loan_num}) — {days}d"
        else:  # PROCESSING, SUBMITTED
            action = f"Check with {processor} on file progress and outstanding items"
            title = f"Processing check: {borrower} ({loan_num}) — {days}d in {stage}"

        priority = "high" if days >= 7 or amount >= 500000 else "medium"

        if not _task_exists_today(lo_id, f"%{loan_num}%", loan_id):
            _t, _d, _li, _lid, _p = title[:255], f"${amount:,.0f} loan — {days} days in {stage}. Action: {action}", str(lo_id), str(loan_id), priority
            def _do_pipeline_task(t=_t, d=_d, li=_li, lid=_lid, p=_p):
                db.execute(text("""
                    INSERT INTO tasks (title, description, owner_id, loan_id,
                                       priority, status, due_date, created_at, organization_id)
                    VALUES (:title, :desc, :lo_id, :loan_id,
                            :priority, 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
                """), {
                    "title": t, "desc": d, "lo_id": li,
                    "loan_id": lid, "priority": p, "org_id": organization_id,
                })
            if gateway:
                gateway.propose("create_task", _do_pipeline_task,
                    target_entity="loan", target_id=str(loan_id),
                    description=title[:200],
                    payload={"title": _t, "desc": _d, "lo_id": _li, "loan_id": _lid, "priority": _p, "org_id": organization_id})
            else:
                _do_pipeline_task()
            actions += 1

    # ── 2. APPLICATION-stage loans potentially missing documents ──────────
    app_loans = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.amount,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) AS days_in_stage,
               (SELECT COUNT(*) FROM documents d
                WHERE d.loan_id = l.id AND d.status = 'active'
                  AND d.organization_id = :org_id) AS doc_count
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage = 'APPLICATION'
          AND l.loan_officer_id IS NOT NULL
          AND l.stage_changed_at IS NOT NULL
          AND EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) >= 2
        ORDER BY l.amount DESC NULLS LAST
    """), {"org_id": organization_id}).fetchall()

    for loan in app_loans:
        lo_id = loan[3]
        if not _lo_is_available(lo_id):
            skipped_ooo += 1
            continue

        loan_id = loan[0]
        loan_num = loan[1] or "N/A"
        borrower = loan[2] or "Unknown"
        amount = _safe_float(loan[4])
        days = _safe_int(loan[5])
        doc_count = _safe_int(loan[6])

        # A typical mortgage needs ~8-12 document categories; flag if low
        if doc_count < 4:
            title = f"Collect docs: {borrower} ({loan_num}) — {doc_count} docs on file"
            desc = (
                f"${amount:,.0f} loan in APPLICATION for {days}d with only {doc_count} documents. "
                "Typical requirement: paystubs, W-2s, tax returns, bank statements, ID, "
                "purchase agreement. Contact borrower to complete file."
            )
            priority = "high" if days >= 5 else "medium"

            if not _task_exists_today(lo_id, f"%Collect docs%{loan_num}%", loan_id):
                _ct, _cd, _cli, _clid, _cp = title[:255], desc, str(lo_id), str(loan_id), priority
                def _do_collect_docs(t=_ct, d=_cd, li=_cli, lid=_clid, p=_cp):
                    db.execute(text("""
                        INSERT INTO tasks (title, description, owner_id, loan_id,
                                           priority, status, due_date, created_at, organization_id)
                        VALUES (:title, :desc, :lo_id, :loan_id,
                                :priority, 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
                    """), {
                        "title": t, "desc": d, "lo_id": li,
                        "loan_id": lid, "priority": p, "org_id": organization_id,
                    })
                if gateway:
                    gateway.propose("create_task", _do_collect_docs,
                        target_entity="loan", target_id=str(loan_id),
                        description=title[:200],
                        payload={"title": _ct, "desc": _cd, "lo_id": _cli, "loan_id": _clid, "priority": _cp, "org_id": organization_id})
                else:
                    _do_collect_docs()
                actions += 1

    # ── 3. Follow-up tasks for completed appointments with no next action ─
    yesterday_appts = db.execute(text("""
        SELECT sa.id, sa.assigned_user_id, sa.lead_id, sa.loan_id,
               sa.title AS appt_title, sa.attendee_name, sa.attendee_email
        FROM scheduler_appointments sa
        WHERE sa.organization_id = :org_id
          AND sa.status = 'completed'
          AND sa.completed_at >= CURRENT_DATE - 1
          AND sa.completed_at < CURRENT_DATE
          AND sa.assigned_user_id IS NOT NULL
    """), {"org_id": organization_id}).fetchall()

    for appt in yesterday_appts:
        lo_id = appt[1]
        if not _lo_is_available(lo_id):
            skipped_ooo += 1
            continue

        appt_id = appt[0]
        lead_id = appt[2]
        loan_id = appt[3]
        appt_title = appt[4] or "appointment"
        attendee = appt[5] or appt[6] or "attendee"

        # Check if there's already a follow-up task or a new appointment
        has_followup = db.execute(text("""
            SELECT id FROM tasks
            WHERE owner_id = :lo_id
              AND (lead_id = :lead_id OR loan_id = :loan_id)
              AND created_at >= CURRENT_DATE - 1
              AND status = 'pending'
              AND organization_id = :org_id
            LIMIT 1
        """), {
            "lo_id": str(lo_id),
            "lead_id": str(lead_id) if lead_id else None,
            "loan_id": str(loan_id) if loan_id else None,
            "org_id": organization_id,
        }).fetchone()

        has_next_appt = db.execute(text("""
            SELECT id FROM scheduler_appointments
            WHERE assigned_user_id = :lo_id
              AND (lead_id = :lead_id OR loan_id = :loan_id)
              AND scheduled_start > CURRENT_TIMESTAMP
              AND status NOT IN ('cancelled', 'rescheduled')
              AND organization_id = :org_id
            LIMIT 1
        """), {
            "lo_id": str(lo_id),
            "lead_id": str(lead_id) if lead_id else None,
            "loan_id": str(loan_id) if loan_id else None,
            "org_id": organization_id,
        }).fetchone()

        if not has_followup and not has_next_appt:
            params: Dict[str, Any] = {
                "title": f"Follow up: {attendee} — post {appt_title}"[:255],
                "desc": (
                    f"Appointment #{appt_id} ('{appt_title}') completed yesterday with {attendee}. "
                    "No follow-up task or next appointment found. Send recap email, schedule next step, "
                    "or update pipeline status."
                ),
                "lo_id": str(lo_id),
                "org_id": organization_id,
            }
            lead_col = ", lead_id" if lead_id else ""
            lead_val = ", :lead_id" if lead_id else ""
            loan_col = ", loan_id" if loan_id else ""
            loan_val = ", :loan_id" if loan_id else ""
            if lead_id:
                params["lead_id"] = str(lead_id)
            if loan_id:
                params["loan_id"] = str(loan_id)

            _sql = f"""
                INSERT INTO tasks (title, description, owner_id{lead_col}{loan_col},
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id{lead_val}{loan_val},
                        'medium', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """
            _params = dict(params)
            def _do_overdue_task(s=_sql, p=_params):
                db.execute(text(s), p)
            if gateway:
                gateway.propose("create_task", _do_overdue_task,
                    target_entity="lead" if lead_id else ("loan" if loan_id else None),
                    target_id=str(lead_id or loan_id) if (lead_id or loan_id) else None,
                    description=params["title"][:200],
                    payload=_params)
            else:
                _do_overdue_task()
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("daily_task_generator commit failed org=%s: %s", organization_id, e)
        raise

    return {
        "summary": f"Created {actions} tasks, skipped {skipped_ooo} (OOO)",
        "actions_taken": actions,
        "notifications_sent": 0,
        "skipped_out_of_office": skipped_ooo,
    }


# ---------------------------------------------------------------------------
# 3. Rate Alert Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="rate_alert",
    description="Detect rate movements and notify LOs with affected borrowers",
    frequency=AgentFrequency.DAILY_8AM,
    max_runtime_seconds=90,
)
def rate_alert(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """
    Rate-sensitive pipeline analysis:
    - Floating loans grouped by program (Conventional, FHA, VA, etc.)
    - Estimated monthly payment impact of rate changes
    - Locks expiring within 7 days that may need renegotiation
    - Priority-ranked tasks with specific rate and payment data
    - Activity log with rate environment context
    """
    actions = 0
    floating_count = 0
    expiring_count = 0

    # ── 1. Find floating loans (no lock, active pipeline) ─────────────────
    floating = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.amount, l.loan_type, l.program, l.term, l.rate,
               l.stage, l.monthly_payment, l.purchase_price
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.lock_expiration_date IS NULL
          AND (l.rate IS NULL OR l.rate = 0)
          AND l.stage NOT IN (
              'FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN',
              'DOES_NOT_QUALIFY','APPLICATION'
          )
          AND l.loan_officer_id IS NOT NULL
        ORDER BY l.amount DESC NULLS LAST
    """), {"org_id": organization_id}).fetchall()

    floating_count = len(floating)

    # Group floating loans by LO, then by program
    lo_floating: Dict[int, Dict[str, List]] = {}
    for loan in floating:
        lo_id = loan[3]
        program = (loan[6] or loan[5] or "Unknown").strip()
        if lo_id not in lo_floating:
            lo_floating[lo_id] = {}
        if program not in lo_floating[lo_id]:
            lo_floating[lo_id][program] = []
        lo_floating[lo_id][program].append({
            "id": loan[0],
            "loan_number": loan[1],
            "borrower": loan[2],
            "amount": _safe_float(loan[4]),
            "term": _safe_int(loan[7], 360),
            "stage": loan[9],
            "monthly_payment": _safe_float(loan[10]),
        })

    # Create tasks per LO with program-specific detail
    for lo_id, programs in lo_floating.items():
        total_floating = sum(len(loans) for loans in programs.values())
        total_volume = sum(l["amount"] for loans in programs.values() for l in loans)

        # Build description with per-program breakdown
        desc_lines = [
            f"You have {total_floating} floating loan(s) totaling ${total_volume:,.0f}.",
            "Review lock strategy by program:",
            "",
        ]
        for prog, loans in sorted(programs.items()):
            prog_volume = sum(l["amount"] for l in loans)
            desc_lines.append(f"  {prog} ({len(loans)} loans, ${prog_volume:,.0f}):")
            for l in loans[:5]:
                # Estimate monthly P&I impact of 0.25% rate increase
                # Simple approximation: (amount * 0.0025) / 12
                rate_impact_monthly = (l["amount"] * 0.0025) / 12
                desc_lines.append(
                    f"    - {l['borrower']} ({l['loan_number']}): "
                    f"${l['amount']:,.0f}, {l['stage']}"
                    f" | +0.25% = ~${rate_impact_monthly:,.0f}/mo more"
                )
            if len(loans) > 5:
                desc_lines.append(f"    ... and {len(loans) - 5} more")
            desc_lines.append("")

        priority = "high" if total_volume >= 1_000_000 or total_floating >= 5 else "medium"

        # Deduplication check
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE owner_id = :lo_id AND title LIKE '%Rate review%floating%'
              AND created_at >= CURRENT_DATE
              AND organization_id = :org_id
            LIMIT 1
        """), {"lo_id": str(lo_id), "org_id": organization_id}).fetchone()

        if not existing:
            _rt = f"Rate review: {total_floating} floating loan(s), ${total_volume:,.0f}"[:255]
            _rd = "\n".join(desc_lines)
            _rli = str(lo_id)
            _rp = priority
            def _do_rate_review(t=_rt, d=_rd, li=_rli, p=_rp):
                db.execute(text("""
                    INSERT INTO tasks (title, description, owner_id,
                                       priority, status, due_date, created_at, organization_id)
                    VALUES (:title, :desc, :lo_id,
                            :priority, 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
                """), {"title": t, "desc": d, "lo_id": li, "priority": p, "org_id": organization_id})
            if gateway:
                gateway.propose("create_task", _do_rate_review,
                    target_entity=None, target_id=None, description=_rt[:200],
                    payload={"title": _rt, "desc": _rd, "lo_id": _rli, "priority": _rp, "org_id": organization_id})
            else:
                _do_rate_review()
            actions += 1

    # ── 2. Locks expiring within 7 days ───────────────────────────────────
    expiring_locks = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.amount, l.rate, l.lock_expiration_date, l.loan_type,
               l.program, l.stage, l.monthly_payment, l.term
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.lock_expiration_date IS NOT NULL
          AND l.lock_expiration_date BETWEEN CURRENT_TIMESTAMP AND CURRENT_TIMESTAMP + INTERVAL '7 days'
          AND l.stage NOT IN (
              'FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY'
          )
          AND l.loan_officer_id IS NOT NULL
        ORDER BY l.lock_expiration_date ASC
    """), {"org_id": organization_id}).fetchall()

    expiring_count = len(expiring_locks)

    # Group expiring locks by LO
    lo_expiring: Dict[int, List] = {}
    for loan in expiring_locks:
        lo_id = loan[3]
        if lo_id not in lo_expiring:
            lo_expiring[lo_id] = []
        lo_expiring[lo_id].append({
            "id": loan[0],
            "loan_number": loan[1],
            "borrower": loan[2],
            "amount": _safe_float(loan[4]),
            "rate": _safe_float(loan[5]),
            "lock_expires": str(loan[6])[:10] if loan[6] else "?",
            "program": loan[8] or loan[7] or "Unknown",
            "stage": loan[9],
        })

    for lo_id, loans in lo_expiring.items():
        desc_lines = [f"{len(loans)} lock(s) expiring within 7 days:"]
        for l in loans:
            desc_lines.append(
                f"  - {l['borrower']} ({l['loan_number']}): ${l['amount']:,.0f} at "
                f"{l['rate']:.3f}%, expires {l['lock_expires']}, {l['stage']} "
                f"[{l['program']}]"
            )
        desc_lines.append("")
        desc_lines.append(
            "Action: Evaluate extension cost vs renegotiation. "
            "If closing is imminent, extend. If rate environment improved, renegotiate."
        )

        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE owner_id = :lo_id AND title LIKE '%Lock expir%'
              AND created_at >= CURRENT_DATE
              AND organization_id = :org_id
            LIMIT 1
        """), {"lo_id": str(lo_id), "org_id": organization_id}).fetchone()

        if not existing:
            _lt = f"Lock expiring: {len(loans)} loan(s) within 7 days"[:255]
            _ld = "\n".join(desc_lines)
            _lli = str(lo_id)
            def _do_lock_expiry(t=_lt, d=_ld, li=_lli):
                db.execute(text("""
                    INSERT INTO tasks (title, description, owner_id,
                                       priority, status, due_date, created_at, organization_id)
                    VALUES (:title, :desc, :lo_id,
                            'high', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
                """), {"title": t, "desc": d, "lo_id": li, "org_id": organization_id})
            if gateway:
                gateway.propose("create_task", _do_lock_expiry,
                    target_entity=None, target_id=None, description=_lt[:200],
                    payload={"title": _lt, "desc": _ld, "lo_id": _lli, "org_id": organization_id})
            else:
                _do_lock_expiry()
            actions += 1

    # ── 3. Log rate environment activity ──────────────────────────────────
    rate_context = json.dumps({
        "agent": "rate_alert",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "floating_loans": floating_count,
        "floating_volume": sum(
            _safe_float(loan[4]) for loan in floating
        ),
        "expiring_locks": expiring_count,
        "by_program": {
            prog: len(loans)
            for programs in lo_floating.values()
            for prog, loans in programs.items()
        },
    })

    _rate_content = (
        f"Rate alert: {floating_count} floating loans, {expiring_count} locks expiring <7d. "
        f"Created {actions} tasks."
    )
    _rate_metadata = rate_context
    def _do_rate_activity(c=_rate_content, m=_rate_metadata):
        db.execute(text("""
            INSERT INTO activities (lead_id, type, content, user_metadata, created_at, organization_id)
            VALUES (NULL, 'Note', :content, :metadata, CURRENT_TIMESTAMP, :org_id)
        """), {"content": c, "metadata": m, "org_id": organization_id})
    if gateway:
        gateway.propose("create_activity", _do_rate_activity,
            target_entity=None, target_id=None, description=_rate_content[:200],
            payload={"content": _rate_content, "metadata": _rate_metadata, "org_id": organization_id})
    else:
        _do_rate_activity()

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("rate_alert commit failed org=%s: %s", organization_id, e)
        raise

    return {
        "summary": f"{floating_count} floating, {expiring_count} expiring locks, {actions} tasks created",
        "actions_taken": actions,
        "notifications_sent": 0,
        "floating_loans": floating_count,
        "expiring_locks": expiring_count,
    }


# ---------------------------------------------------------------------------
# 4. Birthday & Anniversary Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="birthday_anniversary",
    description="Trigger birthday and home anniversary outreach for borrowers",
    frequency=AgentFrequency.DAILY_9AM,
    max_runtime_seconds=60,
)
def birthday_anniversary(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """
    Outreach for funded borrowers:
    - Home closing anniversaries (1st, 2nd, 3rd, ...) with tailored messaging
    - Lead birthdays (if birth_date column exists — graceful skip otherwise)
    - Rough equity estimate (purchase price + 3%/yr appreciation - original loan)
    - Referral-ask talking points in task description
    - Activity log entries for CRM tracking
    """
    actions = 0
    anniversary_tasks = 0
    birthday_tasks = 0

    # ── 1. Closing anniversaries ──────────────────────────────────────────
    # Find loans funded on this calendar day in any prior year.
    # Use day-of-year match to handle month boundaries correctly.
    anniversaries = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
               l.borrower_phone, l.loan_officer_id, l.funded_date,
               l.amount, l.purchase_price, l.property_address,
               EXTRACT(YEAR FROM AGE(CURRENT_DATE, l.funded_date))::int AS years_since
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.funded_date IS NOT NULL
          AND EXTRACT(MONTH FROM l.funded_date) = EXTRACT(MONTH FROM CURRENT_DATE)
          AND EXTRACT(DAY FROM l.funded_date) = EXTRACT(DAY FROM CURRENT_DATE)
          AND l.funded_date < CURRENT_DATE - INTERVAL '180 days'
          AND l.loan_officer_id IS NOT NULL
    """), {"org_id": organization_id}).fetchall()

    for loan in anniversaries:
        loan_id = loan[0]
        loan_num = loan[1] or "N/A"
        borrower = loan[2] or "Unknown"
        borrower_email = loan[3]
        borrower_phone = loan[4]
        lo_id = loan[5]
        funded_date = loan[6]
        original_amount = _safe_float(loan[7])
        purchase_price = _safe_float(loan[8])
        address = loan[9] or "their home"
        years = _safe_int(loan[10], 1)

        # ── Deduplication ─────────────────────────────────────────────────
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id
              AND title LIKE '%anniversary%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '30 days'
              AND organization_id = :org_id
            LIMIT 1
        """), {"loan_id": str(loan_id), "org_id": organization_id}).fetchone()

        if existing:
            continue

        # ── Equity estimate ───────────────────────────────────────────────
        # Rough: purchase_price * (1.03 ^ years) - original_loan_amount
        base_value = purchase_price if purchase_price > 0 else original_amount * 1.25
        estimated_current_value = base_value * (1.03 ** years)
        estimated_equity = estimated_current_value - (original_amount * 0.95)  # rough principal paydown
        equity_str = f"~${max(estimated_equity, 0):,.0f}" if base_value > 0 else "N/A"

        # ── Year-specific messaging ───────────────────────────────────────
        ordinal = _ordinal(years)
        if years == 1:
            milestone_msg = "First year in the home! Check in on how they're settling in."
            referral_angle = (
                "They likely have friends who saw their new home and are thinking about buying. "
                "Ask: 'Has anyone mentioned wanting to buy or refinance since you moved in?'"
            )
        elif years <= 3:
            milestone_msg = f"{ordinal} anniversary. Great time for a home equity check-in."
            referral_angle = (
                f"With {equity_str} estimated equity, they may know others looking to buy. "
                "Ask: 'Any neighbors or coworkers talking about the housing market?'"
            )
        elif years <= 5:
            milestone_msg = f"{ordinal} anniversary. Potential refinance or HELOC candidate."
            referral_angle = (
                f"Estimated equity: {equity_str}. Position yourself for their next move. "
                "Ask: 'Are you thinking about renovations, or do you know someone looking to buy?'"
            )
        else:
            milestone_msg = f"{ordinal} anniversary. Long-term client — high referral value."
            referral_angle = (
                f"Estimated equity: {equity_str}. This client trusts you. "
                "Ask: 'I'd love to help anyone you know. Who's been talking about buying or refinancing?'"
            )

        contact_info = ""
        if borrower_phone:
            contact_info += f" Phone: {borrower_phone}."
        if borrower_email:
            contact_info += f" Email: {borrower_email}."

        title = f"{ordinal} home anniversary: {borrower}"
        desc = (
            f"{milestone_msg}\n\n"
            f"Loan: {loan_num} | Address: {address}\n"
            f"Original loan: ${original_amount:,.0f} | Est. current value: ${estimated_current_value:,.0f}\n"
            f"Estimated equity: {equity_str}\n\n"
            f"Referral ask:\n{referral_angle}\n\n"
            f"Contact:{contact_info}"
        )

        priority = "medium" if years <= 2 else "low"

        _at, _ad, _ali, _alid, _ap = title[:255], desc, str(lo_id), str(loan_id), priority
        def _do_anniv_task(t=_at, d=_ad, li=_ali, lid=_alid, p=_ap):
            db.execute(text("""
                INSERT INTO tasks (title, description, owner_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        :priority, 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {"title": t, "desc": d, "lo_id": li, "loan_id": lid, "priority": p, "org_id": organization_id})
        if gateway:
            gateway.propose("create_task", _do_anniv_task,
                target_entity="loan", target_id=str(loan_id), description=title[:200],
                payload={"title": _at, "desc": _ad, "lo_id": _ali, "loan_id": _alid, "priority": _ap, "org_id": organization_id})
        else:
            _do_anniv_task()

        # ── Activity log entry ────────────────────────────────────────────
        _anniv_content = f"{ordinal} home anniversary for {borrower} ({loan_num}). Task created for LO."
        _anniv_lid = str(loan_id)
        def _do_anniv_activity(c=_anniv_content, lid=_anniv_lid):
            db.execute(text("""
                INSERT INTO activities (loan_id, type, content, created_at, organization_id)
                VALUES (:loan_id, 'Note', :content, CURRENT_TIMESTAMP, :org_id)
            """), {"loan_id": lid, "content": c, "org_id": organization_id})
        if gateway:
            gateway.propose("create_activity", _do_anniv_activity,
                target_entity="loan", target_id=str(loan_id), description=_anniv_content[:200],
                payload={"loan_id": _anniv_lid, "content": _anniv_content, "org_id": organization_id})
        else:
            _do_anniv_activity()

        anniversary_tasks += 1
        actions += 1

    # ── 2. Lead birthdays (graceful skip if column doesn't exist) ─────────
    try:
        # Probe for the birth_date column on leads
        db.execute(text("""
            SELECT birth_date FROM leads WHERE false LIMIT 0
        """))

        birthdays = db.execute(text("""
            SELECT ld.id, ld.name, ld.email, ld.phone, ld.owner_id
            FROM leads ld
            WHERE ld.organization_id = :org_id
              AND ld.birth_date IS NOT NULL
              AND EXTRACT(MONTH FROM ld.birth_date) = EXTRACT(MONTH FROM CURRENT_DATE)
              AND EXTRACT(DAY FROM ld.birth_date) = EXTRACT(DAY FROM CURRENT_DATE)
              AND ld.owner_id IS NOT NULL
              AND ld.stage NOT IN ('Closed', 'Dead', 'Disqualified')
        """), {"org_id": organization_id}).fetchall()

        for lead in birthdays:
            lead_id = lead[0]
            lead_name = lead[1] or "Unknown"
            lead_email = lead[2]
            lead_phone = lead[3]
            lo_id = lead[4]

            existing = db.execute(text("""
                SELECT id FROM tasks
                WHERE lead_id = :lead_id AND title LIKE '%birthday%'
                  AND created_at > CURRENT_TIMESTAMP - INTERVAL '30 days'
                  AND organization_id = :org_id
                LIMIT 1
            """), {"lead_id": str(lead_id), "org_id": organization_id}).fetchone()

            if existing:
                continue

            contact = ""
            if lead_phone:
                contact += f" Phone: {lead_phone}."
            if lead_email:
                contact += f" Email: {lead_email}."

            _bt = f"Happy birthday: {lead_name}"[:255]
            _bd = (
                f"Today is {lead_name}'s birthday! Send a personal message.\n\n"
                f"Contact:{contact}\n\n"
                "Talking points: Wish them well, ask about any real estate plans for "
                "the year ahead, mention any rate improvements since you last spoke."
            )
            _bli = str(lo_id)
            _blid = str(lead_id)
            def _do_bday_task(t=_bt, d=_bd, li=_bli, lid=_blid):
                db.execute(text("""
                    INSERT INTO tasks (title, description, owner_id, lead_id,
                                       priority, status, due_date, created_at, organization_id)
                    VALUES (:title, :desc, :lo_id, :lead_id,
                            'low', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
                """), {"title": t, "desc": d, "lo_id": li, "lead_id": lid, "org_id": organization_id})
            if gateway:
                gateway.propose("create_task", _do_bday_task,
                    target_entity="lead", target_id=str(lead_id), description=_bt[:200],
                    payload={"title": _bt, "desc": _bd, "lo_id": _bli, "lead_id": _blid, "org_id": organization_id})
            else:
                _do_bday_task()

            _bday_content = f"Birthday outreach task created for {lead_name}."
            _bday_lid = str(lead_id)
            def _do_bday_activity(c=_bday_content, lid=_bday_lid):
                db.execute(text("""
                    INSERT INTO activities (lead_id, type, content, created_at, organization_id)
                    VALUES (:lead_id, 'Note', :content, CURRENT_TIMESTAMP, :org_id)
                """), {"lead_id": lid, "content": c, "org_id": organization_id})
            if gateway:
                gateway.propose("create_activity", _do_bday_activity,
                    target_entity="lead", target_id=str(lead_id), description=_bday_content[:200],
                    payload={"lead_id": _bday_lid, "content": _bday_content, "org_id": organization_id})
            else:
                _do_bday_activity()

            birthday_tasks += 1
            actions += 1

    except Exception as e:
        # birth_date column doesn't exist — skip gracefully
        if "birth_date" in str(e).lower() or "column" in str(e).lower():
            logger.debug("birthday_anniversary: leads.birth_date column not found, skipping birthdays")
        else:
            logger.warning("birthday_anniversary: birthday query failed: %s", e)
        # Roll back the failed probe so subsequent queries work
        try:
            db.rollback()
        except Exception:
            pass

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("birthday_anniversary commit failed org=%s: %s", organization_id, e)
        raise

    return {
        "summary": f"{anniversary_tasks} anniversary tasks, {birthday_tasks} birthday tasks",
        "actions_taken": actions,
        "notifications_sent": 0,
        "anniversaries_found": len(anniversaries),
        "birthdays_found": birthday_tasks,
    }


def _ordinal(n: int) -> str:
    """Return ordinal string for an integer (1st, 2nd, 3rd, ...)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# ---------------------------------------------------------------------------
# 5. Daily Metrics Snapshot
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="daily_metrics_snapshot",
    description="Capture end-of-day pipeline and activity metrics for trend analysis",
    frequency=AgentFrequency.DAILY_9PM,
    max_runtime_seconds=60,
)
def daily_metrics_snapshot(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """
    Comprehensive daily metrics snapshot stored as structured JSON:
    - Stage-by-stage distribution with count and volume
    - Pull-through rate (funded / applications over trailing 90 days)
    - Average days-to-close for loans funded today
    - Comparison to yesterday's snapshot
    - LO-level production rankings
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── 1. Stage-by-stage distribution ────────────────────────────────────
    stage_dist = db.execute(text("""
        SELECT l.stage,
               COUNT(*) AS cnt,
               COALESCE(SUM(l.amount), 0) AS volume,
               AVG(EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.stage_changed_at))) AS avg_days
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN ('CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE')
        GROUP BY l.stage
        ORDER BY l.stage
    """), {"org_id": organization_id}).fetchall()

    stages = {}
    total_active = 0
    total_volume = 0.0
    for row in stage_dist:
        cnt = _safe_int(row[1])
        vol = _safe_float(row[2])
        stages[row[0]] = {
            "count": cnt,
            "volume": round(vol, 2),
            "avg_days_in_stage": round(_safe_float(row[3]), 1),
        }
        total_active += cnt
        total_volume += vol

    # ── 2. Today's funded loans and avg days-to-close ─────────────────────
    funded_today = db.execute(text("""
        SELECT l.id, l.amount, l.loan_officer_id,
               EXTRACT(DAY FROM (l.funded_date - l.created_at)) AS days_to_close,
               l.borrower_name, l.loan_number
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.stage_changed_at >= CURRENT_DATE
    """), {"org_id": organization_id}).fetchall()

    funded_count = len(funded_today)
    funded_volume = sum(_safe_float(r[1]) for r in funded_today)
    days_to_close_list = [_safe_float(r[3]) for r in funded_today if r[3] is not None and _safe_float(r[3]) > 0]
    avg_days_to_close = round(sum(days_to_close_list) / len(days_to_close_list), 1) if days_to_close_list else None

    # ── 3. Today's new applications ───────────────────────────────────────
    new_apps = _safe_int(db.execute(text("""
        SELECT COUNT(*) FROM loans
        WHERE organization_id = :org_id
          AND created_at >= CURRENT_DATE
    """), {"org_id": organization_id}).scalar())

    # ── 4. Today's fallen-out loans ───────────────────────────────────────
    fallen_out = _safe_int(db.execute(text("""
        SELECT COUNT(*) FROM loans
        WHERE organization_id = :org_id
          AND stage IN ('CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
          AND stage_changed_at >= CURRENT_DATE
    """), {"org_id": organization_id}).scalar())

    # ── 5. Pull-through rate (90-day trailing) ────────────────────────────
    pull_through = db.execute(text("""
        SELECT
            COUNT(CASE WHEN l.stage = 'FUNDED'
                       AND l.funded_date >= CURRENT_DATE - INTERVAL '90 days'
                  THEN 1 END) AS funded_90d,
            COUNT(CASE WHEN l.created_at >= CURRENT_DATE - INTERVAL '90 days'
                  THEN 1 END) AS apps_90d
        FROM loans l
        WHERE l.organization_id = :org_id
    """), {"org_id": organization_id}).fetchone()

    funded_90d = _safe_int(pull_through[0])
    apps_90d = _safe_int(pull_through[1])
    pull_through_pct = round((funded_90d / apps_90d * 100), 1) if apps_90d > 0 else 0.0

    # ── 6. Lead metrics ───────────────────────────────────────────────────
    lead_stats = db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(CASE WHEN created_at >= CURRENT_DATE THEN 1 END) AS new_today
        FROM leads
        WHERE organization_id = :org_id
          AND stage NOT IN ('Closed', 'Dead', 'Disqualified')
    """), {"org_id": organization_id}).fetchone()

    active_leads = _safe_int(lead_stats[0])
    new_leads_today = _safe_int(lead_stats[1])

    # ── 7. LO-level production rankings ───────────────────────────────────
    lo_rankings = db.execute(text("""
        SELECT u.id, u.first_name, u.last_name,
               COUNT(CASE WHEN l.stage = 'FUNDED'
                          AND l.stage_changed_at >= CURRENT_DATE - INTERVAL '30 days'
                     THEN 1 END) AS funded_30d,
               COALESCE(SUM(CASE WHEN l.stage = 'FUNDED'
                                 AND l.stage_changed_at >= CURRENT_DATE - INTERVAL '30 days'
                            THEN l.amount END), 0) AS volume_30d,
               COUNT(CASE WHEN l.stage NOT IN (
                   'FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'
               ) THEN 1 END) AS active_pipeline
        FROM users u
        LEFT JOIN loans l ON l.loan_officer_id = u.id AND l.organization_id = :org_id
        WHERE u.organization_id = :org_id AND u.is_active = true
          AND u.role IN ('loan_officer', 'manager', 'admin', 'branch_manager')
        GROUP BY u.id, u.first_name, u.last_name
        ORDER BY funded_30d DESC, volume_30d DESC
    """), {"org_id": organization_id}).fetchall()

    lo_board = []
    for rank, row in enumerate(lo_rankings, 1):
        lo_board.append({
            "rank": rank,
            "lo_id": row[0],
            "name": f"{row[1] or ''} {row[2] or ''}".strip(),
            "funded_30d": _safe_int(row[3]),
            "volume_30d": round(_safe_float(row[4]), 2),
            "active_pipeline": _safe_int(row[5]),
        })

    # ── 8. Compare to yesterday's snapshot ────────────────────────────────
    yesterday_snapshot = None
    try:
        yesterday_row = db.execute(text("""
            SELECT user_metadata FROM activities
            WHERE organization_id = :org_id
              AND type = 'Note'
              AND content LIKE 'Daily metrics snapshot%'
              AND created_at >= CURRENT_DATE - 1
              AND created_at < CURRENT_DATE
            ORDER BY created_at DESC
            LIMIT 1
        """), {"org_id": organization_id}).fetchone()

        if yesterday_row and yesterday_row[0]:
            raw = yesterday_row[0]
            yesterday_snapshot = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        logger.debug("daily_metrics_snapshot: could not load yesterday's snapshot: %s", e)

    delta = {}
    if yesterday_snapshot:
        y = yesterday_snapshot
        delta = {
            "active_loans": total_active - _safe_int(y.get("total_active_loans")),
            "active_volume": round(total_volume - _safe_float(y.get("total_active_volume")), 2),
            "active_leads": active_leads - _safe_int(y.get("active_leads")),
            "pull_through_pct": round(pull_through_pct - _safe_float(y.get("pull_through_pct")), 1),
        }

    # ── 9. Build structured snapshot ──────────────────────────────────────
    snapshot_data = {
        "agent": "daily_metrics_snapshot",
        "date": today,
        "total_active_loans": total_active,
        "total_active_volume": round(total_volume, 2),
        "funded_today": funded_count,
        "funded_today_volume": round(funded_volume, 2),
        "avg_days_to_close": avg_days_to_close,
        "new_applications_today": new_apps,
        "fallen_out_today": fallen_out,
        "pull_through_pct": pull_through_pct,
        "funded_90d": funded_90d,
        "apps_90d": apps_90d,
        "active_leads": active_leads,
        "new_leads_today": new_leads_today,
        "stages": stages,
        "lo_rankings": lo_board,
        "vs_yesterday": delta,
    }

    # Human-readable summary
    summary_text = (
        f"Daily metrics snapshot ({today}): "
        f"{total_active} active loans (${total_volume:,.0f}), "
        f"{funded_count} funded today (${funded_volume:,.0f}), "
        f"{new_apps} new apps, {fallen_out} fallen out. "
        f"Pull-through: {pull_through_pct}% (90d). "
        f"{active_leads} active leads ({new_leads_today} new)."
    )
    if avg_days_to_close is not None:
        summary_text += f" Avg days-to-close (today's funded): {avg_days_to_close}."
    if delta:
        summary_text += (
            f" vs yesterday: {delta.get('active_loans', 0):+d} loans, "
            f"${delta.get('active_volume', 0):+,.0f} volume."
        )

    _snap_content = summary_text
    _snap_metadata = json.dumps(snapshot_data)
    def _do_snapshot_activity(c=_snap_content, m=_snap_metadata):
        db.execute(text("""
            INSERT INTO activities (lead_id, type, content, user_metadata, created_at, organization_id)
            VALUES (NULL, 'Note', :content, :metadata, CURRENT_TIMESTAMP, :org_id)
        """), {"content": c, "metadata": m, "org_id": organization_id})
    if gateway:
        gateway.propose("create_activity", _do_snapshot_activity,
            target_entity=None, target_id=None, description=summary_text[:200],
            payload={"content": _snap_content, "metadata": _snap_metadata, "org_id": organization_id})
    else:
        _do_snapshot_activity()

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("daily_metrics_snapshot commit failed org=%s: %s", organization_id, e)
        raise

    return {
        "summary": summary_text,
        "actions_taken": 1,
        "notifications_sent": 0,
        "snapshot": snapshot_data,
    }
