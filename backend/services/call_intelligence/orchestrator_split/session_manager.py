# =============================================================================
# PERENNIA AI — Call Intelligence: Session Manager
# Extracted from orchestrator_service.py (91KB → 4 modules)
#
# This module handles:
#   - Call session lifecycle (create, update, complete, cancel)
#   - Session state machine (pending → active → processing → complete)
#   - Call metadata management
#   - Session-level configuration (STT provider, agent selection)
# =============================================================================

import logging
from uuid import uuid4
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    PENDING_CONSENT = "pending_consent"
    ACTIVE = "active"
    PROCESSING = "processing"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SessionConfig:
    """Configuration for a CI session, resolved at session creation."""

    def __init__(
        self,
        stt_provider: str = "deepgram",
        stt_model: str = "nova-2",
        stt_language: str = "en-US",
        enable_diarization: bool = True,
        extraction_mode: str = "unified",
        enabled_agents: Optional[List[str]] = None,
        confidence_threshold: float = 0.75,
        critical_field_threshold: float = 0.85,
        auto_approve_threshold: float = 0.90,
        max_session_duration_minutes: int = 120,
    ):
        self.stt_provider = stt_provider
        self.stt_model = stt_model
        self.stt_language = stt_language
        self.enable_diarization = enable_diarization
        self.extraction_mode = extraction_mode
        self.enabled_agents = enabled_agents or [
            "identity", "property", "employment",
            "financial", "compliance", "intent",
        ]
        self.confidence_threshold = confidence_threshold
        self.critical_field_threshold = critical_field_threshold
        self.auto_approve_threshold = auto_approve_threshold
        self.max_session_duration_minutes = max_session_duration_minutes


class SessionManager:
    """Manages call intelligence session lifecycle."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(
        self,
        call_control_id: Optional[str],
        loan_officer_id: str,
        organization_id: str,
        contact_id: Optional[str] = None,
        borrower_state: Optional[str] = None,
        config: Optional[SessionConfig] = None,
    ) -> Dict[str, Any]:
        session_id = str(uuid4())
        config = config or SessionConfig()

        await self.db.execute(
            sa_text("""
                INSERT INTO call_sessions (
                    id, call_control_id, loan_officer_id, organization_id,
                    contact_id, borrower_state, status,
                    stt_provider, stt_model, extraction_mode,
                    session_config, created_at, updated_at
                ) VALUES (
                    :id, :ccid, :lo_id, :org_id,
                    :contact_id, :state, :status,
                    :stt_provider, :stt_model, :extraction_mode,
                    :config, NOW(), NOW()
                )
            """),
            {
                "id": session_id,
                "ccid": call_control_id,
                "lo_id": loan_officer_id,
                "org_id": organization_id,
                "contact_id": contact_id,
                "state": borrower_state,
                "status": SessionStatus.PENDING_CONSENT.value,
                "stt_provider": config.stt_provider,
                "stt_model": config.stt_model,
                "extraction_mode": config.extraction_mode,
                "config": {
                    "enabled_agents": config.enabled_agents,
                    "confidence_threshold": config.confidence_threshold,
                    "critical_field_threshold": config.critical_field_threshold,
                    "auto_approve_threshold": config.auto_approve_threshold,
                    "diarization": config.enable_diarization,
                },
            },
        )
        await self.db.commit()

        logger.info(
            f"Session created: {session_id} | LO: {loan_officer_id} | "
            f"STT: {config.stt_provider}/{config.stt_model} | "
            f"Mode: {config.extraction_mode}"
        )

        return {
            "id": session_id,
            "status": SessionStatus.PENDING_CONSENT.value,
            "config": config,
        }

    async def activate_session(self, session_id: str):
        await self._update_status(session_id, SessionStatus.ACTIVE, {
            "activated_at": datetime.utcnow(),
        })
        logger.info(f"Session activated: {session_id}")

    async def begin_post_call_processing(self, session_id: str):
        await self._update_status(session_id, SessionStatus.PROCESSING, {
            "call_ended_at": datetime.utcnow(),
        })

    async def complete_session(
        self,
        session_id: str,
        duration_seconds: Optional[int] = None,
        summary: Optional[Dict] = None,
    ):
        extra = {"completed_at": datetime.utcnow()}
        if duration_seconds is not None:
            extra["duration_seconds"] = duration_seconds
        if summary:
            extra["session_summary"] = summary

        await self._update_status(session_id, SessionStatus.COMPLETE, extra)
        logger.info(f"Session completed: {session_id} ({duration_seconds}s)")

    async def cancel_session(self, session_id: str, reason: str = "user_cancelled"):
        await self._update_status(session_id, SessionStatus.CANCELLED, {
            "cancel_reason": reason,
            "cancelled_at": datetime.utcnow(),
        })

    async def fail_session(self, session_id: str, error: str):
        await self._update_status(session_id, SessionStatus.FAILED, {
            "error_message": error,
            "failed_at": datetime.utcnow(),
        })
        logger.error(f"Session failed: {session_id} — {error}")

    async def get_session(self, session_id: str) -> Optional[Dict]:
        result = await self.db.execute(
            sa_text("SELECT * FROM call_sessions WHERE id = :id"),
            {"id": session_id},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def get_active_sessions(self, organization_id: str) -> List[Dict]:
        result = await self.db.execute(
            sa_text("""
                SELECT cs.*, u.first_name || ' ' || u.last_name AS lo_name
                FROM call_sessions cs
                JOIN users u ON cs.loan_officer_id = u.id
                WHERE cs.organization_id = :org_id
                AND cs.status IN ('active', 'processing')
                ORDER BY cs.created_at DESC
            """),
            {"org_id": organization_id},
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_session_config(self, session_id: str) -> Optional[SessionConfig]:
        result = await self.db.execute(
            sa_text("""
                SELECT stt_provider, stt_model, extraction_mode, session_config
                FROM call_sessions WHERE id = :id
            """),
            {"id": session_id},
        )
        row = result.fetchone()
        if not row:
            return None

        cfg = row.session_config or {}
        return SessionConfig(
            stt_provider=row.stt_provider or "deepgram",
            stt_model=row.stt_model or "nova-2",
            extraction_mode=row.extraction_mode or "unified",
            enabled_agents=cfg.get("enabled_agents"),
            confidence_threshold=cfg.get("confidence_threshold", 0.75),
            critical_field_threshold=cfg.get("critical_field_threshold", 0.85),
            auto_approve_threshold=cfg.get("auto_approve_threshold", 0.90),
        )

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------

    async def _update_status(
        self, session_id: str, status: SessionStatus, extra: Optional[Dict] = None
    ):
        set_clauses = ["status = :status", "updated_at = :now"]
        params = {"session_id": session_id, "status": status.value, "now": datetime.utcnow()}

        if extra:
            for k, v in extra.items():
                set_clauses.append(f"{k} = :{k}")
                params[k] = v

        await self.db.execute(
            sa_text(f"UPDATE call_sessions SET {', '.join(set_clauses)} WHERE id = :session_id"),
            params,
        )
        await self.db.commit()
