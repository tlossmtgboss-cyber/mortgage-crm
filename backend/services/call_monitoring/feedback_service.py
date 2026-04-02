"""
Agent Feedback Service — learns from LO approval/rejection patterns.

Tracks per-agent, per-artifact-type approval rates and generates
feedback summaries that are injected into agent system prompts.

This creates a feedback loop: agents that produce artifacts the LO
consistently rejects will get prompt adjustments to be more selective.
"""

import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Thresholds for generating feedback
LOW_APPROVAL_THRESHOLD = 0.50   # Below 50% → agent is producing too much noise
HIGH_APPROVAL_THRESHOLD = 0.90  # Above 90% → agent is well-calibrated
MIN_SAMPLES = 5                 # Need at least 5 artifacts before giving feedback


class AgentFeedbackService:
    """Tracks and applies agent feedback from LO approval patterns."""

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id

    def get_approval_stats(
        self,
        agent_type: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get approval/rejection statistics per agent and artifact type.

        Returns breakdown of how often each agent's artifacts are
        approved vs rejected by the LO.
        """
        params = {
            "org_id": self.organization_id,
            "since": datetime.now(timezone.utc) - timedelta(days=days),
        }

        agent_filter = ""
        if agent_type:
            agent_filter = "AND ar.agent_type = :agent_type"
            params["agent_type"] = agent_type

        sql = """
            SELECT
                ar.agent_type,
                ca.artifact_type,
                COUNT(*) as total,
                COUNT(CASE WHEN ca.approval_status = 'approved' THEN 1 END) as approved,
                COUNT(CASE WHEN ca.approval_status = 'rejected' THEN 1 END) as rejected,
                COUNT(CASE WHEN ca.approval_status = 'pending' THEN 1 END) as pending,
                AVG(ca.confidence) as avg_confidence
            FROM call_artifacts ca
            JOIN agent_runs ar ON ar.id = ca.run_id
            WHERE ca.organization_id = :org_id
                AND ca.created_at >= :since
        """
        if agent_filter:
            sql += "                " + agent_filter + "\n"
        sql += """            GROUP BY ar.agent_type, ca.artifact_type
            ORDER BY ar.agent_type, total DESC
        """
        rows = self.db.execute(text(sql), params).fetchall()

        stats = {}
        for row in rows:
            agent = row.agent_type
            if agent not in stats:
                stats[agent] = {
                    "agent_type": agent,
                    "total_artifacts": 0,
                    "total_approved": 0,
                    "total_rejected": 0,
                    "approval_rate": 0.0,
                    "by_type": {},
                }

            decided = row.approved + row.rejected
            approval_rate = (row.approved / decided * 100) if decided > 0 else None

            stats[agent]["total_artifacts"] += row.total
            stats[agent]["total_approved"] += row.approved
            stats[agent]["total_rejected"] += row.rejected
            stats[agent]["by_type"][row.artifact_type] = {
                "total": row.total,
                "approved": row.approved,
                "rejected": row.rejected,
                "pending": row.pending,
                "approval_rate": round(approval_rate, 1) if approval_rate is not None else None,
                "avg_confidence": round(float(row.avg_confidence), 2) if row.avg_confidence else None,
            }

        # Calculate overall approval rates
        for agent, data in stats.items():
            decided = data["total_approved"] + data["total_rejected"]
            data["approval_rate"] = round(
                (data["total_approved"] / decided * 100) if decided > 0 else 0, 1
            )

        return {
            "organization_id": self.organization_id,
            "period_days": days,
            "agents": stats,
        }

    def generate_feedback_prompt(
        self,
        agent_type: str,
        days: int = 30,
    ) -> Optional[str]:
        """
        Generate a feedback injection for an agent's system prompt.

        Returns None if there's not enough data or the agent is well-calibrated.
        Returns a feedback string to append to the system prompt if the agent
        needs adjustment.
        """
        stats = self.get_approval_stats(agent_type=agent_type, days=days)
        agent_stats = stats.get("agents", {}).get(agent_type)

        if not agent_stats:
            return None

        decided = agent_stats["total_approved"] + agent_stats["total_rejected"]
        if decided < MIN_SAMPLES:
            return None

        overall_rate = agent_stats["approval_rate"] / 100.0

        if overall_rate >= HIGH_APPROVAL_THRESHOLD:
            # Agent is well-calibrated — no feedback needed
            return None

        # Build feedback based on per-type approval rates
        feedback_lines = []
        feedback_lines.append(
            f"\n## Quality Feedback (based on {decided} reviewed artifacts, last {days} days)"
        )

        if overall_rate < LOW_APPROVAL_THRESHOLD:
            feedback_lines.append(
                f"WARNING: Your overall approval rate is {agent_stats['approval_rate']}%. "
                f"The loan officer is rejecting more than half of your artifacts. "
                f"Be MORE SELECTIVE. Only include artifacts with strong evidence from the transcript."
            )

        # Per-type feedback
        low_types = []
        for artifact_type, type_stats in agent_stats["by_type"].items():
            type_decided = type_stats["approved"] + type_stats["rejected"]
            if type_decided < 3:
                continue

            type_rate = type_stats["approval_rate"]
            if type_rate is not None and type_rate < LOW_APPROVAL_THRESHOLD * 100:
                low_types.append((artifact_type, type_rate, type_stats["rejected"]))

        if low_types:
            feedback_lines.append("\nArtifact types with low approval rates:")
            for atype, rate, rejected in sorted(low_types, key=lambda x: x[1]):
                feedback_lines.append(
                    f"- {atype}: {rate}% approved ({rejected} rejected). "
                    f"Raise your confidence threshold for this type."
                )

        # Look for patterns in rejected artifacts
        rejected_titles = self._get_recently_rejected(agent_type, limit=10)
        if rejected_titles:
            feedback_lines.append(
                f"\nRecently rejected artifact examples (avoid similar):"
            )
            for title in rejected_titles[:5]:
                feedback_lines.append(f"  - \"{title}\"")

        if len(feedback_lines) <= 1:
            return None

        return "\n".join(feedback_lines)

    def get_agent_report(self, days: int = 30) -> Dict[str, Any]:
        """
        Generate a comprehensive agent performance report.
        Useful for the morning briefing or admin dashboard.
        """
        stats = self.get_approval_stats(days=days)
        agents = stats.get("agents", {})

        report = {
            "period_days": days,
            "total_agents": len(agents),
            "agents": [],
        }

        for agent_type, data in agents.items():
            feedback = self.generate_feedback_prompt(agent_type, days)
            report["agents"].append({
                "agent_type": agent_type,
                "total_artifacts": data["total_artifacts"],
                "approval_rate": data["approval_rate"],
                "needs_tuning": feedback is not None,
                "top_types": sorted(
                    data["by_type"].items(),
                    key=lambda x: x[1]["total"],
                    reverse=True,
                )[:3],
            })

        return report

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _get_recently_rejected(
        self, agent_type: str, limit: int = 10
    ) -> List[str]:
        """Get titles of recently rejected artifacts for this agent."""
        rows = self.db.execute(text("""
            SELECT ca.title
            FROM call_artifacts ca
            JOIN agent_runs ar ON ar.id = ca.run_id
            WHERE ca.organization_id = :org_id
                AND ar.agent_type = :agent_type
                AND ca.approval_status = 'rejected'
            ORDER BY ca.updated_at DESC
            LIMIT :limit
        """), {
            "org_id": self.organization_id,
            "agent_type": agent_type,
            "limit": limit,
        }).fetchall()

        return [row.title for row in rows if row.title]
