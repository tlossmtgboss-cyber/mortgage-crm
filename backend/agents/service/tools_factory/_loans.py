"""Loan search & rate-lock advisory tools (extracted verbatim)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def build_loan_tools(db: Session, current_user: Any, ctx: Dict[str, Any]) -> Dict[str, Callable]:
    tools: Dict[str, Callable] = {}

    org_id = ctx["org_id"]
    _has_org_wide_access = ctx["_has_org_wide_access"]

    # ============ Loan Search Tools ============

    async def execute_search_loans(args):
        """Search for loans by borrower name, loan number, or property address."""
        query_str = args.get("query", "")
        limit = args.get("limit", 10)

        try:
            # Scope: org-wide for admins/managers, user-only for others
            if _has_org_wide_access and org_id:
                base_filter = "organization_id = :org_id"
                base_params = {"org_id": org_id, "limit": limit}
            elif _has_org_wide_access and not org_id:
                base_filter = "1=1"
                base_params = {"limit": limit}
            else:
                base_filter = "loan_officer_id = :user_id AND (:org_id IS NULL OR organization_id = :org_id)"
                base_params = {"user_id": current_user.id, "org_id": org_id, "limit": limit}

            if query_str:
                search = f"%{query_str}%"
                base_params["search"] = search
                loan_search_sql = (
                    "SELECT id, loan_number, borrower_name, stage, amount,"
                    " processor, underwriter, property_address, closing_date"
                    " FROM loans"
                    " WHERE " + base_filter +
                    " AND (borrower_name ILIKE :search OR loan_number ILIKE :search"
                    " OR property_address ILIKE :search)"
                    " LIMIT :limit"
                )
                loan_rows = db.execute(
                    text(loan_search_sql),
                    base_params
                ).fetchall()
            else:
                loan_list_sql = (
                    "SELECT id, loan_number, borrower_name, stage, amount,"
                    " processor, underwriter, property_address, closing_date"
                    " FROM loans WHERE " + base_filter +
                    " LIMIT :limit"
                )
                loan_rows = db.execute(
                    text(loan_list_sql),
                    base_params
                ).fetchall()

            return {
                "count": len(loan_rows),
                "loans": [{
                    "id": l.id,
                    "loan_number": l.loan_number,
                    "borrower_name": l.borrower_name,
                    "stage": str(l.stage) if l.stage else None,
                    "amount": float(l.amount) if l.amount else None,
                    "processor": l.processor,
                    "underwriter": l.underwriter,
                    "property_address": l.property_address,
                    "closing_date": l.closing_date.isoformat() if l.closing_date else None
                } for l in loan_rows]
            }
        except Exception as e:
            logger.error(f"Error in search_loans: {e}")
            db.rollback()
            return {"count": 0, "loans": [], "error": "Internal server error"}

    tools["search_loans"] = execute_search_loans

    # ============ Rate Lock Advisory Tools ============

    async def execute_get_rate_lock_advisory(args):
        """Get rate lock advisory based on market conditions and loan specifics."""
        days_to_close = args.get("days_to_close", 30)

        try:
            # Get loans closing in the specified timeframe (LoanStage enum values use title case like 'Funded')
            # Filter to only include future closing dates
            loans = db.execute(
                text("""SELECT id, loan_number, borrower_name, amount, closing_date,
                       rate, lock_expiration_date
                       FROM loans
                       WHERE loan_officer_id = :user_id
                       AND (:org_id IS NULL OR organization_id = :org_id)
                       AND closing_date >= CURRENT_DATE
                       AND closing_date <= CURRENT_DATE + INTERVAL ':days days'
                       AND stage::text NOT IN ('Funded')
                       ORDER BY closing_date ASC""".replace(':days', str(days_to_close))),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchall()

            # Provide advisory based on general market principles
            advisory = {
                "recommendation": "float" if days_to_close > 45 else "lock",
                "confidence": 0.7,
                "reasoning": "Based on typical market volatility and time to close",
                "loans_affected": len(loans),
                "loans": [{
                    "loan_number": l.loan_number,
                    "borrower_name": l.borrower_name,
                    "amount": float(l.amount) if l.amount else 0,
                    "closing_date": l.closing_date.isoformat() if l.closing_date else None,
                    "current_rate": float(l.rate) if l.rate else None,
                    "lock_status": "locked" if l.lock_expiration_date else "floating"
                } for l in loans[:10]]
            }

            return advisory
        except Exception as e:
            logger.error(f"Error in get_rate_lock_advisory: {e}")
            db.rollback()
            return {"error": "Internal server error", "recommendation": "consult_manager"}

    tools["get_rate_lock_advisory"] = execute_get_rate_lock_advisory

    return tools
