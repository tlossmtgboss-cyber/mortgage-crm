"""SMS Opt-Out Manager - Mortgage CRM A+ Module #11
TCPA-compliant opt-out processing: handle STOP/UNSTOP keywords,
persist opt-out lists, validate before every send.
"""
import re
import logging
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Keywords that trigger opt-out (TCPA §227.900-227.908)
OPT_OUT_KEYWORDS: Set[str] = {
    "stop", "stopall", "unsubscribe", "cancel", "end", "quit", "revoke"
}

# Keywords that re-subscribe (opt back in)
OPT_IN_KEYWORDS: Set[str] = {
    "start", "yes", "unstop", "subscribe"
}

# HELP keyword response
HELP_KEYWORDS: Set[str] = {"help", "info"}


class SMSOptOutManager:
    """Manage TCPA-compliant opt-out/opt-in lifecycle for SMS."""

    def __init__(self, db=None):
        self.db = db
        # In-memory store: phone_number -> opt-out record
        # In production this syncs with the DB
        self._opted_out: Dict[str, Dict[str, Any]] = {}

    # ── Core checks ──────────────────────────────────────────────────────────
    def is_opted_out(self, phone: str, tenant_id: Optional[str] = None) -> bool:
        """Return True if the phone number has opted out."""
        normalized = self._normalize_phone(phone)

        # Check in-memory cache
        key = f"{tenant_id}:{normalized}" if tenant_id else normalized
        if key in self._opted_out:
            return True

        # Check DB if available
        if self.db:
            try:
                from models.sms_models import SMSOptOut
                record = self.db.query(SMSOptOut).filter(
                    SMSOptOut.phone_number == normalized,
                    SMSOptOut.active == True,
                ).first()
                if record:
                    self._opted_out[key] = {"phone": normalized, "opted_out_at": record.opted_out_at}
                    return True
            except ImportError:
                # Fallback: raw SQL if ORM model not importable
                try:
                    from sqlalchemy import text
                    row = self.db.execute(
                        text("SELECT id FROM sms_opt_outs WHERE phone_number = :phone AND active = TRUE LIMIT 1"),
                        {"phone": normalized},
                    ).fetchone()
                    if row:
                        self._opted_out[key] = {"phone": normalized, "opted_out_at": datetime.now(timezone.utc).isoformat()}
                        return True
                except Exception as e2:
                    logger.debug(f"DB opt-out check skipped: {e2}")
            except Exception as e:
                logger.debug(f"DB opt-out check skipped: {e}")

        return False

    def opt_out(self, phone: str, reason: str = "STOP keyword", tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Record an opt-out for the given phone number."""
        normalized = self._normalize_phone(phone)
        key = f"{tenant_id}:{normalized}" if tenant_id else normalized
        record = {
            "phone": normalized,
            "reason": reason,
            "opted_out_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id,
        }
        self._opted_out[key] = record
        logger.info(f"Opt-out recorded: {normalized} (reason: {reason})")

        # Persist to DB
        if self.db:
            try:
                from sqlalchemy import text
                self.db.execute(
                    text("""
                        INSERT INTO sms_opt_outs (phone_number, opt_out_keyword, organization_id, opted_out_at, active)
                        VALUES (:phone, :keyword, :org_id, NOW(), TRUE)
                        ON CONFLICT (phone_number) DO UPDATE
                          SET active = TRUE, opted_out_at = NOW(), opt_out_keyword = :keyword,
                              organization_id = COALESCE(:org_id, sms_opt_outs.organization_id)
                    """),
                    {"phone": normalized, "keyword": reason[:20], "org_id": int(tenant_id) if tenant_id and tenant_id.isdigit() else None},
                )
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.error(f"Failed to persist opt-out to DB: {e}")

        return record

    def opt_in(self, phone: str, tenant_id: Optional[str] = None) -> bool:
        """Re-subscribe a previously opted-out number."""
        normalized = self._normalize_phone(phone)
        key = f"{tenant_id}:{normalized}" if tenant_id else normalized
        removed = self._opted_out.pop(key, None)

        # Update DB
        if self.db:
            try:
                from sqlalchemy import text
                self.db.execute(
                    text("""
                        UPDATE sms_opt_outs SET active = FALSE, opted_in_at = NOW()
                        WHERE phone_number = :phone
                    """),
                    {"phone": normalized},
                )
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.error(f"Failed to update opt-in in DB: {e}")

        if removed:
            logger.info(f"Opt-in (re-subscribe): {normalized}")
            return True
        return False

    # ── Inbound keyword processing ───────────────────────────────────────────
    def process_inbound(self, from_phone: str, message_body: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process an inbound SMS for opt-out/opt-in keywords.
        Returns action taken and suggested auto-reply.
        """
        keyword = self._extract_keyword(message_body)
        result = {
            "keyword": keyword,
            "action": "none",
            "auto_reply": None,
            "phone": from_phone,
        }

        if keyword in OPT_OUT_KEYWORDS:
            self.opt_out(from_phone, reason=f"Keyword: {keyword.upper()}", tenant_id=tenant_id)
            result["action"] = "opted_out"
            result["auto_reply"] = (
                "You have been unsubscribed and will receive no further messages. "
                "Reply START to re-subscribe at any time."
            )

        elif keyword in OPT_IN_KEYWORDS:
            self.opt_in(from_phone, tenant_id=tenant_id)
            result["action"] = "opted_in"
            result["auto_reply"] = (
                "You have been re-subscribed. Welcome back! "
                "Reply STOP at any time to unsubscribe."
            )

        elif keyword in HELP_KEYWORDS:
            result["action"] = "help"
            result["auto_reply"] = (
                "For assistance, reply STOP to unsubscribe or START to re-subscribe. "
                "Contact us for other inquiries."
            )

        return result

    def _extract_keyword(self, message_body: str) -> str:
        """Extract the first meaningful keyword from a message."""
        cleaned = re.sub(r"[^a-zA-Z]", "", message_body.strip()).lower()
        return cleaned

    # ── Bulk operations ─────────────────────────────────────────────────────────
    def bulk_opt_out(self, phones: List[str], reason: str = "bulk_import", tenant_id: Optional[str] = None) -> int:
        """Bulk import an opt-out list (e.g., from DNC registry)."""
        count = 0
        for phone in phones:
            if not self.is_opted_out(phone, tenant_id):
                self.opt_out(phone, reason=reason, tenant_id=tenant_id)
                count += 1
        logger.info(f"Bulk opt-out: {count}/{len(phones)} numbers added")
        return count

    def get_opted_out_count(self, tenant_id: Optional[str] = None) -> int:
        """Return the count of opted-out numbers."""
        if tenant_id:
            return sum(1 for k in self._opted_out if k.startswith(f"{tenant_id}:"))
        return len(self._opted_out)

    def export_opted_out(self, tenant_id: Optional[str] = None) -> List[str]:
        """Export all opted-out phone numbers."""
        if tenant_id:
            prefix = f"{tenant_id}:"
            return [
                v["phone"] for k, v in self._opted_out.items()
                if k.startswith(prefix)
            ]
        return [v["phone"] for v in self._opted_out.values()]

    # ── Normalization ────────────────────────────────────────────────────────────
    def _normalize_phone(self, phone: str) -> str:
        """Normalize to E.164 format for consistent storage."""
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 10:
            return f"+1{digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        if len(digits) >= 10:
            return f"+{digits}"
        return phone


# ── Factory (no singleton — avoids stale DB session) ──────────────────────────


def get_opt_out_manager(db=None) -> SMSOptOutManager:
    """Create a new manager with the provided DB session.

    Previously used a singleton, but that caused stale session issues
    in multi-worker deployments. Each call now gets a fresh instance.
    """
    return SMSOptOutManager(db=db)


def is_opted_out(phone: str, tenant_id: Optional[str] = None, db=None) -> bool:
    """Convenience function to check opt-out status."""
    return get_opt_out_manager(db).is_opted_out(phone, tenant_id)


def process_stop_keyword(from_phone: str, message_body: str, tenant_id: Optional[str] = None, db=None) -> Dict[str, Any]:
    """Process inbound STOP/START keywords."""
    return get_opt_out_manager(db).process_inbound(from_phone, message_body, tenant_id)
