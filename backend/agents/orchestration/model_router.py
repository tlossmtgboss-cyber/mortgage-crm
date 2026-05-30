"""
ModelRouter — single source for tier -> LLM client mapping.

Tiers:
  "haiku"  — classification/extraction/routing (cheap, fast)
  "sonnet" — open-ended reasoning and final responses

Model ids are env-tunable:
  ANTHROPIC_MODEL   (default claude-sonnet-4-6)
  ARIA_HAIKU_MODEL  (default claude-haiku-4-5-20251001)
"""
import os
import logging
from typing import Dict

from langchain_anthropic import ChatAnthropic

logger = logging.getLogger(__name__)

_SONNET_DEFAULT = "claude-sonnet-4-6"
_HAIKU_DEFAULT = "claude-haiku-4-5-20251001"


class ModelRouter:
    """Maps a tier name to a cached, configured ChatAnthropic client."""

    def __init__(self, temperature: float = 0.3, max_tokens: int = 1024):
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._cache: Dict[str, ChatAnthropic] = {}

    def _model_id(self, tier: str) -> str:
        if tier == "haiku":
            return os.getenv("ARIA_HAIKU_MODEL", _HAIKU_DEFAULT)
        if tier == "sonnet":
            return os.getenv("ANTHROPIC_MODEL", _SONNET_DEFAULT)
        raise ValueError(f"Unknown model tier: {tier!r} (expected 'haiku' or 'sonnet')")

    def get(self, tier: str) -> ChatAnthropic:
        if tier not in self._cache:
            model_id = self._model_id(tier)
            self._cache[tier] = ChatAnthropic(
                model=model_id,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            logger.info("[MODEL-ROUTER] tier=%s -> %s", tier, model_id)
        return self._cache[tier]


# Module-level shared router (mirrors the circuit-breaker singleton pattern).
_router = ModelRouter()


def get_model_router() -> ModelRouter:
    return _router
