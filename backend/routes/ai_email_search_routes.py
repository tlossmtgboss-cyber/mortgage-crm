"""
AI Email Search API Routes
Perennia AI - IBMA

RESTful API endpoints that expose email identity resolution tools
for AI agents and external integrations.
"""

import os
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai/emails", tags=["AI Email Search"])
security = HTTPBearer(auto_error=False)


# ================================================================
# AUTH HELPER
# ================================================================

class UserProxy:
    """Simple user proxy for auth."""
    def __init__(self, row):
        self.id = row[0]
        self.email = row[1]
        self.name = row[2] if len(row) > 2 else None


from auth.dependencies import get_current_user  # dedup: was local wrapper
# ================================================================
# REQUEST/RESPONSE MODELS
# ================================================================

class SearchEmailsByClientRequest(BaseModel):
    client_name: Optional[str] = Field(None, description="Client's name (fuzzy match)")
    client_email: Optional[str] = Field(None, description="Exact email address")
    loan_id: Optional[int] = Field(None, description="Specific loan ID")
    lead_id: Optional[int] = Field(None, description="Specific lead ID")
    days: int = Field(30, description="Days to look back", ge=1, le=365)
    include_unread_only: bool = Field(False, description="Only unread emails")
    limit: int = Field(20, description="Max results", ge=1, le=100)


class SearchEmailsByContentRequest(BaseModel):
    search_query: Optional[str] = Field(None, description="Text to search for")
    keywords: Optional[str] = Field(None, description="Alias for search_query")
    search_in: Literal["subject", "body", "both"] = Field("both", description="Where to search")
    days: int = Field(30, description="Days to look back", ge=1, le=365)
    limit: int = Field(20, description="Max results", ge=1, le=100)


class IdentifyEmailSenderRequest(BaseModel):
    email_address: str = Field(..., description="Email address to identify")


class EmailThreadRequest(BaseModel):
    email_id: Optional[int] = Field(None, description="Email ID to get thread for")
    thread_id: Optional[str] = Field(None, description="Thread ID to retrieve")


class PriorityEmailsRequest(BaseModel):
    days: int = Field(7, description="Days to look back", ge=1, le=30)
    unread_only: bool = Field(True, description="Only unread emails")
    limit: int = Field(20, description="Max results", ge=1, le=100)


class EmailContextRequest(BaseModel):
    email_id: int = Field(..., description="Email ID to get context for")


class NaturalLanguageQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language question about emails")
    max_results: int = Field(20, description="Maximum results", ge=1, le=100)


# ================================================================
# API ENDPOINTS
# ================================================================

@router.post("/search/by-client")
async def search_emails_by_client(
    request: SearchEmailsByClientRequest,
    db: Session = Depends(get_db),
    current_user: UserProxy = Depends(get_current_user)
):
    """
    Search for emails related to a specific client.

    **AI Use Cases:**
    - "Show me recent emails from John Doe"
    - "What emails did we receive about loan #123456?"
    - "Find unread emails from sarah@example.com"
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        result = tools.search_emails_by_client(
            client_name=request.client_name,
            client_email=request.client_email,
            loan_id=request.loan_id,
            lead_id=request.lead_id,
            days=request.days,
            include_unread_only=request.include_unread_only,
            limit=request.limit
        )
        return result

    except Exception as e:
        logger.error(f"Error in search by client: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/search/by-content")
async def search_emails_by_content(
    request: SearchEmailsByContentRequest,
    db: Session = Depends(get_db),
    current_user: UserProxy = Depends(get_current_user)
):
    """
    Search emails by subject or body content.

    **AI Use Cases:**
    - "Find emails mentioning 'appraisal'"
    - "Search for emails about closing dates"
    - "Show emails containing 'urgent'"
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        result = tools.search_emails_by_content(
            search_query=request.search_query,
            keywords=request.keywords,
            search_in=request.search_in,
            days=request.days,
            limit=request.limit
        )
        return result

    except Exception as e:
        logger.error(f"Error in search by content: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/identify")
async def identify_email_sender(
    request: IdentifyEmailSenderRequest,
    db: Session = Depends(get_db),
    current_user: UserProxy = Depends(get_current_user)
):
    """
    Identify who an email address belongs to in the CRM.

    **AI Use Cases:**
    - "Who is john@example.com?"
    - "Do we know this email address?"
    - "What client is associated with this email?"
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        result = tools.identify_email_sender(
            email_address=request.email_address
        )
        return result

    except Exception as e:
        logger.error(f"Error identifying sender: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/thread")
async def get_email_thread(
    request: EmailThreadRequest,
    db: Session = Depends(get_db),
    current_user: UserProxy = Depends(get_current_user)
):
    """
    Get complete email thread/conversation.

    **AI Use Cases:**
    - "Show me the full conversation with this client"
    - "What's the context around email #12345?"
    - "Get the email thread for this discussion"
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        result = tools.get_email_thread(
            email_id=request.email_id,
            thread_id=request.thread_id
        )
        return result

    except Exception as e:
        logger.error(f"Error getting thread: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/priority")
async def get_priority_emails(
    request: PriorityEmailsRequest,
    db: Session = Depends(get_db),
    current_user: UserProxy = Depends(get_current_user)
):
    """
    Get high-priority emails requiring immediate attention.

    **AI Use Cases:**
    - "What urgent emails do I have?"
    - "Show me priority items"
    - "What needs my attention today?"
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        result = tools.get_priority_emails(
            days=request.days,
            unread_only=request.unread_only,
            limit=request.limit
        )
        return result

    except Exception as e:
        logger.error(f"Error getting priority emails: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/context")
async def get_email_context(
    request: EmailContextRequest,
    db: Session = Depends(get_db),
    current_user: UserProxy = Depends(get_current_user)
):
    """
    Get complete context about an email for AI decision-making.

    Includes:
    - Email content
    - Thread history
    - Client CRM details
    - Recent interactions
    - AI-generated recommendations
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        result = tools.get_email_context_for_ai(
            email_id=request.email_id
        )
        return result

    except Exception as e:
        logger.error(f"Error getting email context: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/query")
async def natural_language_query(
    request: NaturalLanguageQueryRequest,
    db: Session = Depends(get_db),
    current_user: UserProxy = Depends(get_current_user)
):
    """
    Process natural language queries about emails.

    Uses simple pattern matching to route queries to appropriate tools.

    **Example Queries:**
    - "Show me emails from john"
    - "What's urgent today"
    - "Find emails about closing dates"
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        query_lower = request.query.lower()

        # Simple pattern matching
        if any(word in query_lower for word in ["urgent", "priority", "attention", "important"]):
            result = tools.get_priority_emails(limit=request.max_results)

        elif any(word in query_lower for word in ["from", "sent by"]):
            # Extract potential email
            email_match = re.search(r'[\w\.-]+@[\w\.-]+', request.query)
            if email_match:
                result = tools.search_emails_by_client(
                    client_email=email_match.group(),
                    limit=request.max_results
                )
            else:
                # Try to extract name
                name_match = re.search(r'from\s+([a-zA-Z\s]+?)(?:\s+about|\s+regarding|$)', query_lower)
                if name_match:
                    name = name_match.group(1).strip()
                    result = tools.search_emails_by_client(
                        client_name=name,
                        limit=request.max_results
                    )
                else:
                    result = {"success": False, "error": "Could not parse client name"}

        elif any(word in query_lower for word in ["about", "regarding", "mention", "contains"]):
            # Content search
            stop_words = {"about", "regarding", "emails", "email", "find", "show", "me", "the", "any", "mentioning", "containing"}
            words = [w for w in request.query.split() if w.lower() not in stop_words]
            keywords = " ".join(words[-3:]) if words else request.query
            result = tools.search_emails_by_content(
                search_query=keywords,
                limit=request.max_results
            )

        elif "@" in request.query:
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', request.query)
            if email_match:
                result = tools.identify_email_sender(email_match.group())
            else:
                result = {"success": False, "error": "Could not parse email address"}

        else:
            # Default: content search
            result = tools.search_emails_by_content(
                search_query=request.query,
                limit=request.max_results
            )

        return {
            "query": request.query,
            "result": result
        }

    except SQLAlchemyError as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ================================================================
# CONVENIENCE ENDPOINTS
# ================================================================

@router.get("/morning-briefing")
async def get_morning_briefing(
    db: Session = Depends(get_db),
    current_user: UserProxy = Depends(get_current_user)
):
    """
    Get morning briefing with priority emails and suggested actions.

    Returns:
    - Priority email count
    - Emails by category
    - Recommended actions
    - Summary
    """
    try:
        from email_identity_ai_tools import get_morning_briefing

        briefing = get_morning_briefing(db, current_user.id)
        return briefing

    except Exception as e:
        logger.error(f"Error generating briefing: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats")
async def get_email_stats(
    days: int = Query(7, description="Days to look back", ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: UserProxy = Depends(get_current_user)
):
    """
    Get email statistics for the AI agent to understand workload.

    Returns:
    - Total emails
    - Priority emails
    - Unread emails
    - Emails by disposition
    """
    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        stats = db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE is_priority = TRUE) as priority,
                COUNT(*) FILTER (WHERE status = 'pending') as unread,
                COUNT(*) FILTER (WHERE disposition = 'document_request') as doc_requests,
                COUNT(*) FILTER (WHERE disposition = 'action_required') as action_required,
                COUNT(*) FILTER (WHERE disposition = 'document_received') as docs_received
            FROM email_reconciliation_queue
            WHERE user_id = :user_id
              AND created_at >= :start_date
        """), {
            "user_id": current_user.id,
            "start_date": start_date
        }).fetchone()

        return {
            "period_days": days,
            "total_emails": stats[0] or 0,
            "priority_emails": stats[1] or 0,
            "unread_emails": stats[2] or 0,
            "document_requests": stats[3] or 0,
            "action_required": stats[4] or 0,
            "documents_received": stats[5] or 0
        }

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tools-schema")
async def get_tools_schema():
    """
    Get tool definitions in OpenAI function calling format.

    Useful for:
    - AI framework integration
    - Documentation
    - Tool discovery
    """
    from email_identity_ai_tools import get_openai_tools_format

    return {
        "tools": get_openai_tools_format(),
        "version": "1.0",
        "description": "AI email search tools for Perennia CRM"
    }


@router.get("/health")
async def health_check():
    """Health check endpoint for AI email search tools."""
    return {
        "status": "healthy",
        "service": "ai-email-search",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
