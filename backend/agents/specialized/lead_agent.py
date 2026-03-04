"""
Lead Management Agent

Specialized agent for lead lifecycle management with 8 tools:
1. search_leads - Search and filter leads
2. get_lead_details - Get detailed lead information
3. update_lead_stage - Move lead through pipeline stages
4. score_lead_quality - AI-powered lead scoring
5. assign_lead - Assign lead to user
6. get_lead_activity - Get lead activity timeline
7. create_lead_task - Create task for a lead
8. analyze_lead_pipeline - Pipeline analytics and bottlenecks
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from sqlalchemy import text

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

class SearchLeadsInput(BaseModel):
    """Input schema for search_leads tool"""
    stage: Optional[str] = Field(None, description="Filter by stage: new, contacted, qualified, prospect, application")
    source: Optional[str] = Field(None, description="Filter by source: website, referral, zillow, etc.")
    search_query: Optional[str] = Field(None, description="Search by name, email, or phone")
    assigned_to: Optional[int] = Field(None, description="Filter by assigned user ID")
    days_since_contact: Optional[int] = Field(None, description="Leads not contacted in X days")
    min_credit_score: Optional[int] = Field(None, description="Minimum credit score filter")
    limit: int = Field(default=20, description="Maximum results to return")


class GetLeadDetailsInput(BaseModel):
    """Input schema for get_lead_details tool"""
    lead_id: int = Field(..., description="The lead ID to retrieve")
    include_activity: bool = Field(default=True, description="Include activity history")
    include_communications: bool = Field(default=True, description="Include communication history")


class UpdateLeadStageInput(BaseModel):
    """Input schema for update_lead_stage tool"""
    lead_id: int = Field(..., description="The lead ID to update")
    new_stage: str = Field(..., description="New stage: new, contacted, qualified, prospect, application, lost")
    reason: Optional[str] = Field(None, description="Reason for stage change")


class ScoreLeadInput(BaseModel):
    """Input schema for score_lead_quality tool"""
    lead_id: int = Field(..., description="The lead ID to score")
    refresh: bool = Field(default=False, description="Force refresh of existing score")


class AssignLeadInput(BaseModel):
    """Input schema for assign_lead tool"""
    lead_id: int = Field(..., description="The lead ID to assign")
    user_id: int = Field(..., description="User ID to assign to")
    notify: bool = Field(default=True, description="Send notification to assignee")


class GetLeadActivityInput(BaseModel):
    """Input schema for get_lead_activity tool"""
    lead_id: int = Field(..., description="The lead ID")
    limit: int = Field(default=20, description="Maximum activities to return")
    activity_types: Optional[list] = Field(None, description="Filter by activity types")


class CreateLeadTaskInput(BaseModel):
    """Input schema for create_lead_task tool"""
    lead_id: int = Field(..., description="The lead ID")
    title: str = Field(..., description="Task title")
    description: Optional[str] = Field(None, description="Task description")
    due_date: Optional[str] = Field(None, description="Due date (ISO format)")
    priority: str = Field(default="normal", description="Priority: low, normal, high, urgent")
    task_type: str = Field(default="follow_up", description="Task type: follow_up, call, document_request, appointment")


class AnalyzePipelineInput(BaseModel):
    """Input schema for analyze_lead_pipeline tool"""
    days: int = Field(default=30, description="Analysis period in days")
    include_bottlenecks: bool = Field(default=True, description="Include bottleneck analysis")
    include_conversion_rates: bool = Field(default=True, description="Include conversion rate analysis")


# ============================================================================
# LEAD MANAGEMENT AGENT
# ============================================================================

@AgentRegistry.register
class LeadManagementAgent(SpecializedAgent):
    """
    Specialized agent for lead lifecycle management.

    Handles lead acquisition, qualification, nurturing, and conversion
    tracking with 8 specialized tools.
    """

    @property
    def name(self) -> str:
        return "LeadManagementAgent"

    @property
    def description(self) -> str:
        return "Manages lead lifecycle including search, scoring, assignment, and pipeline analytics"

    def _register_tools(self):
        """Register all lead management tools"""

        # Tool 1: Search Leads
        self.register_tool(AgentTool(
            name="search_leads",
            description="Search and filter leads by stage, source, credit score, or contact history. "
                       "Returns a list of matching leads with summary information.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._search_leads,
            input_schema=SearchLeadsInput
        ))

        # Tool 2: Get Lead Details
        self.register_tool(AgentTool(
            name="get_lead_details",
            description="Get comprehensive details for a specific lead including contact info, "
                       "financial data, activity timeline, and communication history.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_lead_details,
            input_schema=GetLeadDetailsInput
        ))

        # Tool 3: Update Lead Stage
        self.register_tool(AgentTool(
            name="update_lead_stage",
            description="Move a lead to a different pipeline stage (new, contacted, qualified, "
                       "prospect, application, lost). Records stage change history.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._update_lead_stage,
            input_schema=UpdateLeadStageInput
        ))

        # Tool 4: Score Lead Quality
        self.register_tool(AgentTool(
            name="score_lead_quality",
            description="Calculate a lead quality score based on credit score, DTI, down payment, "
                       "engagement level, and other factors. Returns score and classification.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._score_lead_quality,
            input_schema=ScoreLeadInput
        ))

        # Tool 5: Assign Lead
        self.register_tool(AgentTool(
            name="assign_lead",
            description="Assign a lead to a specific loan officer or team member. "
                       "Optionally sends notification to the assignee.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._assign_lead,
            input_schema=AssignLeadInput
        ))

        # Tool 6: Get Lead Activity
        self.register_tool(AgentTool(
            name="get_lead_activity",
            description="Get the activity timeline for a lead including calls, emails, "
                       "stage changes, and document submissions.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_lead_activity,
            input_schema=GetLeadActivityInput
        ))

        # Tool 7: Create Lead Task
        self.register_tool(AgentTool(
            name="create_lead_task",
            description="Create a follow-up task for a lead with due date and priority. "
                       "Task types include call, follow_up, document_request, appointment.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._create_lead_task,
            input_schema=CreateLeadTaskInput
        ))

        # Tool 8: Analyze Lead Pipeline
        self.register_tool(AgentTool(
            name="analyze_lead_pipeline",
            description="Analyze the lead pipeline for bottlenecks, conversion rates, "
                       "and stage distribution. Returns actionable insights.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_lead_pipeline,
            input_schema=AnalyzePipelineInput
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _search_leads(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Search and filter leads"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")

            # Build dynamic query based on filters
            conditions = ["1=1"]
            params = {"limit": input_data.get("limit", 20)}

            # Tenant isolation
            if org_id:
                conditions.append("organization_id = :org_id")
                params["org_id"] = org_id

            if input_data.get("stage"):
                conditions.append("stage = :stage")
                params["stage"] = input_data["stage"]

            if input_data.get("source"):
                conditions.append("source = :source")
                params["source"] = input_data["source"]

            if input_data.get("search_query"):
                conditions.append("""
                    (name ILIKE :search_pattern
                     OR first_name ILIKE :search_pattern
                     OR last_name ILIKE :search_pattern
                     OR email ILIKE :search_pattern
                     OR phone ILIKE :search_pattern)
                """)
                params["search_pattern"] = f"%{input_data['search_query']}%"

            if input_data.get("assigned_to"):
                conditions.append("assigned_to = :assigned_to")
                params["assigned_to"] = input_data["assigned_to"]

            if input_data.get("days_since_contact"):
                conditions.append("""
                    updated_at < CURRENT_TIMESTAMP - INTERVAL ':days days'
                """)
                params["days"] = input_data["days_since_contact"]

            if input_data.get("min_credit_score"):
                conditions.append("credit_score >= :min_credit")
                params["min_credit"] = input_data["min_credit_score"]

            where_clause = " AND ".join(conditions)

            query = text(f"""
                SELECT
                    id, name, first_name, last_name, email, phone,
                    stage, source, credit_score, loan_amount,
                    created_at, updated_at, assigned_to
                FROM leads
                WHERE {where_clause}
                ORDER BY updated_at DESC
                LIMIT :limit
            """)

            results = db.execute(query, params).fetchall()

            leads = []
            for row in results:
                lead_name = row.name or f"{row.first_name or ''} {row.last_name or ''}".strip() or "Unknown"
                leads.append({
                    "id": row.id,
                    "name": lead_name,
                    "email": row.email,
                    "phone": row.phone,
                    "stage": row.stage,
                    "source": row.source,
                    "credit_score": row.credit_score,
                    "loan_amount": float(row.loan_amount) if row.loan_amount else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None
                })

            # Get stage counts for context (also filtered by org)
            org_clause = "WHERE organization_id = :org_id" if org_id else ""
            stage_query = text(f"""
                SELECT stage, COUNT(*) as count
                FROM leads
                {org_clause}
                GROUP BY stage
            """)
            stage_params = {"org_id": org_id} if org_id else {}
            stage_results = db.execute(stage_query, stage_params).fetchall()
            stage_counts = {row.stage: row.count for row in stage_results}

            self.audit_log("search_leads", "lead", details={
                "filters": {k: v for k, v in input_data.items() if v is not None},
                "result_count": len(leads),
            })

            return ToolResult(
                success=True,
                data={
                    "leads": leads,
                    "count": len(leads),
                    "stage_counts": stage_counts
                },
                message=f"Found {len(leads)} leads matching criteria"
            )

        except Exception as e:
            logger.exception("search_leads failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_lead_details(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get comprehensive lead details"""
        from database import SessionLocal

        lead_id = input_data["lead_id"]
        org_id = self.context.get("organization_id")
        db = SessionLocal()

        try:
            # Get lead info with tenant isolation
            org_clause = "AND organization_id = :org_id" if org_id else ""
            params = {"lead_id": lead_id}
            if org_id:
                params["org_id"] = org_id

            query = text(f"SELECT * FROM leads WHERE id = :lead_id {org_clause}")
            result = db.execute(query, params).fetchone()

            if not result:
                return ToolResult(success=False, error=f"Lead {lead_id} not found")

            lead_data = dict(result._mapping)

            # Get activity if requested
            if input_data.get("include_activity", True):
                activity_query = text("""
                    SELECT activity_type, description, created_at, created_by
                    FROM lead_activities
                    WHERE lead_id = :lead_id
                    ORDER BY created_at DESC
                    LIMIT 10
                """)
                activities = db.execute(activity_query, {"lead_id": lead_id}).fetchall()
                lead_data["recent_activities"] = [
                    {
                        "type": a.activity_type,
                        "description": a.description,
                        "date": a.created_at.isoformat() if a.created_at else None
                    }
                    for a in activities
                ]

            # Get communications if requested
            if input_data.get("include_communications", True):
                comm_query = text("""
                    SELECT type, direction, status, content, created_at
                    FROM communications
                    WHERE lead_id = :lead_id
                    ORDER BY created_at DESC
                    LIMIT 10
                """)
                comms = db.execute(comm_query, {"lead_id": lead_id}).fetchall()
                lead_data["recent_communications"] = [
                    {
                        "type": c.type,
                        "direction": c.direction,
                        "status": c.status,
                        "date": c.created_at.isoformat() if c.created_at else None
                    }
                    for c in comms
                ]

            self.audit_log("get_lead_details", "lead", entity_id=lead_id)

            return ToolResult(success=True, data={"lead": lead_data})

        except Exception as e:
            logger.exception(f"get_lead_details failed for lead {lead_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _update_lead_stage(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Update lead stage with history tracking"""
        from database import SessionLocal

        lead_id = input_data["lead_id"]
        new_stage = input_data["new_stage"]
        reason = input_data.get("reason", "AI agent update")
        org_id = self.context.get("organization_id")

        valid_stages = ["new", "contacted", "qualified", "prospect", "application", "lost"]
        if new_stage not in valid_stages:
            return ToolResult(
                success=False,
                error=f"Invalid stage. Must be one of: {', '.join(valid_stages)}"
            )

        db = SessionLocal()
        try:
            # Get current stage with tenant isolation
            org_clause = "AND organization_id = :org_id" if org_id else ""
            params = {"lead_id": lead_id}
            if org_id:
                params["org_id"] = org_id

            current_query = text(f"SELECT stage FROM leads WHERE id = :lead_id {org_clause}")
            current = db.execute(current_query, params).fetchone()

            if not current:
                return ToolResult(success=False, error=f"Lead {lead_id} not found")

            old_stage = current.stage

            # Update stage with tenant isolation
            update_query = text(f"""
                UPDATE leads
                SET stage = :new_stage, updated_at = CURRENT_TIMESTAMP
                WHERE id = :lead_id {org_clause}
                RETURNING id, name, first_name, last_name, stage
            """)
            update_params = {"lead_id": lead_id, "new_stage": new_stage}
            if org_id:
                update_params["org_id"] = org_id
            result = db.execute(update_query, update_params).fetchone()

            # Record stage history
            history_query = text("""
                INSERT INTO lead_stage_history
                (lead_id, old_stage, new_stage, changed_by, reason, created_at)
                VALUES (:lead_id, :old_stage, :new_stage, :changed_by, :reason, CURRENT_TIMESTAMP)
            """)
            db.execute(history_query, {
                "lead_id": lead_id,
                "old_stage": old_stage,
                "new_stage": new_stage,
                "changed_by": context.get("user_id", 1),
                "reason": reason
            })

            db.commit()

            lead_name = result.name or f"{result.first_name or ''} {result.last_name or ''}".strip()

            self.audit_log("update_lead_stage", "lead", entity_id=lead_id, details={
                "old_stage": old_stage,
                "new_stage": new_stage,
                "reason": reason,
            })

            return ToolResult(
                success=True,
                data={"lead_id": lead_id, "old_stage": old_stage, "new_stage": new_stage},
                message=f"Lead '{lead_name}' moved from {old_stage} to {new_stage}"
            )

        except Exception as e:
            db.rollback()
            logger.exception(f"update_lead_stage failed for lead {lead_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _score_lead_quality(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Calculate lead quality score"""
        from database import SessionLocal

        lead_id = input_data["lead_id"]
        org_id = self.context.get("organization_id")
        db = SessionLocal()

        try:
            org_clause = "AND organization_id = :org_id" if org_id else ""
            params = {"lead_id": lead_id}
            if org_id:
                params["org_id"] = org_id

            query = text(f"""
                SELECT
                    id, credit_score, loan_amount, property_value,
                    dti, down_payment, employment_status, email, phone
                FROM leads WHERE id = :lead_id {org_clause}
            """)
            result = db.execute(query, params).fetchone()

            if not result:
                return ToolResult(success=False, error=f"Lead {lead_id} not found")

            score = 0
            factors = []

            # Credit score (max 30 points)
            credit = result.credit_score or 0
            if credit >= 740:
                score += 30
                factors.append("Excellent credit (740+)")
            elif credit >= 680:
                score += 20
                factors.append("Good credit (680-739)")
            elif credit >= 620:
                score += 10
                factors.append("Fair credit (620-679)")
            else:
                factors.append("Credit score needs review")

            # DTI (max 25 points)
            dti = result.dti or 50
            if dti <= 36:
                score += 25
                factors.append("Strong DTI (≤36%)")
            elif dti <= 43:
                score += 15
                factors.append("Acceptable DTI (37-43%)")
            elif dti <= 50:
                score += 5
                factors.append("High DTI (44-50%)")

            # Down payment (max 20 points)
            if result.property_value and result.down_payment:
                dp_percent = (result.down_payment / result.property_value) * 100
                if dp_percent >= 20:
                    score += 20
                    factors.append("20%+ down payment")
                elif dp_percent >= 10:
                    score += 12
                    factors.append("10-19% down payment")
                elif dp_percent >= 5:
                    score += 5
                    factors.append("5-9% down payment")

            # Contact completeness (max 15 points)
            if result.email and result.phone:
                score += 15
                factors.append("Complete contact info")
            elif result.email or result.phone:
                score += 8
                factors.append("Partial contact info")

            # Employment (max 10 points)
            if result.employment_status == "employed":
                score += 10
                factors.append("Employed")
            elif result.employment_status == "self_employed":
                score += 7
                factors.append("Self-employed")

            # Classify quality
            if score >= 70:
                quality = "hot"
                recommendation = "Priority follow-up within 24 hours"
            elif score >= 50:
                quality = "warm"
                recommendation = "Follow-up within 48 hours"
            elif score >= 30:
                quality = "cold"
                recommendation = "Nurture with automated campaigns"
            else:
                quality = "unqualified"
                recommendation = "May need additional qualification"

            self.audit_log("score_lead_quality", "lead", entity_id=lead_id, details={
                "score": score,
                "quality": quality,
            })

            return ToolResult(
                success=True,
                data={
                    "lead_id": lead_id,
                    "score": score,
                    "max_score": 100,
                    "quality": quality,
                    "factors": factors,
                    "recommendation": recommendation
                },
                message=f"Lead scored as {quality} ({score}/100)"
            )

        except Exception as e:
            logger.exception(f"score_lead_quality failed for lead {lead_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _assign_lead(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Assign lead to a user"""
        from database import SessionLocal

        lead_id = input_data["lead_id"]
        user_id = input_data["user_id"]
        org_id = self.context.get("organization_id")

        db = SessionLocal()
        try:
            org_clause = "AND organization_id = :org_id" if org_id else ""
            params = {"lead_id": lead_id, "user_id": user_id}
            if org_id:
                params["org_id"] = org_id

            query = text(f"""
                UPDATE leads
                SET assigned_to = :user_id, updated_at = CURRENT_TIMESTAMP
                WHERE id = :lead_id {org_clause}
                RETURNING id, name, first_name, last_name
            """)
            result = db.execute(query, params).fetchone()

            if not result:
                return ToolResult(success=False, error=f"Lead {lead_id} not found")

            db.commit()

            lead_name = result.name or f"{result.first_name or ''} {result.last_name or ''}".strip()

            self.audit_log("assign_lead", "lead", entity_id=lead_id, details={
                "assigned_to_user_id": user_id,
            })

            return ToolResult(
                success=True,
                data={"lead_id": lead_id, "assigned_to": user_id},
                message=f"Lead '{lead_name}' assigned to user {user_id}"
            )

        except Exception as e:
            db.rollback()
            logger.exception(f"assign_lead failed for lead {lead_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_lead_activity(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get lead activity timeline"""
        from database import SessionLocal

        lead_id = input_data["lead_id"]
        limit = input_data.get("limit", 20)
        org_id = self.context.get("organization_id")

        db = SessionLocal()
        try:
            # Verify lead belongs to org before fetching activities
            if org_id:
                lead_check = db.execute(
                    text("SELECT id FROM leads WHERE id = :lead_id AND organization_id = :org_id"),
                    {"lead_id": lead_id, "org_id": org_id}
                ).fetchone()
                if not lead_check:
                    return ToolResult(success=False, error=f"Lead {lead_id} not found")

            query = text("""
                SELECT
                    activity_type, description, created_at, created_by
                FROM lead_activities
                WHERE lead_id = :lead_id
                ORDER BY created_at DESC
                LIMIT :limit
            """)
            results = db.execute(query, {
                "lead_id": lead_id,
                "limit": limit
            }).fetchall()

            activities = [
                {
                    "type": r.activity_type,
                    "description": r.description,
                    "date": r.created_at.isoformat() if r.created_at else None,
                    "by": r.created_by
                }
                for r in results
            ]

            self.audit_log("get_lead_activity", "lead", entity_id=lead_id)

            return ToolResult(
                success=True,
                data={"lead_id": lead_id, "activities": activities, "count": len(activities)}
            )

        except Exception as e:
            logger.exception(f"get_lead_activity failed for lead {lead_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _create_lead_task(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Create a task for a lead"""
        from database import SessionLocal

        lead_id = input_data["lead_id"]
        org_id = self.context.get("organization_id")

        db = SessionLocal()
        try:
            # Verify lead belongs to org before creating task
            if org_id:
                lead_check = db.execute(
                    text("SELECT id FROM leads WHERE id = :lead_id AND organization_id = :org_id"),
                    {"lead_id": lead_id, "org_id": org_id}
                ).fetchone()
                if not lead_check:
                    return ToolResult(success=False, error=f"Lead {lead_id} not found")

            task_params = {
                "title": input_data["title"],
                "description": input_data.get("description", ""),
                "lead_id": lead_id,
                "due_date": input_data.get("due_date"),
                "priority": input_data.get("priority", "normal"),
                "task_type": input_data.get("task_type", "follow_up"),
                "created_by": context.get("user_id", 1),
            }

            # Include organization_id on task if available
            org_col = ", organization_id" if org_id else ""
            org_val = ", :org_id" if org_id else ""
            if org_id:
                task_params["org_id"] = org_id

            query = text(f"""
                INSERT INTO tasks (
                    title, description, entity_type, entity_id,
                    due_date, priority, task_type, status, created_by{org_col}
                ) VALUES (
                    :title, :description, 'lead', :lead_id,
                    :due_date, :priority, :task_type, 'pending', :created_by{org_val}
                )
                RETURNING id, title
            """)

            result = db.execute(query, task_params).fetchone()

            db.commit()

            self.audit_log("create_lead_task", "task", entity_id=result.id, details={
                "lead_id": lead_id,
                "title": input_data["title"],
                "priority": input_data.get("priority", "normal"),
            })

            return ToolResult(
                success=True,
                data={"task_id": result.id, "title": result.title},
                message=f"Task '{result.title}' created for lead {lead_id}"
            )

        except Exception as e:
            db.rollback()
            logger.exception(f"create_lead_task failed for lead {lead_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _analyze_lead_pipeline(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Analyze lead pipeline for insights"""
        from database import SessionLocal

        days = input_data.get("days", 30)
        org_id = self.context.get("organization_id")
        db = SessionLocal()

        try:
            org_clause = "AND organization_id = :org_id" if org_id else ""
            params = {"days": days}
            if org_id:
                params["org_id"] = org_id

            # Stage distribution
            stage_query = text(f"""
                SELECT
                    stage,
                    COUNT(*) as count,
                    AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - created_at)) / 86400) as avg_days
                FROM leads
                WHERE created_at > CURRENT_TIMESTAMP - INTERVAL ':days days'
                    {org_clause}
                GROUP BY stage
                ORDER BY count DESC
            """)
            stage_results = db.execute(stage_query, params).fetchall()

            stages = [
                {
                    "stage": r.stage,
                    "count": r.count,
                    "avg_days_in_stage": round(r.avg_days, 1) if r.avg_days else 0
                }
                for r in stage_results
            ]

            # Bottleneck detection
            bottlenecks = []
            for s in stages:
                if s["avg_days_in_stage"] > 14:
                    bottlenecks.append({
                        "stage": s["stage"],
                        "avg_days": s["avg_days_in_stage"],
                        "issue": f"Leads stuck in {s['stage']} for {s['avg_days_in_stage']:.0f} days on average"
                    })

            # Source effectiveness
            source_query = text(f"""
                SELECT
                    source,
                    COUNT(*) as total,
                    SUM(CASE WHEN stage IN ('qualified', 'prospect', 'application') THEN 1 ELSE 0 END) as qualified
                FROM leads
                WHERE created_at > CURRENT_TIMESTAMP - INTERVAL ':days days'
                    {org_clause}
                GROUP BY source
                ORDER BY total DESC
            """)
            source_results = db.execute(source_query, params).fetchall()

            sources = [
                {
                    "source": r.source,
                    "total": r.total,
                    "qualified": r.qualified,
                    "conversion_rate": round((r.qualified / r.total * 100), 1) if r.total > 0 else 0
                }
                for r in source_results
            ]

            total_leads = sum(s["count"] for s in stages)

            self.audit_log("analyze_lead_pipeline", details={
                "period_days": days,
                "total_leads": total_leads,
                "bottleneck_count": len(bottlenecks),
            })

            return ToolResult(
                success=True,
                data={
                    "period_days": days,
                    "total_leads": total_leads,
                    "stage_distribution": stages,
                    "bottlenecks": bottlenecks,
                    "source_effectiveness": sources,
                    "insights": self._generate_pipeline_insights(stages, bottlenecks, sources)
                },
                message=f"Pipeline analysis for last {days} days: {total_leads} total leads"
            )

        except Exception as e:
            logger.exception("analyze_lead_pipeline failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    def _generate_pipeline_insights(
        self,
        stages: list,
        bottlenecks: list,
        sources: list
    ) -> list:
        """Generate actionable insights from pipeline data"""
        insights = []

        # Bottleneck insights
        if bottlenecks:
            worst = max(bottlenecks, key=lambda x: x["avg_days"])
            insights.append(f"Critical: {worst['stage']} stage has {worst['avg_days']:.0f} day average - needs attention")

        # Source insights
        if sources:
            best_source = max(sources, key=lambda x: x["conversion_rate"])
            if best_source["conversion_rate"] > 0:
                insights.append(f"Top source: {best_source['source']} with {best_source['conversion_rate']}% conversion rate")

        # Stage balance
        new_count = next((s["count"] for s in stages if s["stage"] == "new"), 0)
        qualified_count = next((s["count"] for s in stages if s["stage"] == "qualified"), 0)

        if new_count > qualified_count * 3:
            insights.append("High number of new leads not being contacted - increase outreach capacity")

        return insights
