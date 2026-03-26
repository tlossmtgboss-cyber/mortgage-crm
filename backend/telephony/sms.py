"""
Telnyx SMS Helper — Centralized SMS sending via Telnyx v2 SDK.

The telnyx v2 Python SDK (v4.x) no longer has ``telnyx.Message.create()`` or
a global ``telnyx.api_key``.  Instead it uses a client-based API::

    client = telnyx.Telnyx(api_key=...)
    client.messages.send(to=..., from_=..., text=..., ...)

This module provides a thin wrapper so all SMS call-sites use the correct API.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level lazy singleton for the Telnyx client
# ---------------------------------------------------------------------------
_client = None
_client_lock = threading.Lock()


def _get_client(api_key: Optional[str] = None):
    """Return a Telnyx client, creating one lazily if needed.

    If *api_key* is provided it takes precedence; otherwise the
    ``TELNYX_API_KEY`` environment variable is used.
    """
    global _client

    key = (api_key or os.getenv("TELNYX_API_KEY", "")).strip()
    if not key:
        return None

    # Fast path — already initialised with the same key
    if _client is not None and getattr(_client, "api_key", None) == key:
        return _client

    with _client_lock:
        # Double-check after acquiring lock
        if _client is not None and getattr(_client, "api_key", None) == key:
            return _client
        try:
            import telnyx
            _client = telnyx.Telnyx(api_key=key)
            return _client
        except Exception:
            logger.exception("Failed to initialise Telnyx client")
            return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_sms(
    *,
    to: str,
    from_: str,
    text: str,
    messaging_profile_id: Optional[str] = None,
    media_urls: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an SMS via the Telnyx v2 SDK.

    Parameters
    ----------
    to : str
        Destination phone number (E.164).
    from_ : str
        Sending phone number (E.164).
    text : str
        Message body.
    messaging_profile_id : str, optional
        Telnyx messaging profile ID.
    media_urls : list[str], optional
        Media URLs for MMS.
    api_key : str, optional
        Telnyx API key.  Falls back to ``TELNYX_API_KEY`` env var.

    Returns
    -------
    dict
        ``{"id": "<message_id>", "status": "sent"}`` on success.

    Raises
    ------
    RuntimeError
        If the Telnyx client cannot be initialised (missing API key / SDK).
    Exception
        Any exception from the Telnyx API is re-raised so callers can
        handle it in their existing ``except`` blocks.
    """
    client = _get_client(api_key)
    if client is None:
        raise RuntimeError("Telnyx client not available — check TELNYX_API_KEY")

    kwargs: Dict[str, Any] = {
        "to": to,
        "from_": from_,
        "text": text,
    }
    if messaging_profile_id:
        kwargs["messaging_profile_id"] = messaging_profile_id
    if media_urls:
        kwargs["media_urls"] = media_urls

    response = client.messages.send(**kwargs)

    # The v2 SDK returns a MessageSendResponse object.  Extract the id.
    msg_id = getattr(response, "id", None) or "unknown"
    return {"id": str(msg_id), "status": "sent"}
