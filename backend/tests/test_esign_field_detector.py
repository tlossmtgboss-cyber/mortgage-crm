"""
Test E-Sign Field Auto-Detection - Validates the logic for automatically
detecting signable fields in PDF documents by analyzing text content,
patterns, and layout.

The esign_field_detector_service does not yet exist. These tests define the
expected behavior for an auto-detection service that would:
- Parse PDF text and layout (via pypdf or pdfplumber)
- Identify signature lines, initial fields, date blanks, text inputs, checkboxes
- Map known mortgage forms (1003, 4506-T, LOE templates)
- Group fields by signer role (borrower, co-borrower)
- Assign tab order, estimate field sizes, calculate confidence scores

All PDF parsing is mocked. Tests target pure detection logic.
"""

import pytest
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


# =============================================================================
# Data structures that mirror what the detector service would produce
# =============================================================================

class DetectedFieldType(str, Enum):
    SIGNATURE = "signature"
    INITIAL = "initial"
    DATE_SIGNED = "date_signed"
    TEXT = "text"
    CHECKBOX = "checkbox"


class SignerRole(str, Enum):
    BORROWER = "borrower"
    CO_BORROWER = "co_borrower"
    NOTARY = "notary"
    UNKNOWN = "unknown"


@dataclass
class DetectedField:
    """A field detected by analyzing PDF text and layout."""
    field_type: DetectedFieldType
    page_number: int
    x_position_points: float
    y_position_points: float
    width_points: float
    height_points: float
    label: str = ""
    signer_role: SignerRole = SignerRole.UNKNOWN
    is_required: bool = True
    confidence: float = 0.0  # 0.0 - 1.0
    tab_order: int = 0
    form_field_id: Optional[str] = None  # e.g., "1003_borrower_signature"


@dataclass
class PageText:
    """Simulated extracted text element from a PDF page."""
    text: str
    x0: float  # left edge in points
    y0: float  # bottom edge in points (PDF coordinate system)
    x1: float  # right edge
    y1: float  # top edge
    page_number: int = 1


@dataclass
class PageLine:
    """Simulated horizontal line element from a PDF page."""
    x0: float
    y0: float
    x1: float
    y1: float
    page_number: int = 1


@dataclass
class DetectionResult:
    """Result of running the field detector on a document."""
    fields: List[DetectedField]
    form_type: Optional[str] = None  # e.g., "1003", "4506-T", "LOE"
    page_count: int = 1
    is_filled: bool = False  # whether the form appears already filled


# =============================================================================
# Detection logic functions (pure business logic, no PDF I/O)
# =============================================================================

def detect_signature_line(texts: List[PageText], lines: List[PageLine]) -> List[DetectedField]:
    """
    Detect signature fields by finding horizontal lines near text
    containing 'Signature' or 'Sign' labels.
    """
    fields = []
    sig_labels = []
    for t in texts:
        lower = t.text.lower().strip()
        if "signature" in lower and "notary" not in lower:
            sig_labels.append(t)

    for label in sig_labels:
        # Look for a horizontal line near the label (within 30 points above)
        for line in lines:
            if line.page_number != label.page_number:
                continue
            line_length = abs(line.x1 - line.x0)
            if line_length < 72:  # Less than 1 inch, too short
                continue
            # Line should be above the label text (higher y in PDF coords)
            vertical_dist = abs(line.y0 - label.y1)
            if vertical_dist <= 30:
                role = _infer_signer_role(label.text)
                fields.append(DetectedField(
                    field_type=DetectedFieldType.SIGNATURE,
                    page_number=label.page_number,
                    x_position_points=line.x0,
                    y_position_points=line.y0,
                    width_points=line_length,
                    height_points=36.0,
                    label=label.text.strip(),
                    signer_role=role,
                    is_required=True,
                    confidence=0.9,
                ))
    return fields


def detect_x_blank_pattern(texts: List[PageText]) -> List[DetectedField]:
    """
    Detect 'X___' or 'X ___' patterns indicating a sign-here mark.
    """
    import re
    fields = []
    pattern = re.compile(r'^[Xx]\s*[_]{3,}')

    for t in texts:
        if pattern.search(t.text.strip()):
            underscores = t.text.count('_')
            estimated_width = max(underscores * 6.0, 72.0)  # ~6 pts per underscore char
            fields.append(DetectedField(
                field_type=DetectedFieldType.SIGNATURE,
                page_number=t.page_number,
                x_position_points=t.x0,
                y_position_points=t.y0,
                width_points=min(estimated_width, 288.0),
                height_points=36.0,
                label="X___",
                is_required=True,
                confidence=0.85,
            ))
    return fields


def detect_sign_here_label(texts: List[PageText]) -> List[DetectedField]:
    """
    Detect 'Sign here', 'Sign Here:', 'Please sign below' labels.
    """
    fields = []
    for t in texts:
        lower = t.text.lower().strip()
        if "sign here" in lower or "please sign" in lower:
            if "notary" in lower or "witness" in lower:
                continue
            fields.append(DetectedField(
                field_type=DetectedFieldType.SIGNATURE,
                page_number=t.page_number,
                x_position_points=t.x0,
                y_position_points=t.y0 - 40,  # field below the label
                width_points=200.0,
                height_points=36.0,
                label=t.text.strip(),
                is_required=True,
                confidence=0.80,
            ))
    return fields


def detect_initials_field(texts: List[PageText]) -> List[DetectedField]:
    """
    Detect initials fields: 'Initials: ___', 'Initial Here', 'Borrower Initials'.
    """
    import re
    fields = []
    pattern = re.compile(r'(initials?)\s*[:.]?\s*[_]{2,}', re.IGNORECASE)

    for t in texts:
        if pattern.search(t.text) or "initial here" in t.text.lower():
            role = _infer_signer_role(t.text)
            fields.append(DetectedField(
                field_type=DetectedFieldType.INITIAL,
                page_number=t.page_number,
                x_position_points=t.x0,
                y_position_points=t.y0,
                width_points=72.0,  # 1 inch for initials
                height_points=24.0,
                label=t.text.strip(),
                signer_role=role,
                is_required=True,
                confidence=0.85,
            ))
    return fields


def detect_date_field(texts: List[PageText]) -> List[DetectedField]:
    """
    Detect date fields: 'Date: ___', 'Date Signed:', 'MM/DD/YYYY'.
    """
    import re
    fields = []
    date_pattern = re.compile(
        r'(?:date\s*[:.]?\s*[_]{2,})|(?:date\s+signed)|(?:mm\s*/\s*dd\s*/\s*yyyy)',
        re.IGNORECASE,
    )

    for t in texts:
        if date_pattern.search(t.text):
            fields.append(DetectedField(
                field_type=DetectedFieldType.DATE_SIGNED,
                page_number=t.page_number,
                x_position_points=t.x0,
                y_position_points=t.y0,
                width_points=108.0,  # 1.5 inches
                height_points=24.0,
                label=t.text.strip(),
                is_required=True,
                confidence=0.88,
            ))
    return fields


def detect_text_input_field(texts: List[PageText]) -> List[DetectedField]:
    """
    Detect labeled text input blanks, e.g., 'Name: ___________',
    'Address: ___________', 'Phone: _____'.
    """
    import re
    fields = []
    # Pattern: label word(s) followed by colon/period and underscores
    pattern = re.compile(r'^([A-Za-z\s]+)\s*[:.]?\s*([_]{3,})')

    for t in texts:
        match = pattern.search(t.text.strip())
        if match:
            label_text = match.group(1).strip()
            underscores = len(match.group(2))
            # Skip if this is a signature/initial/date field
            lower_label = label_text.lower()
            if any(kw in lower_label for kw in ["signature", "initial", "date", "sign"]):
                continue
            estimated_width = max(underscores * 6.0, 108.0)
            fields.append(DetectedField(
                field_type=DetectedFieldType.TEXT,
                page_number=t.page_number,
                x_position_points=t.x0,
                y_position_points=t.y0,
                width_points=min(estimated_width, 360.0),
                height_points=24.0,
                label=label_text,
                is_required=False,  # Text inputs default to optional
                confidence=0.70,
            ))
    return fields


def detect_checkbox(texts: List[PageText]) -> List[DetectedField]:
    """
    Detect checkbox fields by looking for common checkbox indicators:
    '[ ]', '()' empty parens, or Unicode ballot box characters.
    """
    import re
    fields = []
    # Matches [ ], [X], empty parens, or ballot box Unicode
    checkbox_pattern = re.compile(r'(\[\s*\]|\(\s*\)|\u2610|\u2611|\u2612)')

    for t in texts:
        matches = list(checkbox_pattern.finditer(t.text))
        for m in matches:
            # Position each checkbox at its character offset
            char_offset = m.start()
            x_offset = t.x0 + (char_offset * 6.0)
            fields.append(DetectedField(
                field_type=DetectedFieldType.CHECKBOX,
                page_number=t.page_number,
                x_position_points=x_offset,
                y_position_points=t.y0,
                width_points=14.0,
                height_points=14.0,
                label=t.text.strip(),
                is_required=False,
                confidence=0.82,
            ))
    return fields


def detect_known_form(texts: List[PageText]) -> Optional[str]:
    """
    Identify the form type by scanning for known identifiers.
    Returns form type string or None.
    """
    full_text = " ".join(t.text for t in texts).lower()

    if "uniform residential loan application" in full_text or "form 1003" in full_text or "urla" in full_text:
        return "1003"
    if "4506-t" in full_text or "request for transcript" in full_text:
        return "4506-T"
    if "letter of explanation" in full_text or "loe" in full_text:
        return "LOE"
    return None


def map_1003_fields(page_count: int) -> List[DetectedField]:
    """
    Return known field positions for the Uniform Residential Loan Application (1003).
    These are pre-mapped based on the standard form layout.
    """
    fields = []
    # Borrower signature on last page
    fields.append(DetectedField(
        field_type=DetectedFieldType.SIGNATURE,
        page_number=page_count,
        x_position_points=72.0,
        y_position_points=120.0,
        width_points=200.0,
        height_points=36.0,
        label="Borrower Signature",
        signer_role=SignerRole.BORROWER,
        is_required=True,
        confidence=0.95,
        form_field_id="1003_borrower_signature",
    ))
    # Co-Borrower signature on last page
    fields.append(DetectedField(
        field_type=DetectedFieldType.SIGNATURE,
        page_number=page_count,
        x_position_points=360.0,
        y_position_points=120.0,
        width_points=200.0,
        height_points=36.0,
        label="Co-Borrower Signature",
        signer_role=SignerRole.CO_BORROWER,
        is_required=True,
        confidence=0.95,
        form_field_id="1003_coborrower_signature",
    ))
    # Date fields
    fields.append(DetectedField(
        field_type=DetectedFieldType.DATE_SIGNED,
        page_number=page_count,
        x_position_points=72.0,
        y_position_points=90.0,
        width_points=108.0,
        height_points=24.0,
        label="Date",
        signer_role=SignerRole.BORROWER,
        is_required=True,
        confidence=0.95,
        form_field_id="1003_borrower_date",
    ))
    fields.append(DetectedField(
        field_type=DetectedFieldType.DATE_SIGNED,
        page_number=page_count,
        x_position_points=360.0,
        y_position_points=90.0,
        width_points=108.0,
        height_points=24.0,
        label="Date",
        signer_role=SignerRole.CO_BORROWER,
        is_required=True,
        confidence=0.95,
        form_field_id="1003_coborrower_date",
    ))
    return fields


def map_4506t_fields() -> List[DetectedField]:
    """
    Return known field positions for IRS Form 4506-T.
    """
    fields = [
        DetectedField(
            field_type=DetectedFieldType.SIGNATURE,
            page_number=1,
            x_position_points=72.0,
            y_position_points=160.0,
            width_points=216.0,
            height_points=36.0,
            label="Signature",
            signer_role=SignerRole.BORROWER,
            is_required=True,
            confidence=0.95,
            form_field_id="4506t_signature",
        ),
        DetectedField(
            field_type=DetectedFieldType.DATE_SIGNED,
            page_number=1,
            x_position_points=400.0,
            y_position_points=160.0,
            width_points=108.0,
            height_points=24.0,
            label="Date",
            signer_role=SignerRole.BORROWER,
            is_required=True,
            confidence=0.95,
            form_field_id="4506t_date",
        ),
        DetectedField(
            field_type=DetectedFieldType.TEXT,
            page_number=1,
            x_position_points=72.0,
            y_position_points=600.0,
            width_points=250.0,
            height_points=24.0,
            label="Name",
            signer_role=SignerRole.BORROWER,
            is_required=True,
            confidence=0.95,
            form_field_id="4506t_name",
        ),
        DetectedField(
            field_type=DetectedFieldType.TEXT,
            page_number=1,
            x_position_points=72.0,
            y_position_points=560.0,
            width_points=350.0,
            height_points=24.0,
            label="Address",
            signer_role=SignerRole.BORROWER,
            is_required=True,
            confidence=0.95,
            form_field_id="4506t_address",
        ),
        DetectedField(
            field_type=DetectedFieldType.TEXT,
            page_number=1,
            x_position_points=72.0,
            y_position_points=520.0,
            width_points=180.0,
            height_points=24.0,
            label="SSN",
            signer_role=SignerRole.BORROWER,
            is_required=True,
            confidence=0.95,
            form_field_id="4506t_ssn",
        ),
        DetectedField(
            field_type=DetectedFieldType.CHECKBOX,
            page_number=1,
            x_position_points=72.0,
            y_position_points=400.0,
            width_points=14.0,
            height_points=14.0,
            label="Return Transcript",
            is_required=False,
            confidence=0.95,
            form_field_id="4506t_return_transcript",
        ),
    ]
    return fields


def map_loe_fields() -> List[DetectedField]:
    """
    Return known field positions for a Letter of Explanation template.
    """
    return [
        DetectedField(
            field_type=DetectedFieldType.TEXT,
            page_number=1,
            x_position_points=72.0,
            y_position_points=650.0,
            width_points=250.0,
            height_points=24.0,
            label="Borrower Name",
            signer_role=SignerRole.BORROWER,
            is_required=True,
            confidence=0.90,
            form_field_id="loe_borrower_name",
        ),
        DetectedField(
            field_type=DetectedFieldType.DATE_SIGNED,
            page_number=1,
            x_position_points=400.0,
            y_position_points=650.0,
            width_points=108.0,
            height_points=24.0,
            label="Date",
            signer_role=SignerRole.BORROWER,
            is_required=True,
            confidence=0.90,
            form_field_id="loe_date",
        ),
        DetectedField(
            field_type=DetectedFieldType.SIGNATURE,
            page_number=1,
            x_position_points=72.0,
            y_position_points=100.0,
            width_points=200.0,
            height_points=36.0,
            label="Borrower Signature",
            signer_role=SignerRole.BORROWER,
            is_required=True,
            confidence=0.90,
            form_field_id="loe_signature",
        ),
    ]


def group_fields_by_signer(fields: List[DetectedField]) -> Dict[SignerRole, List[DetectedField]]:
    """
    Group detected fields by signer role.
    """
    groups: Dict[SignerRole, List[DetectedField]] = {}
    for f in fields:
        if f.signer_role not in groups:
            groups[f.signer_role] = []
        groups[f.signer_role].append(f)
    return groups


def is_notary_section(texts: List[PageText], y_start: float, y_end: float, page: int) -> bool:
    """
    Determine if a region on a page is a notary section.
    Notary sections should be excluded from signer field detection.
    """
    notary_keywords = ["notary public", "notarial", "sworn before me", "my commission", "seal"]
    for t in texts:
        if t.page_number != page:
            continue
        if t.y0 >= y_start and t.y1 <= y_end:
            lower = t.text.lower()
            if any(kw in lower for kw in notary_keywords):
                return True
    return False


def assign_tab_order(fields: List[DetectedField]) -> List[DetectedField]:
    """
    Assign tab order to fields based on page number, then top-to-bottom
    (descending y in PDF coords), then left-to-right.
    """
    sorted_fields = sorted(
        fields,
        key=lambda f: (f.page_number, -f.y_position_points, f.x_position_points),
    )
    for i, f in enumerate(sorted_fields):
        f.tab_order = i + 1
    return sorted_fields


def estimate_field_size(
    field_type: DetectedFieldType,
    label: str = "",
    underscore_count: int = 0,
) -> tuple:
    """
    Estimate field width and height in PDF points based on type and context.
    Returns (width_points, height_points).
    """
    if field_type == DetectedFieldType.SIGNATURE:
        return (200.0, 36.0)
    elif field_type == DetectedFieldType.INITIAL:
        return (72.0, 24.0)
    elif field_type == DetectedFieldType.CHECKBOX:
        return (14.0, 14.0)
    elif field_type == DetectedFieldType.DATE_SIGNED:
        return (108.0, 24.0)
    elif field_type == DetectedFieldType.TEXT:
        if underscore_count > 0:
            width = max(underscore_count * 6.0, 108.0)
            return (min(width, 360.0), 24.0)
        return (180.0, 24.0)
    return (144.0, 36.0)  # default fallback


def determine_required(field_type: DetectedFieldType, label: str = "") -> bool:
    """
    Determine if a field should be required based on type and label context.
    Signatures and dates are always required. Text/checkboxes depend on label.
    """
    if field_type in (DetectedFieldType.SIGNATURE, DetectedFieldType.INITIAL, DetectedFieldType.DATE_SIGNED):
        return True
    lower_label = label.lower()
    if "optional" in lower_label:
        return False
    if any(kw in lower_label for kw in ["ssn", "name", "address", "phone", "email"]):
        return True
    return False


def detect_filled_form(texts: List[PageText]) -> bool:
    """
    Heuristic: if underscores are rare but there is substantial text content,
    the form is likely already filled in.
    """
    total_chars = sum(len(t.text) for t in texts)
    underscore_chars = sum(t.text.count('_') for t in texts)
    if total_chars == 0:
        return False
    underscore_ratio = underscore_chars / total_chars
    # A blank form typically has many underscores (>5% of chars)
    return underscore_ratio < 0.01 and total_chars > 500


def _infer_signer_role(label_text: str) -> SignerRole:
    """Infer signer role from label text."""
    lower = label_text.lower()
    if "co-borrower" in lower or "coborrower" in lower or "co borrower" in lower:
        return SignerRole.CO_BORROWER
    if "borrower" in lower:
        return SignerRole.BORROWER
    if "notary" in lower:
        return SignerRole.NOTARY
    return SignerRole.UNKNOWN


# =============================================================================
# TESTS
# =============================================================================


@pytest.mark.unit
class TestSignatureLineDetection:
    """Test detection of signature lines (horizontal line + 'Signature' label)."""

    def test_signature_line_detected_with_label_and_line(self):
        """A horizontal line near a 'Signature' label should produce a signature field."""
        texts = [
            PageText("Borrower Signature", x0=72, y0=100, x1=200, y1=112, page_number=1),
        ]
        lines = [
            PageLine(x0=72, y0=130, x1=280, y1=130, page_number=1),
        ]
        fields = detect_signature_line(texts, lines)
        assert len(fields) == 1
        assert fields[0].field_type == DetectedFieldType.SIGNATURE
        assert fields[0].confidence >= 0.85

    def test_short_line_not_detected_as_signature(self):
        """Lines shorter than 1 inch (72 pts) should not be treated as signature lines."""
        texts = [
            PageText("Signature", x0=72, y0=100, x1=140, y1=112, page_number=1),
        ]
        lines = [
            PageLine(x0=72, y0=130, x1=120, y1=130, page_number=1),  # Only 48 pts
        ]
        fields = detect_signature_line(texts, lines)
        assert len(fields) == 0

    def test_notary_signature_excluded(self):
        """Labels containing 'notary' should not produce borrower signature fields."""
        texts = [
            PageText("Notary Signature", x0=72, y0=100, x1=200, y1=112, page_number=1),
        ]
        lines = [
            PageLine(x0=72, y0=130, x1=280, y1=130, page_number=1),
        ]
        fields = detect_signature_line(texts, lines)
        assert len(fields) == 0

    def test_line_too_far_from_label_not_detected(self):
        """A line more than 30 points from the label should not be matched."""
        texts = [
            PageText("Signature", x0=72, y0=100, x1=140, y1=112, page_number=1),
        ]
        lines = [
            PageLine(x0=72, y0=200, x1=280, y1=200, page_number=1),  # 88 pts away
        ]
        fields = detect_signature_line(texts, lines)
        assert len(fields) == 0


@pytest.mark.unit
class TestXBlankPatternDetection:
    """Test detection of 'X___' patterns."""

    def test_x_underscore_pattern_detected(self):
        """'X_________' should be detected as a signature field."""
        texts = [
            PageText("X______________", x0=72, y0=200, x1=200, y1=212, page_number=2),
        ]
        fields = detect_x_blank_pattern(texts)
        assert len(fields) == 1
        assert fields[0].field_type == DetectedFieldType.SIGNATURE
        assert fields[0].page_number == 2

    def test_x_space_underscores_detected(self):
        """'X ___' with space should also be detected."""
        texts = [
            PageText("X _______", x0=72, y0=200, x1=180, y1=212, page_number=1),
        ]
        fields = detect_x_blank_pattern(texts)
        assert len(fields) == 1

    def test_non_x_pattern_not_detected(self):
        """Plain underscores without leading X should not match."""
        texts = [
            PageText("______________", x0=72, y0=200, x1=200, y1=212, page_number=1),
        ]
        fields = detect_x_blank_pattern(texts)
        assert len(fields) == 0

    def test_x_with_too_few_underscores_not_detected(self):
        """'X__' (only 2 underscores) should not match; minimum is 3."""
        texts = [
            PageText("X__", x0=72, y0=200, x1=100, y1=212, page_number=1),
        ]
        fields = detect_x_blank_pattern(texts)
        assert len(fields) == 0


@pytest.mark.unit
class TestSignHereLabelDetection:
    """Test detection of 'Sign here' labels."""

    def test_sign_here_detected(self):
        """'Sign here' text should produce a signature field."""
        texts = [
            PageText("Sign here", x0=72, y0=300, x1=140, y1=312, page_number=1),
        ]
        fields = detect_sign_here_label(texts)
        assert len(fields) == 1
        assert fields[0].field_type == DetectedFieldType.SIGNATURE

    def test_please_sign_below_detected(self):
        """'Please sign below' should also be detected."""
        texts = [
            PageText("Please sign below", x0=72, y0=300, x1=200, y1=312, page_number=1),
        ]
        fields = detect_sign_here_label(texts)
        assert len(fields) == 1

    def test_notary_sign_here_excluded(self):
        """'Notary: Sign here' should be excluded."""
        texts = [
            PageText("Notary: Sign here", x0=72, y0=300, x1=200, y1=312, page_number=1),
        ]
        fields = detect_sign_here_label(texts)
        assert len(fields) == 0


@pytest.mark.unit
class TestInitialsFieldDetection:
    """Test detection of initials fields."""

    def test_initials_with_underscores_detected(self):
        """'Initials: ____' should produce an initial field."""
        texts = [
            PageText("Initials: ______", x0=400, y0=500, x1=500, y1=512, page_number=3),
        ]
        fields = detect_initials_field(texts)
        assert len(fields) == 1
        assert fields[0].field_type == DetectedFieldType.INITIAL
        assert fields[0].width_points == 72.0  # 1 inch for initials

    def test_initial_here_detected(self):
        """'Initial Here' label should be detected."""
        texts = [
            PageText("Initial Here", x0=400, y0=500, x1=480, y1=512, page_number=1),
        ]
        fields = detect_initials_field(texts)
        assert len(fields) == 1

    def test_borrower_initials_role_inferred(self):
        """'Borrower Initials: ___' should infer borrower signer role."""
        texts = [
            PageText("Borrower Initials: ______", x0=72, y0=500, x1=250, y1=512, page_number=1),
        ]
        fields = detect_initials_field(texts)
        assert len(fields) == 1
        assert fields[0].signer_role == SignerRole.BORROWER


@pytest.mark.unit
class TestDateFieldDetection:
    """Test detection of date fields."""

    def test_date_with_underscores_detected(self):
        """'Date: ______' should produce a date_signed field."""
        texts = [
            PageText("Date: __________", x0=300, y0=100, x1=420, y1=112, page_number=1),
        ]
        fields = detect_date_field(texts)
        assert len(fields) == 1
        assert fields[0].field_type == DetectedFieldType.DATE_SIGNED

    def test_date_signed_label_detected(self):
        """'Date Signed' should be detected."""
        texts = [
            PageText("Date Signed", x0=300, y0=100, x1=380, y1=112, page_number=1),
        ]
        fields = detect_date_field(texts)
        assert len(fields) == 1

    def test_mm_dd_yyyy_placeholder_detected(self):
        """'MM/DD/YYYY' date format placeholder should be detected."""
        texts = [
            PageText("MM/DD/YYYY", x0=300, y0=100, x1=380, y1=112, page_number=1),
        ]
        fields = detect_date_field(texts)
        assert len(fields) == 1


@pytest.mark.unit
class TestTextInputFieldDetection:
    """Test detection of labeled text input blanks."""

    def test_name_field_detected(self):
        """'Name: ___________' should produce a text field."""
        texts = [
            PageText("Name: ___________", x0=72, y0=600, x1=250, y1=612, page_number=1),
        ]
        fields = detect_text_input_field(texts)
        assert len(fields) == 1
        assert fields[0].field_type == DetectedFieldType.TEXT
        assert fields[0].label == "Name"

    def test_address_field_detected(self):
        """'Address: _____________' should produce a text field."""
        texts = [
            PageText("Address: ________________", x0=72, y0=580, x1=350, y1=592, page_number=1),
        ]
        fields = detect_text_input_field(texts)
        assert len(fields) == 1
        assert fields[0].label == "Address"

    def test_signature_label_not_detected_as_text(self):
        """'Signature: ___' should NOT be detected as a text input field."""
        texts = [
            PageText("Signature: ___________", x0=72, y0=100, x1=250, y1=112, page_number=1),
        ]
        fields = detect_text_input_field(texts)
        assert len(fields) == 0


@pytest.mark.unit
class TestKnownFormDetection:
    """Test identification of known mortgage forms."""

    def test_1003_form_detected_by_title(self):
        """'Uniform Residential Loan Application' should identify as 1003."""
        texts = [
            PageText("Uniform Residential Loan Application", x0=72, y0=700, x1=400, y1=720, page_number=1),
        ]
        assert detect_known_form(texts) == "1003"

    def test_1003_form_detected_by_form_number(self):
        """'Form 1003' should identify as 1003."""
        texts = [
            PageText("Freddie Mac Form 65 / Fannie Mae Form 1003", x0=72, y0=50, x1=400, y1=62, page_number=1),
        ]
        assert detect_known_form(texts) == "1003"

    def test_4506t_detected(self):
        """'4506-T' should be detected."""
        texts = [
            PageText("IRS Form 4506-T Request for Transcript", x0=72, y0=700, x1=400, y1=720, page_number=1),
        ]
        assert detect_known_form(texts) == "4506-T"

    def test_loe_detected(self):
        """'Letter of Explanation' should be detected."""
        texts = [
            PageText("Letter of Explanation", x0=72, y0=700, x1=250, y1=720, page_number=1),
        ]
        assert detect_known_form(texts) == "LOE"

    def test_unknown_form_returns_none(self):
        """Unrecognized form content should return None."""
        texts = [
            PageText("Some random document content", x0=72, y0=700, x1=300, y1=720, page_number=1),
        ]
        assert detect_known_form(texts) is None


@pytest.mark.unit
class TestMultiSignerFieldGrouping:
    """Test grouping fields by signer role (borrower vs co-borrower)."""

    def test_fields_grouped_by_role(self):
        """Fields should be grouped into borrower and co-borrower buckets."""
        fields = [
            DetectedField(
                field_type=DetectedFieldType.SIGNATURE, page_number=5,
                x_position_points=72, y_position_points=120,
                width_points=200, height_points=36,
                label="Borrower Signature", signer_role=SignerRole.BORROWER,
                confidence=0.9,
            ),
            DetectedField(
                field_type=DetectedFieldType.SIGNATURE, page_number=5,
                x_position_points=360, y_position_points=120,
                width_points=200, height_points=36,
                label="Co-Borrower Signature", signer_role=SignerRole.CO_BORROWER,
                confidence=0.9,
            ),
            DetectedField(
                field_type=DetectedFieldType.DATE_SIGNED, page_number=5,
                x_position_points=72, y_position_points=90,
                width_points=108, height_points=24,
                label="Date", signer_role=SignerRole.BORROWER,
                confidence=0.9,
            ),
        ]
        groups = group_fields_by_signer(fields)
        assert len(groups[SignerRole.BORROWER]) == 2
        assert len(groups[SignerRole.CO_BORROWER]) == 1

    def test_unknown_role_grouped_separately(self):
        """Fields with unknown role should be in their own group."""
        fields = [
            DetectedField(
                field_type=DetectedFieldType.TEXT, page_number=1,
                x_position_points=72, y_position_points=400,
                width_points=200, height_points=24,
                label="Loan Number", signer_role=SignerRole.UNKNOWN,
                confidence=0.7,
            ),
        ]
        groups = group_fields_by_signer(fields)
        assert SignerRole.UNKNOWN in groups
        assert len(groups[SignerRole.UNKNOWN]) == 1


@pytest.mark.unit
class TestNotarySectionExclusion:
    """Test that notary sections are correctly identified for exclusion."""

    def test_notary_section_detected(self):
        """Region containing 'Notary Public' should be identified as notary."""
        texts = [
            PageText("Notary Public", x0=72, y0=50, x1=200, y1=62, page_number=4),
            PageText("My commission expires: 12/31/2027", x0=72, y0=30, x1=300, y1=42, page_number=4),
        ]
        assert is_notary_section(texts, y_start=20, y_end=100, page=4) is True

    def test_non_notary_region_not_flagged(self):
        """Region without notary keywords should not be flagged."""
        texts = [
            PageText("Borrower Signature", x0=72, y0=100, x1=200, y1=112, page_number=1),
        ]
        assert is_notary_section(texts, y_start=90, y_end=120, page=1) is False

    def test_sworn_before_me_detected_as_notary(self):
        """'Sworn before me' language should identify notary section."""
        texts = [
            PageText("Sworn before me this 5th day of March", x0=72, y0=60, x1=350, y1=72, page_number=3),
        ]
        assert is_notary_section(texts, y_start=50, y_end=80, page=3) is True


@pytest.mark.unit
class TestPageNumberAndCoordinateCalculation:
    """Test that page numbers and coordinates are correctly assigned."""

    def test_multi_page_fields_retain_page_number(self):
        """Fields detected on different pages should retain correct page numbers."""
        texts_p1 = [PageText("Sign here", x0=72, y0=100, x1=140, y1=112, page_number=1)]
        texts_p3 = [PageText("Sign here", x0=72, y0=100, x1=140, y1=112, page_number=3)]

        fields_p1 = detect_sign_here_label(texts_p1)
        fields_p3 = detect_sign_here_label(texts_p3)

        assert fields_p1[0].page_number == 1
        assert fields_p3[0].page_number == 3

    def test_coordinates_preserved_from_source(self):
        """Field coordinates should be derived from the source text/line positions."""
        texts = [
            PageText("X__________", x0=150.5, y0=300.75, x1=250.0, y1=312.0, page_number=2),
        ]
        fields = detect_x_blank_pattern(texts)
        assert len(fields) == 1
        assert fields[0].x_position_points == 150.5
        assert fields[0].y_position_points == 300.75


@pytest.mark.unit
class TestFieldSizeEstimation:
    """Test field size estimation logic."""

    def test_signature_field_size(self):
        """Signature fields should be ~200x36 points."""
        w, h = estimate_field_size(DetectedFieldType.SIGNATURE)
        assert w == 200.0
        assert h == 36.0

    def test_initial_field_size(self):
        """Initial fields should be ~72x24 points (1 inch wide)."""
        w, h = estimate_field_size(DetectedFieldType.INITIAL)
        assert w == 72.0
        assert h == 24.0

    def test_checkbox_field_size(self):
        """Checkbox fields should be ~14x14 points."""
        w, h = estimate_field_size(DetectedFieldType.CHECKBOX)
        assert w == 14.0
        assert h == 14.0

    def test_text_field_scales_with_underscores(self):
        """Text field width should scale with underscore count."""
        w_short, _ = estimate_field_size(DetectedFieldType.TEXT, underscore_count=10)
        w_long, _ = estimate_field_size(DetectedFieldType.TEXT, underscore_count=50)
        assert w_long > w_short

    def test_text_field_width_capped_at_360(self):
        """Text field width should not exceed 360 points (5 inches)."""
        w, _ = estimate_field_size(DetectedFieldType.TEXT, underscore_count=100)
        assert w <= 360.0


@pytest.mark.unit
class TestTabOrderAssignment:
    """Test tab order assignment based on page, y-position, x-position."""

    def test_tab_order_top_to_bottom(self):
        """Fields higher on the page (larger y) should come first."""
        fields = [
            DetectedField(
                field_type=DetectedFieldType.TEXT, page_number=1,
                x_position_points=72, y_position_points=200,
                width_points=200, height_points=24,
            ),
            DetectedField(
                field_type=DetectedFieldType.TEXT, page_number=1,
                x_position_points=72, y_position_points=600,
                width_points=200, height_points=24,
            ),
        ]
        ordered = assign_tab_order(fields)
        # y=600 is higher on page (PDF coords), so tab_order=1
        assert ordered[0].y_position_points == 600
        assert ordered[0].tab_order == 1
        assert ordered[1].y_position_points == 200
        assert ordered[1].tab_order == 2

    def test_tab_order_across_pages(self):
        """Page 1 fields should come before page 2 fields."""
        fields = [
            DetectedField(
                field_type=DetectedFieldType.SIGNATURE, page_number=2,
                x_position_points=72, y_position_points=700,
                width_points=200, height_points=36,
            ),
            DetectedField(
                field_type=DetectedFieldType.TEXT, page_number=1,
                x_position_points=72, y_position_points=100,
                width_points=200, height_points=24,
            ),
        ]
        ordered = assign_tab_order(fields)
        assert ordered[0].page_number == 1
        assert ordered[0].tab_order == 1
        assert ordered[1].page_number == 2
        assert ordered[1].tab_order == 2

    def test_tab_order_left_to_right_same_row(self):
        """Fields at the same y should be ordered left to right."""
        fields = [
            DetectedField(
                field_type=DetectedFieldType.TEXT, page_number=1,
                x_position_points=360, y_position_points=500,
                width_points=200, height_points=24,
            ),
            DetectedField(
                field_type=DetectedFieldType.TEXT, page_number=1,
                x_position_points=72, y_position_points=500,
                width_points=200, height_points=24,
            ),
        ]
        ordered = assign_tab_order(fields)
        assert ordered[0].x_position_points == 72
        assert ordered[0].tab_order == 1
        assert ordered[1].x_position_points == 360
        assert ordered[1].tab_order == 2


@pytest.mark.unit
class TestRequiredVsOptionalDetermination:
    """Test logic for determining whether a field is required or optional."""

    def test_signature_always_required(self):
        """Signature fields should always be required."""
        assert determine_required(DetectedFieldType.SIGNATURE) is True

    def test_initial_always_required(self):
        """Initial fields should always be required."""
        assert determine_required(DetectedFieldType.INITIAL) is True

    def test_date_signed_always_required(self):
        """Date signed fields should always be required."""
        assert determine_required(DetectedFieldType.DATE_SIGNED) is True

    def test_optional_label_makes_field_optional(self):
        """A text field with 'optional' in the label should not be required."""
        assert determine_required(DetectedFieldType.TEXT, "Phone (optional)") is False

    def test_ssn_field_is_required(self):
        """SSN field should be required even though it is text type."""
        assert determine_required(DetectedFieldType.TEXT, "SSN") is True

    def test_generic_text_field_not_required(self):
        """A generic text field with no special label should default to not required."""
        assert determine_required(DetectedFieldType.TEXT, "Notes") is False

    def test_checkbox_not_required_by_default(self):
        """Checkboxes should not be required by default."""
        assert determine_required(DetectedFieldType.CHECKBOX, "I agree") is False


@pytest.mark.unit
class TestCheckboxDetection:
    """Test detection of checkbox fields."""

    def test_square_bracket_checkbox_detected(self):
        """'[ ] I agree' should detect a checkbox."""
        texts = [
            PageText("[ ] I agree to the terms", x0=72, y0=400, x1=250, y1=412, page_number=1),
        ]
        fields = detect_checkbox(texts)
        assert len(fields) == 1
        assert fields[0].field_type == DetectedFieldType.CHECKBOX

    def test_parentheses_checkbox_detected(self):
        """'( ) Option A' should detect a checkbox."""
        texts = [
            PageText("( ) Option A", x0=72, y0=380, x1=180, y1=392, page_number=1),
        ]
        fields = detect_checkbox(texts)
        assert len(fields) == 1
        assert fields[0].field_type == DetectedFieldType.CHECKBOX

    def test_multiple_checkboxes_in_same_line(self):
        """Multiple checkboxes on the same line should each be detected."""
        texts = [
            PageText("[ ] Yes  [ ] No", x0=72, y0=400, x1=200, y1=412, page_number=1),
        ]
        fields = detect_checkbox(texts)
        assert len(fields) == 2

    def test_checkbox_size_is_small(self):
        """Checkboxes should be 14x14 points."""
        texts = [
            PageText("[ ] Agree", x0=72, y0=400, x1=150, y1=412, page_number=1),
        ]
        fields = detect_checkbox(texts)
        assert fields[0].width_points == 14.0
        assert fields[0].height_points == 14.0


@pytest.mark.unit
class TestForm4506TFieldMapping:
    """Test pre-mapped fields for IRS Form 4506-T."""

    def test_4506t_has_signature_field(self):
        """4506-T mapping should include a signature field."""
        fields = map_4506t_fields()
        sig_fields = [f for f in fields if f.field_type == DetectedFieldType.SIGNATURE]
        assert len(sig_fields) >= 1
        assert sig_fields[0].form_field_id == "4506t_signature"

    def test_4506t_has_date_field(self):
        """4506-T mapping should include a date field."""
        fields = map_4506t_fields()
        date_fields = [f for f in fields if f.field_type == DetectedFieldType.DATE_SIGNED]
        assert len(date_fields) >= 1

    def test_4506t_has_name_and_ssn(self):
        """4506-T should have Name and SSN text fields."""
        fields = map_4506t_fields()
        text_fields = [f for f in fields if f.field_type == DetectedFieldType.TEXT]
        labels = {f.label for f in text_fields}
        assert "Name" in labels
        assert "SSN" in labels

    def test_4506t_has_checkbox(self):
        """4506-T should have at least one checkbox."""
        fields = map_4506t_fields()
        checkboxes = [f for f in fields if f.field_type == DetectedFieldType.CHECKBOX]
        assert len(checkboxes) >= 1

    def test_4506t_all_fields_high_confidence(self):
        """Pre-mapped form fields should have confidence >= 0.95."""
        fields = map_4506t_fields()
        for f in fields:
            assert f.confidence >= 0.95, f"Field {f.form_field_id} confidence too low: {f.confidence}"


@pytest.mark.unit
class TestLOETemplateFields:
    """Test pre-mapped fields for Letter of Explanation templates."""

    def test_loe_has_borrower_name(self):
        """LOE template should have a borrower name text field."""
        fields = map_loe_fields()
        name_fields = [f for f in fields if f.form_field_id == "loe_borrower_name"]
        assert len(name_fields) == 1
        assert name_fields[0].field_type == DetectedFieldType.TEXT

    def test_loe_has_signature(self):
        """LOE template should have a signature field."""
        fields = map_loe_fields()
        sig_fields = [f for f in fields if f.field_type == DetectedFieldType.SIGNATURE]
        assert len(sig_fields) == 1

    def test_loe_has_date(self):
        """LOE template should have a date field."""
        fields = map_loe_fields()
        date_fields = [f for f in fields if f.field_type == DetectedFieldType.DATE_SIGNED]
        assert len(date_fields) == 1

    def test_loe_fields_assigned_to_borrower(self):
        """All LOE fields should be assigned to the borrower role."""
        fields = map_loe_fields()
        for f in fields:
            assert f.signer_role == SignerRole.BORROWER


@pytest.mark.unit
class TestConfidenceScoring:
    """Test that confidence scores are appropriate for different detection methods."""

    def test_known_form_fields_highest_confidence(self):
        """Pre-mapped known form fields should have confidence >= 0.90."""
        fields = map_1003_fields(page_count=5)
        for f in fields:
            assert f.confidence >= 0.90

    def test_signature_line_has_high_confidence(self):
        """Signature line + label detection should have confidence >= 0.85."""
        texts = [PageText("Borrower Signature", x0=72, y0=100, x1=200, y1=112, page_number=1)]
        lines = [PageLine(x0=72, y0=130, x1=280, y1=130, page_number=1)]
        fields = detect_signature_line(texts, lines)
        assert fields[0].confidence >= 0.85

    def test_x_blank_moderate_confidence(self):
        """X___ pattern should have moderate confidence (0.80-0.90)."""
        texts = [PageText("X__________", x0=72, y0=200, x1=200, y1=212, page_number=1)]
        fields = detect_x_blank_pattern(texts)
        assert 0.80 <= fields[0].confidence <= 0.90

    def test_text_input_lowest_confidence(self):
        """Generic text input detection should have lowest confidence."""
        texts = [PageText("Phone: __________", x0=72, y0=500, x1=200, y1=512, page_number=1)]
        fields = detect_text_input_field(texts)
        assert fields[0].confidence < 0.80


@pytest.mark.unit
class TestEmptyVsFilledFormHandling:
    """Test distinguishing between empty forms and already-filled forms."""

    def test_empty_form_detected(self):
        """A form with many underscores and little other text should be detected as empty."""
        texts = [
            PageText("Name: __________________", x0=72, y0=600, x1=300, y1=612, page_number=1),
            PageText("Address: ____________________________", x0=72, y0=580, x1=400, y1=592, page_number=1),
            PageText("Phone: ______________", x0=72, y0=560, x1=250, y1=572, page_number=1),
            PageText("SSN: _________________", x0=72, y0=540, x1=250, y1=552, page_number=1),
            PageText("Signature: ______________________", x0=72, y0=100, x1=300, y1=112, page_number=1),
        ]
        is_filled = detect_filled_form(texts)
        assert is_filled is False

    def test_filled_form_detected(self):
        """A form with substantial text and few underscores should be detected as filled."""
        texts = [
            PageText("Name: John Michael Smith", x0=72, y0=600, x1=300, y1=612, page_number=1),
            PageText("Address: 123 Main Street, Springfield, IL 62701", x0=72, y0=580, x1=400, y1=592, page_number=1),
            PageText("Phone: (555) 123-4567", x0=72, y0=560, x1=250, y1=572, page_number=1),
            PageText("Social Security Number: XXX-XX-1234", x0=72, y0=540, x1=300, y1=552, page_number=1),
            PageText("Loan Amount: $425,000.00", x0=72, y0=520, x1=250, y1=532, page_number=1),
            PageText("Property Type: Single Family Residence", x0=72, y0=500, x1=350, y1=512, page_number=1),
            PageText("Occupancy: Primary Residence", x0=72, y0=480, x1=300, y1=492, page_number=1),
            PageText("This is to certify that the information provided is true and correct.", x0=72, y0=200, x1=500, y1=212, page_number=1),
        ]
        is_filled = detect_filled_form(texts)
        assert is_filled is True

    def test_empty_document_not_filled(self):
        """An empty document (no text) should not be detected as filled."""
        texts = []
        is_filled = detect_filled_form(texts)
        assert is_filled is False


@pytest.mark.unit
class TestForm1003FieldMapping:
    """Test pre-mapped fields for the Uniform Residential Loan Application (1003)."""

    def test_1003_has_borrower_and_coborrower_signatures(self):
        """1003 should have both borrower and co-borrower signature fields."""
        fields = map_1003_fields(page_count=8)
        sig_fields = [f for f in fields if f.field_type == DetectedFieldType.SIGNATURE]
        roles = {f.signer_role for f in sig_fields}
        assert SignerRole.BORROWER in roles
        assert SignerRole.CO_BORROWER in roles

    def test_1003_signatures_on_last_page(self):
        """1003 signature fields should be on the last page."""
        page_count = 8
        fields = map_1003_fields(page_count=page_count)
        sig_fields = [f for f in fields if f.field_type == DetectedFieldType.SIGNATURE]
        for f in sig_fields:
            assert f.page_number == page_count

    def test_1003_has_date_fields(self):
        """1003 should have date fields for both borrower and co-borrower."""
        fields = map_1003_fields(page_count=5)
        date_fields = [f for f in fields if f.field_type == DetectedFieldType.DATE_SIGNED]
        assert len(date_fields) == 2
        roles = {f.signer_role for f in date_fields}
        assert SignerRole.BORROWER in roles
        assert SignerRole.CO_BORROWER in roles

    def test_1003_coborrower_fields_right_of_borrower(self):
        """Co-borrower fields should be positioned to the right of borrower fields."""
        fields = map_1003_fields(page_count=5)
        borrower_sig = next(f for f in fields if f.form_field_id == "1003_borrower_signature")
        coborrower_sig = next(f for f in fields if f.form_field_id == "1003_coborrower_signature")
        assert coborrower_sig.x_position_points > borrower_sig.x_position_points


@pytest.mark.unit
class TestSignerRoleInference:
    """Test signer role inference from label text."""

    def test_borrower_inferred(self):
        """'Borrower Signature' should infer BORROWER role."""
        assert _infer_signer_role("Borrower Signature") == SignerRole.BORROWER

    def test_coborrower_inferred_hyphenated(self):
        """'Co-Borrower Signature' should infer CO_BORROWER role."""
        assert _infer_signer_role("Co-Borrower Signature") == SignerRole.CO_BORROWER

    def test_coborrower_inferred_no_hyphen(self):
        """'Coborrower' should also infer CO_BORROWER role."""
        assert _infer_signer_role("Coborrower Initials") == SignerRole.CO_BORROWER

    def test_notary_inferred(self):
        """'Notary Signature' should infer NOTARY role."""
        assert _infer_signer_role("Notary Signature") == SignerRole.NOTARY

    def test_unknown_for_generic_label(self):
        """A generic label should return UNKNOWN role."""
        assert _infer_signer_role("Signature") == SignerRole.UNKNOWN

    def test_borrower_takes_precedence_over_coborrower_substring(self):
        """'Borrower' alone (not 'Co-Borrower') should be BORROWER."""
        assert _infer_signer_role("Primary Borrower Sign") == SignerRole.BORROWER
