"""
Compliance Check Model — Automated control testing results.
SOC 2 Criteria: CC3 (Risk Assessment), CC4 (Monitoring)
"""
from sqlalchemy import (
    Column, BigInteger, String, Text, Boolean, DateTime, JSON, text
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ComplianceCheck(Base):
    __tablename__ = "soc2_compliance_check"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    check_name = Column(String(255), nullable=False)
    check_category = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    status = Column(String(20), nullable=False)
    details = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True)

    trust_criteria = Column(String(10), nullable=True)
    control_id = Column(String(50), nullable=True)

    remediation_required = Column(Boolean, default=False)
    remediation_notes = Column(Text, nullable=True)
    remediation_deadline = Column(DateTime(timezone=True), nullable=True)
    remediated_at = Column(DateTime(timezone=True), nullable=True)
