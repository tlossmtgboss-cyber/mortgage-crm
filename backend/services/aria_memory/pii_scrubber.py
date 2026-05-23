"""
PII Scrubber for Aria Memory Pipeline

Strips PII from text BEFORE it is sent to external LLM APIs
(OpenAI for embeddings, Anthropic for extraction).

Redacts:
  - SSN (XXX-XX-XXXX, XXX XX XXXX, 9 consecutive digits)
  - DOB (date-of-birth patterns preceded by keywords)
  - Account numbers (preceded by "account" / "acct" keywords)
  - Credit card numbers (13-19 digit sequences with optional separators)

Preserves:
  - Phone numbers (needed for contact matching)
  - Email addresses (needed for borrower matching)

Two entry points:
  scrub_pii(text)              -- redacts PII, leaves tokens like [SSN_REDACTED]
  scrub_pii_for_embedding(text) -- redacts PII AND removes the tokens themselves
                                   so they don't pollute embedding vectors
"""

import logging
import re

logger = logging.getLogger("aria.memory.pii")

# ---------------------------------------------------------------------------
# Compiled regex patterns (compiled once at import time for performance)
# ---------------------------------------------------------------------------

# SSN: 123-45-6789
_SSN_DASHED = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# SSN: 123 45 6789
_SSN_SPACED = re.compile(r"\b\d{3}\s\d{2}\s\d{4}\b")

# SSN: 9 consecutive digits not preceded/followed by a digit.
# Use negative lookbehind/lookahead to avoid matching inside longer digit
# sequences (phone numbers, account numbers handled separately).
# Also exclude sequences starting with common phone-number area-code contexts.
_SSN_BARE = re.compile(
    r"(?<!\d)(?<!\d[-\s])"   # not preceded by digit or digit-separator
    r"\d{9}"
    r"(?![-\s]?\d)"          # not followed by separator-digit
)

# DOB: keyword ("date of birth", "DOB", "born on", "birthday", "birth date")
# followed by optional separator and a date in common formats.
_DOB_KEYWORD = re.compile(
    r"(?i)"
    r"(?:date\s+of\s+birth|d\.?o\.?b\.?|born\s+on|birth\s*date|birthday)"
    r"[\s:,]*"
    r"("
    r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}"  # MM/DD/YYYY or DD-MM-YYYY
    r"|"
    r"\d{4}[/\-]\d{1,2}[/\-]\d{1,2}"    # YYYY-MM-DD
    r"|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
    r"\s+\d{1,2},?\s+\d{4}"             # Month DD, YYYY
    r"|"
    r"\d{1,2}\s+"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
    r",?\s+\d{4}"                        # DD Month YYYY
    r")"
)

# Account numbers: "account" or "acct" followed by optional separators and 6+ digits.
_ACCOUNT_NUM = re.compile(
    r"(?i)"
    r"(?:account|acct)\.?"
    r"[\s#:_.\-]*"
    r"(?:number|num|no\.?)?[\s#:_.\-]*"
    r"(\d[\d\s\-]{5,})"    # 6+ digits (may contain spaces/dashes)
)

# Credit card numbers: 13-19 digits with optional spaces/dashes between groups.
# Negative lookbehind/lookahead for digits to avoid matching inside longer runs.
# We also exclude sequences that look like phone numbers (10-11 digits).
_CC_NUMBER = re.compile(
    r"(?<!\d)"
    r"(?:"
    r"\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{1,4}"  # 4-4-4-4 grouped
    r"|"
    r"\d{4}[\s\-]\d{6}[\s\-]\d{4,5}"              # Amex style 4-6-5
    r"|"
    r"\d{13,19}"                                    # contiguous 13-19 digits
    r")"
    r"(?!\d)"
)

# Phone number pattern for EXCLUSION — we use this to avoid false-positive
# credit-card matches on phone numbers. US phone: 10-11 digits, optionally
# formatted. Requires at least one separator OR explicit word boundary to
# avoid matching substrings of longer digit runs (e.g., credit card numbers).
_PHONE_PATTERN = re.compile(
    r"(?:"
    r"\+1[\s\-.]?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"       # +1 prefix
    r"|"
    r"\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4}"                   # formatted: (843) 383-8956, 843-383-8956, 843.383.8956
    r"|"
    r"(?<!\d)\d{10,11}(?!\d)"                                   # bare 10-11 digits with no adjacent digits
    r")"
)

# Redaction tokens
_REDACTION_TOKENS = re.compile(
    r"\[(?:SSN|DOB|ACCOUNT|CC)_REDACTED\]"
)


def _is_phone_number(match_text: str) -> bool:
    """Check if a digit sequence is actually a phone number."""
    digits_only = re.sub(r"[^\d]", "", match_text)
    # US phone numbers are 10 or 11 digits (with leading 1)
    if len(digits_only) in (10, 11):
        return True
    return False


def scrub_pii(text: str) -> str:
    """
    Redact PII patterns from text, replacing with descriptive tokens.

    Phone numbers and email addresses are intentionally preserved
    because they are needed for contact and borrower matching.
    """
    if not text:
        return text

    original = text
    redaction_count = 0

    # --- SSN (dashed and spaced formats first — unambiguous) ---
    count = len(_SSN_DASHED.findall(text))
    if count:
        text = _SSN_DASHED.sub("[SSN_REDACTED]", text)
        redaction_count += count

    count = len(_SSN_SPACED.findall(text))
    if count:
        text = _SSN_SPACED.sub("[SSN_REDACTED]", text)
        redaction_count += count

    # --- DOB (before bare SSN to avoid date digits being consumed) ---
    count = len(_DOB_KEYWORD.findall(text))
    if count:
        text = _DOB_KEYWORD.sub("[DOB_REDACTED]", text)
        redaction_count += count

    # --- Account numbers (keyword-anchored, before bare SSN) ---
    count = len(_ACCOUNT_NUM.findall(text))
    if count:
        text = _ACCOUNT_NUM.sub("[ACCOUNT_REDACTED]", text)
        redaction_count += count

    # --- Credit card numbers (before bare SSN to avoid 16-digit CCs
    #     being partially consumed as 9-digit SSNs) ---
    phone_ranges = set()
    for pm in _PHONE_PATTERN.finditer(text):
        phone_ranges.add((pm.start(), pm.end()))

    for m in reversed(list(_CC_NUMBER.finditer(text))):
        match_text = m.group()
        digits_only = re.sub(r"[^\d]", "", match_text)

        # Skip if this is a phone number (10-11 digits)
        if _is_phone_number(match_text):
            continue

        # Skip if this overlaps with a known phone match
        overlaps_phone = any(
            not (m.end() <= ps or m.start() >= pe)
            for ps, pe in phone_ranges
        )
        if overlaps_phone:
            continue

        # Only flag as CC if 13-19 digits
        if 13 <= len(digits_only) <= 19:
            text = text[:m.start()] + "[CC_REDACTED]" + text[m.end():]
            redaction_count += 1

    # --- Bare 9-digit SSN (last — most ambiguous, after keyword-anchored
    #     patterns have already consumed their digit sequences) ---
    for m in reversed(list(_SSN_BARE.finditer(text))):
        if not _is_phone_number(m.group()):
            text = text[:m.start()] + "[SSN_REDACTED]" + text[m.end():]
            redaction_count += 1

    if redaction_count > 0:
        logger.info(
            "PII scrubbed: %d redaction(s) applied (%d chars -> %d chars)",
            redaction_count, len(original), len(text),
        )

    return text


def scrub_pii_for_embedding(text: str) -> str:
    """
    Redact PII and then strip the redaction tokens themselves.

    Used before generating embeddings so that tokens like [SSN_REDACTED]
    don't pollute the vector space.
    """
    text = scrub_pii(text)
    text = _REDACTION_TOKENS.sub("", text)
    # Collapse any resulting double-spaces
    text = re.sub(r"  +", " ", text).strip()
    return text
