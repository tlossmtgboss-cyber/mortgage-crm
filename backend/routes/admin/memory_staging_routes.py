"""
Admin API endpoints for Memory Staging UI.

GET    /admin/memory-staging           — paginated list (tenant-scoped)
POST   /admin/memory-staging/{id}/approve — commit to agent_memories
POST   /admin/memory-staging/{id}/reject  — set terminal status
PATCH  /admin/memory-staging/{id}      — edit before approve

All endpoints require authenticated admin user + tenant scoping.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db

logger = logging.getLogger("aria.admin.staging")

router = APIRouter(prefix="/admin/memory-staging", tags=["Memory Staging Admin"])


class RejectRequest(BaseModel):
    reason: Optional[str] = None

class EditRequest(BaseModel):
    fact_text: Optional[str] = None
    topic: Optional[str] = None
    fact_type: Optional[str] = None


async def _get_admin_user(request: Request, db: Session):
    """Extract and verify admin user from Bearer token."""
    from auth.dependencies import get_current_user_flexible
    user = await get_current_user_flexible(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    perm_role = getattr(user, "permission_role", "")
    admin_roles = {"admin", "master_admin", "site_admin", "platform_admin"}
    if perm_role not in admin_roles:
        raise HTTPException(status_code=403, detail="Admin access required")

    return user


@router.get("")
async def list_staging(
    request: Request,
    db: Session = Depends(get_db),
    status: str = Query("pending_review"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    tab: str = Query("staging"),
):
    """List staged memory items, tenant-scoped to authenticated admin."""
    user = await _get_admin_user(request, db)
    tenant_id = user.organization_id

    from database.models.memory_staging import MemoryStaging

    cleanup_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    db.query(MemoryStaging).filter(
        MemoryStaging.organization_id == tenant_id,
        MemoryStaging.status.in_(["approved", "rejected"]),
        MemoryStaging.created_at < cleanup_cutoff,
    ).delete(synchronize_session='fetch')

    query = db.query(MemoryStaging).filter(MemoryStaging.organization_id == tenant_id)

    if tab == "shadow":
        query = query.filter(MemoryStaging.status.in_(["shadow_pending", "confirmed_correct"]))
    elif tab == "audit_sample":
        from database.models.memory_audit import MemoryAuditEvent
        sample_ids = (
            db.query(MemoryAuditEvent.memory_id)
            .filter(
                MemoryAuditEvent.event_type == "staging_review",
                MemoryAuditEvent.details["audit_sample"].astext == "true",
                MemoryAuditEvent.organization_id == tenant_id,
            )
            .subquery()
        )
        query = query.filter(MemoryStaging.committed_memory_id.in_(sample_ids))
    else:
        query = query.filter(MemoryStaging.status == status)

    total = query.count()
    items = (
        query
        .order_by(MemoryStaging.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "items": [
            {
                "id": item.id,
                "fact_text": item.fact_text,
                "fact_type": item.fact_type,
                "topic": item.topic,
                "confidence": item.confidence,
                "transcript_span": item.transcript_span,
                "fact_key": item.fact_key,
                "source_call_id": item.source_call_id,
                "status": item.status,
                "review_action": item.review_action,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/{item_id}/approve")
async def approve_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Approve a staged item — commit to agent_memories."""
    user = await _get_admin_user(request, db)
    tenant_id = user.organization_id

    from database.models.memory_staging import MemoryStaging
    item = db.query(MemoryStaging).filter(
        MemoryStaging.id == item_id,
        MemoryStaging.organization_id == tenant_id,
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Staging item not found")
    if item.status not in ("pending_review", "shadow_pending"):
        raise HTTPException(status_code=400, detail=f"Cannot approve item with status '{item.status}'")

    from database.models.agent_memory import AgentMemory, MemoryType
    type_map = {
        "preference": MemoryType.PREFERENCE,
        "fact": MemoryType.FACT,
        "context": MemoryType.CONTEXT,
        "insight": MemoryType.INSIGHT,
        "directive": MemoryType.DIRECTIVE,
    }

    content_hash = hashlib.sha256(item.fact_text.encode()).hexdigest()[:32]

    # Supersession check: if a preference with the same fact_key exists, supersede it
    superseded_id = None
    if item.fact_key:
        existing = db.query(AgentMemory).filter(
            AgentMemory.borrower_id == item.borrower_id,
            AgentMemory.organization_id == tenant_id,
            AgentMemory.fact_key == item.fact_key,
            AgentMemory.superseded_by.is_(None),
        ).first()
        if existing:
            superseded_id = existing.id
    else:
        # Episodic dedup: check content_hash for confirmation vs new fact
        existing = db.query(AgentMemory).filter(
            AgentMemory.borrower_id == item.borrower_id,
            AgentMemory.organization_id == tenant_id,
            AgentMemory.content_hash == content_hash,
            AgentMemory.superseded_by.is_(None),
        ).first()
        if existing:
            # Confirmation — refresh last_verified_at, don't insert new row
            existing.last_verified_at = datetime.now(timezone.utc)
            from database.models.memory_audit import MemoryAuditEvent as AuditEvent
            confirm_audit = AuditEvent(
                organization_id=tenant_id, borrower_id=item.borrower_id,
                event_type="confirmation", memory_id=existing.id,
                source_call_id=item.source_call_id,
                details={"transcript_span": item.transcript_span},
            )
            db.add(confirm_audit)
            item.status = "approved"
            item.review_action = "approved"
            item.reviewed_by = user.id
            item.reviewed_at = datetime.now(timezone.utc)
            item.committed_memory_id = existing.id
            db.commit()
            return {"status": "confirmed", "memory_id": existing.id}

    # Generate embedding for vector search
    from services.aria_memory.embedding_service import generate_embedding_async, EMBEDDING_MODEL
    embedding = await generate_embedding_async(item.fact_text)

    memory = AgentMemory(
        user_id=item.borrower_id,
        organization_id=tenant_id,
        memory_type=type_map.get(item.fact_type, MemoryType.FACT),
        key=item.fact_key or f"auto_{item.fact_type}_{item.id}",
        value=item.fact_text,
        confidence=item.confidence,
        agent_role="consolidation_worker",
        borrower_id=item.borrower_id,
        topic=item.topic,
        source_call_id=item.source_call_id,
        transcript_span=item.transcript_span,
        fact_key=item.fact_key,
        content_hash=content_hash,
        embedding=embedding,
        embedding_model=EMBEDDING_MODEL if embedding else None,
    )
    db.add(memory)
    db.flush()

    # Complete supersession: point old fact to new one
    if superseded_id:
        old_mem = db.query(AgentMemory).filter(AgentMemory.id == superseded_id).first()
        if old_mem:
            old_mem.superseded_by = memory.id
        from database.models.memory_audit import MemoryAuditEvent
        supersession_audit = MemoryAuditEvent(
            organization_id=tenant_id, borrower_id=item.borrower_id,
            event_type="supersession", memory_id=memory.id,
            source_call_id=item.source_call_id,
            details={"old_memory_id": superseded_id, "fact_key": item.fact_key},
        )
        db.add(supersession_audit)

    item.status = "approved"
    item.review_action = "approved"
    item.reviewed_by = user.id
    item.reviewed_at = datetime.now(timezone.utc)
    item.committed_memory_id = memory.id

    from database.models.memory_audit import MemoryAuditEvent
    audit = MemoryAuditEvent(
        organization_id=tenant_id,
        borrower_id=item.borrower_id,
        event_type="staging_review",
        source_call_id=item.source_call_id,
        memory_id=memory.id,
        details={"review_action": "approved", "reviewer_id": user.id},
    )
    db.add(audit)
    db.commit()

    # --- Conflict detection (post-commit) ---
    conflict_summary = None
    try:
        from services.aria_memory.conflict_detector import detect_conflicts, resolve_auto_conflicts
        conflicts = detect_conflicts(db, memory)
        if conflicts:
            conflict_summary = resolve_auto_conflicts(db, memory, conflicts)
            logger.info(
                "Conflict resolution for memory %d: %s",
                memory.id, conflict_summary,
            )
    except Exception as e:
        logger.warning("Conflict detection failed for memory %d: %s", memory.id, e)

    try:
        redis = None
        try:
            from services.redis_service import redis_client
            redis = redis_client
        except Exception:
            pass
        if redis and item.borrower_id:
            from services.aria_memory.retrieval_service import AriaRetrievalService
            svc = AriaRetrievalService(db=db, redis=redis)
            svc.invalidate_cache("memory", tenant_id, item.borrower_id)
    except Exception:
        pass

    result = {"status": "approved", "memory_id": memory.id}
    if conflict_summary:
        result["conflicts"] = conflict_summary
    return result


@router.post("/{item_id}/reject")
async def reject_item(
    item_id: int,
    body: RejectRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Reject a staged item — set terminal status."""
    user = await _get_admin_user(request, db)
    tenant_id = user.organization_id

    from database.models.memory_staging import MemoryStaging
    item = db.query(MemoryStaging).filter(
        MemoryStaging.id == item_id,
        MemoryStaging.organization_id == tenant_id,
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Staging item not found")
    if item.status not in ("pending_review", "shadow_pending"):
        raise HTTPException(status_code=400, detail=f"Cannot reject item with status '{item.status}'")

    item.status = "rejected"
    item.review_action = "rejected"
    item.reviewed_by = user.id
    item.reviewed_at = datetime.now(timezone.utc)

    from database.models.memory_audit import MemoryAuditEvent
    audit = MemoryAuditEvent(
        organization_id=tenant_id,
        borrower_id=item.borrower_id,
        event_type="staging_review",
        source_call_id=item.source_call_id,
        details={
            "review_action": "rejected",
            "reviewer_id": user.id,
            "reason": body.reason,
        },
    )
    db.add(audit)
    db.commit()

    return {"status": "rejected"}


@router.patch("/{item_id}")
async def edit_item(
    item_id: int,
    body: EditRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Edit a staged item before approving."""
    user = await _get_admin_user(request, db)
    tenant_id = user.organization_id

    from database.models.memory_staging import MemoryStaging
    item = db.query(MemoryStaging).filter(
        MemoryStaging.id == item_id,
        MemoryStaging.organization_id == tenant_id,
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Staging item not found")

    original = {"fact_text": item.fact_text, "topic": item.topic, "fact_type": item.fact_type}

    if body.fact_text is not None:
        item.fact_text = body.fact_text
        item.content_hash = hashlib.sha256(body.fact_text.encode()).hexdigest()[:32]
    if body.topic is not None:
        item.topic = body.topic
    if body.fact_type is not None:
        item.fact_type = body.fact_type

    from database.models.memory_audit import MemoryAuditEvent
    audit = MemoryAuditEvent(
        organization_id=tenant_id,
        borrower_id=item.borrower_id,
        event_type="staging_review",
        source_call_id=item.source_call_id,
        details={
            "review_action": "edited",
            "reviewer_id": user.id,
            "original": original,
        },
    )
    db.add(audit)
    db.commit()

    return {"status": "edited", "id": item.id}


@router.get("/queue-depth")
async def queue_depth(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return count of pending_review items for admin nav badge."""
    user = await _get_admin_user(request, db)
    tenant_id = user.organization_id

    from database.models.memory_staging import MemoryStaging
    count = db.query(func.count(MemoryStaging.id)).filter(
        MemoryStaging.organization_id == tenant_id,
        MemoryStaging.status == "pending_review",
    ).scalar()

    return {"pending_count": count or 0}
