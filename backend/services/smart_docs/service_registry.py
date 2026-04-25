"""
Smart Docs Service Registry

Central factory for all Smart Docs services with org-context injection.
Ensures every service created through the registry carries tenant context
(org_id, user_id) and can verify entity access before processing.

This solves the problem where services are stateless singletons receiving
db + loan_id but never verifying org_id. Agent tools call services without
org context, creating a multi-tenant isolation gap.

Usage:
    from services.smart_docs.service_registry import SmartDocsServiceRegistry

    registry = SmartDocsServiceRegistry(db=db, org_id=42, user_id=7)
    result = registry.bank_analyzer.analyze_statements(loan_id=100, borrower_id=5)
    # org_id is automatically verified before any data access

    # Access verification
    registry.verify_loan_access(loan_id=100)  # raises if loan not in org

    # Decision audit logging with auto-filled context
    registry.log_decision(
        loan_id=100,
        decision_type="document_review",
        entity_type="smart_document",
        entity_id=55,
        decision="approved",
        reasoning="All checks passed",
        new_state="approved",
    )
"""

import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from exceptions import TenantIsolationError

logger = logging.getLogger(__name__)


# =============================================================================
# ORG-AWARE SERVICE BASE CLASS
# =============================================================================

class OrgAwareService:
    """
    Base class for services that need tenant context.

    Provides org_id, user_id, and a helper to verify that a given entity
    belongs to the expected organization.

    Subclasses (or existing services wrapped via the registry) can call
    ``self._require_org_match(entity_org_id)`` to enforce tenant boundaries
    at the service layer, independent of any middleware.
    """

    def __init__(self, db: Session, org_id: int, user_id: Optional[int] = None):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    def _require_org_match(self, entity_org_id: int) -> None:
        """Raise TenantIsolationError if entity does not belong to this org.

        Args:
            entity_org_id: The organization_id found on the entity being accessed.

        Raises:
            TenantIsolationError: If entity_org_id does not match self.org_id.
        """
        if entity_org_id != self.org_id:
            raise TenantIsolationError(
                message=f"Entity belongs to org {entity_org_id}, not {self.org_id}",
                requesting_org_id=self.org_id,
                target_org_id=entity_org_id,
            )


# =============================================================================
# SERVICE REGISTRY
# =============================================================================

class SmartDocsServiceRegistry:
    """
    Central factory for all Smart Docs services with org-context injection.

    Creates services lazily and caches them for the lifetime of this registry
    instance (which should be scoped to a single request). Every service
    created through the registry inherits org_id and user_id context.

    Key design decisions:
    - Lazy initialization: services are only created when first accessed.
    - Per-request caching: repeated access returns the same instance.
    - Org verification: verify_loan_access / verify_document_access check
      entity ownership before any service operates on the entity.
    - Decision logging: log_decision() auto-fills org_id and user_id.

    Example:
        registry = SmartDocsServiceRegistry(db=session, org_id=42, user_id=7)

        # Verify before processing
        registry.verify_loan_access(loan_id=100)

        # Get service (lazily created, cached)
        result = registry.income_calculator.calculate_income(100, 5)

        # Same instance on repeat access
        assert registry.income_calculator is registry.income_calculator
    """

    def __init__(
        self,
        db: Session,
        org_id: int,
        user_id: Optional[int] = None,
        trace_id: Optional[str] = None,
    ):
        """
        Args:
            db: SQLAlchemy session for the current request.
            org_id: Organization ID for tenant isolation.
            user_id: Authenticated user ID (optional for system/cron contexts).
            trace_id: Distributed trace ID for log correlation. Auto-generated
                      if not provided.
        """
        if not org_id:
            raise ValueError("org_id is required for SmartDocsServiceRegistry")

        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.trace_id = trace_id or uuid.uuid4().hex[:16]

        # Internal cache for lazily-initialized service instances
        self._cache: Dict[str, Any] = {}

    # =========================================================================
    # SERVICE FACTORIES (lazy-initialized, cached per registry instance)
    # =========================================================================

    @property
    def classifier(self):
        """AI document classifier service (singleton, no db required)."""
        if "classifier" not in self._cache:
            from services.smart_docs.ai_classifier_service import get_ai_classifier_service
            self._cache["classifier"] = get_ai_classifier_service()
        return self._cache["classifier"]

    @property
    def reviewer(self):
        """AI document review service."""
        if "reviewer" not in self._cache:
            from services.smart_docs.ai_review_service import get_ai_review_service
            self._cache["reviewer"] = get_ai_review_service(self.db)
        return self._cache["reviewer"]

    @property
    def income_calculator(self):
        """Income calculator service."""
        if "income_calculator" not in self._cache:
            from services.smart_docs.income_calculator_service import get_income_calculator_service
            self._cache["income_calculator"] = get_income_calculator_service(self.db)
        return self._cache["income_calculator"]

    @property
    def bank_analyzer(self):
        """Bank statement analyzer service."""
        if "bank_analyzer" not in self._cache:
            from services.smart_docs.bank_statement_analyzer import get_bank_statement_analyzer
            self._cache["bank_analyzer"] = get_bank_statement_analyzer(self.db)
        return self._cache["bank_analyzer"]

    @property
    def fraud_detector(self):
        """Fraud detection service."""
        if "fraud_detector" not in self._cache:
            from services.smart_docs.fraud_detection_service import get_fraud_detection_service
            self._cache["fraud_detector"] = get_fraud_detection_service(self.db)
        return self._cache["fraud_detector"]

    @property
    def ocr(self):
        """Document OCR service (singleton, no db required)."""
        if "ocr" not in self._cache:
            from services.smart_docs.document_ocr_service import get_document_ocr_service
            self._cache["ocr"] = get_document_ocr_service()
        return self._cache["ocr"]

    @property
    def pos_analyzer(self):
        """POS (Point of Sale / application) analyzer service."""
        if "pos_analyzer" not in self._cache:
            from services.smart_docs.pos_analyzer_service import get_pos_analyzer_service
            self._cache["pos_analyzer"] = get_pos_analyzer_service(self.db)
        return self._cache["pos_analyzer"]

    @property
    def followup(self):
        """Follow-up automation service."""
        if "followup" not in self._cache:
            from services.smart_docs.followup_automation_service import get_followup_automation_service
            self._cache["followup"] = get_followup_automation_service(self.db)
        return self._cache["followup"]

    @property
    def esign(self):
        """E-signature envelope service."""
        if "esign" not in self._cache:
            from services.smart_docs.esignature_envelope_service import ESignatureEnvelopeService
            self._cache["esign"] = ESignatureEnvelopeService(self.db)
        return self._cache["esign"]

    @property
    def notification(self):
        """Smart Docs notification service."""
        if "notification" not in self._cache:
            from services.smart_docs.notification_service import SmartDocsNotificationService
            self._cache["notification"] = SmartDocsNotificationService(self.db)
        return self._cache["notification"]

    @property
    def validation(self):
        """Document validation engine (singleton, no db required)."""
        if "validation" not in self._cache:
            from services.smart_docs.document_validation_engine import get_document_validation_engine
            self._cache["validation"] = get_document_validation_engine()
        return self._cache["validation"]

    @property
    def tax_analyzer(self):
        """Tax return analyzer service."""
        if "tax_analyzer" not in self._cache:
            from services.smart_docs.tax_return_analyzer_service import get_tax_return_analyzer
            self._cache["tax_analyzer"] = get_tax_return_analyzer(self.db)
        return self._cache["tax_analyzer"]

    @property
    def w2_validator(self):
        """W2/Paystub cross-validator service."""
        if "w2_validator" not in self._cache:
            from services.smart_docs.w2_paystub_cross_validator import get_w2_paystub_cross_validator
            self._cache["w2_validator"] = get_w2_paystub_cross_validator(self.db)
        return self._cache["w2_validator"]

    @property
    def call_intel(self):
        """Call intelligence document extractor service."""
        if "call_intel" not in self._cache:
            from services.smart_docs.call_intel_extractor import get_call_intel_extractor
            self._cache["call_intel"] = get_call_intel_extractor(self.db)
        return self._cache["call_intel"]

    @property
    def pdf(self):
        """PDF generation service (singleton, no db required)."""
        if "pdf" not in self._cache:
            from services.smart_docs.pdf_generation_service import get_pdf_generation_service
            self._cache["pdf"] = get_pdf_generation_service()
        return self._cache["pdf"]

    @property
    def cache(self):
        """Document cache service (singleton, no db required)."""
        if "cache" not in self._cache:
            from services.smart_docs.document_cache_service import get_document_cache_service
            self._cache["cache"] = get_document_cache_service()
        return self._cache["cache"]

    @property
    def communication_analytics(self):
        """Communication analytics service (org-scoped)."""
        if "communication_analytics" not in self._cache:
            from services.smart_docs.communication_analytics_service import (
                CommunicationAnalyticsService,
            )
            self._cache["communication_analytics"] = CommunicationAnalyticsService(
                db=self.db, org_id=self.org_id,
            )
        return self._cache["communication_analytics"]

    @property
    def business_rules(self):
        """Business rules configuration service."""
        if "business_rules" not in self._cache:
            from services.smart_docs.business_rules_service import get_business_rules_service
            self._cache["business_rules"] = get_business_rules_service(self.db)
        return self._cache["business_rules"]

    @property
    def asset_depletion(self):
        """Asset depletion income calculator service (org-scoped)."""
        if "asset_depletion" not in self._cache:
            from services.smart_docs.income.asset_depletion_service import get_asset_depletion_service
            self._cache["asset_depletion"] = get_asset_depletion_service(
                db=self.db, org_id=self.org_id, user_id=self.user_id,
            )
        return self._cache["asset_depletion"]

    @property
    def splitter(self):
        """Document splitting service."""
        if "splitter" not in self._cache:
            from services.smart_docs.document_splitting_service import get_document_splitting_service
            self._cache["splitter"] = get_document_splitting_service(self.db)
        return self._cache["splitter"]

    @property
    def document_chat(self):
        """Document chat / Q&A service."""
        if "document_chat" not in self._cache:
            from services.smart_docs.document_chat_service import get_document_chat_service
            self._cache["document_chat"] = get_document_chat_service(
                db=self.db,
                org_id=self.org_id,
                user_id=self.user_id,
            )
        return self._cache["document_chat"]

    @property
    def needs_list_generator(self):
        """Needs list generator service."""
        if "needs_list_generator" not in self._cache:
            from services.smart_docs.needs_list_generator import NeedsListGenerator
            self._cache["needs_list_generator"] = NeedsListGenerator(self.db)
        return self._cache["needs_list_generator"]

    @property
    def merge_intelligence(self):
        """Merge intelligence service (org-scoped)."""
        if "merge_intelligence" not in self._cache:
            from services.smart_docs.merge_intelligence_service import MergeIntelligenceService
            self._cache["merge_intelligence"] = MergeIntelligenceService(
                db=self.db, org_id=self.org_id, user_id=self.user_id,
            )
        return self._cache["merge_intelligence"]

    @property
    def template_engine(self):
        """Template engine service."""
        if "template_engine" not in self._cache:
            from services.smart_docs.template_engine_service import TemplateEngineService
            self._cache["template_engine"] = TemplateEngineService(self.db)
        return self._cache["template_engine"]

    @property
    def date_extractor(self):
        """Date extractor service (singleton, no db required)."""
        if "date_extractor" not in self._cache:
            from services.smart_docs.date_extractor import DateExtractor
            self._cache["date_extractor"] = DateExtractor()
        return self._cache["date_extractor"]

    @property
    def document_comparison(self):
        """Document comparison service."""
        if "document_comparison" not in self._cache:
            from services.smart_docs.document_comparison_service import DocumentComparisonService
            self._cache["document_comparison"] = DocumentComparisonService(self.db)
        return self._cache["document_comparison"]

    @property
    def document_search(self):
        """Document search service (stateless, no db in constructor)."""
        if "document_search" not in self._cache:
            from services.smart_docs.document_search_service import DocumentSearchService
            self._cache["document_search"] = DocumentSearchService()
        return self._cache["document_search"]

    @property
    def document_staging(self):
        """Document staging service (org-scoped)."""
        if "document_staging" not in self._cache:
            from services.smart_docs.document_staging_service import DocumentStagingService
            self._cache["document_staging"] = DocumentStagingService(
                db=self.db, org_id=self.org_id,
            )
        return self._cache["document_staging"]

    @property
    def document_review_pipeline(self):
        """Document review pipeline service."""
        if "document_review_pipeline" not in self._cache:
            from services.smart_docs.document_review_pipeline import DocumentReviewPipeline
            self._cache["document_review_pipeline"] = DocumentReviewPipeline(self.db)
        return self._cache["document_review_pipeline"]

    @property
    def document_data_extractor(self):
        """Document data extractor service (singleton, no db required)."""
        if "document_data_extractor" not in self._cache:
            from services.smart_docs.document_data_extractor import DocumentDataExtractor
            self._cache["document_data_extractor"] = DocumentDataExtractor()
        return self._cache["document_data_extractor"]

    @property
    def ocr_enhancement(self):
        """OCR enhancement service (org-scoped)."""
        if "ocr_enhancement" not in self._cache:
            from services.smart_docs.ocr_enhancement_service import OCREnhancementService
            self._cache["ocr_enhancement"] = OCREnhancementService(org_id=self.org_id)
        return self._cache["ocr_enhancement"]

    @property
    def decision_audit(self):
        """Decision audit service (module-level functions, not a class).

        Returns the module itself so callers can call
        ``registry.decision_audit.log_decision(db, org_id, ...)``.
        For convenience, use ``registry.log_decision()`` instead.
        """
        if "decision_audit" not in self._cache:
            from services.smart_docs import decision_audit_service
            self._cache["decision_audit"] = decision_audit_service
        return self._cache["decision_audit"]

    # =========================================================================
    # ACCESS VERIFICATION
    # =========================================================================

    def verify_loan_access(self, loan_id: int) -> bool:
        """Verify that a loan belongs to this registry's organization.

        Args:
            loan_id: The loan ID to check.

        Returns:
            True if the loan belongs to org_id.

        Raises:
            HTTPException(404): If the loan does not exist or does not belong
                to this organization. We use 404 (not 403) to avoid leaking
                information about loans belonging to other orgs.
        """
        row = self.db.execute(
            text("SELECT organization_id FROM loans WHERE id = :loan_id"),
            {"loan_id": loan_id},
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Loan {loan_id} not found",
            )

        if row.organization_id != self.org_id:
            logger.warning(
                "Tenant isolation violation: org %s attempted to access loan %s "
                "belonging to org %s (trace_id=%s)",
                self.org_id, loan_id, row.organization_id, self.trace_id,
            )
            raise HTTPException(
                status_code=404,
                detail=f"Loan {loan_id} not found",
            )

        return True

    def verify_document_access(self, document_id: int) -> bool:
        """Verify that a document belongs to this registry's organization.

        Checks via the document's loan -> organization_id chain.

        Args:
            document_id: The smart_document ID to check.

        Returns:
            True if the document belongs to org_id.

        Raises:
            HTTPException(404): If the document does not exist or does not
                belong to this organization.
        """
        row = self.db.execute(
            text("""
                SELECT l.organization_id
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE sd.id = :document_id
            """),
            {"document_id": document_id},
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Document {document_id} not found",
            )

        if row.organization_id != self.org_id:
            logger.warning(
                "Tenant isolation violation: org %s attempted to access document %s "
                "belonging to org %s (trace_id=%s)",
                self.org_id, document_id, row.organization_id, self.trace_id,
            )
            raise HTTPException(
                status_code=404,
                detail=f"Document {document_id} not found",
            )

        return True

    # =========================================================================
    # DECISION AUDIT CONVENIENCE METHOD
    # =========================================================================

    def log_decision(
        self,
        loan_id: Optional[int] = None,
        decision_type: str = "document_review",
        entity_type: str = "smart_document",
        entity_id: int = 0,
        decision: str = "approved",
        reasoning: str = "",
        new_state: str = "",
        supporting_data: Optional[Dict[str, Any]] = None,
        maker_type: str = "system",
        maker_name: Optional[str] = None,
        previous_state: Optional[str] = None,
        document_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """Log a decision with org_id and user_id auto-filled from registry context.

        This is a convenience wrapper around
        ``decision_audit_service.log_decision()`` that removes the need to
        pass db, organization_id, and maker_id on every call.

        Args:
            loan_id: Related loan ID (nullable for org-level decisions).
            decision_type: Category of decision.
            entity_type: Model type being decided on.
            entity_id: ID of the entity being decided on.
            decision: The decision made.
            reasoning: Narrative explanation of why.
            new_state: Entity state after the decision.
            supporting_data: JSON-serializable evidence dict.
            maker_type: Who made the decision.
            maker_name: Display name for the decision maker.
            previous_state: Entity state before the decision.
            document_id: Related document ID if applicable.
            ip_address: Client IP for human decisions.
            user_agent: Client user-agent for human decisions.

        Returns:
            The created DecisionAuditLog record.
        """
        from services.smart_docs.decision_audit_service import log_decision as _log_decision

        # Enrich supporting_data with trace context
        enriched_data = dict(supporting_data or {})
        enriched_data["trace_id"] = self.trace_id

        return _log_decision(
            db=self.db,
            organization_id=self.org_id,
            loan_id=loan_id,
            decision_type=decision_type,
            entity_type=entity_type,
            entity_id=entity_id,
            decision=decision,
            reasoning=reasoning,
            supporting_data=enriched_data,
            maker_type=maker_type,
            maker_id=self.user_id,
            maker_name=maker_name,
            previous_state=previous_state,
            new_state=new_state,
            document_id=document_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    # =========================================================================
    # INTROSPECTION
    # =========================================================================

    @property
    def cached_services(self) -> list:
        """Return names of services that have been instantiated."""
        return list(self._cache.keys())

    def __repr__(self) -> str:
        return (
            f"SmartDocsServiceRegistry(org_id={self.org_id}, "
            f"user_id={self.user_id}, "
            f"trace_id={self.trace_id!r}, "
            f"cached={len(self._cache)})"
        )
