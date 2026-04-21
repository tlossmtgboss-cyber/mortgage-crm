"""
09-tools/registry.py

Tool registry. Every tool registers itself with:
  - schema (name, description, input_schema) — what Claude sees
  - roles — which RBAC roles can use it
  - domains — pipeline, ai, voice, docs, etc.
  - intents — semantic tags for router matching
  - side_effects — read/write/external (used for safety gates)

Drop-in: backend/app/agents/tools/registry.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

logger = logging.getLogger(__name__)

SideEffect = Literal["read", "write", "external"]


@dataclass
class ToolMetadata:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]
    roles: frozenset[str]
    domains: frozenset[str]
    intents: frozenset[str]
    side_effect: SideEffect
    deprecated: bool = False
    deprecation_replacement: str | None = None
    # For routing tie-breaks: lower number = preferred when multiple tools match
    specificity: int = 10


class ToolRegistry:
    """Central registry. Tools register via @register decorator at import time."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolMetadata] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        roles: set[str],
        domains: set[str],
        intents: set[str],
        side_effect: SideEffect,
        deprecated: bool = False,
        deprecation_replacement: str | None = None,
        specificity: int = 10,
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        def decorator(handler: Callable[..., Awaitable[Any]]):
            if name in self._tools:
                raise ValueError(f"Duplicate tool name: {name}")
            self._tools[name] = ToolMetadata(
                name=name,
                description=description,
                input_schema=input_schema,
                handler=handler,
                roles=frozenset(roles),
                domains=frozenset(domains),
                intents=frozenset(intents),
                side_effect=side_effect,
                deprecated=deprecated,
                deprecation_replacement=deprecation_replacement,
                specificity=specificity,
            )
            return handler

        return decorator

    def get(self, name: str) -> ToolMetadata | None:
        return self._tools.get(name)

    def all(self) -> list[ToolMetadata]:
        return list(self._tools.values())

    def for_role(self, role: str) -> list[ToolMetadata]:
        return [t for t in self._tools.values() if role in t.roles and not t.deprecated]

    def filter(
        self,
        *,
        role: str,
        domains: set[str] | None = None,
        intents: set[str] | None = None,
        include_deprecated: bool = False,
    ) -> list[ToolMetadata]:
        out = []
        for t in self._tools.values():
            if role not in t.roles:
                continue
            if t.deprecated and not include_deprecated:
                continue
            if domains and not (t.domains & domains):
                continue
            if intents and not (t.intents & intents):
                continue
            out.append(t)
        return out

    def to_claude_schema(self, tools: list[ToolMetadata]) -> list[dict[str, Any]]:
        """Format for Anthropic messages API tools param."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]

    def stats(self) -> dict[str, int]:
        domains = {}
        for t in self._tools.values():
            for d in t.domains:
                domains[d] = domains.get(d, 0) + 1
        return {
            "total": len(self._tools),
            "deprecated": sum(1 for t in self._tools.values() if t.deprecated),
            "by_domain": domains,
        }


# Singleton — import from app code as:
#   from app.agents.tools.registry import registry
registry = ToolRegistry()
