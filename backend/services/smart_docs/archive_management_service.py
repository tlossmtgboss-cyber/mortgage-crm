"""
Smart Docs Archive Management Service

Post-closing document archive lifecycle management. Handles the full retention
pipeline: bundling loan documents after funding, tiered S3 storage transitions,
legal hold enforcement, archive retrieval from cold storage, purge workflows,
integrity verification, and regulatory compliance reporting.

Storage tier policy:
    Active  (0-90 days)   ->  S3 Standard
    Warm    (90d - 1 yr)  ->  S3 Standard-IA
    Cold    (1-3 yr)      ->  S3 Glacier
    Deep    (3+ yr)       ->  S3 Glacier Deep Archive

Retention policy:
    3_YEAR     ->  Standard conforming loans
    7_YEAR     ->  FHA / VA (HUD requirement)
    10_YEAR    ->  Non-QM, state-specific requirements
    PERMANENT  ->  Legal hold (no expiry)

Usage:
    from services.smart_docs.archive_management_service import (
        ArchiveManagementService,
        get_archive_management_service,
    )

    service = get_archive_management_service()
    result = await service.create_archive(db, org_id, loan_id, "POST_CLOSING", "7_YEAR", user_id)
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# RESULT TYPES
# =============================================================================

class ArchiveResultStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    NO_DATA = "no_data"
    PENDING_APPROVAL = "pending_approval"


@dataclass
class ArchiveResult:
    """Return type for archive operations."""
    status: ArchiveResultStatus
    archive_id: Optional[int] = None
    data: Optional[Dict[str, Any]] = None
    message: str = ""
    error: Optional[str] = None

    @classmethod
    def success(cls, archive_id: int = None, data: Dict = None, message: str = "") -> ArchiveResult:
        return cls(status=ArchiveResultStatus.SUCCESS, archive_id=archive_id, data=data, message=message)

    @classmethod
    def fail(cls, error: str, message: str = "") -> ArchiveResult:
        return cls(status=ArchiveResultStatus.ERROR, error=error, message=message or error)


@dataclass
class RetrievalResult:
    """Return type for archive retrieval requests."""
    status: ArchiveResultStatus
    archive_id: int = 0
    storage_class: str = ""
    available_immediately: bool = False
    restore_eta_hours: Optional[int] = None
    presigned_url: Optional[str] = None
    message: str = ""
    error: Optional[str] = None


@dataclass
class ComplianceIssue:
    """A single compliance finding."""
    loan_id: int
    loan_number: str
    archive_id: Optional[int]
    issue_type: str  # MISSING_ARCHIVE, EXPIRED_EARLY, WRONG_POLICY, INTEGRITY_FAIL
    severity: str  # critical, high, medium, low
    description: str


@dataclass
class ComplianceReport:
    """Result of a retention compliance check."""
    organization_id: int
    checked_at: str
    total_funded_loans: int = 0
    total_archives: int = 0
    compliant_count: int = 0
    non_compliant_count: int = 0
    issues: List[ComplianceIssue] = field(default_factory=list)
    summary: str = ""


@dataclass
class PurgeCandidate:
    """An archive eligible for purging."""
    archive_id: int
    loan_id: int
    loan_number: str
    archive_type: str
    retention_policy: str
    retention_expired_at: str
    document_count: int
    total_size_bytes: int
    storage_class: str


@dataclass
class PurgeReport:
    """Result of a purge cycle run."""
    organization_id: int
    dry_run: bool
    run_at: str
    candidates: List[PurgeCandidate] = field(default_factory=list)
    purged_count: int = 0
    purged_size_bytes: int = 0
    skipped_legal_hold: int = 0
    errors: List[str] = field(default_factory=list)
    summary: str = ""


# =============================================================================
# CONSTANTS
# =============================================================================

# Retention period in days for each policy
RETENTION_DAYS = {
    "3_YEAR": 365 * 3,
    "7_YEAR": 365 * 7,
    "10_YEAR": 365 * 10,
    "PERMANENT": None,  # Never expires
}

# Loan types that require extended retention
EXTENDED_RETENTION_LOAN_TYPES = {
    "fha": "7_YEAR",
    "va": "7_YEAR",
    "FHA": "7_YEAR",
    "VA": "7_YEAR",
}

NON_QM_RETENTION_LOAN_TYPES = {
    "non_qm": "10_YEAR",
    "Non-QM": "10_YEAR",
    "NON_QM": "10_YEAR",
}

# Storage tier thresholds in days
STORAGE_TIER_THRESHOLDS = {
    "STANDARD": 0,        # 0-90 days
    "STANDARD_IA": 90,    # 90 days to 1 year
    "GLACIER": 365,       # 1-3 years
    "DEEP_ARCHIVE": 1095, # 3+ years
}

# Approximate S3 cost per GB per month in cents (us-east-1 pricing)
STORAGE_COST_PER_GB_MONTH_CENTS = {
    "STANDARD": 2.3,       # $0.023/GB
    "STANDARD_IA": 1.25,   # $0.0125/GB
    "GLACIER": 0.4,        # $0.004/GB
    "DEEP_ARCHIVE": 0.099, # $0.00099/GB
}

# Glacier retrieval time estimates in hours
RETRIEVAL_TIME_HOURS = {
    "STANDARD": 0,
    "STANDARD_IA": 0,
    "GLACIER": 5,       # Expedited: 1-5 min, Standard: 3-5 hr, Bulk: 5-12 hr
    "DEEP_ARCHIVE": 48, # Standard: 12 hr, Bulk: 48 hr
}


# =============================================================================
# LAZY MODEL IMPORTS
# =============================================================================

_models_loaded = False
_DocumentArchive = None
_Document = None
_Loan = None


def _ensure_models():
    """Lazy-load models to avoid circular imports at module load time."""
    global _models_loaded, _DocumentArchive, _Document, _Loan
    if _models_loaded:
        return
    from database.models.document_archive import DocumentArchive
    from database.models.document import Document
    from database.models.lead_loan import Loan
    _DocumentArchive = DocumentArchive
    _Document = Document
    _Loan = Loan
    _models_loaded = True


# =============================================================================
# SERVICE
# =============================================================================

class ArchiveManagementService:
    """Manages document archive lifecycle: creation, storage tiering, legal
    holds, retrieval, purging, and compliance reporting.

    All public methods are async and require an ``org_id`` parameter for
    tenant isolation. The service never crosses organization boundaries.
    """

    def __init__(self):
        self._s3_service = None

    # ------------------------------------------------------------------
    # S3 integration (lazy)
    # ------------------------------------------------------------------

    def _get_s3(self):
        """Lazy-load the S3 service singleton."""
        if self._s3_service is None:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
            self._s3_service = get_smart_docs_s3_service()
        return self._s3_service

    # ------------------------------------------------------------------
    # 1. Create archive
    # ------------------------------------------------------------------

    async def create_archive(
        self,
        db: Session,
        org_id: int,
        loan_id: int,
        archive_type: str,
        retention_policy: str,
        created_by_user_id: int,
        *,
        label: Optional[str] = None,
    ) -> ArchiveResult:
        """Create a post-closing archive for a funded loan.

        Bundles all active documents for the loan, computes a manifest with
        per-file SHA-256 checksums, copies them to the archive S3 prefix,
        and creates the ``DocumentArchive`` row.

        Args:
            db: Database session (caller owns the transaction).
            org_id: Organization ID -- enforced on all queries.
            loan_id: Loan to archive.
            archive_type: POST_CLOSING | AUDIT_HOLD | REGULATORY | MANUAL.
            retention_policy: 3_YEAR | 7_YEAR | 10_YEAR | PERMANENT.
            created_by_user_id: User performing the archive.
            label: Optional human-readable label.

        Returns:
            ArchiveResult with the new archive ID.
        """
        _ensure_models()

        try:
            # Verify loan belongs to org
            loan = (
                db.query(_Loan)
                .filter(
                    _Loan.id == loan_id,
                    _Loan.organization_id == org_id,
                )
                .first()
            )
            if not loan:
                return ArchiveResult.fail("Loan not found or does not belong to this organization")

            # Check for existing active archive
            existing = (
                db.query(_DocumentArchive)
                .filter(
                    _DocumentArchive.organization_id == org_id,
                    _DocumentArchive.loan_id == loan_id,
                    _DocumentArchive.archive_status.in_(["ACTIVE", "LEGAL_HOLD"]),
                )
                .first()
            )
            if existing:
                return ArchiveResult.fail(
                    f"Active archive already exists for loan {loan_id} (archive_id={existing.id})"
                )

            # Auto-select retention policy based on loan type if not specified
            if retention_policy == "AUTO":
                retention_policy = self._determine_retention_policy(loan)

            # Gather documents
            documents = (
                db.query(_Document)
                .filter(
                    _Document.loan_id == loan_id,
                    _Document.organization_id == org_id,
                    _Document.status == "active",
                )
                .all()
            )

            # Build manifest
            manifest = []
            total_size = 0
            for doc in documents:
                entry = {
                    "doc_id": doc.id,
                    "doc_type": str(doc.doc_type) if doc.doc_type else None,
                    "filename": doc.filename,
                    "file_size": doc.file_size or 0,
                    "storage_key": doc.file_location,
                    "sha256": None,  # Populated during S3 copy
                }
                manifest.append(entry)
                total_size += doc.file_size or 0

            # Compute archive storage location
            archive_uuid = uuid.uuid4().hex[:16]
            storage_location = f"org/{org_id}/archives/{loan_id}/{archive_uuid}"

            # Copy documents to archive prefix (best-effort -- S3 may be unavailable)
            s3 = self._get_s3()
            if s3.is_available:
                for entry in manifest:
                    src_key = entry.get("storage_key")
                    if not src_key:
                        continue
                    try:
                        downloaded = s3.download_file(src_key)
                        if downloaded.get("success") and downloaded.get("content"):
                            content = downloaded["content"]
                            entry["sha256"] = hashlib.sha256(content).hexdigest()
                            dest_key = f"{storage_location}/{entry['filename']}"
                            s3.upload_file(
                                content,
                                dest_key,
                                downloaded.get("content_type", "application/octet-stream"),
                                metadata={"source_doc_id": str(entry["doc_id"])},
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to copy doc {entry['doc_id']} to archive: {e}"
                        )

            # Compute overall archive checksum from manifest checksums
            archive_checksum = self._compute_manifest_checksum(manifest)

            # Calculate retention expiry
            retention_expires_at = self._calculate_retention_expiry(retention_policy)

            # Create archive record
            archive = _DocumentArchive(
                organization_id=org_id,
                loan_id=loan_id,
                archive_type=archive_type,
                archive_status="ACTIVE",
                archive_label=label or f"Archive for loan {getattr(loan, 'loan_number', loan_id)}",
                document_count=len(documents),
                total_size_bytes=total_size,
                document_manifest=manifest,
                storage_location=storage_location,
                storage_class="STANDARD",
                retention_policy=retention_policy,
                retention_expires_at=retention_expires_at,
                legal_hold=False,
                archive_checksum=archive_checksum,
                last_integrity_check_at=datetime.now(timezone.utc),
                integrity_verified=True,
                created_by_user_id=created_by_user_id,
                monthly_storage_cost_cents=self._estimate_monthly_cost(total_size, "STANDARD"),
            )
            db.add(archive)
            db.flush()

            logger.info(
                f"Archive created: id={archive.id}, loan={loan_id}, org={org_id}, "
                f"docs={len(documents)}, size={total_size}, retention={retention_policy}"
            )

            return ArchiveResult.success(
                archive_id=archive.id,
                data={
                    "archive_id": archive.id,
                    "loan_id": loan_id,
                    "document_count": len(documents),
                    "total_size_bytes": total_size,
                    "retention_policy": retention_policy,
                    "retention_expires_at": retention_expires_at.isoformat() if retention_expires_at else None,
                    "storage_class": "STANDARD",
                    "storage_location": storage_location,
                },
                message=f"Archive created with {len(documents)} documents",
            )

        except Exception as e:
            logger.exception(f"Failed to create archive for loan {loan_id}: {e}")
            return ArchiveResult.fail(f"Archive creation failed: {e}")

    # ------------------------------------------------------------------
    # 2. Legal hold
    # ------------------------------------------------------------------

    async def place_legal_hold(
        self,
        db: Session,
        org_id: int,
        archive_id: int,
        reason: str,
        user_id: int,
    ) -> ArchiveResult:
        """Place a legal hold on an archive, preventing deletion/purge.

        Args:
            db: Database session.
            org_id: Organization ID.
            archive_id: Target archive.
            reason: Free-text explanation (litigation ref, audit ID, etc.).
            user_id: User placing the hold.

        Returns:
            ArchiveResult indicating success or failure.
        """
        _ensure_models()

        archive = (
            db.query(_DocumentArchive)
            .filter(
                _DocumentArchive.id == archive_id,
                _DocumentArchive.organization_id == org_id,
            )
            .first()
        )
        if not archive:
            return ArchiveResult.fail("Archive not found")

        if archive.archive_status == "PURGED":
            return ArchiveResult.fail("Cannot place legal hold on a purged archive")

        if archive.legal_hold:
            return ArchiveResult.fail(
                f"Legal hold already active (placed {archive.legal_hold_placed_at})"
            )

        archive.legal_hold = True
        archive.legal_hold_reason = reason
        archive.legal_hold_placed_by = user_id
        archive.legal_hold_placed_at = datetime.now(timezone.utc)
        archive.legal_hold_released_at = None
        archive.archive_status = "LEGAL_HOLD"

        db.flush()

        logger.info(
            f"Legal hold placed: archive={archive_id}, org={org_id}, "
            f"user={user_id}, reason={reason[:100]}"
        )

        return ArchiveResult.success(
            archive_id=archive_id,
            data={
                "archive_id": archive_id,
                "legal_hold": True,
                "placed_at": archive.legal_hold_placed_at.isoformat(),
                "reason": reason,
            },
            message="Legal hold placed successfully",
        )

    async def release_legal_hold(
        self,
        db: Session,
        org_id: int,
        archive_id: int,
        user_id: int,
    ) -> ArchiveResult:
        """Release a legal hold on an archive.

        If the archive's retention has not yet expired, it returns to ACTIVE
        status. If retention has expired, it moves to EXPIRED.
        """
        _ensure_models()

        archive = (
            db.query(_DocumentArchive)
            .filter(
                _DocumentArchive.id == archive_id,
                _DocumentArchive.organization_id == org_id,
            )
            .first()
        )
        if not archive:
            return ArchiveResult.fail("Archive not found")

        if not archive.legal_hold:
            return ArchiveResult.fail("No legal hold is active on this archive")

        archive.legal_hold = False
        archive.legal_hold_released_at = datetime.now(timezone.utc)

        # Determine new status
        now = datetime.now(timezone.utc)
        if archive.retention_expires_at and archive.retention_expires_at < now:
            archive.archive_status = "EXPIRED"
        else:
            archive.archive_status = "ACTIVE"

        db.flush()

        logger.info(
            f"Legal hold released: archive={archive_id}, org={org_id}, "
            f"user={user_id}, new_status={archive.archive_status}"
        )

        return ArchiveResult.success(
            archive_id=archive_id,
            data={
                "archive_id": archive_id,
                "legal_hold": False,
                "released_at": archive.legal_hold_released_at.isoformat(),
                "new_status": archive.archive_status,
            },
            message="Legal hold released",
        )

    # ------------------------------------------------------------------
    # 3. Retrieval
    # ------------------------------------------------------------------

    async def retrieve_from_archive(
        self,
        db: Session,
        org_id: int,
        archive_id: int,
        user_id: int,
    ) -> RetrievalResult:
        """Request retrieval of an archive from cold storage.

        For STANDARD and STANDARD_IA archives, a presigned URL is returned
        immediately. For GLACIER and DEEP_ARCHIVE, an S3 restore request is
        initiated and the caller is given an estimated availability time.

        Args:
            db: Database session.
            org_id: Organization ID.
            archive_id: Archive to retrieve.
            user_id: User requesting retrieval.

        Returns:
            RetrievalResult with availability info or restore ETA.
        """
        _ensure_models()

        archive = (
            db.query(_DocumentArchive)
            .filter(
                _DocumentArchive.id == archive_id,
                _DocumentArchive.organization_id == org_id,
            )
            .first()
        )
        if not archive:
            return RetrievalResult(
                status=ArchiveResultStatus.ERROR,
                error="Archive not found",
                message="Archive not found",
            )

        if archive.archive_status == "PURGED":
            return RetrievalResult(
                status=ArchiveResultStatus.ERROR,
                error="Archive has been purged and is no longer available",
                message="Archive purged",
            )

        storage_class = archive.storage_class or "STANDARD"
        eta_hours = RETRIEVAL_TIME_HOURS.get(storage_class, 0)

        # Update retrieval tracking
        archive.retrieval_count = (archive.retrieval_count or 0) + 1
        archive.last_retrieval_at = datetime.now(timezone.utc)

        if storage_class in ("STANDARD", "STANDARD_IA"):
            # Immediately available -- generate presigned URL for the archive location
            s3 = self._get_s3()
            presigned_url = None
            if s3.is_available and archive.storage_location:
                url_result = s3.get_presigned_download_url(
                    archive.storage_location,
                    file_name=f"archive_{archive_id}.zip",
                    expires_in=3600,
                    organization_id=org_id,
                )
                if url_result.get("success"):
                    presigned_url = url_result.get("presigned_url")

            db.flush()

            logger.info(
                f"Archive retrieved (immediate): archive={archive_id}, "
                f"org={org_id}, storage_class={storage_class}"
            )

            return RetrievalResult(
                status=ArchiveResultStatus.SUCCESS,
                archive_id=archive_id,
                storage_class=storage_class,
                available_immediately=True,
                restore_eta_hours=0,
                presigned_url=presigned_url,
                message="Archive available for download",
            )
        else:
            # Cold storage -- initiate restore
            archive.restore_in_progress = True
            archive.restore_eta = datetime.now(timezone.utc) + timedelta(hours=eta_hours)

            # Initiate S3 restore (best-effort)
            s3 = self._get_s3()
            if s3.is_available and archive.storage_location:
                try:
                    tier = "Expedited" if storage_class == "GLACIER" else "Standard"
                    s3.s3_client.restore_object(
                        Bucket=s3.bucket_name,
                        Key=archive.storage_location,
                        RestoreRequest={
                            "Days": 7,
                            "GlacierJobParameters": {"Tier": tier},
                        },
                    )
                except Exception as e:
                    logger.warning(f"S3 restore request failed: {e}")

            db.flush()

            logger.info(
                f"Archive restore initiated: archive={archive_id}, org={org_id}, "
                f"storage_class={storage_class}, eta_hours={eta_hours}"
            )

            return RetrievalResult(
                status=ArchiveResultStatus.PENDING_APPROVAL,
                archive_id=archive_id,
                storage_class=storage_class,
                available_immediately=False,
                restore_eta_hours=eta_hours,
                message=f"Restore initiated -- estimated availability in {eta_hours} hours",
            )

    # ------------------------------------------------------------------
    # 4. Retention compliance check
    # ------------------------------------------------------------------

    async def check_retention_compliance(
        self,
        db: Session,
        org_id: int,
    ) -> ComplianceReport:
        """Check all funded loans against retention requirements.

        Identifies:
          - Funded loans with no archive
          - Archives with incorrect retention policy for their loan type
          - Archives that expired before the required retention period
          - Archives that failed integrity checks

        Args:
            db: Database session.
            org_id: Organization to audit.

        Returns:
            ComplianceReport with all findings.
        """
        _ensure_models()

        report = ComplianceReport(
            organization_id=org_id,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

        # Get all funded loans for this org
        funded_loans = (
            db.query(_Loan)
            .filter(
                _Loan.organization_id == org_id,
                _Loan.stage == "FUNDED",
                _Loan.funded_date.isnot(None),
            )
            .all()
        )
        report.total_funded_loans = len(funded_loans)

        # Get all archives for this org
        archives = (
            db.query(_DocumentArchive)
            .filter(_DocumentArchive.organization_id == org_id)
            .all()
        )
        report.total_archives = len(archives)

        # Index archives by loan_id
        archives_by_loan: Dict[int, _DocumentArchive] = {}
        for arch in archives:
            archives_by_loan[arch.loan_id] = arch

        for loan in funded_loans:
            archive = archives_by_loan.get(loan.id)
            loan_number = getattr(loan, "loan_number", str(loan.id))

            # Check 1: Missing archive
            if archive is None:
                report.issues.append(ComplianceIssue(
                    loan_id=loan.id,
                    loan_number=loan_number,
                    archive_id=None,
                    issue_type="MISSING_ARCHIVE",
                    severity="critical",
                    description=f"Funded loan {loan_number} has no document archive",
                ))
                report.non_compliant_count += 1
                continue

            is_compliant = True

            # Check 2: Correct retention policy
            expected_policy = self._determine_retention_policy(loan)
            actual_policy = archive.retention_policy
            expected_days = RETENTION_DAYS.get(expected_policy)
            actual_days = RETENTION_DAYS.get(actual_policy)

            if expected_days is not None and actual_days is not None and actual_days < expected_days:
                report.issues.append(ComplianceIssue(
                    loan_id=loan.id,
                    loan_number=loan_number,
                    archive_id=archive.id,
                    issue_type="WRONG_POLICY",
                    severity="high",
                    description=(
                        f"Loan {loan_number} requires {expected_policy} retention "
                        f"but archive has {actual_policy}"
                    ),
                ))
                is_compliant = False

            # Check 3: Premature expiry
            if archive.archive_status == "PURGED" and archive.retention_expires_at:
                funded_date = loan.funded_date
                if funded_date and expected_days:
                    if hasattr(funded_date, "date"):
                        funded_date_d = funded_date.date()
                    else:
                        funded_date_d = funded_date
                    required_until = funded_date_d + timedelta(days=expected_days)
                    if archive.purged_at:
                        purged_date = archive.purged_at
                        if hasattr(purged_date, "date"):
                            purged_date = purged_date.date()
                        if purged_date < required_until:
                            report.issues.append(ComplianceIssue(
                                loan_id=loan.id,
                                loan_number=loan_number,
                                archive_id=archive.id,
                                issue_type="EXPIRED_EARLY",
                                severity="critical",
                                description=(
                                    f"Archive purged on {purged_date} but required "
                                    f"until {required_until}"
                                ),
                            ))
                            is_compliant = False

            # Check 4: Integrity
            if archive.integrity_verified is False:
                report.issues.append(ComplianceIssue(
                    loan_id=loan.id,
                    loan_number=loan_number,
                    archive_id=archive.id,
                    issue_type="INTEGRITY_FAIL",
                    severity="critical",
                    description="Archive integrity check failed -- possible data corruption",
                ))
                is_compliant = False

            if is_compliant:
                report.compliant_count += 1
            else:
                report.non_compliant_count += 1

        report.summary = (
            f"Checked {report.total_funded_loans} funded loans: "
            f"{report.compliant_count} compliant, "
            f"{report.non_compliant_count} non-compliant, "
            f"{len(report.issues)} issues found"
        )

        return report

    # ------------------------------------------------------------------
    # 5. Purge cycle
    # ------------------------------------------------------------------

    async def run_purge_cycle(
        self,
        db: Session,
        org_id: int,
        *,
        dry_run: bool = True,
        purged_by_user_id: Optional[int] = None,
    ) -> PurgeReport:
        """Identify and optionally purge archives whose retention has expired.

        Archives under legal hold are never purged regardless of expiry.

        Args:
            db: Database session.
            org_id: Organization to process.
            dry_run: If True (default), only identify candidates without purging.
            purged_by_user_id: User performing the purge (required if dry_run=False).

        Returns:
            PurgeReport listing candidates and actions taken.
        """
        _ensure_models()

        now = datetime.now(timezone.utc)

        report = PurgeReport(
            organization_id=org_id,
            dry_run=dry_run,
            run_at=now.isoformat(),
        )

        # Find expired archives that are not already purged and not on legal hold
        expired_archives = (
            db.query(_DocumentArchive)
            .filter(
                _DocumentArchive.organization_id == org_id,
                _DocumentArchive.archive_status.in_(["ACTIVE", "EXPIRED"]),
                _DocumentArchive.retention_expires_at.isnot(None),
                _DocumentArchive.retention_expires_at < now,
                _DocumentArchive.legal_hold == False,  # noqa: E712
            )
            .all()
        )

        # Get loan numbers for reporting
        loan_ids = [a.loan_id for a in expired_archives]
        loans_by_id = {}
        if loan_ids:
            loans = (
                db.query(_Loan)
                .filter(_Loan.id.in_(loan_ids))
                .all()
            )
            loans_by_id = {l.id: l for l in loans}

        for archive in expired_archives:
            loan = loans_by_id.get(archive.loan_id)
            loan_number = getattr(loan, "loan_number", str(archive.loan_id)) if loan else str(archive.loan_id)

            candidate = PurgeCandidate(
                archive_id=archive.id,
                loan_id=archive.loan_id,
                loan_number=loan_number,
                archive_type=archive.archive_type,
                retention_policy=archive.retention_policy,
                retention_expired_at=archive.retention_expires_at.isoformat() if archive.retention_expires_at else "",
                document_count=archive.document_count or 0,
                total_size_bytes=archive.total_size_bytes or 0,
                storage_class=archive.storage_class or "STANDARD",
            )
            report.candidates.append(candidate)

            if not dry_run:
                try:
                    # Delete from S3
                    s3 = self._get_s3()
                    if s3.is_available and archive.storage_location:
                        # Delete all objects under the archive prefix
                        self._delete_s3_prefix(s3, archive.storage_location)

                    # Mark as purged
                    archive.archive_status = "PURGED"
                    archive.purged_at = now
                    archive.purged_by_user_id = purged_by_user_id
                    archive.storage_location = None
                    archive.monthly_storage_cost_cents = 0

                    report.purged_count += 1
                    report.purged_size_bytes += archive.total_size_bytes or 0

                except Exception as e:
                    logger.exception(f"Failed to purge archive {archive.id}: {e}")
                    report.errors.append(f"Archive {archive.id}: {e}")

        # Count legal-hold archives that would have been purged
        legal_hold_count = (
            db.query(func.count(_DocumentArchive.id))
            .filter(
                _DocumentArchive.organization_id == org_id,
                _DocumentArchive.retention_expires_at.isnot(None),
                _DocumentArchive.retention_expires_at < now,
                _DocumentArchive.legal_hold == True,  # noqa: E712
            )
            .scalar()
        ) or 0
        report.skipped_legal_hold = legal_hold_count

        if not dry_run:
            db.flush()

        action = "identified" if dry_run else "purged"
        report.summary = (
            f"{action.capitalize()} {len(report.candidates)} expired archives "
            f"({report.purged_size_bytes:,} bytes). "
            f"Skipped {report.skipped_legal_hold} under legal hold."
        )

        logger.info(
            f"Purge cycle: org={org_id}, dry_run={dry_run}, "
            f"candidates={len(report.candidates)}, purged={report.purged_count}, "
            f"legal_hold_skip={report.skipped_legal_hold}"
        )

        return report

    # ------------------------------------------------------------------
    # 6. Automated archive on funding
    # ------------------------------------------------------------------

    async def auto_archive_funded_loan(
        self,
        db: Session,
        org_id: int,
        loan_id: int,
        user_id: int,
    ) -> ArchiveResult:
        """Automatically create a post-closing archive when a loan is funded.

        Determines the correct retention policy based on loan type and
        creates the archive with POST_CLOSING type.

        This should be called from a loan stage transition hook or a
        background task when stage changes to FUNDED.
        """
        _ensure_models()

        loan = (
            db.query(_Loan)
            .filter(
                _Loan.id == loan_id,
                _Loan.organization_id == org_id,
            )
            .first()
        )
        if not loan:
            return ArchiveResult.fail("Loan not found")

        retention_policy = self._determine_retention_policy(loan)

        return await self.create_archive(
            db=db,
            org_id=org_id,
            loan_id=loan_id,
            archive_type="POST_CLOSING",
            retention_policy=retention_policy,
            created_by_user_id=user_id,
            label=f"Post-closing archive for {getattr(loan, 'loan_number', loan_id)}",
        )

    # ------------------------------------------------------------------
    # 7. Integrity verification
    # ------------------------------------------------------------------

    async def verify_archive_integrity(
        self,
        db: Session,
        org_id: int,
        archive_id: int,
    ) -> ArchiveResult:
        """Verify the integrity of an archive by re-computing checksums.

        Downloads each document from the archive S3 prefix, computes its
        SHA-256, and compares against the stored manifest. Updates
        ``integrity_verified`` and ``last_integrity_check_at``.

        Args:
            db: Database session.
            org_id: Organization ID.
            archive_id: Archive to verify.

        Returns:
            ArchiveResult with verification details.
        """
        _ensure_models()

        archive = (
            db.query(_DocumentArchive)
            .filter(
                _DocumentArchive.id == archive_id,
                _DocumentArchive.organization_id == org_id,
            )
            .first()
        )
        if not archive:
            return ArchiveResult.fail("Archive not found")

        if archive.archive_status == "PURGED":
            return ArchiveResult.fail("Cannot verify integrity of a purged archive")

        manifest = archive.document_manifest or []
        s3 = self._get_s3()

        if not s3.is_available:
            return ArchiveResult.fail("S3 storage is not available for integrity check")

        verified_count = 0
        failed_count = 0
        failures = []

        for entry in manifest:
            expected_sha = entry.get("sha256")
            if not expected_sha:
                # No baseline hash -- skip
                continue

            storage_key = entry.get("storage_key")
            if not storage_key:
                continue

            # Try archive location first
            archive_key = f"{archive.storage_location}/{entry.get('filename', '')}"
            try:
                result = s3.download_file(archive_key)
                if result.get("success") and result.get("content"):
                    actual_sha = hashlib.sha256(result["content"]).hexdigest()
                    if actual_sha == expected_sha:
                        verified_count += 1
                    else:
                        failed_count += 1
                        failures.append({
                            "doc_id": entry.get("doc_id"),
                            "filename": entry.get("filename"),
                            "expected": expected_sha,
                            "actual": actual_sha,
                        })
                else:
                    failed_count += 1
                    failures.append({
                        "doc_id": entry.get("doc_id"),
                        "filename": entry.get("filename"),
                        "error": "File not found in archive",
                    })
            except Exception as e:
                failed_count += 1
                failures.append({
                    "doc_id": entry.get("doc_id"),
                    "filename": entry.get("filename"),
                    "error": str(e),
                })

        # Verify overall archive checksum
        current_checksum = self._compute_manifest_checksum(manifest)
        checksum_match = current_checksum == archive.archive_checksum

        is_verified = failed_count == 0 and checksum_match

        archive.integrity_verified = is_verified
        archive.last_integrity_check_at = datetime.now(timezone.utc)
        db.flush()

        logger.info(
            f"Integrity check: archive={archive_id}, org={org_id}, "
            f"verified={verified_count}, failed={failed_count}, "
            f"checksum_match={checksum_match}"
        )

        return ArchiveResult.success(
            archive_id=archive_id,
            data={
                "archive_id": archive_id,
                "verified": is_verified,
                "documents_verified": verified_count,
                "documents_failed": failed_count,
                "checksum_match": checksum_match,
                "failures": failures,
                "checked_at": archive.last_integrity_check_at.isoformat(),
            },
            message=(
                f"Integrity {'PASSED' if is_verified else 'FAILED'}: "
                f"{verified_count} verified, {failed_count} failed"
            ),
        )

    # ------------------------------------------------------------------
    # 8. Storage tier management
    # ------------------------------------------------------------------

    async def transition_storage_tiers(
        self,
        db: Session,
        org_id: int,
    ) -> Dict[str, Any]:
        """Evaluate all active archives and transition to the appropriate
        storage tier based on age.

        This should be run as a scheduled background task (e.g., daily).

        Returns:
            Summary of transitions performed.
        """
        _ensure_models()

        now = datetime.now(timezone.utc)
        transitions = {"STANDARD_IA": 0, "GLACIER": 0, "DEEP_ARCHIVE": 0, "errors": []}

        archives = (
            db.query(_DocumentArchive)
            .filter(
                _DocumentArchive.organization_id == org_id,
                _DocumentArchive.archive_status.in_(["ACTIVE", "LEGAL_HOLD"]),
                _DocumentArchive.storage_class != "DEEP_ARCHIVE",
            )
            .all()
        )

        for archive in archives:
            age_days = (now - archive.created_at).days if archive.created_at else 0
            target_class = self._determine_storage_class(age_days)

            if target_class == archive.storage_class:
                continue  # Already at correct tier

            # Only transition forward (cheaper), never backward
            tier_order = ["STANDARD", "STANDARD_IA", "GLACIER", "DEEP_ARCHIVE"]
            current_idx = tier_order.index(archive.storage_class) if archive.storage_class in tier_order else 0
            target_idx = tier_order.index(target_class) if target_class in tier_order else 0

            if target_idx <= current_idx:
                continue  # Don't move backward

            # Perform S3 storage class change
            s3 = self._get_s3()
            if s3.is_available and archive.storage_location:
                try:
                    s3.s3_client.copy_object(
                        Bucket=s3.bucket_name,
                        Key=archive.storage_location,
                        CopySource={"Bucket": s3.bucket_name, "Key": archive.storage_location},
                        StorageClass=target_class,
                    )
                except Exception as e:
                    logger.warning(
                        f"S3 tier transition failed for archive {archive.id}: {e}"
                    )
                    transitions["errors"].append(f"Archive {archive.id}: {e}")
                    continue

            old_class = archive.storage_class
            archive.storage_class = target_class
            archive.monthly_storage_cost_cents = self._estimate_monthly_cost(
                archive.total_size_bytes or 0, target_class
            )
            transitions[target_class] = transitions.get(target_class, 0) + 1

            logger.info(
                f"Storage tier transition: archive={archive.id}, "
                f"{old_class} -> {target_class}, age={age_days}d"
            )

        db.flush()

        total = sum(v for k, v in transitions.items() if k != "errors")
        transitions["total_transitioned"] = total
        transitions["org_id"] = org_id

        return transitions

    # ------------------------------------------------------------------
    # 9. Archive search
    # ------------------------------------------------------------------

    async def search_archives(
        self,
        db: Session,
        org_id: int,
        *,
        loan_id: Optional[int] = None,
        loan_number: Optional[str] = None,
        archive_type: Optional[str] = None,
        archive_status: Optional[str] = None,
        storage_class: Optional[str] = None,
        legal_hold_only: bool = False,
        retention_policy: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Search archives without requiring full retrieval.

        Supports filtering by loan, type, status, storage class, and
        legal hold. Returns archive metadata and document manifests.

        Args:
            db: Database session.
            org_id: Organization ID.
            loan_id: Filter by specific loan.
            loan_number: Filter by loan number (partial match).
            archive_type: Filter by archive type.
            archive_status: Filter by status.
            storage_class: Filter by storage class.
            legal_hold_only: Only return archives under legal hold.
            retention_policy: Filter by retention policy.
            limit: Max results.
            offset: Pagination offset.

        Returns:
            Dict with results list and total count.
        """
        _ensure_models()

        query = db.query(_DocumentArchive).filter(
            _DocumentArchive.organization_id == org_id,
        )

        if loan_id is not None:
            query = query.filter(_DocumentArchive.loan_id == loan_id)

        if archive_type:
            query = query.filter(_DocumentArchive.archive_type == archive_type)

        if archive_status:
            query = query.filter(_DocumentArchive.archive_status == archive_status)

        if storage_class:
            query = query.filter(_DocumentArchive.storage_class == storage_class)

        if legal_hold_only:
            query = query.filter(_DocumentArchive.legal_hold == True)  # noqa: E712

        if retention_policy:
            query = query.filter(_DocumentArchive.retention_policy == retention_policy)

        # Loan number partial match requires a join
        if loan_number:
            query = query.join(
                _Loan, _DocumentArchive.loan_id == _Loan.id
            ).filter(
                _Loan.loan_number.ilike(f"%{loan_number}%"),
            )

        total = query.count()

        archives = (
            query
            .order_by(_DocumentArchive.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Fetch loan numbers for results
        result_loan_ids = [a.loan_id for a in archives]
        loans_by_id = {}
        if result_loan_ids:
            loans = db.query(_Loan).filter(_Loan.id.in_(result_loan_ids)).all()
            loans_by_id = {l.id: l for l in loans}

        results = []
        for archive in archives:
            loan = loans_by_id.get(archive.loan_id)
            results.append({
                "archive_id": archive.id,
                "loan_id": archive.loan_id,
                "loan_number": getattr(loan, "loan_number", None) if loan else None,
                "borrower_name": getattr(loan, "borrower_name", None) if loan else None,
                "archive_type": archive.archive_type,
                "archive_status": archive.archive_status,
                "document_count": archive.document_count,
                "total_size_bytes": archive.total_size_bytes,
                "storage_class": archive.storage_class,
                "retention_policy": archive.retention_policy,
                "retention_expires_at": (
                    archive.retention_expires_at.isoformat()
                    if archive.retention_expires_at else None
                ),
                "legal_hold": archive.legal_hold,
                "legal_hold_reason": archive.legal_hold_reason if archive.legal_hold else None,
                "integrity_verified": archive.integrity_verified,
                "created_at": archive.created_at.isoformat() if archive.created_at else None,
                "document_manifest_summary": [
                    {"doc_type": e.get("doc_type"), "filename": e.get("filename")}
                    for e in (archive.document_manifest or [])
                ],
            })

        return {
            "results": results,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    # ------------------------------------------------------------------
    # 10. Storage cost tracking
    # ------------------------------------------------------------------

    async def get_storage_cost_report(
        self,
        db: Session,
        org_id: int,
    ) -> Dict[str, Any]:
        """Generate a storage cost report with optimization recommendations.

        Aggregates storage usage and cost by tier, identifies archives
        that could save money by transitioning to colder storage, and
        calculates potential savings from purging expired archives.

        Returns:
            Dict with cost breakdown, savings opportunities, and recommendations.
        """
        _ensure_models()

        archives = (
            db.query(_DocumentArchive)
            .filter(
                _DocumentArchive.organization_id == org_id,
                _DocumentArchive.archive_status.in_(["ACTIVE", "LEGAL_HOLD"]),
            )
            .all()
        )

        by_tier: Dict[str, Dict[str, Any]] = {}
        total_size = 0
        total_cost_cents = 0

        for archive in archives:
            tier = archive.storage_class or "STANDARD"
            if tier not in by_tier:
                by_tier[tier] = {
                    "count": 0,
                    "total_size_bytes": 0,
                    "monthly_cost_cents": 0,
                }
            by_tier[tier]["count"] += 1
            by_tier[tier]["total_size_bytes"] += archive.total_size_bytes or 0
            by_tier[tier]["monthly_cost_cents"] += archive.monthly_storage_cost_cents or 0

            total_size += archive.total_size_bytes or 0
            total_cost_cents += archive.monthly_storage_cost_cents or 0

        # Find optimization opportunities
        recommendations = []
        now = datetime.now(timezone.utc)

        for archive in archives:
            age_days = (now - archive.created_at).days if archive.created_at else 0
            optimal_class = self._determine_storage_class(age_days)
            current_class = archive.storage_class or "STANDARD"

            tier_order = ["STANDARD", "STANDARD_IA", "GLACIER", "DEEP_ARCHIVE"]
            if tier_order.index(optimal_class) > tier_order.index(current_class):
                current_cost = self._estimate_monthly_cost(
                    archive.total_size_bytes or 0, current_class
                )
                optimal_cost = self._estimate_monthly_cost(
                    archive.total_size_bytes or 0, optimal_class
                )
                savings = current_cost - optimal_cost
                if savings > 0:
                    recommendations.append({
                        "archive_id": archive.id,
                        "loan_id": archive.loan_id,
                        "current_tier": current_class,
                        "recommended_tier": optimal_class,
                        "age_days": age_days,
                        "monthly_savings_cents": savings,
                    })

        # Expired archives that could be purged
        expired_archives = (
            db.query(_DocumentArchive)
            .filter(
                _DocumentArchive.organization_id == org_id,
                _DocumentArchive.archive_status.in_(["ACTIVE", "EXPIRED"]),
                _DocumentArchive.retention_expires_at.isnot(None),
                _DocumentArchive.retention_expires_at < now,
                _DocumentArchive.legal_hold == False,  # noqa: E712
            )
            .all()
        )
        purgeable_size = sum(a.total_size_bytes or 0 for a in expired_archives)
        purgeable_cost = sum(a.monthly_storage_cost_cents or 0 for a in expired_archives)

        return {
            "organization_id": org_id,
            "generated_at": now.isoformat(),
            "summary": {
                "total_archives": len(archives),
                "total_size_bytes": total_size,
                "total_size_gb": round(total_size / (1024 ** 3), 3) if total_size > 0 else 0,
                "monthly_cost_cents": total_cost_cents,
                "monthly_cost_usd": round(total_cost_cents / 100, 2),
            },
            "by_tier": by_tier,
            "tier_optimization": {
                "opportunities": len(recommendations),
                "potential_monthly_savings_cents": sum(
                    r["monthly_savings_cents"] for r in recommendations
                ),
                "details": recommendations[:20],  # Top 20
            },
            "purge_savings": {
                "expired_purgeable_count": len(expired_archives),
                "purgeable_size_bytes": purgeable_size,
                "monthly_savings_cents": purgeable_cost,
            },
        }

    # ------------------------------------------------------------------
    # 11. Bulk archive operations
    # ------------------------------------------------------------------

    async def bulk_archive_funded_loans(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        *,
        funded_before: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Create archives for all funded loans that lack one.

        Designed for org-wide compliance catch-up: finds all funded loans
        without an existing archive and creates one using the appropriate
        retention policy.

        Args:
            db: Database session.
            org_id: Organization ID.
            user_id: User performing the bulk operation.
            funded_before: Only archive loans funded before this date.

        Returns:
            Summary dict with counts and errors.
        """
        _ensure_models()

        # Find funded loans without archives
        existing_archive_loan_ids = (
            db.query(_DocumentArchive.loan_id)
            .filter(
                _DocumentArchive.organization_id == org_id,
                _DocumentArchive.archive_status.in_(["ACTIVE", "LEGAL_HOLD"]),
            )
            .subquery()
        )

        query = (
            db.query(_Loan)
            .filter(
                _Loan.organization_id == org_id,
                _Loan.stage == "FUNDED",
                _Loan.funded_date.isnot(None),
                ~_Loan.id.in_(existing_archive_loan_ids),
            )
        )

        if funded_before:
            query = query.filter(_Loan.funded_date < funded_before)

        loans = query.all()

        results = {
            "organization_id": org_id,
            "total_needing_archive": len(loans),
            "created": 0,
            "failed": 0,
            "errors": [],
        }

        for loan in loans:
            try:
                result = await self.create_archive(
                    db=db,
                    org_id=org_id,
                    loan_id=loan.id,
                    archive_type="POST_CLOSING",
                    retention_policy="AUTO",
                    created_by_user_id=user_id,
                    label=f"Bulk archive for {getattr(loan, 'loan_number', loan.id)}",
                )
                if result.status == ArchiveResultStatus.SUCCESS:
                    results["created"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append(
                        f"Loan {getattr(loan, 'loan_number', loan.id)}: {result.error}"
                    )
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(
                    f"Loan {getattr(loan, 'loan_number', loan.id)}: {e}"
                )

        results["summary"] = (
            f"Bulk archive: {results['created']} created, "
            f"{results['failed']} failed out of {results['total_needing_archive']} loans"
        )

        logger.info(
            f"Bulk archive: org={org_id}, created={results['created']}, "
            f"failed={results['failed']}"
        )

        return results

    # ------------------------------------------------------------------
    # 12. Update expired archive statuses
    # ------------------------------------------------------------------

    async def update_expired_statuses(
        self,
        db: Session,
        org_id: int,
    ) -> Dict[str, Any]:
        """Mark ACTIVE archives as EXPIRED when their retention period ends.

        Should be called from a daily scheduled task. Archives under legal
        hold are not transitioned.

        Returns:
            Summary of status transitions.
        """
        _ensure_models()

        now = datetime.now(timezone.utc)

        expired = (
            db.query(_DocumentArchive)
            .filter(
                _DocumentArchive.organization_id == org_id,
                _DocumentArchive.archive_status == "ACTIVE",
                _DocumentArchive.retention_expires_at.isnot(None),
                _DocumentArchive.retention_expires_at < now,
                _DocumentArchive.legal_hold == False,  # noqa: E712
            )
            .all()
        )

        count = 0
        for archive in expired:
            archive.archive_status = "EXPIRED"
            count += 1

        if count > 0:
            db.flush()

        logger.info(f"Expired status update: org={org_id}, transitioned={count}")

        return {
            "organization_id": org_id,
            "transitioned_to_expired": count,
        }

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _determine_retention_policy(self, loan) -> str:
        """Determine the correct retention policy for a loan based on its type
        and property state."""
        loan_type = getattr(loan, "loan_type", None) or ""

        # FHA/VA: 7 years (HUD)
        if loan_type in EXTENDED_RETENTION_LOAN_TYPES:
            return EXTENDED_RETENTION_LOAN_TYPES[loan_type]

        # Non-QM: 10 years
        if loan_type in NON_QM_RETENTION_LOAN_TYPES:
            return NON_QM_RETENTION_LOAN_TYPES[loan_type]

        # State-specific: some states require longer retention
        property_state = getattr(loan, "property_state", None) or ""
        state_upper = property_state.upper()
        # NY requires 7 years, CA requires 7 years for certain disclosures
        if state_upper in ("NY", "CA"):
            return "7_YEAR"

        # Default: 3 years
        return "3_YEAR"

    def _calculate_retention_expiry(self, retention_policy: str) -> Optional[datetime]:
        """Calculate the retention expiry date from now."""
        days = RETENTION_DAYS.get(retention_policy)
        if days is None:
            return None  # PERMANENT
        return datetime.now(timezone.utc) + timedelta(days=days)

    def _determine_storage_class(self, age_days: int) -> str:
        """Determine the optimal S3 storage class based on archive age."""
        if age_days >= STORAGE_TIER_THRESHOLDS["DEEP_ARCHIVE"]:
            return "DEEP_ARCHIVE"
        elif age_days >= STORAGE_TIER_THRESHOLDS["GLACIER"]:
            return "GLACIER"
        elif age_days >= STORAGE_TIER_THRESHOLDS["STANDARD_IA"]:
            return "STANDARD_IA"
        return "STANDARD"

    def _estimate_monthly_cost(self, size_bytes: int, storage_class: str) -> int:
        """Estimate monthly storage cost in cents."""
        if size_bytes <= 0:
            return 0
        size_gb = size_bytes / (1024 ** 3)
        cost_per_gb = STORAGE_COST_PER_GB_MONTH_CENTS.get(storage_class, 2.3)
        return max(1, round(size_gb * cost_per_gb))

    def _compute_manifest_checksum(self, manifest: List[Dict]) -> str:
        """Compute a deterministic checksum over the manifest entries."""
        hasher = hashlib.sha256()
        for entry in sorted(manifest, key=lambda e: e.get("doc_id", 0)):
            doc_hash = entry.get("sha256", "")
            doc_id = str(entry.get("doc_id", ""))
            hasher.update(f"{doc_id}:{doc_hash}".encode("utf-8"))
        return hasher.hexdigest()

    def _delete_s3_prefix(self, s3, prefix: str) -> None:
        """Delete all objects under an S3 prefix."""
        try:
            paginator = s3.s3_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=s3.bucket_name, Prefix=prefix):
                objects = page.get("Contents", [])
                if objects:
                    delete_keys = [{"Key": obj["Key"]} for obj in objects]
                    s3.s3_client.delete_objects(
                        Bucket=s3.bucket_name,
                        Delete={"Objects": delete_keys},
                    )
        except Exception as e:
            logger.warning(f"Failed to delete S3 prefix {prefix}: {e}")


# =============================================================================
# SINGLETON
# =============================================================================

_archive_management_service: Optional[ArchiveManagementService] = None


def get_archive_management_service() -> ArchiveManagementService:
    """Get or create the ArchiveManagementService singleton."""
    global _archive_management_service
    if _archive_management_service is None:
        _archive_management_service = ArchiveManagementService()
    return _archive_management_service


__all__ = [
    "ArchiveManagementService",
    "get_archive_management_service",
    "ArchiveResult",
    "ArchiveResultStatus",
    "RetrievalResult",
    "ComplianceReport",
    "ComplianceIssue",
    "PurgeReport",
    "PurgeCandidate",
]
