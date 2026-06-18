"""
Recruiting Knowledge Base Management API

All endpoints require authentication (org admin or manager).

  GET    /api/v1/recruit-platform/kb/documents
  POST   /api/v1/recruit-platform/kb/documents/upload
  DELETE /api/v1/recruit-platform/kb/documents/{doc_id}
  GET    /api/v1/recruit-platform/kb/documents/{doc_id}/status
  POST   /api/v1/recruit-platform/kb/documents/{doc_id}/reprocess
"""

import asyncio
import logging
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

kb_router = APIRouter(
    prefix="/api/v1/recruit-platform/kb",
    tags=["recruit-kb"],
)

ALLOWED_TYPES = {"pdf", "docx", "txt", "md"}
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

UPLOAD_BASE = Path(__file__).resolve().parent.parent.parent / "uploads" / "recruit_kb"


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _upload_dir(org_id: int) -> Path:
    d = UPLOAD_BASE / str(org_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@kb_router.get("/documents")
async def list_documents(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = current_user.organization_id
    rows = db.execute(
        text("""
            SELECT id, filename, original_filename, file_type, file_size_bytes,
                   status, chunk_count, created_at, updated_at
            FROM recruit_kb_documents
            WHERE organization_id = :org_id
            ORDER BY created_at DESC
        """),
        {"org_id": org_id},
    ).fetchall()

    return [
        {
            "id": r.id,
            "filename": r.filename,
            "original_filename": r.original_filename,
            "file_type": r.file_type,
            "file_size_bytes": r.file_size_bytes,
            "status": r.status,
            "chunk_count": r.chunk_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@kb_router.post("/documents/upload", status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = current_user.organization_id

    ext = _ext(file.filename or "")
    if ext not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_TYPES))}",
        )

    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content):,} bytes). Maximum is 10 MB.",
        )

    # Save to disk
    upload_dir = _upload_dir(org_id)
    safe_name = f"{os.urandom(8).hex()}_{Path(file.filename or 'upload').name}"
    storage_path = upload_dir / safe_name
    storage_path.write_bytes(content)

    # Insert document record
    result = db.execute(
        text("""
            INSERT INTO recruit_kb_documents
                (organization_id, filename, original_filename, file_type,
                 file_size_bytes, storage_path, status)
            VALUES (:org_id, :filename, :original, :ftype, :fsize, :path, 'processing')
            RETURNING id
        """),
        {
            "org_id": org_id,
            "filename": safe_name,
            "original": file.filename,
            "ftype": ext,
            "fsize": len(content),
            "path": str(storage_path),
        },
    )
    doc_id = result.scalar()
    db.commit()

    # Trigger background processing
    background_tasks.add_task(_bg_process, doc_id, org_id)

    return {"doc_id": doc_id, "status": "processing"}


@kb_router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = current_user.organization_id

    row = db.execute(
        text(
            "SELECT id, storage_path FROM recruit_kb_documents "
            "WHERE id = :id AND organization_id = :org_id"
        ),
        {"id": doc_id, "org_id": org_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete chunks (CASCADE handles it, but be explicit)
    db.execute(
        text("DELETE FROM recruit_kb_chunks WHERE document_id = :id"),
        {"id": doc_id},
    )
    db.execute(
        text("DELETE FROM recruit_kb_documents WHERE id = :id"),
        {"id": doc_id},
    )
    db.commit()

    # Remove file from disk
    if row.storage_path:
        try:
            Path(row.storage_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Could not delete file %s: %s", row.storage_path, e)


@kb_router.get("/documents/{doc_id}/status")
async def document_status(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = current_user.organization_id

    row = db.execute(
        text(
            "SELECT id, status, chunk_count, updated_at "
            "FROM recruit_kb_documents WHERE id = :id AND organization_id = :org_id"
        ),
        {"id": doc_id, "org_id": org_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "doc_id": row.id,
        "status": row.status,
        "chunk_count": row.chunk_count,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@kb_router.post("/documents/{doc_id}/reprocess", status_code=202)
async def reprocess_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = current_user.organization_id

    row = db.execute(
        text(
            "SELECT id FROM recruit_kb_documents "
            "WHERE id = :id AND organization_id = :org_id"
        ),
        {"id": doc_id, "org_id": org_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    # Reset to processing
    db.execute(
        text(
            "UPDATE recruit_kb_documents "
            "SET status = 'processing', chunk_count = 0, updated_at = NOW() "
            "WHERE id = :id"
        ),
        {"id": doc_id},
    )
    db.commit()

    background_tasks.add_task(_bg_process, doc_id, org_id)

    return {"doc_id": doc_id, "status": "processing"}


# ---------------------------------------------------------------------------
# Background task wrapper
# ---------------------------------------------------------------------------

def _bg_process(doc_id: int, org_id: int) -> None:
    """Sync wrapper to run async process_document from FastAPI BackgroundTasks."""
    from services.recruit_kb_service import process_document
    from database import SessionLocal

    db = SessionLocal()
    try:
        asyncio.run(process_document(doc_id, db))
    except Exception as e:
        logger.exception("Background processing failed for doc %d: %s", doc_id, e)
    finally:
        db.close()
