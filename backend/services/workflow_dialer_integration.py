"""
Workflow-Dialer Integration Service

Integrates workflow phone tasks with the Power Dialer system.
Handles routing workflow tasks to dialer queue and processing completion callbacks.

Key responsibilities:
- Queue workflow phone tasks to dialer sessions
- Handle dialer completion callbacks to update workflow tasks
- Manage sibling task cancellation when contact is made
- Track dialer session task to workflow task mapping
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class WorkflowDialerIntegration:
    """
    Integrates workflow tasks with the Power Dialer system.

    Provides methods to:
    - Queue workflow phone tasks for dialing
    - Create dialer sessions from workflow tasks
    - Handle completion callbacks from dialer
    - Update workflow task status based on call outcomes
    """

    def __init__(self, db: Session):
        self.db = db

    def get_phone_tasks_for_dialer(
        self,
        user_id: int = None,
        lead_ids: List[int] = None,
        loan_ids: List[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get workflow phone tasks that can be added to a dialer session.

        Args:
            user_id: Filter by assigned user
            lead_ids: Filter by specific leads
            loan_ids: Filter by specific loans
            limit: Maximum tasks to return

        Returns:
            List of task details suitable for dialer
        """
        params = {"limit": limit}
        filters = [
            "wti.task_type IN ('phone', 'phone_am', 'phone_pm', 'dialer')",
            "wti.status IN ('scheduled', 'pending')",
            "wti.route IN ('task_list', 'dialer_queue')"
        ]

        if user_id:
            filters.append("wti.assigned_user_id = :user_id")
            params["user_id"] = user_id

        if lead_ids:
            filters.append("wti.lead_id = ANY(:lead_ids)")
            params["lead_ids"] = lead_ids

        if loan_ids:
            filters.append("wti.loan_id = ANY(:loan_ids)")
            params["loan_ids"] = loan_ids

        where_clause = " AND ".join(filters)

        dialer_query = (
            "SELECT"
            " wti.id as workflow_task_id,"
            " wti.task_name, wti.task_type,"
            " wti.lead_id, wti.loan_id,"
            " wti.assigned_user_id, wti.scheduled_date,"
            " wti.task_group_key,"
            " COALESCE(l.phone, lo.borrower_phone) as contact_phone,"
            " COALESCE("
            "     CONCAT(l.first_name, ' ', l.last_name),"
            "     CONCAT(lo.borrower_first_name, ' ', lo.borrower_last_name)"
            " ) as contact_name"
            " FROM workflow_task_instances wti"
            " LEFT JOIN leads l ON l.id = wti.lead_id"
            " LEFT JOIN loans lo ON lo.id = wti.loan_id"
            " WHERE " + where_clause
            + " AND COALESCE(l.phone, lo.borrower_phone) IS NOT NULL"
            " ORDER BY wti.scheduled_date ASC, wti.id ASC"
            " LIMIT :limit"
        )
        results = self.db.execute(text(dialer_query), params).fetchall()

        return [
            {
                "workflow_task_id": row[0],
                "task_name": row[1],
                "task_type": row[2],
                "lead_id": row[3],
                "loan_id": row[4],
                "assigned_user_id": row[5],
                "scheduled_date": row[6].isoformat() if row[6] else None,
                "task_group_key": row[7],
                "contact_phone": row[8],
                "contact_name": row[9] or "Unknown"
            }
            for row in results
        ]

    def create_dialer_session_from_workflow(
        self,
        agent_id: int,
        workflow_task_ids: List[int],
        base_url: str
    ) -> Dict[str, Any]:
        """
        Create a dialer session from workflow tasks.

        This creates a bridge between workflow tasks and the dialer system.

        Args:
            agent_id: Agent/user ID for the session
            workflow_task_ids: List of workflow task instance IDs
            base_url: Base URL for telephony callbacks

        Returns:
            Dict with session info or error
        """
        try:
            from database.enums import DialerSessionStatus, DialerTaskStatus
            from database.models import DialerSession, DialerSessionTask
            from telephony.dialer_engine import DialerEngine

            # Use the existing dialer engine for session creation
            engine = DialerEngine(self.db, agent_id)

            # Check for existing session
            existing = self.db.query(DialerSession).filter(
                DialerSession.agent_id == agent_id,
                DialerSession.status == DialerSessionStatus.ACTIVE
            ).first()

            if existing:
                return {
                    "success": False,
                    "error": "Agent already has an active dialer session",
                    "existing_session_id": existing.id
                }

            # Get caller ID
            caller_id = engine.get_verified_caller_id()
            if not caller_id:
                return {
                    "success": False,
                    "error": "No verified caller ID configured"
                }

            # Get workflow tasks with contact info
            tasks_data = self._get_workflow_tasks_for_session(workflow_task_ids)

            if not tasks_data:
                return {
                    "success": False,
                    "error": "No valid workflow tasks with contact phone numbers"
                }

            # Create session
            session = DialerSession(
                agent_id=agent_id,
                status=DialerSessionStatus.ACTIVE,
                total_tasks=len(tasks_data),
                completed_tasks=0,
                caller_id_used=caller_id
            )
            self.db.add(session)
            self.db.flush()

            # Add tasks to session with workflow reference
            position = 0
            for task_data in tasks_data:
                session_task = DialerSessionTask(
                    session_id=session.id,
                    original_task_id=None,  # No AITask reference
                    contact_phone=task_data["contact_phone"],
                    contact_name=task_data["contact_name"],
                    lead_id=task_data["lead_id"],
                    loan_id=task_data["loan_id"],
                    status=DialerTaskStatus.PENDING,
                    task_order=position
                )
                self.db.add(session_task)
                self.db.flush()

                # Update workflow task with dialer reference
                self.db.execute(text("""
                    UPDATE workflow_task_instances
                    SET dialer_session_task_id = :session_task_id,
                        status = 'in_progress',
                        updated_at = NOW()
                    WHERE id = :workflow_task_id
                """), {
                    "session_task_id": session_task.id,
                    "workflow_task_id": task_data["workflow_task_id"]
                })

                position += 1

            session.total_tasks = position
            self.db.commit()

            logger.info(f"Created dialer session {session.id} from {position} workflow tasks")

            return {
                "success": True,
                "session_id": session.id,
                "total_tasks": position,
                "workflow_task_ids": workflow_task_ids
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to create dialer session: {e}")
            return {"success": False, "error": "Internal server error"}

    def handle_dialer_task_completion(
        self,
        dialer_session_task_id: int,
        call_status: str,
        call_duration: int = None,
        disposition: str = None,
        notes: str = None
    ) -> Dict[str, Any]:
        """
        Handle completion callback from dialer for a workflow task.

        Updates workflow task status and handles sibling cancellation.

        Args:
            dialer_session_task_id: Dialer session task ID
            call_status: Call outcome (completed, no_answer, failed, etc.)
            call_duration: Call duration in seconds
            disposition: Agent disposition code
            notes: Agent notes

        Returns:
            Dict with update result
        """
        try:
            # Find associated workflow task
            result = self.db.execute(text("""
                SELECT id, task_group_key, linked_task_id
                FROM workflow_task_instances
                WHERE dialer_session_task_id = :session_task_id
            """), {"session_task_id": dialer_session_task_id}).fetchone()

            if not result:
                # No workflow task linked - this is fine, could be a regular dialer task
                logger.debug(f"No workflow task for dialer session task {dialer_session_task_id}")
                return {"success": True, "workflow_task_updated": False}

            workflow_task_id, task_group_key, linked_task_id = result

            # Determine workflow task status
            contact_made = call_status in ['completed', 'answered'] and call_duration and call_duration > 30

            if contact_made:
                new_status = 'completed'
                completion_source = 'dialer'
            elif call_status in ['no_answer', 'busy', 'voicemail']:
                new_status = 'completed'  # Task attempted, move on
                completion_source = 'dialer'
            elif call_status == 'failed':
                new_status = 'failed'
                completion_source = 'dialer'
            else:
                new_status = 'completed'
                completion_source = 'dialer'

            # Update workflow task
            self.db.execute(text("""
                UPDATE workflow_task_instances
                SET status = :status,
                    completion_source = :source,
                    completed_at = NOW(),
                    error_message = :notes,
                    updated_at = NOW()
                WHERE id = :id
            """), {
                "id": workflow_task_id,
                "status": new_status,
                "source": completion_source,
                "notes": f"Call: {call_status}, Duration: {call_duration}s. {notes or ''}"
            })

            # Update linked task if exists
            if linked_task_id:
                self.db.execute(text("""
                    UPDATE tasks
                    SET status = 'completed',
                        completed_at = NOW(),
                        description = COALESCE(description, '') || E'\n[Dialer: ' || :status || ']'
                    WHERE id = :id
                """), {"id": linked_task_id, "status": call_status})

            # Cancel sibling tasks if contact was made
            siblings_cancelled = 0
            if contact_made and task_group_key:
                siblings = self.db.execute(text("""
                    UPDATE workflow_task_instances
                    SET status = 'cancelled',
                        error_message = 'Contact made via dialer - sibling cancelled',
                        updated_at = NOW()
                    WHERE task_group_key = :group_key
                    AND id != :current_id
                    AND status IN ('scheduled', 'pending', 'in_progress')
                    RETURNING id
                """), {
                    "group_key": task_group_key,
                    "current_id": workflow_task_id
                }).fetchall()
                siblings_cancelled = len(siblings)

            self.db.commit()

            logger.info(f"Workflow task {workflow_task_id} updated from dialer: {new_status}, {siblings_cancelled} siblings cancelled")

            return {
                "success": True,
                "workflow_task_id": workflow_task_id,
                "workflow_task_updated": True,
                "new_status": new_status,
                "contact_made": contact_made,
                "siblings_cancelled": siblings_cancelled
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to handle dialer completion: {e}")
            return {"success": False, "error": "Internal server error"}

    def add_workflow_tasks_to_session(
        self,
        session_id: int,
        workflow_task_ids: List[int]
    ) -> Dict[str, Any]:
        """
        Add workflow tasks to an existing dialer session.

        Args:
            session_id: Existing dialer session ID
            workflow_task_ids: Workflow task IDs to add

        Returns:
            Dict with result
        """
        try:
            from database.enums import DialerSessionStatus, DialerTaskStatus
            from database.models import DialerSession, DialerSessionTask

            # Verify session exists and is active
            session = self.db.query(DialerSession).filter(
                DialerSession.id == session_id,
                DialerSession.status == DialerSessionStatus.ACTIVE
            ).first()

            if not session:
                return {"success": False, "error": "Session not found or not active"}

            # Get current max position
            max_pos = self.db.execute(text("""
                SELECT COALESCE(MAX(task_order), -1) FROM dialer_session_tasks
                WHERE session_id = :session_id
            """), {"session_id": session_id}).scalar()

            position = max_pos + 1
            tasks_added = 0

            # Get workflow tasks with contact info
            tasks_data = self._get_workflow_tasks_for_session(workflow_task_ids)

            for task_data in tasks_data:
                session_task = DialerSessionTask(
                    session_id=session_id,
                    original_task_id=None,
                    contact_phone=task_data["contact_phone"],
                    contact_name=task_data["contact_name"],
                    lead_id=task_data["lead_id"],
                    loan_id=task_data["loan_id"],
                    status=DialerTaskStatus.PENDING,
                    task_order=position
                )
                self.db.add(session_task)
                self.db.flush()

                # Update workflow task
                self.db.execute(text("""
                    UPDATE workflow_task_instances
                    SET dialer_session_task_id = :session_task_id,
                        updated_at = NOW()
                    WHERE id = :workflow_task_id
                """), {
                    "session_task_id": session_task.id,
                    "workflow_task_id": task_data["workflow_task_id"]
                })

                position += 1
                tasks_added += 1

            # Update session total
            session.total_tasks += tasks_added
            self.db.commit()

            logger.info(f"Added {tasks_added} workflow tasks to session {session_id}")

            return {
                "success": True,
                "session_id": session_id,
                "tasks_added": tasks_added
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to add tasks to session: {e}")
            return {"success": False, "error": "Internal server error"}

    def get_dialer_queue_for_user(
        self,
        user_id: int,
        include_due_only: bool = True
    ) -> Dict[str, Any]:
        """
        Get the dialer queue summary for a user.

        Shows workflow tasks ready for dialing.

        Args:
            user_id: User ID
            include_due_only: Only include tasks that are due

        Returns:
            Dict with queue summary and tasks
        """
        due_filter = "AND wti.scheduled_date <= NOW()" if include_due_only else ""

        # Get summary counts
        summary_query = (
            "SELECT"
            " COUNT(*) as total,"
            " COUNT(CASE WHEN wti.task_type = 'phone' THEN 1 END) as phone,"
            " COUNT(CASE WHEN wti.task_type IN ('phone_am', 'phone_pm') THEN 1 END) as phone_scheduled,"
            " COUNT(CASE WHEN wti.task_type = 'dialer' THEN 1 END) as dialer"
            " FROM workflow_task_instances wti"
            " WHERE wti.assigned_user_id = :user_id"
            " AND wti.task_type IN ('phone', 'phone_am', 'phone_pm', 'dialer')"
            " AND wti.status IN ('scheduled', 'pending')"
            " " + due_filter
        )
        summary = self.db.execute(text(summary_query), {"user_id": user_id}).fetchone()

        # Get tasks
        tasks = self.get_phone_tasks_for_dialer(user_id=user_id, limit=100)

        return {
            "user_id": user_id,
            "summary": {
                "total": summary[0] if summary else 0,
                "phone": summary[1] if summary else 0,
                "phone_scheduled": summary[2] if summary else 0,
                "dialer": summary[3] if summary else 0
            },
            "tasks": tasks
        }

    def _get_workflow_tasks_for_session(
        self,
        workflow_task_ids: List[int]
    ) -> List[Dict[str, Any]]:
        """Get workflow task details with contact info for session creation."""
        if not workflow_task_ids:
            return []

        results = self.db.execute(text("""
            SELECT
                wti.id,
                wti.task_name,
                wti.lead_id,
                wti.loan_id,
                wti.task_group_key,
                COALESCE(l.phone, lo.borrower_phone) as contact_phone,
                COALESCE(
                    CONCAT(l.first_name, ' ', l.last_name),
                    CONCAT(lo.borrower_first_name, ' ', lo.borrower_last_name)
                ) as contact_name
            FROM workflow_task_instances wti
            LEFT JOIN leads l ON l.id = wti.lead_id
            LEFT JOIN loans lo ON lo.id = wti.loan_id
            WHERE wti.id = ANY(:task_ids)
            AND COALESCE(l.phone, lo.borrower_phone) IS NOT NULL
            ORDER BY wti.scheduled_date ASC
        """), {"task_ids": workflow_task_ids}).fetchall()

        return [
            {
                "workflow_task_id": row[0],
                "task_name": row[1],
                "lead_id": row[2],
                "loan_id": row[3],
                "task_group_key": row[4],
                "contact_phone": row[5],
                "contact_name": row[6] or "Unknown"
            }
            for row in results
        ]


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_dialer_integration(db: Session) -> WorkflowDialerIntegration:
    """Factory function to get a WorkflowDialerIntegration instance."""
    return WorkflowDialerIntegration(db)
