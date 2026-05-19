"""
POS Consent Service
===================
Business logic for the voice-complete consent flow: credit authorization,
e-disclosure consent, SMS dispatch, and audit trail.

The flow:
  1. Voice agent completes URLA → calls voice_complete()
  2. Service validates sections, transitions to PENDING_CONSENT
  3. Generates PURL magic link, sends SMS via Telnyx
  4. Borrower opens link → reviews → captures credit auth + e-consent
  5. Borrower submits → status transitions to SUBMITTED
"""

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger("pos_consent")


# =============================================================================
# CONSENT LANGUAGE — swap these templates with compliance-approved text
# =============================================================================

CREDIT_AUTH_VERSION = "2026-04-25-v1"

CREDIT_AUTH_TEXT = """AUTHORIZATION TO OBTAIN CREDIT REPORT

I hereby authorize the lender and its designated agents to obtain my credit report from one or more consumer reporting agencies. This authorization is granted pursuant to the Fair Credit Reporting Act, 15 U.S.C. § 1681b(a)(3)(A).

I understand that:
• My credit report will be used to evaluate my mortgage loan application
• This authorization covers both initial and any subsequent credit inquiries related to this application
• I may revoke this authorization at any time by contacting the lender in writing
• A copy of this authorization will be retained in the loan file

By typing my full legal name below and clicking "I Authorize," I am providing my electronic signature confirming this authorization."""

ECONSENT_VERSION = "2026-04-25-v1"

ECONSENT_TEXT = """CONSENT TO RECEIVE ELECTRONIC DISCLOSURES

In accordance with the Electronic Signatures in Global and National Commerce Act (E-SIGN Act, 15 U.S.C. § 7001 et seq.), I consent to receive all mortgage-related disclosures, notices, and documents electronically.

I understand that:
• I am agreeing to receive the following documents electronically: Loan Estimate, Closing Disclosure, and all other required mortgage disclosures
• I may withdraw this consent at any time by contacting the lender in writing, and may request paper copies of any disclosures at no charge
• Withdrawing consent will not affect the legal validity of any electronic disclosures previously provided

By typing my full legal name below and clicking "I Agree," I am providing my electronic consent."""

HARDWARE_SOFTWARE_REQUIREMENTS = (
    "To access electronic disclosures, you need: a device with internet access, "
    "a current web browser (Chrome, Safari, Firefox, or Edge), and the ability "
    "to receive email. PDF documents require a PDF reader such as Adobe Acrobat."
)

RIGHT_TO_WITHDRAW = (
    "You may withdraw your consent to receive electronic disclosures at any time "
    "by contacting us in writing at the address or email provided in your loan "
    "documents. Withdrawal of consent will not affect the validity of disclosures "
    "previously delivered electronically."
)

PAPER_COPY_INFO = (
    "You may request a paper copy of any electronic disclosure at no charge by "
    "contacting your loan officer or emailing support@perenniaai.com. Paper copies "
    "will be mailed to the address on file within 3 business days."
)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# =============================================================================
# VOICE COMPLETE
# =============================================================================

def voice_complete(
    db: Session,
    voice_loan_id: str,
    borrower_first_name: str,
    borrower_phone: str,
    lo_name: str,
    organization_id: Optional[int] = None,
    owner_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Find or create a BorrowerApplication from the voice agent's loan_id,
    transition to PENDING_CONSENT, and send the borrower an SMS with a
    magic link to review and consent.

    Returns dict with magic_link, sms_result, etc.
    Raises ValueError if application is in an invalid state.
    """
    from database.models.borrower import BorrowerApplication
    from database.enums import ApplicationStatus
    from sqlalchemy import text

    # Look up existing application by voice_loan_id
    app = db.execute(text(
        "SELECT id FROM borrower_applications WHERE voice_loan_id = :vlid LIMIT 1"
    ), {"vlid": voice_loan_id}).fetchone()

    if app:
        application = db.query(BorrowerApplication).get(app[0])
    else:
        # Create a new BorrowerApplication from the voice session data
        import secrets
        application = BorrowerApplication(
            public_token=secrets.token_urlsafe(32),
            status=ApplicationStatus.DRAFT,
            borrower_first_name=borrower_first_name,
            borrower_phone=borrower_phone,
            organization_id=organization_id,
            owner_id=owner_id,
            voice_loan_id=voice_loan_id,
        )
        db.add(application)
        db.flush()

    if application.status not in (
        ApplicationStatus.DRAFT,
        ApplicationStatus.IN_PROGRESS,
        ApplicationStatus.PENDING_DOCUMENTS,
    ):
        if application.status == ApplicationStatus.PENDING_CONSENT:
            return {
                "status": "already_pending",
                "message": "Application already awaiting borrower consent",
                "application_id": application.id,
            }
        raise ValueError(
            f"Application {application.id} is in status {application.status.value} "
            f"and cannot be transitioned to PENDING_CONSENT"
        )

    # Transition status
    application.status = ApplicationStatus.PENDING_CONSENT
    application.voice_completed_at = datetime.now(timezone.utc)
    application.voice_loan_id = voice_loan_id

    # Generate PURL token (stores application.id for reliable lookup)
    magic_link, token = _generate_magic_link(db, application, organization_id)

    # Send SMS before commit — result is recorded in the same transaction.
    sms_result = {"success": False, "error": "not_attempted"}
    try:
        sms_result = _send_consent_sms(
            to_phone=borrower_phone,
            first_name=borrower_first_name,
            lo_name=lo_name,
            magic_link=magic_link,
            organization_id=organization_id,
        )
    except Exception as e:
        logger.warning("SMS send failed: %s", e)
        sms_result = {"success": False, "error": str(e)}

    if sms_result.get("success"):
        application.consent_sms_sent_at = datetime.now(timezone.utc)

    _write_application_event(db, application.id, "voice_complete_triggered", {
        "voice_loan_id": voice_loan_id,
        "sms_sent": sms_result.get("success", False),
        "magic_link_generated": True,
    })

    # Single atomic commit: status change + SMS result + event trail.
    db.commit()

    # Schedule reminder notifications (day 1, 3, 7)
    try:
        from services.pos_consent_reminder_service import schedule_reminders
        schedule_reminders(db, application.id, borrower_phone, borrower_first_name, lo_name, magic_link)
    except Exception as e:
        logger.warning("Failed to schedule consent reminders: %s", e)

    return {
        "status": "pending_consent",
        "application_id": application.id,
        "magic_link": magic_link,
        "sms_result": sms_result,
    }


def _generate_magic_link(
    db: Session,
    app,
    organization_id: Optional[int],
) -> Tuple[str, str]:
    """Generate a PURL token and magic link URL for the consent flow."""
    from services.purl_token_service import PURLTokenService
    from models.purl import TokenScope

    token_service = PURLTokenService(db)

    workspace_id = _get_or_create_workspace(db, app, organization_id)

    token_id, full_token = token_service.create_token(
        organization_id=organization_id or app.organization_id or None,
        workspace_id=workspace_id,
        scope=TokenScope.VOICE_REVIEW_SUBMIT,
        expires_in_days=7,
    )

    base_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
    magic_link = f"{base_url}/apply/voice-review/{full_token}"

    return magic_link, full_token


def _get_or_create_workspace(db, app, organization_id) -> int:
    """Get or create a PURL workspace for this specific application.

    Uses a per-application workspace with slug encoding the application_id
    for reliable token→application resolution.
    """
    from sqlalchemy import text

    slug = f"voice-consent-app-{app.id}"
    org_id = organization_id or app.organization_id or None

    if org_id is not None:
        result = db.execute(text(
            "SELECT id FROM purl_workspaces WHERE organization_id = :org_id "
            "AND slug = :slug LIMIT 1"
        ), {"org_id": org_id, "slug": slug}).fetchone()
    else:
        result = db.execute(text(
            "SELECT id FROM purl_workspaces WHERE organization_id IS NULL "
            "AND slug = :slug LIMIT 1"
        ), {"slug": slug}).fetchone()

    if result:
        return result[0]

    result = db.execute(text("""
        INSERT INTO purl_workspaces (organization_id, display_name, slug, created_at)
        VALUES (:org_id, :display_name, :slug, NOW())
        RETURNING id
    """), {"org_id": org_id, "display_name": f"Voice Consent — App #{app.id}", "slug": slug})
    db.flush()
    return result.fetchone()[0]


def _send_consent_sms(
    to_phone: str,
    first_name: str,
    lo_name: str,
    magic_link: str,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Send the consent magic link SMS via NotificationService."""
    try:
        from services.notification_service import NotificationService
        ns = NotificationService()

        message = (
            f"Hi {first_name}, we just wrapped up your application. "
            f"Tap to review, sign, and submit: {magic_link} "
            f"— {lo_name}. "
            f"By tapping, you'll review your application and authorize a credit check."
        )

        return ns.send_sms(
            to_phone=to_phone,
            message=message,
            skip_consent_check=True,
            organization_id=organization_id,
        )
    except Exception as e:
        logger.exception("Failed to send consent SMS: %s", e)
        return {"success": False, "error": str(e)}


# =============================================================================
# CREDIT AUTHORIZATION
# =============================================================================

def record_credit_authorization(
    db: Session,
    application_id: int,
    typed_full_name: str,
    ip_address: str,
    user_agent: str,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Record credit authorization consent. Idempotent — returns existing
    record if already authorized.
    """
    from database.models.pos_consent import CreditAuthorization
    from database.models.borrower import BorrowerApplication
    from database.enums import ApplicationStatus

    app = db.query(BorrowerApplication).filter(
        BorrowerApplication.id == application_id
    ).first()
    if not app:
        raise ValueError(f"Application {application_id} not found")

    if app.status != ApplicationStatus.PENDING_CONSENT:
        raise ValueError(
            f"Application is in status {app.status.value}, expected PENDING_CONSENT"
        )

    # Idempotency: check for existing authorization
    existing = db.query(CreditAuthorization).filter(
        CreditAuthorization.application_id == application_id,
        CreditAuthorization.authorized == True,
    ).first()
    if existing:
        return {
            "status": "already_authorized",
            "authorized_at": existing.authorized_at.isoformat(),
            "uuid": existing.uuid,
        }

    now = datetime.now(timezone.utc)
    auth = CreditAuthorization(
        uuid=str(uuid.uuid4()),
        application_id=application_id,
        organization_id=organization_id or app.organization_id,
        authorized=True,
        consent_text_version=CREDIT_AUTH_VERSION,
        consent_text_hash=_hash_text(CREDIT_AUTH_TEXT),
        typed_full_name=typed_full_name,
        ip_address=ip_address,
        user_agent=user_agent,
        authorized_at=now,
    )
    db.add(auth)

    # Update the legacy credit_auth fields on BorrowerApplication
    app.credit_auth_captured = True
    app.credit_auth_timestamp = now
    app.credit_auth_ip_address = ip_address
    app.credit_auth_user_agent = user_agent

    db.commit()

    try:
        _write_application_event(db, application_id, "credit_auth_captured", {
            "consent_version": CREDIT_AUTH_VERSION,
            "ip_address": ip_address,
        })
        db.commit()
    except Exception as e:
        logger.warning("Credit auth event write failed (non-fatal): %s", e)
        db.rollback()

    return {
        "status": "authorized",
        "authorized_at": now.isoformat(),
        "uuid": auth.uuid,
    }


# =============================================================================
# E-CONSENT AGREEMENT
# =============================================================================

def record_econsent_agreement(
    db: Session,
    application_id: int,
    typed_full_name: str,
    ip_address: str,
    user_agent: str,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Record e-disclosure consent. Idempotent — returns existing
    record if already consented.
    """
    from database.models.pos_consent import EConsentAgreement
    from database.models.borrower import BorrowerApplication
    from database.enums import ApplicationStatus

    app = db.query(BorrowerApplication).filter(
        BorrowerApplication.id == application_id
    ).first()
    if not app:
        raise ValueError(f"Application {application_id} not found")

    if app.status != ApplicationStatus.PENDING_CONSENT:
        raise ValueError(
            f"Application is in status {app.status.value}, expected PENDING_CONSENT"
        )

    existing = db.query(EConsentAgreement).filter(
        EConsentAgreement.application_id == application_id,
        EConsentAgreement.consented == True,
    ).first()
    if existing:
        return {
            "status": "already_consented",
            "consented_at": existing.consented_at.isoformat(),
            "uuid": existing.uuid,
        }

    now = datetime.now(timezone.utc)
    agreement = EConsentAgreement(
        uuid=str(uuid.uuid4()),
        application_id=application_id,
        organization_id=organization_id or app.organization_id,
        consented=True,
        consent_text_version=ECONSENT_VERSION,
        consent_text_hash=_hash_text(ECONSENT_TEXT),
        typed_full_name=typed_full_name,
        hardware_software_requirements_shown=HARDWARE_SOFTWARE_REQUIREMENTS,
        right_to_withdraw_shown=RIGHT_TO_WITHDRAW,
        paper_copy_info_shown=PAPER_COPY_INFO,
        ip_address=ip_address,
        user_agent=user_agent,
        consented_at=now,
    )
    db.add(agreement)

    db.commit()

    try:
        _write_application_event(db, application_id, "econsent_captured", {
            "consent_version": ECONSENT_VERSION,
            "ip_address": ip_address,
        })
        db.commit()
    except Exception as e:
        logger.warning("E-consent event write failed (non-fatal): %s", e)
        db.rollback()

    return {
        "status": "consented",
        "consented_at": now.isoformat(),
        "uuid": agreement.uuid,
    }


# =============================================================================
# CONSENT STATUS CHECK
# =============================================================================

def check_consents_complete(
    db: Session,
    application_id: int,
) -> Dict[str, Any]:
    """Check whether both credit auth and e-consent are recorded."""
    from database.models.pos_consent import CreditAuthorization, EConsentAgreement

    credit_auth = db.query(CreditAuthorization).filter(
        CreditAuthorization.application_id == application_id,
        CreditAuthorization.authorized == True,
    ).first()

    econsent = db.query(EConsentAgreement).filter(
        EConsentAgreement.application_id == application_id,
        EConsentAgreement.consented == True,
    ).first()

    return {
        "credit_auth": {
            "completed": credit_auth is not None,
            "timestamp": credit_auth.authorized_at.isoformat() if credit_auth else None,
        },
        "e_consent": {
            "completed": econsent is not None,
            "timestamp": econsent.consented_at.isoformat() if econsent else None,
        },
        "all_complete": credit_auth is not None and econsent is not None,
    }


def get_disclosure_texts() -> Dict[str, Any]:
    """Return the current consent language + version info for the frontend."""
    return {
        "credit_auth": {
            "version": CREDIT_AUTH_VERSION,
            "text": CREDIT_AUTH_TEXT,
            "hash": _hash_text(CREDIT_AUTH_TEXT),
        },
        "e_consent": {
            "version": ECONSENT_VERSION,
            "text": ECONSENT_TEXT,
            "hash": _hash_text(ECONSENT_TEXT),
            "hardware_software_requirements": HARDWARE_SOFTWARE_REQUIREMENTS,
            "right_to_withdraw": RIGHT_TO_WITHDRAW,
            "paper_copy_info": PAPER_COPY_INFO,
        },
    }


# =============================================================================
# HELPERS
# =============================================================================

def _write_application_event(
    db: Session,
    application_id: int,
    event_type: str,
    metadata: Dict[str, Any],
) -> None:
    """Write an ApplicationEvent row for the audit trail."""
    from sqlalchemy import text

    try:
        import json as _json
        db.execute(text("""
            INSERT INTO application_events
            (application_id, event_type, event_data, created_at)
            VALUES (:app_id, :event_type, :event_data::jsonb, NOW())
        """), {
            "app_id": application_id,
            "event_type": event_type,
            "event_data": _json.dumps(metadata),
        })
    except Exception as e:
        logger.warning("Failed to write application event: %s", e)
