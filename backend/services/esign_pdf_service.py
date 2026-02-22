"""
E-Signature PDF Service

Handles PDF manipulation for the e-signature system:
- Extract PDF metadata (page count, dimensions)
- Flatten signed PDFs with field values
- Generate audit trail PDF
- Create combined final document
"""

import io
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)


class EsignPDFService:
    """
    Service for PDF manipulation in the e-signature system.
    Uses pypdf for reading and reportlab for overlay generation.
    """

    # Cursive fonts for typed signatures
    SIGNATURE_FONTS = {
        "great_vibes": "Great Vibes",
        "dancing_script": "Dancing Script",
        "pacifico": "Pacifico",
        "sacramento": "Sacramento",
        "allura": "Allura",
    }

    def __init__(self, s3_service=None):
        """
        Initialize PDF service.

        Args:
            s3_service: Optional S3 service for fetching/storing PDFs
        """
        self.s3_service = s3_service
        self._fonts_registered = False

    def get_pdf_metadata(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Extract metadata from a PDF.

        Returns page count and dimensions in PDF points (72 pts/inch).
        """
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(pdf_bytes))
            page_count = len(reader.pages)

            page_dimensions = []
            for page in reader.pages:
                box = page.mediabox
                page_dimensions.append({
                    "width_points": float(box.width),
                    "height_points": float(box.height),
                })

            return {
                "success": True,
                "page_count": page_count,
                "page_dimensions": page_dimensions,
                "file_size": len(pdf_bytes),
            }

        except Exception as e:
            logger.error(f"Error extracting PDF metadata: {e}")
            return {
                "success": False,
                "error": "Internal server error",
            }

    def flatten_signed_pdf(
        self,
        original_pdf_bytes: bytes,
        fields: List[Dict[str, Any]],
        field_values: List[Dict[str, Any]],
        signers: List[Dict[str, Any]],
    ) -> Tuple[bytes, str]:
        """
        Create a flattened PDF with all field values rendered.

        Args:
            original_pdf_bytes: Original PDF document
            fields: List of field placements
            field_values: List of submitted values
            signers: List of signers with adopted signatures

        Returns:
            Tuple of (pdf_bytes, sha256_hash)
        """
        try:
            from pypdf import PdfReader, PdfWriter
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.colors import HexColor
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            # Build lookup maps
            value_map = {v["field_id"]: v for v in field_values}
            signer_map = {s["id"]: s for s in signers}

            # Read original PDF
            reader = PdfReader(io.BytesIO(original_pdf_bytes))
            writer = PdfWriter()

            # Group fields by page
            fields_by_page = {}
            for field in fields:
                page_num = field.get("page_number", 1)
                if page_num not in fields_by_page:
                    fields_by_page[page_num] = []
                fields_by_page[page_num].append(field)

            # Process each page
            for page_idx, page in enumerate(reader.pages):
                page_num = page_idx + 1
                page_box = page.mediabox
                page_width = float(page_box.width)
                page_height = float(page_box.height)

                # Create overlay for this page
                overlay_buffer = io.BytesIO()
                c = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))

                # Render fields on this page
                page_fields = fields_by_page.get(page_num, [])
                for field in page_fields:
                    field_id = field["id"]
                    value = value_map.get(field_id)

                    if not value:
                        continue

                    self._render_field(
                        canvas=c,
                        field=field,
                        value=value,
                        signer_map=signer_map,
                        page_height=page_height,
                    )

                c.save()
                overlay_buffer.seek(0)

                # Merge overlay with original page
                overlay_reader = PdfReader(overlay_buffer)
                if overlay_reader.pages:
                    page.merge_page(overlay_reader.pages[0])

                writer.add_page(page)

            # Generate output PDF
            output_buffer = io.BytesIO()
            writer.write(output_buffer)
            output_buffer.seek(0)
            pdf_bytes = output_buffer.read()

            # Calculate hash
            sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()

            return pdf_bytes, sha256_hash

        except Exception as e:
            logger.error(f"Error flattening PDF: {e}")
            raise

    def _render_field(
        self,
        canvas,
        field: Dict[str, Any],
        value: Dict[str, Any],
        signer_map: Dict[int, Dict[str, Any]],
        page_height: float,
    ):
        """Render a single field onto the canvas."""
        from reportlab.lib.colors import HexColor

        field_type = field.get("field_type")
        x = float(field.get("x_position_points", 0))
        # Convert from bottom-left origin (stored) to top-left (rendering)
        y = float(field.get("y_position_points", 0))
        width = float(field.get("width_points", 144))
        height = float(field.get("height_points", 36))

        font_name = field.get("font_name", "Helvetica")
        font_size = float(field.get("font_size", 12))
        font_color = field.get("font_color", "#000000")

        try:
            canvas.setFillColor(HexColor(font_color))
        except Exception as e:
            logger.exception(f"Failed to set font color '{font_color}', falling back to black: {e}")
            canvas.setFillColor(HexColor("#000000"))

        if field_type in ["signature", "initial"]:
            # Render typed signature
            signer_id = field.get("signer_id")
            signer = signer_map.get(signer_id, {})
            signature_text = signer.get("adopted_signature_text", "")
            signature_font = signer.get("adopted_signature_font", "Helvetica")

            if signature_text:
                # Use larger font for signatures
                sig_font_size = min(font_size * 1.5, height * 0.7)
                canvas.setFont("Helvetica-Oblique", sig_font_size)

                # Center text in field
                text_y = y + (height - sig_font_size) / 2
                canvas.drawString(x + 4, text_y, signature_text)

        elif field_type == "date_signed":
            # Render date
            date_text = value.get("text_value", "")
            if date_text:
                canvas.setFont(font_name, font_size)
                text_y = y + (height - font_size) / 2
                canvas.drawString(x + 4, text_y, date_text)

        elif field_type == "text":
            # Render text
            text_value = value.get("text_value", "")
            if text_value:
                canvas.setFont(font_name, font_size)
                text_y = y + (height - font_size) / 2
                canvas.drawString(x + 4, text_y, text_value)

        elif field_type == "checkbox":
            # Render checkbox
            if value.get("boolean_value"):
                # Draw checkmark
                canvas.setFont("ZapfDingbats", font_size)
                text_y = y + (height - font_size) / 2
                canvas.drawString(x + (width - font_size) / 2, text_y, "4")  # Checkmark

        elif field_type == "dropdown":
            # Render selected option
            text_value = value.get("text_value", "")
            if text_value:
                canvas.setFont(font_name, font_size)
                text_y = y + (height - font_size) / 2
                canvas.drawString(x + 4, text_y, text_value)

    def generate_audit_trail_pdf(
        self,
        envelope: Dict[str, Any],
        signers: List[Dict[str, Any]],
        audit_events: List[Dict[str, Any]],
    ) -> bytes:
        """
        Generate an audit trail PDF (Certificate of Completion).

        Args:
            envelope: Envelope data
            signers: List of signers
            audit_events: Chronological audit events

        Returns:
            PDF bytes
        """
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.colors import HexColor

            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=letter)
            width, height = letter

            # Header
            y = height - 50
            c.setFont("Helvetica-Bold", 18)
            c.drawString(50, y, "Certificate of Completion")

            y -= 30
            c.setFont("Helvetica", 10)
            c.drawString(50, y, f"Document: {envelope.get('name', 'Unknown')}")

            y -= 15
            c.drawString(50, y, f"Envelope ID: {envelope.get('id')}")

            y -= 15
            completed_at = envelope.get('completed_at')
            if completed_at:
                if isinstance(completed_at, str):
                    completed_str = completed_at
                else:
                    completed_str = completed_at.strftime("%m/%d/%Y %I:%M %p %Z")
                c.drawString(50, y, f"Completed: {completed_str}")

            # Signer Summary
            y -= 40
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y, "Signer Summary")

            y -= 5
            c.setStrokeColor(HexColor("#CCCCCC"))
            c.line(50, y, width - 50, y)

            c.setFont("Helvetica", 10)
            for signer in signers:
                y -= 25
                if y < 100:
                    c.showPage()
                    y = height - 50
                    c.setFont("Helvetica", 10)

                name = signer.get('name', 'Unknown')
                email = signer.get('email', '')
                status = signer.get('status', 'pending')
                signed_at = signer.get('signed_at')

                c.drawString(50, y, f"• {name} ({email})")
                y -= 15
                c.drawString(70, y, f"Status: {status.upper()}")

                if signed_at:
                    y -= 15
                    if isinstance(signed_at, str):
                        signed_str = signed_at
                    else:
                        signed_str = signed_at.strftime("%m/%d/%Y %I:%M %p %Z")
                    c.drawString(70, y, f"Signed: {signed_str}")

                ip = signer.get('last_access_ip')
                if ip:
                    y -= 15
                    c.drawString(70, y, f"IP Address: {ip}")

            # Audit Trail
            y -= 40
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y, "Audit Trail")

            y -= 5
            c.line(50, y, width - 50, y)

            c.setFont("Helvetica", 9)
            for event in audit_events:
                y -= 20
                if y < 100:
                    c.showPage()
                    y = height - 50
                    c.setFont("Helvetica", 9)

                created_at = event.get('created_at')
                if isinstance(created_at, str):
                    time_str = created_at[:19]
                else:
                    time_str = created_at.strftime("%Y-%m-%d %H:%M:%S")

                action = event.get('action', '')
                description = event.get('description', '')
                actor_email = event.get('actor_email', '')
                ip = event.get('ip_address', '')

                c.drawString(50, y, f"{time_str}")
                c.drawString(170, y, f"{action}")
                y -= 12
                c.drawString(70, y, description[:80])
                if actor_email:
                    y -= 12
                    c.drawString(70, y, f"By: {actor_email}" + (f" ({ip})" if ip else ""))

            # Footer
            y = 50
            c.setFont("Helvetica", 8)
            c.setFillColor(HexColor("#666666"))
            c.drawString(50, y, "This audit trail is automatically generated and is part of the legal record of this signing.")

            c.save()
            buffer.seek(0)
            return buffer.read()

        except Exception as e:
            logger.error(f"Error generating audit trail PDF: {e}")
            raise

    def combine_pdfs(
        self,
        signed_pdf_bytes: bytes,
        audit_pdf_bytes: bytes,
    ) -> bytes:
        """
        Combine signed PDF and audit trail into a single document.

        Args:
            signed_pdf_bytes: The signed document
            audit_pdf_bytes: The audit trail

        Returns:
            Combined PDF bytes
        """
        try:
            from pypdf import PdfReader, PdfWriter

            writer = PdfWriter()

            # Add signed document
            signed_reader = PdfReader(io.BytesIO(signed_pdf_bytes))
            for page in signed_reader.pages:
                writer.add_page(page)

            # Add audit trail
            audit_reader = PdfReader(io.BytesIO(audit_pdf_bytes))
            for page in audit_reader.pages:
                writer.add_page(page)

            output_buffer = io.BytesIO()
            writer.write(output_buffer)
            output_buffer.seek(0)
            return output_buffer.read()

        except Exception as e:
            logger.error(f"Error combining PDFs: {e}")
            raise

    def generate_signed_pdf(self, envelope_id: int, db=None) -> Dict[str, Any]:
        """
        Generate the complete signed PDF package for a completed envelope.

        Orchestrates the full flow:
        1. Fetch envelope data, signers, fields, field values, and audit events from DB
        2. Download original PDF from S3
        3. Flatten field values onto PDF (signatures, text, dates, checkboxes)
        4. Generate audit trail PDF
        5. Combine signed PDF + audit trail
        6. Upload final document back to S3
        7. Record completed document in database

        Args:
            envelope_id: The envelope ID to generate documents for
            db: Database session (required)

        Returns:
            Dict with success status and document details
        """
        if db is None:
            return {"success": False, "error": "Database session required"}

        if self.s3_service is None:
            return {"success": False, "error": "S3 service not configured"}

        try:
            from sqlalchemy import text as sql_text

            # 1. Fetch envelope
            envelope_row = db.execute(sql_text(
                "SELECT * FROM esign_envelopes WHERE id = :id"
            ), {"id": envelope_id}).fetchone()

            if not envelope_row:
                return {"success": False, "error": f"Envelope {envelope_id} not found"}

            envelope = dict(envelope_row._mapping)

            if envelope["status"] != "completed":
                return {"success": False, "error": "Envelope not yet completed"}

            pdf_storage_key = envelope.get("pdf_storage_key")
            if not pdf_storage_key:
                return {"success": False, "error": "No PDF storage key on envelope"}

            # 2. Fetch signers, fields, field values, audit events
            signers = [
                dict(r._mapping) for r in db.execute(sql_text(
                    "SELECT * FROM esign_signers WHERE envelope_id = :id"
                ), {"id": envelope_id}).fetchall()
            ]

            fields = [
                dict(r._mapping) for r in db.execute(sql_text(
                    "SELECT * FROM esign_fields WHERE envelope_id = :id"
                ), {"id": envelope_id}).fetchall()
            ]

            field_values = [
                dict(r._mapping) for r in db.execute(sql_text("""
                    SELECT fv.* FROM esign_field_values fv
                    JOIN esign_fields f ON f.id = fv.field_id
                    WHERE f.envelope_id = :id
                """), {"id": envelope_id}).fetchall()
            ]

            audit_events = [
                dict(r._mapping) for r in db.execute(sql_text("""
                    SELECT * FROM esign_audit_events
                    WHERE envelope_id = :id
                    ORDER BY created_at ASC
                """), {"id": envelope_id}).fetchall()
            ]

            # 3. Download original PDF from S3
            download_result = self.s3_service.download_file(pdf_storage_key)
            if not download_result.get("success"):
                return {
                    "success": False,
                    "error": f"Failed to download PDF: {download_result.get('error')}"
                }

            original_pdf_bytes = download_result["content"]
            logger.info(f"Downloaded original PDF ({len(original_pdf_bytes)} bytes) for envelope {envelope_id}")

            # 4. Flatten signed PDF with field values
            signed_pdf_bytes, pdf_hash = self.flatten_signed_pdf(
                original_pdf_bytes=original_pdf_bytes,
                fields=fields,
                field_values=field_values,
                signers=signers,
            )
            logger.info(f"Flattened signed PDF ({len(signed_pdf_bytes)} bytes) hash={pdf_hash[:16]}...")

            # 5. Generate audit trail PDF
            audit_pdf_bytes = self.generate_audit_trail_pdf(
                envelope=envelope,
                signers=signers,
                audit_events=audit_events,
            )
            logger.info(f"Generated audit trail PDF ({len(audit_pdf_bytes)} bytes)")

            # 6. Combine signed PDF + audit trail
            combined_pdf_bytes = self.combine_pdfs(signed_pdf_bytes, audit_pdf_bytes)
            logger.info(f"Combined PDF ({len(combined_pdf_bytes)} bytes)")

            combined_hash = hashlib.sha256(combined_pdf_bytes).hexdigest()

            # 7. Upload final document to S3
            # Store alongside original with _signed suffix
            base_key = pdf_storage_key.rsplit('.', 1)[0] if '.' in pdf_storage_key else pdf_storage_key
            signed_key = f"{base_key}_signed.pdf"
            audit_key = f"{base_key}_audit.pdf"
            combined_key = f"{base_key}_complete.pdf"

            # Upload all three variants
            upload_results = {}
            for key, content, label in [
                (signed_key, signed_pdf_bytes, "signed"),
                (audit_key, audit_pdf_bytes, "audit"),
                (combined_key, combined_pdf_bytes, "complete"),
            ]:
                result = self.s3_service.upload_file(
                    storage_key=key,
                    file_content=content,
                    content_type="application/pdf",
                    metadata={
                        "envelope_id": str(envelope_id),
                        "document_type": label,
                    }
                )
                upload_results[label] = result
                if not result.get("success"):
                    logger.error(f"Failed to upload {label} PDF: {result.get('error')}")

            # 8. Record completed document in database
            now = datetime.now(timezone.utc).isoformat()
            try:
                db.execute(sql_text("""
                    INSERT INTO esign_completed_documents
                        (envelope_id, document_type, storage_key, file_size, sha256_hash, created_at)
                    VALUES
                        (:envelope_id, 'signed', :signed_key, :signed_size, :signed_hash, :now),
                        (:envelope_id, 'audit_trail', :audit_key, :audit_size, :audit_hash, :now),
                        (:envelope_id, 'complete', :combined_key, :combined_size, :combined_hash, :now)
                """), {
                    "envelope_id": envelope_id,
                    "signed_key": signed_key,
                    "signed_size": len(signed_pdf_bytes),
                    "signed_hash": pdf_hash,
                    "audit_key": audit_key,
                    "audit_size": len(audit_pdf_bytes),
                    "audit_hash": hashlib.sha256(audit_pdf_bytes).hexdigest(),
                    "combined_key": combined_key,
                    "combined_size": len(combined_pdf_bytes),
                    "combined_hash": combined_hash,
                    "now": now,
                })
                db.commit()
            except Exception as e:
                logger.warning(f"Could not record completed documents (table may not exist): {e}")
                db.rollback()

            return {
                "success": True,
                "envelope_id": envelope_id,
                "documents": {
                    "signed": {
                        "storage_key": signed_key,
                        "file_size": len(signed_pdf_bytes),
                        "sha256": pdf_hash,
                    },
                    "audit_trail": {
                        "storage_key": audit_key,
                        "file_size": len(audit_pdf_bytes),
                    },
                    "complete": {
                        "storage_key": combined_key,
                        "file_size": len(combined_pdf_bytes),
                        "sha256": combined_hash,
                    },
                },
                "signer_count": len(signers),
                "field_count": len(fields),
            }

        except Exception as e:
            logger.error(f"Error generating signed PDF for envelope {envelope_id}: {e}")
            return {
                "success": False,
                "error": "Internal server error",
            }

    def generate_preview_pages(
        self,
        pdf_bytes: bytes,
        max_pages: int = 10,
        dpi: int = 72,
    ) -> List[bytes]:
        """
        Generate PNG previews of PDF pages.

        Args:
            pdf_bytes: PDF document
            max_pages: Maximum pages to preview
            dpi: Resolution for rendering

        Returns:
            List of PNG image bytes
        """
        try:
            # This requires pdf2image which needs poppler
            # Fallback to returning empty list if not available
            try:
                from pdf2image import convert_from_bytes
            except ImportError:
                logger.warning("pdf2image not available, skipping preview generation")
                return []

            images = convert_from_bytes(
                pdf_bytes,
                first_page=1,
                last_page=max_pages,
                dpi=dpi,
            )

            previews = []
            for img in images:
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                buffer.seek(0)
                previews.append(buffer.read())

            return previews

        except Exception as e:
            logger.error(f"Error generating previews: {e}")
            return []


# Singleton instance
_pdf_service = None


def get_esign_pdf_service(s3_service=None) -> EsignPDFService:
    """Get or create the PDF service singleton."""
    global _pdf_service
    if _pdf_service is None:
        _pdf_service = EsignPDFService(s3_service)
    return _pdf_service
