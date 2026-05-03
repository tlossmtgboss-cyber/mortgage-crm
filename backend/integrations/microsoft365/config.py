"""Microsoft 365 integration configuration."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MS365Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MS_",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Azure App Registration ────────────────────────────────────────────
    tenant_id: str = Field(default="common", description="Azure tenant ID or 'common'")
    client_id: str = Field(default="")
    client_secret: SecretStr = Field(default=SecretStr(""))
    redirect_uri: str = Field(default="https://api.perenniaai.com/api/v1/microsoft/oauth/callback")

    # ── Webhooks ──────────────────────────────────────────────────────────
    webhook_base_url: str = Field(
        default="https://api.perenniaai.com/api/v1/microsoft/webhooks",
        description="Public base URL for Graph notifications",
    )
    webhook_client_state: SecretStr = Field(
        default=SecretStr(""),
        description="HMAC secret used to validate incoming notifications",
    )
    webhook_renew_buffer_minutes: int = 30

    # ── Token vault ───────────────────────────────────────────────────────
    token_encryption_key: SecretStr = Field(
        default=SecretStr(""),
        description="32-byte base64 Fernet key for refresh-token encryption",
    )

    # ── Throttling / retry ────────────────────────────────────────────────
    graph_max_retries: int = 5
    graph_initial_backoff_ms: int = 250
    graph_max_backoff_ms: int = 8000

    # ── Reconciliation ────────────────────────────────────────────────────
    auto_link_threshold: float = 0.85
    suggest_threshold: float = 0.60
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # ── Subscription expiry windows (per Graph documentation) ─────────────
    sub_max_minutes_calendar: int = 4230
    sub_max_minutes_messages: int = 4230
    sub_max_minutes_chats: int = 4230
    sub_max_minutes_call_records: int = 4230

    # ── Loan number patterns ─────────────────────────────────────────────
    loan_number_patterns: list[str] = Field(
        default_factory=lambda: [
            r"\bRCA\d{10}\b",
            r"\bRCA\*?\d{4,10}\b",
            r"\bLoan\s*#?\s*(\d{6,12})\b",
            r"\b(\d{10,12})\b",
        ]
    )


@lru_cache
def get_settings() -> MS365Settings:
    """Singleton accessor."""
    return MS365Settings()  # type: ignore[call-arg]


# ── Graph scopes (delegated) ─────────────────────────────────────────────
GRAPH_SCOPES: list[str] = [
    "offline_access",
    "User.Read",
    "Calendars.ReadWrite",
    "Mail.Read",
    "Chat.Read",
    "MailboxSettings.Read",
]

GRAPH_AUTHORITY = "https://login.microsoftonline.com"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


# ── Subscription kinds we manage ─────────────────────────────────────────
SubscriptionKind = Literal["calendar", "email", "teams_chats", "call_records"]

SUBSCRIPTION_RESOURCES: dict[SubscriptionKind, str] = {
    "calendar": "/me/events",
    "email": "/me/messages",
    "teams_chats": "/me/chats/getAllMessages",
    "call_records": "/communications/callRecords",
}

SUBSCRIPTION_CHANGE_TYPES: dict[SubscriptionKind, str] = {
    "calendar": "created,updated,deleted",
    "email": "created,updated",
    "teams_chats": "created",
    "call_records": "created",
}
