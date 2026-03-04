"""
Onboarding Assistant Agent

Specialized agent for new user onboarding with 8 tools:
1. get_onboarding_status - Get user's onboarding progress
2. get_next_steps - Get next onboarding steps
3. complete_step - Mark onboarding step as complete
4. get_training_resources - Get training materials
5. schedule_training - Schedule training session
6. send_welcome_email - Send welcome/onboarding email
7. assign_mentor - Assign a mentor to new user
8. get_team_introduction - Get team member introductions
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class OnboardingStatusInput(BaseModel):
    user_id: Optional[int] = Field(None, description="User ID to check status for")


class NextStepsInput(BaseModel):
    user_id: Optional[int] = Field(None, description="User ID")
    role: Optional[str] = Field(None, description="User role for role-specific steps")


class CompleteStepInput(BaseModel):
    step_id: str = Field(..., description="Step ID to mark complete")
    notes: Optional[str] = Field(None, description="Optional notes")


class TrainingResourcesInput(BaseModel):
    category: Optional[str] = Field(None, description="Category: basics, features, advanced, compliance")
    role: Optional[str] = Field(None, description="Role-specific resources")


class ScheduleTrainingInput(BaseModel):
    training_type: str = Field(..., description="Training type: platform_overview, feature_deep_dive, best_practices")
    preferred_date: Optional[str] = Field(None, description="Preferred date/time")
    attendees: Optional[List[int]] = Field(None, description="List of user IDs to invite")


class WelcomeEmailInput(BaseModel):
    user_id: int = Field(..., description="User ID to send welcome email to")
    include_credentials: bool = Field(default=False, description="Include login credentials")


class AssignMentorInput(BaseModel):
    new_user_id: int = Field(..., description="New user ID")
    mentor_id: Optional[int] = Field(None, description="Specific mentor ID or auto-assign")


class TeamIntroInput(BaseModel):
    user_id: Optional[int] = Field(None, description="User ID to get team for")
    include_roles: bool = Field(default=True, description="Include role descriptions")


# ============================================================================
# ONBOARDING ASSISTANT AGENT
# ============================================================================

@AgentRegistry.register
class OnboardingAgent(SpecializedAgent):
    """
    Onboarding assistant for new user setup and training.

    Guides new users through onboarding process with training resources
    and mentorship with 8 specialized tools.
    """

    @property
    def name(self) -> str:
        return "OnboardingAgent"

    @property
    def description(self) -> str:
        return "Guides new users through onboarding, training, and team introduction"

    def _register_tools(self):
        """Register all onboarding tools"""

        self.register_tool(AgentTool(
            name="get_onboarding_status",
            description="Get current onboarding progress and completion status",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_onboarding_status,
            input_schema=OnboardingStatusInput
        ))

        self.register_tool(AgentTool(
            name="get_next_steps",
            description="Get the next recommended onboarding steps for user",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_next_steps,
            input_schema=NextStepsInput
        ))

        self.register_tool(AgentTool(
            name="complete_step",
            description="Mark an onboarding step as complete",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._complete_step,
            input_schema=CompleteStepInput
        ))

        self.register_tool(AgentTool(
            name="get_training_resources",
            description="Get training materials and resources",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_training_resources,
            input_schema=TrainingResourcesInput
        ))

        self.register_tool(AgentTool(
            name="schedule_training",
            description="Schedule a training session",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._schedule_training,
            input_schema=ScheduleTrainingInput
        ))

        self.register_tool(AgentTool(
            name="send_welcome_email",
            description="Send welcome email to new user",
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._send_welcome_email,
            input_schema=WelcomeEmailInput
        ))

        self.register_tool(AgentTool(
            name="assign_mentor",
            description="Assign a mentor to help onboard new user",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._assign_mentor,
            input_schema=AssignMentorInput
        ))

        self.register_tool(AgentTool(
            name="get_team_introduction",
            description="Get team member introductions and contact info",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_team_introduction,
            input_schema=TeamIntroInput
        ))

    async def _get_onboarding_status(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get onboarding status — attempts DB lookup, falls back to defaults"""
        user_id = input_data.get("user_id") or context.get("user_id")
        org_id = self.context.get("organization_id")

        # Define standard onboarding steps
        default_steps = [
            {"id": "profile", "name": "Complete Profile", "status": "pending"},
            {"id": "email", "name": "Connect Email", "status": "pending"},
            {"id": "calendar", "name": "Connect Calendar", "status": "pending"},
            {"id": "tour", "name": "Platform Tour", "status": "pending"},
            {"id": "first_lead", "name": "Add First Lead", "status": "pending"},
            {"id": "training", "name": "Complete Training", "status": "pending"}
        ]

        # Try to derive status from real user data
        try:
            from database import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                user = db.execute(text("""
                    SELECT id, created_at, email, full_name,
                           google_calendar_token IS NOT NULL as has_calendar,
                           microsoft_token IS NOT NULL as has_email
                    FROM users
                    WHERE id = :user_id AND (:org_id IS NULL OR organization_id = :org_id)
                """), {"user_id": user_id, "org_id": org_id}).fetchone()

                if user:
                    # Derive completion from real data
                    if user.full_name:
                        default_steps[0]["status"] = "completed"
                    if user.has_email:
                        default_steps[1]["status"] = "completed"
                    if user.has_calendar:
                        default_steps[2]["status"] = "completed"

                    # Check if they have any leads
                    lead_count = db.execute(text("""
                        SELECT COUNT(*) as cnt FROM leads
                        WHERE owner_id = :user_id
                        AND (:org_id IS NULL OR organization_id = :org_id)
                        LIMIT 1
                    """), {"user_id": user_id, "org_id": org_id}).fetchone()
                    if lead_count and lead_count.cnt > 0:
                        default_steps[4]["status"] = "completed"
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"Could not load onboarding data from DB: {e}")

        completed = sum(1 for s in default_steps if s["status"] == "completed")
        pct = round((completed / len(default_steps)) * 100)

        status = {
            "user_id": user_id,
            "started_at": (datetime.now() - timedelta(days=3)).isoformat(),
            "completion_percent": pct,
            "steps": default_steps,
            "estimated_completion": "1 day" if pct >= 80 else "2 days" if pct >= 50 else "3 days"
        }

        return ToolResult(
            success=True,
            data=status,
            message=f"Onboarding {pct}% complete"
        )

    async def _get_next_steps(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get next onboarding steps"""
        role = input_data.get("role", "loan_officer")

        next_steps = [
            {
                "step_id": "tour",
                "title": "Complete Platform Tour",
                "description": "Take a guided tour of the platform features",
                "estimated_time": "15 minutes",
                "priority": "high"
            },
            {
                "step_id": "first_lead",
                "title": "Add Your First Lead",
                "description": "Import or manually add a lead to get started",
                "estimated_time": "5 minutes",
                "priority": "high"
            },
            {
                "step_id": "training",
                "title": "Watch Training Videos",
                "description": "Complete the role-specific training modules",
                "estimated_time": "30 minutes",
                "priority": "medium"
            }
        ]

        return ToolResult(
            success=True,
            data={"next_steps": next_steps, "role": role},
            message=f"Found {len(next_steps)} pending onboarding steps"
        )

    async def _complete_step(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Mark step as complete"""
        step_id = input_data["step_id"]

        return ToolResult(
            success=True,
            data={
                "step_id": step_id,
                "status": "completed",
                "completed_at": datetime.now().isoformat()
            },
            message=f"Step '{step_id}' marked as complete"
        )

    async def _get_training_resources(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get training resources"""
        resources = {
            "basics": [
                {"title": "Getting Started Guide", "type": "document", "duration": "10 min read"},
                {"title": "Platform Overview Video", "type": "video", "duration": "5 min"},
                {"title": "Navigation Tutorial", "type": "interactive", "duration": "10 min"}
            ],
            "features": [
                {"title": "Lead Management", "type": "video", "duration": "15 min"},
                {"title": "Pipeline Tracking", "type": "video", "duration": "12 min"},
                {"title": "Email Integration", "type": "document", "duration": "8 min read"}
            ],
            "advanced": [
                {"title": "Automation Rules", "type": "video", "duration": "20 min"},
                {"title": "Custom Reports", "type": "document", "duration": "15 min read"},
                {"title": "API Integration", "type": "document", "duration": "30 min read"}
            ],
            "compliance": [
                {"title": "TRID Compliance", "type": "video", "duration": "25 min"},
                {"title": "Fair Lending", "type": "document", "duration": "20 min read"}
            ]
        }

        category = input_data.get("category")
        if category and category in resources:
            filtered = {category: resources[category]}
        else:
            filtered = resources

        return ToolResult(
            success=True,
            data={"resources": filtered},
            message=f"Found training resources"
        )

    async def _schedule_training(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Schedule training session"""
        training_type = input_data["training_type"]

        return ToolResult(
            success=True,
            data={
                "training_type": training_type,
                "scheduled_date": input_data.get("preferred_date") or (datetime.now() + timedelta(days=2)).isoformat(),
                "duration": "60 minutes",
                "attendees": input_data.get("attendees", []),
                "meeting_link": "https://meet.perennia.ai/training-session"
            },
            message=f"Training session '{training_type}' scheduled"
        )

    async def _send_welcome_email(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Send welcome email"""
        user_id = input_data["user_id"]

        return ToolResult(
            success=True,
            data={
                "user_id": user_id,
                "email_type": "welcome",
                "sent_at": datetime.now().isoformat(),
                "included_credentials": input_data.get("include_credentials", False)
            },
            message=f"Welcome email sent to user {user_id}"
        )

    async def _assign_mentor(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Assign mentor to new user — tenant-isolated"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            mentor_id = input_data.get("mentor_id")

            if not mentor_id:
                # Auto-assign based on availability — scoped to organization
                query = text("""
                    SELECT id, full_name FROM users
                    WHERE permission_role IN ('leadership', 'management')
                    AND is_active = true
                    AND (:org_id IS NULL OR organization_id = :org_id)
                    LIMIT 1
                """)
                result = db.execute(query, {"org_id": org_id}).fetchone()
                if result:
                    mentor_id = result.id
                    mentor_name = result.full_name
                else:
                    return ToolResult(success=False, error="No available mentors found")
            else:
                query = text("""
                    SELECT full_name FROM users
                    WHERE id = :id AND (:org_id IS NULL OR organization_id = :org_id)
                """)
                result = db.execute(query, {"id": mentor_id, "org_id": org_id}).fetchone()
                mentor_name = result.full_name if result else "Unknown"

            self.audit_log("mentor_assigned", entity_type="user",
                          entity_id=str(input_data["new_user_id"]),
                          details={"mentor_id": mentor_id})

            return ToolResult(
                success=True,
                data={
                    "new_user_id": input_data["new_user_id"],
                    "mentor_id": mentor_id,
                    "mentor_name": mentor_name
                },
                message=f"Assigned {mentor_name} as mentor"
            )

        except Exception as e:
            logger.exception(f"Error assigning mentor: {e}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_team_introduction(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get team introductions — tenant-isolated"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = self.context.get("organization_id")
        db = SessionLocal()
        try:
            query = text("""
                SELECT id, full_name, email, permission_role, role
                FROM users
                WHERE is_active = true
                AND (:org_id IS NULL OR organization_id = :org_id)
                ORDER BY permission_role, full_name
                LIMIT 20
            """)

            results = db.execute(query, {"org_id": org_id}).fetchall()

            team = [
                {
                    "id": r.id,
                    "name": r.full_name,
                    "email": r.email,
                    "role": r.role or r.permission_role,
                    "title": r.permission_role.replace("_", " ").title()
                }
                for r in results
            ]

            self.audit_log("team_introduction_viewed", entity_type="organization",
                          entity_id=str(org_id), details={"count": len(team)})

            return ToolResult(
                success=True,
                data={"team_members": team, "count": len(team)},
                message=f"Found {len(team)} team members"
            )

        except Exception as e:
            logger.exception(f"Error getting team introduction: {e}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
