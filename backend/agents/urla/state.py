"""
Perennia AI — URLA State Manager
================================
Redis-backed state persistence for the URLA voice agent.

Key schema (multi-tenant, resumable):
    urla:{tenant_id}:loan:{loan_id}          -> serialized URLAApplication JSON
    urla:{tenant_id}:phone:{phone}           -> set of loan_ids for that caller
    urla:{tenant_id}:active:{phone}          -> most recently active loan_id

TTL: 30 days on loan records by default (extended on every write). Configurable
via URLA_SESSION_TTL_SECONDS env var.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import redis.asyncio as aioredis
from cryptography.fernet import Fernet

from .models import URLAApplication, Borrower

logger = logging.getLogger(__name__)


DEFAULT_TTL_SECONDS = int(os.getenv("URLA_SESSION_TTL_SECONDS", str(30 * 24 * 3600)))


class URLAStateManager:
    """
    Async Redis state manager for URLA applications.

    Usage:
        state = URLAStateManager(redis_url="redis://...")
        app = await state.create_application(tenant_id="perennia", caller_phone="+18435551212")
        ...
        await state.save_application(app)
        resumed = await state.get_active_application(tenant_id, caller_phone)
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.ttl_seconds = ttl_seconds
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        if self._redis is None:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    @property
    def redis(self) -> aioredis.Redis:
        if self._redis is None:
            raise RuntimeError("URLAStateManager not connected. Call connect() first.")
        return self._redis

    # ------------------------------------------------------------------
    # KEY BUILDERS
    # ------------------------------------------------------------------

    @staticmethod
    def _loan_key(tenant_id: str, loan_id: str) -> str:
        return f"urla:{tenant_id}:loan:{loan_id}"

    @staticmethod
    def _phone_index_key(tenant_id: str, phone: str) -> str:
        return f"urla:{tenant_id}:phone:{phone}"

    @staticmethod
    def _active_key(tenant_id: str, phone: str) -> str:
        return f"urla:{tenant_id}:active:{phone}"

    # ------------------------------------------------------------------
    # CREATE / LOAD / SAVE
    # ------------------------------------------------------------------

    @staticmethod
    def generate_loan_id() -> str:
        """Short, caller-friendly loan ID. ~62^8 collision space."""
        return f"URLA-{uuid.uuid4().hex[:8].upper()}"

    async def create_application(
        self,
        tenant_id: str,
        caller_phone: str,
        force_new: bool = False,
    ) -> URLAApplication:
        """
        Create a new URLA record. Initializes with a primary borrower stub
        so the agent can start filling Section 1a immediately.

        Uses a Redis WATCH/MULTI pipeline on the active pointer to prevent
        race conditions when concurrent calls arrive from the same phone.
        If an active, non-finalized application already exists (and
        ``force_new`` is False), returns it instead of creating a duplicate.
        """
        await self.connect()
        active_key = self._active_key(tenant_id, caller_phone)

        # Unless explicitly asked for a new app, return the existing active one
        if not force_new:
            existing_id = await self.redis.get(active_key)
            if existing_id:
                existing = await self.load_application(tenant_id, existing_id)
                if existing and not existing.is_finalized:
                    return existing

        loan_id = self.generate_loan_id()
        app = URLAApplication(
            loan_id=loan_id,
            tenant_id=tenant_id,
            caller_phone=caller_phone,
            current_section="SECTION_1A",
            borrowers=[Borrower(borrower_id="borrower_1", is_primary=True)],
        )

        # Atomically write loan record + phone index + active pointer
        payload = app.model_dump_json(exclude_none=True)
        cipher = self._get_cipher()
        if cipher:
            payload = cipher.encrypt(payload.encode()).decode()

        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.watch(active_key)
            pipe.multi()
            pipe.set(self._loan_key(tenant_id, loan_id), payload, ex=self.ttl_seconds)
            pipe.sadd(self._phone_index_key(tenant_id, caller_phone), loan_id)
            pipe.expire(self._phone_index_key(tenant_id, caller_phone), self.ttl_seconds)
            pipe.set(active_key, loan_id, ex=self.ttl_seconds)
            await pipe.execute()

        return app

    # ------------------------------------------------------------------
    # ENCRYPTION
    # ------------------------------------------------------------------

    def _get_cipher(self) -> Optional[Fernet]:
        """
        Return a Fernet cipher derived from the URLA_ENCRYPTION_KEY env var.
        Returns None (plaintext mode) if the key is not set — suitable for
        local dev, but a WARNING is logged on first call.
        """
        key = os.getenv("URLA_ENCRYPTION_KEY", "")
        if not key:
            logger.warning(
                "URLA_ENCRYPTION_KEY not set — PII stored as plaintext in Redis. "
                "Set this env var in production."
            )
            return None
        # Derive a valid 32-byte Fernet key from any arbitrary string
        derived = hashlib.sha256(key.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(derived))

    # ------------------------------------------------------------------
    # SAVE / LOAD
    # ------------------------------------------------------------------

    async def save_application(self, app: URLAApplication) -> None:
        """Persist the full application record; refresh TTL."""
        await self.connect()
        app.updated_at = datetime.now(timezone.utc)
        payload = app.model_dump_json(exclude_none=True)

        cipher = self._get_cipher()
        if cipher:
            payload = cipher.encrypt(payload.encode()).decode()

        await self.redis.set(
            self._loan_key(app.tenant_id, app.loan_id),
            payload,
            ex=self.ttl_seconds,
        )

    async def load_application(
        self,
        tenant_id: str,
        loan_id: str,
    ) -> Optional[URLAApplication]:
        await self.connect()
        raw = await self.redis.get(self._loan_key(tenant_id, loan_id))
        if raw is None:
            return None

        cipher = self._get_cipher()
        if cipher and raw:
            try:
                raw = cipher.decrypt(raw.encode()).decode()
            except Exception:
                pass  # Fallback: data may be unencrypted (migration period)

        return URLAApplication.model_validate_json(raw)

    async def get_active_application(
        self,
        tenant_id: str,
        caller_phone: str,
    ) -> Optional[URLAApplication]:
        """
        Return the most recently active loan for this phone, if any.
        Used to resume on callback.
        """
        await self.connect()
        active_id = await self.redis.get(self._active_key(tenant_id, caller_phone))
        if not active_id:
            return None
        app = await self.load_application(tenant_id, active_id)
        # If the record expired but the active pointer lingered, clean up
        if app is None:
            await self.redis.delete(self._active_key(tenant_id, caller_phone))
        return app

    async def list_applications_for_phone(
        self,
        tenant_id: str,
        caller_phone: str,
    ) -> List[str]:
        await self.connect()
        members = await self.redis.smembers(self._phone_index_key(tenant_id, caller_phone))
        return sorted(members)

    async def mark_section_complete(
        self,
        app: URLAApplication,
        section_name: str,
        next_section: Optional[str] = None,
    ) -> None:
        if section_name not in app.completed_sections:
            app.completed_sections.append(section_name)
        if next_section:
            app.current_section = next_section
        await self.save_application(app)

    async def pause(self, app: URLAApplication) -> None:
        """Explicit pause — same as save but clarifies intent for observability."""
        app.current_section = f"PAUSED:{app.current_section}"
        await self.save_application(app)

    async def resume(self, app: URLAApplication) -> None:
        if app.current_section.startswith("PAUSED:"):
            app.current_section = app.current_section.replace("PAUSED:", "", 1)
        await self.save_application(app)

    async def finalize(self, app: URLAApplication) -> None:
        """
        Mark BytePro submission complete. Does NOT clear the active pointer —
        that happens in complete_session() after LO kickoff booking (or explicit
        skip) so the caller can resume into the booking flow if they drop.
        """
        app.is_finalized = True
        app.finalized_at = datetime.now(timezone.utc)
        app.current_section = "LO_KICKOFF_BOOKING"
        if "FINALIZED" not in app.completed_sections:
            app.completed_sections.append("FINALIZED")
        await self.save_application(app)

    async def complete_session(self, app: URLAApplication) -> None:
        """
        Fully wrap the session after LO kickoff booking (or explicit skip).
        Clears the active phone->loan pointer so a future call starts fresh.
        The loan record itself stays in Redis for the rest of its TTL.
        """
        app.current_section = "COMPLETE"
        if "COMPLETE" not in app.completed_sections:
            app.completed_sections.append("COMPLETE")
        await self.save_application(app)
        await self.redis.delete(self._active_key(app.tenant_id, app.caller_phone))
