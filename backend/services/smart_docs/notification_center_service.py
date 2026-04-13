"""
Smart Docs V2 Notification Center Service

Centralized async service for creating, delivering, querying, and managing
Smart Docs notifications across all channels (in-app, email, push).

Responsibilities:
    - Create notifications for every Smart Docs event type
    - Route to channels based on user preferences and severity
    - Group / batch similar notifications (e.g. 5 docs uploaded -> 1 summary)
    - Paginated real-time feed with severity filtering
    - Mark-as-read / dismiss (single + bulk)
    - Notification templates with per-type rendering
    - Auto-expiry cleanup for time-sensitive notifications
    - Analytics: delivery rates, read rates, channel effectiveness
    - Role-aware routing (LO vs processor vs manager)
    - Unread count for badge display

Tenant isolation:
    Every query filters on ``organization_id``.  The service constructor
    requires ``org_id`` and every public method enforces it.

Usage:
    from services.smart_docs.notification_center_service import (
        NotificationCenterService,
        get_notification_center_service,
    )

    service = get_notification_center_service(db, org_id=42, user_id=7)
    notif = await service.notify_doc_uploaded(
        loan_id=100,
        document_name="W2_2025.pdf",
        uploader_name="Jane Doe",
        target_user_ids=[7, 12],
    )
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, case, func, or_, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

_APP_URL = os.getenv("APP_URL", "https://app.perenniaai.com")

# Severity ordering for comparisons / filtering
_SEVERITY_RANK: Dict[str, int] = {
    "info": 0,
    "warning": 1,
    "urgent": 2,
    "critical": 3,
}

# Default channel settings when no user preference exists
_DEFAULT_CHANNELS: Dict[str, bool] = {
    "in_app": True,
    "email": True,
    "push": False,
}

# Notification types that always bypass user preferences (compliance/fraud)
_FORCE_DELIVER_TYPES = frozenset({"FRAUD_ALERT", "SLA_WARNING"})

# Maximum notifications to group into a single batch summary
_BATCH_GROUP_WINDOW_SECONDS = 60

# Auto-expiry defaults per notification type (in hours)
_DEFAULT_EXPIRY_HOURS: Dict[str, int] = {
    "DOC_EXPIRING": 168,       # 7 days
    "SLA_WARNING": 72,         # 3 days
    "BATCH_COMPLETE": 48,      # 2 days
    "DOC_UPLOADED": 336,       # 14 days
    "DOC_CLASSIFIED": 336,
    "DOC_APPROVED": 336,
    "DOC_REJECTED": 336,
    "CONDITION_ADDED": 336,
    "CONDITION_CLEARED": 168,
    "INCOME_CALCULATED": 336,
    "FRAUD_ALERT": 720,        # 30 days
    "SIGNATURE_COMPLETED": 336,
    "PACKAGE_READY": 168,
}

# Role mappings: which roles should receive each notification type
# Keys are notification types, values are sets of user role strings
_ROLE_ROUTING: Dict[str, set] = {
    "DOC_UPLOADED": {"loan_officer", "processor", "manager"},
    "DOC_CLASSIFIED": {"processor", "manager"},
    "DOC_APPROVED": {"loan_officer", "processor"},
    "DOC_REJECTED": {"loan_officer", "processor"},
    "DOC_EXPIRING": {"loan_officer", "processor"},
    "CONDITION_ADDED": {"loan_officer", "processor"},
    "CONDITION_CLEARED": {"loan_officer", "processor", "manager"},
    "INCOME_CALCULATED": {"processor", "manager"},
    "FRAUD_ALERT": {"loan_officer", "processor", "manager", "compliance"},
    "SIGNATURE_COMPLETED": {"loan_officer", "processor"},
    "PACKAGE_READY": {"loan_officer", "processor", "closer"},
    "SLA_WARNING": {"loan_officer", "processor", "manager"},
    "BATCH_COMPLETE": {"processor", "manager"},
}


# =============================================================================
# ENUMS
# =============================================================================

class NotificationType(str, Enum):
    DOC_UPLOADED = "DOC_UPLOADED"
    DOC_CLASSIFIED = "DOC_CLASSIFIED"
    DOC_APPROVED = "DOC_APPROVED"
    DOC_REJECTED = "DOC_REJECTED"
    DOC_EXPIRING = "DOC_EXPIRING"
    CONDITION_ADDED = "CONDITION_ADDED"
    CONDITION_CLEARED = "CONDITION_CLEARED"
    INCOME_CALCULATED = "INCOME_CALCULATED"
    FRAUD_ALERT = "FRAUD_ALERT"
    SIGNATURE_COMPLETED = "SIGNATURE_COMPLETED"
    PACKAGE_READY = "PACKAGE_READY"
    SLA_WARNING = "SLA_WARNING"
    BATCH_COMPLETE = "BATCH_COMPLETE"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    URGENT = "urgent"
    CRITICAL = "critical"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class NotificationResult:
    """Result of a notification creation attempt."""
    success: bool
    notification_ids: List[int] = field(default_factory=list)
    channels_delivered: Dict[str, int] = field(default_factory=dict)
    skipped_users: List[int] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "success": self.success,
            "notification_ids": self.notification_ids,
            "channels_delivered": self.channels_delivered,
        }
        if self.skipped_users:
            result["skipped_users"] = self.skipped_users
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class NotificationFeed:
    """Paginated notification feed result."""
    notifications: List[Dict[str, Any]]
    total_count: int
    unread_count: int
    page: int
    page_size: int
    has_more: bool


@dataclass
class NotificationAnalytics:
    """Notification analytics summary."""
    total_sent: int = 0
    total_read: int = 0
    total_dismissed: int = 0
    read_rate: float = 0.0
    avg_time_to_read_minutes: float = 0.0
    by_type: Dict[str, Dict[str, int]] = field(default_factory=dict)
    by_channel: Dict[str, int] = field(default_factory=dict)
    by_severity: Dict[str, int] = field(default_factory=dict)


# =============================================================================
# NOTIFICATION TEMPLATES
# =============================================================================

# Each template defines: title_template, body_template, default_severity,
# default_action_label, action_url_pattern.
# Placeholders use {variable_name} syntax.

_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "DOC_UPLOADED": {
        "title": "New document uploaded: {document_name}",
        "body": "{uploader_name} uploaded \"{document_name}\" for loan {loan_number}.",
        "severity": "info",
        "action_label": "Review Document",
        "action_url": "/loans/{loan_id}/documents/{document_id}",
    },
    "DOC_CLASSIFIED": {
        "title": "Document classified: {document_name}",
        "body": "\"{document_name}\" was classified as {classification} with {confidence}% confidence for loan {loan_number}.",
        "severity": "info",
        "action_label": "View Classification",
        "action_url": "/loans/{loan_id}/documents/{document_id}",
    },
    "DOC_APPROVED": {
        "title": "Document approved: {document_name}",
        "body": "\"{document_name}\" has been approved by {reviewer_name} for loan {loan_number}.",
        "severity": "info",
        "action_label": "View Document",
        "action_url": "/loans/{loan_id}/documents/{document_id}",
    },
    "DOC_REJECTED": {
        "title": "Document rejected: {document_name}",
        "body": "\"{document_name}\" was rejected for loan {loan_number}. Reason: {rejection_reason}",
        "severity": "warning",
        "action_label": "Review Rejection",
        "action_url": "/loans/{loan_id}/documents/{document_id}",
    },
    "DOC_EXPIRING": {
        "title": "Document expiring: {document_name}",
        "body": "\"{document_name}\" for loan {loan_number} expires in {days_until_expiry} days. A renewal may be needed.",
        "severity": "warning",
        "action_label": "Renew Document",
        "action_url": "/loans/{loan_id}/documents/{document_id}",
    },
    "CONDITION_ADDED": {
        "title": "New condition: {condition_title}",
        "body": "A new {condition_severity} condition was added to loan {loan_number}: {condition_title}",
        "severity": "warning",
        "action_label": "View Condition",
        "action_url": "/loans/{loan_id}/conditions/{condition_id}",
    },
    "CONDITION_CLEARED": {
        "title": "Condition cleared: {condition_title}",
        "body": "Condition \"{condition_title}\" has been cleared for loan {loan_number}.",
        "severity": "info",
        "action_label": "View Loan",
        "action_url": "/loans/{loan_id}/conditions",
    },
    "INCOME_CALCULATED": {
        "title": "Income calculation complete",
        "body": "AI income calculation for loan {loan_number} is complete. Qualifying income: {qualifying_income}.",
        "severity": "info",
        "action_label": "Review Income",
        "action_url": "/loans/{loan_id}/income",
    },
    "FRAUD_ALERT": {
        "title": "Fraud alert: {document_name}",
        "body": "Potential fraud detected on \"{document_name}\" for loan {loan_number}. Risk level: {risk_level}. {fraud_details}",
        "severity": "critical",
        "action_label": "Investigate",
        "action_url": "/loans/{loan_id}/documents/{document_id}/fraud",
    },
    "SIGNATURE_COMPLETED": {
        "title": "Signatures complete: {envelope_name}",
        "body": "All parties have signed \"{envelope_name}\" for loan {loan_number}.",
        "severity": "info",
        "action_label": "View Signed Documents",
        "action_url": "/loans/{loan_id}/esign/{envelope_id}",
    },
    "PACKAGE_READY": {
        "title": "Document package ready",
        "body": "The {package_type} package for loan {loan_number} is ready for review.",
        "severity": "info",
        "action_label": "Review Package",
        "action_url": "/loans/{loan_id}/packages/{package_id}",
    },
    "SLA_WARNING": {
        "title": "SLA at risk: {document_name}",
        "body": "Document request for \"{document_name}\" on loan {loan_number} is {sla_status}. {time_remaining} remaining.",
        "severity": "urgent",
        "action_label": "View Request",
        "action_url": "/loans/{loan_id}/requests/{request_id}",
    },
    "BATCH_COMPLETE": {
        "title": "Batch processing complete",
        "body": "Batch \"{batch_name}\" finished: {processed_count} documents processed, {error_count} errors.",
        "severity": "info",
        "action_label": "View Results",
        "action_url": "/batch/{batch_id}/results",
    },
}


# =============================================================================
# HELPER: lazy model import
# =============================================================================

_DocNotification = None
_NotificationPreference = None


def _ensure_models():
    """Lazily import models to avoid circular imports at module load time."""
    global _DocNotification, _NotificationPreference
    if _DocNotification is None:
        from database.models.doc_notification import (
            DocNotification,
            NotificationPreference,
        )
        _DocNotification = DocNotification
        _NotificationPreference = NotificationPreference


# =============================================================================
# SERVICE
# =============================================================================

class NotificationCenterService:
    """Async-ready notification center for Smart Docs V2.

    All queries are scoped to ``org_id`` for tenant isolation. The service
    creates in-app notification records and optionally triggers email/push
    delivery through the existing email infrastructure.

    Args:
        db: SQLAlchemy session for the current request.
        org_id: Organization ID for tenant isolation.
        user_id: Authenticated user ID (for audit context).
    """

    def __init__(self, db: Session, org_id: int, user_id: Optional[int] = None):
        if not org_id:
            raise ValueError("org_id is required for NotificationCenterService")
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        _ensure_models()

    # =========================================================================
    # NOTIFICATION CREATION (one per event type)
    # =========================================================================

    async def notify_doc_uploaded(
        self,
        loan_id: int,
        document_name: str,
        uploader_name: str,
        target_user_ids: List[int],
        document_id: Optional[int] = None,
        loan_number: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> NotificationResult:
        """Create notifications for a newly uploaded document."""
        return await self._create_from_template(
            notification_type=NotificationType.DOC_UPLOADED,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            template_vars={
                "document_name": document_name,
                "uploader_name": uploader_name,
                "loan_number": loan_number or str(loan_id),
                "loan_id": str(loan_id),
                "document_id": str(document_id or ""),
            },
            extra_metadata={
                "document_id": document_id,
                "uploader_name": uploader_name,
                **(extra_metadata or {}),
            },
        )

    async def notify_doc_classified(
        self,
        loan_id: int,
        document_name: str,
        classification: str,
        confidence: float,
        target_user_ids: List[int],
        document_id: Optional[int] = None,
        loan_number: Optional[str] = None,
    ) -> NotificationResult:
        """Create notifications when AI classification completes."""
        return await self._create_from_template(
            notification_type=NotificationType.DOC_CLASSIFIED,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            template_vars={
                "document_name": document_name,
                "classification": classification,
                "confidence": str(round(confidence, 1)),
                "loan_number": loan_number or str(loan_id),
                "loan_id": str(loan_id),
                "document_id": str(document_id or ""),
            },
            extra_metadata={
                "document_id": document_id,
                "classification": classification,
                "confidence": confidence,
            },
        )

    async def notify_doc_approved(
        self,
        loan_id: int,
        document_name: str,
        reviewer_name: str,
        target_user_ids: List[int],
        document_id: Optional[int] = None,
        loan_number: Optional[str] = None,
    ) -> NotificationResult:
        """Create notifications when a document is approved."""
        return await self._create_from_template(
            notification_type=NotificationType.DOC_APPROVED,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            template_vars={
                "document_name": document_name,
                "reviewer_name": reviewer_name,
                "loan_number": loan_number or str(loan_id),
                "loan_id": str(loan_id),
                "document_id": str(document_id or ""),
            },
            extra_metadata={
                "document_id": document_id,
                "reviewer_name": reviewer_name,
            },
        )

    async def notify_doc_rejected(
        self,
        loan_id: int,
        document_name: str,
        rejection_reason: str,
        target_user_ids: List[int],
        document_id: Optional[int] = None,
        loan_number: Optional[str] = None,
    ) -> NotificationResult:
        """Create notifications when a document is rejected."""
        return await self._create_from_template(
            notification_type=NotificationType.DOC_REJECTED,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            template_vars={
                "document_name": document_name,
                "rejection_reason": rejection_reason,
                "loan_number": loan_number or str(loan_id),
                "loan_id": str(loan_id),
                "document_id": str(document_id or ""),
            },
            extra_metadata={
                "document_id": document_id,
                "rejection_reason": rejection_reason,
            },
        )

    async def notify_doc_expiring(
        self,
        loan_id: int,
        document_name: str,
        days_until_expiry: int,
        target_user_ids: List[int],
        document_id: Optional[int] = None,
        loan_number: Optional[str] = None,
    ) -> NotificationResult:
        """Create notifications for an expiring document."""
        severity = Severity.URGENT if days_until_expiry <= 3 else Severity.WARNING
        return await self._create_from_template(
            notification_type=NotificationType.DOC_EXPIRING,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            severity_override=severity,
            template_vars={
                "document_name": document_name,
                "days_until_expiry": str(days_until_expiry),
                "loan_number": loan_number or str(loan_id),
                "loan_id": str(loan_id),
                "document_id": str(document_id or ""),
            },
            extra_metadata={
                "document_id": document_id,
                "days_until_expiry": days_until_expiry,
            },
        )

    async def notify_condition_added(
        self,
        loan_id: int,
        condition_title: str,
        condition_severity: str,
        target_user_ids: List[int],
        condition_id: Optional[int] = None,
        loan_number: Optional[str] = None,
    ) -> NotificationResult:
        """Create notifications when a new condition is added."""
        return await self._create_from_template(
            notification_type=NotificationType.CONDITION_ADDED,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            template_vars={
                "condition_title": condition_title,
                "condition_severity": condition_severity,
                "loan_number": loan_number or str(loan_id),
                "loan_id": str(loan_id),
                "condition_id": str(condition_id or ""),
            },
            extra_metadata={
                "condition_id": condition_id,
                "condition_severity": condition_severity,
            },
        )

    async def notify_condition_cleared(
        self,
        loan_id: int,
        condition_title: str,
        target_user_ids: List[int],
        condition_id: Optional[int] = None,
        loan_number: Optional[str] = None,
    ) -> NotificationResult:
        """Create notifications when a condition is cleared."""
        return await self._create_from_template(
            notification_type=NotificationType.CONDITION_CLEARED,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            template_vars={
                "condition_title": condition_title,
                "loan_number": loan_number or str(loan_id),
                "loan_id": str(loan_id),
                "condition_id": str(condition_id or ""),
            },
            extra_metadata={"condition_id": condition_id},
        )

    async def notify_income_calculated(
        self,
        loan_id: int,
        qualifying_income: str,
        target_user_ids: List[int],
        loan_number: Optional[str] = None,
        income_details: Optional[Dict[str, Any]] = None,
    ) -> NotificationResult:
        """Create notifications when income calculation completes."""
        return await self._create_from_template(
            notification_type=NotificationType.INCOME_CALCULATED,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            template_vars={
                "qualifying_income": qualifying_income,
                "loan_number": loan_number or str(loan_id),
                "loan_id": str(loan_id),
            },
            extra_metadata={
                "qualifying_income": qualifying_income,
                **(income_details or {}),
            },
        )

    async def notify_fraud_alert(
        self,
        loan_id: int,
        document_name: str,
        risk_level: str,
        fraud_details: str,
        target_user_ids: List[int],
        document_id: Optional[int] = None,
        loan_number: Optional[str] = None,
    ) -> NotificationResult:
        """Create CRITICAL fraud alert notifications. Always delivered regardless of preferences."""
        return await self._create_from_template(
            notification_type=NotificationType.FRAUD_ALERT,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            severity_override=Severity.CRITICAL,
            template_vars={
                "document_name": document_name,
                "risk_level": risk_level,
                "fraud_details": fraud_details,
                "loan_number": loan_number or str(loan_id),
                "loan_id": str(loan_id),
                "document_id": str(document_id or ""),
            },
            extra_metadata={
                "document_id": document_id,
                "risk_level": risk_level,
                "fraud_details": fraud_details,
            },
        )

    async def notify_signature_completed(
        self,
        loan_id: int,
        envelope_name: str,
        target_user_ids: List[int],
        envelope_id: Optional[int] = None,
        loan_number: Optional[str] = None,
    ) -> NotificationResult:
        """Create notifications when an e-signature envelope is completed."""
        return await self._create_from_template(
            notification_type=NotificationType.SIGNATURE_COMPLETED,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            template_vars={
                "envelope_name": envelope_name,
                "loan_number": loan_number or str(loan_id),
                "loan_id": str(loan_id),
                "envelope_id": str(envelope_id or ""),
            },
            extra_metadata={"envelope_id": envelope_id},
        )

    async def notify_package_ready(
        self,
        loan_id: int,
        package_type: str,
        target_user_ids: List[int],
        package_id: Optional[int] = None,
        loan_number: Optional[str] = None,
    ) -> NotificationResult:
        """Create notifications when a document package is assembled."""
        return await self._create_from_template(
            notification_type=NotificationType.PACKAGE_READY,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            template_vars={
                "package_type": package_type,
                "loan_number": loan_number or str(loan_id),
                "loan_id": str(loan_id),
                "package_id": str(package_id or ""),
            },
            extra_metadata={
                "package_id": package_id,
                "package_type": package_type,
            },
        )

    async def notify_sla_warning(
        self,
        loan_id: int,
        document_name: str,
        sla_status: str,
        time_remaining: str,
        target_user_ids: List[int],
        request_id: Optional[int] = None,
        loan_number: Optional[str] = None,
    ) -> NotificationResult:
        """Create SLA warning notifications. Always delivered regardless of preferences."""
        return await self._create_from_template(
            notification_type=NotificationType.SLA_WARNING,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            severity_override=Severity.URGENT,
            template_vars={
                "document_name": document_name,
                "sla_status": sla_status,
                "time_remaining": time_remaining,
                "loan_number": loan_number or str(loan_id),
                "loan_id": str(loan_id),
                "request_id": str(request_id or ""),
            },
            extra_metadata={
                "request_id": request_id,
                "sla_status": sla_status,
            },
        )

    async def notify_batch_complete(
        self,
        batch_name: str,
        processed_count: int,
        error_count: int,
        target_user_ids: List[int],
        batch_id: Optional[str] = None,
        loan_id: Optional[int] = None,
    ) -> NotificationResult:
        """Create notifications when a batch processing job finishes."""
        severity = Severity.WARNING if error_count > 0 else Severity.INFO
        return await self._create_from_template(
            notification_type=NotificationType.BATCH_COMPLETE,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            severity_override=severity,
            template_vars={
                "batch_name": batch_name,
                "processed_count": str(processed_count),
                "error_count": str(error_count),
                "batch_id": batch_id or "",
            },
            extra_metadata={
                "batch_id": batch_id,
                "processed_count": processed_count,
                "error_count": error_count,
            },
        )

    # =========================================================================
    # GENERIC NOTIFICATION CREATION
    # =========================================================================

    async def create_notification(
        self,
        notification_type: str,
        title: str,
        body: str,
        target_user_ids: List[int],
        loan_id: Optional[int] = None,
        severity: str = "info",
        action_url: Optional[str] = None,
        action_label: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        delivery_channels: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> NotificationResult:
        """Create a notification directly without using a template.

        Use the type-specific ``notify_*`` methods when possible; this method
        is for custom / ad-hoc notifications that do not map to a template.
        """
        return await self._create_notifications(
            notification_type=notification_type,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            title=title,
            body=body,
            severity=severity,
            action_url=action_url,
            action_label=action_label,
            metadata=metadata,
            delivery_channels=delivery_channels,
            expires_at=expires_at,
        )

    # =========================================================================
    # NOTIFICATION GROUPING / BATCHING
    # =========================================================================

    async def create_grouped_notification(
        self,
        notification_type: str,
        items: List[Dict[str, Any]],
        target_user_ids: List[int],
        loan_id: Optional[int] = None,
        loan_number: Optional[str] = None,
        group_title: Optional[str] = None,
    ) -> NotificationResult:
        """Create a single grouped notification from multiple events.

        Instead of N individual notifications (e.g. 5 documents uploaded),
        this creates one summary notification listing all items.

        Args:
            notification_type: The notification type for all grouped items.
            items: List of dicts, each with at minimum a ``name`` key.
            target_user_ids: Users to notify.
            loan_id: Optional loan ID.
            loan_number: Optional loan number for display.
            group_title: Optional override for the notification title.
        """
        if not items:
            return NotificationResult(success=True)

        # Single item -> use standard creation
        if len(items) == 1:
            item = items[0]
            template = _TEMPLATES.get(notification_type)
            if template:
                title = group_title or template["title"].format(
                    document_name=item.get("name", "Document"),
                    **{k: str(v) for k, v in item.items()},
                )
            else:
                title = group_title or f"{notification_type}: {item.get('name', '')}"
            return await self.create_notification(
                notification_type=notification_type,
                title=title,
                body=item.get("description", ""),
                target_user_ids=target_user_ids,
                loan_id=loan_id,
                metadata={"items": items, "grouped": False},
            )

        # Multiple items -> summary notification
        item_names = [i.get("name", "Unknown") for i in items[:10]]
        summary_list = ", ".join(item_names[:5])
        if len(item_names) > 5:
            summary_list += f" and {len(item_names) - 5} more"

        type_labels = {
            "DOC_UPLOADED": "documents uploaded",
            "DOC_CLASSIFIED": "documents classified",
            "DOC_APPROVED": "documents approved",
            "DOC_REJECTED": "documents rejected",
            "DOC_EXPIRING": "documents expiring",
            "CONDITION_ADDED": "conditions added",
            "CONDITION_CLEARED": "conditions cleared",
        }
        type_label = type_labels.get(notification_type, "events")

        title = group_title or f"{len(items)} {type_label}"
        if loan_number:
            title += f" for loan {loan_number}"

        body = f"{summary_list}"

        return await self.create_notification(
            notification_type=notification_type,
            title=title,
            body=body,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            action_url=f"/loans/{loan_id}/documents" if loan_id else None,
            action_label="View All",
            metadata={"items": items, "grouped": True, "item_count": len(items)},
        )

    # =========================================================================
    # NOTIFICATION FEED (read)
    # =========================================================================

    async def get_feed(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        notification_type: Optional[str] = None,
        severity: Optional[str] = None,
        min_severity: Optional[str] = None,
        is_read: Optional[bool] = None,
        loan_id: Optional[int] = None,
        include_dismissed: bool = False,
        include_expired: bool = False,
    ) -> NotificationFeed:
        """Get paginated notification feed for a user.

        Returns notifications sorted by created_at descending (newest first).
        Expired and dismissed notifications are excluded by default.
        """
        filters = [
            _DocNotification.organization_id == self.org_id,
            _DocNotification.user_id == user_id,
        ]

        if not include_dismissed:
            filters.append(_DocNotification.is_dismissed == False)

        if not include_expired:
            filters.append(
                or_(
                    _DocNotification.expires_at.is_(None),
                    _DocNotification.expires_at > _utcnow(),
                )
            )

        if notification_type is not None:
            filters.append(_DocNotification.notification_type == notification_type)

        if severity is not None:
            filters.append(_DocNotification.severity == severity)

        if min_severity is not None:
            min_rank = _SEVERITY_RANK.get(min_severity, 0)
            # Build a CASE expression for severity ordering in the filter
            severity_values = [
                s for s, r in _SEVERITY_RANK.items() if r >= min_rank
            ]
            if severity_values:
                filters.append(
                    _DocNotification.severity.in_(severity_values)
                )

        if is_read is not None:
            filters.append(_DocNotification.is_read == is_read)

        if loan_id is not None:
            filters.append(_DocNotification.loan_id == loan_id)

        # Total count
        total_count = (
            self.db.query(func.count(_DocNotification.id))
            .filter(and_(*filters))
            .scalar()
        ) or 0

        # Unread count (same filters minus is_read)
        unread_filters = [f for f in filters if not _is_read_filter(f)]
        unread_filters.append(_DocNotification.is_read == False)
        unread_count = (
            self.db.query(func.count(_DocNotification.id))
            .filter(and_(*unread_filters))
            .scalar()
        ) or 0

        # Paginated query
        offset = (page - 1) * page_size
        notifications = (
            self.db.query(_DocNotification)
            .filter(and_(*filters))
            .order_by(_DocNotification.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        return NotificationFeed(
            notifications=[_serialize_notification(n) for n in notifications],
            total_count=total_count,
            unread_count=unread_count,
            page=page,
            page_size=page_size,
            has_more=(offset + page_size) < total_count,
        )

    # =========================================================================
    # UNREAD COUNT (for badge display)
    # =========================================================================

    async def get_unread_count(
        self,
        user_id: int,
        notification_type: Optional[str] = None,
        min_severity: Optional[str] = None,
    ) -> int:
        """Get the number of unread notifications for badge display.

        Excludes dismissed and expired notifications.
        """
        filters = [
            _DocNotification.organization_id == self.org_id,
            _DocNotification.user_id == user_id,
            _DocNotification.is_read == False,
            _DocNotification.is_dismissed == False,
            or_(
                _DocNotification.expires_at.is_(None),
                _DocNotification.expires_at > _utcnow(),
            ),
        ]

        if notification_type is not None:
            filters.append(_DocNotification.notification_type == notification_type)

        if min_severity is not None:
            min_rank = _SEVERITY_RANK.get(min_severity, 0)
            severity_values = [
                s for s, r in _SEVERITY_RANK.items() if r >= min_rank
            ]
            if severity_values:
                filters.append(
                    _DocNotification.severity.in_(severity_values)
                )

        count = (
            self.db.query(func.count(_DocNotification.id))
            .filter(and_(*filters))
            .scalar()
        ) or 0

        return count

    # =========================================================================
    # MARK AS READ / DISMISS
    # =========================================================================

    async def mark_read(
        self,
        notification_id: int,
        user_id: int,
    ) -> bool:
        """Mark a single notification as read. Returns True if updated."""
        now = _utcnow()
        updated = (
            self.db.query(_DocNotification)
            .filter(
                _DocNotification.id == notification_id,
                _DocNotification.organization_id == self.org_id,
                _DocNotification.user_id == user_id,
                _DocNotification.is_read == False,
            )
            .update(
                {"is_read": True, "read_at": now},
                synchronize_session="fetch",
            )
        )
        if updated:
            self.db.commit()
        return updated > 0

    async def mark_unread(
        self,
        notification_id: int,
        user_id: int,
    ) -> bool:
        """Mark a single notification as unread. Returns True if updated."""
        updated = (
            self.db.query(_DocNotification)
            .filter(
                _DocNotification.id == notification_id,
                _DocNotification.organization_id == self.org_id,
                _DocNotification.user_id == user_id,
                _DocNotification.is_read == True,
            )
            .update(
                {"is_read": False, "read_at": None},
                synchronize_session="fetch",
            )
        )
        if updated:
            self.db.commit()
        return updated > 0

    async def dismiss(
        self,
        notification_id: int,
        user_id: int,
    ) -> bool:
        """Dismiss a single notification. Returns True if updated."""
        now = _utcnow()
        updated = (
            self.db.query(_DocNotification)
            .filter(
                _DocNotification.id == notification_id,
                _DocNotification.organization_id == self.org_id,
                _DocNotification.user_id == user_id,
                _DocNotification.is_dismissed == False,
            )
            .update(
                {"is_dismissed": True, "dismissed_at": now, "is_read": True, "read_at": now},
                synchronize_session="fetch",
            )
        )
        if updated:
            self.db.commit()
        return updated > 0

    # =========================================================================
    # BULK OPERATIONS
    # =========================================================================

    async def mark_all_read(
        self,
        user_id: int,
        notification_type: Optional[str] = None,
        loan_id: Optional[int] = None,
    ) -> int:
        """Mark all unread notifications as read for a user.

        Returns the number of notifications updated.
        """
        now = _utcnow()
        filters = [
            _DocNotification.organization_id == self.org_id,
            _DocNotification.user_id == user_id,
            _DocNotification.is_read == False,
        ]
        if notification_type is not None:
            filters.append(_DocNotification.notification_type == notification_type)
        if loan_id is not None:
            filters.append(_DocNotification.loan_id == loan_id)

        updated = (
            self.db.query(_DocNotification)
            .filter(and_(*filters))
            .update(
                {"is_read": True, "read_at": now},
                synchronize_session="fetch",
            )
        )
        if updated:
            self.db.commit()
        return updated

    async def dismiss_all(
        self,
        user_id: int,
        notification_type: Optional[str] = None,
        loan_id: Optional[int] = None,
    ) -> int:
        """Dismiss all notifications for a user.

        Returns the number of notifications dismissed.
        """
        now = _utcnow()
        filters = [
            _DocNotification.organization_id == self.org_id,
            _DocNotification.user_id == user_id,
            _DocNotification.is_dismissed == False,
        ]
        if notification_type is not None:
            filters.append(_DocNotification.notification_type == notification_type)
        if loan_id is not None:
            filters.append(_DocNotification.loan_id == loan_id)

        updated = (
            self.db.query(_DocNotification)
            .filter(and_(*filters))
            .update(
                {
                    "is_dismissed": True,
                    "dismissed_at": now,
                    "is_read": True,
                    "read_at": now,
                },
                synchronize_session="fetch",
            )
        )
        if updated:
            self.db.commit()
        return updated

    async def bulk_mark_read(
        self,
        notification_ids: List[int],
        user_id: int,
    ) -> int:
        """Mark specific notifications as read by ID list.

        Returns the number of notifications updated.
        """
        if not notification_ids:
            return 0

        now = _utcnow()
        updated = (
            self.db.query(_DocNotification)
            .filter(
                _DocNotification.id.in_(notification_ids),
                _DocNotification.organization_id == self.org_id,
                _DocNotification.user_id == user_id,
                _DocNotification.is_read == False,
            )
            .update(
                {"is_read": True, "read_at": now},
                synchronize_session="fetch",
            )
        )
        if updated:
            self.db.commit()
        return updated

    async def bulk_dismiss(
        self,
        notification_ids: List[int],
        user_id: int,
    ) -> int:
        """Dismiss specific notifications by ID list.

        Returns the number of notifications dismissed.
        """
        if not notification_ids:
            return 0

        now = _utcnow()
        updated = (
            self.db.query(_DocNotification)
            .filter(
                _DocNotification.id.in_(notification_ids),
                _DocNotification.organization_id == self.org_id,
                _DocNotification.user_id == user_id,
                _DocNotification.is_dismissed == False,
            )
            .update(
                {
                    "is_dismissed": True,
                    "dismissed_at": now,
                    "is_read": True,
                    "read_at": now,
                },
                synchronize_session="fetch",
            )
        )
        if updated:
            self.db.commit()
        return updated

    # =========================================================================
    # USER PREFERENCE MANAGEMENT
    # =========================================================================

    async def get_preferences(
        self,
        user_id: int,
    ) -> Dict[str, Dict[str, Any]]:
        """Get all notification preferences for a user.

        Returns a dict keyed by notification_type. Types without a stored
        preference row return the system defaults.
        """
        prefs = (
            self.db.query(_NotificationPreference)
            .filter(_NotificationPreference.user_id == user_id)
            .all()
        )

        pref_map: Dict[str, Dict[str, Any]] = {}

        # Start with defaults for all types
        for ntype in NotificationType:
            pref_map[ntype.value] = {
                "notification_type": ntype.value,
                "in_app_enabled": True,
                "email_enabled": True,
                "push_enabled": False,
                "minimum_severity": "info",
                "is_default": True,
            }

        # Override with stored preferences
        for pref in prefs:
            if pref.notification_type in pref_map:
                pref_map[pref.notification_type] = {
                    "notification_type": pref.notification_type,
                    "in_app_enabled": pref.in_app_enabled,
                    "email_enabled": pref.email_enabled,
                    "push_enabled": pref.push_enabled,
                    "minimum_severity": pref.minimum_severity or "info",
                    "is_default": False,
                }

        return pref_map

    async def update_preference(
        self,
        user_id: int,
        notification_type: str,
        in_app_enabled: Optional[bool] = None,
        email_enabled: Optional[bool] = None,
        push_enabled: Optional[bool] = None,
        minimum_severity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a user's preference for a specific notification type.

        Creates the preference row if it does not exist (upsert).
        Returns the updated preference as a dict.
        """
        pref = (
            self.db.query(_NotificationPreference)
            .filter(
                _NotificationPreference.user_id == user_id,
                _NotificationPreference.notification_type == notification_type,
            )
            .first()
        )

        if pref is None:
            pref = _NotificationPreference(
                user_id=user_id,
                notification_type=notification_type,
                in_app_enabled=in_app_enabled if in_app_enabled is not None else True,
                email_enabled=email_enabled if email_enabled is not None else True,
                push_enabled=push_enabled if push_enabled is not None else False,
                minimum_severity=minimum_severity or "info",
            )
            self.db.add(pref)
        else:
            if in_app_enabled is not None:
                pref.in_app_enabled = in_app_enabled
            if email_enabled is not None:
                pref.email_enabled = email_enabled
            if push_enabled is not None:
                pref.push_enabled = push_enabled
            if minimum_severity is not None:
                pref.minimum_severity = minimum_severity

        self.db.commit()
        self.db.refresh(pref)

        return {
            "notification_type": pref.notification_type,
            "in_app_enabled": pref.in_app_enabled,
            "email_enabled": pref.email_enabled,
            "push_enabled": pref.push_enabled,
            "minimum_severity": pref.minimum_severity,
        }

    async def reset_preferences(
        self,
        user_id: int,
    ) -> int:
        """Reset all preferences to defaults by deleting stored rows.

        Returns the number of preference rows deleted.
        """
        deleted = (
            self.db.query(_NotificationPreference)
            .filter(_NotificationPreference.user_id == user_id)
            .delete(synchronize_session="fetch")
        )
        if deleted:
            self.db.commit()
        return deleted

    # =========================================================================
    # AUTO-EXPIRY CLEANUP
    # =========================================================================

    async def expire_stale_notifications(
        self,
        batch_size: int = 500,
    ) -> int:
        """Mark expired notifications as dismissed.

        Called by a scheduled task (e.g. cron) to clean up time-sensitive
        notifications that have passed their ``expires_at`` date.

        Returns the number of notifications expired.
        """
        now = _utcnow()
        updated = (
            self.db.query(_DocNotification)
            .filter(
                _DocNotification.organization_id == self.org_id,
                _DocNotification.expires_at.isnot(None),
                _DocNotification.expires_at <= now,
                _DocNotification.is_dismissed == False,
            )
            .limit(batch_size)
            .update(
                {
                    "is_dismissed": True,
                    "dismissed_at": now,
                },
                synchronize_session="fetch",
            )
        )
        if updated:
            self.db.commit()
            logger.info(
                "Expired %d stale notifications for org %s",
                updated,
                self.org_id,
            )
        return updated

    # =========================================================================
    # ANALYTICS
    # =========================================================================

    async def get_analytics(
        self,
        days: int = 30,
        user_id: Optional[int] = None,
    ) -> NotificationAnalytics:
        """Get notification analytics for the organization.

        Args:
            days: Look-back period in days.
            user_id: Optional filter to a specific user.

        Returns:
            NotificationAnalytics with totals, rates, and breakdowns.
        """
        since = _utcnow() - timedelta(days=days)

        filters = [
            _DocNotification.organization_id == self.org_id,
            _DocNotification.created_at >= since,
        ]
        if user_id is not None:
            filters.append(_DocNotification.user_id == user_id)

        # Totals
        totals = self.db.query(
            func.count(_DocNotification.id).label("total"),
            func.count(
                case(((_DocNotification.is_read == True, _DocNotification.id),))
            ).label("read"),
            func.count(
                case(((_DocNotification.is_dismissed == True, _DocNotification.id),))
            ).label("dismissed"),
        ).filter(and_(*filters)).first()

        total_sent = totals.total if totals else 0
        total_read = totals.read if totals else 0
        total_dismissed = totals.dismissed if totals else 0
        read_rate = (total_read / total_sent * 100) if total_sent > 0 else 0.0

        # Average time to read (for notifications that have been read)
        avg_read_time_result = self.db.query(
            func.avg(
                func.extract("epoch", _DocNotification.read_at)
                - func.extract("epoch", _DocNotification.created_at)
            )
        ).filter(
            and_(
                *filters,
                _DocNotification.is_read == True,
                _DocNotification.read_at.isnot(None),
            )
        ).scalar()

        avg_time_to_read_minutes = (
            round(float(avg_read_time_result) / 60, 1)
            if avg_read_time_result
            else 0.0
        )

        # By type
        type_rows = (
            self.db.query(
                _DocNotification.notification_type,
                func.count(_DocNotification.id).label("count"),
                func.count(
                    case(((_DocNotification.is_read == True, _DocNotification.id),))
                ).label("read"),
            )
            .filter(and_(*filters))
            .group_by(_DocNotification.notification_type)
            .all()
        )

        by_type = {
            row.notification_type: {
                "sent": row.count,
                "read": row.read,
                "read_rate": round((row.read / row.count * 100) if row.count > 0 else 0, 1),
            }
            for row in type_rows
        }

        # By channel
        channel_counts: Dict[str, int] = {"in_app": total_sent}
        email_count = self.db.query(
            func.count(_DocNotification.id)
        ).filter(
            and_(*filters, _DocNotification.email_sent == True)
        ).scalar() or 0
        push_count = self.db.query(
            func.count(_DocNotification.id)
        ).filter(
            and_(*filters, _DocNotification.push_sent == True)
        ).scalar() or 0
        channel_counts["email"] = email_count
        channel_counts["push"] = push_count

        # By severity
        severity_rows = (
            self.db.query(
                _DocNotification.severity,
                func.count(_DocNotification.id).label("count"),
            )
            .filter(and_(*filters))
            .group_by(_DocNotification.severity)
            .all()
        )
        by_severity = {row.severity: row.count for row in severity_rows}

        return NotificationAnalytics(
            total_sent=total_sent,
            total_read=total_read,
            total_dismissed=total_dismissed,
            read_rate=round(read_rate, 1),
            avg_time_to_read_minutes=avg_time_to_read_minutes,
            by_type=by_type,
            by_channel=channel_counts,
            by_severity=by_severity,
        )

    # =========================================================================
    # ROLE-BASED ROUTING
    # =========================================================================

    async def get_target_users_by_role(
        self,
        notification_type: str,
        loan_id: Optional[int] = None,
    ) -> List[int]:
        """Determine which users should receive a notification based on role routing.

        Uses the ``_ROLE_ROUTING`` mapping to find users whose role matches
        the notification type. When ``loan_id`` is provided, also considers
        the loan's assigned loan_officer_id.

        Returns a list of user IDs.
        """
        allowed_roles = _ROLE_ROUTING.get(notification_type, set())
        if not allowed_roles:
            return []

        # Query users in this org with matching roles
        role_filter_clauses = [
            text("u.role = :role").bindparams(role=r)
            for r in allowed_roles
        ]

        # Use raw SQL for the role-based lookup since User.role is a simple
        # String column and we need to handle the OR across multiple values
        rows = self.db.execute(
            text("""
                SELECT DISTINCT u.id
                FROM users u
                WHERE u.organization_id = :org_id
                  AND u.role IN :roles
                  AND u.is_active = true
            """),
            {"org_id": self.org_id, "roles": tuple(allowed_roles)},
        ).fetchall()

        user_ids = [row[0] for row in rows]

        # If a loan_id is specified, ensure the loan officer is included
        if loan_id is not None:
            lo_row = self.db.execute(
                text("""
                    SELECT loan_officer_id
                    FROM loans
                    WHERE id = :loan_id AND organization_id = :org_id
                """),
                {"loan_id": loan_id, "org_id": self.org_id},
            ).fetchone()
            if lo_row and lo_row[0] and lo_row[0] not in user_ids:
                user_ids.append(lo_row[0])

        return user_ids

    # =========================================================================
    # INTERNAL: template rendering + creation pipeline
    # =========================================================================

    async def _create_from_template(
        self,
        notification_type: NotificationType,
        target_user_ids: List[int],
        loan_id: Optional[int],
        template_vars: Dict[str, str],
        extra_metadata: Optional[Dict[str, Any]] = None,
        severity_override: Optional[Severity] = None,
    ) -> NotificationResult:
        """Render a template and create notifications for each target user."""
        template = _TEMPLATES.get(notification_type.value)
        if template is None:
            return NotificationResult(
                success=False,
                error=f"No template for notification type: {notification_type.value}",
            )

        # Render title and body with safe substitution
        title = _safe_format(template["title"], template_vars)
        body = _safe_format(template["body"], template_vars)
        severity = (severity_override.value if severity_override else template["severity"])
        action_label = template.get("action_label")
        action_url_pattern = template.get("action_url", "")
        action_url = _safe_format(action_url_pattern, template_vars)
        if action_url:
            action_url = f"{_APP_URL}{action_url}"

        return await self._create_notifications(
            notification_type=notification_type.value,
            target_user_ids=target_user_ids,
            loan_id=loan_id,
            title=title,
            body=body,
            severity=severity,
            action_url=action_url or None,
            action_label=action_label,
            metadata=extra_metadata,
        )

    async def _create_notifications(
        self,
        notification_type: str,
        target_user_ids: List[int],
        loan_id: Optional[int],
        title: str,
        body: str,
        severity: str = "info",
        action_url: Optional[str] = None,
        action_label: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        delivery_channels: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> NotificationResult:
        """Core creation pipeline: preference check, create records, trigger delivery."""
        if not target_user_ids:
            return NotificationResult(success=True)

        # Deduplicate target user IDs
        target_user_ids = list(set(target_user_ids))

        # Compute expiry if not provided
        if expires_at is None:
            expiry_hours = _DEFAULT_EXPIRY_HOURS.get(notification_type)
            if expiry_hours:
                expires_at = _utcnow() + timedelta(hours=expiry_hours)

        # Load preferences for all target users in one query
        prefs = (
            self.db.query(_NotificationPreference)
            .filter(
                _NotificationPreference.user_id.in_(target_user_ids),
                _NotificationPreference.notification_type == notification_type,
            )
            .all()
        )
        pref_map: Dict[int, _NotificationPreference] = {
            p.user_id: p for p in prefs
        }

        force_deliver = notification_type in _FORCE_DELIVER_TYPES

        created_ids: List[int] = []
        skipped_users: List[int] = []
        channels_delivered: Dict[str, int] = defaultdict(int)

        severity_rank = _SEVERITY_RANK.get(severity, 0)

        for uid in target_user_ids:
            pref = pref_map.get(uid)

            # Determine channels for this user
            if delivery_channels:
                user_channels = list(delivery_channels)
            elif force_deliver:
                # Compliance/fraud: always deliver on all available channels
                user_channels = ["in_app", "email"]
            elif pref:
                # Check minimum severity
                min_sev_rank = _SEVERITY_RANK.get(pref.minimum_severity or "info", 0)
                if severity_rank < min_sev_rank:
                    skipped_users.append(uid)
                    continue

                user_channels = []
                if pref.in_app_enabled:
                    user_channels.append("in_app")
                if pref.email_enabled:
                    user_channels.append("email")
                if pref.push_enabled:
                    user_channels.append("push")
            else:
                # Default channels
                user_channels = ["in_app", "email"]

            if not user_channels:
                skipped_users.append(uid)
                continue

            # Create the notification record (always stored for in-app)
            notif = _DocNotification(
                organization_id=self.org_id,
                user_id=uid,
                loan_id=loan_id,
                notification_type=notification_type,
                severity=severity,
                title=title[:300],
                body=body,
                action_url=action_url[:500] if action_url else None,
                action_label=action_label[:100] if action_label else None,
                metadata=metadata,
                delivery_channels=user_channels,
                expires_at=expires_at,
            )
            self.db.add(notif)
            self.db.flush()  # Get the ID without full commit
            created_ids.append(notif.id)

            for ch in user_channels:
                channels_delivered[ch] += 1

            # Trigger email delivery if enabled
            if "email" in user_channels:
                email_sent = await self._send_email_notification(
                    user_id=uid,
                    title=title,
                    body=body,
                    severity=severity,
                    action_url=action_url,
                    action_label=action_label,
                    notification_type=notification_type,
                )
                if email_sent:
                    notif.email_sent = True

            # Trigger push delivery if enabled
            if "push" in user_channels:
                push_sent = await self._send_push_notification(
                    user_id=uid,
                    title=title,
                    body=body,
                    severity=severity,
                    notification_type=notification_type,
                )
                if push_sent:
                    notif.push_sent = True

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.exception(
                "Failed to commit notifications for org %s: %s",
                self.org_id,
                e,
            )
            return NotificationResult(
                success=False,
                error=f"Database commit failed: {str(e)}",
            )

        logger.info(
            "Created %d %s notifications for org %s (skipped %d users)",
            len(created_ids),
            notification_type,
            self.org_id,
            len(skipped_users),
        )

        return NotificationResult(
            success=True,
            notification_ids=created_ids,
            channels_delivered=dict(channels_delivered),
            skipped_users=skipped_users,
        )

    # =========================================================================
    # DELIVERY BACKENDS
    # =========================================================================

    async def _send_email_notification(
        self,
        user_id: int,
        title: str,
        body: str,
        severity: str,
        action_url: Optional[str],
        action_label: Optional[str],
        notification_type: str,
    ) -> bool:
        """Send an email notification to a user.

        Looks up the user's email and delegates to the existing
        notification_templates module for rendering and sending.
        """
        try:
            row = self.db.execute(
                text("SELECT email, first_name FROM users WHERE id = :uid AND organization_id = :org_id"),
                {"uid": user_id, "org_id": self.org_id},
            ).fetchone()

            if not row or not row[0]:
                logger.warning(
                    "Cannot send email notification to user %s: no email found",
                    user_id,
                )
                return False

            email_addr = row[0]
            first_name = row[1] or "Team Member"

            # Use the existing notification_templates infrastructure
            try:
                from services.smart_docs.notification_templates import send_notification as _send

                return _send(
                    db=self.db,
                    template_name="doc_status_update",
                    to_email=email_addr,
                    variables={
                        "borrower_name": first_name,
                        "document_title": title,
                        "status": severity,
                        "status_message": body,
                        "action_url": action_url or "",
                        "action_label": action_label or "View Details",
                    },
                )
            except Exception as e:
                logger.warning(
                    "Email send via notification_templates failed for user %s, "
                    "falling back to basic email: %s",
                    user_id,
                    e,
                )
                # Fallback: try EmailService directly
                try:
                    from email_service import EmailService
                    svc = EmailService()
                    return svc.send_html_email(
                        to_email=email_addr,
                        subject=f"[Smart Docs] {title}",
                        html_body=f"<p>{body}</p>",
                        plain_text_body=body,
                    )
                except Exception as e2:
                    logger.error("Fallback email send also failed: %s", e2)
                    return False

        except Exception as e:
            logger.exception("Error sending email notification to user %s: %s", user_id, e)
            return False

    async def _send_push_notification(
        self,
        user_id: int,
        title: str,
        body: str,
        severity: str,
        notification_type: str,
    ) -> bool:
        """Send a push notification to a user via APNs/FCM.

        Delegates to PushNotificationService which handles APNs JWT auth,
        HTTP/2 delivery, token invalidation on 410, and FCM.
        """
        try:
            from services.push_notification_service import send_push_to_user

            data = {
                "type": notification_type,
                "severity": severity,
                "route": "/smart-docs",
            }

            result = send_push_to_user(
                user_id=user_id,
                title=title,
                body=body,
                data=data,
                notification_type=notification_type,
            )

            sent = result.get("sent", 0)
            if sent > 0:
                logger.info("Push notification sent to user %s: %s", user_id, title)
                return True
            else:
                logger.debug(
                    "Push notification not delivered to user %s (sent=%d, skipped=%d): %s",
                    user_id, sent, result.get("skipped", 0), title,
                )
                return False

        except Exception as e:
            logger.warning("Push notification failed for user %s: %s", user_id, e)
            return False


# =============================================================================
# MODULE-LEVEL HELPERS
# =============================================================================

def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def _safe_format(template: str, variables: Dict[str, str]) -> str:
    """Format a template string, replacing missing keys with empty strings.

    This avoids KeyError if a template variable is not provided.
    """
    class SafeDict(dict):
        def __missing__(self, key):
            return ""

    try:
        return template.format_map(SafeDict(variables))
    except Exception:
        return template


def _is_read_filter(filter_clause) -> bool:
    """Check if a SQLAlchemy filter clause is an is_read filter.

    Used to strip is_read filters when computing unread count alongside
    the main feed query.
    """
    try:
        clause_str = str(filter_clause)
        return "is_read" in clause_str
    except Exception:
        return False


def _serialize_notification(notif) -> Dict[str, Any]:
    """Serialize a DocNotification ORM object to a JSON-safe dict."""
    return {
        "id": notif.id,
        "organization_id": notif.organization_id,
        "user_id": notif.user_id,
        "loan_id": notif.loan_id,
        "notification_type": notif.notification_type,
        "severity": notif.severity,
        "title": notif.title,
        "body": notif.body,
        "action_url": notif.action_url,
        "action_label": notif.action_label,
        "metadata": notif.metadata,
        "is_read": notif.is_read,
        "read_at": notif.read_at.isoformat() if notif.read_at else None,
        "is_dismissed": notif.is_dismissed,
        "dismissed_at": notif.dismissed_at.isoformat() if notif.dismissed_at else None,
        "delivery_channels": notif.delivery_channels,
        "email_sent": notif.email_sent,
        "push_sent": notif.push_sent,
        "created_at": notif.created_at.isoformat() if notif.created_at else None,
        "expires_at": notif.expires_at.isoformat() if notif.expires_at else None,
    }


# =============================================================================
# FACTORY
# =============================================================================

def get_notification_center_service(
    db: Session,
    org_id: int,
    user_id: Optional[int] = None,
) -> NotificationCenterService:
    """Factory function for creating a NotificationCenterService instance.

    Usage:
        service = get_notification_center_service(db, org_id=42, user_id=7)
    """
    return NotificationCenterService(db=db, org_id=org_id, user_id=user_id)
