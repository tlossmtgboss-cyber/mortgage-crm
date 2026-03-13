"""
Document Version Control Service for Smart Docs V2

Provides version management for mortgage documents with full audit trail,
rollback capability, and regulatory compliance. Every document mutation
(replacement, correction, addendum) creates a new version with a frozen
snapshot of the extracted data at that point in time.

Key capabilities:
  1. Create new version on document replacement (auto-increment version_number)
  2. Maintain version history with full audit trail
  3. Rollback to any previous version
  4. Compare any two versions (diff)
  5. Track who changed what and why
  6. Snapshot extracted data at each version for historical accuracy
  7. Storage management (archive old versions after configurable period)
  8. Prevent version creation without change_reason for regulated documents
  9. Get full version timeline for a document
 10. Bulk version operations for document sets

All public methods enforce organization_id tenant isolation.

Usage:
    from services.smart_docs.document_version_service import (
        DocumentVersionService,
        get_document_version_service,
    )

    svc = get_document_version_service()

    # Create initial version
    version = await svc.create_initial_version(
        db=db,
        organization_id=org_id,
        document_id=doc_id,
        file_hash="abc123...",
        file_location="s3://bucket/key",
        file_size=102400,
        extracted_data={"borrower_name": "Jane Doe"},
        changed_by_user_id=user_id,
        original_filename="paystub_jan.pdf",
        mime_type="application/pdf",
    )

    # Replace document
    new_version = await svc.create_new_version(
        db=db,
        organization_id=org_id,
        document_id=doc_id,
        file_hash="def456...",
        file_location="s3://bucket/new_key",
        file_size=115000,
        change_type="REPLACEMENT",
        change_reason="Borrower uploaded clearer scan",
        extracted_data={"borrower_name": "Jane Doe", "income": 85000},
        changed_by_user_id=user_id,
    )
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from exceptions import (
    DocumentNotFoundError,
    PerenniaError,
    TenantIsolationError,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Document types that require a change_reason on every version
REGULATED_DOC_TYPES = frozenset({
    "PAYSTUB", "W2", "TAX_RETURN", "BANK_STATEMENT",
    "APPRAISAL", "TITLE_REPORT", "PURCHASE_CONTRACT",
    "HOMEOWNERS_INSURANCE", "FHA_CERT", "VA_COE", "DD214",
    "PROFIT_LOSS", "BUSINESS_TAX_RETURN",
})

# Default archive threshold in days
DEFAULT_ARCHIVE_AFTER_DAYS = 365

# Maximum versions per document before warning
MAX_VERSIONS_WARNING_THRESHOLD = 50


# =============================================================================
# Exceptions
# =============================================================================

class VersionNotFoundError(PerenniaError):
    """Raised when a document version cannot be found."""

    def __init__(self, version_id: Any = None, message: Optional[str] = None):
        msg = message or f"Document version '{version_id}' not found"
        super().__init__(msg, code="VERSION_NOT_FOUND", details={"version_id": version_id})


class VersionConflictError(PerenniaError):
    """Raised when a version operation conflicts with current state."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="VERSION_CONFLICT", details=details or {})


class ChangeReasonRequiredError(PerenniaError):
    """Raised when a regulated document version is created without a reason."""

    def __init__(self, document_id: Any, doc_type: str):
        super().__init__(
            f"change_reason is required for regulated document type '{doc_type}' "
            f"(document_id={document_id})",
            code="CHANGE_REASON_REQUIRED",
            details={"document_id": document_id, "doc_type": doc_type},
        )


# =============================================================================
# Lazy model imports
# =============================================================================

def _get_version_model():
    """Lazy import to avoid circular dependency at module load time."""
    from database.models.document_version import DocumentVersion
    return DocumentVersion


def _get_smart_document_model():
    """Lazy import for SmartDocument model."""
    from models.smart_docs_models import SmartDocument
    return SmartDocument


# =============================================================================
# Service
# =============================================================================

class DocumentVersionService:
    """
    Manages document version lifecycle with tenant isolation and audit trail.

    All methods are async-compatible but use synchronous SQLAlchemy sessions
    (matching the project's established pattern). Callers in async routes
    should use ``await run_in_threadpool(svc.method, ...)`` or call directly
    since SQLAlchemy ORM operations are CPU-bound, not I/O-bound.
    """

    # ------------------------------------------------------------------
    # 1. Create initial version
    # ------------------------------------------------------------------

    def create_initial_version(
        self,
        db: Session,
        *,
        organization_id: int,
        document_id: int,
        file_hash: str,
        file_location: str,
        file_size: Optional[int] = None,
        extracted_data: Optional[Dict[str, Any]] = None,
        changed_by_user_id: Optional[int] = None,
        original_filename: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> "DocumentVersion":
        """Create version 1 for a newly uploaded document.

        Args:
            db: SQLAlchemy session.
            organization_id: Tenant ID (required for isolation).
            document_id: The smart_documents.id being versioned.
            file_hash: SHA-256 hex digest of the file contents.
            file_location: Storage path (S3 key or local path).
            file_size: File size in bytes.
            extracted_data: AI extraction results to snapshot.
            changed_by_user_id: User who uploaded the document.
            original_filename: Original filename from the upload.
            mime_type: MIME type of the file.

        Returns:
            The created DocumentVersion instance.

        Raises:
            VersionConflictError: If version 1 already exists for this document.
        """
        DocumentVersion = _get_version_model()

        # Check no versions exist yet
        existing = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.organization_id == organization_id,
            )
            .first()
        )
        if existing is not None:
            raise VersionConflictError(
                f"Document {document_id} already has version history. "
                "Use create_new_version() instead.",
                details={"document_id": document_id, "existing_version": existing.version_number},
            )

        version = DocumentVersion(
            organization_id=organization_id,
            document_id=document_id,
            version_number=1,
            file_hash=file_hash,
            file_location=file_location,
            file_size=file_size,
            change_type="INITIAL",
            change_reason="Initial document upload",
            changed_by_user_id=changed_by_user_id,
            previous_version_id=None,
            extracted_data_snapshot=extracted_data,
            is_current=True,
            original_filename=original_filename,
            mime_type=mime_type,
        )
        db.add(version)
        db.flush()  # Populate version.id for the caller

        logger.info(
            "Created initial version for document %d (org=%d, user=%s)",
            document_id, organization_id, changed_by_user_id,
        )
        return version

    # ------------------------------------------------------------------
    # 2. Create new version (replacement / correction / addendum)
    # ------------------------------------------------------------------

    def create_new_version(
        self,
        db: Session,
        *,
        organization_id: int,
        document_id: int,
        file_hash: str,
        file_location: str,
        change_type: str,
        change_reason: Optional[str] = None,
        file_size: Optional[int] = None,
        extracted_data: Optional[Dict[str, Any]] = None,
        changed_by_user_id: Optional[int] = None,
        original_filename: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> "DocumentVersion":
        """Create a new version for an existing document.

        Automatically:
          - Increments version_number from the current max.
          - Marks previous current version as not current.
          - Links previous_version_id.
          - Enforces change_reason for regulated document types.

        Args:
            db: SQLAlchemy session.
            organization_id: Tenant ID.
            document_id: The smart_documents.id being versioned.
            file_hash: SHA-256 hex digest of the new file.
            file_location: Storage path for the new file.
            change_type: One of REPLACEMENT, CORRECTION, ADDENDUM, REPROCESSED.
            change_reason: Why the document was changed (required for regulated types).
            file_size: New file size in bytes.
            extracted_data: AI extraction results for the new version.
            changed_by_user_id: User who initiated the change.
            original_filename: Filename of the new upload.
            mime_type: MIME type of the new file.

        Returns:
            The created DocumentVersion instance.

        Raises:
            ChangeReasonRequiredError: If a regulated doc type lacks change_reason.
            VersionNotFoundError: If no previous version exists (use create_initial_version).
            VersionConflictError: If the same file_hash already exists as the current version.
        """
        DocumentVersion = _get_version_model()

        # Enforce change_reason for regulated documents
        self._enforce_change_reason(db, document_id, organization_id, change_reason)

        # Get the current version
        current = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.is_current == True,  # noqa: E712
            )
            .first()
        )

        if current is None:
            raise VersionNotFoundError(
                message=f"No existing version found for document {document_id}. "
                "Use create_initial_version() for new documents.",
            )

        # Detect duplicate upload (same hash as current)
        if current.file_hash == file_hash and change_type != "REPROCESSED":
            raise VersionConflictError(
                f"File hash matches current version {current.version_number}. "
                "Upload a different file or use change_type=REPROCESSED.",
                details={
                    "document_id": document_id,
                    "current_version": current.version_number,
                    "file_hash": file_hash,
                },
            )

        # Warn on excessive versions
        version_count = (
            db.query(func.count(DocumentVersion.id))
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.organization_id == organization_id,
            )
            .scalar()
        )
        if version_count >= MAX_VERSIONS_WARNING_THRESHOLD:
            logger.warning(
                "Document %d has %d versions (threshold=%d). "
                "Consider archiving old versions.",
                document_id, version_count, MAX_VERSIONS_WARNING_THRESHOLD,
            )

        # Mark current as no longer current
        current.is_current = False

        # Determine next version number
        next_version = current.version_number + 1

        # Create new version
        new_version = DocumentVersion(
            organization_id=organization_id,
            document_id=document_id,
            version_number=next_version,
            file_hash=file_hash,
            file_location=file_location,
            file_size=file_size,
            change_type=change_type,
            change_reason=change_reason,
            changed_by_user_id=changed_by_user_id,
            previous_version_id=current.id,
            extracted_data_snapshot=extracted_data,
            is_current=True,
            original_filename=original_filename,
            mime_type=mime_type,
        )
        db.add(new_version)
        db.flush()

        logger.info(
            "Created version %d for document %d (type=%s, org=%d, user=%s)",
            next_version, document_id, change_type, organization_id, changed_by_user_id,
        )
        return new_version

    # ------------------------------------------------------------------
    # 3. Rollback to previous version
    # ------------------------------------------------------------------

    def rollback_to_version(
        self,
        db: Session,
        *,
        organization_id: int,
        document_id: int,
        target_version_number: int,
        rollback_reason: str,
        rolled_back_by_user_id: Optional[int] = None,
    ) -> "DocumentVersion":
        """Rollback a document to a previous version.

        This does NOT delete versions -- it creates a new version whose file
        content matches the target version. The version history is preserved
        for audit purposes.

        Args:
            organization_id: Tenant ID.
            document_id: The document to rollback.
            target_version_number: The version number to restore.
            rollback_reason: Mandatory reason for the rollback.
            rolled_back_by_user_id: User initiating the rollback.

        Returns:
            The new DocumentVersion created by the rollback.

        Raises:
            VersionNotFoundError: If the target version does not exist.
            VersionConflictError: If target is already the current version.
        """
        DocumentVersion = _get_version_model()

        # Find the target version
        target = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.version_number == target_version_number,
            )
            .first()
        )
        if target is None:
            raise VersionNotFoundError(
                message=f"Version {target_version_number} not found for document {document_id}",
            )

        if target.is_current:
            raise VersionConflictError(
                f"Version {target_version_number} is already the current version.",
                details={"document_id": document_id, "version_number": target_version_number},
            )

        # Create a new version that copies the target's file info
        reason = f"Rollback to v{target_version_number}: {rollback_reason}"

        new_version = self.create_new_version(
            db,
            organization_id=organization_id,
            document_id=document_id,
            file_hash=target.file_hash,
            file_location=target.file_location,
            change_type="CORRECTION",
            change_reason=reason,
            file_size=target.file_size,
            extracted_data=target.extracted_data_snapshot,
            changed_by_user_id=rolled_back_by_user_id,
            original_filename=target.original_filename,
            mime_type=target.mime_type,
        )

        logger.info(
            "Rolled back document %d from current to v%d (new v%d, org=%d)",
            document_id, target_version_number, new_version.version_number, organization_id,
        )
        return new_version

    # ------------------------------------------------------------------
    # 4. Compare two versions
    # ------------------------------------------------------------------

    def compare_versions(
        self,
        db: Session,
        *,
        organization_id: int,
        document_id: int,
        version_a: int,
        version_b: int,
    ) -> Dict[str, Any]:
        """Compare two versions of a document.

        Returns a diff of file metadata and extracted data changes.

        Args:
            organization_id: Tenant ID.
            document_id: The document being compared.
            version_a: First version number (typically older).
            version_b: Second version number (typically newer).

        Returns:
            Dict with keys: versions, file_changes, data_changes, summary.

        Raises:
            VersionNotFoundError: If either version does not exist.
        """
        DocumentVersion = _get_version_model()

        va = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.version_number == version_a,
            )
            .first()
        )
        vb = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.version_number == version_b,
            )
            .first()
        )

        if va is None:
            raise VersionNotFoundError(
                message=f"Version {version_a} not found for document {document_id}",
            )
        if vb is None:
            raise VersionNotFoundError(
                message=f"Version {version_b} not found for document {document_id}",
            )

        # File-level changes
        file_changes = {}
        if va.file_hash != vb.file_hash:
            file_changes["file_hash"] = {"from": va.file_hash, "to": vb.file_hash}
        if va.file_size != vb.file_size:
            file_changes["file_size"] = {"from": va.file_size, "to": vb.file_size}
        if va.file_location != vb.file_location:
            file_changes["file_location"] = {"from": va.file_location, "to": vb.file_location}
        if va.original_filename != vb.original_filename:
            file_changes["original_filename"] = {"from": va.original_filename, "to": vb.original_filename}
        if va.mime_type != vb.mime_type:
            file_changes["mime_type"] = {"from": va.mime_type, "to": vb.mime_type}

        # Extracted data diff
        data_changes = self._diff_extracted_data(
            va.extracted_data_snapshot,
            vb.extracted_data_snapshot,
        )

        return {
            "document_id": document_id,
            "version_a": {
                "version_number": va.version_number,
                "change_type": va.change_type,
                "created_at": va.created_at.isoformat() if va.created_at else None,
                "changed_by_user_id": va.changed_by_user_id,
            },
            "version_b": {
                "version_number": vb.version_number,
                "change_type": vb.change_type,
                "created_at": vb.created_at.isoformat() if vb.created_at else None,
                "changed_by_user_id": vb.changed_by_user_id,
            },
            "file_changed": bool(file_changes),
            "file_changes": file_changes,
            "data_changed": bool(data_changes),
            "data_changes": data_changes,
            "summary": self._build_comparison_summary(file_changes, data_changes, va, vb),
        }

    # ------------------------------------------------------------------
    # 5. Get version history / audit trail
    # ------------------------------------------------------------------

    def get_version_history(
        self,
        db: Session,
        *,
        organization_id: int,
        document_id: int,
        include_archived: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get full version history for a document.

        Args:
            organization_id: Tenant ID.
            document_id: The document to query.
            include_archived: Whether to include archived versions.

        Returns:
            List of version dicts ordered by version_number ascending.
        """
        DocumentVersion = _get_version_model()

        query = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.organization_id == organization_id,
            )
        )

        if not include_archived:
            query = query.filter(DocumentVersion.is_archived == False)  # noqa: E712

        versions = query.order_by(DocumentVersion.version_number.asc()).all()

        return [
            {
                "id": v.id,
                "version_number": v.version_number,
                "file_hash": v.file_hash,
                "file_location": v.file_location,
                "file_size": v.file_size,
                "change_type": v.change_type,
                "change_reason": v.change_reason,
                "changed_by_user_id": v.changed_by_user_id,
                "is_current": v.is_current,
                "is_archived": v.is_archived,
                "original_filename": v.original_filename,
                "mime_type": v.mime_type,
                "has_extracted_data": v.extracted_data_snapshot is not None,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "archived_at": v.archived_at.isoformat() if v.archived_at else None,
            }
            for v in versions
        ]

    # ------------------------------------------------------------------
    # 6. Get current version
    # ------------------------------------------------------------------

    def get_current_version(
        self,
        db: Session,
        *,
        organization_id: int,
        document_id: int,
    ) -> Optional["DocumentVersion"]:
        """Get the current (latest active) version of a document.

        Returns:
            DocumentVersion or None if no versions exist.
        """
        DocumentVersion = _get_version_model()

        return (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.is_current == True,  # noqa: E712
            )
            .first()
        )

    # ------------------------------------------------------------------
    # 7. Get specific version
    # ------------------------------------------------------------------

    def get_version(
        self,
        db: Session,
        *,
        organization_id: int,
        document_id: int,
        version_number: int,
    ) -> Optional["DocumentVersion"]:
        """Get a specific version of a document.

        Returns:
            DocumentVersion or None.
        """
        DocumentVersion = _get_version_model()

        return (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.version_number == version_number,
            )
            .first()
        )

    # ------------------------------------------------------------------
    # 8. Get version timeline
    # ------------------------------------------------------------------

    def get_version_timeline(
        self,
        db: Session,
        *,
        organization_id: int,
        document_id: int,
    ) -> Dict[str, Any]:
        """Get a rich timeline view of all versions for a document.

        Returns a structured timeline with metadata about the overall
        version history and individual version entries.
        """
        DocumentVersion = _get_version_model()

        versions = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.organization_id == organization_id,
            )
            .order_by(DocumentVersion.version_number.asc())
            .all()
        )

        if not versions:
            return {
                "document_id": document_id,
                "total_versions": 0,
                "timeline": [],
            }

        current = next((v for v in versions if v.is_current), versions[-1])

        # Build user IDs for lookup
        user_ids = {v.changed_by_user_id for v in versions if v.changed_by_user_id}
        user_names = self._resolve_user_names(db, user_ids)

        timeline_entries = []
        for v in versions:
            entry = {
                "version_number": v.version_number,
                "change_type": v.change_type,
                "change_reason": v.change_reason,
                "is_current": v.is_current,
                "is_archived": v.is_archived,
                "file_hash_short": v.file_hash[:12] if v.file_hash else None,
                "file_size": v.file_size,
                "original_filename": v.original_filename,
                "changed_by_user_id": v.changed_by_user_id,
                "changed_by_name": user_names.get(v.changed_by_user_id),
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            timeline_entries.append(entry)

        return {
            "document_id": document_id,
            "total_versions": len(versions),
            "current_version": current.version_number,
            "first_created": versions[0].created_at.isoformat() if versions[0].created_at else None,
            "last_updated": current.created_at.isoformat() if current.created_at else None,
            "unique_uploaders": len(user_ids),
            "archived_count": sum(1 for v in versions if v.is_archived),
            "timeline": timeline_entries,
        }

    # ------------------------------------------------------------------
    # 9. Archive old versions
    # ------------------------------------------------------------------

    def archive_old_versions(
        self,
        db: Session,
        *,
        organization_id: int,
        document_id: Optional[int] = None,
        archive_before_days: int = DEFAULT_ARCHIVE_AFTER_DAYS,
    ) -> Dict[str, Any]:
        """Archive non-current versions older than the threshold.

        Archived versions are soft-deleted: ``is_archived = True``.
        The current version is never archived.

        Args:
            organization_id: Tenant ID.
            document_id: Optional -- scope to a single document. If None,
                archives across all documents in the organization.
            archive_before_days: Versions older than this many days are
                candidates for archival.

        Returns:
            Dict with count of archived versions.
        """
        DocumentVersion = _get_version_model()

        cutoff = datetime.now(timezone.utc) - timedelta(days=archive_before_days)

        filters = [
            DocumentVersion.organization_id == organization_id,
            DocumentVersion.is_current == False,       # noqa: E712
            DocumentVersion.is_archived == False,      # noqa: E712
            DocumentVersion.created_at < cutoff,
        ]

        if document_id is not None:
            filters.append(DocumentVersion.document_id == document_id)

        candidates = (
            db.query(DocumentVersion)
            .filter(and_(*filters))
            .all()
        )

        now = datetime.now(timezone.utc)
        for v in candidates:
            v.is_archived = True
            v.archived_at = now

        db.flush()

        archived_count = len(candidates)
        if archived_count > 0:
            logger.info(
                "Archived %d old versions (org=%d, doc=%s, cutoff=%s)",
                archived_count, organization_id,
                document_id or "all", cutoff.isoformat(),
            )

        return {
            "archived_count": archived_count,
            "cutoff_date": cutoff.isoformat(),
            "organization_id": organization_id,
            "document_id": document_id,
        }

    # ------------------------------------------------------------------
    # 10. Bulk version operations
    # ------------------------------------------------------------------

    def bulk_create_initial_versions(
        self,
        db: Session,
        *,
        organization_id: int,
        documents: List[Dict[str, Any]],
        changed_by_user_id: Optional[int] = None,
    ) -> List["DocumentVersion"]:
        """Create initial versions for multiple documents at once.

        Each entry in ``documents`` must include:
          - document_id: int
          - file_hash: str
          - file_location: str

        Optional keys: file_size, extracted_data, original_filename, mime_type.

        Args:
            organization_id: Tenant ID.
            documents: List of document dicts.
            changed_by_user_id: User performing the bulk operation.

        Returns:
            List of created DocumentVersion instances.
        """
        DocumentVersion = _get_version_model()

        # Pre-check: ensure none of these documents already have versions
        doc_ids = [d["document_id"] for d in documents]
        existing_doc_ids = set(
            row[0]
            for row in db.query(DocumentVersion.document_id)
            .filter(
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.document_id.in_(doc_ids),
            )
            .distinct()
            .all()
        )

        if existing_doc_ids:
            raise VersionConflictError(
                f"Documents already have version history: {sorted(existing_doc_ids)}. "
                "Use create_new_version() for existing documents.",
                details={"existing_document_ids": sorted(existing_doc_ids)},
            )

        created = []
        for doc_info in documents:
            version = DocumentVersion(
                organization_id=organization_id,
                document_id=doc_info["document_id"],
                version_number=1,
                file_hash=doc_info["file_hash"],
                file_location=doc_info["file_location"],
                file_size=doc_info.get("file_size"),
                change_type="INITIAL",
                change_reason="Initial document upload (bulk)",
                changed_by_user_id=changed_by_user_id,
                previous_version_id=None,
                extracted_data_snapshot=doc_info.get("extracted_data"),
                is_current=True,
                original_filename=doc_info.get("original_filename"),
                mime_type=doc_info.get("mime_type"),
            )
            db.add(version)
            created.append(version)

        db.flush()

        logger.info(
            "Bulk created %d initial versions (org=%d, user=%s)",
            len(created), organization_id, changed_by_user_id,
        )
        return created

    def bulk_archive_versions(
        self,
        db: Session,
        *,
        organization_id: int,
        document_ids: List[int],
        archive_before_days: int = DEFAULT_ARCHIVE_AFTER_DAYS,
    ) -> Dict[str, Any]:
        """Archive old versions for multiple documents.

        Args:
            organization_id: Tenant ID.
            document_ids: List of document IDs to process.
            archive_before_days: Versions older than this are archived.

        Returns:
            Dict with per-document and total archive counts.
        """
        total_archived = 0
        per_document = {}

        for doc_id in document_ids:
            result = self.archive_old_versions(
                db,
                organization_id=organization_id,
                document_id=doc_id,
                archive_before_days=archive_before_days,
            )
            per_document[doc_id] = result["archived_count"]
            total_archived += result["archived_count"]

        return {
            "total_archived": total_archived,
            "per_document": per_document,
            "document_count": len(document_ids),
        }

    # ------------------------------------------------------------------
    # Extracted data snapshot retrieval
    # ------------------------------------------------------------------

    def get_extracted_data_at_version(
        self,
        db: Session,
        *,
        organization_id: int,
        document_id: int,
        version_number: int,
    ) -> Optional[Dict[str, Any]]:
        """Get the frozen extracted data snapshot from a specific version.

        Returns:
            The extracted_data_snapshot dict, or None if the version
            does not exist or has no snapshot.
        """
        version = self.get_version(
            db,
            organization_id=organization_id,
            document_id=document_id,
            version_number=version_number,
        )
        if version is None:
            return None
        return version.extracted_data_snapshot

    # ------------------------------------------------------------------
    # Version count
    # ------------------------------------------------------------------

    def get_version_count(
        self,
        db: Session,
        *,
        organization_id: int,
        document_id: int,
        include_archived: bool = True,
    ) -> int:
        """Get the number of versions for a document.

        Args:
            organization_id: Tenant ID.
            document_id: Document to count versions for.
            include_archived: Whether to count archived versions.

        Returns:
            Integer count of versions.
        """
        DocumentVersion = _get_version_model()

        query = db.query(func.count(DocumentVersion.id)).filter(
            DocumentVersion.document_id == document_id,
            DocumentVersion.organization_id == organization_id,
        )

        if not include_archived:
            query = query.filter(DocumentVersion.is_archived == False)  # noqa: E712

        return query.scalar() or 0

    # ------------------------------------------------------------------
    # File hash utilities
    # ------------------------------------------------------------------

    @staticmethod
    def compute_file_hash(file_bytes: bytes) -> str:
        """Compute SHA-256 hash for file content.

        Args:
            file_bytes: Raw file content.

        Returns:
            Hex digest string (64 chars).
        """
        return hashlib.sha256(file_bytes).hexdigest()

    @staticmethod
    def compute_file_hash_streaming(file_obj, chunk_size: int = 8192) -> str:
        """Compute SHA-256 hash for a file-like object without reading
        the entire file into memory.

        Args:
            file_obj: File-like object with read() method.
            chunk_size: Read chunk size in bytes.

        Returns:
            Hex digest string (64 chars).
        """
        hasher = hashlib.sha256()
        while True:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
        # Reset file position for subsequent reads
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        return hasher.hexdigest()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _enforce_change_reason(
        self,
        db: Session,
        document_id: int,
        organization_id: int,
        change_reason: Optional[str],
    ) -> None:
        """Check if the document type requires a change_reason.

        Queries the SmartDocument table to determine the doc_type. If the
        type is in REGULATED_DOC_TYPES and change_reason is empty, raises
        ChangeReasonRequiredError.
        """
        if change_reason:
            return  # Reason provided, nothing to enforce

        SmartDocument = _get_smart_document_model()
        doc = (
            db.query(SmartDocument)
            .filter(SmartDocument.id == document_id)
            .first()
        )

        if doc is None:
            raise DocumentNotFoundError(document_id)

        doc_type_str = doc.doc_type.value if doc.doc_type else None
        if doc_type_str and doc_type_str in REGULATED_DOC_TYPES:
            raise ChangeReasonRequiredError(document_id, doc_type_str)

    @staticmethod
    def _diff_extracted_data(
        data_a: Optional[Dict[str, Any]],
        data_b: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compute a field-level diff between two extracted data snapshots.

        Returns a dict of changed fields with {from, to} values.
        """
        if data_a is None and data_b is None:
            return {}
        if data_a is None:
            return {k: {"from": None, "to": v} for k, v in (data_b or {}).items()}
        if data_b is None:
            return {k: {"from": v, "to": None} for k, v in (data_a or {}).items()}

        changes = {}
        all_keys = set(data_a.keys()) | set(data_b.keys())
        for key in sorted(all_keys):
            val_a = data_a.get(key)
            val_b = data_b.get(key)
            if val_a != val_b:
                changes[key] = {"from": val_a, "to": val_b}

        return changes

    @staticmethod
    def _build_comparison_summary(
        file_changes: Dict,
        data_changes: Dict,
        va: "DocumentVersion",
        vb: "DocumentVersion",
    ) -> str:
        """Build a human-readable summary of the comparison."""
        parts = []

        if not file_changes and not data_changes:
            return f"Versions {va.version_number} and {vb.version_number} are identical."

        if file_changes:
            parts.append(f"{len(file_changes)} file attribute(s) changed")
        if data_changes:
            parts.append(f"{len(data_changes)} extracted data field(s) changed")

        summary = (
            f"v{va.version_number} -> v{vb.version_number}: "
            + ", ".join(parts)
        )

        if vb.change_type:
            summary += f" (type: {vb.change_type})"

        return summary

    @staticmethod
    def _resolve_user_names(
        db: Session,
        user_ids: set,
    ) -> Dict[int, str]:
        """Resolve user IDs to display names.

        Returns a mapping of user_id -> "first_name last_name".
        """
        if not user_ids:
            return {}

        try:
            from database.models.core import User
            users = (
                db.query(User.id, User.first_name, User.last_name)
                .filter(User.id.in_(user_ids))
                .all()
            )
            return {
                u.id: f"{u.first_name or ''} {u.last_name or ''}".strip()
                for u in users
            }
        except Exception as e:
            logger.warning("Failed to resolve user names: %s", e)
            return {}


# =============================================================================
# Module-level factory
# =============================================================================

_service_instance: Optional[DocumentVersionService] = None


def get_document_version_service() -> DocumentVersionService:
    """Get or create the singleton DocumentVersionService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = DocumentVersionService()
    return _service_instance
