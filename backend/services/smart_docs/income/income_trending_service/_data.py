"""Auto-generated mixin. See income_trending_service/__init__.py."""
from __future__ import annotations

import json
import logging
import math
import statistics
import time
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

from ._types import (
    ZERO, TWO_PLACES, FOUR_PLACES,
    STABLE_VARIANCE_PCT, INCREASING_THRESHOLD_PCT,
    DECLINING_WARN_PCT, DECLINING_CRITICAL_PCT, VOLATILE_CV_THRESHOLD,
    PAYSTUB_TAX_DISCREPANCY_PCT, PAYSTUB_TAX_CRITICAL_PCT,
    DEFAULT_QUALIFYING_DTI, MINIMUM_INCOME_MONTHS_HISTORY,
    SEASONAL_AMPLITUDE_THRESHOLD, PAY_FREQUENCY_MULTIPLIERS,
    BLS_OCCUPATION_PATTERNS,
    TrendClassification, DeclineAction, AlertSeverity, IncomeSourceType,
    IncomeDataPoint, TrendLine, SeasonalPattern, IncomeAlert,
    ReconciliationDiscrepancy, ReconciliationResult, SourceTrend,
    IncomePrediction, ChartDataSeries, ChartData, TrendAnalysis,
)

logger = logging.getLogger(__name__)


class _DataMixin:

    async def _load_income_data(
        self,
        org_id: str,
        borrower_id: int,
        loan_id: Optional[int] = None,
    ) -> List[IncomeDataPoint]:
        """
        Load income data from multiple DB sources:
        1. smart_documents / smart_document_extractions (paystubs, W2s, tax returns)
        2. income_sources from prior income_calculations
        3. Bank deposit patterns (from bank_statement_extractions if available)

        Enforces org_id tenant isolation on all queries.
        """
        data_points: List[IncomeDataPoint] = []

        # --- Source 1: Extracted document data ---
        doc_points = await self._load_from_documents(org_id, borrower_id, loan_id)
        data_points.extend(doc_points)

        # --- Source 2: Prior income calculations ---
        calc_points = await self._load_from_calculations(org_id, borrower_id, loan_id)
        data_points.extend(calc_points)

        # Deduplicate: prefer higher-confidence points for the same period/source
        data_points = self._deduplicate_points(data_points)

        return data_points


    async def _load_from_documents(
        self,
        org_id: str,
        borrower_id: int,
        loan_id: Optional[int] = None,
    ) -> List[IncomeDataPoint]:
        """Load income data points from smart_documents + extractions."""
        points: List[IncomeDataPoint] = []

        loan_filter = "AND sd.loan_id = :loan_id" if loan_id else ""
        params: Dict[str, Any] = {
            "org_id": org_id,
            "borrower_id": borrower_id,
        }
        if loan_id:
            params["loan_id"] = loan_id

        trend_query = (
            "SELECT"
            " sd.id AS doc_id,"
            " sd.doc_type,"
            " sd.uploaded_at,"
            " sde.extracted_fields,"
            " sde.overall_confidence"
            " FROM smart_documents sd"
            " LEFT JOIN smart_document_extractions sde"
            "     ON sde.document_id = sd.id"
            " WHERE sd.organization_id = :org_id"
            "   AND sd.borrower_id = :borrower_id"
            "   AND sd.doc_type IN ('PAYSTUB', 'W2', 'TAX_RETURN')"
            "   AND sd.status NOT IN ('REJECTED', 'EXPIRED')"
            "   " + loan_filter
            + " ORDER BY sd.uploaded_at ASC"
        )
        rows = self.db.execute(text(trend_query), params).fetchall()

        for row in rows:
            extracted = self._parse_json_field(row.extracted_fields)
            if not extracted:
                continue

            confidence = int(row.overall_confidence or 70)
            doc_type = str(row.doc_type) if row.doc_type else "UNKNOWN"

            try:
                if doc_type == "PAYSTUB":
                    pts = self._parse_paystub_data(extracted, row.doc_id, confidence)
                    points.extend(pts)
                elif doc_type == "W2":
                    pts = self._parse_w2_data(extracted, row.doc_id, confidence)
                    points.extend(pts)
                elif doc_type == "TAX_RETURN":
                    pts = self._parse_tax_return_data(extracted, row.doc_id, confidence)
                    points.extend(pts)
            except Exception as e:
                logger.warning(
                    f"Failed to parse income data from doc {row.doc_id} "
                    f"(type={doc_type}): {e}"
                )

        return points


    async def _load_from_calculations(
        self,
        org_id: str,
        borrower_id: int,
        loan_id: Optional[int] = None,
    ) -> List[IncomeDataPoint]:
        """Load income data from prior income_sources records."""
        points: List[IncomeDataPoint] = []

        loan_filter = "AND ic.loan_id = :loan_id" if loan_id else ""
        params: Dict[str, Any] = {"borrower_id": borrower_id}
        if loan_id:
            params["loan_id"] = loan_id

        # income_sources joined through income_calculations for tenant isolation
        # income_calculations links to loan which has organization_id
        isrc_query = (
            "SELECT"
            " isrc.source_type,"
            " isrc.employer_name,"
            " isrc.total_monthly_income,"
            " isrc.total_annual_income,"
            " isrc.year1_income,"
            " isrc.year2_income,"
            " isrc.year_over_year_change_pct,"
            " isrc.trending_direction,"
            " isrc.ai_confidence,"
            " isrc.created_at,"
            " ic.loan_id"
            " FROM income_sources isrc"
            " JOIN income_calculations ic ON ic.id = isrc.calculation_id"
            " JOIN loans l ON l.id = ic.loan_id"
            " WHERE isrc.borrower_id = :borrower_id"
            "   AND l.organization_id = :org_id"
            "   AND ic.status NOT IN ('rejected', 'error')"
            "   " + loan_filter
            + " ORDER BY isrc.created_at ASC"
        )
        rows = self.db.execute(
            text(isrc_query),
            {**params, "org_id": org_id},
        ).fetchall()

        for row in rows:
            created = row.created_at
            if isinstance(created, datetime):
                period_date = created.date()
            elif isinstance(created, date):
                period_date = created
            else:
                continue

            # Year 1 (most recent)
            if row.year1_income is not None:
                year1_end = date(period_date.year - 1, 12, 31)
                year1_start = date(period_date.year - 1, 1, 1)
                points.append(IncomeDataPoint(
                    period_start=year1_start,
                    period_end=year1_end,
                    amount=self._to_decimal(row.year1_income),
                    source_type=row.source_type or "W2",
                    employer_name=row.employer_name,
                    income_component="total",
                    annualized=True,
                    confidence=int(row.ai_confidence or 70),
                ))

            # Year 2 (prior year)
            if row.year2_income is not None:
                year2_end = date(period_date.year - 2, 12, 31)
                year2_start = date(period_date.year - 2, 1, 1)
                points.append(IncomeDataPoint(
                    period_start=year2_start,
                    period_end=year2_end,
                    amount=self._to_decimal(row.year2_income),
                    source_type=row.source_type or "W2",
                    employer_name=row.employer_name,
                    income_component="total",
                    annualized=True,
                    confidence=int(row.ai_confidence or 70),
                ))

        return points

    # =========================================================================
    # 4. DOCUMENT PARSERS
    # =========================================================================


    def _parse_paystub_data(
        self,
        extracted: Dict[str, Any],
        doc_id: int,
        confidence: int,
    ) -> List[IncomeDataPoint]:
        """Parse income data from paystub extracted fields."""
        points: List[IncomeDataPoint] = []

        pay_date_str = extracted.get("pay_date") or extracted.get("pay_period_end")
        if not pay_date_str:
            return points

        try:
            pay_date = self._parse_date(pay_date_str)
        except ValueError:
            return points

        employer = extracted.get("employer_name")
        period_start_str = extracted.get("pay_period_start")
        period_start = self._parse_date(period_start_str) if period_start_str else pay_date

        # YTD gross is most useful for trending
        ytd_gross = self._to_decimal(extracted.get("ytd_gross") or extracted.get("ytd_gross_pay"))
        current_gross = self._to_decimal(extracted.get("gross_pay") or extracted.get("current_gross"))

        if ytd_gross > ZERO:
            # YTD data point: annualize based on pay date position in year
            months_elapsed = self._months_elapsed_in_year(pay_date)
            if months_elapsed and months_elapsed > 0:
                annualized = (ytd_gross / months_elapsed * 12).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                points.append(IncomeDataPoint(
                    period_start=date(pay_date.year, 1, 1),
                    period_end=pay_date,
                    amount=annualized,
                    source_type="PAYSTUB",
                    source_doc_id=doc_id,
                    employer_name=employer,
                    income_component="total",
                    annualized=True,
                    confidence=confidence,
                ))

        if current_gross > ZERO:
            # Individual pay period data point (not annualized)
            points.append(IncomeDataPoint(
                period_start=period_start,
                period_end=pay_date,
                amount=current_gross,
                source_type="PAYSTUB",
                source_doc_id=doc_id,
                employer_name=employer,
                income_component="total",
                annualized=False,
                confidence=confidence,
            ))

        # Component-level data if available
        for component, field_names in [
            ("base", ["base_pay", "regular_pay", "salary"]),
            ("overtime", ["overtime_pay", "ot_pay"]),
            ("commission", ["commission", "commission_pay"]),
            ("bonus", ["bonus", "bonus_pay"]),
        ]:
            for field_name in field_names:
                val = self._to_decimal(extracted.get(f"ytd_{field_name}") or extracted.get(field_name))
                if val > ZERO:
                    points.append(IncomeDataPoint(
                        period_start=period_start,
                        period_end=pay_date,
                        amount=val,
                        source_type="PAYSTUB",
                        source_doc_id=doc_id,
                        employer_name=employer,
                        income_component=component,
                        annualized=False,
                        confidence=confidence - 5,  # component-level slightly lower confidence
                    ))
                    break  # take first match per component

        return points


    def _parse_w2_data(
        self,
        extracted: Dict[str, Any],
        doc_id: int,
        confidence: int,
    ) -> List[IncomeDataPoint]:
        """Parse income data from W2 extracted fields."""
        points: List[IncomeDataPoint] = []

        tax_year = extracted.get("tax_year")
        if not tax_year:
            return points

        try:
            year = int(tax_year)
        except (ValueError, TypeError):
            return points

        employer = extracted.get("employer_name")
        wages = self._to_decimal(
            extracted.get("wages_tips_compensation")
            or extracted.get("box_1")
            or extracted.get("total_wages")
        )

        if wages > ZERO:
            points.append(IncomeDataPoint(
                period_start=date(year, 1, 1),
                period_end=date(year, 12, 31),
                amount=wages,
                source_type="W2",
                source_doc_id=doc_id,
                employer_name=employer,
                income_component="total",
                annualized=True,
                confidence=confidence,
            ))

        return points


    def _parse_tax_return_data(
        self,
        extracted: Dict[str, Any],
        doc_id: int,
        confidence: int,
    ) -> List[IncomeDataPoint]:
        """Parse income data from tax return extracted fields."""
        points: List[IncomeDataPoint] = []

        tax_year = extracted.get("tax_year")
        if not tax_year:
            return points

        try:
            year = int(tax_year)
        except (ValueError, TypeError):
            return points

        # Total income from 1040
        total_income = self._to_decimal(
            extracted.get("total_income")
            or extracted.get("line_9")  # 1040 total income line
            or extracted.get("adjusted_gross_income")
        )
        if total_income > ZERO:
            points.append(IncomeDataPoint(
                period_start=date(year, 1, 1),
                period_end=date(year, 12, 31),
                amount=total_income,
                source_type="TAX_RETURN",
                source_doc_id=doc_id,
                income_component="total",
                annualized=True,
                confidence=confidence,
            ))

        # Wages from W2 reported on 1040
        wages = self._to_decimal(
            extracted.get("wages_salaries_tips")
            or extracted.get("line_1")
        )
        if wages > ZERO and wages != total_income:
            points.append(IncomeDataPoint(
                period_start=date(year, 1, 1),
                period_end=date(year, 12, 31),
                amount=wages,
                source_type="TAX_RETURN",
                source_doc_id=doc_id,
                income_component="base",
                annualized=True,
                confidence=confidence,
            ))

        # Self-employment income (Schedule C)
        se_income = self._to_decimal(
            extracted.get("schedule_c_net_profit")
            or extracted.get("self_employment_income")
        )
        if se_income != ZERO:  # can be negative
            points.append(IncomeDataPoint(
                period_start=date(year, 1, 1),
                period_end=date(year, 12, 31),
                amount=se_income,
                source_type="TAX_RETURN",
                source_doc_id=doc_id,
                income_component="self_employment",
                annualized=True,
                confidence=confidence - 5,
            ))

        # Rental income (Schedule E)
        rental_income = self._to_decimal(
            extracted.get("schedule_e_net")
            or extracted.get("rental_income")
        )
        if rental_income != ZERO:
            points.append(IncomeDataPoint(
                period_start=date(year, 1, 1),
                period_end=date(year, 12, 31),
                amount=rental_income,
                source_type="TAX_RETURN",
                source_doc_id=doc_id,
                income_component="rental",
                annualized=True,
                confidence=confidence - 5,
            ))

        return points

    # =========================================================================
    # 5. TREND ANALYSIS (PER SOURCE)
    # =========================================================================


    async def _save_analysis(self, result: TrendAnalysis) -> None:
        """
        Persist trend analysis results to income_trend_analyses table.

        Creates the table if it does not exist (first-run safety).
        """
        try:
            # Ensure table exists
            self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS income_trend_analyses (
                    id SERIAL PRIMARY KEY,
                    organization_id VARCHAR(255) NOT NULL,
                    borrower_id INTEGER NOT NULL,
                    loan_id INTEGER,
                    analysis_date TIMESTAMP WITH TIME ZONE NOT NULL,
                    overall_classification VARCHAR(50) NOT NULL,
                    qualifying_monthly_income NUMERIC(18,2),
                    qualifying_annual_income NUMERIC(18,2),
                    source_count INTEGER DEFAULT 0,
                    prediction_json JSONB,
                    reconciliation_json JSONB,
                    industry_comparison_json JSONB,
                    alerts_json JSONB,
                    chart_data_json JSONB,
                    confidence INTEGER DEFAULT 0,
                    calculation_method VARCHAR(50),
                    flags JSONB,
                    tasks_json JSONB,
                    duration_ms INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))

            # Serialize complex objects
            prediction_json = None
            if result.prediction:
                prediction_json = json.dumps({
                    "projected_monthly": float(result.prediction.projected_monthly_income),
                    "projected_annual": float(result.prediction.projected_annual_income),
                    "ci_low": float(result.prediction.confidence_interval_low),
                    "ci_high": float(result.prediction.confidence_interval_high),
                    "confidence_level": result.prediction.confidence_level,
                    "months_forward": result.prediction.months_forward,
                    "projection_date": result.prediction.projection_date.isoformat(),
                    "trend_basis": result.prediction.trend_basis.value,
                    "break_even_months": result.prediction.break_even_months,
                    "r_squared": result.prediction.r_squared,
                    "notes": result.prediction.notes,
                })

            reconciliation_json = None
            if result.reconciliation:
                reconciliation_json = json.dumps({
                    "is_reconciled": result.reconciliation.is_reconciled,
                    "discrepancy_pct": float(result.reconciliation.overall_discrepancy_pct),
                    "paystub_annual": float(result.reconciliation.paystub_annualized_income),
                    "tax_annual": float(result.reconciliation.tax_return_income),
                    "confidence": result.reconciliation.confidence,
                    "notes": result.reconciliation.notes,
                    "discrepancy_count": len(result.reconciliation.discrepancies),
                })

            alerts_json = json.dumps([
                {
                    "severity": a.severity.value,
                    "type": a.alert_type,
                    "title": a.title,
                    "description": a.description,
                    "source_type": a.source_type,
                    "recommended_action": a.recommended_action,
                }
                for a in result.alerts
            ])

            industry_json = json.dumps(result.industry_comparison) if result.industry_comparison else None

            # Serialize chart data
            chart_json = None
            if result.chart_data:
                chart_json = json.dumps({
                    "series": [
                        {
                            "label": s.label,
                            "data_points": s.data_points,
                            "line_type": s.line_type,
                            "color_hint": s.color_hint,
                        }
                        for s in result.chart_data.series
                    ],
                    "annotations": result.chart_data.annotations,
                    "summary_stats": result.chart_data.summary_stats,
                    "date_range": result.chart_data.date_range,
                })

            self.db.execute(
                text("""
                    INSERT INTO income_trend_analyses (
                        organization_id, borrower_id, loan_id,
                        analysis_date, overall_classification,
                        qualifying_monthly_income, qualifying_annual_income,
                        source_count,
                        prediction_json, reconciliation_json,
                        industry_comparison_json,
                        alerts_json, chart_data_json,
                        confidence, calculation_method,
                        flags, tasks_json,
                        duration_ms, created_at, updated_at
                    ) VALUES (
                        :org_id, :borrower_id, :loan_id,
                        :analysis_date, :classification,
                        :monthly, :annual,
                        :source_count,
                        :prediction, :reconciliation,
                        :industry,
                        :alerts, :chart_data,
                        :confidence, :method,
                        :flags, :tasks,
                        :duration, :now, :now
                    )
                """),
                {
                    "org_id": result.org_id,
                    "borrower_id": result.borrower_id,
                    "loan_id": result.loan_id,
                    "analysis_date": result.analysis_date,
                    "classification": result.overall_classification.value,
                    "monthly": float(result.overall_qualifying_monthly),
                    "annual": float(result.overall_qualifying_annual),
                    "source_count": len(result.source_trends),
                    "prediction": prediction_json,
                    "reconciliation": reconciliation_json,
                    "industry": industry_json,
                    "alerts": alerts_json,
                    "chart_data": chart_json,
                    "confidence": result.confidence,
                    "method": result.calculation_method,
                    "flags": json.dumps(result.flags),
                    "tasks": json.dumps(result.tasks_to_create),
                    "duration": result.duration_ms,
                    "now": datetime.now(timezone.utc),
                },
            )
            self.db.commit()
            logger.info(
                f"Income trend analysis saved: org={result.org_id} "
                f"borrower={result.borrower_id} "
                f"classification={result.overall_classification.value}"
            )

        except Exception as e:
            logger.exception(f"Failed to save income trend analysis: {e}")
            self.db.rollback()

    # =========================================================================
    # 18. UTILITY METHODS
    # =========================================================================

