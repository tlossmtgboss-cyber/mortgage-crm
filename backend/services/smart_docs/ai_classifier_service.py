"""
AI Document Classifier Service

AI-powered document classification for mortgage documents.
Uses Claude API (Anthropic) for intelligent classification with a robust
rule-based fallback when the AI API is unavailable.

Classifies documents into mortgage-specific DocType categories with
confidence scores, alternative predictions, and detected features.

Usage:
    from services.smart_docs.ai_classifier_service import get_ai_classifier_service

    service = get_ai_classifier_service()
    result = service.classify_document(file_bytes, "application/pdf", "paystub_jan.pdf")
    print(result.predicted_type, result.confidence)
"""

import base64
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

from models.smart_docs_models import DocType
from services.smart_docs.ai_resilience import resilient_ai_call

logger = logging.getLogger(__name__)


# =============================================================================
# CLASSIFICATION RESULT
# =============================================================================

@dataclass
class ClassificationResult:
    """Result of AI document classification."""
    predicted_type: str  # DocType value
    confidence: int  # 0-100
    alternatives: List[Dict]  # [{"type": "W2", "confidence": 85}, ...]
    features_detected: Dict  # {"has_employer": True, "has_pay_period": True, ...}
    text_snippet: str  # OCR text used (first 1000 chars)
    model_used: str
    duration_ms: int
    success: bool = True
    error: Optional[str] = None


# =============================================================================
# KEYWORD DICTIONARIES FOR RULE-BASED CLASSIFICATION
# =============================================================================

# Each key is a DocType value, each value is a list of (keyword_or_phrase, weight) tuples.
# Weight indicates how strongly the keyword suggests that document type.
# Phrases are matched case-insensitively against the document text.
KEYWORD_RULES: Dict[str, List[Tuple[str, int]]] = {
    DocType.PAYSTUB.value: [
        ("pay period", 15),
        ("pay date", 12),
        ("gross pay", 15),
        ("net pay", 15),
        ("ytd", 12),
        ("year to date", 12),
        ("year-to-date", 12),
        ("payroll", 10),
        ("earnings statement", 15),
        ("earnings summary", 12),
        ("pay stub", 20),
        ("paystub", 20),
        ("pay statement", 15),
        ("hours worked", 8),
        ("regular hours", 8),
        ("overtime", 6),
        ("deductions", 8),
        ("federal withholding", 10),
        ("state withholding", 8),
        ("fica", 8),
        ("social security tax", 8),
        ("medicare tax", 8),
        ("401k", 5),
        ("check number", 6),
        ("direct deposit", 5),
        ("employee id", 6),
        ("pay rate", 8),
        ("hourly rate", 6),
        ("salary", 4),
        ("current period", 6),
    ],
    DocType.W2.value: [
        ("wage and tax statement", 25),
        ("wage and tax", 20),
        ("form w-2", 25),
        ("form w2", 25),
        ("w-2", 20),
        ("employer identification number", 15),
        ("ein", 8),
        ("wages, tips, other compensation", 18),
        ("federal income tax withheld", 15),
        ("social security wages", 12),
        ("medicare wages and tips", 12),
        ("social security tax withheld", 10),
        ("medicare tax withheld", 10),
        ("control number", 6),
        ("employer's name, address", 8),
        ("employee's social security", 8),
        ("box 1", 5),
        ("box 2", 5),
        ("copy b", 6),
        ("copy c", 6),
        ("department of the treasury", 6),
        ("internal revenue service", 8),
        ("allocated tips", 6),
        ("dependent care benefits", 6),
        ("nonqualified plans", 5),
        ("statutory employee", 5),
    ],
    DocType.TAX_RETURN.value: [
        ("form 1040", 25),
        ("u.s. individual income tax return", 25),
        ("1040", 15),
        ("adjusted gross income", 20),
        ("tax return", 18),
        ("taxable income", 12),
        ("internal revenue service", 8),
        ("filing status", 12),
        ("standard deduction", 10),
        ("itemized deductions", 10),
        ("schedule a", 8),
        ("schedule b", 8),
        ("schedule c", 8),
        ("schedule d", 8),
        ("schedule e", 8),
        ("schedule se", 6),
        ("total income", 10),
        ("tax liability", 8),
        ("refund", 4),
        ("amount you owe", 6),
        ("overpayment", 5),
        ("estimated tax payments", 8),
        ("earned income credit", 6),
        ("child tax credit", 5),
        ("head of household", 6),
        ("married filing jointly", 6),
        ("single", 2),
        ("wages, salaries, tips", 8),
        ("interest income", 5),
        ("dividend income", 5),
        ("capital gains", 5),
        ("irs e-file", 6),
    ],
    DocType.BUSINESS_TAX_RETURN.value: [
        ("form 1120", 25),
        ("form 1120s", 25),
        ("form 1120-s", 25),
        ("form 1065", 25),
        ("u.s. corporation income tax", 20),
        ("u.s. return of partnership income", 20),
        ("s corporation", 15),
        ("partnership return", 15),
        ("business income", 12),
        ("cost of goods sold", 10),
        ("gross receipts", 12),
        ("officers compensation", 10),
        ("ordinary business income", 10),
        ("schedule k-1", 15),
        ("k-1", 12),
        ("depreciation", 6),
        ("business expenses", 8),
        ("net profit or loss", 8),
        ("total assets", 6),
        ("total liabilities", 6),
        ("shareholder's share", 8),
        ("partner's share", 8),
        ("beginning of year", 4),
        ("end of year", 4),
        ("ein", 5),
    ],
    DocType.PROFIT_LOSS.value: [
        ("profit and loss", 25),
        ("profit & loss", 25),
        ("p&l", 20),
        ("income statement", 20),
        ("statement of income", 18),
        ("statement of operations", 15),
        ("revenue", 8),
        ("total revenue", 10),
        ("cost of goods sold", 8),
        ("gross profit", 12),
        ("operating expenses", 10),
        ("net income", 8),
        ("net profit", 10),
        ("net loss", 8),
        ("operating income", 8),
        ("ebitda", 6),
        ("total expenses", 8),
        ("sales revenue", 6),
        ("professional fees", 4),
        ("rent expense", 4),
        ("utilities expense", 4),
        ("payroll expense", 4),
    ],
    DocType.BALANCE_SHEET.value: [
        ("balance sheet", 25),
        ("statement of financial position", 20),
        ("total assets", 15),
        ("total liabilities", 15),
        ("shareholders equity", 12),
        ("stockholders equity", 12),
        ("owner's equity", 12),
        ("current assets", 12),
        ("current liabilities", 12),
        ("long-term liabilities", 8),
        ("accounts receivable", 8),
        ("accounts payable", 8),
        ("retained earnings", 10),
        ("fixed assets", 8),
        ("net worth", 8),
        ("working capital", 6),
        ("intangible assets", 5),
        ("goodwill", 4),
        ("accumulated depreciation", 6),
        ("notes payable", 5),
    ],
    DocType.BANK_STATEMENT.value: [
        ("account summary", 15),
        ("account statement", 15),
        ("bank statement", 20),
        ("statement period", 12),
        ("beginning balance", 15),
        ("ending balance", 15),
        ("opening balance", 12),
        ("closing balance", 12),
        ("deposits", 8),
        ("withdrawals", 8),
        ("checks paid", 6),
        ("transaction history", 10),
        ("available balance", 10),
        ("current balance", 8),
        ("account number", 8),
        ("routing number", 10),
        ("checking account", 10),
        ("savings account", 10),
        ("daily balance", 6),
        ("service charge", 4),
        ("overdraft", 4),
        ("atm withdrawal", 5),
        ("direct deposit", 5),
        ("wire transfer", 5),
        ("electronic payment", 4),
        ("debit card", 4),
        ("average daily balance", 8),
        ("fdic", 6),
        ("member fdic", 8),
    ],
    DocType.INVESTMENT_STATEMENT.value: [
        ("investment statement", 20),
        ("brokerage statement", 20),
        ("portfolio summary", 15),
        ("account value", 10),
        ("market value", 10),
        ("securities", 8),
        ("mutual fund", 8),
        ("stock", 4),
        ("bonds", 4),
        ("etf", 5),
        ("dividend", 6),
        ("capital gains distribution", 8),
        ("investment income", 8),
        ("total portfolio", 10),
        ("unrealized gain", 8),
        ("realized gain", 6),
        ("cost basis", 8),
        ("asset allocation", 8),
        ("401(k)", 6),
        ("ira", 5),
        ("roth ira", 6),
        ("retirement account", 8),
        ("annuity", 5),
        ("shares", 5),
        ("ticker", 4),
        ("cusip", 6),
    ],
    DocType.GIFT_LETTER.value: [
        ("gift letter", 25),
        ("gift fund", 15),
        ("gift of equity", 15),
        ("donor", 10),
        ("donee", 10),
        ("no repayment", 15),
        ("does not need to be repaid", 15),
        ("not a loan", 10),
        ("gift amount", 12),
        ("relationship to borrower", 12),
        ("relationship to recipient", 10),
        ("source of gift funds", 10),
        ("down payment", 6),
        ("closing costs", 5),
        ("i hereby certify", 6),
        ("gifted funds", 12),
    ],
    DocType.LOE.value: [
        ("letter of explanation", 25),
        ("loe", 15),
        ("to whom it may concern", 10),
        ("explanation letter", 15),
        ("i am writing to explain", 12),
        ("please accept this letter", 8),
        ("explanation for", 10),
        ("regarding the", 4),
        ("credit inquiry", 8),
        ("late payment", 8),
        ("gap in employment", 10),
        ("employment gap", 10),
        ("address discrepancy", 8),
        ("large deposit", 8),
        ("overdraft explanation", 8),
        ("name variation", 6),
        ("change of address", 5),
        ("job change", 5),
    ],
    DocType.LEASE_AGREEMENT.value: [
        ("lease agreement", 25),
        ("rental agreement", 20),
        ("lease contract", 18),
        ("landlord", 12),
        ("tenant", 12),
        ("lessee", 10),
        ("lessor", 10),
        ("monthly rent", 15),
        ("security deposit", 10),
        ("lease term", 12),
        ("lease commencement", 8),
        ("lease expiration", 8),
        ("rental property", 8),
        ("premises", 6),
        ("rent amount", 10),
        ("rental income", 8),
        ("occupancy", 4),
        ("eviction", 4),
        ("late fee", 4),
        ("utilities included", 4),
        ("renewal option", 4),
    ],
    DocType.FHA_CERT.value: [
        ("fha", 15),
        ("federal housing administration", 20),
        ("fha case number", 20),
        ("fha certification", 25),
        ("hud", 10),
        ("mutual mortgage insurance", 12),
        ("mortgage insurance premium", 10),
        ("mip", 8),
        ("upfront mip", 10),
        ("amendatory clause", 10),
        ("fha appraisal", 8),
        ("fha addendum", 10),
        ("real estate certification", 8),
    ],
    DocType.VA_COE.value: [
        ("certificate of eligibility", 25),
        ("va certificate", 20),
        ("veteran", 10),
        ("veterans affairs", 15),
        ("department of veterans affairs", 18),
        ("entitlement", 12),
        ("basic entitlement", 15),
        ("bonus entitlement", 10),
        ("va loan", 12),
        ("va home loan", 15),
        ("va eligibility", 12),
        ("coe", 10),
        ("guaranty amount", 10),
        ("service connected", 6),
        ("funding fee", 8),
    ],
    DocType.DD214.value: [
        ("dd form 214", 25),
        ("dd-214", 25),
        ("dd214", 25),
        ("certificate of release", 20),
        ("discharge from active duty", 20),
        ("military service", 12),
        ("armed forces", 10),
        ("honorable discharge", 15),
        ("character of service", 10),
        ("date of separation", 10),
        ("date entered active duty", 10),
        ("branch of service", 8),
        ("rank", 4),
        ("pay grade", 6),
        ("service number", 6),
        ("reenlistment code", 6),
        ("separation code", 6),
        ("general discharge", 8),
        ("national guard", 5),
        ("reserve component", 5),
    ],
    DocType.BANKRUPTCY_DISCHARGE.value: [
        ("bankruptcy discharge", 25),
        ("discharge of debtor", 20),
        ("chapter 7", 12),
        ("chapter 13", 12),
        ("chapter 11", 10),
        ("united states bankruptcy court", 20),
        ("bankruptcy court", 15),
        ("bankruptcy petition", 12),
        ("debtor", 8),
        ("discharged", 10),
        ("order of discharge", 15),
        ("bankruptcy case", 10),
        ("case number", 5),
        ("creditors", 5),
        ("automatic stay", 6),
        ("proof of claim", 5),
        ("trustee", 5),
        ("schedule of debts", 6),
    ],
    DocType.PURCHASE_CONTRACT.value: [
        ("purchase contract", 25),
        ("purchase agreement", 25),
        ("real estate purchase", 20),
        ("sales contract", 18),
        ("purchase and sale", 18),
        ("purchase price", 15),
        ("earnest money", 15),
        ("closing date", 8),
        ("buyer", 8),
        ("seller", 8),
        ("property address", 6),
        ("contingency", 8),
        ("inspection contingency", 8),
        ("financing contingency", 10),
        ("appraisal contingency", 8),
        ("title contingency", 6),
        ("escrow", 8),
        ("possession date", 6),
        ("addendum", 4),
        ("counter offer", 6),
        ("offer to purchase", 12),
        ("real property", 5),
        ("legal description", 6),
    ],
    DocType.APPRAISAL.value: [
        ("appraisal", 15),
        ("appraised value", 20),
        ("market value", 8),
        ("appraisal report", 20),
        ("uniform residential appraisal", 25),
        ("subject property", 12),
        ("comparable sales", 15),
        ("comparable sale", 12),
        ("comp 1", 6),
        ("comp 2", 6),
        ("comp 3", 6),
        ("sale price", 5),
        ("gross living area", 12),
        ("square footage", 6),
        ("year built", 5),
        ("site value", 6),
        ("cost approach", 10),
        ("sales comparison", 12),
        ("income approach", 6),
        ("reconciliation", 4),
        ("highest and best use", 8),
        ("neighborhood analysis", 6),
        ("zoning", 4),
        ("urar", 10),
        ("form 1004", 10),
        ("1004mc", 6),
    ],
    DocType.TITLE_REPORT.value: [
        ("title report", 25),
        ("title commitment", 20),
        ("preliminary title", 18),
        ("title search", 15),
        ("title insurance", 12),
        ("title examination", 12),
        ("chain of title", 12),
        ("deed of trust", 10),
        ("legal description", 8),
        ("vesting", 10),
        ("easement", 6),
        ("lien", 8),
        ("encumbrance", 8),
        ("exception", 4),
        ("schedule a", 5),
        ("schedule b", 5),
        ("title company", 8),
        ("title officer", 6),
        ("lot", 4),
        ("block", 3),
        ("subdivision", 5),
        ("recording", 5),
        ("grantor", 6),
        ("grantee", 6),
        ("warranty deed", 8),
        ("quitclaim deed", 6),
    ],
    DocType.HOMEOWNERS_INSURANCE.value: [
        ("homeowners insurance", 25),
        ("homeowner's insurance", 25),
        ("hazard insurance", 18),
        ("dwelling coverage", 15),
        ("property insurance", 12),
        ("insurance policy", 10),
        ("insurance declaration", 15),
        ("declarations page", 15),
        ("policy number", 8),
        ("coverage amount", 8),
        ("premium", 6),
        ("annual premium", 8),
        ("deductible", 6),
        ("liability coverage", 6),
        ("personal property coverage", 6),
        ("replacement cost", 8),
        ("dwelling", 5),
        ("effective date", 4),
        ("expiration date", 4),
        ("named insured", 8),
        ("mortgagee clause", 12),
        ("loss payee", 8),
        ("flood insurance", 6),
        ("wind coverage", 4),
        ("ho-3", 8),
        ("ho3", 6),
        ("ho-6", 6),
    ],
    DocType.DRIVERS_LICENSE.value: [
        ("driver license", 20),
        ("driver's license", 20),
        ("drivers license", 20),
        ("identification card", 12),
        ("state id", 10),
        ("date of birth", 8),
        ("dob", 6),
        ("expiration date", 4),
        ("exp", 3),
        ("class", 4),
        ("license number", 10),
        ("dl number", 8),
        ("height", 3),
        ("weight", 3),
        ("eye color", 4),
        ("hair color", 3),
        ("sex", 3),
        ("restrictions", 4),
        ("endorsements", 4),
        ("organ donor", 4),
        ("real id", 5),
        ("department of motor vehicles", 8),
        ("dmv", 5),
    ],
}

# Filename patterns: (regex_pattern, DocType_value, confidence_boost)
FILENAME_PATTERNS: List[Tuple[str, str, int]] = [
    (r"(?i)pay\s*stub", DocType.PAYSTUB.value, 80),
    (r"(?i)paystub", DocType.PAYSTUB.value, 80),
    (r"(?i)pay\s*slip", DocType.PAYSTUB.value, 75),
    (r"(?i)earnings\s*statement", DocType.PAYSTUB.value, 75),
    (r"(?i)\bw[\-_\s]?2\b", DocType.W2.value, 85),
    (r"(?i)wage.*tax", DocType.W2.value, 75),
    (r"(?i)1040", DocType.TAX_RETURN.value, 75),
    (r"(?i)tax\s*return", DocType.TAX_RETURN.value, 80),
    (r"(?i)tax_return", DocType.TAX_RETURN.value, 80),
    (r"(?i)1120", DocType.BUSINESS_TAX_RETURN.value, 75),
    (r"(?i)1065", DocType.BUSINESS_TAX_RETURN.value, 75),
    (r"(?i)business.*tax", DocType.BUSINESS_TAX_RETURN.value, 70),
    (r"(?i)corp.*tax", DocType.BUSINESS_TAX_RETURN.value, 70),
    (r"(?i)k[\-_]?1", DocType.BUSINESS_TAX_RETURN.value, 60),
    (r"(?i)profit.*loss|p[\s&]*l|income\s*statement", DocType.PROFIT_LOSS.value, 75),
    (r"(?i)balance\s*sheet", DocType.BALANCE_SHEET.value, 80),
    (r"(?i)bank\s*statement", DocType.BANK_STATEMENT.value, 85),
    (r"(?i)bank_stmt", DocType.BANK_STATEMENT.value, 80),
    (r"(?i)checking|savings", DocType.BANK_STATEMENT.value, 50),
    (r"(?i)invest.*statement|brokerage|portfolio", DocType.INVESTMENT_STATEMENT.value, 75),
    (r"(?i)401k|ira|retirement", DocType.INVESTMENT_STATEMENT.value, 60),
    (r"(?i)gift\s*letter|gift\s*fund", DocType.GIFT_LETTER.value, 85),
    (r"(?i)\bloe\b|letter.*explanation", DocType.LOE.value, 80),
    (r"(?i)lease|rental\s*agreement", DocType.LEASE_AGREEMENT.value, 80),
    (r"(?i)fha.*cert|fha.*addendum", DocType.FHA_CERT.value, 80),
    (r"(?i)va.*coe|certificate.*eligibility", DocType.VA_COE.value, 80),
    (r"(?i)dd[\-_\s]?214", DocType.DD214.value, 90),
    (r"(?i)bankruptcy.*discharge|discharge.*order", DocType.BANKRUPTCY_DISCHARGE.value, 80),
    (r"(?i)purchase.*contract|purchase.*agreement|sales.*contract", DocType.PURCHASE_CONTRACT.value, 80),
    (r"(?i)appraisal", DocType.APPRAISAL.value, 70),
    (r"(?i)title.*report|title.*commitment|prelim.*title", DocType.TITLE_REPORT.value, 80),
    (r"(?i)homeowners?\s*insurance|hazard\s*insurance|insurance.*dec", DocType.HOMEOWNERS_INSURANCE.value, 80),
    (r"(?i)driver|license|state\s*id|identification", DocType.DRIVERS_LICENSE.value, 50),
]


# =============================================================================
# FEATURE DETECTION PATTERNS
# =============================================================================

FEATURE_PATTERNS: Dict[str, str] = {
    "has_employer_name": r"(?i)employer[:\s]|company[:\s]|hired\s+by",
    "has_pay_period": r"(?i)pay\s*period|period\s*(ending|beginning)|pay\s*date",
    "has_ssn": r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b|xxx[-\s]?xx[-\s]?\d{4}|\*{3}[-\s]?\*{2}[-\s]?\d{4}",
    "has_ein": r"(?i)(ein|employer\s+identification)[:\s]*\d{2}[-\s]?\d{7}",
    "has_account_number": r"(?i)account\s*(number|#|no)[:\s]*[\dxX*]+",
    "has_balance": r"(?i)(beginning|ending|opening|closing|available|current)\s*balance",
    "has_routing_number": r"(?i)routing\s*(number|#|no)[:\s]*\d{9}",
    "has_property_address": r"(?i)(property|subject)\s*(address|location)[:\s]",
    "has_appraisal_value": r"(?i)(appraised|estimated|market)\s*value[:\s]*\$?[\d,]+",
    "has_signature": r"(?i)(signature|signed|sign\s+here|x_+)",
    "has_notary": r"(?i)(notary|notarized|sworn|affirm|acknowledge|seal)",
    "has_date": r"\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b",
    "has_watermark": r"(?i)(copy|duplicate|unofficial|sample|draft|void)",
}


# =============================================================================
# AI CLASSIFICATION PROMPT
# =============================================================================

AI_SYSTEM_PROMPT = """You are a mortgage document classifier. Your job is to identify the type of mortgage-related document being presented.

Classify the document into exactly ONE of the following types:
- DRIVERS_LICENSE: Government-issued photo ID / driver's license
- PAYSTUB: Pay stub / earnings statement from an employer
- W2: IRS Form W-2 Wage and Tax Statement
- TAX_RETURN: Personal federal tax return (Form 1040)
- BUSINESS_TAX_RETURN: Business tax return (Form 1120, 1120-S, 1065, Schedule K-1)
- PROFIT_LOSS: Profit and loss statement / income statement for a business
- BALANCE_SHEET: Balance sheet / statement of financial position
- BANK_STATEMENT: Bank account statement (checking or savings)
- INVESTMENT_STATEMENT: Investment / brokerage / retirement account statement
- GIFT_LETTER: Gift letter for down payment or closing costs
- LOE: Letter of explanation (for credit, employment gaps, etc.)
- LEASE_AGREEMENT: Rental / lease agreement
- FHA_CERT: FHA certification or addendum
- VA_COE: VA Certificate of Eligibility
- DD214: DD Form 214 Certificate of Release or Discharge from Active Duty
- BANKRUPTCY_DISCHARGE: Bankruptcy discharge order
- PURCHASE_CONTRACT: Real estate purchase agreement / sales contract
- APPRAISAL: Property appraisal report
- TITLE_REPORT: Title report, commitment, or search
- HOMEOWNERS_INSURANCE: Homeowners / hazard insurance policy or declarations page
- OTHER: Document that does not match any of the above types

Respond with a JSON object containing:
{
    "predicted_type": "DOCTYPE_VALUE",
    "confidence": 0-100,
    "alternatives": [{"type": "DOCTYPE", "confidence": N}, ...],
    "reasoning": "Brief explanation of classification rationale"
}

Rules:
1. Always pick the MOST SPECIFIC matching type.
2. Confidence should reflect how certain you are (100 = definitive, 50 = uncertain).
3. List up to 3 alternatives with their confidence scores.
4. If truly unidentifiable, use OTHER with low confidence.
5. Respond ONLY with the JSON object, no additional text."""


# =============================================================================
# AI DOCUMENT CLASSIFIER SERVICE
# =============================================================================

class AIDocumentClassifierService:
    """
    AI-powered document classification for mortgage documents.

    Uses Claude API for intelligent classification with rule-based fallback.
    Classifies documents into mortgage-specific categories with confidence scores.
    """

    def __init__(self):
        self._anthropic = None
        self._model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

        if HAS_ANTHROPIC and os.getenv("ANTHROPIC_API_KEY"):
            try:
                self._anthropic = Anthropic()
            except Exception as e:
                logger.warning("Failed to initialize Anthropic client: %s", e)

    # -------------------------------------------------------------------------
    # PUBLIC: classify_document
    # -------------------------------------------------------------------------

    def classify_document(
        self,
        file_content: bytes,
        mime_type: str,
        filename: str,
        ocr_text: Optional[str] = None,
        db: Optional[Session] = None,
        organization_id: Optional[int] = None,
    ) -> ClassificationResult:
        """
        Classify a mortgage document using AI with rule-based fallback.

        When db and organization_id are provided, results are cached by
        document hash to avoid re-processing identical documents.

        Args:
            file_content: Raw file bytes.
            mime_type: MIME type (application/pdf, image/jpeg, etc.).
            filename: Original filename.
            ocr_text: Pre-extracted OCR text (optional; skips extraction).
            db: Optional SQLAlchemy session for cache lookups.
            organization_id: Optional org ID for tenant-scoped caching.

        Returns:
            ClassificationResult with predicted type, confidence, and features.
        """
        start_ms = _now_ms()

        # --- Document cache lookup ---
        doc_hash = None
        cache_service = None
        if db is not None and organization_id is not None and file_content:
            try:
                from services.smart_docs.document_cache_service import get_document_cache_service
                cache_service = get_document_cache_service()
                doc_hash = cache_service.get_or_compute_hash(file_content)
                cached = cache_service.get_cached_classification(db, doc_hash, organization_id)
                if cached is not None:
                    logger.info(
                        "doc_cache CLASSIFICATION_HIT hash=%s org=%s filename=%s",
                        doc_hash[:12], organization_id, filename,
                    )
                    return ClassificationResult(
                        predicted_type=cached.get("predicted_type", "OTHER"),
                        confidence=cached.get("confidence", 0),
                        alternatives=cached.get("alternatives", []),
                        features_detected=cached.get("features_detected", {}),
                        text_snippet=cached.get("text_snippet", ""),
                        model_used=cached.get("model_used", "cache"),
                        duration_ms=_now_ms() - start_ms,
                        success=True,
                    )
                else:
                    logger.info(
                        "doc_cache CLASSIFICATION_MISS hash=%s org=%s filename=%s",
                        doc_hash[:12], organization_id, filename,
                    )
            except Exception as e:
                logger.warning("doc_cache classification lookup failed: %s", e)

        # Helper: cache result before returning
        def _cache_and_return(result: ClassificationResult) -> ClassificationResult:
            if cache_service and doc_hash and db is not None and organization_id is not None:
                if result.success and result.confidence >= 40:
                    try:
                        cache_service.cache_classification(db, doc_hash, organization_id, {
                            "predicted_type": result.predicted_type,
                            "confidence": result.confidence,
                            "alternatives": result.alternatives,
                            "features_detected": result.features_detected,
                            "text_snippet": result.text_snippet,
                            "model_used": result.model_used,
                        })
                    except Exception as e:
                        logger.warning("doc_cache classification store failed: %s", e)
            return result

        # Try AI classification first
        fallback_used = False
        if self._anthropic:
            try:
                result = self._classify_with_ai(file_content, mime_type, ocr_text)
                if result.success and result.confidence >= 40:
                    result.duration_ms = _now_ms() - start_ms
                    logger.info(
                        "Document classified | doc_type=%s | confidence=%d | "
                        "duration_ms=%d | fallback_used=False | filename=%s",
                        result.predicted_type,
                        result.confidence,
                        result.duration_ms,
                        filename,
                    )
                    return _cache_and_return(result)
                # Low-confidence AI result -- supplement with rules
                logger.info(
                    "AI classification low confidence (%d) for %s, supplementing with rules",
                    result.confidence,
                    filename,
                )
                fallback_used = True
            except Exception as e:
                logger.warning("AI classification failed for %s: %s", filename, e)
                fallback_used = True

        # Fallback: rule-based classification
        # Use OCR text if available, otherwise try filename
        if ocr_text:
            result = self.classify_by_text(ocr_text, filename)
            result.duration_ms = _now_ms() - start_ms
            logger.info(
                "Document classified | doc_type=%s | confidence=%d | "
                "duration_ms=%d | fallback_used=%s | filename=%s",
                result.predicted_type,
                result.confidence,
                result.duration_ms,
                fallback_used,
                filename,
            )
            return _cache_and_return(result)

        # No OCR text and AI unavailable -- classify by filename only
        result = self.classify_by_filename(filename)
        result.duration_ms = _now_ms() - start_ms
        logger.info(
            "Document classified | doc_type=%s | confidence=%d | "
            "duration_ms=%d | fallback_used=%s | filename=%s",
            result.predicted_type,
            result.confidence,
            result.duration_ms,
            fallback_used,
            filename,
        )
        return _cache_and_return(result)

    # -------------------------------------------------------------------------
    # PUBLIC: classify_by_text
    # -------------------------------------------------------------------------

    def classify_by_text(self, text: str, filename: str = "") -> ClassificationResult:
        """
        Rule-based classification using keyword matching against document text.

        Scores each DocType based on weighted keyword matches, then combines
        with any filename signal for the final prediction.

        Args:
            text: Document text (OCR or extracted).
            filename: Original filename for supplementary signal.

        Returns:
            ClassificationResult from rule-based analysis.
        """
        start_ms = _now_ms()
        text_lower = text.lower()
        snippet = text[:1000]

        # Score each document type
        scores: Dict[str, int] = {}
        for doc_type, keywords in KEYWORD_RULES.items():
            score = 0
            for keyword, weight in keywords:
                if keyword.lower() in text_lower:
                    score += weight
            if score > 0:
                scores[doc_type] = score

        # Add filename signal
        filename_result = self.classify_by_filename(filename)
        if filename_result.predicted_type != DocType.OTHER.value and filename_result.confidence >= 50:
            fn_type = filename_result.predicted_type
            boost = filename_result.confidence // 4  # Up to +25 from filename
            scores[fn_type] = scores.get(fn_type, 0) + boost

        if not scores:
            return ClassificationResult(
                predicted_type=DocType.OTHER.value,
                confidence=20,
                alternatives=[],
                features_detected=self.detect_features(text),
                text_snippet=snippet,
                model_used="rule_based_v1",
                duration_ms=_now_ms() - start_ms,
            )

        # Rank and normalize
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        max_score = ranked[0][1]

        # Convert raw score to confidence (0-100)
        # Confidence scaling: a score of 50+ => ~90 confidence, 20 => ~60, etc.
        confidence = min(95, int(40 + (max_score / max(max_score, 1)) * 55))
        if max_score >= 80:
            confidence = min(95, 80 + min(15, (max_score - 80) // 3))
        elif max_score >= 50:
            confidence = 65 + min(15, (max_score - 50) // 2)
        elif max_score >= 30:
            confidence = 50 + min(15, (max_score - 30))
        elif max_score >= 15:
            confidence = 35 + max_score
        else:
            confidence = max(15, max_score * 2)

        # Check gap between top two for confidence boost
        if len(ranked) >= 2:
            gap = ranked[0][1] - ranked[1][1]
            if gap > 30:
                confidence = min(95, confidence + 5)  # Clear winner boost
            elif gap < 5:
                confidence = max(15, confidence - 10)  # Too close, lower confidence

        # Build alternatives
        alternatives = []
        for doc_type, score in ranked[1:4]:  # Top 3 alternatives
            alt_confidence = int(confidence * (score / max_score)) if max_score > 0 else 0
            alternatives.append({"type": doc_type, "confidence": alt_confidence})

        features = self.detect_features(text)

        return ClassificationResult(
            predicted_type=ranked[0][0],
            confidence=confidence,
            alternatives=alternatives,
            features_detected=features,
            text_snippet=snippet,
            model_used="rule_based_v1",
            duration_ms=_now_ms() - start_ms,
        )

    # -------------------------------------------------------------------------
    # PUBLIC: classify_by_filename
    # -------------------------------------------------------------------------

    def classify_by_filename(self, filename: str) -> ClassificationResult:
        """
        Classify document based solely on filename pattern matching.

        Args:
            filename: Original filename of the document.

        Returns:
            ClassificationResult from filename analysis.
        """
        start_ms = _now_ms()

        if not filename:
            return ClassificationResult(
                predicted_type=DocType.OTHER.value,
                confidence=0,
                alternatives=[],
                features_detected={},
                text_snippet="",
                model_used="filename_v1",
                duration_ms=_now_ms() - start_ms,
            )

        best_type = DocType.OTHER.value
        best_confidence = 0
        all_matches: List[Tuple[str, int]] = []

        for pattern, doc_type, confidence in FILENAME_PATTERNS:
            if re.search(pattern, filename):
                all_matches.append((doc_type, confidence))
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_type = doc_type

        # Build alternatives from other filename matches
        alternatives = []
        for doc_type, conf in sorted(all_matches, key=lambda x: x[1], reverse=True):
            if doc_type != best_type:
                alternatives.append({"type": doc_type, "confidence": conf})

        return ClassificationResult(
            predicted_type=best_type,
            confidence=best_confidence,
            alternatives=alternatives[:3],
            features_detected={},
            text_snippet="",
            model_used="filename_v1",
            duration_ms=_now_ms() - start_ms,
        )

    # -------------------------------------------------------------------------
    # PRIVATE: _classify_with_ai
    # -------------------------------------------------------------------------

    def _classify_with_ai(
        self,
        file_content: bytes,
        mime_type: str,
        ocr_text: Optional[str] = None,
    ) -> ClassificationResult:
        """
        Classify a document using the Anthropic Claude API.

        For images and PDFs, sends the document as a vision input.
        For pre-extracted text, sends the text directly.

        Args:
            file_content: Raw file bytes.
            mime_type: MIME type of the file.
            ocr_text: Pre-extracted OCR text (uses text prompt if provided).

        Returns:
            ClassificationResult from AI analysis.
        """
        start_ms = _now_ms()

        if not self._anthropic:
            return ClassificationResult(
                predicted_type=DocType.OTHER.value,
                confidence=0,
                alternatives=[],
                features_detected={},
                text_snippet=ocr_text[:1000] if ocr_text else "",
                model_used="none",
                duration_ms=_now_ms() - start_ms,
                success=False,
                error="Anthropic API client not available",
            )

        try:
            # Build the message content
            messages_content = []

            if ocr_text:
                # Text-only classification
                messages_content.append({
                    "type": "text",
                    "text": (
                        "Classify the following mortgage document based on its text content.\n\n"
                        f"Document text (first 3000 characters):\n\n{ocr_text[:3000]}"
                    ),
                })
            elif mime_type in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                # Vision-based classification for images
                b64_data = base64.b64encode(file_content).decode("utf-8")
                messages_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": b64_data,
                    },
                })
                messages_content.append({
                    "type": "text",
                    "text": "Classify this mortgage document based on its visual content.",
                })
            elif mime_type == "application/pdf":
                # For PDFs, encode as base64 document
                b64_data = base64.b64encode(file_content).decode("utf-8")
                messages_content.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": b64_data,
                    },
                })
                messages_content.append({
                    "type": "text",
                    "text": "Classify this mortgage document based on its content.",
                })
            else:
                # Unsupported mime type for vision -- try to decode as text
                try:
                    text = file_content.decode("utf-8")[:3000]
                    messages_content.append({
                        "type": "text",
                        "text": (
                            "Classify the following mortgage document based on its text content.\n\n"
                            f"Document text:\n\n{text}"
                        ),
                    })
                except UnicodeDecodeError:
                    return ClassificationResult(
                        predicted_type=DocType.OTHER.value,
                        confidence=0,
                        alternatives=[],
                        features_detected={},
                        text_snippet="",
                        model_used=self._model,
                        duration_ms=_now_ms() - start_ms,
                        success=False,
                        error=f"Unsupported mime type for AI classification: {mime_type}",
                    )

            response = resilient_ai_call(
                client=self._anthropic,
                messages=[{"role": "user", "content": messages_content}],
                model=self._model,
                max_tokens=1024,
                operation_name="classify_document",
                timeout=30.0,
                system=AI_SYSTEM_PROMPT,
            )

            if response is None:
                # AI call failed after retries or circuit is open -- trigger fallback
                logger.warning("AI classification unavailable, falling back to rules")
                return ClassificationResult(
                    predicted_type=DocType.OTHER.value,
                    confidence=0,
                    alternatives=[],
                    features_detected={},
                    text_snippet=ocr_text[:1000] if ocr_text else "",
                    model_used=self._model,
                    duration_ms=_now_ms() - start_ms,
                    success=False,
                    error="AI call failed after retries or circuit breaker open",
                )

            # Parse the response
            response_text = response.content[0].text.strip()
            return self._parse_ai_response(
                response_text,
                text_snippet=ocr_text[:1000] if ocr_text else "",
                start_ms=start_ms,
            )

        except Exception as e:
            logger.exception("AI classification API call failed")
            return ClassificationResult(
                predicted_type=DocType.OTHER.value,
                confidence=0,
                alternatives=[],
                features_detected={},
                text_snippet=ocr_text[:1000] if ocr_text else "",
                model_used=self._model,
                duration_ms=_now_ms() - start_ms,
                success=False,
                error=str(e),
            )

    def _parse_ai_response(
        self,
        response_text: str,
        text_snippet: str,
        start_ms: int,
    ) -> ClassificationResult:
        """Parse the JSON response from Claude into a ClassificationResult."""
        try:
            # Strip markdown code fences if present
            cleaned = response_text
            if cleaned.startswith("```"):
                # Remove opening ```json or ```
                cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
                cleaned = re.sub(r"\n?```\s*$", "", cleaned)
            cleaned = cleaned.strip()

            data = json.loads(cleaned)

            predicted_type = data.get("predicted_type", DocType.OTHER.value)
            # Validate the predicted type is a valid DocType
            valid_types = {dt.value for dt in DocType}
            if predicted_type not in valid_types:
                logger.warning("AI returned invalid doc type: %s", predicted_type)
                predicted_type = DocType.OTHER.value

            confidence = max(0, min(100, int(data.get("confidence", 50))))

            alternatives = []
            for alt in data.get("alternatives", [])[:3]:
                alt_type = alt.get("type", DocType.OTHER.value)
                if alt_type in valid_types:
                    alternatives.append({
                        "type": alt_type,
                        "confidence": max(0, min(100, int(alt.get("confidence", 0)))),
                    })

            return ClassificationResult(
                predicted_type=predicted_type,
                confidence=confidence,
                alternatives=alternatives,
                features_detected={},
                text_snippet=text_snippet,
                model_used=self._model,
                duration_ms=_now_ms() - start_ms,
                success=True,
            )

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("Failed to parse AI classification response: %s", e)
            return ClassificationResult(
                predicted_type=DocType.OTHER.value,
                confidence=0,
                alternatives=[],
                features_detected={},
                text_snippet=text_snippet,
                model_used=self._model,
                duration_ms=_now_ms() - start_ms,
                success=False,
                error=f"Failed to parse AI response: {e}",
            )

    # -------------------------------------------------------------------------
    # PUBLIC: detect_features
    # -------------------------------------------------------------------------

    def detect_features(self, text: str) -> Dict[str, bool]:
        """
        Detect structural features present in document text.

        Scans for patterns indicating employer names, SSN fragments,
        account numbers, signatures, notarization, and other
        mortgage-relevant features.

        Args:
            text: Document text to analyze.

        Returns:
            Dict mapping feature names to boolean presence.
        """
        if not text:
            return {}

        features: Dict[str, bool] = {}
        for feature_name, pattern in FEATURE_PATTERNS.items():
            features[feature_name] = bool(re.search(pattern, text))

        # Additional multi-line / structural features
        lines = text.split("\n")
        features["is_multi_page"] = (
            len(text) > 3000
            or any("page" in line.lower() and re.search(r"\d+\s*(of|/)\s*\d+", line) for line in lines)
        )

        return features

    # -------------------------------------------------------------------------
    # PUBLIC: batch_classify
    # -------------------------------------------------------------------------

    def batch_classify(
        self,
        documents: List[Dict],
    ) -> List[ClassificationResult]:
        """
        Classify multiple documents.

        Each dict in the list should contain:
            - file_content (bytes): Raw file bytes.
            - mime_type (str): MIME type.
            - filename (str): Original filename.
            - ocr_text (str, optional): Pre-extracted text.

        Args:
            documents: List of document dicts to classify.

        Returns:
            List of ClassificationResult in the same order as input.
        """
        results: List[ClassificationResult] = []
        for doc in documents:
            try:
                result = self.classify_document(
                    file_content=doc.get("file_content", b""),
                    mime_type=doc.get("mime_type", "application/octet-stream"),
                    filename=doc.get("filename", ""),
                    ocr_text=doc.get("ocr_text"),
                )
                results.append(result)
            except Exception as e:
                logger.exception("Batch classification failed for %s", doc.get("filename", "unknown"))
                results.append(ClassificationResult(
                    predicted_type=DocType.OTHER.value,
                    confidence=0,
                    alternatives=[],
                    features_detected={},
                    text_snippet="",
                    model_used="error",
                    duration_ms=0,
                    success=False,
                    error=str(e),
                ))
        return results

    # -------------------------------------------------------------------------
    # PUBLIC: get_classification_for_document
    # -------------------------------------------------------------------------

    def get_classification_for_document(
        self,
        db: Session,
        document_id: int,
        organization_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """
        Retrieve an existing AI classification for a document.

        Queries the ai_document_classifications table for a cached result.

        Args:
            db: SQLAlchemy session.
            document_id: ID of the smart_documents record.
            organization_id: Optional org ID for tenant isolation. When set,
                verifies the document belongs to a loan in this organization.

        Returns:
            Dict with classification data, or None if not classified yet.
        """
        try:
            # Tenant isolation: verify the document belongs to the caller's org
            if organization_id is not None:
                doc_org_check = db.execute(
                    text("""
                        SELECT l.organization_id
                        FROM smart_documents sd
                        JOIN loans l ON l.id = sd.loan_id
                        WHERE sd.id = :doc_id
                    """),
                    {"doc_id": document_id},
                ).fetchone()
                if doc_org_check and doc_org_check.organization_id != organization_id:
                    logger.warning(
                        "Tenant isolation violation in classifier: doc %d belongs to org %s, caller org %s",
                        document_id, doc_org_check.organization_id, organization_id,
                    )
                    return None

            from database.models.document_intelligence import AIDocumentClassification

            record = (
                db.query(AIDocumentClassification)
                .filter(AIDocumentClassification.document_id == document_id)
                .order_by(AIDocumentClassification.created_at.desc())
                .first()
            )

            if not record:
                return None

            return {
                "id": record.id,
                "document_id": record.document_id,
                "original_doc_type": record.original_doc_type,
                "predicted_doc_type": record.predicted_doc_type,
                "prediction_confidence": record.prediction_confidence,
                "alternative_classifications": record.alternative_classifications,
                "classification_model": record.classification_model,
                "classification_duration_ms": record.classification_duration_ms,
                "features_detected": record.features_detected,
                "text_snippet": record.text_snippet,
                "is_correct": record.is_correct,
                "corrected_doc_type": record.corrected_doc_type,
                "corrected_by": record.corrected_by,
                "corrected_at": record.corrected_at.isoformat() if record.corrected_at else None,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }

        except Exception as e:
            logger.exception("Failed to retrieve classification for document %d", document_id)
            return None

    # -------------------------------------------------------------------------
    # PUBLIC: save_classification
    # -------------------------------------------------------------------------

    def save_classification(
        self,
        db: Session,
        document_id: int,
        result: ClassificationResult,
        organization_id: int = None,
    ) -> None:
        """
        Persist a classification result to the ai_document_classifications table.

        Args:
            db: SQLAlchemy session.
            document_id: ID of the smart_documents record.
            result: ClassificationResult to save.
            organization_id: Tenant organization ID (optional).
        """
        try:
            from database.models.document_intelligence import AIDocumentClassification

            record = AIDocumentClassification(
                organization_id=organization_id,
                document_id=document_id,
                predicted_doc_type=result.predicted_type,
                prediction_confidence=result.confidence,
                alternative_classifications=result.alternatives if result.alternatives else None,
                classification_model=result.model_used,
                classification_duration_ms=result.duration_ms,
                features_detected=result.features_detected if result.features_detected else None,
                text_snippet=result.text_snippet[:1000] if result.text_snippet else None,
            )

            db.add(record)
            db.flush()
            logger.info(
                "Saved classification for document %d: %s (confidence=%d)",
                document_id,
                result.predicted_type,
                result.confidence,
            )

        except Exception as e:
            logger.exception("Failed to save classification for document %d", document_id)
            raise


# =============================================================================
# HELPERS
# =============================================================================

def _now_ms() -> int:
    """Current time in milliseconds."""
    return int(time.time() * 1000)


# =============================================================================
# SINGLETON
# =============================================================================

_service: Optional[AIDocumentClassifierService] = None


def get_ai_classifier_service() -> AIDocumentClassifierService:
    """
    Get or create the singleton AIDocumentClassifierService instance.

    Returns:
        The shared AIDocumentClassifierService instance.
    """
    global _service
    if _service is None:
        _service = AIDocumentClassifierService()
    return _service
