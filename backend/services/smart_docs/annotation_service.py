"""
Document Annotation Service (Smart Docs V2)

Async service for managing spatial annotations on Smart Document pages.
All operations enforce organization-scoped tenant isolation.

Capabilities:
    1. CRUD for annotations (highlight, note, flag, stamp, redaction, condition tag)
    2. Collaborative multi-user annotation on the same document
    3. Resolution workflow: flag -> review -> resolve
    4. Flattened-PDF export with annotations burned in
    5. Cross-document annotation search (e.g. all flags on a loan)
    6. Pre-defined annotation templates (stamps, common notes)
    7. Real-time annotation list for frontend rendering / sync
    8. Bulk operations (resolve all, delete all by type)
    9. Per-document and per-org annotation statistics

Usage:
    from services.smart_docs.annotation_service import AnnotationService

    svc = AnnotationService(db)
    ann = await svc.add_annotation(org_id=1, document_id=42, ...)
    page_annotations = await svc.get_annotations_for_document(org_id=1, document_id=42)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, and_, case
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy model import (avoids circular dependency at module load time)
# ---------------------------------------------------------------------------

def _get_models():
    from database.models.document_annotation import (
        DocumentAnnotation,
        AnnotationType,
        AnnotationStatus,
    )
    return DocumentAnnotation, AnnotationType, AnnotationStatus


# ---------------------------------------------------------------------------
# Pre-defined templates
# ---------------------------------------------------------------------------

STAMP_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "approved": {
        "content": "APPROVED",
        "color": "#4CAF50",
        "annotation_type": "STAMP",
    },
    "reviewed": {
        "content": "REVIEWED",
        "color": "#2196F3",
        "annotation_type": "STAMP",
    },
    "rejected": {
        "content": "REJECTED",
        "color": "#F44336",
        "annotation_type": "STAMP",
    },
    "needs_revision": {
        "content": "NEEDS REVISION",
        "color": "#FF9800",
        "annotation_type": "STAMP",
    },
    "verified": {
        "content": "VERIFIED",
        "color": "#009688",
        "annotation_type": "STAMP",
    },
    "original_received": {
        "content": "ORIGINAL RECEIVED",
        "color": "#673AB7",
        "annotation_type": "STAMP",
    },
}

NOTE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "missing_page": {
        "content": "Missing page(s) -- please re-upload complete document.",
        "color": "#FF9800",
        "annotation_type": "NOTE",
    },
    "illegible": {
        "content": "This section is illegible. Please provide a clearer copy.",
        "color": "#F44336",
        "annotation_type": "NOTE",
    },
    "name_mismatch": {
        "content": "Name on document does not match borrower name on file.",
        "color": "#F44336",
        "annotation_type": "NOTE",
    },
    "date_expired": {
        "content": "Document date is outside the acceptable freshness window.",
        "color": "#FF9800",
        "annotation_type": "NOTE",
    },
    "amount_discrepancy": {
        "content": "Amount on this document does not match cross-referenced data.",
        "color": "#FF9800",
        "annotation_type": "NOTE",
    },
    "pii_detected": {
        "content": "PII detected -- verify redaction before sharing externally.",
        "color": "#9C27B0",
        "annotation_type": "NOTE",
    },
}

ALL_TEMPLATES: Dict[str, Dict[str, Any]] = {**STAMP_TEMPLATES, **NOTE_TEMPLATES}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_VALID_HEX_COLOR_LEN = 7  # e.g. "#ABCDEF"


def _validate_annotation_type(annotation_type: str) -> None:
    _, AnnotationType, _ = _get_models()
    if annotation_type not in AnnotationType.ALL:
        raise ValueError(
            f"Invalid annotation_type '{annotation_type}'. "
            f"Must be one of: {', '.join(sorted(AnnotationType.ALL))}"
        )


def _validate_status(status: str) -> None:
    _, _, AnnotationStatus = _get_models()
    if status not in AnnotationStatus.ALL:
        raise ValueError(
            f"Invalid status '{status}'. "
            f"Must be one of: {', '.join(sorted(AnnotationStatus.ALL))}"
        )


def _validate_color(color: Optional[str]) -> None:
    if color is None:
        return
    if (
        len(color) != _VALID_HEX_COLOR_LEN
        or color[0] != "#"
        or not all(c in "0123456789abcdefABCDEF" for c in color[1:])
    ):
        raise ValueError(
            f"Invalid color '{color}'. Must be a 7-char hex string (e.g. '#FF0000')."
        )


def _validate_position_data(position_data: Optional[Dict]) -> None:
    if position_data is None:
        return
    required_keys = {"x", "y", "width", "height"}
    missing = required_keys - set(position_data.keys())
    if missing:
        raise ValueError(f"position_data missing required keys: {missing}")
    for key in required_keys:
        val = position_data[key]
        if not isinstance(val, (int, float)):
            raise ValueError(f"position_data['{key}'] must be numeric, got {type(val).__name__}")


def _annotation_to_dict(ann) -> Dict[str, Any]:
    """Serialize a DocumentAnnotation row to a plain dict for API responses."""
    return {
        "id": ann.id,
        "organization_id": ann.organization_id,
        "document_id": ann.document_id,
        "page_number": ann.page_number,
        "annotation_type": ann.annotation_type,
        "content": ann.content,
        "position_data": ann.position_data,
        "color": ann.color,
        "status": ann.status,
        "related_condition_id": ann.related_condition_id,
        "created_by_user_id": ann.created_by_user_id,
        "resolved_by_user_id": ann.resolved_by_user_id,
        "resolved_at": ann.resolved_at.isoformat() if ann.resolved_at else None,
        "created_at": ann.created_at.isoformat() if ann.created_at else None,
        "updated_at": ann.updated_at.isoformat() if ann.updated_at else None,
    }


# ===========================================================================
# SERVICE
# ===========================================================================

class AnnotationService:
    """
    Async-style annotation service.

    All public methods accept a ``db: Session`` (from ``Depends(get_db)``),
    an ``org_id: int``, and are implemented as regular methods rather than
    coroutines because the underlying DB driver is synchronous (psycopg2).
    Route handlers can call these from ``async def`` endpoints via
    ``run_in_executor`` if strict async is needed; keeping the service sync
    avoids the overhead of wrapping every SA call.
    """

    # ------------------------------------------------------------------
    # 1. Add annotation
    # ------------------------------------------------------------------

    def add_annotation(
        self,
        db: Session,
        *,
        org_id: int,
        document_id: int,
        page_number: int,
        annotation_type: str,
        created_by_user_id: int,
        content: Optional[str] = None,
        position_data: Optional[Dict[str, Any]] = None,
        color: Optional[str] = None,
        related_condition_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a single annotation on a document page.

        Returns:
            Serialized annotation dict.

        Raises:
            ValueError: on invalid type, color, or position data.
        """
        DocumentAnnotation, AnnotationType, AnnotationStatus = _get_models()

        _validate_annotation_type(annotation_type)
        _validate_color(color)
        _validate_position_data(position_data)

        if page_number < 1:
            raise ValueError("page_number must be >= 1")

        # Default colors per type when caller omits
        if color is None:
            color = {
                AnnotationType.HIGHLIGHT: "#FFEB3B",
                AnnotationType.NOTE: "#FFF9C4",
                AnnotationType.FLAG: "#F44336",
                AnnotationType.STAMP: "#4CAF50",
                AnnotationType.REDACTION: "#000000",
                AnnotationType.CONDITION_TAG: "#FF9800",
            }.get(annotation_type)

        annotation = DocumentAnnotation(
            organization_id=org_id,
            document_id=document_id,
            page_number=page_number,
            annotation_type=annotation_type,
            content=content,
            position_data=position_data,
            color=color,
            status=AnnotationStatus.ACTIVE,
            related_condition_id=related_condition_id,
            created_by_user_id=created_by_user_id,
        )
        db.add(annotation)
        db.flush()  # Populate id and defaults

        logger.info(
            "Annotation %s created on doc %s page %s by user %s (org %s)",
            annotation.id, document_id, page_number,
            created_by_user_id, org_id,
        )
        return _annotation_to_dict(annotation)

    # ------------------------------------------------------------------
    # 2. Add annotation from template
    # ------------------------------------------------------------------

    def add_from_template(
        self,
        db: Session,
        *,
        org_id: int,
        document_id: int,
        page_number: int,
        template_key: str,
        created_by_user_id: int,
        position_data: Optional[Dict[str, Any]] = None,
        content_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an annotation using a pre-defined template.

        Args:
            template_key: Key from STAMP_TEMPLATES or NOTE_TEMPLATES.
            content_override: Replace the template's default content text.

        Raises:
            ValueError: if template_key is unknown.
        """
        template = ALL_TEMPLATES.get(template_key)
        if template is None:
            raise ValueError(
                f"Unknown template '{template_key}'. "
                f"Available: {', '.join(sorted(ALL_TEMPLATES))}"
            )

        return self.add_annotation(
            db,
            org_id=org_id,
            document_id=document_id,
            page_number=page_number,
            annotation_type=template["annotation_type"],
            content=content_override or template["content"],
            color=template["color"],
            position_data=position_data,
            created_by_user_id=created_by_user_id,
        )

    # ------------------------------------------------------------------
    # 3. Get annotations for a document (real-time sync payload)
    # ------------------------------------------------------------------

    def get_annotations_for_document(
        self,
        db: Session,
        *,
        org_id: int,
        document_id: int,
        page_number: Optional[int] = None,
        status: Optional[str] = None,
        annotation_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return all annotations for a document, optionally filtered.

        The result is ordered by page_number ASC, then created_at ASC so the
        frontend can render them in reading order.
        """
        DocumentAnnotation, _, _ = _get_models()

        filters = [
            DocumentAnnotation.organization_id == org_id,
            DocumentAnnotation.document_id == document_id,
        ]

        if page_number is not None:
            filters.append(DocumentAnnotation.page_number == page_number)
        if status is not None:
            _validate_status(status)
            filters.append(DocumentAnnotation.status == status)
        if annotation_type is not None:
            _validate_annotation_type(annotation_type)
            filters.append(DocumentAnnotation.annotation_type == annotation_type)

        rows = (
            db.query(DocumentAnnotation)
            .filter(and_(*filters))
            .order_by(DocumentAnnotation.page_number.asc(), DocumentAnnotation.created_at.asc())
            .all()
        )

        return [_annotation_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 4. Update annotation
    # ------------------------------------------------------------------

    def update_annotation(
        self,
        db: Session,
        *,
        org_id: int,
        annotation_id: int,
        user_id: int,
        content: Optional[str] = ...,
        position_data: Optional[Dict[str, Any]] = ...,
        color: Optional[str] = ...,
    ) -> Dict[str, Any]:
        """Update mutable fields of an existing annotation.

        Sentinel ``...`` (Ellipsis) means "do not change". ``None`` explicitly
        clears the field.

        Raises:
            LookupError: if annotation not found within the org.
        """
        DocumentAnnotation, _, _ = _get_models()

        annotation = (
            db.query(DocumentAnnotation)
            .filter(
                DocumentAnnotation.id == annotation_id,
                DocumentAnnotation.organization_id == org_id,
            )
            .first()
        )
        if annotation is None:
            raise LookupError(
                f"Annotation {annotation_id} not found in org {org_id}"
            )

        if content is not ...:
            annotation.content = content
        if position_data is not ...:
            if position_data is not None:
                _validate_position_data(position_data)
            annotation.position_data = position_data
        if color is not ...:
            if color is not None:
                _validate_color(color)
            annotation.color = color

        db.flush()
        logger.info(
            "Annotation %s updated by user %s (org %s)",
            annotation_id, user_id, org_id,
        )
        return _annotation_to_dict(annotation)

    # ------------------------------------------------------------------
    # 5. Resolution workflow
    # ------------------------------------------------------------------

    def resolve_annotation(
        self,
        db: Session,
        *,
        org_id: int,
        annotation_id: int,
        resolved_by_user_id: int,
        resolution_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Mark an annotation as resolved (flag -> review -> resolve).

        Optionally appends a resolution note to the content field.

        Raises:
            LookupError: if annotation not found.
            ValueError: if annotation is not in active status.
        """
        DocumentAnnotation, _, AnnotationStatus = _get_models()

        annotation = (
            db.query(DocumentAnnotation)
            .filter(
                DocumentAnnotation.id == annotation_id,
                DocumentAnnotation.organization_id == org_id,
            )
            .first()
        )
        if annotation is None:
            raise LookupError(
                f"Annotation {annotation_id} not found in org {org_id}"
            )
        if annotation.status != AnnotationStatus.ACTIVE:
            raise ValueError(
                f"Cannot resolve annotation {annotation_id}: "
                f"current status is '{annotation.status}', expected 'active'"
            )

        now = datetime.now(timezone.utc)
        annotation.status = AnnotationStatus.RESOLVED
        annotation.resolved_by_user_id = resolved_by_user_id
        annotation.resolved_at = now

        if resolution_note:
            existing = annotation.content or ""
            separator = "\n---\n" if existing else ""
            annotation.content = f"{existing}{separator}[Resolved] {resolution_note}"

        db.flush()
        logger.info(
            "Annotation %s resolved by user %s (org %s)",
            annotation_id, resolved_by_user_id, org_id,
        )
        return _annotation_to_dict(annotation)

    # ------------------------------------------------------------------
    # 6. Soft delete
    # ------------------------------------------------------------------

    def delete_annotation(
        self,
        db: Session,
        *,
        org_id: int,
        annotation_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """Soft-delete an annotation (sets status to 'deleted').

        Raises:
            LookupError: if annotation not found.
        """
        DocumentAnnotation, _, AnnotationStatus = _get_models()

        annotation = (
            db.query(DocumentAnnotation)
            .filter(
                DocumentAnnotation.id == annotation_id,
                DocumentAnnotation.organization_id == org_id,
            )
            .first()
        )
        if annotation is None:
            raise LookupError(
                f"Annotation {annotation_id} not found in org {org_id}"
            )

        annotation.status = AnnotationStatus.DELETED
        db.flush()
        logger.info(
            "Annotation %s soft-deleted by user %s (org %s)",
            annotation_id, user_id, org_id,
        )
        return _annotation_to_dict(annotation)

    # ------------------------------------------------------------------
    # 7. Cross-document search
    # ------------------------------------------------------------------

    def search_annotations(
        self,
        db: Session,
        *,
        org_id: int,
        document_ids: Optional[List[int]] = None,
        annotation_type: Optional[str] = None,
        status: Optional[str] = None,
        created_by_user_id: Optional[int] = None,
        related_condition_id: Optional[int] = None,
        content_search: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Search annotations across multiple documents within an org.

        Returns:
            Dict with ``annotations`` list and ``total`` count.
        """
        DocumentAnnotation, _, _ = _get_models()

        if annotation_type is not None:
            _validate_annotation_type(annotation_type)
        if status is not None:
            _validate_status(status)

        filters = [DocumentAnnotation.organization_id == org_id]

        if document_ids:
            filters.append(DocumentAnnotation.document_id.in_(document_ids))
        if annotation_type:
            filters.append(DocumentAnnotation.annotation_type == annotation_type)
        if status:
            filters.append(DocumentAnnotation.status == status)
        if created_by_user_id is not None:
            filters.append(DocumentAnnotation.created_by_user_id == created_by_user_id)
        if related_condition_id is not None:
            filters.append(DocumentAnnotation.related_condition_id == related_condition_id)
        if content_search:
            filters.append(DocumentAnnotation.content.ilike(f"%{content_search}%"))

        base_q = db.query(DocumentAnnotation).filter(and_(*filters))

        total = base_q.count()
        rows = (
            base_q
            .order_by(DocumentAnnotation.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "annotations": [_annotation_to_dict(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    # ------------------------------------------------------------------
    # 8. Bulk resolve
    # ------------------------------------------------------------------

    def bulk_resolve(
        self,
        db: Session,
        *,
        org_id: int,
        document_id: int,
        resolved_by_user_id: int,
        annotation_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve all active annotations on a document, optionally filtered by type.

        Returns:
            Dict with ``resolved_count``.
        """
        DocumentAnnotation, _, AnnotationStatus = _get_models()

        if annotation_type is not None:
            _validate_annotation_type(annotation_type)

        now = datetime.now(timezone.utc)
        filters = [
            DocumentAnnotation.organization_id == org_id,
            DocumentAnnotation.document_id == document_id,
            DocumentAnnotation.status == AnnotationStatus.ACTIVE,
        ]
        if annotation_type:
            filters.append(DocumentAnnotation.annotation_type == annotation_type)

        count = (
            db.query(DocumentAnnotation)
            .filter(and_(*filters))
            .update(
                {
                    DocumentAnnotation.status: AnnotationStatus.RESOLVED,
                    DocumentAnnotation.resolved_by_user_id: resolved_by_user_id,
                    DocumentAnnotation.resolved_at: now,
                },
                synchronize_session="fetch",
            )
        )

        db.flush()
        logger.info(
            "Bulk-resolved %d annotations on doc %s by user %s (org %s, type=%s)",
            count, document_id, resolved_by_user_id, org_id, annotation_type,
        )
        return {"resolved_count": count, "document_id": document_id}

    # ------------------------------------------------------------------
    # 9. Bulk delete by type
    # ------------------------------------------------------------------

    def bulk_delete_by_type(
        self,
        db: Session,
        *,
        org_id: int,
        document_id: int,
        annotation_type: str,
        user_id: int,
    ) -> Dict[str, Any]:
        """Soft-delete all annotations of a given type on a document.

        Returns:
            Dict with ``deleted_count``.
        """
        DocumentAnnotation, _, AnnotationStatus = _get_models()
        _validate_annotation_type(annotation_type)

        count = (
            db.query(DocumentAnnotation)
            .filter(
                DocumentAnnotation.organization_id == org_id,
                DocumentAnnotation.document_id == document_id,
                DocumentAnnotation.annotation_type == annotation_type,
                DocumentAnnotation.status != AnnotationStatus.DELETED,
            )
            .update(
                {DocumentAnnotation.status: AnnotationStatus.DELETED},
                synchronize_session="fetch",
            )
        )

        db.flush()
        logger.info(
            "Bulk-deleted %d %s annotations on doc %s by user %s (org %s)",
            count, annotation_type, document_id, user_id, org_id,
        )
        return {"deleted_count": count, "annotation_type": annotation_type}

    # ------------------------------------------------------------------
    # 10. Annotation statistics
    # ------------------------------------------------------------------

    def get_document_stats(
        self,
        db: Session,
        *,
        org_id: int,
        document_id: int,
    ) -> Dict[str, Any]:
        """Per-document annotation statistics.

        Returns counts by type, by status, unique annotators, and average
        resolution time for resolved annotations.
        """
        DocumentAnnotation, _, AnnotationStatus = _get_models()

        base_filter = and_(
            DocumentAnnotation.organization_id == org_id,
            DocumentAnnotation.document_id == document_id,
            DocumentAnnotation.status != AnnotationStatus.DELETED,
        )

        # Counts by type
        by_type_rows = (
            db.query(
                DocumentAnnotation.annotation_type,
                func.count(DocumentAnnotation.id),
            )
            .filter(base_filter)
            .group_by(DocumentAnnotation.annotation_type)
            .all()
        )
        by_type = {row[0]: row[1] for row in by_type_rows}

        # Counts by status
        by_status_rows = (
            db.query(
                DocumentAnnotation.status,
                func.count(DocumentAnnotation.id),
            )
            .filter(
                DocumentAnnotation.organization_id == org_id,
                DocumentAnnotation.document_id == document_id,
            )
            .group_by(DocumentAnnotation.status)
            .all()
        )
        by_status = {row[0]: row[1] for row in by_status_rows}

        # Unique annotators
        annotator_count = (
            db.query(func.count(func.distinct(DocumentAnnotation.created_by_user_id)))
            .filter(base_filter)
            .scalar()
        ) or 0

        # Average resolution time (seconds) for resolved annotations
        avg_resolution = (
            db.query(
                func.avg(
                    func.extract("epoch", DocumentAnnotation.resolved_at)
                    - func.extract("epoch", DocumentAnnotation.created_at)
                )
            )
            .filter(
                DocumentAnnotation.organization_id == org_id,
                DocumentAnnotation.document_id == document_id,
                DocumentAnnotation.status == AnnotationStatus.RESOLVED,
                DocumentAnnotation.resolved_at.isnot(None),
            )
            .scalar()
        )

        # Convert seconds to hours for readability
        avg_resolution_hours = round(float(avg_resolution) / 3600, 2) if avg_resolution else None

        # Page coverage: distinct pages with annotations
        annotated_pages = (
            db.query(func.count(func.distinct(DocumentAnnotation.page_number)))
            .filter(base_filter)
            .scalar()
        ) or 0

        total_active = by_status.get(AnnotationStatus.ACTIVE, 0)
        total_resolved = by_status.get(AnnotationStatus.RESOLVED, 0)

        return {
            "document_id": document_id,
            "total_active": total_active,
            "total_resolved": total_resolved,
            "total_deleted": by_status.get(AnnotationStatus.DELETED, 0),
            "by_type": by_type,
            "by_status": by_status,
            "unique_annotators": annotator_count,
            "annotated_pages": annotated_pages,
            "avg_resolution_hours": avg_resolution_hours,
            "unresolved_flags": (
                db.query(func.count(DocumentAnnotation.id))
                .filter(
                    base_filter,
                    DocumentAnnotation.annotation_type == "FLAG",
                )
                .scalar()
            ) or 0,
        }

    def get_org_stats(
        self,
        db: Session,
        *,
        org_id: int,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Organization-wide annotation statistics over a rolling window.

        Useful for dashboards and team performance tracking.
        """
        DocumentAnnotation, _, AnnotationStatus = _get_models()

        cutoff = datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days)

        recent_filter = and_(
            DocumentAnnotation.organization_id == org_id,
            DocumentAnnotation.created_at >= cutoff,
        )

        total_created = (
            db.query(func.count(DocumentAnnotation.id))
            .filter(recent_filter)
            .scalar()
        ) or 0

        total_resolved = (
            db.query(func.count(DocumentAnnotation.id))
            .filter(
                DocumentAnnotation.organization_id == org_id,
                DocumentAnnotation.status == AnnotationStatus.RESOLVED,
                DocumentAnnotation.resolved_at >= cutoff,
            )
            .scalar()
        ) or 0

        # By type breakdown
        by_type_rows = (
            db.query(
                DocumentAnnotation.annotation_type,
                func.count(DocumentAnnotation.id),
            )
            .filter(recent_filter)
            .group_by(DocumentAnnotation.annotation_type)
            .all()
        )

        # Top annotators
        top_annotators = (
            db.query(
                DocumentAnnotation.created_by_user_id,
                func.count(DocumentAnnotation.id).label("count"),
            )
            .filter(recent_filter)
            .group_by(DocumentAnnotation.created_by_user_id)
            .order_by(func.count(DocumentAnnotation.id).desc())
            .limit(10)
            .all()
        )

        # Documents with most unresolved flags
        flagged_docs = (
            db.query(
                DocumentAnnotation.document_id,
                func.count(DocumentAnnotation.id).label("flag_count"),
            )
            .filter(
                DocumentAnnotation.organization_id == org_id,
                DocumentAnnotation.annotation_type == "FLAG",
                DocumentAnnotation.status == AnnotationStatus.ACTIVE,
            )
            .group_by(DocumentAnnotation.document_id)
            .order_by(func.count(DocumentAnnotation.id).desc())
            .limit(10)
            .all()
        )

        return {
            "period_days": days,
            "total_created": total_created,
            "total_resolved": total_resolved,
            "resolution_rate": (
                round((total_resolved / total_created) * 100, 1)
                if total_created > 0 else 0.0
            ),
            "by_type": {row[0]: row[1] for row in by_type_rows},
            "top_annotators": [
                {"user_id": row[0], "count": row[1]}
                for row in top_annotators
            ],
            "flagged_documents": [
                {"document_id": row[0], "flag_count": row[1]}
                for row in flagged_docs
            ],
        }

    # ------------------------------------------------------------------
    # 11. Export annotation overlay data (for PDF flattening)
    # ------------------------------------------------------------------

    def get_export_overlay(
        self,
        db: Session,
        *,
        org_id: int,
        document_id: int,
        include_resolved: bool = False,
        include_redactions: bool = True,
    ) -> Dict[str, Any]:
        """Build a page-keyed overlay payload for the PDF flattening pipeline.

        Each page entry contains a list of annotations with their position,
        type, content, and color -- everything the PDF renderer needs to burn
        annotations into the document.

        The ``pdf_generation_service`` can consume this output to produce a
        flattened PDF with annotations rendered as vector graphics.

        Returns:
            Dict with ``document_id``, ``pages`` (page_number -> annotations),
            and ``annotation_count``.
        """
        DocumentAnnotation, _, AnnotationStatus = _get_models()

        statuses = [AnnotationStatus.ACTIVE]
        if include_resolved:
            statuses.append(AnnotationStatus.RESOLVED)

        filters = [
            DocumentAnnotation.organization_id == org_id,
            DocumentAnnotation.document_id == document_id,
            DocumentAnnotation.status.in_(statuses),
        ]

        if not include_redactions:
            filters.append(DocumentAnnotation.annotation_type != "REDACTION")

        rows = (
            db.query(DocumentAnnotation)
            .filter(and_(*filters))
            .order_by(DocumentAnnotation.page_number.asc(), DocumentAnnotation.created_at.asc())
            .all()
        )

        pages: Dict[int, List[Dict[str, Any]]] = {}
        for ann in rows:
            entry = {
                "id": ann.id,
                "annotation_type": ann.annotation_type,
                "content": ann.content,
                "position_data": ann.position_data,
                "color": ann.color,
                "status": ann.status,
            }
            pages.setdefault(ann.page_number, []).append(entry)

        return {
            "document_id": document_id,
            "pages": pages,
            "annotation_count": len(rows),
        }

    # ------------------------------------------------------------------
    # 12. List available templates
    # ------------------------------------------------------------------

    @staticmethod
    def list_templates() -> Dict[str, Any]:
        """Return all available annotation templates.

        Useful for populating a template picker in the frontend.
        """
        return {
            "stamps": {
                k: {**v, "template_key": k}
                for k, v in STAMP_TEMPLATES.items()
            },
            "notes": {
                k: {**v, "template_key": k}
                for k, v in NOTE_TEMPLATES.items()
            },
        }

    # ------------------------------------------------------------------
    # 13. Link annotation to condition
    # ------------------------------------------------------------------

    def link_to_condition(
        self,
        db: Session,
        *,
        org_id: int,
        annotation_id: int,
        condition_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """Link an existing annotation to an underwriting condition.

        This converts the annotation type to CONDITION_TAG if it is not
        already, and sets the related_condition_id.

        Raises:
            LookupError: if annotation not found.
        """
        DocumentAnnotation, AnnotationType, _ = _get_models()

        annotation = (
            db.query(DocumentAnnotation)
            .filter(
                DocumentAnnotation.id == annotation_id,
                DocumentAnnotation.organization_id == org_id,
            )
            .first()
        )
        if annotation is None:
            raise LookupError(
                f"Annotation {annotation_id} not found in org {org_id}"
            )

        annotation.related_condition_id = condition_id
        if annotation.annotation_type != AnnotationType.CONDITION_TAG:
            annotation.annotation_type = AnnotationType.CONDITION_TAG
            annotation.color = "#FF9800"  # condition tag default

        db.flush()
        logger.info(
            "Annotation %s linked to condition %s by user %s (org %s)",
            annotation_id, condition_id, user_id, org_id,
        )
        return _annotation_to_dict(annotation)

    # ------------------------------------------------------------------
    # 14. Get annotations by condition
    # ------------------------------------------------------------------

    def get_annotations_by_condition(
        self,
        db: Session,
        *,
        org_id: int,
        condition_id: int,
    ) -> List[Dict[str, Any]]:
        """Find all annotations linked to a specific underwriting condition.

        Useful for reviewing all document evidence related to a condition.
        """
        DocumentAnnotation, _, AnnotationStatus = _get_models()

        rows = (
            db.query(DocumentAnnotation)
            .filter(
                DocumentAnnotation.organization_id == org_id,
                DocumentAnnotation.related_condition_id == condition_id,
                DocumentAnnotation.status != AnnotationStatus.DELETED,
            )
            .order_by(DocumentAnnotation.created_at.asc())
            .all()
        )

        return [_annotation_to_dict(r) for r in rows]


# ===========================================================================
# MODULE-LEVEL SINGLETON
# ===========================================================================

_service_instance: Optional[AnnotationService] = None


def get_annotation_service() -> AnnotationService:
    """Get or create the module-level AnnotationService singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = AnnotationService()
    return _service_instance
