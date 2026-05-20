"""
Portal AI Assistant Routes
Perennia AI - Mortgage CRM

AI-powered chat assistant for the borrower portal.
Provides contextual help, document guidance, and loan status information.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/portal-assistant", tags=["Portal AI Assistant"])


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

from db import get_db

_get_current_user = None


def set_dependencies(get_db_func, get_current_user_func):
    """Set dependencies from main.py."""
    global _get_current_user
    _get_current_user = get_current_user_func
    logger.info("Portal AI Assistant routes dependencies set")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class ChatMessage(BaseModel):
    """Chat message model."""
    role: str = Field(..., description="Message role: user, assistant, system")
    content: str = Field(..., description="Message content")
    timestamp: Optional[str] = None


class ChatRequest(BaseModel):
    """Chat request model."""
    workspace_id: int
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_history: List[ChatMessage] = Field(default_factory=list)
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    """Chat response model."""
    message: str
    suggestions: List[str] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    conversation_id: Optional[str] = None


class QuickAction(BaseModel):
    """Quick action for the assistant."""
    action_type: str
    label: str
    description: str
    params: Optional[Dict[str, Any]] = None


# =============================================================================
# PORTAL CONTEXT HELPERS
# =============================================================================

async def get_workspace_context(db: Session, workspace_id: int) -> Dict[str, Any]:
    """Get context about the workspace for the AI assistant."""
    # Get workspace info
    workspace = db.execute(text("""
        SELECT w.id, w.slug, w.display_name, w.status, w.settings,
               w.created_at, w.updated_at
        FROM purl_workspaces w
        WHERE w.id = :workspace_id
    """), {"workspace_id": workspace_id}).fetchone()

    if not workspace:
        return {}

    context = {
        "workspace": {
            "id": workspace[0],
            "slug": workspace[1],
            "display_name": workspace[2],
            "status": workspace[3],
        }
    }

    # Get application status
    application = db.execute(text("""
        SELECT id, status, completeness_pct, validation_errors, started_at, submitted_at
        FROM purl_applications
        WHERE workspace_id = :workspace_id
        ORDER BY created_at DESC
        LIMIT 1
    """), {"workspace_id": workspace_id}).fetchone()

    if application:
        context["application"] = {
            "id": application[0],
            "status": application[1],
            "completeness_pct": application[2],
            "has_errors": bool(application[3]),
            "started": bool(application[4]),
            "submitted": bool(application[5]),
        }

    # Get document summary
    docs = db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'approved') as approved,
            COUNT(*) FILTER (WHERE status = 'pending') as pending,
            COUNT(*) FILTER (WHERE status = 'rejected') as rejected
        FROM purl_documents
        WHERE workspace_id = :workspace_id
    """), {"workspace_id": workspace_id}).fetchone()

    if docs:
        context["documents"] = {
            "total": docs[0],
            "approved": docs[1],
            "pending": docs[2],
            "rejected": docs[3],
        }

    # Get pending tasks
    tasks = db.execute(text("""
        SELECT COUNT(*) as pending_count
        FROM purl_tasks
        WHERE workspace_id = :workspace_id AND status = 'pending'
    """), {"workspace_id": workspace_id}).fetchone()

    if tasks:
        context["pending_tasks"] = tasks[0]

    # Get loan milestones
    milestones = db.execute(text("""
        SELECT m.name, lm.status, lm.completed_at
        FROM purl_loan_milestones lm
        JOIN purl_milestone_definitions m ON m.id = lm.milestone_id
        JOIN purl_loans l ON l.id = lm.loan_id
        WHERE l.workspace_id = :workspace_id
        ORDER BY m.order_index
    """), {"workspace_id": workspace_id}).fetchall()

    if milestones:
        context["milestones"] = [
            {"name": m[0], "status": m[1], "completed": bool(m[2])}
            for m in milestones
        ]

    return context


def generate_system_prompt(context: Dict[str, Any]) -> str:
    """Generate system prompt based on workspace context."""
    status = context.get("workspace", {}).get("status", "unknown")
    app_status = context.get("application", {}).get("status", "not_started")
    completeness = context.get("application", {}).get("completeness_pct", 0)
    pending_docs = context.get("documents", {}).get("pending", 0)
    pending_tasks = context.get("pending_tasks", 0)

    prompt = """You are a helpful AI assistant for borrowers going through the mortgage loan process.
Your role is to:
1. Answer questions about the loan process and requirements
2. Help borrowers understand what documents they need and why
3. Provide status updates on their application and documents
4. Guide them through completing tasks and uploading documents
5. Explain mortgage terms and concepts in simple language

Current Context:
"""

    if status == "application":
        prompt += f"""
- The borrower is working on their loan application
- Application is {completeness}% complete
- Application status: {app_status}
"""
    elif status == "active_loan":
        prompt += """
- The borrower has an active loan in progress
- They should focus on completing pending tasks and uploading required documents
"""

    if pending_docs > 0:
        prompt += f"- There are {pending_docs} documents pending review\n"

    if pending_tasks > 0:
        prompt += f"- There are {pending_tasks} tasks that need attention\n"

    prompt += """
Guidelines:
- Be friendly, professional, and reassuring
- Keep responses concise but helpful
- If you don't know something specific about their loan, encourage them to contact their loan officer
- Never make promises about approval or timeline
- Protect sensitive information - don't reveal specifics about other borrowers
- Suggest specific next actions when appropriate
"""

    return prompt


async def generate_ai_response(
    message: str,
    context: Dict[str, Any],
    conversation_history: List[ChatMessage],
    db: Session
) -> Dict[str, Any]:
    """Generate AI response using Claude or fallback to rule-based responses."""

    # Try to use Claude API if available
    try:
        import anthropic
        import os

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            client = anthropic.Anthropic(api_key=api_key)

            # Build messages
            messages = []
            for msg in conversation_history[-10:]:  # Last 10 messages for context
                messages.append({
                    "role": msg.role if msg.role in ["user", "assistant"] else "user",
                    "content": msg.content
                })
            messages.append({"role": "user", "content": message})

            # Call via unified gateway
            from services.llm_gateway import llm_gateway
            llm_result = llm_gateway.complete_sync(
                intent="customer",
                system_prompt=generate_system_prompt(context),
                messages=messages,
                max_tokens_override=500,
            )

            return {
                "message": llm_result.text,
                "suggestions": _generate_suggestions(context, message),
                "actions": _generate_actions(context, message),
                "sources": []
            }
    except Exception as e:
        logger.warning(f"Claude API not available, using rule-based response: {e}")

    # Fallback to rule-based responses
    return _generate_rule_based_response(message, context)


def _generate_suggestions(context: Dict[str, Any], message: str) -> List[str]:
    """Generate follow-up suggestions based on context."""
    suggestions = []

    app_completeness = context.get("application", {}).get("completeness_pct", 100)
    pending_docs = context.get("documents", {}).get("pending", 0)
    pending_tasks = context.get("pending_tasks", 0)

    if app_completeness < 100:
        suggestions.append("How do I complete my application?")

    if pending_docs > 0:
        suggestions.append("What's the status of my documents?")

    if pending_tasks > 0:
        suggestions.append("What tasks do I need to complete?")

    suggestions.extend([
        "What documents do I need?",
        "How long will this process take?",
        "Can I speak with my loan officer?"
    ])

    return suggestions[:4]


def _generate_actions(context: Dict[str, Any], message: str) -> List[Dict[str, Any]]:
    """Generate suggested actions based on context and message."""
    actions = []

    message_lower = message.lower()

    if any(word in message_lower for word in ["document", "upload", "file"]):
        actions.append({
            "type": "navigate",
            "label": "Go to Documents",
            "target": "/portal/documents"
        })

    if any(word in message_lower for word in ["application", "form", "complete"]):
        if context.get("application", {}).get("completeness_pct", 100) < 100:
            actions.append({
                "type": "navigate",
                "label": "Continue Application",
                "target": "/portal/application"
            })

    if any(word in message_lower for word in ["task", "todo", "do"]):
        actions.append({
            "type": "navigate",
            "label": "View Tasks",
            "target": "/portal/tasks"
        })

    if any(word in message_lower for word in ["contact", "call", "speak", "loan officer"]):
        actions.append({
            "type": "contact",
            "label": "Contact Loan Officer",
            "target": "loan_officer"
        })

    return actions


def _generate_rule_based_response(message: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a rule-based response when AI is not available."""
    message_lower = message.lower()

    # Document-related queries
    if any(word in message_lower for word in ["document", "upload", "file", "paperwork"]):
        pending = context.get("documents", {}).get("pending", 0)
        approved = context.get("documents", {}).get("approved", 0)

        if "status" in message_lower or "where" in message_lower:
            response = f"You have {approved} approved documents and {pending} documents pending review. "
            if pending > 0:
                response += "Our team is reviewing your pending documents and will update you soon."
            else:
                response += "All your submitted documents have been reviewed."
        else:
            response = """To upload documents:
1. Go to the Documents section
2. Click 'Upload Document'
3. Select the document type
4. Choose your file and upload

Supported formats: PDF, JPG, PNG. Make sure documents are clear and complete."""

    # Application-related queries
    elif any(word in message_lower for word in ["application", "form", "complete", "finish"]):
        completeness = context.get("application", {}).get("completeness_pct", 0)
        status = context.get("application", {}).get("status", "not_started")

        if status == "submitted":
            response = "Your application has been submitted and is being reviewed by our team. We'll notify you of any updates."
        elif completeness < 100:
            response = f"Your application is {completeness}% complete. Click 'Continue Application' to finish the remaining sections."
        else:
            response = "Your application is complete! Review your information and submit when ready."

    # Timeline/status queries
    elif any(word in message_lower for word in ["long", "time", "when", "timeline", "how long"]):
        response = """The mortgage process typically takes 30-45 days from application to closing. Here's a general timeline:

1. Application & Document Collection: 1-2 weeks
2. Processing & Underwriting: 2-3 weeks
3. Approval & Clear to Close: 1 week
4. Closing: Final step!

Your actual timeline may vary. Check your milestones for personalized progress."""

    # Task-related queries
    elif any(word in message_lower for word in ["task", "todo", "do", "next"]):
        pending_tasks = context.get("pending_tasks", 0)
        if pending_tasks > 0:
            response = f"You have {pending_tasks} pending task(s) that need your attention. Check the Tasks section to see what's needed and complete them to keep your loan moving forward."
        else:
            response = "Great news! You don't have any pending tasks right now. We'll notify you when there's something that needs your attention."

    # Contact/help queries
    elif any(word in message_lower for word in ["contact", "call", "help", "speak", "talk", "loan officer"]):
        response = """You can reach your loan team in several ways:

1. Send a message through the portal (Messages section)
2. Call your loan officer directly
3. Email us at support@perennia.ai

For urgent matters, please call. For general questions, sending a message through the portal is usually fastest."""

    # Greeting
    elif any(word in message_lower for word in ["hello", "hi", "hey", "good morning", "good afternoon"]):
        display_name = context.get("workspace", {}).get("display_name", "there")
        response = f"Hello! I'm your AI assistant and I'm here to help you through the loan process. How can I assist you today?"

    # Default response
    else:
        response = """I'm here to help with your mortgage loan process! I can assist with:

- Document uploads and status
- Application progress
- Task completion
- Timeline and process questions
- Connecting you with your loan officer

What would you like to know?"""

    return {
        "message": response,
        "suggestions": _generate_suggestions(context, message),
        "actions": _generate_actions(context, message),
        "sources": []
    }


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(
    request: ChatRequest,
    http_request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Chat with the AI assistant.

    Provides contextual help based on the borrower's workspace status,
    application progress, and document needs.
    """
    # Validate portal session — caller must have access to this workspace
    from routes.portal_auth_routes import validate_portal_session
    session = await validate_portal_session(http_request, db) if http_request else None
    if not session or session.get("workspace_id") != request.workspace_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Get workspace context
    context = await get_workspace_context(db, request.workspace_id)

    if not context:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Merge only safe keys from request context (prevent overwriting system context)
    _MERGEABLE_CONTEXT_KEYS = {'custom_message', 'user_preference', 'locale'}
    if request.context:
        for key in _MERGEABLE_CONTEXT_KEYS:
            if key in request.context:
                context[key] = request.context[key]

    # Generate response
    response = await generate_ai_response(
        message=request.message,
        context=context,
        conversation_history=request.conversation_history,
        db=db
    )

    # Log the interaction
    try:
        db.execute(text("""
            INSERT INTO purl_audit_log (
                organization_id, workspace_id, action, actor_type,
                metadata, created_at
            ) VALUES (
                (SELECT organization_id FROM purl_workspaces WHERE id = :workspace_id),
                :workspace_id, 'ai_chat', 'contact',
                :metadata, NOW()
            )
        """), {
            "workspace_id": request.workspace_id,
            "metadata": {
                "message_length": len(request.message),
                "response_length": len(response["message"]),
                "suggestions_count": len(response.get("suggestions", [])),
            }
        })
        db.commit()
    except SQLAlchemyError as e:
        logger.warning(f"Failed to log AI chat interaction: {e}")

    return ChatResponse(**response)


@router.get("/quick-actions/{workspace_id}")
async def get_quick_actions(
    workspace_id: int = Path(..., description="Workspace ID"),
    http_request: Request = None,
    db: Session = Depends(get_db)
) -> List[QuickAction]:
    """
    Get contextual quick actions for the workspace.

    Returns a list of suggested actions based on the current
    state of the application, documents, and tasks.
    """
    # Validate portal session
    from routes.portal_auth_routes import validate_portal_session
    session = await validate_portal_session(http_request, db) if http_request else None
    if not session or session.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    context = await get_workspace_context(db, workspace_id)

    if not context:
        raise HTTPException(status_code=404, detail="Workspace not found")

    actions = []

    # Application actions
    app = context.get("application", {})
    if app.get("completeness_pct", 100) < 100:
        actions.append(QuickAction(
            action_type="continue_application",
            label="Continue Application",
            description=f"Your application is {app.get('completeness_pct', 0)}% complete",
            params={"target": "/portal/application"}
        ))
    elif not app.get("submitted"):
        actions.append(QuickAction(
            action_type="submit_application",
            label="Submit Application",
            description="Your application is ready to submit",
            params={"target": "/portal/application/review"}
        ))

    # Document actions
    docs = context.get("documents", {})
    if docs.get("rejected", 0) > 0:
        actions.append(QuickAction(
            action_type="reupload_documents",
            label="Reupload Documents",
            description=f"{docs['rejected']} document(s) need to be resubmitted",
            params={"target": "/portal/documents?filter=rejected"}
        ))

    # Task actions
    if context.get("pending_tasks", 0) > 0:
        actions.append(QuickAction(
            action_type="complete_tasks",
            label="Complete Tasks",
            description=f"{context['pending_tasks']} task(s) awaiting completion",
            params={"target": "/portal/tasks"}
        ))

    # Upload action (always available)
    actions.append(QuickAction(
        action_type="upload_document",
        label="Upload Document",
        description="Submit required documents",
        params={"target": "/portal/documents/upload"}
    ))

    # Contact action (always available)
    actions.append(QuickAction(
        action_type="contact_team",
        label="Message Loan Team",
        description="Send a message to your loan officer",
        params={"target": "/portal/messages/new"}
    ))

    return actions[:5]  # Return top 5 actions


@router.get("/faq")
async def get_faq() -> List[Dict[str, str]]:
    """
    Get frequently asked questions for the portal.

    Returns common questions and answers about the loan process.
    """
    return [
        {
            "question": "What documents do I need to provide?",
            "answer": "Common documents include: 2 months of pay stubs, 2 years of W-2s or tax returns, 2 months of bank statements, and a valid ID. Your specific requirements may vary based on your loan type."
        },
        {
            "question": "How long does the loan process take?",
            "answer": "A typical mortgage takes 30-45 days from application to closing. The timeline can vary based on document collection, property appraisal, and underwriting review."
        },
        {
            "question": "Why was my document rejected?",
            "answer": "Documents may be rejected if they're unclear, incomplete, or don't meet requirements. Check the rejection reason in your Documents section and upload a new version that addresses the issue."
        },
        {
            "question": "Can I make changes after submitting my application?",
            "answer": "Yes, you can update certain information after submission. Contact your loan officer to discuss any changes needed to your application."
        },
        {
            "question": "What is the difference between pre-approval and approval?",
            "answer": "Pre-approval is a preliminary check based on your finances. Final approval comes after underwriting reviews your complete application, documents, and property details."
        },
        {
            "question": "How do I know what's needed next?",
            "answer": "Check your Tasks section for pending items, and your Documents section for any missing or rejected documents. The portal will notify you of new requirements."
        },
        {
            "question": "Is my information secure?",
            "answer": "Yes, we use bank-level encryption to protect your data. All documents and personal information are stored securely and only accessible to your loan team."
        },
        {
            "question": "Who can I contact if I have questions?",
            "answer": "You can send a message through the portal, or contact your loan officer directly. For urgent matters, please call the number provided in your welcome email."
        }
    ]


@router.get("/tips/{workspace_id}")
async def get_contextual_tips(
    workspace_id: int = Path(..., description="Workspace ID"),
    db: Session = Depends(get_db)
) -> List[Dict[str, str]]:
    """
    Get contextual tips based on current workspace state.

    Returns helpful tips relevant to the borrower's current stage.
    """
    context = await get_workspace_context(db, workspace_id)

    if not context:
        raise HTTPException(status_code=404, detail="Workspace not found")

    tips = []

    # Application-stage tips
    app = context.get("application", {})
    if app.get("completeness_pct", 100) < 50:
        tips.append({
            "title": "Complete Your Application",
            "tip": "Finishing your application early helps us process your loan faster. Set aside 20-30 minutes to complete the remaining sections."
        })

    if app.get("has_errors"):
        tips.append({
            "title": "Review Application Errors",
            "tip": "There are some issues with your application that need attention. Review the highlighted fields and make corrections."
        })

    # Document tips
    docs = context.get("documents", {})
    if docs.get("pending", 0) > 0:
        tips.append({
            "title": "Documents Under Review",
            "tip": "Our team is reviewing your documents. This typically takes 1-2 business days. You'll be notified of any issues."
        })

    if docs.get("rejected", 0) > 0:
        tips.append({
            "title": "Documents Need Attention",
            "tip": "Some documents were rejected. Check the Documents section for details and upload corrected versions."
        })

    # General tips
    tips.extend([
        {
            "title": "Upload Clear Documents",
            "tip": "Ensure documents are complete, all pages included, and text is readable. This prevents delays from rejections."
        },
        {
            "title": "Stay Responsive",
            "tip": "Quick responses to requests help keep your loan on track. Enable notifications to stay updated."
        }
    ])

    return tips[:4]


@router.post("/feedback")
async def submit_assistant_feedback(
    workspace_id: int,
    message_id: Optional[str] = None,
    rating: int = Query(..., ge=1, le=5),
    feedback: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Submit feedback about the AI assistant.

    Helps improve the assistant's responses over time.
    """
    try:
        db.execute(text("""
            INSERT INTO purl_audit_log (
                organization_id, workspace_id, action, actor_type,
                metadata, created_at
            ) VALUES (
                (SELECT organization_id FROM purl_workspaces WHERE id = :workspace_id),
                :workspace_id, 'ai_feedback', 'contact',
                :metadata, NOW()
            )
        """), {
            "workspace_id": workspace_id,
            "metadata": {
                "message_id": message_id,
                "rating": rating,
                "feedback": feedback
            }
        })
        db.commit()

        return {"success": True, "message": "Thank you for your feedback!"}

    except SQLAlchemyError as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit feedback")
