"""
Email Delivery Models
=====================
Pydantic models for the native email delivery service.

These are plain data-transfer objects and configuration containers —
no SQLAlchemy dependencies, safe to import anywhere.

Usage:
    from services.email_delivery_models import (
        EmailMessage,
        EmailDeliveryResult,
        EmailDeliveryConfig,
        EmailProvider,
        EmailStatus,
        EmailAttachment,
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# =============================================================================
# ENUMS
# =============================================================================

class EmailProvider(str, Enum):
    """Email delivery provider identifiers."""
    SENDGRID = "sendgrid"
    MICROSOFT = "microsoft"
    GMAIL = "gmail"
    NONE = "none"  # Dry-run / logging only


class EmailStatus(str, Enum):
    """Delivery status for a sent email."""
    SENT = "sent"          # Accepted by provider (202 / queued)
    DELIVERED = "delivered"  # Confirmed delivered by provider webhook
    BOUNCED = "bounced"    # Hard bounce reported by provider
    FAILED = "failed"      # Delivery attempt failed (all providers exhausted)
    RATE_LIMITED = "rate_limited"  # Request blocked by in-process rate limiter
    DRY_RUN = "dry_run"    # No provider configured; logged only


# =============================================================================
# SUB-MODELS
# =============================================================================

class EmailAttachment(BaseModel):
    """File attachment for an outgoing email."""

    filename: str = Field(..., description="Attachment filename shown to recipients")
    content_type: str = Field(
        default="application/octet-stream",
        description="MIME content type, e.g. 'application/pdf' or 'image/png'",
    )
    file_path: Optional[str] = Field(
        default=None,
        description=(
            "Absolute path to the file on disk. "
            "Used by the delivery service to read and encode the attachment. "
            "Either file_path or raw_content must be provided."
        ),
    )
    raw_content: Optional[bytes] = Field(
        default=None,
        description=(
            "Raw file bytes. Use this when the content is already in memory "
            "and no file path exists. Either file_path or raw_content must be provided."
        ),
    )

    @field_validator("filename")
    @classmethod
    def filename_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Attachment filename must not be empty")
        return v.strip()

    model_config = {"arbitrary_types_allowed": True}


# =============================================================================
# CORE MESSAGE MODEL
# =============================================================================

class EmailMessage(BaseModel):
    """
    A fully-specified outbound email message.

    The delivery service accepts this object and routes it through whichever
    provider is available (SendGrid → Microsoft Graph → Gmail).
    """

    # Required fields
    to: List[str] = Field(..., min_length=1, description="Primary recipient addresses")
    subject: str = Field(..., min_length=1, description="Email subject line")

    # Body — at least one of html_body / text_body is required (validated below)
    html_body: Optional[str] = Field(
        default=None, description="HTML body. Preferred over text_body."
    )
    text_body: Optional[str] = Field(
        default=None, description="Plain-text fallback body."
    )

    # Optional addressing
    cc: Optional[List[str]] = Field(default=None, description="Carbon-copy recipients")
    bcc: Optional[List[str]] = Field(default=None, description="Blind carbon-copy recipients")
    from_email: Optional[str] = Field(
        default=None,
        description=(
            "Sender address. Falls back to SENDGRID_FROM_EMAIL env var or "
            "the authenticated Microsoft / Google account address."
        ),
    )
    from_name: Optional[str] = Field(
        default=None,
        description="Human-readable sender display name.",
    )
    reply_to: Optional[str] = Field(
        default=None, description="Reply-To address (defaults to from_email)"
    )

    # Attachments
    attachments: Optional[List[EmailAttachment]] = Field(
        default=None, description="File attachments"
    )

    # Arbitrary extra headers injected verbatim into the outgoing message
    headers: Optional[Dict[str, str]] = Field(
        default=None,
        description=(
            "Extra SMTP/API headers. "
            "List-Unsubscribe is added automatically by the delivery service."
        ),
    )

    # Metadata carried through to the delivery result for auditing
    organization_id: Optional[str] = Field(
        default=None, description="Organization ID — used for rate limiting and audit logging"
    )
    user_id: Optional[str] = Field(
        default=None, description="User ID of the sender — stored in delivery logs"
    )

    # CAN-SPAM / GDPR helpers
    unsubscribe_url: Optional[str] = Field(
        default=None,
        description=(
            "If provided, a List-Unsubscribe header is added and the URL is "
            "appended as a footer link in the HTML body."
        ),
    )

    @field_validator("to")
    @classmethod
    def to_not_empty(cls, v: List[str]) -> List[str]:
        cleaned = [addr.strip() for addr in v if addr.strip()]
        if not cleaned:
            raise ValueError("'to' must contain at least one non-empty address")
        return cleaned

    @field_validator("html_body", "text_body", mode="before")
    @classmethod
    def body_none_on_empty_string(cls, v: Any) -> Optional[str]:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    def model_post_init(self, __context: Any) -> None:
        """Ensure at least one body part is present."""
        if not self.html_body and not self.text_body:
            raise ValueError("At least one of html_body or text_body must be provided")

    @property
    def effective_text_body(self) -> str:
        """Return plain-text body, stripping basic HTML tags as fallback."""
        if self.text_body:
            return self.text_body
        if self.html_body:
            import re
            return re.sub(r"<[^>]+>", "", self.html_body)
        return ""

    model_config = {"arbitrary_types_allowed": True}


# =============================================================================
# DELIVERY RESULT
# =============================================================================

class EmailDeliveryResult(BaseModel):
    """
    Result returned by EmailDeliveryService.send_email().

    Callers should check `status` to determine whether the message was
    accepted; check `error` for a human-readable failure description.
    """

    message_id: Optional[str] = Field(
        default=None,
        description=(
            "Provider-assigned message ID. "
            "For SendGrid this is the X-Message-Id response header value. "
            "For Microsoft Graph this is the sent-items message GUID. "
            "For Gmail this is the message thread ID."
        ),
    )
    status: EmailStatus = Field(..., description="Final delivery status")
    provider: EmailProvider = Field(..., description="Provider that accepted or attempted delivery")
    error: Optional[str] = Field(
        default=None, description="Human-readable error message when status is FAILED"
    )
    sent_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the delivery attempt was made",
    )

    # Providers tried in order before arriving at this result
    providers_tried: List[str] = Field(
        default_factory=list,
        description="Ordered list of provider names that were attempted",
    )

    # Original recipient list echoed back for convenience
    to: List[str] = Field(default_factory=list)

    @property
    def success(self) -> bool:
        """True when the message was accepted by a provider."""
        return self.status in (EmailStatus.SENT, EmailStatus.DELIVERED, EmailStatus.DRY_RUN)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "status": self.status.value,
            "provider": self.provider.value,
            "error": self.error,
            "sent_at": self.sent_at.isoformat(),
            "providers_tried": self.providers_tried,
            "success": self.success,
            "to": self.to,
        }


# =============================================================================
# PER-ORG DELIVERY CONFIG
# =============================================================================

class EmailDeliveryConfig(BaseModel):
    """
    Per-organization email delivery configuration.

    Loaded by EmailDeliveryService from the organization's `settings` JSON
    column (key ``"email_delivery"``) or from environment variables as a
    global fallback.

    Example org settings JSON::

        {
            "email_delivery": {
                "preferred_provider": "sendgrid",
                "sendgrid_api_key": "SG.xxx",
                "from_domain": "loanteam.com",
                "from_email": "updates@loanteam.com",
                "from_name": "Loan Team",
                "max_emails_per_minute": 80
            }
        }
    """

    # Provider preference
    preferred_provider: EmailProvider = Field(
        default=EmailProvider.SENDGRID,
        description=(
            "Primary provider to attempt first. "
            "The service always tries remaining providers as fallbacks."
        ),
    )

    # SendGrid
    sendgrid_api_key: Optional[str] = Field(
        default=None,
        description=(
            "Org-specific SendGrid API key. "
            "Falls back to the SENDGRID_API_KEY environment variable."
        ),
    )

    # Sender identity
    from_domain: Optional[str] = Field(
        default=None,
        description="Verified sending domain, e.g. 'company.com'",
    )
    from_email: Optional[str] = Field(
        default=None,
        description=(
            "Default From address for this org. "
            "Falls back to SENDGRID_FROM_EMAIL env var."
        ),
    )
    from_name: Optional[str] = Field(
        default=None,
        description="Default From display name for this org.",
    )

    # Rate limiting
    max_emails_per_minute: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum emails per minute for this org (in-process rate limit)",
    )

    # CAN-SPAM
    unsubscribe_base_url: Optional[str] = Field(
        default=None,
        description=(
            "Base URL for unsubscribe links. "
            "When set, the delivery service appends '?token=<email_hash>' "
            "and injects List-Unsubscribe headers automatically."
        ),
    )

    @field_validator("max_emails_per_minute")
    @classmethod
    def clamp_rate_limit(cls, v: int) -> int:
        return max(1, min(v, 1000))
