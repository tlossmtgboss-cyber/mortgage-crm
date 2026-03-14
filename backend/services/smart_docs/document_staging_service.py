"""
Smart Docs / Portal Task Engine - Document Staging Service

Manages the document staging workflow for the Application Completion Orchestrator
(ACO). Documents identified as needed are staged as draft requests, reviewed by
staff, then published to the borrower portal with notifications.

This is the bridge between AI document identification and borrower-facing task
lists. The lifecycle is:

    IDENTIFIED -> STAGED -> SELECTED -> SENT -> UPLOADED -> REVIEWED -> CLEARED
                                                                 or
                                                         WAIVED (with reason)

Usage:
    from services.smart_docs.document_staging_service import DocumentStagingService

    svc = DocumentStagingService(db=session, org_id="org_123")
    required = await svc.identify_required_documents(
        loan_id="loan_456",
        loan_type="fha",
        loan_purpose="purchase",
        is_self_employed=True,
    )
    staged = await svc.stage_documents(
        loan_id="loan_456", review_id=1, documents=required,
    )
    await svc.select_all_for_sending(loan_id="loan_456", user_id="user_789")
    result = await svc.publish_to_portal(loan_id="loan_456")
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from database.models.app_completion import (
    DocumentStagingRequest,
    DocStagingStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DOCUMENT REQUIREMENTS MATRIX
# =============================================================================
# Maps loan scenarios to the documents required.  Each entry carries a
# doc_type key (matching the string stored on DocumentStagingRequest.doc_type),
# a borrower-friendly label, a reason code used for auditing/grouping, and a
# priority that drives the portal sort order and blocking-doc detection.

DOCUMENT_REQUIREMENTS: Dict[str, List[Dict[str, str]]] = {
    # ------------------------------------------------------------------
    # Base requirements for ALL loans
    # ------------------------------------------------------------------
    "base": [
        {
            "doc_type": "paystub",
            "label": "Most Recent Paystub (30 days)",
            "reason": "income_validation",
            "priority": "HIGH",
        },
        {
            "doc_type": "w2",
            "label": "W-2 Forms (Last 2 Years)",
            "reason": "income_validation",
            "priority": "HIGH",
        },
        {
            "doc_type": "bank_statement",
            "label": "Bank Statements (Last 2 Months)",
            "reason": "asset_verification",
            "priority": "HIGH",
        },
        {
            "doc_type": "drivers_license",
            "label": "Government-Issued Photo ID",
            "reason": "identity_verification",
            "priority": "CRITICAL",
        },
    ],

    # ------------------------------------------------------------------
    # Purchase-specific
    # ------------------------------------------------------------------
    "purchase": [
        {
            "doc_type": "purchase_contract",
            "label": "Fully Executed Purchase Contract",
            "reason": "property_verification",
            "priority": "CRITICAL",
        },
        {
            "doc_type": "earnest_money",
            "label": "Earnest Money Deposit Receipt",
            "reason": "asset_verification",
            "priority": "HIGH",
        },
    ],

    # ------------------------------------------------------------------
    # Self-employed additions
    # ------------------------------------------------------------------
    "self_employed": [
        {
            "doc_type": "tax_returns_personal",
            "label": "Personal Tax Returns (Last 2 Years)",
            "reason": "income_validation",
            "priority": "CRITICAL",
        },
        {
            "doc_type": "tax_returns_business",
            "label": "Business Tax Returns (Last 2 Years)",
            "reason": "income_validation",
            "priority": "CRITICAL",
        },
        {
            "doc_type": "profit_loss",
            "label": "Year-to-Date Profit & Loss Statement",
            "reason": "income_validation",
            "priority": "HIGH",
        },
        {
            "doc_type": "business_license",
            "label": "Business License or Articles of Incorporation",
            "reason": "employment_verification",
            "priority": "MEDIUM",
        },
    ],

    # ------------------------------------------------------------------
    # VA-specific
    # ------------------------------------------------------------------
    "va": [
        {
            "doc_type": "dd214",
            "label": "DD-214 (Certificate of Release)",
            "reason": "eligibility_verification",
            "priority": "CRITICAL",
        },
        {
            "doc_type": "coe",
            "label": "Certificate of Eligibility (COE)",
            "reason": "eligibility_verification",
            "priority": "CRITICAL",
        },
    ],

    # ------------------------------------------------------------------
    # FHA-specific
    # ------------------------------------------------------------------
    "fha": [
        {
            "doc_type": "fha_case_number",
            "label": "FHA Case Number Assignment",
            "reason": "program_requirement",
            "priority": "HIGH",
        },
    ],

    # ------------------------------------------------------------------
    # Gift funds
    # ------------------------------------------------------------------
    "gift_funds": [
        {
            "doc_type": "gift_letter",
            "label": "Gift Letter (Signed by Donor)",
            "reason": "asset_verification",
            "priority": "CRITICAL",
        },
        {
            "doc_type": "gift_source",
            "label": "Gift Funds Source Documentation",
            "reason": "asset_verification",
            "priority": "HIGH",
        },
    ],

    # ------------------------------------------------------------------
    # Rental income
    # ------------------------------------------------------------------
    "rental_income": [
        {
            "doc_type": "rental_agreement",
            "label": "Current Lease Agreements",
            "reason": "income_validation",
            "priority": "HIGH",
        },
        {
            "doc_type": "schedule_e",
            "label": "Schedule E from Tax Returns",
            "reason": "income_validation",
            "priority": "HIGH",
        },
    ],

    # ------------------------------------------------------------------
    # Refinance
    # ------------------------------------------------------------------
    "refinance": [
        {
            "doc_type": "mortgage_statement",
            "label": "Current Mortgage Statement",
            "reason": "liability_verification",
            "priority": "HIGH",
        },
        {
            "doc_type": "homeowners_insurance",
            "label": "Current Homeowners Insurance Dec Page",
            "reason": "property_verification",
            "priority": "MEDIUM",
        },
    ],

    # ------------------------------------------------------------------
    # Credit issues
    # ------------------------------------------------------------------
    "credit_issues": [
        {
            "doc_type": "credit_explanation",
            "label": "Letter of Explanation (Credit)",
            "reason": "credit_verification",
            "priority": "HIGH",
        },
    ],

    # ------------------------------------------------------------------
    # Divorce
    # ------------------------------------------------------------------
    "divorce": [
        {
            "doc_type": "divorce_decree",
            "label": "Final Divorce Decree",
            "reason": "legal_verification",
            "priority": "HIGH",
        },
    ],

    # ------------------------------------------------------------------
    # High DTI
    # ------------------------------------------------------------------
    "high_dti": [
        {
            "doc_type": "lox_debt",
            "label": "Letter of Explanation (Debts)",
            "reason": "liability_verification",
            "priority": "MEDIUM",
        },
    ],
}

# Priority sort order for deterministic ordering in portal task lists.
_PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

# Valid transitions for the staging lifecycle.  Each key maps to the set of
# statuses the record is allowed to move *to* from that status.
_VALID_TRANSITIONS: Dict[str, set] = {
    DocStagingStatus.IDENTIFIED.value: {
        DocStagingStatus.STAGED.value,
        DocStagingStatus.WAIVED.value,
    },
    DocStagingStatus.STAGED.value: {
        DocStagingStatus.SELECTED.value,
        DocStagingStatus.WAIVED.value,
    },
    DocStagingStatus.SELECTED.value: {
        DocStagingStatus.SENT.value,
        DocStagingStatus.STAGED.value,   # allow de-select
        DocStagingStatus.WAIVED.value,
    },
    DocStagingStatus.SENT.value: {
        DocStagingStatus.UPLOADED.value,
        DocStagingStatus.WAIVED.value,
    },
    DocStagingStatus.UPLOADED.value: {
        DocStagingStatus.REVIEWED.value,
        DocStagingStatus.SENT.value,     # reject -> re-request
    },
    DocStagingStatus.REVIEWED.value: {
        DocStagingStatus.CLEARED.value,
        DocStagingStatus.SENT.value,     # reject after review -> re-request
    },
    DocStagingStatus.CLEARED.value: set(),   # terminal
    DocStagingStatus.WAIVED.value: {
        DocStagingStatus.STAGED.value,       # un-waive
    },
}


# =============================================================================
# HELPERS
# =============================================================================

def _now_utc() -> datetime:
    """Current UTC timestamp for audit columns."""
    return datetime.now(timezone.utc)


def _validate_transition(current: str, target: str) -> None:
    """Raise ValueError if the status transition is not allowed."""
    allowed = _VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(
            f"Invalid status transition: {current} -> {target}. "
            f"Allowed targets: {sorted(allowed) if allowed else 'none (terminal state)'}."
        )


def _staging_to_dict(req: DocumentStagingRequest) -> Dict[str, Any]:
    """Serialize a DocumentStagingRequest row to a plain dict."""
    return {
        "id": req.id,
        "loan_id": req.loan_id,
        "review_id": req.review_id,
        "doc_type": req.doc_type,
        "doc_label": req.doc_label,
        "reason_code": req.reason_code,
        "reason_description": req.reason_description,
        "status": req.status,
        "priority": req.priority,
        "portal_published": req.portal_published,
        "borrower_notified": req.borrower_notified,
        "uploaded_document_id": req.uploaded_document_id,
        "due_date": req.due_date.isoformat() if req.due_date else None,
        "staged_at": req.staged_at.isoformat() if req.staged_at else None,
        "sent_at": req.sent_at.isoformat() if req.sent_at else None,
        "uploaded_at": req.uploaded_at.isoformat() if req.uploaded_at else None,
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
        "cleared_at": req.cleared_at.isoformat() if req.cleared_at else None,
        "waived_at": req.waived_at.isoformat() if req.waived_at else None,
        "waived_reason": req.waived_reason,
        "created_at": req.created_at.isoformat() if req.created_at else None,
    }


# =============================================================================
# DOCUMENT STAGING SERVICE
# =============================================================================

class DocumentStagingService:
    """Orchestrates the document staging lifecycle.

    Sits between AI document identification (ACO review engine) and the
    borrower-facing portal task list.  Staff can review, select, waive, or
    add custom requests before anything is published to the borrower.
    """

    def __init__(self, db: Session, org_id: str):
        self.db = db
        self.org_id = org_id

    # -----------------------------------------------------------------
    # 1.  Identify required documents
    # -----------------------------------------------------------------

    async def identify_required_documents(
        self,
        loan_id: str,
        loan_type: Optional[str] = None,
        loan_purpose: Optional[str] = None,
        is_self_employed: bool = False,
        has_gift_funds: bool = False,
        has_rental_income: bool = False,
        has_credit_issues: bool = False,
        is_divorced: bool = False,
        high_dti: bool = False,
    ) -> List[Dict[str, str]]:
        """Determine all documents needed for this loan scenario.

        Builds the full requirement set from the DOCUMENT_REQUIREMENTS matrix
        based on loan characteristics, then cross-references against documents
        already on file (``documents`` table) and any existing staging requests
        to eliminate duplicates.

        Returns a list of requirement dicts (doc_type, label, reason, priority)
        representing truly missing documents.
        """
        # --- Step 1: Assemble applicable requirement keys ----------------
        applicable_keys: List[str] = ["base"]

        purpose_lower = (loan_purpose or "").lower()
        if purpose_lower == "purchase":
            applicable_keys.append("purchase")
        elif purpose_lower in ("refinance", "cash_out_refinance", "rate_term_refinance"):
            applicable_keys.append("refinance")

        type_lower = (loan_type or "").lower()
        if type_lower == "va":
            applicable_keys.append("va")
        elif type_lower == "fha":
            applicable_keys.append("fha")

        if is_self_employed:
            applicable_keys.append("self_employed")
        if has_gift_funds:
            applicable_keys.append("gift_funds")
        if has_rental_income:
            applicable_keys.append("rental_income")
        if has_credit_issues:
            applicable_keys.append("credit_issues")
        if is_divorced:
            applicable_keys.append("divorce")
        if high_dti:
            applicable_keys.append("high_dti")

        # --- Step 2: Build full doc list, dedup by doc_type ---------------
        seen_doc_types: set = set()
        all_required: List[Dict[str, str]] = []

        for key in applicable_keys:
            for req in DOCUMENT_REQUIREMENTS.get(key, []):
                if req["doc_type"] not in seen_doc_types:
                    seen_doc_types.add(req["doc_type"])
                    all_required.append(dict(req))  # shallow copy

        logger.info(
            "Loan %s: %d requirement keys -> %d unique doc types needed",
            loan_id, len(applicable_keys), len(all_required),
        )

        # --- Step 3: Cross-reference existing documents on file -----------
        existing_doc_types = self._get_existing_document_types(loan_id)

        # --- Step 4: Cross-reference existing staging requests ------------
        staged_doc_types = self._get_staged_document_types(loan_id)

        # --- Step 5: Filter to truly missing ------------------------------
        already_covered = existing_doc_types | staged_doc_types
        missing = [
            req for req in all_required
            if req["doc_type"] not in already_covered
        ]

        logger.info(
            "Loan %s: %d on file, %d already staged, %d truly missing",
            loan_id,
            len(existing_doc_types & seen_doc_types),
            len(staged_doc_types & seen_doc_types),
            len(missing),
        )

        return missing

    # -----------------------------------------------------------------
    # 2.  Stage documents
    # -----------------------------------------------------------------

    async def stage_documents(
        self,
        loan_id: str,
        review_id: int,
        documents: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """Create DocumentStagingRequest records in STAGED status.

        These appear on the internal scoring page for staff review before
        anything is published to the borrower portal.

        Args:
            loan_id:   The loan these documents belong to.
            review_id: FK to the ApplicationCompletenessReview that triggered
                       identification (may be None for manual adds).
            documents: List of dicts with at least ``doc_type``, ``label``,
                       ``reason``, ``priority``.

        Returns:
            List of serialized staging request dicts.
        """
        created: List[DocumentStagingRequest] = []
        now = _now_utc()

        for doc in documents:
            req = DocumentStagingRequest(
                organization_id=self.org_id,
                loan_id=loan_id,
                review_id=review_id,
                doc_type=doc["doc_type"],
                doc_label=doc["label"],
                reason_code=doc.get("reason"),
                reason_description=doc.get("reason_description"),
                status=DocStagingStatus.STAGED.value,
                priority=doc.get("priority", "MEDIUM"),
                staged_at=now,
                portal_published=False,
                borrower_notified=False,
            )
            self.db.add(req)
            created.append(req)

        self.db.flush()  # populate ids

        logger.info(
            "Staged %d document requests for loan %s (review %s)",
            len(created), loan_id, review_id,
        )

        return [_staging_to_dict(r) for r in created]

    # -----------------------------------------------------------------
    # 3.  Get staged documents
    # -----------------------------------------------------------------

    async def get_staged_documents(self, loan_id: str) -> List[Dict[str, Any]]:
        """Get all staged documents for a loan, ordered by priority then status.

        Returns every DocumentStagingRequest for the loan regardless of status,
        sorted so CRITICAL items appear first and terminal states (CLEARED,
        WAIVED) appear last.
        """
        requests = (
            self.db.query(DocumentStagingRequest)
            .filter(
                DocumentStagingRequest.organization_id == self.org_id,
                DocumentStagingRequest.loan_id == loan_id,
            )
            .all()
        )

        # Sort: priority asc (CRITICAL first), then lifecycle order
        status_order = {
            DocStagingStatus.IDENTIFIED.value: 0,
            DocStagingStatus.STAGED.value: 1,
            DocStagingStatus.SELECTED.value: 2,
            DocStagingStatus.SENT.value: 3,
            DocStagingStatus.UPLOADED.value: 4,
            DocStagingStatus.REVIEWED.value: 5,
            DocStagingStatus.CLEARED.value: 6,
            DocStagingStatus.WAIVED.value: 7,
        }

        requests.sort(
            key=lambda r: (
                _PRIORITY_ORDER.get(r.priority, 99),
                status_order.get(r.status, 99),
            )
        )

        return [_staging_to_dict(r) for r in requests]

    # -----------------------------------------------------------------
    # 4.  Select for sending (individual)
    # -----------------------------------------------------------------

    async def select_for_sending(
        self,
        staging_ids: List[int],
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """Mark selected staging requests as SELECTED (ready to send).

        Staff reviews the staged list and picks which docs to request from
        the borrower.  Only requests in STAGED status are eligible.

        Returns the updated records.
        """
        if not staging_ids:
            return []

        requests = (
            self.db.query(DocumentStagingRequest)
            .filter(
                DocumentStagingRequest.organization_id == self.org_id,
                DocumentStagingRequest.id.in_(staging_ids),
            )
            .all()
        )

        updated: List[Dict[str, Any]] = []
        now = _now_utc()

        for req in requests:
            _validate_transition(req.status, DocStagingStatus.SELECTED.value)
            req.status = DocStagingStatus.SELECTED.value
            req.staged_by_user_id = user_id
            req.updated_at = now
            updated.append(_staging_to_dict(req))

        self.db.flush()

        logger.info(
            "Selected %d/%d staging requests for sending (user %s)",
            len(updated), len(staging_ids), user_id,
        )

        return updated

    # -----------------------------------------------------------------
    # 5.  Select all for sending (batch)
    # -----------------------------------------------------------------

    async def select_all_for_sending(
        self,
        loan_id: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """Select every STAGED document for sending (batch action).

        Convenience method that selects all requests currently in STAGED
        status for a given loan.
        """
        requests = (
            self.db.query(DocumentStagingRequest)
            .filter(
                DocumentStagingRequest.organization_id == self.org_id,
                DocumentStagingRequest.loan_id == loan_id,
                DocumentStagingRequest.status == DocStagingStatus.STAGED.value,
            )
            .all()
        )

        now = _now_utc()
        updated: List[Dict[str, Any]] = []

        for req in requests:
            req.status = DocStagingStatus.SELECTED.value
            req.staged_by_user_id = user_id
            req.updated_at = now
            updated.append(_staging_to_dict(req))

        self.db.flush()

        logger.info(
            "Batch-selected %d staging requests for loan %s (user %s)",
            len(updated), loan_id, user_id,
        )

        return updated

    # -----------------------------------------------------------------
    # 6.  Publish to portal
    # -----------------------------------------------------------------

    async def publish_to_portal(
        self,
        loan_id: str,
        staging_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Publish selected document requests to the borrower portal.

        Transitions eligible requests from SELECTED to SENT, sets
        ``portal_published = True``, and leaves ``borrower_notified = False``
        so the notification layer can pick them up.

        If *staging_ids* is provided, only those records are published.
        Otherwise every SELECTED request for the loan is published.

        Returns:
            ``{"published_count": int, "portal_tasks": list[dict]}``
        """
        if staging_ids:
            requests = (
                self.db.query(DocumentStagingRequest)
                .filter(
                    DocumentStagingRequest.organization_id == self.org_id,
                    DocumentStagingRequest.loan_id == loan_id,
                    DocumentStagingRequest.id.in_(staging_ids),
                    DocumentStagingRequest.status == DocStagingStatus.SELECTED.value,
                )
                .all()
            )
        else:
            requests = (
                self.db.query(DocumentStagingRequest)
                .filter(
                    DocumentStagingRequest.organization_id == self.org_id,
                    DocumentStagingRequest.loan_id == loan_id,
                    DocumentStagingRequest.status == DocStagingStatus.SELECTED.value,
                )
                .all()
            )

        now = _now_utc()
        portal_tasks: List[Dict[str, Any]] = []

        for req in requests:
            req.status = DocStagingStatus.SENT.value
            req.sent_at = now
            req.sent_channel = "PORTAL"
            req.portal_published = True
            req.borrower_notified = False  # notification sent separately
            req.updated_at = now
            portal_tasks.append(_staging_to_dict(req))

        self.db.flush()

        logger.info(
            "Published %d document tasks to portal for loan %s",
            len(portal_tasks), loan_id,
        )

        return {
            "published_count": len(portal_tasks),
            "portal_tasks": portal_tasks,
        }

    # -----------------------------------------------------------------
    # 7.  Mark uploaded
    # -----------------------------------------------------------------

    async def mark_uploaded(
        self,
        staging_id: int,
        document_id: str,
    ) -> Dict[str, Any]:
        """Mark a staging request as UPLOADED when the borrower uploads the doc.

        Links the staging request to the actual document row via
        ``uploaded_document_id``.
        """
        req = self._get_request(staging_id)
        _validate_transition(req.status, DocStagingStatus.UPLOADED.value)

        now = _now_utc()
        req.status = DocStagingStatus.UPLOADED.value
        req.uploaded_at = now
        req.uploaded_document_id = document_id
        req.updated_at = now
        self.db.flush()

        logger.info(
            "Staging request %d marked uploaded (document %s)",
            staging_id, document_id,
        )

        return _staging_to_dict(req)

    # -----------------------------------------------------------------
    # 8.  Mark reviewed
    # -----------------------------------------------------------------

    async def mark_reviewed(
        self,
        staging_id: int,
        user_id: str,
    ) -> Dict[str, Any]:
        """Mark an uploaded doc as reviewed by staff."""
        req = self._get_request(staging_id)
        _validate_transition(req.status, DocStagingStatus.REVIEWED.value)

        now = _now_utc()
        req.status = DocStagingStatus.REVIEWED.value
        req.reviewed_at = now
        req.reviewed_by_user_id = user_id
        req.updated_at = now
        self.db.flush()

        logger.info(
            "Staging request %d marked reviewed by user %s",
            staging_id, user_id,
        )

        return _staging_to_dict(req)

    # -----------------------------------------------------------------
    # 9.  Mark cleared
    # -----------------------------------------------------------------

    async def mark_cleared(
        self,
        staging_id: int,
        user_id: str,
    ) -> Dict[str, Any]:
        """Mark a document as cleared (accepted, complete).

        This is a terminal state -- the document requirement is fully
        satisfied.
        """
        req = self._get_request(staging_id)
        _validate_transition(req.status, DocStagingStatus.CLEARED.value)

        now = _now_utc()
        req.status = DocStagingStatus.CLEARED.value
        req.cleared_at = now
        req.reviewed_by_user_id = user_id
        req.updated_at = now
        self.db.flush()

        logger.info(
            "Staging request %d cleared by user %s",
            staging_id, user_id,
        )

        return _staging_to_dict(req)

    # -----------------------------------------------------------------
    # 10.  Waive document
    # -----------------------------------------------------------------

    async def waive_document(
        self,
        staging_id: int,
        user_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Waive a document requirement with a reason.

        Allowed from most non-terminal statuses.  The reason is stored for
        audit purposes.
        """
        req = self._get_request(staging_id)
        _validate_transition(req.status, DocStagingStatus.WAIVED.value)

        now = _now_utc()
        req.status = DocStagingStatus.WAIVED.value
        req.waived_at = now
        req.waived_reason = reason
        req.reviewed_by_user_id = user_id
        req.updated_at = now
        self.db.flush()

        logger.info(
            "Staging request %d waived by user %s: %s",
            staging_id, user_id, reason,
        )

        return _staging_to_dict(req)

    # -----------------------------------------------------------------
    # 11.  Add custom request
    # -----------------------------------------------------------------

    async def add_custom_request(
        self,
        loan_id: str,
        review_id: int,
        doc_type: str,
        doc_label: str,
        reason: str,
        priority: str = "MEDIUM",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a custom document request not from the standard matrix.

        Useful when an underwriter needs something specific that is not
        covered by the requirements matrix (e.g., a specialised letter of
        explanation for an unusual asset).
        """
        if priority not in _PRIORITY_ORDER:
            raise ValueError(
                f"Invalid priority '{priority}'. "
                f"Must be one of: {', '.join(_PRIORITY_ORDER)}."
            )

        now = _now_utc()
        req = DocumentStagingRequest(
            organization_id=self.org_id,
            loan_id=loan_id,
            review_id=review_id,
            doc_type=doc_type,
            doc_label=doc_label,
            reason_code="custom",
            reason_description=reason,
            status=DocStagingStatus.STAGED.value,
            priority=priority,
            staged_by_user_id=user_id,
            staged_at=now,
            portal_published=False,
            borrower_notified=False,
        )
        self.db.add(req)
        self.db.flush()

        logger.info(
            "Custom staging request created for loan %s: %s (%s)",
            loan_id, doc_type, doc_label,
        )

        return _staging_to_dict(req)

    # -----------------------------------------------------------------
    # 12.  Get portal task list (borrower-facing)
    # -----------------------------------------------------------------

    async def get_portal_task_list(self, loan_id: str) -> List[Dict[str, Any]]:
        """Get the borrower-facing task list for the portal.

        Returns only published items (``portal_published = True``) with
        borrower-friendly labels.  Each task tells the borrower what to
        upload and its current status.  Items that have been CLEARED or
        WAIVED are excluded from the active task list; they are returned
        in a separate ``completed`` section.
        """
        requests = (
            self.db.query(DocumentStagingRequest)
            .filter(
                DocumentStagingRequest.organization_id == self.org_id,
                DocumentStagingRequest.loan_id == loan_id,
                DocumentStagingRequest.portal_published == True,  # noqa: E712
            )
            .all()
        )

        active_tasks: List[Dict[str, Any]] = []
        completed_tasks: List[Dict[str, Any]] = []

        terminal_statuses = {
            DocStagingStatus.CLEARED.value,
            DocStagingStatus.WAIVED.value,
        }

        for req in requests:
            task = {
                "id": req.id,
                "doc_type": req.doc_type,
                "label": req.doc_label,
                "priority": req.priority,
                "status": self._borrower_friendly_status(req.status),
                "status_raw": req.status,
                "due_date": req.due_date.isoformat() if req.due_date else None,
                "uploaded": req.status in (
                    DocStagingStatus.UPLOADED.value,
                    DocStagingStatus.REVIEWED.value,
                    DocStagingStatus.CLEARED.value,
                ),
                "cleared": req.status == DocStagingStatus.CLEARED.value,
            }

            if req.status in terminal_statuses:
                completed_tasks.append(task)
            else:
                active_tasks.append(task)

        # Sort active tasks: CRITICAL first, then HIGH, etc.
        active_tasks.sort(key=lambda t: _PRIORITY_ORDER.get(t["priority"], 99))

        return active_tasks + completed_tasks

    # -----------------------------------------------------------------
    # 13.  Document readiness summary
    # -----------------------------------------------------------------

    async def get_document_readiness_summary(self, loan_id: str) -> Dict[str, Any]:
        """Summary for scoring: how ready are we on documents?

        Returns counts by status, a readiness percentage, and a list of
        blocking documents (CRITICAL priority docs not yet cleared/waived).
        """
        requests = (
            self.db.query(DocumentStagingRequest)
            .filter(
                DocumentStagingRequest.organization_id == self.org_id,
                DocumentStagingRequest.loan_id == loan_id,
            )
            .all()
        )

        counters: Dict[str, int] = {
            "identified": 0,
            "staged": 0,
            "selected": 0,
            "sent": 0,
            "uploaded": 0,
            "reviewed": 0,
            "cleared": 0,
            "waived": 0,
        }

        blocking_docs: List[Dict[str, Any]] = []
        terminal = {DocStagingStatus.CLEARED.value, DocStagingStatus.WAIVED.value}

        for req in requests:
            status_key = req.status.lower() if req.status else "identified"
            if status_key in counters:
                counters[status_key] += 1

            # A blocking doc is CRITICAL priority and not yet in a terminal state
            if req.priority == "CRITICAL" and req.status not in terminal:
                blocking_docs.append({
                    "id": req.id,
                    "doc_type": req.doc_type,
                    "label": req.doc_label,
                    "status": req.status,
                })

        total_required = len(requests)
        total_satisfied = counters["cleared"] + counters["waived"]

        readiness_pct = 0.0
        if total_required > 0:
            readiness_pct = round((total_satisfied / total_required) * 100, 1)

        # Sort blocking docs: IDENTIFIED before STAGED before SENT, etc.
        lifecycle_order = {
            DocStagingStatus.IDENTIFIED.value: 0,
            DocStagingStatus.STAGED.value: 1,
            DocStagingStatus.SELECTED.value: 2,
            DocStagingStatus.SENT.value: 3,
            DocStagingStatus.UPLOADED.value: 4,
            DocStagingStatus.REVIEWED.value: 5,
        }
        blocking_docs.sort(
            key=lambda d: lifecycle_order.get(d["status"], 99)
        )

        return {
            "total_required": total_required,
            "identified": counters["identified"],
            "staged": counters["staged"],
            "selected": counters["selected"],
            "sent": counters["sent"],
            "uploaded": counters["uploaded"],
            "reviewed": counters["reviewed"],
            "cleared": counters["cleared"],
            "waived": counters["waived"],
            "readiness_pct": readiness_pct,
            "blocking_docs": blocking_docs,
        }

    # -----------------------------------------------------------------
    # 14.  Reject uploaded document (send back for re-upload)
    # -----------------------------------------------------------------

    async def reject_uploaded_document(
        self,
        staging_id: int,
        user_id: str,
        rejection_reason: str,
    ) -> Dict[str, Any]:
        """Reject an uploaded/reviewed document and request re-upload.

        Transitions the request back to SENT so it reappears on the
        borrower's active task list.  The rejection reason is stored in
        ``reason_description`` and the linked ``uploaded_document_id`` is
        cleared.
        """
        req = self._get_request(staging_id)
        _validate_transition(req.status, DocStagingStatus.SENT.value)

        now = _now_utc()
        req.status = DocStagingStatus.SENT.value
        req.reason_description = (
            f"Rejected: {rejection_reason}"
            if not (req.reason_description or "").startswith("Rejected:")
            else f"Rejected: {rejection_reason}"
        )
        req.uploaded_document_id = None
        req.uploaded_at = None
        req.reviewed_at = None
        req.reviewed_by_user_id = user_id
        req.borrower_notified = False  # trigger re-notification
        req.updated_at = now
        self.db.flush()

        logger.info(
            "Staging request %d rejected by user %s: %s",
            staging_id, user_id, rejection_reason,
        )

        return _staging_to_dict(req)

    # -----------------------------------------------------------------
    # 15.  Un-waive a document (restore to STAGED)
    # -----------------------------------------------------------------

    async def un_waive_document(
        self,
        staging_id: int,
        user_id: str,
    ) -> Dict[str, Any]:
        """Restore a waived document requirement back to STAGED.

        Used when a waiver decision is reversed, e.g. underwriter now
        requires the document after all.
        """
        req = self._get_request(staging_id)
        _validate_transition(req.status, DocStagingStatus.STAGED.value)

        now = _now_utc()
        req.status = DocStagingStatus.STAGED.value
        req.waived_at = None
        req.waived_reason = None
        req.staged_at = now
        req.updated_at = now
        self.db.flush()

        logger.info(
            "Staging request %d un-waived by user %s",
            staging_id, user_id,
        )

        return _staging_to_dict(req)

    # -----------------------------------------------------------------
    # 16.  Bulk publish and notify (convenience)
    # -----------------------------------------------------------------

    async def stage_select_and_publish(
        self,
        loan_id: str,
        review_id: int,
        documents: List[Dict[str, str]],
        user_id: str,
    ) -> Dict[str, Any]:
        """End-to-end convenience: stage, select-all, and publish in one call.

        Used when the review engine wants to go straight to borrower without
        staff gate-keeping (e.g., auto-publish for simple files).

        Returns the publish result from ``publish_to_portal``.
        """
        staged = await self.stage_documents(loan_id, review_id, documents)
        if not staged:
            return {"published_count": 0, "portal_tasks": []}

        await self.select_all_for_sending(loan_id, user_id)
        result = await self.publish_to_portal(loan_id)

        logger.info(
            "Auto-published %d documents for loan %s (review %d)",
            result["published_count"], loan_id, review_id,
        )

        return result

    # -----------------------------------------------------------------
    # 17.  Get pending notifications
    # -----------------------------------------------------------------

    async def get_pending_notifications(
        self,
        loan_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get staging requests that are published but borrower has not been
        notified yet.

        The notification layer should call this, send the notification, then
        call ``mark_borrower_notified`` for each.
        """
        query = (
            self.db.query(DocumentStagingRequest)
            .filter(
                DocumentStagingRequest.organization_id == self.org_id,
                DocumentStagingRequest.portal_published == True,   # noqa: E712
                DocumentStagingRequest.borrower_notified == False,  # noqa: E712
            )
        )
        if loan_id:
            query = query.filter(DocumentStagingRequest.loan_id == loan_id)

        requests = query.all()
        return [_staging_to_dict(r) for r in requests]

    # -----------------------------------------------------------------
    # 18.  Mark borrower notified
    # -----------------------------------------------------------------

    async def mark_borrower_notified(
        self,
        staging_ids: List[int],
    ) -> int:
        """Mark staging requests as having been notified to the borrower.

        Returns the number of rows updated.
        """
        if not staging_ids:
            return 0

        updated_count = (
            self.db.query(DocumentStagingRequest)
            .filter(
                DocumentStagingRequest.organization_id == self.org_id,
                DocumentStagingRequest.id.in_(staging_ids),
            )
            .update(
                {
                    DocumentStagingRequest.borrower_notified: True,
                    DocumentStagingRequest.updated_at: _now_utc(),
                },
                synchronize_session="fetch",
            )
        )

        self.db.flush()

        logger.info(
            "Marked %d staging requests as borrower-notified", updated_count,
        )

        return updated_count

    # =================================================================
    # PRIVATE HELPERS
    # =================================================================

    def _get_request(self, staging_id: int) -> DocumentStagingRequest:
        """Fetch a single staging request, raising ValueError if not found
        or if it belongs to a different organization."""
        req = (
            self.db.query(DocumentStagingRequest)
            .filter(
                DocumentStagingRequest.id == staging_id,
                DocumentStagingRequest.organization_id == self.org_id,
            )
            .first()
        )
        if req is None:
            raise ValueError(
                f"DocumentStagingRequest {staging_id} not found "
                f"(org {self.org_id})."
            )
        return req

    def _get_existing_document_types(self, loan_id: str) -> set:
        """Query the ``documents`` table for doc_types already on file for
        this loan.  Only considers documents with status='active'."""
        rows = self.db.execute(
            text(
                "SELECT DISTINCT doc_type FROM documents "
                "WHERE loan_id = :loan_id "
                "  AND organization_id = :org_id "
                "  AND status = 'active'"
            ),
            {"loan_id": loan_id, "org_id": self.org_id},
        ).fetchall()

        return {row[0] for row in rows if row[0]}

    def _get_staged_document_types(self, loan_id: str) -> set:
        """Get doc_types that already have a non-terminal staging request
        for this loan (avoid duplicate requests)."""
        terminal = {DocStagingStatus.WAIVED.value}
        requests = (
            self.db.query(DocumentStagingRequest.doc_type)
            .filter(
                DocumentStagingRequest.organization_id == self.org_id,
                DocumentStagingRequest.loan_id == loan_id,
                ~DocumentStagingRequest.status.in_([s for s in terminal]),
            )
            .distinct()
            .all()
        )
        return {r[0] for r in requests if r[0]}

    @staticmethod
    def _borrower_friendly_status(raw_status: str) -> str:
        """Convert internal staging status to a borrower-friendly label."""
        mapping = {
            DocStagingStatus.IDENTIFIED.value: "Needed",
            DocStagingStatus.STAGED.value: "Needed",
            DocStagingStatus.SELECTED.value: "Needed",
            DocStagingStatus.SENT.value: "Action Required",
            DocStagingStatus.UPLOADED.value: "Under Review",
            DocStagingStatus.REVIEWED.value: "Under Review",
            DocStagingStatus.CLEARED.value: "Complete",
            DocStagingStatus.WAIVED.value: "Not Required",
        }
        return mapping.get(raw_status, "Needed")
