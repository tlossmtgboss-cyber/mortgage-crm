"""Autonomous Document Follow-Up Agent

Proactively follows up on missing/outstanding documents for active loans.
Runs on a schedule to scan all loans in an organization, determine required
documents for each loan's stage, and generate reminders for borrowers/LOs.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models.lead_loan import Lead, Loan
from database.models.document import Document
from database.models.communication import Activity
from database.models.security import Notification
from database.enums import ActivityType, DocumentType

logger = logging.getLogger(__name__)

TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
})

_DT = DocumentType  # shorthand for table below

# Map required-doc keys -> DocumentType values that satisfy them
_DOC_KEY_TO_TYPES: dict[str, list[DocumentType]] = {
    "identification": [_DT.DRIVERS_LICENSE, _DT.PASSPORT, _DT.SSN_CARD],
    "pay_stubs": [_DT.PAYSTUB], "bank_statements": [_DT.BANK_STATEMENT],
    "tax_returns": [_DT.TAX_RETURN_1040, _DT.TAX_RETURN_1099],
    "signed_disclosures": [_DT.INITIAL_DISCLOSURES, _DT.LOAN_ESTIMATE],
    "employment_verification": [_DT.EMPLOYMENT_VERIFICATION],
    "appraisal": [_DT.APPRAISAL], "title_search": [_DT.TITLE_COMMITMENT],
    "insurance_binder": [_DT.HOMEOWNERS_INSURANCE],
    "conditions_list": [_DT.MISC], "final_conditions": [_DT.MISC],
    "closing_docs": [_DT.CLOSING_DISCLOSURE], "wire_instructions": [_DT.MISC],
}

_DOC_KEY_LABELS: dict[str, str] = {
    "identification": "Photo ID", "pay_stubs": "Pay Stubs",
    "bank_statements": "Bank Statements", "tax_returns": "Tax Returns",
    "signed_disclosures": "Signed Disclosures", "employment_verification": "VOE",
    "appraisal": "Appraisal", "title_search": "Title Search / Commitment",
    "insurance_binder": "Insurance Binder", "conditions_list": "Conditions List",
    "final_conditions": "Final Conditions", "closing_docs": "Closing Docs",
    "wire_instructions": "Wire Instructions",
}

_STALE_REVIEW_DAYS = 5


class DocumentFollowupAgent:
    """Identifies loans with missing documents and generates follow-up
    reminders for borrowers and notifications for loan officers."""

    AGENT_TYPE = "document_followup"
    REQUIRED_DOCS_BY_STAGE: dict[str, list[str]] = {
        "APPLICATION": ["identification", "pay_stubs", "bank_statements", "tax_returns"],
        "PROCESSING": ["signed_disclosures", "employment_verification"],
        "UNDERWRITING": ["appraisal", "title_search", "insurance_binder"],
        "CONDITIONAL_APPROVAL": ["conditions_list"],
        "CTC": ["final_conditions"],
        "CLOSING": ["closing_docs", "wire_instructions"],
    }

    def __init__(self, db: Session, org_id: int, config: dict | None = None, gateway=None):
        self.db, self.org_id, self.config = db, org_id, (config or {})
        self.gateway = gateway
        self.logger = logging.getLogger(f"{__name__}.org_{org_id}")

    async def run(self) -> dict:
        """Scan all active loans for missing docs. Returns execution summary."""
        summary: dict = {
            "agent": self.AGENT_TYPE, "organization_id": self.org_id,
            "loans_checked": 0, "loans_with_missing_docs": 0,
            "reminders_sent": 0, "notifications_created": 0, "stale_docs_flagged": 0,
            "by_urgency": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "errors": [],
        }
        try:
            loan_results = self._find_loans_missing_docs()
            summary["loans_checked"] = len(loan_results)
            self.logger.info("Evaluating %d active loans for org %d", len(loan_results), self.org_id)

            for loan, lead, missing_docs in loan_results:
                if not missing_docs:
                    continue
                summary["loans_with_missing_docs"] += 1
                try:
                    urgency = self._calculate_urgency(loan, missing_docs)
                    summary["by_urgency"][urgency] += 1
                    self._send_doc_reminder(loan, lead, missing_docs, urgency)
                    summary["reminders_sent"] += 1
                    if loan.loan_officer_id:
                        self._notify_lo(loan, lead, missing_docs, urgency)
                        summary["notifications_created"] += 1
                    stale = self._check_doc_staleness(loan)
                    if stale:
                        summary["stale_docs_flagged"] += len(stale)
                        self._notify_stale_docs(loan, lead, stale)
                        summary["notifications_created"] += 1
                except Exception as e:
                    self.logger.exception("Failed to process loan %d: %s", loan.id, e)
                    summary["errors"].append({"loan_id": loan.id, "error": str(e)})
            self.db.commit()
        except Exception as e:
            self.logger.exception("Doc follow-up failed for org %d: %s", self.org_id, e)
            self.db.rollback()
            summary["errors"].append({"fatal": str(e)})
        self.logger.info(
            "Doc follow-up org %d: %d checked, %d missing, %d reminders, %d notifs",
            self.org_id, summary["loans_checked"], summary["loans_with_missing_docs"],
            summary["reminders_sent"], summary["notifications_created"],
        )
        return summary

    def _find_loans_missing_docs(self) -> list[tuple]:
        """Return (Loan, Lead|None, missing_doc_keys) for active loans."""
        loans = (
            self.db.query(Loan).filter(
                Loan.organization_id == self.org_id,
                Loan.stage.in_(list(self.REQUIRED_DOCS_BY_STAGE.keys())),
                ~Loan.stage.in_(TERMINAL_STAGES),
            ).all()
        )
        return [(loan, self._resolve_lead(loan), self._get_missing_docs(loan)) for loan in loans]

    def _resolve_lead(self, loan: Loan) -> Optional[Lead]:
        """Find the Lead for a Loan via loan_number or borrower_email."""
        if loan.loan_number:
            lead = self.db.query(Lead).filter(
                Lead.organization_id == self.org_id, Lead.loan_number == loan.loan_number,
            ).first()
            if lead:
                return lead
        if loan.borrower_email:
            return self.db.query(Lead).filter(
                Lead.organization_id == self.org_id, Lead.email == loan.borrower_email,
            ).first()
        return None

    def _get_missing_docs(self, loan: Loan) -> list[str]:
        """Which required documents are missing for this loan's stage (cumulative)."""
        stage_upper = (loan.stage or "").upper()
        required_keys: list[str] = []
        for s in self.REQUIRED_DOCS_BY_STAGE:
            required_keys.extend(self.REQUIRED_DOCS_BY_STAGE[s])
            if s == stage_upper:
                break
        if not required_keys:
            return []

        existing_docs = self.db.query(Document.doc_type).filter(
            Document.organization_id == self.org_id,
            Document.loan_id == loan.id, Document.status == "active",
        ).all()
        existing_types = {
            (dt.value if hasattr(dt, "value") else str(dt))
            for (dt,) in existing_docs if dt is not None
        }
        return [
            key for key in dict.fromkeys(required_keys)
            if not any(dt.value in existing_types for dt in _DOC_KEY_TO_TYPES.get(key, []))
        ]

    def _calculate_urgency(self, loan: Loan, missing_docs: list[str]) -> str:
        """'critical' | 'high' | 'medium' | 'low' based on closing proximity and stage."""
        now = datetime.now(timezone.utc)
        closing = loan.closing_date or loan.scheduled_closing_date
        days_to_close: Optional[float] = None
        if closing:
            closing = closing.replace(tzinfo=timezone.utc) if closing.tzinfo is None else closing
            days_to_close = (closing - now).total_seconds() / 86400
        stage = (loan.stage or "").upper()

        if days_to_close is not None and days_to_close <= 7 and missing_docs:
            return "critical"
        if (days_to_close is not None and days_to_close <= 14) or (
            stage in {"UNDERWRITING", "CONDITIONAL_APPROVAL", "CTC", "CLOSING"} and missing_docs
        ):
            return "high"
        if stage == "PROCESSING" or (days_to_close is not None and days_to_close <= 30):
            return "medium"
        return "low"

    def _send_doc_reminder(
        self, loan: Loan, lead: Optional[Lead], missing_docs: list[str], urgency: str,
    ) -> None:
        """Create a reminder Activity for the borrower about missing documents."""
        name = (lead.first_name if lead else None) or loan.borrower_name or "Borrower"
        doc_list = ", ".join(_DOC_KEY_LABELS.get(k, k) for k in missing_docs)
        prefix = {"critical": "URGENT: ", "high": "Action needed: "}.get(urgency, "")
        self.db.add(Activity(
            organization_id=self.org_id, lead_id=lead.id if lead else None,
            loan_id=loan.id, user_id=loan.loan_officer_id,
            type=ActivityType.NOTE, sentiment="neutral",
            content=(
                f"{prefix}Hi {name}, the following documents are still needed "
                f"for your loan ({loan.loan_number}): {doc_list}. "
                f"Please upload or send them at your earliest convenience."
            ),
            user_metadata={
                "source": self.AGENT_TYPE, "urgency": urgency,
                "missing_docs": missing_docs, "automated": True,
            },
        ))

    def _notify_lo(
        self, loan: Loan, lead: Optional[Lead], missing_docs: list[str], urgency: str,
    ) -> None:
        """Create a Notification for the assigned LO about outstanding docs."""
        if not loan.loan_officer_id:
            return
        name = (
            f"{lead.first_name} {lead.last_name}" if lead and lead.first_name
            else loan.borrower_name or "Unknown Borrower"
        )
        doc_list = ", ".join(_DOC_KEY_LABELS.get(k, k) for k in missing_docs)
        tag = {"critical": "[CRITICAL]", "high": "[HIGH]", "medium": "[MEDIUM]", "low": "[LOW]"}.get(urgency, "")
        closing_str = loan.closing_date.strftime("%m/%d/%Y") if loan.closing_date else "Not set"
        notif = Notification(
            organization_id=self.org_id, user_id=loan.loan_officer_id,
            type="doc_followup", title=f"{tag} Missing docs for {name}",
            message=f"Loan {loan.loan_number} (stage: {loan.stage}) is missing: {doc_list}. Closing: {closing_str}.",
            link=f"/loans/{loan.id}", is_read=False,
        )
        if self.gateway:
            self.gateway.propose(
                "create_notification", lambda n=notif: self.db.add(n),
                target_entity="loan", target_id=loan.id,
                description=f"Missing docs notification for {name}",
            )
        else:
            self.db.add(notif)

    def _check_doc_staleness(self, loan: Loan) -> list[Document]:
        """Find documents uploaded but not updated/reviewed within the staleness window."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.config.get("stale_review_days", _STALE_REVIEW_DAYS))
        return self.db.query(Document).filter(
            Document.organization_id == self.org_id, Document.loan_id == loan.id,
            Document.status == "active", Document.uploaded_at < cutoff,
            func.coalesce(Document.updated_at, Document.uploaded_at) <= Document.uploaded_at,
        ).all()

    def _notify_stale_docs(
        self, loan: Loan, lead: Optional[Lead], stale_docs: list[Document],
    ) -> None:
        """Notify the LO about documents awaiting review."""
        if not loan.loan_officer_id or not stale_docs:
            return
        name = (
            f"{lead.first_name} {lead.last_name}" if lead and lead.first_name
            else loan.borrower_name or "Unknown Borrower"
        )
        doc_names = [d.filename or str(d.doc_type) for d in stale_docs]
        self.db.add(Notification(
            organization_id=self.org_id, user_id=loan.loan_officer_id,
            type="doc_review_stale", title=f"Documents awaiting review for {name}",
            message=(
                f"{len(stale_docs)} doc(s) on loan {loan.loan_number} uploaded but not reviewed: "
                f"{', '.join(doc_names[:5])}{'...' if len(doc_names) > 5 else ''}."
            ),
            link=f"/loans/{loan.id}/documents", is_read=False,
        ))
