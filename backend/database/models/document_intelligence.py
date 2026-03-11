"""
AI Document Intelligence Models

Models for AI-powered document classification, dynamic requirement rules,
POS-to-document mapping, and call-transcript-based document need detection.

Key tables:
    ai_document_classifications     — AI predictions for document type with
                                      confidence scores and human feedback loop
    document_requirement_rules      — Configurable rules that determine which
                                      documents are required based on loan params
    pos_document_mappings           — Maps POS application fields to doc requirements
    call_intel_document_needs       — Documents needed detected from call transcripts

Usage:
    from database.models.document_intelligence import (
        AIDocumentClassification,
        DocumentRequirementRule,
        POSDocumentMapping,
        CallIntelDocumentNeed,
    )

    # Find low-confidence classifications for human review
    review_queue = db.query(AIDocumentClassification).filter(
        AIDocumentClassification.prediction_confidence < 70,
        AIDocumentClassification.is_correct.is_(None),
        AIDocumentClassification.organization_id == org_id,
    ).order_by(AIDocumentClassification.created_at.desc()).all()
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from db import Base


# =============================================================================
# ENUMS
# =============================================================================

class DocumentRuleCategory(str, enum.Enum):
    """Category of documents that a requirement rule produces."""
    IDENTITY = "identity"
    INCOME = "income"
    ASSETS = "assets"
    PROPERTY = "property"
    CREDIT = "credit"
    SPECIAL = "special"


class DocumentRulePriority(str, enum.Enum):
    """Priority level for a document requirement rule."""
    CRITICAL = "CRITICAL"
    NORMAL = "NORMAL"
    OPTIONAL = "OPTIONAL"


class DocumentRuleAppliesTo(str, enum.Enum):
    """Who the document requirement applies to."""
    BORROWER = "BORROWER"
    CO_BORROWER = "CO_BORROWER"
    BOTH = "BOTH"


class CallIntelDocNeedStatus(str, enum.Enum):
    """Lifecycle status of a call-intel-detected document need."""
    DETECTED = "DETECTED"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"
    REQUEST_CREATED = "REQUEST_CREATED"


# =============================================================================
# AI DOCUMENT CLASSIFICATION
# =============================================================================

class AIDocumentClassification(Base):
    """AI-predicted document type classification with human feedback loop.

    When a document is uploaded (via borrower portal, email intake, or manual
    upload), the AI classifier examines OCR text and visual features to predict
    the document type (e.g., W-2, bank statement, appraisal).

    The ``is_correct`` / ``corrected_doc_type`` fields support a feedback loop
    so classification accuracy improves over time.
    """
    __tablename__ = "ai_document_classifications"
    __table_args__ = (
        Index("ix_ai_doc_class_org_id", "organization_id"),
        Index("ix_ai_doc_class_document_id", "document_id"),
        Index("ix_ai_doc_class_predicted_type", "predicted_doc_type"),
        Index("ix_ai_doc_class_confidence", "prediction_confidence"),
        Index("ix_ai_doc_class_is_correct", "is_correct"),
        Index("ix_ai_doc_class_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, comment="FK to organizations.id")

    # Reference to the classified document (no hard FK — survives document deletion)
    document_id = Column(Integer, nullable=False, comment="FK to smart_documents.id")

    # Classification results
    original_doc_type = Column(String(64), nullable=True, comment="User-assigned type if any")
    predicted_doc_type = Column(String(64), nullable=False, comment="AI-predicted document type")
    prediction_confidence = Column(Integer, nullable=False, comment="0-100 confidence score")
    alternative_classifications = Column(
        JSON, nullable=True,
        comment="Top 3 alternative predictions with scores, e.g. [{type, score}]",
    )

    # Model metadata
    classification_model = Column(String(64), nullable=True, comment="AI model identifier used")
    classification_duration_ms = Column(Integer, nullable=True, comment="Time taken in milliseconds")

    # Feature extraction
    features_detected = Column(
        JSON, nullable=True,
        comment="Features that informed classification, e.g. has_employer_name, has_pay_period",
    )
    text_snippet = Column(Text, nullable=True, comment="OCR text used for classification (first 1000 chars)")

    # Human feedback loop
    is_correct = Column(Boolean, nullable=True, comment="Human feedback: was prediction correct?")
    corrected_doc_type = Column(String(64), nullable=True, comment="Human-corrected type if wrong")
    corrected_by = Column(String(100), nullable=True, comment="User who provided correction")
    corrected_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# =============================================================================
# DOCUMENT REQUIREMENT RULE
# =============================================================================

class DocumentRequirementRule(Base):
    """Configurable rule that determines when a specific document type is required.

    Rules are evaluated against loan parameters (loan type, occupancy, income
    type, amount) to dynamically build the document checklist for each loan.
    Organizations can customize rules to match their underwriting guidelines.

    Example trigger_conditions JSON:
        {
            "loan_types": ["CONVENTIONAL", "FHA"],
            "occupancy_types": ["PRIMARY"],
            "income_types": ["SELF_EMPLOYED"],
            "min_loan_amount": 0,
            "max_loan_amount": null,
            "requires_fields": ["is_self_employed"],
            "field_values": {"is_self_employed": true}
        }
    """
    __tablename__ = "document_requirement_rules"
    __table_args__ = (
        Index("ix_doc_req_rule_org_id", "organization_id"),
        Index("ix_doc_req_rule_category", "category"),
        Index("ix_doc_req_rule_doc_type", "doc_type"),
        Index("ix_doc_req_rule_is_active", "is_active"),
        Index("ix_doc_req_rule_sort_order", "sort_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, comment="FK to organizations.id")

    rule_name = Column(String(255), nullable=False)
    rule_description = Column(Text, nullable=True)
    category = Column(String(64), nullable=False, comment="identity, income, assets, property, credit, special")
    doc_type = Column(String(64), nullable=False, comment="Document type this rule produces")

    # Trigger conditions — evaluated against loan parameters
    trigger_conditions = Column(
        JSON, nullable=True,
        comment="JSON conditions that activate this rule (loan_types, occupancy, income, amount, etc.)",
    )

    required_count = Column(Integer, nullable=False, default=1, comment="Number of documents needed")
    applies_to = Column(
        String(20), nullable=False, default="BORROWER",
        comment="BORROWER, CO_BORROWER, or BOTH",
    )
    priority = Column(
        String(20), nullable=False, default="NORMAL",
        comment="CRITICAL, NORMAL, or OPTIONAL",
    )
    freshness_days = Column(
        Integer, nullable=True,
        comment="Max age in days for the document to be considered current",
    )
    instructions = Column(Text, nullable=True, comment="Instructions shown to borrower when requesting")

    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0, comment="Display ordering within category")

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime, nullable=True,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# =============================================================================
# POS DOCUMENT MAPPING
# =============================================================================

class POSDocumentMapping(Base):
    """Maps Point-of-Sale loan application fields to document requirements.

    When a borrower fills out a POS application (e.g., selects "Self-Employed"
    for income type), this mapping triggers the corresponding document
    requirement (e.g., 2 years of tax returns + P&L statement).

    The ``pos_field_path`` uses JSON-path-style notation to reference nested
    fields in the POS data structure.
    """
    __tablename__ = "pos_document_mappings"
    __table_args__ = (
        Index("ix_pos_doc_map_org_id", "organization_id"),
        Index("ix_pos_doc_map_field_path", "pos_field_path"),
        Index("ix_pos_doc_map_doc_type", "maps_to_doc_type"),
        Index("ix_pos_doc_map_rule_id", "maps_to_rule_id"),
        Index("ix_pos_doc_map_is_active", "is_active"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, comment="FK to organizations.id")

    # POS field reference
    pos_field_path = Column(
        String(500), nullable=False,
        comment="JSON path in POS data, e.g. borrower.income_type",
    )
    pos_field_value = Column(
        String(255), nullable=False,
        comment="Field value that triggers this mapping",
    )

    # Mapping target
    maps_to_doc_type = Column(String(64), nullable=False, comment="Document type this mapping produces")
    maps_to_rule_id = Column(
        Integer, nullable=True,
        comment="FK to document_requirement_rules.id",
    )

    confidence_weight = Column(
        Integer, nullable=False, default=100,
        comment="0-100 — how strongly this mapping indicates the document is needed",
    )
    description = Column(Text, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# =============================================================================
# CALL INTEL DOCUMENT NEED
# =============================================================================

class CallIntelDocumentNeed(Base):
    """Document need identified from call transcript analysis.

    When the call intelligence engine processes a conversation transcript,
    it detects mentions of documents that need to be collected (e.g., borrower
    mentions they changed jobs — triggers need for new employment verification).

    Detected needs go through a confirmation workflow before a formal document
    request is created in the smart_document_requests table.
    """
    __tablename__ = "call_intel_document_needs"
    __table_args__ = (
        Index("ix_call_intel_doc_org_id", "organization_id"),
        Index("ix_call_intel_doc_loan_id", "loan_id"),
        Index("ix_call_intel_doc_lead_id", "lead_id"),
        Index("ix_call_intel_doc_call_id", "call_id"),
        Index("ix_call_intel_doc_status", "status"),
        Index("ix_call_intel_doc_detected_type", "detected_doc_type"),
        Index("ix_call_intel_doc_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, comment="FK to organizations.id")

    # Loan / lead context (no hard FKs — survives record deletion)
    loan_id = Column(Integer, nullable=True, comment="FK to loans.id")
    lead_id = Column(Integer, nullable=True, comment="FK to leads.id")

    # Call reference
    call_id = Column(Integer, nullable=True, comment="FK to call record")
    call_date = Column(DateTime, nullable=True)

    # Detection results
    detected_doc_type = Column(String(64), nullable=False, comment="Document type detected from call")
    detected_doc_description = Column(Text, nullable=True, comment="Description of what was discussed")
    detection_confidence = Column(Integer, nullable=False, comment="0-100 confidence score")
    source_transcript_snippet = Column(Text, nullable=True, comment="Relevant transcript section")
    keywords_matched = Column(
        JSON, nullable=True,
        comment="Keywords that triggered detection, e.g. ['job change', 'new employer']",
    )

    # Status lifecycle
    status = Column(
        String(20), nullable=False, default="DETECTED",
        comment="DETECTED, CONFIRMED, DISMISSED, REQUEST_CREATED",
    )

    # Link to created request (if status = REQUEST_CREATED)
    linked_request_id = Column(
        Integer, nullable=True,
        comment="FK to smart_document_requests.id if request was created",
    )

    # Confirmation tracking
    confirmed_by = Column(String(100), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)

    # Dismissal tracking
    dismissed_by = Column(String(100), nullable=True)
    dismissed_at = Column(DateTime, nullable=True)
    dismiss_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "DocumentRuleCategory",
    "DocumentRulePriority",
    "DocumentRuleAppliesTo",
    "CallIntelDocNeedStatus",
    # Models
    "AIDocumentClassification",
    "DocumentRequirementRule",
    "POSDocumentMapping",
    "CallIntelDocumentNeed",
]
