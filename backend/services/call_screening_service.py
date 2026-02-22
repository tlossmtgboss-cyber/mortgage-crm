"""
Call Screening Service

Multi-tier call screening for spam filtering:
1. Check whitelist (free, instant) → ALLOW
2. Check blocklist (free, instant) → BLOCK
3. Check lookup cache (free) → decision based on cached spam score
4. Phone Lookup API (paid) → decision based on spam score
5. Default for truly unknown → SCREEN (ask name/reason)
"""

import os
import re
import json
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class ScreeningDecision(Enum):
    """Possible screening decisions"""
    ALLOW = "allow"    # Known good caller, connect directly to AI
    BLOCK = "block"    # Known bad caller, hang up immediately
    SCREEN = "screen"  # Unknown caller, ask name and reason first


@dataclass
class ScreeningResult:
    """Result from call screening"""
    decision: ScreeningDecision
    reason: str
    caller_name: Optional[str] = None
    category: Optional[str] = None  # Whitelist category if matched
    spam_score: Optional[int] = None
    lookup_performed: bool = False
    lookup_cost_cents: int = 0
    extra_data: Dict[str, Any] = field(default_factory=dict)


class CallScreeningService:
    """
    Multi-tier call screening service for spam filtering.

    Screening order:
    1. Check whitelist → ALLOW (free, instant)
    2. Check blocklist → BLOCK (free, instant)
    3. Check lookup cache → decision based on cached spam score
    4. Phone Lookup API → decision based on spam score (~$0.05)
    5. Default → SCREEN (ask name/reason)
    """

    def __init__(self, db: Session):
        self.db = db
        self.spam_threshold = int(os.getenv("SPAM_SCORE_THRESHOLD", "60"))
        self.cache_ttl_days = int(os.getenv("LOOKUP_CACHE_TTL_DAYS", "30"))
        self.lookup_enabled = os.getenv("PHONE_LOOKUP_ENABLED", "true").lower() == "true"

    async def screen_call(self, phone_number: str, call_sid: str) -> ScreeningResult:
        """
        Main entry point for call screening.

        Args:
            phone_number: Caller's phone number
            call_sid: Call SID for logging

        Returns:
            ScreeningResult with decision and metadata
        """
        start_time = datetime.now(timezone.utc)

        # Normalize phone number
        phone = self._normalize_phone(phone_number)
        logger.info(f"Screening call from {phone} (SID: {call_sid})")

        # 1. Check whitelist first (known good callers)
        whitelist_result = await self._check_whitelist(phone)
        if whitelist_result:
            await self._log_screening_decision(call_sid, phone, whitelist_result, start_time)
            return whitelist_result

        # 1b. Check CRM for known contacts (leads, clients, team members)
        crm_result = await self._check_crm(phone)
        if crm_result:
            await self._log_screening_decision(call_sid, phone, crm_result, start_time)
            return crm_result

        # 2. Check blocklist (known bad callers)
        blocklist_result = await self._check_blocklist(phone)
        if blocklist_result:
            await self._log_screening_decision(call_sid, phone, blocklist_result, start_time)
            return blocklist_result

        # 3. Check lookup cache
        cached_result = await self._check_lookup_cache(phone)
        if cached_result:
            decision = self._decide_from_spam_score(cached_result.get("spam_score", 0))
            result = ScreeningResult(
                decision=decision,
                reason="cached_lookup",
                caller_name=cached_result.get("caller_name"),
                spam_score=cached_result.get("spam_score"),
                lookup_performed=False,
                extra_data={"cached": True, "lookup_data": cached_result}
            )
            await self._log_screening_decision(call_sid, phone, result, start_time)
            return result

        # 4. Perform Phone Lookup (if enabled)
        if self.lookup_enabled:
            lookup_result = await self._perform_phone_lookup(phone)
            if lookup_result and not lookup_result.get("error"):
                # Cache the result
                await self._cache_lookup_result(phone, lookup_result)

                # Decide based on spam score
                spam_score = lookup_result.get("spam_score", 0)
                decision = self._decide_from_spam_score(spam_score)

                result = ScreeningResult(
                    decision=decision,
                    reason=f"phone_lookup_spam_score_{spam_score}",
                    caller_name=lookup_result.get("caller_name"),
                    spam_score=spam_score,
                    lookup_performed=True,
                    lookup_cost_cents=5,  # Approximate cost
                    extra_data={"lookup_data": lookup_result}
                )
                await self._log_screening_decision(call_sid, phone, result, start_time)
                return result

        # 5. Default: Unknown caller → SCREEN
        result = ScreeningResult(
            decision=ScreeningDecision.SCREEN,
            reason="unknown_caller",
            lookup_performed=False
        )
        await self._log_screening_decision(call_sid, phone, result, start_time)
        return result

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to E.164 format."""
        # Remove all non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', phone)

        # Add +1 if it's a 10-digit US number
        if len(cleaned) == 10 and cleaned.isdigit():
            cleaned = f"+1{cleaned}"
        elif len(cleaned) == 11 and cleaned.startswith("1"):
            cleaned = f"+{cleaned}"
        elif not cleaned.startswith("+"):
            cleaned = f"+{cleaned}"

        return cleaned

    async def _check_whitelist(self, phone: str) -> Optional[ScreeningResult]:
        """Check if phone is whitelisted."""
        try:
            result = self.db.execute(text("""
                SELECT name, category, priority
                FROM phone_whitelist
                WHERE phone_number = :phone
            """), {"phone": phone})
            row = result.fetchone()

            if row:
                logger.info(f"Whitelist match for {phone}: {row[1]} ({row[0]})")
                return ScreeningResult(
                    decision=ScreeningDecision.ALLOW,
                    reason="whitelist_match",
                    caller_name=row[0],
                    category=row[1],
                    extra_data={"priority": row[2]}
                )
            return None
        except Exception as e:
            logger.error(f"Whitelist check error: {e}")
            return None

    async def _check_crm(self, phone: str) -> Optional[ScreeningResult]:
        """
        Check if phone belongs to a known contact in the CRM.
        Searches: lead_profiles, mum_client_profiles, users (team members)
        """
        # Normalize phone for matching (remove +1 prefix for comparison)
        phone_variants = [phone]
        if phone.startswith("+1"):
            phone_variants.append(phone[2:])  # Without +1
        elif phone.startswith("+"):
            phone_variants.append(phone[1:])  # Without +
        # Also try with +1 if not present
        if not phone.startswith("+"):
            phone_variants.append(f"+1{phone}")
            phone_variants.append(f"+{phone}")

        try:
            # 1. Check lead_profiles (prospective borrowers)
            result = self.db.execute(text("""
                SELECT first_name, last_name, email, phone, id
                FROM lead_profiles
                WHERE phone = ANY(:phones)
                   OR REPLACE(REPLACE(REPLACE(phone, '-', ''), ' ', ''), '(', '')
                      LIKE '%' || RIGHT(:phone_digits, 10)
                LIMIT 1
            """), {"phones": phone_variants, "phone_digits": phone.replace("+", "").replace("-", "")})
            row = result.fetchone()

            if row:
                name = f"{row[0]} {row[1]}".strip() if row[0] else row[1]
                logger.info(f"CRM Lead match for {phone}: {name}")
                return ScreeningResult(
                    decision=ScreeningDecision.ALLOW,
                    reason="crm_lead_match",
                    caller_name=name,
                    category="lead",
                    extra_data={"lead_id": str(row[4]), "email": row[2]}
                )

            # 2. Check mum_client_profiles (existing clients/funded loans)
            result = self.db.execute(text("""
                SELECT name, email, phone, id, loan_number
                FROM mum_client_profiles
                WHERE phone = ANY(:phones)
                   OR REPLACE(REPLACE(REPLACE(phone, '-', ''), ' ', ''), '(', '')
                      LIKE '%' || RIGHT(:phone_digits, 10)
                LIMIT 1
            """), {"phones": phone_variants, "phone_digits": phone.replace("+", "").replace("-", "")})
            row = result.fetchone()

            if row:
                logger.info(f"CRM Client match for {phone}: {row[0]}")
                return ScreeningResult(
                    decision=ScreeningDecision.ALLOW,
                    reason="crm_client_match",
                    caller_name=row[0],
                    category="client",
                    extra_data={"client_id": str(row[3]), "email": row[1], "loan_number": row[4]}
                )

            # 3. Check users table (team members)
            result = self.db.execute(text("""
                SELECT name, email, phone, id, role
                FROM users
                WHERE phone = ANY(:phones)
                   OR REPLACE(REPLACE(REPLACE(phone, '-', ''), ' ', ''), '(', '')
                      LIKE '%' || RIGHT(:phone_digits, 10)
                LIMIT 1
            """), {"phones": phone_variants, "phone_digits": phone.replace("+", "").replace("-", "")})
            row = result.fetchone()

            if row:
                logger.info(f"CRM Team member match for {phone}: {row[0]}")
                return ScreeningResult(
                    decision=ScreeningDecision.ALLOW,
                    reason="crm_team_match",
                    caller_name=row[0],
                    category="team",
                    extra_data={"user_id": str(row[3]), "email": row[1], "role": row[4]}
                )

            return None

        except Exception as e:
            logger.error(f"CRM check error: {e}")
            return None

    async def _check_blocklist(self, phone: str) -> Optional[ScreeningResult]:
        """Check if phone is blocked."""
        try:
            result = self.db.execute(text("""
                SELECT reason, spam_score, blocked_at, expires_at
                FROM phone_blocklist
                WHERE phone_number = :phone
                AND is_active = true
                AND (expires_at IS NULL OR expires_at > NOW())
            """), {"phone": phone})
            row = result.fetchone()

            if row:
                logger.warning(f"Blocklist match for {phone}: {row[0]}")

                # Increment call attempts counter
                self.db.execute(text("""
                    UPDATE phone_blocklist
                    SET call_attempts_since_block = call_attempts_since_block + 1
                    WHERE phone_number = :phone
                """), {"phone": phone})
                self.db.commit()

                return ScreeningResult(
                    decision=ScreeningDecision.BLOCK,
                    reason=f"blocklist_match_{row[0]}",
                    spam_score=row[1],
                    extra_data={"blocked_at": str(row[2]), "expires_at": str(row[3]) if row[3] else None}
                )
            return None
        except SQLAlchemyError as e:
            logger.error(f"Blocklist check error: {e}")
            return None

    async def _check_lookup_cache(self, phone: str) -> Optional[Dict[str, Any]]:
        """Check if we have cached lookup data."""
        try:
            result = self.db.execute(text("""
                SELECT carrier_name, carrier_type, line_type, caller_name,
                       spam_score, risk_level, lookup_data
                FROM phone_lookup_cache
                WHERE phone_number = :phone
                AND expires_at > NOW()
            """), {"phone": phone})
            row = result.fetchone()

            if row:
                logger.info(f"Cache hit for {phone}")
                return {
                    "carrier_name": row[0],
                    "carrier_type": row[1],
                    "line_type": row[2],
                    "caller_name": row[3],
                    "spam_score": row[4],
                    "risk_level": row[5],
                    "lookup_data": row[6]
                }
            return None
        except Exception as e:
            logger.error(f"Cache lookup error: {e}")
            return None

    async def _perform_phone_lookup(self, phone: str) -> Optional[Dict[str, Any]]:
        """Call Phone Lookup API for phone intelligence."""
        try:
            from integrations.phone_lookup_service import get_phone_lookup_service

            lookup_service = get_phone_lookup_service()
            if not lookup_service.is_enabled():
                logger.info("Phone Lookup service disabled")
                return None

            result = await lookup_service.lookup_phone(phone)

            return {
                "phone_number": result.phone_number,
                "valid": result.valid,
                "carrier_name": result.carrier_name,
                "carrier_type": result.carrier_type,
                "line_type": result.line_type,
                "caller_name": result.caller_name,
                "caller_type": result.caller_type,
                "country_code": result.country_code,
                "spam_score": result.spam_score,
                "risk_level": result.risk_level,
                "error": result.error
            }
        except Exception as e:
            logger.error(f"Phone Lookup error: {e}")
            return {"error": "Internal server error"}

    async def _cache_lookup_result(self, phone: str, result: Dict[str, Any]):
        """Cache lookup result to avoid repeated API calls."""
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(days=self.cache_ttl_days)

            # Upsert cache entry
            self.db.execute(text("""
                INSERT INTO phone_lookup_cache
                (phone_number, carrier_name, carrier_type, line_type, caller_name,
                 caller_type, country_code, spam_score, risk_level, lookup_data,
                 cached_at, expires_at)
                VALUES
                (:phone, :carrier_name, :carrier_type, :line_type, :caller_name,
                 :caller_type, :country_code, :spam_score, :risk_level, :lookup_data::jsonb,
                 NOW(), :expires_at)
                ON CONFLICT (phone_number) DO UPDATE SET
                    carrier_name = EXCLUDED.carrier_name,
                    carrier_type = EXCLUDED.carrier_type,
                    line_type = EXCLUDED.line_type,
                    caller_name = EXCLUDED.caller_name,
                    caller_type = EXCLUDED.caller_type,
                    country_code = EXCLUDED.country_code,
                    spam_score = EXCLUDED.spam_score,
                    risk_level = EXCLUDED.risk_level,
                    lookup_data = EXCLUDED.lookup_data,
                    cached_at = NOW(),
                    expires_at = EXCLUDED.expires_at
            """), {
                "phone": phone,
                "carrier_name": result.get("carrier_name"),
                "carrier_type": result.get("carrier_type"),
                "line_type": result.get("line_type"),
                "caller_name": result.get("caller_name"),
                "caller_type": result.get("caller_type"),
                "country_code": result.get("country_code"),
                "spam_score": result.get("spam_score"),
                "risk_level": result.get("risk_level"),
                "lookup_data": json.dumps(result),  # JSON string
                "expires_at": expires_at
            })
            self.db.commit()
            logger.info(f"Cached lookup for {phone} (expires {expires_at})")
        except SQLAlchemyError as e:
            logger.error(f"Cache write error: {e}")

    def _decide_from_spam_score(self, spam_score: int) -> ScreeningDecision:
        """Determine decision based on spam score."""
        if spam_score >= self.spam_threshold:
            return ScreeningDecision.BLOCK
        elif spam_score >= 30:
            return ScreeningDecision.SCREEN  # Medium risk, ask for verification
        else:
            return ScreeningDecision.ALLOW  # Low risk, let through

    async def _log_screening_decision(
        self,
        call_sid: str,
        phone: str,
        result: ScreeningResult,
        start_time: datetime
    ):
        """Log screening decision for analytics."""
        try:
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            self.db.execute(text("""
                INSERT INTO call_screening_log
                (call_sid, phone_number, screening_decision, decision_reason,
                 lookup_performed, lookup_result, lookup_cost_cents,
                 screening_duration_ms, connected_to_ai, created_at)
                VALUES
                (:call_sid, :phone, :decision, :reason,
                 :lookup_performed, :lookup_result::jsonb, :lookup_cost,
                 :duration_ms, :connected, NOW())
            """), {
                "call_sid": call_sid,
                "phone": phone,
                "decision": result.decision.value,
                "reason": result.reason,
                "lookup_performed": result.lookup_performed,
                "lookup_result": json.dumps(result.extra_data) if result.extra_data else None,
                "lookup_cost": result.lookup_cost_cents,
                "duration_ms": duration_ms,
                "connected": result.decision == ScreeningDecision.ALLOW
            })
            self.db.commit()

            logger.info(
                f"Screening logged: {phone} -> {result.decision.value} "
                f"({result.reason}) in {duration_ms}ms"
            )
        except SQLAlchemyError as e:
            logger.error(f"Failed to log screening decision: {e}")
            try:
                self.db.rollback()
            except Exception as e:
                logger.exception(f"Failed to rollback after screening log failure: {e}")


# Helper functions for use in other parts of the codebase

async def add_to_whitelist(
    db: Session,
    phone: str,
    name: str,
    category: str,
    source: str = "manual",
    lead_id: Optional[int] = None,
    added_by: Optional[int] = None
):
    """Add a phone number to the whitelist."""
    # Normalize phone
    phone = re.sub(r'[^\d+]', '', phone)
    if len(phone) == 10:
        phone = f"+1{phone}"
    elif not phone.startswith("+"):
        phone = f"+{phone}"

    try:
        db.execute(text("""
            INSERT INTO phone_whitelist
            (phone_number, name, category, source, lead_id, added_by, added_at)
            VALUES (:phone, :name, :category, :source, :lead_id, :added_by, NOW())
            ON CONFLICT (phone_number) DO UPDATE SET
                name = COALESCE(EXCLUDED.name, phone_whitelist.name),
                category = EXCLUDED.category,
                updated_at = NOW()
        """), {
            "phone": phone,
            "name": name,
            "category": category,
            "source": source,
            "lead_id": lead_id,
            "added_by": added_by
        })
        db.commit()
        logger.info(f"Added {phone} to whitelist ({category})")
    except SQLAlchemyError as e:
        logger.error(f"Failed to add to whitelist: {e}")
        db.rollback()


async def add_to_blocklist(
    db: Session,
    phone: str,
    reason: str,
    source: str = "manual",
    spam_score: Optional[int] = None,
    blocked_by: Optional[int] = None,
    expires_days: Optional[int] = None
):
    """Add a phone number to the blocklist."""
    # Normalize phone
    phone = re.sub(r'[^\d+]', '', phone)
    if len(phone) == 10:
        phone = f"+1{phone}"
    elif not phone.startswith("+"):
        phone = f"+{phone}"

    expires_at = None
    if expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

    try:
        db.execute(text("""
            INSERT INTO phone_blocklist
            (phone_number, reason, source, spam_score, blocked_by, blocked_at, expires_at)
            VALUES (:phone, :reason, :source, :spam_score, :blocked_by, NOW(), :expires_at)
            ON CONFLICT (phone_number) DO UPDATE SET
                reason = EXCLUDED.reason,
                is_active = true,
                expires_at = EXCLUDED.expires_at,
                updated_at = NOW()
        """), {
            "phone": phone,
            "reason": reason,
            "source": source,
            "spam_score": spam_score,
            "blocked_by": blocked_by,
            "expires_at": expires_at
        })
        db.commit()
        logger.info(f"Added {phone} to blocklist ({reason})")
    except SQLAlchemyError as e:
        logger.error(f"Failed to add to blocklist: {e}")
        db.rollback()
