"""
Smart Docs Provisioning Agent

Auto-provisions Smart Docs portals for new borrowers and team members.
Triggered on user_created or borrower_added events, this agent:
  - Creates a PURL access token via the existing PURLTokenService
  - Generates a document checklist based on loan_type + current stage
  - Sends the portal link via SMS and email
  - Logs every action to the audit trail
  - Returns the portal_url

Target: < 2 second provisioning time (all I/O is batched where possible).

Usage:
    from services.smart_docs_provisioning_agent import SmartDocsProvisioningAgent

    agent = SmartDocsProvisioningAgent()
    result = await agent.provision_borrower_portal(
        borrower_id=42, loan_id=17, org_id=1, db=db
    )
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORTAL_BASE_URL = os.getenv(
    "PORTAL_BASE_URL", "https://app.perenniaai.com/portal"
)
TELNYX_FROM_NUMBER = os.getenv("TELNYX_FROM_NUMBER", "")
TELNYX_MESSAGING_PROFILE = os.getenv(
    "TELNYX_MESSAGING_PROFILE_ID", ""
)

# Provisioning SLA — warn if exceeded
PROVISIONING_SLA_SECONDS = 2.0


class SmartDocsProvisioningAgent:
    """Auto-provisions Smart Docs portal for new borrowers and team members."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def provision_borrower_portal(
        self,
        borrower_id: int,
        loan_id: int,
        org_id: int,
        db: Session,
    ) -> dict:
        """
        Provision a full borrower portal in a single call.

        Steps:
          1. Load borrower + loan context
          2. Create PURL token (via PURLTokenService)
          3. Generate document checklist for loan_type + stage
          4. Send portal link via SMS + email (concurrently)
          5. Audit-log the provisioning event

        Returns:
            dict with keys: portal_url, token_id, checklist, notifications_sent
        """
        start = time.monotonic()
        result: Dict[str, Any] = {
            "portal_url": None,
            "token_id": None,
            "checklist": [],
            "notifications_sent": {"sms": False, "email": False},
            "provisioning_ms": 0,
        }

        try:
            # --- 1. Load context ---
            borrower, loan, user = self._load_borrower_context(
                borrower_id, loan_id, org_id, db
            )
            if borrower is None or loan is None:
                logger.error(
                    "Provisioning aborted: borrower=%s loan=%s not found",
                    borrower_id,
                    loan_id,
                )
                return result

            loan_type = getattr(loan, "loan_type", None) or "CONVENTIONAL"
            stage = (getattr(loan, "stage", None) or "APPLICATION").upper()

            # --- 2. Create PURL token ---
            token_id, portal_url = self._create_purl_token(
                org_id=org_id,
                loan_id=loan_id,
                borrower_id=borrower_id,
                db=db,
            )
            result["token_id"] = token_id
            result["portal_url"] = portal_url

            # --- 3. Generate checklist ---
            checklist = await self._generate_checklist(
                loan_id=loan_id,
                loan_type=loan_type,
                stage=stage,
                db=db,
            )
            result["checklist"] = checklist

            # --- 4. Send notifications concurrently ---
            recipient = self._build_recipient(borrower, loan, user)
            sms_ok, email_ok = await self._send_portal_link(
                recipient=recipient,
                portal_url=portal_url,
                db=db,
            )
            result["notifications_sent"]["sms"] = sms_ok
            result["notifications_sent"]["email"] = email_ok

            # --- 5. Audit log ---
            self._write_audit_log(
                org_id=org_id,
                entity_type="borrower_portal",
                entity_id=borrower_id,
                change_type="provisioned",
                after_state={
                    "portal_url": portal_url,
                    "token_id": token_id,
                    "checklist_count": len(checklist),
                    "loan_id": loan_id,
                    "loan_type": loan_type,
                    "stage": stage,
                },
                db=db,
            )

            db.commit()

        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "DB error provisioning portal for borrower=%s loan=%s",
                borrower_id,
                loan_id,
            )
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            db.rollback()
            logger.exception(
                "Unexpected error provisioning portal for borrower=%s loan=%s",
                borrower_id,
                loan_id,
            )

        elapsed_ms = (time.monotonic() - start) * 1000
        result["provisioning_ms"] = round(elapsed_ms, 1)
        if elapsed_ms / 1000 > PROVISIONING_SLA_SECONDS:
            logger.warning(
                "Provisioning SLA exceeded: %.0fms (target <%ss) for borrower=%s",
                elapsed_ms,
                PROVISIONING_SLA_SECONDS,
                borrower_id,
            )

        logger.info(
            "Borrower portal provisioned in %.0fms: borrower=%s loan=%s url=%s",
            elapsed_ms,
            borrower_id,
            loan_id,
            result.get("portal_url"),
        )
        return result

    async def provision_team_portal(
        self,
        user_id: int,
        org_id: int,
        db: Session,
    ) -> dict:
        """
        Provision a team-member portal (internal doc workspace).

        Lighter-weight than borrower provisioning — no checklist generation
        or SMS, just a PURL token + email link.

        Returns:
            dict with keys: portal_url, token_id, notifications_sent
        """
        start = time.monotonic()
        result: Dict[str, Any] = {
            "portal_url": None,
            "token_id": None,
            "notifications_sent": {"email": False},
            "provisioning_ms": 0,
        }

        try:
            from database.models.core import User

            user = db.query(User).filter(
                User.id == user_id,
                User.organization_id == org_id,
            ).first()

            if user is None:
                logger.error(
                    "Team provisioning aborted: user=%s org=%s not found",
                    user_id,
                    org_id,
                )
                return result

            # Create PURL token scoped to the team member
            token_id, portal_url = self._create_purl_token(
                org_id=org_id,
                loan_id=None,
                borrower_id=None,
                user_id=user_id,
                db=db,
            )
            result["token_id"] = token_id
            result["portal_url"] = portal_url

            # Email only — no SMS for internal team members
            email_ok = await self._send_email_notification(
                to_email=user.email,
                to_name=f"{user.first_name or ''} {user.last_name or ''}".strip()
                or "Team Member",
                portal_url=portal_url,
                subject="Your Perennia Smart Docs Portal is Ready",
            )
            result["notifications_sent"]["email"] = email_ok

            self._write_audit_log(
                org_id=org_id,
                entity_type="team_portal",
                entity_id=user_id,
                change_type="provisioned",
                after_state={
                    "portal_url": portal_url,
                    "token_id": token_id,
                },
                db=db,
            )

            db.commit()

        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "DB error provisioning team portal for user=%s org=%s",
                user_id,
                org_id,
            )
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            db.rollback()
            logger.exception(
                "Unexpected error provisioning team portal for user=%s org=%s",
                user_id,
                org_id,
            )

        elapsed_ms = (time.monotonic() - start) * 1000
        result["provisioning_ms"] = round(elapsed_ms, 1)
        logger.info(
            "Team portal provisioned in %.0fms: user=%s url=%s",
            elapsed_ms,
            user_id,
            result.get("portal_url"),
        )
        return result

    # ------------------------------------------------------------------
    # Checklist generation
    # ------------------------------------------------------------------

    async def _generate_checklist(
        self,
        loan_id: int,
        loan_type: str,
        stage: str,
        db: Session,
    ) -> list:
        """
        Generate a document checklist appropriate for the loan type and
        current pipeline stage.

        Delegates to StageChecklistService for the stage-aware requirements,
        then persists checklist items as DocumentRequest rows.

        Returns:
            list of dicts, each with doc_type, description, category, priority
        """
        from services.stage_checklist_service import StageChecklistService

        svc = StageChecklistService(db)
        requirements = svc.get_requirements_for_stage(
            stage=stage,
            loan_type=loan_type,
        )

        # Persist as document requests linked to the loan
        checklist_items: List[Dict[str, Any]] = []
        for req in requirements:
            item = svc.create_document_request(
                loan_id=loan_id,
                doc_type=req["doc_type"],
                description=req["description"],
                category=req["category"],
                priority=req["priority"],
            )
            checklist_items.append(item)

        logger.info(
            "Generated %d checklist items for loan=%s type=%s stage=%s",
            len(checklist_items),
            loan_id,
            loan_type,
            stage,
        )
        return checklist_items

    # ------------------------------------------------------------------
    # Notification delivery
    # ------------------------------------------------------------------

    async def _send_portal_link(
        self,
        recipient: dict,
        portal_url: str,
        db: Session,
    ) -> tuple:
        """
        Send portal link via SMS and email concurrently.

        Returns:
            tuple (sms_success: bool, email_success: bool)
        """
        phone = recipient.get("phone")
        email = recipient.get("email")
        name = recipient.get("name", "Borrower")

        sms_coro = self._send_sms_notification(
            to_phone=phone,
            portal_url=portal_url,
            name=name,
        ) if phone else self._noop_false()

        email_coro = self._send_email_notification(
            to_email=email,
            to_name=name,
            portal_url=portal_url,
            subject="Your Secure Document Portal is Ready",
        ) if email else self._noop_false()

        sms_ok, email_ok = await asyncio.gather(
            sms_coro, email_coro, return_exceptions=True
        )

        # Treat exceptions as False
        if isinstance(sms_ok, BaseException):
            logger.error("SMS notification failed: %s", sms_ok)
            sms_ok = False
        if isinstance(email_ok, BaseException):
            logger.error("Email notification failed: %s", email_ok)
            email_ok = False

        return bool(sms_ok), bool(email_ok)

    async def _send_sms_notification(
        self,
        to_phone: Optional[str],
        portal_url: str,
        name: str,
    ) -> bool:
        """Send SMS with portal link via Telnyx."""
        if not to_phone:
            return False

        try:
            from telephony.sms import send_sms as telnyx_send_sms

            message = (
                f"Hi {name}, your secure document portal is ready. "
                f"Upload your loan documents here: {portal_url}"
            )
            telnyx_send_sms(
                to=to_phone,
                from_=TELNYX_FROM_NUMBER,
                text=message,
                messaging_profile_id=TELNYX_MESSAGING_PROFILE,
            )
            logger.info("Portal SMS sent to %s", to_phone[-4:].rjust(len(to_phone), "*"))
            return True

        except Exception as e:
            logger.exception("Failed to send portal SMS to %s: %s", to_phone[-4:], e)
            return False

    async def _send_email_notification(
        self,
        to_email: Optional[str],
        to_name: str,
        portal_url: str,
        subject: str = "Your Secure Document Portal is Ready",
    ) -> bool:
        """Send email with portal link via EmailService (SendGrid / SMTP)."""
        if not to_email:
            return False

        try:
            from email_service import EmailService

            svc = EmailService()
            html_body = (
                f"<p>Hi {to_name},</p>"
                f"<p>Your secure document portal is ready. Click the link below "
                f"to view your checklist and upload documents:</p>"
                f'<p><a href="{portal_url}" style="'
                f"background-color:#2563eb;color:#fff;padding:12px 24px;"
                f"border-radius:6px;text-decoration:none;font-weight:bold;"
                f'">Open Your Portal</a></p>'
                f"<p>This link is unique to you. Do not share it.</p>"
                f"<p>Best,<br>Perennia AI</p>"
            )
            svc.send_email(
                to_emails=[to_email],
                subject=subject,
                html_content=html_body,
            )
            logger.info("Portal email sent to %s", to_email)
            return True

        except Exception as e:
            logger.exception("Failed to send portal email to %s: %s", to_email, e)
            return False

    # ------------------------------------------------------------------
    # PURL token creation
    # ------------------------------------------------------------------

    def _create_purl_token(
        self,
        org_id: int,
        db: Session,
        loan_id: Optional[int] = None,
        borrower_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> tuple:
        """
        Create a PURL access token and return (token_id, portal_url).

        Wraps PURLTokenService.create_token — if the PURL workspace does
        not yet exist for this loan/org, one is created first.
        """
        from services.purl_token_service import PURLTokenService
        from models.purl import PURLWorkspace, TokenScope

        token_svc = PURLTokenService(db)

        # Find or create workspace
        workspace = db.query(PURLWorkspace).filter(
            PURLWorkspace.organization_id == org_id,
        ).first()

        if workspace is None:
            workspace = PURLWorkspace(
                organization_id=org_id,
                name=f"Smart Docs Portal — Org {org_id}",
                status="active",
            )
            db.add(workspace)
            db.flush()

        token_id, full_token = token_svc.create_token(
            organization_id=org_id,
            workspace_id=workspace.id,
            scope=TokenScope.WRITE,
            contact_id=borrower_id,
            expires_in_days=90,
            created_by=user_id,
        )

        portal_url = f"{PORTAL_BASE_URL}?token={full_token}"
        return token_id, portal_url

    # ------------------------------------------------------------------
    # Context loading helpers
    # ------------------------------------------------------------------

    def _load_borrower_context(
        self,
        borrower_id: int,
        loan_id: int,
        org_id: int,
        db: Session,
    ) -> tuple:
        """
        Load borrower (Lead), loan, and assigned user records.

        Returns:
            (borrower, loan, user) — any may be None if not found.
        """
        from database.models.lead_loan import Lead, Loan
        from database.models.core import User

        borrower = db.query(Lead).filter(
            Lead.id == borrower_id,
            Lead.organization_id == org_id,
        ).first()

        loan = db.query(Loan).filter(
            Loan.id == loan_id,
            Loan.organization_id == org_id,
        ).first()

        user = None
        if loan and getattr(loan, "owner_id", None):
            user = db.query(User).filter(User.id == loan.owner_id).first()

        return borrower, loan, user

    def _build_recipient(self, borrower, loan, user) -> dict:
        """Build a recipient dict from borrower/loan/user context."""
        name_parts = []
        if getattr(borrower, "first_name", None):
            name_parts.append(borrower.first_name)
        if getattr(borrower, "last_name", None):
            name_parts.append(borrower.last_name)

        return {
            "name": " ".join(name_parts) or "Borrower",
            "email": getattr(borrower, "email", None),
            "phone": getattr(borrower, "phone", None),
        }

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------

    def _write_audit_log(
        self,
        org_id: int,
        entity_type: str,
        entity_id: int,
        change_type: str,
        after_state: dict,
        db: Session,
        before_state: Optional[dict] = None,
    ) -> None:
        """Write an immutable audit log entry for the provisioning event."""
        try:
            from database.models.security import AuditLog

            entry = AuditLog(
                organization_id=org_id,
                change_type=change_type,
                entity_type=entity_type,
                entity_id=entity_id,
                before_state=before_state,
                after_state=after_state,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(entry)
            db.flush()

        except Exception as e:
            # Audit logging must never block provisioning
            logger.error("Failed to write audit log: %s", e)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    async def _noop_false() -> bool:
        """Coroutine that returns False (used as placeholder)."""
        return False
