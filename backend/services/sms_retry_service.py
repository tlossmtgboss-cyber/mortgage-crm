"""SMS Retry Service — reliable SMS delivery with retry, dead letter queue, and circuit breaker.

Wraps SMS send operations with automatic retry (exponential backoff),
dead letter handling for messages that fail after all retries,
and a circuit breaker to avoid hammering Telnyx when the API is down.
"""

import logging
import asyncio
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class SMSDeliveryStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class SMSRetryService:
    """Reliable SMS delivery with retry, dead letter, and circuit breaker."""

    MAX_RETRIES = 3
    BASE_DELAY_SECONDS = 2  # Exponential backoff: 2s, 4s, 8s

    # Circuit breaker state (class-level so shared across instances)
    _circuit_state = "closed"  # closed, open, half_open
    _failure_count = 0
    _failure_threshold = 5
    _circuit_opened_at: Optional[float] = None
    _circuit_cooldown_seconds = 30

    def __init__(self, telnyx_api_key: Optional[str] = None, db=None):
        self._api_key = telnyx_api_key
        self._db = db  # Optional SQLAlchemy Session for DB-backed dead letter
        self._dead_letter_queue: list = []  # In-memory fallback when no DB session

    # -----------------------------------------------------------------
    # Circuit breaker
    # -----------------------------------------------------------------

    def _check_circuit(self) -> bool:
        """Check if circuit breaker allows requests. Returns True if request can proceed."""
        if self._circuit_state == "closed":
            return True
        if self._circuit_state == "open":
            if self._circuit_opened_at and (time.time() - self._circuit_opened_at > self._circuit_cooldown_seconds):
                SMSRetryService._circuit_state = "half_open"
                logger.info("Circuit breaker half-open, testing connectivity")
                return True
            return False
        if self._circuit_state == "half_open":
            return True
        return True

    def _record_success(self):
        """Record a successful API call."""
        if self._circuit_state == "half_open":
            SMSRetryService._circuit_state = "closed"
            SMSRetryService._failure_count = 0
            logger.info("Circuit breaker closed — Telnyx API recovered")
        SMSRetryService._failure_count = 0

    def _record_failure(self):
        """Record a failed API call."""
        SMSRetryService._failure_count += 1
        if self._circuit_state == "half_open":
            SMSRetryService._circuit_state = "open"
            SMSRetryService._circuit_opened_at = time.time()
            logger.warning("Circuit breaker re-opened after half-open failure")
        elif self._failure_count >= self._failure_threshold:
            SMSRetryService._circuit_state = "open"
            SMSRetryService._circuit_opened_at = time.time()
            logger.warning(
                "Circuit breaker opened — Telnyx API failure threshold reached",
                extra={"failure_count": self._failure_count},
            )

    # -----------------------------------------------------------------
    # Core send with retry
    # -----------------------------------------------------------------

    async def send_sms_with_retry(
        self,
        to_phone: str,
        from_phone: str,
        message: str,
        messaging_profile_id: Optional[str] = None,
        organization_id: Optional[int] = None,
        workflow_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send SMS with automatic retry on transient failures.

        Returns dict with status, attempt count, and message_id on success.
        On permanent failure after all retries, adds to dead letter queue.
        """
        log_extra = {
            "to_phone_last4": to_phone[-4:] if len(to_phone) >= 4 else "****",
            "organization_id": str(organization_id) if organization_id else None,
            "workflow_id": str(workflow_id) if workflow_id else None,
        }

        # Circuit breaker check — skip retry loop entirely if open
        if not self._check_circuit():
            logger.warning("Circuit breaker open — SMS not attempted", extra=log_extra)
            self._persist_dead_letter(
                to_phone=to_phone,
                from_phone=from_phone,
                message=message,
                organization_id=organization_id,
                workflow_id=workflow_id,
                last_error="Circuit breaker open",
                metadata=metadata,
            )
            return {
                "status": SMSDeliveryStatus.DEAD_LETTER.value,
                "attempt": 0,
                "error": "Circuit breaker open",
            }

        last_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = await self._send_sms(
                    to_phone=to_phone,
                    from_phone=from_phone,
                    message=message,
                    messaging_profile_id=messaging_profile_id,
                )

                self._record_success()

                logger.info(
                    "SMS sent successfully",
                    extra={**log_extra, "attempt": attempt},
                )

                return {
                    "status": SMSDeliveryStatus.SENT.value,
                    "attempt": attempt,
                    "message_id": result.get("message_id"),
                }

            except Exception as e:
                last_error = str(e)
                self._record_failure()

                logger.warning(
                    "SMS send failed, will retry" if attempt < self.MAX_RETRIES else "SMS send failed, max retries reached",
                    extra={
                        **log_extra,
                        "attempt": attempt,
                        "max_retries": self.MAX_RETRIES,
                        "error": last_error,
                    },
                )

                if attempt < self.MAX_RETRIES:
                    delay = self.BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)

        # All retries exhausted — dead letter
        self._persist_dead_letter(
            to_phone=to_phone,
            from_phone=from_phone,
            message=message,
            organization_id=organization_id,
            workflow_id=workflow_id,
            last_error=last_error,
            metadata=metadata,
        )

        logger.error(
            "SMS moved to dead letter queue",
            extra={**log_extra, "last_error": last_error},
        )

        return {
            "status": SMSDeliveryStatus.DEAD_LETTER.value,
            "attempt": self.MAX_RETRIES,
            "error": last_error,
        }

    # -----------------------------------------------------------------
    # Dead letter persistence
    # -----------------------------------------------------------------

    def _persist_dead_letter(
        self,
        to_phone: str,
        from_phone: str,
        message: str,
        organization_id: Optional[int],
        workflow_id: Optional[int],
        last_error: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ):
        """Persist a dead letter entry to DB (preferred) or in-memory fallback."""
        if self._db:
            from database.models.sms_dead_letter import SMSDeadLetter
            dead_letter = SMSDeadLetter(
                to_phone=to_phone,
                from_phone=from_phone,
                message=message,
                organization_id=organization_id,
                workflow_id=workflow_id,
                last_error=last_error,
                attempts=self.MAX_RETRIES,
                extra_metadata=metadata or {},
            )
            self._db.add(dead_letter)
            self._db.flush()
        else:
            # Fallback to in-memory for backwards compatibility
            dead_letter_entry = {
                "to_phone": to_phone,
                "from_phone": from_phone,
                "message": message,
                "organization_id": organization_id,
                "workflow_id": workflow_id,
                "last_error": last_error,
                "attempts": self.MAX_RETRIES,
                "dead_lettered_at": datetime.utcnow().isoformat(),
                "metadata": metadata or {},
            }
            self._dead_letter_queue.append(dead_letter_entry)

    # -----------------------------------------------------------------
    # Telnyx API call
    # -----------------------------------------------------------------

    async def _send_sms(
        self,
        to_phone: str,
        from_phone: str,
        message: str,
        messaging_profile_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Actually send SMS via Telnyx. Raises on failure."""
        import httpx
        import os

        api_key = self._api_key or os.getenv("TELNYX_API_KEY")
        if not api_key:
            raise ValueError("TELNYX_API_KEY not configured")

        payload = {
            "from": from_phone,
            "to": to_phone,
            "text": message,
        }
        if messaging_profile_id:
            payload["messaging_profile_id"] = messaging_profile_id

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.telnyx.com/v2/messages",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {"message_id": data.get("data", {}).get("id")}

    # -----------------------------------------------------------------
    # Dead letter queue access
    # -----------------------------------------------------------------

    def get_dead_letter_queue(self, organization_id: Optional[int] = None) -> list:
        """Get dead letter entries, optionally filtered by organization."""
        if self._db:
            from database.models.sms_dead_letter import SMSDeadLetter
            query = self._db.query(SMSDeadLetter).filter(SMSDeadLetter.status == "pending")
            if organization_id is not None:
                query = query.filter(SMSDeadLetter.organization_id == organization_id)
            return [
                {
                    "id": dl.id,
                    "to_phone": dl.to_phone,
                    "from_phone": dl.from_phone,
                    "message": dl.message,
                    "organization_id": dl.organization_id,
                    "workflow_id": dl.workflow_id,
                    "last_error": dl.last_error,
                    "attempts": dl.attempts,
                    "dead_lettered_at": dl.created_at.isoformat() if dl.created_at else None,
                }
                for dl in query.order_by(SMSDeadLetter.created_at.desc()).all()
            ]
        # Fallback to in-memory
        if organization_id is None:
            return list(self._dead_letter_queue)
        return [e for e in self._dead_letter_queue if e.get("organization_id") == organization_id]

    def retry_dead_letter(self, entry_id) -> Optional[Dict]:
        """Remove an entry from dead letter queue for manual retry.

        When DB-backed, entry_id is the SMSDeadLetter.id (int).
        When in-memory, entry_id is the list index (int).
        """
        if self._db:
            from database.models.sms_dead_letter import SMSDeadLetter
            dl = self._db.query(SMSDeadLetter).filter(
                SMSDeadLetter.id == entry_id,
                SMSDeadLetter.status == "pending",
            ).first()
            if dl is None:
                return None
            dl.status = "retried"
            dl.retried_at = datetime.utcnow()
            self._db.flush()
            return {
                "id": dl.id,
                "to_phone": dl.to_phone,
                "from_phone": dl.from_phone,
                "message": dl.message,
                "organization_id": dl.organization_id,
                "workflow_id": dl.workflow_id,
                "last_error": dl.last_error,
            }
        # Fallback to in-memory (index-based)
        index = entry_id
        if 0 <= index < len(self._dead_letter_queue):
            return self._dead_letter_queue.pop(index)
        return None

    def dead_letter_count(self, organization_id: Optional[int] = None) -> int:
        """Count of messages in dead letter queue."""
        if self._db:
            from database.models.sms_dead_letter import SMSDeadLetter
            query = self._db.query(SMSDeadLetter).filter(SMSDeadLetter.status == "pending")
            if organization_id is not None:
                query = query.filter(SMSDeadLetter.organization_id == organization_id)
            return query.count()
        # Fallback to in-memory
        if organization_id is None:
            return len(self._dead_letter_queue)
        return len([e for e in self._dead_letter_queue if e.get("organization_id") == organization_id])
