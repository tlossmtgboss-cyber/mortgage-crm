"""
AI Agent Orchestration System

Enhanced prompt building, token optimization, and performance tracking
Based on "The Instant AI Agency" principles.

Key Features:
- Context-aware prompt loading (90k -> 12-18k tokens)
- One question at a time rule
- No conciliatory phrases
- Persistent engagement
- SPIN Selling & Challenger Sale methodologies
- Performance tracking and A/B testing
"""

from .context_manager import ContextManager
from .prompt_builder import AgentPromptBuilder, ConversationStyle, SalesMethodology
from .performance_tracker import PerformanceTracker
from .quality_analyzer import QualityAnalyzer
from .llm_circuit_breaker import LLMCircuitBreaker, CircuitState
from .config.agent_configs import AgentPersona, ConversationRules, QualificationCriteria

__all__ = [
    "ContextManager",
    "AgentPromptBuilder",
    "ConversationStyle",
    "SalesMethodology",
    "PerformanceTracker",
    "QualityAnalyzer",
    "LLMCircuitBreaker",
    "CircuitState",
    "AgentPersona",
    "ConversationRules",
    "QualificationCriteria",
]
