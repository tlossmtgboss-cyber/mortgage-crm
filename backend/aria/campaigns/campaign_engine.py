"""
Campaign Engine — orchestrates the multi-step campaign workflow.

Steps: parse_filter -> preview_audience -> compose_message -> confirm -> execute -> track
"""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from aria.tools.campaign_tools import CampaignFilterBuilder, BatchSMSSender

logger = logging.getLogger(__name__)


class CampaignStep(str, Enum):
    PARSE_FILTER = "parse_filter"
    PREVIEW_AUDIENCE = "preview_audience"
    COMPOSE_MESSAGE = "compose_message"
    CONFIRM = "confirm"
    EXECUTING = "executing"
    ACTIVE = "active"
    COMPLETED = "completed"


llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    temperature=0.3,
    max_tokens=512,
)


class CampaignEngine:
    def __init__(self):
        self.filter_builder = CampaignFilterBuilder()
        self.batch_sender = BatchSMSSender()

    async def parse_filter(
        self, user_message: str, org_id: str
    ) -> Dict[str, Any]:
        prompt = f"""Parse this campaign request into a structured filter.

User said: "{user_message}"

Available filter fields and operators:
- rate: {{gt, gte, lt, lte, eq}} (interest rate as decimal, e.g. 6.0)
- loan_amount: {{gt, gte, lt, lte, eq}}
- stage: {{in: [list], eq: "value"}} (stages: FUNDED, CLOSING, CLEAR_TO_CLOSE, etc.)
- loan_type: {{eq: "value"}} (Conventional, FHA, VA, USDA)
- closing_date: {{gt, lt}} (ISO date)

Respond ONLY with JSON:
{{
  "filter_criteria": {{...}},
  "description": "human-readable summary of the filter"
}}"""

        response = await llm.ainvoke([
            SystemMessage(content="You parse campaign criteria into structured filters. JSON only."),
            HumanMessage(content=prompt),
        ])

        try:
            parsed = json.loads(response.content.strip())
        except json.JSONDecodeError:
            return {"filter_criteria": {}, "description": "Could not parse filter"}

        filter_criteria = parsed.get("filter_criteria", {})
        recipients = self.filter_builder.preview(filter_criteria, org_id)

        return {
            "step": CampaignStep.PREVIEW_AUDIENCE.value,
            "filter_criteria": filter_criteria,
            "description": parsed.get("description", ""),
            "recipient_count": len(recipients),
            "preview": recipients[:5],
        }

    async def compose_message(
        self, intent: str, lo_name: str, include_slots: bool = True
    ) -> str:
        prompt = f"""Draft a brief, professional SMS for a mortgage campaign.

Campaign intent: {intent}
Sender: {lo_name}
Include calendar slots: {include_slots}

Use these placeholders:
- [first_name] — recipient's first name
- [lo_name] — loan officer's name
{"- [slot_1], [slot_2], [slot_3] — available meeting times" if include_slots else ""}

Keep it under 300 characters. End with a clear call to action.
Reply with the message text only, no JSON or explanation."""

        response = await llm.ainvoke([
            SystemMessage(content="You draft professional SMS messages for mortgage outreach."),
            HumanMessage(content=prompt),
        ])

        return response.content.strip().strip('"')

    async def execute_campaign(
        self,
        campaign_id: int,
        filter_criteria: dict,
        message_template: str,
        org_id: str,
        user_id: str,
        available_slots: List[str] = None,
    ) -> Dict[str, Any]:
        from aria.tools.crm_tools import CRMTools

        crm = CRMTools()
        lo = await crm.get_user(user_id)

        recipients = self.filter_builder.preview(filter_criteria, org_id)

        results = await self.batch_sender.send_batch(
            recipients=recipients,
            message_template=message_template,
            lo=lo,
            org_id=org_id,
            campaign_id=campaign_id,
            available_slots=available_slots,
        )

        try:
            from db import SessionLocal
            from database.models.aria_campaign import AriaCampaign, AriaCampaignRecipient

            db = SessionLocal()
            try:
                campaign = db.query(AriaCampaign).filter(AriaCampaign.id == campaign_id).first()
                if campaign:
                    sent = 0
                    for i, r in enumerate(results):
                        recip = AriaCampaignRecipient(
                            campaign_id=campaign_id,
                            lead_id=recipients[i].get("lead_id") if i < len(recipients) else None,
                            loan_id=recipients[i].get("loan_id") if i < len(recipients) else None,
                            phone=r["phone"],
                            first_name=recipients[i].get("lead_name", "").split()[0] if i < len(recipients) and recipients[i].get("lead_name") else None,
                            status=r["status"],
                            message_id=r.get("message_id"),
                            sent_at=datetime.now(timezone.utc) if r["status"] == "sent" else None,
                        )
                        db.add(recip)
                        if r["status"] == "sent":
                            sent += 1

                    campaign.status = "active"
                    campaign.recipient_count = len(recipients)
                    campaign.sent_count = sent
                    db.commit()
            except Exception as e:
                db.rollback()
                logger.error("Failed to persist campaign results: %s", e)
            finally:
                db.close()
        except ImportError:
            logger.debug("DB models not available — campaign results not persisted")

        sent_count = sum(1 for r in results if r["status"] == "sent")
        blocked_count = sum(1 for r in results if r["status"] == "blocked")
        failed_count = sum(1 for r in results if r["status"] == "failed")

        return {
            "campaign_id": campaign_id,
            "total_recipients": len(recipients),
            "sent": sent_count,
            "blocked": blocked_count,
            "failed": failed_count,
            "status": "active",
        }

    async def get_campaign_status(self, campaign_id: int) -> Dict[str, Any]:
        from db import SessionLocal
        from database.models.aria_campaign import AriaCampaign

        db = SessionLocal()
        try:
            campaign = db.query(AriaCampaign).filter(AriaCampaign.id == campaign_id).first()
            if not campaign:
                return {"error": "Campaign not found"}
            return {
                "campaign_id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
                "recipient_count": campaign.recipient_count,
                "sent_count": campaign.sent_count,
                "replied_count": campaign.replied_count,
                "booked_count": campaign.booked_count,
                "declined_count": campaign.declined_count,
            }
        finally:
            db.close()
