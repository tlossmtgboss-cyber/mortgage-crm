"""
Smart Docs SLA Service

Handles SLA calculation, tracking, and status determination:
- Calculate SLA due dates (3 business days)
- Determine SLA status (GOOD, AT_RISK, BREACHED)
- Superseding logic for expired documents
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from enum import Enum
from sqlalchemy.orm import Session

from models.smart_docs_models import DocumentRequest, RequestStatus

logger = logging.getLogger(__name__)


class SLAStatus(str, Enum):
    """SLA status levels."""
    GOOD = "GOOD"          # More than 24 hours remaining
    AT_RISK = "AT_RISK"    # Less than 24 hours remaining
    BREACHED = "BREACHED"  # Past due


# SLA configuration
SLA_BUSINESS_DAYS = 3  # 3 business days to respond


class SLAService:
    """Service for managing document request SLAs."""

    def __init__(self, db: Session):
        self.db = db

    def calculate_sla_due_date(self, created_at: datetime) -> datetime:
        """
        Calculate SLA due date (3 business days from creation).

        Business days = Monday-Friday (excludes weekends).
        This is a simplified calculation - for production, consider
        integrating a holiday calendar.

        Args:
            created_at: The timestamp when the request was created

        Returns:
            datetime: The SLA due date (end of business day)
        """
        current = created_at
        business_days_added = 0

        while business_days_added < SLA_BUSINESS_DAYS:
            current += timedelta(days=1)
            # Monday = 0, Sunday = 6
            if current.weekday() < 5:  # Monday-Friday
                business_days_added += 1

        # Set to end of business day (5 PM)
        return current.replace(hour=17, minute=0, second=0, microsecond=0)

    def get_sla_status(self, request: DocumentRequest) -> SLAStatus:
        """
        Determine SLA status for a document request.

        Args:
            request: The DocumentRequest to check

        Returns:
            SLAStatus: GOOD, AT_RISK, or BREACHED
        """
        if not request.sla_due_at:
            return SLAStatus.GOOD  # No SLA set

        # Only active, open requests can be breached
        if request.status not in [RequestStatus.OPEN, RequestStatus.PENDING_REVIEW]:
            return SLAStatus.GOOD  # Completed requests are not breached

        if not request.is_active:
            return SLAStatus.GOOD  # Superseded requests are not breached

        now = datetime.now(timezone.utc)
        time_remaining = request.sla_due_at - now

        if time_remaining.total_seconds() < 0:
            return SLAStatus.BREACHED
        elif time_remaining.total_seconds() < 24 * 3600:  # Less than 24 hours
            return SLAStatus.AT_RISK
        else:
            return SLAStatus.GOOD

    def get_client_sla_summary(self, loan_id: int) -> Dict[str, Any]:
        """
        Get SLA summary for a client (loan).

        Args:
            loan_id: The loan ID to get summary for

        Returns:
            dict with:
                - has_breach: bool
                - sla_status: worst status (BREACHED > AT_RISK > GOOD)
                - breached_count: number of breached requests
                - at_risk_count: number of at-risk requests
        """
        requests = self.db.query(DocumentRequest).filter(
            DocumentRequest.loan_id == loan_id,
            DocumentRequest.is_active == True,
            DocumentRequest.status.in_([RequestStatus.OPEN, RequestStatus.PENDING_REVIEW])
        ).all()

        breached_count = 0
        at_risk_count = 0

        for req in requests:
            status = self.get_sla_status(req)
            if status == SLAStatus.BREACHED:
                breached_count += 1
            elif status == SLAStatus.AT_RISK:
                at_risk_count += 1

        # Determine overall status (worst case)
        if breached_count > 0:
            overall_status = SLAStatus.BREACHED
        elif at_risk_count > 0:
            overall_status = SLAStatus.AT_RISK
        else:
            overall_status = SLAStatus.GOOD

        return {
            "has_breach": breached_count > 0,
            "sla_status": overall_status.value,
            "breached_count": breached_count,
            "at_risk_count": at_risk_count,
        }

    def supersede_request(
        self,
        old_request_id: int,
        new_request_id: int,
        reason: str = "Document expired"
    ) -> bool:
        """
        Mark an old request as superseded by a new one.

        This is used when a document expires and a new request is created.

        Args:
            old_request_id: The ID of the request being superseded
            new_request_id: The ID of the new replacement request
            reason: The reason for superseding (for logging)

        Returns:
            bool: True if successful, False if old request not found
        """
        old_request = self.db.query(DocumentRequest).filter(
            DocumentRequest.id == old_request_id
        ).first()

        if not old_request:
            return False

        old_request.is_active = False
        old_request.superseded_by = new_request_id
        self.db.commit()

        logger.info(
            f"Request {old_request_id} superseded by {new_request_id}: {reason}"
        )
        return True

    def set_sla_on_create(self, request: DocumentRequest) -> DocumentRequest:
        """
        Set SLA due date when creating a new request.

        Call this after creating a DocumentRequest to set the SLA.

        Args:
            request: The DocumentRequest to update

        Returns:
            DocumentRequest: The updated request with SLA set
        """
        if not request.sla_due_at:
            request.sla_due_at = self.calculate_sla_due_date(
                request.created_at or datetime.now(timezone.utc)
            )
        return request

    def get_breached_requests(self, loan_id: Optional[int] = None) -> list:
        """
        Get all breached document requests.

        Args:
            loan_id: Optional filter by loan

        Returns:
            List of breached DocumentRequest objects
        """
        now = datetime.now(timezone.utc)

        query = self.db.query(DocumentRequest).filter(
            DocumentRequest.is_active == True,
            DocumentRequest.status.in_([RequestStatus.OPEN, RequestStatus.PENDING_REVIEW]),
            DocumentRequest.sla_due_at < now
        )

        if loan_id:
            query = query.filter(DocumentRequest.loan_id == loan_id)

        return query.order_by(DocumentRequest.sla_due_at.asc()).all()

    def get_at_risk_requests(self, loan_id: Optional[int] = None) -> list:
        """
        Get all at-risk document requests (due within 24 hours).

        Args:
            loan_id: Optional filter by loan

        Returns:
            List of at-risk DocumentRequest objects
        """
        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(hours=24)

        query = self.db.query(DocumentRequest).filter(
            DocumentRequest.is_active == True,
            DocumentRequest.status.in_([RequestStatus.OPEN, RequestStatus.PENDING_REVIEW]),
            DocumentRequest.sla_due_at >= now,
            DocumentRequest.sla_due_at < tomorrow
        )

        if loan_id:
            query = query.filter(DocumentRequest.loan_id == loan_id)

        return query.order_by(DocumentRequest.sla_due_at.asc()).all()
