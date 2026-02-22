"""
Content Personalization Service

Handles CRM data integration for content personalization:
- Token resolution from LeadProfile, ActiveLoanProfile, MUMClientProfile
- Jinja2 template rendering with CRM data
- Batch personalization for segments
- Token value formatting (currency, dates, percentages)
"""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, date
from decimal import Decimal
from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError
from sqlalchemy.orm import Session

from models.lead_profile import LeadProfile
from models.active_loan_profile import ActiveLoanProfile
from models.mum_client_profile import MUMClientProfile
from models.content_marketing import PersonalizationToken, PersonalizationType

logger = logging.getLogger(__name__)


class ContentPersonalizationService:
    """
    Service for personalizing content with CRM data.

    Supports personalization tokens like:
    - {{lead.first_name}} -> Lead's first name
    - {{loan.rate}} -> Active loan interest rate
    - {{mum.estimated_savings}} -> MUM client's potential savings
    """

    # Token format patterns
    FORMAT_PATTERNS = {
        "currency": "${:,.2f}",
        "percentage": "{:.3f}%",
        "date": "%B %d, %Y",  # e.g., "January 15, 2026"
        "date_short": "%m/%d/%Y",
        "number": "{:,.0f}",
        "decimal": "{:,.2f}",
    }

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.jinja_env = Environment(loader=BaseLoader())
        # Add custom filters
        self.jinja_env.filters['currency'] = self._format_currency
        self.jinja_env.filters['percentage'] = self._format_percentage
        self.jinja_env.filters['date'] = self._format_date

    # =========================================================================
    # CRM Data Fetching
    # =========================================================================

    def get_lead_data(self, lead_id: str) -> Optional[Dict[str, Any]]:
        """Fetch lead profile data for personalization."""
        try:
            lead = self.db.query(LeadProfile).filter(
                LeadProfile.id == lead_id,
                LeadProfile.is_deleted == False
            ).first()

            if not lead:
                return None

            return self._extract_lead_tokens(lead)
        except Exception as e:
            logger.error(f"Error fetching lead data: {e}")
            return None

    def get_loan_data(self, loan_id: str) -> Optional[Dict[str, Any]]:
        """Fetch active loan profile data for personalization."""
        try:
            loan = self.db.query(ActiveLoanProfile).filter(
                ActiveLoanProfile.id == loan_id,
                ActiveLoanProfile.is_deleted == False
            ).first()

            if not loan:
                return None

            return self._extract_loan_tokens(loan)
        except Exception as e:
            logger.error(f"Error fetching loan data: {e}")
            return None

    def get_mum_data(self, mum_id: str) -> Optional[Dict[str, Any]]:
        """Fetch MUM client profile data for personalization."""
        try:
            mum = self.db.query(MUMClientProfile).filter(
                MUMClientProfile.id == mum_id,
                MUMClientProfile.is_deleted == False
            ).first()

            if not mum:
                return None

            return self._extract_mum_tokens(mum)
        except Exception as e:
            logger.error(f"Error fetching MUM data: {e}")
            return None

    def get_combined_context(
        self,
        lead_id: Optional[str] = None,
        loan_id: Optional[str] = None,
        mum_id: Optional[str] = None,
        extra_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build combined personalization context from multiple CRM sources.

        Returns context dict with namespaced data:
        {
            "lead": {...},
            "loan": {...},
            "mum": {...},
            "company": {...},
            ...extra_context
        }
        """
        context = {
            "lead": {},
            "loan": {},
            "mum": {},
            "company": self._get_company_defaults(),
            "today": datetime.now(),
        }

        if lead_id:
            lead_data = self.get_lead_data(lead_id)
            if lead_data:
                context["lead"] = lead_data

        if loan_id:
            loan_data = self.get_loan_data(loan_id)
            if loan_data:
                context["loan"] = loan_data

        if mum_id:
            mum_data = self.get_mum_data(mum_id)
            if mum_data:
                context["mum"] = mum_data

        if extra_context:
            context.update(extra_context)

        return context

    # =========================================================================
    # Token Extraction
    # =========================================================================

    def _extract_lead_tokens(self, lead: LeadProfile) -> Dict[str, Any]:
        """Extract personalization tokens from LeadProfile."""
        return {
            # Personal
            "first_name": lead.first_name or "",
            "last_name": lead.last_name or "",
            "full_name": f"{lead.first_name or ''} {lead.last_name or ''}".strip(),
            "email": lead.email or "",
            "phone": lead.phone or "",

            # Employment
            "employer_name": lead.employer_name or "",
            "job_title": lead.job_title or "",
            "annual_income": self._to_float(lead.annual_income),
            "annual_income_formatted": self._format_currency(lead.annual_income),

            # Property
            "address": lead.address or "",
            "city": lead.city or "",
            "state": lead.state or "",
            "zip_code": lead.zip_code or "",
            "full_address": self._build_address(lead.address, lead.city, lead.state, lead.zip_code),
            "property_type": self._format_property_type(lead.property_type),
            "property_value": self._to_float(lead.property_value),
            "property_value_formatted": self._format_currency(lead.property_value),

            # Loan details
            "loan_amount": self._to_float(lead.loan_amount),
            "loan_amount_formatted": self._format_currency(lead.loan_amount),
            "down_payment": self._to_float(lead.down_payment),
            "down_payment_formatted": self._format_currency(lead.down_payment),
            "interest_rate": self._to_float(lead.interest_rate),
            "interest_rate_formatted": self._format_percentage(lead.interest_rate),
            "loan_term": lead.loan_term or 30,
            "loan_type": self._format_loan_type(lead.loan_type),
            "credit_score": lead.credit_score or 0,
            "ltv": self._to_float(lead.ltv),
            "ltv_formatted": self._format_percentage(lead.ltv),
            "dti": self._to_float(lead.dti),
            "dti_formatted": self._format_percentage(lead.dti),

            # Dates
            "lock_date": self._format_date(lead.lock_date),
            "lock_expiration": self._format_date(lead.lock_expiration),
            "closing_date": self._format_date(lead.closing_date),
            "preapproval_expiration_date": self._format_date(lead.preapproval_expiration_date),

            # Team
            "loan_officer": lead.loan_officer or "",
            "processor": lead.processor or "",
            "lender": lead.lender or "",

            # Status
            "stage": lead.stage or "",
            "status": lead.status or "",
        }

    def _extract_loan_tokens(self, loan: ActiveLoanProfile) -> Dict[str, Any]:
        """Extract personalization tokens from ActiveLoanProfile."""
        return {
            # Loan details
            "loan_number": loan.loan_number or "",
            "amount": self._to_float(loan.amount),
            "amount_formatted": self._format_currency(loan.amount),
            "rate": self._to_float(loan.rate),
            "rate_formatted": self._format_percentage(loan.rate),
            "term": loan.term or 30,
            "program": loan.program or "",
            "apr": self._to_float(loan.apr),
            "apr_formatted": self._format_percentage(loan.apr),
            "points": self._to_float(loan.points),
            "lender": loan.lender or "",
            "appraisal_value": self._to_float(loan.appraisal_value),
            "appraisal_value_formatted": self._format_currency(loan.appraisal_value),
            "ltv": self._to_float(loan.ltv),
            "ltv_formatted": self._format_percentage(loan.ltv),
            "dti": self._to_float(loan.dti),
            "dti_formatted": self._format_percentage(loan.dti),

            # Property
            "property_address": loan.property_address or "",
            "property_city": loan.property_city or "",
            "property_state": loan.property_state or "",
            "property_zip": loan.property_zip or "",
            "full_property_address": self._build_address(
                loan.property_address, loan.property_city,
                loan.property_state, loan.property_zip
            ),

            # Team
            "loan_officer_name": loan.loan_officer_name or "",
            "loan_officer_email": loan.loan_officer_email or "",
            "processor": loan.processor or "",
            "processor_email": loan.processor_email or "",
            "underwriter": loan.underwriter or "",
            "closer": loan.closer or "",

            # Key dates
            "lock_date": self._format_date(loan.lock_date),
            "lock_expiration": self._format_date(loan.lock_expiration),
            "contract_received_date": self._format_date(loan.contract_received_date),
            "appraisal_ordered_date": self._format_date(loan.appraisal_ordered_date),
            "appraisal_completed_date": self._format_date(loan.appraisal_completed_date),
            "clear_to_close_date": self._format_date(loan.clear_to_close_date),
            "closing_scheduled_date": self._format_date(loan.closing_scheduled_date),
            "funding_date": self._format_date(loan.funding_date),
            "closing_disclosure_sent_date": self._format_date(loan.closing_disclosure_sent_date),

            # Status
            "status": loan.status or "",
            "current_milestone": loan.current_milestone or "",
            "days_to_closing": loan.days_to_closing or 0,
        }

    def _extract_mum_tokens(self, mum: MUMClientProfile) -> Dict[str, Any]:
        """Extract personalization tokens from MUMClientProfile."""
        # Parse name into first/last
        name_parts = (mum.name or "").split(" ", 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        return {
            # Personal
            "name": mum.name or "",
            "first_name": first_name,
            "last_name": last_name,
            "email": mum.email or "",
            "phone": mum.phone or "",

            # Loan details
            "loan_number": mum.loan_number or "",
            "original_close_date": self._format_date(mum.original_close_date),
            "original_rate": self._to_float(mum.original_rate),
            "original_rate_formatted": self._format_percentage(mum.original_rate),
            "current_rate": self._to_float(mum.current_rate),
            "current_rate_formatted": self._format_percentage(mum.current_rate),
            "loan_balance": self._to_float(mum.loan_balance),
            "loan_balance_formatted": self._format_currency(mum.loan_balance),

            # Refinance opportunity
            "estimated_savings": self._to_float(mum.estimated_savings),
            "estimated_savings_formatted": self._format_currency(mum.estimated_savings),
            "refinance_opportunity": mum.refinance_opportunity or False,
            "opportunity_notes": mum.opportunity_notes or "",

            # Team
            "loan_officer": mum.loan_officer or "",
            "loan_officer_email": mum.loan_officer_email or "",
            "processor": mum.processor or "",

            # Engagement
            "last_contact": self._format_date(mum.last_contact),
            "next_touchpoint": self._format_date(mum.next_touchpoint),
            "engagement_score": mum.engagement_score or 0,
            "referrals_sent": mum.referrals_sent or 0,

            # Status
            "status": mum.status or "",
        }

    # =========================================================================
    # Template Rendering
    # =========================================================================

    def render_template(
        self,
        template_text: str,
        context: Dict[str, Any],
        use_defaults: bool = True
    ) -> str:
        """
        Render a Jinja2 template with personalization context.

        Args:
            template_text: Jinja2 template string with {{tokens}}
            context: Personalization context dict
            use_defaults: Whether to use default values for missing tokens

        Returns:
            Rendered string with tokens replaced
        """
        try:
            template = self.jinja_env.from_string(template_text)

            if use_defaults:
                # Add default fallbacks for common tokens
                context = self._add_default_fallbacks(context)

            return template.render(**context)
        except TemplateSyntaxError as e:
            logger.error(f"Template syntax error: {e}")
            raise ValueError(f"Invalid template syntax: {e}")
        except UndefinedError as e:
            logger.error(f"Undefined token in template: {e}")
            if use_defaults:
                # Return template with missing tokens as empty strings
                return self._safe_render(template_text, context)
            raise ValueError(f"Undefined personalization token: {e}")
        except Exception as e:
            logger.error(f"Template rendering error: {e}")
            raise ValueError(f"Failed to render template: {e}")

    def _safe_render(self, template_text: str, context: Dict[str, Any]) -> str:
        """Safely render template, replacing undefined tokens with empty strings."""
        try:
            # Use a more permissive environment
            safe_env = Environment(loader=BaseLoader(), undefined=lambda *a, **k: "")
            template = safe_env.from_string(template_text)
            return template.render(**context)
        except Exception as e:
            logger.exception(f"Failed to safely render template: {e}")
            # Last resort: return template as-is
            return template_text

    def preview_personalization(
        self,
        template_text: str,
        personalization_type: str,
        record_id: str,
        extra_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Preview personalized content for a specific CRM record.

        Returns both the rendered content and the context used.
        """
        context = {}

        if personalization_type == PersonalizationType.LEAD.value:
            context = self.get_combined_context(lead_id=record_id, extra_context=extra_context)
        elif personalization_type == PersonalizationType.LOAN.value:
            context = self.get_combined_context(loan_id=record_id, extra_context=extra_context)
        elif personalization_type == PersonalizationType.MUM.value:
            context = self.get_combined_context(mum_id=record_id, extra_context=extra_context)
        else:
            context = self.get_combined_context(extra_context=extra_context)

        rendered = self.render_template(template_text, context)

        return {
            "original_template": template_text,
            "rendered_content": rendered,
            "context_used": context,
            "personalization_type": personalization_type,
            "record_id": record_id,
        }

    # =========================================================================
    # Batch Personalization
    # =========================================================================

    def batch_personalize(
        self,
        template_text: str,
        personalization_type: str,
        record_ids: List[str],
        extra_context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Batch personalize content for multiple CRM records.

        Returns list of personalized content with record info.
        """
        results = []

        for record_id in record_ids:
            try:
                result = self.preview_personalization(
                    template_text, personalization_type, record_id, extra_context
                )
                result["success"] = True
                results.append(result)
            except Exception as e:
                results.append({
                    "record_id": record_id,
                    "success": False,
                    "error": "Internal server error"
                })

        return results

    def get_segment_records(
        self,
        personalization_type: str,
        segment_filter: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[str]:
        """
        Get CRM record IDs for a segment based on filters.

        Args:
            personalization_type: Type of CRM record (lead, loan, mum)
            segment_filter: Filter criteria (e.g., {"stage": "qualified", "state": "CA"})
            limit: Maximum records to return

        Returns:
            List of record IDs matching the segment
        """
        try:
            if personalization_type == PersonalizationType.LEAD.value:
                query = self.db.query(LeadProfile.id).filter(
                    LeadProfile.is_deleted == False
                )
                if segment_filter:
                    if "stage" in segment_filter:
                        query = query.filter(LeadProfile.stage == segment_filter["stage"])
                    if "state" in segment_filter:
                        query = query.filter(LeadProfile.state == segment_filter["state"])
                    if "loan_type" in segment_filter:
                        query = query.filter(LeadProfile.loan_type == segment_filter["loan_type"])
                    if "status" in segment_filter:
                        query = query.filter(LeadProfile.status == segment_filter["status"])

            elif personalization_type == PersonalizationType.LOAN.value:
                query = self.db.query(ActiveLoanProfile.id).filter(
                    ActiveLoanProfile.is_deleted == False
                )
                if segment_filter:
                    if "status" in segment_filter:
                        query = query.filter(ActiveLoanProfile.status == segment_filter["status"])
                    if "current_milestone" in segment_filter:
                        query = query.filter(ActiveLoanProfile.current_milestone == segment_filter["current_milestone"])
                    if "lender" in segment_filter:
                        query = query.filter(ActiveLoanProfile.lender == segment_filter["lender"])

            elif personalization_type == PersonalizationType.MUM.value:
                query = self.db.query(MUMClientProfile.id).filter(
                    MUMClientProfile.is_deleted == False
                )
                if segment_filter:
                    if "status" in segment_filter:
                        query = query.filter(MUMClientProfile.status == segment_filter["status"])
                    if "refinance_opportunity" in segment_filter:
                        query = query.filter(MUMClientProfile.refinance_opportunity == segment_filter["refinance_opportunity"])
            else:
                return []

            records = query.limit(limit).all()
            return [str(r[0]) for r in records]

        except Exception as e:
            logger.error(f"Error getting segment records: {e}")
            return []

    # =========================================================================
    # Token Management
    # =========================================================================

    def get_available_tokens(
        self,
        personalization_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get list of available personalization tokens from database."""
        try:
            query = self.db.query(PersonalizationToken).filter(
                PersonalizationToken.is_active == True
            )

            if personalization_type:
                query = query.filter(
                    PersonalizationToken.source_model == personalization_type
                )

            tokens = query.all()

            return [
                {
                    "token_name": t.token_name,
                    "display_name": t.display_name,
                    "description": t.description,
                    "source_model": t.source_model,
                    "source_field": t.source_field,
                    "format_type": t.format_type,
                    "category": t.category,
                    "default_value": t.default_value,
                }
                for t in tokens
            ]
        except Exception as e:
            logger.error(f"Error getting available tokens: {e}")
            return []

    def extract_tokens_from_template(self, template_text: str) -> List[str]:
        """Extract all personalization tokens from a template string."""
        import re
        # Match {{ token.name }} or {{token.name}}
        pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}'
        matches = re.findall(pattern, template_text)
        return list(set(matches))

    def validate_template_tokens(
        self,
        template_text: str,
        personalization_type: str
    ) -> Dict[str, Any]:
        """
        Validate that all tokens in a template are available.

        Returns validation result with any missing tokens.
        """
        extracted = self.extract_tokens_from_template(template_text)
        available = self.get_available_tokens(personalization_type)
        available_names = {t["token_name"] for t in available}

        # Also add general tokens
        general_tokens = {"today", "company.name", "company.phone", "company.nmls"}
        available_names.update(general_tokens)

        missing = []
        valid = []

        for token in extracted:
            # Handle nested tokens like lead.first_name
            if token in available_names:
                valid.append(token)
            elif "." in token:
                # Check if parent.child format matches source_model.source_field
                parts = token.split(".", 1)
                parent = parts[0]
                child = parts[1] if len(parts) > 1 else ""

                # Build the lookup
                matching = [
                    t for t in available
                    if t["source_model"] == parent and t["source_field"] == child
                ]
                if matching or parent in ["lead", "loan", "mum", "company"]:
                    valid.append(token)
                else:
                    missing.append(token)
            else:
                missing.append(token)

        return {
            "is_valid": len(missing) == 0,
            "total_tokens": len(extracted),
            "valid_tokens": valid,
            "missing_tokens": missing,
        }

    # =========================================================================
    # Formatting Helpers
    # =========================================================================

    def _format_currency(self, value: Any) -> str:
        """Format value as currency."""
        if value is None:
            return "$0.00"
        try:
            return f"${float(value):,.2f}"
        except (ValueError, TypeError):
            return "$0.00"

    def _format_percentage(self, value: Any) -> str:
        """Format value as percentage."""
        if value is None:
            return "0%"
        try:
            return f"{float(value):.3f}%"
        except (ValueError, TypeError):
            return "0%"

    def _format_date(self, value: Any, format_str: str = None) -> str:
        """Format date value."""
        if value is None:
            return ""
        try:
            if isinstance(value, str):
                return value
            if isinstance(value, (datetime, date)):
                fmt = format_str or self.FORMAT_PATTERNS["date"]
                return value.strftime(fmt)
            return str(value)
        except Exception as e:
            logger.exception(f"Failed to format date value: {e}")
            return ""

    def _to_float(self, value: Any) -> float:
        """Convert value to float."""
        if value is None:
            return 0.0
        try:
            if isinstance(value, Decimal):
                return float(value)
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    def _build_address(
        self,
        street: Optional[str],
        city: Optional[str],
        state: Optional[str],
        zip_code: Optional[str]
    ) -> str:
        """Build formatted address string."""
        parts = []
        if street:
            parts.append(street)
        if city:
            parts.append(city)
        if state:
            if zip_code:
                parts.append(f"{state} {zip_code}")
            else:
                parts.append(state)
        elif zip_code:
            parts.append(zip_code)
        return ", ".join(parts)

    def _format_property_type(self, value: Optional[str]) -> str:
        """Format property type for display."""
        if not value:
            return ""
        mapping = {
            "single_family": "Single Family Home",
            "condo": "Condominium",
            "townhouse": "Townhouse",
            "multi_family": "Multi-Family",
        }
        return mapping.get(value, value.replace("_", " ").title())

    def _format_loan_type(self, value: Optional[str]) -> str:
        """Format loan type for display."""
        if not value:
            return ""
        mapping = {
            "conventional": "Conventional",
            "fha": "FHA",
            "va": "VA",
            "usda": "USDA",
        }
        return mapping.get(value, value.upper())

    def _get_company_defaults(self) -> Dict[str, str]:
        """Get default company information."""
        return {
            "name": "Your Mortgage Company",
            "phone": "(555) 123-4567",
            "email": "info@yourmortgage.com",
            "nmls": "123456",
            "website": "www.yourmortgage.com",
        }

    def _add_default_fallbacks(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Add default fallback values for common tokens."""
        defaults = {
            "lead": {
                "first_name": "Valued Customer",
                "full_name": "Valued Customer",
            },
            "loan": {
                "loan_officer_name": "Your Loan Officer",
            },
            "mum": {
                "first_name": "Valued Client",
                "name": "Valued Client",
            },
        }

        # Merge defaults with context
        for key, default_values in defaults.items():
            if key not in context:
                context[key] = default_values
            else:
                for field, default_val in default_values.items():
                    if field not in context[key] or not context[key][field]:
                        context[key][field] = default_val

        return context
