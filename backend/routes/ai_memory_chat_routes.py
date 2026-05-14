"""
AI Memory and Smart Chat Routes
Enhanced AI chat with conversation memory, context retrieval, and email functionality
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import logging
import os
from routes.auth_deps import current_user_dep, current_user_flexible_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'Lead': main.Lead,
        'Loan': main.Loan,
        'Task': main.Task,
        'LeadStage': main.LeadStage,
        'LoanStage': main.LoanStage,
        'ConversationMemory': main.ConversationMemory,
    }


def get_db_dep():
    """Get database dependency at runtime"""
    from db import get_db
    return get_db


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user_flexible


def get_current_user_strict():
    """Get strict current user dependency"""
    import main
    return main.get_current_user


def get_log_ai_action():
    """Get AI action logging function"""
    import main
    return main.log_ai_action_to_mission_control


def get_update_ai_action():
    """Get AI action update function"""
    import main
    return main.update_ai_action_outcome


async def _get_coaching_context(db: Session, user_id: int) -> str:
    """Fetch CRM data for coaching context - optimized with database filtering"""
    models = get_models()
    Lead = models['Lead']
    Loan = models['Loan']
    Task = models['Task']
    LeadStage = models['LeadStage']
    LoanStage = models['LoanStage']

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    ten_days_ago = now - timedelta(days=10)
    today = now.date()

    context_parts = []

    # Get leads stats with database COUNT queries
    total_leads = db.query(func.count(Lead.id)).filter(Lead.owner_id == user_id).scalar() or 0
    new_leads_count = db.query(func.count(Lead.id)).filter(
        Lead.owner_id == user_id,
        Lead.created_at >= yesterday
    ).scalar() or 0
    pending_leads_count = db.query(func.count(Lead.id)).filter(
        Lead.owner_id == user_id,
        Lead.stage.in_([LeadStage.NEW, LeadStage.ATTEMPTED_CONTACT, LeadStage.PROSPECT])
    ).scalar() or 0

    context_parts.append(f"## LEADS DATA:")
    context_parts.append(f"- Total leads: {total_leads}")
    context_parts.append(f"- New leads (last 24h): {new_leads_count}")
    context_parts.append(f"- Pending follow-up: {pending_leads_count}")

    # Get loans stats
    total_loans = db.query(func.count(Loan.id)).filter(Loan.loan_officer_id == user_id).scalar() or 0
    active_loans_count = db.query(func.count(Loan.id)).filter(
        Loan.loan_officer_id == user_id,
        Loan.stage != LoanStage.FUNDED
    ).scalar() or 0

    stuck_loans = db.query(Loan).filter(
        Loan.loan_officer_id == user_id,
        Loan.stage != LoanStage.FUNDED,
        Loan.updated_at <= ten_days_ago
    ).limit(5).all()

    context_parts.append(f"\n## PIPELINE DATA:")
    context_parts.append(f"- Total loans: {total_loans}")
    context_parts.append(f"- Active in pipeline: {active_loans_count}")
    context_parts.append(f"- Stalled (10+ days): {len(stuck_loans)}")

    if stuck_loans:
        context_parts.append(f"\nStalled deals:")
        for loan in stuck_loans:
            days_stuck = (now - loan.updated_at).days if loan.updated_at else 0
            context_parts.append(f"  - {loan.borrower_name}: {str(loan.stage)} ({days_stuck} days)")

    # Get tasks stats
    total_tasks = db.query(func.count(Task.id)).filter(Task.owner_id == user_id).scalar() or 0
    overdue_count = db.query(func.count(Task.id)).filter(
        Task.owner_id == user_id,
        Task.due_date < today,
        Task.status != 'completed'
    ).scalar() or 0
    today_count = db.query(func.count(Task.id)).filter(
        Task.owner_id == user_id,
        func.date(Task.due_date) == today,
        Task.status != 'completed'
    ).scalar() or 0

    context_parts.append(f"\n## TASKS DATA:")
    context_parts.append(f"- Total tasks: {total_tasks}")
    context_parts.append(f"- Overdue: {overdue_count}")
    context_parts.append(f"- Due today: {today_count}")

    return "\n".join(context_parts)


@router.post("/ai/smart-chat")
async def smart_chat_with_memory(
    request: Request,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """
    Enhanced AI chat with conversation memory and context retrieval
    Uses RAG (Retrieval-Augmented Generation) for personalized responses
    """
    log_ai_action = get_log_ai_action()
    update_ai_action = get_update_ai_action()
    action_id = None

    try:
        data = await request.json()
        raw_message = data.get("message", "")
        lead_id = data.get("lead_id")
        loan_id = data.get("loan_id")
        include_context = data.get("include_context", True)
        coaching_mode = data.get("coaching_mode")
        context_type = data.get("context_type")
        user_context = data.get("user_context", {})

        # Sanitize user message to mitigate prompt injection
        try:
            from input_validation import sanitize_chat_input
            message = sanitize_chat_input(raw_message)
        except ImportError:
            message = raw_message.strip()[:4000] if raw_message else ""

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        # Build coaching context
        coaching_context = None
        if coaching_mode or context_type == "coaching":
            if user_context:
                context_parts = []
                if user_context.get("profile"):
                    p = user_context["profile"]
                    context_parts.append(f"## Your Profile Summary")
                    context_parts.append(f"Pipeline: {p.get('pipeline_summary', 'N/A')}")
                    context_parts.append(f"Active Leads: {p.get('total_active_leads', 0)}")
                    context_parts.append(f"Funded Loans: {p.get('funded_this_month', 0)} this month")
                    if p.get('tasks'):
                        context_parts.append(f"Tasks: {p['tasks'].get('pending', 0)} pending, {p['tasks'].get('overdue', 0)} overdue")

                if user_context.get("tasks") and user_context["tasks"].get("tasks"):
                    context_parts.append(f"\n## Your Tasks ({len(user_context['tasks']['tasks'])} items)")
                    for task in user_context["tasks"]["tasks"][:10]:
                        status = "🔴 OVERDUE" if task.get("is_overdue") else "⏰ Due"
                        context_parts.append(f"- {task.get('title', 'Untitled')}: {status} {task.get('due_date', 'No date')}")

                if user_context.get("pipeline") and user_context["pipeline"].get("stages"):
                    context_parts.append(f"\n## Your Pipeline")
                    for stage in user_context["pipeline"]["stages"]:
                        context_parts.append(f"- {stage.get('name', 'Unknown')}: {stage.get('count', 0)} leads (${stage.get('value', 0):,.0f})")

                coaching_context = "\n".join(context_parts)
            else:
                coaching_context = await _get_coaching_context(db, current_user.id)

        # Log to Mission Control
        action_id = await log_ai_action(
            db=db,
            agent_name="Smart AI Chat",
            action_type="conversation",
            lead_id=lead_id,
            loan_id=loan_id,
            user_id=current_user.id,
            context={"message": message[:100], "include_context": include_context},
            autonomy_level="assisted",
            status="pending"
        )

        try:
            from services.ai_memory_service import context_ai

            result = await context_ai.get_intelligent_response(
                db=db,
                user_id=current_user.id,
                current_message=message,
                lead_id=lead_id,
                loan_id=loan_id,
                include_context=include_context,
                coaching_context=coaching_context
            )

            if action_id:
                await update_ai_action(
                    db=db,
                    action_id=action_id,
                    outcome="success",
                    impact_score=0.7,
                    metadata={
                        "context_used": result.get("context_used", False),
                        "context_count": result.get("context_count", 0),
                        "has_memory": result.get("has_memory", False)
                    }
                )

            return {
                "success": True,
                "response": result.get("response"),
                "context_used": result.get("context_used", False),
                "context_count": result.get("context_count", 0),
                "has_memory": result.get("has_memory", False),
                "metadata": result.get("metadata", {})
            }

        except Exception as ai_error:
            logger.error(f"AI response failed: {ai_error}")

            if action_id:
                await update_ai_action(
                    db=db,
                    action_id=action_id,
                    outcome="failure",
                    impact_score=0.0,
                    metadata={"error": str(ai_error)}
                )

            return {
                "success": False,
                "response": "I apologize, but I'm having trouble right now. Please try again.",
                "error": str(ai_error)
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in smart chat: {e}")

        if action_id:
            try:
                await update_ai_action(
                    db=db,
                    action_id=action_id,
                    outcome="failure",
                    impact_score=0.0,
                    metadata={"error": "Internal server error"}
                )
            except Exception as e:
                logger.error(f"Error updating AI action on failure: {e}")

        return {
            "success": False,
            "response": "I apologize, but I'm having trouble right now. Please try again.",
            "error": "Internal server error"
        }


@router.get("/ai/memory-stats")
async def get_memory_stats(
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """Get AI memory statistics for the current user"""
    models = get_models()
    ConversationMemory = models['ConversationMemory']

    try:
        from integrations.pinecone_service import vector_memory

        memory_count = db.query(ConversationMemory).filter(
            ConversationMemory.user_id == current_user.id
        ).count()

        vector_count = 0
        if vector_memory.enabled:
            vector_count = await vector_memory.get_conversation_count(current_user.id)

        top_memories = db.query(ConversationMemory).filter(
            ConversationMemory.user_id == current_user.id
        ).order_by(
            ConversationMemory.access_count.desc()
        ).limit(5).all()

        return {
            "total_memories": memory_count,
            "vector_count": vector_count,
            "memory_enabled": vector_memory.enabled,
            "top_memories": [{
                "summary": m.conversation_summary[:100],
                "access_count": m.access_count,
                "last_accessed": m.last_accessed_at.isoformat() if m.last_accessed_at else None,
                "sentiment": m.sentiment
            } for m in top_memories]
        }

    except Exception as e:
        logger.error(f"Error getting memory stats: {e}")
        return {
            "total_memories": 0,
            "vector_count": 0,
            "memory_enabled": False,
            "error": "Internal server error"
        }


@router.post("/ai/send-task-summary-email")
async def send_task_summary_email(
    request: Request,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """Send an email to the user with their task summary for today or tomorrow"""
    try:
        data = await request.json()
        timeframe = data.get("timeframe", "today")
        tasks = data.get("tasks", [])

        user_email = current_user.email
        user_name = current_user.full_name or user_email.split('@')[0]

        if not tasks:
            task_list = "No tasks scheduled - great job staying ahead!"
        else:
            task_list = "\n".join([
                f"• {task.get('title', task.get('description', 'Untitled task'))}"
                + (f" - Due: {task.get('due_date', 'No date')}" if task.get('due_date') else "")
                for task in tasks[:20]
            ])
            if len(tasks) > 20:
                task_list += f"\n\n...and {len(tasks) - 20} more tasks"

        subject = f"Your Task Summary for {timeframe.title()}"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2c3e50;">Hi {user_name},</h2>
            <p>Here's your task summary for <strong>{timeframe}</strong>:</p>
            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0;">
                <h3 style="color: #495057; margin-top: 0;">Tasks ({len(tasks)} items)</h3>
                <pre style="white-space: pre-wrap; font-family: Arial, sans-serif; margin: 0;">{task_list}</pre>
            </div>
            <p style="color: #6c757d; font-size: 12px;">
                Sent from your Mortgage CRM AI Assistant
            </p>
        </body>
        </html>
        """

        # Try Microsoft Graph
        try:
            from integrations.microsoft_graph import graph_client
            if graph_client and hasattr(graph_client, 'send_email'):
                await graph_client.send_email(
                    to_email=user_email,
                    subject=subject,
                    body=html_content,
                    is_html=True
                )
                logger.info(f"Task summary email sent to {user_email}")
                return {"success": True, "message": f"Email sent to {user_email}"}
        except Exception as e:
            logger.warning(f"Microsoft Graph email failed: {e}")

        # Try SendGrid
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail, Email, To, Content

            sg_api_key = os.getenv("SENDGRID_API_KEY")
            if sg_api_key:
                sg = sendgrid.SendGridAPIClient(api_key=sg_api_key)
                message = Mail(
                    from_email=Email(os.getenv("SENDGRID_FROM_EMAIL", "noreply@mortgagecrm.com")),
                    to_emails=To(user_email),
                    subject=subject,
                    html_content=Content("text/html", html_content)
                )
                sg.send(message)
                logger.info(f"Task summary email sent via SendGrid to {user_email}")
                return {"success": True, "message": f"Email sent to {user_email}"}
        except Exception as e:
            logger.warning(f"SendGrid email failed: {e}")

        return {"success": False, "message": "Email service not configured"}

    except Exception as e:
        logger.error(f"Error sending task summary email: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


class GenericEmailRequest(BaseModel):
    """Request model for generic email sending"""
    to_email: str
    subject: str
    body_html: str
    body_text: Optional[str] = None


@router.post("/email/send")
async def send_generic_email(
    request: GenericEmailRequest,
    current_user = Depends(current_user_dep)
):
    """Send a generic email using the email service (SendGrid/SMTP)."""
    try:
        from email_service import email_service
        import re

        plain_text = request.body_text
        if not plain_text:
            plain_text = re.sub('<[^<]+?>', '', request.body_html)

        success = email_service.send_html_email(
            to_email=request.to_email,
            subject=request.subject,
            html_body=request.body_html,
            plain_text_body=plain_text
        )

        if success:
            logger.info(f"Email sent successfully to {request.to_email}")
            return {
                "success": True,
                "message": f"Email sent to {request.to_email}",
                "recipient": request.to_email,
                "subject": request.subject
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to send email - check email service configuration"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def set_dependencies(get_db_func, get_current_user_func):
    """Set dependencies for this router"""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func
