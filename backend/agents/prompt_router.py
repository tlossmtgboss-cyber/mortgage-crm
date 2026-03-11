#!/usr/bin/env python3
"""
Prompt Router - Automatically selects the most efficient prompt for each query.

This module analyzes incoming messages and routes them to the optimal
prompt context, maximizing token savings while maintaining response quality.

Usage:
    from prompt_router import route_to_optimal_prompt, smart_get_prompt

    # Get the optimal prompt for a message
    system_prompt = smart_get_prompt("Hi there!")  # Returns minimal greeting prompt
    system_prompt = smart_get_prompt("Show me my pipeline")  # Returns pipeline prompt
"""

import os
import re
import logging
from typing import Callable, Optional, Dict, Any

from .prompt_integration import (
    # Standard contexts
    get_receptionist_prompt,
    get_pipeline_prompt,
    get_loan_processor_prompt,
    get_lead_manager_prompt,
    get_email_prompt,
    get_briefing_prompt,
    get_market_prompt,
    get_general_prompt,
    get_minimal_prompt,
    get_full_prompt,
    # Ultra-minimal contexts
    get_greeting_prompt,
    get_email_minimal_prompt,
    get_voice_only_prompt,
    get_task_only_prompt,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Pattern Definitions
# =============================================================================

GREETING_PATTERNS = {
    'hi', 'hello', 'hey', 'good morning', 'good afternoon',
    'good evening', 'howdy', 'greetings', 'sup', 'yo', 'hiya',
    'whats up', "what's up", 'how are you', 'morning', 'afternoon'
}

SIMPLE_RESPONSES = {
    'thanks', 'thank you', 'ok', 'okay', 'got it', 'sounds good',
    'perfect', 'great', 'yes', 'no', 'yep', 'nope', 'sure',
    'bye', 'goodbye', 'see you', 'later', 'cool', 'nice'
}

# Keyword to prompt getter mapping
KEYWORD_ROUTES: Dict[tuple, Callable] = {
    # Email - check tools needed
    ('email', 'inbox', 'message'): 'email',

    # Voice/Phone
    ('call', 'phone', 'voice', 'dial', 'ring', 'spoke', 'talked'): 'voice',

    # Pipeline/Analytics
    ('pipeline', 'metrics', 'report', 'analytics', 'dashboard', 'stats'): 'pipeline',

    # Loan processing
    ('loan', 'application', 'underwriting', 'closing', 'funded', 'processing'): 'loan',

    # Lead management
    ('lead', 'leads', 'prospect', 'nurture', 'follow up', 'followup', 'contact'): 'lead',

    # Market/Rates
    ('rate', 'rates', 'market', 'pricing', 'lock', 'float', 'mbs', 'treasury'): 'market',

    # Daily briefing/priorities
    ('briefing', 'priority', 'priorities', 'today', 'urgent', 'morning brief'): 'briefing',

    # Task-focused
    ('task', 'tasks', 'create', 'schedule', 'reminder'): 'task',
}


# =============================================================================
# Detection Functions
# =============================================================================

def is_simple_greeting(message: str) -> bool:
    """Detect simple greetings that need minimal context."""
    # Strip punctuation and normalize
    cleaned = re.sub(r'[^\w\s]', '', message).strip().lower()
    words = cleaned.split()

    # Direct match
    if cleaned in GREETING_PATTERNS:
        return True

    # Short message with greeting word
    if len(words) <= 3 and any(g in cleaned for g in GREETING_PATTERNS):
        return True

    return False


def is_simple_response(message: str) -> bool:
    """Detect simple acknowledgments that need minimal context."""
    cleaned = re.sub(r'[^\w\s]', '', message).strip().lower()
    return cleaned in SIMPLE_RESPONSES or len(cleaned.split()) <= 2


def detect_category(message: str) -> str:
    """Detect the category of query based on keywords."""
    message_lower = message.lower()

    for keywords, category in KEYWORD_ROUTES.items():
        if any(kw in message_lower for kw in keywords):
            return category

    return 'general'


def needs_tools(message: str, category: str) -> bool:
    """Determine if the query requires tool access."""
    message_lower = message.lower()

    # Action words that typically need tools
    action_words = ['send', 'create', 'update', 'schedule', 'search',
                    'find', 'get', 'show', 'list', 'make']

    return any(word in message_lower for word in action_words)


# =============================================================================
# Main Router
# =============================================================================

def route_to_optimal_prompt(
    user_message: str,
    user_context: Optional[Dict[str, Any]] = None
) -> Callable[[], str]:
    """
    Automatically select the most efficient prompt getter for the query.

    Args:
        user_message: The user's input message
        user_context: Optional context (role, preferences, etc.)

    Returns:
        A callable that returns the optimal system prompt string
    """
    message_lower = user_message.lower().strip()

    # 1. Ultra-minimal for greetings (biggest savings!)
    if is_simple_greeting(message_lower):
        logger.debug(f"Routed to greeting_prompt: '{user_message[:30]}...'")
        return get_greeting_prompt

    # 2. Ultra-minimal for simple responses
    if is_simple_response(message_lower):
        logger.debug(f"Routed to minimal_prompt: '{user_message[:30]}...'")
        return get_minimal_prompt

    # 3. Detect category
    category = detect_category(user_message)
    has_tools = needs_tools(user_message, category)

    # 4. Route based on category and tool needs
    if category == 'email':
        if has_tools:
            logger.debug(f"Routed to email_prompt (with tools)")
            return get_email_prompt
        logger.debug(f"Routed to email_minimal_prompt")
        return get_email_minimal_prompt

    if category == 'voice':
        if has_tools or 'crm' in message_lower or 'update' in message_lower:
            logger.debug(f"Routed to receptionist_prompt (full)")
            return get_receptionist_prompt
        logger.debug(f"Routed to voice_only_prompt")
        return get_voice_only_prompt

    if category == 'pipeline':
        logger.debug(f"Routed to pipeline_prompt")
        return get_pipeline_prompt

    if category == 'loan':
        logger.debug(f"Routed to loan_processor_prompt")
        return get_loan_processor_prompt

    if category == 'lead':
        logger.debug(f"Routed to lead_manager_prompt")
        return get_lead_manager_prompt

    if category == 'market':
        logger.debug(f"Routed to market_prompt")
        return get_market_prompt

    if category == 'briefing':
        logger.debug(f"Routed to briefing_prompt")
        return get_briefing_prompt

    if category == 'task':
        logger.debug(f"Routed to task_only_prompt")
        return get_task_only_prompt

    # 5. Default to general
    logger.debug(f"Routed to general_prompt (default)")
    return get_general_prompt


def smart_get_prompt(
    user_message: str,
    user_context: Optional[Dict[str, Any]] = None
) -> str:
    """Get optimized prompt with INFO-level logging for production visibility"""
    getter = route_to_optimal_prompt(user_message, user_context)
    prompt = getter()

    # Log at INFO level for production visibility
    log_prompt_selection(
        user_message,
        getter.__name__,
        len(prompt)
    )

    return prompt


# =============================================================================
# Analytics & Logging
# =============================================================================

class PromptRoutingStats:
    """Track prompt routing statistics for optimization analysis."""

    def __init__(self):
        self.routes: Dict[str, int] = {}
        self.total_chars_saved = 0
        self.full_prompt_chars = 0

    def record(self, getter_name: str, prompt_chars: int, full_chars: int = 24187):
        """Record a routing decision."""
        self.routes[getter_name] = self.routes.get(getter_name, 0) + 1
        self.total_chars_saved += (full_chars - prompt_chars)
        self.full_prompt_chars = full_chars

    def get_stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        total_requests = sum(self.routes.values())
        return {
            'total_requests': total_requests,
            'routes': self.routes,
            'total_chars_saved': self.total_chars_saved,
            'avg_chars_saved': self.total_chars_saved / total_requests if total_requests > 0 else 0,
            'estimated_token_savings': self.total_chars_saved / 4,  # ~4 chars per token
        }


# Global stats tracker
_routing_stats = PromptRoutingStats()


def log_prompt_selection(
    user_message: str,
    getter_name: str,
    prompt_chars: int,
    full_chars: int = 24187
):
    """Log prompt selection for analysis."""
    _routing_stats.record(getter_name, prompt_chars, full_chars)

    savings_pct = ((full_chars - prompt_chars) / full_chars) * 100
    logger.info(
        f"[PROMPT_ROUTER] {getter_name}: {prompt_chars:,} chars "
        f"({savings_pct:.0f}% savings) | '{user_message[:40]}...'"
    )


def get_routing_stats() -> Dict[str, Any]:
    """Get accumulated routing statistics."""
    return _routing_stats.get_stats()


def reset_routing_stats():
    """Reset routing statistics."""
    global _routing_stats
    _routing_stats = PromptRoutingStats()


# =============================================================================
# Integration Helper
# =============================================================================

def handle_chat_request(
    user_message: str,
    client,  # Anthropic client
    user_context: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
    max_tokens: int = 2048,
    log_stats: bool = True
):
    """
    Smart prompt selection for chat requests.

    Args:
        user_message: The user's input
        client: Anthropic client instance
        user_context: Optional user context
        model: Model to use (defaults to ANTHROPIC_MODEL env var or claude-sonnet-4-20250514)
        max_tokens: Max response tokens
        log_stats: Whether to log routing stats

    Returns:
        Anthropic API response
    """
    if model is None:
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    # Route to optimal prompt
    prompt_getter = route_to_optimal_prompt(user_message, user_context)
    system_prompt = prompt_getter()

    # Log for analysis
    if log_stats:
        log_prompt_selection(
            user_message,
            prompt_getter.__name__,
            len(system_prompt)
        )

    # Make API call
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )

    return response


# =============================================================================
# CLI Demo
# =============================================================================

def main():
    """Demo the prompt router."""
    test_messages = [
        "Hi there!",
        "Hello, how are you?",
        "Thanks!",
        "Show me my pipeline",
        "What are my leads doing?",
        "Should I lock or float?",
        "Send an email to John",
        "Parse this email for me",
        "Who should I call today?",
        "What are my priorities?",
        "Create a task for follow-up",
        "How is my loan application going?",
        "What's the market looking like?",
    ]

    print("=" * 70)
    print("PROMPT ROUTER DEMO")
    print("=" * 70)
    print()

    full_chars = len(get_full_prompt())
    print(f"Full prompt size: {full_chars:,} chars")
    print()

    print(f"{'Message':<40} {'Route':<25} {'Chars':>8} {'Savings':>8}")
    print("-" * 85)

    for msg in test_messages:
        getter = route_to_optimal_prompt(msg)
        prompt = getter()
        savings = ((full_chars - len(prompt)) / full_chars) * 100

        display_msg = msg[:38] + ".." if len(msg) > 40 else msg
        print(f"{display_msg:<40} {getter.__name__:<25} {len(prompt):>8,} {savings:>7.0f}%")

    print()
    print("=" * 70)


if __name__ == '__main__':
    main()
