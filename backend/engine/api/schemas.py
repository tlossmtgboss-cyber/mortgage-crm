"""Pydantic v2 request/response models for CIE endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

class WebhookResponse(BaseModel):
    status: str = "accepted"
    call_record_id: Optional[UUID] = None
    message: str = "Queued for processing"


# ---------------------------------------------------------------------------
# Report responses
# ---------------------------------------------------------------------------

class ScoreDetail(BaseModel):
    name: str
    score: float
    evidence: str = ""


class ComplianceFlag(BaseModel):
    type: str
    severity: str
    message: str
    state: Optional[str] = None
    keywords: Optional[list[str]] = None
    terms: Optional[list[str]] = None


class CoachingSuggestion(BaseModel):
    area: str
    suggestion: str
    example: str = ""


class Objection(BaseModel):
    objection: str
    lo_response: str = ""
    effectiveness: str = ""


class GeneratedTask(BaseModel):
    title: str
    owner: str = "lo"
    priority: str = "medium"
    due_days: int = 3


class DraftMessage(BaseModel):
    channel: str = "sms"
    recipient: str = "borrower"
    body: str = ""


class Opportunity(BaseModel):
    label: str
    description: str = ""
    priority: str = "medium"


class Risk(BaseModel):
    label: str
    description: str = ""
    severity: str = "medium"


class ReportResponse(BaseModel):
    id: UUID
    call_record_id: UUID

    cis_composite: Optional[float] = None
    engagement_score: Optional[float] = None
    information_quality_score: Optional[float] = None
    objection_handling_score: Optional[float] = None
    compliance_score: Optional[float] = None
    rapport_score: Optional[float] = None
    closing_effectiveness_score: Optional[float] = None

    primary_intent: Optional[str] = None
    intent_confidence: Optional[float] = None

    conversion_probability: Optional[float] = None
    conversion_ci_low: Optional[float] = None
    conversion_ci_high: Optional[float] = None

    summary: Optional[str] = None
    summary_bullets: Optional[list[str]] = None
    opportunities: Optional[list[dict[str, Any]]] = None
    risks: Optional[list[dict[str, Any]]] = None
    objections: Optional[list[dict[str, Any]]] = None
    compliance_flags: Optional[list[dict[str, Any]]] = None
    coaching_suggestions: Optional[list[dict[str, Any]]] = None
    generated_tasks: Optional[list[dict[str, Any]]] = None
    draft_messages: Optional[list[dict[str, Any]]] = None

    llm_model_used: Optional[str] = None
    pipeline_version: Optional[str] = None
    processing_time_ms: Optional[int] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CallRecordBrief(BaseModel):
    id: UUID
    external_call_id: str
    provider: str
    direction: str
    started_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    processing_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReportListItem(BaseModel):
    call: CallRecordBrief
    report: Optional[ReportResponse] = None


class ReportListResponse(BaseModel):
    items: list[ReportListItem]
    total: int


class StatsResponse(BaseModel):
    total_calls: int
    analyzed: int
    pending: int
    failed: int
    avg_cis: Optional[float] = None
    avg_conversion: Optional[float] = None
