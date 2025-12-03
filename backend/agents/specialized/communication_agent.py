"""
Communication Agent

Specialized agent for email, SMS, and notification management with 8 tools:
1. send_email - Send email to contact
2. send_sms - Send SMS message
3. get_communication_history - Get communication history for entity
4. schedule_communication - Schedule future communication
5. get_templates - Get available message templates
6. create_template - Create a new message template
7. get_unread_messages - Get unread messages/responses
8. log_communication - Log a communication that occurred externally
"""

from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from sqlalchemy import text

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class SendEmailInput(BaseModel):
    """Input schema for send_email tool"""
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Email body content (supports HTML)")
    entity_type: Optional[str] = Field(None, description="Related entity type: lead, loan, contact")
    entity_id: Optional[int] = Field(None, description="Related entity ID")
    template_id: Optional[int] = Field(None, description="Template ID to use")
    cc: Optional[List[str]] = Field(None, description="CC email addresses")
    attachments: Optional[List[str]] = Field(None, description="Attachment file paths")


class SendSmsInput(BaseModel):
    """Input schema for send_sms tool"""
    to_phone: str = Field(..., description="Recipient phone number")
    message: str = Field(..., description="SMS message content (max 160 chars for single SMS)")
    entity_type: Optional[str] = Field(None, description="Related entity type: lead, loan, contact")
    entity_id: Optional[int] = Field(None, description="Related entity ID")


class GetCommunicationHistoryInput(BaseModel):
    """Input schema for get_communication_history tool"""
    entity_type: str = Field(..., description="Entity type: lead, loan, contact")
    entity_id: int = Field(..., description="Entity ID")
    comm_type: Optional[str] = Field(None, description="Filter by type: email, sms, call, note")
    limit: int = Field(default=50, description="Maximum records to return")


class ScheduleCommunicationInput(BaseModel):
    """Input schema for schedule_communication tool"""
    comm_type: str = Field(..., description="Communication type: email, sms")
    scheduled_time: str = Field(..., description="Scheduled time (ISO format)")
    entity_type: str = Field(..., description="Related entity type")
    entity_id: int = Field(..., description="Related entity ID")
    subject: Optional[str] = Field(None, description="Email subject (for email type)")
    body: str = Field(..., description="Message content")
    template_id: Optional[int] = Field(None, description="Template ID to use")


class GetTemplatesInput(BaseModel):
    """Input schema for get_templates tool"""
    template_type: Optional[str] = Field(None, description="Filter by type: email, sms")
    category: Optional[str] = Field(None, description="Filter by category: follow_up, document_request, status_update, etc.")
    search: Optional[str] = Field(None, description="Search templates by name or content")


class CreateTemplateInput(BaseModel):
    """Input schema for create_template tool"""
    name: str = Field(..., description="Template name")
    template_type: str = Field(..., description="Template type: email, sms")
    category: str = Field(..., description="Category: follow_up, document_request, status_update, welcome, etc.")
    subject: Optional[str] = Field(None, description="Email subject (for email templates)")
    body: str = Field(..., description="Template body with merge fields like {{first_name}}, {{loan_amount}}")


class GetUnreadMessagesInput(BaseModel):
    """Input schema for get_unread_messages tool"""
    message_type: Optional[str] = Field(None, description="Filter by type: email, sms")
    limit: int = Field(default=50, description="Maximum messages to return")


class LogCommunicationInput(BaseModel):
    """Input schema for log_communication tool"""
    comm_type: str = Field(..., description="Communication type: call, email, sms, meeting, note")
    direction: str = Field(..., description="Direction: inbound, outbound")
    entity_type: str = Field(..., description="Related entity type: lead, loan, contact")
    entity_id: int = Field(..., description="Related entity ID")
    subject: Optional[str] = Field(None, description="Subject or call topic")
    content: str = Field(..., description="Content or notes about the communication")
    duration_minutes: Optional[int] = Field(None, description="Duration for calls/meetings")
    outcome: Optional[str] = Field(None, description="Outcome: connected, voicemail, no_answer, etc.")


# ============================================================================
# COMMUNICATION AGENT
# ============================================================================

@AgentRegistry.register
class CommunicationAgent(SpecializedAgent):
    """
    Specialized agent for communication management.

    Handles email, SMS, and other communications with leads,
    borrowers, and contacts including templates and scheduling.
    """

    @property
    def name(self) -> str:
        return "CommunicationAgent"

    @property
    def description(self) -> str:
        return "Manages all communications including email, SMS, templates, and communication history"

    def _register_tools(self):
        """Register all communication tools"""

        # Tool 1: Send Email
        self.register_tool(AgentTool(
            name="send_email",
            description="Send an email to a contact, lead, or borrower. "
                       "Supports templates, HTML content, and attachments.",
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._send_email,
            input_schema=SendEmailInput,
            requires_confirmation=True
        ))

        # Tool 2: Send SMS
        self.register_tool(AgentTool(
            name="send_sms",
            description="Send an SMS message to a phone number. "
                       "Messages over 160 characters will be split.",
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._send_sms,
            input_schema=SendSmsInput,
            requires_confirmation=True
        ))

        # Tool 3: Get Communication History
        self.register_tool(AgentTool(
            name="get_communication_history",
            description="Get the communication history for a lead, loan, or contact. "
                       "Includes emails, SMS, calls, and notes.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_communication_history,
            input_schema=GetCommunicationHistoryInput
        ))

        # Tool 4: Schedule Communication
        self.register_tool(AgentTool(
            name="schedule_communication",
            description="Schedule an email or SMS to be sent at a future time. "
                       "Useful for follow-up sequences and timed outreach.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._schedule_communication,
            input_schema=ScheduleCommunicationInput
        ))

        # Tool 5: Get Templates
        self.register_tool(AgentTool(
            name="get_templates",
            description="Get available message templates filtered by type or category. "
                       "Templates include merge fields for personalization.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_templates,
            input_schema=GetTemplatesInput
        ))

        # Tool 6: Create Template
        self.register_tool(AgentTool(
            name="create_template",
            description="Create a new email or SMS template with merge fields. "
                       "Use {{field_name}} syntax for personalization.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._create_template,
            input_schema=CreateTemplateInput
        ))

        # Tool 7: Get Unread Messages
        self.register_tool(AgentTool(
            name="get_unread_messages",
            description="Get unread email or SMS responses that need attention. "
                       "Essential for monitoring inbound communications.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_unread_messages,
            input_schema=GetUnreadMessagesInput
        ))

        # Tool 8: Log Communication
        self.register_tool(AgentTool(
            name="log_communication",
            description="Log a communication that occurred outside the system "
                       "(phone calls, in-person meetings, external emails).",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._log_communication,
            input_schema=LogCommunicationInput
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _send_email(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Send an email"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            # In production, this would integrate with email service (SendGrid, etc.)
            # For now, we log the email to the communications table

            query = text("""
                INSERT INTO communications (
                    type, direction, entity_type, entity_id,
                    to_address, subject, content, status,
                    created_by, created_at
                ) VALUES (
                    'email', 'outbound', :entity_type, :entity_id,
                    :to_email, :subject, :body, 'sent',
                    :created_by, CURRENT_TIMESTAMP
                )
                RETURNING id, subject, to_address
            """)

            result = db.execute(query, {
                "entity_type": input_data.get("entity_type"),
                "entity_id": input_data.get("entity_id"),
                "to_email": input_data["to_email"],
                "subject": input_data["subject"],
                "body": input_data["body"],
                "created_by": context.get("user_id", 1)
            }).fetchone()

            db.commit()

            return ToolResult(
                success=True,
                data={
                    "communication_id": result.id,
                    "to": result.to_address,
                    "subject": result.subject,
                    "status": "sent"
                },
                message=f"Email sent to {result.to_address}: {result.subject}"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _send_sms(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Send an SMS message"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            message = input_data["message"]
            segments = (len(message) + 159) // 160  # Calculate SMS segments

            query = text("""
                INSERT INTO communications (
                    type, direction, entity_type, entity_id,
                    to_address, content, status,
                    created_by, created_at
                ) VALUES (
                    'sms', 'outbound', :entity_type, :entity_id,
                    :to_phone, :message, 'sent',
                    :created_by, CURRENT_TIMESTAMP
                )
                RETURNING id, to_address
            """)

            result = db.execute(query, {
                "entity_type": input_data.get("entity_type"),
                "entity_id": input_data.get("entity_id"),
                "to_phone": input_data["to_phone"],
                "message": message,
                "created_by": context.get("user_id", 1)
            }).fetchone()

            db.commit()

            return ToolResult(
                success=True,
                data={
                    "communication_id": result.id,
                    "to": result.to_address,
                    "message_length": len(message),
                    "segments": segments,
                    "status": "sent"
                },
                message=f"SMS sent to {result.to_address} ({segments} segment(s))"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_communication_history(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get communication history for an entity"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            params = {
                "entity_type": input_data["entity_type"],
                "entity_id": input_data["entity_id"],
                "limit": input_data.get("limit", 50)
            }

            type_filter = ""
            if input_data.get("comm_type"):
                type_filter = "AND type = :comm_type"
                params["comm_type"] = input_data["comm_type"]

            query = text(f"""
                SELECT
                    id, type, direction, to_address, from_address,
                    subject, content, status, created_at, created_by
                FROM communications
                WHERE entity_type = :entity_type
                    AND entity_id = :entity_id
                    {type_filter}
                ORDER BY created_at DESC
                LIMIT :limit
            """)

            results = db.execute(query, params).fetchall()

            communications = []
            type_counts = {"email": 0, "sms": 0, "call": 0, "note": 0}

            for r in results:
                comm_type = r.type or "other"
                if comm_type in type_counts:
                    type_counts[comm_type] += 1

                communications.append({
                    "id": r.id,
                    "type": r.type,
                    "direction": r.direction,
                    "to": r.to_address,
                    "from": r.from_address,
                    "subject": r.subject,
                    "content": r.content[:200] + "..." if r.content and len(r.content) > 200 else r.content,
                    "status": r.status,
                    "date": r.created_at.isoformat() if r.created_at else None
                })

            return ToolResult(
                success=True,
                data={
                    "entity_type": input_data["entity_type"],
                    "entity_id": input_data["entity_id"],
                    "communications": communications,
                    "count": len(communications),
                    "type_counts": type_counts
                },
                message=f"Found {len(communications)} communications"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _schedule_communication(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Schedule a future communication"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            scheduled_time = datetime.fromisoformat(input_data["scheduled_time"])

            if scheduled_time <= datetime.now():
                return ToolResult(
                    success=False,
                    error="Scheduled time must be in the future"
                )

            query = text("""
                INSERT INTO scheduled_communications (
                    comm_type, entity_type, entity_id,
                    subject, body, template_id,
                    scheduled_time, status,
                    created_by, created_at
                ) VALUES (
                    :comm_type, :entity_type, :entity_id,
                    :subject, :body, :template_id,
                    :scheduled_time, 'pending',
                    :created_by, CURRENT_TIMESTAMP
                )
                RETURNING id, comm_type, scheduled_time
            """)

            result = db.execute(query, {
                "comm_type": input_data["comm_type"],
                "entity_type": input_data["entity_type"],
                "entity_id": input_data["entity_id"],
                "subject": input_data.get("subject"),
                "body": input_data["body"],
                "template_id": input_data.get("template_id"),
                "scheduled_time": scheduled_time,
                "created_by": context.get("user_id", 1)
            }).fetchone()

            db.commit()

            return ToolResult(
                success=True,
                data={
                    "scheduled_id": result.id,
                    "type": result.comm_type,
                    "scheduled_for": result.scheduled_time.isoformat()
                },
                message=f"{result.comm_type.upper()} scheduled for {result.scheduled_time.strftime('%m/%d/%Y %I:%M %p')}"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_templates(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get available message templates"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            conditions = ["is_active = true"]
            params = {}

            if input_data.get("template_type"):
                conditions.append("template_type = :template_type")
                params["template_type"] = input_data["template_type"]

            if input_data.get("category"):
                conditions.append("category = :category")
                params["category"] = input_data["category"]

            if input_data.get("search"):
                conditions.append("(name ILIKE :search OR body ILIKE :search)")
                params["search"] = f"%{input_data['search']}%"

            where_clause = " AND ".join(conditions)

            query = text(f"""
                SELECT
                    id, name, template_type, category,
                    subject, body, created_at, usage_count
                FROM message_templates
                WHERE {where_clause}
                ORDER BY usage_count DESC, name
            """)

            results = db.execute(query, params).fetchall()

            templates = [
                {
                    "id": r.id,
                    "name": r.name,
                    "type": r.template_type,
                    "category": r.category,
                    "subject": r.subject,
                    "body_preview": r.body[:100] + "..." if r.body and len(r.body) > 100 else r.body,
                    "usage_count": r.usage_count
                }
                for r in results
            ]

            # Group by category
            by_category = {}
            for t in templates:
                cat = t["category"] or "uncategorized"
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(t)

            return ToolResult(
                success=True,
                data={
                    "templates": templates,
                    "count": len(templates),
                    "by_category": by_category
                },
                message=f"Found {len(templates)} templates"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _create_template(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Create a new message template"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            # Extract merge fields from body
            import re
            merge_fields = list(set(re.findall(r'\{\{(\w+)\}\}', input_data["body"])))

            query = text("""
                INSERT INTO message_templates (
                    name, template_type, category,
                    subject, body, merge_fields,
                    is_active, created_by, created_at
                ) VALUES (
                    :name, :template_type, :category,
                    :subject, :body, :merge_fields,
                    true, :created_by, CURRENT_TIMESTAMP
                )
                RETURNING id, name
            """)

            result = db.execute(query, {
                "name": input_data["name"],
                "template_type": input_data["template_type"],
                "category": input_data["category"],
                "subject": input_data.get("subject"),
                "body": input_data["body"],
                "merge_fields": ",".join(merge_fields),
                "created_by": context.get("user_id", 1)
            }).fetchone()

            db.commit()

            return ToolResult(
                success=True,
                data={
                    "template_id": result.id,
                    "name": result.name,
                    "merge_fields": merge_fields
                },
                message=f"Template '{result.name}' created with {len(merge_fields)} merge fields"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_unread_messages(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get unread inbound messages"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            params = {"limit": input_data.get("limit", 50)}
            type_filter = ""

            if input_data.get("message_type"):
                type_filter = "AND type = :message_type"
                params["message_type"] = input_data["message_type"]

            query = text(f"""
                SELECT
                    c.id, c.type, c.direction, c.from_address,
                    c.subject, c.content, c.entity_type, c.entity_id,
                    c.created_at,
                    CASE
                        WHEN c.entity_type = 'lead' THEN l.name
                        WHEN c.entity_type = 'loan' THEN lo.borrower_name
                        ELSE NULL
                    END as entity_name
                FROM communications c
                LEFT JOIN leads l ON c.entity_type = 'lead' AND c.entity_id = l.id
                LEFT JOIN loans lo ON c.entity_type = 'loan' AND c.entity_id = lo.id
                WHERE c.direction = 'inbound'
                    AND c.is_read = false
                    {type_filter}
                ORDER BY c.created_at DESC
                LIMIT :limit
            """)

            results = db.execute(query, params).fetchall()

            messages = [
                {
                    "id": r.id,
                    "type": r.type,
                    "from": r.from_address,
                    "subject": r.subject,
                    "preview": r.content[:100] + "..." if r.content and len(r.content) > 100 else r.content,
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id,
                    "entity_name": r.entity_name,
                    "received_at": r.created_at.isoformat() if r.created_at else None
                }
                for r in results
            ]

            return ToolResult(
                success=True,
                data={
                    "messages": messages,
                    "count": len(messages)
                },
                message=f"Found {len(messages)} unread messages"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _log_communication(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Log an external communication"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            query = text("""
                INSERT INTO communications (
                    type, direction, entity_type, entity_id,
                    subject, content, duration_minutes, outcome,
                    status, created_by, created_at
                ) VALUES (
                    :comm_type, :direction, :entity_type, :entity_id,
                    :subject, :content, :duration, :outcome,
                    'logged', :created_by, CURRENT_TIMESTAMP
                )
                RETURNING id, type, entity_type, entity_id
            """)

            result = db.execute(query, {
                "comm_type": input_data["comm_type"],
                "direction": input_data["direction"],
                "entity_type": input_data["entity_type"],
                "entity_id": input_data["entity_id"],
                "subject": input_data.get("subject"),
                "content": input_data["content"],
                "duration": input_data.get("duration_minutes"),
                "outcome": input_data.get("outcome"),
                "created_by": context.get("user_id", 1)
            }).fetchone()

            # Update entity's last contact timestamp
            if input_data["entity_type"] == "lead":
                db.execute(
                    text("UPDATE leads SET updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                    {"id": input_data["entity_id"]}
                )
            elif input_data["entity_type"] == "loan":
                db.execute(
                    text("UPDATE loans SET updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                    {"id": input_data["entity_id"]}
                )

            db.commit()

            return ToolResult(
                success=True,
                data={
                    "communication_id": result.id,
                    "type": result.type,
                    "entity_type": result.entity_type,
                    "entity_id": result.entity_id
                },
                message=f"{input_data['comm_type'].title()} logged for {input_data['entity_type']} {input_data['entity_id']}"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
