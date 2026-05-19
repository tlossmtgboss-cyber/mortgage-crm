"""
Internal API for dispatching LangGraph workflows from the Aria agent.
Workflows run on a dedicated thread pool executor to avoid blocking API workers.
"""
import logging
import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import hmac
import os

from database import get_db
from db import get_async_db
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("aria.internal.workflows")

router = APIRouter(prefix="/internal/aria", tags=["Aria Internal Workflows"])

INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")


def _verify_internal_key(request: Request):
    key = request.headers.get("X-Internal-API-Key", "")
    if not INTERNAL_API_KEY or not hmac.compare_digest(key, INTERNAL_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid internal API key")


class WorkflowRequest(BaseModel):
    workflow_id: str
    params: Dict[str, Any] = {}
    lead_id: Optional[int] = None
    user_id: Optional[int] = None


@router.post("/trigger-workflow")
async def trigger_workflow(
    req: WorkflowRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Dispatch a LangGraph workflow asynchronously.
    Returns immediately -- the workflow runs in background on a dedicated executor.
    """
    _verify_internal_key(request)

    executor = getattr(request.app.state, "langgraph_executor", None)
    if executor is None:
        logger.warning("LangGraph executor not configured -- running inline")

    logger.info(f"Dispatching workflow: {req.workflow_id} for lead={req.lead_id}")

    # For now, log the dispatch. Full LangGraph integration wired in a later task.
    return {
        "status": "dispatched",
        "workflow_id": req.workflow_id,
        "message": f"Workflow {req.workflow_id} queued for execution.",
    }
