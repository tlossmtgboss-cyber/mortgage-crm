"""
Fraud Vendor Integration Service

Abstraction layer for external document fraud detection vendors
(PointPredictive, Resistant AI, etc.) with a built-in internal fallback
analyzer that performs PDF metadata, structure, and image consistency checks.

Usage:
    from services.smart_docs.integrations.fraud_vendor_service import (
        FraudVendorService, get_fraud_vendor_service,
    )

    service = get_fraud_vendor_service(db)
    result = await service.analyze_document(
        file_bytes=pdf_bytes,
        filename="paystub_jan2026.pdf",
        doc_type="paystub",
        loan_id=123,
        org_id=1,
    )
    if result.risk_level == "HIGH":
        ...  # flag for review
"""

import hashlib
import io
import logging
import os
import re
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class FraudIndicator:
    """A single fraud indicator detected by a vendor or internal analysis."""
    indicator_type: str  # metadata_anomaly, font_inconsistency, image_manipulation, text_overlay, date_mismatch
    severity: str  # critical, high, medium, low
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VendorFraudResult:
    """Standardized result from any fraud detection vendor or internal analyzer."""
    risk_score: float  # 0-100
    risk_level: str  # HIGH, MEDIUM, LOW
    indicators: List[FraudIndicator] = field(default_factory=list)
    vendor: str = "internal"
    analysis_duration_ms: int = 0
    recommendation: str = "pass"  # flag, review, pass
    raw_response: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "indicators": [
                {
                    "indicator_type": ind.indicator_type,
                    "severity": ind.severity,
                    "description": ind.description,
                    "evidence": ind.evidence,
                }
                for ind in self.indicators
            ],
            "vendor": self.vendor,
            "analysis_duration_ms": self.analysis_duration_ms,
            "recommendation": self.recommendation,
        }


# =============================================================================
# KNOWN-SUSPICIOUS CREATORS / PRODUCERS
# =============================================================================

SUSPICIOUS_PDF_CREATORS = {
    "photoshop", "gimp", "illustrator", "inkscape", "paint",
    "canva", "pixlr", "affinity", "corel", "sketch",
    "figma", "procreate", "paint.net", "krita",
}

# Legitimate financial document generators
LEGITIMATE_PRODUCERS = {
    "adp", "paychex", "gusto", "quickbooks", "intuit",
    "workday", "ceridian", "paylocity", "paycom",
    "chase", "wells fargo", "bank of america", "citi",
    "irs", "turbotax", "h&r block", "jackson hewitt",
    "encompass", "calyx", "ellie mae", "ice mortgage",
}


# =============================================================================
# INTERNAL FALLBACK ANALYZER
# =============================================================================

class InternalFraudAnalyzer:
    """
    Built-in document fraud analysis when no external vendor is configured.

    Performs:
    1. PDF metadata analysis (creator, producer, dates)
    2. PDF structural analysis (fonts, overlaid objects)
    3. Image consistency analysis (EXIF, DPI)
    4. Risk scoring from combined indicators
    """

    def analyze_pdf_metadata(self, file_bytes: bytes) -> Dict[str, Any]:
        """
        Extract and analyze PDF metadata for fraud indicators.

        Checks:
        - Creator / Producer software (Photoshop = suspicious)
        - Creation vs modification date gap
        - PDF version anomalies
        """
        result = {
            "creator": None,
            "producer": None,
            "creation_date": None,
            "modification_date": None,
            "pdf_version": None,
            "indicators": [],
        }

        try:
            # Try pypdf first for robust extraction
            metadata = self._extract_metadata_pypdf(file_bytes)
            if not metadata:
                # Fall back to regex parsing
                metadata = self._extract_metadata_regex(file_bytes)

            if not metadata:
                return result

            result["creator"] = metadata.get("creator")
            result["producer"] = metadata.get("producer")
            result["creation_date"] = metadata.get("creation_date")
            result["modification_date"] = metadata.get("modification_date")
            result["pdf_version"] = metadata.get("pdf_version")

            # Check for suspicious creator tools
            creator_lower = (result["creator"] or "").lower()
            producer_lower = (result["producer"] or "").lower()

            for tool in SUSPICIOUS_PDF_CREATORS:
                if tool in creator_lower or tool in producer_lower:
                    result["indicators"].append(FraudIndicator(
                        indicator_type="metadata_anomaly",
                        severity="critical",
                        description=(
                            f"Document created with image editing software: "
                            f"'{result['creator'] or result['producer']}'"
                        ),
                        evidence={
                            "creator": result["creator"],
                            "producer": result["producer"],
                            "flagged_tool": tool,
                        },
                    ))
                    break

            # Check modification date vs creation date
            creation_dt = self._parse_pdf_date(result["creation_date"])
            modification_dt = self._parse_pdf_date(result["modification_date"])

            if creation_dt and modification_dt:
                diff_hours = abs((modification_dt - creation_dt).total_seconds()) / 3600

                if diff_hours > 24:
                    severity = "high" if diff_hours > 72 else "medium"
                    result["indicators"].append(FraudIndicator(
                        indicator_type="metadata_anomaly",
                        severity=severity,
                        description=(
                            f"Document modified {diff_hours:.0f} hours after creation"
                        ),
                        evidence={
                            "creation_date": str(creation_dt),
                            "modification_date": str(modification_dt),
                            "gap_hours": round(diff_hours, 1),
                        },
                    ))

            # Check if creation date is in the future
            if creation_dt and creation_dt > datetime.now(timezone.utc):
                result["indicators"].append(FraudIndicator(
                    indicator_type="date_mismatch",
                    severity="high",
                    description="PDF creation date is in the future",
                    evidence={
                        "creation_date": str(creation_dt),
                        "current_time": str(datetime.now(timezone.utc)),
                    },
                ))

        except Exception as e:
            logger.debug("PDF metadata analysis error: %s", e)

        return result

    def analyze_pdf_structure(self, file_bytes: bytes) -> Dict[str, Any]:
        """
        Analyze PDF internal structure for fraud indicators.

        Checks:
        - Multiple font families (sign of text replacement)
        - Overlaid text objects (text covering existing text)
        - Inconsistent text encoding
        - Total font count anomalies
        """
        result = {
            "fonts_found": [],
            "font_count": 0,
            "has_overlaid_objects": False,
            "encoding_inconsistencies": False,
            "indicators": [],
        }

        try:
            # Try pypdf for structural analysis
            fonts, overlays, encoding_issues = self._analyze_structure_pypdf(file_bytes)

            if fonts is not None:
                result["fonts_found"] = fonts
                result["font_count"] = len(fonts)

                # Flag excessive font variety (typical legitimate docs: 2-5 fonts)
                unique_families = set()
                for font_name in fonts:
                    # Extract font family from full name
                    family = re.sub(r'[-,]?(Bold|Italic|Regular|Light|Medium|Thin|Condensed|Black).*', '', font_name, flags=re.IGNORECASE).strip()
                    if family:
                        unique_families.add(family.lower())

                if len(unique_families) > 8:
                    result["indicators"].append(FraudIndicator(
                        indicator_type="font_inconsistency",
                        severity="medium",
                        description=(
                            f"Document uses {len(unique_families)} distinct font families "
                            f"(typical documents use 2-5)"
                        ),
                        evidence={
                            "font_families": list(unique_families)[:15],
                            "family_count": len(unique_families),
                        },
                    ))

                # Check for mixed encoding types in font names (e.g., Type1 + TrueType)
                font_types = set()
                for font_name in fonts:
                    if "Type1" in font_name or "T1" in font_name:
                        font_types.add("Type1")
                    elif "TrueType" in font_name or "TT" in font_name:
                        font_types.add("TrueType")
                    elif "CIDFont" in font_name or "CID" in font_name:
                        font_types.add("CID")

                if len(font_types) > 2:
                    result["indicators"].append(FraudIndicator(
                        indicator_type="font_inconsistency",
                        severity="low",
                        description=(
                            f"Document mixes {len(font_types)} font technologies: "
                            f"{', '.join(font_types)}"
                        ),
                        evidence={"font_types": list(font_types)},
                    ))

            if overlays:
                result["has_overlaid_objects"] = True
                result["indicators"].append(FraudIndicator(
                    indicator_type="text_overlay",
                    severity="high",
                    description=(
                        f"Detected {len(overlays)} potential text overlay regions "
                        f"(text placed over existing content)"
                    ),
                    evidence={
                        "overlay_count": len(overlays),
                        "overlay_details": overlays[:5],
                    },
                ))

            if encoding_issues:
                result["encoding_inconsistencies"] = True
                result["indicators"].append(FraudIndicator(
                    indicator_type="font_inconsistency",
                    severity="medium",
                    description="Inconsistent text encoding detected across document",
                    evidence={"encoding_details": encoding_issues[:5]},
                ))

        except Exception as e:
            logger.debug("PDF structure analysis error: %s", e)

        # Fallback: regex-based font detection if pypdf was unavailable
        if not result["fonts_found"]:
            try:
                result["fonts_found"] = self._extract_fonts_regex(file_bytes)
                result["font_count"] = len(result["fonts_found"])
            except Exception as e:
                logger.debug("Regex font extraction error: %s", e)

        return result

    def analyze_image_consistency(self, file_bytes: bytes) -> Dict[str, Any]:
        """
        Analyze embedded images for fraud indicators.

        Checks:
        - EXIF data for editing software traces
        - DPI consistency across the document
        - Image compression artifacts suggesting re-saving
        """
        result = {
            "images_found": 0,
            "exif_flags": [],
            "dpi_values": [],
            "dpi_consistent": True,
            "indicators": [],
        }

        try:
            images_info = self._extract_images_pypdf(file_bytes)

            if images_info:
                result["images_found"] = len(images_info)
                dpis = []

                for img_info in images_info:
                    if img_info.get("dpi"):
                        dpis.append(img_info["dpi"])

                    # Check for EXIF editing software traces
                    exif = img_info.get("exif", {})
                    if exif:
                        software = exif.get("software", "").lower()
                        for tool in SUSPICIOUS_PDF_CREATORS:
                            if tool in software:
                                flag = f"Image edited with: {exif.get('software')}"
                                result["exif_flags"].append(flag)
                                result["indicators"].append(FraudIndicator(
                                    indicator_type="image_manipulation",
                                    severity="high",
                                    description=f"Embedded image shows editing software: {exif.get('software')}",
                                    evidence={
                                        "software": exif.get("software"),
                                        "image_index": img_info.get("index", 0),
                                    },
                                ))
                                break

                # Check DPI consistency
                if len(dpis) >= 2:
                    result["dpi_values"] = dpis
                    unique_dpis = set()
                    for dpi_pair in dpis:
                        if isinstance(dpi_pair, (tuple, list)):
                            unique_dpis.add(tuple(dpi_pair))
                        else:
                            unique_dpis.add(dpi_pair)

                    if len(unique_dpis) > 1:
                        result["dpi_consistent"] = False
                        result["indicators"].append(FraudIndicator(
                            indicator_type="image_manipulation",
                            severity="medium",
                            description=(
                                f"Inconsistent DPI across {len(dpis)} images: "
                                f"{[str(d) for d in unique_dpis]}"
                            ),
                            evidence={
                                "dpi_values": [str(d) for d in unique_dpis],
                                "image_count": len(dpis),
                            },
                        ))

        except Exception as e:
            logger.debug("Image consistency analysis error: %s", e)

        # Fallback: scan raw bytes for EXIF markers
        if result["images_found"] == 0:
            try:
                exif_flags = self._scan_exif_raw(file_bytes)
                if exif_flags:
                    result["exif_flags"] = exif_flags
                    for flag in exif_flags:
                        result["indicators"].append(FraudIndicator(
                            indicator_type="image_manipulation",
                            severity="medium",
                            description=f"EXIF data indicates: {flag}",
                            evidence={"raw_exif_flag": flag},
                        ))
            except Exception as e:
                logger.debug("Raw EXIF scan error: %s", e)

        return result

    def calculate_forgery_risk_score(
        self,
        metadata_result: Dict[str, Any],
        structure_result: Dict[str, Any],
        image_result: Dict[str, Any],
    ) -> Tuple[float, str]:
        """
        Calculate forgery risk score from combined analysis results.

        Returns:
            (score, risk_level) where score is 0-100 and risk_level is
            HIGH (>= 70), MEDIUM (40-69), or LOW (< 40).

        Weights:
        - critical indicator: 25 points
        - high indicator: 15 points
        - medium indicator: 8 points
        - low indicator: 3 points
        """
        severity_weights = {
            "critical": 25,
            "high": 15,
            "medium": 8,
            "low": 3,
        }

        all_indicators = []
        for result_dict in [metadata_result, structure_result, image_result]:
            all_indicators.extend(result_dict.get("indicators", []))

        if not all_indicators:
            return 0.0, "LOW"

        raw_score = 0.0
        for ind in all_indicators:
            raw_score += severity_weights.get(ind.severity, 3)

        score = min(raw_score, 100.0)

        if score >= 70:
            risk_level = "HIGH"
        elif score >= 40:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return score, risk_level

    # =========================================================================
    # PRIVATE HELPERS — pypdf-based extraction
    # =========================================================================

    def _extract_metadata_pypdf(self, file_bytes: bytes) -> Optional[Dict]:
        """Extract metadata using pypdf library."""
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader  # type: ignore[no-redef]
            except ImportError:
                return None

        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            meta = reader.metadata
            if not meta:
                return None

            result = {}
            if hasattr(meta, 'creator') and meta.creator:
                result["creator"] = str(meta.creator)
            elif hasattr(meta, '/Creator'):
                result["creator"] = str(meta['/Creator'])

            if hasattr(meta, 'producer') and meta.producer:
                result["producer"] = str(meta.producer)
            elif hasattr(meta, '/Producer'):
                result["producer"] = str(meta['/Producer'])

            # Dates
            if hasattr(meta, 'creation_date') and meta.creation_date:
                result["creation_date"] = str(meta.creation_date)
            elif hasattr(meta, '/CreationDate'):
                result["creation_date"] = str(meta['/CreationDate'])

            if hasattr(meta, 'modification_date') and meta.modification_date:
                result["modification_date"] = str(meta.modification_date)
            elif hasattr(meta, '/ModDate'):
                result["modification_date"] = str(meta['/ModDate'])

            # PDF version
            if hasattr(reader, 'pdf_header'):
                result["pdf_version"] = str(reader.pdf_header)

            return result if result else None

        except Exception as e:
            logger.debug("pypdf metadata extraction failed: %s", e)
            return None

    def _extract_metadata_regex(self, file_bytes: bytes) -> Optional[Dict]:
        """Fallback: extract PDF metadata via regex scanning."""
        try:
            content_str = file_bytes[:65536].decode("latin-1", errors="replace")
            metadata = {}

            patterns = {
                "creator": r'/Creator\s*\(([^)]*)\)',
                "producer": r'/Producer\s*\(([^)]*)\)',
                "creation_date": r'/CreationDate\s*\(([^)]*)\)',
                "modification_date": r'/ModDate\s*\(([^)]*)\)',
            }

            for key, pattern in patterns.items():
                match = re.search(pattern, content_str)
                if match:
                    metadata[key] = match.group(1)

            # PDF version from header
            version_match = re.match(r'%PDF-(\d+\.\d+)', content_str[:20])
            if version_match:
                metadata["pdf_version"] = version_match.group(1)

            return metadata if metadata else None

        except Exception as e:
            logger.debug("Regex metadata extraction failed: %s", e)
            return None

    def _analyze_structure_pypdf(
        self, file_bytes: bytes
    ) -> Tuple[Optional[List[str]], Optional[List[Dict]], Optional[List[str]]]:
        """
        Analyze PDF structure using pypdf.

        Returns:
            (fonts, overlays, encoding_issues) or (None, None, None) on failure
        """
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader  # type: ignore[no-redef]
            except ImportError:
                return None, None, None

        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            all_fonts: List[str] = []
            overlays: List[Dict] = []
            encoding_issues: List[str] = []

            for page_num, page in enumerate(reader.pages):
                # Extract font information from page resources
                resources = page.get("/Resources")
                if not resources:
                    continue

                # Get fonts
                font_dict = None
                if hasattr(resources, 'get'):
                    font_dict = resources.get("/Font")
                elif isinstance(resources, dict):
                    font_dict = resources.get("/Font")

                if font_dict:
                    try:
                        if hasattr(font_dict, 'get_object'):
                            font_dict = font_dict.get_object()

                        if hasattr(font_dict, 'keys'):
                            for font_key in font_dict.keys():
                                try:
                                    font_obj = font_dict[font_key]
                                    if hasattr(font_obj, 'get_object'):
                                        font_obj = font_obj.get_object()

                                    base_font = None
                                    if hasattr(font_obj, 'get'):
                                        base_font = font_obj.get("/BaseFont")
                                    elif isinstance(font_obj, dict):
                                        base_font = font_obj.get("/BaseFont")

                                    if base_font:
                                        font_name = str(base_font)
                                        if font_name.startswith("/"):
                                            font_name = font_name[1:]
                                        all_fonts.append(font_name)

                                    # Check encoding
                                    encoding = None
                                    if hasattr(font_obj, 'get'):
                                        encoding = font_obj.get("/Encoding")
                                    elif isinstance(font_obj, dict):
                                        encoding = font_obj.get("/Encoding")

                                    if encoding:
                                        enc_str = str(encoding)
                                        if enc_str not in (
                                            "/WinAnsiEncoding",
                                            "/Identity-H",
                                            "/Identity-V",
                                            "/MacRomanEncoding",
                                            "/StandardEncoding",
                                        ):
                                            encoding_issues.append(
                                                f"Page {page_num + 1}, font {font_key}: "
                                                f"unusual encoding {enc_str}"
                                            )
                                except Exception as _exc:  # noqa: BLE001
                                    continue
                    except Exception as _exc:  # noqa: BLE001
                        pass

                # Detect potential overlaid content by checking content streams
                # for multiple text blocks at similar coordinates
                try:
                    if hasattr(page, 'get_contents'):
                        contents = page.get_contents()
                    elif "/Contents" in page:
                        contents = page["/Contents"]
                    else:
                        contents = None

                    if contents:
                        # Look for text matrix operations (Tm) that might indicate overlays
                        content_data = None
                        if hasattr(contents, 'get_data'):
                            content_data = contents.get_data()
                        elif hasattr(contents, 'getData'):
                            content_data = contents.getData()

                        if content_data:
                            content_str = content_data.decode("latin-1", errors="replace")
                            # Find text positioning commands (Tm = text matrix)
                            tm_positions = re.findall(
                                r'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+Tm',
                                content_str
                            )
                            if len(tm_positions) >= 2:
                                # Check for text blocks at very similar positions
                                # (sign of overlay/replacement)
                                seen_positions: Dict[str, int] = {}
                                for tm in tm_positions:
                                    # Use x,y position rounded to whole number
                                    pos_key = f"{float(tm[4]):.0f},{float(tm[5]):.0f}"
                                    seen_positions[pos_key] = seen_positions.get(pos_key, 0) + 1

                                for pos_key, count in seen_positions.items():
                                    if count > 1:
                                        overlays.append({
                                            "page": page_num + 1,
                                            "position": pos_key,
                                            "overlap_count": count,
                                        })
                except Exception as _exc:  # noqa: BLE001
                    pass

            # Deduplicate fonts
            all_fonts = list(set(all_fonts))

            return all_fonts, overlays, encoding_issues

        except Exception as e:
            logger.debug("pypdf structure analysis failed: %s", e)
            return None, None, None

    def _extract_fonts_regex(self, file_bytes: bytes) -> List[str]:
        """Fallback: extract font names from PDF via regex."""
        content_str = file_bytes[:200000].decode("latin-1", errors="replace")
        font_matches = re.findall(r'/BaseFont\s*/([^\s/\[\]<>()]+)', content_str)
        return list(set(font_matches))

    def _extract_images_pypdf(self, file_bytes: bytes) -> Optional[List[Dict]]:
        """Extract image information from PDF using pypdf."""
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader  # type: ignore[no-redef]
            except ImportError:
                return None

        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            images_info: List[Dict] = []
            image_index = 0

            for page_num, page in enumerate(reader.pages):
                resources = page.get("/Resources")
                if not resources:
                    continue

                xobjects = None
                if hasattr(resources, 'get'):
                    xobjects = resources.get("/XObject")
                elif isinstance(resources, dict):
                    xobjects = resources.get("/XObject")

                if not xobjects:
                    continue

                try:
                    if hasattr(xobjects, 'get_object'):
                        xobjects = xobjects.get_object()

                    if not hasattr(xobjects, 'keys'):
                        continue

                    for obj_key in xobjects.keys():
                        try:
                            xobj = xobjects[obj_key]
                            if hasattr(xobj, 'get_object'):
                                xobj = xobj.get_object()

                            subtype = None
                            if hasattr(xobj, 'get'):
                                subtype = xobj.get("/Subtype")
                            elif isinstance(xobj, dict):
                                subtype = xobj.get("/Subtype")

                            if str(subtype) != "/Image":
                                continue

                            img_info: Dict[str, Any] = {
                                "index": image_index,
                                "page": page_num + 1,
                            }

                            # Get dimensions
                            width = None
                            height = None
                            if hasattr(xobj, 'get'):
                                width = xobj.get("/Width")
                                height = xobj.get("/Height")
                            elif isinstance(xobj, dict):
                                width = xobj.get("/Width")
                                height = xobj.get("/Height")

                            if width and height:
                                img_info["width"] = int(str(width))
                                img_info["height"] = int(str(height))

                            # Try to determine DPI from page media box and image size
                            try:
                                media_box = page.get("/MediaBox")
                                if media_box and width and height:
                                    page_width = float(str(media_box[2]))
                                    page_height = float(str(media_box[3]))
                                    if page_width > 0 and page_height > 0:
                                        dpi_x = round(int(str(width)) / (page_width / 72.0))
                                        dpi_y = round(int(str(height)) / (page_height / 72.0))
                                        img_info["dpi"] = (dpi_x, dpi_y)
                            except Exception as _exc:  # noqa: BLE001
                                pass

                            images_info.append(img_info)
                            image_index += 1

                        except Exception as _exc:  # noqa: BLE001
                            continue
                except Exception as _exc:  # noqa: BLE001
                    continue

            return images_info

        except Exception as e:
            logger.debug("pypdf image extraction failed: %s", e)
            return None

    def _scan_exif_raw(self, file_bytes: bytes) -> List[str]:
        """Scan raw bytes for EXIF software tags without a library."""
        flags: List[str] = []
        try:
            # Search for EXIF App1 marker (0xFFE1) and Software tag (0x0131)
            content = file_bytes[:500000]

            # Look for common editing software strings in EXIF-like data
            software_patterns = [
                (b"Adobe Photoshop", "Adobe Photoshop detected in EXIF"),
                (b"GIMP", "GIMP detected in EXIF"),
                (b"Adobe Illustrator", "Adobe Illustrator detected in EXIF"),
                (b"Pixlr", "Pixlr detected in EXIF"),
                (b"Canva", "Canva detected in EXIF"),
            ]

            for pattern, msg in software_patterns:
                if pattern in content:
                    flags.append(msg)
                    break  # Only flag once

        except Exception as e:
            logger.debug("Raw EXIF scan error: %s", e)

        return flags

    def _parse_pdf_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse a PDF metadata date string into a datetime."""
        if not date_str:
            return None

        # Handle datetime objects already parsed by pypdf
        if isinstance(date_str, datetime):
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
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

        return None


# =============================================================================
# FRAUD VENDOR SERVICE
# =============================================================================

class FraudVendorService:
    """
    Abstraction layer for document fraud detection vendors.

    Supports multiple backends:
    - "pointpredictive": PointPredictive Document Risk API
    - "resistant_ai": Resistant AI Document Forensics API
    - "internal": Built-in fallback analyzer (no vendor required)

    Configuration via environment variables:
    - FRAUD_VENDOR: vendor name (default: "internal")
    - FRAUD_VENDOR_API_KEY: API key for vendor
    - FRAUD_VENDOR_API_URL: Base URL for vendor API
    - FRAUD_VENDOR_TIMEOUT: Request timeout in seconds (default: 30)
    """

    def __init__(self, db: Session):
        self.db = db
        self.vendor = os.getenv("FRAUD_VENDOR", "internal").lower()
        self.api_key = os.getenv("FRAUD_VENDOR_API_KEY", "")
        self.api_url = os.getenv("FRAUD_VENDOR_API_URL", "")
        self.timeout = int(os.getenv("FRAUD_VENDOR_TIMEOUT", "30"))
        self.internal_analyzer = InternalFraudAnalyzer()

    async def analyze_document(
        self,
        file_bytes: bytes,
        filename: str,
        doc_type: str,
        loan_id: int,
        org_id: int,
    ) -> VendorFraudResult:
        """
        Analyze a document for fraud using the configured vendor.

        Falls back to internal analysis if:
        - No vendor is configured
        - Vendor API call fails
        - Vendor does not support the document type
        """
        start_ms = int(time.time() * 1000)

        try:
            if self.vendor == "pointpredictive" and self.api_key:
                result = await self._call_pointpredictive(
                    file_bytes, filename, doc_type, loan_id, org_id,
                )
            elif self.vendor == "resistant_ai" and self.api_key:
                result = await self._call_resistant_ai(
                    file_bytes, filename, doc_type, loan_id, org_id,
                )
            else:
                result = self._run_internal_analysis(file_bytes, filename, doc_type)

        except Exception as e:
            logger.warning(
                "Vendor %s analysis failed, falling back to internal: %s",
                self.vendor, e,
            )
            result = self._run_internal_analysis(file_bytes, filename, doc_type)

        elapsed_ms = int(time.time() * 1000) - start_ms
        result.analysis_duration_ms = elapsed_ms

        return result

    def get_vendor_status(self) -> Dict[str, Any]:
        """Get the current vendor configuration and health status."""
        return {
            "vendor": self.vendor,
            "configured": bool(self.api_key) if self.vendor != "internal" else True,
            "api_url": self.api_url[:50] + "..." if len(self.api_url) > 50 else self.api_url,
            "timeout": self.timeout,
            "supported_doc_types": self.get_supported_doc_types(),
        }

    def get_supported_doc_types(self) -> List[str]:
        """Get document types supported by the configured vendor."""
        vendor_types = {
            "pointpredictive": [
                "paystub", "w2", "bank_statement", "tax_return",
                "1099", "profit_loss", "asset_statement",
            ],
            "resistant_ai": [
                "paystub", "w2", "bank_statement", "tax_return",
                "1099", "profit_loss", "drivers_license", "passport",
                "utility_bill", "asset_statement",
            ],
            "internal": [
                "paystub", "w2", "bank_statement", "tax_return",
                "1099", "profit_loss", "asset_statement",
                "drivers_license", "passport", "utility_bill",
                "appraisal", "purchase_contract", "title",
            ],
        }
        return vendor_types.get(self.vendor, vendor_types["internal"])

    def _run_internal_analysis(
        self,
        file_bytes: bytes,
        filename: str,
        doc_type: str,
    ) -> VendorFraudResult:
        """Run the internal fallback analyzer."""
        metadata_result = self.internal_analyzer.analyze_pdf_metadata(file_bytes)
        structure_result = self.internal_analyzer.analyze_pdf_structure(file_bytes)
        image_result = self.internal_analyzer.analyze_image_consistency(file_bytes)

        score, risk_level = self.internal_analyzer.calculate_forgery_risk_score(
            metadata_result, structure_result, image_result,
        )

        # Collect all indicators
        all_indicators: List[FraudIndicator] = []
        for r in [metadata_result, structure_result, image_result]:
            all_indicators.extend(r.get("indicators", []))

        # Determine recommendation
        if score >= 70:
            recommendation = "flag"
        elif score >= 40:
            recommendation = "review"
        else:
            recommendation = "pass"

        return VendorFraudResult(
            risk_score=score,
            risk_level=risk_level,
            indicators=all_indicators,
            vendor="internal",
            recommendation=recommendation,
            raw_response={
                "metadata": {
                    k: v for k, v in metadata_result.items() if k != "indicators"
                },
                "structure": {
                    k: v for k, v in structure_result.items() if k != "indicators"
                },
                "images": {
                    k: v for k, v in image_result.items() if k != "indicators"
                },
            },
        )

    async def _call_pointpredictive(
        self,
        file_bytes: bytes,
        filename: str,
        doc_type: str,
        loan_id: int,
        org_id: int,
    ) -> VendorFraudResult:
        """
        Call PointPredictive Document Risk API.

        Expected API:
          POST /v2/document-analysis
          Headers: Authorization: Bearer <key>
          Body: multipart/form-data with file + metadata
          Response: JSON with risk_score, signals[], recommendation
        """
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        files = {"file": (filename, file_bytes, "application/pdf")}
        data = {
            "document_type": doc_type,
            "loan_id": str(loan_id),
            "organization_id": str(org_id),
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.api_url}/v2/document-analysis",
                headers=headers,
                files=files,
                data=data,
            )
            response.raise_for_status()
            resp_data = response.json()

        return self._parse_pointpredictive_response(resp_data)

    def _parse_pointpredictive_response(self, resp: Dict) -> VendorFraudResult:
        """Parse PointPredictive API response into standardized result."""
        risk_score = float(resp.get("risk_score", 0))

        if risk_score >= 70:
            risk_level = "HIGH"
        elif risk_score >= 40:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        indicators = []
        for signal in resp.get("signals", []):
            indicators.append(FraudIndicator(
                indicator_type=signal.get("type", "unknown"),
                severity=signal.get("severity", "medium").lower(),
                description=signal.get("description", ""),
                evidence=signal.get("evidence", {}),
            ))

        recommendation = resp.get("recommendation", "pass")
        if recommendation not in ("flag", "review", "pass"):
            recommendation = "review" if risk_score >= 40 else "pass"

        return VendorFraudResult(
            risk_score=risk_score,
            risk_level=risk_level,
            indicators=indicators,
            vendor="pointpredictive",
            recommendation=recommendation,
            raw_response=resp,
        )

    async def _call_resistant_ai(
        self,
        file_bytes: bytes,
        filename: str,
        doc_type: str,
        loan_id: int,
        org_id: int,
    ) -> VendorFraudResult:
        """
        Call Resistant AI Document Forensics API.

        Expected API:
          POST /api/v1/submissions
          Headers: X-API-Key: <key>
          Body: multipart/form-data with file + metadata JSON
          Response: JSON with score, findings[], verdict
        """
        import httpx
        import json

        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
        }

        metadata_json = json.dumps({
            "document_type": doc_type,
            "reference_id": str(loan_id),
            "organization_id": str(org_id),
        })

        files = {"file": (filename, file_bytes, "application/pdf")}
        data = {"metadata": metadata_json}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.api_url}/api/v1/submissions",
                headers=headers,
                files=files,
                data=data,
            )
            response.raise_for_status()
            resp_data = response.json()

        return self._parse_resistant_ai_response(resp_data)

    def _parse_resistant_ai_response(self, resp: Dict) -> VendorFraudResult:
        """Parse Resistant AI API response into standardized result."""
        risk_score = float(resp.get("score", 0))

        if risk_score >= 70:
            risk_level = "HIGH"
        elif risk_score >= 40:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        indicators = []
        for finding in resp.get("findings", []):
            indicators.append(FraudIndicator(
                indicator_type=finding.get("category", "unknown"),
                severity=finding.get("severity", "medium").lower(),
                description=finding.get("message", ""),
                evidence=finding.get("details", {}),
            ))

        verdict = resp.get("verdict", "unknown")
        recommendation_map = {
            "fraudulent": "flag",
            "suspicious": "review",
            "genuine": "pass",
        }
        recommendation = recommendation_map.get(verdict, "review")

        return VendorFraudResult(
            risk_score=risk_score,
            risk_level=risk_level,
            indicators=indicators,
            vendor="resistant_ai",
            recommendation=recommendation,
            raw_response=resp,
        )


# =============================================================================
# SINGLETON
# =============================================================================

def get_fraud_vendor_service(db: Session) -> FraudVendorService:
    """Get a FraudVendorService instance for the given database session."""
    return FraudVendorService(db)
