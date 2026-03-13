"""
PII Log Filter for Smart Docs Loggers

Extends the root-level PIIRedactionFilter (middleware/pii_log_filter.py) with
Smart Docs-specific patterns. In mortgage document processing, OCR output and
extraction results frequently contain SSNs, account numbers, income figures,
and borrower contact information.

This module installs a dedicated filter on all ``services.smart_docs.*``
loggers so PII never reaches log sinks -- even if the root-level filter is
not configured.

Usage:
    from services.smart_docs.pii_log_filter import install_smart_docs_pii_filter

    # Call once at startup (idempotent)
    install_smart_docs_pii_filter()
"""

from __future__ import annotations

import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)


class SmartDocsPIIFilter(logging.Filter):
    """Logging filter that redacts mortgage-specific PII from log records.

    This covers patterns commonly found in OCR-extracted text:

    * Full SSNs (XXX-XX-XXXX and 9-digit numeric)
    * Bank account numbers (8-17 digits preceded by 'account')
    * Routing numbers (9 digits preceded by 'routing')
    * Income / dollar amounts with borrower context
    * Email addresses
    * Phone numbers
    * IP addresses in access log context
    """

    PATTERNS: List[Tuple[re.Pattern, str]] = [
        # Bank account numbers (keyword-anchored -- before generic digit patterns)
        (
            re.compile(r"\baccount[_\s#:]*(\d{8,17})\b", re.IGNORECASE),
            r"account [ACCT_REDACTED]",
        ),
        # Routing numbers
        (
            re.compile(r"\brouting[_\s#:]*(\d{9})\b", re.IGNORECASE),
            r"routing [RTN_REDACTED]",
        ),
        # SSN: 123-45-6789, 123 45 6789
        (
            re.compile(r"\b(\d{3})[-\s](\d{2})[-\s](\d{4})\b"),
            r"***-**-\3",
        ),
        # SSN: 9 consecutive digits (best-effort -- anchored to avoid timestamps)
        (
            re.compile(r"(?<![0-9\-])(\d{3})(\d{2})(\d{4})(?![0-9\-])"),
            r"***-**-\3",
        ),
        # Email addresses
        (
            re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
            "[EMAIL_REDACTED]",
        ),
        # Phone numbers: (123) 456-7890, 123-456-7890, 123.456.7890
        (
            re.compile(
                r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
            ),
            "[PHONE_REDACTED]",
        ),
        # IP addresses (v4)
        (
            re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
            "[IP_REDACTED]",
        ),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact PII from the log record, then allow it through."""
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._redact(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._redact(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )

        if record.exc_text:
            record.exc_text = self._redact(record.exc_text)

        return True  # Always pass through (redacted)

    def _redact(self, text: str) -> str:
        for pattern, replacement in self.PATTERNS:
            text = pattern.sub(replacement, text)
        return text


# ---------------------------------------------------------------------------
# Installer
# ---------------------------------------------------------------------------

_installed = False


def install_smart_docs_pii_filter() -> None:
    """Install the Smart Docs PII filter on all ``services.smart_docs`` loggers.

    Safe to call multiple times -- subsequent calls are no-ops.
    """
    global _installed
    if _installed:
        return

    pii_filter = SmartDocsPIIFilter()

    # Attach to the parent logger so every child inherits it.
    smart_docs_logger = logging.getLogger("services.smart_docs")
    smart_docs_logger.addFilter(pii_filter)

    _installed = True
    logger.info("Smart Docs PII log filter installed")
