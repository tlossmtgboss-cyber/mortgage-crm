"""
Proactive Deal Alerts Service

AI-powered monitoring and alerting for loans in the pipeline.
Proactively identifies issues before they become problems.

Features:
- Rate lock expiration monitoring
- Stalled loan detection
- Compliance deadline tracking
- At-risk deal identification
- Document expiration alerts
- SLA violation warnings
- Closing delay prediction
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, date
from dataclasses import dataclass, field
from enum import Enum
import uuid
from sqlalchemy.exc import SQLAlchemyError

from services.workflow_constants import STAGE_SLA_DAYS as _CANONICAL_SLA_DAYS

logger = logging.getLogger(__name__)


class AlertType(str, Enum):
    """Types of deal alerts."""
    RATE_LOCK_EXPIRING = "rate_lock_expiring"
    RATE_LOCK_EXPIRED = "rate_lock_expired"
    STALLED_LOAN = "stalled_loan"
    COMPLIANCE_DEADLINE = "compliance_deadline"
    DOCUMENT_EXPIRING = "document_expiring"
    DOCUMENT_MISSING = "document_missing"
    CONDITION_PAST_DUE = "condition_past_due"
    SLA_AT_RISK = "sla_at_risk"
    SLA_VIOLATED = "sla_violated"
    CLOSING_DELAY_RISK = "closing_delay_risk"
    BORROWER_UNRESPONSIVE = "borrower_unresponsive"
    CREDIT_EXPIRING = "credit_expiring"
    APPRAISAL_ISSUE = "appraisal_issue"
    TITLE_ISSUE = "title_issue"
    FUNDING_ISSUE = "funding_issue"
    PIPELINE_BOTTLENECK = "pipeline_bottleneck"


class AlertPriority(str, Enum):
    """Alert priority levels."""
    CRITICAL = "critical"  # Immediate action required
    HIGH = "high"          # Action needed today
    MEDIUM = "medium"      # Action needed this week
    LOW = "low"            # Informational


class AlertStatus(str, Enum):
    """Alert status."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SNOOZED = "snoozed"


@dataclass
class DealAlert:
    """A single deal alert."""
    id: str
    type: AlertType
    priority: AlertPriority
    status: AlertStatus
    loan_id: str
    loan_number: str
    borrower_name: str
    title: str
    message: str
    details: Dict[str, Any]
    recommended_action: str
    created_at: datetime
    due_date: Optional[date] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None
    assigned_to: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "loan_id": self.loan_id,
            "loan_number": self.loan_number,
            "borrower_name": self.borrower_name,
            "title": self.title,
            "message": self.message,
            "details": self.details,
            "recommended_action": self.recommended_action,
            "created_at": self.created_at.isoformat(),
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "snoozed_until": self.snoozed_until.isoformat() if self.snoozed_until else None,
            "assigned_to": self.assigned_to,
            "tags": self.tags,
        }


@dataclass
class AlertSummary:
    """Summary of alerts for a user or team."""
    total_alerts: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    by_type: Dict[str, int]
    loans_at_risk: int
    alerts_today: int
    resolved_today: int


class ProactiveDealAlertsService:
    """
    Proactive deal monitoring and alerting service.

    Continuously monitors the pipeline and generates alerts
    before issues become problems.
    """

    # SLA thresholds by stage (in days)
    # Derived from canonical STAGE_SLA_DAYS with lowercase keys for compatibility
    SLA_THRESHOLDS = {k.lower(): v for k, v in _CANONICAL_SLA_DAYS.items()}

    # Alert templates
    ALERT_TEMPLATES = {
        AlertType.RATE_LOCK_EXPIRING: {
            "title": "Rate Lock Expiring Soon",
            "message": "Rate lock expires in {days} days. Consider extending or expediting close.",
            "action": "Review lock status and coordinate with borrower on timeline",
        },
        AlertType.RATE_LOCK_EXPIRED: {
            "title": "Rate Lock Expired",
            "message": "Rate lock has expired. Immediate action required to relock.",
            "action": "Contact borrower about market changes and relock options",
        },
        AlertType.STALLED_LOAN: {
            "title": "Loan Stalled in {stage}",
            "message": "Loan has been in {stage} for {days} days without progress.",
            "action": "Review blockers and create action plan to move forward",
        },
        AlertType.COMPLIANCE_DEADLINE: {
            "title": "Compliance Deadline Approaching",
            "message": "{disclosure_type} deadline in {days} days.",
            "action": "Ensure all required disclosures are prepared and sent",
        },
        AlertType.DOCUMENT_EXPIRING: {
            "title": "Document Expiring",
            "message": "{doc_type} expires in {days} days.",
            "action": "Request updated document from borrower",
        },
        AlertType.DOCUMENT_MISSING: {
            "title": "Critical Document Missing",
            "message": "{doc_type} required but not received after {days} days.",
            "action": "Follow up with borrower on document submission",
        },
        AlertType.CONDITION_PAST_DUE: {
            "title": "Condition Past Due",
            "message": "{condition} was due {days} days ago.",
            "action": "Prioritize clearing this condition to avoid further delays",
        },
        AlertType.SLA_AT_RISK: {
            "title": "SLA At Risk",
            "message": "Loan approaching SLA threshold for {stage}.",
            "action": "Expedite processing to meet SLA commitment",
        },
        AlertType.SLA_VIOLATED: {
            "title": "SLA Violated",
            "message": "SLA breached for {stage} by {days} days.",
            "action": "Escalate and document reason for delay",
        },
        AlertType.CLOSING_DELAY_RISK: {
            "title": "Closing Delay Risk",
            "message": "Current pace indicates {days} day delay from scheduled close.",
            "action": "Review timeline and communicate with all parties",
        },
        AlertType.BORROWER_UNRESPONSIVE: {
            "title": "Borrower Unresponsive",
            "message": "No borrower response in {days} days.",
            "action": "Try alternative contact methods or escalate",
        },
    }

    def __init__(self, db_session=None):
        self.db = db_session
        self._alerts: Dict[str, DealAlert] = {}  # In-memory storage for demo

    def scan_pipeline(
        self,
        user_id: Optional[str] = None,
        branch_id: Optional[str] = None,
    ) -> List[DealAlert]:
        """
        Scan the pipeline and generate proactive alerts.

        In production, this would query the database for all active loans
        and analyze each one for potential issues.
        """
        alerts = []
        today = date.today()

        # Simulate scanning pipeline (in production, query database)
        sample_loans = self._get_sample_loans()

        for loan in sample_loans:
            # Check rate lock
            if loan.get("lock_expiration"):
                lock_exp = loan["lock_expiration"]
                days_to_exp = (lock_exp - today).days

                if days_to_exp < 0:
                    alert = self._create_alert(
                        AlertType.RATE_LOCK_EXPIRED,
                        AlertPriority.CRITICAL,
                        loan,
                        {"days": abs(days_to_exp)},
                    )
                    alerts.append(alert)
                elif days_to_exp <= 5:
                    alert = self._create_alert(
                        AlertType.RATE_LOCK_EXPIRING,
                        AlertPriority.HIGH if days_to_exp <= 2 else AlertPriority.MEDIUM,
                        loan,
                        {"days": days_to_exp},
                    )
                    alerts.append(alert)

            # Check for stalled loans
            if loan.get("days_in_stage", 0) > self.SLA_THRESHOLDS.get(loan.get("status"), 5):
                days_over = loan["days_in_stage"] - self.SLA_THRESHOLDS.get(loan.get("status"), 5)
                alert = self._create_alert(
                    AlertType.STALLED_LOAN,
                    AlertPriority.HIGH if days_over > 3 else AlertPriority.MEDIUM,
                    loan,
                    {"stage": loan["status"], "days": loan["days_in_stage"]},
                )
                alerts.append(alert)

            # Check SLA status
            sla_threshold = self.SLA_THRESHOLDS.get(loan.get("status"), 5)
            days_in_stage = loan.get("days_in_stage", 0)

            if days_in_stage > sla_threshold:
                alert = self._create_alert(
                    AlertType.SLA_VIOLATED,
                    AlertPriority.HIGH,
                    loan,
                    {"stage": loan["status"], "days": days_in_stage - sla_threshold},
                )
                alerts.append(alert)
            elif days_in_stage >= sla_threshold - 1:
                alert = self._create_alert(
                    AlertType.SLA_AT_RISK,
                    AlertPriority.MEDIUM,
                    loan,
                    {"stage": loan["status"]},
                )
                alerts.append(alert)

            # Check closing delay risk
            if loan.get("expected_close") and loan.get("predicted_close"):
                delay_days = (loan["predicted_close"] - loan["expected_close"]).days
                if delay_days > 0:
                    alert = self._create_alert(
                        AlertType.CLOSING_DELAY_RISK,
                        AlertPriority.HIGH if delay_days > 5 else AlertPriority.MEDIUM,
                        loan,
                        {"days": delay_days},
                    )
                    alerts.append(alert)

            # Check borrower responsiveness
            if loan.get("days_since_contact", 0) > 5:
                alert = self._create_alert(
                    AlertType.BORROWER_UNRESPONSIVE,
                    AlertPriority.MEDIUM,
                    loan,
                    {"days": loan["days_since_contact"]},
                )
                alerts.append(alert)

        # Store alerts
        for alert in alerts:
            self._alerts[alert.id] = alert

        return alerts

    def _get_sample_loans(self) -> List[Dict]:
        """Get loan data - from database if available, otherwise demo data."""
        today = date.today()

        # Try to fetch real loans from database
        if self.db:
            try:
                from sqlalchemy import text
                result = self.db.execute(text("""
                    SELECT
                        l.id,
                        COALESCE(l.loan_number, 'LOAN-' || l.id) as loan_number,
                        COALESCE(l.borrower_name, 'Unknown') as borrower_name,
                        COALESCE(l.stage::text, 'processing') as status,
                        COALESCE(l.days_in_stage, EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.updated_at))::integer, 0) as days_in_stage,
                        l.amount as loan_amount
                    FROM loans l
                    WHERE l.stage IS NULL
                       OR UPPER(l.stage::text) NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'CLOSED')
                    ORDER BY l.updated_at ASC
                    LIMIT 100
                """))

                loans = []
                for row in result.fetchall():
                    row_dict = row._asdict() if hasattr(row, '_asdict') else dict(row)
                    days_in_stage = int(row_dict.get('days_in_stage') or 0)

                    loans.append({
                        "id": str(row_dict.get('id')),
                        "loan_number": row_dict.get('loan_number') or f"LOAN-{row_dict.get('id')}",
                        "borrower_name": row_dict.get('borrower_name') or 'Unknown',
                        "status": row_dict.get('status') or 'processing',
                        "days_in_stage": days_in_stage,
                        # Estimate lock expiration based on days in stage (demo fallback)
                        "lock_expiration": today + timedelta(days=max(30 - days_in_stage, 0)) if days_in_stage < 30 else today - timedelta(days=1),
                        "expected_close": today + timedelta(days=30),
                        "predicted_close": today + timedelta(days=30 + min(days_in_stage // 5, 10)),
                        "days_since_contact": min(days_in_stage, 7),  # Estimate
                    })

                if loans:
                    logger.info(f"Fetched {len(loans)} active loans from database for alert scanning")
                    return loans

            except Exception as e:
                logger.warning(f"Could not fetch loans from database, using demo data: {e}")

        # Fallback to demo data
        logger.info("Using demo loan data for alert scanning")
        return [
            {
                "id": "loan-001",
                "loan_number": "2024-001234",
                "borrower_name": "John Smith",
                "status": "processing",
                "days_in_stage": 8,
                "lock_expiration": today + timedelta(days=3),
                "expected_close": today + timedelta(days=15),
                "predicted_close": today + timedelta(days=18),
                "days_since_contact": 2,
            },
            {
                "id": "loan-002",
                "loan_number": "2024-001235",
                "borrower_name": "Jane Doe",
                "status": "underwriting",
                "days_in_stage": 6,
                "lock_expiration": today + timedelta(days=10),
                "expected_close": today + timedelta(days=20),
                "predicted_close": today + timedelta(days=20),
                "days_since_contact": 7,
            },
            {
                "id": "loan-003",
                "loan_number": "2024-001236",
                "borrower_name": "Bob Johnson",
                "status": "approved",
                "days_in_stage": 2,
                "lock_expiration": today - timedelta(days=1),  # Expired
                "expected_close": today + timedelta(days=10),
                "predicted_close": today + timedelta(days=12),
                "days_since_contact": 1,
            },
            {
                "id": "loan-004",
                "loan_number": "2024-001237",
                "borrower_name": "Alice Williams",
                "status": "clear_to_close",
                "days_in_stage": 4,
                "lock_expiration": today + timedelta(days=7),
                "expected_close": today + timedelta(days=5),
                "predicted_close": today + timedelta(days=5),
                "days_since_contact": 0,
            },
        ]

    def _create_alert(
        self,
        alert_type: AlertType,
        priority: AlertPriority,
        loan: Dict,
        params: Dict,
    ) -> DealAlert:
        """Create an alert from template."""
        template = self.ALERT_TEMPLATES.get(alert_type, {})

        # Format message with parameters
        title = template.get("title", str(alert_type.value)).format(**params)
        message = template.get("message", "").format(**params)
        action = template.get("action", "Review and take action").format(**params)

        return DealAlert(
            id=str(uuid.uuid4())[:8],
            type=alert_type,
            priority=priority,
            status=AlertStatus.ACTIVE,
            loan_id=loan["id"],
            loan_number=loan["loan_number"],
            borrower_name=loan["borrower_name"],
            title=title,
            message=message,
            details=params,
            recommended_action=action,
            created_at=datetime.now(),
            due_date=date.today() if priority in [AlertPriority.CRITICAL, AlertPriority.HIGH] else None,
            tags=[alert_type.value, priority.value],
        )

    def get_alerts(
        self,
        user_id: Optional[str] = None,
        status: Optional[AlertStatus] = None,
        priority: Optional[AlertPriority] = None,
        alert_type: Optional[AlertType] = None,
        loan_id: Optional[str] = None,
    ) -> List[DealAlert]:
        """Get alerts with optional filters."""
        alerts = list(self._alerts.values())

        if status:
            alerts = [a for a in alerts if a.status == status]
        if priority:
            alerts = [a for a in alerts if a.priority == priority]
        if alert_type:
            alerts = [a for a in alerts if a.type == alert_type]
        if loan_id:
            alerts = [a for a in alerts if a.loan_id == loan_id]

        # Sort by priority (critical first) then by created_at
        priority_order = {
            AlertPriority.CRITICAL: 0,
            AlertPriority.HIGH: 1,
            AlertPriority.MEDIUM: 2,
            AlertPriority.LOW: 3,
        }
        alerts.sort(key=lambda a: (priority_order[a.priority], a.created_at))

        return alerts

    def get_alert(self, alert_id: str) -> Optional[DealAlert]:
        """Get a specific alert by ID."""
        return self._alerts.get(alert_id)

    def acknowledge_alert(self, alert_id: str) -> Optional[DealAlert]:
        """Acknowledge an alert."""
        alert = self._alerts.get(alert_id)
        if alert:
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = datetime.now()
        return alert

    def resolve_alert(self, alert_id: str, resolution_note: Optional[str] = None) -> Optional[DealAlert]:
        """Resolve an alert."""
        alert = self._alerts.get(alert_id)
        if alert:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now()
            if resolution_note:
                alert.details["resolution_note"] = resolution_note
        return alert

    def snooze_alert(self, alert_id: str, snooze_hours: int = 24) -> Optional[DealAlert]:
        """Snooze an alert for a specified duration."""
        alert = self._alerts.get(alert_id)
        if alert:
            alert.status = AlertStatus.SNOOZED
            alert.snoozed_until = datetime.now() + timedelta(hours=snooze_hours)
        return alert

    def get_summary(self, user_id: Optional[str] = None) -> AlertSummary:
        """Get summary of alerts."""
        alerts = self.get_alerts(user_id=user_id, status=AlertStatus.ACTIVE)
        today = date.today()

        by_type: Dict[str, int] = {}
        for alert in alerts:
            by_type[alert.type.value] = by_type.get(alert.type.value, 0) + 1

        loans_at_risk = len(set(a.loan_id for a in alerts if a.priority in [AlertPriority.CRITICAL, AlertPriority.HIGH]))

        alerts_today = len([a for a in alerts if a.created_at.date() == today])
        resolved_today = len([a for a in self._alerts.values() if a.resolved_at and a.resolved_at.date() == today])

        return AlertSummary(
            total_alerts=len(alerts),
            critical_count=len([a for a in alerts if a.priority == AlertPriority.CRITICAL]),
            high_count=len([a for a in alerts if a.priority == AlertPriority.HIGH]),
            medium_count=len([a for a in alerts if a.priority == AlertPriority.MEDIUM]),
            low_count=len([a for a in alerts if a.priority == AlertPriority.LOW]),
            by_type=by_type,
            loans_at_risk=loans_at_risk,
            alerts_today=alerts_today,
            resolved_today=resolved_today,
        )

    def get_alerts_for_loan(self, loan_id: str) -> List[DealAlert]:
        """Get all alerts for a specific loan."""
        return [a for a in self._alerts.values() if a.loan_id == loan_id]

    def bulk_acknowledge(self, alert_ids: List[str]) -> int:
        """Acknowledge multiple alerts at once."""
        count = 0
        for alert_id in alert_ids:
            if self.acknowledge_alert(alert_id):
                count += 1
        return count

    def get_priority_actions(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top priority actions across all alerts."""
        alerts = self.get_alerts(status=AlertStatus.ACTIVE)
        critical_and_high = [a for a in alerts if a.priority in [AlertPriority.CRITICAL, AlertPriority.HIGH]]

        actions = []
        for alert in critical_and_high[:limit]:
            actions.append({
                "alert_id": alert.id,
                "loan_number": alert.loan_number,
                "borrower": alert.borrower_name,
                "priority": alert.priority.value,
                "issue": alert.title,
                "action": alert.recommended_action,
                "due": alert.due_date.isoformat() if alert.due_date else None,
            })

        return actions


# Singleton instance
_alerts_service = None


def get_deal_alerts_service(db_session=None) -> ProactiveDealAlertsService:
    """Get or create the deal alerts service instance."""
    global _alerts_service
    if _alerts_service is None:
        _alerts_service = ProactiveDealAlertsService(db_session=db_session)
    elif db_session is not None:
        # Update the db session if provided
        _alerts_service.db = db_session
    return _alerts_service
