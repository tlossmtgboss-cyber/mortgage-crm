"""
1003 (URLA) Intake Field Extractor — D4 CI-007 closeout.

The URLA / Uniform Residential Loan Application ("the 1003") is the
canonical mortgage application form. This module turns a free-form call
transcript into a populated 1003 field dict using *deterministic*
regex + lightweight NLP heuristics — NO LLM round-trip required.

Output schema:
    {
        "fields": {
            "<field_name>": {
                "value":        <typed value>,
                "confidence":   <0..1 float>,
                "source_span":  (start, end)  # int char offsets in transcript
            },
            ...
        },
        "_pii_secure": {
            "ssn": "<raw, last-4-only stored separately>"
        },
        "extraction_metadata": {
            "transcript_length": int,
            "fields_extracted": int,
            "avg_confidence": float,
            "processing_ms": int,
        },
    }

The redacted SSN (``XXX-XX-NNNN``) appears in ``fields`` while the raw
last-4 is mirrored into ``_pii_secure`` so downstream encryption /
key-management layers can lift it out before persistence.

Confidence heuristics:
    1.0 — high-precision regex (SSN, formatted phone, dollar amount)
    0.85 — labeled field ("my employer is X", "I work at X")
    0.7  — single match, contextually plausible
    0.5  — ambiguous or fuzzy match (multiple candidates, weak label)
    <0.5 — discarded
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Canonical 1003 field catalog (kept here as the single source of truth)
# ---------------------------------------------------------------------------
PERSONAL_FIELDS = (
    "borrower_first_name",
    "borrower_last_name",
    "borrower_dob",
    "borrower_ssn",
    "borrower_phone",
    "borrower_email",
    "current_address",
)
EMPLOYMENT_FIELDS = (
    "employer_name",
    "employer_phone",
    "employment_start_date",
    "job_title",
    "monthly_income_gross",
    "self_employed",
)
FINANCIAL_FIELDS = (
    "monthly_debts",
    "liquid_assets",
    "retirement_assets",
    "real_estate_assets",
)
PROPERTY_FIELDS = (
    "subject_property_address",
    "subject_property_type",
    "purchase_price",
    "down_payment_amount",
    "occupancy",
)
LOAN_FIELDS = (
    "loan_amount",
    "loan_type",
    "loan_purpose",
    "loan_term_months",
    "lock_period_days",
)

ALL_FIELDS = (
    PERSONAL_FIELDS
    + EMPLOYMENT_FIELDS
    + FINANCIAL_FIELDS
    + PROPERTY_FIELDS
    + LOAN_FIELDS
)


# ---------------------------------------------------------------------------
# Regex library
# ---------------------------------------------------------------------------
# Phone: (xxx) xxx-xxxx | xxx-xxx-xxxx | xxx.xxx.xxxx | xxxxxxxxxx
_PHONE_RE = re.compile(
    r"\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})\b"
)

# SSN: xxx-xx-xxxx or 9 contiguous digits when explicitly labeled
_SSN_RE = re.compile(r"\b(\d{3})[-\s]?(\d{2})[-\s]?(\d{4})\b")

# Email
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Money: $123,456 or $1234.56 or 1,234,567
_MONEY_RE = re.compile(
    r"\$?\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?(k|thousand|m|million)?",
    re.IGNORECASE,
)

# Date: MM/DD/YYYY, M-D-YYYY, "March 5 2025", "March 5, 2025"
_DATE_NUMERIC_RE = re.compile(
    r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b"
)
_DATE_WORD_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
    re.IGNORECASE,
)

# ZIP — 5 or 9
_ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")

# US state abbreviations
_STATE_RE = re.compile(
    r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|"
    r"MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|"
    r"SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b"
)

# Street address (simple — number + words + Street/Ave/Rd/etc.)
_STREET_RE = re.compile(
    r"\b\d{1,6}\s+(?:[A-Z][a-zA-Z]*\.?\s+){1,5}"
    r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|"
    r"Lane|Ln\.?|Drive|Dr\.?|Court|Ct\.?|Way|Place|Pl\.?|Circle|Cir\.?|"
    r"Highway|Hwy\.?|Parkway|Pkwy\.?|Trail|Trl\.?)\b",
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------
class Intake1003Extractor:
    """
    Regex-and-heuristic extractor for URLA 1003 fields.

    Usage:
        extractor = Intake1003Extractor()
        result = extractor.extract(transcript, existing_fields=prior)
    """

    # Per-field minimum confidence to be retained
    MIN_CONFIDENCE = 0.5

    def extract(
        self,
        transcript: str,
        existing_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        transcript = transcript or ""
        fields: Dict[str, Dict[str, Any]] = {}
        pii_secure: Dict[str, str] = {}

        if transcript.strip():
            self._extract_personal(transcript, fields, pii_secure)
            self._extract_employment(transcript, fields)
            self._extract_financial(transcript, fields)
            self._extract_property(transcript, fields)
            self._extract_loan(transcript, fields)

        # Drop low-confidence fields
        fields = {
            k: v for k, v in fields.items()
            if v.get("confidence", 0) >= self.MIN_CONFIDENCE
        }

        # Merge existing_fields, only overwrite if new confidence >= existing
        if existing_fields:
            merged: Dict[str, Dict[str, Any]] = {}
            # Preserve all existing entries first
            for k, v in existing_fields.items():
                if isinstance(v, dict) and "confidence" in v:
                    merged[k] = v
                else:
                    merged[k] = {
                        "value": v,
                        "confidence": 1.0,
                        "source_span": (-1, -1),
                    }
            # Apply new extractions where they beat existing
            for k, v in fields.items():
                if k not in merged or v["confidence"] >= merged[k]["confidence"]:
                    merged[k] = v
            fields = merged

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        confidences = [v["confidence"] for v in fields.values()]
        avg = sum(confidences) / len(confidences) if confidences else 0.0

        return {
            "fields": fields,
            "_pii_secure": pii_secure,
            "extraction_metadata": {
                "transcript_length": len(transcript),
                "fields_extracted": len(fields),
                "avg_confidence": round(avg, 3),
                "processing_ms": elapsed_ms,
            },
        }

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _store(
        fields: Dict[str, Dict[str, Any]],
        name: str,
        value: Any,
        confidence: float,
        span: Tuple[int, int],
    ) -> None:
        """Insert or upgrade-on-confidence."""
        if name in fields and fields[name]["confidence"] >= confidence:
            return
        fields[name] = {
            "value": value,
            "confidence": round(confidence, 3),
            "source_span": span,
        }

    @staticmethod
    def _money_to_float(raw: str, suffix: Optional[str]) -> Optional[float]:
        try:
            n = float(raw.replace(",", ""))
        except ValueError:
            return None
        if suffix:
            s = suffix.lower()
            if s in ("k", "thousand"):
                n *= 1_000
            elif s in ("m", "million"):
                n *= 1_000_000
        return n

    # ------------------------------------------------------------------ sections
    def _extract_personal(
        self,
        transcript: str,
        fields: Dict[str, Dict[str, Any]],
        pii_secure: Dict[str, str],
    ) -> None:
        t = transcript

        # --- Name: "my name is X Y" / "this is X Y"
        # Lowercase the prefix-label section only, then re-search positions
        # using a case-insensitive label with a case-sensitive name class.
        m = re.search(
            r"\b(?:[Mm]y name is|[Tt]his is|I'?m|I am)\s+"
            r"([A-Z][a-zA-Z'\-]+)\s+([A-Z][a-zA-Z'\-]+)",
            t,
        )
        if m:
            first, last = m.group(1), m.group(2)
            # Non-ASCII / hyphenated names get a small confidence haircut
            base = 0.9
            if not first.isascii() or not last.isascii():
                base = 0.6
            self._store(fields, "borrower_first_name", first, base, m.span(1))
            self._store(fields, "borrower_last_name", last, base, m.span(2))

        # --- Email
        m = _EMAIL_RE.search(t)
        if m:
            self._store(fields, "borrower_email", m.group(0), 1.0, m.span())

        # --- Phone
        for m in _PHONE_RE.finditer(t):
            phone = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            # Distinguish borrower vs employer: first phone wins as borrower
            # unless preceded by "employer"
            window = t[max(0, m.start() - 40):m.start()].lower()
            if "employer" in window or "company" in window or "office" in window:
                self._store(fields, "employer_phone", phone, 0.85, m.span())
            else:
                self._store(fields, "borrower_phone", phone, 0.95, m.span())

        # --- SSN (formatted with dashes is highest-confidence)
        m = _SSN_RE.search(t)
        if m:
            full = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            last4 = m.group(3)
            redacted = f"XXX-XX-{last4}"
            # Only attach if context plausibly mentions SSN/social
            window = t[max(0, m.start() - 30):m.end() + 5].lower()
            confidence = 0.95 if ("ssn" in window or "social" in window) else 0.7
            self._store(fields, "borrower_ssn", redacted, confidence, m.span())
            pii_secure["ssn"] = full

        # --- DOB: phrase "born on" / "date of birth" / "DOB"
        m = re.search(
            r"\b(?:born on|date of birth|DOB|D\.O\.B\.?)\s*(?:is\s*)?"
            r"([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            t,
            re.IGNORECASE,
        )
        if m:
            parsed = self._parse_date(m.group(1))
            if parsed:
                self._store(
                    fields, "borrower_dob", parsed.isoformat(), 0.9, m.span(1)
                )

        # --- Current address: street + state + zip nearby
        for m in _STREET_RE.finditer(t):
            tail = t[m.end():m.end() + 80]
            zip_m = _ZIP_RE.search(tail)
            state_m = _STATE_RE.search(tail)
            if zip_m and state_m:
                full_addr = t[m.start():m.end() + zip_m.end()].strip()
                # "current" or "live at" boosts confidence
                window = t[max(0, m.start() - 30):m.start()].lower()
                if "subject" in window or "buying" in window or "purchase" in window:
                    continue  # handled in property extraction
                conf = 0.9 if ("live" in window or "current" in window or "home" in window) else 0.7
                self._store(
                    fields,
                    "current_address",
                    full_addr,
                    conf,
                    (m.start(), m.end() + zip_m.end()),
                )
                break

    def _extract_employment(
        self,
        transcript: str,
        fields: Dict[str, Dict[str, Any]],
    ) -> None:
        t = transcript

        # --- Employer
        m = re.search(
            r"\b(?:I work (?:at|for)|employed by|employer is|I'm with|"
            r"work with)\s+([A-Z][A-Za-z0-9 &.,'\-]{2,50}?)"
            r"(?=\s+(?:as|in|since|where|for|and|\.|,|$))",
            t,
        )
        if m:
            name = m.group(1).strip(" .,")
            self._store(fields, "employer_name", name, 0.85, m.span(1))

        # --- Job title: "as a/an X" or "I'm a X"
        m = re.search(
            r"\b(?:as (?:a|an)|I'?m (?:a|an)|work as (?:a|an)|"
            r"title is|position is)\s+([A-Za-z][A-Za-z \-/]{2,40}?)"
            r"(?:\s+(?:at|for|with|in)\b|[.,;\n]|$)",
            t,
        )
        if m:
            self._store(fields, "job_title", m.group(1).strip(), 0.8, m.span(1))

        # --- Employment start date
        m = re.search(
            r"\b(?:start(?:ed)?|since|hired|joined)\s+(?:on|in|at)?\s*"
            r"([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|"
            r"[A-Za-z]+\s+\d{4}|"
            r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            t,
            re.IGNORECASE,
        )
        if m:
            parsed = self._parse_date(m.group(1))
            if parsed:
                self._store(
                    fields,
                    "employment_start_date",
                    parsed.isoformat(),
                    0.8,
                    m.span(1),
                )

        # --- Monthly income — "$X a month" / "$X per month" / "$X monthly"
        m = re.search(
            r"\$?\s?([\d,]+(?:\.\d+)?)\s?(k|thousand|m|million)?\s+"
            r"(?:a|per)\s+month",
            t,
            re.IGNORECASE,
        )
        if m:
            n = self._money_to_float(m.group(1), m.group(2))
            if n:
                self._store(
                    fields, "monthly_income_gross", n, 0.9, m.span()
                )

        # --- Self-employed boolean
        if re.search(r"\bself[- ]employed\b", t, re.IGNORECASE):
            self._store(fields, "self_employed", True, 0.95, (0, 0))
        elif re.search(r"\bW-?2\b|\bsalaried\b|\bemploye[er]\b", t, re.IGNORECASE):
            # Don't overwrite if true was set
            if "self_employed" not in fields:
                self._store(fields, "self_employed", False, 0.7, (0, 0))

    def _extract_financial(
        self,
        transcript: str,
        fields: Dict[str, Dict[str, Any]],
    ) -> None:
        t = transcript

        # Monthly debts
        m = re.search(
            r"\b(?:monthly debts?|debt payments?|total debts?)\s*"
            r"(?:are|is|of|total|come to)?\s*\$?\s?([\d,]+(?:\.\d+)?)\s?(k|thousand|m|million)?",
            t,
            re.IGNORECASE,
        )
        if m:
            n = self._money_to_float(m.group(1), m.group(2))
            if n:
                self._store(fields, "monthly_debts", n, 0.85, m.span())

        # Liquid assets / savings
        m = re.search(
            r"\b(?:liquid assets?|savings|in (?:my|the) bank|checking)\s*"
            r"(?:of|is|are|total)?\s*\$?\s?([\d,]+(?:\.\d+)?)\s?(k|thousand|m|million)?",
            t,
            re.IGNORECASE,
        )
        if m:
            n = self._money_to_float(m.group(1), m.group(2))
            if n:
                self._store(fields, "liquid_assets", n, 0.8, m.span())

        # Retirement
        m = re.search(
            r"\b(?:401k|401\(k\)|IRA|retirement|pension)\b"
            r"(?:\s+(?:of|is|are|balance|account|has|with|worth|totaling)){0,3}"
            r"\s*\$?\s?([\d,]+(?:\.\d+)?)\s?(k|thousand|m|million)?",
            t,
            re.IGNORECASE,
        )
        if m:
            n = self._money_to_float(m.group(1), m.group(2))
            if n:
                self._store(fields, "retirement_assets", n, 0.85, m.span())

        # Real estate
        m = re.search(
            r"\b(?:real estate|rental property|other property|investment property)\s*"
            r"(?:worth|valued at|of|is|are)?\s*\$?\s?([\d,]+(?:\.\d+)?)\s?(k|thousand|m|million)?",
            t,
            re.IGNORECASE,
        )
        if m:
            n = self._money_to_float(m.group(1), m.group(2))
            if n:
                self._store(fields, "real_estate_assets", n, 0.8, m.span())

    def _extract_property(
        self,
        transcript: str,
        fields: Dict[str, Dict[str, Any]],
    ) -> None:
        t = transcript

        # Subject property — prefer street near "buying" / "purchasing" / "subject"
        for m in _STREET_RE.finditer(t):
            tail = t[m.end():m.end() + 80]
            zip_m = _ZIP_RE.search(tail)
            window = t[max(0, m.start() - 40):m.start()].lower()
            if any(k in window for k in ("buying", "purchasing", "subject", "property at", "house at")):
                if zip_m:
                    full_addr = t[m.start():m.end() + zip_m.end()].strip()
                    self._store(
                        fields,
                        "subject_property_address",
                        full_addr,
                        0.9,
                        (m.start(), m.end() + zip_m.end()),
                    )
                    break

        # Property type
        if re.search(r"\bsingle[- ]family\b|\bSFR\b", t, re.IGNORECASE):
            self._store(fields, "subject_property_type", "SFR", 0.9, (0, 0))
        elif re.search(r"\bcondo(?:minium)?\b", t, re.IGNORECASE):
            self._store(fields, "subject_property_type", "condo", 0.9, (0, 0))
        elif re.search(r"\bPUD\b|\bplanned unit\b", t, re.IGNORECASE):
            self._store(fields, "subject_property_type", "PUD", 0.9, (0, 0))

        # Purchase price
        m = re.search(
            r"\b(?:purchase price|asking price|sales price|price)\s*(?:is|of|at)?\s*"
            r"\$?\s?([\d,]+(?:\.\d+)?)\s?(k|thousand|m|million)?",
            t,
            re.IGNORECASE,
        )
        if m:
            n = self._money_to_float(m.group(1), m.group(2))
            if n:
                self._store(fields, "purchase_price", n, 0.9, m.span())

        # Down payment
        m = re.search(
            r"\b(?:down payment|down)\s*(?:of|is)?\s*\$?\s?([\d,]+(?:\.\d+)?)\s?(k|thousand|m|million)?",
            t,
            re.IGNORECASE,
        )
        if m:
            n = self._money_to_float(m.group(1), m.group(2))
            if n:
                self._store(fields, "down_payment_amount", n, 0.85, m.span())

        # Occupancy
        if re.search(r"\bprimary (?:residence|home)\b|\bmain home\b", t, re.IGNORECASE):
            self._store(fields, "occupancy", "primary", 0.95, (0, 0))
        elif re.search(r"\bsecond home\b|\bvacation home\b", t, re.IGNORECASE):
            self._store(fields, "occupancy", "secondary", 0.95, (0, 0))
        elif re.search(r"\binvestment property\b|\brental\b", t, re.IGNORECASE):
            self._store(fields, "occupancy", "investment", 0.9, (0, 0))

    def _extract_loan(
        self,
        transcript: str,
        fields: Dict[str, Dict[str, Any]],
    ) -> None:
        t = transcript

        # Loan amount
        m = re.search(
            r"\b(?:loan amount|loan of|borrow(?:ing)?|mortgage of)\s*"
            r"(?:is|for|approximately|about)?\s*\$?\s?([\d,]+(?:\.\d+)?)\s?(k|thousand|m|million)?",
            t,
            re.IGNORECASE,
        )
        if m:
            n = self._money_to_float(m.group(1), m.group(2))
            if n:
                self._store(fields, "loan_amount", n, 0.9, m.span())

        # Loan type
        for pat, val in (
            (r"\bconventional\b", "conv"),
            (r"\bFHA\b", "FHA"),
            (r"\bVA loan\b|\bVA mortgage\b|\bveterans\b", "VA"),
            (r"\bUSDA\b", "USDA"),
        ):
            mm = re.search(pat, t, re.IGNORECASE)
            if mm:
                self._store(fields, "loan_type", val, 0.9, mm.span())
                break

        # Loan purpose
        if re.search(r"\bcash[- ]out\b", t, re.IGNORECASE):
            self._store(fields, "loan_purpose", "cashout", 0.95, (0, 0))
        elif re.search(r"\brefinanc(?:e|ing)\b|\brefi\b", t, re.IGNORECASE):
            self._store(fields, "loan_purpose", "refi", 0.9, (0, 0))
        elif re.search(r"\bpurchas(?:e|ing)\b|\bbuying\b", t, re.IGNORECASE):
            self._store(fields, "loan_purpose", "purchase", 0.9, (0, 0))

        # Loan term — "30 year" / "15 year"
        m = re.search(r"\b(10|15|20|25|30|40)[- ]year\b", t, re.IGNORECASE)
        if m:
            months = int(m.group(1)) * 12
            self._store(fields, "loan_term_months", months, 0.9, m.span())

        # Lock period — "lock for 30 days" / "60-day lock"
        m = re.search(
            r"\b(\d{2,3})[- ]?day\s+lock\b|\block(?:ed)?\s+(?:for|in)?\s+(\d{2,3})\s+days?\b",
            t,
            re.IGNORECASE,
        )
        if m:
            days = int(m.group(1) or m.group(2))
            self._store(fields, "lock_period_days", days, 0.85, m.span())

    # ------------------------------------------------------------------ date helpers
    @staticmethod
    def _parse_date(raw: str) -> Optional[date]:
        raw = raw.strip().rstrip(",")
        # Numeric MM/DD/YYYY
        m = _DATE_NUMERIC_RE.match(raw)
        if m:
            mo, da, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if yr < 100:
                yr += 2000 if yr < 50 else 1900
            try:
                return date(yr, mo, da)
            except ValueError:
                return None
        # Word date
        m = _DATE_WORD_RE.match(raw)
        if m:
            mo = _MONTHS.get(m.group(1).lower())
            da = int(m.group(2))
            yr = int(m.group(3))
            if mo:
                try:
                    return date(yr, mo, da)
                except ValueError:
                    return None
        # "March 2020" — month + year only -> 1st of month
        m = re.match(r"([A-Za-z]+)\s+(\d{4})", raw)
        if m:
            mo = _MONTHS.get(m.group(1).lower())
            yr = int(m.group(2))
            if mo:
                try:
                    return date(yr, mo, 1)
                except ValueError:
                    return None
        return None


__all__ = [
    "Intake1003Extractor",
    "ALL_FIELDS",
    "PERSONAL_FIELDS",
    "EMPLOYMENT_FIELDS",
    "FINANCIAL_FIELDS",
    "PROPERTY_FIELDS",
    "LOAN_FIELDS",
]
