"""Voice Provider Configuration — abstraction layer for STT/TTS provider selection.

Decouples the voice pipeline from specific providers (OpenAI Realtime, Deepgram, etc.)
so that providers can be swapped without modifying voice route code.

Finding H-9: STT/TTS provider tightly coupled — this module provides the abstraction.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VoiceProviderConfig:
    """Configuration for voice pipeline providers.

    Attributes:
        stt_provider: Speech-to-text provider (e.g., "openai", "deepgram", "google").
        tts_provider: Text-to-speech provider (e.g., "openai", "elevenlabs", "google", "deepgram").
        tts_voice: Voice ID or name for TTS (e.g., "alloy", "nova", "aura-asteria-en").
        model_name: LLM model used for realtime voice (e.g., "gpt-4o-realtime-preview").
        model_version: Specific model version string (e.g., "2024-12-17").
        stt_model: STT model variant (e.g., "nova-2" for Deepgram, "whisper-1" for OpenAI).
        stt_language: Language code for STT (e.g., "en-US").
        tts_speed: TTS playback speed multiplier (1.0 = normal).
    """

    stt_provider: str = "openai"
    tts_provider: str = "openai"
    tts_voice: str = "alloy"
    model_name: str = "gpt-4o-realtime-preview"
    model_version: str = "2024-12-17"
    stt_model: str = "nova-2"
    stt_language: str = "en-US"
    tts_speed: float = 1.0

    @property
    def realtime_url(self) -> str:
        """Get the WebSocket URL for the realtime model."""
        if self.stt_provider == "openai":
            version_suffix = f"-{self.model_version}" if self.model_version else ""
            return f"wss://api.openai.com/v1/realtime?model={self.model_name}{version_suffix}"
        elif self.stt_provider == "deepgram":
            return "wss://api.deepgram.com/v1/listen"
        return ""

    @property
    def full_model_id(self) -> str:
        """Get the full model identifier including version."""
        if self.model_version:
            return f"{self.model_name}-{self.model_version}"
        return self.model_name


# Default configuration — populated from environment variables
_default_config: Optional[VoiceProviderConfig] = None


def get_voice_config(organization_id: Optional[int] = None) -> VoiceProviderConfig:
    """Get voice provider configuration.

    Args:
        organization_id: Optional org ID for per-tenant overrides.
                         Currently unused; returns global defaults.
                         Future: look up org-specific provider preferences from DB.

    Returns:
        VoiceProviderConfig with provider settings.
    """
    global _default_config

    # TODO: Per-org overrides — query organization_settings table for voice provider prefs
    # if organization_id:
    #     org_config = _load_org_voice_config(organization_id)
    #     if org_config:
    #         return org_config

    if _default_config is None:
        _default_config = VoiceProviderConfig(
            stt_provider=os.getenv("VOICE_STT_PROVIDER", "openai"),
            tts_provider=os.getenv("VOICE_TTS_PROVIDER", "openai"),
            tts_voice=os.getenv("VOICE_TTS_VOICE", "alloy"),
            model_name=os.getenv("VOICE_MODEL_NAME", "gpt-4o-realtime-preview"),
            model_version=os.getenv("VOICE_MODEL_VERSION", "2024-12-17"),
            stt_model=os.getenv("VOICE_STT_MODEL", "nova-2"),
            stt_language=os.getenv("VOICE_STT_LANGUAGE", "en-US"),
            tts_speed=float(os.getenv("VOICE_TTS_SPEED", "1.0")),
        )
        logger.info(
            "Voice provider config initialized",
            extra={
                "stt_provider": _default_config.stt_provider,
                "tts_provider": _default_config.tts_provider,
                "tts_voice": _default_config.tts_voice,
                "model_name": _default_config.model_name,
                "model_version": _default_config.model_version,
            },
        )

    return _default_config


def reset_voice_config() -> None:
    """Reset cached config (useful for testing or dynamic reconfiguration)."""
    global _default_config
    _default_config = None
