"""
Microsite Theme Marketplace Routes

API endpoints for the microsite theme marketplace system:
- Theme browsing and selection
- Microsite configuration
- Profile customization

This module provides both public and authenticated endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging
import uuid

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: EXPERIMENTAL
# This module is in the experimental tier -- frozen, no SLA.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

# Security scheme
security = HTTPBearer(auto_error=False)


def ensure_microsite_columns_exist():
    """Ensure content_json and branding_json columns exist in microsites table."""
    try:
        from database import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            # Check if columns already exist
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'microsites'
                AND column_name IN ('content_json', 'branding_json')
            """))
            existing_columns = [row[0] for row in result.fetchall()]

            if 'content_json' not in existing_columns:
                logger.info("Adding content_json column to microsites table...")
                conn.execute(text("""
                    ALTER TABLE microsites
                    ADD COLUMN content_json JSONB DEFAULT '{}'::jsonb
                """))
                logger.info("content_json column added successfully")

            if 'branding_json' not in existing_columns:
                logger.info("Adding branding_json column to microsites table...")
                conn.execute(text("""
                    ALTER TABLE microsites
                    ADD COLUMN branding_json JSONB DEFAULT '{}'::jsonb
                """))
                logger.info("branding_json column added successfully")

            conn.commit()
    except Exception as e:
        logger.warning(f"Could not ensure microsite columns exist: {e}")


# Run migration on module load
ensure_microsite_columns_exist()

# Lazy imports to avoid circular dependencies
def get_db():
    """Wrapper for get_db to avoid circular import."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current authenticated user."""
    from auth.dependencies import get_current_user_flexible
    # Use the flexible auth from main.py
    return await get_current_user_flexible(request=request, db=db)


# =============================================================================
# ROUTERS
# =============================================================================

# Public routes (no auth required)
public_router = APIRouter(prefix="/api/v1/public/themes", tags=["Microsite Themes (Public)"])

# Authenticated routes
auth_router = APIRouter(prefix="/api/v1/microsites", tags=["Microsite Configuration"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ThemeResponse(BaseModel):
    """Theme data for API responses"""
    id: int
    slug: str
    name: str
    description: Optional[str] = None
    category: str
    thumbnailUrl: Optional[str] = None
    previewUrl: Optional[str] = None
    previewImages: List[str] = []
    componentName: str
    defaultConfig: Dict[str, Any] = {}
    features: List[str] = []
    supportsCustomColors: bool = True
    supportsCustomFonts: bool = False
    layoutOptions: Dict[str, Any] = {}
    isPremium: bool = False
    priceCents: int = 0
    isFeatured: bool = False

    class Config:
        from_attributes = True


class ThemeListResponse(BaseModel):
    """List of themes"""
    themes: List[ThemeResponse]
    total: int
    featured: List[ThemeResponse] = []


class MicrositeConfigUpdate(BaseModel):
    """Update microsite configuration"""
    theme_id: Optional[int] = None
    theme_config: Optional[Dict[str, Any]] = None
    content_json: Optional[Dict[str, Any]] = None
    branding_json: Optional[Dict[str, Any]] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    og_image_url: Optional[str] = None
    ga_tracking_id: Optional[str] = None
    fb_pixel_id: Optional[str] = None
    is_published: Optional[bool] = None


class MicrositeProfileUpdate(BaseModel):
    """Update microsite profile"""
    headline: Optional[str] = None
    tagline: Optional[str] = None
    bio_extended: Optional[str] = None
    hero_image_url: Optional[str] = None
    hero_video_url: Optional[str] = None
    hero_background_color: Optional[str] = None
    years_experience: Optional[int] = None
    total_loans_funded: Optional[int] = None
    total_volume_funded: Optional[float] = None
    specialties: Optional[List[str]] = None
    certifications: Optional[List[str]] = None
    testimonials: Optional[List[Dict[str, Any]]] = None
    social_links: Optional[Dict[str, str]] = None
    calendly_url: Optional[str] = None
    contact_form_enabled: Optional[bool] = None
    show_phone: Optional[bool] = None
    show_email: Optional[bool] = None
    cta_text: Optional[str] = None
    cta_secondary_text: Optional[str] = None


class MicrositeResponse(BaseModel):
    """Full microsite data response"""
    id: int
    userId: int
    themeId: Optional[int] = None
    themeConfig: Dict[str, Any] = {}
    metaTitle: Optional[str] = None
    metaDescription: Optional[str] = None
    ogImageUrl: Optional[str] = None
    isPublished: bool = False
    publishedAt: Optional[str] = None
    gaTrackingId: Optional[str] = None
    fbPixelId: Optional[str] = None
    theme: Optional[ThemeResponse] = None
    profile: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class PublicMicrositeResponse(BaseModel):
    """Public-facing microsite data for rendering"""
    theme: ThemeResponse
    themeConfig: Dict[str, Any] = {}
    profile: Dict[str, Any] = {}
    user: Dict[str, Any] = {}

    class Config:
        from_attributes = True


# =============================================================================
# THEME SEEDING
# =============================================================================

def seed_default_themes(db: Session):
    """
    Seed default microsite themes if they don't exist.
    This ensures the system is self-initializing.
    Also renames 'leadpops-cardinal' to 'bold-impact' if it exists.
    """
    from microsite_models import MicrositeTheme, ThemeStatus, ThemeCategory

    # First, check if old 'leadpops-cardinal' theme exists and rename it
    old_theme = db.query(MicrositeTheme).filter(
        MicrositeTheme.slug == "leadpops-cardinal"
    ).first()

    if old_theme:
        logger.info("Renaming 'leadpops-cardinal' to 'bold-impact'...")
        old_theme.slug = "bold-impact"
        old_theme.name = "Bold Impact"
        old_theme.description = "A bold, modern theme with strong call-to-actions and lead capture focus."
        old_theme.component_name = "BoldImpact"
        db.commit()
        logger.info("Theme renamed successfully")

    default_themes = [
        {
            "slug": "bold-impact",
            "name": "Bold Impact",
            "description": "A bold, modern theme with strong call-to-actions and lead capture focus.",
            "category": ThemeCategory.BOLD,
            "component_name": "BoldImpact",
            "features": ["hero_image", "contact_form", "rate_calculator", "testimonials", "about_section"],
            "display_order": 1,
            "is_featured": True,
            "supports_custom_colors": True,
            "supports_custom_fonts": True,
            "layout_options": {"heroStyle": ["image", "gradient"], "headerStyle": ["centered", "left"]}
        },
        {
            "slug": "professional-clean",
            "name": "Professional Clean",
            "description": "A clean, professional theme perfect for established loan officers.",
            "category": ThemeCategory.PROFESSIONAL,
            "component_name": "ProfessionalClean",
            "features": ["hero_image", "contact_form", "credentials", "about_section"],
            "display_order": 2,
            "is_featured": False,
            "supports_custom_colors": True,
            "supports_custom_fonts": True,
            "layout_options": {"heroStyle": ["solid", "image"], "headerStyle": ["centered", "left"]}
        },
        {
            "slug": "modern-gradient",
            "name": "Modern Gradient",
            "description": "A contemporary theme with gradient backgrounds and smooth animations.",
            "category": ThemeCategory.MODERN,
            "component_name": "ModernGradient",
            "features": ["hero_gradient", "contact_form", "testimonials", "about_section"],
            "display_order": 3,
            "is_featured": False,
            "supports_custom_colors": True,
            "supports_custom_fonts": True,
            "layout_options": {"gradientDirection": ["diagonal", "horizontal", "vertical"]}
        },
        {
            "slug": "minimal-focus",
            "name": "Minimal Focus",
            "description": "A minimalist theme that puts the focus on your message and lead capture.",
            "category": ThemeCategory.MINIMAL,
            "component_name": "MinimalFocus",
            "features": ["contact_form", "about_section"],
            "display_order": 4,
            "is_featured": False,
            "supports_custom_colors": True,
            "supports_custom_fonts": True,
            "layout_options": {"layout": ["centered", "split"]}
        }
    ]

    seeded_count = 0
    for theme_data in default_themes:
        # Check if theme already exists
        existing = db.query(MicrositeTheme).filter(
            MicrositeTheme.slug == theme_data["slug"]
        ).first()

        if not existing:
            theme = MicrositeTheme(
                slug=theme_data["slug"],
                name=theme_data["name"],
                description=theme_data["description"],
                category=theme_data["category"],  # Keep as ThemeCategory enum
                status=ThemeStatus.ACTIVE,  # Keep as ThemeStatus enum
                component_name=theme_data["component_name"],
                features=theme_data["features"],
                display_order=theme_data["display_order"],
                is_featured=theme_data["is_featured"],
                supports_custom_colors=theme_data["supports_custom_colors"],
                supports_custom_fonts=theme_data["supports_custom_fonts"],
                layout_options=theme_data["layout_options"]
            )
            db.add(theme)
            seeded_count += 1

    if seeded_count > 0:
        db.commit()
        logger.info(f"Seeded {seeded_count} default themes")

    return seeded_count


# =============================================================================
# PUBLIC ROUTES
# =============================================================================

def ensure_themes_table_exists(db: Session):
    """
    Ensure the microsite_themes table exists and is seeded.
    Creates the table if it doesn't exist using the raw SQL migration.
    """
    from sqlalchemy import text
    from database import engine
    from pathlib import Path

    try:
        # Check if table exists
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'microsite_themes'
                )
            """))
            table_exists = result.scalar()

            if not table_exists:
                logger.info("microsite_themes table does not exist, creating via migration...")

                # Read and execute the migration SQL file
                migration_path = Path(__file__).parent / "migrations" / "add_microsite_themes.sql"
                if migration_path.exists():
                    sql = migration_path.read_text()
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info("Migration executed successfully")
                    return True
                else:
                    logger.error(f"Migration file not found at {migration_path}")
                    return False

    except Exception as e:
        logger.error(f"Error ensuring themes table exists: {e}")
        # Don't raise - try to continue anyway

    return False


@public_router.get("", response_model=ThemeListResponse)
async def list_themes(
    category: Optional[str] = Query(None, description="Filter by category"),
    featured_only: bool = Query(False, description="Only show featured themes"),
    db: Session = Depends(get_db)
):
    """
    List all available microsite themes.

    This is a public endpoint for browsing the theme marketplace.
    Auto-seeds default themes if none exist.
    """
    try:
        from microsite_models import MicrositeTheme, ThemeStatus, ThemeCategory

        # Ensure table exists
        ensure_themes_table_exists(db)

        # Check for old 'leadpops-cardinal' theme and rename it
        old_theme = db.query(MicrositeTheme).filter(
            MicrositeTheme.slug == "leadpops-cardinal"
        ).first()

        if old_theme:
            logger.info("Auto-renaming 'leadpops-cardinal' to 'bold-impact'...")
            old_theme.slug = "bold-impact"
            old_theme.name = "Bold Impact"
            old_theme.description = "A bold, modern theme with strong call-to-actions and lead capture focus."
            old_theme.component_name = "BoldImpact"
            db.commit()
            logger.info("Theme renamed successfully")

        # Also check for old component_name and update it
        old_component = db.query(MicrositeTheme).filter(
            MicrositeTheme.component_name == "LeadPopsCardinal"
        ).first()

        if old_component:
            logger.info("Updating component_name from 'LeadPopsCardinal' to 'BoldImpact'...")
            old_component.component_name = "BoldImpact"
            db.commit()
            logger.info("Component name updated successfully")

        # Check if any themes exist, seed defaults if not
        theme_count = db.query(MicrositeTheme).count()
        if theme_count == 0:
            logger.info("No themes found, seeding defaults...")
            seed_default_themes(db)

        # Use text() for enum comparison to bypass SQLAlchemy enum conversion
        from sqlalchemy import text
        query = db.query(MicrositeTheme).filter(
            text("microsite_themes.status = 'active'")
        )

        # Filter by category
        if category:
            # Use lowercase string value for category enum
            query = query.filter(MicrositeTheme.category == category.lower())

        # Filter featured only
        if featured_only:
            query = query.filter(MicrositeTheme.is_featured == True)

        # Order by display_order
        query = query.order_by(MicrositeTheme.display_order, MicrositeTheme.name)

        themes = query.all()

        # Get featured themes separately - use text() to bypass enum conversion
        featured_query = db.query(MicrositeTheme).filter(
            text("microsite_themes.status = 'active'"),
            MicrositeTheme.is_featured == True
        ).order_by(MicrositeTheme.display_order).limit(5)
        featured_themes = featured_query.all()

        return ThemeListResponse(
            themes=[ThemeResponse(**t.to_dict()) for t in themes],
            total=len(themes),
            featured=[ThemeResponse(**t.to_dict()) for t in featured_themes]
        )

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error listing themes: {e}\n{error_trace}")
        raise HTTPException(status_code=500, detail="Error loading themes")


@public_router.get("/{theme_slug}", response_model=ThemeResponse)
async def get_theme(
    theme_slug: str,
    db: Session = Depends(get_db)
):
    """
    Get a specific theme by slug.
    """
    try:
        from microsite_models import MicrositeTheme, ThemeStatus

        from sqlalchemy import text
        theme = db.query(MicrositeTheme).filter(
            MicrositeTheme.slug == theme_slug,
            text("microsite_themes.status = 'active'")
        ).first()

        if not theme:
            raise HTTPException(status_code=404, detail="Theme not found")

        return ThemeResponse(**theme.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching theme: {e}")
        raise HTTPException(status_code=500, detail="Error loading theme")


@public_router.get("/render/{user_slug}")
async def get_public_microsite(
    user_slug: str,
    db: Session = Depends(get_db)
):
    """
    Get public microsite data for rendering.

    This endpoint returns all data needed to render a public microsite,
    including theme, configuration, profile, and user info.
    """
    try:
        from database.models import User
        from microsite_models import UserMicrosite as Microsite, MicrositeTheme, MicrositeProfile

        # Find user by slug
        user = db.query(User).filter(
            User.slug == user_slug,
            User.is_active == True
        ).first()

        if not user:
            # Try by ID
            try:
                user_id = int(user_slug)
                user = db.query(User).filter(
                    User.id == user_id,
                    User.is_active == True
                ).first()
            except ValueError:
                pass

        if not user:
            raise HTTPException(status_code=404, detail="Loan officer not found")

        # Get microsite configuration
        microsite = db.query(Microsite).filter(
            Microsite.user_id == user.id
        ).options(
            joinedload(Microsite.theme),
            joinedload(Microsite.profile)
        ).first()

        # If no microsite configured, use default theme
        if not microsite:
            default_theme = db.query(MicrositeTheme).filter(
                MicrositeTheme.slug == "bold-impact"
            ).first()

            if not default_theme:
                # Fallback to any active theme
                from sqlalchemy import text
                default_theme = db.query(MicrositeTheme).filter(
                    text("microsite_themes.status = 'active'")
                ).first()

            theme_data = default_theme.to_dict() if default_theme else {
                "id": 0,
                "slug": "default",
                "name": "Default Theme",
                "componentName": "LOMicrosite",
                "features": ["contact_form"],
            }
            theme_config = {}
            profile_data = {}
        else:
            theme_data = microsite.theme.to_dict() if microsite.theme else {
                "id": 0,
                "slug": "default",
                "name": "Default Theme",
                "componentName": "LOMicrosite",
                "features": ["contact_form"],
            }
            # Merge theme_config with branding data so logo and colors are available
            theme_config = microsite.theme_config or {}
            # Check for branding_json in theme_config or as separate attribute
            branding = getattr(microsite, 'branding_json', None) or theme_config.get('branding', {}) or {}
            if branding:
                # Map branding fields to themeConfig (check both camelCase and snake_case)
                logo = branding.get('logoUrl') or branding.get('logo_url')
                if logo:
                    theme_config['logoUrl'] = logo
                hero_image = branding.get('heroImageUrl') or branding.get('hero_image_url')
                if hero_image:
                    theme_config['heroImageUrl'] = hero_image
                primary = branding.get('primaryColor') or branding.get('primary_color')
                if primary:
                    theme_config['primaryColor'] = primary
                secondary = branding.get('secondaryColor') or branding.get('secondary_color')
                if secondary:
                    theme_config['secondaryColor'] = secondary
                accent = branding.get('accentColor') or branding.get('accent_color')
                if accent:
                    theme_config['accentColor'] = accent
            profile_data = microsite.profile.to_dict() if microsite.profile else {}

        # Build user data (public fields only)
        # Extract bio from user_metadata JSON if available
        user_metadata = getattr(user, 'user_metadata', None) or {}
        bio = user_metadata.get('bio') if isinstance(user_metadata, dict) else getattr(user, 'bio', None)

        user_data = {
            "id": user.id,
            "name": user.full_name or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
            "email": user.email,
            "phone": user.phone,
            "nmls_id": user.nmls_number,
            "slug": user.slug,
            "company": getattr(user, 'company', None),
            "bio": bio,
            "photo_url": getattr(user, 'photo_url', None) or getattr(user, 'avatar_url', None),
        }

        return {
            "theme": theme_data,
            "themeConfig": theme_config,
            "profile": profile_data,
            "user": user_data
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error fetching public microsite: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Error loading microsite")


# =============================================================================
# ONE-TIME SETUP ENDPOINT (can be removed after setup)
# =============================================================================

@public_router.post("/setup-tim-loss")
async def setup_tim_loss_microsite(db: Session = Depends(get_db)):
    """One-time setup endpoint for tim-loss microsite with bio and theme colors."""
    try:
        from database.models import User
        from microsite_models import UserMicrosite as Microsite, MicrositeTheme

        # Find tim-loss user
        user = db.query(User).filter(User.slug == "tim-loss").first()
        if not user:
            raise HTTPException(status_code=404, detail="User tim-loss not found")

        # Update user bio in metadata (use flag_modified for JSON column updates)
        from sqlalchemy.orm.attributes import flag_modified
        current_metadata = dict(user.user_metadata) if user.user_metadata else {}
        current_metadata["bio"] = "Experienced mortgage professional dedicated to helping clients achieve their homeownership dreams with personalized service and competitive rates."
        user.user_metadata = current_metadata
        flag_modified(user, "user_metadata")

        # Get or create microsite
        microsite = db.query(Microsite).filter(Microsite.user_id == user.id).first()

        # Get bold-impact theme
        theme = db.query(MicrositeTheme).filter(MicrositeTheme.slug == "bold-impact").first()

        theme_config = {
            "primaryColor": "#2d5a27",
            "secondaryColor": "#4a8c3f",
            "accentColor": "#8bc34a",
            "textColor": "#1a1a1a",
            "backgroundColor": "#ffffff"
        }

        if not microsite:
            microsite = Microsite(
                user_id=user.id,
                theme_id=theme.id if theme else 1,
                theme_config=theme_config,
                is_published=True
            )
            db.add(microsite)
        else:
            microsite.theme_config = theme_config
            if theme:
                microsite.theme_id = theme.id

        db.commit()
        return {"status": "success", "message": "Microsite configured with forest green theme and bio", "user_id": user.id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting up tim-loss microsite: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@public_router.post("/add-testimonials-page/{user_slug}")
async def add_testimonials_page_for_user(user_slug: str, db: Session = Depends(get_db)):
    """One-time endpoint to add a Testimonials page for a user's microsite."""
    try:
        from database.models import User
        from microsite_models import UserMicrosite as Microsite, MicrositeContentPage, PageType

        # Find user
        user = db.query(User).filter(User.slug == user_slug).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User {user_slug} not found")

        # Get microsite
        microsite = db.query(Microsite).filter(Microsite.user_id == user.id).first()
        if not microsite:
            raise HTTPException(status_code=404, detail="Microsite not found for this user")

        # Check if Testimonials page already exists
        existing = db.query(MicrositeContentPage).filter(
            MicrositeContentPage.microsite_id == microsite.id,
            MicrositeContentPage.slug == "testimonials"
        ).first()

        if existing:
            return {"status": "exists", "message": "Testimonials page already exists", "page_id": existing.id}

        user_name = user.full_name or user_slug.replace("-", " ").title()

        # Create Testimonials page content with sample reviews
        content = {
            "headline": "What Our Clients Say",
            "subheadline": "Real stories from homeowners I've helped achieve their dreams",
            "testimonials": [
                {
                    "name": "Sarah & Michael Johnson",
                    "location": "Denver, CO",
                    "type": "First-Time Homebuyers",
                    "rating": 5,
                    "text": f"As first-time homebuyers, we were nervous about the entire process. {user_name} made everything so easy to understand and was always available to answer our questions. We closed on our dream home in just 30 days!",
                    "date": "2024"
                },
                {
                    "name": "Robert Chen",
                    "location": "Aurora, CO",
                    "type": "Refinance",
                    "rating": 5,
                    "text": f"{user_name} helped us refinance and save over $400/month on our mortgage. The process was smooth and {user_name} kept us informed every step of the way. Highly recommend!",
                    "date": "2024"
                },
                {
                    "name": "Jennifer Martinez",
                    "location": "Boulder, CO",
                    "type": "VA Loan",
                    "rating": 5,
                    "text": f"As a veteran, I wanted someone who understood VA loans. {user_name} was incredibly knowledgeable and helped me take advantage of benefits I didn't even know I had. Thank you for your patience and expertise!",
                    "date": "2024"
                },
                {
                    "name": "David & Lisa Thompson",
                    "location": "Lakewood, CO",
                    "type": "Investment Property",
                    "rating": 5,
                    "text": f"We've worked with {user_name} on multiple investment properties now. Always professional, always delivers great rates, and makes the process stress-free. Our go-to mortgage professional!",
                    "date": "2023"
                },
                {
                    "name": "Amanda Wilson",
                    "location": "Centennial, CO",
                    "type": "FHA Loan",
                    "rating": 5,
                    "text": f"I thought my credit score would prevent me from buying a home, but {user_name} found an FHA loan that worked for my situation. Now I'm a proud homeowner! Forever grateful.",
                    "date": "2024"
                },
                {
                    "name": "James & Patricia Brown",
                    "location": "Highlands Ranch, CO",
                    "type": "Jumbo Loan",
                    "rating": 5,
                    "text": f"Buying our luxury home required a jumbo loan, and {user_name} navigated the complexities with ease. Excellent communication throughout and a seamless closing. Top-notch service!",
                    "date": "2024"
                }
            ],
            "stats": {
                "totalClients": "500+",
                "avgRating": "4.9",
                "yearsExperience": "10+"
            },
            "cta": {
                "headline": "Ready to Start Your Journey?",
                "text": "Join hundreds of satisfied clients who've found their perfect home.",
                "buttonText": "Get Started Today"
            }
        }

        # Create the Testimonials page
        testimonials_page = MicrositeContentPage(
            microsite_id=microsite.id,
            page_type=PageType.TESTIMONIALS,
            slug="testimonials",
            title="Reviews",
            content=content,
            is_enabled=True,
            display_order=3,
            show_in_nav=True
        )
        db.add(testimonials_page)
        db.commit()
        db.refresh(testimonials_page)

        return {"status": "success", "message": "Testimonials page created", "page_id": testimonials_page.id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding testimonials page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@public_router.post("/add-services-page/{user_slug}")
async def add_services_page_for_user(user_slug: str, db: Session = Depends(get_db)):
    """One-time endpoint to add a Services/Loan Programs page for a user's microsite."""
    try:
        from database.models import User
        from microsite_models import UserMicrosite as Microsite, MicrositeContentPage, PageType

        # Find user
        user = db.query(User).filter(User.slug == user_slug).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User {user_slug} not found")

        # Get microsite
        microsite = db.query(Microsite).filter(Microsite.user_id == user.id).first()
        if not microsite:
            raise HTTPException(status_code=404, detail="Microsite not found for this user")

        # Check if Services page already exists
        existing = db.query(MicrositeContentPage).filter(
            MicrositeContentPage.microsite_id == microsite.id,
            MicrositeContentPage.slug == "services"
        ).first()

        if existing:
            return {"status": "exists", "message": "Services page already exists", "page_id": existing.id}

        # Create Services page content with loan programs
        content = {
            "headline": "Loan Programs & Services",
            "subheadline": "Find the perfect mortgage solution for your needs",
            "programs": [
                {
                    "name": "Conventional Loans",
                    "icon": "home",
                    "description": "Traditional financing with competitive rates for qualified buyers. Ideal for borrowers with good credit and stable income.",
                    "features": ["As low as 3% down payment", "Fixed and adjustable rate options", "No mortgage insurance with 20% down", "Loan amounts up to conforming limits"]
                },
                {
                    "name": "FHA Loans",
                    "icon": "shield",
                    "description": "Government-backed loans designed to help first-time homebuyers and those with lower credit scores achieve homeownership.",
                    "features": ["Down payments as low as 3.5%", "More flexible credit requirements", "Lower closing costs", "Gift funds allowed for down payment"]
                },
                {
                    "name": "VA Loans",
                    "icon": "star",
                    "description": "Exclusive benefits for our veterans and active military. Thank you for your service - let us help you find your home.",
                    "features": ["No down payment required", "No private mortgage insurance", "Competitive interest rates", "Limited closing costs"]
                },
                {
                    "name": "USDA Loans",
                    "icon": "tree",
                    "description": "Zero-down financing for eligible rural and suburban properties. Perfect for buyers looking outside major metro areas.",
                    "features": ["No down payment required", "Below-market interest rates", "Low mortgage insurance", "Flexible credit guidelines"]
                },
                {
                    "name": "Jumbo Loans",
                    "icon": "building",
                    "description": "Financing for luxury homes and high-cost areas that exceed conventional loan limits.",
                    "features": ["Loan amounts above conforming limits", "Competitive rates for high-value properties", "Various term options available", "Interest-only options available"]
                },
                {
                    "name": "Refinance Options",
                    "icon": "refresh",
                    "description": "Lower your rate, reduce your term, or tap into your home's equity with our refinancing solutions.",
                    "features": ["Rate-and-term refinancing", "Cash-out refinancing", "Streamline refinance programs", "Debt consolidation options"]
                }
            ],
            "cta": {
                "headline": "Not sure which program is right for you?",
                "text": "Schedule a free consultation and I'll help you find the perfect loan for your situation.",
                "buttonText": "Get Started Today"
            }
        }

        # Create the Services page
        services_page = MicrositeContentPage(
            microsite_id=microsite.id,
            page_type=PageType.SERVICES,
            slug="services",
            title="Loan Programs",
            content=content,
            is_enabled=True,
            display_order=2,
            show_in_nav=True
        )
        db.add(services_page)
        db.commit()
        db.refresh(services_page)

        return {"status": "success", "message": "Services page created", "page_id": services_page.id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding services page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@public_router.post("/add-about-page/{user_slug}")
async def add_about_page_for_user(user_slug: str, db: Session = Depends(get_db)):
    """One-time endpoint to add an About page for a user's microsite."""
    try:
        from database.models import User
        from microsite_models import UserMicrosite as Microsite, MicrositeContentPage, PageType

        # Find user
        user = db.query(User).filter(User.slug == user_slug).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User {user_slug} not found")

        # Get microsite
        microsite = db.query(Microsite).filter(Microsite.user_id == user.id).first()
        if not microsite:
            raise HTTPException(status_code=404, detail="Microsite not found for this user")

        # Check if About page already exists
        existing = db.query(MicrositeContentPage).filter(
            MicrositeContentPage.microsite_id == microsite.id,
            MicrositeContentPage.slug == "about"
        ).first()

        if existing:
            return {"status": "exists", "message": "About page already exists", "page_id": existing.id}

        # Create About page content
        user_name = user.full_name or user.slug.replace("-", " ").title()
        content = {
            "headline": f"About {user_name}",
            "story": "With years of experience in the mortgage industry, I'm dedicated to helping families achieve their dream of homeownership. My approach combines deep market knowledge with personalized service to find the perfect loan solution for each client.",
            "values": [
                {"title": "Integrity", "description": "Honest, transparent communication at every step"},
                {"title": "Expertise", "description": "Deep knowledge of loan products and market conditions"},
                {"title": "Service", "description": "Responsive, personalized attention to your needs"}
            ],
            "certifications": [],
            "yearsExperience": "10+"
        }

        # Create the About page
        about_page = MicrositeContentPage(
            microsite_id=microsite.id,
            page_type=PageType.ABOUT,
            slug="about",
            title="About Me",
            content=content,
            is_enabled=True,
            display_order=1,
            show_in_nav=True
        )
        db.add(about_page)
        db.commit()
        db.refresh(about_page)

        return {"status": "success", "message": "About page created", "page_id": about_page.id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding about page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# AUTHENTICATED ROUTES
# =============================================================================

@auth_router.get("/my-microsite", response_model=MicrositeResponse)
async def get_my_microsite(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get the current user's microsite configuration.
    """
    try:
        from microsite_models import UserMicrosite as Microsite

        microsite = db.query(Microsite).filter(
            Microsite.user_id == current_user.id
        ).options(
            joinedload(Microsite.theme),
            joinedload(Microsite.profile)
        ).first()

        if not microsite:
            # Return empty configuration
            return MicrositeResponse(
                id=0,
                userId=current_user.id,
                themeId=None,
                themeConfig={},
                isPublished=False
            )

        return MicrositeResponse(**microsite.to_dict())

    except Exception as e:
        logger.error(f"Error fetching microsite: {e}")
        raise HTTPException(status_code=500, detail="Error loading microsite configuration")


@auth_router.put("/my-microsite", response_model=MicrositeResponse)
async def update_my_microsite(
    update_data: MicrositeConfigUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Update the current user's microsite configuration.

    Creates a new microsite if one doesn't exist.
    """
    try:
        from microsite_models import UserMicrosite as Microsite, MicrositeTheme

        # Get or create microsite
        microsite = db.query(Microsite).filter(
            Microsite.user_id == current_user.id
        ).first()

        if not microsite:
            microsite = Microsite(
                user_id=current_user.id,
                organization_id=current_user.organization_id
            )
            db.add(microsite)

        # Validate theme_id if provided
        if update_data.theme_id is not None:
            theme = db.query(MicrositeTheme).filter(
                MicrositeTheme.id == update_data.theme_id
            ).first()
            if not theme:
                raise HTTPException(status_code=400, detail="Invalid theme ID")

        # Update fields
        if update_data.theme_id is not None:
            microsite.theme_id = update_data.theme_id
        if update_data.theme_config is not None:
            microsite.theme_config = update_data.theme_config
        if update_data.content_json is not None:
            microsite.content_json = update_data.content_json
        if update_data.branding_json is not None:
            microsite.branding_json = update_data.branding_json
        if update_data.meta_title is not None:
            microsite.meta_title = update_data.meta_title
        if update_data.meta_description is not None:
            microsite.meta_description = update_data.meta_description
        if update_data.og_image_url is not None:
            microsite.og_image_url = update_data.og_image_url
        if update_data.ga_tracking_id is not None:
            microsite.ga_tracking_id = update_data.ga_tracking_id
        if update_data.fb_pixel_id is not None:
            microsite.fb_pixel_id = update_data.fb_pixel_id
        if update_data.is_published is not None:
            microsite.is_published = update_data.is_published
            if update_data.is_published and not microsite.published_at:
                microsite.published_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(microsite)

        # Reload with relationships
        microsite = db.query(Microsite).filter(
            Microsite.id == microsite.id
        ).options(
            joinedload(Microsite.theme),
            joinedload(Microsite.profile)
        ).first()

        return MicrositeResponse(**microsite.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating microsite: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error updating microsite configuration")


@auth_router.put("/my-microsite/profile", response_model=Dict[str, Any])
async def update_my_microsite_profile(
    update_data: MicrositeProfileUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Update the current user's microsite profile.

    Creates microsite and profile if they don't exist.
    """
    try:
        from microsite_models import UserMicrosite as Microsite, MicrositeProfile

        # Get or create microsite
        microsite = db.query(Microsite).filter(
            Microsite.user_id == current_user.id
        ).first()

        if not microsite:
            microsite = Microsite(
                user_id=current_user.id,
                organization_id=current_user.organization_id
            )
            db.add(microsite)
            db.flush()  # Get the ID

        # Get or create profile
        profile = db.query(MicrositeProfile).filter(
            MicrositeProfile.microsite_id == microsite.id
        ).first()

        if not profile:
            profile = MicrositeProfile(microsite_id=microsite.id)
            db.add(profile)

        # Update fields
        update_dict = update_data.model_dump(exclude_unset=True)
        _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
        for field, value in update_dict.items():
            if hasattr(profile, field) and field not in _protected:
                setattr(profile, field, value)

        db.commit()
        db.refresh(profile)

        return profile.to_dict()

    except Exception as e:
        logger.error(f"Error updating microsite profile: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error updating profile")


# =============================================================================
# ASSET UPLOAD ENDPOINTS
# =============================================================================

class AssetUploadResponse(BaseModel):
    """Response for asset upload"""
    url: str
    asset_type: str
    file_name: str
    file_size: int


@auth_router.post("/my-microsite/assets/upload", response_model=AssetUploadResponse)
async def upload_microsite_asset(
    file: bytes = None,
    asset_type: str = "image",
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Upload an image asset (logo or headshot) for the user's microsite.
    """
    from fastapi import UploadFile, File, Form
    import os
    import base64

    # This endpoint needs to be reimplemented with proper file handling
    # For now, return a placeholder response
    raise HTTPException(
        status_code=501,
        detail="Asset upload endpoint not yet implemented. Please use the profile update endpoint with base64 encoded images."
    )


@auth_router.post("/my-microsite/upload-image")
async def upload_microsite_image(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Upload an image for the user's microsite (logo or headshot).
    Accepts multipart/form-data with 'file' and 'asset_type' fields.
    """
    import os
    import base64

    try:
        from microsite_models import UserMicrosite as Microsite

        # Parse the multipart form data
        form = await request.form()
        file = form.get('file')
        asset_type = form.get('asset_type', 'image')

        if not file:
            raise HTTPException(status_code=400, detail="No file provided")

        # Read file content
        file_content = await file.read()

        # Validate file size (max 5MB)
        if len(file_content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size must be less than 5MB")

        # Validate file type
        content_type = file.content_type or ''
        if not content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")

        # Get or create microsite
        microsite = db.query(Microsite).filter(
            Microsite.user_id == current_user.id
        ).first()

        if not microsite:
            raise HTTPException(status_code=404, detail="No microsite found for this user")

        # Convert to base64 for storage
        file_base64 = base64.b64encode(file_content).decode('utf-8')
        data_url = f"data:{content_type};base64,{file_base64}"

        # Update the appropriate field based on asset_type
        branding = microsite.branding_json or {}

        if asset_type == 'logo':
            branding['logoUrl'] = data_url
        elif asset_type == 'headshot':
            branding['heroImageUrl'] = data_url
        else:
            branding[f'{asset_type}Url'] = data_url

        microsite.branding_json = branding
        db.commit()

        return {
            "url": data_url,
            "asset_type": asset_type,
            "file_name": file.filename,
            "file_size": len(file_content),
            "message": f"{asset_type.capitalize()} uploaded successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading asset: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error uploading file")


@auth_router.post("/my-microsite/publish")
async def publish_microsite(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Publish the current user's microsite.
    """
    try:
        from microsite_models import UserMicrosite as Microsite

        microsite = db.query(Microsite).filter(
            Microsite.user_id == current_user.id
        ).first()

        if not microsite:
            raise HTTPException(status_code=404, detail="No microsite configured")

        if not microsite.theme_id:
            raise HTTPException(status_code=400, detail="Please select a theme before publishing")

        microsite.is_published = True
        microsite.published_at = datetime.now(timezone.utc)

        db.commit()

        return {"success": True, "message": "Microsite published successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error publishing microsite: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error publishing microsite")


@auth_router.post("/my-microsite/unpublish")
async def unpublish_microsite(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Unpublish the current user's microsite.
    """
    try:
        from microsite_models import UserMicrosite as Microsite

        microsite = db.query(Microsite).filter(
            Microsite.user_id == current_user.id
        ).first()

        if not microsite:
            raise HTTPException(status_code=404, detail="No microsite configured")

        microsite.is_published = False

        db.commit()

        return {"success": True, "message": "Microsite unpublished"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unpublishing microsite: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error unpublishing microsite")


@auth_router.get("/preview-url")
async def get_microsite_preview_url(
    current_user = Depends(get_current_user)
):
    """
    Get the preview URL for the current user's microsite.
    """
    slug = current_user.slug or str(current_user.id)
    return {
        "previewUrl": f"/lo/{slug}",
        "slug": slug
    }


# =============================================================================
# MICROSITE PAGES ROUTES
# =============================================================================

class PageContentCreate(BaseModel):
    """Create a new page"""
    page_type: str = Field(..., description="Type of page: about, services, testimonials, blog, custom")
    slug: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    content: Optional[Dict[str, Any]] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    is_enabled: bool = True
    display_order: Optional[int] = 0
    show_in_nav: bool = True


class PageContentUpdate(BaseModel):
    """Update an existing page"""
    title: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    is_enabled: Optional[bool] = None
    display_order: Optional[int] = None
    show_in_nav: Optional[bool] = None


class PageContentResponse(BaseModel):
    """Response model for page content"""
    id: int
    micrositeId: int
    pageType: str
    slug: str
    title: str
    content: Dict[str, Any] = {}
    metaTitle: Optional[str] = None
    metaDescription: Optional[str] = None
    isEnabled: bool = True
    displayOrder: int = 0
    showInNav: bool = True
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None

    class Config:
        from_attributes = True


# Default page templates with suggested content structures
DEFAULT_PAGE_TEMPLATES = {
    "about": {
        "title": "About Me",
        "content": {
            "sections": [
                {
                    "type": "bio",
                    "heading": "About Me",
                    "text": "",
                    "image": ""
                },
                {
                    "type": "experience",
                    "heading": "My Experience",
                    "yearsExperience": None,
                    "loansFunded": None,
                    "volumeFunded": None
                },
                {
                    "type": "certifications",
                    "heading": "Certifications & Credentials",
                    "items": []
                }
            ]
        }
    },
    "services": {
        "title": "Loan Programs",
        "content": {
            "heading": "Loan Programs I Offer",
            "description": "Find the right mortgage solution for your needs",
            "programs": [
                {
                    "name": "Conventional Loans",
                    "description": "Traditional financing with competitive rates",
                    "icon": "home"
                },
                {
                    "name": "FHA Loans",
                    "description": "Low down payment options for first-time buyers",
                    "icon": "key"
                },
                {
                    "name": "VA Loans",
                    "description": "Special financing for veterans and service members",
                    "icon": "star"
                },
                {
                    "name": "Jumbo Loans",
                    "description": "Financing for high-value properties",
                    "icon": "building"
                }
            ]
        }
    },
    "testimonials": {
        "title": "Client Reviews",
        "content": {
            "heading": "What My Clients Say",
            "description": "Real stories from satisfied homeowners",
            "testimonials": []
        }
    },
    "blog": {
        "title": "Blog",
        "content": {
            "heading": "Latest Insights",
            "description": "Tips, news, and updates from the mortgage world",
            "posts": []
        }
    }
}


@auth_router.get("/my-microsite/pages", response_model=List[PageContentResponse])
async def get_my_pages(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get all pages for the current user's microsite.
    """
    try:
        from microsite_models import UserMicrosite as Microsite, MicrositeContentPage

        microsite = db.query(Microsite).filter(
            Microsite.user_id == current_user.id
        ).first()

        if not microsite:
            return []

        pages = db.query(MicrositeContentPage).filter(
            MicrositeContentPage.microsite_id == microsite.id
        ).order_by(MicrositeContentPage.display_order).all()

        return [PageContentResponse(**page.to_dict()) for page in pages]

    except Exception as e:
        logger.error(f"Error fetching pages: {e}")
        raise HTTPException(status_code=500, detail="Error loading pages")


@auth_router.get("/my-microsite/pages/{page_slug}", response_model=PageContentResponse)
async def get_page_by_slug(
    page_slug: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get a specific page by slug.
    """
    try:
        from microsite_models import UserMicrosite as Microsite, MicrositeContentPage

        microsite = db.query(Microsite).filter(
            Microsite.user_id == current_user.id
        ).first()

        if not microsite:
            raise HTTPException(status_code=404, detail="Microsite not found")

        page = db.query(MicrositeContentPage).filter(
            MicrositeContentPage.microsite_id == microsite.id,
            MicrositeContentPage.slug == page_slug
        ).first()

        if not page:
            raise HTTPException(status_code=404, detail="Page not found")

        return PageContentResponse(**page.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching page: {e}")
        raise HTTPException(status_code=500, detail="Error loading page")


@auth_router.post("/my-microsite/pages", response_model=PageContentResponse, status_code=201)
async def create_page(
    page_data: PageContentCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Create a new page for the user's microsite.
    """
    try:
        from microsite_models import UserMicrosite as Microsite, MicrositeContentPage, PageType

        # Get or create microsite
        microsite = db.query(Microsite).filter(
            Microsite.user_id == current_user.id
        ).first()

        if not microsite:
            microsite = Microsite(
                user_id=current_user.id,
                organization_id=current_user.organization_id
            )
            db.add(microsite)
            db.flush()

        # Check if slug already exists
        existing = db.query(MicrositeContentPage).filter(
            MicrositeContentPage.microsite_id == microsite.id,
            MicrositeContentPage.slug == page_data.slug
        ).first()

        if existing:
            raise HTTPException(status_code=400, detail="A page with this slug already exists")

        # Get page type enum
        try:
            page_type = PageType(page_data.page_type.lower())
        except ValueError:
            page_type = PageType.CUSTOM

        # Use template content if not provided
        content = page_data.content
        if not content and page_data.page_type.lower() in DEFAULT_PAGE_TEMPLATES:
            content = DEFAULT_PAGE_TEMPLATES[page_data.page_type.lower()]["content"]

        # Create page
        page = MicrositeContentPage(
            microsite_id=microsite.id,
            page_type=page_type,
            slug=page_data.slug,
            title=page_data.title,
            content=content or {},
            meta_title=page_data.meta_title,
            meta_description=page_data.meta_description,
            is_enabled=page_data.is_enabled,
            display_order=page_data.display_order or 0,
            show_in_nav=page_data.show_in_nav
        )

        db.add(page)
        db.commit()
        db.refresh(page)

        return PageContentResponse(**page.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating page: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error creating page")


@auth_router.put("/my-microsite/pages/{page_slug}", response_model=PageContentResponse)
async def update_page(
    page_slug: str,
    page_data: PageContentUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Update an existing page.
    """
    try:
        from microsite_models import UserMicrosite as Microsite, MicrositeContentPage

        microsite = db.query(Microsite).filter(
            Microsite.user_id == current_user.id
        ).first()

        if not microsite:
            raise HTTPException(status_code=404, detail="Microsite not found")

        page = db.query(MicrositeContentPage).filter(
            MicrositeContentPage.microsite_id == microsite.id,
            MicrositeContentPage.slug == page_slug
        ).first()

        if not page:
            raise HTTPException(status_code=404, detail="Page not found")

        # Update fields
        if page_data.title is not None:
            page.title = page_data.title
        if page_data.content is not None:
            page.content = page_data.content
        if page_data.meta_title is not None:
            page.meta_title = page_data.meta_title
        if page_data.meta_description is not None:
            page.meta_description = page_data.meta_description
        if page_data.is_enabled is not None:
            page.is_enabled = page_data.is_enabled
        if page_data.display_order is not None:
            page.display_order = page_data.display_order
        if page_data.show_in_nav is not None:
            page.show_in_nav = page_data.show_in_nav

        db.commit()
        db.refresh(page)

        return PageContentResponse(**page.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating page: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error updating page")


@auth_router.delete("/my-microsite/pages/{page_slug}")
async def delete_page(
    page_slug: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Delete a page from the microsite.
    """
    try:
        from microsite_models import UserMicrosite as Microsite, MicrositeContentPage

        microsite = db.query(Microsite).filter(
            Microsite.user_id == current_user.id
        ).first()

        if not microsite:
            raise HTTPException(status_code=404, detail="Microsite not found")

        page = db.query(MicrositeContentPage).filter(
            MicrositeContentPage.microsite_id == microsite.id,
            MicrositeContentPage.slug == page_slug
        ).first()

        if not page:
            raise HTTPException(status_code=404, detail="Page not found")

        db.delete(page)
        db.commit()

        return {"success": True, "message": f"Page '{page_slug}' deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting page: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error deleting page")


@auth_router.post("/my-microsite/pages/reorder")
async def reorder_pages(
    page_order: List[Dict[str, Any]],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Reorder pages by updating display_order.

    Expects: [{"slug": "about", "display_order": 0}, {"slug": "services", "display_order": 1}, ...]
    """
    try:
        from microsite_models import UserMicrosite as Microsite, MicrositeContentPage

        microsite = db.query(Microsite).filter(
            Microsite.user_id == current_user.id
        ).first()

        if not microsite:
            raise HTTPException(status_code=404, detail="Microsite not found")

        for item in page_order:
            page = db.query(MicrositeContentPage).filter(
                MicrositeContentPage.microsite_id == microsite.id,
                MicrositeContentPage.slug == item.get("slug")
            ).first()

            if page:
                page.display_order = item.get("display_order", 0)

        db.commit()

        return {"success": True, "message": "Pages reordered"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reordering pages: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error reordering pages")


@auth_router.get("/my-microsite/page-templates")
async def get_page_templates():
    """
    Get available page templates with default content structures.
    """
    return {
        "templates": [
            {
                "type": "about",
                "name": "About Me / Bio",
                "description": "Showcase your background, experience, and credentials",
                "defaultContent": DEFAULT_PAGE_TEMPLATES["about"]
            },
            {
                "type": "services",
                "name": "Services / Loan Programs",
                "description": "Highlight the loan programs and services you offer",
                "defaultContent": DEFAULT_PAGE_TEMPLATES["services"]
            },
            {
                "type": "testimonials",
                "name": "Testimonials / Reviews",
                "description": "Display client reviews and success stories",
                "defaultContent": DEFAULT_PAGE_TEMPLATES["testimonials"]
            },
            {
                "type": "blog",
                "name": "Blog",
                "description": "Share articles, tips, and market updates",
                "defaultContent": DEFAULT_PAGE_TEMPLATES["blog"]
            }
        ]
    }


# =============================================================================
# PUBLIC PAGES ROUTE
# =============================================================================

@public_router.get("/render/{user_slug}/pages")
async def get_public_microsite_pages(
    user_slug: str,
    db: Session = Depends(get_db)
):
    """
    Get all enabled pages for a public microsite.
    """
    try:
        from database.models import User
        from microsite_models import UserMicrosite as Microsite, MicrositeContentPage

        # Find user by slug
        user = db.query(User).filter(
            User.slug == user_slug,
            User.is_active == True
        ).first()

        if not user:
            try:
                user_id = int(user_slug)
                user = db.query(User).filter(
                    User.id == user_id,
                    User.is_active == True
                ).first()
            except ValueError:
                pass

        if not user:
            raise HTTPException(status_code=404, detail="Loan officer not found")

        # Get microsite
        microsite = db.query(Microsite).filter(
            Microsite.user_id == user.id
        ).first()

        if not microsite:
            return {"pages": [], "navigation": []}

        # Get enabled pages
        pages = db.query(MicrositeContentPage).filter(
            MicrositeContentPage.microsite_id == microsite.id,
            MicrositeContentPage.is_enabled == True
        ).order_by(MicrositeContentPage.display_order).all()

        # Build navigation
        navigation = [
            {
                "slug": page.slug,
                "title": page.title,
                "showInNav": page.show_in_nav
            }
            for page in pages if page.show_in_nav
        ]

        return {
            "pages": [page.to_dict() for page in pages],
            "navigation": navigation
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching public pages: {e}")
        raise HTTPException(status_code=500, detail="Error loading pages")


@public_router.get("/render/{user_slug}/pages/{page_slug}")
async def get_public_page(
    user_slug: str,
    page_slug: str,
    db: Session = Depends(get_db)
):
    """
    Get a specific public page by slug.
    """
    try:
        from database.models import User
        from microsite_models import UserMicrosite as Microsite, MicrositeContentPage

        # Find user by slug
        user = db.query(User).filter(
            User.slug == user_slug,
            User.is_active == True
        ).first()

        if not user:
            try:
                user_id = int(user_slug)
                user = db.query(User).filter(
                    User.id == user_id,
                    User.is_active == True
                ).first()
            except ValueError:
                pass

        if not user:
            raise HTTPException(status_code=404, detail="Loan officer not found")

        # Get microsite
        microsite = db.query(Microsite).filter(
            Microsite.user_id == user.id
        ).first()

        if not microsite:
            raise HTTPException(status_code=404, detail="Page not found")

        # Get page
        page = db.query(MicrositeContentPage).filter(
            MicrositeContentPage.microsite_id == microsite.id,
            MicrositeContentPage.slug == page_slug,
            MicrositeContentPage.is_enabled == True
        ).first()

        if not page:
            raise HTTPException(status_code=404, detail="Page not found")

        return page.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching public page: {e}")
        raise HTTPException(status_code=500, detail="Error loading page")


# =============================================================================
# PUBLIC AI CHAT ROUTES
# =============================================================================

class ChatMessageRequest(BaseModel):
    """Request model for chat messages"""
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None


class BookAppointmentRequest(BaseModel):
    """Request model for booking appointments"""
    contact_name: str = Field(..., min_length=1, max_length=200)
    contact_email: str = Field(..., min_length=1)
    contact_phone: Optional[str] = None
    appointment_date: str  # YYYY-MM-DD
    appointment_time: str  # HH:MM
    appointment_type: str = "consultation"
    notes: Optional[str] = None


class CancelAppointmentRequest(BaseModel):
    """Request model for cancelling appointments"""
    appointment_id: str = Field(..., description="The appointment ID (APPT-XXXXXXXX format)")
    contact_email: str = Field(..., description="Email used when booking (for verification)")
    reason: Optional[str] = Field(None, max_length=500, description="Reason for cancellation")


class RescheduleAppointmentRequest(BaseModel):
    """Request model for rescheduling appointments"""
    appointment_id: str = Field(..., description="The appointment ID (APPT-XXXXXXXX format)")
    contact_email: str = Field(..., description="Email used when booking (for verification)")
    new_date: str = Field(..., description="New appointment date (YYYY-MM-DD)")
    new_time: str = Field(..., description="New appointment time (HH:MM)")
    reason: Optional[str] = Field(None, max_length=500, description="Reason for rescheduling")


@public_router.post("/chat/{user_slug}/message")
async def chat_with_mortgage_assistant(
    user_slug: str,
    request: ChatMessageRequest,
    db: Session = Depends(get_db)
):
    """
    Send a message to the AI mortgage assistant.
    No authentication required - public facing for microsite visitors.
    """
    try:
        from services.public_mortgage_chat_service import get_public_chat_service

        chat_service = get_public_chat_service(db, user_slug)

        result = chat_service.generate_response(
            user_message=request.message,
            conversation_history=request.conversation_history
        )

        return {
            "success": True,
            "response": result.get("response"),
            "loan_officer": result.get("loan_officer"),
            "scheduling_intent": result.get("scheduling_intent", False),
            "available_slots": result.get("available_slots"),
            "session_id": request.session_id or str(uuid.uuid4())
        }

    except Exception as e:
        logger.error(f"Error in chat: {e}")
        return {
            "success": False,
            "response": "I'm sorry, I'm having trouble processing your request. Please try again.",
            "error": "Internal server error"
        }


@public_router.get("/chat/{user_slug}/availability")
async def get_loan_officer_availability(
    user_slug: str,
    days_ahead: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db)
):
    """
    Get available appointment slots for a loan officer.
    """
    try:
        from services.public_mortgage_chat_service import get_public_chat_service

        chat_service = get_public_chat_service(db, user_slug)
        slots = chat_service.get_available_slots(days_ahead=days_ahead)

        return {
            "success": True,
            "loan_officer": chat_service.lo_info.get("name") if chat_service.lo_info else None,
            "slots": slots,
            "total_available": len(slots)
        }

    except Exception as e:
        logger.error(f"Error getting availability: {e}")
        return {
            "success": False,
            "slots": [],
            "error": "Internal server error"
        }


@public_router.post("/chat/{user_slug}/book")
async def book_appointment_via_chat(
    user_slug: str,
    request: BookAppointmentRequest,
    db: Session = Depends(get_db)
):
    """
    Book an appointment with the loan officer.
    """
    try:
        from services.public_mortgage_chat_service import get_public_chat_service
        from datetime import datetime

        chat_service = get_public_chat_service(db, user_slug)

        # Parse appointment datetime
        appointment_datetime = datetime.strptime(
            f"{request.appointment_date} {request.appointment_time}",
            "%Y-%m-%d %H:%M"
        )

        result = chat_service.book_appointment(
            contact_name=request.contact_name,
            contact_email=request.contact_email,
            contact_phone=request.contact_phone,
            appointment_time=appointment_datetime,
            appointment_type=request.appointment_type,
            notes=request.notes
        )

        # Send SMS confirmation if booking was successful
        if result.get("success") and request.contact_phone:
            try:
                from services.notification_service import NotificationService
                notification_service = NotificationService()

                lo_name = chat_service.lo_info.get("name", "Your Loan Officer") if chat_service.lo_info else "Your Loan Officer"
                appointment_time_formatted = appointment_datetime.strftime("%B %d, %Y at %I:%M %p")
                appointment_id = result.get("appointment_id", "")

                # SMS to the client
                sms_message = f"Appointment confirmed with {lo_name} on {appointment_time_formatted}. Appointment ID: {appointment_id}. Reply HELP for assistance."

                sms_result = notification_service.send_sms(
                    to_phone=request.contact_phone,
                    message=sms_message
                )
                if sms_result.get("success"):
                    logger.info(f"Sent booking confirmation SMS to {request.contact_phone}")
                else:
                    logger.warning(f"Failed to send booking SMS: {sms_result.get('error')}")

                # SMS to the loan officer
                lo_phone = chat_service.lo_info.get("phone") if chat_service.lo_info else None
                if lo_phone:
                    lo_sms = f"New appointment: {request.contact_name} booked for {appointment_time_formatted}. Phone: {request.contact_phone}"

                    sms_result = notification_service.send_sms(
                        to_phone=lo_phone,
                        message=lo_sms
                    )
                    if sms_result.get("success"):
                        logger.info(f"Sent new booking SMS to LO {lo_phone}")

            except Exception as sms_error:
                logger.warning(f"Failed to send booking SMS notifications: {sms_error}")

        return result

    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return {
            "success": False,
            "error": "Invalid date or time format"
        }
    except Exception as e:
        logger.error(f"Error booking appointment: {e}")
        return {
            "success": False,
            "error": "Internal server error"
        }


@public_router.post("/chat/{user_slug}/cancel")
async def cancel_appointment_via_chat(
    user_slug: str,
    request: CancelAppointmentRequest,
    db: Session = Depends(get_db)
):
    """
    Cancel an appointment booked via the chat widget.
    Requires the appointment ID and the email used when booking for verification.
    """
    try:
        from services.smart_scheduler_service import ScheduledAppointment, AppointmentStatus
        from database.models import User
        from datetime import datetime

        # Resolve user_slug to org_id for tenant isolation
        slug_user = db.query(User).filter(User.slug == user_slug, User.is_active == True).first()
        if not slug_user:
            try:
                slug_user = db.query(User).filter(User.id == int(user_slug), User.is_active == True).first()
            except ValueError:
                pass
        cancel_org_id = getattr(slug_user, 'organization_id', None) if slug_user else None

        # Find the appointment by appointment_id, scoped to org
        cancel_query = db.query(ScheduledAppointment).filter(
            ScheduledAppointment.appointment_id == request.appointment_id
        )
        if cancel_org_id:
            cancel_query = cancel_query.filter(ScheduledAppointment.organization_id == cancel_org_id)
        appointment = cancel_query.first()

        if not appointment:
            return {
                "success": False,
                "error": "Appointment not found. Please check the appointment ID."
            }

        # Verify email matches (case-insensitive)
        if appointment.contact_email.lower() != request.contact_email.lower():
            logger.warning(f"Email mismatch for appointment {request.appointment_id}: "
                          f"provided {request.contact_email}, expected {appointment.contact_email}")
            return {
                "success": False,
                "error": "Email does not match the booking. Please use the email you provided when scheduling."
            }

        # Check if already cancelled
        if appointment.status == AppointmentStatus.CANCELLED.value:
            return {
                "success": False,
                "error": "This appointment has already been cancelled."
            }

        # Check if appointment is in the past
        if appointment.start_time < datetime.utcnow():
            return {
                "success": False,
                "error": "Cannot cancel past appointments."
            }

        # Cancel the appointment
        appointment.status = AppointmentStatus.CANCELLED.value
        appointment.cancelled_at = datetime.utcnow()
        if request.reason:
            appointment.internal_notes = f"Cancelled by user: {request.reason}"
        else:
            appointment.internal_notes = "Cancelled by user via chat widget"

        db.commit()

        cancelled_time = appointment.start_time.strftime("%B %d, %Y at %I:%M %p")
        lo_name = appointment.lo_name or "Your Loan Officer"

        # Send cancellation email notifications
        try:
            from services.notification_service import NotificationService
            notification_service = NotificationService()

            # Email to the client
            if appointment.contact_email:
                notification_service.send_email(
                    to_email=appointment.contact_email,
                    subject=f"Appointment Cancelled - {cancelled_time}",
                    html_content=f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #dc2626;">Appointment Cancelled</h2>
                        <p>Hi {appointment.contact_name},</p>
                        <p>Your appointment has been cancelled as requested:</p>

                        <div style="background: #fef2f2; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #dc2626;">
                            <p style="margin: 0;"><strong>Original Date & Time:</strong> {cancelled_time}</p>
                            <p style="margin: 10px 0 0 0;"><strong>With:</strong> {lo_name}</p>
                            <p style="margin: 10px 0 0 0;"><strong>Status:</strong> Cancelled</p>
                            {f'<p style="margin: 10px 0 0 0;"><strong>Reason:</strong> {request.reason}</p>' if request.reason else ''}
                        </div>

                        <p>If you'd like to reschedule, please visit our website or reply to this email.</p>

                        <p style="color: #6b7280; font-size: 14px; margin-top: 30px;">
                            We hope to connect with you soon!
                        </p>
                    </div>
                    """
                )
                logger.info(f"Sent cancellation email to {appointment.contact_email}")

            # Email to the loan officer
            if appointment.lo_email:
                notification_service.send_email(
                    to_email=appointment.lo_email,
                    subject=f"Appointment Cancelled: {appointment.contact_name} - {cancelled_time}",
                    html_content=f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #dc2626;">Appointment Cancelled</h2>
                        <p>An appointment has been cancelled:</p>

                        <div style="background: #fef2f2; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #dc2626;">
                            <p style="margin: 0;"><strong>Contact:</strong> {appointment.contact_name}</p>
                            <p style="margin: 10px 0 0 0;"><strong>Email:</strong> {appointment.contact_email}</p>
                            <p style="margin: 10px 0 0 0;"><strong>Phone:</strong> {appointment.contact_phone or 'Not provided'}</p>
                            <p style="margin: 10px 0 0 0;"><strong>Original Time:</strong> {cancelled_time}</p>
                            {f'<p style="margin: 10px 0 0 0;"><strong>Reason:</strong> {request.reason}</p>' if request.reason else ''}
                        </div>

                        <p>This appointment was cancelled by the client via the chat widget.</p>
                    </div>
                    """
                )
                logger.info(f"Sent cancellation alert to {appointment.lo_email}")

            # SMS to the client
            if appointment.contact_phone:
                sms_message = f"Your appointment with {lo_name} on {cancelled_time} has been cancelled."
                if request.reason:
                    sms_message += f" Reason: {request.reason}"
                sms_message += " Reply to reschedule or visit our website."

                sms_result = notification_service.send_sms(
                    to_phone=appointment.contact_phone,
                    message=sms_message
                )
                if sms_result.get("success"):
                    logger.info(f"Sent cancellation SMS to {appointment.contact_phone}")
                else:
                    logger.warning(f"Failed to send cancellation SMS: {sms_result.get('error')}")

            # SMS to the loan officer
            if appointment.lo_phone:
                lo_sms = f"Appointment cancelled: {appointment.contact_name} ({cancelled_time})"
                if request.reason:
                    lo_sms += f" - {request.reason}"

                sms_result = notification_service.send_sms(
                    to_phone=appointment.lo_phone,
                    message=lo_sms
                )
                if sms_result.get("success"):
                    logger.info(f"Sent cancellation SMS to LO {appointment.lo_phone}")

        except Exception as notify_error:
            logger.warning(f"Failed to send cancellation notifications: {notify_error}")

        logger.info(f"Appointment {request.appointment_id} cancelled by {request.contact_email}")

        return {
            "success": True,
            "message": "Your appointment has been cancelled successfully.",
            "appointment_id": request.appointment_id,
            "cancelled_time": cancelled_time
        }

    except Exception as e:
        logger.error(f"Error cancelling appointment: {e}")
        return {
            "success": False,
            "error": "An error occurred while cancelling. Please try again or contact support."
        }


@public_router.post("/chat/{user_slug}/reschedule")
async def reschedule_appointment_via_chat(
    user_slug: str,
    request: RescheduleAppointmentRequest,
    db: Session = Depends(get_db)
):
    """
    Reschedule an appointment booked via the chat widget.
    Requires the appointment ID and the email used when booking for verification.
    Atomically updates the appointment to the new time if the slot is available.
    """
    try:
        from services.smart_scheduler_service import ScheduledAppointment, AppointmentStatus
        from database.models import User
        from datetime import datetime, timedelta

        # Resolve user_slug to org_id for tenant isolation
        slug_user = db.query(User).filter(User.slug == user_slug, User.is_active == True).first()
        if not slug_user:
            try:
                slug_user = db.query(User).filter(User.id == int(user_slug), User.is_active == True).first()
            except ValueError:
                pass
        resched_org_id = getattr(slug_user, 'organization_id', None) if slug_user else None

        # Find the appointment by appointment_id, scoped to org
        resched_query = db.query(ScheduledAppointment).filter(
            ScheduledAppointment.appointment_id == request.appointment_id
        )
        if resched_org_id:
            resched_query = resched_query.filter(ScheduledAppointment.organization_id == resched_org_id)
        appointment = resched_query.first()

        if not appointment:
            return {
                "success": False,
                "error": "Appointment not found. Please check the appointment ID."
            }

        # Verify email matches (case-insensitive)
        if appointment.contact_email.lower() != request.contact_email.lower():
            logger.warning(f"Email mismatch for reschedule {request.appointment_id}")
            return {
                "success": False,
                "error": "Email does not match the booking. Please use the email you provided when scheduling."
            }

        # Check if already cancelled
        if appointment.status == AppointmentStatus.CANCELLED.value:
            return {
                "success": False,
                "error": "Cannot reschedule a cancelled appointment. Please book a new appointment."
            }

        # Check if original appointment is in the past
        if appointment.start_time < datetime.utcnow():
            return {
                "success": False,
                "error": "Cannot reschedule past appointments."
            }

        # Parse new datetime
        try:
            new_start_time = datetime.strptime(
                f"{request.new_date} {request.new_time}",
                "%Y-%m-%d %H:%M"
            )
        except ValueError:
            return {
                "success": False,
                "error": "Invalid date or time format. Use YYYY-MM-DD for date and HH:MM for time."
            }

        # Check new time is in the future
        if new_start_time < datetime.utcnow():
            return {
                "success": False,
                "error": "Cannot reschedule to a past time."
            }

        # Calculate new end time based on original duration
        duration = appointment.duration_minutes or 30
        new_end_time = new_start_time + timedelta(minutes=duration)

        # Check for conflicts with OTHER appointments (exclude current appointment)
        # Include organization_id filter for tenant isolation
        conflict_filters = [
            ScheduledAppointment.loan_officer_id == appointment.loan_officer_id,
            ScheduledAppointment.id != appointment.id,  # Exclude current appointment
            ScheduledAppointment.status.in_([
                AppointmentStatus.SCHEDULED.value,
                AppointmentStatus.CONFIRMED.value
            ]),
            ScheduledAppointment.start_time < new_end_time,
            ScheduledAppointment.end_time > new_start_time,
        ]
        if appointment.organization_id:
            conflict_filters.append(
                ScheduledAppointment.organization_id == appointment.organization_id
            )
        conflicting = db.query(ScheduledAppointment).filter(
            *conflict_filters
        ).first()

        if conflicting:
            return {
                "success": False,
                "error": "The new time slot is not available. Please select a different time.",
                "conflict": True
            }

        # Store old time for response
        old_time = appointment.start_time.strftime("%B %d, %Y at %I:%M %p")

        # Update the appointment
        appointment.start_time = new_start_time
        appointment.end_time = new_end_time

        # Add reschedule note
        reschedule_note = f"Rescheduled from {old_time}"
        if request.reason:
            reschedule_note += f" - Reason: {request.reason}"

        if appointment.internal_notes:
            appointment.internal_notes += f"\n{reschedule_note}"
        else:
            appointment.internal_notes = reschedule_note

        db.commit()

        new_time_formatted = new_start_time.strftime("%B %d, %Y at %I:%M %p")
        lo_name = appointment.lo_name or "Your Loan Officer"

        # Send reschedule email notifications
        try:
            from services.notification_service import NotificationService
            notification_service = NotificationService()

            # Email to the client
            if appointment.contact_email:
                notification_service.send_email(
                    to_email=appointment.contact_email,
                    subject=f"Appointment Rescheduled - {new_time_formatted}",
                    html_content=f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #2563eb;">Appointment Rescheduled</h2>
                        <p>Hi {appointment.contact_name},</p>
                        <p>Your appointment has been rescheduled as requested:</p>

                        <div style="background: #eff6ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #2563eb;">
                            <p style="margin: 0; color: #6b7280; text-decoration: line-through;"><strong>Original Time:</strong> {old_time}</p>
                            <p style="margin: 10px 0 0 0;"><strong>New Date & Time:</strong> {new_time_formatted}</p>
                            <p style="margin: 10px 0 0 0;"><strong>With:</strong> {lo_name}</p>
                            <p style="margin: 10px 0 0 0;"><strong>Duration:</strong> {duration} minutes</p>
                            {f'<p style="margin: 10px 0 0 0;"><strong>Reason:</strong> {request.reason}</p>' if request.reason else ''}
                        </div>

                        <p>If you need to make any changes, please contact us or reply to this email.</p>

                        <p style="color: #6b7280; font-size: 14px; margin-top: 30px;">
                            We look forward to speaking with you!
                        </p>
                    </div>
                    """
                )
                logger.info(f"Sent reschedule confirmation email to {appointment.contact_email}")

            # Email to the loan officer
            if appointment.lo_email:
                notification_service.send_email(
                    to_email=appointment.lo_email,
                    subject=f"Appointment Rescheduled: {appointment.contact_name} - {new_time_formatted}",
                    html_content=f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #2563eb;">Appointment Rescheduled</h2>
                        <p>An appointment has been rescheduled:</p>

                        <div style="background: #eff6ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #2563eb;">
                            <p style="margin: 0;"><strong>Contact:</strong> {appointment.contact_name}</p>
                            <p style="margin: 10px 0 0 0;"><strong>Email:</strong> {appointment.contact_email}</p>
                            <p style="margin: 10px 0 0 0;"><strong>Phone:</strong> {appointment.contact_phone or 'Not provided'}</p>
                            <p style="margin: 10px 0 0 0; color: #6b7280; text-decoration: line-through;"><strong>Original Time:</strong> {old_time}</p>
                            <p style="margin: 10px 0 0 0;"><strong>New Time:</strong> {new_time_formatted}</p>
                            {f'<p style="margin: 10px 0 0 0;"><strong>Reason:</strong> {request.reason}</p>' if request.reason else ''}
                        </div>

                        <p>This appointment was rescheduled by the client via the chat widget.</p>
                    </div>
                    """
                )
                logger.info(f"Sent reschedule alert to {appointment.lo_email}")

            # SMS to the client
            if appointment.contact_phone:
                sms_message = f"Your appointment with {lo_name} has been rescheduled from {old_time} to {new_time_formatted}."

                sms_result = notification_service.send_sms(
                    to_phone=appointment.contact_phone,
                    message=sms_message
                )
                if sms_result.get("success"):
                    logger.info(f"Sent reschedule SMS to {appointment.contact_phone}")
                else:
                    logger.warning(f"Failed to send reschedule SMS: {sms_result.get('error')}")

            # SMS to the loan officer
            if appointment.lo_phone:
                lo_sms = f"Appointment rescheduled: {appointment.contact_name} moved from {old_time} to {new_time_formatted}"

                sms_result = notification_service.send_sms(
                    to_phone=appointment.lo_phone,
                    message=lo_sms
                )
                if sms_result.get("success"):
                    logger.info(f"Sent reschedule SMS to LO {appointment.lo_phone}")

        except Exception as notify_error:
            logger.warning(f"Failed to send reschedule notifications: {notify_error}")

        logger.info(f"Appointment {request.appointment_id} rescheduled from {old_time} to {new_start_time}")

        return {
            "success": True,
            "message": "Your appointment has been rescheduled successfully.",
            "appointment_id": request.appointment_id,
            "old_time": old_time,
            "new_time": new_start_time.strftime("%B %d, %Y at %I:%M %p"),
            "appointment": {
                "start_time": new_start_time.isoformat(),
                "end_time": new_end_time.isoformat(),
                "duration_minutes": duration
            }
        }

    except Exception as e:
        logger.error(f"Error rescheduling appointment: {e}")
        return {
            "success": False,
            "error": "An error occurred while rescheduling. Please try again or contact support."
        }


@public_router.get("/chat/{user_slug}/info")
async def get_loan_officer_chat_info(
    user_slug: str,
    db: Session = Depends(get_db)
):
    """
    Get loan officer information for chat widget initialization.
    """
    try:
        from services.public_mortgage_chat_service import get_public_chat_service

        chat_service = get_public_chat_service(db, user_slug)

        if not chat_service.lo_info:
            raise HTTPException(status_code=404, detail="Loan officer not found")

        return {
            "success": True,
            "loan_officer": {
                "name": chat_service.lo_info.get("name"),
                "bio": chat_service.lo_info.get("bio"),
                "company": chat_service.lo_info.get("company"),
                "photo_url": None  # Can be added if available
            },
            "chat_enabled": True,
            "greeting": f"Hi! I'm an AI assistant for {chat_service.lo_info.get('name')}. I can answer your mortgage questions and help schedule a consultation. How can I help you today?"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat info: {e}")
        raise HTTPException(status_code=500, detail="Error loading chat")
