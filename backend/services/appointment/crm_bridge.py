"""
CRM integration bridge for the appointment service.

Handles lead creation/linking, activity logging, and follow-up task
creation when appointments are booked/updated/cancelled.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from services.appointment._models import get_model

logger = logging.getLogger(__name__)


def ensure_lead(
    db: Session,
    organization_id: int,
    email: str,
    name: Optional[str],
    phone: Optional[str],
    assigned_user_id: Optional[int],
) -> Optional[int]:
    """Find or create a Lead record for a booking attendee. Returns lead_id."""
    Lead = get_model("Lead")
    if not Lead or not email:
        return None

    try:
        existing = db.query(Lead).filter(
            Lead.email == email,
            Lead.organization_id == organization_id,
        ).first()

        if existing:
            existing.last_contact = datetime.now(timezone.utc)
            logger.info(f"Linked booking to existing lead {existing.id}")
            return existing.id

        name_parts = (name or "").strip().split(None, 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        new_lead = Lead(
            organization_id=organization_id,
            name=name or email,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            stage="New",
            source="scheduler",
            owner_id=assigned_user_id,
            last_contact=datetime.now(timezone.utc),
            lead_received_date=datetime.now(timezone.utc),
        )
        db.add(new_lead)
        db.flush()
        logger.info(f"Created new lead {new_lead.id} from booking")
        return new_lead.id
    except Exception as e:
        logger.error(f"Failed to ensure lead for booking: {e}")
        return None


def log_activity(
    db: Session,
    organization_id: int,
    user_id: Optional[int],
    lead_id: Optional[int],
    loan_id: Optional[int],
    content: str,
    activity_type: str = "Meeting",
) -> None:
    """Log appointment-related activity to CRM Activity table."""
    Activity = get_model("Activity")
    if not Activity:
        return

    try:
        from database.enums import ActivityType
        type_map = {
            "Meeting": ActivityType.MEETING,
            "Note": ActivityType.NOTE,
            "Email": ActivityType.EMAIL,
        }
        activity = Activity(
            organization_id=organization_id,
            type=type_map.get(activity_type, ActivityType.MEETING),
            content=content[:2000],
            lead_id=lead_id,
            loan_id=loan_id,
            user_id=user_id,
        )
        db.add(activity)
    except Exception as e:
        logger.debug(f"Could not log activity: {e}")


def create_followup_task(
    db: Session,
    organization_id: int,
    owner_id: Optional[int],
    lead_id: Optional[int],
    loan_id: Optional[int],
    title: str,
    description: str,
    due_date: datetime,
    priority: str = "medium",
) -> None:
    """Create a follow-up task linked to a lead/loan."""
    Task = get_model("Task")
    if not Task:
        return

    try:
        task = Task(
            organization_id=organization_id,
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
    except Exception as e:
        logger.debug(f"Could not create followup task: {e}")
