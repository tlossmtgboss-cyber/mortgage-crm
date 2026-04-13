"""
aria/core/context_loader.py
Perennia AI — Aria Context Loader

Loads pipeline context, recent contacts, and borrower data
to make Aria's questions and responses context-aware.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)


def _run_sync(fn):
    return asyncio.to_thread(fn)


class AriaContextLoader:

    async def load_full(self, user_id: str) -> Dict[str, Any]:
        """Load full pipeline context for general conversation."""
        def _query():
            db = SessionLocal()
            try:
                # Get user info
                user_row = db.execute(text(
                    "SELECT first_name, last_name, organization_id FROM users WHERE id = :uid"
                ), {"uid": user_id}).fetchone()

                if not user_row:
                    return {"user_name": "there", "org_name": "", "pipeline_summary": "", "recent_contacts": ""}

                org_id = user_row[2]
                user_name = f"{user_row[0] or ''} {user_row[1] or ''}".strip()

                # Active loan count
                active_count = db.execute(text(
                    "SELECT COUNT(*) FROM loans WHERE organization_id = :org "
                    "AND stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN')"
                ), {"org": org_id}).scalar() or 0

                # Stage breakdown
                stages = db.execute(text(
                    "SELECT stage, COUNT(*) FROM loans WHERE organization_id = :org "
                    "AND stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN') "
                    "GROUP BY stage ORDER BY COUNT(*) DESC LIMIT 5"
                ), {"org": org_id}).fetchall()

                stage_summary = ", ".join(f"{r[0]}: {r[1]}" for r in stages) if stages else "empty"

                # Urgent tasks
                urgent_count = db.execute(text(
                    "SELECT COUNT(*) FROM tasks WHERE owner_id = :uid "
                    "AND status = 'pending' AND due_date <= NOW() + INTERVAL '1 day'"
                ), {"uid": user_id}).scalar() or 0

                # Recent leads
                recent = db.execute(text(
                    "SELECT name, stage, updated_at FROM leads "
                    "WHERE organization_id = :org ORDER BY updated_at DESC LIMIT 5"
                ), {"org": org_id}).fetchall()

                recent_list = "\n".join(
                    f"- {r[0]} ({r[1]})" for r in recent
                ) if recent else "No recent contacts."

                pipeline = (
                    f"{active_count} active loans. Breakdown: {stage_summary}. "
                    f"{urgent_count} urgent task{'s' if urgent_count != 1 else ''}."
                )

                return {
                    "user_name": user_name,
                    "org_name": "",
                    "pipeline_summary": pipeline,
                    "recent_contacts": recent_list,
                    "active_loan_count": active_count,
                    "urgent_task_count": urgent_count,
                }
            except Exception as e:
                logger.error(f"Context load failed: {e}")
                return {"user_name": "there", "org_name": "", "pipeline_summary": "",
                        "recent_contacts": "", "active_loan_count": 0, "urgent_task_count": 0}
            finally:
                db.close()
        return await _run_sync(_query)

    async def load_for_slot(
        self, user_id: str, slot, slots_so_far: Dict,
    ) -> str:
        """Load context relevant to a specific slot being asked about."""
        def _query():
            db = SessionLocal()
            try:
                user_row = db.execute(text(
                    "SELECT organization_id FROM users WHERE id = :uid"
                ), {"uid": user_id}).fetchone()
                if not user_row:
                    return "No context available."

                org_id = user_row[0]

                # If asking about a borrower, show recent leads
                if slot.slot_type == "borrower":
                    rows = db.execute(text(
                        "SELECT name, loan_amount, stage, property_address "
                        "FROM leads WHERE organization_id = :org "
                        "ORDER BY updated_at DESC LIMIT 10"
                    ), {"org": org_id}).fetchall()
                    if rows:
                        lines = []
                        for r in rows:
                            amt = f"${r[1]:,.0f}" if r[1] else "N/A"
                            addr = f" — {r[3]}" if r[3] else ""
                            lines.append(f"- {r[0]} ({r[2]}, {amt}{addr})")
                        return "Recent borrowers:\n" + "\n".join(lines)

                # If we already have a borrower, load their details
                borrower_id = slots_so_far.get("borrower_id")
                if borrower_id:
                    row = db.execute(text(
                        "SELECT name, loan_amount, property_address, stage "
                        "FROM leads WHERE (id = :id OR LOWER(name) LIKE :name) "
                        "AND organization_id = :org LIMIT 1"
                    ), {"id": borrower_id if str(borrower_id).isdigit() else 0,
                        "name": f"%{str(borrower_id).lower()}%",
                        "org": org_id}).fetchone()
                    if row:
                        amt = f"${row[1]:,.0f}" if row[1] else "N/A"
                        return f"Borrower: {row[0]}, {amt} {row[2] or ''} ({row[3]})"

                return "No additional context."
            except Exception as e:
                logger.warning(f"Slot context load failed: {e}")
                return "No additional context."
            finally:
                db.close()
        return await _run_sync(_query)

    async def build_preview_context(
        self, user_id: str, intent, slots: Dict,
    ) -> str:
        """Build context for the confirmation preview."""
        # Reuse slot context with whatever borrower info we have
        return await self.load_for_slot(user_id, intent.required_slots[0] if intent.required_slots else None, slots)
