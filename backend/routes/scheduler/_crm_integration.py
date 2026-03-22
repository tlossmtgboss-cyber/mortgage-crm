"""
Scheduler CRM integration helpers — lead creation, activity logging, task creation,
LO licensing checks for booked appointments.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import logging

from routes.scheduler._input_validation import _mask_email

logger = logging.getLogger(__name__)


def _log_appointment_activity(db, org_id: int, user_id: int, lead_id: int,
                               loan_id: int, content: str,
                               activity_type: str = "Meeting"):
    """Log an appointment-related activity to the CRM Activity table."""
    try:
        from database.models.communication import Activity
        from database.enums import ActivityType

        type_map = {
            "Meeting": ActivityType.MEETING,
            "Note": ActivityType.NOTE,
            "Email": ActivityType.EMAIL,
        }

        activity = Activity(
            organization_id=org_id,
            type=type_map.get(activity_type, ActivityType.MEETING),
            content=content[:2000],  # Truncate to safe length
            lead_id=lead_id,
            loan_id=loan_id,
            user_id=user_id,
        )
        db.add(activity)
        logger.debug(f"Activity logged: {content[:80]}")
    except ImportError:
        logger.debug("Activity model not available, skipping activity log")
    except Exception as e:
        logger.error(f"Failed to log appointment activity: {e}")


def _ensure_lead_for_booking(db, attendee_email: str, attendee_name: str,
                              attendee_phone: str, assigned_user_id: int,
                              org_id: int) -> Optional[int]:
    """
    Find or create a Lead record for a booking attendee.
    Dedup: Match on email + organization_id. Returns lead_id or None.
    """
    if not attendee_email:
        return None

    try:
        from database.models.lead_loan import Lead
    except ImportError:
        logger.debug("Lead model not available, skipping lead creation")
        return None

    try:
        existing = db.query(Lead).filter(
            Lead.email == attendee_email,
            Lead.organization_id == org_id
        ).first()

        if existing:
            existing.last_contact = datetime.now(timezone.utc)
            logger.info(f"Linked booking to existing lead {existing.id} ({_mask_email(attendee_email)})")
            return existing.id

        # Parse name into first/last
        name_parts = (attendee_name or "").strip().split(None, 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        new_lead = Lead(
            organization_id=org_id,
            name=attendee_name or attendee_email,
            first_name=first_name,
            last_name=last_name,
            email=attendee_email,
            phone=attendee_phone,
            stage="New",
            source="scheduler",
            owner_id=assigned_user_id,
            last_contact=datetime.now(timezone.utc),
            lead_received_date=datetime.now(timezone.utc),
        )
        db.add(new_lead)
        db.flush()  # Get the ID without committing

        logger.info(f"Created new lead {new_lead.id} from booking ({_mask_email(attendee_email)})")
        return new_lead.id

    except Exception as e:
        logger.error(f"Failed to ensure lead for booking: {e}")
        return None


def _create_followup_task(db, org_id: int, owner_id: int, lead_id: int,
                           loan_id: int, title: str, description: str,
                           due_date, priority: str = "medium"):
    """Create a follow-up task linked to a lead/loan."""
    try:
        from database.models.task import Task

        task = Task(
            organization_id=org_id,
            title=title[:255],
            description=description[:2000],
            status="pending",
            priority=priority,
            due_date=due_date,
            owner_id=owner_id,
            lead_id=lead_id,
            loan_id=loan_id,
        )
        db.add(task)
        logger.info(f"Follow-up task created: {title[:80]}")
    except ImportError:
        logger.debug("Task model not available, skipping task creation")
    except Exception as e:
        logger.error(f"Failed to create follow-up task: {e}")


def _create_comm_failure_task(db, org_id: int, assigned_user_id: int,
                               attendee_name: str, error_msg: str):
    """R5: Create a high-priority task when all communication channels fail.
    Note: Does NOT commit -- caller owns the transaction boundary."""
    try:
        from database.models.task import Task
        task = Task(
            organization_id=org_id,
            title=f"Communication failure: {attendee_name or 'Client'}"[:255],
            description=f"All email/SMS attempts failed. Manual follow-up required.\nError: {error_msg}"[:2000],
            priority="high",
            status="pending",
            owner_id=assigned_user_id,
            due_date=datetime.now(timezone.utc) + timedelta(hours=4),
        )
        db.add(task)
        logger.info(f"Created communication failure escalation task for {attendee_name}")
    except Exception as e:
        logger.error(f"Failed to create escalation task: {e}")


class NMLSBlockingError(Exception):
    """Raised when a booking must be blocked due to missing NMLS in a regulated state."""
    pass


def _check_lo_licensing(db, assigned_user_id: int, attendee_state: str, org_id: int = None,
                        enforce: bool = True) -> Optional[str]:
    """
    C3: Verify LO has NMLS number on file.

    In NMLS-regulated states (all 50 + DC), missing NMLS raises
    ``NMLSBlockingError`` when ``enforce=True`` (the default).
    Returns a warning string for non-regulated states or when
    ``enforce=False``. Returns None if OK.

    Scoped by org_id to prevent cross-tenant user enumeration.
    """
    if not attendee_state:
        return None

    try:
        from database.models.core import User
        from routes.scheduler.constants import NMLS_REGULATED_STATES
    except ImportError:
        return None

    try:
        lo_query = db.query(User).filter(User.id == assigned_user_id)
        lo_query = lo_query.filter(User.organization_id == org_id)
        assigned = lo_query.first()
        if not assigned:
            return f"Warning: Could not verify LO licensing - user {assigned_user_id} not found"

        nmls = getattr(assigned, 'nmls_number', None)
        state_upper = attendee_state.strip().upper()[:2]

        if not nmls:
            name = f"{getattr(assigned, 'first_name', '')} {getattr(assigned, 'last_name', '')}".strip()
            msg = (f"LO {name} has no NMLS number on file. "
                   f"Cannot verify licensing for state {state_upper}.")

            if enforce and state_upper in NMLS_REGULATED_STATES:
                logger.warning(f"NMLS_BLOCK: {msg}")
                raise NMLSBlockingError(
                    f"Booking blocked: {msg} "
                    f"An NMLS number is required to book appointments in {state_upper}."
                )
            return f"Warning: {msg}"

        logger.info(f"LO licensing check: NMLS#{nmls} for state {state_upper}")
        return None
    except NMLSBlockingError:
        raise
    except Exception as e:
        logger.warning(f"LO licensing check failed: {e}")
        return None
