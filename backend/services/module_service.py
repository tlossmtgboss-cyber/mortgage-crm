"""
Module Service

Business logic for the modular subscription system.
Handles module access checks, enabling/disabling modules, and navigation gating.
"""

import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# Default navigation items with module requirements
DEFAULT_NAVIGATION_ITEMS = [
    {"path": "/dashboard", "label": "Dashboard", "module": "base", "icon": "dashboard"},
    {"path": "/leads", "label": "Leads", "module": "base", "icon": "people"},
    {"path": "/loans", "label": "Active Loans", "module": "base", "icon": "account_balance"},
    {"path": "/portfolio", "label": "MUM Clients", "module": "base", "icon": "folder_shared"},
    {"path": "/tasks", "label": "Tasks", "module": "base", "icon": "task_alt"},
    {"path": "/calendar", "label": "Calendar", "module": "base", "icon": "calendar_today"},
    {"path": "/smart-docs", "label": "Smart Docs", "module": "base", "icon": "description"},
    {"path": "/reconciliation", "label": "Reconciliation", "module": "base", "icon": "balance"},
    {"path": "/ai-underwriter", "label": "AI Underwriter", "module": "ai_assistant", "icon": "psychology"},
    {"path": "/ai-chat", "label": "AI Chat", "module": "ai_assistant", "icon": "smart_toy"},
    {"path": "/ai-email-training", "label": "Email Training", "module": "ai_assistant", "icon": "school"},
    {"path": "/referral-partners", "label": "Partners", "module": "partner_portals", "icon": "handshake"},
    {"path": "/realtor-portal", "label": "Realtor Portal", "module": "partner_portals", "icon": "home_work"},
    {"path": "/listing-portal", "label": "Listing Portal", "module": "partner_portals", "icon": "apartment"},
    {"path": "/video-os", "label": "Video OS", "module": "video_os", "icon": "videocam"},
    {"path": "/master-manager/recruiting", "label": "Recruiting", "module": "recruiting_suite", "icon": "person_add"},
    {"path": "/conversation-intelligence", "label": "Call Intelligence", "module": "conversation_intelligence", "icon": "record_voice_over"},
    {"path": "/profitability", "label": "Profitability", "module": "advanced_analytics", "icon": "trending_up"},
    # {"path": "/decision-lab", "label": "Decision Lab", "module": "advanced_analytics", "icon": "science"},  # DEPRECATED: Experimental feature deregistered
    {"path": "/integrations", "label": "Integrations", "module": "integrations", "icon": "extension"},
]

# Module icon mapping
MODULE_ICONS = {
    "base": "home",
    "ai_assistant": "psychology",
    "partner_portals": "handshake",
    "video_os": "videocam",
    "recruiting_suite": "person_add",
    "conversation_intelligence": "record_voice_over",
    "advanced_analytics": "insights",
    "integrations": "extension",
}


def _parse_json_field(value) -> list:
    """Parse JSON field that may be string or list."""
    if isinstance(value, str):
        return json.loads(value) if value else []
    elif isinstance(value, list):
        return value
    return []


class ModuleService:
    """Service for managing subscription modules.

    All methods are static and take db as first parameter for compatibility
    with the routes that use dependency injection.
    """

    @staticmethod
    def get_all_modules(db: Session, include_inactive: bool = False) -> List[Dict]:
        """Get all available subscription modules."""
        try:
            query = """
                SELECT
                    id, module_key, module_name, description, category,
                    monthly_price, annual_price, stripe_price_id_monthly,
                    stripe_price_id_annual, included_features, gated_routes,
                    sort_order, is_active
                FROM subscription_modules
            """
            if not include_inactive:
                query += " WHERE is_active = true"
            query += " ORDER BY sort_order ASC"

            result = db.execute(text(query))
            modules = []
            for row in result.fetchall():
                modules.append({
                    "id": row[0],
                    "module_key": row[1],
                    "module_name": row[2],
                    "description": row[3],
                    "category": row[4],
                    "icon": MODULE_ICONS.get(row[1], "extension"),
                    "monthly_price": float(row[5] or 0),
                    "annual_price": float(row[6] or 0),
                    "stripe_price_id_monthly": row[7],
                    "stripe_price_id_annual": row[8],
                    "included_features": _parse_json_field(row[9]),
                    "gated_routes": _parse_json_field(row[10]),
                    "sort_order": row[11],
                    "is_active": row[12],
                })
            return modules
        except Exception as e:
            logger.error(f"Error getting modules: {e}")
            return []

    @staticmethod
    def get_module_by_key(db: Session, module_key: str) -> Optional[Dict]:
        """Get a specific module by key."""
        try:
            result = db.execute(text("""
                SELECT
                    id, module_key, module_name, description, category,
                    monthly_price, annual_price, stripe_price_id_monthly,
                    stripe_price_id_annual, included_features, gated_routes,
                    sort_order, is_active
                FROM subscription_modules
                WHERE module_key = :key
            """), {"key": module_key})
            row = result.fetchone()
            if not row:
                return None

            return {
                "id": row[0],
                "module_key": row[1],
                "module_name": row[2],
                "description": row[3],
                "category": row[4],
                "icon": MODULE_ICONS.get(row[1], "extension"),
                "monthly_price": float(row[5] or 0),
                "annual_price": float(row[6] or 0),
                "stripe_price_id_monthly": row[7],
                "stripe_price_id_annual": row[8],
                "included_features": _parse_json_field(row[9]),
                "gated_routes": _parse_json_field(row[10]),
                "sort_order": row[11],
                "is_active": row[12],
            }
        except Exception as e:
            logger.error(f"Error getting module {module_key}: {e}")
            return None

    @staticmethod
    def get_organization_modules(db: Session, organization_id: int) -> List[Dict]:
        """Get all modules for an organization with their enabled status."""
        try:
            result = db.execute(text("""
                SELECT
                    sm.module_key,
                    sm.module_name,
                    sm.description,
                    sm.category,
                    sm.monthly_price,
                    sm.annual_price,
                    sm.included_features,
                    sm.gated_routes,
                    COALESCE(om.is_enabled, CASE WHEN sm.category = 'base' THEN true ELSE false END) as is_enabled,
                    om.enabled_at,
                    om.is_trial,
                    om.trial_ends_at
                FROM subscription_modules sm
                LEFT JOIN organization_modules om
                    ON sm.module_key = om.module_key
                    AND om.organization_id = :org_id
                WHERE sm.is_active = true
                ORDER BY sm.sort_order ASC
            """), {"org_id": organization_id})

            modules = []
            for row in result.fetchall():
                is_trial = row[10] if row[10] is not None else False
                trial_ends_at = row[11]

                # Check if trial has expired
                trial_active = False
                if is_trial and trial_ends_at:
                    trial_active = datetime.now() < trial_ends_at

                modules.append({
                    "module_key": row[0],
                    "module_name": row[1],
                    "description": row[2],
                    "category": row[3],
                    "icon": MODULE_ICONS.get(row[0], "extension"),
                    "monthly_price": float(row[4] or 0),
                    "annual_price": float(row[5] or 0),
                    "included_features": _parse_json_field(row[6]),
                    "gated_routes": _parse_json_field(row[7]),
                    "is_enabled": row[8] or trial_active,
                    "enabled_at": row[9].isoformat() if row[9] else None,
                    "is_trial": trial_active,
                    "trial_ends_at": trial_ends_at.isoformat() if trial_ends_at else None,
                })
            return modules
        except Exception as e:
            logger.error(f"Error getting org modules: {e}")
            return []

    @staticmethod
    def get_organization_modules_detailed(db: Session, organization_id: int) -> List[Dict]:
        """Get detailed modules for an organization (alias for get_organization_modules)."""
        return ModuleService.get_organization_modules(db, organization_id)

    @staticmethod
    def has_module(db: Session, organization_id: int, module_key: str) -> bool:
        """Check if an organization has access to a specific module."""
        if module_key == "base":
            return True

        try:
            result = db.execute(text("""
                SELECT om.is_enabled, om.is_trial, om.trial_ends_at
                FROM organization_modules om
                WHERE om.organization_id = :org_id
                    AND om.module_key = :module_key
            """), {"org_id": organization_id, "module_key": module_key})

            row = result.fetchone()
            if not row:
                return False

            is_enabled = row[0]
            is_trial = row[1]
            trial_ends_at = row[2]

            if is_enabled:
                return True

            if is_trial and trial_ends_at:
                return datetime.now() < trial_ends_at

            return False
        except Exception as e:
            logger.error(f"Error checking module access: {e}")
            return False

    @staticmethod
    def has_feature(db: Session, organization_id: int, feature_key: str) -> bool:
        """Check if an organization has access to a specific feature.

        Features are mapped to modules - this checks if the parent module is enabled.
        """
        # Feature to module mapping
        feature_module_map = {
            "ai_chat": "ai_assistant",
            "ai_underwriter": "ai_assistant",
            "email_training": "ai_assistant",
            "realtor_portal": "partner_portals",
            "listing_portal": "partner_portals",
            "purl": "partner_portals",
            "video_creation": "video_os",
            "avatars": "video_os",
            "candidate_pipeline": "recruiting_suite",
            "disc_assessment": "recruiting_suite",
            "call_recording": "conversation_intelligence",
            "qa_scoring": "conversation_intelligence",
            # "decision_lab": "advanced_analytics",  # DEPRECATED: Experimental feature deregistered
            "profitability": "advanced_analytics",
            "salesforce": "integrations",
            "hubspot": "integrations",
        }

        module_key = feature_module_map.get(feature_key, "base")
        return ModuleService.has_module(db, organization_id, module_key)

    @staticmethod
    def is_route_accessible(db: Session, organization_id: int, route_path: str) -> Dict:
        """Check if a route is accessible for an organization."""
        try:
            modules = ModuleService.get_organization_modules(db, organization_id)

            for module in modules:
                gated_routes = module.get("gated_routes", [])
                for gated_route in gated_routes:
                    if route_path.startswith(gated_route):
                        return {
                            "accessible": module["is_enabled"],
                            "required_module": module["module_key"],
                            "module_name": module["module_name"],
                            "monthly_price": module["monthly_price"],
                        }

            return {"accessible": True, "required_module": None}
        except Exception as e:
            logger.error(f"Error checking route access: {e}")
            return {"accessible": True, "required_module": None}

    @staticmethod
    def get_navigation_with_access(db: Session, organization_id: int) -> Dict:
        """Get navigation items with lock status based on modules."""
        org_modules = ModuleService.get_organization_modules(db, organization_id)
        enabled_keys = {m["module_key"] for m in org_modules if m["is_enabled"]}

        # Build route access map
        route_access = {}
        for item in DEFAULT_NAVIGATION_ITEMS:
            module_key = item.get("module", "base")
            is_locked = module_key not in enabled_keys and module_key != "base"

            required_module = None
            if is_locked:
                for m in org_modules:
                    if m["module_key"] == module_key:
                        required_module = {
                            "key": m["module_key"],
                            "name": m["module_name"],
                            "price": m["monthly_price"],
                        }
                        break

            route_access[item["path"]] = {
                "is_locked": is_locked,
                "required_module": required_module,
            }

        return {
            "enabled_modules": list(enabled_keys),
            "route_access": route_access,
            "navigation_items": [
                {
                    **item,
                    "is_locked": route_access[item["path"]]["is_locked"],
                    "required_module": route_access[item["path"]]["required_module"],
                }
                for item in DEFAULT_NAVIGATION_ITEMS
            ],
        }

    @staticmethod
    def get_pricing_summary(db: Session, organization_id: int) -> Dict:
        """Get pricing summary for an organization's modules."""
        modules = ModuleService.get_organization_modules(db, organization_id)

        enabled_modules = [m for m in modules if m["is_enabled"]]
        base_module = next((m for m in enabled_modules if m["category"] == "base"), None)
        premium_modules = [m for m in enabled_modules if m["category"] != "base"]

        base_price = base_module["monthly_price"] if base_module else 99.0
        modules_price = sum(m["monthly_price"] for m in premium_modules)
        total_monthly = base_price + modules_price
        total_annual = sum(m["annual_price"] for m in enabled_modules)

        return {
            "base_price": base_price,
            "modules_price": modules_price,
            "total_monthly": total_monthly,
            "total_annual": total_annual,
            "enabled_modules": [m["module_key"] for m in enabled_modules],
            "premium_modules_count": len(premium_modules),
        }

    @staticmethod
    def enable_module(
        db: Session,
        organization_id: int,
        module_key: str,
        enabled_by: Optional[int] = None,
        stripe_subscription_item_id: Optional[str] = None,
        is_trial: bool = False,
        trial_days: int = 14,
    ) -> Dict:
        """Enable a module for an organization."""
        try:
            # Verify module exists
            module = ModuleService.get_module_by_key(db, module_key)
            if not module:
                raise ValueError(f"Module '{module_key}' not found")

            now = datetime.now()
            trial_ends_at = now + timedelta(days=trial_days) if is_trial else None

            db.execute(text("""
                INSERT INTO organization_modules
                (organization_id, module_key, is_enabled, enabled_at,
                 stripe_subscription_item_id, is_trial, trial_ends_at)
                VALUES (:org_id, :module_key, :is_enabled, :enabled_at,
                        :stripe_item_id, :is_trial, :trial_ends_at)
                ON CONFLICT (organization_id, module_key)
                DO UPDATE SET
                    is_enabled = EXCLUDED.is_enabled,
                    enabled_at = EXCLUDED.enabled_at,
                    stripe_subscription_item_id = EXCLUDED.stripe_subscription_item_id,
                    is_trial = EXCLUDED.is_trial,
                    trial_ends_at = EXCLUDED.trial_ends_at,
                    disabled_at = NULL,
                    updated_at = NOW()
            """), {
                "org_id": organization_id,
                "module_key": module_key,
                "is_enabled": not is_trial,
                "enabled_at": now,
                "stripe_item_id": stripe_subscription_item_id,
                "is_trial": is_trial,
                "trial_ends_at": trial_ends_at,
            })
            db.commit()

            return {
                "success": True,
                "module_key": module_key,
                "module_name": module["module_name"],
                "is_trial": is_trial,
                "trial_ends_at": trial_ends_at.isoformat() if trial_ends_at else None,
            }
        except ValueError as e:
            raise
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error enabling module: {e}")
            return {"success": False, "error": "Internal server error"}

    @staticmethod
    def disable_module(db: Session, organization_id: int, module_key: str) -> Dict:
        """Disable a module for an organization."""
        if module_key == "base":
            raise ValueError("Cannot disable base package")

        try:
            db.execute(text("""
                UPDATE organization_modules
                SET is_enabled = false,
                    disabled_at = NOW(),
                    is_trial = false,
                    updated_at = NOW()
                WHERE organization_id = :org_id
                    AND module_key = :module_key
            """), {"org_id": organization_id, "module_key": module_key})
            db.commit()

            return {"success": True, "module_key": module_key}
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error disabling module: {e}")
            return {"success": False, "error": "Internal server error"}

    @staticmethod
    def calculate_subscription_total(
        db: Session,
        module_keys: List[str],
        billing_cycle: str = "monthly"
    ) -> Dict:
        """Calculate total subscription price for selected modules."""
        try:
            modules = ModuleService.get_all_modules(db)
            total = 0.0
            selected_modules = []

            for module in modules:
                if module["module_key"] in module_keys:
                    price = module["monthly_price"] if billing_cycle == "monthly" else module["annual_price"]
                    total += price
                    selected_modules.append({
                        "module_key": module["module_key"],
                        "module_name": module["module_name"],
                        "price": price,
                    })

            return {
                "billing_cycle": billing_cycle,
                "total": total,
                "modules": selected_modules,
            }
        except Exception as e:
            logger.error(f"Error calculating total: {e}")
            return {"error": "Internal server error"}


def get_module_service(db: Session) -> ModuleService:
    """Get a ModuleService instance (deprecated, use static methods directly)."""
    return ModuleService()
