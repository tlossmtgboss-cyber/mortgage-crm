"""
Loan Estimate Parser Service

Parses loan estimates, fee worksheets, and closing disclosures into structured JSON.
Supports PDF (native text + scanned) and image uploads via AWS Textract OCR.

Pipeline:
1. File validation
2. Hash computation for caching
3. Cache lookup
4. Text extraction (PDF native or OCR)
5. Provenance snippet extraction
6. PII redaction
7. LLM normalization
8. Pydantic validation
9. Confidence scoring
10. Cache storage
"""

import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from io import BytesIO

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# PDF parsing
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    try:
        # PyPDF2 is the older name
        import PyPDF2 as pypdf
        HAS_PYPDF = True
    except ImportError:
        HAS_PYPDF = False

# Anthropic/OpenAI
try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB
MAX_PDF_PAGES = 25
MIN_TEXT_LENGTH = 100  # Minimum chars to consider extraction successful
OCR_TEXT_THRESHOLD = 200  # Below this, trigger OCR for PDFs

ALLOWED_MIME_TYPES = [
    'application/pdf',
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/webp',
]

# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class LoanCosts(BaseModel):
    origination_charges: Optional[float] = None
    services_you_cannot_shop_for: Optional[float] = None
    services_you_can_shop_for: Optional[float] = None


class OtherCosts(BaseModel):
    taxes: Optional[float] = None
    prepaids: Optional[float] = None
    escrow_and_other: Optional[float] = None


class CostBreakdown(BaseModel):
    loan_costs: Optional[LoanCosts] = None
    other_costs: Optional[OtherCosts] = None


class ProvenanceSnippets(BaseModel):
    """Snippets showing where key values came from in the document"""
    cash_to_close: Optional[str] = None
    total_closing_costs: Optional[str] = None
    loan_amount: Optional[str] = None
    interest_rate: Optional[str] = None
    apr: Optional[str] = None


class ParseMeta(BaseModel):
    """Metadata about the parse operation"""
    confidence: float = 0.0
    needs_review: bool = False
    confidence_reasons: List[str] = []
    provenance: Optional[ProvenanceSnippets] = None
    cached: bool = False
    request_id: Optional[str] = None
    elapsed_ms: Optional[int] = None
    source_type: Optional[str] = None


class LoanEstimate(BaseModel):
    """Normalized loan estimate data"""
    loan_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    apr: Optional[float] = None
    monthly_principal_and_interest: Optional[float] = None
    estimated_total_monthly_payment: Optional[float] = None
    total_closing_costs: Optional[float] = None
    cash_to_close: Optional[float] = None
    loan_term: Optional[int] = None  # in months
    loan_type: Optional[str] = None
    property_address: Optional[str] = None
    estimated_closing_date: Optional[str] = None
    lender_name: Optional[str] = None
    costs: Optional[CostBreakdown] = None
    meta: Optional[ParseMeta] = None

    @validator('interest_rate', 'apr', pre=True)
    def clean_percentage(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.replace('%', '').strip()
            try:
                return float(v)
            except ValueError:
                return None
        return float(v) if v else None

    @validator('loan_amount', 'monthly_principal_and_interest', 'estimated_total_monthly_payment',
               'total_closing_costs', 'cash_to_close', pre=True)
    def clean_currency(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.replace('$', '').replace(',', '').strip()
            try:
                return float(v)
            except ValueError:
                return None
        return float(v) if v else None


class ParseResult(BaseModel):
    """Result of parsing a document"""
    success: bool
    data: Optional[LoanEstimate] = None
    error: Optional[str] = None
    request_id: str


class ComparisonResult(BaseModel):
    """Result of comparing two estimates"""
    winner: Optional[str] = None  # 'A', 'B', or None
    reason: Optional[str] = None
    savings_amount: Optional[float] = None
    estimate_a: LoanEstimate
    estimate_b: LoanEstimate


# ============================================================================
# ESTIMATE PARSER SERVICE
# ============================================================================

class EstimateParserService:
    """Service for parsing loan estimates"""

    def __init__(self, db: Session):
        self.db = db
        self.request_id = str(uuid.uuid4())
        self.start_time = time.time()
        self.stages: List[Dict] = []

        # AWS clients
        self._textract_client = None
        self._s3_client = None

        # LLM clients
        self._anthropic_client = None
        self._openai_client = None

    @property
    def textract_client(self):
        if self._textract_client is None:
            self._textract_client = boto3.client(
                'textract',
                region_name=os.getenv('AWS_REGION', 'us-east-1'),
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            )
        return self._textract_client

    @property
    def s3_client(self):
        if self._s3_client is None:
            self._s3_client = boto3.client(
                's3',
                region_name=os.getenv('AWS_REGION', 'us-east-1'),
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            )
        return self._s3_client

    def log_stage(self, stage: str, data: Dict = None):
        """Log a pipeline stage for debugging"""
        entry = {
            'stage': stage,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'elapsed_ms': int((time.time() - self.start_time) * 1000),
            **(data or {})
        }
        self.stages.append(entry)
        logger.info(f"[{self.request_id}] {stage}: {json.dumps(data or {})}")

    # ========================================================================
    # MAIN PARSE METHOD
    # ========================================================================

    async def parse_estimate(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
    ) -> ParseResult:
        """
        Main entry point for parsing a loan estimate document.

        Args:
            file_content: Raw file bytes
            filename: Original filename
            mime_type: MIME type of the file

        Returns:
            ParseResult with success status and parsed data or error
        """
        self.log_stage('START', {'filename': filename, 'mime_type': mime_type, 'size': len(file_content)})

        try:
            # 1. Validate file
            validation_error = self._validate_file(file_content, mime_type)
            if validation_error:
                return ParseResult(success=False, error=validation_error, request_id=self.request_id)

            # 2. Compute hash
            doc_hash = self._compute_hash(file_content)
            self.log_stage('HASH', {'doc_hash': doc_hash})

            # 3. Check cache
            cached = self._check_cache(doc_hash)
            if cached:
                self.log_stage('CACHE_HIT', {'doc_hash': doc_hash})
                cached['meta']['cached'] = True
                cached['meta']['request_id'] = self.request_id
                cached['meta']['elapsed_ms'] = int((time.time() - self.start_time) * 1000)
                return ParseResult(
                    success=True,
                    data=LoanEstimate(**cached),
                    request_id=self.request_id
                )

            self.log_stage('CACHE_MISS', {'doc_hash': doc_hash})

            # 4. Extract text
            is_pdf = mime_type == 'application/pdf'
            raw_text, page_count = await self._extract_text(file_content, is_pdf)

            if len(raw_text.strip()) < MIN_TEXT_LENGTH:
                return ParseResult(
                    success=False,
                    error='Could not extract sufficient text from document. Please ensure the document is readable.',
                    request_id=self.request_id
                )

            # 5. Extract provenance snippets (before redaction)
            provenance = self._extract_provenance_snippets(raw_text)

            # 6. Redact PII
            redacted_text = self._redact_pii(raw_text)
            self.log_stage('REDACT', {'original_length': len(raw_text), 'redacted_length': len(redacted_text)})

            # 7. Detect source type
            source_type = self._detect_source_type(raw_text)
            self.log_stage('SOURCE_TYPE', {'type': source_type})

            # 8. LLM normalization
            parsed_data = await self._llm_normalize(redacted_text)
            if parsed_data is None:
                self._log_failure(doc_hash, 'llm', 'LLM returned empty response', redacted_text)
                return ParseResult(
                    success=False,
                    error='Unable to parse document structure. Please try a different format.',
                    request_id=self.request_id
                )

            # 9. Validate with Pydantic
            try:
                estimate = LoanEstimate(**parsed_data)
            except Exception as e:
                self._log_failure(doc_hash, 'validation', str(e), redacted_text)
                return ParseResult(
                    success=False,
                    error=f'Document validation failed: {str(e)}',
                    request_id=self.request_id
                )

            # 10. Calculate confidence
            confidence, needs_review, reasons = self._calculate_confidence(estimate, raw_text)

            # 11. Add metadata
            estimate.meta = ParseMeta(
                confidence=confidence,
                needs_review=needs_review,
                confidence_reasons=reasons,
                provenance=provenance,
                cached=False,
                request_id=self.request_id,
                elapsed_ms=int((time.time() - self.start_time) * 1000),
                source_type=source_type,
            )

            # 12. Store in cache
            self._store_cache(doc_hash, estimate, confidence, needs_review, source_type)

            self.log_stage('DONE', {'confidence': confidence, 'needs_review': needs_review})

            return ParseResult(
                success=True,
                data=estimate,
                request_id=self.request_id
            )

        except Exception as e:
            logger.exception(f"[{self.request_id}] Parse failed: {e}")
            return ParseResult(
                success=False,
                error=f'Internal error: {str(e)}',
                request_id=self.request_id
            )

    # ========================================================================
    # FILE VALIDATION
    # ========================================================================

    def _validate_file(self, content: bytes, mime_type: str) -> Optional[str]:
        """Validate file type and size"""
        self.log_stage('VALIDATE', {'mime_type': mime_type, 'size': len(content)})

        if mime_type not in ALLOWED_MIME_TYPES:
            return f'File type {mime_type} not supported. Please upload PDF or image (JPG, PNG, WebP).'

        if len(content) > MAX_FILE_SIZE:
            size_mb = len(content) / (1024 * 1024)
            return f'File too large ({size_mb:.1f}MB). Maximum size is 15MB.'

        return None

    def _compute_hash(self, content: bytes) -> str:
        """Compute SHA-256 hash of file content"""
        return hashlib.sha256(content).hexdigest()

    # ========================================================================
    # CACHE OPERATIONS
    # ========================================================================

    def _check_cache(self, doc_hash: str) -> Optional[Dict]:
        """Check if we have a cached parse for this document"""
        try:
            result = self.db.execute(text("""
                UPDATE estimate_parse_cache
                SET accessed_at = NOW(), access_count = access_count + 1
                WHERE doc_hash = :doc_hash
                RETURNING parsed_json, confidence_score, needs_review, source_type
            """), {'doc_hash': doc_hash})

            row = result.fetchone()
            if row:
                return row[0]  # parsed_json
            return None
        except SQLAlchemyError as e:
            logger.error(f"Cache lookup error: {e}")
            return None

    def _store_cache(
        self,
        doc_hash: str,
        estimate: LoanEstimate,
        confidence: float,
        needs_review: bool,
        source_type: str
    ):
        """Store parsed result in cache"""
        try:
            self.db.execute(text("""
                INSERT INTO estimate_parse_cache (
                    doc_hash, parsed_json, confidence_score, needs_review, source_type
                ) VALUES (
                    :doc_hash, :parsed_json, :confidence, :needs_review, :source_type
                )
                ON CONFLICT (doc_hash) DO UPDATE SET
                    parsed_json = EXCLUDED.parsed_json,
                    accessed_at = NOW(),
                    access_count = estimate_parse_cache.access_count + 1
            """), {
                'doc_hash': doc_hash,
                'parsed_json': json.dumps(estimate.dict()),
                'confidence': confidence,
                'needs_review': needs_review,
                'source_type': source_type,
            })
            self.db.commit()
            self.log_stage('CACHE_STORE', {'doc_hash': doc_hash})
        except SQLAlchemyError as e:
            logger.error(f"Cache storage error: {e}")
            self.db.rollback()

    def _log_failure(self, doc_hash: str, stage: str, error: str, raw_text: str):
        """Log a parse failure for review"""
        try:
            self.db.execute(text("""
                INSERT INTO estimate_parse_failures (
                    request_id, doc_hash, error_stage, error_message, raw_text
                ) VALUES (
                    :request_id, :doc_hash, :stage, :error, :raw_text
                )
            """), {
                'request_id': self.request_id,
                'doc_hash': doc_hash,
                'stage': stage,
                'error': error,
                'raw_text': raw_text[:10000],  # Truncate
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Failed to log failure: {e}")
            self.db.rollback()

    # ========================================================================
    # TEXT EXTRACTION
    # ========================================================================

    async def _extract_text(self, content: bytes, is_pdf: bool) -> Tuple[str, int]:
        """
        Extract text from document.
        For PDFs, try native extraction first, fall back to OCR if needed.
        For images, always use OCR.
        """
        if is_pdf:
            # Try native PDF text extraction
            text, page_count = self._extract_pdf_text(content)
            self.log_stage('EXTRACT_PDF', {'page_count': page_count, 'text_length': len(text)})

            if page_count > MAX_PDF_PAGES:
                raise ValueError(f'PDF has {page_count} pages. Maximum allowed is {MAX_PDF_PAGES} pages.')

            # Check if we need OCR (scanned PDF)
            if len(text.strip()) < OCR_TEXT_THRESHOLD and os.getenv('ENABLE_OCR', 'true').lower() == 'true':
                self.log_stage('OCR_TRIGGER', {'reason': 'scanned_pdf', 'native_text_length': len(text)})
                text = await self._ocr_document(content, is_pdf=True)

            return text, page_count
        else:
            # Image - always use OCR
            self.log_stage('OCR_TRIGGER', {'reason': 'image'})
            text = await self._ocr_document(content, is_pdf=False)
            return text, 1

    def _extract_pdf_text(self, content: bytes) -> Tuple[str, int]:
        """Extract text from PDF using pdfplumber or pypdf/PyPDF2"""
        text_parts = []
        page_count = 0

        if HAS_PDFPLUMBER:
            try:
                with pdfplumber.open(BytesIO(content)) as pdf:
                    page_count = len(pdf.pages)
                    for page in pdf.pages[:MAX_PDF_PAGES]:
                        page_text = page.extract_text() or ''
                        text_parts.append(page_text)
                return '\n'.join(text_parts), page_count
            except Exception as e:
                logger.warning(f"pdfplumber failed: {e}, trying pypdf/PyPDF2")

        if HAS_PYPDF:
            try:
                # pypdf 4.x uses PdfReader
                if hasattr(pypdf, 'PdfReader'):
                    reader = pypdf.PdfReader(BytesIO(content))
                    page_count = len(reader.pages)
                    for page in reader.pages[:MAX_PDF_PAGES]:
                        text_parts.append(page.extract_text() or '')
                # PyPDF2 older versions use PdfFileReader
                elif hasattr(pypdf, 'PdfFileReader'):
                    reader = pypdf.PdfFileReader(BytesIO(content))
                    page_count = reader.getNumPages()
                    for i in range(min(page_count, MAX_PDF_PAGES)):
                        page = reader.getPage(i)
                        text_parts.append(page.extract_text() or '')
                else:
                    logger.warning("No compatible PDF reader found in pypdf module")
                    return '', 0
                return '\n'.join(text_parts), page_count
            except Exception as e:
                logger.warning(f"pypdf/PyPDF2 failed: {e}")

        return '', 0

    async def _ocr_document(self, content: bytes, is_pdf: bool) -> str:
        """OCR document using AWS Textract"""
        if is_pdf:
            return await self._ocr_pdf_async(content)
        else:
            return self._ocr_image_sync(content)

    def _ocr_image_sync(self, content: bytes) -> str:
        """OCR image using synchronous Textract API"""
        try:
            response = self.textract_client.detect_document_text(
                Document={'Bytes': content}
            )

            lines = [
                block['Text']
                for block in response.get('Blocks', [])
                if block['BlockType'] == 'LINE'
            ]

            text = '\n'.join(lines)
            self.log_stage('OCR_COMPLETE', {'text_length': len(text)})
            return text

        except ClientError as e:
            logger.error(f"Textract sync OCR failed: {e}")
            raise

    async def _ocr_pdf_async(self, content: bytes) -> str:
        """OCR PDF using async Textract API via S3"""
        import asyncio

        bucket = os.getenv('TEXTRACT_S3_BUCKET')
        prefix = os.getenv('TEXTRACT_S3_PREFIX', 'textract/')

        if not bucket:
            raise ValueError("TEXTRACT_S3_BUCKET not configured")

        # Generate unique S3 key
        s3_key = f"{prefix}{self.request_id}.pdf"

        try:
            # Upload to S3
            self.s3_client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=content,
                ContentType='application/pdf'
            )
            self.log_stage('S3_UPLOAD', {'bucket': bucket, 'key': s3_key})

            # Start async Textract job
            response = self.textract_client.start_document_text_detection(
                DocumentLocation={
                    'S3Object': {
                        'Bucket': bucket,
                        'Name': s3_key
                    }
                },
                ClientRequestToken=self.request_id
            )
            job_id = response['JobId']
            self.log_stage('TEXTRACT_JOB_START', {'job_id': job_id})

            # Poll for completion
            max_attempts = 45
            poll_interval = 1.0

            for attempt in range(max_attempts):
                await asyncio.sleep(poll_interval)

                result = self.textract_client.get_document_text_detection(JobId=job_id)
                status = result['JobStatus']

                if status == 'SUCCEEDED':
                    # Extract text from all pages
                    all_text = self._extract_text_from_blocks(result.get('Blocks', []))

                    # Handle pagination
                    next_token = result.get('NextToken')
                    while next_token:
                        next_result = self.textract_client.get_document_text_detection(
                            JobId=job_id,
                            NextToken=next_token
                        )
                        all_text += self._extract_text_from_blocks(next_result.get('Blocks', []))
                        next_token = next_result.get('NextToken')

                    self.log_stage('OCR_COMPLETE', {'text_length': len(all_text), 'attempts': attempt + 1})
                    return all_text

                elif status == 'FAILED':
                    raise RuntimeError(f"Textract job failed: {result.get('StatusMessage')}")

                # Still IN_PROGRESS, continue polling

            raise TimeoutError("Textract OCR timeout after 45 seconds")

        finally:
            # Clean up S3 file (optional - lifecycle rule will also clean it)
            try:
                self.s3_client.delete_object(Bucket=bucket, Key=s3_key)
            except Exception as e:
                logger.warning(f"Error cleaning up S3 file {s3_key}: {e}")

    def _extract_text_from_blocks(self, blocks: List[Dict]) -> str:
        """Extract text from Textract blocks"""
        lines = [
            block['Text']
            for block in blocks
            if block.get('BlockType') == 'LINE'
        ]
        return '\n'.join(lines)

    # ========================================================================
    # PROVENANCE SNIPPETS
    # ========================================================================

    def _extract_provenance_snippets(self, raw_text: str) -> ProvenanceSnippets:
        """Extract snippets showing where key values came from"""
        snippets = ProvenanceSnippets()
        lines = raw_text.split('\n')

        def find_snippet(keywords: List[str], context_chars: int = 120) -> Optional[str]:
            for keyword in keywords:
                pattern = re.compile(keyword, re.IGNORECASE)

                for i, line in enumerate(lines):
                    if pattern.search(line):
                        # Get surrounding context
                        context_lines = lines[i:min(i + 3, len(lines))]
                        context_text = ' '.join(context_lines).strip()

                        # Extract window around match
                        match = pattern.search(context_text)
                        if match:
                            start = max(0, match.start() - 40)
                            end = min(len(context_text), match.end() + context_chars)
                            snippet = context_text[start:end].strip()

                            if start > 0:
                                snippet = '...' + snippet
                            if end < len(context_text):
                                snippet = snippet + '...'

                            return snippet
            return None

        snippets.cash_to_close = find_snippet([
            r'cash to close',
            r'cash from.+borrower',
            r'estimated cash to close'
        ])

        snippets.total_closing_costs = find_snippet([
            r'total closing costs',
            r'total loan costs',
            r'estimated closing costs'
        ])

        snippets.loan_amount = find_snippet([
            r'loan amount',
            r'sale price',
            r'base loan amount'
        ])

        snippets.interest_rate = find_snippet([
            r'interest rate',
            r'note rate',
            r'your interest rate'
        ])

        snippets.apr = find_snippet([
            r'annual percentage rate',
            r'\bAPR\b'
        ])

        self.log_stage('SNIPPETS', {
            'cash_to_close': bool(snippets.cash_to_close),
            'total_closing_costs': bool(snippets.total_closing_costs),
            'loan_amount': bool(snippets.loan_amount),
            'interest_rate': bool(snippets.interest_rate),
            'apr': bool(snippets.apr),
        })

        return snippets

    # ========================================================================
    # PII REDACTION
    # ========================================================================

    def _redact_pii(self, text: str) -> str:
        """Redact PII before sending to LLM"""
        redacted = text

        # Email addresses
        redacted = re.sub(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            '[EMAIL_REDACTED]',
            redacted
        )

        # Phone numbers
        redacted = re.sub(
            r'(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            '[PHONE_REDACTED]',
            redacted
        )

        # SSN patterns
        redacted = re.sub(r'\b\d{3}-?\d{2}-?\d{4}\b', '[SSN_REDACTED]', redacted)
        redacted = re.sub(r'\bXXX-XX-\d{4}\b', '[SSN_REDACTED]', redacted, flags=re.IGNORECASE)

        # Long digit sequences (account numbers) - but keep short ones for amounts/rates
        redacted = re.sub(r'\b\d{10,}\b', '[ACCOUNT_REDACTED]', redacted)

        # Street addresses (basic pattern)
        redacted = re.sub(
            r'\b\d{1,5}\s+[A-Za-z0-9\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Circle|Cir|Way)\b',
            '[ADDRESS_REDACTED]',
            redacted,
            flags=re.IGNORECASE
        )

        return redacted

    # ========================================================================
    # SOURCE TYPE DETECTION
    # ========================================================================

    def _detect_source_type(self, text: str) -> str:
        """Detect document type from content"""
        text_lower = text.lower()

        if 'closing disclosure' in text_lower:
            return 'closing_disclosure'
        elif 'loan estimate' in text_lower:
            return 'loan_estimate'
        elif 'fee worksheet' in text_lower or 'fee estimate' in text_lower:
            return 'fee_worksheet'
        elif 'good faith estimate' in text_lower:
            return 'good_faith_estimate'
        else:
            return 'unknown'

    # ========================================================================
    # LLM NORMALIZATION
    # ========================================================================

    async def _llm_normalize(self, redacted_text: str) -> Optional[Dict]:
        """Use LLM to normalize document text into structured JSON"""
        self.log_stage('LLM_START', {'text_length': len(redacted_text)})

        system_prompt = """You are a mortgage document parser. Extract loan estimate data into structured JSON.

CRITICAL RULES:
1. Return ONLY valid JSON, no markdown, no explanations
2. All currency values as numbers (no $ or commas)
3. All percentages as decimals (5.75% = 5.75, NOT 0.0575)
4. If field not found, use null
5. Preserve exact numbers from document

Required fields to extract:
- loan_amount: Total loan amount
- interest_rate: Interest rate as percentage (e.g., 6.875)
- apr: Annual percentage rate if available
- monthly_principal_and_interest: Monthly P&I payment
- estimated_total_monthly_payment: Including taxes, insurance, HOA if shown
- total_closing_costs: Section J total or equivalent
- cash_to_close: Section H or equivalent cash needed
- loan_term: In months (360 for 30-year, 180 for 15-year)
- loan_type: e.g., "Conventional", "FHA", "VA", "USDA"
- property_address: If shown (can be null)
- estimated_closing_date: If shown (can be null)
- lender_name: If shown (can be null)

Optional nested costs:
- costs.loan_costs.origination_charges
- costs.loan_costs.services_you_cannot_shop_for
- costs.loan_costs.services_you_can_shop_for
- costs.other_costs.taxes
- costs.other_costs.prepaids
- costs.other_costs.escrow_and_other

Output format example:
{
  "loan_amount": 400000,
  "interest_rate": 6.875,
  "apr": 7.125,
  "monthly_principal_and_interest": 2632,
  "estimated_total_monthly_payment": 3450,
  "total_closing_costs": 12500,
  "cash_to_close": 65000,
  "loan_term": 360,
  "loan_type": "Conventional",
  "property_address": null,
  "estimated_closing_date": null,
  "lender_name": "ABC Mortgage",
  "costs": {
    "loan_costs": {
      "origination_charges": 2500,
      "services_you_cannot_shop_for": 1200,
      "services_you_can_shop_for": 3500
    },
    "other_costs": {
      "taxes": 850,
      "prepaids": 3200,
      "escrow_and_other": 1250
    }
  }
}"""

        user_prompt = f"Parse this loan estimate document:\n\n{redacted_text[:15000]}"  # Truncate for token limits

        max_attempts = 2
        last_error = None

        for attempt in range(max_attempts):
            try:
                response = await self._call_llm(system_prompt, user_prompt)

                if not response:
                    continue

                # Clean and parse JSON
                cleaned = self._clean_json_response(response)
                parsed = json.loads(cleaned)

                self.log_stage('LLM_SUCCESS', {'attempt': attempt + 1})
                return parsed

            except json.JSONDecodeError as e:
                last_error = str(e)
                self.log_stage('LLM_JSON_ERROR', {'attempt': attempt + 1, 'error': str(e)})

                # On first failure, try repair prompt
                if attempt == 0 and os.getenv('ENABLE_LLM_REPAIR', 'true').lower() == 'true':
                    user_prompt = f"""The previous JSON was invalid. Error: {e}

Please output ONLY valid JSON with no additional text.

Original document:
{redacted_text[:10000]}"""

            except Exception as e:
                last_error = str(e)
                self.log_stage('LLM_ERROR', {'attempt': attempt + 1, 'error': str(e)})

        self.log_stage('LLM_FAILED', {'attempts': max_attempts, 'last_error': last_error})
        return None

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Call LLM provider (Anthropic or OpenAI)"""
        provider = os.getenv('LLM_PROVIDER', 'anthropic').lower()

        if provider == 'anthropic' and HAS_ANTHROPIC:
            return await self._call_anthropic(system_prompt, user_prompt)
        elif provider == 'openai' and HAS_OPENAI:
            return await self._call_openai(system_prompt, user_prompt)
        else:
            # Default to Anthropic if available
            if HAS_ANTHROPIC:
                return await self._call_anthropic(system_prompt, user_prompt)
            elif HAS_OPENAI:
                return await self._call_openai(system_prompt, user_prompt)
            else:
                raise RuntimeError("No LLM provider available. Install anthropic or openai package.")

    async def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        """Call Anthropic Claude"""
        if self._anthropic_client is None:
            self._anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY') or os.getenv('LLM_API_KEY'))

        model = os.getenv('LLM_MODEL', 'claude-sonnet-4-20250514')

        message = self._anthropic_client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{'role': 'user', 'content': user_prompt}]
        )

        return message.content[0].text

    async def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI GPT"""
        if self._openai_client is None:
            self._openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY') or os.getenv('LLM_API_KEY'))

        model = os.getenv('LLM_MODEL', 'gpt-4o-mini')

        response = self._openai_client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            temperature=0
        )

        return response.choices[0].message.content

    def _clean_json_response(self, text: str) -> str:
        """Clean LLM response to extract JSON"""
        # Remove markdown code fences
        cleaned = re.sub(r'```json\s*', '', text)
        cleaned = re.sub(r'```\s*', '', cleaned)

        # Remove common preambles
        cleaned = re.sub(r'^Here is the JSON.*?:', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^The JSON output.*?:', '', cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    # ========================================================================
    # CONFIDENCE SCORING
    # ========================================================================

    def _calculate_confidence(
        self,
        estimate: LoanEstimate,
        raw_text: str
    ) -> Tuple[float, bool, List[str]]:
        """Calculate confidence score for parsed estimate"""
        score = 1.0
        reasons = []

        # Critical fields (50% weight)
        critical_fields = ['loan_amount', 'interest_rate', 'monthly_principal_and_interest', 'total_closing_costs']
        critical_missing = 0

        for field in critical_fields:
            if getattr(estimate, field, None) is None:
                critical_missing += 1
                reasons.append(f'Missing critical field: {field}')

        if critical_missing > 0:
            score -= 0.5 * (critical_missing / len(critical_fields))

        # Important fields (30% weight)
        if estimate.apr is None:
            score -= 0.15
            reasons.append('Missing APR')

        if estimate.cash_to_close is None:
            score -= 0.15
            reasons.append('Missing Cash to Close')

        # Text quality (20% weight)
        if len(raw_text) < 500:
            score -= 0.1
            reasons.append('Low text extraction quality')

        # Sanity checks
        if estimate.loan_amount and estimate.loan_amount < 10000:
            score -= 0.1
            reasons.append('Unusually low loan amount')

        if estimate.interest_rate and estimate.interest_rate > 20:
            score -= 0.1
            reasons.append('Unusually high interest rate')

        if estimate.cash_to_close and estimate.loan_amount:
            if estimate.cash_to_close > estimate.loan_amount * 1.5:
                score -= 0.1
                reasons.append('Cash to close exceeds loan amount significantly')

        # Clamp score
        score = max(0.0, min(1.0, score))
        needs_review = score < 0.7

        if not reasons:
            reasons.append('Confidence acceptable')

        return round(score, 2), needs_review, reasons

    # ========================================================================
    # COMPARISON
    # ========================================================================

    def compare_estimates(
        self,
        estimate_a: LoanEstimate,
        estimate_b: LoanEstimate
    ) -> ComparisonResult:
        """
        Compare two estimates and determine winner.
        Priority: Cash to Close > Total Closing Costs > APR > P&I
        """
        winner = None
        reason = None
        savings = None

        # 1. Cash to Close
        if estimate_a.cash_to_close and estimate_b.cash_to_close:
            delta = abs(estimate_a.cash_to_close - estimate_b.cash_to_close)
            if estimate_a.cash_to_close < estimate_b.cash_to_close:
                winner = 'A'
                reason = 'Lower cash required at closing'
                savings = delta
            elif estimate_b.cash_to_close < estimate_a.cash_to_close:
                winner = 'B'
                reason = 'Lower cash required at closing'
                savings = delta

        # 2. Total Closing Costs
        if winner is None and estimate_a.total_closing_costs and estimate_b.total_closing_costs:
            delta = abs(estimate_a.total_closing_costs - estimate_b.total_closing_costs)
            if estimate_a.total_closing_costs < estimate_b.total_closing_costs:
                winner = 'A'
                reason = 'Lower closing costs'
                savings = delta
            elif estimate_b.total_closing_costs < estimate_a.total_closing_costs:
                winner = 'B'
                reason = 'Lower closing costs'
                savings = delta

        # 3. APR
        if winner is None and estimate_a.apr and estimate_b.apr:
            if estimate_a.apr < estimate_b.apr:
                winner = 'A'
                reason = 'Lower APR (better long-term cost)'
            elif estimate_b.apr < estimate_a.apr:
                winner = 'B'
                reason = 'Lower APR (better long-term cost)'

        # 4. Monthly P&I
        if winner is None:
            a_pi = estimate_a.monthly_principal_and_interest
            b_pi = estimate_b.monthly_principal_and_interest
            if a_pi and b_pi:
                if a_pi < b_pi:
                    winner = 'A'
                    reason = 'Lower monthly payment'
                elif b_pi < a_pi:
                    winner = 'B'
                    reason = 'Lower monthly payment'

        return ComparisonResult(
            winner=winner,
            reason=reason,
            savings_amount=savings,
            estimate_a=estimate_a,
            estimate_b=estimate_b
        )

    # ========================================================================
    # PDF GENERATION
    # ========================================================================

    def generate_comparison_pdf(
        self,
        comparison: ComparisonResult,
        comparison_id: str,
    ) -> bytes:
        """
        Generate a PDF report for a comparison result.
        Uses reportlab for PDF generation.
        """
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)

        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontSize=24,
            alignment=TA_CENTER,
            spaceAfter=12,
            textColor=colors.HexColor('#1e293b')
        )

        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Normal'],
            fontSize=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#64748b'),
            spaceAfter=24
        )

        section_header = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1e293b'),
            spaceBefore=16,
            spaceAfter=8
        )

        winner_style = ParagraphStyle(
            'Winner',
            parent=styles['Normal'],
            fontSize=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#166534'),
            backColor=colors.HexColor('#f0fdf4'),
            borderPadding=12,
            spaceAfter=16
        )

        story = []

        # Title
        story.append(Paragraph("Loan Estimate Comparison Report", title_style))
        story.append(Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", subtitle_style))

        # Winner section
        if comparison.winner:
            winner_text = f"<b>Best Option: Estimate {comparison.winner}</b><br/>{comparison.reason}"
            if comparison.savings_amount:
                winner_text += f"<br/>Potential Savings: ${comparison.savings_amount:,.0f}"
            story.append(Paragraph(winner_text, winner_style))
            story.append(Spacer(1, 12))

        # Helper function to format values
        def fmt_currency(val):
            if val is None:
                return '—'
            return f"${val:,.0f}"

        def fmt_percent(val):
            if val is None:
                return '—'
            return f"{val:.3f}%"

        # Comparison table
        story.append(Paragraph("Side-by-Side Comparison", section_header))

        est_a = comparison.estimate_a
        est_b = comparison.estimate_b

        table_data = [
            ['', 'Estimate A', 'Estimate B', 'Difference'],
            ['Cash to Close', fmt_currency(est_a.cash_to_close if est_a else None),
             fmt_currency(est_b.cash_to_close if est_b else None),
             fmt_currency(abs(est_a.cash_to_close - est_b.cash_to_close)) if est_a and est_b and est_a.cash_to_close and est_b.cash_to_close else '—'],
            ['Total Closing Costs', fmt_currency(est_a.total_closing_costs if est_a else None),
             fmt_currency(est_b.total_closing_costs if est_b else None),
             fmt_currency(abs(est_a.total_closing_costs - est_b.total_closing_costs)) if est_a and est_b and est_a.total_closing_costs and est_b.total_closing_costs else '—'],
            ['APR', fmt_percent(est_a.apr if est_a else None),
             fmt_percent(est_b.apr if est_b else None),
             fmt_percent(abs(est_a.apr - est_b.apr)) if est_a and est_b and est_a.apr and est_b.apr else '—'],
            ['Interest Rate', fmt_percent(est_a.interest_rate if est_a else None),
             fmt_percent(est_b.interest_rate if est_b else None),
             fmt_percent(abs(est_a.interest_rate - est_b.interest_rate)) if est_a and est_b and est_a.interest_rate and est_b.interest_rate else '—'],
            ['Monthly P&I', fmt_currency(est_a.monthly_principal_and_interest if est_a else None),
             fmt_currency(est_b.monthly_principal_and_interest if est_b else None),
             fmt_currency(abs(est_a.monthly_principal_and_interest - est_b.monthly_principal_and_interest)) if est_a and est_b and est_a.monthly_principal_and_interest and est_b.monthly_principal_and_interest else '—'],
            ['Loan Amount', fmt_currency(est_a.loan_amount if est_a else None),
             fmt_currency(est_b.loan_amount if est_b else None),
             '—'],
        ]

        # Determine which column is the winner
        winner_col = 1 if comparison.winner == 'A' else (2 if comparison.winner == 'B' else None)

        table = Table(table_data, colWidths=[2*inch, 1.5*inch, 1.5*inch, 1.5*inch])

        # Table styling
        table_style = TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#64748b')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

            # All cells
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 10),

            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),

            # Row backgrounds
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ])

        # Highlight winner column
        if winner_col:
            for row in range(1, len(table_data)):
                table_style.add('TEXTCOLOR', (winner_col, row), (winner_col, row), colors.HexColor('#10b981'))
                table_style.add('FONTNAME', (winner_col, row), (winner_col, row), 'Helvetica-Bold')

        table.setStyle(table_style)
        story.append(table)

        # Individual estimates details
        if est_a:
            story.append(Spacer(1, 20))
            story.append(Paragraph("Estimate A Details", section_header))
            if est_a.loan_type:
                story.append(Paragraph(f"<b>Loan Type:</b> {est_a.loan_type}", styles['Normal']))
            if est_a.loan_term:
                story.append(Paragraph(f"<b>Loan Term:</b> {est_a.loan_term}", styles['Normal']))

        if est_b:
            story.append(Spacer(1, 20))
            story.append(Paragraph("Estimate B Details", section_header))
            if est_b.loan_type:
                story.append(Paragraph(f"<b>Loan Type:</b> {est_b.loan_type}", styles['Normal']))
            if est_b.loan_term:
                story.append(Paragraph(f"<b>Loan Term:</b> {est_b.loan_term}", styles['Normal']))

        # Footer
        story.append(Spacer(1, 30))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#94a3b8'),
            alignment=TA_CENTER
        )
        story.append(Paragraph(
            "This comparison is for informational purposes only. Actual loan terms may vary.<br/>"
            f"Comparison ID: {comparison_id}",
            footer_style
        ))

        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
