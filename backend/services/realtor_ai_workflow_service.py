"""
Realtor Portal AI Workflow Service - Deterministic AI operations for portal.

Provides:
- Intent classification for realtor requests
- SMS command parsing and execution
- AI assistant for realtor queries (bounded by permissions)
- Deterministic workflows with human-in-the-loop for sensitive actions
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from enum import Enum
import logging
import json
import re

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class RealtorIntent(str, Enum):
    """Classified intents for realtor requests."""

    # Status queries
    CHECK_STATUS = "check_status"
    GET_TIMELINE = "get_timeline"
    GET_MILESTONES = "get_milestones"

    # Document operations
    VIEW_DOCUMENTS = "view_documents"
    DOWNLOAD_DOCUMENT = "download_document"
    UPLOAD_DOCUMENT = "upload_document"

    # Letter operations
    GENERATE_PREQUAL = "generate_prequal"
    GENERATE_PREAPPROVAL = "generate_preapproval"
    VIEW_LETTERS = "view_letters"
    SHARE_LETTER = "share_letter"

    # Communication
    SEND_MESSAGE = "send_message"
    REQUEST_UPDATE = "request_update"
    SCHEDULE_MEETING = "schedule_meeting"

    # Conditions
    VIEW_CONDITIONS = "view_conditions"
    ASK_ABOUT_CONDITION = "ask_about_condition"

    # General
    ASK_QUESTION = "ask_question"
    HELP = "help"
    UNKNOWN = "unknown"


class SMSCommand:
    """Represents a parsed SMS command."""

    # Common SMS command patterns
    COMMAND_PATTERNS = {
        r"^status\s*(\d+)?": RealtorIntent.CHECK_STATUS,
        r"^update\s*(\d+)?": RealtorIntent.REQUEST_UPDATE,
        r"^timeline\s*(\d+)?": RealtorIntent.GET_TIMELINE,
        r"^docs?\s*(\d+)?": RealtorIntent.VIEW_DOCUMENTS,
        r"^letter\s*(\d+)?": RealtorIntent.VIEW_LETTERS,
        r"^prequal\s*(\d+)?": RealtorIntent.GENERATE_PREQUAL,
        r"^preapproval\s*(\d+)?": RealtorIntent.GENERATE_PREAPPROVAL,
        r"^conditions?\s*(\d+)?": RealtorIntent.VIEW_CONDITIONS,
        r"^help": RealtorIntent.HELP,
        r"^schedule\s*(\d+)?": RealtorIntent.SCHEDULE_MEETING,
    }

    def __init__(
        self,
        raw_message: str,
        intent: RealtorIntent,
        loan_id: Optional[int] = None,
        args: Optional[Dict] = None
    ):
        self.raw_message = raw_message
        self.intent = intent
        self.loan_id = loan_id
        self.args = args or {}

    @classmethod
    def parse(cls, message: str) -> "SMSCommand":
        """Parse an SMS message into a command."""
        message = message.strip().lower()

        for pattern, intent in cls.COMMAND_PATTERNS.items():
            match = re.match(pattern, message, re.IGNORECASE)
            if match:
                loan_id = None
                if match.groups():
                    try:
                        loan_id = int(match.group(1)) if match.group(1) else None
                    except (ValueError, IndexError):
                        pass

                return cls(
                    raw_message=message,
                    intent=intent,
                    loan_id=loan_id
                )

        return cls(
            raw_message=message,
            intent=RealtorIntent.UNKNOWN
        )


class PortalAIWorkflowService:
    """
    AI workflow service for deterministic portal operations.

    All operations are bounded by the realtor's permissions and
    require explicit approval for sensitive actions.
    """

    def __init__(self, db: Session, anthropic_client=None):
        self.db = db
        self.anthropic = anthropic_client
        self._load_system_prompts()

    def _load_system_prompts(self):
        """Load system prompts for AI operations."""
        self.INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier for a mortgage loan portal used by real estate agents.

Given a realtor's message, classify their intent into one of these categories:
- check_status: Asking about loan status or progress
- get_timeline: Asking about expected dates or timeline
- get_milestones: Asking about specific milestones
- view_documents: Wanting to see documents
- download_document: Wanting to download a specific document
- upload_document: Wanting to upload a document
- generate_prequal: Requesting a pre-qualification letter
- generate_preapproval: Requesting a pre-approval letter
- view_letters: Viewing existing letters
- share_letter: Sharing a letter with someone
- send_message: Sending a message to the loan officer
- request_update: Requesting a status update
- schedule_meeting: Wanting to schedule a meeting
- view_conditions: Asking about loan conditions
- ask_about_condition: Questions about a specific condition
- ask_question: General questions about the loan process
- help: Asking for help with the portal
- unknown: Cannot determine intent

Respond with ONLY the intent category and confidence (0-1), in JSON format:
{"intent": "category", "confidence": 0.95, "entities": {"loan_id": null, "document_type": null}}"""

        self.ASSISTANT_SYSTEM_PROMPT = """You are a helpful assistant for real estate agents using a mortgage loan portal.

You can help with:
{allowed_topics}

You CANNOT discuss or provide information about:
- Specific interest rates or pricing
- Underwriting decisions or reasons
- Borrower's personal financial details (income, credit score, assets)
- Internal company processes

Current loan context:
- Status: {loan_status}
- Borrower: {borrower_name} (property at {property_address})
- Loan Amount: {loan_amount}
- Available actions: {available_actions}

Be concise and helpful. If asked about something you cannot discuss, politely explain
that information is not available in the portal."""

    # =========================================================================
    # INTENT CLASSIFICATION
    # =========================================================================

    async def classify_intent(
        self,
        message: str,
        context: Optional[Dict] = None
    ) -> Tuple[RealtorIntent, float, Dict]:
        """
        Classify the intent of a realtor message.

        Returns:
            Tuple of (intent, confidence, entities)
        """
        # First try rule-based classification
        rule_result = self._classify_by_rules(message)
        if rule_result[1] > 0.9:  # High confidence from rules
            return rule_result

        # Fall back to AI classification if available
        if self.anthropic:
            return await self._classify_by_ai(message, context)

        return rule_result

    def _classify_by_rules(self, message: str) -> Tuple[RealtorIntent, float, Dict]:
        """Rule-based intent classification."""
        message_lower = message.lower()
        entities = {}

        # Status patterns
        if any(word in message_lower for word in ["status", "where", "stage", "progress"]):
            return (RealtorIntent.CHECK_STATUS, 0.95, entities)

        # Timeline patterns
        if any(word in message_lower for word in ["when", "timeline", "expected", "closing date"]):
            return (RealtorIntent.GET_TIMELINE, 0.9, entities)

        # Document patterns
        if any(word in message_lower for word in ["document", "doc", "file", "upload"]):
            if "upload" in message_lower:
                return (RealtorIntent.UPLOAD_DOCUMENT, 0.9, entities)
            elif "download" in message_lower:
                return (RealtorIntent.DOWNLOAD_DOCUMENT, 0.9, entities)
            return (RealtorIntent.VIEW_DOCUMENTS, 0.85, entities)

        # Letter patterns
        if "prequal" in message_lower or "pre-qual" in message_lower:
            if any(word in message_lower for word in ["generate", "create", "need", "get"]):
                return (RealtorIntent.GENERATE_PREQUAL, 0.95, entities)
            return (RealtorIntent.VIEW_LETTERS, 0.8, entities)

        if "preapproval" in message_lower or "pre-approval" in message_lower:
            if any(word in message_lower for word in ["generate", "create", "need", "get"]):
                return (RealtorIntent.GENERATE_PREAPPROVAL, 0.95, entities)
            return (RealtorIntent.VIEW_LETTERS, 0.8, entities)

        # Condition patterns
        if any(word in message_lower for word in ["condition", "conditions", "outstanding"]):
            return (RealtorIntent.VIEW_CONDITIONS, 0.9, entities)

        # Message patterns
        if any(word in message_lower for word in ["message", "tell", "contact", "reach"]):
            return (RealtorIntent.SEND_MESSAGE, 0.85, entities)

        # Update request patterns
        if any(word in message_lower for word in ["update", "news", "anything new"]):
            return (RealtorIntent.REQUEST_UPDATE, 0.85, entities)

        # Meeting patterns
        if any(word in message_lower for word in ["meeting", "schedule", "call", "appointment"]):
            return (RealtorIntent.SCHEDULE_MEETING, 0.9, entities)

        # Help patterns
        if any(word in message_lower for word in ["help", "how do i", "how to", "what can"]):
            return (RealtorIntent.HELP, 0.95, entities)

        # Default to question
        if "?" in message:
            return (RealtorIntent.ASK_QUESTION, 0.6, entities)

        return (RealtorIntent.UNKNOWN, 0.3, entities)

    async def _classify_by_ai(
        self,
        message: str,
        context: Optional[Dict]
    ) -> Tuple[RealtorIntent, float, Dict]:
        """AI-based intent classification using Claude."""
        try:
            response = await self.anthropic.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=200,
                system=self.INTENT_CLASSIFICATION_PROMPT,
                messages=[{"role": "user", "content": message}]
            )

            result = json.loads(response.content[0].text)
            intent = RealtorIntent(result.get("intent", "unknown"))
            confidence = result.get("confidence", 0.5)
            entities = result.get("entities", {})

            return (intent, confidence, entities)

        except Exception as e:
            logger.error(f"AI classification error: {e}")
            return self._classify_by_rules(message)

    # =========================================================================
    # SMS COMMAND PROCESSING
    # =========================================================================

    async def process_sms_command(
        self,
        phone_number: str,
        message: str,
        realtor_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process an SMS command from a realtor.

        Returns response to send back via SMS.
        """
        # Parse the command
        command = SMSCommand.parse(message)

        # Record the command
        command_id = self._record_sms_command(phone_number, message, command, realtor_id)

        # Find realtor if not provided
        if not realtor_id:
            realtor_id = self._lookup_realtor_by_phone(phone_number)

        if not realtor_id:
            return {
                "success": False,
                "response": "Phone number not recognized. Please register in the portal first.",
                "command_id": command_id
            }

        # Determine loan context
        loan_id = command.loan_id
        if not loan_id:
            # Get most recent active loan
            loan_id = self._get_default_loan(realtor_id)

        if not loan_id and command.intent not in [RealtorIntent.HELP, RealtorIntent.UNKNOWN]:
            return {
                "success": False,
                "response": "No active loans found. Reply with loan ID, e.g., 'status 12345'",
                "command_id": command_id
            }

        # Execute based on intent
        response = await self._execute_sms_intent(
            command.intent,
            realtor_id,
            loan_id,
            command.args
        )

        # Update command record
        self._update_sms_command(command_id, response)

        return {
            "success": True,
            "response": response,
            "command_id": command_id,
            "intent": command.intent.value
        }

    async def _execute_sms_intent(
        self,
        intent: RealtorIntent,
        realtor_id: int,
        loan_id: Optional[int],
        args: Dict
    ) -> str:
        """Execute an SMS intent and return response text."""
        if intent == RealtorIntent.HELP:
            return self._get_help_text()

        if intent == RealtorIntent.CHECK_STATUS:
            return await self._get_status_sms(realtor_id, loan_id)

        if intent == RealtorIntent.GET_TIMELINE:
            return await self._get_timeline_sms(realtor_id, loan_id)

        if intent == RealtorIntent.VIEW_CONDITIONS:
            return await self._get_conditions_sms(realtor_id, loan_id)

        if intent == RealtorIntent.REQUEST_UPDATE:
            return await self._request_update_sms(realtor_id, loan_id)

        if intent == RealtorIntent.VIEW_LETTERS:
            return await self._get_letters_sms(realtor_id, loan_id)

        if intent == RealtorIntent.GENERATE_PREQUAL:
            return "Pre-qual letter generation requires portal access. Visit: portal.example.com/loans/{}/letters".format(loan_id)

        return "I didn't understand that. Reply HELP for available commands."

    def _get_help_text(self) -> str:
        """Get SMS help text."""
        return """Available commands:
STATUS [loan_id] - Check loan status
TIMELINE [loan_id] - Get timeline
CONDITIONS [loan_id] - View conditions
UPDATE [loan_id] - Request update
DOCS [loan_id] - Document status
LETTER [loan_id] - View letters
SCHEDULE [loan_id] - Schedule meeting"""

    async def _get_status_sms(self, realtor_id: int, loan_id: int) -> str:
        """Get loan status for SMS."""
        loan = self.db.execute(text("""
            SELECT
                l.status, l.loan_amount,
                CONCAT(c.first_name, ' ', c.last_name) as borrower_name,
                l.expected_close_date
            FROM loans l
            JOIN realtor_loan_associations rla ON rla.loan_id = l.id
            LEFT JOIN contacts c ON c.id = l.borrower_id
            WHERE l.id = :loan_id AND rla.realtor_id = :realtor_id
                AND rla.access_revoked_at IS NULL
        """), {"loan_id": loan_id, "realtor_id": realtor_id}).fetchone()

        if not loan:
            return f"Loan {loan_id} not found or access denied."

        status_display = loan[0].replace("_", " ").title()
        return f"Loan {loan_id}: {status_display}\nBorrower: {loan[2]}\nClose Date: {loan[3] or 'TBD'}"

    async def _get_timeline_sms(self, realtor_id: int, loan_id: int) -> str:
        """Get timeline for SMS."""
        milestones = self.db.execute(text("""
            SELECT milestone_name, is_completed, target_date
            FROM portal_milestones
            WHERE loan_id = :loan_id
            ORDER BY display_order
            LIMIT 5
        """), {"loan_id": loan_id}).fetchall()

        if not milestones:
            return f"No timeline available for loan {loan_id}."

        lines = [f"Timeline for {loan_id}:"]
        for m in milestones:
            status = "[DONE]" if m[1] else "[PENDING]"
            date = m[2].strftime("%m/%d") if m[2] else ""
            lines.append(f"{status} {m[0]} {date}")

        return "\n".join(lines)

    async def _get_conditions_sms(self, realtor_id: int, loan_id: int) -> str:
        """Get conditions for SMS."""
        # Check permission first
        from services.realtor_permission_service import RealtorPermissionService
        perm_service = RealtorPermissionService(self.db)

        if not perm_service.check_permission(realtor_id, loan_id, "view_conditions"):
            return "Conditions not available for this loan stage."

        conditions = self.db.execute(text("""
            SELECT condition_name, status
            FROM loan_conditions
            WHERE loan_id = :loan_id AND status = 'open'
            LIMIT 5
        """), {"loan_id": loan_id}).fetchall()

        if not conditions:
            return f"No open conditions for loan {loan_id}."

        lines = [f"Open conditions ({len(conditions)}):"]
        for c in conditions:
            lines.append(f"- {c[0]}")

        return "\n".join(lines)

    async def _request_update_sms(self, realtor_id: int, loan_id: int) -> str:
        """Request an update via SMS."""
        # Record the request
        self.db.execute(text("""
            INSERT INTO portal_communication_events (
                organization_id, realtor_id, loan_id,
                event_type, channel, direction, content
            )
            SELECT
                l.organization_id, :realtor_id, :loan_id,
                'message', 'sms', 'inbound', 'Update request via SMS'
            FROM loans l WHERE l.id = :loan_id
        """), {"realtor_id": realtor_id, "loan_id": loan_id})
        self.db.commit()

        return f"Update request sent for loan {loan_id}. The loan officer will be notified."

    async def _get_letters_sms(self, realtor_id: int, loan_id: int) -> str:
        """Get letters summary for SMS."""
        letters = self.db.execute(text("""
            SELECT letter_type, version, expires_at, is_void
            FROM pre_approval_letters
            WHERE loan_id = :loan_id AND is_void = FALSE
            ORDER BY issued_at DESC
            LIMIT 3
        """), {"loan_id": loan_id}).fetchall()

        if not letters:
            return f"No letters generated for loan {loan_id}."

        lines = [f"Letters for {loan_id}:"]
        for letter in letters:
            expires = letter[2].strftime("%m/%d/%Y") if letter[2] else "N/A"
            lines.append(f"- {letter[0].title()} v{letter[1]} (exp: {expires})")

        lines.append("View/download at portal.example.com")
        return "\n".join(lines)

    def _record_sms_command(
        self,
        phone_number: str,
        message: str,
        command: SMSCommand,
        realtor_id: Optional[int]
    ) -> int:
        """Record an SMS command in history."""
        result = self.db.execute(text("""
            INSERT INTO portal_sms_command_history (
                phone_number, realtor_id, raw_message,
                parsed_command, parsed_args, loan_id, status
            ) VALUES (
                :phone, :realtor_id, :message,
                :command, :args, :loan_id, 'processing'
            )
            RETURNING id
        """), {
            "phone": phone_number,
            "realtor_id": realtor_id,
            "message": message,
            "command": command.intent.value,
            "args": json.dumps(command.args),
            "loan_id": command.loan_id
        })
        self.db.commit()
        return result.fetchone()[0]

    def _update_sms_command(self, command_id: int, response: str):
        """Update SMS command with response."""
        self.db.execute(text("""
            UPDATE portal_sms_command_history
            SET status = 'completed',
                response_sent = :response,
                processed_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"id": command_id, "response": response})
        self.db.commit()

    def _lookup_realtor_by_phone(self, phone_number: str) -> Optional[int]:
        """Look up realtor ID by phone number."""
        # Normalize phone number
        normalized = re.sub(r'[^0-9]', '', phone_number)
        if len(normalized) == 11 and normalized.startswith('1'):
            normalized = normalized[1:]

        result = self.db.execute(text("""
            SELECT id FROM realtor_portal_users
            WHERE REGEXP_REPLACE(phone, '[^0-9]', '', 'g') = :phone
                AND is_active = TRUE
        """), {"phone": normalized}).fetchone()

        return result[0] if result else None

    def _get_default_loan(self, realtor_id: int) -> Optional[int]:
        """Get the most recently active loan for a realtor."""
        result = self.db.execute(text("""
            SELECT loan_id FROM realtor_loan_associations
            WHERE realtor_id = :realtor_id
                AND access_revoked_at IS NULL
            ORDER BY last_viewed_at DESC NULLS LAST, created_at DESC
            LIMIT 1
        """), {"realtor_id": realtor_id}).fetchone()

        return result[0] if result else None

    # =========================================================================
    # AI ASSISTANT
    # =========================================================================

    async def answer_question(
        self,
        realtor_id: int,
        loan_id: int,
        question: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Answer a realtor's question using AI assistant.

        Bounded by permissions and allowed topics.
        """
        from services.realtor_permission_service import RealtorPermissionService

        # Get permissions
        perm_service = RealtorPermissionService(self.db)
        permissions = perm_service.get_permissions(realtor_id, loan_id)

        if not permissions.ai_assistant_enabled:
            return {
                "success": False,
                "error": "AI assistant not available for this loan"
            }

        # Build context
        loan_context = await self._get_loan_context(loan_id, realtor_id)

        # Build allowed topics description
        topic_descriptions = {
            "status": "current loan status and stage",
            "timeline": "expected dates and milestones",
            "documents": "document requirements and status",
            "conditions": "loan conditions and requirements",
            "general": "general mortgage process questions"
        }

        allowed_topics = ", ".join([
            topic_descriptions.get(t, t)
            for t in permissions.ai_allowed_topics
        ])

        # Get available actions
        available_actions = perm_service.get_available_actions(realtor_id, loan_id)

        # Build system prompt
        system_prompt = self.ASSISTANT_SYSTEM_PROMPT.format(
            allowed_topics=allowed_topics,
            loan_status=loan_context.get("status", "Unknown"),
            borrower_name=loan_context.get("borrower_name", "Unknown"),
            property_address=loan_context.get("property_address", "TBD"),
            loan_amount=loan_context.get("loan_amount_formatted", "N/A"),
            available_actions=", ".join(available_actions)
        )

        if not self.anthropic:
            return {
                "success": False,
                "error": "AI service not configured"
            }

        try:
            # Build messages
            messages = []
            if conversation_history:
                messages.extend(conversation_history[-5:])  # Last 5 messages
            messages.append({"role": "user", "content": question})

            response = await self.anthropic.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=500,
                system=system_prompt,
                messages=messages
            )

            answer = response.content[0].text

            # Log the interaction
            self._log_ai_interaction(
                realtor_id, loan_id, question, answer,
                response.usage.input_tokens,
                response.usage.output_tokens
            )

            return {
                "success": True,
                "answer": answer,
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens
            }

        except Exception as e:
            logger.error(f"AI assistant error: {e}")
            return {
                "success": False,
                "error": "Failed to get response. Please try again."
            }

    async def _get_loan_context(self, loan_id: int, realtor_id: int) -> Dict:
        """Get loan context for AI assistant."""
        loan = self.db.execute(text("""
            SELECT
                l.status, l.loan_amount, l.loan_type,
                l.expected_close_date, l.property_address,
                CONCAT(c.first_name, ' ', c.last_name) as borrower_name,
                COALESCE(es.full_name, u.email) as lo_name
            FROM loans l
            JOIN realtor_loan_associations rla ON rla.loan_id = l.id
            LEFT JOIN contacts c ON c.id = l.borrower_id
            LEFT JOIN users u ON u.id = l.loan_officer_id
            LEFT JOIN email_signatures es ON es.user_id = u.id
            WHERE l.id = :loan_id AND rla.realtor_id = :realtor_id
        """), {"loan_id": loan_id, "realtor_id": realtor_id}).fetchone()

        if not loan:
            return {}

        return {
            "status": loan[0],
            "loan_amount": float(loan[1]) if loan[1] else None,
            "loan_amount_formatted": f"${loan[1]:,.0f}" if loan[1] else "N/A",
            "loan_type": loan[2],
            "expected_close_date": loan[3].strftime("%m/%d/%Y") if loan[3] else "TBD",
            "property_address": loan[4] or "TBD",
            "borrower_name": loan[5] or "Unknown",
            "lo_name": loan[6] or "Unknown"
        }

    def _log_ai_interaction(
        self,
        realtor_id: int,
        loan_id: int,
        question: str,
        answer: str,
        input_tokens: int,
        output_tokens: int
    ):
        """Log AI interaction for analytics and compliance."""
        try:
            self.db.execute(text("""
                INSERT INTO portal_communication_events (
                    organization_id, realtor_id, loan_id,
                    event_type, channel, direction, content,
                    ai_generated, ai_model, ai_prompt_tokens, ai_completion_tokens,
                    metadata
                )
                SELECT
                    l.organization_id, :realtor_id, :loan_id,
                    'message', 'portal', 'outbound', :answer,
                    TRUE, 'claude-3-haiku', :input_tokens, :output_tokens,
                    :metadata
                FROM loans l WHERE l.id = :loan_id
            """), {
                "realtor_id": realtor_id,
                "loan_id": loan_id,
                "answer": answer,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "metadata": json.dumps({"question": question[:500]})
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error logging AI interaction: {e}")
            self.db.rollback()
