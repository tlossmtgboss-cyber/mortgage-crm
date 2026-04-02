"""
Dialer Engine - Power Dialer Session Management
Handles session state machine, next-call logic, and call flow

Features:
- Automatic call progression with configurable delays
- Real-time WebSocket updates to connected clients
- Compliance checking before each call
- Multi-agent collision prevention via soft locks
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from .provider import get_telephony_provider, CallResult, CallStatus
from .compliance import ComplianceChecker
from .websocket import ws_manager, DialerEvent

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================


class SessionState(str, Enum):
    """Dialer session states"""
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


class TaskState(str, Enum):
    """Individual task states within a session"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DialerTask:
    """A single task/call in the dialer queue"""
    id: int
    contact_phone: str
    contact_name: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    task_id: Optional[int] = None
    status: TaskState = TaskState.PENDING
    call_sid: Optional[str] = None
    attempts: int = 0
    disposition: Optional[str] = None
    notes: Optional[str] = None


class DialerEngine:
    """
    Power Dialer Engine

    Manages dialer sessions with state machine:
    - ACTIVE: Session running, making calls
    - PAUSED: Temporarily halted, can resume
    - STOPPED: Manually ended by agent
    - COMPLETED: All tasks processed

    Features:
    - Automatic call progression
    - Compliance checking before each call
    - Disposition workflow
    - Multi-agent collision prevention
    """

    def __init__(self, db_session, agent_id: int, organization_id: Optional[int] = None):
        """
        Initialize dialer engine for an agent

        Args:
            db_session: SQLAlchemy database session
            agent_id: ID of the agent using the dialer
            organization_id: Tenant org ID for data isolation
        """
        self.db = db_session
        self.agent_id = agent_id
        self.organization_id = organization_id
        self.provider = get_telephony_provider()
        self.compliance = ComplianceChecker(db_session, organization_id=organization_id)
        self._current_session_id: Optional[int] = None

    def get_agent_settings(self) -> Optional[Dict[str, Any]]:
        """Get telephony settings for the current agent"""
        from database.models import AgentTelephonySettings

        settings = self.db.query(AgentTelephonySettings).filter(
            AgentTelephonySettings.user_id == self.agent_id
        ).first()

        if settings:
            return {
                "cell_phone": settings.cell_phone,
                "business_caller_id": settings.business_caller_id,
                "dialer_enabled": settings.dialer_enabled,
                "max_calls_per_day": settings.max_calls_per_day,
                "auto_advance": settings.auto_advance,
                "pause_between_calls": settings.pause_between_calls
            }
        return None

    def get_verified_caller_id(self) -> Optional[str]:
        """Get the agent's verified caller ID"""
        settings = self.get_agent_settings()
        if settings and settings.get("business_caller_id"):
            return settings["business_caller_id"]
        return None

    def create_session(
        self,
        task_ids: List[int],
        base_url: str
    ) -> Dict[str, Any]:
        """
        Create a new dialer session with selected tasks

        Args:
            task_ids: List of task IDs to include in session
            base_url: Base URL for Telnyx callbacks

        Returns:
            Dict with session info or error
        """
        from database.enums import DialerSessionStatus, DialerTaskStatus
        from database.models import DialerSession, DialerSessionTask, AITask, Lead, Loan

        # Check if agent has an active session
        existing = self.db.query(DialerSession).filter(
            DialerSession.agent_id == self.agent_id,
            DialerSession.status == DialerSessionStatus.ACTIVE
        ).first()

        if existing:
            return {
                "success": False,
                "error": "Agent already has an active dialer session",
                "existing_session_id": existing.id
            }

        # Get caller ID
        caller_id = self.get_verified_caller_id()
        if not caller_id:
            return {
                "success": False,
                "error": "No verified caller ID configured. Please set up your business phone number."
            }

        # Create session (with tenant isolation)
        session_kwargs = dict(
            agent_id=self.agent_id,
            status=DialerSessionStatus.ACTIVE,
            total_tasks=len(task_ids),
            completed_tasks=0,
            caller_id_used=caller_id,
        )
        if self.organization_id and hasattr(DialerSession, 'organization_id'):
            session_kwargs['organization_id'] = self.organization_id
        session = DialerSession(**session_kwargs)
        self.db.add(session)
        self.db.flush()  # Get session ID

        # Add tasks to session
        position = 0
        for task_id in task_ids:
            # AITask is the model used by the call-tasks endpoint
            task = self.db.query(AITask).filter(AITask.id == task_id).first()
            if not task:
                logger.warning(f"AITask {task_id} not found, skipping")
                continue

            # Get contact info from lead or loan
            contact_phone = None
            contact_name = task.borrower_name or None
            lead_id = None
            loan_id = None

            if task.lead_id:
                lead_q = self.db.query(Lead).filter(Lead.id == task.lead_id)
                if self.organization_id:
                    lead_q = lead_q.filter(Lead.organization_id == self.organization_id)
                lead = lead_q.first()
                if lead:
                    contact_phone = lead.phone
                    contact_name = contact_name or lead.name
                    lead_id = lead.id
            elif task.loan_id:
                loan_q = self.db.query(Loan).filter(Loan.id == task.loan_id)
                if self.organization_id:
                    loan_q = loan_q.filter(Loan.organization_id == self.organization_id)
                loan = loan_q.first()
                if loan:
                    contact_phone = loan.borrower_phone
                    contact_name = contact_name or loan.borrower_name
                    loan_id = loan.id

            if not contact_phone:
                logger.warning(f"AITask {task_id} has no contact phone (lead_id={task.lead_id}, loan_id={task.loan_id}), skipping")
                continue

            session_task = DialerSessionTask(
                session_id=session.id,
                original_task_id=task_id,
                contact_phone=contact_phone,
                contact_name=contact_name or "Unknown",
                lead_id=lead_id,
                loan_id=loan_id,
                status=DialerTaskStatus.PENDING,
                task_order=position
            )
            self.db.add(session_task)
            position += 1

        session.total_tasks = position
        self.db.commit()

        self._current_session_id = session.id

        logger.info(f"Created dialer session {session.id} with {position} tasks for agent {self.agent_id}")

        return {
            "success": True,
            "session_id": session.id,
            "total_tasks": position,
            "status": SessionState.ACTIVE.value
        }

    def get_session_status(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Get current status of a dialer session"""
        from database.models import DialerSession, DialerSessionTask

        session = self.db.query(DialerSession).filter(
            DialerSession.id == session_id
        ).first()

        if not session:
            return None

        # Get task breakdown
        tasks = self.db.query(DialerSessionTask).filter(
            DialerSessionTask.session_id == session_id
        ).order_by(DialerSessionTask.task_order).all()

        pending = sum(1 for t in tasks if t.status == "pending")
        completed = sum(1 for t in tasks if t.status == "completed")
        no_answer = sum(1 for t in tasks if t.status == "no_answer")
        failed = sum(1 for t in tasks if t.status == "failed")
        skipped = sum(1 for t in tasks if t.status == "skipped")

        current_task = None
        current_task_record = next((t for t in tasks if t.status == "in_progress"), None)
        if current_task_record:
            current_task = {
                "id": current_task_record.id,
                "contact_name": current_task_record.contact_name,
                "contact_phone": current_task_record.contact_phone,
                "call_sid": current_task_record.call_sid
            }

        return {
            "session_id": session.id,
            "status": session.status,
            "total_tasks": session.total_tasks,
            "completed_tasks": completed,
            "pending_tasks": pending,
            "no_answer_tasks": no_answer,
            "failed_tasks": failed,
            "skipped_tasks": skipped,
            "current_task": current_task,
            "started_at": session.created_at.isoformat() if session.created_at else None,
            "ended_at": session.completed_at.isoformat() if session.completed_at else None
        }

    def get_next_task(self, session_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the next pending task in the session

        Returns:
            Task info dict or None if no more tasks
        """
        from database.enums import DialerTaskStatus
        from database.models import DialerSessionTask

        task = self.db.query(DialerSessionTask).filter(
            DialerSessionTask.session_id == session_id,
            DialerSessionTask.status == DialerTaskStatus.PENDING
        ).order_by(DialerSessionTask.task_order).first()

        if not task:
            return None

        return {
            "id": task.id,
            "task_id": task.original_task_id,
            "contact_phone": task.contact_phone,
            "contact_name": task.contact_name,
            "lead_id": task.lead_id,
            "loan_id": task.loan_id,
            "position": task.task_order,
            "attempts": 0  # Track attempts separately if needed
        }

    def initiate_call(
        self,
        session_id: int,
        task_id: int,
        base_url: str
    ) -> Dict[str, Any]:
        """
        Initiate a call for a specific task in the session

        Args:
            session_id: Dialer session ID
            task_id: Session task ID (not the Task table ID)
            base_url: Base URL for Telnyx callbacks

        Returns:
            Dict with call result
        """
        from database.enums import DialerSessionStatus, DialerTaskStatus
        from database.models import DialerSession, DialerSessionTask

        # Verify session is active
        session = self.db.query(DialerSession).filter(
            DialerSession.id == session_id,
            DialerSession.agent_id == self.agent_id
        ).first()

        if not session:
            return {"success": False, "error": "Session not found"}

        if session.status != DialerSessionStatus.ACTIVE:
            return {"success": False, "error": f"Session is {session.status}, not active"}

        # Get the task
        task = self.db.query(DialerSessionTask).filter(
            DialerSessionTask.id == task_id,
            DialerSessionTask.session_id == session_id
        ).first()

        if not task:
            return {"success": False, "error": "Task not found in session"}

        # Run compliance checks (pass lead_id for consent verification)
        compliance_result = self.compliance.full_compliance_check(
            task.contact_phone,
            self.agent_id,
            contact_id=getattr(task, 'lead_id', None)
        )

        if not compliance_result["can_call"]:
            # Mark task as skipped due to compliance
            task.status = DialerTaskStatus.SKIPPED
            task.disposition = "compliance_blocked"
            task.notes = "; ".join(compliance_result["issues"])
            self.db.commit()

            return {
                "success": False,
                "error": "Compliance check failed",
                "issues": compliance_result["issues"],
                "skipped": True
            }

        # Get caller ID
        caller_id = self.get_verified_caller_id()
        if not caller_id:
            return {"success": False, "error": "No verified caller ID"}

        # Build callback URLs
        callback_url = f"{base_url}/api/v1/dialer/twiml/outbound?session_id={session_id}&task_id={task_id}"
        status_callback_url = f"{base_url}/api/v1/dialer/webhook/status?session_id={session_id}&task_id={task_id}"
        recording_callback_url = f"{base_url}/api/v1/dialer/webhook/recording-complete?session_id={session_id}&task_id={task_id}"

        # Acquire soft lock
        lock_acquired = self.compliance.acquire_soft_lock(
            task.contact_phone,
            self.agent_id,
            f"pending_{task_id}"  # Temporary call SID
        )

        if not lock_acquired:
            return {"success": False, "error": "Could not acquire call lock - number may be in use"}

        # Place the call with recording enabled
        result = self.provider.place_call(
            to_number=task.contact_phone,
            from_number=caller_id,
            callback_url=callback_url,
            status_callback_url=status_callback_url,
            recording_status_callback=recording_callback_url,
            record=True,
            timeout=30
        )

        if result.success:
            # Update task
            task.status = DialerTaskStatus.IN_PROGRESS
            task.call_sid = result.call_sid
            task.updated_at = datetime.now(timezone.utc)

            # Update soft lock with real call SID
            self.compliance.acquire_soft_lock(
                task.contact_phone,
                self.agent_id,
                result.call_sid
            )

            # Update session
            session.current_task_id = task_id

            self.db.commit()

            logger.info(f"Call initiated: {result.call_sid} for task {task_id}")

            # Send WebSocket event
            ws_manager.send_to_agent_sync(
                str(self.agent_id),
                DialerEvent.call_initiated(
                    session_id=session_id,
                    task_id=task_id,
                    call_sid=result.call_sid,
                    contact_name=task.contact_name,
                    contact_phone=task.contact_phone
                )
            )

            return {
                "success": True,
                "call_sid": result.call_sid,
                "task_id": task_id,
                "contact_name": task.contact_name,
                "contact_phone": task.contact_phone
            }
        else:
            # Release lock on failure
            self.compliance.release_soft_lock(task.contact_phone, self.agent_id)

            # Mark task as failed
            task.status = DialerTaskStatus.FAILED
            task.disposition = "call_failed"
            task.notes = result.error_message
            task.updated_at = datetime.now(timezone.utc)
            self.db.commit()

            # Send failure event via WebSocket
            ws_manager.send_to_agent_sync(
                str(self.agent_id),
                DialerEvent.call_failed(
                    session_id=session_id,
                    task_id=task_id,
                    error=result.error_message or "Call failed",
                    error_code=result.error_code
                )
            )

            return {
                "success": False,
                "error": result.error_message,
                "error_code": result.error_code
            }

    def handle_call_status_update(
        self,
        session_id: int,
        task_id: int,
        call_sid: str,
        status: str,
        duration: Optional[int] = None,
        answered_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle Telnyx status callback for a call

        Args:
            session_id: Dialer session ID
            task_id: Session task ID
            call_sid: Telnyx call SID
            status: Call status (ringing, in-progress, completed, no-answer, busy, failed)
            duration: Call duration in seconds
            answered_by: Who/what answered (human, machine, etc.)

        Returns:
            Dict with next action
        """
        from database.enums import DialerSessionStatus, DialerTaskStatus, CallOutcome
        from database.models import DialerSession, DialerSessionTask, CallLog

        task = self.db.query(DialerSessionTask).filter(
            DialerSessionTask.id == task_id,
            DialerSessionTask.session_id == session_id
        ).first()

        if not task:
            logger.error(f"Task {task_id} not found for status update")
            return {"error": "Task not found"}

        session = self.db.query(DialerSession).filter(
            DialerSession.id == session_id
        ).first()

        # Map call status to our status and send WebSocket events
        if status == "ringing":
            ws_manager.send_to_agent_sync(
                str(session.agent_id),
                DialerEvent.call_ringing(session_id, task_id, call_sid)
            )
            return {"task_id": task_id, "status": "ringing"}

        elif status in ["in-progress", "answered"]:
            ws_manager.send_to_agent_sync(
                str(session.agent_id),
                DialerEvent.call_answered(session_id, task_id, call_sid, answered_by)
            )
            return {"task_id": task_id, "status": "answered"}

        elif status in ["completed"]:
            task.status = DialerTaskStatus.COMPLETED
            task.duration_seconds = duration
            session.completed_tasks += 1
        elif status in ["no-answer", "canceled"]:
            task.status = DialerTaskStatus.NO_ANSWER
        elif status in ["busy"]:
            task.status = DialerTaskStatus.NO_ANSWER
            task.disposition = "busy"
        elif status in ["failed"]:
            task.status = DialerTaskStatus.FAILED

        # Release soft lock
        self.compliance.release_soft_lock(task.contact_phone, self.agent_id)

        # Send call completed event
        ws_manager.send_to_agent_sync(
            str(session.agent_id),
            DialerEvent.call_completed(
                session_id=session_id,
                task_id=task_id,
                call_sid=call_sid,
                duration=duration,
                status=status
            )
        )

        # Log the call - map status to CallOutcome
        outcome_map = {
            "completed": CallOutcome.COMPLETED,
            "answered": CallOutcome.COMPLETED,
            "busy": CallOutcome.BUSY,
            "no-answer": CallOutcome.NO_ANSWER,
            "failed": CallOutcome.FAILED,
            "canceled": CallOutcome.FAILED,
        }
        call_outcome = outcome_map.get(status.lower() if isinstance(status, str) else status, CallOutcome.COMPLETED)

        call_log_kwargs = dict(
            agent_id=self.agent_id,
            session_id=session_id,
            session_task_id=task_id,
            contact_phone=task.contact_phone,
            contact_name=task.contact_name,
            lead_id=task.lead_id,
            loan_id=task.loan_id,
            call_sid=call_sid,
            duration_seconds=duration,
            outcome=call_outcome,
            start_time=task.created_at,  # Use created_at as start time
            end_time=datetime.now(timezone.utc),
        )
        if self.organization_id and hasattr(CallLog, 'organization_id'):
            call_log_kwargs['organization_id'] = self.organization_id
        call_log = CallLog(**call_log_kwargs)
        self.db.add(call_log)

        # Clear current task
        session.current_task_id = None

        # Check if session is complete
        pending = self.db.query(DialerSessionTask).filter(
            DialerSessionTask.session_id == session_id,
            DialerSessionTask.status == DialerTaskStatus.PENDING
        ).count()

        if pending == 0:
            session.status = DialerSessionStatus.COMPLETED
            session.completed_at = datetime.now(timezone.utc)

            # Send session completed event
            completed_count = self.db.query(DialerSessionTask).filter(
                DialerSessionTask.session_id == session_id,
                DialerSessionTask.status == DialerTaskStatus.COMPLETED
            ).count()

            ws_manager.send_to_agent_sync(
                str(session.agent_id),
                DialerEvent.session_completed(
                    session_id=session_id,
                    total_calls=session.total_tasks,
                    connected_calls=completed_count
                )
            )
        else:
            # Send session updated event
            ws_manager.send_to_agent_sync(
                str(session.agent_id),
                DialerEvent.session_updated(
                    session_id=session_id,
                    status=session.status,
                    total_tasks=session.total_tasks,
                    completed_tasks=session.completed_tasks,
                    pending_tasks=pending
                )
            )

            # If call completed and needs disposition, notify
            if task.status == DialerTaskStatus.COMPLETED:
                ws_manager.send_to_agent_sync(
                    str(session.agent_id),
                    DialerEvent.disposition_required(
                        session_id=session_id,
                        task_id=task_id,
                        contact_name=task.contact_name
                    )
                )

        self.db.commit()

        return {
            "task_id": task_id,
            "status": task.status,
            "session_status": session.status,
            "remaining_tasks": pending,
            "needs_disposition": task.status == DialerTaskStatus.COMPLETED
        }

    def set_disposition(
        self,
        session_id: int,
        task_id: int,
        disposition: str,
        notes: Optional[str] = None,
        schedule_callback: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Set the disposition for a completed call

        Args:
            session_id: Dialer session ID
            task_id: Session task ID
            disposition: Disposition code (connected, voicemail, callback_scheduled, etc.)
            notes: Optional notes about the call
            schedule_callback: Optional callback datetime

        Returns:
            Dict with result
        """
        from database.models import DialerSessionTask, CallLog

        task = self.db.query(DialerSessionTask).filter(
            DialerSessionTask.id == task_id,
            DialerSessionTask.session_id == session_id
        ).first()

        if not task:
            return {"success": False, "error": "Task not found"}

        task.disposition = disposition
        task.notes = notes

        # Update call log too
        call_log = self.db.query(CallLog).filter(
            CallLog.session_task_id == task_id
        ).order_by(CallLog.created_at.desc()).first()

        if call_log:
            call_log.disposition = disposition
            call_log.notes = notes

        # Handle callback scheduling
        if schedule_callback and disposition == "callback_scheduled":
            # Create a new AITask for the callback (same model as source tasks)
            from database.models import AITask

            # Create callback task linked to same lead/loan
            callback_task = AITask(
                assigned_to_id=self.agent_id,
                title=f"Callback: {task.contact_name}",
                description=f"Scheduled callback from dialer session. Notes: {notes or 'None'}",
                due_date=schedule_callback,
                priority="high",
                lead_id=task.lead_id,
                loan_id=task.loan_id,
                borrower_name=task.contact_name
            )
            self.db.add(callback_task)

        self.db.commit()

        return {
            "success": True,
            "task_id": task_id,
            "disposition": disposition
        }

    def pause_session(self, session_id: int) -> Dict[str, Any]:
        """Pause an active session"""
        from database.enums import DialerSessionStatus
        from database.models import DialerSession

        session = self.db.query(DialerSession).filter(
            DialerSession.id == session_id,
            DialerSession.agent_id == self.agent_id
        ).first()

        if not session:
            return {"success": False, "error": "Session not found"}

        if session.status != DialerSessionStatus.ACTIVE:
            return {"success": False, "error": f"Session is {session.status}, cannot pause"}

        session.status = DialerSessionStatus.PAUSED
        self.db.commit()

        return {"success": True, "status": SessionState.PAUSED.value}

    def resume_session(self, session_id: int) -> Dict[str, Any]:
        """Resume a paused session"""
        from database.enums import DialerSessionStatus
        from database.models import DialerSession

        session = self.db.query(DialerSession).filter(
            DialerSession.id == session_id,
            DialerSession.agent_id == self.agent_id
        ).first()

        if not session:
            return {"success": False, "error": "Session not found"}

        if session.status != DialerSessionStatus.PAUSED:
            return {"success": False, "error": f"Session is {session.status}, cannot resume"}

        session.status = DialerSessionStatus.ACTIVE
        self.db.commit()

        return {"success": True, "status": SessionState.ACTIVE.value}

    def stop_session(self, session_id: int) -> Dict[str, Any]:
        """Stop a session completely"""
        from database.enums import DialerSessionStatus
        from database.models import DialerSession, DialerSessionTask

        session = self.db.query(DialerSession).filter(
            DialerSession.id == session_id,
            DialerSession.agent_id == self.agent_id
        ).first()

        if not session:
            return {"success": False, "error": "Session not found"}

        if session.status in [DialerSessionStatus.STOPPED, DialerSessionStatus.COMPLETED]:
            return {"success": False, "error": f"Session already {session.status}"}

        # If there's an active call, try to hang up
        if session.current_task_id:
            current_task = self.db.query(DialerSessionTask).filter(
                DialerSessionTask.id == session.current_task_id
            ).first()

            if current_task and current_task.call_sid:
                self.provider.hangup_call(current_task.call_sid)
                self.compliance.release_soft_lock(current_task.contact_phone, self.agent_id)

        session.status = DialerSessionStatus.STOPPED
        session.completed_at = datetime.now(timezone.utc)
        session.current_task_id = None
        self.db.commit()

        return {"success": True, "status": SessionState.STOPPED.value}

    def skip_task(self, session_id: int, task_id: int, reason: str = "manual_skip") -> Dict[str, Any]:
        """Skip a task in the session"""
        from database.enums import DialerTaskStatus
        from database.models import DialerSessionTask

        task = self.db.query(DialerSessionTask).filter(
            DialerSessionTask.id == task_id,
            DialerSessionTask.session_id == session_id
        ).first()

        if not task:
            return {"success": False, "error": "Task not found"}

        if task.status not in [DialerTaskStatus.PENDING, DialerTaskStatus.IN_PROGRESS]:
            return {"success": False, "error": f"Task is {task.status}, cannot skip"}

        # If call in progress, hang up
        if task.status == DialerTaskStatus.IN_PROGRESS and task.call_sid:
            self.provider.hangup_call(task.call_sid)
            self.compliance.release_soft_lock(task.contact_phone, self.agent_id)

        task.status = DialerTaskStatus.SKIPPED
        task.disposition = reason
        self.db.commit()

        return {"success": True, "task_id": task_id, "status": TaskState.SKIPPED.value}


def click_to_dial(
    db_session,
    agent_id: int,
    phone_number: str,
    contact_name: str,
    base_url: str,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    task_id: Optional[int] = None,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Single click-to-dial call (not part of a session)

    Args:
        db_session: Database session
        agent_id: Agent placing the call
        phone_number: Number to call
        contact_name: Name of the contact
        base_url: Base URL for callbacks
        lead_id: Optional lead ID
        loan_id: Optional loan ID
        task_id: Optional task ID
        organization_id: Optional org ID for tenant isolation

    Returns:
        Dict with call result
    """
    from database.enums import CallOutcome
    from database.models import AgentTelephonySettings, CallLog

    provider = get_telephony_provider()
    compliance = ComplianceChecker(db_session, organization_id=organization_id)

    # Run compliance checks (pass lead_id for consent verification)
    compliance_result = compliance.full_compliance_check(phone_number, agent_id, contact_id=lead_id)

    if not compliance_result["can_call"]:
        return {
            "success": False,
            "error": "Compliance check failed",
            "issues": compliance_result["issues"]
        }

    # Get caller ID
    settings = db_session.query(AgentTelephonySettings).filter(
        AgentTelephonySettings.user_id == agent_id
    ).first()

    if not settings or not settings.business_caller_id:
        return {"success": False, "error": "No verified caller ID configured"}

    # Build callback URLs - include destination number for the TwiML to dial
    from urllib.parse import quote
    callback_url = f"{base_url}/api/v1/dialer/twiml/click-to-dial?destination={quote(phone_number)}&contact_name={quote(contact_name or 'Contact')}"
    status_callback_url = f"{base_url}/api/v1/dialer/webhook/click-to-dial-status?agent_id={agent_id}"
    recording_callback_url = f"{base_url}/api/v1/dialer/webhook/recording-complete?agent_id={agent_id}"

    # Acquire soft lock
    lock_acquired = compliance.acquire_soft_lock(
        phone_number,
        agent_id,
        "pending_click_to_dial"
    )

    if not lock_acquired:
        return {"success": False, "error": "Number currently in use by another agent"}

    # First, call the agent's cell phone. When they answer, the TwiML will dial the contact.
    agent_phone = settings.cell_phone
    if not agent_phone:
        return {"success": False, "error": "Agent cell phone not configured"}

    result = provider.place_call(
        to_number=agent_phone,  # Call agent first
        from_number=settings.business_caller_id,
        callback_url=callback_url,  # TwiML will dial the contact
        status_callback_url=status_callback_url,
        recording_status_callback=recording_callback_url,
        record=True,
        timeout=30
    )

    if result.success:
        # Update lock with real call SID
        compliance.acquire_soft_lock(phone_number, agent_id, result.call_sid)

        # Log the call (with tenant isolation)
        call_log_kwargs = dict(
            agent_id=agent_id,
            contact_phone=phone_number,
            contact_name=contact_name,
            lead_id=lead_id,
            loan_id=loan_id,
            session_task_id=task_id,
            call_sid=result.call_sid,
            outcome=CallOutcome.INITIATED,
            start_time=datetime.now(timezone.utc),
        )
        if organization_id and hasattr(CallLog, 'organization_id'):
            call_log_kwargs['organization_id'] = organization_id
        call_log = CallLog(**call_log_kwargs)
        db_session.add(call_log)
        db_session.commit()

        return {
            "success": True,
            "call_sid": result.call_sid,
            "contact_name": contact_name,
            "contact_phone": phone_number
        }
    else:
        compliance.release_soft_lock(phone_number, agent_id)
        return {
            "success": False,
            "error": result.error_message,
            "error_code": result.error_code
        }
