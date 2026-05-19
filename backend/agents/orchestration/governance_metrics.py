"""
Governance Metrics Store — In-Memory, Thread-Safe Telemetry Buffer
=================================================================

Wave 3 (D3 audit remediation #2). Wave 1 introduced three runtime guards
(``TokenBudgetManager``, ``ComplianceGuard``, ``HallucinationGuard``) that
emit useful per-event signals but discard them after returning to the
caller. This module collects those signals into a single, thread-safe,
**bounded** in-process buffer so a governance dashboard can read them.

Design notes
------------
* **In-memory only.** Storage is process-local — uses ``deque(maxlen=1000)``
  for each event class to bound memory. In a multi-worker / multi-instance
  deploy (gunicorn workers, Railway replicas) each worker has its own
  buffer. Wave 4 candidate: push events to Redis Streams or a Postgres
  ``agent_governance_events`` table for cross-worker aggregation and
  historical reporting / chargeback.
* **Never raises.** The three Wave 1 guards call this store from inside
  ``try/except`` blocks; even so, every public method is defensive and
  swallows internal errors rather than propagating.
* **Thread safety.** A single ``threading.Lock`` guards all mutations
  and reads. The critical sections are tiny (append + counter bump) so
  contention is negligible at typical agent traffic.

Public surface
--------------
``governance_metrics.record_compliance_event(...)``
``governance_metrics.record_hallucination_event(...)``
``governance_metrics.record_token_usage(...)``
``governance_metrics.get_per_agent_summary(agent_id)``
``governance_metrics.get_fleet_summary()``
``governance_metrics.recent_compliance(limit=50)``
``governance_metrics.recent_hallucinations(limit=50)``
``governance_metrics.budgets_snapshot()``
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

# Bound the buffers so a long-running worker can never OOM from event volume.
_BUFFER_MAXLEN = 1000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GovernanceMetricsStore:
    """
    Thread-safe, in-memory store of recent governance events per agent.

    Events are append-only ring buffers (one global ring per event class,
    plus per-agent rings). Aggregate counters live alongside so that
    summaries are O(1) reads.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Global ring buffers (newest-last).
        self._compliance_events: Deque[Dict[str, Any]] = deque(maxlen=_BUFFER_MAXLEN)
        self._hallucination_events: Deque[Dict[str, Any]] = deque(maxlen=_BUFFER_MAXLEN)
        self._token_events: Deque[Dict[str, Any]] = deque(maxlen=_BUFFER_MAXLEN)

        # Per-agent ring buffers (newest-last).
        self._compliance_per_agent: Dict[str, Deque[Dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=_BUFFER_MAXLEN)
        )
        self._hallucination_per_agent: Dict[str, Deque[Dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=_BUFFER_MAXLEN)
        )
        self._token_per_agent: Dict[str, Deque[Dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=_BUFFER_MAXLEN)
        )

        # Per-agent aggregate counters (cheap roll-ups).
        # role lookup map: agent_id -> last-seen role (best effort).
        self._agent_role: Dict[str, str] = {}

        self._compliance_count: Dict[str, int] = defaultdict(int)
        self._compliance_violation_count: Dict[str, int] = defaultdict(int)
        self._compliance_escalation_count: Dict[str, int] = defaultdict(int)

        self._hallucination_count: Dict[str, int] = defaultdict(int)
        self._hallucination_unverified_total: Dict[str, int] = defaultdict(int)
        # rolling sum + count so we can compute mean confidence on demand
        self._hallucination_conf_sum: Dict[str, float] = defaultdict(float)

        self._token_input_total: Dict[str, int] = defaultdict(int)
        self._token_output_total: Dict[str, int] = defaultdict(int)
        self._token_call_count: Dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # Recording methods (callers wrap in try/except — but we are also
    # defensive here).
    # ------------------------------------------------------------------

    def record_compliance_event(
        self,
        agent_id: str,
        agent_role: str,
        violation_count: int,
        violations: Optional[List[Dict[str, Any]]] = None,
        escalated: bool = False,
    ) -> None:
        try:
            agent_id = str(agent_id) if agent_id is not None else "unknown"
            agent_role = str(agent_role) if agent_role is not None else "unknown"
            violation_count = int(violation_count or 0)
            escalated = bool(escalated)
            event = {
                "ts": _utc_now_iso(),
                "agent_id": agent_id,
                "agent_role": agent_role,
                "violation_count": violation_count,
                "escalated": escalated,
                "violations": list(violations or [])[:20],  # trim huge payloads
            }
            with self._lock:
                self._agent_role[agent_id] = agent_role
                self._compliance_events.append(event)
                self._compliance_per_agent[agent_id].append(event)
                self._compliance_count[agent_id] += 1
                self._compliance_violation_count[agent_id] += violation_count
                if escalated:
                    self._compliance_escalation_count[agent_id] += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("governance_metrics.record_compliance_event swallowed: %s", exc)

    def record_hallucination_event(
        self,
        agent_id: str,
        agent_role: str,
        confidence: float,
        unverified_claims: Optional[List[str]] = None,
    ) -> None:
        try:
            agent_id = str(agent_id) if agent_id is not None else "unknown"
            agent_role = str(agent_role) if agent_role is not None else "unknown"
            try:
                conf = float(confidence)
            except (TypeError, ValueError):
                conf = 1.0
            unv = list(unverified_claims or [])[:20]
            event = {
                "ts": _utc_now_iso(),
                "agent_id": agent_id,
                "agent_role": agent_role,
                "confidence": round(conf, 4),
                "unverified_claims": unv,
                "unverified_count": len(unv),
            }
            with self._lock:
                self._agent_role[agent_id] = agent_role
                self._hallucination_events.append(event)
                self._hallucination_per_agent[agent_id].append(event)
                self._hallucination_count[agent_id] += 1
                self._hallucination_unverified_total[agent_id] += len(unv)
                self._hallucination_conf_sum[agent_id] += conf
        except Exception as exc:  # noqa: BLE001
            logger.debug("governance_metrics.record_hallucination_event swallowed: %s", exc)

    def record_token_usage(
        self,
        agent_id: str,
        agent_role: str,
        input_tokens: int,
        output_tokens: int,
        model: Optional[str] = None,
    ) -> None:
        try:
            agent_id = str(agent_id) if agent_id is not None else "unknown"
            agent_role = str(agent_role) if agent_role is not None else "unknown"
            in_tok = int(input_tokens or 0)
            out_tok = int(output_tokens or 0)
            event = {
                "ts": _utc_now_iso(),
                "agent_id": agent_id,
                "agent_role": agent_role,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "total_tokens": in_tok + out_tok,
                "model": str(model) if model else None,
            }
            with self._lock:
                self._agent_role[agent_id] = agent_role
                self._token_events.append(event)
                self._token_per_agent[agent_id].append(event)
                self._token_input_total[agent_id] += in_tok
                self._token_output_total[agent_id] += out_tok
                self._token_call_count[agent_id] += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("governance_metrics.record_token_usage swallowed: %s", exc)

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def _avg_confidence(self, agent_id: str) -> float:
        n = self._hallucination_count.get(agent_id, 0)
        if n <= 0:
            return 1.0
        return round(self._hallucination_conf_sum.get(agent_id, 0.0) / n, 4)

    def get_per_agent_summary(self, agent_id: str, last_n: int = 20) -> Dict[str, Any]:
        """
        Return counters + the last ``last_n`` events of each type for one agent.
        """
        try:
            agent_id = str(agent_id)
            last_n = max(0, int(last_n))
            with self._lock:
                role = self._agent_role.get(agent_id, "unknown")
                comp = self._compliance_per_agent.get(agent_id, deque())
                hall = self._hallucination_per_agent.get(agent_id, deque())
                tok = self._token_per_agent.get(agent_id, deque())

                return {
                    "agent_id": agent_id,
                    "agent_role": role,
                    "compliance": {
                        "event_count": self._compliance_count.get(agent_id, 0),
                        "violation_count": self._compliance_violation_count.get(agent_id, 0),
                        "escalation_count": self._compliance_escalation_count.get(agent_id, 0),
                        "recent": list(comp)[-last_n:] if last_n else [],
                    },
                    "hallucination": {
                        "event_count": self._hallucination_count.get(agent_id, 0),
                        "unverified_total": self._hallucination_unverified_total.get(agent_id, 0),
                        "avg_confidence": self._avg_confidence(agent_id),
                        "recent": list(hall)[-last_n:] if last_n else [],
                    },
                    "tokens": {
                        "call_count": self._token_call_count.get(agent_id, 0),
                        "input_total": self._token_input_total.get(agent_id, 0),
                        "output_total": self._token_output_total.get(agent_id, 0),
                        "grand_total": (
                            self._token_input_total.get(agent_id, 0)
                            + self._token_output_total.get(agent_id, 0)
                        ),
                        "recent": list(tok)[-last_n:] if last_n else [],
                    },
                }
        except Exception as exc:  # noqa: BLE001
            logger.debug("governance_metrics.get_per_agent_summary swallowed: %s", exc)
            return {"agent_id": str(agent_id), "error": "summary_unavailable"}

    def get_fleet_summary(self, top_n: int = 5) -> Dict[str, Any]:
        """
        Roll-up across all agents:
          * per-agent totals
          * per-role totals
          * top-N hot spots for each event class
        """
        try:
            top_n = max(1, int(top_n))
            with self._lock:
                agent_ids: set[str] = set()
                agent_ids.update(self._compliance_count.keys())
                agent_ids.update(self._hallucination_count.keys())
                agent_ids.update(self._token_call_count.keys())

                per_agent: List[Dict[str, Any]] = []
                per_role: Dict[str, Dict[str, int]] = defaultdict(
                    lambda: {
                        "agents": 0,
                        "compliance_events": 0,
                        "compliance_violations": 0,
                        "compliance_escalations": 0,
                        "hallucination_events": 0,
                        "unverified_claims": 0,
                        "token_calls": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                    }
                )

                for aid in agent_ids:
                    role = self._agent_role.get(aid, "unknown")
                    entry: Dict[str, Any] = {
                        "agent_id": aid,
                        "agent_role": role,
                        "compliance_events": self._compliance_count.get(aid, 0),
                        "compliance_violations": self._compliance_violation_count.get(aid, 0),
                        "compliance_escalations": self._compliance_escalation_count.get(aid, 0),
                        "hallucination_events": self._hallucination_count.get(aid, 0),
                        "unverified_claims": self._hallucination_unverified_total.get(aid, 0),
                        "avg_confidence": self._avg_confidence(aid),
                        "token_calls": self._token_call_count.get(aid, 0),
                        "input_tokens": self._token_input_total.get(aid, 0),
                        "output_tokens": self._token_output_total.get(aid, 0),
                        "total_tokens": (
                            self._token_input_total.get(aid, 0)
                            + self._token_output_total.get(aid, 0)
                        ),
                    }
                    per_agent.append(entry)

                    r = per_role[role]
                    r["agents"] += 1
                    r["compliance_events"] += entry["compliance_events"]
                    r["compliance_violations"] += entry["compliance_violations"]
                    r["compliance_escalations"] += entry["compliance_escalations"]
                    r["hallucination_events"] += entry["hallucination_events"]
                    r["unverified_claims"] += entry["unverified_claims"]
                    r["token_calls"] += entry["token_calls"]
                    r["input_tokens"] += entry["input_tokens"]
                    r["output_tokens"] += entry["output_tokens"]

                hot_compliance = sorted(
                    per_agent, key=lambda x: x["compliance_violations"], reverse=True
                )[:top_n]
                hot_hallucination = sorted(
                    per_agent, key=lambda x: x["unverified_claims"], reverse=True
                )[:top_n]
                hot_tokens = sorted(
                    per_agent, key=lambda x: x["total_tokens"], reverse=True
                )[:top_n]

                return {
                    "generated_at": _utc_now_iso(),
                    "agent_count": len(per_agent),
                    "totals": {
                        "compliance_events": sum(e["compliance_events"] for e in per_agent),
                        "compliance_violations": sum(
                            e["compliance_violations"] for e in per_agent
                        ),
                        "compliance_escalations": sum(
                            e["compliance_escalations"] for e in per_agent
                        ),
                        "hallucination_events": sum(
                            e["hallucination_events"] for e in per_agent
                        ),
                        "unverified_claims": sum(e["unverified_claims"] for e in per_agent),
                        "token_calls": sum(e["token_calls"] for e in per_agent),
                        "input_tokens": sum(e["input_tokens"] for e in per_agent),
                        "output_tokens": sum(e["output_tokens"] for e in per_agent),
                    },
                    "per_agent": per_agent,
                    "per_role": dict(per_role),
                    "hot_spots": {
                        "compliance": hot_compliance,
                        "hallucination": hot_hallucination,
                        "tokens": hot_tokens,
                    },
                }
        except Exception as exc:  # noqa: BLE001
            logger.debug("governance_metrics.get_fleet_summary swallowed: %s", exc)
            return {"generated_at": _utc_now_iso(), "error": "summary_unavailable"}

    def recent_compliance(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            limit = max(1, min(int(limit), _BUFFER_MAXLEN))
            with self._lock:
                return list(self._compliance_events)[-limit:][::-1]
        except Exception as _exc:  # noqa: BLE001
            return []

    def recent_hallucinations(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            limit = max(1, min(int(limit), _BUFFER_MAXLEN))
            with self._lock:
                return list(self._hallucination_events)[-limit:][::-1]
        except Exception as _exc:  # noqa: BLE001
            return []

    def recent_tokens(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            limit = max(1, min(int(limit), _BUFFER_MAXLEN))
            with self._lock:
                return list(self._token_events)[-limit:][::-1]
        except Exception as _exc:  # noqa: BLE001
            return []

    def reset(self) -> None:
        """Test/maintenance helper — clear all buffers and counters."""
        with self._lock:
            self._compliance_events.clear()
            self._hallucination_events.clear()
            self._token_events.clear()
            self._compliance_per_agent.clear()
            self._hallucination_per_agent.clear()
            self._token_per_agent.clear()
            self._agent_role.clear()
            self._compliance_count.clear()
            self._compliance_violation_count.clear()
            self._compliance_escalation_count.clear()
            self._hallucination_count.clear()
            self._hallucination_unverified_total.clear()
            self._hallucination_conf_sum.clear()
            self._token_input_total.clear()
            self._token_output_total.clear()
            self._token_call_count.clear()


# Module-level singleton.
governance_metrics = GovernanceMetricsStore()


__all__ = ["GovernanceMetricsStore", "governance_metrics"]
