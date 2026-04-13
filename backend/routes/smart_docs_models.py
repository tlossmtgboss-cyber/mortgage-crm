"""
Smart Docs Pydantic Models / Schemas

Shared request/response models used across smart_docs sub-routers.
Also contains constants (document ID mapping, freshness days) and
tenant-verification helpers used by all sub-routers.
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from models.smart_docs_models import DocType


# =============================================================================
# Tenant Verification Helpers
# =============================================================================

def _get_loan_org_id(db: Session, loan_id: int) -> Optional[int]:
    """Look up organization_id for a loan (for S3 tenant isolation)."""
    row = db.execute(sa_text("SELECT organization_id FROM loans WHERE id = :id"), {"id": loan_id}).first()
    return row[0] if row else None


def _verify_loan_tenant(db: Session, loan_id: int, current_user) -> None:
    """Verify the requesting user's org owns the loan. Raises 404 if not."""
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
    if org_id and not is_platform_admin:
        loan_org = _get_loan_org_id(db, loan_id)
        if loan_org is not None and loan_org != org_id:
            raise HTTPException(status_code=404, detail="Not found")


def _verify_document_tenant(db: Session, document_id: int, current_user):
    """Verify the requesting user's org owns the document's loan. Raises 404 if not."""
    from models.smart_docs_models import SmartDocument as _SD
    doc = db.query(_SD).filter(_SD.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    if doc.loan_id:
        _verify_loan_tenant(db, doc.loan_id, current_user)
    return doc


def _verify_request_tenant(db: Session, request_id: int, current_user) -> None:
    """Verify the requesting user's org owns the document request's loan. Raises 404 if not."""
    from models.smart_docs_models import DocumentRequest as _DR
    req = db.query(_DR).filter(_DR.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    if req.loan_id:
        _verify_loan_tenant(db, req.loan_id, current_user)


# =============================================================================
# Request / Response Models
# =============================================================================

class GenerateNeedsListRequest(BaseModel):
    """Request to generate a needs list."""
    loan_id: int
    loan_program: str  # CONVENTIONAL, FHA, VA, USDA
    occupancy_type: str  # PRIMARY, SECOND_HOME, INVESTMENT
    income_type: str  # W2, SELF_EMPLOYED, RETIREMENT
    borrower_id: int
    co_borrower_id: Optional[int] = None
    has_gift_funds: bool = False
    is_self_employed: bool = False
    has_bankruptcy: bool = False
    property_type: Optional[str] = None


class AddCustomRequestBody(BaseModel):
    """Request to add a custom document request."""
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    priority: str = "NORMAL"
    due_date: Optional[datetime] = None
    doc_type: Optional[str] = None
    requires_esign: bool = False
    esign_initiated: bool = False
    # Notification options
    send_notification: bool = False
    borrower_email: Optional[str] = None
    borrower_name: Optional[str] = None


class WaiveRequestBody(BaseModel):
    """Request to waive a document requirement."""
    reason: str
    waived_by: str


class ManualReviewBody(BaseModel):
    """Request for manual document review."""
    decision: str  # "accept" or "reject"
    reviewer: str
    notes: Optional[str] = None


class DeleteDocumentBody(BaseModel):
    """Request to delete (trash) a document."""
    reviewer: str
    reason: Optional[str] = None


class RejectDocumentBody(BaseModel):
    """Request to reject a document."""
    reviewer: str
    reason: str
    rejection_category: Optional[str] = None  # SCREENSHOT, EXPIRED, POOR_QUALITY, INCOMPLETE, WRONG_TYPE, OTHER


class ReRequestDocumentBody(BaseModel):
    """Request to re-request a document (reset request to OPEN)."""
    reviewer: str
    notes: Optional[str] = None
    new_due_date: Optional[str] = None  # ISO date string


class UpdatePayrollFrequencyBody(BaseModel):
    """Request to update payroll frequency."""
    borrower_id: int
    frequency: str  # WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY


class UpdateDocumentTypeBody(BaseModel):
    """Request to update a document's type."""
    doc_type: str  # PAYSTUB, W2, DRIVERS_LICENSE, BANK_STATEMENT, etc.


class MergeDocumentsRequest(BaseModel):
    """Request to merge multiple documents into a single PDF."""
    loan_id: int
    document_ids: List[int]
    recipient_email: Optional[str] = None  # For merge-email endpoint


class ApplicationDocumentItem(BaseModel):
    """A single document requirement from the application."""
    id: str
    name: str
    description: str
    category: str  # 'identity', 'income', 'assets'
    stage: str


class SyncApplicationDocumentsRequest(BaseModel):
    """Request to sync document requirements from application."""
    loan_id: int
    workspace_slug: Optional[str] = None
    borrower_first_name: str
    co_borrower_first_name: Optional[str] = None
    documents: List[ApplicationDocumentItem]


class ReminderSettingsBody(BaseModel):
    """Request body for updating reminder settings."""
    reminders_enabled: bool = True
    reminder_frequency_hours: int = 72


class ApplyFieldRequest(BaseModel):
    """Single field to apply."""
    field_name: str
    action: str  # "add", "replace", "ignore"
    value: Optional[str] = None


class ApplyFieldsBody(BaseModel):
    """Request to apply extracted fields to Lead/Loan."""
    profile_type: str  # "lead" or "loan"
    profile_id: int
    fields_to_apply: List[ApplyFieldRequest]


class UpdateDocumentNameBody(BaseModel):
    """Request to update document name."""
    display_name: str


class ApproveDocumentBody(BaseModel):
    """Request to approve a document."""
    reviewer: str
    assigned_owner: Optional[str] = None  # "BORROWER", "CO_BORROWER"
    apply_fields: Optional[ApplyFieldsBody] = None
    notes: Optional[str] = None


class SendToPortalForSignatureBody(BaseModel):
    """Request to send a document request to the portal for DocuSign."""
    request_id: Optional[int] = None
    doc_type: Optional[str] = None
    title: str
    type: str  # 'signature' or 'loe' (letter of explanation)
    loe_subject: Optional[str] = None
    loe_instructions: Optional[str] = None


# =============================================================================
# Document ID to DocType Mapping
# =============================================================================

# Maps frontend document IDs to Smart Docs DocType enum
DOCUMENT_ID_TO_DOC_TYPE = {
    # Identity documents
    'id': DocType.DRIVERS_LICENSE,
    'coborrower_id': DocType.DRIVERS_LICENSE,
    'green_card': DocType.OTHER,
    'visa_docs': DocType.OTHER,
    'va_coe': DocType.VA_COE,
    'va_pending_claim': DocType.OTHER,

    # Income documents
    'paystubs': DocType.PAYSTUB,
    'coborrower_paystubs': DocType.PAYSTUB,
    'w2_recent': DocType.W2,
    'w2_prior': DocType.W2,
    'coborrower_w2_recent': DocType.W2,
    'coborrower_w2_prior': DocType.W2,
    'tax_returns': DocType.TAX_RETURN,
    'tax_returns_recent': DocType.TAX_RETURN,
    'tax_returns_prior': DocType.TAX_RETURN,
    'business_tax_returns': DocType.BUSINESS_TAX_RETURN,
    'business_tax_returns_recent': DocType.BUSINESS_TAX_RETURN,
    'business_tax_returns_prior': DocType.BUSINESS_TAX_RETURN,
    'profit_loss': DocType.PROFIT_LOSS,
    'business_bank_statements': DocType.BANK_STATEMENT,
    'articles_incorporation': DocType.OTHER,
    'rental_tax_returns': DocType.TAX_RETURN,

    # Asset documents
    'bank_statements': DocType.BANK_STATEMENT,
    'coborrower_bank_statements': DocType.BANK_STATEMENT,
    'investment_statements': DocType.INVESTMENT_STATEMENT,
    'gift_letter': DocType.GIFT_LETTER,
    'existing_mortgage_statement': DocType.OTHER,
    'lease_agreement': DocType.LEASE_AGREEMENT,
    'new_credit_statement': DocType.OTHER,

    # Special documents
    'divorce_decree': DocType.OTHER,
    'property_settlement': DocType.OTHER,
    'irs_payment_arrangement': DocType.OTHER,
    'irs_payoff': DocType.OTHER,
    'bankruptcy_docs': DocType.BANKRUPTCY_DISCHARGE,
    'bankruptcy_discharge': DocType.BANKRUPTCY_DISCHARGE,
    'ch13_payment_history': DocType.OTHER,
    'ch13_court_approval': DocType.OTHER,
    'ch12_payment_history': DocType.OTHER,
    'ch12_court_approval': DocType.OTHER,
}

# Freshness requirements (days) for different doc types
FRESHNESS_DAYS = {
    DocType.PAYSTUB: 30,
    DocType.BANK_STATEMENT: 60,
    DocType.INVESTMENT_STATEMENT: 90,
    DocType.W2: 365,
    DocType.TAX_RETURN: 365,
    DocType.BUSINESS_TAX_RETURN: 365,
}
