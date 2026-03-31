"""
Capacity Service
Real-time capacity calculation and workload distribution for Master Manager Platform.
"""

import logging
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Optional, Any, Tuple
from sqlalchemy import text, func
from sqlalchemy.orm import Session
from dataclasses import dataclass
from enum import Enum

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class CapacityStatus(str, Enum):
    AVAILABLE = "available"
    NEAR_CAPACITY = "near_capacity"
    AT_CAPACITY = "at_capacity"
    OVER_CAPACITY = "over_capacity"


@dataclass
class CapacityMetrics:
    """Capacity metrics for a user."""
    user_id: int
    user_name: str
    role_name: str

    # Current counts
    current_files: int
    current_leads: int
    current_tasks: int

    # Limits
    max_files: int
    max_leads: int
    max_tasks: int

    # Percentages
    file_capacity_pct: float
    lead_capacity_pct: float
    task_capacity_pct: float
    overall_capacity_pct: float

    # Status
    capacity_status: str
    is_available: bool

    # Risk scores
    burnout_risk: float
    attrition_risk: float


@dataclass
class TeamCapacityOverview:
    """Team-level capacity overview."""
    total_members: int
    available_count: int
    near_capacity_count: int
    at_capacity_count: int
    over_capacity_count: int

    avg_capacity_pct: float
    total_file_capacity: int
    used_file_capacity: int

    bottleneck_roles: List[str]
    surge_risk: bool


class CapacityService:
    """
    Service for calculating and managing team capacity.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # CAPACITY CALCULATION
    # =========================================================================

    async def calculate_user_capacity(
        self,
        user_id: int,
        organization_id: Optional[int] = None
    ) -> CapacityMetrics:
        """
        Calculate current capacity for a single user.
        Returns detailed capacity metrics.
        """
        # Get user info and capacity config
        user_query = text("""
            SELECT
                u.id,
                u.full_name,
                COALESCE(rd.role_name, 'Unknown') as role_name,
                COALESCE(tc.max_files_concurrent, rd.default_max_files, 25) as max_files,
                COALESCE(tc.max_leads_concurrent, rd.default_max_leads, 50) as max_leads,
                COALESCE(tc.max_tasks_daily, rd.default_max_tasks_daily, 30) as max_tasks,
                COALESCE(tc.is_available, true) as is_available,
                COALESCE(tc.burnout_risk_score, 0) as burnout_risk,
                COALESCE(tc.attrition_risk_score, 0) as attrition_risk
            FROM users u
            LEFT JOIN mm_talent_capacity tc ON tc.user_id = u.id
            LEFT JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            WHERE u.id = :user_id
        """)
        user_result = self.db.execute(user_query, {"user_id": user_id}).fetchone()

        if not user_result:
            raise ValueError(f"User {user_id} not found")

        # Count active files (loans in pipeline)
        files_query = text("""
            SELECT COUNT(*) as count
            FROM loans
            WHERE loan_officer_id = :user_id
            AND stage NOT IN ('funded', 'cancelled', 'denied', 'withdrawn')
        """)
        files_result = self.db.execute(files_query, {"user_id": user_id}).fetchone()
        current_files = files_result.count if files_result else 0

        # Count active leads
        leads_query = text("""
            SELECT COUNT(*) as count
            FROM leads
            WHERE owner_id = :user_id
            AND status NOT IN ('converted', 'lost', 'dead', 'unqualified')
        """)
        leads_result = self.db.execute(leads_query, {"user_id": user_id}).fetchone()
        current_leads = leads_result.count if leads_result else 0

        # Count pending tasks for today
        tasks_query = text("""
            SELECT COUNT(*) as count
            FROM tasks
            WHERE owner_id = :user_id
            AND status IN ('pending', 'in_progress')
            AND (due_date IS NULL OR due_date <= CURRENT_DATE + 1)
        """)
        tasks_result = self.db.execute(tasks_query, {"user_id": user_id}).fetchone()
        current_tasks = tasks_result.count if tasks_result else 0

        # Calculate percentages
        max_files = user_result.max_files or 25
        max_leads = user_result.max_leads or 50
        max_tasks = user_result.max_tasks or 30

        file_pct = (current_files / max_files) * 100 if max_files > 0 else 0
        lead_pct = (current_leads / max_leads) * 100 if max_leads > 0 else 0
        task_pct = (current_tasks / max_tasks) * 100 if max_tasks > 0 else 0

        # Weighted overall capacity (files matter most for ops)
        overall_pct = (file_pct * 0.5) + (lead_pct * 0.3) + (task_pct * 0.2)

        # Determine status
        if overall_pct >= 100:
            status = CapacityStatus.OVER_CAPACITY.value
        elif overall_pct >= 90:
            status = CapacityStatus.AT_CAPACITY.value
        elif overall_pct >= 75:
            status = CapacityStatus.NEAR_CAPACITY.value
        else:
            status = CapacityStatus.AVAILABLE.value

        return CapacityMetrics(
            user_id=user_id,
            user_name=user_result.full_name or "Unknown",
            role_name=user_result.role_name,
            current_files=current_files,
            current_leads=current_leads,
            current_tasks=current_tasks,
            max_files=max_files,
            max_leads=max_leads,
            max_tasks=max_tasks,
            file_capacity_pct=round(file_pct, 1),
            lead_capacity_pct=round(lead_pct, 1),
            task_capacity_pct=round(task_pct, 1),
            overall_capacity_pct=round(overall_pct, 1),
            capacity_status=status,
            is_available=user_result.is_available,
            burnout_risk=user_result.burnout_risk,
            attrition_risk=user_result.attrition_risk
        )

    async def recalculate_all_capacities(
        self,
        organization_id: Optional[int] = None
    ) -> int:
        """
        Recalculate capacity for all active users.
        Returns count of users updated.
        """
        # Get all active users with capacity records
        users_query = text("""
            SELECT DISTINCT u.id
            FROM users u
            LEFT JOIN mm_talent_capacity tc ON tc.user_id = u.id
            WHERE u.is_active = true
            AND (:org_id IS NULL OR u.organization_id = :org_id)
        """)
        users = self.db.execute(users_query, {"org_id": organization_id}).fetchall()

        count = 0
        for user_row in users:
            try:
                metrics = await self.calculate_user_capacity(user_row.id, organization_id)
                await self._update_capacity_record(metrics, organization_id)
                count += 1
            except SQLAlchemyError as e:
                logger.error(f"Error calculating capacity for user {user_row.id}: {e}")

        return count

    async def _update_capacity_record(
        self,
        metrics: CapacityMetrics,
        organization_id: Optional[int] = None
    ):
        """Update the mm_talent_capacity record for a user."""
        upsert_query = text("""
            INSERT INTO mm_talent_capacity (
                organization_id, user_id,
                current_file_count, current_lead_count, current_task_count,
                file_capacity_pct, lead_capacity_pct, task_capacity_pct,
                overall_capacity_pct, capacity_status,
                last_calculated_at, updated_at
            )
            VALUES (
                :org_id, :user_id,
                :files, :leads, :tasks,
                :file_pct, :lead_pct, :task_pct,
                :overall_pct, :status,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (organization_id, user_id)
            DO UPDATE SET
                current_file_count = EXCLUDED.current_file_count,
                current_lead_count = EXCLUDED.current_lead_count,
                current_task_count = EXCLUDED.current_task_count,
                file_capacity_pct = EXCLUDED.file_capacity_pct,
                lead_capacity_pct = EXCLUDED.lead_capacity_pct,
                task_capacity_pct = EXCLUDED.task_capacity_pct,
                overall_capacity_pct = EXCLUDED.overall_capacity_pct,
                capacity_status = EXCLUDED.capacity_status,
                last_calculated_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
        """)

        self.db.execute(upsert_query, {
            "org_id": organization_id,
            "user_id": metrics.user_id,
            "files": metrics.current_files,
            "leads": metrics.current_leads,
            "tasks": metrics.current_tasks,
            "file_pct": metrics.file_capacity_pct,
            "lead_pct": metrics.lead_capacity_pct,
            "task_pct": metrics.task_capacity_pct,
            "overall_pct": metrics.overall_capacity_pct,
            "status": metrics.capacity_status
        })
        self.db.commit()

    # =========================================================================
    # TEAM OVERVIEW
    # =========================================================================

    async def get_team_capacity_overview(
        self,
        organization_id: Optional[int] = None,
        role_filter: Optional[str] = None
    ) -> TeamCapacityOverview:
        """Get team-level capacity overview."""
        query = text("""
            SELECT
                COUNT(*) as total_members,
                SUM(CASE WHEN capacity_status = 'available' THEN 1 ELSE 0 END) as available,
                SUM(CASE WHEN capacity_status = 'near_capacity' THEN 1 ELSE 0 END) as near,
                SUM(CASE WHEN capacity_status = 'at_capacity' THEN 1 ELSE 0 END) as at_cap,
                SUM(CASE WHEN capacity_status = 'over_capacity' THEN 1 ELSE 0 END) as over,
                AVG(overall_capacity_pct) as avg_capacity,
                SUM(max_files_concurrent) as total_file_capacity,
                SUM(current_file_count) as used_file_capacity
            FROM mm_talent_capacity tc
            LEFT JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            WHERE tc.is_available = true
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
            AND (:role IS NULL OR rd.role_name = :role)
        """)

        result = self.db.execute(query, {
            "org_id": organization_id,
            "role": role_filter
        }).fetchone()

        # Find bottleneck roles (roles with avg capacity > 85%)
        bottleneck_query = text("""
            SELECT rd.role_name, AVG(tc.overall_capacity_pct) as avg_cap
            FROM mm_talent_capacity tc
            JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            WHERE tc.is_available = true
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
            GROUP BY rd.role_name
            HAVING AVG(tc.overall_capacity_pct) > 85
            ORDER BY avg_cap DESC
        """)
        bottlenecks = self.db.execute(bottleneck_query, {"org_id": organization_id}).fetchall()

        over_capacity = result.over or 0 if result else 0
        surge_risk = over_capacity > 0 or (result and result.avg_capacity and result.avg_capacity > 80)

        return TeamCapacityOverview(
            total_members=result.total_members or 0 if result else 0,
            available_count=result.available or 0 if result else 0,
            near_capacity_count=result.near or 0 if result else 0,
            at_capacity_count=result.at_cap or 0 if result else 0,
            over_capacity_count=over_capacity,
            avg_capacity_pct=round(result.avg_capacity or 0, 1) if result else 0,
            total_file_capacity=result.total_file_capacity or 0 if result else 0,
            used_file_capacity=result.used_file_capacity or 0 if result else 0,
            bottleneck_roles=[r.role_name for r in bottlenecks],
            surge_risk=surge_risk
        )

    async def get_capacity_by_role(
        self,
        organization_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get capacity metrics grouped by role."""
        query = text("""
            SELECT
                rd.role_name,
                rd.role_category,
                COUNT(*) as member_count,
                AVG(tc.overall_capacity_pct) as avg_capacity,
                SUM(tc.max_files_concurrent) as total_capacity,
                SUM(tc.current_file_count) as used_capacity,
                SUM(CASE WHEN tc.capacity_status = 'available' THEN 1 ELSE 0 END) as available_count,
                SUM(CASE WHEN tc.capacity_status IN ('at_capacity', 'over_capacity') THEN 1 ELSE 0 END) as at_risk_count
            FROM mm_talent_capacity tc
            JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            WHERE tc.is_available = true
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
            GROUP BY rd.role_name, rd.role_category
            ORDER BY avg_capacity DESC
        """)

        results = self.db.execute(query, {"org_id": organization_id}).fetchall()

        return [
            {
                "role_name": r.role_name,
                "role_category": r.role_category,
                "member_count": r.member_count,
                "avg_capacity_pct": round(r.avg_capacity or 0, 1),
                "total_capacity": r.total_capacity or 0,
                "used_capacity": r.used_capacity or 0,
                "available_count": r.available_count or 0,
                "at_risk_count": r.at_risk_count or 0,
                "utilization_pct": round(((r.used_capacity or 0) / (r.total_capacity or 1)) * 100, 1)
            }
            for r in results
        ]

    # =========================================================================
    # INDIVIDUAL USER CAPACITY
    # =========================================================================

    async def get_all_user_capacities(
        self,
        organization_id: Optional[int] = None,
        status_filter: Optional[str] = None,
        role_filter: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get capacity metrics for all users."""
        query = text("""
            SELECT
                tc.user_id,
                u.full_name,
                u.email,
                rd.role_name,
                tc.current_file_count,
                tc.current_lead_count,
                tc.current_task_count,
                tc.max_files_concurrent,
                tc.max_leads_concurrent,
                tc.max_tasks_daily,
                tc.file_capacity_pct,
                tc.lead_capacity_pct,
                tc.task_capacity_pct,
                tc.overall_capacity_pct,
                tc.capacity_status,
                tc.is_available,
                tc.burnout_risk_score,
                tc.attrition_risk_score,
                tc.last_calculated_at
            FROM mm_talent_capacity tc
            JOIN users u ON u.id = tc.user_id
            LEFT JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            WHERE u.is_active = true
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
            AND (:status IS NULL OR tc.capacity_status = :status)
            AND (:role IS NULL OR rd.role_name = :role)
            ORDER BY tc.overall_capacity_pct DESC
            LIMIT :limit
        """)

        results = self.db.execute(query, {
            "org_id": organization_id,
            "status": status_filter,
            "role": role_filter,
            "limit": limit
        }).fetchall()

        return [
            {
                "user_id": r.user_id,
                "user_name": r.full_name,
                "email": r.email,
                "role_name": r.role_name,
                "current_files": r.current_file_count,
                "current_leads": r.current_lead_count,
                "current_tasks": r.current_task_count,
                "max_files": r.max_files_concurrent,
                "max_leads": r.max_leads_concurrent,
                "max_tasks": r.max_tasks_daily,
                "file_capacity_pct": r.file_capacity_pct,
                "lead_capacity_pct": r.lead_capacity_pct,
                "task_capacity_pct": r.task_capacity_pct,
                "overall_capacity_pct": r.overall_capacity_pct,
                "capacity_status": r.capacity_status,
                "is_available": r.is_available,
                "burnout_risk": r.burnout_risk_score,
                "attrition_risk": r.attrition_risk_score,
                "last_calculated": r.last_calculated_at.isoformat() if r.last_calculated_at else None
            }
            for r in results
        ]

    # =========================================================================
    # ASSIGNMENT OPTIMIZATION
    # =========================================================================

    async def get_available_users_for_role(
        self,
        role_name: str,
        min_capacity_pct: float = 25,
        organization_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get users with available capacity for a specific role.
        Returns users sorted by best availability (lowest current capacity).
        """
        query = text("""
            SELECT
                tc.user_id,
                u.full_name,
                rd.role_name,
                tc.overall_capacity_pct,
                tc.current_file_count,
                tc.max_files_concurrent,
                (tc.max_files_concurrent - tc.current_file_count) as available_slots
            FROM mm_talent_capacity tc
            JOIN users u ON u.id = tc.user_id
            JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            WHERE rd.role_name = :role_name
            AND tc.is_available = true
            AND tc.is_locked_for_assignment = false
            AND tc.overall_capacity_pct <= (100 - :min_capacity)
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
            ORDER BY tc.overall_capacity_pct ASC
        """)

        results = self.db.execute(query, {
            "role_name": role_name,
            "min_capacity": min_capacity_pct,
            "org_id": organization_id
        }).fetchall()

        return [
            {
                "user_id": r.user_id,
                "user_name": r.full_name,
                "role_name": r.role_name,
                "capacity_pct": r.overall_capacity_pct,
                "current_files": r.current_file_count,
                "max_files": r.max_files_concurrent,
                "available_slots": r.available_slots,
                "recommendation_score": 100 - r.overall_capacity_pct  # Higher = more recommended
            }
            for r in results
        ]

    async def suggest_optimal_assignment(
        self,
        entity_type: str,  # "lead", "loan", "task"
        role_needed: str,
        organization_id: Optional[int] = None,
        complexity: str = "normal"  # "simple", "normal", "complex"
    ) -> Optional[Dict[str, Any]]:
        """
        Suggest the best person to assign based on capacity and performance.
        Returns the top recommendation with reasoning.
        """
        # Get available users for this role
        available = await self.get_available_users_for_role(
            role_name=role_needed,
            min_capacity_pct=20,
            organization_id=organization_id
        )

        if not available:
            return None

        # For complex items, prefer experienced users (filter to lower capacity)
        if complexity == "complex":
            # Get performance scores to weight by skill
            perf_query = text("""
                SELECT user_id, overall_score
                FROM mm_talent_performance
                WHERE period_type = 'monthly'
                AND period_start >= CURRENT_DATE - 30
                ORDER BY period_start DESC
            """)
            perf_results = self.db.execute(perf_query).fetchall()
            perf_map = {r.user_id: r.overall_score for r in perf_results}

            # Re-score with performance weighting
            for user in available:
                perf_score = perf_map.get(user["user_id"], 50)
                user["recommendation_score"] = (
                    (100 - user["capacity_pct"]) * 0.6 +
                    perf_score * 0.4
                )

            available.sort(key=lambda x: x["recommendation_score"], reverse=True)

        top_pick = available[0]

        return {
            "recommended_user_id": top_pick["user_id"],
            "recommended_user_name": top_pick["user_name"],
            "role": role_needed,
            "current_capacity_pct": top_pick["capacity_pct"],
            "available_slots": top_pick["available_slots"],
            "recommendation_score": top_pick["recommendation_score"],
            "reasoning": self._generate_assignment_reasoning(top_pick, complexity),
            "alternatives": available[1:4] if len(available) > 1 else []
        }

    def _generate_assignment_reasoning(
        self,
        user: Dict[str, Any],
        complexity: str
    ) -> str:
        """Generate human-readable reasoning for assignment recommendation."""
        reasons = []

        if user["capacity_pct"] < 50:
            reasons.append(f"Has low current workload ({user['capacity_pct']:.0f}%)")
        elif user["capacity_pct"] < 75:
            reasons.append(f"Has moderate capacity ({user['capacity_pct']:.0f}%)")
        else:
            reasons.append(f"Near capacity but available ({user['capacity_pct']:.0f}%)")

        reasons.append(f"{user['available_slots']} available file slots")

        if complexity == "complex":
            reasons.append("Selected for experience with complex files")

        return ". ".join(reasons)

    # =========================================================================
    # CAPACITY LIMITS MANAGEMENT
    # =========================================================================

    async def update_user_capacity_limits(
        self,
        user_id: int,
        max_files: Optional[int] = None,
        max_leads: Optional[int] = None,
        max_tasks: Optional[int] = None,
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Update capacity limits for a user."""
        updates = []
        params = {"user_id": user_id, "org_id": organization_id}

        if max_files is not None:
            updates.append("max_files_concurrent = :max_files")
            params["max_files"] = max_files

        if max_leads is not None:
            updates.append("max_leads_concurrent = :max_leads")
            params["max_leads"] = max_leads

        if max_tasks is not None:
            updates.append("max_tasks_daily = :max_tasks")
            params["max_tasks"] = max_tasks

        if not updates:
            raise ValueError("No updates provided")

        update_sql = ", ".join(updates)
        query = text(f"""
            UPDATE mm_talent_capacity
            SET {update_sql}, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id
            AND (:org_id IS NULL OR organization_id = :org_id)
            RETURNING *
        """)

        result = self.db.execute(query, params).fetchone()
        self.db.commit()

        if not result:
            raise ValueError(f"Capacity record not found for user {user_id}")

        # Recalculate after limit change
        metrics = await self.calculate_user_capacity(user_id, organization_id)

        return {
            "user_id": user_id,
            "max_files": result.max_files_concurrent,
            "max_leads": result.max_leads_concurrent,
            "max_tasks": result.max_tasks_daily,
            "new_capacity_status": metrics.capacity_status,
            "new_capacity_pct": metrics.overall_capacity_pct
        }

    async def set_user_availability(
        self,
        user_id: int,
        is_available: bool,
        status: str = "active",
        return_date: Optional[date] = None,
        notes: Optional[str] = None,
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Set user availability status."""
        query = text("""
            UPDATE mm_talent_capacity
            SET
                is_available = :is_available,
                availability_status = :status,
                return_date = :return_date,
                availability_notes = :notes,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id
            AND (:org_id IS NULL OR organization_id = :org_id)
            RETURNING *
        """)

        result = self.db.execute(query, {
            "user_id": user_id,
            "is_available": is_available,
            "status": status,
            "return_date": return_date,
            "notes": notes,
            "org_id": organization_id
        }).fetchone()
        self.db.commit()

        return {
            "user_id": user_id,
            "is_available": is_available,
            "availability_status": status,
            "return_date": return_date.isoformat() if return_date else None
        }


# =========================================================================
# FACTORY FUNCTION
# =========================================================================

def get_capacity_service(db: Session) -> CapacityService:
    """Factory function to get CapacityService instance."""
    return CapacityService(db)


# =========================================================================
# HELPER FUNCTIONS FOR INTEGRATION
# =========================================================================

async def update_capacity_on_assignment(
    db: Session,
    user_id: int,
    organization_id: Optional[int] = None
) -> None:
    """
    Quick capacity update after a lead/loan is assigned.
    Call this after create_lead or create_loan to keep capacity in sync.

    This is a lightweight update that just recalculates for one user.
    """
    try:
        service = CapacityService(db)
        metrics = await service.calculate_user_capacity(user_id, organization_id)
        await service._update_capacity_record(metrics, organization_id)
    except Exception as e:
        # Don't fail the main operation if capacity update fails
        import logging
        logging.getLogger(__name__).warning(
            f"Failed to update capacity for user {user_id}: {e}"
        )


def sync_update_capacity(db: Session, user_id: int, organization_id: Optional[int] = None) -> None:
    """
    Synchronous wrapper for capacity update.
    Use this when you can't await in the calling context.

    Safe to call from both sync and async contexts.
    """
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in async context — schedule as fire-and-forget task
        loop.create_task(update_capacity_on_assignment(db, user_id, organization_id))
    else:
        # No running loop — safe to use asyncio.run() directly
        asyncio.run(update_capacity_on_assignment(db, user_id, organization_id))
