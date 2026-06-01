"""POS document status endpoint.

Returns document requests and reference documents for the borrower's loan,
shaped for the POS DocumentsPage component.

Auth: PURL token (same as other POS routes).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from middleware.purl_auth import (
    PURLAuthContext,
    check_purl_rate_limit,
    require_purl_token,
)

from models.smart_docs_models import (
    DocType,
    DocumentRequest,
    RequestStatus,
    SmartDocument,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/pos",
    tags=["POS - Documents"],
    dependencies=[Depends(check_purl_rate_limit)],
)


# ---------------------------------------------------------------------------
# Category mapping
# ---------------------------------------------------------------------------

_INCOME_TYPES = {
    DocType.W2, DocType.PAYSTUB, DocType.TAX_RETURN,
    DocType.BUSINESS_TAX_RETURN, DocType.PROFIT_LOSS,
    DocType.BALANCE_SHEET,
}

_ASSET_TYPES = {
    DocType.BANK_STATEMENT, DocType.INVESTMENT_STATEMENT,
    DocType.GIFT_LETTER,
}

_IDENTITY_TYPES = {
    DocType.DRIVERS_LICENSE,
}

_PROPERTY_TYPES = {
    DocType.PURCHASE_CONTRACT, DocType.APPRAISAL,
    DocType.TITLE_REPORT, DocType.HOMEOWNERS_INSURANCE,
    DocType.LEASE_AGREEMENT,
}


def _doc_type_to_category(doc_type: Optional[DocType]) -> str:
    if doc_type is None:
        return "compliance"
    if doc_type in _INCOME_TYPES:
        return "income"
    if doc_type in _ASSET_TYPES:
        return "assets"
    if doc_type in _IDENTITY_TYPES:
        return "identity"
    if doc_type in _PROPERTY_TYPES:
        return "property"
    return "compliance"


def _request_status_to_bucket(req_status: Optional[RequestStatus]) -> str:
    """Map a DocumentRequest status to the frontend bucket."""
    if req_status in (RequestStatus.OPEN, RequestStatus.REJECTED):
        return "action"
    if req_status == RequestStatus.PENDING_REVIEW:
        return "review"
    if req_status == RequestStatus.ACCEPTED:
        return "approved"
    # WAIVED or unknown -> approved (cleared)
    return "approved"


def _format_filesize(size_bytes: Optional[int]) -> Optional[str]:
    if size_bytes is None:
        return None
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes // 1024} KB"
    return f"{round(size_bytes / (1024 * 1024), 1)} MB"


def _due_severity(
    req: DocumentRequest,
) -> Optional[str]:
    """Return 'urgent' / 'normal' / None based on due_date proximity."""
    if not req.due_date:
        return None
    now = datetime.now(timezone.utc)
    due = req.due_date if req.due_date.tzinfo else req.due_date.replace(tzinfo=timezone.utc)
    delta = (due - now).days
    if delta <= 3:
        return "urgent"
    return "normal"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/documents",
    summary="Get document requests and reference docs for a loan",
)
def get_pos_documents(
    loan_id: int = Query(..., description="Loan ID to fetch documents for"),
    purl_ctx: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db),
):
    """Return the borrower's document requests and reference docs, shaped
    for the POS DocumentsPage component.

    The borrower must own the loan (verified via PURL workspace).
    """

    # -----------------------------------------------------------------------
    # Verify borrower owns this loan via the PURL workspace.
    # Match the requested loan_id directly within the token's workspace rather
    # than grabbing an arbitrary workspace loan with .first(): a workspace can
    # hold more than one PURLLoan, and the unordered .first() would 404 a loan
    # the borrower legitimately owns whenever it returned a different one.
    # Still tenant-safe — the workspace_id filter scopes to this token.
    # -----------------------------------------------------------------------
    from models.purl import PURLLoan
    from sqlalchemy import or_

    purl_loan = (
        db.query(PURLLoan)
        .filter(
            PURLLoan.workspace_id == purl_ctx.workspace_id,
            or_(
                PURLLoan.main_loan_id == loan_id,
                PURLLoan.id == loan_id,
            ),
        )
        .first()
    )

    if purl_loan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Loan not found",
        )

    # -----------------------------------------------------------------------
    # 1. Fetch active document requests
    # -----------------------------------------------------------------------
    # NOTE: DocumentRequest has no organization_id column. Tenant isolation
    # is enforced by the PURLLoan workspace check above — only the
    # borrower's own loan_id can reach this point. SmartDocument does have
    # organization_id, and we filter on it in sections 2 and 5 below.
    requests = (
        db.query(DocumentRequest)
        .filter(
            DocumentRequest.loan_id == loan_id,
            DocumentRequest.is_active == True,
        )
        .order_by(
            DocumentRequest.priority.asc(),
            DocumentRequest.created_at.asc(),
        )
        .all()
    )

    # -----------------------------------------------------------------------
    # 2. Batch-fetch uploaded documents (avoids N+1)
    # -----------------------------------------------------------------------
    request_ids = [req.id for req in requests]
    docs_by_request: Dict[int, List[SmartDocument]] = {}

    if request_ids:
        all_docs = (
            db.query(SmartDocument)
            .filter(
                SmartDocument.request_id.in_(request_ids),
                SmartDocument.organization_id == purl_ctx.organization_id,
                SmartDocument.status.notin_(["DELETED", "SUPERSEDED"]),
            )
            .order_by(SmartDocument.uploaded_at.desc())
            .all()
        )
        for doc in all_docs:
            docs_by_request.setdefault(doc.request_id, []).append(doc)

    # -----------------------------------------------------------------------
    # 3. Batch-fetch extractions for those documents
    # -----------------------------------------------------------------------
    all_doc_ids = []
    for doc_list in docs_by_request.values():
        all_doc_ids.extend(d.id for d in doc_list)

    extractions_by_doc: Dict[int, dict] = {}
    if all_doc_ids:
        try:
            from models.document_extraction import SmartDocumentExtraction

            extraction_rows = (
                db.query(SmartDocumentExtraction)
                .filter(SmartDocumentExtraction.document_id.in_(all_doc_ids))
                .all()
            )
            for ext in extraction_rows:
                if ext.extracted_fields:
                    extractions_by_doc[ext.document_id] = ext.extracted_fields
        except Exception as e:
            logger.warning("Could not fetch extractions: %s", e)

    # -----------------------------------------------------------------------
    # 4. Build document items from requests
    # -----------------------------------------------------------------------
    documents: List[dict] = []
    counts: Dict[str, int] = {"action": 0, "review": 0, "approved": 0, "reference": 0}

    for req in requests:
        bucket = _request_status_to_bucket(req.status)
        counts[bucket] = counts.get(bucket, 0) + 1

        uploaded_docs = docs_by_request.get(req.id, [])
        latest_doc = uploaded_docs[0] if uploaded_docs else None

        # Build extraction array from latest doc
        extraction = None
        if latest_doc and latest_doc.id in extractions_by_doc:
            fields = extractions_by_doc[latest_doc.id]
            extraction = [
                {"label": k.replace("_", " ").title(), "value": str(v)}
                for k, v in fields.items()
                if v is not None
            ]

        # Rejection info
        rejection_reason = None
        fix_instructions = None
        if req.status == RequestStatus.REJECTED and uploaded_docs:
            for d in uploaded_docs:
                if d.rejection_reason:
                    rejection_reason = d.rejection_reason
                    fix_instructions = d.fix_instructions
                    break

        item: dict = {
            "id": f"req-{req.id}",
            "name": req.title,
            "status": bucket,
            "category": _doc_type_to_category(req.doc_type),
            "description": req.description or req.instructions,
            "filename": latest_doc.display_name or latest_doc.file_name if latest_doc else None,
            "filesize": _format_filesize(latest_doc.file_size) if latest_doc else None,
            "uploadedAt": (
                latest_doc.uploaded_at.isoformat()
                if latest_doc and latest_doc.uploaded_at
                else None
            ),
            "dueDate": req.due_date.strftime("%Y-%m-%d") if req.due_date else None,
            "dueSeverity": _due_severity(req),
            "extraction": extraction,
            "reviewedBy": (
                f"Reviewed by {latest_doc.reviewed_by}"
                if latest_doc and latest_doc.reviewed_by
                else None
            ),
            "clearedAt": (
                req.completed_at.isoformat() if req.completed_at else None
            ),
            "meta": None,
            "rejectionReason": rejection_reason,
            "fixInstructions": fix_instructions,
        }
        documents.append(item)

    # -----------------------------------------------------------------------
    # 5. Reference documents: SmartDocuments with no request_id on this loan
    #    (generated docs like Loan Estimate, pre-approval letter)
    # -----------------------------------------------------------------------
    try:
        ref_docs = (
            db.query(SmartDocument)
            .filter(
                SmartDocument.loan_id == loan_id,
                SmartDocument.organization_id == purl_ctx.organization_id,
                SmartDocument.request_id == None,  # noqa: E711
                SmartDocument.status.notin_(["DELETED", "SUPERSEDED"]),
            )
            .order_by(SmartDocument.uploaded_at.desc())
            .all()
        )
        for doc in ref_docs:
            counts["reference"] = counts.get("reference", 0) + 1
            page_info = f"{doc.page_count} pages" if doc.page_count else None
            size_info = _format_filesize(doc.file_size)
            meta_parts = [p for p in [doc.mime_type.split("/")[-1].upper() if doc.mime_type else None, page_info, size_info] if p]
            documents.append({
                "id": f"ref-{doc.id}",
                "name": doc.display_name or doc.file_name,
                "status": "reference",
                "category": _doc_type_to_category(doc.doc_type),
                "description": None,
                "filename": doc.file_name,
                "filesize": size_info,
                "uploadedAt": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                "dueDate": None,
                "dueSeverity": None,
                "extraction": None,
                "reviewedBy": None,
                "clearedAt": None,
                "meta": " · ".join(meta_parts) if meta_parts else None,
                "rejectionReason": None,
                "fixInstructions": None,
            })
    except Exception as e:
        logger.warning("Could not fetch reference docs: %s", e)

    return {
        "documents": documents,
        "counts": counts,
    }
