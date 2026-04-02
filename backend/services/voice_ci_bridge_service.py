"""Voice-CI Bridge — connects Aria voice sessions to Call Intelligence sessions.

Manages the lifecycle of CI sessions initiated from the Aria voice app,
handles session lookup, and provides voice-tool-friendly access to CI results.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class VoiceCIBridgeService:
    """Bridge between Aria voice commands and Call Intelligence sessions."""

    def __init__(self, db: Session, organization_id: int, user_id: int):
        self.db = db
        self.organization_id = organization_id
        self.user_id = user_id

    async def start_ci_session(
        self,
        capture_mode: str = "mobile_app",
        context: Optional[str] = None,
        client_name: Optional[str] = None,
        client_phone: Optional[str] = None,
    ) -> str:
        """Create a new CI session and return session_id."""
        session_id = str(uuid.uuid4())
        metadata = {}
        if context:
            metadata["context"] = context
        if client_name:
            metadata["client_name"] = client_name
        if client_phone:
            metadata["client_phone"] = client_phone
        metadata["source"] = "aria_voice_app"

        import json
        self.db.execute(text("""
            INSERT INTO call_sessions (
                id, organization_id, user_id, capture_mode, status,
                started_at, metadata
            ) VALUES (
                :id, :org_id, :user_id, :capture_mode, 'active',
                NOW(), :metadata::jsonb
            )
        """), {
            "id": session_id,
            "org_id": self.organization_id,
            "user_id": str(self.user_id),
            "capture_mode": capture_mode,
            "metadata": json.dumps(metadata),
        })
        self.db.flush()

        logger.info(
            "CI session started from voice",
            extra={"session_id": session_id, "org_id": self.organization_id},
        )
        return session_id

    async def stop_ci_session(
        self, session_id: Optional[str] = None, run_agents: bool = True
    ) -> Dict[str, Any]:
        """End CI session and optionally trigger agent processing."""
        if not session_id:
            session_id = await self._get_latest_session_id()
        if not session_id:
            return {"success": False, "error": "No active CI session found"}

        self.db.execute(text("""
            UPDATE call_sessions
            SET status = :new_status, ended_at = NOW()
            WHERE id = :session_id
                AND organization_id = :org_id
                AND status = 'active'
        """), {
            "session_id": session_id,
            "new_status": "processing" if run_agents else "completed",
            "org_id": self.organization_id,
        })
        self.db.flush()

        logger.info(
            "CI session stopped from voice",
            extra={"session_id": session_id, "run_agents": run_agents},
        )
        return {"success": True, "session_id": session_id}

    async def get_latest_session(self) -> Optional[Dict[str, Any]]:
        """Get most recent CI session for this user/org."""
        row = self.db.execute(text("""
            SELECT id, status, capture_mode, started_at, ended_at,
                   full_transcript, transcript_word_count, metadata
            FROM call_sessions
            WHERE organization_id = :org_id
                AND user_id = :user_id
            ORDER BY started_at DESC
            LIMIT 1
        """), {
            "org_id": self.organization_id,
            "user_id": str(self.user_id),
        }).fetchone()

        if not row:
            return None

        return {
            "session_id": str(row.id),
            "status": row.status,
            "capture_mode": row.capture_mode,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "ended_at": row.ended_at.isoformat() if row.ended_at else None,
            "word_count": row.transcript_word_count,
        }

    async def get_session_summary(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get human-readable summary from most recent or specified session."""
        if not session_id:
            session_id = await self._get_latest_session_id()
        if not session_id:
            return {"error": "No CI session found"}

        # Get session info
        session = self.db.execute(text("""
            SELECT id, status, full_transcript, started_at, ended_at,
                   transcript_word_count
            FROM call_sessions
            WHERE id = :session_id AND organization_id = :org_id
        """), {"session_id": session_id, "org_id": self.organization_id}).fetchone()

        if not session:
            return {"error": f"Session {session_id} not found"}

        # Get summary artifacts
        summaries = self.db.execute(text("""
            SELECT title, content, artifact_type, confidence
            FROM call_artifacts
            WHERE session_id = :session_id
                AND organization_id = :org_id
                AND artifact_type IN ('summary', 'scribe_recap')
            ORDER BY created_at DESC
        """), {"session_id": session_id, "org_id": self.organization_id}).fetchall()

        # Get action items
        actions = self.db.execute(text("""
            SELECT title, content, priority, approval_status
            FROM call_artifacts
            WHERE session_id = :session_id
                AND organization_id = :org_id
                AND artifact_type = 'action_item'
            ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
        """), {"session_id": session_id, "org_id": self.organization_id}).fetchall()

        # Count all artifacts
        artifact_count = self.db.execute(text("""
            SELECT COUNT(*) as cnt FROM call_artifacts
            WHERE session_id = :session_id AND organization_id = :org_id
        """), {"session_id": session_id, "org_id": self.organization_id}).scalar()

        summary_text = ""
        if summaries:
            # Use content which may be JSONB or text
            content = summaries[0].content
            if isinstance(content, dict):
                summary_text = content.get("text", content.get("summary", str(content)))
            else:
                summary_text = str(content) if content else ""

        return {
            "session_id": str(session.id),
            "status": session.status,
            "summary": summary_text,
            "action_items": [
                {
                    "title": a.title,
                    "priority": a.priority,
                    "status": a.approval_status,
                }
                for a in actions
            ],
            "total_artifacts": artifact_count or 0,
            "duration_seconds": (
                (session.ended_at - session.started_at).total_seconds()
                if session.ended_at and session.started_at
                else None
            ),
        }

    async def get_artifacts(
        self,
        session_id: Optional[str] = None,
        artifact_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get artifacts, optionally filtered by type."""
        if not session_id:
            session_id = await self._get_latest_session_id()
        if not session_id:
            return []

        params = {"session_id": session_id, "org_id": self.organization_id}
        type_filter = ""
        if artifact_type and artifact_type != "all":
            type_filter = "AND artifact_type = :artifact_type"
            params["artifact_type"] = artifact_type

        artifacts_query = (
            "SELECT id, artifact_type, title, content, confidence,"
            " approval_status, execution_status, priority, created_at"
            " FROM call_artifacts"
            " WHERE session_id = :session_id"
            "     AND organization_id = :org_id"
            "     " + type_filter
            + " ORDER BY created_at DESC"
        )
        rows = self.db.execute(text(artifacts_query), params).fetchall()

        return [
            {
                "id": str(r.id),
                "type": r.artifact_type,
                "title": r.title,
                "content": r.content,
                "confidence": float(r.confidence) if r.confidence else None,
                "approval_status": r.approval_status,
                "execution_status": r.execution_status,
                "priority": r.priority,
            }
            for r in rows
        ]

    async def approve_artifact(
        self,
        artifact_id: Optional[str] = None,
        title_match: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approve artifact by ID or fuzzy title match."""
        if artifact_id:
            result = self.db.execute(text("""
                UPDATE call_artifacts
                SET approval_status = 'approved'
                WHERE id = :artifact_id
                    AND organization_id = :org_id
                    AND approval_status = 'pending'
                RETURNING id, title, artifact_type
            """), {"artifact_id": artifact_id, "org_id": self.organization_id}).fetchone()
        elif title_match:
            # Fuzzy match on title within most recent session
            session_id = await self._get_latest_session_id()
            if not session_id:
                return {"success": False, "error": "No CI session found"}
            result = self.db.execute(text("""
                UPDATE call_artifacts
                SET approval_status = 'approved'
                WHERE id = (
                    SELECT id FROM call_artifacts
                    WHERE session_id = :session_id
                        AND organization_id = :org_id
                        AND approval_status = 'pending'
                        AND LOWER(title) LIKE LOWER(:pattern)
                    ORDER BY created_at DESC
                    LIMIT 1
                )
                RETURNING id, title, artifact_type
            """), {
                "session_id": session_id,
                "org_id": self.organization_id,
                "pattern": f"%{title_match}%",
            }).fetchone()
        else:
            return {"success": False, "error": "Provide artifact_id or artifact_title"}

        self.db.flush()

        if not result:
            return {"success": False, "error": "No matching pending artifact found"}

        return {
            "success": True,
            "id": str(result.id),
            "title": result.title,
            "type": result.artifact_type,
        }

    async def execute_approved(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Execute all approved artifacts for a session."""
        if not session_id:
            session_id = await self._get_latest_session_id()
        if not session_id:
            return {"success": False, "error": "No CI session found", "count": 0}

        # Get all approved, unexecuted artifacts
        artifacts = self.db.execute(text("""
            SELECT id, artifact_type, title, content, priority
            FROM call_artifacts
            WHERE session_id = :session_id
                AND organization_id = :org_id
                AND approval_status = 'approved'
                AND execution_status = 'pending'
            ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
        """), {"session_id": session_id, "org_id": self.organization_id}).fetchall()

        executed = 0
        results = []

        for artifact in artifacts:
            try:
                result = await self._execute_single_artifact(artifact)
                results.append(result)

                self.db.execute(text("""
                    UPDATE call_artifacts
                    SET execution_status = 'executed'
                    WHERE id = :artifact_id AND organization_id = :org_id
                """), {"artifact_id": str(artifact.id), "org_id": self.organization_id})

                executed += 1
            except Exception as e:
                logger.error(f"Failed to execute artifact {artifact.id}: {e}")
                self.db.execute(text("""
                    UPDATE call_artifacts
                    SET execution_status = 'failed'
                    WHERE id = :artifact_id AND organization_id = :org_id
                """), {"artifact_id": str(artifact.id), "org_id": self.organization_id})

        self.db.flush()

        return {"success": True, "count": executed, "results": results}

    async def get_document_checklist(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get the document checklist artifact content."""
        if not session_id:
            session_id = await self._get_latest_session_id()
        if not session_id:
            return {"error": "No CI session found", "documents": []}

        docs = self.db.execute(text("""
            SELECT title, content, priority
            FROM call_artifacts
            WHERE session_id = :session_id
                AND organization_id = :org_id
                AND artifact_type = 'document_request'
            ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
        """), {"session_id": session_id, "org_id": self.organization_id}).fetchall()

        documents = []
        for doc in docs:
            content = doc.content
            if isinstance(content, dict):
                documents.append({
                    "title": doc.title,
                    "details": content.get("details", content.get("description", "")),
                    "priority": doc.priority,
                })
            else:
                documents.append({
                    "title": doc.title,
                    "details": str(content) if content else "",
                    "priority": doc.priority,
                })

        return {
            "session_id": session_id,
            "documents": documents,
            "count": len(documents),
        }

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    async def _get_latest_session_id(self) -> Optional[str]:
        """Get ID of the most recent CI session for this user/org."""
        row = self.db.execute(text("""
            SELECT id FROM call_sessions
            WHERE organization_id = :org_id AND user_id = :user_id
            ORDER BY started_at DESC
            LIMIT 1
        """), {
            "org_id": self.organization_id,
            "user_id": str(self.user_id),
        }).fetchone()
        return str(row.id) if row else None

    async def _execute_single_artifact(self, artifact) -> Dict[str, Any]:
        """Execute a single artifact based on its type."""
        artifact_type = artifact.artifact_type
        content = artifact.content if isinstance(artifact.content, dict) else {}

        if artifact_type == "action_item":
            # Create a CRM task
            import uuid as uuid_mod
            self.db.execute(text("""
                INSERT INTO tasks (id, title, description, priority, status, created_at, organization_id)
                VALUES (gen_random_uuid(), :title, :description, :priority, 'pending', NOW(), :org_id)
            """), {
                "title": artifact.title,
                "description": content.get("details", str(artifact.content or "")),
                "priority": artifact.priority or "medium",
                "org_id": self.organization_id,
            })
            return {"type": "task_created", "title": artifact.title}

        elif artifact_type == "document_request":
            # Create a task for the document request
            self.db.execute(text("""
                INSERT INTO tasks (id, title, description, priority, status, created_at, organization_id)
                VALUES (gen_random_uuid(), :title, :description, 'high', 'pending', NOW(), :org_id)
            """), {
                "title": f"Request: {artifact.title}",
                "description": f"Document needed: {content.get('details', artifact.title)}",
                "org_id": self.organization_id,
            })
            return {"type": "doc_request_task_created", "title": artifact.title}

        elif artifact_type in ("scheduled_appointment", "follow_up_call"):
            # Create an appointment
            self.db.execute(text("""
                INSERT INTO appointments (id, caller_name, reason, status, created_at, organization_id, notes)
                VALUES (gen_random_uuid(), :name, :reason, 'scheduled', NOW(), :org_id, :notes)
            """), {
                "name": content.get("contact_name", "From CI"),
                "reason": artifact.title,
                "org_id": self.organization_id,
                "notes": f"Created from Call Intelligence artifact: {artifact.title}",
            })
            return {"type": "appointment_created", "title": artifact.title}

        else:
            # For other types, just mark as executed (no CRM action)
            return {"type": "marked_complete", "title": artifact.title}
