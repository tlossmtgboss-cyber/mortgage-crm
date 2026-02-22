"""
AI Tool Interface for Email Identity Resolution System
Perennia AI - IBMA (Intelligent Business Mortgage Assistant)

This module provides AI-accessible tools for the email identity system,
enabling AI agents to search emails, understand matches, and execute
context-aware tasks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Literal
from dataclasses import dataclass, asdict
from enum import Enum

from sqlalchemy import text
from sqlalchemy.orm import Session

# Import from services directory
from services.email_identity_resolver import EmailIdentityResolver
from services.email_identity_analytics import EmailIdentityAnalytics

logger = logging.getLogger(__name__)


# ================================================================
# AI TOOL DEFINITIONS
# ================================================================

class EmailSearchTools:
    """
    AI-accessible tools for email search and identity resolution.

    These tools are designed to be used by LangGraph agents, OpenAI function
    calling, or other AI orchestration frameworks.
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.resolver = EmailIdentityResolver(db)
        self.analytics = EmailIdentityAnalytics(db)

    # ================================================================
    # TOOL 1: Search Emails by Client
    # ================================================================

    def search_emails_by_client(
        self,
        client_name: Optional[str] = None,
        client_email: Optional[str] = None,
        loan_id: Optional[int] = None,
        lead_id: Optional[int] = None,
        days: int = 30,
        include_unread_only: bool = False,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Search for emails related to a specific client.

        AI USE CASE:
        - "Show me recent emails from John Doe"
        - "What emails did we receive about loan #123456?"
        - "Find unread emails from sarah@example.com"

        Args:
            client_name: Client's name (fuzzy match)
            client_email: Exact email address
            loan_id: Specific loan ID
            lead_id: Specific lead ID
            days: Days to look back
            include_unread_only: Only unread/pending emails
            limit: Max results

        Returns:
            Dictionary with emails and match summary
        """
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)

            # Build WHERE clause dynamically
            where_conditions = ["e.user_id = :user_id", "e.created_at >= :start_date"]
            params = {"user_id": self.user_id, "start_date": start_date}

            if client_name:
                where_conditions.append("e.match_client_name ILIKE :client_name")
                params["client_name"] = f"%{client_name}%"

            if client_email:
                where_conditions.append("LOWER(e.from_email) = :client_email")
                params["client_email"] = client_email.lower()

            if loan_id:
                where_conditions.append("e.matched_loan_id = :loan_id")
                params["loan_id"] = loan_id

            if lead_id:
                where_conditions.append("e.matched_lead_id = :lead_id")
                params["lead_id"] = lead_id

            if include_unread_only:
                where_conditions.append("e.status = 'pending'")

            where_clause = " AND ".join(where_conditions)

            # Execute search
            results = self.db.execute(text(f"""
                SELECT
                    e.id,
                    e.from_email,
                    e.from_name,
                    e.subject,
                    e.body_preview,
                    COALESCE(e.received_date, e.sent_date) as received_date,
                    e.match_method,
                    e.match_confidence,
                    e.match_client_name,
                    e.matched_loan_id,
                    e.matched_lead_id,
                    e.is_priority,
                    e.status,
                    e.has_attachments,
                    e.disposition
                FROM email_reconciliation_queue e
                WHERE {where_clause}
                ORDER BY COALESCE(e.received_date, e.sent_date) DESC
                LIMIT :limit
            """), {**params, "limit": limit}).fetchall()

            emails = [
                {
                    "email_id": row[0],
                    "from_email": row[1],
                    "from_name": row[2],
                    "subject": row[3],
                    "preview": row[4],
                    "received_date": row[5].isoformat() if row[5] else None,
                    "match_method": row[6],
                    "match_confidence": float(row[7]) if row[7] else None,
                    "client_name": row[8],
                    "loan_id": row[9],
                    "lead_id": row[10],
                    "is_priority": row[11],
                    "status": row[12],
                    "has_attachments": row[13],
                    "disposition": row[14]
                }
                for row in results
            ]

            return {
                "success": True,
                "emails": emails,
                "count": len(emails),
                "search_criteria": {
                    "client_name": client_name,
                    "client_email": client_email,
                    "loan_id": loan_id,
                    "lead_id": lead_id,
                    "days": days,
                    "unread_only": include_unread_only
                },
                "ai_summary": self._generate_email_summary(emails)
            }

        except Exception as e:
            logger.error(f"Email search failed: {e}")
            return {
                "success": False,
                "error": "Internal server error",
                "emails": []
            }

    # ================================================================
    # TOOL 2: Get Email Thread
    # ================================================================

    def get_email_thread(
        self,
        email_id: Optional[int] = None,
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get complete email thread/conversation.

        AI USE CASE:
        - "Show me the full conversation with this client"
        - "What's the context around email #12345?"
        - "Get the email thread for this discussion"

        Args:
            email_id: Specific email ID to get thread for
            thread_id: Thread ID to retrieve

        Returns:
            Complete thread with all messages in chronological order
        """
        try:
            # Get thread_id if email_id provided
            if email_id and not thread_id:
                result = self.db.execute(text("""
                    SELECT thread_id FROM email_reconciliation_queue
                    WHERE id = :email_id
                """), {"email_id": email_id}).fetchone()

                if result and result[0]:
                    thread_id = result[0]

            if not thread_id:
                return {
                    "success": False,
                    "error": "No thread_id found",
                    "thread": []
                }

            # Get all emails in thread
            results = self.db.execute(text("""
                SELECT
                    id,
                    from_email,
                    from_name,
                    to_emails,
                    subject,
                    body_preview,
                    body_full,
                    COALESCE(received_date, sent_date) as received_date,
                    direction,
                    match_client_name,
                    has_attachments,
                    attachment_names
                FROM email_reconciliation_queue
                WHERE thread_id = :thread_id
                  AND user_id = :user_id
                ORDER BY COALESCE(received_date, sent_date) ASC
            """), {
                "thread_id": thread_id,
                "user_id": self.user_id
            }).fetchall()

            thread_emails = [
                {
                    "email_id": row[0],
                    "from_email": row[1],
                    "from_name": row[2],
                    "to_emails": row[3],
                    "subject": row[4],
                    "preview": row[5],
                    "full_body": row[6],
                    "received_date": row[7].isoformat() if row[7] else None,
                    "direction": row[8],
                    "client_name": row[9],
                    "has_attachments": row[10],
                    "attachments": row[11]
                }
                for row in results
            ]

            return {
                "success": True,
                "thread_id": thread_id,
                "email_count": len(thread_emails),
                "thread": thread_emails,
                "ai_summary": self._generate_thread_summary(thread_emails)
            }

        except Exception as e:
            logger.error(f"Thread retrieval failed: {e}")
            return {
                "success": False,
                "error": "Internal server error",
                "thread": []
            }

    # ================================================================
    # TOOL 3: Identify Email Sender
    # ================================================================

    def identify_email_sender(
        self,
        email_address: str
    ) -> Dict[str, Any]:
        """
        Identify who an email address belongs to in the CRM.

        AI USE CASE:
        - "Who is john@example.com?"
        - "Do we know this email address?"
        - "What client is associated with this email?"

        Args:
            email_address: Email address to identify

        Returns:
            Complete identity information from CRM
        """
        try:
            email_data = {"from_email": email_address}
            match = self.resolver.resolve(email_data, self.user_id)

            # Enrich with full CRM details
            crm_details = self._get_full_crm_details(match)

            return {
                "success": True,
                "email_address": email_address,
                "matched": match.get("match_method") is not None,
                "identity": {
                    "client_name": match.get("match_client_name"),
                    "match_method": match.get("match_method"),
                    "confidence": match.get("match_confidence"),
                    "loan_id": match.get("matched_loan_id"),
                    "lead_id": match.get("matched_lead_id"),
                    "contact_id": match.get("matched_contact_id"),
                    "is_priority": match.get("is_priority")
                },
                "crm_details": crm_details,
                "ai_summary": self._generate_identity_summary(match, crm_details)
            }

        except Exception as e:
            logger.error(f"Identity resolution failed: {e}")
            return {
                "success": False,
                "error": "Internal server error",
                "email_address": email_address,
                "matched": False
            }

    # ================================================================
    # TOOL 4: Get Priority Emails
    # ================================================================

    def get_priority_emails(
        self,
        days: int = 7,
        unread_only: bool = True,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get high-priority emails requiring immediate attention.

        AI USE CASE:
        - "What urgent emails do I have?"
        - "Show me priority items"
        - "What needs my attention today?"

        Args:
            days: Days to look back
            unread_only: Only pending/unread emails
            limit: Max results

        Returns:
            Priority emails with context
        """
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)

            where_clauses = [
                "user_id = :user_id",
                "is_priority = TRUE",
                "created_at >= :start_date"
            ]

            if unread_only:
                where_clauses.append("status = 'pending'")

            where_clause = " AND ".join(where_clauses)

            results = self.db.execute(text(f"""
                SELECT
                    id,
                    from_email,
                    from_name,
                    subject,
                    body_preview,
                    COALESCE(received_date, sent_date) as received_date,
                    match_client_name,
                    match_loan_number,
                    matched_loan_id,
                    match_confidence,
                    disposition,
                    has_attachments
                FROM email_reconciliation_queue
                WHERE {where_clause}
                ORDER BY COALESCE(received_date, sent_date) DESC
                LIMIT :limit
            """), {
                "user_id": self.user_id,
                "start_date": start_date,
                "limit": limit
            }).fetchall()

            priority_emails = [
                {
                    "email_id": row[0],
                    "from_email": row[1],
                    "from_name": row[2],
                    "subject": row[3],
                    "preview": row[4],
                    "received_date": row[5].isoformat() if row[5] else None,
                    "client_name": row[6],
                    "loan_number": row[7],
                    "loan_id": row[8],
                    "confidence": float(row[9]) if row[9] else None,
                    "disposition": row[10],
                    "has_attachments": row[11]
                }
                for row in results
            ]

            return {
                "success": True,
                "priority_count": len(priority_emails),
                "emails": priority_emails,
                "ai_summary": self._generate_priority_summary(priority_emails),
                "recommended_actions": self._suggest_actions(priority_emails)
            }

        except Exception as e:
            logger.error(f"Priority email retrieval failed: {e}")
            return {
                "success": False,
                "error": "Internal server error",
                "emails": []
            }

    # ================================================================
    # TOOL 5: Search Emails by Content
    # ================================================================

    def search_emails_by_content(
        self,
        search_query: Optional[str] = None,
        keywords: Optional[str] = None,  # Alias for search_query
        search_in: Literal["subject", "body", "both"] = "both",
        days: int = 30,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Search emails by subject or body content.

        AI USE CASE:
        - "Find emails mentioning 'appraisal'"
        - "Search for emails about closing dates"
        - "Show emails containing 'urgent'"

        Args:
            search_query: Text to search for
            keywords: Alias for search_query (for backward compatibility)
            search_in: Where to search (subject, body, or both)
            days: Days to look back
            limit: Max results

        Returns:
            Matching emails with relevance scoring
        """
        # Support both parameter names
        query = search_query or keywords
        if not query:
            return {
                "success": False,
                "error": "search_query or keywords required",
                "emails": []
            }

        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)

            # Build search condition
            if search_in == "subject":
                search_condition = "subject ILIKE :query"
            elif search_in == "body":
                search_condition = "(body_preview ILIKE :query OR body_full ILIKE :query)"
            else:  # both
                search_condition = """(
                    subject ILIKE :query OR
                    body_preview ILIKE :query OR
                    body_full ILIKE :query
                )"""

            results = self.db.execute(text(f"""
                SELECT
                    id,
                    from_email,
                    from_name,
                    subject,
                    body_preview,
                    COALESCE(received_date, sent_date) as received_date,
                    match_client_name,
                    matched_loan_id,
                    matched_lead_id,
                    disposition,
                    is_priority
                FROM email_reconciliation_queue
                WHERE user_id = :user_id
                  AND created_at >= :start_date
                  AND {search_condition}
                ORDER BY COALESCE(received_date, sent_date) DESC
                LIMIT :limit
            """), {
                "user_id": self.user_id,
                "start_date": start_date,
                "query": f"%{query}%",
                "limit": limit
            }).fetchall()

            matching_emails = [
                {
                    "email_id": row[0],
                    "from_email": row[1],
                    "from_name": row[2],
                    "subject": row[3],
                    "preview": row[4],
                    "received_date": row[5].isoformat() if row[5] else None,
                    "client_name": row[6],
                    "loan_id": row[7],
                    "lead_id": row[8],
                    "disposition": row[9],
                    "is_priority": row[10]
                }
                for row in results
            ]

            return {
                "success": True,
                "search_query": query,
                "search_in": search_in,
                "count": len(matching_emails),
                "emails": matching_emails,
                "ai_summary": self._generate_search_summary(query, matching_emails)
            }

        except Exception as e:
            logger.error(f"Content search failed: {e}")
            return {
                "success": False,
                "error": "Internal server error",
                "emails": []
            }

    # ================================================================
    # TOOL 6: Get Email Context for AI Decision
    # ================================================================

    def get_email_context_for_ai(
        self,
        email_id: int
    ) -> Dict[str, Any]:
        """
        Get complete context about an email for AI decision-making.

        AI USE CASE:
        - "Give me full context on this email"
        - "What do I need to know about email #12345?"
        - "Help me understand this client's situation"

        Args:
            email_id: Email ID to get context for

        Returns:
            Complete context including client history, loan status, etc.
        """
        try:
            # Get base email
            email_result = self.db.execute(text("""
                SELECT
                    id, from_email, from_name, to_emails, subject,
                    body_preview, body_full, COALESCE(received_date, sent_date) as received_date, thread_id,
                    match_client_name, matched_loan_id, matched_lead_id,
                    matched_contact_id, match_method, match_confidence,
                    disposition, is_priority, has_attachments, attachment_names
                FROM email_reconciliation_queue
                WHERE id = :email_id AND user_id = :user_id
            """), {
                "email_id": email_id,
                "user_id": self.user_id
            }).fetchone()

            if not email_result:
                return {
                    "success": False,
                    "error": "Email not found"
                }

            # Build email object
            email = {
                "email_id": email_result[0],
                "from_email": email_result[1],
                "from_name": email_result[2],
                "to_emails": email_result[3],
                "subject": email_result[4],
                "preview": email_result[5],
                "full_body": email_result[6],
                "received_date": email_result[7].isoformat() if email_result[7] else None,
                "thread_id": email_result[8],
                "client_name": email_result[9],
                "loan_id": email_result[10],
                "lead_id": email_result[11],
                "contact_id": email_result[12],
                "match_method": email_result[13],
                "confidence": float(email_result[14]) if email_result[14] else None,
                "disposition": email_result[15],
                "is_priority": email_result[16],
                "has_attachments": email_result[17],
                "attachments": email_result[18]
            }

            # Get thread context
            thread_context = None
            if email["thread_id"]:
                thread_result = self.get_email_thread(thread_id=email["thread_id"])
                thread_context = thread_result.get("thread", [])

            # Get client/loan context
            crm_context = self._get_full_crm_details({
                "matched_loan_id": email["loan_id"],
                "matched_lead_id": email["lead_id"],
                "matched_contact_id": email["contact_id"]
            })

            # Get recent emails from same client
            recent_emails = []
            if email["from_email"]:
                recent_result = self.search_emails_by_client(
                    client_email=email["from_email"],
                    days=30,
                    limit=5
                )
                recent_emails = recent_result.get("emails", [])

            return {
                "success": True,
                "email": email,
                "thread_context": thread_context,
                "crm_context": crm_context,
                "recent_client_emails": recent_emails,
                "ai_recommendations": self._generate_ai_recommendations(
                    email, crm_context, thread_context
                )
            }

        except Exception as e:
            logger.error(f"Email context retrieval failed: {e}")
            return {
                "success": False,
                "error": "Internal server error"
            }

    # ================================================================
    # Helper Methods for AI Summaries
    # ================================================================

    def _generate_email_summary(self, emails: List[Dict]) -> str:
        """Generate AI-friendly summary of email search results."""
        if not emails:
            return "No emails found matching the search criteria."

        priority_count = sum(1 for e in emails if e.get("is_priority"))
        unread_count = sum(1 for e in emails if e.get("status") == "pending")

        summary = f"Found {len(emails)} emails. "
        if priority_count > 0:
            summary += f"{priority_count} are high priority. "
        if unread_count > 0:
            summary += f"{unread_count} are unread. "

        # Most recent email
        if emails[0].get("subject"):
            summary += f"Most recent: '{emails[0]['subject']}' from {emails[0].get('from_name') or emails[0].get('from_email')}."

        return summary

    def _generate_thread_summary(self, thread: List[Dict]) -> str:
        """Generate AI-friendly summary of email thread."""
        if not thread:
            return "No emails in this thread."

        return (
            f"Thread contains {len(thread)} messages. "
            f"Started {thread[0].get('received_date', 'unknown date')}. "
            f"Last message from {thread[-1].get('from_name') or thread[-1].get('from_email')}."
        )

    def _generate_identity_summary(
        self,
        match: Dict,
        crm_details: Dict
    ) -> str:
        """Generate AI-friendly identity summary."""
        if not match.get("match_method"):
            return "This email address is not recognized in the CRM."

        name = match.get("match_client_name", "Unknown")
        method = match.get("match_method", "").replace("_", " ")
        confidence = (match.get("match_confidence") or 0) * 100

        summary = f"{name} identified via {method} ({confidence:.0f}% confidence). "

        if match.get("matched_loan_id"):
            summary += "Active loan on file. "
        elif match.get("matched_lead_id"):
            summary += "Active lead in pipeline. "

        if match.get("is_priority"):
            summary += "⚠️ Priority client."

        return summary

    def _generate_priority_summary(self, emails: List[Dict]) -> str:
        """Generate AI-friendly priority email summary."""
        if not emails:
            return "No priority emails requiring attention."

        return (
            f"You have {len(emails)} priority emails. "
            f"Most urgent: '{emails[0].get('subject')}' from {emails[0].get('client_name') or emails[0].get('from_email')}."
        )

    def _generate_search_summary(
        self,
        query: str,
        emails: List[Dict]
    ) -> str:
        """Generate AI-friendly search results summary."""
        if not emails:
            return f"No emails found containing '{query}'."

        return f"Found {len(emails)} emails mentioning '{query}'."

    def _suggest_actions(self, priority_emails: List[Dict]) -> List[str]:
        """Suggest actions based on priority emails."""
        actions = []

        for email in priority_emails[:3]:  # Top 3
            disposition = email.get("disposition")
            client = email.get("client_name") or email.get("from_email")

            if disposition == "document_request":
                actions.append(f"Follow up on document request from {client}")
            elif disposition == "action_required":
                actions.append(f"Review action item from {client}")
            elif disposition == "date_change":
                actions.append(f"Update calendar for {client}")
            else:
                actions.append(f"Respond to {client}")

        return actions

    def _generate_ai_recommendations(
        self,
        email: Dict,
        crm_context: Dict,
        thread_context: Optional[List[Dict]]
    ) -> List[str]:
        """Generate AI recommendations for handling this email."""
        recommendations = []

        # Priority
        if email.get("is_priority"):
            recommendations.append("⚠️ Respond to this email within 2 hours")

        # Disposition-based
        disposition = email.get("disposition")
        if disposition == "document_request":
            recommendations.append("Check if requested documents are available in system")
        elif disposition == "document_received":
            recommendations.append("Review and process received documents")
        elif disposition == "status_update":
            recommendations.append("Update loan status in CRM")

        # Thread-based
        if thread_context and len(thread_context) > 5:
            recommendations.append("Long conversation - consider scheduling a call")

        # CRM-based
        if crm_context.get("loan"):
            loan = crm_context["loan"]
            if loan.get("closing_date"):
                recommendations.append(f"Loan closing on {loan['closing_date']} - timeline critical")

        return recommendations

    def _get_full_crm_details(self, match: Dict) -> Dict[str, Any]:
        """Get full CRM details for matched entities."""
        details = {}

        # Get loan details
        if match.get("matched_loan_id"):
            try:
                loan = self.db.execute(text("""
                    SELECT
                        id, loan_number, borrower_name, borrower_email,
                        loan_amount, property_address, loan_type, stage,
                        closing_date, lock_expiration
                    FROM loans
                    WHERE id = :loan_id
                """), {"loan_id": match["matched_loan_id"]}).fetchone()

                if loan:
                    details["loan"] = {
                        "id": loan[0],
                        "loan_number": loan[1],
                        "borrower_name": loan[2],
                        "borrower_email": loan[3],
                        "loan_amount": float(loan[4]) if loan[4] else None,
                        "property_address": loan[5],
                        "loan_type": loan[6],
                        "stage": loan[7],
                        "closing_date": loan[8].isoformat() if loan[8] else None,
                        "lock_expires": loan[9].isoformat() if loan[9] else None
                    }
            except Exception as e:
                logger.warning(f"Error fetching loan details: {e}")

        # Get lead details
        if match.get("matched_lead_id"):
            try:
                lead = self.db.execute(text("""
                    SELECT
                        id, name, email, phone, stage, source,
                        loan_amount, notes
                    FROM leads
                    WHERE id = :lead_id
                """), {"lead_id": match["matched_lead_id"]}).fetchone()

                if lead:
                    details["lead"] = {
                        "id": lead[0],
                        "name": lead[1],
                        "email": lead[2],
                        "phone": lead[3],
                        "stage": lead[4],
                        "source": lead[5],
                        "estimated_amount": float(lead[6]) if lead[6] else None,
                        "notes": lead[7]
                    }
            except Exception as e:
                logger.warning(f"Error fetching lead details: {e}")

        # Get contact details
        if match.get("matched_contact_id"):
            try:
                contact = self.db.execute(text("""
                    SELECT
                        id, first_name, last_name, email, phone,
                        contact_type, company
                    FROM contacts
                    WHERE id = :contact_id
                """), {"contact_id": match["matched_contact_id"]}).fetchone()

                if contact:
                    details["contact"] = {
                        "id": contact[0],
                        "first_name": contact[1],
                        "last_name": contact[2],
                        "email": contact[3],
                        "phone": contact[4],
                        "contact_type": contact[5],
                        "company": contact[6]
                    }
            except Exception as e:
                logger.warning(f"Error fetching contact details: {e}")

        return details


# ================================================================
# AI TOOL REGISTRY FOR LANGGRAPH/OPENAI FUNCTIONS
# ================================================================

TOOL_DEFINITIONS = {
    "search_emails_by_client": {
        "name": "search_emails_by_client",
        "description": (
            "Search for emails related to a specific client by name, email address, "
            "loan ID, or lead ID. Returns recent emails with match information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {
                    "type": "string",
                    "description": "Client's name (fuzzy match supported)"
                },
                "client_email": {
                    "type": "string",
                    "description": "Exact email address to search for"
                },
                "loan_id": {
                    "type": "integer",
                    "description": "Specific loan ID"
                },
                "lead_id": {
                    "type": "integer",
                    "description": "Specific lead ID"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back (default: 30)",
                    "default": 30
                },
                "include_unread_only": {
                    "type": "boolean",
                    "description": "Only include unread/pending emails",
                    "default": False
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 20)",
                    "default": 20
                }
            }
        }
    },

    "get_email_thread": {
        "name": "get_email_thread",
        "description": (
            "Get the complete email thread/conversation for a specific email. "
            "Useful for understanding context and conversation history."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "integer",
                    "description": "Specific email ID to get thread for"
                },
                "thread_id": {
                    "type": "string",
                    "description": "Thread ID to retrieve"
                }
            }
        }
    },

    "identify_email_sender": {
        "name": "identify_email_sender",
        "description": (
            "Identify who an email address belongs to in the CRM. Returns client "
            "information, loan/lead details, and confidence level."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "email_address": {
                    "type": "string",
                    "description": "Email address to identify"
                }
            },
            "required": ["email_address"]
        }
    },

    "get_priority_emails": {
        "name": "get_priority_emails",
        "description": (
            "Get high-priority emails requiring immediate attention. These are "
            "emails from known clients or flagged as urgent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Days to look back (default: 7)",
                    "default": 7
                },
                "unread_only": {
                    "type": "boolean",
                    "description": "Only unread emails (default: True)",
                    "default": True
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default: 20)",
                    "default": 20
                }
            }
        }
    },

    "search_emails_by_content": {
        "name": "search_emails_by_content",
        "description": (
            "Search emails by subject or body content. Useful for finding emails "
            "about specific topics, keywords, or issues."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "search_query": {
                    "type": "string",
                    "description": "Text to search for"
                },
                "keywords": {
                    "type": "string",
                    "description": "Alias for search_query (backward compatibility)"
                },
                "search_in": {
                    "type": "string",
                    "enum": ["subject", "body", "both"],
                    "description": "Where to search (default: both)",
                    "default": "both"
                },
                "days": {
                    "type": "integer",
                    "description": "Days to look back (default: 30)",
                    "default": 30
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default: 20)",
                    "default": 20
                }
            }
        }
    },

    "get_email_context_for_ai": {
        "name": "get_email_context_for_ai",
        "description": (
            "Get complete context about an email for AI decision-making. Includes "
            "email content, thread history, client CRM details, recent interactions, "
            "and AI-generated recommendations."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "integer",
                    "description": "Email ID to get full context for"
                }
            },
            "required": ["email_id"]
        }
    }
}


def get_tools_for_langgraph(db: Session, user_id: int) -> Dict[str, Any]:
    """
    Get tools configured for LangGraph agent use.

    Returns:
        Dictionary of tool names to callable functions
    """
    tools = EmailSearchTools(db, user_id)

    return {
        "search_emails_by_client": tools.search_emails_by_client,
        "get_email_thread": tools.get_email_thread,
        "identify_email_sender": tools.identify_email_sender,
        "get_priority_emails": tools.get_priority_emails,
        "search_emails_by_content": tools.search_emails_by_content,
        "get_email_context_for_ai": tools.get_email_context_for_ai
    }


def get_openai_tools_format() -> List[Dict[str, Any]]:
    """
    Get tool descriptions formatted for OpenAI function calling.

    Returns:
        List of tool definitions in OpenAI format
    """
    return [
        {
            "type": "function",
            "function": tool_def
        }
        for tool_def in TOOL_DEFINITIONS.values()
    ]


def get_tool_descriptions_for_openai() -> List[Dict[str, Any]]:
    """
    Get tool descriptions formatted for OpenAI function calling.
    (Alias for get_openai_tools_format)

    Returns:
        List of tool definitions in OpenAI format
    """
    return get_openai_tools_format()


# ================================================================
# Morning Briefing Helper
# ================================================================

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
    try:
        count_query = text("""
            SELECT COUNT(*) as count
            FROM email_reconciliation_queue
            WHERE user_id = :user_id
            AND status = 'pending'
            AND created_at > NOW() - INTERVAL '24 hours'
        """)
        recent_count = db.execute(count_query, {"user_id": user_id}).scalar() or 0
    except Exception as e:
        logger.error(f"Error getting recent email count: {e}")
        recent_count = 0

    briefing = {
        "date": datetime.now(timezone.utc).strftime("%A, %B %d, %Y"),
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
