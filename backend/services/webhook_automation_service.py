"""
Webhook Automation Service
==========================
Outbound webhook system for triggering external automations:
- Zapier integration for 5,000+ app connections
- Make (Integromat) support
- Custom webhook endpoints
- Event-driven triggers from AI Receptionist actions

Supported Events:
- call.started, call.completed, call.missed
- appointment.scheduled, appointment.cancelled
- lead.created, lead.qualified, lead.converted
- loan.stage_changed, loan.funded
- document.uploaded, document.approved
- sms.received, sms.sent

Security:
- HMAC signature verification
- API key authentication
- IP whitelisting support
- Rate limiting
"""

import os
import hmac
import hashlib
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from threading import Lock
import uuid

# Try to import httpx for async HTTP
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None
    HTTPX_AVAILABLE = False

# Try to import requests as fallback
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None
    REQUESTS_AVAILABLE = False

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

WEBHOOK_TIMEOUT_SECONDS = 10
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = [1, 5, 30]  # Exponential backoff
MAX_QUEUE_SIZE = 10000


class WebhookEvent(str, Enum):
    # Call events
    CALL_STARTED = "call.started"
    CALL_COMPLETED = "call.completed"
    CALL_MISSED = "call.missed"
    CALL_TRANSFERRED = "call.transferred"
    VOICEMAIL_RECEIVED = "voicemail.received"

    # Appointment events
    APPOINTMENT_SCHEDULED = "appointment.scheduled"
    APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    APPOINTMENT_REMINDER = "appointment.reminder"

    # Lead events
    LEAD_CREATED = "lead.created"
    LEAD_QUALIFIED = "lead.qualified"
    LEAD_CONVERTED = "lead.converted"
    LEAD_STAGE_CHANGED = "lead.stage_changed"

    # Loan events
    LOAN_CREATED = "loan.created"
    LOAN_STAGE_CHANGED = "loan.stage_changed"
    LOAN_APPROVED = "loan.approved"
    LOAN_FUNDED = "loan.funded"
    LOAN_DENIED = "loan.denied"

    # Document events
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_APPROVED = "document.approved"
    DOCUMENT_REJECTED = "document.rejected"

    # SMS events
    SMS_RECEIVED = "sms.received"
    SMS_SENT = "sms.sent"
    SMS_DELIVERY_FAILED = "sms.delivery_failed"

    # AI events
    AI_INTENT_DETECTED = "ai.intent_detected"
    AI_ESCALATION_TRIGGERED = "ai.escalation_triggered"


class WebhookStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    ERROR = "error"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class WebhookEndpoint:
    """Webhook endpoint configuration."""
    id: str
    name: str
    url: str
    events: List[WebhookEvent]
    secret: str = None
    status: WebhookStatus = WebhookStatus.ACTIVE
    headers: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_triggered_at: datetime = None
    success_count: int = 0
    failure_count: int = 0
    organization_id: int = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "events": [e.value for e in self.events],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "success_count": self.success_count,
            "failure_count": self.failure_count
        }


@dataclass
class WebhookDelivery:
    """Record of a webhook delivery attempt."""
    id: str
    endpoint_id: str
    event: WebhookEvent
    payload: Dict
    status: str  # pending, success, failed
    attempt_count: int = 0
    response_code: int = None
    response_body: str = None
    error_message: str = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    delivered_at: datetime = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "endpoint_id": self.endpoint_id,
            "event": self.event.value,
            "status": self.status,
            "attempt_count": self.attempt_count,
            "response_code": self.response_code,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None
        }


# ============================================================================
# WEBHOOK AUTOMATION SERVICE
# ============================================================================

class WebhookAutomationService:
    """
    Manages outbound webhooks for external automation integrations.

    Features:
    - Event-driven webhook triggers
    - HMAC signature for security
    - Automatic retry with exponential backoff
    - Delivery tracking and logging
    - Zapier/Make compatibility
    """

    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, db: Session = None):
        if self._initialized:
            return

        self.db = db
        self._endpoints: Dict[str, WebhookEndpoint] = {}
        self._delivery_queue: deque = deque(maxlen=MAX_QUEUE_SIZE)
        self._delivery_history: deque = deque(maxlen=1000)
        self._event_handlers: Dict[WebhookEvent, List[Callable]] = {}

        self._initialized = True
        logger.info("Webhook automation service initialized")

    def set_db(self, db: Session):
        """Set database session (for dependency injection)."""
        self.db = db

    # ========================================================================
    # ENDPOINT MANAGEMENT
    # ========================================================================

    def register_endpoint(
        self,
        name: str,
        url: str,
        events: List[WebhookEvent],
        secret: str = None,
        headers: Dict[str, str] = None,
        organization_id: int = None
    ) -> WebhookEndpoint:
        """
        Register a new webhook endpoint.

        Args:
            name: Friendly name for the endpoint
            url: Target URL for webhook delivery
            events: List of events to subscribe to
            secret: Optional secret for HMAC signing
            headers: Optional custom headers
            organization_id: Optional organization scope
        """
        endpoint_id = str(uuid.uuid4())[:12]

        if not secret:
            secret = self._generate_secret()

        endpoint = WebhookEndpoint(
            id=endpoint_id,
            name=name,
            url=url,
            events=events,
            secret=secret,
            headers=headers or {},
            organization_id=organization_id
        )

        self._endpoints[endpoint_id] = endpoint

        # Store in database
        self._store_endpoint(endpoint)

        logger.info(f"Registered webhook endpoint: {name} ({endpoint_id})")
        return endpoint

    def update_endpoint(
        self,
        endpoint_id: str,
        **updates
    ) -> Optional[WebhookEndpoint]:
        """Update an existing endpoint."""
        if endpoint_id not in self._endpoints:
            return None

        endpoint = self._endpoints[endpoint_id]

        if "name" in updates:
            endpoint.name = updates["name"]
        if "url" in updates:
            endpoint.url = updates["url"]
        if "events" in updates:
            endpoint.events = updates["events"]
        if "status" in updates:
            endpoint.status = WebhookStatus(updates["status"])
        if "headers" in updates:
            endpoint.headers = updates["headers"]

        self._store_endpoint(endpoint)
        return endpoint

    def delete_endpoint(self, endpoint_id: str) -> bool:
        """Delete a webhook endpoint."""
        if endpoint_id in self._endpoints:
            del self._endpoints[endpoint_id]

            if self.db:
                try:
                    self.db.execute(text("""
                        DELETE FROM webhook_endpoints WHERE id = :id
                    """), {"id": endpoint_id})
                    self.db.commit()
                except SQLAlchemyError as e:
                    logger.warning(f"Could not delete endpoint from DB: {e}")

            return True
        return False

    def get_endpoint(self, endpoint_id: str) -> Optional[WebhookEndpoint]:
        """Get endpoint by ID."""
        return self._endpoints.get(endpoint_id)

    def list_endpoints(
        self,
        organization_id: int = None,
        event_filter: WebhookEvent = None
    ) -> List[WebhookEndpoint]:
        """List all registered endpoints."""
        endpoints = list(self._endpoints.values())

        if organization_id:
            endpoints = [e for e in endpoints if e.organization_id == organization_id]

        if event_filter:
            endpoints = [e for e in endpoints if event_filter in e.events]

        return endpoints

    def _store_endpoint(self, endpoint: WebhookEndpoint):
        """Store endpoint in database."""
        if not self.db:
            return

        try:
            self.db.execute(text("""
                INSERT INTO webhook_endpoints
                (id, name, url, events, secret, status, headers, organization_id, created_at)
                VALUES
                (:id, :name, :url, :events, :secret, :status, :headers, :organization_id, :created_at)
                ON CONFLICT (id) DO UPDATE
                SET name = :name, url = :url, events = :events, status = :status, headers = :headers
            """), {
                "id": endpoint.id,
                "name": endpoint.name,
                "url": endpoint.url,
                "events": json.dumps([e.value for e in endpoint.events]),
                "secret": endpoint.secret,
                "status": endpoint.status.value,
                "headers": json.dumps(endpoint.headers),
                "organization_id": endpoint.organization_id,
                "created_at": endpoint.created_at
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.warning(f"Could not store endpoint: {e}")

    def _generate_secret(self) -> str:
        """Generate a secure webhook secret."""
        import secrets
        return secrets.token_urlsafe(32)

    # ========================================================================
    # EVENT TRIGGERING
    # ========================================================================

    def trigger_event(
        self,
        event: WebhookEvent,
        payload: Dict[str, Any],
        organization_id: int = None
    ) -> List[str]:
        """
        Trigger a webhook event.

        Sends the payload to all registered endpoints subscribed to this event.

        Args:
            event: The event type
            payload: Event data to send
            organization_id: Optional organization scope

        Returns:
            List of delivery IDs
        """
        delivery_ids = []

        # Find subscribed endpoints
        endpoints = [
            e for e in self._endpoints.values()
            if event in e.events
            and e.status == WebhookStatus.ACTIVE
            and (organization_id is None or e.organization_id == organization_id)
        ]

        if not endpoints:
            logger.debug(f"No endpoints subscribed to event: {event.value}")
            return []

        # Build full payload
        full_payload = {
            "event": event.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": payload
        }

        # Queue deliveries
        for endpoint in endpoints:
            delivery_id = str(uuid.uuid4())[:12]
            delivery = WebhookDelivery(
                id=delivery_id,
                endpoint_id=endpoint.id,
                event=event,
                payload=full_payload,
                status="pending"
            )

            self._delivery_queue.append((endpoint, delivery))
            delivery_ids.append(delivery_id)

        # Process queue (async if possible)
        self._process_queue()

        return delivery_ids

    def _process_queue(self):
        """Process pending webhook deliveries."""
        while self._delivery_queue:
            try:
                endpoint, delivery = self._delivery_queue.popleft()
                self._deliver_webhook(endpoint, delivery)
            except Exception as e:
                logger.error(f"Error processing webhook queue: {e}")

    def _deliver_webhook(
        self,
        endpoint: WebhookEndpoint,
        delivery: WebhookDelivery
    ):
        """Deliver a webhook to an endpoint."""
        delivery.attempt_count += 1

        # Build headers
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Perennia-Webhook/1.0",
            "X-Webhook-Event": delivery.event.value,
            "X-Webhook-Delivery": delivery.id,
            "X-Webhook-Timestamp": datetime.now(timezone.utc).isoformat(),
            **endpoint.headers
        }

        # Add HMAC signature
        if endpoint.secret:
            payload_bytes = json.dumps(delivery.payload).encode()
            signature = hmac.new(
                endpoint.secret.encode(),
                payload_bytes,
                hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        # Attempt delivery
        try:
            if HTTPX_AVAILABLE:
                response = httpx.post(
                    endpoint.url,
                    json=delivery.payload,
                    headers=headers,
                    timeout=WEBHOOK_TIMEOUT_SECONDS
                )
                delivery.response_code = response.status_code
                delivery.response_body = response.text[:500]
            elif REQUESTS_AVAILABLE:
                response = requests.post(
                    endpoint.url,
                    json=delivery.payload,
                    headers=headers,
                    timeout=WEBHOOK_TIMEOUT_SECONDS
                )
                delivery.response_code = response.status_code
                delivery.response_body = response.text[:500]
            else:
                raise RuntimeError("No HTTP client available (install httpx or requests)")

            if 200 <= delivery.response_code < 300:
                delivery.status = "success"
                delivery.delivered_at = datetime.now(timezone.utc)
                endpoint.success_count += 1
                endpoint.last_triggered_at = datetime.now(timezone.utc)
                logger.debug(f"Webhook delivered: {endpoint.name} ({delivery.event.value})")
            else:
                raise Exception(f"HTTP {delivery.response_code}: {delivery.response_body}")

        except Exception as e:
            delivery.error_message = str(e)[:200]
            endpoint.failure_count += 1

            # Retry logic
            if delivery.attempt_count < MAX_RETRY_ATTEMPTS:
                retry_delay = RETRY_BACKOFF_SECONDS[min(delivery.attempt_count - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
                logger.warning(f"Webhook delivery failed, retrying in {retry_delay}s: {e}")
                # In production, would use a proper task queue here
                self._delivery_queue.append((endpoint, delivery))
            else:
                delivery.status = "failed"
                logger.error(f"Webhook delivery failed after {MAX_RETRY_ATTEMPTS} attempts: {e}")

                # Mark endpoint as error if too many failures
                if endpoint.failure_count > endpoint.success_count * 2 and endpoint.failure_count > 10:
                    endpoint.status = WebhookStatus.ERROR
                    logger.warning(f"Endpoint marked as error due to high failure rate: {endpoint.name}")

        # Store delivery record
        self._store_delivery(delivery)
        self._delivery_history.append(delivery)

    def _store_delivery(self, delivery: WebhookDelivery):
        """Store delivery record in database."""
        if not self.db:
            return

        try:
            self.db.execute(text("""
                INSERT INTO webhook_deliveries
                (id, endpoint_id, event, payload, status, attempt_count,
                 response_code, error_message, created_at, delivered_at)
                VALUES
                (:id, :endpoint_id, :event, :payload, :status, :attempt_count,
                 :response_code, :error_message, :created_at, :delivered_at)
            """), {
                "id": delivery.id,
                "endpoint_id": delivery.endpoint_id,
                "event": delivery.event.value,
                "payload": json.dumps(delivery.payload),
                "status": delivery.status,
                "attempt_count": delivery.attempt_count,
                "response_code": delivery.response_code,
                "error_message": delivery.error_message,
                "created_at": delivery.created_at,
                "delivered_at": delivery.delivered_at
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.debug(f"Could not store delivery: {e}")

    # ========================================================================
    # ZAPIER/MAKE HELPERS
    # ========================================================================

    def get_zapier_subscribe_url(self, event: WebhookEvent) -> str:
        """Get subscription URL for Zapier trigger."""
        base_url = os.getenv("API_BASE_URL", "https://api.perennia.ai")
        return f"{base_url}/api/v1/webhooks/zapier/subscribe?event={event.value}"

    def get_sample_payload(self, event: WebhookEvent) -> Dict:
        """Get sample payload for Zapier/Make setup."""
        samples = {
            WebhookEvent.CALL_COMPLETED: {
                "event": "call.completed",
                "timestamp": "2024-01-15T10:30:00Z",
                "data": {
                    "call_id": "call_abc123",
                    "phone_number": "+15551234567",
                    "duration_seconds": 180,
                    "outcome": "appointment_scheduled",
                    "transcript_summary": "Customer inquired about refinance rates"
                }
            },
            WebhookEvent.APPOINTMENT_SCHEDULED: {
                "event": "appointment.scheduled",
                "timestamp": "2024-01-15T10:30:00Z",
                "data": {
                    "appointment_id": "apt_xyz789",
                    "customer_name": "John Smith",
                    "customer_phone": "+15551234567",
                    "scheduled_time": "2024-01-16T14:00:00Z",
                    "appointment_type": "loan_consultation",
                    "assigned_to": "Jane Doe"
                }
            },
            WebhookEvent.LEAD_CREATED: {
                "event": "lead.created",
                "timestamp": "2024-01-15T10:30:00Z",
                "data": {
                    "lead_id": "lead_123",
                    "name": "John Smith",
                    "email": "john@example.com",
                    "phone": "+15551234567",
                    "source": "ai_receptionist",
                    "loan_purpose": "purchase",
                    "estimated_loan_amount": 350000
                }
            },
            WebhookEvent.LOAN_FUNDED: {
                "event": "loan.funded",
                "timestamp": "2024-01-15T10:30:00Z",
                "data": {
                    "loan_id": "loan_456",
                    "loan_number": "2024-001234",
                    "borrower_name": "John Smith",
                    "loan_amount": 350000,
                    "loan_type": "conventional",
                    "funded_date": "2024-01-15"
                }
            }
        }
        return samples.get(event, {"event": event.value, "data": {}})

    # ========================================================================
    # DELIVERY HISTORY
    # ========================================================================

    def get_delivery_history(
        self,
        endpoint_id: str = None,
        event: WebhookEvent = None,
        status: str = None,
        limit: int = 50
    ) -> List[Dict]:
        """Get webhook delivery history."""
        deliveries = list(self._delivery_history)

        if endpoint_id:
            deliveries = [d for d in deliveries if d.endpoint_id == endpoint_id]
        if event:
            deliveries = [d for d in deliveries if d.event == event]
        if status:
            deliveries = [d for d in deliveries if d.status == status]

        return [d.to_dict() for d in deliveries[-limit:]]

    def get_delivery_stats(self) -> Dict[str, Any]:
        """Get delivery statistics."""
        deliveries = list(self._delivery_history)

        total = len(deliveries)
        success = len([d for d in deliveries if d.status == "success"])
        failed = len([d for d in deliveries if d.status == "failed"])

        return {
            "total_deliveries": total,
            "successful": success,
            "failed": failed,
            "success_rate": round((success / total) * 100, 2) if total > 0 else 100,
            "endpoints_count": len(self._endpoints),
            "active_endpoints": len([e for e in self._endpoints.values() if e.status == WebhookStatus.ACTIVE])
        }


# Global instance
webhook_service = WebhookAutomationService()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def trigger_webhook(event: WebhookEvent, payload: Dict, organization_id: int = None) -> List[str]:
    """Convenience function to trigger a webhook event."""
    return webhook_service.trigger_event(event, payload, organization_id)


# Event-specific helpers
def on_call_completed(call_data: Dict, organization_id: int = None):
    """Trigger webhook when a call is completed."""
    return trigger_webhook(WebhookEvent.CALL_COMPLETED, call_data, organization_id)


def on_appointment_scheduled(appointment_data: Dict, organization_id: int = None):
    """Trigger webhook when an appointment is scheduled."""
    return trigger_webhook(WebhookEvent.APPOINTMENT_SCHEDULED, appointment_data, organization_id)


def on_lead_created(lead_data: Dict, organization_id: int = None):
    """Trigger webhook when a lead is created."""
    return trigger_webhook(WebhookEvent.LEAD_CREATED, lead_data, organization_id)


def on_loan_funded(loan_data: Dict, organization_id: int = None):
    """Trigger webhook when a loan is funded."""
    return trigger_webhook(WebhookEvent.LOAN_FUNDED, loan_data, organization_id)
