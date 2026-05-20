"""
Rate Watch Models — Time-series rate observations, margins, targets, and opportunities.

Supports the rate watch polling system that monitors market rates,
compares against borrower targets, and emits refi opportunity events.

Usage:
    from database.models.rate_watch import (
        RateWatchRunLog, RateObservation, RateMarginConfig,
        BorrowerTargetRate, RefiOpportunityEvent,
    )
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime,
    Text, ForeignKey, JSON, Index, Numeric, CheckConstraint,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
import uuid

from db import Base


class RateWatchRunLog(Base):
    """Every ingestion run. Drives 'no successful fetch in N minutes' alerting."""
    __tablename__ = "rate_watch_run_log"
    __table_args__ = (
        Index('idx_run_log_source_started', 'source', text('started_at DESC')),
        Index(
            'idx_run_log_status_started', 'status', text('started_at DESC'),
            postgresql_where=text("status IN ('hard_fail', 'soft_fail')"),
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True))
    status = Column(String, nullable=False)
    rows_observed = Column(Integer, nullable=False, default=0)
    error_message = Column(Text)
    error_kind = Column(String)
    fetch_duration_ms = Column(Integer)
    upstream_etag = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class RateObservation(Base):
    """Time-series of market rate observations. Append-only."""
    __tablename__ = "rate_observations"
    __table_args__ = (
        UniqueConstraint('source', 'product', 'observed_at', name='rate_observations_dedup'),
        CheckConstraint('rate >= 0 AND rate <= 30', name='rate_observations_rate_sane'),
        CheckConstraint(
            "product IN ('30_fixed','15_fixed','30_jumbo','7_6_sofr_arm','30_fha','30_va','20_fixed','10_fixed')",
            name='rate_observations_product_valid',
        ),
        Index('idx_obs_product_observed', 'product', text('observed_at DESC')),
        Index('idx_obs_source_product_observed', 'source', 'product', text('observed_at DESC')),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False)
    product = Column(String, nullable=False)
    rate = Column(Numeric(7, 4), nullable=False)
    points = Column(Numeric(5, 3), nullable=False, default=0)
    change_pct = Column(Numeric(7, 4))
    observed_at = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    fetch_run_id = Column(BigInteger, ForeignKey('rate_watch_run_log.id'), nullable=False)
    raw_payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class RateMarginConfig(Base):
    """Perennia rate = market_rate - margin_bps/10000. Versioned via effective_to."""
    __tablename__ = "rate_margins"
    __table_args__ = (
        CheckConstraint('margin_bps BETWEEN -500 AND 500', name='rate_margins_bps_sane'),
        CheckConstraint(
            "(scope = 'lo_override' AND loan_officer_id IS NOT NULL) "
            "OR (scope = 'global' AND loan_officer_id IS NULL)",
            name='rate_margins_lo_scope',
        ),
        CheckConstraint(
            "product IN ('30_fixed','15_fixed','30_jumbo','7_6_sofr_arm','30_fha','30_va','20_fixed','10_fixed')",
            name='rate_margins_product_valid',
        ),
        Index(
            'uq_margins_active_global', 'product',
            unique=True,
            postgresql_where=text("scope = 'global' AND effective_to IS NULL"),
        ),
        Index(
            'uq_margins_active_lo', 'loan_officer_id', 'product',
            unique=True,
            postgresql_where=text("scope = 'lo_override' AND effective_to IS NULL"),
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product = Column(String, nullable=False)
    margin_bps = Column(Integer, nullable=False)
    scope = Column(String, nullable=False, default='global')
    loan_officer_id = Column(PG_UUID(as_uuid=True))
    effective_from = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    effective_to = Column(DateTime(timezone=True))
    created_by = Column(PG_UUID(as_uuid=True), nullable=False)
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class BorrowerTargetRate(Base):
    """Per-loan refi target. Match engine compares perennia_rate(product) <= target_rate."""
    __tablename__ = "borrower_target_rates"
    __table_args__ = (
        CheckConstraint('target_rate > 0 AND target_rate < 30', name='btr_target_sane'),
        Index('idx_btr_active_product', 'product', 'target_rate', postgresql_where=text("active = TRUE")),
        Index('idx_btr_borrower', 'borrower_id'),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    borrower_id = Column(PG_UUID(as_uuid=True), nullable=False)
    loan_id = Column(Integer, ForeignKey('loans.id'), nullable=False)
    product = Column(String, nullable=False)
    target_rate = Column(Numeric(7, 4), nullable=False)
    min_monthly_savings = Column(Numeric(10, 2))
    min_break_even_months = Column(Integer)
    cooldown_days = Column(Integer, nullable=False, default=30)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    source = Column(String, nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    loan_officer_id = Column(Integer, ForeignKey("users.id"))


class RefiOpportunityEvent(Base):
    """Event log of refi triggers. Status transitions tracked. Snapshot fields captured at detection."""
    __tablename__ = "refi_opportunities"
    __table_args__ = (
        CheckConstraint(
            "status IN ('detected','outreach_sent','borrower_responded','meeting_booked','closed_won','closed_lost','expired')",
            name='refi_status_valid',
        ),
        Index('idx_refi_loan_detected', 'loan_id', text('detected_at DESC')),
        Index(
            'idx_refi_status', 'status', text('detected_at DESC'),
            postgresql_where=text("status NOT IN ('closed_won','closed_lost','expired')"),
        ),
        Index('idx_refi_lo_dashboard', 'loan_officer_id', 'status', text('detected_at DESC')),
        Index('idx_refi_org', 'organization_id'),
        {"extend_existing": True},
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(Integer, ForeignKey('loans.id'), nullable=False)
    borrower_id = Column(PG_UUID(as_uuid=True), nullable=False)
    loan_officer_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    product = Column(String, nullable=False)
    target_rate = Column(Numeric(7, 4), nullable=False)
    market_rate = Column(Numeric(7, 4), nullable=False)
    perennia_rate = Column(Numeric(7, 4), nullable=False)
    margin_bps_at_detection = Column(Integer, nullable=False)
    rate_observation_id = Column(BigInteger, ForeignKey('rate_observations.id'), nullable=False)

    current_balance = Column(Numeric(12, 2), nullable=False)
    current_rate = Column(Numeric(7, 4), nullable=False)
    current_payment = Column(Numeric(10, 2), nullable=False)
    projected_payment = Column(Numeric(10, 2), nullable=False)
    monthly_savings = Column(Numeric(10, 2), nullable=False)
    estimated_break_even_months = Column(Integer)

    status = Column(String, nullable=False, default='detected')
    detected_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    outreach_dispatched_at = Column(DateTime(timezone=True))
    meeting_booked_at = Column(DateTime(timezone=True))
    calendar_event_id = Column(PG_UUID(as_uuid=True))

    tcpa_consent_verified = Column(Boolean, nullable=False)
    tcpa_consent_id = Column(PG_UUID(as_uuid=True))
    quiet_hours_check_passed = Column(Boolean, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
