"""
Blog Compliance and Similarity Service - Ensure content meets guidelines and is original.

Handles:
- Compliance checking (banned phrases, required disclosures)
- Similarity detection against source material
- Uniqueness scoring
- Content validation before publishing
"""

import os
import re
import logging
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class ComplianceIssue:
    """Represents a compliance issue found in content."""
    issue_type: str  # banned_phrase, missing_disclosure, length_violation, etc.
    severity: str  # error, warning, info
    message: str
    location: Optional[str] = None  # Where in the content
    suggestion: Optional[str] = None


@dataclass
class ComplianceResult:
    """Result from compliance checking."""
    is_compliant: bool
    issues: List[ComplianceIssue] = field(default_factory=list)
    warnings: List[ComplianceIssue] = field(default_factory=list)
    applied_disclosures: List[str] = field(default_factory=list)
    score: float = 100.0  # Compliance score 0-100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_compliant": self.is_compliant,
            "issues": [
                {"type": i.issue_type, "severity": i.severity, "message": i.message, "suggestion": i.suggestion}
                for i in self.issues
            ],
            "warnings": [
                {"type": w.issue_type, "severity": w.severity, "message": w.message, "suggestion": w.suggestion}
                for w in self.warnings
            ],
            "applied_disclosures": self.applied_disclosures,
            "score": self.score,
        }


@dataclass
class SimilarityResult:
    """Result from similarity checking."""
    is_unique: bool
    uniqueness_score: float  # 0-1, higher is more unique
    max_similarity: float  # Highest similarity found
    similar_passages: List[Dict[str, Any]] = field(default_factory=list)
    source_attributions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_unique": self.is_unique,
            "uniqueness_score": self.uniqueness_score,
            "max_similarity": self.max_similarity,
            "similar_passages": self.similar_passages[:5],  # Limit for response size
            "source_attributions": self.source_attributions,
        }


class BlogComplianceService:
    """Service for content compliance and validation."""

    # Default banned phrases for mortgage industry
    DEFAULT_BANNED_PHRASES = [
        "guaranteed approval",
        "no credit check",
        "100% approval",
        "instant approval guaranteed",
        "bad credit no problem",
        "we approve everyone",
        "no income verification needed",
        "stated income",
        "ninja loan",
        "liar loan",
    ]

    # Default required disclosures
    DEFAULT_DISCLOSURES = [
        "NMLS# [YOUR_NMLS_NUMBER]",
        "Equal Housing Lender",
    ]

    # Common compliance patterns
    RATE_CLAIM_PATTERN = re.compile(
        r'(?:lowest|best|guaranteed)\s+(?:rate|rates|interest)',
        re.IGNORECASE
    )

    PROMISE_PATTERN = re.compile(
        r'\b(?:guarantee|promise|ensure|certain)\s+(?:approval|closing|funding)',
        re.IGNORECASE
    )

    def __init__(self):
        logger.info("Blog compliance service initialized")

    def check_compliance(
        self,
        content: str,
        compliance_profile: Dict[str, Any] = None,
        content_type: str = "blog",
    ) -> ComplianceResult:
        """
        Check content for compliance issues.

        Args:
            content: The content to check
            compliance_profile: Custom compliance settings
            content_type: Type of content (blog, social, email)

        Returns:
            ComplianceResult with findings
        """
        issues = []
        warnings = []

        # Get compliance settings
        profile = compliance_profile or {}
        banned_phrases = profile.get("banned_phrases_json", self.DEFAULT_BANNED_PHRASES)
        required_disclosures = profile.get("required_disclosures_json", self.DEFAULT_DISCLOSURES)
        overrides = profile.get("overrides_json", {})

        content_lower = content.lower()

        # Check for banned phrases
        for phrase in banned_phrases:
            if phrase.lower() in content_lower:
                issues.append(ComplianceIssue(
                    issue_type="banned_phrase",
                    severity="error",
                    message=f"Content contains banned phrase: '{phrase}'",
                    location=self._find_phrase_location(content, phrase),
                    suggestion=f"Remove or rephrase the banned phrase '{phrase}'",
                ))

        # Check for rate claims without disclaimers
        if self.RATE_CLAIM_PATTERN.search(content):
            has_rate_disclaimer = any(
                disclaimer in content_lower
                for disclaimer in ["rates subject to change", "rate not guaranteed", "actual rate may vary"]
            )
            if not has_rate_disclaimer:
                warnings.append(ComplianceIssue(
                    issue_type="rate_claim",
                    severity="warning",
                    message="Rate claim detected without disclaimer",
                    suggestion="Add 'Rates subject to change' or similar disclaimer",
                ))

        # Check for promise patterns
        promise_match = self.PROMISE_PATTERN.search(content)
        if promise_match:
            issues.append(ComplianceIssue(
                issue_type="guarantee_promise",
                severity="error",
                message=f"Potentially misleading guarantee: '{promise_match.group()}'",
                location=promise_match.group(),
                suggestion="Avoid guaranteeing outcomes that depend on underwriting",
            ))

        # Check for required disclosures (for blog content)
        applied_disclosures = []
        if content_type in ["blog", "email"] and not overrides.get("skip_disclosures"):
            for disclosure in required_disclosures:
                # Check if disclosure is present (fuzzy match)
                disclosure_base = disclosure.replace("[YOUR_NMLS_NUMBER]", "").strip()
                if disclosure_base.lower() in content_lower:
                    applied_disclosures.append(disclosure)
                else:
                    warnings.append(ComplianceIssue(
                        issue_type="missing_disclosure",
                        severity="warning",
                        message=f"Required disclosure not found: '{disclosure}'",
                        suggestion=f"Add '{disclosure}' to the content footer",
                    ))

        # Content length checks
        word_count = len(content.split())
        if content_type == "blog" and word_count < 300:
            warnings.append(ComplianceIssue(
                issue_type="length_violation",
                severity="info",
                message=f"Blog post is short ({word_count} words, recommended 600+)",
                suggestion="Consider expanding the content for better SEO",
            ))

        # Calculate compliance score
        error_count = len(issues)
        warning_count = len(warnings)
        score = max(0, 100 - (error_count * 25) - (warning_count * 5))

        return ComplianceResult(
            is_compliant=len(issues) == 0,
            issues=issues,
            warnings=warnings,
            applied_disclosures=applied_disclosures,
            score=score,
        )

    def _find_phrase_location(self, content: str, phrase: str) -> Optional[str]:
        """Find the context around a phrase in content."""
        idx = content.lower().find(phrase.lower())
        if idx == -1:
            return None
        start = max(0, idx - 30)
        end = min(len(content), idx + len(phrase) + 30)
        return f"...{content[start:end]}..."

    def add_disclosures(
        self,
        content: str,
        disclosures: List[str],
        format_type: str = "footer",
    ) -> str:
        """
        Add required disclosures to content.

        Args:
            content: The content to modify
            disclosures: List of disclosure strings
            format_type: How to format (footer, inline, banner)

        Returns:
            Content with disclosures added
        """
        if not disclosures:
            return content

        if format_type == "footer":
            disclosure_text = "\n\n---\n\n" + " | ".join(disclosures)
            return content + disclosure_text
        elif format_type == "inline":
            disclosure_text = "\n\n*" + " • ".join(disclosures) + "*"
            return content + disclosure_text
        else:
            return content

    def sanitize_content(
        self,
        content: str,
        banned_phrases: List[str] = None,
        replacement: str = "[REMOVED]",
    ) -> Tuple[str, List[str]]:
        """
        Remove or replace banned phrases in content.

        Args:
            content: Content to sanitize
            banned_phrases: Phrases to remove
            replacement: What to replace with

        Returns:
            Tuple of (sanitized_content, list_of_removed_phrases)
        """
        banned = banned_phrases or self.DEFAULT_BANNED_PHRASES
        removed = []
        sanitized = content

        for phrase in banned:
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            if pattern.search(sanitized):
                removed.append(phrase)
                sanitized = pattern.sub(replacement, sanitized)

        return sanitized, removed


class BlogSimilarityService:
    """Service for content similarity and uniqueness checking."""

    # Minimum similarity threshold to flag
    SIMILARITY_THRESHOLD = 0.7

    # Minimum passage length to check
    MIN_PASSAGE_LENGTH = 50

    def __init__(self):
        logger.info("Blog similarity service initialized")

    def check_similarity(
        self,
        generated_content: str,
        source_content: str,
        threshold: float = None,
    ) -> SimilarityResult:
        """
        Check generated content for similarity to source material.

        Args:
            generated_content: The AI-generated content
            source_content: Original source material
            threshold: Custom similarity threshold (0-1)

        Returns:
            SimilarityResult with findings
        """
        threshold = threshold or self.SIMILARITY_THRESHOLD
        similar_passages = []
        source_attributions = []

        # Split content into paragraphs/passages
        gen_passages = self._split_into_passages(generated_content)
        src_passages = self._split_into_passages(source_content)

        max_similarity = 0.0
        total_similarity = 0.0
        checked_count = 0

        for gen_p in gen_passages:
            if len(gen_p) < self.MIN_PASSAGE_LENGTH:
                continue

            best_match = 0.0
            best_source = ""

            for src_p in src_passages:
                if len(src_p) < self.MIN_PASSAGE_LENGTH:
                    continue

                similarity = self._calculate_similarity(gen_p, src_p)

                if similarity > best_match:
                    best_match = similarity
                    best_source = src_p

            if best_match >= threshold:
                similar_passages.append({
                    "generated": gen_p[:200],
                    "source": best_source[:200],
                    "similarity": round(best_match, 3),
                })

            if best_match > max_similarity:
                max_similarity = best_match

            total_similarity += best_match
            checked_count += 1

        # Calculate overall uniqueness
        avg_similarity = total_similarity / max(checked_count, 1)
        uniqueness_score = 1.0 - avg_similarity

        # Determine if content is sufficiently unique
        is_unique = max_similarity < threshold and uniqueness_score >= 0.6

        return SimilarityResult(
            is_unique=is_unique,
            uniqueness_score=round(uniqueness_score, 3),
            max_similarity=round(max_similarity, 3),
            similar_passages=similar_passages,
            source_attributions=source_attributions,
        )

    def check_against_corpus(
        self,
        content: str,
        corpus: List[Dict[str, str]],
        threshold: float = None,
    ) -> SimilarityResult:
        """
        Check content against a corpus of existing content.

        Args:
            content: Content to check
            corpus: List of {"id": "...", "content": "..."} dicts
            threshold: Similarity threshold

        Returns:
            SimilarityResult with findings
        """
        threshold = threshold or self.SIMILARITY_THRESHOLD
        all_passages = []
        max_similarity = 0.0

        content_passages = self._split_into_passages(content)

        for doc in corpus:
            doc_content = doc.get("content", "")
            doc_id = doc.get("id", "unknown")

            result = self.check_similarity(content, doc_content, threshold)

            if result.max_similarity > max_similarity:
                max_similarity = result.max_similarity

            for passage in result.similar_passages:
                passage["source_id"] = doc_id
                all_passages.append(passage)

        # Sort by similarity
        all_passages.sort(key=lambda x: x["similarity"], reverse=True)

        return SimilarityResult(
            is_unique=max_similarity < threshold,
            uniqueness_score=1.0 - max_similarity,
            max_similarity=max_similarity,
            similar_passages=all_passages[:10],
        )

    def _split_into_passages(self, text: str) -> List[str]:
        """Split text into passages for comparison."""
        # Split by paragraphs
        paragraphs = text.split('\n\n')
        passages = []

        for para in paragraphs:
            para = para.strip()
            if para:
                # Also split long paragraphs by sentences
                if len(para) > 500:
                    sentences = re.split(r'(?<=[.!?])\s+', para)
                    for sent in sentences:
                        if len(sent) >= self.MIN_PASSAGE_LENGTH:
                            passages.append(sent)
                else:
                    passages.append(para)

        return passages

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two text passages.

        Uses a combination of:
        - Sequence matching (for exact phrase detection)
        - Word overlap (Jaccard similarity)
        """
        # Normalize texts
        t1 = text1.lower().strip()
        t2 = text2.lower().strip()

        # Sequence matching for phrase similarity
        seq_ratio = SequenceMatcher(None, t1, t2).ratio()

        # Word-level Jaccard similarity
        words1 = set(re.findall(r'\b\w+\b', t1))
        words2 = set(re.findall(r'\b\w+\b', t2))

        if not words1 or not words2:
            return seq_ratio

        intersection = len(words1 & words2)
        union = len(words1 | words2)
        jaccard = intersection / union if union > 0 else 0

        # Weighted combination
        return (seq_ratio * 0.6) + (jaccard * 0.4)

    def get_content_fingerprint(self, content: str) -> str:
        """
        Generate a fingerprint for content deduplication.

        Args:
            content: Content to fingerprint

        Returns:
            Hash string for the content
        """
        # Normalize content
        normalized = content.lower()
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = re.sub(r'[^\w\s]', '', normalized)

        # Use first 1000 chars for fingerprint
        sample = normalized[:1000]

        return hashlib.sha256(sample.encode()).hexdigest()[:16]

    def find_duplicate_content(
        self,
        content: str,
        existing_fingerprints: Dict[str, str],
    ) -> Optional[str]:
        """
        Check if content is a duplicate of existing content.

        Args:
            content: Content to check
            existing_fingerprints: Dict of content_id -> fingerprint

        Returns:
            ID of duplicate content if found, None otherwise
        """
        new_fingerprint = self.get_content_fingerprint(content)

        for content_id, fingerprint in existing_fingerprints.items():
            if fingerprint == new_fingerprint:
                return content_id

        return None


# Create singleton instances
blog_compliance_service = BlogComplianceService()
blog_similarity_service = BlogSimilarityService()
