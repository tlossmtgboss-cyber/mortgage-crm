# backend/chat_system_bootstrap.py
"""
Chat System Bootstrap Module

Initializes and configures all chat system components for production:
- Circuit breaker for AI API resilience
- Response caching for cost optimization
- Message deduplication for reliability
- Graceful degradation for high availability
- Structured logging for observability
- Rate limiting for abuse prevention

Usage in main.py:
    from chat_system_bootstrap import ChatSystemBootstrap

    # During app startup
    chat_system = ChatSystemBootstrap(app)
    await chat_system.initialize()

    # During app shutdown
    await chat_system.shutdown()
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Any
from dataclasses import dataclass
import redis.asyncio as redis
from sqlalchemy.orm import Session

from middleware.structured_logging import StructuredLogger, setup_structured_logging
try:
    from middleware.rate_limiting import setup_rate_limiting, AdaptiveRateLimiter
except ImportError:
    setup_rate_limiting = None
    AdaptiveRateLimiter = None
from services.circuit_breaker import CircuitBreaker, AIServiceWithCircuitBreaker
from services.graceful_degradation import GracefulDegradation
from services.response_cache import ResponseCache
from services.message_deduplication import MessageDeduplicator
from services.session_recovery import SessionRecoveryService
from services.conversation_quality import ConversationQualityAnalyzer
from services.chat_realtime_monitoring import RealtimeMonitor

logger = logging.getLogger(__name__)


@dataclass
class ChatSystemComponents:
    """Container for all chat system components."""
    redis_client: Optional[redis.Redis] = None
    circuit_breaker: Optional[CircuitBreaker] = None
    ai_service: Optional[AIServiceWithCircuitBreaker] = None
    degradation: Optional[GracefulDegradation] = None
    response_cache: Optional[ResponseCache] = None
    deduplicator: Optional[MessageDeduplicator] = None
    session_recovery: Optional[SessionRecoveryService] = None
    quality_analyzer: Optional[ConversationQualityAnalyzer] = None
    realtime_monitor: Optional[RealtimeMonitor] = None
    structured_logger: Optional[StructuredLogger] = None


class ChatSystemBootstrap:
    """
    Bootstrap and manage all chat system components.

    Provides a unified interface for initializing and managing
    the chat system's production infrastructure.
    """

    def __init__(
        self,
        app: Any,
        redis_url: str = "redis://localhost:6379/0",
        db_session_factory: Any = None,
        anthropic_client: Any = None,
    ):
        """
        Initialize chat system bootstrap.

        Args:
            app: FastAPI application instance
            redis_url: Redis connection URL
            db_session_factory: SQLAlchemy session factory
            anthropic_client: Anthropic API client (optional)
        """
        self.app = app
        self.redis_url = redis_url
        self.db_session_factory = db_session_factory
        self.anthropic_client = anthropic_client

        self.components = ChatSystemComponents()
        self._initialized = False

        # Configuration
        self.config = {
            "circuit_breaker": {
                "failure_threshold": 5,
                "recovery_timeout": 30,
                "timeout": 30.0,
            },
            "rate_limiting": {
                "enabled": True,
            },
            "caching": {
                "enabled": True,
                "default_ttl": 3600,
            },
        }

    async def initialize(self) -> ChatSystemComponents:
        """
        Initialize all chat system components.

        Returns:
            ChatSystemComponents with all initialized services
        """
        logger.info("Initializing Perennia Chat System...")

        # 1. Initialize structured logging
        self.components.structured_logger = StructuredLogger("perennia.chat")
        setup_structured_logging(self.app)

        self.components.structured_logger.logger.info(
            "Chat system initialization started",
            extra={"event_type": "chat_system_init_start"}
        )

        # 2. Initialize Redis
        try:
            self.components.redis_client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self.components.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Continuing without Redis.")
            self.components.redis_client = None

        # 3. Initialize Circuit Breaker
        self.components.circuit_breaker = CircuitBreaker(
            name="anthropic_api",
            **self.config["circuit_breaker"]
        )
        logger.info("Circuit breaker initialized")

        # 4. Initialize AI Service with circuit breaker
        if self.anthropic_client:
            self.components.ai_service = AIServiceWithCircuitBreaker(
                anthropic_client=self.anthropic_client,
                circuit_breaker=self.components.circuit_breaker
            )
            logger.info("AI service with circuit breaker initialized")

        # 5. Initialize Response Cache
        if self.components.redis_client:
            self.components.response_cache = ResponseCache(
                self.components.redis_client
            )
            logger.info("Response cache initialized")

        # 6. Initialize Message Deduplicator
        if self.components.redis_client:
            self.components.deduplicator = MessageDeduplicator(
                self.components.redis_client
            )
            logger.info("Message deduplicator initialized")

        # 7. Initialize Graceful Degradation
        if self.db_session_factory:
            db = self.db_session_factory()
            try:
                self.components.degradation = GracefulDegradation(
                    redis_client=self.components.redis_client,
                    db=db,
                    circuit_breaker=self.components.circuit_breaker
                )
                logger.info("Graceful degradation manager initialized")
            finally:
                db.close()

        # 8. Initialize Session Recovery
        if self.db_session_factory and self.components.redis_client:
            self.components.session_recovery = SessionRecoveryService(
                db=self.db_session_factory(),
                redis_client=self.components.redis_client
            )
            logger.info("Session recovery service initialized")

        # 9. Initialize Quality Analyzer
        self.components.quality_analyzer = ConversationQualityAnalyzer()
        logger.info("Quality analyzer initialized")

        # 10. Initialize Realtime Monitor
        if self.db_session_factory:
            self.components.realtime_monitor = RealtimeMonitor(
                db=self.db_session_factory()
            )
            logger.info("Realtime monitor initialized")

        # 11. Setup Rate Limiting
        if self.components.redis_client and self.config["rate_limiting"]["enabled"] and setup_rate_limiting:
            setup_rate_limiting(self.app, self.components.redis_client)
            logger.info("Rate limiting middleware enabled")

        # 12. Store components in app state
        self.app.state.chat_system = self.components

        # 13. Run initial health check
        await self._run_health_check()

        self._initialized = True

        self.components.structured_logger.logger.info(
            "Chat system initialization complete",
            extra={
                "event_type": "chat_system_init_complete",
                "redis_available": self.components.redis_client is not None,
                "ai_service_available": self.components.ai_service is not None,
            }
        )

        return self.components

    async def _run_health_check(self):
        """Run initial health check on all components."""
        health = {
            "redis": False,
            "circuit_breaker": "closed",
            "degradation_level": "unknown"
        }

        # Check Redis
        if self.components.redis_client:
            try:
                await self.components.redis_client.ping()
                health["redis"] = True
            except Exception as e:
                logger.exception(f"Redis health check ping failed: {e}")
                health["redis"] = False

        # Check circuit breaker
        if self.components.circuit_breaker:
            health["circuit_breaker"] = self.components.circuit_breaker.state.value

        # Check degradation level
        if self.components.degradation:
            try:
                capabilities = await self.components.degradation.get_capabilities()
                health["degradation_level"] = capabilities['level']
            except Exception as e:
                logger.warning(f"Degradation check failed: {e}")

        logger.info(f"Health check complete: {health}")
        return health

    async def shutdown(self):
        """Shutdown all chat system components gracefully."""
        logger.info("Shutting down chat system...")

        if self.components.structured_logger:
            self.components.structured_logger.logger.info(
                "Chat system shutdown initiated",
                extra={"event_type": "chat_system_shutdown"}
            )

        # Close Redis connection
        if self.components.redis_client:
            try:
                await self.components.redis_client.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.warning(f"Error closing Redis: {e}")

        self._initialized = False
        logger.info("Chat system shutdown complete")

    def get_components(self) -> ChatSystemComponents:
        """Get initialized components."""
        if not self._initialized:
            raise RuntimeError("Chat system not initialized. Call initialize() first.")
        return self.components

    async def get_system_status(self) -> dict:
        """Get current system status."""
        status = {
            "initialized": self._initialized,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if self._initialized:
            # Get circuit breaker status
            if self.components.circuit_breaker:
                status["circuit_breaker"] = self.components.circuit_breaker.get_status()

            # Get degradation status
            if self.components.degradation:
                try:
                    capabilities = await self.components.degradation.get_capabilities()
                    status["service_level"] = capabilities['level']
                    status["capabilities"] = capabilities['capabilities']
                except Exception as e:
                    status["degradation_error"] = str(e)

            # Get cache stats
            if self.components.response_cache:
                try:
                    cache_stats = await self.components.response_cache.get_stats()
                    status["cache"] = cache_stats
                except Exception as e:
                    status["cache_error"] = str(e)

            # Get monitoring stats
            if self.components.realtime_monitor:
                try:
                    monitor_stats = self.components.realtime_monitor.get_dashboard_summary()
                    status["monitoring"] = monitor_stats
                except Exception as e:
                    status["monitoring_error"] = str(e)

        return status


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def integrate_chat_system(app: Any, db_session_factory: Any, redis_url: str):
    """
    Helper function to integrate chat system into existing FastAPI app.

    Usage in main.py:
        from chat_system_bootstrap import integrate_chat_system

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # ... existing startup code ...

            # Initialize chat system
            chat_bootstrap = integrate_chat_system(
                app=app,
                db_session_factory=get_db,
                redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0")
            )
            await chat_bootstrap.initialize()

            yield

            # Shutdown chat system
            await chat_bootstrap.shutdown()
    """
    return ChatSystemBootstrap(
        app=app,
        redis_url=redis_url,
        db_session_factory=db_session_factory
    )


# =============================================================================
# DEPENDENCY INJECTION HELPERS
# =============================================================================

def get_chat_components(request) -> ChatSystemComponents:
    """
    FastAPI dependency to get chat components.

    Usage:
        @router.post("/messages")
        async def send_message(
            components: ChatSystemComponents = Depends(get_chat_components)
        ):
            cache = components.response_cache
    """
    return request.app.state.chat_system


def get_response_cache(request) -> Optional[ResponseCache]:
    """Get response cache from app state."""
    components = getattr(request.app.state, 'chat_system', None)
    return components.response_cache if components else None


def get_deduplicator(request) -> Optional[MessageDeduplicator]:
    """Get message deduplicator from app state."""
    components = getattr(request.app.state, 'chat_system', None)
    return components.deduplicator if components else None


def get_circuit_breaker(request) -> Optional[CircuitBreaker]:
    """Get circuit breaker from app state."""
    components = getattr(request.app.state, 'chat_system', None)
    return components.circuit_breaker if components else None


def get_quality_analyzer(request) -> ConversationQualityAnalyzer:
    """Get quality analyzer from app state."""
    components = getattr(request.app.state, 'chat_system', None)
    if components and components.quality_analyzer:
        return components.quality_analyzer
    return ConversationQualityAnalyzer()
