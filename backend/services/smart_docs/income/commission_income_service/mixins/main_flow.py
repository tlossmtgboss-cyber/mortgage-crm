"""Main calculation entry point for commission income."""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from .._shared import (
    CommissionIncomeResult,
    CommissionSource,
    MONTHS_PER_YEAR,
    ONE_HUNDRED,
    TWO_PLACES,
    ZERO,
    _audit,
    _now_ms,
)

logger = logging.getLogger(__name__)


class MainFlowMixin:
    # =========================================================================
    # 1. MAIN ENTRY POINT
    # =========================================================================

    async def calculate_commission_income(
        self,
        loan_id: int,
        borrower_id: int,
        documents: Optional[List[Dict[str, Any]]] = None,
    ) -> CommissionIncomeResult:
        """
        Calculate qualifying commission income for a borrower.

        Gathers commission-related documents (or uses provided documents),
        groups them by employer/source, calculates per-source qualifying
        income, runs eligibility checks, and persists the result.

        Args:
            loan_id: The loan ID this calculation is for.
            borrower_id: The borrower whose income is being calculated.
            documents: Optional pre-gathered documents. If None, queries
                smart_documents for commission-related docs.

        Returns:
            CommissionIncomeResult with full calculation breakdown.
        """
        start_ms = _now_ms()
        audit_trail: List[Dict[str, Any]] = []
        _audit(audit_trail, "calculation_started", {
            "loan_id": loan_id,
            "borrower_id": borrower_id,
            "org_id": self.org_id,
            "user_id": self.user_id,
        })

        try:
            # Verify loan belongs to this org
            self._verify_loan_org(loan_id)

            # Step 1: Gather documents
            if documents is None:
                documents = self._gather_commission_documents(loan_id, borrower_id)

            _audit(audit_trail, "documents_gathered", {
                "document_count": len(documents),
                "doc_types": list({d.get("doc_type") for d in documents}),
            })

            if not documents:
                return CommissionIncomeResult(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    org_id=self.org_id,
                    confidence=0,
                    flags=["NO_COMMISSION_DOCUMENTS"],
                    recommendations=[
                        "No commission-related documents found. Upload W-2s, "
                        "paystubs, 1099-NEC/MISC forms, or tax returns showing "
                        "commission income to begin analysis."
                    ],
                    audit_trail=audit_trail,
                    success=False,
                    error="No commission income documents found for this borrower.",
                    duration_ms=_now_ms() - start_ms,
                )

            # Step 2: Parse and group documents by employer/source
            parsed_sources = self._parse_documents_into_sources(documents)
            _audit(audit_trail, "sources_parsed", {
                "source_count": len(parsed_sources),
                "employers": [s.get("employer_name") for s in parsed_sources],
            })

            if not parsed_sources:
                return CommissionIncomeResult(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    org_id=self.org_id,
                    confidence=0,
                    flags=["NO_COMMISSION_DATA_EXTRACTED"],
                    recommendations=[
                        "Documents were found but no commission income data could "
                        "be extracted. Verify document quality and completeness."
                    ],
                    audit_trail=audit_trail,
                    success=False,
                    error="Could not extract commission income data from provided documents.",
                    duration_ms=_now_ms() - start_ms,
                )

            # Step 3: Calculate per source
            commission_sources: List[CommissionSource] = []
            for parsed in parsed_sources:
                source = self._calculate_single_source(parsed, audit_trail)
                commission_sources.append(source)

            # Step 4: Run eligibility checks
            # Get total income from loan for commission-to-total ratio
            total_gross_income = self._get_borrower_total_income(loan_id, borrower_id)
            eligibility = self._validate_commission_eligibility(
                commission_sources, total_gross_income, audit_trail,
            )

            # Step 5: Aggregate across all sources
            total_monthly_commission = sum(
                (s.qualifying_monthly_commission for s in commission_sources), ZERO
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            total_monthly_base = sum(
                (s.qualifying_monthly_base for s in commission_sources), ZERO
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            total_monthly = (total_monthly_commission + total_monthly_base).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )
            total_annual = (total_monthly * MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )

            # Commission as percentage of total income
            if total_gross_income > ZERO:
                commission_pct = (
                    total_monthly_commission / total_gross_income * ONE_HUNDRED
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            else:
                # If no other income data, commission IS the total income
                commission_pct = ONE_HUNDRED if total_monthly_commission > ZERO else ZERO

            # Determine primary method and overall trend
            primary_method = self._determine_primary_method(commission_sources)
            overall_trend = self._determine_overall_trend(commission_sources)

            # Confidence: weighted average by qualifying amount
            confidence = self._calculate_aggregate_confidence(commission_sources)

            # Step 6: Generate flags, recommendations, tasks
            all_flags = self._generate_flags(
                commission_sources, eligibility, commission_pct, overall_trend,
            )
            recommendations = self._generate_recommendations(all_flags, eligibility)
            tasks = self._generate_tasks(all_flags, eligibility, loan_id)

            _audit(audit_trail, "calculation_completed", {
                "total_monthly_commission": float(total_monthly_commission),
                "total_monthly_base": float(total_monthly_base),
                "total_qualifying_monthly": float(total_monthly),
                "commission_pct": float(commission_pct),
                "method": primary_method.value,
                "trend": overall_trend.value,
                "confidence": confidence,
                "flag_count": len(all_flags),
                "task_count": len(tasks),
            })

            result = CommissionIncomeResult(
                loan_id=loan_id,
                borrower_id=borrower_id,
                org_id=self.org_id,
                sources=commission_sources,
                eligibility=eligibility,
                total_qualifying_monthly_commission=total_monthly_commission,
                total_qualifying_monthly_base=total_monthly_base,
                total_qualifying_monthly=total_monthly,
                total_qualifying_annual=total_annual,
                commission_pct_of_total_income=commission_pct,
                primary_calculation_method=primary_method,
                overall_trend=overall_trend,
                confidence=confidence,
                flags=all_flags,
                recommendations=recommendations,
                tasks_to_create=tasks,
                audit_trail=audit_trail,
                duration_ms=_now_ms() - start_ms,
            )

            # Step 7: Persist
            self._save_calculation(result)

            return result

        except Exception as e:
            logger.exception(
                "Commission income calculation failed: loan=%s borrower=%s org=%s: %s",
                loan_id, borrower_id, self.org_id, e,
            )
            _audit(audit_trail, "calculation_error", {"error": str(e)})
            return CommissionIncomeResult(
                loan_id=loan_id,
                borrower_id=borrower_id,
                org_id=self.org_id,
                confidence=0,
                audit_trail=audit_trail,
                success=False,
                error=str(e),
                duration_ms=_now_ms() - start_ms,
            )
