"""
Smart Docs V2 - Data Export/Import Service

Production-grade service for bulk data export and import supporting migration,
backup, regulatory examination, and integration scenarios.

Export capabilities:
    - Full org data export (all Smart Docs data for an organization)
    - Loan-level export (all documents and metadata for a loan)
    - Document package export (submission package with metadata)
    - Configuration export (rules, templates, workflows, SLAs)
    - Audit trail export (for regulatory examination)

Export formats:
    - JSON  (structured data)
    - CSV   (tabular data)
    - ZIP   (documents + metadata bundle)
    - MISMO XML (regulatory / GSE format)
    - PDF   (merged documents with table of contents)

Import capabilities:
    - Bulk document import (ZIP with manifest)
    - Configuration import (from another org)
    - Migration import (from legacy system with type mapping)
    - MISMO XML import
    - Spreadsheet import (CSV / Excel for document metadata)

Design principles:
    - Org-id isolation on every query (multi-tenant safe)
    - Background job processing for large datasets
    - Cooperative cancellation via BatchJob status checks
    - PII redaction / encryption options
    - Streaming for large exports (chunked S3 upload)
    - Comprehensive audit trail for all export/import operations

Usage:
    from services.smart_docs.enterprise.data_export_import_service import (
        DataExportImportService,
        get_data_export_import_service,
    )

    service = get_data_export_import_service()

    # Export a loan package
    job = await service.export_loan_package(
        db=db, org_id=1, user_id=42, loan_id=100,
        export_format=ExportFormat.ZIP,
        options=ExportOptions(redact_pii=True),
    )

    # Import documents from a ZIP with manifest
    result = await service.import_documents(
        db=db, org_id=1, user_id=42,
        import_file=zip_bytes, manifest=manifest_dict,
    )
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import logging
import os
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

__all__ = [
    "DataExportImportService",
    "get_data_export_import_service",
    "ExportFormat",
    "ExportScope",
    "ExportOptions",
    "ImportMode",
    "ExportJob",
    "ImportJob",
    "ImportResult",
    "ValidationResult",
    "ValidationIssue",
    "ExportRecord",
    "JobStatus",
]


# =============================================================================
# LAZY MODEL IMPORTS
# =============================================================================

def _get_models():
    """Lazy import to avoid circular dependencies at module load time."""
    from database.models.document import Document
    from database.models.batch_job import BatchJob, BatchJobStatus, BatchJobType

    return Document, BatchJob, BatchJobStatus, BatchJobType


def _get_loan_model():
    """Lazy import for Loan model."""
    from database.models.lead_loan import Loan
    return Loan


def _get_lead_model():
    """Lazy import for Lead model."""
    from database.models.lead_loan import Lead
    return Lead


def _get_compliance_models():
    """Lazy import for compliance-related models."""
    try:
        from database.models.decision_audit import DecisionAuditLog
        return DecisionAuditLog
    except ImportError:
        return None


# =============================================================================
# SQL INJECTION PREVENTION — TABLE & COLUMN WHITELISTS
# =============================================================================

# Strict mapping from config section name to actual table name.
# Prevents SQL injection via f-string table name interpolation.
_CONFIG_TABLE_MAP: Dict[str, str] = {
    "business_rules": "smart_docs_business_rules",
    "notification_templates": "smart_docs_notification_templates",
    "sla_configs": "smart_docs_sla_configs",
    "workflow_rules": "smart_docs_workflow_rules",
}

# Valid column names for each config table. Only columns in this whitelist
# are accepted during import. Prevents SQL injection via user-controlled
# column names in INSERT statements.
_CONFIG_COLUMN_WHITELIST: Dict[str, Set[str]] = {
    "business_rules": {
        "id", "organization_id", "name", "description", "rule_type",
        "rule_category", "rule_key", "rule_value", "value_type",
        "priority", "is_active", "effective_date", "expiration_date",
        "conditions", "actions", "metadata", "source",
        "created_at", "updated_at", "created_by_user_id",
        "updated_by_user_id", "imported_by_user_id", "imported_at",
    },
    "notification_templates": {
        "id", "organization_id", "name", "description", "template_type",
        "notification_type", "subject_template", "body_template",
        "channel", "severity", "is_active", "is_system",
        "variables", "metadata",
        "created_at", "updated_at", "created_by_user_id",
        "imported_by_user_id", "imported_at",
    },
    "sla_configs": {
        "id", "organization_id", "name", "sla_name", "sla_type",
        "target_hours", "warning_threshold_pct",
        "business_hours_only", "business_hours_start", "business_hours_end",
        "exclude_weekends", "exclude_holidays",
        "escalation_enabled", "escalation_chain",
        "is_active", "created_at",
        "imported_by_user_id", "imported_at",
    },
    "workflow_rules": {
        "id", "organization_id", "name", "description", "workflow_type",
        "trigger_event", "trigger_conditions", "actions", "action_config",
        "priority", "is_active", "execution_order", "metadata",
        "created_at", "updated_at", "created_by_user_id",
        "imported_by_user_id", "imported_at",
    },
}

# Compiled regex for validating column names: only alphanumeric + underscores.
_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_column_names(
    item_keys: Set[str],
    section_name: str,
) -> Tuple[List[str], List[str]]:
    """Validate column names against whitelist and identifier format.

    Returns:
        Tuple of (valid_columns, rejected_columns).
    """
    whitelist = _CONFIG_COLUMN_WHITELIST.get(section_name, set())
    valid = []
    rejected = []

    for key in item_keys:
        if key not in whitelist:
            rejected.append(key)
        elif not _SAFE_IDENTIFIER_RE.match(key):
            # Defense-in-depth: even whitelisted names must be safe identifiers
            rejected.append(key)
        else:
            valid.append(key)

    return valid, rejected


# =============================================================================
# ENUMS
# =============================================================================

class ExportFormat(str, Enum):
    """Supported export output formats."""
    JSON = "json"
    CSV = "csv"
    ZIP = "zip"
    MISMO_XML = "mismo_xml"
    PDF = "pdf"


class ExportScope(str, Enum):
    """Scope of the export operation."""
    FULL_ORG = "full_org"
    LOAN = "loan"
    DOCUMENT_PACKAGE = "document_package"
    CONFIGURATION = "configuration"
    AUDIT_TRAIL = "audit_trail"
    REGULATORY = "regulatory"


class ImportMode(str, Enum):
    """Import strategy."""
    BULK_DOCUMENTS = "bulk_documents"
    CONFIGURATION = "configuration"
    MIGRATION = "migration"
    MISMO_XML = "mismo_xml"
    SPREADSHEET = "spreadsheet"


class ExportJobStatus(str, Enum):
    """Lifecycle status of an export/import job."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RegulatoryPackageType(str, Enum):
    """Type of regulatory data package."""
    CFPB_EXAMINATION = "cfpb_examination"
    STATE_REGULATOR = "state_regulator"
    AUDIT_FIRM = "audit_firm"
    INVESTOR_DUE_DILIGENCE = "investor_due_diligence"


# =============================================================================
# CONFIGURATION
# =============================================================================

# Maximum concurrent export/import jobs per org
MAX_CONCURRENT_JOBS_PER_ORG = int(os.getenv("EXPORT_MAX_CONCURRENT_PER_ORG", "3"))

# Maximum documents per single export
MAX_DOCS_PER_EXPORT = int(os.getenv("EXPORT_MAX_DOCS", "5000"))

# Maximum import file size (500 MB)
MAX_IMPORT_SIZE_BYTES = int(os.getenv("EXPORT_MAX_IMPORT_SIZE", str(500 * 1024 * 1024)))

# Maximum items per import batch
MAX_IMPORT_ITEMS = int(os.getenv("EXPORT_MAX_IMPORT_ITEMS", "1000"))

# Export download link expiration (seconds) -- default 24 hours
DOWNLOAD_LINK_EXPIRY_SECONDS = int(os.getenv("EXPORT_DOWNLOAD_EXPIRY", str(24 * 3600)))

# Rate limit delay between items during batch processing (seconds)
ITEM_RATE_LIMIT_SECONDS = float(os.getenv("EXPORT_ITEM_RATE_LIMIT", "0.05"))

# Async concurrency limit for file I/O within a single job
ASYNC_CONCURRENCY_LIMIT = int(os.getenv("EXPORT_ASYNC_CONCURRENCY", "5"))

# S3 prefix for export artifacts
EXPORT_S3_PREFIX = "smart-docs/exports"

# Allowed import file extensions
ALLOWED_IMPORT_EXTENSIONS = frozenset({
    ".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff",
    ".gif", ".webp", ".json", ".csv", ".xlsx", ".xml",
})

# PII patterns for redaction
_SSN_PATTERN = re.compile(
    r"\b(?!000|666|9\d{2})(\d{3})[-\s]?(?!00)(\d{2})[-\s]?(?!0000)(\d{4})\b"
)
_ACCOUNT_PATTERN = re.compile(r"\b\d{8,17}\b")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

# Legacy document type mapping for migration imports
LEGACY_DOC_TYPE_MAP: Dict[str, str] = {
    # Common legacy system names -> Smart Docs doc_type values
    "pay_stub": "Paystub",
    "paystub": "Paystub",
    "pay_stubs": "Paystub",
    "w-2": "W2",
    "w2": "W2",
    "tax_return": "Tax Return (1040)",
    "tax_returns": "Tax Return (1040)",
    "1040": "Tax Return (1040)",
    "bank_statement": "Bank Statement",
    "bank_statements": "Bank Statement",
    "credit_report": "Credit Report",
    "appraisal": "Appraisal",
    "appraisal_report": "Appraisal",
    "title": "Title Commitment",
    "title_commitment": "Title Commitment",
    "title_report": "Title Commitment",
    "insurance": "Homeowners Insurance",
    "homeowners_insurance": "Homeowners Insurance",
    "hoi": "Homeowners Insurance",
    "purchase_contract": "Purchase Contract",
    "contract": "Purchase Contract",
    "drivers_license": "Driver's License",
    "dl": "Driver's License",
    "id": "Driver's License",
    "gift_letter": "Gift Letter",
    "1099": "1099",
    "profit_loss": "Profit & Loss Statement",
    "p_and_l": "Profit & Loss Statement",
    "pnl": "Profit & Loss Statement",
    "le": "Loan Estimate",
    "loan_estimate": "Loan Estimate",
    "cd": "Closing Disclosure",
    "closing_disclosure": "Closing Disclosure",
    "initial_disclosures": "Initial Disclosures",
    "other": "Other",
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ExportOptions:
    """Configuration for an export operation."""
    redact_pii: bool = False
    encrypt_output: bool = False
    watermark_text: Optional[str] = None
    include_metadata: bool = True
    include_audit_trail: bool = False
    include_versions: bool = False
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    document_types: Optional[List[str]] = None
    document_statuses: Optional[List[str]] = None
    loan_ids: Optional[List[int]] = None
    compress: bool = True
    chunk_size: int = 100
    webhook_url: Optional[str] = None
    s3_destination: Optional[str] = None


@dataclass
class ExportJob:
    """Represents a running or completed export job."""
    job_id: str
    org_id: int
    scope: ExportScope
    export_format: ExportFormat
    status: ExportJobStatus
    total_items: int = 0
    processed_items: int = 0
    failed_items: int = 0
    download_url: Optional[str] = None
    download_expires_at: Optional[datetime] = None
    file_size_bytes: int = 0
    file_hash: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    created_by_user_id: Optional[int] = None
    options: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def progress_pct(self) -> float:
        if self.total_items == 0:
            return 0.0
        return min(round(
            ((self.processed_items + self.failed_items) / self.total_items) * 100, 1
        ), 100.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "org_id": self.org_id,
            "scope": self.scope.value,
            "format": self.export_format.value,
            "status": self.status.value,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "failed_items": self.failed_items,
            "progress_pct": self.progress_pct,
            "download_url": self.download_url,
            "download_expires_at": (
                self.download_expires_at.isoformat() if self.download_expires_at else None
            ),
            "file_size_bytes": self.file_size_bytes,
            "file_hash": self.file_hash,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_by_user_id": self.created_by_user_id,
            "metadata": self.metadata,
        }


@dataclass
class ImportJob:
    """Represents a running or completed import job."""
    job_id: str
    org_id: int
    mode: ImportMode
    status: ExportJobStatus
    total_items: int = 0
    processed_items: int = 0
    failed_items: int = 0
    skipped_items: int = 0
    error: Optional[str] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    created_by_user_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def progress_pct(self) -> float:
        if self.total_items == 0:
            return 0.0
        processed = self.processed_items + self.failed_items + self.skipped_items
        return min(round((processed / self.total_items) * 100, 1), 100.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "org_id": self.org_id,
            "mode": self.mode.value,
            "status": self.status.value,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "failed_items": self.failed_items,
            "skipped_items": self.skipped_items,
            "progress_pct": self.progress_pct,
            "error": self.error,
            "errors": self.errors[:50],  # Cap error list in response
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_by_user_id": self.created_by_user_id,
            "metadata": self.metadata,
        }


@dataclass
class ImportResult:
    """Final result of a completed import operation."""
    success: bool
    total_items: int
    imported_items: int
    failed_items: int
    skipped_items: int
    errors: List[Dict[str, Any]]
    warnings: List[str]
    summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "total_items": self.total_items,
            "imported_items": self.imported_items,
            "failed_items": self.failed_items,
            "skipped_items": self.skipped_items,
            "errors": self.errors[:100],
            "warnings": self.warnings[:50],
            "summary": self.summary,
        }


@dataclass
class ValidationIssue:
    """A single validation finding during import validation."""
    severity: str  # error, warning, info
    code: str
    message: str
    item_index: Optional[int] = None
    field: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class ValidationResult:
    """Result of import data validation."""
    is_valid: bool
    total_items: int
    valid_items: int
    issues: List[ValidationIssue]

    @property
    def error_count(self) -> int:
        return len([i for i in self.issues if i.severity == "error"])

    @property
    def warning_count(self) -> int:
        return len([i for i in self.issues if i.severity == "warning"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "total_items": self.total_items,
            "valid_items": self.valid_items,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [
                {
                    "severity": i.severity,
                    "code": i.code,
                    "message": i.message,
                    "item_index": i.item_index,
                    "field": i.field,
                    "details": i.details,
                }
                for i in self.issues[:200]  # Cap at 200 issues in response
            ],
        }


@dataclass
class ExportRecord:
    """Historical record of a completed export."""
    job_id: str
    scope: str
    export_format: str
    status: str
    total_items: int
    file_size_bytes: int
    file_hash: Optional[str]
    created_by_user_id: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]
    download_url: Optional[str]
    download_expired: bool
    pii_redacted: bool
    encrypted: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "scope": self.scope,
            "format": self.export_format,
            "status": self.status,
            "total_items": self.total_items,
            "file_size_bytes": self.file_size_bytes,
            "file_hash": self.file_hash,
            "created_by_user_id": self.created_by_user_id,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "download_url": self.download_url,
            "download_expired": self.download_expired,
            "pii_redacted": self.pii_redacted,
            "encrypted": self.encrypted,
        }


@dataclass
class JobStatus:
    """Current status of an export or import job."""
    job_id: str
    status: str
    progress_pct: float
    total_items: int
    processed_items: int
    failed_items: int
    error: Optional[str]
    download_url: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress_pct": self.progress_pct,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "failed_items": self.failed_items,
            "error": self.error,
            "download_url": self.download_url,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# =============================================================================
# EXCEPTIONS
# =============================================================================

class DataExportImportError(Exception):
    """Base exception for export/import operations."""

    def __init__(self, message: str, code: str = "EXPORT_IMPORT_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ExportConcurrencyLimitError(DataExportImportError):
    """Raised when org exceeds max concurrent export/import jobs."""

    def __init__(self, org_id: int, current_count: int):
        super().__init__(
            message=(
                f"Organization {org_id} already has {current_count} active export/import "
                f"jobs (max {MAX_CONCURRENT_JOBS_PER_ORG}). Wait for existing jobs to "
                f"finish or cancel them."
            ),
            code="CONCURRENCY_LIMIT_EXCEEDED",
        )


class ExportSizeLimitError(DataExportImportError):
    """Raised when export exceeds size limits."""

    def __init__(self, item_count: int, max_count: int):
        super().__init__(
            message=f"Export contains {item_count} items, exceeding maximum of {max_count}.",
            code="SIZE_LIMIT_EXCEEDED",
        )


class ImportValidationError(DataExportImportError):
    """Raised when import data fails validation."""

    def __init__(self, message: str, issues: Optional[List[ValidationIssue]] = None):
        self.issues = issues or []
        super().__init__(message=message, code="IMPORT_VALIDATION_FAILED")


# =============================================================================
# SERVICE
# =============================================================================

class DataExportImportService:
    """
    Orchestrates Smart Docs data export and import operations with background
    job processing, progress tracking, and PII handling.

    All public methods require explicit org_id for tenant isolation.
    """

    def __init__(self):
        # In-memory job tracking (backed by BatchJob table for persistence)
        self._active_jobs: Dict[str, Union[ExportJob, ImportJob]] = {}

    # ------------------------------------------------------------------
    # Internal: Job lifecycle
    # ------------------------------------------------------------------

    def _generate_job_id(self) -> str:
        """Generate a unique job identifier."""
        return f"exp_{uuid.uuid4().hex[:16]}"

    def _check_concurrency(self, db: Session, org_id: int) -> int:
        """
        Check active export/import jobs for the org.
        Raises ExportConcurrencyLimitError if at capacity.
        Returns current active count.
        """
        Document, BatchJob, BatchJobStatus, BatchJobType = _get_models()

        active_count = (
            db.query(func.count(BatchJob.id))
            .filter(
                BatchJob.organization_id == org_id,
                BatchJob.status.in_([
                    BatchJobStatus.PENDING.value,
                    BatchJobStatus.RUNNING.value,
                ]),
                BatchJob.job_type == BatchJobType.BULK_EXPORT.value,
            )
            .scalar()
        ) or 0

        if active_count >= MAX_CONCURRENT_JOBS_PER_ORG:
            raise ExportConcurrencyLimitError(org_id, active_count)

        return active_count

    def _create_batch_job(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        total_items: int,
        input_params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Create a BatchJob row for tracking in the database."""
        Document, BatchJob, BatchJobStatus, BatchJobType = _get_models()

        self._check_concurrency(db, org_id)

        job = BatchJob(
            organization_id=org_id,
            job_type=BatchJobType.BULK_EXPORT.value,
            status=BatchJobStatus.PENDING.value,
            total_items=total_items,
            input_params=input_params,
            created_by_user_id=user_id,
        )
        db.add(job)
        db.flush()
        logger.info(
            "export_import_job_created job_id=%s org_id=%s items=%s user_id=%s",
            job.id, org_id, total_items, user_id,
        )
        return job

    def _log_export_audit(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        job_id: str,
        scope: str,
        export_format: str,
        item_count: int,
        pii_redacted: bool,
        encrypted: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an export event to the audit trail for regulatory compliance."""
        DecisionAuditLog = _get_compliance_models()
        if DecisionAuditLog is None:
            logger.warning(
                "export_audit_skipped: DecisionAuditLog model not available "
                "job_id=%s org_id=%s",
                job_id, org_id,
            )
            return

        try:
            audit = DecisionAuditLog(
                organization_id=org_id,
                decision_type="data_export",
                decision="approved",
                decision_maker_type="user",
                decision_maker_id=str(user_id),
                loan_id=None,
                document_id=None,
                context={
                    "job_id": job_id,
                    "scope": scope,
                    "format": export_format,
                    "item_count": item_count,
                    "pii_redacted": pii_redacted,
                    "encrypted": encrypted,
                    **(metadata or {}),
                },
            )
            db.add(audit)
            db.flush()
            logger.info(
                "export_audit_logged job_id=%s org_id=%s scope=%s",
                job_id, org_id, scope,
            )
        except Exception as e:
            # Audit logging failure should not block the export
            logger.error(
                "export_audit_failed job_id=%s org_id=%s error=%s",
                job_id, org_id, str(e),
            )

    # ------------------------------------------------------------------
    # Internal: Data fetching (org-scoped)
    # ------------------------------------------------------------------

    def _fetch_org_documents(
        self,
        db: Session,
        org_id: int,
        options: ExportOptions,
        loan_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch documents for an organization with optional filters.
        Returns list of document dicts. Always filters by org_id.
        """
        Document, _, _, _ = _get_models()

        query = db.query(Document).filter(Document.organization_id == org_id)

        if loan_id is not None:
            query = query.filter(Document.loan_id == loan_id)

        if options.loan_ids:
            query = query.filter(Document.loan_id.in_(options.loan_ids))

        if options.document_types:
            query = query.filter(Document.doc_type.in_(options.document_types))

        if options.document_statuses:
            query = query.filter(Document.status.in_(options.document_statuses))
        else:
            # Default: only active documents
            query = query.filter(Document.status == "active")

        if options.date_range_start:
            query = query.filter(Document.uploaded_at >= options.date_range_start)

        if options.date_range_end:
            query = query.filter(Document.uploaded_at <= options.date_range_end)

        query = query.order_by(Document.uploaded_at.desc())

        docs = query.all()

        return [self._document_to_dict(doc) for doc in docs]

    def _document_to_dict(self, doc: Any) -> Dict[str, Any]:
        """Convert a Document ORM object to a serializable dict."""
        return {
            "id": doc.id,
            "organization_id": doc.organization_id,
            "borrower_id": doc.borrower_id,
            "loan_id": doc.loan_id,
            "doc_type": str(doc.doc_type.value) if doc.doc_type else None,
            "doc_category": str(doc.doc_category.value) if doc.doc_category else None,
            "filename": doc.filename,
            "original_filename": doc.original_filename,
            "file_size": doc.file_size,
            "mime_type": doc.mime_type,
            "file_location": doc.file_location,
            "period_start_date": (
                doc.period_start_date.isoformat() if doc.period_start_date else None
            ),
            "period_end_date": (
                doc.period_end_date.isoformat() if doc.period_end_date else None
            ),
            "source": doc.source,
            "status": doc.status,
            "notes": doc.notes,
            "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            "uploaded_by_user_id": doc.uploaded_by_user_id,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        }

    def _fetch_loan_metadata(
        self,
        db: Session,
        org_id: int,
        loan_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Fetch loan metadata for inclusion in exports."""
        Loan = _get_loan_model()

        loan = (
            db.query(Loan)
            .filter(Loan.id == loan_id, Loan.organization_id == org_id)
            .first()
        )
        if loan is None:
            return None

        return {
            "id": loan.id,
            "loan_number": loan.loan_number,
            "borrower_name": loan.borrower_name,
            "borrower_email": loan.borrower_email,
            "stage": loan.stage,
            "loan_type": loan.loan_type,
            "amount": float(loan.amount) if loan.amount else None,
            "rate": float(loan.rate) if loan.rate else None,
            "property_address": loan.property_address,
            "application_date": (
                loan.application_date.isoformat() if loan.application_date else None
            ),
            "closing_date": (
                loan.closing_date.isoformat() if loan.closing_date else None
            ),
            "funded_date": (
                loan.funded_date.isoformat() if loan.funded_date else None
            ),
        }

    def _fetch_audit_trail(
        self,
        db: Session,
        org_id: int,
        loan_id: Optional[int] = None,
        date_start: Optional[datetime] = None,
        date_end: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch audit trail records for an org, optionally filtered by loan."""
        DecisionAuditLog = _get_compliance_models()
        if DecisionAuditLog is None:
            return []

        query = db.query(DecisionAuditLog).filter(
            DecisionAuditLog.organization_id == org_id
        )

        if loan_id is not None:
            query = query.filter(DecisionAuditLog.loan_id == loan_id)

        if date_start:
            query = query.filter(DecisionAuditLog.created_at >= date_start)

        if date_end:
            query = query.filter(DecisionAuditLog.created_at <= date_end)

        query = query.order_by(DecisionAuditLog.created_at.desc()).limit(10000)
        records = query.all()

        results = []
        for r in records:
            results.append({
                "id": r.id,
                "decision_type": r.decision_type,
                "decision": r.decision,
                "decision_maker_type": r.decision_maker_type,
                "decision_maker_id": r.decision_maker_id,
                "loan_id": r.loan_id,
                "document_id": r.document_id,
                "context": r.context,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

        return results

    # ------------------------------------------------------------------
    # Internal: PII handling
    # ------------------------------------------------------------------

    def _redact_pii_in_text(self, text_value: str) -> str:
        """Redact PII patterns from a text string."""
        if not text_value:
            return text_value

        result = _SSN_PATTERN.sub("[REDACTED-SSN]", text_value)
        result = _ACCOUNT_PATTERN.sub("[REDACTED-ACCOUNT]", result)
        result = _EMAIL_PATTERN.sub("[REDACTED-EMAIL]", result)

        return result

    def _redact_pii_in_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively redact PII from a dictionary."""
        sensitive_keys = {
            "ssn", "social_security", "social_security_number",
            "account_number", "routing_number", "bank_account",
            "borrower_email", "email", "phone", "borrower_phone",
            "date_of_birth", "dob",
        }

        redacted = {}
        for key, value in data.items():
            if key.lower() in sensitive_keys:
                if isinstance(value, str) and value:
                    if "email" in key.lower():
                        redacted[key] = "[REDACTED-EMAIL]"
                    elif "phone" in key.lower():
                        redacted[key] = "[REDACTED-PHONE]"
                    elif "ssn" in key.lower() or "social" in key.lower():
                        redacted[key] = "[REDACTED-SSN]"
                    elif "dob" in key.lower() or "birth" in key.lower():
                        redacted[key] = "[REDACTED-DOB]"
                    else:
                        redacted[key] = "[REDACTED]"
                else:
                    redacted[key] = "[REDACTED]"
            elif isinstance(value, dict):
                redacted[key] = self._redact_pii_in_dict(value)
            elif isinstance(value, list):
                redacted[key] = [
                    self._redact_pii_in_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            elif isinstance(value, str):
                redacted[key] = self._redact_pii_in_text(value)
            else:
                redacted[key] = value

        return redacted

    # ------------------------------------------------------------------
    # Internal: Format serializers
    # ------------------------------------------------------------------

    def _serialize_json(
        self,
        data: Dict[str, Any],
        redact_pii: bool = False,
    ) -> bytes:
        """Serialize data to JSON bytes."""
        if redact_pii:
            data = self._redact_pii_in_dict(data)

        def _json_serializer(obj: Any) -> Any:
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, Enum):
                return obj.value
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        return json.dumps(
            data, indent=2, default=_json_serializer, ensure_ascii=False
        ).encode("utf-8")

    def _serialize_csv(
        self,
        rows: List[Dict[str, Any]],
        redact_pii: bool = False,
    ) -> bytes:
        """Serialize a list of flat dicts to CSV bytes."""
        if not rows:
            return b""

        if redact_pii:
            rows = [self._redact_pii_in_dict(row) for row in rows]

        output = io.StringIO()
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for row in rows:
            # Flatten any nested values for CSV
            flat_row = {}
            for key, value in row.items():
                if isinstance(value, (dict, list)):
                    flat_row[key] = json.dumps(value, default=str)
                elif isinstance(value, (datetime, date)):
                    flat_row[key] = value.isoformat()
                elif isinstance(value, Decimal):
                    flat_row[key] = str(value)
                else:
                    flat_row[key] = value
            writer.writerow(flat_row)

        return output.getvalue().encode("utf-8")

    def _build_zip_package(
        self,
        documents: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        file_contents: Dict[int, bytes],
        redact_pii: bool = False,
        watermark_text: Optional[str] = None,
    ) -> bytes:
        """
        Build a ZIP package containing documents and metadata.

        Structure:
            manifest.json          -- export metadata and document index
            metadata/
                loan_metadata.json -- loan details (if loan export)
                export_info.json   -- export timestamp, options, hash
            documents/
                001_Paystub_john_doe.pdf
                002_W2_john_doe.pdf
                ...
        """
        buf = io.BytesIO()

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # Build manifest
            manifest = {
                "export_version": "2.0",
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "pii_redacted": redact_pii,
                "watermarked": watermark_text is not None,
                "document_count": len(documents),
                "documents": [],
            }

            for idx, doc in enumerate(documents, start=1):
                doc_entry = dict(doc)
                if redact_pii:
                    doc_entry = self._redact_pii_in_dict(doc_entry)

                # Remove file_location from exported metadata (internal path)
                doc_entry.pop("file_location", None)

                safe_type = (doc.get("doc_type") or "document").replace(" ", "_")
                safe_name = re.sub(r"[^\w\-.]", "_", doc.get("filename") or "file")
                archive_name = f"documents/{idx:04d}_{safe_type}_{safe_name}"

                doc_entry["archive_path"] = archive_name
                manifest["documents"].append(doc_entry)

                # Add file content if available
                doc_id = doc.get("id")
                if doc_id and doc_id in file_contents:
                    content = file_contents[doc_id]
                    # Watermark PDF files if requested
                    if watermark_text and safe_name.lower().endswith(".pdf"):
                        content = self._apply_watermark(content, watermark_text)
                    zf.writestr(archive_name, content)

            # Write manifest
            manifest_bytes = self._serialize_json(manifest, redact_pii=False)
            zf.writestr("manifest.json", manifest_bytes)

            # Write metadata
            if redact_pii:
                metadata = self._redact_pii_in_dict(metadata)
            metadata_bytes = self._serialize_json(metadata, redact_pii=False)
            zf.writestr("metadata/export_info.json", metadata_bytes)

            if "loan" in metadata:
                loan_bytes = self._serialize_json(
                    metadata["loan"], redact_pii=False
                )
                zf.writestr("metadata/loan_metadata.json", loan_bytes)

        return buf.getvalue()

    def _apply_watermark(self, pdf_bytes: bytes, watermark_text: str) -> bytes:
        """
        Apply a watermark to a PDF. Falls back to returning unmodified bytes
        if pypdf is not available.
        """
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            try:
                from PyPDF2 import PdfReader, PdfWriter  # type: ignore[no-redef]
            except ImportError:
                logger.debug(
                    "watermark_skipped: pypdf/PyPDF2 not installed, "
                    "returning unmodified PDF"
                )
                return pdf_bytes

        try:
            # Create watermark page
            watermark_buf = io.BytesIO()
            try:
                from reportlab.pdfgen import canvas as rl_canvas
                from reportlab.lib.pagesizes import letter
                from reportlab.lib.colors import Color

                c = rl_canvas.Canvas(watermark_buf, pagesize=letter)
                c.setFont("Helvetica", 48)
                c.setFillColor(Color(0.8, 0.8, 0.8, alpha=0.3))
                c.saveState()
                c.translate(letter[0] / 2, letter[1] / 2)
                c.rotate(45)
                c.drawCentredString(0, 0, watermark_text)
                c.restoreState()
                c.save()
            except ImportError:
                logger.debug("watermark_skipped: reportlab not installed")
                return pdf_bytes

            # Merge watermark onto each page
            watermark_buf.seek(0)
            watermark_reader = PdfReader(watermark_buf)
            watermark_page = watermark_reader.pages[0]

            reader = PdfReader(io.BytesIO(pdf_bytes))
            writer = PdfWriter()

            for page in reader.pages:
                page.merge_page(watermark_page)
                writer.add_page(page)

            output = io.BytesIO()
            writer.write(output)
            return output.getvalue()

        except Exception as e:
            logger.warning("watermark_failed: %s, returning unmodified PDF", str(e))
            return pdf_bytes

    def _generate_mismo_xml(
        self,
        db: Session,
        org_id: int,
        loan_id: int,
    ) -> bytes:
        """
        Generate MISMO 3.6 XML for a loan using the existing MISMO mapper.
        Falls back to a minimal XML if the mapper service is unavailable.
        """
        try:
            from services.smart_docs.integrations.mismo_mapper_service import (
                MISMOMapperService,
            )
            mapper = MISMOMapperService(db)
            xml_str = mapper.generate_mismo_xml(loan_id=loan_id, org_id=org_id)
            return xml_str.encode("utf-8")
        except ImportError:
            logger.warning(
                "mismo_mapper_unavailable: generating minimal MISMO XML for "
                "loan_id=%s org_id=%s",
                loan_id, org_id,
            )
        except Exception as e:
            logger.error(
                "mismo_xml_generation_failed: loan_id=%s org_id=%s error=%s",
                loan_id, org_id, str(e),
            )

        # Fallback: minimal MISMO wrapper with loan metadata
        import defusedxml.ElementTree as ET

        root = ET.Element("MESSAGE", xmlns="http://www.mismo.org/residential/2009/schemas")
        root.set("MISMOReferenceModelIdentifier", "3.6")

        deal = ET.SubElement(root, "DEAL_SETS")
        deal_set = ET.SubElement(deal, "DEAL_SET")
        deals = ET.SubElement(deal_set, "DEALS")
        deal_elem = ET.SubElement(deals, "DEAL")

        loan_meta = self._fetch_loan_metadata(db, org_id, loan_id)
        if loan_meta:
            loans_elem = ET.SubElement(deal_elem, "LOANS")
            loan_elem = ET.SubElement(loans_elem, "LOAN")

            for field_name, xml_tag in [
                ("loan_number", "LoanIdentifier"),
                ("amount", "LoanAmountType"),
                ("rate", "NoteRatePercent"),
                ("loan_type", "MortgageType"),
                ("stage", "LoanStatusType"),
            ]:
                value = loan_meta.get(field_name)
                if value is not None:
                    elem = ET.SubElement(loan_elem, xml_tag)
                    elem.text = str(value)

        tree = ET.ElementTree(root)
        xml_buf = io.BytesIO()
        tree.write(xml_buf, encoding="unicode", xml_declaration=True)
        return xml_buf.getvalue().encode("utf-8")

    def _generate_pdf_package(
        self,
        documents: List[Dict[str, Any]],
        file_contents: Dict[int, bytes],
        metadata: Dict[str, Any],
        watermark_text: Optional[str] = None,
    ) -> bytes:
        """
        Merge all documents into a single PDF with a table of contents cover page.
        Falls back to a ZIP of individual PDFs if pypdf is not available.
        """
        try:
            from pypdf import PdfReader, PdfWriter, PdfMerger
        except ImportError:
            try:
                from PyPDF2 import PdfReader, PdfWriter, PdfMerger  # type: ignore[no-redef]
            except ImportError:
                logger.warning(
                    "pdf_merge_unavailable: pypdf/PyPDF2 not installed, "
                    "falling back to ZIP package"
                )
                return self._build_zip_package(
                    documents, metadata, file_contents,
                    watermark_text=watermark_text,
                )

        try:
            merger = PdfMerger()

            # Generate TOC cover page
            toc_bytes = self._generate_toc_page(documents, metadata)
            if toc_bytes:
                merger.append(io.BytesIO(toc_bytes))

            # Append each document
            page_offset = 1 if toc_bytes else 0
            for doc in documents:
                doc_id = doc.get("id")
                if doc_id and doc_id in file_contents:
                    content = file_contents[doc_id]
                    # Only merge PDF files
                    if (doc.get("mime_type") or "").lower() == "application/pdf":
                        try:
                            merger.append(io.BytesIO(content))
                        except Exception as e:
                            logger.warning(
                                "pdf_merge_skip: doc_id=%s error=%s",
                                doc_id, str(e),
                            )

            output = io.BytesIO()
            merger.write(output)
            merger.close()

            result = output.getvalue()

            if watermark_text:
                result = self._apply_watermark(result, watermark_text)

            return result

        except Exception as e:
            logger.error("pdf_package_generation_failed: %s", str(e))
            return self._build_zip_package(
                documents, metadata, file_contents,
                watermark_text=watermark_text,
            )

    def _generate_toc_page(
        self,
        documents: List[Dict[str, Any]],
        metadata: Dict[str, Any],
    ) -> Optional[bytes]:
        """Generate a PDF table of contents page. Returns None if reportlab is unavailable."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib import colors
            from reportlab.lib.units import inch
        except ImportError:
            return None

        buf = io.BytesIO()
        doc_template = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        # Title
        title_style = styles["Title"]
        elements.append(Paragraph("Document Package - Table of Contents", title_style))
        elements.append(Spacer(1, 0.3 * inch))

        # Export info
        info_style = styles["Normal"]
        export_date = metadata.get("exported_at", datetime.now(timezone.utc).isoformat())
        elements.append(Paragraph(f"Export Date: {export_date}", info_style))

        loan_info = metadata.get("loan", {})
        if loan_info:
            loan_num = loan_info.get("loan_number", "N/A")
            borrower = loan_info.get("borrower_name", "N/A")
            elements.append(Paragraph(f"Loan: {loan_num}", info_style))
            elements.append(Paragraph(f"Borrower: {borrower}", info_style))

        elements.append(Spacer(1, 0.3 * inch))

        # Document table
        table_data = [["#", "Document Type", "Filename", "Date", "Status"]]
        for idx, doc_item in enumerate(documents, start=1):
            table_data.append([
                str(idx),
                str(doc_item.get("doc_type", "Other")),
                str(doc_item.get("filename", ""))[:40],
                str(doc_item.get("uploaded_at", ""))[:10],
                str(doc_item.get("status", "")),
            ])

        table = Table(table_data, colWidths=[0.4 * inch, 1.8 * inch, 2.5 * inch, 1.0 * inch, 0.8 * inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.2, 0.3, 0.5)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.Color(0.95, 0.95, 0.95), colors.white]),
        ]))
        elements.append(table)

        elements.append(Spacer(1, 0.5 * inch))
        elements.append(Paragraph(
            f"Total documents: {len(documents)}",
            info_style,
        ))

        try:
            doc_template.build(elements)
            return buf.getvalue()
        except Exception as e:
            logger.warning("toc_generation_failed: %s", str(e))
            return None

    # ------------------------------------------------------------------
    # Internal: S3 upload for export artifacts
    # ------------------------------------------------------------------

    def _upload_export_to_s3(
        self,
        org_id: int,
        job_id: str,
        content: bytes,
        filename: str,
        content_type: str,
    ) -> Optional[str]:
        """Upload export artifact to S3 and return a presigned download URL."""
        try:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

            s3 = get_smart_docs_s3_service()
            if not s3.is_available:
                logger.warning("s3_not_available: export stored in-memory only")
                return None

            storage_key = (
                f"org/{org_id}/{EXPORT_S3_PREFIX}/{job_id}/{filename}"
            )

            upload_result = s3.upload_file(
                file_content=content,
                storage_key=storage_key,
                content_type=content_type,
                metadata={
                    "export_job_id": job_id,
                    "org_id": str(org_id),
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            if not upload_result.get("success"):
                logger.error(
                    "export_s3_upload_failed job_id=%s error=%s",
                    job_id, upload_result.get("error"),
                )
                return None

            # Generate presigned download URL
            url_result = s3.get_presigned_download_url(
                storage_key=storage_key,
                file_name=filename,
                expires_in=DOWNLOAD_LINK_EXPIRY_SECONDS,
                organization_id=org_id,
            )

            if url_result.get("success"):
                return url_result["presigned_url"]
            else:
                logger.error(
                    "export_presigned_url_failed job_id=%s error=%s",
                    job_id, url_result.get("error"),
                )
                return None

        except ImportError:
            logger.warning("s3_service_not_available: export cannot be uploaded")
            return None
        except Exception as e:
            logger.error(
                "export_s3_upload_error job_id=%s error=%s",
                job_id, str(e),
            )
            return None

    # ------------------------------------------------------------------
    # Internal: File content retrieval
    # ------------------------------------------------------------------

    async def _fetch_file_contents(
        self,
        documents: List[Dict[str, Any]],
        semaphore: Optional[asyncio.Semaphore] = None,
    ) -> Dict[int, bytes]:
        """
        Fetch file contents from S3 for a list of documents.
        Uses a semaphore to limit concurrent S3 calls.
        Returns {doc_id: bytes}.
        """
        if semaphore is None:
            semaphore = asyncio.Semaphore(ASYNC_CONCURRENCY_LIMIT)

        try:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
            s3 = get_smart_docs_s3_service()
            if not s3.is_available:
                return {}
        except ImportError:
            return {}

        results: Dict[int, bytes] = {}

        async def _fetch_one(doc: Dict[str, Any]) -> None:
            doc_id = doc.get("id")
            file_location = doc.get("file_location")
            if not doc_id or not file_location:
                return

            async with semaphore:
                try:
                    # Run synchronous S3 download in executor
                    loop = asyncio.get_event_loop()
                    download_result = await loop.run_in_executor(
                        None, s3.download_file, file_location
                    )
                    if download_result.get("success"):
                        results[doc_id] = download_result["content"]
                    else:
                        logger.warning(
                            "file_fetch_failed doc_id=%s error=%s",
                            doc_id, download_result.get("error"),
                        )
                except Exception as e:
                    logger.warning(
                        "file_fetch_error doc_id=%s error=%s",
                        doc_id, str(e),
                    )

        tasks = [_fetch_one(doc) for doc in documents]
        await asyncio.gather(*tasks, return_exceptions=True)

        return results

    # ------------------------------------------------------------------
    # Public: Export operations
    # ------------------------------------------------------------------

    async def export_org_data(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        export_format: ExportFormat = ExportFormat.JSON,
        options: Optional[ExportOptions] = None,
    ) -> ExportJob:
        """
        Export all Smart Docs data for an organization.

        Includes documents, metadata, and optionally audit trail.
        Large exports run as background jobs with S3 upload.

        Args:
            db: Database session.
            org_id: Organization ID (tenant isolation).
            user_id: User initiating the export.
            export_format: Output format (JSON, CSV, ZIP).
            options: Export configuration.

        Returns:
            ExportJob with status and download URL (when complete).

        Raises:
            ExportConcurrencyLimitError: If org has too many active jobs.
            ExportSizeLimitError: If export exceeds size limits.
        """
        if options is None:
            options = ExportOptions()

        job_id = self._generate_job_id()

        # Fetch documents
        documents = self._fetch_org_documents(db, org_id, options)

        if len(documents) > MAX_DOCS_PER_EXPORT:
            raise ExportSizeLimitError(len(documents), MAX_DOCS_PER_EXPORT)

        # Create tracking job
        export_job = ExportJob(
            job_id=job_id,
            org_id=org_id,
            scope=ExportScope.FULL_ORG,
            export_format=export_format,
            status=ExportJobStatus.RUNNING,
            total_items=len(documents),
            created_by_user_id=user_id,
            options={
                "redact_pii": options.redact_pii,
                "encrypt_output": options.encrypt_output,
                "include_audit_trail": options.include_audit_trail,
            },
        )
        self._active_jobs[job_id] = export_job

        try:
            # Build export data
            export_data: Dict[str, Any] = {
                "export_version": "2.0",
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "org_id": org_id,
                "scope": ExportScope.FULL_ORG.value,
                "document_count": len(documents),
                "documents": documents,
            }

            if options.include_audit_trail:
                export_data["audit_trail"] = self._fetch_audit_trail(
                    db, org_id,
                    date_start=options.date_range_start,
                    date_end=options.date_range_end,
                )

            # Serialize based on format
            if export_format == ExportFormat.JSON:
                content = self._serialize_json(export_data, redact_pii=options.redact_pii)
                filename = f"org_{org_id}_export_{job_id}.json"
                content_type = "application/json"

            elif export_format == ExportFormat.CSV:
                content = self._serialize_csv(documents, redact_pii=options.redact_pii)
                filename = f"org_{org_id}_export_{job_id}.csv"
                content_type = "text/csv"

            elif export_format == ExportFormat.ZIP:
                file_contents = await self._fetch_file_contents(documents)
                content = self._build_zip_package(
                    documents=documents,
                    metadata=export_data,
                    file_contents=file_contents,
                    redact_pii=options.redact_pii,
                    watermark_text=options.watermark_text,
                )
                filename = f"org_{org_id}_export_{job_id}.zip"
                content_type = "application/zip"

            else:
                content = self._serialize_json(export_data, redact_pii=options.redact_pii)
                filename = f"org_{org_id}_export_{job_id}.json"
                content_type = "application/json"

            # Calculate hash
            file_hash = hashlib.sha256(content).hexdigest()

            # Upload to S3
            download_url = self._upload_export_to_s3(
                org_id, job_id, content, filename, content_type
            )

            # Encrypt if requested
            if options.encrypt_output:
                content = self._encrypt_export(content)

            # Update job status
            export_job.status = ExportJobStatus.COMPLETED
            export_job.processed_items = len(documents)
            export_job.file_size_bytes = len(content)
            export_job.file_hash = file_hash
            export_job.download_url = download_url
            export_job.download_expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=DOWNLOAD_LINK_EXPIRY_SECONDS)
            )
            export_job.completed_at = datetime.now(timezone.utc)

            # Log audit trail
            self._log_export_audit(
                db, org_id, user_id, job_id,
                scope=ExportScope.FULL_ORG.value,
                export_format=export_format.value,
                item_count=len(documents),
                pii_redacted=options.redact_pii,
                encrypted=options.encrypt_output,
            )

            db.commit()

            logger.info(
                "export_org_completed job_id=%s org_id=%s docs=%s size=%s",
                job_id, org_id, len(documents), len(content),
            )

        except Exception as e:
            export_job.status = ExportJobStatus.FAILED
            export_job.error = str(e)
            export_job.completed_at = datetime.now(timezone.utc)
            logger.exception(
                "export_org_failed job_id=%s org_id=%s error=%s",
                job_id, org_id, str(e),
            )

        return export_job

    async def export_loan_package(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        loan_id: int,
        export_format: ExportFormat = ExportFormat.ZIP,
        options: Optional[ExportOptions] = None,
    ) -> ExportJob:
        """
        Export all documents and metadata for a specific loan.

        Args:
            db: Database session.
            org_id: Organization ID (tenant isolation).
            user_id: User initiating the export.
            loan_id: Target loan ID.
            export_format: Output format.
            options: Export configuration.

        Returns:
            ExportJob with status and download URL.

        Raises:
            DataExportImportError: If loan not found or access denied.
        """
        if options is None:
            options = ExportOptions()

        # Verify loan belongs to org
        loan_meta = self._fetch_loan_metadata(db, org_id, loan_id)
        if loan_meta is None:
            raise DataExportImportError(
                f"Loan {loan_id} not found in organization {org_id}.",
                code="LOAN_NOT_FOUND",
            )

        job_id = self._generate_job_id()

        # Fetch documents for this loan
        documents = self._fetch_org_documents(db, org_id, options, loan_id=loan_id)

        export_job = ExportJob(
            job_id=job_id,
            org_id=org_id,
            scope=ExportScope.LOAN,
            export_format=export_format,
            status=ExportJobStatus.RUNNING,
            total_items=len(documents),
            created_by_user_id=user_id,
            metadata={"loan_id": loan_id, "loan_number": loan_meta.get("loan_number")},
        )
        self._active_jobs[job_id] = export_job

        try:
            export_data = {
                "export_version": "2.0",
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "org_id": org_id,
                "scope": ExportScope.LOAN.value,
                "loan": loan_meta,
                "document_count": len(documents),
                "documents": documents,
            }

            if options.include_audit_trail:
                export_data["audit_trail"] = self._fetch_audit_trail(
                    db, org_id, loan_id=loan_id,
                )

            file_contents: Dict[int, bytes] = {}
            if export_format in (ExportFormat.ZIP, ExportFormat.PDF):
                file_contents = await self._fetch_file_contents(documents)

            if export_format == ExportFormat.JSON:
                content = self._serialize_json(export_data, redact_pii=options.redact_pii)
                filename = f"loan_{loan_id}_export_{job_id}.json"
                content_type = "application/json"

            elif export_format == ExportFormat.CSV:
                content = self._serialize_csv(documents, redact_pii=options.redact_pii)
                filename = f"loan_{loan_id}_export_{job_id}.csv"
                content_type = "text/csv"

            elif export_format == ExportFormat.ZIP:
                content = self._build_zip_package(
                    documents=documents,
                    metadata=export_data,
                    file_contents=file_contents,
                    redact_pii=options.redact_pii,
                    watermark_text=options.watermark_text,
                )
                filename = f"loan_{loan_id}_export_{job_id}.zip"
                content_type = "application/zip"

            elif export_format == ExportFormat.MISMO_XML:
                content = self._generate_mismo_xml(db, org_id, loan_id)
                filename = f"loan_{loan_id}_mismo_{job_id}.xml"
                content_type = "application/xml"

            elif export_format == ExportFormat.PDF:
                content = self._generate_pdf_package(
                    documents=documents,
                    file_contents=file_contents,
                    metadata=export_data,
                    watermark_text=options.watermark_text,
                )
                filename = f"loan_{loan_id}_package_{job_id}.pdf"
                content_type = "application/pdf"

            else:
                content = self._serialize_json(export_data, redact_pii=options.redact_pii)
                filename = f"loan_{loan_id}_export_{job_id}.json"
                content_type = "application/json"

            file_hash = hashlib.sha256(content).hexdigest()

            download_url = self._upload_export_to_s3(
                org_id, job_id, content, filename, content_type
            )

            export_job.status = ExportJobStatus.COMPLETED
            export_job.processed_items = len(documents)
            export_job.file_size_bytes = len(content)
            export_job.file_hash = file_hash
            export_job.download_url = download_url
            export_job.download_expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=DOWNLOAD_LINK_EXPIRY_SECONDS)
            )
            export_job.completed_at = datetime.now(timezone.utc)

            self._log_export_audit(
                db, org_id, user_id, job_id,
                scope=ExportScope.LOAN.value,
                export_format=export_format.value,
                item_count=len(documents),
                pii_redacted=options.redact_pii,
                encrypted=options.encrypt_output,
                metadata={"loan_id": loan_id},
            )

            db.commit()

            logger.info(
                "export_loan_completed job_id=%s org_id=%s loan_id=%s docs=%s",
                job_id, org_id, loan_id, len(documents),
            )

        except Exception as e:
            export_job.status = ExportJobStatus.FAILED
            export_job.error = str(e)
            export_job.completed_at = datetime.now(timezone.utc)
            logger.exception(
                "export_loan_failed job_id=%s org_id=%s loan_id=%s error=%s",
                job_id, org_id, loan_id, str(e),
            )

        return export_job

    async def create_regulatory_package(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        package_type: RegulatoryPackageType,
        request_config: Dict[str, Any],
    ) -> ExportJob:
        """
        Create a regulatory data package for examination or due diligence.

        Regulatory packages always include audit trails and use structured
        formats appropriate for the requesting authority.

        Args:
            db: Database session.
            org_id: Organization ID.
            user_id: User initiating the export.
            package_type: Type of regulatory package.
            request_config: Configuration for the package.
                - loan_ids: Optional list of loan IDs to include.
                - date_range_start: Start date for data range.
                - date_range_end: End date for data range.
                - include_documents: Whether to include document files.
                - examiner_reference: External reference number.

        Returns:
            ExportJob tracking the package creation.
        """
        job_id = self._generate_job_id()

        loan_ids = request_config.get("loan_ids")
        date_start_str = request_config.get("date_range_start")
        date_end_str = request_config.get("date_range_end")
        include_docs = request_config.get("include_documents", True)
        examiner_ref = request_config.get("examiner_reference")

        date_start = (
            datetime.fromisoformat(date_start_str) if date_start_str else None
        )
        date_end = (
            datetime.fromisoformat(date_end_str) if date_end_str else None
        )

        options = ExportOptions(
            redact_pii=False,  # Regulatory packages need full PII
            include_metadata=True,
            include_audit_trail=True,
            date_range_start=date_start,
            date_range_end=date_end,
            loan_ids=loan_ids,
        )

        # Fetch all relevant data
        documents = self._fetch_org_documents(db, org_id, options)
        audit_trail = self._fetch_audit_trail(
            db, org_id,
            date_start=date_start,
            date_end=date_end,
        )

        # Fetch loan metadata for each unique loan
        loan_ids_in_docs = list({
            d["loan_id"] for d in documents if d.get("loan_id")
        })
        loan_metadata = {}
        for lid in loan_ids_in_docs:
            meta = self._fetch_loan_metadata(db, org_id, lid)
            if meta:
                loan_metadata[lid] = meta

        export_job = ExportJob(
            job_id=job_id,
            org_id=org_id,
            scope=ExportScope.REGULATORY,
            export_format=ExportFormat.ZIP,
            status=ExportJobStatus.RUNNING,
            total_items=len(documents),
            created_by_user_id=user_id,
            metadata={
                "package_type": package_type.value,
                "examiner_reference": examiner_ref,
                "loan_count": len(loan_ids_in_docs),
            },
        )
        self._active_jobs[job_id] = export_job

        try:
            # Build comprehensive regulatory package data
            package_data = {
                "export_version": "2.0",
                "package_type": package_type.value,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "org_id": org_id,
                "examiner_reference": examiner_ref,
                "scope": ExportScope.REGULATORY.value,
                "date_range": {
                    "start": date_start.isoformat() if date_start else None,
                    "end": date_end.isoformat() if date_end else None,
                },
                "summary": {
                    "total_loans": len(loan_ids_in_docs),
                    "total_documents": len(documents),
                    "total_audit_records": len(audit_trail),
                },
                "loans": loan_metadata,
                "documents": documents,
                "audit_trail": audit_trail,
                "chain_of_custody": {
                    "generated_by_user_id": user_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "package_type": package_type.value,
                    "integrity_method": "SHA-256",
                },
            }

            file_contents: Dict[int, bytes] = {}
            if include_docs:
                file_contents = await self._fetch_file_contents(documents)

            content = self._build_zip_package(
                documents=documents,
                metadata=package_data,
                file_contents=file_contents,
                redact_pii=False,
            )

            file_hash = hashlib.sha256(content).hexdigest()
            package_data["chain_of_custody"]["package_hash"] = file_hash

            # Re-serialize with hash included in manifest
            content = self._build_zip_package(
                documents=documents,
                metadata=package_data,
                file_contents=file_contents,
                redact_pii=False,
            )

            filename = f"regulatory_{package_type.value}_{job_id}.zip"
            download_url = self._upload_export_to_s3(
                org_id, job_id, content, filename, "application/zip"
            )

            export_job.status = ExportJobStatus.COMPLETED
            export_job.processed_items = len(documents)
            export_job.file_size_bytes = len(content)
            export_job.file_hash = file_hash
            export_job.download_url = download_url
            export_job.download_expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=DOWNLOAD_LINK_EXPIRY_SECONDS)
            )
            export_job.completed_at = datetime.now(timezone.utc)

            self._log_export_audit(
                db, org_id, user_id, job_id,
                scope=ExportScope.REGULATORY.value,
                export_format=ExportFormat.ZIP.value,
                item_count=len(documents),
                pii_redacted=False,
                encrypted=False,
                metadata={
                    "package_type": package_type.value,
                    "examiner_reference": examiner_ref,
                },
            )

            db.commit()

            logger.info(
                "regulatory_package_completed job_id=%s org_id=%s type=%s docs=%s",
                job_id, org_id, package_type.value, len(documents),
            )

        except Exception as e:
            export_job.status = ExportJobStatus.FAILED
            export_job.error = str(e)
            export_job.completed_at = datetime.now(timezone.utc)
            logger.exception(
                "regulatory_package_failed job_id=%s org_id=%s error=%s",
                job_id, org_id, str(e),
            )

        return export_job

    # ------------------------------------------------------------------
    # Public: Import operations
    # ------------------------------------------------------------------

    async def import_documents(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        import_file: bytes,
        manifest: Optional[Dict[str, Any]] = None,
    ) -> ImportJob:
        """
        Import documents from a ZIP file with an optional manifest.

        The ZIP may contain:
            - A manifest.json describing documents and their metadata
            - Document files referenced by the manifest
            - Or just document files (auto-classified if no manifest)

        Args:
            db: Database session.
            org_id: Organization ID (tenant isolation).
            user_id: User performing the import.
            import_file: Raw bytes of the ZIP file.
            manifest: Optional pre-parsed manifest (overrides manifest.json in ZIP).

        Returns:
            ImportJob with status and results.

        Raises:
            DataExportImportError: If import file is invalid or too large.
            ImportValidationError: If manifest fails validation.
        """
        if len(import_file) > MAX_IMPORT_SIZE_BYTES:
            raise DataExportImportError(
                f"Import file is {len(import_file) / (1024 * 1024):.1f} MB -- "
                f"maximum is {MAX_IMPORT_SIZE_BYTES / (1024 * 1024):.0f} MB.",
                code="IMPORT_TOO_LARGE",
            )

        # Parse ZIP
        try:
            zf = zipfile.ZipFile(io.BytesIO(import_file))
        except zipfile.BadZipFile:
            raise DataExportImportError("Invalid ZIP file.", code="INVALID_ZIP")

        # Extract or use provided manifest
        if manifest is None:
            try:
                manifest_bytes = zf.read("manifest.json")
                manifest = json.loads(manifest_bytes.decode("utf-8"))
            except KeyError:
                # No manifest -- create one from ZIP contents
                manifest = self._infer_manifest_from_zip(zf)
            except json.JSONDecodeError:
                raise DataExportImportError(
                    "manifest.json is not valid JSON.",
                    code="INVALID_MANIFEST",
                )

        # Validate manifest
        doc_entries = manifest.get("documents", [])
        if not doc_entries:
            raise DataExportImportError(
                "Manifest contains no document entries.",
                code="EMPTY_MANIFEST",
            )

        if len(doc_entries) > MAX_IMPORT_ITEMS:
            raise DataExportImportError(
                f"Import contains {len(doc_entries)} items, exceeding "
                f"maximum of {MAX_IMPORT_ITEMS}.",
                code="TOO_MANY_ITEMS",
            )

        job_id = self._generate_job_id()

        import_job = ImportJob(
            job_id=job_id,
            org_id=org_id,
            mode=ImportMode.BULK_DOCUMENTS,
            status=ExportJobStatus.RUNNING,
            total_items=len(doc_entries),
            created_by_user_id=user_id,
        )
        self._active_jobs[job_id] = import_job

        Document, _, _, _ = _get_models()
        semaphore = asyncio.Semaphore(ASYNC_CONCURRENCY_LIMIT)

        try:
            for idx, entry in enumerate(doc_entries):
                # Rate limit
                if idx > 0 and ITEM_RATE_LIMIT_SECONDS > 0:
                    await asyncio.sleep(ITEM_RATE_LIMIT_SECONDS)

                try:
                    archive_path = entry.get("archive_path") or entry.get("filename")
                    if not archive_path:
                        import_job.skipped_items += 1
                        import_job.errors.append({
                            "item_index": idx,
                            "error": "No archive_path or filename specified",
                        })
                        continue

                    # Read file from ZIP
                    try:
                        file_bytes = zf.read(archive_path)
                    except KeyError:
                        # Try without directory prefix
                        base_name = os.path.basename(archive_path)
                        matching = [
                            n for n in zf.namelist()
                            if os.path.basename(n) == base_name
                        ]
                        if matching:
                            file_bytes = zf.read(matching[0])
                        else:
                            import_job.skipped_items += 1
                            import_job.errors.append({
                                "item_index": idx,
                                "filename": archive_path,
                                "error": f"File not found in ZIP: {archive_path}",
                            })
                            continue

                    # Validate file extension
                    _, ext = os.path.splitext(archive_path)
                    if ext.lower() not in ALLOWED_IMPORT_EXTENSIONS:
                        import_job.skipped_items += 1
                        import_job.errors.append({
                            "item_index": idx,
                            "filename": archive_path,
                            "error": f"Unsupported file type: {ext}",
                        })
                        continue

                    # Determine document metadata
                    doc_type = entry.get("doc_type")
                    doc_category = entry.get("doc_category")
                    loan_id = entry.get("loan_id")
                    borrower_id = entry.get("borrower_id")
                    filename = entry.get("filename") or os.path.basename(archive_path)
                    mime_type = entry.get("mime_type") or self._guess_mime_type(filename)

                    # Duplicate detection
                    existing = (
                        db.query(Document)
                        .filter(
                            Document.organization_id == org_id,
                            Document.loan_id == loan_id,
                            Document.filename == filename,
                            Document.file_size == len(file_bytes),
                            Document.status == "active",
                        )
                        .first()
                    )

                    if existing:
                        import_job.skipped_items += 1
                        import_job.errors.append({
                            "item_index": idx,
                            "filename": filename,
                            "error": f"Duplicate detected: existing doc_id={existing.id}",
                            "severity": "warning",
                        })
                        continue

                    # Upload to S3
                    storage_key = await self._upload_import_file(
                        org_id, loan_id, borrower_id, filename, file_bytes, mime_type,
                        semaphore=semaphore,
                    )

                    # Create document record
                    new_doc = Document(
                        organization_id=org_id,
                        borrower_id=borrower_id,
                        loan_id=loan_id,
                        doc_type=doc_type,
                        doc_category=doc_category,
                        filename=filename,
                        original_filename=entry.get("original_filename", filename),
                        file_size=len(file_bytes),
                        mime_type=mime_type,
                        file_location=storage_key or f"import/{job_id}/{filename}",
                        source="IMPORT",
                        status="active",
                        notes=entry.get("notes"),
                        uploaded_by_user_id=user_id,
                    )

                    if entry.get("period_start_date"):
                        try:
                            new_doc.period_start_date = date.fromisoformat(
                                entry["period_start_date"]
                            )
                        except (ValueError, TypeError):
                            pass

                    if entry.get("period_end_date"):
                        try:
                            new_doc.period_end_date = date.fromisoformat(
                                entry["period_end_date"]
                            )
                        except (ValueError, TypeError):
                            pass

                    db.add(new_doc)
                    db.flush()

                    import_job.processed_items += 1

                except Exception as e:
                    import_job.failed_items += 1
                    import_job.errors.append({
                        "item_index": idx,
                        "filename": entry.get("filename", "unknown"),
                        "error": str(e),
                    })
                    logger.warning(
                        "import_item_failed job_id=%s idx=%s error=%s",
                        job_id, idx, str(e),
                    )

            import_job.status = ExportJobStatus.COMPLETED
            import_job.completed_at = datetime.now(timezone.utc)

            db.commit()

            logger.info(
                "import_documents_completed job_id=%s org_id=%s "
                "processed=%s failed=%s skipped=%s",
                job_id, org_id,
                import_job.processed_items,
                import_job.failed_items,
                import_job.skipped_items,
            )

        except Exception as e:
            import_job.status = ExportJobStatus.FAILED
            import_job.error = str(e)
            import_job.completed_at = datetime.now(timezone.utc)
            db.rollback()
            logger.exception(
                "import_documents_failed job_id=%s org_id=%s error=%s",
                job_id, org_id, str(e),
            )

        return import_job

    async def import_configuration(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        config_data: Dict[str, Any],
    ) -> ImportResult:
        """
        Import configuration data (rules, templates, workflows, SLAs) from
        another organization or a backup.

        Configuration is validated before import. Existing configurations
        are updated; new ones are created.

        Args:
            db: Database session.
            org_id: Target organization ID.
            user_id: User performing the import.
            config_data: Configuration data dict with sections:
                - business_rules: List of business rule definitions.
                - notification_templates: List of notification templates.
                - sla_configs: List of SLA configurations.
                - workflow_rules: List of workflow rules.

        Returns:
            ImportResult with counts and any errors.
        """
        warnings: List[str] = []
        errors: List[Dict[str, Any]] = []
        imported_count = 0
        skipped_count = 0
        total_count = 0

        # Process each configuration section
        for section_name in [
            "business_rules", "notification_templates",
            "sla_configs", "workflow_rules",
        ]:
            section_data = config_data.get(section_name, [])
            if not section_data:
                continue

            # Resolve table name via strict whitelist (not f-string)
            table_name = _CONFIG_TABLE_MAP.get(section_name)
            if table_name is None:
                errors.append({
                    "section": section_name,
                    "error": f"Unknown configuration section: {section_name}",
                })
                continue
            # Defense-in-depth: even whitelisted table names must be safe identifiers
            if not _SAFE_IDENTIFIER_RE.fullmatch(table_name):
                errors.append({
                    "section": section_name,
                    "error": f"Invalid table name in whitelist: {table_name}",
                })
                continue

            total_count += len(section_data)

            for idx, item in enumerate(section_data):
                try:
                    # Validate required fields
                    if not item.get("name"):
                        errors.append({
                            "section": section_name,
                            "item_index": idx,
                            "error": "Missing required field: name",
                        })
                        skipped_count += 1
                        continue

                    # Override org_id to ensure tenant isolation
                    item["organization_id"] = org_id
                    item["imported_by_user_id"] = user_id
                    item["imported_at"] = datetime.now(timezone.utc).isoformat()

                    # Validate column names against whitelist to prevent
                    # SQL injection via user-controlled JSON keys
                    valid_cols, rejected_cols = _validate_column_names(
                        set(item.keys()), section_name
                    )
                    if rejected_cols:
                        errors.append({
                            "section": section_name,
                            "item_index": idx,
                            "item_name": item.get("name", "unknown"),
                            "error": (
                                f"Invalid column names rejected: "
                                f"{', '.join(sorted(rejected_cols))}"
                            ),
                        })
                        skipped_count += 1
                        continue

                    # Check for existing configuration with same name.
                    # table_name is from _CONFIG_TABLE_MAP (hardcoded whitelist).
                    existing = db.execute(
                        text(
                            f"SELECT id FROM {table_name} "
                            f"WHERE organization_id = :org_id AND name = :name "
                            f"LIMIT 1"
                        ),
                        {"org_id": org_id, "name": item["name"]},
                    ).fetchone()

                    if existing:
                        warnings.append(
                            f"{section_name}: '{item['name']}' already exists "
                            f"(id={existing[0]}), skipping"
                        )
                        skipped_count += 1
                        continue

                    # Insert new configuration using only validated columns.
                    # valid_cols are verified against _CONFIG_COLUMN_WHITELIST
                    # and _SAFE_IDENTIFIER_RE — safe for SQL interpolation.
                    safe_item = {k: item[k] for k in valid_cols}
                    columns = ", ".join(safe_item.keys())
                    placeholders = ", ".join(f":{k}" for k in safe_item.keys())
                    db.execute(
                        text(
                            f"INSERT INTO {table_name} "
                            f"({columns}) VALUES ({placeholders})"
                        ),
                        safe_item,
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append({
                        "section": section_name,
                        "item_index": idx,
                        "item_name": item.get("name", "unknown"),
                        "error": str(e),
                    })
                    skipped_count += 1
                    logger.warning(
                        "config_import_item_failed section=%s idx=%s error=%s",
                        section_name, idx, str(e),
                    )

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            return ImportResult(
                success=False,
                total_items=total_count,
                imported_items=0,
                failed_items=total_count,
                skipped_items=0,
                errors=[{"error": f"Database commit failed: {str(e)}"}],
                warnings=warnings,
                summary={"sections_attempted": list(config_data.keys())},
            )

        logger.info(
            "config_import_completed org_id=%s imported=%s skipped=%s",
            org_id, imported_count, skipped_count,
        )

        return ImportResult(
            success=len(errors) == 0,
            total_items=total_count,
            imported_items=imported_count,
            failed_items=len(errors),
            skipped_items=skipped_count,
            errors=errors,
            warnings=warnings,
            summary={
                "sections_processed": list(config_data.keys()),
                "imported": imported_count,
                "skipped": skipped_count,
            },
        )

    # ------------------------------------------------------------------
    # Public: Validation
    # ------------------------------------------------------------------

    def validate_import(
        self,
        db: Session,
        org_id: int,
        import_data: Union[bytes, Dict[str, Any]],
        import_mode: ImportMode = ImportMode.BULK_DOCUMENTS,
    ) -> ValidationResult:
        """
        Validate import data before executing the import.

        Performs schema validation, duplicate detection, referential integrity
        checks, file format validation, and size/count limit checks.

        Args:
            db: Database session.
            org_id: Organization ID.
            import_data: Raw bytes (ZIP) or parsed dict (manifest/config).
            import_mode: Type of import being validated.

        Returns:
            ValidationResult with issues found.
        """
        issues: List[ValidationIssue] = []
        total_items = 0
        valid_items = 0

        if import_mode == ImportMode.BULK_DOCUMENTS:
            issues, total_items, valid_items = self._validate_document_import(
                db, org_id, import_data
            )
        elif import_mode == ImportMode.CONFIGURATION:
            if not isinstance(import_data, dict):
                issues.append(ValidationIssue(
                    severity="error",
                    code="INVALID_FORMAT",
                    message="Configuration import requires a JSON dict.",
                ))
                return ValidationResult(
                    is_valid=False, total_items=0, valid_items=0, issues=issues
                )
            issues, total_items, valid_items = self._validate_config_import(
                db, org_id, import_data
            )
        elif import_mode == ImportMode.MIGRATION:
            if isinstance(import_data, bytes):
                issues, total_items, valid_items = self._validate_migration_import(
                    db, org_id, import_data
                )
            else:
                issues.append(ValidationIssue(
                    severity="error",
                    code="INVALID_FORMAT",
                    message="Migration import requires a ZIP file (bytes).",
                ))
        elif import_mode == ImportMode.SPREADSHEET:
            if isinstance(import_data, bytes):
                issues, total_items, valid_items = self._validate_spreadsheet_import(
                    db, org_id, import_data
                )
            else:
                issues.append(ValidationIssue(
                    severity="error",
                    code="INVALID_FORMAT",
                    message="Spreadsheet import requires file bytes.",
                ))

        has_errors = any(i.severity == "error" for i in issues)

        return ValidationResult(
            is_valid=not has_errors,
            total_items=total_items,
            valid_items=valid_items,
            issues=issues,
        )

    def _validate_document_import(
        self,
        db: Session,
        org_id: int,
        import_data: Union[bytes, Dict[str, Any]],
    ) -> Tuple[List[ValidationIssue], int, int]:
        """Validate a document import ZIP."""
        issues: List[ValidationIssue] = []
        total_items = 0
        valid_items = 0

        # Parse ZIP
        if isinstance(import_data, bytes):
            if len(import_data) > MAX_IMPORT_SIZE_BYTES:
                issues.append(ValidationIssue(
                    severity="error",
                    code="FILE_TOO_LARGE",
                    message=(
                        f"File size {len(import_data) / (1024 * 1024):.1f} MB exceeds "
                        f"maximum {MAX_IMPORT_SIZE_BYTES / (1024 * 1024):.0f} MB."
                    ),
                ))
                return issues, 0, 0

            try:
                zf = zipfile.ZipFile(io.BytesIO(import_data))
            except zipfile.BadZipFile:
                issues.append(ValidationIssue(
                    severity="error",
                    code="INVALID_ZIP",
                    message="File is not a valid ZIP archive.",
                ))
                return issues, 0, 0

            # Try to read manifest
            try:
                manifest_bytes = zf.read("manifest.json")
                manifest = json.loads(manifest_bytes.decode("utf-8"))
            except KeyError:
                manifest = self._infer_manifest_from_zip(zf)
                issues.append(ValidationIssue(
                    severity="warning",
                    code="NO_MANIFEST",
                    message="No manifest.json found; metadata inferred from filenames.",
                ))
            except json.JSONDecodeError:
                issues.append(ValidationIssue(
                    severity="error",
                    code="INVALID_MANIFEST",
                    message="manifest.json is not valid JSON.",
                ))
                return issues, 0, 0
        elif isinstance(import_data, dict):
            manifest = import_data
            zf = None
        else:
            issues.append(ValidationIssue(
                severity="error",
                code="INVALID_FORMAT",
                message="Import data must be bytes (ZIP) or dict (manifest).",
            ))
            return issues, 0, 0

        doc_entries = manifest.get("documents", [])
        total_items = len(doc_entries)

        if total_items == 0:
            issues.append(ValidationIssue(
                severity="error",
                code="EMPTY_MANIFEST",
                message="No document entries found in manifest.",
            ))
            return issues, 0, 0

        if total_items > MAX_IMPORT_ITEMS:
            issues.append(ValidationIssue(
                severity="error",
                code="TOO_MANY_ITEMS",
                message=(
                    f"Manifest contains {total_items} items, exceeding "
                    f"maximum of {MAX_IMPORT_ITEMS}."
                ),
            ))

        Document, _, _, _ = _get_models()

        # Validate each entry
        seen_filenames: Set[str] = set()
        for idx, entry in enumerate(doc_entries):
            entry_valid = True
            filename = entry.get("filename") or entry.get("archive_path")

            # Required fields
            if not filename:
                issues.append(ValidationIssue(
                    severity="error",
                    code="MISSING_FILENAME",
                    message="Entry missing filename.",
                    item_index=idx,
                ))
                entry_valid = False
                continue

            # File extension check
            _, ext = os.path.splitext(filename)
            if ext.lower() not in ALLOWED_IMPORT_EXTENSIONS:
                issues.append(ValidationIssue(
                    severity="error",
                    code="UNSUPPORTED_FILE_TYPE",
                    message=f"Unsupported file type: {ext}",
                    item_index=idx,
                    field="filename",
                ))
                entry_valid = False

            # Duplicate detection within manifest
            base_name = os.path.basename(filename)
            if base_name in seen_filenames:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="DUPLICATE_IN_MANIFEST",
                    message=f"Duplicate filename in manifest: {base_name}",
                    item_index=idx,
                    field="filename",
                ))
            seen_filenames.add(base_name)

            # File exists in ZIP
            if zf is not None:
                archive_path = entry.get("archive_path") or filename
                names_in_zip = zf.namelist()
                if archive_path not in names_in_zip:
                    # Check basename match
                    matching = [n for n in names_in_zip if os.path.basename(n) == base_name]
                    if not matching:
                        issues.append(ValidationIssue(
                            severity="error",
                            code="FILE_NOT_IN_ZIP",
                            message=f"File not found in ZIP: {archive_path}",
                            item_index=idx,
                        ))
                        entry_valid = False

            # Duplicate detection in database
            loan_id = entry.get("loan_id")
            if loan_id and filename:
                existing = (
                    db.query(func.count(Document.id))
                    .filter(
                        Document.organization_id == org_id,
                        Document.loan_id == loan_id,
                        Document.filename == base_name,
                        Document.status == "active",
                    )
                    .scalar()
                )
                if existing and existing > 0:
                    issues.append(ValidationIssue(
                        severity="warning",
                        code="DUPLICATE_IN_DB",
                        message=(
                            f"Document '{base_name}' already exists for "
                            f"loan {loan_id}."
                        ),
                        item_index=idx,
                    ))

            # Referential integrity: verify loan belongs to org
            if loan_id:
                Loan = _get_loan_model()
                loan_exists = (
                    db.query(func.count(Loan.id))
                    .filter(Loan.id == loan_id, Loan.organization_id == org_id)
                    .scalar()
                )
                if not loan_exists:
                    issues.append(ValidationIssue(
                        severity="error",
                        code="INVALID_LOAN_ID",
                        message=f"Loan {loan_id} not found in organization.",
                        item_index=idx,
                        field="loan_id",
                    ))
                    entry_valid = False

            if entry_valid:
                valid_items += 1

        return issues, total_items, valid_items

    def _validate_config_import(
        self,
        db: Session,
        org_id: int,
        config_data: Dict[str, Any],
    ) -> Tuple[List[ValidationIssue], int, int]:
        """Validate configuration import data."""
        issues: List[ValidationIssue] = []
        total_items = 0
        valid_items = 0

        for section_name, section_data in config_data.items():
            if section_name not in _CONFIG_TABLE_MAP:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="UNKNOWN_SECTION",
                    message=f"Unknown configuration section: {section_name}",
                ))
                continue

            if not isinstance(section_data, list):
                issues.append(ValidationIssue(
                    severity="error",
                    code="INVALID_SECTION_FORMAT",
                    message=f"Section '{section_name}' must be a list.",
                    field=section_name,
                ))
                continue

            for idx, item in enumerate(section_data):
                total_items += 1
                item_valid = True

                if not isinstance(item, dict):
                    issues.append(ValidationIssue(
                        severity="error",
                        code="INVALID_ITEM_FORMAT",
                        message=f"Item at index {idx} must be a dict.",
                        item_index=idx,
                        field=section_name,
                    ))
                    item_valid = False
                    continue

                if not item.get("name"):
                    issues.append(ValidationIssue(
                        severity="error",
                        code="MISSING_NAME",
                        message=f"Item at index {idx} missing required 'name' field.",
                        item_index=idx,
                        field=section_name,
                    ))
                    item_valid = False

                if item_valid:
                    valid_items += 1

        return issues, total_items, valid_items

    def _validate_migration_import(
        self,
        db: Session,
        org_id: int,
        import_data: bytes,
    ) -> Tuple[List[ValidationIssue], int, int]:
        """Validate a migration import ZIP (legacy system data)."""
        issues: List[ValidationIssue] = []

        try:
            zf = zipfile.ZipFile(io.BytesIO(import_data))
        except zipfile.BadZipFile:
            issues.append(ValidationIssue(
                severity="error",
                code="INVALID_ZIP",
                message="File is not a valid ZIP archive.",
            ))
            return issues, 0, 0

        # Look for migration manifest or mapping file
        has_manifest = "migration_manifest.json" in zf.namelist()
        has_mapping = "type_mapping.json" in zf.namelist()

        if not has_manifest:
            issues.append(ValidationIssue(
                severity="warning",
                code="NO_MIGRATION_MANIFEST",
                message=(
                    "No migration_manifest.json found. Default legacy type "
                    "mappings will be used."
                ),
            ))

        doc_files = [
            name for name in zf.namelist()
            if not name.endswith("/")
            and not name.startswith("__MACOSX")
            and name not in ("migration_manifest.json", "type_mapping.json", "manifest.json")
        ]

        total_items = len(doc_files)
        valid_items = 0

        for idx, name in enumerate(doc_files):
            _, ext = os.path.splitext(name)
            if ext.lower() not in ALLOWED_IMPORT_EXTENSIONS:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="UNSUPPORTED_FILE_TYPE",
                    message=f"Unsupported file type: {name}",
                    item_index=idx,
                ))
            else:
                valid_items += 1

        return issues, total_items, valid_items

    def _validate_spreadsheet_import(
        self,
        db: Session,
        org_id: int,
        import_data: bytes,
    ) -> Tuple[List[ValidationIssue], int, int]:
        """Validate a spreadsheet (CSV) import for document metadata."""
        issues: List[ValidationIssue] = []

        try:
            text_content = import_data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text_content = import_data.decode("latin-1")
                issues.append(ValidationIssue(
                    severity="warning",
                    code="NON_UTF8_ENCODING",
                    message="File is not UTF-8 encoded; using Latin-1 fallback.",
                ))
            except Exception:
                issues.append(ValidationIssue(
                    severity="error",
                    code="ENCODING_ERROR",
                    message="Unable to decode file. Ensure it is UTF-8 or Latin-1 encoded.",
                ))
                return issues, 0, 0

        reader = csv.DictReader(io.StringIO(text_content))
        required_columns = {"filename", "doc_type"}
        if reader.fieldnames is None:
            issues.append(ValidationIssue(
                severity="error",
                code="NO_HEADERS",
                message="CSV file has no header row.",
            ))
            return issues, 0, 0

        actual_columns = set(reader.fieldnames)
        missing_columns = required_columns - actual_columns
        if missing_columns:
            issues.append(ValidationIssue(
                severity="error",
                code="MISSING_COLUMNS",
                message=f"Missing required columns: {', '.join(missing_columns)}",
            ))
            return issues, 0, 0

        rows = list(reader)
        total_items = len(rows)
        valid_items = 0

        for idx, row in enumerate(rows):
            row_valid = True

            if not row.get("filename"):
                issues.append(ValidationIssue(
                    severity="error",
                    code="MISSING_FILENAME",
                    message="Row missing filename.",
                    item_index=idx,
                    field="filename",
                ))
                row_valid = False

            if not row.get("doc_type"):
                issues.append(ValidationIssue(
                    severity="warning",
                    code="MISSING_DOC_TYPE",
                    message="Row missing doc_type; will default to 'Other'.",
                    item_index=idx,
                    field="doc_type",
                ))

            if row_valid:
                valid_items += 1

        return issues, total_items, valid_items

    # ------------------------------------------------------------------
    # Public: Migration support
    # ------------------------------------------------------------------

    async def import_migration(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        migration_file: bytes,
        type_mapping: Optional[Dict[str, str]] = None,
        batch_size: int = 50,
    ) -> ImportJob:
        """
        Import documents from a legacy document management system.

        Supports incremental migration with legacy-to-Smart-Docs type mapping,
        history preservation, and batch processing.

        Args:
            db: Database session.
            org_id: Organization ID.
            user_id: User performing the migration.
            migration_file: ZIP bytes containing legacy documents + manifest.
            type_mapping: Optional custom legacy type -> Smart Docs type mapping.
                Falls back to LEGACY_DOC_TYPE_MAP.
            batch_size: Number of documents to process per batch.

        Returns:
            ImportJob with migration results.
        """
        effective_mapping = dict(LEGACY_DOC_TYPE_MAP)
        if type_mapping:
            effective_mapping.update(type_mapping)

        try:
            zf = zipfile.ZipFile(io.BytesIO(migration_file))
        except zipfile.BadZipFile:
            raise DataExportImportError("Invalid ZIP file.", code="INVALID_ZIP")

        # Load migration manifest if present
        manifest: Dict[str, Any] = {}
        try:
            manifest_bytes = zf.read("migration_manifest.json")
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (KeyError, json.JSONDecodeError):
            manifest = self._infer_manifest_from_zip(zf)

        # Load custom type mapping from ZIP if present
        try:
            mapping_bytes = zf.read("type_mapping.json")
            zip_mapping = json.loads(mapping_bytes.decode("utf-8"))
            effective_mapping.update(zip_mapping)
        except (KeyError, json.JSONDecodeError):
            pass

        doc_entries = manifest.get("documents", [])

        job_id = self._generate_job_id()
        import_job = ImportJob(
            job_id=job_id,
            org_id=org_id,
            mode=ImportMode.MIGRATION,
            status=ExportJobStatus.RUNNING,
            total_items=len(doc_entries),
            created_by_user_id=user_id,
            metadata={
                "batch_size": batch_size,
                "type_mappings_used": len(effective_mapping),
            },
        )
        self._active_jobs[job_id] = import_job

        Document, _, _, _ = _get_models()
        semaphore = asyncio.Semaphore(ASYNC_CONCURRENCY_LIMIT)

        try:
            # Process in batches
            for batch_start in range(0, len(doc_entries), batch_size):
                batch = doc_entries[batch_start:batch_start + batch_size]

                for idx_in_batch, entry in enumerate(batch):
                    idx = batch_start + idx_in_batch

                    try:
                        archive_path = entry.get("archive_path") or entry.get("filename")
                        if not archive_path:
                            import_job.skipped_items += 1
                            continue

                        try:
                            file_bytes = zf.read(archive_path)
                        except KeyError:
                            import_job.skipped_items += 1
                            import_job.errors.append({
                                "item_index": idx,
                                "filename": archive_path,
                                "error": "File not found in ZIP",
                            })
                            continue

                        # Map legacy doc type
                        legacy_type = entry.get("doc_type", "").lower().strip()
                        mapped_type = effective_mapping.get(
                            legacy_type,
                            effective_mapping.get(legacy_type.replace(" ", "_"), "Other"),
                        )

                        filename = entry.get("filename") or os.path.basename(archive_path)
                        mime_type = entry.get("mime_type") or self._guess_mime_type(filename)
                        loan_id = entry.get("loan_id")
                        borrower_id = entry.get("borrower_id")

                        storage_key = await self._upload_import_file(
                            org_id, loan_id, borrower_id, filename, file_bytes, mime_type,
                            semaphore=semaphore,
                        )

                        new_doc = Document(
                            organization_id=org_id,
                            borrower_id=borrower_id,
                            loan_id=loan_id,
                            doc_type=mapped_type,
                            filename=filename,
                            original_filename=entry.get("original_filename", filename),
                            file_size=len(file_bytes),
                            mime_type=mime_type,
                            file_location=storage_key or f"migration/{job_id}/{filename}",
                            source="MIGRATION",
                            status="active",
                            notes=(
                                f"Migrated from legacy system. "
                                f"Original type: {entry.get('doc_type', 'unknown')}"
                            ),
                            uploaded_by_user_id=user_id,
                        )
                        db.add(new_doc)
                        import_job.processed_items += 1

                    except Exception as e:
                        import_job.failed_items += 1
                        import_job.errors.append({
                            "item_index": idx,
                            "filename": entry.get("filename", "unknown"),
                            "error": str(e),
                        })

                # Flush each batch
                db.flush()

                # Brief yield to allow cooperative cancellation
                await asyncio.sleep(0)

            import_job.status = ExportJobStatus.COMPLETED
            import_job.completed_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(
                "migration_import_completed job_id=%s org_id=%s "
                "processed=%s failed=%s skipped=%s",
                job_id, org_id,
                import_job.processed_items,
                import_job.failed_items,
                import_job.skipped_items,
            )

        except Exception as e:
            import_job.status = ExportJobStatus.FAILED
            import_job.error = str(e)
            import_job.completed_at = datetime.now(timezone.utc)
            db.rollback()
            logger.exception(
                "migration_import_failed job_id=%s org_id=%s error=%s",
                job_id, org_id, str(e),
            )

        return import_job

    # ------------------------------------------------------------------
    # Public: Status and history
    # ------------------------------------------------------------------

    def get_export_status(
        self,
        org_id: int,
        job_id: str,
    ) -> Optional[JobStatus]:
        """
        Get the current status of an export or import job.

        Args:
            org_id: Organization ID (for access control).
            job_id: Job identifier.

        Returns:
            JobStatus or None if job not found.
        """
        job = self._active_jobs.get(job_id)
        if job is None:
            return None

        # Verify org access
        if job.org_id != org_id:
            return None

        if isinstance(job, ExportJob):
            return JobStatus(
                job_id=job.job_id,
                status=job.status.value,
                progress_pct=job.progress_pct,
                total_items=job.total_items,
                processed_items=job.processed_items,
                failed_items=job.failed_items,
                error=job.error,
                download_url=job.download_url,
                created_at=job.created_at,
                completed_at=job.completed_at,
            )
        elif isinstance(job, ImportJob):
            return JobStatus(
                job_id=job.job_id,
                status=job.status.value,
                progress_pct=job.progress_pct,
                total_items=job.total_items,
                processed_items=job.processed_items,
                failed_items=job.failed_items,
                error=job.error,
                download_url=None,
                created_at=job.created_at,
                completed_at=job.completed_at,
            )

        return None

    def get_export_history(
        self,
        db: Session,
        org_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ExportRecord]:
        """
        Get export history for an organization from the audit trail.

        Args:
            db: Database session.
            org_id: Organization ID.
            limit: Max records to return.
            offset: Pagination offset.

        Returns:
            List of ExportRecord entries.
        """
        DecisionAuditLog = _get_compliance_models()
        if DecisionAuditLog is None:
            # Return from in-memory jobs if audit model unavailable
            return self._get_history_from_memory(org_id, limit, offset)

        try:
            records = (
                db.query(DecisionAuditLog)
                .filter(
                    DecisionAuditLog.organization_id == org_id,
                    DecisionAuditLog.decision_type == "data_export",
                )
                .order_by(DecisionAuditLog.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )

            results = []
            now = datetime.now(timezone.utc)

            for record in records:
                ctx = record.context or {}
                created_at = record.created_at or now
                download_expires_at = created_at + timedelta(
                    seconds=DOWNLOAD_LINK_EXPIRY_SECONDS
                )

                results.append(ExportRecord(
                    job_id=ctx.get("job_id", "unknown"),
                    scope=ctx.get("scope", "unknown"),
                    export_format=ctx.get("format", "unknown"),
                    status="completed",
                    total_items=ctx.get("item_count", 0),
                    file_size_bytes=ctx.get("file_size_bytes", 0),
                    file_hash=ctx.get("file_hash"),
                    created_by_user_id=(
                        int(record.decision_maker_id)
                        if record.decision_maker_id else None
                    ),
                    created_at=created_at,
                    completed_at=created_at,
                    download_url=None,  # URLs are ephemeral
                    download_expired=now > download_expires_at,
                    pii_redacted=ctx.get("pii_redacted", False),
                    encrypted=ctx.get("encrypted", False),
                ))

            return results

        except Exception as e:
            logger.error(
                "get_export_history_failed org_id=%s error=%s",
                org_id, str(e),
            )
            return self._get_history_from_memory(org_id, limit, offset)

    def _get_history_from_memory(
        self, org_id: int, limit: int, offset: int
    ) -> List[ExportRecord]:
        """Fallback: get export history from in-memory job store."""
        matching = [
            j for j in self._active_jobs.values()
            if isinstance(j, ExportJob)
            and j.org_id == org_id
            and j.status == ExportJobStatus.COMPLETED
        ]
        matching.sort(key=lambda j: j.created_at, reverse=True)

        now = datetime.now(timezone.utc)
        results = []
        for job in matching[offset:offset + limit]:
            download_expired = (
                job.download_expires_at is not None and now > job.download_expires_at
            )
            results.append(ExportRecord(
                job_id=job.job_id,
                scope=job.scope.value,
                export_format=job.export_format.value,
                status=job.status.value,
                total_items=job.total_items,
                file_size_bytes=job.file_size_bytes,
                file_hash=job.file_hash,
                created_by_user_id=job.created_by_user_id,
                created_at=job.created_at,
                completed_at=job.completed_at,
                download_url=job.download_url if not download_expired else None,
                download_expired=download_expired,
                pii_redacted=(job.options or {}).get("redact_pii", False),
                encrypted=(job.options or {}).get("encrypt_output", False),
            ))

        return results

    # ------------------------------------------------------------------
    # Internal: Helpers
    # ------------------------------------------------------------------

    def _infer_manifest_from_zip(self, zf: zipfile.ZipFile) -> Dict[str, Any]:
        """
        Create an inferred manifest from ZIP contents when no manifest.json is
        provided. Assigns doc_type based on filename heuristics.
        """
        entries = []
        for name in zf.namelist():
            # Skip directories, macOS resource forks, and metadata files
            if (
                name.endswith("/")
                or name.startswith("__MACOSX")
                or name in ("manifest.json", "migration_manifest.json", "type_mapping.json")
            ):
                continue

            _, ext = os.path.splitext(name)
            if ext.lower() not in ALLOWED_IMPORT_EXTENSIONS:
                continue

            # Try to guess doc type from filename
            base = os.path.basename(name).lower()
            doc_type = "Other"
            for legacy_key, mapped_type in LEGACY_DOC_TYPE_MAP.items():
                if legacy_key in base:
                    doc_type = mapped_type
                    break

            entries.append({
                "archive_path": name,
                "filename": os.path.basename(name),
                "doc_type": doc_type,
                "mime_type": self._guess_mime_type(name),
            })

        return {
            "export_version": "2.0",
            "inferred": True,
            "documents": entries,
        }

    def _guess_mime_type(self, filename: str) -> str:
        """Guess MIME type from file extension."""
        ext_to_mime = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".json": "application/json",
            ".csv": "text/csv",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xml": "application/xml",
        }
        _, ext = os.path.splitext(filename)
        return ext_to_mime.get(ext.lower(), "application/octet-stream")

    async def _upload_import_file(
        self,
        org_id: int,
        loan_id: Optional[int],
        borrower_id: Optional[int],
        filename: str,
        file_bytes: bytes,
        mime_type: str,
        semaphore: Optional[asyncio.Semaphore] = None,
    ) -> Optional[str]:
        """Upload an imported file to S3. Returns the storage key or None."""
        try:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

            s3 = get_smart_docs_s3_service()
            if not s3.is_available:
                return None

            storage_key = s3.generate_storage_key(
                loan_id=loan_id or 0,
                borrower_id=borrower_id,
                file_name=filename,
                organization_id=org_id,
            )

            if semaphore:
                async with semaphore:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None,
                        lambda: s3.upload_file(file_bytes, storage_key, mime_type),
                    )
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: s3.upload_file(file_bytes, storage_key, mime_type),
                )

            if result.get("success"):
                return storage_key
            else:
                logger.warning(
                    "import_file_upload_failed filename=%s error=%s",
                    filename, result.get("error"),
                )
                return None

        except ImportError:
            return None
        except Exception as e:
            logger.warning(
                "import_file_upload_error filename=%s error=%s",
                filename, str(e),
            )
            return None

    def _encrypt_export(self, content: bytes) -> bytes:
        """
        Encrypt export content using Fernet symmetric encryption.
        Falls back to returning unmodified content if encryption is unavailable.
        """
        try:
            from services.smart_docs.pii_encryption_service import get_pii_encryption_service

            svc = get_pii_encryption_service()
            encrypted = svc.encrypt(content.decode("utf-8", errors="replace"))
            return encrypted.encode("utf-8") if isinstance(encrypted, str) else encrypted

        except ImportError:
            logger.warning("encryption_unavailable: pii_encryption_service not found")
            return content
        except Exception as e:
            logger.warning("encryption_failed: %s, returning unencrypted content", str(e))
            return content


# =============================================================================
# SINGLETON
# =============================================================================

_data_export_import_service: Optional[DataExportImportService] = None


def get_data_export_import_service() -> DataExportImportService:
    """Get or create the DataExportImportService singleton."""
    global _data_export_import_service
    if _data_export_import_service is None:
        _data_export_import_service = DataExportImportService()
    return _data_export_import_service
