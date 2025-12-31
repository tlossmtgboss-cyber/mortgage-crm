"""
SLA Task Engine
Creates workflow tasks based on intake signals and scores
"""

from typing import Any, Dict, List, Optional
from uuid import uuid4
from .models import Session, SLATask, TruthBand, Flag


class SLAEngine:
    """Creates SLA tasks based on intake outcomes"""

    def __init__(self, sla_config: Dict[str, Any]):
        self.config = sla_config
        self.score_band_hooks = sla_config.get("score_band_hooks", [])
        self.flag_hooks = sla_config.get("flag_hooks", [])
        self.completion_hooks = sla_config.get("completion_hooks", [])
        self.time_based_hooks = sla_config.get("time_based_hooks", [])

    def evaluate_hooks(
        self,
        session: Session,
        event_type: str = "score_update",
    ) -> List[SLATask]:
        """Evaluate all hooks and create tasks"""
        tasks = []

        if event_type in ["score_update", "session_complete"]:
            # Check score band hooks
            tasks.extend(self._check_score_band_hooks(session))

        if event_type in ["flag_added", "session_complete"]:
            # Check flag hooks
            tasks.extend(self._check_flag_hooks(session))

        if event_type == "session_complete":
            # Check completion hooks
            tasks.extend(self._check_completion_hooks(session))

        # Deduplicate tasks by code
        seen = set()
        unique_tasks = []
        for task in tasks:
            if task.code not in seen:
                seen.add(task.code)
                unique_tasks.append(task)

        return unique_tasks

    def _check_score_band_hooks(self, session: Session) -> List[SLATask]:
        """Check score-based hooks"""
        tasks = []
        truth_band = session.scores.truth_band

        for hook in self.score_band_hooks:
            band = hook.get("band")
            if self._matches_band(truth_band, band):
                task = self._create_task_from_hook(hook, session)
                if task:
                    tasks.append(task)

        return tasks

    def _check_flag_hooks(self, session: Session) -> List[SLATask]:
        """Check flag-based hooks"""
        tasks = []

        for hook in self.flag_hooks:
            trigger_flag = hook.get("when_flag")
            if trigger_flag and session.has_flag(trigger_flag):
                task = self._create_task_from_hook(hook, session)
                if task:
                    tasks.append(task)

        return tasks

    def _check_completion_hooks(self, session: Session) -> List[SLATask]:
        """Check completion-based hooks"""
        tasks = []

        for hook in self.completion_hooks:
            conditions = hook.get("when", {})

            # Check all conditions
            if self._check_conditions(conditions, session):
                task = self._create_task_from_hook(hook, session)
                if task:
                    tasks.append(task)

        return tasks

    def _matches_band(self, actual: TruthBand, expected: str) -> bool:
        """Check if actual band matches expected"""
        if expected == "RED":
            return actual == TruthBand.RED
        elif expected == "ORANGE":
            return actual == TruthBand.ORANGE
        elif expected == "YELLOW":
            return actual == TruthBand.YELLOW
        elif expected == "LIGHT_GREEN":
            return actual == TruthBand.LIGHT_GREEN
        elif expected == "GREEN":
            return actual == TruthBand.GREEN
        elif expected == "RED_OR_ORANGE":
            return actual in [TruthBand.RED, TruthBand.ORANGE]
        return False

    def _check_conditions(
        self,
        conditions: Dict[str, Any],
        session: Session,
    ) -> bool:
        """Check if all conditions are met"""
        # Check truth score
        if "truth_score_below" in conditions:
            if session.scores.underwriting_truth_score >= conditions["truth_score_below"]:
                return False

        if "truth_score_above" in conditions:
            if session.scores.underwriting_truth_score <= conditions["truth_score_above"]:
                return False

        # Check readiness score
        if "readiness_below" in conditions:
            if session.scores.lo_readiness_score >= conditions["readiness_below"]:
                return False

        # Check hesitation
        if "hesitation_band" in conditions:
            if session.scores.hesitation_band != conditions["hesitation_band"]:
                return False

        # Check flag presence
        if "has_flag" in conditions:
            if not session.has_flag(conditions["has_flag"]):
                return False

        if "has_any_flag" in conditions:
            if not any(session.has_flag(f) for f in conditions["has_any_flag"]):
                return False

        # Check section
        if "section" in conditions:
            if session.current_section != conditions["section"]:
                return False

        return True

    def _create_task_from_hook(
        self,
        hook: Dict[str, Any],
        session: Session,
    ) -> Optional[SLATask]:
        """Create an SLATask from a hook definition"""
        create_task = hook.get("create_task")
        if not create_task:
            return None

        # Format title and description with session values
        title = self._format_text(create_task.get("title", ""), session)
        description = self._format_text(create_task.get("description", ""), session)

        return SLATask(
            session_id=session.session_id,
            code=create_task.get("code", f"TASK_{uuid4().hex[:8].upper()}"),
            title=title,
            description=description,
            priority=create_task.get("priority", "P2"),
            status="OPEN",
            assignee_role=create_task.get("assignee_role"),
            due_hours=create_task.get("due_hours"),
        )

    def _format_text(self, text: str, session: Session) -> str:
        """Format text with session values"""
        replacements = {
            "{session_id}": session.session_id,
            "{loan_id}": session.loan_id or "",
            "{truth_score}": str(round(session.scores.underwriting_truth_score, 1)),
            "{readiness_score}": str(round(session.scores.lo_readiness_score, 1)),
            "{truth_band}": str(session.scores.truth_band),
            "{current_section}": session.current_section,
        }

        for key, value in replacements.items():
            text = text.replace(key, value)

        return text

    def get_task_summary(self, tasks: List[SLATask]) -> Dict[str, Any]:
        """Get summary of created tasks"""
        by_priority = {}
        by_assignee = {}

        for task in tasks:
            # By priority
            priority = task.priority
            if priority not in by_priority:
                by_priority[priority] = []
            by_priority[priority].append(task.code)

            # By assignee
            assignee = task.assignee_role or "unassigned"
            if assignee not in by_assignee:
                by_assignee[assignee] = []
            by_assignee[assignee].append(task.code)

        return {
            "total_tasks": len(tasks),
            "by_priority": by_priority,
            "by_assignee": by_assignee,
            "urgent_count": len(by_priority.get("P0", [])) + len(by_priority.get("P1", [])),
        }


def create_sla_engine(sla_config: Dict[str, Any]) -> SLAEngine:
    """Factory function to create SLA engine"""
    return SLAEngine(sla_config)
