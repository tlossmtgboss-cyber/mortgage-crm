"""
Remote Configuration Routes
Mobile App — Dynamic Config Without Deploys

Provides GET and PUT endpoints for mobile app remote configuration.
Config is stored per-organization in the database, with a global fallback.

GET /api/v1/config/mobile  — No auth required (must work before login for
                             maintenance mode). Returns org-specific config
                             if a valid token is present, otherwise global.
PUT /api/v1/config/mobile  — Admin only. Updates config for the caller's org.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import logging
import json

logger = logging.getLogger(__name__)


# =============================================================================
# DEFAULT CONFIG — mirrors frontend DEFAULT_CONFIG as the server-side source of truth
# =============================================================================

DEFAULT_CONFIG: Dict[str, Any] = {
    "features": {
        "voiceAssistant": True,
        "documentScanner": True,
        "offlineMode": True,
        "biometricLogin": True,
        "pushNotifications": True,
        "rateLockAlerts": True,
        "darkMode": True,
    },
    "ui": {
        "mobileHomeScreen": "dashboard",
        "maxCacheSize": 10 * 1024 * 1024,  # 10 MB
        "syncInterval": 300000,              # 5 min
        "animationsEnabled": True,
    },
    "security": {
        "sessionTimeout": 900000,            # 15 min
        "requireBiometric": False,
        "allowScreenshots": True,
        "maxLoginAttempts": 5,
        "lockoutDuration": 300000,           # 5 min
    },
    "maintenance": {
        "enabled": False,
        "message": "",
        "estimatedEnd": None,
    },
}


# =============================================================================
# SCHEMAS
# =============================================================================

class MobileConfigResponse(BaseModel):
    config: Dict[str, Any]
    version: str = "1.0"
    updated_at: Optional[str] = None
    source: str = "default"  # "default" | "global" | "organization"


class MobileConfigUpdateRequest(BaseModel):
    config: Dict[str, Any] = Field(
        ...,
        description="Partial config dict. Only provided keys are merged; "
                    "omitted keys keep their current values.",
    )


# =============================================================================
# HELPERS
# =============================================================================

def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base. Returns a new dict."""
    result = {**base}
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _ensure_table(db: Session) -> None:
    """Create the remote_config table if it does not exist.

    Uses raw SQL with IF NOT EXISTS so it is safe to call on every request
    without risk of race conditions or errors.
    """
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS remote_config (
            id SERIAL PRIMARY KEY,
            scope VARCHAR(50) NOT NULL DEFAULT 'global',
            organization_id VARCHAR(255),
            config_json TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_by VARCHAR(255),
            UNIQUE(scope, organization_id)
        )
    """))
    db.commit()


def _get_config_row(db: Session, scope: str, organization_id: Optional[str] = None) -> Optional[dict]:
    """Fetch a config row by scope and optional org id."""
    if scope == "global":
        row = db.execute(
            text("SELECT config_json, updated_at FROM remote_config WHERE scope = 'global' LIMIT 1")
        ).fetchone()
    else:
        row = db.execute(
            text(
                "SELECT config_json, updated_at FROM remote_config "
                "WHERE scope = 'organization' AND organization_id = :org_id LIMIT 1"
            ),
            {"org_id": organization_id},
        ).fetchone()
    return row


def _upsert_config(
    db: Session,
    scope: str,
    config_json: str,
    organization_id: Optional[str] = None,
    updated_by: Optional[str] = None,
) -> None:
    """Insert or update a config row."""
    now = datetime.now(timezone.utc).isoformat()

    if scope == "global":
        existing = db.execute(
            text("SELECT id FROM remote_config WHERE scope = 'global' LIMIT 1")
        ).fetchone()
        if existing:
            db.execute(
                text(
                    "UPDATE remote_config SET config_json = :config, updated_at = :now, "
                    "updated_by = :by WHERE scope = 'global'"
                ),
                {"config": config_json, "now": now, "by": updated_by},
            )
        else:
            db.execute(
                text(
                    "INSERT INTO remote_config (scope, config_json, updated_at, updated_by) "
                    "VALUES ('global', :config, :now, :by)"
                ),
                {"config": config_json, "now": now, "by": updated_by},
            )
    else:
        existing = db.execute(
            text(
                "SELECT id FROM remote_config "
                "WHERE scope = 'organization' AND organization_id = :org_id LIMIT 1"
            ),
            {"org_id": organization_id},
        ).fetchone()
        if existing:
            db.execute(
                text(
                    "UPDATE remote_config SET config_json = :config, updated_at = :now, "
                    "updated_by = :by WHERE scope = 'organization' AND organization_id = :org_id"
                ),
                {"config": config_json, "now": now, "by": updated_by, "org_id": organization_id},
            )
        else:
            db.execute(
                text(
                    "INSERT INTO remote_config (scope, organization_id, config_json, updated_at, updated_by) "
                    "VALUES ('organization', :org_id, :config, :now, :by)"
                ),
                {"org_id": organization_id, "config": config_json, "now": now, "by": updated_by},
            )
    db.commit()


def _try_get_current_user(request: Request, get_current_user, get_db):
    """Attempt to extract the current user from the request.

    Returns (user, db_session) on success, (None, db_session) if auth fails.
    This allows the GET endpoint to work both with and without auth.

    Uses centralized auth.tokens.verify_access_token() for proper RS256/HS256
    handling and token blacklist checks.
    """
    db = next(get_db())
    try:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return None, db

        token = auth_header.split(" ", 1)[1]
        try:
            from auth.tokens import verify_access_token
            payload = verify_access_token(token)
        except Exception as _exc:  # noqa: BLE001
            return None, db

        if not payload:
            return None, db

        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            return None, db

        from database.models import User
        user = db.query(User).filter(User.id == user_id).first()
        return user, db

    except Exception as e:
        logger.debug(f"Remote config: auth extraction skipped ({e})")
        return None, db


# =============================================================================
# ROUTE REGISTRATION
# =============================================================================

def register_remote_config_routes(app, get_db, get_current_user, **kwargs):
    """Register remote configuration routes on the FastAPI app."""

    # Ensure the storage table exists on first load
    try:
        db = next(get_db())
        _ensure_table(db)
        db.close()
    except Exception as e:
        logger.warning(f"Remote config table creation deferred: {e}")

    # -----------------------------------------------------------------
    # GET /api/v1/config/mobile
    # No auth required — must work before login for maintenance mode.
    # If a valid bearer token is present, returns org-specific overrides.
    # -----------------------------------------------------------------
    @app.get("/api/v1/config/mobile", response_model=MobileConfigResponse, tags=["Remote Config"])
    async def get_mobile_config(request: Request):
        """Return the merged mobile configuration.

        Resolution order:
        1. Start with DEFAULT_CONFIG
        2. Merge global DB overrides (if any)
        3. Merge organization-specific DB overrides (if user is authenticated)
        """
        user, db = _try_get_current_user(request, get_current_user, get_db)

        try:
            _ensure_table(db)

            merged = {**DEFAULT_CONFIG}
            source = "default"
            updated_at = None

            # Layer 1: global overrides
            global_row = _get_config_row(db, "global")
            if global_row:
                try:
                    global_config = json.loads(global_row[0])
                    merged = _deep_merge(merged, global_config)
                    source = "global"
                    updated_at = str(global_row[1]) if global_row[1] else None
                except (json.JSONDecodeError, IndexError):
                    pass

            # Layer 2: org-specific overrides
            org_id = None
            if user:
                org_id = getattr(user, "organization_id", None)

            if org_id:
                org_row = _get_config_row(db, "organization", str(org_id))
                if org_row:
                    try:
                        org_config = json.loads(org_row[0])
                        merged = _deep_merge(merged, org_config)
                        source = "organization"
                        updated_at = str(org_row[1]) if org_row[1] else updated_at
                    except (json.JSONDecodeError, IndexError):
                        pass

            return MobileConfigResponse(
                config=merged,
                updated_at=updated_at,
                source=source,
            )

        except Exception as e:
            logger.error(f"Remote config GET error: {e}")
            # Always return defaults so the app can function
            return MobileConfigResponse(config=DEFAULT_CONFIG, source="default")
        finally:
            db.close()

    # -----------------------------------------------------------------
    # PUT /api/v1/config/mobile
    # Admin only. Updates the config for the caller's organization.
    # Pass scope=global query param to update the global config (platform admin).
    # -----------------------------------------------------------------
    @app.put("/api/v1/config/mobile", response_model=MobileConfigResponse, tags=["Remote Config"])
    async def update_mobile_config(
        request: Request,
        body: MobileConfigUpdateRequest,
        scope: str = "organization",
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Update mobile configuration.

        - scope=organization (default): updates config for the caller's org.
        - scope=global: updates the global base config (platform admins only).

        The provided config dict is deep-merged into the existing config.
        To remove a key, set it to null explicitly.
        """
        # Verify admin role
        user_role = getattr(current_user, "role", "")
        is_admin = user_role in ("Platform Admin", "Site Admin", "Admin", "admin", "platform_admin", "site_admin")
        if not is_admin:
            raise HTTPException(status_code=403, detail="Admin access required to update remote config")

        _ensure_table(db)

        org_id = str(getattr(current_user, "organization_id", "")) or None
        user_id = str(getattr(current_user, "id", ""))

        if scope == "global":
            # Only platform admins can update global config
            if user_role not in ("Platform Admin", "platform_admin"):
                raise HTTPException(status_code=403, detail="Platform Admin access required for global config")

            # Merge with existing global config
            existing_row = _get_config_row(db, "global")
            existing = {}
            if existing_row:
                try:
                    existing = json.loads(existing_row[0])
                except (json.JSONDecodeError, IndexError):
                    pass

            merged_override = _deep_merge(existing, body.config)
            _upsert_config(db, "global", json.dumps(merged_override), updated_by=user_id)

            # Return the fully resolved config
            full = _deep_merge(DEFAULT_CONFIG, merged_override)
            return MobileConfigResponse(
                config=full,
                updated_at=datetime.now(timezone.utc).isoformat(),
                source="global",
            )

        else:
            # Organization-scoped update
            if not org_id:
                raise HTTPException(status_code=400, detail="No organization found for current user")

            existing_row = _get_config_row(db, "organization", org_id)
            existing = {}
            if existing_row:
                try:
                    existing = json.loads(existing_row[0])
                except (json.JSONDecodeError, IndexError):
                    pass

            merged_override = _deep_merge(existing, body.config)
            _upsert_config(db, "organization", json.dumps(merged_override), organization_id=org_id, updated_by=user_id)

            # Return the fully resolved config (default -> global -> org)
            full = {**DEFAULT_CONFIG}
            global_row = _get_config_row(db, "global")
            if global_row:
                try:
                    full = _deep_merge(full, json.loads(global_row[0]))
                except (json.JSONDecodeError, IndexError):
                    pass
            full = _deep_merge(full, merged_override)

            return MobileConfigResponse(
                config=full,
                updated_at=datetime.now(timezone.utc).isoformat(),
                source="organization",
            )
