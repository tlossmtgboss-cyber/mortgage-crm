"""Referral partner tools (extracted verbatim)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def build_partner_tools(db: Session, current_user: Any, ctx: Dict[str, Any]) -> Dict[str, Callable]:
    tools: Dict[str, Callable] = {}

    _ = (db, ctx)  # signature parity — these tools don't need them directly

    # Tool to create referral partners
    from ..tools.customer import create_referral_partner as _create_referral_partner

    async def execute_create_referral_partner(args):
        """Create or add a referral partner to the CRM."""
        user_id = current_user.id if hasattr(current_user, 'id') else None
        name = args.get("name", "")
        email = args.get("email", "")
        phone = args.get("phone")
        company = args.get("company")
        partner_type = args.get("partner_type", "realtor")
        notes = args.get("notes")

        try:
            result = _create_referral_partner(
                name=name,
                email=email,
                phone=phone,
                company=company,
                partner_type=partner_type,
                notes=notes,
                user_id=user_id
            )
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            logger.error(f"Error in create_referral_partner: {e}")
            return {"status": "error", "error": "Internal server error"}

    tools["create_referral_partner"] = execute_create_referral_partner

    return tools
