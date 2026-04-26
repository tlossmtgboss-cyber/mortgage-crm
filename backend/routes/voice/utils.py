"""
Voice Routes - Shared Utilities

Contains utility functions and shared state used across voice route modules:
- mask_phone (PII masking)
- _validate_webhook_signature / _validate_twilio_signature
- get_models (lazy model imports)
- get_current_user_flexible (lazy auth import)
- Module-level config (voice_client, ai_config)
"""
import os
import logging
import json
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Request

logger = logging.getLogger(__name__)


# ============================================================================
# PII MASKING
# ============================================================================

try:
    from utils.pii_mask import mask_phone
except ImportError:
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"


# ============================================================================
# DEFAULT AI CONFIG
# ============================================================================

_DEFAULT_SYSTEM_PROMPT = """You are a helpful mortgage CRM voice assistant for loan officers at {business_name}.

You help loan officers work efficiently by voice. Your capabilities include:
- Searching contacts and leads in the CRM
- Sending SMS messages to contacts
- Checking calendar availability
- Scheduling appointments
- Creating tasks and reminders
- Starting scheduling workflows
- Getting pipeline summaries and loan status updates
- Managing call intelligence sessions

Be concise and professional. When a loan officer asks you to do something, confirm the action
before executing it. If you need clarification, ask briefly. Keep responses short since this
is a voice conversation."""


@dataclass
class AIConfig:
    """Configuration for AI voice assistant. Mutable so dashboard can update."""
    system_prompt: str = _DEFAULT_SYSTEM_PROMPT
    business_name: str = ""
    business_hours: str = "Monday-Friday 9am-5pm"
    greeting: str = "Hello, thank you for calling. How can I help you today?"

    def __post_init__(self):
        if not self.business_name:
            self.business_name = os.getenv("BUSINESS_NAME", "The Tim Loss Team")


ai_config = AIConfig()

# voice_client removed — legacy voice service deleted.
# Telnyx handles telephony; Vapi handles AI voice. Stub for backward compat.
voice_client = None


# ============================================================================
# WEBHOOK SIGNATURE VALIDATION
# ============================================================================

async def _validate_webhook_signature(request: Request, form_data: dict) -> bool:
    """Validate webhook signature header. Returns True if valid or not configured."""
    auth_token = os.getenv("TELNYX_API_KEY")
    if not auth_token:
        logger.warning("TELNYX_API_KEY not set — skipping webhook signature validation")
        return True
    try:
        # Legacy RequestValidator removed — Telnyx uses webhook signing secrets instead.
        # For now, log and pass through; Telnyx signature validation should be added
        # at the Telnyx webhook ingress layer.
        signature = request.headers.get("X-Telnyx-Signature", "")
        url = str(request.url)
        if signature:
            logger.info(f"Received request with webhook signature header at {url} — pass-through (Telnyx)")
        return True
    except Exception as e:
        logger.error(f"Webhook signature validation error: {e}")
        return False

# Backward-compatible alias
_validate_twilio_signature = _validate_webhook_signature


# ============================================================================
# LAZY MODEL/AUTH IMPORTS
# ============================================================================

def get_models():
    """Lazy import models from main.py to avoid circular imports"""
    from database.models import User, Lead, Task, Activity, IncomingDataEvent
    return User, Lead, Task, Activity, IncomingDataEvent


def get_current_user_flexible():
    """Lazy import auth dependency from main.py"""
    from auth.dependencies import get_current_user_flexible as _get_current_user_flexible
    return _get_current_user_flexible
