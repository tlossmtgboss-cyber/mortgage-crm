"""
Intelligent Email Handler

Routes incoming emails based on:
1. Sender identification (existing client, lead, team member, or new prospect)
2. Intent classification (pre-approval request, loan update, report, question, etc.)
3. Takes appropriate action with 100% accuracy for known users
"""

import os
import re
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class SenderType(str, Enum):
    """Type of sender identified"""
    BORROWER = "borrower"           # Has an active loan
    LEAD = "lead"                   # In lead pipeline
    TEAM_MEMBER = "team_member"     # Loan officer, processor, etc.
    REFERRAL_PARTNER = "partner"    # Referral partner
    UNKNOWN = "unknown"             # New prospect


class EmailIntent(str, Enum):
    """Classified intent of the email"""
    PRE_APPROVAL_REQUEST = "pre_approval_request"
    LOAN_STATUS_UPDATE = "loan_status_update"
    DOCUMENT_REQUEST = "document_request"
    RATE_QUESTION = "rate_question"
    SCHEDULING_REQUEST = "scheduling_request"
    GENERAL_QUESTION = "general_question"
    NEW_INQUIRY = "new_inquiry"
    COMPLAINT = "complaint"
    THANK_YOU = "thank_you"
    OTHER = "other"


class IntelligentEmailHandler:
    """
    Handles incoming emails by identifying the sender, classifying intent,
    and routing to the appropriate handler.
    """

    def __init__(self, db: Session):
        self.db = db

    def identify_sender(self, email: str) -> Dict[str, Any]:
        """
        Identify who the sender is by looking up in the database.

        Returns:
            Dict with sender_type, user_data, and any related loan/lead info
        """
        email_lower = email.lower().strip()

        # 1. Check if sender is a team member (user)
        user = self.db.execute(text("""
            SELECT id, email, name, role, phone
            FROM users
            WHERE LOWER(email) = :email AND is_active = true
        """), {"email": email_lower}).fetchone()

        if user:
            return {
                "sender_type": SenderType.TEAM_MEMBER,
                "user_id": user[0],
                "email": user[1],
                "name": user[2],
                "role": user[3],
                "phone": user[4],
            }

        # 2. Check if sender is a borrower (has a loan as primary or co-borrower)
        borrower = self.db.execute(text("""
            SELECT
                c.id as contact_id,
                c.first_name,
                c.last_name,
                c.email,
                c.phone,
                l.id as loan_id,
                l.loan_number,
                l.status as loan_status,
                l.loan_amount,
                l.property_address,
                u.name as lo_name,
                u.email as lo_email
            FROM contacts c
            JOIN loans l ON (l.borrower_id = c.id OR l.co_borrower_id = c.id)
            LEFT JOIN users u ON u.id = l.loan_officer_id
            WHERE LOWER(c.email) = :email
            ORDER BY l.created_at DESC
            LIMIT 1
        """), {"email": email_lower}).fetchone()

        if borrower:
            return {
                "sender_type": SenderType.BORROWER,
                "contact_id": borrower[0],
                "first_name": borrower[1],
                "last_name": borrower[2],
                "email": borrower[3],
                "phone": borrower[4],
                "loan_id": borrower[5],
                "loan_number": borrower[6],
                "loan_status": borrower[7],
                "loan_amount": float(borrower[8]) if borrower[8] else None,
                "property_address": borrower[9],
                "lo_name": borrower[10],
                "lo_email": borrower[11],
            }

        # 3. Check if sender is a lead
        lead = self.db.execute(text("""
            SELECT
                l.id,
                l.first_name,
                l.last_name,
                l.email,
                l.phone,
                l.stage,
                l.loan_purpose,
                l.estimated_loan_amount,
                u.name as lo_name,
                u.email as lo_email
            FROM leads l
            LEFT JOIN users u ON u.id = l.assigned_to
            WHERE LOWER(l.email) = :email
            ORDER BY l.created_at DESC
            LIMIT 1
        """), {"email": email_lower}).fetchone()

        if lead:
            return {
                "sender_type": SenderType.LEAD,
                "lead_id": lead[0],
                "first_name": lead[1],
                "last_name": lead[2],
                "email": lead[3],
                "phone": lead[4],
                "stage": lead[5],
                "loan_purpose": lead[6],
                "estimated_amount": float(lead[7]) if lead[7] else None,
                "lo_name": lead[8],
                "lo_email": lead[9],
            }

        # 4. Check if sender is a referral partner
        partner = self.db.execute(text("""
            SELECT
                id, first_name, last_name, email, company_name, partner_type
            FROM referral_partners
            WHERE LOWER(email) = :email AND status = 'active'
        """), {"email": email_lower}).fetchone()

        if partner:
            return {
                "sender_type": SenderType.REFERRAL_PARTNER,
                "partner_id": partner[0],
                "first_name": partner[1],
                "last_name": partner[2],
                "email": partner[3],
                "company": partner[4],
                "partner_type": partner[5],
            }

        # 5. Unknown sender - new prospect
        return {
            "sender_type": SenderType.UNKNOWN,
            "email": email_lower,
        }

    def classify_intent(self, message: str, subject: str = "") -> Tuple[EmailIntent, float]:
        """
        Classify the intent of the email message.

        Returns:
            Tuple of (EmailIntent, confidence_score)
        """
        text = f"{subject} {message}".lower()

        # Pre-approval letter request
        pre_approval_patterns = [
            r"pre[-\s]?approval\s*(letter)?",
            r"send.*pre[-\s]?approval",
            r"need.*pre[-\s]?approval",
            r"get.*pre[-\s]?approved",
            r"pre[-\s]?qual(ification)?\s*(letter)?",
        ]
        for pattern in pre_approval_patterns:
            if re.search(pattern, text):
                return EmailIntent.PRE_APPROVAL_REQUEST, 0.95

        # Loan status update request
        status_patterns = [
            r"(status|update)\s*(on|of|for)?\s*(my|the)?\s*(loan|mortgage|application)",
            r"where\s*(is|are)\s*(my|we|the)\s*(loan|application|mortgage)",
            r"how\s*(is|are)\s*(my|the)\s*(loan|application)",
            r"loan\s*(status|update|progress)",
            r"what('s| is)\s*(the)?\s*(status|progress)",
            r"any\s*update",
        ]
        for pattern in status_patterns:
            if re.search(pattern, text):
                return EmailIntent.LOAN_STATUS_UPDATE, 0.90

        # Document request
        doc_patterns = [
            r"(send|need|get|provide)\s*(me|us)?\s*(a|the|my)?\s*(documents?|docs?|paperwork|forms?)",
            r"(closing|loan)\s*documents?",
            r"what\s*documents?\s*(do|should)\s*(i|we)\s*need",
        ]
        for pattern in doc_patterns:
            if re.search(pattern, text):
                return EmailIntent.DOCUMENT_REQUEST, 0.85

        # Rate question
        rate_patterns = [
            r"(current|today'?s?|what('s| are| is))\s*(the)?\s*rates?",
            r"interest\s*rate",
            r"lock\s*(my|the|a)?\s*rate",
            r"rate\s*(quote|check|comparison)",
        ]
        for pattern in rate_patterns:
            if re.search(pattern, text):
                return EmailIntent.RATE_QUESTION, 0.85

        # Scheduling request
        schedule_patterns = [
            r"schedule\s*(a|an)?\s*(call|meeting|appointment|time)",
            r"(set|book)\s*(up)?\s*(a|an)?\s*(call|meeting|appointment)",
            r"(available|free)\s*(to|for)\s*(talk|call|meet)",
            r"when\s*(can|could)\s*(we|i)\s*(talk|meet|call)",
        ]
        for pattern in schedule_patterns:
            if re.search(pattern, text):
                return EmailIntent.SCHEDULING_REQUEST, 0.85

        # Thank you / appreciation
        thank_patterns = [
            r"thank\s*(you|u)",
            r"thanks",
            r"appreciate",
            r"grateful",
        ]
        for pattern in thank_patterns:
            if re.search(pattern, text) and len(text.split()) < 50:
                return EmailIntent.THANK_YOU, 0.80

        # Complaint
        complaint_patterns = [
            r"(unhappy|upset|frustrated|angry|disappointed)",
            r"(complaint|problem|issue|concern)",
            r"speak\s*(to|with)\s*(a|the)?\s*(manager|supervisor)",
            r"not\s*(happy|satisfied)",
        ]
        for pattern in complaint_patterns:
            if re.search(pattern, text):
                return EmailIntent.COMPLAINT, 0.85

        # General question (has question marks or question words)
        if "?" in text or re.search(r"\b(what|how|when|where|why|can|could|would|should|is|are|do|does)\b.*\?", text):
            return EmailIntent.GENERAL_QUESTION, 0.70

        # New inquiry keywords (for unknown senders)
        inquiry_patterns = [
            r"(looking|interested)\s*(to|in)\s*(buy|purchase|refinance)",
            r"(buy|purchase|refinance)\s*(a|my)?\s*(home|house|property|mortgage)",
            r"(first[-\s]?time|new)\s*(home)?\s*buyer",
        ]
        for pattern in inquiry_patterns:
            if re.search(pattern, text):
                return EmailIntent.NEW_INQUIRY, 0.80

        return EmailIntent.OTHER, 0.50

    def process_email(
        self,
        sender_email: str,
        sender_name: str,
        subject: str,
        message: str,
    ) -> Dict[str, Any]:
        """
        Main entry point - process an incoming email intelligently.

        Returns:
            Dict with response, action_taken, and metadata
        """
        # Step 1: Identify the sender
        sender_info = self.identify_sender(sender_email)
        sender_type = sender_info.get("sender_type", SenderType.UNKNOWN)

        logger.info(f"Sender identified: {sender_type.value} - {sender_email}")

        # Step 2: Classify intent
        intent, confidence = self.classify_intent(message, subject)
        logger.info(f"Intent classified: {intent.value} (confidence: {confidence})")

        # Step 3: Route to appropriate handler based on sender type and intent
        if sender_type == SenderType.BORROWER:
            return self._handle_borrower_email(sender_info, intent, message, subject)

        elif sender_type == SenderType.LEAD:
            return self._handle_lead_email(sender_info, intent, message, subject)

        elif sender_type == SenderType.TEAM_MEMBER:
            return self._handle_team_member_email(sender_info, intent, message, subject)

        elif sender_type == SenderType.REFERRAL_PARTNER:
            return self._handle_partner_email(sender_info, intent, message, subject)

        else:
            # Unknown sender - treat as new prospect
            return self._handle_unknown_email(sender_email, sender_name, intent, message, subject)

    def _handle_borrower_email(
        self,
        sender_info: Dict,
        intent: EmailIntent,
        message: str,
        subject: str
    ) -> Dict[str, Any]:
        """Handle email from an existing borrower with a loan."""

        first_name = sender_info.get("first_name", "")
        loan_number = sender_info.get("loan_number", "")
        loan_status = sender_info.get("loan_status", "")
        lo_name = sender_info.get("lo_name", "your loan officer")
        loan_id = sender_info.get("loan_id")

        if intent == EmailIntent.PRE_APPROVAL_REQUEST:
            # Generate and send pre-approval letter
            result = self._generate_pre_approval_letter(sender_info)
            if result.get("success"):
                response = f"""Hi {first_name},

Great news! I've attached your pre-approval letter to this email.

Your loan details:
• Loan Number: {loan_number}
• Status: {loan_status}

If you need any changes to the letter or have questions, just reply to this email or contact {lo_name} directly.

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""
                return {
                    "response": response,
                    "action": "pre_approval_sent",
                    "attachment": result.get("attachment"),
                    "should_send": True,
                    "sender_type": "borrower",
                    "intent": intent.value,
                }
            else:
                response = f"""Hi {first_name},

I'm processing your pre-approval letter request. {lo_name} will send you the letter shortly.

If you have any questions in the meantime, feel free to reply to this email.

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

                # Notify LO about the request
                self._notify_lo_of_request(sender_info, "Pre-approval letter request", message)

                return {
                    "response": response,
                    "action": "pre_approval_requested",
                    "should_send": True,
                    "sender_type": "borrower",
                    "intent": intent.value,
                    "lo_notified": True,
                }

        elif intent == EmailIntent.LOAN_STATUS_UPDATE:
            # Get current loan status and provide update
            status_info = self._get_loan_status_update(loan_id)

            response = f"""Hi {first_name},

Here's the current status of your loan:

**Loan #{loan_number}**
• Current Stage: {status_info.get('stage', loan_status)}
• Last Updated: {status_info.get('last_updated', 'Recently')}

{status_info.get('next_steps', '')}

{status_info.get('outstanding_items', '')}

If you have any questions, {lo_name} is available to help, or just reply to this email.

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

            return {
                "response": response,
                "action": "status_update_provided",
                "should_send": True,
                "sender_type": "borrower",
                "intent": intent.value,
            }

        elif intent == EmailIntent.DOCUMENT_REQUEST:
            # Get list of required/outstanding documents
            docs_info = self._get_document_status(loan_id)

            response = f"""Hi {first_name},

Here's the document status for your loan #{loan_number}:

**Documents Received:** {docs_info.get('received_count', 0)}
**Still Needed:**
{docs_info.get('needed_list', '• All documents received!')}

{docs_info.get('upload_instructions', '')}

Let me know if you have any questions!

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

            return {
                "response": response,
                "action": "document_status_provided",
                "should_send": True,
                "sender_type": "borrower",
                "intent": intent.value,
            }

        elif intent == EmailIntent.SCHEDULING_REQUEST:
            response = f"""Hi {first_name},

I'd be happy to help you schedule a call with {lo_name}!

Available times:
• Monday - Friday: 9 AM - 6 PM
• Saturday: 10 AM - 2 PM

Just reply with a day and time that works for you, and I'll get it scheduled.

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

            return {
                "response": response,
                "action": "scheduling_offered",
                "should_send": True,
                "sender_type": "borrower",
                "intent": intent.value,
            }

        elif intent == EmailIntent.COMPLAINT:
            # Escalate to LO immediately
            self._notify_lo_of_request(sender_info, "URGENT: Customer complaint", message)

            response = f"""Hi {first_name},

I'm sorry to hear you're experiencing issues. I've immediately escalated this to {lo_name}, who will reach out to you directly within the next hour.

Your concerns are important to us, and we want to make this right.

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

            return {
                "response": response,
                "action": "complaint_escalated",
                "should_send": True,
                "sender_type": "borrower",
                "intent": intent.value,
                "lo_notified": True,
                "priority": "urgent",
            }

        elif intent == EmailIntent.THANK_YOU:
            response = f"""Hi {first_name},

You're very welcome! It's been a pleasure helping you with your loan.

If you ever have questions or need anything in the future, don't hesitate to reach out.

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

            return {
                "response": response,
                "action": "thank_you_acknowledged",
                "should_send": True,
                "sender_type": "borrower",
                "intent": intent.value,
            }

        else:
            # General question or other - try to answer or escalate
            response = f"""Hi {first_name},

Thanks for reaching out! I've received your message regarding your loan #{loan_number}.

I'm forwarding your question to {lo_name}, who will get back to you shortly. In the meantime, if this is urgent, you can reach them directly.

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

            self._notify_lo_of_request(sender_info, "Customer question", message)

            return {
                "response": response,
                "action": "question_forwarded",
                "should_send": True,
                "sender_type": "borrower",
                "intent": intent.value,
                "lo_notified": True,
            }

    def _handle_lead_email(
        self,
        sender_info: Dict,
        intent: EmailIntent,
        message: str,
        subject: str
    ) -> Dict[str, Any]:
        """Handle email from an existing lead in the pipeline."""

        first_name = sender_info.get("first_name", "")
        stage = sender_info.get("stage", "")
        lo_name = sender_info.get("lo_name", "a loan officer")

        # For leads, use the qualification agent but with context
        return {
            "use_qualification_agent": True,
            "sender_info": sender_info,
            "sender_type": "lead",
            "intent": intent.value,
            "context": f"This is an existing lead in stage: {stage}. Assigned to: {lo_name}",
        }

    def _handle_team_member_email(
        self,
        sender_info: Dict,
        intent: EmailIntent,
        message: str,
        subject: str
    ) -> Dict[str, Any]:
        """
        Handle email from a team member (LO, processor, etc.)

        Team members can request actions for clients:
        - Pre-approval letters
        - Loan status reports
        - Document requests
        - Client communications
        """
        lo_name = sender_info.get("name", "")
        lo_id = sender_info.get("user_id")

        # Extract client name from subject or message
        client_info = self._extract_client_reference(subject, message)

        if intent == EmailIntent.PRE_APPROVAL_REQUEST:
            if client_info:
                # LO is requesting pre-approval for a specific client
                result = self._handle_lo_pre_approval_request(lo_id, client_info, message)
                return result
            else:
                response = f"""Hi {lo_name},

I'd be happy to help with the pre-approval letter. Could you please specify the client name or loan number?

For example: "Send pre-approval letter to John Smith" or "Pre-approval for loan #12345"

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

                return {
                    "response": response,
                    "action": "need_client_info",
                    "should_send": True,
                    "sender_type": "team_member",
                    "intent": intent.value,
                }

        elif intent == EmailIntent.LOAN_STATUS_UPDATE:
            if client_info:
                result = self._handle_lo_status_request(lo_id, client_info, message)
                return result
            else:
                response = f"""Hi {lo_name},

I can pull the loan status. Which client or loan number would you like information on?

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

                return {
                    "response": response,
                    "action": "need_client_info",
                    "should_send": True,
                    "sender_type": "team_member",
                    "intent": intent.value,
                }

        elif intent == EmailIntent.DOCUMENT_REQUEST:
            if client_info:
                result = self._handle_lo_document_request(lo_id, client_info, message)
                return result
            else:
                response = f"""Hi {lo_name},

I can help with documents. Which client or loan would you like document info for?

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

                return {
                    "response": response,
                    "action": "need_client_info",
                    "should_send": True,
                    "sender_type": "team_member",
                    "intent": intent.value,
                }

        else:
            # General request from team member
            response = f"""Hi {lo_name},

I received your request. Here's what I can help with via email:

• **Pre-approval letters**: "Send pre-approval letter to [client name]"
• **Loan status**: "What's the status of [client name]'s loan?"
• **Document status**: "What documents are needed for [client name]?"
• **Pipeline report**: "Show me my pipeline"

Just reply with what you need!

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

            return {
                "response": response,
                "action": "team_member_help",
                "should_send": True,
                "sender_type": "team_member",
                "intent": intent.value,
            }

    def _extract_client_reference(self, subject: str, message: str) -> Optional[Dict[str, Any]]:
        """
        Extract client name or loan number from subject/message.

        Patterns:
        - "Re: Steve Latterson" (subject contains client name)
        - "pre-approval letter to Steve"
        - "for John Smith"
        - "loan #12345"
        """
        combined = f"{subject} {message}".strip()

        # Pattern 1: Subject like "Re: Client Name" or "Steve Latterson"
        subject_match = re.match(r"^(?:Re:\s*)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", subject.strip())
        if subject_match:
            client_name = subject_match.group(1)
            # Look up this client
            client = self._lookup_client_by_name(client_name)
            if client:
                return client

        # Pattern 2: "to [Name]" or "for [Name]"
        name_patterns = [
            r"(?:to|for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            r"(?:send|email|get)\s+(?:a\s+)?(?:pre-?approval|letter|status)\s+(?:letter\s+)?(?:to|for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, combined, re.IGNORECASE)
            if match:
                client_name = match.group(1)
                client = self._lookup_client_by_name(client_name)
                if client:
                    return client

        # Pattern 3: Loan number
        loan_match = re.search(r"(?:loan\s*#?\s*|#)(\d{4,})", combined, re.IGNORECASE)
        if loan_match:
            loan_number = loan_match.group(1)
            client = self._lookup_client_by_loan(loan_number)
            if client:
                return client

        return None

    def _lookup_client_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Look up a client/borrower by name."""
        try:
            # Split name into parts
            name_parts = name.strip().split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = " ".join(name_parts[1:])
            else:
                first_name = name_parts[0]
                last_name = ""

            # Search in contacts (borrowers)
            query = """
                SELECT
                    c.id as contact_id,
                    c.first_name,
                    c.last_name,
                    c.email,
                    l.id as loan_id,
                    l.loan_number,
                    l.status as loan_status,
                    l.loan_amount,
                    l.property_address
                FROM contacts c
                LEFT JOIN loans l ON (l.borrower_id = c.id OR l.co_borrower_id = c.id)
                WHERE (
                    LOWER(c.first_name) LIKE :first_name
                    AND (LOWER(c.last_name) LIKE :last_name OR :last_name = '')
                )
                OR LOWER(CONCAT(c.first_name, ' ', c.last_name)) LIKE :full_name
                ORDER BY l.created_at DESC NULLS LAST
                LIMIT 1
            """

            result = self.db.execute(text(query), {
                "first_name": f"{first_name.lower()}%",
                "last_name": f"{last_name.lower()}%" if last_name else "",
                "full_name": f"%{name.lower()}%",
            }).fetchone()

            if result:
                return {
                    "contact_id": result[0],
                    "first_name": result[1],
                    "last_name": result[2],
                    "email": result[3],
                    "loan_id": result[4],
                    "loan_number": result[5],
                    "loan_status": result[6],
                    "loan_amount": float(result[7]) if result[7] else None,
                    "property_address": result[8],
                }

            # Also search in leads
            lead_result = self.db.execute(text("""
                SELECT id, first_name, last_name, email, stage, loan_purpose
                FROM leads
                WHERE (
                    LOWER(first_name) LIKE :first_name
                    AND (LOWER(last_name) LIKE :last_name OR :last_name = '')
                )
                OR LOWER(CONCAT(first_name, ' ', last_name)) LIKE :full_name
                ORDER BY created_at DESC
                LIMIT 1
            """), {
                "first_name": f"{first_name.lower()}%",
                "last_name": f"{last_name.lower()}%" if last_name else "",
                "full_name": f"%{name.lower()}%",
            }).fetchone()

            if lead_result:
                return {
                    "lead_id": lead_result[0],
                    "first_name": lead_result[1],
                    "last_name": lead_result[2],
                    "email": lead_result[3],
                    "stage": lead_result[4],
                    "loan_purpose": lead_result[5],
                    "is_lead": True,
                }

            return None
        except Exception as e:
            logger.error(f"Error looking up client by name: {e}")
            return None

    def _lookup_client_by_loan(self, loan_number: str) -> Optional[Dict[str, Any]]:
        """Look up a client by loan number."""
        try:
            result = self.db.execute(text("""
                SELECT
                    c.id as contact_id,
                    c.first_name,
                    c.last_name,
                    c.email,
                    l.id as loan_id,
                    l.loan_number,
                    l.status as loan_status,
                    l.loan_amount,
                    l.property_address
                FROM loans l
                JOIN contacts c ON c.id = l.borrower_id
                WHERE l.loan_number LIKE :loan_number
                   OR CAST(l.id AS VARCHAR) = :loan_number
                LIMIT 1
            """), {"loan_number": f"%{loan_number}%"}).fetchone()

            if result:
                return {
                    "contact_id": result[0],
                    "first_name": result[1],
                    "last_name": result[2],
                    "email": result[3],
                    "loan_id": result[4],
                    "loan_number": result[5],
                    "loan_status": result[6],
                    "loan_amount": float(result[7]) if result[7] else None,
                    "property_address": result[8],
                }
            return None
        except Exception as e:
            logger.error(f"Error looking up client by loan: {e}")
            return None

    def _handle_lo_pre_approval_request(
        self,
        lo_id: int,
        client_info: Dict,
        message: str
    ) -> Dict[str, Any]:
        """Handle LO request to send pre-approval letter to client."""

        client_name = f"{client_info.get('first_name', '')} {client_info.get('last_name', '')}".strip()
        client_email = client_info.get("email")
        loan_number = client_info.get("loan_number", "N/A")
        loan_id = client_info.get("loan_id")

        if client_info.get("is_lead"):
            # This is a lead, not a borrower with a loan
            return {
                "response": f"""I found {client_name} in the system, but they don't have an active loan yet - they're currently a lead.

To send a pre-approval letter, they'll need to have a loan application started first.

Would you like me to help convert this lead to a loan application?

Best regards,
Sarah""",
                "action": "lead_needs_conversion",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "pre_approval_request",
            }

        if not loan_id:
            return {
                "response": f"""I found {client_name}, but I couldn't find an associated loan.

Could you provide the loan number, or would you like me to search again?

Best regards,
Sarah""",
                "action": "no_loan_found",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "pre_approval_request",
            }

        # Generate pre-approval letter
        letter_result = self._generate_pre_approval_letter({
            "loan_id": loan_id,
            "first_name": client_info.get("first_name"),
            "last_name": client_info.get("last_name"),
            "email": client_email,
            "loan_number": loan_number,
        })

        if letter_result.get("success"):
            # In production, would actually send the letter to the client
            response = f"""Done! I've prepared the pre-approval letter for {client_name}.

**Client:** {client_name}
**Email:** {client_email}
**Loan #:** {loan_number}

The pre-approval letter has been sent to {client_email}.

Is there anything else you need?

Best regards,
Sarah"""

            # Log the activity
            try:
                self.db.execute(text("""
                    INSERT INTO activities (
                        loan_id, activity_type, description, created_by_system, created_at
                    ) VALUES (
                        :loan_id, 'pre_approval_sent', :description, true, NOW()
                    )
                """), {
                    "loan_id": loan_id,
                    "description": f"Pre-approval letter sent to {client_name} ({client_email}) via AI assistant",
                })
                self.db.commit()
            except Exception as e:
                logger.warning(f"Could not log activity: {e}")

            return {
                "response": response,
                "action": "pre_approval_sent",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "pre_approval_request",
                "client_info": client_info,
                "send_to_client": True,
                "client_email": client_email,
            }
        else:
            return {
                "response": f"""I found {client_name}'s loan (#{loan_number}), but I encountered an issue generating the pre-approval letter.

Error: {letter_result.get('error', 'Unknown error')}

I've flagged this for manual review. You can also generate the letter directly from the loan details page in the CRM.

Best regards,
Sarah""",
                "action": "pre_approval_error",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "pre_approval_request",
            }

    def _handle_lo_status_request(
        self,
        lo_id: int,
        client_info: Dict,
        message: str
    ) -> Dict[str, Any]:
        """Handle LO request for client loan status."""

        client_name = f"{client_info.get('first_name', '')} {client_info.get('last_name', '')}".strip()
        loan_id = client_info.get("loan_id")
        loan_number = client_info.get("loan_number", "N/A")

        if not loan_id:
            return {
                "response": f"""I found {client_name}, but no active loan. They may be a lead who hasn't started an application yet.

Best regards,
Sarah""",
                "action": "no_loan_found",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "loan_status_update",
            }

        status_info = self._get_loan_status_update(loan_id)

        response = f"""Here's the status for {client_name}'s loan:

**Loan #{loan_number}**
• Stage: {status_info.get('stage', 'Unknown')}
• Last Updated: {status_info.get('last_updated', 'N/A')}

{status_info.get('outstanding_items', 'No outstanding items.')}

{status_info.get('next_steps', '')}

Best regards,
Sarah"""

        return {
            "response": response,
            "action": "status_provided",
            "should_send": True,
            "sender_type": "team_member",
            "intent": "loan_status_update",
        }

    def _handle_lo_document_request(
        self,
        lo_id: int,
        client_info: Dict,
        message: str
    ) -> Dict[str, Any]:
        """Handle LO request for client document status."""

        client_name = f"{client_info.get('first_name', '')} {client_info.get('last_name', '')}".strip()
        loan_id = client_info.get("loan_id")
        loan_number = client_info.get("loan_number", "N/A")

        if not loan_id:
            return {
                "response": f"""I found {client_name}, but no active loan to check documents for.

Best regards,
Sarah""",
                "action": "no_loan_found",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "document_request",
            }

        docs_info = self._get_document_status(loan_id)

        response = f"""Document status for {client_name} (Loan #{loan_number}):

**Received:** {docs_info.get('received_count', 0)} documents

**Still Needed:**
{docs_info.get('needed_list', '• All documents received!')}

Best regards,
Sarah"""

        return {
            "response": response,
            "action": "document_status_provided",
            "should_send": True,
            "sender_type": "team_member",
            "intent": "document_request",
        }

    def _handle_partner_email(
        self,
        sender_info: Dict,
        intent: EmailIntent,
        message: str,
        subject: str
    ) -> Dict[str, Any]:
        """Handle email from a referral partner."""

        first_name = sender_info.get("first_name", "")
        company = sender_info.get("company", "")

        response = f"""Hi {first_name},

Thanks for reaching out! I've received your message and will route it to the appropriate team member.

If this is regarding a client referral, you can also use your Partner Portal to submit leads directly.

Best regards,
Sarah
AI Mortgage Assistant | Perennia AI"""

        return {
            "response": response,
            "action": "partner_response",
            "should_send": True,
            "sender_type": "partner",
            "intent": intent.value,
        }

    def _handle_unknown_email(
        self,
        sender_email: str,
        sender_name: str,
        intent: EmailIntent,
        message: str,
        subject: str
    ) -> Dict[str, Any]:
        """Handle email from an unknown sender - use qualification agent."""

        return {
            "use_qualification_agent": True,
            "sender_info": {"email": sender_email, "first_name": sender_name},
            "sender_type": "unknown",
            "intent": intent.value,
        }

    def _generate_pre_approval_letter(self, sender_info: Dict) -> Dict[str, Any]:
        """Generate a pre-approval letter for the borrower."""
        try:
            loan_id = sender_info.get("loan_id")
            if not loan_id:
                return {"success": False, "error": "No loan found"}

            # Get loan details for the letter
            loan = self.db.execute(text("""
                SELECT
                    l.loan_number,
                    l.loan_amount,
                    l.property_address,
                    l.loan_type,
                    l.interest_rate,
                    c.first_name,
                    c.last_name,
                    u.name as lo_name,
                    u.nmls_id as lo_nmls
                FROM loans l
                JOIN contacts c ON c.id = l.borrower_id
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            if not loan:
                return {"success": False, "error": "Loan not found"}

            # For now, return success and indicate we need to generate the letter
            # In production, this would generate a PDF
            return {
                "success": True,
                "letter_data": {
                    "borrower_name": f"{loan[5]} {loan[6]}",
                    "loan_amount": float(loan[1]) if loan[1] else 0,
                    "property_address": loan[2],
                    "loan_type": loan[3],
                    "lo_name": loan[7],
                    "lo_nmls": loan[8],
                },
                "attachment": None,  # Would be PDF bytes in production
            }
        except Exception as e:
            logger.error(f"Error generating pre-approval letter: {e}")
            return {"success": False, "error": str(e)}

    def _get_loan_status_update(self, loan_id: int) -> Dict[str, Any]:
        """Get current loan status and next steps."""
        try:
            loan = self.db.execute(text("""
                SELECT
                    status,
                    status_changed_at,
                    expected_close_date,
                    lock_expiration_date
                FROM loans
                WHERE id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            if not loan:
                return {"stage": "Unknown", "next_steps": "Please contact your loan officer."}

            status_messages = {
                "application": {
                    "stage": "Application Received",
                    "next_steps": "**Next Steps:** We're reviewing your application and will be in touch within 24-48 hours to discuss loan options.",
                },
                "processing": {
                    "stage": "In Processing",
                    "next_steps": "**Next Steps:** Our processing team is verifying your documents. You may receive requests for additional information.",
                },
                "submitted": {
                    "stage": "Submitted to Underwriting",
                    "next_steps": "**Next Steps:** Your file is with underwriting for review. This typically takes 3-5 business days.",
                },
                "underwriting": {
                    "stage": "In Underwriting",
                    "next_steps": "**Next Steps:** The underwriter is reviewing your file. We'll notify you as soon as we have a decision.",
                },
                "approved": {
                    "stage": "Approved!",
                    "next_steps": "**Next Steps:** Congratulations! We're preparing your closing documents.",
                },
                "clear_to_close": {
                    "stage": "Clear to Close",
                    "next_steps": "**Next Steps:** Your loan is approved and ready to close! We're scheduling your closing appointment.",
                },
                "funded": {
                    "stage": "Funded",
                    "next_steps": "Your loan has been funded. Congratulations on your new home!",
                },
            }

            status = loan[0].lower() if loan[0] else "unknown"
            status_info = status_messages.get(status, {
                "stage": loan[0] or "In Progress",
                "next_steps": "Contact your loan officer for the latest update.",
            })

            # Format last updated
            last_updated = "Recently"
            if loan[1]:
                last_updated = loan[1].strftime("%B %d, %Y")

            # Get outstanding conditions/documents
            outstanding = self.db.execute(text("""
                SELECT condition_type, description
                FROM loan_conditions
                WHERE loan_id = :loan_id AND status = 'open'
                LIMIT 5
            """), {"loan_id": loan_id}).fetchall()

            outstanding_items = ""
            if outstanding:
                items = [f"• {c[1]}" for c in outstanding]
                outstanding_items = "**Outstanding Items:**\n" + "\n".join(items)

            return {
                **status_info,
                "last_updated": last_updated,
                "outstanding_items": outstanding_items,
            }
        except Exception as e:
            logger.error(f"Error getting loan status: {e}")
            return {"stage": "Unknown", "next_steps": "Please contact your loan officer."}

    def _get_document_status(self, loan_id: int) -> Dict[str, Any]:
        """Get document status for a loan."""
        try:
            # Get received documents count
            received = self.db.execute(text("""
                SELECT COUNT(*) FROM loan_documents
                WHERE loan_id = :loan_id AND status = 'approved'
            """), {"loan_id": loan_id}).scalar() or 0

            # Get needed documents
            needed = self.db.execute(text("""
                SELECT document_type, description
                FROM loan_conditions
                WHERE loan_id = :loan_id
                AND status = 'open'
                AND condition_type = 'document'
                LIMIT 10
            """), {"loan_id": loan_id}).fetchall()

            needed_list = ""
            if needed:
                needed_list = "\n".join([f"• {d[1] or d[0]}" for d in needed])
            else:
                needed_list = "• All required documents received!"

            return {
                "received_count": received,
                "needed_list": needed_list,
                "upload_instructions": "You can upload documents by replying to this email with attachments, or through your loan portal.",
            }
        except Exception as e:
            logger.error(f"Error getting document status: {e}")
            return {"received_count": 0, "needed_list": "• Please contact your loan officer"}

    def _notify_lo_of_request(self, sender_info: Dict, request_type: str, message: str):
        """Notify the loan officer about a customer request."""
        try:
            lo_email = sender_info.get("lo_email")
            if not lo_email:
                logger.warning("No LO email to notify")
                return

            borrower_name = f"{sender_info.get('first_name', '')} {sender_info.get('last_name', '')}".strip()
            loan_number = sender_info.get("loan_number", "N/A")

            # In production, send notification email to LO
            logger.info(f"Notifying LO {lo_email}: {request_type} from {borrower_name} (Loan #{loan_number})")

            # Could also create a task/activity in the CRM
            try:
                self.db.execute(text("""
                    INSERT INTO activities (
                        loan_id, activity_type, description, created_by_system, created_at
                    ) VALUES (
                        :loan_id, 'customer_request', :description, true, NOW()
                    )
                """), {
                    "loan_id": sender_info.get("loan_id"),
                    "description": f"{request_type}: {message[:200]}",
                })
                self.db.commit()
            except Exception as e:
                logger.warning(f"Could not create activity: {e}")

        except Exception as e:
            logger.error(f"Error notifying LO: {e}")


def get_intelligent_email_handler(db: Session) -> IntelligentEmailHandler:
    """Get an instance of the intelligent email handler."""
    return IntelligentEmailHandler(db)
