"""
Test Document Intelligence Models - Validates AIDocumentClassification,
DocumentRequirementRule, POSDocumentMapping, and CallIntelDocumentNeed models
using an in-memory SQLite database.

Covers:
- AIDocumentClassification: creation, confidence scores, feedback loop,
  alternative classifications, batch tracking
- DocumentRequirementRule: rule creation for different loan types, priority
  ordering, trigger conditions, freshness constraints
- POSDocumentMapping: field-to-document mapping, confidence weights
- CallIntelDocumentNeed: status lifecycle, confirmation/dismissal tracking
- Multi-tenant isolation via organization_id filtering
- Classification status transitions
- Confidence threshold validation
- Document type mapping accuracy
"""

import os
import pytest
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from db import Base


# ---------------------------------------------------------------------------
# Fixtures: in-memory SQLite engine scoped to this module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    """Create a PostgreSQL engine and register only the document
    intelligence tables so tests are fully self-contained."""
    _engine = create_engine(os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/test_perennia"))

    # Import models so their table definitions are registered on Base.metadata
    from database.models.document_intelligence import (  # noqa: F401
        AIDocumentClassification,
        DocumentRequirementRule,
        POSDocumentMapping,
        CallIntelDocumentNeed,
    )

    # Create only the four tables under test -- avoids FK issues from other models
    for table_name in (
        "ai_document_classifications",
        "document_requirement_rules",
        "pos_document_mappings",
        "call_intel_document_needs",
    ):
        table = Base.metadata.tables.get(table_name)
        if table is not None:
            table.create(bind=_engine, checkfirst=True)

    yield _engine
    _engine.dispose()


@pytest.fixture()
def db(engine):
    """Yield a transactional session that rolls back after each test."""
    SessionLocal = sessionmaker(bind=engine)
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# =============================================================================
# 1. AIDocumentClassification - Creation & Confidence
# =============================================================================

@pytest.mark.unit
class TestAIDocumentClassificationCreation:
    """Validate basic creation and field storage for document classifications."""

    def test_create_classification_with_required_fields(self, db: Session):
        """A classification can be created with the minimum required fields."""
        from database.models.document_intelligence import AIDocumentClassification

        cls = AIDocumentClassification(
            document_id=101,
            predicted_doc_type="w2",
            prediction_confidence=92,
        )
        db.add(cls)
        db.flush()

        assert cls.id is not None
        assert cls.document_id == 101
        assert cls.predicted_doc_type == "w2"
        assert cls.prediction_confidence == 92

    def test_confidence_score_stored_as_integer(self, db: Session):
        """Confidence score should be stored as an integer 0-100."""
        from database.models.document_intelligence import AIDocumentClassification

        cls = AIDocumentClassification(
            document_id=200,
            predicted_doc_type="bank_statement",
            prediction_confidence=85,
        )
        db.add(cls)
        db.flush()

        fetched = db.query(AIDocumentClassification).filter_by(id=cls.id).one()
        assert isinstance(fetched.prediction_confidence, int)
        assert fetched.prediction_confidence == 85

    def test_classification_stores_alternative_predictions(self, db: Session):
        """Alternative classifications JSON should be persisted correctly."""
        from database.models.document_intelligence import AIDocumentClassification

        alternatives = [
            {"type": "w2", "score": 82},
            {"type": "1099", "score": 65},
            {"type": "paystub", "score": 40},
        ]

        cls = AIDocumentClassification(
            document_id=301,
            predicted_doc_type="w2",
            prediction_confidence=82,
            alternative_classifications=alternatives,
        )
        db.add(cls)
        db.flush()

        fetched = db.query(AIDocumentClassification).filter_by(id=cls.id).one()
        assert fetched.alternative_classifications is not None
        assert len(fetched.alternative_classifications) == 3
        assert fetched.alternative_classifications[0]["type"] == "w2"

    def test_classification_stores_features_detected(self, db: Session):
        """Feature extraction results should be persisted as JSON."""
        from database.models.document_intelligence import AIDocumentClassification

        features = {
            "has_employer_name": True,
            "has_pay_period": True,
            "has_ssn_masked": True,
            "page_count": 2,
        }

        cls = AIDocumentClassification(
            document_id=302,
            predicted_doc_type="paystubs",
            prediction_confidence=95,
            features_detected=features,
        )
        db.add(cls)
        db.flush()

        fetched = db.query(AIDocumentClassification).filter_by(id=cls.id).one()
        assert fetched.features_detected["has_employer_name"] is True
        assert fetched.features_detected["page_count"] == 2


# =============================================================================
# 2. AIDocumentClassification - Human Feedback Loop
# =============================================================================

@pytest.mark.unit
class TestAIDocumentClassificationFeedback:
    """Validate the human feedback / correction workflow."""

    def test_feedback_correct_prediction(self, db: Session):
        """When human marks prediction correct, is_correct=True and no corrected_doc_type."""
        from database.models.document_intelligence import AIDocumentClassification

        cls = AIDocumentClassification(
            document_id=400,
            predicted_doc_type="tax_returns",
            prediction_confidence=90,
        )
        db.add(cls)
        db.flush()

        # Simulate human feedback
        cls.is_correct = True
        cls.corrected_by = "user@example.com"
        cls.corrected_at = datetime.now(timezone.utc)
        db.flush()

        fetched = db.query(AIDocumentClassification).filter_by(id=cls.id).one()
        assert fetched.is_correct is True
        assert fetched.corrected_doc_type is None
        assert fetched.corrected_by == "user@example.com"

    def test_feedback_incorrect_prediction_stores_correction(self, db: Session):
        """When human marks prediction wrong, corrected_doc_type is populated."""
        from database.models.document_intelligence import AIDocumentClassification

        cls = AIDocumentClassification(
            document_id=401,
            predicted_doc_type="bank_statement",
            prediction_confidence=55,
        )
        db.add(cls)
        db.flush()

        cls.is_correct = False
        cls.corrected_doc_type = "investment_statement"
        cls.corrected_by = "reviewer@example.com"
        cls.corrected_at = datetime.now(timezone.utc)
        db.flush()

        fetched = db.query(AIDocumentClassification).filter_by(id=cls.id).one()
        assert fetched.is_correct is False
        assert fetched.corrected_doc_type == "investment_statement"

    def test_unreviewed_classification_has_null_is_correct(self, db: Session):
        """Before human review, is_correct should be None (nullable)."""
        from database.models.document_intelligence import AIDocumentClassification

        cls = AIDocumentClassification(
            document_id=402,
            predicted_doc_type="appraisal",
            prediction_confidence=78,
        )
        db.add(cls)
        db.flush()

        fetched = db.query(AIDocumentClassification).filter_by(id=cls.id).one()
        assert fetched.is_correct is None
        assert fetched.corrected_doc_type is None


# =============================================================================
# 3. DocumentRequirementRule - Creation & Loan Types
# =============================================================================

@pytest.mark.unit
class TestDocumentRequirementRuleCreation:
    """Validate DocumentRequirementRule creation and configuration."""

    def test_create_rule_for_conventional_loan(self, db: Session):
        """A rule targeting conventional loans can be created with trigger conditions."""
        from database.models.document_intelligence import DocumentRequirementRule

        rule = DocumentRequirementRule(
            rule_name="W-2 for Salaried Borrowers",
            category="income",
            doc_type="w2",
            trigger_conditions={"loan_types": ["CONVENTIONAL"]},
            required_count=2,
            applies_to="BORROWER",
            priority="CRITICAL",
            freshness_days=365,
            is_active=True,
            sort_order=10,
        )
        db.add(rule)
        db.flush()

        assert rule.id is not None
        assert rule.rule_name == "W-2 for Salaried Borrowers"
        assert rule.trigger_conditions["loan_types"] == ["CONVENTIONAL"]
        assert rule.required_count == 2
        assert rule.freshness_days == 365

    def test_create_rule_for_multiple_loan_types(self, db: Session):
        """A single rule can apply to multiple loan types via trigger_conditions."""
        from database.models.document_intelligence import DocumentRequirementRule

        rule = DocumentRequirementRule(
            rule_name="Bank Statements",
            category="assets",
            doc_type="bank_statements",
            trigger_conditions={
                "loan_types": ["CONVENTIONAL", "FHA", "VA"],
                "min_loan_amount": 100000,
            },
            required_count=2,
            applies_to="BOTH",
            priority="CRITICAL",
            is_active=True,
            sort_order=20,
        )
        db.add(rule)
        db.flush()

        fetched = db.query(DocumentRequirementRule).filter_by(id=rule.id).one()
        assert "FHA" in fetched.trigger_conditions["loan_types"]
        assert fetched.trigger_conditions["min_loan_amount"] == 100000
        assert fetched.applies_to == "BOTH"

    def test_rule_self_employed_trigger_condition(self, db: Session):
        """Rules can use field_values conditions for self-employment doc needs."""
        from database.models.document_intelligence import DocumentRequirementRule

        rule = DocumentRequirementRule(
            rule_name="P&L for Self-Employed",
            category="income",
            doc_type="profit_loss",
            trigger_conditions={
                "loan_types": ["CONVENTIONAL", "FHA"],
                "income_types": ["SELF_EMPLOYED"],
                "field_values": {"is_self_employed": True},
            },
            required_count=1,
            applies_to="BORROWER",
            priority="CRITICAL",
            instructions="Please provide a year-to-date P&L statement signed by a CPA.",
            is_active=True,
            sort_order=30,
        )
        db.add(rule)
        db.flush()

        fetched = db.query(DocumentRequirementRule).filter_by(id=rule.id).one()
        assert fetched.trigger_conditions["field_values"]["is_self_employed"] is True
        assert "CPA" in fetched.instructions


# =============================================================================
# 4. Rule Priority Ordering
# =============================================================================

@pytest.mark.unit
class TestRulePriorityOrdering:
    """Validate that rules can be queried in priority and sort_order."""

    def test_sort_order_determines_display_sequence(self, db: Session):
        """Rules should be orderable by sort_order within a category."""
        from database.models.document_intelligence import DocumentRequirementRule

        rules_data = [
            ("Tax Returns", "income", "tax_returns", 30),
            ("W-2", "income", "w2", 10),
            ("Pay Stubs", "income", "paystubs", 20),
        ]
        for name, cat, dtype, order in rules_data:
            db.add(DocumentRequirementRule(
                rule_name=name,
                category=cat,
                doc_type=dtype,
                required_count=1,
                applies_to="BORROWER",
                priority="NORMAL",
                is_active=True,
                sort_order=order,
                organization_id=9990,
            ))
        db.flush()

        ordered = (
            db.query(DocumentRequirementRule)
            .filter_by(category="income", organization_id=9990)
            .order_by(DocumentRequirementRule.sort_order.asc())
            .all()
        )

        assert len(ordered) >= 3
        assert ordered[0].doc_type == "w2"
        assert ordered[1].doc_type == "paystubs"
        assert ordered[2].doc_type == "tax_returns"

    def test_critical_priority_sorts_before_optional(self, db: Session):
        """CRITICAL rules should sort before OPTIONAL when ordered by priority string."""
        from database.models.document_intelligence import DocumentRequirementRule, DocumentRulePriority

        db.add(DocumentRequirementRule(
            rule_name="Optional ID",
            category="identity",
            doc_type="passport",
            required_count=1,
            applies_to="BORROWER",
            priority=DocumentRulePriority.OPTIONAL.value,
            is_active=True,
            sort_order=0,
            organization_id=9991,
        ))
        db.add(DocumentRequirementRule(
            rule_name="Required License",
            category="identity",
            doc_type="drivers_license",
            required_count=1,
            applies_to="BORROWER",
            priority=DocumentRulePriority.CRITICAL.value,
            is_active=True,
            sort_order=0,
            organization_id=9991,
        ))
        db.flush()

        # CRITICAL sorts before OPTIONAL alphabetically
        rules = (
            db.query(DocumentRequirementRule)
            .filter_by(category="identity", organization_id=9991)
            .order_by(DocumentRequirementRule.priority.asc())
            .all()
        )
        assert rules[0].priority == "CRITICAL"


# =============================================================================
# 5. POSDocumentMapping - Field to Document Mapping
# =============================================================================

@pytest.mark.unit
class TestPOSDocumentMapping:
    """Validate POS application field to document requirement mappings."""

    def test_create_pos_mapping(self, db: Session):
        """A POS field mapping can be created and persisted."""
        from database.models.document_intelligence import POSDocumentMapping

        mapping = POSDocumentMapping(
            pos_field_path="borrower.income_type",
            pos_field_value="SELF_EMPLOYED",
            maps_to_doc_type="profit_loss",
            confidence_weight=95,
            description="Self-employed borrower needs P&L statement",
            is_active=True,
        )
        db.add(mapping)
        db.flush()

        assert mapping.id is not None
        assert mapping.pos_field_path == "borrower.income_type"
        assert mapping.pos_field_value == "SELF_EMPLOYED"
        assert mapping.maps_to_doc_type == "profit_loss"
        assert mapping.confidence_weight == 95

    def test_mapping_links_to_rule(self, db: Session):
        """A mapping can reference a DocumentRequirementRule via maps_to_rule_id."""
        from database.models.document_intelligence import (
            POSDocumentMapping,
            DocumentRequirementRule,
        )

        rule = DocumentRequirementRule(
            rule_name="VA DD-214",
            category="special",
            doc_type="dd214",
            required_count=1,
            applies_to="BORROWER",
            priority="CRITICAL",
            is_active=True,
            sort_order=0,
        )
        db.add(rule)
        db.flush()

        mapping = POSDocumentMapping(
            pos_field_path="borrower.veteran_status",
            pos_field_value="YES",
            maps_to_doc_type="dd214",
            maps_to_rule_id=rule.id,
            confidence_weight=100,
            is_active=True,
        )
        db.add(mapping)
        db.flush()

        fetched = db.query(POSDocumentMapping).filter_by(id=mapping.id).one()
        assert fetched.maps_to_rule_id == rule.id

    def test_mapping_document_type_accuracy(self, db: Session):
        """Multiple POS field values should map to the correct doc types."""
        from database.models.document_intelligence import POSDocumentMapping

        mappings = [
            ("borrower.income_type", "W2_EMPLOYEE", "w2"),
            ("borrower.income_type", "SELF_EMPLOYED", "tax_returns"),
            ("borrower.property_type", "CONDO", "hoa_docs"),
            ("borrower.is_veteran", "true", "dd214"),
        ]

        for path, value, doc_type in mappings:
            db.add(POSDocumentMapping(
                pos_field_path=path,
                pos_field_value=value,
                maps_to_doc_type=doc_type,
                confidence_weight=90,
                is_active=True,
                organization_id=7770,
            ))
        db.flush()

        w2_mapping = (
            db.query(POSDocumentMapping)
            .filter_by(pos_field_value="W2_EMPLOYEE", organization_id=7770)
            .one()
        )
        assert w2_mapping.maps_to_doc_type == "w2"

        condo_mapping = (
            db.query(POSDocumentMapping)
            .filter_by(pos_field_value="CONDO", organization_id=7770)
            .one()
        )
        assert condo_mapping.maps_to_doc_type == "hoa_docs"


# =============================================================================
# 6. CallIntelDocumentNeed - Creation & Status
# =============================================================================

@pytest.mark.unit
class TestCallIntelDocumentNeedCreation:
    """Validate call intelligence document need detection."""

    def test_create_detected_need_from_transcript(self, db: Session):
        """A document need detected from a call transcript can be persisted."""
        from database.models.document_intelligence import CallIntelDocumentNeed

        need = CallIntelDocumentNeed(
            loan_id=500,
            lead_id=600,
            call_id=700,
            call_date=datetime.now(timezone.utc),
            detected_doc_type="employment_verification",
            detected_doc_description="Borrower mentioned changing jobs last month",
            detection_confidence=88,
            source_transcript_snippet="...I actually just started a new job two weeks ago...",
            keywords_matched=["new job", "started", "changed jobs"],
            status="DETECTED",
        )
        db.add(need)
        db.flush()

        assert need.id is not None
        assert need.detected_doc_type == "employment_verification"
        assert need.detection_confidence == 88
        assert need.status == "DETECTED"
        assert "new job" in need.keywords_matched


# =============================================================================
# 7. CallIntelDocumentNeed - Status Transitions
# =============================================================================

@pytest.mark.unit
class TestCallIntelStatusTransitions:
    """Validate the status lifecycle: DETECTED -> CONFIRMED -> REQUEST_CREATED
    and DETECTED -> DISMISSED."""

    def test_transition_detected_to_confirmed(self, db: Session):
        """A detected need can transition to CONFIRMED with user attribution."""
        from database.models.document_intelligence import CallIntelDocumentNeed

        need = CallIntelDocumentNeed(
            loan_id=510,
            call_id=710,
            detected_doc_type="bank_statements",
            detection_confidence=72,
            status="DETECTED",
        )
        db.add(need)
        db.flush()

        need.status = "CONFIRMED"
        need.confirmed_by = "lo@company.com"
        need.confirmed_at = datetime.now(timezone.utc)
        db.flush()

        fetched = db.query(CallIntelDocumentNeed).filter_by(id=need.id).one()
        assert fetched.status == "CONFIRMED"
        assert fetched.confirmed_by == "lo@company.com"
        assert fetched.confirmed_at is not None

    def test_transition_detected_to_dismissed(self, db: Session):
        """A detected need can be dismissed with a reason."""
        from database.models.document_intelligence import CallIntelDocumentNeed

        need = CallIntelDocumentNeed(
            loan_id=520,
            call_id=720,
            detected_doc_type="gift_letter",
            detection_confidence=45,
            status="DETECTED",
        )
        db.add(need)
        db.flush()

        need.status = "DISMISSED"
        need.dismissed_by = "processor@company.com"
        need.dismissed_at = datetime.now(timezone.utc)
        need.dismiss_reason = "False positive - borrower was discussing a different loan"
        db.flush()

        fetched = db.query(CallIntelDocumentNeed).filter_by(id=need.id).one()
        assert fetched.status == "DISMISSED"
        assert fetched.dismiss_reason is not None

    def test_transition_confirmed_to_request_created(self, db: Session):
        """A confirmed need can transition to REQUEST_CREATED with a linked request."""
        from database.models.document_intelligence import CallIntelDocumentNeed

        need = CallIntelDocumentNeed(
            loan_id=530,
            call_id=730,
            detected_doc_type="tax_returns",
            detection_confidence=91,
            status="CONFIRMED",
            confirmed_by="lo@company.com",
            confirmed_at=datetime.now(timezone.utc),
        )
        db.add(need)
        db.flush()

        need.status = "REQUEST_CREATED"
        need.linked_request_id = 9999
        db.flush()

        fetched = db.query(CallIntelDocumentNeed).filter_by(id=need.id).one()
        assert fetched.status == "REQUEST_CREATED"
        assert fetched.linked_request_id == 9999

    def test_all_valid_statuses_from_enum(self, db: Session):
        """CallIntelDocNeedStatus enum should define exactly 4 statuses."""
        from database.models.document_intelligence import CallIntelDocNeedStatus

        expected = {"DETECTED", "CONFIRMED", "DISMISSED", "REQUEST_CREATED"}
        actual = {s.value for s in CallIntelDocNeedStatus}
        assert actual == expected


# =============================================================================
# 8. Multi-Tenant Isolation
# =============================================================================

@pytest.mark.unit
class TestMultiTenantIsolation:
    """Validate that organization_id filtering correctly isolates tenants."""

    def test_classifications_filtered_by_org_id(self, db: Session):
        """Querying by organization_id should only return that org's records."""
        from database.models.document_intelligence import AIDocumentClassification

        for org_id in (1001, 1001, 1002, 1002, 1002):
            db.add(AIDocumentClassification(
                organization_id=org_id,
                document_id=org_id * 10,
                predicted_doc_type="w2",
                prediction_confidence=80,
            ))
        db.flush()

        org_1001 = (
            db.query(AIDocumentClassification)
            .filter_by(organization_id=1001)
            .all()
        )
        org_1002 = (
            db.query(AIDocumentClassification)
            .filter_by(organization_id=1002)
            .all()
        )

        assert len(org_1001) == 2
        assert len(org_1002) == 3
        assert all(c.organization_id == 1001 for c in org_1001)
        assert all(c.organization_id == 1002 for c in org_1002)

    def test_rules_filtered_by_org_id(self, db: Session):
        """Document requirement rules should be isolated per organization."""
        from database.models.document_intelligence import DocumentRequirementRule

        db.add(DocumentRequirementRule(
            organization_id=2001,
            rule_name="Org 2001 Rule",
            category="income",
            doc_type="w2",
            required_count=1,
            applies_to="BORROWER",
            priority="NORMAL",
            is_active=True,
            sort_order=0,
        ))
        db.add(DocumentRequirementRule(
            organization_id=2002,
            rule_name="Org 2002 Rule",
            category="income",
            doc_type="w2",
            required_count=1,
            applies_to="BORROWER",
            priority="NORMAL",
            is_active=True,
            sort_order=0,
        ))
        db.flush()

        org_2001_rules = (
            db.query(DocumentRequirementRule)
            .filter_by(organization_id=2001)
            .all()
        )
        assert len(org_2001_rules) == 1
        assert org_2001_rules[0].rule_name == "Org 2001 Rule"

    def test_call_intel_needs_filtered_by_org_id(self, db: Session):
        """Call intel document needs should be isolated per organization."""
        from database.models.document_intelligence import CallIntelDocumentNeed

        db.add(CallIntelDocumentNeed(
            organization_id=3001,
            loan_id=100,
            detected_doc_type="paystubs",
            detection_confidence=80,
            status="DETECTED",
        ))
        db.add(CallIntelDocumentNeed(
            organization_id=3002,
            loan_id=200,
            detected_doc_type="paystubs",
            detection_confidence=80,
            status="DETECTED",
        ))
        db.flush()

        org_3001 = (
            db.query(CallIntelDocumentNeed)
            .filter_by(organization_id=3001)
            .all()
        )
        assert len(org_3001) == 1
        assert org_3001[0].loan_id == 100


# =============================================================================
# 9. Confidence Threshold Validation
# =============================================================================

@pytest.mark.unit
class TestConfidenceThresholdValidation:
    """Validate confidence-based querying patterns."""

    def test_low_confidence_classifications_queryable(self, db: Session):
        """Classifications below a confidence threshold can be queried for review."""
        from database.models.document_intelligence import AIDocumentClassification

        org_id = 5000
        confidences = [95, 82, 68, 45, 30]
        for i, conf in enumerate(confidences):
            db.add(AIDocumentClassification(
                organization_id=org_id,
                document_id=5000 + i,
                predicted_doc_type="bank_statement",
                prediction_confidence=conf,
            ))
        db.flush()

        review_queue = (
            db.query(AIDocumentClassification)
            .filter(
                AIDocumentClassification.organization_id == org_id,
                AIDocumentClassification.prediction_confidence < 70,
                AIDocumentClassification.is_correct.is_(None),
            )
            .order_by(AIDocumentClassification.prediction_confidence.asc())
            .all()
        )

        assert len(review_queue) == 2
        assert review_queue[0].prediction_confidence == 30
        assert review_queue[1].prediction_confidence == 45

    def test_high_confidence_classifications_bypass_review(self, db: Session):
        """High-confidence classifications (>=90) should not appear in review queue."""
        from database.models.document_intelligence import AIDocumentClassification

        org_id = 5001
        db.add(AIDocumentClassification(
            organization_id=org_id,
            document_id=6001,
            predicted_doc_type="w2",
            prediction_confidence=97,
        ))
        db.add(AIDocumentClassification(
            organization_id=org_id,
            document_id=6002,
            predicted_doc_type="paystubs",
            prediction_confidence=91,
        ))
        db.flush()

        review_queue = (
            db.query(AIDocumentClassification)
            .filter(
                AIDocumentClassification.organization_id == org_id,
                AIDocumentClassification.prediction_confidence < 70,
                AIDocumentClassification.is_correct.is_(None),
            )
            .all()
        )

        assert len(review_queue) == 0


# =============================================================================
# 10. Batch Classification Tracking
# =============================================================================

@pytest.mark.unit
class TestBatchClassificationTracking:
    """Validate batch classification scenarios with model metadata."""

    def test_batch_classifications_share_model_identifier(self, db: Session):
        """All classifications in a batch should reference the same model version."""
        from database.models.document_intelligence import AIDocumentClassification

        model_version = "doc-classifier-v2.3"
        org_id = 6000
        doc_types = ["w2", "bank_statement", "tax_returns", "paystubs", "appraisal"]

        for i, dt in enumerate(doc_types):
            db.add(AIDocumentClassification(
                organization_id=org_id,
                document_id=7000 + i,
                predicted_doc_type=dt,
                prediction_confidence=85 + i,
                classification_model=model_version,
                classification_duration_ms=120 + i * 10,
            ))
        db.flush()

        batch = (
            db.query(AIDocumentClassification)
            .filter_by(organization_id=org_id, classification_model=model_version)
            .all()
        )

        assert len(batch) == 5
        assert all(c.classification_model == model_version for c in batch)
        assert all(c.classification_duration_ms is not None for c in batch)

    def test_batch_statistics_computable(self, db: Session):
        """Batch-level statistics (avg confidence, avg duration) can be computed."""
        from database.models.document_intelligence import AIDocumentClassification
        from sqlalchemy import func

        model_version = "doc-classifier-v2.4"
        org_id = 6001

        for i in range(4):
            db.add(AIDocumentClassification(
                organization_id=org_id,
                document_id=8000 + i,
                predicted_doc_type="w2",
                prediction_confidence=70 + i * 10,  # 70, 80, 90, 100
                classification_model=model_version,
                classification_duration_ms=100 + i * 50,  # 100, 150, 200, 250
            ))
        db.flush()

        stats = (
            db.query(
                func.avg(AIDocumentClassification.prediction_confidence).label("avg_conf"),
                func.avg(AIDocumentClassification.classification_duration_ms).label("avg_dur"),
                func.count(AIDocumentClassification.id).label("total"),
            )
            .filter_by(organization_id=org_id, classification_model=model_version)
            .one()
        )

        assert stats.total == 4
        assert stats.avg_conf == 85.0  # (70+80+90+100)/4
        assert stats.avg_dur == 175.0  # (100+150+200+250)/4


# =============================================================================
# 11. Enum Completeness
# =============================================================================

@pytest.mark.unit
class TestDocumentIntelligenceEnums:
    """Validate all enums in the document intelligence module."""

    def test_document_rule_category_values(self):
        """DocumentRuleCategory should have exactly 6 categories."""
        from database.models.document_intelligence import DocumentRuleCategory

        expected = {"identity", "income", "assets", "property", "credit", "special"}
        actual = {c.value for c in DocumentRuleCategory}
        assert actual == expected

    def test_document_rule_priority_values(self):
        """DocumentRulePriority should have 3 levels."""
        from database.models.document_intelligence import DocumentRulePriority

        expected = {"CRITICAL", "NORMAL", "OPTIONAL"}
        actual = {p.value for p in DocumentRulePriority}
        assert actual == expected

    def test_document_rule_applies_to_values(self):
        """DocumentRuleAppliesTo should have BORROWER, CO_BORROWER, BOTH."""
        from database.models.document_intelligence import DocumentRuleAppliesTo

        expected = {"BORROWER", "CO_BORROWER", "BOTH"}
        actual = {a.value for a in DocumentRuleAppliesTo}
        assert actual == expected

    def test_call_intel_doc_need_status_values(self):
        """CallIntelDocNeedStatus should have 4 statuses."""
        from database.models.document_intelligence import CallIntelDocNeedStatus

        expected = {"DETECTED", "CONFIRMED", "DISMISSED", "REQUEST_CREATED"}
        actual = {s.value for s in CallIntelDocNeedStatus}
        assert actual == expected


# =============================================================================
# 12. Inactive Rule Filtering
# =============================================================================

@pytest.mark.unit
class TestInactiveRuleFiltering:
    """Validate that inactive rules can be excluded from queries."""

    def test_active_only_query_excludes_deactivated_rules(self, db: Session):
        """Setting is_active=False should remove a rule from active queries."""
        from database.models.document_intelligence import DocumentRequirementRule

        org_id = 4000

        db.add(DocumentRequirementRule(
            organization_id=org_id,
            rule_name="Active Rule",
            category="income",
            doc_type="w2",
            required_count=1,
            applies_to="BORROWER",
            priority="NORMAL",
            is_active=True,
            sort_order=0,
        ))
        db.add(DocumentRequirementRule(
            organization_id=org_id,
            rule_name="Deprecated Rule",
            category="income",
            doc_type="1099",
            required_count=1,
            applies_to="BORROWER",
            priority="NORMAL",
            is_active=False,
            sort_order=0,
        ))
        db.flush()

        active_rules = (
            db.query(DocumentRequirementRule)
            .filter_by(organization_id=org_id, is_active=True)
            .all()
        )

        assert len(active_rules) == 1
        assert active_rules[0].rule_name == "Active Rule"

    def test_inactive_pos_mappings_excluded(self, db: Session):
        """Inactive POS mappings should be excluded from active queries."""
        from database.models.document_intelligence import POSDocumentMapping

        org_id = 4001

        db.add(POSDocumentMapping(
            organization_id=org_id,
            pos_field_path="borrower.income_type",
            pos_field_value="W2_EMPLOYEE",
            maps_to_doc_type="w2",
            confidence_weight=100,
            is_active=True,
        ))
        db.add(POSDocumentMapping(
            organization_id=org_id,
            pos_field_path="borrower.income_type",
            pos_field_value="RETIRED",
            maps_to_doc_type="retirement_statement",
            confidence_weight=80,
            is_active=False,
        ))
        db.flush()

        active_mappings = (
            db.query(POSDocumentMapping)
            .filter_by(organization_id=org_id, is_active=True)
            .all()
        )

        assert len(active_mappings) == 1
        assert active_mappings[0].maps_to_doc_type == "w2"
