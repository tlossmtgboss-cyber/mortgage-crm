"""
Redis Caching Service
High-performance caching layer for permissions and employee data

Features:
- 60-second TTL for permissions
- Automatic cache invalidation
- Materialized view refresh coordination
- Connection pooling
- Cluster mode support

AWS ElastiCache Redis Configuration:
- Cluster mode enabled
- 3 shards for horizontal scaling
- Multi-AZ with automatic failover

Author: System
Date: 2025-11-15
"""

import redis
from redis.cluster import RedisCluster
from typing import Optional, Any, Dict, List
import json
import os
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session


class RedisCacheService:
    """
    Redis caching service optimized for 10,000 users

    Performance targets:
    - Cache hit: <5ms
    - Cache miss: <10ms
    - Invalidation: <20ms
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
        cluster_mode: bool = False,
        cluster_nodes: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Initialize Redis cache service

        Args:
            host: Redis host (default: from env REDIS_HOST)
            port: Redis port (default: 6379)
            password: Redis password (default: from env REDIS_PASSWORD)
            db: Redis database number (default: 0)
            cluster_mode: Whether to use cluster mode (default: False)
            cluster_nodes: List of cluster nodes for cluster mode

        Environment Variables:
            REDIS_HOST: Redis host address
            REDIS_PORT: Redis port
            REDIS_PASSWORD: Redis password
            REDIS_CLUSTER_MODE: 'true' for cluster mode
            REDIS_CLUSTER_NODES: JSON array of cluster nodes
        """

        # Get config from environment
        self.host = host or os.getenv('REDIS_HOST', 'localhost')
        self.port = int(os.getenv('REDIS_PORT', port))
        self.password = password or os.getenv('REDIS_PASSWORD')
        self.db = db

        # Cluster mode setup
        self.cluster_mode = cluster_mode or os.getenv('REDIS_CLUSTER_MODE', 'false').lower() == 'true'

        # Initialize Redis client
        if self.cluster_mode:
            self.client = self._init_cluster_client(cluster_nodes)
        else:
            self.client = self._init_standalone_client()

        # Cache TTL settings (in seconds)
        self.permission_ttl = 60  # 60 seconds for permissions
        self.employee_info_ttl = 300  # 5 minutes for employee info
        self.template_ttl = 3600  # 1 hour for templates (rarely change)

        print(f"✅ Redis cache initialized ({'cluster' if self.cluster_mode else 'standalone'} mode)")

    def _init_standalone_client(self) -> redis.Redis:
        """Initialize standalone Redis client with connection pooling"""

        pool = redis.ConnectionPool(
            host=self.host,
            port=self.port,
            password=self.password,
            db=self.db,
            max_connections=100,  # Connection pool size
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            decode_responses=False
        )

        return redis.Redis(connection_pool=pool)

    def _init_cluster_client(self, cluster_nodes: Optional[List[Dict[str, Any]]] = None) -> RedisCluster:
        """Initialize Redis cluster client (for AWS ElastiCache cluster mode)"""

        # Parse cluster nodes from environment if not provided
        if cluster_nodes is None:
            nodes_json = os.getenv('REDIS_CLUSTER_NODES')
            if nodes_json:
                cluster_nodes = json.loads(nodes_json)
            else:
                # Default to single node (will auto-discover cluster)
                cluster_nodes = [{'host': self.host, 'port': self.port}]

        return RedisCluster(
            startup_nodes=cluster_nodes,
            password=self.password,
            decode_responses=False,
            skip_full_coverage_check=False,
            max_connections_per_node=50
        )

    # ============================================================================
    # PERMISSION CACHING (60-SECOND TTL)
    # ============================================================================

    def cache_permission(
        self,
        employee_id: int,
        permission_key: str,
        granted: bool
    ) -> bool:
        """
        Cache a permission check result

        Args:
            employee_id: Employee ID
            permission_key: Permission key
            granted: Whether permission is granted

        Returns:
            True if cached successfully
        """

        key = f"perm:{employee_id}:{permission_key}"
        try:
            self.client.setex(
                key,
                self.permission_ttl,
                '1' if granted else '0'
            )
            return True
        except Exception as e:
            print(f"❌ Redis cache error: {e}")
            return False

    def get_cached_permission(
        self,
        employee_id: int,
        permission_key: str
    ) -> Optional[bool]:
        """
        Get cached permission check result

        Args:
            employee_id: Employee ID
            permission_key: Permission key

        Returns:
            True/False if cached, None if not in cache
        """

        key = f"perm:{employee_id}:{permission_key}"
        try:
            value = self.client.get(key)
            if value is None:
                return None
            return value.decode() == '1'
        except Exception as e:
            print(f"❌ Redis cache error: {e}")
            return None

    def cache_employee_permissions(
        self,
        employee_id: int,
        permissions: Dict[str, Any]
    ) -> bool:
        """
        Cache all permissions for an employee

        Args:
            employee_id: Employee ID
            permissions: Dictionary of all permissions

        Returns:
            True if cached successfully
        """

        key = f"employee_permissions:{employee_id}"
        try:
            self.client.setex(
                key,
                self.permission_ttl,
                json.dumps(permissions)
            )
            return True
        except Exception as e:
            print(f"❌ Redis cache error: {e}")
            return False

    def get_cached_employee_permissions(
        self,
        employee_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get all cached permissions for an employee

        Args:
            employee_id: Employee ID

        Returns:
            Dictionary of permissions or None
        """

        key = f"employee_permissions:{employee_id}"
        try:
            value = self.client.get(key)
            if value is None:
                return None
            return json.loads(value.decode())
        except Exception as e:
            print(f"❌ Redis cache error: {e}")
            return None

    # ============================================================================
    # EMPLOYEE INFO CACHING (5-MINUTE TTL)
    # ============================================================================

    def cache_employee_info(
        self,
        employee_id: int,
        info: Dict[str, Any]
    ) -> bool:
        """
        Cache employee information (territory, team, etc.)

        Args:
            employee_id: Employee ID
            info: Employee information dictionary

        Returns:
            True if cached successfully
        """

        key = f"employee_info:{employee_id}"
        try:
            self.client.setex(
                key,
                self.employee_info_ttl,
                json.dumps(info)
            )
            return True
        except Exception as e:
            print(f"❌ Redis cache error: {e}")
            return False

    def get_cached_employee_info(
        self,
        employee_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached employee information

        Args:
            employee_id: Employee ID

        Returns:
            Employee info dictionary or None
        """

        key = f"employee_info:{employee_id}"
        try:
            value = self.client.get(key)
            if value is None:
                return None
            return json.loads(value.decode())
        except Exception as e:
            print(f"❌ Redis cache error: {e}")
            return None

    # ============================================================================
    # TEMPLATE CACHING (1-HOUR TTL)
    # ============================================================================

    def cache_permission_template(
        self,
        template_id: int,
        template: Dict[str, Any]
    ) -> bool:
        """
        Cache permission template

        Args:
            template_id: Template ID
            template: Template data dictionary

        Returns:
            True if cached successfully
        """

        key = f"template:{template_id}"
        try:
            self.client.setex(
                key,
                self.template_ttl,
                json.dumps(template)
            )
            return True
        except Exception as e:
            print(f"❌ Redis cache error: {e}")
            return False

    def get_cached_template(
        self,
        template_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached permission template

        Args:
            template_id: Template ID

        Returns:
            Template data or None
        """

        key = f"template:{template_id}"
        try:
            value = self.client.get(key)
            if value is None:
                return None
            return json.loads(value.decode())
        except Exception as e:
            print(f"❌ Redis cache error: {e}")
            return None

    # ============================================================================
    # CACHE INVALIDATION
    # ============================================================================

    def invalidate_employee_cache(self, employee_id: int) -> int:
        """
        Invalidate all cached data for an employee

        Args:
            employee_id: Employee ID

        Returns:
            Number of keys deleted
        """

        deleted_count = 0

        try:
            # Delete all permission keys for this employee
            pattern = f"perm:{employee_id}:*"
            for key in self.client.scan_iter(match=pattern):
                self.client.delete(key)
                deleted_count += 1

            # Delete employee permissions
            if self.client.delete(f"employee_permissions:{employee_id}"):
                deleted_count += 1

            # Delete employee info
            if self.client.delete(f"employee_info:{employee_id}"):
                deleted_count += 1

            print(f"✅ Invalidated {deleted_count} cache keys for employee {employee_id}")

        except Exception as e:
            print(f"❌ Redis cache invalidation error: {e}")

        return deleted_count

    def invalidate_template_cache(self, template_id: int) -> bool:
        """
        Invalidate cached template

        Args:
            template_id: Template ID

        Returns:
            True if deleted
        """

        try:
            deleted = self.client.delete(f"template:{template_id}")
            if deleted:
                print(f"✅ Invalidated template {template_id} cache")
            return bool(deleted)
        except Exception as e:
            print(f"❌ Redis cache error: {e}")
            return False

    def invalidate_all_permissions(self) -> int:
        """
        Invalidate ALL permission caches (use sparingly!)

        Returns:
            Number of keys deleted
        """

        deleted_count = 0

        try:
            # Delete all permission keys
            for pattern in ['perm:*', 'employee_permissions:*']:
                for key in self.client.scan_iter(match=pattern):
                    self.client.delete(key)
                    deleted_count += 1

            print(f"✅ Invalidated {deleted_count} permission cache keys")

        except Exception as e:
            print(f"❌ Redis cache invalidation error: {e}")

        return deleted_count

    def flush_all(self) -> bool:
        """
        Flush entire cache (use with extreme caution!)

        Returns:
            True if successful
        """

        try:
            self.client.flushdb()
            print("⚠️  Flushed entire Redis cache")
            return True
        except Exception as e:
            print(f"❌ Redis flush error: {e}")
            return False

    # ============================================================================
    # MATERIALIZED VIEW REFRESH COORDINATION
    # ============================================================================

    def mark_permissions_dirty(self) -> bool:
        """
        Mark permissions as dirty (needs materialized view refresh)

        Returns:
            True if marked successfully
        """

        try:
            self.client.set('permissions_dirty', '1')
            print("✅ Marked permissions as dirty")
            return True
        except Exception as e:
            print(f"❌ Redis error: {e}")
            return False

    def is_permissions_dirty(self) -> bool:
        """
        Check if permissions materialized view needs refresh

        Returns:
            True if dirty
        """

        try:
            value = self.client.get('permissions_dirty')
            return value is not None and value.decode() == '1'
        except Exception as e:
            print(f"❌ Redis error: {e}")
            return False

    def clear_permissions_dirty(self) -> bool:
        """
        Clear dirty flag after refreshing materialized view

        Returns:
            True if cleared successfully
        """

        try:
            self.client.delete('permissions_dirty')
            print("✅ Cleared permissions dirty flag")
            return True
        except Exception as e:
            print(f"❌ Redis error: {e}")
            return False

    # ============================================================================
    # STATISTICS & MONITORING
    # ============================================================================

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary of cache statistics
        """

        try:
            info = self.client.info('stats')
            keyspace = self.client.info('keyspace')

            return {
                'total_keys': sum(
                    keyspace.get(f'db{i}', {}).get('keys', 0)
                    for i in range(16)
                ),
                'hits': info.get('keyspace_hits', 0),
                'misses': info.get('keyspace_misses', 0),
                'hit_rate': self._calculate_hit_rate(
                    info.get('keyspace_hits', 0),
                    info.get('keyspace_misses', 0)
                ),
                'evicted_keys': info.get('evicted_keys', 0),
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_human': info.get('used_memory_human', 'N/A'),
            }
        except Exception as e:
            print(f"❌ Redis stats error: {e}")
            return {}

    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """Calculate cache hit rate percentage"""

        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)

    def get_permission_cache_count(self) -> int:
        """Get count of cached permissions"""

        try:
            count = 0
            for _ in self.client.scan_iter(match='perm:*'):
                count += 1
            return count
        except Exception as e:
            print(f"❌ Redis error: {e}")
            return 0

    # ============================================================================
    # HEALTH CHECK
    # ============================================================================

    def health_check(self) -> Dict[str, Any]:
        """
        Check Redis health

        Returns:
            Health status dictionary
        """

        try:
            # Ping test
            ping_success = self.client.ping()

            # Get info
            info = self.client.info('server')

            return {
                'healthy': ping_success,
                'redis_version': info.get('redis_version', 'unknown'),
                'uptime_seconds': info.get('uptime_in_seconds', 0),
                'cluster_mode': self.cluster_mode,
                'connected': True
            }
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'connected': False
            }


# ============================================================================
# MATERIALIZED VIEW REFRESH SCHEDULER
# ============================================================================

class MaterializedViewRefresher:
    """
    Background task to refresh materialized views when permissions change

    Run this as a background worker or cron job
    """

    def __init__(self, db: Session, redis_service: RedisCacheService):
        """
        Initialize refresher

        Args:
            db: Database session
            redis_service: Redis cache service
        """
        self.db = db
        self.redis_service = redis_service

    def refresh_if_needed(self) -> bool:
        """
        Check if refresh is needed and refresh materialized views

        Returns:
            True if refreshed, False if no refresh needed
        """

        # Check if permissions are dirty
        if not self.redis_service.is_permissions_dirty():
            return False

        print("🔄 Refreshing materialized views...")

        try:
            # Refresh permission cache view
            self.db.execute(text("""
                REFRESH MATERIALIZED VIEW CONCURRENTLY mv_employee_permissions_cache
            """))

            # Refresh audit log summary view
            self.db.execute(text("""
                REFRESH MATERIALIZED VIEW CONCURRENTLY mv_audit_log_summary
            """))

            self.db.commit()

            # Clear dirty flag
            self.redis_service.clear_permissions_dirty()

            # Invalidate all permission caches
            self.redis_service.invalidate_all_permissions()

            print("✅ Materialized views refreshed successfully")
            return True

        except Exception as e:
            print(f"❌ Materialized view refresh error: {e}")
            self.db.rollback()
            return False

    def schedule_refresh(self) -> bool:
        """
        Schedule a refresh for next run

        Returns:
            True if scheduled
        """

        return self.redis_service.mark_permissions_dirty()


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == '__main__':
    """
    Example usage and testing
    """

    # Initialize Redis cache
    redis_cache = RedisCacheService()

    # Health check
    health = redis_cache.health_check()
    print(f"Redis Health: {health}")

    # Cache a permission
    redis_cache.cache_permission(123, 'leads.view_all', True)

    # Get cached permission
    granted = redis_cache.get_cached_permission(123, 'leads.view_all')
    print(f"Permission cached: {granted}")

    # Get cache stats
    stats = redis_cache.get_cache_stats()
    print(f"Cache Stats: {stats}")

    # Invalidate employee cache
    redis_cache.invalidate_employee_cache(123)
