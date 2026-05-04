"""
CRM event subscribers for BorrowerApplicationAgent events.

Translates agent events into CRM records:
- APPLICATION_ESCALATION -> Activity + Task + ensure ClientFile
- MEETING_BOOKED -> Activity + Task + LO notification
- DOCUMENT_SUGGESTED -> Activity on Lead
- APPLICATION_STALL -> Task for LO + nurture workflow trigger
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.event_bus import Event

logger = logging.getLogger(__name__)


async def on_application_escalation(event: Event) -> None:
    data = event.data
    contact_id = data.get("contact_id")
    application_id = data.get("application_id")
    trigger = data.get("trigger", "unknown")
    org_id = event.org_id

    if not contact_id:
        logger.warning("on_application_escalation: missing contact_id")
        return

    try:
        from db import SessionLocal
        from database.models.lead_loan import Lead
        from database.models.task import Task
        from database.models.communication import Activity
        from database.enums import ActivityType
        from database.models.client_file import ClientFile

        session = SessionLocal()
        try:
            lead = session.query(Lead).filter(Lead.id == int(contact_id)).first()
            if not lead:
                logger.warning("Escalation: Lead %s not found", contact_id)
                return

            activity = Activity(
                organization_id=int(org_id) if org_id else lead.organization_id,
                lead_id=lead.id,
                type=ActivityType.NOTE,
                content=f"Borrower application agent escalation: {trigger}",
                user_metadata={
                    "source": "borrower_application_agent",
                    "application_id": application_id,
                    "trigger": trigger,
                    "event_type": event.type.value,
                },
            )
            session.add(activity)

            task = Task(
                title=f"Review escalation: {trigger}",
                description=(
                    f"The borrower application agent escalated for: {trigger}. "
                    f"Application: {application_id}. Review and follow up."
                ),
                status="pending",
                priority="high",
                owner_id=lead.owner_id,
                lead_id=lead.id,
                organization_id=int(org_id) if org_id else lead.organization_id,
                related_type="borrower_agent_escalation",
                due_date=datetime.now(timezone.utc),
            )
            session.add(task)

            existing_cf = (
                session.query(ClientFile)
                .filter(ClientFile.lead_id == lead.id)
                .first()
            )
            if not existing_cf:
                cf = ClientFile(
                    lead_id=lead.id,
                    organization_id=int(org_id) if org_id else lead.organization_id,
                    created_by_user_id=lead.owner_id,
                )
                session.add(cf)
                logger.info("Created ClientFile for lead %s via escalation", lead.id)
            else:
                existing_cf.last_contact_at = datetime.now(timezone.utc)

            session.commit()
            logger.info("Escalation processed: lead=%s trigger=%s", contact_id, trigger)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except ImportError:
        logger.debug("DB models not available — skipping escalation handler")
    except Exception as e:
        logger.error("on_application_escalation failed: %s", e, exc_info=True)
        raise


async def on_meeting_booked(event: Event) -> None:
    data = event.data
    appointment_id = data.get("appointment_id")
    lo_user_id = data.get("lo_user_id")
    borrower_name = data.get("borrower_name", "Borrower")
    org_id = event.org_id

    if not appointment_id or not lo_user_id:
        return

    try:
        from db import SessionLocal
        from database.models.task import Task
        from database.models.communication import Activity
        from database.enums import ActivityType

        session = SessionLocal()
        try:
            activity = Activity(
                organization_id=int(org_id) if org_id else None,
                type=ActivityType.NOTE,
                content=(
                    f"Borrower {borrower_name} booked application review meeting "
                    f"(appointment #{appointment_id}) via Aria."
                ),
                user_metadata={
                    "source": "borrower_application_agent",
                    "appointment_id": appointment_id,
                    "event_type": event.type.value,
                },
            )
            session.add(activity)

            task = Task(
                title=f"Prepare for application review — {borrower_name}",
                description=(
                    f"{borrower_name} booked an application review meeting "
                    f"(appointment #{appointment_id}) through the borrower portal. "
                    f"Review their application before the call."
                ),
                status="pending",
                priority="medium",
                owner_id=int(lo_user_id),
                organization_id=int(org_id) if org_id else None,
                related_type="borrower_agent_meeting",
                due_date=datetime.now(timezone.utc),
            )
            session.add(task)
            session.commit()
            logger.info("Meeting booked handler: appointment=%s", appointment_id)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except ImportError:
        logger.debug("DB models not available — skipping meeting booked handler")
    except Exception as e:
        logger.error("on_meeting_booked failed: %s", e, exc_info=True)
        raise


async def on_document_suggested(event: Event) -> None:
    data = event.data
    contact_id = data.get("contact_id")
    documents = data.get("documents", [])
    reason = data.get("reason", "")
    org_id = event.org_id

    if not contact_id:
        return

    try:
        from db import SessionLocal
        from database.models.communication import Activity
        from database.enums import ActivityType

        session = SessionLocal()
        try:
            activity = Activity(
                organization_id=int(org_id) if org_id else None,
                lead_id=int(contact_id),
                type=ActivityType.NOTE,
                content=(
                    f"Aria suggested documents to borrower: {', '.join(documents)}. "
                    f"Reason: {reason}"
                ),
                user_metadata={
                    "source": "borrower_application_agent",
                    "documents": documents,
                    "reason": reason,
                    "event_type": event.type.value,
                },
            )
            session.add(activity)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except ImportError:
        logger.debug("DB models not available — skipping document suggested handler")
    except Exception as e:
        logger.error("on_document_suggested failed: %s", e, exc_info=True)
        raise


async def on_application_stall(event: Event) -> None:
    data = event.data
    contact_id = data.get("contact_id")
    application_id = data.get("application_id")
    section = data.get("section", "unknown")
    org_id = event.org_id

    if not contact_id:
        return

    try:
        from db import SessionLocal
        from database.models.lead_loan import Lead
        from database.models.task import Task

        session = SessionLocal()
        try:
            lead = session.query(Lead).filter(Lead.id == int(contact_id)).first()
            if not lead:
                return

            task = Task(
                title=f"Borrower stalled on {section}",
                description=(
                    f"The borrower's application ({application_id}) appears stalled "
                    f"on the {section} section. Consider reaching out to offer help."
                ),
                status="pending",
                priority="medium",
                owner_id=lead.owner_id,
                lead_id=lead.id,
                organization_id=int(org_id) if org_id else lead.organization_id,
                related_type="borrower_agent_stall",
                due_date=datetime.now(timezone.utc),
            )
            session.add(task)
            session.commit()
            logger.info("Stall task created: lead=%s section=%s", contact_id, section)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except ImportError:
        logger.debug("DB models not available — skipping stall handler")
    except Exception as e:
        logger.error("on_application_stall failed: %s", e, exc_info=True)
        raise
