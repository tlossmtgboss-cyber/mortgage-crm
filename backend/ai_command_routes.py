"""
AI Command Routes for Pipeline 360 AI Landing Page

This module provides endpoints for processing natural language commands
and executing CRM actions through Claude AI.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import logging
import os
import json
import uuid
import time
import anthropic

from database import get_db
from conversation_memory_service import ConversationMemory
from crm_context_service import CRMContextService
from pattern_analyzer import PatternAnalyzer
from query_executor import QueryExecutor, execute_query, format_results

logger = logging.getLogger(__name__)


# ============================================================================
# AI Reliability Configuration
# ============================================================================

AI_CONFIG = {
    "temperature": 0,           # No randomness - deterministic
    "top_p": 1,                  # No nucleus sampling
    "max_tokens": 2000,
}


# ============================================================================
# Circuit Breaker Pattern
# ============================================================================

class AICircuitBreaker:
    """Circuit breaker to prevent cascading AI failures"""

    def __init__(self, failure_threshold=3, timeout=300):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED = working, OPEN = broken

    def record_success(self):
        """Record successful AI call"""
        self.failure_count = 0
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            logger.info("AI Circuit breaker CLOSED - recovered")

    def record_failure(self):
        """Record failed AI call"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.error(f"AI Circuit breaker OPEN after {self.failure_count} failures")

    def can_execute(self) -> bool:
        """Check if we can make an AI call"""
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
                logger.info("AI Circuit breaker HALF_OPEN - attempting recovery")
                return True
            return False

        # HALF_OPEN - allow one test call
        return True

    def get_fallback(self) -> Dict[str, Any]:
        """Return fallback response when circuit is open"""
        return {
            "intent": "GENERAL_QUERY",
            "explanation": "The AI assistant is temporarily unavailable. Please try again in a few minutes.",
            "data": {},
            "fallback": True
        }


# Global circuit breaker instance
ai_circuit_breaker = AICircuitBreaker(failure_threshold=3, timeout=300)


# ============================================================================
# AI Metrics Logging
# ============================================================================

class AIMetrics:
    """Log AI interactions for monitoring and debugging"""

    @staticmethod
    def log_interaction(
        user_id: int,
        request_message: str,
        response: Dict[str, Any],
        execution_time_ms: float,
        success: bool,
        error: str = None,
        function_calls_made: int = 0
    ):
        """Log an AI interaction"""
        try:
            logger.info(f"AI_METRIC | user_id={user_id} | "
                       f"intent={response.get('intent', 'UNKNOWN')} | "
                       f"success={success} | "
                       f"time_ms={execution_time_ms:.0f} | "
                       f"function_calls={function_calls_made} | "
                       f"message_preview={request_message[:50]}...")

            if error:
                logger.error(f"AI_ERROR | user_id={user_id} | error={error}")
        except Exception as e:
            logger.warning(f"Failed to log AI metrics: {e}")


# ============================================================================
# Function Calling Tools Definition
# ============================================================================

AI_TOOLS = [
    {
        "name": "get_daily_summary",
        "description": "Get the user's daily summary including tasks, leads, loans, and follow-ups",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "search_crm",
        "description": "Search for leads, loans, or clients by name, email, or phone",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (name, email, or phone)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "update_lead_status",
        "description": "Update a lead's status/stage in the CRM",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {
                    "type": "integer",
                    "description": "The lead's ID"
                },
                "new_status": {
                    "type": "string",
                    "enum": ["New", "Prospect", "Application Started", "Pre-Approved", "Closed Won", "Closed Lost"],
                    "description": "New status for the lead"
                }
            },
            "required": ["lead_id", "new_status"]
        }
    },
    {
        "name": "create_task",
        "description": "Create a new task in the CRM",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Task title"
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date in ISO format (YYYY-MM-DD)"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Task priority"
                },
                "lead_id": {
                    "type": "integer",
                    "description": "Optional lead ID to associate with task"
                }
            },
            "required": ["title", "due_date"]
        }
    },
    {
        "name": "send_email_campaign",
        "description": "Send an email campaign to selected clients",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter_criteria": {
                    "type": "object",
                    "description": "Criteria to select recipients (status, loan_type, etc.)"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line"
                },
                "body": {
                    "type": "string",
                    "description": "Email body content"
                }
            },
            "required": ["subject", "body"]
        }
    },
    {
        "name": "get_pipeline_report",
        "description": "Generate a pipeline analysis report",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_range": {
                    "type": "string",
                    "enum": ["7d", "30d", "90d", "ytd"],
                    "description": "Date range for the report"
                }
            },
            "required": []
        }
    },
    # Analytical Query Tools
    {
        "name": "query_pipeline_analysis",
        "description": "Get detailed pipeline analysis by stage including lead counts, values, and age",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "query_lead_source_performance",
        "description": "Analyze lead source performance including close rates and revenue",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_range_days": {
                    "type": "integer",
                    "description": "Number of days to analyze (default 90)",
                    "default": 90
                }
            },
            "required": []
        }
    },
    {
        "name": "query_conversion_funnel",
        "description": "Analyze conversion rates through pipeline stages",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "query_loan_type_performance",
        "description": "Get performance breakdown by loan type including win rates",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "query_monthly_trends",
        "description": "Get monthly trends for leads and closings",
        "input_schema": {
            "type": "object",
            "properties": {
                "months": {
                    "type": "integer",
                    "description": "Number of months to analyze (default 6)",
                    "default": 6
                }
            },
            "required": []
        }
    },
    {
        "name": "query_stale_leads",
        "description": "Find stale leads that need attention",
        "input_schema": {
            "type": "object",
            "properties": {
                "stale_days": {
                    "type": "integer",
                    "description": "Days since created to consider stale (default 14)",
                    "default": 14
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default 20)",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "query_high_value_opportunities",
        "description": "Find high-value leads in pipeline",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_amount": {
                    "type": "integer",
                    "description": "Minimum loan amount to include (default 500000)",
                    "default": 500000
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default 20)",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "query_activity_summary",
        "description": "Get summary of recent activities by type",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to analyze (default 30)",
                    "default": 30
                }
            },
            "required": []
        }
    },
    # Market Intelligence Tools
    {
        "name": "get_market_intelligence",
        "description": "Get current market conditions including treasury yields, mortgage rates, MBS prices, and rate lock recommendations",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_rate_lock_recommendation",
        "description": "Get specific rate lock recommendation based on lock period and current market conditions",
        "input_schema": {
            "type": "object",
            "properties": {
                "lock_days": {
                    "type": "integer",
                    "description": "Number of days for rate lock (15, 30, 45, 60)",
                    "default": 30
                },
                "loan_amount": {
                    "type": "number",
                    "description": "Loan amount for context"
                }
            },
            "required": []
        }
    }
]


# ============================================================================
# Validation Pipeline
# ============================================================================

class ValidationResult:
    def __init__(self, is_valid: bool, reason: str = None):
        self.is_valid = is_valid
        self.reason = reason


class ActionValidator:
    """Validate AI actions before execution"""

    @staticmethod
    def validate_action(action: Dict[str, Any], user_id: int, db: Session) -> ValidationResult:
        """Validate an action is safe to execute"""
        action_name = action.get("name", "")
        parameters = action.get("parameters", {})

        # Check 1: Known action type
        valid_actions = [
            "get_daily_summary", "search_crm", "update_lead_status",
            "create_task", "send_email_campaign", "get_pipeline_report",
            # Analytical query tools
            "query_pipeline_analysis", "query_lead_source_performance",
            "query_conversion_funnel", "query_loan_type_performance",
            "query_monthly_trends", "query_stale_leads",
            "query_high_value_opportunities", "query_activity_summary",
            "get_market_intelligence", "get_rate_lock_recommendation"
        ]
        if action_name not in valid_actions:
            return ValidationResult(False, f"Unknown action: {action_name}")

        # Check 2: User owns the entity (for update operations)
        if action_name == "update_lead_status":
            lead_id = parameters.get("lead_id")
            if lead_id:
                main = get_main_module()
                Lead = main.Lead
                lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == user_id).first()
                if not lead:
                    return ValidationResult(False, "Lead not found or not owned by user")

        # Check 3: Parameter validation
        if action_name == "create_task":
            due_date_str = parameters.get("due_date", "")
            try:
                due_date = datetime.fromisoformat(due_date_str) if due_date_str else None
                if due_date and due_date.date() < datetime.now().date():
                    return ValidationResult(False, "Cannot create tasks with past due dates")
            except ValueError:
                return ValidationResult(False, "Invalid date format")

        return ValidationResult(True)

    @staticmethod
    def pre_execution_check(action: Dict[str, Any], user_id: int, db: Session) -> ValidationResult:
        """Verify data exists before attempting action"""
        action_name = action.get("name", "")
        parameters = action.get("parameters", {})

        if action_name == "update_lead_status":
            lead_id = parameters.get("lead_id")
            main = get_main_module()
            Lead = main.Lead
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return ValidationResult(False, f"Lead {lead_id} not found")

        return ValidationResult(True)

# Lazy import helper for main module to avoid circular imports
def get_main_module():
    import main
    return main

def get_current_user_dependency():
    """Get the get_current_user dependency from main module"""
    return get_main_module().get_current_user

router = APIRouter(prefix="/api/v1/ai")

# Initialize Anthropic client
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# In-memory action cache (in production, use Redis)
action_cache: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Pydantic Models
# ============================================================================

class AICommandRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # For permanent memory tracking
    conversation_context: Optional[List[Dict[str, str]]] = []
    action_context: Optional[Dict[str, Any]] = {}  # Store action previews for context
    current_state: Optional[Dict[str, Any]] = {}  # Current conversation state


class AICommandResponse(BaseModel):
    intent: str
    explanation: str
    preview: Optional[Dict[str, Any]] = None
    action_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None  # Return session ID for tracking


class ActionExecuteRequest(BaseModel):
    action_id: str
    session_id: Optional[str] = None  # For permanent memory tracking
    modifications: Optional[Dict[str, Any]] = {}


class ActionExecuteResponse(BaseModel):
    success: bool
    message: str
    result: Optional[Dict[str, Any]] = None


# ============================================================================
# System Prompt
# ============================================================================

SYSTEM_PROMPT = """You are Pipeline 360's AI assistant, designed to help mortgage professionals manage their CRM efficiently through natural language commands.

=== CRITICAL RULES FOR DATA AND ACTIONS ===

1. WHEN RESPONDING TO DATA REQUESTS:
   - You MUST use the ACTUAL CRM DATA provided in this context
   - NEVER say "0 active leads" when the data shows leads exist
   - NEVER use placeholder or default values
   - If you see "Active Leads: 16" in the context, say "16 active leads" in your response

2. FORBIDDEN RESPONSES (never say these):
   ❌ "0 active leads" when leads exist
   ❌ "$0 pipeline" when pipeline has value
   ❌ "0 tasks" when tasks are listed
   ❌ Any response with placeholder zeros when real data is provided

3. FOR DAILY_VIEW REQUESTS ("what do I need to do today"):
   - Look at the DAILY VIEW DATA section below
   - Use the EXACT numbers provided
   - List actual client names from the data
   - Mention specific tasks and follow-ups

4. EXAMPLE OF CORRECT RESPONSE:
   If data shows: Active Leads: 16, Pipeline: $2,845,000
   ✅ CORRECT: "You have 16 active leads with $2,845,000 in pipeline"
   ❌ WRONG: "You have 0 active leads with $0 in pipeline"

5. FOR REFERRAL PARTNER QUESTIONS:
   When user asks "who is my most profitable referral partner":
   - You MUST name the specific partner from the data
   - You MUST include revenue amount and deal count
   - NEVER say "Let me show you..." without showing actual data

6. FORBIDDEN GENERIC RESPONSES:
   ❌ "Let me show you your tasks and priorities..."
   ❌ "I'll look at your referral partner data..."
   ❌ "Here's an overview of your pipeline..."

   These are WRONG because they don't include actual data.

   ALWAYS include specific names, numbers, and amounts from the CRM DATA section.

=== END CRITICAL RULES ===

INTENT CLASSIFICATION:
You MUST classify each user message to one of these intents and return the appropriate JSON:

- "What do I need to do today?" or "my tasks" or "daily overview" → intent: "DAILY_VIEW"
- "Tell me about my leads" or "how many leads" or "show my clients" → intent: "GENERAL_QUERY"
- "Send email" or "email clients" → intent: "EMAIL_CAMPAIGN"
- "Find [name]" or "search for" → intent: "SEARCH"
- Questions about data (leads, loans, pipeline) → intent: "GENERAL_QUERY"

STOP AND CHECK: If the user asked about "leads", "clients", or "data", you MUST return intent: "GENERAL_QUERY", NOT "DAILY_VIEW".

CRITICAL MEMORY INSTRUCTIONS:
- You have access to the FULL conversation history - use it!
- When user says "it", "that", "the email", "the update" - CHECK HISTORY to find what they're referring to
- NEVER ask "what email?" if we just discussed an email
- NEVER start over if user asks to modify something - build on what was already created
- When user asks to modify previous work, find it in history and make the specific change
- Always reference previous context when relevant to the current request
- If user says "make it shorter" or "make it more urgent", modify the PREVIOUS draft

CONVERSATION CONTINUITY EXAMPLES:
- If we just drafted an email and user says "make it shorter" → modify that email
- If we previewed a bulk update and user says "change the reason" → update that action
- If user refers to "the last one" or "that" → find it in conversation history
- Maintain context across multiple turns without losing track

INTENT MATCHING RULES (FOLLOW STRICTLY):
- When user asks "what do I need to do today", "my tasks", "what's on my plate", "daily overview" → return DAILY_VIEW
- When user asks about their leads, clients, or pipeline data (e.g., "tell me about my leads", "show my clients", "how many leads do I have") → return GENERAL_QUERY with the actual data from CRM context
- When user explicitly asks to "send email", "email clients", "draft email" → return EMAIL_CAMPAIGN
- When user explicitly asks to "update records", "bulk update" → return BULK_UPDATE
- When user explicitly asks about "voicemail", "drop voicemail" → return VOICEMAIL_DROP
- When user explicitly asks for "report", "pipeline report" → return PIPELINE_REPORT
- When user asks about specific lead/client by name → return SEARCH
- DO NOT suggest actions the user didn't ask for. If they ask about leads, show the lead data from CRM context.

CRITICAL: When answering questions about CRM data (leads, loans, clients, pipeline):
- ALWAYS use the CRM DATA provided below - this is the user's ACTUAL data
- Include specific names, numbers, and details from the data
- Never make up placeholder data - use what's in the CRM DATA section

EXAMPLES OF CORRECT INTENT MATCHING:
User: "What do I need to do today?" → intent: "DAILY_VIEW"
User: "Tell me about my leads" → intent: "GENERAL_QUERY" (explain the lead data)
User: "How many leads do I have?" → intent: "GENERAL_QUERY" (provide count)
User: "Show me my pipeline" → intent: "GENERAL_QUERY" (show pipeline data)
User: "Send an email to my pre-approved clients" → intent: "EMAIL_CAMPAIGN"
User: "Find John Smith" → intent: "SEARCH"

For GENERAL_QUERY about data, your response should include:
- explanation: A summary of the requested data with actual numbers and names from CRM context
- data: The relevant data subset

You can perform the following actions:

1. DAILY_VIEW - Show today's tasks, follow-ups, and reconciliation items (use for ANY question about "today", "tasks", "to do", "what should I do")
2. EMAIL_CAMPAIGN - Send emails to filtered groups of clients (ONLY when user explicitly requests email)
3. BULK_UPDATE - Update multiple records at once
4. VOICEMAIL_DROP - Queue ringless voicemail campaigns
5. PIPELINE_REPORT - Generate pipeline analysis reports
6. SEARCH - Search for clients, deals, or tasks
7. GENERAL_QUERY - Answer questions about the CRM data
8. ANALYTICAL_QUERY - Run advanced analytics on CRM data
9. MARKET_INTELLIGENCE - Get rate lock recommendations and market conditions

MARKET INTELLIGENCE QUERIES:
When user asks about rate locks, market conditions, or whether to lock:
- "should I lock?" or "rate lock recommendation" → intent: "MARKET_INTELLIGENCE"
- "what are current rates?" or "market conditions" → intent: "MARKET_INTELLIGENCE"
- "when should I lock?" or "lock or float?" → intent: "MARKET_INTELLIGENCE"
- "MBS prices" or "treasury yields" → intent: "MARKET_INTELLIGENCE"

For MARKET_INTELLIGENCE, data should include:
- lock_days: Optional number of days for lock (15, 30, 45, 60). Default 30.
- loan_amount: Optional loan amount for context

EXAMPLE MARKET_INTELLIGENCE RESPONSE:
{
  "intent": "MARKET_INTELLIGENCE",
  "explanation": "Based on current market conditions, here's my rate lock recommendation.",
  "data": {
    "lock_days": 30
  }
}

ANALYTICAL QUERIES AVAILABLE:
When user asks analytical questions, use these query types:
- "pipeline analysis" or "how is my pipeline doing" → query_pipeline_analysis
- "lead source performance" or "best lead sources" → query_lead_source_performance
- "conversion rates" or "funnel analysis" → query_conversion_funnel
- "loan type performance" or "best loan types" → query_loan_type_performance
- "monthly trends" or "month over month" → query_monthly_trends
- "stale leads" or "leads not spoken to" or "inactive leads" or "haven't contacted" → query_stale_leads

CRITICAL - STALE LEADS QUERIES:
When user asks about leads they haven't contacted, leads gone cold, or inactive leads:
Examples:
- "what leads have I not spoken to in a while?" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"
- "show me stale leads" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"
- "which leads need follow-up?" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"
- "leads I haven't contacted recently" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"
- "inactive leads" or "cold leads" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"

DO NOT return DAILY_VIEW for these queries - they are specifically asking about STALE LEADS, not daily tasks.
- "stale leads" or "leads need attention" → query_stale_leads
- "high value opportunities" or "big deals" → query_high_value_opportunities
- "activity summary" or "what have I done" → query_activity_summary

For ANALYTICAL_QUERY, data MUST include:
- query_type: One of: "query_pipeline_analysis", "query_lead_source_performance", "query_conversion_funnel", "query_loan_type_performance", "query_monthly_trends", "query_stale_leads", "query_high_value_opportunities", "query_activity_summary"
- params: Any parameters like date_range_days (default 90), min_amount (default 500000), limit (default 20), stale_days (default 14), months (default 6), days (default 30)

EXAMPLE ANALYTICAL_QUERY RESPONSE:
{
  "intent": "ANALYTICAL_QUERY",
  "explanation": "I'll run that analysis for you.",
  "data": {
    "query_type": "query_monthly_trends",
    "params": {"months": 6}
  }
}

When responding, you MUST return a valid JSON object with these fields:
- intent: The action type from the list above
- explanation: A brief, friendly explanation of what you're going to do
- preview: Object containing preview data for the action (if applicable)
- data: Additional data needed for execution

For EMAIL_CAMPAIGN, preview should include:
- recipients: List of client names/count
- subject: Email subject line
- body: Email content
- template: Template name if using one

For BULK_UPDATE, preview should include:
- records: List of records to update with current and new values
- field: Field being updated
- count: Number of records affected

For VOICEMAIL_DROP, preview should include:
- recipients: List of recipients
- script: The voicemail script content
- scheduled_time: When to send

For PIPELINE_REPORT, preview should include:
- report_type: Type of report
- date_range: Date range covered
- metrics: Key metrics to include

For DAILY_VIEW, data should include:
- tasks: List of today's tasks
- follow_ups: List of follow-ups
- reconciliations: List of reconciliation items
- summary: Overview statistics

For SEARCH, data should include:
- results: List of matching records
- query: The search terms used

Always be helpful, concise, and focus on actionable results. If you can't determine the intent, ask for clarification.
"""


# ============================================================================
# Helper Functions
# ============================================================================

def get_daily_summary(db: Session, user_id: int) -> Dict[str, Any]:
    """Get daily summary data for the user - includes REAL CRM data"""
    # Clear any previous failed transaction state
    try:
        db.rollback()
    except Exception:
        pass

    main = get_main_module()
    Task = main.Task
    Lead = main.Lead
    Loan = main.Loan

    today = datetime.now().date()

    # Get ALL pending tasks (not just today's)
    all_tasks = db.query(Task).filter(
        Task.owner_id == user_id,
        Task.status != 'completed'
    ).order_by(Task.priority.desc(), Task.due_date.asc()).limit(20).all()

    # Separate today's tasks and overdue tasks
    today_tasks = [t for t in all_tasks if t.due_date and t.due_date.date() == today]
    overdue_tasks = [t for t in all_tasks if t.due_date and t.due_date.date() < today]

    # Get ACTUAL LEAD DATA
    all_leads = db.query(Lead).filter(Lead.owner_id == user_id).all()
    total_leads = len(all_leads)

    # Group leads by status
    lead_status_breakdown = {}
    for lead in all_leads:
        status = lead.stage.value if lead.stage else 'Unassigned'
        lead_status_breakdown[status] = lead_status_breakdown.get(status, 0) + 1

    # Get ACTUAL LOAN DATA
    all_loans = db.query(Loan).filter(Loan.loan_officer_id == user_id).all()
    total_loans = len(all_loans)
    total_pipeline_value = sum(float(loan.amount or 0) for loan in all_loans)

    # Group loans by stage
    loan_stage_breakdown = {}
    for loan in all_loans:
        stage = loan.stage or 'Unknown'
        loan_stage_breakdown[stage] = loan_stage_breakdown.get(stage, 0) + 1

    # Get MUM clients (safely check if table exists)
    mum_clients = []
    try:
        # Check if MUMClient model exists and query
        if hasattr(main, 'MUMClient'):
            MUMClient = main.MUMClient
            mum_clients = db.query(MUMClient).filter(MUMClient.loan_officer_id == user_id).limit(10).all()
    except Exception as e:
        db.rollback()  # Rollback to clear failed transaction
        logger.debug(f"MUM query failed (table may not exist): {e}")

    # Get unread emails/messages (safely check if table exists)
    unread_messages = 0
    try:
        if hasattr(main, 'EmailMessage'):
            EmailMessage = main.EmailMessage
            unread_messages = db.query(EmailMessage).filter(
                EmailMessage.user_id == user_id,
                EmailMessage.direction == 'inbound',
                EmailMessage.status == 'received'
            ).count()
    except Exception as e:
        db.rollback()  # Rollback to clear failed transaction
        logger.debug(f"EmailMessage query failed (table may not exist): {e}")

    # Build follow-ups from leads needing attention
    follow_ups = []

    # Overdue tasks need immediate attention
    if overdue_tasks:
        follow_ups.append({
            "type": "Overdue Tasks",
            "items": [f"{t.title} (Due: {t.due_date.strftime('%m/%d') if t.due_date else 'N/A'})" for t in overdue_tasks[:5]],
            "priority": "High"
        })

    # New leads need initial contact
    new_stage_leads = [l for l in all_leads if l.stage and l.stage.value == 'New']
    if new_stage_leads:
        follow_ups.append({
            "type": "New Leads Follow-up",
            "items": [f"{l.name} ({l.loan_type or 'N/A'})" for l in new_stage_leads[:5]],
            "priority": "High"
        })

    # Application started leads need follow-up
    app_leads = [l for l in all_leads if l.stage and l.stage.value == 'Application Started']
    if app_leads:
        follow_ups.append({
            "type": "Application Started Follow-up",
            "items": [f"{l.name} (${l.preapproval_amount or 0:,.0f})" for l in app_leads[:5]],
            "priority": "High"
        })

    # Pre-approved leads - rate lock opportunities
    preapproved = [l for l in all_leads if l.stage and l.stage.value == 'Pre-Approved']
    if preapproved:
        follow_ups.append({
            "type": "Pre-Approved - Rate Lock Check",
            "items": [f"{l.name} (${l.preapproval_amount or 0:,.0f})" for l in preapproved[:5]],
            "priority": "High"
        })

    # Prospects need nurturing
    prospects = [l for l in all_leads if l.stage and l.stage.value == 'Prospect']
    if prospects:
        follow_ups.append({
            "type": "Prospect Nurturing",
            "items": [f"{l.name}" for l in prospects[:5]],
            "priority": "Medium"
        })

    # Build reconciliations from loans in pipeline
    reconciliations = []

    # Loans needing attention by stage
    processing_loans = [l for l in all_loans if l.stage == 'Processing']
    if processing_loans:
        reconciliations.append({
            "type": "Processing - Document Collection",
            "items": [f"{loan.borrower_name} (${loan.amount or 0:,.0f})" for loan in processing_loans[:3]]
        })

    uw_loans = [l for l in all_loans if l.stage in ['UW Received', 'Approved']]
    if uw_loans:
        reconciliations.append({
            "type": "Underwriting Review",
            "items": [f"{loan.borrower_name} ({loan.stage} - ${loan.amount or 0:,.0f})" for loan in uw_loans[:3]]
        })

    ctc_loans = [l for l in all_loans if l.stage == 'CTC']
    if ctc_loans:
        reconciliations.append({
            "type": "Clear to Close - Schedule Closing",
            "items": [f"{loan.borrower_name} (${loan.amount or 0:,.0f})" for loan in ctc_loans[:3]]
        })

    # MUM clients needing attention
    if mum_clients:
        reconciliations.append({
            "type": "MUM Client Check-ins",
            "items": [f"{c.borrower_name} ({c.loan_type or 'N/A'})" for c in mum_clients[:3]]
        })

    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "lead_id": t.lead_id
            } for t in all_tasks[:10]
        ],
        "follow_ups": follow_ups,
        "reconciliations": reconciliations,
        "summary": {
            "total_tasks": len(all_tasks),
            "overdue_tasks": len(overdue_tasks),
            "active_leads": total_leads,
            "hot_prospects": len([l for l in all_leads if l.stage and l.stage.value in ['Prospect', 'Pre-Approved']]),
            "loans_in_pipeline": total_loans,
            "pipeline_volume": f"${total_pipeline_value:,.0f}",
            "unread_messages": unread_messages,
            "mum_clients": len(mum_clients),
            "lead_status_breakdown": lead_status_breakdown,
            "loan_stage_breakdown": loan_stage_breakdown
        }
    }


def search_records(db: Session, user_id: int, query: str) -> Dict[str, Any]:
    """Search across leads and loans"""
    main = get_main_module()
    Lead = main.Lead
    Loan = main.Loan

    search_term = f"%{query}%"

    # Search leads (using owner_id and name field)
    leads = db.query(Lead).filter(
        Lead.owner_id == user_id,
        or_(
            Lead.name.ilike(search_term),
            Lead.email.ilike(search_term),
            Lead.phone.ilike(search_term)
        )
    ).limit(10).all()

    # Search loans
    loans = db.query(Loan).filter(
        Loan.loan_officer_id == user_id,
        or_(
            Loan.borrower_name.ilike(search_term),
            Loan.property_address.ilike(search_term)
        )
    ).limit(10).all()

    return {
        "leads": [
            {
                "id": l.id,
                "name": l.name,
                "email": l.email,
                "phone": l.phone,
                "status": l.stage.value if l.stage else "Unassigned"
            } for l in leads
        ],
        "loans": [
            {
                "id": loan.id,
                "borrower_name": loan.borrower_name,
                "loan_amount": float(loan.amount) if loan.amount else 0,
                "stage": loan.stage
            } for loan in loans
        ],
        "query": query
    }


def get_clients_by_filter(db: Session, user_id: int, filter_criteria: Dict[str, Any]):
    """Get clients matching filter criteria"""
    main = get_main_module()
    Lead = main.Lead

    query = db.query(Lead).filter(Lead.owner_id == user_id)

    if "loan_type" in filter_criteria:
        query = query.filter(Lead.loan_type == filter_criteria["loan_type"])

    if "status" in filter_criteria:
        query = query.filter(Lead.status == filter_criteria["status"])

    if "tag" in filter_criteria:
        # Filter by tag if your Lead model supports tags
        pass

    return query.limit(100).all()


def execute_analytical_query(db: Session, user_id: int, query_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Execute an analytical query and return formatted results"""
    if params is None:
        params = {}

    # Map tool names to query types
    query_type_map = {
        "query_pipeline_analysis": "pipeline_analysis",
        "query_lead_source_performance": "lead_source_performance",
        "query_conversion_funnel": "conversion_funnel",
        "query_loan_type_performance": "loan_type_performance",
        "query_monthly_trends": "monthly_trends",
        "query_stale_leads": "stale_leads_report",
        "query_high_value_opportunities": "high_value_opportunities",
        "query_activity_summary": "activity_summary",
    }

    actual_query_type = query_type_map.get(query_type, query_type)

    # Execute the query
    result = execute_query(db, actual_query_type, params, user_id)

    # Format for Claude
    formatted = format_results(actual_query_type, result)

    return {
        "query_type": actual_query_type,
        "success": result.get("success", False),
        "data": result.get("data", []),
        "count": result.get("count", 0),
        "formatted_text": formatted
    }


def get_market_intelligence(lock_days: int = 30) -> Dict[str, Any]:
    """Fetch current market intelligence for rate lock recommendations"""
    try:
        from scrapers import MarketDataOrchestrator

        orchestrator = MarketDataOrchestrator()
        snapshot = orchestrator.get_market_snapshot()

        if not snapshot:
            snapshot = get_fallback_market_data()

        # Get rate lock context for specific days
        lock_context = orchestrator.get_rate_lock_context(lock_days)

        return {
            "current_rates": {
                "30yr_fixed": snapshot.get("mortgage_rates", {}).get("rate_30yr", 6.50),
                "15yr_fixed": snapshot.get("mortgage_rates", {}).get("rate_15yr", 5.75),
                "spread_to_10yr": snapshot.get("mortgage_rates", {}).get("spread_to_10yr", 2.35)
            },
            "treasury_yields": {
                "2yr": snapshot.get("treasury", {}).get("2yr", 4.25),
                "5yr": snapshot.get("treasury", {}).get("5yr", 4.10),
                "10yr": snapshot.get("treasury", {}).get("10yr", 4.15),
                "30yr": snapshot.get("treasury", {}).get("30yr", 4.35),
                "spread_2s10s": snapshot.get("treasury", {}).get("spread_2s10s", -0.10)
            },
            "market_conditions": {
                "volatility": snapshot.get("volatility", {}).get("assessment", "moderate"),
                "vix": snapshot.get("volatility", {}).get("vix", 18.5),
                "market_score": snapshot.get("market_score", 55)
            },
            "rate_lock_recommendation": {
                "overall": snapshot.get("recommendation", "CAUTIOUS"),
                "lock_period": lock_days,
                "context": lock_context
            },
            "timestamp": snapshot.get("timestamp")
        }
    except Exception as e:
        logger.error(f"Error fetching market intelligence: {e}")
        return get_fallback_market_data()


def get_fallback_market_data() -> Dict[str, Any]:
    """Fallback market data when scrapers unavailable"""
    from datetime import datetime

    return {
        "current_rates": {
            "30yr_fixed": 6.50,
            "15yr_fixed": 5.75,
            "spread_to_10yr": 2.35
        },
        "treasury_yields": {
            "2yr": 4.25,
            "5yr": 4.10,
            "10yr": 4.15,
            "30yr": 4.35,
            "spread_2s10s": -0.10
        },
        "market_conditions": {
            "volatility": "moderate",
            "vix": 18.5,
            "market_score": 55
        },
        "rate_lock_recommendation": {
            "overall": "CAUTIOUS",
            "guidance": "Market conditions suggest careful evaluation. Consider locking if rate is acceptable and closing within 30 days. For longer timelines, monitor for better opportunities.",
            "factors": [
                "Treasury yields relatively stable",
                "Moderate volatility environment",
                "Mortgage spreads within normal range"
            ]
        },
        "timestamp": datetime.now().isoformat(),
        "is_fallback": True
    }


async def process_with_claude(
    message: str,
    context: List[Dict[str, str]],
    db: Session,
    user_id: int,
    action_context: Optional[Dict[str, Any]] = None,
    relevant_past: Optional[List[Dict]] = None,
    total_messages: int = 0,
    crm_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Process the message with Claude AI"""

    if not anthropic_client:
        # Return mock response if no API key
        return generate_mock_response(message, db, user_id)

    # Build conversation history - use more context (50 messages for permanent memory)
    messages = []
    for ctx in context[-50:]:  # Keep last 50 messages for better context
        messages.append({
            "role": ctx.get("role", "user"),
            "content": ctx.get("content", "")
        })

    messages.append({
        "role": "user",
        "content": message
    })

    # Build enhanced system prompt with memory context
    system = SYSTEM_PROMPT

    # CHECK IF THIS IS A DAILY_VIEW REQUEST - add explicit summary numbers
    message_lower = message.lower()
    if any(phrase in message_lower for phrase in ["today", "daily", "morning", "need to do", "what should i", "my tasks", "what's on"]):
        # Fetch daily summary data to show exact numbers
        daily_data = get_daily_summary(db, user_id)
        summary = daily_data.get("summary", {})

        system += f"""

=== DAILY VIEW DATA (YOU MUST USE THESE EXACT NUMBERS) ===
ACTUAL CRM DATA FOR TODAY:
- Active Leads: {summary.get('active_leads', 0)}
- Loans in Pipeline: {summary.get('loans_in_pipeline', 0)}
- Pipeline Volume: {summary.get('pipeline_volume', '$0')}
- Total Tasks: {summary.get('total_tasks', 0)}
- Overdue Tasks: {summary.get('overdue_tasks', 0)}
- Unread Messages: {summary.get('unread_messages', 0)}

LEAD STATUS BREAKDOWN:
{chr(10).join([f"- {status}: {count}" for status, count in summary.get('lead_status_breakdown', {}).items()])}

LOAN STAGE BREAKDOWN:
{chr(10).join([f"- {stage}: {count}" for stage, count in summary.get('loan_stage_breakdown', {}).items()])}

IMPORTANT: Use the EXACT numbers above in your response. Do NOT say "0 active leads" - use "{summary.get('active_leads', 0)} active leads".
=== END DAILY VIEW DATA ===
"""

    # ADD COMPLETE CRM DATA CONTEXT
    if crm_context:
        system += "\n\n=== COMPLETE CRM DATA (You have full access to all this data) ===\n"
        system += CRMContextService.format_complete_context_for_claude(crm_context)

        # Add detailed data for specific queries
        leads = crm_context.get("leads", {})
        if leads.get("recent_leads"):
            system += "\n\nDETAILED LEAD DATA:\n"
            for lead in leads["recent_leads"][:20]:
                system += f"- {lead['name']} | {lead['status']} | {lead.get('loan_type', 'N/A')} | ${lead.get('loan_amount', 0):,.0f} | {lead.get('email', 'N/A')}\n"

        loans = crm_context.get("loans", {})
        if loans.get("recent_loans"):
            system += "\n\nDETAILED LOAN/DEAL DATA:\n"
            for loan in loans["recent_loans"][:20]:
                system += f"- {loan['borrower_name']} | {loan['stage']} | {loan.get('loan_type', 'N/A')} | ${loan.get('loan_amount', 0):,.0f} | {loan.get('property_address', 'N/A')}\n"

        tasks = crm_context.get("tasks", {})
        if tasks.get("todays_tasks"):
            system += "\n\nTODAY'S TASKS:\n"
            for task in tasks["todays_tasks"]:
                system += f"- [{task.get('priority', 'N/A')}] {task['title']} | {task.get('status', 'N/A')}\n"

        mum = crm_context.get("mum_clients", {})
        if mum.get("clients"):
            system += "\n\nMUM CLIENTS:\n"
            for client in mum["clients"][:15]:
                system += f"- {client['name']} | ${client.get('loan_amount', 0):,.0f} | {client.get('interest_rate', 0)}% | Next review: {client.get('next_review_date', 'N/A')}\n"

        partners = crm_context.get("referral_partners", {})
        if partners.get("partners"):
            system += "\n\nREFERRAL PARTNER PERFORMANCE:\n"

            # Highlight most profitable first
            most_profitable = partners.get("most_profitable")
            if most_profitable:
                system += f"*** MOST PROFITABLE: {most_profitable['name']} - ${most_profitable['revenue']:,.0f} from {most_profitable['deals']} closed deals ***\n\n"

            system += "All Partners (ranked by revenue):\n"
            for i, partner in enumerate(partners["partners"][:10], 1):
                system += f"{i}. {partner['name']}"
                if partner.get('company'):
                    system += f" ({partner['company']})"
                system += f"\n   - Total Leads: {partner.get('total_leads', 0)}\n"
                system += f"   - Closed Deals: {partner.get('closed_deals', 0)}\n"
                system += f"   - Total Revenue: ${partner.get('total_revenue', 0):,.0f}\n"
                system += f"   - Avg Deal Size: ${partner.get('avg_deal_size', 0):,.0f}\n"
                system += f"   - Close Rate: {partner.get('close_rate_pct', 0):.0f}%\n\n"

        system += "\n=== END CRM DATA ===\n"

    # ADD PATTERN ANALYSIS & INSIGHTS
    try:
        patterns = PatternAnalyzer.analyze_user_patterns(db, user_id)
        if patterns:
            system += PatternAnalyzer.format_patterns_for_claude(patterns)
    except Exception as e:
        logger.warning(f"Failed to add pattern analysis: {e}")

    # ADD PERMANENT MEMORY CONTEXT
    if total_messages > 0:
        system += f"""

PERMANENT MEMORY STATUS:
- You have had {total_messages} total messages with this user
- You have COMPLETE MEMORY of everything we've discussed
- When user references "yesterday", "last week", or past conversations, check the context below
- ALWAYS use your memory - never claim to not remember something from our history
"""

    # Add relevant past conversations if available
    if relevant_past and len(relevant_past) > 0:
        system += "\n\nRELEVANT PAST CONVERSATIONS (from your permanent memory):\n"
        for msg in relevant_past:
            content_preview = msg.get('content', '')[:300]
            system += f"[{msg.get('timestamp', 'unknown')}] {msg.get('role', 'unknown')}: {content_preview}...\n"

    # Add action context
    if action_context:
        action_summary = "\n\nRECENT ACTIONS IN THIS CONVERSATION:\n"
        for action_id, action_data in action_context.items():
            intent = action_data.get('intent', 'unknown')
            status = action_data.get('status', 'unknown')
            preview = action_data.get('preview', {})
            action_summary += f"- Action {action_id}: {intent} ({status})\n"
            if preview:
                if intent == 'EMAIL_CAMPAIGN':
                    action_summary += f"  Subject: {preview.get('subject', 'N/A')}\n"
                    action_summary += f"  Body: {preview.get('body', 'N/A')[:200]}...\n"
                elif intent == 'BULK_UPDATE':
                    action_summary += f"  Field: {preview.get('field', 'N/A')}, Count: {preview.get('count', 'N/A')}\n"
        system += action_summary

    # Check circuit breaker before making AI call
    if not ai_circuit_breaker.can_execute():
        logger.warning("AI Circuit breaker is OPEN - using fallback")
        return ai_circuit_breaker.get_fallback()

    start_time = time.time()
    function_calls_made = 0

    try:
        # Log the request
        logger.info(f"AI Request - User ID: {user_id}, Message: {message[:100]}...")

        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=AI_CONFIG["max_tokens"],
            temperature=AI_CONFIG["temperature"],  # Deterministic responses
            system=system,
            messages=messages
        )

        # Log the response
        logger.info(f"AI Response - Stop reason: {response.stop_reason}")

        # Record success in circuit breaker
        ai_circuit_breaker.record_success()

        # Parse Claude's response
        response_text = response.content[0].text
        logger.info(f"AI Response text preview: {response_text[:200]}...")

        # Try to extract JSON from the response
        try:
            # Find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)

                # INJECT REAL CRM DATA for DAILY_VIEW
                if result.get("intent") == "DAILY_VIEW":
                    daily_data = get_daily_summary(db, user_id)
                    # Merge Claude's response with actual CRM data
                    if "data" not in result:
                        result["data"] = {}
                    result["data"]["tasks"] = daily_data.get("tasks", [])
                    result["data"]["follow_ups"] = daily_data.get("follow_ups", [])
                    result["data"]["reconciliations"] = daily_data.get("reconciliations", [])
                    # Use Claude's summary if it has better formatting, but include all our data
                    if "summary" in result["data"]:
                        result["data"]["summary"].update({
                            "lead_status_breakdown": daily_data["summary"].get("lead_status_breakdown", {}),
                            "loan_stage_breakdown": daily_data["summary"].get("loan_stage_breakdown", {}),
                            "unread_messages": daily_data["summary"].get("unread_messages", 0),
                            "mum_clients": daily_data["summary"].get("mum_clients", 0),
                        })
                    else:
                        result["data"]["summary"] = daily_data.get("summary", {})

                    # VALIDATION: Check for placeholder values in AI response
                    actual_leads = daily_data["summary"].get("active_leads", 0)
                    actual_loans = daily_data["summary"].get("loans_in_pipeline", 0)
                    explanation = result.get("explanation", "").lower()

                    if "0 active leads" in explanation and actual_leads > 0:
                        logger.warning(f"AI returned placeholder '0 leads' but actual count is {actual_leads}")
                        # Override the explanation with correct data
                        result["explanation"] = f"Here's your daily overview. You have {actual_leads} active leads and {actual_loans} loans in pipeline ({daily_data['summary'].get('pipeline_volume', '$0')})."

                    if "0 loans in pipeline" in explanation and actual_loans > 0:
                        logger.warning(f"AI returned placeholder '0 loans' but actual count is {actual_loans}")

                    logger.info(f"DAILY_VIEW response validated - Leads: {actual_leads}, Loans: {actual_loans}")

                # INJECT QUERY RESULTS for ANALYTICAL_QUERY
                if result.get("intent") == "ANALYTICAL_QUERY":
                    query_type = result.get("data", {}).get("query_type", "")
                    params = result.get("data", {}).get("params", {})

                    if query_type:
                        query_result = execute_analytical_query(db, user_id, query_type, params)
                        result["data"]["query_result"] = query_result
                        # Append formatted results to explanation
                        if query_result.get("success"):
                            result["explanation"] += "\n\n" + query_result.get("formatted_text", "")
                        logger.info(f"ANALYTICAL_QUERY executed: {query_type}, success={query_result.get('success')}")

                # INJECT MARKET DATA for MARKET_INTELLIGENCE
                if result.get("intent") == "MARKET_INTELLIGENCE":
                    lock_days = result.get("data", {}).get("lock_days", 30)
                    market_data = get_market_intelligence(lock_days)
                    result["data"]["market_data"] = market_data

                    # Format market data for explanation
                    rates = market_data.get("current_rates", {})
                    conditions = market_data.get("market_conditions", {})
                    recommendation = market_data.get("rate_lock_recommendation", {})

                    market_summary = f"""

**Current Market Conditions:**
- 30-Year Fixed: {rates.get('30yr_fixed', 'N/A')}%
- 15-Year Fixed: {rates.get('15yr_fixed', 'N/A')}%
- 10-Year Treasury: {market_data.get('treasury_yields', {}).get('10yr', 'N/A')}%
- Market Volatility: {conditions.get('volatility', 'Unknown')} (VIX: {conditions.get('vix', 'N/A')})
- Market Score: {conditions.get('market_score', 'N/A')}/100

**Rate Lock Recommendation: {recommendation.get('overall', 'CAUTIOUS')}**

{recommendation.get('guidance', '')}
"""
                    result["explanation"] += market_summary
                    logger.info(f"MARKET_INTELLIGENCE executed: lock_days={lock_days}, recommendation={recommendation.get('overall')}")

                # Log metrics for successful response
                execution_time = (time.time() - start_time) * 1000
                AIMetrics.log_interaction(
                    user_id=user_id,
                    request_message=message,
                    response=result,
                    execution_time_ms=execution_time,
                    success=True,
                    function_calls_made=function_calls_made
                )

                return result
        except json.JSONDecodeError:
            pass

        # If no JSON found, create a general response
        result = {
            "intent": "GENERAL_QUERY",
            "explanation": response_text,
            "data": {}
        }

        # Log metrics
        execution_time = (time.time() - start_time) * 1000
        AIMetrics.log_interaction(
            user_id=user_id,
            request_message=message,
            response=result,
            execution_time_ms=execution_time,
            success=True,
            function_calls_made=function_calls_made
        )

        return result

    except Exception as e:
        # Record failure in circuit breaker
        ai_circuit_breaker.record_failure()

        # Log metrics for failed response
        execution_time = (time.time() - start_time) * 1000
        AIMetrics.log_interaction(
            user_id=user_id,
            request_message=message,
            response={"intent": "ERROR"},
            execution_time_ms=execution_time,
            success=False,
            error=str(e)
        )

        logger.error(f"Claude API error: {str(e)}")
        return generate_mock_response(message, db, user_id)


def generate_mock_response(message: str, db: Session, user_id: int) -> Dict[str, Any]:
    """Generate a mock response for demo purposes"""
    main = get_main_module()
    Lead = main.Lead

    message_lower = message.lower()

    if "today" in message_lower or "daily" in message_lower or "morning" in message_lower:
        summary = get_daily_summary(db, user_id)
        return {
            "intent": "DAILY_VIEW",
            "explanation": "Here's your daily overview:",
            "data": summary
        }

    elif "email" in message_lower or "send" in message_lower:
        # Get some sample clients
        clients = db.query(Lead).filter(Lead.user_id == user_id).limit(5).all()
        return {
            "intent": "EMAIL_CAMPAIGN",
            "explanation": "I'll prepare an email campaign for you.",
            "preview": {
                "recipients": [f"{c.first_name} {c.last_name}" for c in clients],
                "count": len(clients),
                "subject": "Important Update from Your Mortgage Team",
                "body": "Dear Client,\n\nWe wanted to reach out with some important information about your loan.\n\nBest regards,\nYour Mortgage Team"
            }
        }

    elif "search" in message_lower or "find" in message_lower:
        # Extract search term (simple approach)
        words = message.split()
        search_term = words[-1] if len(words) > 1 else "client"
        results = search_records(db, user_id, search_term)
        return {
            "intent": "SEARCH",
            "explanation": f"Here are the search results for '{search_term}':",
            "data": results
        }

    elif "report" in message_lower or "pipeline" in message_lower:
        return {
            "intent": "PIPELINE_REPORT",
            "explanation": "I'll generate a pipeline report for you.",
            "preview": {
                "report_type": "Pipeline Analysis",
                "date_range": "Last 30 days",
                "metrics": ["Total Loans", "Conversion Rate", "Average Loan Size", "Stage Distribution"]
            }
        }

    elif "voicemail" in message_lower:
        clients = db.query(Lead).filter(Lead.user_id == user_id).limit(3).all()
        return {
            "intent": "VOICEMAIL_DROP",
            "explanation": "I'll set up a ringless voicemail campaign.",
            "preview": {
                "recipients": [f"{c.first_name} {c.last_name}" for c in clients],
                "script": "Hi, this is a quick message from your mortgage team. We have some important updates about current rates. Please call us back at your convenience.",
                "scheduled_time": "Immediately"
            }
        }

    else:
        return {
            "intent": "GENERAL_QUERY",
            "explanation": f"I understand you're asking about: {message}. How can I help you further?",
            "data": {}
        }


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/process-command", response_model=AICommandResponse)
async def process_command(
    request: AICommandRequest,
    db: Session = Depends(get_db)
):
    """
    Process a natural language command and return intent with preview.
    """
    # Get current user from main module
    main = get_main_module()
    get_current_user = get_current_user_dependency()

    # Get actual user from token - try to authenticate
    from fastapi import Request
    try:
        # Get user from database based on demo user for now
        # In a real implementation, this would use proper token auth
        User = main.User
        demo_user = db.query(User).filter(User.email == "demo@example.com").first()
        current_user_id = demo_user.id if demo_user else 1
    except Exception:
        current_user_id = 1  # Fallback

    # Get or create session ID for permanent memory
    session_id = request.session_id or str(uuid.uuid4())

    try:
        # 1. SAVE USER MESSAGE TO PERMANENT MEMORY
        try:
            ConversationMemory.save_message(
                db=db,
                user_id=current_user_id,
                session_id=session_id,
                role='user',
                content=request.message
            )
        except Exception as mem_error:
            logger.warning(f"Failed to save user message to memory: {mem_error}")

        # 2. GET FULL CONTEXT FROM PERMANENT MEMORY
        context = ConversationMemory.get_full_context(
            db=db,
            user_id=current_user_id,
            current_message=request.message
        )

        # 3. GET FULL CRM DATA CONTEXT
        crm_context = CRMContextService.get_full_crm_context(db, current_user_id)

        # 4. BUILD ENHANCED CONTEXT FOR CLAUDE
        # Combine permanent memory with current session context
        combined_context = context['recent_messages'] if context['recent_messages'] else request.conversation_context

        # Process with Claude AI - pass full context including action history and CRM data
        result = await process_with_claude(
            request.message,
            combined_context,
            db,
            current_user_id,
            request.action_context,  # Include action context for memory
            context.get('relevant_past', []),
            context.get('total_messages', 0),
            crm_context  # Include full CRM data
        )

        # Generate action ID if this is an actionable command
        action_id = None
        if result.get("intent") in ["EMAIL_CAMPAIGN", "BULK_UPDATE", "VOICEMAIL_DROP"]:
            action_id = str(uuid.uuid4())
            # Cache the action for later execution
            action_cache[action_id] = {
                "intent": result["intent"],
                "preview": result.get("preview"),
                "user_id": current_user_id,
                "created_at": datetime.now().isoformat(),
                "session_id": session_id
            }

            # 4. SAVE ACTION TO PERMANENT MEMORY
            try:
                ConversationMemory.save_action(
                    db=db,
                    user_id=current_user_id,
                    action_id=action_id,
                    action_type=result["intent"],
                    preview_data=result.get("preview", {})
                )
            except Exception as action_error:
                logger.warning(f"Failed to save action to memory: {action_error}")

        # 5. SAVE ASSISTANT RESPONSE TO PERMANENT MEMORY
        try:
            ConversationMemory.save_message(
                db=db,
                user_id=current_user_id,
                session_id=session_id,
                role='assistant',
                content=result.get("explanation", ""),
                action_id=action_id,
                action_data=result.get("preview")
            )
        except Exception as mem_error:
            logger.warning(f"Failed to save assistant message to memory: {mem_error}")

        return AICommandResponse(
            intent=result.get("intent", "GENERAL_QUERY"),
            explanation=result.get("explanation", ""),
            preview=result.get("preview"),
            action_id=action_id,
            data=result.get("data"),
            session_id=session_id
        )

    except Exception as e:
        logger.error(f"Error processing command: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute-action", response_model=ActionExecuteResponse)
async def execute_action(
    request: ActionExecuteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Execute a previously previewed action.
    """
    # Get actual user from database
    main = get_main_module()
    try:
        User = main.User
        demo_user = db.query(User).filter(User.email == "demo@example.com").first()
        current_user_id = demo_user.id if demo_user else 1
    except Exception:
        current_user_id = 1  # Fallback

    try:
        # Get cached action
        action_data = action_cache.get(request.action_id)
        if not action_data:
            raise HTTPException(status_code=404, detail="Action not found or expired")

        # Verify ownership
        if action_data["user_id"] != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized to execute this action")

        intent = action_data["intent"]
        preview = action_data.get("preview", {})
        modifications = request.modifications
        session_id = request.session_id or action_data.get("session_id")

        # Execute based on intent
        if intent == "EMAIL_CAMPAIGN":
            result = await execute_email_campaign(
                db, current_user_id, preview, modifications, background_tasks
            )
        elif intent == "BULK_UPDATE":
            result = await execute_bulk_update(
                db, current_user_id, preview, modifications
            )
        elif intent == "VOICEMAIL_DROP":
            result = await execute_voicemail_drop(
                db, current_user_id, preview, modifications, background_tasks
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action type: {intent}")

        # UPDATE ACTION STATUS IN PERMANENT MEMORY
        try:
            ConversationMemory.update_action_status(
                db=db,
                action_id=request.action_id,
                status='executed' if result.get('message') else 'failed',
                execution_data=result
            )
        except Exception as mem_error:
            logger.warning(f"Failed to update action status in memory: {mem_error}")

        # SAVE EXECUTION RESULT TO CONVERSATION
        if session_id:
            try:
                ConversationMemory.save_message(
                    db=db,
                    user_id=current_user_id,
                    session_id=session_id,
                    role='assistant',
                    content=f"Action executed: {result.get('message', 'Success')}"
                )
            except Exception as mem_error:
                logger.warning(f"Failed to save execution result to memory: {mem_error}")

        # Remove from cache after execution
        del action_cache[request.action_id]

        return ActionExecuteResponse(
            success=True,
            message=result.get("message", "Action executed successfully"),
            result=result
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing action: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Action Executors
# ============================================================================

async def execute_email_campaign(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any],
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Execute an email campaign"""
    main = get_main_module()
    Lead = main.Lead
    Activity = main.Activity

    # Apply any modifications
    subject = modifications.get("subject", preview.get("subject", ""))
    body = modifications.get("body", preview.get("body", ""))
    recipients = preview.get("recipients", [])

    # In production, this would queue emails through your email service
    # For now, log the action and create activity records

    for recipient_name in recipients:
        # Find the lead
        names = recipient_name.split()
        if len(names) >= 2:
            lead = db.query(Lead).filter(
                Lead.user_id == user_id,
                Lead.first_name == names[0],
                Lead.last_name == names[-1]
            ).first()

            if lead:
                # Create activity record
                activity = Activity(
                    user_id=user_id,
                    lead_id=lead.id,
                    activity_type="email",
                    description=f"Email sent: {subject}",
                    data={"subject": subject, "body": body[:500]}
                )
                db.add(activity)

    db.commit()

    return {
        "message": f"Email campaign sent to {len(recipients)} recipients",
        "recipients_count": len(recipients),
        "subject": subject
    }


async def execute_bulk_update(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute a bulk update operation"""
    main = get_main_module()
    Lead = main.Lead
    Deal = main.Deal

    records = preview.get("records", [])
    field = modifications.get("field", preview.get("field", ""))
    new_value = modifications.get("new_value", preview.get("new_value", ""))

    updated_count = 0

    for record in records:
        record_id = record.get("id")
        record_type = record.get("type", "lead")

        if record_type == "lead":
            lead = db.query(Lead).filter(
                Lead.id == record_id,
                Lead.user_id == user_id
            ).first()

            if lead and hasattr(lead, field):
                setattr(lead, field, new_value)
                updated_count += 1

        elif record_type == "deal":
            deal = db.query(Deal).filter(
                Deal.id == record_id,
                Deal.user_id == user_id
            ).first()

            if deal and hasattr(deal, field):
                setattr(deal, field, new_value)
                updated_count += 1

    db.commit()

    return {
        "message": f"Updated {updated_count} records",
        "updated_count": updated_count,
        "field": field,
        "new_value": new_value
    }


async def execute_voicemail_drop(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any],
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Execute a voicemail drop campaign"""
    main = get_main_module()
    Lead = main.Lead
    Activity = main.Activity

    script = modifications.get("script", preview.get("script", ""))
    recipients = preview.get("recipients", [])

    # In production, this would integrate with a service like Slybroadcast
    # For now, create activity records

    for recipient_name in recipients:
        names = recipient_name.split()
        if len(names) >= 2:
            lead = db.query(Lead).filter(
                Lead.user_id == user_id,
                Lead.first_name == names[0],
                Lead.last_name == names[-1]
            ).first()

            if lead:
                activity = Activity(
                    user_id=user_id,
                    lead_id=lead.id,
                    activity_type="voicemail",
                    description="Ringless voicemail sent",
                    data={"script": script[:500]}
                )
                db.add(activity)

    db.commit()

    return {
        "message": f"Voicemail campaign queued for {len(recipients)} recipients",
        "recipients_count": len(recipients),
        "status": "queued"
    }
