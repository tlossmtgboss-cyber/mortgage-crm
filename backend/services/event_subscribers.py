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

        # Employment fields from employment section (nested under employer/income)
        employment = (sections.get("employment") or {}).get("data") or {}
        if employment.get("employment_type"):
            lead.employment_status = employment["employment_type"]
        employer = employment.get("employer") or {}
        if employer.get("name"):
            lead.employer_name = employer["name"]
        income = employment.get("income") or {}
        try:
            annual = sum(float(income.get(k) or 0) for k in ("base", "overtime", "bonus", "commission"))
            if annual > 0:
                lead.annual_income = annual
        except (ValueError, TypeError):
            pass

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

        # Subject property lives nested under loan_section["property"]
        subject_prop = loan_section.get("property") or {}
        if subject_prop.get("type"):
            loan.property_type = subject_prop["type"]
        if subject_prop.get("occupancy"):
            loan.occupancy_type = subject_prop["occupancy"]

        if loan_section.get("purchase_price") is not None:
            try:
                loan.purchase_price = float(loan_section["purchase_price"])
            except (ValueError, TypeError):
                pass

        # Down payment: frontend computes it (purchase_price - loan_amount)
        try:
            pp = float(loan_section.get("purchase_price") or 0)
            la = float(loan_section.get("loan_amount") or 0)
            if pp > 0 and la > 0 and la <= pp:
                loan.down_payment = pp - la
        except (ValueError, TypeError):
            pass

        if loan_section.get("term") is not None:
            try:
                loan.term = int(loan_section["term"])
            except (ValueError, TypeError):
                pass

        # Subject property address from loan section (not residence)
        if subject_prop.get("address"):
            loan.property_address = subject_prop["address"]
        if subject_prop.get("city"):
            loan.property_city = subject_prop["city"]
        if subject_prop.get("state"):
            loan.property_state = subject_prop["state"]
        if subject_prop.get("zip"):
            loan.property_zip = subject_prop["zip"]

        # Borrower's current address from residence section (nested under "current")
        residence = (sections.get("residence") or {}).get("data") or {}
        current_addr = residence.get("current") or {}
        if current_addr.get("street"):
            lead.address = current_addr["street"]
        if current_addr.get("city"):
            lead.city = current_addr["city"]
        if current_addr.get("state"):
            lead.state = current_addr["state"]
        if current_addr.get("zip"):
            lead.zip_code = current_addr["zip"]

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
# POS application submitted — MISMO 3.4 XML email to LO + team
# =============================================================================


def _flatten_pos_for_mismo(payload: dict) -> dict:
    """Flatten nested POS section data into the flat dict MISMOGenerator expects."""
    sections = payload.get("sections") or {}
    pii = payload.get("pii") or {}
    flat: dict = {}

    def _pull(section_key: str) -> dict:
        return ((sections.get(section_key) or {}).get("data") or {})

    personal = _pull("personal")
    flat.update({
        "first_name": personal.get("first_name", ""),
        "last_name": personal.get("last_name", ""),
        "middle_name": personal.get("middle_name", ""),
        "email": personal.get("email", ""),
        "phone": personal.get("phone", ""),
        "marital_status": personal.get("marital_status", ""),
        "dependents_count": personal.get("dependents_count", 0),
        "citizenship_status": personal.get("citizenship_status", ""),
    })

    coborrower = _pull("coborrower")
    if coborrower.get("first_name"):
        flat["has_coborrower"] = True
        flat.update({
            "co_first_name": coborrower.get("first_name", ""),
            "co_last_name": coborrower.get("last_name", ""),
            "co_email": coborrower.get("email", ""),
            "co_phone": coborrower.get("phone", ""),
        })

    employment = _pull("employment")
    flat.update({
        "employment_type": employment.get("employment_type", ""),
        "employerName": employment.get("employer_name", ""),
        "job_title": employment.get("job_title", ""),
        "years_employed": employment.get("years_at_job", 0),
        "annual_income": employment.get("annual_income", 0),
        "monthly_bonus": employment.get("monthly_bonus", 0),
        "monthly_commission": employment.get("monthly_commission", 0),
        "other_income": employment.get("other_income", 0),
        "other_income_source": employment.get("other_income_source", ""),
    })

    loan = _pull("loan")
    flat.update({
        "loan_purpose": loan.get("loan_purpose", ""),
        "purchase_price": loan.get("purchase_price", 0),
        "down_payment": loan.get("down_payment", 0),
        "down_payment_type": loan.get("down_payment_type", "percentage"),
        "property_type": loan.get("property_type", ""),
        "occupancy": loan.get("occupancy", ""),
        "monthly_rent_mortgage": loan.get("monthly_rent_mortgage", 0),
        "propertyAddress": loan.get("property_address", ""),
        "city": loan.get("city", ""),
        "state": loan.get("state", ""),
        "zip": loan.get("zip", ""),
        "county": loan.get("county", ""),
    })

    assets = _pull("assets")
    flat.update({
        "checking_balance": assets.get("checking_balance", 0),
        "savings_balance": assets.get("savings_balance", 0),
        "investment_value": assets.get("investment_value", 0),
        "retirement_value": assets.get("retirement_value", 0),
        "other_assets": assets.get("other_assets", 0),
        "gift_funds": assets.get("gift_funds", 0),
    })

    liabilities = _pull("liabilities")
    flat.update({
        "car_payment": liabilities.get("car_payment", 0),
        "student_loans": liabilities.get("student_loans", 0),
        "credit_card_payments": liabilities.get("credit_card_payments", 0),
        "child_support": liabilities.get("child_support", 0),
        "other_debts": liabilities.get("other_debts", 0),
    })

    declarations = _pull("declarations")
    flat.update({
        "has_bankruptcy": declarations.get("has_bankruptcy", False),
        "has_foreclosure": declarations.get("has_foreclosure", False),
        "has_lawsuit": declarations.get("has_lawsuit", False),
        "will_occupy_property": declarations.get("will_occupy_property", True),
        "has_delinquent_debt": declarations.get("has_delinquent_debt", False),
    })

    if pii.get("ssn"):
        flat["ssn"] = pii["ssn"]
    if pii.get("dob"):
        flat["dob"] = pii["dob"]

    return flat


def _build_application_summary_html(payload: dict, borrower_name: str, application_id: str) -> str:
    """Build a detailed HTML email body with the full application summary."""
    import html as html_mod
    sections = payload.get("sections") or {}

    def _pull(key: str) -> dict:
        return ((sections.get(key) or {}).get("data") or {})

    personal = _pull("personal")
    employment = _pull("employment")
    loan = _pull("loan")
    assets = _pull("assets")
    liabilities = _pull("liabilities")
    declarations = _pull("declarations")
    coborrower = _pull("coborrower")
    residence = _pull("residence")

    def _esc(v: object) -> str:
        return html_mod.escape(str(v)) if v else ""

    def _money(v: object) -> str:
        try:
            return f"${float(v or 0):,.0f}"
        except (ValueError, TypeError):
            return "$0"

    def _row(label: str, value: str) -> str:
        if not value or value in ("", "$0", "None"):
            return ""
        return f"""<tr>
            <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#6b7280;">{label}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#111827;text-align:right;">{value}</td>
        </tr>"""

    purpose = _esc((loan.get("loan_purpose") or "").replace("_", " ").title())

    rows_personal = "".join(filter(None, [
        _row("Name", _esc(f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip())),
        _row("Email", _esc(personal.get("email"))),
        _row("Phone", _esc(personal.get("phone"))),
        _row("Marital Status", _esc((personal.get("marital_status") or "").title())),
        _row("Citizenship", _esc((personal.get("citizenship_status") or "").replace("_", " ").title())),
    ]))

    rows_loan = "".join(filter(None, [
        _row("Loan Purpose", purpose),
        _row("Purchase Price", _money(loan.get("purchase_price"))),
        _row("Down Payment", _money(loan.get("down_payment")) if loan.get("down_payment_type") != "percentage" else f"{loan.get('down_payment', 0)}%"),
        _row("Property Type", _esc((loan.get("property_type") or "").replace("_", " ").title())),
        _row("Occupancy", _esc((loan.get("occupancy") or "").replace("_", " ").title())),
        _row("Property Address", _esc(loan.get("property_address"))),
        _row("City / State / ZIP", _esc(f"{loan.get('city', '')} {loan.get('state', '')} {loan.get('zip', '')}".strip())),
    ]))

    rows_employment = "".join(filter(None, [
        _row("Employer", _esc(employment.get("employer_name"))),
        _row("Title", _esc(employment.get("job_title"))),
        _row("Type", _esc((employment.get("employment_type") or "").replace("_", " ").title())),
        _row("Annual Income", _money(employment.get("annual_income"))),
    ]))

    rows_assets = "".join(filter(None, [
        _row("Checking", _money(assets.get("checking_balance"))),
        _row("Savings", _money(assets.get("savings_balance"))),
        _row("Investments", _money(assets.get("investment_value"))),
        _row("Retirement", _money(assets.get("retirement_value"))),
        _row("Gift Funds", _money(assets.get("gift_funds"))),
    ]))

    rows_liabilities = "".join(filter(None, [
        _row("Car Payment", _money(liabilities.get("car_payment"))),
        _row("Student Loans", _money(liabilities.get("student_loans"))),
        _row("Credit Cards", _money(liabilities.get("credit_card_payments"))),
        _row("Child Support", _money(liabilities.get("child_support"))),
        _row("Other Debts", _money(liabilities.get("other_debts"))),
    ]))

    declaration_flags = []
    for key, label in [
        ("has_bankruptcy", "Bankruptcy"),
        ("has_foreclosure", "Foreclosure"),
        ("has_lawsuit", "Lawsuit"),
        ("has_delinquent_debt", "Delinquent Debt"),
    ]:
        if declarations.get(key):
            declaration_flags.append(label)
    declarations_text = ", ".join(declaration_flags) if declaration_flags else "None disclosed"

    coborrower_html = ""
    if coborrower.get("first_name"):
        coborrower_html = f"""
        <h3 style="color:#218D8D;margin:24px 0 12px;">Co-Borrower</h3>
        <table style="width:100%;border-collapse:collapse;">
            {_row("Name", _esc(f"{coborrower.get('first_name', '')} {coborrower.get('last_name', '')}".strip()))}
            {_row("Email", _esc(coborrower.get("email")))}
            {_row("Phone", _esc(coborrower.get("phone")))}
        </table>
        """

    residence_html = ""
    if residence.get("current_address"):
        residence_html = f"""
        <h3 style="color:#218D8D;margin:24px 0 12px;">Current Residence</h3>
        <table style="width:100%;border-collapse:collapse;">
            {_row("Address", _esc(residence.get("current_address")))}
            {_row("Ownership", _esc((residence.get("ownership_status") or "").replace("_", " ").title()))}
            {_row("Monthly Payment", _money(residence.get("monthly_payment")))}
            {_row("Years at Address", _esc(residence.get("years_at_address")))}
        </table>
        """

    safe_app_id = html_mod.escape(application_id or "")
    safe_borrower = html_mod.escape(borrower_name or "Unknown Borrower")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:0;background:#f6f9fc;">
<div style="max-width:700px;margin:0 auto;padding:40px 20px;">
<div style="background:white;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,0.08);padding:40px;">

<div style="background:#218D8D;color:white;padding:16px 24px;margin:-40px -40px 32px;border-radius:16px 16px 0 0;">
    <h1 style="margin:0;font-size:20px;">1003 Application Submitted</h1>
    <p style="margin:4px 0 0;opacity:0.85;font-size:14px;">Application #{safe_app_id[:8]}</p>
</div>

<h2 style="color:#111827;font-size:22px;margin:0 0 4px;">{safe_borrower}</h2>
<p style="color:#6b7280;margin:0 0 24px;font-size:14px;">{purpose} &mdash; {_money(loan.get("purchase_price") or loan.get("loan_amount"))}</p>

<h3 style="color:#218D8D;margin:0 0 12px;">Borrower Information</h3>
<table style="width:100%;border-collapse:collapse;">{rows_personal}</table>

{coborrower_html}
{residence_html}

<h3 style="color:#218D8D;margin:24px 0 12px;">Loan Details</h3>
<table style="width:100%;border-collapse:collapse;">{rows_loan}</table>

<h3 style="color:#218D8D;margin:24px 0 12px;">Employment &amp; Income</h3>
<table style="width:100%;border-collapse:collapse;">{rows_employment}</table>

<h3 style="color:#218D8D;margin:24px 0 12px;">Assets</h3>
<table style="width:100%;border-collapse:collapse;">{rows_assets}</table>

<h3 style="color:#218D8D;margin:24px 0 12px;">Liabilities (Monthly)</h3>
<table style="width:100%;border-collapse:collapse;">{rows_liabilities}</table>

<h3 style="color:#218D8D;margin:24px 0 12px;">Declarations</h3>
<p style="color:#111827;margin:0 0 24px;">{declarations_text}</p>

{{{{NOTES_SECTION}}}}

<div style="text-align:center;margin:32px 0 0;">
    <a href="{{{{FRONTEND_URL}}}}/applications/{safe_app_id}" style="display:inline-block;background:#218D8D;color:white;text-decoration:none;padding:14px 32px;border-radius:8px;font-weight:600;font-size:16px;">
        View in Perennia
    </a>
</div>

<p style="color:#9ca3af;font-size:12px;margin:24px 0 0;text-align:center;">
    A MISMO 3.4 XML file is attached to this email for LOS import.
</p>

</div></div></body></html>"""


async def on_pos_application_submitted_mismo_email(event: Event) -> None:
    """Generate MISMO 3.4 XML, build application summary email, and send to LO + team."""
    data = event.data
    application_id = data.get("application_id")
    payload = data.get("payload") or {}
    contact_id = data.get("contact_id")

    if not application_id or not contact_id:
        return

    try:
        import base64
        from db import SessionLocal
        from database.models.lead_loan import Lead
        from database.models.core import User
        from services.mismo_generator import MISMOGenerator
        from services.notification_service import notification_service

        session = SessionLocal()
        _org_id = event.org_id
        if _org_id:
            try:
                from database.tenant_mixin import set_tenant_context as _stc
                _stc(session, int(_org_id))
            except Exception:
                pass
        try:
            lead = session.query(Lead).filter(Lead.id == int(contact_id)).first()
            if not lead or not lead.owner_id:
                logger.warning(
                    "MISMO email: no lead or owner for contact %s — skipping", contact_id
                )
                return

            lo = session.query(User).filter(User.id == lead.owner_id).first()
            if not lo or not getattr(lo, "email", None):
                return

            personal = ((payload.get("sections") or {}).get("personal") or {}).get("data") or {}
            borrower_name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
            borrower_name = borrower_name or lead.name or "Unknown Borrower"

            # -- Generate MISMO 3.4 XML --
            flat_data = _flatten_pos_for_mismo(payload)
            generator = MISMOGenerator()
            mismo_xml = generator.generate(flat_data)
            filename = generator.generate_filename(str(application_id)[:8])

            # -- Gather borrower notes / messages --
            notes_html = ""
            try:
                from database.models.pos import POSBorrowerMessage
                messages = (
                    session.query(POSBorrowerMessage)
                    .filter(POSBorrowerMessage.application_id == application_id)
                    .order_by(POSBorrowerMessage.created_at.asc())
                    .limit(50)
                    .all()
                )
                if messages:
                    msg_rows = ""
                    for msg in messages:
                        ts = msg.created_at.strftime("%b %d, %I:%M %p") if msg.created_at else ""
                        sender = msg.sender_name or "Borrower"
                        import html as html_mod
                        content = html_mod.escape(msg.content or "")
                        msg_rows += f"""<tr>
                            <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#6b7280;white-space:nowrap;vertical-align:top;font-size:13px;">{ts}<br/><strong>{sender}</strong></td>
                            <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#111827;font-size:13px;">{content}</td>
                        </tr>"""
                    notes_html = f"""
                    <h3 style="color:#218D8D;margin:24px 0 12px;">Messages &amp; Notes</h3>
                    <table style="width:100%;border-collapse:collapse;">{msg_rows}</table>
                    """
            except Exception as e:
                logger.debug("Could not fetch POS messages for MISMO email: %s", e)

            # Also include Aria Q&A conversation as notes
            try:
                from database.models.pos import POSAIQAMessage
                qa_messages = (
                    session.query(POSAIQAMessage)
                    .filter(POSAIQAMessage.application_id == application_id)
                    .order_by(POSAIQAMessage.created_at.asc())
                    .limit(50)
                    .all()
                )
                if qa_messages:
                    qa_rows = ""
                    for msg in qa_messages:
                        ts = msg.created_at.strftime("%b %d, %I:%M %p") if msg.created_at else ""
                        role_label = "Borrower" if msg.role == "borrower" else "Aria"
                        import html as html_mod
                        content = html_mod.escape(msg.content or "")
                        if len(content) > 500:
                            content = content[:500] + "..."
                        qa_rows += f"""<tr>
                            <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#6b7280;white-space:nowrap;vertical-align:top;font-size:13px;">{ts}<br/><strong>{role_label}</strong></td>
                            <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#111827;font-size:13px;">{content}</td>
                        </tr>"""
                    notes_html += f"""
                    <h3 style="color:#218D8D;margin:24px 0 12px;">Aria Q&amp;A History</h3>
                    <table style="width:100%;border-collapse:collapse;">{qa_rows}</table>
                    """
            except Exception as e:
                logger.debug("Could not fetch Aria Q&A for MISMO email: %s", e)

            # -- Build email --
            import os
            frontend_url = os.environ.get("FRONTEND_URL", "https://app.perenniaai.com")
            email_html = _build_application_summary_html(payload, borrower_name, application_id)
            email_html = email_html.replace("{{NOTES_SECTION}}", notes_html)
            email_html = email_html.replace("{{FRONTEND_URL}}", frontend_url)

            # -- Gather team CC recipients --
            cc_emails = []
            try:
                from sqlalchemy import text as sa_text
                team_rows = session.execute(
                    sa_text(
                        "SELECT u.email FROM default_role_assignments dra "
                        "JOIN users u ON u.id = dra.user_id "
                        "WHERE dra.organization_id = :org_id AND u.is_active = true AND u.email IS NOT NULL"
                    ),
                    {"org_id": int(_org_id)} if _org_id else {},
                ).fetchall()
                cc_emails = [
                    r[0] for r in team_rows
                    if r[0] and r[0] != lo.email
                ]
            except Exception as e:
                logger.debug("Could not fetch team for MISMO email CC: %s", e)

            # -- Attach MISMO XML as base64 --
            xml_b64 = base64.b64encode(mismo_xml.encode("utf-8")).decode("utf-8")
            attachments = [{
                "content": xml_b64,
                "filename": filename,
                "type": "application/xml",
            }]

            subject = f"1003 Application — {borrower_name}"

            await _call_or_run(
                notification_service.send_email,
                to_email=lo.email,
                subject=subject,
                html_content=email_html,
                attachments=attachments,
                cc=cc_emails[:10] if cc_emails else None,
            )
            logger.info(
                "MISMO 3.4 email sent for POS application %s to %s (cc: %d)",
                application_id,
                lo.email,
                len(cc_emails),
            )
        finally:
            session.close()
    except ImportError as e:
        logger.debug("MISMO email: import not available — skipping: %s", e)
    except Exception as e:
        logger.error("MISMO email failed for POS application %s: %s", application_id, e)
        raise


# =============================================================================
# POS submission — Aria intro SMS + team contact card
# =============================================================================


async def on_pos_application_submitted_sms_intro(event: Event) -> None:
    """Send Aria's welcome SMS sequence with team vCard to the applicant.

    3-message sequence via Telnyx (+18438838956):
      1. Aria introduces herself as the LO's AI assistant
      2. Prompt to save the team contact card
      3. MMS with the team vCard attachment
    """
    import asyncio
    import os
    import time

    data = event.data
    application_id = data.get("application_id")
    contact_id = data.get("contact_id")
    payload = data.get("payload") or {}
    org_id = event.org_id

    if not contact_id:
        logger.warning("sms_intro: no contact_id — skipping [%s]", event.correlation_id)
        return

    sections = payload.get("sections") or {}
    personal = (sections.get("personal") or {}).get("data") or {}
    borrower_first = personal.get("first_name") or "there"

    try:
        from db import SessionLocal
        from database.models.lead_loan import Lead
        from database.models.core import User, Organization
    except ImportError:
        logger.debug("sms_intro: DB models not available — skipping")
        return

    session = SessionLocal()
    if org_id:
        try:
            from database.tenant_mixin import set_tenant_context
            set_tenant_context(session, int(org_id))
        except Exception:
            pass

    try:
        lead = session.query(Lead).filter(Lead.id == int(contact_id)).first()
        if not lead:
            logger.error("sms_intro: Lead %s not found — skipping", contact_id)
            return

        borrower_phone = lead.phone or personal.get("phone")
        if not borrower_phone:
            logger.warning("sms_intro: no borrower phone on lead %s — skipping", contact_id)
            return
        if borrower_first == "there" and lead.first_name:
            borrower_first = lead.first_name

        lo_name = "your loan officer"
        lo_user_id = lead.owner_id
        if lo_user_id:
            lo = session.query(User).filter(User.id == lo_user_id).first()
            if lo:
                lo_name = (lo.full_name or f"{lo.first_name or ''} {lo.last_name or ''}".strip()) or "your loan officer"

        company_name = "Perennia AI"
        if lead.organization_id:
            org = session.query(Organization).filter(Organization.id == lead.organization_id).first()
            if org and org.name:
                company_name = org.name

        # ── Message 1: Aria introduction ──────────────────────────────
        msg1 = (
            f"Hi {borrower_first}! This is Aria, {lo_name}'s AI assistant at "
            f"{company_name}. Thank you for submitting your mortgage application! "
            f"I'm here to help with anything you need throughout your loan process "
            f"— just text me anytime with questions."
        )

        # ── Message 2: Save contact prompt ────────────────────────────
        msg2 = (
            f"I'm sending you {lo_name}'s team contact card now — please save it "
            f"to your phone so you'll always know who's calling you in the future."
        )

        # ── Message 3: MMS vCard ──────────────────────────────────────
        from routes.vcard_routes import _sign_vcard_token
        vcard_token = _sign_vcard_token(lead.id)
        api_domain = os.getenv("API_BASE_URL", "https://api.perenniaai.com")
        vcard_url = f"{api_domain}/api/v1/vcard/team/{vcard_token}"

        from telephony.sms import send_sms_verified
        telnyx_from = os.getenv("TELNYX_PHONE_NUMBER", "+18438838956")
        org_id_int = int(org_id) if org_id else None

        r1 = send_sms_verified(
            to=borrower_phone,
            from_=telnyx_from,
            text=msg1,
            user_id=lo_user_id,
            lead_id=lead.id,
            organization_id=org_id_int,
            db=session,
            bypass_compliance=True,
        )
        logger.info(
            "sms_intro msg1 to ...%s: %s",
            borrower_phone[-4:] if borrower_phone else "?",
            r1.get("status"),
        )

        await asyncio.sleep(2)

        r2 = send_sms_verified(
            to=borrower_phone,
            from_=telnyx_from,
            text=msg2,
            user_id=lo_user_id,
            lead_id=lead.id,
            organization_id=org_id_int,
            db=session,
            bypass_compliance=True,
        )
        logger.info("sms_intro msg2: %s", r2.get("status"))

        await asyncio.sleep(2)

        r3 = send_sms_verified(
            to=borrower_phone,
            from_=telnyx_from,
            text=f"Contact card for {lo_name}'s team at {company_name}",
            media_urls=[vcard_url],
            user_id=lo_user_id,
            lead_id=lead.id,
            organization_id=org_id_int,
            db=session,
            bypass_compliance=True,
        )
        logger.info("sms_intro vcard MMS: %s", r3.get("status"))

    except Exception as e:
        logger.error("sms_intro failed for POS application %s: %s", application_id, e)
    finally:
        session.close()


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
    event_bus.subscribe(EventType.POS_APPLICATION_SUBMITTED, on_pos_application_submitted_mismo_email)
    event_bus.subscribe(EventType.POS_APPLICATION_SUBMITTED, on_pos_application_submitted_sms_intro)

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
