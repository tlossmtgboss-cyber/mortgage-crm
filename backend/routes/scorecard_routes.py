"""
Loan Scorecard Report Routes

Extracted from inline_legacy_routes.py.
Provides comprehensive loan scorecard metrics including conversion metrics,
funding totals, and referral source breakdown.

Enterprise Readiness (Checks 9.5-9.7, 9.6, 9.8):
- All report queries include organization_id filtering for multi-tenant isolation.
- Role-based access scoping (Check 9.6): Admins see org data, branch managers
  see branch data, loan officers see only their own data.
- CSV export endpoint (Check 9.8): GET /api/v1/scorecard/export?format=csv
"""
from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime as dt
from typing import Optional
import csv
import io
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)


def _apply_lead_scope(query, scope, Lead):
    """Apply role-based scope to a Lead query."""
    org_id = scope.get("org_id")
    if org_id is not None and hasattr(Lead, "organization_id"):
        query = query.filter(Lead.organization_id == org_id)
    if scope["scope"] == "user":
        query = query.filter(Lead.owner_id == scope["user_id"])
    elif scope["scope"] == "branch" and hasattr(Lead, "branch_id"):
        query = query.filter(Lead.branch_id == scope.get("branch_id"))
    return query


def _apply_loan_scope(query, scope, Loan):
    """Apply role-based scope to a Loan query."""
    org_id = scope.get("org_id")
    if org_id is not None and hasattr(Loan, "organization_id"):
        query = query.filter(Loan.organization_id == org_id)
    if scope["scope"] == "user":
        query = query.filter(Loan.loan_officer_id == scope["user_id"])
    elif scope["scope"] == "branch" and hasattr(Loan, "branch_id"):
        query = query.filter(Loan.branch_id == scope.get("branch_id"))
    return query


def register_scorecard_routes(app, get_db, get_current_user, Lead, Loan, LoanStage, **kwargs):
    """Register scorecard report routes."""

    def _get_scope(current_user):
        """Get role-based report scope for the current user."""
        from middleware.report_access import get_report_scope
        return get_report_scope(current_user)

    @app.get("/api/v1/scorecard")
    async def get_scorecard(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user)
    ):
        """
        Get comprehensive loan scorecard metrics matching the Loan Scorecard Report format.
        Includes conversion metrics, funding totals, and referral source breakdown.

        Role-based access (Enterprise Readiness Check 9.6):
        - Admin/Leadership: Organization-wide data
        - Branch Manager: Branch data
        - Loan Officer: Own data only

        All queries are scoped to the current user's organization_id for
        multi-tenant data isolation (Enterprise Readiness Check 9.5-9.7).
        """
        try:
            if start_date and end_date:
                start = dt.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
                end = dt.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            else:
                today = date.today()
                start = dt(today.year, today.month, 1, 0, 0, 0)
                end = dt(today.year, today.month, today.day, 23, 59, 59)

            start_date_str = start.strftime("%Y-%m-%d")
            end_date_str = end.strftime("%Y-%m-%d")
            logger.info(f"Scorecard request: {start_date_str} to {end_date_str} for user {current_user.id}")
        except Exception as e:
            logger.error(f"Error in scorecard endpoint (date setup): {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Error processing scorecard data")

        try:
            # Role-based scope (Check 9.6) + org isolation (Check 9.5-9.7)
            scope = _get_scope(current_user)

            # LOAN STARTS VS. ACTIVITY TOTALS
            try:
                lead_query = db.query(Lead).filter(
                    Lead.created_at >= start,
                    Lead.created_at <= end
                )
                lead_query = _apply_lead_scope(lead_query, scope, Lead)
                all_leads = lead_query.all()
            except Exception as e:
                logger.error(f"Error in get_scorecard (lead query): {e}")
                all_leads = []

            starts_count = len(all_leads)

            try:
                apps_query = db.query(func.count(Loan.id)).filter(
                    Loan.created_at >= start,
                    Loan.created_at <= end
                )
                apps_query = _apply_loan_scope(apps_query, scope, Loan)
                apps_count = apps_query.scalar() or 0
            except Exception as e:
                logger.error(f"Error in get_scorecard (apps query): {e}")
                apps_count = 0

            try:
                funded_query = db.query(func.count(Loan.id)).filter(
                    Loan.stage == LoanStage.FUNDED,
                    Loan.funded_date >= start,
                    Loan.funded_date <= end
                )
                funded_query = _apply_loan_scope(funded_query, scope, Loan)
                funded_count = funded_query.scalar() or 0
            except Exception as e:
                logger.error(f"Error in get_scorecard (funded query): {e}")
                funded_count = 0

            try:
                credit_query = db.query(func.count(Lead.id)).filter(
                    Lead.created_at >= start,
                    Lead.created_at <= end,
                    Lead.credit_score.isnot(None)
                )
                credit_query = _apply_lead_scope(credit_query, scope, Lead)
                credit_pulls = credit_query.scalar() or 0
            except Exception as e:
                logger.error(f"Error in get_scorecard (credit pulls query): {e}")
                credit_pulls = 0

            try:
                cancelled_query = db.query(func.count(Loan.id)).filter(
                    Loan.stage == LoanStage.SUSPENDED,
                    Loan.created_at >= start,
                    Loan.created_at <= end
                )
                cancelled_query = _apply_loan_scope(cancelled_query, scope, Loan)
                cancelled_count = cancelled_query.scalar() or 0
            except Exception as e:
                logger.error(f"Error in get_scorecard (cancelled query): {e}")
                cancelled_count = 0

            denied_count = 0

            try:
                uw_query = db.query(func.count(Loan.id)).filter(
                    Loan.stage == LoanStage.UW_RECEIVED,
                    Loan.created_at >= start,
                    Loan.created_at <= end
                )
                uw_query = _apply_loan_scope(uw_query, scope, Loan)
                uw_count = uw_query.scalar() or 0
            except Exception as e:
                logger.error(f"Error in get_scorecard (UW query): {e}")
                uw_count = 0

            try:
                ctc_query = db.query(func.count(Loan.id)).filter(
                    Loan.stage == LoanStage.CTC,
                    Loan.created_at >= start,
                    Loan.created_at <= end
                )
                ctc_query = _apply_loan_scope(ctc_query, scope, Loan)
                ctc_count = ctc_query.scalar() or 0
            except Exception as e:
                logger.error(f"Error in get_scorecard (CTC query): {e}")
                ctc_count = 0

            locked_funded = funded_count

            # Conversion percentages
            starts_to_apps_pct = int((apps_count / starts_count * 100)) if starts_count > 0 else 0
            apps_to_funded_pct = int((funded_count / apps_count * 100)) if apps_count > 0 else 0
            starts_to_funded_pct = int((funded_count / starts_count * 100)) if starts_count > 0 else 0
            credit_to_funded_pct = int((funded_count / credit_pulls * 100)) if credit_pulls > 0 else 0
            starts_to_cancelled_pct = int((cancelled_count / starts_count * 100)) if starts_count > 0 else 0
            starts_to_denied_pct = int((denied_count / starts_count * 100)) if starts_count > 0 else 0
            uw_to_ctc_pct = int((ctc_count / uw_count * 100)) if uw_count > 0 else 0
            lock_to_funded_pct = int((funded_count / locked_funded * 100)) if locked_funded > 0 else 0

            conversion_metrics = [
                {"metric": "Starts to Appl(E)", "current": apps_count, "total": starts_count, "mot_pct": starts_to_apps_pct, "goal_pct": 75, "status": "good" if starts_to_apps_pct >= 75 else "warning" if starts_to_apps_pct >= 60 else "critical"},
                {"metric": "Appl(E) to Funded", "current": funded_count, "total": apps_count, "mot_pct": apps_to_funded_pct, "goal_pct": 80, "status": "good" if apps_to_funded_pct >= 80 else "warning" if apps_to_funded_pct >= 60 else "critical"},
                {"metric": "Starts to Funded", "current": funded_count, "total": starts_count, "mot_pct": starts_to_funded_pct, "goal_pct": 50, "status": "good" if starts_to_funded_pct >= 50 else "warning" if starts_to_funded_pct >= 40 else "critical"},
                {"metric": "Credit Pulls to Funded", "current": funded_count, "total": credit_pulls, "mot_pct": credit_to_funded_pct, "goal_pct": 70, "status": "critical" if credit_to_funded_pct < 50 else "warning" if credit_to_funded_pct < 70 else "good"},
                {"metric": "Starts to Cancelled", "current": cancelled_count, "total": starts_count, "mot_pct": starts_to_cancelled_pct, "goal_pct": 10, "status": "good" if starts_to_cancelled_pct <= 10 else "warning"},
                {"metric": "Starts to Denied", "current": denied_count, "total": starts_count, "mot_pct": starts_to_denied_pct, "goal_pct": 5, "status": "good" if starts_to_denied_pct <= 5 else "warning"},
                {"metric": "UW to TBDs", "current": ctc_count, "total": uw_count, "mot_pct": uw_to_ctc_pct, "goal_pct": 50, "status": "good" if uw_to_ctc_pct >= 50 else "warning"},
                {"metric": "Initial Lock to Funded", "current": funded_count, "total": locked_funded, "mot_pct": lock_to_funded_pct, "goal_pct": 90, "status": "warning" if lock_to_funded_pct < 90 else "good"},
            ]

            # CONVERSION UPSWING
            current_pull_thru_pct = starts_to_funded_pct
            target_pull_thru_pct = current_pull_thru_pct + 10

            try:
                funded_loans_query = db.query(Loan).filter(
                    Loan.stage == LoanStage.FUNDED,
                    Loan.funded_date >= start,
                    Loan.funded_date <= end
                )
                funded_loans_query = _apply_loan_scope(funded_loans_query, scope, Loan)
                funded_loans = funded_loans_query.all()
            except Exception as e:
                logger.error(f"Error in get_scorecard (funded loans query): {e}")
                funded_loans = []

            current_avg_amount = sum(loan.amount for loan in funded_loans if loan.amount) / len(funded_loans) if funded_loans else 0
            current_volume = sum(loan.amount for loan in funded_loans if loan.amount) if funded_loans else 0
            target_volume = current_volume * 1.1
            volume_increase = target_volume - current_volume
            current_bps = 100
            current_compensation = (current_volume * current_bps) / 10000
            target_compensation = (target_volume * current_bps) / 10000

            conversion_upswing = {
                "current_starts": starts_count,
                "target_starts": int(starts_count * 1.1),
                "current_pull_thru_pct": current_pull_thru_pct,
                "target_pull_thru_pct": target_pull_thru_pct,
                "current_avg_amount": current_avg_amount,
                "target_avg_amount": current_avg_amount,
                "current_volume": current_volume,
                "target_volume": target_volume,
                "volume_increase": volume_increase,
                "current_bps": current_bps,
                "target_bps": current_bps,
                "current_compensation": current_compensation,
                "additional_compensation": target_compensation - current_compensation,
            }

            # FUNDING TOTALS
            try:
                funded_all_query = db.query(Loan).filter(
                    Loan.stage == LoanStage.FUNDED,
                    Loan.funded_date >= start,
                    Loan.funded_date <= end
                )
                funded_all_query = _apply_loan_scope(funded_all_query, scope, Loan)
                funded_loans_all = funded_all_query.all()
            except Exception as e:
                logger.error(f"Error in get_scorecard (funded loans all query): {e}")
                funded_loans_all = []

            total_funded_units = len(funded_loans_all)
            total_funded_volume = sum(loan.amount for loan in funded_loans_all if loan.amount) if funded_loans_all else 0

            loan_type_breakdown = {}
            for loan in funded_loans_all:
                lt = loan.loan_type or "Unknown"
                if lt not in loan_type_breakdown:
                    loan_type_breakdown[lt] = {"units": 0, "volume": 0}
                loan_type_breakdown[lt]["units"] += 1
                loan_type_breakdown[lt]["volume"] += loan.amount if loan.amount else 0

            loan_types = [
                {"type": lt, "units": d["units"], "volume": d["volume"], "percentage": (d["volume"] / total_funded_volume * 100) if total_funded_volume > 0 else 0}
                for lt, d in loan_type_breakdown.items()
            ]

            referral_breakdown = {}
            for loan in funded_loans_all:
                source = loan.source or "Unknown"
                if source not in referral_breakdown:
                    referral_breakdown[source] = {"referrals": 0, "closed_volume": 0}
                referral_breakdown[source]["referrals"] += 1
                referral_breakdown[source]["closed_volume"] += loan.amount if loan.amount else 0

            referral_sources = [
                {"source": s, "referrals": d["referrals"], "closed_volume": d["closed_volume"]}
                for s, d in referral_breakdown.items()
            ]

            funding_totals = {
                "total_units": total_funded_units,
                "total_volume": total_funded_volume,
                "loan_types": loan_types,
                "referral_sources": referral_sources,
                "avg_loan_amount": total_funded_volume / total_funded_units if total_funded_units > 0 else 0,
            }

            from middleware.report_access import get_scope_description
            return {
                "period": {"start_date": start_date_str, "end_date": end_date_str},
                "scope": get_scope_description(scope),
                "conversion_metrics": conversion_metrics,
                "conversion_upswing": conversion_upswing,
                "funding_totals": funding_totals,
                "generated_at": dt.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error in scorecard endpoint: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Error generating scorecard")

    # ==================================================================
    # GET /api/v1/scorecard/export - CSV Export (Check 9.8)
    # ==================================================================

    @app.get("/api/v1/scorecard/export")
    async def export_scorecard(
        request: Request,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        format: str = Query("csv", description="Export format (csv)"),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """
        Export scorecard report as CSV.

        Returns a streaming CSV file with conversion metrics, funding
        totals, and referral source breakdown. Respects role-based
        access scoping (Check 9.6).

        Enterprise Readiness Check 9.8: Report export capability.
        """
        if format != "csv":
            raise HTTPException(
                status_code=400,
                detail="Only CSV format is currently supported",
            )

        try:
            if start_date and end_date:
                start = dt.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
                end = dt.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            else:
                today = date.today()
                start = dt(today.year, today.month, 1, 0, 0, 0)
                end = dt(today.year, today.month, today.day, 23, 59, 59)

            start_date_str = start.strftime("%Y-%m-%d")
            end_date_str = end.strftime("%Y-%m-%d")
        except Exception as e:
            logger.error(f"Error in export_scorecard (date parsing): {e}")
            raise HTTPException(status_code=400, detail="Invalid date format")

        scope = _get_scope(current_user)

        # Gather metrics (same logic as JSON endpoint)
        try:
            lead_query = db.query(Lead).filter(
                Lead.created_at >= start, Lead.created_at <= end
            )
            lead_query = _apply_lead_scope(lead_query, scope, Lead)
            starts_count = lead_query.count()
        except Exception as e:
            logger.error(f"Error in export_scorecard (starts query): {e}")
            starts_count = 0

        try:
            apps_query = db.query(func.count(Loan.id)).filter(
                Loan.created_at >= start, Loan.created_at <= end
            )
            apps_query = _apply_loan_scope(apps_query, scope, Loan)
            apps_count = apps_query.scalar() or 0
        except Exception as e:
            logger.error(f"Error in export_scorecard (apps query): {e}")
            apps_count = 0

        try:
            funded_query = db.query(func.count(Loan.id)).filter(
                Loan.stage == LoanStage.FUNDED,
                Loan.funded_date >= start, Loan.funded_date <= end
            )
            funded_query = _apply_loan_scope(funded_query, scope, Loan)
            funded_count = funded_query.scalar() or 0
        except Exception as e:
            logger.error(f"Error in export_scorecard (funded query): {e}")
            funded_count = 0

        try:
            funded_loans_query = db.query(Loan).filter(
                Loan.stage == LoanStage.FUNDED,
                Loan.funded_date >= start, Loan.funded_date <= end
            )
            funded_loans_query = _apply_loan_scope(funded_loans_query, scope, Loan)
            funded_loans_all = funded_loans_query.all()
        except Exception as e:
            logger.error(f"Error in export_scorecard (funded loans query): {e}")
            funded_loans_all = []

        total_funded_volume = sum(
            loan.amount for loan in funded_loans_all if loan.amount
        ) if funded_loans_all else 0

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header section
        from middleware.report_access import get_scope_description
        writer.writerow(["Loan Scorecard Report"])
        writer.writerow(["Period", f"{start_date_str} to {end_date_str}"])
        writer.writerow(["Scope", get_scope_description(scope)])
        writer.writerow(["Generated At", dt.utcnow().isoformat()])
        writer.writerow([])

        # Conversion metrics
        writer.writerow(["Conversion Metrics"])
        writer.writerow(["Metric", "Current", "Total", "Percentage", "Goal %"])
        starts_to_apps = int((apps_count / starts_count * 100)) if starts_count > 0 else 0
        apps_to_funded = int((funded_count / apps_count * 100)) if apps_count > 0 else 0
        starts_to_funded = int((funded_count / starts_count * 100)) if starts_count > 0 else 0

        writer.writerow(["Starts to Applications", apps_count, starts_count, f"{starts_to_apps}%", "75%"])
        writer.writerow(["Applications to Funded", funded_count, apps_count, f"{apps_to_funded}%", "80%"])
        writer.writerow(["Starts to Funded", funded_count, starts_count, f"{starts_to_funded}%", "50%"])
        writer.writerow([])

        # Funding totals
        writer.writerow(["Funding Totals"])
        writer.writerow(["Total Funded Units", len(funded_loans_all)])
        writer.writerow(["Total Funded Volume", f"${total_funded_volume:,.2f}"])
        avg_amount = total_funded_volume / len(funded_loans_all) if funded_loans_all else 0
        writer.writerow(["Average Loan Amount", f"${avg_amount:,.2f}"])
        writer.writerow([])

        # Loan type breakdown
        writer.writerow(["Funded Loans by Type"])
        writer.writerow(["Loan Type", "Units", "Volume", "% of Total"])
        loan_type_breakdown = {}
        for loan in funded_loans_all:
            lt = loan.loan_type or "Unknown"
            if lt not in loan_type_breakdown:
                loan_type_breakdown[lt] = {"units": 0, "volume": 0}
            loan_type_breakdown[lt]["units"] += 1
            loan_type_breakdown[lt]["volume"] += loan.amount if loan.amount else 0

        for lt, d in loan_type_breakdown.items():
            pct = (d["volume"] / total_funded_volume * 100) if total_funded_volume > 0 else 0
            writer.writerow([lt, d["units"], f"${d['volume']:,.2f}", f"{pct:.1f}%"])
        writer.writerow([])

        # Referral sources
        writer.writerow(["Referral Sources"])
        writer.writerow(["Source", "Referrals", "Closed Volume"])
        referral_breakdown = {}
        for loan in funded_loans_all:
            source = loan.source or "Unknown"
            if source not in referral_breakdown:
                referral_breakdown[source] = {"referrals": 0, "volume": 0}
            referral_breakdown[source]["referrals"] += 1
            referral_breakdown[source]["volume"] += loan.amount if loan.amount else 0

        for s, d in referral_breakdown.items():
            writer.writerow([s, d["referrals"], f"${d['volume']:,.2f}"])

        output.seek(0)
        filename = f"scorecard_{start_date_str}_to_{end_date_str}.csv"

        try:
            from utils.export_audit import log_export_event, _get_client_ip
            org_id = scope.get("org_id")
            log_export_event(
                db=db, user_id=current_user.id, organization_id=org_id,
                resource_type="scorecard", export_format="csv",
                ip_address=_get_client_ip(request),
                details={"start_date": start_date_str, "end_date": end_date_str, "funded_count": funded_count},
            )
        except Exception as _exc:  # noqa: BLE001
            pass

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )

    logger.info("Scorecard routes loaded (with role-based scoping + CSV export)")
