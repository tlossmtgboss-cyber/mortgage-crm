"""Agent registry — loads ``agents.yaml`` and instantiates agents.

Most of the 100 agents are handled by :class:`GenericAgent` driven by
their YAML spec. A handful of high-risk agents (secret handling,
schema changes, consent gateway) have specialist subclasses that add
extra guardrails; those are registered in :data:`SPECIALIST_CLASSES`.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import yaml

from agents.base import BaseAgent, GenericAgent
from agents.critical import (
    IdContractValidator,
    SecretStartupValidator,
    UnifiedConsentGateway,
    FailClosedPolicy,
)
from agents.meta import (
    Coordinator,
    DependencyResolver,
    ConflictDetector,
    HumanApprover,
    Observer,
)
from orchestrator.state import AgentSpec

log = logging.getLogger(__name__)

# --- Specialist overrides -------------------------------------------------
# Only agents whose behaviour warrants custom code live here. Everything
# else is handled by GenericAgent via its YAML spec.
SPECIALIST_CLASSES: dict[str, type[BaseAgent]] = {
    # Critical specialists
    "A07": IdContractValidator,
    "A23": SecretStartupValidator,
    "A26": FailClosedPolicy,
    "A30": UnifiedConsentGateway,
    # Meta specialists
    "M91": Coordinator,
    "M92": DependencyResolver,
    "M93": ConflictDetector,
    "M99": HumanApprover,
    "M100": Observer,
}


class AgentRegistry:
    """Loads the YAML registry and vends agent instances."""

    def __init__(self, yaml_path: Path):
        self.yaml_path = yaml_path
        self._specs: dict[str, AgentSpec] = {}
        self._load()

    def _load(self) -> None:
        with self.yaml_path.open() as f:
            doc = yaml.safe_load(f)
        for entry in doc.get("agents", []):
            self._specs[entry["id"]] = entry  # type: ignore[assignment]
        if len(self._specs) != doc.get("total_agents", len(self._specs)):
            log.warning(
                "registry count mismatch: %d agents loaded, %d declared",
                len(self._specs), doc.get("total_agents"),
            )
        log.info("registry loaded %d agents", len(self._specs))

    def all_specs(self) -> dict[str, AgentSpec]:
        return dict(self._specs)

    def specs_for_findings(self, finding_ids: Iterable[int]) -> list[AgentSpec]:
        selected = set(finding_ids)
        if not selected:
            return list(self._specs.values())
        return [
            s for s in self._specs.values()
            if s.get("tier") == "meta" or set(s.get("finding_refs", [])) & selected
        ]

    def build(self, agent_id: str) -> BaseAgent:
        spec = self._specs[agent_id]
        cls = SPECIALIST_CLASSES.get(agent_id, GenericAgent)
        return cls(spec)

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._specs

    def __len__(self) -> int:
        return len(self._specs)
