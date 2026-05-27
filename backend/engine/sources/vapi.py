"""Vapi webhook adapter — handles end-of-call-report events."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

from .base import NormalizedCall, ProviderAdapter, parse_ts


class VapiAdapter(ProviderAdapter):

    def validate_signature(
        self, body: bytes, headers: dict[str, str], secret: str,
    ) -> None:
        if not secret:
            return

        # Mode 1: X-Vapi-Secret (direct comparison)
        vapi_secret = headers.get("x-vapi-secret", "")
        if vapi_secret:
            if not hmac.compare_digest(vapi_secret, secret):
                raise ValueError("Invalid Vapi webhook secret")
            return

        # Mode 2: x-vapi-signature (HMAC-SHA256)
        sig = headers.get("x-vapi-signature", "")
        if sig:
            expected = hmac.new(
                secret.encode(), body, hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(sig, expected):
                raise ValueError("Invalid Vapi webhook signature")
            return

        raise ValueError("Missing Vapi authentication header")

    def normalize(self, payload: dict[str, Any]) -> NormalizedCall:
        msg = payload.get("message", payload)
        call = msg.get("call", msg)

        messages: list[dict[str, str]] = []
        transcript_parts: list[str] = []
        for m in msg.get("messages", call.get("messages", [])):
            role = m.get("role", "unknown")
            content = m.get("content") or m.get("message", "")
            if content:
                messages.append({"role": role, "content": content})
                transcript_parts.append(f"{role.upper()}: {content}")

        started_at = parse_ts(call.get("startedAt") or call.get("createdAt"))
        ended_at = parse_ts(call.get("endedAt"))
        duration = None
        if started_at and ended_at:
            duration = int((ended_at - started_at).total_seconds())

        return NormalizedCall(
            external_call_id=call.get("id", ""),
            provider="vapi",
            direction=call.get("type", "inbound").replace("Phonecall", "").lower() or "inbound",
            phone_from=call.get("customer", {}).get("number"),
            phone_to=call.get("phoneNumber", {}).get("number"),
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            transcript="\n".join(transcript_parts) if transcript_parts else None,
            recording_url=msg.get("recordingUrl") or call.get("recordingUrl"),
            raw_payload=payload,
            messages=messages,
        )


