"""
eClosing Platform Integration Service

Abstraction layer for eClosing providers (Snapdocs, Pavaso, NotaryCam) that
handle the regulated closing ceremony for mortgage loans.  This fills the
strategic gap where the platform's built-in e-signature system cannot handle
closings that require:

  - MISMO-compliant eNotes registered with MERS
  - RON (Remote Online Notarization) or IPEN sessions
  - Wet-ink signature requirements on certain documents
  - eVault storage for negotiable instruments
  - County recording integration

The service uses mock API responses today and is designed as an integration
stub for future completion when a provider contract is signed.

Architecture:
    EClosingService
      |-- create_closing()        -> creates session with provider
      |-- upload_closing_documents() -> uploads closing package
      |-- generate_closing_package() -> identifies required docs by loan/state
      |-- schedule_notary()       -> schedules RON/IPEN/traditional notary
      |-- get_closing_status()    -> polls provider for document status
      |-- get_enote_status()      -> checks MERS/eVault status
      |-- complete_closing()      -> finalizes closing, triggers post-close
      |-- webhook_handler()       -> receives provider status updates

Usage:
    from services.smart_docs.integrations.eclosing_service import EClosingService

    service = EClosingService(db)
    session = service.create_closing(loan_id=123, org_id=1, ...)
"""

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timezone, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ClosingDocument:
    """A single document in the closing package."""
    doc_type: str
    filename: str
    file_bytes: Optional[bytes] = None
    requires_notarization: bool = False
    requires_wet_ink: bool = False
    signing_order: int = 1
    mismo_compliant: bool = False


@dataclass
class ClosingSession:
    """Result of creating a closing session with a provider."""
    session_id: str
    loan_id: int
    provider: str
    closing_type: str
    status: str
    signing_url: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class ClosingStatus:
    """Current status of a closing session."""
    status: str
    documents_signed: int = 0
    documents_pending: int = 0
    documents_total: int = 0
    notary_status: Optional[str] = None
    enote_status: Optional[Dict] = None
    signing_url: Optional[str] = None


# =============================================================================
# STATE-SPECIFIC CLOSING REQUIREMENTS
# =============================================================================

# States that allow Remote Online Notarization (RON)
RON_ENABLED_STATES = {
    "AK", "AZ", "AR", "CO", "CT", "FL", "HI", "ID", "IN", "IA",
    "KS", "KY", "LA", "MD", "MI", "MN", "MO", "MT", "NE", "NV",
    "NJ", "NM", "ND", "OH", "OK", "OR", "PA", "SD", "TN", "TX",
    "UT", "VA", "WA", "WV", "WI", "WY",
}

# Documents that typically require wet-ink signatures (state-dependent)
WET_INK_REQUIRED_DOC_TYPES = {
    "promissory_note",      # Unless state allows eNote
    "deed_of_trust",        # Some states require wet-ink
    "security_instrument",  # Varies by state
}

# MISMO document type codes for closing documents
MISMO_DOC_TYPES = {
    "promissory_note": "024",
    "deed_of_trust": "033",
    "security_instrument": "033",
    "closing_disclosure": "248",
    "initial_escrow_disclosure": "069",
    "right_to_cancel": "128",
    "compliance_agreement": "277",
    "name_affidavit": "178",
    "tax_authorization": "189",
    "hazard_insurance_disclosure": "190",
    "occupancy_affidavit": "037",
}

# Required closing documents by loan type
CLOSING_DOCS_BY_LOAN_TYPE = {
    "conventional": [
        "promissory_note", "deed_of_trust", "closing_disclosure",
        "initial_escrow_disclosure", "compliance_agreement",
        "name_affidavit", "tax_authorization", "occupancy_affidavit",
    ],
    "fha": [
        "promissory_note", "deed_of_trust", "closing_disclosure",
        "initial_escrow_disclosure", "compliance_agreement",
        "name_affidavit", "tax_authorization", "occupancy_affidavit",
        "hazard_insurance_disclosure",
    ],
    "va": [
        "promissory_note", "deed_of_trust", "closing_disclosure",
        "initial_escrow_disclosure", "compliance_agreement",
        "name_affidavit", "tax_authorization", "occupancy_affidavit",
    ],
    "usda": [
        "promissory_note", "deed_of_trust", "closing_disclosure",
        "initial_escrow_disclosure", "compliance_agreement",
        "name_affidavit", "tax_authorization", "occupancy_affidavit",
    ],
}

# States that require right-to-cancel (refinance only)
RIGHT_TO_CANCEL_STATES = {
    "CA", "TX", "NY", "FL", "IL", "PA", "OH", "MI", "NJ", "GA",
}


# =============================================================================
# ECLOSING SERVICE
# =============================================================================

class EClosingService:
    """Abstraction layer for eClosing provider integration.

    Currently uses mock responses. Replace _mock_* methods with real
    API calls when a provider contract is signed.

    Environment variables:
        ECLOSING_PROVIDER: snapdocs | pavaso | notarycam | internal
        ECLOSING_API_URL: Provider API base URL
        ECLOSING_API_KEY: Provider API key
    """

    def __init__(self, db: Session):
        self.db = db
        self.provider = os.getenv("ECLOSING_PROVIDER", "internal")
        self.api_url = os.getenv("ECLOSING_API_URL", "")
        self.api_key = os.getenv("ECLOSING_API_KEY", "")

    # -------------------------------------------------------------------------
    # CREATE CLOSING
    # -------------------------------------------------------------------------

    def create_closing(
        self,
        loan_id: int,
        org_id: int,
        closing_date: date,
        closing_type: str = "hybrid",
    ) -> ClosingSession:
        """Create a closing session with the eClosing provider.

        Args:
            loan_id: Internal loan ID.
            org_id: Organization ID for tenant isolation.
            closing_date: Scheduled closing date.
            closing_type: "full_eclosing", "hybrid", or "ink".

        Returns:
            ClosingSession with provider session ID and signing URL.
        """
        from database.models.eclosing import EClosingSession as EClosingSessionModel

        # Validate loan exists and belongs to org
        loan = self._get_loan(loan_id, org_id)
        if not loan:
            raise ValueError(f"Loan {loan_id} not found for organization {org_id}")

        # Create session with provider (mock)
        provider_response = self._mock_create_session(
            loan_number=loan["loan_number"],
            borrower_name=loan["borrower_name"],
            closing_date=closing_date,
            closing_type=closing_type,
        )

        # Persist to database
        db_session = EClosingSessionModel(
            organization_id=org_id,
            loan_id=loan_id,
            provider=self.provider,
            session_id=provider_response["session_id"],
            closing_type=closing_type,
            closing_date=closing_date,
            status="created",
            signing_url=provider_response.get("signing_url"),
            documents_package=[],
            enote_status={
                "mers_registered": False,
                "evault_stored": False,
                "evault_id": None,
                "tamper_seal_valid": True,
            },
        )

        self.db.add(db_session)
        self.db.flush()

        logger.info(
            "eClosing session created: session_id=%s, loan_id=%d, provider=%s",
            provider_response["session_id"], loan_id, self.provider,
        )

        return ClosingSession(
            session_id=provider_response["session_id"],
            loan_id=loan_id,
            provider=self.provider,
            closing_type=closing_type,
            status="created",
            signing_url=provider_response.get("signing_url"),
            created_at=datetime.now(timezone.utc),
        )

    # -------------------------------------------------------------------------
    # UPLOAD CLOSING DOCUMENTS
    # -------------------------------------------------------------------------

    def upload_closing_documents(
        self,
        session_id: str,
        documents: List[ClosingDocument],
        org_id: int,
    ) -> Dict:
        """Upload closing package to the eClosing provider.

        Each document is tagged with signing requirements (wet-ink, notarization,
        MISMO compliance).

        Args:
            session_id: Provider session ID.
            documents: List of ClosingDocument objects.
            org_id: Organization ID for tenant isolation.

        Returns:
            Upload result with document statuses.
        """
        db_session = self._get_db_session(session_id, org_id)
        if not db_session:
            raise ValueError(f"eClosing session {session_id} not found")

        # Build package manifest
        package = []
        for doc in documents:
            mismo_code = MISMO_DOC_TYPES.get(doc.doc_type)
            package.append({
                "doc_type": doc.doc_type,
                "filename": doc.filename,
                "requires_notarization": doc.requires_notarization,
                "requires_wet_ink": doc.requires_wet_ink,
                "signing_order": doc.signing_order,
                "mismo_code": mismo_code,
                "mismo_compliant": doc.mismo_compliant,
                "status": "uploaded",
                "signed_at": None,
            })

        # Mock upload to provider
        upload_result = self._mock_upload_documents(session_id, package)

        # Update database
        db_session.documents_package = package
        db_session.status = "documents_uploaded"
        self.db.flush()

        logger.info(
            "Closing documents uploaded: session_id=%s, doc_count=%d",
            session_id, len(documents),
        )

        return {
            "session_id": session_id,
            "documents_uploaded": len(documents),
            "status": "documents_uploaded",
            "package": package,
            "provider_reference": upload_result.get("reference_id"),
        }

    # -------------------------------------------------------------------------
    # GET CLOSING STATUS
    # -------------------------------------------------------------------------

    def get_closing_status(self, session_id: str, org_id: int) -> ClosingStatus:
        """Get current status of all documents in the closing package.

        Args:
            session_id: Provider session ID.
            org_id: Organization ID for tenant isolation.

        Returns:
            ClosingStatus with document-level detail.
        """
        db_session = self._get_db_session(session_id, org_id)
        if not db_session:
            raise ValueError(f"eClosing session {session_id} not found")

        package = db_session.documents_package or []
        signed = sum(1 for d in package if d.get("status") == "signed")
        pending = sum(1 for d in package if d.get("status") != "signed")

        notary_status = None
        if db_session.notary_type:
            if db_session.completed_at:
                notary_status = "completed"
            elif db_session.notary_scheduled_at:
                notary_status = "scheduled"
            else:
                notary_status = "pending"

        return ClosingStatus(
            status=db_session.status,
            documents_signed=signed,
            documents_pending=pending,
            documents_total=len(package),
            notary_status=notary_status,
            enote_status=db_session.enote_status,
            signing_url=db_session.signing_url,
        )

    # -------------------------------------------------------------------------
    # GENERATE CLOSING PACKAGE
    # -------------------------------------------------------------------------

    def generate_closing_package(
        self,
        loan_id: int,
        org_id: int,
    ) -> List[ClosingDocument]:
        """Identify required closing documents based on loan type and state.

        Determines which documents require wet-ink, notarization, or can be
        fully electronic based on:
          - Loan type (conventional, FHA, VA, USDA)
          - Property state (RON eligibility, specific requirements)
          - Lender overlays

        Args:
            loan_id: Internal loan ID.
            org_id: Organization ID.

        Returns:
            List of ClosingDocument with signing requirements populated.
        """
        loan = self._get_loan(loan_id, org_id)
        if not loan:
            raise ValueError(f"Loan {loan_id} not found for organization {org_id}")

        loan_type = (loan.get("loan_type") or "conventional").lower()
        property_state = (loan.get("property_state") or "").upper()
        loan_purpose = (loan.get("loan_purpose") or "purchase").lower()

        # Get base document list for loan type
        doc_types = CLOSING_DOCS_BY_LOAN_TYPE.get(
            loan_type,
            CLOSING_DOCS_BY_LOAN_TYPE["conventional"],
        ).copy()

        # Add right-to-cancel for refinances in applicable states
        if "refi" in loan_purpose and property_state in RIGHT_TO_CANCEL_STATES:
            if "right_to_cancel" not in doc_types:
                doc_types.append("right_to_cancel")

        # Check RON eligibility for the property state
        ron_eligible = property_state in RON_ENABLED_STATES

        # Build closing documents with signing requirements
        documents = []
        for i, doc_type in enumerate(doc_types, start=1):
            requires_wet_ink = doc_type in WET_INK_REQUIRED_DOC_TYPES
            requires_notarization = doc_type in ("deed_of_trust", "security_instrument")

            # If state allows RON and closing type is full_eclosing,
            # some wet-ink requirements can be waived for eNotes
            if ron_eligible and doc_type == "promissory_note":
                requires_wet_ink = False  # Can use eNote instead

            documents.append(ClosingDocument(
                doc_type=doc_type,
                filename=f"{doc_type}.pdf",
                requires_notarization=requires_notarization,
                requires_wet_ink=requires_wet_ink,
                signing_order=i,
                mismo_compliant=doc_type in MISMO_DOC_TYPES,
            ))

        logger.info(
            "Generated closing package: loan_id=%d, doc_count=%d, state=%s",
            loan_id, len(documents), property_state,
        )

        return documents

    # -------------------------------------------------------------------------
    # SCHEDULE NOTARY
    # -------------------------------------------------------------------------

    def schedule_notary(
        self,
        session_id: str,
        notary_type: str,
        preferred_date: datetime,
        org_id: int,
    ) -> Dict:
        """Schedule a notary for the closing session.

        Args:
            session_id: Provider session ID.
            notary_type: "RON", "IPEN", or "traditional".
            preferred_date: Preferred date/time for notary appointment.
            org_id: Organization ID for tenant isolation.

        Returns:
            Available notary slots and scheduling confirmation.
        """
        db_session = self._get_db_session(session_id, org_id)
        if not db_session:
            raise ValueError(f"eClosing session {session_id} not found")

        # Mock notary scheduling
        mock_slots = self._mock_schedule_notary(
            notary_type=notary_type,
            preferred_date=preferred_date,
        )

        # Update session with notary info
        db_session.notary_type = notary_type.lower()
        db_session.notary_scheduled_at = mock_slots["confirmed_slot"]
        db_session.notary_name = mock_slots["notary_name"]
        db_session.notary_commission_id = mock_slots["commission_id"]

        # Mark ready if documents are uploaded
        if db_session.status == "documents_uploaded":
            db_session.status = "ready"

        self.db.flush()

        logger.info(
            "Notary scheduled: session_id=%s, type=%s, date=%s",
            session_id, notary_type, mock_slots["confirmed_slot"],
        )

        return {
            "session_id": session_id,
            "notary_type": notary_type,
            "confirmed_slot": mock_slots["confirmed_slot"].isoformat(),
            "notary_name": mock_slots["notary_name"],
            "commission_id": mock_slots["commission_id"],
            "available_slots": [
                s.isoformat() for s in mock_slots["available_slots"]
            ],
            "status": db_session.status,
        }

    # -------------------------------------------------------------------------
    # GET ENOTE STATUS
    # -------------------------------------------------------------------------

    def get_enote_status(self, session_id: str, org_id: int) -> Dict:
        """Get eNote status including MERS registration and eVault storage.

        Args:
            session_id: Provider session ID.
            org_id: Organization ID.

        Returns:
            eNote lifecycle details.
        """
        db_session = self._get_db_session(session_id, org_id)
        if not db_session:
            raise ValueError(f"eClosing session {session_id} not found")

        enote_status = db_session.enote_status or {}

        return {
            "session_id": session_id,
            "mers_min": db_session.enote_mers_min,
            "mers_registered": enote_status.get("mers_registered", False),
            "evault_stored": enote_status.get("evault_stored", False),
            "evault_id": enote_status.get("evault_id"),
            "tamper_seal_valid": enote_status.get("tamper_seal_valid", True),
            "closing_status": db_session.status,
        }

    # -------------------------------------------------------------------------
    # COMPLETE CLOSING
    # -------------------------------------------------------------------------

    def complete_closing(self, session_id: str, org_id: int) -> Dict:
        """Finalize the closing session and trigger post-closing workflows.

        Marks all documents as signed, registers eNote with MERS (mock),
        stores in eVault (mock), and triggers post-closing tasks.

        Args:
            session_id: Provider session ID.
            org_id: Organization ID.

        Returns:
            Completion result with signed document references.
        """
        db_session = self._get_db_session(session_id, org_id)
        if not db_session:
            raise ValueError(f"eClosing session {session_id} not found")

        if db_session.status == "completed":
            raise ValueError(f"eClosing session {session_id} is already completed")

        if db_session.status == "cancelled":
            raise ValueError(f"eClosing session {session_id} is cancelled")

        now = datetime.now(timezone.utc)

        # Mark all documents as signed
        package = db_session.documents_package or []
        for doc in package:
            doc["status"] = "signed"
            doc["signed_at"] = now.isoformat()

        # Generate mock MERS MIN and eVault ID
        mers_min = f"100{uuid.uuid4().hex[:15].upper()}"[:18]
        evault_id = f"EV-{uuid.uuid4().hex[:12].upper()}"

        # Update eNote status
        enote_status = {
            "mers_registered": True,
            "evault_stored": True,
            "evault_id": evault_id,
            "tamper_seal_valid": True,
        }

        # Mock recording info
        recording_number = f"REC-{uuid.uuid4().hex[:8].upper()}"

        # Update database
        db_session.status = "completed"
        db_session.completed_at = now
        db_session.documents_package = package
        db_session.enote_mers_min = mers_min
        db_session.enote_status = enote_status
        db_session.recording_number = recording_number
        db_session.recording_date = now.date()
        db_session.signed_documents_key = (
            f"closings/{db_session.organization_id}/{db_session.loan_id}"
            f"/{session_id}/signed_package.zip"
        )

        self.db.flush()

        logger.info(
            "eClosing completed: session_id=%s, loan_id=%d, mers_min=%s",
            session_id, db_session.loan_id, mers_min,
        )

        return {
            "session_id": session_id,
            "status": "completed",
            "completed_at": now.isoformat(),
            "documents_signed": len(package),
            "mers_min": mers_min,
            "evault_id": evault_id,
            "recording_number": recording_number,
            "recording_date": now.date().isoformat(),
            "signed_documents_key": db_session.signed_documents_key,
            "post_closing_tasks": [
                "Record deed with county",
                "Send final title policy",
                "Update loan status to FUNDED",
                "Archive closing package",
            ],
        }

    # -------------------------------------------------------------------------
    # WEBHOOK HANDLER
    # -------------------------------------------------------------------------

    def webhook_handler(self, webhook_data: Dict, org_id: Optional[int] = None) -> Dict:
        """Handle closing status updates from the eClosing provider.

        Supported webhook events:
          - closing.status_changed: Overall session status update
          - document.signed: Individual document signed
          - notary.completed: Notarization session completed
          - enote.registered: eNote registered with MERS

        Args:
            webhook_data: Webhook payload from provider.
            org_id: Organization ID (optional, extracted from payload if absent).

        Returns:
            Processing result.
        """
        event_type = webhook_data.get("event_type", "")
        session_id = webhook_data.get("session_id", "")

        if not session_id:
            logger.warning("Webhook received without session_id: %s", webhook_data)
            return {"status": "error", "message": "Missing session_id"}

        # Look up session (without org filter for webhooks -- provider doesn't know our org_id)
        from database.models.eclosing import EClosingSession as EClosingSessionModel
        db_session = self.db.query(EClosingSessionModel).filter(
            EClosingSessionModel.session_id == session_id,
        ).first()

        if not db_session:
            logger.warning("Webhook for unknown session: %s", session_id)
            return {"status": "error", "message": f"Unknown session {session_id}"}

        # Process by event type
        if event_type == "closing.status_changed":
            new_status = webhook_data.get("status", "")
            if new_status in ("created", "documents_uploaded", "ready", "in_progress", "completed", "cancelled"):
                db_session.status = new_status
                if new_status == "completed":
                    db_session.completed_at = datetime.now(timezone.utc)
                self.db.flush()

        elif event_type == "document.signed":
            doc_type = webhook_data.get("doc_type", "")
            package = db_session.documents_package or []
            for doc in package:
                if doc.get("doc_type") == doc_type:
                    doc["status"] = "signed"
                    doc["signed_at"] = datetime.now(timezone.utc).isoformat()
            db_session.documents_package = package
            self.db.flush()

        elif event_type == "notary.completed":
            db_session.notary_name = webhook_data.get("notary_name", db_session.notary_name)
            db_session.notary_commission_id = webhook_data.get("commission_id", db_session.notary_commission_id)
            self.db.flush()

        elif event_type == "enote.registered":
            mers_min = webhook_data.get("mers_min", "")
            db_session.enote_mers_min = mers_min
            enote_status = db_session.enote_status or {}
            enote_status["mers_registered"] = True
            db_session.enote_status = enote_status
            self.db.flush()

        else:
            logger.info("Unhandled webhook event type: %s", event_type)
            return {"status": "ignored", "event_type": event_type}

        logger.info(
            "Webhook processed: event=%s, session_id=%s",
            event_type, session_id,
        )

        return {"status": "processed", "event_type": event_type, "session_id": session_id}

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _get_loan(self, loan_id: int, org_id: int) -> Optional[Dict]:
        """Fetch loan details with tenant isolation."""
        from sqlalchemy import text
        result = self.db.execute(
            text("""
                SELECT id, loan_number, borrower_name, borrower_email,
                       loan_type, property_state, loan_purpose, amount,
                       stage, closing_date
                FROM loans
                WHERE id = :loan_id AND organization_id = :org_id
            """),
            {"loan_id": loan_id, "org_id": org_id},
        )
        row = result.fetchone()
        if not row:
            return None
        return dict(zip(result.keys(), row))

    def _get_db_session(self, session_id: str, org_id: int):
        """Fetch eClosing session with tenant isolation."""
        from database.models.eclosing import EClosingSession as EClosingSessionModel
        return self.db.query(EClosingSessionModel).filter(
            EClosingSessionModel.session_id == session_id,
            EClosingSessionModel.organization_id == org_id,
        ).first()

    # =========================================================================
    # MOCK PROVIDER RESPONSES
    # Replace these with real API calls when provider contract is signed.
    # =========================================================================

    def _mock_create_session(
        self,
        loan_number: str,
        borrower_name: str,
        closing_date: date,
        closing_type: str,
    ) -> Dict:
        """Mock: Create session with eClosing provider."""
        session_id = f"EC-{uuid.uuid4().hex[:12].upper()}"
        return {
            "session_id": session_id,
            "signing_url": f"https://{self.provider}.example.com/closing/{session_id}",
            "status": "created",
        }

    def _mock_upload_documents(self, session_id: str, package: List[Dict]) -> Dict:
        """Mock: Upload documents to eClosing provider."""
        return {
            "reference_id": f"UPL-{uuid.uuid4().hex[:8].upper()}",
            "status": "uploaded",
            "document_count": len(package),
        }

    def _mock_schedule_notary(
        self,
        notary_type: str,
        preferred_date: datetime,
    ) -> Dict:
        """Mock: Schedule notary with provider."""
        # Generate mock available slots around the preferred date
        base = preferred_date.replace(minute=0, second=0, microsecond=0)
        available_slots = [
            base,
            base + timedelta(hours=2),
            base + timedelta(hours=4),
            base + timedelta(days=1),
            base + timedelta(days=1, hours=2),
        ]

        return {
            "confirmed_slot": base,
            "available_slots": available_slots,
            "notary_name": "Jane Smith, Notary Public",
            "commission_id": f"NP-{uuid.uuid4().hex[:8].upper()}",
            "notary_type": notary_type,
        }
