"""
aria/tools/crm_tools.py
Perennia AI — CRM Data Bridge for Aria

Bridges Aria's task executor to existing SQLAlchemy models
for borrower/loan/user/contact lookups.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)


def _run_sync(fn):
    """Run a sync DB function in a thread to avoid blocking the event loop."""
    return asyncio.to_thread(fn)


class CRMTools:

    async def get_borrower(self, identifier: str, org_id: str) -> Optional[Dict]:
        """Look up a borrower/lead by name, email, or ID."""
        def _query():
            db = SessionLocal()
            try:
                if org_id:
                    db.execute(text("SET LOCAL app.current_tenant = :tid"), {"tid": str(org_id)})
                # Try by ID first
                try:
                    lead_id = int(identifier)
                    row = db.execute(text(
                        "SELECT id, name, email, phone, stage, loan_number, "
                        "loan_amount, property_address, organization_id "
                        "FROM leads WHERE id = :id AND organization_id = :org"
                    ), {"id": lead_id, "org": org_id}).fetchone()
                    if row:
                        return _lead_to_dict(row)
                except (ValueError, TypeError):
                    pass

                # Search by name (fuzzy)
                row = db.execute(text(
                    "SELECT id, name, email, phone, stage, loan_number, "
                    "loan_amount, property_address, organization_id "
                    "FROM leads WHERE LOWER(name) LIKE :name AND organization_id = :org "
                    "ORDER BY updated_at DESC LIMIT 1"
                ), {"name": f"%{identifier.lower()}%", "org": org_id}).fetchone()
                if row:
                    return _lead_to_dict(row)

                # Search by email
                row = db.execute(text(
                    "SELECT id, name, email, phone, stage, loan_number, "
                    "loan_amount, property_address, organization_id "
                    "FROM leads WHERE LOWER(email) = :email AND organization_id = :org "
                    "LIMIT 1"
                ), {"email": identifier.lower(), "org": org_id}).fetchone()
                if row:
                    return _lead_to_dict(row)

                return None
            finally:
                db.close()
        return await _run_sync(_query)

    async def get_active_loan(self, borrower_id: int, org_id: str) -> Optional[Dict]:
        """Get the most recent active loan for a borrower."""
        def _query():
            db = SessionLocal()
            try:
                if org_id:
                    db.execute(text("SET LOCAL app.current_tenant = :tid"), {"tid": str(org_id)})
                # NOTE: `loans` has no lead_id FK — the link to a lead is the
                # shared `loan_number`. Columns are `amount` (not loan_amount)
                # and `loan_officer_id` (not owner_id). Verified against prod schema.
                row = db.execute(text(
                    "SELECT l.id, l.loan_number, l.amount, l.loan_type, "
                    "l.stage, l.rate, l.property_address, l.purchase_price, "
                    "l.updated_at, l.loan_officer_id "
                    "FROM loans l "
                    "JOIN leads ld ON ld.loan_number = l.loan_number "
                    "AND ld.organization_id = l.organization_id "
                    "WHERE ld.id = :lead_id AND l.organization_id = :org "
                    "AND l.loan_number IS NOT NULL AND l.loan_number <> '' "
                    "AND l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN') "
                    "ORDER BY l.updated_at DESC LIMIT 1"
                ), {"lead_id": borrower_id, "org": org_id}).fetchone()
                if not row:
                    # Fallback: any loan for this lead (linked via loan_number)
                    row = db.execute(text(
                        "SELECT l.id, l.loan_number, l.amount, l.loan_type, "
                        "l.stage, l.rate, l.property_address, l.purchase_price, "
                        "l.updated_at, l.loan_officer_id "
                        "FROM loans l "
                        "JOIN leads ld ON ld.loan_number = l.loan_number "
                        "AND ld.organization_id = l.organization_id "
                        "WHERE ld.id = :lead_id AND l.organization_id = :org "
                        "AND l.loan_number IS NOT NULL AND l.loan_number <> '' "
                        "ORDER BY l.updated_at DESC LIMIT 1"
                    ), {"lead_id": borrower_id, "org": org_id}).fetchone()
                if row:
                    return {
                        "id": row[0], "loan_number": row[1],
                        "loan_amount": float(row[2]) if row[2] else 0,
                        "loan_type": row[3] or "Conventional",
                        "stage": row[4], "rate": float(row[5]) if row[5] else None,
                        "property_address": row[6],
                        "purchase_price": float(row[7]) if row[7] else None,
                        "last_activity_at": row[8].isoformat() if row[8] else None,
                        "owner_id": row[9],
                    }
                return None
            finally:
                db.close()
        return await _run_sync(_query)

    async def get_user(self, user_id: str) -> Optional[Dict]:
        """Get a user (loan officer) by ID."""
        def _query():
            db = SessionLocal()
            try:
                row = db.execute(text(
                    "SELECT id, email, first_name, last_name, phone, "
                    "organization_id, role, nmls_number "
                    "FROM users WHERE id = :id"
                ), {"id": user_id}).fetchone()
                if row:
                    return {
                        "id": row[0], "email": row[1],
                        "first_name": row[2] or "", "last_name": row[3] or "",
                        "full_name": f"{row[2] or ''} {row[3] or ''}".strip(),
                        "phone": row[4], "organization_id": row[5],
                        "role": row[6], "nmls_number": row[7] or "",
                        "title": "Loan Officer",
                        "org_name": "",
                        "org_address": "",
                    }
                return None
            finally:
                db.close()
        return await _run_sync(_query)

    async def resolve_contact(self, identifier: str, org_id: str) -> Optional[Dict]:
        """Resolve a contact by name, email, or phone — searches leads first, then users."""
        # Try as a borrower/lead first
        lead = await self.get_borrower(identifier, org_id)
        if lead:
            return {
                "id": lead["id"], "name": lead["full_name"],
                "email": lead.get("email"), "phone": lead.get("phone"),
                "type": "borrower",
            }

        # Try as a user/team member
        def _query():
            db = SessionLocal()
            try:
                if org_id:
                    db.execute(text("SET LOCAL app.current_tenant = :tid"), {"tid": str(org_id)})
                row = db.execute(text(
                    "SELECT id, email, first_name, last_name, phone "
                    "FROM users WHERE organization_id = :org "
                    "AND (LOWER(first_name || ' ' || last_name) LIKE :name "
                    "OR LOWER(email) = :email) LIMIT 1"
                ), {"org": org_id, "name": f"%{identifier.lower()}%",
                    "email": identifier.lower()}).fetchone()
                if row:
                    return {
                        "id": row[0], "name": f"{row[2] or ''} {row[3] or ''}".strip(),
                        "email": row[1], "phone": row[4], "type": "user",
                    }
                return None
            finally:
                db.close()
        return await _run_sync(_query)


def _lead_to_dict(row) -> Dict:
    return {
        "id": row[0],
        "full_name": row[1] or "",
        "last_name": (row[1] or "").split()[-1] if row[1] else "",
        "email": row[2],
        "phone": row[3],
        "stage": row[4],
        "loan_number": row[5],
        "loan_amount": float(row[6]) if row[6] else 0,
        "property_address": row[7],
        "organization_id": row[8],
    }
