"""
aria/tools/pipeline_tools.py
Perennia AI — Pipeline Operations Bridge for Aria

Bridges Aria task executor to loan status updates, notes, tasks,
document requests, and pipeline reporting.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)


def _run_sync(fn):
    return asyncio.to_thread(fn)


class PipelineTools:

    # Valid loan stages (VARCHAR, stored UPPERCASE). Mirrors CLAUDE.md.
    _VALID_STAGES = {
        "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UNDERWRITING",
        "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED", "SUSPENDED", "CTC",
        "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT", "FUNDED", "CANCELLED",
        "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
    }

    async def update_status(self, loan_id: int, new_stage: str, user_id: str, org_id: str = "") -> Dict:
        """Update a loan's pipeline stage. Tenant-scoped and stage-validated."""
        stage_upper = new_stage.upper().replace(" ", "_")
        if stage_upper not in self._VALID_STAGES:
            return {
                "action": "update_status_failed",
                "error": f"'{new_stage}' is not a valid loan stage.",
            }
        if not org_id:
            return {"action": "update_status_failed", "error": "Missing organization context."}

        def _query():
            db = SessionLocal()
            try:
                # SECURITY: scope the UPDATE to the caller's org so a loan_id
                # collision cannot mutate another tenant's loan.
                result = db.execute(text(
                    "UPDATE loans SET stage = :stage, updated_at = NOW() "
                    "WHERE id = :id AND organization_id = :org"
                ), {"stage": stage_upper, "id": loan_id, "org": org_id})
                db.commit()
                if result.rowcount == 0:
                    return {
                        "action": "update_status_failed",
                        "error": "Loan not found in your organization.",
                    }
                return {"loan_id": loan_id, "new_stage": stage_upper}
            finally:
                db.close()
        return await _run_sync(_query)

    async def add_note(
        self, loan_id: int, user_id: str,
        note: str, note_type: str = "manual",
    ) -> Dict:
        """Add a note to a loan file.

        Writes to the `activities` table (type='Note'), deriving organization_id
        from the loan so the activity is correctly tenant-scoped. The previous
        implementation targeted a nonexistent `loan_notes` table and fell back to
        a `loans.lead_id` subquery (loans has no lead_id) — both threw, and it
        still returned {"id": 0} as if it had succeeded. Now it returns an honest
        error when nothing was persisted.
        """
        def _query():
            db = SessionLocal()
            try:
                # int() coercion: user_id arrives as a string from the WS layer.
                try:
                    uid = int(user_id)
                except (TypeError, ValueError):
                    uid = None
                result = db.execute(text(
                    "INSERT INTO activities (type, content, loan_id, organization_id, user_id, created_at) "
                    "SELECT 'Note', :content, l.id, l.organization_id, :user_id, NOW() "
                    "FROM loans l WHERE l.id = :loan_id "
                    "RETURNING id, created_at"
                ), {"content": note, "loan_id": loan_id, "user_id": uid})
                db.commit()
                row = result.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "created_at": row[1].isoformat() if row[1] else datetime.now(timezone.utc).isoformat(),
                    }
                # No row inserted → loan_id didn't match any loan.
                return {"action": "add_note_failed", "error": "Loan not found — note not saved."}
            except Exception as e:
                db.rollback()
                logger.error(f"add_note failed: {e}")
                return {"action": "add_note_failed", "error": "Could not save the note."}
            finally:
                db.close()
        return await _run_sync(_query)

    async def create_task(
        self, description: str, due_date: str,
        assigned_to: str, borrower_id: Optional[str] = None,
        created_by: str = "", org_id: str = "",
    ) -> Dict:
        """Create a task using the existing agent tool."""
        def _query():
            db = SessionLocal()
            try:
                result = db.execute(text(
                    "INSERT INTO tasks (title, description, due_date, status, "
                    "owner_id, lead_id, organization_id, created_at) "
                    "VALUES (:title, :desc, :due, 'pending', :owner, :lead, :org, NOW()) "
                    "RETURNING id, created_at"
                ), {
                    "title": description[:200],
                    "desc": description,
                    "due": due_date,
                    "owner": assigned_to,
                    "lead": borrower_id,
                    "org": org_id,
                })
                db.commit()
                row = result.fetchone()
                if row:
                    return {"id": row[0], "created_at": row[1].isoformat() if row[1] else ""}
                return {"id": 0, "created_at": ""}
            except Exception as e:
                db.rollback()
                logger.error(f"Task creation failed: {e}")
                return {"id": 0, "created_at": "", "error": str(e)}
            finally:
                db.close()
        return await _run_sync(_query)

    async def get_open_tasks(self, loan_id: int) -> List[Dict]:
        """Get open tasks for a loan."""
        def _query():
            db = SessionLocal()
            try:
                # tasks has a real loan_id FK; loans has no lead_id, so the old
                # JOIN on t.lead_id = l.lead_id was invalid. Filter directly.
                rows = db.execute(text(
                    "SELECT t.id, t.title, t.due_date, t.status "
                    "FROM tasks t "
                    "WHERE t.loan_id = :loan_id AND t.status NOT IN ('completed', 'cancelled') "
                    "ORDER BY t.due_date ASC"
                ), {"loan_id": loan_id}).fetchall()
                return [{"id": r[0], "title": r[1], "due_date": str(r[2]) if r[2] else None,
                         "status": r[3]} for r in rows]
            except Exception:
                return []
            finally:
                db.close()
        return await _run_sync(_query)

    async def get_document_status(self, loan_id: int, org_id: str = "") -> List[Dict]:
        """Get document-request status for a loan.

        Reads the REAL `smart_document_requests` table (singular) the portal and
        smart_docs subsystem use — not the nonexistent `smart_docs_requests`.
        status/doc_type are PG enums, cast to text. 'received' == ACCEPTED.
        """
        def _query():
            db = SessionLocal()
            try:
                rows = db.execute(text(
                    "SELECT r.id, r.title, CAST(r.status AS TEXT), CAST(r.doc_type AS TEXT) "
                    "FROM smart_document_requests r "
                    "JOIN loans l ON l.id = r.loan_id "
                    "WHERE r.loan_id = :loan_id AND l.organization_id = :org "
                    "AND r.is_active = TRUE "
                    "ORDER BY r.created_at DESC"
                ), {"loan_id": loan_id, "org": org_id}).fetchall()
                return [{"id": r[0], "name": r[1],
                         "received": (r[2] or "").upper() == "ACCEPTED",
                         "status": r[2], "doc_type": r[3]} for r in rows]
            except Exception as e:
                logger.error(f"get_document_status failed: {e}")
                return []
            finally:
                db.close()
        return await _run_sync(_query)

    async def send_document_request(
        self, loan_id: int, borrower: Dict,
        doc_list: str, due_date: Optional[str] = None,
        note: Optional[str] = None, requested_by: str = "", org_id: str = "",
    ) -> Dict:
        """Create borrower document requests via the canonical NeedsListGenerator.

        Writes real rows into `smart_document_requests` (keyed on loan_id) so they
        surface in the borrower portal. Replaces the prior INSERT into the
        nonexistent `smart_docs_requests` table with fabricated columns. The
        generator resolves organization_id + enum types from the loan.
        """
        def _work():
            db = SessionLocal()
            try:
                # Defense-in-depth: never create rows on another tenant's loan.
                owns = db.execute(text(
                    "SELECT 1 FROM loans WHERE id = :id AND organization_id = :org"
                ), {"id": loan_id, "org": org_id}).fetchone()
                if not owns:
                    return {"action": "document_request_failed", "docs_requested": 0,
                            "error": "Loan not found in your organization."}

                from services.smart_docs.needs_list_generator import NeedsListGenerator
                gen = NeedsListGenerator(db)

                parsed_due = None
                if due_date:
                    try:
                        parsed_due = datetime.fromisoformat(str(due_date).replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        parsed_due = None

                docs = [d.strip() for d in doc_list.split(",") if d.strip()]
                created = 0
                for doc_name in docs:
                    gen.add_custom_request(
                        loan_id=loan_id,
                        borrower_id=None,   # Aria resolves a lead, not a borrower_profiles.id; portal keys on loan_id
                        title=doc_name,
                        description=note,
                        instructions=note,
                        priority="NORMAL",
                        due_date=parsed_due,
                        doc_type=None,      # mapped to DocType.OTHER unless the name matches a known type
                    )
                    created += 1
                return {"portal_link": "", "docs_requested": created}
            except Exception as e:
                db.rollback()
                logger.error(f"send_document_request failed: {e}", exc_info=True)
                return {"action": "document_request_failed", "docs_requested": 0,
                        "error": "Could not create the document request(s)."}
            finally:
                db.close()
        return await _run_sync(_work)

    async def generate_report(
        self, user_id: str, org_id: str,
        time_period: str = "this month",
        filter_by: Optional[str] = None,
    ) -> Dict:
        """Generate a pipeline performance summary."""
        def _query():
            db = SessionLocal()
            try:
                # Active loans
                active = db.execute(text(
                    "SELECT COUNT(*) FROM loans "
                    "WHERE organization_id = :org "
                    "AND stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN')"
                ), {"org": org_id}).scalar() or 0

                # By stage breakdown
                stages = db.execute(text(
                    "SELECT stage, COUNT(*) FROM loans "
                    "WHERE organization_id = :org "
                    "AND stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN') "
                    "GROUP BY stage ORDER BY COUNT(*) DESC"
                ), {"org": org_id}).fetchall()

                # Funded this month
                funded = db.execute(text(
                    "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM loans "
                    "WHERE organization_id = :org AND stage = 'FUNDED' "
                    "AND updated_at >= DATE_TRUNC('month', NOW())"
                ), {"org": org_id}).fetchone()

                return {
                    "active_loans": active,
                    "by_stage": {r[0]: r[1] for r in stages},
                    "funded_this_month": funded[0] if funded else 0,
                    "funded_volume": float(funded[1]) if funded else 0,
                    "time_period": time_period,
                }
            except Exception as e:
                logger.error(f"Pipeline report failed: {e}")
                return {"error": str(e)}
            finally:
                db.close()
        return await _run_sync(_query)
