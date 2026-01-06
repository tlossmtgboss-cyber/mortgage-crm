"""
Module Service

Handles subscription module access checking and management.
Organizations can have different modules enabled based on their subscription.
"""

from typing import List, Dict, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
import json


class ModuleService:
    """Service for managing subscription modules."""

    # Base module is always available
    BASE_MODULE = 'base'

    @staticmethod
    def get_all_modules(db: Session) -> List[Dict]:
        """Get all available subscription modules."""
        result = db.execute(text("""
            SELECT
                id, module_key, module_name, description, category, icon,
                monthly_price, annual_price, stripe_price_id_monthly, stripe_price_id_annual,
                included_features, gated_routes, sort_order, is_active
            FROM subscription_modules
            WHERE is_active = TRUE
            ORDER BY sort_order ASC
        """))

        modules = []
        for row in result.fetchall():
            modules.append({
                'id': row[0],
                'module_key': row[1],
                'module_name': row[2],
                'description': row[3],
                'category': row[4],
                'icon': row[5],
                'monthly_price': float(row[6]) if row[6] else 0,
                'annual_price': float(row[7]) if row[7] else 0,
                'stripe_price_id_monthly': row[8],
                'stripe_price_id_annual': row[9],
                'included_features': row[10] if isinstance(row[10], list) else json.loads(row[10] or '[]'),
                'gated_routes': row[11] if isinstance(row[11], list) else json.loads(row[11] or '[]'),
                'sort_order': row[12],
                'is_active': row[13]
            })

        return modules

    @staticmethod
    def get_module_by_key(db: Session, module_key: str) -> Optional[Dict]:
        """Get a specific module by its key."""
        result = db.execute(text("""
            SELECT
                id, module_key, module_name, description, category, icon,
                monthly_price, annual_price, stripe_price_id_monthly, stripe_price_id_annual,
                included_features, gated_routes, sort_order, is_active
            FROM subscription_modules
            WHERE module_key = :module_key AND is_active = TRUE
        """), {'module_key': module_key}).fetchone()

        if not result:
            return None

        return {
            'id': result[0],
            'module_key': result[1],
            'module_name': result[2],
            'description': result[3],
            'category': result[4],
            'icon': result[5],
            'monthly_price': float(result[6]) if result[6] else 0,
            'annual_price': float(result[7]) if result[7] else 0,
            'stripe_price_id_monthly': result[8],
            'stripe_price_id_annual': result[9],
            'included_features': result[10] if isinstance(result[10], list) else json.loads(result[10] or '[]'),
            'gated_routes': result[11] if isinstance(result[11], list) else json.loads(result[11] or '[]'),
            'sort_order': result[12],
            'is_active': result[13]
        }

    @staticmethod
    def get_organization_modules(db: Session, organization_id: int) -> List[str]:
        """Get list of enabled module keys for an organization."""
        result = db.execute(text("""
            SELECT module_key
            FROM organization_modules
            WHERE organization_id = :org_id AND is_enabled = TRUE
        """), {'org_id': organization_id})

        modules = [row[0] for row in result.fetchall()]

        # Base module is always included
        if ModuleService.BASE_MODULE not in modules:
            modules.insert(0, ModuleService.BASE_MODULE)

        return modules

    @staticmethod
    def get_organization_modules_detailed(db: Session, organization_id: int) -> List[Dict]:
        """Get detailed module information for an organization."""
        result = db.execute(text("""
            SELECT
                sm.id, sm.module_key, sm.module_name, sm.description, sm.category, sm.icon,
                sm.monthly_price, sm.annual_price, sm.included_features, sm.gated_routes,
                om.is_enabled, om.enabled_at, om.is_trial, om.trial_ends_at, om.billing_status
            FROM subscription_modules sm
            LEFT JOIN organization_modules om
                ON sm.module_key = om.module_key AND om.organization_id = :org_id
            WHERE sm.is_active = TRUE
            ORDER BY sm.sort_order ASC
        """), {'org_id': organization_id})

        modules = []
        for row in result.fetchall():
            is_base = row[1] == ModuleService.BASE_MODULE
            modules.append({
                'id': row[0],
                'module_key': row[1],
                'module_name': row[2],
                'description': row[3],
                'category': row[4],
                'icon': row[5],
                'monthly_price': float(row[6]) if row[6] else 0,
                'annual_price': float(row[7]) if row[7] else 0,
                'included_features': row[8] if isinstance(row[8], list) else json.loads(row[8] or '[]'),
                'gated_routes': row[9] if isinstance(row[9], list) else json.loads(row[9] or '[]'),
                'is_enabled': is_base or bool(row[10]),  # Base is always enabled
                'enabled_at': row[11].isoformat() if row[11] else None,
                'is_trial': bool(row[12]),
                'trial_ends_at': row[13].isoformat() if row[13] else None,
                'billing_status': row[14] or 'active' if row[10] else None
            })

        return modules

    @staticmethod
    def has_module(db: Session, organization_id: int, module_key: str) -> bool:
        """Check if an organization has access to a specific module."""
        # Base module is always available
        if module_key == ModuleService.BASE_MODULE:
            return True

        result = db.execute(text("""
            SELECT is_enabled
            FROM organization_modules
            WHERE organization_id = :org_id AND module_key = :module_key
        """), {'org_id': organization_id, 'module_key': module_key}).fetchone()

        return bool(result and result[0])

    @staticmethod
    def has_feature(db: Session, organization_id: int, feature_key: str) -> bool:
        """Check if an organization has access to a specific feature."""
        # Get all enabled modules for the org
        enabled_modules = ModuleService.get_organization_modules(db, organization_id)

        # Get all modules and check if any enabled module includes this feature
        all_modules = ModuleService.get_all_modules(db)

        for module in all_modules:
            if module['module_key'] in enabled_modules:
                if feature_key in module['included_features']:
                    return True

        return False

    @staticmethod
    def is_route_accessible(db: Session, organization_id: int, route_path: str) -> Dict:
        """Check if a route is accessible to an organization."""
        enabled_modules = ModuleService.get_organization_modules(db, organization_id)
        all_modules = ModuleService.get_all_modules(db)

        for module in all_modules:
            for gated_route in module['gated_routes']:
                if route_path.startswith(gated_route):
                    if module['module_key'] in enabled_modules:
                        return {'accessible': True, 'module_key': module['module_key']}
                    else:
                        return {
                            'accessible': False,
                            'module_key': module['module_key'],
                            'module_name': module['module_name'],
                            'monthly_price': module['monthly_price']
                        }

        # Route not gated by any module
        return {'accessible': True, 'module_key': None}

    @staticmethod
    def enable_module(
        db: Session,
        organization_id: int,
        module_key: str,
        enabled_by: int,
        stripe_subscription_item_id: Optional[str] = None,
        is_trial: bool = False,
        trial_days: int = 14
    ) -> Dict:
        """Enable a module for an organization."""
        from datetime import timedelta

        # Check if module exists
        module = ModuleService.get_module_by_key(db, module_key)
        if not module:
            raise ValueError(f"Module '{module_key}' not found")

        # Check if already enabled
        existing = db.execute(text("""
            SELECT id, is_enabled FROM organization_modules
            WHERE organization_id = :org_id AND module_key = :module_key
        """), {'org_id': organization_id, 'module_key': module_key}).fetchone()

        trial_ends_at = None
        if is_trial:
            trial_ends_at = datetime.utcnow() + timedelta(days=trial_days)

        if existing:
            # Update existing record
            db.execute(text("""
                UPDATE organization_modules SET
                    is_enabled = TRUE,
                    enabled_at = NOW(),
                    enabled_by = :enabled_by,
                    stripe_subscription_item_id = :stripe_item_id,
                    is_trial = :is_trial,
                    trial_ends_at = :trial_ends_at,
                    billing_status = 'active',
                    updated_at = NOW()
                WHERE organization_id = :org_id AND module_key = :module_key
            """), {
                'org_id': organization_id,
                'module_key': module_key,
                'enabled_by': enabled_by,
                'stripe_item_id': stripe_subscription_item_id,
                'is_trial': is_trial,
                'trial_ends_at': trial_ends_at
            })
        else:
            # Create new record
            db.execute(text("""
                INSERT INTO organization_modules
                (organization_id, module_key, is_enabled, enabled_at, enabled_by,
                 stripe_subscription_item_id, is_trial, trial_ends_at, billing_status)
                VALUES
                (:org_id, :module_key, TRUE, NOW(), :enabled_by,
                 :stripe_item_id, :is_trial, :trial_ends_at, 'active')
            """), {
                'org_id': organization_id,
                'module_key': module_key,
                'enabled_by': enabled_by,
                'stripe_item_id': stripe_subscription_item_id,
                'is_trial': is_trial,
                'trial_ends_at': trial_ends_at
            })

        db.commit()

        return {
            'success': True,
            'module_key': module_key,
            'module_name': module['module_name'],
            'is_trial': is_trial,
            'trial_ends_at': trial_ends_at.isoformat() if trial_ends_at else None
        }

    @staticmethod
    def disable_module(db: Session, organization_id: int, module_key: str) -> Dict:
        """Disable a module for an organization."""
        # Cannot disable base module
        if module_key == ModuleService.BASE_MODULE:
            raise ValueError("Cannot disable the base module")

        db.execute(text("""
            UPDATE organization_modules SET
                is_enabled = FALSE,
                billing_status = 'canceled',
                updated_at = NOW()
            WHERE organization_id = :org_id AND module_key = :module_key
        """), {'org_id': organization_id, 'module_key': module_key})

        db.commit()

        return {'success': True, 'module_key': module_key}

    @staticmethod
    def get_pricing_summary(db: Session, organization_id: int) -> Dict:
        """Calculate total pricing for an organization's selected modules."""
        modules = ModuleService.get_organization_modules_detailed(db, organization_id)

        enabled_modules = [m for m in modules if m['is_enabled']]
        premium_modules = [m for m in enabled_modules if m['category'] == 'premium']

        base_price = next((m['monthly_price'] for m in enabled_modules if m['category'] == 'base'), 99.00)
        modules_price = sum(m['monthly_price'] for m in premium_modules)

        return {
            'base_price': base_price,
            'modules_price': modules_price,
            'total_monthly': base_price + modules_price,
            'total_annual': (base_price + modules_price) * 10,  # 2 months free
            'enabled_modules': [m['module_key'] for m in enabled_modules],
            'premium_modules_count': len(premium_modules)
        }

    @staticmethod
    def get_navigation_with_access(db: Session, organization_id: int) -> List[Dict]:
        """Get all navigation items with their lock status based on modules."""
        enabled_modules = ModuleService.get_organization_modules(db, organization_id)
        all_modules = ModuleService.get_all_modules(db)

        # Build route to module mapping
        route_module_map = {}
        for module in all_modules:
            for route in module['gated_routes']:
                route_module_map[route] = {
                    'module_key': module['module_key'],
                    'module_name': module['module_name'],
                    'monthly_price': module['monthly_price'],
                    'is_enabled': module['module_key'] in enabled_modules
                }

        return {
            'enabled_modules': enabled_modules,
            'route_access': route_module_map
        }
