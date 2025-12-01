"""
AI Email Search API Routes
REST endpoints for AI agents to search and analyze emails.
"""

import logging
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai/emails", tags=["AI Email Search"])


# =============================================================================
# Dependencies
# =============================================================================

from database import get_db


def get_current_user_dep():
    """Get current user - imports from main at runtime to avoid circular imports"""
    import main
    return main.get_current_user


# =============================================================================
# Request models
# =============================================================================

class SearchByClientRequest(BaseModel):
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    client_id: Optional[int] = None
    days: int = 30
    limit: int = 20


class SearchByContentRequest(BaseModel):
    keywords: str
    days: int = 30
    limit: int = 20


class IdentifyEmailRequest(BaseModel):
    email_address: str


class GetThreadRequest(BaseModel):
    email_id: Optional[int] = None
    thread_id: Optional[str] = None


class PriorityEmailsRequest(BaseModel):
    days: int = 7
    limit: int = 20


class EmailContextRequest(BaseModel):
    email_id: int


class NaturalLanguageQueryRequest(BaseModel):
    query: str
    max_results: int = 20


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/search/by-client")
async def search_emails_by_client(
    request: SearchByClientRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """
    Search emails from a specific client.

    AI agents use this to find emails from clients by:
    - Name (partial match)
    - Email address (exact match)
    - CRM ID (lead_id or loan_id)
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        result = tools.search_emails_by_client(
            client_name=request.client_name,
            client_email=request.client_email,
            client_id=request.client_id,
            days=request.days,
            limit=request.limit
        )
        return result
    except Exception as e:
        logger.error(f"Error in search by client: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/by-content")
async def search_emails_by_content(
    request: SearchByContentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """
    Search emails by keywords in subject and body.

    AI agents use this to find emails containing specific terms
    like "documents", "appraisal", "closing", etc.
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        result = tools.search_emails_by_content(
            keywords=request.keywords,
            days=request.days,
            limit=request.limit
        )
        return result
    except Exception as e:
        logger.error(f"Error in search by content: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/identify")
async def identify_email_sender(
    request: IdentifyEmailRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """
    Identify who an email address belongs to.

    AI agents use this to determine:
    - If sender is a known client
    - Associated lead/loan in CRM
    - Priority status
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        result = tools.identify_email_sender(request.email_address)
        return result
    except Exception as e:
        logger.error(f"Error identifying sender: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thread")
async def get_email_thread(
    request: GetThreadRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """
    Get complete email conversation thread.

    AI agents use this to understand conversation history
    and context before responding.
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/priority")
async def get_priority_emails(
    request: PriorityEmailsRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """
    Get priority emails that need attention.

    AI agents use this for:
    - Morning briefings
    - "What needs my attention?" queries
    - Task prioritization
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        result = tools.get_priority_emails(
            days=request.days,
            limit=request.limit
        )
        return result
    except Exception as e:
        logger.error(f"Error getting priority emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context")
async def get_email_context(
    request: EmailContextRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """
    Get complete context for an email.

    AI agents use this before making decisions about:
    - How to respond
    - What actions to recommend
    - Priority assessment
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        result = tools.get_email_context_for_ai(request.email_id)
        return result
    except Exception as e:
        logger.error(f"Error getting email context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query")
async def natural_language_query(
    request: NaturalLanguageQueryRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """
    Process natural language email queries.

    Parses queries like:
    - "Show me emails from John"
    - "Find urgent emails"
    - "What did Jane send about the appraisal?"

    Returns appropriate results based on query intent.
    """
    try:
        from email_identity_ai_tools import EmailSearchTools

        tools = EmailSearchTools(db, current_user.id)
        query = request.query.lower()

        # Simple intent detection
        if any(word in query for word in ["urgent", "priority", "attention", "important"]):
            return tools.get_priority_emails(days=7, limit=request.max_results)

        if any(word in query for word in ["from", "sent by"]):
            # Extract potential name/email
            email_match = re.search(r'[\w\.-]+@[\w\.-]+', query)
            if email_match:
                return tools.search_emails_by_client(
                    client_email=email_match.group(),
                    limit=request.max_results
                )

            # Try to extract name (words after "from")
            name_match = re.search(r'from\s+([a-zA-Z\s]+?)(?:\s+about|\s+regarding|$)', query)
            if name_match:
                name = name_match.group(1).strip()
                return tools.search_emails_by_client(
                    client_name=name,
                    limit=request.max_results
                )

        if any(word in query for word in ["about", "regarding", "mention", "contains"]):
            # Content search - extract keywords
            # Remove common words
            stop_words = {"about", "regarding", "emails", "email", "find", "show", "me", "the", "any"}
            words = [w for w in query.split() if w not in stop_words]
            keywords = " ".join(words[-3:])  # Use last few words as search
            return tools.search_emails_by_content(
                keywords=keywords,
                limit=request.max_results
            )

        # Default: content search with full query
        return tools.search_emails_by_content(
            keywords=request.query,
            limit=request.max_results
        )

    except Exception as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/morning-briefing")
async def morning_briefing(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """
    Get morning email briefing.

    Returns:
    - Priority emails from last 24 hours
    - Recommended action items
    - Text summary for AI to read
    """
    try:
        from email_identity_ai_tools import get_morning_briefing

        briefing = get_morning_briefing(db, current_user.id)
        return briefing
    except Exception as e:
        logger.error(f"Error generating briefing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_email_stats(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """
    Get email statistics for dashboard.

    Returns counts by:
    - Status (pending, matched, archived)
    - Priority
    - Match method
    """
    try:
        stats_query = text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'matched' THEN 1 END) as matched,
                COUNT(CASE WHEN status = 'archived' THEN 1 END) as archived,
                COUNT(CASE WHEN is_priority = TRUE THEN 1 END) as priority,
                COUNT(CASE WHEN match_method = 'known_client' THEN 1 END) as known_client_matches,
                COUNT(CASE WHEN match_method = 'lead_email' THEN 1 END) as lead_matches,
                COUNT(CASE WHEN match_method = 'loan_email' THEN 1 END) as loan_matches,
                AVG(match_confidence) as avg_confidence
            FROM email_reconciliation_queue
            WHERE received_date > NOW() - INTERVAL :days_val
        """)

        result = db.execute(stats_query, {"days_val": f"{days} days"}).fetchone()

        return {
            "period_days": days,
            "total_emails": result.total if result and result.total else 0,
            "by_status": {
                "pending": result.pending if result and result.pending else 0,
                "matched": result.matched if result and result.matched else 0,
                "archived": result.archived if result and result.archived else 0
            },
            "priority_count": result.priority if result and result.priority else 0,
            "by_match_method": {
                "known_client": result.known_client_matches if result and result.known_client_matches else 0,
                "lead": result.lead_matches if result and result.lead_matches else 0,
                "loan": result.loan_matches if result and result.loan_matches else 0
            },
            "avg_match_confidence": round(float(result.avg_confidence or 0), 2) if result else 0.0
        }

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
