"""
POS (Point-of-Sale) Service — Business logic for the Digital 1003 borrower application.

Extends the existing ApplicationService in services.pos.application_service
with document management, co-borrower invitations, and status aggregation.

The core URLA lifecycle (create, section upsert, submit) lives in
services.pos.application_service. This module adds the supporting workflows
that sit alongside that lifecycle:

  - Document upload & listing
  - Co-borrower invitation generation
  - Application status aggregation (sections + docs + co-borrower)
  - Demographics section handling

Usage:
    from services.pos_service import POSService
    service = POSService()
    status = service.get_application_status(db, application)
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from database.models.borrower import (
    ApplicationDocument,
    BorrowerApplication,
    CoborrowerInvitation,
)
from database.models.pos import (
    POSApplication,
    POSApplicationSection,
    POSAuditEvent,
    POSSectionKey,
    POSStatus,
    calculate_completion_pct,
)
from services.pos.application_service import (
    ApplicationService,
    ApplicationNotFoundError,
    ApplicationStateError,
    AuditContext,
)

logger = logging.getLogger(__name__)


# Valid URLA section keys — the 7 specified in the task plus existing ones.
URLA_SECTIONS = (
    "personal_info",
    "employment",
    "assets",
    "liabilities",
    "property",
    "declarations",
    "demographics",
)

# Maps task-style section names to the existing POSSectionKey values.
SECTION_KEY_MAP = {
    "personal_info": POSSectionKey.PERSONAL,
    "employment": POSSectionKey.EMPLOYMENT,
    "assets": POSSectionKey.ASSETS,
    "liabilities": POSSectionKey.LIABILITIES,
    "property": POSSectionKey.LOAN,
    "declarations": POSSectionKey.DECLARATIONS,
    "demographics": POSSectionKey.REVIEW,  # demographics stored as part of review data
}

# Supported document categories.
DOCUMENT_CATEGORIES = {
    "income": "Income",
    "assets": "Assets",
    "identity": "Identity",
    "property": "Property",
    "credit": "Credit",
    "other": "Miscellaneous",
}


class POSService:
    """Extended POS service adding document, co-borrower, and status logic.

    Delegates core lifecycle operations to ApplicationService.
    """

    def __init__(self) -> None:
        self._app_service = ApplicationService()

    # -------------------------------------------------------------------------
    # Application status aggregation
    # -------------------------------------------------------------------------

    def get_application_status(
        self,
        session: Session,
        application: POSApplication,
    ) -> dict[str, Any]:
        """Build a comprehensive status response for the borrower.

        Returns a dict matching ApplicationStatusResponse schema with
        per-section breakdown, document count, and co-borrower status.
        """
        # Section details.
        sections = []
        for key in POSSectionKey.ORDERED:
            section = next(
                (s for s in application.sections if s.section_key == key),
                None,
            )
            sections.append({
                "section_key": key,
                "is_complete": section.is_complete if section else False,
                "completed_at": section.completed_at if section else None,
                "updated_at": section.updated_at if section else None,
            })

        # Document count — query the canonical ApplicationDocument table if
        # there's a linked BorrowerApplication, otherwise check POS-local docs.
        doc_count = 0
        if application.loan_id:
            doc_count = (
                session.query(func.count(ApplicationDocument.id))
                .join(
                    BorrowerApplication,
                    ApplicationDocument.application_id == BorrowerApplication.id,
                )
                .filter(BorrowerApplication.loan_id == application.loan_id)
                .scalar()
            ) or 0

        # Co-borrower status — check CoborrowerInvitation linked via loan.
        has_coborrower_invite = False
        coborrower_status = None
        if application.loan_id:
            invite = (
                session.query(CoborrowerInvitation)
                .join(
                    BorrowerApplication,
                    CoborrowerInvitation.application_id == BorrowerApplication.id,
                )
                .filter(BorrowerApplication.loan_id == application.loan_id)
                .order_by(CoborrowerInvitation.created_at.desc())
                .first()
            )
            if invite:
                has_coborrower_invite = True
                coborrower_status = invite.status

        return {
            "id": application.id,
            "status": application.status,
            "current_step": application.current_step,
            "completion_pct": application.completion_pct,
            "sections": sections,
            "submitted_at": application.submitted_at,
            "submitted_appointment_id": getattr(
                application, "submitted_appointment_id", None
            ),
            "document_count": doc_count,
            "has_coborrower_invite": has_coborrower_invite,
            "coborrower_status": coborrower_status,
            "created_at": application.created_at,
            "updated_at": application.updated_at,
        }

    # -------------------------------------------------------------------------
    # Document management
    # -------------------------------------------------------------------------

    def upload_document(
        self,
        session: Session,
        *,
        application: POSApplication,
        filename: str,
        original_filename: str,
        file_size: int,
        mime_type: str,
        category: str = "other",
        description: str | None = None,
        storage_key: str | None = None,
        ctx: AuditContext,
    ) -> ApplicationDocument:
        """Attach a document to the borrower application.

        Creates an ApplicationDocument row linked to the BorrowerApplication
        that corresponds to this POS draft. If no canonical BorrowerApplication
        exists yet, one is created with minimal data.
        """
        if application.status != POSStatus.DRAFT:
            raise ApplicationStateError(
                f"Cannot upload documents to a {application.status} application"
            )

        # Resolve or create a canonical BorrowerApplication for doc storage.
        borrower_app = self._resolve_borrower_application(session, application)

        # Normalize category.
        category_label = DOCUMENT_CATEGORIES.get(category, "Miscellaneous")

        doc = ApplicationDocument(
            application_id=borrower_app.id,
            filename=filename,
            original_filename=original_filename,
            file_size=file_size,
            mime_type=mime_type,
            category=category_label,
            description=description,
            storage_key=storage_key or f"org-{application.organization_id}/pos/{application.id}/{filename}",
            uploaded_by=f"borrower:{ctx.actor_id}" if ctx.actor_id else "borrower",
        )
        session.add(doc)
        session.flush()

        # Audit trail.
        self._app_service._write_audit(
            session,
            application_id=application.id,
            ctx=ctx,
            event_type="document.uploaded",
            delta={
                "document_id": doc.id,
                "filename": original_filename,
                "category": category_label,
                "file_size": file_size,
            },
        )

        logger.info(
            "Document %s uploaded for POS application %s",
            doc.id,
            application.id,
        )
        return doc

    def list_documents(
        self,
        session: Session,
        application: POSApplication,
    ) -> list[ApplicationDocument]:
        """List all documents attached to this application."""
        borrower_app = self._find_borrower_application(session, application)
        if borrower_app is None:
            return []

        return (
            session.query(ApplicationDocument)
            .filter(ApplicationDocument.application_id == borrower_app.id)
            .order_by(ApplicationDocument.created_at.desc())
            .all()
        )

    # -------------------------------------------------------------------------
    # Co-borrower invitation
    # -------------------------------------------------------------------------

    def invite_coborrower(
        self,
        session: Session,
        *,
        application: POSApplication,
        email: str,
        first_name: str,
        last_name: str,
        phone: str | None = None,
        relationship_type: str | None = None,
        ctx: AuditContext,
    ) -> CoborrowerInvitation:
        """Generate and send a co-borrower invitation.

        Creates a CoborrowerInvitation row with a unique token and returns it.
        The frontend uses the invitation_link to send the co-borrower an email
        or SMS with a link to complete their portion.
        """
        if application.status != POSStatus.DRAFT:
            raise ApplicationStateError(
                f"Cannot invite co-borrower on a {application.status} application"
            )

        # Resolve or create canonical BorrowerApplication.
        borrower_app = self._resolve_borrower_application(session, application)

        # Generate a secure invitation token.
        invitation_token = secrets.token_urlsafe(48)

        # Build expiration (7 days from now).
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        invitation = CoborrowerInvitation(
            application_id=borrower_app.id,
            invitation_token=invitation_token,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            relationship_type=relationship_type,
            status="pending",
            sent_at=datetime.now(timezone.utc),
            expires_at=expires_at,
        )
        session.add(invitation)
        session.flush()

        # Mark application as having a co-borrower.
        borrower_app.has_coborrower = True
        borrower_app.coborrower_email = email

        # Audit trail.
        self._app_service._write_audit(
            session,
            application_id=application.id,
            ctx=ctx,
            event_type="coborrower.invited",
            delta={
                "invitation_id": invitation.id,
                "relationship_type": relationship_type,
            },
        )

        logger.info(
            "Co-borrower invitation %s created for POS application %s",
            invitation.id,
            application.id,
        )
        return invitation

    # -------------------------------------------------------------------------
    # Section validation
    # -------------------------------------------------------------------------

    def validate_section(
        self,
        section_key: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate section data completeness.

        Returns a dict with:
          - is_valid: bool
          - missing_fields: list of field names that are empty/missing
          - warnings: list of advisory messages
        """
        result: dict[str, Any] = {
            "is_valid": True,
            "missing_fields": [],
            "warnings": [],
        }

        # Per-section required field checks.
        required_fields = _SECTION_REQUIRED_FIELDS.get(section_key, [])
        for field_name in required_fields:
            value = data.get(field_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                result["missing_fields"].append(field_name)

        if result["missing_fields"]:
            result["is_valid"] = False

        return result

    # -------------------------------------------------------------------------
    # Progress tracking
    # -------------------------------------------------------------------------

    def calculate_progress(
        self,
        application: POSApplication,
    ) -> dict[str, Any]:
        """Calculate overall progress and per-section completion."""
        sections_complete: dict[str, bool] = {}
        for key in POSSectionKey.ORDERED:
            section = next(
                (s for s in application.sections if s.section_key == key),
                None,
            )
            sections_complete[key] = section.is_complete if section else False

        completed_count = sum(1 for v in sections_complete.values() if v)
        total = len(POSSectionKey.ORDERED)

        return {
            "sections_complete": sections_complete,
            "completed_count": completed_count,
            "total_sections": total,
            "percentage": calculate_completion_pct(completed_count, total),
        }

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _resolve_borrower_application(
        self,
        session: Session,
        pos_app: POSApplication,
    ) -> BorrowerApplication:
        """Find or create the canonical BorrowerApplication for this POS draft.

        The POS tables hold draft state; the canonical BorrowerApplication is
        the durable record. We link them via loan_id.
        """
        existing = self._find_borrower_application(session, pos_app)
        if existing:
            return existing

        # Create a minimal canonical record.
        public_token = secrets.token_urlsafe(48)
        borrower_app = BorrowerApplication(
            public_token=public_token,
            loan_id=pos_app.loan_id,
            organization_id=pos_app.organization_id,
            status="DRAFT",
            progress_percentage=pos_app.completion_pct,
        )
        session.add(borrower_app)
        session.flush()

        logger.info(
            "Created canonical BorrowerApplication %s for POS %s",
            borrower_app.id,
            pos_app.id,
        )
        return borrower_app

    def _find_borrower_application(
        self,
        session: Session,
        pos_app: POSApplication,
    ) -> BorrowerApplication | None:
        """Find canonical BorrowerApplication linked to this POS draft."""
        if not pos_app.loan_id:
            return None
        return (
            session.query(BorrowerApplication)
            .filter(BorrowerApplication.loan_id == pos_app.loan_id)
            .order_by(BorrowerApplication.created_at.desc())
            .first()
        )


# ---------------------------------------------------------------------------
# Required fields per section (for validation)
# ---------------------------------------------------------------------------

_SECTION_REQUIRED_FIELDS: dict[str, list[str]] = {
    POSSectionKey.PERSONAL: [
        "first_name",
        "last_name",
        "email",
        "phone",
    ],
    POSSectionKey.RESIDENCE: [
        "current",
    ],
    POSSectionKey.EMPLOYMENT: [
        "employment_type",
    ],
    POSSectionKey.ASSETS: [
        "accounts",
    ],
    POSSectionKey.LIABILITIES: [
        "liabilities",
    ],
    POSSectionKey.REO: [
        "owns_other_property",
    ],
    POSSectionKey.LOAN: [
        "loan_purpose",
        "loan_type",
        "loan_amount",
    ],
    POSSectionKey.DECLARATIONS: [
        "will_occupy_as_primary",
        "us_citizen",
    ],
}
