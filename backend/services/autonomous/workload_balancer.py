"""
Workload Auto-Balancer

Monitors per-user file queue depth within an organization, detects imbalance
(one processor at capacity while another has bandwidth), and auto-redistributes
files when the imbalance exceeds a configurable threshold.

Escalation path:
  1. Detect imbalance -> produce suggestions
  2. If auto_approve is enabled, immediately reassign
  3. Otherwise, create Notification records for Branch Manager

Target: complete analysis + rebalance within 60 seconds of detection.

Usage:
    from services.autonomous.workload_balancer import WorkloadBalancer

    balancer = WorkloadBalancer()
    analysis = await balancer.analyze_workload(org_id=1, db=session)
    result   = await balancer.rebalance(org_id=1, db=session)
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from database.models.core import User
from database.models.lead_loan import Loan
from database.models.security import Notification

logger = logging.getLogger(__name__)

TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD",
    "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
})

# Default thresholds
DEFAULT_IMBALANCE_RATIO = 2.0  # Flag when top user has 2x the median
DEFAULT_MAX_FILES_PER_USER = 50  # Capacity ceiling
DEFAULT_MIN_FILES_TO_TRIGGER = 5  # Don't rebalance if total is trivial


class WorkloadBalancer:
    """Analyzes and rebalances loan-file assignments across processors."""

    def __init__(
        self,
        imbalance_ratio: float = DEFAULT_IMBALANCE_RATIO,
        max_files_per_user: int = DEFAULT_MAX_FILES_PER_USER,
        min_files_to_trigger: int = DEFAULT_MIN_FILES_TO_TRIGGER,
        auto_approve: bool = False,
    ):
        self.imbalance_ratio = imbalance_ratio
        self.max_files_per_user = max_files_per_user
        self.min_files_to_trigger = min_files_to_trigger
        self.auto_approve = auto_approve
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_workload(self, org_id: int, db: Session) -> dict[str, Any]:
        """Return workload distribution and flag imbalances.

        Returns:
            {
                "org_id": int,
                "timestamp": str,
                "total_active_files": int,
                "user_loads": [{"user_id": int, "name": str, "file_count": int, "status": str}],
                "imbalanced": bool,
                "overloaded_users": [...],
                "underloaded_users": [...],
                "suggestions": [{"move_loan_id": int, "from_user_id": int, "to_user_id": int}],
            }
        """
        self.logger.info("Analyzing workload for org %s", org_id)
        now = datetime.now(timezone.utc)

        user_loads = self._get_user_loads(org_id, db)
        if not user_loads:
            return {
                "org_id": org_id,
                "timestamp": now.isoformat(),
                "total_active_files": 0,
                "user_loads": [],
                "imbalanced": False,
                "overloaded_users": [],
                "underloaded_users": [],
                "suggestions": [],
            }

        total = sum(ul["file_count"] for ul in user_loads)
        if total < self.min_files_to_trigger:
            return {
                "org_id": org_id,
                "timestamp": now.isoformat(),
                "total_active_files": total,
                "user_loads": user_loads,
                "imbalanced": False,
                "overloaded_users": [],
                "underloaded_users": [],
                "suggestions": [],
            }

        median_load = self._median([ul["file_count"] for ul in user_loads])
        threshold = max(median_load * self.imbalance_ratio, self.max_files_per_user)

        overloaded = [ul for ul in user_loads if ul["file_count"] > threshold]
        underloaded = [
            ul for ul in user_loads
            if ul["file_count"] < median_load and ul["file_count"] < self.max_files_per_user
        ]
        imbalanced = len(overloaded) > 0 and len(underloaded) > 0

        # Tag status
        for ul in user_loads:
            if ul["file_count"] > threshold:
                ul["status"] = "overloaded"
            elif ul["file_count"] < median_load * 0.5:
                ul["status"] = "underloaded"
            else:
                ul["status"] = "balanced"

        suggestions = self._generate_suggestions(overloaded, underloaded, org_id, db) if imbalanced else []

        return {
            "org_id": org_id,
            "timestamp": now.isoformat(),
            "total_active_files": total,
            "user_loads": user_loads,
            "imbalanced": imbalanced,
            "overloaded_users": overloaded,
            "underloaded_users": underloaded,
            "suggestions": suggestions,
        }

    async def rebalance(self, org_id: int, db: Session) -> dict[str, Any]:
        """Perform redistribution of files. Respects auto_approve flag.

        Returns:
            {
                "org_id": int,
                "timestamp": str,
                "action": "rebalanced" | "suggestions_created" | "no_action",
                "moves": [{"loan_id": int, "from_user_id": int, "to_user_id": int}],
                "notifications_created": int,
            }
        """
        self.logger.info("Rebalance requested for org %s", org_id)
        now = datetime.now(timezone.utc)

        analysis = await self.analyze_workload(org_id, db)
        if not analysis["imbalanced"] or not analysis["suggestions"]:
            return {
                "org_id": org_id,
                "timestamp": now.isoformat(),
                "action": "no_action",
                "moves": [],
                "notifications_created": 0,
            }

        suggestions = analysis["suggestions"]

        if self.auto_approve:
            moves = self._execute_moves(suggestions, db)
            db.commit()
            self.logger.info(
                "Auto-rebalanced %d files for org %s", len(moves), org_id,
            )
            return {
                "org_id": org_id,
                "timestamp": now.isoformat(),
                "action": "rebalanced",
                "moves": moves,
                "notifications_created": 0,
            }

        # Otherwise create notifications for manager approval
        notif_count = self._create_rebalance_notifications(org_id, suggestions, db)
        db.commit()
        return {
            "org_id": org_id,
            "timestamp": now.isoformat(),
            "action": "suggestions_created",
            "moves": [],
            "notifications_created": notif_count,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_user_loads(self, org_id: int, db: Session) -> list[dict[str, Any]]:
        """Query active file count per user (loan officer / processor)."""
        rows = (
            db.query(
                Loan.owner_id,
                func.count(Loan.id).label("file_count"),
            )
            .filter(
                Loan.organization_id == org_id,
                ~Loan.stage.in_(TERMINAL_STAGES),
                Loan.owner_id.isnot(None),
            )
            .group_by(Loan.owner_id)
            .all()
        )
        if not rows:
            return []

        user_ids = [r.owner_id for r in rows]
        users_by_id = {
            u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()
        }

        result = []
        for r in rows:
            user = users_by_id.get(r.owner_id)
            result.append({
                "user_id": r.owner_id,
                "name": f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unknown",
                "file_count": r.file_count,
                "status": "unknown",
            })

        result.sort(key=lambda x: x["file_count"], reverse=True)
        return result

    def _generate_suggestions(
        self,
        overloaded: list[dict],
        underloaded: list[dict],
        org_id: int,
        db: Session,
    ) -> list[dict[str, Any]]:
        """Produce move suggestions: take newest files from overloaded, assign to underloaded."""
        suggestions: list[dict[str, Any]] = []
        under_idx = 0

        for over_user in overloaded:
            excess = over_user["file_count"] - self.max_files_per_user
            if excess <= 0:
                continue

            # Get the newest (most recently assigned) active loans for this user
            movable = (
                db.query(Loan.id)
                .filter(
                    Loan.organization_id == org_id,
                    Loan.owner_id == over_user["user_id"],
                    ~Loan.stage.in_(TERMINAL_STAGES),
                )
                .order_by(Loan.created_at.desc())
                .limit(excess)
                .all()
            )

            for (loan_id,) in movable:
                if under_idx >= len(underloaded):
                    break
                target = underloaded[under_idx]
                suggestions.append({
                    "move_loan_id": loan_id,
                    "from_user_id": over_user["user_id"],
                    "to_user_id": target["user_id"],
                })
                target["file_count"] += 1
                if target["file_count"] >= self.max_files_per_user:
                    under_idx += 1

        return suggestions

    def _execute_moves(self, suggestions: list[dict], db: Session) -> list[dict]:
        """Actually reassign loans. Returns executed moves."""
        executed: list[dict] = []
        for s in suggestions:
            loan = db.query(Loan).filter(Loan.id == s["move_loan_id"]).first()
            if loan and loan.owner_id == s["from_user_id"]:
                loan.owner_id = s["to_user_id"]
                loan.updated_at = datetime.now(timezone.utc)
                executed.append(s)
        return executed

    def _create_rebalance_notifications(
        self, org_id: int, suggestions: list[dict], db: Session,
    ) -> int:
        """Create Notification records for branch manager to approve moves."""
        # Find admins/managers in org
        managers = (
            db.query(User)
            .filter(
                User.organization_id == org_id,
                User.is_active == True,  # noqa: E712
                User.role.in_(["Admin", "Branch Manager", "admin", "branch_manager"]),
            )
            .all()
        )
        if not managers:
            self.logger.warning("No managers found for org %s to notify", org_id)
            return 0

        now = datetime.now(timezone.utc)
        count = 0
        summary = f"Workload imbalance detected: {len(suggestions)} file(s) recommended for reassignment."
        for mgr in managers:
            notif = Notification(
                user_id=mgr.id,
                organization_id=org_id,
                title="Workload Rebalance Suggestion",
                message=summary,
                notification_type="workload_rebalance",
                created_at=now,
            )
            db.add(notif)
            count += 1
        return count

    @staticmethod
    def _median(values: list[int]) -> float:
        """Simple median for a list of ints."""
        if not values:
            return 0.0
        s = sorted(values)
        mid = len(s) // 2
        if len(s) % 2 == 0:
            return (s[mid - 1] + s[mid]) / 2.0
        return float(s[mid])
