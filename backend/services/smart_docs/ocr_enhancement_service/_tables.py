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


# FinancialTableExtractor

class FinancialTableExtractor:
    """Extracts and classifies tables from financial documents.

    Tuned for mortgage documents: bank statement transaction tables,
    paystub earnings/deductions tables, tax return schedule tables.
    """

    # Table type detection keywords
    _TABLE_TYPE_KEYWORDS: Dict[str, List[str]] = {
        "transaction": [
            "date", "description", "amount", "debit", "credit",
            "withdrawal", "deposit", "check", "balance",
        ],
        "earnings": [
            "hours", "rate", "earnings", "current", "ytd",
            "regular", "overtime", "gross", "description",
        ],
        "deduction": [
            "deduction", "federal", "state", "fica", "medicare",
            "insurance", "401k", "retirement", "current", "ytd",
        ],
        "summary": [
            "beginning", "ending", "balance", "total", "deposits",
            "withdrawals", "average", "interest",
        ],
        "tax_schedule": [
            "line", "amount", "income", "expense", "depreciation",
            "deduction", "description", "adjustment",
        ],
    }

    def extract_tables_from_text(
        self,
        text: str,
        page_number: int = 1,
    ) -> List[ExtractedTable]:
        """Extract table structures from OCR text using delimiter analysis.

        Detects pipe-delimited tables (from Claude Vision) and
        whitespace-aligned columnar data.

        Args:
            text: OCR text that may contain tables.
            page_number: Page number for attribution.

        Returns:
            List of ExtractedTable objects.
        """
        if not text:
            return []

        tables: List[ExtractedTable] = []

        # Strategy 1: Pipe-delimited tables (from Claude Vision output)
        pipe_tables = self._extract_pipe_tables(text, page_number)
        tables.extend(pipe_tables)

        # Strategy 2: Whitespace-aligned columnar data
        if not pipe_tables:
            columnar_tables = self._extract_columnar_tables(text, page_number)
            tables.extend(columnar_tables)

        # Classify each table
        for table in tables:
            table.table_type = self._classify_table(table)

        return tables

    def extract_tables_from_pdfplumber(
        self,
        pdf_bytes: bytes,
        max_pages: int = 50,
    ) -> List[ExtractedTable]:
        """Extract tables from PDF using pdfplumber's table detection.

        Provides higher accuracy than text-based extraction for PDFs
        with native text layers.

        Args:
            pdf_bytes: Raw PDF content.
            max_pages: Maximum pages to process.

        Returns:
            List of ExtractedTable objects.
        """
        if not HAS_PDFPLUMBER:
            return []

        tables: List[ExtractedTable] = []
        table_idx = 0

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages[:max_pages], 1):
                    try:
                        raw_tables = page.extract_tables()
                        if not raw_tables:
                            continue

                        for raw_table in raw_tables:
                            if not raw_table or len(raw_table) < MIN_TABLE_ROWS:
                                continue

                            # Clean cells
                            cleaned_rows: List[List[str]] = []
                            for row in raw_table:
                                cleaned_row = [
                                    str(cell).strip() if cell else ""
                                    for cell in row
                                ]
                                cleaned_rows.append(cleaned_row)

                            # First row as headers if it looks like a header
                            headers: List[str] = []
                            data_rows = cleaned_rows
                            if cleaned_rows and self._looks_like_header(cleaned_rows[0]):
                                headers = cleaned_rows[0]
                                data_rows = cleaned_rows[1:]

                            if not data_rows:
                                continue

                            col_count = max(len(row) for row in data_rows) if data_rows else 0

                            table = ExtractedTable(
                                table_index=table_idx,
                                page_number=page_num,
                                headers=headers,
                                rows=data_rows,
                                row_count=len(data_rows),
                                col_count=col_count,
                                confidence=0.90,  # pdfplumber tables are high confidence
                            )
                            table.table_type = self._classify_table(table)
                            tables.append(table)
                            table_idx += 1

                    except Exception as e:
                        logger.debug(
                            "Table extraction failed on page %d: %s", page_num, e
                        )

        except Exception as e:
            logger.warning("PDF table extraction failed: %s", e)

        return tables

    def _extract_pipe_tables(
        self, text: str, page_number: int,
    ) -> List[ExtractedTable]:
        """Extract pipe-delimited tables from text."""
        tables: List[ExtractedTable] = []
        lines = text.split("\n")
        current_table_lines: List[str] = []
        table_idx = 0

        for line in lines:
            stripped = line.strip()
            if "|" in stripped and stripped.count("|") >= 1:
                current_table_lines.append(stripped)
            else:
                if len(current_table_lines) >= MIN_TABLE_ROWS:
                    table = self._parse_pipe_table(
                        current_table_lines, table_idx, page_number,
                    )
                    if table is not None:
                        tables.append(table)
                        table_idx += 1
                current_table_lines = []

        # Handle table at end of text
        if len(current_table_lines) >= MIN_TABLE_ROWS:
            table = self._parse_pipe_table(
                current_table_lines, table_idx, page_number,
            )
            if table is not None:
                tables.append(table)

        return tables

    def _parse_pipe_table(
        self,
        lines: List[str],
        table_index: int,
        page_number: int,
    ) -> Optional[ExtractedTable]:
        """Parse pipe-delimited lines into an ExtractedTable."""
        rows: List[List[str]] = []
        for line in lines:
            # Skip separator lines (e.g., ---|---|---)
            if re.match(r"^[\s|+\-=]+$", line):
                continue
            cells = [cell.strip() for cell in line.split("|")]
            # Remove empty leading/trailing cells from pipes at start/end
            if cells and not cells[0]:
                cells = cells[1:]
            if cells and not cells[-1]:
                cells = cells[:-1]
            if cells:
                rows.append(cells)

        if len(rows) < MIN_TABLE_ROWS:
            return None

        # Verify column consistency
        col_counts = [len(row) for row in rows]
        if not col_counts:
            return None
        median_cols = int(statistics.median(col_counts))
        if median_cols < MIN_TABLE_COLUMNS:
            return None
        consistent = sum(1 for c in col_counts if abs(c - median_cols) <= 1)
        if consistent / len(col_counts) < TABLE_COLUMN_CONSISTENCY_THRESHOLD:
            return None

        headers: List[str] = []
        data_rows = rows
        if rows and self._looks_like_header(rows[0]):
            headers = rows[0]
            data_rows = rows[1:]

        return ExtractedTable(
            table_index=table_index,
            page_number=page_number,
            headers=headers,
            rows=data_rows,
            row_count=len(data_rows),
            col_count=median_cols,
            confidence=0.80,
        )

    def _extract_columnar_tables(
        self, text: str, page_number: int,
    ) -> List[ExtractedTable]:
        """Extract whitespace-aligned columnar data.

        Uses column position analysis to detect aligned data that
        lacks explicit delimiters.
        """
        if not HAS_NUMPY:
            return []

        lines = text.split("\n")
        if len(lines) < MIN_TABLE_ROWS:
            return []

        tables: List[ExtractedTable] = []
        table_idx = 0

        # Find runs of lines with consistent spacing patterns
        current_run: List[str] = []
        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                if len(current_run) >= MIN_TABLE_ROWS:
                    table = self._analyze_column_alignment(
                        current_run, table_idx, page_number,
                    )
                    if table is not None:
                        tables.append(table)
                        table_idx += 1
                current_run = []
                continue

            # Lines with multiple whitespace gaps likely contain columnar data
            gap_count = len(re.findall(r"\s{2,}", stripped))
            if gap_count >= 1:
                current_run.append(stripped)
            else:
                if len(current_run) >= MIN_TABLE_ROWS:
                    table = self._analyze_column_alignment(
                        current_run, table_idx, page_number,
                    )
                    if table is not None:
                        tables.append(table)
                        table_idx += 1
                current_run = []

        # Handle trailing run
        if len(current_run) >= MIN_TABLE_ROWS:
            table = self._analyze_column_alignment(
                current_run, table_idx, page_number,
            )
            if table is not None:
                tables.append(table)

        return tables

    def _analyze_column_alignment(
        self,
        lines: List[str],
        table_index: int,
        page_number: int,
    ) -> Optional[ExtractedTable]:
        """Analyze whitespace positions to split lines into columns."""
        if not lines:
            return None

        # Find common whitespace positions across all lines
        max_len = max(len(line) for line in lines)
        if max_len < 10:
            return None

        # Build a "whitespace frequency" array
        ws_freq = np.zeros(max_len, dtype=int)
        for line in lines:
            padded = line.ljust(max_len)
            for i, ch in enumerate(padded):
                if ch == " ":
                    ws_freq[i] += 1

        # Column boundaries are positions where most lines have whitespace
        threshold = len(lines) * 0.6
        boundaries: List[int] = []
        in_gap = False
        gap_start = 0

        for i in range(max_len):
            if ws_freq[i] >= threshold:
                if not in_gap:
                    gap_start = i
                    in_gap = True
            else:
                if in_gap:
                    # Use the middle of the gap as the boundary
                    boundaries.append((gap_start + i) // 2)
                    in_gap = False

        if len(boundaries) < 1:
            return None

        # Split each line at the boundaries
        all_boundaries = [0] + boundaries + [max_len]
        rows: List[List[str]] = []

        for line in lines:
            padded = line.ljust(max_len)
            cells = []
            for j in range(len(all_boundaries) - 1):
                start = all_boundaries[j]
                end = all_boundaries[j + 1]
                cell = padded[start:end].strip()
                cells.append(cell)
            rows.append(cells)

        col_count = len(all_boundaries) - 1
        if col_count < MIN_TABLE_COLUMNS:
            return None

        headers: List[str] = []
        data_rows = rows
        if rows and self._looks_like_header(rows[0]):
            headers = rows[0]
            data_rows = rows[1:]

        if len(data_rows) < MIN_TABLE_ROWS - 1:
            return None

        return ExtractedTable(
            table_index=table_index,
            page_number=page_number,
            headers=headers,
            rows=data_rows,
            row_count=len(data_rows),
            col_count=col_count,
            confidence=0.65,  # Columnar detection is less certain
        )

    def _looks_like_header(self, row: List[str]) -> bool:
        """Heuristic: does this row look like a table header?"""
        if not row:
            return False

        non_empty = [cell for cell in row if cell.strip()]
        if not non_empty:
            return False

        # Headers tend to be text (not numbers), short, and non-currency
        numeric_count = 0
        for cell in non_empty:
            cleaned = cell.replace(",", "").replace("$", "").replace(".", "").strip()
            if cleaned.isdigit():
                numeric_count += 1

        # If most cells are non-numeric, it looks like a header
        return numeric_count / len(non_empty) < 0.5 if non_empty else False

    def _classify_table(self, table: ExtractedTable) -> str:
        """Classify a table's type based on its content."""
        # Combine headers and first few data rows for keyword matching
        sample_text = " ".join(table.headers).lower()
        for row in table.rows[:3]:
            sample_text += " " + " ".join(row).lower()

        best_type = "unknown"
        best_score = 0

        for table_type, keywords in self._TABLE_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in sample_text)
            if score > best_score:
                best_score = score
                best_type = table_type

        return best_type if best_score >= 2 else "unknown"
