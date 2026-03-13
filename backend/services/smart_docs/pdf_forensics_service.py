"""
PDF Forensics Service

Deep structural and metadata analysis of PDF documents for fraud detection.
Uses pypdf (or PyPDF2) for PDF parsing with graceful degradation when
neither library is available.

Usage:
    from services.smart_docs.pdf_forensics_service import (
        PDFForensicsService, get_pdf_forensics_service,
    )

    service = get_pdf_forensics_service()
    report = service.generate_forensics_report(
        file_bytes=pdf_bytes,
        doc_type="paystub",
    )
    if report.risk_score >= 70:
        ...  # flag for review
"""

import io
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Check for pypdf availability at module load
_pdf_reader_class = None
_pdf_library = None

try:
    from pypdf import PdfReader as _PdfReader
    _pdf_reader_class = _PdfReader
    _pdf_library = "pypdf"
except ImportError:
    try:
        from PyPDF2 import PdfReader as _PdfReader2  # type: ignore[no-redef]
        _pdf_reader_class = _PdfReader2
        _pdf_library = "PyPDF2"
    except ImportError:
        logger.warning(
            "Neither pypdf nor PyPDF2 is available. "
            "PDF forensics will use fallback regex-based analysis."
        )


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ForensicsFinding:
    """A single forensics finding."""
    category: str  # metadata, fonts, overlay, image, date, editing
    severity: str  # critical, high, medium, low
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ForensicsReport:
    """Comprehensive PDF forensics analysis report."""
    filename: str = ""
    doc_type: str = ""
    analysis_timestamp: str = ""
    pdf_version: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    fonts: Dict[str, Any] = field(default_factory=dict)
    images: Dict[str, Any] = field(default_factory=dict)
    overlays: List[Dict[str, Any]] = field(default_factory=list)
    editing_traces: List[Dict[str, Any]] = field(default_factory=list)
    date_analysis: Dict[str, Any] = field(default_factory=dict)
    findings: List[ForensicsFinding] = field(default_factory=list)
    risk_score: float = 0.0
    risk_level: str = "LOW"
    library_used: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "doc_type": self.doc_type,
            "analysis_timestamp": self.analysis_timestamp,
            "pdf_version": self.pdf_version,
            "metadata": self.metadata,
            "fonts": self.fonts,
            "images": self.images,
            "overlays": self.overlays,
            "editing_traces": self.editing_traces,
            "date_analysis": self.date_analysis,
            "findings": [
                {
                    "category": f.category,
                    "severity": f.severity,
                    "description": f.description,
                    "evidence": f.evidence,
                }
                for f in self.findings
            ],
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "library_used": self.library_used,
        }


# =============================================================================
# KNOWN EDITING SOFTWARE FINGERPRINTS
# =============================================================================

EDITING_SOFTWARE = {
    "photoshop", "gimp", "illustrator", "inkscape", "paint",
    "canva", "pixlr", "affinity", "corel", "sketch",
    "figma", "procreate", "paint.net", "krita",
    "foxit phantompdf", "nitro pro", "pdf-xchange",
}

# Document producers that are legitimate for financial documents
LEGITIMATE_FINANCIAL_PRODUCERS = {
    "adp", "paychex", "gusto", "quickbooks", "intuit",
    "workday", "ceridian", "paylocity", "paycom", "ultipro",
    "chase", "wells fargo", "bank of america", "citi", "capital one",
    "usaa", "navy federal", "pnc", "td bank", "us bank",
    "irs", "turbotax", "h&r block", "jackson hewitt", "taxact",
    "encompass", "calyx", "ellie mae", "ice mortgage",
    "crystal reports", "jasperreports", "ssrs",
    "apache fop", "itext", "reportlab", "wkhtmltopdf",
    "microsoft", "libreoffice", "openoffice",
}


# =============================================================================
# PDF FORENSICS SERVICE
# =============================================================================

class PDFForensicsService:
    """
    Deep PDF forensics analysis for fraud detection.

    Capabilities:
    1. Metadata extraction and analysis (creator, producer, dates)
    2. Font analysis (consistency, count, type mixing)
    3. Overlaid object detection (text-on-text replacement)
    4. Embedded image analysis (DPI, dimensions, compression)
    5. Creation date validity checking
    6. Editing software fingerprint detection
    7. Comprehensive report generation with risk scoring
    """

    def __init__(self):
        self.pdf_library = _pdf_library

    def extract_metadata(self, file_bytes: bytes) -> Dict[str, Any]:
        """
        Extract PDF metadata: creator, producer, dates, version.

        Returns dict with keys: creator, producer, creation_date,
        modification_date, pdf_version, title, author, subject, page_count.
        """
        result: Dict[str, Any] = {
            "creator": None,
            "producer": None,
            "creation_date": None,
            "modification_date": None,
            "pdf_version": None,
            "title": None,
            "author": None,
            "subject": None,
            "page_count": 0,
        }

        if _pdf_reader_class:
            try:
                reader = _pdf_reader_class(io.BytesIO(file_bytes))
                result["page_count"] = len(reader.pages)

                meta = reader.metadata
                if meta:
                    result["creator"] = self._get_meta_field(meta, "creator", "/Creator")
                    result["producer"] = self._get_meta_field(meta, "producer", "/Producer")
                    result["title"] = self._get_meta_field(meta, "title", "/Title")
                    result["author"] = self._get_meta_field(meta, "author", "/Author")
                    result["subject"] = self._get_meta_field(meta, "subject", "/Subject")

                    creation = self._get_meta_field(meta, "creation_date", "/CreationDate")
                    modification = self._get_meta_field(meta, "modification_date", "/ModDate")
                    result["creation_date"] = str(creation) if creation else None
                    result["modification_date"] = str(modification) if modification else None

                if hasattr(reader, 'pdf_header'):
                    result["pdf_version"] = str(reader.pdf_header)

                return result
            except Exception as e:
                logger.debug("pypdf metadata extraction failed: %s", e)

        # Fallback: regex-based extraction
        return self._extract_metadata_regex(file_bytes, result)

    def analyze_fonts(self, file_bytes: bytes) -> Dict[str, Any]:
        """
        List all fonts used in the PDF and flag inconsistencies.

        Returns dict with: fonts (list), font_count, unique_families,
        font_types, inconsistencies (list of issues).
        """
        result: Dict[str, Any] = {
            "fonts": [],
            "font_count": 0,
            "unique_families": [],
            "font_types": [],
            "inconsistencies": [],
        }

        fonts: List[str] = []
        font_type_set: set = set()

        if _pdf_reader_class:
            try:
                reader = _pdf_reader_class(io.BytesIO(file_bytes))

                for page_num, page in enumerate(reader.pages):
                    page_fonts = self._extract_page_fonts(page, page_num)
                    fonts.extend(page_fonts)

            except Exception as e:
                logger.debug("pypdf font analysis failed: %s", e)

        # Fallback if no fonts found via pypdf
        if not fonts:
            fonts = self._extract_fonts_regex(file_bytes)

        # Deduplicate
        fonts = list(set(fonts))
        result["fonts"] = fonts
        result["font_count"] = len(fonts)

        # Extract font families
        families: set = set()
        for font_name in fonts:
            family = re.sub(
                r'[-,]?(Bold|Italic|Regular|Light|Medium|Thin|Condensed|'
                r'Black|Oblique|Semibold|ExtraBold|ExtraLight|Book|Demi).*',
                '', font_name, flags=re.IGNORECASE,
            ).strip()
            if family:
                families.add(family)

            # Categorize font type
            if any(t in font_name for t in ("Type1", "T1")):
                font_type_set.add("Type1")
            elif any(t in font_name for t in ("TrueType", "TT")):
                font_type_set.add("TrueType")
            elif any(t in font_name for t in ("CIDFont", "CID")):
                font_type_set.add("CID")
            elif any(t in font_name for t in ("OpenType", "OT")):
                font_type_set.add("OpenType")

        result["unique_families"] = sorted(families)
        result["font_types"] = sorted(font_type_set)

        # Flag inconsistencies
        if len(families) > 8:
            result["inconsistencies"].append({
                "type": "excessive_font_families",
                "detail": (
                    f"{len(families)} distinct font families detected "
                    f"(typical documents use 2-5)"
                ),
                "families": sorted(families),
            })

        if len(font_type_set) > 2:
            result["inconsistencies"].append({
                "type": "mixed_font_technologies",
                "detail": f"Mixes {len(font_type_set)} font technologies: {', '.join(sorted(font_type_set))}",
                "types": sorted(font_type_set),
            })

        return result

    def detect_overlaid_objects(self, file_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Find suspicious text overlay regions in the PDF.

        Detects text positioning commands (Tm) at identical or very close
        coordinates, which may indicate text placed over existing content.
        """
        overlays: List[Dict[str, Any]] = []

        if not _pdf_reader_class:
            return overlays

        try:
            reader = _pdf_reader_class(io.BytesIO(file_bytes))

            for page_num, page in enumerate(reader.pages):
                content_data = self._get_page_content_data(page)
                if not content_data:
                    continue

                content_str = content_data.decode("latin-1", errors="replace")

                # Find text matrix operations: a b c d tx ty Tm
                tm_ops = re.findall(
                    r'([\d.e+-]+)\s+([\d.e+-]+)\s+([\d.e+-]+)\s+([\d.e+-]+)\s+'
                    r'([\d.e+-]+)\s+([\d.e+-]+)\s+Tm',
                    content_str,
                )

                if len(tm_ops) < 2:
                    continue

                # Group by position (rounded to nearest integer)
                positions: Dict[str, List[int]] = {}
                for i, tm in enumerate(tm_ops):
                    try:
                        tx = round(float(tm[4]))
                        ty = round(float(tm[5]))
                        pos_key = f"{tx},{ty}"
                        positions.setdefault(pos_key, []).append(i)
                    except (ValueError, IndexError):
                        continue

                for pos_key, indices in positions.items():
                    if len(indices) > 1:
                        overlays.append({
                            "page": page_num + 1,
                            "position": pos_key,
                            "overlap_count": len(indices),
                            "description": (
                                f"Page {page_num + 1}: {len(indices)} text blocks "
                                f"at position ({pos_key})"
                            ),
                        })

        except Exception as e:
            logger.debug("Overlay detection failed: %s", e)

        return overlays

    def analyze_images_in_pdf(self, file_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extract and check embedded images in the PDF.

        Returns list of image info dicts with: page, width, height,
        bits_per_component, color_space, filter, estimated_dpi.
        """
        images: List[Dict[str, Any]] = []

        if not _pdf_reader_class:
            return images

        try:
            reader = _pdf_reader_class(io.BytesIO(file_bytes))

            for page_num, page in enumerate(reader.pages):
                resources = page.get("/Resources")
                if not resources:
                    continue

                xobjects = self._safe_get(resources, "/XObject")
                if not xobjects:
                    continue

                if hasattr(xobjects, 'get_object'):
                    xobjects = xobjects.get_object()

                if not hasattr(xobjects, 'keys'):
                    continue

                # Get page dimensions for DPI estimation
                page_width_pts, page_height_pts = self._get_page_dimensions(page)

                for obj_key in xobjects.keys():
                    try:
                        xobj = xobjects[obj_key]
                        if hasattr(xobj, 'get_object'):
                            xobj = xobj.get_object()

                        subtype = self._safe_get(xobj, "/Subtype")
                        if str(subtype) != "/Image":
                            continue

                        img_info: Dict[str, Any] = {
                            "page": page_num + 1,
                            "object_key": str(obj_key),
                        }

                        width = self._safe_get_int(xobj, "/Width")
                        height = self._safe_get_int(xobj, "/Height")
                        if width:
                            img_info["width"] = width
                        if height:
                            img_info["height"] = height

                        bpc = self._safe_get_int(xobj, "/BitsPerComponent")
                        if bpc:
                            img_info["bits_per_component"] = bpc

                        cs = self._safe_get(xobj, "/ColorSpace")
                        if cs:
                            img_info["color_space"] = str(cs)

                        filt = self._safe_get(xobj, "/Filter")
                        if filt:
                            img_info["filter"] = str(filt)

                        # Estimate DPI
                        if width and height and page_width_pts and page_height_pts:
                            dpi_x = round(width / (page_width_pts / 72.0))
                            dpi_y = round(height / (page_height_pts / 72.0))
                            img_info["estimated_dpi"] = (dpi_x, dpi_y)

                        images.append(img_info)

                    except Exception:
                        continue

        except Exception as e:
            logger.debug("Image analysis failed: %s", e)

        return images

    def check_creation_date_validity(
        self,
        metadata: Dict[str, Any],
        doc_type: str,
        doc_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Check if the PDF creation date is consistent with the purported document date.

        Flags:
        - Creation date in the future
        - Creation date significantly before document date (pre-fabricated)
        - Creation date on a weekend/holiday for financial institution docs
        - Mismatch between PDF creation date and document content date
        """
        result: Dict[str, Any] = {
            "is_valid": True,
            "issues": [],
            "creation_date_parsed": None,
            "doc_date": str(doc_date) if doc_date else None,
        }

        creation_str = metadata.get("creation_date")
        if not creation_str:
            return result

        creation_dt = self._parse_pdf_date(creation_str)
        if not creation_dt:
            return result

        result["creation_date_parsed"] = str(creation_dt)
        now = datetime.now(timezone.utc)

        # Check future date
        if creation_dt > now:
            result["is_valid"] = False
            result["issues"].append({
                "type": "future_creation_date",
                "severity": "high",
                "detail": f"PDF created in the future: {creation_dt}",
            })

        # Check against document date
        if doc_date:
            creation_date_only = creation_dt.date() if isinstance(creation_dt, datetime) else creation_dt

            # Document created significantly before its content date is suspicious
            # (e.g., a January 2026 paystub created in November 2025)
            days_before = (doc_date - creation_date_only).days
            if days_before > 30:
                result["is_valid"] = False
                result["issues"].append({
                    "type": "premature_creation",
                    "severity": "high",
                    "detail": (
                        f"PDF created {days_before} days before document date "
                        f"(created: {creation_date_only}, doc date: {doc_date})"
                    ),
                })

            # Document created long after its content date might be a re-creation
            days_after = (creation_date_only - doc_date).days
            if days_after > 90:
                result["issues"].append({
                    "type": "late_creation",
                    "severity": "medium",
                    "detail": (
                        f"PDF created {days_after} days after document date "
                        f"(may be a re-generated copy)"
                    ),
                })

        # Check if financial doc was created on a weekend
        financial_doc_types = {
            "paystub", "pay_stub", "w2", "w-2", "bank_statement",
            "tax_return", "1099",
        }
        if doc_type.lower().replace(" ", "_") in financial_doc_types:
            if creation_dt.weekday() in (5, 6):
                result["issues"].append({
                    "type": "weekend_creation",
                    "severity": "low",
                    "detail": (
                        f"Financial document PDF created on a "
                        f"{'Saturday' if creation_dt.weekday() == 5 else 'Sunday'}"
                    ),
                })

        if result["issues"]:
            # Set validity based on whether there are high-severity issues
            high_severity = any(
                i.get("severity") in ("high", "critical")
                for i in result["issues"]
            )
            result["is_valid"] = not high_severity

        return result

    def detect_editing_traces(self, file_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Check for editing software fingerprints in the PDF.

        Scans metadata, XMP data, and raw content for traces of
        image editors, PDF editors, and document manipulation tools.
        """
        traces: List[Dict[str, Any]] = []

        metadata = self.extract_metadata(file_bytes)

        # Check creator / producer
        for field_name in ("creator", "producer"):
            value = (metadata.get(field_name) or "").lower()
            for editor in EDITING_SOFTWARE:
                if editor in value:
                    traces.append({
                        "source": f"pdf_{field_name}",
                        "software": metadata.get(field_name),
                        "severity": "critical",
                        "description": (
                            f"PDF {field_name} is editing software: "
                            f"{metadata.get(field_name)}"
                        ),
                    })
                    break

        # Scan for XMP metadata editing traces in raw bytes
        try:
            content_sample = file_bytes[:200000].decode("latin-1", errors="replace")

            # Look for XMP creator tool
            xmp_match = re.search(
                r'<xmp:CreatorTool>([^<]+)</xmp:CreatorTool>',
                content_sample,
                re.IGNORECASE,
            )
            if xmp_match:
                creator_tool = xmp_match.group(1)
                for editor in EDITING_SOFTWARE:
                    if editor in creator_tool.lower():
                        traces.append({
                            "source": "xmp_creator_tool",
                            "software": creator_tool,
                            "severity": "critical",
                            "description": f"XMP CreatorTool is editing software: {creator_tool}",
                        })
                        break

            # Look for editing history in XMP
            history_match = re.search(
                r'<stEvt:softwareAgent>([^<]+)</stEvt:softwareAgent>',
                content_sample,
                re.IGNORECASE,
            )
            if history_match:
                agent = history_match.group(1)
                for editor in EDITING_SOFTWARE:
                    if editor in agent.lower():
                        traces.append({
                            "source": "xmp_edit_history",
                            "software": agent,
                            "severity": "high",
                            "description": f"XMP edit history shows: {agent}",
                        })
                        break

            # Check for Photoshop-specific markers
            if b"photoshop" in file_bytes[:500000].lower():
                # Look for 8BIM markers (Photoshop resource blocks)
                bim_count = file_bytes[:500000].count(b"8BIM")
                if bim_count > 0:
                    traces.append({
                        "source": "photoshop_markers",
                        "software": "Adobe Photoshop",
                        "severity": "critical",
                        "description": (
                            f"Found {bim_count} Photoshop resource blocks (8BIM markers)"
                        ),
                    })

        except Exception as e:
            logger.debug("Editing trace scan error: %s", e)

        return traces

    def generate_forensics_report(
        self,
        file_bytes: bytes,
        doc_type: str,
        filename: str = "",
        doc_date: Optional[date] = None,
    ) -> ForensicsReport:
        """
        Generate a comprehensive PDF forensics report.

        Runs all analysis methods and compiles results into a single report
        with an aggregate risk score.
        """
        report = ForensicsReport(
            filename=filename,
            doc_type=doc_type,
            analysis_timestamp=datetime.now(timezone.utc).isoformat(),
            library_used=self.pdf_library,
        )

        # 1. Metadata extraction
        report.metadata = self.extract_metadata(file_bytes)
        report.pdf_version = report.metadata.get("pdf_version")

        # 2. Font analysis
        report.fonts = self.analyze_fonts(file_bytes)

        # 3. Overlay detection
        report.overlays = self.detect_overlaid_objects(file_bytes)

        # 4. Image analysis
        images = self.analyze_images_in_pdf(file_bytes)
        report.images = {
            "count": len(images),
            "details": images,
            "dpi_values": [
                img.get("estimated_dpi")
                for img in images
                if img.get("estimated_dpi")
            ],
        }

        # 5. Date validity
        report.date_analysis = self.check_creation_date_validity(
            report.metadata, doc_type, doc_date,
        )

        # 6. Editing traces
        report.editing_traces = self.detect_editing_traces(file_bytes)

        # 7. Compile findings
        report.findings = self._compile_findings(report)

        # 8. Calculate risk score
        report.risk_score, report.risk_level = self._calculate_risk_score(
            report.findings,
        )

        return report

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _compile_findings(self, report: ForensicsReport) -> List[ForensicsFinding]:
        """Compile all findings from analysis results."""
        findings: List[ForensicsFinding] = []

        # Metadata findings
        creator = (report.metadata.get("creator") or "").lower()
        producer = (report.metadata.get("producer") or "").lower()
        for editor in EDITING_SOFTWARE:
            if editor in creator or editor in producer:
                findings.append(ForensicsFinding(
                    category="metadata",
                    severity="critical",
                    description=(
                        f"Document created with editing software: "
                        f"{report.metadata.get('creator') or report.metadata.get('producer')}"
                    ),
                    evidence={
                        "creator": report.metadata.get("creator"),
                        "producer": report.metadata.get("producer"),
                    },
                ))
                break

        # Modification gap
        creation_dt = self._parse_pdf_date(report.metadata.get("creation_date"))
        mod_dt = self._parse_pdf_date(report.metadata.get("modification_date"))
        if creation_dt and mod_dt:
            gap_hours = abs((mod_dt - creation_dt).total_seconds()) / 3600
            if gap_hours > 24:
                severity = "high" if gap_hours > 72 else "medium"
                findings.append(ForensicsFinding(
                    category="metadata",
                    severity=severity,
                    description=f"Document modified {gap_hours:.0f} hours after creation",
                    evidence={
                        "creation_date": str(creation_dt),
                        "modification_date": str(mod_dt),
                        "gap_hours": round(gap_hours, 1),
                    },
                ))

        # Font findings
        for inconsistency in report.fonts.get("inconsistencies", []):
            findings.append(ForensicsFinding(
                category="fonts",
                severity="medium",
                description=inconsistency.get("detail", "Font inconsistency"),
                evidence=inconsistency,
            ))

        # Overlay findings
        if report.overlays:
            findings.append(ForensicsFinding(
                category="overlay",
                severity="high",
                description=(
                    f"Detected {len(report.overlays)} potential text overlay regions"
                ),
                evidence={"overlays": report.overlays[:5]},
            ))

        # Image DPI consistency
        dpi_values = report.images.get("dpi_values", [])
        if len(dpi_values) >= 2:
            unique_dpis = set()
            for dpi in dpi_values:
                if isinstance(dpi, (tuple, list)):
                    unique_dpis.add(tuple(dpi))
                else:
                    unique_dpis.add(dpi)
            if len(unique_dpis) > 1:
                findings.append(ForensicsFinding(
                    category="image",
                    severity="medium",
                    description=(
                        f"Inconsistent DPI across {len(dpi_values)} images"
                    ),
                    evidence={"dpi_values": [str(d) for d in unique_dpis]},
                ))

        # Date validity findings
        for issue in report.date_analysis.get("issues", []):
            findings.append(ForensicsFinding(
                category="date",
                severity=issue.get("severity", "medium"),
                description=issue.get("detail", "Date issue"),
                evidence=issue,
            ))

        # Editing trace findings
        for trace in report.editing_traces:
            findings.append(ForensicsFinding(
                category="editing",
                severity=trace.get("severity", "high"),
                description=trace.get("description", "Editing trace detected"),
                evidence=trace,
            ))

        return findings

    def _calculate_risk_score(
        self, findings: List[ForensicsFinding]
    ) -> Tuple[float, str]:
        """Calculate risk score from findings."""
        severity_weights = {
            "critical": 25,
            "high": 15,
            "medium": 8,
            "low": 3,
        }

        if not findings:
            return 0.0, "LOW"

        raw_score = sum(
            severity_weights.get(f.severity, 3) for f in findings
        )
        score = min(float(raw_score), 100.0)

        if score >= 70:
            risk_level = "HIGH"
        elif score >= 40:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return score, risk_level

    def _get_meta_field(self, meta, attr_name: str, dict_key: str):
        """Safely get a metadata field by attribute or dict key."""
        if hasattr(meta, attr_name):
            val = getattr(meta, attr_name)
            if val is not None:
                return str(val) if not isinstance(val, (datetime, date)) else val
        if hasattr(meta, '__getitem__'):
            try:
                val = meta[dict_key]
                if val is not None:
                    return str(val)
            except (KeyError, TypeError):
                pass
        return None

    def _extract_page_fonts(self, page, page_num: int) -> List[str]:
        """Extract font names from a single PDF page."""
        fonts: List[str] = []

        resources = page.get("/Resources")
        if not resources:
            return fonts

        font_dict = self._safe_get(resources, "/Font")
        if not font_dict:
            return fonts

        if hasattr(font_dict, 'get_object'):
            font_dict = font_dict.get_object()

        if not hasattr(font_dict, 'keys'):
            return fonts

        for font_key in font_dict.keys():
            try:
                font_obj = font_dict[font_key]
                if hasattr(font_obj, 'get_object'):
                    font_obj = font_obj.get_object()

                base_font = self._safe_get(font_obj, "/BaseFont")
                if base_font:
                    name = str(base_font)
                    if name.startswith("/"):
                        name = name[1:]
                    fonts.append(name)
            except Exception:
                continue

        return fonts

    def _extract_fonts_regex(self, file_bytes: bytes) -> List[str]:
        """Fallback: extract font names via regex."""
        try:
            content = file_bytes[:200000].decode("latin-1", errors="replace")
            matches = re.findall(r'/BaseFont\s*/([^\s/\[\]<>()]+)', content)
            return list(set(matches))
        except Exception:
            return []

    def _extract_metadata_regex(
        self, file_bytes: bytes, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fallback: extract metadata via regex."""
        try:
            content = file_bytes[:65536].decode("latin-1", errors="replace")

            patterns = {
                "creator": r'/Creator\s*\(([^)]*)\)',
                "producer": r'/Producer\s*\(([^)]*)\)',
                "creation_date": r'/CreationDate\s*\(([^)]*)\)',
                "modification_date": r'/ModDate\s*\(([^)]*)\)',
                "title": r'/Title\s*\(([^)]*)\)',
                "author": r'/Author\s*\(([^)]*)\)',
            }

            for key, pattern in patterns.items():
                match = re.search(pattern, content)
                if match:
                    result[key] = match.group(1)

            version_match = re.match(r'%PDF-(\d+\.\d+)', content[:20])
            if version_match:
                result["pdf_version"] = version_match.group(1)

        except Exception as e:
            logger.debug("Regex metadata extraction failed: %s", e)

        return result

    def _get_page_content_data(self, page) -> Optional[bytes]:
        """Get raw content stream data from a PDF page."""
        try:
            if hasattr(page, 'get_contents'):
                contents = page.get_contents()
                if contents:
                    if hasattr(contents, 'get_data'):
                        return contents.get_data()
                    elif hasattr(contents, 'getData'):
                        return contents.getData()
            elif "/Contents" in page:
                contents = page["/Contents"]
                if hasattr(contents, 'get_object'):
                    contents = contents.get_object()
                if hasattr(contents, 'get_data'):
                    return contents.get_data()
        except Exception:
            pass
        return None

    def _get_page_dimensions(self, page) -> Tuple[Optional[float], Optional[float]]:
        """Get page width and height in points."""
        try:
            media_box = page.get("/MediaBox")
            if media_box:
                return float(str(media_box[2])), float(str(media_box[3]))
        except Exception:
            pass
        return None, None

    def _safe_get(self, obj, key: str):
        """Safely get a value from a PDF object or dict."""
        if hasattr(obj, 'get'):
            val = obj.get(key)
            return val
        if isinstance(obj, dict):
            return obj.get(key)
        return None

    def _safe_get_int(self, obj, key: str) -> Optional[int]:
        """Safely get an integer value from a PDF object."""
        val = self._safe_get(obj, key)
        if val is not None:
            try:
                return int(str(val))
            except (ValueError, TypeError):
                pass
        return None

    def _parse_pdf_date(self, date_str) -> Optional[datetime]:
        """Parse a PDF date string into a datetime."""
        if not date_str:
            return None

        if isinstance(date_str, datetime):
            if date_str.tzinfo is None:
                return date_str.replace(tzinfo=timezone.utc)
            return date_str

        date_str = str(date_str)

        # PDF date format: D:YYYYMMDDHHmmSS+HH'mm'
        match = re.match(
            r"D?:?(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?",
            date_str,
        )
        if match:
            groups = match.groups()
            try:
                return datetime(
                    int(groups[0]),
                    int(groups[1]),
                    int(groups[2]),
                    int(groups[3] or 0),
                    int(groups[4] or 0),
                    int(groups[5] or 0),
                    tzinfo=timezone.utc,
                )
            except (ValueError, TypeError):
                return None

        # Try ISO format
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            pass

        return None


# =============================================================================
# SINGLETON
# =============================================================================

def get_pdf_forensics_service() -> PDFForensicsService:
    """Get a PDFForensicsService instance."""
    return PDFForensicsService()
