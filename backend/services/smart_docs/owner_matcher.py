"""
Owner Matcher Service

Fuzzy name matching to determine document owner (borrower vs co-borrower).
Uses multiple matching strategies to handle name variations.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import fuzzy matching library
try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:
    try:
        from fuzzywuzzy import fuzz, process
        HAS_RAPIDFUZZ = True  # Same API
    except ImportError:
        HAS_RAPIDFUZZ = False


@dataclass
class OwnerMatchResult:
    """Result of owner matching."""
    owner: str  # "BORROWER", "CO_BORROWER", or "UNKNOWN"
    confidence: int  # 0-100
    matched_name: Optional[str] = None
    borrower_score: int = 0
    co_borrower_score: int = 0
    match_details: Optional[dict] = None


class OwnerMatcher:
    """
    Service for matching extracted names to borrower/co-borrower.

    Uses fuzzy string matching with multiple strategies:
    - Full name matching
    - First + Last name matching
    - Last name only matching (lower confidence)
    - First name only matching (lowest confidence)
    """

    # Minimum scores for different match types
    FULL_MATCH_THRESHOLD = 85
    PARTIAL_MATCH_THRESHOLD = 70
    NAME_ONLY_THRESHOLD = 90

    def match_owner(
        self,
        extracted_names: List[str],
        borrower_name: Optional[str] = None,
        co_borrower_name: Optional[str] = None,
    ) -> OwnerMatchResult:
        """
        Match extracted names to borrower or co-borrower.

        Args:
            extracted_names: List of names found in the document
            borrower_name: Primary borrower's name
            co_borrower_name: Co-borrower's name (optional)

        Returns:
            OwnerMatchResult with owner determination and confidence
        """
        if not extracted_names or (not borrower_name and not co_borrower_name):
            return OwnerMatchResult(owner="UNKNOWN", confidence=0)

        best_borrower_match = self._find_best_match(extracted_names, borrower_name)
        best_co_borrower_match = self._find_best_match(extracted_names, co_borrower_name)

        borrower_score = best_borrower_match[0] if best_borrower_match else 0
        co_borrower_score = best_co_borrower_match[0] if best_co_borrower_match else 0

        # Determine owner based on scores
        if borrower_score >= self.FULL_MATCH_THRESHOLD and borrower_score > co_borrower_score:
            return OwnerMatchResult(
                owner="BORROWER",
                confidence=borrower_score,
                matched_name=best_borrower_match[1] if best_borrower_match else None,
                borrower_score=borrower_score,
                co_borrower_score=co_borrower_score,
                match_details={"match_type": "full_name", "strategy": best_borrower_match[2] if best_borrower_match else None}
            )
        elif co_borrower_score >= self.FULL_MATCH_THRESHOLD and co_borrower_score > borrower_score:
            return OwnerMatchResult(
                owner="CO_BORROWER",
                confidence=co_borrower_score,
                matched_name=best_co_borrower_match[1] if best_co_borrower_match else None,
                borrower_score=borrower_score,
                co_borrower_score=co_borrower_score,
                match_details={"match_type": "full_name", "strategy": best_co_borrower_match[2] if best_co_borrower_match else None}
            )
        elif borrower_score >= self.PARTIAL_MATCH_THRESHOLD and borrower_score > co_borrower_score:
            return OwnerMatchResult(
                owner="BORROWER",
                confidence=borrower_score - 10,  # Reduce confidence for partial match
                matched_name=best_borrower_match[1] if best_borrower_match else None,
                borrower_score=borrower_score,
                co_borrower_score=co_borrower_score,
                match_details={"match_type": "partial", "strategy": best_borrower_match[2] if best_borrower_match else None}
            )
        elif co_borrower_score >= self.PARTIAL_MATCH_THRESHOLD:
            return OwnerMatchResult(
                owner="CO_BORROWER",
                confidence=co_borrower_score - 10,
                matched_name=best_co_borrower_match[1] if best_co_borrower_match else None,
                borrower_score=borrower_score,
                co_borrower_score=co_borrower_score,
                match_details={"match_type": "partial", "strategy": best_co_borrower_match[2] if best_co_borrower_match else None}
            )
        else:
            return OwnerMatchResult(
                owner="UNKNOWN",
                confidence=max(borrower_score, co_borrower_score),
                borrower_score=borrower_score,
                co_borrower_score=co_borrower_score,
                match_details={"reason": "no_match_above_threshold"}
            )

    def _find_best_match(
        self,
        extracted_names: List[str],
        target_name: Optional[str]
    ) -> Optional[Tuple[int, str, str]]:
        """
        Find the best matching name from extracted names.

        Returns:
            Tuple of (score, matched_name, strategy) or None
        """
        if not target_name or not extracted_names:
            return None

        target_normalized = self._normalize_name(target_name)
        target_parts = self._split_name(target_name)

        best_score = 0
        best_match = None
        best_strategy = None

        for extracted in extracted_names:
            if not extracted:
                continue

            extracted_normalized = self._normalize_name(extracted)
            extracted_parts = self._split_name(extracted)

            # Strategy 1: Full name match
            score = self._fuzzy_ratio(extracted_normalized, target_normalized)
            if score > best_score:
                best_score = score
                best_match = extracted
                best_strategy = "full_name"

            # Strategy 2: Token set ratio (handles word order differences)
            score = self._token_set_ratio(extracted_normalized, target_normalized)
            if score > best_score:
                best_score = score
                best_match = extracted
                best_strategy = "token_set"

            # Strategy 3: First + Last name match
            if len(target_parts) >= 2 and len(extracted_parts) >= 2:
                # Compare first and last names
                first_score = self._fuzzy_ratio(extracted_parts[0], target_parts[0])
                last_score = self._fuzzy_ratio(extracted_parts[-1], target_parts[-1])
                combined_score = (first_score + last_score) // 2

                if combined_score > best_score:
                    best_score = combined_score
                    best_match = extracted
                    best_strategy = "first_last"

            # Strategy 4: Last name only (lower weight)
            if len(target_parts) >= 1 and len(extracted_parts) >= 1:
                last_score = self._fuzzy_ratio(extracted_parts[-1], target_parts[-1])
                # Apply penalty for last name only match
                adjusted_score = int(last_score * 0.7)  # 70% weight for last name only

                if adjusted_score > best_score and last_score >= self.NAME_ONLY_THRESHOLD:
                    best_score = adjusted_score
                    best_match = extracted
                    best_strategy = "last_name_only"

        if best_score > 0:
            return (best_score, best_match, best_strategy)
        return None

    def _normalize_name(self, name: str) -> str:
        """Normalize a name for comparison."""
        if not name:
            return ""

        # Convert to lowercase
        name = name.lower().strip()

        # Remove common titles
        titles = ["mr", "mrs", "ms", "dr", "jr", "sr", "ii", "iii", "iv"]
        words = name.split()
        words = [w for w in words if w.replace(".", "") not in titles]

        # Remove punctuation
        name = " ".join(words)
        name = re.sub(r"[^\w\s]", "", name)

        # Collapse multiple spaces
        name = re.sub(r"\s+", " ", name).strip()

        return name

    def _split_name(self, name: str) -> List[str]:
        """Split a name into parts."""
        if not name:
            return []

        normalized = self._normalize_name(name)
        return normalized.split()

    def _fuzzy_ratio(self, s1: str, s2: str) -> int:
        """Calculate fuzzy match ratio between two strings."""
        if not s1 or not s2:
            return 0

        if HAS_RAPIDFUZZ:
            return int(fuzz.ratio(s1, s2))
        else:
            # Simple fallback without fuzzy library
            return self._simple_ratio(s1, s2)

    def _token_set_ratio(self, s1: str, s2: str) -> int:
        """Calculate token set ratio (handles word order differences)."""
        if not s1 or not s2:
            return 0

        if HAS_RAPIDFUZZ:
            return int(fuzz.token_set_ratio(s1, s2))
        else:
            # Fallback: compare sorted tokens
            tokens1 = sorted(s1.split())
            tokens2 = sorted(s2.split())
            return self._simple_ratio(" ".join(tokens1), " ".join(tokens2))

    def _simple_ratio(self, s1: str, s2: str) -> int:
        """Simple string similarity without fuzzy library."""
        if not s1 or not s2:
            return 0

        # Exact match
        if s1 == s2:
            return 100

        # Check if one contains the other
        if s1 in s2 or s2 in s1:
            shorter = min(len(s1), len(s2))
            longer = max(len(s1), len(s2))
            return int((shorter / longer) * 100)

        # Count matching characters
        matches = sum(1 for c in s1 if c in s2)
        total = (len(s1) + len(s2)) / 2
        return int((matches / total) * 100) if total > 0 else 0


# Singleton instance
_matcher_instance = None


def get_owner_matcher() -> OwnerMatcher:
    """Get the singleton matcher instance."""
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = OwnerMatcher()
    return _matcher_instance
