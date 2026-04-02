"""
Rate Monitor Models
SQLAlchemy models for rate monitoring and refinance opportunity tracking
"""

from sqlalchemy import (
    Column, String, Integer, Numeric, Date, DateTime, Text,
    Boolean, ForeignKey, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional

from database import Base


class RateMonitorTarget(Base):
    """
    Rate monitoring target for a MUM client.
    Defines when to trigger refinance opportunity alerts.
    """
    __tablename__ = "rate_monitor_targets"

    id = Column(Integer, primary_key=True, index=True)

    # Link to MUM client (optional - can be standalone)
    mum_client_id = Column(Integer, nullable=True, index=True)

    # Standalone borrower info (when not linked to MUM client)
    borrower_name = Column(String(255))
    borrower_phone = Column(String(50))
    borrower_email = Column(String(255))
    current_rate = Column(Numeric(5, 3))
    current_loan_amount = Column(Numeric(12, 2))

    # Target Type
    target_type = Column(String(50), nullable=False)  # savings_threshold, rate_drop_percentage, manual_target

    # Threshold Values (one will be used based on target_type)
    monthly_savings_threshold = Column(Numeric(10, 2))  # e.g., $200/month
    rate_drop_percentage = Column(Numeric(5, 3))  # e.g., 0.500 (0.5%)
    target_rate = Column(Numeric(5, 3))  # e.g., 5.500

    # Loan Scenario Parameters
    loan_type = Column(String(50), default='conventional')
    loan_term = Column(Integer, default=30)

    # Status
    status = Column(String(50), default='active')
    is_active = Column(Boolean, default=True)

    # AI Receptionist Integration
    auto_call_enabled = Column(Boolean, default=False)
    call_preference = Column(String(50), default='business_hours')

    # Call Tracking
    last_triggered_at = Column(DateTime)
    trigger_count = Column(Integer, default=0)
    vapi_call_id = Column(String(100))
    last_call_status = Column(String(50))
    last_call_at = Column(DateTime)
    appointment_scheduled = Column(Boolean, default=False)
    appointment_date = Column(DateTime)

    # Notification Settings
    notify_email = Column(Boolean, default=True)
    notify_sms = Column(Boolean, default=True)
    notify_lo = Column(Boolean, default=True)

    # Metadata
    notes = Column(Text)
    created_by = Column(Integer)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    history = relationship("RateMonitorHistory", back_populates="target", cascade="all, delete-orphan")
    alerts = relationship("RateMonitorAlert", back_populates="target", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'mum_client_id': self.mum_client_id,
            'borrower_name': self.borrower_name,
            'borrower_phone': self.borrower_phone,
            'borrower_email': self.borrower_email,
            'current_rate': float(self.current_rate) if self.current_rate else None,
            'current_loan_amount': float(self.current_loan_amount) if self.current_loan_amount else None,
            'target_type': self.target_type,
            'monthly_savings_threshold': float(self.monthly_savings_threshold) if self.monthly_savings_threshold else None,
            'rate_drop_percentage': float(self.rate_drop_percentage) if self.rate_drop_percentage else None,
            'target_rate': float(self.target_rate) if self.target_rate else None,
            'loan_type': self.loan_type,
            'loan_term': self.loan_term,
            'status': self.status,
            'is_active': self.is_active,
            'auto_call_enabled': self.auto_call_enabled,
            'call_preference': self.call_preference,
            'last_triggered_at': self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            'trigger_count': self.trigger_count,
            'appointment_scheduled': self.appointment_scheduled,
            'appointment_date': self.appointment_date.isoformat() if self.appointment_date else None,
            'notify_email': self.notify_email,
            'notify_sms': self.notify_sms,
            'notify_lo': self.notify_lo,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_threshold_description(self) -> str:
        """Returns a human-readable description of the threshold."""
        if self.target_type == 'savings_threshold':
            return f"${float(self.monthly_savings_threshold):,.0f}/month savings"
        elif self.target_type == 'rate_drop_percentage':
            return f"{float(self.rate_drop_percentage):.2f}% below client rate"
        elif self.target_type == 'manual_target':
            return f"Rate hits {float(self.target_rate):.3f}%"
        return "Unknown threshold"


class RateMonitorHistory(Base):
    """
    Audit trail of rate checks performed by the background monitoring job.
    """
    __tablename__ = "rate_monitor_history"

    id = Column(Integer, primary_key=True, index=True)

    target_id = Column(Integer, ForeignKey('rate_monitor_targets.id', ondelete='CASCADE'), index=True)
    mum_client_id = Column(Integer, ForeignKey('mum_clients.id', ondelete='SET NULL'), index=True)

    # Rate Check Details
    check_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    client_rate = Column(Numeric(5, 3))
    market_rate = Column(Numeric(5, 3))
    rate_difference = Column(Numeric(5, 3))

    # Calculated Values
    loan_balance = Column(Numeric(12, 2))
    monthly_savings = Column(Numeric(10, 2))
    annual_savings = Column(Numeric(12, 2))

    # Threshold Comparison
    threshold_met = Column(Boolean, default=False, index=True)
    threshold_type = Column(String(50))
    threshold_value = Column(Numeric(10, 3))

    # Action Taken
    alert_generated = Column(Boolean, default=False)
    call_initiated = Column(Boolean, default=False)

    # Rate Source
    rate_source = Column(String(100), default='optimal_blue')
    rate_scenario = Column(JSONB)

    # Relationships
    target = relationship("RateMonitorTarget", back_populates="history")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'target_id': self.target_id,
            'mum_client_id': self.mum_client_id,
            'check_timestamp': self.check_timestamp.isoformat() if self.check_timestamp else None,
            'client_rate': float(self.client_rate) if self.client_rate else None,
            'market_rate': float(self.market_rate) if self.market_rate else None,
            'rate_difference': float(self.rate_difference) if self.rate_difference else None,
            'loan_balance': float(self.loan_balance) if self.loan_balance else None,
            'monthly_savings': float(self.monthly_savings) if self.monthly_savings else None,
            'annual_savings': float(self.annual_savings) if self.annual_savings else None,
            'threshold_met': self.threshold_met,
            'threshold_type': self.threshold_type,
            'threshold_value': float(self.threshold_value) if self.threshold_value else None,
            'alert_generated': self.alert_generated,
            'call_initiated': self.call_initiated,
            'rate_source': self.rate_source,
            'rate_scenario': self.rate_scenario,
        }


class RateMonitorAlert(Base):
    """
    Alert generated when a rate monitoring target is triggered.
    Tracks the lifecycle from alert to potential conversion.
    """
    __tablename__ = "rate_monitor_alerts"

    id = Column(Integer, primary_key=True, index=True)

    target_id = Column(Integer, ForeignKey('rate_monitor_targets.id', ondelete='CASCADE'), index=True)
    mum_client_id = Column(Integer, ForeignKey('mum_clients.id', ondelete='SET NULL'), index=True)
    history_id = Column(Integer, ForeignKey('rate_monitor_history.id', ondelete='SET NULL'))

    # Alert Details
    alert_type = Column(String(50), nullable=False)  # rate_target_hit, savings_threshold, rate_drop
    priority = Column(String(20), default='medium')

    # Rate Information at Alert Time
    client_rate = Column(Numeric(5, 3))
    market_rate = Column(Numeric(5, 3))
    monthly_savings = Column(Numeric(10, 2))
    annual_savings = Column(Numeric(12, 2))

    # Status
    status = Column(String(50), default='pending', index=True)

    # AI Call Tracking
    auto_call_attempted = Column(Boolean, default=False)
    vapi_call_id = Column(String(100))
    call_status = Column(String(50))
    call_outcome = Column(String(100))
    call_duration = Column(Integer)
    call_summary = Column(Text)
    appointment_scheduled_at = Column(DateTime)

    # Manual Follow-up
    assigned_to = Column(Integer)
    follow_up_notes = Column(Text)
    follow_up_date = Column(Date)

    # Conversion Tracking
    converted_to_application = Column(Boolean, default=False)
    application_id = Column(Integer)
    conversion_date = Column(Date)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    acknowledged_at = Column(DateTime)
    resolved_at = Column(DateTime)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    target = relationship("RateMonitorTarget", back_populates="alerts")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'target_id': self.target_id,
            'mum_client_id': self.mum_client_id,
            'history_id': self.history_id,
            'alert_type': self.alert_type,
            'priority': self.priority,
            'client_rate': float(self.client_rate) if self.client_rate else None,
            'market_rate': float(self.market_rate) if self.market_rate else None,
            'monthly_savings': float(self.monthly_savings) if self.monthly_savings else None,
            'annual_savings': float(self.annual_savings) if self.annual_savings else None,
            'status': self.status,
            'auto_call_attempted': self.auto_call_attempted,
            'vapi_call_id': self.vapi_call_id,
            'call_status': self.call_status,
            'call_outcome': self.call_outcome,
            'call_duration': self.call_duration,
            'call_summary': self.call_summary,
            'appointment_scheduled_at': self.appointment_scheduled_at.isoformat() if self.appointment_scheduled_at else None,
            'assigned_to': self.assigned_to,
            'follow_up_notes': self.follow_up_notes,
            'follow_up_date': self.follow_up_date.isoformat() if self.follow_up_date else None,
            'converted_to_application': self.converted_to_application,
            'application_id': self.application_id,
            'conversion_date': self.conversion_date.isoformat() if self.conversion_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
        }


class OptimalBlueRateCache(Base):
    """
    Cached rate data from Optimal Blue API.
    Uses 15-minute TTL to reduce API calls.
    """
    __tablename__ = "optimal_blue_rate_cache"

    id = Column(Integer, primary_key=True, index=True)

    # Cache Key
    cache_key = Column(String(255), unique=True, nullable=False, index=True)

    # Loan Scenario
    loan_type = Column(String(50), nullable=False)
    loan_term = Column(Integer, nullable=False)
    loan_amount = Column(Numeric(12, 2))
    ltv = Column(Numeric(5, 2))
    credit_score = Column(Integer)
    property_type = Column(String(50))
    occupancy = Column(String(50))
    state = Column(String(2))

    # Rate Data
    rate = Column(Numeric(5, 3), nullable=False)
    apr = Column(Numeric(5, 3))
    points = Column(Numeric(5, 3))
    lender_credits = Column(Numeric(10, 2))

    # Additional Options
    rate_options = Column(JSONB)

    # Metadata
    source = Column(String(50), default='optimal_blue')
    is_mock = Column(Boolean, default=False)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, index=True)

    # Raw Response
    raw_response = Column(JSONB)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'cache_key': self.cache_key,
            'loan_type': self.loan_type,
            'loan_term': self.loan_term,
            'loan_amount': float(self.loan_amount) if self.loan_amount else None,
            'ltv': float(self.ltv) if self.ltv else None,
            'credit_score': self.credit_score,
            'property_type': self.property_type,
            'occupancy': self.occupancy,
            'state': self.state,
            'rate': float(self.rate) if self.rate else None,
            'apr': float(self.apr) if self.apr else None,
            'points': float(self.points) if self.points else None,
            'lender_credits': float(self.lender_credits) if self.lender_credits else None,
            'rate_options': self.rate_options,
            'source': self.source,
            'is_mock': self.is_mock,
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
        }

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        if not self.expires_at:
            return True
        return datetime.now(timezone.utc) > self.expires_at


def calculate_monthly_savings(
    client_rate: float,
    market_rate: float,
    loan_balance: float
) -> float:
    """
    Calculate estimated monthly savings from refinancing.

    Formula: (rate_difference / 12 / 100) * loan_balance
    This is a simplified estimate - actual savings depend on many factors.

    Args:
        client_rate: Current rate as percentage (e.g., 7.5)
        market_rate: Current market rate as percentage (e.g., 6.5)
        loan_balance: Current loan balance

    Returns:
        Estimated monthly savings in dollars
    """
    rate_difference = client_rate - market_rate
    if rate_difference <= 0:
        return 0.0

    # Monthly interest savings
    monthly_savings = (rate_difference / 100 / 12) * loan_balance
    return round(monthly_savings, 2)


def calculate_annual_savings(monthly_savings: float) -> float:
    """Calculate annual savings from monthly savings."""
    return round(monthly_savings * 12, 2)
