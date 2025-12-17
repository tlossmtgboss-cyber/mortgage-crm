"""
Pydantic schemas for Agent API endpoints
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class ConversationStage(str, Enum):
    """Available conversation stages"""
    INITIAL_CONTACT = "initial_contact"
    QUALIFICATION = "qualification"
    OBJECTION_HANDLING = "objection_handling"
    BOOKING = "booking"
    FOLLOW_UP = "follow_up"
    EMAIL_ANALYSIS = "email_analysis"
    DOCUMENT_COLLECTION = "document_collection"


class OutcomeType(str, Enum):
    """Conversation outcome types"""
    QUALIFIED = "qualified"
    BOOKED = "booked"
    REJECTED = "rejected"
    NO_RESPONSE = "no_response"
    ESCALATED = "escalated"


# =============================================================================
# REQUEST SCHEMAS
# =============================================================================

class Message(BaseModel):
    """A single message in a conversation"""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = None


class OrganizationInfo(BaseModel):
    """Organization branding info for white-label support"""
    id: Optional[int] = Field(None, description="Organization ID")
    name: Optional[str] = Field(None, description="Organization name")
    brand_name: Optional[str] = Field(None, description="Brand name agents should use")
    display_name: Optional[str] = Field(None, description="Display name for customers")
    website: Optional[str] = Field(None, description="Company website")
    phone: Optional[str] = Field(None, description="Company phone")
    agent_personas: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="Custom agent personas per org: {agent_id: {name, role}}"
    )


class AgentExecuteRequest(BaseModel):
    """Request to execute an agent"""
    agent_id: str = Field(..., description="Agent identifier (e.g., 'lead_agent', 'email_intel')")
    conversation_id: str = Field(..., description="Unique conversation identifier")
    stage: ConversationStage = Field(
        ConversationStage.INITIAL_CONTACT,
        description="Current conversation stage"
    )
    history: List[Message] = Field(
        default_factory=list,
        description="Conversation history"
    )
    user_profile: Dict[str, Any] = Field(
        default_factory=dict,
        description="User/lead profile data"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional context variables"
    )
    # White-label support
    organization_id: Optional[int] = Field(
        None,
        description="Organization ID for white-label branding"
    )
    organization: Optional[OrganizationInfo] = Field(
        None,
        description="Organization branding info (alternative to organization_id)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "lead_agent",
                "conversation_id": "conv_123",
                "stage": "initial_contact",
                "history": [
                    {"role": "assistant", "content": "Hi! Are you still exploring mortgage options?"},
                    {"role": "user", "content": "Yes, I'm looking to refinance"}
                ],
                "user_profile": {
                    "first_name": "John",
                    "email": "john@example.com",
                    "loan_purpose": "refinance"
                },
                "metadata": {
                    "source": "website",
                    "campaign": "spring_2024"
                },
                "organization_id": 123,
                "organization": {
                    "brand_name": "ABC Mortgage",
                    "display_name": "ABC Mortgage Company"
                }
            }
        }


class EmailAnalysisRequest(BaseModel):
    """Request to analyze an email"""
    email_content: str = Field(..., description="Full email content")
    sender: str = Field(..., description="Sender email address")
    subject: str = Field(..., description="Email subject line")
    conversation_id: Optional[str] = Field(None, description="Conversation ID if part of thread")
    user_id: Optional[str] = Field(None, description="Internal user ID")
    # White-label support
    organization_id: Optional[int] = Field(
        None,
        description="Organization ID for white-label branding"
    )
    organization: Optional[OrganizationInfo] = Field(
        None,
        description="Organization branding info (alternative to organization_id)"
    )


class OutcomeLogRequest(BaseModel):
    """Request to log a conversation outcome"""
    conversation_id: str
    agent_id: str
    outcome_type: OutcomeType
    total_messages: int = 0
    qualification_complete: bool = False
    booking_made: bool = False
    revenue_generated: Optional[float] = None
    metrics: Optional[Dict[str, Any]] = None


class ABTestCreateRequest(BaseModel):
    """Request to create an A/B test"""
    test_name: str = Field(..., description="Name for the test")
    agent_id: str = Field(..., description="Agent to test")
    variant_a_config: Dict[str, Any] = Field(..., description="Config for variant A")
    variant_b_config: Dict[str, Any] = Field(..., description="Config for variant B")
    traffic_split: float = Field(0.5, ge=0, le=1, description="Traffic % to variant A")


class QualityAnalysisRequest(BaseModel):
    """Request to analyze prompt quality"""
    prompt: str = Field(..., description="The prompt to analyze")
    agent_name: Optional[str] = Field(None, description="Agent name for the report")


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================

class AgentExecuteResponse(BaseModel):
    """Response from agent execution"""
    success: bool
    response_text: str = Field(..., description="Agent's response")
    conversation_id: str
    stage: str
    suggested_next_stage: Optional[str] = None
    qualification_data: Optional[Dict[str, Any]] = None
    execution_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Execution metrics (tokens, latency)"
    )


class EmailAnalysisResponse(BaseModel):
    """Response from email analysis"""
    success: bool
    category: str
    confidence: float
    loan_number: Optional[str] = None
    borrower: Optional[str] = None
    urgency: str
    action_items: List[str] = Field(default_factory=list)
    deadline: Optional[str] = None
    routing: str
    summary: str
    execution_metrics: Dict[str, Any] = Field(default_factory=dict)


class AgentMetricsResponse(BaseModel):
    """Agent performance metrics response"""
    agent_id: str
    period_days: int
    total_conversations: int
    response_rate: float
    qualification_rate: float
    booking_rate: float
    pull_through_rate: float
    token_metrics: Dict[str, Any]
    latency_metrics: Dict[str, Any]
    revenue: Dict[str, Any]
    funnel: Dict[str, int]


class StageBreakdownResponse(BaseModel):
    """Stage-by-stage performance breakdown"""
    agent_id: str
    period_days: int
    stages: Dict[str, Dict[str, Any]]


class ABTestResultsResponse(BaseModel):
    """A/B test results response"""
    test_id: str
    test_name: str
    status: str
    variant_a: Dict[str, Any]
    variant_b: Dict[str, Any]
    lift_percent: float
    is_significant: bool
    winner: Optional[str]
    recommendation: str


class QualityAnalysisResponse(BaseModel):
    """Quality analysis response"""
    total_score: float
    max_score: int = 100
    percentage: float
    grade: str
    category_scores: Dict[str, Dict[str, Any]]
    checks_passed: List[Dict[str, str]]
    checks_failed: List[Dict[str, str]]
    recommendations: List[str]


class AgentConfigResponse(BaseModel):
    """Agent configuration response"""
    agent_id: str
    persona: Dict[str, Any]
    rules: Dict[str, Any]
    qualification: Dict[str, Any]
    objection_handling: Dict[str, Any]
    use_case: str
    channels: List[str]
    first_message_template: str
    is_active: bool


class AgentListResponse(BaseModel):
    """List of agents response"""
    agents: List[AgentConfigResponse]
    total: int


class TokenUsageResponse(BaseModel):
    """Token usage trends response"""
    agent_id: str
    period_days: int
    trends: List[Dict[str, Any]]
    total_tokens: int
    estimated_cost: float
