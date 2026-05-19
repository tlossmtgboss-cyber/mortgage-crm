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

    async def update_status(self, loan_id: int, new_stage: str, user_id: str) -> Dict:
        """Update a loan's pipeline stage."""
        def _query():
            db = SessionLocal()
            try:
                stage_upper = new_stage.upper().replace(" ", "_")
                db.execute(text(
                    "UPDATE loans SET stage = :stage, updated_at = NOW() WHERE id = :id"
                ), {"stage": stage_upper, "id": loan_id})
                db.commit()
                return {"loan_id": loan_id, "new_stage": stage_upper}
            finally:
                db.close()
        return await _run_sync(_query)

    async def add_note(
        self, loan_id: int, user_id: str,
        note: str, note_type: str = "manual",
    ) -> Dict:
        """Add a note to a loan file."""
        def _query():
            db = SessionLocal()
            try:
                # Try the notes table if it exists, otherwise update lead notes
                result = db.execute(text(
                    "INSERT INTO loan_notes (loan_id, user_id, content, note_type, created_at) "
                    "VALUES (:loan_id, :user_id, :content, :note_type, NOW()) "
                    "RETURNING id, created_at"
                ), {
                    "loan_id": loan_id, "user_id": user_id,
                    "content": note, "note_type": note_type,
                })
                db.commit()
                row = result.fetchone()
                if row:
                    return {"id": row[0], "created_at": row[1].isoformat() if row[1] else datetime.now(timezone.utc).isoformat()}
            except Exception as _exc:  # noqa: BLE001
                logger.exception("unhandled exception")
                db.rollback()
                # Fallback: append to lead.notes text field
                try:
                    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                    db.execute(text(
                        "UPDATE leads SET notes = COALESCE(notes, '') || :note_line "
                        "WHERE id = (SELECT lead_id FROM loans WHERE id = :loan_id)"
                    ), {
                        "note_line": f"\n[{timestamp}] {note}",
                        "loan_id": loan_id,
                    })
                    db.commit()
                except Exception as e2:
                    db.rollback()
                    logger.warning(f"Note fallback failed: {e2}")
            finally:
                db.close()
            return {"id": 0, "created_at": datetime.now(timezone.utc).isoformat()}
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
                rows = db.execute(text(
                    "SELECT t.id, t.title, t.due_date, t.status "
                    "FROM tasks t "
                    "JOIN loans l ON t.lead_id = l.lead_id "
                    "WHERE l.id = :loan_id AND t.status NOT IN ('completed', 'cancelled') "
                    "ORDER BY t.due_date ASC"
                ), {"loan_id": loan_id}).fetchall()
                return [{"id": r[0], "title": r[1], "due_date": str(r[2]) if r[2] else None,
                         "status": r[3]} for r in rows]
            except Exception as _exc:  # noqa: BLE001
                return []
            finally:
                db.close()
        return await _run_sync(_query)

    async def get_document_status(self, loan_id: int) -> List[Dict]:
        """Get document status for a loan."""
        def _query():
            db = SessionLocal()
            try:
                rows = db.execute(text(
                    "SELECT id, document_name, status "
                    "FROM smart_docs_requests "
                    "WHERE loan_id = :loan_id "
                    "ORDER BY created_at DESC"
                ), {"loan_id": loan_id}).fetchall()
                return [{"id": r[0], "name": r[1], "received": r[2] == "completed",
                         "status": r[2]} for r in rows]
            except Exception as _exc:  # noqa: BLE001
                return []
            finally:
                db.close()
        return await _run_sync(_query)

    async def send_document_request(
        self, loan_id: int, borrower: Dict,
        doc_list: str, due_date: Optional[str] = None,
        note: Optional[str] = None, requested_by: str = "",
    ) -> Dict:
        """Send a document request to a borrower via the portal."""
        def _query():
            db = SessionLocal()
            try:
                docs = [d.strip() for d in doc_list.split(",") if d.strip()]
                for doc_name in docs:
                    db.execute(text(
                        "INSERT INTO smart_docs_requests "
                        "(loan_id, document_name, status, requested_by, due_date, notes, created_at) "
                        "VALUES (:loan, :name, 'pending', :by, :due, :notes, NOW())"
                    ), {
                        "loan": loan_id, "name": doc_name, "by": requested_by,
                        "due": due_date, "notes": note,
                    })
                db.commit()
                portal_link = f"https://app.perenniaai.com/portal/{borrower['id']}/documents"
                return {"portal_link": portal_link, "docs_requested": len(docs)}
            except Exception as e:
                db.rollback()
                logger.error(f"Document request failed: {e}")
                return {"portal_link": "", "docs_requested": 0, "error": str(e)}
            finally:
                db.close()
        return await _run_sync(_query)

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
                    "SELECT COUNT(*), COALESCE(SUM(loan_amount), 0) FROM loans "
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
