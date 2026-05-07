"""
Graceful Degradation Manager

Manages system degradation when dependencies fail:
- Detects service health issues
- Determines available capabilities
- Provides user-facing status messages
- Enables fallback behaviors

Service Levels:
- FULL: All features working
- DEGRADED: AI limited/cached, core features work
- MINIMAL: Calls only, no AI chat
- MAINTENANCE: System down for maintenance
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, List
import redis
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class ServiceLevel(Enum):
    """System service levels"""
    FULL = "full"               # All features working
    DEGRADED = "degraded"       # AI cached/limited, calls work
    MINIMAL = "minimal"         # Calls only, no AI
    MAINTENANCE = "maintenance" # System down


class ServiceHealth:
    """Health status of individual services"""
    def __init__(
        self,
        name: str,
        healthy: bool,
        latency_ms: Optional[float] = None,
        error: Optional[str] = None
    ):
        self.name = name
        self.healthy = healthy
        self.latency_ms = latency_ms
        self.error = error
        self.checked_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'healthy': self.healthy,
            'latency_ms': self.latency_ms,
            'error': self.error,
            'checked_at': self.checked_at.isoformat()
        }


class GracefulDegradation:
    """
    Manage system degradation gracefully when dependencies fail.

    Usage:
        degradation = GracefulDegradation(redis_client, db_session)
        capabilities = await degradation.get_capabilities()

        if capabilities['capabilities']['chat']:
            # Process chat normally
        else:
            # Show degraded UI
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        db: Optional[Session] = None,
        circuit_breaker: Optional[Any] = None
    ):
        self.redis = redis_client
        self.db = db
        self.circuit_breaker = circuit_breaker
        self._cached_level: Optional[ServiceLevel] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = 10  # seconds

    async def check_service_health(self) -> Dict[str, ServiceHealth]:
        """Check health of all dependencies"""
        health = {}

        # Check AI API (via circuit breaker)
        health['ai_api'] = await self._check_ai_health()

        # Check Database
        health['database'] = await self._check_db_health()

        # Check Redis
        health['redis'] = await self._check_redis_health()

        # Check Telnyx (SMS/direct telephony)
        health['telnyx'] = await self._check_telnyx_health()

        # Check Vapi (AI voice calls)
        health['vapi'] = await self._check_vapi_health()

        return health

    async def determine_service_level(self) -> ServiceLevel:
        """Determine current service level based on health checks"""
        # Use cached level if recent
        if self._cached_level and self._cache_time:
            age = (datetime.now(timezone.utc) - self._cache_time).total_seconds()
            if age < self._cache_ttl:
                return self._cached_level

        health = await self.check_service_health()

        # Telephony is healthy if either Telnyx (SMS) or Vapi (voice) is up
        telephony_healthy = health['telnyx'].healthy or health['vapi'].healthy

        # All healthy = FULL
        if all(h.healthy for h in health.values()):
            level = ServiceLevel.FULL

        # Database and telephony healthy = DEGRADED (can do calls, cached AI)
        elif health['database'].healthy and telephony_healthy:
            level = ServiceLevel.DEGRADED

        # Only telephony healthy = MINIMAL (calls only)
        elif telephony_healthy:
            level = ServiceLevel.MINIMAL

        # Nothing working = MAINTENANCE
        else:
            level = ServiceLevel.MAINTENANCE

        # Cache result
        self._cached_level = level
        self._cache_time = datetime.now(timezone.utc)

        return level

    async def get_capabilities(self) -> Dict[str, Any]:
        """Get current system capabilities based on health"""
        level = await self.determine_service_level()
        health = await self.check_service_health()

        capabilities = {
            ServiceLevel.FULL: {
                'chat': True,
                'ai_responses': True,
                'click_to_call': True,
                'scheduling': True,
                'analytics': True,
                'session_recovery': True,
            },
            ServiceLevel.DEGRADED: {
                'chat': True,
                'ai_responses': False,  # Cached responses only
                'click_to_call': True,
                'scheduling': True,
                'analytics': False,
                'session_recovery': True,
            },
            ServiceLevel.MINIMAL: {
                'chat': False,
                'ai_responses': False,
                'click_to_call': True,
                'scheduling': True,  # Can still schedule via simple form
                'analytics': False,
                'session_recovery': False,
            },
            ServiceLevel.MAINTENANCE: {
                'chat': False,
                'ai_responses': False,
                'click_to_call': False,
                'scheduling': False,
                'analytics': False,
                'session_recovery': False,
            }
        }

        return {
            'level': level.value,
            'capabilities': capabilities[level],
            'health': {name: h.to_dict() for name, h in health.items()},
            'message': self._get_user_message(level),
            'actions': self._get_recommended_actions(level),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

    def _get_user_message(self, level: ServiceLevel) -> Optional[str]:
        """Get user-facing message for current service level"""
        messages = {
            ServiceLevel.FULL: None,  # No message needed
            ServiceLevel.DEGRADED: (
                "We're experiencing high demand. "
                "You can still connect with Tim via phone or schedule a call."
            ),
            ServiceLevel.MINIMAL: (
                "Our chat system is temporarily unavailable. "
                "Click 'Call Now' to speak with Tim directly, "
                "or schedule a callback."
            ),
            ServiceLevel.MAINTENANCE: (
                "We're performing scheduled maintenance. "
                "Please check back in a few minutes, "
                "or call us directly at (843) 555-1234."
            )
        }
        return messages.get(level)

    def _get_recommended_actions(self, level: ServiceLevel) -> List[Dict[str, str]]:
        """Get recommended user actions for current level"""
        actions = {
            ServiceLevel.FULL: [],
            ServiceLevel.DEGRADED: [
                {'type': 'call', 'label': 'Call Tim Now', 'priority': 'high'},
                {'type': 'schedule', 'label': 'Schedule a Call', 'priority': 'medium'},
            ],
            ServiceLevel.MINIMAL: [
                {'type': 'call', 'label': 'Call Tim Now', 'priority': 'high'},
                {'type': 'schedule', 'label': 'Schedule a Callback', 'priority': 'high'},
            ],
            ServiceLevel.MAINTENANCE: [
                {'type': 'phone', 'label': 'Call (843) 555-1234', 'priority': 'high'},
                {'type': 'retry', 'label': 'Try Again Later', 'priority': 'medium'},
            ]
        }
        return actions.get(level, [])

    async def _check_ai_health(self) -> ServiceHealth:
        """Check if AI API is healthy"""
        import time
        start = time.time()

        try:
            # Check circuit breaker state if available
            if self.circuit_breaker:
                status = self.circuit_breaker.get_status()
                if status['state'] == 'open':
                    return ServiceHealth(
                        name='ai_api',
                        healthy=False,
                        error='Circuit breaker open'
                    )

            # Could make lightweight API call here
            latency = (time.time() - start) * 1000
            return ServiceHealth(name='ai_api', healthy=True, latency_ms=latency)

        except Exception as e:
            return ServiceHealth(name='ai_api', healthy=False, error=str(e))

    async def _check_db_health(self) -> ServiceHealth:
        """Check database health"""
        import time
        start = time.time()

        if not self.db:
            return ServiceHealth(name='database', healthy=False, error='No DB connection')

        try:
            self.db.execute(text("SELECT 1"))
            latency = (time.time() - start) * 1000
            return ServiceHealth(name='database', healthy=True, latency_ms=latency)

        except SQLAlchemyError as e:
            return ServiceHealth(name='database', healthy=False, error=str(e))

    async def _check_redis_health(self) -> ServiceHealth:
        """Check Redis health"""
        import time
        start = time.time()

        if not self.redis:
            return ServiceHealth(name='redis', healthy=False, error='No Redis connection')

        try:
            self.redis.ping()
            latency = (time.time() - start) * 1000
            return ServiceHealth(name='redis', healthy=True, latency_ms=latency)

        except redis.RedisError as e:
            return ServiceHealth(name='redis', healthy=False, error=str(e))

    async def _check_telnyx_health(self) -> ServiceHealth:
        """Check Telnyx API health (lightweight credential validation)"""
        import time
        start = time.time()

        telnyx_key = __import__("os").getenv("TELNYX_API_KEY")
        if not telnyx_key:
            return ServiceHealth(name='telnyx', healthy=False, error='TELNYX_API_KEY not configured')

        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://api.telnyx.com/v2/messaging_profiles",
                    headers={"Authorization": f"Bearer {telnyx_key}"},
                    params={"page[size]": 1},
                )
            latency = (time.time() - start) * 1000
            healthy = resp.status_code == 200
            error = None if healthy else f"HTTP {resp.status_code}"
            return ServiceHealth(name='telnyx', healthy=healthy, latency_ms=latency, error=error)
        except Exception as e:
            return ServiceHealth(name='telnyx', healthy=False, error=str(e))

    async def _check_vapi_health(self) -> ServiceHealth:
        """Check Vapi API health (lightweight assistant list)"""
        import time
        start = time.time()

        vapi_key = __import__("os").getenv("VAPI_API_KEY")
        if not vapi_key:
            return ServiceHealth(name='vapi', healthy=False, error='VAPI_API_KEY not configured')

        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://api.vapi.ai/assistant",
                    headers={"Authorization": f"Bearer {vapi_key}"},
                    params={"limit": 1},
                )
            latency = (time.time() - start) * 1000
            healthy = resp.status_code == 200
            error = None if healthy else f"HTTP {resp.status_code}"
            return ServiceHealth(name='vapi', healthy=healthy, latency_ms=latency, error=error)
        except Exception as e:
            return ServiceHealth(name='vapi', healthy=False, error=str(e))

    def force_level(self, level: ServiceLevel):
        """Force a specific service level (for maintenance windows)"""
        self._cached_level = level
        self._cache_time = datetime.now(timezone.utc)
        self._cache_ttl = 3600  # Force for 1 hour
        logger.warning(f"Service level forced to {level.value}")

    def clear_forced_level(self):
        """Clear any forced service level"""
        self._cached_level = None
        self._cache_time = None
        self._cache_ttl = 10
        logger.info("Forced service level cleared")


# FastAPI endpoint helper
async def get_system_health(
    redis_client: redis.Redis,
    db: Session,
    circuit_breaker: Any = None
) -> Dict[str, Any]:
    """
    Get complete system health for API endpoint.

    Usage in FastAPI:
        @router.get("/api/v1/system/health")
        async def health_check(
            redis: redis.Redis = Depends(get_redis),
            db: Session = Depends(get_db)
        ):
            return await get_system_health(redis, db)
    """
    degradation = GracefulDegradation(redis_client, db, circuit_breaker)
    capabilities = await degradation.get_capabilities()

    return {
        "status": "operational" if capabilities['level'] == 'full' else "degraded",
        **capabilities
    }
