"""
Pydantic v2 models for the Rate Watch system.

These are the contracts between source adapters, the ingestion worker,
the match engine, and the event bus. Every external value crosses one of
these models — no raw dicts past the source boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)


# ---------------------------------------------------------------------------
# Enums — keep these tight; product strings are also enforced in the DB CHECK
# ---------------------------------------------------------------------------
class Product(str, Enum):
    THIRTY_FIXED = "30_fixed"
    FIFTEEN_FIXED = "15_fixed"
    THIRTY_JUMBO = "30_jumbo"
    ARM_7_6_SOFR = "7_6_sofr_arm"
    THIRTY_FHA = "30_fha"
    THIRTY_VA = "30_va"
    TWENTY_FIXED = "20_fixed"
    TEN_FIXED = "10_fixed"


class SourceName(str, Enum):
    MND_HTML = "mnd_html"
    OPTIMAL_BLUE = "optimal_blue"
    FRED = "fred"
    POLLY = "polly"


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    SOFT_FAIL = "soft_fail"
    HARD_FAIL = "hard_fail"


class ErrorKind(str, Enum):
    HTTP_ERROR = "http_error"
    PARSE_ERROR = "parse_error"
    SCHEMA_DRIFT = "schema_drift"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"


class OpportunityStatus(str, Enum):
    DETECTED = "detected"
    OUTREACH_SENT = "outreach_sent"
    BORROWER_RESPONDED = "borrower_responded"
    MEETING_BOOKED = "meeting_booked"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Rate observation — what every source must return for each product
# ---------------------------------------------------------------------------
RateValue = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("30"), decimal_places=4),
]


class RawRateObservation(BaseModel):
    """One product's rate as scraped/fetched from one source at one point in time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: SourceName
    product: Product
    rate: RateValue
    points: Annotated[Decimal, Field(ge=Decimal("-5"), le=Decimal("10"), decimal_places=3)] = Decimal("0.000")
    change_pct: Decimal | None = None
    observed_at: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def _ensure_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        return v.astimezone(timezone.utc)


class SourceFetchResult(BaseModel):
    """What a RateSource.fetch() call returns."""

    model_config = ConfigDict(extra="forbid")

    source: SourceName
    fetched_at: datetime
    fetch_duration_ms: int
    upstream_etag: str | None = None
    observations: list[RawRateObservation]
    # If the source returned a partial result (some products missing), this is non-empty:
    missing_products: list[Product] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Margin & rate computation
# ---------------------------------------------------------------------------
class RateMargin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: Product
    margin_bps: Annotated[int, Field(ge=-500, le=500)]
    scope: Annotated[str, StringConstraints(pattern=r"^(global|lo_override)$")] = "global"
    loan_officer_id: UUID | None = None


class CurrentRate(BaseModel):
    """Joined snapshot: latest market obs + active margin + computed Perennia rate."""

    model_config = ConfigDict(extra="forbid")

    product: Product
    market_rate: RateValue
    points: Decimal
    perennia_rate: RateValue
    margin_bps: int
    observed_at: datetime
    source: SourceName
    observation_id: int

    @property
    def is_stale(self, max_age_minutes: int = 60) -> bool:
        age = (datetime.now(timezone.utc) - self.observed_at).total_seconds() / 60
        return age > max_age_minutes


# ---------------------------------------------------------------------------
# Borrower target & opportunity detection
# ---------------------------------------------------------------------------
class BorrowerTargetRate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    borrower_id: UUID
    loan_id: UUID
    product: Product
    target_rate: RateValue
    min_monthly_savings: Decimal | None = None
    min_break_even_months: int | None = None
    cooldown_days: int = 30
    active: bool = True


class LoanSnapshot(BaseModel):
    """The state of a loan-under-management at the moment of evaluation."""

    model_config = ConfigDict(extra="forbid")

    loan_id: UUID
    borrower_id: UUID
    loan_officer_id: UUID
    current_balance: Decimal
    current_rate: RateValue
    current_term_months: int
    months_remaining: int
    current_monthly_payment: Decimal


class RefiOpportunity(BaseModel):
    """An opportunity emitted to the event bus. Frozen — never mutated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    loan_id: UUID
    borrower_id: UUID
    loan_officer_id: UUID
    product: Product
    target_rate: RateValue
    market_rate: RateValue
    perennia_rate: RateValue
    margin_bps_at_detection: int
    rate_observation_id: int

    current_balance: Decimal
    current_rate: RateValue
    current_payment: Decimal
    projected_payment: Decimal
    monthly_savings: Decimal
    estimated_break_even_months: int | None

    detected_at: datetime
    expires_at: datetime

    tcpa_consent_verified: bool
    tcpa_consent_id: UUID | None
    quiet_hours_check_passed: bool


# ---------------------------------------------------------------------------
# Event bus payloads — what gets emitted to your existing CRM event bus
# ---------------------------------------------------------------------------
class RateObservationRecordedEvent(BaseModel):
    """Emitted after every successful ingestion run."""

    model_config = ConfigDict(extra="forbid")

    event_type: str = "rate.observation.recorded"
    fetch_run_id: int
    source: SourceName
    products_updated: list[Product]
    occurred_at: datetime


class RefiOpportunityDetectedEvent(BaseModel):
    """Emitted when a borrower's target rate is hit. Aria consumes this."""

    model_config = ConfigDict(extra="forbid")

    event_type: str = "refi.opportunity.detected"
    opportunity_id: UUID
    loan_id: UUID
    borrower_id: UUID
    loan_officer_id: UUID
    product: Product
    target_rate: RateValue
    perennia_rate: RateValue
    monthly_savings: Decimal
    occurred_at: datetime
