"""
Permission Enforcement Service
Provides middleware and utilities for permission checking with Redis caching

Features:
- hasPermission() - Check if employee has specific permission
- checkDataScope() - Verify access to specific resources
- Territory/Team/Ownership filtering
- Redis caching with 60-second TTL
- Audit logging integration

Author: System
Date: 2025-11-15
"""

from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Depends
from functools import wraps
import json
import hashlib

# Redis imports (will implement caching in next phase)
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class PermissionService:
    """
    Core permission checking service with caching and audit logging
    Optimized for 10,000 users with sub-100ms response times
    """

    def __init__(self, db: Session, redis_client=None, audit_logger=None):
        """
        Initialize permission service

        Args:
            db: SQLAlchemy database session
            redis_client: Optional Redis client for caching
            audit_logger: Optional audit logging service
        """
        self.db = db
        self.redis_client = redis_client
        self.audit_logger = audit_logger
        self.cache_ttl = 60  # 60-second TTL for permission cache

    # ============================================================================
    # CORE PERMISSION CHECKING
    # ============================================================================

    def has_permission(
        self,
        employee_id: int,
        permission_key: str,
        check_expiration: bool = True
    ) -> bool:
        """
        Check if employee has a specific permission

        Performance target: <100ms (with caching: <10ms)

        Args:
            employee_id: ID of the employee
            permission_key: Permission key to check (e.g., 'leads.edit_all')
            check_expiration: Whether to check if permission has expired

        Returns:
            True if employee has permission, False otherwise

        Example:
            >>> service.has_permission(123, 'leads.edit_all')
            True
        """

        # Try cache first (fast path: ~5ms)
        cached_result = self._get_cached_permission(employee_id, permission_key)
        if cached_result is not None:
            return cached_result

        # Database lookup (slow path: ~50-100ms)
        result = self.db.execute(text("""
            SELECT granted, expires_at
            FROM employee_permissions
            WHERE employee_id = :employee_id
              AND permission_key = :permission_key
            LIMIT 1
        """), {
            'employee_id': employee_id,
            'permission_key': permission_key
        }).fetchone()

        # No permission record found
        if not result:
            granted = False
        else:
            granted = result[0]
            expires_at = result[1]

            # Check if permission has expired
            if check_expiration and expires_at and datetime.utcnow() > expires_at:
                granted = False

        # Cache the result
        self._cache_permission(employee_id, permission_key, granted)

        return granted

    def has_any_permission(
        self,
        employee_id: int,
        permission_keys: List[str]
    ) -> bool:
        """
        Check if employee has ANY of the specified permissions

        Args:
            employee_id: ID of the employee
            permission_keys: List of permission keys to check

        Returns:
            True if employee has at least one permission
        """
        for key in permission_keys:
            if self.has_permission(employee_id, key):
                return True
        return False

    def has_all_permissions(
        self,
        employee_id: int,
        permission_keys: List[str]
    ) -> bool:
        """
        Check if employee has ALL of the specified permissions

        Args:
            employee_id: ID of the employee
            permission_keys: List of permission keys to check

        Returns:
            True if employee has all permissions
        """
        for key in permission_keys:
            if not self.has_permission(employee_id, key):
                return False
        return True

    def get_employee_permissions(
        self,
        employee_id: int,
        include_metadata: bool = False
    ) -> Dict[str, Any]:
        """
        Get all permissions for an employee

        Uses materialized view for fast lookups

        Args:
            employee_id: ID of the employee
            include_metadata: Whether to include scope, expiration, etc.

        Returns:
            Dictionary of permission_key -> granted/metadata
        """

        # Try cache first
        cache_key = f"employee_permissions:{employee_id}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return json.loads(cached)

        # Use materialized view for fast lookup
        result = self.db.execute(text("""
            SELECT permissions
            FROM mv_employee_permissions_cache
            WHERE employee_id = :employee_id
        """), {'employee_id': employee_id}).fetchone()

        if not result:
            permissions = {}
        else:
            permissions = result[0] or {}

        # If metadata not needed, simplify to just granted status
        if not include_metadata and permissions:
            permissions = {
                key: value.get('granted', False)
                for key, value in permissions.items()
            }

        # Cache the result
        self._set_in_cache(cache_key, json.dumps(permissions))

        return permissions

    # ============================================================================
    # DATA SCOPE CHECKING
    # ============================================================================

    def check_data_scope(
        self,
        employee_id: int,
        resource_type: str,
        resource_id: int,
        action: str = 'view'
    ) -> bool:
        """
        Check if employee has access to specific resource based on:
        - Territory assignment
        - Team membership
        - Direct ownership
        - Permission scope

        Performance target: <100ms

        Args:
            employee_id: ID of the employee
            resource_type: Type of resource ('lead', 'client', 'loan', etc.)
            resource_id: ID of the specific resource
            action: Action being performed ('view', 'edit', 'delete')

        Returns:
            True if employee has access, False otherwise

        Example:
            >>> service.check_data_scope(123, 'lead', 456, 'edit')
            True
        """

        # Get employee's territory and team
        employee_info = self._get_employee_info(employee_id)
        if not employee_info:
            return False

        territory_id = employee_info['territory_id']
        team_id = employee_info['team_id']

        # Check permission level for this resource type
        permission_prefix = f"{resource_type}s"  # leads, clients, loans, etc.

        # Check view_all permission (highest level)
        if self.has_permission(employee_id, f"{permission_prefix}.view_all"):
            if action in ['view', 'edit', 'delete']:
                # For edit/delete, check specific permission too
                if action != 'view':
                    return self.has_permission(employee_id, f"{permission_prefix}.{action}_all")
                return True

        # Check team-level access
        if self.has_permission(employee_id, f"{permission_prefix}.view_team"):
            # Verify resource belongs to same team
            if self._resource_in_team(resource_type, resource_id, team_id):
                if action == 'view':
                    return True
                elif action == 'edit':
                    return self.has_permission(employee_id, f"{permission_prefix}.edit_team")
                elif action == 'delete':
                    return self.has_permission(employee_id, f"{permission_prefix}.delete")

        # Check territory-level access
        if self.has_permission(employee_id, f"{permission_prefix}.view_territory"):
            # Verify resource belongs to same territory
            if self._resource_in_territory(resource_type, resource_id, territory_id):
                if action == 'view':
                    return True
                elif action == 'edit':
                    return self.has_permission(employee_id, f"{permission_prefix}.edit_all")

        # Check direct ownership (assigned to this employee)
        if self.has_permission(employee_id, f"{permission_prefix}.view_assigned"):
            # Verify resource is assigned to this employee
            if self._resource_assigned_to(resource_type, resource_id, employee_id):
                if action == 'view':
                    return True
                elif action == 'edit':
                    return self.has_permission(employee_id, f"{permission_prefix}.edit_own")
                elif action == 'delete':
                    # Usually can't delete own items
                    return False

        return False

    def get_data_scope_filter(
        self,
        employee_id: int,
        resource_type: str
    ) -> Dict[str, Any]:
        """
        Get SQL filter conditions for scoping queries
        Returns conditions that can be applied to WHERE clause

        Args:
            employee_id: ID of the employee
            resource_type: Type of resource ('lead', 'client', 'loan')

        Returns:
            Dictionary with filter conditions

        Example:
            >>> filters = service.get_data_scope_filter(123, 'lead')
            >>> # filters = {'territory_id': 5, 'team_id': 10, 'assigned_to': 123}
        """

        permission_prefix = f"{resource_type}s"
        employee_info = self._get_employee_info(employee_id)

        filters = {}

        # View all - no filters needed
        if self.has_permission(employee_id, f"{permission_prefix}.view_all"):
            return {}  # Empty filter = all records

        # Team-level access
        if self.has_permission(employee_id, f"{permission_prefix}.view_team"):
            filters['team_id'] = employee_info['team_id']
            return filters

        # Territory-level access
        if self.has_permission(employee_id, f"{permission_prefix}.view_territory"):
            filters['territory_id'] = employee_info['territory_id']
            return filters

        # Assigned only
        if self.has_permission(employee_id, f"{permission_prefix}.view_assigned"):
            filters['assigned_to'] = employee_id
            return filters

        # No access - return impossible filter
        filters['assigned_to'] = -1  # No records match
        return filters

    # ============================================================================
    # HELPER METHODS
    # ============================================================================

    def _get_employee_info(self, employee_id: int) -> Optional[Dict[str, Any]]:
        """Get employee's territory and team info (cached)"""

        cache_key = f"employee_info:{employee_id}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return json.loads(cached)

        result = self.db.execute(text("""
            SELECT territory_id, team_id, department_id
            FROM employees
            WHERE id = :employee_id
        """), {'employee_id': employee_id}).fetchone()

        if not result:
            return None

        info = {
            'territory_id': result[0],
            'team_id': result[1],
            'department_id': result[2]
        }

        self._set_in_cache(cache_key, json.dumps(info))
        return info

    def _resource_in_team(
        self,
        resource_type: str,
        resource_id: int,
        team_id: int
    ) -> bool:
        """Check if resource belongs to team"""

        table_map = {
            'lead': 'leads',
            'client': 'clients',
            'loan': 'loans'
        }
        table = table_map.get(resource_type)
        if not table:
            return False

        result = self.db.execute(text(f"""
            SELECT COUNT(*) FROM {table}
            WHERE id = :resource_id
              AND team_id = :team_id
        """), {
            'resource_id': resource_id,
            'team_id': team_id
        }).fetchone()

        return result[0] > 0 if result else False

    def _resource_in_territory(
        self,
        resource_type: str,
        resource_id: int,
        territory_id: int
    ) -> bool:
        """Check if resource belongs to territory"""

        table_map = {
            'lead': 'leads',
            'client': 'clients',
            'loan': 'loans'
        }
        table = table_map.get(resource_type)
        if not table:
            return False

        result = self.db.execute(text(f"""
            SELECT COUNT(*) FROM {table}
            WHERE id = :resource_id
              AND territory_id = :territory_id
        """), {
            'resource_id': resource_id,
            'territory_id': territory_id
        }).fetchone()

        return result[0] > 0 if result else False

    def _resource_assigned_to(
        self,
        resource_type: str,
        resource_id: int,
        employee_id: int
    ) -> bool:
        """Check if resource is assigned to employee"""

        table_map = {
            'lead': 'leads',
            'client': 'clients',
            'loan': 'loans'
        }
        table = table_map.get(resource_type)
        if not table:
            return False

        result = self.db.execute(text(f"""
            SELECT COUNT(*) FROM {table}
            WHERE id = :resource_id
              AND assigned_to = :employee_id
        """), {
            'resource_id': resource_id,
            'employee_id': employee_id
        }).fetchone()

        return result[0] > 0 if result else False

    # ============================================================================
    # REDIS CACHING (60-SECOND TTL)
    # ============================================================================

    def _get_cached_permission(
        self,
        employee_id: int,
        permission_key: str
    ) -> Optional[bool]:
        """Get permission from Redis cache"""

        if not self.redis_client:
            return None

        cache_key = f"perm:{employee_id}:{permission_key}"
        try:
            cached = self.redis_client.get(cache_key)
            if cached:
                return cached.decode() == 'true'
        except Exception as e:
            print(f"Redis cache error: {e}")

        return None

    def _cache_permission(
        self,
        employee_id: int,
        permission_key: str,
        granted: bool
    ):
        """Cache permission in Redis with 60-second TTL"""

        if not self.redis_client:
            return

        cache_key = f"perm:{employee_id}:{permission_key}"
        try:
            self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                'true' if granted else 'false'
            )
        except Exception as e:
            print(f"Redis cache error: {e}")

    def _get_from_cache(self, key: str) -> Optional[str]:
        """Get value from Redis cache"""

        if not self.redis_client:
            return None

        try:
            cached = self.redis_client.get(key)
            return cached.decode() if cached else None
        except Exception as e:
            print(f"Redis cache error: {e}")
            return None

    def _set_in_cache(self, key: str, value: str):
        """Set value in Redis cache with TTL"""

        if not self.redis_client:
            return

        try:
            self.redis_client.setex(key, self.cache_ttl, value)
        except Exception as e:
            print(f"Redis cache error: {e}")

    def invalidate_employee_cache(self, employee_id: int):
        """Invalidate all cached data for an employee"""

        if not self.redis_client:
            return

        try:
            # Delete all permission keys for this employee
            pattern = f"perm:{employee_id}:*"
            for key in self.redis_client.scan_iter(match=pattern):
                self.redis_client.delete(key)

            # Delete employee info
            self.redis_client.delete(f"employee_info:{employee_id}")
            self.redis_client.delete(f"employee_permissions:{employee_id}")
        except Exception as e:
            print(f"Redis cache invalidation error: {e}")

    # ============================================================================
    # AUDIT LOGGING
    # ============================================================================

    def log_permission_check(
        self,
        employee_id: int,
        permission_key: str,
        granted: bool,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None
    ):
        """Log permission check for audit trail"""

        if not self.audit_logger:
            return

        self.audit_logger.log_event(
            event_type='permission_check',
            employee_id=employee_id,
            details={
                'permission_key': permission_key,
                'granted': granted,
                'resource_type': resource_type,
                'resource_id': resource_id
            }
        )


# ============================================================================
# FASTAPI MIDDLEWARE & DEPENDENCIES
# ============================================================================

def require_permission(permission_key: str):
    """
    FastAPI dependency for requiring specific permission

    Usage:
        @app.get("/leads", dependencies=[Depends(require_permission("leads.view_all"))])
        async def get_leads():
            ...
    """

    async def check_permission(
        current_user = Depends(get_current_user),
        db: Session = Depends(get_db),
        permission_service: PermissionService = Depends(get_permission_service)
    ):
        if not permission_service.has_permission(current_user.id, permission_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission_key}"
            )
        return current_user

    return check_permission


def require_data_scope(resource_type: str, action: str = 'view'):
    """
    FastAPI dependency for checking data scope on specific resource

    Usage:
        @app.get("/leads/{lead_id}")
        async def get_lead(
            lead_id: int,
            user = Depends(require_data_scope("lead", "view"))
        ):
            ...
    """

    async def check_scope(
        resource_id: int,
        current_user = Depends(get_current_user),
        db: Session = Depends(get_db),
        permission_service: PermissionService = Depends(get_permission_service)
    ):
        if not permission_service.check_data_scope(
            current_user.id,
            resource_type,
            resource_id,
            action
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to {resource_type} {resource_id}"
            )
        return current_user

    return check_scope


# ============================================================================
# PLACEHOLDER DEPENDENCIES (implement these in main app)
# ============================================================================

def get_current_user():
    """Placeholder - implement in main app to get current authenticated user"""
    raise NotImplementedError("get_current_user dependency not implemented")


def get_db():
    """Placeholder - implement in main app to get database session"""
    raise NotImplementedError("get_db dependency not implemented")


def get_permission_service(db: Session = Depends(get_db)):
    """Placeholder - implement in main app to get permission service instance"""
    raise NotImplementedError("get_permission_service dependency not implemented")
