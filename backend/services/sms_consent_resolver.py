"""
SMS Consent Resolver — Single source of truth for SMS consent decisions.

Problem: SMS consent is tracked in **6+ overlapping tables** across the codebase.
When one says "consented" and another says "opted out", which wins?

This resolver checks ALL consent sources in a strict priority order and returns
a single, authoritative verdict.  Every SMS send path should call
``resolve_consent()`` instead of querying individual tables directly.

Priority order (first match wins):
    1. Explicit opt-out (sms_opt_outs.active=True)          -> BLOCK
    2. Internal DNC list (internal_dnc_entries, unexpired)   -> BLOCK
    3. Dialer DNC list (contact_dnc_status)                  -> BLOCK
    4. Channel preference DNC (channel_preferences.do_not_sms) -> BLOCK
    5. Channel preference explicit no-consent                -> BLOCK
    6. Most recent positive consent record (across all consent tables) -> ALLOW
    7. No record found anywhere                              -> ALLOW (transactional exemption)

Consent tables checked for positive consent (step 6), most-recent wins:
    - sms_consent (SMSConsent)
    - tcpa_consents (TCPAConsent)
    - smart_docs_consent_records (SmartDocsConsentRecord)
    - channel_preferences (ChannelPreference.sms_consent)
    - borrower_profiles (BorrowerProfile.communication_consent)

Usage:
    from services.sms_consent_resolver import resolve_consent

    resolution = resolve_consent("+18005551234", organization_id=42, db=session)
    if not resolution.allowed:
        logger.warning("SMS blocked: %s", resolution.reason)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from telephony.phone_utils import normalize_phone as _normalize_phone
from telephony.phone_utils import digits_only as _digits_only

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ConsentResolution:
    """Authoritative consent verdict from the resolver."""

    allowed: bool
    source: str  # table/model name that determined the verdict
    record_id: Optional[str] = None  # PK of the deciding record (str for UUID compat)
    reason: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Additional context for audit logging
    consent_method: Optional[str] = None  # web_form, sms_keyword, verbal, etc.
    consented_at: Optional[datetime] = None  # when consent was granted (if applicable)

    def __repr__(self) -> str:
        return (
            f"ConsentResolution(allowed={self.allowed}, source={self.source!r}, "
            f"reason={self.reason!r}, record_id={self.record_id})"
        )


# ---------------------------------------------------------------------------
# Individual source checkers
# ---------------------------------------------------------------------------

def _check_sms_opt_outs(
    db: Session, phone: str, organization_id: Optional[int],
) -> Optional[ConsentResolution]:
    """Priority 1: Check sms_opt_outs table for active opt-out."""
    try:
        if organization_id:
            row = db.execute(
                text("""
                    SELECT id, opt_out_keyword, opted_out_at
                    FROM sms_opt_outs
                    WHERE phone_number = :phone AND active = TRUE
                      AND (organization_id = :org_id OR organization_id IS NULL)
                    ORDER BY opted_out_at DESC NULLS LAST
                    LIMIT 1
                """),
                {"phone": phone, "org_id": organization_id},
            ).fetchone()
        else:
            row = db.execute(
                text("""
                    SELECT id, opt_out_keyword, opted_out_at
                    FROM sms_opt_outs
                    WHERE phone_number = :phone AND active = TRUE
                    ORDER BY opted_out_at DESC NULLS LAST
                    LIMIT 1
                """),
                {"phone": phone},
            ).fetchone()

        if row:
            return ConsentResolution(
                allowed=False,
                source="sms_opt_outs",
                record_id=str(row[0]),
                reason=f"Active opt-out via keyword '{row[1] or 'STOP'}'",
            )
    except Exception as e:
        logger.warning("sms_opt_outs check failed (table may not exist): %s", e)
        _safe_rollback(db)
    return None


def _check_internal_dnc(
    db: Session, phone: str, organization_id: Optional[int],
) -> Optional[ConsentResolution]:
    """Priority 2: Check internal_dnc_entries (Smart Docs DNC, with expiration)."""
    try:
        params: dict = {"phone": phone}
        org_clause = ""
        if organization_id:
            org_clause = "AND organization_id = :org_id"
            params["org_id"] = organization_id

        row = db.execute(
            text(f"""
                SELECT id, reason, added_at
                FROM internal_dnc_entries
                WHERE phone = :phone
                  {org_clause}
                  AND (expires_at IS NULL OR expires_at > NOW())
                LIMIT 1
            """),
            params,
        ).fetchone()

        if row:
            return ConsentResolution(
                allowed=False,
                source="internal_dnc_entries",
                record_id=str(row[0]),
                reason=f"Internal DNC: {row[1] or 'no reason provided'}",
            )
    except Exception as e:
        logger.debug("internal_dnc_entries check skipped: %s", e)
        _safe_rollback(db)
    return None


def _check_contact_dnc_status(
    db: Session, phone: str, organization_id: Optional[int],
) -> Optional[ConsentResolution]:
    """Priority 3: Check contact_dnc_status (dialer DNC list)."""
    try:
        # ContactDNCStatus stores phone in various formats; check both normalized and digits
        digits = _digits_only(phone)
        params: dict = {"phone": phone, "digits": digits}
        org_clause = ""
        if organization_id:
            org_clause = "AND (organization_id = :org_id OR organization_id IS NULL)"
            params["org_id"] = organization_id

        row = db.execute(
            text(f"""
                SELECT id, reason
                FROM contact_dnc_status
                WHERE (phone_number = :phone OR phone_number = :digits)
                  {org_clause}
                LIMIT 1
            """),
            params,
        ).fetchone()

        if row:
            return ConsentResolution(
                allowed=False,
                source="contact_dnc_status",
                record_id=str(row[0]),
                reason=f"Dialer DNC list: {row[1] or 'no reason provided'}",
            )
    except Exception as e:
        logger.debug("contact_dnc_status check skipped: %s", e)
        _safe_rollback(db)
    return None


def _check_channel_preferences_block(
    db: Session, phone: str, organization_id: Optional[int],
) -> Optional[ConsentResolution]:
    """Priority 4-5: Check channel_preferences for do_not_sms or sms_consent=False.

    ChannelPreference is keyed by lead_id, so we need to find the lead by phone first.
    """
    try:
        digits = _digits_only(phone)
        if len(digits) < 10:
            return None

        # Find lead(s) matching this phone number, scoped by org
        lead_suffix = digits[-10:]
        params: dict = {"phone_pattern": f"%{lead_suffix}"}
        org_clause = ""
        if organization_id:
            org_clause = "AND l.organization_id = :org_id"
            params["org_id"] = organization_id

        row = db.execute(
            text(f"""
                SELECT cp.id, cp.do_not_sms, cp.sms_consent, cp.sms_consent_date, cp.lead_id
                FROM channel_preferences cp
                JOIN leads l ON l.id = cp.lead_id
                WHERE l.phone ILIKE :phone_pattern
                  {org_clause}
                ORDER BY cp.updated_at DESC NULLS LAST
                LIMIT 1
            """),
            params,
        ).fetchone()

        if row:
            cp_id, do_not_sms, sms_consent, sms_consent_date, lead_id = row

            # Priority 4: Explicit DNC flag
            if do_not_sms:
                return ConsentResolution(
                    allowed=False,
                    source="channel_preferences",
                    record_id=str(cp_id),
                    reason="Contact has do_not_sms=True in channel preferences",
                )

            # Priority 5: Explicit no-consent (only block if the field was set to False,
            # not if it's NULL/default which means "not yet asked")
            if sms_consent is False:
                return ConsentResolution(
                    allowed=False,
                    source="channel_preferences",
                    record_id=str(cp_id),
                    reason="Contact has sms_consent=False in channel preferences",
                )
    except Exception as e:
        logger.debug("channel_preferences check skipped: %s", e)
        _safe_rollback(db)
    return None


def _find_most_recent_consent(
    db: Session, phone: str, organization_id: Optional[int],
) -> Optional[ConsentResolution]:
    """Priority 6: Look for the most recent positive consent across all consent tables.

    Checks (in query order, but picks most recent across all):
      - sms_consent
      - tcpa_consents
      - smart_docs_consent_records
      - channel_preferences.sms_consent
      - borrower_profiles.communication_consent
    """
    best: Optional[ConsentResolution] = None
    best_date: Optional[datetime] = None

    # --- sms_consent table ---
    try:
        row = db.execute(
            text("""
                SELECT id, consent_source, consented_at
                FROM sms_consent
                WHERE phone_number = :phone AND consent_given = TRUE
                ORDER BY consented_at DESC NULLS LAST
                LIMIT 1
            """),
            {"phone": phone},
        ).fetchone()
        if row and (best_date is None or (row[2] and row[2] > best_date)):
            best_date = row[2]
            best = ConsentResolution(
                allowed=True,
                source="sms_consent",
                record_id=str(row[0]),
                reason="Active consent in sms_consent table",
                consent_method=row[1],
                consented_at=row[2],
            )
    except Exception as e:
        logger.debug("sms_consent positive-consent check skipped: %s", e)
        _safe_rollback(db)

    # --- tcpa_consents table ---
    try:
        params: dict = {"phone": phone}
        org_clause = ""
        if organization_id:
            org_clause = "AND organization_id = CAST(:org_id AS uuid)"
            params["org_id"] = str(organization_id)

        # TCPAConsent stores org_id as UUID; try integer match first, fall back
        try:
            row = db.execute(
                text(f"""
                    SELECT id, consent_source, granted_at, consent_type
                    FROM tcpa_consents
                    WHERE phone_number = :phone
                      AND is_active = TRUE
                      AND consent_channel IN ('sms', 'both')
                      {org_clause}
                    ORDER BY granted_at DESC NULLS LAST
                    LIMIT 1
                """),
                params,
            ).fetchone()
        except Exception:
            _safe_rollback(db)
            # Fall back to unscoped query if org_id type mismatch
            row = db.execute(
                text("""
                    SELECT id, consent_source, granted_at, consent_type
                    FROM tcpa_consents
                    WHERE phone_number = :phone
                      AND is_active = TRUE
                      AND consent_channel IN ('sms', 'both')
                    ORDER BY granted_at DESC NULLS LAST
                    LIMIT 1
                """),
                {"phone": phone},
            ).fetchone()

        if row and (best_date is None or (row[2] and row[2] > best_date)):
            best_date = row[2]
            best = ConsentResolution(
                allowed=True,
                source="tcpa_consents",
                record_id=str(row[0]),
                reason=f"Active TCPA consent ({row[3] or 'express_written'})",
                consent_method=row[1],
                consented_at=row[2],
            )
    except Exception as e:
        logger.debug("tcpa_consents positive-consent check skipped: %s", e)
        _safe_rollback(db)

    # --- smart_docs_consent_records table ---
    try:
        digits = _digits_only(phone)
        params = {"phone": phone, "digits": digits}
        org_clause = ""
        if organization_id:
            org_clause = "AND organization_id = :org_id"
            params["org_id"] = organization_id

        row = db.execute(
            text(f"""
                SELECT id, consent_source, consented_at
                FROM smart_docs_consent_records
                WHERE (phone = :phone OR phone = :digits)
                  AND consent_given = TRUE
                  AND revoked_at IS NULL
                  AND channel IN ('sms', 'both')
                  {org_clause}
                ORDER BY consented_at DESC NULLS LAST
                LIMIT 1
            """),
            params,
        ).fetchone()

        if row and (best_date is None or (row[2] and row[2] > best_date)):
            best_date = row[2]
            best = ConsentResolution(
                allowed=True,
                source="smart_docs_consent_records",
                record_id=str(row[0]),
                reason="Active consent in Smart Docs consent records",
                consent_method=row[1],
                consented_at=row[2],
            )
    except Exception as e:
        logger.debug("smart_docs_consent_records positive-consent check skipped: %s", e)
        _safe_rollback(db)

    # --- channel_preferences.sms_consent ---
    try:
        digits = _digits_only(phone)
        lead_suffix = digits[-10:] if len(digits) >= 10 else digits
        params = {"phone_pattern": f"%{lead_suffix}"}
        org_clause = ""
        if organization_id:
            org_clause = "AND l.organization_id = :org_id"
            params["org_id"] = organization_id

        row = db.execute(
            text(f"""
                SELECT cp.id, cp.sms_consent_date, cp.sms_consent
                FROM channel_preferences cp
                JOIN leads l ON l.id = cp.lead_id
                WHERE l.phone ILIKE :phone_pattern
                  AND cp.sms_consent = TRUE
                  {org_clause}
                ORDER BY cp.sms_consent_date DESC NULLS LAST
                LIMIT 1
            """),
            params,
        ).fetchone()

        if row and row[2] is True:
            consent_date = row[1]
            if best_date is None or (consent_date and consent_date > best_date):
                best_date = consent_date
                best = ConsentResolution(
                    allowed=True,
                    source="channel_preferences",
                    record_id=str(row[0]),
                    reason="SMS consent=True in channel preferences",
                    consent_method="channel_preference",
                    consented_at=consent_date,
                )
    except Exception as e:
        logger.debug("channel_preferences positive-consent check skipped: %s", e)
        _safe_rollback(db)

    # --- borrower_profiles.communication_consent ---
    try:
        # BorrowerProfile has NO phone column; match on email via lead association
        # This is a weak signal — only used if no stronger consent source exists
        # Skip if we already have a stronger consent source
        if best is None:
            digits = _digits_only(phone)
            lead_suffix = digits[-10:] if len(digits) >= 10 else digits
            params = {"phone_pattern": f"%{lead_suffix}"}
            org_clause = ""
            if organization_id:
                org_clause = "AND l.organization_id = :org_id"
                params["org_id"] = organization_id

            row = db.execute(
                text(f"""
                    SELECT bp.id, bp.communication_consent, bp.consent_captured_at
                    FROM borrower_profiles bp
                    JOIN leads l ON LOWER(l.email) = LOWER(bp.email)
                    WHERE l.phone ILIKE :phone_pattern
                      AND bp.communication_consent = TRUE
                      AND bp.consent_revoked_at IS NULL
                      {org_clause}
                    LIMIT 1
                """),
                params,
            ).fetchone()

            if row and row[1] is True:
                best = ConsentResolution(
                    allowed=True,
                    source="borrower_profiles",
                    record_id=str(row[0]),
                    reason="Borrower profile has communication_consent=True",
                    consent_method="borrower_profile",
                    consented_at=row[2],
                )
    except Exception as e:
        logger.debug("borrower_profiles consent check skipped: %s", e)
        _safe_rollback(db)

    return best


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _safe_rollback(db: Session) -> None:
    """Rollback without raising if the session is in a bad state."""
    try:
        db.rollback()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def resolve_consent(
    phone_number: str,
    organization_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> ConsentResolution:
    """Resolve SMS consent from ALL sources, returning a single authoritative verdict.

    This is the **canonical** function for SMS consent decisions.  All SMS send
    paths should call this instead of querying individual consent tables.

    Args:
        phone_number: Recipient phone number (any format, will be normalized).
        organization_id: Org ID for tenant-scoped checks (highly recommended).
        db: SQLAlchemy session.  If None, a new session is created and closed.

    Returns:
        ConsentResolution with the authoritative verdict.
    """
    owns_session = False
    if db is None:
        try:
            from database import SessionLocal
            db = SessionLocal()
            owns_session = True
        except Exception as e:
            logger.error("Cannot create DB session for consent resolution: %s", e)
            return ConsentResolution(
                allowed=False,
                source="system",
                reason=f"Database unavailable: {e}",
            )

    try:
        phone = _normalize_phone(phone_number)
        if not phone:
            return ConsentResolution(
                allowed=False,
                source="system",
                reason=f"Invalid phone number format: {phone_number!r}",
            )

        # ----------------------------------------------------------------
        # Priority 1: Explicit opt-out (sms_opt_outs) -> BLOCK
        # ----------------------------------------------------------------
        result = _check_sms_opt_outs(db, phone, organization_id)
        if result:
            logger.info(
                "Consent DENIED for %s: %s (source=%s)",
                phone, result.reason, result.source,
            )
            return result

        # ----------------------------------------------------------------
        # Priority 2: Internal DNC (internal_dnc_entries) -> BLOCK
        # ----------------------------------------------------------------
        result = _check_internal_dnc(db, phone, organization_id)
        if result:
            logger.info(
                "Consent DENIED for %s: %s (source=%s)",
                phone, result.reason, result.source,
            )
            return result

        # ----------------------------------------------------------------
        # Priority 3: Dialer DNC (contact_dnc_status) -> BLOCK
        # ----------------------------------------------------------------
        result = _check_contact_dnc_status(db, phone, organization_id)
        if result:
            logger.info(
                "Consent DENIED for %s: %s (source=%s)",
                phone, result.reason, result.source,
            )
            return result

        # ----------------------------------------------------------------
        # Priority 4-5: Channel preference blocks -> BLOCK
        # ----------------------------------------------------------------
        result = _check_channel_preferences_block(db, phone, organization_id)
        if result:
            logger.info(
                "Consent DENIED for %s: %s (source=%s)",
                phone, result.reason, result.source,
            )
            return result

        # ----------------------------------------------------------------
        # Priority 6: Most recent positive consent -> ALLOW
        # ----------------------------------------------------------------
        result = _find_most_recent_consent(db, phone, organization_id)
        if result:
            logger.debug(
                "Consent GRANTED for %s: %s (source=%s)",
                phone, result.reason, result.source,
            )
            return result

        # ----------------------------------------------------------------
        # Priority 7: No record found -> ALLOW (transactional exemption)
        # ----------------------------------------------------------------
        logger.info(
            "No consent record found for %s — allowing (transactional SMS exemption)",
            phone,
        )
        return ConsentResolution(
            allowed=True,
            source="no_record",
            reason="No consent record found — transactional SMS exemption applies",
            consent_method="transactional_exemption",
        )

    except Exception as e:
        logger.error("Consent resolution failed for %s: %s", phone_number, e, exc_info=True)
        # Fail-CLOSED for TCPA safety — block SMS when consent state is unknown
        return ConsentResolution(
            allowed=False,
            source="error_fallback",
            reason=f"Consent resolution error (fail-closed for TCPA safety): {e}",
        )
    finally:
        if owns_session and db:
            db.close()
