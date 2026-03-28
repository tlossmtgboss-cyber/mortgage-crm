"""
White-Label Configuration Models for Smart Docs V2

Per-organization branding, email template customization, and portal theming.
Supports custom logos, color schemes, fonts, email templates, compliance
footers, and custom portal domains.

Tables:
    smart_docs_white_label_configs  -- One row per org (brand, colors, compliance)
    smart_docs_email_templates      -- Per-org email templates with versioning

Usage:
    from database.models.white_label_config import WhiteLabelConfig, EmailTemplate

    config = db.query(WhiteLabelConfig).filter(
        WhiteLabelConfig.organization_id == org_id,
        WhiteLabelConfig.is_active == True,
    ).first()
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, JSON, Text,
    ForeignKey, Index,
)

from db import Base


def utcnow():
    """Return current UTC timestamp for column defaults."""
    return datetime.now(timezone.utc)


class WhiteLabelConfig(Base):
    """Per-organization white-label branding configuration.

    Stores visual identity (logo, colors, fonts), email sender settings,
    portal customization, compliance disclaimers, and custom domain config.
    Each organization can have at most one active configuration (enforced by
    the unique constraint on organization_id).
    """

    __tablename__ = "smart_docs_white_label_configs"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
        unique=True,
    )

    # --- Brand identity ---
    company_name = Column(String(200), nullable=False)
    logo_url = Column(String(500))
    favicon_url = Column(String(500))

    # --- Color palette (hex) ---
    primary_color = Column(String(7), default="#1a56db")
    secondary_color = Column(String(7), default="#7c3aed")
    accent_color = Column(String(7), default="#059669")
    header_bg_color = Column(String(7), default="#ffffff")

    # --- Typography ---
    font_family = Column(String(100), default="Inter, sans-serif")

    # --- Email sender settings ---
    email_from_name = Column(String(200))
    email_from_address = Column(String(255))
    email_reply_to = Column(String(255))
    email_footer_html = Column(Text)

    # --- Portal customization ---
    portal_welcome_message = Column(Text)
    portal_custom_css = Column(Text)  # Additional CSS overrides

    # --- SMS ---
    sms_sender_name = Column(String(50))

    # --- Support ---
    support_email = Column(String(255))
    support_phone = Column(String(20))

    # --- Legal & compliance ---
    privacy_policy_url = Column(String(500))
    terms_of_service_url = Column(String(500))
    nmls_number = Column(String(20))
    equal_housing_logo = Column(Boolean, default=True)
    disclaimer_text = Column(Text)

    # --- Custom domain ---
    custom_domain = Column(String(255))  # Custom portal domain
    ssl_status = Column(String(20), default="pending")  # pending, provisioning, active, failed
    domain_verified = Column(Boolean, default=False)
    domain_verification_token = Column(String(100))  # DNS TXT record value for verification
    vercel_domain_id = Column(String(100))  # Vercel API domain ID for management

    # --- Status ---
    is_active = Column(Boolean, default=True)

    # --- Timestamps ---
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class EmailTemplate(Base):
    """Per-organization email template with versioning and i18n.

    Template keys map to document lifecycle events:
        doc_request         -- Initial document request to borrower
        doc_reminder        -- Follow-up reminder for outstanding documents
        doc_approved        -- Document approved notification
        doc_rejected        -- Document rejected with reason
        signature_request   -- E-signature request
        welcome             -- Borrower portal welcome
        checklist_update    -- Needs-list / checklist progress update
        condition_added     -- New underwriting condition added

    Templates use {{variable}} merge-field syntax for rendering.
    """

    __tablename__ = "smart_docs_email_templates"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    template_key = Column(String(100), nullable=False)
    subject_template = Column(String(500), nullable=False)
    body_html_template = Column(Text, nullable=False)
    body_text_template = Column(Text)  # Plain text fallback
    language = Column(String(5), default="en")
    is_active = Column(Boolean, default=True)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index(
            "ix_email_templates_org_key",
            "organization_id",
            "template_key",
            "language",
        ),
    )


__all__ = [
    "WhiteLabelConfig",
    "EmailTemplate",
]
