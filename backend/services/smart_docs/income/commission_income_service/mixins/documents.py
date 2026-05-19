"""Document gathering, parsing, and grouping by employer/source."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from .._shared import (
    COMMISSION_DOC_TYPES,
    PAY_FREQUENCY_MULTIPLIERS,
    TWO_PLACES,
    ZERO,
    _months_elapsed_in_year,
    _parse_date,
    _safe_int,
    _to_decimal,
)

logger = logging.getLogger(__name__)


class DocumentsMixin:
    # =========================================================================
    # INTERNAL: DOCUMENT GATHERING
    # =========================================================================

    def _gather_commission_documents(
        self,
        loan_id: int,
        borrower_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Query smart_documents for commission-relevant documents with
        extracted field data from smart_document_extractions.
        """
        rows = self.db.execute(
            text("""
                SELECT
                    sd.id              AS doc_id,
                    sd.doc_type        AS doc_type,
                    sd.ocr_text        AS ocr_text,
                    sd.uploaded_at     AS uploaded_at,
                    sd.file_name       AS file_name,
                    sde.extracted_fields  AS extracted_fields,
                    sde.confidence_scores AS confidence_scores,
                    sde.overall_confidence AS overall_confidence
                FROM smart_documents sd
                LEFT JOIN smart_document_extractions sde
                    ON sde.document_id = sd.id
                JOIN loans l ON l.id = sd.loan_id
                WHERE sd.loan_id = :loan_id
                  AND sd.borrower_id = :borrower_id
                  AND sd.doc_type IN :doc_types
                  AND sd.status NOT IN ('REJECTED', 'EXPIRED')
                  AND l.organization_id = :org_id
                ORDER BY sd.uploaded_at DESC
            """),
            {
                "loan_id": loan_id,
                "borrower_id": borrower_id,
                "doc_types": tuple(COMMISSION_DOC_TYPES),
                "org_id": self.org_id,
            },
        ).fetchall()

        results: List[Dict[str, Any]] = []
        for row in rows:
            extracted = row.extracted_fields
            if isinstance(extracted, str):
                try:
                    extracted = json.loads(extracted)
                except (json.JSONDecodeError, TypeError):
                    extracted = {}

            confidence_scores = row.confidence_scores
            if isinstance(confidence_scores, str):
                try:
                    confidence_scores = json.loads(confidence_scores)
                except (json.JSONDecodeError, TypeError):
                    confidence_scores = {}

            results.append({
                "doc_id": row.doc_id,
                "doc_type": str(row.doc_type) if row.doc_type else None,
                "ocr_text": row.ocr_text,
                "uploaded_at": row.uploaded_at,
                "file_name": row.file_name,
                "extracted_fields": extracted or {},
                "confidence_scores": confidence_scores or {},
                "overall_confidence": row.overall_confidence or 0,
            })

        return results

    # =========================================================================
    # INTERNAL: DOCUMENT PARSING & GROUPING
    # =========================================================================

    def _parse_documents_into_sources(
        self,
        documents: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Parse documents and group by employer/source to build commission
        income sources. Each employer gets a separate source entry with
        all relevant year data aggregated.

        Returns list of dicts, each representing one commission source with:
            - employer_name, employer_ein, position_title
            - commission_type
            - yearly_data: {year: {commission, base, total_w2, ...}}
            - ytd_data: {commission, base, total_gross, months_elapsed, pay_date}
            - voe_data: {start_date, current_base, commission_frequency, ...}
            - doc_ids: list of contributing doc IDs
        """
        # Group by employer (normalized name)
        employer_groups: Dict[str, Dict[str, Any]] = {}

        for doc in documents:
            ef = doc.get("extracted_fields", {})
            doc_type = doc.get("doc_type", "")
            doc_id = doc.get("doc_id")

            employer = (
                ef.get("employer_name", "") or ""
            ).strip()
            employer_key = employer.lower() if employer else "_unknown_"

            if employer_key not in employer_groups:
                employer_groups[employer_key] = {
                    "employer_name": employer or None,
                    "employer_ein": ef.get("employer_ein") or ef.get("ein"),
                    "position_title": ef.get("job_title") or ef.get("position_title"),
                    "commission_type": CommissionType.W2_COMMISSION,
                    "yearly_data": {},
                    "ytd_data": None,
                    "voe_data": None,
                    "doc_ids": [],
                    "expense_data": [],
                }

            group = employer_groups[employer_key]
            group["doc_ids"].append(doc_id)

            # Update employer info if we get better data
            if not group["employer_ein"] and (ef.get("employer_ein") or ef.get("ein")):
                group["employer_ein"] = ef.get("employer_ein") or ef.get("ein")
            if not group["position_title"] and (ef.get("job_title") or ef.get("position_title")):
                group["position_title"] = ef.get("job_title") or ef.get("position_title")

            if doc_type == "PAYSTUB":
                self._parse_paystub_into_group(group, ef)

            elif doc_type == "W2":
                self._parse_w2_into_group(group, ef)

            elif doc_type in ("1099_NEC", "1099_MISC"):
                group["commission_type"] = CommissionType.INDEPENDENT_1099
                self._parse_1099_into_group(group, ef)

            elif doc_type in ("TAX_RETURN", "BUSINESS_TAX_RETURN"):
                self._parse_tax_return_into_group(group, ef)

            elif doc_type == "VOE":
                self._parse_voe_into_group(group, ef)

        # Filter out groups with no commission data at all
        result: List[Dict[str, Any]] = []
        for group in employer_groups.values():
            has_commission = False

            # Check yearly data for commission amounts
            for year_data in group["yearly_data"].values():
                if _to_decimal(year_data.get("commission")) > ZERO:
                    has_commission = True
                    break

            # Check YTD
            if not has_commission and group["ytd_data"]:
                if _to_decimal(group["ytd_data"].get("commission")) > ZERO:
                    has_commission = True

            # Check 1099 amounts (all income is commission)
            if not has_commission and group["commission_type"] == CommissionType.INDEPENDENT_1099:
                for year_data in group["yearly_data"].values():
                    if _to_decimal(year_data.get("total_w2")) > ZERO:
                        has_commission = True
                        break

            if has_commission:
                result.append(group)

        return result

    def _parse_paystub_into_group(
        self,
        group: Dict[str, Any],
        ef: Dict[str, Any],
    ) -> None:
        """Extract YTD commission and base data from a paystub."""
        ytd_commission = _to_decimal(ef.get("ytd_commission"))
        ytd_gross = _to_decimal(ef.get("ytd_gross"))
        ytd_base = _to_decimal(
            ef.get("ytd_regular_earnings")
            or ef.get("ytd_base_salary")
            or ef.get("ytd_regular_pay")
        )
        pay_date_str = ef.get("pay_date")
        pay_freq = (ef.get("pay_frequency") or "MONTHLY").upper()

        # Current period commission
        current_commission = _to_decimal(ef.get("commission"))
        current_base = _to_decimal(
            ef.get("regular_earnings")
            or ef.get("base_salary")
            or ef.get("regular_pay")
            or ef.get("gross_pay")
        )

        months_elapsed = _months_elapsed_in_year(pay_date_str)

        existing_ytd = group["ytd_data"]
        if existing_ytd is None or (
            pay_date_str and (existing_ytd.get("pay_date") or "0000") < pay_date_str
        ):
            group["ytd_data"] = {
                "commission": ytd_commission,
                "base": ytd_base if ytd_base > ZERO else (ytd_gross - ytd_commission if ytd_gross > ytd_commission else ZERO),
                "total_gross": ytd_gross,
                "months_elapsed": months_elapsed or 0,
                "pay_date": pay_date_str,
                "pay_frequency": pay_freq,
                "current_period_commission": current_commission,
                "current_period_base": current_base,
            }

    def _parse_w2_into_group(
        self,
        group: Dict[str, Any],
        ef: Dict[str, Any],
    ) -> None:
        """Extract annual commission and wage data from a W-2."""
        tax_year = _safe_int(ef.get("tax_year"))
        if not tax_year:
            return

        total_wages = _to_decimal(ef.get("wages_tips_compensation"))
        # W-2 Box 1 includes all compensation. We need to separate commission.
        # Some W-2 extractions may have commission broken out; most do not.
        commission = _to_decimal(ef.get("commission_income") or ef.get("commission"))
        base_salary = _to_decimal(ef.get("base_salary") or ef.get("regular_wages"))

        # If commission not broken out but we have base, derive it
        if commission == ZERO and base_salary > ZERO and total_wages > base_salary:
            commission = (total_wages - base_salary).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        existing = group["yearly_data"].get(tax_year, {})
        group["yearly_data"][tax_year] = {
            "commission": max(commission, _to_decimal(existing.get("commission"))),
            "base": max(base_salary, _to_decimal(existing.get("base"))),
            "total_w2": max(total_wages, _to_decimal(existing.get("total_w2"))),
            "source": "W2",
        }

    def _parse_1099_into_group(
        self,
        group: Dict[str, Any],
        ef: Dict[str, Any],
    ) -> None:
        """Extract commission data from 1099-NEC or 1099-MISC."""
        tax_year = _safe_int(ef.get("tax_year"))
        if not tax_year:
            return

        # 1099-NEC Box 1: Nonemployee compensation (all is commission)
        nec_amount = _to_decimal(
            ef.get("nonemployee_compensation")
            or ef.get("box1_amount")
            or ef.get("total_compensation")
        )

        # 1099-MISC: various boxes, but typically Box 7 (pre-2020) or Box 1
        misc_amount = _to_decimal(
            ef.get("box7_nonemployee_compensation")
            or ef.get("rents")  # sometimes misclassified
        )

        total = nec_amount + misc_amount

        existing = group["yearly_data"].get(tax_year, {})
        group["yearly_data"][tax_year] = {
            "commission": total + _to_decimal(existing.get("commission")),
            "base": ZERO,  # 1099 has no base salary
            "total_w2": total + _to_decimal(existing.get("total_w2")),
            "source": "1099",
        }

        # Look for Schedule C expenses
        schedule_c_expenses = _to_decimal(ef.get("schedule_c_total_expenses"))
        if schedule_c_expenses > ZERO:
            group["expense_data"].append({
                "tax_year": tax_year,
                "schedule_c_expenses": schedule_c_expenses,
                "gross_commission": total,
            })

    def _parse_tax_return_into_group(
        self,
        group: Dict[str, Any],
        ef: Dict[str, Any],
    ) -> None:
        """Extract commission-relevant data from tax returns."""
        tax_year = _safe_int(ef.get("tax_year"))
        if not tax_year:
            return

        # Schedule C self-employment income (common for real estate agents)
        schedule_c_gross = _to_decimal(ef.get("schedule_c_gross_receipts"))
        schedule_c_net = _to_decimal(ef.get("net_profit_loss") or ef.get("net_profit"))
        schedule_c_expenses = _to_decimal(ef.get("schedule_c_total_expenses"))

        if schedule_c_gross > ZERO:
            group["commission_type"] = CommissionType.SCHEDULE_C
            existing = group["yearly_data"].get(tax_year, {})
            group["yearly_data"][tax_year] = {
                "commission": schedule_c_net if schedule_c_net > ZERO else schedule_c_gross,
                "base": ZERO,
                "total_w2": schedule_c_gross,
                "schedule_c_gross": schedule_c_gross,
                "schedule_c_net": schedule_c_net,
                "depreciation_addback": _to_decimal(ef.get("depreciation_addback")),
                "amortization_addback": _to_decimal(ef.get("amortization_addback")),
                "source": "SCHEDULE_C",
            }

            if schedule_c_expenses > ZERO:
                group["expense_data"].append({
                    "tax_year": tax_year,
                    "schedule_c_expenses": schedule_c_expenses,
                    "gross_commission": schedule_c_gross,
                })

        # Form 2106 unreimbursed employee expenses
        form_2106 = _to_decimal(ef.get("form_2106_expenses"))
        if form_2106 > ZERO:
            group["expense_data"].append({
                "tax_year": tax_year,
                "form_2106_expenses": form_2106,
                "gross_commission": _to_decimal(
                    group["yearly_data"].get(tax_year, {}).get("commission")
                ),
            })

        # Also check W-2 wages on tax return Line 1
        wages_line1 = _to_decimal(ef.get("wages_salaries_tips") or ef.get("line1_wages"))
        if wages_line1 > ZERO and tax_year not in group["yearly_data"]:
            group["yearly_data"][tax_year] = {
                "commission": ZERO,  # Cannot separate from tax return Line 1
                "base": ZERO,
                "total_w2": wages_line1,
                "source": "TAX_RETURN",
            }

    def _parse_voe_into_group(
        self,
        group: Dict[str, Any],
        ef: Dict[str, Any],
    ) -> None:
        """Extract employment verification data from VOE."""
        start_date_str = ef.get("employment_start_date") or ef.get("hire_date")
        current_base = _to_decimal(ef.get("current_base_salary") or ef.get("base_rate"))
        commission_freq = ef.get("commission_frequency") or ef.get("commission_pay_frequency")
        probability_of_continuance = ef.get("probability_of_continuance")

        # VOE may have annual earnings history
        prior_year1_earnings = _to_decimal(ef.get("prior_year1_earnings") or ef.get("year1_earnings"))
        prior_year2_earnings = _to_decimal(ef.get("prior_year2_earnings") or ef.get("year2_earnings"))
        ytd_earnings = _to_decimal(ef.get("ytd_earnings"))

        group["voe_data"] = {
            "start_date": start_date_str,
            "current_base": current_base,
            "commission_frequency": commission_freq,
            "probability_of_continuance": probability_of_continuance,
            "prior_year1_earnings": prior_year1_earnings,
            "prior_year2_earnings": prior_year2_earnings,
            "ytd_earnings": ytd_earnings,
            "is_currently_employed": ef.get("currently_employed", True),
        }
