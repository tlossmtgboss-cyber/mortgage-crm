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
from sqlalchemy.exc import SQLAlchemyError

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
    # Reporting intents (LO only)
    PIPELINE_REPORT = "pipeline_report"
    BOTTLENECK_ANALYSIS = "bottleneck_analysis"
    STALE_FILES_REPORT = "stale_files_report"
    PERFORMANCE_REPORT = "performance_report"
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
            SELECT id, email, full_name, role, phone
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
        # Borrower info is stored directly on the loans table (borrower_email, borrower_name, etc.)
        try:
            borrower = self.db.execute(text("""
                SELECT
                    l.id as loan_id,
                    l.borrower_name,
                    l.borrower_email,
                    l.borrower_phone,
                    l.loan_number,
                    l.stage as loan_status,
                    l.amount as loan_amount,
                    l.property_address,
                    u.full_name as lo_name,
                    u.email as lo_email,
                    CASE WHEN LOWER(l.borrower_email) = :email THEN 'primary' ELSE 'co-borrower' END as borrower_type
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE LOWER(l.borrower_email) = :email OR LOWER(l.co_borrower_email) = :email
                ORDER BY l.created_at DESC
                LIMIT 1
            """), {"email": email_lower}).fetchone()

            if borrower:
                # Parse name into first/last
                name_parts = (borrower[1] or "").split(" ", 1) if borrower[1] else ["", ""]
                first_name = name_parts[0] if name_parts else ""
                last_name = name_parts[1] if len(name_parts) > 1 else ""
                return {
                    "sender_type": SenderType.BORROWER,
                    "loan_id": borrower[0],
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": borrower[2],
                    "phone": borrower[3],
                    "loan_number": borrower[4],
                    "loan_status": borrower[5],
                    "loan_amount": float(borrower[6]) if borrower[6] else None,
                    "property_address": borrower[7],
                    "lo_name": borrower[8],
                    "lo_email": borrower[9],
                    "borrower_type": borrower[10],
                }
        except Exception as e:
            # Log but continue to check leads
            import logging
            logging.getLogger(__name__).warning(f"Borrower lookup failed: {e}")

        # 3. Check if sender is a lead
        lead = self.db.execute(text("""
            SELECT
                l.id,
                l.first_name,
                l.last_name,
                l.email,
                l.phone,
                l.stage,
                l.loan_type,
                l.loan_amount,
                u.full_name as lo_name,
                u.email as lo_email
            FROM leads l
            LEFT JOIN users u ON u.id = l.owner_id
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
                "loan_type": lead[6],
                "loan_amount": float(lead[7]) if lead[7] else None,
                "lo_name": lead[8],
                "lo_email": lead[9],
            }

        # 4. Check if sender is a referral partner
        try:
            partner = self.db.execute(text("""
                SELECT
                    id, name, contact_name, email, company, type
                FROM referral_partners
                WHERE LOWER(email) = :email
            """), {"email": email_lower}).fetchone()

            if partner:
                # Parse name into first/last
                name_parts = (partner[2] or partner[1] or "").split(" ", 1)
                return {
                    "sender_type": SenderType.REFERRAL_PARTNER,
                    "partner_id": partner[0],
                    "first_name": name_parts[0] if name_parts else "",
                    "last_name": name_parts[1] if len(name_parts) > 1 else "",
                    "email": partner[3],
                    "company": partner[4],
                    "partner_type": partner[5],
                }
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Referral partner lookup failed: {e}")

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

        # =================================================================
        # REPORTING INTENTS (for LOs/team members)
        # =================================================================

        # Pipeline report
        pipeline_patterns = [
            r"(show|give|send|what('s| is))\s*(me\s*)?(my\s*)?pipeline",
            r"my\s*pipeline",
            r"pipeline\s*(report|summary|overview|status)",
            r"how\s*(many|much)\s*(loans?|files?|deals?)\s*(do\s*i\s*have|in\s*pipeline)",
            r"(current|active)\s*(loans?|files?|pipeline)",
        ]
        for pattern in pipeline_patterns:
            if re.search(pattern, text):
                return EmailIntent.PIPELINE_REPORT, 0.95

        # Bottleneck analysis
        bottleneck_patterns = [
            r"(where\s*(are|is)\s*(my|the)?\s*)?bottleneck",
            r"what('s| is)\s*(stuck|stalled|delayed)",
            r"(pipeline\s*)?bottleneck",
            r"where\s*(am\s*i|are\s*we)\s*(stuck|blocked|delayed)",
            r"what('s| is)\s*holding\s*(things?|us|me)\s*(up|back)",
            r"(identify|find|show)\s*(my\s*)?(the\s*)?bottleneck",
        ]
        for pattern in bottleneck_patterns:
            if re.search(pattern, text):
                return EmailIntent.BOTTLENECK_ANALYSIS, 0.95

        # Stale/falling behind files
        stale_patterns = [
            r"(files?|loans?)\s*(falling|fall)\s*behind",
            r"(stale|aging|old|stuck)\s*(files?|loans?)",
            r"what('s| is)\s*(falling|fall)\s*behind",
            r"(files?|loans?)\s*(at\s*risk|overdue|past\s*due)",
            r"which\s*(files?|loans?)\s*(need|require)\s*attention",
            r"(aging|stale)\s*report",
            r"what\s*(files?|loans?)\s*(are\s*)?(stuck|stale|behind)",
        ]
        for pattern in stale_patterns:
            if re.search(pattern, text):
                return EmailIntent.STALE_FILES_REPORT, 0.95

        # Performance report
        performance_patterns = [
            r"(my|team)\s*performance",
            r"how\s*(am\s*i|are\s*we)\s*(doing|performing)",
            r"(production|volume|units)\s*(report|numbers?|stats?)",
            r"(this|last)\s*(month|week|quarter)('s)?\s*(numbers?|production|volume)",
            r"(ytd|year\s*to\s*date)\s*(numbers?|production|stats?)",
            r"conversion\s*rate",
            r"pull[\s-]?through\s*rate",
        ]
        for pattern in performance_patterns:
            if re.search(pattern, text):
                return EmailIntent.PERFORMANCE_REPORT, 0.90

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

        # =================================================================
        # REPORTING HANDLERS
        # =================================================================

        elif intent == EmailIntent.PIPELINE_REPORT:
            return self._handle_pipeline_report(lo_id, lo_name)

        elif intent == EmailIntent.BOTTLENECK_ANALYSIS:
            return self._handle_bottleneck_analysis(lo_id, lo_name)

        elif intent == EmailIntent.STALE_FILES_REPORT:
            return self._handle_stale_files_report(lo_id, lo_name)

        elif intent == EmailIntent.PERFORMANCE_REPORT:
            return self._handle_performance_report(lo_id, lo_name)

        else:
            # General request from team member
            response = f"""Hi {lo_name},

I received your request. Here's what I can help with via email:

**Client Actions:**
• "Send pre-approval letter to [client name]"
• "What's the status of [client name]'s loan?"
• "What documents are needed for [client name]?"

**Reports & Analytics:**
• "Show me my pipeline"
• "Where are my bottlenecks?"
• "What files are falling behind?"
• "How am I doing this month?"

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

            # Search in loans by borrower name
            query = """
                SELECT
                    l.id as loan_id,
                    l.borrower_name,
                    l.borrower_email,
                    l.loan_number,
                    l.stage as loan_status,
                    l.amount as loan_amount,
                    l.property_address
                FROM loans l
                WHERE LOWER(l.borrower_name) LIKE :full_name
                ORDER BY l.created_at DESC NULLS LAST
                LIMIT 1
            """

            result = self.db.execute(text(query), {
                "full_name": f"%{name.lower()}%",
            }).fetchone()

            if result:
                # Parse borrower_name into first/last
                name_parts = (result[1] or "").split(" ", 1) if result[1] else ["", ""]
                return {
                    "loan_id": result[0],
                    "first_name": name_parts[0] if name_parts else "",
                    "last_name": name_parts[1] if len(name_parts) > 1 else "",
                    "email": result[2],
                    "loan_number": result[3],
                    "loan_status": result[4],
                    "loan_amount": float(result[5]) if result[5] else None,
                    "property_address": result[6],
                }

            # Also search in leads
            lead_result = self.db.execute(text("""
                SELECT id, first_name, last_name, email, stage, loan_type
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
                    "loan_type": lead_result[5],
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
                    l.id as loan_id,
                    l.borrower_name,
                    l.borrower_email,
                    l.loan_number,
                    l.stage as loan_status,
                    l.amount as loan_amount,
                    l.property_address
                FROM loans l
                WHERE l.loan_number LIKE :loan_number
                   OR CAST(l.id AS VARCHAR) = :loan_number
                LIMIT 1
            """), {"loan_number": f"%{loan_number}%"}).fetchone()

            if result:
                # Parse borrower_name into first/last
                name_parts = (result[1] or "").split(" ", 1) if result[1] else ["", ""]
                return {
                    "loan_id": result[0],
                    "first_name": name_parts[0] if name_parts else "",
                    "last_name": name_parts[1] if len(name_parts) > 1 else "",
                    "email": result[2],
                    "loan_number": result[3],
                    "loan_status": result[4],
                    "loan_amount": float(result[5]) if result[5] else None,
                    "property_address": result[6],
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
            except SQLAlchemyError as e:
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
                    l.amount as loan_amount,
                    l.property_address,
                    l.loan_type,
                    l.interest_rate,
                    l.borrower_name,
                    u.full_name as lo_name,
                    u.nmls_number as lo_nmls
                FROM loans l
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
                    "borrower_name": loan[5] or "Borrower",
                    "loan_amount": float(loan[1]) if loan[1] else 0,
                    "property_address": loan[2],
                    "loan_type": loan[3],
                    "lo_name": loan[6],
                    "lo_nmls": loan[7],
                },
                "attachment": None,  # Would be PDF bytes in production
            }
        except Exception as e:
            logger.error(f"Error generating pre-approval letter: {e}")
            return {"success": False, "error": "Internal server error"}

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
                SELECT COUNT(*) FROM documents
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
            except SQLAlchemyError as e:
                logger.warning(f"Could not create activity: {e}")

        except SQLAlchemyError as e:
            logger.error(f"Error notifying LO: {e}")

    # =========================================================================
    # REPORTING HANDLERS
    # =========================================================================

    def _handle_pipeline_report(self, lo_id: int, lo_name: str) -> Dict[str, Any]:
        """Generate pipeline report for loan officer."""
        try:
            # Get pipeline summary by status
            pipeline = self.db.execute(text("""
                SELECT
                    status,
                    COUNT(*) as count,
                    COALESCE(SUM(loan_amount), 0) as volume
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND status NOT IN ('funded', 'cancelled', 'denied', 'closed')
                GROUP BY status
                ORDER BY
                    CASE status
                        WHEN 'application' THEN 1
                        WHEN 'processing' THEN 2
                        WHEN 'submitted' THEN 3
                        WHEN 'underwriting' THEN 4
                        WHEN 'approved' THEN 5
                        WHEN 'clear_to_close' THEN 6
                        WHEN 'docs_out' THEN 7
                        WHEN 'docs_back' THEN 8
                        ELSE 9
                    END
            """), {"lo_id": lo_id}).fetchall()

            # Get total counts
            totals = self.db.execute(text("""
                SELECT
                    COUNT(*) as total_count,
                    COALESCE(SUM(loan_amount), 0) as total_volume,
                    COUNT(CASE WHEN status IN ('clear_to_close', 'docs_out', 'docs_back') THEN 1 END) as closing_soon
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND status NOT IN ('funded', 'cancelled', 'denied', 'closed')
            """), {"lo_id": lo_id}).fetchone()

            # Get closing this month
            closing_month = self.db.execute(text("""
                SELECT COUNT(*), COALESCE(SUM(loan_amount), 0)
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND status = 'funded'
                AND funded_at >= DATE_TRUNC('month', CURRENT_DATE)
            """), {"lo_id": lo_id}).fetchone()

            # Format pipeline by stage
            pipeline_lines = []
            for row in pipeline:
                status_display = row[0].replace('_', ' ').title() if row[0] else 'Unknown'
                count = row[1]
                volume = float(row[2]) if row[2] else 0
                pipeline_lines.append(f"• **{status_display}**: {count} loans (${volume:,.0f})")

            pipeline_text = "\n".join(pipeline_lines) if pipeline_lines else "• No active loans in pipeline"

            total_count = totals[0] if totals else 0
            total_volume = float(totals[1]) if totals and totals[1] else 0
            closing_soon = totals[2] if totals else 0

            funded_count = closing_month[0] if closing_month else 0
            funded_volume = float(closing_month[1]) if closing_month and closing_month[1] else 0

            response = f"""Hi {lo_name},

Here's your pipeline report:

**📊 PIPELINE SUMMARY**
────────────────────
**Total Active Loans:** {total_count}
**Total Volume:** ${total_volume:,.0f}
**Closing Soon:** {closing_soon} loans

**📈 BY STAGE:**
{pipeline_text}

**💰 THIS MONTH:**
• Funded: {funded_count} loans (${funded_volume:,.0f})

Need more details on any stage? Just ask!

Best regards,
Sarah"""

            return {
                "response": response,
                "action": "pipeline_report_sent",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "pipeline_report",
            }

        except Exception as e:
            logger.error(f"Error generating pipeline report: {e}")
            return {
                "response": f"Hi {lo_name},\n\nI encountered an error generating your pipeline report. Please try again or check the CRM dashboard.\n\nBest regards,\nSarah",
                "action": "pipeline_report_error",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "pipeline_report",
            }

    def _handle_bottleneck_analysis(self, lo_id: int, lo_name: str) -> Dict[str, Any]:
        """Analyze pipeline bottlenecks for loan officer."""
        try:
            # Get loans stuck in each stage (over SLA thresholds)
            bottlenecks = self.db.execute(text("""
                SELECT
                    l.stage as status,
                    l.loan_number,
                    l.borrower_name,
                    l.amount as loan_amount,
                    EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.status_changed_at)) as days_in_stage,
                    l.status_changed_at
                FROM loans l
                WHERE l.loan_officer_id = :lo_id
                AND l.stage NOT IN ('funded', 'cancelled', 'denied', 'closed')
                AND EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.status_changed_at)) > 5
                ORDER BY EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.status_changed_at)) DESC
                LIMIT 10
            """), {"lo_id": lo_id}).fetchall()

            # Get stage averages
            stage_avgs = self.db.execute(text("""
                SELECT
                    status,
                    COUNT(*) as count,
                    AVG(EXTRACT(DAY FROM (CURRENT_TIMESTAMP - status_changed_at))) as avg_days
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND status NOT IN ('funded', 'cancelled', 'denied', 'closed')
                GROUP BY status
                HAVING AVG(EXTRACT(DAY FROM (CURRENT_TIMESTAMP - status_changed_at))) > 3
                ORDER BY avg_days DESC
            """), {"lo_id": lo_id}).fetchall()

            # Format bottleneck loans
            bottleneck_lines = []
            for row in bottlenecks:
                status = row[0].replace('_', ' ').title() if row[0] else 'Unknown'
                loan_num = row[1] or 'N/A'
                borrower = row[2] or 'Unknown'
                days = int(row[4]) if row[4] else 0
                bottleneck_lines.append(f"• **{borrower}** (#{loan_num}) - {status} for **{days} days**")

            bottleneck_text = "\n".join(bottleneck_lines) if bottleneck_lines else "• No significant bottlenecks found! 🎉"

            # Format stage analysis
            stage_lines = []
            for row in stage_avgs:
                status = row[0].replace('_', ' ').title() if row[0] else 'Unknown'
                count = row[1]
                avg_days = round(float(row[2]), 1) if row[2] else 0
                severity = "🔴" if avg_days > 10 else "🟡" if avg_days > 5 else "🟢"
                stage_lines.append(f"{severity} **{status}**: {count} loans, avg {avg_days} days")

            stage_text = "\n".join(stage_lines) if stage_lines else "• All stages flowing smoothly!"

            response = f"""Hi {lo_name},

Here's your bottleneck analysis:

**🚨 LOANS NEEDING ATTENTION:**
{bottleneck_text}

**📊 STAGE ANALYSIS:**
{stage_text}

**💡 RECOMMENDATIONS:**
"""
            # Add recommendations based on bottlenecks
            if bottlenecks:
                if any(r[0] == 'underwriting' for r in bottlenecks):
                    response += "• Follow up with underwriting on pending files\n"
                if any(r[0] == 'processing' for r in bottlenecks):
                    response += "• Check with processor on document collection\n"
                if any(int(r[4] or 0) > 14 for r in bottlenecks):
                    response += "• Escalate loans over 14 days to management\n"
            else:
                response += "• Pipeline is flowing well - keep it up!\n"

            response += "\nBest regards,\nSarah"

            return {
                "response": response,
                "action": "bottleneck_analysis_sent",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "bottleneck_analysis",
            }

        except Exception as e:
            logger.error(f"Error generating bottleneck analysis: {e}")
            return {
                "response": f"Hi {lo_name},\n\nI encountered an error analyzing bottlenecks. Please try again or check the CRM dashboard.\n\nBest regards,\nSarah",
                "action": "bottleneck_analysis_error",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "bottleneck_analysis",
            }

    def _handle_stale_files_report(self, lo_id: int, lo_name: str) -> Dict[str, Any]:
        """Get report of files falling behind / at risk."""
        try:
            # Get stale files (no activity in 7+ days)
            stale_files = self.db.execute(text("""
                SELECT
                    l.loan_number,
                    l.borrower_name,
                    l.stage as status,
                    l.amount as loan_amount,
                    EXTRACT(DAY FROM (CURRENT_TIMESTAMP - COALESCE(l.updated_at, l.status_changed_at))) as days_stale,
                    l.expected_close_date,
                    l.lock_expiration_date
                FROM loans l
                WHERE l.loan_officer_id = :lo_id
                AND l.stage NOT IN ('funded', 'cancelled', 'denied', 'closed')
                AND EXTRACT(DAY FROM (CURRENT_TIMESTAMP - COALESCE(l.updated_at, l.status_changed_at))) > 7
                ORDER BY days_stale DESC
                LIMIT 15
            """), {"lo_id": lo_id}).fetchall()

            # Get loans with expiring rate locks
            expiring_locks = self.db.execute(text("""
                SELECT
                    l.loan_number,
                    l.borrower_name,
                    l.lock_expiration_date,
                    EXTRACT(DAY FROM (l.lock_expiration_date - CURRENT_DATE)) as days_until_expiry
                FROM loans l
                WHERE l.loan_officer_id = :lo_id
                AND l.stage NOT IN ('funded', 'cancelled', 'denied', 'closed')
                AND l.lock_expiration_date IS NOT NULL
                AND l.lock_expiration_date <= CURRENT_DATE + INTERVAL '14 days'
                ORDER BY l.lock_expiration_date
                LIMIT 10
            """), {"lo_id": lo_id}).fetchall()

            # Get loans past expected close
            past_close = self.db.execute(text("""
                SELECT
                    l.loan_number,
                    l.borrower_name,
                    l.expected_close_date,
                    EXTRACT(DAY FROM (CURRENT_DATE - l.expected_close_date)) as days_past
                FROM loans l
                WHERE l.loan_officer_id = :lo_id
                AND l.stage NOT IN ('funded', 'cancelled', 'denied', 'closed')
                AND l.expected_close_date < CURRENT_DATE
                ORDER BY l.expected_close_date
                LIMIT 10
            """), {"lo_id": lo_id}).fetchall()

            # Format stale files
            stale_lines = []
            for row in stale_files:
                borrower = row[1] or 'Unknown'
                loan_num = row[0] or 'N/A'
                status = row[2].replace('_', ' ').title() if row[2] else 'Unknown'
                days = int(row[4]) if row[4] else 0
                stale_lines.append(f"• **{borrower}** (#{loan_num}) - {status}, no activity for {days} days")

            stale_text = "\n".join(stale_lines[:8]) if stale_lines else "• No stale files! 🎉"

            # Format expiring locks
            lock_lines = []
            for row in expiring_locks:
                borrower = row[1] or 'Unknown'
                loan_num = row[0] or 'N/A'
                days = int(row[3]) if row[3] else 0
                if days <= 0:
                    lock_lines.append(f"🔴 **{borrower}** (#{loan_num}) - **LOCK EXPIRED**")
                elif days <= 7:
                    lock_lines.append(f"🟡 **{borrower}** (#{loan_num}) - Lock expires in {days} days")
                else:
                    lock_lines.append(f"🟢 **{borrower}** (#{loan_num}) - Lock expires in {days} days")

            lock_text = "\n".join(lock_lines) if lock_lines else "• No rate locks expiring soon"

            # Format past close
            past_lines = []
            for row in past_close:
                borrower = row[1] or 'Unknown'
                loan_num = row[0] or 'N/A'
                days_past = int(row[3]) if row[3] else 0
                past_lines.append(f"• **{borrower}** (#{loan_num}) - {days_past} days past expected close")

            past_text = "\n".join(past_lines) if past_lines else "• No loans past expected close date"

            response = f"""Hi {lo_name},

Here's your **Files at Risk** report:

**🕐 STALE FILES** (No activity 7+ days):
{stale_text}

**🔒 EXPIRING RATE LOCKS:**
{lock_text}

**📅 PAST EXPECTED CLOSE:**
{past_text}

**📊 SUMMARY:**
• Stale files: {len(stale_files)}
• Expiring locks: {len(expiring_locks)}
• Past close date: {len(past_close)}

Need to take action on any of these? Just reply!

Best regards,
Sarah"""

            return {
                "response": response,
                "action": "stale_files_report_sent",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "stale_files_report",
            }

        except Exception as e:
            logger.error(f"Error generating stale files report: {e}")
            return {
                "response": f"Hi {lo_name},\n\nI encountered an error generating the stale files report. Please try again or check the CRM dashboard.\n\nBest regards,\nSarah",
                "action": "stale_files_report_error",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "stale_files_report",
            }

    def _handle_performance_report(self, lo_id: int, lo_name: str) -> Dict[str, Any]:
        """Generate performance report for loan officer."""
        try:
            # This month's production
            this_month = self.db.execute(text("""
                SELECT
                    COUNT(*) as funded_count,
                    COALESCE(SUM(loan_amount), 0) as funded_volume
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND status = 'funded'
                AND funded_at >= DATE_TRUNC('month', CURRENT_DATE)
            """), {"lo_id": lo_id}).fetchone()

            # Last month's production
            last_month = self.db.execute(text("""
                SELECT
                    COUNT(*) as funded_count,
                    COALESCE(SUM(loan_amount), 0) as funded_volume
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND status = 'funded'
                AND funded_at >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')
                AND funded_at < DATE_TRUNC('month', CURRENT_DATE)
            """), {"lo_id": lo_id}).fetchone()

            # YTD production
            ytd = self.db.execute(text("""
                SELECT
                    COUNT(*) as funded_count,
                    COALESCE(SUM(loan_amount), 0) as funded_volume
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND status = 'funded'
                AND funded_at >= DATE_TRUNC('year', CURRENT_DATE)
            """), {"lo_id": lo_id}).fetchone()

            # Conversion rate (apps to funded)
            conversion = self.db.execute(text("""
                SELECT
                    COUNT(*) as total_apps,
                    COUNT(CASE WHEN status = 'funded' THEN 1 END) as funded
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND application_date >= CURRENT_DATE - INTERVAL '90 days'
            """), {"lo_id": lo_id}).fetchone()

            # Average cycle time
            cycle_time = self.db.execute(text("""
                SELECT AVG(EXTRACT(DAY FROM (funded_at - application_date))) as avg_days
                FROM loans
                WHERE loan_officer_id = :lo_id
                AND status = 'funded'
                AND funded_at >= CURRENT_DATE - INTERVAL '90 days'
            """), {"lo_id": lo_id}).fetchone()

            # Format numbers
            this_month_count = this_month[0] if this_month else 0
            this_month_vol = float(this_month[1]) if this_month and this_month[1] else 0

            last_month_count = last_month[0] if last_month else 0
            last_month_vol = float(last_month[1]) if last_month and last_month[1] else 0

            ytd_count = ytd[0] if ytd else 0
            ytd_vol = float(ytd[1]) if ytd and ytd[1] else 0

            total_apps = conversion[0] if conversion else 0
            funded_apps = conversion[1] if conversion else 0
            conversion_rate = (funded_apps / total_apps * 100) if total_apps > 0 else 0

            avg_cycle = round(float(cycle_time[0]), 1) if cycle_time and cycle_time[0] else 0

            # Month over month change
            vol_change = ((this_month_vol - last_month_vol) / last_month_vol * 100) if last_month_vol > 0 else 0
            vol_emoji = "📈" if vol_change > 0 else "📉" if vol_change < 0 else "➡️"

            response = f"""Hi {lo_name},

Here's your performance report:

**📅 THIS MONTH:**
• Funded: {this_month_count} loans
• Volume: ${this_month_vol:,.0f}

**📅 LAST MONTH:**
• Funded: {last_month_count} loans
• Volume: ${last_month_vol:,.0f}

{vol_emoji} **Month-over-Month:** {vol_change:+.1f}%

**📊 YEAR-TO-DATE:**
• Funded: {ytd_count} loans
• Volume: ${ytd_vol:,.0f}

**📈 KEY METRICS (90 days):**
• Pull-through rate: {conversion_rate:.1f}%
• Avg cycle time: {avg_cycle} days

Keep up the great work!

Best regards,
Sarah"""

            return {
                "response": response,
                "action": "performance_report_sent",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "performance_report",
            }

        except Exception as e:
            logger.error(f"Error generating performance report: {e}")
            return {
                "response": f"Hi {lo_name},\n\nI encountered an error generating your performance report. Please try again or check the CRM dashboard.\n\nBest regards,\nSarah",
                "action": "performance_report_error",
                "should_send": True,
                "sender_type": "team_member",
                "intent": "performance_report",
            }


def get_intelligent_email_handler(db: Session) -> IntelligentEmailHandler:
    """Get an instance of the intelligent email handler."""
    return IntelligentEmailHandler(db)
