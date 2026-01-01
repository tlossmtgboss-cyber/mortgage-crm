"""
Deep Health Check Service

Provides comprehensive health monitoring for:
- Database connectivity
- External service dependencies
- Cache availability
- Message queue health
- Storage systems

Enterprise Features:
- Deep vs shallow health checks
- Dependency health aggregation
- Automatic degraded mode detection
- Health history tracking
- Kubernetes-compatible probes
"""

import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import time

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status for a single component"""
    name: str
    status: HealthStatus
    message: str = ""
    latency_ms: float = 0
    last_check: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "latency_ms": round(self.latency_ms, 2),
            "last_check": self.last_check,
            "metadata": self.metadata,
        }


@dataclass
class HealthReport:
    """Aggregated health report"""
    status: HealthStatus
    components: List[ComponentHealth]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = "1.0.0"
    uptime_seconds: float = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "timestamp": self.timestamp,
            "version": self.version,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "components": [c.to_dict() for c in self.components],
        }


class HealthChecker:
    """Base class for health checkers"""

    async def check(self) -> ComponentHealth:
        raise NotImplementedError


class DatabaseHealthChecker(HealthChecker):
    """Check database connectivity and performance"""

    def __init__(self, db_session_factory, timeout_seconds: float = 5.0):
        self.db_session_factory = db_session_factory
        self.timeout = timeout_seconds

    async def check(self) -> ComponentHealth:
        start_time = time.time()

        try:
            from sqlalchemy import text

            with self.db_session_factory() as db:
                # Simple query to check connectivity
                result = db.execute(text("SELECT 1"))
                result.fetchone()

                # Check connection pool stats if available
                pool_stats = {}
                try:
                    engine = db.get_bind()
                    pool = engine.pool
                    pool_stats = {
                        "pool_size": pool.size(),
                        "checked_out": pool.checkedout(),
                        "overflow": pool.overflow(),
                    }
                except:
                    pass

            latency = (time.time() - start_time) * 1000

            # Degraded if slow
            status = HealthStatus.HEALTHY
            if latency > 1000:
                status = HealthStatus.DEGRADED

            return ComponentHealth(
                name="database",
                status=status,
                message="Database connection successful",
                latency_ms=latency,
                metadata=pool_stats,
            )

        except asyncio.TimeoutError:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message="Database connection timeout",
                latency_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000,
            )


class RedisHealthChecker(HealthChecker):
    """Check Redis connectivity"""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL")

    async def check(self) -> ComponentHealth:
        if not self.redis_url:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNKNOWN,
                message="Redis not configured",
            )

        start_time = time.time()

        try:
            import redis.asyncio as redis

            client = redis.from_url(self.redis_url)
            await client.ping()

            # Get info
            info = await client.info("memory")
            await client.close()

            latency = (time.time() - start_time) * 1000

            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Redis connection successful",
                latency_ms=latency,
                metadata={
                    "used_memory": info.get("used_memory_human", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                },
            )

        except Exception as e:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000,
            )


class ExternalAPIHealthChecker(HealthChecker):
    """Check external API connectivity"""

    def __init__(self, name: str, url: str, timeout_seconds: float = 5.0):
        self.name = name
        self.url = url
        self.timeout = timeout_seconds

    async def check(self) -> ComponentHealth:
        start_time = time.time()

        try:
            import httpx

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.url)

            latency = (time.time() - start_time) * 1000

            if response.status_code < 400:
                return ComponentHealth(
                    name=self.name,
                    status=HealthStatus.HEALTHY,
                    message=f"API responding (status {response.status_code})",
                    latency_ms=latency,
                )
            else:
                return ComponentHealth(
                    name=self.name,
                    status=HealthStatus.DEGRADED,
                    message=f"API returned status {response.status_code}",
                    latency_ms=latency,
                )

        except asyncio.TimeoutError:
            return ComponentHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message="API timeout",
                latency_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return ComponentHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"API error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000,
            )


class StorageHealthChecker(HealthChecker):
    """Check file storage connectivity (S3, etc.)"""

    def __init__(self, bucket_name: Optional[str] = None):
        self.bucket_name = bucket_name or os.getenv("AWS_S3_BUCKET")

    async def check(self) -> ComponentHealth:
        if not self.bucket_name:
            return ComponentHealth(
                name="storage",
                status=HealthStatus.UNKNOWN,
                message="S3 not configured",
            )

        start_time = time.time()

        try:
            import boto3

            s3 = boto3.client('s3')
            s3.head_bucket(Bucket=self.bucket_name)

            latency = (time.time() - start_time) * 1000

            return ComponentHealth(
                name="storage",
                status=HealthStatus.HEALTHY,
                message="S3 bucket accessible",
                latency_ms=latency,
                metadata={"bucket": self.bucket_name},
            )

        except Exception as e:
            return ComponentHealth(
                name="storage",
                status=HealthStatus.UNHEALTHY,
                message=f"S3 error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000,
            )


class DeepHealthCheck:
    """
    Deep Health Check Service

    Provides comprehensive health monitoring with:
    - Multiple component checks
    - Configurable timeouts
    - Health status aggregation
    - Kubernetes-compatible responses
    """

    def __init__(
        self,
        db_session_factory=None,
        redis_url: Optional[str] = None,
        external_apis: Optional[Dict[str, str]] = None,
    ):
        self._start_time = time.time()
        self._checkers: List[HealthChecker] = []
        self._last_report: Optional[HealthReport] = None
        self._health_history: List[HealthReport] = []
        self._max_history = 100

        # Add default checkers
        if db_session_factory:
            self._checkers.append(DatabaseHealthChecker(db_session_factory))

        if redis_url or os.getenv("REDIS_URL"):
            self._checkers.append(RedisHealthChecker(redis_url))

        if external_apis:
            for name, url in external_apis.items():
                self._checkers.append(ExternalAPIHealthChecker(name, url))

        # Add storage checker if configured
        if os.getenv("AWS_S3_BUCKET"):
            self._checkers.append(StorageHealthChecker())

    def add_checker(self, checker: HealthChecker):
        """Add a custom health checker"""
        self._checkers.append(checker)

    async def check_liveness(self) -> Dict[str, Any]:
        """
        Kubernetes liveness probe.

        Returns basic health - is the process alive?
        """
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def check_readiness(self) -> Dict[str, Any]:
        """
        Kubernetes readiness probe.

        Returns whether the service can accept traffic.
        Checks critical dependencies only.
        """
        # Check database only for readiness
        db_checker = next(
            (c for c in self._checkers if isinstance(c, DatabaseHealthChecker)),
            None
        )

        if db_checker:
            result = await db_checker.check()
            is_ready = result.status != HealthStatus.UNHEALTHY
        else:
            is_ready = True

        return {
            "status": "ready" if is_ready else "not_ready",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def check_all(self) -> HealthReport:
        """
        Deep health check of all components.

        Returns comprehensive health status.
        """
        # Run all checks concurrently
        tasks = [checker.check() for checker in self._checkers]
        components = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        results = []
        for i, component in enumerate(components):
            if isinstance(component, Exception):
                results.append(ComponentHealth(
                    name=f"checker_{i}",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(component)}",
                ))
            else:
                results.append(component)

        # Aggregate status
        statuses = [c.status for c in results]

        if HealthStatus.UNHEALTHY in statuses:
            overall_status = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall_status = HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses if s != HealthStatus.UNKNOWN):
            overall_status = HealthStatus.HEALTHY
        else:
            overall_status = HealthStatus.UNKNOWN

        # Create report
        report = HealthReport(
            status=overall_status,
            components=results,
            version=os.getenv("VERSION", "1.0.0"),
            uptime_seconds=time.time() - self._start_time,
        )

        # Store in history
        self._last_report = report
        self._health_history.append(report)
        if len(self._health_history) > self._max_history:
            self._health_history = self._health_history[-self._max_history:]

        return report

    def get_last_report(self) -> Optional[HealthReport]:
        """Get the most recent health report"""
        return self._last_report

    def get_health_history(self, limit: int = 10) -> List[HealthReport]:
        """Get recent health reports"""
        return self._health_history[-limit:]

    def get_uptime(self) -> float:
        """Get service uptime in seconds"""
        return time.time() - self._start_time


# FastAPI integration
def create_health_routes(health_check: DeepHealthCheck):
    """
    Create FastAPI health check routes.

    Usage:
        from fastapi import FastAPI
        from enterprise.observability.health import DeepHealthCheck, create_health_routes

        app = FastAPI()
        health = DeepHealthCheck(db_session_factory=get_db)
        app.include_router(create_health_routes(health))
    """
    from fastapi import APIRouter, Response

    router = APIRouter(tags=["health"])

    @router.get("/health")
    async def health():
        """Deep health check endpoint"""
        report = await health_check.check_all()
        status_code = 200 if report.status == HealthStatus.HEALTHY else 503
        return Response(
            content=str(report.to_dict()),
            status_code=status_code,
            media_type="application/json",
        )

    @router.get("/health/live")
    async def liveness():
        """Kubernetes liveness probe"""
        return await health_check.check_liveness()

    @router.get("/health/ready")
    async def readiness():
        """Kubernetes readiness probe"""
        result = await health_check.check_readiness()
        status_code = 200 if result["status"] == "ready" else 503
        return Response(
            content=str(result),
            status_code=status_code,
            media_type="application/json",
        )

    return router
