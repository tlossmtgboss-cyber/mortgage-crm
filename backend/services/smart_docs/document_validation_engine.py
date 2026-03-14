"""
Document Validation Engine

Rule-based deterministic document validation for mortgage document uploads.
Handles file security, freshness, completeness, PII detection, and duplicate
detection. This is separate from the AI review pipeline -- it runs pure
rule-based checks that do not require any ML/LLM calls.

Usage:
    from services.smart_docs.document_validation_engine import get_document_validation_engine

    engine = get_document_validation_engine()
    result = engine.validate_upload(file_bytes, "paystub_jan.pdf", "application/pdf", "PAYSTUB")
"""

import hashlib
import io
import logging
import os
import re
import struct
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field

from sqlalchemy.orm import Session
from sqlalchemy import text

from middleware.upload_limits import (
    MAX_DOCUMENT_SIZE,
    MAX_IMAGE_SIZE,
    MAX_IMAGE_DIMENSIONS,
    MAX_PDF_PAGES,
    PDF_BOMB_RATIO,
)

logger = logging.getLogger(__name__)


# =============================================================================
# FILE TYPE VALIDATION CONSTANTS
# =============================================================================

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/bmp",
    "image/gif",
    "image/webp",
}

# Magic bytes for file type verification (prefix -> MIME type)
MAGIC_BYTES: Dict[bytes, str] = {
    b"%PDF": "application/pdf",
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"II\x2a\x00": "image/tiff",  # Little-endian TIFF
    b"MM\x00\x2a": "image/tiff",  # Big-endian TIFF
    b"BM": "image/bmp",
    b"GIF8": "image/gif",
    b"RIFF": "image/webp",  # WebP (RIFF container)
}

# Maximum file sizes (bytes)
MAX_FILE_SIZES = {
    "application/pdf": 50 * 1024 * 1024,  # 50 MB
    "image/jpeg": 20 * 1024 * 1024,       # 20 MB
    "image/png": 20 * 1024 * 1024,
    "image/tiff": 100 * 1024 * 1024,      # 100 MB (scanned docs can be large)
    "default": 50 * 1024 * 1024,
}

# Minimum file sizes to detect blank/corrupt uploads
MIN_FILE_SIZES = {
    "application/pdf": 1024,   # 1 KB
    "image/jpeg": 2048,       # 2 KB
    "image/png": 1024,
    "default": 512,
}

# Extensions that must never be accepted
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".pif",
    ".vbs", ".js", ".wsf", ".wsh", ".ps1", ".sh", ".bash",
    ".app", ".action", ".command", ".workflow",
    ".dll", ".sys", ".drv",
    ".html", ".htm", ".svg",  # Could contain scripts
}

# Freshness requirements (days) by doc type string
FRESHNESS_RULES: Dict[str, int] = {
    "PAYSTUB": 30,
    "BANK_STATEMENT": 60,
    "INVESTMENT_STATEMENT": 90,
    "W2": 365,
    "TAX_RETURN": 365,
    "BUSINESS_TAX_RETURN": 365,
    "DRIVERS_LICENSE": 3650,  # 10 years
    "PROFIT_LOSS": 120,
    "BALANCE_SHEET": 120,
}

# Expected page count ranges (min, max) by doc type
EXPECTED_PAGE_COUNTS: Dict[str, Tuple[int, int]] = {
    "W2": (1, 4),
    "PAYSTUB": (1, 4),
    "TAX_RETURN": (2, 50),
    "BUSINESS_TAX_RETURN": (3, 80),
    "BANK_STATEMENT": (2, 30),
    "INVESTMENT_STATEMENT": (2, 30),
    "DRIVERS_LICENSE": (1, 2),
    "GIFT_LETTER": (1, 3),
    "PURCHASE_CONTRACT": (5, 60),
    "APPRAISAL": (10, 80),
    "TITLE_REPORT": (5, 50),
    "PROFIT_LOSS": (1, 10),
    "BALANCE_SHEET": (1, 10),
}

# Required text fields for completeness validation (doc_type -> list of (field_name, patterns))
COMPLETENESS_RULES: Dict[str, List[Tuple[str, List[str]]]] = {
    "PAYSTUB": [
        ("employer_name", [r"employer", r"company", r"corp", r"inc", r"llc", r"ltd"]),
        ("pay_period", [r"pay\s*period", r"period\s*(end|begin)", r"check\s*date", r"pay\s*date"]),
        ("gross_pay", [r"gross\s*pay", r"gross\s*earnings", r"total\s*gross"]),
        ("net_pay", [r"net\s*pay", r"net\s*earnings", r"total\s*net", r"net\s*check"]),
        ("ytd_earnings", [r"ytd", r"year[\s-]*to[\s-]*date"]),
    ],
    "W2": [
        ("employer_ein", [r"employer.*id", r"ein\b", r"\d{2}-\d{7}"]),
        ("wages", [r"wages.*tips", r"box\s*1\b", r"compensation"]),
        ("federal_tax_withheld", [r"federal.*tax.*withheld", r"box\s*2\b"]),
        ("ssn_present", [r"\d{3}-\d{2}-\d{4}", r"xxx-xx-\d{4}", r"social\s*security"]),
    ],
    "BANK_STATEMENT": [
        ("institution_name", [r"bank", r"credit\s*union", r"financial", r"savings"]),
        ("account_number", [r"account\s*(number|no|#)", r"acct\s*(number|no|#)"]),
        ("statement_period", [r"statement\s*period", r"period.*from.*to", r"beginning\s*balance"]),
        ("ending_balance", [r"ending\s*balance", r"closing\s*balance", r"available\s*balance"]),
    ],
    "TAX_RETURN": [
        ("filing_status", [r"filing\s*status", r"single", r"married.*filing", r"head\s*of\s*household"]),
        ("agi", [r"adjusted\s*gross\s*income", r"agi\b", r"line\s*11\b", r"line\s*37\b"]),
        ("tax_year", [r"form\s*1040", r"tax\s*year", r"20\d{2}"]),
    ],
    "BUSINESS_TAX_RETURN": [
        ("business_name", [r"business\s*name", r"company\s*name", r"corporation"]),
        ("ein", [r"employer.*id", r"ein\b", r"\d{2}-\d{7}"]),
        ("tax_year", [r"tax\s*year", r"20\d{2}"]),
    ],
}

# PII patterns to detect
PII_PATTERNS = {
    "full_ssn": (r"\b\d{3}-\d{2}-\d{4}\b", "Full SSN detected - should be redacted"),
    "full_ssn_nohyphens": (r"\b(?<!\d)\d{9}(?!\d)\b", "Possible unformatted SSN detected"),
    "full_account_number": (
        r"\b\d{10,17}\b",
        "Long numeric sequence may be full account number - consider masking",
    ),
    "routing_number": (
        r"\b(?:0[0-9]|1[0-2]|2[1-9]|3[0-2]|6[1-9]|7[0-2]|8[0-9])\d{7}\b",
        "Possible bank routing number detected",
    ),
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ValidationIssue:
    """A single validation issue found."""
    rule: str           # Rule identifier (e.g. FILE_TYPE_BLOCKED)
    severity: str       # CRITICAL, HIGH, MEDIUM, LOW, INFO
    message: str        # Human-readable description
    details: Optional[str] = None
    auto_fixable: bool = False
    fix_instruction: Optional[str] = None


@dataclass
class ValidationResult:
    """Complete validation result for a document."""
    is_valid: bool
    score: int  # 0-100 overall validation score
    issues: List[ValidationIssue] = field(default_factory=list)
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    passed_rules: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Serialize to dict for API responses."""
        return {
            "is_valid": self.is_valid,
            "score": self.score,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "passed_rules": self.passed_rules,
            "issues": [
                {
                    "rule": issue.rule,
                    "severity": issue.severity,
                    "message": issue.message,
                    "details": issue.details,
                    "auto_fixable": issue.auto_fixable,
                    "fix_instruction": issue.fix_instruction,
                }
                for issue in self.issues
            ],
            "metadata": self.metadata,
        }


# =============================================================================
# VALIDATION ENGINE
# =============================================================================

class DocumentValidationEngine:
    """
    Rule-based document validation engine.

    Validates:
    1. File security (type, magic bytes, size, extension, malware indicators)
    2. Document freshness (age vs requirements)
    3. Document completeness (required fields present)
    4. Filename sanitization
    5. Content safety (no embedded scripts, macros)
    6. Page count validation
    7. Duplicate detection
    8. PII protection rules
    """

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def validate_upload(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        declared_doc_type: Optional[str] = None,
    ) -> ValidationResult:
        """
        Run all upload-time validations and return a comprehensive result.

        Args:
            file_content: Raw file bytes.
            filename: Original filename as submitted by the client.
            mime_type: Declared MIME type (e.g. from Content-Type header).
            declared_doc_type: Declared document category (e.g. PAYSTUB, W2).

        Returns:
            ValidationResult with score, issues, and metadata.
        """
        all_issues: List[ValidationIssue] = []
        passed_rules: List[str] = []

        # 0. Hard size limit check (before any other processing)
        hard_limit_issues = self._validate_hard_size_limit(file_content, mime_type)
        if hard_limit_issues:
            all_issues.extend(hard_limit_issues)
            # If hard limit is exceeded, skip further processing to avoid DoS
            return self._build_result(all_issues, passed_rules, {
                "file_size": len(file_content),
                "declared_mime_type": mime_type,
                "rejected_early": True,
            })

        # 1. File type checks
        type_issues = self.validate_file_type(file_content, filename, mime_type)
        if type_issues:
            all_issues.extend(type_issues)
        else:
            passed_rules.append("FILE_TYPE")

        # 2. File size checks
        size_issues = self.validate_file_size(file_content, mime_type)
        if size_issues:
            all_issues.extend(size_issues)
        else:
            passed_rules.append("FILE_SIZE")

        # 3. Image dimension check (before loading into PIL or OCR)
        if mime_type.startswith("image/"):
            dim_issues = self._validate_image_dimensions(file_content)
            if dim_issues:
                all_issues.extend(dim_issues)
            else:
                passed_rules.append("IMAGE_DIMENSIONS")

        # 4. PDF-specific: page count hard limit and bomb detection
        if mime_type == "application/pdf":
            pdf_limit_issues = self._validate_pdf_limits(file_content)
            if pdf_limit_issues:
                all_issues.extend(pdf_limit_issues)
            else:
                passed_rules.append("PDF_LIMITS")

        # 5. Content safety (PDF or image)
        if mime_type == "application/pdf":
            safety_issues = self.validate_pdf_safety(file_content)
        elif mime_type.startswith("image/"):
            safety_issues = self.validate_image_safety(file_content)
        else:
            safety_issues = []

        if safety_issues:
            all_issues.extend(safety_issues)
        else:
            passed_rules.append("CONTENT_SAFETY")

        # 6. Page count validation (if doc type declared)
        if declared_doc_type:
            page_issues = self.validate_page_count(file_content, mime_type, declared_doc_type)
            if page_issues:
                all_issues.extend(page_issues)
            else:
                passed_rules.append("PAGE_COUNT")

        # 7. Filename sanitization produces no issues itself, but we record it
        sanitized = self.sanitize_filename(filename)
        if sanitized != filename:
            all_issues.append(ValidationIssue(
                rule="FILENAME_SANITIZED",
                severity="INFO",
                message="Filename was sanitized for safety",
                details=f"Original: {filename}, Sanitized: {sanitized}",
                auto_fixable=True,
            ))
        else:
            passed_rules.append("FILENAME")

        # Build result
        return self._build_result(all_issues, passed_rules, {
            "sanitized_filename": sanitized,
            "file_size": len(file_content),
            "declared_doc_type": declared_doc_type,
            "declared_mime_type": mime_type,
            "file_hash_sha256": hashlib.sha256(file_content).hexdigest(),
        })

    # ------------------------------------------------------------------
    # File type validation
    # ------------------------------------------------------------------

    def validate_file_type(
        self,
        file_content: bytes,
        filename: str,
        declared_mime: str,
    ) -> List[ValidationIssue]:
        """
        Validate the file type via extension, magic bytes, and MIME allowlist.

        Checks:
        - Extension not in BLOCKED_EXTENSIONS
        - No double extensions (e.g. document.pdf.exe)
        - Magic bytes match declared MIME
        - MIME type is in ALLOWED_MIME_TYPES
        """
        issues: List[ValidationIssue] = []
        lower_name = filename.lower()

        # -- Blocked extension check --
        _, ext = os.path.splitext(lower_name)
        if ext in BLOCKED_EXTENSIONS:
            issues.append(ValidationIssue(
                rule="FILE_TYPE_BLOCKED",
                severity="CRITICAL",
                message=f"File extension '{ext}' is not allowed",
                details="This extension is associated with executable or script files",
                fix_instruction="Upload the document as a PDF or image (JPEG, PNG, TIFF)",
            ))

        # -- Double-extension check (e.g. report.pdf.exe) --
        parts = lower_name.rsplit(".", maxsplit=3)
        if len(parts) >= 3:
            # Check all trailing extensions
            for i in range(1, len(parts)):
                candidate_ext = "." + parts[i]
                if candidate_ext in BLOCKED_EXTENSIONS:
                    issues.append(ValidationIssue(
                        rule="FILE_TYPE_DOUBLE_EXT",
                        severity="CRITICAL",
                        message=f"Double extension detected: filename contains blocked extension '{candidate_ext}'",
                        details=f"Filename '{filename}' may be attempting to disguise file type",
                        fix_instruction="Rename the file to remove extra extensions",
                    ))

        # -- MIME allowlist --
        if declared_mime not in ALLOWED_MIME_TYPES:
            issues.append(ValidationIssue(
                rule="FILE_TYPE_MIME_NOT_ALLOWED",
                severity="CRITICAL",
                message=f"MIME type '{declared_mime}' is not allowed",
                details=f"Allowed types: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
                fix_instruction="Convert the document to PDF, JPEG, PNG, or TIFF before uploading",
            ))

        # -- Magic bytes verification --
        if file_content:
            detected_mime = self._detect_mime_from_magic(file_content)
            if detected_mime:
                if detected_mime != declared_mime:
                    # Allow tiff variants and webp/riff to pass with a warning
                    if not self._mime_types_compatible(detected_mime, declared_mime):
                        issues.append(ValidationIssue(
                            rule="FILE_TYPE_MAGIC_MISMATCH",
                            severity="HIGH",
                            message="File content does not match declared type",
                            details=(
                                f"Declared: {declared_mime}, "
                                f"Detected: {detected_mime}"
                            ),
                            fix_instruction="Ensure the file extension and content type are correct",
                        ))
            else:
                # Could not identify magic bytes -- not necessarily bad, but flag it
                if len(file_content) >= 4:
                    issues.append(ValidationIssue(
                        rule="FILE_TYPE_MAGIC_UNKNOWN",
                        severity="MEDIUM",
                        message="Could not verify file type from content bytes",
                        details="The file header does not match any known document format",
                    ))

        return issues

    # ------------------------------------------------------------------
    # File size validation
    # ------------------------------------------------------------------

    def validate_file_size(
        self,
        file_content: bytes,
        mime_type: str,
    ) -> List[ValidationIssue]:
        """
        Validate file size against minimum and maximum limits.
        """
        issues: List[ValidationIssue] = []
        size = len(file_content)

        max_size = MAX_FILE_SIZES.get(mime_type, MAX_FILE_SIZES["default"])
        min_size = MIN_FILE_SIZES.get(mime_type, MIN_FILE_SIZES["default"])

        if size > max_size:
            max_mb = max_size / (1024 * 1024)
            actual_mb = size / (1024 * 1024)
            issues.append(ValidationIssue(
                rule="FILE_SIZE_TOO_LARGE",
                severity="CRITICAL",
                message=f"File size ({actual_mb:.1f} MB) exceeds maximum ({max_mb:.0f} MB)",
                fix_instruction="Reduce file size or split into multiple uploads",
            ))

        if size < min_size:
            issues.append(ValidationIssue(
                rule="FILE_SIZE_TOO_SMALL",
                severity="HIGH",
                message=f"File size ({size} bytes) is suspiciously small (min {min_size} bytes)",
                details="The file may be blank, corrupt, or incomplete",
                fix_instruction="Re-scan or re-download the document and try again",
            ))

        if size == 0:
            issues.append(ValidationIssue(
                rule="FILE_SIZE_EMPTY",
                severity="CRITICAL",
                message="File is empty (0 bytes)",
                fix_instruction="Select the correct file and re-upload",
            ))

        return issues

    # ------------------------------------------------------------------
    # Filename sanitization
    # ------------------------------------------------------------------

    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize a filename for safe storage.

        - Removes path traversal sequences (../, ..\\)
        - Removes null bytes
        - Replaces dangerous characters with underscores
        - Limits length to 255 characters (preserving extension)
        - Strips leading/trailing whitespace and dots
        """
        # Remove null bytes
        name = filename.replace("\x00", "")

        # Strip absolute path prefixes and leading slashes/backslashes
        name = re.sub(r'^([a-zA-Z]:)?[\\/]+', '', name)

        # Remove path traversal sequences in a loop to defeat bypass
        # patterns like "....//", "..../\", etc.
        prev = None
        while prev != name:
            prev = name
            name = name.replace("../", "").replace("..\\", "")

        # Replace any remaining path separators
        name = name.replace("/", "_").replace("\\", "_")

        # Remove control characters (0x00-0x1f, 0x7f)
        name = re.sub(r"[\x00-\x1f\x7f]", "", name)

        # Replace characters that are dangerous on various filesystems
        name = re.sub(r'[<>:"|?*]', "_", name)

        # Strip leading/trailing whitespace and dots
        name = name.strip(" .")

        # Collapse multiple underscores/spaces
        name = re.sub(r"[_\s]{2,}", "_", name)

        # If nothing is left, assign a default
        if not name:
            name = "document"

        # Preserve extension while limiting total length
        base, ext = os.path.splitext(name)
        max_base_len = 255 - len(ext)
        if max_base_len < 1:
            max_base_len = 1
        base = base[:max_base_len]

        return base + ext

    # ------------------------------------------------------------------
    # Freshness validation
    # ------------------------------------------------------------------

    def validate_freshness(
        self,
        doc_type: str,
        doc_date: Optional[datetime],
    ) -> List[ValidationIssue]:
        """
        Check document age against FRESHNESS_RULES.

        Args:
            doc_type: Document type string (e.g. PAYSTUB, W2).
            doc_date: Date extracted from the document.

        Returns:
            List of freshness issues (empty if fresh or not applicable).
        """
        issues: List[ValidationIssue] = []
        doc_type_upper = doc_type.upper() if doc_type else ""

        max_days = FRESHNESS_RULES.get(doc_type_upper)
        if max_days is None:
            # No freshness rule for this type
            return issues

        if doc_date is None:
            issues.append(ValidationIssue(
                rule="FRESHNESS_NO_DATE",
                severity="MEDIUM",
                message=f"Cannot verify freshness for {doc_type_upper} -- no date extracted",
                fix_instruction="Ensure the document date is visible and legible",
            ))
            return issues

        # Normalize to date
        if isinstance(doc_date, datetime):
            check_date = doc_date.date() if doc_date.tzinfo is None else doc_date.astimezone(timezone.utc).date()
        else:
            check_date = doc_date

        today = date.today()
        age_days = (today - check_date).days

        if age_days > max_days:
            issues.append(ValidationIssue(
                rule="FRESHNESS_EXPIRED",
                severity="HIGH",
                message=f"{doc_type_upper} is {age_days} days old (max {max_days} days)",
                details=f"Document date: {check_date.isoformat()}, expired {age_days - max_days} days ago",
                fix_instruction=f"Provide a {doc_type_upper} dated within the last {max_days} days",
            ))
        elif age_days > max_days - 7:
            # Expiring soon (within 7 days)
            remaining = max_days - age_days
            issues.append(ValidationIssue(
                rule="FRESHNESS_EXPIRING_SOON",
                severity="LOW",
                message=f"{doc_type_upper} expires in {remaining} days",
                details=f"Document date: {check_date.isoformat()}",
            ))

        return issues

    # ------------------------------------------------------------------
    # PDF safety validation
    # ------------------------------------------------------------------

    def validate_pdf_safety(self, file_content: bytes) -> List[ValidationIssue]:
        """
        Inspect PDF bytes for dangerous embedded content.

        Checks for:
        - Embedded JavaScript (/JS, /JavaScript)
        - Launch actions (/Launch)
        - Auto-open actions (/OpenAction with /JS)
        - Embedded executables (/EmbeddedFile with dangerous types)
        - Excessive page count (DoS vector)
        """
        issues: List[ValidationIssue] = []

        if not file_content or not file_content[:5].startswith(b"%PDF"):
            return issues

        # Scan a reasonable portion of the file (or all of it if small)
        # PDF structures can appear anywhere, so scan the whole thing
        # but work with bytes to avoid encoding issues.
        content_str = file_content  # keep as bytes for pattern search

        # -- JavaScript --
        js_patterns = [b"/JS ", b"/JS(", b"/JS<", b"/JavaScript"]
        for pattern in js_patterns:
            if pattern in content_str:
                issues.append(ValidationIssue(
                    rule="PDF_JAVASCRIPT",
                    severity="CRITICAL",
                    message="PDF contains embedded JavaScript",
                    details="Embedded JavaScript in PDFs is a common malware vector",
                    fix_instruction="Print the document to a new PDF to strip scripts, then re-upload",
                ))
                break  # One issue is enough

        # -- Launch actions --
        if b"/Launch" in content_str:
            issues.append(ValidationIssue(
                rule="PDF_LAUNCH_ACTION",
                severity="CRITICAL",
                message="PDF contains a Launch action",
                details="Launch actions can execute programs on the user's computer",
                fix_instruction="Print the document to a new PDF to strip actions, then re-upload",
            ))

        # -- Auto-open with JS --
        if b"/OpenAction" in content_str:
            # Only flag if combined with JS or URI
            has_js_open = False
            oa_idx = content_str.find(b"/OpenAction")
            if oa_idx >= 0:
                # Check a window after /OpenAction for /JS or /JavaScript
                window = content_str[oa_idx:oa_idx + 512]
                if b"/JS" in window or b"/JavaScript" in window or b"/URI" in window:
                    has_js_open = True

            if has_js_open:
                issues.append(ValidationIssue(
                    rule="PDF_AUTOOPEN_SCRIPT",
                    severity="CRITICAL",
                    message="PDF has an auto-open action that triggers a script or URI",
                    fix_instruction="Print the document to a new PDF to strip auto-open actions",
                ))

        # -- Embedded executables --
        if b"/EmbeddedFile" in content_str:
            # Check for dangerous MIME types in the embedded file spec
            dangerous_embed_indicators = [
                b"application/x-msdownload",
                b"application/x-msdos-program",
                b"application/x-executable",
                b".exe",
                b".bat",
                b".cmd",
                b".vbs",
                b".ps1",
            ]
            for indicator in dangerous_embed_indicators:
                if indicator in content_str:
                    issues.append(ValidationIssue(
                        rule="PDF_EMBEDDED_EXECUTABLE",
                        severity="CRITICAL",
                        message="PDF contains an embedded executable file",
                        details=f"Detected indicator: {indicator.decode('ascii', errors='replace')}",
                        fix_instruction="Remove embedded files and re-upload the PDF",
                    ))
                    break

        # -- Excessive page count (DoS) --
        page_count = self._estimate_pdf_page_count(file_content)
        if page_count is not None and page_count > 500:
            issues.append(ValidationIssue(
                rule="PDF_EXCESSIVE_PAGES",
                severity="HIGH",
                message=f"PDF has an estimated {page_count} pages",
                details="Documents with hundreds of pages may indicate a corrupted file or DoS attempt",
                fix_instruction="Split the document into smaller sections before uploading",
            ))

        return issues

    # ------------------------------------------------------------------
    # Image safety validation
    # ------------------------------------------------------------------

    def validate_image_safety(self, file_content: bytes) -> List[ValidationIssue]:
        """
        Inspect image bytes for safety concerns.

        Checks for:
        - Steganography indicators (excessive trailing data)
        - Absurdly large declared dimensions
        - Embedded data after end-of-image marker (JPEG)
        """
        issues: List[ValidationIssue] = []

        if not file_content:
            return issues

        # -- JPEG trailing data --
        if file_content[:3] == b"\xff\xd8\xff":
            eoi_idx = file_content.rfind(b"\xff\xd9")
            if eoi_idx >= 0:
                trailing = len(file_content) - (eoi_idx + 2)
                if trailing > 4096:
                    issues.append(ValidationIssue(
                        rule="IMAGE_TRAILING_DATA",
                        severity="MEDIUM",
                        message=f"JPEG has {trailing} bytes after end-of-image marker",
                        details="Excess data after the image end marker may indicate hidden content",
                    ))

        # -- PNG trailing data --
        if file_content[:4] == b"\x89PNG":
            iend_idx = file_content.rfind(b"IEND")
            if iend_idx >= 0:
                # IEND chunk: 4 bytes length + "IEND" + 4 bytes CRC = at least 12 bytes to end
                expected_end = iend_idx + 8  # "IEND" + 4 CRC bytes
                trailing = len(file_content) - expected_end
                if trailing > 4096:
                    issues.append(ValidationIssue(
                        rule="IMAGE_TRAILING_DATA",
                        severity="MEDIUM",
                        message=f"PNG has {trailing} bytes after IEND chunk",
                        details="Excess data after the image end marker may indicate hidden content",
                    ))

        # -- Dimension check for PNG --
        if file_content[:4] == b"\x89PNG" and len(file_content) >= 24:
            # PNG IHDR: bytes 16-19 = width, 20-23 = height (big-endian)
            try:
                width = struct.unpack(">I", file_content[16:20])[0]
                height = struct.unpack(">I", file_content[20:24])[0]
                if width > 20000 or height > 20000:
                    issues.append(ValidationIssue(
                        rule="IMAGE_ABSURD_DIMENSIONS",
                        severity="HIGH",
                        message=f"Image dimensions are unusually large ({width}x{height})",
                        details="Extremely large images can cause memory exhaustion",
                        fix_instruction="Resize the image to reasonable dimensions before uploading",
                    ))
                total_pixels = width * height
                if total_pixels > 200_000_000:  # 200 megapixels
                    issues.append(ValidationIssue(
                        rule="IMAGE_PIXEL_BOMB",
                        severity="HIGH",
                        message=f"Image has {total_pixels:,} pixels (potential decompression bomb)",
                        fix_instruction="Resize the image to reasonable dimensions before uploading",
                    ))
            except (struct.error, IndexError):
                pass

        # -- Dimension check for JPEG (SOF0 marker) --
        if file_content[:3] == b"\xff\xd8\xff":
            dims = self._extract_jpeg_dimensions(file_content)
            if dims:
                width, height = dims
                if width > 20000 or height > 20000:
                    issues.append(ValidationIssue(
                        rule="IMAGE_ABSURD_DIMENSIONS",
                        severity="HIGH",
                        message=f"JPEG dimensions are unusually large ({width}x{height})",
                        fix_instruction="Resize the image before uploading",
                    ))

        # -- Excessive EXIF/metadata check --
        # JPEG APP1 (Exif) segments can be large; flag if metadata is disproportionate
        if file_content[:3] == b"\xff\xd8\xff":
            metadata_size = self._estimate_jpeg_metadata_size(file_content)
            file_size = len(file_content)
            if file_size > 0 and metadata_size > 0:
                ratio = metadata_size / file_size
                if ratio > 0.5 and metadata_size > 100_000:
                    issues.append(ValidationIssue(
                        rule="IMAGE_EXCESSIVE_METADATA",
                        severity="LOW",
                        message=f"Image metadata ({metadata_size:,} bytes) is {ratio:.0%} of file size",
                        details="Excessive metadata may indicate steganography or data hiding",
                    ))

        return issues

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def detect_duplicates(
        self,
        loan_id: int,
        file_content: bytes,
        doc_type: str,
        db: Session,
        organization_id: Optional[int] = None,
    ) -> List[ValidationIssue]:
        """
        Detect duplicate documents for the same loan.

        Checks:
        1. Exact duplicate by SHA-256 hash
        2. Same doc type uploaded recently (within 24 hours)

        Args:
            loan_id: The loan to check for duplicates.
            file_content: Raw bytes of the file being uploaded.
            doc_type: Document type string.
            db: SQLAlchemy session.
            organization_id: Optional org ID for tenant isolation.
        """
        issues: List[ValidationIssue] = []
        file_hash = hashlib.sha256(file_content).hexdigest()

        # Build tenant isolation JOIN fragment
        _org_join = (
            "JOIN loans _org_l ON _org_l.id = smart_documents.loan_id "
            "AND _org_l.organization_id = :_org_id"
            if organization_id is not None else ""
        )
        _org_params: Dict = {"_org_id": organization_id} if organization_id is not None else {}

        try:
            # Check for exact hash match in smart_documents
            # The smart_documents table doesn't store a hash column, so we compare
            # against storage_key or file_size as a proxy, plus doc_type.
            # For true dedup, we'd need a hash column.  For now, check by file_size
            # + doc_type as a heuristic, and note the hash in metadata.

            existing = db.execute(text(f"""
                SELECT smart_documents.id, file_name, file_size, doc_type, uploaded_at
                FROM smart_documents
                {_org_join}
                WHERE loan_id = :loan_id
                    AND file_size = :file_size
                    AND status NOT IN ('REJECTED', 'EXPIRED')
                ORDER BY uploaded_at DESC
                LIMIT 5
            """), {
                "loan_id": loan_id,
                "file_size": len(file_content),
                **_org_params,
            }).fetchall()

            if existing:
                for row in existing:
                    issues.append(ValidationIssue(
                        rule="DUPLICATE_EXACT_SIZE",
                        severity="MEDIUM",
                        message=f"A file with the same size already exists for this loan",
                        details=(
                            f"Existing document: {row.file_name} "
                            f"(uploaded {row.uploaded_at.strftime('%m/%d/%Y') if row.uploaded_at else 'unknown'})"
                        ),
                        fix_instruction="Verify this is not a duplicate upload",
                    ))

            # Check for same doc type uploaded in last 24 hours
            if doc_type:
                recent_same_type = db.execute(text(f"""
                    SELECT smart_documents.id, file_name, uploaded_at
                    FROM smart_documents
                    {_org_join}
                    WHERE loan_id = :loan_id
                        AND doc_type = :doc_type
                        AND uploaded_at >= NOW() - INTERVAL '24 hours'
                        AND status NOT IN ('REJECTED', 'EXPIRED')
                    ORDER BY uploaded_at DESC
                    LIMIT 3
                """), {
                    "loan_id": loan_id,
                    "doc_type": doc_type,
                    **_org_params,
                }).fetchall()

                if recent_same_type:
                    names = ", ".join(row.file_name for row in recent_same_type)
                    issues.append(ValidationIssue(
                        rule="DUPLICATE_RECENT_SAME_TYPE",
                        severity="LOW",
                        message=f"A {doc_type} was already uploaded in the last 24 hours",
                        details=f"Recent uploads: {names}",
                        fix_instruction="If this is a corrected version, consider removing the previous upload",
                    ))

        except Exception as e:
            logger.warning("Duplicate detection query failed: %s", e)
            # Non-fatal: skip duplicate check if DB is unavailable

        return issues

    # ------------------------------------------------------------------
    # Completeness validation
    # ------------------------------------------------------------------

    def validate_completeness(
        self,
        doc_type: str,
        ocr_text: Optional[str],
    ) -> List[ValidationIssue]:
        """
        Check OCR text for required fields based on document type.

        Args:
            doc_type: Document type (e.g. PAYSTUB, W2, BANK_STATEMENT).
            ocr_text: Extracted text from the document.

        Returns:
            Issues for missing required fields.
        """
        issues: List[ValidationIssue] = []
        doc_type_upper = (doc_type or "").upper()

        rules = COMPLETENESS_RULES.get(doc_type_upper)
        if not rules:
            return issues  # No completeness rules for this type

        if not ocr_text or not ocr_text.strip():
            issues.append(ValidationIssue(
                rule="COMPLETENESS_NO_TEXT",
                severity="MEDIUM",
                message=f"No text extracted from {doc_type_upper} -- cannot verify completeness",
                fix_instruction="Ensure the document is not a photo of a blank page or a low-quality scan",
            ))
            return issues

        text_lower = ocr_text.lower()

        for field_name, patterns in rules:
            found = False
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    found = True
                    break
            if not found:
                readable_name = field_name.replace("_", " ").title()
                issues.append(ValidationIssue(
                    rule=f"COMPLETENESS_MISSING_{field_name.upper()}",
                    severity="MEDIUM",
                    message=f"{readable_name} not detected in {doc_type_upper}",
                    details=f"Expected to find patterns related to: {readable_name}",
                    fix_instruction=f"Ensure the {readable_name} is visible on the document",
                ))

        return issues

    # ------------------------------------------------------------------
    # PII handling validation
    # ------------------------------------------------------------------

    def validate_pii_handling(
        self,
        ocr_text: Optional[str],
    ) -> List[ValidationIssue]:
        """
        Detect PII in extracted text and recommend redaction or masking.

        Args:
            ocr_text: Extracted text from the document.

        Returns:
            PII-related issues and recommendations.
        """
        issues: List[ValidationIssue] = []

        if not ocr_text or not ocr_text.strip():
            return issues

        for pii_type, (pattern, description) in PII_PATTERNS.items():
            matches = re.findall(pattern, ocr_text)
            if matches:
                # Filter out obvious non-PII (e.g. phone numbers for full_ssn_nohyphens)
                if pii_type == "full_ssn_nohyphens":
                    # Heuristic: 9-digit numbers that look like SSNs
                    # Skip numbers starting with 000, 666, 900-999 (invalid SSN prefixes)
                    real_matches = []
                    for m in matches:
                        prefix = int(m[:3])
                        if prefix not in (0, 666) and prefix < 900:
                            real_matches.append(m)
                    matches = real_matches

                if pii_type == "full_account_number":
                    # Only flag if there are a reasonable number (not every long number)
                    if len(matches) > 20:
                        matches = matches[:5]  # Limit noise

                if matches:
                    count = len(matches)
                    severity = "HIGH" if pii_type == "full_ssn" else "MEDIUM"
                    issues.append(ValidationIssue(
                        rule=f"PII_{pii_type.upper()}",
                        severity=severity,
                        message=f"{description} ({count} occurrence{'s' if count > 1 else ''})",
                        details=f"PII type: {pii_type}",
                        fix_instruction=(
                            "Redact or mask sensitive information before storing. "
                            "Full SSNs should show only last 4 digits."
                        ),
                    ))

        return issues

    # ------------------------------------------------------------------
    # Page count validation
    # ------------------------------------------------------------------

    def validate_page_count(
        self,
        file_content: bytes,
        mime_type: str,
        doc_type: str,
    ) -> List[ValidationIssue]:
        """
        Estimate page count and compare to expected range for the doc type.

        Args:
            file_content: Raw file bytes.
            mime_type: MIME type of the file.
            doc_type: Declared document type.
        """
        issues: List[ValidationIssue] = []
        doc_type_upper = (doc_type or "").upper()

        expected = EXPECTED_PAGE_COUNTS.get(doc_type_upper)
        if expected is None:
            return issues  # No expectation for this type

        min_pages, max_pages = expected
        page_count = None

        if mime_type == "application/pdf":
            page_count = self._estimate_pdf_page_count(file_content)
        elif mime_type.startswith("image/"):
            # Images are single-page unless TIFF (which can be multi-page)
            if mime_type == "image/tiff":
                page_count = self._estimate_tiff_page_count(file_content)
            else:
                page_count = 1

        if page_count is None:
            return issues  # Could not determine

        if page_count < min_pages:
            issues.append(ValidationIssue(
                rule="PAGE_COUNT_TOO_FEW",
                severity="MEDIUM",
                message=f"{doc_type_upper} has {page_count} page(s), expected at least {min_pages}",
                details=f"Expected range: {min_pages}-{max_pages} pages",
                fix_instruction="Ensure all pages of the document were included in the upload",
            ))

        if page_count > max_pages:
            severity = "HIGH" if page_count > max_pages * 3 else "LOW"
            issues.append(ValidationIssue(
                rule="PAGE_COUNT_TOO_MANY",
                severity=severity,
                message=f"{doc_type_upper} has {page_count} pages, expected at most {max_pages}",
                details=f"Expected range: {min_pages}-{max_pages} pages",
                fix_instruction="Verify the correct document was uploaded, or split if multiple docs are combined",
            ))

        return issues

    # ------------------------------------------------------------------
    # Batch validation
    # ------------------------------------------------------------------

    def batch_validate(
        self,
        documents: List[Dict],
    ) -> List[ValidationResult]:
        """
        Validate multiple documents.

        Each dict should contain:
        - file_content: bytes
        - filename: str
        - mime_type: str
        - doc_type: Optional[str]

        Returns:
            List of ValidationResult, one per input document.
        """
        results: List[ValidationResult] = []
        for doc in documents:
            result = self.validate_upload(
                file_content=doc.get("file_content", b""),
                filename=doc.get("filename", "unknown"),
                mime_type=doc.get("mime_type", "application/octet-stream"),
                declared_doc_type=doc.get("doc_type"),
            )
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Rule introspection
    # ------------------------------------------------------------------

    def get_validation_rules_for_type(self, doc_type: str) -> Dict:
        """
        Return applicable validation rules for a document type.

        Useful for frontends to display upload requirements.
        """
        doc_type_upper = (doc_type or "").upper()

        # Determine allowed MIME types (same for all doc types)
        allowed_types = sorted(ALLOWED_MIME_TYPES)

        # Freshness
        freshness_days = FRESHNESS_RULES.get(doc_type_upper)

        # Expected pages
        page_range = EXPECTED_PAGE_COUNTS.get(doc_type_upper)

        # Completeness fields
        completeness_fields = []
        rules = COMPLETENESS_RULES.get(doc_type_upper, [])
        for field_name, _patterns in rules:
            completeness_fields.append(field_name.replace("_", " ").title())

        # Max file size
        max_sizes = {}
        for mime, size in MAX_FILE_SIZES.items():
            if mime != "default":
                max_sizes[mime] = f"{size / (1024 * 1024):.0f} MB"

        return {
            "doc_type": doc_type_upper,
            "allowed_mime_types": allowed_types,
            "blocked_extensions": sorted(BLOCKED_EXTENSIONS),
            "max_file_sizes": max_sizes,
            "freshness_days": freshness_days,
            "freshness_description": (
                f"Must be dated within the last {freshness_days} days"
                if freshness_days
                else "No freshness requirement"
            ),
            "expected_page_range": {
                "min": page_range[0] if page_range else None,
                "max": page_range[1] if page_range else None,
            },
            "required_fields": completeness_fields,
        }

    # ------------------------------------------------------------------
    # Hard size and dimension limits (new checks)
    # ------------------------------------------------------------------

    def _validate_hard_size_limit(
        self,
        file_content: bytes,
        mime_type: str,
    ) -> List[ValidationIssue]:
        """
        Enforce absolute size limits from upload_limits module.

        This runs FIRST before any other processing to prevent large files
        from consuming memory during subsequent validation steps.
        """
        issues: List[ValidationIssue] = []
        file_size = len(file_content)

        # Determine the applicable hard limit
        if mime_type.startswith("image/"):
            hard_limit = MAX_IMAGE_SIZE
            limit_label = "image"
        else:
            hard_limit = MAX_DOCUMENT_SIZE
            limit_label = "document"

        if file_size > hard_limit:
            limit_mb = hard_limit / (1024 * 1024)
            actual_mb = file_size / (1024 * 1024)
            issues.append(ValidationIssue(
                rule="HARD_SIZE_LIMIT_EXCEEDED",
                severity="CRITICAL",
                message=(
                    f"File size ({actual_mb:.1f} MB) exceeds the maximum "
                    f"allowed {limit_label} size ({limit_mb:.0f} MB)"
                ),
                fix_instruction=(
                    f"Reduce the file size to under {limit_mb:.0f} MB. "
                    f"For PDFs, try compressing or splitting. "
                    f"For images, try reducing resolution or using JPEG compression."
                ),
            ))

        return issues

    def _validate_image_dimensions(
        self,
        file_content: bytes,
    ) -> List[ValidationIssue]:
        """
        Check image dimensions against MAX_IMAGE_DIMENSIONS without
        loading the full image into memory.
        """
        issues: List[ValidationIssue] = []
        width, height = 0, 0
        max_w, max_h = MAX_IMAGE_DIMENSIONS

        if not file_content or len(file_content) < 24:
            return issues

        # PNG: IHDR at bytes 16-23
        if file_content[:4] == b"\x89PNG":
            try:
                width = struct.unpack(">I", file_content[16:20])[0]
                height = struct.unpack(">I", file_content[20:24])[0]
            except (struct.error, IndexError):
                pass

        # JPEG: SOF marker
        elif file_content[:3] == b"\xff\xd8\xff":
            dims = self._extract_jpeg_dimensions(file_content)
            if dims:
                width, height = dims

        # BMP
        elif file_content[:2] == b"BM" and len(file_content) >= 26:
            try:
                width = struct.unpack("<I", file_content[18:22])[0]
                height = abs(struct.unpack("<i", file_content[22:26])[0])
            except (struct.error, IndexError):
                pass

        if width == 0 and height == 0:
            return issues  # Cannot determine dimensions, skip

        if width > max_w or height > max_h:
            issues.append(ValidationIssue(
                rule="IMAGE_DIMENSIONS_EXCEEDED",
                severity="CRITICAL",
                message=(
                    f"Image dimensions {width}x{height} exceed the "
                    f"maximum allowed {max_w}x{max_h} pixels"
                ),
                fix_instruction=(
                    "Resize the image to smaller dimensions before uploading. "
                    "Most mortgage documents should be 300 DPI letter size "
                    "(2550x3300 pixels)."
                ),
            ))

        # Decompression bomb check: total pixels
        total_pixels = width * height
        if total_pixels > 100_000_000:  # 100 megapixels
            issues.append(ValidationIssue(
                rule="IMAGE_DECOMPRESSION_BOMB",
                severity="CRITICAL",
                message=(
                    f"Image has {total_pixels:,} total pixels, which could "
                    f"exhaust server memory when processed"
                ),
                fix_instruction="Resize the image to reasonable dimensions",
            ))

        return issues

    def _validate_pdf_limits(
        self,
        file_content: bytes,
    ) -> List[ValidationIssue]:
        """
        Enforce PDF page count limit and detect decompression bombs.
        """
        issues: List[ValidationIssue] = []

        # Page count check
        page_count = self._estimate_pdf_page_count(file_content)
        if page_count is not None and page_count > MAX_PDF_PAGES:
            issues.append(ValidationIssue(
                rule="PDF_PAGE_LIMIT_EXCEEDED",
                severity="CRITICAL",
                message=(
                    f"PDF has {page_count} pages, exceeding the "
                    f"maximum of {MAX_PDF_PAGES} pages"
                ),
                fix_instruction=(
                    f"Split the document into parts with no more than "
                    f"{MAX_PDF_PAGES} pages each and upload separately."
                ),
            ))

        # PDF bomb detection: check if declared stream lengths are
        # disproportionate to the compressed file size
        compressed_size = len(file_content)
        if compressed_size > 0:
            try:
                lengths = re.findall(rb"/Length\s+(\d+)", file_content)
                total_declared = sum(
                    int(l) for l in lengths if int(l) < 1_000_000_000
                )
                if total_declared > compressed_size * PDF_BOMB_RATIO:
                    issues.append(ValidationIssue(
                        rule="PDF_DECOMPRESSION_BOMB",
                        severity="CRITICAL",
                        message=(
                            f"PDF contains compressed streams that would decompress "
                            f"to ~{total_declared / (1024 * 1024):.0f} MB "
                            f"(file is only {compressed_size / (1024 * 1024):.1f} MB). "
                            f"Ratio exceeds {PDF_BOMB_RATIO}x threshold."
                        ),
                        fix_instruction=(
                            "This file may be malformed or malicious. "
                            "Try re-creating the PDF from the original source."
                        ),
                    ))
            except Exception as e:
                logger.debug("PDF bomb heuristic failed: %s", e)

            # Also check if file is tiny but claims many pages
            if page_count is not None and page_count > 10:
                bytes_per_page = compressed_size / page_count
                if bytes_per_page < 100:
                    issues.append(ValidationIssue(
                        rule="PDF_SUSPICIOUS_SIZE_RATIO",
                        severity="CRITICAL",
                        message=(
                            f"PDF claims {page_count} pages but is only "
                            f"{compressed_size:,} bytes "
                            f"({bytes_per_page:.0f} bytes/page)"
                        ),
                        fix_instruction=(
                            "This file may be malformed. "
                            "Try re-scanning or re-creating the document."
                        ),
                    ))

        return issues

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_mime_from_magic(self, content: bytes) -> Optional[str]:
        """Detect MIME type from magic bytes at the start of the file."""
        for magic, mime in MAGIC_BYTES.items():
            if content[:len(magic)] == magic:
                return mime
        return None

    def _mime_types_compatible(self, detected: str, declared: str) -> bool:
        """Check if two MIME types should be considered compatible."""
        # Same type
        if detected == declared:
            return True
        # WebP: RIFF detection may report image/webp, declared could be image/webp
        if {detected, declared} == {"image/webp", "image/webp"}:
            return True
        # TIFF variants
        if detected.startswith("image/tiff") and declared.startswith("image/tiff"):
            return True
        return False

    def _estimate_pdf_page_count(self, content: bytes) -> Optional[int]:
        """
        Estimate the number of pages in a PDF by counting /Type /Page occurrences.

        This is a heuristic -- not 100% accurate but good enough for validation.
        """
        if not content:
            return None

        # Method 1: Count /Type /Page (but not /Type /Pages which is the page tree)
        # This is the most reliable byte-level heuristic
        count = 0
        idx = 0
        search_term = b"/Type /Page"
        pages_term = b"/Type /Pages"

        while True:
            idx = content.find(search_term, idx)
            if idx == -1:
                break
            # Make sure it's not /Type /Pages (the page tree node)
            if content[idx:idx + len(pages_term)] != pages_term:
                count += 1
            idx += len(search_term)

        if count > 0:
            return count

        # Method 2: Look for /Count in the page tree
        count_idx = content.find(b"/Count ")
        if count_idx >= 0:
            # Extract the number after /Count
            num_start = count_idx + 7
            num_bytes = content[num_start:num_start + 10]
            try:
                num_str = num_bytes.split(b" ")[0].split(b"/")[0].split(b"\n")[0].split(b"\r")[0]
                return int(num_str)
            except (ValueError, IndexError):
                pass

        return None

    def _estimate_tiff_page_count(self, content: bytes) -> Optional[int]:
        """Estimate pages in a multi-page TIFF by counting IFD entries."""
        if not content or len(content) < 8:
            return None

        try:
            # Determine endianness
            if content[:2] == b"II":
                endian = "<"
            elif content[:2] == b"MM":
                endian = ">"
            else:
                return None

            # Read offset to first IFD
            ifd_offset = struct.unpack(endian + "I", content[4:8])[0]

            page_count = 0
            visited = set()

            while ifd_offset > 0 and ifd_offset < len(content) and ifd_offset not in visited:
                visited.add(ifd_offset)
                page_count += 1

                if page_count > 1000:
                    return page_count  # Safety limit

                # Read number of entries in this IFD
                if ifd_offset + 2 > len(content):
                    break
                num_entries = struct.unpack(endian + "H", content[ifd_offset:ifd_offset + 2])[0]

                # Calculate offset to next IFD pointer
                next_ifd_ptr = ifd_offset + 2 + (num_entries * 12)
                if next_ifd_ptr + 4 > len(content):
                    break

                ifd_offset = struct.unpack(endian + "I", content[next_ifd_ptr:next_ifd_ptr + 4])[0]

            return page_count if page_count > 0 else None

        except (struct.error, IndexError):
            return None

    def _extract_jpeg_dimensions(self, content: bytes) -> Optional[Tuple[int, int]]:
        """Extract width and height from JPEG SOF marker."""
        if not content or len(content) < 20:
            return None

        # Search for SOF0 (0xFFC0) or SOF2 (0xFFC2) marker
        idx = 2  # Skip SOI marker
        while idx < len(content) - 8:
            if content[idx] != 0xFF:
                idx += 1
                continue

            marker = content[idx + 1]

            # SOF markers: C0, C1, C2, C3 (most common are C0 and C2)
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                try:
                    height = struct.unpack(">H", content[idx + 5:idx + 7])[0]
                    width = struct.unpack(">H", content[idx + 7:idx + 9])[0]
                    return (width, height)
                except (struct.error, IndexError):
                    return None

            # Skip to next marker
            if marker == 0xD9:  # EOI
                break
            if marker in (0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0x01):
                idx += 2
                continue

            # Read segment length
            if idx + 4 > len(content):
                break
            try:
                seg_len = struct.unpack(">H", content[idx + 2:idx + 4])[0]
                idx += 2 + seg_len
            except struct.error:
                break

        return None

    def _estimate_jpeg_metadata_size(self, content: bytes) -> int:
        """Estimate total metadata size in JPEG (APP segments before SOS)."""
        if not content or len(content) < 4:
            return 0

        metadata_bytes = 0
        idx = 2  # Skip SOI

        while idx < len(content) - 4:
            if content[idx] != 0xFF:
                break

            marker = content[idx + 1]

            # SOS (Start of Scan) marks end of metadata
            if marker == 0xDA:
                break

            # APP segments (0xE0-0xEF) and COM (0xFE) are metadata
            if (0xE0 <= marker <= 0xEF) or marker == 0xFE:
                try:
                    seg_len = struct.unpack(">H", content[idx + 2:idx + 4])[0]
                    metadata_bytes += seg_len
                    idx += 2 + seg_len
                    continue
                except struct.error:
                    break

            # Other markers -- skip
            if marker in (0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0x01):
                idx += 2
                continue

            try:
                seg_len = struct.unpack(">H", content[idx + 2:idx + 4])[0]
                idx += 2 + seg_len
            except struct.error:
                break

        return metadata_bytes

    def _build_result(
        self,
        issues: List[ValidationIssue],
        passed_rules: List[str],
        metadata: Dict,
    ) -> ValidationResult:
        """Build a ValidationResult from collected issues and metadata."""
        critical = sum(1 for i in issues if i.severity == "CRITICAL")
        high = sum(1 for i in issues if i.severity == "HIGH")
        medium = sum(1 for i in issues if i.severity == "MEDIUM")

        # Score: start at 100, deduct for issues
        score = 100
        for issue in issues:
            if issue.severity == "CRITICAL":
                score -= 30
            elif issue.severity == "HIGH":
                score -= 15
            elif issue.severity == "MEDIUM":
                score -= 5
            elif issue.severity == "LOW":
                score -= 2
            # INFO does not affect score

        score = max(0, min(100, score))

        # Valid if no CRITICAL issues and score >= 40
        is_valid = critical == 0 and score >= 40

        return ValidationResult(
            is_valid=is_valid,
            score=score,
            issues=issues,
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            passed_rules=passed_rules,
            metadata=metadata,
        )


# =============================================================================
# SINGLETON
# =============================================================================

_engine_instance: Optional[DocumentValidationEngine] = None


def get_document_validation_engine() -> DocumentValidationEngine:
    """Get or create the singleton DocumentValidationEngine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = DocumentValidationEngine()
    return _engine_instance
