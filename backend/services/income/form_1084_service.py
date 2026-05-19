# Fannie Mae Form 1084 — Cash Flow Analysis Generator
#
# Implements Fannie Mae Form 1084 per Selling Guide B3-3.1-03 (03/04/2026).
# Generates structured cash flow analysis data from IncomeCalculation records,
# then renders as PDF (via reportlab) or styled HTML for UI preview.
#
# This is the form LOs must include in every loan file for borrowers with
# self-employment, variable, or non-standard income. Previously required
# manual completion — this service auto-populates from calculation results.

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database.models.income_calculation import (
    IncomeCalculation,
    IncomeSource,
    IncomeSourceType,
    TrendingDirection,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional: reportlab for PDF generation
# ---------------------------------------------------------------------------

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    logger.info(
        "reportlab not installed — Form 1084 PDF generation will use HTML fallback"
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PAGE_WIDTH, _PAGE_HEIGHT = letter  # 612 x 792 points (US Letter)
_MARGIN = 54  # 0.75 inch
_CONTENT_WIDTH = _PAGE_WIDTH - 2 * _MARGIN

# Fannie Mae guideline: use lower of 2-year average when income is declining
_DECLINING_THRESHOLD_PCT = Decimal("0")  # Any decline triggers lower-of rule


# ============================================================================
# DATA MODEL — Maps to Form 1084 structure
# ============================================================================

@dataclass
class IncomeLineItem:
    """Single income line with multi-year columns matching Form 1084 layout."""

    label: str
    year1: Optional[Decimal] = None  # Most recent full tax year
    year2: Optional[Decimal] = None  # Prior tax year
    ytd: Optional[Decimal] = None  # Year-to-date from paystub/P&L
    monthly: Optional[Decimal] = None  # Qualifying monthly amount
    notes: str = ""


@dataclass
class W2BaseSection:
    """Form 1084 Section: W-2 Base Employment Income."""

    employer_name: str = ""
    position_title: str = ""
    employment_start_date: Optional[str] = None
    year1_w2: Optional[Decimal] = None
    year2_w2: Optional[Decimal] = None
    ytd_base: Optional[Decimal] = None
    monthly_base: Optional[Decimal] = None


@dataclass
class OvertimeSection:
    """Form 1084 Section: Overtime Income."""

    year1_ot: Optional[Decimal] = None
    year2_ot: Optional[Decimal] = None
    ytd_ot: Optional[Decimal] = None
    monthly_ot: Optional[Decimal] = None
    trending: str = ""  # "increasing", "stable", "declining"


@dataclass
class BonusSection:
    """Form 1084 Section: Bonus Income."""

    year1_bonus: Optional[Decimal] = None
    year2_bonus: Optional[Decimal] = None
    ytd_bonus: Optional[Decimal] = None
    monthly_bonus: Optional[Decimal] = None
    trending: str = ""


@dataclass
class CommissionSection:
    """Form 1084 Section: Commission Income."""

    year1_commission: Optional[Decimal] = None
    year2_commission: Optional[Decimal] = None
    ytd_commission: Optional[Decimal] = None
    monthly_commission: Optional[Decimal] = None
    trending: str = ""
    unreimbursed_expenses: Optional[Decimal] = None


@dataclass
class SelfEmploymentSection:
    """Form 1084 Section: Self-Employment / Schedule C Income.

    Per Fannie Mae B3-3.1-03: Net profit + depreciation/amortization add-backs,
    averaged over 2 years. If declining, use the lower of the two years.
    """

    business_name: str = ""
    year1_net_profit: Optional[Decimal] = None
    year2_net_profit: Optional[Decimal] = None
    depreciation_addback: Optional[Decimal] = None
    amortization_addback: Optional[Decimal] = None
    monthly_se: Optional[Decimal] = None


@dataclass
class PartnershipSCorpSection:
    """Form 1084 Section: Partnership (1065) / S-Corp (1120S) K-1 Income."""

    business_name: str = ""
    year1_ordinary: Optional[Decimal] = None
    year2_ordinary: Optional[Decimal] = None
    guaranteed_payments: Optional[Decimal] = None
    monthly_k1: Optional[Decimal] = None


@dataclass
class RentalSection:
    """Form 1084 Section: Rental Income (Schedule E)."""

    property_address: str = ""
    gross_rents: Optional[Decimal] = None
    total_expenses: Optional[Decimal] = None
    depreciation: Optional[Decimal] = None
    net_rental: Optional[Decimal] = None
    monthly_rental: Optional[Decimal] = None


@dataclass
class OtherIncomeSection:
    """Form 1084 Section: Other Income (non-employment)."""

    social_security: Optional[Decimal] = None
    pension: Optional[Decimal] = None
    child_support: Optional[Decimal] = None
    alimony: Optional[Decimal] = None
    monthly_other: Optional[Decimal] = None


@dataclass
class Form1084Data:
    """Complete Fannie Mae Form 1084 — Cash Flow Analysis data.

    Maps to the official Form 1084 structure per Selling Guide B3-3.1-03.
    Each section corresponds to a worksheet block on the form. The service
    populates this from IncomeCalculation/IncomeSource records, then
    renderers (PDF or HTML) consume it for output.
    """

    # Header identification
    borrower_name: str = ""
    co_borrower_name: str = ""
    loan_number: str = ""
    employer_name: str = ""
    business_name: str = ""

    # Income type sections
    w2_base: W2BaseSection = field(default_factory=W2BaseSection)
    overtime: OvertimeSection = field(default_factory=OvertimeSection)
    bonus: BonusSection = field(default_factory=BonusSection)
    commission: CommissionSection = field(default_factory=CommissionSection)
    self_employment: SelfEmploymentSection = field(
        default_factory=SelfEmploymentSection
    )
    partnership_scorp: PartnershipSCorpSection = field(
        default_factory=PartnershipSCorpSection
    )
    rental: RentalSection = field(default_factory=RentalSection)
    other_income: OtherIncomeSection = field(default_factory=OtherIncomeSection)

    # Multiple sources — when a borrower has >1 employer or rental property
    additional_w2_sources: List[W2BaseSection] = field(default_factory=list)
    additional_rental_sources: List[RentalSection] = field(default_factory=list)

    # Totals
    total_qualifying_monthly_income: Optional[Decimal] = None

    # Calculation metadata
    calculation_notes: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    calculation_id: Optional[int] = None
    generated_at: Optional[datetime] = None


# ============================================================================
# SERVICE
# ============================================================================

class Form1084Service:
    """Generates Fannie Mae Form 1084 (Cash Flow Analysis) from income
    calculation results stored in the database.

    Usage::

        service = Form1084Service()
        data = service.generate_from_calculation(calculation_id=42, db=session)
        pdf_bytes = service.generate_pdf(data)
        html_str = service.generate_html(data)

    References:
        Fannie Mae Selling Guide B3-3.1-03 — Income Calculation and
        Documentation Requirements for Self-Employed Borrowers.
    """

    # ------------------------------------------------------------------
    # generate_from_calculation
    # ------------------------------------------------------------------

    def generate_from_calculation(
        self,
        calculation_id: int,
        db: Session,
    ) -> Form1084Data:
        """Load an IncomeCalculation and its sources, then map to Form 1084.

        Args:
            calculation_id: Primary key of the IncomeCalculation record.
            db: SQLAlchemy session (caller manages lifecycle).

        Returns:
            Fully populated Form1084Data ready for PDF/HTML rendering.

        Raises:
            ValueError: If calculation_id does not exist.
        """
        calc: Optional[IncomeCalculation] = (
            db.query(IncomeCalculation)
            .filter(IncomeCalculation.id == calculation_id)
            .first()
        )
        if calc is None:
            raise ValueError(
                f"IncomeCalculation with id={calculation_id} not found"
            )

        sources: List[IncomeSource] = (
            db.query(IncomeSource)
            .filter(IncomeSource.calculation_id == calculation_id)
            .order_by(IncomeSource.is_primary.desc(), IncomeSource.id)
            .all()
        )

        logger.info(
            "Generating Form 1084 for calculation_id=%d with %d income sources",
            calculation_id,
            len(sources),
        )

        data = Form1084Data(
            calculation_id=calculation_id,
            generated_at=datetime.now(timezone.utc),
        )

        # Resolve borrower / loan context from the calculation record.
        data.loan_number = str(calc.loan_id)  # Loan ID as fallback
        data = self._resolve_borrower_context(calc, db, data)

        # Map each IncomeSource into the appropriate 1084 section
        total_monthly = Decimal("0")
        w2_count = 0

        for source in sources:
            section_monthly = self._map_source_to_section(source, data)
            if section_monthly is not None:
                total_monthly += section_monthly

            # Track W-2 employer count for multi-employer support
            if source.source_type == IncomeSourceType.W2_EMPLOYMENT:
                w2_count += 1

        # Use the calculation-level total if present (it may include
        # aggregation logic not captured at the source level).
        if calc.total_qualifying_monthly_income is not None:
            data.total_qualifying_monthly_income = Decimal(
                str(calc.total_qualifying_monthly_income)
            )
        else:
            data.total_qualifying_monthly_income = total_monthly.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        # Pull AI flags and notes
        if calc.ai_flags:
            flags = calc.ai_flags if isinstance(calc.ai_flags, list) else []
            data.flags.extend(str(f) for f in flags)
        if calc.ai_recommendations:
            recs = (
                calc.ai_recommendations
                if isinstance(calc.ai_recommendations, list)
                else []
            )
            data.calculation_notes.extend(str(r) for r in recs)

        logger.info(
            "Form 1084 generated: total_qualifying_monthly=$%s, sources=%d, flags=%d",
            data.total_qualifying_monthly_income,
            len(sources),
            len(data.flags),
        )

        return data

    # ------------------------------------------------------------------
    # generate_pdf
    # ------------------------------------------------------------------

    def generate_pdf(self, data: Form1084Data) -> bytes:
        """Render Form1084Data as a PDF document.

        Uses reportlab if available; otherwise generates an HTML document
        and wraps it in a minimal PDF-like byte stream (callers should
        prefer ``generate_html`` when reportlab is absent).

        Args:
            data: Populated Form1084Data instance.

        Returns:
            PDF file content as bytes.
        """
        if HAS_REPORTLAB:
            return self._generate_pdf_reportlab(data)

        logger.warning(
            "reportlab unavailable — generating HTML-wrapped PDF fallback"
        )
        html = self.generate_html(data)
        return html.encode("utf-8")

    # ------------------------------------------------------------------
    # generate_html
    # ------------------------------------------------------------------

    def generate_html(self, data: Form1084Data) -> str:
        """Render Form1084Data as styled HTML for in-app preview.

        Args:
            data: Populated Form1084Data instance.

        Returns:
            Complete HTML document string.
        """
        generated_date = (
            data.generated_at.strftime("%B %d, %Y")
            if data.generated_at
            else datetime.now(timezone.utc).strftime("%B %d, %Y")
        )

        rows_html = ""

        # --- W-2 Base ---
        if data.w2_base.monthly_base is not None:
            rows_html += self._html_section_header("W-2 Base Employment Income")
            rows_html += self._html_employer_info(data.w2_base)
            rows_html += self._html_income_row(
                "Base Salary/Wages",
                data.w2_base.year1_w2,
                data.w2_base.year2_w2,
                data.w2_base.ytd_base,
                data.w2_base.monthly_base,
            )
        for extra in data.additional_w2_sources:
            if extra.monthly_base is not None:
                rows_html += self._html_section_header(
                    f"W-2 Base — {extra.employer_name or 'Additional Employer'}"
                )
                rows_html += self._html_employer_info(extra)
                rows_html += self._html_income_row(
                    "Base Salary/Wages",
                    extra.year1_w2,
                    extra.year2_w2,
                    extra.ytd_base,
                    extra.monthly_base,
                )

        # --- Overtime ---
        if data.overtime.monthly_ot is not None:
            rows_html += self._html_section_header("Overtime")
            rows_html += self._html_income_row(
                "Overtime",
                data.overtime.year1_ot,
                data.overtime.year2_ot,
                data.overtime.ytd_ot,
                data.overtime.monthly_ot,
                trending=data.overtime.trending,
            )

        # --- Bonus ---
        if data.bonus.monthly_bonus is not None:
            rows_html += self._html_section_header("Bonus")
            rows_html += self._html_income_row(
                "Bonus",
                data.bonus.year1_bonus,
                data.bonus.year2_bonus,
                data.bonus.ytd_bonus,
                data.bonus.monthly_bonus,
                trending=data.bonus.trending,
            )

        # --- Commission ---
        if data.commission.monthly_commission is not None:
            rows_html += self._html_section_header("Commission")
            rows_html += self._html_income_row(
                "Commission",
                data.commission.year1_commission,
                data.commission.year2_commission,
                data.commission.ytd_commission,
                data.commission.monthly_commission,
                trending=data.commission.trending,
            )
            if data.commission.unreimbursed_expenses:
                rows_html += self._html_detail_row(
                    "Less: Unreimbursed Expenses",
                    data.commission.unreimbursed_expenses,
                )

        # --- Self-Employment ---
        if data.self_employment.monthly_se is not None:
            rows_html += self._html_section_header(
                f"Self-Employment (Schedule C) — {data.self_employment.business_name or 'N/A'}"
            )
            rows_html += self._html_income_row(
                "Net Profit (Line 31)",
                data.self_employment.year1_net_profit,
                data.self_employment.year2_net_profit,
                None,
                None,
            )
            if data.self_employment.depreciation_addback:
                rows_html += self._html_detail_row(
                    "Add: Depreciation",
                    data.self_employment.depreciation_addback,
                )
            if data.self_employment.amortization_addback:
                rows_html += self._html_detail_row(
                    "Add: Amortization/Casualty Loss",
                    data.self_employment.amortization_addback,
                )
            rows_html += self._html_income_row(
                "Qualifying Monthly SE Income",
                None,
                None,
                None,
                data.self_employment.monthly_se,
            )

        # --- Partnership / S-Corp ---
        if data.partnership_scorp.monthly_k1 is not None:
            rows_html += self._html_section_header(
                f"Partnership/S-Corp (K-1) — {data.partnership_scorp.business_name or 'N/A'}"
            )
            rows_html += self._html_income_row(
                "Ordinary Income",
                data.partnership_scorp.year1_ordinary,
                data.partnership_scorp.year2_ordinary,
                None,
                None,
            )
            if data.partnership_scorp.guaranteed_payments:
                rows_html += self._html_detail_row(
                    "Guaranteed Payments",
                    data.partnership_scorp.guaranteed_payments,
                )
            rows_html += self._html_income_row(
                "Qualifying Monthly K-1 Income",
                None,
                None,
                None,
                data.partnership_scorp.monthly_k1,
            )

        # --- Rental ---
        rental_sections = [data.rental] + data.additional_rental_sources
        for idx, r in enumerate(rental_sections):
            if r.monthly_rental is not None:
                addr = r.property_address or f"Property {idx + 1}"
                rows_html += self._html_section_header(
                    f"Rental Income (Schedule E) — {addr}"
                )
                rows_html += self._html_detail_row("Gross Rents", r.gross_rents)
                rows_html += self._html_detail_row(
                    "Less: Total Expenses", r.total_expenses
                )
                rows_html += self._html_detail_row(
                    "Add: Depreciation", r.depreciation
                )
                rows_html += self._html_detail_row(
                    "Net Rental Income", r.net_rental
                )
                rows_html += self._html_income_row(
                    "Qualifying Monthly Rental",
                    None,
                    None,
                    None,
                    r.monthly_rental,
                )

        # --- Other Income ---
        if data.other_income.monthly_other is not None:
            rows_html += self._html_section_header("Other Income")
            if data.other_income.social_security:
                rows_html += self._html_detail_row(
                    "Social Security", data.other_income.social_security
                )
            if data.other_income.pension:
                rows_html += self._html_detail_row(
                    "Pension/Retirement", data.other_income.pension
                )
            if data.other_income.child_support:
                rows_html += self._html_detail_row(
                    "Child Support", data.other_income.child_support
                )
            if data.other_income.alimony:
                rows_html += self._html_detail_row(
                    "Alimony", data.other_income.alimony
                )
            rows_html += self._html_income_row(
                "Qualifying Monthly Other",
                None,
                None,
                None,
                data.other_income.monthly_other,
            )

        # --- Total ---
        total_display = self._fmt(data.total_qualifying_monthly_income)

        # --- Notes / Flags ---
        notes_html = ""
        if data.calculation_notes:
            notes_html += '<div class="notes"><h3>Calculation Notes</h3><ul>'
            for note in data.calculation_notes:
                notes_html += f"<li>{_escape_html(note)}</li>"
            notes_html += "</ul></div>"
        if data.flags:
            notes_html += '<div class="flags"><h3>Flags</h3><ul>'
            for flag_item in data.flags:
                notes_html += f'<li class="flag">{_escape_html(flag_item)}</li>'
            notes_html += "</ul></div>"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Cash Flow Analysis &mdash; Form 1084</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 11px;
         color: #1a1a1a; padding: 32px; max-width: 850px; margin: 0 auto; }}
  h1 {{ font-size: 18px; text-align: center; margin-bottom: 4px; }}
  .subtitle {{ text-align: center; font-size: 11px; color: #666; margin-bottom: 16px; }}
  .header-info {{ display: flex; justify-content: space-between; margin-bottom: 20px;
                  border: 1px solid #ddd; padding: 10px 14px; background: #fafafa; }}
  .header-info div {{ flex: 1; }}
  .header-info label {{ font-weight: bold; display: block; font-size: 9px;
                        text-transform: uppercase; color: #888; margin-bottom: 2px; }}
  .header-info span {{ font-size: 12px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 4px; }}
  th {{ background: #2563eb; color: #fff; padding: 6px 8px; text-align: left;
       font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }}
  th.num {{ text-align: right; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #e5e7eb; font-size: 11px; }}
  td.num {{ text-align: right; font-family: 'Courier New', monospace; }}
  tr.section-header td {{ background: #f0f4ff; font-weight: bold; font-size: 11px;
                          color: #1e40af; border-bottom: 2px solid #2563eb;
                          padding: 8px; }}
  tr.detail td {{ color: #555; font-size: 10px; padding-left: 24px; }}
  tr.total td {{ font-weight: bold; background: #f0fdf4; border-top: 2px solid #16a34a;
                 font-size: 13px; }}
  tr.total td.num {{ color: #16a34a; }}
  .trending {{ font-size: 9px; padding: 1px 6px; border-radius: 3px; margin-left: 4px; }}
  .trending.increasing {{ background: #dcfce7; color: #166534; }}
  .trending.stable {{ background: #e0e7ff; color: #3730a3; }}
  .trending.declining {{ background: #fee2e2; color: #991b1b; }}
  .notes, .flags {{ margin-top: 16px; padding: 10px 14px; border-radius: 4px; }}
  .notes {{ background: #fffbeb; border: 1px solid #fbbf24; }}
  .flags {{ background: #fef2f2; border: 1px solid #f87171; }}
  .notes h3, .flags h3 {{ font-size: 12px; margin-bottom: 6px; }}
  .notes ul, .flags ul {{ padding-left: 18px; }}
  .notes li, .flags li {{ margin-bottom: 3px; font-size: 10px; }}
  .flag {{ color: #991b1b; }}
  .footer {{ margin-top: 24px; padding-top: 10px; border-top: 1px solid #ddd;
             text-align: center; font-size: 9px; color: #999; }}
  .employer-info {{ font-size: 10px; color: #555; padding: 4px 8px 2px 16px; }}
  .employer-info span {{ margin-right: 16px; }}
</style>
</head>
<body>

<h1>Cash Flow Analysis &mdash; Form 1084</h1>
<div class="subtitle">Fannie Mae Selling Guide B3-3.1-03</div>

<div class="header-info">
  <div><label>Borrower</label><span>{_escape_html(data.borrower_name or 'N/A')}</span></div>
  <div><label>Co-Borrower</label><span>{_escape_html(data.co_borrower_name or 'N/A')}</span></div>
  <div><label>Loan #</label><span>{_escape_html(data.loan_number or 'N/A')}</span></div>
  <div><label>Generated</label><span>{generated_date}</span></div>
</div>

<table>
<thead>
  <tr>
    <th style="width:40%">Income Source</th>
    <th class="num" style="width:15%">Year 1</th>
    <th class="num" style="width:15%">Year 2</th>
    <th class="num" style="width:15%">YTD</th>
    <th class="num" style="width:15%">Monthly</th>
  </tr>
</thead>
<tbody>
{rows_html}
<tr class="total">
  <td colspan="4">Total Qualifying Monthly Income</td>
  <td class="num">{total_display}</td>
</tr>
</tbody>
</table>

{notes_html}

<div class="footer">
  Generated by Perennia AI | {generated_date} | Loan: {_escape_html(data.loan_number or 'N/A')}
</div>

</body>
</html>"""

        return html

    # ==================================================================
    # INTERNAL — Source-to-section mapping
    # ==================================================================

    def _map_source_to_section(
        self,
        source: IncomeSource,
        data: Form1084Data,
    ) -> Optional[Decimal]:
        """Map a single IncomeSource to the appropriate Form1084Data section.

        Applies Fannie Mae averaging rules:
        - 2-year average for stable/increasing income
        - Lower of 2 years when declining (B3-3.1-03)

        Returns the qualifying monthly amount contributed by this source,
        or None if the source has no usable data.
        """
        monthly = self._safe_decimal(source.total_monthly_income)
        year1 = self._safe_decimal(source.year1_income)
        year2 = self._safe_decimal(source.year2_income)
        trending = (
            source.trending_direction.value
            if source.trending_direction
            else ""
        )

        # Apply Fannie Mae declining-income rule: if income is declining,
        # use the most recent (lower) year rather than the 2-year average.
        computed_monthly = self._apply_averaging_rules(
            year1, year2, monthly, trending
        )

        stype = source.source_type

        if stype == IncomeSourceType.W2_EMPLOYMENT:
            section = W2BaseSection(
                employer_name=source.employer_name or "",
                position_title=source.position_title or "",
                employment_start_date=(
                    source.employment_start_date.isoformat()
                    if source.employment_start_date
                    else None
                ),
                year1_w2=year1 or None,
                year2_w2=year2 or None,
                ytd_base=self._safe_decimal(source.base_monthly_income),
                monthly_base=computed_monthly,
            )
            # First W-2 goes into primary slot; additional go into list
            if data.w2_base.monthly_base is None:
                data.w2_base = section
                data.employer_name = section.employer_name
            else:
                data.additional_w2_sources.append(section)

        elif stype == IncomeSourceType.OVERTIME:
            data.overtime = OvertimeSection(
                year1_ot=year1 or None,
                year2_ot=year2 or None,
                ytd_ot=self._safe_decimal(source.overtime_monthly),
                monthly_ot=computed_monthly,
                trending=trending,
            )

        elif stype == IncomeSourceType.BONUS:
            data.bonus = BonusSection(
                year1_bonus=year1 or None,
                year2_bonus=year2 or None,
                ytd_bonus=self._safe_decimal(source.bonus_monthly),
                monthly_bonus=computed_monthly,
                trending=trending,
            )

        elif stype == IncomeSourceType.COMMISSION:
            data.commission = CommissionSection(
                year1_commission=year1 or None,
                year2_commission=year2 or None,
                ytd_commission=self._safe_decimal(source.commission_monthly),
                monthly_commission=computed_monthly,
                trending=trending,
                unreimbursed_expenses=None,  # Populated from source docs if available
            )

        elif stype == IncomeSourceType.SELF_EMPLOYMENT:
            data.self_employment = SelfEmploymentSection(
                business_name=source.employer_name or "",
                year1_net_profit=year1 or None,
                year2_net_profit=year2 or None,
                depreciation_addback=None,  # Not stored as separate column on IncomeSource
                amortization_addback=None,
                monthly_se=computed_monthly,
            )
            data.business_name = source.employer_name or ""

        elif stype == IncomeSourceType.RENTAL:
            rental = RentalSection(
                property_address=source.employer_name or "",  # employer_name used for address
                gross_rents=year1 or None,
                total_expenses=None,
                depreciation=None,
                net_rental=monthly * Decimal("12") if monthly else None,
                monthly_rental=computed_monthly,
            )
            if data.rental.monthly_rental is None:
                data.rental = rental
            else:
                data.additional_rental_sources.append(rental)

        elif stype == IncomeSourceType.SOCIAL_SECURITY:
            data.other_income.social_security = monthly or None
            data.other_income.monthly_other = (
                data.other_income.monthly_other or Decimal("0")
            ) + (computed_monthly or Decimal("0"))

        elif stype == IncomeSourceType.PENSION:
            data.other_income.pension = monthly or None
            data.other_income.monthly_other = (
                data.other_income.monthly_other or Decimal("0")
            ) + (computed_monthly or Decimal("0"))

        elif stype == IncomeSourceType.CHILD_SUPPORT:
            data.other_income.child_support = monthly or None
            data.other_income.monthly_other = (
                data.other_income.monthly_other or Decimal("0")
            ) + (computed_monthly or Decimal("0"))

        elif stype == IncomeSourceType.ALIMONY:
            data.other_income.alimony = monthly or None
            data.other_income.monthly_other = (
                data.other_income.monthly_other or Decimal("0")
            ) + (computed_monthly or Decimal("0"))

        else:
            # INVESTMENT, PART_TIME, MILITARY, DISABILITY, OTHER —
            # aggregate into other income.
            data.other_income.monthly_other = (
                data.other_income.monthly_other or Decimal("0")
            ) + (computed_monthly or Decimal("0"))
            if not data.other_income.monthly_other:
                data.other_income.monthly_other = None

        # Add declining-income flag if applicable
        if trending == TrendingDirection.DECLINING.value:
            data.flags.append(
                f"Declining income detected for {stype.value}: "
                f"Year 1=${year1 or 0:,.2f}, Year 2=${year2 or 0:,.2f}"
            )
            data.calculation_notes.append(
                f"Per B3-3.1-03: Used lower of 2 years for {stype.value} "
                f"due to declining trend."
            )

        return computed_monthly

    def _apply_averaging_rules(
        self,
        year1: Decimal,
        year2: Decimal,
        existing_monthly: Decimal,
        trending: str,
    ) -> Optional[Decimal]:
        """Apply Fannie Mae income averaging rules.

        Per Selling Guide B3-3.1-03:
        - Stable/increasing: use 2-year average
        - Declining: use the lower (most recent) year
        - Single year available: use that year

        Falls back to the pre-computed monthly from the IncomeSource if
        year-level data is not available.
        """
        if year1 and year2:
            if (
                trending == TrendingDirection.DECLINING.value
                or year1 < year2
            ):
                # Declining: use lower of the two years (which is year1, the
                # most recent, in a declining scenario)
                annual = min(year1, year2)
            else:
                # Stable or increasing: 2-year average
                annual = (year1 + year2) / Decimal("2")
            return (annual / Decimal("12")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        elif year1:
            return (year1 / Decimal("12")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        elif existing_monthly:
            return existing_monthly.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return None

    def _resolve_borrower_context(
        self,
        calc: IncomeCalculation,
        db: Session,
        data: Form1084Data,
    ) -> Form1084Data:
        """Attempt to resolve borrower name and loan number from related records.

        This is best-effort — if the related tables are unavailable or the
        foreign keys are null, we fall back to IDs.
        """
        try:
            # Resolve borrower name from leads table
            if calc.borrower_id:
                from database.models.lead_loan import Lead

                lead = (
                    db.query(Lead)
                    .filter(Lead.id == calc.borrower_id)
                    .first()
                )
                if lead:
                    parts = [
                        getattr(lead, "first_name", None) or "",
                        getattr(lead, "last_name", None) or "",
                    ]
                    data.borrower_name = " ".join(p for p in parts if p).strip()

            # Resolve loan number
            if calc.loan_id:
                from database.models.lead_loan import Loan

                loan = (
                    db.query(Loan)
                    .filter(Loan.id == calc.loan_id)
                    .first()
                )
                if loan:
                    data.loan_number = (
                        getattr(loan, "loan_number", None)
                        or str(loan.id)
                    )
        except Exception as e:
            logger.warning(
                "Could not resolve borrower/loan context: %s", e
            )

        return data

    # ==================================================================
    # INTERNAL — PDF via reportlab
    # ==================================================================

    def _generate_pdf_reportlab(self, data: Form1084Data) -> bytes:
        """Render Form 1084 as a professional PDF using reportlab.

        Layout:
          - Header with title and borrower identification
          - Table for each income section with Year1/Year2/YTD/Monthly columns
          - Total qualifying income summary row
          - Notes and flags
          - Footer with generation metadata
        """
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=letter,
            leftMargin=_MARGIN,
            rightMargin=_MARGIN,
            topMargin=_MARGIN,
            bottomMargin=_MARGIN,
        )

        styles = getSampleStyleSheet()
        elements: List[Any] = []

        # --- Custom styles ---
        title_style = ParagraphStyle(
            "Form1084Title",
            parent=styles["Title"],
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=4,
            textColor=colors.HexColor("#1a1a1a"),
        )
        subtitle_style = ParagraphStyle(
            "Form1084Subtitle",
            parent=styles["Normal"],
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#666666"),
            spaceAfter=16,
        )
        section_style = ParagraphStyle(
            "Form1084Section",
            parent=styles["Heading2"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#1e40af"),
            spaceBefore=12,
            spaceAfter=4,
        )
        normal_style = ParagraphStyle(
            "Form1084Normal",
            parent=styles["Normal"],
            fontSize=9,
            leading=11,
        )
        note_style = ParagraphStyle(
            "Form1084Note",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#555555"),
        )
        footer_style = ParagraphStyle(
            "Form1084Footer",
            parent=styles["Normal"],
            fontSize=8,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#999999"),
            spaceBefore=20,
        )

        # --- Title ---
        elements.append(
            Paragraph("Cash Flow Analysis &mdash; Form 1084", title_style)
        )
        elements.append(
            Paragraph(
                "Fannie Mae Selling Guide B3-3.1-03",
                subtitle_style,
            )
        )

        # --- Header info table ---
        generated_date = (
            data.generated_at.strftime("%B %d, %Y")
            if data.generated_at
            else datetime.now(timezone.utc).strftime("%B %d, %Y")
        )
        header_data = [
            ["Borrower:", data.borrower_name or "N/A",
             "Co-Borrower:", data.co_borrower_name or "N/A"],
            ["Loan #:", data.loan_number or "N/A",
             "Generated:", generated_date],
        ]
        header_table = Table(
            header_data,
            colWidths=[70, 170, 80, 170],
        )
        header_table.setStyle(
            TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#666666")),
                ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#666666")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafafa")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        elements.append(header_table)
        elements.append(Spacer(1, 12))

        # --- Income sections as tables ---
        col_widths = [
            _CONTENT_WIDTH * 0.40,
            _CONTENT_WIDTH * 0.15,
            _CONTENT_WIDTH * 0.15,
            _CONTENT_WIDTH * 0.15,
            _CONTENT_WIDTH * 0.15,
        ]
        table_header = ["Income Source", "Year 1", "Year 2", "YTD", "Monthly"]

        all_rows = [table_header]

        # Collect all income rows
        all_rows.extend(
            self._pdf_section_rows("W-2 Base Employment Income", data.w2_base)
        )
        for extra in data.additional_w2_sources:
            label = f"W-2 Base — {extra.employer_name or 'Additional'}"
            all_rows.extend(self._pdf_section_rows(label, extra))

        if data.overtime.monthly_ot is not None:
            all_rows.extend(
                self._pdf_income_rows("Overtime", data.overtime)
            )
        if data.bonus.monthly_bonus is not None:
            all_rows.extend(
                self._pdf_income_rows("Bonus", data.bonus)
            )
        if data.commission.monthly_commission is not None:
            all_rows.extend(
                self._pdf_income_rows("Commission", data.commission)
            )
        if data.self_employment.monthly_se is not None:
            all_rows.extend(
                self._pdf_se_rows(data.self_employment)
            )
        if data.partnership_scorp.monthly_k1 is not None:
            all_rows.extend(
                self._pdf_k1_rows(data.partnership_scorp)
            )

        rental_sections = [data.rental] + data.additional_rental_sources
        for r in rental_sections:
            if r.monthly_rental is not None:
                all_rows.extend(self._pdf_rental_rows(r))

        if data.other_income.monthly_other is not None:
            all_rows.extend(self._pdf_other_rows(data.other_income))

        # Total row
        all_rows.append([
            "TOTAL QUALIFYING MONTHLY INCOME",
            "",
            "",
            "",
            self._fmt(data.total_qualifying_monthly_income),
        ])

        income_table = Table(all_rows, colWidths=col_widths, repeatRows=1)
        income_table.setStyle(self._pdf_table_style(len(all_rows)))
        elements.append(income_table)

        # --- Notes ---
        if data.calculation_notes:
            elements.append(Spacer(1, 10))
            elements.append(Paragraph("Calculation Notes", section_style))
            for note in data.calculation_notes:
                elements.append(
                    Paragraph(f"&bull; {_escape_html(note)}", note_style)
                )

        # --- Flags ---
        if data.flags:
            elements.append(Spacer(1, 8))
            elements.append(Paragraph("Flags", section_style))
            for flag_item in data.flags:
                elements.append(
                    Paragraph(
                        f"&bull; {_escape_html(flag_item)}",
                        ParagraphStyle(
                            "FlagItem",
                            parent=note_style,
                            textColor=colors.HexColor("#991b1b"),
                        ),
                    )
                )

        # --- Footer ---
        elements.append(
            Paragraph(
                f"Generated by Perennia AI | {generated_date} "
                f"| Loan: {_escape_html(data.loan_number or 'N/A')}",
                footer_style,
            )
        )

        doc.build(elements)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # PDF helper — table style
    # ------------------------------------------------------------------

    def _pdf_table_style(self, row_count: int) -> TableStyle:
        """Build a TableStyle for the main income table."""
        style_commands = [
            # Header row
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (1, 0), (-1, 0), "RIGHT"),
            # Body
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#2563eb")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            # Grid lines
            ("LINEBELOW", (0, 1), (-1, -2), 0.5, colors.HexColor("#e5e7eb")),
            # Total row (last row)
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0fdf4")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, -1), (-1, -1), 10),
            ("LINEABOVE", (0, -1), (-1, -1), 2, colors.HexColor("#16a34a")),
            ("TEXTCOLOR", (-1, -1), (-1, -1), colors.HexColor("#16a34a")),
        ]

        # Highlight section-header rows (cells starting with specific markers)
        # We handle this by checking row content in _pdf_section_rows — they
        # return a sentinel that we can detect. Instead, we apply alternating
        # row shading for readability.
        for i in range(2, row_count - 1, 2):
            style_commands.append(
                ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f9fafb"))
            )

        return TableStyle(style_commands)

    # ------------------------------------------------------------------
    # PDF helper — section row builders
    # ------------------------------------------------------------------

    def _pdf_section_rows(
        self, label: str, section: W2BaseSection
    ) -> List[List[str]]:
        """Build table rows for a W-2 base section."""
        if section.monthly_base is None:
            return []
        rows = [
            [label, "", "", "", ""],  # Section header
            [
                "  Base Salary/Wages",
                self._fmt(section.year1_w2),
                self._fmt(section.year2_w2),
                self._fmt(section.ytd_base),
                self._fmt(section.monthly_base),
            ],
        ]
        return rows

    def _pdf_income_rows(
        self,
        label: str,
        section: Any,
    ) -> List[List[str]]:
        """Build generic income rows from overtime/bonus/commission sections."""
        year1 = getattr(section, f"year1_{label.lower()[:2]}", None) or getattr(
            section, f"year1_{label.lower()}", None
        )
        year2 = getattr(section, f"year2_{label.lower()[:2]}", None) or getattr(
            section, f"year2_{label.lower()}", None
        )
        ytd = getattr(section, f"ytd_{label.lower()[:2]}", None) or getattr(
            section, f"ytd_{label.lower()}", None
        )
        monthly = getattr(section, f"monthly_{label.lower()[:2]}", None) or getattr(
            section, f"monthly_{label.lower()}", None
        )
        trending = getattr(section, "trending", "")

        display_label = label
        if trending:
            display_label = f"{label} ({trending})"

        return [
            [
                display_label,
                self._fmt(year1),
                self._fmt(year2),
                self._fmt(ytd),
                self._fmt(monthly),
            ]
        ]

    def _pdf_se_rows(self, se: SelfEmploymentSection) -> List[List[str]]:
        """Build self-employment section rows."""
        rows = [
            [
                f"Self-Employment — {se.business_name or 'N/A'}",
                "",
                "",
                "",
                "",
            ],
            [
                "  Net Profit (Line 31)",
                self._fmt(se.year1_net_profit),
                self._fmt(se.year2_net_profit),
                "",
                "",
            ],
        ]
        if se.depreciation_addback:
            rows.append([
                "  Add: Depreciation",
                self._fmt(se.depreciation_addback),
                "",
                "",
                "",
            ])
        if se.amortization_addback:
            rows.append([
                "  Add: Amortization",
                self._fmt(se.amortization_addback),
                "",
                "",
                "",
            ])
        rows.append([
            "  Qualifying Monthly",
            "",
            "",
            "",
            self._fmt(se.monthly_se),
        ])
        return rows

    def _pdf_k1_rows(self, k1: PartnershipSCorpSection) -> List[List[str]]:
        """Build K-1 (partnership/S-Corp) section rows."""
        rows = [
            [
                f"Partnership/S-Corp — {k1.business_name or 'N/A'}",
                "",
                "",
                "",
                "",
            ],
            [
                "  Ordinary Income",
                self._fmt(k1.year1_ordinary),
                self._fmt(k1.year2_ordinary),
                "",
                "",
            ],
        ]
        if k1.guaranteed_payments:
            rows.append([
                "  Guaranteed Payments",
                self._fmt(k1.guaranteed_payments),
                "",
                "",
                "",
            ])
        rows.append([
            "  Qualifying Monthly",
            "",
            "",
            "",
            self._fmt(k1.monthly_k1),
        ])
        return rows

    def _pdf_rental_rows(self, r: RentalSection) -> List[List[str]]:
        """Build rental income (Schedule E) section rows."""
        rows = [
            [
                f"Rental — {r.property_address or 'N/A'}",
                "",
                "",
                "",
                "",
            ],
        ]
        if r.gross_rents:
            rows.append([
                "  Gross Rents",
                self._fmt(r.gross_rents),
                "",
                "",
                "",
            ])
        if r.total_expenses:
            rows.append([
                "  Less: Total Expenses",
                self._fmt(r.total_expenses),
                "",
                "",
                "",
            ])
        if r.depreciation:
            rows.append([
                "  Add: Depreciation",
                self._fmt(r.depreciation),
                "",
                "",
                "",
            ])
        rows.append([
            "  Qualifying Monthly Rental",
            "",
            "",
            "",
            self._fmt(r.monthly_rental),
        ])
        return rows

    def _pdf_other_rows(self, other: OtherIncomeSection) -> List[List[str]]:
        """Build other income section rows."""
        rows = [["Other Income", "", "", "", ""]]
        if other.social_security:
            rows.append([
                "  Social Security",
                self._fmt(other.social_security),
                "",
                "",
                "",
            ])
        if other.pension:
            rows.append([
                "  Pension/Retirement",
                self._fmt(other.pension),
                "",
                "",
                "",
            ])
        if other.child_support:
            rows.append([
                "  Child Support",
                self._fmt(other.child_support),
                "",
                "",
                "",
            ])
        if other.alimony:
            rows.append([
                "  Alimony",
                self._fmt(other.alimony),
                "",
                "",
                "",
            ])
        rows.append([
            "  Qualifying Monthly Other",
            "",
            "",
            "",
            self._fmt(other.monthly_other),
        ])
        return rows

    # ==================================================================
    # INTERNAL — HTML helpers
    # ==================================================================

    def _html_section_header(self, title: str) -> str:
        return (
            f'<tr class="section-header">'
            f"<td colspan=\"5\">{_escape_html(title)}</td></tr>\n"
        )

    def _html_income_row(
        self,
        label: str,
        year1: Optional[Decimal],
        year2: Optional[Decimal],
        ytd: Optional[Decimal],
        monthly: Optional[Decimal],
        trending: str = "",
    ) -> str:
        trending_badge = ""
        if trending:
            trending_badge = (
                f' <span class="trending {trending}">{trending}</span>'
            )
        return (
            f"<tr>"
            f"<td>{_escape_html(label)}{trending_badge}</td>"
            f'<td class="num">{self._fmt(year1)}</td>'
            f'<td class="num">{self._fmt(year2)}</td>'
            f'<td class="num">{self._fmt(ytd)}</td>'
            f'<td class="num">{self._fmt(monthly)}</td>'
            f"</tr>\n"
        )

    def _html_detail_row(
        self, label: str, value: Optional[Decimal]
    ) -> str:
        return (
            f'<tr class="detail">'
            f"<td>{_escape_html(label)}</td>"
            f"<td></td><td></td><td></td>"
            f'<td class="num">{self._fmt(value)}</td>'
            f"</tr>\n"
        )

    def _html_employer_info(self, section: W2BaseSection) -> str:
        parts = []
        if section.employer_name:
            parts.append(f"<span><b>Employer:</b> {_escape_html(section.employer_name)}</span>")
        if section.position_title:
            parts.append(f"<span><b>Position:</b> {_escape_html(section.position_title)}</span>")
        if section.employment_start_date:
            parts.append(f"<span><b>Start:</b> {_escape_html(section.employment_start_date)}</span>")
        if not parts:
            return ""
        return f'<tr><td colspan="5" class="employer-info">{"".join(parts)}</td></tr>\n'

    # ==================================================================
    # INTERNAL — formatting / utilities
    # ==================================================================

    @staticmethod
    def _fmt(value: Optional[Decimal]) -> str:
        """Format a Decimal as a dollar string, or empty if None/zero."""
        if value is None:
            return ""
        try:
            d = Decimal(str(value)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if d == 0:
                return ""
            # Format with comma separators and 2 decimal places
            sign = "-" if d < 0 else ""
            abs_val = abs(d)
            int_part = int(abs_val)
            dec_part = abs_val - int_part
            formatted_int = f"{int_part:,}"
            return f"{sign}${formatted_int}.{str(dec_part.quantize(Decimal('0.01')))[2:]}"
        except Exception as _exc:  # noqa: BLE001
            return ""

    @staticmethod
    def _safe_decimal(value: Any) -> Decimal:
        """Safely convert a value to Decimal, defaulting to 0."""
        if value is None:
            return Decimal("0")
        try:
            return Decimal(str(value))
        except Exception as _exc:  # noqa: BLE001
            return Decimal("0")


# ============================================================================
# MODULE-LEVEL UTILITIES
# ============================================================================

def _escape_html(text: str) -> str:
    """Minimal HTML escaping for safe rendering."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


# ============================================================================
# SINGLETON ACCESSOR
# ============================================================================

_form_1084_service: Optional[Form1084Service] = None


def get_form_1084_service() -> Form1084Service:
    """Get the singleton Form 1084 service instance."""
    global _form_1084_service
    if _form_1084_service is None:
        _form_1084_service = Form1084Service()
    return _form_1084_service
