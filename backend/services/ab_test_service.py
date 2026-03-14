"""
A/B Test Service - Core logic for booking page A/B testing.

Handles:
- Deterministic variant assignment using hash-based bucketing
- Impression and conversion recording
- Statistical significance testing using chi-square
- Result aggregation and winner determination
"""

import hashlib
import logging
import math
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from database.models.ab_test import ABTest, ABTestResult, ABTestStatus

logger = logging.getLogger(__name__)


class ABTestService:
    """Service for managing A/B test lifecycle and statistical analysis."""

    def __init__(self, db: Session):
        self.db = db

    # ========================================================================
    # VARIANT ASSIGNMENT
    # ========================================================================

    def assign_variant(self, test_id: int, visitor_id: str) -> str:
        """Assign a visitor to a variant deterministically using hash-based bucketing.

        The same visitor_id always gets the same variant for a given test,
        even across multiple visits. Uses MD5 hash modulo 100 to determine
        bucket, then compares against the traffic_split percentage.

        Args:
            test_id: The A/B test ID.
            visitor_id: Unique visitor identifier (cookie, fingerprint, etc.).

        Returns:
            "A" or "B"

        Raises:
            ValueError: If test not found or not active.
        """
        test = self.db.query(ABTest).filter(ABTest.id == test_id).first()
        if not test:
            raise ValueError(f"A/B test {test_id} not found")
        if test.status != ABTestStatus.ACTIVE.value:
            raise ValueError(f"A/B test {test_id} is not active (status: {test.status})")

        # Check if visitor already has an assignment
        existing = self.db.query(ABTestResult).filter(
            ABTestResult.ab_test_id == test_id,
            ABTestResult.visitor_id == visitor_id,
        ).first()

        if existing:
            return existing.variant

        # Deterministic hash-based assignment
        hash_input = f"{test_id}:{visitor_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        bucket = hash_value % 100

        variant = "A" if bucket < test.traffic_split else "B"
        return variant

    # ========================================================================
    # RECORDING
    # ========================================================================

    def record_impression(self, test_id: int, variant: str, visitor_id: str) -> ABTestResult:
        """Record an impression (page view) for a visitor.

        Creates a new result row if this is the visitor's first impression,
        otherwise increments the existing impression count.

        Args:
            test_id: The A/B test ID.
            variant: "A" or "B".
            visitor_id: Unique visitor identifier.

        Returns:
            The ABTestResult record.
        """
        if variant not in ("A", "B"):
            raise ValueError(f"Invalid variant: {variant}. Must be 'A' or 'B'.")

        existing = self.db.query(ABTestResult).filter(
            ABTestResult.ab_test_id == test_id,
            ABTestResult.visitor_id == visitor_id,
        ).first()

        if existing:
            existing.impressions += 1
            self.db.flush()
            return existing

        result = ABTestResult(
            ab_test_id=test_id,
            variant=variant,
            visitor_id=visitor_id,
            impressions=1,
            bookings=0,
        )
        self.db.add(result)
        self.db.flush()
        return result

    def record_conversion(self, test_id: int, variant: str, visitor_id: str) -> ABTestResult:
        """Record a conversion (booking made) for a visitor.

        The visitor must already have an impression recorded. Increments
        the bookings count on their existing result row.

        Args:
            test_id: The A/B test ID.
            variant: "A" or "B".
            visitor_id: Unique visitor identifier.

        Returns:
            The ABTestResult record.

        Raises:
            ValueError: If no impression exists for this visitor.
        """
        if variant not in ("A", "B"):
            raise ValueError(f"Invalid variant: {variant}. Must be 'A' or 'B'.")

        existing = self.db.query(ABTestResult).filter(
            ABTestResult.ab_test_id == test_id,
            ABTestResult.visitor_id == visitor_id,
        ).first()

        if not existing:
            # Auto-create impression if conversion comes without one
            existing = ABTestResult(
                ab_test_id=test_id,
                variant=variant,
                visitor_id=visitor_id,
                impressions=1,
                bookings=0,
            )
            self.db.add(existing)
            self.db.flush()

        existing.bookings += 1
        self.db.flush()
        return existing

    # ========================================================================
    # RESULTS & STATISTICS
    # ========================================================================

    def calculate_results(self, test_id: int) -> Dict[str, Any]:
        """Calculate aggregated results with statistical significance.

        Returns conversion rates for each variant, the absolute and relative
        difference, and chi-square significance test results.

        Args:
            test_id: The A/B test ID.

        Returns:
            Dict with variant stats, winner info, and significance data.
        """
        test = self.db.query(ABTest).filter(ABTest.id == test_id).first()
        if not test:
            raise ValueError(f"A/B test {test_id} not found")

        # Aggregate per-variant stats
        stats = self.db.query(
            ABTestResult.variant,
            func.count(ABTestResult.id).label("unique_visitors"),
            func.sum(ABTestResult.impressions).label("total_impressions"),
            func.sum(ABTestResult.bookings).label("total_bookings"),
        ).filter(
            ABTestResult.ab_test_id == test_id,
        ).group_by(ABTestResult.variant).all()

        variant_data = {}
        for row in stats:
            impressions = int(row.total_impressions or 0)
            bookings = int(row.total_bookings or 0)
            conversion_rate = (bookings / impressions * 100) if impressions > 0 else 0.0

            variant_data[row.variant] = {
                "variant": row.variant,
                "unique_visitors": int(row.unique_visitors or 0),
                "impressions": impressions,
                "bookings": bookings,
                "conversion_rate": round(conversion_rate, 2),
            }

        # Ensure both variants exist in the output
        for v in ("A", "B"):
            if v not in variant_data:
                variant_data[v] = {
                    "variant": v,
                    "unique_visitors": 0,
                    "impressions": 0,
                    "bookings": 0,
                    "conversion_rate": 0.0,
                }

        a = variant_data["A"]
        b = variant_data["B"]

        # Determine leader
        winner = None
        lift = 0.0
        if a["conversion_rate"] > b["conversion_rate"] and a["impressions"] > 0:
            winner = "A"
            lift = a["conversion_rate"] - b["conversion_rate"]
        elif b["conversion_rate"] > a["conversion_rate"] and b["impressions"] > 0:
            winner = "B"
            lift = b["conversion_rate"] - a["conversion_rate"]

        # Calculate relative improvement
        baseline_rate = a["conversion_rate"] if winner == "B" else b["conversion_rate"]
        relative_lift = (lift / baseline_rate * 100) if baseline_rate > 0 else 0.0

        # Statistical significance
        significance = self._chi_square_test(
            a["impressions"], a["bookings"],
            b["impressions"], b["bookings"],
        )

        return {
            "test_id": test_id,
            "test_name": test.name,
            "status": test.status,
            "element_type": test.element_type,
            "variants": variant_data,
            "winner": winner,
            "lift": round(lift, 2),
            "relative_lift_pct": round(relative_lift, 1),
            "significance": significance,
            "total_impressions": a["impressions"] + b["impressions"],
            "total_bookings": a["bookings"] + b["bookings"],
        }

    def is_significant(self, test_id: int, confidence: float = 0.95) -> bool:
        """Check if the test results are statistically significant.

        Args:
            test_id: The A/B test ID.
            confidence: Confidence level (default 0.95 for 95%).

        Returns:
            True if results are significant at the given confidence level.
        """
        results = self.calculate_results(test_id)
        sig = results["significance"]

        if not sig["valid"]:
            return False

        # Map confidence level to chi-square critical value (1 degree of freedom)
        critical_values = {
            0.90: 2.706,
            0.95: 3.841,
            0.99: 6.635,
        }
        critical = critical_values.get(confidence, 3.841)
        return sig["chi_square"] >= critical

    # ========================================================================
    # INTERNAL: CHI-SQUARE TEST
    # ========================================================================

    def _chi_square_test(
        self,
        impressions_a: int, conversions_a: int,
        impressions_b: int, conversions_b: int,
    ) -> Dict[str, Any]:
        """Perform a chi-square test of independence on 2x2 contingency table.

        Tests whether the difference in conversion rates between variants A and B
        is statistically significant.

        The contingency table is:
                        | Converted | Not Converted |
            Variant A   |    a      |    b          |
            Variant B   |    c      |    d          |

        Args:
            impressions_a: Total impressions for variant A.
            conversions_a: Conversions (bookings) for variant A.
            impressions_b: Total impressions for variant B.
            conversions_b: Conversions (bookings) for variant B.

        Returns:
            Dict with chi_square statistic, p_value approximation, confidence level, and validity.
        """
        total = impressions_a + impressions_b

        # Need minimum sample size for valid test
        if total < 20 or impressions_a < 5 or impressions_b < 5:
            return {
                "valid": False,
                "reason": "Insufficient sample size (need at least 5 impressions per variant, 20 total)",
                "chi_square": 0.0,
                "p_value": 1.0,
                "confidence_pct": 0.0,
            }

        total_conversions = conversions_a + conversions_b
        total_non_conversions = total - total_conversions

        # If no conversions at all, can't compute
        if total_conversions == 0 or total_non_conversions == 0:
            return {
                "valid": False,
                "reason": "No variance in outcomes (all converted or none converted)",
                "chi_square": 0.0,
                "p_value": 1.0,
                "confidence_pct": 0.0,
            }

        # Build 2x2 table
        # observed: [conv_a, non_conv_a, conv_b, non_conv_b]
        observed = [
            conversions_a,
            impressions_a - conversions_a,
            conversions_b,
            impressions_b - conversions_b,
        ]

        # Expected values under null hypothesis (same conversion rate)
        expected = [
            impressions_a * total_conversions / total,
            impressions_a * total_non_conversions / total,
            impressions_b * total_conversions / total,
            impressions_b * total_non_conversions / total,
        ]

        # Check expected frequencies >= 5 (standard chi-square assumption)
        if any(e < 5 for e in expected):
            # Use Yates' correction for small samples
            chi_sq = sum(
                (abs(o - e) - 0.5) ** 2 / e
                for o, e in zip(observed, expected)
                if e > 0
            )
        else:
            chi_sq = sum(
                (o - e) ** 2 / e
                for o, e in zip(observed, expected)
                if e > 0
            )

        # Approximate p-value from chi-square with 1 degree of freedom
        # Using the survival function approximation
        p_value = self._chi_square_p_value(chi_sq, df=1)

        # Determine confidence level
        confidence_pct = round((1.0 - p_value) * 100, 1)

        return {
            "valid": True,
            "chi_square": round(chi_sq, 4),
            "p_value": round(p_value, 6),
            "confidence_pct": min(confidence_pct, 99.9),
            "is_significant_90": chi_sq >= 2.706,
            "is_significant_95": chi_sq >= 3.841,
            "is_significant_99": chi_sq >= 6.635,
        }

    @staticmethod
    def _chi_square_p_value(x: float, df: int = 1) -> float:
        """Approximate the p-value of a chi-square statistic.

        Uses the regularized incomplete gamma function approximation.
        For df=1 (our case), this simplifies to the complementary error function.

        Args:
            x: Chi-square statistic.
            df: Degrees of freedom (always 1 for 2x2 table).

        Returns:
            Approximate p-value.
        """
        if x <= 0:
            return 1.0

        # For df=1, chi-square p-value = 2 * (1 - Phi(sqrt(x)))
        # where Phi is the standard normal CDF
        # Using the complementary error function: erfc(z/sqrt(2))
        z = math.sqrt(x)
        return math.erfc(z / math.sqrt(2))
