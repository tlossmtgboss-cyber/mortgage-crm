"""
PII Log Redaction Filter
Enterprise Readiness Check 3.20 - PII must not appear in application logs

Automatically redacts SSN, credit card numbers, and other PII patterns
from all log messages before they're written.

Usage:
    import logging
    from middleware.pii_log_filter import PIIRedactionFilter

    # Apply to root logger (catches everything)
    logging.getLogger().addFilter(PIIRedactionFilter())
"""
import re
import logging


class PIIRedactionFilter(logging.Filter):
    """Filter that redacts PII patterns from log records."""

    # Patterns to redact — keyword-specific patterns FIRST to avoid SSN pattern
    # consuming digits that belong to routing/account numbers
    PATTERNS = [
        # Bank account numbers (8-17 digits preceded by account keyword)
        (re.compile(r'\baccount[_\s#:]*(\d{8,17})\b', re.IGNORECASE), r'account [ACCT_REDACTED]'),
        # Routing numbers (9 digits preceded by routing keyword)
        (re.compile(r'\brouting[_\s#:]*(\d{9})\b', re.IGNORECASE), r'routing [RTN_REDACTED]'),
        # Credit card: 16 digits with optional separators
        (re.compile(r'\b(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})\b'), r'****-****-****-\4'),
        # SSN: 123-45-6789 or 123456789 or 123 45 6789
        (re.compile(r'\b(\d{3})[-\s]?(\d{2})[-\s]?(\d{4})\b'), r'***-**-\3'),
        # Date of Birth patterns: MM/DD/YYYY, YYYY-MM-DD
        (re.compile(r'\b(0[1-9]|1[0-2])[/\-](0[1-9]|[12]\d|3[01])[/\-](19|20)\d{2}\b'), '[DOB_REDACTED]'),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact PII from log message and args."""
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._redact(str(v)) if isinstance(v, str) else v
                              for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._redact(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )

        # Also redact exception info if present
        if record.exc_text:
            record.exc_text = self._redact(record.exc_text)

        return True  # Always allow the record through (just redacted)

    def _redact(self, text: str) -> str:
        """Apply all redaction patterns to text."""
        for pattern, replacement in self.PATTERNS:
            text = pattern.sub(replacement, text)
        return text


def install_pii_filter():
    """Install PII redaction filter on the root logger.
    Call this once during application startup."""
    root_logger = logging.getLogger()

    # Check if already installed
    for f in root_logger.filters:
        if isinstance(f, PIIRedactionFilter):
            return

    root_logger.addFilter(PIIRedactionFilter())
    logging.getLogger(__name__).info("PII redaction filter installed on root logger")
