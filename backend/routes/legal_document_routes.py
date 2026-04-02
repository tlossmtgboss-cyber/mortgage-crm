"""
Tenant Legal Document Routes — WL-007

Per-tenant Terms & Conditions, Privacy Policy, and borrower-facing legal document management:
    GET    /api/v1/admin/legal-documents              — List org legal documents
    GET    /api/v1/admin/legal-documents/{id}          — Get single document
    POST   /api/v1/admin/legal-documents               — Create/update legal document
    PUT    /api/v1/admin/legal-documents/{id}           — Update document
    POST   /api/v1/admin/legal-documents/{id}/publish   — Publish version
    GET    /api/v1/legal/{org_slug}/{doc_type}          — Public endpoint for borrowers
"""
from fastapi import Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import json
import logging

logger = logging.getLogger(__name__)


class LegalDocumentCreate(BaseModel):
    document_type: str  # terms_of_service, privacy_policy, consent_to_contact, e_consent, equal_housing, licensing_disclosure
    title: str
    content_html: str
    content_text: Optional[str] = None
    version: str = "1.0"
    effective_date: Optional[str] = None
    requires_acceptance: bool = True


class LegalDocumentUpdate(BaseModel):
    title: Optional[str] = None
    content_html: Optional[str] = None
    content_text: Optional[str] = None
    version: Optional[str] = None
    effective_date: Optional[str] = None
    requires_acceptance: Optional[bool] = None


def register_legal_document_routes(app, get_db, get_current_user, **kwargs):
    """Register per-tenant legal document endpoints (WL-007)."""

    VALID_DOC_TYPES = [
        "terms_of_service", "privacy_policy", "consent_to_contact",
        "e_consent", "equal_housing", "licensing_disclosure",
    ]

    def _require_admin(current_user):
        role = getattr(current_user, 'permission_role', None) or getattr(current_user, 'role', None)
        if role not in ('admin', 'site_admin', 'leadership'):
            raise HTTPException(status_code=403, detail="Admin access required")

    # ==================================================================
    # List legal documents
    # ==================================================================
    @app.get("/api/v1/admin/legal-documents", tags=["Legal Documents"])
    async def list_legal_documents(
        document_type: Optional[str] = Query(None),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """List all legal documents for the organization (WL-007)."""
        _require_admin(current_user)
        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        query = """
            SELECT id, document_type, title, version, is_published,
                   effective_date, requires_acceptance, created_at, updated_at, published_at
            FROM tenant_legal_documents
            WHERE organization_id = :org_id
        """
        params = {"org_id": org_id}
        if document_type:
            query += " AND document_type = :dt"
            params["dt"] = document_type

        query += " ORDER BY document_type, version DESC"

        rows = db.execute(text(query), params).fetchall()
        docs = []
        for r in rows:
            docs.append({
                "id": r[0], "document_type": r[1], "title": r[2],
                "version": r[3], "is_published": r[4],
                "effective_date": str(r[5]) if r[5] else None,
                "requires_acceptance": r[6],
                "created_at": str(r[7]) if r[7] else None,
                "updated_at": str(r[8]) if r[8] else None,
                "published_at": str(r[9]) if r[9] else None,
            })

        return {"documents": docs, "count": len(docs), "valid_types": VALID_DOC_TYPES}

    # ==================================================================
    # Get single legal document
    # ==================================================================
    @app.get("/api/v1/admin/legal-documents/{doc_id}", tags=["Legal Documents"])
    async def get_legal_document(
        doc_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get a legal document with full content (WL-007)."""
        _require_admin(current_user)
        org_id = getattr(current_user, 'organization_id', None)

        row = db.execute(text("""
            SELECT id, organization_id, document_type, title, content_html, content_text,
                   version, is_published, effective_date, requires_acceptance,
                   created_by_id, created_at, updated_at, published_at
            FROM tenant_legal_documents
            WHERE id = :id AND organization_id = :org_id
        """), {"id": doc_id, "org_id": org_id}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Legal document not found")

        return {
            "id": row[0], "organization_id": row[1], "document_type": row[2],
            "title": row[3], "content_html": row[4], "content_text": row[5],
            "version": row[6], "is_published": row[7],
            "effective_date": str(row[8]) if row[8] else None,
            "requires_acceptance": row[9], "created_by_id": row[10],
            "created_at": str(row[11]) if row[11] else None,
            "updated_at": str(row[12]) if row[12] else None,
            "published_at": str(row[13]) if row[13] else None,
        }

    # ==================================================================
    # Create legal document
    # ==================================================================
    @app.post("/api/v1/admin/legal-documents", tags=["Legal Documents"], status_code=201)
    async def create_legal_document(
        body: LegalDocumentCreate,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Create a new legal document for the organization (WL-007)."""
        _require_admin(current_user)
        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        if body.document_type not in VALID_DOC_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid type. Must be one of: {VALID_DOC_TYPES}")

        result = db.execute(text("""
            INSERT INTO tenant_legal_documents
                (organization_id, document_type, title, content_html, content_text,
                 version, effective_date, requires_acceptance, is_published,
                 created_by_id, created_at, updated_at)
            VALUES
                (:org_id, :doc_type, :title, :content_html, :content_text,
                 :version, :effective_date, :requires_acceptance, false,
                 :user_id, NOW(), NOW())
            RETURNING id
        """), {
            "org_id": org_id,
            "doc_type": body.document_type,
            "title": body.title,
            "content_html": body.content_html,
            "content_text": body.content_text,
            "version": body.version,
            "effective_date": body.effective_date,
            "requires_acceptance": body.requires_acceptance,
            "user_id": current_user.id,
        })
        doc_id = result.fetchone()[0]
        db.commit()

        return {"id": doc_id, "message": f"Legal document '{body.title}' created (draft)"}

    # ==================================================================
    # Update legal document
    # ==================================================================
    @app.put("/api/v1/admin/legal-documents/{doc_id}", tags=["Legal Documents"])
    async def update_legal_document(
        doc_id: int,
        body: LegalDocumentUpdate,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Update a legal document (WL-007)."""
        _require_admin(current_user)
        org_id = getattr(current_user, 'organization_id', None)

        existing = db.execute(text(
            "SELECT id, is_published FROM tenant_legal_documents WHERE id = :id AND organization_id = :org_id"
        ), {"id": doc_id, "org_id": org_id}).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Legal document not found")

        updates = []
        params = {"id": doc_id, "org_id": org_id}
        for field in ["title", "content_html", "content_text", "version", "effective_date", "requires_acceptance"]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{field} = :{field}")
                params[field] = val

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")
        # If published doc is edited, unpublish (requires re-publish to go live)
        if existing[1]:
            updates.append("is_published = false")

        sql = (
            "UPDATE tenant_legal_documents SET " + ", ".join(updates)
            + " WHERE id = :id AND organization_id = :org_id"
        )
        db.execute(text(sql), params)
        db.commit()

        return {"id": doc_id, "message": "Legal document updated"}

    # ==================================================================
    # Publish legal document
    # ==================================================================
    @app.post("/api/v1/admin/legal-documents/{doc_id}/publish", tags=["Legal Documents"])
    async def publish_legal_document(
        doc_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Publish a legal document, making it the active version for borrowers (WL-007)."""
        _require_admin(current_user)
        org_id = getattr(current_user, 'organization_id', None)

        row = db.execute(text(
            "SELECT id, document_type FROM tenant_legal_documents WHERE id = :id AND organization_id = :org_id"
        ), {"id": doc_id, "org_id": org_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Legal document not found")

        # Unpublish previous version of same type
        db.execute(text("""
            UPDATE tenant_legal_documents SET is_published = false
            WHERE organization_id = :org_id AND document_type = :dt AND id != :id
        """), {"org_id": org_id, "dt": row[1], "id": doc_id})

        # Publish this version
        db.execute(text("""
            UPDATE tenant_legal_documents
            SET is_published = true, published_at = NOW(), updated_at = NOW()
            WHERE id = :id
        """), {"id": doc_id})
        db.commit()

        return {"id": doc_id, "message": f"Published as active {row[1]}"}

    # ==================================================================
    # Public borrower-facing endpoint (no auth required)
    # ==================================================================
    @app.get("/api/v1/legal/{org_slug}/{doc_type}", tags=["Legal Documents (Public)"])
    async def get_public_legal_document(
        org_slug: str,
        doc_type: str,
        db: Session = Depends(get_db),
    ):
        """Get the published legal document for a given org (public, no auth). WL-007."""
        if doc_type not in VALID_DOC_TYPES:
            raise HTTPException(status_code=404, detail="Document type not found")

        row = db.execute(text("""
            SELECT d.title, d.content_html, d.content_text, d.version,
                   d.effective_date, o.name as org_name
            FROM tenant_legal_documents d
            JOIN organizations o ON o.id = d.organization_id
            WHERE o.slug = :slug AND d.document_type = :dt AND d.is_published = true
            LIMIT 1
        """), {"slug": org_slug, "dt": doc_type}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Document not found or not published")

        return {
            "title": row[0], "content_html": row[1], "content_text": row[2],
            "version": row[3], "effective_date": str(row[4]) if row[4] else None,
            "organization_name": row[5],
        }

    logger.info("  Legal document routes registered (WL-007)")
