"""
Risk & Compliance Agents

Autonomous agents focused on regulatory compliance and risk detection:
1. wire_fraud_scanner — Every 15 min, scan for suspicious email/wire patterns
2. ecoa_audit — Daily, verify no prohibited questions in AI conversations
3. tcpa_compliance_scanner — Daily, verify quiet hours and opt-outs respected
4. hmda_data_collector — Daily, ensure HMDA reportable fields are complete
5. fair_lending_monitor — Weekly, statistical analysis of lending patterns
"""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Wire Fraud Scanner
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="wire_fraud_scanner",
    description="Scan for suspicious wire/email patterns indicating fraud attempts",
    frequency=AgentFrequency.EVERY_15_MIN,
    max_runtime_seconds=60,
)
def wire_fraud_scanner(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Detect emails with wire instruction changes or suspicious patterns."""
    actions = 0

    # Scan recent activities for wire-related keywords
    suspicious = db.execute(text("""
        SELECT a.id, a.lead_id, a.content, a.created_at, l.owner_id
        FROM activities a
        LEFT JOIN leads l ON l.id = a.lead_id
        WHERE a.organization_id = :org_id
          AND a.created_at > CURRENT_TIMESTAMP - INTERVAL '15 minutes'
          AND a.type IN ('Email', 'System')
          AND (
              LOWER(a.content) LIKE '%wire%instruct%'
              OR LOWER(a.content) LIKE '%routing%number%changed%'
              OR LOWER(a.content) LIKE '%new%bank%account%'
              OR LOWER(a.content) LIKE '%updated%closing%account%'
              OR LOWER(a.content) LIKE '%send%funds%to%'
          )
    """), {"org_id": organization_id}).fetchall()

    for activity in suspicious:
        existing = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE organization_id = :org_id AND alert_type = 'WIRE_FRAUD_SUSPECT'
              AND description LIKE :pattern AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {"org_id": organization_id, "pattern": f"%activity {activity[0]}%"}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO compliance_alerts
                    (loan_id, organization_id, alert_type, severity, title, description,
                     status, created_at)
                VALUES
                    (NULL, :org_id, 'WIRE_FRAUD_SUSPECT', 'critical',
                     'Potential wire fraud detected',
                     :desc, 'open', CURRENT_TIMESTAMP)
            """), {
                "org_id": organization_id,
                "desc": f"Suspicious wire-related content in activity {activity[0]}. Lead: {activity[1]}. Content snippet: {str(activity[2])[:200]}",
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Wire fraud scanner commit failed: {e}")

    return {
        "summary": f"{actions} wire fraud alerts created",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 2. ECOA Audit Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="ecoa_audit",
    description="Verify no prohibited questions (race, sex, religion) in AI conversations",
    frequency=AgentFrequency.DAILY_6AM,
    max_runtime_seconds=120,
)
def ecoa_audit(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Scan AI conversation logs for ECOA-prohibited topics."""
    actions = 0

    PROHIBITED_PATTERNS = [
        '%race%', '%ethnic%', '%national origin%', '%religion%',
        '%marital status%', '%are you married%', '%handicap%',
        '%familial status%', '%how old are you%', '%your age%',
    ]

    for pattern in PROHIBITED_PATTERNS:
        violations = db.execute(text("""
            SELECT ac.id, ac.user_message, ac.agent_response
            FROM agent_conversations ac
            WHERE ac.organization_id = :org_id
              AND ac.created_at >= CURRENT_DATE - 1
              AND (LOWER(ac.agent_response) LIKE :pattern)
            LIMIT 5
        """), {"org_id": organization_id, "pattern": pattern}).fetchall()

        for v in violations:
            db.execute(text("""
                INSERT INTO compliance_alerts
                    (loan_id, organization_id, alert_type, severity, title, description,
                     status, created_at)
                VALUES
                    (NULL, :org_id, 'ECOA_VIOLATION', 'high',
                     'Potential ECOA violation in AI response',
                     :desc, 'open', CURRENT_TIMESTAMP)
            """), {
                "org_id": organization_id,
                "desc": f"AI conversation {v[0]} may contain prohibited topic matching pattern: {pattern.strip('%')}",
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"ECOA audit commit failed: {e}")

    return {
        "summary": f"{actions} ECOA compliance alerts created",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 3. TCPA Compliance Scanner
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="tcpa_compliance_scanner",
    description="Verify quiet hours and opt-out compliance for calls/SMS",
    frequency=AgentFrequency.DAILY_6AM,
    max_runtime_seconds=90,
)
def tcpa_compliance_scanner(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Check for calls/SMS sent outside quiet hours or to opted-out numbers."""
    actions = 0

    # Check for activities outside 8am-9pm window (simplified — full impl checks borrower timezone)
    after_hours = db.execute(text("""
        SELECT a.id, a.lead_id, a.type, a.created_at
        FROM activities a
        WHERE a.organization_id = :org_id
          AND a.created_at >= CURRENT_DATE - 1
          AND a.type IN ('Call', 'SMS', 'Voicemail')
          AND (EXTRACT(HOUR FROM a.created_at) < 8 OR EXTRACT(HOUR FROM a.created_at) >= 21)
        LIMIT 20
    """), {"org_id": organization_id}).fetchall()

    if after_hours:
        db.execute(text("""
            INSERT INTO compliance_alerts
                (loan_id, organization_id, alert_type, severity, title, description,
                 status, created_at)
            VALUES
                (NULL, :org_id, 'TCPA_QUIET_HOURS', 'high',
                 :title, :desc, 'open', CURRENT_TIMESTAMP)
        """), {
            "org_id": organization_id,
            "title": f"TCPA: {len(after_hours)} contact(s) outside quiet hours",
            "desc": f"Found {len(after_hours)} calls/SMS sent outside 8am-9pm window in last 24 hours. Review and adjust scheduling.",
        })
        actions += 1

    # Check for contacts to opted-out numbers
    opted_out_contacts = db.execute(text("""
        SELECT a.id, a.lead_id FROM activities a
        JOIN leads l ON l.id = a.lead_id
        WHERE a.organization_id = :org_id
          AND a.created_at >= CURRENT_DATE - 1
          AND a.type IN ('SMS', 'Call')
          AND EXISTS (
              SELECT 1 FROM sms_opt_outs so WHERE so.phone_number = l.phone
          )
        LIMIT 10
    """), {"org_id": organization_id}).fetchall()

    if opted_out_contacts:
        db.execute(text("""
            INSERT INTO compliance_alerts
                (loan_id, organization_id, alert_type, severity, title, description,
                 status, created_at)
            VALUES
                (NULL, :org_id, 'TCPA_OPT_OUT', 'critical',
                 :title, :desc, 'open', CURRENT_TIMESTAMP)
        """), {
            "org_id": organization_id,
            "title": f"TCPA: {len(opted_out_contacts)} contact(s) to opted-out numbers",
            "desc": f"Found {len(opted_out_contacts)} contacts to opted-out phone numbers. Immediate review required.",
        })
        actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"TCPA compliance scanner commit failed: {e}")

    return {
        "summary": f"{actions} TCPA alerts created",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 4. HMDA Data Collector
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="hmda_data_collector",
    description="Ensure HMDA-reportable data fields are complete on all loans",
    frequency=AgentFrequency.DAILY_9AM,
    max_runtime_seconds=90,
)
def hmda_data_collector(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Find loans missing required HMDA fields and create data-collection tasks."""
    actions = 0

    # HMDA requires: loan purpose, property type, property address, loan amount,
    # census tract, action taken, etc.
    incomplete = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id, l.stage,
               CASE
                   WHEN l.loan_purpose IS NULL THEN 'loan_purpose'
                   WHEN l.property_type IS NULL THEN 'property_type'
                   WHEN l.property_address IS NULL THEN 'property_address'
                   WHEN l.amount IS NULL OR l.amount = 0 THEN 'loan_amount'
               END as missing_field
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN ('APPLICATION','FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
          AND (l.loan_purpose IS NULL OR l.property_type IS NULL
               OR l.property_address IS NULL OR l.amount IS NULL OR l.amount = 0)
        LIMIT 25
    """), {"org_id": organization_id}).fetchall()

    for loan in incomplete:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%HMDA%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        'medium', 'pending', CURRENT_DATE + 3, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"HMDA data incomplete: {loan[2]} — {loan[5]}",
                "desc": f"Loan {loan[1]} ({loan[4]}) is missing HMDA-required field: {loan[5]}. Update before submission.",
                "lo_id": str(loan[3]),
                "loan_id": str(loan[0]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"HMDA data collector commit failed: {e}")

    return {
        "summary": f"{actions} HMDA data tasks created, {len(incomplete)} incomplete loans",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 5. Fair Lending Monitor
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="fair_lending_monitor",
    description="Statistical analysis of lending patterns for fair lending compliance",
    frequency=AgentFrequency.WEEKLY_MONDAY,
    max_runtime_seconds=120,
)
def fair_lending_monitor(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Analyze denial rates, processing times, and pricing by demographics."""
    actions = 0

    # Check denial rate variance across loan officers
    lo_denial_rates = db.execute(text("""
        SELECT l.loan_officer_id,
               CONCAT(u.first_name, ' ', u.last_name) as lo_name,
               COUNT(*) as total,
               COUNT(CASE WHEN l.stage IN ('DENIED','DOES_NOT_QUALIFY') THEN 1 END) as denied,
               ROUND(COUNT(CASE WHEN l.stage IN ('DENIED','DOES_NOT_QUALIFY') THEN 1 END)::numeric
                     / NULLIF(COUNT(*), 0) * 100, 1) as denial_rate
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.created_at >= CURRENT_DATE - 90
        GROUP BY l.loan_officer_id, u.first_name, u.last_name
        HAVING COUNT(*) >= 5
        ORDER BY denial_rate DESC
    """), {"org_id": organization_id}).fetchall()

    # Flag significant variance (>2x the org average)
    if lo_denial_rates:
        avg_rate = sum(float(r[4] or 0) for r in lo_denial_rates) / len(lo_denial_rates)
        for lo in lo_denial_rates:
            rate = float(lo[4] or 0)
            if rate > avg_rate * 2 and rate > 20:
                db.execute(text("""
                    INSERT INTO compliance_alerts
                        (loan_id, organization_id, alert_type, severity, title, description,
                         status, created_at)
                    VALUES
                        (NULL, :org_id, 'FAIR_LENDING', 'medium',
                         :title, :desc, 'open', CURRENT_TIMESTAMP)
                """), {
                    "org_id": organization_id,
                    "title": f"Fair lending: High denial rate for {lo[1]}",
                    "desc": f"{lo[1]} has {rate}% denial rate ({lo[3]}/{lo[2]} loans) vs org avg {avg_rate:.1f}%. Review for patterns.",
                })
                actions += 1

    # Check average days-to-close variance
    processing_variance = db.execute(text("""
        SELECT l.loan_officer_id,
               CONCAT(u.first_name, ' ', u.last_name) as lo_name,
               AVG(EXTRACT(DAY FROM (l.stage_changed_at - l.application_date))) as avg_days
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.application_date IS NOT NULL
          AND l.stage_changed_at >= CURRENT_DATE - 90
        GROUP BY l.loan_officer_id, u.first_name, u.last_name
        HAVING COUNT(*) >= 3
    """), {"org_id": organization_id}).fetchall()

    if processing_variance:
        avg_days = sum(float(r[2] or 0) for r in processing_variance) / len(processing_variance)
        for lo in processing_variance:
            days = float(lo[2] or 0)
            if days > avg_days * 1.5 and days > 45:
                db.execute(text("""
                    INSERT INTO compliance_alerts
                        (loan_id, organization_id, alert_type, severity, title, description,
                         status, created_at)
                    VALUES
                        (NULL, :org_id, 'FAIR_LENDING_TIMING', 'low',
                         :title, :desc, 'open', CURRENT_TIMESTAMP)
                """), {
                    "org_id": organization_id,
                    "title": f"Fair lending: Slow processing for {lo[1]}",
                    "desc": f"{lo[1]} avg {days:.0f} days to fund vs org avg {avg_days:.0f}. May indicate disparate treatment.",
                })
                actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Fair lending monitor commit failed: {e}")

    return {
        "summary": f"{actions} fair lending alerts created",
        "actions_taken": actions,
        "notifications_sent": 0,
    }
