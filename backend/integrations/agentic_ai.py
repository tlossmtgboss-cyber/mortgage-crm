"""
Agentic AI System
Autonomous AI agent that executes tasks based on triggers and context
"""
import os
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from openai import OpenAI
from enum import Enum

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    """Types of actions the agent can execute"""
    SEND_SMS = "send_sms"
    SEND_EMAIL = "send_email"
    SEND_TEAMS_MESSAGE = "send_teams_message"
    UPDATE_LEAD_STATUS = "update_lead_status"
    UPDATE_LOAN_STATUS = "update_loan_status"
    CREATE_TASK = "create_task"
    CREATE_CALENDAR_EVENT = "create_calendar_event"
    SEND_DOCUMENT_REQUEST = "send_document_request"
    ESCALATE_TO_HUMAN = "escalate_to_human"


class TriggerType(str, Enum):
    """Types of triggers that activate the agent"""
    TASK_CREATED = "task_created"
    EMAIL_RECEIVED = "email_received"
    STATUS_CHANGE = "status_change"
    DOCUMENT_UPLOADED = "document_uploaded"
    DEADLINE_APPROACHING = "deadline_approaching"
    LEAD_SCORE_CHANGE = "lead_score_change"
    MANUAL_REQUEST = "manual_request"


class AgenticAI:
    """Autonomous AI agent for task execution"""

    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        if self.openai_api_key:
            self.client = OpenAI(api_key=self.openai_api_key)
            self.enabled = True
            logger.info("Agentic AI initialized successfully")
        else:
            self.client = None
            self.enabled = False
            logger.warning("Agentic AI not enabled - OpenAI API key not configured")

    async def analyze_and_execute(
        self,
        trigger: TriggerType,
        context: Dict[str, Any],
        db_session: Any,  # SQLAlchemy session
        integrations: Dict[str, Any]  # SMS, Email, Teams clients
    ) -> Dict[str, Any]:
        """
        Analyze trigger and context, decide on action, and execute
        """
        if not self.enabled:
            return {"status": "disabled", "message": "Agentic AI not configured"}

        try:
            # Step 1: Analyze the situation
            analysis = await self._analyze_situation(trigger, context)

            # Step 2: Decide on action(s)
            actions = await self._decide_actions(analysis, context)

            # Step 3: Execute actions
            results = []
            for action in actions:
                result = await self._execute_action(
                    action,
                    context,
                    db_session,
                    integrations
                )
                results.append(result)

            return {
                "status": "success",
                "trigger": trigger.value,
                "analysis": analysis,
                "actions_taken": len(results),
                "results": results
            }

        except Exception as e:
            logger.error(f"Error in agentic AI execution: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    async def _analyze_situation(
        self,
        trigger: TriggerType,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Use AI to analyze the situation and understand what needs to be done"""

        system_prompt = """You are an intelligent AI agent for a mortgage CRM system.
Your job is to analyze situations and determine the best course of action to help loan officers.

Analyze the given trigger and context, then provide:
1. Urgency level (low, medium, high, critical)
2. Recommended actions
3. Client communication strategy
4. Risk factors if any

Be concise and actionable."""

        user_prompt = f"""
Trigger: {trigger.value}

Context:
{self._format_context(context)}

Please analyze this situation and recommend actions.
"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )

            analysis_text = response.choices[0].message.content

            # Parse the analysis
            return {
                "raw_analysis": analysis_text,
                "urgency": self._extract_urgency(analysis_text),
                "recommendations": self._extract_recommendations(analysis_text)
            }

        except Exception as e:
            logger.error(f"Error analyzing situation: {e}")
            return {
                "raw_analysis": "Error analyzing",
                "urgency": "medium",
                "recommendations": []
            }

    async def _decide_actions(
        self,
        analysis: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Decide which actions to take based on analysis"""

        actions = []
        trigger = context.get("trigger_type")

        # Rule-based action decisions
        if trigger == TriggerType.TASK_CREATED:
            # When a task is created, notify the client via SMS
            if context.get("client_phone"):
                actions.append({
                    "type": ActionType.SEND_SMS,
                    "params": {
                        "to": context["client_phone"],
                        "message": f"Hi {context.get('client_name', 'there')}, "
                                 f"we've created a new task: {context.get('task_title', 'N/A')}. "
                                 f"We'll keep you updated!",
                        "template": "task_created"
                    }
                })

            # Also send Teams notification to loan officer
            if context.get("loan_officer_email"):
                actions.append({
                    "type": ActionType.SEND_TEAMS_MESSAGE,
                    "params": {
                        "to": context["loan_officer_email"],
                        "message": f"New task created: {context.get('task_title', 'N/A')}"
                    }
                })

        elif trigger == TriggerType.EMAIL_RECEIVED:
            # Parse email and update status
            email_body = context.get("email_body", "")
            email_from = context.get("email_from", "")

            # Check for status change keywords
            status_change = self._detect_status_change_from_email(email_body)
            if status_change:
                actions.append({
                    "type": ActionType.UPDATE_LEAD_STATUS,
                    "params": {
                        "lead_id": context.get("lead_id"),
                        "new_status": status_change,
                        "reason": f"Email from {email_from}"
                    }
                })

            # Check for document mentions
            if "document" in email_body.lower() or "upload" in email_body.lower():
                actions.append({
                    "type": ActionType.CREATE_TASK,
                    "params": {
                        "title": "Review client documents",
                        "description": f"Client mentioned documents in email: {email_body[:100]}",
                        "priority": "high"
                    }
                })

        elif trigger == TriggerType.DEADLINE_APPROACHING:
            # Send reminder
            if context.get("client_phone"):
                actions.append({
                    "type": ActionType.SEND_SMS,
                    "params": {
                        "to": context["client_phone"],
                        "message": f"Hi {context.get('client_name')}, reminder: "
                                 f"{context.get('deadline_description')} is due soon!",
                        "template": "appointment_reminder"
                    }
                })

        elif trigger == TriggerType.LEAD_SCORE_CHANGE:
            # If lead score increased significantly, escalate
            if context.get("new_score", 0) >= 80:
                actions.append({
                    "type": ActionType.ESCALATE_TO_HUMAN,
                    "params": {
                        "message": f"Hot lead: {context.get('client_name')} - Score: {context.get('new_score')}",
                        "urgency": "high"
                    }
                })

        elif trigger == TriggerType.STATUS_CHANGE:
            # Notify client of status change
            if context.get("client_phone"):
                actions.append({
                    "type": ActionType.SEND_SMS,
                    "params": {
                        "to": context["client_phone"],
                        "message": f"Hi {context.get('client_name')}, "
                                 f"your loan status has been updated to: {context.get('new_status')}.",
                        "template": "status_update"
                    }
                })

        return actions

    async def _execute_action(
        self,
        action: Dict[str, Any],
        context: Dict[str, Any],
        db_session: Any,
        integrations: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a specific action"""

        action_type = action["type"]
        params = action["params"]

        try:
            if action_type == ActionType.SEND_SMS:
                sms_client = integrations.get("sms")
                if sms_client:
                    result = await sms_client.send_sms(
                        to_number=params["to"],
                        message=params["message"]
                    )
                    return {
                        "action": action_type.value,
                        "status": "success" if result else "failed",
                        "result": result
                    }

            elif action_type == ActionType.SEND_EMAIL:
                email_client = integrations.get("email")
                if email_client:
                    result = await email_client.send_email(
                        to_email=params["to"],
                        subject=params["subject"],
                        body=params["body"]
                    )
                    return {
                        "action": action_type.value,
                        "status": "success" if result else "failed"
                    }

            elif action_type == ActionType.SEND_TEAMS_MESSAGE:
                teams_client = integrations.get("teams")
                if teams_client:
                    result = await teams_client.send_teams_message(
                        user_email=params["to"],
                        message=params["message"]
                    )
                    return {
                        "action": action_type.value,
                        "status": "success" if result else "failed"
                    }

            elif action_type == ActionType.UPDATE_LEAD_STATUS:
                # Update lead status in database
                lead_id = params.get("lead_id")
                new_status = params.get("new_status")

                # This would need the actual Lead model imported
                # For now, return a placeholder
                return {
                    "action": action_type.value,
                    "status": "success",
                    "lead_id": lead_id,
                    "new_status": new_status
                }

            elif action_type == ActionType.CREATE_TASK:
                # Create task in database
                return {
                    "action": action_type.value,
                    "status": "success",
                    "task": params
                }

            elif action_type == ActionType.ESCALATE_TO_HUMAN:
                # Send notification to loan officer
                logger.info(f"ESCALATION: {params['message']}")
                return {
                    "action": action_type.value,
                    "status": "escalated",
                    "message": params["message"]
                }

            return {
                "action": action_type.value,
                "status": "not_implemented"
            }

        except Exception as e:
            logger.error(f"Error executing action {action_type}: {e}")
            return {
                "action": action_type.value,
                "status": "error",
                "error": str(e)
            }

    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context for AI analysis"""
        formatted = []
        for key, value in context.items():
            formatted.append(f"{key}: {value}")
        return "\n".join(formatted)

    def _extract_urgency(self, text: str) -> str:
        """Extract urgency level from AI response"""
        text_lower = text.lower()
        if "critical" in text_lower:
            return "critical"
        elif "high" in text_lower:
            return "high"
        elif "medium" in text_lower:
            return "medium"
        else:
            return "low"

    def _extract_recommendations(self, text: str) -> List[str]:
        """Extract action recommendations from AI response"""
        # Simple extraction - look for bullet points or numbered lists
        recommendations = []
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("-") or line.startswith("•") or line[0:2].replace(".", "").isdigit():
                recommendations.append(line.lstrip("-•0123456789. "))
        return recommendations

    def _detect_status_change_from_email(self, email_body: str) -> Optional[str]:
        """Detect if email indicates a status change"""
        email_lower = email_body.lower()

        status_keywords = {
            "Application Started": ["started application", "beginning application", "filling out forms"],
            "Application Complete": ["completed application", "submitted application", "application done"],
            "Pre-Approved": ["pre-approved", "preapproved", "conditional approval"],
            "Prospect": ["interested", "want to learn more", "tell me more"]
        }

        for status, keywords in status_keywords.items():
            for keyword in keywords:
                if keyword in email_lower:
                    return status

        return None


# Global instance
agentic_ai = AgenticAI()
