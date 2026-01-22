"""
Carousel Builder Models

AI-powered carousel generator for social media content including:
- CarouselProject: Main project container
- CarouselSlide: Individual slides within a project
- CarouselTheme: Reusable design themes
- CarouselTemplate: Pre-built carousel templates
- CarouselExport: Export tracking
"""

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, JSON, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
import uuid

from database import Base


def generate_uuid():
    return str(uuid.uuid4())[:12]


# =============================================================================
# Enums
# =============================================================================

class CarouselProjectType(str, enum.Enum):
    JUST_CLOSED = "just_closed"
    MARKETING = "marketing"
    RATE_UPDATE = "rate_update"
    EDUCATIONAL = "educational"
    CUSTOM = "custom"


class CarouselPlatform(str, enum.Enum):
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    FACEBOOK = "facebook"


class CarouselAspectRatio(str, enum.Enum):
    SQUARE = "1:1"        # 1080x1080 - LinkedIn, Facebook, Instagram
    PORTRAIT = "4:5"      # 1080x1350 - Instagram
    STORY = "9:16"        # 1080x1920 - TikTok, Instagram Stories


class CarouselStatus(str, enum.Enum):
    DRAFT = "draft"
    GENERATING = "generating"
    READY = "ready"
    EXPORTED = "exported"


class SlideBackgroundType(str, enum.Enum):
    SOLID = "solid"
    GRADIENT = "gradient"
    IMAGE = "image"


class SlideLayoutTemplate(str, enum.Enum):
    CENTERED = "centered"
    LEFT = "left"
    RIGHT = "right"
    SPLIT = "split"
    FULL_IMAGE = "full_image"


class ExportStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# Carousel Project
# =============================================================================

class CarouselProject(Base):
    """Main carousel project container."""
    __tablename__ = "carousel_projects"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    organization_id = Column(Integer, default=1, index=True)

    # Project metadata
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    project_type = Column(
        SQLEnum(CarouselProjectType),
        default=CarouselProjectType.CUSTOM,
        nullable=False
    )

    # Platform targeting
    platform = Column(
        SQLEnum(CarouselPlatform),
        default=CarouselPlatform.LINKEDIN,
        nullable=False
    )
    aspect_ratio = Column(
        SQLEnum(CarouselAspectRatio),
        default=CarouselAspectRatio.SQUARE,
        nullable=False
    )
    width = Column(Integer, nullable=False, default=1080)
    height = Column(Integer, nullable=False, default=1080)

    # CRM data binding
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True, index=True)
    lead_id = Column(String(50), nullable=True, index=True)  # UUID from lead_profiles
    active_loan_id = Column(String(50), nullable=True, index=True)  # UUID from active_loan_profiles

    # Theme/Branding
    theme_id = Column(String(50), ForeignKey("carousel_themes.id"), nullable=True)
    custom_branding = Column(JSON, default=dict)
    # custom_branding structure:
    # {
    #     "primary_color": "#217F8D",
    #     "secondary_color": "#c9a227",
    #     "background_color": "#ffffff",
    #     "text_color": "#1a1a1a",
    #     "font_family": "Inter",
    #     "logo_url": "https://..."
    # }

    # Status
    status = Column(
        SQLEnum(CarouselStatus),
        default=CarouselStatus.DRAFT,
        nullable=False
    )

    # AI generation metadata
    ai_prompt = Column(Text, nullable=True)
    ai_generated = Column(Boolean, default=False)
    generation_tokens_used = Column(Integer, default=0)

    # Export tracking
    last_exported_at = Column(DateTime, nullable=True)
    export_format = Column(String(20), nullable=True)  # png, jpg

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    slides = relationship(
        "CarouselSlide",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="CarouselSlide.order"
    )
    theme = relationship("CarouselTheme", foreign_keys=[theme_id])
    exports = relationship(
        "CarouselExport",
        back_populates="project",
        cascade="all, delete-orphan"
    )


# =============================================================================
# Carousel Slide
# =============================================================================

class CarouselSlide(Base):
    """Individual slide within a carousel project."""
    __tablename__ = "carousel_slides"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    project_id = Column(
        String(50),
        ForeignKey("carousel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Ordering
    order = Column(Integer, nullable=False, default=0)

    # Slide content
    title = Column(String(500), nullable=True)
    subtitle = Column(String(500), nullable=True)
    body_text = Column(Text, nullable=True)

    # Background
    background_type = Column(
        SQLEnum(SlideBackgroundType),
        default=SlideBackgroundType.SOLID,
        nullable=False
    )
    background_color = Column(String(20), default="#ffffff")  # hex color
    background_gradient = Column(JSON, nullable=True)
    # gradient structure: {"type": "linear", "angle": 135, "colors": ["#667eea", "#764ba2"]}
    background_image_url = Column(Text, nullable=True)
    background_image_key = Column(String(500), nullable=True)  # S3 key

    # Layout
    layout_template = Column(
        SQLEnum(SlideLayoutTemplate),
        default=SlideLayoutTemplate.CENTERED,
        nullable=False
    )

    # Elements (stored as JSON for flexibility)
    elements = Column(JSON, default=list)
    # elements structure:
    # [
    #     {
    #         "id": "elem_123",
    #         "type": "text",  # text, image, shape, icon
    #         "content": "Hello World",
    #         "position": {"x": 50, "y": 30},  # percentage
    #         "size": {"width": 80, "height": null},  # percentage, null = auto
    #         "styles": {
    #             "fontSize": 48,
    #             "fontWeight": "bold",
    #             "color": "#1a1a1a",
    #             "textAlign": "center"
    #         },
    #         "dataBinding": "loan.amount"  # optional CRM data token
    #     }
    # ]

    # Slide-specific style overrides
    custom_styles = Column(JSON, default=dict)
    # custom_styles structure:
    # {
    #     "padding": 40,
    #     "textColor": "#ffffff",
    #     "overlayColor": "rgba(0,0,0,0.5)"
    # }

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("CarouselProject", back_populates="slides")


# =============================================================================
# Carousel Theme
# =============================================================================

class CarouselTheme(Base):
    """Reusable design themes for carousels."""
    __tablename__ = "carousel_themes"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL for system themes
    organization_id = Column(Integer, default=1)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    preview_url = Column(Text, nullable=True)

    # Theme definition
    colors = Column(JSON, default=dict)
    # colors structure:
    # {
    #     "primary": "#217F8D",
    #     "secondary": "#c9a227",
    #     "accent": "#ec4899",
    #     "background": "#ffffff",
    #     "text": "#1a1a1a",
    #     "muted": "#6b7280"
    # }

    typography = Column(JSON, default=dict)
    # typography structure:
    # {
    #     "headingFont": "Inter",
    #     "bodyFont": "Inter",
    #     "titleSize": 48,
    #     "subtitleSize": 24,
    #     "bodySize": 18
    # }

    spacing = Column(JSON, default=dict)
    # spacing structure:
    # {
    #     "padding": 40,
    #     "elementGap": 16
    # }

    decorations = Column(JSON, default=dict)
    # decorations structure:
    # {
    #     "cornerRadius": 0,
    #     "showBorder": false,
    #     "borderColor": "#e5e7eb",
    #     "shadowEnabled": false
    # }

    # Categorization
    category = Column(String(100), nullable=True)  # celebration, professional, modern, elegant
    tags = Column(JSON, default=list)

    # Usage tracking
    times_used = Column(Integer, default=0)
    is_system = Column(Boolean, default=False)  # System themes can't be deleted
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


# =============================================================================
# Carousel Template
# =============================================================================

class CarouselTemplate(Base):
    """Pre-built carousel templates with slide structures."""
    __tablename__ = "carousel_templates"

    id = Column(String(50), primary_key=True, default=generate_uuid)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    preview_url = Column(Text, nullable=True)

    # Template type
    template_type = Column(
        SQLEnum(CarouselProjectType),
        default=CarouselProjectType.CUSTOM,
        nullable=False
    )
    platform = Column(
        SQLEnum(CarouselPlatform),
        default=CarouselPlatform.LINKEDIN,
        nullable=False
    )
    aspect_ratio = Column(
        SQLEnum(CarouselAspectRatio),
        default=CarouselAspectRatio.SQUARE,
        nullable=False
    )

    # Template structure (JSON definition of slides)
    slide_templates = Column(JSON, default=list)
    # slide_templates structure:
    # [
    #     {
    #         "title": "{{headline}}",
    #         "subtitle": "{{subheadline}}",
    #         "body_text": null,
    #         "background_type": "gradient",
    #         "background_gradient": {"type": "linear", "angle": 135, "colors": ["#667eea", "#764ba2"]},
    #         "layout_template": "centered",
    #         "elements": []
    #     },
    #     ...
    # ]

    # Default theme
    default_theme_id = Column(String(50), ForeignKey("carousel_themes.id"), nullable=True)

    # Data requirements
    required_data_bindings = Column(JSON, default=list)  # ["loan.amount", "property.address"]
    optional_data_bindings = Column(JSON, default=list)

    # Categorization
    category = Column(String(100), nullable=True)
    tags = Column(JSON, default=list)

    # Usage tracking
    times_used = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    default_theme = relationship("CarouselTheme", foreign_keys=[default_theme_id])


# =============================================================================
# Carousel Export
# =============================================================================

class CarouselExport(Base):
    """Track carousel exports."""
    __tablename__ = "carousel_exports"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    project_id = Column(
        String(50),
        ForeignKey("carousel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Export details
    export_format = Column(String(20), nullable=False, default="png")  # png, jpg
    quality = Column(Integer, default=90)  # JPEG quality (1-100)
    scale = Column(Integer, default=2)  # Resolution multiplier (1x, 2x)

    # Files (array of S3 keys for each slide)
    file_keys = Column(JSON, default=list)
    # file_keys structure: ["carousels/abc123/exports/20240115/slide_0.png", ...]
    zip_file_key = Column(String(500), nullable=True)  # Combined ZIP file S3 key

    # Status
    status = Column(
        SQLEnum(ExportStatus),
        default=ExportStatus.PENDING,
        nullable=False
    )
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    project = relationship("CarouselProject", back_populates="exports")
