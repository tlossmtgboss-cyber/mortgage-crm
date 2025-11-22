"""
Pydantic models for AI Task Automation system
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID


# Request Models

class AIAuthorizationCreate(BaseModel):
    workflow_id: str
    task_type_name: str


class TrainingFeedback(BaseModel):
    text: Optional[str] = None
    structured: Optional[Dict[str, Any]] = None


class TrainingReview(BaseModel):
    action: str  # 'approved' or 'rejected'
    feedback: Optional[TrainingFeedback] = None


class RevokeAuthorization(BaseModel):
    retain_training_data: bool = True


class RollbackRequest(BaseModel):
    state_id: str


class DelegateToAI(BaseModel):
    enable_learning: bool = False


# Response Models

class AIRecommendation(BaseModel):
    recommended_action: str
    steps: List[str]
    data_to_use: Dict[str, Any]
    reasoning: str


class AuthorizationResponse(BaseModel):
    authorization_id: str
    user_id: str
    workflow_id: str
    task_type_name: str
    authorization_status: str
    training_progress_count: int
    confidence_threshold: float
    date_authorized: Optional[datetime] = None
    date_training_completed: Optional[datetime] = None
    tasks_completed_count: Optional[int] = 0
    success_rate: Optional[float] = None
    avg_confidence: Optional[float] = None
    last_activity: Optional[datetime] = None


class AuditLogEntry(BaseModel):
    log_id: str
    user_id: str
    task_instance_id: Optional[str] = None
    authorization_id: Optional[str] = None
    action_type: str
    action_details: Optional[Dict[str, Any]] = None
    result_status: Optional[str] = None
    error_message: Optional[str] = None
    confidence_score: Optional[float] = None
    execution_time_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    estimated_cost: Optional[float] = None
    timestamp: datetime
    task_title: Optional[str] = None
    task_type_name: Optional[str] = None


class CostSummary(BaseModel):
    total_tasks: int
    total_cost: float
    avg_cost_per_task: float
    total_tokens: int


class CostBreakdown(BaseModel):
    task_type_name: Optional[str] = None
    task_count: int
    total_cost: float
    avg_cost: float


class CostTrend(BaseModel):
    period_year: int
    period_month: int
    tasks: int
    cost: float


class PerformanceOverall(BaseModel):
    total_tasks: int
    success_rate: float
    avg_confidence: float
    time_saved_hours: float
    error_rate: float


class PerformanceByTaskType(BaseModel):
    task_type_name: str
    completed: int
    success_rate: float
    avg_confidence: float


class DailyTrend(BaseModel):
    date: str
    tasks: int
    avg_confidence: float


class RollbackState(BaseModel):
    state_id: str
    created_at: datetime
    snapshot_reason: str
    tasks_completed_count: int
    performance_metrics: Optional[Dict[str, Any]] = None


class TaskDelegationResponse(BaseModel):
    task_id: str
    ai_status: str
    message: str
    training_progress: Optional[str] = None
    ai_recommendation: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    authorization_required: bool = False
    workflow_id: Optional[str] = None
    task_type_name: Optional[str] = None
