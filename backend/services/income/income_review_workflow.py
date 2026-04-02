"""
Income Review Workflow Service

Manages the review and approval workflow for AI-calculated income:
1. Tracks confidence scores and review status
2. Routes for review based on confidence thresholds
3. Handles approvals, rejections, and revisions
4. Maintains complete audit trail
5. Auto-approves when confidence reaches 98%

Target: 98% confidence for auto-approval
"""

import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from .unified_income_calculator import (
    UnifiedIncomeType,
    ConfidenceLevel,
    IncomeCalculationResult,
)
from .ai_income_detection_service import DocumentDetectionResult

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class ReviewStatus(str, enum.Enum):
    """Status of income calculation review."""
    PENDING_AI = "PENDING_AI"              # Awaiting AI processing
    PENDING_REVIEW = "PENDING_REVIEW"       # Needs human review
    IN_REVIEW = "IN_REVIEW"                 # Currently being reviewed
    REVISION_REQUESTED = "REVISION_REQUESTED"  # Reviewer requested changes
    APPROVED = "APPROVED"                   # Approved for use
    REJECTED = "REJECTED"                   # Rejected, will not be used
    AUTO_APPROVED = "AUTO_APPROVED"         # Auto-approved (98%+ confidence)


class ReviewAction(str, enum.Enum):
    """Actions a reviewer can take."""
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_REVISION = "REQUEST_REVISION"
    OVERRIDE_VALUE = "OVERRIDE_VALUE"
    ADD_COMMENT = "ADD_COMMENT"
    REASSIGN = "REASSIGN"


class ConfidenceThreshold(int, enum.Enum):
    """Confidence thresholds for workflow routing."""
    AUTO_APPROVE = 98      # 98%+ = auto-approve
    QUICK_REVIEW = 90      # 90-97% = quick review (verify only)
    STANDARD_REVIEW = 80   # 80-89% = standard review
    DETAILED_REVIEW = 60   # 60-79% = detailed review required
    MANUAL_ENTRY = 0       # <60% = manual entry required


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ReviewHistoryEntry:
    """Single entry in review history."""
    action: ReviewAction
    performed_by: str
    performed_at: datetime
    previous_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    comment: Optional[str] = None
    confidence_at_action: int = 0


@dataclass
class IncomeReviewItem:
    """An income calculation pending or under review."""
    id: str
    loan_id: int
    borrower_id: int
    income_type: UnifiedIncomeType

    # Calculated values
    monthly_income: Decimal
    annual_income: Decimal
    calculation_method: str

    # Confidence
    confidence_score: int
    confidence_level: ConfidenceLevel
    field_confidences: Dict[str, int]

    # Status
    status: ReviewStatus
    assigned_reviewer: Optional[str] = None

    # History
    history: List[ReviewHistoryEntry] = field(default_factory=list)

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None

    # Source tracking
    source_documents: List[str] = field(default_factory=list)
    extraction_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "borrower_id": self.borrower_id,
            "income_type": self.income_type.value,
            "monthly_income": float(self.monthly_income),
            "annual_income": float(self.annual_income),
            "calculation_method": self.calculation_method,
            "confidence_score": self.confidence_score,
            "confidence_level": self.confidence_level.value,
            "field_confidences": self.field_confidences,
            "status": self.status.value,
            "assigned_reviewer": self.assigned_reviewer,
            "requires_review": self.status in [
                ReviewStatus.PENDING_REVIEW,
                ReviewStatus.REVISION_REQUESTED
            ],
            "is_approved": self.status in [
                ReviewStatus.APPROVED,
                ReviewStatus.AUTO_APPROVED
            ],
            "source_documents": self.source_documents,
            "extraction_warnings": self.extraction_warnings,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "history_count": len(self.history),
        }


@dataclass
class ReviewQueueSummary:
    """Summary of review queue status."""
    pending_review_count: int
    in_review_count: int
    revision_requested_count: int
    auto_approved_today: int
    approved_today: int
    rejected_today: int
    average_confidence: float
    oldest_pending_hours: float


# =============================================================================
# INCOME REVIEW WORKFLOW SERVICE
# =============================================================================

class IncomeReviewWorkflowService:
    """
    Service for managing income review workflow.

    Features:
    1. Routes items based on confidence thresholds
    2. Tracks review status and history
    3. Auto-approves high-confidence items
    4. Manages reviewer assignments
    5. Provides review queue analytics
    """

    def __init__(self, auto_approve_threshold: int = 98):
        self.auto_approve_threshold = auto_approve_threshold
        # In-memory storage for demo - would use database in production
        self._review_items: Dict[str, IncomeReviewItem] = {}

    def submit_for_review(
        self,
        loan_id: int,
        borrower_id: int,
        calculation_result: IncomeCalculationResult,
        detection_result: Optional[DocumentDetectionResult] = None,
        source_documents: Optional[List[str]] = None,
    ) -> IncomeReviewItem:
        """
        Submit an income calculation for review.

        Routes to appropriate queue based on confidence:
        - 98%+: Auto-approve
        - 90-97%: Quick review
        - 80-89%: Standard review
        - 60-79%: Detailed review
        - <60%: Manual entry required
        """
        import uuid
        item_id = str(uuid.uuid4())[:12].upper()

        # Determine confidence and field confidences
        confidence = calculation_result.confidence_score
        field_confidences = detection_result.extracted_fields if detection_result else {}

        # Convert extracted fields to confidence dict
        field_conf_dict = {}
        if detection_result:
            field_conf_dict = {
                f.field_name: f.confidence
                for f in detection_result.extracted_fields
            }

        # Determine initial status based on confidence
        if confidence >= self.auto_approve_threshold:
            status = ReviewStatus.AUTO_APPROVED
            logger.info(f"Income calculation {item_id} auto-approved with {confidence}% confidence")
        elif confidence >= ConfidenceThreshold.DETAILED_REVIEW.value:
            status = ReviewStatus.PENDING_REVIEW
        else:
            status = ReviewStatus.PENDING_AI  # Needs manual data entry

        # Collect warnings
        warnings = calculation_result.warnings.copy()
        if detection_result:
            warnings.extend(detection_result.warnings)

        item = IncomeReviewItem(
            id=item_id,
            loan_id=loan_id,
            borrower_id=borrower_id,
            income_type=calculation_result.income_type,
            monthly_income=calculation_result.monthly_income or Decimal("0"),
            annual_income=calculation_result.annual_income or Decimal("0"),
            calculation_method=calculation_result.calculation_method,
            confidence_score=confidence,
            confidence_level=calculation_result.confidence_level,
            field_confidences=field_conf_dict,
            status=status,
            source_documents=source_documents or [],
            extraction_warnings=warnings,
        )

        # Add initial history entry
        item.history.append(ReviewHistoryEntry(
            action=ReviewAction.ADD_COMMENT,
            performed_by="SYSTEM",
            performed_at=datetime.now(timezone.utc),
            comment=f"Submitted for review with {confidence}% confidence",
            confidence_at_action=confidence,
        ))

        if status == ReviewStatus.AUTO_APPROVED:
            item.history.append(ReviewHistoryEntry(
                action=ReviewAction.APPROVE,
                performed_by="AUTO_APPROVE_SYSTEM",
                performed_at=datetime.now(timezone.utc),
                comment=f"Auto-approved: confidence {confidence}% >= {self.auto_approve_threshold}% threshold",
                confidence_at_action=confidence,
            ))
            item.reviewed_at = datetime.now(timezone.utc)

        self._review_items[item_id] = item
        return item

    def get_review_item(self, item_id: str) -> Optional[IncomeReviewItem]:
        """Get a review item by ID."""
        return self._review_items.get(item_id)

    def get_pending_reviews(
        self,
        loan_id: Optional[int] = None,
        reviewer: Optional[str] = None,
        min_confidence: Optional[int] = None,
        max_confidence: Optional[int] = None,
    ) -> List[IncomeReviewItem]:
        """Get items pending review with optional filters."""
        pending_statuses = [
            ReviewStatus.PENDING_REVIEW,
            ReviewStatus.IN_REVIEW,
            ReviewStatus.REVISION_REQUESTED,
        ]

        items = [
            item for item in self._review_items.values()
            if item.status in pending_statuses
        ]

        if loan_id:
            items = [i for i in items if i.loan_id == loan_id]

        if reviewer:
            items = [i for i in items if i.assigned_reviewer == reviewer]

        if min_confidence is not None:
            items = [i for i in items if i.confidence_score >= min_confidence]

        if max_confidence is not None:
            items = [i for i in items if i.confidence_score <= max_confidence]

        # Sort by confidence (lower first - need more attention)
        items.sort(key=lambda x: x.confidence_score)

        return items

    def approve(
        self,
        item_id: str,
        reviewer: str,
        comment: Optional[str] = None,
        override_values: Optional[Dict[str, Any]] = None,
    ) -> IncomeReviewItem:
        """Approve an income calculation."""
        item = self._review_items.get(item_id)
        if not item:
            raise ValueError(f"Review item {item_id} not found")

        previous_value = None
        if override_values:
            previous_value = {
                "monthly_income": float(item.monthly_income),
                "annual_income": float(item.annual_income),
            }
            if "monthly_income" in override_values:
                item.monthly_income = Decimal(str(override_values["monthly_income"]))
            if "annual_income" in override_values:
                item.annual_income = Decimal(str(override_values["annual_income"]))

        item.status = ReviewStatus.APPROVED
        item.reviewed_at = datetime.now(timezone.utc)
        item.updated_at = datetime.now(timezone.utc)

        item.history.append(ReviewHistoryEntry(
            action=ReviewAction.APPROVE if not override_values else ReviewAction.OVERRIDE_VALUE,
            performed_by=reviewer,
            performed_at=datetime.now(timezone.utc),
            previous_value=previous_value,
            new_value=override_values,
            comment=comment,
            confidence_at_action=item.confidence_score,
        ))

        logger.info(f"Income calculation {item_id} approved by {reviewer}")
        return item

    def reject(
        self,
        item_id: str,
        reviewer: str,
        reason: str,
    ) -> IncomeReviewItem:
        """Reject an income calculation."""
        item = self._review_items.get(item_id)
        if not item:
            raise ValueError(f"Review item {item_id} not found")

        item.status = ReviewStatus.REJECTED
        item.reviewed_at = datetime.now(timezone.utc)
        item.updated_at = datetime.now(timezone.utc)

        item.history.append(ReviewHistoryEntry(
            action=ReviewAction.REJECT,
            performed_by=reviewer,
            performed_at=datetime.now(timezone.utc),
            comment=reason,
            confidence_at_action=item.confidence_score,
        ))

        logger.info(f"Income calculation {item_id} rejected by {reviewer}: {reason}")
        return item

    def request_revision(
        self,
        item_id: str,
        reviewer: str,
        revision_notes: str,
        required_fields: Optional[List[str]] = None,
    ) -> IncomeReviewItem:
        """Request revision on an income calculation."""
        item = self._review_items.get(item_id)
        if not item:
            raise ValueError(f"Review item {item_id} not found")

        item.status = ReviewStatus.REVISION_REQUESTED
        item.updated_at = datetime.now(timezone.utc)

        comment = f"Revision requested: {revision_notes}"
        if required_fields:
            comment += f"\nRequired fields: {', '.join(required_fields)}"

        item.history.append(ReviewHistoryEntry(
            action=ReviewAction.REQUEST_REVISION,
            performed_by=reviewer,
            performed_at=datetime.now(timezone.utc),
            comment=comment,
            confidence_at_action=item.confidence_score,
        ))

        logger.info(f"Revision requested for {item_id} by {reviewer}")
        return item

    def assign_reviewer(
        self,
        item_id: str,
        reviewer: str,
        assigned_by: str,
    ) -> IncomeReviewItem:
        """Assign a reviewer to an item."""
        item = self._review_items.get(item_id)
        if not item:
            raise ValueError(f"Review item {item_id} not found")

        previous_reviewer = item.assigned_reviewer
        item.assigned_reviewer = reviewer
        item.status = ReviewStatus.IN_REVIEW
        item.updated_at = datetime.now(timezone.utc)

        item.history.append(ReviewHistoryEntry(
            action=ReviewAction.REASSIGN,
            performed_by=assigned_by,
            performed_at=datetime.now(timezone.utc),
            previous_value={"reviewer": previous_reviewer},
            new_value={"reviewer": reviewer},
            comment=f"Assigned to {reviewer}",
            confidence_at_action=item.confidence_score,
        ))

        return item

    def update_confidence(
        self,
        item_id: str,
        new_confidence: int,
        updated_fields: Dict[str, int],
        reason: str,
    ) -> IncomeReviewItem:
        """
        Update confidence score after additional data entry or AI improvement.

        If confidence reaches threshold, triggers auto-approval.
        """
        item = self._review_items.get(item_id)
        if not item:
            raise ValueError(f"Review item {item_id} not found")

        previous_confidence = item.confidence_score
        item.confidence_score = new_confidence
        item.field_confidences.update(updated_fields)
        item.updated_at = datetime.now(timezone.utc)

        # Update confidence level
        if new_confidence >= 95:
            item.confidence_level = ConfidenceLevel.HIGH
        elif new_confidence >= 80:
            item.confidence_level = ConfidenceLevel.MEDIUM
        elif new_confidence >= 60:
            item.confidence_level = ConfidenceLevel.LOW
        else:
            item.confidence_level = ConfidenceLevel.MANUAL

        item.history.append(ReviewHistoryEntry(
            action=ReviewAction.ADD_COMMENT,
            performed_by="SYSTEM",
            performed_at=datetime.now(timezone.utc),
            previous_value={"confidence": previous_confidence},
            new_value={"confidence": new_confidence},
            comment=f"Confidence updated: {reason}",
            confidence_at_action=new_confidence,
        ))

        # Check for auto-approval
        if (
            new_confidence >= self.auto_approve_threshold
            and item.status not in [ReviewStatus.APPROVED, ReviewStatus.AUTO_APPROVED, ReviewStatus.REJECTED]
        ):
            item.status = ReviewStatus.AUTO_APPROVED
            item.reviewed_at = datetime.now(timezone.utc)
            item.history.append(ReviewHistoryEntry(
                action=ReviewAction.APPROVE,
                performed_by="AUTO_APPROVE_SYSTEM",
                performed_at=datetime.now(timezone.utc),
                comment=f"Auto-approved after confidence improved to {new_confidence}%",
                confidence_at_action=new_confidence,
            ))
            logger.info(f"Income calculation {item_id} auto-approved after confidence update to {new_confidence}%")

        return item

    def get_queue_summary(self) -> ReviewQueueSummary:
        """Get summary of review queue status."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        items = list(self._review_items.values())

        pending = [i for i in items if i.status == ReviewStatus.PENDING_REVIEW]
        in_review = [i for i in items if i.status == ReviewStatus.IN_REVIEW]
        revision = [i for i in items if i.status == ReviewStatus.REVISION_REQUESTED]

        auto_approved_today = len([
            i for i in items
            if i.status == ReviewStatus.AUTO_APPROVED
            and i.reviewed_at and i.reviewed_at >= today_start
        ])

        approved_today = len([
            i for i in items
            if i.status == ReviewStatus.APPROVED
            and i.reviewed_at and i.reviewed_at >= today_start
        ])

        rejected_today = len([
            i for i in items
            if i.status == ReviewStatus.REJECTED
            and i.reviewed_at and i.reviewed_at >= today_start
        ])

        # Calculate average confidence of pending items
        pending_items = pending + in_review + revision
        avg_confidence = (
            sum(i.confidence_score for i in pending_items) / len(pending_items)
            if pending_items else 0
        )

        # Find oldest pending
        oldest_hours = 0.0
        if pending:
            oldest = min(pending, key=lambda x: x.created_at)
            oldest_hours = (now - oldest.created_at).total_seconds() / 3600

        return ReviewQueueSummary(
            pending_review_count=len(pending),
            in_review_count=len(in_review),
            revision_requested_count=len(revision),
            auto_approved_today=auto_approved_today,
            approved_today=approved_today,
            rejected_today=rejected_today,
            average_confidence=round(avg_confidence, 1),
            oldest_pending_hours=round(oldest_hours, 1),
        )

    def get_review_history(self, item_id: str) -> List[Dict[str, Any]]:
        """Get complete review history for an item."""
        item = self._review_items.get(item_id)
        if not item:
            return []

        return [
            {
                "action": entry.action.value,
                "performed_by": entry.performed_by,
                "performed_at": entry.performed_at.isoformat(),
                "previous_value": entry.previous_value,
                "new_value": entry.new_value,
                "comment": entry.comment,
                "confidence_at_action": entry.confidence_at_action,
            }
            for entry in item.history
        ]

    def get_items_by_loan(self, loan_id: int) -> List[IncomeReviewItem]:
        """Get all review items for a loan."""
        return [
            item for item in self._review_items.values()
            if item.loan_id == loan_id
        ]

    def get_approved_income_for_loan(self, loan_id: int) -> List[IncomeReviewItem]:
        """Get all approved income items for a loan."""
        approved_statuses = [ReviewStatus.APPROVED, ReviewStatus.AUTO_APPROVED]
        return [
            item for item in self._review_items.values()
            if item.loan_id == loan_id and item.status in approved_statuses
        ]

    def calculate_total_qualifying_income(self, loan_id: int) -> Dict[str, Decimal]:
        """Calculate total qualifying income from approved items."""
        approved_items = self.get_approved_income_for_loan(loan_id)

        total_monthly = sum(item.monthly_income for item in approved_items)
        total_annual = sum(item.annual_income for item in approved_items)

        return {
            "total_monthly": total_monthly,
            "total_annual": total_annual,
            "item_count": len(approved_items),
            "by_type": {
                item.income_type.value: float(item.monthly_income)
                for item in approved_items
            }
        }


# =============================================================================
# REVIEW WORKFLOW ORCHESTRATOR
# =============================================================================

class IncomeReviewOrchestrator:
    """
    Orchestrates the complete income review workflow.

    Combines:
    - Document detection
    - Income calculation
    - Review workflow
    """

    def __init__(self):
        from .unified_income_calculator import get_unified_income_calculator
        from .ai_income_detection_service import get_ai_income_detection_service

        self.calculator = get_unified_income_calculator()
        self.detector = get_ai_income_detection_service()
        self.workflow = IncomeReviewWorkflowService()

    def process_document(
        self,
        loan_id: int,
        borrower_id: int,
        document_text: str,
        document_filename: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> IncomeReviewItem:
        """
        Process a document through the complete workflow.

        1. Detect document type and extract fields
        2. Calculate income based on detected type
        3. Submit for review or auto-approve
        """
        # Step 1: Detect document type
        detection_result = self.detector.detect_from_text(
            document_text,
            document_filename
        )

        logger.info(
            f"Detected {detection_result.document_type.value} "
            f"({detection_result.confidence}% confidence) - "
            f"suggested income type: {detection_result.suggested_income_type.value}"
        )

        # Step 2: Calculate income based on type
        # This would normally extract data from detection_result and call appropriate calculator
        # For now, create a placeholder result
        calculation_result = self._calculate_from_detection(detection_result)

        # Step 3: Submit for review
        review_item = self.workflow.submit_for_review(
            loan_id=loan_id,
            borrower_id=borrower_id,
            calculation_result=calculation_result,
            detection_result=detection_result,
            source_documents=[document_id] if document_id else [],
        )

        return review_item

    def _calculate_from_detection(
        self,
        detection: DocumentDetectionResult
    ) -> IncomeCalculationResult:
        """
        Calculate income from detection result.

        Maps extracted fields to appropriate calculator.
        """
        from .unified_income_calculator import (
            IncomeCalculationResult,
            CalculationStep,
            W2SalaryData,
            W2HourlyData,
        )

        income_type = detection.suggested_income_type
        field_values = {f.field_name: f.value for f in detection.extracted_fields}

        # Build appropriate data object and calculate
        # This is simplified - full implementation would handle all 14 types

        if income_type == UnifiedIncomeType.W2_SALARY:
            base_salary = field_values.get("gross_pay") or field_values.get("w2_box1") or Decimal("0")
            data = W2SalaryData(base_salary=base_salary)
            return self.calculator.calculate_w2_salary(data)

        elif income_type == UnifiedIncomeType.W2_HOURLY:
            hourly_rate = field_values.get("hourly_rate") or Decimal("0")
            data = W2HourlyData(hourly_rate=hourly_rate)
            return self.calculator.calculate_w2_hourly(data)

        # For unhandled types, return a basic result
        monthly = field_values.get("gross_pay") or Decimal("0")
        return IncomeCalculationResult(
            success=True,
            income_type=income_type,
            monthly_income=monthly,
            annual_income=monthly * Decimal("12"),
            calculation_method="EXTRACTED_AMOUNT",
            confidence_score=detection.confidence,
            confidence_level=detection._get_confidence_level(),
            warnings=detection.warnings,
        )

    def get_loan_income_status(self, loan_id: int) -> Dict[str, Any]:
        """Get complete income status for a loan."""
        items = self.workflow.get_items_by_loan(loan_id)
        totals = self.workflow.calculate_total_qualifying_income(loan_id)

        return {
            "loan_id": loan_id,
            "total_monthly_income": float(totals["total_monthly"]),
            "total_annual_income": float(totals["total_annual"]),
            "income_sources": [item.to_dict() for item in items],
            "approved_count": len([
                i for i in items
                if i.status in [ReviewStatus.APPROVED, ReviewStatus.AUTO_APPROVED]
            ]),
            "pending_count": len([
                i for i in items
                if i.status == ReviewStatus.PENDING_REVIEW
            ]),
            "all_approved": all(
                i.status in [ReviewStatus.APPROVED, ReviewStatus.AUTO_APPROVED]
                for i in items
            ) if items else False,
        }


# =============================================================================
# SINGLETON INSTANCES
# =============================================================================

_workflow_service: Optional[IncomeReviewWorkflowService] = None
_orchestrator: Optional[IncomeReviewOrchestrator] = None


def get_income_review_workflow() -> IncomeReviewWorkflowService:
    """Get singleton instance of IncomeReviewWorkflowService."""
    global _workflow_service
    if _workflow_service is None:
        _workflow_service = IncomeReviewWorkflowService()
    return _workflow_service


def get_income_review_orchestrator() -> IncomeReviewOrchestrator:
    """Get singleton instance of IncomeReviewOrchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = IncomeReviewOrchestrator()
    return _orchestrator
