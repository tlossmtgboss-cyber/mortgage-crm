"""Pydantic v2 schemas for the Microsoft 365 integration API surface."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import (
    CalendarSyncDirection,
    ReconciliationLinkType,
    ReconciliationStatus,
    SubscriptionKind,
)


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── OAuth ───────────────────────────────────────────────────────────────


class OAuthInitResponse(_Base):
    authorization_url: str
    state: str


class OAuthCallbackRequest(_Base):
    code: str
    state: str


# ── Account status ──────────────────────────────────────────────────────


class MSAccountStatus(_Base):
    id: int
    upn: str
    display_name: str | None
    is_active: bool
    scopes: list[str]
    last_error: str | None
    connected_at: datetime
    subscriptions: list["SubscriptionStatus"]


class SubscriptionStatus(_Base):
    kind: str
    expiration_datetime: datetime
    last_renewed_at: datetime | None
    failure_count: int


# ── Calendar mirror ─────────────────────────────────────────────────────


class CalendarSyncStatus(_Base):
    total_mapped_events: int
    last_inbound_sync_at: datetime | None
    last_outbound_sync_at: datetime | None
    pending_outbound: int


class CRMEventUpsert(_Base):
    crm_event_id: int
    title: str
    body_html: str | None = None
    start: datetime
    end: datetime
    timezone: str = "UTC"
    location: str | None = None
    attendees: list[EmailStr] = Field(default_factory=list)
    is_online_meeting: bool = False
    direction_hint: CalendarSyncDirection = CalendarSyncDirection.CRM_TO_OUTLOOK


# ── Reconciliation ──────────────────────────────────────────────────────


class SuggestedLink(_Base):
    link_type: str
    link_id: int
    label: str
    confidence: float
    strategy: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmailReconciliationItem(_Base):
    id: int
    subject: str
    sender_email: str
    sender_name: str | None
    recipient_emails: list[str]
    received_at: datetime
    has_attachments: bool
    body_preview: str | None
    web_link: str | None
    status: str
    match_confidence: float | None
    match_strategy: str | None
    matched_link_type: str | None
    matched_link_id: int | None
    suggested_links: list[SuggestedLink] | None


class TeamsChatReconciliationItem(_Base):
    id: int
    chat_topic: str | None
    sender_email: str
    sender_name: str | None
    sent_at: datetime
    body_text: str | None
    web_link: str | None
    status: str
    match_confidence: float | None
    match_strategy: str | None
    matched_link_type: str | None
    matched_link_id: int | None
    suggested_links: list[SuggestedLink] | None


class ReconciliationListResponse(_Base):
    emails: list[EmailReconciliationItem]
    teams_chats: list[TeamsChatReconciliationItem]
    total_unmatched: int
    total_suggested: int


class ManualLinkRequest(_Base):
    link_type: str
    link_id: int


class DismissRequest(_Base):
    reason: str | None = None


# ── Webhook payloads ────────────────────────────────────────────────────


class GraphChangeNotification(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    subscription_id: str = Field(alias="subscriptionId")
    client_state: str | None = Field(default=None, alias="clientState")
    change_type: Literal["created", "updated", "deleted"] = Field(alias="changeType")
    resource: str
    resource_data: dict[str, Any] | None = Field(default=None, alias="resourceData")
    tenant_id: str | None = Field(default=None, alias="tenantId")


class GraphNotificationBatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    value: list[GraphChangeNotification]
