"""
Recruiting Workflow Definitions

Defines automated tasks that are created when a candidate's disposition changes.
Integrates with the workflow SLA system for task routing and management.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy import text
from database import engine
import json
import logging

logger = logging.getLogger(__name__)

# Stall thresholds: max days a candidate should stay in each stage before escalation
STALL_THRESHOLDS = {
    "new": 3,
    "screening": 5,
    "phone_screen": 7,
    "interview": 10,
    "assessment": 7,
    "offer": 5,
}

TERMINAL_CANDIDATE_STATUSES = ("hired", "rejected", "withdrawn")


# =============================================================================
# WORKFLOW TASK DEFINITIONS
# =============================================================================

RECRUITING_WORKFLOWS = {
    "new": {
        "name": "New Candidate Intake",
        "trigger": "status_change_to_new",
        "tasks": [
            {
                "day": 0,
                "title": "Review candidate profile",
                "description": "Review the candidate's profile, production history, and qualifications",
                "priority": "high",
                "route_to": "task_list"
            },
            {
                "day": 0,
                "title": "Check social media presence",
                "description": "Review LinkedIn, Facebook, and other social profiles for professional presence",
                "priority": "medium",
                "route_to": "task_list"
            },
            {
                "day": 1,
                "title": "Initial outreach call",
                "description": "Make first contact with the candidate to gauge interest",
                "priority": "high",
                "route_to": "dialer_queue"
            },
        ]
    },
    "screening": {
        "name": "Candidate Screening",
        "trigger": "status_change_to_screening",
        "tasks": [
            {
                "day": 0,
                "title": "Complete screening assessment quiz",
                "description": "Fill out the screening stage assessment quiz",
                "priority": "high",
                "route_to": "task_list"
            },
            {
                "day": 1,
                "title": "Schedule phone screen",
                "description": "Coordinate with candidate to schedule a phone screen",
                "priority": "high",
                "route_to": "task_list"
            },
            {
                "day": 2,
                "title": "Follow up if no response",
                "description": "Attempt follow-up contact if candidate hasn't responded",
                "priority": "medium",
                "route_to": "dialer_queue"
            },
        ]
    },
    "phone_screen": {
        "name": "Phone Screen",
        "trigger": "status_change_to_phone_screen",
        "tasks": [
            {
                "day": 0,
                "title": "Conduct phone screen",
                "description": "Complete the scheduled phone screen with candidate",
                "priority": "high",
                "route_to": "dialer_queue"
            },
            {
                "day": 0,
                "title": "Complete phone screen quiz",
                "description": "Fill out the phone screen assessment quiz",
                "priority": "high",
                "route_to": "task_list"
            },
            {
                "day": 1,
                "title": "Send follow-up email",
                "description": "Send thank you and next steps email to candidate",
                "priority": "medium",
                "route_to": "email_automation"
            },
        ]
    },
    "interview": {
        "name": "Interview Process",
        "trigger": "status_change_to_interview",
        "tasks": [
            {
                "day": 0,
                "title": "Prepare interview materials",
                "description": "Gather candidate info and prepare interview questions",
                "priority": "high",
                "route_to": "task_list"
            },
            {
                "day": 0,
                "title": "Send candidate portal invitation",
                "description": "Create and send PURL portal link to candidate",
                "priority": "medium",
                "route_to": "email_automation"
            },
            {
                "day": 1,
                "title": "Conduct interview",
                "description": "Complete the scheduled interview",
                "priority": "high",
                "route_to": "task_list"
            },
            {
                "day": 1,
                "title": "Complete interview quiz",
                "description": "Fill out the comprehensive interview assessment quiz",
                "priority": "high",
                "route_to": "task_list"
            },
        ]
    },
    "assessment": {
        "name": "Assessment Phase",
        "trigger": "status_change_to_assessment",
        "tasks": [
            {
                "day": 0,
                "title": "Send technical assessment",
                "description": "Send technical/product knowledge assessment to candidate",
                "priority": "high",
                "route_to": "email_automation"
            },
            {
                "day": 2,
                "title": "Review assessment results",
                "description": "Review and score the candidate's assessment submission",
                "priority": "high",
                "route_to": "task_list"
            },
            {
                "day": 2,
                "title": "Complete assessment quiz",
                "description": "Fill out the assessment stage evaluation quiz",
                "priority": "high",
                "route_to": "task_list"
            },
        ]
    },
    "offer": {
        "name": "Offer Process",
        "trigger": "status_change_to_offer",
        "tasks": [
            {
                "day": 0,
                "title": "Prepare offer package",
                "description": "Prepare compensation and onboarding materials",
                "priority": "high",
                "route_to": "task_list"
            },
            {
                "day": 0,
                "title": "Schedule offer presentation call",
                "description": "Schedule call to present the offer to candidate",
                "priority": "high",
                "route_to": "dialer_queue"
            },
            {
                "day": 3,
                "title": "Follow up on offer decision",
                "description": "Check in with candidate about offer decision",
                "priority": "high",
                "route_to": "dialer_queue"
            },
            {
                "day": 5,
                "title": "Final offer status check",
                "description": "Get final decision if not yet received",
                "priority": "medium",
                "route_to": "task_list"
            },
        ]
    },
    "hired": {
        "name": "Onboarding Preparation",
        "trigger": "status_change_to_hired",
        "tasks": [
            {
                "day": 0,
                "title": "Send offer acceptance confirmation",
                "description": "Send welcome email with next steps",
                "priority": "high",
                "route_to": "email_automation"
            },
            {
                "day": 0,
                "title": "Initiate background check",
                "description": "Start background check process",
                "priority": "high",
                "route_to": "task_list"
            },
            {
                "day": 1,
                "title": "Prepare onboarding materials",
                "description": "Gather and prepare all onboarding documents",
                "priority": "medium",
                "route_to": "task_list"
            },
            {
                "day": 1,
                "title": "Schedule onboarding orientation",
                "description": "Set up first day and orientation schedule",
                "priority": "medium",
                "route_to": "task_list"
            },
        ]
    },
}


# =============================================================================
# RECRUITING WORKFLOW SERVICE
# =============================================================================

class RecruitingWorkflowService:
    """Service for managing recruiting workflow task creation."""

    def __init__(self):
        pass

    def get_workflow_for_disposition(self, disposition: str, organization_id: Optional[int] = None) -> Optional[Dict]:
        """Get workflow definition. Checks org-specific config first, then defaults."""
        if organization_id:
            with engine.connect() as conn:
                row = conn.execute(
                    text("""
                        SELECT workflow_name, tasks
                        FROM recruit_workflow_config
                        WHERE organization_id = :org_id
                            AND disposition = :disposition
                            AND is_active = true
                    """),
                    {"org_id": organization_id, "disposition": disposition}
                ).fetchone()

                if row:
                    return {
                        "name": row.workflow_name or f"Custom: {disposition}",
                        "trigger": f"status_change_to_{disposition}",
                        "tasks": row.tasks,
                    }

        return RECRUITING_WORKFLOWS.get(disposition)

    def create_tasks_for_disposition(
        self,
        candidate_id: int,
        disposition: str,
        assigned_to: int,
        organization_id: int
    ) -> List[Dict]:
        """Create workflow tasks when a candidate disposition changes."""
        workflow = self.get_workflow_for_disposition(disposition, organization_id=organization_id)
        if not workflow:
            return []

        created_tasks = []
        now = datetime.now()

        with engine.connect() as conn:
            # Verify candidate belongs to the given organization
            candidate_check = conn.execute(
                text("SELECT id FROM mm_candidates WHERE id = :id AND organization_id = :org_id"),
                {"id": candidate_id, "org_id": organization_id}
            ).fetchone()
            if not candidate_check:
                raise ValueError(f"Candidate {candidate_id} not found in organization {organization_id}")

            for task_def in workflow["tasks"]:
                due_date = now + timedelta(days=task_def["day"])

                # Insert task into recruiting_tasks table
                result = conn.execute(
                    text("""
                        INSERT INTO recruiting_tasks
                        (candidate_id, title, description, due_date, priority,
                         route_to, status, assigned_to, organization_id, created_at)
                        VALUES (:candidate_id, :title, :description, :due_date, :priority,
                                :route_to, 'pending', :assigned_to, :org_id, NOW())
                        RETURNING id
                    """),
                    {
                        "candidate_id": candidate_id,
                        "title": task_def["title"],
                        "description": task_def["description"],
                        "due_date": due_date,
                        "priority": task_def["priority"],
                        "route_to": task_def["route_to"],
                        "assigned_to": assigned_to,
                        "org_id": organization_id
                    }
                )
                row = result.fetchone()
                task_id = row.id if row else None

                created_tasks.append({
                    "id": task_id,
                    "title": task_def["title"],
                    "due_date": due_date.isoformat(),
                    "priority": task_def["priority"],
                    "route_to": task_def["route_to"]
                })

            conn.commit()

        return created_tasks

    def get_pending_tasks(
        self,
        candidate_id: Optional[int] = None,
        assigned_to: Optional[int] = None,
        *,
        organization_id: int
    ) -> List[Dict]:
        """Get pending tasks, optionally filtered by candidate or assignee."""
        params = {"org_id": organization_id}
        filters = ["rt.organization_id = :org_id", "rt.status = 'pending'"]

        if candidate_id:
            filters.append("rt.candidate_id = :candidate_id")
            params["candidate_id"] = candidate_id
        if assigned_to:
            filters.append("rt.assigned_to = :assigned_to")
            params["assigned_to"] = assigned_to

        where_sql = " AND ".join(filters)

        with engine.connect() as conn:
            result = conn.execute(
                text(f"""
                    SELECT rt.id, rt.candidate_id, rt.title, rt.description,
                           rt.due_date, rt.priority, rt.route_to, rt.status,
                           rc.first_name, rc.last_name
                    FROM recruiting_tasks rt
                    JOIN mm_candidates rc ON rc.id = rt.candidate_id
                    WHERE {where_sql}
                    ORDER BY rt.due_date ASC,
                             CASE rt.priority
                                WHEN 'high' THEN 1
                                WHEN 'medium' THEN 2
                                ELSE 3
                             END
                """),
                params
            )
            rows = result.fetchall()

        return [
            {
                "id": row.id,
                "candidate_id": row.candidate_id,
                "candidate_name": f"{row.first_name} {row.last_name}",
                "title": row.title,
                "description": row.description,
                "due_date": row.due_date.isoformat() if row.due_date else None,
                "priority": row.priority,
                "route_to": row.route_to,
                "status": row.status,
                "is_overdue": row.due_date and row.due_date < datetime.now()
            }
            for row in rows
        ]

    def complete_task(self, task_id: int, completed_by: int, *, organization_id: int) -> bool:
        """Mark a task as completed. Only pending tasks in the caller's org can be completed."""
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    UPDATE recruiting_tasks
                    SET status = 'completed', completed_at = NOW(), completed_by = :completed_by
                    WHERE id = :task_id AND status = 'pending' AND organization_id = :org_id
                """),
                {"task_id": task_id, "completed_by": completed_by, "org_id": organization_id}
            )
            conn.commit()
        return result.rowcount > 0

    def skip_task(self, task_id: int, reason: str, skipped_by: int, *, organization_id: int) -> bool:
        """Skip a task with a reason. Only pending tasks in the caller's org can be skipped."""
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    UPDATE recruiting_tasks
                    SET status = 'skipped', skip_reason = :reason,
                        completed_at = NOW(), completed_by = :skipped_by
                    WHERE id = :task_id AND status = 'pending' AND organization_id = :org_id
                """),
                {"task_id": task_id, "reason": reason, "skipped_by": skipped_by, "org_id": organization_id}
            )
            conn.commit()
        return result.rowcount > 0

    def get_dialer_queue(
        self,
        assigned_to: Optional[int] = None,
        *,
        organization_id: int
    ) -> List[Dict]:
        """Get tasks routed to the dialer queue."""
        params = {"org_id": organization_id}
        filters = [
            "rt.organization_id = :org_id",
            "rt.status = 'pending'",
            "rt.route_to = 'dialer_queue'"
        ]

        if assigned_to:
            filters.append("rt.assigned_to = :assigned_to")
            params["assigned_to"] = assigned_to

        where_sql = " AND ".join(filters)

        with engine.connect() as conn:
            result = conn.execute(
                text(f"""
                    SELECT rt.id, rt.candidate_id, rt.title, rt.description,
                           rt.due_date, rt.priority,
                           rc.first_name, rc.last_name, rc.phone, rc.email
                    FROM recruiting_tasks rt
                    JOIN mm_candidates rc ON rc.id = rt.candidate_id
                        AND rc.organization_id = :org_id
                    WHERE {where_sql}
                    ORDER BY rt.due_date ASC,
                             CASE rt.priority
                                WHEN 'high' THEN 1
                                WHEN 'medium' THEN 2
                                ELSE 3
                             END
                """),
                params
            )
            rows = result.fetchall()

        return [
            {
                "id": row.id,
                "candidate_id": row.candidate_id,
                "candidate_name": f"{row.first_name} {row.last_name}",
                "phone": row.phone,
                "email": row.email,
                "title": row.title,
                "description": row.description,
                "due_date": row.due_date.isoformat() if row.due_date else None,
                "priority": row.priority
            }
            for row in rows
        ]

    # =========================================================================
    # WORKFLOW CONFIGURATION (PER-ORG CUSTOMIZATION)
    # =========================================================================

    def get_org_workflows(self, organization_id: int) -> List[Dict]:
        """Get all custom workflow configs for an organization."""
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, disposition, workflow_name, tasks, is_active,
                           created_at, updated_at
                    FROM recruit_workflow_config
                    WHERE organization_id = :org_id
                    ORDER BY disposition
                """),
                {"org_id": organization_id}
            ).fetchall()

        return [
            {
                "id": row.id,
                "disposition": row.disposition,
                "workflow_name": row.workflow_name,
                "tasks": row.tasks,
                "is_active": row.is_active,
                "is_custom": True,
            }
            for row in rows
        ]

    def update_org_workflow(
        self,
        organization_id: int,
        disposition: str,
        tasks: List[Dict],
        workflow_name: Optional[str] = None,
        created_by: Optional[int] = None,
    ) -> Dict:
        """Create or update org-specific workflow for a disposition."""
        VALID_ROUTE_TO = {"task_list", "dialer_queue", "email_automation"}
        VALID_PRIORITIES = {"high", "medium", "low"}

        for task in tasks:
            if not all(k in task for k in ("day", "title", "priority")):
                raise ValueError("Each task must have 'day', 'title', 'priority'")
            if task.get("route_to") and task["route_to"] not in VALID_ROUTE_TO:
                raise ValueError(f"Invalid route_to: {task['route_to']}")
            if task["priority"] not in VALID_PRIORITIES:
                raise ValueError(f"Invalid priority: {task['priority']}")

        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO recruit_workflow_config
                        (organization_id, disposition, workflow_name, tasks, created_by,
                         created_at, updated_at)
                    VALUES (:org_id, :disposition, :name, :tasks::jsonb, :created_by,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (organization_id, disposition)
                    DO UPDATE SET
                        tasks = EXCLUDED.tasks,
                        workflow_name = EXCLUDED.workflow_name,
                        is_active = true,
                        updated_at = CURRENT_TIMESTAMP
                """),
                {
                    "org_id": organization_id,
                    "disposition": disposition,
                    "name": workflow_name or RECRUITING_WORKFLOWS.get(disposition, {}).get("name", disposition),
                    "tasks": json.dumps(tasks),
                    "created_by": created_by,
                }
            )
            conn.commit()

        return {"disposition": disposition, "tasks": tasks, "status": "saved"}

    def reset_org_workflow(self, organization_id: int, disposition: str) -> Dict:
        """Reset org workflow to system defaults by deactivating override."""
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    UPDATE recruit_workflow_config
                    SET is_active = false, updated_at = CURRENT_TIMESTAMP
                    WHERE organization_id = :org_id AND disposition = :disposition
                """),
                {"org_id": organization_id, "disposition": disposition}
            )
            conn.commit()

        return {"disposition": disposition, "reset": result.rowcount > 0}

    # =========================================================================
    # STALLED PIPELINE DETECTION
    # =========================================================================

    def detect_stalled_candidates(self, organization_id: int) -> List[Dict]:
        """Detect candidates stalled in pipeline stages beyond thresholds."""
        stalled = []

        with engine.connect() as conn:
            for status, threshold_days in STALL_THRESHOLDS.items():
                rows = conn.execute(
                    text("""
                        SELECT c.id, c.first_name, c.last_name, c.status,
                               c.status_changed_at, c.email,
                               EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - c.status_changed_at)) / 86400 as days_in_stage
                        FROM mm_candidates c
                        WHERE c.organization_id = :org_id
                            AND c.is_active = true
                            AND c.status = :status
                            AND c.status_changed_at < CURRENT_TIMESTAMP - make_interval(days => :threshold)
                        ORDER BY c.status_changed_at ASC
                    """),
                    {"org_id": organization_id, "status": status, "threshold": threshold_days}
                ).fetchall()

                for row in rows:
                    stalled.append({
                        "candidate_id": row.id,
                        "name": f"{row.first_name} {row.last_name}",
                        "status": row.status,
                        "days_in_stage": round(float(row.days_in_stage), 1),
                        "threshold_days": threshold_days,
                        "email": row.email,
                        "severity": "critical" if float(row.days_in_stage) > threshold_days * 2 else "warning",
                    })

        return stalled

    def create_stall_alerts(self, organization_id: int) -> Dict:
        """Detect stalled candidates and create alerts in mm_capacity_alerts."""
        stalled = self.detect_stalled_candidates(organization_id)
        alerts_created = 0

        with engine.connect() as conn:
            for candidate in stalled:
                # Check for existing open stall alert for this candidate
                existing = conn.execute(
                    text("""
                        SELECT id FROM mm_capacity_alerts
                        WHERE organization_id = :org_id
                            AND alert_type = 'candidate_stalled'
                            AND status = 'open'
                            AND title LIKE :title_pattern
                    """),
                    {
                        "org_id": organization_id,
                        "title_pattern": f"%candidate {candidate['candidate_id']}%",
                    }
                ).fetchone()

                if not existing:
                    conn.execute(
                        text("""
                            INSERT INTO mm_capacity_alerts (
                                organization_id, alert_type, severity,
                                title, description, metrics_snapshot,
                                recommended_actions, status, created_at
                            ) VALUES (
                                :org_id, 'candidate_stalled', :severity,
                                :title, :description, :metrics::jsonb,
                                :actions::jsonb, 'open', CURRENT_TIMESTAMP
                            )
                        """),
                        {
                            "org_id": organization_id,
                            "severity": candidate["severity"],
                            "title": f"Stalled candidate {candidate['candidate_id']}: {candidate['name']} in {candidate['status']}",
                            "description": (
                                f"{candidate['name']} has been in {candidate['status']} "
                                f"for {candidate['days_in_stage']} days (threshold: {candidate['threshold_days']})"
                            ),
                            "metrics": json.dumps({
                                "candidate_id": candidate["candidate_id"],
                                "status": candidate["status"],
                                "days_in_stage": candidate["days_in_stage"],
                                "threshold_days": candidate["threshold_days"],
                            }),
                            "actions": json.dumps([
                                f"Contact {candidate['name']} immediately",
                                "Review status and decide: advance, reject, or note delay reason",
                            ]),
                        }
                    )
                    alerts_created += 1

            conn.commit()

        return {
            "stalled_count": len(stalled),
            "alerts_created": alerts_created,
            "candidates": stalled,
        }


# Singleton instance
recruiting_workflow_service = RecruitingWorkflowService()
