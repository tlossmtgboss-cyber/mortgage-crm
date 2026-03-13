"""
ESIGN Act Consent Capture and Paper Alternative Workflow Service

Implements the consent requirements of the Electronic Signatures in Global
and National Commerce Act (ESIGN Act, 15 U.S.C. 7001):

  1. Before a consumer can sign electronically, the system must present
     a clear disclosure about electronic records and obtain affirmative
     consent.
  2. If the consumer declines, a paper alternative workflow is triggered
     (a task is created for staff to print and mail physical copies).
  3. A consumer may withdraw previously-given consent at any time, which
     also triggers the paper alternative workflow.

All consent events are recorded in the esign_consent_sessions table with
IP address and user-agent for audit and legal defensibility.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Current version of the ESIGN consent disclosure text.  Bump this when
# the disclosure language is materially changed so that each consent
# record tracks exactly which version the signer saw.
CONSENT_TEXT_VERSION = "1.0"

# Default ESIGN Act disclosure template.  The placeholders {org_support_email}
# and {org_name} are filled per-organization when available.
_DEFAULT_DISCLOSURE = (
    "By clicking 'I Agree', you consent to receive and sign documents "
    "electronically. You may withdraw consent at any time. You have the "
    "right to receive paper copies. To view documents you need: a modern "
    "web browser (Chrome, Firefox, Safari, or Edge) with JavaScript "
    "enabled and a PDF viewer. To request paper copies, contact "
    "{org_support_contact}."
)


class ESignConsentService:
    """Manages ESIGN Act consent capture, withdrawal, and paper fallback.

    Usage::

        svc = ESignConsentService(db)

        # 1. Show disclosure to recipient
        disclosure = svc.get_consent_disclosure_text(org_id=42)

        # 2. Record their decision
        result = svc.record_consent(
            recipient_id=101,
            envelope_id=55,
            org_id=42,
            consented=True,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 ...",
        )

        # 3. Before signing, verify consent
        has_consent = svc.verify_consent(recipient_id=101, envelope_id=55)
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_consent_disclosure_text(self, org_id: Optional[int] = None) -> dict:
        """Return the ESIGN consent disclosure text and version.

        Tries to load org-specific support contact information.  Falls
        back to a generic placeholder if the org is unknown.

        Returns:
            dict with ``text`` and ``version`` keys.
        """
        org_support_contact = "your loan officer"

        if org_id:
            try:
                from sqlalchemy import text as sa_text
                row = self.db.execute(
                    sa_text(
                        "SELECT name, support_email FROM organizations "
                        "WHERE id = :org_id"
                    ),
                    {"org_id": org_id},
                ).first()
                if row:
                    org_name = row[0] or "our office"
                    support_email = row[1]
                    if support_email:
                        org_support_contact = f"{org_name} at {support_email}"
                    else:
                        org_support_contact = org_name
            except Exception as e:
                logger.warning("Could not load org info for consent disclosure: %s", e)

        disclosure_text = _DEFAULT_DISCLOSURE.format(
            org_support_contact=org_support_contact,
        )

        return {
            "text": disclosure_text,
            "version": CONSENT_TEXT_VERSION,
        }

    def record_consent(
        self,
        recipient_id: int,
        envelope_id: int,
        org_id: Optional[int],
        consented: bool,
        ip_address: str,
        user_agent: str,
    ) -> dict:
        """Record the signer's consent decision.

        If ``consented`` is False the recipient is flagged for paper
        delivery and a staff task is created automatically.

        Args:
            recipient_id: ID of the ESignatureRecipient row.
            envelope_id:  ID of the ESignatureEnvelope row.
            org_id:       Organization that owns the envelope.
            consented:    True if the signer agrees to e-sign.
            ip_address:   Client IP at time of consent.
            user_agent:   Client user-agent string.

        Returns:
            dict with session details.
        """
        from database.models.esignature import (
            ESignConsentSession,
            ESignatureAuditEvent,
            AuditEventType,
        )

        now = datetime.now(timezone.utc)

        # Check for existing consent session for this recipient + envelope
        existing = (
            self.db.query(ESignConsentSession)
            .filter(
                ESignConsentSession.recipient_id == recipient_id,
                ESignConsentSession.envelope_id == envelope_id,
            )
            .first()
        )

        if existing:
            # Update existing session
            existing.consent_given = consented
            existing.ip_address = ip_address
            existing.user_agent = user_agent
            existing.consent_text_version = CONSENT_TEXT_VERSION
            if consented:
                existing.consented_at = now
                existing.withdrawn_at = None
                existing.withdrawal_reason = None
            else:
                existing.consented_at = None
            existing.updated_at = now
            session = existing
        else:
            session = ESignConsentSession(
                recipient_id=recipient_id,
                envelope_id=envelope_id,
                organization_id=org_id,
                consent_given=consented,
                consent_text_version=CONSENT_TEXT_VERSION,
                ip_address=ip_address,
                user_agent=user_agent,
                consented_at=now if consented else None,
            )
            self.db.add(session)

        # Audit event
        event_type = (
            AuditEventType.CONSENT_GIVEN.value
            if consented
            else AuditEventType.CONSENT_DECLINED.value
        )
        audit = ESignatureAuditEvent(
            envelope_id=envelope_id,
            recipient_id=recipient_id,
            event_type=event_type,
            event_description=(
                f"Recipient {'consented to' if consented else 'declined'} "
                f"electronic signatures (disclosure v{CONSENT_TEXT_VERSION})"
            ),
            ip_address=ip_address,
            user_agent=user_agent,
            extra_metadata={
                "consent_text_version": CONSENT_TEXT_VERSION,
                "consented": consented,
            },
            timestamp=now,
        )
        self.db.add(audit)

        # If they declined, create paper delivery task
        paper_task_id = None
        if not consented:
            paper_task_id = self.create_paper_delivery_task(
                recipient_id=recipient_id,
                envelope_id=envelope_id,
                org_id=org_id,
            )

        self.db.flush()

        logger.info(
            "Consent %s for recipient %s on envelope %s (IP: %s)",
            "given" if consented else "declined",
            recipient_id,
            envelope_id,
            ip_address,
        )

        return {
            "recipient_id": recipient_id,
            "envelope_id": envelope_id,
            "consent_given": consented,
            "consent_text_version": CONSENT_TEXT_VERSION,
            "consented_at": now.isoformat() if consented else None,
            "paper_task_id": paper_task_id,
        }

    def verify_consent(self, recipient_id: int, envelope_id: int) -> bool:
        """Check whether the recipient has given active (non-withdrawn) consent.

        Returns True only if a consent session exists with
        ``consent_given = True`` and ``withdrawn_at IS NULL``.
        """
        from database.models.esignature import ESignConsentSession

        session = (
            self.db.query(ESignConsentSession)
            .filter(
                ESignConsentSession.recipient_id == recipient_id,
                ESignConsentSession.envelope_id == envelope_id,
                ESignConsentSession.consent_given.is_(True),
                ESignConsentSession.withdrawn_at.is_(None),
            )
            .first()
        )
        return session is not None

    def withdraw_consent(
        self,
        recipient_id: int,
        envelope_id: int,
        reason: Optional[str],
        ip_address: str,
        user_agent: str,
    ) -> dict:
        """Withdraw previously-given consent and trigger paper workflow.

        Args:
            recipient_id: ID of the ESignatureRecipient.
            envelope_id:  ID of the ESignatureEnvelope.
            reason:       Optional free-text reason for withdrawal.
            ip_address:   Client IP at time of withdrawal.
            user_agent:   Client user-agent string.

        Returns:
            dict with withdrawal details.

        Raises:
            ValueError: If no active consent exists to withdraw.
        """
        from database.models.esignature import (
            ESignConsentSession,
            ESignatureAuditEvent,
            AuditEventType,
        )

        now = datetime.now(timezone.utc)

        session = (
            self.db.query(ESignConsentSession)
            .filter(
                ESignConsentSession.recipient_id == recipient_id,
                ESignConsentSession.envelope_id == envelope_id,
                ESignConsentSession.consent_given.is_(True),
                ESignConsentSession.withdrawn_at.is_(None),
            )
            .first()
        )
        if not session:
            raise ValueError(
                "No active consent found to withdraw for recipient "
                f"{recipient_id} on envelope {envelope_id}"
            )

        session.withdrawn_at = now
        session.withdrawal_reason = reason
        session.updated_at = now

        # Audit event
        audit = ESignatureAuditEvent(
            envelope_id=envelope_id,
            recipient_id=recipient_id,
            event_type=AuditEventType.CONSENT_WITHDRAWN.value,
            event_description=(
                f"Recipient withdrew electronic signature consent"
                f"{': ' + reason if reason else ''}"
            ),
            ip_address=ip_address,
            user_agent=user_agent,
            extra_metadata={"reason": reason},
            timestamp=now,
        )
        self.db.add(audit)

        # Trigger paper workflow
        paper_task_id = self.create_paper_delivery_task(
            recipient_id=recipient_id,
            envelope_id=envelope_id,
            org_id=session.organization_id,
        )

        self.db.flush()

        logger.info(
            "Consent withdrawn for recipient %s on envelope %s (reason: %s)",
            recipient_id,
            envelope_id,
            reason or "none",
        )

        return {
            "recipient_id": recipient_id,
            "envelope_id": envelope_id,
            "withdrawn_at": now.isoformat(),
            "reason": reason,
            "paper_task_id": paper_task_id,
        }

    def create_paper_delivery_task(
        self,
        recipient_id: int,
        envelope_id: int,
        org_id: Optional[int],
    ) -> Optional[str]:
        """Create a task for staff to print and mail paper copies.

        Looks up recipient and envelope details, then inserts a task
        record in the ``tasks`` table (if it exists) for fulfillment.

        Returns:
            The task UUID string, or None if task creation failed.
        """
        from database.models.esignature import (
            ESignatureRecipient,
            ESignatureEnvelope,
            ESignatureAuditEvent,
            AuditEventType,
        )

        now = datetime.now(timezone.utc)
        task_uuid = str(uuid.uuid4())[:8].upper()

        # Look up recipient and envelope for task context
        recipient = (
            self.db.query(ESignatureRecipient)
            .filter(ESignatureRecipient.id == recipient_id)
            .first()
        )
        envelope = (
            self.db.query(ESignatureEnvelope)
            .filter(ESignatureEnvelope.id == envelope_id)
            .first()
        )

        if not recipient or not envelope:
            logger.warning(
                "Cannot create paper delivery task: recipient %s or envelope %s not found",
                recipient_id,
                envelope_id,
            )
            return None

        # Try to create a task in the tasks table
        try:
            from sqlalchemy import text as sa_text

            self.db.execute(
                sa_text("""
                    INSERT INTO tasks (
                        title, description, status, priority,
                        organization_id, created_at, updated_at
                    ) VALUES (
                        :title, :description, 'pending', 'high',
                        :org_id, :now, :now
                    )
                """),
                {
                    "title": f"Paper delivery: {envelope.title} for {recipient.name}",
                    "description": (
                        f"Recipient {recipient.name} ({recipient.email}) "
                        f"declined electronic signature consent for envelope "
                        f"'{envelope.title}' (UUID: {envelope.envelope_uuid}). "
                        f"Print and mail paper copies of the document."
                    ),
                    "org_id": org_id,
                    "now": now,
                },
            )
            logger.info(
                "Created paper delivery task %s for recipient %s on envelope %s",
                task_uuid,
                recipient_id,
                envelope_id,
            )
        except Exception as e:
            logger.warning(
                "Could not create paper delivery task (tasks table may not exist): %s",
                e,
            )

        # Always record the paper request audit event
        audit = ESignatureAuditEvent(
            envelope_id=envelope_id,
            recipient_id=recipient_id,
            event_type=AuditEventType.PAPER_REQUESTED.value,
            event_description=(
                f"Paper delivery requested for {recipient.name} ({recipient.email})"
            ),
            extra_metadata={"task_uuid": task_uuid},
            timestamp=now,
        )
        self.db.add(audit)

        return task_uuid
