"""
Client Management Profile (CMP) Models

ClientProfile, TeamRole, ProcessFlowDocument, and KPISnapshot models.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.client import ClientProfile, TeamRole, ProcessFlowDocument, KPISnapshot
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    Text, ForeignKey, JSON
)
from sqlalchemy.orm import relationship

from db import Base


class ClientProfile(Base):
    __tablename__ = "client_profiles"

    # 1. ACCOUNT & SUBSCRIBER IDENTIFICATION
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String, unique=True, index=True)  # UUID for the subscriber
    account_type = Column(String)  # Solo LO / Team / Branch / Brokerage / Lender
    primary_user_id = Column(Integer, ForeignKey("users.id"))
    company_name = Column(String)  # DBA Name
    nmls_number = Column(String)  # NMLS # for LO
    business_address = Column(JSON)  # {street, city, state, zip}
    team_size = Column(Integer, default=1)

    # 2. USER PROFILE (Primary User)
    user_profile = Column(JSON)

    # 3. TEAM STRUCTURE
    team_structure = Column(JSON)

    # 4. SYSTEM INTEGRATIONS CONFIGURATION
    integration_settings = Column(JSON)

    # 5. CUSTOM PROCESS FLOW
    process_flow_documents = Column(JSON)
    ai_parsed_process_tree = Column(JSON)
    role_to_task_mapping = Column(JSON)
    stage_definitions = Column(JSON)
    user_confirmed_flow = Column(JSON)

    # 6. COMMUNICATION & BRANDING SETTINGS
    branding_settings = Column(JSON)

    # 7. AUTOMATION SETTINGS & PREFERENCES
    automation_settings = Column(JSON)

    # 8. DATA RECONCILIATION PREFERENCES
    reconciliation_settings = Column(JSON)

    # 9. LEAD & PIPELINE PREFERENCES
    pipeline_settings = Column(JSON)

    # 10. ANALYTICS, KPI TARGETS & COACHING GOALS
    kpi_targets = Column(JSON)

    # 11. BILLING & SUBSCRIPTION SETTINGS
    subscription_plan = Column(String)
    addon_modules = Column(JSON)
    seats = Column(Integer, default=1)
    billing_cycle = Column(String)
    billing_status = Column(String)
    payment_method = Column(JSON)
    usage_metrics = Column(JSON)
    renewal_date = Column(DateTime)

    # 12. SUPPORT, LOGGING & AUDIT HISTORY
    support_tickets = Column(JSON)
    ai_corrections = Column(JSON)
    reconciliation_history = Column(JSON)
    user_overrides = Column(JSON)
    webhook_logs = Column(JSON)
    integration_errors = Column(JSON)

    # 13. PORTFOLIO SETTINGS
    portfolio_settings = Column(JSON)

    # 14. ADVANCED FIELDS
    advanced_settings = Column(JSON)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    primary_user = relationship("User", backref="client_profile")


class TeamRole(Base):
    __tablename__ = "team_roles"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    role_name = Column(String)
    responsibilities = Column(JSON)
    permissions = Column(JSON)
    service_level_expectations = Column(JSON)
    backup_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    profile = relationship("ClientProfile", backref="team_roles")
    user = relationship("User", foreign_keys=[user_id], backref="assigned_roles")
    backup_user = relationship("User", foreign_keys=[backup_user_id])


class ProcessFlowDocument(Base):
    __tablename__ = "process_flow_documents"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"))
    document_name = Column(String)
    document_type = Column(String)  # PDF, spreadsheet, flowchart, SOP
    file_url = Column(String)  # S3 or storage URL
    ai_parsing_status = Column(String)  # pending, processing, completed, failed
    ai_parsed_content = Column(JSON)  # Extracted content
    upload_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    profile = relationship("ClientProfile", backref="uploaded_process_flows")


class KPISnapshot(Base):
    __tablename__ = "kpi_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"))
    snapshot_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    metrics = Column(JSON)
    targets = Column(JSON)
    performance_score = Column(Float)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    profile = relationship("ClientProfile", backref="kpi_history")


__all__ = [
    "ClientProfile",
    "TeamRole",
    "ProcessFlowDocument",
    "KPISnapshot",
]
