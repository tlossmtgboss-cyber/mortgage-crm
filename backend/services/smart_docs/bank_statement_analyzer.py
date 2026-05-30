"""
AI-Powered Bank Statement Analysis Service

Analyzes bank statements to identify underwriting concerns for mortgage
qualification. Generates flags, recommendations, and tasks for LO follow-up.

Integrates with:
    - smart_documents / smart_document_extractions for document data and OCR text
    - income_calculations / income_verification_tasks for result persistence
    - IncomeCalculatorService for income cross-referencing

Key analysis areas:
    1. Large deposits requiring sourcing (per Fannie Mae/FHA guidelines)
    2. NSF/overdraft events (underwriting red flags)
    3. IRS payments (tax liens, payment plans)
    4. Payroll deposit patterns (income verification)
    5. Recurring undisclosed debts
    6. Suspicious activity (structuring, round deposits)
    7. Balance trends and sufficiency for closing

Usage:
    from services.smart_docs.bank_statement_analyzer import (
        get_bank_statement_analyzer,
        BankStatementAnalyzerService,
    )

    service = get_bank_statement_analyzer(db)
    result = service.analyze_statements(loan_id=42, borrower_id=7)
"""

import logging
import os
import re
import json
import time
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional AI client
# ---------------------------------------------------------------------------
try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

from services.smart_docs.ai_resilience import resilient_ai_call

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")

# Per Fannie Mae Selling Guide B3-4.2-01: any deposit >= 50% of qualifying
# monthly income requires sourcing.  For initial screening before income is
# calculated, $500 is a conservative proxy used by most lenders.
LARGE_DEPOSIT_THRESHOLD = Decimal("500.00")

# Currency Transaction Report filing threshold (31 CFR 1010.311)
STRUCTURING_THRESHOLD = Decimal("10000.00")

# Deposits between $9,000 and $9,999 are suspicious for structuring
NEAR_STRUCTURING_THRESHOLD = Decimal("9000.00")

# NSF severity mapping based on count within statement period
NSF_SEVERITY_MAP = {0: "LOW", 1: "MEDIUM", 2: "MEDIUM", 3: "HIGH", 4: "HIGH"}

# Known payroll/direct-deposit indicators (lowercase for matching)
PAYROLL_KEYWORDS = [
    "payroll", "direct dep", "salary", "wages", "ach",
    "employer", "workforce", "adp", "paychex", "gusto",
    "quickbooks payroll", "intuit payroll", "dp ", "dir dep",
    "direct deposit", "paycheck",
]

# IRS payment indicators
IRS_KEYWORDS = [
    "irs", "internal revenue", "ustreas", "us treasury",
    "tax payment", "eftps", "estimated tax", "federal tax",
    "treas 310", "tax ref",
]

# Common recurring payment categories with keyword lists
RECURRING_CATEGORIES: Dict[str, List[str]] = {
    "mortgage_rent": ["mortgage", "rent", "hoa", "homeowner", "escrow"],
    "auto_loan": [
        "auto loan", "car payment", "vehicle", "ally",
        "capital one auto", "toyota financial", "ford motor credit",
    ],
    "student_loan": [
        "student loan", "navient", "nelnet", "fedloan",
        "great lakes", "mohela", "aidvantage", "dept of ed",
    ],
    "credit_card": [
        "credit card", "visa", "mastercard", "amex", "discover",
        "chase card", "citi card", "capital one", "synchrony",
        "barclays",
    ],
    "insurance": [
        "insurance", "geico", "state farm", "allstate",
        "progressive", "usaa", "liberty mutual",
    ],
    "utilities": [
        "electric", "gas", "water", "sewer", "utility",
        "power", "comcast", "spectrum", "at&t", "verizon",
        "t-mobile",
    ],
    "child_support": ["child support", "domestic rel", "family support"],
    "alimony": ["alimony", "spousal support"],
}

# Bank-statement doc type (matches DocType enum in smart_docs_models)
BANK_STATEMENT_DOC_TYPE = "BANK_STATEMENT"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class LargeDeposit:
    """A large deposit requiring sourcing."""
    date: str
    amount: Decimal
    description: str
    is_payroll: bool
    is_transfer: bool
    needs_sourcing: bool
    sourcing_explanation: Optional[str]
    risk_level: str  # LOW, MEDIUM, HIGH
    notes: str


@dataclass
class NSFEvent:
    """An NSF/overdraft event."""
    date: str
    amount: Decimal
    description: str
    resulting_balance: Optional[Decimal]
    fee_charged: Optional[Decimal]


@dataclass
class RecurringPayment:
    """A recurring payment pattern detected."""
    category: str
    payee: str
    average_amount: Decimal
    frequency: str  # MONTHLY, BIWEEKLY, WEEKLY
    occurrences: int
    total_amount: Decimal
    is_disclosed: bool  # Will need LO to verify
    dates: List[str]


@dataclass
class IRSPayment:
    """Payment to IRS detected."""
    date: str
    amount: Decimal
    description: str
    payment_type: str  # ESTIMATED_TAX, PAYMENT_PLAN, PENALTY, UNKNOWN
    is_recurring: bool


@dataclass
class PayrollDeposit:
    """Payroll deposit identified."""
    date: str
    amount: Decimal
    source: str  # Employer/source name
    frequency: str  # WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY
    is_consistent: bool


@dataclass
class BankStatementAnalysis:
    """Complete bank statement analysis result."""
    loan_id: int
    document_ids: List[int]
    statement_period_start: Optional[str]
    statement_period_end: Optional[str]
    account_type: str  # CHECKING, SAVINGS, BUSINESS
    institution_name: Optional[str]

    # Balances
    beginning_balance: Optional[Decimal]
    ending_balance: Optional[Decimal]
    average_daily_balance: Optional[Decimal]
    lowest_balance: Optional[Decimal]
    lowest_balance_date: Optional[str]

    # Large deposits
    large_deposits: List[LargeDeposit]
    total_large_deposits: Decimal
    deposits_needing_sourcing: int

    # NSF/Overdrafts
    nsf_events: List[NSFEvent]
    nsf_count: int
    nsf_severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    total_nsf_fees: Decimal
    overdraft_days: int

    # IRS payments
    irs_payments: List[IRSPayment]
    total_irs_payments: Decimal
    irs_payment_plan_detected: bool

    # Payroll/Income deposits
    payroll_deposits: List[PayrollDeposit]
    estimated_monthly_income: Optional[Decimal]
    income_consistency: str  # CONSISTENT, VARIABLE, IRREGULAR

    # Recurring payments (undisclosed obligations)
    recurring_payments: List[RecurringPayment]
    total_monthly_obligations: Decimal
    undisclosed_obligations: List[RecurringPayment]

    # Risk assessment
    risk_score: int  # 0-100
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    flags: List[str]
    recommendations: List[str]
    tasks_to_create: List[Dict]

    # AI analysis
    ai_summary: Optional[str]
    ai_confidence: int

    success: bool = True
    error: Optional[str] = None


# =============================================================================
# SERVICE
# =============================================================================

class BankStatementAnalyzerService:
    """
    AI-powered bank statement analysis for mortgage underwriting.

    Analyzes bank statements to identify:
    1. Large deposits requiring sourcing (per Fannie Mae/FHA guidelines)
    2. NSF/overdraft events (underwriting concern)
    3. IRS payments (tax liens, payment plans)
    4. Payroll deposit patterns (income verification)
    5. Recurring undisclosed debts
    6. Suspicious activity (structuring, round deposits)
    7. Balance trends and sufficiency for closing

    Generates tasks for:
    - Each large deposit needing sourcing letter/documentation
    - NSF explanation letters
    - IRS payment plan documentation
    - Undisclosed debt verification
    """

    def __init__(self, db: Session):
        self.db = db
        self._anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self._model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    # =========================================================================
    # 1. MAIN ENTRY POINT
    # =========================================================================

    def analyze_statements(
        self,
        loan_id: int,
        borrower_id: int,
    ) -> BankStatementAnalysis:
        """
        Main entry point: gather bank statement documents, extract
        transaction data, run all analysis modules, generate flags/tasks,
        save results, and return a comprehensive analysis.
        """
        start_ms = int(time.time() * 1000)

        try:
            # Step 1: gather all bank statement documents with OCR text
            docs = self._gather_statements(loan_id, borrower_id)

            if not docs:
                return BankStatementAnalysis(
                    loan_id=loan_id,
                    document_ids=[],
                    statement_period_start=None,
                    statement_period_end=None,
                    account_type="UNKNOWN",
                    institution_name=None,
                    beginning_balance=None,
                    ending_balance=None,
                    average_daily_balance=None,
                    lowest_balance=None,
                    lowest_balance_date=None,
                    large_deposits=[],
                    total_large_deposits=ZERO,
                    deposits_needing_sourcing=0,
                    nsf_events=[],
                    nsf_count=0,
                    nsf_severity="LOW",
                    total_nsf_fees=ZERO,
                    overdraft_days=0,
                    irs_payments=[],
                    total_irs_payments=ZERO,
                    irs_payment_plan_detected=False,
                    payroll_deposits=[],
                    estimated_monthly_income=None,
                    income_consistency="IRREGULAR",
                    recurring_payments=[],
                    total_monthly_obligations=ZERO,
                    undisclosed_obligations=[],
                    risk_score=0,
                    risk_level="LOW",
                    flags=["NO_BANK_STATEMENTS"],
                    recommendations=[
                        "Upload bank statements (most recent 2-3 months) to begin "
                        "asset verification and deposit analysis."
                    ],
                    tasks_to_create=[],
                    ai_summary=None,
                    ai_confidence=0,
                    success=False,
                    error="No bank statement documents found for this borrower.",
                )

            doc_ids = [d["doc_id"] for d in docs]

            # Step 2: extract transactions from each statement
            all_transactions: List[Dict] = []
            for doc in docs:
                ocr_text = doc.get("ocr_text") or ""
                if not ocr_text.strip():
                    continue

                # Try AI extraction first, fall back to regex
                txns = self._extract_transactions_with_ai(ocr_text)
                if not txns:
                    txns = self._extract_transactions(ocr_text)
                all_transactions.extend(txns)

            # Sort transactions by date
            all_transactions.sort(key=lambda t: t.get("date", "0000-00-00"))

            # Step 3: extract metadata from extraction fields
            metadata = self._extract_metadata(docs)

            # Step 4: determine borrower name for payroll matching
            borrower_name = self._get_borrower_name(loan_id)

            # Step 5: run all analysis modules
            large_deposits = self.analyze_large_deposits(all_transactions, borrower_name)

            nsf_events, nsf_count, nsf_severity, total_nsf_fees = self.analyze_nsf_events(
                all_transactions
            )

            irs_payments, total_irs, irs_payment_plan = self.analyze_irs_payments(
                all_transactions
            )

            payroll_deposits, est_monthly_income, income_consistency = self.analyze_payroll_deposits(
                all_transactions
            )

            recurring_payments = self.analyze_recurring_payments(all_transactions)

            structuring_flags = self._detect_structuring(all_transactions)

            # Step 6: calculate balance metrics
            balances = self._analyze_balances(all_transactions, metadata)

            # Step 7: identify undisclosed obligations
            undisclosed = [rp for rp in recurring_payments if not rp.is_disclosed]
            total_monthly_obligations = sum(
                (rp.average_amount for rp in recurring_payments),
                ZERO,
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # Count overdraft days (negative balance days)
            overdraft_days = self._count_overdraft_days(all_transactions)

            # Build preliminary analysis
            analysis = BankStatementAnalysis(
                loan_id=loan_id,
                document_ids=doc_ids,
                statement_period_start=metadata.get("period_start"),
                statement_period_end=metadata.get("period_end"),
                account_type=metadata.get("account_type", "CHECKING"),
                institution_name=metadata.get("institution"),
                beginning_balance=balances.get("beginning"),
                ending_balance=balances.get("ending"),
                average_daily_balance=balances.get("average_daily"),
                lowest_balance=balances.get("lowest"),
                lowest_balance_date=balances.get("lowest_date"),
                large_deposits=large_deposits,
                total_large_deposits=sum(
                    (ld.amount for ld in large_deposits), ZERO
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
                deposits_needing_sourcing=len(
                    [ld for ld in large_deposits if ld.needs_sourcing]
                ),
                nsf_events=nsf_events,
                nsf_count=nsf_count,
                nsf_severity=nsf_severity,
                total_nsf_fees=total_nsf_fees,
                overdraft_days=overdraft_days,
                irs_payments=irs_payments,
                total_irs_payments=total_irs,
                irs_payment_plan_detected=irs_payment_plan,
                payroll_deposits=payroll_deposits,
                estimated_monthly_income=est_monthly_income,
                income_consistency=income_consistency,
                recurring_payments=recurring_payments,
                total_monthly_obligations=total_monthly_obligations,
                undisclosed_obligations=undisclosed,
                risk_score=0,
                risk_level="LOW",
                flags=[],
                recommendations=[],
                tasks_to_create=[],
                ai_summary=None,
                ai_confidence=0,
            )

            # Step 8: generate flags (including structuring flags)
            analysis.flags = self._generate_flags(analysis)
            analysis.flags.extend(structuring_flags)

            # Step 9: calculate risk score
            analysis.risk_score, analysis.risk_level = self._calculate_risk_score(analysis)

            # Step 10: generate recommendations and tasks
            analysis.recommendations = self._generate_recommendations(analysis)
            analysis.tasks_to_create = self._generate_tasks(analysis)

            # Step 11: generate AI summary
            analysis.ai_summary = self._generate_ai_summary(analysis)

            # Calculate AI confidence from transaction extraction quality
            if all_transactions:
                txns_with_amounts = len([t for t in all_transactions if t.get("amount")])
                analysis.ai_confidence = min(
                    95, int((txns_with_amounts / len(all_transactions)) * 100)
                )
            else:
                analysis.ai_confidence = 0

            # Step 12: persist results
            duration_ms = int(time.time() * 1000) - start_ms
            self.save_analysis(analysis, duration_ms)

            return analysis

        except Exception as e:
            logger.exception(
                f"Bank statement analysis failed for loan={loan_id} "
                f"borrower={borrower_id}: {e}"
            )
            return BankStatementAnalysis(
                loan_id=loan_id,
                document_ids=[],
                statement_period_start=None,
                statement_period_end=None,
                account_type="UNKNOWN",
                institution_name=None,
                beginning_balance=None,
                ending_balance=None,
                average_daily_balance=None,
                lowest_balance=None,
                lowest_balance_date=None,
                large_deposits=[],
                total_large_deposits=ZERO,
                deposits_needing_sourcing=0,
                nsf_events=[],
                nsf_count=0,
                nsf_severity="LOW",
                total_nsf_fees=ZERO,
                overdraft_days=0,
                irs_payments=[],
                total_irs_payments=ZERO,
                irs_payment_plan_detected=False,
                payroll_deposits=[],
                estimated_monthly_income=None,
                income_consistency="IRREGULAR",
                recurring_payments=[],
                total_monthly_obligations=ZERO,
                undisclosed_obligations=[],
                risk_score=0,
                risk_level="LOW",
                flags=[],
                recommendations=[],
                tasks_to_create=[],
                ai_summary=None,
                ai_confidence=0,
                success=False,
                error=str(e),
            )

    # =========================================================================
    # 2. GATHER STATEMENTS
    # =========================================================================

    def _gather_statements(
        self,
        loan_id: int,
        borrower_id: int,
    ) -> List[Dict]:
        """
        Query smart_documents for BANK_STATEMENT type documents, then join
        with smart_document_extractions to get extracted field data and OCR
        text. Returns list of dicts with keys: doc_id, doc_type, ocr_text,
        uploaded_at, file_name, extracted_fields, confidence_scores,
        overall_confidence.
        """
        rows = self.db.execute(
            text("""
                SELECT
                    sd.id              AS doc_id,
                    sd.doc_type        AS doc_type,
                    sd.ocr_text        AS ocr_text,
                    sd.uploaded_at     AS uploaded_at,
                    sd.file_name       AS file_name,
                    sd.extracted_dates AS extracted_dates,
                    sde.extracted_fields  AS extracted_fields,
                    sde.confidence_scores AS confidence_scores,
                    sde.overall_confidence AS overall_confidence
                FROM smart_documents sd
                LEFT JOIN smart_document_extractions sde
                    ON sde.document_id = sd.id
                WHERE sd.loan_id = :loan_id
                  AND sd.borrower_id = :borrower_id
                  AND sd.doc_type = :doc_type
                  AND sd.status NOT IN ('REJECTED', 'EXPIRED')
                ORDER BY sd.uploaded_at DESC
            """),
            {
                "loan_id": loan_id,
                "borrower_id": borrower_id,
                "doc_type": BANK_STATEMENT_DOC_TYPE,
            },
        ).fetchall()

        results = []
        for row in rows:
            extracted = row.extracted_fields
            if isinstance(extracted, str):
                try:
                    extracted = json.loads(extracted)
                except (json.JSONDecodeError, TypeError):
                    extracted = {}

            confidence_scores = row.confidence_scores
            if isinstance(confidence_scores, str):
                try:
                    confidence_scores = json.loads(confidence_scores)
                except (json.JSONDecodeError, TypeError):
                    confidence_scores = {}

            extracted_dates = row.extracted_dates
            if isinstance(extracted_dates, str):
                try:
                    extracted_dates = json.loads(extracted_dates)
                except (json.JSONDecodeError, TypeError):
                    extracted_dates = {}

            results.append({
                "doc_id": row.doc_id,
                "doc_type": str(row.doc_type) if row.doc_type else None,
                "ocr_text": row.ocr_text,
                "uploaded_at": row.uploaded_at,
                "file_name": row.file_name,
                "extracted_dates": extracted_dates or {},
                "extracted_fields": extracted or {},
                "confidence_scores": confidence_scores or {},
                "overall_confidence": row.overall_confidence or 0,
            })

        return results

    # =========================================================================
    # 3. EXTRACT TRANSACTIONS (REGEX)
    # =========================================================================

    def _extract_transactions(self, ocr_text: str) -> List[Dict]:
        """
        Parse bank statement OCR text into structured transactions using
        regex patterns for common bank statement formats.

        Each transaction dict contains:
            date, description, amount, type (debit/credit), balance

        Returns list sorted by date ascending.
        """
        transactions: List[Dict] = []

        # Normalize line endings and collapse excessive whitespace
        text_lines = ocr_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        # Common bank statement formats:
        # Format 1: MM/DD/YYYY  Description  Amount  Balance
        # Format 2: MM/DD  Description  -$1,234.56  $5,678.90
        # Format 3: Date | Description | Debit | Credit | Balance

        # Currency amount pattern (handles $, commas, optional negative/parens)
        amt_pat = r"[-]?\$?\s*[\(\-]?\s*([\d,]+\.?\d{0,2})\s*\)?"

        # Date patterns
        date_patterns = [
            r"(\d{1,2}/\d{1,2}/\d{4})",      # MM/DD/YYYY
            r"(\d{1,2}/\d{1,2}/\d{2})",       # MM/DD/YY
            r"(\d{1,2}-\d{1,2}-\d{4})",       # MM-DD-YYYY
            r"(\d{4}-\d{2}-\d{2})",           # YYYY-MM-DD
        ]

        combined_date_pattern = "|".join(f"(?:{p})" for p in date_patterns)

        # Full transaction line pattern:
        # date  description  amount(s)  optional_balance
        line_pattern = re.compile(
            rf"^\s*(?:{combined_date_pattern})\s+"   # date
            rf"(.+?)\s+"                              # description (non-greedy)
            rf"({amt_pat})"                           # amount
            rf"(?:\s+{amt_pat})?\s*$",                # optional balance
            re.MULTILINE,
        )

        # Simpler fallback: just date + description + currency amount
        simple_pattern = re.compile(
            rf"^\s*(\d{{1,2}}[/-]\d{{1,2}}(?:[/-]\d{{2,4}})?)\s+"
            rf"(.+?)\s+"
            rf"(-?\$?\s*[\d,]+\.?\d{{0,2}})\s*$",
            re.MULTILINE,
        )

        pending_description = None
        pending_date = None

        for line in text_lines:
            line = line.strip()
            if not line:
                continue

            # Try the comprehensive pattern first
            match = line_pattern.search(line)
            if not match:
                # Try the simpler pattern
                simple_match = simple_pattern.search(line)
                if simple_match:
                    raw_date = simple_match.group(1)
                    description = simple_match.group(2).strip()
                    raw_amount = simple_match.group(3).strip()

                    parsed_date = self._normalize_date(raw_date)
                    amount = self._parse_amount(raw_amount)

                    if parsed_date and amount is not None:
                        is_debit = amount < ZERO or raw_amount.startswith("-")
                        txn = {
                            "date": parsed_date,
                            "description": description,
                            "amount": abs(amount),
                            "type": "debit" if is_debit else "credit",
                            "balance": None,
                        }
                        transactions.append(txn)
                        pending_description = None
                        pending_date = None
                        continue

                # Check if this is a continuation of a multi-line description
                if pending_date and pending_description:
                    # Look for an amount on this line
                    amt_match = re.search(
                        r"(-?\$?\s*[\d,]+\.\d{2})\s*$", line
                    )
                    if amt_match:
                        amount = self._parse_amount(amt_match.group(1))
                        full_desc = f"{pending_description} {line[:amt_match.start()].strip()}"
                        if amount is not None:
                            is_debit = amount < ZERO
                            transactions.append({
                                "date": pending_date,
                                "description": full_desc.strip(),
                                "amount": abs(amount),
                                "type": "debit" if is_debit else "credit",
                                "balance": None,
                            })
                        pending_description = None
                        pending_date = None
                    else:
                        # Append to description
                        pending_description += " " + line
                else:
                    # Check if this line starts with a date but has no amount
                    # (multi-line transaction start)
                    date_only_match = re.match(
                        rf"^\s*(\d{{1,2}}[/-]\d{{1,2}}(?:[/-]\d{{2,4}})?)\s+(.+)$",
                        line,
                    )
                    if date_only_match:
                        raw_date = date_only_match.group(1)
                        parsed_date = self._normalize_date(raw_date)
                        if parsed_date:
                            pending_date = parsed_date
                            pending_description = date_only_match.group(2).strip()
                continue

            # Extract groups from the comprehensive pattern
            groups = match.groups()
            # Find which date group matched
            raw_date = None
            for i in range(4):  # 4 date patterns
                if groups[i]:
                    raw_date = groups[i]
                    break

            description = groups[4].strip() if len(groups) > 4 and groups[4] else ""
            raw_amount = groups[5] if len(groups) > 5 and groups[5] else ""

            parsed_date = self._normalize_date(raw_date) if raw_date else None
            amount = self._parse_amount(raw_amount)

            if parsed_date and amount is not None:
                is_debit = (
                    amount < ZERO
                    or "(" in raw_amount
                    or raw_amount.strip().startswith("-")
                )
                transactions.append({
                    "date": parsed_date,
                    "description": description,
                    "amount": abs(amount),
                    "type": "debit" if is_debit else "credit",
                    "balance": None,
                })

        # De-duplicate: same date + description + amount
        seen = set()
        unique_txns = []
        for txn in transactions:
            key = (txn["date"], txn["description"][:50], str(txn["amount"]), txn["type"])
            if key not in seen:
                seen.add(key)
                unique_txns.append(txn)

        unique_txns.sort(key=lambda t: t.get("date", "0000-00-00"))
        return unique_txns

    # =========================================================================
    # 4. EXTRACT TRANSACTIONS WITH AI
    # =========================================================================

    def _extract_transactions_with_ai(self, ocr_text: str) -> List[Dict]:
        """
        Use Claude API to extract structured transactions from bank
        statement OCR text. More accurate than regex for complex or
        multi-column formats. Falls back to empty list if AI unavailable.
        """
        if not HAS_ANTHROPIC or not self._anthropic_key:
            return []

        # Limit input size to control cost/latency
        truncated = ocr_text[:40000]

        try:
            client = Anthropic(api_key=self._anthropic_key)

            prompt = f"""You are a mortgage underwriting document specialist.
Extract ALL transactions from this bank statement text. Return ONLY a JSON array.

BANK STATEMENT TEXT:
{truncated}

Return a JSON array where each element is:
{{
    "date": "YYYY-MM-DD",
    "description": "transaction description",
    "amount": 1234.56,
    "type": "debit" or "credit",
    "balance": 5678.90 or null
}}

Rules:
- "amount" is always a positive number
- "type" is "debit" for withdrawals/payments/fees, "credit" for deposits/transfers in
- Include ALL transactions, even small ones
- Use YYYY-MM-DD format for dates
- If the year is not shown, infer it from context (statement date, surrounding transactions)
- For currency values, return numbers only (no $ or commas)
- If balance after transaction is shown, include it
- Respond with ONLY the JSON array, no explanation"""

            response = resilient_ai_call(
                client=client,
                model=self._model,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
                operation_name="extract_bank_transactions",
            )

            if response is None:
                logger.warning("AI transaction extraction failed after retries")
                return []

            response_text = response.content[0].text.strip()

            # Strip markdown code fences if present
            if response_text.startswith("```"):
                response_text = re.sub(r"^```json?\n?", "", response_text)
                response_text = re.sub(r"\n?```$", "", response_text)

            parsed = json.loads(response_text)

            if not isinstance(parsed, list):
                logger.warning("AI extraction returned non-list; falling back")
                return []

            # Validate and normalize each transaction
            valid_txns: List[Dict] = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                try:
                    txn = {
                        "date": str(item.get("date", "")),
                        "description": str(item.get("description", "")),
                        "amount": self._to_decimal(item.get("amount")),
                        "type": str(item.get("type", "debit")).lower(),
                        "balance": (
                            self._to_decimal(item["balance"])
                            if item.get("balance") is not None
                            else None
                        ),
                    }
                    # Must have a valid date and non-zero amount
                    if txn["date"] and txn["amount"] > ZERO:
                        if txn["type"] not in ("debit", "credit"):
                            txn["type"] = "debit"
                        valid_txns.append(txn)
                except Exception:
                    continue

            logger.info(
                f"AI extracted {len(valid_txns)} transactions from bank statement"
            )
            return valid_txns

        except Exception as e:
            logger.warning(f"AI transaction extraction failed: {e}")
            return []

    # =========================================================================
    # 5. ANALYZE LARGE DEPOSITS
    # =========================================================================

    def analyze_large_deposits(
        self,
        transactions: List[Dict],
        borrower_name: str,
    ) -> List[LargeDeposit]:
        """
        Find all credit transactions >= LARGE_DEPOSIT_THRESHOLD and classify
        each deposit as payroll, transfer, or requiring sourcing.

        Per Fannie Mae Selling Guide B3-4.2-01, large deposits not from a
        documented source require a written explanation and supporting docs.

        Returns list sorted by amount descending.
        """
        credits = [
            t for t in transactions
            if t.get("type") == "credit" and t.get("amount", ZERO) >= LARGE_DEPOSIT_THRESHOLD
        ]

        if not credits:
            return []

        # Build a set of known payroll amounts (for consistency detection)
        payroll_amounts: List[Decimal] = []
        for t in transactions:
            if t.get("type") == "credit":
                desc_lower = (t.get("description") or "").lower()
                if any(kw in desc_lower for kw in PAYROLL_KEYWORDS):
                    payroll_amounts.append(self._to_decimal(t.get("amount")))

        results: List[LargeDeposit] = []
        for txn in credits:
            amount = self._to_decimal(txn.get("amount"))
            desc = txn.get("description", "")
            desc_lower = desc.lower()
            txn_date = txn.get("date", "")

            # Classify: payroll?
            is_payroll = any(kw in desc_lower for kw in PAYROLL_KEYWORDS)

            # If not keyword-matched, check if amount is consistent with
            # known payroll deposits (within 5%)
            if not is_payroll and payroll_amounts:
                for pa in payroll_amounts:
                    if pa > ZERO:
                        variance = abs(amount - pa) / pa
                        if variance < Decimal("0.05"):
                            is_payroll = True
                            break

            # Classify: transfer?
            transfer_keywords = [
                "transfer", "xfer", "trnsfr", "from savings",
                "from checking", "mobile deposit", "online transfer",
                "zelle", "venmo", "paypal",
            ]
            is_transfer = any(kw in desc_lower for kw in transfer_keywords)

            # Needs sourcing if not payroll AND not an internal transfer
            needs_sourcing = not is_payroll and not is_transfer

            # Determine risk level
            risk_level = "LOW"
            if needs_sourcing:
                risk_level = "MEDIUM"
                if amount >= NEAR_STRUCTURING_THRESHOLD:
                    risk_level = "HIGH"
                elif amount >= Decimal("5000.00"):
                    risk_level = "MEDIUM"

            # Build sourcing explanation if needed
            sourcing_explanation = None
            if needs_sourcing:
                sourcing_explanation = (
                    f"Deposit of ${amount:,.2f} on {txn_date} requires sourcing. "
                    f"Obtain a letter of explanation and supporting documentation "
                    f"(e.g., canceled check, gift letter, sale proceeds)."
                )

            notes = ""
            if is_payroll:
                notes = "Identified as payroll/direct deposit"
            elif is_transfer:
                notes = "Identified as account transfer"
            elif amount >= NEAR_STRUCTURING_THRESHOLD:
                notes = "Large deposit near CTR threshold -- verify source"
            else:
                notes = "Non-payroll deposit requires sourcing documentation"

            results.append(LargeDeposit(
                date=txn_date,
                amount=amount,
                description=desc,
                is_payroll=is_payroll,
                is_transfer=is_transfer,
                needs_sourcing=needs_sourcing,
                sourcing_explanation=sourcing_explanation,
                risk_level=risk_level,
                notes=notes,
            ))

        # Sort by amount descending
        results.sort(key=lambda ld: ld.amount, reverse=True)
        return results

    # =========================================================================
    # 6. ANALYZE NSF EVENTS
    # =========================================================================

    def analyze_nsf_events(
        self,
        transactions: List[Dict],
    ) -> Tuple[List[NSFEvent], int, str, Decimal]:
        """
        Find NSF/overdraft transactions and negative balance occurrences.

        Returns:
            (events, count, severity, total_fees)
        """
        nsf_keywords = [
            "nsf", "overdraft", "insufficient", "returned item",
            "od fee", "overdraft fee", "non-sufficient", "return check",
            "returned check", "nsf fee", "od charge",
        ]

        events: List[NSFEvent] = []
        total_fees = ZERO

        for txn in transactions:
            desc_lower = (txn.get("description") or "").lower()
            amount = self._to_decimal(txn.get("amount"))

            if any(kw in desc_lower for kw in nsf_keywords):
                # Determine if this is a fee or the original returned item
                fee_charged = None
                if "fee" in desc_lower or "charge" in desc_lower:
                    fee_charged = amount
                    total_fees += amount

                events.append(NSFEvent(
                    date=txn.get("date", ""),
                    amount=amount,
                    description=txn.get("description", ""),
                    resulting_balance=(
                        self._to_decimal(txn["balance"])
                        if txn.get("balance") is not None
                        else None
                    ),
                    fee_charged=fee_charged,
                ))

        count = len(events)

        # Determine severity
        if count >= 5:
            severity = "CRITICAL"
        elif count in NSF_SEVERITY_MAP:
            severity = NSF_SEVERITY_MAP[count]
        else:
            severity = "HIGH"

        return (events, count, severity, total_fees)

    # =========================================================================
    # 7. ANALYZE IRS PAYMENTS
    # =========================================================================

    def analyze_irs_payments(
        self,
        transactions: List[Dict],
    ) -> Tuple[List[IRSPayment], Decimal, bool]:
        """
        Find payments matching IRS_KEYWORDS and classify the payment type.

        Returns:
            (payments, total_amount, is_payment_plan_detected)
        """
        payments: List[IRSPayment] = []
        total = ZERO

        for txn in transactions:
            if txn.get("type") != "debit":
                continue

            desc_lower = (txn.get("description") or "").lower()
            if not any(kw in desc_lower for kw in IRS_KEYWORDS):
                continue

            amount = self._to_decimal(txn.get("amount"))
            total += amount

            # Classify payment type
            payment_type = "UNKNOWN"
            if "estimated" in desc_lower or "eftps" in desc_lower:
                payment_type = "ESTIMATED_TAX"
            elif "penalty" in desc_lower or "interest" in desc_lower:
                payment_type = "PENALTY"

            payments.append(IRSPayment(
                date=txn.get("date", ""),
                amount=amount,
                description=txn.get("description", ""),
                payment_type=payment_type,
                is_recurring=False,  # updated below
            ))

        # Detect payment plan: 3+ payments of similar amounts at regular intervals
        irs_payment_plan = False
        if len(payments) >= 3:
            # Check if amounts are consistent (within 10% of each other)
            amounts = [p.amount for p in payments]
            avg_amount = sum(amounts, ZERO) / len(amounts)
            if avg_amount > ZERO:
                consistent = all(
                    abs(a - avg_amount) / avg_amount < Decimal("0.10")
                    for a in amounts
                )
                if consistent:
                    irs_payment_plan = True
                    for p in payments:
                        p.is_recurring = True
                        if p.payment_type == "UNKNOWN":
                            p.payment_type = "PAYMENT_PLAN"

        # Also check for estimated tax: quarterly pattern
        if not irs_payment_plan and len(payments) >= 2:
            estimated_payments = [
                p for p in payments if p.payment_type == "ESTIMATED_TAX"
            ]
            if len(estimated_payments) >= 2:
                # Estimated tax payments are expected; not a red flag
                for p in estimated_payments:
                    p.is_recurring = True

        return (payments, total, irs_payment_plan)

    # =========================================================================
    # 8. ANALYZE PAYROLL DEPOSITS
    # =========================================================================

    def analyze_payroll_deposits(
        self,
        transactions: List[Dict],
    ) -> Tuple[List[PayrollDeposit], Optional[Decimal], str]:
        """
        Identify payroll/salary deposits using PAYROLL_KEYWORDS and pattern
        analysis. Determine frequency and consistency.

        Returns:
            (deposits, estimated_monthly_income, consistency)
        """
        payroll_txns: List[Dict] = []
        for txn in transactions:
            if txn.get("type") != "credit":
                continue
            desc_lower = (txn.get("description") or "").lower()
            if any(kw in desc_lower for kw in PAYROLL_KEYWORDS):
                payroll_txns.append(txn)

        if not payroll_txns:
            return ([], None, "IRREGULAR")

        # Determine source name from the most common description pattern
        desc_counter: Dict[str, int] = defaultdict(int)
        for txn in payroll_txns:
            # Extract a cleaned source name from description
            source = self._extract_payroll_source(txn.get("description", ""))
            desc_counter[source] += 1

        primary_source = max(desc_counter, key=desc_counter.get) if desc_counter else "Unknown"

        # Analyze frequency from date intervals
        dates = []
        for txn in payroll_txns:
            try:
                d = datetime.strptime(txn["date"], "%Y-%m-%d").date()
                dates.append(d)
            except (ValueError, KeyError):
                continue

        dates.sort()
        frequency = self._determine_frequency(dates)

        # Assess consistency: are amounts within 5% of each other?
        amounts = [self._to_decimal(t.get("amount")) for t in payroll_txns]
        amounts = [a for a in amounts if a > ZERO]

        consistency = "IRREGULAR"
        if len(amounts) >= 2:
            avg_amount = sum(amounts, ZERO) / len(amounts)
            if avg_amount > ZERO:
                max_variance = max(
                    abs(a - avg_amount) / avg_amount for a in amounts
                )
                if max_variance < Decimal("0.05"):
                    consistency = "CONSISTENT"
                elif max_variance < Decimal("0.15"):
                    consistency = "VARIABLE"
                else:
                    consistency = "IRREGULAR"

        # Build deposit list
        deposits: List[PayrollDeposit] = []
        for txn in payroll_txns:
            amount = self._to_decimal(txn.get("amount"))
            is_consistent = consistency == "CONSISTENT"

            deposits.append(PayrollDeposit(
                date=txn.get("date", ""),
                amount=amount,
                source=primary_source,
                frequency=frequency,
                is_consistent=is_consistent,
            ))

        # Estimate monthly income
        estimated_monthly = None
        if amounts:
            total_deposits = sum(amounts, ZERO)

            if frequency == "WEEKLY":
                # Annualize then divide by 12
                estimated_monthly = (total_deposits / len(amounts) * 52 / 12).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
            elif frequency == "BIWEEKLY":
                estimated_monthly = (total_deposits / len(amounts) * 26 / 12).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
            elif frequency == "SEMIMONTHLY":
                estimated_monthly = (total_deposits / len(amounts) * 24 / 12).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
            elif frequency == "MONTHLY":
                estimated_monthly = (total_deposits / len(amounts)).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
            else:
                # Unknown frequency: sum deposits / number of months covered
                if len(dates) >= 2:
                    days_span = (dates[-1] - dates[0]).days
                    months_span = max(1, days_span / 30.44)
                    estimated_monthly = (total_deposits / Decimal(str(months_span))).quantize(
                        TWO_PLACES, rounding=ROUND_HALF_UP
                    )

        return (deposits, estimated_monthly, consistency)

    # =========================================================================
    # 9. ANALYZE RECURRING PAYMENTS
    # =========================================================================

    def analyze_recurring_payments(
        self,
        transactions: List[Dict],
    ) -> List[RecurringPayment]:
        """
        Group debits by payee similarity to identify recurring payment
        patterns. Categorize using RECURRING_CATEGORIES and flag potential
        undisclosed obligations.
        """
        debits = [
            t for t in transactions
            if t.get("type") == "debit" and self._to_decimal(t.get("amount")) > ZERO
        ]

        if not debits:
            return []

        # Group debits by normalized payee description
        payee_groups: Dict[str, List[Dict]] = defaultdict(list)
        for txn in debits:
            normalized = self._normalize_payee(txn.get("description", ""))
            if normalized:
                payee_groups[normalized].append(txn)

        results: List[RecurringPayment] = []

        for payee, txn_group in payee_groups.items():
            # Need at least 2 occurrences to be considered recurring
            if len(txn_group) < 2:
                continue

            amounts = [self._to_decimal(t.get("amount")) for t in txn_group]
            amounts = [a for a in amounts if a > ZERO]
            if not amounts:
                continue

            avg_amount = (sum(amounts, ZERO) / len(amounts)).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
            total_amount = sum(amounts, ZERO).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

            # Check amount consistency (within 20% means likely same obligation)
            if avg_amount > ZERO:
                max_var = max(abs(a - avg_amount) / avg_amount for a in amounts)
                if max_var > Decimal("0.50"):
                    # Too much variance -- probably not the same recurring payment
                    continue

            # Determine frequency
            txn_dates = []
            for t in txn_group:
                try:
                    d = datetime.strptime(t["date"], "%Y-%m-%d").date()
                    txn_dates.append(d)
                except (ValueError, KeyError):
                    continue

            txn_dates.sort()
            frequency = self._determine_frequency(txn_dates)

            # Categorize
            category = "other"
            payee_lower = payee.lower()
            for cat, keywords in RECURRING_CATEGORIES.items():
                if any(kw in payee_lower for kw in keywords):
                    category = cat
                    break

            # Mark as undisclosed -- LO will need to verify against credit report
            # Mortgage/rent, utilities, and insurance are expected and typically
            # not "undisclosed" in the credit-report sense.
            expected_categories = {"mortgage_rent", "utilities", "insurance"}
            is_disclosed = category in expected_categories

            results.append(RecurringPayment(
                category=category,
                payee=payee,
                average_amount=avg_amount,
                frequency=frequency,
                occurrences=len(txn_group),
                total_amount=total_amount,
                is_disclosed=is_disclosed,
                dates=[t.get("date", "") for t in txn_group],
            ))

        # Sort by average amount descending
        results.sort(key=lambda rp: rp.average_amount, reverse=True)
        return results

    # =========================================================================
    # 10. DETECT STRUCTURING
    # =========================================================================

    def _detect_structuring(self, transactions: List[Dict]) -> List[str]:
        """
        Check for patterns that may indicate structuring:
        1. Deposits between $9,000 and $9,999 (just below CTR threshold)
        2. Multiple deposits on the same day that sum to > $10,000
        3. Pattern of round-number cash deposits

        Returns list of flag strings.
        """
        flags: List[str] = []
        credits = [
            t for t in transactions
            if t.get("type") == "credit"
        ]

        if not credits:
            return flags

        # Check 1: deposits just below $10,000
        near_threshold = [
            t for t in credits
            if NEAR_STRUCTURING_THRESHOLD <= self._to_decimal(t.get("amount")) < STRUCTURING_THRESHOLD
        ]
        if near_threshold:
            for t in near_threshold:
                flags.append(
                    f"STRUCTURING_INDICATOR: Deposit of "
                    f"${self._to_decimal(t.get('amount')):,.2f} on {t.get('date', '?')} "
                    f"is just below the $10,000 CTR reporting threshold"
                )

        # Check 2: multiple same-day deposits summing to > $10,000
        daily_totals: Dict[str, Decimal] = defaultdict(lambda: ZERO)
        daily_counts: Dict[str, int] = defaultdict(int)
        for t in credits:
            dt = t.get("date", "")
            if dt:
                daily_totals[dt] += self._to_decimal(t.get("amount"))
                daily_counts[dt] += 1

        for dt, total in daily_totals.items():
            if total >= STRUCTURING_THRESHOLD and daily_counts[dt] >= 2:
                flags.append(
                    f"STRUCTURING_INDICATOR: Multiple deposits on {dt} "
                    f"total ${total:,.2f} (exceeds $10,000 threshold across "
                    f"{daily_counts[dt]} transactions)"
                )

        # Check 3: pattern of round-number deposits (e.g., $5,000, $3,000)
        round_deposits = []
        for t in credits:
            amount = self._to_decimal(t.get("amount"))
            # Round means divisible by 1000 and >= 1000
            if amount >= Decimal("1000") and amount % Decimal("1000") == ZERO:
                round_deposits.append(t)

        if len(round_deposits) >= 3:
            total_round = sum(
                self._to_decimal(t.get("amount")) for t in round_deposits
            )
            flags.append(
                f"STRUCTURING_INDICATOR: {len(round_deposits)} round-number "
                f"cash deposits detected totaling ${total_round:,.2f} -- "
                f"review for potential structuring"
            )

        return flags

    # =========================================================================
    # 11. CALCULATE RISK SCORE
    # =========================================================================

    def _calculate_risk_score(
        self,
        analysis: BankStatementAnalysis,
    ) -> Tuple[int, str]:
        """
        Calculate a composite risk score (0-100) based on all findings.

        Scoring:
        - NSF events: +5 per event, max 25
        - Large deposits needing sourcing: +8 per deposit, max 30
        - IRS payment plan: +15
        - Structuring indicators: +20
        - Undisclosed recurring payments: +5 per, max 20
        - Negative balance days: +2 per day, max 15
        """
        score = 0

        # NSF events: +5 each, capped at 25
        score += min(25, analysis.nsf_count * 5)

        # Large deposits needing sourcing: +8 each, capped at 30
        score += min(30, analysis.deposits_needing_sourcing * 8)

        # IRS payment plan: +15
        if analysis.irs_payment_plan_detected:
            score += 15

        # Structuring indicators: +20 if any present
        structuring_flags = [
            f for f in analysis.flags if "STRUCTURING" in f
        ]
        if structuring_flags:
            score += 20

        # Undisclosed recurring payments: +5 each, capped at 20
        score += min(20, len(analysis.undisclosed_obligations) * 5)

        # Negative balance / overdraft days: +2 per day, capped at 15
        score += min(15, analysis.overdraft_days * 2)

        # Cap at 100
        score = min(100, score)

        # Determine risk level
        if score >= 70:
            risk_level = "CRITICAL"
        elif score >= 45:
            risk_level = "HIGH"
        elif score >= 20:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return (score, risk_level)

    # =========================================================================
    # 12. GENERATE FLAGS
    # =========================================================================

    def _generate_flags(self, analysis: BankStatementAnalysis) -> List[str]:
        """
        Generate human-readable flags from the analysis results.
        """
        flags: List[str] = []

        # Large deposits needing sourcing
        for ld in analysis.large_deposits:
            if ld.needs_sourcing:
                flags.append(
                    f"LARGE_DEPOSIT: ${ld.amount:,.2f} on {ld.date} "
                    f"requires sourcing documentation -- \"{ld.description[:60]}\""
                )

        # NSF/overdraft events
        if analysis.nsf_count > 0:
            flags.append(
                f"NSF_OVERDRAFT: {analysis.nsf_count} overdraft/NSF event(s) "
                f"in statement period (total fees: ${analysis.total_nsf_fees:,.2f})"
            )

        # IRS payments
        if analysis.irs_payment_plan_detected:
            flags.append(
                f"IRS_PAYMENT_PLAN: Regular payments to IRS detected "
                f"(${analysis.total_irs_payments:,.2f} total) -- need IRS "
                f"payment agreement and transcripts"
            )
        elif analysis.irs_payments:
            flags.append(
                f"IRS_PAYMENT: {len(analysis.irs_payments)} payment(s) to IRS "
                f"totaling ${analysis.total_irs_payments:,.2f} -- obtain tax "
                f"transcripts to verify no outstanding liens"
            )

        # Undisclosed debts
        for rp in analysis.undisclosed_obligations:
            flags.append(
                f"UNDISCLOSED_DEBT: Monthly payment of ${rp.average_amount:,.2f} "
                f"to \"{rp.payee[:40]}\" ({rp.category}) not verified on credit report"
            )

        # Low balance
        if analysis.lowest_balance is not None and analysis.lowest_balance < Decimal("100"):
            flags.append(
                f"LOW_BALANCE: Balance dropped to ${analysis.lowest_balance:,.2f} "
                f"on {analysis.lowest_balance_date or 'unknown date'} -- "
                f"verify sufficient reserves for closing"
            )

        # Overdraft days
        if analysis.overdraft_days > 0:
            flags.append(
                f"NEGATIVE_BALANCE: Account had negative balance on "
                f"{analysis.overdraft_days} day(s) during statement period"
            )

        # Income consistency
        if analysis.income_consistency == "IRREGULAR":
            flags.append(
                "IRREGULAR_INCOME: Payroll deposits show irregular pattern -- "
                "may indicate variable employment or multiple jobs"
            )

        return flags

    # =========================================================================
    # 13. GENERATE TASKS
    # =========================================================================

    def _generate_tasks(self, analysis: BankStatementAnalysis) -> List[Dict]:
        """
        Generate task definitions for each actionable item.
        Each task maps to the IncomeVerificationTask model schema.
        """
        tasks: List[Dict] = []

        # Task for each large deposit needing sourcing
        for ld in analysis.large_deposits:
            if ld.needs_sourcing:
                tasks.append({
                    "task_type": "review_large_deposit",
                    "title": f"Source deposit: ${ld.amount:,.2f} on {ld.date}",
                    "description": (
                        f"Large deposit of ${ld.amount:,.2f} on {ld.date} "
                        f"(\"{ld.description[:80]}\") requires sourcing per "
                        f"Fannie Mae guidelines."
                    ),
                    "priority": "high" if ld.risk_level == "HIGH" else "medium",
                    "ai_recommendation": (
                        f"Obtain a signed Letter of Explanation from the borrower "
                        f"describing the source of this ${ld.amount:,.2f} deposit. "
                        f"Supporting documentation required (e.g., canceled check, "
                        f"gift letter with donor bank statement, sale proceeds, "
                        f"insurance settlement)."
                    ),
                })

        # Task for NSF events
        if analysis.nsf_count > 0:
            priority = "critical" if analysis.nsf_severity == "CRITICAL" else "high"
            tasks.append({
                "task_type": "review_large_deposit",  # reuse closest task type
                "title": (
                    f"Obtain NSF/overdraft explanation "
                    f"({analysis.nsf_count} event{'s' if analysis.nsf_count != 1 else ''})"
                ),
                "description": (
                    f"{analysis.nsf_count} NSF/overdraft events detected with "
                    f"${analysis.total_nsf_fees:,.2f} in fees. Borrower must "
                    f"provide a written explanation."
                ),
                "priority": priority,
                "ai_recommendation": (
                    "Request a Letter of Explanation for each NSF/overdraft event. "
                    "Multiple NSFs are a significant underwriting concern and may "
                    "indicate cash-flow management issues. Document the borrower's "
                    "explanation and verify the account is now in good standing."
                ),
            })

        # Task for IRS payment plan
        if analysis.irs_payment_plan_detected:
            tasks.append({
                "task_type": "manual_override_needed",
                "title": "Obtain IRS payment plan documentation",
                "description": (
                    f"Regular payments to IRS detected totaling "
                    f"${analysis.total_irs_payments:,.2f}. Likely indicates an "
                    f"IRS installment agreement."
                ),
                "priority": "critical",
                "ai_recommendation": (
                    "Obtain the following: (1) IRS Installment Agreement letter "
                    "showing monthly payment amount and remaining balance, "
                    "(2) IRS Tax Transcripts for the last 3 years, (3) Proof of "
                    "timely payments for the last 12 months. The monthly IRS "
                    "payment must be included in DTI calculations."
                ),
            })
        elif analysis.irs_payments:
            tasks.append({
                "task_type": "manual_override_needed",
                "title": "Verify IRS payment status",
                "description": (
                    f"{len(analysis.irs_payments)} payment(s) to IRS detected. "
                    f"Verify no outstanding tax liens or payment plans."
                ),
                "priority": "high",
                "ai_recommendation": (
                    "Request IRS Tax Transcripts (4506-C) to verify no "
                    "outstanding federal tax liens. If payments are estimated "
                    "quarterly taxes, document as normal course of business."
                ),
            })

        # Tasks for undisclosed recurring debts
        for rp in analysis.undisclosed_obligations:
            if rp.average_amount >= Decimal("50.00"):
                tasks.append({
                    "task_type": "manual_override_needed",
                    "title": (
                        f"Verify undisclosed obligation: "
                        f"\"{rp.payee[:40]}\" -- ${rp.average_amount:,.2f}/mo"
                    ),
                    "description": (
                        f"Recurring {rp.frequency.lower()} payment of "
                        f"${rp.average_amount:,.2f} to \"{rp.payee}\" "
                        f"({rp.category}) detected in bank statements. "
                        f"Verify if this obligation appears on the credit report."
                    ),
                    "priority": (
                        "high" if rp.average_amount >= Decimal("200.00") else "medium"
                    ),
                    "ai_recommendation": (
                        f"Cross-reference this ${rp.average_amount:,.2f} "
                        f"monthly payment to \"{rp.payee[:40]}\" against the "
                        f"credit report. If not listed, it must be added to "
                        f"the DTI calculation as an undisclosed liability. "
                        f"Common exclusions: child support (verify with court "
                        f"order), alimony, and voluntary payroll deductions."
                    ),
                })

        return tasks

    # =========================================================================
    # 14. GENERATE AI SUMMARY
    # =========================================================================

    def _generate_ai_summary(self, analysis: BankStatementAnalysis) -> str:
        """
        Generate a natural-language summary of the bank statement analysis.
        Uses Claude API if available; falls back to template-based summary.
        """
        if HAS_ANTHROPIC and self._anthropic_key:
            try:
                return self._generate_ai_summary_with_claude(analysis)
            except Exception as e:
                logger.warning(f"AI summary generation failed: {e}")

        return self._generate_template_summary(analysis)

    def _generate_ai_summary_with_claude(
        self,
        analysis: BankStatementAnalysis,
    ) -> str:
        """Use Claude to generate a concise underwriting summary."""
        client = Anthropic(api_key=self._anthropic_key)

        findings = {
            "account_type": analysis.account_type,
            "institution": analysis.institution_name,
            "period": f"{analysis.statement_period_start} to {analysis.statement_period_end}",
            "ending_balance": (
                f"${analysis.ending_balance:,.2f}"
                if analysis.ending_balance is not None else "Unknown"
            ),
            "average_daily_balance": (
                f"${analysis.average_daily_balance:,.2f}"
                if analysis.average_daily_balance is not None else "Unknown"
            ),
            "large_deposits_needing_sourcing": analysis.deposits_needing_sourcing,
            "total_large_deposits": f"${analysis.total_large_deposits:,.2f}",
            "nsf_count": analysis.nsf_count,
            "nsf_severity": analysis.nsf_severity,
            "irs_payment_plan": analysis.irs_payment_plan_detected,
            "total_irs_payments": f"${analysis.total_irs_payments:,.2f}",
            "estimated_monthly_income": (
                f"${analysis.estimated_monthly_income:,.2f}"
                if analysis.estimated_monthly_income is not None else "Unknown"
            ),
            "income_consistency": analysis.income_consistency,
            "undisclosed_obligations_count": len(analysis.undisclosed_obligations),
            "total_monthly_obligations": f"${analysis.total_monthly_obligations:,.2f}",
            "risk_score": analysis.risk_score,
            "risk_level": analysis.risk_level,
            "flags": analysis.flags,
        }

        prompt = f"""You are a mortgage underwriter reviewing bank statement analysis results.
Write a concise 3-5 sentence summary of the key findings for the loan officer.

Focus on:
1. The most critical issues that need attention
2. Overall assessment of the borrower's financial health
3. Any blocking items for loan approval

Analysis findings:
{json.dumps(findings, indent=2)}

Write the summary as if speaking directly to the loan officer. Be professional
and specific. Do not use bullet points -- write flowing sentences."""

        response = resilient_ai_call(
            client=client,
            model=self._model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
            operation_name="generate_bank_statement_summary",
        )

        if response is None:
            logger.warning("AI summary generation failed after retries")
            return self._generate_template_summary(analysis)

        return response.content[0].text.strip()

    def _generate_template_summary(self, analysis: BankStatementAnalysis) -> str:
        """Fallback template-based summary when AI is unavailable."""
        parts = []

        # Opening
        if analysis.institution_name:
            parts.append(
                f"Analysis of {analysis.institution_name} "
                f"{analysis.account_type.lower()} account"
            )
        else:
            parts.append(
                f"Bank statement analysis ({analysis.account_type.lower()} account)"
            )

        if analysis.statement_period_start and analysis.statement_period_end:
            parts[-1] += (
                f" for period {analysis.statement_period_start} "
                f"to {analysis.statement_period_end}"
            )
        parts[-1] += "."

        # Balances
        if analysis.ending_balance is not None:
            parts.append(
                f"Ending balance: ${analysis.ending_balance:,.2f}."
            )

        # Key findings
        issues = []
        if analysis.deposits_needing_sourcing > 0:
            issues.append(
                f"{analysis.deposits_needing_sourcing} deposit(s) requiring sourcing "
                f"(${analysis.total_large_deposits:,.2f} total)"
            )
        if analysis.nsf_count > 0:
            issues.append(
                f"{analysis.nsf_count} NSF/overdraft event(s) "
                f"(severity: {analysis.nsf_severity})"
            )
        if analysis.irs_payment_plan_detected:
            issues.append("IRS payment plan detected")
        if analysis.undisclosed_obligations:
            issues.append(
                f"{len(analysis.undisclosed_obligations)} potential undisclosed "
                f"obligation(s)"
            )

        if issues:
            parts.append("Key findings: " + "; ".join(issues) + ".")
        else:
            parts.append("No significant concerns identified.")

        # Risk
        parts.append(
            f"Overall risk assessment: {analysis.risk_level} "
            f"(score: {analysis.risk_score}/100)."
        )

        return " ".join(parts)

    # =========================================================================
    # 15. COMPARE INCOME TO DEPOSITS
    # =========================================================================

    def compare_income_to_deposits(
        self,
        loan_id: int,
        stated_monthly_income: Decimal,
    ) -> Dict:
        """
        Compare stated income against actual deposit patterns found in the
        most recent bank statement analysis for this loan.

        Flags significant discrepancies:
        - Deposits significantly less than stated income (< 80%)
        - Deposits significantly more than stated income (> 130%)
        """
        # Get the most recent analysis results from income_calculations
        # where the analysis type suggests bank-statement origin
        row = self.db.execute(
            text("""
                SELECT
                    ai_flags,
                    total_qualifying_monthly_income,
                    source_documents
                FROM income_calculations
                WHERE loan_id = :loan_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"loan_id": loan_id},
        ).fetchone()

        # Also get deposit totals from our stored analysis
        estimated_monthly = None
        if row and row.total_qualifying_monthly_income:
            estimated_monthly = self._to_decimal(row.total_qualifying_monthly_income)

        # If no stored calculation, try to compute from bank statements directly
        if estimated_monthly is None or estimated_monthly <= ZERO:
            # Check if we have any bank statement docs
            stmt_row = self.db.execute(
                text("""
                    SELECT COUNT(*) as cnt
                    FROM smart_documents
                    WHERE loan_id = :loan_id
                      AND doc_type = :doc_type
                      AND status NOT IN ('REJECTED', 'EXPIRED')
                """),
                {"loan_id": loan_id, "doc_type": BANK_STATEMENT_DOC_TYPE},
            ).fetchone()

            if not stmt_row or stmt_row.cnt == 0:
                return {
                    "loan_id": loan_id,
                    "stated_monthly_income": float(stated_monthly_income),
                    "estimated_deposit_income": None,
                    "comparison": "NO_DATA",
                    "variance_pct": None,
                    "flags": ["No bank statements on file for income comparison"],
                }

        if estimated_monthly is None:
            estimated_monthly = ZERO

        # Calculate variance
        if stated_monthly_income > ZERO:
            variance_pct = (
                (estimated_monthly - stated_monthly_income) / stated_monthly_income * 100
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            variance_pct = Decimal("100") if estimated_monthly > ZERO else ZERO

        # Determine comparison result
        flags: List[str] = []
        if variance_pct < Decimal("-20"):
            comparison = "DEPOSITS_BELOW_STATED"
            flags.append(
                f"INCOME_MISMATCH: Payroll deposits average "
                f"${estimated_monthly:,.2f}/month vs stated income of "
                f"${stated_monthly_income:,.2f} ({variance_pct}% variance)"
            )
        elif variance_pct > Decimal("30"):
            comparison = "DEPOSITS_ABOVE_STATED"
            flags.append(
                f"INCOME_MISMATCH: Payroll deposits average "
                f"${estimated_monthly:,.2f}/month vs stated income of "
                f"${stated_monthly_income:,.2f} -- possible undisclosed income "
                f"source ({variance_pct}% above stated)"
            )
        else:
            comparison = "CONSISTENT"

        return {
            "loan_id": loan_id,
            "stated_monthly_income": float(stated_monthly_income),
            "estimated_deposit_income": float(estimated_monthly),
            "comparison": comparison,
            "variance_pct": float(variance_pct),
            "flags": flags,
        }

    # =========================================================================
    # 16. SAVE ANALYSIS
    # =========================================================================

    def save_analysis(
        self,
        analysis: BankStatementAnalysis,
        duration_ms: int = 0,
    ) -> int:
        """
        Persist bank statement analysis results.

        Saves to income_calculations (as a bank_statement_analysis type)
        and creates income_verification_tasks for each flagged item.
        Returns the saved calculation ID.
        """
        try:
            # Build a comprehensive data blob for the JSON fields
            analysis_data = {
                "analysis_type": "bank_statement",
                "statement_period_start": analysis.statement_period_start,
                "statement_period_end": analysis.statement_period_end,
                "account_type": analysis.account_type,
                "institution_name": analysis.institution_name,
                "beginning_balance": (
                    float(analysis.beginning_balance)
                    if analysis.beginning_balance is not None else None
                ),
                "ending_balance": (
                    float(analysis.ending_balance)
                    if analysis.ending_balance is not None else None
                ),
                "average_daily_balance": (
                    float(analysis.average_daily_balance)
                    if analysis.average_daily_balance is not None else None
                ),
                "lowest_balance": (
                    float(analysis.lowest_balance)
                    if analysis.lowest_balance is not None else None
                ),
                "lowest_balance_date": analysis.lowest_balance_date,
                "large_deposits": [
                    {
                        "date": ld.date,
                        "amount": float(ld.amount),
                        "description": ld.description[:200],
                        "is_payroll": ld.is_payroll,
                        "needs_sourcing": ld.needs_sourcing,
                        "risk_level": ld.risk_level,
                    }
                    for ld in analysis.large_deposits
                ],
                "nsf_events": [
                    {
                        "date": nsf.date,
                        "amount": float(nsf.amount),
                        "description": nsf.description[:200],
                    }
                    for nsf in analysis.nsf_events
                ],
                "nsf_count": analysis.nsf_count,
                "nsf_severity": analysis.nsf_severity,
                "irs_payments": [
                    {
                        "date": ip.date,
                        "amount": float(ip.amount),
                        "payment_type": ip.payment_type,
                        "is_recurring": ip.is_recurring,
                    }
                    for ip in analysis.irs_payments
                ],
                "irs_payment_plan_detected": analysis.irs_payment_plan_detected,
                "payroll_deposits_count": len(analysis.payroll_deposits),
                "estimated_monthly_income": (
                    float(analysis.estimated_monthly_income)
                    if analysis.estimated_monthly_income is not None else None
                ),
                "income_consistency": analysis.income_consistency,
                "recurring_payments": [
                    {
                        "category": rp.category,
                        "payee": rp.payee[:100],
                        "average_amount": float(rp.average_amount),
                        "frequency": rp.frequency,
                        "occurrences": rp.occurrences,
                        "is_disclosed": rp.is_disclosed,
                    }
                    for rp in analysis.recurring_payments
                ],
                "undisclosed_count": len(analysis.undisclosed_obligations),
                "total_monthly_obligations": float(analysis.total_monthly_obligations),
                "risk_score": analysis.risk_score,
                "risk_level": analysis.risk_level,
                "overdraft_days": analysis.overdraft_days,
                "ai_summary": analysis.ai_summary,
            }

            # Insert into income_calculations
            calc_row = self.db.execute(
                text("""
                    INSERT INTO income_calculations (
                        loan_id,
                        calculation_type, status,
                        total_qualifying_monthly_income,
                        total_qualifying_annual_income,
                        calculation_method,
                        total_monthly_obligations,
                        ai_confidence_score,
                        ai_flags, ai_recommendations,
                        ai_model_used, calculation_duration_ms,
                        source_documents,
                        created_at, updated_at
                    ) VALUES (
                        :loan_id,
                        :calculation_type, :status,
                        :total_monthly, :total_annual,
                        :method,
                        :monthly_obligations,
                        :confidence,
                        :flags, :recommendations,
                        :model, :duration,
                        :source_docs,
                        :now, :now
                    )
                    RETURNING id
                """),
                {
                    "loan_id": analysis.loan_id,
                    "calculation_type": "initial",
                    "status": "needs_review" if analysis.flags else "completed",
                    "total_monthly": (
                        float(analysis.estimated_monthly_income)
                        if analysis.estimated_monthly_income is not None else None
                    ),
                    "total_annual": (
                        float(analysis.estimated_monthly_income * 12)
                        if analysis.estimated_monthly_income is not None else None
                    ),
                    "method": "bank_statement_analysis",
                    "monthly_obligations": float(analysis.total_monthly_obligations),
                    "confidence": analysis.ai_confidence,
                    "flags": json.dumps(analysis.flags),
                    "recommendations": json.dumps(
                        analysis.recommendations + [analysis.ai_summary or ""]
                    ),
                    "model": self._model,
                    "duration": duration_ms,
                    "source_docs": json.dumps(analysis.document_ids),
                    "now": datetime.now(timezone.utc),
                },
            )
            calculation_id = calc_row.fetchone()[0]

            # Create income_verification_tasks for each generated task
            for task in analysis.tasks_to_create:
                self.db.execute(
                    text("""
                        INSERT INTO income_verification_tasks (
                            calculation_id,
                            loan_id, organization_id,
                            task_type, title, description,
                            priority, status,
                            ai_recommendation,
                            created_at, updated_at
                        ) VALUES (
                            :calc_id,
                            :loan_id, NULL,
                            :task_type, :title, :description,
                            :priority, 'open',
                            :ai_rec,
                            :now, :now
                        )
                    """),
                    {
                        "calc_id": calculation_id,
                        "loan_id": analysis.loan_id,
                        "task_type": task["task_type"],
                        "title": task["title"],
                        "description": task["description"],
                        "priority": task["priority"],
                        "ai_rec": task.get("ai_recommendation", ""),
                        "now": datetime.now(timezone.utc),
                    },
                )

            self.db.commit()
            logger.info(
                f"Bank statement analysis saved: id={calculation_id} "
                f"loan={analysis.loan_id} risk={analysis.risk_level} "
                f"score={analysis.risk_score} flags={len(analysis.flags)} "
                f"tasks={len(analysis.tasks_to_create)}"
            )
            return calculation_id

        except Exception as e:
            self.db.rollback()
            logger.exception(f"Failed to save bank statement analysis: {e}")
            raise

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _generate_recommendations(
        self,
        analysis: BankStatementAnalysis,
    ) -> List[str]:
        """Generate actionable recommendations based on analysis flags."""
        recs: List[str] = []

        if analysis.deposits_needing_sourcing > 0:
            recs.append(
                f"Obtain sourcing documentation for {analysis.deposits_needing_sourcing} "
                f"large deposit(s) totaling ${analysis.total_large_deposits:,.2f}. "
                f"Each deposit requires a signed Letter of Explanation and supporting "
                f"documentation per Fannie Mae B3-4.2-01."
            )

        if analysis.nsf_count > 0:
            if analysis.nsf_severity in ("HIGH", "CRITICAL"):
                recs.append(
                    f"URGENT: {analysis.nsf_count} NSF/overdraft events detected. "
                    f"This is a significant underwriting red flag indicating potential "
                    f"cash-flow issues. Obtain LOE for each event and verify the "
                    f"account is currently in good standing."
                )
            else:
                recs.append(
                    f"Obtain Letter of Explanation for {analysis.nsf_count} "
                    f"NSF/overdraft event(s)."
                )

        if analysis.irs_payment_plan_detected:
            recs.append(
                "IRS installment agreement detected. Obtain: (1) IRS installment "
                "agreement letter, (2) IRS tax transcripts for last 3 years, "
                "(3) proof of 12 months of timely payments. Monthly payment "
                "must be included in DTI."
            )

        if analysis.undisclosed_obligations:
            total_undisclosed = sum(
                rp.average_amount for rp in analysis.undisclosed_obligations
            )
            recs.append(
                f"{len(analysis.undisclosed_obligations)} potential undisclosed "
                f"obligation(s) totaling ${total_undisclosed:,.2f}/month detected. "
                f"Cross-reference against credit report and update DTI if not "
                f"already included."
            )

        if analysis.overdraft_days > 0:
            recs.append(
                f"Account showed negative balance on {analysis.overdraft_days} "
                f"day(s). Verify sufficient reserves for closing costs and "
                f"consider requesting additional months of statements."
            )

        if analysis.income_consistency == "IRREGULAR":
            recs.append(
                "Payroll deposits show irregular pattern. Consider requesting "
                "additional documentation (VOE, additional pay stubs) to verify "
                "employment stability and income consistency."
            )

        structuring_flags = [f for f in analysis.flags if "STRUCTURING" in f]
        if structuring_flags:
            recs.append(
                "Potential structuring activity detected. Review deposit patterns "
                "carefully. Multiple deposits just below $10,000 may indicate "
                "attempts to avoid Currency Transaction Report requirements. "
                "Escalate to compliance if patterns are concerning."
            )

        if not recs:
            recs.append(
                "Bank statement analysis shows no significant concerns. "
                "Balances and deposit patterns appear consistent with the "
                "borrower's stated financial profile."
            )

        return recs

    def _extract_metadata(self, docs: List[Dict]) -> Dict:
        """Extract statement metadata (dates, institution, account type) from documents."""
        metadata: Dict[str, Any] = {}

        for doc in docs:
            ef = doc.get("extracted_fields") or {}
            ed = doc.get("extracted_dates") or {}

            # Period dates
            if not metadata.get("period_start"):
                period_start = (
                    ef.get("statement_start_date")
                    or ed.get("statementStart")
                    or ef.get("period_start")
                )
                if period_start:
                    metadata["period_start"] = str(period_start)

            if not metadata.get("period_end"):
                period_end = (
                    ef.get("statement_end_date")
                    or ed.get("statementEnd")
                    or ef.get("period_end")
                )
                if period_end:
                    metadata["period_end"] = str(period_end)

            # Institution
            if not metadata.get("institution"):
                institution = ef.get("bank_name") or ef.get("institution_name")
                if institution:
                    metadata["institution"] = str(institution)

            # Account type
            if not metadata.get("account_type"):
                acct_type = ef.get("account_type")
                if acct_type:
                    acct_upper = str(acct_type).upper()
                    if "SAVINGS" in acct_upper:
                        metadata["account_type"] = "SAVINGS"
                    elif "BUSINESS" in acct_upper:
                        metadata["account_type"] = "BUSINESS"
                    else:
                        metadata["account_type"] = "CHECKING"

            # Balances
            if not metadata.get("beginning_balance"):
                bb = ef.get("beginning_balance") or ef.get("opening_balance")
                if bb is not None:
                    metadata["beginning_balance"] = self._to_decimal(bb)

            if not metadata.get("ending_balance"):
                eb = ef.get("ending_balance") or ef.get("closing_balance")
                if eb is not None:
                    metadata["ending_balance"] = self._to_decimal(eb)

            if not metadata.get("average_daily_balance"):
                adb = ef.get("average_balance") or ef.get("average_daily_balance")
                if adb is not None:
                    metadata["average_daily_balance"] = self._to_decimal(adb)

        if "account_type" not in metadata:
            metadata["account_type"] = "CHECKING"

        return metadata

    def _analyze_balances(
        self,
        transactions: List[Dict],
        metadata: Dict,
    ) -> Dict:
        """
        Analyze balance information from transactions and metadata.
        Returns dict with beginning, ending, average_daily, lowest, lowest_date.
        """
        result: Dict[str, Any] = {
            "beginning": metadata.get("beginning_balance"),
            "ending": metadata.get("ending_balance"),
            "average_daily": metadata.get("average_daily_balance"),
            "lowest": None,
            "lowest_date": None,
        }

        # If transactions have balance info, find the lowest
        balances_with_dates: List[Tuple[Decimal, str]] = []
        for txn in transactions:
            if txn.get("balance") is not None:
                bal = self._to_decimal(txn["balance"])
                balances_with_dates.append((bal, txn.get("date", "")))

        if balances_with_dates:
            lowest_balance, lowest_date = min(balances_with_dates, key=lambda x: x[0])
            result["lowest"] = lowest_balance
            result["lowest_date"] = lowest_date

            # If we don't have beginning/ending from metadata, infer from transactions
            if result["beginning"] is None and balances_with_dates:
                result["beginning"] = balances_with_dates[0][0]
            if result["ending"] is None and balances_with_dates:
                result["ending"] = balances_with_dates[-1][0]

            # Calculate average daily balance from transaction balances if not in metadata
            if result["average_daily"] is None and len(balances_with_dates) >= 2:
                total = sum(b[0] for b in balances_with_dates)
                result["average_daily"] = (total / len(balances_with_dates)).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )

        return result

    def _count_overdraft_days(self, transactions: List[Dict]) -> int:
        """Count the number of days with negative balance."""
        negative_dates: set = set()
        for txn in transactions:
            if txn.get("balance") is not None:
                bal = self._to_decimal(txn["balance"])
                if bal < ZERO:
                    negative_dates.add(txn.get("date", ""))

        return len(negative_dates)

    def _get_borrower_name(self, loan_id: int) -> str:
        """Get borrower name from the loan record."""
        row = self.db.execute(
            text("SELECT borrower_name FROM loans WHERE id = :loan_id"),
            {"loan_id": loan_id},
        ).fetchone()
        return row.borrower_name if row and row.borrower_name else ""

    def _normalize_date(self, raw_date: Optional[str]) -> Optional[str]:
        """
        Normalize various date formats to YYYY-MM-DD.
        Handles: MM/DD/YYYY, MM/DD/YY, MM-DD-YYYY, YYYY-MM-DD.
        """
        if not raw_date:
            return None

        raw_date = raw_date.strip()

        formats = [
            ("%m/%d/%Y", None),
            ("%m/%d/%y", None),
            ("%m-%d-%Y", None),
            ("%m-%d-%y", None),
            ("%Y-%m-%d", None),
        ]

        for fmt, _ in formats:
            try:
                dt = datetime.strptime(raw_date, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return None

    def _parse_amount(self, raw_amount: Optional[str]) -> Optional[Decimal]:
        """Parse a currency string into a Decimal."""
        if not raw_amount:
            return None

        cleaned = raw_amount.strip()

        # Detect negative: parentheses or leading minus
        is_negative = "(" in cleaned or cleaned.startswith("-")

        # Remove currency symbols, commas, parens, spaces
        cleaned = re.sub(r"[$(),\s]", "", cleaned)

        if not cleaned:
            return None

        try:
            value = Decimal(cleaned).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            if is_negative and value > ZERO:
                value = -value
            return value
        except (InvalidOperation, ValueError):
            return None

    def _to_decimal(self, value: Any) -> Decimal:
        """Safely convert a value to Decimal, returning ZERO on failure."""
        if value is None:
            return ZERO
        try:
            if isinstance(value, Decimal):
                return value
            if isinstance(value, str):
                value = value.replace("$", "").replace(",", "").strip()
                if not value:
                    return ZERO
            return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            return ZERO

    def _extract_payroll_source(self, description: str) -> str:
        """
        Extract a normalized employer/source name from a payroll
        transaction description.
        """
        desc = description.strip()

        # Remove common prefixes
        prefixes_to_strip = [
            "direct dep", "ach", "payroll", "dp ", "dir dep",
            "direct deposit", "credit",
        ]
        lower_desc = desc.lower()
        for prefix in prefixes_to_strip:
            if lower_desc.startswith(prefix):
                desc = desc[len(prefix):].strip()
                lower_desc = desc.lower()
                # Strip leading punctuation/spaces
                desc = desc.lstrip(" -:")
                break

        # Take first meaningful segment (up to first common delimiter)
        for delim in [" - ", " / ", "  ", "#"]:
            if delim in desc:
                desc = desc.split(delim)[0].strip()
                break

        return desc[:50] if desc else "Unknown"

    def _normalize_payee(self, description: str) -> str:
        """
        Normalize a payee description for grouping purposes.
        Strips transaction IDs, reference numbers, dates, etc.
        """
        desc = description.strip().upper()

        # Remove reference numbers, transaction IDs
        desc = re.sub(r"#\d+", "", desc)
        desc = re.sub(r"REF\s*:?\s*\d+", "", desc)
        desc = re.sub(r"TRANS\s*:?\s*\d+", "", desc)
        desc = re.sub(r"CONF\s*:?\s*\d+", "", desc)

        # Remove dates embedded in descriptions
        desc = re.sub(r"\d{1,2}/\d{1,2}(/\d{2,4})?", "", desc)
        desc = re.sub(r"\d{4}-\d{2}-\d{2}", "", desc)

        # Remove trailing numbers (often check numbers or sequence IDs)
        desc = re.sub(r"\s+\d{3,}$", "", desc)

        # Collapse whitespace
        desc = re.sub(r"\s+", " ", desc).strip()

        # Take first 40 characters for grouping
        return desc[:40] if desc else ""

    def _determine_frequency(self, dates: List[date]) -> str:
        """
        Determine payment/deposit frequency from a list of dates.
        Analyzes intervals between consecutive dates.
        """
        if len(dates) < 2:
            return "MONTHLY"

        intervals = []
        for i in range(1, len(dates)):
            delta = (dates[i] - dates[i - 1]).days
            if delta > 0:
                intervals.append(delta)

        if not intervals:
            return "MONTHLY"

        avg_interval = sum(intervals) / len(intervals)

        if avg_interval <= 9:
            return "WEEKLY"
        elif avg_interval <= 18:
            return "BIWEEKLY"
        elif avg_interval <= 20:
            return "SEMIMONTHLY"
        elif avg_interval <= 40:
            return "MONTHLY"
        else:
            return "MONTHLY"  # Default for sparse data


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================

def get_bank_statement_analyzer(db: Session) -> BankStatementAnalyzerService:
    """
    Factory function returning a BankStatementAnalyzerService for the given
    database session.

    Not a true singleton because each request may have a different DB session,
    but the service itself is lightweight and stateless beyond the session.
    """
    return BankStatementAnalyzerService(db)
