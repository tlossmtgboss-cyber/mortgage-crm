"""
Internal API endpoints for Aria Memory & RAG.

POST /internal/aria/context    — Tier 1 context load
POST /internal/aria/retrieve   — Tier 2 retrieval (memory or guideline scope)
POST /internal/aria/consolidate — Trigger consolidation after call end

Auth: X-Internal-API-Key header (same as aria_tool_routes.py).
"""

import os
import logging
from typing import Any, Dict, Literal, Optional
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db

logger = logging.getLogger("aria.memory.routes")

router = APIRouter(prefix="/internal/aria", tags=["Aria Memory Internal"])


def _verify_internal_key(request: Request):
    import hmac
    expected = os.environ.get("INTERNAL_API_KEY", "")
    key = request.headers.get("X-Internal-API-Key", "")
    if not expected or not hmac.compare_digest(key, expected):
        raise HTTPException(status_code=403, detail="Invalid internal API key")


# ─── Request Schemas ────────────────────────────────────────────────────────

class ContextRequest(BaseModel):
    borrower_id: int
    tenant_id: int
    call_trigger: str
    loan_stage: Optional[str] = None

class RetrieveRequest(BaseModel):
    scope: Literal["memory", "guideline"]
    query: str
    tenant_id: int
    borrower_id: Optional[int] = None
    jurisdiction: Optional[str] = None
    effective_date: Optional[date] = None
    top_k: int = 5
    time_scope_days: Optional[int] = None
    topic: Optional[str] = None

class ConsolidateRequest(BaseModel):
    call_session_id: str
    tenant_id: int
    borrower_id: int
    transcript: str
    call_metadata: Dict[str, Any] = {}


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/context")
async def load_context(
    req: ContextRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Tier 1 context load at call start."""
    _verify_internal_key(request)

    from services.aria_memory.context_loader import AriaContextLoader, ContextLoadRequest
    loader = AriaContextLoader(db)
    ctx = await loader.load_context(ContextLoadRequest(
        borrower_id=req.borrower_id,
        tenant_id=req.tenant_id,
        call_trigger=req.call_trigger,
        loan_stage=req.loan_stage,
    ))
    return ctx.model_dump()


@router.post("/retrieve")
async def retrieve(
    req: RetrieveRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Shared retrieval — memory or guideline scope."""
    _verify_internal_key(request)

    if req.scope == "memory" and req.borrower_id is None:
        raise HTTPException(status_code=400, detail="borrower_id required for memory scope")

    from services.aria_memory.retrieval_service import AriaRetrievalService
    redis = _get_redis()
    service = AriaRetrievalService(db=db, redis=redis)
    result = await service.retrieve(
        scope=req.scope,
        query=req.query,
        tenant_id=req.tenant_id,
        borrower_id=req.borrower_id,
        jurisdiction=req.jurisdiction,
        effective_date=req.effective_date,
        top_k=req.top_k,
        time_scope_days=req.time_scope_days,
        topic=req.topic,
    )
    return result.model_dump()


@router.post("/consolidate", status_code=202)
async def consolidate(
    req: ConsolidateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger async consolidation after call end. Returns 202 immediately."""
    _verify_internal_key(request)

    async def _run_consolidation():
        from database import get_db as get_db_func
        consolidation_db = next(get_db_func())
        try:
            from services.aria_memory.consolidation_worker import ConsolidationWorker
            redis = _get_redis()
            worker = ConsolidationWorker(db=consolidation_db, redis=redis)
            await worker.process_call(
                call_session_id=req.call_session_id,
                tenant_id=req.tenant_id,
                borrower_id=req.borrower_id,
                transcript=req.transcript,
                call_metadata=req.call_metadata,
            )
        except Exception as e:
            logger.error("Consolidation failed for call %s: %s", req.call_session_id, e)
        finally:
            consolidation_db.close()

    background_tasks.add_task(_run_consolidation)
    return {"status": "accepted", "call_session_id": req.call_session_id}


def _get_redis():
    try:
        from services.redis_service import redis_client
        return redis_client
    except Exception:
        return None
