"""Central registry of Claude model IDs.

Single source of truth so a model upgrade is a one-line change here instead of
edits across ~100 files. Import these constants rather than hardcoding model
strings:

    from models_config import SONNET, HAIKU, OPUS

Tiers (current as of this writing):
  - HAIKU  — cheap/fast: routing, classification, extraction, simple replies
  - SONNET — default reasoning: chat, pipeline, compliance synthesis
  - OPUS   — hardest reasoning only: complex compliance, income/underwriting analysis

NOTE: Cost/pricing tables and governance enums intentionally reference other
(older) IDs for accounting/back-compat and are NOT meant to use these.
"""
from __future__ import annotations

import os

# --- canonical model IDs -----------------------------------------------------
HAIKU: str = "claude-haiku-4-5-20251001"
SONNET: str = "claude-sonnet-4-6"
OPUS: str = "claude-opus-4-8"

# Env override for the default chat/voice model (kept for back-compat with the
# existing ANTHROPIC_MODEL knob used by the agent service).
DEFAULT_MODEL: str = os.getenv("ANTHROPIC_MODEL", SONNET)

# Tier aliases used by the LLM gateway.
TIER_FAST: str = HAIKU
TIER_STANDARD: str = SONNET
TIER_PREMIUM: str = OPUS

__all__ = [
    "HAIKU",
    "SONNET",
    "OPUS",
    "DEFAULT_MODEL",
    "TIER_FAST",
    "TIER_STANDARD",
    "TIER_PREMIUM",
]
