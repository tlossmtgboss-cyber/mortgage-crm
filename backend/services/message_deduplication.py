"""
Message Deduplication Service

Prevents duplicate message processing caused by:
- Network retries
- User double-clicks
- Client-side bugs
- Race conditions

Uses Redis for atomic check-and-set operations.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import UUID
import redis

logger = logging.getLogger(__name__)


class MessageDeduplicator:
    """Prevent duplicate message processing with atomic operations"""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.DUPLICATE_WINDOW = 60  # seconds
        self.PROCESSING_LOCK_TTL = 30  # seconds

    def get_message_hash(self, session_id: UUID, content: str) -> str:
        """Generate unique hash for message"""
        # Normalize content
        normalized = content.lower().strip()
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        # Combine with session
        combined = f"{session_id}:{normalized}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    async def is_duplicate(
        self,
        session_id: UUID,
        content: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if message is duplicate within window.

        Returns:
            Tuple of (is_duplicate, cached_response_id if available)
        """
        msg_hash = self.get_message_hash(session_id, content)
        key = f"msg_seen:{msg_hash}"

        try:
            # Check if we've seen this message
            cached = self.redis.get(key)

            if cached:
                logger.info(f"Duplicate message detected: {msg_hash}")
                # Return the response ID if we cached it
                response_key = f"msg_response:{msg_hash}"
                response_id = self.redis.get(response_key)
                return True, response_id

            return False, None

        except redis.RedisError as e:
            logger.error(f"Redis error in deduplication check: {e}")
            # Fail open - allow processing on Redis errors
            return False, None

    async def mark_seen(
        self,
        session_id: UUID,
        content: str,
        response_id: Optional[str] = None
    ):
        """
        Mark message as seen with optional response ID for retrieval.

        Args:
            session_id: Chat session ID
            content: Message content
            response_id: Optional ID of the response message for retrieval
        """
        msg_hash = self.get_message_hash(session_id, content)
        key = f"msg_seen:{msg_hash}"

        try:
            self.redis.setex(key, self.DUPLICATE_WINDOW, "1")

            if response_id:
                response_key = f"msg_response:{msg_hash}"
                self.redis.setex(response_key, self.DUPLICATE_WINDOW, response_id)

        except redis.RedisError as e:
            logger.error(f"Redis error marking message seen: {e}")

    async def acquire_processing_lock(
        self,
        session_id: UUID,
        content: str
    ) -> bool:
        """
        Atomic check-and-set for message processing.
        Ensures only one process handles a message.

        Returns:
            True if this process should handle the message, False otherwise
        """
        msg_hash = self.get_message_hash(session_id, content)
        lock_key = f"msg_lock:{msg_hash}"

        try:
            # Try to acquire lock (NX = only set if doesn't exist)
            acquired = self.redis.set(
                lock_key,
                datetime.now(timezone.utc).isoformat(),
                nx=True,
                ex=self.PROCESSING_LOCK_TTL
            )

            if acquired:
                logger.debug(f"Acquired processing lock: {msg_hash}")
                return True

            logger.debug(f"Lock already held: {msg_hash}")
            return False

        except redis.RedisError as e:
            logger.error(f"Redis error acquiring lock: {e}")
            # Fail open - allow processing
            return True

    async def release_processing_lock(
        self,
        session_id: UUID,
        content: str
    ):
        """Release processing lock after completion"""
        msg_hash = self.get_message_hash(session_id, content)
        lock_key = f"msg_lock:{msg_hash}"

        try:
            self.redis.delete(lock_key)
        except redis.RedisError as e:
            logger.error(f"Redis error releasing lock: {e}")

    async def get_idempotency_stats(self) -> dict:
        """Get deduplication statistics"""
        try:
            # Count keys by pattern
            seen_count = len(list(self.redis.scan_iter("msg_seen:*")))
            lock_count = len(list(self.redis.scan_iter("msg_lock:*")))

            return {
                'messages_tracked': seen_count,
                'active_locks': lock_count,
                'duplicate_window_seconds': self.DUPLICATE_WINDOW,
            }

        except redis.RedisError as e:
            logger.error(f"Redis error getting stats: {e}")
            return {
                'error': str(e),
                'messages_tracked': 0,
                'active_locks': 0,
            }


class IdempotencyKeyGenerator:
    """Generate idempotency keys for various operations"""

    @staticmethod
    def for_message(session_id: UUID, content: str, timestamp_ms: int) -> str:
        """Generate idempotency key for chat message"""
        combined = f"msg:{session_id}:{content}:{timestamp_ms}"
        return hashlib.sha256(combined.encode()).hexdigest()[:24]

    @staticmethod
    def for_call_request(session_id: UUID, phone: str) -> str:
        """Generate idempotency key for call request"""
        # Only allow one call request per session per 5-minute window
        window = int(datetime.now(timezone.utc).timestamp()) // 300
        combined = f"call:{session_id}:{phone}:{window}"
        return hashlib.sha256(combined.encode()).hexdigest()[:24]

    @staticmethod
    def for_cta_response(session_id: UUID, cta_type: str) -> str:
        """Generate idempotency key for CTA response"""
        combined = f"cta:{session_id}:{cta_type}"
        return hashlib.sha256(combined.encode()).hexdigest()[:24]
