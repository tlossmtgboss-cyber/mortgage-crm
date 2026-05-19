"""
Stage-Aware Checklist Trigger Service

Maps each loan stage to required documents and automatically updates the
checklist when a loan stage changes.  Notifies the borrower of newly
required documents via SMS and email.

Stages covered:
  APPLICATION, PROCESSING, UNDERWRITING, CONDITIONAL_APPROVAL, CTC, CLOSING

Usage:
    from services.stage_checklist_service import StageChecklistService

    svc = StageChecklistService(db)
    svc.on_stage_change(loan_id=42, old_stage="APPLICATION", new_stage="PROCESSING")
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TELNYX_FROM_NUMBER = os.getenv("TELNYX_FROM_NUMBER", "")
TELNYX_MESSAGING_PROFILE = os.getenv(
    "TELNYX_MESSAGING_PROFILE_ID", ""
)
PORTAL_BASE_URL = os.getenv(
    "PORTAL_BASE_URL", "https://app.perenniaai.com/portal"
)

# ---------------------------------------------------------------------------
# Stage → Document Requirements
# ---------------------------------------------------------------------------

STAGE_DOCUMENT_REQUIREMENTS: Dict[str, List[Dict[str, Any]]] = {
    "APPLICATION": [
        {
            "doc_type": "government_id",
            "description": "Government-issued photo ID (driver's license or passport)",
            "category": "identity",
            "priority": "required",
        },
        {
            "doc_type": "pay_stubs_30day",
            "description": "Most recent 30 days of pay stubs",
            "category": "income",
            "priority": "required",
        },
        {
            "doc_type": "bank_statements_2month",
            "description": "Most recent 2 months of bank statements (all pages)",
            "category": "assets",
            "priority": "required",
        },
        {
            "doc_type": "tax_returns_2year",
            "description": "Federal tax returns for the past 2 years (all pages, all schedules)",
            "category": "income",
            "priority": "required",
        },
        {
            "doc_type": "w2_2year",
            "description": "W-2 forms for the past 2 years",
            "category": "income",
            "priority": "required",
        },
    ],
    "PROCESSING": [
        {
            "doc_type": "purchase_contract",
            "description": "Fully executed purchase contract",
            "category": "property",
            "priority": "required",
        },
        {
            "doc_type": "earnest_money_receipt",
            "description": "Earnest money deposit receipt",
            "category": "assets",
            "priority": "required",
        },
        {
            "doc_type": "homeowners_insurance_quote",
            "description": "Homeowners insurance quote or binder",
            "category": "property",
            "priority": "required",
        },
    ],
    "UNDERWRITING": [
        {
            "doc_type": "employment_verification",
            "description": "Verbal or written verification of employment (VOE)",
            "category": "income",
            "priority": "required",
        },
        {
            "doc_type": "asset_verification",
            "description": "Updated asset verification (VOD or recent statements)",
            "category": "assets",
            "priority": "required",
        },
    ],
    "CONDITIONAL_APPROVAL": [
        # Dynamic — populated based on underwriting conditions at runtime
    ],
    "CTC": [
        {
            "doc_type": "final_closing_disclosure",
            "description": "Final closing disclosure (CD) signed by borrower",
            "category": "compliance",
            "priority": "required",
        },
        {
            "doc_type": "wire_instructions",
            "description": "Wire transfer instructions from title company",
            "category": "compliance",
            "priority": "required",
        },
    ],
    "CLOSING": [
        {
            "doc_type": "signed_closing_docs",
            "description": "Signed closing documents package",
            "category": "compliance",
            "priority": "required",
        },
    ],
}

# Loan-type-specific additional requirements
_LOAN_TYPE_EXTRAS: Dict[str, List[Dict[str, Any]]] = {
    "FHA": [
        {
            "doc_type": "fha_case_number_assignment",
            "description": "FHA case number assignment",
            "category": "compliance",
            "priority": "required",
            "stages": ["APPLICATION"],
        },
    ],
    "VA": [
        {
            "doc_type": "va_certificate_of_eligibility",
            "description": "VA Certificate of Eligibility (COE)",
            "category": "compliance",
            "priority": "required",
            "stages": ["APPLICATION"],
        },
        {
            "doc_type": "dd214",
            "description": "DD-214 or Statement of Service",
            "category": "compliance",
            "priority": "required",
            "stages": ["APPLICATION"],
        },
    ],
    "USDA": [
        {
            "doc_type": "usda_eligibility_determination",
            "description": "USDA property and income eligibility determination",
            "category": "compliance",
            "priority": "required",
            "stages": ["APPLICATION"],
        },
    ],
    "SELF_EMPLOYED": [
        {
            "doc_type": "profit_loss_statement",
            "description": "Year-to-date profit & loss statement",
            "category": "income",
            "priority": "required",
            "stages": ["APPLICATION", "UNDERWRITING"],
        },
        {
            "doc_type": "business_tax_returns_2year",
            "description": "Business tax returns for the past 2 years",
            "category": "income",
            "priority": "required",
            "stages": ["APPLICATION"],
        },
    ],
}


class StageChecklistService:
    """
    Stage-aware document checklist manager.

    Generates requirements based on loan stage + type and auto-updates
    checklists when a loan transitions between stages.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public: get requirements for a stage
    # ------------------------------------------------------------------

    def get_requirements_for_stage(
        self,
        stage: str,
        loan_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return the list of document requirements for a given pipeline stage,
        optionally augmented with loan-type-specific documents.

        Parameters
        ----------
        stage : str
            Loan pipeline stage (uppercase, e.g. ``"APPLICATION"``).
        loan_type : str, optional
            Loan program type (e.g. ``"CONVENTIONAL"``, ``"FHA"``, ``"VA"``).

        Returns
        -------
        list[dict]
            Each dict has keys: doc_type, description, category, priority
        """
        stage_upper = (stage or "").upper().strip()
        base = STAGE_DOCUMENT_REQUIREMENTS.get(stage_upper, [])
        # Deep-copy so callers cannot mutate the module-level constant
        requirements = [dict(item) for item in base]

        # Merge loan-type extras applicable to this stage
        if loan_type:
            lt_upper = loan_type.upper().strip()
            for extra in _LOAN_TYPE_EXTRAS.get(lt_upper, []):
                applicable_stages = extra.get("stages", [])
                if stage_upper in applicable_stages:
                    requirements.append({
                        "doc_type": extra["doc_type"],
                        "description": extra["description"],
                        "category": extra["category"],
                        "priority": extra["priority"],
                    })

        return requirements

    def get_cumulative_requirements(
        self,
        up_to_stage: str,
        loan_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return all document requirements from APPLICATION through *up_to_stage*
        (inclusive), de-duplicated by doc_type.

        Useful for showing the complete checklist on a borrower portal.
        """
        stage_order = [
            "APPLICATION",
            "PROCESSING",
            "UNDERWRITING",
            "CONDITIONAL_APPROVAL",
            "CTC",
            "CLOSING",
        ]
        target = (up_to_stage or "").upper().strip()
        seen: set = set()
        cumulative: List[Dict[str, Any]] = []

        for stg in stage_order:
            for req in self.get_requirements_for_stage(stg, loan_type):
                if req["doc_type"] not in seen:
                    seen.add(req["doc_type"])
                    cumulative.append(req)
            if stg == target:
                break

        return cumulative

    # ------------------------------------------------------------------
    # Public: stage-change handler
    # ------------------------------------------------------------------

    def on_stage_change(
        self,
        loan_id: int,
        old_stage: Optional[str],
        new_stage: str,
        conditions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Handle a loan stage transition.

        1. Determine newly required documents (delta between old and new stage).
        2. Create document-request records for any new requirements.
        3. Notify borrower of the new documents needed.
        4. Write audit log entry.

        Parameters
        ----------
        loan_id : int
            The loan being transitioned.
        old_stage : str or None
            Previous stage (None on initial creation).
        new_stage : str
            Stage the loan is transitioning to.
        conditions : list[dict], optional
            Underwriting conditions to add at CONDITIONAL_APPROVAL stage.
            Each dict should have ``doc_type`` and ``description``.

        Returns
        -------
        dict
            ``new_requirements``: list of newly added doc requirements
            ``notification_sent``: bool
        """
        new_upper = (new_stage or "").upper().strip()
        old_upper = (old_stage or "").upper().strip() if old_stage else None

        result: Dict[str, Any] = {
            "new_requirements": [],
            "notification_sent": False,
            "loan_id": loan_id,
            "old_stage": old_upper,
            "new_stage": new_upper,
        }

        try:
            from database.models.lead_loan import Loan

            loan = self.db.query(Loan).filter(Loan.id == loan_id).first()
            if loan is None:
                logger.error("on_stage_change: loan %s not found", loan_id)
                return result

            loan_type = getattr(loan, "loan_type", None) or "CONVENTIONAL"

            # Compute delta: new-stage requirements minus already-existing doc types
            new_reqs = self.get_requirements_for_stage(new_upper, loan_type)

            # Handle CONDITIONAL_APPROVAL dynamic conditions
            if new_upper == "CONDITIONAL_APPROVAL" and conditions:
                for cond in conditions:
                    new_reqs.append({
                        "doc_type": cond.get("doc_type", "uw_condition"),
                        "description": cond.get(
                            "description", "Underwriting condition"
                        ),
                        "category": cond.get("category", "compliance"),
                        "priority": "required",
                    })

            # Filter out docs already requested for this loan
            existing_types = self._get_existing_doc_types(loan_id)
            delta = [
                req for req in new_reqs
                if req["doc_type"] not in existing_types
            ]

            if not delta:
                logger.info(
                    "No new doc requirements for loan=%s stage=%s",
                    loan_id,
                    new_upper,
                )
                return result

            # Persist new document requests
            for req in delta:
                self.create_document_request(
                    loan_id=loan_id,
                    doc_type=req["doc_type"],
                    description=req["description"],
                    category=req["category"],
                    priority=req["priority"],
                )

            result["new_requirements"] = delta

            # Notify borrower
            borrower_contact = self._get_borrower_contact(loan)
            if borrower_contact:
                notified = self._notify_borrower_new_docs(
                    borrower_contact=borrower_contact,
                    new_docs=delta,
                    new_stage=new_upper,
                    loan=loan,
                )
                result["notification_sent"] = notified

            # Audit
            self._write_audit_log(
                loan=loan,
                old_stage=old_upper,
                new_stage=new_upper,
                delta=delta,
            )

            self.db.commit()
            logger.info(
                "Stage change %s→%s for loan=%s: %d new doc requirements",
                old_upper,
                new_upper,
                loan_id,
                len(delta),
            )

        except SQLAlchemyError:
            self.db.rollback()
            logger.exception(
                "DB error on stage change for loan=%s", loan_id
            )
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            self.db.rollback()
            logger.exception(
                "Unexpected error on stage change for loan=%s", loan_id
            )

        return result

    # ------------------------------------------------------------------
    # Document request persistence
    # ------------------------------------------------------------------

    def create_document_request(
        self,
        loan_id: int,
        doc_type: str,
        description: str,
        category: str,
        priority: str,
    ) -> Dict[str, Any]:
        """
        Create a document-request record linked to a loan.

        Uses the perennia_document_requests table if the model is available,
        otherwise falls back to a lightweight in-memory representation.

        Returns:
            dict with the document request details.
        """
        try:
            from models.perennia_docs import PerenniaDocs

            DocRequest = PerenniaDocs.DocumentRequest

            req = DocRequest(
                loan_id=loan_id,
                doc_type=doc_type,
                description=description,
                category=category,
                priority=priority,
                status="pending",
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(req)
            self.db.flush()

            return {
                "id": req.id,
                "doc_type": doc_type,
                "description": description,
                "category": category,
                "priority": priority,
                "status": "pending",
            }

        except Exception as e:
            logger.warning(
                "Could not persist DocumentRequest (model may not exist): %s. "
                "Returning transient dict.",
                e,
            )
            return {
                "doc_type": doc_type,
                "description": description,
                "category": category,
                "priority": priority,
                "status": "pending",
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_existing_doc_types(self, loan_id: int) -> set:
        """Return the set of doc_type strings already requested for a loan."""
        try:
            from models.perennia_docs import PerenniaDocs

            DocRequest = PerenniaDocs.DocumentRequest
            rows = (
                self.db.query(DocRequest.doc_type)
                .filter(DocRequest.loan_id == loan_id)
                .all()
            )
            return {r[0] for r in rows}

        except Exception as _exc:  # noqa: BLE001
            # Table may not exist yet
            return set()

    def _get_borrower_contact(self, loan) -> Optional[Dict[str, Any]]:
        """
        Resolve borrower contact details from a Loan record.

        Tries: loan.lead → lead.email/phone/name.
        """
        try:
            from database.models.lead_loan import Lead

            lead_id = getattr(loan, "lead_id", None)
            if not lead_id:
                return None

            lead = self.db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return None

            name_parts = []
            if getattr(lead, "first_name", None):
                name_parts.append(lead.first_name)
            if getattr(lead, "last_name", None):
                name_parts.append(lead.last_name)

            return {
                "name": " ".join(name_parts) or "Borrower",
                "email": getattr(lead, "email", None),
                "phone": getattr(lead, "phone", None),
            }

        except Exception as e:
            logger.error("Failed to resolve borrower contact for loan=%s: %s", loan.id, e)
            return None

    def _notify_borrower_new_docs(
        self,
        borrower_contact: Dict[str, Any],
        new_docs: List[Dict[str, Any]],
        new_stage: str,
        loan: Any,
    ) -> bool:
        """
        Notify borrower about newly required documents via SMS and email.

        Returns True if at least one notification channel succeeded.
        """
        name = borrower_contact.get("name", "Borrower")
        phone = borrower_contact.get("phone")
        email = borrower_contact.get("email")
        any_sent = False

        doc_summary = ", ".join(d["description"][:50] for d in new_docs[:5])
        if len(new_docs) > 5:
            doc_summary += f" (+{len(new_docs) - 5} more)"

        # SMS (via centralized chokepoint with compliance)
        if phone:
            try:
                from telephony.sms import send_sms_verified

                message = (
                    f"Hi {name}, your loan has moved to {new_stage}. "
                    f"New documents needed: {doc_summary}. "
                    f"Upload at {PORTAL_BASE_URL}"
                )
                # Truncate to SMS-safe length
                if len(message) > 1600:
                    message = message[:1597] + "..."

                result = send_sms_verified(
                    to=phone,
                    from_=TELNYX_FROM_NUMBER,
                    text=message,
                    messaging_profile_id=TELNYX_MESSAGING_PROFILE,
                    db=self.db,
                    lead_id=getattr(loan, "lead_id", None),
                    organization_id=getattr(loan, "organization_id", None),
                )
                if result.get("status") == "sent":
                    any_sent = True
                    logger.info(
                        "Stage-change SMS sent to %s for loan=%s",
                        phone[-4:],
                        loan.id,
                    )
                else:
                    logger.warning(
                        "Stage-change SMS blocked for loan=%s: %s",
                        loan.id,
                        result.get("reason", "unknown"),
                    )
            except Exception as e:
                logger.error("SMS notification failed for loan=%s: %s", loan.id, e)

        # Email
        if email:
            try:
                from email_service import EmailService

                svc = EmailService()

                doc_list_html = "".join(
                    f"<li>{d['description']}</li>" for d in new_docs
                )

                html_body = (
                    f"<p>Hi {name},</p>"
                    f"<p>Your loan has progressed to <strong>{new_stage}</strong>. "
                    f"The following new documents are needed:</p>"
                    f"<ul>{doc_list_html}</ul>"
                    f'<p><a href="{PORTAL_BASE_URL}" style="'
                    f"background-color:#2563eb;color:#fff;padding:12px 24px;"
                    f"border-radius:6px;text-decoration:none;font-weight:bold;"
                    f'">Upload Documents</a></p>'
                    f"<p>Best,<br>Perennia AI</p>"
                )

                svc.send_email(
                    to_emails=[email],
                    subject=f"New Documents Needed — Loan Stage: {new_stage}",
                    html_content=html_body,
                )
                any_sent = True
                logger.info(
                    "Stage-change email sent to %s for loan=%s",
                    email,
                    loan.id,
                )
            except Exception as e:
                logger.error("Email notification failed for loan=%s: %s", loan.id, e)

        return any_sent

    def _write_audit_log(
        self,
        loan: Any,
        old_stage: Optional[str],
        new_stage: str,
        delta: List[Dict[str, Any]],
    ) -> None:
        """Write an audit entry for the checklist update."""
        try:
            from database.models.security import AuditLog

            org_id = getattr(loan, "organization_id", None)
            entry = AuditLog(
                organization_id=org_id,
                change_type="checklist_updated",
                entity_type="loan_checklist",
                entity_id=loan.id,
                before_state={"stage": old_stage},
                after_state={
                    "stage": new_stage,
                    "new_doc_types": [d["doc_type"] for d in delta],
                    "count": len(delta),
                },
                timestamp=datetime.now(timezone.utc),
            )
            self.db.add(entry)
            self.db.flush()

        except Exception as e:
            # Audit logging must never block the stage transition
            logger.error("Failed to write checklist audit log: %s", e)
