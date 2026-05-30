"""
Perennia Docs AI Triage Agent

LangGraph-powered document classification and data extraction.

Pipeline:
1. Load document (PDF/image)
2. Classify document type using vision model
3. Extract key data fields
4. Validate quality and completeness
5. Update database with classification

Uses Claude claude-sonnet-4-6 for vision-based classification.
"""

import os
import io
import base64
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple, TypedDict
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# DOCUMENT TYPES AND EXTRACTION SCHEMAS
# =============================================================================

class DocType(str, Enum):
    """Standard mortgage document types."""
    PAYSTUB = "paystub"
    W2 = "w2"
    TAX_RETURN = "tax_return"
    BANK_STATEMENT = "bank_statement"
    INVESTMENT_STATEMENT = "investment_statement"
    DRIVERS_LICENSE = "drivers_license"
    PASSPORT = "passport"
    PURCHASE_CONTRACT = "purchase_contract"
    APPRAISAL = "appraisal"
    TITLE = "title"
    INSURANCE = "insurance"
    GIFT_LETTER = "gift_letter"
    EMPLOYMENT_VERIFICATION = "employment_verification"
    OTHER = "other"


# Extraction schemas per document type
EXTRACTION_SCHEMAS = {
    DocType.PAYSTUB: {
        "fields": ["employer_name", "employee_name", "pay_period_start", "pay_period_end",
                   "gross_pay", "net_pay", "ytd_gross", "pay_frequency"],
        "required": ["employer_name", "employee_name", "gross_pay", "pay_period_end"]
    },
    DocType.W2: {
        "fields": ["employer_name", "employee_name", "employee_ssn_last4", "tax_year",
                   "wages", "federal_tax_withheld", "state_tax_withheld", "employer_ein"],
        "required": ["employer_name", "employee_name", "tax_year", "wages"]
    },
    DocType.BANK_STATEMENT: {
        "fields": ["bank_name", "account_holder", "account_number_last4", "statement_date",
                   "beginning_balance", "ending_balance", "total_deposits", "total_withdrawals"],
        "required": ["bank_name", "account_holder", "statement_date", "ending_balance"]
    },
    DocType.DRIVERS_LICENSE: {
        "fields": ["full_name", "license_number", "state", "date_of_birth",
                   "expiration_date", "address"],
        "required": ["full_name", "license_number", "expiration_date"]
    },
    DocType.TAX_RETURN: {
        "fields": ["tax_year", "taxpayer_name", "filing_status", "total_income",
                   "adjusted_gross_income", "taxable_income", "total_tax"],
        "required": ["tax_year", "taxpayer_name", "adjusted_gross_income"]
    }
}


@dataclass
class ClassificationResult:
    """Result of document classification."""
    doc_type: str
    doc_subtype: Optional[str] = None
    confidence: float = 0.0
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    validation_errors: List[str] = field(default_factory=list)
    quality_checks: Dict[str, Any] = field(default_factory=dict)
    raw_response: Optional[str] = None
    model: str = "unknown"
    tokens_used: int = 0


class TriageState(TypedDict):
    """State for LangGraph triage pipeline."""
    document_id: int
    file_data: bytes
    mime_type: str
    file_name: str
    classification: Optional[ClassificationResult]
    error: Optional[str]
    step: str


# =============================================================================
# AI TRIAGE AGENT
# =============================================================================

class PerenniaAITriageAgent:
    """
    AI-powered document classification and extraction agent.

    Uses Claude vision model to:
    1. Classify document type
    2. Extract key fields
    3. Validate data quality
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-6"
    ):
        """
        Initialize triage agent.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Model to use for classification
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.confidence_threshold = 0.85  # Auto-approve threshold

        if not self.api_key:
            logger.warning("No Anthropic API key configured - AI triage will be disabled")

    def classify_document(
        self,
        file_data: bytes,
        mime_type: str,
        file_name: str
    ) -> ClassificationResult:
        """
        Classify a document and extract key data.

        Args:
            file_data: Raw file bytes
            mime_type: MIME type of the file
            file_name: Original filename

        Returns:
            ClassificationResult with classification and extraction
        """
        if not self.api_key:
            return ClassificationResult(
                doc_type="other",
                confidence=0.0,
                validation_errors=["AI classification disabled - no API key"]
            )

        try:
            # Convert to base64 for vision API
            image_data = self._prepare_image(file_data, mime_type)

            if image_data is None:
                return ClassificationResult(
                    doc_type="other",
                    confidence=0.0,
                    validation_errors=["Could not process file for classification"]
                )

            # Run classification
            classification = self._run_classification(image_data, mime_type, file_name)

            # If we got a classification, try to extract data
            if classification.doc_type != "other" and classification.confidence >= 0.7:
                extraction = self._run_extraction(image_data, mime_type, classification.doc_type)
                classification.extracted_data = extraction.get("data", {})
                classification.validation_errors = extraction.get("errors", [])

            # Run quality checks
            classification.quality_checks = self._run_quality_checks(image_data, mime_type)

            return classification

        except Exception as e:
            logger.error(f"Classification failed for {file_name}: {e}")
            return ClassificationResult(
                doc_type="other",
                confidence=0.0,
                validation_errors=[f"Classification error: {str(e)}"]
            )

    def _prepare_image(self, file_data: bytes, mime_type: str) -> Optional[str]:
        """Prepare file data for vision API."""
        # For PDFs, convert first page to image
        if mime_type == "application/pdf":
            return self._pdf_to_base64(file_data)

        # For images, encode directly
        if mime_type.startswith("image/"):
            return base64.b64encode(file_data).decode("utf-8")

        return None

    def _pdf_to_base64(self, pdf_data: bytes) -> Optional[str]:
        """Convert PDF first page to base64 image."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=pdf_data, filetype="pdf")
            page = doc[0]

            # Render at 150 DPI
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")

            doc.close()

            return base64.b64encode(img_bytes).decode("utf-8")

        except ImportError:
            logger.warning("PyMuPDF not installed - PDF classification unavailable")
            return None
        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")
            return None

    def _run_classification(
        self,
        image_base64: str,
        mime_type: str,
        file_name: str
    ) -> ClassificationResult:
        """Run document classification using Claude vision."""
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)

        # Build classification prompt
        doc_types_list = ", ".join([t.value for t in DocType if t != DocType.OTHER])

        prompt = f"""Analyze this mortgage document image and classify it.

Document filename: {file_name}

Available document types: {doc_types_list}

Respond in this exact JSON format:
{{
    "doc_type": "the document type from the list above, or 'other' if unclear",
    "doc_subtype": "optional subtype like 'biweekly' for paystubs, null if not applicable",
    "confidence": 0.0 to 1.0 confidence score,
    "reasoning": "brief explanation of classification"
}}

Be precise. Only classify as a specific type if you are confident. Use 'other' for unclear documents."""

        try:
            # Determine media type for API
            if mime_type == "application/pdf":
                media_type = "image/png"  # We converted to PNG
            else:
                media_type = mime_type

            response = client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )

            # Parse response
            response_text = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            # Extract JSON from response
            import json
            import re

            json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())

                return ClassificationResult(
                    doc_type=data.get("doc_type", "other"),
                    doc_subtype=data.get("doc_subtype"),
                    confidence=float(data.get("confidence", 0.0)),
                    raw_response=response_text,
                    model=self.model,
                    tokens_used=tokens_used
                )

            return ClassificationResult(
                doc_type="other",
                confidence=0.0,
                raw_response=response_text,
                validation_errors=["Could not parse classification response"],
                model=self.model,
                tokens_used=tokens_used
            )

        except Exception as e:
            logger.error(f"Classification API call failed: {e}")
            return ClassificationResult(
                doc_type="other",
                confidence=0.0,
                validation_errors=[f"API error: {str(e)}"]
            )

    def _run_extraction(
        self,
        image_base64: str,
        mime_type: str,
        doc_type: str
    ) -> Dict[str, Any]:
        """Extract key fields from document."""
        schema = EXTRACTION_SCHEMAS.get(DocType(doc_type))
        if not schema:
            return {"data": {}, "errors": []}

        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)

        fields_list = ", ".join(schema["fields"])
        required_list = ", ".join(schema["required"])

        prompt = f"""Extract data from this {doc_type} document.

Fields to extract: {fields_list}
Required fields: {required_list}

Respond in this exact JSON format:
{{
    "data": {{
        "field_name": "value or null if not found",
        ...
    }},
    "missing_required": ["list of required fields that could not be found"],
    "low_confidence_fields": ["fields where the value is uncertain"]
}}

For dates, use YYYY-MM-DD format. For money values, use numbers without currency symbols."""

        try:
            if mime_type == "application/pdf":
                media_type = "image/png"
            else:
                media_type = mime_type

            response = client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )

            response_text = response.content[0].text

            import json
            import re

            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                errors = []

                # Add missing required fields as errors
                missing = data.get("missing_required", [])
                for field in missing:
                    errors.append(f"Required field missing: {field}")

                # Add low confidence warnings
                low_conf = data.get("low_confidence_fields", [])
                for field in low_conf:
                    errors.append(f"Low confidence: {field}")

                return {
                    "data": data.get("data", {}),
                    "errors": errors
                }

            return {"data": {}, "errors": ["Could not parse extraction response"]}

        except Exception as e:
            logger.error(f"Extraction API call failed: {e}")
            return {"data": {}, "errors": [f"Extraction error: {str(e)}"]}

    def _run_quality_checks(
        self,
        image_base64: str,
        mime_type: str
    ) -> Dict[str, Any]:
        """Run quality checks on document image."""
        # Basic quality checks we can do without API
        checks = {
            "has_content": True,  # Placeholder
            "is_legible": True,   # Placeholder
            "is_complete": True,  # Placeholder
            "resolution_ok": True # Placeholder
        }

        # Could add more sophisticated checks:
        # - OCR confidence scores
        # - Image blur detection
        # - Page completeness

        return checks


# =============================================================================
# TRIAGE WORKER
# =============================================================================

class PerenniaTriageWorker:
    """
    Worker that processes documents pending AI classification.

    Workflow:
    1. Query for documents with classification_status = 'pending'
    2. Download document from S3
    3. Run AI classification
    4. Update database with results
    5. Trigger rules engine if applicable
    """

    def __init__(self, db: Session, s3_service=None):
        """
        Initialize worker.

        Args:
            db: Database session
            s3_service: Optional S3 service
        """
        self.db = db
        self.agent = PerenniaAITriageAgent()

        if s3_service is None:
            from services.perennia_s3_service import get_s3_service
            self.s3 = get_s3_service()
        else:
            self.s3 = s3_service

        self.batch_size = 5

    def get_pending_documents(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get documents pending classification."""
        result = self.db.execute(text("""
            SELECT id, loan_id, lead_id, request_id,
                   file_name, file_size, mime_type,
                   original_storage_key
            FROM perennia_documents
            WHERE classification_status = 'pending'
              AND virus_scan_status = 'clean'
              AND status = 'processing'
            ORDER BY created_at ASC
            LIMIT :limit
        """), {"limit": limit or self.batch_size})

        return [dict(row._mapping) for row in result]

    def classify_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify a single document.

        Args:
            document: Document record from database

        Returns:
            Dict with classification result
        """
        doc_id = document['id']
        storage_key = document['original_storage_key']
        file_name = document['file_name']
        mime_type = document['mime_type']

        logger.info(f"Classifying document {doc_id}: {file_name}")

        result = {
            "document_id": doc_id,
            "success": False,
            "classification": None,
            "auto_approved": False
        }

        try:
            # Download from S3
            import boto3
            s3_client = boto3.client('s3')

            response = s3_client.get_object(
                Bucket=self.s3.bucket_name,
                Key=storage_key
            )
            file_data = response['Body'].read()

            # Run classification
            classification = self.agent.classify_document(file_data, mime_type, file_name)

            result["classification"] = {
                "doc_type": classification.doc_type,
                "doc_subtype": classification.doc_subtype,
                "confidence": classification.confidence,
                "extracted_data": classification.extracted_data,
                "validation_errors": classification.validation_errors,
                "model": classification.model,
                "tokens_used": classification.tokens_used
            }

            # Update database
            self._update_classification(doc_id, document, classification)

            # Check for auto-approval
            if (classification.confidence >= self.agent.confidence_threshold
                and not classification.validation_errors
                and classification.doc_type != "other"):

                self._auto_approve(doc_id, document, classification)
                result["auto_approved"] = True

            result["success"] = True

        except Exception as e:
            logger.error(f"Error classifying document {doc_id}: {e}")
            self._mark_failed(doc_id, str(e))
            result["error"] = str(e)

        return result

    def _update_classification(
        self,
        doc_id: int,
        document: Dict[str, Any],
        classification: ClassificationResult
    ):
        """Update document with classification results."""
        self.db.execute(text("""
            UPDATE perennia_documents
            SET classification_status = 'classified',
                doc_type = :doc_type,
                doc_subtype = :doc_subtype,
                classification_confidence = :confidence,
                extracted_data = :extracted_data,
                validation_errors = :validation_errors,
                quality_checks = :quality_checks,
                ai_model = :model,
                updated_at = NOW()
            WHERE id = :id
        """), {
            "id": doc_id,
            "doc_type": classification.doc_type,
            "doc_subtype": classification.doc_subtype,
            "confidence": classification.confidence,
            "extracted_data": classification.extracted_data,
            "validation_errors": classification.validation_errors,
            "quality_checks": classification.quality_checks,
            "model": classification.model
        })
        self.db.commit()

        # Log event
        self.db.execute(text("""
            INSERT INTO perennia_document_events (
                document_id, loan_id, lead_id, request_id,
                event_type, event_data, actor_type, created_at
            ) VALUES (
                :doc_id, :loan_id, :lead_id, :request_id,
                'ai_classification', :event_data, 'ai', NOW()
            )
        """), {
            "doc_id": doc_id,
            "loan_id": document.get('loan_id'),
            "lead_id": document.get('lead_id'),
            "request_id": document.get('request_id'),
            "event_data": {
                "doc_type": classification.doc_type,
                "confidence": classification.confidence,
                "model": classification.model,
                "tokens_used": classification.tokens_used
            }
        })
        self.db.commit()

    def _auto_approve(
        self,
        doc_id: int,
        document: Dict[str, Any],
        classification: ClassificationResult
    ):
        """Auto-approve high-confidence classification."""
        self.db.execute(text("""
            UPDATE perennia_documents
            SET status = 'approved', updated_at = NOW()
            WHERE id = :id
        """), {"id": doc_id})
        self.db.commit()

        # Log event
        self.db.execute(text("""
            INSERT INTO perennia_document_events (
                document_id, loan_id, lead_id, request_id,
                event_type, event_data, actor_type, created_at
            ) VALUES (
                :doc_id, :loan_id, :lead_id, :request_id,
                'document_approved', :event_data, 'ai', NOW()
            )
        """), {
            "doc_id": doc_id,
            "loan_id": document.get('loan_id'),
            "lead_id": document.get('lead_id'),
            "request_id": document.get('request_id'),
            "event_data": {
                "auto_approved": True,
                "confidence": classification.confidence,
                "reason": "High confidence AI classification"
            }
        })
        self.db.commit()

        # Update request status if applicable
        if document.get('request_id'):
            self._update_request_status(document['request_id'])

    def _update_request_status(self, request_id: int):
        """Update request status based on approved documents."""
        result = self.db.execute(text("""
            SELECT dr.quantity,
                   COUNT(d.id) FILTER (WHERE d.status = 'approved') as approved_count
            FROM perennia_document_requests dr
            LEFT JOIN perennia_documents d ON d.request_id = dr.id
            WHERE dr.id = :request_id
            GROUP BY dr.id
        """), {"request_id": request_id})

        row = result.fetchone()
        if row and row[1] >= row[0]:
            self.db.execute(text("""
                UPDATE perennia_document_requests
                SET status = 'complete', updated_at = NOW()
                WHERE id = :id
            """), {"id": request_id})
            self.db.commit()

    def _mark_failed(self, doc_id: int, error: str):
        """Mark classification as failed."""
        self.db.execute(text("""
            UPDATE perennia_documents
            SET classification_status = 'failed',
                validation_errors = :errors,
                updated_at = NOW()
            WHERE id = :id
        """), {
            "id": doc_id,
            "errors": [f"Classification failed: {error}"]
        })
        self.db.commit()

    def run_batch(self, limit: int = None) -> Dict[str, Any]:
        """
        Process a batch of pending documents.

        Returns:
            Dict with batch processing results
        """
        documents = self.get_pending_documents(limit)

        results = {
            "processed": 0,
            "classified": 0,
            "auto_approved": 0,
            "failed": 0,
            "details": []
        }

        for doc in documents:
            classify_result = self.classify_document(doc)
            results["processed"] += 1
            results["details"].append(classify_result)

            if classify_result.get("success"):
                results["classified"] += 1
                if classify_result.get("auto_approved"):
                    results["auto_approved"] += 1
            else:
                results["failed"] += 1

        return results


def run_ai_triage(db: Session, batch_size: int = 5) -> Dict[str, Any]:
    """
    Run AI triage worker.

    Args:
        db: Database session
        batch_size: Number of documents to process

    Returns:
        Dict with processing results
    """
    worker = PerenniaTriageWorker(db)
    return worker.run_batch(batch_size)
