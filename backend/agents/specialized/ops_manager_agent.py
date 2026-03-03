"""
Operations Manager Agent — v2.1

Proactive, always-on agent that sweeps all three pipelines (Leads, Active Loans, MUM),
detects impediments, and creates corrective tasks automatically.

8 Tools:
1. run_pipeline_sweep - Full sweep of all 3 pipelines (orchestrator)
2. sweep_lead_pipeline - Detect stale leads, unassigned leads, no first contact
3. sweep_active_loans - Detect SLA breaches, expiring locks/docs, missing documents
4. sweep_mum_pipeline - Detect missed touchpoints, overdue MUM clients
5. detect_team_gaps - Find loans/leads missing LO, PA, processor, underwriter, closer
6. detect_stalled_files - Find files with zero activity past threshold
7. get_impediment_summary - Query open ops tasks by category
8. get_sweep_history - Query ops_sweep_results table
"""

import json
import traceback
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
# CONSTANTS
# ============================================================================

# SLA targets in days per stage
STAGE_SLA_DAYS = {
    "APPLICATION": 3,
    "DISCLOSED": 7,
    "PROCESSING": 10,
    "SUBMITTED": 2,
    "UNDERWRITING": 5,
    "UW_RECEIVED": 5,
    "CONDITIONAL_APPROVAL": 5,
    "APPROVED": 3,
    "CTC": 3,
    "CLEAR_TO_CLOSE": 3,
    "CLOSING": 5,
    "DOCS": 3,
    "DOCS_OUT": 5,
}

TERMINAL_STAGES = (
    "FUNDED", "CANCELLED", "DENIED", "DEAD",
    "WITHDRAWN", "DOES_NOT_QUALIFY"
)

# Terminal lead stages (from LeadStage enum in database/enums.py)
TERMINAL_LEAD_STAGES = (
    "Closed", "Funded", "Withdrawn", "Does Not Qualify", "Do Not Call"
)

# Stage thresholds for team role requirements
# processor required past PROCESSING, closer past APPROVED, PA past DISCLOSED
ROLE_STAGE_REQUIREMENTS = {
    "processor": ["SUBMITTED", "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
                   "APPROVED", "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT"],
    "closer": ["APPROVED", "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT"],
    "production_assistant": ["PROCESSING", "SUBMITTED", "UNDERWRITING", "UW_RECEIVED",
                             "CONDITIONAL_APPROVAL", "APPROVED", "CTC", "CLEAR_TO_CLOSE",
                             "CLOSING", "DOCS", "DOCS_OUT"],
}

IMPEDIMENT_LIMIT = 100  # Max impediments per category per sweep


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class PipelineSweepInput(BaseModel):
    organization_id: Optional[int] = Field(None, description="Organization ID to sweep")
    dry_run: bool = Field(default=False, description="If true, detect but don't create tasks")


class LeadSweepInput(BaseModel):
    organization_id: Optional[int] = Field(None, description="Organization ID")
    stale_days: int = Field(default=7, description="Days without contact to flag as stale")
    dry_run: bool = Field(default=False, description="Detect only, don't create tasks")


class LoanSweepInput(BaseModel):
    organization_id: Optional[int] = Field(None, description="Organization ID")
    lock_warning_days: int = Field(default=5, description="Days before lock expiration to warn")
    doc_warning_days: int = Field(default=14, description="Days before doc expiration to warn")
    dry_run: bool = Field(default=False, description="Detect only, don't create tasks")


class MumSweepInput(BaseModel):
    organization_id: Optional[int] = Field(None, description="Organization ID")
    overdue_days: int = Field(default=90, description="Days since last contact to flag")
    dry_run: bool = Field(default=False, description="Detect only, don't create tasks")


class TeamGapsInput(BaseModel):
    organization_id: Optional[int] = Field(None, description="Organization ID")
    dry_run: bool = Field(default=False, description="Detect only, don't create tasks")


class StalledFilesInput(BaseModel):
    organization_id: Optional[int] = Field(None, description="Organization ID")
    stalled_days: int = Field(default=14, description="Days with no activity to flag")
    dry_run: bool = Field(default=False, description="Detect only, don't create tasks")


class ImpedimentSummaryInput(BaseModel):
    organization_id: Optional[int] = Field(None, description="Organization ID")
    category: Optional[str] = Field(None, description="Filter by category prefix (SLA, LOCK, DOCS, etc.)")


class SweepHistoryInput(BaseModel):
    organization_id: Optional[int] = Field(None, description="Organization ID")
    limit: int = Field(default=20, description="Number of recent sweeps to return")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _dedup_and_create_task(db, title: str, description: str, priority: str,
                           loan_id=None, lead_id=None, owner_id=None,
                           organization_id=None, due_date=None,
                           category=None, borrower_name=None) -> bool:
    """Check for existing open task with same title in ai_tasks, create if not found.

    Writes to ai_tasks table (not tasks) so tasks appear in the frontend task list.
    Uses type='Human Needed' for open ops tasks; dedup excludes 'Completed' tasks.
    Returns True if created.
    """
    from sqlalchemy import text

    # Build dedup query against ai_tasks (type is a PostgreSQL enum — cast to text for safe comparison)
    conditions = ["title = :title", "type::text != 'Completed'"]
    params = {"title": title}

    if loan_id:
        conditions.append("loan_id = :loan_id")
        params["loan_id"] = loan_id
    if lead_id:
        conditions.append("lead_id = :lead_id")
        params["lead_id"] = lead_id

    where = " AND ".join(conditions)
    existing = db.execute(text(f"SELECT id FROM ai_tasks WHERE {where} LIMIT 1"), params).fetchone()

    if existing:
        return False

    # Create the task in ai_tasks
    insert_cols = ["title", "description", "priority", "type", "created_at"]
    insert_vals = [":title", ":description", ":priority", ":task_type", "NOW()"]
    insert_params = {"title": title, "description": description, "priority": priority, "task_type": "Human Needed"}

    if loan_id:
        insert_cols.append("loan_id")
        insert_vals.append(":loan_id")
        insert_params["loan_id"] = loan_id
    if lead_id:
        insert_cols.append("lead_id")
        insert_vals.append(":lead_id")
        insert_params["lead_id"] = lead_id
    if owner_id:
        insert_cols.append("assigned_to_id")
        insert_vals.append(":assigned_to_id")
        insert_params["assigned_to_id"] = owner_id
    if organization_id:
        insert_cols.append("organization_id")
        insert_vals.append(":organization_id")
        insert_params["organization_id"] = organization_id
    if due_date:
        insert_cols.append("due_date")
        insert_vals.append(":due_date")
        insert_params["due_date"] = due_date
    if category:
        insert_cols.append("category")
        insert_vals.append(":category")
        insert_params["category"] = category
    if borrower_name:
        insert_cols.append("borrower_name")
        insert_vals.append(":borrower_name")
        insert_params["borrower_name"] = borrower_name

    cols_sql = ", ".join(insert_cols)
    vals_sql = ", ".join(insert_vals)
    db.execute(text(f"INSERT INTO ai_tasks ({cols_sql}) VALUES ({vals_sql})"), insert_params)
    return True


# ============================================================================
# OPS MANAGER AGENT
# ============================================================================

@AgentRegistry.register
class OpsManagerAgent(SpecializedAgent):
    """
    Operations Manager Agent — proactive pipeline patrol.

    Sweeps all three pipelines (Leads, Active Loans, MUM) on demand or on schedule,
    detects impediments across 10 categories, and creates corrective tasks
    with deterministic deduplication.
    """

    @property
    def name(self) -> str:
        return "OpsManagerAgent"

    @property
    def description(self) -> str:
        return "Proactive pipeline patrol — sweeps leads, loans, and MUM pipelines to detect impediments and create corrective tasks"

    def _register_tools(self):
        """Register all 8 ops manager tools"""

        # Tool 1: Full pipeline sweep (orchestrator)
        self.register_tool(AgentTool(
            name="run_pipeline_sweep",
            description="Run a full sweep of all 3 pipelines (leads, active loans, MUM) to detect impediments and create tasks",
            category=ToolCategory.WORKFLOW,
            risk_level=RiskLevel.MEDIUM,
            handler=self._run_pipeline_sweep,
            input_schema=PipelineSweepInput
        ))

        # Tool 2: Lead pipeline sweep
        self.register_tool(AgentTool(
            name="sweep_lead_pipeline",
            description="Sweep lead pipeline for stale leads, unassigned leads, and leads with no first contact",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._sweep_lead_pipeline,
            input_schema=LeadSweepInput
        ))

        # Tool 3: Active loans sweep
        self.register_tool(AgentTool(
            name="sweep_active_loans",
            description="Sweep active loans for SLA breaches, expiring rate locks, expiring documents, and missing documents",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._sweep_active_loans,
            input_schema=LoanSweepInput
        ))

        # Tool 4: MUM pipeline sweep
        self.register_tool(AgentTool(
            name="sweep_mum_pipeline",
            description="Sweep MUM (post-close) pipeline for overdue touchpoints and no-contact clients",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._sweep_mum_pipeline,
            input_schema=MumSweepInput
        ))

        # Tool 5: Team gaps detection
        self.register_tool(AgentTool(
            name="detect_team_gaps",
            description="Find loans and leads missing required team members (LO, processor, closer, PA) based on stage",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._detect_team_gaps,
            input_schema=TeamGapsInput
        ))

        # Tool 6: Stalled files detection
        self.register_tool(AgentTool(
            name="detect_stalled_files",
            description="Find loan files with zero activity past a configurable threshold",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._detect_stalled_files,
            input_schema=StalledFilesInput
        ))

        # Tool 7: Impediment summary
        self.register_tool(AgentTool(
            name="get_impediment_summary",
            description="Get summary of open ops-created tasks grouped by impediment category and priority",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_impediment_summary,
            input_schema=ImpedimentSummaryInput
        ))

        # Tool 8: Sweep history
        self.register_tool(AgentTool(
            name="get_sweep_history",
            description="Get history of pipeline sweep runs with results and metrics",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_sweep_history,
            input_schema=SweepHistoryInput
        ))

    # ========================================================================
    # TOOL 1: FULL PIPELINE SWEEP (orchestrator)
    # ========================================================================

    async def _run_pipeline_sweep(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Orchestrate a full sweep of all 3 pipelines using a single DB session"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = input_data.get("organization_id")
        dry_run = input_data.get("dry_run", False)
        started_at = datetime.utcnow()

        # Use route's DB session if available, otherwise create one
        existing_db = context.get("_shared_db") if context else None
        db = existing_db or SessionLocal()
        shared_context = dict(context) if context else {}
        shared_context["_shared_db"] = db

        try:
            # Run each sub-sweep with shared session
            lead_result = await self._sweep_lead_pipeline(
                {"organization_id": org_id, "stale_days": 7, "dry_run": dry_run}, shared_context)
            loan_result = await self._sweep_active_loans(
                {"organization_id": org_id, "lock_warning_days": 5, "doc_warning_days": 14, "dry_run": dry_run}, shared_context)
            mum_result = await self._sweep_mum_pipeline(
                {"organization_id": org_id, "overdue_days": 90, "dry_run": dry_run}, shared_context)
            team_result = await self._detect_team_gaps(
                {"organization_id": org_id, "dry_run": dry_run}, shared_context)
            stalled_result = await self._detect_stalled_files(
                {"organization_id": org_id, "stalled_days": 14, "dry_run": dry_run}, shared_context)

            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()

            # Aggregate results
            lead_data = lead_result.data or {}
            loan_data = loan_result.data or {}
            mum_data = mum_result.data or {}
            team_data = team_result.data or {}
            stalled_data = stalled_result.data or {}

            total_impediments = (
                lead_data.get("impediments_found", 0) +
                loan_data.get("impediments_found", 0) +
                mum_data.get("impediments_found", 0) +
                team_data.get("impediments_found", 0) +
                stalled_data.get("impediments_found", 0)
            )
            total_tasks_created = (
                lead_data.get("tasks_created", 0) +
                loan_data.get("tasks_created", 0) +
                mum_data.get("tasks_created", 0) +
                team_data.get("tasks_created", 0) +
                stalled_data.get("tasks_created", 0)
            )
            total_skipped = (
                lead_data.get("tasks_skipped_dedup", 0) +
                loan_data.get("tasks_skipped_dedup", 0) +
                mum_data.get("tasks_skipped_dedup", 0) +
                team_data.get("tasks_skipped_dedup", 0) +
                stalled_data.get("tasks_skipped_dedup", 0)
            )

            impediment_breakdown = {}
            for sub_data in [lead_data, loan_data, mum_data, team_data, stalled_data]:
                for cat, count in sub_data.get("by_category", {}).items():
                    impediment_breakdown[cat] = impediment_breakdown.get(cat, 0) + count

            # Record sweep result (auto-create table if missing)
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS ops_sweep_results (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER,
                        sweep_type VARCHAR(50) NOT NULL DEFAULT 'full',
                        started_at TIMESTAMP NOT NULL,
                        completed_at TIMESTAMP,
                        duration_seconds NUMERIC(10,2),
                        leads_scanned INTEGER DEFAULT 0,
                        loans_scanned INTEGER DEFAULT 0,
                        mum_scanned INTEGER DEFAULT 0,
                        impediments_found INTEGER DEFAULT 0,
                        tasks_created INTEGER DEFAULT 0,
                        tasks_skipped_dedup INTEGER DEFAULT 0,
                        impediment_breakdown JSONB DEFAULT '{}',
                        dry_run BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                db.execute(text("""
                    INSERT INTO ops_sweep_results (
                        organization_id, sweep_type, started_at, completed_at,
                        duration_seconds, leads_scanned, loans_scanned, mum_scanned,
                        impediments_found, tasks_created, tasks_skipped_dedup,
                        impediment_breakdown, dry_run
                    ) VALUES (
                        :org_id, 'full', :started, :completed,
                        :duration, :leads, :loans, :mum,
                        :impediments, :created, :skipped,
                        :breakdown, :dry_run
                    )
                """), {
                    "org_id": org_id,
                    "started": started_at,
                    "completed": completed_at,
                    "duration": round(duration, 2),
                    "leads": lead_data.get("scanned", 0),
                    "loans": loan_data.get("scanned", 0),
                    "mum": mum_data.get("scanned", 0),
                    "impediments": total_impediments,
                    "created": total_tasks_created,
                    "skipped": total_skipped,
                    "breakdown": json.dumps(impediment_breakdown),
                    "dry_run": dry_run,
                })
                db.commit()
            except Exception as e:
                logger.warning(f"Failed to record sweep result: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass

            return ToolResult(
                success=True,
                data={
                    "sweep_type": "full",
                    "dry_run": dry_run,
                    "duration_seconds": round(duration, 2),
                    "leads_scanned": lead_data.get("scanned", 0),
                    "loans_scanned": loan_data.get("scanned", 0),
                    "mum_scanned": mum_data.get("scanned", 0),
                    "impediments_found": total_impediments,
                    "tasks_created": total_tasks_created,
                    "tasks_skipped_dedup": total_skipped,
                    "impediment_breakdown": impediment_breakdown,
                    "sub_results": {
                        "leads": lead_data,
                        "loans": loan_data,
                        "mum": mum_data,
                        "team_gaps": team_data,
                        "stalled_files": stalled_data,
                    },
                    "sub_errors": {
                        name: res.error for name, res in [
                            ("leads", lead_result), ("loans", loan_result),
                            ("mum", mum_result), ("team_gaps", team_result),
                            ("stalled_files", stalled_result),
                        ] if not res.success and res.error
                    },
                },
                message=f"Sweep complete: {total_impediments} impediments, {total_tasks_created} tasks created, {total_skipped} deduped ({round(duration, 1)}s)"
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            if not existing_db:
                db.close()

    # ========================================================================
    # TOOL 2: LEAD PIPELINE SWEEP
    # ========================================================================

    async def _sweep_lead_pipeline(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Detect stale leads, unassigned leads, no first contact"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = input_data.get("organization_id")
        stale_days = input_data.get("stale_days", 7)
        dry_run = input_data.get("dry_run", False)

        shared_db = context.get("_shared_db") if context else None
        db = shared_db or SessionLocal()
        try:
            org_filter = "AND l.organization_id = :org_id" if org_id else ""
            params = {"stale_days": stale_days}
            if org_id:
                params["org_id"] = org_id

            impediments = []
            by_category = {}
            tasks_created = 0
            tasks_skipped = 0

            # --- LEAD_STALE: leads with no contact past threshold ---
            stale_leads = db.execute(text(f"""
                SELECT l.id, l.first_name, l.last_name, l.owner_id, l.organization_id,
                       l.last_contact,
                       EXTRACT(EPOCH FROM (NOW() - COALESCE(l.last_contact, l.created_at))) / 86400 AS days_no_contact
                FROM leads l
                WHERE l.stage NOT IN ('Closed', 'Funded', 'Withdrawn', 'Does Not Qualify', 'Do Not Call')
                    AND COALESCE(l.last_contact, l.created_at) < NOW() - INTERVAL ':stale_days days'
                    {org_filter}
                ORDER BY days_no_contact DESC
                LIMIT :limit
            """.replace(":stale_days days", f"{int(stale_days)} days")), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

            by_category["LEAD_STALE"] = len(stale_leads)
            for lead in stale_leads:
                days = int(lead.days_no_contact) if lead.days_no_contact else stale_days
                name = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or "Unknown"
                title = f"[LEAD] No contact in {days}d: {name}"
                priority = "high" if days > 14 else "medium"
                impediments.append({"category": "LEAD_STALE", "title": title, "priority": priority})

                if not dry_run:
                    created = _dedup_and_create_task(
                        db, title=title,
                        description=f"Lead has had no contact in {days} days. Last contact: {lead.last_contact or 'never'}.",
                        priority=priority, lead_id=lead.id, owner_id=lead.owner_id,
                        organization_id=lead.organization_id)
                    if created:
                        tasks_created += 1
                    else:
                        tasks_skipped += 1

            # --- LEAD_NO_OWNER: unassigned leads ---
            unassigned = db.execute(text(f"""
                SELECT l.id, l.first_name, l.last_name, l.organization_id, l.created_at
                FROM leads l
                WHERE l.owner_id IS NULL
                    AND l.stage NOT IN ('Closed', 'Funded', 'Withdrawn', 'Does Not Qualify', 'Do Not Call')
                    {org_filter}
                ORDER BY l.created_at ASC
                LIMIT :limit
            """), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

            by_category["LEAD_NO_OWNER"] = len(unassigned)
            for lead in unassigned:
                name = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or "Unknown"
                title = f"[ASSIGN] Unassigned lead needs LO: {name}"
                impediments.append({"category": "LEAD_NO_OWNER", "title": title, "priority": "high"})

                if not dry_run:
                    created = _dedup_and_create_task(
                        db, title=title,
                        description=f"Lead '{name}' has no assigned loan officer. Created: {lead.created_at}.",
                        priority="high", lead_id=lead.id, organization_id=lead.organization_id)
                    if created:
                        tasks_created += 1
                    else:
                        tasks_skipped += 1

            if not dry_run:
                db.commit()

            scanned_row = db.execute(text(f"""
                SELECT COUNT(*) as cnt FROM leads l
                WHERE l.stage NOT IN ('Closed', 'Funded', 'Withdrawn', 'Does Not Qualify', 'Do Not Call')
                {org_filter}
            """), params).fetchone()
            scanned = scanned_row.cnt if scanned_row else 0

            return ToolResult(
                success=True,
                data={
                    "scanned": scanned,
                    "impediments_found": len(impediments),
                    "tasks_created": tasks_created,
                    "tasks_skipped_dedup": tasks_skipped,
                    "by_category": by_category,
                    "impediments": impediments[:50],
                },
                message=f"Lead sweep: {len(impediments)} impediments from {scanned} leads"
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Ops manager sub-sweep error: {e}\n{tb}")
            try:
                db.rollback()
            except Exception:
                pass
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")
        finally:
            if not shared_db:
                db.close()

    # ========================================================================
    # TOOL 3: ACTIVE LOANS SWEEP
    # ========================================================================

    async def _sweep_active_loans(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Detect SLA breaches, expiring locks, expiring docs, missing docs, open compliance alerts"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = input_data.get("organization_id")
        lock_days = input_data.get("lock_warning_days", 5)
        doc_days = input_data.get("doc_warning_days", 14)
        dry_run = input_data.get("dry_run", False)

        shared_db = context.get("_shared_db") if context else None
        db = shared_db or SessionLocal()
        try:
            terminal_list = ", ".join(f"'{s}'" for s in TERMINAL_STAGES)
            org_filter = "AND l.organization_id = :org_id" if org_id else ""
            params = {}
            if org_id:
                params["org_id"] = org_id

            impediments = []
            by_category = {}
            tasks_created = 0
            tasks_skipped = 0

            # --- SLA_BREACH: loans over SLA for their stage ---
            sla_cases = " ".join(
                f"WHEN '{stage}' THEN {days}" for stage, days in STAGE_SLA_DAYS.items()
            )
            sla_loans = db.execute(text(f"""
                SELECT l.id, l.loan_number, l.borrower_name, l.stage,
                       l.loan_officer_id, l.organization_id,
                       EXTRACT(EPOCH FROM (NOW() - l.stage_changed_at)) / 86400 AS days_in_stage,
                       CASE l.stage {sla_cases} ELSE 10 END AS sla_target
                FROM loans l
                WHERE l.stage NOT IN ({terminal_list})
                    AND l.stage_changed_at IS NOT NULL
                    AND EXTRACT(EPOCH FROM (NOW() - l.stage_changed_at)) / 86400 >
                        CASE l.stage {sla_cases} ELSE 10 END
                    {org_filter}
                ORDER BY days_in_stage DESC
                LIMIT :limit
            """), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

            by_category["SLA_BREACH"] = len(sla_loans)
            for loan in sla_loans:
                days = int(loan.days_in_stage)
                title = f"[SLA] {loan.stage} overdue ({days}d): {loan.borrower_name or 'Unknown'} ({loan.loan_number or ''})"
                priority = "high"
                impediments.append({"category": "SLA_BREACH", "title": title, "priority": priority})
                if not dry_run:
                    created = _dedup_and_create_task(
                        db, title=title,
                        description=f"Loan has been in {loan.stage} for {days} days (SLA target: {loan.sla_target}d).",
                        priority=priority, loan_id=loan.id, owner_id=loan.loan_officer_id,
                        organization_id=loan.organization_id)
                    tasks_created += 1 if created else 0
                    tasks_skipped += 0 if created else 1

            # --- LOCK_EXPIRING: rate locks expiring soon ---
            lock_loans = db.execute(text(f"""
                SELECT l.id, l.loan_number, l.borrower_name, l.lock_expiration_date,
                       l.loan_officer_id, l.organization_id,
                       EXTRACT(EPOCH FROM (l.lock_expiration_date - NOW())) / 86400 AS days_until_expiry
                FROM loans l
                WHERE l.stage NOT IN ({terminal_list})
                    AND l.lock_expiration_date IS NOT NULL
                    AND l.lock_expiration_date <= NOW() + INTERVAL ':lock_days days'
                    AND l.lock_expiration_date > NOW() - INTERVAL '30 days'
                    {org_filter}
                ORDER BY l.lock_expiration_date ASC
                LIMIT :limit
            """.replace(":lock_days days", f"{int(lock_days)} days")), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

            by_category["LOCK_EXPIRING"] = len(lock_loans)
            for loan in lock_loans:
                days_left = int(loan.days_until_expiry) if loan.days_until_expiry and loan.days_until_expiry > 0 else 0
                expired = loan.days_until_expiry is not None and loan.days_until_expiry < 0
                title = f"[LOCK] Rate lock {'EXPIRED' if expired else f'expires in {days_left}d'}: {loan.borrower_name or 'Unknown'} ({loan.loan_number or ''})"
                priority = "high"
                impediments.append({"category": "LOCK_EXPIRING", "title": title, "priority": priority})
                if not dry_run:
                    created = _dedup_and_create_task(
                        db, title=title,
                        description=f"Rate lock expires {loan.lock_expiration_date}.",
                        priority=priority, loan_id=loan.id, owner_id=loan.loan_officer_id,
                        organization_id=loan.organization_id,
                        due_date=loan.lock_expiration_date)
                    tasks_created += 1 if created else 0
                    tasks_skipped += 0 if created else 1

            # --- DOCS_EXPIRING: credit or appraisal docs expiring ---
            doc_loans = db.execute(text(f"""
                SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id, l.organization_id,
                       l.credit_docs_expire_date, l.appraisal_docs_expire_date
                FROM loans l
                WHERE l.stage NOT IN ({terminal_list})
                    AND (
                        (l.credit_docs_expire_date IS NOT NULL AND l.credit_docs_expire_date <= NOW() + INTERVAL ':doc_days days')
                        OR (l.appraisal_docs_expire_date IS NOT NULL AND l.appraisal_docs_expire_date <= NOW() + INTERVAL ':doc_days days')
                    )
                    {org_filter}
                LIMIT :limit
            """.replace(":doc_days days", f"{int(doc_days)} days")), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

            docs_count = 0
            for loan in doc_loans:
                for doc_type, col in [("Credit docs", loan.credit_docs_expire_date),
                                      ("Appraisal docs", loan.appraisal_docs_expire_date)]:
                    if col and col <= datetime.utcnow() + timedelta(days=doc_days):
                        exp_date = col.strftime("%m/%d/%Y") if hasattr(col, 'strftime') else str(col)
                        title = f"[DOCS] {doc_type} expiring {exp_date}: {loan.borrower_name or 'Unknown'} ({loan.loan_number or ''})"
                        impediments.append({"category": "DOCS_EXPIRING", "title": title, "priority": "high"})
                        docs_count += 1
                        if not dry_run:
                            created = _dedup_and_create_task(
                                db, title=title,
                                description=f"{doc_type} expire on {exp_date}. Renewal needed.",
                                priority="high", loan_id=loan.id, owner_id=loan.loan_officer_id,
                                organization_id=loan.organization_id, due_date=col)
                            tasks_created += 1 if created else 0
                            tasks_skipped += 0 if created else 1
            by_category["DOCS_EXPIRING"] = docs_count

            # --- COMPLIANCE_OPEN: critical/high compliance alerts ---
            try:
                compliance_alerts = db.execute(text(f"""
                    SELECT ca.id, ca.title as alert_title, ca.severity, ca.loan_id,
                           l.loan_number, l.borrower_name, l.loan_officer_id, l.organization_id
                    FROM compliance_alerts ca
                    JOIN loans l ON l.id = ca.loan_id
                    WHERE ca.status = 'open'
                        AND ca.severity IN ('critical', 'high')
                        AND l.stage NOT IN ({terminal_list})
                        {org_filter}
                    ORDER BY CASE ca.severity WHEN 'critical' THEN 1 ELSE 2 END
                    LIMIT :limit
                """), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

                by_category["COMPLIANCE_OPEN"] = len(compliance_alerts)
                for alert in compliance_alerts:
                    title = f"[COMPLIANCE] {alert.alert_title}: {alert.borrower_name or 'Unknown'} ({alert.loan_number or ''})"
                    priority = "high"
                    impediments.append({"category": "COMPLIANCE_OPEN", "title": title, "priority": priority})
                    if not dry_run:
                        created = _dedup_and_create_task(
                            db, title=title,
                            description=f"Open {alert.severity} compliance alert: {alert.alert_title}.",
                            priority=priority, loan_id=alert.loan_id, owner_id=alert.loan_officer_id,
                            organization_id=alert.organization_id)
                        tasks_created += 1 if created else 0
                        tasks_skipped += 0 if created else 1
            except Exception as e:
                logger.warning(f"COMPLIANCE_OPEN check skipped (table may not exist): {e}")
                try:
                    db.rollback()
                except Exception:
                    pass
                by_category["COMPLIANCE_OPEN"] = 0

            # --- MISSING_DOCS: loans past PROCESSING with <3 active documents ---
            try:
                missing_doc_loans = db.execute(text(f"""
                    SELECT l.id, l.loan_number, l.borrower_name, l.stage,
                           l.loan_officer_id, l.organization_id,
                           COUNT(d.id) FILTER (WHERE d.status = 'active') as active_doc_count
                    FROM loans l
                    LEFT JOIN documents d ON d.loan_id = l.id
                    WHERE l.stage NOT IN ({terminal_list}, 'APPLICATION', 'DISCLOSED')
                        {org_filter}
                    GROUP BY l.id, l.loan_number, l.borrower_name, l.stage, l.loan_officer_id, l.organization_id
                    HAVING COUNT(d.id) FILTER (WHERE d.status = 'active') < 3
                    LIMIT :limit
                """), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

                by_category["MISSING_DOCS"] = len(missing_doc_loans)
                for loan in missing_doc_loans:
                    title = f"[DOCS] Missing documents ({loan.active_doc_count} on file): {loan.borrower_name or 'Unknown'} ({loan.loan_number or ''})"
                    impediments.append({"category": "MISSING_DOCS", "title": title, "priority": "medium"})
                    if not dry_run:
                        created = _dedup_and_create_task(
                            db, title=title,
                            description=f"Loan in {loan.stage} has only {loan.active_doc_count} active documents. Minimum 3 expected.",
                            priority="medium", loan_id=loan.id, owner_id=loan.loan_officer_id,
                            organization_id=loan.organization_id)
                        tasks_created += 1 if created else 0
                        tasks_skipped += 0 if created else 1
            except Exception as e:
                logger.warning(f"MISSING_DOCS check skipped (table may not exist): {e}")
                try:
                    db.rollback()
                except Exception:
                    pass
                by_category["MISSING_DOCS"] = 0

            if not dry_run:
                db.commit()

            scanned_row = db.execute(text(f"""
                SELECT COUNT(*) as cnt FROM loans l
                WHERE l.stage NOT IN ({terminal_list}) {org_filter}
            """), params).fetchone()
            scanned = scanned_row.cnt if scanned_row else 0

            return ToolResult(
                success=True,
                data={
                    "scanned": scanned,
                    "impediments_found": len(impediments),
                    "tasks_created": tasks_created,
                    "tasks_skipped_dedup": tasks_skipped,
                    "by_category": by_category,
                    "impediments": impediments[:50],
                },
                message=f"Loan sweep: {len(impediments)} impediments from {scanned} active loans"
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Ops manager sub-sweep error: {e}\n{tb}")
            try:
                db.rollback()
            except Exception:
                pass
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")
        finally:
            if not shared_db:
                db.close()

    # ========================================================================
    # TOOL 4: MUM PIPELINE SWEEP
    # ========================================================================

    async def _sweep_mum_pipeline(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Detect overdue MUM (post-close) touchpoints"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = input_data.get("organization_id")
        overdue_days = input_data.get("overdue_days", 90)
        dry_run = input_data.get("dry_run", False)

        shared_db = context.get("_shared_db") if context else None
        db = shared_db or SessionLocal()
        try:
            org_filter = "AND l.organization_id = :org_id" if org_id else ""
            params = {}
            if org_id:
                params["org_id"] = org_id

            impediments = []
            by_category = {}
            tasks_created = 0
            tasks_skipped = 0

            # MUM clients = funded loans where borrower needs ongoing touchpoints
            mum_clients = db.execute(text(f"""
                SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
                       l.loan_officer_id, l.organization_id, l.funded_date,
                       COALESCE(
                           (SELECT MAX(a.created_at) FROM activities a WHERE a.loan_id = l.id),
                           l.funded_date
                       ) as last_activity,
                       EXTRACT(EPOCH FROM (NOW() - COALESCE(
                           (SELECT MAX(a.created_at) FROM activities a WHERE a.loan_id = l.id),
                           l.funded_date
                       ))) / 86400 AS days_since_contact
                FROM loans l
                WHERE l.stage = 'FUNDED'
                    AND l.funded_date IS NOT NULL
                    AND COALESCE(
                        (SELECT MAX(a.created_at) FROM activities a WHERE a.loan_id = l.id),
                        l.funded_date
                    ) < NOW() - INTERVAL ':overdue days'
                    {org_filter}
                ORDER BY days_since_contact DESC
                LIMIT :limit
            """.replace(":overdue days", f"{int(overdue_days)} days")), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

            by_category["MUM_OVERDUE"] = len(mum_clients)
            for client in mum_clients:
                days = int(client.days_since_contact) if client.days_since_contact else overdue_days
                name = client.borrower_name or "Unknown"
                title = f"[MUM] Overdue touchpoint ({days}d): {name}"
                priority = "high" if days > 180 else "medium"
                impediments.append({"category": "MUM_OVERDUE", "title": title, "priority": priority})

                if not dry_run:
                    created = _dedup_and_create_task(
                        db, title=title,
                        description=f"Post-close client '{name}' has not been contacted in {days} days. Funded: {client.funded_date}.",
                        priority=priority, loan_id=client.id, owner_id=client.loan_officer_id,
                        organization_id=client.organization_id,
                        category="mum_client", borrower_name=name)
                    tasks_created += 1 if created else 0
                    tasks_skipped += 0 if created else 1

            if not dry_run:
                db.commit()

            scanned_row = db.execute(text(f"""
                SELECT COUNT(*) as cnt FROM loans l
                WHERE l.stage = 'FUNDED' AND l.funded_date IS NOT NULL {org_filter}
            """), params).fetchone()
            scanned = scanned_row.cnt if scanned_row else 0

            return ToolResult(
                success=True,
                data={
                    "scanned": scanned,
                    "impediments_found": len(impediments),
                    "tasks_created": tasks_created,
                    "tasks_skipped_dedup": tasks_skipped,
                    "by_category": by_category,
                    "impediments": impediments[:50],
                },
                message=f"MUM sweep: {len(impediments)} overdue from {scanned} funded loans"
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Ops manager sub-sweep error: {e}\n{tb}")
            try:
                db.rollback()
            except Exception:
                pass
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")
        finally:
            if not shared_db:
                db.close()

    # ========================================================================
    # TOOL 5: TEAM GAPS DETECTION
    # ========================================================================

    async def _detect_team_gaps(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Find loans/leads missing required team members"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = input_data.get("organization_id")
        dry_run = input_data.get("dry_run", False)

        shared_db = context.get("_shared_db") if context else None
        db = shared_db or SessionLocal()
        try:
            terminal_list = ", ".join(f"'{s}'" for s in TERMINAL_STAGES)
            org_filter = "AND l.organization_id = :org_id" if org_id else ""
            params = {}
            if org_id:
                params["org_id"] = org_id

            impediments = []
            by_category = {}
            tasks_created = 0
            tasks_skipped = 0

            # --- LOAN_MISSING_LO: loans with no loan officer ---
            no_lo = db.execute(text(f"""
                SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.organization_id
                FROM loans l
                WHERE l.loan_officer_id IS NULL
                    AND l.stage NOT IN ({terminal_list})
                    {org_filter}
                LIMIT :limit
            """), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

            by_category["LOAN_MISSING_LO"] = len(no_lo)
            for loan in no_lo:
                title = f"[ASSIGN] Loan needs LO: {loan.borrower_name or 'Unknown'} ({loan.loan_number or ''})"
                impediments.append({"category": "LOAN_MISSING_LO", "title": title, "priority": "high"})
                if not dry_run:
                    created = _dedup_and_create_task(
                        db, title=title,
                        description=f"Active loan in {loan.stage} has no assigned loan officer.",
                        priority="high", loan_id=loan.id, organization_id=loan.organization_id)
                    tasks_created += 1 if created else 0
                    tasks_skipped += 0 if created else 1

            # --- LOAN_TEAM_GAPS: missing processor/closer/PA based on stage ---
            for role, required_stages in ROLE_STAGE_REQUIREMENTS.items():
                stages_list = ", ".join(f"'{s}'" for s in required_stages)
                # Columns are plain String (name), not FK _id columns
                col_name = role  # processor, closer, production_assistant

                try:
                    gaps = db.execute(text(f"""
                        SELECT l.id, l.loan_number, l.borrower_name, l.stage,
                               l.loan_officer_id, l.organization_id
                        FROM loans l
                        WHERE l.stage IN ({stages_list})
                            AND (l.{col_name} IS NULL OR TRIM(l.{col_name}) = '')
                            AND l.stage NOT IN ({terminal_list})
                            {org_filter}
                        LIMIT :limit
                    """), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()
                except Exception:
                    # Column may not exist — skip this role
                    gaps = []

                role_label = role.replace("_", " ").title()
                gap_key = f"LOAN_TEAM_GAPS_{role.upper()}"
                by_category[gap_key] = len(gaps)

                for loan in gaps:
                    title = f"[TEAM] Missing {role_label}: {loan.borrower_name or 'Unknown'} ({loan.loan_number or ''})"
                    priority = "high" if role == "processor" else "medium"
                    impediments.append({"category": "LOAN_TEAM_GAPS", "title": title, "priority": priority})
                    if not dry_run:
                        created = _dedup_and_create_task(
                            db, title=title,
                            description=f"Loan in {loan.stage} is missing a {role_label}.",
                            priority=priority, loan_id=loan.id, owner_id=loan.loan_officer_id,
                            organization_id=loan.organization_id)
                        tasks_created += 1 if created else 0
                        tasks_skipped += 0 if created else 1

            if not dry_run:
                db.commit()

            return ToolResult(
                success=True,
                data={
                    "impediments_found": len(impediments),
                    "tasks_created": tasks_created,
                    "tasks_skipped_dedup": tasks_skipped,
                    "by_category": by_category,
                    "impediments": impediments[:50],
                },
                message=f"Team gaps: {len(impediments)} found"
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Ops manager sub-sweep error: {e}\n{tb}")
            try:
                db.rollback()
            except Exception:
                pass
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")
        finally:
            if not shared_db:
                db.close()

    # ========================================================================
    # TOOL 6: STALLED FILES DETECTION
    # ========================================================================

    async def _detect_stalled_files(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Find loan files with zero activity past threshold"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = input_data.get("organization_id")
        stalled_days = input_data.get("stalled_days", 14)
        dry_run = input_data.get("dry_run", False)

        shared_db = context.get("_shared_db") if context else None
        db = shared_db or SessionLocal()
        try:
            terminal_list = ", ".join(f"'{s}'" for s in TERMINAL_STAGES)
            org_filter = "AND l.organization_id = :org_id" if org_id else ""
            params = {}
            if org_id:
                params["org_id"] = org_id

            stalled = db.execute(text(f"""
                SELECT l.id, l.loan_number, l.borrower_name, l.stage,
                       l.loan_officer_id, l.organization_id,
                       COALESCE(
                           (SELECT MAX(a.created_at) FROM activities a WHERE a.loan_id = l.id),
                           l.stage_changed_at,
                           l.created_at
                       ) as last_activity,
                       EXTRACT(EPOCH FROM (NOW() - COALESCE(
                           (SELECT MAX(a.created_at) FROM activities a WHERE a.loan_id = l.id),
                           l.stage_changed_at,
                           l.created_at
                       ))) / 86400 AS days_stalled
                FROM loans l
                WHERE l.stage NOT IN ({terminal_list})
                    AND COALESCE(
                        (SELECT MAX(a.created_at) FROM activities a WHERE a.loan_id = l.id),
                        l.stage_changed_at,
                        l.created_at
                    ) < NOW() - INTERVAL ':stalled days'
                    {org_filter}
                ORDER BY days_stalled DESC
                LIMIT :limit
            """.replace(":stalled days", f"{int(stalled_days)} days")), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

            impediments = []
            tasks_created = 0
            tasks_skipped = 0

            for loan in stalled:
                days = int(loan.days_stalled) if loan.days_stalled else stalled_days
                title = f"[STALLED] No activity in {days}d: {loan.borrower_name or 'Unknown'} ({loan.loan_number or ''})"
                priority = "high" if days > 30 else "medium"
                impediments.append({"category": "STALLED", "title": title, "priority": priority})

                if not dry_run:
                    created = _dedup_and_create_task(
                        db, title=title,
                        description=f"Loan in {loan.stage} has had no activity for {days} days. Last activity: {loan.last_activity}.",
                        priority=priority, loan_id=loan.id, owner_id=loan.loan_officer_id,
                        organization_id=loan.organization_id)
                    tasks_created += 1 if created else 0
                    tasks_skipped += 0 if created else 1

            if not dry_run:
                db.commit()

            return ToolResult(
                success=True,
                data={
                    "stalled_threshold_days": stalled_days,
                    "impediments_found": len(impediments),
                    "tasks_created": tasks_created,
                    "tasks_skipped_dedup": tasks_skipped,
                    "impediments": impediments[:50],
                },
                message=f"Stalled files: {len(impediments)} loans with no activity in {stalled_days}+ days"
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Ops manager sub-sweep error: {e}\n{tb}")
            try:
                db.rollback()
            except Exception:
                pass
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")
        finally:
            if not shared_db:
                db.close()

    # ========================================================================
    # TOOL 7: IMPEDIMENT SUMMARY
    # ========================================================================

    async def _get_impediment_summary(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Query open ops tasks grouped by category prefix"""
        from sqlalchemy import text

        org_id = input_data.get("organization_id")
        category = input_data.get("category")

        shared_db = context.get("_shared_db") if context else None
        if shared_db:
            db = shared_db
        else:
            from database import SessionLocal
            db = SessionLocal()
        try:
            org_filter = "AND t.organization_id = :org_id" if org_id else ""
            params = {}
            if org_id:
                params["org_id"] = org_id

            # Tasks created by ops sweep have titles like [CATEGORY] ...
            category_filter = ""
            if category:
                category_filter = "AND t.title LIKE :cat_pattern"
                params["cat_pattern"] = f"[{category.upper()}]%"

            # Only match ops-manager-created task prefixes (not arbitrary [xyz] tasks)
            ops_prefixes = (
                "t.title LIKE '[SLA]%' OR t.title LIKE '[LOCK]%' OR "
                "t.title LIKE '[DOCS]%' OR t.title LIKE '[COMPLIANCE]%' OR "
                "t.title LIKE '[LEAD]%' OR t.title LIKE '[ASSIGN]%' OR "
                "t.title LIKE '[TEAM]%' OR t.title LIKE '[MUM]%' OR "
                "t.title LIKE '[STALLED]%'"
            )

            summary = db.execute(text(f"""
                SELECT
                    CASE
                        WHEN t.title LIKE '[SLA]%' THEN 'SLA_BREACH'
                        WHEN t.title LIKE '[LOCK]%' THEN 'LOCK_EXPIRING'
                        WHEN t.title LIKE '[DOCS]%' THEN 'DOCS'
                        WHEN t.title LIKE '[COMPLIANCE]%' THEN 'COMPLIANCE_OPEN'
                        WHEN t.title LIKE '[LEAD]%' THEN 'LEAD_STALE'
                        WHEN t.title LIKE '[ASSIGN]%' THEN 'UNASSIGNED'
                        WHEN t.title LIKE '[TEAM]%' THEN 'TEAM_GAPS'
                        WHEN t.title LIKE '[MUM]%' THEN 'MUM_OVERDUE'
                        WHEN t.title LIKE '[STALLED]%' THEN 'STALLED'
                    END as category,
                    t.priority,
                    COUNT(*) as count
                FROM ai_tasks t
                WHERE t.type::text != 'Completed'
                    AND ({ops_prefixes})
                    {category_filter}
                    {org_filter}
                GROUP BY category, t.priority
                ORDER BY category, t.priority
            """), params).fetchall()

            # Pivot into category -> {priority: count}
            categories = {}
            total = 0
            for row in summary:
                cat = row.category
                if cat not in categories:
                    categories[cat] = {"total": 0, "by_priority": {}}
                categories[cat]["by_priority"][row.priority] = row.count
                categories[cat]["total"] += row.count
                total += row.count

            return ToolResult(
                success=True,
                data={
                    "total_open_impediments": total,
                    "by_category": categories,
                },
                message=f"{total} open impediments across {len(categories)} categories"
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Ops manager sub-sweep error: {e}\n{tb}")
            try:
                db.rollback()
            except Exception:
                pass
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")
        finally:
            if not shared_db:
                db.close()

    # ========================================================================
    # TOOL 8: SWEEP HISTORY
    # ========================================================================

    async def _get_sweep_history(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Query ops_sweep_results table for sweep history"""
        from sqlalchemy import text

        org_id = input_data.get("organization_id")
        limit = input_data.get("limit", 20)

        shared_db = context.get("_shared_db") if context else None
        if shared_db:
            db = shared_db
        else:
            from database import SessionLocal
            db = SessionLocal()
        try:
            # Check if table exists (it may not have been created yet)
            table_check = db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'ops_sweep_results'
                )
            """)).scalar()
            if not table_check:
                return ToolResult(
                    success=True,
                    data={"sweeps": [], "count": 0},
                    message="No sweep history yet (table not created — run a sweep first)"
                )

            org_filter = "WHERE organization_id = :org_id" if org_id else ""
            params = {"limit": limit}
            if org_id:
                params["org_id"] = org_id

            sweeps = db.execute(text(f"""
                SELECT id, organization_id, sweep_type, started_at, completed_at,
                       duration_seconds, leads_scanned, loans_scanned, mum_scanned,
                       impediments_found, tasks_created, tasks_skipped_dedup,
                       impediment_breakdown, dry_run
                FROM ops_sweep_results
                {org_filter}
                ORDER BY started_at DESC
                LIMIT :limit
            """), params).fetchall()

            results = []
            for s in sweeps:
                results.append({
                    "id": s.id,
                    "sweep_type": s.sweep_type,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "duration_seconds": float(s.duration_seconds) if s.duration_seconds else None,
                    "leads_scanned": s.leads_scanned,
                    "loans_scanned": s.loans_scanned,
                    "mum_scanned": s.mum_scanned,
                    "impediments_found": s.impediments_found,
                    "tasks_created": s.tasks_created,
                    "tasks_skipped_dedup": s.tasks_skipped_dedup,
                    "dry_run": s.dry_run,
                })

            return ToolResult(
                success=True,
                data={
                    "sweeps": results,
                    "count": len(results),
                },
                message=f"{len(results)} sweep records found"
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Ops manager sub-sweep error: {e}\n{tb}")
            try:
                db.rollback()
            except Exception:
                pass
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")
        finally:
            if not shared_db:
                db.close()
# Ops Manager v2 - 1772579967
