"""Pydantic schemas for the POS application endpoints."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from database.models.pos import POSSectionKey, POSStatus


SectionKey = Literal[
    "intake",
    "personal",
    "coborrower",
    "residence",
    "employment",
    "assets",
    "liabilities",
    "reo",
    "loan",
    "documents_upload",
    "declarations",
    "credit_auth",
    "schedule",
    "review",
]


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class ApplicationCreate(BaseModel):
    """Body for POST /api/v1/pos/applications when starting a new application."""

    loan_id: int | None = Field(
        default=None,
        description=(
            "Optional. If the borrower already has a loan file, link to it. "
            "If omitted, the application is for a prequalification."
        ),
    )
    source_channel: str | None = Field(
        default=None,
        max_length=64,
        description="Where the borrower came from (purl_email, sms_invite, etc.)",
    )


class ApplicationResponse(BaseModel):
    """Application root returned to the borrower."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    loan_id: int | None
    status: str
    current_step: SectionKey
    completion_pct: int
    submitted_at: datetime | None
    submitted_appointment_id: int | None
    created_at: datetime
    updated_at: datetime

    # Section completion summary (keyed by section_key, value is bool).
    sections_complete: dict[str, bool] = Field(default_factory=dict)

    # PII presence flags only — never the values themselves.
    has_ssn: bool = False
    has_co_ssn: bool = False
    has_dob: bool = False


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


# M4: Cap section payloads at 100 KB serialized and 10 levels of nesting to
# prevent abuse via deeply nested or oversized JSON. Defined at module scope
# because Pydantic v2 reinterprets underscore-prefixed class attributes as
# ModelPrivateAttr — so referencing `cls._MAX_DATA_BYTES` inside a validator
# would compare ints to a ModelPrivateAttr descriptor and raise TypeError.
_SECTION_DATA_MAX_BYTES = 100_000  # 100 KB
_SECTION_DATA_MAX_DEPTH = 10


class SectionData(BaseModel):
    """Container for arbitrary section JSON.

    The shape inside `data` is deliberately not strictly typed at the schema
    level — the URLA structure varies enormously per agency and we don't want
    schema migrations every time a panel adds a field. Section-level
    validation lives in the frontend Zod schemas (see
    frontend/src/features/pos/schemas/) and at submit time in the
    canonical-store mapper.
    """

    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Section-specific URLA fields (varies by section_key).",
    )

    # Optional PII fields lifted out of `data` for encrypted storage.
    # These are only valid on the 'personal' section.
    ssn: str | None = Field(default=None, pattern=r"^\d{3}-?\d{2}-?\d{4}$")
    co_ssn: str | None = Field(default=None, pattern=r"^\d{3}-?\d{2}-?\d{4}$")
    dob: date | None = None
    co_dob: date | None = None

    @field_validator("data")
    @classmethod
    def _validate_data_limits(cls, v: dict[str, Any]) -> dict[str, Any]:
        serialized = json.dumps(v, default=str)
        if len(serialized) > _SECTION_DATA_MAX_BYTES:
            raise ValueError(
                f"Section data exceeds maximum size of {_SECTION_DATA_MAX_BYTES // 1000} KB"
            )
        if _check_depth(v) > _SECTION_DATA_MAX_DEPTH:
            raise ValueError(
                f"Section data exceeds maximum nesting depth of {_SECTION_DATA_MAX_DEPTH}"
            )
        return v

    @field_validator("ssn", "co_ssn")
    @classmethod
    def _normalize_ssn(cls, v: str | None) -> str | None:
        if v is None:
            return v
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) != 9:
            raise ValueError("SSN must be 9 digits")
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"


class SectionUpdateRequest(SectionData):
    """Body for PATCH /api/v1/pos/applications/{id}/sections/{key}.

    Setting `mark_complete=true` flips the section's is_complete flag and
    advances current_step if appropriate.

    `expected_updated_at` enables optimistic locking — if supplied and the
    section's current updated_at differs, the save is rejected with 409.
    """

    mark_complete: bool = False
    expected_updated_at: datetime | None = None


class SectionResponse(BaseModel):
    """Section state returned to the borrower."""

    model_config = ConfigDict(from_attributes=True)

    section_key: SectionKey
    data: dict[str, Any]
    is_complete: bool
    completed_at: datetime | None
    updated_at: datetime

    # PII presence flags for the personal section (never the values).
    has_ssn: bool = False
    has_co_ssn: bool = False
    has_dob: bool = False

    # Populated on PATCH responses so the frontend can skip a second GET.
    application: ApplicationResponse | None = None


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


class ApplicationSubmitRequest(BaseModel):
    """Body for POST /api/v1/pos/applications/{id}/submit."""

    appointment_id: int | None = Field(
        default=None,
        description=(
            "ID of the booked Smart Calendar appointment (from Step 9). "
            "Optional but recommended — drives the LO's intake workflow."
        ),
    )
    acknowledged_certifications: list[str] = Field(
        default_factory=list,
        description=(
            "Keys of the eSign acknowledgments the borrower checked. "
            "Must include 'truth_certification', 'esign_consent', "
            "'credit_authorization' for a valid submit."
        ),
    )


class ApplicationSubmitResponse(BaseModel):
    """Response confirming a successful submit."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str = POSStatus.SUBMITTED
    submitted_at: datetime
    submitted_appointment_id: int | None
    confirmation_number: str = Field(
        description="Human-friendly reference for the borrower (e.g. PRN-2026-04881)."
    )
    next_steps: list[str] = Field(
        default_factory=list,
        description="Borrower-facing checklist of what happens next.",
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _check_depth(obj: Any, current: int = 1) -> int:
    """Return the maximum nesting depth of a JSON-like structure (iterative)."""
    stack = [(obj, current)]
    max_depth = current
    while stack:
        item, depth = stack.pop()
        if depth > max_depth:
            max_depth = depth
        if isinstance(item, dict):
            for v in item.values():
                if isinstance(v, (dict, list)):
                    stack.append((v, depth + 1))
        elif isinstance(item, list):
            for v in item:
                if isinstance(v, (dict, list)):
                    stack.append((v, depth + 1))
    return max_depth
