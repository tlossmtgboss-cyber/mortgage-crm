"""
App Branding Routes

Provides the per-organization branding configuration to the main React app.
The frontend BrandingProvider fetches this once on login and applies CSS
custom properties, updates the favicon, and replaces hardcoded brand text.

Endpoint (registered via register_branding_routes):
  GET /api/v1/branding  — Returns org's WhiteLabelConfig or sensible defaults
"""

import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Default branding — returned when no WhiteLabelConfig exists for the org
_DEFAULTS = {
    "company_name": "The Tim Loss Team",
    "logo_url": None,
    "favicon_url": None,
    "primary_color": "#218d8d",
    "secondary_color": "#7c3aed",
    "accent_color": "#059669",
    "header_bg_color": "#ffffff",
    "font_family": "Inter, sans-serif",
}


def register_branding_routes(app, get_db_func, get_current_user_flexible):
    """Register branding routes with the FastAPI app.

    Called from main.py during startup. Receives auth/db dependencies as
    arguments so we never import from main at module load time (avoids
    circular imports).

    Endpoint:
      GET /api/v1/branding
        - Requires JWT auth via get_current_user_flexible
        - Returns org's WhiteLabelConfig or _DEFAULTS if none found
        - Catches all exceptions (including missing table) and returns defaults
    """
    from fastapi import Depends

    @app.get("/api/v1/branding", tags=["App Branding"])
    async def get_app_branding(
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_flexible),
    ):
        """Return the authenticated user's org branding config.

        Returns WhiteLabelConfig if one exists for the org (is_active=True),
        otherwise returns Perennia AI defaults so the app renders correctly
        for all orgs, including those without a white-label config.
        """
        organization_id = getattr(current_user, "organization_id", None)

        if organization_id is None:
            return _DEFAULTS.copy()

        try:
            from database.models.white_label_config import WhiteLabelConfig

            config = (
                db.query(WhiteLabelConfig)
                .filter(
                    WhiteLabelConfig.organization_id == organization_id,
                    WhiteLabelConfig.is_active == True,
                )
                .first()
            )

            if config is None:
                return _DEFAULTS.copy()

            return {
                "company_name": config.company_name or _DEFAULTS["company_name"],
                "logo_url": config.logo_url,
                "favicon_url": config.favicon_url,
                "primary_color": config.primary_color or _DEFAULTS["primary_color"],
                "secondary_color": config.secondary_color or _DEFAULTS["secondary_color"],
                "accent_color": config.accent_color or _DEFAULTS["accent_color"],
                "header_bg_color": config.header_bg_color or _DEFAULTS["header_bg_color"],
                "font_family": config.font_family or _DEFAULTS["font_family"],
            }

        except Exception as e:
            # Table may not exist yet in some environments — return defaults
            logger.warning(
                "Could not fetch WhiteLabelConfig for org %s: %s",
                organization_id,
                e,
            )
            return _DEFAULTS.copy()
