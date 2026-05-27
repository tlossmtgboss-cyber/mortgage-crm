"""
Compliance Watchdog Agent

Runs every 30 minutes. Monitors TRID deadlines, disclosure timing,
and document expiration. Creates compliance alerts before violations occur.
"""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency
from agents.autonomous.memory_context import get_lo_memory_context, get_org_directives

logger = logging.getLogger(__name__)


@autonomous_agent(
    name="compliance_watchdog",
    description="Monitor TRID deadlines, disclosure timing, document expiration",
    frequency=AgentFrequency.EVERY_30_MIN,
    max_runtime_seconds=90,
)
def compliance_watchdog(
    db: Session,
    organization_id: int,
    org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Check for upcoming compliance deadlines and create alerts."""

    actions = 0
    org_ctx = get_org_directives(db, organization_id)

    # 1. LE not sent within 3 days of application
    le_overdue = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.application_date,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.application_date)) as days_since_app
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.application_date IS NOT NULL
          AND l.initial_disclosures_sent_date IS NULL
          AND l.application_date < CURRENT_DATE - 2
          AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
    """), {"org_id": organization_id}).fetchall()

    for loan in le_overdue:
        days = int(loan[5] or 0)
        existing = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE loan_id = :loan_id AND alert_type = 'LE_TIMING' AND status = 'open'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            severity = "critical" if days >= 3 else "high"
            _le_params = {
                "loan_id": str(loan[0]),
                "org_id": organization_id,
                "severity": severity,
                "title": f"LE not sent — {days} days since application",
                "desc": f"{loan[2]} ({loan[1]}): Loan Estimate must be sent within 3 business days of application. Application date: {loan[4]}",
                "deadline": loan[4],
            }
            def _do_le_insert(_p=_le_params):
                db.execute(text("""
                    INSERT INTO compliance_alerts
                        (loan_id, organization_id, alert_type, severity, title, description,
                         status, deadline_date, created_at)
                    VALUES
                        (:loan_id, :org_id, 'LE_TIMING', :severity,
                         :title, :desc, 'open', :deadline, CURRENT_TIMESTAMP)
                """), _p)
            if gateway:
                gateway.propose(
                    "create_compliance_alert", _do_le_insert,
                    target_entity="loan", target_id=loan[0],
                    description=f"LE timing alert for {loan[2]} ({loan[1]}) — {days}d since application",
                )
            else:
                _do_le_insert()
            actions += 1

    # 2. CD timing check — must be 3 days before closing
    cd_needed = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.closing_date, l.cd_sent_to_borrower_date,
               (l.closing_date - CURRENT_DATE) as days_to_close
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.closing_date IS NOT NULL
          AND l.cd_sent_to_borrower_date IS NULL
          AND l.closing_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 5
          AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
    """), {"org_id": organization_id}).fetchall()

    for loan in cd_needed:
        days_to_close = int(loan[6] or 0)
        existing = db.execute(text("""
            SELECT id FROM compliance_alerts
            WHERE loan_id = :loan_id AND alert_type = 'CD_TIMING' AND status = 'open'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            severity = "critical" if days_to_close <= 3 else "high"
            _cd_params = {
                "loan_id": str(loan[0]),
                "org_id": organization_id,
                "severity": severity,
                "title": f"CD must be sent — closing in {days_to_close} days",
                "desc": f"{loan[2]} ({loan[1]}): Closing Disclosure must be delivered 3+ business days before closing ({loan[4]})",
                "deadline": loan[4],
            }
            def _do_cd_insert(_p=_cd_params):
                db.execute(text("""
                    INSERT INTO compliance_alerts
                        (loan_id, organization_id, alert_type, severity, title, description,
                         status, deadline_date, created_at)
                    VALUES
                        (:loan_id, :org_id, 'CD_TIMING', :severity,
                         :title, :desc, 'open', :deadline, CURRENT_TIMESTAMP)
                """), _p)
            if gateway:
                gateway.propose(
                    "create_compliance_alert", _do_cd_insert,
                    target_entity="loan", target_id=loan[0],
                    description=f"CD timing alert for {loan[2]} ({loan[1]}) — closing in {days_to_close}d",
                )
            else:
                _do_cd_insert()
            actions += 1

    # 3. Document expiration (credit docs, appraisal)
    expiring_docs = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.credit_docs_expire_date, l.appraisal_docs_expire_date
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
          AND (
              (l.credit_docs_expire_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 14)
              OR (l.appraisal_docs_expire_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 14)
          )
    """), {"org_id": organization_id}).fetchall()

    for loan in expiring_docs:
        for doc_type, col_idx in [("CREDIT_DOCS_EXPIRY", 4), ("APPRAISAL_DOCS_EXPIRY", 5)]:
            expire_date = loan[col_idx]
            if not expire_date:
                continue

            existing = db.execute(text("""
                SELECT id FROM compliance_alerts
                WHERE loan_id = :loan_id AND alert_type = :alert_type AND status = 'open'
                LIMIT 1
            """), {"loan_id": str(loan[0]), "alert_type": doc_type}).fetchone()

            if not existing:
                _doc_params = {
                    "loan_id": str(loan[0]),
                    "org_id": organization_id,
                    "alert_type": doc_type,
                    "title": f"{doc_type.replace('_', ' ').title()} — expires {expire_date}",
                    "desc": f"{loan[2]} ({loan[1]}): Document expires {expire_date}. Order renewal.",
                    "deadline": expire_date,
                }
                def _do_doc_insert(_p=_doc_params):
                    db.execute(text("""
                        INSERT INTO compliance_alerts
                            (loan_id, organization_id, alert_type, severity, title, description,
                             status, deadline_date, created_at)
                        VALUES
                            (:loan_id, :org_id, :alert_type, 'medium',
                             :title, :desc, 'open', :deadline, CURRENT_TIMESTAMP)
                    """), _p)
                if gateway:
                    gateway.propose(
                        "create_compliance_alert", _do_doc_insert,
                        target_entity="loan", target_id=loan[0],
                        description=f"Doc expiry alert for {loan[2]} ({loan[1]}) — {doc_type} expires {expire_date}",
                    )
                else:
                    _do_doc_insert()
                actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Compliance watchdog commit failed: {e}")

    return {
        "summary": f"{actions} compliance alerts created",
        "actions_taken": actions,
        "notifications_sent": 0,
        "le_overdue": len(le_overdue),
        "cd_needed": len(cd_needed),
        "expiring_docs": len(expiring_docs),
    }
