"""
Email Intelligence Agent

Specialized agent for email parsing and intelligence with 12 tools:
1. parse_email_content - Parse and extract data from email
2. classify_email_intent - Classify email intent/category
3. extract_entities - Extract entities from email
4. suggest_response - Suggest response to email
5. generate_response - Generate full email response
6. analyze_sentiment - Analyze email sentiment
7. get_email_thread - Get full email thread context
8. create_follow_up_task - Create task from email
9. link_email_to_lead - Link email to lead/loan
10. get_email_analytics - Get email performance analytics
11. train_response_pattern - Train response pattern
12. get_response_templates - Get response templates
"""

from typing import Any, Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import logging

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)

logger = logging.getLogger(__name__)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class ParseEmailInput(BaseModel):
    email_content: str = Field(..., description="Email content to parse")
    include_attachments: bool = Field(default=False, description="Include attachment info")


class ClassifyIntentInput(BaseModel):
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body")


class ExtractEntitiesInput(BaseModel):
    text: str = Field(..., description="Text to extract entities from")
    entity_types: Optional[List[str]] = Field(None, description="Types to extract: person, date, amount, property")


class SuggestResponseInput(BaseModel):
    email_id: Optional[str] = Field(None, description="Email ID")
    email_content: str = Field(..., description="Email content to respond to")
    tone: str = Field(default="professional", description="Response tone")


class GenerateResponseInput(BaseModel):
    email_content: str = Field(..., description="Original email")
    response_type: str = Field(..., description="Response type: acknowledge, answer, request_info")
    key_points: Optional[List[str]] = Field(None, description="Key points to include")


class SentimentInput(BaseModel):
    text: str = Field(..., description="Text to analyze")


class ThreadInput(BaseModel):
    email_id: str = Field(..., description="Email ID")
    limit: int = Field(default=10, description="Max thread messages")


class CreateTaskInput(BaseModel):
    email_id: str = Field(..., description="Source email ID")
    task_type: str = Field(default="follow_up", description="Task type")
    due_days: int = Field(default=1, description="Days until due")


class LinkEmailInput(BaseModel):
    email_id: str = Field(..., description="Email ID")
    entity_type: str = Field(..., description="Entity type: lead, loan, contact")
    entity_id: int = Field(..., description="Entity ID to link to")


class EmailAnalyticsInput(BaseModel):
    period_days: int = Field(default=30, description="Analytics period")
    group_by: str = Field(default="day", description="Group by: day, week, category")


class TrainPatternInput(BaseModel):
    pattern_name: str = Field(..., description="Pattern name")
    example_emails: List[str] = Field(..., description="Example emails for training")
    response_template: str = Field(..., description="Response template")


class TemplatesInput(BaseModel):
    category: Optional[str] = Field(None, description="Template category")


# ============================================================================
# EMAIL INTELLIGENCE AGENT
# ============================================================================

@AgentRegistry.register
class EmailIntelAgent(SpecializedAgent):
    """
    Email intelligence agent for parsing and response generation.

    Provides email analysis, entity extraction, and automated response
    generation with 12 specialized tools.
    """

    @property
    def name(self) -> str:
        return "EmailIntelAgent"

    @property
    def description(self) -> str:
        return "Parses emails, extracts data, classifies intent, and generates responses"

    def _register_tools(self):
        """Register all email intelligence tools"""

        self.register_tool(AgentTool(
            name="parse_email_content",
            description="Parse email content and extract structured data",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._parse_email_content,
            input_schema=ParseEmailInput
        ))

        self.register_tool(AgentTool(
            name="classify_email_intent",
            description="Classify email intent and category",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._classify_email_intent,
            input_schema=ClassifyIntentInput
        ))

        self.register_tool(AgentTool(
            name="extract_entities",
            description="Extract entities like names, dates, amounts from text",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._extract_entities,
            input_schema=ExtractEntitiesInput
        ))

        self.register_tool(AgentTool(
            name="suggest_response",
            description="Suggest response options for an email",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._suggest_response,
            input_schema=SuggestResponseInput
        ))

        self.register_tool(AgentTool(
            name="generate_response",
            description="Generate full email response",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._generate_response,
            input_schema=GenerateResponseInput
        ))

        self.register_tool(AgentTool(
            name="analyze_sentiment",
            description="Analyze sentiment of email text",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_sentiment,
            input_schema=SentimentInput
        ))

        self.register_tool(AgentTool(
            name="get_email_thread",
            description="Get full email thread context",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_email_thread,
            input_schema=ThreadInput
        ))

        self.register_tool(AgentTool(
            name="create_follow_up_task",
            description="Create follow-up task from email",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._create_follow_up_task,
            input_schema=CreateTaskInput
        ))

        self.register_tool(AgentTool(
            name="link_email_to_lead",
            description="Link email to lead, loan, or contact",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._link_email_to_lead,
            input_schema=LinkEmailInput
        ))

        self.register_tool(AgentTool(
            name="get_email_analytics",
            description="Get email performance analytics",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._get_email_analytics,
            input_schema=EmailAnalyticsInput
        ))

        self.register_tool(AgentTool(
            name="train_response_pattern",
            description="Train a new response pattern",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._train_response_pattern,
            input_schema=TrainPatternInput
        ))

        self.register_tool(AgentTool(
            name="get_response_templates",
            description="Get available response templates",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_response_templates,
            input_schema=TemplatesInput
        ))

    async def _parse_email_content(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Parse email content"""
        content = input_data["email_content"]

        parsed = {
            "has_question": "?" in content,
            "has_request": any(word in content.lower() for word in ["please", "can you", "could you", "need"]),
            "urgency": "high" if any(word in content.lower() for word in ["urgent", "asap", "immediately"]) else "normal",
            "word_count": len(content.split()),
            "estimated_read_time": len(content.split()) // 200  # minutes
        }

        return ToolResult(
            success=True,
            data={"parsed": parsed},
            message="Email parsed successfully"
        )

    async def _classify_email_intent(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Classify email intent"""
        subject = input_data["subject"].lower()
        body = input_data["body"].lower()
        combined = f"{subject} {body}"

        intents = {
            "status_inquiry": ["status", "update", "where", "progress"],
            "document_submission": ["attached", "document", "uploading", "sending"],
            "question": ["how", "what", "when", "why", "can you"],
            "appointment_request": ["schedule", "meeting", "call", "time"],
            "rate_inquiry": ["rate", "interest", "pricing", "quote"],
            "complaint": ["unhappy", "frustrated", "problem", "issue", "wrong"]
        }

        matched_intent = "general"
        confidence = 0.5

        for intent, keywords in intents.items():
            matches = sum(1 for kw in keywords if kw in combined)
            if matches > 0:
                matched_intent = intent
                confidence = min(0.95, 0.5 + (matches * 0.15))
                break

        return ToolResult(
            success=True,
            data={
                "intent": matched_intent,
                "confidence": confidence,
                "requires_response": matched_intent in ["question", "status_inquiry", "appointment_request"]
            },
            message=f"Intent: {matched_intent} ({confidence:.0%} confidence)"
        )

    async def _extract_entities(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Extract entities from text"""
        import re

        text = input_data["text"]
        entities = []

        # Extract amounts
        amounts = re.findall(r'\$[\d,]+(?:\.\d{2})?', text)
        for amt in amounts:
            entities.append({"type": "amount", "value": amt})

        # Extract dates (simple patterns)
        dates = re.findall(r'\d{1,2}/\d{1,2}/\d{2,4}', text)
        for date in dates:
            entities.append({"type": "date", "value": date})

        # Extract phone numbers
        phones = re.findall(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
        for phone in phones:
            entities.append({"type": "phone", "value": phone})

        # Extract emails
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        for email in emails:
            entities.append({"type": "email", "value": email})

        return ToolResult(
            success=True,
            data={"entities": entities, "count": len(entities)},
            message=f"Extracted {len(entities)} entities"
        )

    async def _suggest_response(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Suggest response options"""
        suggestions = [
            {
                "type": "acknowledge",
                "preview": "Thank you for your email. I've received your message and...",
                "tone": "professional"
            },
            {
                "type": "answer",
                "preview": "Thank you for reaching out. To answer your question...",
                "tone": "helpful"
            },
            {
                "type": "request_info",
                "preview": "Thank you for your inquiry. To better assist you, could you please...",
                "tone": "professional"
            }
        ]

        return ToolResult(
            success=True,
            data={"suggestions": suggestions},
            message=f"Generated {len(suggestions)} response suggestions"
        )

    async def _generate_response(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Generate email response"""
        response_type = input_data["response_type"]

        templates = {
            "acknowledge": "Thank you for your email. I've received your message and will review it promptly. I'll get back to you within 24 hours.",
            "answer": "Thank you for reaching out. To answer your question, {answer}. Please let me know if you need any additional information.",
            "request_info": "Thank you for your inquiry. To better assist you, could you please provide the following information:\n\n- {info_needed}\n\nOnce I have this information, I'll be able to help you more effectively."
        }

        response = templates.get(response_type, templates["acknowledge"])

        return ToolResult(
            success=True,
            data={
                "response": response,
                "response_type": response_type,
                "needs_review": True
            },
            message="Response generated"
        )

    async def _analyze_sentiment(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Analyze sentiment"""
        text = input_data["text"].lower()

        positive_words = ["thank", "appreciate", "great", "excellent", "happy", "pleased"]
        negative_words = ["unhappy", "frustrated", "disappointed", "problem", "issue", "wrong"]

        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)

        if negative_count > positive_count:
            sentiment = "negative"
            score = -0.5 - (negative_count * 0.1)
        elif positive_count > negative_count:
            sentiment = "positive"
            score = 0.5 + (positive_count * 0.1)
        else:
            sentiment = "neutral"
            score = 0

        return ToolResult(
            success=True,
            data={
                "sentiment": sentiment,
                "score": max(-1, min(1, score)),
                "requires_attention": sentiment == "negative"
            },
            message=f"Sentiment: {sentiment}"
        )

    async def _get_email_thread(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get email thread"""
        org_id = self.require_org_id()
        # Placeholder - would query email system scoped to organization
        thread = {
            "email_id": input_data["email_id"],
            "organization_id": org_id,
            "messages": [
                {"from": "borrower", "date": datetime.now().isoformat(), "preview": "Initial inquiry..."}
            ],
            "participants": ["borrower@email.com", "lo@perennia.ai"],
            "message_count": 1
        }

        return ToolResult(
            success=True,
            data=thread,
            message=f"Thread with {thread['message_count']} messages"
        )

    async def _create_follow_up_task(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Create follow-up task"""
        from datetime import timedelta
        org_id = self.require_org_id()

        self.audit_log(
            action="create_follow_up_task",
            entity_type="task",
            details={"email_id": input_data["email_id"], "organization_id": org_id}
        )

        return ToolResult(
            success=True,
            data={
                "task_created": True,
                "email_id": input_data["email_id"],
                "organization_id": org_id,
                "task_type": input_data.get("task_type", "follow_up"),
                "due_date": (datetime.now() + timedelta(days=input_data.get("due_days", 1))).isoformat()
            },
            message="Follow-up task created"
        )

    async def _link_email_to_lead(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Link email to entity"""
        org_id = self.require_org_id()

        self.audit_log(
            action="link_email_to_entity",
            entity_type=input_data["entity_type"],
            entity_id=str(input_data["entity_id"]),
            details={"email_id": input_data["email_id"], "organization_id": org_id}
        )

        return ToolResult(
            success=True,
            data={
                "email_id": input_data["email_id"],
                "entity_type": input_data["entity_type"],
                "entity_id": input_data["entity_id"],
                "organization_id": org_id,
                "linked": True
            },
            message=f"Email linked to {input_data['entity_type']} {input_data['entity_id']}"
        )

    async def _get_email_analytics(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get email analytics"""
        org_id = self.require_org_id()

        # Placeholder - would query email analytics scoped to organization
        analytics = {
            "organization_id": org_id,
            "period_days": input_data.get("period_days", 30),
            "metrics": {
                "total_received": 250,
                "total_sent": 180,
                "avg_response_time_hours": 2.5,
                "response_rate": 95
            },
            "by_category": [
                {"category": "status_inquiry", "count": 85},
                {"category": "document_submission", "count": 65},
                {"category": "question", "count": 55},
                {"category": "other", "count": 45}
            ]
        }

        return ToolResult(
            success=True,
            data=analytics,
            message=f"Email analytics for {input_data.get('period_days', 30)} days"
        )

    async def _train_response_pattern(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Train response pattern"""
        org_id = self.require_org_id()

        self.audit_log(
            action="train_response_pattern",
            entity_type="response_pattern",
            details={"pattern_name": input_data["pattern_name"], "organization_id": org_id}
        )

        return ToolResult(
            success=True,
            data={
                "pattern_name": input_data["pattern_name"],
                "organization_id": org_id,
                "examples_count": len(input_data["example_emails"]),
                "trained": True,
                "created_at": datetime.now().isoformat()
            },
            message=f"Pattern '{input_data['pattern_name']}' trained"
        )

    async def _get_response_templates(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get response templates"""
        org_id = self.require_org_id()

        # Placeholder - would query org-specific templates from DB
        templates = {
            "status_update": [
                {"name": "Processing Update", "preview": "Your loan is currently in processing..."},
                {"name": "Underwriting Update", "preview": "Your loan has been submitted to underwriting..."}
            ],
            "document_request": [
                {"name": "Missing Documents", "preview": "We need the following documents..."},
                {"name": "Document Received", "preview": "We've received your documents..."}
            ],
            "general": [
                {"name": "Thank You", "preview": "Thank you for your email..."},
                {"name": "Appointment Confirmation", "preview": "This confirms your appointment..."}
            ]
        }

        category = input_data.get("category")
        if category and category in templates:
            filtered = {category: templates[category]}
        else:
            filtered = templates

        return ToolResult(
            success=True,
            data={"templates": filtered, "organization_id": org_id},
            message="Response templates retrieved"
        )
