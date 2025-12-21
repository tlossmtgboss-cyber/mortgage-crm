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
        from main import User
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
            theme_config = microsite.theme_config or {}
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
        raise HTTPException(status_code=500, detail=f"Error loading microsite: {str(e)}")


# =============================================================================
# ONE-TIME SETUP ENDPOINT (can be removed after setup)
# =============================================================================

@public_router.post("/setup-tim-loss")
async def setup_tim_loss_microsite(db: Session = Depends(get_db)):
    """One-time setup endpoint for tim-loss microsite with bio and theme colors."""
    try:
        from main import User
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
        raise HTTPException(status_code=500, detail=str(e))


@public_router.post("/add-about-page/{user_slug}")
async def add_about_page_for_user(user_slug: str, db: Session = Depends(get_db)):
    """One-time endpoint to add an About page for a user's microsite."""
    try:
        from main import User
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
        content = {
            "headline": f"About {user.name}",
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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=f"Error creating page: {str(e)}")


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
        from main import User
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
        from main import User
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
