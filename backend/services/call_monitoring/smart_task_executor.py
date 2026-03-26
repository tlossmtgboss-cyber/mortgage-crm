"""
Smart Task Executor — intelligent CRM record creation from CI artifacts.

Replaces bare INSERT with smart defaults:
- Due dates calculated from priority
- Loan/lead linking from CI session
- Assignee routing based on artifact type
- Duplicate detection before creation
"""

import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Priority → days until due
PRIORITY_DUE_DAYS = {
    "critical": 0,   # Same day
    "high": 1,
    "medium": 3,
    "low": 7,
}

# Artifact type → suggested assignee role (looked up from loan's team)
ASSIGNEE_ROUTING = {
    "action_item": "loan_officer",         # Default to the LO
    "document_request": "processor",        # Doc collection is processor's job
    "scheduled_appointment": "loan_officer",
    "follow_up_call": "loan_officer",
    "risk_flag": "underwriter",            # Risk goes to UW
    "uw_note": "underwriter",
    "task": "loan_officer",                # Generic tasks to LO
}

# Task type mapping from artifact type
TASK_TYPE_MAP = {
    "action_item": "action_item",
    "document_request": "document_request",
    "risk_flag": "risk_review",
    "uw_note": "uw_condition",
    "task": "general",
}


class SmartTaskExecutor:
    """Creates CRM tasks and appointments with intelligent defaults."""

    def __init__(self, db: Session, organization_id: int, user_id: int):
        self.db = db
        self.organization_id = organization_id
        self.user_id = user_id

    async def execute_artifact(
        self,
        artifact,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Execute a single artifact into a CRM record with smart defaults.

        Routes to the correct handler based on artifact type.
        """
        artifact_type = artifact.artifact_type
        content = artifact.content if isinstance(artifact.content, dict) else {}
        structured = artifact.structured_data if isinstance(artifact.structured_data, dict) else {}

        # Merge content and structured_data for field lookups
        if isinstance(artifact.content, str):
            content = {"text": artifact.content}
        if isinstance(artifact.structured_data, str):
            try:
                structured = json.loads(artifact.structured_data)
            except (json.JSONDecodeError, TypeError):
                structured = {}

        # Get session context (loan_id, lead_id)
        session_ctx = self._get_session_context(session_id)

        if artifact_type in ("action_item", "document_request", "task", "risk_flag", "uw_note"):
            return await self._create_smart_task(
                artifact, content, structured, session_ctx
            )
        elif artifact_type in ("scheduled_appointment", "follow_up_call", "calendar_action"):
            return await self._create_smart_appointment(
                artifact, content, structured, session_ctx
            )
        else:
            # No CRM action for this type — mark complete
            return {"type": "marked_complete", "title": artifact.title}

    async def _create_smart_task(
        self,
        artifact,
        content: Dict,
        structured: Dict,
        session_ctx: Dict,
    ) -> Dict[str, Any]:
        """Create a task with intelligent defaults."""
        title = artifact.title or "CI Task"
        description = content.get("text", content.get("details", str(artifact.content or "")))
        priority = artifact.priority or "medium"
        artifact_type = artifact.artifact_type

        loan_id = session_ctx.get("loan_id")
        lead_id = session_ctx.get("lead_id")

        # Duplicate check
        if loan_id:
            duplicate = await self._check_duplicate_task(title, loan_id)
            if duplicate:
                logger.info(f"Duplicate task detected: '{title}' for loan {loan_id}")
                return {
                    "type": "duplicate_skipped",
                    "title": title,
                    "existing_task_id": duplicate,
                    "message": f"Task '{title}' already exists for this loan",
                }

        # Calculate due date
        due_days = PRIORITY_DUE_DAYS.get(priority, 3)
        due_date = datetime.now(timezone.utc) + timedelta(days=due_days)

        # Determine assignee
        assignee_id = await self._resolve_assignee(
            artifact_type, loan_id, session_ctx.get("user_id")
        )

        # Build description with context
        if artifact_type == "document_request":
            title = f"Request: {title}"
            doc_details = structured.get("details") or content.get("details", "")
            if doc_details:
                description = f"Document needed: {doc_details}"

        task_type = TASK_TYPE_MAP.get(artifact_type, "general")

        # Create the task
        self.db.execute(text("""
            INSERT INTO tasks (
                id, title, description, priority, status, due_date,
                loan_id, lead_id, assigned_to, created_by,
                task_type, organization_id, created_at
            ) VALUES (
                gen_random_uuid(), :title, :description, :priority, 'pending', :due_date,
                :loan_id, :lead_id, :assigned_to, :created_by,
                :task_type, :org_id, NOW()
            )
            RETURNING id
        """), {
            "title": title[:255],
            "description": description[:5000] if description else None,
            "priority": priority,
            "due_date": due_date,
            "loan_id": loan_id,
            "lead_id": lead_id,
            "assigned_to": assignee_id,
            "created_by": self.user_id,
            "task_type": task_type,
            "org_id": self.organization_id,
        })

        logger.info(
            f"Smart task created: '{title}' (priority={priority}, due={due_date.date()}, assignee={assignee_id})",
            extra={"loan_id": loan_id, "artifact_type": artifact_type},
        )

        return {
            "type": "task_created",
            "title": title,
            "priority": priority,
            "due_date": due_date.isoformat(),
            "assigned_to": assignee_id,
            "loan_id": loan_id,
            "task_type": task_type,
        }

    async def _create_smart_appointment(
        self,
        artifact,
        content: Dict,
        structured: Dict,
        session_ctx: Dict,
    ) -> Dict[str, Any]:
        """Create an appointment with smart defaults."""
        title = artifact.title or "Follow-up"
        contact_name = (
            structured.get("contact_name")
            or content.get("contact_name")
            or session_ctx.get("client_name", "Contact")
        )

        # Try to parse scheduled time from structured data
        scheduled_time = structured.get("scheduled_time") or structured.get("start_time")
        start_time = None
        end_time = None

        if scheduled_time:
            try:
                start_time = datetime.fromisoformat(str(scheduled_time))
                end_time = start_time + timedelta(minutes=30)
            except (ValueError, TypeError):
                pass

        # Default: schedule for tomorrow at 10 AM if no time specified
        if not start_time:
            tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
            start_time = tomorrow.replace(hour=17, minute=0, second=0, microsecond=0)  # 10 AM PT ≈ 5 PM UTC
            end_time = start_time + timedelta(minutes=30)

        notes = f"Created from Call Intelligence: {title}"
        if session_ctx.get("session_id"):
            notes += f"\nCI Session: {session_ctx['session_id'][:8]}"

        self.db.execute(text("""
            INSERT INTO appointments (
                id, caller_name, reason, status, notes,
                user_id, start_time, end_time,
                organization_id, created_at
            ) VALUES (
                gen_random_uuid(), :name, :reason, 'scheduled', :notes,
                :user_id, :start_time, :end_time,
                :org_id, NOW()
            )
        """), {
            "name": contact_name[:255],
            "reason": title[:500],
            "notes": notes[:2000],
            "user_id": self.user_id,
            "start_time": start_time,
            "end_time": end_time,
            "org_id": self.organization_id,
        })

        logger.info(
            f"Smart appointment created: '{title}' with {contact_name} at {start_time}",
        )

        return {
            "type": "appointment_created",
            "title": title,
            "contact": contact_name,
            "start_time": start_time.isoformat() if start_time else None,
        }

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _get_session_context(self, session_id: str) -> Dict[str, Any]:
        """Get loan/lead/user context from the CI session."""
        row = self.db.execute(text("""
            SELECT loan_id, lead_id, user_id, metadata
            FROM call_sessions
            WHERE id = :session_id AND organization_id = :org_id
        """), {"session_id": session_id, "org_id": self.organization_id}).fetchone()

        if not row:
            return {"session_id": session_id, "user_id": self.user_id}

        metadata = row.metadata if isinstance(row.metadata, dict) else {}
        if isinstance(row.metadata, str):
            try:
                metadata = json.loads(row.metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        return {
            "session_id": session_id,
            "loan_id": str(row.loan_id) if row.loan_id else None,
            "lead_id": str(row.lead_id) if row.lead_id else None,
            "user_id": str(row.user_id) if row.user_id else str(self.user_id),
            "client_name": metadata.get("client_name"),
        }

    async def _check_duplicate_task(
        self, title: str, loan_id: str
    ) -> Optional[str]:
        """Check if a similar task already exists for this loan. Returns task ID if found."""
        row = self.db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id
                AND organization_id = :org_id
                AND status IN ('pending', 'in_progress')
                AND LOWER(title) = LOWER(:title)
            LIMIT 1
        """), {
            "loan_id": loan_id,
            "org_id": self.organization_id,
            "title": title,
        }).fetchone()

        return str(row.id) if row else None

    async def _resolve_assignee(
        self,
        artifact_type: str,
        loan_id: Optional[str],
        fallback_user_id: Optional[str],
    ) -> Optional[int]:
        """
        Determine the best assignee for a task based on artifact type
        and the loan's team.
        """
        target_role = ASSIGNEE_ROUTING.get(artifact_type, "loan_officer")

        if loan_id:
            # Try to find the team member with the right role
            if target_role == "processor":
                row = self.db.execute(text("""
                    SELECT processor_id FROM loans
                    WHERE id = :loan_id AND organization_id = :org_id
                """), {"loan_id": loan_id, "org_id": self.organization_id}).fetchone()
                if row and row.processor_id:
                    return row.processor_id

            elif target_role == "loan_officer":
                row = self.db.execute(text("""
                    SELECT loan_officer_id FROM loans
                    WHERE id = :loan_id AND organization_id = :org_id
                """), {"loan_id": loan_id, "org_id": self.organization_id}).fetchone()
                if row and row.loan_officer_id:
                    return row.loan_officer_id

        # Fallback to the user who initiated the CI session
        if fallback_user_id:
            try:
                return int(fallback_user_id)
            except (ValueError, TypeError):
                pass

        return self.user_id
