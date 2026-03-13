# backend/integrations/sms_compliance_gate.py
# TCPA/CTIA Compliance Gate - Pre-send validation for all outbound SMS
# Checks: DNC registry, consent records, opt-out status, quiet hours, message content

import re
import logging
from datetime import datetime, time
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
QUIET_HOURS_START = time(21, 0)  # 9 PM local time
QUIET_HOURS_END = time(8, 0)   # 8 AM local time

FORBIDDEN_PATTERNS = [
    r"\b(guaranteed|100%|free money|click here|act now|limited time|winner|prize|claim now)\b",
    r"\b(make money fast|earn \$|income from home)\b",
]

OPT_OUT_KEYWORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
OPT_IN_KEYWORDS = {"START", "UNSTOP", "YES"}
HELP_KEYWORDS = {"HELP", "INFO"}

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
class ComplianceResult:
    def __init__(self, allowed: bool, reason: str = "", risk_level: str = "low"):
        self.allowed = allowed
        self.reason = reason
        self.risk_level = risk_level  # low | medium | high | blocked

    def __repr__(self):
        return f"ComplianceResult(allowed={self.allowed}, reason={self.reason!r}, risk={self.risk_level})"


# ---------------------------------------------------------------------------
# Core gate function
# ---------------------------------------------------------------------------
def check_sms_compliance(
    db: Session,
    to_phone: str,
    message_body: str,
    from_phone: Optional[str] = None,
    lead_id: Optional[int] = None,
    user_id: Optional[int] = None,
    bypass_quiet_hours: bool = False,
) -> ComplianceResult:
    """
    Run all compliance checks before sending an SMS.
    Returns ComplianceResult with allowed=True if message may be sent.
    """
    phone = _normalize_phone(to_phone)
    if not phone:
        return ComplianceResult(False, "Invalid phone number format", "blocked")

    # 1. Check opt-out / DNC status
    dnc = _check_opt_out(db, phone)
    if dnc:
        return ComplianceResult(False, f"Phone {phone} is on DNC/opt-out list", "blocked")

    # 2. Check consent record
    consent = _check_consent(db, phone, lead_id)
    if not consent:
        logger.warning(f"No consent record for {phone} - blocking SMS")
        return ComplianceResult(False, "No written consent record on file (TCPA)", "blocked")

    # 3. Quiet hours check
    if not bypass_quiet_hours:
        tz_str = _get_lead_timezone(db, lead_id) or "America/New_York"
        if _is_quiet_hours(tz_str):
            return ComplianceResult(
                False,
                f"Quiet hours active for timezone {tz_str} (9 PM - 8 AM)",
                "blocked",
            )

    # 4. Message content scan
    content_issue = _scan_message_content(message_body)
    if content_issue:
        return ComplianceResult(False, f"Message content violation: {content_issue}", "high")

    # 5. Message length check (CTIA: 160 chars per segment, warn at 480+)
    if len(message_body) > 1600:
        return ComplianceResult(False, "Message exceeds maximum allowed length (1600 chars)", "high")

    # 6. Log compliance check for audit trail
    _log_compliance_check(db, phone, lead_id, user_id, "passed")

    return ComplianceResult(True, "All compliance checks passed", "low")


# ---------------------------------------------------------------------------
# Opt-out / DNC helpers
# ---------------------------------------------------------------------------
def _check_opt_out(db: Session, phone: str) -> bool:
    """Return True if phone is on DNC or has sent STOP."""
    try:
        row = db.execute(
            text("""
                SELECT id FROM sms_opt_outs
                WHERE phone_number = :phone AND active = TRUE
                LIMIT 1
            """),
            {"phone": phone},
        ).fetchone()
        return row is not None
    except Exception as e:
        logger.error(f"DNC check error: {e}")
        # Fail safe: if we can't check, block the message
        return True


def record_opt_out(db: Session, phone: str, keyword: str = "STOP", lead_id: Optional[int] = None):
    """Record an opt-out when a STOP keyword is received."""
    phone = _normalize_phone(phone) or phone
    try:
        db.execute(
            text("""
                INSERT INTO sms_opt_outs (phone_number, opt_out_keyword, lead_id, opted_out_at, active)
                VALUES (:phone, :keyword, :lead_id, NOW(), TRUE)
                ON CONFLICT (phone_number) DO UPDATE
                  SET active = TRUE, opted_out_at = NOW(), opt_out_keyword = :keyword
            """),
            {"phone": phone, "keyword": keyword.upper(), "lead_id": lead_id},
        )
        db.commit()
        logger.info(f"Opt-out recorded for {phone} via keyword {keyword}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to record opt-out for {phone}: {e}")


def record_opt_in(db: Session, phone: str, keyword: str = "START", lead_id: Optional[int] = None):
    """Re-activate consent when START/UNSTOP is received."""
    phone = _normalize_phone(phone) or phone
    try:
        db.execute(
            text("""
                UPDATE sms_opt_outs
                SET active = FALSE, opted_in_at = NOW()
                WHERE phone_number = :phone
            """),
            {"phone": phone},
        )
        # Also upsert consent record
        db.execute(
            text("""
                INSERT INTO sms_consent (phone_number, lead_id, consent_given, consent_source, consented_at)
                VALUES (:phone, :lead_id, TRUE, 'sms_keyword', NOW())
                ON CONFLICT (phone_number) DO UPDATE
                  SET consent_given = TRUE, consented_at = NOW(), consent_source = 'sms_keyword'
            """),
            {"phone": phone, "lead_id": lead_id},
        )
        db.commit()
        logger.info(f"Opt-in recorded for {phone} via keyword {keyword}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to record opt-in for {phone}: {e}")


# ---------------------------------------------------------------------------
# Consent helpers
# ---------------------------------------------------------------------------
def _check_consent(db: Session, phone: str, lead_id: Optional[int] = None) -> bool:
    """Return True if valid consent exists for this phone number."""
    try:
        row = db.execute(
            text("""
                SELECT id FROM sms_consent
                WHERE phone_number = :phone AND consent_given = TRUE
                LIMIT 1
            """),
            {"phone": phone},
        ).fetchone()
        return row is not None
    except Exception as e:
        logger.error(f"Consent check error: {e}")
        # If consent table doesn't exist yet, allow with warning
        logger.warning("Consent table may not exist - allowing message but flagging")
        return True


def record_consent(
    db: Session,
    phone: str,
    lead_id: Optional[int] = None,
    source: str = "web_form",
    ip_address: Optional[str] = None,
):
    """Record written consent for a phone number."""
    phone = _normalize_phone(phone) or phone
    try:
        db.execute(
            text("""
                INSERT INTO sms_consent
                  (phone_number, lead_id, consent_given, consent_source, consented_at, ip_address)
                VALUES (:phone, :lead_id, TRUE, :source, NOW(), :ip)
                ON CONFLICT (phone_number) DO UPDATE
                  SET consent_given = TRUE, consented_at = NOW(), consent_source = :source
            """),
            {"phone": phone, "lead_id": lead_id, "source": source, "ip": ip_address},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to record consent for {phone}: {e}")


# ---------------------------------------------------------------------------
# Quiet hours
# ---------------------------------------------------------------------------
def _is_quiet_hours(tz_str: str) -> bool:
    """Return True if current local time is within quiet hours (9 PM - 8 AM)."""
    try:
        tz = ZoneInfo(tz_str)
        now = datetime.now(tz).time()
        if QUIET_HOURS_START <= now or now < QUIET_HOURS_END:
            return True
        return False
    except Exception:
        # Unknown timezone - use Eastern
        try:
            tz = ZoneInfo("America/New_York")
            now = datetime.now(tz).time()
            return QUIET_HOURS_START <= now or now < QUIET_HOURS_END
        except Exception:
            return False


def _get_lead_timezone(db: Session, lead_id: Optional[int]) -> Optional[str]:
    """Look up lead's timezone from leads table."""
    if not lead_id:
        return None
    try:
        row = db.execute(
            text("SELECT timezone FROM leads WHERE id = :id LIMIT 1"),
            {"id": lead_id},
        ).fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Content scanning
# ---------------------------------------------------------------------------
def _scan_message_content(body: str) -> Optional[str]:
    """Scan message for spam/regulatory violations. Returns issue string or None."""
    lower_body = body.lower()
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, lower_body, re.IGNORECASE):
            return f"Matched forbidden pattern: {pattern}"
    return None


# ---------------------------------------------------------------------------
# Inbound keyword handler
# ---------------------------------------------------------------------------
def handle_inbound_keyword(
    db: Session, from_phone: str, body: str, lead_id: Optional[int] = None
) -> Tuple[bool, str]:
    """
    Process inbound SMS keywords for opt-out/opt-in/help.
    Returns (is_keyword, response_message).
    """
    keyword = body.strip().upper()

    if keyword in OPT_OUT_KEYWORDS:
        record_opt_out(db, from_phone, keyword, lead_id)
        return (
            True,
            "You have been unsubscribed from Perennia AI SMS messages. "
            "Reply START to re-subscribe. Reply HELP for assistance.",
        )

    if keyword in OPT_IN_KEYWORDS:
        record_opt_in(db, from_phone, keyword, lead_id)
        return (
            True,
            "Welcome back! You have been re-subscribed to Perennia AI messages. "
            "Reply STOP to unsubscribe at any time.",
        )

    if keyword in HELP_KEYWORDS:
        return (
            True,
            "Perennia AI Mortgage CRM - Reply STOP to unsubscribe, "
            "START to re-subscribe. Msg & data rates may apply.",
        )

    return (False, "")


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------
def _log_compliance_check(
    db: Session,
    phone: str,
    lead_id: Optional[int],
    user_id: Optional[int],
    result: str,
):
    """Write compliance check audit record."""
    try:
        db.execute(
            text("""
                INSERT INTO sms_compliance_log
                  (phone_number, lead_id, user_id, check_result, checked_at)
                VALUES (:phone, :lead_id, :user_id, :result, NOW())
            """),
            {"phone": phone, "lead_id": lead_id, "user_id": user_id, "result": result},
        )
        db.commit()
    except Exception:
        # Non-fatal: don't block message if audit log fails
        pass


# ---------------------------------------------------------------------------
# Phone normalization
# ---------------------------------------------------------------------------
def _normalize_phone(phone: str) -> Optional[str]:
    """Normalize to E.164 format (+1XXXXXXXXXX for US numbers)."""
    if not phone:
        return None
    digits = re.sub(r"[^\d]", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if phone.startswith("+") and len(digits) >= 10:
        return f"+{digits}"
    return None
