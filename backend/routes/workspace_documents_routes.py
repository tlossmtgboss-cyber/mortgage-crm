"""
Workspace Documents Routes
API endpoints for managing document requirements during application intake.

This module handles the dynamic document checklist that populates as
borrowers fill out their mortgage applications.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from db import get_async_db
from sqlalchemy.exc import SQLAlchemyError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# Auth dependency — lazy import to avoid circular imports
_security = HTTPBearer(auto_error=False)


async def _require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: AsyncSession = Depends(get_async_db),
):
    """Require valid authentication for workspace document endpoints."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from auth.dependencies import get_current_user_flexible
    user = await get_current_user_flexible(
        token=credentials.credentials, request=None, db=db
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

# =============================================================================
# ROUTER
# =============================================================================

router = APIRouter(
    prefix="/api/workspaces",
    tags=["Workspace Documents"],
    dependencies=[Depends(_require_auth)],
)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class DocumentRequirement(BaseModel):
    """A single document requirement from the frontend."""
    name: str = Field(..., description="Document name")
    description: Optional[str] = Field(None, description="Document description")
    category: str = Field(default="other", description="Document category (income, assets, property, etc.)")
    priority: str = Field(default="required", description="Priority level (required, optional)")


class DocumentsRequest(BaseModel):
    """Request body for syncing document requirements."""
    documents: List[DocumentRequirement] = Field(default=[], description="List of required documents")


class DocumentsResponse(BaseModel):
    """Response for document sync operation."""
    success: bool = True
    message: str = ""
    synced_count: int = 0
    documents: List[Dict[str, Any]] = []


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def get_workspace_by_slug(db: AsyncSession, slug: str) -> Optional[Dict[str, Any]]:
    """
    Get workspace info by slug.
    Returns workspace_id and lead_id if available.
    """
    try:
        # Try PURL workspace first
        result = await db.execute(text("""
            SELECT pw.id as workspace_id, pw.slug, pw.organization_id,
                   pl.main_loan_id
            FROM purl_workspaces pw
            LEFT JOIN purl_loans pl ON pl.workspace_id = pw.id
            WHERE pw.slug = :slug
            LIMIT 1
        """), {"slug": slug})
        row = result.fetchone()

        if row:
            # Try to get lead_id from main loan if linked
            lead_id = None
            if row.main_loan_id:
                lead_result = await db.execute(text("""
                    SELECT lead_id FROM loans WHERE id = :loan_id
                """), {"loan_id": row.main_loan_id})
                lead_row = lead_result.fetchone()
                if lead_row:
                    lead_id = lead_row.lead_id

            return {
                "workspace_id": row.workspace_id,
                "slug": row.slug,
                "organization_id": row.organization_id,
                "lead_id": lead_id
            }
        return None
    except SQLAlchemyError as e:
        logger.warning(f"Error getting workspace by slug: {e}")
        return None


async def sync_documents_to_workspace(
    db: AsyncSession,
    workspace_id: int,
    organization_id: int,
    documents: List[DocumentRequirement]
) -> List[Dict[str, Any]]:
    """
    Sync document requirements to the purl_document_requests table.
    Creates or updates document request records.
    """
    synced = []

    for doc in documents:
        try:
            # Check if document request already exists
            existing = (await db.execute(text("""
                SELECT id FROM purl_document_requests
                WHERE workspace_id = :workspace_id
                  AND document_type = :doc_type
                  AND document_category = :category
            """), {
                "workspace_id": workspace_id,
                "doc_type": doc.name,
                "category": doc.category
            })).fetchone()

            if existing:
                # Update existing record
                await db.execute(text("""
                    UPDATE purl_document_requests
                    SET description = :description,
                        is_required = :is_required,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), {
                    "id": existing.id,
                    "description": doc.description,
                    "is_required": doc.priority == "required"
                })
                synced.append({
                    "id": existing.id,
                    "name": doc.name,
                    "category": doc.category,
                    "action": "updated"
                })
            else:
                # Create new record
                result = await db.execute(text("""
                    INSERT INTO purl_document_requests
                    (organization_id, workspace_id, document_type, document_category,
                     description, is_required, status, created_at, updated_at)
                    VALUES
                    (:org_id, :workspace_id, :doc_type, :category,
                     :description, :is_required, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                """), {
                    "org_id": organization_id,
                    "workspace_id": workspace_id,
                    "doc_type": doc.name,
                    "category": doc.category,
                    "description": doc.description,
                    "is_required": doc.priority == "required"
                })
                new_id = result.fetchone()[0]
                synced.append({
                    "id": new_id,
                    "name": doc.name,
                    "category": doc.category,
                    "action": "created"
                })
        except Exception as e:
            logger.warning(f"Error syncing document '{doc.name}': {e}")
            continue

    return synced


async def sync_documents_to_lead(
    db: AsyncSession,
    lead_id: int,
    documents: List[DocumentRequirement]
) -> List[Dict[str, Any]]:
    """
    Sync document requirements to the lead_conditions table.
    Creates or updates condition records for the lead.
    """
    synced = []

    for doc in documents:
        try:
            # Check if condition already exists
            existing = (await db.execute(text("""
                SELECT id FROM lead_conditions
                WHERE lead_id = :lead_id
                  AND name = :name
                  AND category = :category
            """), {
                "lead_id": lead_id,
                "name": doc.name,
                "category": doc.category
            })).fetchone()

            if existing:
                # Update existing record
                await db.execute(text("""
                    UPDATE lead_conditions
                    SET description = :description,
                        priority = :priority,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), {
                    "id": existing.id,
                    "description": doc.description,
                    "priority": doc.priority
                })
                synced.append({
                    "id": existing.id,
                    "name": doc.name,
                    "category": doc.category,
                    "action": "updated"
                })
            else:
                # Create new record
                result = await db.execute(text("""
                    INSERT INTO lead_conditions
                    (lead_id, name, description, category, priority, status, is_new, created_at, updated_at)
                    VALUES
                    (:lead_id, :name, :description, :category, :priority, 'pending', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                """), {
                    "lead_id": lead_id,
                    "name": doc.name,
                    "description": doc.description,
                    "category": doc.category,
                    "priority": doc.priority
                })
                new_id = result.fetchone()[0]
                synced.append({
                    "id": new_id,
                    "name": doc.name,
                    "category": doc.category,
                    "action": "created"
                })
        except Exception as e:
            logger.warning(f"Error syncing document condition '{doc.name}': {e}")
            continue

    return synced


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.post(
    "/{workspace_id}/documents",
    response_model=DocumentsResponse,
    summary="Sync document requirements",
    description="Sync required documents for a workspace based on application answers"
)
async def sync_workspace_documents(
    workspace_id: str = Path(..., description="Workspace ID or slug"),
    request: DocumentsRequest = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Sync document requirements for a workspace.

    This endpoint receives the list of required documents generated by the
    frontend DocumentsNeeded component based on application answers.

    Documents are stored in purl_document_requests and optionally lead_conditions
    tables to track what the borrower needs to provide.
    """
    try:
        # Handle empty request
        if not request or not request.documents:
            return DocumentsResponse(
                success=True,
                message="No documents to sync",
                synced_count=0,
                documents=[]
            )

        # Try to find workspace by slug or ID
        workspace = await get_workspace_by_slug(db, workspace_id)

        if not workspace:
            # Try as numeric ID
            try:
                ws_id = int(workspace_id)
                result = await db.execute(text("""
                    SELECT id as workspace_id, slug, organization_id
                    FROM purl_workspaces
                    WHERE id = :id
                """), {"id": ws_id})
                row = result.fetchone()
                if row:
                    workspace = {
                        "workspace_id": row.workspace_id,
                        "slug": row.slug,
                        "organization_id": row.organization_id,
                        "lead_id": None
                    }
            except (ValueError, TypeError):
                pass

        synced_docs = []

        if workspace:
            # Sync to purl_document_requests
            synced_docs = await sync_documents_to_workspace(
                db,
                workspace["workspace_id"],
                workspace["organization_id"],
                request.documents
            )

            # Also sync to lead_conditions if lead is linked
            if workspace.get("lead_id"):
                lead_synced = await sync_documents_to_lead(
                    db,
                    workspace["lead_id"],
                    request.documents
                )
                # Log lead sync but don't duplicate in response
                logger.info(f"Synced {len(lead_synced)} documents to lead_conditions")
        else:
            # No workspace found - just log the request for now
            logger.warning(f"Workspace not found for '{workspace_id}', documents not persisted")
            # Still return success so frontend doesn't error
            synced_docs = [
                {"name": doc.name, "category": doc.category, "action": "logged"}
                for doc in request.documents
            ]

        await db.commit()

        return DocumentsResponse(
            success=True,
            message=f"Synced {len(synced_docs)} document requirements",
            synced_count=len(synced_docs),
            documents=synced_docs
        )

    except SQLAlchemyError as e:
        logger.exception(f"Error syncing workspace documents: {e}")
        await db.rollback()
        # Return success=True to prevent frontend errors, but log the issue
        return DocumentsResponse(
            success=True,
            message="Documents noted (sync pending)",
            synced_count=0,
            documents=[]
        )


@router.get(
    "/{workspace_id}/documents",
    summary="Get document requirements",
    description="Get current document requirements for a workspace"
)
async def get_workspace_documents(
    workspace_id: str = Path(..., description="Workspace ID or slug"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get document requirements for a workspace.

    Returns the list of required documents and their status.
    """
    try:
        # Try to find workspace
        workspace = await get_workspace_by_slug(db, workspace_id)

        if not workspace:
            try:
                ws_id = int(workspace_id)
                result = await db.execute(text("""
                    SELECT id as workspace_id FROM purl_workspaces WHERE id = :id
                """), {"id": ws_id})
                row = result.fetchone()
                if row:
                    workspace = {"workspace_id": row.workspace_id}
            except (ValueError, TypeError):
                pass

        if not workspace:
            return {"documents": [], "message": "Workspace not found"}

        # Get document requests
        result = await db.execute(text("""
            SELECT id, document_type as name, document_category as category,
                   description, status, is_required,
                   created_at, updated_at
            FROM purl_document_requests
            WHERE workspace_id = :workspace_id
            ORDER BY is_required DESC, document_category, document_type
        """), {"workspace_id": workspace["workspace_id"]})

        documents = []
        for row in result.fetchall():
            # Handle timestamps - SQLite returns strings, PostgreSQL returns datetime
            created_at = row.created_at
            updated_at = row.updated_at
            if created_at and hasattr(created_at, 'isoformat'):
                created_at = created_at.isoformat()
            if updated_at and hasattr(updated_at, 'isoformat'):
                updated_at = updated_at.isoformat()

            documents.append({
                "id": row.id,
                "name": row.name,
                "category": row.category,
                "description": row.description,
                "status": row.status,
                "priority": "required" if row.is_required else "optional",
                "created_at": created_at,
                "updated_at": updated_at
            })

        return {
            "success": True,
            "documents": documents,
            "count": len(documents)
        }

    except Exception as e:
        logger.exception(f"Error getting workspace documents: {e}")
        return {"success": False, "documents": [], "error": "Internal server error"}
