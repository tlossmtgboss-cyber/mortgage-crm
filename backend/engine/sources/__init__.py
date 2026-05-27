"""Provider adapters — normalize webhook payloads into a common shape."""
from __future__ import annotations

from .base import ProviderAdapter, NormalizedCall
from .vapi import VapiAdapter
from .telnyx import TelnyxAdapter

_ADAPTERS: dict[str, type[ProviderAdapter]] = {
    "vapi": VapiAdapter,
    "telnyx": TelnyxAdapter,
}


def get_adapter(provider: str) -> ProviderAdapter:
    cls = _ADAPTERS.get(provider.lower())
    if cls is None:
        raise ValueError(f"Unknown provider: {provider}")
    return cls()
