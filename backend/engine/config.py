"""Engine configuration — all env vars use the CIE_ prefix."""
from __future__ import annotations

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CIESettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CIE_", env_file=".env", extra="ignore")

    ENABLED: bool = False

    # LLM
    PRIMARY_MODEL: str = "claude-sonnet-4-6"
    FAST_MODEL: str = "claude-haiku-4-5-20251001"

    # Provider webhooks
    VAPI_WEBHOOK_SECRET: str = ""
    TELNYX_WEBHOOK_SECRET: str = ""

    # Pipeline
    WORKER_CONCURRENCY: int = 4
    MIN_ANALYZABLE_SECONDS: int = 25
    PIPELINE_TIMEOUT_S: int = 120

    # Scoring weights (must sum to 1.0)
    SCORE_WEIGHTS: dict[str, float] = Field(default_factory=lambda: {
        "engagement": 0.15,
        "information_quality": 0.20,
        "objection_handling": 0.20,
        "compliance": 0.15,
        "rapport": 0.15,
        "closing_effectiveness": 0.15,
    })

    # Two-party consent states (recording disclosure required)
    TWO_PARTY_CONSENT_STATES: list[str] = Field(default_factory=lambda: [
        "CA", "CT", "FL", "IL", "MD", "MA", "MI", "MT", "NV", "NH", "OR", "PA", "WA",
    ])

    # Auth (for read endpoints — inherits platform JWT by default)
    JWT_PUBLIC_KEY: Optional[str] = None


cie_settings = CIESettings()
