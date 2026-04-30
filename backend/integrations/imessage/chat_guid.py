"""
BlueBubbles chat-GUID helpers.

A chat GUID identifies a conversation on the Mac:
  - 1:1: "iMessage;-;+15551234567"  or  "SMS;-;+15551234567"
  - 1:1, let server pick service: "any;-;+15551234567"
  - Group: "iMessage;+;chat<random_hex>"

When initiating a fresh outbound, we use "any;-;<recipient>" so BlueBubbles
itself decides between iMessage and SMS at send time. We capture the actual
service from the response and persist it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

E164_RE = re.compile(r"^\+\d{8,15}$")


@dataclass(frozen=True)
class ChatGuid:
    service: str  # "iMessage", "SMS", "any"
    is_group: bool
    address: str  # E.164 or email for 1:1; chat<hex> for groups

    def to_string(self) -> str:
        sep = "+" if self.is_group else "-"
        return f"{self.service};{sep};{self.address}"


def parse_chat_guid(guid: str) -> ChatGuid:
    parts = guid.split(";", 2)
    if len(parts) != 3:
        raise ValueError(f"invalid chat guid: {guid!r}")
    service, sep, address = parts
    if sep not in ("-", "+"):
        raise ValueError(f"invalid chat guid separator: {guid!r}")
    return ChatGuid(service=service, is_group=(sep == "+"), address=address)


def build_chat_guid(
    *, recipient: str, service: str = "any", is_group: bool = False
) -> str:
    if not is_group:
        if "@" not in recipient and not E164_RE.match(recipient):
            raise ValueError(
                f"recipient must be E.164 (+1...) or an email; got {recipient!r}"
            )
    return ChatGuid(service=service, is_group=is_group, address=recipient).to_string()


def normalize_handle(handle: str) -> str:
    """
    Normalize a recipient handle for storage / lookup keys.
    - Strips whitespace
    - Lowercases emails
    - Leaves E.164 numbers as-is
    """
    h = handle.strip()
    if "@" in h:
        return h.lower()
    return h


def display_handle(handle: Optional[str]) -> str:
    """Pretty-print a handle for the UI when no contact name is on file."""
    if not handle:
        return ""
    if "@" in handle:
        return handle
    if E164_RE.match(handle) and len(handle) == 12 and handle.startswith("+1"):
        return f"({handle[2:5]}) {handle[5:8]}-{handle[8:]}"
    return handle
