"""
Realtor Letter Generation Service - Pre-qual/Pre-approval letter generation.

Provides:
- Template-based letter generation
- Variable substitution with validation
- PDF generation and storage
- Letter versioning and history
- Secure sharing via tokens
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import secrets
import re
import json
import io

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class LetterTemplate:
    """Represents a letter template with variable schema."""

    def __init__(
        self,
        template_id: int,
        template_type: str,
        name: str,
        version: int,
        html_template: str,
        css_styles: Optional[str],
        header_html: Optional[str],
        footer_html: Optional[str],
        variables_schema: Dict,
        page_size: str,
        margins: Dict,
        expiration_days: int
    ):
        self.id = template_id
        self.template_type = template_type
        self.name = name
        self.version = version
        self.html_template = html_template
        self.css_styles = css_styles
        self.header_html = header_html
        self.footer_html = footer_html
        self.variables_schema = variables_schema
        self.page_size = page_size
        self.margins = margins
        self.expiration_days = expiration_days

    def get_required_variables(self) -> List[str]:
        """Get list of required variable names."""
        return [
            name for name, schema in self.variables_schema.items()
            if schema.get("required", False)
        ]

    def validate_variables(self, variables: Dict) -> Dict[str, List[str]]:
        """
        Validate provided variables against schema.

        Returns dict with 'errors' and 'warnings' lists.
        """
        errors = []
        warnings = []

        for var_name, schema in self.variables_schema.items():
            value = variables.get(var_name)

            # Check required
            if schema.get("required", False) and not value:
                errors.append(f"Missing required variable: {var_name}")
                continue

            if value:
                # Check type
                var_type = schema.get("type", "string")
                if var_type == "currency" and not self._is_valid_currency(value):
                    errors.append(f"Invalid currency format for {var_name}: {value}")
                elif var_type == "date" and not self._is_valid_date(value):
                    errors.append(f"Invalid date format for {var_name}: {value}")
                elif var_type == "email" and not self._is_valid_email(value):
                    errors.append(f"Invalid email format for {var_name}: {value}")

        return {"errors": errors, "warnings": warnings}

    def render(self, variables: Dict) -> str:
        """Render the template with provided variables."""
        html = self.html_template

        # Replace all {{variable}} patterns
        for var_name, value in variables.items():
            pattern = r"\{\{\s*" + re.escape(var_name) + r"\s*\}\}"
            html = re.sub(pattern, str(value) if value else "", html)

        # Inject CSS
        if self.css_styles:
            html = html.replace("</head>", f"<style>{self.css_styles}</style></head>")

        return html

    @staticmethod
    def _is_valid_currency(value: Any) -> bool:
        try:
            float(str(value).replace(",", "").replace("$", ""))
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_valid_date(value: Any) -> bool:
        try:
            datetime.strptime(str(value), "%Y-%m-%d")
            return True
        except ValueError:
            try:
                datetime.strptime(str(value), "%m/%d/%Y")
                return True
            except ValueError:
                return False

    @staticmethod
    def _is_valid_email(value: Any) -> bool:
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        return bool(re.match(pattern, str(value)))


class LetterGenerationService:
    """
    Service for generating pre-qualification and pre-approval letters.
    """

    def __init__(self, db: Session):
        self.db = db
        self._template_cache: Dict[str, LetterTemplate] = {}

    # =========================================================================
    # TEMPLATE MANAGEMENT
    # =========================================================================

    def get_template(
        self,
        organization_id: int,
        template_type: str,
        version: Optional[int] = None
    ) -> Optional[LetterTemplate]:
        """
        Get a letter template by type.

        If version not specified, returns the active default.
        """
        cache_key = f"{organization_id}:{template_type}:{version or 'default'}"
        if cache_key in self._template_cache:
            return self._template_cache[cache_key]

        if version:
            query = """
                SELECT id, template_type, name, version, html_template,
                       css_styles, header_html, footer_html, variables_schema,
                       page_size, margins, expiration_days
                FROM letter_templates
                WHERE organization_id = :org_id
                    AND template_type = :type
                    AND version = :version
                    AND is_active = TRUE
            """
            params = {"org_id": organization_id, "type": template_type, "version": version}
        else:
            query = """
                SELECT id, template_type, name, version, html_template,
                       css_styles, header_html, footer_html, variables_schema,
                       page_size, margins, expiration_days
                FROM letter_templates
                WHERE organization_id = :org_id
                    AND template_type = :type
                    AND is_active = TRUE
                    AND is_default = TRUE
                ORDER BY version DESC
                LIMIT 1
            """
            params = {"org_id": organization_id, "type": template_type}

        result = self.db.execute(text(query), params).fetchone()

        if not result:
            logger.warning(f"No template found for {template_type} in org {organization_id}")
            return None

        template = LetterTemplate(
            template_id=result[0],
            template_type=result[1],
            name=result[2],
            version=result[3],
            html_template=result[4],
            css_styles=result[5],
            header_html=result[6],
            footer_html=result[7],
            variables_schema=result[8] or {},
            page_size=result[9] or "letter",
            margins=result[10] or {"top": "1in", "bottom": "1in", "left": "1in", "right": "1in"},
            expiration_days=result[11] or 90
        )

        self._template_cache[cache_key] = template
        return template

    def list_templates(
        self,
        organization_id: int,
        template_type: Optional[str] = None
    ) -> List[Dict]:
        """List available templates for an organization."""
        query = """
            SELECT id, template_type, name, version, is_default, created_at
            FROM letter_templates
            WHERE organization_id = :org_id AND is_active = TRUE
        """
        params = {"org_id": organization_id}

        if template_type:
            query += " AND template_type = :type"
            params["type"] = template_type

        query += " ORDER BY template_type, version DESC"

        results = self.db.execute(text(query), params).fetchall()

        return [
            {
                "id": r[0],
                "type": r[1],
                "name": r[2],
                "version": r[3],
                "is_default": r[4],
                "created_at": r[5].isoformat() if r[5] else None
            }
            for r in results
        ]

    # =========================================================================
    # LETTER GENERATION
    # =========================================================================

    def generate_letter(
        self,
        organization_id: int,
        loan_id: int,
        letter_type: str,
        variables: Dict,
        generated_by_user: Optional[int] = None,
        generated_by_realtor: Optional[int] = None,
        property_address: Optional[str] = None,
        purchase_price: Optional[Decimal] = None,
        template_version: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate a new letter for a loan.

        Returns:
            Dict with letter_id, html, pdf_url, expires_at, share_token
        """
        # Get template
        template = self.get_template(organization_id, letter_type, template_version)
        if not template:
            return {
                "success": False,
                "error": f"No template found for letter type: {letter_type}"
            }

        # Validate variables
        validation = template.validate_variables(variables)
        if validation["errors"]:
            return {
                "success": False,
                "error": "Variable validation failed",
                "validation_errors": validation["errors"]
            }

        # Add system variables
        variables = self._add_system_variables(variables, organization_id, loan_id)

        # Render HTML
        html_content = template.render(variables)

        # Calculate expiration
        expires_at = datetime.now(timezone.utc) + timedelta(days=template.expiration_days)

        # Generate share token
        share_token = secrets.token_urlsafe(32)

        # Get next version for this loan
        version = self._get_next_letter_version(loan_id, letter_type)

        # Store in database
        try:
            result = self.db.execute(text("""
                INSERT INTO pre_approval_letters (
                    organization_id, loan_id, template_id, letter_type, version,
                    generated_html, variables_used, property_address, purchase_price,
                    approved_amount, expires_at, generated_by, generated_by_realtor,
                    share_token
                ) VALUES (
                    :org_id, :loan_id, :template_id, :letter_type, :version,
                    :html, :variables, :property_address, :purchase_price,
                    :approved_amount, :expires_at, :generated_by, :generated_by_realtor,
                    :share_token
                )
                RETURNING id
            """), {
                "org_id": organization_id,
                "loan_id": loan_id,
                "template_id": template.id,
                "letter_type": letter_type,
                "version": version,
                "html": html_content,
                "variables": json.dumps(variables),
                "property_address": property_address,
                "purchase_price": purchase_price,
                "approved_amount": variables.get("prequal_amount") or variables.get("approved_amount"),
                "expires_at": expires_at,
                "generated_by": generated_by_user,
                "generated_by_realtor": generated_by_realtor,
                "share_token": share_token
            })
            letter_id = result.fetchone()[0]
            self.db.commit()

            logger.info(f"Generated {letter_type} letter {letter_id} for loan {loan_id}")

            return {
                "success": True,
                "letter_id": letter_id,
                "version": version,
                "html": html_content,
                "expires_at": expires_at.isoformat(),
                "share_token": share_token,
                "share_url": f"/letters/shared/{share_token}"
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error generating letter: {e}")
            return {"success": False, "error": "Internal server error"}

    def generate_pdf(self, letter_id: int) -> Optional[bytes]:
        """
        Generate PDF from letter HTML.

        Uses reportlab or weasyprint for PDF generation.
        """
        letter = self.get_letter(letter_id)
        if not letter:
            return None

        try:
            # Try using weasyprint if available
            try:
                from weasyprint import HTML
                pdf_bytes = HTML(string=letter["html"]).write_pdf()
                return pdf_bytes
            except ImportError:
                pass

            # Fallback: return HTML for client-side PDF generation
            logger.warning("PDF library not available, returning HTML for client-side generation")
            return letter["html"].encode("utf-8")

        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            return None

    def _add_system_variables(
        self,
        variables: Dict,
        organization_id: int,
        loan_id: int
    ) -> Dict:
        """Add system-generated variables to the template data."""
        # Add current date
        variables["letter_date"] = datetime.now().strftime("%B %d, %Y")

        # Get organization info
        org_info = self.db.execute(text("""
            SELECT name, nmls_number, address, phone, logo_url
            FROM organizations
            WHERE id = :org_id
        """), {"org_id": organization_id}).fetchone()

        if org_info:
            variables.setdefault("company_name", org_info[0])
            variables.setdefault("company_nmls", org_info[1])
            variables.setdefault("company_address", org_info[2])
            variables.setdefault("company_phone", org_info[3])
            variables.setdefault("company_logo", org_info[4])

        # Get loan officer info from loan
        lo_info = self.db.execute(text("""
            SELECT u.name, u.email, u.phone, u.nmls_number, u.title
            FROM loans l
            JOIN users u ON u.id = l.loan_officer_id
            WHERE l.id = :loan_id
        """), {"loan_id": loan_id}).fetchone()

        if lo_info:
            variables.setdefault("lo_name", lo_info[0])
            variables.setdefault("lo_email", lo_info[1])
            variables.setdefault("lo_phone", lo_info[2])
            variables.setdefault("lo_nmls", lo_info[3])
            variables.setdefault("lo_title", lo_info[4] or "Loan Officer")

        return variables

    def _get_next_letter_version(self, loan_id: int, letter_type: str) -> int:
        """Get next version number for a letter on a loan."""
        result = self.db.execute(text("""
            SELECT COALESCE(MAX(version), 0) + 1
            FROM pre_approval_letters
            WHERE loan_id = :loan_id AND letter_type = :letter_type
        """), {"loan_id": loan_id, "letter_type": letter_type}).fetchone()

        return result[0]

    # =========================================================================
    # LETTER RETRIEVAL
    # =========================================================================

    def get_letter(self, letter_id: int) -> Optional[Dict]:
        """Get a letter by ID."""
        result = self.db.execute(text("""
            SELECT
                pal.id, pal.loan_id, pal.letter_type, pal.version,
                pal.generated_html, pal.generated_pdf_url, pal.variables_used,
                pal.property_address, pal.purchase_price, pal.approved_amount,
                pal.issued_at, pal.expires_at, pal.is_void, pal.voided_at,
                pal.share_token, pal.download_count,
                lt.name as template_name
            FROM pre_approval_letters pal
            LEFT JOIN letter_templates lt ON lt.id = pal.template_id
            WHERE pal.id = :letter_id
        """), {"letter_id": letter_id}).fetchone()

        if not result:
            return None

        return {
            "id": result[0],
            "loan_id": result[1],
            "letter_type": result[2],
            "version": result[3],
            "html": result[4],
            "pdf_url": result[5],
            "variables": result[6],
            "property_address": result[7],
            "purchase_price": float(result[8]) if result[8] else None,
            "approved_amount": float(result[9]) if result[9] else None,
            "issued_at": result[10].isoformat() if result[10] else None,
            "expires_at": result[11].isoformat() if result[11] else None,
            "is_void": result[12],
            "voided_at": result[13].isoformat() if result[13] else None,
            "share_token": result[14],
            "download_count": result[15],
            "template_name": result[16],
            "is_expired": result[11] < datetime.now(timezone.utc) if result[11] else False
        }

    def get_letter_by_share_token(self, share_token: str) -> Optional[Dict]:
        """Get a letter by its share token."""
        result = self.db.execute(text("""
            SELECT id FROM pre_approval_letters
            WHERE share_token = :token
                AND is_void = FALSE
                AND expires_at > CURRENT_TIMESTAMP
        """), {"token": share_token}).fetchone()

        if not result:
            return None

        return self.get_letter(result[0])

    def get_letters_for_loan(
        self,
        loan_id: int,
        include_void: bool = False
    ) -> List[Dict]:
        """Get all letters for a loan."""
        query = """
            SELECT
                id, letter_type, version, property_address,
                approved_amount, issued_at, expires_at, is_void,
                download_count
            FROM pre_approval_letters
            WHERE loan_id = :loan_id
        """
        if not include_void:
            query += " AND is_void = FALSE"
        query += " ORDER BY issued_at DESC"

        results = self.db.execute(text(query), {"loan_id": loan_id}).fetchall()

        return [
            {
                "id": r[0],
                "letter_type": r[1],
                "version": r[2],
                "property_address": r[3],
                "approved_amount": float(r[4]) if r[4] else None,
                "issued_at": r[5].isoformat() if r[5] else None,
                "expires_at": r[6].isoformat() if r[6] else None,
                "is_void": r[7],
                "download_count": r[8],
                "is_expired": r[6] < datetime.now(timezone.utc) if r[6] else False
            }
            for r in results
        ]

    # =========================================================================
    # LETTER MANAGEMENT
    # =========================================================================

    def void_letter(
        self,
        letter_id: int,
        voided_by: int,
        reason: str
    ) -> Dict[str, Any]:
        """Void a letter."""
        try:
            self.db.execute(text("""
                UPDATE pre_approval_letters
                SET is_void = TRUE,
                    voided_at = CURRENT_TIMESTAMP,
                    voided_by = :voided_by,
                    void_reason = :reason,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :letter_id
            """), {
                "letter_id": letter_id,
                "voided_by": voided_by,
                "reason": reason
            })
            self.db.commit()

            logger.info(f"Voided letter {letter_id} by user {voided_by}")
            return {"success": True, "letter_id": letter_id}

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error voiding letter: {e}")
            return {"success": False, "error": "Internal server error"}

    def record_download(self, letter_id: int):
        """Record that a letter was downloaded."""
        try:
            self.db.execute(text("""
                UPDATE pre_approval_letters
                SET download_count = download_count + 1,
                    last_downloaded_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :letter_id
            """), {"letter_id": letter_id})
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error recording download: {e}")
            self.db.rollback()

    def regenerate_share_token(self, letter_id: int) -> Optional[str]:
        """Regenerate the share token for a letter."""
        new_token = secrets.token_urlsafe(32)

        try:
            self.db.execute(text("""
                UPDATE pre_approval_letters
                SET share_token = :token,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :letter_id
            """), {"letter_id": letter_id, "token": new_token})
            self.db.commit()
            return new_token
        except SQLAlchemyError as e:
            logger.error(f"Error regenerating token: {e}")
            self.db.rollback()
            return None


class LetterRateLimiter:
    """Rate limiting for letter generation."""

    def __init__(self, db: Session):
        self.db = db

    def check_limit(
        self,
        organization_id: int,
        letter_type: str
    ) -> Dict[str, Any]:
        """
        Check if letter generation is within rate limits.

        Returns:
            Dict with 'allowed' bool and current usage stats
        """
        # Get policy
        policy = self.db.execute(text("""
            SELECT
                max_per_hour, max_per_day, max_per_month,
                current_hour_usage, current_day_usage, current_month_usage,
                hour_reset_at, day_reset_at, month_reset_at
            FROM portal_limit_policies
            WHERE policy_type = 'letter_generation'
                AND policy_key = :letter_type
                AND (organization_id = :org_id OR organization_id IS NULL)
                AND is_active = TRUE
            ORDER BY organization_id NULLS LAST
            LIMIT 1
        """), {"org_id": organization_id, "letter_type": letter_type}).fetchone()

        if not policy:
            # No limit configured
            return {"allowed": True, "reason": "No limits configured"}

        now = datetime.now(timezone.utc)

        # Reset counters if needed
        hour_usage = policy[3]
        day_usage = policy[4]
        month_usage = policy[5]

        if policy[6] and (now - policy[6]).total_seconds() > 3600:
            hour_usage = 0
        if policy[7] and (now - policy[7]).days >= 1:
            day_usage = 0
        if policy[8] and (now - policy[8]).days >= 30:
            month_usage = 0

        # Check limits
        if policy[0] and hour_usage >= policy[0]:
            return {
                "allowed": False,
                "reason": f"Hourly limit reached ({policy[0]} letters/hour)",
                "retry_after": 3600
            }

        if policy[1] and day_usage >= policy[1]:
            return {
                "allowed": False,
                "reason": f"Daily limit reached ({policy[1]} letters/day)",
                "retry_after": 86400
            }

        if policy[2] and month_usage >= policy[2]:
            return {
                "allowed": False,
                "reason": f"Monthly limit reached ({policy[2]} letters/month)",
                "retry_after": 86400 * 30
            }

        return {
            "allowed": True,
            "usage": {
                "hour": hour_usage,
                "day": day_usage,
                "month": month_usage
            },
            "limits": {
                "hour": policy[0],
                "day": policy[1],
                "month": policy[2]
            }
        }

    def increment_usage(self, organization_id: int, letter_type: str):
        """Increment usage counters after generating a letter."""
        try:
            self.db.execute(text("""
                UPDATE portal_limit_policies
                SET current_hour_usage = current_hour_usage + 1,
                    current_day_usage = current_day_usage + 1,
                    current_month_usage = current_month_usage + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE policy_type = 'letter_generation'
                    AND policy_key = :letter_type
                    AND (organization_id = :org_id OR organization_id IS NULL)
            """), {"org_id": organization_id, "letter_type": letter_type})
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error incrementing usage: {e}")
            self.db.rollback()
