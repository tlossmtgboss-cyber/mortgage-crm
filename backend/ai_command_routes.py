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
import anthropic

from database import get_db
from conversation_memory_service import ConversationMemory
from crm_context_service import CRMContextService

logger = logging.getLogger(__name__)

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

MOST IMPORTANT - INTENT CLASSIFICATION (read this first):
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

    # ADD COMPLETE CRM DATA CONTEXT
    if crm_context:
        system += "\n\n=== COMPLETE CRM DATA (You have full access to all this data) ===\n"
        system += CRMContextService.format_context_for_claude(crm_context)

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
            system += "\n\nTOP REFERRAL PARTNERS:\n"
            for partner in partners["partners"][:10]:
                system += f"- {partner['name']} ({partner.get('company', 'N/A')}) | {partner.get('total_referrals', 0)} referrals | ${partner.get('total_volume', 0):,.0f}\n"

        system += "\n=== END CRM DATA ===\n"

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

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system,
            messages=messages
        )

        # Parse Claude's response
        response_text = response.content[0].text

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

                return result
        except json.JSONDecodeError:
            pass

        # If no JSON found, create a general response
        return {
            "intent": "GENERAL_QUERY",
            "explanation": response_text,
            "data": {}
        }

    except Exception as e:
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
