"""Auto-generated. See ocr_enhancement_service/__init__.py."""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import statistics
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

# Optional dependency imports (graceful degradation)
try:
    from PIL import Image, ImageFilter, ImageEnhance, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    from pdf2image import convert_from_bytes
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from middleware.upload_limits import (
    MAX_VISION_API_SIZE,
    MAX_IMAGE_DIMENSIONS,
    MAX_OCR_OUTPUT_CHARS,
    MAX_PDF_PAGES,
)

# Pull all constants/enums/dataclasses (incl. DEFAULT_TARGET_DPI, MIN_TABLE_ROWS, etc.)
from ._types import *  # noqa: F401,F403

from ._spell import SpellCorrector
from ._tables import FinancialTableExtractor
from ._preprocess import AdvancedImagePreprocessor
from ._validation import FieldValidator
from ._handwriting import HandwritingDetector


class _EnrichMixin:

    def _enrich_from_tables(
        self,
        document_type: str,
        existing_fields: Dict[str, StructuredField],
        tables: List[ExtractedTable],
    ) -> Dict[str, StructuredField]:
        """Attempt to fill missing fields from extracted table data.

        For bank statements, transaction tables provide deposit/withdrawal
        totals. For paystubs, earnings/deduction tables provide breakdowns.
        """
        enrichments: Dict[str, StructuredField] = {}

        if not tables:
            return enrichments

        if document_type == MortgageDocType.BANK_STATEMENT.value:
            enrichments.update(
                self._enrich_bank_statement_from_tables(existing_fields, tables),
            )
        elif document_type == MortgageDocType.PAYSTUB.value:
            enrichments.update(
                self._enrich_paystub_from_tables(existing_fields, tables),
            )

        return enrichments

    def _enrich_bank_statement_from_tables(
        self,
        existing: Dict[str, StructuredField],
        tables: List[ExtractedTable],
    ) -> Dict[str, StructuredField]:
        """Extract deposit/withdrawal totals from bank statement tables."""
        enrichments: Dict[str, StructuredField] = {}

        # Look for summary tables
        summary_tables = [t for t in tables if t.table_type == "summary"]
        transaction_tables = [t for t in tables if t.table_type == "transaction"]

        for table in summary_tables:
            for row in table.rows:
                row_text = " ".join(row).lower()

                if "total_deposits" not in existing and "total_deposits" not in enrichments:
                    if "deposit" in row_text or "credit" in row_text:
                        amount = self._extract_amount_from_row(row)
                        if amount is not None:
                            enrichments["total_deposits"] = StructuredField(
                                name="total_deposits",
                                value=amount,
                                raw_value=" | ".join(row),
                                confidence=table.confidence * 0.9,
                                page_number=table.page_number,
                                validated=True,
                                validation_notes="Extracted from summary table",
                            )

                if "total_withdrawals" not in existing and "total_withdrawals" not in enrichments:
                    if "withdrawal" in row_text or "debit" in row_text:
                        amount = self._extract_amount_from_row(row)
                        if amount is not None:
                            enrichments["total_withdrawals"] = StructuredField(
                                name="total_withdrawals",
                                value=amount,
                                raw_value=" | ".join(row),
                                confidence=table.confidence * 0.9,
                                page_number=table.page_number,
                                validated=True,
                                validation_notes="Extracted from summary table",
                            )

        # If we still lack totals, compute from transaction tables
        if transaction_tables and ("total_deposits" not in existing and "total_deposits" not in enrichments):
            deposits_sum = Decimal("0")
            withdrawals_sum = Decimal("0")
            transaction_count = 0

            for table in transaction_tables:
                for row in table.rows:
                    amounts = self._extract_all_amounts_from_row(row)
                    row_text = " ".join(row).lower()
                    for amount in amounts:
                        if amount > 0 and ("deposit" in row_text or "credit" in row_text):
                            deposits_sum += Decimal(str(amount))
                            transaction_count += 1
                        elif amount > 0 and ("withdrawal" in row_text or "debit" in row_text or "check" in row_text):
                            withdrawals_sum += Decimal(str(amount))
                            transaction_count += 1

            if transaction_count > 0:
                if "total_deposits" not in existing and "total_deposits" not in enrichments and deposits_sum > 0:
                    enrichments["total_deposits"] = StructuredField(
                        name="total_deposits",
                        value=float(deposits_sum),
                        raw_value=f"Computed from {transaction_count} transactions",
                        confidence=0.60,  # Lower confidence for computed values
                        validated=True,
                        validation_notes="Computed from transaction table rows",
                    )

                if "total_withdrawals" not in existing and "total_withdrawals" not in enrichments and withdrawals_sum > 0:
                    enrichments["total_withdrawals"] = StructuredField(
                        name="total_withdrawals",
                        value=float(withdrawals_sum),
                        raw_value=f"Computed from {transaction_count} transactions",
                        confidence=0.60,
                        validated=True,
                        validation_notes="Computed from transaction table rows",
                    )

        return enrichments

    def _enrich_paystub_from_tables(
        self,
        existing: Dict[str, StructuredField],
        tables: List[ExtractedTable],
    ) -> Dict[str, StructuredField]:
        """Extract earnings/deduction details from paystub tables."""
        enrichments: Dict[str, StructuredField] = {}

        earnings_tables = [t for t in tables if t.table_type == "earnings"]
        deduction_tables = [t for t in tables if t.table_type == "deduction"]

        # Map common table labels to field names
        earnings_field_map = {
            "regular": "regular_earnings",
            "overtime": "overtime_earnings",
            "bonus": "bonus",
            "commission": "commission",
        }

        deduction_field_map = {
            "federal": "federal_tax",
            "state": "state_tax",
            "social security": "social_security",
            "fica": "social_security",
            "medicare": "medicare",
            "401k": "retirement_401k",
            "retirement": "retirement_401k",
            "health": "health_insurance",
            "medical": "health_insurance",
        }

        for table in earnings_tables:
            for row in table.rows:
                row_text = " ".join(row).lower()
                for keyword, field_name in earnings_field_map.items():
                    if keyword in row_text and field_name not in existing and field_name not in enrichments:
                        amount = self._extract_amount_from_row(row)
                        if amount is not None:
                            enrichments[field_name] = StructuredField(
                                name=field_name,
                                value=amount,
                                raw_value=" | ".join(row),
                                confidence=table.confidence * 0.85,
                                page_number=table.page_number,
                                validated=True,
                                validation_notes="Extracted from earnings table",
                            )
                            break

        for table in deduction_tables:
            for row in table.rows:
                row_text = " ".join(row).lower()
                for keyword, field_name in deduction_field_map.items():
                    if keyword in row_text and field_name not in existing and field_name not in enrichments:
                        amount = self._extract_amount_from_row(row)
                        if amount is not None:
                            enrichments[field_name] = StructuredField(
                                name=field_name,
                                value=amount,
                                raw_value=" | ".join(row),
                                confidence=table.confidence * 0.85,
                                page_number=table.page_number,
                                validated=True,
                                validation_notes="Extracted from deduction table",
                            )
                            break

        return enrichments

    @staticmethod
    def _extract_amount_from_row(row: List[str]) -> Optional[float]:
        """Extract the first currency amount from a table row."""
        currency_pattern = re.compile(
            r"\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
        )

        # Search from right to left (amounts are usually in rightmost columns)
        for cell in reversed(row):
            match = currency_pattern.search(cell)
            if match:
                try:
                    value = float(match.group(1).replace(",", ""))
                    if value > 0:
                        return value
                except ValueError:
                    continue

        return None

    @staticmethod
    def _extract_all_amounts_from_row(row: List[str]) -> List[float]:
        """Extract all currency amounts from a table row."""
        currency_pattern = re.compile(
            r"\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
        )
        amounts: List[float] = []

        for cell in row:
            for match in currency_pattern.finditer(cell):
                try:
                    value = float(match.group(1).replace(",", ""))
                    if value > 0:
                        amounts.append(value)
                except ValueError:
                    continue

        return amounts
