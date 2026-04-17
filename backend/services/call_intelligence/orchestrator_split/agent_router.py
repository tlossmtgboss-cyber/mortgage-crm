# =============================================================================
# PERENNIA AI — Call Intelligence: Agent Router
# Extracted from orchestrator_service.py (91KB → 4 modules)
#
# This module handles:
#   - Fan-out dispatch of transcript chunks to agents
#   - Agent selection based on session config
#   - Unified vs. parallel extraction mode routing
#   - Agent result collection and merging
#   - Per-agent error isolation
# =============================================================================

import logging
import asyncio
from uuid import uuid4
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from enum import Enum

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    IDENTITY = "identity"
    PROPERTY = "property"
    EMPLOYMENT = "employment"
    FINANCIAL = "financial"
    COMPLIANCE = "compliance"
    INTENT = "intent"
    SENTIMENT = "sentiment"
    OBJECTION = "objection"
    COACHING = "coaching"
    TRANSCRIPTION = "transcription"
    CALCULATOR = "calculator"


class AgentStatus(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


class AgentResult:
    """Standardized result from any agent."""

    def __init__(
        self,
        agent_type: str,
        status: AgentStatus,
        artifacts: Optional[List[Dict]] = None,
        extracted_fields: Optional[List[Dict]] = None,
        confidence_scores: Optional[Dict[str, float]] = None,
        error: Optional[str] = None,
        processing_time_ms: int = 0,
        token_usage: Optional[Dict] = None,
    ):
        self.agent_type = agent_type
        self.status = status
        self.artifacts = artifacts or []
        self.extracted_fields = extracted_fields or []
        self.confidence_scores = confidence_scores or {}
        self.error = error
        self.processing_time_ms = processing_time_ms
        self.token_usage = token_usage or {}


class AgentRouter:
    """
    Routes transcript chunks to extraction agents.
    Supports unified (single LLM call) and parallel (per-domain) modes.
    Isolates per-agent failures so one bad extraction doesn't poison the batch.
    """

    def __init__(
        self,
        db: AsyncSession,
        llm_client: Any,
        ws_manager: Any = None,
    ):
        self.db = db
        self.llm_client = llm_client
        self.ws_manager = ws_manager
        self._agent_processors: Dict[str, Callable] = {}

    def register_agent(self, agent_type: str, processor: Callable):
        self._agent_processors[agent_type] = processor
        logger.info(f"Agent registered: {agent_type}")

    # -----------------------------------------------------------------
    # Dispatch
    # -----------------------------------------------------------------

    async def dispatch_chunk(
        self,
        session_id: str,
        chunk: Dict[str, Any],
        enabled_agents: List[str],
        extraction_mode: str = "unified",
    ) -> Dict[str, AgentResult]:
        if extraction_mode == "unified":
            return await self._dispatch_unified(session_id, chunk, enabled_agents)
        else:
            return await self._dispatch_parallel(session_id, chunk, enabled_agents)

    async def _dispatch_unified(
        self,
        session_id: str,
        chunk: Dict,
        enabled_agents: List[str],
    ) -> Dict[str, AgentResult]:
        start = datetime.utcnow()

        try:
            result = await self._run_unified_extraction(
                session_id, chunk, enabled_agents
            )

            agent_results = {}
            for agent_type in enabled_agents:
                domain_data = result.get(agent_type, {})
                agent_results[agent_type] = AgentResult(
                    agent_type=agent_type,
                    status=AgentStatus.COMPLETE,
                    extracted_fields=domain_data.get("fields", []),
                    artifacts=domain_data.get("artifacts", []),
                    confidence_scores=domain_data.get("confidence", {}),
                    processing_time_ms=int(
                        (datetime.utcnow() - start).total_seconds() * 1000
                    ),
                    token_usage=result.get("_token_usage", {}),
                )

            agent_results = await self._validate_results(agent_results)

            await self._persist_agent_runs(session_id, agent_results, "unified")
            await self._notify_frontend(session_id, agent_results)

            return agent_results

        except Exception as e:
            logger.error(
                f"Unified extraction failed for session {session_id}: {e}. "
                f"Falling back to parallel."
            )
            return await self._dispatch_parallel(session_id, chunk, enabled_agents)

    async def _dispatch_parallel(
        self,
        session_id: str,
        chunk: Dict,
        enabled_agents: List[str],
    ) -> Dict[str, AgentResult]:
        tasks = {}
        for agent_type in enabled_agents:
            processor = self._agent_processors.get(agent_type)
            if processor:
                tasks[agent_type] = asyncio.create_task(
                    self._run_agent_safe(session_id, agent_type, processor, chunk)
                )

        results = {}
        for agent_type, task in tasks.items():
            try:
                results[agent_type] = await task
            except Exception as e:
                logger.error(f"Agent {agent_type} failed: {e}")
                results[agent_type] = AgentResult(
                    agent_type=agent_type,
                    status=AgentStatus.ERROR,
                    error=str(e),
                )

        await self._persist_agent_runs(session_id, results, "parallel")
        await self._notify_frontend(session_id, results)

        return results

    async def _run_agent_safe(
        self,
        session_id: str,
        agent_type: str,
        processor: Callable,
        chunk: Dict,
    ) -> AgentResult:
        start = datetime.utcnow()
        try:
            result = await processor(session_id, chunk, self.llm_client)
            elapsed = int((datetime.utcnow() - start).total_seconds() * 1000)

            if isinstance(result, AgentResult):
                result.processing_time_ms = elapsed
                return result

            return AgentResult(
                agent_type=agent_type,
                status=AgentStatus.COMPLETE,
                extracted_fields=result.get("fields", []),
                artifacts=result.get("artifacts", []),
                confidence_scores=result.get("confidence", {}),
                processing_time_ms=elapsed,
            )
        except Exception as e:
            logger.error(f"Agent {agent_type} error in session {session_id}: {e}")
            return AgentResult(
                agent_type=agent_type,
                status=AgentStatus.ERROR,
                error=str(e),
                processing_time_ms=int(
                    (datetime.utcnow() - start).total_seconds() * 1000
                ),
            )

    # -----------------------------------------------------------------
    # Unified Extraction
    # -----------------------------------------------------------------

    async def _run_unified_extraction(
        self,
        session_id: str,
        chunk: Dict,
        enabled_agents: List[str],
    ) -> Dict:
        # TODO: Wire to existing unified_extract() from processor.py
        raise NotImplementedError(
            "Wire to existing unified_extract() from processor.py"
        )

    # -----------------------------------------------------------------
    # Validation (hallucination isolation for unified mode)
    # -----------------------------------------------------------------

    async def _validate_results(
        self, results: Dict[str, AgentResult]
    ) -> Dict[str, AgentResult]:
        from .extraction_validator import ExtractionValidator

        validator = ExtractionValidator()

        for agent_type, result in results.items():
            if result.status != AgentStatus.COMPLETE:
                continue

            validated_fields = []
            for field in result.extracted_fields:
                validation = validator.validate_field(
                    agent_type, field
                )
                if validation["valid"]:
                    validated_fields.append(field)
                else:
                    logger.warning(
                        f"Field rejected (validation): {agent_type}.{field.get('field')} "
                        f"— {validation['reason']}"
                    )
                    field["confidence"] = min(field.get("confidence", 0), 0.40)
                    field["needs_review"] = True
                    field["validation_warning"] = validation["reason"]
                    validated_fields.append(field)

            result.extracted_fields = validated_fields

        return results

    # -----------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------

    async def _persist_agent_runs(
        self,
        session_id: str,
        results: Dict[str, AgentResult],
        mode: str,
    ):
        for agent_type, result in results.items():
            await self.db.execute(
                sa_text("""
                    INSERT INTO agent_runs (
                        id, call_session_id, agent_type, status,
                        extraction_mode, processing_time_ms,
                        artifact_count, field_count,
                        token_usage, error_message,
                        created_at
                    ) VALUES (
                        :id, :session_id, :agent_type, :status,
                        :mode, :time_ms,
                        :artifacts, :fields,
                        :tokens, :error,
                        NOW()
                    )
                """),
                {
                    "id": str(uuid4()),
                    "session_id": session_id,
                    "agent_type": agent_type,
                    "status": result.status.value,
                    "mode": mode,
                    "time_ms": result.processing_time_ms,
                    "artifacts": len(result.artifacts),
                    "fields": len(result.extracted_fields),
                    "tokens": result.token_usage,
                    "error": result.error,
                },
            )
        await self.db.commit()

    # -----------------------------------------------------------------
    # Frontend Notification
    # -----------------------------------------------------------------

    async def _notify_frontend(
        self, session_id: str, results: Dict[str, AgentResult]
    ):
        if not self.ws_manager:
            return

        for agent_type, result in results.items():
            await self.ws_manager.send(session_id, {
                "event": "agent_update",
                "agent_type": agent_type,
                "status": result.status.value,
                "artifact_count": len(result.artifacts),
                "field_count": len(result.extracted_fields),
                "processing_time_ms": result.processing_time_ms,
                "has_error": result.error is not None,
            })
