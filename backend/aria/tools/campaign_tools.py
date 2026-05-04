"""
Campaign Tools — filter builder and batch SMS sender for Aria campaigns.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)


class CampaignFilterBuilder:
    """Translate natural-language criteria into SQL filters for campaign audiences."""

    FILTERABLE_FIELDS = {
        "rate": ("l.rate", "number"),
        "interest_rate": ("l.rate", "number"),
        "loan_amount": ("l.loan_amount", "number"),
        "stage": ("l.stage", "stage"),
        "loan_type": ("l.loan_type", "text"),
        "closing_date": ("l.closing_date", "date"),
        "property_address": ("l.property_address", "text"),
    }

    def build_query(self, filter_criteria: dict, org_id: str) -> tuple[str, dict]:
        conditions = ["l.organization_id = :org_id"]
        params: dict = {"org_id": org_id}

        for field, spec in filter_criteria.items():
            col_info = self.FILTERABLE_FIELDS.get(field)
            if not col_info:
                continue
            col, col_type = col_info

            if isinstance(spec, dict):
                if "gt" in spec:
                    conditions.append(f"{col} > :f_{field}_gt")
                    params[f"f_{field}_gt"] = spec["gt"]
                if "gte" in spec:
                    conditions.append(f"{col} >= :f_{field}_gte")
                    params[f"f_{field}_gte"] = spec["gte"]
                if "lt" in spec:
                    conditions.append(f"{col} < :f_{field}_lt")
                    params[f"f_{field}_lt"] = spec["lt"]
                if "lte" in spec:
                    conditions.append(f"{col} <= :f_{field}_lte")
                    params[f"f_{field}_lte"] = spec["lte"]
                if "eq" in spec:
                    conditions.append(f"{col} = :f_{field}_eq")
                    params[f"f_{field}_eq"] = spec["eq"]
                if "in" in spec:
                    values = spec["in"]
                    placeholders = ", ".join(f":f_{field}_in_{i}" for i in range(len(values)))
                    conditions.append(f"UPPER({col}) IN ({placeholders})")
                    for i, v in enumerate(values):
                        params[f"f_{field}_in_{i}"] = v.upper() if isinstance(v, str) else v
            else:
                conditions.append(f"UPPER({col}) = UPPER(:f_{field})")
                params[f"f_{field}"] = spec

        where = " AND ".join(conditions)

        sql = (
            f"SELECT l.id as loan_id, l.lead_id, l.borrower_name, "
            f"l.rate, l.loan_amount, l.stage, "
            f"ld.phone, ld.email, ld.name as lead_name "
            f"FROM loans l "
            f"LEFT JOIN leads ld ON l.lead_id = ld.id "
            f"WHERE {where} "
            f"AND ld.phone IS NOT NULL AND ld.phone != '' "
            f"ORDER BY l.updated_at DESC"
        )
        return sql, params

    def preview(self, filter_criteria: dict, org_id: str) -> List[Dict]:
        sql, params = self.build_query(filter_criteria, org_id)
        db = SessionLocal()
        try:
            rows = db.execute(text(sql), params).fetchall()
            return [dict(r._mapping) for r in rows]
        finally:
            db.close()


class BatchSMSSender:
    """Send campaign SMS messages in batches via Telnyx."""

    def __init__(self):
        from aria.tools.communication_tools import CommunicationTools
        self.comms = CommunicationTools()

    async def send_batch(
        self,
        recipients: List[Dict],
        message_template: str,
        lo: Dict,
        org_id: str,
        campaign_id: int,
        available_slots: List[str] = None,
    ) -> List[Dict]:
        results = []

        for recipient in recipients:
            message = self._personalize(
                message_template,
                recipient=recipient,
                lo=lo,
                available_slots=available_slots,
            )

            try:
                from services.sms_compliance import check_sms_consent
                can_send, reason = await asyncio.to_thread(
                    check_sms_consent,
                    recipient["phone"],
                    organization_id=org_id,
                )
                if not can_send:
                    results.append({
                        "phone": recipient["phone"],
                        "status": "blocked",
                        "reason": reason,
                    })
                    continue

                send_result = await self.comms.send_sms(
                    to_phone=recipient["phone"],
                    from_user=lo,
                    message=message,
                    org_id=org_id,
                )
                results.append({
                    "phone": recipient["phone"],
                    "status": "sent",
                    "message_id": send_result.get("message_id"),
                    "sent_at": send_result.get("sent_at"),
                })
            except Exception as e:
                logger.error("Campaign SMS to %s failed: %s", recipient.get("phone", "?"), e)
                results.append({
                    "phone": recipient["phone"],
                    "status": "failed",
                    "error": str(e),
                })

            await asyncio.sleep(0.1)

        return results

    def _personalize(
        self,
        template: str,
        recipient: Dict,
        lo: Dict,
        available_slots: List[str] = None,
    ) -> str:
        msg = template
        first_name = "there"
        lead_name = recipient.get("lead_name", "")
        if recipient.get("first_name"):
            first_name = recipient["first_name"]
        elif lead_name:
            first_name = lead_name.split()[0]
        msg = msg.replace("[first_name]", first_name)
        msg = msg.replace("[lo_name]", lo.get("full_name", "your loan officer"))

        if available_slots:
            for i, slot in enumerate(available_slots[:3], 1):
                msg = msg.replace(f"[slot_{i}]", slot)

        return msg
