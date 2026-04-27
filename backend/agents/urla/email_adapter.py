"""
URLA MISMO 3.4 Email Adapter
============================
Emails the completed 1003 application as a MISMO 3.4 XML attachment
to the assigned loan officer.

Uses the existing EmailDeliveryService (SendGrid -> Microsoft Graph ->
Gmail -> SMTP waterfall) so no new infrastructure is required.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("urla.email_adapter")


@dataclass
class EmailResult:
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


def _build_html_body(
    *,
    borrower_name: str,
    loan_id: str,
    loan_officer_name: str,
    timestamp: str,
) -> str:
    """Build the HTML email body for the MISMO attachment email."""
    lo_first = loan_officer_name.split()[0] if loan_officer_name else "Team"
    return (
        f"<p>Hi {lo_first},</p>"
        f"<p>A new loan application has been completed via Perennia's AI intake.</p>"
        f"<ul>"
        f"  <li><strong>Borrower:</strong> {borrower_name}</li>"
        f"  <li><strong>Loan ID:</strong> {loan_id}</li>"
        f"  <li><strong>Completed:</strong> {timestamp}</li>"
        f"</ul>"
        f"<p>The attached MISMO 3.4 XML file contains the complete Uniform Residential "
        f"Loan Application (Form 1003) data. Import this file into your LOS to begin "
        f"processing.</p>"
        f"<p>&mdash; Perennia AI</p>"
    )


async def email_mismo_file(
    *,
    xml_content: str,
    loan_id: str,
    borrower_name: str,
    borrower_email: str,
    loan_officer_email: str,
    loan_officer_name: str,
    organization_id: str = "",
    cc_emails: list[str] | None = None,
) -> EmailResult:
    """
    Email the MISMO 3.4 XML as an attachment to the loan officer.

    Uses the native EmailDeliveryService which waterfalls through
    SendGrid -> Microsoft Graph -> Gmail -> SMTP. Falls back gracefully
    when no provider is configured (dry-run mode in dev).

    Parameters
    ----------
    xml_content : str
        The MISMO 3.4 XML document as a string.
    loan_id : str
        Perennia voice-URLA loan identifier.
    borrower_name : str
        Full name of the primary borrower.
    borrower_email : str
        Borrower email (used for CC if non-empty).
    loan_officer_email : str
        Destination email for the LO.
    loan_officer_name : str
        LO display name (used in greeting).
    organization_id : str
        Org ID for rate-limiting and audit logging.
    cc_emails : list[str] | None
        Additional CC recipients beyond the borrower.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"URLA 1003 Application — {borrower_name} — {loan_id}"
    html_body = _build_html_body(
        borrower_name=borrower_name,
        loan_id=loan_id,
        loan_officer_name=loan_officer_name,
        timestamp=timestamp,
    )

    # Build CC list: borrower + any extras
    cc_list: list[str] = []
    if borrower_email and borrower_email.strip():
        cc_list.append(borrower_email.strip())
    if cc_emails:
        cc_list.extend(addr for addr in cc_emails if addr and addr.strip())
    cc_list = cc_list or None  # type: ignore[assignment]

    # XML attachment as raw bytes
    xml_bytes = xml_content.encode("utf-8")
    attachment_filename = f"{loan_id}_1003_MISMO34.xml"

    # ------------------------------------------------------------------
    # Strategy A: EmailDeliveryService (SendGrid -> Graph -> Gmail -> SMTP)
    # ------------------------------------------------------------------
    try:
        from services.email_delivery_service import EmailDeliveryService
        from services.email_delivery_models import EmailAttachment

        # EmailDeliveryService needs a DB session for org config lookup and
        # OAuth token retrieval. We create a short-lived session here.
        db_session = _get_db_session()

        if db_session is not None:
            service = EmailDeliveryService(db_session)
            try:
                result = await service.send_email(
                    to=loan_officer_email,
                    subject=subject,
                    html_body=html_body,
                    cc=cc_list,
                    attachments=[
                        EmailAttachment(
                            filename=attachment_filename,
                            content_type="application/xml",
                            raw_content=xml_bytes,
                        ),
                    ],
                    organization_id=organization_id or None,
                )

                if result.success:
                    logger.info(
                        "MISMO email sent via %s",
                        result.provider.value,
                        extra={
                            "loan_id": loan_id,
                            "message_id": result.message_id,
                            "provider": result.provider.value,
                        },
                    )
                    return EmailResult(
                        success=True,
                        message_id=result.message_id,
                    )

                logger.warning(
                    "EmailDeliveryService failed, all providers exhausted",
                    extra={
                        "loan_id": loan_id,
                        "error": result.error,
                        "providers_tried": result.providers_tried,
                    },
                )
                return EmailResult(success=False, error=result.error)
            finally:
                db_session.close()
        else:
            logger.warning(
                "No DB session available for EmailDeliveryService; "
                "cannot send MISMO email",
                extra={"loan_id": loan_id},
            )
            return EmailResult(
                success=False,
                error="No database session available for email delivery",
            )

    except ImportError as exc:
        logger.error(
            "EmailDeliveryService import failed: %s", exc,
            extra={"loan_id": loan_id},
        )
        return EmailResult(success=False, error=f"Email service unavailable: {exc}")
    except Exception as exc:
        logger.exception(
            "Unexpected error sending MISMO email",
            extra={"loan_id": loan_id},
        )
        return EmailResult(success=False, error=str(exc))


def _get_db_session():
    """
    Obtain a short-lived SQLAlchemy session for the email service.

    Returns None if the database module is unavailable (e.g. in unit tests
    or when the voice agent runs outside the FastAPI process).
    """
    try:
        from database import SessionLocal
        return SessionLocal()
    except Exception as exc:
        logger.warning("Could not create DB session for email: %s", exc)
        return None
