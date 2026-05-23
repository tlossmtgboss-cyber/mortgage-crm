"""Application service — owns the borrower's URLA draft lifecycle."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from database.models.pos import (
    POSAIQAMessage,
    POSApplication,
    POSApplicationAudit,
    POSApplicationPII,
    POSApplicationSection,
    POSAuditEvent,
    POSSectionKey,
    POSStatus,
    calculate_completion_pct,
)
from services.event_bus import Event, EventType, event_bus


logger = logging.getLogger(__name__)


# Required certifications for a valid submit.
REQUIRED_CERTIFICATIONS = frozenset(
    {"truth_certification", "esign_consent", "credit_authorization"}
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ApplicationNotFoundError(LookupError):
    """Raised when the application doesn't exist or isn't visible to the borrower.

    Same exception is used for both cases — never leak whether a row exists
    for a different borrower (see services/pos/_helpers.py).
    """


class ApplicationStateError(ValueError):
    """Raised when an operation is invalid for the application's current state."""


# ---------------------------------------------------------------------------
# Audit context
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Per-request context that gets stamped onto audit rows."""

    actor_type: str  # 'borrower' | 'lo' | 'system'
    actor_id: int | None
    ip_address: str | None
    user_agent: str | None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ApplicationService:
    """Owns POSApplication CRUD and the submit transition.

    Stateless — every method takes the Session explicitly, matching
    Perennia's existing service pattern.
    """

    # ----- read paths --------------------------------------------------------

    def get_for_borrower(
        self,
        session: Session,
        application_id: UUID,
        contact_id: int,
    ) -> POSApplication:
        """Fetch an application, asserting the contact owns it.

        Raises ApplicationNotFoundError if the app doesn't exist OR if it
        belongs to a different contact (same exception class — no info leak).
        """
        stmt = (
            select(POSApplication)
            .where(
                and_(
                    POSApplication.id == application_id,
                    POSApplication.contact_id == contact_id,
                )
            )
            .options(
                selectinload(POSApplication.sections),
                selectinload(POSApplication.pii),
            )
        )
        result = session.execute(stmt)
        app = result.scalar_one_or_none()
        if app is None:
            raise ApplicationNotFoundError(
                f"Application {application_id} not found for this borrower"
            )
        return app

    def get_or_create_for_loan(
        self,
        session: Session,
        *,
        organization_id: int,
        workspace_id: int,
        contact_id: int,
        loan_id: int | None,
        source_channel: str | None = None,
        ctx: AuditContext,
    ) -> POSApplication:
        """Return the in-progress draft for this borrower+loan, creating one if needed.

        Enforced by the partial unique index `ix_pos_app_one_active_per_loan`
        at the database level.
        """
        stmt = select(POSApplication).where(
            and_(
                POSApplication.contact_id == contact_id,
                POSApplication.loan_id == loan_id if loan_id is not None else POSApplication.loan_id.is_(None),
                POSApplication.status == POSStatus.DRAFT,
            )
        )
        result = session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        try:
            nested = session.begin_nested()
            app = POSApplication(
                organization_id=organization_id,
                workspace_id=workspace_id,
                contact_id=contact_id,
                loan_id=loan_id,
                source_channel=source_channel,
                status=POSStatus.DRAFT,
                current_step=POSSectionKey.PERSONAL,
                completion_pct=0,
            )
            session.add(app)
            session.flush()
        except IntegrityError:
            nested.rollback()
            result = session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is not None:
                return existing
            raise

        self._write_audit(
            session,
            application_id=app.id,
            ctx=ctx,
            event_type=POSAuditEvent.APPLICATION_CREATED,
        )
        return app

    # ----- section updates ---------------------------------------------------

    def upsert_section(
        self,
        session: Session,
        *,
        application: POSApplication,
        section_key: str,
        data: dict[str, Any],
        mark_complete: bool = False,
        expected_updated_at: Any = None,
        ctx: AuditContext,
    ) -> POSApplicationSection:
        """Insert or update a section's JSON data.

        For the 'personal' section, callers should strip SSN/DOB out of `data`
        and pass them to `upsert_pii` separately — those go to the encrypted
        PII table, not the JSONB section.
        """
        if section_key not in POSSectionKey.ALL_VALID:
            raise ApplicationStateError(f"Unknown section_key: {section_key}")
        if application.status != POSStatus.DRAFT:
            raise ApplicationStateError(
                f"Cannot modify sections of a {application.status} application"
            )

        _PII_KEYS = {"ssn", "co_ssn", "dob", "co_dob",
                      "social_security_number", "date_of_birth"}
        pii_extracted = {k: data.pop(k) for k in list(data.keys()) if k in _PII_KEYS}
        if pii_extracted:
            self.upsert_pii(
                session,
                application=application,
                ssn=pii_extracted.get("ssn") or pii_extracted.get("social_security_number"),
                co_ssn=pii_extracted.get("co_ssn"),
                dob=pii_extracted.get("dob") or pii_extracted.get("date_of_birth"),
                co_dob=pii_extracted.get("co_dob"),
            )

        # Find existing or create.
        section = next(
            (s for s in application.sections if s.section_key == section_key),
            None,
        )

        if section is not None and expected_updated_at is not None:
            session.refresh(section, ["updated_at"])
            if section.updated_at != expected_updated_at:
                raise ApplicationStateError(
                    "Section was modified by another session. "
                    "Refresh and retry."
                )

        previously_complete = section.is_complete if section else False

        if section is None:
            section = POSApplicationSection(
                application_id=application.id,
                section_key=section_key,
                data=data or {},
                is_complete=False,
            )
            session.add(section)
        else:
            section.data = data or {}

        # Completion transition.
        newly_completed = False
        if mark_complete and not section.is_complete:
            section.is_complete = True
            section.completed_at = datetime.now(timezone.utc)
            newly_completed = True

        session.flush()

        # Recompute completion percentage on the application root.
        complete_count = sum(1 for s in application.sections if s.is_complete)
        application.completion_pct = calculate_completion_pct(complete_count)

        # Advance current_step if appropriate.
        if newly_completed:
            application.current_step = self._next_step(section_key)

        # Audit.
        self._write_audit(
            session,
            application_id=application.id,
            ctx=ctx,
            event_type=(
                POSAuditEvent.SECTION_COMPLETED
                if newly_completed
                else POSAuditEvent.SECTION_UPDATED
            ),
            section_key=section_key,
            # Delta intentionally omits the full data blob — auditors don't
            # need every keystroke, just the fact that the section changed.
            delta={"keys_present": sorted(data.keys()) if data else []},
        )
        return section

    def upsert_pii(
        self,
        session: Session,
        *,
        application: POSApplication,
        ssn: str | None = None,
        co_ssn: str | None = None,
        dob: Any = None,
        co_dob: Any = None,
    ) -> POSApplicationPII:
        """Write encrypted SSN / DOB to the separate PII table.

        Each parameter is independently optional — pass only what the borrower
        just edited. None means "do not modify"; an empty string means "clear".
        """
        if application.status != POSStatus.DRAFT:
            raise ApplicationStateError(
                f"Cannot modify PII of a {application.status} application"
            )

        pii = application.pii
        if pii is None:
            pii = POSApplicationPII(application_id=application.id)
            session.add(pii)

        # Use a sentinel-free pattern: the schemas validate format before this
        # is called, so by the time we get here `None` always means "skip".
        if ssn is not None:
            pii.ssn_encrypted = ssn or None  # EncryptedString handles encryption
        if co_ssn is not None:
            pii.co_ssn_encrypted = co_ssn or None
        if dob is not None:
            pii.dob_encrypted = dob.isoformat() if dob else None
        if co_dob is not None:
            pii.co_dob_encrypted = co_dob.isoformat() if co_dob else None

        session.flush()
        return pii

    # ----- submit ------------------------------------------------------------

    async def submit(
        self,
        session: Session,
        *,
        application: POSApplication,
        appointment_id: int | None,
        acknowledged_certifications: list[str],
        ctx: AuditContext,
    ) -> POSApplication:
        """Transition the application from draft to submitted."""
        if application.status != POSStatus.DRAFT:
            raise ApplicationStateError(
                f"Application is already {application.status}; cannot submit again"
            )

        # All required sections must be complete.
        complete_keys = {s.section_key for s in application.sections if s.is_complete}
        # The 'review' section is the act of submitting itself, so we don't
        # require it to be complete before submit.
        required = set(POSSectionKey.ORDERED) - {POSSectionKey.REVIEW}
        missing = required - complete_keys
        if missing:
            raise ApplicationStateError(
                f"Cannot submit — these sections are incomplete: {sorted(missing)}"
            )

        # All three required certifications must be acknowledged.
        ack = set(acknowledged_certifications)
        missing_certs = REQUIRED_CERTIFICATIONS - ack
        if missing_certs:
            raise ApplicationStateError(
                f"Cannot submit — missing certifications: {sorted(missing_certs)}"
            )

        # Transition.
        now = datetime.now(timezone.utc)
        application.status = POSStatus.SUBMITTED
        application.submitted_at = now
        application.submitted_appointment_id = appointment_id
        application.completion_pct = 100

        # Mark the review section complete as a side effect.
        review_section = next(
            (s for s in application.sections if s.section_key == POSSectionKey.REVIEW),
            None,
        )
        if review_section is None:
            review_section = POSApplicationSection(
                application_id=application.id,
                section_key=POSSectionKey.REVIEW,
                data={"acknowledged": list(ack)},
                is_complete=True,
                completed_at=now,
            )
            session.add(review_section)
        else:
            review_section.is_complete = True
            review_section.completed_at = now
            review_section.data = {**(review_section.data or {}), "acknowledged": list(ack)}

        self._write_audit(
            session,
            application_id=application.id,
            ctx=ctx,
            event_type=POSAuditEvent.APPLICATION_SUBMITTED,
            delta={
                "appointment_id": appointment_id,
                "acknowledged": sorted(ack),
            },
        )
        session.flush()

        # Emit event for canonical-store handler to consume.
        # The handler in YOUR existing codebase is responsible for mapping
        # the POS payload onto BorrowerApplication.
        await event_bus.publish(
            Event(
                type=EventType.POS_APPLICATION_SUBMITTED,
                data={
                    "application_id": str(application.id),
                    "loan_id": application.loan_id,
                    "contact_id": application.contact_id,
                    "appointment_id": appointment_id,
                    "submitted_at": now.isoformat(),
                    "payload": _serialize_for_promotion(application),
                },
                org_id=str(application.organization_id),
            )
        )
        logger.info(
            "POS application %s submitted by contact %s",
            application.id,
            application.contact_id,
        )
        return application

    # ----- audit helper ------------------------------------------------------

    def _write_audit(
        self,
        session: Session,
        *,
        application_id: UUID,
        ctx: AuditContext,
        event_type: str,
        section_key: str | None = None,
        delta: dict[str, Any] | None = None,
    ) -> None:
        row = POSApplicationAudit(
            application_id=application_id,
            actor_type=ctx.actor_type,
            actor_id=ctx.actor_id,
            event_type=event_type,
            section_key=section_key,
            delta=delta,
            ip_address=ctx.ip_address,
            user_agent=(ctx.user_agent[:1000] if ctx.user_agent else None),
        )
        session.add(row)
        # Flush lets us see the audit row in tests; the route does the commit.
        session.flush()

    # ----- step ordering -----------------------------------------------------

    @staticmethod
    def _next_step(current: str) -> str:
        """Return the next step key, or stay on the last step."""
        try:
            idx = POSSectionKey.ORDERED.index(current)
        except ValueError:
            return POSSectionKey.PERSONAL
        next_idx = min(idx + 1, len(POSSectionKey.ORDERED) - 1)
        return POSSectionKey.ORDERED[next_idx]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_for_promotion(application: POSApplication) -> dict[str, Any]:
    """Produce the payload published on POS_APPLICATION_SUBMITTED.

    The canonical-store handler consumes this. Keep the schema additive — never
    rename or remove keys without bumping the major version of this skill,
    because downstream subscribers are coupled to it.
    """
    sections_payload = {
        s.section_key: {
            "data": s.data or {},
            "is_complete": s.is_complete,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in application.sections
    }

    pii_payload: dict[str, Any] = {}
    if application.pii is not None:
        # We pass plaintext PII to the canonical store — it will re-encrypt at
        # rest using its own EncryptedString columns. The event bus is in-process
        # and never crosses a network boundary in Perennia's deployment.
        pii_payload = {
            "ssn": application.pii.ssn_encrypted,  # decrypted by EncryptedString on read
            "co_ssn": application.pii.co_ssn_encrypted,
            "dob": application.pii.dob_date.isoformat() if application.pii.dob_date else None,
            "co_dob": application.pii.co_dob_date.isoformat() if application.pii.co_dob_date else None,
        }

    return {
        "version": "pos_1003_v1",
        "sections": sections_payload,
        "pii": pii_payload,
        "loan_id": application.loan_id,
        "contact_id": application.contact_id,
        "organization_id": application.organization_id,
        "workspace_id": application.workspace_id,
        "source_channel": application.source_channel,
    }


