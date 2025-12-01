"""
Email Identity AI Tools
AI-accessible tools for email search and identity resolution.
Enables AI agents to intelligently search, analyze, and act on emails.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class EmailSearchTools:
    """
    AI-accessible email search tools.
    Provides 6 core search methods for AI agents.
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def search_emails_by_client(
        self,
        client_name: Optional[str] = None,
        client_email: Optional[str] = None,
        client_id: Optional[int] = None,
        days: int = 30,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Search emails from a specific client.

        Args:
            client_name: Client's name (partial match supported)
            client_email: Client's email address
            client_id: Lead or loan ID
            days: Number of days to search back
            limit: Maximum results to return

        Returns:
            Dict with emails, count, and AI-friendly summary
        """
        try:
            conditions = ["1=1"]
            params = {"days": days, "limit": limit}

            if client_email:
                conditions.append("LOWER(from_email) = LOWER(:email)")
                params["email"] = client_email

            if client_name:
                conditions.append("LOWER(from_name) LIKE LOWER(:name_pattern)")
                params["name_pattern"] = f"%{client_name}%"

            if client_id:
                conditions.append("(matched_lead_id = :client_id OR matched_loan_id = :client_id)")
                params["client_id"] = client_id

            query = text(f"""
                SELECT
                    id, provider_message_id as message_id, from_email, from_name,
                    subject, COALESCE(received_date, sent_date) as received_date, is_priority,
                    matched_lead_id as lead_id, matched_loan_id as loan_id,
                    match_confidence, match_method,
                    LEFT(body_preview, 200) as body_preview
                FROM email_reconciliation_queue
                WHERE {' AND '.join(conditions)}
                AND COALESCE(received_date, sent_date) > NOW() - INTERVAL '{days} days'
                ORDER BY COALESCE(received_date, sent_date) DESC
                LIMIT :limit
            """)

            results = self.db.execute(query, params).fetchall()

            emails = []
            priority_count = 0
            for row in results:
                email = {
                    "id": row.id,
                    "from": row.from_email,
                    "from_name": row.from_name,
                    "subject": row.subject,
                    "date": row.received_date.isoformat() if row.received_date else None,
                    "is_priority": row.is_priority,
                    "preview": row.body_preview,
                    "lead_id": row.lead_id,
                    "loan_id": row.loan_id
                }
                emails.append(email)
                if row.is_priority:
                    priority_count += 1

            # Generate AI summary
            summary = self._generate_search_summary(emails, client_name or client_email, priority_count)

            return {
                "success": True,
                "emails": emails,
                "count": len(emails),
                "priority_count": priority_count,
                "ai_summary": summary
            }

        except Exception as e:
            logger.error(f"Error searching emails by client: {e}")
            return {
                "success": False,
                "error": str(e),
                "emails": [],
                "count": 0
            }

    def get_email_thread(
        self,
        email_id: Optional[int] = None,
        thread_id: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get complete email conversation thread.

        Args:
            email_id: Database ID of any email in thread
            thread_id: Gmail/Outlook thread ID
            message_id: Specific message ID

        Returns:
            Dict with thread emails and context
        """
        try:
            # First get the reference email
            if email_id:
                ref_query = text("""
                    SELECT thread_id, from_email, subject
                    FROM email_reconciliation_queue
                    WHERE id = :email_id
                """)
                ref = self.db.execute(ref_query, {"email_id": email_id}).fetchone()
                if ref:
                    thread_id = ref.thread_id

            if not thread_id:
                return {
                    "success": False,
                    "error": "Could not find thread",
                    "emails": []
                }

            # Get all emails in thread
            query = text("""
                SELECT
                    id, provider_message_id as message_id, from_email, from_name,
                    subject, COALESCE(received_date, sent_date) as received_date, body_preview,
                    is_priority, matched_lead_id as lead_id, matched_loan_id as loan_id
                FROM email_reconciliation_queue
                WHERE thread_id = :thread_id
                ORDER BY COALESCE(received_date, sent_date) ASC
            """)

            results = self.db.execute(query, {"thread_id": thread_id}).fetchall()

            emails = []
            participants = set()
            for row in results:
                emails.append({
                    "id": row.id,
                    "from": row.from_email,
                    "from_name": row.from_name,
                    "subject": row.subject,
                    "date": row.received_date.isoformat() if row.received_date else None,
                    "preview": row.body_preview
                })
                if row.from_email:
                    participants.add(row.from_email)

            return {
                "success": True,
                "thread_id": thread_id,
                "emails": emails,
                "email_count": len(emails),
                "participants": list(participants),
                "ai_summary": f"Thread with {len(emails)} emails between {len(participants)} participants"
            }

        except Exception as e:
            logger.error(f"Error getting email thread: {e}")
            return {
                "success": False,
                "error": str(e),
                "emails": []
            }

    def identify_email_sender(self, email_address: str) -> Dict[str, Any]:
        """
        Identify who an email address belongs to in the CRM.

        Args:
            email_address: Email address to identify

        Returns:
            Dict with identity information and CRM context
        """
        try:
            email_lower = email_address.lower().strip()

            # Check known client emails
            known_query = text("""
                SELECT
                    kce.email_address, kce.client_name, kce.source_type,
                    kce.lead_id, kce.loan_id, kce.contact_id,
                    l.name as lead_name, l.stage as lead_stage,
                    lo.borrower_name, lo.loan_number, lo.stage as loan_stage
                FROM known_client_emails kce
                LEFT JOIN leads l ON kce.lead_id = l.id
                LEFT JOIN loans lo ON kce.loan_id = lo.id
                WHERE LOWER(kce.email_address) = :email
                AND kce.user_id = :user_id
            """)

            result = self.db.execute(known_query, {"email": email_lower, "user_id": self.user_id}).fetchone()

            if result:
                # Determine entity type and id
                entity_type = "unknown"
                entity_id = None
                if result.lead_id:
                    entity_type = "lead"
                    entity_id = result.lead_id
                elif result.loan_id:
                    entity_type = "loan"
                    entity_id = result.loan_id
                elif result.contact_id:
                    entity_type = "contact"
                    entity_id = result.contact_id

                identity = {
                    "matched": True,
                    "match_confidence": 1.0,
                    "email": result.email_address,
                    "client_name": result.client_name,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "source_type": result.source_type
                }

                # Add CRM details
                if result.lead_id and result.lead_name:
                    identity["lead_details"] = {
                        "id": result.lead_id,
                        "name": result.lead_name,
                        "stage": result.lead_stage
                    }
                if result.loan_id and result.borrower_name:
                    identity["loan_details"] = {
                        "id": result.loan_id,
                        "borrower": result.borrower_name,
                        "loan_number": result.loan_number,
                        "stage": result.loan_stage
                    }

                return {
                    "success": True,
                    "identity": identity,
                    "ai_summary": f"{result.client_name} identified via known client email (100% confidence)."
                }

            # Check leads by email
            lead_query = text("""
                SELECT id, name, email, phone, stage
                FROM leads
                WHERE LOWER(email) = :email
            """)
            lead = self.db.execute(lead_query, {"email": email_lower}).fetchone()

            if lead:
                return {
                    "success": True,
                    "identity": {
                        "matched": True,
                        "match_confidence": 0.95,
                        "email": lead.email,
                        "client_name": lead.name,
                        "entity_type": "lead",
                        "entity_id": lead.id,
                        "is_priority": False
                    },
                    "lead_details": {
                        "id": lead.id,
                        "name": lead.name,
                        "phone": lead.phone,
                        "stage": lead.stage
                    },
                    "ai_summary": f"{lead.name} - Lead (Stage: {lead.stage})"
                }

            # Check loans by borrower email
            loan_query = text("""
                SELECT id, loan_number, borrower_name, borrower_email, stage, amount
                FROM loans
                WHERE LOWER(borrower_email) = :email
            """)
            loan = self.db.execute(loan_query, {"email": email_lower}).fetchone()

            if loan:
                return {
                    "success": True,
                    "identity": {
                        "matched": True,
                        "match_confidence": 0.95,
                        "email": loan.borrower_email,
                        "client_name": loan.borrower_name,
                        "entity_type": "loan",
                        "entity_id": loan.id,
                        "is_priority": True
                    },
                    "loan_details": {
                        "id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower": loan.borrower_name,
                        "stage": loan.stage,
                        "amount": float(loan.amount) if loan.amount else None
                    },
                    "ai_summary": f"{loan.borrower_name} - Active loan #{loan.loan_number} (Stage: {loan.stage})"
                }

            # Unknown sender
            return {
                "success": True,
                "identity": {
                    "matched": False,
                    "email": email_address,
                    "client_name": None
                },
                "ai_summary": f"Unknown sender: {email_address}. Not found in CRM."
            }

        except Exception as e:
            logger.error(f"Error identifying email sender: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_priority_emails(self, days: int = 7, limit: int = 20) -> Dict[str, Any]:
        """
        Get priority emails that need attention.

        Args:
            days: Number of days to look back
            limit: Maximum results

        Returns:
            Dict with priority emails and recommended actions
        """
        try:
            query = text(f"""
                SELECT
                    id, from_email, from_name, subject,
                    COALESCE(received_date, sent_date) as received_date, body_preview,
                    matched_lead_id as lead_id, matched_loan_id as loan_id, match_confidence,
                    is_priority, status
                FROM email_reconciliation_queue
                WHERE is_priority = TRUE
                AND COALESCE(received_date, sent_date) > NOW() - INTERVAL '{days} days'
                AND status != 'archived'
                ORDER BY COALESCE(received_date, sent_date) DESC
                LIMIT :limit
            """)

            results = self.db.execute(query, {"limit": limit}).fetchall()

            emails = []
            action_items = []

            for row in results:
                email = {
                    "id": row.id,
                    "from": row.from_email,
                    "from_name": row.from_name,
                    "subject": row.subject,
                    "date": row.received_date.isoformat() if row.received_date else None,
                    "preview": row.body_preview,
                    "lead_id": row.lead_id,
                    "loan_id": row.loan_id,
                    "status": row.status
                }
                emails.append(email)

                # Generate action recommendation
                if row.status == 'pending':
                    client = row.from_name or row.from_email
                    action_items.append(f"Follow up on email from {client}: {row.subject[:50] if row.subject else 'No subject'}")

            # Categorize by urgency
            today = datetime.utcnow().date()
            urgent = []
            important = []

            for email in emails:
                if email["date"]:
                    email_date = datetime.fromisoformat(email["date"].replace('Z', '+00:00')).date()
                    days_old = (today - email_date).days
                    if days_old <= 1:
                        urgent.append(email)
                    else:
                        important.append(email)

            summary = f"You have {len(emails)} priority emails. "
            if urgent:
                summary += f"{len(urgent)} are urgent (last 24h). "
            if action_items:
                summary += f"Top action: {action_items[0]}"

            return {
                "success": True,
                "emails": emails,
                "priority_count": len(emails),
                "urgent_count": len(urgent),
                "recommended_actions": action_items[:5],
                "ai_summary": summary
            }

        except Exception as e:
            logger.error(f"Error getting priority emails: {e}")
            return {
                "success": False,
                "error": str(e),
                "emails": []
            }

    def search_emails_by_content(
        self,
        keywords: str,
        days: int = 30,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Search emails by keywords in subject and body.

        Args:
            keywords: Search terms
            days: Days to search back
            limit: Maximum results

        Returns:
            Dict with matching emails
        """
        try:
            # Split keywords for matching
            terms = keywords.lower().split()

            query = text(f"""
                SELECT
                    id, from_email, from_name, subject,
                    COALESCE(received_date, sent_date) as received_date, body_preview,
                    matched_lead_id as lead_id, matched_loan_id as loan_id, is_priority
                FROM email_reconciliation_queue
                WHERE COALESCE(received_date, sent_date) > NOW() - INTERVAL '{days} days'
                AND (
                    LOWER(subject) LIKE :pattern
                    OR LOWER(body_preview) LIKE :pattern
                )
                ORDER BY
                    CASE WHEN is_priority THEN 0 ELSE 1 END,
                    COALESCE(received_date, sent_date) DESC
                LIMIT :limit
            """)

            pattern = f"%{keywords.lower()}%"
            results = self.db.execute(query, {
                "limit": limit,
                "pattern": pattern
            }).fetchall()

            emails = []
            for row in results:
                emails.append({
                    "id": row.id,
                    "from": row.from_email,
                    "from_name": row.from_name,
                    "subject": row.subject,
                    "date": row.received_date.isoformat() if row.received_date else None,
                    "preview": row.body_preview,
                    "is_priority": row.is_priority,
                    "lead_id": row.lead_id,
                    "loan_id": row.loan_id
                })

            return {
                "success": True,
                "emails": emails,
                "count": len(emails),
                "search_terms": keywords,
                "ai_summary": f"Found {len(emails)} emails matching '{keywords}'"
            }

        except Exception as e:
            logger.error(f"Error searching emails by content: {e}")
            return {
                "success": False,
                "error": str(e),
                "emails": []
            }

    def get_email_context_for_ai(self, email_id: int) -> Dict[str, Any]:
        """
        Get complete context for an email to help AI make decisions.

        Args:
            email_id: Email ID to get context for

        Returns:
            Dict with email, thread, CRM context, and recommendations
        """
        try:
            # Get the email
            email_query = text("""
                SELECT
                    id, provider_message_id as message_id, thread_id, from_email, from_name,
                    subject, COALESCE(received_date, sent_date) as received_date, body_preview,
                    matched_lead_id as lead_id, matched_loan_id as loan_id,
                    match_confidence, match_method, is_priority, status
                FROM email_reconciliation_queue
                WHERE id = :email_id
            """)

            email = self.db.execute(email_query, {"email_id": email_id}).fetchone()

            if not email:
                return {
                    "success": False,
                    "error": f"Email {email_id} not found"
                }

            context = {
                "email": {
                    "id": email.id,
                    "from": email.from_email,
                    "from_name": email.from_name,
                    "subject": email.subject,
                    "date": email.received_date.isoformat() if email.received_date else None,
                    "preview": email.body_preview,
                    "is_priority": email.is_priority,
                    "status": email.status
                }
            }

            # Get thread context
            if email.thread_id:
                thread = self.get_email_thread(thread_id=email.thread_id)
                context["thread_context"] = {
                    "email_count": thread.get("email_count", 0),
                    "participants": thread.get("participants", [])
                }

            # Get CRM context
            crm_context = {}

            if email.lead_id:
                lead_query = text("""
                    SELECT id, name, email, phone, stage, created_at
                    FROM leads WHERE id = :lead_id
                """)
                lead = self.db.execute(lead_query, {"lead_id": email.lead_id}).fetchone()
                if lead:
                    crm_context["lead"] = {
                        "id": lead.id,
                        "name": lead.name,
                        "email": lead.email,
                        "phone": lead.phone,
                        "stage": lead.stage
                    }

            if email.loan_id:
                loan_query = text("""
                    SELECT id, loan_number, borrower_name, stage, amount, closing_date
                    FROM loans WHERE id = :loan_id
                """)
                loan = self.db.execute(loan_query, {"loan_id": email.loan_id}).fetchone()
                if loan:
                    crm_context["loan"] = {
                        "id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower": loan.borrower_name,
                        "stage": loan.stage,
                        "amount": float(loan.amount) if loan.amount else None,
                        "closing_date": loan.closing_date.isoformat() if loan.closing_date else None
                    }

            context["crm_context"] = crm_context

            # Get recent emails from same sender
            recent_query = text("""
                SELECT id, subject, COALESCE(received_date, sent_date) as received_date
                FROM email_reconciliation_queue
                WHERE from_email = :from_addr
                AND id != :email_id
                ORDER BY COALESCE(received_date, sent_date) DESC
                LIMIT 5
            """)
            recent = self.db.execute(recent_query, {
                "from_addr": email.from_email,
                "email_id": email_id
            }).fetchall()

            context["recent_client_emails"] = [
                {"id": r.id, "subject": r.subject, "date": r.received_date.isoformat() if r.received_date else None}
                for r in recent
            ]

            # Generate AI recommendations
            recommendations = []

            if email.is_priority and email.status == 'pending':
                recommendations.append("This is a priority email - respond within 2 hours")

            if crm_context.get("loan"):
                loan = crm_context["loan"]
                if loan.get("closing_date"):
                    closing = datetime.fromisoformat(loan["closing_date"])
                    days_to_close = (closing.date() - datetime.utcnow().date()).days
                    if days_to_close <= 7:
                        recommendations.append(f"Client closing in {days_to_close} days - high priority")

            if len(context.get("recent_client_emails", [])) >= 3:
                recommendations.append("Frequent communicator - maintain engagement")

            context["ai_recommendations"] = recommendations
            context["success"] = True

            # Generate summary
            client = email.from_name or email.from_email
            summary = f"Email from {client}"
            if crm_context.get("loan"):
                summary += f" (Active loan #{crm_context['loan']['loan_number']})"
            elif crm_context.get("lead"):
                summary += f" (Lead - {crm_context['lead']['stage']})"
            if recommendations:
                summary += f". {recommendations[0]}"

            context["ai_summary"] = summary

            return context

        except Exception as e:
            logger.error(f"Error getting email context: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _generate_search_summary(
        self,
        emails: List[Dict],
        search_term: str,
        priority_count: int
    ) -> str:
        """Generate AI-friendly summary of search results."""
        if not emails:
            return f"No emails found for '{search_term}'"

        summary = f"Found {len(emails)} emails"
        if search_term:
            summary += f" for '{search_term}'"

        if priority_count > 0:
            summary += f". {priority_count} are high priority"

        if emails:
            latest = emails[0]
            summary += f". Most recent: '{latest.get('subject', 'No subject')[:50]}'"

        return summary


# Tool definitions for different AI frameworks

def get_tools_for_langgraph(db: Session, user_id: int) -> Dict[str, callable]:
    """Get tool functions formatted for LangGraph/LangChain."""
    tools = EmailSearchTools(db, user_id)
    return {
        "search_emails_by_client": tools.search_emails_by_client,
        "get_email_thread": tools.get_email_thread,
        "identify_email_sender": tools.identify_email_sender,
        "get_priority_emails": tools.get_priority_emails,
        "search_emails_by_content": tools.search_emails_by_content,
        "get_email_context_for_ai": tools.get_email_context_for_ai
    }


def get_openai_tools_format() -> List[Dict]:
    """Get tool definitions in OpenAI function calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": "search_emails_by_client",
                "description": "Search emails from a specific client by name, email address, or CRM ID",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_name": {"type": "string", "description": "Client's name (partial match)"},
                        "client_email": {"type": "string", "description": "Client's email address"},
                        "client_id": {"type": "integer", "description": "Lead or loan ID"},
                        "days": {"type": "integer", "description": "Days to search back", "default": 30},
                        "limit": {"type": "integer", "description": "Max results", "default": 20}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_email_thread",
                "description": "Get complete email conversation thread",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email_id": {"type": "integer", "description": "Email ID in the thread"},
                        "thread_id": {"type": "string", "description": "Thread ID"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "identify_email_sender",
                "description": "Identify who an email address belongs to in the CRM",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email_address": {"type": "string", "description": "Email address to identify"}
                    },
                    "required": ["email_address"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_priority_emails",
                "description": "Get priority emails that need attention",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "Days to look back", "default": 7},
                        "limit": {"type": "integer", "description": "Max results", "default": 20}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_emails_by_content",
                "description": "Search emails by keywords in subject and body",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keywords": {"type": "string", "description": "Search terms"},
                        "days": {"type": "integer", "description": "Days to search back", "default": 30},
                        "limit": {"type": "integer", "description": "Max results", "default": 20}
                    },
                    "required": ["keywords"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_email_context_for_ai",
                "description": "Get complete context for an email including CRM data and recommendations",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email_id": {"type": "integer", "description": "Email ID"}
                    },
                    "required": ["email_id"]
                }
            }
        }
    ]


# Morning briefing helper
def get_morning_briefing(db: Session, user_id: int) -> Dict[str, Any]:
    """
    Generate a morning email briefing for the user.

    Returns:
        Dict with priority emails, action items, and summary
    """
    tools = EmailSearchTools(db, user_id)

    # Get priority emails from last 24 hours
    priority = tools.get_priority_emails(days=1, limit=10)

    # Get recent unread count
    count_query = text("""
        SELECT COUNT(*) as count
        FROM email_reconciliation_queue
        WHERE status = 'pending'
        AND received_date > NOW() - INTERVAL '24 hours'
    """)
    recent_count = db.execute(count_query).scalar() or 0

    briefing = {
        "date": datetime.utcnow().strftime("%A, %B %d, %Y"),
        "priority_emails": priority.get("emails", []),
        "priority_count": priority.get("priority_count", 0),
        "recent_email_count": recent_count,
        "recommended_actions": priority.get("recommended_actions", [])
    }

    # Generate briefing text
    text_briefing = f"Good morning! Here's your email briefing for {briefing['date']}:\n\n"
    text_briefing += f"You have {recent_count} new emails in the last 24 hours.\n"
    text_briefing += f"{briefing['priority_count']} are marked as priority.\n\n"

    if briefing["recommended_actions"]:
        text_briefing += "Recommended actions:\n"
        for i, action in enumerate(briefing["recommended_actions"][:3], 1):
            text_briefing += f"  {i}. {action}\n"

    briefing["text_briefing"] = text_briefing

    return briefing
