"""
Tenant Email Template Routes — WL-003

Per-tenant transactional email template management with full composition:
    GET    /api/v1/admin/email-templates              — List org templates
    GET    /api/v1/admin/email-templates/{id}          — Get single template
    POST   /api/v1/admin/email-templates               — Create template
    PUT    /api/v1/admin/email-templates/{id}           — Update template
    DELETE /api/v1/admin/email-templates/{id}           — Delete template
    POST   /api/v1/admin/email-templates/{id}/preview   — Preview with merge fields
    POST   /api/v1/admin/email-templates/reset-defaults — Reset to system defaults
"""
from fastapi import Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timezone
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Schemas
# ============================================================================

class EmailTemplateCreate(BaseModel):
    template_type: str  # welcome, follow_up, rate_alert, document_request, closing_update, nurture, custom
    name: str
    subject: str
    body_html: str
    body_text: Optional[str] = None
    cta_text: Optional[str] = None
    cta_url: Optional[str] = None
    merge_fields: Optional[List[str]] = None  # e.g. ["first_name", "loan_amount", "rate"]
    category: str = "transactional"  # transactional, marketing, system
    is_active: bool = True


class EmailTemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    cta_text: Optional[str] = None
    cta_url: Optional[str] = None
    merge_fields: Optional[List[str]] = None
    is_active: Optional[bool] = None


class TemplatePreviewRequest(BaseModel):
    merge_data: Dict[str, str]  # e.g. {"first_name": "John", "loan_amount": "$350,000"}


# ============================================================================
# System Default Templates
# ============================================================================

SYSTEM_DEFAULT_TEMPLATES = [
    {
        "template_type": "welcome",
        "name": "Welcome Email",
        "subject": "Welcome to {{company_name}}, {{first_name}}!",
        "body_html": """<div style="font-family: Arial, sans-serif; max-width: 600px;">
<p>Hi {{first_name}},</p>
<p>Welcome to <strong>{{company_name}}</strong>! We're excited to help you with your mortgage journey.</p>
<p>Your dedicated loan officer, <strong>{{lo_name}}</strong>, is ready to assist you every step of the way.</p>
<p>Here's what you can do next:</p>
<ul>
<li>Upload your documents securely through your portal</li>
<li>Check current rates personalized for you</li>
<li>Schedule a consultation at your convenience</li>
</ul>
<p>{{cta_button}}</p>
<p>Best regards,<br>{{lo_name}}<br>{{lo_title}}<br>NMLS# {{lo_nmls}}</p>
</div>""",
        "body_text": "Hi {{first_name}}, Welcome to {{company_name}}! Your loan officer {{lo_name}} is ready to help.",
        "cta_text": "Access Your Portal",
        "cta_url": "{{portal_url}}",
        "merge_fields": ["first_name", "company_name", "lo_name", "lo_title", "lo_nmls", "portal_url"],
        "category": "transactional",
    },
    {
        "template_type": "document_request",
        "name": "Document Request",
        "subject": "Action Required: Documents needed for your loan — {{loan_number}}",
        "body_html": """<div style="font-family: Arial, sans-serif; max-width: 600px;">
<p>Hi {{first_name}},</p>
<p>To keep your loan application moving forward, we need the following documents:</p>
<ul>{{document_list}}</ul>
<p>Please upload them through your secure portal by <strong>{{due_date}}</strong>.</p>
<p>{{cta_button}}</p>
<p>Questions? Reply to this email or call {{lo_phone}}.</p>
<p>Best regards,<br>{{lo_name}}</p>
</div>""",
        "body_text": "Hi {{first_name}}, We need documents for loan {{loan_number}}. Please upload by {{due_date}}.",
        "cta_text": "Upload Documents",
        "cta_url": "{{upload_url}}",
        "merge_fields": ["first_name", "loan_number", "document_list", "due_date", "lo_name", "lo_phone", "upload_url"],
        "category": "transactional",
    },
    {
        "template_type": "rate_alert",
        "name": "Rate Alert",
        "subject": "Rate Update: {{rate_direction}} to {{current_rate}}%",
        "body_html": """<div style="font-family: Arial, sans-serif; max-width: 600px;">
<p>Hi {{first_name}},</p>
<p>Mortgage rates have <strong>{{rate_direction}}</strong>. Here's your personalized update:</p>
<table style="border-collapse: collapse; width: 100%;">
<tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>30-Year Fixed</strong></td><td style="padding: 8px; border: 1px solid #ddd;">{{rate_30yr}}%</td></tr>
<tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>15-Year Fixed</strong></td><td style="padding: 8px; border: 1px solid #ddd;">{{rate_15yr}}%</td></tr>
<tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>Your Est. Payment</strong></td><td style="padding: 8px; border: 1px solid #ddd;">{{estimated_payment}}/mo</td></tr>
</table>
<p>{{cta_button}}</p>
<p>{{lo_name}} | {{lo_phone}}</p>
</div>""",
        "body_text": "Hi {{first_name}}, Rates have {{rate_direction}}. 30yr: {{rate_30yr}}%. Call {{lo_phone}} to discuss.",
        "cta_text": "Get Your Rate Quote",
        "cta_url": "{{rate_quote_url}}",
        "merge_fields": ["first_name", "rate_direction", "current_rate", "rate_30yr", "rate_15yr", "estimated_payment", "lo_name", "lo_phone", "rate_quote_url"],
        "category": "marketing",
    },
    {
        "template_type": "closing_update",
        "name": "Closing Update",
        "subject": "Your closing is scheduled — {{closing_date}}",
        "body_html": """<div style="font-family: Arial, sans-serif; max-width: 600px;">
<p>Hi {{first_name}},</p>
<p>Great news! Your closing has been scheduled:</p>
<p><strong>Date:</strong> {{closing_date}}<br>
<strong>Time:</strong> {{closing_time}}<br>
<strong>Location:</strong> {{closing_location}}</p>
<p>Please bring:</p>
<ul>
<li>Valid government-issued photo ID</li>
<li>Certified/cashier's check for {{cash_to_close}}</li>
</ul>
<p>Congratulations on reaching this milestone!</p>
<p>Best regards,<br>{{lo_name}}</p>
</div>""",
        "body_text": "Hi {{first_name}}, Your closing is scheduled for {{closing_date}} at {{closing_location}}.",
        "cta_text": "View Closing Details",
        "cta_url": "{{portal_url}}",
        "merge_fields": ["first_name", "closing_date", "closing_time", "closing_location", "cash_to_close", "lo_name", "portal_url"],
        "category": "transactional",
    },
    {
        "template_type": "follow_up",
        "name": "Follow-Up",
        "subject": "Following up on your mortgage inquiry",
        "body_html": """<div style="font-family: Arial, sans-serif; max-width: 600px;">
<p>Hi {{first_name}},</p>
<p>I wanted to follow up on our recent conversation about your {{loan_purpose}}.</p>
<p>Based on current market conditions, I think we can find some great options for you. Would you have 15 minutes this week for a quick call?</p>
<p>{{cta_button}}</p>
<p>Best regards,<br>{{lo_name}}<br>{{lo_title}}<br>NMLS# {{lo_nmls}}</p>
</div>""",
        "body_text": "Hi {{first_name}}, Following up on your {{loan_purpose}} inquiry. Available for a quick call this week?",
        "cta_text": "Schedule a Call",
        "cta_url": "{{schedule_url}}",
        "merge_fields": ["first_name", "loan_purpose", "lo_name", "lo_title", "lo_nmls", "schedule_url"],
        "category": "transactional",
    },
    {
        "template_type": "nurture",
        "name": "Market Nurture",
        "subject": "{{first_name}}, here's your monthly market update",
        "body_html": """<div style="font-family: Arial, sans-serif; max-width: 600px;">
<p>Hi {{first_name}},</p>
<p>Here's what's happening in the mortgage market this month:</p>
<p>{{market_summary}}</p>
<p>Whether you're ready now or just keeping an eye on the market, I'm here to help whenever the time is right.</p>
<p>{{cta_button}}</p>
<p>{{lo_name}} | {{company_name}}</p>
</div>""",
        "body_text": "Hi {{first_name}}, Monthly market update: {{market_summary}}. Contact {{lo_name}} when you're ready.",
        "cta_text": "Check Today's Rates",
        "cta_url": "{{rate_quote_url}}",
        "merge_fields": ["first_name", "market_summary", "lo_name", "company_name", "rate_quote_url"],
        "category": "marketing",
    },
]


# ============================================================================
# Route Registration
# ============================================================================

def register_email_template_routes(app, get_db, get_current_user, **kwargs):
    """Register per-tenant email template CRUD endpoints (WL-003)."""

    def _require_admin(current_user):
        role = getattr(current_user, 'permission_role', None) or getattr(current_user, 'role', None)
        if role not in ('admin', 'site_admin', 'leadership'):
            raise HTTPException(status_code=403, detail="Admin access required")

    # ==================================================================
    # List templates for organization
    # ==================================================================
    @app.get("/api/v1/admin/email-templates", tags=["Email Templates"])
    async def list_email_templates(
        category: Optional[str] = Query(None),
        template_type: Optional[str] = Query(None),
        is_active: Optional[bool] = Query(None),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """List all email templates for the current organization (WL-003)."""
        _require_admin(current_user)
        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        query = """
            SELECT id, template_type, name, subject, category, is_active,
                   merge_fields, created_at, updated_at
            FROM tenant_email_templates
            WHERE organization_id = :org_id
        """
        params = {"org_id": org_id}

        if category:
            query += " AND category = :category"
            params["category"] = category
        if template_type:
            query += " AND template_type = :template_type"
            params["template_type"] = template_type
        if is_active is not None:
            query += " AND is_active = :is_active"
            params["is_active"] = is_active

        query += " ORDER BY template_type, name"

        rows = await db.execute(text(query), params).fetchall()
        templates = []
        for r in rows:
            templates.append({
                "id": r[0], "template_type": r[1], "name": r[2],
                "subject": r[3], "category": r[4], "is_active": r[5],
                "merge_fields": r[6], "created_at": str(r[7]) if r[7] else None,
                "updated_at": str(r[8]) if r[8] else None,
            })

        return {"templates": templates, "count": len(templates)}

    # ==================================================================
    # Get single template
    # ==================================================================
    @app.get("/api/v1/admin/email-templates/{template_id}", tags=["Email Templates"])
    async def get_email_template(
        template_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Get a single email template with full body content (WL-003)."""
        _require_admin(current_user)
        org_id = getattr(current_user, 'organization_id', None)

        row = await db.execute(text("""
            SELECT id, organization_id, template_type, name, subject,
                   body_html, body_text, cta_text, cta_url,
                   merge_fields, category, is_active, created_at, updated_at
            FROM tenant_email_templates
            WHERE id = :id AND organization_id = :org_id
        """), {"id": template_id, "org_id": org_id}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Template not found")

        return {
            "id": row[0], "organization_id": row[1], "template_type": row[2],
            "name": row[3], "subject": row[4], "body_html": row[5],
            "body_text": row[6], "cta_text": row[7], "cta_url": row[8],
            "merge_fields": row[9], "category": row[10], "is_active": row[11],
            "created_at": str(row[12]) if row[12] else None,
            "updated_at": str(row[13]) if row[13] else None,
        }

    # ==================================================================
    # Create template
    # ==================================================================
    @app.post("/api/v1/admin/email-templates", tags=["Email Templates"], status_code=201)
    async def create_email_template(
        body: EmailTemplateCreate,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Create a new email template for the organization (WL-003)."""
        _require_admin(current_user)
        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        result = await db.execute(text("""
            INSERT INTO tenant_email_templates
                (organization_id, template_type, name, subject, body_html, body_text,
                 cta_text, cta_url, merge_fields, category, is_active,
                 created_by_id, created_at, updated_at)
            VALUES
                (:org_id, :template_type, :name, :subject, :body_html, :body_text,
                 :cta_text, :cta_url, :merge_fields, :category, :is_active,
                 :user_id, NOW(), NOW())
            RETURNING id
        """), {
            "org_id": org_id,
            "template_type": body.template_type,
            "name": body.name,
            "subject": body.subject,
            "body_html": body.body_html,
            "body_text": body.body_text,
            "cta_text": body.cta_text,
            "cta_url": body.cta_url,
            "merge_fields": json.dumps(body.merge_fields) if body.merge_fields else None,
            "category": body.category,
            "is_active": body.is_active,
            "user_id": current_user.id,
        })
        template_id = result.fetchone()[0]
        await db.commit()

        return {"id": template_id, "message": f"Template '{body.name}' created"}

    # ==================================================================
    # Update template
    # ==================================================================
    @app.put("/api/v1/admin/email-templates/{template_id}", tags=["Email Templates"])
    async def update_email_template(
        template_id: int,
        body: EmailTemplateUpdate,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Update an email template (WL-003)."""
        _require_admin(current_user)
        org_id = getattr(current_user, 'organization_id', None)

        # Verify ownership
        existing = await db.execute(text(
            "SELECT id FROM tenant_email_templates WHERE id = :id AND organization_id = :org_id"
        ), {"id": template_id, "org_id": org_id}).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Template not found")

        updates = []
        params = {"id": template_id, "org_id": org_id}
        for field in ["name", "subject", "body_html", "body_text", "cta_text", "cta_url", "is_active"]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{field} = :{field}")
                params[field] = val
        if body.merge_fields is not None:
            updates.append("merge_fields = :merge_fields")
            params["merge_fields"] = json.dumps(body.merge_fields)

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")
        update_sql = (
            "UPDATE tenant_email_templates SET " + ", ".join(updates)
            + " WHERE id = :id AND organization_id = :org_id"
        )
        await db.execute(text(update_sql), params)
        await db.commit()

        return {"id": template_id, "message": "Template updated"}

    # ==================================================================
    # Delete template
    # ==================================================================
    @app.delete("/api/v1/admin/email-templates/{template_id}", tags=["Email Templates"])
    async def delete_email_template(
        template_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Delete an email template (WL-003)."""
        _require_admin(current_user)
        org_id = getattr(current_user, 'organization_id', None)

        result = await db.execute(text(
            "DELETE FROM tenant_email_templates WHERE id = :id AND organization_id = :org_id"
        ), {"id": template_id, "org_id": org_id})
        await db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Template not found")

        return {"message": "Template deleted"}

    # ==================================================================
    # Preview template with merge data
    # ==================================================================
    @app.post("/api/v1/admin/email-templates/{template_id}/preview", tags=["Email Templates"])
    async def preview_email_template(
        template_id: int,
        body: TemplatePreviewRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Preview a template with merge field substitution (WL-003)."""
        _require_admin(current_user)
        org_id = getattr(current_user, 'organization_id', None)

        row = await db.execute(text("""
            SELECT subject, body_html, body_text, cta_text, cta_url
            FROM tenant_email_templates
            WHERE id = :id AND organization_id = :org_id
        """), {"id": template_id, "org_id": org_id}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Template not found")

        def merge(template_str, data):
            if not template_str:
                return template_str
            result = template_str
            for key, value in data.items():
                result = result.replace("{{" + key + "}}", str(value))
            # Build CTA button if cta_text present
            if "{{cta_button}}" in result and row[3]:
                cta_url = row[4] or "#"
                for key, value in data.items():
                    cta_url = cta_url.replace("{{" + key + "}}", str(value))
                button_html = f'<a href="{cta_url}" style="display:inline-block;padding:12px 24px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;">{row[3]}</a>'
                result = result.replace("{{cta_button}}", button_html)
            return result

        return {
            "subject": merge(row[0], body.merge_data),
            "body_html": merge(row[1], body.merge_data),
            "body_text": merge(row[2], body.merge_data),
        }

    # ==================================================================
    # Reset to system defaults
    # ==================================================================
    @app.post("/api/v1/admin/email-templates/reset-defaults", tags=["Email Templates"])
    async def reset_default_templates(
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Reset organization templates to system defaults (WL-003)."""
        _require_admin(current_user)
        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        created = 0
        for tmpl in SYSTEM_DEFAULT_TEMPLATES:
            # Only insert if template_type doesn't exist for this org
            existing = await db.execute(text("""
                SELECT id FROM tenant_email_templates
                WHERE organization_id = :org_id AND template_type = :tt
            """), {"org_id": org_id, "tt": tmpl["template_type"]}).fetchone()

            if not existing:
                await db.execute(text("""
                    INSERT INTO tenant_email_templates
                        (organization_id, template_type, name, subject, body_html, body_text,
                         cta_text, cta_url, merge_fields, category, is_active,
                         created_by_id, created_at, updated_at)
                    VALUES
                        (:org_id, :template_type, :name, :subject, :body_html, :body_text,
                         :cta_text, :cta_url, :merge_fields, :category, true,
                         :user_id, NOW(), NOW())
                """), {
                    "org_id": org_id,
                    "template_type": tmpl["template_type"],
                    "name": tmpl["name"],
                    "subject": tmpl["subject"],
                    "body_html": tmpl["body_html"],
                    "body_text": tmpl["body_text"],
                    "cta_text": tmpl.get("cta_text"),
                    "cta_url": tmpl.get("cta_url"),
                    "merge_fields": json.dumps(tmpl.get("merge_fields")),
                    "category": tmpl.get("category", "transactional"),
                    "user_id": current_user.id,
                })
                created += 1

        await db.commit()
        return {"message": f"Reset complete: {created} default templates created", "created": created}

    logger.info("  Email template routes registered (WL-003)")
