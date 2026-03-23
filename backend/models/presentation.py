"""
Presentation Scenario Model
For storing equity scenarios created in PresentationEngine
"""

from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, Text, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from database import Base


class ScenarioType(str, enum.Enum):
    """Types of presentation scenarios"""
    REFINANCE = "refinance"
    CASH_OUT = "cashOut"
    HELOC = "heloc"
    SELL = "sell"


class QuoteRequestStatus(str, enum.Enum):
    """Status of quote requests"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    QUOTED = "quoted"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class PresentationScenario(Base):
    """
    Stores saved presentation scenarios for borrowers
    """
    __tablename__ = "presentation_scenarios"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Foreign Keys
    loan_id = Column(Integer, ForeignKey('loans.id'), nullable=False, index=True)
    borrower_id = Column(Integer, ForeignKey('borrower_profiles.id'), index=True)
    created_by_user_id = Column(Integer, ForeignKey('users.id'), index=True)

    # Scenario Type
    scenario_type = Column(SQLEnum(ScenarioType), nullable=False)

    # Input Values (what the user configured)
    home_value = Column(Numeric(12, 2), nullable=False)
    loan_balance = Column(Numeric(12, 2), nullable=False)
    current_rate = Column(Numeric(5, 3))
    current_payment = Column(Numeric(10, 2))

    # Scenario-specific inputs stored as JSON
    scenario_inputs = Column(JSONB, default={})
    # Example for refinance: {"newRate": 5.5, "newTerm": 30}
    # Example for cashOut: {"cashOutAmount": 50000, "newRate": 6.75}
    # Example for heloc: {"creditLine": 100000, "drawAmount": 25000, "helocRate": 8.5}
    # Example for sell: {"salePrice": 550000, "agentCommission": 5.5, "repairCredits": 5000}

    # Calculated Results (stored for quick retrieval)
    calculated_results = Column(JSONB, default={})
    # Example for refinance: {"newPayment": 1800, "monthlySavings": 200, "breakEvenMonths": 15}

    # Scenario metadata
    name = Column(String(255))  # User-given name like "Refinance Option 1"
    notes = Column(Text)
    is_favorite = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<PresentationScenario {self.scenario_type.value} for loan {self.loan_id}>"

    def to_dict(self):
        return {
            'id': str(self.id),
            'loan_id': self.loan_id,
            'borrower_id': self.borrower_id,
            'scenario_type': self.scenario_type.value if self.scenario_type else None,
            'home_value': float(self.home_value) if self.home_value else None,
            'loan_balance': float(self.loan_balance) if self.loan_balance else None,
            'current_rate': float(self.current_rate) if self.current_rate else None,
            'current_payment': float(self.current_payment) if self.current_payment else None,
            'scenario_inputs': self.scenario_inputs,
            'calculated_results': self.calculated_results,
            'name': self.name,
            'notes': self.notes,
            'is_favorite': self.is_favorite,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class QuoteRequest(Base):
    """
    Stores quote requests submitted from the PresentationEngine
    """
    __tablename__ = "presentation_quote_requests"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Foreign Keys
    loan_id = Column(Integer, ForeignKey('loans.id'), nullable=False, index=True)
    borrower_id = Column(Integer, ForeignKey('borrower_profiles.id'), index=True)
    scenario_id = Column(UUID(as_uuid=True), ForeignKey('presentation_scenarios.id'), index=True)
    assigned_to_user_id = Column(Integer, ForeignKey('users.id'), index=True)

    # Quote Type (matches scenario type)
    quote_type = Column(SQLEnum(ScenarioType), nullable=False)

    # Status
    status = Column(SQLEnum(QuoteRequestStatus), default=QuoteRequestStatus.PENDING)

    # Request Details
    request_data = Column(JSONB, default={})
    # Contains the scenario configuration at time of request

    # Quote Response
    quote_data = Column(JSONB, default={})
    # Filled in by LO with actual quote details

    # Contact preferences
    preferred_contact_method = Column(String(50))  # email, phone, text
    preferred_contact_time = Column(String(255))
    borrower_notes = Column(Text)

    # Internal notes
    internal_notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    quoted_at = Column(DateTime)
    expires_at = Column(DateTime)

    # Relationships
    scenario = relationship("PresentationScenario", backref="quote_requests")

    def __repr__(self):
        return f"<QuoteRequest {self.quote_type.value} - {self.status.value}>"

    def to_dict(self):
        return {
            'id': str(self.id),
            'loan_id': self.loan_id,
            'borrower_id': self.borrower_id,
            'scenario_id': str(self.scenario_id) if self.scenario_id else None,
            'assigned_to_user_id': self.assigned_to_user_id,
            'quote_type': self.quote_type.value if self.quote_type else None,
            'status': self.status.value if self.status else None,
            'request_data': self.request_data,
            'quote_data': self.quote_data,
            'preferred_contact_method': self.preferred_contact_method,
            'preferred_contact_time': self.preferred_contact_time,
            'borrower_notes': self.borrower_notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'quoted_at': self.quoted_at.isoformat() if self.quoted_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
        }
