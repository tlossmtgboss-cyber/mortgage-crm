"""
Pydantic schemas for the POS (Point-of-Sale) Digital 1003 borrower application.

This module provides the complete schema surface for the borrower-facing
application flow, including per-section URLA data, document uploads,
co-borrower invitations, and application status.

Re-exports core schemas from schemas.pos.application and adds document,
co-borrower, and status schemas that were not yet covered.

Usage:
    from schemas.pos_schemas import (
        ApplicationResponse,
        SectionUpdateRequest,
        DocumentUploadResponse,
        CoborrowerInviteRequest,
        ApplicationStatusResponse,
    )
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator

# Re-export existing core schemas for single-import convenience.
from schemas.pos.application import (  # noqa: F401
    ApplicationCreate,
    ApplicationResponse,
    ApplicationSubmitRequest,
    ApplicationSubmitResponse,
    SectionData,
    SectionResponse,
    SectionUpdateRequest,
)


# ============================================================================
# URLA Section Data Schemas (typed per-section shapes)
# ============================================================================


class PersonalInfoData(BaseModel):
    """URLA Section 1a — Borrower personal information."""
    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: Optional[str] = Field(None, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    suffix: Optional[str] = Field(None, max_length=10)
    email: str = Field(..., description="Borrower email")
    phone: str = Field(..., description="Borrower phone")
    marital_status: Optional[str] = Field(
        None,
        description="married | single | separated | unmarried",
    )
    dependents_count: Optional[int] = Field(None, ge=0, le=20)


class AddressData(BaseModel):
    """Common address shape used in residence and employer."""
    street: str = Field(..., min_length=1, max_length=200)
    unit: Optional[str] = Field(None, max_length=50)
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")
    zip: str = Field(..., pattern=r"^\d{5}(-\d{4})?$")


class ResidenceData(BaseModel):
    """URLA Section 1b — Current and previous addresses."""
    current: Optional[dict[str, Any]] = Field(
        None,
        description="Current address with housing_status, years/months, monthly_cost",
    )
    previous: Optional[dict[str, Any]] = Field(
        None,
        description="Previous address (if < 2 years at current)",
    )


class EmployerData(BaseModel):
    """Employer details within employment section."""
    name: str = Field(..., min_length=1, max_length=200)
    position: str = Field(..., min_length=1, max_length=200)
    start_date: Optional[str] = None
    phone: Optional[str] = None
    is_self_employed: Optional[bool] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None


class IncomeData(BaseModel):
    """Monthly income breakdown."""
    base: float = Field(..., ge=0, description="Gross monthly base income")
    overtime: Optional[float] = Field(None, ge=0)
    bonus: Optional[float] = Field(None, ge=0)
    commission: Optional[float] = Field(None, ge=0)
    other: Optional[float] = Field(None, ge=0)


class EmploymentData(BaseModel):
    """URLA Section 1e — Employment and income."""
    employment_type: Optional[str] = Field(
        None,
        description="employee | self_employed | contractor | retired | military | other",
    )
    years_in_profession: Optional[int] = Field(None, ge=0)
    employer: Optional[EmployerData] = None
    income: Optional[IncomeData] = None


class AssetAccountData(BaseModel):
    """Single asset account entry."""
    type: str = Field(
        ...,
        description="checking | savings | money_market | cd | retirement_401k | retirement_ira | brokerage | gift",
    )
    institution: str = Field(..., min_length=1, max_length=200)
    account_number_last4: Optional[str] = Field(None, pattern=r"^\d{4}$")
    balance: float = Field(..., ge=0)


class AssetsData(BaseModel):
    """URLA Section 2a — Assets."""
    accounts: list[AssetAccountData] = Field(default_factory=list)
    receiving_gift: Optional[bool] = None
    gift_amount: Optional[float] = Field(None, ge=0)
    gift_donor: Optional[str] = None
    gift_relationship: Optional[str] = None


class LiabilityData(BaseModel):
    """Single liability entry."""
    type: str = Field(
        ...,
        description="credit_card | auto_loan | student_loan | personal_loan | child_support | alimony | tax_lien | other",
    )
    creditor: str = Field(..., min_length=1, max_length=200)
    balance: Optional[float] = Field(None, ge=0)
    monthly_payment: float = Field(..., ge=0)
    pay_off_at_close: Optional[bool] = None


class LiabilitiesData(BaseModel):
    """URLA Section 2c — Liabilities."""
    liabilities: list[LiabilityData] = Field(default_factory=list)


class PropertyData(BaseModel):
    """Subject property details."""
    address: str = Field(..., min_length=1, max_length=300)
    type: Optional[str] = Field(
        None,
        description="sfr | condo | townhouse | multi_2_4 | manufactured",
    )
    occupancy: Optional[str] = Field(
        None,
        description="primary | second_home | investment",
    )
    value: Optional[float] = Field(None, ge=0, description="Purchase price or estimated value")
    year_built: Optional[int] = Field(None, ge=1800, le=2100)


class LoanPropertyData(BaseModel):
    """URLA Sections 3-4 — Loan and property info."""
    loan_purpose: Optional[str] = Field(
        None,
        description="purchase | refinance | cash_out_refi | construction",
    )
    loan_type: Optional[str] = Field(
        None,
        description="conventional | fha | va | usda | jumbo",
    )
    loan_amount: Optional[float] = Field(None, ge=0)
    property: Optional[PropertyData] = None


class DeclarationsData(BaseModel):
    """URLA Section 5 — Declarations (yes/no questions)."""
    will_occupy_as_primary: Optional[bool] = None
    has_recent_ownership: Optional[bool] = None
    other_mortgage_on_property: Optional[bool] = None
    borrowed_down_payment: Optional[bool] = None
    cosigner_on_other_loans: Optional[bool] = None
    outstanding_judgments: Optional[bool] = None
    bankruptcy_7_years: Optional[bool] = None
    foreclosure_7_years: Optional[bool] = None
    party_to_lawsuit: Optional[bool] = None
    federal_debt_delinquent: Optional[bool] = None
    us_citizen: Optional[bool] = None
    permanent_resident: Optional[bool] = None


class DemographicsData(BaseModel):
    """URLA Section 8 — Demographics (voluntary ECOA/HMDA).

    All fields optional per ECOA. Collection is voluntary and the borrower
    may decline to answer any or all of them.
    """
    ethnicity: Optional[str] = Field(
        None,
        description="hispanic_or_latino | not_hispanic_or_latino | prefer_not_to_say",
    )
    ethnicity_detail: Optional[str] = Field(
        None,
        description="Specific origin (Mexican, Puerto Rican, Cuban, Other)",
    )
    race: Optional[list[str]] = Field(
        None,
        description="One or more: american_indian, asian, black, pacific_islander, white, prefer_not_to_say",
    )
    race_detail: Optional[str] = Field(
        None,
        description="Specific sub-category if applicable",
    )
    sex: Optional[str] = Field(
        None,
        description="male | female | prefer_not_to_say",
    )
    collection_method: Optional[str] = Field(
        None,
        description="face_to_face | telephone | mail_internet",
    )


# ============================================================================
# Document Upload Schemas
# ============================================================================


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document to a POS application."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: UUID
    filename: str
    original_filename: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    category: str
    description: Optional[str] = None
    created_at: datetime


class DocumentListResponse(BaseModel):
    """List of documents attached to an application."""
    application_id: UUID
    documents: list[DocumentUploadResponse]
    total: int


# ============================================================================
# Co-Borrower Invitation Schemas
# ============================================================================


class CoborrowerInviteRequest(BaseModel):
    """Request to invite a co-borrower to the application."""
    email: str = Field(..., description="Co-borrower email address")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, description="Co-borrower phone (optional)")
    relationship_type: Optional[str] = Field(
        None,
        description="spouse | partner | parent | other",
    )

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v


class CoborrowerInviteResponse(BaseModel):
    """Response after sending a co-borrower invitation."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: UUID
    email: str
    first_name: str
    last_name: str
    status: str
    invitation_link: str
    sent_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


# ============================================================================
# Application Status Schema
# ============================================================================


class SectionStatusDetail(BaseModel):
    """Completion status for a single section."""
    section_key: str
    is_complete: bool
    completed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ApplicationStatusResponse(BaseModel):
    """Detailed application status with per-section breakdown."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    current_step: str
    completion_pct: int
    sections: list[SectionStatusDetail]
    submitted_at: Optional[datetime] = None
    submitted_appointment_id: Optional[int] = None

    # Document summary
    document_count: int = 0

    # Co-borrower summary
    has_coborrower_invite: bool = False
    coborrower_status: Optional[str] = None

    created_at: datetime
    updated_at: datetime
