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

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)

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
    from main import get_current_user_flexible
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
    """
    from microsite_models import MicrositeTheme, ThemeStatus, ThemeCategory

    default_themes = [
        {
            "slug": "leadpops-cardinal",
            "name": "LeadPops Cardinal",
            "description": "A bold, modern theme inspired by LeadPops with strong call-to-actions and lead capture focus.",
            "category": ThemeCategory.BOLD,
            "component_name": "LeadPopsCardinal",
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
                category=theme_data["category"].value,  # Use lowercase string value
                status='active',  # Use lowercase string value for PostgreSQL enum
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

        # Check if any themes exist, seed defaults if not
        theme_count = db.query(MicrositeTheme).count()
        if theme_count == 0:
            logger.info("No themes found, seeding defaults...")
            seed_default_themes(db)

        # Use string value for enum comparison (PostgreSQL enums are lowercase)
        query = db.query(MicrositeTheme).filter(
            MicrositeTheme.status == 'active'
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

        # Get featured themes separately
        featured_query = db.query(MicrositeTheme).filter(
            MicrositeTheme.status == 'active',
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
        raise HTTPException(status_code=500, detail=f"Error loading themes: {str(e)}")


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

        theme = db.query(MicrositeTheme).filter(
            MicrositeTheme.slug == theme_slug,
            MicrositeTheme.status == 'active'  # Use lowercase for PostgreSQL enum
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
        from main import User
        from microsite_models import Microsite, MicrositeTheme, MicrositeProfile

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
                MicrositeTheme.slug == "leadpops-cardinal"
            ).first()

            if not default_theme:
                # Fallback to any active theme
                default_theme = db.query(MicrositeTheme).filter(
                    MicrositeTheme.status == 'active'
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
            theme_config = microsite.theme_config or {}
            profile_data = microsite.profile.to_dict() if microsite.profile else {}

        # Build user data (public fields only)
        user_data = {
            "id": user.id,
            "name": user.full_name or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
            "email": user.email,
            "phone": user.phone,
            "nmls_id": user.nmls_number,
            "slug": user.slug,
            "company": getattr(user, 'company', None),
            "bio": getattr(user, 'bio', None),
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
        logger.error(f"Error fetching public microsite: {e}")
        raise HTTPException(status_code=500, detail="Error loading microsite")


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
        from microsite_models import Microsite

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
        from microsite_models import Microsite, MicrositeTheme

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
        from microsite_models import Microsite, MicrositeProfile

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
        for field, value in update_dict.items():
            if hasattr(profile, field):
                setattr(profile, field, value)

        db.commit()
        db.refresh(profile)

        return profile.to_dict()

    except Exception as e:
        logger.error(f"Error updating microsite profile: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error updating profile")


@auth_router.post("/my-microsite/publish")
async def publish_microsite(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Publish the current user's microsite.
    """
    try:
        from microsite_models import Microsite

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
        from microsite_models import Microsite

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
