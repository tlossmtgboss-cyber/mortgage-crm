"""
Microsite Theme Marketplace - Database Models

This module defines SQLAlchemy models for the microsite theme marketplace system:
- MicrositeTheme: Registry of available themes
- Microsite: User's microsite configuration
- MicrositeProfile: Extended profile data for microsites
"""

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, ForeignKey,
    DateTime, DECIMAL, JSON, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
import enum

from database import Base


# =============================================================================
# ENUMS
# =============================================================================

class ThemeCategory(str, enum.Enum):
    """Theme category types"""
    PROFESSIONAL = "professional"
    MODERN = "modern"
    CLASSIC = "classic"
    MINIMAL = "minimal"
    BOLD = "bold"
    ELEGANT = "elegant"
    CUSTOM = "custom"


class ThemeStatus(str, enum.Enum):
    """Theme availability status"""
    ACTIVE = "active"
    DRAFT = "draft"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


# =============================================================================
# MODELS
# =============================================================================

class MicrositeTheme(Base):
    """
    Registry of available microsite themes.

    Themes define the visual appearance and layout of LO microsites.
    """
    __tablename__ = "microsite_themes"

    id = Column(Integer, primary_key=True, index=True)

    # Theme identification
    slug = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # Theme metadata
    category = Column(
        SQLEnum(ThemeCategory, name='microsite_theme_category', create_type=False),
        nullable=False,
        default=ThemeCategory.PROFESSIONAL
    )
    status = Column(
        SQLEnum(ThemeStatus, name='microsite_theme_status', create_type=False),
        nullable=False,
        default=ThemeStatus.ACTIVE
    )

    # Preview assets
    thumbnail_url = Column(String(500))
    preview_url = Column(String(500))
    preview_images = Column(JSONB, default=list)  # Array of preview image URLs

    # Theme configuration
    component_name = Column(String(100), nullable=False)  # React component name
    default_config = Column(JSONB, default=dict)  # Default theme configuration

    # Features & capabilities
    features = Column(JSONB, default=list)  # ["contact_form", "testimonials", etc.]
    supports_custom_colors = Column(Boolean, nullable=False, default=True)
    supports_custom_fonts = Column(Boolean, nullable=False, default=False)

    # Layout options
    layout_options = Column(JSONB, default=dict)

    # Pricing
    is_premium = Column(Boolean, nullable=False, default=False)
    price_cents = Column(Integer, default=0)

    # Ordering & display
    display_order = Column(Integer, nullable=False, default=0)
    is_featured = Column(Boolean, nullable=False, default=False)

    # Multi-tenant support
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"))
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    microsites = relationship("Microsite", back_populates="theme")
    organization = relationship("Organization", foreign_keys=[organization_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    def __repr__(self):
        return f"<MicrositeTheme {self.slug}: {self.name}>"

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "category": self.category.value if self.category else None,
            "status": self.status.value if self.status else None,
            "thumbnailUrl": self.thumbnail_url,
            "previewUrl": self.preview_url,
            "previewImages": self.preview_images or [],
            "componentName": self.component_name,
            "defaultConfig": self.default_config or {},
            "features": self.features or [],
            "supportsCustomColors": self.supports_custom_colors,
            "supportsCustomFonts": self.supports_custom_fonts,
            "layoutOptions": self.layout_options or {},
            "isPremium": self.is_premium,
            "priceCents": self.price_cents,
            "displayOrder": self.display_order,
            "isFeatured": self.is_featured,
        }


class Microsite(Base):
    """
    User's microsite configuration.

    Links a user to their selected theme and custom configuration.
    """
    __tablename__ = "microsites"

    id = Column(Integer, primary_key=True, index=True)

    # User linkage
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"))

    # Theme selection
    theme_id = Column(Integer, ForeignKey("microsite_themes.id", ondelete="SET NULL"))

    # Custom configuration (overrides theme defaults)
    theme_config = Column(JSONB, default=dict)

    # SEO & metadata
    meta_title = Column(String(200))
    meta_description = Column(String(500))
    og_image_url = Column(String(500))

    # Custom domain support
    custom_domain = Column(String(200))
    custom_domain_verified = Column(Boolean, default=False)

    # Publishing status
    is_published = Column(Boolean, nullable=False, default=False)
    published_at = Column(DateTime(timezone=True))

    # Analytics tracking
    ga_tracking_id = Column(String(50))
    fb_pixel_id = Column(String(50))

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization", foreign_keys=[organization_id])
    theme = relationship("MicrositeTheme", back_populates="microsites")
    profile = relationship("MicrositeProfile", back_populates="microsite", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Microsite user_id={self.user_id} theme_id={self.theme_id}>"

    def to_dict(self, include_theme=True, include_profile=True):
        """Convert to dictionary for API responses"""
        result = {
            "id": self.id,
            "userId": self.user_id,
            "themeId": self.theme_id,
            "themeConfig": self.theme_config or {},
            "metaTitle": self.meta_title,
            "metaDescription": self.meta_description,
            "ogImageUrl": self.og_image_url,
            "customDomain": self.custom_domain,
            "customDomainVerified": self.custom_domain_verified,
            "isPublished": self.is_published,
            "publishedAt": self.published_at.isoformat() if self.published_at else None,
            "gaTrackingId": self.ga_tracking_id,
            "fbPixelId": self.fb_pixel_id,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_theme and self.theme:
            result["theme"] = self.theme.to_dict()

        if include_profile and self.profile:
            result["profile"] = self.profile.to_dict()

        return result


class MicrositeProfile(Base):
    """
    Extended profile data for microsites.

    Contains theme-specific content that goes beyond the base user profile.
    """
    __tablename__ = "microsite_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # Link to microsite
    microsite_id = Column(Integer, ForeignKey("microsites.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Extended profile information
    headline = Column(String(200))  # "Your Trusted Mortgage Expert"
    tagline = Column(String(300))   # "Making homeownership dreams a reality"
    bio_extended = Column(Text)     # Longer bio for microsite

    # Hero section
    hero_image_url = Column(String(500))
    hero_video_url = Column(String(500))
    hero_background_color = Column(String(20))

    # Professional credentials
    years_experience = Column(Integer)
    total_loans_funded = Column(Integer)
    total_volume_funded = Column(DECIMAL(15, 2))  # In dollars
    specialties = Column(JSONB, default=list)  # ["First-time buyers", "VA loans"]
    certifications = Column(JSONB, default=list)  # ["CMPS", "FHA Direct Endorsed"]

    # Social proof
    testimonials = Column(JSONB, default=list)

    # Social links
    social_links = Column(JSONB, default=dict)

    # Contact preferences
    calendly_url = Column(String(500))
    contact_form_enabled = Column(Boolean, default=True)
    show_phone = Column(Boolean, default=True)
    show_email = Column(Boolean, default=True)

    # Call to action
    cta_text = Column(String(100), default="Get Started Today")
    cta_secondary_text = Column(String(100), default="Check Rates")

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    microsite = relationship("Microsite", back_populates="profile")

    def __repr__(self):
        return f"<MicrositeProfile microsite_id={self.microsite_id}>"

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "micrositeId": self.microsite_id,
            "headline": self.headline,
            "tagline": self.tagline,
            "bioExtended": self.bio_extended,
            "heroImageUrl": self.hero_image_url,
            "heroVideoUrl": self.hero_video_url,
            "heroBackgroundColor": self.hero_background_color,
            "yearsExperience": self.years_experience,
            "totalLoansFunded": self.total_loans_funded,
            "totalVolumeFunded": float(self.total_volume_funded) if self.total_volume_funded else None,
            "specialties": self.specialties or [],
            "certifications": self.certifications or [],
            "testimonials": self.testimonials or [],
            "socialLinks": self.social_links or {},
            "calendlyUrl": self.calendly_url,
            "contactFormEnabled": self.contact_form_enabled,
            "showPhone": self.show_phone,
            "showEmail": self.show_email,
            "ctaText": self.cta_text,
            "ctaSecondaryText": self.cta_secondary_text,
        }
