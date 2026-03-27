"""State-specific mortgage disclosure requirements — database-backed."""

from sqlalchemy import Column, Integer, String, Text, Date, DateTime, func
from sqlalchemy.dialects.postgresql import ARRAY

from database import Base


class StateDisclosure(Base):
    __tablename__ = "state_disclosures"

    id = Column(Integer, primary_key=True)
    state_code = Column(String(2), nullable=False, index=True)
    state_name = Column(String(50), nullable=False)
    # licensing, disclosure, fee_limit, prepayment, cooling_off, special_rule, recording_consent
    category = Column(String(50), nullable=False, index=True)
    requirement = Column(Text, nullable=False)
    applies_to_loan_types = Column(ARRAY(String), nullable=True)  # null = all types
    regulatory_reference = Column(String(255), nullable=True)
    effective_date = Column(Date, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
