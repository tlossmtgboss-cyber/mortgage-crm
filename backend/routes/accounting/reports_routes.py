"""
Financial Reports API Routes.

Provides endpoints for generating financial reports including:
- Profit & Loss (Income Statement)
- Balance Sheet
- Cash Flow Statement
- General Ledger
- Account Transaction History
- Budget vs Actual Variance
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_, or_, extract
from typing import Optional, List, Literal
from datetime import date, datetime, timedelta
from decimal import Decimal
from pydantic import BaseModel, Field
from enum import Enum
import calendar

from database import get_db
from models.accounting.core import (
    ChartOfAccounts, JournalEntry, JournalEntryLine,
    AccountingPeriod, AccountingSettings
)
from models.accounting.budgeting import BudgetTemplate, BudgetItem

# ============================================================================
# FEATURE TIER: EXPERIMENTAL
# This module is in the experimental tier -- frozen, no SLA.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================


def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/accounting/reports", tags=["Financial Reports"],
    dependencies=[Depends(_get_current_user())],
)


# =============================================================================
# Enums and Schemas
# =============================================================================

class ReportPeriod(str, Enum):
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    CUSTOM = "custom"


class ReportFormat(str, Enum):
    SUMMARY = "summary"
    DETAILED = "detailed"
    COMPARATIVE = "comparative"


# =============================================================================
# Helper Functions
# =============================================================================

def get_organization_id(request: Request) -> int:
    """Get organization ID from tenant context middleware."""
    org_id = getattr(request.state, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def get_period_dates(
    period: ReportPeriod,
    year: int,
    month: Optional[int] = None,
    quarter: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> tuple[date, date]:
    """Calculate start and end dates for a reporting period."""
    if period == ReportPeriod.CUSTOM:
        if not start_date or not end_date:
            raise ValueError("Custom period requires start_date and end_date")
        return start_date, end_date

    if period == ReportPeriod.MONTH:
        if not month:
            month = date.today().month
        start = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        end = date(year, month, last_day)

    elif period == ReportPeriod.QUARTER:
        if not quarter:
            quarter = (date.today().month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start = date(year, start_month, 1)
        end_month = start_month + 2
        _, last_day = calendar.monthrange(year, end_month)
        end = date(year, end_month, last_day)

    else:  # YEAR
        start = date(year, 1, 1)
        end = date(year, 12, 31)

    return start, end


def get_account_balance(
    db: Session,
    account_id: str,
    org_id: int,
    start_date: date,
    end_date: date,
    include_opening: bool = False,
) -> dict:
    """Get account balance for a period."""
    # Get account info
    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == account_id
    ).first()

    if not account:
        return {"debit": Decimal("0"), "credit": Decimal("0"), "balance": Decimal("0")}

    # Query posted journal entry lines
    query = db.query(
        func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label('total_debit'),
        func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label('total_credit'),
    ).join(
        JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
    ).filter(
        JournalEntryLine.account_id == account_id,
        JournalEntry.organization_id == org_id,
        JournalEntry.status == 'posted',
        JournalEntry.entry_date >= start_date,
        JournalEntry.entry_date <= end_date,
    )

    result = query.first()

    total_debit = Decimal(str(result.total_debit or 0))
    total_credit = Decimal(str(result.total_credit or 0))

    # Calculate balance based on account type
    # Assets and Expenses: Debit increases, Credit decreases
    # Liabilities, Equity, Revenue: Credit increases, Debit decreases
    if account.account_type in ('asset', 'expense'):
        balance = total_debit - total_credit
    else:
        balance = total_credit - total_debit

    return {
        "debit": total_debit,
        "credit": total_credit,
        "balance": balance,
    }


def get_opening_balance(
    db: Session,
    account_id: str,
    org_id: int,
    as_of_date: date,
) -> Decimal:
    """Get account balance as of a specific date (before that date)."""
    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == account_id
    ).first()

    if not account:
        return Decimal("0")

    result = db.query(
        func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label('total_debit'),
        func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label('total_credit'),
    ).join(
        JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
    ).filter(
        JournalEntryLine.account_id == account_id,
        JournalEntry.organization_id == org_id,
        JournalEntry.status == 'posted',
        JournalEntry.entry_date < as_of_date,
    ).first()

    total_debit = Decimal(str(result.total_debit or 0))
    total_credit = Decimal(str(result.total_credit or 0))

    if account.account_type in ('asset', 'expense'):
        return total_debit - total_credit
    else:
        return total_credit - total_debit


# =============================================================================
# Profit & Loss (Income Statement)
# =============================================================================

@router.get("/profit-loss")
async def get_profit_loss(
    request: Request,
    period: ReportPeriod = Query(ReportPeriod.MONTH),
    year: int = Query(default_factory=lambda: date.today().year),
    month: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    compare_prior: bool = Query(False, description="Include prior period comparison"),
    format: ReportFormat = Query(ReportFormat.SUMMARY),
    department_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Generate Profit & Loss (Income Statement) report.

    Shows revenue, expenses, and net income for the period.
    """
    org_id = get_organization_id(request)

    try:
        report_start, report_end = get_period_dates(
            period, year, month, quarter, start_date, end_date
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")

    # Get revenue accounts
    revenue_accounts = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.account_type == 'revenue',
        ChartOfAccounts.is_active == True,
    ).order_by(ChartOfAccounts.account_number).all()

    # Get expense accounts
    expense_accounts = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.account_type.in_(['expense', 'cost_of_goods']),
        ChartOfAccounts.is_active == True,
    ).order_by(ChartOfAccounts.account_number).all()

    # Build department filter if provided
    dept_filter = []
    if department_id:
        dept_filter = [JournalEntryLine.department_id == department_id]

    # Calculate revenue
    revenue_lines = []
    total_revenue = Decimal("0")

    for account in revenue_accounts:
        result = db.query(
            func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label('credits'),
            func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label('debits'),
        ).join(
            JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
        ).filter(
            JournalEntryLine.account_id == account.id,
            JournalEntry.organization_id == org_id,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date >= report_start,
            JournalEntry.entry_date <= report_end,
            *dept_filter,
        ).first()

        # Revenue is credit - debit
        amount = Decimal(str(result.credits or 0)) - Decimal(str(result.debits or 0))

        if amount != 0 or format == ReportFormat.DETAILED:
            revenue_lines.append({
                "account_id": str(account.id),
                "account_number": account.account_number,
                "account_name": account.name,
                "amount": float(amount),
            })
            total_revenue += amount

    # Calculate expenses (including COGS)
    cogs_lines = []
    expense_lines = []
    total_cogs = Decimal("0")
    total_expenses = Decimal("0")

    for account in expense_accounts:
        result = db.query(
            func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label('debits'),
            func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label('credits'),
        ).join(
            JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
        ).filter(
            JournalEntryLine.account_id == account.id,
            JournalEntry.organization_id == org_id,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date >= report_start,
            JournalEntry.entry_date <= report_end,
            *dept_filter,
        ).first()

        # Expenses are debit - credit
        amount = Decimal(str(result.debits or 0)) - Decimal(str(result.credits or 0))

        if amount != 0 or format == ReportFormat.DETAILED:
            line_data = {
                "account_id": str(account.id),
                "account_number": account.account_number,
                "account_name": account.name,
                "amount": float(amount),
            }

            if account.account_type == 'cost_of_goods':
                cogs_lines.append(line_data)
                total_cogs += amount
            else:
                expense_lines.append(line_data)
                total_expenses += amount

    gross_profit = total_revenue - total_cogs
    net_income = gross_profit - total_expenses

    report = {
        "success": True,
        "report_type": "profit_loss",
        "period": {
            "type": period.value,
            "start_date": report_start.isoformat(),
            "end_date": report_end.isoformat(),
        },
        "revenue": {
            "lines": revenue_lines,
            "total": float(total_revenue),
        },
        "cost_of_goods_sold": {
            "lines": cogs_lines,
            "total": float(total_cogs),
        },
        "gross_profit": float(gross_profit),
        "gross_margin_percent": round(float(gross_profit / total_revenue * 100), 2) if total_revenue > 0 else 0,
        "operating_expenses": {
            "lines": expense_lines,
            "total": float(total_expenses),
        },
        "net_income": float(net_income),
        "net_margin_percent": round(float(net_income / total_revenue * 100), 2) if total_revenue > 0 else 0,
    }

    # Add prior period comparison if requested
    if compare_prior:
        # Calculate prior period dates
        if period == ReportPeriod.MONTH:
            if report_start.month == 1:
                prior_start = date(report_start.year - 1, 12, 1)
            else:
                prior_start = date(report_start.year, report_start.month - 1, 1)
            _, last_day = calendar.monthrange(prior_start.year, prior_start.month)
            prior_end = date(prior_start.year, prior_start.month, last_day)
        elif period == ReportPeriod.QUARTER:
            prior_start = date(report_start.year - 1, report_start.month, 1) if report_start.month <= 3 else date(report_start.year, report_start.month - 3, 1)
            prior_end = date(report_end.year - 1, report_end.month, report_end.day) if report_end.month <= 3 else date(report_end.year, report_end.month - 3, report_end.day)
        else:
            prior_start = date(report_start.year - 1, 1, 1)
            prior_end = date(report_start.year - 1, 12, 31)

        # Get prior period totals (simplified)
        prior_revenue = db.query(
            func.coalesce(func.sum(JournalEntryLine.credit_amount - JournalEntryLine.debit_amount), 0)
        ).join(JournalEntry).join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id).filter(
            ChartOfAccounts.account_type == 'revenue',
            JournalEntry.organization_id == org_id,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date >= prior_start,
            JournalEntry.entry_date <= prior_end,
        ).scalar() or Decimal("0")

        prior_expenses = db.query(
            func.coalesce(func.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount), 0)
        ).join(JournalEntry).join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id).filter(
            ChartOfAccounts.account_type.in_(['expense', 'cost_of_goods']),
            JournalEntry.organization_id == org_id,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date >= prior_start,
            JournalEntry.entry_date <= prior_end,
        ).scalar() or Decimal("0")

        prior_net = float(prior_revenue) - float(prior_expenses)

        report["prior_period"] = {
            "start_date": prior_start.isoformat(),
            "end_date": prior_end.isoformat(),
            "revenue": float(prior_revenue),
            "expenses": float(prior_expenses),
            "net_income": prior_net,
        }

        report["variance"] = {
            "revenue": float(total_revenue) - float(prior_revenue),
            "revenue_percent": round((float(total_revenue) - float(prior_revenue)) / float(prior_revenue) * 100, 2) if prior_revenue > 0 else 0,
            "net_income": float(net_income) - prior_net,
            "net_income_percent": round((float(net_income) - prior_net) / abs(prior_net) * 100, 2) if prior_net != 0 else 0,
        }

    return report


# =============================================================================
# Balance Sheet
# =============================================================================

@router.get("/balance-sheet")
async def get_balance_sheet(
    request: Request,
    as_of_date: Optional[date] = Query(None, description="Balance sheet date"),
    compare_prior: bool = Query(False, description="Include prior period comparison"),
    format: ReportFormat = Query(ReportFormat.SUMMARY),
    db: Session = Depends(get_db),
):
    """
    Generate Balance Sheet report.

    Shows assets, liabilities, and equity as of a specific date.
    """
    org_id = get_organization_id(request)
    report_date = as_of_date or date.today()

    # Function to get account balances by type
    def get_type_balances(account_type: str, sub_types: List[str] = None):
        query = db.query(ChartOfAccounts).filter(
            ChartOfAccounts.organization_id == org_id,
            ChartOfAccounts.account_type == account_type,
            ChartOfAccounts.is_active == True,
        )

        if sub_types:
            query = query.filter(ChartOfAccounts.account_sub_type.in_(sub_types))

        accounts = query.order_by(ChartOfAccounts.account_number).all()

        lines = []
        total = Decimal("0")

        for account in accounts:
            # Get all-time balance up to report date
            result = db.query(
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label('debits'),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label('credits'),
            ).join(JournalEntry).filter(
                JournalEntryLine.account_id == account.id,
                JournalEntry.organization_id == org_id,
                JournalEntry.status == 'posted',
                JournalEntry.entry_date <= report_date,
            ).first()

            debits = Decimal(str(result.debits or 0))
            credits = Decimal(str(result.credits or 0))

            # Balance depends on account type
            if account_type == 'asset':
                balance = debits - credits
            else:  # liability, equity
                balance = credits - debits

            if balance != 0 or format == ReportFormat.DETAILED:
                lines.append({
                    "account_id": str(account.id),
                    "account_number": account.account_number,
                    "account_name": account.name,
                    "sub_type": account.account_sub_type,
                    "balance": float(balance),
                })
                total += balance

        return lines, total

    # Get Assets
    current_assets, total_current_assets = get_type_balances(
        'asset', ['cash', 'accounts_receivable', 'inventory', 'prepaid', 'other_current']
    )
    fixed_assets, total_fixed_assets = get_type_balances(
        'asset', ['fixed_asset', 'accumulated_depreciation', 'intangible', 'other_asset']
    )

    # If no sub_types matched, get all assets
    if not current_assets and not fixed_assets:
        all_assets, total_assets = get_type_balances('asset')
        current_assets = all_assets
        total_current_assets = total_assets
        total_fixed_assets = Decimal("0")

    total_assets = total_current_assets + total_fixed_assets

    # Get Liabilities
    current_liabilities, total_current_liabilities = get_type_balances(
        'liability', ['accounts_payable', 'accrued', 'short_term_debt', 'other_current_liability']
    )
    long_term_liabilities, total_long_term_liabilities = get_type_balances(
        'liability', ['long_term_debt', 'deferred', 'other_liability']
    )

    if not current_liabilities and not long_term_liabilities:
        all_liabilities, total_liabilities = get_type_balances('liability')
        current_liabilities = all_liabilities
        total_current_liabilities = total_liabilities
        total_long_term_liabilities = Decimal("0")

    total_liabilities = total_current_liabilities + total_long_term_liabilities

    # Get Equity
    equity_lines, total_equity_accounts = get_type_balances('equity')

    # Calculate retained earnings (Revenue - Expenses for all time)
    ytd_revenue = db.query(
        func.coalesce(func.sum(JournalEntryLine.credit_amount - JournalEntryLine.debit_amount), 0)
    ).join(JournalEntry).join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id).filter(
        ChartOfAccounts.account_type == 'revenue',
        JournalEntry.organization_id == org_id,
        JournalEntry.status == 'posted',
        JournalEntry.entry_date <= report_date,
    ).scalar() or Decimal("0")

    ytd_expenses = db.query(
        func.coalesce(func.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount), 0)
    ).join(JournalEntry).join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id).filter(
        ChartOfAccounts.account_type.in_(['expense', 'cost_of_goods']),
        JournalEntry.organization_id == org_id,
        JournalEntry.status == 'posted',
        JournalEntry.entry_date <= report_date,
    ).scalar() or Decimal("0")

    retained_earnings = Decimal(str(ytd_revenue)) - Decimal(str(ytd_expenses))
    total_equity = total_equity_accounts + retained_earnings

    report = {
        "success": True,
        "report_type": "balance_sheet",
        "as_of_date": report_date.isoformat(),
        "assets": {
            "current_assets": {
                "lines": current_assets,
                "total": float(total_current_assets),
            },
            "fixed_assets": {
                "lines": fixed_assets,
                "total": float(total_fixed_assets),
            },
            "total_assets": float(total_assets),
        },
        "liabilities": {
            "current_liabilities": {
                "lines": current_liabilities,
                "total": float(total_current_liabilities),
            },
            "long_term_liabilities": {
                "lines": long_term_liabilities,
                "total": float(total_long_term_liabilities),
            },
            "total_liabilities": float(total_liabilities),
        },
        "equity": {
            "lines": equity_lines,
            "retained_earnings": float(retained_earnings),
            "total_equity": float(total_equity),
        },
        "total_liabilities_and_equity": float(total_liabilities + total_equity),
        "balanced": abs(float(total_assets) - float(total_liabilities + total_equity)) < 0.01,
    }

    return report


# =============================================================================
# Cash Flow Statement
# =============================================================================

@router.get("/cash-flow")
async def get_cash_flow(
    request: Request,
    period: ReportPeriod = Query(ReportPeriod.MONTH),
    year: int = Query(default_factory=lambda: date.today().year),
    month: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    method: Literal["direct", "indirect"] = Query("indirect"),
    db: Session = Depends(get_db),
):
    """
    Generate Cash Flow Statement.

    Shows cash flows from operating, investing, and financing activities.
    """
    org_id = get_organization_id(request)

    try:
        report_start, report_end = get_period_dates(
            period, year, month, quarter, start_date, end_date
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")

    # Get cash accounts
    cash_accounts = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.account_sub_type == 'cash',
        ChartOfAccounts.is_active == True,
    ).all()

    cash_account_ids = [str(a.id) for a in cash_accounts]

    # Calculate opening and closing cash
    opening_cash = Decimal("0")
    closing_cash = Decimal("0")

    for account in cash_accounts:
        opening_cash += get_opening_balance(db, str(account.id), org_id, report_start)
        closing_cash += get_opening_balance(db, str(account.id), org_id, report_end + timedelta(days=1))

    net_change_in_cash = closing_cash - opening_cash

    if method == "indirect":
        # Indirect method - start with net income and adjust

        # Net Income
        revenue = db.query(
            func.coalesce(func.sum(JournalEntryLine.credit_amount - JournalEntryLine.debit_amount), 0)
        ).join(JournalEntry).join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id).filter(
            ChartOfAccounts.account_type == 'revenue',
            JournalEntry.organization_id == org_id,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date >= report_start,
            JournalEntry.entry_date <= report_end,
        ).scalar() or Decimal("0")

        expenses = db.query(
            func.coalesce(func.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount), 0)
        ).join(JournalEntry).join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id).filter(
            ChartOfAccounts.account_type.in_(['expense', 'cost_of_goods']),
            JournalEntry.organization_id == org_id,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date >= report_start,
            JournalEntry.entry_date <= report_end,
        ).scalar() or Decimal("0")

        net_income = Decimal(str(revenue)) - Decimal(str(expenses))

        # Get changes in working capital accounts
        def get_account_change(sub_type: str) -> Decimal:
            accounts = db.query(ChartOfAccounts).filter(
                ChartOfAccounts.organization_id == org_id,
                ChartOfAccounts.account_sub_type == sub_type,
            ).all()

            total_change = Decimal("0")
            for account in accounts:
                opening = get_opening_balance(db, str(account.id), org_id, report_start)
                closing = get_opening_balance(db, str(account.id), org_id, report_end + timedelta(days=1))
                total_change += closing - opening

            return total_change

        # Operating activities adjustments
        ar_change = get_account_change('accounts_receivable')
        inventory_change = get_account_change('inventory')
        prepaid_change = get_account_change('prepaid')
        ap_change = get_account_change('accounts_payable')
        accrued_change = get_account_change('accrued')

        # Depreciation (add back non-cash expense)
        depreciation = db.query(
            func.coalesce(func.sum(JournalEntryLine.debit_amount), 0)
        ).join(JournalEntry).join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id).filter(
            ChartOfAccounts.account_sub_type == 'accumulated_depreciation',
            JournalEntry.organization_id == org_id,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date >= report_start,
            JournalEntry.entry_date <= report_end,
        ).scalar() or Decimal("0")

        operating_adjustments = [
            {"description": "Depreciation & Amortization", "amount": float(depreciation)},
            {"description": "Decrease (Increase) in Accounts Receivable", "amount": float(-ar_change)},
            {"description": "Decrease (Increase) in Inventory", "amount": float(-inventory_change)},
            {"description": "Decrease (Increase) in Prepaid Expenses", "amount": float(-prepaid_change)},
            {"description": "Increase (Decrease) in Accounts Payable", "amount": float(ap_change)},
            {"description": "Increase (Decrease) in Accrued Liabilities", "amount": float(accrued_change)},
        ]

        total_operating_adjustments = sum(adj["amount"] for adj in operating_adjustments)
        cash_from_operations = float(net_income) + total_operating_adjustments

        # Investing activities (changes in fixed assets)
        fixed_asset_change = get_account_change('fixed_asset')

        investing_items = [
            {"description": "Purchase of Property & Equipment", "amount": float(-fixed_asset_change) if fixed_asset_change > 0 else 0},
            {"description": "Sale of Property & Equipment", "amount": float(-fixed_asset_change) if fixed_asset_change < 0 else 0},
        ]
        cash_from_investing = sum(item["amount"] for item in investing_items)

        # Financing activities
        debt_change = get_account_change('long_term_debt') + get_account_change('short_term_debt')
        equity_change = Decimal("0")  # Would need to track equity transactions separately

        financing_items = [
            {"description": "Proceeds from Debt", "amount": float(debt_change) if debt_change > 0 else 0},
            {"description": "Repayment of Debt", "amount": float(debt_change) if debt_change < 0 else 0},
        ]
        cash_from_financing = sum(item["amount"] for item in financing_items)

        report = {
            "success": True,
            "report_type": "cash_flow",
            "method": "indirect",
            "period": {
                "start_date": report_start.isoformat(),
                "end_date": report_end.isoformat(),
            },
            "operating_activities": {
                "net_income": float(net_income),
                "adjustments": operating_adjustments,
                "total_adjustments": total_operating_adjustments,
                "cash_from_operations": cash_from_operations,
            },
            "investing_activities": {
                "items": [i for i in investing_items if i["amount"] != 0],
                "cash_from_investing": cash_from_investing,
            },
            "financing_activities": {
                "items": [i for i in financing_items if i["amount"] != 0],
                "cash_from_financing": cash_from_financing,
            },
            "summary": {
                "net_change_in_cash": float(net_change_in_cash),
                "opening_cash": float(opening_cash),
                "closing_cash": float(closing_cash),
                "calculated_change": cash_from_operations + cash_from_investing + cash_from_financing,
            },
        }

    else:
        # Direct method - show actual cash receipts and payments
        # Get all transactions affecting cash accounts

        cash_transactions = db.query(
            JournalEntryLine,
            JournalEntry,
            ChartOfAccounts,
        ).join(
            JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
        ).join(
            ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id
        ).filter(
            JournalEntryLine.account_id.in_(cash_account_ids),
            JournalEntry.organization_id == org_id,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date >= report_start,
            JournalEntry.entry_date <= report_end,
        ).all()

        # Categorize by source
        operating_receipts = Decimal("0")
        operating_payments = Decimal("0")

        for line, entry, account in cash_transactions:
            cash_in = line.debit_amount or Decimal("0")
            cash_out = line.credit_amount or Decimal("0")

            # Simplified categorization based on entry source
            if entry.source in ('ar_payment', 'revenue'):
                operating_receipts += cash_in
            elif entry.source in ('ap_payment', 'expense'):
                operating_payments += cash_out

        report = {
            "success": True,
            "report_type": "cash_flow",
            "method": "direct",
            "period": {
                "start_date": report_start.isoformat(),
                "end_date": report_end.isoformat(),
            },
            "operating_activities": {
                "cash_receipts": float(operating_receipts),
                "cash_payments": float(operating_payments),
                "cash_from_operations": float(operating_receipts - operating_payments),
            },
            "summary": {
                "net_change_in_cash": float(net_change_in_cash),
                "opening_cash": float(opening_cash),
                "closing_cash": float(closing_cash),
            },
        }

    return report


# =============================================================================
# General Ledger
# =============================================================================

@router.get("/general-ledger")
async def get_general_ledger(
    request: Request,
    account_id: Optional[str] = Query(None, description="Filter by account"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Get General Ledger transactions.

    Shows all posted journal entry lines with running balances.
    """
    org_id = get_organization_id(request)

    report_start = start_date or date(date.today().year, 1, 1)
    report_end = end_date or date.today()

    query = db.query(
        JournalEntryLine,
        JournalEntry,
        ChartOfAccounts,
    ).join(
        JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
    ).join(
        ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id
    ).filter(
        JournalEntry.organization_id == org_id,
        JournalEntry.status == 'posted',
        JournalEntry.entry_date >= report_start,
        JournalEntry.entry_date <= report_end,
    )

    if account_id:
        query = query.filter(JournalEntryLine.account_id == account_id)

    query = query.order_by(JournalEntry.entry_date, JournalEntry.id, JournalEntryLine.line_number)

    total = query.count()
    results = query.offset(skip).limit(limit).all()

    # Calculate running balances if single account
    entries = []
    running_balance = Decimal("0")

    if account_id:
        # Get opening balance
        running_balance = get_opening_balance(db, account_id, org_id, report_start)
        account = db.query(ChartOfAccounts).filter(ChartOfAccounts.id == account_id).first()
        is_debit_account = account.account_type in ('asset', 'expense') if account else True

    for line, entry, account in results:
        debit = line.debit_amount or Decimal("0")
        credit = line.credit_amount or Decimal("0")

        if account_id:
            if is_debit_account:
                running_balance += debit - credit
            else:
                running_balance += credit - debit

        entries.append({
            "entry_id": str(entry.id),
            "entry_number": entry.entry_number,
            "entry_date": entry.entry_date.isoformat(),
            "description": entry.description,
            "line_description": line.description,
            "account_id": str(account.id),
            "account_number": account.account_number,
            "account_name": account.name,
            "debit": float(debit),
            "credit": float(credit),
            "running_balance": float(running_balance) if account_id else None,
        })

    return {
        "success": True,
        "period": {
            "start_date": report_start.isoformat(),
            "end_date": report_end.isoformat(),
        },
        "total": total,
        "opening_balance": float(get_opening_balance(db, account_id, org_id, report_start)) if account_id else None,
        "entries": entries,
    }


# =============================================================================
# Account Transaction History
# =============================================================================

@router.get("/account-history/{account_id}")
async def get_account_history(
    request: Request,
    account_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Get transaction history for a specific account.
    """
    org_id = get_organization_id(request)

    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == account_id,
        ChartOfAccounts.organization_id == org_id,
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    report_start = start_date or date(date.today().year, 1, 1)
    report_end = end_date or date.today()

    # Get opening balance
    opening_balance = get_opening_balance(db, account_id, org_id, report_start)

    # Get transactions
    transactions = db.query(JournalEntryLine, JournalEntry).join(
        JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
    ).filter(
        JournalEntryLine.account_id == account_id,
        JournalEntry.organization_id == org_id,
        JournalEntry.status == 'posted',
        JournalEntry.entry_date >= report_start,
        JournalEntry.entry_date <= report_end,
    ).order_by(
        JournalEntry.entry_date, JournalEntry.id
    ).offset(skip).limit(limit).all()

    is_debit_account = account.account_type in ('asset', 'expense')
    running_balance = opening_balance

    entries = []
    for line, entry in transactions:
        debit = line.debit_amount or Decimal("0")
        credit = line.credit_amount or Decimal("0")

        if is_debit_account:
            running_balance += debit - credit
        else:
            running_balance += credit - debit

        entries.append({
            "date": entry.entry_date.isoformat(),
            "entry_number": entry.entry_number,
            "description": line.description or entry.description,
            "debit": float(debit),
            "credit": float(credit),
            "balance": float(running_balance),
            "source": entry.source,
        })

    # Get period totals
    totals = db.query(
        func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label('total_debit'),
        func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label('total_credit'),
    ).join(JournalEntry).filter(
        JournalEntryLine.account_id == account_id,
        JournalEntry.organization_id == org_id,
        JournalEntry.status == 'posted',
        JournalEntry.entry_date >= report_start,
        JournalEntry.entry_date <= report_end,
    ).first()

    return {
        "success": True,
        "account": {
            "id": str(account.id),
            "account_number": account.account_number,
            "name": account.name,
            "type": account.account_type,
        },
        "period": {
            "start_date": report_start.isoformat(),
            "end_date": report_end.isoformat(),
        },
        "opening_balance": float(opening_balance),
        "total_debits": float(totals.total_debit),
        "total_credits": float(totals.total_credit),
        "closing_balance": float(running_balance),
        "transactions": entries,
    }


# =============================================================================
# Budget vs Actual Variance
# =============================================================================

@router.get("/budget-variance")
async def get_budget_variance(
    request: Request,
    budget_id: str = Query(..., description="Budget template ID"),
    through_period: int = Query(None, ge=1, le=12, description="Through period number"),
    db: Session = Depends(get_db),
):
    """
    Get Budget vs Actual variance report.
    """
    org_id = get_organization_id(request)

    budget = db.query(BudgetTemplate).filter(
        BudgetTemplate.id == budget_id,
        BudgetTemplate.organization_id == org_id,
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    # Determine periods to include
    if through_period is None:
        through_period = date.today().month

    # Get date range for actual figures
    fiscal_year = budget.fiscal_year
    report_start = date(fiscal_year, 1, 1)
    report_end = date(fiscal_year, through_period, calendar.monthrange(fiscal_year, through_period)[1])

    # Get budget items with actuals
    items = db.query(BudgetItem).filter(
        BudgetItem.budget_id == budget_id,
    ).all()

    variance_lines = []
    total_budget = Decimal("0")
    total_actual = Decimal("0")

    for item in items:
        # Get YTD budget
        ytd_budget = item.get_ytd_budget(through_period)

        # Get actual for this account
        account = item.account
        if not account:
            continue

        result = db.query(
            func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label('debits'),
            func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label('credits'),
        ).join(JournalEntry).filter(
            JournalEntryLine.account_id == item.account_id,
            JournalEntry.organization_id == org_id,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date >= report_start,
            JournalEntry.entry_date <= report_end,
        ).first()

        debits = Decimal(str(result.debits or 0))
        credits = Decimal(str(result.credits or 0))

        # Calculate actual based on account type
        if account.account_type == 'revenue':
            actual = credits - debits
        else:  # expense
            actual = debits - credits

        variance = actual - ytd_budget
        variance_pct = (variance / ytd_budget * 100) if ytd_budget != 0 else Decimal("0")

        # Determine if favorable or unfavorable
        # For revenue: positive variance is favorable
        # For expense: negative variance is favorable
        if account.account_type == 'revenue':
            is_favorable = variance >= 0
        else:
            is_favorable = variance <= 0

        variance_lines.append({
            "account_id": str(account.id),
            "account_number": account.account_number,
            "account_name": account.name,
            "account_type": account.account_type,
            "budget": float(ytd_budget),
            "actual": float(actual),
            "variance": float(variance),
            "variance_percent": round(float(variance_pct), 2),
            "is_favorable": is_favorable,
        })

        total_budget += ytd_budget
        total_actual += actual

    # Separate revenue and expenses
    revenue_lines = [l for l in variance_lines if l["account_type"] == "revenue"]
    expense_lines = [l for l in variance_lines if l["account_type"] in ("expense", "cost_of_goods")]

    total_revenue_budget = sum(l["budget"] for l in revenue_lines)
    total_revenue_actual = sum(l["actual"] for l in revenue_lines)
    total_expense_budget = sum(l["budget"] for l in expense_lines)
    total_expense_actual = sum(l["actual"] for l in expense_lines)

    return {
        "success": True,
        "budget": {
            "id": str(budget.id),
            "name": budget.name,
            "fiscal_year": budget.fiscal_year,
        },
        "period": {
            "through_period": through_period,
            "start_date": report_start.isoformat(),
            "end_date": report_end.isoformat(),
        },
        "revenue": {
            "lines": sorted(revenue_lines, key=lambda x: x["account_number"]),
            "budget": total_revenue_budget,
            "actual": total_revenue_actual,
            "variance": total_revenue_actual - total_revenue_budget,
        },
        "expenses": {
            "lines": sorted(expense_lines, key=lambda x: x["account_number"]),
            "budget": total_expense_budget,
            "actual": total_expense_actual,
            "variance": total_expense_actual - total_expense_budget,
        },
        "net_income": {
            "budget": total_revenue_budget - total_expense_budget,
            "actual": total_revenue_actual - total_expense_actual,
            "variance": (total_revenue_actual - total_expense_actual) - (total_revenue_budget - total_expense_budget),
        },
    }


# =============================================================================
# Financial Ratios
# =============================================================================

@router.get("/financial-ratios")
async def get_financial_ratios(
    request: Request,
    as_of_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Calculate key financial ratios.
    """
    org_id = get_organization_id(request)
    report_date = as_of_date or date.today()
    year_start = date(report_date.year, 1, 1)

    # Helper to get balance for account sub-type
    def get_subtype_balance(sub_type: str) -> Decimal:
        result = db.query(
            func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label('debits'),
            func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label('credits'),
        ).join(JournalEntry).join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id).filter(
            ChartOfAccounts.organization_id == org_id,
            ChartOfAccounts.account_sub_type == sub_type,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date <= report_date,
        ).first()

        return Decimal(str(result.debits or 0)) - Decimal(str(result.credits or 0))

    def get_type_balance(account_type: str) -> Decimal:
        result = db.query(
            func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label('debits'),
            func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label('credits'),
        ).join(JournalEntry).join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id).filter(
            ChartOfAccounts.organization_id == org_id,
            ChartOfAccounts.account_type == account_type,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date <= report_date,
        ).first()

        debits = Decimal(str(result.debits or 0))
        credits = Decimal(str(result.credits or 0))

        if account_type in ('asset', 'expense'):
            return debits - credits
        return credits - debits

    # Get key balances
    cash = get_subtype_balance('cash')
    ar = get_subtype_balance('accounts_receivable')
    inventory = get_subtype_balance('inventory')
    current_assets = cash + ar + inventory + get_subtype_balance('prepaid')
    total_assets = get_type_balance('asset')

    ap = abs(get_subtype_balance('accounts_payable'))  # AP is credit balance
    current_liabilities = ap + abs(get_subtype_balance('accrued'))
    total_liabilities = abs(get_type_balance('liability'))
    total_equity = abs(get_type_balance('equity'))

    # YTD Income Statement
    ytd_revenue = db.query(
        func.coalesce(func.sum(JournalEntryLine.credit_amount - JournalEntryLine.debit_amount), 0)
    ).join(JournalEntry).join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id).filter(
        ChartOfAccounts.account_type == 'revenue',
        JournalEntry.organization_id == org_id,
        JournalEntry.status == 'posted',
        JournalEntry.entry_date >= year_start,
        JournalEntry.entry_date <= report_date,
    ).scalar() or Decimal("0")

    ytd_expenses = db.query(
        func.coalesce(func.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount), 0)
    ).join(JournalEntry).join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id).filter(
        ChartOfAccounts.account_type.in_(['expense', 'cost_of_goods']),
        JournalEntry.organization_id == org_id,
        JournalEntry.status == 'posted',
        JournalEntry.entry_date >= year_start,
        JournalEntry.entry_date <= report_date,
    ).scalar() or Decimal("0")

    net_income = Decimal(str(ytd_revenue)) - Decimal(str(ytd_expenses))

    # Calculate ratios
    def safe_ratio(numerator, denominator, multiplier=1):
        if denominator == 0:
            return None
        return round(float(numerator / denominator * multiplier), 2)

    ratios = {
        "liquidity": {
            "current_ratio": safe_ratio(current_assets, current_liabilities),
            "quick_ratio": safe_ratio(cash + ar, current_liabilities),
            "cash_ratio": safe_ratio(cash, current_liabilities),
        },
        "leverage": {
            "debt_to_equity": safe_ratio(total_liabilities, total_equity),
            "debt_to_assets": safe_ratio(total_liabilities, total_assets),
            "equity_ratio": safe_ratio(total_equity, total_assets),
        },
        "profitability": {
            "gross_margin": None,  # Would need COGS breakdown
            "net_profit_margin": safe_ratio(net_income, ytd_revenue, 100),
            "return_on_assets": safe_ratio(net_income, total_assets, 100),
            "return_on_equity": safe_ratio(net_income, total_equity, 100),
        },
        "efficiency": {
            "asset_turnover": safe_ratio(ytd_revenue, total_assets),
            "receivables_turnover": safe_ratio(ytd_revenue, ar),
            "days_sales_outstanding": safe_ratio(ar * 365, ytd_revenue) if ytd_revenue > 0 else None,
        },
    }

    return {
        "success": True,
        "as_of_date": report_date.isoformat(),
        "balances": {
            "cash": float(cash),
            "accounts_receivable": float(ar),
            "current_assets": float(current_assets),
            "total_assets": float(total_assets),
            "current_liabilities": float(current_liabilities),
            "total_liabilities": float(total_liabilities),
            "total_equity": float(total_equity),
            "ytd_revenue": float(ytd_revenue),
            "ytd_net_income": float(net_income),
        },
        "ratios": ratios,
    }


# =============================================================================
# Report Export
# =============================================================================

@router.get("/export/{report_type}")
async def export_report(
    request: Request,
    report_type: Literal["profit-loss", "balance-sheet", "cash-flow", "trial-balance"],
    format: Literal["json", "csv"] = Query("json"),
    period: ReportPeriod = Query(ReportPeriod.MONTH),
    year: int = Query(default_factory=lambda: date.today().year),
    month: Optional[int] = Query(None),
    as_of_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Export financial report in specified format.
    """
    # Generate the base report
    if report_type == "profit-loss":
        report = await get_profit_loss(
            request=request, period=period, year=year, month=month,
            format=ReportFormat.DETAILED, db=db
        )
    elif report_type == "balance-sheet":
        report = await get_balance_sheet(
            request=request, as_of_date=as_of_date, format=ReportFormat.DETAILED, db=db
        )
    elif report_type == "cash-flow":
        report = await get_cash_flow(
            request=request, period=period, year=year, month=month, db=db
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid report type")

    if format == "json":
        return report

    # CSV export would be handled differently - returning structured data for now
    return {
        "success": True,
        "format": format,
        "message": "CSV export would be generated here",
        "data": report,
    }
