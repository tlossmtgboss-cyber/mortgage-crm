"""
Content Library Models

Pre-built and customizable marketing content templates for mortgage professionals.
Supports Surefire-style content libraries with 1,000+ pieces across all categories
and lifecycle stages.

Usage:
    from database.models.content_library import ContentLibraryItem

    # Get all platform-default email templates
    templates = db.query(ContentLibraryItem).filter(
        ContentLibraryItem.is_platform_default == True,
        ContentLibraryItem.content_type == ContentType.EMAIL,
    ).all()

    # Get org-specific customizations
    custom = db.query(ContentLibraryItem).filter(
        ContentLibraryItem.organization_id == org_id,
    ).all()
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db import Base


# ============================================================================
# ENUMS
# ============================================================================

class ContentType(str, enum.Enum):
    """The channel/format this content piece is designed for."""
    EMAIL = "email"
    SMS = "sms"
    SOCIAL_POST = "social_post"
    BLOG = "blog"
    VIDEO_SCRIPT = "video_script"
    POSTCARD = "postcard"


class ContentCategory(str, enum.Enum):
    """Pipeline stage or lifecycle moment this content targets."""
    NEW_LEAD = "new_lead"
    APPLICATION = "application"
    PROCESSING = "processing"
    CLOSING = "closing"
    POST_CLOSE = "post_close"
    REFINANCE = "refinance"
    REFERRAL = "referral"
    HOLIDAY = "holiday"
    MARKET_UPDATE = "market_update"


# ============================================================================
# CONTENT LIBRARY ITEM MODEL
# ============================================================================

class ContentLibraryItem(Base):
    """A single piece of pre-built or custom marketing content.

    Platform-default items (is_platform_default=True, organization_id=NULL) are
    visible to all organizations and cannot be deleted by tenants — only copied
    and customized.

    Organization-specific items (organization_id=<id>) are private to that tenant
    and may be created from scratch or by customizing a platform default.

    Merge fields:
        Available personalization tokens are stored as a JSON list in merge_fields.
        Example: ["{{first_name}}", "{{loan_officer_name}}", "{{rate}}", "{{company_name}}"]
        The personalize_content() service method handles substitution at send-time.

    Compliance:
        compliance_approved must be True before an item can be sent via any campaign.
        Platform defaults ship pre-approved. Org customizations start unapproved.
    """
    __tablename__ = "content_library_items"
    __table_args__ = (
        # Fast lookups for the library browser
        Index("ix_cli_org_id", "organization_id"),
        Index("ix_cli_content_type", "content_type"),
        Index("ix_cli_category", "category"),
        Index("ix_cli_platform_default", "is_platform_default"),
        Index("ix_cli_compliance", "compliance_approved"),
        # Compound: common query pattern — org scoped by type
        Index("ix_cli_org_type", "organization_id", "content_type"),
        # Compound: org scoped by category
        Index("ix_cli_org_category", "organization_id", "category"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Tenant scoping — NULL means visible to all organizations (platform default)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # If this item was copied/forked from a platform default, track the source
    source_template_id = Column(
        Integer,
        ForeignKey("content_library_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Created / last modified by
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # -------------------------------------------------------------------------
    # Identity & Classification
    # -------------------------------------------------------------------------
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)

    content_type = Column(
        String(32),  # Stored as plain string; validated at app layer against ContentType enum
        nullable=False,
        index=True,
    )

    category = Column(
        String(32),  # Stored as plain string; validated at app layer against ContentCategory enum
        nullable=False,
        index=True,
    )

    # -------------------------------------------------------------------------
    # Content Body
    # -------------------------------------------------------------------------
    # HTML version (emails, postcards, blog excerpts)
    body_html = Column(Text, nullable=True)

    # Plain-text version (SMS, social posts, video scripts, email text fallback)
    body_text = Column(Text, nullable=True)

    # Subject line — applicable only for emails
    subject_line = Column(String(500), nullable=True)

    # -------------------------------------------------------------------------
    # Presentation
    # -------------------------------------------------------------------------
    # URL to thumbnail image (stored in S3 / CDN)
    thumbnail_url = Column(String(1024), nullable=True)

    # Arbitrary tag list for advanced filtering: ["market_update", "rate_drop", "2024"]
    # Stored as JSON list of strings
    tags = Column(JSON, nullable=True, default=list)

    # -------------------------------------------------------------------------
    # Personalization
    # -------------------------------------------------------------------------
    # List of merge field tokens available in this template
    # Example: ["{{first_name}}", "{{loan_officer_name}}", "{{company_name}}", "{{rate}}"]
    merge_fields = Column(JSON, nullable=True, default=list)

    # -------------------------------------------------------------------------
    # Platform vs. Tenant Flags
    # -------------------------------------------------------------------------
    # True = ships with the platform, visible to all orgs, cannot be deleted by tenants
    is_platform_default = Column(Boolean, nullable=False, default=False, index=True)

    # False = read-only; True = tenants may copy and customize this item
    is_customizable = Column(Boolean, nullable=False, default=True)

    # -------------------------------------------------------------------------
    # Compliance
    # -------------------------------------------------------------------------
    # Must be True before the item can be used in a live campaign
    compliance_approved = Column(Boolean, nullable=False, default=False, index=True)
    compliance_approved_at = Column(DateTime, nullable=True)
    compliance_approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Notes from compliance reviewer (e.g., "Approved with Equal Housing lender language")
    compliance_notes = Column(Text, nullable=True)

    # -------------------------------------------------------------------------
    # Usage & Quality Metrics
    # -------------------------------------------------------------------------
    # Total times this template has been sent / deployed
    usage_count = Column(Integer, nullable=False, default=0)

    # Average star rating (1.0–5.0), updated by track_usage()
    rating = Column(Numeric(3, 2), nullable=True)

    # Total number of ratings submitted (used to compute rolling average)
    rating_count = Column(Integer, nullable=False, default=0)

    # -------------------------------------------------------------------------
    # Soft Delete
    # -------------------------------------------------------------------------
    is_active = Column(Boolean, nullable=False, default=True)

    # -------------------------------------------------------------------------
    # Timestamps
    # -------------------------------------------------------------------------
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    organization = relationship(
        "Organization",
        backref="content_library_items",
        foreign_keys=[organization_id],
    )
    source_template = relationship(
        "ContentLibraryItem",
        remote_side="ContentLibraryItem.id",
        foreign_keys=[source_template_id],
    )
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    compliance_approved_by = relationship("User", foreign_keys=[compliance_approved_by_id])

    def __repr__(self) -> str:
        return (
            f"<ContentLibraryItem id={self.id} type={self.content_type!r} "
            f"category={self.category!r} title={self.title!r}>"
        )


# ============================================================================
# CONTENT USAGE LOG
# ============================================================================

class ContentUsageLog(Base):
    """Per-send tracking record for content library analytics.

    Created each time a library item is used in a campaign, one-off send,
    or manual outreach. Enables per-item open/click/conversion attribution
    and drives the rolling rating updates.
    """
    __tablename__ = "content_usage_logs"
    __table_args__ = (
        Index("ix_cul_item_id", "item_id"),
        Index("ix_cul_user_id", "user_id"),
        Index("ix_cul_org_id", "organization_id"),
        Index("ix_cul_sent_at", "sent_at"),
        Index("ix_cul_item_sent", "item_id", "sent_at"),
    )

    id = Column(Integer, primary_key=True, index=True)

    item_id = Column(
        Integer,
        ForeignKey("content_library_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Target context (nullable — may be sent to a one-off contact)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id", ondelete="SET NULL"), nullable=True)

    # Channel used (may differ if org overrides default channel)
    channel = Column(String(32), nullable=True)  # email, sms, print, social

    # Optional user rating submitted alongside this usage (1–5)
    user_rating = Column(Integer, nullable=True)

    # Engagement outcomes (populated asynchronously by webhook handlers)
    was_opened = Column(Boolean, nullable=True)
    was_clicked = Column(Boolean, nullable=True)
    was_replied = Column(Boolean, nullable=True)
    led_to_conversion = Column(Boolean, nullable=True)  # Led to application/loan

    sent_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    item = relationship("ContentLibraryItem", backref="usage_logs")
    organization = relationship("Organization")
    user = relationship("User")

    def __repr__(self) -> str:
        return f"<ContentUsageLog id={self.id} item_id={self.item_id} user_id={self.user_id}>"


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "ContentType",
    "ContentCategory",
    "ContentLibraryItem",
    "ContentUsageLog",
]
