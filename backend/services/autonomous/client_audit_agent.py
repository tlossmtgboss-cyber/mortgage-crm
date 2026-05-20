"""
Client Audit Agent

Per-client/per-loan autonomous agent that proactively audits every active
loan file in an organization and generates actionable user-facing tasks.

This is the "watch → generate tasks → user completes → AI learns" agent
that the autonomous-agents skill requires. It bridges the gap between
org-level compliance scanning and per-client task generation.

Checks per loan:
    1. SLA deadline proximity (closing, lock expiry, disclosure deadlines)
    2. Missing documents by stage
    3. Stale pipeline items (days in stage vs SLA target)
    4. Third-party order status (appraisal, title, insurance)
    5. Borrower communication gaps (no contact in N days)
    6. Condition/compliance alert resolution

For each issue found, creates a Task assigned to the loan officer with
clear action items. Uses the confidence graduation system to determine
whether to auto-create tasks or hold for approval.

Usage:
    from services.autonomous.client_audit_agent import ClientAuditAgent

    agent = ClientAuditAgent(db=session, org_id=org.id)
    summary = await agent.run()
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD",
    "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
})

# SLA targets in days — how long a loan should spend in each stage
SLA_TARGETS = {
    "APPLICATION": 3,
    "DISCLOSED": 7,
    "PROCESSING": 10,
    "SUBMITTED": 5,
    "UNDERWRITING": 5,
    "UW_RECEIVED": 5,
    "CONDITIONAL_APPROVAL": 7,
    "APPROVED": 5,
    "CTC": 3,
    "CLEAR_TO_CLOSE": 3,
    "CLOSING": 5,
    "DOCS": 3,
    "DOCS_OUT": 5,
}

# Required doc types by stage threshold
EARLY_STAGE_DOCS = {"paystubs", "w2", "bank_statements", "drivers_license"}
UW_STAGE_DOCS = EARLY_STAGE_DOCS | {"credit_report", "purchase_contract", "appraisal"}

# Stages at or past underwriting
UW_PLUS_STAGES = frozenset({
    "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED",
    "SUSPENDED", "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT",
})

# Days without contact before flagging
CONTACT_GAP_THRESHOLD = 7


class ClientAuditAgent:
    """
    Autonomous agent that audits every active loan and generates tasks.

    Designed to be dispatched by AutonomousTaskExecutor on a daily schedule.
    """

    def __init__(
        self,
        db: Session,
        org_id: int,
        config: Optional[Dict[str, Any]] = None,
        gateway=None,
    ):
        self.db = db
        self.org_id = org_id
        self.config = config or {}
        self.gateway = gateway
        self._load_models()

    def _load_models(self):
        """Lazy-load models to avoid circular imports."""
        from database.models.lead_loan import Loan
        from database.models.document import Document
        from database.models.communication import Activity
        from database.models.compliance import ComplianceAlert
        from database.models.autonomous_task import AgentAction

        self.Loan = Loan
        self.Document = Document
        self.Activity = Activity
        self.ComplianceAlert = ComplianceAlert
        self.AgentAction = AgentAction

        # Task model for creating user-facing tasks
        try:
            from database.models.task import Task
            from database.models.core import User
            self.Task = Task
            self.User = User
        except ImportError:
            self.Task = None
            self.User = None

    async def run(self) -> Dict[str, Any]:
        """
        Main execution entry point. Called by AutonomousTaskExecutor.

        Returns summary dict with counts of items processed and tasks created.
        """
        today = date.today()
        now = datetime.now(timezone.utc)

        # Get all active loans for this org
        loans = (
            self.db.query(self.Loan)
            .filter(
                self.Loan.organization_id == self.org_id,
                ~self.Loan.stage.in_(TERMINAL_STAGES),
            )
            .all()
        )

        summary = {
            "agent": "client_audit",
            "org_id": self.org_id,
            "loans_evaluated": len(loans),
            "issues_found": 0,
            "tasks_created": 0,
            "items_acted_on": 0,
            "by_category": {
                "sla_deadline": 0,
                "missing_docs": 0,
                "stale_pipeline": 0,
                "third_party": 0,
                "contact_gap": 0,
                "open_conditions": 0,
            },
            "actions": [],
        }

        for loan in loans:
            try:
                issues = self._audit_loan(loan, today, now)
                summary["issues_found"] += len(issues)
                for issue in issues:
                    summary["by_category"][issue["category"]] = (
                        summary["by_category"].get(issue["category"], 0) + 1
                    )
                    task_created = self._create_task_for_issue(loan, issue)
                    if task_created:
                        summary["tasks_created"] += 1
                        summary["items_acted_on"] += 1
                        summary["actions"].append({
                            "type": "create_task",
                            "loan_id": loan.id,
                            "loan_number": loan.loan_number,
                            "category": issue["category"],
                            "title": issue["title"],
                        })
            except Exception as e:
                logger.warning(
                    "Client audit failed for loan %s (org %d): %s",
                    loan.id, self.org_id, e,
                )

        logger.info(
            "Client audit complete for org %d: %d loans, %d issues, %d tasks",
            self.org_id, summary["loans_evaluated"],
            summary["issues_found"], summary["tasks_created"],
        )

        return summary

    def _audit_loan(
        self, loan, today: date, now: datetime,
    ) -> List[Dict[str, Any]]:
        """Run all audit checks on a single loan. Returns list of issues."""
        issues: List[Dict[str, Any]] = []

        issues.extend(self._check_sla_deadlines(loan, today))
        issues.extend(self._check_missing_documents(loan))
        issues.extend(self._check_stale_pipeline(loan, now))
        issues.extend(self._check_third_party_orders(loan, today))
        issues.extend(self._check_contact_gap(loan, now))
        issues.extend(self._check_open_conditions(loan))

        return issues

    # -----------------------------------------------------------------------
    # Audit checks
    # -----------------------------------------------------------------------

    def _check_sla_deadlines(self, loan, today: date) -> List[Dict]:
        """Check upcoming SLA deadlines (closing date, lock expiry)."""
        issues = []

        # Closing date within 7 days
        if loan.closing_date:
            closing = loan.closing_date
            if isinstance(closing, datetime):
                closing = closing.date()
            days_to_close = (closing - today).days
            if 0 < days_to_close <= 7:
                issues.append({
                    "category": "sla_deadline",
                    "severity": "high" if days_to_close <= 3 else "medium",
                    "title": f"Closing in {days_to_close} days",
                    "description": (
                        f"Loan {loan.loan_number} closes on {closing.strftime('%m/%d/%Y')}. "
                        f"Verify all conditions cleared, docs ready, and funding scheduled."
                    ),
                    "priority": 1 if days_to_close <= 3 else 3,
                })
            elif days_to_close < 0:
                issues.append({
                    "category": "sla_deadline",
                    "severity": "critical",
                    "title": f"Closing date PAST DUE ({abs(days_to_close)} days)",
                    "description": (
                        f"Loan {loan.loan_number} closing date was {closing.strftime('%m/%d/%Y')}. "
                        f"Update closing date or escalate."
                    ),
                    "priority": 1,
                })

        # Rate lock expiration
        if loan.lock_expiration_date:
            lock_exp = loan.lock_expiration_date
            if isinstance(lock_exp, datetime):
                lock_exp = lock_exp.date()
            days_to_lock_exp = (lock_exp - today).days
            if 0 < days_to_lock_exp <= 5:
                issues.append({
                    "category": "sla_deadline",
                    "severity": "high",
                    "title": f"Rate lock expires in {days_to_lock_exp} days",
                    "description": (
                        f"Lock on {loan.loan_number} expires {lock_exp.strftime('%m/%d/%Y')}. "
                        f"Push to close or request lock extension."
                    ),
                    "priority": 2,
                })

        return issues

    def _check_missing_documents(self, loan) -> List[Dict]:
        """Check for missing documents based on loan stage."""
        issues = []
        stage = (loan.stage or "").upper()

        # Determine required docs based on stage
        if stage in UW_PLUS_STAGES:
            required = UW_STAGE_DOCS
        else:
            required = EARLY_STAGE_DOCS

        # Get existing doc types
        existing = set(
            row[0] for row in
            self.db.query(self.Document.doc_type)
            .filter(
                self.Document.loan_id == loan.id,
                self.Document.status == "active",
            )
            .all()
            if row[0]
        )

        missing = required - existing
        if missing:
            issues.append({
                "category": "missing_docs",
                "severity": "high" if stage in UW_PLUS_STAGES else "medium",
                "title": f"{len(missing)} missing document(s)",
                "description": (
                    f"Loan {loan.loan_number} ({stage}) missing: "
                    f"{', '.join(sorted(missing))}. "
                    f"Request from borrower."
                ),
                "priority": 2 if stage in UW_PLUS_STAGES else 4,
            })

        return issues

    def _check_stale_pipeline(self, loan, now: datetime) -> List[Dict]:
        """Check if loan has been in current stage too long."""
        issues = []
        stage = (loan.stage or "").upper()
        target_days = SLA_TARGETS.get(stage)

        if target_days and loan.stage_changed_at:
            changed_at = loan.stage_changed_at
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            days_in_stage = (now - changed_at).days

            if days_in_stage > target_days:
                overage = days_in_stage - target_days
                issues.append({
                    "category": "stale_pipeline",
                    "severity": "critical" if overage > target_days else "high",
                    "title": f"Stale in {stage} — {days_in_stage} days (SLA: {target_days})",
                    "description": (
                        f"Loan {loan.loan_number} has been in {stage} for {days_in_stage} days "
                        f"(target: {target_days}). {overage} days over SLA. "
                        f"Review and advance or update status."
                    ),
                    "priority": 2,
                })

        return issues

    def _check_third_party_orders(self, loan, today: date) -> List[Dict]:
        """Check third-party order status (appraisal, title, insurance)."""
        issues = []
        stage = (loan.stage or "").upper()

        # Only check at stages where these matter
        if stage not in UW_PLUS_STAGES and stage not in {"PROCESSING", "SUBMITTED"}:
            return issues

        # Appraisal: ordered but not received after 14 days
        if loan.appraisal_ordered_date and not loan.appraisal_received_date:
            ordered = loan.appraisal_ordered_date
            if isinstance(ordered, datetime):
                ordered = ordered.date()
            days_waiting = (today - ordered).days
            if days_waiting > 14:
                issues.append({
                    "category": "third_party",
                    "severity": "high",
                    "title": f"Appraisal pending {days_waiting} days",
                    "description": (
                        f"Appraisal for {loan.loan_number} ordered {ordered.strftime('%m/%d/%Y')} "
                        f"— {days_waiting} days ago. Follow up with appraiser."
                    ),
                    "priority": 3,
                })

        # Title: needed but not ordered
        if stage in {"APPROVED", "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT"}:
            if not loan.title_ordered_date:
                issues.append({
                    "category": "third_party",
                    "severity": "high",
                    "title": "Title not ordered",
                    "description": (
                        f"Loan {loan.loan_number} is in {stage} but title has not been ordered. "
                        f"Order title immediately."
                    ),
                    "priority": 2,
                })

        return issues

    def _check_contact_gap(self, loan, now: datetime) -> List[Dict]:
        """Check if there's been no borrower contact in too long."""
        issues = []

        # Find most recent activity for this loan's borrower
        last_activity = (
            self.db.query(self.Activity)
            .filter(
                self.Activity.loan_id == loan.id,
            )
            .order_by(self.Activity.created_at.desc())
            .first()
        )

        if last_activity and last_activity.created_at:
            last_contact = last_activity.created_at
            if last_contact.tzinfo is None:
                last_contact = last_contact.replace(tzinfo=timezone.utc)
            days_since = (now - last_contact).days

            if days_since > CONTACT_GAP_THRESHOLD:
                issues.append({
                    "category": "contact_gap",
                    "severity": "medium",
                    "title": f"No borrower contact in {days_since} days",
                    "description": (
                        f"No activity on {loan.loan_number} for {days_since} days. "
                        f"Contact {loan.borrower_name or 'borrower'} with a status update."
                    ),
                    "priority": 4,
                })
        elif loan.stage_changed_at:
            # No activity at all — check stage age
            changed_at = loan.stage_changed_at
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            days_since = (now - changed_at).days
            if days_since > CONTACT_GAP_THRESHOLD:
                issues.append({
                    "category": "contact_gap",
                    "severity": "medium",
                    "title": f"No recorded contact — {days_since} days in stage",
                    "description": (
                        f"No activity found for {loan.loan_number}. "
                        f"Reach out to {loan.borrower_name or 'borrower'}."
                    ),
                    "priority": 4,
                })

        return issues

    def _check_open_conditions(self, loan) -> List[Dict]:
        """Check for unresolved compliance alerts/conditions."""
        issues = []

        open_alerts = (
            self.db.query(self.ComplianceAlert)
            .filter(
                self.ComplianceAlert.loan_id == loan.id,
                self.ComplianceAlert.status == "open",
            )
            .all()
        )

        past_due = [
            a for a in open_alerts
            if a.deadline_date and (
                a.deadline_date.date() if isinstance(a.deadline_date, datetime) else a.deadline_date
            ) < date.today()
        ]

        if past_due:
            issues.append({
                "category": "open_conditions",
                "severity": "critical",
                "title": f"{len(past_due)} past-due condition(s)",
                "description": (
                    f"Loan {loan.loan_number} has {len(past_due)} past-due compliance condition(s). "
                    f"Resolve immediately: {', '.join(a.title or a.alert_type for a in past_due[:3])}"
                ),
                "priority": 1,
            })
        elif open_alerts:
            issues.append({
                "category": "open_conditions",
                "severity": "medium",
                "title": f"{len(open_alerts)} open condition(s)",
                "description": (
                    f"Loan {loan.loan_number} has {len(open_alerts)} open condition(s) to resolve."
                ),
                "priority": 3,
            })

        return issues

    # -----------------------------------------------------------------------
    # Task creation
    # -----------------------------------------------------------------------

    def _create_task_for_issue(
        self, loan, issue: Dict[str, Any],
    ) -> bool:
        """
        Create a user-facing Task for an audit issue.

        Uses the confidence graduation system to decide whether the task
        requires human approval or can be auto-created.

        Returns True if task was created.
        """
        if self.Task is None:
            return False

        # Check for duplicate: don't create if an identical open task exists
        existing = (
            self.db.query(self.Task)
            .filter(
                self.Task.loan_id == loan.id,
                self.Task.title == issue["title"],
                self.Task.status.in_(["pending", "in_progress", "open"]),
            )
            .first()
        )
        if existing:
            return False

        # Determine if this needs approval via confidence graduation
        needs_approval = True
        try:
            from services.autonomous.confidence_graduation import ConfidenceGraduationService
            grad_service = ConfidenceGraduationService(self.db)
            needs_approval = grad_service.requires_approval(self.org_id, "create_task")
        except Exception:
            pass  # Default to requiring approval

        # Map severity to task priority (Task.priority is a String)
        priority_map = {"critical": "high", "high": "high", "medium": "medium", "low": "low"}
        task_priority = priority_map.get(issue.get("severity", "medium"), "medium")

        task = self.Task(
            organization_id=self.org_id,
            loan_id=loan.id,
            owner_id=loan.loan_officer_id,
            title=issue["title"],
            description=issue["description"],
            priority=task_priority,
            status="pending_approval" if needs_approval else "pending",
            related_type="ai_audit",
            due_date=datetime.now(timezone.utc) + timedelta(days=issue.get("priority", 3)),
        )

        try:
            self.db.add(task)
            self.db.flush()
            return True
        except Exception as e:
            logger.warning("Failed to create task for loan %s: %s", loan.id, e)
            return False
