# backend/integrations/sms_template_engine.py
# SMS template management with variable substitution for mortgage workflows

import re
import logging
from typing import Optional, List, Dict
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Built-in mortgage workflow templates
BUILTIN_TEMPLATES = {
    "welcome": {
        "name": "Welcome New Lead",
        "body": "Hi {{first_name}}, thanks for your interest in Perennia AI Mortgage! I'm {{agent_name}}, your dedicated loan officer. Ready to help you get the best rate.",
        "variables": ["first_name", "agent_name"],
        "category": "nurture",
    },
    "rate_update": {
        "name": "Rate Update Alert",
        "body": "Hi {{first_name}}, great news! 30-yr fixed rates moved to {{rate}}% today. Based on your {{loan_amount}} target, your est. payment is {{monthly_payment}}/mo. Want to lock in? Reply YES or call {{agent_phone}}.",
        "variables": ["first_name", "rate", "loan_amount", "monthly_payment", "agent_phone"],
        "category": "rate_alert",
    },
    "follow_up": {
        "name": "Follow Up",
        "body": "Hi {{first_name}}, just checking in on your home purchase plans. I have some great options for you at {{property_address}}. Shall we set up a quick 15-min call? - {{agent_name}}, {{agent_phone}}.",
        "variables": ["first_name", "property_address", "agent_name", "agent_phone"],
        "category": "follow_up",
    },
    "pre_approval": {
        "name": "Pre-Approval Ready",
        "body": "Great news {{first_name}}! Your pre-approval for {{approval_amount}} is ready. Valid through {{expiry_date}}. Log in to download: {{portal_link}}. Questions? Call {{agent_phone}}.",
        "variables": ["first_name", "approval_amount", "expiry_date", "portal_link", "agent_phone"],
        "category": "milestone",
    },
    "closing_reminder": {
        "name": "Closing Day Reminder",
        "body": "Reminder {{first_name}}: Your closing is {{closing_date}} at {{closing_time}} at {{closing_address}}. Bring your ID and certified funds for {{cash_to_close}}. Questions? {{agent_phone}}.",
        "variables": ["first_name", "closing_date", "closing_time", "closing_address", "cash_to_close", "agent_phone"],
        "category": "milestone",
    },
    "document_request": {
        "name": "Document Request",
        "body": "Hi {{first_name}}, we need {{document_name}} to move your loan forward. Please upload at {{portal_link}} by {{due_date}}. Need help? Reply or call {{agent_phone}}.",
        "variables": ["first_name", "document_name", "portal_link", "due_date", "agent_phone"],
        "category": "documents",
    },
}


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------
def render_template(
    template_body: str,
    variables: Dict[str, str],
    strict: bool = False,
) -> str:
    """
    Substitute {{variable}} placeholders with values.
    If strict=True, raises ValueError for missing variables.
    Otherwise leaves them as-is with [MISSING: var] marker.
    """
    def replace_var(match):
        var_name = match.group(1).strip()
        value = variables.get(var_name)
        if value is None:
            if strict:
                raise ValueError(f"Missing required template variable: {var_name}")
            return f"[MISSING: {var_name}]"
        return str(value)

    return re.sub(r"\{\{([^}]+)\}\}", replace_var, template_body)


def get_template_variables(template_body: str) -> List[str]:
    """Extract all variable names from a template string."""
    return list(set(re.findall(r"\{\{([^}]+)\}\}", template_body)))


def validate_template(template_body: str, provided_vars: Dict[str, str]) -> List[str]:
    """Return list of missing variable names."""
    required = get_template_variables(template_body)
    return [v for v in required if v.strip() not in provided_vars]


# ---------------------------------------------------------------------------
# DB-backed template CRUD
# ---------------------------------------------------------------------------
def get_template(db: Session, template_id: int) -> Optional[dict]:
    """Fetch a template by ID."""
    try:
        row = db.execute(
            text("""
                SELECT id, name, body, variables, category, active, created_at
                FROM sms_templates
                WHERE id = :id
            """),
            {"id": template_id},
        ).fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "name": row[1],
            "body": row[2],
            "variables": row[3] or [],
            "category": row[4],
            "active": row[5],
            "created_at": str(row[6]) if row[6] else None,
        }
    except Exception as e:
        logger.error(f"Failed to get template {template_id}: {e}")
        return None


def get_templates_by_category(db: Session, category: Optional[str] = None) -> List[dict]:
    """List all active templates, optionally filtered by category."""
    try:
        if category:
            rows = db.execute(
                text("""
                    SELECT id, name, body, variables, category, active
                    FROM sms_templates
                    WHERE active = TRUE AND category = :cat
                    ORDER BY name
                """),
                {"cat": category},
            ).fetchall()
        else:
            rows = db.execute(
                text("""
                    SELECT id, name, body, variables, category, active
                    FROM sms_templates
                    WHERE active = TRUE
                    ORDER BY category, name
                """)
            ).fetchall()

        return [
            {"id": r[0], "name": r[1], "body": r[2],
             "variables": r[3] or [], "category": r[4], "active": r[5]}
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Failed to list templates: {e}")
        return []


def create_template(
    db: Session,
    name: str,
    body: str,
    category: str = "general",
    user_id: Optional[int] = None,
) -> Optional[int]:
    """Create a new SMS template. Returns ID."""
    variables = get_template_variables(body)
    try:
        result = db.execute(
            text("""
                INSERT INTO sms_templates
                  (name, body, variables, category, active, created_by, created_at)
                VALUES
                  (:name, :body, :variables, :category, TRUE, :user_id, NOW())
                RETURNING id
            """),
            {
                "name": name,
                "body": body,
                "variables": variables,
                "category": category,
                "user_id": user_id,
            },
        )
        db.commit()
        row = result.fetchone()
        return row[0] if row else None
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create template: {e}")
        return None


def render_template_by_id(
    db: Session,
    template_id: int,
    variables: Dict[str, str],
) -> Optional[str]:
    """Fetch template and render with provided variables."""
    tmpl = get_template(db, template_id)
    if not tmpl:
        # Try built-in templates by checking if template_id maps to a key
        return None
    return render_template(tmpl["body"], variables)


def render_builtin(
    template_key: str,
    variables: Dict[str, str],
    strict: bool = False,
) -> Optional[str]:
    """Render one of the built-in mortgage workflow templates."""
    tmpl = BUILTIN_TEMPLATES.get(template_key)
    if not tmpl:
        return None
    return render_template(tmpl["body"], variables, strict=strict)


def seed_builtin_templates(db: Session):
    """Seed the database with built-in templates (idempotent)."""
    for key, tmpl in BUILTIN_TEMPLATES.items():
        try:
            db.execute(
                text("""
                    INSERT INTO sms_templates
                      (name, body, variables, category, active, created_at)
                    VALUES
                      (:name, :body, :variables, :category, TRUE, NOW())
                    ON CONFLICT (name) DO NOTHING
                """),
                {
                    "name": tmpl["name"],
                    "body": tmpl["body"],
                    "variables": tmpl["variables"],
                    "category": tmpl["category"],
                },
            )
        except Exception as e:
            logger.warning(f"Seeding template {key}: {e}")
    try:
        db.commit()
        logger.info("Built-in SMS templates seeded")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed templates: {e}")
