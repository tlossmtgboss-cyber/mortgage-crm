"""
Human Review Service for Call Intelligence

Manages low-confidence extractions that require human review.
Provides queue management, review submission, and integration
with the extraction pipeline.

Features:
- Automatic routing of low-confidence extractions to review queue
- Configurable confidence thresholds
- Review workflow (approve, reject, modify)
- Audit trail of review decisions
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .data_contracts import (
    ExtractedValue,
    ReviewQueueItem,
    ReviewDecision,
    ReviewStatus,
)
from .pii_utils import mask_pii_for_logging

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Default confidence threshold for routing to review
DEFAULT_REVIEW_THRESHOLD = 75.0

# Critical fields that always require review below higher threshold
CRITICAL_FIELDS = {
    "ssn_last_four",
    "date_of_birth",
    "annual_salary",
    "purchase_price",
    "has_bankruptcy",
    "has_foreclosure",
    "citizenship_status",
}
CRITICAL_FIELD_THRESHOLD = 85.0

# Maximum items to return in a single query
MAX_REVIEW_ITEMS = 100


class HumanReviewService:
    """
    Manage low-confidence extractions requiring human review.

    Usage:
        service = HumanReviewService(db_session)

        # Route extraction to review if needed
        if service.should_review(extraction):
            item = await service.queue_for_review(extraction, call_id, loan_id)

        # Get pending reviews
        items = await service.get_pending_reviews(loan_id=123)

        # Submit review decision
        result = await service.submit_review(
            review_id="abc123",
            decision=ReviewDecision(
                review_id="abc123",
                decision="approved",
                reviewer_id=1,
            ),
        )
    """

    REVIEW_THRESHOLD = DEFAULT_REVIEW_THRESHOLD

    def __init__(
        self,
        db_session: "Session",
        review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    ):
        """
        Initialize review service.

        Args:
            db_session: SQLAlchemy session (required)
            review_threshold: Confidence threshold for review routing
        """
        if db_session is None:
            raise ValueError("HumanReviewService requires a database session")

        self.db = db_session
        self.review_threshold = review_threshold

    def should_review(self, extraction: ExtractedValue) -> bool:
        """
        Determine if an extraction should be routed to human review.

        Args:
            extraction: The extracted value to check

        Returns:
            True if extraction should go to review queue
        """
        # Skip null values
        if extraction.value is None:
            return False

        # Check critical fields with higher threshold
        if extraction.field_name in CRITICAL_FIELDS:
            return extraction.confidence < CRITICAL_FIELD_THRESHOLD

        # Standard threshold check
        return extraction.confidence < self.review_threshold

    async def queue_for_review(
        self,
        extraction: ExtractedValue,
        call_id: str,
        loan_id: Optional[int] = None,
        extraction_type: str = "identity",
    ) -> ReviewQueueItem:
        """
        Add extraction to review queue.

        Args:
            extraction: The extracted value to review
            call_id: Call identifier
            loan_id: Associated loan ID
            extraction_type: Domain type (identity, property, etc.)

        Returns:
            Created ReviewQueueItem
        """
        review_id = f"rev_{uuid.uuid4().hex[:12]}"

        item = ReviewQueueItem(
            review_id=review_id,
            call_id=call_id,
            loan_id=loan_id,
            extraction_type=extraction_type,
            field_name=extraction.field_name,
            extracted_value=extraction.value,
            confidence_score=extraction.confidence,
            source_text=extraction.source_text,
            status="pending",
        )

        # Persist to database
        await self._save_review_item(item)

        logger.info(
            f"Queued for review: {extraction.field_name} "
            f"(confidence: {extraction.confidence:.1f}) - {review_id}"
        )

        return item

    async def queue_multiple_for_review(
        self,
        extractions: List[ExtractedValue],
        call_id: str,
        loan_id: Optional[int] = None,
        extraction_type_map: Optional[Dict[str, str]] = None,
    ) -> List[ReviewQueueItem]:
        """
        Queue multiple extractions for review.

        Args:
            extractions: List of extractions to potentially queue
            call_id: Call identifier
            loan_id: Associated loan ID
            extraction_type_map: Optional mapping of field_name to extraction_type

        Returns:
            List of created ReviewQueueItems
        """
        items = []
        extraction_type_map = extraction_type_map or {}

        for extraction in extractions:
            if self.should_review(extraction):
                extraction_type = extraction_type_map.get(
                    extraction.field_name, "identity"
                )
                item = await self.queue_for_review(
                    extraction, call_id, loan_id, extraction_type
                )
                items.append(item)

        return items

    async def get_pending_reviews(
        self,
        loan_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        extraction_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReviewQueueItem]:
        """
        Get extractions pending human review.

        Args:
            loan_id: Filter by loan ID
            organization_id: Filter by organization
            extraction_type: Filter by extraction type
            limit: Max items to return
            offset: Pagination offset

        Returns:
            List of pending ReviewQueueItems
        """
        from sqlalchemy import text

        # Build query with filters
        filters = ["review_status = 'pending'"]
        params = {"limit": min(limit, MAX_REVIEW_ITEMS), "offset": offset}

        if loan_id:
            filters.append("loan_id = :loan_id")
            params["loan_id"] = loan_id

        if organization_id:
            filters.append("organization_id = :org_id")
            params["org_id"] = organization_id

        if extraction_type:
            filters.append("extraction_type = :ext_type")
            params["ext_type"] = extraction_type

        where_clause = " AND ".join(filters)

        try:
            sql = """
                    SELECT
                        id, call_id, loan_id, extraction_type, field_name,
                        extracted_value, confidence_score, source_text,
                        review_status, reviewed_by, reviewed_at, reviewer_notes,
                        final_value, created_at
                    FROM extraction_review_queue
                    WHERE """ + where_clause + """
                    ORDER BY
                        CASE WHEN extraction_type IN ('compliance', 'financial') THEN 0 ELSE 1 END,
                        confidence_score ASC,
                        created_at ASC
                    LIMIT :limit OFFSET :offset
                """
            result = self.db.execute(text(sql), params).fetchall()

            items = []
            for row in result:
                items.append(ReviewQueueItem(
                    review_id=str(row[0]),
                    call_id=row[1],
                    loan_id=row[2],
                    extraction_type=row[3],
                    field_name=row[4],
                    extracted_value=row[5],
                    confidence_score=row[6],
                    source_text=row[7] or "",
                    status=row[8],
                    reviewed_by=row[9],
                    reviewed_at=row[10],
                    reviewer_notes=row[11],
                    final_value=row[12],
                    created_at=row[13],
                ))

            return items

        except Exception as e:
            safe_error = mask_pii_for_logging(str(e))
            logger.error(f"Failed to get pending reviews: {safe_error}")
            return []

    async def get_review_by_id(self, review_id: str) -> Optional[ReviewQueueItem]:
        """Get a specific review item by ID."""
        from sqlalchemy import text

        try:
            result = self.db.execute(
                text("""
                    SELECT
                        id, call_id, loan_id, extraction_type, field_name,
                        extracted_value, confidence_score, source_text,
                        review_status, reviewed_by, reviewed_at, reviewer_notes,
                        final_value, created_at
                    FROM extraction_review_queue
                    WHERE id = :review_id
                """),
                {"review_id": review_id}
            ).fetchone()

            if result:
                return ReviewQueueItem(
                    review_id=str(result[0]),
                    call_id=result[1],
                    loan_id=result[2],
                    extraction_type=result[3],
                    field_name=result[4],
                    extracted_value=result[5],
                    confidence_score=result[6],
                    source_text=result[7] or "",
                    status=result[8],
                    reviewed_by=result[9],
                    reviewed_at=result[10],
                    reviewer_notes=result[11],
                    final_value=result[12],
                    created_at=result[13],
                )

        except Exception as e:
            logger.warning(f"Failed to get review {review_id}: {e}")

        return None

    async def submit_review(
        self,
        review_id: str,
        decision: ReviewDecision,
    ) -> Dict[str, Any]:
        """
        Submit human review decision.

        Args:
            review_id: Review item ID
            decision: Review decision (approve, reject, modify)

        Returns:
            Dict with review result
        """
        from sqlalchemy import text

        # Validate decision
        if decision.decision not in ("approved", "rejected", "modified"):
            return {
                "success": False,
                "error": f"Invalid decision: {decision.decision}",
            }

        try:
            # Update review item
            self.db.execute(
                text("""
                    UPDATE extraction_review_queue
                    SET
                        review_status = :status,
                        reviewed_by = :reviewer_id,
                        reviewed_at = :reviewed_at,
                        reviewer_notes = :notes,
                        final_value = :final_value
                    WHERE id = :review_id
                """),
                {
                    "review_id": review_id,
                    "status": decision.decision,
                    "reviewer_id": decision.reviewer_id,
                    "reviewed_at": datetime.now(timezone.utc),
                    "notes": decision.notes,
                    "final_value": decision.final_value,
                }
            )
            self.db.commit()

            # If approved/modified, apply to loan data
            if decision.decision in ("approved", "modified"):
                item = await self.get_review_by_id(review_id)
                if item and item.loan_id:
                    await self._apply_reviewed_value(item, decision)

            logger.info(
                f"Review submitted: {review_id} -> {decision.decision} "
                f"by user {decision.reviewer_id}"
            )

            return {
                "success": True,
                "review_id": review_id,
                "decision": decision.decision,
            }

        except Exception as e:
            self.db.rollback()
            safe_error = mask_pii_for_logging(str(e))
            logger.error(f"Failed to submit review: {safe_error}")
            return {
                "success": False,
                "error": safe_error,
            }

    async def get_review_stats(
        self,
        loan_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get review queue statistics.

        Args:
            loan_id: Filter by loan
            organization_id: Filter by organization
            days: Look back period

        Returns:
            Dict with review statistics
        """
        from sqlalchemy import text
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        filters = ["created_at >= :cutoff"]
        params = {"cutoff": cutoff}

        if loan_id:
            filters.append("loan_id = :loan_id")
            params["loan_id"] = loan_id

        if organization_id:
            filters.append("organization_id = :org_id")
            params["org_id"] = organization_id

        where_clause = " AND ".join(filters)

        try:
            sql = """
                    SELECT
                        review_status,
                        COUNT(*) as count,
                        AVG(confidence_score) as avg_confidence
                    FROM extraction_review_queue
                    WHERE """ + where_clause + """
                    GROUP BY review_status
                """
            result = self.db.execute(text(sql), params).fetchall()

            stats = {
                "pending": 0,
                "approved": 0,
                "rejected": 0,
                "modified": 0,
                "total": 0,
                "avg_confidence": 0,
            }

            total_confidence = 0
            total_count = 0

            for row in result:
                status, count, avg_conf = row
                stats[status] = count
                stats["total"] += count
                if avg_conf:
                    total_confidence += avg_conf * count
                    total_count += count

            if total_count > 0:
                stats["avg_confidence"] = round(total_confidence / total_count, 1)

            return stats

        except Exception as e:
            logger.warning(f"Failed to get review stats: {e}")
            return {}

    async def _save_review_item(self, item: ReviewQueueItem) -> None:
        """Save review item to database."""
        from sqlalchemy import text
        import json

        try:
            self.db.execute(
                text("""
                    INSERT INTO extraction_review_queue
                    (id, call_id, loan_id, extraction_type, field_name,
                     extracted_value, confidence_score, source_text,
                     review_status, created_at)
                    VALUES
                    (:id, :call_id, :loan_id, :ext_type, :field_name,
                     :value, :confidence, :source_text,
                     :status, :created_at)
                """),
                {
                    "id": item.review_id,
                    "call_id": item.call_id,
                    "loan_id": item.loan_id,
                    "ext_type": item.extraction_type,
                    "field_name": item.field_name,
                    "value": json.dumps(item.extracted_value) if not isinstance(item.extracted_value, str) else item.extracted_value,
                    "confidence": item.confidence_score,
                    "source_text": item.source_text[:1000] if item.source_text else None,
                    "status": item.status,
                    "created_at": item.created_at,
                }
            )
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            safe_error = mask_pii_for_logging(str(e))
            logger.error(f"Failed to save review item: {safe_error}")
            raise

    async def _apply_reviewed_value(
        self,
        item: ReviewQueueItem,
        decision: ReviewDecision,
    ) -> None:
        """Apply reviewed value to loan data."""
        # This would integrate with your loan data model
        # For now, just log the action
        value = decision.final_value if decision.decision == "modified" else item.extracted_value
        logger.info(
            f"Applying reviewed value for loan {item.loan_id}: "
            f"{item.field_name} = {value}"
        )

        # TODO: Integrate with Application Engine or loan data model
        # Example:
        # loan_data_service.update_field(
        #     loan_id=item.loan_id,
        #     field=item.field_name,
        #     value=value,
        #     source="human_review",
        #     reviewer_id=decision.reviewer_id,
        # )


# =============================================================================
# Integration helper
# =============================================================================

def create_review_service(db_session: "Session") -> HumanReviewService:
    """
    Create review service instance.

    Args:
        db_session: SQLAlchemy session

    Returns:
        Configured HumanReviewService
    """
    return HumanReviewService(db_session)
