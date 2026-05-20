"""Email identity resolution service for IBMA pipeline.

This module centralizes how we map inbound emails to CRM entities
using identifiers like email addresses, loan numbers, and known
client metadata. It is used by the email ingestion endpoints to
pre-populate reconciliation queue records with the most confident
matches available.

Key Features:
- Multi-strategy matching (known clients, leads, loans, loan numbers)
- Confidence scoring for each match type
- Priority flagging for high-confidence matches
- Comprehensive address extraction from various email formats
- Thread-aware matching for conversation continuity
- Domain-based vendor/partner classification
- Gmail alias normalization (handles + and . variants)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# ============================================================
# Email Normalization Utilities
# ============================================================

def normalize_email(email: str) -> str:
    """Normalize email for consistent matching.

    Handles:
    - Lowercase conversion
    - Whitespace trimming
    - Gmail dot-insensitivity (a.b.c@gmail.com = abc@gmail.com)
    - Gmail plus aliases (user+tag@gmail.com = user@gmail.com)
    - googlemail.com → gmail.com normalization

    Args:
        email: Raw email address

    Returns:
        Normalized email string
    """
    if not email:
        return ""

    email = email.lower().strip()

    # Handle Gmail variants
    if email.endswith('@gmail.com') or email.endswith('@googlemail.com'):
        local, _ = email.split('@')
        # Remove dots from local part
        local = local.replace('.', '')
        # Remove everything after + (alias)
        local = local.split('+')[0]
        return f"{local}@gmail.com"

    return email


def extract_domain(email: str) -> str:
    """Extract domain from email address.

    Args:
        email: Email address

    Returns:
        Domain portion (lowercase) or empty string
    """
    if not email or '@' not in email:
        return ""
    return email.lower().split('@')[1]


def extract_display_name(email_header: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract display name and email from header format.

    Handles formats like:
    - "John Smith <john@example.com>"
    - "john@example.com"
    - <john@example.com>

    Args:
        email_header: Raw email header value

    Returns:
        Tuple of (display_name, email_address)
    """
    if not email_header:
        return None, None

    # Match "Name <email>" format
    match = re.match(r'^"?([^"<]+)"?\s*<([^>]+)>$', email_header.strip())
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Just email address (possibly in angle brackets)
    email_match = re.match(r'^<?([^<>\s]+@[^<>\s]+)>?$', email_header.strip())
    if email_match:
        return None, email_match.group(1)

    return None, email_header.strip()


# ============================================================
# Known Vendor/Partner Domains
# ============================================================

# Pre-configured domain mappings for common mortgage industry vendors
# Format: domain -> (entity_type, entity_name, confidence)
KNOWN_VENDOR_DOMAINS: Dict[str, Tuple[str, str, float]] = {
    # Government agencies
    'fha.gov': ('vendor', 'FHA', 0.95),
    'va.gov': ('vendor', 'VA', 0.95),
    'hud.gov': ('vendor', 'HUD', 0.95),
    'usda.gov': ('vendor', 'USDA', 0.95),

    # GSEs
    'fanniemae.com': ('vendor', 'Fannie Mae', 0.95),
    'freddiemac.com': ('vendor', 'Freddie Mac', 0.95),

    # Title companies
    'firstam.com': ('vendor', 'First American Title', 0.90),
    'stewart.com': ('vendor', 'Stewart Title', 0.90),
    'oldrepublictitle.com': ('vendor', 'Old Republic Title', 0.90),
    'fidelity.com': ('vendor', 'Fidelity National Title', 0.90),
    'titleone.com': ('vendor', 'TitleOne', 0.90),
    'chicagotitle.com': ('vendor', 'Chicago Title', 0.90),

    # Appraisal management
    'corelogic.com': ('vendor', 'CoreLogic', 0.90),
    'clarocity.com': ('vendor', 'Clarocity', 0.90),

    # Credit bureaus
    'equifax.com': ('vendor', 'Equifax', 0.90),
    'experian.com': ('vendor', 'Experian', 0.90),
    'transunion.com': ('vendor', 'TransUnion', 0.90),

    # Mortgage insurance
    'mgic.com': ('vendor', 'MGIC', 0.90),
    'radian.com': ('vendor', 'Radian', 0.90),
    'genworth.com': ('vendor', 'Genworth', 0.90),
    'archmi.com': ('vendor', 'Arch MI', 0.90),
    'nationalmi.com': ('vendor', 'National MI', 0.90),
    'essent.us': ('vendor', 'Essent', 0.90),
}


class EmailIdentityResolver:
    """Resolve CRM entities for an incoming email.

    This class implements a waterfall matching strategy:
    1. Known client emails (highest confidence, 1.0)
    2. Lead email matches (0.9 confidence)
    3. Loan borrower email matches (0.9 confidence)
    4. Loan number in subject (0.8 confidence)
    5. Contact email matches (0.85 confidence)
    6. Thread/conversation continuity (0.75 confidence)
    7. Domain-based vendor classification (0.7-0.95 confidence)

    Priority is flagged for known client matches to ensure
    rapid routing to the correct loan officer.
    """

    def __init__(self, db: Session):
        self.db = db
        self._custom_domain_cache: Optional[Dict[str, Tuple[str, str, float]]] = None

    def _load_custom_domains(self) -> Dict[str, Tuple[str, str, float]]:
        """Load custom domain mappings from database if available.

        Falls back to built-in KNOWN_VENDOR_DOMAINS if table doesn't exist.
        """
        if self._custom_domain_cache is not None:
            return self._custom_domain_cache

        self._custom_domain_cache = dict(KNOWN_VENDOR_DOMAINS)

        try:
            # Try to load from custom_domain_mappings table if it exists
            result = self.db.execute(
                text("""
                    SELECT domain, entity_type, entity_name, confidence
                    FROM custom_domain_mappings
                    WHERE is_active = true
                """)
            ).fetchall()

            for row in result:
                self._custom_domain_cache[row[0].lower()] = (row[1], row[2], row[3])

            logger.info(f"Loaded {len(result)} custom domain mappings")
        except Exception as e:
            logger.exception(f"Failed to load custom domain mappings (table may not exist): {e}")
            # Must rollback to clear the failed transaction state in PostgreSQL
            self.db.rollback()

        return self._custom_domain_cache

    def resolve(self, email_data: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Resolve best-fit CRM entity for the provided email payload.

        Args:
            email_data: Email metadata including addresses, subject, thread_id
            user_id: The user/loan officer ID to scope matches to

        Returns:
            Dictionary with matched entity IDs, method, confidence, and metadata
        """
        addresses = self._collect_addresses(email_data)
        subject = email_data.get("subject", "") or ""
        body = email_data.get("body_full") or email_data.get("body_preview") or ""
        thread_id = email_data.get("thread_id")

        # Strategy 1: Known client emails (priority)
        match = self._match_known_clients(addresses, user_id)
        if match:
            return match

        # Strategy 2: Lead email matches
        match = self._match_leads(addresses, user_id)
        if match:
            return match

        # Strategy 3: Loan borrower email matches
        match = self._match_loans(addresses, subject, user_id)
        if match:
            return match

        # Strategy 4: Contact email matches
        match = self._match_contacts(addresses, user_id)
        if match:
            return match

        # Strategy 5: Loan number extraction from subject AND body
        match = self._match_by_loan_number(subject, user_id)
        if match:
            return match

        # Strategy 5b: Also check body for loan numbers (lower confidence)
        match = self._match_by_loan_number_in_body(body, user_id)
        if match:
            return match

        # Strategy 5c: Match by borrower name extracted from email (from AI analysis or subject)
        extracted_data = email_data.get("extracted_data") or email_data.get("ai_analysis", {}).get("extracted_data", {})
        if extracted_data:
            first_name = extracted_data.get("borrower_first_name", "")
            last_name = extracted_data.get("borrower_last_name", "")
            if first_name and last_name:
                match = self._match_by_borrower_name(first_name, last_name, user_id)
                if match:
                    return match

        # Strategy 6: Thread/conversation continuity
        if thread_id:
            match = self._match_by_thread(thread_id, user_id)
            if match:
                return match

        # Strategy 7: Domain-based vendor classification
        match = self._match_by_domain(addresses)
        if match:
            return match

        # No match found
        return self._format_match()

    def _collect_addresses(self, email_data: Dict[str, Any]) -> List[str]:
        """Extract and normalize all email addresses from the payload.

        Handles multiple formats:
        - Simple strings: "user@example.com"
        - Microsoft Graph format: {"emailAddress": {"address": "..."}}
        - Arrays of addresses in to/cc fields

        Returns:
            Deduplicated list of normalized lowercase email addresses
        """
        addresses: List[str] = []

        # Handle from_email (can be string or Graph API format)
        for key in ["from_email", "from"]:
            value = email_data.get(key)
            if isinstance(value, dict):
                # Microsoft Graph API format
                email_obj = value.get("emailAddress", {})
                if isinstance(email_obj, dict):
                    addr = email_obj.get("address", "")
                    if addr:
                        addresses.append(addr)
            elif value:
                addresses.append(str(value))

        # Handle to_emails and cc_emails (arrays)
        for key in ["to_emails", "cc_emails", "to", "cc"]:
            raw_values = email_data.get(key, []) or []
            if isinstance(raw_values, list):
                for item in raw_values:
                    if isinstance(item, dict):
                        email_obj = item.get("emailAddress", {})
                        if isinstance(email_obj, dict):
                            addr = email_obj.get("address", "")
                            if addr:
                                addresses.append(addr)
                    elif item:
                        addresses.append(str(item))
            elif raw_values:
                addresses.append(str(raw_values))

        # Normalize and deduplicate
        normalized = []
        seen = set()
        for a in addresses:
            if a and a.strip():
                norm = normalize_email(a)
                if norm not in seen:
                    seen.add(norm)
                    normalized.append(norm)

        return normalized

    def _match_known_clients(
        self, addresses: List[str], user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Match against the known_client_emails lookup table.

        This is the highest confidence match (1.0) because it represents
        emails we've explicitly associated with CRM entities through
        the sync process.
        """
        if not addresses:
            return None

        for email in addresses:
            # Try both normalized and original
            email_variants = [email, normalize_email(email)]

            for variant in email_variants:
                try:
                    result = self.db.execute(
                        text(
                            """
                            SELECT contact_id, loan_id, lead_id, client_name
                            FROM known_client_emails
                            WHERE email_address = :email AND user_id = :user_id
                            LIMIT 1
                            """
                        ),
                        {"email": variant, "user_id": user_id},
                    ).fetchone()

                    if result:
                        return self._format_match(
                            contact_id=result[0],
                            loan_id=result[1],
                            lead_id=result[2],
                            method="known_client_email",
                            confidence=1.0,
                            evidence=email,
                            client_name=result[3],
                            is_priority=True,
                        )
                except Exception as e:
                    logger.error(f"Error matching known client for {email}: {e}")
                    continue

        return None

    def _match_leads(
        self, addresses: List[str], user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Match against active leads by email address.

        Returns 0.9 confidence since leads are actively being worked
        but may not yet be in the known_client_emails table.
        """
        if not addresses:
            return None

        for email in addresses:
            try:
                lead = self.db.execute(
                    text(
                        """
                        SELECT id, name, phone
                        FROM leads
                        WHERE lower(email) = :email
                        AND owner_id = :user_id
                        AND stage NOT IN ('dead', 'closed_lost')
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"email": email.lower(), "user_id": user_id},
                ).fetchone()

                if lead:
                    return self._format_match(
                        lead_id=lead[0],
                        method="lead_email_match",
                        confidence=0.9,
                        evidence=email,
                        client_name=lead[1],
                    )
            except Exception as e:
                logger.error(f"Error matching lead for {email}: {e}")
                continue

        return None

    def _match_loans(
        self, addresses: List[str], subject: str, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Match against active loans by borrower email.

        Returns 0.9 confidence. Also checks co-borrower email if available.
        """
        if not addresses:
            return None

        for email in addresses:
            try:
                loan = self.db.execute(
                    text(
                        """
                        SELECT id, borrower_name, loan_number, loan_amount, property_address
                        FROM loans
                        WHERE (lower(borrower_email) = :email OR lower(coborrower_email) = :email)
                        AND loan_officer_id = :user_id
                        AND stage NOT IN ('CANCELLED', 'WITHDRAWN')
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"email": email.lower(), "user_id": user_id},
                ).fetchone()

                if loan:
                    return self._format_match(
                        loan_id=loan[0],
                        method="loan_email_match",
                        confidence=0.9,
                        evidence=email,
                        client_name=loan[1],
                        loan_number=loan[2],
                    )
            except Exception as e:
                logger.error(f"Error matching loan for {email}: {e}")
                continue

        return None

    def _match_contacts(
        self, addresses: List[str], user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Match against general contacts table.

        Returns 0.85 confidence. Lower than leads/loans because contacts
        might be referral partners, vendors, etc., not direct clients.
        """
        if not addresses:
            return None

        for email in addresses:
            try:
                contact = self.db.execute(
                    text(
                        """
                        SELECT id, first_name, last_name, contact_type
                        FROM contacts
                        WHERE lower(email) = :email
                        AND user_id = :user_id
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"email": email.lower(), "user_id": user_id},
                ).fetchone()

                if contact:
                    full_name = f"{contact[1] or ''} {contact[2] or ''}".strip()
                    return self._format_match(
                        contact_id=contact[0],
                        method="contact_email_match",
                        confidence=0.85,
                        evidence=email,
                        client_name=full_name or "Unknown Contact",
                    )
            except Exception as e:
                logger.error(f"Error matching contact for {email}: {e}")
                continue

        return None

    def _match_by_loan_number(
        self, subject: str, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Extract loan numbers from subject and match.

        Returns 0.8 confidence since we're inferring from subject text
        rather than direct email address matching.

        Patterns matched:
        - "Loan 123456"
        - "Loan #123456"
        - "Loan: 123456"
        - "RE: 123456789" (standalone long numbers)
        - "RCA0000010794" (alphanumeric loan numbers)
        """
        if not subject:
            return None

        loan_numbers = self._extract_loan_numbers(subject)

        for loan_number in loan_numbers:
            try:
                # Try exact match first
                loan = self.db.execute(
                    text(
                        """
                        SELECT id, borrower_name, loan_amount, property_address, loan_number
                        FROM loans
                        WHERE loan_number = :loan_number
                        AND loan_officer_id = :user_id
                        LIMIT 1
                        """
                    ),
                    {"loan_number": loan_number, "user_id": user_id},
                ).fetchone()

                if loan:
                    return self._format_match(
                        loan_id=loan[0],
                        method="loan_number_subject",
                        confidence=0.8,
                        evidence=f"Loan #{loan_number}",
                        client_name=loan[1],
                        loan_number=loan[4],
                    )

                # Try partial/fuzzy match - strip alphanumeric prefix and search
                # For cases like RCA0000010794 -> search for loans containing the numeric part
                numeric_part = re.sub(r'^[A-Z]{2,4}[-]?', '', loan_number)
                if numeric_part and numeric_part != loan_number:
                    loan = self.db.execute(
                        text(
                            """
                            SELECT id, borrower_name, loan_amount, property_address, loan_number
                            FROM loans
                            WHERE (loan_number LIKE :pattern OR loan_number = :numeric)
                            AND loan_officer_id = :user_id
                            LIMIT 1
                            """
                        ),
                        {
                            "pattern": f"%{numeric_part}%",
                            "numeric": numeric_part,
                            "user_id": user_id
                        },
                    ).fetchone()

                    if loan:
                        return self._format_match(
                            loan_id=loan[0],
                            method="loan_number_subject_partial",
                            confidence=0.75,
                            evidence=f"Loan #{loan_number} (matched {loan[4]})",
                            client_name=loan[1],
                            loan_number=loan[4],
                        )

                # Also try searching by loan number containing the extracted number
                loan = self.db.execute(
                    text(
                        """
                        SELECT id, borrower_name, loan_amount, property_address, loan_number
                        FROM loans
                        WHERE loan_number LIKE :pattern
                        AND loan_officer_id = :user_id
                        LIMIT 1
                        """
                    ),
                    {"pattern": f"%{loan_number}%", "user_id": user_id},
                ).fetchone()

                if loan:
                    return self._format_match(
                        loan_id=loan[0],
                        method="loan_number_subject_contains",
                        confidence=0.7,
                        evidence=f"Loan containing {loan_number}",
                        client_name=loan[1],
                        loan_number=loan[4],
                    )

            except Exception as e:
                logger.error(f"Error matching loan number {loan_number}: {e}")
                continue

        return None

    def _match_by_borrower_name(
        self, first_name: str, last_name: str, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Match by borrower name extracted from email content.

        Returns 0.7 confidence since name matching can have false positives.
        """
        if not first_name or not last_name:
            return None

        try:
            # Try exact match on borrower_name field
            full_name = f"{first_name} {last_name}"
            loan = self.db.execute(
                text(
                    """
                    SELECT id, borrower_name, loan_number, loan_amount, property_address
                    FROM loans
                    WHERE (
                        lower(borrower_name) = :full_name
                        OR lower(borrower_name) LIKE :name_pattern
                    )
                    AND loan_officer_id = :user_id
                    AND stage NOT IN ('CANCELLED', 'WITHDRAWN')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "full_name": full_name.lower(),
                    "name_pattern": f"%{first_name.lower()}%{last_name.lower()}%",
                    "user_id": user_id
                },
            ).fetchone()

            if loan:
                return self._format_match(
                    loan_id=loan[0],
                    method="borrower_name_match",
                    confidence=0.7,
                    evidence=f"Borrower: {full_name}",
                    client_name=loan[1],
                    loan_number=loan[2],
                )

            # Also check leads
            lead = self.db.execute(
                text(
                    """
                    SELECT id, name, email
                    FROM leads
                    WHERE (
                        lower(name) = :full_name
                        OR lower(name) LIKE :name_pattern
                    )
                    AND stage NOT IN ('dead', 'closed_lost')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "full_name": full_name.lower(),
                    "name_pattern": f"%{first_name.lower()}%{last_name.lower()}%",
                },
            ).fetchone()

            if lead:
                return self._format_match(
                    lead_id=lead[0],
                    method="borrower_name_lead_match",
                    confidence=0.65,
                    evidence=f"Lead: {full_name}",
                    client_name=lead[1],
                )

        except Exception as e:
            logger.error(f"Error matching borrower name {first_name} {last_name}: {e}")

        return None

    def _match_by_thread(
        self, thread_id: str, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Match by looking up previous emails in the same thread.

        Returns 0.75 confidence since we're assuming thread continuity,
        but the original match might have been incorrect.
        """
        if not thread_id:
            return None

        try:
            # Find the most recent email in this thread that has a match
            previous = self.db.execute(
                text(
                    """
                    SELECT matched_contact_id, matched_loan_id, matched_lead_id,
                           match_client_name, match_loan_number
                    FROM email_reconciliation_queue
                    WHERE thread_id = :thread_id
                    AND user_id = :user_id
                    AND (matched_contact_id IS NOT NULL
                         OR matched_loan_id IS NOT NULL
                         OR matched_lead_id IS NOT NULL)
                    ORDER BY received_date DESC
                    LIMIT 1
                    """
                ),
                {"thread_id": thread_id, "user_id": user_id},
            ).fetchone()

            if previous:
                return self._format_match(
                    contact_id=previous[0],
                    loan_id=previous[1],
                    lead_id=previous[2],
                    method="thread_continuity",
                    confidence=0.75,
                    evidence=f"Thread {thread_id[:8]}...",
                    client_name=previous[3],
                    loan_number=previous[4],
                )
        except Exception as e:
            logger.error(f"Error matching by thread {thread_id}: {e}")

        return None

    def _match_by_domain(
        self, addresses: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Match by email domain against known vendors/partners.

        This is a fallback strategy for when we can't match to a specific
        client but can classify the sender as a known vendor type.

        Returns 0.7-0.95 confidence depending on the domain.
        """
        domains = self._load_custom_domains()

        for email in addresses:
            domain = extract_domain(email)
            if not domain:
                continue

            # Check exact domain match
            if domain in domains:
                entity_type, entity_name, confidence = domains[domain]
                return self._format_match(
                    method="domain_vendor_match",
                    confidence=confidence,
                    evidence=f"Domain: {domain}",
                    client_name=entity_name,
                    vendor_type=entity_type,
                )

            # Check parent domain for subdomains (e.g., noreply.fanniemae.com)
            parts = domain.split('.')
            if len(parts) > 2:
                parent = '.'.join(parts[-2:])
                if parent in domains:
                    entity_type, entity_name, confidence = domains[parent]
                    return self._format_match(
                        method="domain_vendor_match",
                        confidence=confidence * 0.95,  # Slightly lower for subdomain
                        evidence=f"Domain: {domain} (parent: {parent})",
                        client_name=entity_name,
                        vendor_type=entity_type,
                    )

        return None

    def _match_by_loan_number_in_body(
        self, body: str, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Extract loan numbers from body and match.

        Returns 0.75 confidence since body extraction is less reliable than subject.
        """
        if not body:
            return None

        loan_numbers = self._extract_loan_numbers(body)

        for loan_number in loan_numbers:
            try:
                loan = self.db.execute(
                    text(
                        """
                        SELECT id, borrower_name, loan_amount, property_address
                        FROM loans
                        WHERE loan_number = :loan_number
                        AND loan_officer_id = :user_id
                        LIMIT 1
                        """
                    ),
                    {"loan_number": loan_number, "user_id": user_id},
                ).fetchone()

                if loan:
                    return self._format_match(
                        loan_id=loan[0],
                        method="loan_number_body",
                        confidence=0.75,
                        evidence=f"Loan #{loan_number} (found in body)",
                        client_name=loan[1],
                        loan_number=loan_number,
                    )
            except Exception as e:
                logger.error(f"Error matching loan number from body {loan_number}: {e}")
                continue

        return None

    def _extract_loan_numbers(self, text_value: str) -> List[str]:
        """Extract potential loan numbers from text.

        Looks for:
        - "loan" followed by 4+ digits
        - Standalone 6+ digit numbers
        - Alphanumeric loan numbers like RCA00000011704

        Returns:
            List of extracted loan number strings
        """
        if not text_value:
            return []

        matches: Set[str] = set()

        # Pattern 1: "loan" prefix with number
        pattern1 = r"loan[-\s#:]?\s*(\d{4,})"
        found1 = re.findall(pattern1, text_value, flags=re.IGNORECASE)
        for match in found1:
            cleaned = re.sub(r"[^0-9]", "", match)
            if cleaned and len(cleaned) >= 4:
                matches.add(cleaned)

        # Pattern 2: Standalone long numbers (likely loan numbers)
        pattern2 = r"\b(\d{6,})\b"
        found2 = re.findall(pattern2, text_value, flags=re.IGNORECASE)
        for match in found2:
            cleaned = re.sub(r"[^0-9]", "", match)
            if cleaned and len(cleaned) >= 4:
                matches.add(cleaned)

        # Pattern 3: Alphanumeric loan numbers like RCA00000011704 or CMG-0157427
        # Common patterns: RCA + digits, CMG- + digits, letters + long number
        pattern3 = r"\b([A-Z]{2,4}[-]?\d{6,})\b"
        found3 = re.findall(pattern3, text_value, flags=re.IGNORECASE)
        for match in found3:
            matches.add(match.upper())

        # Pattern 4: Look for loan numbers in URLs (upload?LN=RCA00000011704)
        pattern4 = r"LN=([A-Z0-9-]+)"
        found4 = re.findall(pattern4, text_value, flags=re.IGNORECASE)
        for match in found4:
            matches.add(match.upper())

        return sorted(list(matches), key=len, reverse=True)  # Longest first

    def _format_match(
        self,
        *,
        contact_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        lead_id: Optional[int] = None,
        method: Optional[str] = None,
        confidence: Optional[float] = None,
        evidence: Optional[str] = None,
        client_name: Optional[str] = None,
        loan_number: Optional[str] = None,
        is_priority: bool = False,
        vendor_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Format a match result into a standard dictionary.

        This ensures consistent structure across all matching methods.
        """
        return {
            "matched_contact_id": contact_id,
            "matched_loan_id": loan_id,
            "matched_lead_id": lead_id,
            "match_method": method,
            "match_confidence": confidence,
            "match_evidence": evidence,
            "match_client_name": client_name,
            "match_loan_number": loan_number,
            "is_priority": is_priority,
            "vendor_type": vendor_type,
        }

    def batch_resolve(
        self, email_batch: List[Dict[str, Any]], user_id: int
    ) -> List[Dict[str, Any]]:
        """Resolve multiple emails in a single batch.

        This is more efficient than calling resolve() individually
        when processing large email imports.

        Args:
            email_batch: List of email data dictionaries
            user_id: User ID to scope matches to

        Returns:
            List of match results in the same order as input
        """
        results = []

        for email_data in email_batch:
            try:
                match = self.resolve(email_data, user_id)
                results.append(match)
            except Exception as e:
                logger.error(f"Batch resolve error: {e}")
                # Return empty match on error
                results.append(self._format_match())

        return results

    def populate_known_clients(self, user_id: int) -> Dict[str, int]:
        """Populate known_client_emails table from existing CRM data.

        This is a maintenance utility to ensure the known_client_emails
        lookup table stays in sync with the main CRM tables.

        Args:
            user_id: User ID to populate for

        Returns:
            Dictionary with counts of records added/updated
        """
        counts = {"leads": 0, "loans": 0, "contacts": 0}

        try:
            # Add from leads
            self.db.execute(
                text("""
                    INSERT INTO known_client_emails (email_address, user_id, lead_id, client_name, created_at)
                    SELECT LOWER(TRIM(email)), owner_id, id, name, NOW()
                    FROM leads
                    WHERE email IS NOT NULL
                    AND email != ''
                    AND owner_id = :user_id
                    AND stage NOT IN ('dead', 'closed_lost')
                    ON CONFLICT (email_address, user_id)
                    DO UPDATE SET lead_id = EXCLUDED.lead_id, client_name = EXCLUDED.client_name
                """),
                {"user_id": user_id}
            )
            counts["leads"] = self.db.execute(text("SELECT changes()")).scalar() or 0

            # Add from loans
            self.db.execute(
                text("""
                    INSERT INTO known_client_emails (email_address, user_id, loan_id, client_name, created_at)
                    SELECT LOWER(TRIM(borrower_email)), loan_officer_id, id, borrower_name, NOW()
                    FROM loans
                    WHERE borrower_email IS NOT NULL
                    AND borrower_email != ''
                    AND loan_officer_id = :user_id
                    AND stage NOT IN ('CANCELLED', 'WITHDRAWN')
                    ON CONFLICT (email_address, user_id)
                    DO UPDATE SET loan_id = EXCLUDED.loan_id, client_name = EXCLUDED.client_name
                """),
                {"user_id": user_id}
            )
            counts["loans"] = self.db.execute(text("SELECT changes()")).scalar() or 0

            # Add from contacts
            self.db.execute(
                text("""
                    INSERT INTO known_client_emails (email_address, user_id, contact_id, client_name, created_at)
                    SELECT LOWER(TRIM(email)), user_id, id,
                           COALESCE(first_name || ' ' || last_name, first_name, last_name, 'Unknown'),
                           NOW()
                    FROM contacts
                    WHERE email IS NOT NULL
                    AND email != ''
                    AND user_id = :user_id
                    ON CONFLICT (email_address, user_id)
                    DO UPDATE SET contact_id = EXCLUDED.contact_id, client_name = EXCLUDED.client_name
                """),
                {"user_id": user_id}
            )
            counts["contacts"] = self.db.execute(text("SELECT changes()")).scalar() or 0

            self.db.commit()
            logger.info(f"Populated known_client_emails for user {user_id}: {counts}")

        except SQLAlchemyError as e:
            logger.error(f"Error populating known_client_emails: {e}")
            self.db.rollback()

        return counts

    def get_resolution_stats(self, user_id: int) -> Dict[str, Any]:
        """Get statistics about email resolution for a user.

        Args:
            user_id: User ID to get stats for

        Returns:
            Dictionary with resolution statistics
        """
        try:
            # Total emails in queue
            total = self.db.execute(
                text("""
                    SELECT COUNT(*) FROM email_reconciliation_queue
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id}
            ).scalar() or 0

            # Resolved (have a match)
            resolved = self.db.execute(
                text("""
                    SELECT COUNT(*) FROM email_reconciliation_queue
                    WHERE user_id = :user_id
                    AND (matched_contact_id IS NOT NULL
                         OR matched_loan_id IS NOT NULL
                         OR matched_lead_id IS NOT NULL)
                """),
                {"user_id": user_id}
            ).scalar() or 0

            # By method
            by_method = self.db.execute(
                text("""
                    SELECT match_method, COUNT(*) as count
                    FROM email_reconciliation_queue
                    WHERE user_id = :user_id AND match_method IS NOT NULL
                    GROUP BY match_method
                    ORDER BY count DESC
                """),
                {"user_id": user_id}
            ).fetchall()

            # Known client count
            known_clients = self.db.execute(
                text("""
                    SELECT COUNT(*) FROM known_client_emails
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id}
            ).scalar() or 0

            return {
                "total_emails": total,
                "resolved": resolved,
                "unresolved": total - resolved,
                "resolution_rate": round(resolved / total * 100, 1) if total > 0 else 0,
                "by_method": {row[0]: row[1] for row in by_method},
                "known_clients_count": known_clients,
            }

        except Exception as e:
            logger.error(f"Error getting resolution stats: {e}")
            return {
                "total_emails": 0,
                "resolved": 0,
                "unresolved": 0,
                "resolution_rate": 0,
                "by_method": {},
                "known_clients_count": 0,
                "error": "Internal server error",
            }


# ============================================================
# Factory function
# ============================================================

def get_email_identity_resolver(db: Session) -> EmailIdentityResolver:
    """Get an EmailIdentityResolver instance.

    Args:
        db: SQLAlchemy database session

    Returns:
        EmailIdentityResolver instance
    """
    return EmailIdentityResolver(db)
