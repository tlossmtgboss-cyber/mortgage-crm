"""
Pydantic schemas for the iMessage integration.

Three layers of models:

  * BlueBubbles-shaped models  — match BB's REST + webhook payloads
  * Internal Perennia models   — what the FastAPI router accepts/returns
  * Pipeline models            — what we pass to AI agents downstream
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# Shared enums
# =============================================================================
class Channel(str, Enum):
    IMESSAGE = "imessage"
    SMS = "sms"
    AUTO = "auto"


class Direction(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(str, Enum):
    QUEUED = "queued"  # we accepted it, not yet handed to BB
    SENDING = "sending"  # BB accepted it
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    RECEIVED = "received"  # inbound only


class SendStyle(str, Enum):
    NONE = ""
    INVISIBLE = "invisible"
    GENTLE = "gentle"
    LOUD = "loud"
    SLAM = "slam"
    CONFETTI = "confetti"
    ECHO = "echo"
    FIREWORKS = "fireworks"
    HEART = "heart"
    LASERS = "lasers"
    SHOOTING_STAR = "shooting_star"
    SPARKLES = "sparkles"
    SPOTLIGHT = "spotlight"


class TapbackType(str, Enum):
    LOVE = "love"
    LIKE = "like"
    DISLIKE = "dislike"
    LAUGH = "laugh"
    EMPHASIZE = "emphasize"
    QUESTION = "question"


# =============================================================================
# BlueBubbles-shaped models
# =============================================================================
class BBHandle(BaseModel):
    address: str
    service: Optional[str] = None  # "iMessage" or "SMS"


class BBSendTextPayload(BaseModel):
    """Body for POST /api/v1/message/text."""

    chatGuid: str
    tempGuid: str
    message: str
    method: Literal["apple-script", "private-api"] = "private-api"
    subject: Optional[str] = None
    effectId: Optional[str] = None  # send_style
    selectedMessageGuid: Optional[str] = None  # for replies
    partIndex: Optional[int] = None


class BBMessageEnvelope(BaseModel):
    """Common Message-shaped object returned by BB endpoints + webhooks."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    guid: str
    text: Optional[str] = ""
    isFromMe: bool = False
    dateCreated: int = 0
    dateDelivered: Optional[int] = 0
    dateRead: Optional[int] = 0
    error: int = 0
    handle: Optional[BBHandle] = None
    chats: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    expressiveSendStyleId: Optional[str] = None
    associatedMessageGuid: Optional[str] = None
    associatedMessageType: Optional[str] = None  # "love", "tapback:0", etc.
    threadOriginatorGuid: Optional[str] = None


class BBWebhookEvent(BaseModel):
    """
    Top-level webhook envelope from BlueBubbles.

    Subscribe in the BB UI to: new-message, updated-message, typing-indicator,
    chat-read-status-changed, group-name-change, participant-removed,
    participant-added.
    """

    model_config = ConfigDict(extra="allow")

    type: str
    data: dict[str, Any] = Field(default_factory=dict)

    def as_message(self) -> Optional[BBMessageEnvelope]:
        if self.type in ("new-message", "updated-message") and self.data:
            return BBMessageEnvelope.model_validate(self.data)
        return None


# =============================================================================
# Perennia-facing models (what the React frontend talks to)
# =============================================================================
class SendMessageRequest(BaseModel):
    contact_id: UUID
    body: Optional[str] = Field(None, max_length=4000)
    media_url: Optional[str] = None
    channel: Channel = Channel.AUTO
    send_style: Optional[SendStyle] = None
    reply_to_message_id: Optional[UUID] = None
    line_id: Optional[UUID] = Field(
        None, description="Override which Mac line to send from"
    )

    @field_validator("body")
    @classmethod
    def _need_content(cls, v: Optional[str], info) -> Optional[str]:  # type: ignore[no-untyped-def]
        if not v and not info.data.get("media_url"):
            raise ValueError("provide body or media_url")
        return v


class SendMessageResponse(BaseModel):
    message_id: UUID
    bb_message_guid: str
    chat_guid: str
    channel: Channel
    status: MessageStatus
    sent_via_line_id: UUID
    created_at: datetime


class TapbackRequest(BaseModel):
    target_message_id: UUID
    tapback: TapbackType
    remove: bool = False


class ConversationMessage(BaseModel):
    id: UUID
    contact_id: UUID
    direction: Direction
    body: Optional[str]
    media_urls: list[str] = Field(default_factory=list)
    channel: Channel
    status: MessageStatus
    send_style: Optional[SendStyle] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    bb_message_guid: Optional[str] = None
    sender_seat_id: Optional[UUID] = None
    reply_to_message_id: Optional[UUID] = None
    associated_message_guid: Optional[str] = None  # for tapbacks
    tapback: Optional[TapbackType] = None
    created_at: datetime
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None


class ConversationThread(BaseModel):
    contact_id: UUID
    contact_phone: Optional[str]
    contact_email: Optional[str]
    chat_guid: Optional[str]
    last_known_channel: Optional[Channel]
    imessage_supported: Optional[bool]
    line_id: UUID
    line_handle: str
    messages: list[ConversationMessage]


class IMessageDetectionResult(BaseModel):
    handle: str
    service: Channel  # imessage or sms
    cached: bool
    checked_at: datetime


# =============================================================================
# Pipeline models — passed to AI agents (call intel, Deal Breaker, ops mgr)
# =============================================================================
class InboundMessageEvent(BaseModel):
    """Event payload pushed onto your existing intake queue."""

    tenant_id: UUID
    contact_id: UUID
    message_id: UUID
    channel: Channel
    body: str
    media_urls: list[str] = Field(default_factory=list)
    received_at: datetime
    bb_message_guid: str
