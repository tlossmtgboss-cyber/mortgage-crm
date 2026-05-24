"""
Email Template Management for Call Intelligence

Externalizes email and SMS templates from code to configuration files,
enabling:
- Easy editing by non-developers
- Per-organization customization
- Template versioning
- A/B testing of message variants

Templates are loaded from YAML files with placeholder support.
Placeholders use {variable_name} format.

Usage:
    from services.call_intelligence.email_templates import (
        TemplateManager,
        get_template_manager,
    )

    # Load templates
    manager = get_template_manager()

    # Render a template
    subject, body = manager.render_email(
        template_id="welcome",
        variables={
            "first_name": "John",
            "company_name": "ABC Mortgage",
            "loan_purpose": "home purchase",
        }
    )

    # Get SMS template
    message = manager.render_sms(
        template_id="appointment_reminder",
        variables={...}
    )
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import yaml

logger = logging.getLogger(__name__)


# =============================================================================
# Template Data Classes
# =============================================================================

@dataclass
class EmailTemplate:
    """Email template definition."""
    id: str
    name: str
    subject: str
    body: str
    category: str = "general"  # welcome, documents, prequal, appointment, followup
    description: str = ""
    required_variables: List[str] = field(default_factory=list)
    optional_variables: List[str] = field(default_factory=list)
    default_values: Dict[str, Any] = field(default_factory=dict)
    html_body: Optional[str] = None  # Optional HTML version
    version: str = "1.0"
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "subject": self.subject,
            "body": self.body,
            "category": self.category,
            "description": self.description,
            "required_variables": self.required_variables,
            "optional_variables": self.optional_variables,
            "default_values": self.default_values,
            "version": self.version,
            "active": self.active,
        }


@dataclass
class SMSTemplate:
    """SMS template definition."""
    id: str
    name: str
    message: str
    category: str = "general"
    description: str = ""
    required_variables: List[str] = field(default_factory=list)
    default_values: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "message": self.message,
            "category": self.category,
            "description": self.description,
            "required_variables": self.required_variables,
            "default_values": self.default_values,
            "version": self.version,
            "active": self.active,
        }


@dataclass
class TemplateRenderResult:
    """Result of template rendering."""
    success: bool
    content: str
    subject: Optional[str] = None  # For emails
    html_content: Optional[str] = None  # For HTML emails
    missing_variables: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# =============================================================================
# Default Templates (Fallback)
# =============================================================================

DEFAULT_EMAIL_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "welcome": {
        "id": "welcome",
        "name": "Welcome Email",
        "category": "welcome",
        "description": "Sent after initial call to welcome borrower",
        "subject": "Welcome to {company_name} - Your Mortgage Journey Starts Here",
        "body": """Hi {first_name},

Thank you for speaking with us about your mortgage needs. We're excited to help you with your {loan_purpose} goals.

Based on our conversation, here's a quick summary:
- Loan Purpose: {loan_purpose}
- Estimated Amount: ${estimated_amount}
- Target Timeline: {target_timeline}

Your next steps:
{next_steps}

If you have any questions, please don't hesitate to reach out.

Best regards,
{lo_name}
{company_name}
""",
        "required_variables": ["first_name", "company_name", "lo_name"],
        "optional_variables": ["loan_purpose", "estimated_amount", "target_timeline", "next_steps"],
        "default_values": {
            "loan_purpose": "home financing",
            "estimated_amount": "TBD",
            "target_timeline": "As soon as possible",
            "next_steps": "• Complete your full application online\n• Gather required documents\n• Schedule a follow-up call",
        },
    },
    "document_request": {
        "id": "document_request",
        "name": "Document Request",
        "category": "documents",
        "description": "Request required documents from borrower",
        "subject": "Documents Needed for Your Mortgage Application",
        "body": """Hi {first_name},

To move forward with your mortgage application, we'll need the following documents:

Required Documents:
{required_documents}

You can securely upload your documents through our portal at: {upload_link}

Please try to submit these within the next {deadline_days} days to keep your application on track.

If you have any questions about what's needed, just reply to this email.

Best regards,
{lo_name}
{company_name}
""",
        "required_variables": ["first_name", "required_documents", "lo_name", "company_name"],
        "optional_variables": ["upload_link", "deadline_days"],
        "default_values": {
            "upload_link": "your secure portal",
            "deadline_days": "5",
        },
    },
    "prequal_results": {
        "id": "prequal_results",
        "name": "Pre-Qualification Results",
        "category": "prequal",
        "description": "Send pre-qualification calculation results",
        "subject": "Your Pre-Qualification Results Are Ready",
        "body": """Hi {first_name},

Great news! Based on the information you provided, here are your pre-qualification results:

Qualification Status: {qualification_status}
Maximum Purchase Price: ${max_purchase_price}
Estimated Monthly Payment: ${monthly_payment}
Estimated Rate: {estimated_rate}%

Loan Programs You Qualify For:
{qualified_programs}

{recommendations}

Ready to take the next step? {next_step_cta}

Best regards,
{lo_name}
{company_name}
""",
        "required_variables": ["first_name", "qualification_status", "lo_name", "company_name"],
        "optional_variables": ["max_purchase_price", "monthly_payment", "estimated_rate", "qualified_programs", "recommendations", "next_step_cta"],
        "default_values": {
            "max_purchase_price": "Contact us for details",
            "monthly_payment": "Contact us for details",
            "estimated_rate": "Current market rate",
            "qualified_programs": "Multiple options available",
            "recommendations": "",
            "next_step_cta": "Schedule a call to discuss your options.",
        },
    },
    "appointment_confirmation": {
        "id": "appointment_confirmation",
        "name": "Appointment Confirmation",
        "category": "appointment",
        "description": "Confirm scheduled appointment",
        "subject": "Appointment Confirmed: {appointment_type} on {appointment_date}",
        "body": """Hi {first_name},

Your appointment has been confirmed:

Date: {appointment_date}
Time: {appointment_time}
Type: {appointment_type}
{meeting_link_section}

What to prepare:
{preparation_items}

Need to reschedule? Click here: {reschedule_link}

We look forward to speaking with you!

Best regards,
{lo_name}
{company_name}
""",
        "required_variables": ["first_name", "appointment_date", "appointment_time", "appointment_type", "lo_name", "company_name"],
        "optional_variables": ["meeting_link_section", "preparation_items", "reschedule_link"],
        "default_values": {
            "meeting_link_section": "",
            "preparation_items": "• Have your ID ready\n• Prepare any questions\n• Have recent financial documents accessible",
            "reschedule_link": "Contact us to reschedule",
        },
    },
    "followup": {
        "id": "followup",
        "name": "Follow-up Email",
        "category": "followup",
        "description": "Follow up after initial contact",
        "subject": "Following Up on Your Mortgage Inquiry",
        "body": """Hi {first_name},

I wanted to follow up on our recent conversation about your {loan_purpose}.

{personalized_message}

Is there anything I can help clarify or any questions you have?

Best regards,
{lo_name}
{company_name}
""",
        "required_variables": ["first_name", "lo_name", "company_name"],
        "optional_variables": ["loan_purpose", "personalized_message"],
        "default_values": {
            "loan_purpose": "mortgage needs",
            "personalized_message": "I'm here to help whenever you're ready to move forward.",
        },
    },
    "callback_scheduled": {
        "id": "callback_scheduled",
        "name": "Callback Scheduled",
        "category": "appointment",
        "description": "Confirm a callback was scheduled during the call",
        "subject": "Your Callback is Scheduled",
        "body": """Hi {first_name},

As discussed, I've scheduled a callback for:

Date: {callback_date}
Time: {callback_time}

During this call, we'll {callback_purpose}.

If this time no longer works, please reply to this email to reschedule.

Talk soon!

Best regards,
{lo_name}
{company_name}
""",
        "required_variables": ["first_name", "callback_date", "callback_time", "lo_name", "company_name"],
        "optional_variables": ["callback_purpose"],
        "default_values": {
            "callback_purpose": "continue our discussion about your mortgage options",
        },
    },
}

DEFAULT_SMS_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "welcome": {
        "id": "welcome",
        "name": "Welcome SMS",
        "category": "welcome",
        "description": "Initial welcome text message",
        "message": "Hi {first_name}, thanks for speaking with {company_name} about your mortgage! We'll be in touch soon with next steps.",
        "required_variables": ["first_name", "company_name"],
    },
    "document_reminder": {
        "id": "document_reminder",
        "name": "Document Reminder",
        "category": "documents",
        "description": "Remind about pending documents",
        "message": "Hi {first_name}, friendly reminder: we're still waiting on some documents for your mortgage application. Check your email or call us at {phone_number} to discuss.",
        "required_variables": ["first_name"],
        "default_values": {"phone_number": "our office"},
    },
    "appointment_reminder": {
        "id": "appointment_reminder",
        "name": "Appointment Reminder",
        "category": "appointment",
        "description": "Remind about upcoming appointment",
        "message": "Reminder: Your {appointment_type} is {time_until} at {appointment_time}. Reply YES to confirm or call us to reschedule.",
        "required_variables": ["appointment_type", "appointment_time"],
        "default_values": {"time_until": "tomorrow"},
    },
    "callback_reminder": {
        "id": "callback_reminder",
        "name": "Callback Reminder",
        "category": "appointment",
        "description": "Remind about scheduled callback",
        "message": "Hi {first_name}, just a reminder that we have a callback scheduled for {callback_time}. Looking forward to speaking with you! - {lo_name}",
        "required_variables": ["first_name", "callback_time", "lo_name"],
    },
}


# =============================================================================
# Template Manager
# =============================================================================

class TemplateManager:
    """
    Manages email and SMS templates.

    Supports loading templates from:
    - YAML configuration files
    - Database (organization-specific overrides)
    - Default fallbacks
    """

    def __init__(
        self,
        templates_dir: Optional[str] = None,
        db_session=None,
        organization_id: Optional[int] = None,
    ):
        """
        Initialize template manager.

        Args:
            templates_dir: Directory containing template YAML files
            db_session: Optional database session for org-specific templates
            organization_id: Optional organization ID for template overrides
        """
        self.templates_dir = templates_dir
        self.db = db_session
        self.organization_id = organization_id

        self._email_templates: Dict[str, EmailTemplate] = {}
        self._sms_templates: Dict[str, SMSTemplate] = {}

        self._load_templates()

    def _load_templates(self) -> None:
        """Load templates from all sources."""
        # 1. Load default templates
        self._load_default_templates()

        # 2. Load from YAML files (override defaults)
        if self.templates_dir:
            self._load_yaml_templates()

        # 3. Load from database (org-specific overrides)
        if self.db and self.organization_id:
            self._load_db_templates()

        logger.info(
            f"Loaded {len(self._email_templates)} email templates, "
            f"{len(self._sms_templates)} SMS templates"
        )

    def _load_default_templates(self) -> None:
        """Load default templates from constants."""
        for template_id, data in DEFAULT_EMAIL_TEMPLATES.items():
            self._email_templates[template_id] = EmailTemplate(
                id=data["id"],
                name=data["name"],
                subject=data["subject"],
                body=data["body"],
                category=data.get("category", "general"),
                description=data.get("description", ""),
                required_variables=data.get("required_variables", []),
                optional_variables=data.get("optional_variables", []),
                default_values=data.get("default_values", {}),
            )

        for template_id, data in DEFAULT_SMS_TEMPLATES.items():
            self._sms_templates[template_id] = SMSTemplate(
                id=data["id"],
                name=data["name"],
                message=data["message"],
                category=data.get("category", "general"),
                description=data.get("description", ""),
                required_variables=data.get("required_variables", []),
                default_values=data.get("default_values", {}),
            )

    def _load_yaml_templates(self) -> None:
        """Load templates from YAML files."""
        templates_path = Path(self.templates_dir)

        if not templates_path.exists():
            logger.warning(f"Templates directory not found: {self.templates_dir}")
            return

        # Load email templates
        email_file = templates_path / "email_templates.yaml"
        if email_file.exists():
            try:
                with open(email_file, "r") as f:
                    data = yaml.safe_load(f)

                for template_data in data.get("templates", []):
                    template = EmailTemplate(
                        id=template_data["id"],
                        name=template_data.get("name", template_data["id"]),
                        subject=template_data["subject"],
                        body=template_data["body"],
                        category=template_data.get("category", "general"),
                        description=template_data.get("description", ""),
                        required_variables=template_data.get("required_variables", []),
                        optional_variables=template_data.get("optional_variables", []),
                        default_values=template_data.get("default_values", {}),
                        html_body=template_data.get("html_body"),
                        version=template_data.get("version", "1.0"),
                        active=template_data.get("active", True),
                    )
                    self._email_templates[template.id] = template
                    logger.debug(f"Loaded email template: {template.id}")

            except Exception as e:
                logger.error(f"Error loading email templates: {e}")

        # Load SMS templates
        sms_file = templates_path / "sms_templates.yaml"
        if sms_file.exists():
            try:
                with open(sms_file, "r") as f:
                    data = yaml.safe_load(f)

                for template_data in data.get("templates", []):
                    template = SMSTemplate(
                        id=template_data["id"],
                        name=template_data.get("name", template_data["id"]),
                        message=template_data["message"],
                        category=template_data.get("category", "general"),
                        description=template_data.get("description", ""),
                        required_variables=template_data.get("required_variables", []),
                        default_values=template_data.get("default_values", {}),
                        version=template_data.get("version", "1.0"),
                        active=template_data.get("active", True),
                    )
                    self._sms_templates[template.id] = template
                    logger.debug(f"Loaded SMS template: {template.id}")

            except Exception as e:
                logger.error(f"Error loading SMS templates: {e}")

    def _load_db_templates(self) -> None:
        """Load organization-specific templates from database."""
        try:
            from sqlalchemy import text

            # Load email templates
            result = self.db.execute(
                text("""
                    SELECT id, name, subject, body, category, description,
                           required_variables, optional_variables, default_values,
                           html_body, version, active
                    FROM email_templates
                    WHERE organization_id = :org_id AND active = true
                """),
                {"org_id": self.organization_id}
            )

            for row in result:
                template = EmailTemplate(
                    id=row.id,
                    name=row.name,
                    subject=row.subject,
                    body=row.body,
                    category=row.category or "general",
                    description=row.description or "",
                    required_variables=row.required_variables or [],
                    optional_variables=row.optional_variables or [],
                    default_values=row.default_values or {},
                    html_body=row.html_body,
                    version=row.version or "1.0",
                    active=row.active,
                )
                self._email_templates[template.id] = template

            # Load SMS templates
            result = self.db.execute(
                text("""
                    SELECT id, name, message, category, description,
                           required_variables, default_values, version, active
                    FROM sms_templates
                    WHERE organization_id = :org_id AND active = true
                """),
                {"org_id": self.organization_id}
            )

            for row in result:
                template = SMSTemplate(
                    id=row.id,
                    name=row.name,
                    message=row.message,
                    category=row.category or "general",
                    description=row.description or "",
                    required_variables=row.required_variables or [],
                    default_values=row.default_values or {},
                    version=row.version or "1.0",
                    active=row.active,
                )
                self._sms_templates[template.id] = template

        except Exception as e:
            logger.warning(f"Could not load DB templates: {e}")

    def render_email(
        self,
        template_id: str,
        variables: Dict[str, Any],
    ) -> TemplateRenderResult:
        """
        Render an email template with variables.

        Args:
            template_id: Template identifier
            variables: Variables to substitute in template

        Returns:
            TemplateRenderResult with rendered content
        """
        template = self._email_templates.get(template_id)
        if not template:
            return TemplateRenderResult(
                success=False,
                content="",
                errors=[f"Template not found: {template_id}"],
            )

        if not template.active:
            return TemplateRenderResult(
                success=False,
                content="",
                errors=[f"Template is inactive: {template_id}"],
            )

        # Merge with default values
        merged_vars = {**template.default_values, **variables}

        # Check for missing required variables
        missing = [v for v in template.required_variables if v not in merged_vars or merged_vars[v] is None]
        if missing:
            return TemplateRenderResult(
                success=False,
                content="",
                missing_variables=missing,
                errors=[f"Missing required variables: {', '.join(missing)}"],
            )

        # Render template
        try:
            subject = self._render_string(template.subject, merged_vars)
            body = self._render_string(template.body, merged_vars)
            html_body = None
            if template.html_body:
                html_body = self._render_string(template.html_body, merged_vars)

            return TemplateRenderResult(
                success=True,
                content=body,
                subject=subject,
                html_content=html_body,
            )

        except Exception as e:
            return TemplateRenderResult(
                success=False,
                content="",
                errors=[f"Render error: {str(e)}"],
            )

    def render_sms(
        self,
        template_id: str,
        variables: Dict[str, Any],
    ) -> TemplateRenderResult:
        """
        Render an SMS template with variables.

        Args:
            template_id: Template identifier
            variables: Variables to substitute in template

        Returns:
            TemplateRenderResult with rendered content
        """
        template = self._sms_templates.get(template_id)
        if not template:
            return TemplateRenderResult(
                success=False,
                content="",
                errors=[f"Template not found: {template_id}"],
            )

        if not template.active:
            return TemplateRenderResult(
                success=False,
                content="",
                errors=[f"Template is inactive: {template_id}"],
            )

        # Merge with default values
        merged_vars = {**template.default_values, **variables}

        # Check for missing required variables
        missing = [v for v in template.required_variables if v not in merged_vars or merged_vars[v] is None]
        if missing:
            return TemplateRenderResult(
                success=False,
                content="",
                missing_variables=missing,
                errors=[f"Missing required variables: {', '.join(missing)}"],
            )

        # Render template
        try:
            message = self._render_string(template.message, merged_vars)

            return TemplateRenderResult(
                success=True,
                content=message,
            )

        except Exception as e:
            return TemplateRenderResult(
                success=False,
                content="",
                errors=[f"Render error: {str(e)}"],
            )

    def _render_string(self, template: str, variables: Dict[str, Any]) -> str:
        """
        Render a template string with variables.

        Uses {variable_name} format. Handles missing variables gracefully.
        """
        def replace_var(match):
            var_name = match.group(1)
            # Handle format specifiers like {amount:,.0f}
            if ":" in var_name:
                var_name, fmt = var_name.split(":", 1)
                value = variables.get(var_name, "")
                if value and fmt:
                    try:
                        return format(value, fmt)
                    except (ValueError, TypeError):
                        return str(value)
            return str(variables.get(var_name, f"{{{var_name}}}"))

        # Match {variable_name} or {variable_name:format}
        pattern = r"\{([^}]+)\}"
        return re.sub(pattern, replace_var, template)

    def get_template(self, template_id: str, template_type: str = "email") -> Optional[Dict[str, Any]]:
        """Get template by ID."""
        if template_type == "email":
            template = self._email_templates.get(template_id)
            return template.to_dict() if template else None
        else:
            template = self._sms_templates.get(template_id)
            return template.to_dict() if template else None

    def list_templates(self, category: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        List all available templates.

        Args:
            category: Optional filter by category

        Returns:
            Dict with email and sms template lists
        """
        email_templates = []
        for template in self._email_templates.values():
            if template.active and (category is None or template.category == category):
                email_templates.append({
                    "id": template.id,
                    "name": template.name,
                    "category": template.category,
                    "description": template.description,
                    "required_variables": template.required_variables,
                })

        sms_templates = []
        for template in self._sms_templates.values():
            if template.active and (category is None or template.category == category):
                sms_templates.append({
                    "id": template.id,
                    "name": template.name,
                    "category": template.category,
                    "description": template.description,
                    "required_variables": template.required_variables,
                })

        return {
            "email": email_templates,
            "sms": sms_templates,
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_template_manager: Optional[TemplateManager] = None


def get_template_manager(
    templates_dir: Optional[str] = None,
    db_session=None,
    organization_id: Optional[int] = None,
    force_reload: bool = False,
) -> TemplateManager:
    """
    Get or create the template manager singleton.

    Args:
        templates_dir: Directory containing template YAML files
        db_session: Optional database session
        organization_id: Optional organization ID
        force_reload: Force reload templates

    Returns:
        TemplateManager instance
    """
    global _template_manager

    if _template_manager is None or force_reload:
        # Default templates directory
        if templates_dir is None:
            templates_dir = os.getenv(
                "EMAIL_TEMPLATES_DIR",
                str(Path(__file__).parent / "templates")
            )

        _template_manager = TemplateManager(
            templates_dir=templates_dir,
            db_session=db_session,
            organization_id=organization_id,
        )

    return _template_manager


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "EmailTemplate",
    "SMSTemplate",
    "TemplateRenderResult",
    "TemplateManager",
    "get_template_manager",
    "DEFAULT_EMAIL_TEMPLATES",
    "DEFAULT_SMS_TEMPLATES",
]
