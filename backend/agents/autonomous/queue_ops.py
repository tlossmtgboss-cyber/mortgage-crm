"""
Queue & Real-Time Operations Agents

Fast-cycle operational agents for real-time pipeline management:
1. call_queue_optimizer — Hourly, smart dialer queue scoring and redistribution
2. lock_desk_monitor — Every 15 min, rate lock expiration tracking and decision framework
3. task_overdue_escalator — Every 30 min, tiered task escalation with business impact
4. email_response_monitor — Hourly, unanswered email detection with urgency tiers
5. new_lead_qualifier — Every 5 min, multi-factor lead scoring, staging, and auto-assignment
"""

import logging
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)

# Terminal loan stages — excluded from active pipeline queries
TERMINAL_LOAN_STAGES = (
    "'FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','NURTURE'"
)

# Terminal lead stages — excluded from active lead queries
TERMINAL_LEAD_STAGES = (
    "'Closed','Dead','Disqualified','Converted','Funded','Does Not Qualify'"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dedup_task(db: Session, *, loan_id: str = None, lead_id: str = None,
                title_pattern: str, hours: int = 24) -> bool:
    """Return True if a matching task already exists within the dedup window."""
    if loan_id:
        row = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :entity_id
              AND title LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '1 hour' * :hours
            LIMIT 1
        """), {"entity_id": loan_id, "pattern": title_pattern, "hours": hours}).fetchone()
    elif lead_id:
        row = db.execute(text("""
            SELECT id FROM tasks
            WHERE lead_id = :entity_id
              AND title LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '1 hour' * :hours
            LIMIT 1
        """), {"entity_id": lead_id, "pattern": title_pattern, "hours": hours}).fetchone()
    else:
        row = db.execute(text("""
            SELECT id FROM tasks
            WHERE title LIKE :pattern
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '1 hour' * :hours
            LIMIT 1
        """), {"pattern": title_pattern, "hours": hours}).fetchone()
    return row is not None


def _insert_task(db: Session, *, title: str, description: str,
                 assigned_to_id: str, organization_id: int,
                 priority: str = "high", loan_id: str = None,
                 lead_id: str = None, due_date_expr: str = "CURRENT_DATE",
                 gateway=None):
    """Insert a task with standard fields."""
    def _do():
        db.execute(text(f"""
            INSERT INTO tasks (title, description, assigned_to_id, loan_id, lead_id,
                               priority, status, due_date, created_at, organization_id)
            VALUES (:title, :desc, :assigned_to, :loan_id, :lead_id,
                    :priority, 'pending', {due_date_expr}, CURRENT_TIMESTAMP, :org_id)
        """), {
            "title": title[:255],
            "desc": description[:2000],
            "assigned_to": assigned_to_id,
            "loan_id": loan_id,
            "lead_id": lead_id,
            "priority": priority,
            "org_id": organization_id,
        })
    if gateway:
        gateway.propose(
            "create_task", _do,
            target_entity="lead" if lead_id else ("loan" if loan_id else None),
            target_id=lead_id or loan_id,
            description=title[:200],
        )
    else:
        _do()


def _insert_activity(db: Session, *, lead_id: str, activity_type: str,
                     content: str, organization_id: int, gateway=None):
    """Insert an activity log entry on a lead."""
    def _do():
        db.execute(text("""
            INSERT INTO activities (lead_id, type, content, created_at, organization_id)
            VALUES (:lead_id, :type, :content, CURRENT_TIMESTAMP, :org_id)
        """), {
            "lead_id": lead_id,
            "type": activity_type,
            "content": content[:4000],
            "org_id": organization_id,
        })
    if gateway:
        gateway.propose(
            "create_activity", _do,
            target_entity="lead" if lead_id else None,
            target_id=lead_id,
            description=content[:200],
        )
    else:
        _do()


def _safe_float(val, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default: int = 0) -> int:
    """Safely convert a value to int."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_str(val, default: str = "") -> str:
    """Safely convert a value to string."""
    if val is None:
        return default
    return str(val).strip()


def _find_manager(db: Session, organization_id: int) -> str:
    """Find the best manager to escalate to. Returns user id as string or None."""
    row = db.execute(text("""
        SELECT id FROM users
        WHERE organization_id = :org_id
          AND role IN ('manager', 'branch_manager', 'admin')
          AND is_active = true
        ORDER BY CASE role
            WHEN 'branch_manager' THEN 1
            WHEN 'manager' THEN 2
            ELSE 3
        END
        LIMIT 1
    """), {"org_id": organization_id}).fetchone()
    return str(row[0]) if row else None


# ---------------------------------------------------------------------------
# 1. Call Queue Optimizer
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="call_queue_optimizer",
    description="Smart dialer queue: composite scoring, LO balancing, redistribution alerts",
    frequency=AgentFrequency.HOURLY,
    max_runtime_seconds=90,
)
def call_queue_optimizer(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Score every contactable lead with a composite call priority (0-100),
    rank per-LO queues, flag overloaded LOs, and create redistribution tasks."""

    actions = 0
    notifications = 0

    # ---- Fetch all contactable leads needing outreach ----
    leads = db.execute(text(f"""
        SELECT l.id, l.first_name, l.last_name, l.owner_id,
               l.ai_score, l.loan_amount, l.source,
               l.last_contact, l.created_at, l.stage
        FROM leads l
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN ({TERMINAL_LEAD_STAGES})
          AND l.phone IS NOT NULL
          AND l.phone != ''
          AND (l.last_contact IS NULL
               OR l.last_contact < CURRENT_TIMESTAMP - INTERVAL '4 hours')
        ORDER BY l.created_at DESC
    """), {"org_id": organization_id}).fetchall()

    if not leads:
        return {
            "summary": "No leads in call queue",
            "actions_taken": 0,
            "notifications_sent": 0,
            "queue_depth": 0,
            "queue_by_lo": {},
        }

    # ---- Score each lead ----
    scored_leads: List[Dict[str, Any]] = []
    for row in leads:
        lead_id = row[0]
        owner_id = row[3]
        ai_score = _safe_float(row[4])
        loan_amount = _safe_float(row[5])
        source = _safe_str(row[6]).lower()
        last_contact = row[7]
        created_at = row[8]

        # Recency factor (0-40)
        recency = 5
        if created_at is not None:
            recency_row = db.execute(text("""
                SELECT EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - :created)) / 3600.0
            """), {"created": created_at}).fetchone()
            hours_old = _safe_float(recency_row[0]) if recency_row else 999
            if hours_old < 1:
                recency = 40
            elif hours_old < 24:
                recency = 30
            elif hours_old < 48:
                recency = 20
            elif hours_old < 168:  # 7 days
                recency = 10
            else:
                recency = 5

        # Score factor (0-30): ai_score scaled
        score_factor = min(round(ai_score * 0.3), 30)

        # Financial factor (0-15)
        if loan_amount > 500000:
            financial = 15
        elif loan_amount > 300000:
            financial = 10
        elif loan_amount > 150000:
            financial = 5
        else:
            financial = 0

        # Source factor (0-15)
        is_referral = "referral" in source
        is_portal = source in ("zillow", "realtor.com", "realtor", "lendingtree")
        is_organic = source in ("organic", "website", "direct", "seo")
        if is_referral:
            source_pts = 15
        elif is_portal:
            source_pts = 10
        elif is_organic:
            source_pts = 5
        else:
            source_pts = 0

        composite = min(recency + score_factor + financial + source_pts, 100)

        scored_leads.append({
            "id": lead_id,
            "owner_id": str(owner_id) if owner_id else None,
            "score": composite,
            "name": f"{_safe_str(row[1])} {_safe_str(row[2])}".strip(),
        })

        # Write composite score back as ai_score update
        db.execute(text("""
            UPDATE leads
            SET ai_score = :score, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id AND organization_id = :org_id
        """), {"score": composite, "id": lead_id, "org_id": organization_id})
        actions += 1

    # ---- Build per-LO queue stats ----
    lo_queues: Dict[str, List[Dict]] = {}
    for sl in scored_leads:
        owner = sl["owner_id"] or "unassigned"
        lo_queues.setdefault(owner, []).append(sl)

    # Sort each LO queue by score descending
    for owner in lo_queues:
        lo_queues[owner].sort(key=lambda x: x["score"], reverse=True)

    queue_stats: Dict[str, int] = {k: len(v) for k, v in lo_queues.items()}
    total_in_queue = len(scored_leads)
    avg_score = round(sum(s["score"] for s in scored_leads) / total_in_queue, 1) if total_in_queue else 0

    # ---- Flag overloaded LOs (>30 leads needing contact) ----
    overloaded_los: List[str] = []
    for owner, queue in lo_queues.items():
        if owner != "unassigned" and len(queue) > 30:
            overloaded_los.append(owner)

    # ---- Create redistribution tasks when imbalance detected ----
    assigned_queues = {k: v for k, v in lo_queues.items() if k != "unassigned"}
    if len(assigned_queues) >= 2:
        queue_sizes = [len(v) for v in assigned_queues.values()]
        max_q = max(queue_sizes)
        min_q = min(queue_sizes) if min(queue_sizes) > 0 else 1

        if max_q >= min_q * 3 and max_q > 10:
            manager_id = _find_manager(db, organization_id)
            if manager_id:
                # Find the overloaded LO
                overloaded_owner = max(assigned_queues, key=lambda k: len(assigned_queues[k]))

                # Get LO name
                lo_row = db.execute(text("""
                    SELECT first_name, last_name FROM users WHERE id = :uid
                """), {"uid": overloaded_owner}).fetchone()
                lo_name = f"{lo_row[0]} {lo_row[1]}" if lo_row else f"LO #{overloaded_owner}"

                if not _dedup_task(db, title_pattern=f"%redistribution%{overloaded_owner}%", hours=12):
                    _insert_task(
                        db,
                        title=f"Lead redistribution needed: {lo_name} has {max_q} queued vs team avg {round(sum(queue_sizes)/len(queue_sizes))}",
                        description=(
                            f"{lo_name} has {max_q} leads needing contact while the team minimum is {min_q}. "
                            f"Consider redistributing {max_q - round(sum(queue_sizes)/len(queue_sizes))} leads to balance workload. "
                            f"Overloaded LOs: {', '.join(overloaded_los) if overloaded_los else 'none flagged'}."
                        ),
                        assigned_to_id=manager_id,
                        organization_id=organization_id,
                        priority="high",
                        gateway=gateway,
                    )
                    notifications += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"call_queue_optimizer commit failed: {e}")

    return {
        "summary": (
            f"Queue optimized: {total_in_queue} leads scored (avg {avg_score}), "
            f"{len(lo_queues)} LO queues, {len(overloaded_los)} overloaded"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications,
        "queue_depth": total_in_queue,
        "avg_score": avg_score,
        "queue_by_lo": queue_stats,
        "overloaded_los": overloaded_los,
    }


# ---------------------------------------------------------------------------
# 2. Lock Desk Monitor
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="lock_desk_monitor",
    description="Rate lock tracking: tiered alerts, extension costs, renegotiation signals, daily summary",
    frequency=AgentFrequency.EVERY_15_MIN,
    max_runtime_seconds=60,
)
def lock_desk_monitor(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Full lock desk management: expiration alerts, cost estimates, decision
    framework (extend vs expedite vs renegotiate), and daily volume summary."""

    actions = 0
    notifications = 0

    # ---- Active locks with days remaining ----
    active_locks = db.execute(text(f"""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.lock_expiration_date, l.rate, l.amount, l.stage,
               (l.lock_expiration_date - CURRENT_DATE) as days_left
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.lock_expiration_date IS NOT NULL
          AND l.lock_expiration_date >= CURRENT_DATE
          AND l.stage NOT IN ({TERMINAL_LOAN_STAGES})
        ORDER BY l.lock_expiration_date ASC
    """), {"org_id": organization_id}).fetchall()

    # ---- Track daily volume ----
    new_locks_today = 0
    total_locked_pipeline = 0.0
    expiring_5d = 0
    critical_1d = 0

    for lock in active_locks:
        loan_id = str(lock[0])
        loan_number = _safe_str(lock[1])
        borrower = _safe_str(lock[2])
        lo_id = str(lock[3]) if lock[3] else None
        expiration = lock[4]
        rate = _safe_float(lock[5])
        amount = _safe_float(lock[6])
        stage = _safe_str(lock[7])
        days_left = _safe_int(lock[8])

        total_locked_pipeline += amount

        # Count new locks (locked today = lock expiration far out, proxy: check if
        # stage_changed_at is today)
        # We approximate by counting locks in early stages
        if stage in ("APPLICATION", "DISCLOSED", "PROCESSING"):
            new_locks_today += 1

        if days_left > 5:
            continue  # No alert needed

        expiring_5d += 1

        # Extension cost estimate: 0.125% of loan amount per week
        extension_cost = round(amount * 0.00125, 2) if amount else 0

        # Determine alert tier and action recommendation
        if days_left <= 1:
            critical_1d += 1
            priority = "critical"
            tier_label = "CRITICAL"
            # Decision framework: with 1 day left, must act immediately
            if stage in ("CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT"):
                action = f"EXPEDITE closing immediately. Lock expires tomorrow. Extension cost: ${extension_cost:,.2f}/week."
            else:
                action = (
                    f"EXTEND LOCK — closing not imminent (stage: {stage}). "
                    f"Extension cost: ${extension_cost:,.2f}/week. "
                    f"If market rates improved, consider RENEGOTIATION instead of extension."
                )
        elif days_left <= 3:
            priority = "high"
            tier_label = "HIGH PRIORITY"
            action = (
                f"Lock expires in {days_left}d. Extension cost: ${extension_cost:,.2f}/week. "
                f"Review stage ({stage}) — if CTC or later, push to close. "
                f"Otherwise, prepare extension request or evaluate renegotiation."
            )
        else:
            priority = "medium"
            tier_label = "INFORMATIONAL"
            action = (
                f"Lock expires in {days_left}d. Monitor progress. "
                f"Current stage: {stage}. Extension cost if needed: ${extension_cost:,.2f}/week."
            )

        if not lo_id:
            continue

        dedup_pattern = f"%lock%{loan_number}%"
        dedup_hours = 12 if days_left <= 1 else 24

        if not _dedup_task(db, loan_id=loan_id, title_pattern=dedup_pattern, hours=dedup_hours):
            _insert_task(
                db,
                title=f"[{tier_label}] Lock expires {days_left}d: {borrower} ({loan_number})",
                description=(
                    f"Loan {loan_number} ({borrower}) at {rate}% — "
                    f"lock expires {expiration}. Amount: ${amount:,.2f}.\n\n"
                    f"ACTION: {action}"
                ),
                assigned_to_id=lo_id,
                loan_id=loan_id,
                organization_id=organization_id,
                priority=priority,
                gateway=gateway,
            )
            actions += 1

    # ---- Detect locks that expired today ----
    expired_today = db.execute(text(f"""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.lock_expiration_date, l.rate, l.amount
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.lock_expiration_date = CURRENT_DATE - 1
          AND l.stage NOT IN ({TERMINAL_LOAN_STAGES})
    """), {"org_id": organization_id}).fetchall()

    expirations_today = len(expired_today)
    for expired in expired_today:
        loan_id = str(expired[0])
        loan_number = _safe_str(expired[1])
        borrower = _safe_str(expired[2])
        lo_id = str(expired[3]) if expired[3] else None
        amount = _safe_float(expired[6])

        if lo_id and not _dedup_task(db, loan_id=loan_id, title_pattern="%EXPIRED LOCK%", hours=24):
            _insert_task(
                db,
                title=f"EXPIRED LOCK: {borrower} ({loan_number})",
                description=(
                    f"Rate lock on {loan_number} ({borrower}) EXPIRED yesterday. "
                    f"Amount: ${amount:,.2f}. Immediate action required:\n"
                    f"1. Contact lock desk for extension options and pricing\n"
                    f"2. Check current market rates — renegotiation may be favorable\n"
                    f"3. Communicate with borrower about any rate/cost changes"
                ),
                assigned_to_id=lo_id,
                loan_id=loan_id,
                organization_id=organization_id,
                priority="critical",
                gateway=gateway,
            )
            actions += 1
            notifications += 1

    # ---- End-of-day lock desk summary (create once per day at most) ----
    if not _dedup_task(db, title_pattern="%Lock desk daily summary%", hours=20):
        manager_id = _find_manager(db, organization_id)
        if manager_id and (len(active_locks) > 0 or expirations_today > 0):
            _insert_task(
                db,
                title=f"Lock desk daily summary: {len(active_locks)} active, {critical_1d} critical",
                description=(
                    f"Lock Desk Summary:\n"
                    f"- Active locks: {len(active_locks)}\n"
                    f"- Total locked pipeline: ${total_locked_pipeline:,.2f}\n"
                    f"- Expiring within 5 days: {expiring_5d}\n"
                    f"- Critical (1 day or less): {critical_1d}\n"
                    f"- Expired yesterday: {expirations_today}\n\n"
                    f"Review critical locks immediately. Prepare extension requests for at-risk files."
                ),
                assigned_to_id=manager_id,
                organization_id=organization_id,
                priority="medium" if critical_1d == 0 else "high",
                gateway=gateway,
            )
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"lock_desk_monitor commit failed: {e}")

    return {
        "summary": (
            f"Lock desk: {len(active_locks)} active locks, {expiring_5d} expiring in 5d, "
            f"{critical_1d} critical, {expirations_today} expired yesterday, "
            f"${total_locked_pipeline:,.0f} locked pipeline"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications,
        "active_locks": len(active_locks),
        "expiring_5d": expiring_5d,
        "critical_1d": critical_1d,
        "expired_today": expirations_today,
        "locked_pipeline_total": round(total_locked_pipeline, 2),
    }


# ---------------------------------------------------------------------------
# 3. Task Overdue Escalator
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="task_overdue_escalator",
    description="Tiered task escalation: LO warn, manager escalate, admin escalate, coaching tasks",
    frequency=AgentFrequency.EVERY_30_MIN,
    max_runtime_seconds=90,
)
def task_overdue_escalator(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Intelligent task escalation with tiered thresholds, business impact
    calculation, per-LO grouping, OOO awareness, and coaching triggers."""

    actions = 0
    notifications = 0

    # ---- Fetch all overdue tasks ----
    overdue_tasks = db.execute(text("""
        SELECT t.id, t.title, t.assigned_to_id, t.priority, t.due_date,
               t.loan_id, t.lead_id,
               CONCAT(u.first_name, ' ', u.last_name) as assigned_name,
               (CURRENT_DATE - t.due_date) as days_overdue
        FROM tasks t
        LEFT JOIN users u ON u.id = t.assigned_to_id
        WHERE t.organization_id = :org_id
          AND t.status IN ('pending', 'in_progress')
          AND t.due_date < CURRENT_DATE
    """), {"org_id": organization_id}).fetchall()

    if not overdue_tasks:
        return {
            "summary": "No overdue tasks",
            "actions_taken": 0,
            "notifications_sent": 0,
            "overdue_count": 0,
        }

    # ---- Group by LO ----
    lo_overdue: Dict[str, List[Dict[str, Any]]] = {}
    for task in overdue_tasks:
        lo_id = str(task[2]) if task[2] else "unassigned"
        lo_name = _safe_str(task[7]) or "Unassigned"
        days = _safe_int(task[8])
        priority = _safe_str(task[3])

        entry = {
            "task_id": task[0],
            "title": _safe_str(task[1]),
            "priority": priority,
            "days_overdue": days,
            "loan_id": str(task[5]) if task[5] else None,
            "lead_id": str(task[6]) if task[6] else None,
            "lo_name": lo_name,
        }
        lo_overdue.setdefault(lo_id, []).append(entry)

    # ---- Metrics by age bucket ----
    bucket_1_2 = 0
    bucket_3_5 = 0
    bucket_5_plus = 0
    priority_counts: Dict[str, int] = {}

    for task in overdue_tasks:
        days = _safe_int(task[8])
        priority = _safe_str(task[3])
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
        if days <= 2:
            bucket_1_2 += 1
        elif days <= 5:
            bucket_3_5 += 1
        else:
            bucket_5_plus += 1

    manager_id = _find_manager(db, organization_id)

    # ---- Process each LO's overdue tasks ----
    for lo_id, tasks in lo_overdue.items():
        if lo_id == "unassigned":
            continue

        lo_name = tasks[0]["lo_name"]

        # Check if LO is out of office (has an appointment/event marked as OOO today)
        ooo_row = db.execute(text("""
            SELECT id FROM scheduler_appointments
            WHERE organization_id = :org_id
              AND (host_user_id = :lo_id OR assigned_to_id = :lo_id)
              AND CURRENT_DATE BETWEEN DATE(start_time) AND DATE(end_time)
              AND (title ILIKE '%out of office%' OR title ILIKE '%ooo%'
                   OR title ILIKE '%vacation%' OR title ILIKE '%pto%')
            LIMIT 1
        """), {"org_id": organization_id, "lo_id": lo_id}).fetchone()

        is_ooo = ooo_row is not None
        if is_ooo:
            logger.info(f"Skipping escalation for {lo_name} (LO #{lo_id}) — out of office")
            continue

        # Calculate LO's overall task completion rate (last 30 days)
        completion_row = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE status IN ('completed', 'done')) as completed,
                COUNT(*) as total
            FROM tasks
            WHERE assigned_to_id = :lo_id
              AND organization_id = :org_id
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '30 days'
        """), {"lo_id": lo_id, "org_id": organization_id}).fetchone()

        completed = _safe_int(completion_row[0]) if completion_row else 0
        total_tasks = _safe_int(completion_row[1]) if completion_row else 0
        completion_rate = round((completed / total_tasks * 100), 1) if total_tasks > 0 else 0

        # Calculate business impact: sum loan amounts for tasks with loan_id
        loan_ids = [t["loan_id"] for t in tasks if t["loan_id"]]
        dollar_exposure = 0.0
        if loan_ids:
            # Query in batches to avoid overly long IN clauses
            for i in range(0, len(loan_ids), 50):
                batch = loan_ids[i:i + 50]
                placeholders = ", ".join(f":lid_{j}" for j in range(len(batch)))
                params = {f"lid_{j}": batch[j] for j in range(len(batch))}
                params["org_id"] = organization_id
                amount_row = db.execute(text(f"""
                    SELECT COALESCE(SUM(amount), 0) FROM loans
                    WHERE id IN ({placeholders}) AND organization_id = :org_id
                """), params).fetchone()
                dollar_exposure += _safe_float(amount_row[0]) if amount_row else 0

        # Determine worst overdue severity
        max_days = max(t["days_overdue"] for t in tasks)
        has_critical = any(t["priority"] in ("critical", "high") for t in tasks)
        overdue_count = len(tasks)

        # ---- Tier 1: 1+ day overdue on high/critical — warn LO ----
        warn_tasks = [t for t in tasks if t["days_overdue"] >= 1 and t["priority"] in ("critical", "high")]
        if warn_tasks and not _dedup_task(db, title_pattern=f"%Overdue warning%{lo_id}%", hours=24):
            task_list = "\n".join(
                f"  - [{t['priority'].upper()}] \"{t['title']}\" ({t['days_overdue']}d overdue)"
                for t in sorted(warn_tasks, key=lambda x: -x["days_overdue"])[:10]
            )
            _insert_task(
                db,
                title=f"Overdue warning: {overdue_count} tasks — {lo_name}",
                description=(
                    f"You have {overdue_count} overdue tasks ({len(warn_tasks)} high/critical):\n"
                    f"{task_list}\n\n"
                    f"Dollar exposure: ${dollar_exposure:,.2f}\n"
                    f"Your 30-day completion rate: {completion_rate}%\n"
                    f"Please address critical items first."
                ),
                assigned_to_id=lo_id,
                organization_id=organization_id,
                priority="high",
                gateway=gateway,
            )
            actions += 1

        # ---- Tier 2: 2+ days overdue — escalate to manager ----
        escalate_tasks = [t for t in tasks if t["days_overdue"] >= 2 and t["priority"] in ("critical", "high")]
        if escalate_tasks and manager_id and manager_id != lo_id:
            if not _dedup_task(db, title_pattern=f"%Escalation%overdue%{lo_id}%", hours=24):
                task_list = "\n".join(
                    f"  - [{t['priority'].upper()}] \"{t['title']}\" ({t['days_overdue']}d overdue)"
                    for t in sorted(escalate_tasks, key=lambda x: -x["days_overdue"])[:10]
                )
                pattern_note = (
                    f" This appears to be a pattern (completion rate: {completion_rate}%)."
                    if completion_rate < 70 else ""
                )
                _insert_task(
                    db,
                    title=f"Escalation: {lo_name} has {len(escalate_tasks)} overdue high-priority tasks",
                    description=(
                        f"{lo_name} has {len(escalate_tasks)} high/critical tasks overdue 2+ days:\n"
                        f"{task_list}\n\n"
                        f"Dollar exposure at risk: ${dollar_exposure:,.2f}\n"
                        f"30-day completion rate: {completion_rate}%{pattern_note}"
                    ),
                    assigned_to_id=manager_id,
                    organization_id=organization_id,
                    priority="high",
                    gateway=gateway,
                )
                actions += 1
                notifications += 1

        # ---- Tier 3: 5+ days overdue — escalate to admin ----
        admin_tasks = [t for t in tasks if t["days_overdue"] >= 5]
        if admin_tasks and manager_id:
            admin_row = db.execute(text("""
                SELECT id FROM users
                WHERE organization_id = :org_id AND role = 'admin' AND is_active = true
                LIMIT 1
            """), {"org_id": organization_id}).fetchone()
            admin_id = str(admin_row[0]) if admin_row else manager_id

            if not _dedup_task(db, title_pattern=f"%Admin escalation%{lo_id}%", hours=48):
                _insert_task(
                    db,
                    title=f"Admin escalation: {lo_name} — {len(admin_tasks)} tasks 5+ days overdue",
                    description=(
                        f"{lo_name} has {len(admin_tasks)} tasks overdue by 5 or more days. "
                        f"Dollar exposure: ${dollar_exposure:,.2f}. "
                        f"Completion rate: {completion_rate}%. Immediate management intervention required."
                    ),
                    assigned_to_id=admin_id,
                    organization_id=organization_id,
                    priority="critical",
                    gateway=gateway,
                )
                actions += 1
                notifications += 1

        # ---- Coaching trigger: >5 overdue tasks for one LO ----
        if overdue_count > 5 and manager_id and manager_id != lo_id:
            if not _dedup_task(db, title_pattern=f"%Coaching%{lo_id}%", hours=72):
                _insert_task(
                    db,
                    title=f"Coaching needed: {lo_name} — {overdue_count} overdue tasks",
                    description=(
                        f"{lo_name} has {overdue_count} overdue tasks (completion rate: {completion_rate}%). "
                        f"Schedule a 1:1 coaching session to discuss workload management, "
                        f"prioritization, and any blockers. "
                        f"Dollar exposure: ${dollar_exposure:,.2f}."
                    ),
                    assigned_to_id=manager_id,
                    organization_id=organization_id,
                    priority="medium",
                    gateway=gateway,
                )
                actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"task_overdue_escalator commit failed: {e}")

    return {
        "summary": (
            f"{len(overdue_tasks)} overdue tasks across {len(lo_overdue)} LOs, "
            f"{actions} escalation actions taken"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications,
        "overdue_count": len(overdue_tasks),
        "by_priority": priority_counts,
        "by_age": {"1-2d": bucket_1_2, "3-5d": bucket_3_5, "5d+": bucket_5_plus},
        "lo_count": len(lo_overdue),
    }


# ---------------------------------------------------------------------------
# 4. Email Response Monitor
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="email_response_monitor",
    description="Unanswered email detection: source-tiered urgency, response time tracking, manager alerts",
    frequency=AgentFrequency.HOURLY,
    max_runtime_seconds=60,
)
def email_response_monitor(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Detect unanswered inbound emails, tier by source and pipeline status,
    track per-LO response times, and create manager alerts for slow responders."""

    actions = 0
    notifications = 0

    # ---- Find inbound emails with no outbound reply ----
    unanswered = db.execute(text("""
        SELECT a.id, a.lead_id, a.content, a.created_at,
               l.first_name, l.last_name, l.owner_id, l.source,
               l.stage,
               EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - a.created_at)) / 3600.0 as hours_waiting
        FROM activities a
        JOIN leads l ON l.id = a.lead_id AND l.organization_id = :org_id
        WHERE a.organization_id = :org_id
          AND a.type IN ('Email', 'email', 'email_inbound', 'inbound_email')
          AND (a.content ILIKE '%inbound%' OR a.content ILIKE '%received%'
               OR a.content ILIKE '%from:%')
          AND a.created_at BETWEEN CURRENT_TIMESTAMP - INTERVAL '48 hours'
                                AND CURRENT_TIMESTAMP - INTERVAL '2 hours'
          AND NOT EXISTS (
              SELECT 1 FROM activities a2
              WHERE a2.lead_id = a.lead_id
                AND a2.type IN ('Email', 'email', 'email_outbound', 'outbound_email')
                AND (a2.content ILIKE '%sent%' OR a2.content ILIKE '%outbound%'
                     OR a2.content ILIKE '%replied%')
                AND a2.created_at > a.created_at
          )
        ORDER BY a.created_at ASC
        LIMIT 100
    """), {"org_id": organization_id}).fetchall()

    if not unanswered:
        return {
            "summary": "No unanswered emails detected",
            "actions_taken": 0,
            "notifications_sent": 0,
            "unanswered_count": 0,
        }

    # ---- Check which leads have active pipeline loans (increases urgency) ----
    pipeline_leads = set()
    lead_ids = list(set(str(row[1]) for row in unanswered if row[1]))
    if lead_ids:
        for i in range(0, len(lead_ids), 50):
            batch = lead_ids[i:i + 50]
            placeholders = ", ".join(f":lid_{j}" for j in range(len(batch)))
            params = {f"lid_{j}": batch[j] for j in range(len(batch))}
            params["org_id"] = organization_id
            pipeline_rows = db.execute(text(f"""
                SELECT DISTINCT l.borrower_name, le.id
                FROM loans l
                JOIN leads le ON (
                    LOWER(TRIM(le.first_name || ' ' || le.last_name)) = LOWER(TRIM(l.borrower_name))
                    OR le.id::text = l.id::text
                )
                WHERE le.id IN ({placeholders})
                  AND l.organization_id = :org_id
                  AND l.stage NOT IN ({TERMINAL_LOAN_STAGES})
            """), params).fetchall()
            for pr in pipeline_rows:
                pipeline_leads.add(str(pr[1]))

    # ---- Process each unanswered email ----
    lo_response_data: Dict[str, List[float]] = {}  # lo_id -> list of wait hours

    for email in unanswered:
        activity_id = email[0]
        lead_id = str(email[1])
        content_snippet = _safe_str(email[2])[:200]
        email_time = email[3]
        first_name = _safe_str(email[4])
        last_name = _safe_str(email[5])
        owner_id = str(email[6]) if email[6] else None
        source = _safe_str(email[7]).lower()
        lead_stage = _safe_str(email[8])
        hours_waiting = _safe_float(email[9])
        contact_name = f"{first_name} {last_name}".strip() or "Unknown"

        # Track response time per LO
        if owner_id:
            lo_response_data.setdefault(owner_id, []).append(hours_waiting)

        # Determine source tier
        is_referral = "referral" in source
        is_realtor = "realtor" in source or "agent" in source or "partner" in source
        if is_referral or is_realtor:
            source_priority = "high"
            source_label = "referral/partner"
        elif source in ("borrower", "client", "applicant", ""):
            source_priority = "high"
            source_label = "borrower"
        else:
            source_priority = "medium"
            source_label = source or "unknown"

        # Pipeline status increases urgency
        in_pipeline = lead_id in pipeline_leads
        if in_pipeline and source_priority == "medium":
            source_priority = "high"

        priority = "critical" if (hours_waiting > 8 and source_priority == "high") else source_priority

        # Suggest response action based on context
        if in_pipeline:
            suggested_action = "Reply with loan status update — this borrower has an active file."
        elif "schedule" in content_snippet.lower() or "appointment" in content_snippet.lower():
            suggested_action = "Reply with availability for a call or meeting."
        elif "rate" in content_snippet.lower() or "quote" in content_snippet.lower():
            suggested_action = "Reply with current rate sheet or personalized quote."
        else:
            suggested_action = "Review email content and reply with appropriate follow-up."

        if owner_id and not _dedup_task(db, lead_id=lead_id, title_pattern="%Unanswered email%", hours=12):
            pipeline_flag = " [ACTIVE PIPELINE]" if in_pipeline else ""
            _insert_task(
                db,
                title=f"Unanswered email from {contact_name}{pipeline_flag}",
                description=(
                    f"Email from {contact_name} ({source_label}) received {email_time} "
                    f"has been waiting {hours_waiting:.1f} hours with no reply.\n\n"
                    f"Preview: {content_snippet}\n\n"
                    f"Lead stage: {lead_stage}\n"
                    f"Suggested action: {suggested_action}"
                ),
                assigned_to_id=owner_id,
                lead_id=lead_id,
                organization_id=organization_id,
                priority=priority,
                gateway=gateway,
            )
            actions += 1

    # ---- Calculate per-LO average response time and alert on slow responders ----
    slow_los: List[Dict[str, Any]] = []
    for lo_id, wait_hours_list in lo_response_data.items():
        avg_wait = sum(wait_hours_list) / len(wait_hours_list)
        if avg_wait > 4.0:
            # Get LO name
            lo_row = db.execute(text("""
                SELECT first_name, last_name FROM users WHERE id = :uid
            """), {"uid": lo_id}).fetchone()
            lo_name = f"{lo_row[0]} {lo_row[1]}" if lo_row else f"LO #{lo_id}"
            slow_los.append({
                "lo_id": lo_id,
                "lo_name": lo_name,
                "avg_response_hours": round(avg_wait, 1),
                "unanswered_count": len(wait_hours_list),
            })

    if slow_los:
        manager_id = _find_manager(db, organization_id)
        if manager_id and not _dedup_task(db, title_pattern="%Email response time alert%", hours=24):
            lo_summary = "\n".join(
                f"  - {sl['lo_name']}: {sl['avg_response_hours']}h avg, {sl['unanswered_count']} unanswered"
                for sl in sorted(slow_los, key=lambda x: -x["avg_response_hours"])
            )
            _insert_task(
                db,
                title=f"Email response time alert: {len(slow_los)} LO(s) exceed 4hr threshold",
                description=(
                    f"The following LOs have average email response times exceeding 4 hours:\n"
                    f"{lo_summary}\n\n"
                    f"Industry best practice is sub-1-hour response on inbound borrower emails. "
                    f"Consider coaching or workload redistribution."
                ),
                assigned_to_id=manager_id,
                organization_id=organization_id,
                priority="high",
            )
            notifications += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"email_response_monitor commit failed: {e}")

    avg_response_all = 0.0
    all_waits = [h for hrs in lo_response_data.values() for h in hrs]
    if all_waits:
        avg_response_all = round(sum(all_waits) / len(all_waits), 1)

    return {
        "summary": (
            f"{len(unanswered)} unanswered emails found, {actions} follow-up tasks created, "
            f"avg wait {avg_response_all}h, {len(slow_los)} slow LOs flagged"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications,
        "unanswered_count": len(unanswered),
        "avg_response_hours": avg_response_all,
        "slow_responder_count": len(slow_los),
    }


# ---------------------------------------------------------------------------
# 5. New Lead Qualifier
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="new_lead_qualifier",
    description="Multi-factor lead scoring (0-100), auto-staging, weighted round-robin assignment",
    frequency=AgentFrequency.EVERY_5_MIN,
    max_runtime_seconds=45,
)
def new_lead_qualifier(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Score new leads with a multi-factor algorithm, set appropriate stage,
    auto-assign unowned leads via weighted round-robin, and create speed-to-lead
    tasks for high-scoring leads."""

    actions = 0
    notifications = 0

    # ---- Fetch unscored leads from last 24 hours ----
    unscored = db.execute(text("""
        SELECT l.id, l.first_name, l.last_name, l.email, l.phone,
               l.loan_amount, l.loan_purpose, l.credit_score,
               l.property_value, l.down_payment, l.source,
               l.owner_id, l.created_at, l.stage
        FROM leads l
        WHERE l.organization_id = :org_id
          AND (l.ai_score IS NULL OR l.ai_score = 0)
          AND l.created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
        ORDER BY l.created_at DESC
        LIMIT 50
    """), {"org_id": organization_id}).fetchall()

    if not unscored:
        return {
            "summary": "No new leads to qualify",
            "actions_taken": 0,
            "notifications_sent": 0,
            "scored_count": 0,
        }

    # ---- Pre-fetch active LOs with their current lead counts for round-robin ----
    active_los = db.execute(text(f"""
        SELECT u.id, u.first_name, u.last_name,
               COUNT(l.id) as active_lead_count
        FROM users u
        LEFT JOIN leads l ON l.owner_id = u.id
            AND l.organization_id = :org_id
            AND l.stage NOT IN ({TERMINAL_LEAD_STAGES})
        WHERE u.organization_id = :org_id
          AND u.is_active = true
          AND u.role IN ('loan_officer', 'lo', 'agent', 'producer')
        GROUP BY u.id, u.first_name, u.last_name
        ORDER BY active_lead_count ASC, u.id ASC
    """), {"org_id": organization_id}).fetchall()

    # Build LO pool with weights (fewer active leads = more weight)
    lo_pool: List[Dict[str, Any]] = []
    for lo in active_los:
        lo_pool.append({
            "id": str(lo[0]),
            "name": f"{lo[1]} {lo[2]}",
            "active_leads": _safe_int(lo[3]),
        })

    # Track assignments made this run to update weights dynamically
    assignments_this_run: Dict[str, int] = {}

    # ---- Score each lead ----
    score_distribution = {"high": 0, "medium": 0, "low": 0}
    scored_count = 0

    for lead in unscored:
        lead_id = str(lead[0])
        first_name = _safe_str(lead[1])
        last_name = _safe_str(lead[2])
        email = _safe_str(lead[3])
        phone = _safe_str(lead[4])
        loan_amount = _safe_float(lead[5])
        loan_purpose = _safe_str(lead[6]).lower()
        credit_score = _safe_float(lead[7])
        property_value = _safe_float(lead[8])
        down_payment = _safe_float(lead[9])
        source = _safe_str(lead[10]).lower()
        owner_id = str(lead[11]) if lead[11] else None
        created_at = lead[12]
        current_stage = _safe_str(lead[13])
        contact_name = f"{first_name} {last_name}".strip() or "Unknown"

        breakdown: List[str] = []

        # --- Contact completeness (0-20) ---
        contact_score = 0
        if email:
            contact_score += 10
            breakdown.append("Email provided (+10)")
        if phone:
            contact_score += 10
            breakdown.append("Phone provided (+10)")

        # --- Financial qualification: credit score (0-20) ---
        credit_pts = 0
        if credit_score >= 740:
            credit_pts = 20
            breakdown.append(f"Credit {int(credit_score)}: excellent (+20)")
        elif credit_score >= 700:
            credit_pts = 15
            breakdown.append(f"Credit {int(credit_score)}: good (+15)")
        elif credit_score >= 680:
            credit_pts = 10
            breakdown.append(f"Credit {int(credit_score)}: fair (+10)")
        elif credit_score >= 620:
            credit_pts = 5
            breakdown.append(f"Credit {int(credit_score)}: qualifying (+5)")
        elif credit_score > 0:
            breakdown.append(f"Credit {int(credit_score)}: below threshold (+0)")

        # --- Deal size (0-15) ---
        deal_pts = 0
        if loan_amount > 500000:
            deal_pts = 15
            breakdown.append(f"Loan ${loan_amount:,.0f}: jumbo (+15)")
        elif loan_amount > 300000:
            deal_pts = 10
            breakdown.append(f"Loan ${loan_amount:,.0f}: high (+10)")
        elif loan_amount > 150000:
            deal_pts = 5
            breakdown.append(f"Loan ${loan_amount:,.0f}: standard (+5)")
        elif loan_amount > 0:
            breakdown.append(f"Loan ${loan_amount:,.0f}: low (+0)")

        # --- Down payment ratio (0-10) ---
        dp_pts = 0
        if property_value > 0 and down_payment > 0:
            dp_ratio = down_payment / property_value
            if dp_ratio >= 0.20:
                dp_pts = 10
                breakdown.append(f"Down payment {dp_ratio:.0%}: 20%+ (+10)")
            elif dp_ratio >= 0.10:
                dp_pts = 5
                breakdown.append(f"Down payment {dp_ratio:.0%}: 10-19% (+5)")
            else:
                breakdown.append(f"Down payment {dp_ratio:.0%}: <10% (+0)")

        # --- Loan purpose (0-10) ---
        purpose_pts = 0
        if "purchase" in loan_purpose:
            purpose_pts = 10
            breakdown.append("Purpose: purchase (+10)")
        elif "refinance" in loan_purpose and "cash" not in loan_purpose:
            purpose_pts = 8
            breakdown.append("Purpose: refinance (+8)")
        elif "cash" in loan_purpose:
            purpose_pts = 5
            breakdown.append("Purpose: cash-out refi (+5)")
        elif loan_purpose:
            purpose_pts = 3
            breakdown.append(f"Purpose: {loan_purpose} (+3)")

        # --- Source quality (0-10) ---
        source_pts = 0
        is_referral = "referral" in source
        if is_referral:
            source_pts = 10
            breakdown.append("Source: referral (+10)")
        elif source in ("zillow", "realtor.com", "realtor", "lendingtree"):
            source_pts = 8
            breakdown.append(f"Source: {source} (+8)")
        elif source in ("organic", "website", "direct", "seo"):
            source_pts = 5
            breakdown.append(f"Source: {source} (+5)")
        elif source:
            source_pts = 3
            breakdown.append(f"Source: {source} (+3)")

        # --- Timing bonus (0-5) ---
        timing_pts = 0
        if created_at is not None:
            age_row = db.execute(text("""
                SELECT EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - :created)) / 3600.0
            """), {"created": created_at}).fetchone()
            hours_old = _safe_float(age_row[0]) if age_row else 999
            if hours_old < 1:
                timing_pts = 5
                breakdown.append("Created <1hr ago (+5)")

        # --- Composite score ---
        total_score = min(
            contact_score + credit_pts + deal_pts + dp_pts + purpose_pts + source_pts + timing_pts,
            100
        )
        breakdown.append(f"TOTAL: {total_score}/100")

        # --- Determine stage ---
        if total_score >= 70:
            new_stage = "Qualified"
            score_distribution["high"] += 1
        elif total_score >= 30:
            new_stage = "Nurture"
            score_distribution["medium"] += 1
        else:
            new_stage = "Low Priority"
            score_distribution["low"] += 1

        # --- Auto-assign unowned leads via weighted round-robin ---
        assigned_to = owner_id
        assignment_note = ""
        if not owner_id and lo_pool:
            # Pick LO with fewest active leads (accounting for this run's assignments)
            best_lo = min(
                lo_pool,
                key=lambda lo: lo["active_leads"] + assignments_this_run.get(lo["id"], 0)
            )
            assigned_to = best_lo["id"]
            assignments_this_run[assigned_to] = assignments_this_run.get(assigned_to, 0) + 1
            assignment_note = f" Auto-assigned to {best_lo['name']} (round-robin)."

            db.execute(text("""
                UPDATE leads
                SET owner_id = :owner_id, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND organization_id = :org_id
            """), {"owner_id": assigned_to, "id": lead[0], "org_id": organization_id})

        # --- Update lead score and stage ---
        # Only update stage if lead is in a default/new state (don't override manual staging)
        stage_update = ""
        if current_stage in ("", "New", "new", "Unqualified", None):
            stage_update = ", stage = :new_stage"

        db.execute(text(f"""
            UPDATE leads
            SET ai_score = :score, updated_at = CURRENT_TIMESTAMP{stage_update}
            WHERE id = :id AND organization_id = :org_id
        """), {"score": total_score, "id": lead[0], "org_id": organization_id,
               "new_stage": new_stage})

        # --- Log scoring breakdown as activity ---
        breakdown_text = " | ".join(breakdown) + f" | Stage: {new_stage}.{assignment_note}"
        _insert_activity(
            db,
            lead_id=lead_id,
            activity_type="System",
            content=f"AI Lead Qualification: {breakdown_text}",
            organization_id=organization_id,
            gateway=gateway,
        )
        actions += 1
        scored_count += 1

        # --- Speed-to-lead task for high-scoring leads ---
        if total_score >= 70 and assigned_to:
            _insert_task(
                db,
                title=f"Speed-to-lead: {contact_name} (score {total_score})",
                description=(
                    f"High-quality lead just scored {total_score}/100. Contact ASAP.\n\n"
                    f"Qualification summary:\n"
                    f"  Credit: {int(credit_score) if credit_score else 'N/A'}\n"
                    f"  Loan amount: ${loan_amount:,.0f}\n"
                    f"  Purpose: {loan_purpose or 'N/A'}\n"
                    f"  Source: {source or 'N/A'}\n"
                    f"  Down payment: ${down_payment:,.0f}\n"
                    f"  Contact: {email or 'no email'} / {phone or 'no phone'}\n\n"
                    f"Stage set to: {new_stage}{assignment_note}"
                ),
                assigned_to_id=assigned_to,
                lead_id=lead_id,
                organization_id=organization_id,
                priority="critical",
                gateway=gateway,
            )
            notifications += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"new_lead_qualifier commit failed: {e}")

    return {
        "summary": (
            f"Scored {scored_count} leads: {score_distribution['high']} qualified, "
            f"{score_distribution['medium']} nurture, {score_distribution['low']} low priority, "
            f"{sum(assignments_this_run.values())} auto-assigned"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications,
        "scored_count": scored_count,
        "score_distribution": score_distribution,
        "auto_assigned": sum(assignments_this_run.values()),
        "assignments_by_lo": assignments_this_run,
    }
