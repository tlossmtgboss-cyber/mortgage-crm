"""
Perennia AI — URLA Voice Input Validators
=========================================
Converts spoken / transcribed user input into structured URLA field values.

Deepgram Nova-3 is good but not perfect for digit strings, dates, and currency.
These validators normalize common transcription patterns so save tools can
accept natural answers.

Every validator returns either a parsed value or raises `URLAInputError` so the
agent can re-prompt with a clarification.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional


class URLAInputError(ValueError):
    """Raised when user input cannot be parsed. Agent should re-prompt."""


# =============================================================================
# SSN
# =============================================================================

_SSN_DIGITS_ONLY = re.compile(r"\D+")


def parse_ssn(raw: str) -> str:
    """
    Accepts: "123-45-6789", "123 45 6789", "one two three four five six seven eight nine",
    or any mix of digits with separators.
    Returns: "123-45-6789" (normalized).
    """
    if not raw:
        raise URLAInputError("SSN cannot be empty.")

    # First, convert spelled-out digits if Deepgram returned them (sometimes happens)
    raw = _spelled_digits_to_numeric(raw)

    digits = _SSN_DIGITS_ONLY.sub("", raw)
    if len(digits) != 9:
        raise URLAInputError(
            f"SSN must be 9 digits. Got {len(digits)} digit(s) from '{raw}'."
        )
    if digits == "123456789":
        raise URLAInputError("SSN appears invalid — please confirm.")
    if len(set(digits)) == 1:
        raise URLAInputError("SSN appears invalid — please confirm.")
    area = int(digits[:3])
    group = int(digits[3:5])
    serial = int(digits[5:])
    if area == 0 or area == 666 or area >= 900:
        raise URLAInputError("SSN area number is invalid — please confirm.")
    if group == 0:
        raise URLAInputError("SSN group number is invalid — please confirm.")
    if serial == 0:
        raise URLAInputError("SSN serial number is invalid — please confirm.")
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"


def ssn_digit_by_digit(ssn: str) -> str:
    """Return 'one two three ... nine' for voice readback."""
    digits = _SSN_DIGITS_ONLY.sub("", ssn)
    return " ".join(_NUM_TO_WORD[d] for d in digits)


# =============================================================================
# DATES
# =============================================================================

_MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_DATE_MDY_NUMERIC = re.compile(r"^\s*(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\s*$")
_DATE_WORD = re.compile(
    r"^\s*([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{2,4})\s*$"
)


def parse_date(raw: str) -> date:
    """
    Accepts:
      - '6/15/1988', '06-15-1988', '6.15.1988'
      - 'June 15, 1988', 'June 15 1988', 'Jun 15 88'
      - 'fifteenth of June nineteen eighty-eight' (best-effort via spelled digits)
    Returns datetime.date.
    """
    if not raw:
        raise URLAInputError("Date cannot be empty.")

    raw = raw.strip()

    # Try M/D/Y numeric first
    m = _DATE_MDY_NUMERIC.match(raw)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = _expand_2_digit_year(year)
        return _safe_date(year, month, day, raw)

    # Try "Month Day, Year"
    m = _DATE_WORD.match(raw)
    if m:
        month_name = m.group(1).lower()
        if month_name not in _MONTHS:
            raise URLAInputError(f"Unrecognized month '{m.group(1)}' in '{raw}'.")
        month = _MONTHS[month_name]
        day = int(m.group(2))
        year = _expand_2_digit_year(int(m.group(3)))
        return _safe_date(year, month, day, raw)

    # Last resort: strip spelled digits and retry numeric
    numeric = _spelled_digits_to_numeric(raw)
    m = _DATE_MDY_NUMERIC.match(numeric)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = _expand_2_digit_year(year)
        return _safe_date(year, month, day, raw)

    raise URLAInputError(f"Could not parse date from '{raw}'.")


def _expand_2_digit_year(year: int) -> int:
    if year >= 100:
        return year
    from datetime import date as _date
    current_year = _date.today().year
    century_2000 = 2000 + year
    century_1900 = 1900 + year
    # For DOBs, the year should never be in the future
    # Choose the interpretation that's most plausible (not in future, not impossibly old)
    if century_2000 <= current_year:
        return century_2000
    return century_1900


def _safe_date(year: int, month: int, day: int, raw: str) -> date:
    try:
        return date(year, month, day)
    except ValueError as e:
        raise URLAInputError(f"Invalid date '{raw}': {e}") from e


# =============================================================================
# CURRENCY / NUMBERS
# =============================================================================

_CURRENCY_CHARS = re.compile(r"[\$,\s]")
_NUMBER_WORD_MULTIPLIERS = {
    "thousand": 1_000,
    "k": 1_000,
    "million": 1_000_000,
    "m": 1_000_000,
    "mil": 1_000_000,
}


def parse_currency(raw: str) -> Decimal:
    """
    Accepts:
      - '$4,500', '4500', '4500.00'
      - '4.5k', '4500 dollars'
      - 'forty-five hundred', 'four thousand five hundred'
      - 'a hundred and fifty thousand'
    Returns: Decimal
    """
    if not raw:
        raise URLAInputError("Amount cannot be empty.")

    s = raw.lower().strip().replace("dollars", "").replace("bucks", "")
    s = _CURRENCY_CHARS.sub("", s)

    # Try direct numeric first
    try:
        return Decimal(s)
    except InvalidOperation:
        pass

    # Handle "4.5k" / "250k" / "1.2m"
    m = re.match(r"^(\d+(?:\.\d+)?)([kmM]|thousand|million|mil)$", s)
    if m:
        try:
            base = Decimal(m.group(1))
            mult = _NUMBER_WORD_MULTIPLIERS[m.group(2).lower()]
            return base * Decimal(mult)
        except InvalidOperation as e:
            raise URLAInputError(f"Could not parse currency '{raw}': {e}") from e

    # Spelled-out numbers
    numeric_s = _spelled_number_to_numeric(raw.lower())
    if numeric_s is not None:
        try:
            return Decimal(numeric_s)
        except InvalidOperation:
            pass

    raise URLAInputError(f"Could not parse currency from '{raw}'.")


# =============================================================================
# US STATES
# =============================================================================

_STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "washington dc": "DC", "d.c.": "DC",
}
_STATE_CODES = set(_STATE_NAME_TO_CODE.values())


def parse_state(raw: str) -> str:
    """Return USPS 2-letter code. Accepts full name or code."""
    if not raw:
        raise URLAInputError("State cannot be empty.")
    s = raw.strip().lower().rstrip(".")
    upper = s.upper()
    if upper in _STATE_CODES:
        return upper
    if s in _STATE_NAME_TO_CODE:
        return _STATE_NAME_TO_CODE[s]
    raise URLAInputError(f"Could not parse US state from '{raw}'.")


# =============================================================================
# PHONE
# =============================================================================

def parse_phone(raw: str) -> str:
    """Return E.164 phone number. Accepts US 10-digit and international numbers."""
    if not raw:
        raise URLAInputError("Phone number cannot be empty.")
    raw = _spelled_digits_to_numeric(raw)
    digits = re.sub(r"\D", "", raw)
    # US numbers
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    # International: accept 7-15 digit numbers with + prefix
    if raw.strip().startswith("+") and 7 <= len(digits) <= 15:
        return f"+{digits}"
    if 7 <= len(digits) <= 15:
        return f"+{digits}"
    raise URLAInputError(
        f"Phone number must be 10 digits (US) or a valid international number. Got {len(digits)} digits from '{raw}'."
    )


# =============================================================================
# YES / NO
# =============================================================================

_YES = {"yes", "yeah", "yep", "yup", "correct", "right", "sure", "absolutely",
        "affirmative", "that's right", "thats right", "uh huh", "mmhmm", "of course"}
_NO = {"no", "nope", "nah", "negative", "not at all", "don't", "dont",
       "not really", "incorrect", "wrong"}


def parse_yes_no(raw: str) -> bool:
    """Strict yes/no. Raises URLAInputError on ambiguity."""
    if not raw:
        raise URLAInputError("Please answer yes or no.")
    s = raw.lower().strip().rstrip(".!?").strip()
    for token in _YES:
        if s == token or s.startswith(token + " "):
            return True
    for token in _NO:
        if s == token or s.startswith(token + " "):
            return False
    # Heuristic: first word
    first = s.split()[0] if s.split() else ""
    if first in _YES:
        return True
    if first in _NO:
        return False
    raise URLAInputError(f"Could not determine yes or no from '{raw}'.")


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

_WORD_TO_NUM = {
    "zero": "0", "oh": "0", "o": "0",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9",
}
_NUM_TO_WORD = {v: k for k, v in _WORD_TO_NUM.items() if len(v) == 1}
_NUM_TO_WORD["0"] = "zero"


def _spelled_digits_to_numeric(raw: str) -> str:
    """Convert 'one two three' -> '123' within a larger string."""
    tokens = re.split(r"(\s+|-)", raw.lower())
    out = []
    for t in tokens:
        if t in _WORD_TO_NUM:
            out.append(_WORD_TO_NUM[t])
        else:
            out.append(t)
    return "".join(out)


_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1_000, "million": 1_000_000,
    "half": 0.5, "quarter": 0.25,
}


def _spelled_number_to_numeric(raw: str) -> Optional[str]:
    """
    Very small spelled-number parser — good enough for common currency phrasing.
    Supports decimals via "point" and fractional multipliers ("half", "quarter").
    Returns string representation or None if it can't parse.
    """
    tokens = re.findall(r"[a-z]+", raw.lower())
    if not tokens:
        return None
    if not any(t in _NUMBER_WORDS for t in tokens):
        return None

    total = 0
    current = 0
    decimal_part = 0
    in_decimal = False

    for t in tokens:
        if t == "point":
            in_decimal = True
            continue
        if t in ("and", "a"):
            continue
        if t not in _NUMBER_WORDS:
            return None
        v = _NUMBER_WORDS[t]
        if isinstance(v, float):
            # "half" or "quarter" — multiply into current group
            if current == 0:
                current = v
            else:
                current += v
        elif v >= 100:
            if current == 0:
                current = 1
            current *= v
            if v >= 1000:
                total += current
                current = 0
        elif in_decimal:
            # "point five" → 0.5
            decimal_part = v / (10 ** len(str(v)))
            in_decimal = False
        else:
            current += v
    total += current + decimal_part
    return str(total) if total > 0 else None
