"""
Operations Manager Agent — v3.0

Proactive, always-on agent that sweeps all three pipelines (Leads, Active Loans, MUM),
detects impediments, and creates corrective tasks automatically.

11 Tools:
1. run_pipeline_sweep - Full sweep of all 3 pipelines (orchestrator)
2. sweep_lead_pipeline - Detect stale leads, unassigned leads, no first contact
3. sweep_active_loans - Detect SLA breaches, expiring locks/docs, missing documents
4. sweep_mum_pipeline - Detect missed touchpoints, overdue MUM clients
5. detect_team_gaps - Find loans/leads missing LO, PA, processor, underwriter, closer
6. detect_stalled_files - Find files with zero activity past threshold
7. get_impediment_summary - Query open ops tasks by category
8. get_sweep_history - Query ops_sweep_results table
9. get_priority_queue - Bucketed priority queue (must_today/should_today/strategic)
10. check_loan_health - Single-loan health score with impediment list
11. evaluate_stage_transition - Stage transition gating per policy YAML
"""

import json
import traceback
import logging
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta, timezone
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
# YAML POLICY CONFIG LOADING (I5)
# ============================================================================

_POLICY_CONFIG = None
_POLICY_CONFIG_PATH = Path(__file__).parent / "ops_manager_policy_config.yaml"


def _get_policy_config():
    """Load and cache policy config YAML. Falls back to hardcoded defaults."""
    global _POLICY_CONFIG
    if _POLICY_CONFIG is not None:
        return _POLICY_CONFIG
    try:
        with open(_POLICY_CONFIG_PATH, 'r') as f:
            _POLICY_CONFIG = yaml.safe_load(f)
            logger.info(f"Policy config loaded: version {_POLICY_CONFIG.get('rule_version', 'unknown')}")
    except Exception as e:
        logger.warning(f"Failed to load policy config, using defaults: {e}")
        _POLICY_CONFIG = {}
    return _POLICY_CONFIG


# ============================================================================
# CONSTANTS (fallback defaults when YAML not available)
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

# Terminal lead stages — leads that have moved out of the active lead pipeline.
# "Withdrawn" and "Does Not Qualify" are now Active Loan terminal stages, not lead stages.
# Leads only exit to: Closed/Funded (MUM) or Do Not Call (suppressed).
TERMINAL_LEAD_STAGES = (
    "Closed", "Funded", "AMR", "Referral Source", "Do Not Call"
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

# Standardized ops task categories (stored in ai_tasks.category column) (I9)
OPS_CATEGORIES = {
    "SLA_BREACH": "SLA_BREACH",
    "LOCK_EXPIRING": "LOCK_EXPIRING",
    "DOC_EXPIRING": "DOC_EXPIRING",
    "DOC_MISSING": "DOC_MISSING",
    "COMPLIANCE_OPEN": "COMPLIANCE_OPEN",
    "LEAD_STALE": "LEAD_STALE",
    "LEAD_UNASSIGNED": "LEAD_UNASSIGNED",
    "TEAM_GAP": "TEAM_GAP",
    "MUM_OVERDUE": "MUM_OVERDUE",
    "STALLED": "STALLED",
}
ALL_OPS_CATEGORIES = tuple(OPS_CATEGORIES.values())


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
    category: Optional[str] = Field(None, description="Filter by category (SLA_BREACH, LOCK_EXPIRING, etc.)")


class SweepHistoryInput(BaseModel):
    organization_id: Optional[int] = Field(None, description="Organization ID")
    limit: int = Field(default=20, description="Number of recent sweeps to return")


class PriorityQueueInput(BaseModel):
    organization_id: Optional[int] = Field(None, description="Organization ID")
    assigned_to_id: Optional[int] = Field(None, description="Filter by assigned user ID")


class LoanHealthInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID to check health for")


class TransitionEvalInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID to evaluate")
    target_stage: str = Field(..., description="Target stage to transition to")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# Cache the resolved tasktype enum value so we only query it once per process
_RESOLVED_TASK_TYPE = None


def _get_task_type_value(db):
    """Resolve the correct tasktype enum value for 'Human Needed' / first available type.

    The PostgreSQL tasktype enum may store values differently from the Python enum
    (e.g. 'HUMAN_NEEDED' vs 'Human Needed'). This queries the actual DB enum values
    once and caches the result.
    """
    global _RESOLVED_TASK_TYPE
    if _RESOLVED_TASK_TYPE is not None:
        return _RESOLVED_TASK_TYPE

    from sqlalchemy import text
    try:
        rows = db.execute(text(
            "SELECT unnest(enum_range(NULL::tasktype)) as val"
        )).fetchall()
        enum_vals = [r[0] for r in rows]
        logger.info(f"Resolved tasktype enum values: {enum_vals}")

        # Prefer a value that looks like "Human Needed" or "HUMAN_NEEDED"
        for val in enum_vals:
            if val.lower().replace("_", " ") == "human needed":
                _RESOLVED_TASK_TYPE = val
                return val
        # Fallback: use first non-completed value
        for val in enum_vals:
            if "complete" not in val.lower():
                _RESOLVED_TASK_TYPE = val
                return val
        # Last resort: first value
        if enum_vals:
            _RESOLVED_TASK_TYPE = enum_vals[0]
            return enum_vals[0]
    except Exception as e:
        logger.warning(f"Could not resolve tasktype enum: {e}")

    return None


_RESOLVED_COMPLETED_TYPE = None


def _get_completed_type_value(db):
    """Resolve the correct tasktype enum value for 'Completed'.
    Caches result globally like _get_task_type_value().
    """
    global _RESOLVED_COMPLETED_TYPE
    if _RESOLVED_COMPLETED_TYPE is not None:
        return _RESOLVED_COMPLETED_TYPE

    from sqlalchemy import text
    try:
        rows = db.execute(text(
            "SELECT unnest(enum_range(NULL::tasktype)) as val"
        )).fetchall()
        for r in rows:
            if "complete" in r[0].lower():
                _RESOLVED_COMPLETED_TYPE = r[0]
                return r[0]
    except Exception:
        pass
    return None


def _dedup_and_create_task(db, title: str, description: str, priority: str,
                           loan_id=None, lead_id=None, owner_id=None,
                           organization_id=None, due_date=None,
                           category=None, borrower_name=None) -> bool:
    """Check for existing open task with same title in ai_tasks, create if not found.

    Writes to ai_tasks table (not tasks) so tasks appear in the frontend task list.
    Dynamically resolves the tasktype enum values to handle DB/Python mismatches.
    When category is provided, dedup also matches on category for more precise dedup (I9).
    Returns True if created.
    """
    from sqlalchemy import text

    # Dedup: check for existing non-completed task with same title
    # Cast type to text to avoid enum comparison issues
    conditions = ["title = :title", "type::text NOT ILIKE '%completed%'"]
    params = {"title": title}

    if loan_id:
        conditions.append("loan_id = :loan_id")
        params["loan_id"] = loan_id
    if lead_id:
        conditions.append("lead_id = :lead_id")
        params["lead_id"] = lead_id
    # Include category in dedup check when provided (I9) — more precise matching
    if category:
        conditions.append("category = :dedup_category")
        params["dedup_category"] = category

    where = " AND ".join(conditions)
    dedup_sql = "SELECT id FROM ai_tasks WHERE " + where + " LIMIT 1"
    existing = db.execute(text(dedup_sql), params).fetchone()

    if existing:
        return False

    # Resolve the actual DB enum value for the type column
    task_type = _get_task_type_value(db)

    insert_cols = ["title", "description", "priority", "created_at"]
    insert_vals = [":title", ":description", ":priority", "NOW()"]
    insert_params = {"title": title, "description": description, "priority": priority}

    if task_type:
        insert_cols.append("type")
        insert_vals.append("CAST(:task_type AS tasktype)")
        insert_params["task_type"] = task_type

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
    insert_sql = "INSERT INTO ai_tasks (" + cols_sql + ") VALUES (" + vals_sql + ")"
    db.execute(text(insert_sql), insert_params)
    return True


# ============================================================================
# PRIORITY SCORING (I5 / S12)
# ============================================================================

def _compute_priority_score(category, priority_str, loan_data=None):
    """Compute weighted priority score per policy config."""
    config = _get_policy_config()
    scoring = config.get("priority_scoring", {})

    severity_weights = scoring.get("severity_weights", {"Critical": 100, "Warning": 50, "Info": 10})
    time_pressure = scoring.get("time_pressure", {})
    type_urgency = scoring.get("type_urgency", {})

    # Map priority string to severity
    severity = "Critical" if priority_str == "high" else "Warning"
    score = severity_weights.get(severity, 50)

    # Add type urgency
    category_type_map = {
        "COMPLIANCE_OPEN": "Compliance",
        "LOCK_EXPIRING": "LockRisk",
        "SLA_BREACH": "SLA",
        "TEAM_GAP": "Staffing",
        "DOC_MISSING": "DataIntegrity",
        "DOC_EXPIRING": "DataIntegrity",
    }
    mapped_type = category_type_map.get(category, "")
    score += type_urgency.get(mapped_type, 0)

    # Add time pressure if loan data provided
    if loan_data:
        if loan_data.get("is_overdue"):
            score += time_pressure.get("overdue", 80)
        if loan_data.get("closing_within_3d"):
            score += time_pressure.get("closing_within_3d", 40)
        if loan_data.get("lock_within_3d"):
            score += time_pressure.get("lock_within_3d", 30)

    return score


def _get_priority_bucket(score):
    """Get bucket name from score."""
    config = _get_policy_config()
    thresholds = config.get("priority_scoring", {}).get("bucket_thresholds", {})
    must_today = thresholds.get("MustToday", 140)
    should_today = thresholds.get("ShouldToday", 80)
    if score >= must_today:
        return "must_today"
    elif score >= should_today:
        return "should_today"
    return "strategic"


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
        """Register all 11 ops manager tools"""

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

        # Tool 9: Priority queue (S12)
        self.register_tool(AgentTool(
            name="get_priority_queue",
            description="Get bucketed priority queue (must_today / should_today / strategic) for open ops tasks",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_priority_queue,
            input_schema=PriorityQueueInput
        ))

        # Tool 10: Loan health check (S13)
        self.register_tool(AgentTool(
            name="check_loan_health",
            description="Compute single-loan health score (0-100) with impediment list",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._check_loan_health,
            input_schema=LoanHealthInput
        ))

        # Tool 11: Stage transition gating (S11)
        self.register_tool(AgentTool(
            name="evaluate_stage_transition",
            description="Evaluate whether a loan can transition to a target stage per policy rules",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._evaluate_stage_transition,
            input_schema=TransitionEvalInput
        ))

    # ========================================================================
    # AUTO-RESOLVE STALE TASKS (I7)
    # ========================================================================

    def _resolve_stale_ops_tasks(self, db, org_id):
        """Auto-resolve ops tasks whose impediments no longer exist.

        Checks each open ops task to see if the underlying condition has been cleared,
        and marks resolved ones as completed with completed_action='auto_resolved'.
        Called at the START of _run_pipeline_sweep before sub-sweeps.
        """
        from sqlalchemy import text

        completed_type = _get_completed_type_value(db)
        if not completed_type:
            logger.warning("Cannot auto-resolve: completed task type not found")
            return 0

        org_filter = "AND t.organization_id = :org_id" if org_id else ""
        params = {}
        if org_id:
            params["org_id"] = org_id

        cats_placeholder = ", ".join(f"'{c}'" for c in ALL_OPS_CATEGORIES)

        # Fetch all open ops tasks
        open_tasks_sql = (
            "SELECT t.id, t.category, t.loan_id, t.lead_id, t.created_at, t.title"
            " FROM ai_tasks t"
            " WHERE t.type::text NOT ILIKE '%completed%'"
            " AND t.category IN (" + cats_placeholder + ")"
            " " + org_filter +
            " ORDER BY t.created_at ASC"
            " LIMIT 500"
        )
        open_tasks = db.execute(text(open_tasks_sql), params).fetchall()

        resolved_count = 0

        for task in open_tasks:
            should_resolve = False
            try:
                cat = task.category
                loan_id = task.loan_id
                lead_id = task.lead_id
                task_created = task.created_at

                if cat == OPS_CATEGORIES["LOCK_EXPIRING"] and loan_id:
                    # Resolve if lock_expiration_date > NOW() + 5 days OR loan in terminal stage
                    row = db.execute(text("""
                        SELECT stage, lock_expiration_date FROM loans WHERE id = :lid
                    """), {"lid": loan_id}).fetchone()
                    if row:
                        if row.stage in TERMINAL_STAGES:
                            should_resolve = True
                        elif row.lock_expiration_date and row.lock_expiration_date > datetime.now(timezone.utc) + timedelta(days=5):
                            should_resolve = True

                elif cat == OPS_CATEGORIES["SLA_BREACH"] and loan_id:
                    # Resolve if loan has moved to a different stage since task creation
                    row = db.execute(text("""
                        SELECT stage, stage_changed_at FROM loans WHERE id = :lid
                    """), {"lid": loan_id}).fetchone()
                    if row:
                        if row.stage in TERMINAL_STAGES:
                            should_resolve = True
                        elif row.stage_changed_at and task_created and row.stage_changed_at > task_created:
                            should_resolve = True

                elif cat == OPS_CATEGORIES["STALLED"] and loan_id:
                    # Resolve if there is activity newer than task.created_at
                    row = db.execute(text("""
                        SELECT MAX(a.created_at) as last_activity FROM activities a WHERE a.loan_id = :lid
                    """), {"lid": loan_id}).fetchone()
                    if row and row.last_activity and task_created and row.last_activity > task_created:
                        should_resolve = True
                    # Also resolve if loan moved to terminal
                    loan_row = db.execute(text("SELECT stage FROM loans WHERE id = :lid"), {"lid": loan_id}).fetchone()
                    if loan_row and loan_row.stage in TERMINAL_STAGES:
                        should_resolve = True

                elif cat in (OPS_CATEGORIES["LEAD_STALE"], OPS_CATEGORIES["LEAD_UNASSIGNED"]) and lead_id:
                    # Resolve if lead now has owner or recent contact
                    row = db.execute(text("""
                        SELECT owner_id, last_contact, stage FROM leads WHERE id = :lid
                    """), {"lid": lead_id}).fetchone()
                    if row:
                        if row.stage in TERMINAL_LEAD_STAGES:
                            should_resolve = True
                        elif cat == OPS_CATEGORIES["LEAD_UNASSIGNED"] and row.owner_id is not None:
                            should_resolve = True
                        elif cat == OPS_CATEGORIES["LEAD_STALE"] and row.last_contact and task_created and row.last_contact > task_created:
                            should_resolve = True

                elif cat == OPS_CATEGORIES["MUM_OVERDUE"] and loan_id:
                    # Resolve if there is activity on loan since task creation
                    row = db.execute(text("""
                        SELECT MAX(a.created_at) as last_activity FROM activities a WHERE a.loan_id = :lid
                    """), {"lid": loan_id}).fetchone()
                    if row and row.last_activity and task_created and row.last_activity > task_created:
                        should_resolve = True

                if should_resolve:
                    db.execute(text("""
                        UPDATE ai_tasks
                        SET type = CAST(:completed_type AS tasktype),
                            completed_at = NOW(),
                            completed_action = 'auto_resolved'
                        WHERE id = :task_id
                    """), {"completed_type": completed_type, "task_id": task.id})
                    resolved_count += 1

            except Exception as e:
                logger.debug(f"Auto-resolve check failed for task {task.id}: {e}")
                continue

        if resolved_count > 0:
            try:
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
            logger.info(f"Auto-resolved {resolved_count} stale ops tasks")

        return resolved_count

    # ========================================================================
    # TOOL 1: FULL PIPELINE SWEEP (orchestrator)
    # ========================================================================

    async def _run_pipeline_sweep(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Orchestrate a full sweep of all 3 pipelines using a single DB session"""
        from database import SessionLocal
        from sqlalchemy import text

        org_id = input_data.get("organization_id")
        dry_run = input_data.get("dry_run", False)
        started_at = datetime.now(timezone.utc)

        # Use route's DB session if available, otherwise create one
        existing_db = context.get("_shared_db") if context else None
        db = existing_db or SessionLocal()
        shared_context = dict(context) if context else {}
        shared_context["_shared_db"] = db

        try:
            # Auto-resolve stale tasks before running new sweeps (I7)
            auto_resolved = 0
            if not dry_run:
                try:
                    db.begin_nested()
                    auto_resolved = self._resolve_stale_ops_tasks(db, org_id)
                except Exception as ar_err:
                    logger.warning(f"Auto-resolve failed, continuing sweep: {ar_err}")
                    try:
                        db.rollback()
                    except Exception:
                        pass

            # Run each sub-sweep with savepoints so one failure doesn't abort the whole sweep
            sub_sweeps = [
                ("leads", self._sweep_lead_pipeline,
                 {"organization_id": org_id, "stale_days": 7, "dry_run": dry_run}),
                ("loans", self._sweep_active_loans,
                 {"organization_id": org_id, "lock_warning_days": 5, "doc_warning_days": 14, "dry_run": dry_run}),
                ("mum", self._sweep_mum_pipeline,
                 {"organization_id": org_id, "overdue_days": 90, "dry_run": dry_run}),
                ("team_gaps", self._detect_team_gaps,
                 {"organization_id": org_id, "dry_run": dry_run}),
                ("stalled_files", self._detect_stalled_files,
                 {"organization_id": org_id, "stalled_days": 14, "dry_run": dry_run}),
            ]

            sub_results = {}
            for name, handler, sweep_params in sub_sweeps:
                try:
                    db.begin_nested()  # Savepoint: isolates this sub-sweep
                    result = await handler(sweep_params, shared_context)
                    # Sub-sweep's own db.commit() releases the savepoint on success
                    sub_results[name] = result
                except Exception as sub_err:
                    logger.warning(f"Sub-sweep '{name}' failed, rolling back savepoint: {sub_err}")
                    try:
                        db.rollback()  # Rolls back to savepoint, not entire transaction
                    except Exception:
                        pass
                    sub_results[name] = ToolResult(success=False, error=str(sub_err))

            lead_result = sub_results.get("leads", ToolResult(success=False, error="skipped"))
            loan_result = sub_results.get("loans", ToolResult(success=False, error="skipped"))
            mum_result = sub_results.get("mum", ToolResult(success=False, error="skipped"))
            team_result = sub_results.get("team_gaps", ToolResult(success=False, error="skipped"))
            stalled_result = sub_results.get("stalled_files", ToolResult(success=False, error="skipped"))

            completed_at = datetime.now(timezone.utc)
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

            # Send in-app notifications for high-priority tasks created (S13 notifications)
            if not dry_run:
                try:
                    self._send_high_priority_notifications(db, org_id, lead_data, loan_data, mum_data, team_data, stalled_data)
                except Exception as notif_err:
                    logger.warning(f"Failed to send notifications: {notif_err}")
                    try:
                        db.rollback()
                    except Exception:
                        pass

            # Record sweep result (table created by migrations/create_ops_sweep_results.py)
            try:
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
                    "auto_resolved": auto_resolved,
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
                message=f"Sweep complete: {total_impediments} impediments, {total_tasks_created} tasks created, {total_skipped} deduped, {auto_resolved} auto-resolved ({round(duration, 1)}s)"
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            if not existing_db:
                db.close()

    # ========================================================================
    # NOTIFICATIONS HELPER (S13)
    # ========================================================================

    def _send_high_priority_notifications(self, db, org_id, lead_data, loan_data, mum_data, team_data, stalled_data):
        """Send in-app AND push notifications for high-priority impediments created during sweep.

        In-app notifications go to the notifications table (existing behavior).
        Push notifications go to APNs/FCM via AgentNotificationService (new behavior).
        Push delivery is fire-and-forget: failures are logged but never block the sweep.
        """
        from sqlalchemy import text

        # Collect all high-priority impediments that were newly created
        all_impediments = []
        for sub_data in [lead_data, loan_data, mum_data, team_data, stalled_data]:
            for imp in sub_data.get("impediments", []):
                if imp.get("priority") == "high":
                    all_impediments.append(imp)

        if not all_impediments:
            return

        # Get tasks that were just created (within last 5 minutes, high priority, ops categories)
        cats_placeholder = ", ".join(f"'{c}'" for c in ALL_OPS_CATEGORIES)
        org_filter = "AND t.organization_id = :org_id" if org_id else ""
        params = {}
        if org_id:
            params["org_id"] = org_id

        recent_tasks_sql = (
            "SELECT t.id, t.title, t.assigned_to_id, t.organization_id, t.loan_id, t.lead_id, t.category"
            " FROM ai_tasks t"
            " WHERE t.priority = 'high'"
            " AND t.category IN (" + cats_placeholder + ")"
            " AND t.created_at >= NOW() - INTERVAL '5 minutes'"
            " AND t.assigned_to_id IS NOT NULL"
            " AND t.type::text NOT ILIKE '%completed%'"
            " " + org_filter +
            " ORDER BY t.created_at DESC"
            " LIMIT 50"
        )
        recent_tasks = db.execute(text(recent_tasks_sql), params).fetchall()

        # --- In-app notifications (existing behavior) ---
        for task in recent_tasks:
            try:
                db.execute(text("""
                    INSERT INTO notifications (user_id, organization_id, type, title, message, link, is_read, created_at)
                    VALUES (:user_id, :org_id, 'ops_impediment', :title, :message, :link, false, NOW())
                """), {
                    "user_id": task.assigned_to_id,
                    "org_id": task.organization_id,
                    "title": f"Action Required: {task.category or 'Ops Task'}",
                    "message": task.title[:255] if task.title else "New high-priority ops task requires attention",
                    "link": f"/tasks?task_id={task.id}",
                })
            except Exception as e:
                logger.debug(f"Failed to create in-app notification for task {task.id}: {e}")
                continue

        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

        # --- Push notifications (new: send to mobile devices) ---
        try:
            from services.agent_notification_service import get_agent_notification_service
            push_service = get_agent_notification_service()

            push_sent = 0
            push_skipped = 0
            for task in recent_tasks:
                try:
                    category = task.category or "OPS_TASK"
                    task_title = task.title or "High-priority ops task requires attention"

                    # Use category-specific push methods when possible
                    if category == OPS_CATEGORIES["SLA_BREACH"] and task.loan_id:
                        result = push_service.notify_task_created(
                            db=db,
                            user_id=task.assigned_to_id,
                            task_title=task_title[:200],
                            task_priority="high",
                            task_id=task.id,
                            loan_id=task.loan_id,
                        )
                    elif category == OPS_CATEGORIES["LOCK_EXPIRING"] and task.loan_id:
                        result = push_service.notify_task_created(
                            db=db,
                            user_id=task.assigned_to_id,
                            task_title=task_title[:200],
                            task_priority="high",
                            task_id=task.id,
                            loan_id=task.loan_id,
                        )
                    elif category in (OPS_CATEGORIES["DOC_EXPIRING"], OPS_CATEGORIES["DOC_MISSING"]) and task.loan_id:
                        result = push_service.notify_task_created(
                            db=db,
                            user_id=task.assigned_to_id,
                            task_title=task_title[:200],
                            task_priority="high",
                            task_id=task.id,
                            loan_id=task.loan_id,
                        )
                    elif category == OPS_CATEGORIES["COMPLIANCE_OPEN"] and task.loan_id:
                        result = push_service.notify_task_created(
                            db=db,
                            user_id=task.assigned_to_id,
                            task_title=task_title[:200],
                            task_priority="high",
                            task_id=task.id,
                            loan_id=task.loan_id,
                        )
                    else:
                        # Generic push for other categories (TEAM_GAP, STALLED, etc.)
                        result = push_service.notify_task_created(
                            db=db,
                            user_id=task.assigned_to_id,
                            task_title=task_title[:200],
                            task_priority="high",
                            task_id=task.id,
                            loan_id=task.loan_id,
                        )

                    if result.get("sent", 0) > 0:
                        push_sent += 1
                    else:
                        push_skipped += 1

                except Exception as e:
                    logger.debug(f"Push notification failed for task {task.id}: {e}")
                    push_skipped += 1
                    continue

            if push_sent > 0 or push_skipped > 0:
                logger.info(
                    "Sweep push notifications: %d sent, %d skipped (of %d tasks)",
                    push_sent, push_skipped, len(recent_tasks),
                )

        except Exception as e:
            logger.warning(f"Push notification batch failed (non-blocking): {e}")

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
            stale_sql = (
                "SELECT l.id, l.first_name, l.last_name, l.owner_id, l.organization_id,"
                " l.last_contact,"
                " EXTRACT(EPOCH FROM (NOW() - COALESCE(l.last_contact, l.created_at))) / 86400 AS days_no_contact"
                " FROM leads l"
                " WHERE l.stage NOT IN ('Closed', 'Funded', 'Withdrawn', 'Does Not Qualify', 'Do Not Call')"
                " AND COALESCE(l.last_contact, l.created_at) < NOW() - (CAST(:stale_days AS INTEGER) * INTERVAL '1 day')"
                " " + org_filter +
                " ORDER BY days_no_contact DESC"
                " LIMIT :limit"
            )
            stale_leads = db.execute(text(stale_sql), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

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
                        organization_id=lead.organization_id,
                        category=OPS_CATEGORIES["LEAD_STALE"])
                    if created:
                        tasks_created += 1
                    else:
                        tasks_skipped += 1

            # --- LEAD_UNASSIGNED: unassigned leads ---
            unassigned_sql = (
                "SELECT l.id, l.first_name, l.last_name, l.organization_id, l.created_at"
                " FROM leads l"
                " WHERE l.owner_id IS NULL"
                " AND l.stage NOT IN ('Closed', 'Funded', 'Withdrawn', 'Does Not Qualify', 'Do Not Call')"
                " " + org_filter +
                " ORDER BY l.created_at ASC"
                " LIMIT :limit"
            )
            unassigned = db.execute(text(unassigned_sql), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

            by_category["LEAD_UNASSIGNED"] = len(unassigned)
            for lead in unassigned:
                name = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or "Unknown"
                title = f"[ASSIGN] Unassigned lead needs LO: {name}"
                impediments.append({"category": "LEAD_UNASSIGNED", "title": title, "priority": "high"})

                if not dry_run:
                    created = _dedup_and_create_task(
                        db, title=title,
                        description=f"Lead '{name}' has no assigned loan officer. Created: {lead.created_at}.",
                        priority="high", lead_id=lead.id, organization_id=lead.organization_id,
                        category=OPS_CATEGORIES["LEAD_UNASSIGNED"])
                    if created:
                        tasks_created += 1
                    else:
                        tasks_skipped += 1

            if not dry_run:
                db.commit()

            lead_count_sql = (
                "SELECT COUNT(*) as cnt FROM leads l"
                " WHERE l.stage NOT IN ('Closed', 'Funded', 'Withdrawn', 'Does Not Qualify', 'Do Not Call')"
                " " + org_filter
            )
            scanned_row = db.execute(text(lead_count_sql), params).fetchone()
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
            params = {"lock_days": lock_days, "doc_days": doc_days}
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
            sla_sql = (
                "SELECT l.id, l.loan_number, l.borrower_name, l.stage,"
                " l.loan_officer_id, l.organization_id,"
                " EXTRACT(EPOCH FROM (NOW() - l.stage_changed_at)) / 86400 AS days_in_stage,"
                " CASE l.stage " + sla_cases + " ELSE 10 END AS sla_target"
                " FROM loans l"
                " WHERE l.stage NOT IN (" + terminal_list + ")"
                " AND l.stage_changed_at IS NOT NULL"
                " AND EXTRACT(EPOCH FROM (NOW() - l.stage_changed_at)) / 86400 >"
                " CASE l.stage " + sla_cases + " ELSE 10 END"
                " " + org_filter +
                " ORDER BY days_in_stage DESC"
                " LIMIT :limit"
            )
            sla_loans = db.execute(text(sla_sql), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

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
                        organization_id=loan.organization_id,
                        category=OPS_CATEGORIES["SLA_BREACH"])
                    tasks_created += 1 if created else 0
                    tasks_skipped += 0 if created else 1

            # --- LOCK_EXPIRING: rate locks expiring soon ---
            lock_sql = (
                "SELECT l.id, l.loan_number, l.borrower_name, l.lock_expiration_date,"
                " l.loan_officer_id, l.organization_id,"
                " EXTRACT(EPOCH FROM (l.lock_expiration_date - NOW())) / 86400 AS days_until_expiry"
                " FROM loans l"
                " WHERE l.stage NOT IN (" + terminal_list + ")"
                " AND l.lock_expiration_date IS NOT NULL"
                " AND l.lock_expiration_date <= NOW() + (CAST(:lock_days AS INTEGER) * INTERVAL '1 day')"
                " AND l.lock_expiration_date > NOW() - INTERVAL '30 days'"
                " " + org_filter +
                " ORDER BY l.lock_expiration_date ASC"
                " LIMIT :limit"
            )
            lock_loans = db.execute(text(lock_sql), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

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
                        due_date=loan.lock_expiration_date,
                        category=OPS_CATEGORIES["LOCK_EXPIRING"])
                    tasks_created += 1 if created else 0
                    tasks_skipped += 0 if created else 1

            # --- DOC_EXPIRING: credit or appraisal docs expiring ---
            doc_sql = (
                "SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id, l.organization_id,"
                " l.credit_docs_expire_date, l.appraisal_docs_expire_date"
                " FROM loans l"
                " WHERE l.stage NOT IN (" + terminal_list + ")"
                " AND ("
                " (l.credit_docs_expire_date IS NOT NULL AND l.credit_docs_expire_date <= NOW() + (CAST(:doc_days AS INTEGER) * INTERVAL '1 day'))"
                " OR (l.appraisal_docs_expire_date IS NOT NULL AND l.appraisal_docs_expire_date <= NOW() + (CAST(:doc_days AS INTEGER) * INTERVAL '1 day'))"
                " )"
                " " + org_filter +
                " LIMIT :limit"
            )
            doc_loans = db.execute(text(doc_sql), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

            docs_count = 0
            for loan in doc_loans:
                for doc_type, col in [("Credit docs", loan.credit_docs_expire_date),
                                      ("Appraisal docs", loan.appraisal_docs_expire_date)]:
                    if col and col <= datetime.now(timezone.utc) + timedelta(days=doc_days):
                        exp_date = col.strftime("%m/%d/%Y") if hasattr(col, 'strftime') else str(col)
                        title = f"[DOCS] {doc_type} expiring {exp_date}: {loan.borrower_name or 'Unknown'} ({loan.loan_number or ''})"
                        impediments.append({"category": "DOC_EXPIRING", "title": title, "priority": "high"})
                        docs_count += 1
                        if not dry_run:
                            created = _dedup_and_create_task(
                                db, title=title,
                                description=f"{doc_type} expire on {exp_date}. Renewal needed.",
                                priority="high", loan_id=loan.id, owner_id=loan.loan_officer_id,
                                organization_id=loan.organization_id, due_date=col,
                                category=OPS_CATEGORIES["DOC_EXPIRING"])
                            tasks_created += 1 if created else 0
                            tasks_skipped += 0 if created else 1
            by_category["DOC_EXPIRING"] = docs_count

            # --- COMPLIANCE_OPEN: critical/high compliance alerts ---
            try:
                compliance_sql = (
                    "SELECT ca.id, ca.title as alert_title, ca.severity, ca.loan_id,"
                    " l.loan_number, l.borrower_name, l.loan_officer_id, l.organization_id"
                    " FROM compliance_alerts ca"
                    " JOIN loans l ON l.id = ca.loan_id"
                    " WHERE ca.status = 'open'"
                    " AND ca.severity IN ('critical', 'high')"
                    " AND l.stage NOT IN (" + terminal_list + ")"
                    " " + org_filter +
                    " ORDER BY CASE ca.severity WHEN 'critical' THEN 1 ELSE 2 END"
                    " LIMIT :limit"
                )
                compliance_alerts = db.execute(text(compliance_sql), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

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
                            organization_id=alert.organization_id,
                            category=OPS_CATEGORIES["COMPLIANCE_OPEN"])
                        tasks_created += 1 if created else 0
                        tasks_skipped += 0 if created else 1
            except Exception as e:
                logger.warning(f"COMPLIANCE_OPEN check skipped (table may not exist): {e}")
                try:
                    db.rollback()
                except Exception:
                    pass
                by_category["COMPLIANCE_OPEN"] = 0

            # --- DOC_MISSING: loans past PROCESSING with <3 active documents ---
            try:
                missing_doc_sql = (
                    "SELECT l.id, l.loan_number, l.borrower_name, l.stage,"
                    " l.loan_officer_id, l.organization_id,"
                    " COUNT(d.id) FILTER (WHERE d.status = 'active') as active_doc_count"
                    " FROM loans l"
                    " LEFT JOIN documents d ON d.loan_id = l.id"
                    " WHERE l.stage NOT IN (" + terminal_list + ", 'APPLICATION', 'DISCLOSED')"
                    " " + org_filter +
                    " GROUP BY l.id, l.loan_number, l.borrower_name, l.stage, l.loan_officer_id, l.organization_id"
                    " HAVING COUNT(d.id) FILTER (WHERE d.status = 'active') < 3"
                    " LIMIT :limit"
                )
                missing_doc_loans = db.execute(text(missing_doc_sql), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

                by_category["DOC_MISSING"] = len(missing_doc_loans)
                for loan in missing_doc_loans:
                    title = f"[DOCS] Missing documents ({loan.active_doc_count} on file): {loan.borrower_name or 'Unknown'} ({loan.loan_number or ''})"
                    impediments.append({"category": "DOC_MISSING", "title": title, "priority": "medium"})
                    if not dry_run:
                        created = _dedup_and_create_task(
                            db, title=title,
                            description=f"Loan in {loan.stage} has only {loan.active_doc_count} active documents. Minimum 3 expected.",
                            priority="medium", loan_id=loan.id, owner_id=loan.loan_officer_id,
                            organization_id=loan.organization_id,
                            category=OPS_CATEGORIES["DOC_MISSING"])
                        tasks_created += 1 if created else 0
                        tasks_skipped += 0 if created else 1
            except Exception as e:
                logger.warning(f"DOC_MISSING check skipped (table may not exist): {e}")
                try:
                    db.rollback()
                except Exception:
                    pass
                by_category["DOC_MISSING"] = 0

            if not dry_run:
                db.commit()

            # --- Push notifications for critical loan sweep findings ---
            # Fire-and-forget: failures never block the sweep result
            if not dry_run and tasks_created > 0:
                try:
                    from services.agent_notification_service import get_agent_notification_service
                    push_svc = get_agent_notification_service()

                    # SLA breaches: push to each affected LO
                    for loan in sla_loans:
                        if loan.loan_officer_id:
                            try:
                                days = int(loan.days_in_stage)
                                push_svc.notify_stale_loan(
                                    db=db,
                                    loan_id=loan.id,
                                    days_stale=days,
                                    stage=loan.stage,
                                    borrower_name=loan.borrower_name or "",
                                    loan_number=loan.loan_number or "",
                                )
                            except Exception:
                                pass

                    # Lock expirations: push to each affected LO
                    for loan in lock_loans:
                        if loan.loan_officer_id:
                            try:
                                days_left = int(loan.days_until_expiry) if loan.days_until_expiry and loan.days_until_expiry > 0 else 0
                                push_svc.notify_lock_expiring(
                                    db=db,
                                    loan_id=loan.id,
                                    days_until_expiry=days_left,
                                    borrower_name=loan.borrower_name or "",
                                    loan_number=loan.loan_number or "",
                                )
                            except Exception:
                                pass

                    # Doc expirations: push to each affected LO
                    for loan in doc_loans:
                        if loan.loan_officer_id:
                            for doc_type_label, col in [("Credit docs", loan.credit_docs_expire_date),
                                                        ("Appraisal docs", loan.appraisal_docs_expire_date)]:
                                if col and col <= datetime.now(timezone.utc) + timedelta(days=doc_days):
                                    try:
                                        exp_str = col.strftime("%m/%d/%Y") if hasattr(col, 'strftime') else str(col)
                                        push_svc.notify_doc_expiring(
                                            db=db,
                                            loan_id=loan.id,
                                            doc_type=doc_type_label,
                                            expire_date=exp_str,
                                            borrower_name=loan.borrower_name or "",
                                            loan_number=loan.loan_number or "",
                                        )
                                    except Exception:
                                        pass

                except Exception as push_err:
                    logger.debug(f"Loan sweep push notifications failed (non-blocking): {push_err}")

            loan_count_sql = (
                "SELECT COUNT(*) as cnt FROM loans l"
                " WHERE l.stage NOT IN (" + terminal_list + ") " + org_filter
            )
            scanned_row = db.execute(text(loan_count_sql), params).fetchone()
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
    # TOOL 4: MUM PIPELINE SWEEP (C2: LEFT JOIN LATERAL)
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
            # C2: Replaced correlated subqueries with LEFT JOIN LATERAL
            mum_sql = (
                "SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,"
                " l.loan_officer_id, l.organization_id, l.funded_date,"
                " COALESCE(la.last_activity, l.funded_date) as last_activity,"
                " EXTRACT(EPOCH FROM (NOW() - COALESCE(la.last_activity, l.funded_date))) / 86400 AS days_since_contact"
                " FROM loans l"
                " LEFT JOIN LATERAL ("
                " SELECT MAX(a.created_at) as last_activity FROM activities a WHERE a.loan_id = l.id"
                " ) la ON true"
                " WHERE l.stage = 'FUNDED'"
                " AND l.funded_date IS NOT NULL"
                " AND COALESCE(la.last_activity, l.funded_date) < NOW() - (CAST(:overdue_days AS INTEGER) * INTERVAL '1 day')"
                " " + org_filter +
                " ORDER BY days_since_contact DESC"
                " LIMIT :limit"
            )
            mum_clients = db.execute(text(mum_sql), {**params, "overdue_days": overdue_days, "limit": IMPEDIMENT_LIMIT}).fetchall()

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
                        category=OPS_CATEGORIES["MUM_OVERDUE"], borrower_name=name)
                    tasks_created += 1 if created else 0
                    tasks_skipped += 0 if created else 1

            if not dry_run:
                db.commit()

            mum_count_sql = (
                "SELECT COUNT(*) as cnt FROM loans l"
                " WHERE l.stage = 'FUNDED' AND l.funded_date IS NOT NULL " + org_filter
            )
            scanned_row = db.execute(text(mum_count_sql), params).fetchone()
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
            no_lo_sql = (
                "SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.organization_id"
                " FROM loans l"
                " WHERE l.loan_officer_id IS NULL"
                " AND l.stage NOT IN (" + terminal_list + ")"
                " " + org_filter +
                " LIMIT :limit"
            )
            no_lo = db.execute(text(no_lo_sql), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()

            by_category["LOAN_MISSING_LO"] = len(no_lo)
            for loan in no_lo:
                title = f"[ASSIGN] Loan needs LO: {loan.borrower_name or 'Unknown'} ({loan.loan_number or ''})"
                impediments.append({"category": "TEAM_GAP", "title": title, "priority": "high"})
                if not dry_run:
                    created = _dedup_and_create_task(
                        db, title=title,
                        description=f"Active loan in {loan.stage} has no assigned loan officer.",
                        priority="high", loan_id=loan.id, organization_id=loan.organization_id,
                        category=OPS_CATEGORIES["TEAM_GAP"])
                    tasks_created += 1 if created else 0
                    tasks_skipped += 0 if created else 1

            # --- LOAN_TEAM_GAPS: missing processor/closer/PA based on stage ---
            for role, required_stages in ROLE_STAGE_REQUIREMENTS.items():
                stages_list = ", ".join(f"'{s}'" for s in required_stages)
                # Columns are plain String (name), not FK _id columns
                col_name = role  # processor, closer, production_assistant

                try:
                    gaps_sql = (
                        "SELECT l.id, l.loan_number, l.borrower_name, l.stage,"
                        " l.loan_officer_id, l.organization_id"
                        " FROM loans l"
                        " WHERE l.stage IN (" + stages_list + ")"
                        " AND (l." + col_name + " IS NULL OR TRIM(l." + col_name + ") = '')"
                        " AND l.stage NOT IN (" + terminal_list + ")"
                        " " + org_filter +
                        " LIMIT :limit"
                    )
                    gaps = db.execute(text(gaps_sql), {**params, "limit": IMPEDIMENT_LIMIT}).fetchall()
                except Exception:
                    # Column may not exist — skip this role
                    gaps = []

                role_label = role.replace("_", " ").title()
                gap_key = f"LOAN_TEAM_GAPS_{role.upper()}"
                by_category[gap_key] = len(gaps)

                for loan in gaps:
                    title = f"[TEAM] Missing {role_label}: {loan.borrower_name or 'Unknown'} ({loan.loan_number or ''})"
                    priority = "high" if role == "processor" else "medium"
                    impediments.append({"category": "TEAM_GAP", "title": title, "priority": priority})
                    if not dry_run:
                        created = _dedup_and_create_task(
                            db, title=title,
                            description=f"Loan in {loan.stage} is missing a {role_label}.",
                            priority=priority, loan_id=loan.id, owner_id=loan.loan_officer_id,
                            organization_id=loan.organization_id,
                            category=OPS_CATEGORIES["TEAM_GAP"])
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
    # TOOL 6: STALLED FILES DETECTION (C2: LEFT JOIN LATERAL)
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

            # C2: Replaced correlated subqueries with LEFT JOIN LATERAL
            stalled_sql = (
                "SELECT l.id, l.loan_number, l.borrower_name, l.stage,"
                " l.loan_officer_id, l.organization_id,"
                " COALESCE(la.last_activity, l.stage_changed_at, l.created_at) as last_activity,"
                " EXTRACT(EPOCH FROM (NOW() - COALESCE(la.last_activity, l.stage_changed_at, l.created_at))) / 86400 AS days_stalled"
                " FROM loans l"
                " LEFT JOIN LATERAL ("
                " SELECT MAX(a.created_at) as last_activity FROM activities a WHERE a.loan_id = l.id"
                " ) la ON true"
                " WHERE l.stage NOT IN (" + terminal_list + ")"
                " AND COALESCE(la.last_activity, l.stage_changed_at, l.created_at) < NOW() - (CAST(:stalled_days AS INTEGER) * INTERVAL '1 day')"
                " " + org_filter +
                " ORDER BY days_stalled DESC"
                " LIMIT :limit"
            )
            stalled = db.execute(text(stalled_sql), {**params, "stalled_days": stalled_days, "limit": IMPEDIMENT_LIMIT}).fetchall()

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
                        organization_id=loan.organization_id,
                        category=OPS_CATEGORIES["STALLED"])
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
    # TOOL 7: IMPEDIMENT SUMMARY (I9: category column)
    # ========================================================================

    async def _get_impediment_summary(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Query open ops tasks grouped by category column (I9)"""
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

            # Build category filter
            category_filter = ""
            if category:
                category_filter = "AND t.category = :cat_filter"
                params["cat_filter"] = category.upper()

            # Use the standardized category column (I9) instead of LIKE-based title parsing
            cats_placeholder = ", ".join(f"'{c}'" for c in ALL_OPS_CATEGORIES)

            summary_sql = (
                "SELECT category, priority, COUNT(*) as count"
                " FROM ai_tasks t"
                " WHERE t.type::text NOT ILIKE '%completed%'"
                " AND t.category IN (" + cats_placeholder + ")"
                " " + category_filter +
                " " + org_filter +
                " GROUP BY category, t.priority"
                " ORDER BY category, t.priority"
            )
            summary = db.execute(text(summary_sql), params).fetchall()

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

            sweeps_sql = (
                "SELECT id, organization_id, sweep_type, started_at, completed_at,"
                " duration_seconds, leads_scanned, loans_scanned, mum_scanned,"
                " impediments_found, tasks_created, tasks_skipped_dedup,"
                " impediment_breakdown, dry_run"
                " FROM ops_sweep_results"
                " " + org_filter +
                " ORDER BY started_at DESC"
                " LIMIT :limit"
            )
            sweeps = db.execute(text(sweeps_sql), params).fetchall()

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

    # ========================================================================
    # TOOL 9: PRIORITY QUEUE (S12)
    # ========================================================================

    async def _get_priority_queue(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get bucketed priority queue for open ops tasks"""
        from sqlalchemy import text

        org_id = input_data.get("organization_id")
        assigned_to_id = input_data.get("assigned_to_id")

        shared_db = context.get("_shared_db") if context else None
        if shared_db:
            db = shared_db
        else:
            from database import SessionLocal
            db = SessionLocal()
        try:
            cats_placeholder = ", ".join(f"'{c}'" for c in ALL_OPS_CATEGORIES)
            org_filter = "AND t.organization_id = :org_id" if org_id else ""
            user_filter = "AND t.assigned_to_id = :assigned_to_id" if assigned_to_id else ""
            params = {}
            if org_id:
                params["org_id"] = org_id
            if assigned_to_id:
                params["assigned_to_id"] = assigned_to_id

            priority_queue_sql = (
                "SELECT t.id, t.title, t.category, t.priority, t.loan_id, t.lead_id,"
                " t.assigned_to_id, t.organization_id, t.created_at, t.due_date,"
                " t.borrower_name,"
                " l.closing_date, l.lock_expiration_date, l.stage as loan_stage,"
                " l.loan_number"
                " FROM ai_tasks t"
                " LEFT JOIN loans l ON l.id = t.loan_id"
                " WHERE t.type::text NOT ILIKE '%completed%'"
                " AND t.category IN (" + cats_placeholder + ")"
                " " + org_filter +
                " " + user_filter +
                " ORDER BY t.created_at ASC"
                " LIMIT 200"
            )
            tasks = db.execute(text(priority_queue_sql), params).fetchall()

            buckets = {"must_today": [], "should_today": [], "strategic": []}

            for task in tasks:
                # Build loan_data context for scoring
                loan_data = {}
                if task.due_date and task.due_date < datetime.now(timezone.utc):
                    loan_data["is_overdue"] = True
                if task.closing_date:
                    days_to_close = (task.closing_date - datetime.now(timezone.utc)).total_seconds() / 86400
                    if 0 < days_to_close <= 3:
                        loan_data["closing_within_3d"] = True
                if task.lock_expiration_date:
                    days_to_lock = (task.lock_expiration_date - datetime.now(timezone.utc)).total_seconds() / 86400
                    if 0 < days_to_lock <= 3:
                        loan_data["lock_within_3d"] = True

                score = _compute_priority_score(task.category or "", task.priority or "medium", loan_data)
                bucket = _get_priority_bucket(score)

                task_dict = {
                    "task_id": task.id,
                    "title": task.title,
                    "category": task.category,
                    "priority": task.priority,
                    "priority_score": score,
                    "bucket": bucket,
                    "loan_id": task.loan_id,
                    "loan_number": task.loan_number,
                    "lead_id": task.lead_id,
                    "assigned_to_id": task.assigned_to_id,
                    "borrower_name": task.borrower_name,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                }
                buckets[bucket].append(task_dict)

            # Sort each bucket by score descending
            for bucket_name in buckets:
                buckets[bucket_name].sort(key=lambda x: x["priority_score"], reverse=True)

            total = sum(len(b) for b in buckets.values())

            return ToolResult(
                success=True,
                data={
                    "total": total,
                    "must_today": buckets["must_today"],
                    "must_today_count": len(buckets["must_today"]),
                    "should_today": buckets["should_today"],
                    "should_today_count": len(buckets["should_today"]),
                    "strategic": buckets["strategic"],
                    "strategic_count": len(buckets["strategic"]),
                },
                message=f"Priority queue: {len(buckets['must_today'])} must-today, {len(buckets['should_today'])} should-today, {len(buckets['strategic'])} strategic"
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Priority queue error: {e}\n{tb}")
            try:
                db.rollback()
            except Exception:
                pass
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")
        finally:
            if not shared_db:
                db.close()

    # ========================================================================
    # TOOL 10: LOAN HEALTH CHECK (S13)
    # ========================================================================

    async def _check_loan_health(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Compute single-loan health score (0-100) with impediment list"""
        from sqlalchemy import text

        loan_id = input_data.get("loan_id")
        if not loan_id:
            return ToolResult(success=False, error="loan_id is required")

        shared_db = context.get("_shared_db") if context else None
        if shared_db:
            db = shared_db
        else:
            from database import SessionLocal
            db = SessionLocal()
        try:
            # Fetch loan with all relevant fields
            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.stage,
                       l.loan_officer_id, l.organization_id,
                       l.stage_changed_at, l.lock_expiration_date, l.closing_date,
                       l.processor, l.closer, l.production_assistant,
                       l.loan_officer_name,
                       CONCAT(u.first_name, ' ', u.last_name) as lo_name
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Start at 100, deduct for issues
            health_score = 100
            impediments = []

            # 1. Days in stage vs SLA target
            if loan.stage_changed_at and loan.stage not in TERMINAL_STAGES:
                days_in_stage = (datetime.now(timezone.utc) - loan.stage_changed_at).total_seconds() / 86400
                sla_target = STAGE_SLA_DAYS.get(loan.stage, 10)
                if days_in_stage > sla_target:
                    over_by = days_in_stage - sla_target
                    deduction = min(30, int(over_by * 3))  # Up to 30 points
                    health_score -= deduction
                    impediments.append({
                        "type": "SLA_BREACH",
                        "severity": "high" if over_by > sla_target else "medium",
                        "message": f"In {loan.stage} for {int(days_in_stage)}d (SLA: {sla_target}d, over by {int(over_by)}d)",
                        "deduction": deduction,
                    })

            # 2. Role assignments
            if not loan.loan_officer_id:
                health_score -= 20
                impediments.append({
                    "type": "MISSING_ROLE",
                    "severity": "high",
                    "message": "No loan officer assigned",
                    "deduction": 20,
                })

            if loan.stage in ROLE_STAGE_REQUIREMENTS.get("processor", []):
                if not loan.processor or (isinstance(loan.processor, str) and not loan.processor.strip()):
                    health_score -= 15
                    impediments.append({
                        "type": "MISSING_ROLE",
                        "severity": "high",
                        "message": "No processor assigned (required for this stage)",
                        "deduction": 15,
                    })

            if loan.stage in ROLE_STAGE_REQUIREMENTS.get("closer", []):
                if not loan.closer or (isinstance(loan.closer, str) and not loan.closer.strip()):
                    health_score -= 10
                    impediments.append({
                        "type": "MISSING_ROLE",
                        "severity": "medium",
                        "message": "No closer assigned (required for this stage)",
                        "deduction": 10,
                    })

            if loan.stage in ROLE_STAGE_REQUIREMENTS.get("production_assistant", []):
                if not loan.production_assistant or (isinstance(loan.production_assistant, str) and not loan.production_assistant.strip()):
                    health_score -= 5
                    impediments.append({
                        "type": "MISSING_ROLE",
                        "severity": "low",
                        "message": "No production assistant assigned",
                        "deduction": 5,
                    })

            # 3. Active document count
            try:
                doc_row = db.execute(text("""
                    SELECT COUNT(*) as cnt FROM documents
                    WHERE loan_id = :loan_id AND status = 'active'
                """), {"loan_id": loan_id}).fetchone()
                doc_count = doc_row.cnt if doc_row else 0
                if loan.stage not in ("APPLICATION", "DISCLOSED") + TERMINAL_STAGES and doc_count < 3:
                    deduction = min(15, (3 - doc_count) * 5)
                    health_score -= deduction
                    impediments.append({
                        "type": "DOC_MISSING",
                        "severity": "medium",
                        "message": f"Only {doc_count} active documents on file (minimum 3 expected)",
                        "deduction": deduction,
                    })
            except Exception:
                doc_count = -1  # Unknown

            # 4. Lock expiration risk
            if loan.lock_expiration_date and loan.stage not in TERMINAL_STAGES:
                days_to_lock = (loan.lock_expiration_date - datetime.now(timezone.utc)).total_seconds() / 86400
                if days_to_lock < 0:
                    health_score -= 20
                    impediments.append({
                        "type": "LOCK_EXPIRED",
                        "severity": "high",
                        "message": f"Rate lock expired {int(abs(days_to_lock))} days ago",
                        "deduction": 20,
                    })
                elif days_to_lock <= 3:
                    health_score -= 10
                    impediments.append({
                        "type": "LOCK_EXPIRING",
                        "severity": "high",
                        "message": f"Rate lock expires in {int(days_to_lock)} days",
                        "deduction": 10,
                    })

            # 5. Open compliance alerts
            try:
                alert_row = db.execute(text("""
                    SELECT COUNT(*) as cnt FROM compliance_alerts
                    WHERE loan_id = :loan_id AND status = 'open' AND severity IN ('critical', 'high')
                """), {"loan_id": loan_id}).fetchone()
                alert_count = alert_row.cnt if alert_row else 0
                if alert_count > 0:
                    deduction = min(20, alert_count * 10)
                    health_score -= deduction
                    impediments.append({
                        "type": "COMPLIANCE_OPEN",
                        "severity": "high",
                        "message": f"{alert_count} open critical/high compliance alert(s)",
                        "deduction": deduction,
                    })
            except Exception:
                alert_count = -1  # Unknown (table may not exist)

            # Clamp score
            health_score = max(0, min(100, health_score))

            # Determine grade
            if health_score >= 90:
                grade = "A"
            elif health_score >= 75:
                grade = "B"
            elif health_score >= 50:
                grade = "C"
            elif health_score >= 25:
                grade = "D"
            else:
                grade = "F"

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_name": loan.borrower_name,
                    "stage": loan.stage,
                    "health_score": health_score,
                    "grade": grade,
                    "impediment_count": len(impediments),
                    "impediments": impediments,
                    "role_assignments": {
                        "loan_officer": loan.lo_name or loan.loan_officer_name or None,
                        "processor": loan.processor or None,
                        "closer": loan.closer or None,
                        "production_assistant": loan.production_assistant or None,
                    },
                },
                message=f"Health score: {health_score}/100 (Grade {grade}) — {len(impediments)} issue(s)"
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Loan health check error: {e}\n{tb}")
            try:
                db.rollback()
            except Exception:
                pass
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")
        finally:
            if not shared_db:
                db.close()

    # ========================================================================
    # TOOL 11: STAGE TRANSITION GATING (S11)
    # ========================================================================

    async def _evaluate_stage_transition(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Evaluate whether a loan can transition to a target stage per policy YAML"""
        from sqlalchemy import text

        loan_id = input_data.get("loan_id")
        target_stage = input_data.get("target_stage")

        if not loan_id or not target_stage:
            return ToolResult(success=False, error="loan_id and target_stage are required")

        shared_db = context.get("_shared_db") if context else None
        if shared_db:
            db = shared_db
        else:
            from database import SessionLocal
            db = SessionLocal()
        try:
            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.stage,
                       l.loan_officer_id, l.processor, l.closer, l.production_assistant
                FROM loans l
                WHERE l.id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            current_stage = loan.stage
            config = _get_policy_config()
            transitions = config.get("stage_transitions", [])

            # Find matching transition rule
            matching_rule = None
            for rule in transitions:
                if rule.get("from") == current_stage and rule.get("to") == target_stage:
                    matching_rule = rule
                    break

            if not matching_rule:
                # No explicit rule — check if target is a terminal state (always allowed)
                if target_stage in ("Withdrawn", "Denied", "Cancelled", "Dead"):
                    return ToolResult(
                        success=True,
                        data={
                            "loan_id": loan_id,
                            "current_stage": current_stage,
                            "target_stage": target_stage,
                            "allowed": True,
                            "hard_block": False,
                            "reasons": [],
                            "warnings": ["Terminal transition — no prerequisites required"],
                        },
                        message=f"Transition {current_stage} -> {target_stage}: ALLOWED (terminal)"
                    )
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "current_stage": current_stage,
                        "target_stage": target_stage,
                        "allowed": False,
                        "hard_block": True,
                        "reasons": [f"No transition rule defined for {current_stage} -> {target_stage}"],
                        "warnings": [],
                    },
                    message=f"Transition {current_stage} -> {target_stage}: BLOCKED (no rule)"
                )

            if not matching_rule.get("allowed", True):
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "current_stage": current_stage,
                        "target_stage": target_stage,
                        "allowed": False,
                        "hard_block": True,
                        "reasons": ["Transition explicitly disallowed by policy"],
                        "warnings": [],
                    },
                    message=f"Transition {current_stage} -> {target_stage}: BLOCKED (disallowed)"
                )

            hard_block = matching_rule.get("hard_block", True)
            reasons = []
            warnings = []

            # Check required_roles
            required_roles = matching_rule.get("required_roles", [])
            # Map policy role names to loan columns
            role_column_map = {
                "LO": ("loan_officer_id", loan.loan_officer_id),
                "PA": ("production_assistant", loan.production_assistant),
                "Processor": ("processor", loan.processor),
                "Closer": ("closer", loan.closer),
                "UW": ("processor", loan.processor),  # UW check uses processor as proxy
                "PostCloseReviewer": ("processor", loan.processor),  # proxy
            }
            for role in required_roles:
                col_name, col_val = role_column_map.get(role, (None, None))
                if col_name is None:
                    warnings.append(f"Unknown role '{role}' in policy — cannot validate")
                    continue
                if col_val is None or (isinstance(col_val, str) and not col_val.strip()):
                    reasons.append(f"Required role '{role}' is not assigned")

            # Check required_milestones (query compliance_alerts or milestones if available)
            required_milestones = matching_rule.get("required_milestones", [])
            for milestone in required_milestones:
                # Check if a completed milestone of this type exists
                # We check ai_tasks with category matching the milestone as a proxy
                try:
                    milestone_check = db.execute(text("""
                        SELECT id FROM ai_tasks
                        WHERE loan_id = :loan_id
                            AND title ILIKE :milestone_pattern
                            AND type::text ILIKE '%completed%'
                        LIMIT 1
                    """), {"loan_id": loan_id, "milestone_pattern": f"%{milestone}%"}).fetchone()
                    if not milestone_check:
                        reasons.append(f"Required milestone '{milestone}' not completed")
                except Exception:
                    warnings.append(f"Could not verify milestone '{milestone}' — table query failed")

            # Check disallow_if_open_exception_types
            blocking_types = matching_rule.get("disallow_if_open_exception_types", [])
            for exc_type in blocking_types:
                try:
                    # Check compliance_alerts for open alerts of this type
                    open_alert = db.execute(text("""
                        SELECT id, title FROM compliance_alerts
                        WHERE loan_id = :loan_id AND status = 'open'
                            AND (alert_type ILIKE :exc_type OR severity ILIKE :exc_type)
                        LIMIT 1
                    """), {"loan_id": loan_id, "exc_type": f"%{exc_type}%"}).fetchone()
                    if open_alert:
                        reasons.append(f"Open '{exc_type}' exception blocks transition: {open_alert.title}")
                except Exception:
                    warnings.append(f"Could not verify '{exc_type}' exceptions — table query failed")

            allowed = len(reasons) == 0

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "current_stage": current_stage,
                    "target_stage": target_stage,
                    "allowed": allowed,
                    "hard_block": hard_block and not allowed,
                    "reasons": reasons,
                    "warnings": warnings,
                    "rule_id": matching_rule.get("id"),
                },
                message=f"Transition {current_stage} -> {target_stage}: {'ALLOWED' if allowed else 'BLOCKED'} ({len(reasons)} issue(s))"
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Stage transition eval error: {e}\n{tb}")
            try:
                db.rollback()
            except Exception:
                pass
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")
        finally:
            if not shared_db:
                db.close()
