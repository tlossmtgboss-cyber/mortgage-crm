"""Telnyx webhook adapter — handles call.recording.saved events."""
from __future__ import annotations

import base64
import time
from datetime import datetime, timezone
from typing import Any

from .base import NormalizedCall, ProviderAdapter, parse_ts

_MAX_TIMESTAMP_AGE_SECONDS = 300


class TelnyxAdapter(ProviderAdapter):

    def validate_signature(
        self, body: bytes, headers: dict[str, str], secret: str,
    ) -> None:
        if not secret:
            return
        sig = headers.get("telnyx-signature-ed25519", "")
        ts = headers.get("telnyx-timestamp", "")
        if not sig or not ts:
            raise ValueError("Missing Telnyx signature headers")

        try:
            ts_int = int(ts)
        except (ValueError, TypeError):
            raise ValueError("Invalid Telnyx timestamp header")

        if abs(time.time() - ts_int) > _MAX_TIMESTAMP_AGE_SECONDS:
            raise ValueError("Telnyx webhook timestamp too old or too far in the future")

        try:
            from nacl.signing import VerifyKey
            from nacl.exceptions import BadSignatureError
        except ImportError:
            raise ValueError("PyNaCl is required for Telnyx signature verification")

        signing_payload = ts.encode("utf-8") + b"." + body
        try:
            public_key = VerifyKey(base64.b64decode(secret))
            public_key.verify(signing_payload, base64.b64decode(sig))
        except BadSignatureError:
            raise ValueError("Invalid Telnyx webhook signature")
        except Exception:
            raise ValueError("Telnyx signature verification failed")

    def normalize(self, payload: dict[str, Any]) -> NormalizedCall:
        data = payload.get("data", payload)
        event_payload = data.get("payload", data)

        call_control_id = event_payload.get("call_control_id", "")
        call_session_id = event_payload.get("call_session_id", call_control_id)

        started_at = parse_ts(event_payload.get("start_time"))
        ended_at = parse_ts(event_payload.get("end_time"))
        duration = None
        if started_at and ended_at:
            duration = int((ended_at - started_at).total_seconds())

        recording_url = None
        rec = event_payload.get("recording_urls", {})
        if isinstance(rec, dict):
            recording_url = rec.get("mp3") or rec.get("wav")
        elif isinstance(rec, str):
            recording_url = rec

        return NormalizedCall(
            external_call_id=call_session_id,
            provider="telnyx",
            direction=event_payload.get("direction", "incoming").replace("incoming", "inbound").replace("outgoing", "outbound"),
            phone_from=event_payload.get("from"),
            phone_to=event_payload.get("to"),
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            transcript=None,
            recording_url=recording_url,
            raw_payload=payload,
            messages=[],
        )


