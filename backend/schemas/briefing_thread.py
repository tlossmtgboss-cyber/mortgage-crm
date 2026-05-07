"""Pydantic schemas for the interactive briefing thread system."""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


# --- Reply Parsing (Claude structured output) ---

class BulkAction(BaseModel):
    type: str = Field(description="'handle_all' or 'handle_except'")
    except_items: list[int] = Field(default_factory=list)


class ItemOverride(BaseModel):
    item_number: int
    new_action_type: Optional[str] = None
    instruction_delta: str = ""
    requires_validation: list[str] = Field(default_factory=list)


class ParsedReply(BaseModel):
    handled_items: list[int] = Field(default_factory=list)
    skipped_items: list[int] = Field(default_factory=list)
    overrides: list[ItemOverride] = Field(default_factory=list)
    bulk_action: Optional[BulkAction] = None
    free_text_instructions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_clarification: bool = False
    clarification_question: Optional[str] = None


# --- Approval Classification ---

class ApprovalIntent(str, Enum):
    APPROVE = "approve"
    APPROVE_ALL = "approve_all"
    APPROVE_SPECIFIC = "approve_specific"
    APPROVE_EXCEPT = "approve_except"
    MODIFY = "modify"
    CANCEL = "cancel"


class ClassifiedApproval(BaseModel):
    intent: ApprovalIntent
    task_numbers: list[int] = Field(default_factory=list)
    modification_text: Optional[str] = None


# --- Thread States ---

VALID_STATES = {
    "BRIEFING_SENT", "AWAITING_REPLY", "PARSING_INSTRUCTIONS",
    "CONFIRMATION_SENT", "AWAITING_APPROVAL", "EXECUTING",
    "RESULTS_SENT", "EXPIRED", "CANCELLED", "FAILED",
    "MANUAL_REVIEW", "CLARIFICATION_SENT",
}

TERMINAL_STATES = {"RESULTS_SENT", "EXPIRED", "CANCELLED", "FAILED", "MANUAL_REVIEW"}

VALID_TRANSITIONS = {
    "BRIEFING_SENT": {"AWAITING_REPLY"},
    "AWAITING_REPLY": {"PARSING_INSTRUCTIONS", "EXPIRED"},
    "PARSING_INSTRUCTIONS": {"CONFIRMATION_SENT", "CLARIFICATION_SENT", "MANUAL_REVIEW"},
    "CONFIRMATION_SENT": {"AWAITING_APPROVAL"},
    "AWAITING_APPROVAL": {"EXECUTING", "CONFIRMATION_SENT", "CANCELLED", "EXPIRED"},
    "CLARIFICATION_SENT": {"AWAITING_REPLY"},
    "EXECUTING": {"RESULTS_SENT", "FAILED"},
}


# --- Supported Action Types ---

SUPPORTED_ACTION_TYPES = {
    "send_borrower_email", "send_realtor_update", "create_crm_task",
    "schedule_call", "assign_processor_task", "request_docs",
    "update_pipeline_stage", "send_checklist",
}

ACTION_TOOL_MAP = {
    "send_borrower_email": "send_email",
    "send_realtor_update": "send_email",
    "create_crm_task": "create_task",
    "schedule_call": "book_appointment",
    "assign_processor_task": "assign_task",
    "request_docs": "track_document_request",
    "update_pipeline_stage": "update_loan_fields",
    "send_checklist": "send_email",
}

HIGH_RISK_ACTIONS = {"update_pipeline_stage"}


# --- API Response Schemas ---

class BriefingTaskResponse(BaseModel):
    id: int
    briefing_item_number: int
    briefing_item_summary: Optional[str] = None
    action_type: str
    tool_name: Optional[str] = None
    confidence_score: Optional[float] = None
    risk_level: Optional[str] = None
    status: str
    result_data: Optional[dict] = None
    error_message: Optional[str] = None
    executed_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class BriefingThreadResponse(BaseModel):
    id: int
    thread_token: str
    state: str
    trust_mode: int
    loop_count: int
    briefing_items: Optional[list] = None
    extracted_tasks: Optional[list] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    tasks: list[BriefingTaskResponse] = Field(default_factory=list)
    model_config = {"from_attributes": True}
