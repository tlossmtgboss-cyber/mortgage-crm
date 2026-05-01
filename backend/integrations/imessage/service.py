"""
iMessage service layer.

Coordinates BlueBubbles, Postgres, and downstream Perennia agents.

Outbound flow:
  send() → resolve_line → resolve_channel(lookup cache or live probe) →
    if iMessage available: BlueBubblesClient.send_text
    else if Telnyx fallback enabled: hand off to existing Telnyx adapter
  → persist message row (status=SENDING) → return optimistic response
  → webhook later flips status to SENT/DELIVERED/READ/FAILED

Inbound flow:
  webhook receiver hands BBWebhookEvent → ingest_event() →
    dedupe via webhook log → resolve thread/contact/line →
    insert/update message row → fan out to:
      * AI Operations Manager      (record_inbound)
      * Deal Breaker Radar         (evaluate_message)
      * Engagement engine SLA      (reset_followup_sla)
      * Calculator Agent           (classify borrower type if first reply)
      * Real-time WebSocket push   (frontend live update)
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

# === Stub adapters ========================================================
# These classes/functions wrap Perennia subsystems that don't exist yet as
# importable modules. Each stub logs and no-ops so the iMessage service
# can run end-to-end without wiring every downstream system first.
# Replace individual stubs with real imports as each subsystem is wired.
import logging as _logging

_stub_log = _logging.getLogger("integrations.imessage.stubs")


class AuditLogger:
    """Stub — replace with real audit trail service."""
    async def record(self, session, *, action, actor_user_id, organization_id,
                     resource_type, resource_id, metadata=None):
        _stub_log.debug(
            "audit.stub: %s %s/%s by %s", action, resource_type, resource_id, actor_user_id
        )


class ContactRepository:
    """Stub — replace with real contact lookup/creation."""
    async def get_for_tenant(self, session, *, organization_id, contact_id):
        from sqlalchemy import select
        # Attempt a real lookup against the leads table as a best-effort fallback
        try:
            from database.models import Lead
            return session.execute(
                select(Lead).where(Lead.id == contact_id)
            ).scalar_one_or_none()
        except Exception:
            _stub_log.warning("contact_repo.stub: get_for_tenant(%s) — no real impl", contact_id)
            return None

    async def get_or_create_by_handle(self, session, *, organization_id, phone_or_email, source):
        _stub_log.warning(
            "contact_repo.stub: get_or_create_by_handle(%s) — no real impl", phone_or_email
        )
        return None


async def reset_followup_sla(session, *, organization_id, contact_id):
    """Stub — replace with real engagement SLA reset."""
    _stub_log.debug("sla.stub: reset_followup_sla for contact %s", contact_id)


class CalculatorAgent:
    """Stub — replace with real borrower-type classification agent."""
    async def classify_borrower_async(self, session, *, organization_id, contact_id, body):
        _stub_log.debug("calculator.stub: classify_borrower for %s", contact_id)


class DealBreakerRadar:
    """Stub — replace with real deal-breaker detection agent."""
    async def evaluate_message_async(self, session, *, event):
        _stub_log.debug("deal_breaker.stub: evaluate_message %s", event.message_id if hasattr(event, 'message_id') else '?')


class AIOperationsManager:
    """Stub — replace with real AI ops manager."""
    async def record_inbound_async(self, session, *, event):
        _stub_log.debug("ops_mgr.stub: record_inbound %s", event.message_id if hasattr(event, 'message_id') else '?')


async def broadcast_to_tenant(tenant_id, payload):
    """Stub — replace with real WebSocket broadcast."""
    _stub_log.debug("broadcast.stub: tenant=%s type=%s", tenant_id, payload.get("type"))


class TelnyxAdapter:
    """Wraps the existing telephony.sms.send_sms for iMessage fallback."""
    async def send(self, *, organization_id, from_number, to_number, body, media_url=None):
        try:
            from telephony.sms import send_sms
            result = send_sms(
                to=to_number,
                from_=from_number,
                text=body,
                media_urls=[media_url] if media_url else None,
                organization_id=organization_id,
            )

            class _Resp:
                pass
            resp = _Resp()
            resp.id = result.get("id", "telnyx-unknown")
            return resp
        except Exception as e:
            _stub_log.error("telnyx.send_failed: %s -> %s: %s", from_number, to_number, e)
            raise
# ==========================================================================

from .chat_guid import build_chat_guid, normalize_handle
from .client import (
    BlueBubblesClient,
    BlueBubblesError,
    BlueBubblesUnreachableError,
    BlueBubblesValidationError,
)
from .config import IMessageSettings, get_imessage_settings
from .models import (
    IMessageLine,
    IMessageLookupCache,
    IMessageMessage,
    IMessageThread,
    IMessageWebhookLog,
)
from .schemas import (
    BBMessageEnvelope,
    BBSendTextPayload,
    BBWebhookEvent,
    Channel,
    ConversationMessage,
    ConversationThread,
    Direction,
    IMessageDetectionResult,
    InboundMessageEvent,
    MessageStatus,
    SendMessageRequest,
    SendMessageResponse,
    TapbackRequest,
    TapbackType,
)

logger = logging.getLogger(__name__)


class IMessageService:
    def __init__(
        self,
        *,
        client_factory,  # callable: (line: IMessageLine) -> BlueBubblesClient
        contacts: ContactRepository,
        audit: AuditLogger,
        ops_manager: AIOperationsManager,
        deal_breaker: DealBreakerRadar,
        calculator: CalculatorAgent,
        telnyx: Optional[TelnyxAdapter] = None,
        settings: Optional[IMessageSettings] = None,
    ) -> None:
        self._client_for = client_factory
        self.contacts = contacts
        self.audit = audit
        self.ops_manager = ops_manager
        self.deal_breaker = deal_breaker
        self.calculator = calculator
        self.telnyx = telnyx
        self.settings = settings or get_imessage_settings()

    # =====================================================================
    # OUTBOUND
    # =====================================================================
    async def send(
        self,
        session: Session,
        *,
        organization_id: int,
        seat_user_id: UUID,
        request: SendMessageRequest,
    ) -> SendMessageResponse:
        contact = await self.contacts.get_for_tenant(
            session, organization_id=organization_id, contact_id=request.contact_id
        )
        if contact is None:
            raise ValueError(f"contact {request.contact_id} not found")
        recipient = contact.phone or contact.email
        if not recipient:
            raise ValueError(f"contact {contact.id} has no phone or email")

        line = self._resolve_line(
            session, organization_id=organization_id, line_id=request.line_id
        )
        thread = self._get_or_create_thread(
            session,
            organization_id=organization_id,
            contact_id=contact.id,
            line=line,
            recipient=normalize_handle(recipient),
        )

        # ---- decide channel -----------------------------------------------
        channel = await self._resolve_channel(
            session,
            line=line,
            handle=normalize_handle(recipient),
            requested=request.channel,
        )

        # ---- persist optimistic row first (so the UI gets an id) ---------
        msg = IMessageMessage(
            organization_id=organization_id,
            thread_id=thread.id,
            contact_id=contact.id,
            sender_seat_id=seat_user_id,
            direction=Direction.OUTBOUND.value,
            channel=channel.value,
            status=MessageStatus.QUEUED.value,
            body=request.body,
            media_urls=[request.media_url] if request.media_url else None,
            send_style=(request.send_style.value if request.send_style else None),
            bb_temp_guid=f"temp-{uuid.uuid4()}",
            bb_chat_guid=thread.chat_guid,
            reply_to_message_id=request.reply_to_message_id,
        )
        session.add(msg)
        session.flush()

        # ---- SMS fallback path --------------------------------------------
        if channel == Channel.SMS and self.settings.telnyx_fallback_enabled and self.telnyx:
            telnyx_resp = await self.telnyx.send(
                organization_id=organization_id,
                from_number=line.handle,
                to_number=recipient,
                body=request.body or "",
                media_url=request.media_url,
            )
            msg.status = MessageStatus.SENDING.value
            msg.bb_message_guid = telnyx_resp.id  # reuse field for unified lookup
            msg.sent_at = datetime.now(timezone.utc)
            session.flush()
            await self._audit_send(session, organization_id, seat_user_id, msg, "telnyx")
            return self._send_response(msg, line, channel)

        # ---- iMessage path -------------------------------------------------
        bb_chat_guid = thread.chat_guid or build_chat_guid(
            recipient=normalize_handle(recipient),
            service="iMessage" if channel == Channel.IMESSAGE else "any",
        )

        bb_payload = BBSendTextPayload(
            chatGuid=bb_chat_guid,
            tempGuid=msg.bb_temp_guid or f"temp-{uuid.uuid4()}",
            message=request.body or "",
            method="private-api",
            effectId=(request.send_style.value if request.send_style else None) or None,
        )

        # Reply handling
        if request.reply_to_message_id:
            replied = session.execute(
                select(IMessageMessage).where(IMessageMessage.id == request.reply_to_message_id)
            ).scalar_one_or_none()
            if replied and replied.bb_message_guid:
                bb_payload.selectedMessageGuid = replied.bb_message_guid
                bb_payload.partIndex = 0

        client = self._client_for(line)
        try:
            bb_resp = await client.send_text(bb_payload)
        except BlueBubblesUnreachableError as exc:
            msg.status = MessageStatus.FAILED.value
            msg.error_code = -1
            msg.error_message = f"BlueBubbles unreachable: {exc}"
            await self._audit_send(
                session, organization_id, seat_user_id, msg, "imessage_unreachable"
            )
            session.flush()
            raise
        except BlueBubblesValidationError as exc:
            msg.status = MessageStatus.FAILED.value
            msg.error_code = exc.status_code or 400
            msg.error_message = str(exc.payload)[:1000]
            session.flush()
            raise
        except BlueBubblesError as exc:
            # iMessage send timeout — try Telnyx if enabled
            if (
                self.settings.telnyx_fallback_enabled
                and self.telnyx
                and channel == Channel.IMESSAGE
            ):
                logger.warning(
                    "imessage.bb_send_timeout_falling_back_to_sms",
                    extra={"line": str(line.id), "contact": str(contact.id)},
                )
                msg.channel = Channel.SMS.value
                telnyx_resp = await self.telnyx.send(
                    organization_id=organization_id,
                    from_number=line.handle,
                    to_number=recipient,
                    body=request.body or "",
                    media_url=request.media_url,
                )
                msg.status = MessageStatus.SENDING.value
                msg.bb_message_guid = telnyx_resp.id
                msg.sent_at = datetime.now(timezone.utc)
                session.flush()
                await self._audit_send(
                    session, organization_id, seat_user_id, msg, "telnyx_fallback"
                )
                return self._send_response(msg, line, Channel.SMS)
            msg.status = MessageStatus.FAILED.value
            msg.error_code = exc.bb_status or exc.status_code or 500
            msg.error_message = str(exc.payload)[:1000]
            session.flush()
            raise

        # ---- happy path ----------------------------------------------------
        data = (bb_resp or {}).get("data") or {}
        envelope = BBMessageEnvelope.model_validate(data) if data else None
        if envelope:
            msg.bb_message_guid = envelope.guid
            handle_service = (envelope.handle.service if envelope.handle else None)
            if handle_service:
                msg.channel = (
                    Channel.IMESSAGE.value
                    if handle_service.lower().startswith("imessage")
                    else Channel.SMS.value
                )
                # Keep the cache fresh based on what BB actually used.
                await self._upsert_lookup(
                    session,
                    line_id=line.id,
                    handle=normalize_handle(recipient),
                    service=handle_service,
                )
        msg.status = MessageStatus.SENDING.value
        msg.sent_at = datetime.now(timezone.utc)
        msg.raw_payload = bb_resp

        # Stamp the chat_guid on the thread so the next send reuses it
        if not thread.chat_guid:
            thread.chat_guid = bb_chat_guid
        thread.last_message_at = datetime.now(timezone.utc)

        session.flush()
        await self._audit_send(session, organization_id, seat_user_id, msg, "imessage")

        await broadcast_to_tenant(
            organization_id,
            {
                "type": "imessage.message.created",
                "thread_id": str(thread.id),
                "message": _serialize(msg),
            },
        )
        return self._send_response(msg, line, Channel(msg.channel))

    async def send_tapback(
        self,
        session: Session,
        *,
        organization_id: int,
        seat_user_id: UUID,
        request: TapbackRequest,
    ) -> ConversationMessage:
        target = session.execute(
            select(IMessageMessage).where(IMessageMessage.id == request.target_message_id)
        ).scalar_one_or_none()
        if target is None or target.organization_id != organization_id:
            raise ValueError("target message not found")
        if not target.bb_message_guid or not target.bb_chat_guid:
            raise ValueError("target has no BB identifiers — cannot tapback")

        thread = session.execute(
            select(IMessageThread).where(IMessageThread.id == target.thread_id)
        ).scalar_one_or_none()
        if thread is None:
            raise ValueError("thread missing")
        line = session.execute(
            select(IMessageLine).where(IMessageLine.id == thread.line_id)
        ).scalar_one_or_none()
        if line is None:
            raise ValueError("line missing")

        client = self._client_for(line)
        bb_resp = await client.send_tapback(
            chat_guid=target.bb_chat_guid,
            target_message_guid=target.bb_message_guid,
            tapback=request.tapback,
            remove=request.remove,
        )
        envelope = BBMessageEnvelope.model_validate((bb_resp or {}).get("data", {}))

        tap_msg = IMessageMessage(
            organization_id=organization_id,
            thread_id=thread.id,
            contact_id=target.contact_id,
            sender_seat_id=seat_user_id,
            direction=Direction.OUTBOUND.value,
            channel=target.channel,
            status=MessageStatus.SENDING.value,
            body=None,
            tapback=request.tapback.value,
            associated_message_guid=target.bb_message_guid,
            bb_message_guid=envelope.guid if envelope else None,
            bb_chat_guid=target.bb_chat_guid,
            sent_at=datetime.now(timezone.utc),
            raw_payload=bb_resp,
        )
        session.add(tap_msg)
        session.flush()
        return _to_conv_message(tap_msg)

    async def detect_imessage(
        self,
        session: Session,
        *,
        organization_id: int,
        handle: str,
        force: bool = False,
        line_id: Optional[UUID] = None,
    ) -> IMessageDetectionResult:
        line = self._resolve_line(session, organization_id=organization_id, line_id=line_id)
        normalized = normalize_handle(handle)

        if not force:
            cached = self._get_cached_lookup(session, line_id=line.id, handle=normalized)
            if cached is not None:
                return IMessageDetectionResult(
                    handle=normalized,
                    service=Channel.IMESSAGE
                    if cached.service.lower() == "imessage"
                    else Channel.SMS,
                    cached=True,
                    checked_at=cached.checked_at,
                )

        client = self._client_for(line)
        body = await client.check_handle_availability(normalized)
        service = ((body.get("data") or {}).get("service") or "SMS")
        row = self._upsert_lookup(
            session, line_id=line.id, handle=normalized, service=service
        )
        return IMessageDetectionResult(
            handle=normalized,
            service=Channel.IMESSAGE if service.lower() == "imessage" else Channel.SMS,
            cached=False,
            checked_at=row.checked_at,
        )

    # =====================================================================
    # INBOUND (webhook ingestion)
    # =====================================================================
    async def ingest_event(
        self,
        session: Session,
        *,
        line: IMessageLine,
        event: BBWebhookEvent,
        raw_body: dict,
    ) -> None:
        """
        Idempotent webhook handler. Sendblue may retry — we dedupe on
        (event_type, bb_guid, signature).
        """
        signature = self._signature(event, raw_body)
        bb_guid = (event.data or {}).get("guid") or (event.data or {}).get("address") or ""

        log_stmt = (
            pg_insert(IMessageWebhookLog)
            .values(
                organization_id=line.organization_id,
                line_id=line.id,
                event_type=event.type,
                bb_guid=bb_guid,
                event_signature=signature,
                payload=raw_body,
                processed=False,
            )
            .on_conflict_do_nothing(
                index_elements=["event_type", "bb_guid", "event_signature"]
            )
            .returning(IMessageWebhookLog.id)
        )
        log_row = session.execute(log_stmt).first()
        if log_row is None:
            logger.info("imessage.webhook.dedupe_skip", extra={"type": event.type})
            return

        try:
            if event.type == "new-message":
                await self._handle_new_message(session, line, event)
            elif event.type == "updated-message":
                await self._handle_updated_message(session, line, event)
            elif event.type == "typing-indicator":
                await self._handle_typing_indicator(line, event)
            elif event.type == "chat-read-status-changed":
                await self._handle_read_status(session, event)
            elif event.type in (
                "group-name-change",
                "participant-removed",
                "participant-added",
            ):
                await self._handle_group_event(session, line, event)
            elif event.type == "hello-world":
                logger.info("imessage.webhook.hello_world", extra={"line": str(line.id)})
            else:
                logger.info("imessage.webhook.unhandled_type", extra={"type": event.type})
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "imessage.webhook.processing_error", extra={"type": event.type}
            )
            session.execute(
                IMessageWebhookLog.__table__.update()
                .where(IMessageWebhookLog.id == log_row[0])
                .values(processing_error=str(exc))
            )
            return

        session.execute(
            IMessageWebhookLog.__table__.update()
            .where(IMessageWebhookLog.id == log_row[0])
            .values(processed=True)
        )

    # ---- new-message handler -------------------------------------------------
    async def _handle_new_message(
        self, session: Session, line: IMessageLine, event: BBWebhookEvent
    ) -> None:
        envelope = event.as_message()
        if envelope is None:
            return

        # Outbound echo: a message we just sent is being acknowledged. Find
        # by tempGuid so we can stamp the real BB GUID on our row.
        if envelope.isFromMe:
            await self._reconcile_outbound_echo(session, envelope)
            return

        # Inbound from a borrower
        if not envelope.handle or not envelope.handle.address:
            logger.warning("imessage.inbound.no_handle", extra={"event": event.type})
            return

        contact = await self.contacts.get_or_create_by_handle(
            session,
            organization_id=line.organization_id,
            phone_or_email=envelope.handle.address,
            source="imessage_inbound",
        )
        thread = self._get_or_create_thread(
            session,
            organization_id=line.organization_id,
            contact_id=contact.id,
            line=line,
            recipient=normalize_handle(envelope.handle.address),
        )

        chat_guid = self._chat_guid_from_envelope(envelope) or thread.chat_guid
        if chat_guid and not thread.chat_guid:
            thread.chat_guid = chat_guid

        # Tapback?
        tapback = _parse_tapback_type(envelope.associatedMessageType)

        msg = IMessageMessage(
            organization_id=line.organization_id,
            thread_id=thread.id,
            contact_id=contact.id,
            direction=Direction.INBOUND.value,
            channel=(
                Channel.IMESSAGE.value
                if (envelope.handle.service or "").lower().startswith("imessage")
                else Channel.SMS.value
            ),
            status=(
                MessageStatus.RECEIVED.value
                if not tapback
                else MessageStatus.RECEIVED.value
            ),
            body=envelope.text or None,
            media_urls=[a.get("guid") for a in envelope.attachments] or None,
            bb_message_guid=envelope.guid,
            bb_chat_guid=chat_guid,
            associated_message_guid=envelope.associatedMessageGuid,
            tapback=tapback.value if tapback else None,
            sent_at=_ms_to_dt(envelope.dateCreated),
            raw_payload=envelope.model_dump(mode="json"),
        )
        session.add(msg)
        thread.last_message_at = msg.sent_at or datetime.now(timezone.utc)
        session.flush()

        # Pipeline fan-out -----------------------------------------------------
        await reset_followup_sla(
            session, organization_id=line.organization_id, contact_id=contact.id
        )

        if envelope.text:
            inbound_event = InboundMessageEvent(
                organization_id=line.organization_id,
                contact_id=contact.id,
                message_id=msg.id,
                channel=Channel(msg.channel),
                body=envelope.text,
                received_at=msg.sent_at or datetime.now(timezone.utc),
                bb_message_guid=envelope.guid,
            )
            await self.ops_manager.record_inbound_async(session, event=inbound_event)
            await self.deal_breaker.evaluate_message_async(session, event=inbound_event)
            # First-reply borrower-type classification (Calculator Agent)
            is_first = self._is_first_inbound(session, contact.id)
            if is_first:
                await self.calculator.classify_borrower_async(
                    session, organization_id=line.organization_id, contact_id=contact.id, body=envelope.text
                )

        await broadcast_to_tenant(
            line.organization_id,
            {
                "type": "imessage.message.received",
                "thread_id": str(thread.id),
                "contact_id": str(contact.id),
                "message": _serialize(msg),
            },
        )

        await self.audit.record(
            session,
            action="imessage.receive",
            actor_user_id=None,
            organization_id=line.organization_id,
            resource_type="imessage_message",
            resource_id=str(msg.id),
            metadata={"bb_guid": envelope.guid, "channel": msg.channel},
        )

    async def _reconcile_outbound_echo(
        self, session: Session, envelope: BBMessageEnvelope
    ) -> None:
        # Find by guid first (perfect match) — covers the case where BB
        # returned the guid synchronously and we already stamped it.
        msg = session.execute(
            select(IMessageMessage).where(
                IMessageMessage.bb_message_guid == envelope.guid
            )
        ).scalar_one_or_none()
        if msg is None:
            # No row yet: this happens if the send response was slow and
            # the webhook beat it. We'll let the send-path UPSERT.
            return
        if envelope.dateDelivered:
            msg.delivered_at = _ms_to_dt(envelope.dateDelivered)
            msg.status = MessageStatus.DELIVERED.value
        if envelope.dateRead:
            msg.read_at = _ms_to_dt(envelope.dateRead)
            msg.status = MessageStatus.READ.value
        if envelope.error:
            msg.status = MessageStatus.FAILED.value
            msg.error_code = envelope.error

    async def _handle_updated_message(
        self, session: Session, line: IMessageLine, event: BBWebhookEvent
    ) -> None:
        envelope = event.as_message()
        if envelope is None:
            return
        msg = session.execute(
            select(IMessageMessage).where(
                IMessageMessage.bb_message_guid == envelope.guid
            )
        ).scalar_one_or_none()
        if msg is None:
            return
        if envelope.dateDelivered and not msg.delivered_at:
            msg.delivered_at = _ms_to_dt(envelope.dateDelivered)
            if msg.status not in (MessageStatus.READ.value, MessageStatus.FAILED.value):
                msg.status = MessageStatus.DELIVERED.value
        if envelope.dateRead and not msg.read_at:
            msg.read_at = _ms_to_dt(envelope.dateRead)
            if msg.status != MessageStatus.FAILED.value:
                msg.status = MessageStatus.READ.value
        if envelope.error:
            msg.status = MessageStatus.FAILED.value
            msg.error_code = envelope.error

        await broadcast_to_tenant(
            line.organization_id,
            {
                "type": "imessage.message.updated",
                "message_id": str(msg.id),
                "status": msg.status,
                "delivered_at": msg.delivered_at.isoformat() if msg.delivered_at else None,
                "read_at": msg.read_at.isoformat() if msg.read_at else None,
            },
        )

    async def _handle_typing_indicator(
        self, line: IMessageLine, event: BBWebhookEvent
    ) -> None:
        # BB payload: {chatGuid, display: bool}
        await broadcast_to_tenant(
            line.organization_id,
            {
                "type": "imessage.typing",
                "chat_guid": event.data.get("chatGuid"),
                "display": event.data.get("display", False),
            },
        )

    async def _handle_read_status(
        self, session: Session, event: BBWebhookEvent
    ) -> None:
        chat_guid = event.data.get("chatGuid")
        read = event.data.get("read", False)
        if not chat_guid or not read:
            return
        # Mark all outbound messages in this chat as read up to the given ts
        thread = session.execute(
            select(IMessageThread).where(IMessageThread.chat_guid == chat_guid)
        ).scalar_one_or_none()
        if thread is None:
            return
        session.execute(
            IMessageMessage.__table__.update()
            .where(
                IMessageMessage.thread_id == thread.id,
                IMessageMessage.direction == Direction.OUTBOUND.value,
                IMessageMessage.read_at.is_(None),
            )
            .values(read_at=datetime.now(timezone.utc), status=MessageStatus.READ.value)
        )

    async def _handle_group_event(
        self, session: Session, line: IMessageLine, event: BBWebhookEvent
    ) -> None:
        # Hook this up if/when you launch the co-borrower thread feature
        logger.info(
            "imessage.group_event",
            extra={"type": event.type, "data": event.data},
        )

    # =====================================================================
    # Read APIs (for the FastAPI router)
    # =====================================================================
    async def get_thread(
        self,
        session: Session,
        *,
        organization_id: int,
        contact_id: UUID,
        limit: int = 200,
    ) -> ConversationThread:
        contact = await self.contacts.get_for_tenant(
            session, organization_id=organization_id, contact_id=contact_id
        )
        if contact is None:
            raise ValueError("contact not found")

        thread = session.execute(
            select(IMessageThread).where(
                IMessageThread.organization_id == organization_id,
                IMessageThread.contact_id == contact_id,
            )
        ).scalar_one_or_none()
        if thread is None:
            line = self._resolve_line(session, organization_id=organization_id, line_id=None)
            return ConversationThread(
                contact_id=contact.id,
                contact_phone=contact.phone,
                contact_email=contact.email,
                chat_guid=None,
                last_known_channel=None,
                imessage_supported=None,
                line_id=line.id,
                line_handle=line.handle,
                messages=[],
            )

        rows = session.scalars(
            select(IMessageMessage)
            .where(IMessageMessage.thread_id == thread.id)
            .order_by(IMessageMessage.created_at.desc())
            .limit(limit)
        ).all()
        line = session.execute(
            select(IMessageLine).where(IMessageLine.id == thread.line_id)
        ).scalar_one_or_none()
        cached = self._get_cached_lookup(
            session,
            line_id=thread.line_id,
            handle=normalize_handle(contact.phone or contact.email or ""),
        )
        last_known: Optional[Channel] = None
        if thread.last_known_service:
            last_known = (
                Channel.IMESSAGE
                if thread.last_known_service.lower() == "imessage"
                else Channel.SMS
            )

        return ConversationThread(
            contact_id=contact.id,
            contact_phone=contact.phone,
            contact_email=contact.email,
            chat_guid=thread.chat_guid,
            last_known_channel=last_known,
            imessage_supported=(
                None if cached is None else cached.service.lower() == "imessage"
            ),
            line_id=line.id if line else thread.line_id,
            line_handle=line.handle if line else "",
            messages=[_to_conv_message(r) for r in reversed(rows)],
        )

    # =====================================================================
    # Helpers
    # =====================================================================
    def _resolve_line(
        self,
        session: Session,
        *,
        organization_id: int,
        line_id: Optional[UUID],
    ) -> IMessageLine:
        if line_id:
            line = session.execute(
                select(IMessageLine).where(IMessageLine.id == line_id)
            ).scalar_one_or_none()
            if line is None or line.organization_id != organization_id or not line.enabled:
                raise ValueError(f"line {line_id} not available for organization")
            return line
        # Default: pick the first enabled line for this organization
        line = session.execute(
            select(IMessageLine)
            .where(IMessageLine.organization_id == organization_id, IMessageLine.enabled.is_(True))
            .order_by(IMessageLine.created_at)
            .limit(1)
        ).scalar_one_or_none()
        if line is None:
            raise ValueError(f"no iMessage lines configured for organization {organization_id}")
        return line

    def _get_or_create_thread(
        self,
        session: Session,
        *,
        organization_id: int,
        contact_id: int,
        line: IMessageLine,
        recipient: str,
    ) -> IMessageThread:
        thread = session.execute(
            select(IMessageThread).where(
                IMessageThread.organization_id == organization_id,
                IMessageThread.contact_id == contact_id,
                IMessageThread.line_id == line.id,
            )
        ).scalar_one_or_none()
        if thread is not None:
            return thread
        thread = IMessageThread(
            organization_id=organization_id,
            contact_id=contact_id,
            line_id=line.id,
            chat_guid=None,
            is_group=False,
        )
        session.add(thread)
        session.flush()
        return thread

    async def _resolve_channel(
        self,
        session: Session,
        *,
        line: IMessageLine,
        handle: str,
        requested: Channel,
    ) -> Channel:
        if requested != Channel.AUTO:
            return requested
        cached = self._get_cached_lookup(
            session, line_id=line.id, handle=handle
        )
        if cached is not None:
            return (
                Channel.IMESSAGE
                if cached.service.lower() == "imessage"
                else Channel.SMS
            )
        client = self._client_for(line)
        try:
            body = await client.check_handle_availability(handle)
        except BlueBubblesError:
            return Channel.IMESSAGE
        service = ((body.get("data") or {}).get("service") or "SMS")
        self._upsert_lookup(
            session, line_id=line.id, handle=handle, service=service
        )
        return Channel.IMESSAGE if service.lower() == "imessage" else Channel.SMS

    def _get_cached_lookup(
        self, session: Session, *, line_id: UUID, handle: str
    ) -> Optional[IMessageLookupCache]:
        if not handle:
            return None
        row = session.execute(
            select(IMessageLookupCache).where(
                IMessageLookupCache.line_id == line_id,
                IMessageLookupCache.handle == handle,
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        ttl = timedelta(seconds=self.settings.imessage_lookup_cache_ttl_seconds)
        if row.checked_at + ttl < datetime.now(timezone.utc):
            return None
        return row

    def _upsert_lookup(
        self,
        session: Session,
        *,
        line_id: UUID,
        handle: str,
        service: str,
    ) -> IMessageLookupCache:
        stmt = (
            pg_insert(IMessageLookupCache)
            .values(line_id=line_id, handle=handle, service=service)
            .on_conflict_do_update(
                index_elements=["line_id", "handle"],
                set_={"service": service, "checked_at": datetime.now(timezone.utc)},
            )
            .returning(IMessageLookupCache)
        )
        return session.execute(stmt).scalar_one()

    def _is_first_inbound(
        self, session: Session, contact_id: int
    ) -> bool:
        row = session.execute(
            select(IMessageMessage)
            .where(
                IMessageMessage.contact_id == contact_id,
                IMessageMessage.direction == Direction.INBOUND.value,
            )
            .limit(2)
        ).scalar_one_or_none()
        return row is None

    def _signature(self, event: BBWebhookEvent, raw_body: dict) -> str:
        envelope = event.data or {}
        key = json.dumps(
            {
                "g": envelope.get("guid"),
                "d": envelope.get("dateDelivered"),
                "r": envelope.get("dateRead"),
                "e": envelope.get("error"),
                "f": envelope.get("isFromMe"),
                "t": event.type,
            },
            sort_keys=True,
        )
        return hashlib.sha256(key.encode()).hexdigest()[:64]

    def _chat_guid_from_envelope(self, envelope: BBMessageEnvelope) -> Optional[str]:
        for chat in envelope.chats or []:
            if guid := chat.get("guid"):
                return guid
        return None

    async def _audit_send(
        self,
        session: Session,
        organization_id: int,
        seat_user_id: UUID,
        msg: IMessageMessage,
        outcome: str,
    ) -> None:
        await self.audit.record(
            session,
            action="imessage.send",
            actor_user_id=seat_user_id,
            organization_id=organization_id,
            resource_type="imessage_message",
            resource_id=str(msg.id),
            metadata={
                "channel": msg.channel,
                "outcome": outcome,
                "bb_guid": msg.bb_message_guid,
            },
        )

    def _send_response(
        self, msg: IMessageMessage, line: IMessageLine, channel: Channel
    ) -> SendMessageResponse:
        return SendMessageResponse(
            message_id=msg.id,
            bb_message_guid=msg.bb_message_guid or "",
            chat_guid=msg.bb_chat_guid or "",
            channel=channel,
            status=MessageStatus(msg.status),
            sent_via_line_id=line.id,
            created_at=msg.created_at,
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def _ms_to_dt(ms: Optional[int]) -> Optional[datetime]:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _parse_tapback_type(associated: Optional[str]) -> Optional[TapbackType]:
    if not associated:
        return None
    name = associated.lower()
    for t in TapbackType:
        if t.value in name:
            return t
    return None


def _to_conv_message(m: IMessageMessage) -> ConversationMessage:
    return ConversationMessage(
        id=m.id,
        contact_id=m.contact_id,
        direction=Direction(m.direction),
        body=m.body,
        media_urls=m.media_urls or [],
        channel=Channel(m.channel),
        status=MessageStatus(m.status),
        send_style=None,  # populated by frontend serializer if needed
        error_code=m.error_code,
        error_message=m.error_message,
        bb_message_guid=m.bb_message_guid,
        sender_seat_id=m.sender_seat_id,
        reply_to_message_id=m.reply_to_message_id,
        associated_message_guid=m.associated_message_guid,
        tapback=TapbackType(m.tapback) if m.tapback else None,
        created_at=m.created_at,
        delivered_at=m.delivered_at,
        read_at=m.read_at,
    )


def _serialize(m: IMessageMessage) -> dict:
    return _to_conv_message(m).model_dump(mode="json")
