# backend/integrations/sms_compliance_gate.py
# TCPA/CTIA Compliance Gate - Pre-send validation for all outbound SMS
# Checks: DNC registry, consent records, opt-out status, quiet hours, message content

import re
import logging
from datetime import datetime, time, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from sqlalchemy import text

from telephony.phone_utils import normalize_phone as _normalize_phone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
QUIET_HOURS_START = time(21, 0)  # 9 PM local time
QUIET_HOURS_END = time(8, 0)   # 8 AM local time

FORBIDDEN_PATTERNS = [
    r"\b(free money|click here|act now|limited time|winner|prize|claim now)\b",
    r"\b(make money fast|earn \$|income from home)\b",
]
# Note: "guaranteed" and "100%" are intentionally NOT forbidden — they are
# standard mortgage language (e.g. "rate guaranteed for 60 days", "100% VA financing").

PII_PATTERNS = [
    (r'\b\d{3}-\d{2}-\d{4}\b', "SSN pattern detected"),
    (r'\b\d{3}[- ]\d{2}[- ]\d{4}\b', "Possible SSN (formatted 9-digit pattern)"),
    (r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', "Credit card number pattern"),
    (r'\b(?:password|passwd|pwd)\s*[:=]\s*\S+', "Password in message"),
    (r'\baccount\s*#?\s*:?\s*\d{6,}\b', "Account number pattern"),
    (r'\brouting\s*#?\s*:?\s*\d{9}\b', "Routing number pattern"),
]

OPT_OUT_KEYWORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "REVOKE"}
OPT_IN_KEYWORDS = {"START", "UNSTOP", "YES"}
HELP_KEYWORDS = {"HELP", "INFO"}

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
class ComplianceResult:
    def __init__(
        self,
        allowed: bool,
        reason: str = "",
        risk_level: str = "low",
        consent_record_id: Optional[int] = None,
        consent_verified_at: Optional[datetime] = None,
        consent_method: Optional[str] = None,
    ):
        self.allowed = allowed
        self.reason = reason
        self.risk_level = risk_level  # low | medium | high | blocked
        # TCPA consent proof — links outbound SMS to the consent that authorized it
        self.consent_record_id = consent_record_id
        self.consent_verified_at = consent_verified_at
        self.consent_method = consent_method  # web_form, sms_keyword, verbal, imported, etc.

    def __repr__(self):
        return (
            f"ComplianceResult(allowed={self.allowed}, reason={self.reason!r}, "
            f"risk={self.risk_level}, consent_id={self.consent_record_id})"
        )


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
    organization_id: Optional[int] = None,
    bypass_quiet_hours: bool = False,
    urgent: bool = False,
    message_type: str = "marketing",
) -> ComplianceResult:
    """
    Run all compliance checks before sending an SMS.
    Returns ComplianceResult with allowed=True if message may be sent.

    Policy:
    - DNC/opt-out match -> BLOCK (always, regardless of message_type)
    - DNC check error -> BLOCK (fail-closed for TCPA)
    - No consent record -> BLOCK for marketing, ALLOW for transactional
    - Per-recipient frequency cap -> BLOCK (unless urgent=True)
    - Outside quiet hours -> BLOCK
    - Forbidden content -> BLOCK
    - Message > 1600 chars -> BLOCK

    Set message_type="transactional" for loan servicing messages (closing
    updates, document requests, payment reminders) that are exempt from
    express consent requirements under TCPA. DNC/opt-out checks are NEVER
    bypassed regardless of message_type.

    Set urgent=True to bypass frequency caps (e.g. opt-out confirmations,
    legally required transactional messages). DNC/opt-out checks are never
    bypassed.
    """
    if message_type not in ("transactional", "marketing"):
        message_type = "marketing"

    phone = _normalize_phone(to_phone)
    if not phone:
        _log_compliance_check(db, phone or to_phone, lead_id, user_id, "blocked:invalid_phone",
                              message_type=message_type)
        return ComplianceResult(False, "Invalid phone number format", "blocked")

    # 1-2. Unified consent resolution (replaces separate DNC + consent checks).
    # The resolver checks ALL consent sources in strict priority order:
    #   sms_opt_outs > internal_dnc > contact_dnc_status > channel_prefs > consent records
    # See services/sms_consent_resolver.py for the full priority chain.
    from services.sms_consent_resolver import resolve_consent as _resolve_consent

    consent_resolution = _resolve_consent(phone, organization_id=organization_id, db=db)

    if not consent_resolution.allowed:
        # DNC/opt-out blocks are NEVER skipped, even for transactional messages.
        is_dnc_block = "opt" in consent_resolution.source or "dnc" in consent_resolution.source

        if is_dnc_block:
            # Hard block: recipient opted out or is on DNC
            _log_compliance_check(db, phone, lead_id, user_id, "blocked:dnc_opt_out",
                                  message_type=message_type)
            return ComplianceResult(
                False,
                consent_resolution.reason,
                "blocked",
            )

        # Consent-only failure: transactional messages are exempt
        if message_type == "transactional":
            logger.info(
                "Consent requirement skipped for transactional message to ...%s (source=%s)",
                phone[-4:] if phone else "????",
                consent_resolution.source,
            )
            consent_info = {
                "id": None,
                "consent_source": "transactional_exemption",
                "consented_at": None,
            }
        else:
            _log_compliance_check(db, phone, lead_id, user_id, "blocked:no_consent",
                                  message_type=message_type)
            return ComplianceResult(
                False,
                consent_resolution.reason,
                "blocked",
            )
    else:
        # Consent passed -- build consent_info dict for downstream audit linkage
        consent_info = {
            "id": consent_resolution.record_id,
            "consent_source": consent_resolution.consent_method or consent_resolution.source,
            "consented_at": consent_resolution.consented_at,
        }

    # 3. Per-recipient frequency cap (after consent, before send)
    if urgent:
        logger.info(
            "Frequency cap BYPASSED (urgent=True) for %s (user_id=%s, lead_id=%s)",
            phone[-4:] if phone else "????",
            user_id,
            lead_id,
        )
    else:
        from integrations.sms_rate_limiter import check_recipient_frequency

        freq = check_recipient_frequency(phone, organization_id=organization_id, db=db)
        if not freq["allowed"]:
            _log_compliance_check(db, phone, lead_id, user_id, "blocked:frequency_cap_exceeded",
                                  message_type=message_type)
            return ComplianceResult(
                False,
                f"Frequency cap exceeded: {freq['reason']}",
                "blocked",
            )

    # 4. Quiet hours check — resolve timezone from lead record or area code
    if not bypass_quiet_hours:
        tz_str = _get_lead_timezone(db, lead_id)
        if not tz_str:
            # No lead timezone on file — infer from recipient phone area code
            try:
                from telephony.compliance import resolve_recipient_timezone
                tz_str = resolve_recipient_timezone(to_phone)
            except ImportError:
                tz_str = "America/New_York"
        if _is_quiet_hours(tz_str):
            _log_compliance_check(db, phone, lead_id, user_id, "blocked:quiet_hours",
                                  message_type=message_type)
            return ComplianceResult(
                False,
                f"It's outside calling hours in the recipient's timezone ({tz_str}). "
                f"TCPA prohibits contact before 8 AM and after 9 PM local time. "
                f"Want me to schedule it for tomorrow morning?",
                "blocked",
            )

    # 5. Message content scan
    content_issue = _scan_message_content(message_body)
    if content_issue:
        _log_compliance_check(db, phone, lead_id, user_id, "blocked:content_violation",
                              message_type=message_type)
        return ComplianceResult(False, f"Message content violation: {content_issue}", "high")

    # 6. Message length check (CTIA: 160 chars per segment, max 1600)
    if len(message_body) > 1600:
        _log_compliance_check(db, phone, lead_id, user_id, "blocked:message_too_long",
                              message_type=message_type)
        return ComplianceResult(False, "Message exceeds maximum allowed length (1600 chars)", "high")

    # 7. Log compliance check for audit trail (with consent proof)
    _log_compliance_check(
        db, phone, lead_id, user_id, "passed",
        consent_record_id=consent_info.get("id"),
        consent_method=consent_info.get("consent_source"),
        message_type=message_type,
    )

    # Attach consent proof to result so callers can persist the linkage
    verified_at = datetime.now(timezone.utc)
    return ComplianceResult(
        True,
        "All compliance checks passed",
        "low",
        consent_record_id=consent_info.get("id"),
        consent_verified_at=verified_at,
        consent_method=consent_info.get("consent_source"),
    )


def record_opt_out(
    db: Session, phone: str, keyword: str = "STOP",
    lead_id: Optional[int] = None, organization_id: Optional[int] = None,
) -> bool:
    """Record an opt-out when a STOP keyword is received.

    Flushes but does NOT commit — caller controls the transaction.
    For webhook handlers that own the session, call db.commit() after.
    Returns True if recorded successfully, False on failure.
    """
    phone = _normalize_phone(phone) or phone
    try:
        db.execute(
            text("""
                INSERT INTO sms_opt_outs (phone_number, opt_out_keyword, lead_id, organization_id, opted_out_at, active)
                VALUES (:phone, :keyword, :lead_id, :org_id, NOW(), TRUE)
                ON CONFLICT (phone_number) DO UPDATE
                  SET active = TRUE, opted_out_at = NOW(), opt_out_keyword = :keyword,
                      organization_id = COALESCE(:org_id, sms_opt_outs.organization_id)
            """),
            {"phone": phone, "keyword": keyword.upper(), "lead_id": lead_id, "org_id": organization_id},
        )
        db.flush()
        logger.info(f"Opt-out recorded for ...{phone[-4:] if phone else '????'} via keyword {keyword}")
        return True
    except Exception as e:
        logger.error(f"Failed to record opt-out for ...{phone[-4:] if phone else '????'}: {e}")
        return False


def record_opt_in(
    db: Session, phone: str, keyword: str = "START",
    lead_id: Optional[int] = None, organization_id: Optional[int] = None,
) -> bool:
    """Re-activate consent when START/UNSTOP is received.

    Flushes but does NOT commit — caller controls the transaction.
    Scoped by organization_id when provided to prevent cross-tenant effects.
    Returns True if recorded successfully, False on failure.
    """
    phone = _normalize_phone(phone) or phone
    try:
        # Scope opt-in to tenant when possible
        if organization_id:
            db.execute(
                text("""
                    UPDATE sms_opt_outs
                    SET active = FALSE, opted_in_at = NOW()
                    WHERE phone_number = :phone
                      AND (organization_id = :org_id OR organization_id IS NULL)
                """),
                {"phone": phone, "org_id": organization_id},
            )
        else:
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
        db.flush()
        logger.info(f"Opt-in recorded for ...{phone[-4:] if phone else '????'} via keyword {keyword}")
        return True
    except Exception as e:
        logger.error(f"Failed to record opt-in for ...{phone[-4:] if phone else '????'}: {e}")
        return False


def record_consent(
    db: Session,
    phone: str,
    lead_id: Optional[int] = None,
    source: str = "web_form",
    ip_address: Optional[str] = None,
):
    """Record written consent for a phone number. Flushes but does not commit."""
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
        db.flush()
    except Exception as e:
        logger.error(f"Failed to record consent for ...{phone[-4:] if phone else '????'}: {e}")


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
    """Look up lead's timezone from channel_preferences table."""
    if not lead_id:
        return None
    try:
        row = db.execute(
            text("SELECT timezone FROM channel_preferences WHERE lead_id = :id LIMIT 1"),
            {"id": lead_id},
        ).fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Content scanning
# ---------------------------------------------------------------------------
def _scan_message_content(body: str) -> Optional[str]:
    """Scan message for spam/regulatory violations and PII. Returns issue string or None."""
    lower_body = body.lower()
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, lower_body):
            return f"Matched forbidden pattern: {pattern}"
    for pattern, label in PII_PATTERNS:
        if re.search(pattern, body):
            return f"PII detected: {label}"
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
    consent_record_id: Optional[int] = None,
    consent_method: Optional[str] = None,
    message_type: Optional[str] = None,
):
    """Write compliance check audit record. Commits immediately for durability.

    Audit records must persist even if the caller crashes after the compliance
    check returns. Uses a SAVEPOINT so the commit does not interfere with the
    caller's surrounding transaction.

    When the check passes, consent_record_id and consent_method are
    included so the audit log captures which consent record authorized
    the send at the moment of verification.
    """
    try:
        nested = db.begin_nested()  # SAVEPOINT
        db.execute(
            text("""
                INSERT INTO sms_compliance_log
                  (phone_number, lead_id, user_id, check_result,
                   consent_record_id, consent_method, message_type, checked_at)
                VALUES (:phone, :lead_id, :user_id, :result,
                        :consent_record_id, :consent_method, :message_type, NOW())
            """),
            {
                "phone": phone,
                "lead_id": lead_id,
                "user_id": user_id,
                "result": result,
                "consent_record_id": consent_record_id,
                "consent_method": consent_method,
                "message_type": message_type,
            },
        )
        nested.commit()
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


