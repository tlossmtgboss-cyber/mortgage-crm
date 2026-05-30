"""
Bank Statement Extraction Service

Uses AI (Claude) to extract financial data from uploaded bank statement PDFs.
Extracts monthly totals, deposits, balances, and flags ineligible transactions.
"""

import os
import json
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, List, Any, Tuple

from agents.anthropic_client import get_anthropic_client

logger = logging.getLogger(__name__)


class BankStatementExtractionService:
    """Service for extracting data from bank statements using AI."""

    def __init__(self):
        self.client = get_anthropic_client()
        self.model = "claude-sonnet-4-6"

    async def extract_statement_data(
        self,
        document_text: str,
        statement_type: str = "PERSONAL",
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Extract financial data from a bank statement.

        Args:
            document_text: OCR text from the bank statement
            statement_type: "PERSONAL" or "BUSINESS"
            context: Additional context (borrower name, expected account, etc.)

        Returns:
            Dictionary with extracted data
        """
        system_prompt = """You are an expert at extracting financial data from bank statements for mortgage income calculation.

Your task is to extract the following data from the bank statement:

1. **Account Information:**
   - Bank name
   - Account last 4 digits
   - Statement period (start and end dates)
   - Account holder name

2. **Monthly Totals:**
   - Beginning balance
   - Ending balance
   - Total deposits
   - Total withdrawals

3. **Deposit Analysis:**
   - List all deposits with date, description, and amount
   - Flag deposits that appear INELIGIBLE for income calculation:
     * Transfers from other accounts
     * Loan proceeds
     * One-time large deposits (inheritance, gifts, tax refunds)
     * NSF fee reversals
     * Credit card payments received
     * ATM deposits (if from another account)

4. **NSF/Overdraft Count:**
   - Count of NSF (Non-Sufficient Funds) fees
   - Count of overdraft occurrences

Return your analysis as valid JSON with this structure:
{
  "bank_name": "string",
  "account_last_four": "string",
  "account_holder": "string",
  "statement_start_date": "YYYY-MM-DD",
  "statement_end_date": "YYYY-MM-DD",
  "statement_month": "January/February/etc",
  "beginning_balance": number,
  "ending_balance": number,
  "total_deposits": number,
  "total_withdrawals": number,
  "nsf_count": number,
  "deposits": [
    {
      "date": "YYYY-MM-DD",
      "description": "string",
      "amount": number,
      "is_eligible": boolean,
      "ineligible_reason": "string or null"
    }
  ],
  "eligible_deposits_total": number,
  "ineligible_deposits_total": number,
  "extraction_confidence": number (0-100),
  "notes": "any important observations"
}"""

        user_prompt = f"""Please extract the financial data from this {statement_type.lower()} bank statement:

{document_text}

{f'Context: {json.dumps(context)}' if context else ''}

Return ONLY valid JSON with the extracted data."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

            # Parse the JSON response
            response_text = response.content[0].text

            # Try to extract JSON from the response
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0]
            else:
                json_str = response_text

            extracted_data = json.loads(json_str.strip())
            return extracted_data

        except Exception as e:
            logger.error(f"Error extracting bank statement data: {e}")
            return {
                "error": "Internal server error",
                "extraction_confidence": 0
            }

    async def extract_multiple_statements(
        self,
        statements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract data from multiple bank statements.

        Args:
            statements: List of dicts with 'document_text' and 'metadata'

        Returns:
            List of extracted data dicts
        """
        results = []
        for stmt in statements:
            data = await self.extract_statement_data(
                document_text=stmt.get("document_text", ""),
                statement_type=stmt.get("statement_type", "PERSONAL"),
                context=stmt.get("context")
            )
            data["source_document_id"] = stmt.get("document_id")
            results.append(data)
        return results

    def calculate_qualifying_income(
        self,
        monthly_data: List[Dict],
        calculation_method: str = "UNIFORM_EXPENSE_RATIO",
        ownership_percentage: float = 100.0,
        ltv_percentage: float = 80.0,
        cpa_expense_ratio: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate qualifying income from extracted bank statement data.

        Args:
            monthly_data: List of monthly extracted data
            calculation_method: UNIFORM_EXPENSE_RATIO, CPA_PL, or CPA_EXPENSE_RATIO
            ownership_percentage: Business ownership % (for business accounts)
            ltv_percentage: LTV % (determines expense ratio for Method 1)
            cpa_expense_ratio: CPA-stated expense ratio (for Method 3)

        Returns:
            Dictionary with calculated income
        """
        # Sum eligible deposits across all months
        total_eligible = sum(
            Decimal(str(m.get("eligible_deposits_total", 0)))
            for m in monthly_data
        )

        num_months = len(monthly_data)

        # Determine expense ratio based on method
        if calculation_method == "UNIFORM_EXPENSE_RATIO":
            # Method 1: 50% for LTV <= 80%, 60% for LTV > 80%
            expense_ratio = Decimal("0.50") if ltv_percentage <= 80 else Decimal("0.60")
        elif calculation_method == "CPA_EXPENSE_RATIO" and cpa_expense_ratio:
            # Method 3: Use CPA-stated ratio
            expense_ratio = Decimal(str(cpa_expense_ratio)) / Decimal("100")
        else:
            # Default to 50%
            expense_ratio = Decimal("0.50")

        # Calculate net income (after expenses)
        net_deposits = total_eligible * (Decimal("1") - expense_ratio)

        # Apply ownership percentage
        ownership_factor = Decimal(str(ownership_percentage)) / Decimal("100")
        owner_share = net_deposits * ownership_factor

        # Calculate monthly and annual income
        monthly_income = owner_share / Decimal(str(num_months))
        annual_income = monthly_income * Decimal("12")

        return {
            "total_eligible_deposits": float(total_eligible),
            "expense_ratio_used": float(expense_ratio),
            "net_deposits": float(net_deposits),
            "ownership_percentage": ownership_percentage,
            "owner_share": float(owner_share),
            "num_months_analyzed": num_months,
            "monthly_qualifying_income": float(monthly_income),
            "annual_qualifying_income": float(annual_income),
            "calculation_method": calculation_method
        }

    def validate_statement_continuity(
        self,
        monthly_data: List[Dict]
    ) -> Dict[str, Any]:
        """
        Validate that statements are continuous and complete.

        Returns:
            Dictionary with validation results and any gaps found
        """
        issues = []
        warnings = []

        # Check for missing months
        if len(monthly_data) < 12:
            issues.append(f"Only {len(monthly_data)} months of statements (12 required)")

        # Check for balance continuity
        for i in range(len(monthly_data) - 1):
            current = monthly_data[i]
            previous = monthly_data[i + 1]

            current_begin = current.get("beginning_balance", 0)
            previous_end = previous.get("ending_balance", 0)

            if abs(current_begin - previous_end) > 1:  # Allow $1 rounding
                warnings.append(
                    f"Balance discontinuity: Month {i+1} begins at ${current_begin}, "
                    f"but Month {i+2} ended at ${previous_end}"
                )

        # Check for high NSF counts
        total_nsfs = sum(m.get("nsf_count", 0) for m in monthly_data)
        if total_nsfs > 3:
            warnings.append(f"High NSF count: {total_nsfs} NSFs in {len(monthly_data)} months")

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "months_provided": len(monthly_data),
            "total_nsf_count": total_nsfs
        }


# Singleton instance
_extraction_service = None


def get_bank_statement_extraction_service() -> BankStatementExtractionService:
    """Get or create the extraction service singleton."""
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = BankStatementExtractionService()
    return _extraction_service
