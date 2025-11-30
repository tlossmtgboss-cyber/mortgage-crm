"""
AI Metrics Data Models
Defines the schema for tracking AI agent performance and quality metrics.
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel


class AIMetricType(str, Enum):
    """Types of metrics tracked"""
    # Agent Performance
    RESPONSE_TIME = "response_time"
    TOOL_EXECUTION = "tool_execution"
    NODE_ERROR = "node_error"
    USER_FEEDBACK = "user_feedback"

    # Business Metrics
    QUERY_TYPE = "query_type"
    TOOL_USAGE = "tool_usage"
    ACTION_EXECUTED = "action_executed"
    USER_ENGAGEMENT = "user_engagement"

    # AI Quality
    INTENT_CLASSIFICATION = "intent_classification"
    TOOL_SELECTION = "tool_selection"
    RESPONSE_QUALITY = "response_quality"
    FOLLOWUP_CLICK = "followup_click"


class FeedbackType(str, Enum):
    """User feedback types"""
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    ACCURATE = "accurate"
    INACCURATE = "inaccurate"


class AIMetricEvent(BaseModel):
    """Schema for a single metric event"""
    metric_type: AIMetricType
    user_id: int
    session_id: Optional[str] = None
    value: float  # Numeric value (time in ms, count, score 0-1, etc.)
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = None

    class Config:
        use_enum_values = True


class ResponseTimeMetric(BaseModel):
    """Response time breakdown by phase"""
    total_ms: float
    analyze_ms: Optional[float] = None
    gather_ms: Optional[float] = None
    reason_ms: Optional[float] = None
    execute_ms: Optional[float] = None
    respond_ms: Optional[float] = None
    query_type: Optional[str] = None
    tools_used: List[str] = []


class ToolExecutionMetric(BaseModel):
    """Tool execution tracking"""
    tool_name: str
    success: bool
    execution_time_ms: float
    error_message: Optional[str] = None
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None


class UserFeedbackMetric(BaseModel):
    """User feedback on AI response"""
    session_id: str
    message_id: Optional[str] = None
    feedback_type: FeedbackType
    rating: Optional[int] = None  # 1-5 star rating
    comment: Optional[str] = None
    query_type: Optional[str] = None


class IntentClassificationMetric(BaseModel):
    """Intent classification accuracy tracking"""
    detected_intent: str
    confidence: float
    user_confirmed: Optional[bool] = None  # If user indicated correct/incorrect
    actual_intent: Optional[str] = None  # If different from detected


class QueryAnalytics(BaseModel):
    """Aggregated query analytics"""
    total_queries: int
    queries_by_type: Dict[str, int]
    avg_response_time_ms: float
    tool_usage_counts: Dict[str, int]
    success_rate: float
    user_satisfaction_rate: Optional[float] = None
    period_start: datetime
    period_end: datetime


class AgentPerformanceMetrics(BaseModel):
    """Aggregated agent performance metrics"""
    avg_response_time_ms: float
    p50_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    tool_success_rate: float
    error_rate: float
    errors_by_node: Dict[str, int]
    thumbs_up_count: int
    thumbs_down_count: int
    satisfaction_rate: float
    period_start: datetime
    period_end: datetime


class BusinessMetrics(BaseModel):
    """Business-level metrics"""
    total_queries: int
    unique_users: int
    queries_per_user: float
    most_common_queries: List[Dict[str, Any]]
    tool_usage_ranking: List[Dict[str, Any]]
    actions_executed: int
    actions_by_type: Dict[str, int]
    engagement_metrics: Dict[str, Any]
    period_start: datetime
    period_end: datetime


class AIQualityMetrics(BaseModel):
    """AI quality metrics"""
    intent_accuracy: float
    intent_confidence_avg: float
    tool_selection_accuracy: float
    response_quality_avg: float
    followup_click_rate: float
    user_corrections_count: int
    period_start: datetime
    period_end: datetime
