"""
PDF Generation and Manipulation Service for Smart Docs.

Handles all PDF operations:
- Generation of signing completion certificates
- Merging multiple documents into single PDFs
- Watermarking (DRAFT, COPY, CONFIDENTIAL)
- Signature overlay onto documents
- Cover page and needs list PDF generation
- Income calculation report generation
- Page numbering and text extraction

Uses ReportLab for PDF generation and pypdf for manipulation.
Both are optional — the service degrades gracefully if either is missing.
"""

from __future__ import annotations

import io
import logging
import math
import os
import hashlib
import struct
import zlib
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple

from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency imports
# ---------------------------------------------------------------------------

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image as RLImage,
    )

    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    logger.info("reportlab not installed — PDF generation will use fallback renderer")

try:
    from pypdf import PdfReader, PdfWriter, PdfMerger, Transformation
    HAS_PYPDF = True
except ImportError:
    try:
        # Legacy package name
        from PyPDF2 import PdfReader, PdfWriter, PdfMerger  # type: ignore[no-redef]
        from PyPDF2 import Transformation  # type: ignore[no-redef]
        HAS_PYPDF = True
    except ImportError:
        HAS_PYPDF = False
        logger.info("pypdf/PyPDF2 not installed — PDF manipulation will be limited")

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PDFGenerationResult:
    """Result of PDF generation."""

    content: bytes
    page_count: int
    file_size: int
    sha256_hash: str
    success: bool = True
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PAGE_WIDTH, _PAGE_HEIGHT = 612, 792  # US Letter in points (8.5 x 11 in)
_MARGIN = 72  # 1 inch


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PDFGenerationService:
    """
    PDF generation and manipulation service for Smart Docs.

    Capabilities:
    - Generate signing completion certificates
    - Merge multiple documents into single PDF
    - Add watermarks (DRAFT, COPY, CONFIDENTIAL)
    - Overlay signatures onto documents
    - Generate document cover pages
    - Create needs list PDFs
    - Generate income calculation report PDFs
    - Add page numbers
    - Flatten form fields
    """

    def __init__(self):
        self._company_name = os.getenv("COMPANY_NAME", "Perennia AI")
        self._company_logo_path = os.getenv("COMPANY_LOGO_PATH")

    # ------------------------------------------------------------------
    # 1. Completion Certificate
    # ------------------------------------------------------------------

    def generate_completion_certificate(
        self,
        envelope_uuid: str,
        title: str,
        signers: List[Dict],
        document_hash: str,
        completed_at: datetime,
    ) -> PDFGenerationResult:
        """Generate a professional signing completion certificate PDF.

        Args:
            envelope_uuid: Unique identifier for the signing envelope.
            title: Document title.
            signers: List of dicts with keys: name, email, signed_at, ip_address,
                     signature_hash.
            document_hash: SHA-256 hash of the signed document for verification.
            completed_at: Datetime when all signatures were collected.

        Returns:
            PDFGenerationResult with the certificate PDF bytes.
        """
        try:
            if HAS_REPORTLAB:
                content = self._generate_certificate_reportlab(
                    envelope_uuid, title, signers, document_hash, completed_at,
                )
            else:
                content = self._generate_certificate_fallback(
                    envelope_uuid, title, signers, document_hash, completed_at,
                )

            page_count = self.get_page_count(content) if HAS_PYPDF else 1
            return PDFGenerationResult(
                content=content,
                page_count=page_count,
                file_size=len(content),
                sha256_hash=self._hash_content(content),
            )
        except Exception as e:
            logger.exception("Failed to generate completion certificate")
            return PDFGenerationResult(
                content=b"",
                page_count=0,
                file_size=0,
                sha256_hash="",
                success=False,
                error=str(e),
            )

    def _generate_certificate_reportlab(
        self,
        envelope_uuid: str,
        title: str,
        signers: List[Dict],
        document_hash: str,
        completed_at: datetime,
    ) -> bytes:
        """Generate certificate using ReportLab."""
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=letter)
        width, height = letter

        # --- Header ---
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(width / 2, height - 60, "Signing Completion Certificate")

        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#555555"))
        c.drawCentredString(width / 2, height - 80, self._company_name)

        # Divider
        c.setStrokeColor(colors.HexColor("#2563EB"))
        c.setLineWidth(2)
        c.line(_MARGIN, height - 95, width - _MARGIN, height - 95)

        # --- Envelope details ---
        y = height - 130
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(_MARGIN, y, "Document Details")
        y -= 20

        details = [
            ("Envelope ID:", envelope_uuid),
            ("Document Title:", title),
            ("Completed At:", completed_at.strftime("%B %d, %Y at %I:%M %p %Z")),
            ("Document Hash (SHA-256):", ""),
        ]

        c.setFont("Helvetica", 10)
        for label, value in details:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(_MARGIN, y, label)
            c.setFont("Helvetica", 10)
            c.drawString(_MARGIN + 170, y, value)
            y -= 16

        # Hash on its own line (it's long)
        c.setFont("Courier", 8)
        c.drawString(_MARGIN + 10, y, document_hash)
        y -= 30

        # --- Signers ---
        c.setFont("Helvetica-Bold", 12)
        c.drawString(_MARGIN, y, "Signers")
        y -= 6

        c.setStrokeColor(colors.HexColor("#E5E7EB"))
        c.setLineWidth(0.5)
        c.line(_MARGIN, y, width - _MARGIN, y)
        y -= 20

        for idx, signer in enumerate(signers):
            if y < 140:
                c.showPage()
                y = height - 60

            signer_name = signer.get("name", "Unknown")
            signer_email = signer.get("email", "")
            signed_at_str = signer.get("signed_at", "")
            ip_address = signer.get("ip_address", "N/A")
            sig_hash = signer.get("signature_hash", "N/A")

            c.setFont("Helvetica-Bold", 11)
            c.drawString(_MARGIN, y, f"Signer {idx + 1}: {signer_name}")
            y -= 16

            c.setFont("Helvetica", 9)
            signer_lines = [
                f"Email: {signer_email}",
                f"Signed At: {signed_at_str}",
                f"IP Address: {ip_address}",
                f"Signature Hash: {sig_hash}",
            ]
            for line in signer_lines:
                c.drawString(_MARGIN + 20, y, line)
                y -= 14
            y -= 10

        # --- Footer ---
        y -= 10
        c.setStrokeColor(colors.HexColor("#2563EB"))
        c.setLineWidth(1)
        c.line(_MARGIN, y, width - _MARGIN, y)
        y -= 20

        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawCentredString(
            width / 2, y,
            "This certificate confirms that all parties completed signing via "
            f"{self._company_name}.",
        )
        y -= 12
        c.drawCentredString(
            width / 2, y,
            "Document integrity can be verified using the SHA-256 hash above.",
        )

        c.save()
        return buf.getvalue()

    def _generate_certificate_fallback(
        self,
        envelope_uuid: str,
        title: str,
        signers: List[Dict],
        document_hash: str,
        completed_at: datetime,
    ) -> bytes:
        """Generate certificate using minimal PDF fallback."""
        lines = [
            "SIGNING COMPLETION CERTIFICATE",
            f"Company: {self._company_name}",
            "",
            "--- Document Details ---",
            f"Envelope ID: {envelope_uuid}",
            f"Document Title: {title}",
            f"Completed At: {completed_at.strftime('%B %d, %Y at %I:%M %p %Z')}",
            f"Document Hash (SHA-256): {document_hash}",
            "",
            "--- Signers ---",
        ]
        for idx, signer in enumerate(signers):
            lines.append(f"  Signer {idx + 1}: {signer.get('name', 'Unknown')}")
            lines.append(f"    Email: {signer.get('email', '')}")
            lines.append(f"    Signed At: {signer.get('signed_at', '')}")
            lines.append(f"    IP Address: {signer.get('ip_address', 'N/A')}")
            lines.append(f"    Signature Hash: {signer.get('signature_hash', 'N/A')}")
            lines.append("")

        lines.append("---")
        lines.append(
            "This certificate confirms that all parties completed signing "
            f"via {self._company_name}."
        )
        return self._create_simple_pdf("\n".join(lines), title="Signing Completion Certificate")

    # ------------------------------------------------------------------
    # 2. Merge Documents
    # ------------------------------------------------------------------

    def merge_documents(
        self,
        documents: List[Tuple[bytes, str]],
        output_title: str = "Merged Document",
    ) -> PDFGenerationResult:
        """Merge multiple PDF/image files into a single PDF.

        Args:
            documents: List of (content_bytes, filename) tuples.
            output_title: Title metadata for the merged PDF.

        Returns:
            PDFGenerationResult with the merged PDF bytes.
        """
        if not documents:
            return PDFGenerationResult(
                content=b"",
                page_count=0,
                file_size=0,
                sha256_hash="",
                success=False,
                error="No documents provided",
            )

        if not HAS_PYPDF:
            return PDFGenerationResult(
                content=b"",
                page_count=0,
                file_size=0,
                sha256_hash="",
                success=False,
                error="pypdf is required for merging documents",
            )

        try:
            merger = PdfMerger()
            total_pages = 0

            for content, filename in documents:
                lower_name = filename.lower()
                if lower_name.endswith((".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp")):
                    content = self.image_to_pdf(content, filename)
                    if not content:
                        logger.warning("Skipping non-convertible image: %s", filename)
                        continue

                try:
                    reader = PdfReader(io.BytesIO(content))
                    total_pages += len(reader.pages)
                    merger.append(io.BytesIO(content))
                except Exception as e:
                    logger.warning("Skipping unreadable document %s: %s", filename, e)
                    continue

            buf = io.BytesIO()
            merger.write(buf)
            merger.close()
            merged_content = buf.getvalue()

            # Add page numbers to the merged result
            numbered = self._add_page_numbers_internal(merged_content)
            if numbered is not None:
                merged_content = numbered

            return PDFGenerationResult(
                content=merged_content,
                page_count=total_pages,
                file_size=len(merged_content),
                sha256_hash=self._hash_content(merged_content),
            )
        except Exception as e:
            logger.exception("Failed to merge documents")
            return PDFGenerationResult(
                content=b"",
                page_count=0,
                file_size=0,
                sha256_hash="",
                success=False,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # 3. Add Watermark
    # ------------------------------------------------------------------

    def add_watermark(
        self,
        pdf_content: bytes,
        watermark_text: str,
        opacity: float = 0.15,
    ) -> PDFGenerationResult:
        """Add a diagonal watermark to every page of a PDF.

        Args:
            pdf_content: Source PDF bytes.
            watermark_text: Text to overlay (e.g., "DRAFT", "COPY", "CONFIDENTIAL").
            opacity: Transparency (0.0 fully transparent, 1.0 fully opaque).

        Returns:
            PDFGenerationResult with the watermarked PDF.
        """
        if not HAS_REPORTLAB or not HAS_PYPDF:
            return PDFGenerationResult(
                content=pdf_content,
                page_count=self.get_page_count(pdf_content),
                file_size=len(pdf_content),
                sha256_hash=self._hash_content(pdf_content),
                success=False,
                error="reportlab and pypdf are both required for watermarking",
            )

        try:
            reader = PdfReader(io.BytesIO(pdf_content))
            writer = PdfWriter()

            # Build watermark page
            watermark_pdf = self._create_watermark_page(
                watermark_text, opacity,
                float(reader.pages[0].mediabox.width),
                float(reader.pages[0].mediabox.height),
            )
            watermark_reader = PdfReader(io.BytesIO(watermark_pdf))
            watermark_page = watermark_reader.pages[0]

            for page in reader.pages:
                page.merge_page(watermark_page)
                writer.add_page(page)

            buf = io.BytesIO()
            writer.write(buf)
            result_content = buf.getvalue()

            return PDFGenerationResult(
                content=result_content,
                page_count=len(reader.pages),
                file_size=len(result_content),
                sha256_hash=self._hash_content(result_content),
            )
        except Exception as e:
            logger.exception("Failed to add watermark")
            return PDFGenerationResult(
                content=pdf_content,
                page_count=0,
                file_size=len(pdf_content),
                sha256_hash=self._hash_content(pdf_content),
                success=False,
                error=str(e),
            )

    def _create_watermark_page(
        self,
        text: str,
        opacity: float,
        page_width: float,
        page_height: float,
    ) -> bytes:
        """Create a single-page PDF with diagonal watermark text."""
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(page_width, page_height))

        c.saveState()
        c.setFillColor(colors.Color(0.5, 0.5, 0.5, alpha=opacity))
        c.setFont("Helvetica-Bold", 72)

        # Rotate 45 degrees and center
        c.translate(page_width / 2, page_height / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, text)

        c.restoreState()
        c.save()
        return buf.getvalue()

    # ------------------------------------------------------------------
    # 4. Overlay Signature
    # ------------------------------------------------------------------

    def overlay_signature(
        self,
        pdf_content: bytes,
        signature_image: bytes,
        page_number: int,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> PDFGenerationResult:
        """Place a signature image on a specific page at given coordinates.

        Args:
            pdf_content: Source PDF bytes.
            signature_image: PNG/JPEG signature image bytes.
            page_number: 1-based page number.
            x: X coordinate (points from left).
            y: Y coordinate (points from bottom).
            width: Desired width in points.
            height: Desired height in points.

        Returns:
            PDFGenerationResult with signature overlaid.
        """
        return self.overlay_all_fields(pdf_content, [{
            "page": page_number,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "type": "SIGNATURE",
            "image_bytes": signature_image,
        }])

    # ------------------------------------------------------------------
    # 5. Overlay All Fields
    # ------------------------------------------------------------------

    def overlay_all_fields(
        self,
        pdf_content: bytes,
        fields: List[Dict],
    ) -> PDFGenerationResult:
        """Overlay multiple fields (signatures, initials, dates, text) on a PDF.

        Args:
            pdf_content: Source PDF bytes.
            fields: List of field dicts. Each contains:
                - page (int, 1-based)
                - x, y, width, height (float, points)
                - type (str): SIGNATURE, INITIAL, DATE_SIGNED, TEXT, CHECKBOX
                - value (str, optional): text value for TEXT/DATE_SIGNED
                - image_bytes (bytes, optional): for SIGNATURE/INITIAL

        Returns:
            PDFGenerationResult with all fields applied.
        """
        if not HAS_REPORTLAB or not HAS_PYPDF:
            return PDFGenerationResult(
                content=pdf_content,
                page_count=self.get_page_count(pdf_content),
                file_size=len(pdf_content),
                sha256_hash=self._hash_content(pdf_content),
                success=False,
                error="reportlab and pypdf are both required for field overlay",
            )

        try:
            reader = PdfReader(io.BytesIO(pdf_content))
            writer = PdfWriter()
            num_pages = len(reader.pages)

            # Group fields by page
            fields_by_page: Dict[int, List[Dict]] = {}
            for field in fields:
                pg = field.get("page", 1)
                fields_by_page.setdefault(pg, []).append(field)

            for page_idx in range(num_pages):
                page = reader.pages[page_idx]
                page_num = page_idx + 1  # 1-based

                page_fields = fields_by_page.get(page_num, [])
                if page_fields:
                    page_w = float(page.mediabox.width)
                    page_h = float(page.mediabox.height)
                    overlay_pdf = self._render_fields_overlay(page_fields, page_w, page_h)
                    overlay_reader = PdfReader(io.BytesIO(overlay_pdf))
                    page.merge_page(overlay_reader.pages[0])

                writer.add_page(page)

            buf = io.BytesIO()
            writer.write(buf)
            result_content = buf.getvalue()

            return PDFGenerationResult(
                content=result_content,
                page_count=num_pages,
                file_size=len(result_content),
                sha256_hash=self._hash_content(result_content),
            )
        except Exception as e:
            logger.exception("Failed to overlay fields")
            return PDFGenerationResult(
                content=pdf_content,
                page_count=0,
                file_size=len(pdf_content),
                sha256_hash=self._hash_content(pdf_content),
                success=False,
                error=str(e),
            )

    def _render_fields_overlay(
        self,
        fields: List[Dict],
        page_width: float,
        page_height: float,
    ) -> bytes:
        """Render an overlay PDF page containing the given fields."""
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(page_width, page_height))

        for field in fields:
            field_type = (field.get("type") or "TEXT").upper()
            x = float(field.get("x", 0))
            y = float(field.get("y", 0))
            w = float(field.get("width", 100))
            h = float(field.get("height", 30))
            value = field.get("value", "")
            image_bytes = field.get("image_bytes")

            if field_type in ("SIGNATURE", "INITIAL") and image_bytes:
                try:
                    img_buf = io.BytesIO(image_bytes)
                    c.drawImage(
                        RLImage(img_buf, w, h)._img
                        if False  # placeholder — use ImageReader
                        else _image_reader_path(img_buf),
                        x, y, width=w, height=h,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                except Exception:
                    # Fallback: try with reportlab ImageReader
                    try:
                        from reportlab.lib.utils import ImageReader
                        img_reader = ImageReader(io.BytesIO(image_bytes))
                        c.drawImage(
                            img_reader, x, y,
                            width=w, height=h,
                            preserveAspectRatio=True,
                            mask="auto",
                        )
                    except Exception as img_err:
                        logger.warning("Could not overlay image: %s", img_err)

            elif field_type == "DATE_SIGNED":
                date_text = value or datetime.now(timezone.utc).strftime("%m/%d/%Y")
                c.setFont("Helvetica", min(h * 0.6, 12))
                c.setFillColor(colors.black)
                c.drawString(x + 2, y + h * 0.25, date_text)

            elif field_type == "TEXT":
                font_size = min(h * 0.6, 12)
                c.setFont("Helvetica", font_size)
                c.setFillColor(colors.black)
                c.drawString(x + 2, y + h * 0.25, str(value))

            elif field_type == "CHECKBOX":
                # Draw a checkmark
                c.setStrokeColor(colors.black)
                c.setLineWidth(2)
                # Checkmark stroke
                cx, cy = x + w * 0.2, y + h * 0.4
                c.line(cx, cy, x + w * 0.45, y + h * 0.15)
                c.line(x + w * 0.45, y + h * 0.15, x + w * 0.8, y + h * 0.8)

        c.save()
        return buf.getvalue()

    # ------------------------------------------------------------------
    # 6. Cover Page
    # ------------------------------------------------------------------

    def generate_cover_page(
        self,
        title: str,
        loan_info: Dict,
        document_list: List[Dict],
    ) -> PDFGenerationResult:
        """Generate a cover page for document packages.

        Args:
            title: Cover page title.
            loan_info: Dict with keys like borrower_name, loan_number, property_address.
            document_list: List of dicts with name, page_count keys.

        Returns:
            PDFGenerationResult with the cover page PDF.
        """
        try:
            if HAS_REPORTLAB:
                content = self._generate_cover_page_reportlab(title, loan_info, document_list)
            else:
                content = self._generate_cover_page_fallback(title, loan_info, document_list)

            return PDFGenerationResult(
                content=content,
                page_count=1,
                file_size=len(content),
                sha256_hash=self._hash_content(content),
            )
        except Exception as e:
            logger.exception("Failed to generate cover page")
            return PDFGenerationResult(
                content=b"",
                page_count=0,
                file_size=0,
                sha256_hash="",
                success=False,
                error=str(e),
            )

    def _generate_cover_page_reportlab(
        self,
        title: str,
        loan_info: Dict,
        document_list: List[Dict],
    ) -> bytes:
        """Generate cover page with ReportLab."""
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=letter)
        width, height = letter

        # Header bar
        c.setFillColor(colors.HexColor("#1E3A5F"))
        c.rect(0, height - 100, width, 100, fill=True, stroke=False)

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(width / 2, height - 55, title)

        c.setFont("Helvetica", 12)
        c.drawCentredString(width / 2, height - 80, self._company_name)

        # Loan details
        y = height - 140
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(_MARGIN, y, "Loan Information")
        y -= 25

        info_fields = [
            ("Borrower:", loan_info.get("borrower_name", "N/A")),
            ("Loan Number:", loan_info.get("loan_number", "N/A")),
            ("Property:", loan_info.get("property_address", "N/A")),
            ("Date:", datetime.now(timezone.utc).strftime("%B %d, %Y")),
        ]

        c.setFont("Helvetica", 11)
        for label, value in info_fields:
            c.setFont("Helvetica-Bold", 11)
            c.drawString(_MARGIN, y, label)
            c.setFont("Helvetica", 11)
            c.drawString(_MARGIN + 120, y, str(value))
            y -= 18

        # Document index
        y -= 15
        c.setFont("Helvetica-Bold", 14)
        c.drawString(_MARGIN, y, "Included Documents")
        y -= 10

        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.setLineWidth(0.5)
        c.line(_MARGIN, y, width - _MARGIN, y)
        y -= 20

        # Table header
        c.setFont("Helvetica-Bold", 10)
        c.drawString(_MARGIN, y, "#")
        c.drawString(_MARGIN + 30, y, "Document")
        c.drawString(width - _MARGIN - 60, y, "Pages")
        y -= 5
        c.line(_MARGIN, y, width - _MARGIN, y)
        y -= 15

        c.setFont("Helvetica", 10)
        running_page = 2  # Cover page is page 1
        for idx, doc in enumerate(document_list):
            if y < 80:
                break
            doc_name = doc.get("name", "Untitled")
            doc_pages = doc.get("page_count", 1)
            c.drawString(_MARGIN, y, str(idx + 1))
            c.drawString(_MARGIN + 30, y, doc_name[:70])
            c.drawString(width - _MARGIN - 60, y, f"p. {running_page}")
            running_page += doc_pages
            y -= 16

        # Footer
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(colors.HexColor("#999999"))
        c.drawCentredString(
            width / 2, 40,
            f"Generated by {self._company_name} on "
            f"{datetime.now(timezone.utc).strftime('%m/%d/%Y %I:%M %p UTC')}",
        )

        c.save()
        return buf.getvalue()

    def _generate_cover_page_fallback(
        self,
        title: str,
        loan_info: Dict,
        document_list: List[Dict],
    ) -> bytes:
        """Generate cover page with minimal PDF fallback."""
        lines = [
            title.upper(),
            self._company_name,
            "",
            "--- Loan Information ---",
            f"Borrower: {loan_info.get('borrower_name', 'N/A')}",
            f"Loan Number: {loan_info.get('loan_number', 'N/A')}",
            f"Property: {loan_info.get('property_address', 'N/A')}",
            f"Date: {datetime.now(timezone.utc).strftime('%B %d, %Y')}",
            "",
            "--- Included Documents ---",
        ]
        for idx, doc in enumerate(document_list):
            lines.append(f"  {idx + 1}. {doc.get('name', 'Untitled')}")
        return self._create_simple_pdf("\n".join(lines), title=title)

    # ------------------------------------------------------------------
    # 7. Needs List PDF
    # ------------------------------------------------------------------

    def generate_needs_list_pdf(
        self,
        loan_info: Dict,
        requirements: List[Dict],
        include_instructions: bool = True,
    ) -> PDFGenerationResult:
        """Generate a printable needs list document.

        Args:
            loan_info: Dict with borrower_name, loan_number, loan_program.
            requirements: List of dicts with keys: category, name, description,
                          required (bool), due_date, status.
            include_instructions: Whether to include upload instructions.

        Returns:
            PDFGenerationResult with the needs list PDF.
        """
        try:
            if HAS_REPORTLAB:
                content = self._generate_needs_list_reportlab(
                    loan_info, requirements, include_instructions,
                )
            else:
                content = self._generate_needs_list_fallback(
                    loan_info, requirements, include_instructions,
                )

            page_count = self.get_page_count(content) if HAS_PYPDF else 1
            return PDFGenerationResult(
                content=content,
                page_count=page_count,
                file_size=len(content),
                sha256_hash=self._hash_content(content),
            )
        except Exception as e:
            logger.exception("Failed to generate needs list PDF")
            return PDFGenerationResult(
                content=b"",
                page_count=0,
                file_size=0,
                sha256_hash="",
                success=False,
                error=str(e),
            )

    def _generate_needs_list_reportlab(
        self,
        loan_info: Dict,
        requirements: List[Dict],
        include_instructions: bool,
    ) -> bytes:
        """Generate needs list using ReportLab."""
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=letter)
        width, height = letter

        # Title
        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(width / 2, height - 50, "Document Needs List")
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#555555"))
        c.drawCentredString(width / 2, height - 68, self._company_name)

        c.setStrokeColor(colors.HexColor("#2563EB"))
        c.setLineWidth(1.5)
        c.line(_MARGIN, height - 78, width - _MARGIN, height - 78)

        # Loan info
        y = height - 105
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 10)
        info_items = [
            f"Borrower: {loan_info.get('borrower_name', '')}",
            f"Loan #: {loan_info.get('loan_number', '')}",
            f"Program: {loan_info.get('loan_program', '')}",
            f"Date: {datetime.now(timezone.utc).strftime('%m/%d/%Y')}",
        ]
        for item in info_items:
            c.drawString(_MARGIN, y, item)
            y -= 15

        if include_instructions:
            y -= 10
            c.setFont("Helvetica-Bold", 10)
            c.drawString(_MARGIN, y, "Instructions:")
            y -= 14
            c.setFont("Helvetica", 9)
            instructions = [
                "1. Please provide all documents marked as REQUIRED.",
                "2. Upload documents through your secure portal or email them to your loan officer.",
                "3. Ensure documents are legible — no screenshots or cropped images.",
                "4. Documents with due dates must be received by the indicated date.",
            ]
            for inst in instructions:
                c.drawString(_MARGIN + 10, y, inst)
                y -= 13
            y -= 5

        # Group requirements by category
        CATEGORY_ORDER = ["Identity", "Income", "Assets", "Property", "Credit", "Special"]
        by_category: Dict[str, List[Dict]] = {}
        for req in requirements:
            cat = req.get("category", "Special")
            by_category.setdefault(cat, []).append(req)

        for category in CATEGORY_ORDER:
            cat_reqs = by_category.pop(category, [])
            if not cat_reqs:
                continue

            if y < 120:
                c.showPage()
                y = height - 60

            # Category header
            c.setFillColor(colors.HexColor("#F1F5F9"))
            c.rect(_MARGIN, y - 4, width - 2 * _MARGIN, 18, fill=True, stroke=False)
            c.setFillColor(colors.HexColor("#1E3A5F"))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(_MARGIN + 5, y, category)
            y -= 22

            # Items
            for req in cat_reqs:
                if y < 80:
                    c.showPage()
                    y = height - 60

                is_required = req.get("required", False)
                name = req.get("name", "")
                description = req.get("description", "")
                due_date = req.get("due_date", "")
                status = req.get("status", "pending")

                # Checkbox
                c.setStrokeColor(colors.black)
                c.setLineWidth(0.75)
                c.rect(_MARGIN + 5, y - 2, 10, 10, fill=False)

                if status == "received":
                    # Draw checkmark inside
                    c.setLineWidth(1.5)
                    c.line(_MARGIN + 7, y + 2, _MARGIN + 10, y - 1)
                    c.line(_MARGIN + 10, y - 1, _MARGIN + 14, y + 7)

                # Document name
                c.setFillColor(colors.black)
                c.setFont("Helvetica-Bold" if is_required else "Helvetica", 10)
                label = name
                if is_required:
                    label += " *"
                c.drawString(_MARGIN + 22, y, label)

                # Due date on the right
                if due_date:
                    c.setFont("Helvetica", 8)
                    c.setFillColor(colors.HexColor("#DC2626"))
                    c.drawRightString(width - _MARGIN, y, f"Due: {due_date}")
                    c.setFillColor(colors.black)

                # Description
                if description:
                    y -= 13
                    c.setFont("Helvetica", 8)
                    c.setFillColor(colors.HexColor("#666666"))
                    # Truncate long descriptions
                    c.drawString(_MARGIN + 22, y, description[:90])
                    c.setFillColor(colors.black)

                y -= 18

        # Remaining categories not in the predefined order
        for category, cat_reqs in by_category.items():
            if y < 120:
                c.showPage()
                y = height - 60
            c.setFont("Helvetica-Bold", 11)
            c.drawString(_MARGIN + 5, y, category)
            y -= 20
            for req in cat_reqs:
                if y < 80:
                    c.showPage()
                    y = height - 60
                c.setFont("Helvetica", 10)
                c.drawString(_MARGIN + 22, y, req.get("name", ""))
                y -= 16

        # Footer
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(colors.HexColor("#999999"))
        c.drawCentredString(width / 2, 30, "* Required documents")

        c.save()
        return buf.getvalue()

    def _generate_needs_list_fallback(
        self,
        loan_info: Dict,
        requirements: List[Dict],
        include_instructions: bool,
    ) -> bytes:
        """Generate needs list with minimal PDF fallback."""
        lines = [
            "DOCUMENT NEEDS LIST",
            self._company_name,
            "",
            f"Borrower: {loan_info.get('borrower_name', '')}",
            f"Loan #: {loan_info.get('loan_number', '')}",
            f"Program: {loan_info.get('loan_program', '')}",
            "",
        ]
        if include_instructions:
            lines += [
                "Instructions:",
                "  1. Provide all documents marked REQUIRED.",
                "  2. Upload via secure portal or email.",
                "  3. Ensure documents are legible.",
                "",
            ]
        current_cat = None
        for req in requirements:
            cat = req.get("category", "Special")
            if cat != current_cat:
                lines.append(f"\n--- {cat} ---")
                current_cat = cat
            marker = "[*]" if req.get("required") else "[ ]"
            lines.append(f"  {marker} {req.get('name', '')}")
            if req.get("description"):
                lines.append(f"      {req['description']}")

        return self._create_simple_pdf("\n".join(lines), title="Document Needs List")

    # ------------------------------------------------------------------
    # 8. Income Report PDF
    # ------------------------------------------------------------------

    def generate_income_report_pdf(
        self,
        calculation: Dict,
        sources: List[Dict],
    ) -> PDFGenerationResult:
        """Generate an income calculation report PDF.

        Args:
            calculation: Dict with total_monthly_income, dti_front, dti_back,
                         qualifying_income, recommendation.
            sources: List of dicts with name, type, monthly_amount, annual_amount,
                     verified (bool), notes.

        Returns:
            PDFGenerationResult with the report PDF.
        """
        try:
            if HAS_REPORTLAB:
                content = self._generate_income_report_reportlab(calculation, sources)
            else:
                content = self._generate_income_report_fallback(calculation, sources)

            page_count = self.get_page_count(content) if HAS_PYPDF else 1
            return PDFGenerationResult(
                content=content,
                page_count=page_count,
                file_size=len(content),
                sha256_hash=self._hash_content(content),
            )
        except Exception as e:
            logger.exception("Failed to generate income report PDF")
            return PDFGenerationResult(
                content=b"",
                page_count=0,
                file_size=0,
                sha256_hash="",
                success=False,
                error=str(e),
            )

    def _generate_income_report_reportlab(
        self,
        calculation: Dict,
        sources: List[Dict],
    ) -> bytes:
        """Generate income report using ReportLab."""
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=letter)
        width, height = letter

        # Title
        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(width / 2, height - 50, "Income Calculation Report")
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#555555"))
        c.drawCentredString(
            width / 2, height - 68,
            f"{self._company_name} | Generated {datetime.now(timezone.utc).strftime('%m/%d/%Y')}",
        )

        c.setStrokeColor(colors.HexColor("#2563EB"))
        c.setLineWidth(1.5)
        c.line(_MARGIN, height - 78, width - _MARGIN, height - 78)

        # Summary box
        y = height - 110
        c.setFillColor(colors.HexColor("#F8FAFC"))
        c.rect(_MARGIN, y - 70, width - 2 * _MARGIN, 80, fill=True, stroke=False)
        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.rect(_MARGIN, y - 70, width - 2 * _MARGIN, 80, fill=False, stroke=True)

        c.setFillColor(colors.HexColor("#1E3A5F"))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(_MARGIN + 10, y, "Summary")

        c.setFont("Helvetica", 10)
        c.setFillColor(colors.black)
        total_monthly = calculation.get("total_monthly_income", 0)
        qualifying = calculation.get("qualifying_income", total_monthly)
        dti_front = calculation.get("dti_front", 0)
        dti_back = calculation.get("dti_back", 0)

        summary_items = [
            (f"Total Monthly Income: ${total_monthly:,.2f}", _MARGIN + 15),
            (f"Qualifying Income: ${qualifying:,.2f}", _MARGIN + 15),
            (f"Front-End DTI: {dti_front:.1f}%", width / 2 + 10),
            (f"Back-End DTI: {dti_back:.1f}%", width / 2 + 10),
        ]

        row_y = y - 18
        for idx, (text, x_pos) in enumerate(summary_items):
            if idx == 2:
                row_y = y - 18  # Reset y for right column
            c.drawString(x_pos, row_y, text)
            row_y -= 16

        # Income Sources Table
        y = y - 95
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(_MARGIN, y, "Income Sources")
        y -= 20

        # Table header
        col_positions = [_MARGIN, _MARGIN + 140, _MARGIN + 230, _MARGIN + 340, _MARGIN + 420]
        headers = ["Source", "Type", "Monthly", "Annual", "Verified"]

        c.setFillColor(colors.HexColor("#F1F5F9"))
        c.rect(_MARGIN, y - 4, width - 2 * _MARGIN, 18, fill=True, stroke=False)
        c.setFillColor(colors.HexColor("#1E3A5F"))
        c.setFont("Helvetica-Bold", 9)
        for header, x_pos in zip(headers, col_positions):
            c.drawString(x_pos + 3, y, header)
        y -= 20

        # Table rows
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.black)
        for idx, source in enumerate(sources):
            if y < 100:
                c.showPage()
                y = height - 60

            # Alternating row background
            if idx % 2 == 1:
                c.setFillColor(colors.HexColor("#FAFAFA"))
                c.rect(_MARGIN, y - 4, width - 2 * _MARGIN, 16, fill=True, stroke=False)

            c.setFillColor(colors.black)
            name = source.get("name", "")[:20]
            stype = source.get("type", "")[:15]
            monthly = source.get("monthly_amount", 0)
            annual = source.get("annual_amount", 0)
            verified = source.get("verified", False)

            c.drawString(col_positions[0] + 3, y, name)
            c.drawString(col_positions[1] + 3, y, stype)
            c.drawString(col_positions[2] + 3, y, f"${monthly:,.2f}")
            c.drawString(col_positions[3] + 3, y, f"${annual:,.2f}")

            if verified:
                c.setFillColor(colors.HexColor("#16A34A"))
                c.drawString(col_positions[4] + 3, y, "Yes")
            else:
                c.setFillColor(colors.HexColor("#DC2626"))
                c.drawString(col_positions[4] + 3, y, "No")

            c.setFillColor(colors.black)
            y -= 16

        # Recommendation
        recommendation = calculation.get("recommendation", "")
        if recommendation:
            y -= 20
            c.setFont("Helvetica-Bold", 12)
            c.drawString(_MARGIN, y, "AI Recommendation")
            y -= 18
            c.setFont("Helvetica", 10)
            # Word-wrap recommendation text
            words = recommendation.split()
            line = ""
            max_line_width = width - 2 * _MARGIN - 20
            for word in words:
                test_line = f"{line} {word}".strip()
                if c.stringWidth(test_line, "Helvetica", 10) < max_line_width:
                    line = test_line
                else:
                    c.drawString(_MARGIN + 10, y, line)
                    y -= 14
                    line = word
                    if y < 60:
                        c.showPage()
                        y = height - 60
            if line:
                c.drawString(_MARGIN + 10, y, line)

        c.save()
        return buf.getvalue()

    def _generate_income_report_fallback(
        self,
        calculation: Dict,
        sources: List[Dict],
    ) -> bytes:
        """Generate income report with minimal PDF fallback."""
        total_monthly = calculation.get("total_monthly_income", 0)
        qualifying = calculation.get("qualifying_income", total_monthly)
        dti_front = calculation.get("dti_front", 0)
        dti_back = calculation.get("dti_back", 0)

        lines = [
            "INCOME CALCULATION REPORT",
            self._company_name,
            f"Generated: {datetime.now(timezone.utc).strftime('%m/%d/%Y')}",
            "",
            "--- Summary ---",
            f"Total Monthly Income: ${total_monthly:,.2f}",
            f"Qualifying Income: ${qualifying:,.2f}",
            f"Front-End DTI: {dti_front:.1f}%",
            f"Back-End DTI: {dti_back:.1f}%",
            "",
            "--- Income Sources ---",
        ]
        for source in sources:
            verified = "Yes" if source.get("verified") else "No"
            lines.append(
                f"  {source.get('name', '')} ({source.get('type', '')}) "
                f"- ${source.get('monthly_amount', 0):,.2f}/mo "
                f"- Verified: {verified}"
            )

        recommendation = calculation.get("recommendation", "")
        if recommendation:
            lines += ["", "--- AI Recommendation ---", f"  {recommendation}"]

        return self._create_simple_pdf("\n".join(lines), title="Income Calculation Report")

    # ------------------------------------------------------------------
    # 9. Add Page Numbers
    # ------------------------------------------------------------------

    def add_page_numbers(
        self,
        pdf_content: bytes,
        start_number: int = 1,
        position: str = "bottom-center",
    ) -> PDFGenerationResult:
        """Add page numbers to an existing PDF.

        Args:
            pdf_content: Source PDF bytes.
            start_number: Starting page number.
            position: One of "bottom-center", "bottom-right", "top-right".

        Returns:
            PDFGenerationResult with numbered pages.
        """
        result = self._add_page_numbers_internal(pdf_content, start_number, position)
        if result is None:
            return PDFGenerationResult(
                content=pdf_content,
                page_count=self.get_page_count(pdf_content),
                file_size=len(pdf_content),
                sha256_hash=self._hash_content(pdf_content),
                success=False,
                error="reportlab and pypdf are both required for page numbering",
            )

        return PDFGenerationResult(
            content=result,
            page_count=self.get_page_count(result),
            file_size=len(result),
            sha256_hash=self._hash_content(result),
        )

    def _add_page_numbers_internal(
        self,
        pdf_content: bytes,
        start_number: int = 1,
        position: str = "bottom-center",
    ) -> Optional[bytes]:
        """Internal page numbering — returns None if deps missing."""
        if not HAS_REPORTLAB or not HAS_PYPDF:
            return None

        try:
            reader = PdfReader(io.BytesIO(pdf_content))
            writer = PdfWriter()
            total_pages = len(reader.pages)

            for page_idx in range(total_pages):
                page = reader.pages[page_idx]
                page_w = float(page.mediabox.width)
                page_h = float(page.mediabox.height)
                page_num = start_number + page_idx

                # Create overlay with page number
                overlay_buf = io.BytesIO()
                c = rl_canvas.Canvas(overlay_buf, pagesize=(page_w, page_h))
                c.setFont("Helvetica", 9)
                c.setFillColor(colors.HexColor("#888888"))

                text = f"Page {page_num} of {total_pages + start_number - 1}"

                if position == "bottom-center":
                    c.drawCentredString(page_w / 2, 25, text)
                elif position == "bottom-right":
                    c.drawRightString(page_w - _MARGIN, 25, text)
                elif position == "top-right":
                    c.drawRightString(page_w - _MARGIN, page_h - 25, text)
                else:
                    c.drawCentredString(page_w / 2, 25, text)

                c.save()

                overlay_reader = PdfReader(io.BytesIO(overlay_buf.getvalue()))
                page.merge_page(overlay_reader.pages[0])
                writer.add_page(page)

            out_buf = io.BytesIO()
            writer.write(out_buf)
            return out_buf.getvalue()
        except Exception as e:
            logger.warning("Could not add page numbers: %s", e)
            return None

    # ------------------------------------------------------------------
    # 10. Get Page Count
    # ------------------------------------------------------------------

    def get_page_count(self, pdf_content: bytes) -> int:
        """Return number of pages in a PDF.

        Args:
            pdf_content: PDF file bytes.

        Returns:
            Page count, or 0 on error.
        """
        if not pdf_content:
            return 0

        if HAS_PYPDF:
            try:
                reader = PdfReader(io.BytesIO(pdf_content))
                return len(reader.pages)
            except Exception as e:
                logger.warning("Could not read page count: %s", e)
                return 0

        # Fallback: count /Type /Page entries (rough estimate)
        try:
            count = pdf_content.count(b"/Type /Page")
            # Subtract /Type /Pages (the parent node)
            pages_count = pdf_content.count(b"/Type /Pages")
            return max(count - pages_count, 1)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # 11. Extract Text
    # ------------------------------------------------------------------

    def extract_text(self, pdf_content: bytes, max_pages: int = 50) -> str:
        """Extract text content from a PDF.

        Args:
            pdf_content: PDF file bytes.
            max_pages: Maximum pages to extract (for performance).

        Returns:
            Extracted text, or empty string on error.
        """
        if not pdf_content:
            return ""

        if not HAS_PYPDF:
            logger.warning("pypdf not available — cannot extract text")
            return ""

        try:
            reader = PdfReader(io.BytesIO(pdf_content))
            texts: List[str] = []
            for idx, page in enumerate(reader.pages):
                if idx >= max_pages:
                    break
                page_text = page.extract_text()
                if page_text:
                    texts.append(page_text)
            return "\n\n".join(texts)
        except Exception as e:
            logger.warning("Could not extract text from PDF: %s", e)
            return ""

    # ------------------------------------------------------------------
    # 12. Hash Content
    # ------------------------------------------------------------------

    def _hash_content(self, content: bytes) -> str:
        """Return SHA-256 hex digest of content."""
        return hashlib.sha256(content).hexdigest()

    # ------------------------------------------------------------------
    # 13. Simple PDF Fallback
    # ------------------------------------------------------------------

    def _create_simple_pdf(self, text_content: str, title: str = "") -> bytes:
        """Create a minimal text PDF without reportlab.

        Builds a raw PDF 1.4 document with a single page containing the
        provided text content.  The text is rendered in Courier at 10pt.

        Args:
            text_content: Plain text to include.
            title: PDF metadata title.

        Returns:
            Raw PDF bytes.
        """
        # Encode text lines into a content stream
        lines = text_content.split("\n")
        font_size = 10
        leading = 13  # line spacing in points
        usable_height = _PAGE_HEIGHT - 2 * _MARGIN
        max_lines_per_page = int(usable_height / leading)

        # Split into pages
        pages_text: List[List[str]] = []
        for i in range(0, len(lines), max_lines_per_page):
            pages_text.append(lines[i : i + max_lines_per_page])

        if not pages_text:
            pages_text = [[""]]

        # Build PDF objects
        objects: List[bytes] = []
        offsets: List[int] = []

        def add_obj(data: bytes) -> int:
            obj_num = len(objects) + 1
            objects.append(data)
            return obj_num

        # 1 - Catalog
        catalog_obj = add_obj(b"")  # placeholder
        # 2 - Pages
        pages_obj = add_obj(b"")  # placeholder
        # 3 - Font
        font_obj = add_obj(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"
        )

        # Page objects and content streams
        page_obj_nums: List[int] = []
        for page_lines in pages_text:
            # Build content stream
            stream_lines: List[str] = [
                "BT",
                f"/F1 {font_size} Tf",
                f"{_MARGIN} {_PAGE_HEIGHT - _MARGIN} Td",
                f"{leading} TL",
            ]
            for line in page_lines:
                # Escape PDF special characters in text
                safe = (
                    line.replace("\\", "\\\\")
                    .replace("(", "\\(")
                    .replace(")", "\\)")
                )
                stream_lines.append(f"({safe}) '")
            stream_lines.append("ET")
            stream_data = "\n".join(stream_lines).encode("latin-1", errors="replace")

            content_obj = add_obj(
                f"<< /Length {len(stream_data)} >>\nstream\n".encode()
                + stream_data
                + b"\nendstream"
            )

            page_obj = add_obj(
                (
                    f"<< /Type /Page /Parent 2 0 R "
                    f"/MediaBox [0 0 {_PAGE_WIDTH} {_PAGE_HEIGHT}] "
                    f"/Contents {content_obj} 0 R "
                    f"/Resources << /Font << /F1 {font_obj} 0 R >> >> >>"
                ).encode()
            )
            page_obj_nums.append(page_obj)

        # Fill in Pages object
        kids = " ".join(f"{n} 0 R" for n in page_obj_nums)
        objects[pages_obj - 1] = (
            f"<< /Type /Pages /Kids [{kids}] /Count {len(page_obj_nums)} >>"
        ).encode()

        # Fill in Catalog
        title_escaped = title.replace("(", "\\(").replace(")", "\\)")
        objects[catalog_obj - 1] = (
            f"<< /Type /Catalog /Pages {pages_obj} 0 R >>"
        ).encode()

        # Info dict (for title)
        info_obj = add_obj(
            f"<< /Title ({title_escaped}) /Producer (PerenniaAI PDFGen) >>".encode()
        )

        # Serialize
        output = io.BytesIO()
        output.write(b"%PDF-1.4\n")

        offsets = []
        for idx, obj_data in enumerate(objects):
            offsets.append(output.tell())
            obj_num = idx + 1
            output.write(f"{obj_num} 0 obj\n".encode())
            output.write(obj_data)
            output.write(b"\nendobj\n")

        # Cross-reference table
        xref_offset = output.tell()
        output.write(b"xref\n")
        output.write(f"0 {len(objects) + 1}\n".encode())
        output.write(b"0000000000 65535 f \n")
        for off in offsets:
            output.write(f"{off:010d} 00000 n \n".encode())

        # Trailer
        output.write(b"trailer\n")
        output.write(
            f"<< /Size {len(objects) + 1} /Root {catalog_obj} 0 R "
            f"/Info {info_obj} 0 R >>\n".encode()
        )
        output.write(b"startxref\n")
        output.write(f"{xref_offset}\n".encode())
        output.write(b"%%EOF\n")

        return output.getvalue()

    # ------------------------------------------------------------------
    # 14. Image to PDF
    # ------------------------------------------------------------------

    def image_to_pdf(self, image_content: bytes, filename: str) -> bytes:
        """Convert an image (JPEG, PNG, TIFF) to a single-page PDF.

        Args:
            image_content: Raw image bytes.
            filename: Original filename (used for format detection).

        Returns:
            PDF bytes containing the image, or empty bytes on failure.
        """
        if HAS_REPORTLAB and HAS_PIL:
            return self._image_to_pdf_reportlab(image_content, filename)
        elif HAS_PIL:
            return self._image_to_pdf_pil(image_content, filename)
        else:
            logger.warning(
                "Cannot convert image to PDF — PIL and reportlab not available"
            )
            return b""

    def _image_to_pdf_reportlab(self, image_content: bytes, filename: str) -> bytes:
        """Convert image using ReportLab + PIL."""
        try:
            from reportlab.lib.utils import ImageReader

            img = PILImage.open(io.BytesIO(image_content))
            img_width, img_height = img.size

            # Scale to fit letter page with margins
            max_w = _PAGE_WIDTH - 2 * _MARGIN
            max_h = _PAGE_HEIGHT - 2 * _MARGIN
            scale = min(max_w / img_width, max_h / img_height, 1.0)
            draw_w = img_width * scale
            draw_h = img_height * scale

            buf = io.BytesIO()
            c = rl_canvas.Canvas(buf, pagesize=letter)

            img_reader = ImageReader(io.BytesIO(image_content))
            x = (_PAGE_WIDTH - draw_w) / 2
            y = (_PAGE_HEIGHT - draw_h) / 2
            c.drawImage(img_reader, x, y, width=draw_w, height=draw_h)
            c.save()
            return buf.getvalue()
        except Exception as e:
            logger.warning("ReportLab image conversion failed for %s: %s", filename, e)
            return self._image_to_pdf_pil(image_content, filename)

    def _image_to_pdf_pil(self, image_content: bytes, filename: str) -> bytes:
        """Convert image using PIL's built-in PDF export."""
        try:
            img = PILImage.open(io.BytesIO(image_content))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PDF")
            return buf.getvalue()
        except Exception as e:
            logger.warning("PIL image conversion failed for %s: %s", filename, e)
            return b""


# ---------------------------------------------------------------------------
# Helper for reportlab image drawing
# ---------------------------------------------------------------------------

def _image_reader_path(buf: io.BytesIO):
    """Return an ImageReader from reportlab for the given BytesIO buffer."""
    try:
        from reportlab.lib.utils import ImageReader
        return ImageReader(buf)
    except Exception:
        return buf


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: Optional[PDFGenerationService] = None


def get_pdf_generation_service() -> PDFGenerationService:
    """Get or create the singleton PDFGenerationService instance."""
    global _service
    if _service is None:
        _service = PDFGenerationService()
    return _service
