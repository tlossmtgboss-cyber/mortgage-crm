"""
Data Classification Model — Track sensitive data locations.
SOC 2 Criteria: C1 (Confidentiality), P1-P8 (Privacy)
"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ARRAY, text
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class DataClassificationRecord(Base):
    __tablename__ = "soc2_data_classification"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    table_name = Column(String(255), nullable=False)
    column_name = Column(String(255), nullable=False)

    classification = Column(String(20), nullable=False)
    is_pii = Column(Boolean, default=False)
    is_financial = Column(Boolean, default=False)
    is_encrypted = Column(Boolean, default=False)

    access_restricted = Column(Boolean, default=True)
    authorized_roles = Column(ARRAY(Text), nullable=True)

    retention_policy = Column(String(50), nullable=True)
    retention_days = Column(Integer, nullable=True)

    description = Column(Text, nullable=True)
    regulatory_basis = Column(Text, nullable=True)
