"""Base class and shared dataclass for provider adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


def parse_ts(v: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp string into a datetime, handling Z suffix."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        s = str(v)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@dataclass
class NormalizedCall:
    """Provider-agnostic call record."""

    external_call_id: str
    provider: str
    direction: str = "inbound"

    phone_from: Optional[str] = None
    phone_to: Optional[str] = None

    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None

    transcript: Optional[str] = None
    recording_url: Optional[str] = None

    raw_payload: dict[str, Any] = field(default_factory=dict)

    # Speaker-diarized messages: [{"role": "user"|"assistant", "content": "..."}]
    messages: list[dict[str, str]] = field(default_factory=list)


class ProviderAdapter(ABC):
    """Validates a webhook request and normalizes its payload."""

    @abstractmethod
    def validate_signature(
        self, body: bytes, headers: dict[str, str], secret: str,
    ) -> None:
        """Raise ValueError if signature verification fails."""

    @abstractmethod
    def normalize(self, payload: dict[str, Any]) -> NormalizedCall:
        """Convert a raw webhook payload into a NormalizedCall."""
