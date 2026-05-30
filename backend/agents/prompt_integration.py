#!/usr/bin/env python3
"""
Prompt Integration Service - Production-ready prompt optimization service.

This module provides:
- In-memory caching with TTL
- Performance monitoring and metrics
- API integration helpers
- Optional FastAPI routes
"""

import time
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from functools import wraps

from .prompt_loader import (
    PromptLoader,
    CachedPromptLoader,
    LoadContext,
    ContextPresets,
    PerenniaContexts,
    LoadedPrompt
)


@dataclass
class CacheEntry:
    """Entry in the prompt cache with TTL."""
    prompt: LoadedPrompt
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0


@dataclass
class PerformanceMetrics:
    """Performance metrics for prompt loading."""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_load_time_ms: float = 0
    total_chars_served: int = 0
    requests_by_context: Dict[str, int] = field(default_factory=dict)
    char_reductions: List[float] = field(default_factory=list)


class OptimizedPromptService:
    """
    Production-ready service for optimized prompt loading.

    Features:
    - TTL-based caching
    - Thread-safe operations
    - Performance monitoring
    - Multiple context presets
    """

    def __init__(
        self,
        prompts_dir: str,
        cache_ttl_seconds: int = 300,
        max_cache_entries: int = 100,
        enable_cache: bool = True
    ):
        """
        Initialize the service.

        Args:
            prompts_dir: Directory containing split prompts
            cache_ttl_seconds: Time-to-live for cache entries
            max_cache_entries: Maximum number of cached prompts
            enable_cache: Whether to enable caching
        """
        self._loader = PromptLoader(prompts_dir)
        self._cache: Dict[str, CacheEntry] = {}
        self._cache_lock = threading.RLock()
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._max_cache_entries = max_cache_entries
        self._enable_cache = enable_cache
        self._metrics = PerformanceMetrics()
        self._original_chars = self._loader.get_stats().get('total_characters', 0)

    def get_system_prompt(self, context: LoadContext) -> str:
        """
        Get optimized system prompt for the given context.

        Args:
            context: LoadContext specifying what to load

        Returns:
            Combined prompt content string
        """
        start_time = time.time()
        cache_key = context.to_cache_key()

        # Update metrics
        self._metrics.total_requests += 1
        context_name = self._get_context_name(context)
        self._metrics.requests_by_context[context_name] = \
            self._metrics.requests_by_context.get(context_name, 0) + 1

        # Check cache
        if self._enable_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                self._metrics.cache_hits += 1
                self._metrics.total_chars_served += cached.total_chars
                return cached.content

        self._metrics.cache_misses += 1

        # Load prompt
        result = self._loader.load_prompt(context)

        # Calculate reduction
        if self._original_chars > 0:
            reduction = (1 - (result.total_chars / self._original_chars)) * 100
            self._metrics.char_reductions.append(reduction)

        # Update metrics
        load_time = (time.time() - start_time) * 1000
        self._metrics.total_load_time_ms += load_time
        self._metrics.total_chars_served += result.total_chars

        # Cache result
        if self._enable_cache:
            self._add_to_cache(cache_key, result)

        return result.content

    def get_prompt_with_metadata(self, context: LoadContext) -> Dict[str, Any]:
        """
        Get prompt with full metadata.

        Args:
            context: LoadContext specifying what to load

        Returns:
            Dictionary with content and metadata
        """
        start_time = time.time()
        cache_key = context.to_cache_key()

        # Check cache
        if self._enable_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                return {
                    'content': cached.content,
                    'sections': cached.sections_loaded,
                    'char_count': cached.total_chars,
                    'section_count': cached.total_sections,
                    'cache_hit': True,
                    'load_time_ms': 0
                }

        # Load prompt
        result = self._loader.load_prompt(context)
        load_time = (time.time() - start_time) * 1000

        # Cache result
        if self._enable_cache:
            self._add_to_cache(cache_key, result)

        return {
            'content': result.content,
            'sections': result.sections_loaded,
            'char_count': result.total_chars,
            'section_count': result.total_sections,
            'cache_hit': False,
            'load_time_ms': round(load_time, 2)
        }

    def _get_from_cache(self, cache_key: str) -> Optional[LoadedPrompt]:
        """Get entry from cache if valid."""
        with self._cache_lock:
            if cache_key not in self._cache:
                return None

            entry = self._cache[cache_key]

            # Check TTL
            if datetime.now() - entry.created_at > self._cache_ttl:
                del self._cache[cache_key]
                return None

            # Update access time and count
            entry.last_accessed = datetime.now()
            entry.access_count += 1

            return entry.prompt

    def _add_to_cache(self, cache_key: str, prompt: LoadedPrompt):
        """Add entry to cache."""
        with self._cache_lock:
            # Evict old entries if at capacity
            if len(self._cache) >= self._max_cache_entries:
                self._evict_oldest()

            self._cache[cache_key] = CacheEntry(
                prompt=prompt,
                created_at=datetime.now(),
                last_accessed=datetime.now(),
                access_count=1
            )

    def _evict_oldest(self):
        """Evict the oldest/least used cache entry."""
        if not self._cache:
            return

        # Find least recently accessed
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed
        )
        del self._cache[oldest_key]

    def _get_context_name(self, context: LoadContext) -> str:
        """Get a human-readable name for the context."""
        if context.domain:
            return f"domain:{context.domain}"
        if context.needs_agent:
            return "agent"
        if context.needs_tools:
            return "tools"
        if context.needs_memory:
            return "conversational"
        return "minimal"

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        total = self._metrics.cache_hits + self._metrics.cache_misses
        hit_rate = (self._metrics.cache_hits / total * 100) if total > 0 else 0
        avg_load_time = (self._metrics.total_load_time_ms / total) if total > 0 else 0
        avg_reduction = sum(self._metrics.char_reductions) / len(self._metrics.char_reductions) \
            if self._metrics.char_reductions else 0

        return {
            'total_requests': self._metrics.total_requests,
            'cache_stats': {
                'hits': self._metrics.cache_hits,
                'misses': self._metrics.cache_misses,
                'hit_rate': round(hit_rate, 1),
                'entries': len(self._cache)
            },
            'avg_load_time_ms': round(avg_load_time, 2),
            'total_chars_served': self._metrics.total_chars_served,
            'avg_reduction_percent': round(avg_reduction, 1),
            'requests_by_context': self._metrics.requests_by_context,
            'original_prompt_chars': self._original_chars
        }

    def clear_cache(self):
        """Clear the prompt cache."""
        with self._cache_lock:
            self._cache.clear()

    def reset_metrics(self):
        """Reset performance metrics."""
        self._metrics = PerformanceMetrics()

    def warm_cache(self, contexts: Optional[List[LoadContext]] = None):
        """
        Pre-warm the cache with common contexts.

        Args:
            contexts: List of contexts to warm. Defaults to common presets.
        """
        if contexts is None:
            contexts = [
                ContextPresets.minimal(),
                ContextPresets.conversational(),
                ContextPresets.mortgage_crm(),
                ContextPresets.tool_use(),
                ContextPresets.agent_orchestration()
            ]

        for context in contexts:
            self.get_system_prompt(context)

    def list_sections(self) -> List[Dict]:
        """List all available sections."""
        return self._loader.list_sections()


# ============================================================================
# API Integration Helpers
# ============================================================================

def create_anthropic_message(
    service: OptimizedPromptService,
    context: LoadContext,
    user_message: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4096
) -> Dict[str, Any]:
    """
    Create a message payload for the Anthropic API.

    Args:
        service: OptimizedPromptService instance
        context: LoadContext for prompt selection
        user_message: The user's message
        model: Claude model to use
        max_tokens: Maximum response tokens

    Returns:
        Dictionary ready for Anthropic API
    """
    system_prompt = service.get_system_prompt(context)

    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_message}
        ]
    }


def create_openai_compatible_messages(
    service: OptimizedPromptService,
    context: LoadContext,
    user_message: str
) -> List[Dict[str, str]]:
    """
    Create messages array for OpenAI-compatible APIs.

    Args:
        service: OptimizedPromptService instance
        context: LoadContext for prompt selection
        user_message: The user's message

    Returns:
        List of message dictionaries
    """
    system_prompt = service.get_system_prompt(context)

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]


# ============================================================================
# FastAPI Integration (Optional)
# ============================================================================

def create_fastapi_routes(service: OptimizedPromptService):
    """
    Create FastAPI routes for the prompt service.

    Usage:
        from fastapi import FastAPI
        from prompt_integration import OptimizedPromptService, create_fastapi_routes

        app = FastAPI()
        service = OptimizedPromptService('./prompts')
        routes = create_fastapi_routes(service)
        app.include_router(routes)
    """
    try:
        from fastapi import APIRouter, Query
        from pydantic import BaseModel
    except ImportError:
        raise ImportError("FastAPI and Pydantic required. Install with: pip install fastapi pydantic")

    router = APIRouter(prefix="/prompts", tags=["prompts"])

    class PromptRequest(BaseModel):
        context_type: str = "conversational"
        domain: Optional[str] = None
        needs_tools: bool = False
        needs_memory: bool = False
        needs_search: bool = False
        needs_agent: bool = False
        tags: List[str] = []

    class PromptResponse(BaseModel):
        content: str
        sections: List[str]
        char_count: int
        section_count: int
        cache_hit: bool
        load_time_ms: float

    @router.get("/stats")
    async def get_stats():
        """Get performance statistics."""
        return service.get_performance_stats()

    @router.get("/sections")
    async def list_sections():
        """List all available sections."""
        return service.list_sections()

    @router.post("/load", response_model=PromptResponse)
    async def load_prompt(request: PromptRequest):
        """Load a prompt with custom context."""
        # Map preset names
        preset_map = {
            "minimal": ContextPresets.minimal,
            "conversational": ContextPresets.conversational,
            "mortgage": ContextPresets.mortgage_crm,
            "tools": ContextPresets.tool_use,
            "agent": ContextPresets.agent_orchestration,
            "full": ContextPresets.full
        }

        if request.context_type in preset_map:
            context = preset_map[request.context_type]()
        else:
            context = LoadContext(
                domain=request.domain,
                needs_tools=request.needs_tools,
                needs_memory=request.needs_memory,
                needs_search=request.needs_search,
                needs_agent=request.needs_agent,
                tags=request.tags
            )

        result = service.get_prompt_with_metadata(context)
        return PromptResponse(**result)

    @router.post("/clear-cache")
    async def clear_cache():
        """Clear the prompt cache."""
        service.clear_cache()
        return {"status": "cache cleared"}

    @router.post("/warm-cache")
    async def warm_cache():
        """Pre-warm the cache with common contexts."""
        service.warm_cache()
        return {"status": "cache warmed", "entries": len(service._cache)}

    return router


# ============================================================================
# Convenience Functions
# ============================================================================

# Module-level cached service (initialized on first use)
_cached_service: Optional[OptimizedPromptService] = None


def _get_service() -> OptimizedPromptService:
    """Get or create the cached prompt service."""
    global _cached_service
    if _cached_service is None:
        import os
        # Auto-detect prompts directory
        prompts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'perennia-prompts')
        if not os.path.exists(prompts_dir):
            prompts_dir = './perennia-prompts'
        _cached_service = OptimizedPromptService(prompts_dir, enable_cache=True)
    return _cached_service


# =============================================================================
# Simple One-Line Getters (cached, ready to use)
# =============================================================================

def get_receptionist_prompt() -> str:
    """Get AI Receptionist prompt - voice interactions, greeting, routing."""
    return _get_service().get_system_prompt(PerenniaContexts.receptionist())


def get_pipeline_prompt() -> str:
    """Get Pipeline Analyst prompt - data queries, metrics, analytics."""
    return _get_service().get_system_prompt(PerenniaContexts.pipeline_analyst())


def get_loan_processor_prompt() -> str:
    """Get Loan Processor prompt - full CRM, compliance, documents."""
    return _get_service().get_system_prompt(PerenniaContexts.loan_processor())


def get_lead_manager_prompt() -> str:
    """Get Lead Manager prompt - CRM, follow-up, scoring, outreach."""
    return _get_service().get_system_prompt(PerenniaContexts.lead_manager())


def get_email_prompt() -> str:
    """Get Email Intelligence prompt - parsing, sentiment, routing."""
    return _get_service().get_system_prompt(PerenniaContexts.email_intelligence())


def get_briefing_prompt() -> str:
    """Get Daily Briefing prompt - lead coaching, priorities."""
    return _get_service().get_system_prompt(PerenniaContexts.daily_briefing())


def get_market_prompt() -> str:
    """Get Market Intelligence prompt - rates, lock/float, trends."""
    return _get_service().get_system_prompt(PerenniaContexts.market_intelligence())


def get_general_prompt() -> str:
    """Get General Purpose prompt - balanced context for mixed queries."""
    return _get_service().get_system_prompt(PerenniaContexts.general())


def get_minimal_prompt() -> str:
    """Get Minimal prompt - core identity only, lowest token usage."""
    return _get_service().get_system_prompt(ContextPresets.minimal())


def get_full_prompt() -> str:
    """Get Full prompt - everything loaded."""
    return _get_service().get_system_prompt(ContextPresets.full())


# =============================================================================
# Ultra-Minimal Specialized Getters (lowest token usage)
# =============================================================================

def get_email_minimal_prompt() -> str:
    """Ultra-minimal for simple email parsing - no tools, no CRM complexity."""
    context = LoadContext(
        domain="email",
        needs_tools=False,
        needs_memory=False,
        needs_search=False,
        needs_agent=False,
        tags=['identity', 'communication']  # Only core + communication
    )
    return _get_service().get_system_prompt(context)


def get_voice_only_prompt() -> str:
    """Just voice handling - no CRM tools, minimal complexity."""
    context = LoadContext(
        domain="voice",
        needs_tools=False,
        needs_memory=False,
        needs_agent=False,
        tags=['identity', 'communication', 'domain']  # Voice-specific only
    )
    return _get_service().get_system_prompt(context)


def get_greeting_prompt() -> str:
    """Ultra-minimal for greetings - fastest possible response."""
    context = LoadContext(
        needs_tools=False,
        needs_memory=False,
        needs_search=False,
        needs_agent=False,
        tags=['identity']  # Absolute minimum
    )
    return _get_service().get_system_prompt(context)


def get_task_only_prompt() -> str:
    """Task management only - no lead/pipeline complexity."""
    context = LoadContext(
        needs_tools=True,
        needs_memory=False,
        tags=['identity', 'tools', 'workflow']
    )
    return _get_service().get_system_prompt(context)


def get_optimized_prompt(
    prompts_dir: str,
    context_type: str = "conversational",
    **kwargs
) -> str:
    """
    Convenience function to get an optimized prompt.

    Args:
        prompts_dir: Directory containing split prompts
        context_type: One of: minimal, conversational, mortgage, tools, agent, full
        **kwargs: Additional LoadContext parameters

    Returns:
        Optimized prompt string
    """
    service = OptimizedPromptService(prompts_dir)

    preset_map = {
        "minimal": ContextPresets.minimal,
        "conversational": ContextPresets.conversational,
        "mortgage": ContextPresets.mortgage_crm,
        "tools": ContextPresets.tool_use,
        "agent": ContextPresets.agent_orchestration,
        "full": ContextPresets.full
    }

    if context_type in preset_map:
        context = preset_map[context_type]()
    else:
        context = LoadContext(**kwargs)

    return service.get_system_prompt(context)


# ============================================================================
# Demo
# ============================================================================

def main():
    """Demo the integration service."""
    import argparse

    parser = argparse.ArgumentParser(description='Optimized Prompt Service Demo')
    parser.add_argument('prompts_dir', help='Directory containing split prompts')
    parser.add_argument('--benchmark', action='store_true', help='Run performance benchmark')

    args = parser.parse_args()

    # Initialize service
    print("Initializing OptimizedPromptService...")
    service = OptimizedPromptService(args.prompts_dir, enable_cache=True)

    if args.benchmark:
        print("\n=== Performance Benchmark ===\n")

        # Test each context preset
        contexts = [
            ("minimal", ContextPresets.minimal()),
            ("conversational", ContextPresets.conversational()),
            ("mortgage_crm", ContextPresets.mortgage_crm()),
            ("tool_use", ContextPresets.tool_use()),
            ("agent", ContextPresets.agent_orchestration()),
            ("full", ContextPresets.full())
        ]

        print(f"{'Context':<20} {'Sections':<10} {'Chars':<12} {'Time (ms)':<12} {'Cache':<8}")
        print("-" * 70)

        for name, context in contexts:
            start = time.time()
            result = service.get_prompt_with_metadata(context)
            elapsed = (time.time() - start) * 1000

            print(f"{name:<20} {result['section_count']:<10} {result['char_count']:<12,} {elapsed:<12.2f} {'hit' if result['cache_hit'] else 'miss':<8}")

        # Run again to show cache hits
        print("\n=== Second Pass (cached) ===\n")

        for name, context in contexts:
            start = time.time()
            result = service.get_prompt_with_metadata(context)
            elapsed = (time.time() - start) * 1000

            print(f"{name:<20} {result['section_count']:<10} {result['char_count']:<12,} {elapsed:<12.2f} {'hit' if result['cache_hit'] else 'miss':<8}")

        # Show stats
        print("\n=== Performance Stats ===\n")
        stats = service.get_performance_stats()
        print(f"Total Requests: {stats['total_requests']}")
        print(f"Cache Hit Rate: {stats['cache_stats']['hit_rate']}%")
        print(f"Avg Load Time: {stats['avg_load_time_ms']}ms")
        print(f"Avg Reduction: {stats['avg_reduction_percent']}%")
        print(f"Original Chars: {stats['original_prompt_chars']:,}")
    else:
        # Simple demo
        print("\n=== Simple Demo ===\n")

        context = ContextPresets.conversational()
        prompt = service.get_system_prompt(context)

        print(f"Loaded prompt: {len(prompt):,} characters")
        print(f"\nPreview (first 300 chars):")
        print("-" * 40)
        print(prompt[:300] + "..." if len(prompt) > 300 else prompt)

        print("\n=== Stats ===")
        stats = service.get_performance_stats()
        print(f"Cache entries: {stats['cache_stats']['entries']}")
        print(f"Reduction: {stats['avg_reduction_percent']}%")


if __name__ == '__main__':
    main()
