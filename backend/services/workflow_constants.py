"""
Workflow Constants — Single Source of Truth

All workflow stage mappings, SLA targets, terminal stages, escalation chains,
and stage ordering constants live here. Every service that needs these values
should import from this module instead of defining its own copy.

Consolidation note (2026-03-31): Prior to this file, the following constants
were duplicated across 7+ service files with minor drift between them.
Discrepancies found and resolved:
  - lead_cascade_service.py defined TERMINAL_LOAN_STAGES with only 4 values
    (missing WITHDRAWN, DOES_NOT_QUALIFY). Updated to import the full 6-value
    canonical set.
  - morning_briefing_service.py SLA_TARGETS used flat stage keys with 10 entries
    including CTC/CONDITIONAL_APPROVAL aliases. The canonical SLA_TARGETS uses
    the transition format ("APPLICATION_to_DISCLOSED") with 7 entries matching
    real SLA date field pairs. A flat STAGE_SLA_DAYS lookup is derived from it.
  - pipeline_probability_service.py and proactive_deal_alerts_service.py used
    lowercase keys and fewer entries. These class-level constants are replaced
    with imports from the canonical set.
"""

from typing import Dict, Optional


# =============================================================================
# TERMINAL STAGES
# =============================================================================

# Loan stages that represent a closed/terminal state.
# Excluded from active pipeline queries, workflow enrollment, SLA tracking, etc.
TERMINAL_LOAN_STAGES = (
    "FUNDED",
    "CANCELLED",
    "DENIED",
    "DEAD",
    "WITHDRAWN",
    "DOES_NOT_QUALIFY",
)

# Convenience set for O(1) membership tests
TERMINAL_LOAN_STAGES_SET = frozenset(TERMINAL_LOAN_STAGES)


# =============================================================================
# SLA TARGETS — Stage Transition Durations
# =============================================================================

# SLA targets in days for stage-to-stage transitions.
# Keys use the format "FROM_to_TO" matching real SLA date field pairs on the Loan model.
SLA_TARGETS = {
    "APPLICATION_to_DISCLOSED": 3,
    "DISCLOSED_to_SUBMITTED": 7,
    "SUBMITTED_to_UW_RECEIVED": 2,
    "UW_RECEIVED_to_APPROVED": 5,
    "APPROVED_to_CLEAR_TO_CLOSE": 3,
    "CLEAR_TO_CLOSE_to_DOCS_OUT": 3,
    "DOCS_OUT_to_FUNDED": 5,
}

# Flat lookup: stage name -> max days allowed in that stage.
# Derived from SLA_TARGETS by extracting the "from" stage of each transition,
# then augmented with alias/intermediate stages that share the same SLA window.
STAGE_SLA_DAYS: Dict[str, int] = {}
for _key, _days in SLA_TARGETS.items():
    _from_stage = _key.split("_to_")[0]
    STAGE_SLA_DAYS[_from_stage] = _days

# Alias/intermediate stages that share another stage's SLA window.
# These were previously defined in morning_briefing_service.py but missing
# from the canonical SLA_TARGETS transitions.
STAGE_SLA_DAYS.setdefault("UNDERWRITING", STAGE_SLA_DAYS.get("UW_RECEIVED", 5))
STAGE_SLA_DAYS.setdefault("CONDITIONAL_APPROVAL", STAGE_SLA_DAYS.get("APPROVED", 3))
STAGE_SLA_DAYS.setdefault("CTC", STAGE_SLA_DAYS.get("CLEAR_TO_CLOSE", 3))
STAGE_SLA_DAYS.setdefault("PROCESSING", STAGE_SLA_DAYS.get("DISCLOSED", 7))
STAGE_SLA_DAYS.setdefault("CLOSING", STAGE_SLA_DAYS.get("DOCS_OUT", 5))


# =============================================================================
# STAGE ORDER — Ordinal Pipeline Position
# =============================================================================

# Ordinal position of each LoanStage in the pipeline.
# Higher = further along. Terminal/special states are negative.
STAGE_ORDER: Dict[str, int] = {
    "APPLICATION": 10,
    "DISCLOSED": 15,
    "PROCESSING": 20,
    "SUBMITTED": 30,
    "UNDERWRITING": 40,
    "UW_RECEIVED": 45,
    "CONDITIONAL_APPROVAL": 50,
    "APPROVED": 60,
    "CTC": 70,
    "CLEAR_TO_CLOSE": 70,
    "CLOSING": 80,
    "DOCS": 85,
    "DOCS_OUT": 85,
    "FUNDED": 100,
    # Terminal / special states
    "CANCELLED": -10,
    "DENIED": -20,
    "DEAD": -30,
    "WITHDRAWN": -40,
    "DOES_NOT_QUALIFY": -50,
    "SUSPENDED": -5,
    "NURTURE": -1,
}

FUNDED_STAGES = {"FUNDED"}
PAUSE_STAGES = {"SUSPENDED"}
ARCHIVE_STAGES = {"CANCELLED", "WITHDRAWN", "DENIED", "DEAD", "DOES_NOT_QUALIFY"}
COMPLIANCE_TRIGGER_STAGES = {"DENIED"}

# Stages that are "active" in the pipeline (positive ordinal, not yet funded)
ACTIVE_LOAN_STAGES = frozenset(
    stage for stage, order in STAGE_ORDER.items()
    if order > 0 and stage not in FUNDED_STAGES
)


# =============================================================================
# STAGE TO DATE FIELD — Maps CRM stage to the Loan model date column
# =============================================================================

STAGE_TO_DATE_FIELD: Dict[str, Optional[str]] = {
    "APPLICATION": "application_date",
    "DISCLOSED": "initial_disclosures_sent_date",
    "PROCESSING": "file_received_date",
    "SUBMITTED": "uw_received_date",
    "UNDERWRITING": "uw_received_date",
    "UW_RECEIVED": "uw_received_date",
    "CONDITIONAL_APPROVAL": "conditional_approval_date",
    "APPROVED": "loan_approved_date",
    "CTC": "clear_to_close_date",
    "CLEAR_TO_CLOSE": "clear_to_close_date",
    "CLOSING": "scheduled_closing_date",
    "DOCS_OUT": "docs_out_date",
    "FUNDED": "funded_date",
    "SUSPENDED": "suspended_date",
    "WITHDRAWN": "withdrawn_date",
    "CANCELLED": None,
    "DENIED": None,
    "DEAD": None,
    "DOES_NOT_QUALIFY": None,
    "NURTURE": None,
}


# =============================================================================
# LEAD STATUS -> WORKFLOW MAPPING
# =============================================================================

# Maps lead stage values (LeadStage enum, as strings) to workflow keys.
# Used by WorkflowScheduler to auto-enroll leads into the correct workflow.
# WF-009: All lead stages now mapped — unmapped stages use None to skip.
LEAD_STATUS_WORKFLOW_MAP = {
    "New": "prospect",
    "Attempted Contact": "prospect",
    "Prospect": "prospect",
    "Application": "prequal",
    "Pre-Qualified": "prequal",
    "Pre-Approved": "pre_approved",
    "Does Not Qualify": "credit_repair",
    "Credit Repair": "credit_repair",
    "Long-Term Nurture": "nurture",
    "Document Fulfillment": "prequal",  # Needs docs = prequal workflow
}

# Lead stages that should be explicitly skipped (no workflow enrollment).
# These are terminal, loan-level, informational, or compliance-restricted.
LEAD_SKIP_STAGES = frozenset({
    "Under Contract",    # Loan-level stage — leads shouldn't be here
    "Closed",            # Terminal
    "Disclosed",         # Loan-level stage
    "Funded",            # Terminal
    "AMR",               # Annual mortgage review — no automation needed
    "Referral Source",   # Informational only
    "Do Not Call",       # Compliance — must NOT trigger outreach
})


# =============================================================================
# LOAN STAGE -> WORKFLOW MAPPING
# =============================================================================

# Maps loan stage values (LoanStage enum, UPPERCASE) to workflow keys.
# Used by WorkflowScheduler to auto-enroll loans into the correct workflow.
# WF-010: All loan stages now mapped — unmapped stages use None to skip.
LOAN_STAGE_WORKFLOW_MAP = {
    "DISCLOSED": "under_contract",
    "PROCESSING": "under_contract",
    "SUBMITTED": "under_contract",
    "UW_RECEIVED": "under_contract",          # WF-010: was missing
    "UNDERWRITING": "under_contract",
    "CONDITIONAL_APPROVAL": "under_contract",  # WF-010: was missing
    "APPROVED": "under_contract",               # WF-010: was missing
    "CTC": "last_mile",
    "CLEAR_TO_CLOSE": "last_mile",
    "CLOSING": "last_mile",                     # WF-010: was missing
    "DOCS": "last_mile",                        # WF-010: was missing
    "DOCS_OUT": "last_mile",
    "FUNDED": "post_close",
}

# Loan stages that should be explicitly skipped (no new workflow enrollment).
LOAN_SKIP_STAGES = frozenset({
    "SUSPENDED",          # Paused — don't generate new tasks
    "CANCELLED",          # Terminal
    "DENIED",             # Terminal
    "DEAD",               # Terminal
    "WITHDRAWN",          # Terminal
    "DOES_NOT_QUALIFY",   # Terminal
    "NURTURE",            # Long-term nurture, not active pipeline
})


# =============================================================================
# ESCALATION CHAIN
# =============================================================================

# SLA-002: Multi-level escalation chain (SLA-008: uses business hours).
# Level -> {hours_overdue threshold (business hours), target recipient, action}
# Business hours = Mon-Fri 8AM-6PM (10h/day).
# Level 1 = 8 biz hours (1 day), Level 2 = 16 biz hours (2 days), Level 3 = 24 biz hours (3 days)
ESCALATION_CHAIN = {
    1: {"hours_overdue": 8, "target": "assignee", "action": "notify"},
    2: {"hours_overdue": 16, "target": "manager", "action": "notify_and_reassign"},
    3: {"hours_overdue": 24, "target": "branch_manager", "action": "notify_and_flag"},
}


# =============================================================================
# TASK TYPE ROUTING
# =============================================================================

# Maps task communication types to their routing destination.
TASK_TYPE_ROUTES = {
    "phone": "task_list",
    "phone_am": "task_list",
    "phone_pm": "task_list",
    "text": "sms_automation",
    "text_am": "sms_automation",
    "text_pm": "sms_automation",
    "email": "email_automation",
    "referral_partner": "task_list",
    "dialer": "dialer_queue",
    "manual": "task_list",
}

# Task types eligible for AI autonomous execution.
AI_ELIGIBLE_TASK_TYPES = frozenset({"email", "text", "text_am", "text_pm"})


# =============================================================================
# STAGE PROBABILITY WEIGHTS
# =============================================================================

# Stage progression weights for pipeline probability scoring.
# Higher = closer to closing. Used by PipelineProbabilityService.
STAGE_PROBABILITY_WEIGHTS = {
    "lead": 0.05,
    "application": 0.15,
    "processing": 0.30,
    "submitted": 0.45,
    "underwriting": 0.55,
    "conditional_approval": 0.70,
    "approved": 0.80,
    "clear_to_close": 0.90,
    "docs_out": 0.95,
    "docs_back": 0.98,
}
