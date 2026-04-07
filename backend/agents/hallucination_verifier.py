"""
Hallucination Verifier Service

Extracts claims from AI responses and verifies them against source data
to detect hallucinations and measure faithfulness.

Architecture:
1. Claim Extraction: Uses LLM to extract discrete factual claims from responses
2. Source Matching: Maps claims to relevant tool outputs/source data
3. Verification: Compares claimed values against source data
4. Scoring: Calculates faithfulness score and hallucination rate
"""

import os
import re
import json
import logging
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import httpx
from anthropic import Anthropic

from .anthropic_client import get_anthropic_client

from .metrics.models import (
    ClaimType,
    VerificationStatus,
    ExtractedClaim,
    ClaimVerificationResult,
    HallucinationReport,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CLAIM EXTRACTION PROMPTS
# =============================================================================

CLAIM_EXTRACTION_PROMPT = """You are a claim extraction system. Extract all factual claims from the given AI response.

For each claim, identify:
1. The exact claim text
2. The type of claim (numeric, temporal, entity, status, comparison, aggregation, factual)
3. The specific value being claimed (if applicable)
4. Any entity references (loan IDs, borrower names, etc.)

Focus on VERIFIABLE claims:
- Numbers, counts, percentages, amounts
- Dates, times, durations
- Names, IDs, statuses
- Comparisons between values
- Aggregations (totals, averages)

IGNORE:
- Opinions or subjective statements
- General advice or recommendations
- Hypothetical scenarios
- Questions

Respond in JSON format:
{
    "claims": [
        {
            "claim_text": "The exact claim from the response",
            "claim_type": "numeric|temporal|entity|status|comparison|aggregation|factual",
            "source_sentence": "The full sentence containing the claim",
            "extracted_value": "The specific value (number, date, name, etc.)",
            "entity_references": ["loan_123", "John Smith"]
        }
    ]
}

AI Response to analyze:
"""


CLAIM_VERIFICATION_PROMPT = """You are a fact-checking system. Compare each claim against the source data and determine if it is accurate.

For each claim, determine:
1. VERIFIED: The claim matches the source data
2. CONTRADICTED: The claim directly contradicts the source data
3. UNSUPPORTED: There is no source data to verify this claim
4. PARTIAL: The claim is partially correct

Consider numeric tolerance (within 1% is acceptable for aggregations).
Consider date/time differences (same day is acceptable).

Claims to verify:
{claims}

Source data available:
{source_data}

Respond in JSON format:
{
    "verifications": [
        {
            "claim_id": "claim identifier",
            "status": "verified|contradicted|unsupported|partial",
            "expected_value": "value from source data (if available)",
            "discrepancy": "description of mismatch (if any)",
            "confidence": 0.95
        }
    ]
}
"""


class HallucinationVerifier:
    """
    Service for detecting hallucinations in AI responses.

    Flow:
    1. extract_claims() - Parse response into discrete claims
    2. verify_claims() - Check each claim against source data
    3. generate_report() - Create comprehensive hallucination report
    """

    def __init__(self):
        # Short timeout: verification is non-blocking and should not delay responses
        self.client = get_anthropic_client(
            timeout=httpx.Timeout(30.0, connect=5.0),
            max_retries=2,
        )
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

        # Numeric patterns for rule-based extraction
        self.numeric_patterns = [
            r'\$[\d,]+(?:\.\d{2})?',                    # Currency
            r'\d+(?:\.\d+)?%',                          # Percentages
            r'\d{1,3}(?:,\d{3})*(?:\.\d+)?',           # Numbers with commas
            r'\d+\s*(?:days?|weeks?|months?|years?)',   # Time durations
        ]

        # Entity patterns
        self.entity_patterns = [
            r'loan\s*#?\s*(\w+)',                       # Loan numbers
            r'(?:borrower|client):\s*([^,\.]+)',       # Borrower names
            r'ID:\s*(\w+)',                             # Generic IDs
        ]

    async def extract_claims(
        self,
        response_text: str,
        use_llm: bool = True
    ) -> List[ExtractedClaim]:
        """
        Extract factual claims from an AI response.

        Args:
            response_text: The AI response to analyze
            use_llm: Whether to use LLM for extraction (more accurate but slower)

        Returns:
            List of extracted claims
        """
        claims = []

        if use_llm:
            claims = await self._extract_claims_llm(response_text)

        # Also do rule-based extraction to catch obvious numerics
        rule_based_claims = self._extract_claims_rules(response_text)

        # Merge, preferring LLM extractions but adding any rule-based ones not found
        existing_texts = {c.claim_text.lower() for c in claims}
        for claim in rule_based_claims:
            if claim.claim_text.lower() not in existing_texts:
                claims.append(claim)

        return claims

    async def _extract_claims_llm(self, response_text: str) -> List[ExtractedClaim]:
        """Use LLM to extract claims from response."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": CLAIM_EXTRACTION_PROMPT + response_text
                }]
            )

            # Parse JSON response
            content = response.content[0].text

            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                content = json_match.group(1)

            data = json.loads(content)
            claims = []

            for i, claim_data in enumerate(data.get("claims", [])):
                claim_type = self._map_claim_type(claim_data.get("claim_type", "factual"))
                claims.append(ExtractedClaim(
                    claim_id=f"claim_{i}_{hashlib.md5(claim_data['claim_text'].encode()).hexdigest()[:8]}",
                    claim_text=claim_data["claim_text"],
                    claim_type=claim_type,
                    source_sentence=claim_data.get("source_sentence", claim_data["claim_text"]),
                    extracted_value=claim_data.get("extracted_value"),
                    entity_references=claim_data.get("entity_references", []),
                    confidence=0.9
                ))

            return claims

        except Exception as e:
            logger.error(f"LLM claim extraction failed: {e}")
            return []

    def _extract_claims_rules(self, response_text: str) -> List[ExtractedClaim]:
        """Rule-based claim extraction for numeric and entity claims."""
        claims = []
        sentences = re.split(r'[.!?]+', response_text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Extract numeric claims
            for pattern in self.numeric_patterns:
                matches = re.findall(pattern, sentence, re.IGNORECASE)
                for match in matches:
                    claim_id = f"rule_{hashlib.md5(f'{sentence}:{match}'.encode()).hexdigest()[:8]}"
                    claims.append(ExtractedClaim(
                        claim_id=claim_id,
                        claim_text=sentence,
                        claim_type=ClaimType.NUMERIC,
                        source_sentence=sentence,
                        extracted_value=match,
                        entity_references=[],
                        confidence=0.7
                    ))

            # Extract entity references
            for pattern in self.entity_patterns:
                matches = re.findall(pattern, sentence, re.IGNORECASE)
                for match in matches:
                    claim_id = f"entity_{hashlib.md5(f'{sentence}:{match}'.encode()).hexdigest()[:8]}"
                    claims.append(ExtractedClaim(
                        claim_id=claim_id,
                        claim_text=sentence,
                        claim_type=ClaimType.ENTITY,
                        source_sentence=sentence,
                        extracted_value=match,
                        entity_references=[match],
                        confidence=0.7
                    ))

        return claims

    def _map_claim_type(self, type_str: str) -> ClaimType:
        """Map string claim type to enum."""
        mapping = {
            "numeric": ClaimType.NUMERIC,
            "temporal": ClaimType.TEMPORAL,
            "entity": ClaimType.ENTITY,
            "status": ClaimType.STATUS,
            "comparison": ClaimType.COMPARISON,
            "aggregation": ClaimType.AGGREGATION,
            "factual": ClaimType.FACTUAL,
        }
        return mapping.get(type_str.lower(), ClaimType.FACTUAL)

    async def verify_claims(
        self,
        claims: List[ExtractedClaim],
        source_data: Dict[str, Any],
        tools_used: List[str] = None,
        use_llm: bool = True
    ) -> List[ClaimVerificationResult]:
        """
        Verify extracted claims against source data.

        Args:
            claims: List of claims to verify
            source_data: Tool outputs and other source data
            tools_used: List of tools that provided the source data
            use_llm: Whether to use LLM for verification

        Returns:
            List of verification results
        """
        if not claims:
            return []

        results = []

        if use_llm and source_data:
            results = await self._verify_claims_llm(claims, source_data, tools_used)
        else:
            # Fall back to rule-based verification
            results = self._verify_claims_rules(claims, source_data, tools_used)

        return results

    async def _verify_claims_llm(
        self,
        claims: List[ExtractedClaim],
        source_data: Dict[str, Any],
        tools_used: List[str] = None
    ) -> List[ClaimVerificationResult]:
        """Use LLM to verify claims against source data."""
        try:
            # Prepare claims for verification
            claims_str = json.dumps([{
                "claim_id": c.claim_id,
                "claim_text": c.claim_text,
                "claim_type": c.claim_type.value,
                "extracted_value": c.extracted_value
            } for c in claims], indent=2)

            # Prepare source data (truncate if too large)
            source_str = json.dumps(source_data, indent=2, default=str)
            if len(source_str) > 10000:
                source_str = source_str[:10000] + "...[truncated]"

            prompt = CLAIM_VERIFICATION_PROMPT.format(
                claims=claims_str,
                source_data=source_str
            )

            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text

            # Extract JSON from response
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                content = json_match.group(1)

            data = json.loads(content)
            results = []

            # Map verifications back to claims
            claim_map = {c.claim_id: c for c in claims}

            for v in data.get("verifications", []):
                claim = claim_map.get(v["claim_id"])
                if not claim:
                    continue

                status = self._map_verification_status(v.get("status", "unable"))

                results.append(ClaimVerificationResult(
                    claim_id=v["claim_id"],
                    claim_text=claim.claim_text,
                    claim_type=claim.claim_type,
                    status=status,
                    source_data=source_data,
                    source_tool=tools_used[0] if tools_used else None,
                    expected_value=v.get("expected_value"),
                    claimed_value=claim.extracted_value,
                    discrepancy=v.get("discrepancy"),
                    confidence=v.get("confidence", 0.8)
                ))

            # Add results for any claims not verified
            verified_ids = {r.claim_id for r in results}
            for claim in claims:
                if claim.claim_id not in verified_ids:
                    results.append(ClaimVerificationResult(
                        claim_id=claim.claim_id,
                        claim_text=claim.claim_text,
                        claim_type=claim.claim_type,
                        status=VerificationStatus.UNABLE_TO_VERIFY,
                        source_tool=tools_used[0] if tools_used else None,
                        claimed_value=claim.extracted_value,
                        confidence=0.5
                    ))

            return results

        except Exception as e:
            logger.error(f"LLM verification failed: {e}")
            # Return unable to verify for all claims
            return [
                ClaimVerificationResult(
                    claim_id=c.claim_id,
                    claim_text=c.claim_text,
                    claim_type=c.claim_type,
                    status=VerificationStatus.UNABLE_TO_VERIFY,
                    discrepancy=f"Verification error: {str(e)}",
                    confidence=0.0
                )
                for c in claims
            ]

    def _verify_claims_rules(
        self,
        claims: List[ExtractedClaim],
        source_data: Dict[str, Any],
        tools_used: List[str] = None
    ) -> List[ClaimVerificationResult]:
        """Rule-based claim verification."""
        results = []
        source_str = json.dumps(source_data, default=str).lower()

        for claim in claims:
            status = VerificationStatus.UNSUPPORTED
            expected_value = None
            discrepancy = None

            # Check if the claimed value appears in source data
            if claim.extracted_value:
                value_str = str(claim.extracted_value).lower()

                if value_str in source_str:
                    status = VerificationStatus.VERIFIED
                else:
                    # Try to find similar numeric values
                    if claim.claim_type == ClaimType.NUMERIC:
                        status, expected_value = self._verify_numeric(
                            claim.extracted_value, source_data
                        )
                        if status == VerificationStatus.CONTRADICTED:
                            discrepancy = f"Expected {expected_value}, found {claim.extracted_value}"

            results.append(ClaimVerificationResult(
                claim_id=claim.claim_id,
                claim_text=claim.claim_text,
                claim_type=claim.claim_type,
                status=status,
                source_data=source_data,
                source_tool=tools_used[0] if tools_used else None,
                expected_value=expected_value,
                claimed_value=claim.extracted_value,
                discrepancy=discrepancy,
                confidence=0.6
            ))

        return results

    def _verify_numeric(
        self,
        claimed_value: Any,
        source_data: Dict[str, Any],
        tolerance: float = 0.01
    ) -> Tuple[VerificationStatus, Optional[Any]]:
        """Verify numeric claims with tolerance."""
        try:
            # Parse claimed value
            claimed_num = self._parse_number(claimed_value)
            if claimed_num is None:
                return VerificationStatus.UNSUPPORTED, None

            # Search for numeric values in source data
            source_numbers = self._extract_numbers_from_dict(source_data)

            for source_num in source_numbers:
                if source_num == 0:
                    if claimed_num == 0:
                        return VerificationStatus.VERIFIED, source_num
                    continue

                # Check within tolerance
                diff = abs(claimed_num - source_num) / abs(source_num)
                if diff <= tolerance:
                    return VerificationStatus.VERIFIED, source_num
                elif diff <= 0.5:  # Significantly different but same order of magnitude
                    return VerificationStatus.CONTRADICTED, source_num

            return VerificationStatus.UNSUPPORTED, None

        except Exception as e:
            logger.exception(f"Failed to verify numeric claim: {e}")
            return VerificationStatus.UNABLE_TO_VERIFY, None

    def _parse_number(self, value: Any) -> Optional[float]:
        """Parse a value into a number."""
        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            # Remove currency symbols, commas, percent signs
            clean = re.sub(r'[$,% ]', '', value)
            try:
                return float(clean)
            except ValueError:
                return None

        return None

    def _extract_numbers_from_dict(self, data: Any, numbers: List[float] = None) -> List[float]:
        """Recursively extract all numbers from a dictionary."""
        if numbers is None:
            numbers = []

        if isinstance(data, (int, float)):
            numbers.append(float(data))
        elif isinstance(data, dict):
            for value in data.values():
                self._extract_numbers_from_dict(value, numbers)
        elif isinstance(data, list):
            for item in data:
                self._extract_numbers_from_dict(item, numbers)
        elif isinstance(data, str):
            # Try to parse as number
            num = self._parse_number(data)
            if num is not None:
                numbers.append(num)

        return numbers

    def _map_verification_status(self, status_str: str) -> VerificationStatus:
        """Map string status to enum."""
        mapping = {
            "verified": VerificationStatus.VERIFIED,
            "unsupported": VerificationStatus.UNSUPPORTED,
            "contradicted": VerificationStatus.CONTRADICTED,
            "partial": VerificationStatus.PARTIAL,
            "unable": VerificationStatus.UNABLE_TO_VERIFY,
        }
        return mapping.get(status_str.lower(), VerificationStatus.UNABLE_TO_VERIFY)

    async def generate_report(
        self,
        session_id: str,
        message_id: str,
        response_text: str,
        source_data: Dict[str, Any],
        tools_used: List[str] = None,
        use_llm: bool = True
    ) -> HallucinationReport:
        """
        Generate a complete hallucination report for a response.

        Args:
            session_id: Session identifier
            message_id: Message identifier
            response_text: The AI response to analyze
            source_data: Tool outputs and source data
            tools_used: List of tools that provided source data
            use_llm: Whether to use LLM for analysis

        Returns:
            Complete hallucination report
        """
        import time
        start_time = time.time()

        # Extract claims
        claims = await self.extract_claims(response_text, use_llm=use_llm)

        # Verify claims
        verification_results = await self.verify_claims(
            claims, source_data, tools_used, use_llm=use_llm
        )

        # Count results
        verified = sum(1 for r in verification_results if r.status == VerificationStatus.VERIFIED)
        unsupported = sum(1 for r in verification_results if r.status == VerificationStatus.UNSUPPORTED)
        contradicted = sum(1 for r in verification_results if r.status == VerificationStatus.CONTRADICTED)
        partial = sum(1 for r in verification_results if r.status == VerificationStatus.PARTIAL)

        total = len(verification_results)

        # Calculate scores
        if total > 0:
            # Faithfulness = verified + partial (partially correct counts as half)
            faithfulness_score = (verified + (partial * 0.5)) / total
            # Hallucination rate = contradicted / verifiable claims
            verifiable = verified + contradicted + partial
            hallucination_rate = contradicted / verifiable if verifiable > 0 else 0.0
        else:
            faithfulness_score = 1.0  # No claims = fully faithful
            hallucination_rate = 0.0

        # Calculate confidence
        avg_confidence = (
            sum(r.confidence for r in verification_results) / total
            if total > 0 else 1.0
        )

        analysis_time = (time.time() - start_time) * 1000

        return HallucinationReport(
            session_id=session_id,
            message_id=message_id,
            response_text=response_text,
            total_claims=total,
            verified_claims=verified,
            unsupported_claims=unsupported,
            contradicted_claims=contradicted,
            partial_claims=partial,
            faithfulness_score=faithfulness_score,
            hallucination_rate=hallucination_rate,
            confidence=avg_confidence,
            claims=claims,
            verification_results=verification_results,
            tools_used=tools_used or [],
            source_data_summary=self._summarize_source_data(source_data),
            analysis_time_ms=analysis_time,
            timestamp=datetime.now(timezone.utc)
        )

    def _summarize_source_data(self, source_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a summary of source data for the report."""
        summary = {
            "tools_count": len(source_data) if isinstance(source_data, dict) else 0,
            "data_keys": list(source_data.keys())[:10] if isinstance(source_data, dict) else [],
            "has_numeric_data": False,
            "has_entity_data": False,
        }

        # Check what types of data we have
        source_str = json.dumps(source_data, default=str)
        if re.search(r'\d+', source_str):
            summary["has_numeric_data"] = True
        if re.search(r'"id":|"name":|"_id":', source_str.lower()):
            summary["has_entity_data"] = True

        return summary


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_verifier_instance: Optional[HallucinationVerifier] = None


def get_hallucination_verifier() -> HallucinationVerifier:
    """Get or create the hallucination verifier instance."""
    global _verifier_instance
    if _verifier_instance is None:
        _verifier_instance = HallucinationVerifier()
    return _verifier_instance
