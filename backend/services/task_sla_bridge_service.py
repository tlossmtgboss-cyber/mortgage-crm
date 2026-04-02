"""
Task SLA Bridge Service

Bridges tasks with SLA milestone tracking, handling the creation and management
of SLA-linked tasks for leads and loans.

Key responsibilities:
- Create tasks from SLA milestone definitions
- Update task SLA status based on deadline proximity
- Query tasks by SLA milestone type
- Track and report on SLA compliance
- Generate SLA alerts and escalations
"""

import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# =============================================================================
# SLA MILESTONE DEFINITIONS
# =============================================================================

# Standard mortgage SLA milestones with default days allowed
SLA_MILESTONE_DEFINITIONS = {
    # TRID Compliance Milestones
    "initial_disclosure": {
        "name": "Initial Disclosure (LE)",
        "description": "Send Loan Estimate within 3 business days of application",
        "trigger_field": "application_date",
        "days_allowed": 3,
        "business_days": True,
        "regulatory": True,
    },
    "closing_disclosure": {
        "name": "Closing Disclosure (CD)",
        "description": "Send Closing Disclosure at least 3 business days before closing",
        "trigger_field": "expected_close_date",
        "days_allowed": -3,  # Negative means days BEFORE the trigger date
        "business_days": True,
        "regulatory": True,
    },

    # Processing Milestones
    "appraisal_order": {
        "name": "Appraisal Order",
        "description": "Order appraisal within target timeframe",
        "trigger_field": "application_date",
        "days_allowed": 5,
        "business_days": True,
        "regulatory": False,
    },
    "title_order": {
        "name": "Title Order",
        "description": "Order title work within target timeframe",
        "trigger_field": "application_date",
        "days_allowed": 3,
        "business_days": True,
        "regulatory": False,
    },
    "submit_to_underwriting": {
        "name": "Submit to Underwriting",
        "description": "Submit complete file to underwriting",
        "trigger_field": "application_date",
        "days_allowed": 7,
        "business_days": True,
        "regulatory": False,
    },

    # Underwriting Milestones
    "initial_uw_decision": {
        "name": "Initial UW Decision",
        "description": "Receive initial underwriting decision",
        "trigger_field": "submitted_to_uw_at",
        "days_allowed": 3,
        "business_days": True,
        "regulatory": False,
    },
    "conditions_review": {
        "name": "Conditions Review",
        "description": "Review and clear conditions",
        "trigger_field": "conditions_received_at",
        "days_allowed": 2,
        "business_days": True,
        "regulatory": False,
    },
    "clear_to_close": {
        "name": "Clear to Close",
        "description": "Obtain clear to close status",
        "trigger_field": "final_approval_at",
        "days_allowed": 2,
        "business_days": True,
        "regulatory": False,
    },

    # Closing Milestones
    "closing_scheduled": {
        "name": "Schedule Closing",
        "description": "Schedule closing appointment",
        "trigger_field": "clear_to_close_at",
        "days_allowed": 1,
        "business_days": True,
        "regulatory": False,
    },
    "docs_to_title": {
        "name": "Docs to Title",
        "description": "Send closing docs to title company",
        "trigger_field": "expected_close_date",
        "days_allowed": -2,
        "business_days": True,
        "regulatory": False,
    },

    # Post-Closing Milestones
    "funding": {
        "name": "Funding",
        "description": "Fund the loan after closing",
        "trigger_field": "closing_date",
        "days_allowed": 1,
        "business_days": True,
        "regulatory": False,
    },
    "welcome_call": {
        "name": "Welcome Call",
        "description": "Make welcome call after funding",
        "trigger_field": "funded_at",
        "days_allowed": 1,
        "business_days": True,
        "regulatory": False,
    },
}

# SLA Status thresholds (percentage of time elapsed)
SLA_STATUS_THRESHOLDS = {
    "on_track": 0.5,      # Less than 50% of time elapsed
    "at_risk": 0.75,      # 50-75% of time elapsed
    "critical": 0.90,     # 75-90% of time elapsed
    "overdue": 1.0,       # 100%+ of time elapsed
}


class TaskSLABridgeService:
    """
    Service for bridging tasks with SLA milestone tracking.

    Provides functionality to:
    - Create SLA-linked tasks for loans
    - Track SLA compliance status
    - Generate SLA reports and alerts
    - Update task statuses based on deadlines
    """

    def __init__(self, db: Session):
        self.db = db
        self._load_models()

    def _load_models(self):
        """Load required models dynamically to avoid circular imports."""
        from database.models import Lead, Loan, Task, User

        self.Lead = Lead
        self.Loan = Loan
        self.Task = Task
        self.User = User

    # =========================================================================
    # TASK CREATION FROM SLA MILESTONES
    # =========================================================================

    def create_sla_task(
        self,
        loan_id: int,
        milestone_type: str,
        owner_id: int,
        trigger_date: datetime = None,
        custom_days_allowed: int = None,
        custom_description: str = None,
    ) -> Dict[str, Any]:
        """
        Create a task linked to an SLA milestone.

        Args:
            loan_id: ID of the loan
            milestone_type: Type of SLA milestone (e.g., 'initial_disclosure')
            owner_id: User ID to assign the task to
            trigger_date: Override the trigger date (defaults to loan field)
            custom_days_allowed: Override the default days allowed
            custom_description: Custom task description

        Returns:
            Dict with task creation result
        """
        try:
            # Get milestone definition
            milestone_def = SLA_MILESTONE_DEFINITIONS.get(milestone_type)
            if not milestone_def:
                return {"success": False, "error": f"Unknown milestone type: {milestone_type}"}

            # Get loan data
            loan = self.db.query(self.Loan).filter(self.Loan.id == loan_id).first()
            if not loan:
                return {"success": False, "error": f"Loan {loan_id} not found"}

            # Determine trigger date
            if not trigger_date:
                trigger_field = milestone_def["trigger_field"]
                trigger_date = getattr(loan, trigger_field, None)
                if not trigger_date:
                    return {
                        "success": False,
                        "error": f"Trigger field '{trigger_field}' not set on loan"
                    }

            # Ensure trigger_date is timezone-aware
            if trigger_date.tzinfo is None:
                trigger_date = trigger_date.replace(tzinfo=timezone.utc)

            # Calculate milestone date (deadline)
            days_allowed = custom_days_allowed or milestone_def["days_allowed"]
            if milestone_def.get("business_days", False):
                milestone_date = self._add_business_days(trigger_date, days_allowed)
            else:
                milestone_date = trigger_date + timedelta(days=days_allowed)

            # Build task title and description
            borrower_name = f"{loan.borrower_first_name or ''} {loan.borrower_last_name or ''}".strip()
            title = f"[SLA] {milestone_def['name']} - {borrower_name or f'Loan #{loan_id}'}"

            description = custom_description or milestone_def["description"]
            if milestone_def.get("regulatory"):
                description = f"⚠️ REGULATORY REQUIREMENT\n\n{description}"

            # Determine initial SLA status
            sla_status = self._calculate_sla_status(trigger_date, milestone_date)

            # Determine priority based on regulatory status and time remaining
            priority = "high" if milestone_def.get("regulatory") else "medium"
            if sla_status in ["critical", "overdue"]:
                priority = "urgent"

            # Create the task
            self.db.execute(text("""
                INSERT INTO tasks (
                    title, description, status, priority,
                    due_date, owner_id, loan_id,
                    sla_milestone_type, sla_date_field,
                    milestone_date, sla_days_allowed, sla_status,
                    created_at, updated_at
                ) VALUES (
                    :title, :description, 'pending', :priority,
                    :due_date, :owner_id, :loan_id,
                    :milestone_type, :date_field,
                    :milestone_date, :days_allowed, :sla_status,
                    NOW(), NOW()
                )
            """), {
                "title": title,
                "description": description,
                "priority": priority,
                "due_date": milestone_date,
                "owner_id": owner_id,
                "loan_id": loan_id,
                "milestone_type": milestone_type,
                "date_field": milestone_def["trigger_field"],
                "milestone_date": milestone_date,
                "days_allowed": abs(days_allowed),
                "sla_status": sla_status,
            })
            self.db.commit()

            # Get the created task ID
            result = self.db.execute(text("""
                SELECT id FROM tasks
                WHERE loan_id = :loan_id
                AND sla_milestone_type = :milestone_type
                ORDER BY id DESC LIMIT 1
            """), {"loan_id": loan_id, "milestone_type": milestone_type}).fetchone()

            task_id = result[0] if result else None

            logger.info(f"Created SLA task {task_id} for loan {loan_id}: {milestone_type}")

            return {
                "success": True,
                "task_id": task_id,
                "milestone_type": milestone_type,
                "milestone_date": milestone_date.isoformat(),
                "sla_status": sla_status,
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create SLA task: {e}")
            return {"success": False, "error": "Internal server error"}

    def create_loan_sla_tasks(
        self,
        loan_id: int,
        owner_id: int,
        milestone_types: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Create multiple SLA tasks for a loan.

        Args:
            loan_id: ID of the loan
            owner_id: User ID to assign tasks to
            milestone_types: List of milestone types to create (defaults to all applicable)

        Returns:
            Dict with creation results
        """
        try:
            loan = self.db.query(self.Loan).filter(self.Loan.id == loan_id).first()
            if not loan:
                return {"success": False, "error": f"Loan {loan_id} not found"}

            if not milestone_types:
                # Determine applicable milestones based on loan stage
                milestone_types = self._get_applicable_milestones(loan)

            results = []
            for milestone_type in milestone_types:
                result = self.create_sla_task(
                    loan_id=loan_id,
                    milestone_type=milestone_type,
                    owner_id=owner_id
                )
                results.append({
                    "milestone_type": milestone_type,
                    "result": result
                })

            successful = [r for r in results if r["result"].get("success")]

            return {
                "success": True,
                "total_created": len(successful),
                "total_attempted": len(results),
                "results": results,
            }

        except Exception as e:
            logger.error(f"Failed to create loan SLA tasks: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # SLA STATUS TRACKING
    # =========================================================================

    def update_sla_statuses(self, loan_id: int = None) -> Dict[str, Any]:
        """
        Update SLA status for all active SLA tasks.

        Args:
            loan_id: Optional loan ID to filter (updates all if not provided)

        Returns:
            Dict with update results
        """
        try:
            # Get all active SLA tasks
            params = {}
            loan_filter = ""
            if loan_id:
                loan_filter = "AND loan_id = :loan_id"
                params["loan_id"] = loan_id

            query = f"""
                SELECT id, sla_milestone_type, sla_date_field,
                       milestone_date, sla_status, loan_id
                FROM tasks
                WHERE sla_milestone_type IS NOT NULL
                AND status NOT IN ('completed', 'cancelled')
                {loan_filter}
            """
            tasks = self.db.execute(text(query), params).fetchall()

            updated_count = 0
            for task in tasks:
                task_id = task[0]
                milestone_date = task[3]
                current_status = task[4]
                task_loan_id = task[5]

                if not milestone_date:
                    continue

                # Get trigger date from loan
                trigger_date = self._get_trigger_date(
                    task_loan_id,
                    task[2]  # sla_date_field
                )
                if not trigger_date:
                    continue

                # Calculate new status
                new_status = self._calculate_sla_status(trigger_date, milestone_date)

                if new_status != current_status:
                    self.db.execute(text("""
                        UPDATE tasks
                        SET sla_status = :status, updated_at = NOW()
                        WHERE id = :task_id
                    """), {"status": new_status, "task_id": task_id})
                    updated_count += 1

            self.db.commit()

            logger.info(f"Updated SLA status for {updated_count} tasks")

            return {
                "success": True,
                "tasks_checked": len(tasks),
                "tasks_updated": updated_count,
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to update SLA statuses: {e}")
            return {"success": False, "error": "Internal server error"}

    def get_sla_summary(
        self,
        loan_id: int = None,
        owner_id: int = None,
        organization_id: int = None,
    ) -> Dict[str, Any]:
        """
        Get SLA compliance summary.

        Args:
            loan_id: Optional filter by loan
            owner_id: Optional filter by task owner
            organization_id: Optional filter by organization

        Returns:
            Dict with SLA summary statistics
        """
        try:
            params = {}
            filters = ["t.sla_milestone_type IS NOT NULL"]

            if loan_id:
                filters.append("t.loan_id = :loan_id")
                params["loan_id"] = loan_id
            if owner_id:
                filters.append("t.owner_id = :owner_id")
                params["owner_id"] = owner_id
            if organization_id:
                filters.append("l.organization_id = :org_id")
                params["org_id"] = organization_id

            where_clause = " AND ".join(filters)

            # Get counts by status
            query = f"""
                SELECT
                    t.sla_status,
                    COUNT(*) as count
                FROM tasks t
                LEFT JOIN loans l ON l.id = t.loan_id
                WHERE {where_clause}
                AND t.status NOT IN ('completed', 'cancelled')
                GROUP BY t.sla_status
            """
            status_counts = self.db.execute(text(query), params).fetchall()

            # Get counts by milestone type
            query = f"""
                SELECT
                    t.sla_milestone_type,
                    t.sla_status,
                    COUNT(*) as count
                FROM tasks t
                LEFT JOIN loans l ON l.id = t.loan_id
                WHERE {where_clause}
                AND t.status NOT IN ('completed', 'cancelled')
                GROUP BY t.sla_milestone_type, t.sla_status
            """
            milestone_counts = self.db.execute(text(query), params).fetchall()

            # Build summary
            by_status = {row[0]: row[1] for row in status_counts}

            by_milestone = {}
            for row in milestone_counts:
                milestone = row[0]
                status = row[1]
                count = row[2]
                if milestone not in by_milestone:
                    by_milestone[milestone] = {}
                by_milestone[milestone][status] = count

            total_active = sum(by_status.values())
            overdue_count = by_status.get("overdue", 0)
            critical_count = by_status.get("critical", 0)

            return {
                "success": True,
                "total_active_sla_tasks": total_active,
                "by_status": by_status,
                "by_milestone_type": by_milestone,
                "compliance_rate": round((1 - (overdue_count / total_active)) * 100, 1) if total_active > 0 else 100,
                "at_risk_count": critical_count + by_status.get("at_risk", 0),
                "overdue_count": overdue_count,
            }

        except Exception as e:
            logger.error(f"Failed to get SLA summary: {e}")
            return {"success": False, "error": "Internal server error"}

    def get_overdue_sla_tasks(
        self,
        owner_id: int = None,
        organization_id: int = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Get list of overdue SLA tasks for alerting.

        Returns:
            Dict with overdue task details
        """
        try:
            params = {"limit": limit}
            filters = [
                "t.sla_milestone_type IS NOT NULL",
                "t.sla_status IN ('overdue', 'critical')",
                "t.status NOT IN ('completed', 'cancelled')"
            ]

            if owner_id:
                filters.append("t.owner_id = :owner_id")
                params["owner_id"] = owner_id
            if organization_id:
                filters.append("l.organization_id = :org_id")
                params["org_id"] = organization_id

            where_clause = " AND ".join(filters)

            query = f"""
                SELECT
                    t.id, t.title, t.sla_milestone_type, t.sla_status,
                    t.milestone_date, t.owner_id, t.loan_id,
                    l.borrower_first_name, l.borrower_last_name,
                    u.full_name as owner_name
                FROM tasks t
                LEFT JOIN loans l ON l.id = t.loan_id
                LEFT JOIN users u ON u.id = t.owner_id
                WHERE {where_clause}
                ORDER BY t.milestone_date ASC
                LIMIT :limit
            """
            tasks = self.db.execute(text(query), params).fetchall()

            now = datetime.now(timezone.utc)

            overdue_tasks = []
            for task in tasks:
                milestone_date = task[4]
                if milestone_date and milestone_date.tzinfo is None:
                    milestone_date = milestone_date.replace(tzinfo=timezone.utc)

                days_overdue = (now - milestone_date).days if milestone_date and now > milestone_date else 0

                overdue_tasks.append({
                    "task_id": task[0],
                    "title": task[1],
                    "milestone_type": task[2],
                    "sla_status": task[3],
                    "milestone_date": milestone_date.isoformat() if milestone_date else None,
                    "days_overdue": days_overdue,
                    "owner_id": task[5],
                    "owner_name": task[9],
                    "loan_id": task[6],
                    "borrower_name": f"{task[7] or ''} {task[8] or ''}".strip(),
                })

            return {
                "success": True,
                "count": len(overdue_tasks),
                "tasks": overdue_tasks,
            }

        except Exception as e:
            logger.error(f"Failed to get overdue SLA tasks: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # MILESTONE COMPLETION
    # =========================================================================

    def complete_sla_milestone(
        self,
        loan_id: int,
        milestone_type: str,
        completed_by_id: int = None,
        completion_notes: str = None,
    ) -> Dict[str, Any]:
        """
        Mark an SLA milestone as completed.

        Args:
            loan_id: ID of the loan
            milestone_type: Type of milestone completed
            completed_by_id: User who completed the milestone
            completion_notes: Optional notes about completion

        Returns:
            Dict with completion result
        """
        try:
            # Find the active SLA task for this milestone
            task = self.db.execute(text("""
                SELECT id, milestone_date, sla_status
                FROM tasks
                WHERE loan_id = :loan_id
                AND sla_milestone_type = :milestone_type
                AND status NOT IN ('completed', 'cancelled')
                ORDER BY created_at DESC
                LIMIT 1
            """), {"loan_id": loan_id, "milestone_type": milestone_type}).fetchone()

            if not task:
                return {"success": False, "error": "No active SLA task found for this milestone"}

            task_id = task[0]
            milestone_date = task[1]
            final_status = task[2]

            # Determine if completed on time
            now = datetime.now(timezone.utc)
            if milestone_date:
                if milestone_date.tzinfo is None:
                    milestone_date = milestone_date.replace(tzinfo=timezone.utc)
                completed_on_time = now <= milestone_date
            else:
                completed_on_time = True

            # Update task status
            description_append = f"\n\n✅ Completed on {now.strftime('%Y-%m-%d %H:%M')}"
            if completion_notes:
                description_append += f"\nNotes: {completion_notes}"
            if not completed_on_time:
                description_append += f"\n⚠️ Completed after SLA deadline"

            self.db.execute(text("""
                UPDATE tasks
                SET status = 'completed',
                    completed_at = NOW(),
                    sla_status = :final_status,
                    description = description || :notes,
                    updated_at = NOW()
                WHERE id = :task_id
            """), {
                "task_id": task_id,
                "final_status": "completed" if completed_on_time else "completed_late",
                "notes": description_append,
            })
            self.db.commit()

            logger.info(f"Completed SLA milestone {milestone_type} for loan {loan_id}")

            return {
                "success": True,
                "task_id": task_id,
                "milestone_type": milestone_type,
                "completed_on_time": completed_on_time,
                "final_status": "completed" if completed_on_time else "completed_late",
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to complete SLA milestone: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # PRIVATE HELPER METHODS
    # =========================================================================

    def _calculate_sla_status(
        self,
        trigger_date: datetime,
        milestone_date: datetime,
    ) -> str:
        """Calculate current SLA status based on time elapsed."""
        now = datetime.now(timezone.utc)

        # Ensure timezone awareness
        if trigger_date.tzinfo is None:
            trigger_date = trigger_date.replace(tzinfo=timezone.utc)
        if milestone_date.tzinfo is None:
            milestone_date = milestone_date.replace(tzinfo=timezone.utc)

        # Handle negative days (milestone before trigger - e.g., CD before closing)
        if milestone_date < trigger_date:
            # For reverse milestones, check if we're past the deadline
            if now > milestone_date:
                return "overdue"
            days_remaining = (milestone_date - now).days
            total_days = (trigger_date - milestone_date).days
            if total_days == 0:
                return "critical"
            elapsed_ratio = 1 - (days_remaining / total_days)
        else:
            # Standard forward milestone
            if now > milestone_date:
                return "overdue"

            total_time = (milestone_date - trigger_date).total_seconds()
            elapsed_time = (now - trigger_date).total_seconds()

            if total_time == 0:
                return "critical"

            elapsed_ratio = elapsed_time / total_time

        # Determine status based on elapsed ratio
        if elapsed_ratio >= SLA_STATUS_THRESHOLDS["overdue"]:
            return "overdue"
        elif elapsed_ratio >= SLA_STATUS_THRESHOLDS["critical"]:
            return "critical"
        elif elapsed_ratio >= SLA_STATUS_THRESHOLDS["at_risk"]:
            return "at_risk"
        else:
            return "on_track"

    def _add_business_days(self, start_date: datetime, days: int) -> datetime:
        """Add business days to a date, handling negative days.

        SLA-006: Delegates to PortalCloseOnTimeService for holiday-aware
        calculation when available, falls back to weekend-only skip.
        """
        try:
            from services.portal_close_on_time_service import PortalCloseOnTimeService
            portal_service = PortalCloseOnTimeService(self.db)
            result_date = portal_service.add_business_days(start_date.date() if isinstance(start_date, datetime) else start_date, days)
            # Preserve time component from original datetime
            if isinstance(start_date, datetime):
                return datetime.combine(result_date, start_date.time(), tzinfo=start_date.tzinfo)
            return datetime.combine(result_date, datetime.min.time(), tzinfo=timezone.utc)
        except Exception as e:
            logger.debug(f"Holiday calendar unavailable, using weekend-only fallback: {e}")

        # Fallback: weekend-only skip
        current = start_date
        remaining = abs(days)
        direction = 1 if days >= 0 else -1

        while remaining > 0:
            current += timedelta(days=direction)
            # Skip weekends (Saturday=5, Sunday=6)
            if current.weekday() < 5:
                remaining -= 1

        return current

    def _get_trigger_date(self, loan_id: int, date_field: str) -> Optional[datetime]:
        """Get the trigger date from a loan."""
        try:
            query = f"""
                SELECT {date_field} FROM loans WHERE id = :loan_id
            """
            result = self.db.execute(text(query), {"loan_id": loan_id}).fetchone()

            if result and result[0]:
                trigger_date = result[0]
                if isinstance(trigger_date, date) and not isinstance(trigger_date, datetime):
                    trigger_date = datetime.combine(trigger_date, datetime.min.time())
                if trigger_date.tzinfo is None:
                    trigger_date = trigger_date.replace(tzinfo=timezone.utc)
                return trigger_date
            return None
        except SQLAlchemyError as e:
            logger.error(f"Failed to get trigger date: {e}")
            return None

    def _get_applicable_milestones(self, loan) -> List[str]:
        """Determine which milestones are applicable based on loan stage."""
        applicable = []

        # Check which fields are set and determine applicable milestones
        if hasattr(loan, 'application_date') and loan.application_date:
            applicable.extend([
                "initial_disclosure",
                "appraisal_order",
                "title_order",
                "submit_to_underwriting",
            ])

        if hasattr(loan, 'submitted_to_uw_at') and loan.submitted_to_uw_at:
            applicable.append("initial_uw_decision")

        if hasattr(loan, 'conditions_received_at') and loan.conditions_received_at:
            applicable.append("conditions_review")

        if hasattr(loan, 'final_approval_at') and loan.final_approval_at:
            applicable.append("clear_to_close")

        if hasattr(loan, 'clear_to_close_at') and loan.clear_to_close_at:
            applicable.append("closing_scheduled")

        if hasattr(loan, 'expected_close_date') and loan.expected_close_date:
            applicable.extend([
                "closing_disclosure",
                "docs_to_title",
            ])

        if hasattr(loan, 'closing_date') and loan.closing_date:
            applicable.append("funding")

        if hasattr(loan, 'funded_at') and loan.funded_at:
            applicable.append("welcome_call")

        return applicable


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_task_sla_bridge_service(db: Session) -> TaskSLABridgeService:
    """Factory function to get a TaskSLABridgeService instance."""
    return TaskSLABridgeService(db)
