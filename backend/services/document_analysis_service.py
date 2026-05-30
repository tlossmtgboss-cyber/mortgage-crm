"""
Document Analysis Service - AI-powered document verification using Claude Vision.

Analyzes uploaded documents to:
- Verify document type matches what user claimed
- Extract key information (names, dates, amounts)
- Detect potential issues or fraud indicators
- Auto-categorize documents
"""

import os
import json
import logging
import base64
import httpx
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Claude API configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-sonnet-4-6"  # Use latest Claude with vision


class DocumentAnalysisResult:
    """Result from document analysis."""

    def __init__(
        self,
        verified: bool,
        confidence: float,
        document_type: str,
        extracted_data: Dict[str, Any],
        issues: List[str],
        suggestions: List[str],
        raw_analysis: str,
    ):
        self.verified = verified
        self.confidence = confidence
        self.document_type = document_type
        self.extracted_data = extracted_data
        self.issues = issues
        self.suggestions = suggestions
        self.raw_analysis = raw_analysis

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "confidence": self.confidence,
            "document_type": self.document_type,
            "extracted_data": self.extracted_data,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "analysis_summary": self.raw_analysis[:500] if self.raw_analysis else None,
        }


class DocumentAnalysisService:
    """Service for AI-powered document analysis."""

    # Document type definitions for verification
    DOCUMENT_TYPES = {
        "paystub": {
            "description": "Pay stub or earnings statement",
            "required_fields": ["employer_name", "employee_name", "pay_period", "gross_pay", "net_pay"],
            "optional_fields": ["ytd_earnings", "deductions", "pay_date"],
        },
        "w2": {
            "description": "W-2 Wage and Tax Statement",
            "required_fields": ["employer_name", "employer_ein", "employee_name", "employee_ssn_last4", "wages", "tax_year"],
            "optional_fields": ["federal_tax_withheld", "state_tax_withheld", "social_security_wages"],
        },
        "bank_statement": {
            "description": "Bank account statement",
            "required_fields": ["bank_name", "account_holder", "statement_period", "ending_balance"],
            "optional_fields": ["account_number_last4", "deposits", "withdrawals", "average_balance"],
        },
        "tax_return": {
            "description": "Tax return (1040, 1040-SR, etc.)",
            "required_fields": ["tax_year", "taxpayer_name", "filing_status", "adjusted_gross_income"],
            "optional_fields": ["taxable_income", "total_tax", "refund_amount"],
        },
        "drivers_license": {
            "description": "Driver's license or state ID",
            "required_fields": ["full_name", "date_of_birth", "expiration_date", "state"],
            "optional_fields": ["license_number_last4", "address"],
        },
        "utility_bill": {
            "description": "Utility bill (electric, gas, water)",
            "required_fields": ["service_provider", "account_holder", "service_address", "bill_date"],
            "optional_fields": ["amount_due", "due_date"],
        },
        "property_insurance": {
            "description": "Homeowner's or property insurance declaration",
            "required_fields": ["insurance_company", "policyholder", "property_address", "coverage_amount"],
            "optional_fields": ["policy_number", "effective_date", "premium"],
        },
        "1099": {
            "description": "1099 tax form (various types)",
            "required_fields": ["payer_name", "recipient_name", "tax_year", "amount"],
            "optional_fields": ["payer_tin", "recipient_tin_last4", "form_type"],
        },
        "purchase_contract": {
            "description": "Real estate purchase agreement",
            "required_fields": ["property_address", "purchase_price", "buyer_name", "seller_name"],
            "optional_fields": ["closing_date", "earnest_money", "contingencies"],
        },
        "gift_letter": {
            "description": "Gift letter for down payment funds",
            "required_fields": ["donor_name", "recipient_name", "gift_amount", "relationship"],
            "optional_fields": ["donor_address", "date_signed", "no_repayment_statement"],
        },
        "mortgage_statement": {
            "description": "Monthly mortgage statement or escrow statement",
            "required_fields": ["lender_name", "property_address", "principal_balance", "monthly_payment"],
            "optional_fields": [
                "interest_rate", "loan_number", "maturity_date", "original_loan_date",
                "escrow_balance", "principal_and_interest", "property_taxes", "insurance",
                "hoa_dues", "pmi", "statement_date", "next_payment_due"
            ],
        },
    }

    def __init__(self):
        if not ANTHROPIC_API_KEY:
            logger.warning("Anthropic API key not configured - document analysis disabled")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("Document analysis service initialized")

    async def analyze_document(
        self,
        file_path: str,
        claimed_type: Optional[str] = None,
        borrower_name: Optional[str] = None,
        additional_context: Optional[str] = None,
    ) -> DocumentAnalysisResult:
        """
        Analyze a document using Claude Vision.

        Args:
            file_path: Path to the document file
            claimed_type: What type of document the user claims this is
            borrower_name: Expected borrower name for verification
            additional_context: Any additional context for analysis

        Returns:
            DocumentAnalysisResult with verification status and extracted data
        """
        if not self.enabled:
            return DocumentAnalysisResult(
                verified=False,
                confidence=0,
                document_type="unknown",
                extracted_data={},
                issues=["Document analysis service not configured"],
                suggestions=["Contact support to enable document verification"],
                raw_analysis="",
            )

        try:
            # Read and encode the file
            file_path = Path(file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"Document not found: {file_path}")

            # Determine media type
            suffix = file_path.suffix.lower()
            media_type_map = {
                ".pdf": "application/pdf",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }

            media_type = media_type_map.get(suffix)
            if not media_type:
                raise ValueError(f"Unsupported file type: {suffix}")

            # Read and encode file
            with open(file_path, "rb") as f:
                file_content = base64.standard_b64encode(f.read()).decode("utf-8")

            # Build the analysis prompt
            prompt = self._build_analysis_prompt(claimed_type, borrower_name, additional_context)

            # Call Claude API
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": CLAUDE_MODEL,
                        "max_tokens": 2000,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": media_type,
                                            "data": file_content,
                                        },
                                    },
                                    {
                                        "type": "text",
                                        "text": prompt,
                                    },
                                ],
                            }
                        ],
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Claude API error: {response.status_code} - {response.text}")
                    raise Exception(f"Claude API error: {response.status_code}")

                result = response.json()
                analysis_text = result["content"][0]["text"]

            # Parse the analysis
            return self._parse_analysis(analysis_text, claimed_type)

        except Exception as e:
            logger.error(f"Document analysis failed: {e}")
            return DocumentAnalysisResult(
                verified=False,
                confidence=0,
                document_type="error",
                extracted_data={},
                issues=[f"Analysis failed: {str(e)}"],
                suggestions=["Please try uploading the document again"],
                raw_analysis="",
            )

    def _build_analysis_prompt(
        self,
        claimed_type: Optional[str],
        borrower_name: Optional[str],
        additional_context: Optional[str],
    ) -> str:
        """Build the analysis prompt for Claude."""

        type_info = ""
        if claimed_type and claimed_type in self.DOCUMENT_TYPES:
            doc_def = self.DOCUMENT_TYPES[claimed_type]
            type_info = f"""
The user claims this is a: {doc_def['description']}
Expected fields to find: {', '.join(doc_def['required_fields'])}
"""

        name_info = ""
        if borrower_name:
            name_info = f"The expected borrower/account holder name is: {borrower_name}"

        context_info = ""
        if additional_context:
            context_info = f"Additional context: {additional_context}"

        return f"""Analyze this document for a mortgage application. Provide a structured analysis.

{type_info}
{name_info}
{context_info}

Please respond in the following JSON format:
{{
    "document_type": "the actual type of document you see",
    "confidence": 0.0 to 1.0,
    "verified": true if it appears to be a legitimate document of the claimed type,
    "extracted_data": {{
        // key-value pairs of data you can extract from the document
        // for amounts, use numbers not strings
        // for dates, use YYYY-MM-DD format
    }},
    "issues": [
        // list of any problems or concerns with the document
        // e.g., "Name on document doesn't match borrower name"
        // e.g., "Document appears to be expired"
        // e.g., "Image quality too low to verify details"
    ],
    "suggestions": [
        // list of suggestions for the borrower
        // e.g., "Please upload a clearer image"
        // e.g., "Please provide the complete document (all pages)"
    ],
    "summary": "Brief 1-2 sentence summary of what this document shows"
}}

Be thorough but concise. Focus on information relevant to mortgage underwriting.
If you cannot read or verify something clearly, note it as an issue.
Watch for signs of document tampering or inconsistencies."""

    def _parse_analysis(self, analysis_text: str, claimed_type: Optional[str]) -> DocumentAnalysisResult:
        """Parse Claude's analysis response."""
        try:
            # Try to extract JSON from the response
            # Claude might wrap it in markdown code blocks
            json_text = analysis_text

            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            data = json.loads(json_text.strip())

            return DocumentAnalysisResult(
                verified=data.get("verified", False),
                confidence=float(data.get("confidence", 0)),
                document_type=data.get("document_type", "unknown"),
                extracted_data=data.get("extracted_data", {}),
                issues=data.get("issues", []),
                suggestions=data.get("suggestions", []),
                raw_analysis=data.get("summary", ""),
            )

        except json.JSONDecodeError:
            # If we can't parse JSON, extract what we can from free text
            logger.warning("Could not parse JSON from Claude response, using fallback parsing")

            return DocumentAnalysisResult(
                verified=False,
                confidence=0.5,
                document_type=claimed_type or "unknown",
                extracted_data={},
                issues=["Analysis format was unexpected - manual review recommended"],
                suggestions=["Please have a loan officer review this document"],
                raw_analysis=analysis_text[:500],
            )

    async def batch_analyze(
        self,
        documents: List[Tuple[str, str]],  # List of (file_path, claimed_type)
        borrower_name: Optional[str] = None,
    ) -> Dict[str, DocumentAnalysisResult]:
        """
        Analyze multiple documents.

        Args:
            documents: List of (file_path, claimed_type) tuples
            borrower_name: Expected borrower name for all documents

        Returns:
            Dict mapping file paths to analysis results
        """
        import asyncio

        results = {}

        # Process in parallel with rate limiting
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent requests

        async def analyze_with_limit(file_path: str, claimed_type: str):
            async with semaphore:
                return file_path, await self.analyze_document(
                    file_path=file_path,
                    claimed_type=claimed_type,
                    borrower_name=borrower_name,
                )

        tasks = [
            analyze_with_limit(file_path, claimed_type)
            for file_path, claimed_type in documents
        ]

        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for result in completed:
            if isinstance(result, Exception):
                logger.error(f"Batch analysis error: {result}")
            else:
                file_path, analysis = result
                results[file_path] = analysis

        return results

    def get_document_checklist(self, loan_type: str = "conventional") -> List[Dict[str, Any]]:
        """
        Get required document checklist based on loan type.

        Args:
            loan_type: Type of loan (conventional, fha, va, etc.)

        Returns:
            List of required documents with descriptions
        """
        base_docs = [
            {
                "type": "drivers_license",
                "description": "Government-issued photo ID",
                "required": True,
            },
            {
                "type": "paystub",
                "description": "Most recent 30 days of pay stubs",
                "required": True,
                "quantity": "Most recent month",
            },
            {
                "type": "w2",
                "description": "W-2 forms for past 2 years",
                "required": True,
                "quantity": "Last 2 years",
            },
            {
                "type": "bank_statement",
                "description": "Bank statements for past 2 months",
                "required": True,
                "quantity": "Last 2 months",
            },
            {
                "type": "tax_return",
                "description": "Tax returns for past 2 years (if self-employed)",
                "required": False,
                "condition": "Required if self-employed",
            },
        ]

        # Add loan-type specific documents
        if loan_type == "va":
            base_docs.append({
                "type": "dd214",
                "description": "DD-214 or Certificate of Eligibility",
                "required": True,
            })
        elif loan_type == "fha":
            pass  # FHA uses similar base docs

        return base_docs


    async def parse_mortgage_statement(
        self,
        file_path: str,
        borrower_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parse a mortgage statement to extract key information for refinance applications.

        This specialized method extracts data commonly needed for refinance applications:
        - Property address
        - Current mortgage balance
        - Monthly payment breakdown
        - Interest rate
        - Original loan date
        - Lender information

        Args:
            file_path: Path to the mortgage statement file (PDF or image)
            borrower_name: Optional borrower name to verify against document

        Returns:
            Dict with parsed mortgage information ready for form population
        """
        if not self.enabled:
            return {
                "success": False,
                "error": "Document analysis service not configured",
                "data": {}
            }

        try:
            # Read and encode the file
            file_path = Path(file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"Document not found: {file_path}")

            suffix = file_path.suffix.lower()

            # Handle PDFs by converting to image first (Claude Vision only accepts images)
            if suffix == ".pdf":
                try:
                    from pdf2image import convert_from_path
                    import io

                    # Convert first page of PDF to image
                    images = convert_from_path(file_path, first_page=1, last_page=1, dpi=150)
                    if not images:
                        raise ValueError("Could not convert PDF to image")

                    # Convert PIL image to bytes
                    img_buffer = io.BytesIO()
                    images[0].save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                    file_content = base64.standard_b64encode(img_buffer.read()).decode("utf-8")
                    media_type = "image/png"

                except ImportError:
                    logger.warning("pdf2image not available, trying alternative PDF handling")
                    raise ValueError("PDF processing requires poppler to be installed")
            else:
                media_type_map = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                }

                media_type = media_type_map.get(suffix)
                if not media_type:
                    raise ValueError(f"Unsupported file type: {suffix}")

                with open(file_path, "rb") as f:
                    file_content = base64.standard_b64encode(f.read()).decode("utf-8")

            # Build specialized prompt for mortgage statements
            prompt = f"""Analyze this mortgage statement and extract the following information for a refinance application.

{f"Expected borrower name: {borrower_name}" if borrower_name else ""}

Please extract and return a JSON response with this exact structure:
{{
    "success": true,
    "confidence": 0.0 to 1.0,
    "data": {{
        "property_address": "Full property address",
        "property_street": "Street address only",
        "property_city": "City",
        "property_state": "State abbreviation (e.g., CA)",
        "property_zip": "ZIP code",
        "lender_name": "Name of the mortgage company/servicer",
        "loan_number": "Last 4 digits only for security",
        "principal_balance": 0.00,
        "monthly_payment": 0.00,
        "principal_and_interest": 0.00,
        "escrow_payment": 0.00,
        "property_taxes_monthly": 0.00,
        "homeowners_insurance_monthly": 0.00,
        "pmi_monthly": 0.00,
        "hoa_monthly": 0.00,
        "interest_rate": 0.000,
        "original_loan_date": "YYYY-MM-DD or YYYY-MM if day unknown",
        "loan_term_years": 30,
        "maturity_date": "YYYY-MM-DD",
        "escrow_balance": 0.00,
        "statement_date": "YYYY-MM-DD",
        "next_payment_due": "YYYY-MM-DD"
    }},
    "borrower_name_matches": true or false or null if cannot verify,
    "warnings": ["list of any issues or uncertainties"],
    "document_type_verified": true if this appears to be a valid mortgage statement
}}

Important:
- For amounts, use numbers without currency symbols or commas (e.g., 350000.00 not "$350,000")
- For interest rate, use decimal format (e.g., 6.5 not "6.5%")
- If a field cannot be found, use null
- Include any warnings about data quality or uncertainty
- Verify this is actually a mortgage statement and not another document type"""

            # Call Claude API
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": CLAUDE_MODEL,
                        "max_tokens": 2000,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": media_type,
                                            "data": file_content,
                                        },
                                    },
                                    {
                                        "type": "text",
                                        "text": prompt,
                                    },
                                ],
                            }
                        ],
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Claude API error: {response.status_code} - {response.text}")
                    raise Exception(f"Claude API error: {response.status_code}")

                result = response.json()
                analysis_text = result["content"][0]["text"]

            # Parse the response
            json_text = analysis_text

            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            parsed = json.loads(json_text.strip())

            # Add metadata
            parsed["parsed_at"] = datetime.now().isoformat()
            parsed["source_file"] = str(file_path.name)

            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse mortgage statement response: {e}")
            return {
                "success": False,
                "error": "Could not parse document analysis response",
                "raw_response": analysis_text[:500] if 'analysis_text' in locals() else None,
                "data": {}
            }
        except Exception as e:
            logger.error(f"Mortgage statement parsing failed: {e}")
            return {
                "success": False,
                "error": "Internal server error",
                "data": {}
            }


# Create singleton instance
document_analysis_service = DocumentAnalysisService()
