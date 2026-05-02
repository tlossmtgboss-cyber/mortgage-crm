"""
Async HTTP client for the BlueBubbles Server REST API (v1).

BlueBubbles auth model:
  - Every request needs `?password=<server-password>` as a query param.
    Aliases accepted by the server: `guid` and `token`.
  - Cloudflare Access service-token headers go on every request to gate
    the tunnel.

Endpoints we use:
  GET  /api/v1/ping
  POST /api/v1/message/text                (send text, replies, effects)
  POST /api/v1/message/attachment          (multipart, send media)
  POST /api/v1/message/react               (private API — tapbacks)
  POST /api/v1/chat/query                  (list chats, find or create)
  POST /api/v1/chat/<guid>/typing          (start typing indicator)
  DELETE /api/v1/chat/<guid>/typing        (stop typing indicator)
  POST /api/v1/chat/<guid>/read            (mark as read)
  GET  /api/v1/chat/<guid>/message         (history)
  GET  /api/v1/message/<guid>              (single message)
  POST /api/v1/handle/availability         (check iMessage support)
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

import httpx

from .config import IMessageSettings, get_imessage_settings
from .models import IMessageLine
from .schemas import BBSendTextPayload, TapbackType

logger = logging.getLogger(__name__)


class BlueBubblesError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        bb_status: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.bb_status = bb_status
        self.payload = payload or {}


class BlueBubblesAuthError(BlueBubblesError):
    pass


class BlueBubblesUnreachableError(BlueBubblesError):
    pass


class BlueBubblesValidationError(BlueBubblesError):
    pass


# ---------------------------------------------------------------------------
# Tapback association map (BB private API)
# ---------------------------------------------------------------------------
_TAPBACK_TO_REACTION = {
    TapbackType.LOVE: "love",
    TapbackType.LIKE: "like",
    TapbackType.DISLIKE: "dislike",
    TapbackType.LAUGH: "laugh",
    TapbackType.EMPHASIZE: "emphasize",
    TapbackType.QUESTION: "question",
}
_TAPBACK_REMOVE_PREFIX = "-"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class BlueBubblesClient:
    """
    One client instance per Mac line. Keep these as long-lived singletons in
    a tenant-keyed registry so the connection pool is reused.
    """

    def __init__(
        self,
        line: IMessageLine,
        *,
        settings: Optional[IMessageSettings] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.line = line
        self.settings = settings or get_imessage_settings()
        self._password = line.bb_password or self.settings.bb_password

        headers = {
            "Accept": "application/json",
            "User-Agent": "Perennia-AI-iMessage/1.0",
        }
        cf_id = line.cf_access_client_id or self.settings.cf_access_client_id
        cf_secret = line.cf_access_client_secret or self.settings.cf_access_client_secret
        if cf_id and cf_secret:
            headers["CF-Access-Client-Id"] = cf_id
            headers["CF-Access-Client-Secret"] = cf_secret

        self._client = client or httpx.AsyncClient(
            base_url=line.bb_base_url.rstrip("/"),
            timeout=self.settings.request_timeout_seconds,
            headers=headers,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # -----------------------------------------------------------------------
    # Internal request with retry
    # -----------------------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        params = {**(params or {}), "password": self._password}

        last_exc: Optional[Exception] = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                resp = await self._client.request(
                    method, path, json=json, params=params, files=files, data=data
                )
            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "imessage.bb.timeout",
                    extra={"path": path, "attempt": attempt, "line": str(self.line.id)},
                )
                await asyncio.sleep(self.settings.retry_backoff_base * (2**attempt))
                continue
            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "imessage.bb.network_error",
                    extra={"path": path, "attempt": attempt, "err": str(exc)},
                )
                await asyncio.sleep(self.settings.retry_backoff_base * (2**attempt))
                continue

            try:
                body = resp.json()
            except ValueError:
                body = {"raw": resp.text}

            # BB returns 200 + status:200 on success; 200 + status:5xx on
            # iMessage-side failures (e.g. send timeout). Surface both.
            bb_status = body.get("status") if isinstance(body, dict) else None

            if resp.status_code == 401 or resp.status_code == 403:
                raise BlueBubblesAuthError(
                    f"BlueBubbles auth failed: {body}",
                    status_code=resp.status_code,
                    payload=body,
                )

            if resp.status_code >= 500 and attempt < self.settings.max_retries:
                logger.warning(
                    "imessage.bb.5xx_retry",
                    extra={"path": path, "status": resp.status_code, "attempt": attempt},
                )
                await asyncio.sleep(self.settings.retry_backoff_base * (2**attempt))
                continue

            if resp.status_code >= 400:
                raise BlueBubblesValidationError(
                    f"BlueBubbles {resp.status_code}: {body}",
                    status_code=resp.status_code,
                    bb_status=bb_status,
                    payload=body,
                )

            # 200 OK envelope. BB sometimes returns status:500 inside a 200.
            if isinstance(body, dict) and bb_status and bb_status >= 500:
                # Retry transient send timeouts
                if attempt < self.settings.max_retries and "timeout" in (
                    body.get("error", {}) or {}
                ).get("message", "").lower():
                    await asyncio.sleep(self.settings.retry_backoff_base * (2**attempt))
                    continue
                raise BlueBubblesError(
                    f"BlueBubbles internal: {body}",
                    status_code=resp.status_code,
                    bb_status=bb_status,
                    payload=body,
                )

            return body

        raise BlueBubblesUnreachableError(
            f"BlueBubbles unreachable after {self.settings.max_retries} retries: {last_exc}"
        )

    # -----------------------------------------------------------------------
    # Public methods
    # -----------------------------------------------------------------------
    async def ping(self) -> bool:
        body = await self._request("GET", "/api/v1/ping")
        return body.get("status") == 200

    async def send_text(self, payload: BBSendTextPayload) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/message/text",
            json=payload.model_dump(exclude_none=True),
        )

    async def send_attachment(
        self,
        *,
        chat_guid: str,
        file_bytes: bytes,
        filename: str,
        message: Optional[str] = None,
    ) -> dict[str, Any]:
        files = {"attachment": (filename, file_bytes)}
        data: dict[str, str] = {
            "chatGuid": chat_guid,
            "tempGuid": f"temp-{uuid.uuid4()}",
            "name": filename,
        }
        if message:
            data["message"] = message
        return await self._request(
            "POST", "/api/v1/message/attachment", files=files, data=data
        )

    async def send_tapback(
        self,
        *,
        chat_guid: str,
        target_message_guid: str,
        tapback: TapbackType,
        remove: bool = False,
    ) -> dict[str, Any]:
        reaction = _TAPBACK_TO_REACTION[tapback]
        if remove:
            reaction = _TAPBACK_REMOVE_PREFIX + reaction
        body = {
            "chatGuid": chat_guid,
            "selectedMessageGuid": target_message_guid,
            "reaction": reaction,
        }
        return await self._request("POST", "/api/v1/message/react", json=body)

    async def start_typing(self, chat_guid: str) -> None:
        await self._request("POST", f"/api/v1/chat/{chat_guid}/typing")

    async def stop_typing(self, chat_guid: str) -> None:
        await self._request("DELETE", f"/api/v1/chat/{chat_guid}/typing")

    async def mark_read(self, chat_guid: str) -> None:
        await self._request("POST", f"/api/v1/chat/{chat_guid}/read")

    async def find_chat(self, chat_guid: str) -> Optional[dict[str, Any]]:
        body = await self._request(
            "POST",
            "/api/v1/chat/query",
            json={"limit": 1, "offset": 0, "with": ["participants"], "where": [
                {"statement": "chat.guid = :guid", "args": {"guid": chat_guid}}
            ]},
        )
        rows = body.get("data") or []
        return rows[0] if rows else None

    async def get_messages_for_chat(
        self, chat_guid: str, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        body = await self._request(
            "GET",
            f"/api/v1/chat/{chat_guid}/message",
            params={"limit": limit, "offset": offset, "sort": "ASC"},
        )
        return body.get("data") or []

    async def get_message(self, message_guid: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/message/{message_guid}")

    async def check_handle_availability(
        self, handle: str
    ) -> dict[str, Any]:
        """
        BB v1.9+ exposes GET /api/v1/handle/availability/imessage?address=...
        Returns: {"status": 200, "data": {"available": true}}
        We normalize to {"data": {"available": bool, "service": "iMessage"|"SMS"}}
        for backward compat with the service layer.
        """
        resp = await self._request(
            "GET",
            f"/api/v1/handle/availability/imessage",
            params={"address": handle},
        )
        available = (resp.get("data") or {}).get("available", False)
        resp.setdefault("data", {})["service"] = "iMessage" if available else "SMS"
        return resp

    async def upsert_webhook(self, *, url: str, events: list[str]) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/webhook",
            json={"url": url, "events": events},
        )
