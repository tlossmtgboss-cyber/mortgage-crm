"""
ModelRouter — Intent-driven multi-model selection for the agent fleet.

Wave 6 / Slice E (D3 closeout). Different intents have very different
compute and reasoning requirements. Burning Opus on a greeting or status
check is wasteful; running an underwriting decision through Haiku is
risky. This router maps the classified intent (or an explicit complexity
hint) to one of the three production Claude tiers per CLAUDE.md naming:

* ``claude-opus-4-7``           — high-stakes / complex reasoning
* ``claude-sonnet-4-6``         — balanced workhorse (default)
* ``claude-haiku-4-5-20251001`` — cheap/fast simple turns

Env override
------------
For cost tuning without a deploy, the router honours per-intent overrides
of the form ``INTENT_MODEL_OVERRIDE_<INTENT_NAME>=<model_id>``. The
intent name is uppercased and stripped of non-alphanumerics; the value
is returned as-is so an ops engineer can swap (e.g.)
``INTENT_MODEL_OVERRIDE_UNDERWRITING_DECISION=claude-sonnet-4-6`` to fall
back from Opus to Sonnet during a price spike.

Public surface
--------------
``ModelRouter.select_model(intent, complexity_hint="auto", agent_role=None)``
``ModelRouter.estimate_cost(intent, input_tokens, output_tokens)``

Both methods always return a primitive (``str`` / ``float``) so callers
can pass the result directly to the Anthropic SDK or to governance
metrics without enum unwrapping.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Production model IDs (per CLAUDE.md naming convention)
# ---------------------------------------------------------------------------
MODEL_OPUS = "claude-opus-4-7"
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_HAIKU = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Intent -> model routing table.
# Keys are uppercase intent strings. Any intent not in the table falls
# through to the balanced default (Sonnet).
# ---------------------------------------------------------------------------
HIGH_COMPLEXITY_INTENTS = frozenset({
    "UNDERWRITING_DECISION",
    "COMPLIANCE_REVIEW",
    "LOAN_STRUCTURING",
    "COMPLEX_ANALYSIS",
})

MEDIUM_COMPLEXITY_INTENTS = frozenset({
    "LEAD_NURTURE",
    "EMAIL_DRAFT",
    "TASK_PRIORITIZATION",
    "PIPELINE_ANALYSIS",
    "RATE_ANALYSIS",
})

LOW_COMPLEXITY_INTENTS = frozenset({
    "GREETING",
    "GENERAL_QUERY",
    "FAQ",
    "STATUS_CHECK",
    "ACKNOWLEDGEMENT",
})

DEFAULT_MODEL = MODEL_SONNET

# ---------------------------------------------------------------------------
# Per-1K-token pricing — mirrors governance_metrics._PRICING_PER_1K_TOKENS
# but keyed by *all* model IDs the router can return (including the
# Haiku snapshot suffix). Kept here so the router has no hard runtime
# dep on the governance buffer module.
# ---------------------------------------------------------------------------
_PRICING_PER_1K_TOKENS: Dict[str, Dict[str, float]] = {
    MODEL_OPUS:   {"input": 0.015,   "output": 0.075},
    MODEL_SONNET: {"input": 0.003,   "output": 0.015},
    MODEL_HAIKU:  {"input": 0.00080, "output": 0.0040},
    # Snapshot-free Haiku alias kept for parity with governance_metrics.
    "claude-haiku-4-5": {"input": 0.00080, "output": 0.0040},
    "_default": {"input": 0.003, "output": 0.015},
}


_NON_ALNUM_RE = re.compile(r"[^A-Z0-9]+")


def _normalize_intent(intent: Optional[str]) -> str:
    if not intent:
        return ""
    return _NON_ALNUM_RE.sub("_", str(intent).upper()).strip("_")


class ModelRouter:
    """Stateless model selector. Cheap to instantiate; safe to share."""

    def select_model(
        self,
        intent: str,
        complexity_hint: str = "auto",
        agent_role: Optional[str] = None,
    ) -> str:
        """Return the Anthropic model ID to use for this turn.

        Resolution order:
        1. ``INTENT_MODEL_OVERRIDE_<INTENT>`` env var (highest priority).
        2. Explicit ``complexity_hint`` of ``"high"`` / ``"low"``.
        3. Intent routing table (HIGH / MEDIUM / LOW).
        4. Default Sonnet.
        """
        normalized = _normalize_intent(intent)

        # 1. Env override always wins.
        if normalized:
            env_key = f"INTENT_MODEL_OVERRIDE_{normalized}"
            override = os.getenv(env_key)
            if override:
                logger.debug("ModelRouter: env override %s=%s", env_key, override)
                return override

        # 2. Explicit complexity hint short-circuits the table.
        hint = (complexity_hint or "auto").lower().strip()
        if hint == "high":
            return MODEL_OPUS
        if hint == "low":
            return MODEL_HAIKU
        # "auto" or anything unrecognised falls through to the table.

        # 3. Intent table lookup.
        if normalized in HIGH_COMPLEXITY_INTENTS:
            return MODEL_OPUS
        if normalized in MEDIUM_COMPLEXITY_INTENTS:
            return MODEL_SONNET
        if normalized in LOW_COMPLEXITY_INTENTS:
            return MODEL_HAIKU

        # 4. Default to balanced workhorse.
        return DEFAULT_MODEL

    def estimate_cost(
        self,
        intent: str,
        input_tokens: int,
        output_tokens: int,
        complexity_hint: str = "auto",
        agent_role: Optional[str] = None,
    ) -> float:
        """Estimate USD cost for a turn at this intent's chosen model."""
        model = self.select_model(
            intent, complexity_hint=complexity_hint, agent_role=agent_role
        )
        rate = _PRICING_PER_1K_TOKENS.get(model, _PRICING_PER_1K_TOKENS["_default"])
        try:
            in_cost = (max(0, int(input_tokens)) / 1000.0) * float(rate.get("input", 0.0))
            out_cost = (max(0, int(output_tokens)) / 1000.0) * float(rate.get("output", 0.0))
        except (TypeError, ValueError):
            return 0.0
        return round(in_cost + out_cost, 6)


# Module-level singleton for cheap reuse.
model_router = ModelRouter()


__all__ = [
    "ModelRouter",
    "model_router",
    "MODEL_OPUS",
    "MODEL_SONNET",
    "MODEL_HAIKU",
    "HIGH_COMPLEXITY_INTENTS",
    "MEDIUM_COMPLEXITY_INTENTS",
    "LOW_COMPLEXITY_INTENTS",
    "DEFAULT_MODEL",
]
