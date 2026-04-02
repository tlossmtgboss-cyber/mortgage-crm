"""
Opportunity Detection Service
Compares parsed rate sheet rates against funded loans to identify refinance opportunities.

Features:
- Scans funded loans with known rates
- Matches each loan to best available rate from rate sheet
- Calculates savings potential
- Creates opportunities when thresholds are met
"""

import os
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_MIN_SAVINGS_THRESHOLD = float(os.getenv('DEFAULT_MIN_SAVINGS_THRESHOLD', '200'))
DEFAULT_MIN_RATE_DROP = float(os.getenv('DEFAULT_MIN_RATE_DROP', '0.5'))


class OpportunityDetectionService:
    """
    Service for detecting refinance opportunities by comparing
    funded loan rates against new rate sheet rates.
    """

    def __init__(self, db: Session):
        self.db = db
        self.min_savings_threshold = DEFAULT_MIN_SAVINGS_THRESHOLD
        self.min_rate_drop = DEFAULT_MIN_RATE_DROP

    async def scan_for_opportunities(
        self,
        rate_sheet_id: int,
        min_savings: Optional[float] = None,
        min_rate_drop: Optional[float] = None,
        created_by: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Scan funded loans and create opportunities based on rate sheet.

        Args:
            rate_sheet_id: ID of the rate sheet to use
            min_savings: Minimum monthly savings threshold (default $200)
            min_rate_drop: Minimum rate drop threshold (default 0.5%)
            created_by: User ID who initiated the scan

        Returns:
            Dict with scan results and created opportunities
        """
        from models.rate_sheet import RateSheet, RateSheetRate, RefinanceOpportunity

        min_savings = min_savings or self.min_savings_threshold
        min_rate_drop = min_rate_drop or self.min_rate_drop

        # Verify rate sheet exists and has rates
        rate_sheet = self.db.query(RateSheet).filter(RateSheet.id == rate_sheet_id).first()
        if not rate_sheet:
            return {
                'success': False,
                'error': f'Rate sheet {rate_sheet_id} not found',
            }

        if rate_sheet.status != 'parsed':
            return {
                'success': False,
                'error': f'Rate sheet is not parsed (status: {rate_sheet.status})',
            }

        # Get available rates from the sheet
        sheet_rates = self.db.query(RateSheetRate).filter(
            RateSheetRate.rate_sheet_id == rate_sheet_id
        ).all()

        if not sheet_rates:
            return {
                'success': False,
                'error': 'No rates found in rate sheet',
            }

        # Build rate lookup by loan type and term
        rate_lookup = {}
        for rate in sheet_rates:
            key = (rate.loan_type, rate.loan_term)
            if key not in rate_lookup or float(rate.rate) < float(rate_lookup[key].rate):
                rate_lookup[key] = rate

        # Get funded loans with rate information
        funded_loans = self._get_eligible_funded_loans()

        logger.info(f"Scanning {len(funded_loans)} funded loans against {len(sheet_rates)} rates")

        opportunities_created = []
        loans_scanned = 0
        loans_with_savings = 0

        for loan in funded_loans:
            loans_scanned += 1

            # Find matching rate from sheet
            loan_type = loan.get('loan_type', 'conventional')
            loan_term = loan.get('loan_term', 30)
            current_rate = loan.get('interest_rate')
            loan_amount = loan.get('loan_amount')

            if not current_rate or not loan_amount:
                continue

            # Look up best available rate
            key = (loan_type, loan_term)
            if key not in rate_lookup:
                # Try fallback to conventional 30yr
                key = ('conventional', 30)
                if key not in rate_lookup:
                    continue

            new_rate_record = rate_lookup[key]
            new_rate = float(new_rate_record.rate)
            current_rate = float(current_rate)
            loan_amount = float(loan_amount)

            # Calculate savings
            rate_difference = current_rate - new_rate
            if rate_difference <= 0:
                continue

            monthly_savings = (rate_difference / 100 / 12) * loan_amount
            annual_savings = monthly_savings * 12

            # Check if meets thresholds
            if monthly_savings >= min_savings or rate_difference >= min_rate_drop:
                loans_with_savings += 1

                # Check for existing opportunity for this loan
                existing = self.db.query(RefinanceOpportunity).filter(
                    RefinanceOpportunity.loan_id == loan.get('id'),
                    RefinanceOpportunity.status.in_(['identified', 'sms_sent', 'called']),
                ).first()

                if existing:
                    # Update existing opportunity if new rate is better
                    if new_rate < float(existing.new_rate):
                        existing.new_rate = Decimal(str(new_rate))
                        existing.rate_difference = Decimal(str(rate_difference))
                        existing.monthly_savings = Decimal(str(round(monthly_savings, 2)))
                        existing.annual_savings = Decimal(str(round(annual_savings, 2)))
                        existing.rate_sheet_id = rate_sheet_id
                        existing.priority = self._calculate_priority(monthly_savings, rate_difference)
                        existing.updated_at = datetime.now(timezone.utc)
                    continue

                # Create new opportunity
                opportunity = RefinanceOpportunity(
                    loan_id=loan.get('id'),
                    rate_sheet_id=rate_sheet_id,
                    client_name=loan.get('borrower_name'),
                    client_phone=loan.get('borrower_phone'),
                    client_email=loan.get('borrower_email'),
                    current_rate=Decimal(str(current_rate)),
                    current_loan_amount=Decimal(str(loan_amount)),
                    loan_type=loan_type,
                    loan_term=loan_term,
                    funded_date=loan.get('funded_date'),
                    new_rate=Decimal(str(new_rate)),
                    rate_difference=Decimal(str(round(rate_difference, 3))),
                    monthly_savings=Decimal(str(round(monthly_savings, 2))),
                    annual_savings=Decimal(str(round(annual_savings, 2))),
                    priority=self._calculate_priority(monthly_savings, rate_difference),
                    status='identified',
                    created_by=created_by,
                )

                self.db.add(opportunity)
                opportunities_created.append(opportunity)

        self.db.commit()

        logger.info(f"Scan complete: {loans_scanned} loans scanned, {len(opportunities_created)} opportunities created")

        return {
            'success': True,
            'rate_sheet_id': rate_sheet_id,
            'loans_scanned': loans_scanned,
            'loans_with_savings': loans_with_savings,
            'opportunities_created': len(opportunities_created),
            'thresholds': {
                'min_savings': min_savings,
                'min_rate_drop': min_rate_drop,
            },
            'opportunities': [opp.to_dict() for opp in opportunities_created],
        }

    def _get_eligible_funded_loans(self) -> List[Dict[str, Any]]:
        """
        Get funded loans that are eligible for refinance opportunity detection.

        Criteria:
        - Status is 'funded'
        - Has interest rate on file
        - Has loan amount
        - Funded within last 5 years (to ensure loan still exists)
        - Has contact information
        """
        # Try to query from loans table
        try:
            query = text("""
                SELECT
                    l.id,
                    l.loan_number,
                    l.borrower_name,
                    l.loan_amount,
                    l.interest_rate,
                    l.loan_type,
                    l.loan_term,
                    l.funded_at as funded_date,
                    c.phone as borrower_phone,
                    c.email as borrower_email
                FROM loans l
                LEFT JOIN contacts c ON c.id = l.borrower_id
                WHERE l.status = 'funded'
                    AND l.interest_rate IS NOT NULL
                    AND l.loan_amount IS NOT NULL
                    AND l.funded_at >= :min_date
                ORDER BY l.funded_at DESC
                LIMIT 1000
            """)

            min_date = date.today() - timedelta(days=5*365)
            result = self.db.execute(query, {'min_date': min_date})
            columns = result.keys()
            loans = [dict(zip(columns, row)) for row in result.fetchall()]

            return loans

        except SQLAlchemyError as e:
            logger.warning(f"Could not query loans table: {e}")

            # Try MUM clients as fallback
            try:
                query = text("""
                    SELECT
                        m.id,
                        m.client_name as borrower_name,
                        m.phone as borrower_phone,
                        m.email as borrower_email,
                        m.current_rate as interest_rate,
                        m.loan_balance as loan_amount,
                        m.loan_type,
                        m.loan_term,
                        m.closing_date as funded_date
                    FROM mum_clients m
                    WHERE m.current_rate IS NOT NULL
                        AND m.loan_balance IS NOT NULL
                        AND m.loan_balance > 50000
                    ORDER BY m.closing_date DESC NULLS LAST
                    LIMIT 1000
                """)

                result = self.db.execute(query)
                columns = result.keys()
                loans = [dict(zip(columns, row)) for row in result.fetchall()]

                return loans

            except Exception as e2:
                logger.error(f"Could not query MUM clients: {e2}")
                return []

    def _calculate_priority(self, monthly_savings: float, rate_difference: float) -> str:
        """Calculate priority based on savings potential."""
        if monthly_savings >= 400 or rate_difference >= 1.0:
            return 'urgent'
        elif monthly_savings >= 300 or rate_difference >= 0.75:
            return 'high'
        elif monthly_savings >= 200 or rate_difference >= 0.5:
            return 'medium'
        else:
            return 'low'

    def get_opportunities(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        rate_sheet_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Get list of refinance opportunities."""
        from models.rate_sheet import RefinanceOpportunity

        query = self.db.query(RefinanceOpportunity)

        if status:
            query = query.filter(RefinanceOpportunity.status == status)
        if priority:
            query = query.filter(RefinanceOpportunity.priority == priority)
        if rate_sheet_id:
            query = query.filter(RefinanceOpportunity.rate_sheet_id == rate_sheet_id)

        total = query.count()

        opportunities = query.order_by(
            RefinanceOpportunity.monthly_savings.desc()
        ).offset(offset).limit(limit).all()

        return {
            'opportunities': [opp.to_dict() for opp in opportunities],
            'total': total,
            'limit': limit,
            'offset': offset,
        }

    def get_opportunity(self, opportunity_id: int) -> Optional[Dict[str, Any]]:
        """Get a single opportunity by ID."""
        from models.rate_sheet import RefinanceOpportunity

        opp = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.id == opportunity_id
        ).first()

        if opp:
            return opp.to_dict()
        return None

    def update_opportunity_status(
        self,
        opportunity_id: int,
        status: str,
        notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update opportunity status."""
        from models.rate_sheet import RefinanceOpportunity

        opp = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.id == opportunity_id
        ).first()

        if not opp:
            return None

        opp.status = status
        if notes:
            opp.notes = notes

        self.db.commit()
        return opp.to_dict()

    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Get dashboard metrics for opportunities."""
        from models.rate_sheet import RefinanceOpportunity, RateSheet

        # Counts by status
        identified = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.status == 'identified'
        ).count()

        sms_sent = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.status == 'sms_sent'
        ).count()

        called = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.status == 'called'
        ).count()

        scheduled = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.status == 'scheduled'
        ).count()

        converted = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.status == 'converted'
        ).count()

        # Priority counts
        urgent = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.priority == 'urgent',
            RefinanceOpportunity.status.in_(['identified', 'sms_sent']),
        ).count()

        high = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.priority == 'high',
            RefinanceOpportunity.status.in_(['identified', 'sms_sent']),
        ).count()

        # Total potential savings from pending opportunities
        from sqlalchemy import func
        total_savings_result = self.db.query(
            func.sum(RefinanceOpportunity.monthly_savings)
        ).filter(
            RefinanceOpportunity.status.in_(['identified', 'sms_sent'])
        ).scalar()

        total_monthly_savings = float(total_savings_result or 0)

        # Recent rate sheets
        recent_sheets = self.db.query(RateSheet).filter(
            RateSheet.status == 'parsed'
        ).order_by(RateSheet.created_at.desc()).limit(5).all()

        return {
            'by_status': {
                'identified': identified,
                'sms_sent': sms_sent,
                'called': called,
                'scheduled': scheduled,
                'converted': converted,
            },
            'by_priority': {
                'urgent': urgent,
                'high': high,
            },
            'pending_total': identified + sms_sent,
            'total_monthly_savings': round(total_monthly_savings, 2),
            'total_annual_savings': round(total_monthly_savings * 12, 2),
            'recent_rate_sheets': [sheet.to_dict() for sheet in recent_sheets],
        }
