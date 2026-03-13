"""
Smart Docs V2 Field Mapping Models

Configurable field mappings between AI-extracted document data and CRM
lead/loan/custom fields. Supports per-organization custom fields, transform
pipelines, and mapping versioning.

Tables:
    smart_docs_field_mappings  - Mapping configurations (source -> target)
    smart_docs_custom_fields   - Org-defined custom fields on leads/loans/documents
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, JSON, Text,
    ForeignKey, Index,
)
from db import Base


def utcnow():
    return datetime.now(timezone.utc)


class FieldMappingConfig(Base):
    """Per-org mapping configuration between document extraction fields and CRM targets."""
    __tablename__ = "smart_docs_field_mappings"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    mapping_name = Column(String(200), nullable=False)
    source_type = Column(String(50), nullable=False)
    # Source types:
    #   DOCUMENT_EXTRACTION - Fields extracted by AI from documents
    #   PLAID_DATA          - Fields from Plaid bank account verification
    #   AUS_RESPONSE        - Fields from AUS (DU/LP) findings
    #   MISMO_IMPORT        - Fields imported from MISMO 3.6 XML
    #   MANUAL_ENTRY        - Manually entered field values
    target_type = Column(String(50), nullable=False)
    # Target types:
    #   LEAD_FIELD   - Standard Lead model columns
    #   LOAN_FIELD   - Standard Loan model columns
    #   CUSTOM_FIELD - Org-defined custom fields (smart_docs_custom_fields)
    #   MISMO_FIELD  - MISMO 3.6 data point path
    #   LOS_FIELD    - LOS-specific field (Encompass, Byte, etc.)
    mappings = Column(JSON, nullable=False)
    # Array of mapping rules:
    # [
    #   {
    #     "source_field": "employer_name",
    #     "target_field": "employer",
    #     "transform": "uppercase",
    #     "validation": "not_empty",
    #     "confidence_threshold": 70,
    #     "conflict_resolution": "keep_existing"  # keep_existing | overwrite | manual_review
    #   },
    #   ...
    # ]
    doc_types = Column(JSON)  # Which doc types this mapping applies to, e.g. ["PAYSTUB", "W2"]
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # System-provided (non-deletable) vs user-created
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index('ix_field_mappings_org_source', 'organization_id', 'source_type'),
    )


class CustomField(Base):
    """Org-defined custom field on leads, loans, or documents."""
    __tablename__ = "smart_docs_custom_fields"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    field_name = Column(String(100), nullable=False)
    display_name = Column(String(200), nullable=False)
    field_type = Column(String(30), nullable=False)
    # Field types: STRING, NUMBER, DATE, BOOLEAN, ENUM, CURRENCY
    entity_type = Column(String(30), nullable=False)
    # Entity types: LOAN, LEAD, DOCUMENT
    enum_values = Column(JSON)  # For ENUM type: ["option1", "option2"]
    is_required = Column(Boolean, default=False)
    validation_rules = Column(JSON)  # {min: 0, max: 100, pattern: "^[A-Z]"}
    default_value = Column(String(500))
    is_searchable = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index('ix_custom_fields_org_entity', 'organization_id', 'entity_type'),
    )
