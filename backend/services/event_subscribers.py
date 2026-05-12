"""
Default event subscribers for appointment lifecycle events.

Each subscriber is a standalone async function that handles one concern
(email, calendar sync, task creation, analytics, audit logging).  Failures
in any subscriber are isolated by the EventBus — they never propagate to
the publisher or block other subscribers.

Call ``register_all_subscribers()`` during application startup (e.g. in
``main.py`` or a startup event handler).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from services.event_bus import Event, EventType, event_bus

logger = logging.getLogger(__name__)


# =============================================================================
# Email / SMS notifications
# =============================================================================

async def on_appointment_created_send_confirmation(event: Event) -> None:
    """Send confirmation email + SMS to the attendee when an appointment is booked."""
    data = event.data
    appointment_id = data.get("appointment_id")
    attendee_email = data.get("attendee_email")
    attendee_phone = data.get("attendee_phone")
    attendee_name = data.get("attendee_name", "")

    if not appointment_id:
        logger.warning("on_appointment_created_send_confirmation: missing appointment_id")
        return

    try:
        from scheduler_email_service import (
            send_appointment_confirmation_email,
            send_appointment_confirmation_sms,
        )

        if attendee_email:
            await _call_or_run(
                send_appointment_confirmation_email,
                to_email=attendee_email,
                attendee_name=attendee_name,
                appointment_data=data,
            )
            logger.info(
                "Confirmation email sent for appointment %s [%s]",
                appointment_id,
                event.correlation_id,
            )

        if attendee_phone:
            await _call_or_run(
                send_appointment_confirmation_sms,
                to_phone=attendee_phone,
                attendee_name=attendee_name,
                appointment_data=data,
            )
    except ImportError:
        logger.debug("scheduler_email_service not available — skipping confirmation email")
    except Exception as e:
        logger.error(
            "Failed to send confirmation for appointment %s: %s",
            appointment_id,
            e,
            exc_info=True,
        )
        raise  # Let EventBus catch and isolate


async def on_appointment_cancelled_send_notification(event: Event) -> None:
    """Send cancellation notice to attendee and assigned LO."""
    data = event.data
    appointment_id = data.get("appointment_id")
    attendee_email = data.get("attendee_email")

    if not appointment_id:
        return

    try:
        from scheduler_email_service import (
            send_appointment_cancellation_email,
            send_team_member_cancellation_email,
        )

        if attendee_email:
            await _call_or_run(
                send_appointment_cancellation_email,
                to_email=attendee_email,
                appointment_data=data,
            )

        lo_email = data.get("assigned_user_email")
        if lo_email:
            await _call_or_run(
                send_team_member_cancellation_email,
                to_email=lo_email,
                appointment_data=data,
            )

        logger.info("Cancellation notifications sent for appointment %s", appointment_id)
    except ImportError:
        logger.debug("scheduler_email_service not available — skipping cancellation email")
    except Exception as e:
        logger.error("Failed to send cancellation notice for %s: %s", appointment_id, e)
        raise


# =============================================================================
# Calendar sync (Google / Outlook)
# =============================================================================

async def on_appointment_created_sync_calendar(event: Event) -> None:
    """Sync newly created appointment to external calendar (Google Calendar, Outlook)."""
    data = event.data
    appointment_id = data.get("appointment_id")
    assigned_user_id = data.get("assigned_user_id")

    if not appointment_id or not assigned_user_id:
        return

    try:
        from services.unified_calendar_service import unified_calendar_service
        await _call_or_run(
            unified_calendar_service.create_event_from_appointment,
            user_id=assigned_user_id,
            appointment_data=data,
        )
        logger.info(
            "Calendar sync completed for appointment %s [%s]",
            appointment_id,
            event.correlation_id,
        )
    except ImportError:
        logger.debug("unified_calendar_service not available — skipping calendar sync")
    except Exception as e:
        logger.error("Calendar sync failed for appointment %s: %s", appointment_id, e)
        raise


async def on_appointment_cancelled_sync_calendar(event: Event) -> None:
    """Remove or cancel the calendar event when an appointment is cancelled."""
    data = event.data
    appointment_id = data.get("appointment_id")
    google_event_id = data.get("google_calendar_event_id")
    outlook_event_id = data.get("outlook_event_id")

    if not (google_event_id or outlook_event_id):
        return

    try:
        from services.unified_calendar_service import unified_calendar_service
        await _call_or_run(
            unified_calendar_service.cancel_event_from_appointment,
            appointment_data=data,
        )
        logger.info("Calendar event cancelled for appointment %s", appointment_id)
    except ImportError:
        logger.debug("unified_calendar_service not available — skipping calendar cancel")
    except Exception as e:
        logger.error("Calendar cancel failed for appointment %s: %s", appointment_id, e)
        raise


# =============================================================================
# Task creation
# =============================================================================

async def on_appointment_created_create_tasks(event: Event) -> None:
    """Create follow-up tasks when an appointment is booked.

    For example: "Prepare docs for pre-approval review with Jane Doe".
    """
    data = event.data
    appointment_id = data.get("appointment_id")
    assigned_user_id = data.get("assigned_user_id")
    meeting_type = data.get("meeting_type")
    org_id = event.org_id

    if not appointment_id or not assigned_user_id:
        return

    try:
        from services.workflow_task_generator import generate_appointment_prep_tasks
        await _call_or_run(
            generate_appointment_prep_tasks,
            appointment_id=appointment_id,
            user_id=assigned_user_id,
            meeting_type=meeting_type,
            organization_id=org_id,
        )
        logger.info("Follow-up tasks created for appointment %s", appointment_id)
    except ImportError:
        logger.debug("workflow_task_generator not available — skipping task creation")
    except Exception as e:
        logger.error("Task creation failed for appointment %s: %s", appointment_id, e)
        raise


# =============================================================================
# Analytics / conversion tracking
# =============================================================================

async def on_appointment_completed_track_conversion(event: Event) -> None:
    """Track the appointment completion in the analytics pipeline."""
    data = event.data
    appointment_id = data.get("appointment_id")
    meeting_type = data.get("meeting_type")
    lead_id = data.get("lead_id")

    if not appointment_id:
        return

    try:
        from services.scheduling_intelligence import track_appointment_outcome
        await _call_or_run(
            track_appointment_outcome,
            appointment_id=appointment_id,
            outcome="completed",
            meeting_type=meeting_type,
            lead_id=lead_id,
        )
        logger.info("Conversion tracked for completed appointment %s", appointment_id)
    except ImportError:
        logger.debug("scheduling_intelligence not available — skipping conversion tracking")
    except Exception as e:
        logger.error("Conversion tracking failed for appointment %s: %s", appointment_id, e)
        raise


async def on_appointment_no_show_track(event: Event) -> None:
    """Record a no-show event for analytics and potential re-engagement."""
    data = event.data
    appointment_id = data.get("appointment_id")

    if not appointment_id:
        return

    try:
        from services.scheduling_intelligence import track_appointment_outcome
        await _call_or_run(
            track_appointment_outcome,
            appointment_id=appointment_id,
            outcome="no_show",
            meeting_type=data.get("meeting_type"),
            lead_id=data.get("lead_id"),
        )
        logger.info("No-show tracked for appointment %s", appointment_id)
    except ImportError:
        logger.debug("scheduling_intelligence not available — skipping no-show tracking")
    except Exception as e:
        logger.error("No-show tracking failed for appointment %s: %s", appointment_id, e)
        raise


# =============================================================================
# Audit logging
# =============================================================================

async def on_any_appointment_event_audit_log(event: Event) -> None:
    """Write every appointment lifecycle event to SchedulerAuditLog.

    This subscriber is registered for all appointment event types to provide
    a complete audit trail.
    """
    data = event.data
    appointment_id = data.get("appointment_id")
    org_id = event.org_id

    if not appointment_id:
        return

    # Map event type to audit action
    action_map = {
        EventType.APPOINTMENT_CREATED: "created",
        EventType.APPOINTMENT_CONFIRMED: "confirmed",
        EventType.APPOINTMENT_CANCELLED: "cancelled",
        EventType.APPOINTMENT_RESCHEDULED: "rescheduled",
        EventType.APPOINTMENT_COMPLETED: "completed",
        EventType.APPOINTMENT_NO_SHOW: "no_show",
        EventType.SLOT_HELD: "slot_held",
        EventType.SLOT_RELEASED: "slot_released",
        EventType.BOOKING_CONFLICT: "booking_conflict",
        EventType.WAITLIST_NOTIFIED: "waitlist_notified",
    }
    action = action_map.get(event.type, event.type.value)

    try:
        from db import SessionLocal
        from smart_scheduler_models import create_smart_scheduler_models
        from db import Base

        models = create_smart_scheduler_models(Base)
        AuditLog = models["SchedulerAuditLog"]

        session = SessionLocal()
        # TENANT-017: Set RLS context for event subscriber
        if org_id:
            try:
                from database.tenant_mixin import set_tenant_context
                set_tenant_context(session, int(org_id))
            except Exception:
                pass
        try:
            log_entry = AuditLog(
                organization_id=int(org_id) if org_id else None,
                user_id=data.get("changed_by_user_id"),
                action=action,
                entity_type="appointment",
                entity_id=appointment_id,
                changes={
                    "event_type": event.type.value,
                    "correlation_id": event.correlation_id,
                    "source": event.source,
                    "timestamp": event.timestamp.isoformat(),
                    **{k: v for k, v in data.items() if k not in ("appointment_id",)},
                },
            )
            session.add(log_entry)
            session.commit()
            logger.debug("Audit log written for appointment %s action=%s", appointment_id, action)
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
    except ImportError:
        logger.debug("DB modules not available — skipping audit log")
    except Exception as e:
        logger.error("Audit logging failed for appointment %s: %s", appointment_id, e)
        raise


# =============================================================================
# POS application submitted — canonical store promotion
# =============================================================================

# Loan stages that are considered "earlier" than APPLICATION (i.e. stages
# where we should auto-advance to APPLICATION on 1003 submission).
_PRE_APPLICATION_STAGES = frozenset({"DISCLOSED"})


async def on_pos_application_submitted_promote(event: Event) -> None:
    """Map a submitted POS 1003 application onto the canonical Lead/Loan models.

    * If ``loan_id`` is present in the payload, update the existing Loan.
    * Otherwise create a new Loan linked to the Lead (via ``contact_id``).
    * Transition ``Loan.stage`` to APPLICATION if currently in an earlier stage.
    * Create a review Task for the assigned LO.
    * Write an audit log entry.
    """
    data = event.data
    application_id = data.get("application_id")
    contact_id = data.get("contact_id")
    payload = data.get("payload") or {}
    org_id = event.org_id

    if not contact_id:
        logger.warning(
            "on_pos_application_submitted_promote: missing contact_id — skipping [%s]",
            event.correlation_id,
        )
        return

    sections = payload.get("sections") or {}
    pii = payload.get("pii") or {}

    try:
        from db import SessionLocal
        from database.models.lead_loan import Lead, Loan
        from database.models.task import Task
    except ImportError:
        logger.debug("DB models not available — skipping POS application promotion")
        return

    session = SessionLocal()
    # TENANT-017: Set RLS context for event subscriber
    if org_id:
        try:
            from database.tenant_mixin import set_tenant_context
            set_tenant_context(session, int(org_id))
        except Exception:
            pass
    try:
        # ----- Resolve the Lead ------------------------------------------------
        lead = session.query(Lead).filter(Lead.id == int(contact_id)).first()
        if not lead:
            logger.error(
                "POS application %s: Lead (contact_id=%s) not found — skipping",
                application_id,
                contact_id,
            )
            return

        # ----- Update Lead fields from personal section -----------------------
        personal = (sections.get("personal") or {}).get("data") or {}
        if personal.get("first_name"):
            lead.first_name = personal["first_name"]
        if personal.get("last_name"):
            lead.last_name = personal["last_name"]
        if personal.get("first_name") or personal.get("last_name"):
            lead.name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
        if personal.get("email"):
            lead.email = personal["email"]
        if personal.get("phone"):
            lead.phone = personal["phone"]

        # Employment fields from employment section
        employment = (sections.get("employment") or {}).get("data") or {}
        if employment.get("employment_status"):
            lead.employment_status = employment["employment_status"]
        if employment.get("annual_income") is not None:
            try:
                lead.annual_income = float(employment["annual_income"])
            except (ValueError, TypeError):
                pass
        if employment.get("employer_name"):
            lead.employer_name = employment["employer_name"]

        # Mark application completion date on the lead
        lead.application_completed_date = datetime.now(timezone.utc)

        # ----- Resolve or create Loan -----------------------------------------
        loan_section = (sections.get("loan") or {}).get("data") or {}
        existing_loan_id = data.get("loan_id") or payload.get("loan_id")
        loan: Optional["Loan"] = None

        if existing_loan_id:
            loan = session.query(Loan).filter(Loan.id == int(existing_loan_id)).first()

        if loan is None:
            # Create a new Loan
            import uuid as _uuid
            loan_number = f"POS-{_uuid.uuid4().hex[:8].upper()}"
            loan = Loan(
                loan_number=loan_number,
                borrower_name=lead.name or f"{lead.first_name or ''} {lead.last_name or ''}".strip() or "Unknown Borrower",
                borrower_email=lead.email,
                borrower_phone=lead.phone,
                amount=float(loan_section.get("loan_amount") or 0) or 1.0,
                stage="APPLICATION",
                loan_officer_id=lead.owner_id,
                organization_id=int(org_id) if org_id else lead.organization_id,
            )
            session.add(loan)
            logger.info(
                "POS application %s: created new Loan %s for Lead %s",
                application_id,
                loan.loan_number,
                contact_id,
            )
        else:
            logger.info(
                "POS application %s: updating existing Loan %s",
                application_id,
                loan.id,
            )

        # ----- Apply section data to the Loan ---------------------------------
        if loan_section.get("loan_amount") is not None:
            try:
                loan.amount = float(loan_section["loan_amount"])
            except (ValueError, TypeError):
                pass
        if loan_section.get("loan_purpose"):
            loan.loan_purpose = loan_section["loan_purpose"]
        if loan_section.get("loan_type"):
            loan.loan_type = loan_section["loan_type"]
        if loan_section.get("property_type"):
            loan.property_type = loan_section["property_type"]
        if loan_section.get("purchase_price") is not None:
            try:
                loan.purchase_price = float(loan_section["purchase_price"])
            except (ValueError, TypeError):
                pass
        if loan_section.get("down_payment") is not None:
            try:
                loan.down_payment = float(loan_section["down_payment"])
            except (ValueError, TypeError):
                pass
        if loan_section.get("term") is not None:
            try:
                loan.term = int(loan_section["term"])
            except (ValueError, TypeError):
                pass

        # Property details from the residence section
        residence = (sections.get("residence") or {}).get("data") or {}
        if residence.get("property_address"):
            loan.property_address = residence["property_address"]
        if residence.get("city"):
            loan.property_city = residence["city"]
        if residence.get("state"):
            loan.property_state = residence["state"]
        if residence.get("zip_code"):
            loan.property_zip = residence["zip_code"]

        # PII → Lead encrypted fields (SSN/DOB live on Lead, not Loan)
        if pii.get("ssn"):
            # Lead doesn't have SSN column — store in user_metadata if needed.
            # (BorrowerProfile also has no SSN column.)
            lead.user_metadata = lead.user_metadata or {}
            # Do NOT store raw SSN in metadata — flag that it was received.
            lead.user_metadata = {
                **(lead.user_metadata or {}),
                "pos_ssn_received": True,
                "pos_dob": pii.get("dob"),
            }

        # ----- Stage promotion ------------------------------------------------
        current_stage = (loan.stage or "").upper()
        if current_stage in _PRE_APPLICATION_STAGES or not current_stage:
            loan.stage = "APPLICATION"
            loan.stage_changed_at = datetime.now(timezone.utc)
            loan.application_date = datetime.now(timezone.utc)
            logger.info(
                "POS application %s: promoted Loan %s stage %s → APPLICATION",
                application_id,
                loan.id or "(new)",
                current_stage or "(none)",
            )

        # ----- Create review Task for the LO ----------------------------------
        borrower_display = loan.borrower_name or "Unknown Borrower"
        task = Task(
            title=f"Review submitted 1003 application — {borrower_display}",
            description=(
                f"Borrower {borrower_display} submitted a 1003 application via the "
                f"self-service portal (POS application {application_id}). "
                f"Review the application data and verify completeness."
            ),
            status="pending",
            priority="high",
            owner_id=loan.loan_officer_id or lead.owner_id,
            lead_id=lead.id,
            loan_id=loan.id,  # may be None until flush for new loans
            organization_id=int(org_id) if org_id else lead.organization_id,
            related_contact_name=borrower_display,
            related_type="pos_application",
            due_date=datetime.now(timezone.utc),
        )
        session.add(task)

        session.flush()

        # Back-fill loan_id on the task if it was a new loan
        if task.loan_id is None and loan.id:
            task.loan_id = loan.id

        session.commit()

        logger.info(
            "POS application %s promoted: Loan=%s, Task=%s [%s]",
            application_id,
            loan.id,
            task.id,
            event.correlation_id,
        )
    except Exception as e:
        session.rollback()
        logger.error(
            "POS application promotion failed for %s: %s",
            application_id,
            e,
            exc_info=True,
        )
        raise
    finally:
        session.close()


async def on_pos_application_submitted_audit(event: Event) -> None:
    """Write an audit log entry for the POS application submission.

    Uses the Activity model with type=NOTE to create a persistent audit trail.
    """
    data = event.data
    application_id = data.get("application_id")
    org_id = event.org_id

    if not application_id:
        return

    try:
        from db import SessionLocal
        from database.models.communication import Activity
        from database.enums import ActivityType

        session = SessionLocal()
        # TENANT-017: Set RLS context for event subscriber
        if org_id:
            try:
                from database.tenant_mixin import set_tenant_context as _stc
                _stc(session, int(org_id))
            except Exception:
                pass
        try:
            activity = Activity(
                organization_id=int(org_id) if org_id else None,
                lead_id=int(data["contact_id"]) if data.get("contact_id") else None,
                type=ActivityType.NOTE,
                content=(
                    f"POS 1003 application {application_id} submitted. "
                    f"correlation_id={event.correlation_id}, source={event.source}"
                ),
                user_metadata={
                    "event_type": event.type.value,
                    "application_id": application_id,
                    "loan_id": data.get("loan_id"),
                    "contact_id": data.get("contact_id"),
                    "submitted_at": data.get("submitted_at"),
                    "correlation_id": event.correlation_id,
                },
            )
            session.add(activity)
            session.commit()
            logger.debug(
                "Audit log written for POS application %s [%s]",
                application_id,
                event.correlation_id,
            )
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
    except ImportError:
        logger.debug("Activity model not available — skipping POS application audit log")
    except Exception as e:
        logger.error("POS application audit logging failed for %s: %s", application_id, e)
        raise


async def on_pos_application_submitted_notify_lo(event: Event) -> None:
    """Send a new-application alert email to the assigned LO."""
    data = event.data
    application_id = data.get("application_id")
    payload = data.get("payload") or {}
    contact_id = data.get("contact_id")

    if not application_id or not contact_id:
        return

    try:
        from db import SessionLocal
        from database.models.lead_loan import Lead
        from database.models.core import User

        session = SessionLocal()
        # TENANT-017: Set RLS context for event subscriber
        _notify_org_id = event.org_id
        if _notify_org_id:
            try:
                from database.tenant_mixin import set_tenant_context as _stc
                _stc(session, int(_notify_org_id))
            except Exception:
                pass
        try:
            lead = session.query(Lead).filter(Lead.id == int(contact_id)).first()
            if not lead or not lead.owner_id:
                return

            lo = session.query(User).filter(User.id == lead.owner_id).first()
            if not lo or not getattr(lo, "email", None):
                return

            personal = ((payload.get("sections") or {}).get("personal") or {}).get("data") or {}
            loan_section = ((payload.get("sections") or {}).get("loan") or {}).get("data") or {}
            borrower_name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
            borrower_name = borrower_name or lead.name or "Unknown Borrower"

            from services.notification_service import notification_service
            await _call_or_run(
                notification_service.send_lo_new_application_alert,
                lo_email=lo.email,
                lo_name=getattr(lo, "full_name", "") or getattr(lo, "first_name", "") or "",
                borrower_name=borrower_name,
                borrower_email=personal.get("email") or lead.email or "",
                borrower_phone=personal.get("phone") or lead.phone,
                loan_purpose=loan_section.get("loan_purpose") or "",
                loan_amount=float(loan_section.get("loan_amount") or 0),
                application_id=application_id,
            )
            logger.info(
                "LO notification sent for POS application %s to %s",
                application_id,
                lo.email,
            )
        finally:
            session.close()
    except ImportError:
        logger.debug("notification_service not available — skipping LO alert for POS application")
    except Exception as e:
        logger.error("LO notification failed for POS application %s: %s", application_id, e)
        raise


# =============================================================================
# POS appointment booked
# =============================================================================


async def on_pos_appointment_booked_create_task(event: Event) -> None:
    """Create a Task for the LO when a borrower books via the POS portal."""
    data = event.data
    appointment_id = data.get("appointment_id")
    lo_user_id = data.get("loan_officer_user_id")
    meeting_type = data.get("meeting_type", "consultation")
    org_id = event.org_id

    if not appointment_id or not lo_user_id:
        logger.warning(
            "on_pos_appointment_booked_create_task: missing appointment_id or lo_user_id — skipping [%s]",
            event.correlation_id,
        )
        return

    try:
        from db import SessionLocal
        from database.models.task import Task
    except ImportError:
        logger.debug("DB models not available — skipping POS appointment task creation")
        return

    session = SessionLocal()
    # TENANT-017: Set RLS context for event subscriber
    if org_id:
        try:
            from database.tenant_mixin import set_tenant_context as _stc
            _stc(session, int(org_id))
        except Exception:
            pass
    try:
        task = Task(
            title=f"POS borrower booked {meeting_type} appointment — appointment #{appointment_id}",
            description=(
                f"A borrower booked a {meeting_type} appointment (#{appointment_id}) "
                f"through the self-service portal. Review and prepare."
            ),
            status="pending",
            priority="medium",
            owner_id=int(lo_user_id),
            organization_id=int(org_id) if org_id else None,
            related_type="pos_appointment",
            due_date=datetime.now(timezone.utc),
        )

        # Link to loan if available
        loan_id = data.get("loan_id")
        if loan_id:
            task.loan_id = int(loan_id)

        session.add(task)
        session.commit()
        logger.info(
            "Task created for POS appointment %s, LO user %s [%s]",
            appointment_id,
            lo_user_id,
            event.correlation_id,
        )
    except Exception as e:
        session.rollback()
        logger.error(
            "Task creation failed for POS appointment %s: %s",
            appointment_id,
            e,
            exc_info=True,
        )
        raise
    finally:
        session.close()


async def on_pos_appointment_booked_notify_lo(event: Event) -> None:
    """Send an email notification to the LO about the POS-originated appointment."""
    data = event.data
    appointment_id = data.get("appointment_id")
    lo_user_id = data.get("loan_officer_user_id")
    meeting_type = data.get("meeting_type", "consultation")

    if not appointment_id or not lo_user_id:
        return

    try:
        from services.notification_service import notification_service
        from db import SessionLocal
        from database.models.core import User

        session = SessionLocal()
        # TENANT-017: Set RLS context for event subscriber
        _appt_org_id = event.org_id
        if _appt_org_id:
            try:
                from database.tenant_mixin import set_tenant_context as _stc
                _stc(session, int(_appt_org_id))
            except Exception:
                pass
        try:
            lo = session.query(User).filter(User.id == int(lo_user_id)).first()
            if not lo or not getattr(lo, "email", None):
                return

            subject = f"New {meeting_type} appointment booked — #{appointment_id}"
            html_content = (
                f"<p>A borrower booked a <strong>{meeting_type}</strong> appointment "
                f"(#{appointment_id}) via the self-service portal.</p>"
                f"<p>Please review the borrower's application and prepare for the meeting.</p>"
            )
            await _call_or_run(
                notification_service.send_email,
                to_email=lo.email,
                subject=subject,
                html_content=html_content,
            )
            logger.info(
                "LO notification sent for POS appointment %s to %s",
                appointment_id,
                lo.email,
            )
        finally:
            session.close()
    except (ImportError, AttributeError):
        logger.debug("notification_service not available — skipping POS appointment LO alert")
    except Exception as e:
        logger.error("LO notification failed for POS appointment %s: %s", appointment_id, e)
        raise


async def on_pos_appointment_booked_audit(event: Event) -> None:
    """Write an audit log entry for POS appointment booking.

    Uses the Activity model with type=NOTE to create a persistent audit trail.
    """
    data = event.data
    appointment_id = data.get("appointment_id")
    org_id = event.org_id

    if not appointment_id:
        return

    try:
        from db import SessionLocal
        from database.models.communication import Activity
        from database.enums import ActivityType

        session = SessionLocal()
        try:
            activity = Activity(
                organization_id=int(org_id) if org_id else None,
                type=ActivityType.NOTE,
                content=(
                    f"POS borrower booked appointment #{appointment_id}. "
                    f"meeting_type={data.get('meeting_type')}, "
                    f"correlation_id={event.correlation_id}"
                ),
                user_metadata={
                    "event_type": event.type.value,
                    "appointment_id": appointment_id,
                    "application_id": data.get("application_id"),
                    "loan_id": data.get("loan_id"),
                    "loan_officer_user_id": data.get("loan_officer_user_id"),
                    "meeting_type": data.get("meeting_type"),
                    "correlation_id": event.correlation_id,
                },
            )
            session.add(activity)
            session.commit()
            logger.debug(
                "Audit log written for POS appointment %s [%s]",
                appointment_id,
                event.correlation_id,
            )
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
    except ImportError:
        logger.debug("Activity model not available — skipping POS appointment audit log")
    except Exception as e:
        logger.error("POS appointment audit logging failed for %s: %s", appointment_id, e)
        raise


# =============================================================================
# Slot management
# =============================================================================

async def on_slot_released_notify_waitlist(event: Event) -> None:
    """When a slot is released (cancellation), notify anyone on the waitlist."""
    data = event.data
    slot_start = data.get("slot_start")
    assigned_user_id = data.get("assigned_user_id")

    if not slot_start or not assigned_user_id:
        return

    try:
        from services.notification_service import notification_service
        await _call_or_run(
            notification_service.notify_waitlist,
            user_id=assigned_user_id,
            slot_start=slot_start,
            org_id=event.org_id,
        )
        logger.info("Waitlist notified for released slot at %s", slot_start)
    except (ImportError, AttributeError):
        logger.debug("Waitlist notification not available — skipping")
    except Exception as e:
        logger.error("Waitlist notification failed: %s", e)
        raise


# =============================================================================
# Registration
# =============================================================================

def register_all_subscribers() -> None:
    """Register all default event subscribers.  Call once during app startup."""

    # -- appointment.created --
    event_bus.subscribe(EventType.APPOINTMENT_CREATED, on_appointment_created_send_confirmation)
    event_bus.subscribe(EventType.APPOINTMENT_CREATED, on_appointment_created_sync_calendar)
    event_bus.subscribe(EventType.APPOINTMENT_CREATED, on_appointment_created_create_tasks)
    event_bus.subscribe(EventType.APPOINTMENT_CREATED, on_any_appointment_event_audit_log)

    # -- appointment.confirmed --
    event_bus.subscribe(EventType.APPOINTMENT_CONFIRMED, on_any_appointment_event_audit_log)

    # -- appointment.cancelled --
    event_bus.subscribe(EventType.APPOINTMENT_CANCELLED, on_appointment_cancelled_send_notification)
    event_bus.subscribe(EventType.APPOINTMENT_CANCELLED, on_appointment_cancelled_sync_calendar)
    event_bus.subscribe(EventType.APPOINTMENT_CANCELLED, on_any_appointment_event_audit_log)

    # -- appointment.rescheduled --
    event_bus.subscribe(EventType.APPOINTMENT_RESCHEDULED, on_any_appointment_event_audit_log)

    # -- appointment.completed --
    event_bus.subscribe(EventType.APPOINTMENT_COMPLETED, on_appointment_completed_track_conversion)
    event_bus.subscribe(EventType.APPOINTMENT_COMPLETED, on_any_appointment_event_audit_log)

    # -- appointment.no_show --
    event_bus.subscribe(EventType.APPOINTMENT_NO_SHOW, on_appointment_no_show_track)
    event_bus.subscribe(EventType.APPOINTMENT_NO_SHOW, on_any_appointment_event_audit_log)

    # -- slot.released --
    event_bus.subscribe(EventType.SLOT_RELEASED, on_slot_released_notify_waitlist)
    event_bus.subscribe(EventType.SLOT_RELEASED, on_any_appointment_event_audit_log)

    # -- slot.held --
    event_bus.subscribe(EventType.SLOT_HELD, on_any_appointment_event_audit_log)

    # -- booking.conflict --
    event_bus.subscribe(EventType.BOOKING_CONFLICT, on_any_appointment_event_audit_log)

    # -- waitlist.notified --
    event_bus.subscribe(EventType.WAITLIST_NOTIFIED, on_any_appointment_event_audit_log)

    # -- pos.application.submitted --
    event_bus.subscribe(EventType.POS_APPLICATION_SUBMITTED, on_pos_application_submitted_promote)
    event_bus.subscribe(EventType.POS_APPLICATION_SUBMITTED, on_pos_application_submitted_audit)
    event_bus.subscribe(EventType.POS_APPLICATION_SUBMITTED, on_pos_application_submitted_notify_lo)

    # -- pos.appointment.booked --
    event_bus.subscribe(EventType.POS_APPOINTMENT_BOOKED, on_pos_appointment_booked_create_task)
    event_bus.subscribe(EventType.POS_APPOINTMENT_BOOKED, on_pos_appointment_booked_notify_lo)
    event_bus.subscribe(EventType.POS_APPOINTMENT_BOOKED, on_pos_appointment_booked_audit)

    # -- borrower_agent events --
    try:
        from services.pos.borrower_agent_event_handlers import (
            on_application_escalation,
            on_meeting_booked,
            on_document_suggested,
            on_application_stall,
        )
        event_bus.subscribe(EventType.APPLICATION_ESCALATION, on_application_escalation)
        event_bus.subscribe(EventType.MEETING_BOOKED, on_meeting_booked)
        event_bus.subscribe(EventType.DOCUMENT_SUGGESTED, on_document_suggested)
        event_bus.subscribe(EventType.APPLICATION_STALL, on_application_stall)
    except ImportError:
        logger.debug("Borrower agent event handlers not available — skipping")

    logger.info(
        "Registered %d event subscribers across %d event types",
        event_bus.subscriber_count,
        len(EventType),
    )


# =============================================================================
# Helpers
# =============================================================================

async def _call_or_run(fn, **kwargs):
    """Call *fn* with **kwargs, awaiting if it returns a coroutine.

    Many service functions in the codebase are plain sync functions.  This
    helper lets subscribers call them without caring.
    """
    import asyncio
    import inspect

    if asyncio.iscoroutinefunction(fn):
        return await fn(**kwargs)
    else:
        result = fn(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
