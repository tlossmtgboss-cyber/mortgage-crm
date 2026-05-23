"""
Workflow AI Executor

Plans and executes AI actions for workflow nodes.
Dispatches to channel providers: Vapi (calls), Telnyx (SMS), Graph (email).
Records outcomes and updates confidence scores.

Key features:
- Communication history retrieval before drafting any action
- Supervised conversation loop: AI drafts → LO corrects → AI responds and iterates
- Confidence tracking per node × channel
"""

import uuid
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database.models.workflow_flowchart import (
    WorkflowNode, WorkflowAIAction, WorkflowLeadMovement
)
from database.models.lead_loan import Lead
from services.workflow_confidence_service import WorkflowConfidenceService

logger = logging.getLogger(__name__)


class WorkflowFlowchartExecutor:
    def __init__(self, db: Session):
        self.db = db
        self.confidence_svc = WorkflowConfidenceService(db)

    # ── Communication History ─────────────────────────────────────

    def _get_communication_history(self, lead: Lead, limit: int = 20) -> list[dict]:
        """Retrieve recent communication history for context before drafting."""
        history = []

        try:
            from database.models.communication import CommunicationLog
            logs = self.db.query(CommunicationLog).filter(
                CommunicationLog.lead_id == lead.id
            ).order_by(desc(CommunicationLog.created_at)).limit(limit).all()
            for log in logs:
                history.append({
                    "type": getattr(log, "channel", "unknown"),
                    "direction": getattr(log, "direction", "unknown"),
                    "summary": getattr(log, "summary", None) or getattr(log, "body", "")[:200],
                    "timestamp": log.created_at.isoformat() if log.created_at else None,
                    "outcome": getattr(log, "outcome", None),
                })
        except Exception as e:
            logger.debug(f"CommunicationLog not available: {e}")

        past_actions = self.db.query(WorkflowAIAction).filter(
            WorkflowAIAction.lead_id == lead.id,
            WorkflowAIAction.completed_at.isnot(None),
        ).order_by(desc(WorkflowAIAction.created_at)).limit(10).all()
        for action in past_actions:
            plan = action.action_plan or {}
            history.append({
                "type": f"ai_{action.channel}",
                "direction": "outbound",
                "summary": plan.get("objective", "AI action"),
                "timestamp": action.created_at.isoformat() if action.created_at else None,
                "outcome": action.outcome,
                "autonomy_level": action.autonomy_level,
            })

        history.sort(key=lambda h: h.get("timestamp") or "", reverse=True)
        return history[:limit]

    def _get_lead_context(self, lead: Lead) -> dict:
        """Build lead context for AI drafting."""
        return {
            "name": f"{lead.first_name} {lead.last_name}",
            "email": lead.email,
            "phone": lead.phone,
            "stage": lead.stage,
            "source": getattr(lead, "source", None),
            "loan_amount": str(getattr(lead, "loan_amount", "")) if getattr(lead, "loan_amount", None) else None,
            "property_type": getattr(lead, "property_type", None),
            "notes": getattr(lead, "notes", None),
        }

    # ── Action Planning ───────────────────────────────────────────

    def plan_action(self, node: WorkflowNode, lead: Lead, channel: str) -> dict:
        guidance = node.ai_guidance or {}
        comm_history = self._get_communication_history(lead)
        lead_context = self._get_lead_context(lead)

        return {
            "channel": channel,
            "objective": guidance.get("objective", f"Execute {node.label}"),
            "talking_points": guidance.get("talking_points", ""),
            "tone": guidance.get("tone", "warm & conversational"),
            "success_criteria": guidance.get("success_criteria", "Lead responds positively"),
            "escalation_rules": guidance.get("escalation_rules", ""),
            "lead_context": lead_context,
            "communication_history": comm_history,
            "lead_name": f"{lead.first_name} {lead.last_name}",
            "lead_email": lead.email,
            "lead_phone": lead.phone,
        }

    # ── Supervised Conversation Loop ──────────────────────────────

    def submit_review(self, action_id: str, lo_action: str, lo_version: str = None) -> Optional[dict]:
        """
        LO submits a review of an AI draft (supervised mode conversation loop).

        lo_action: "approved" | "edited" | "rejected"
        lo_version: The LO's corrected version (when lo_action == "edited")

        Returns the AI's response dict (acknowledgement or counter-suggestion).
        """
        action = self.db.query(WorkflowAIAction).filter(WorkflowAIAction.id == action_id).first()
        if not action:
            return None

        review_data = action.human_review or {"rounds": []}
        rounds = review_data.get("rounds", [])
        current_draft = action.action_plan.get("draft_message", action.action_plan.get("talking_points", ""))

        if lo_action == "approved":
            rounds.append({
                "draft": current_draft,
                "lo_action": "approved",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            action.human_review = {"rounds": rounds}

            event = "human_approved_no_edit" if len(rounds) == 1 else "success"
            new_confidence = self.confidence_svc.update_confidence(action.workflow_node_id, action.channel, event)
            action.confidence_after = new_confidence
            self.db.flush()

            return {
                "status": "approved",
                "ai_response": "Approved. Executing now.",
                "ready_to_execute": True,
            }

        elif lo_action == "edited":
            ai_response = self._generate_ai_review_response(action, current_draft, lo_version, rounds)

            rounds.append({
                "draft": current_draft,
                "lo_action": "edited",
                "lo_version": lo_version,
                "ai_response": ai_response["message"],
                "ai_revised_draft": ai_response.get("revised_draft"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            action.human_review = {"rounds": rounds}
            if ai_response.get("revised_draft"):
                plan = action.action_plan or {}
                plan["draft_message"] = ai_response["revised_draft"]
                action.action_plan = plan

            self.db.flush()
            return {
                "status": "needs_review",
                "ai_response": ai_response["message"],
                "revised_draft": ai_response.get("revised_draft", lo_version),
                "ready_to_execute": False,
            }

        elif lo_action == "rejected":
            rounds.append({
                "draft": current_draft,
                "lo_action": "rejected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            action.human_review = {"rounds": rounds}
            action.outcome = "rejected"
            action.completed_at = datetime.now(timezone.utc)

            new_confidence = self.confidence_svc.update_confidence(action.workflow_node_id, action.channel, "human_rejected")
            action.confidence_after = new_confidence
            self.db.flush()

            return {
                "status": "rejected",
                "ai_response": "Understood. I won't send this. I'll adjust my approach for next time.",
                "ready_to_execute": False,
            }

        return None

    def _generate_ai_review_response(self, action: WorkflowAIAction, original: str, corrected: str, previous_rounds: list) -> dict:
        """
        AI analyzes what the LO changed and generates a response.
        Can acknowledge the correction, or suggest an improvement on top of it.
        """
        if not corrected:
            return {"message": "I'll adjust my approach for the next draft."}

        original_words = set(original.lower().split()) if original else set()
        corrected_words = set(corrected.lower().split()) if corrected else set()
        change_ratio = len(original_words.symmetric_difference(corrected_words)) / max(len(original_words | corrected_words), 1)

        if change_ratio < 0.15:
            return {
                "message": "Small adjustment noted. I'll incorporate this phrasing going forward. Ready to send your version?",
                "revised_draft": corrected,
            }
        elif change_ratio < 0.5:
            return {
                "message": "Good corrections. I've noted the tone and phrasing changes. I'll use this style for future messages at this step. Want to send as-is, or should I refine further?",
                "revised_draft": corrected,
            }
        else:
            return {
                "message": "Significant rewrite — I'll learn from this. My original approach was off for this type of outreach. I'll model future drafts on your version. Ready to send?",
                "revised_draft": corrected,
            }

    # ── Execution ─────────────────────────────────────────────────

    async def execute_node_for_lead(self, node: WorkflowNode, lead: Lead) -> list[WorkflowAIAction]:
        if node.role != "AI":
            return []

        channels = node.channels or {}
        active_channels = [ch for ch, enabled in channels.items() if enabled and ch in ("phone", "text", "email")]

        actions = []
        for channel in active_channels:
            confidence = self.confidence_svc.get_confidence(node.id, channel)
            autonomy = self.confidence_svc.get_autonomy_level(node.id, channel)

            plan = self.plan_action(node, lead, channel)

            action = WorkflowAIAction(
                id=str(uuid.uuid4()),
                workflow_node_id=node.id,
                lead_id=lead.id,
                channel=channel,
                autonomy_level=autonomy,
                action_plan=plan,
                confidence_before=confidence,
            )
            self.db.add(action)

            if autonomy == "supervised":
                action.human_review = {"rounds": []}
                logger.info(f"AI action queued for review: node={node.label} lead={lead.id} channel={channel}")
            else:
                result = await self._dispatch(channel, plan)
                action.execution_result = result
                action.completed_at = datetime.now(timezone.utc)

                if autonomy == "guided":
                    logger.info(f"AI action executed (guided): node={node.label} lead={lead.id} channel={channel}")

            actions.append(action)

        self.db.flush()
        return actions

    async def execute_approved_action(self, action_id: str) -> Optional[WorkflowAIAction]:
        """Execute an action that was approved through the supervised review loop."""
        action = self.db.query(WorkflowAIAction).filter(WorkflowAIAction.id == action_id).first()
        if not action or action.completed_at:
            return None

        plan = action.action_plan or {}
        review = action.human_review or {}
        rounds = review.get("rounds", [])
        if rounds and rounds[-1].get("lo_action") == "approved":
            final_draft = rounds[-1].get("draft", plan.get("draft_message", plan.get("talking_points", "")))
            plan["final_approved_message"] = final_draft
            action.action_plan = plan

        result = await self._dispatch(action.channel, plan)
        action.execution_result = result
        action.completed_at = datetime.now(timezone.utc)
        self.db.flush()
        return action

    async def _dispatch(self, channel: str, plan: dict) -> dict:
        if channel == "phone":
            return await self._dispatch_call(plan)
        elif channel == "text":
            return await self._dispatch_sms(plan)
        elif channel == "email":
            return await self._dispatch_email(plan)
        return {"error": f"Unknown channel: {channel}"}

    async def _dispatch_call(self, plan: dict) -> dict:
        try:
            import aiohttp

            vapi_key = os.getenv("VAPI_API_KEY")
            if not vapi_key:
                return {"status": "error", "detail": "VAPI_API_KEY not configured"}

            talking_points = plan.get("final_approved_message", plan.get("talking_points", ""))
            comm_history_summary = ""
            for h in (plan.get("communication_history") or [])[:5]:
                comm_history_summary += f"- {h.get('type', 'contact')}: {h.get('summary', '')[:100]} ({h.get('timestamp', 'unknown')})\n"

            payload = {
                "assistantId": os.getenv("VAPI_ASSISTANT_ID"),
                "customer": {"number": plan.get("lead_phone")},
                "assistantOverrides": {
                    "firstMessage": f"Hi {plan.get('lead_name', 'there')}, this is Aria calling from your loan team.",
                    "model": {
                        "messages": [{
                            "role": "system",
                            "content": (
                                f"Objective: {plan['objective']}\n\n"
                                f"Talking points:\n{talking_points}\n\n"
                                f"Tone: {plan['tone']}\n\n"
                                f"Recent communication history:\n{comm_history_summary}"
                            )
                        }]
                    }
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.vapi.ai/call/phone",
                    headers={"Authorization": f"Bearer {vapi_key}", "Content-Type": "application/json"},
                    json=payload,
                ) as resp:
                    data = await resp.json()
                    return {"status": "initiated", "call_id": data.get("id"), "provider": "vapi"}

        except Exception as e:
            logger.error(f"Call dispatch failed: {e}")
            return {"status": "error", "detail": str(e)}

    async def _dispatch_sms(self, plan: dict) -> dict:
        try:
            import aiohttp

            telnyx_key = os.getenv("TELNYX_API_KEY")
            if not telnyx_key:
                return {"status": "error", "detail": "TELNYX_API_KEY not configured"}

            message_text = plan.get("final_approved_message")
            if not message_text:
                message_text = f"Hi {plan.get('lead_name', 'there')}, {plan['objective']}"
            if len(message_text) > 160:
                message_text = message_text[:157] + "..."

            payload = {
                "from": os.getenv("TELNYX_FROM_NUMBER", "+18438838956"),
                "to": plan.get("lead_phone"),
                "text": message_text,
                "messaging_profile_id": os.getenv("TELNYX_MESSAGING_PROFILE_ID", "40019bed-2fa1-4407-a0c6-fe4c6b222c93"),
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.telnyx.com/v2/messages",
                    headers={"Authorization": f"Bearer {telnyx_key}", "Content-Type": "application/json"},
                    json=payload,
                ) as resp:
                    data = await resp.json()
                    return {"status": "sent", "message_id": data.get("data", {}).get("id"), "provider": "telnyx"}

        except Exception as e:
            logger.error(f"SMS dispatch failed: {e}")
            return {"status": "error", "detail": str(e)}

    async def _dispatch_email(self, plan: dict) -> dict:
        try:
            import aiohttp

            graph_token = os.getenv("MS_GRAPH_ACCESS_TOKEN")
            if not graph_token:
                return {"status": "error", "detail": "MS_GRAPH_ACCESS_TOKEN not configured"}

            body_content = plan.get("final_approved_message")
            if not body_content:
                body_content = f"Hi {plan.get('lead_name', 'there')},\n\n{plan.get('talking_points', plan['objective'])}\n\nBest regards,\nYour Loan Team"

            payload = {
                "message": {
                    "subject": plan.get("objective", "Following up"),
                    "body": {
                        "contentType": "Text",
                        "content": body_content,
                    },
                    "toRecipients": [{"emailAddress": {"address": plan.get("lead_email")}}]
                },
                "saveToSentItems": True,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://graph.microsoft.com/v1.0/me/sendMail",
                    headers={"Authorization": f"Bearer {graph_token}", "Content-Type": "application/json"},
                    json=payload,
                ) as resp:
                    if resp.status == 202:
                        return {"status": "sent", "provider": "msgraph"}
                    data = await resp.json()
                    return {"status": "error", "detail": data}

        except Exception as e:
            logger.error(f"Email dispatch failed: {e}")
            return {"status": "error", "detail": str(e)}

    def record_outcome(self, action_id: str, outcome: str) -> Optional[WorkflowAIAction]:
        action = self.db.query(WorkflowAIAction).filter(WorkflowAIAction.id == action_id).first()
        if not action:
            return None

        action.outcome = outcome
        action.completed_at = datetime.now(timezone.utc)

        event_map = {
            "success": "success",
            "no_response": "success",
            "negative": "negative_outcome",
            "error": "human_rejected",
            "escalated": "human_edited",
        }
        event = event_map.get(outcome, "success")
        new_confidence = self.confidence_svc.update_confidence(action.workflow_node_id, action.channel, event)
        action.confidence_after = new_confidence

        self.db.flush()
        return action
