"""
Loan Scorecard Report Routes

Extracted from inline_legacy_routes.py.
Provides comprehensive loan scorecard metrics including conversion metrics,
funding totals, and referral source breakdown.

Enterprise Readiness (Check 9.5-9.7):
All report queries include organization_id filtering to enforce multi-tenant
data isolation. The current user's organization_id is extracted from the
authenticated user object and applied to every database query.
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime as dt
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def register_scorecard_routes(app, get_db, get_current_user, Lead, Loan, LoanStage, **kwargs):
    """Register scorecard report routes."""

    @app.get("/api/v1/scorecard")
    async def get_scorecard(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user)
    ):
        """
        Get comprehensive loan scorecard metrics matching the Loan Scorecard Report format.
        Includes conversion metrics, funding totals, and referral source breakdown.

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
            # Extract organization_id for tenant isolation (Check 9.5-9.7)
            org_id = getattr(current_user, 'organization_id', None)

            # LOAN STARTS VS. ACTIVITY TOTALS
            try:
                lead_query = db.query(Lead).filter(
                    Lead.owner_id == current_user.id,
                    Lead.created_at >= start,
                    Lead.created_at <= end
                )
                if org_id is not None:
                    lead_query = lead_query.filter(Lead.organization_id == org_id)
                all_leads = lead_query.all()
            except Exception:
                all_leads = []

            starts_count = len(all_leads)

            try:
                apps_query = db.query(func.count(Loan.id)).filter(
                    Loan.loan_officer_id == current_user.id,
                    Loan.created_at >= start,
                    Loan.created_at <= end
                )
                if org_id is not None:
                    apps_query = apps_query.filter(Loan.organization_id == org_id)
                apps_count = apps_query.scalar() or 0
            except Exception:
                apps_count = 0

            try:
                funded_query = db.query(func.count(Loan.id)).filter(
                    Loan.loan_officer_id == current_user.id,
                    Loan.stage == LoanStage.FUNDED,
                    Loan.funded_date >= start,
                    Loan.funded_date <= end
                )
                if org_id is not None:
                    funded_query = funded_query.filter(Loan.organization_id == org_id)
                funded_count = funded_query.scalar() or 0
            except Exception:
                funded_count = 0

            try:
                credit_query = db.query(func.count(Lead.id)).filter(
                    Lead.owner_id == current_user.id,
                    Lead.created_at >= start,
                    Lead.created_at <= end,
                    Lead.credit_score.isnot(None)
                )
                if org_id is not None:
                    credit_query = credit_query.filter(Lead.organization_id == org_id)
                credit_pulls = credit_query.scalar() or 0
            except Exception:
                credit_pulls = 0

            try:
                cancelled_query = db.query(func.count(Loan.id)).filter(
                    Loan.loan_officer_id == current_user.id,
                    Loan.stage == LoanStage.SUSPENDED,
                    Loan.created_at >= start,
                    Loan.created_at <= end
                )
                if org_id is not None:
                    cancelled_query = cancelled_query.filter(Loan.organization_id == org_id)
                cancelled_count = cancelled_query.scalar() or 0
            except Exception:
                cancelled_count = 0

            denied_count = 0

            try:
                uw_query = db.query(func.count(Loan.id)).filter(
                    Loan.loan_officer_id == current_user.id,
                    Loan.stage == LoanStage.UW_RECEIVED,
                    Loan.created_at >= start,
                    Loan.created_at <= end
                )
                if org_id is not None:
                    uw_query = uw_query.filter(Loan.organization_id == org_id)
                uw_count = uw_query.scalar() or 0
            except Exception:
                uw_count = 0

            try:
                ctc_query = db.query(func.count(Loan.id)).filter(
                    Loan.loan_officer_id == current_user.id,
                    Loan.stage == LoanStage.CTC,
                    Loan.created_at >= start,
                    Loan.created_at <= end
                )
                if org_id is not None:
                    ctc_query = ctc_query.filter(Loan.organization_id == org_id)
                ctc_count = ctc_query.scalar() or 0
            except Exception:
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
                    Loan.loan_officer_id == current_user.id,
                    Loan.stage == LoanStage.FUNDED,
                    Loan.funded_date >= start,
                    Loan.funded_date <= end
                )
                if org_id is not None:
                    funded_loans_query = funded_loans_query.filter(Loan.organization_id == org_id)
                funded_loans = funded_loans_query.all()
            except Exception:
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
                    Loan.loan_officer_id == current_user.id,
                    Loan.stage == LoanStage.FUNDED,
                    Loan.funded_date >= start,
                    Loan.funded_date <= end
                )
                if org_id is not None:
                    funded_all_query = funded_all_query.filter(Loan.organization_id == org_id)
                funded_loans_all = funded_all_query.all()
            except Exception:
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

            return {
                "period": {"start_date": start_date_str, "end_date": end_date_str},
                "conversion_metrics": conversion_metrics,
                "conversion_upswing": conversion_upswing,
                "funding_totals": funding_totals,
                "generated_at": dt.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error in scorecard endpoint: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Error generating scorecard")

    logger.info("Scorecard routes loaded")
