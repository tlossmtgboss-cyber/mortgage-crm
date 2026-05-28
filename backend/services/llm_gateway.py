"""
Unified LLM Gateway

Single entry point for ALL LLM calls across the application.
Handles: model selection, prompt caching, temperature control,
retry logic, cost tracking, circuit breaking, and streaming.

Usage:
    from services.llm_gateway import llm_gateway

    # Simple call
    response = await llm_gateway.complete(
        intent="pipeline",
        system_prompt="You are Aria...",
        messages=[{"role": "user", "content": "How's my pipeline?"}],
    )

    # Streaming
    async for chunk in llm_gateway.stream(
        intent="email",
        system_prompt="You are Aria...",
        messages=[...],
    ):
        yield chunk

    # With explicit overrides
    response = await llm_gateway.complete(
        intent="compliance",
        system_prompt="...",
        messages=[...],
        model_override="claude-sonnet-4-6",
        temperature_override=0.0,
        max_tokens_override=2000,
    )
"""

import asyncio
import hashlib
import logging
import os
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import httpx
from anthropic import Anthropic, AsyncAnthropic

logger = logging.getLogger(__name__)


# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

class ModelTier(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    PREMIUM = "premium"


MODEL_REGISTRY = {
    "fast": "claude-haiku-4-5-20251001",
    "standard": "claude-sonnet-4-6",
    "premium": "claude-sonnet-4-6",
}


# =============================================================================
# TEMPERATURE PRESETS PER INTENT
# =============================================================================

INTENT_TEMPERATURE: Dict[str, float] = {
    # Deterministic — compliance-sensitive, factual lookups
    "compliance": 0.0,
    "rates": 0.0,
    "sla": 0.0,
    "documents": 0.1,
    "billing": 0.1,
    "integrations": 0.1,

    # Low creativity — data analysis, reporting
    "pipeline": 0.2,
    "leads": 0.2,
    "tasks": 0.2,
    "priorities": 0.2,
    "historical": 0.2,
    "reports": 0.2,
    "profit": 0.2,
    "operations": 0.2,
    "customer": 0.2,

    # Moderate — conversational, some creativity needed
    "greeting": 0.5,
    "simple": 0.3,
    "schedule": 0.3,
    "calls": 0.3,
    "coaching": 0.4,
    "notifications": 0.3,
    "onboarding": 0.4,

    # Higher creativity — content generation, drafting
    "email": 0.6,
    "content_marketing": 0.7,
    "compound": 0.4,
    "video": 0.3,

    # Default
    "general": 0.3,
}

# Intents that should use the fast (Haiku) model
FAST_INTENTS = frozenset({
    "greeting", "simple", "schedule", "coaching", "video",
    "calls", "sla", "documents", "notifications", "onboarding",
    "content_marketing", "customer", "tasks",
})

# Intents that need the standard (Sonnet) model
STANDARD_INTENTS = frozenset({
    "pipeline", "leads", "compliance", "compound", "rates",
    "historical", "priorities", "profit", "reports", "billing",
    "integrations", "email", "operations",
})


# =============================================================================
# CIRCUIT BREAKER (reuses pattern from orchestrator)
# =============================================================================

class _CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class _CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._state = _CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> _CircuitState:
        with self._lock:
            if self._state == _CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.cooldown_seconds:
                    self._state = _CircuitState.HALF_OPEN
            return self._state

    def allow_request(self) -> bool:
        return self.state != _CircuitState.OPEN

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._state = _CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_time = time.monotonic()
            if self._state == _CircuitState.HALF_OPEN:
                self._state = _CircuitState.OPEN
            elif self._consecutive_failures >= self.failure_threshold:
                self._state = _CircuitState.OPEN


# =============================================================================
# RESPONSE DATACLASS
# =============================================================================

@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cache_hit: bool = False
    temperature: float = 0.0
    intent: str = ""
    stop_reason: str = ""


# =============================================================================
# LLM GATEWAY
# =============================================================================

class LLMGateway:
    """
    Unified gateway for all LLM calls.

    Features:
    - Automatic model selection based on intent
    - Temperature control per intent
    - Prompt caching (cache_control: ephemeral) on all system prompts
    - Circuit breaker for resilience
    - Retry with model fallback (Sonnet fails → retry with Haiku)
    - Cost and latency logging
    - Streaming support
    """

    def __init__(self):
        self._sync_client: Optional[Anthropic] = None
        self._async_client: Optional[AsyncAnthropic] = None
        self._circuit_breaker = _CircuitBreaker(failure_threshold=5, cooldown_seconds=30.0)
        self._timeout = httpx.Timeout(300.0, connect=10.0)
        self._max_retries = 3

        # Metrics
        self._total_calls = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_latency_ms = 0.0
        self._total_cache_read_tokens = 0
        self._total_cache_creation_tokens = 0
        self._cache_hit_count = 0

    @property
    def sync_client(self) -> Anthropic:
        if self._sync_client is None:
            self._sync_client = Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                timeout=self._timeout,
                max_retries=self._max_retries,
            )
        return self._sync_client

    @property
    def async_client(self) -> AsyncAnthropic:
        if self._async_client is None:
            self._async_client = AsyncAnthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                timeout=self._timeout,
                max_retries=self._max_retries,
            )
        return self._async_client

    def _select_model(self, intent: str, model_override: Optional[str] = None) -> str:
        if model_override:
            return model_override
        if intent in FAST_INTENTS:
            return MODEL_REGISTRY["fast"]
        return MODEL_REGISTRY["standard"]

    def _select_temperature(self, intent: str, temperature_override: Optional[float] = None) -> float:
        if temperature_override is not None:
            return temperature_override
        return INTENT_TEMPERATURE.get(intent, 0.3)

    def _select_max_tokens(self, intent: str, max_tokens_override: Optional[int] = None) -> int:
        if max_tokens_override is not None:
            return max_tokens_override
        DATA_HEAVY = {"pipeline", "leads", "priorities", "tasks", "reports", "operations"}
        if intent in FAST_INTENTS:
            return 300
        elif intent in DATA_HEAVY:
            return 1500
        elif intent == "email":
            return 800
        return 600

    def _build_system_block(self, system_prompt: str) -> list:
        """Wrap system prompt with cache_control for Anthropic prompt caching."""
        return [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    async def complete(
        self,
        intent: str,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        *,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
        timeout: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """
        Make a single LLM completion call with all gateway features.

        Args:
            intent: Query intent (used for model/temperature selection)
            system_prompt: System prompt text (will be cached automatically)
            messages: Conversation messages
            model_override: Force a specific model
            temperature_override: Force a specific temperature
            max_tokens_override: Force specific max tokens
            timeout: Per-call timeout override
            metadata: Additional metadata for logging
        """
        if not self._circuit_breaker.allow_request():
            logger.warning("[LLM_GATEWAY] Circuit breaker OPEN — fast-failing")
            return LLMResponse(
                text="I'm having trouble connecting to my AI service right now. Please try again in a moment.",
                model="circuit_breaker",
                intent=intent,
            )

        model = self._select_model(intent, model_override)
        temperature = self._select_temperature(intent, temperature_override)
        max_tokens = self._select_max_tokens(intent, max_tokens_override)
        call_timeout = timeout or (8.0 if intent in FAST_INTENTS else 15.0)

        start = time.perf_counter()
        response = None
        error = None

        for attempt in range(2):
            try:
                response = await self.async_client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=self._build_system_block(system_prompt),
                    messages=messages,
                    timeout=call_timeout,
                )
                self._circuit_breaker.record_success()
                break
            except Exception as e:
                error = e
                if attempt == 0 and model != MODEL_REGISTRY["fast"]:
                    model = MODEL_REGISTRY["fast"]
                    max_tokens = min(max_tokens, 400)
                    logger.warning(f"[LLM_GATEWAY] {e.__class__.__name__}, retrying with {model}")
                    continue
                self._circuit_breaker.record_failure()
                break

        latency_ms = (time.perf_counter() - start) * 1000

        if response is None:
            logger.error(f"[LLM_GATEWAY] Failed after retries: {error}")
            return LLMResponse(
                text="I'm having trouble generating a response right now. Please try again.",
                model=model,
                latency_ms=latency_ms,
                intent=intent,
            )

        input_tokens = getattr(response.usage, "input_tokens", 0)
        output_tokens = getattr(response.usage, "output_tokens", 0)
        cache_read_tokens = getattr(response.usage, "cache_read_input_tokens", 0)
        cache_creation_tokens = getattr(response.usage, "cache_creation_input_tokens", 0)
        cache_hit = cache_read_tokens > 0

        # Update metrics
        self._total_calls += 1
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_latency_ms += latency_ms
        self._total_cache_read_tokens += cache_read_tokens
        self._total_cache_creation_tokens += cache_creation_tokens
        if cache_hit:
            self._cache_hit_count += 1

        result = LLMResponse(
            text=response.content[0].text.strip(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            temperature=temperature,
            intent=intent,
            stop_reason=response.stop_reason or "",
        )

        logger.info(
            f"[LLM_GATEWAY] intent={intent} model={model} temp={temperature:.1f} "
            f"tokens={input_tokens}+{output_tokens} latency={latency_ms:.0f}ms "
            f"cache_hit={cache_hit} cache_read={cache_read_tokens} cache_create={cache_creation_tokens}"
        )

        return result

    async def stream(
        self,
        intent: str,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        *,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream LLM response tokens. Yields text chunks as they arrive.

        Same model/temperature selection logic as complete().
        """
        if not self._circuit_breaker.allow_request():
            yield "I'm having trouble connecting right now. Please try again in a moment."
            return

        model = self._select_model(intent, model_override)
        temperature = self._select_temperature(intent, temperature_override)
        max_tokens = self._select_max_tokens(intent, max_tokens_override)

        try:
            async with self.async_client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=self._build_system_block(system_prompt),
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text

            self._circuit_breaker.record_success()
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error(f"[LLM_GATEWAY] Stream error: {e}")
            yield "I encountered an issue generating that response. Let me try again."

    def complete_sync(
        self,
        intent: str,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        *,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        """
        Synchronous version of complete() for non-async code paths.
        """
        if not self._circuit_breaker.allow_request():
            return LLMResponse(
                text="I'm having trouble connecting right now. Please try again in a moment.",
                model="circuit_breaker",
                intent=intent,
            )

        model = self._select_model(intent, model_override)
        temperature = self._select_temperature(intent, temperature_override)
        max_tokens = self._select_max_tokens(intent, max_tokens_override)
        call_timeout = timeout or (8.0 if intent in FAST_INTENTS else 15.0)

        start = time.perf_counter()
        response = None
        error = None

        for attempt in range(2):
            try:
                response = self.sync_client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=self._build_system_block(system_prompt),
                    messages=messages,
                    timeout=call_timeout,
                )
                self._circuit_breaker.record_success()
                break
            except Exception as e:
                error = e
                if attempt == 0 and model != MODEL_REGISTRY["fast"]:
                    model = MODEL_REGISTRY["fast"]
                    max_tokens = min(max_tokens, 400)
                    logger.warning(f"[LLM_GATEWAY] Sync {e.__class__.__name__}, retrying with {model}")
                    continue
                self._circuit_breaker.record_failure()
                break

        latency_ms = (time.perf_counter() - start) * 1000

        if response is None:
            logger.error(f"[LLM_GATEWAY] Sync failed: {error}")
            return LLMResponse(
                text="I'm having trouble generating a response. Please try again.",
                model=model,
                latency_ms=latency_ms,
                intent=intent,
            )

        input_tokens = getattr(response.usage, "input_tokens", 0)
        output_tokens = getattr(response.usage, "output_tokens", 0)
        cache_hit = getattr(response.usage, "cache_read_input_tokens", 0) > 0

        self._total_calls += 1
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_latency_ms += latency_ms

        logger.info(
            f"[LLM_GATEWAY] sync intent={intent} model={model} temp={temperature:.1f} "
            f"tokens={input_tokens}+{output_tokens} latency={latency_ms:.0f}ms"
        )

        return LLMResponse(
            text=response.content[0].text.strip(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            temperature=temperature,
            intent=intent,
            stop_reason=response.stop_reason or "",
        )

    def get_metrics(self) -> Dict[str, Any]:
        """Return gateway-level metrics for monitoring.

        Includes prompt caching stats: cache_hit_rate, total tokens saved
        via cache reads, and total tokens used for cache creation.
        """
        avg_latency = (
            self._total_latency_ms / self._total_calls
            if self._total_calls > 0 else 0
        )
        cache_hit_rate = (
            self._cache_hit_count / self._total_calls
            if self._total_calls > 0 else 0
        )
        return {
            "total_calls": self._total_calls,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "avg_latency_ms": round(avg_latency, 1),
            "circuit_breaker_state": self._circuit_breaker.state.value,
            # Prompt caching metrics
            "cache_hit_count": self._cache_hit_count,
            "cache_hit_rate": round(cache_hit_rate, 3),
            "total_cache_read_tokens": self._total_cache_read_tokens,
            "total_cache_creation_tokens": self._total_cache_creation_tokens,
        }


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_gateway: Optional[LLMGateway] = None


def get_llm_gateway() -> LLMGateway:
    """Get the global LLM gateway singleton."""
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway


# Convenience alias for direct import
llm_gateway = get_llm_gateway()
