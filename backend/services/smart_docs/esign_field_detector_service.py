"""
E-Signature Field Auto-Detection Service

Intelligently identifies where signature, initial, date, and text fields
should be placed on a document for e-signing.  Works with the built-in
e-signature system (no third-party providers).

Detection Strategies:
  1. Text pattern matching: regex-based detection of signature lines,
     initial fields, date blanks, and text input areas.
  2. Mortgage form intelligence: pre-mapped field positions for common
     mortgage forms (1003, 1004, 1008, 4506-T, LOE templates).
  3. AI vision analysis: Claude Vision API for complex/non-standard
     form layouts when text extraction alone is insufficient.

Each detected field is assigned:
  - A type (signature, initial, date_signed, text, checkbox, full_name)
  - Page-level coordinates (page, x, y, width, height in points)
  - A signer role (borrower, co_borrower, notary, loan_officer, etc.)
  - A confidence score (0-100)
  - A required/optional flag
  - A tab order for navigation
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from pdf2image import convert_from_bytes
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class DetectedFieldType(str, Enum):
    """Field type detected on the document."""
    SIGNATURE = "signature"
    INITIAL = "initial"
    DATE_SIGNED = "date_signed"
    TEXT = "text"
    CHECKBOX = "checkbox"
    FULL_NAME = "full_name"
    TITLE = "title"
    COMPANY = "company"


class SignerRole(str, Enum):
    """Role of the person who should fill this field."""
    BORROWER = "borrower"
    CO_BORROWER = "co_borrower"
    LOAN_OFFICER = "loan_officer"
    NOTARY = "notary"
    SELLER = "seller"
    WITNESS = "witness"
    UNKNOWN = "unknown"


class DetectionMethod(str, Enum):
    """How the field was detected."""
    TEXT_PATTERN = "text_pattern"
    FORM_TEMPLATE = "form_template"
    AI_VISION = "ai_vision"
    LINE_GEOMETRY = "line_geometry"
    MANUAL_CORRECTION = "manual_correction"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DetectedField:
    """A single field detected on the document."""
    field_id: str
    field_type: DetectedFieldType
    page: int
    x: float
    y: float
    width: float
    height: float
    confidence: int  # 0-100
    signer_role: SignerRole = SignerRole.UNKNOWN
    label: str = ""
    is_required: bool = True
    tab_order: int = 0
    group_id: Optional[str] = None
    detection_method: DetectionMethod = DetectionMethod.TEXT_PATTERN
    context_text: str = ""
    placeholder: str = ""
    validation_regex: Optional[str] = None
    exclude_from_esign: bool = False  # True for notary-only sections

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_id": self.field_id,
            "field_type": self.field_type.value,
            "page": self.page,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "width": round(self.width, 1),
            "height": round(self.height, 1),
            "confidence": self.confidence,
            "signer_role": self.signer_role.value,
            "label": self.label,
            "is_required": self.is_required,
            "tab_order": self.tab_order,
            "group_id": self.group_id,
            "detection_method": self.detection_method.value,
            "context_text": self.context_text[:200],
            "placeholder": self.placeholder,
            "validation_regex": self.validation_regex,
            "exclude_from_esign": self.exclude_from_esign,
        }


@dataclass
class FormIdentification:
    """Result of identifying a known mortgage form."""
    form_id: Optional[str] = None  # e.g. "1003", "4506-T"
    form_name: str = ""
    confidence: int = 0
    version: str = ""
    page_count_expected: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DetectionResult:
    """Complete result from field detection on a document."""
    success: bool
    fields: List[DetectedField] = field(default_factory=list)
    form_identification: Optional[FormIdentification] = None
    page_count: int = 0
    signer_roles_found: List[str] = field(default_factory=list)
    detection_duration_ms: int = 0
    detection_methods_used: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def field_count(self) -> int:
        return len(self.fields)

    @property
    def fields_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for f in self.fields:
            key = f.field_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    @property
    def fields_by_signer(self) -> Dict[str, List[DetectedField]]:
        groups: Dict[str, List[DetectedField]] = {}
        for f in self.fields:
            key = f.signer_role.value
            groups.setdefault(key, []).append(f)
        return groups

    @property
    def esignable_fields(self) -> List[DetectedField]:
        """Fields that should be presented for e-signing (excludes notary sections)."""
        return [f for f in self.fields if not f.exclude_from_esign]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "fields": [f.to_dict() for f in self.fields],
            "esignable_fields": [f.to_dict() for f in self.esignable_fields],
            "form_identification": self.form_identification.to_dict() if self.form_identification else None,
            "page_count": self.page_count,
            "field_count": self.field_count,
            "fields_by_type": self.fields_by_type,
            "signer_roles_found": self.signer_roles_found,
            "detection_duration_ms": self.detection_duration_ms,
            "detection_methods_used": self.detection_methods_used,
            "warnings": self.warnings,
            "error": self.error,
        }


# =============================================================================
# TEXT PATTERNS FOR FIELD DETECTION
# =============================================================================

# Signature line patterns (regex, label hint, required flag)
SIGNATURE_PATTERNS: List[Tuple[re.Pattern, str, bool]] = [
    (re.compile(r"(?i)(?:borrower['s]*\s+)?signature\s*[:_\-]?\s*[_\-]{3,}"), "Borrower Signature", True),
    (re.compile(r"(?i)co[\-\s]?borrower['s]*\s+signature\s*[:_\-]?\s*[_\-]{3,}"), "Co-Borrower Signature", True),
    (re.compile(r"(?i)(?:authorized\s+)?signature\s*[:_\-]?\s*[_\-]{3,}"), "Signature", True),
    (re.compile(r"(?i)sign\s+here\s*[:_\-]?\s*[_\-]{3,}"), "Sign Here", True),
    (re.compile(r"(?i)loan\s+officer['s]*\s+signature\s*[:_\-]?\s*[_\-]{3,}"), "Loan Officer Signature", True),
    (re.compile(r"(?i)lender['s]*\s+signature\s*[:_\-]?\s*[_\-]{3,}"), "Lender Signature", True),
    (re.compile(r"(?i)seller['s]*\s+signature\s*[:_\-]?\s*[_\-]{3,}"), "Seller Signature", False),
    (re.compile(r"(?i)notary\s+(?:public\s+)?signature\s*[:_\-]?\s*[_\-]{3,}"), "Notary Signature", True),
    (re.compile(r"(?i)witness\s+signature\s*[:_\-]?\s*[_\-]{3,}"), "Witness Signature", False),
    (re.compile(r"X\s*[_]{5,}"), "Signature (X mark)", True),
    (re.compile(r"[_]{15,}\s*\n\s*(?:Signature|Sign)", re.MULTILINE), "Signature Line", True),
    (re.compile(r"(?i)by:\s*[_\-]{5,}"), "Signature (by line)", True),
]

# Initials patterns
INITIALS_PATTERNS: List[Tuple[re.Pattern, str, bool]] = [
    (re.compile(r"(?i)initial(?:s)?\s*[:_\-]?\s*[_\-]{2,}"), "Initials", True),
    (re.compile(r"(?i)borrower['s]*\s+initials?\s*[:_\-]?\s*[_\-]{2,}"), "Borrower Initials", True),
    (re.compile(r"(?i)co[\-\s]?borrower['s]*\s+initials?\s*[:_\-]?\s*[_\-]{2,}"), "Co-Borrower Initials", True),
    (re.compile(r"(?i)initial\s+here"), "Initial Here", True),
    (re.compile(r"(?i)\[\s*initials?\s*\]"), "Initials (bracketed)", True),
    (re.compile(r"(?i)(?:acknowledge|acknowledgment).{0,80}initial", re.DOTALL), "Acknowledgment Initials", True),
]

# Date field patterns
DATE_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"(?i)date\s*[:_\-]?\s*[_\-]{3,}"), "Date", r"^\d{1,2}/\d{1,2}/\d{4}$"),
    (re.compile(r"(?i)dated?\s*(?:this)?\s*[:_\-]?\s*[_\-]{3,}"), "Date", r"^\d{1,2}/\d{1,2}/\d{4}$"),
    (re.compile(r"(?i)date\s+signed\s*[:_\-]?\s*[_\-]{3,}"), "Date Signed", r"^\d{1,2}/\d{1,2}/\d{4}$"),
    (re.compile(r"MM\s*/\s*DD\s*/\s*YYYY"), "Date (MM/DD/YYYY)", r"^\d{2}/\d{2}/\d{4}$"),
    (re.compile(r"__/__/____"), "Date (formatted)", r"^\d{2}/\d{2}/\d{4}$"),
    (re.compile(r"(?i)dated\s+this\s+[_]+\s*day\s+of\s+[_]+"), "Date (formal)", None),
    (re.compile(r"(?i)(?:execution|effective)\s+date\s*[:_\-]?\s*[_\-]{3,}"), "Execution Date", r"^\d{1,2}/\d{1,2}/\d{4}$"),
]

# Text input field patterns
TEXT_PATTERNS: List[Tuple[re.Pattern, str, str, Optional[str]]] = [
    (re.compile(r"(?i)(?:print(?:ed)?)\s+name\s*[:_\-]?\s*[_\-]{3,}"), "Printed Name", "full_name", None),
    (re.compile(r"(?i)(?:borrower['s]*\s+)?name\s*[:_\-]?\s*[_\-]{5,}"), "Name", "full_name", None),
    (re.compile(r"(?i)address\s*[:_\-]?\s*[_\-]{5,}"), "Address", "text", None),
    (re.compile(r"(?i)(?:property\s+)?address\s*[:_\-]?\s*[_\-]{5,}"), "Property Address", "text", None),
    (re.compile(r"(?i)(?:email|e-mail)\s*(?:address)?\s*[:_\-]?\s*[_\-]{5,}"), "Email Address", "text", r"^[^@]+@[^@]+\.[^@]+$"),
    (re.compile(r"(?i)phone\s*(?:number|#)?\s*[:_\-]?\s*[_\-]{5,}"), "Phone Number", "text", r"^\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}$"),
    (re.compile(r"(?i)(?:social\s+security|ss[#n]|ssn)\s*[:_\-]?\s*[_\-]{3,}"), "SSN", "text", r"^\d{3}-?\d{2}-?\d{4}$"),
    (re.compile(r"(?i)loan\s*(?:number|#|no\.?)\s*[:_\-]?\s*[_\-]{3,}"), "Loan Number", "text", None),
    (re.compile(r"(?i)title\s*[:_\-]?\s*[_\-]{5,}"), "Title", "title", None),
    (re.compile(r"(?i)company\s*(?:name)?\s*[:_\-]?\s*[_\-]{5,}"), "Company", "company", None),
    (re.compile(r"(?i)nmls\s*(?:#|id|number)?\s*[:_\-]?\s*[_\-]{3,}"), "NMLS ID", "text", r"^\d{4,10}$"),
    (re.compile(r"\[\s{5,}\]"), "Fill-in field (brackets)", "text", None),
    (re.compile(r"(?i)employer(?:'s)?\s+name\s*[:_\-]?\s*[_\-]{3,}"), "Employer Name", "text", None),
]

# Checkbox patterns
CHECKBOX_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)\[\s*\]\s+(.{3,80})"), "Checkbox"),
    (re.compile(r"(?i)(?:yes|no)\s*\[\s*\]"), "Yes/No Checkbox"),
    (re.compile(r"(?i)\( \)\s+(.{3,80})"), "Checkbox (parentheses)"),
]

# Notary section patterns (these fields should be excluded from e-sign)
NOTARY_SECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"(?i)notary\s+public", re.MULTILINE),
    re.compile(r"(?i)state\s+of\s+.{2,30}\s*\n\s*county\s+of", re.MULTILINE),
    re.compile(r"(?i)sworn\s+(?:to\s+)?(?:and\s+)?subscribed\s+before\s+me", re.MULTILINE),
    re.compile(r"(?i)my\s+commission\s+expires", re.MULTILINE),
    re.compile(r"(?i)acknowledgment|acknowledgement", re.MULTILINE),
    re.compile(r"(?i)notarial\s+(?:seal|certificate)", re.MULTILINE),
]


# =============================================================================
# KNOWN MORTGAGE FORM DEFINITIONS
# =============================================================================

# Form fingerprints: text fragments unique to each form type
FORM_FINGERPRINTS: Dict[str, List[Tuple[str, int]]] = {
    "1003": [
        ("Uniform Residential Loan Application", 40),
        ("URLA", 20),
        ("Section 1: Borrower Information", 15),
        ("Section 2: Financial Information", 15),
        ("Section 3: Financial Information", 10),
        ("Section 4: Loan and Property Information", 15),
        ("Section 5: Declarations", 10),
        ("Section 6: Acknowledgments", 10),
        ("Section 7: Military Service", 8),
        ("Section 8: Demographic Information", 8),
        ("Section 9: Loan Originator Information", 10),
    ],
    "1004": [
        ("Uniform Residential Appraisal Report", 40),
        ("URAR", 20),
        ("Subject", 5),
        ("Contract", 5),
        ("Neighborhood", 5),
        ("Site", 5),
        ("Improvements", 5),
        ("Sales Comparison Approach", 10),
        ("Cost Approach", 8),
        ("Income Approach", 8),
        ("Appraiser", 8),
    ],
    "1008": [
        ("Transmittal Summary", 30),
        ("Uniform Underwriting", 15),
        ("Freddie Mac Form 1077", 10),
        ("Fannie Mae Form 1008", 20),
        ("Risk Classification", 10),
        ("Underwriter Recommendation", 15),
    ],
    "4506-T": [
        ("Request for Transcript of Tax Return", 40),
        ("4506-T", 30),
        ("Internal Revenue Service", 10),
        ("Return Transcript", 10),
        ("Tax Periods", 8),
        ("Signatory attests", 8),
    ],
    "4506-C": [
        ("IVES Request for Transcript", 40),
        ("4506-C", 30),
        ("Intermediate Service Provider", 10),
    ],
    "LOE": [
        ("Letter of Explanation", 35),
        ("LOE", 10),
        ("I hereby acknowledge", 8),
        ("explain the following", 10),
        ("To Whom It May Concern", 8),
    ],
    "CD": [
        ("Closing Disclosure", 40),
        ("Loan Terms", 10),
        ("Projected Payments", 10),
        ("Costs at Closing", 10),
        ("Loan Calculations", 8),
        ("Total Interest Percentage", 8),
    ],
    "LE": [
        ("Loan Estimate", 40),
        ("Estimated", 5),
        ("Loan Terms", 10),
        ("Projected Payments", 10),
        ("Costs at Closing", 10),
        ("Comparisons", 8),
    ],
}

# Pre-mapped field positions for known forms.
# Coordinates are in points (72 points/inch) from top-left page origin,
# assuming US Letter (612 x 792 points).
FORM_FIELD_MAPS: Dict[str, List[Dict[str, Any]]] = {
    "1003": [
        # Page 5 / Section 6 — Borrower acknowledgment signature
        {
            "field_type": "signature", "page": 5, "x": 72, "y": 650,
            "width": 200, "height": 30, "label": "Borrower Signature",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "date_signed", "page": 5, "x": 400, "y": 650,
            "width": 140, "height": 20, "label": "Date",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "signature", "page": 5, "x": 72, "y": 700,
            "width": 200, "height": 30, "label": "Co-Borrower Signature",
            "signer_role": "co_borrower", "required": False,
        },
        {
            "field_type": "date_signed", "page": 5, "x": 400, "y": 700,
            "width": 140, "height": 20, "label": "Date",
            "signer_role": "co_borrower", "required": False,
        },
        # Section 9 — Loan Originator
        {
            "field_type": "signature", "page": 6, "x": 72, "y": 680,
            "width": 200, "height": 30, "label": "Loan Originator Signature",
            "signer_role": "loan_officer", "required": True,
        },
        {
            "field_type": "date_signed", "page": 6, "x": 400, "y": 680,
            "width": 140, "height": 20, "label": "Date",
            "signer_role": "loan_officer", "required": True,
        },
        {
            "field_type": "text", "page": 6, "x": 72, "y": 710,
            "width": 200, "height": 18, "label": "Loan Originator NMLS ID",
            "signer_role": "loan_officer", "required": True,
        },
    ],
    "4506-T": [
        # Signature block at bottom of the single-page form
        {
            "field_type": "signature", "page": 1, "x": 72, "y": 635,
            "width": 220, "height": 30, "label": "Signature",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "date_signed", "page": 1, "x": 420, "y": 635,
            "width": 140, "height": 20, "label": "Date",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "full_name", "page": 1, "x": 72, "y": 665,
            "width": 220, "height": 18, "label": "Print Name",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "title", "page": 1, "x": 420, "y": 665,
            "width": 140, "height": 18, "label": "Title (if applicable)",
            "signer_role": "borrower", "required": False,
        },
        # Second signature line for spouse/co-borrower
        {
            "field_type": "signature", "page": 1, "x": 72, "y": 695,
            "width": 220, "height": 30, "label": "Spouse/Co-Borrower Signature",
            "signer_role": "co_borrower", "required": False,
        },
        {
            "field_type": "date_signed", "page": 1, "x": 420, "y": 695,
            "width": 140, "height": 20, "label": "Date",
            "signer_role": "co_borrower", "required": False,
        },
    ],
    "4506-C": [
        {
            "field_type": "signature", "page": 1, "x": 72, "y": 620,
            "width": 220, "height": 30, "label": "Signature",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "date_signed", "page": 1, "x": 420, "y": 620,
            "width": 140, "height": 20, "label": "Date",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "full_name", "page": 1, "x": 72, "y": 655,
            "width": 220, "height": 18, "label": "Print Name",
            "signer_role": "borrower", "required": True,
        },
    ],
    "LOE": [
        # Typical single-page letter of explanation
        {
            "field_type": "signature", "page": 1, "x": 72, "y": 600,
            "width": 220, "height": 30, "label": "Borrower Signature",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "date_signed", "page": 1, "x": 420, "y": 600,
            "width": 140, "height": 20, "label": "Date",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "full_name", "page": 1, "x": 72, "y": 640,
            "width": 220, "height": 18, "label": "Print Name",
            "signer_role": "borrower", "required": True,
        },
    ],
    "CD": [
        # Page 5 — Closing Disclosure signature page
        {
            "field_type": "signature", "page": 5, "x": 72, "y": 480,
            "width": 220, "height": 30, "label": "Borrower Signature",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "date_signed", "page": 5, "x": 400, "y": 480,
            "width": 140, "height": 20, "label": "Date",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "signature", "page": 5, "x": 72, "y": 530,
            "width": 220, "height": 30, "label": "Co-Borrower Signature",
            "signer_role": "co_borrower", "required": False,
        },
        {
            "field_type": "date_signed", "page": 5, "x": 400, "y": 530,
            "width": 140, "height": 20, "label": "Date",
            "signer_role": "co_borrower", "required": False,
        },
        {
            "field_type": "signature", "page": 5, "x": 72, "y": 590,
            "width": 220, "height": 30, "label": "Seller Signature",
            "signer_role": "seller", "required": False,
        },
        {
            "field_type": "date_signed", "page": 5, "x": 400, "y": 590,
            "width": 140, "height": 20, "label": "Date",
            "signer_role": "seller", "required": False,
        },
    ],
    "LE": [
        # Page 3 — Loan Estimate confirmation
        {
            "field_type": "signature", "page": 3, "x": 72, "y": 580,
            "width": 220, "height": 30, "label": "Borrower Signature",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "date_signed", "page": 3, "x": 400, "y": 580,
            "width": 140, "height": 20, "label": "Date",
            "signer_role": "borrower", "required": True,
        },
        {
            "field_type": "signature", "page": 3, "x": 72, "y": 630,
            "width": 220, "height": 30, "label": "Co-Borrower Signature",
            "signer_role": "co_borrower", "required": False,
        },
        {
            "field_type": "date_signed", "page": 3, "x": 400, "y": 630,
            "width": 140, "height": 20, "label": "Date",
            "signer_role": "co_borrower", "required": False,
        },
    ],
}


# =============================================================================
# SIGNER ROLE INFERENCE
# =============================================================================

_ROLE_KEYWORDS: Dict[SignerRole, List[str]] = {
    SignerRole.BORROWER: [
        "borrower", "applicant", "buyer", "mortgagor", "obligor",
    ],
    SignerRole.CO_BORROWER: [
        "co-borrower", "coborrower", "co borrower", "co-applicant",
        "co applicant", "joint applicant", "spouse",
    ],
    SignerRole.LOAN_OFFICER: [
        "loan officer", "loan originator", "originator", "lender",
        "lender representative", "nmls",
    ],
    SignerRole.NOTARY: [
        "notary", "notarial", "sworn", "subscribed before me",
        "commission expires",
    ],
    SignerRole.SELLER: [
        "seller", "vendor", "grantor",
    ],
    SignerRole.WITNESS: [
        "witness",
    ],
}


def _infer_signer_role(context: str) -> SignerRole:
    """Infer the signer role from surrounding text context."""
    lower = context.lower()
    # Check co-borrower first (more specific than borrower)
    for keyword in _ROLE_KEYWORDS[SignerRole.CO_BORROWER]:
        if keyword in lower:
            return SignerRole.CO_BORROWER
    for role, keywords in _ROLE_KEYWORDS.items():
        if role == SignerRole.CO_BORROWER:
            continue
        for keyword in keywords:
            if keyword in lower:
                return role
    return SignerRole.UNKNOWN


def _is_in_notary_section(text: str, match_start: int, page_text: str) -> bool:
    """Determine if a match position falls within a notary section."""
    # Look backwards from the match position for notary markers within 500 chars
    lookback = page_text[max(0, match_start - 500):match_start].lower()
    for pattern in NOTARY_SECTION_PATTERNS:
        if pattern.search(lookback):
            return True
    return False


# =============================================================================
# E-SIGN FIELD DETECTOR SERVICE
# =============================================================================

class ESignFieldDetectorService:
    """
    Auto-detects e-signature field placements on mortgage documents.

    Detection pipeline:
      1. Extract text from each page (pdfplumber or OCR fallback).
      2. Identify the form type using text fingerprints.
      3. If a known form is detected with high confidence, use the
         pre-mapped field positions from FORM_FIELD_MAPS.
      4. Otherwise, run regex-based pattern detection across all pages.
      5. Optionally, invoke Claude Vision API for complex layouts.
      6. Assign tab order, deduplicate, and return results.

    Thread-safety: instances are stateless beyond configuration and can
    be shared across requests.
    """

    def __init__(self):
        self._anthropic = Anthropic() if HAS_ANTHROPIC else None
        self._vision_model = os.getenv("ANTHROPIC_VISION_MODEL", "claude-sonnet-4-20250514")
        self._enable_ai_vision = os.getenv("ESIGN_ENABLE_AI_VISION", "false").lower() == "true"
        # Minimum confidence to include a detected field in results
        self._min_confidence = int(os.getenv("ESIGN_MIN_FIELD_CONFIDENCE", "30"))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_fields(
        self,
        file_content: bytes,
        mime_type: str = "application/pdf",
        use_ai_vision: Optional[bool] = None,
        signer_names: Optional[Dict[str, str]] = None,
    ) -> DetectionResult:
        """
        Detect all signable fields in a document.

        Args:
            file_content: Raw bytes of the document (PDF or image).
            mime_type: MIME type of the document.
            use_ai_vision: Override for AI vision (None = use env default).
            signer_names: Optional mapping of role -> name for
                personalized field labels, e.g.
                {"borrower": "Jane Doe", "co_borrower": "John Doe"}.

        Returns:
            DetectionResult containing all detected fields and metadata.
        """
        start_time = time.time()
        methods_used: List[str] = []
        warnings: List[str] = []
        all_fields: List[DetectedField] = []

        try:
            # Step 1: Extract per-page text
            pages_text = self._extract_pages_text(file_content, mime_type)
            if not pages_text:
                return DetectionResult(
                    success=False,
                    error="Could not extract any text from the document",
                    detection_duration_ms=self._elapsed_ms(start_time),
                )

            page_count = len(pages_text)

            # Step 2: Identify the form
            form_id = self._identify_form(pages_text)

            # Step 3: Use pre-mapped fields if we have a high-confidence match
            if form_id and form_id.confidence >= 70 and form_id.form_id in FORM_FIELD_MAPS:
                template_fields = self._apply_form_template(form_id.form_id, page_count)
                all_fields.extend(template_fields)
                methods_used.append(DetectionMethod.FORM_TEMPLATE.value)
                logger.info(
                    "Applied form template '%s' (%d fields, confidence=%d)",
                    form_id.form_id, len(template_fields), form_id.confidence,
                )
            else:
                if form_id and form_id.confidence > 0:
                    warnings.append(
                        f"Form resembles '{form_id.form_id}' (confidence {form_id.confidence}%) "
                        "but below threshold for template — using pattern detection."
                    )

            # Step 4: Pattern-based detection on every page
            pattern_fields = self._detect_from_patterns(pages_text)
            if pattern_fields:
                methods_used.append(DetectionMethod.TEXT_PATTERN.value)

            # Step 5: Horizontal-line detection (pdfplumber geometry)
            if HAS_PDFPLUMBER and mime_type == "application/pdf":
                line_fields = self._detect_from_line_geometry(file_content)
                if line_fields:
                    methods_used.append(DetectionMethod.LINE_GEOMETRY.value)
                    pattern_fields.extend(line_fields)

            # Step 6: Merge pattern fields with template fields (deduplicate)
            all_fields = self._merge_fields(all_fields, pattern_fields)

            # Step 7: AI Vision (optional)
            should_use_vision = use_ai_vision if use_ai_vision is not None else self._enable_ai_vision
            if should_use_vision and self._anthropic and mime_type == "application/pdf":
                try:
                    vision_fields = self._detect_with_ai_vision(file_content, pages_text)
                    if vision_fields:
                        methods_used.append(DetectionMethod.AI_VISION.value)
                        all_fields = self._merge_fields(all_fields, vision_fields)
                except Exception as e:
                    logger.warning("AI vision detection failed: %s", e)
                    warnings.append(f"AI vision detection failed: {e}")

            # Step 8: Filter low-confidence fields
            all_fields = [f for f in all_fields if f.confidence >= self._min_confidence]

            # Step 9: Mark notary-section fields
            self._mark_notary_exclusions(all_fields, pages_text)

            # Step 10: Assign tab order and group IDs
            self._assign_tab_order(all_fields)
            self._assign_groups(all_fields)

            # Step 11: Apply signer names to labels
            if signer_names:
                self._apply_signer_names(all_fields, signer_names)

            # Collect unique signer roles
            signer_roles = sorted({f.signer_role.value for f in all_fields if f.signer_role != SignerRole.UNKNOWN})

            duration_ms = self._elapsed_ms(start_time)
            logger.info(
                "Field detection complete: %d fields on %d pages in %dms (methods: %s)",
                len(all_fields), page_count, duration_ms, ", ".join(methods_used),
            )

            return DetectionResult(
                success=True,
                fields=all_fields,
                form_identification=form_id,
                page_count=page_count,
                signer_roles_found=signer_roles,
                detection_duration_ms=duration_ms,
                detection_methods_used=methods_used,
                warnings=warnings,
            )

        except Exception as e:
            logger.exception("Field detection failed: %s", e)
            return DetectionResult(
                success=False,
                error=str(e),
                detection_duration_ms=self._elapsed_ms(start_time),
            )

    def detect_fields_for_envelope(
        self,
        file_content: bytes,
        mime_type: str = "application/pdf",
        recipients: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """
        Detect fields and format them for ESignatureEnvelope creation.

        Returns a list of field dicts compatible with the
        ``EnvelopeCreateRequest.fields`` structure expected by the
        envelope service.

        Args:
            file_content: Raw document bytes.
            mime_type: MIME type.
            recipients: Optional list of recipient dicts with "name",
                "email", and "type" keys.  Used to map detected signer
                roles to recipient indices.

        Returns:
            List of field dicts with keys: type, page, x, y, width,
            height, recipient_index, required, label, placeholder.
        """
        result = self.detect_fields(file_content, mime_type)
        if not result.success:
            logger.warning("Field detection failed; returning empty field list: %s", result.error)
            return []

        # Build role -> recipient index mapping
        role_to_index: Dict[str, int] = {}
        if recipients:
            for idx, r in enumerate(recipients):
                rtype = r.get("type", "signer")
                if rtype == "signer":
                    rname = r.get("name", "").lower()
                    # Heuristic: first signer = borrower, second = co-borrower
                    if idx == 0:
                        role_to_index.setdefault("borrower", idx)
                    elif idx == 1:
                        role_to_index.setdefault("co_borrower", idx)
                    role_to_index.setdefault("unknown", idx)

        envelope_fields = []
        for f in result.esignable_fields:
            recipient_idx = role_to_index.get(f.signer_role.value, role_to_index.get("unknown", 0))
            envelope_fields.append({
                "type": f.field_type.value,
                "page": f.page,
                "x": round(f.x, 1),
                "y": round(f.y, 1),
                "width": round(f.width, 1),
                "height": round(f.height, 1),
                "recipient_index": recipient_idx,
                "required": f.is_required,
                "label": f.label,
                "placeholder": f.placeholder,
                "validation_regex": f.validation_regex,
            })

        return envelope_fields

    def learn_from_correction(
        self,
        document_hash: str,
        original_fields: List[Dict],
        corrected_fields: List[Dict],
    ) -> Dict[str, Any]:
        """
        Record a manual correction to field placements for future learning.

        This stores the delta between auto-detected and human-corrected
        fields so that future detections on similar documents can benefit.
        Currently stores the correction record; a separate training pipeline
        would consume these records to fine-tune detection heuristics.

        Args:
            document_hash: SHA-256 hash of the document.
            original_fields: Fields as originally detected.
            corrected_fields: Fields after human correction.

        Returns:
            Summary dict with correction_id and delta stats.
        """
        correction_id = f"CORR-{uuid.uuid4().hex[:12].upper()}"

        added = []
        removed = []
        moved = []

        original_ids = {f.get("field_id") for f in original_fields}
        corrected_ids = {f.get("field_id") for f in corrected_fields}

        for cf in corrected_fields:
            fid = cf.get("field_id")
            if fid and fid not in original_ids:
                added.append(cf)
            elif fid:
                # Check if position changed
                orig = next((of for of in original_fields if of.get("field_id") == fid), None)
                if orig:
                    dx = abs(cf.get("x", 0) - orig.get("x", 0))
                    dy = abs(cf.get("y", 0) - orig.get("y", 0))
                    if dx > 5 or dy > 5:
                        moved.append({"field_id": fid, "dx": dx, "dy": dy})

        for of in original_fields:
            fid = of.get("field_id")
            if fid and fid not in corrected_ids:
                removed.append(of)

        summary = {
            "correction_id": correction_id,
            "document_hash": document_hash,
            "fields_added": len(added),
            "fields_removed": len(removed),
            "fields_moved": len(moved),
            "total_corrections": len(added) + len(removed) + len(moved),
            "timestamp": time.time(),
        }

        logger.info(
            "Recorded field correction %s: +%d -%d ~%d",
            correction_id, len(added), len(removed), len(moved),
        )

        return summary

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    def _extract_pages_text(
        self,
        file_content: bytes,
        mime_type: str,
    ) -> List[str]:
        """Extract text from each page. Returns list of per-page text strings."""
        if mime_type == "application/pdf":
            return self._extract_pdf_pages(file_content)
        elif mime_type.startswith("image/"):
            # Single-page image
            text = self._extract_image_text(file_content)
            return [text] if text else []
        else:
            try:
                text = file_content.decode("utf-8")
                return [text] if text.strip() else []
            except Exception:
                return []

    def _extract_pdf_pages(self, file_content: bytes) -> List[str]:
        """Extract text per page using pdfplumber."""
        pages: List[str] = []
        if not HAS_PDFPLUMBER:
            logger.warning("pdfplumber not available; cannot extract PDF text")
            return pages

        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for page in pdf.pages[:50]:  # Cap at 50 pages
                    page_text = page.extract_text() or ""
                    pages.append(page_text)
        except Exception as e:
            logger.warning("pdfplumber extraction failed: %s", e)

        # If we got no text from any page, try OCR fallback
        total_text = sum(len(p.strip()) for p in pages)
        if total_text < 100 and HAS_PDF2IMAGE:
            try:
                images = convert_from_bytes(file_content, first_page=1, last_page=10)
                pages = []
                for img in images:
                    ocr_text = self._ocr_image(img)
                    pages.append(ocr_text)
            except Exception as e:
                logger.warning("OCR fallback failed: %s", e)

        return pages

    def _extract_image_text(self, file_content: bytes) -> str:
        """Extract text from a single image using OCR."""
        try:
            from PIL import Image
            import pytesseract
            img = Image.open(io.BytesIO(file_content))
            return pytesseract.image_to_string(img)
        except ImportError:
            logger.warning("PIL/pytesseract not available for OCR")
            return ""
        except Exception as e:
            logger.warning("Image OCR failed: %s", e)
            return ""

    def _ocr_image(self, image) -> str:
        """OCR a PIL Image object."""
        try:
            import pytesseract
            return pytesseract.image_to_string(image)
        except Exception as e:
            logger.warning("OCR failed on image: %s", e)
            return ""

    # ------------------------------------------------------------------
    # Form identification
    # ------------------------------------------------------------------

    def _identify_form(self, pages_text: List[str]) -> Optional[FormIdentification]:
        """Identify the mortgage form type by scoring text fingerprints."""
        full_text = "\n".join(pages_text).lower()
        if len(full_text) < 50:
            return None

        best_form: Optional[str] = None
        best_score = 0
        best_max_possible = 1  # avoid division by zero

        for form_id, fingerprints in FORM_FINGERPRINTS.items():
            score = 0
            max_possible = sum(weight for _, weight in fingerprints)
            for phrase, weight in fingerprints:
                if phrase.lower() in full_text:
                    score += weight
            if score > best_score:
                best_score = score
                best_form = form_id
                best_max_possible = max_possible

        if best_form is None or best_score == 0:
            return None

        confidence = min(100, int((best_score / best_max_possible) * 100))

        form_names = {
            "1003": "Uniform Residential Loan Application",
            "1004": "Uniform Residential Appraisal Report",
            "1008": "Transmittal Summary",
            "4506-T": "Request for Transcript of Tax Return",
            "4506-C": "IVES Request for Transcript of Tax Return",
            "LOE": "Letter of Explanation",
            "CD": "Closing Disclosure",
            "LE": "Loan Estimate",
        }

        return FormIdentification(
            form_id=best_form,
            form_name=form_names.get(best_form, best_form),
            confidence=confidence,
            page_count_expected=len(pages_text),
        )

    # ------------------------------------------------------------------
    # Template-based detection
    # ------------------------------------------------------------------

    def _apply_form_template(
        self,
        form_id: str,
        actual_page_count: int,
    ) -> List[DetectedField]:
        """Apply pre-mapped field positions from FORM_FIELD_MAPS."""
        template = FORM_FIELD_MAPS.get(form_id, [])
        fields: List[DetectedField] = []

        for entry in template:
            page = entry["page"]
            # Skip fields on pages that don't exist in the actual document
            if page > actual_page_count:
                continue

            field_type_str = entry["field_type"]
            try:
                ft = DetectedFieldType(field_type_str)
            except ValueError:
                ft = DetectedFieldType.TEXT

            signer_str = entry.get("signer_role", "unknown")
            try:
                sr = SignerRole(signer_str)
            except ValueError:
                sr = SignerRole.UNKNOWN

            fields.append(DetectedField(
                field_id=f"tmpl-{form_id}-{uuid.uuid4().hex[:8]}",
                field_type=ft,
                page=page,
                x=entry["x"],
                y=entry["y"],
                width=entry["width"],
                height=entry["height"],
                confidence=85,  # Template fields get high confidence
                signer_role=sr,
                label=entry.get("label", ""),
                is_required=entry.get("required", True),
                detection_method=DetectionMethod.FORM_TEMPLATE,
            ))

        return fields

    # ------------------------------------------------------------------
    # Pattern-based detection
    # ------------------------------------------------------------------

    def _detect_from_patterns(self, pages_text: List[str]) -> List[DetectedField]:
        """Run regex patterns against each page to detect fields."""
        fields: List[DetectedField] = []

        for page_idx, page_text in enumerate(pages_text):
            page_num = page_idx + 1
            if not page_text.strip():
                continue

            # Estimate vertical position from character offset.
            # Assume ~80 characters per line, ~12 points per line.
            page_lines = page_text.split("\n")
            total_lines = max(len(page_lines), 1)

            # Signature fields
            for pattern, label, required in SIGNATURE_PATTERNS:
                for match in pattern.finditer(page_text):
                    line_num = page_text[:match.start()].count("\n")
                    y_pos = self._estimate_y_from_line(line_num, total_lines)
                    x_pos = self._estimate_x_from_offset(match.start(), page_text, line_num)
                    context = self._get_context(page_text, match.start(), 150)

                    fields.append(DetectedField(
                        field_id=f"sig-{page_num}-{uuid.uuid4().hex[:8]}",
                        field_type=DetectedFieldType.SIGNATURE,
                        page=page_num,
                        x=x_pos,
                        y=y_pos,
                        width=200,
                        height=30,
                        confidence=75,
                        signer_role=_infer_signer_role(context),
                        label=label,
                        is_required=required,
                        detection_method=DetectionMethod.TEXT_PATTERN,
                        context_text=context,
                    ))

            # Initials fields
            for pattern, label, required in INITIALS_PATTERNS:
                for match in pattern.finditer(page_text):
                    line_num = page_text[:match.start()].count("\n")
                    y_pos = self._estimate_y_from_line(line_num, total_lines)
                    x_pos = self._estimate_x_from_offset(match.start(), page_text, line_num)
                    context = self._get_context(page_text, match.start(), 100)

                    fields.append(DetectedField(
                        field_id=f"init-{page_num}-{uuid.uuid4().hex[:8]}",
                        field_type=DetectedFieldType.INITIAL,
                        page=page_num,
                        x=x_pos,
                        y=y_pos,
                        width=60,
                        height=25,
                        confidence=70,
                        signer_role=_infer_signer_role(context),
                        label=label,
                        is_required=required,
                        detection_method=DetectionMethod.TEXT_PATTERN,
                        context_text=context,
                    ))

            # Date fields
            for pattern, label, validation in DATE_PATTERNS:
                for match in pattern.finditer(page_text):
                    line_num = page_text[:match.start()].count("\n")
                    y_pos = self._estimate_y_from_line(line_num, total_lines)
                    x_pos = self._estimate_x_from_offset(match.start(), page_text, line_num)
                    context = self._get_context(page_text, match.start(), 100)

                    fields.append(DetectedField(
                        field_id=f"date-{page_num}-{uuid.uuid4().hex[:8]}",
                        field_type=DetectedFieldType.DATE_SIGNED,
                        page=page_num,
                        x=x_pos,
                        y=y_pos,
                        width=140,
                        height=20,
                        confidence=70,
                        signer_role=_infer_signer_role(context),
                        label=label,
                        is_required=True,
                        detection_method=DetectionMethod.TEXT_PATTERN,
                        context_text=context,
                        placeholder="MM/DD/YYYY",
                        validation_regex=validation,
                    ))

            # Text input fields
            for pattern, label, subtype, validation in TEXT_PATTERNS:
                for match in pattern.finditer(page_text):
                    line_num = page_text[:match.start()].count("\n")
                    y_pos = self._estimate_y_from_line(line_num, total_lines)
                    x_pos = self._estimate_x_from_offset(match.start(), page_text, line_num)
                    context = self._get_context(page_text, match.start(), 100)

                    try:
                        ft = DetectedFieldType(subtype)
                    except ValueError:
                        ft = DetectedFieldType.TEXT

                    fields.append(DetectedField(
                        field_id=f"txt-{page_num}-{uuid.uuid4().hex[:8]}",
                        field_type=ft,
                        page=page_num,
                        x=x_pos,
                        y=y_pos,
                        width=200,
                        height=18,
                        confidence=65,
                        signer_role=_infer_signer_role(context),
                        label=label,
                        is_required=False,
                        detection_method=DetectionMethod.TEXT_PATTERN,
                        context_text=context,
                        validation_regex=validation,
                    ))

            # Checkbox fields
            for pattern, label in CHECKBOX_PATTERNS:
                for match in pattern.finditer(page_text):
                    line_num = page_text[:match.start()].count("\n")
                    y_pos = self._estimate_y_from_line(line_num, total_lines)
                    x_pos = self._estimate_x_from_offset(match.start(), page_text, line_num)

                    checkbox_label = label
                    if match.lastindex and match.lastindex >= 1:
                        checkbox_label = match.group(1).strip()[:80]

                    fields.append(DetectedField(
                        field_id=f"chk-{page_num}-{uuid.uuid4().hex[:8]}",
                        field_type=DetectedFieldType.CHECKBOX,
                        page=page_num,
                        x=x_pos,
                        y=y_pos,
                        width=16,
                        height=16,
                        confidence=55,
                        label=checkbox_label,
                        is_required=False,
                        detection_method=DetectionMethod.TEXT_PATTERN,
                    ))

        return fields

    # ------------------------------------------------------------------
    # Line-geometry detection (pdfplumber)
    # ------------------------------------------------------------------

    def _detect_from_line_geometry(self, file_content: bytes) -> List[DetectedField]:
        """Detect signature lines from horizontal line objects in the PDF."""
        fields: List[DetectedField] = []
        if not HAS_PDFPLUMBER:
            return fields

        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for page_idx, page in enumerate(pdf.pages[:50]):
                    page_num = page_idx + 1
                    page_width = float(page.width)
                    page_height = float(page.height)
                    page_text = page.extract_text() or ""
                    total_lines = max(page_text.count("\n"), 1)

                    lines = page.lines or []
                    for line_obj in lines:
                        x0 = float(line_obj.get("x0", 0))
                        x1 = float(line_obj.get("x1", 0))
                        y0 = float(line_obj.get("top", 0))
                        y1 = float(line_obj.get("bottom", 0))

                        line_length = abs(x1 - x0)
                        line_height = abs(y1 - y0)

                        # A signature line is a long horizontal line
                        # (>= 100pt wide, <= 3pt tall)
                        if line_length < 100 or line_height > 3:
                            continue

                        # Skip lines that span the full page width (likely borders/rules)
                        if line_length > page_width * 0.85:
                            continue

                        # Check if text below the line indicates a signature
                        # Look at characters near this Y position
                        nearby_text = self._get_text_near_y(page, y0, tolerance=30)
                        lower_nearby = nearby_text.lower()

                        is_sig_line = any(
                            kw in lower_nearby
                            for kw in [
                                "signature", "sign here", "authorized",
                                "borrower", "co-borrower", "applicant",
                                "print name", "printed name", "date",
                            ]
                        )

                        if not is_sig_line:
                            continue

                        # Determine field type from nearby text
                        if "initial" in lower_nearby:
                            ft = DetectedFieldType.INITIAL
                            width = 60
                            height = 25
                        elif "date" in lower_nearby and "sign" not in lower_nearby:
                            ft = DetectedFieldType.DATE_SIGNED
                            width = 140
                            height = 20
                        elif "print" in lower_nearby and "name" in lower_nearby:
                            ft = DetectedFieldType.FULL_NAME
                            width = min(line_length, 220)
                            height = 18
                        else:
                            ft = DetectedFieldType.SIGNATURE
                            width = min(line_length, 220)
                            height = 30

                        fields.append(DetectedField(
                            field_id=f"line-{page_num}-{uuid.uuid4().hex[:8]}",
                            field_type=ft,
                            page=page_num,
                            x=x0,
                            y=max(0, y0 - height),  # Place field above the line
                            width=width,
                            height=height,
                            confidence=80,
                            signer_role=_infer_signer_role(nearby_text),
                            label=self._extract_label_from_nearby(nearby_text),
                            is_required=True,
                            detection_method=DetectionMethod.LINE_GEOMETRY,
                            context_text=nearby_text[:200],
                        ))

        except Exception as e:
            logger.warning("Line geometry detection failed: %s", e)

        return fields

    def _get_text_near_y(self, page, y_position: float, tolerance: float = 30) -> str:
        """Extract text characters near a given Y position on a pdfplumber page."""
        try:
            chars = page.chars or []
            nearby_chars = [
                c for c in chars
                if abs(float(c.get("top", 0)) - y_position) <= tolerance
            ]
            nearby_chars.sort(key=lambda c: (float(c.get("top", 0)), float(c.get("x0", 0))))
            return "".join(c.get("text", "") for c in nearby_chars)
        except Exception:
            return ""

    def _extract_label_from_nearby(self, text: str) -> str:
        """Extract a clean label from nearby text."""
        lower = text.lower().strip()
        for keyword in [
            "borrower signature", "co-borrower signature",
            "borrower's signature", "co-borrower's signature",
            "loan officer signature", "lender signature",
            "notary signature", "witness signature",
            "authorized signature", "signature",
            "print name", "printed name", "date signed", "date",
            "initials", "initial here",
        ]:
            if keyword in lower:
                return keyword.title()
        return "Signature Line"

    # ------------------------------------------------------------------
    # AI Vision detection
    # ------------------------------------------------------------------

    def _detect_with_ai_vision(
        self,
        file_content: bytes,
        pages_text: List[str],
    ) -> List[DetectedField]:
        """Use Claude Vision API to detect fields on complex form layouts."""
        if not self._anthropic:
            return []

        if not HAS_PDF2IMAGE:
            logger.warning("pdf2image not available; skipping AI vision detection")
            return []

        fields: List[DetectedField] = []

        try:
            # Convert first 5 pages to images for vision analysis
            images = convert_from_bytes(file_content, first_page=1, last_page=5, dpi=150)
        except Exception as e:
            logger.warning("Failed to convert PDF pages to images: %s", e)
            return []

        for page_idx, img in enumerate(images):
            page_num = page_idx + 1
            try:
                # Convert PIL image to base64 PNG
                img_buffer = io.BytesIO()
                img.save(img_buffer, format="PNG")
                img_b64 = base64.standard_b64encode(img_buffer.getvalue()).decode("ascii")

                page_text = pages_text[page_idx] if page_idx < len(pages_text) else ""

                prompt = (
                    "You are analyzing a mortgage document page to detect where "
                    "e-signature fields should be placed.\n\n"
                    "Look for:\n"
                    "1. Signature lines (horizontal lines with labels like 'Signature', 'Sign Here')\n"
                    "2. Initial fields ('Initials:' labels, page-bottom acknowledgments)\n"
                    "3. Date fields ('Date:' labels near signature lines)\n"
                    "4. Text input blanks (labeled blank lines for Name, Address, etc.)\n"
                    "5. Checkboxes (empty squares or brackets)\n\n"
                    "For each field, provide:\n"
                    "- type: signature, initial, date_signed, text, checkbox, full_name\n"
                    "- x: horizontal position as percentage of page width (0-100)\n"
                    "- y: vertical position as percentage of page height (0-100)\n"
                    "- width_pct: width as percentage of page width\n"
                    "- height_pct: height as percentage of page height\n"
                    "- label: descriptive label\n"
                    "- signer_role: borrower, co_borrower, loan_officer, notary, seller, witness, unknown\n"
                    "- required: true/false\n"
                    "- confidence: 0-100\n\n"
                    f"Page text (for context):\n{page_text[:3000]}\n\n"
                    "Respond with ONLY a JSON array of field objects. "
                    "If no fields are found, respond with []."
                )

                response = self._anthropic.messages.create(
                    model=self._vision_model,
                    max_tokens=2048,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": img_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }],
                )

                response_text = response.content[0].text.strip()
                # Strip markdown code fences
                if response_text.startswith("```"):
                    response_text = re.sub(r"^```json?\n?", "", response_text)
                    response_text = re.sub(r"\n?```$", "", response_text)

                detected = json.loads(response_text)
                if not isinstance(detected, list):
                    continue

                # Convert percentage coordinates to points (US Letter: 612 x 792)
                page_width_pts = 612.0
                page_height_pts = 792.0

                for entry in detected:
                    x_pct = float(entry.get("x", 0))
                    y_pct = float(entry.get("y", 0))
                    w_pct = float(entry.get("width_pct", 30))
                    h_pct = float(entry.get("height_pct", 4))

                    x_pts = (x_pct / 100.0) * page_width_pts
                    y_pts = (y_pct / 100.0) * page_height_pts
                    w_pts = (w_pct / 100.0) * page_width_pts
                    h_pts = (h_pct / 100.0) * page_height_pts

                    field_type_str = entry.get("type", "text")
                    try:
                        ft = DetectedFieldType(field_type_str)
                    except ValueError:
                        ft = DetectedFieldType.TEXT

                    signer_str = entry.get("signer_role", "unknown")
                    try:
                        sr = SignerRole(signer_str)
                    except ValueError:
                        sr = SignerRole.UNKNOWN

                    fields.append(DetectedField(
                        field_id=f"ai-{page_num}-{uuid.uuid4().hex[:8]}",
                        field_type=ft,
                        page=page_num,
                        x=x_pts,
                        y=y_pts,
                        width=w_pts,
                        height=h_pts,
                        confidence=int(entry.get("confidence", 60)),
                        signer_role=sr,
                        label=entry.get("label", ""),
                        is_required=entry.get("required", True),
                        detection_method=DetectionMethod.AI_VISION,
                    ))

            except json.JSONDecodeError as e:
                logger.warning("Failed to parse AI vision response for page %d: %s", page_num, e)
            except Exception as e:
                logger.warning("AI vision failed for page %d: %s", page_num, e)

        return fields

    # ------------------------------------------------------------------
    # Field merging and deduplication
    # ------------------------------------------------------------------

    def _merge_fields(
        self,
        primary: List[DetectedField],
        secondary: List[DetectedField],
    ) -> List[DetectedField]:
        """
        Merge two field lists, deduplicating by proximity.

        Primary fields take precedence when two fields overlap spatially
        on the same page.  A secondary field is considered a duplicate if
        it is within 40 points of a primary field of the same type on the
        same page.
        """
        if not primary:
            return list(secondary)
        if not secondary:
            return list(primary)

        merged = list(primary)
        proximity_threshold = 40.0

        for s_field in secondary:
            is_dup = False
            for p_field in merged:
                if (
                    p_field.page == s_field.page
                    and p_field.field_type == s_field.field_type
                    and abs(p_field.x - s_field.x) < proximity_threshold
                    and abs(p_field.y - s_field.y) < proximity_threshold
                ):
                    # Keep the higher-confidence one
                    if s_field.confidence > p_field.confidence:
                        p_field.confidence = s_field.confidence
                        if s_field.label and not p_field.label:
                            p_field.label = s_field.label
                        if s_field.signer_role != SignerRole.UNKNOWN and p_field.signer_role == SignerRole.UNKNOWN:
                            p_field.signer_role = s_field.signer_role
                    is_dup = True
                    break

            if not is_dup:
                merged.append(s_field)

        return merged

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    def _mark_notary_exclusions(
        self,
        fields: List[DetectedField],
        pages_text: List[str],
    ) -> None:
        """Mark fields within notary sections as excluded from e-sign."""
        for f in fields:
            if f.signer_role == SignerRole.NOTARY:
                f.exclude_from_esign = True
                continue

            page_idx = f.page - 1
            if page_idx >= len(pages_text):
                continue

            page_text = pages_text[page_idx]
            # Approximate character offset from Y position
            total_lines = max(page_text.count("\n"), 1)
            approx_line = int((f.y / 792.0) * total_lines)
            approx_offset = sum(
                len(line) + 1
                for i, line in enumerate(page_text.split("\n"))
                if i < approx_line
            )

            if _is_in_notary_section("", approx_offset, page_text):
                f.exclude_from_esign = True

    def _assign_tab_order(self, fields: List[DetectedField]) -> None:
        """Assign tab order: page ascending, then top-to-bottom, left-to-right."""
        sorted_fields = sorted(fields, key=lambda f: (f.page, f.y, f.x))
        for idx, f in enumerate(sorted_fields):
            f.tab_order = idx + 1

    def _assign_groups(self, fields: List[DetectedField]) -> None:
        """
        Group related fields together (e.g. signature + date on the same line).

        Fields on the same page within 20 vertical points of each other are
        grouped together.
        """
        if not fields:
            return

        sorted_fields = sorted(fields, key=lambda f: (f.page, f.y, f.x))
        group_counter = 0
        current_group_page = -1
        current_group_y = -999.0
        current_group_id: Optional[str] = None

        for f in sorted_fields:
            if f.page != current_group_page or abs(f.y - current_group_y) > 20:
                group_counter += 1
                current_group_page = f.page
                current_group_y = f.y
                current_group_id = f"grp-{group_counter}"
            f.group_id = current_group_id

    def _apply_signer_names(
        self,
        fields: List[DetectedField],
        signer_names: Dict[str, str],
    ) -> None:
        """Enrich field labels with signer names."""
        for f in fields:
            role_key = f.signer_role.value
            name = signer_names.get(role_key)
            if name and f.label:
                f.label = f"{f.label} ({name})"

    # ------------------------------------------------------------------
    # Coordinate estimation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_y_from_line(line_num: int, total_lines: int) -> float:
        """Estimate Y coordinate (points) from line number in page text."""
        # US Letter page: 792 points tall, ~72pt margins top/bottom
        usable_height = 648.0  # 792 - 72 - 72
        top_margin = 72.0
        if total_lines <= 0:
            return top_margin
        return top_margin + (line_num / total_lines) * usable_height

    @staticmethod
    def _estimate_x_from_offset(char_offset: int, page_text: str, line_num: int) -> float:
        """Estimate X coordinate from character offset within the line."""
        lines = page_text.split("\n")
        if line_num < len(lines):
            line = lines[line_num]
            # Find position of match within the line
            line_start = sum(len(lines[i]) + 1 for i in range(line_num))
            pos_in_line = char_offset - line_start
            line_len = max(len(line), 1)
            # Assume usable width of ~468 points (72pt margins on 612pt page)
            left_margin = 72.0
            usable_width = 468.0
            return left_margin + (pos_in_line / line_len) * usable_width
        return 72.0  # default left margin

    @staticmethod
    def _get_context(text: str, pos: int, window: int = 150) -> str:
        """Extract context text around a position."""
        start = max(0, pos - window)
        end = min(len(text), pos + window)
        return text[start:end].strip()

    @staticmethod
    def _elapsed_ms(start_time: float) -> int:
        """Calculate elapsed milliseconds since start_time."""
        return int((time.time() - start_time) * 1000)


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_service: Optional[ESignFieldDetectorService] = None


def get_esign_field_detector_service() -> ESignFieldDetectorService:
    """
    Get or create the singleton ESignFieldDetectorService instance.

    Returns:
        The shared ``ESignFieldDetectorService`` instance.
    """
    global _service
    if _service is None:
        _service = ESignFieldDetectorService()
    return _service
