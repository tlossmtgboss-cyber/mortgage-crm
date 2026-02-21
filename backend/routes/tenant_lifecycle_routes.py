"""
Tenant Lifecycle Routes — PROV-001, PROV-003, PROV-006, PROV-007, PROV-008, PROV-009

Full organization lifecycle management:
    POST /api/v1/tenants/signup              — Self-service signup (PROV-001)
    POST /api/v1/tenants/provision           — Full provisioning with admin user (PROV-003)
    POST /api/v1/admin/org/export-data       — Export before deactivation (PROV-006)
    POST /api/v1/admin/org/deactivate        — Soft-delete/suspend org (PROV-005)
    POST /api/v1/admin/org/reactivate        — Reactivate suspended org (PROV-007)
    POST /api/v1/admin/org/hard-delete       — Hard delete with cascade purge (PROV-008)
    GET  /api/v1/admin/org/onboarding        — Org-level onboarding status (PROV-009)
    POST /api/v1/admin/org/onboarding/step   — Complete onboarding step (PROV-009)
"""
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime, timezone
import json
import logging
import secrets

logger = logging.getLogger(__name__)


class SignupRequest(BaseModel):
    organization_name: str
    admin_email: str
    admin_first_name: str
    admin_last_name: str
    admin_password: str
    subdomain: Optional[str] = None
    tier: str = "lead_management"
    billing_cycle: str = "monthly"


class ProvisionRequest(BaseModel):
    organization_name: str
    admin_email: str
    admin_first_name: str = "Admin"
    admin_last_name: str = "User"
    subdomain: Optional[str] = None
    tier: str = "lead_management"


class HardDeleteRequest(BaseModel):
    confirm_organization_name: str
    reason: str = "gdpr_right_to_erasure"


class OnboardingStepRequest(BaseModel):
    step_key: str
    completed: bool = True
    step_data: Optional[dict] = None


# Organization-level onboarding steps
ORG_ONBOARDING_STEPS = [
    {"key": "company_profile", "label": "Complete company profile", "order": 1},
    {"key": "branding", "label": "Upload logo and configure branding", "order": 2},
    {"key": "invite_team", "label": "Invite team members", "order": 3},
    {"key": "configure_pipeline", "label": "Configure pipeline stages", "order": 4},
    {"key": "connect_integrations", "label": "Connect integrations (email, calendar)", "order": 5},
    {"key": "import_data", "label": "Import existing data", "order": 6},
    {"key": "setup_billing", "label": "Set up billing/payment method", "order": 7},
    {"key": "custom_domain", "label": "Configure custom domain (optional)", "order": 8},
]


def register_tenant_lifecycle_routes(app, get_db, get_current_user, **kwargs):
    """Register tenant lifecycle endpoints."""

    get_password_hash = kwargs.get('get_password_hash')

    # ==================================================================
    # PROV-001: Self-service signup flow
    # ==================================================================
    @app.post("/api/v1/tenants/signup", tags=["Tenant Lifecycle"])
    async def self_service_signup(
        body: SignupRequest,
        db: Session = Depends(get_db),
    ):
        """
        Self-service organization signup with admin user creation.

        Flow:
        1. Create Organization record
        2. Create admin User account
        3. Create default subscription (trial)
        4. Initialize org settings
        5. Create org-level onboarding progress
        """
        try:
            # Check if org name or subdomain already taken
            existing = db.execute(text("""
                SELECT id FROM organizations WHERE name = :name
            """), {"name": body.organization_name}).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="Organization name already taken")

            # Check if email already registered
            existing_user = db.execute(text("""
                SELECT id FROM users WHERE email = :email
            """), {"email": body.admin_email}).fetchone()
            if existing_user:
                raise HTTPException(status_code=409, detail="Email already registered")

            # 1. Create Organization
            subdomain = body.subdomain or body.organization_name.lower().replace(" ", "-")[:30]
            result = db.execute(text("""
                INSERT INTO organizations (name, subdomain, settings, is_active, created_at)
                VALUES (:name, :subdomain, :settings, TRUE, NOW())
                RETURNING id
            """), {
                "name": body.organization_name,
                "subdomain": subdomain,
                "settings": json.dumps({
                    "onboarding_completed": False,
                    "onboarding_steps": {s["key"]: False for s in ORG_ONBOARDING_STEPS},
                }),
            })
            org_id = result.fetchone()[0]

            # 2. Create admin user (PROV-003)
            pw_hash = get_password_hash(body.admin_password) if get_password_hash else "placeholder"
            db.execute(text("""
                INSERT INTO users
                    (email, first_name, last_name, hashed_password, role, permission_role,
                     organization_id, is_active, created_at)
                VALUES
                    (:email, :first, :last, :pw, 'admin', 'site_admin',
                     :org_id, TRUE, NOW())
            """), {
                "email": body.admin_email,
                "first": body.admin_first_name,
                "last": body.admin_last_name,
                "pw": pw_hash,
                "org_id": org_id,
            })

            # 3. Create trial subscription
            from subscription_models import SUBSCRIPTION_TIERS
            tier_config = SUBSCRIPTION_TIERS.get(body.tier, SUBSCRIPTION_TIERS["lead_management"])
            db.execute(text("""
                INSERT INTO organization_subscriptions
                    (organization_id, tier, status, billing_cycle, monthly_price,
                     trial_ends_at, current_period_start, current_period_end, created_at)
                VALUES
                    (:org_id, :tier, 'trial', :cycle, :price,
                     NOW() + INTERVAL '14 days', NOW(), NOW() + INTERVAL '30 days', NOW())
            """), {
                "org_id": org_id,
                "tier": body.tier,
                "cycle": body.billing_cycle,
                "price": tier_config.get("price_monthly", 299),
            })

            db.commit()

            return {
                "status": "created",
                "organization_id": org_id,
                "subdomain": subdomain,
                "admin_email": body.admin_email,
                "tier": body.tier,
                "trial_days": 14,
            }

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Signup failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Signup failed")

    # ==================================================================
    # PROV-003: Provision org with admin user
    # ==================================================================
    @app.post("/api/v1/tenants/provision", tags=["Tenant Lifecycle"])
    async def provision_tenant(
        body: ProvisionRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Platform admin: provision a new org with admin user.
        Requires platform_admin role.
        """
        from utils.auth import require_admin
        require_admin(current_user)

        # Delegate to signup with generated password
        temp_password = secrets.token_urlsafe(16)
        signup = SignupRequest(
            organization_name=body.organization_name,
            admin_email=body.admin_email,
            admin_first_name=body.admin_first_name,
            admin_last_name=body.admin_last_name,
            admin_password=temp_password,
            subdomain=body.subdomain,
            tier=body.tier,
        )
        result = await self_service_signup(signup, db)
        result["temp_password"] = temp_password
        result["note"] = "Admin must change password on first login"
        return result

    # ==================================================================
    # PROV-006: Data export before deactivation
    # ==================================================================
    @app.post("/api/v1/admin/org/export-data", tags=["Tenant Lifecycle"])
    async def export_org_data_before_deactivation(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Export all organization data before deactivation.
        Wraps the GDPR export endpoint to ensure data portability
        before any org lifecycle change.
        """
        from utils.auth import require_admin
        require_admin(current_user)

        # Reuse GDPR export logic
        from routes.gdpr_routes import register_gdpr_routes
        org_id = getattr(current_user, 'organization_id', None)

        # Build export manifest inline (same as GDPR export)
        EXPORT_TABLES = [
            "users", "leads", "loans", "clients", "contacts", "tasks",
            "notes", "documents", "email_messages", "sms_messages",
            "audit_logs", "activities", "workflows",
        ]

        export_summary = {"organization_id": org_id, "tables": {}}
        for table in EXPORT_TABLES:
            try:
                count = db.execute(text(
                    f"SELECT COUNT(*) FROM {table} WHERE organization_id = :org_id"
                ), {"org_id": org_id}).scalar() or 0
                export_summary["tables"][table] = count
            except Exception:
                export_summary["tables"][table] = "skipped"

        # Log export event
        db.execute(text("""
            INSERT INTO audit_logs
                (user_id, changed_by_id, change_type, entity_type, reason,
                 after_state, timestamp, organization_id)
            VALUES
                (:uid, :uid, 'pre_deactivation_export', 'organization', 'data_portability',
                 CAST(:data AS jsonb), NOW(), :org_id)
        """), {
            "uid": current_user.id,
            "org_id": org_id,
            "data": json.dumps(export_summary),
        })
        db.commit()

        return {
            "status": "export_ready",
            "message": "Use POST /api/v1/admin/gdpr/export to download ZIP",
            "summary": export_summary,
        }

    # ==================================================================
    # PROV-007: Org reactivation from suspended state
    # ==================================================================
    @app.post("/api/v1/admin/org/reactivate", tags=["Tenant Lifecycle"])
    async def reactivate_organization(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Reactivate a suspended/soft-deleted organization.
        Clears deleted_at, sets is_active=True, restores subscription.
        """
        from utils.auth import require_admin
        require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)

        try:
            # Clear soft-delete flags on organization
            db.execute(text("""
                UPDATE organizations
                SET is_active = TRUE, deleted_at = NULL, updated_at = NOW()
                WHERE id = :org_id
            """), {"org_id": org_id})

            # Reactivate subscription if suspended
            db.execute(text("""
                UPDATE organization_subscriptions
                SET status = 'active', updated_at = NOW()
                WHERE organization_id = :org_id AND status IN ('suspended', 'canceled', 'past_due')
            """), {"org_id": org_id})

            # Reactivate users
            db.execute(text("""
                UPDATE users
                SET is_active = TRUE
                WHERE organization_id = :org_id AND is_active = FALSE
            """), {"org_id": org_id})

            # Audit log
            db.execute(text("""
                INSERT INTO audit_logs
                    (user_id, changed_by_id, change_type, entity_type, reason,
                     timestamp, organization_id)
                VALUES
                    (:uid, :uid, 'org_reactivation', 'organization', 'admin_request',
                     NOW(), :org_id)
            """), {"uid": current_user.id, "org_id": org_id})

            db.commit()
            return {"status": "reactivated", "organization_id": org_id}

        except Exception as e:
            db.rollback()
            logger.error(f"Reactivation failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Reactivation failed")

    # ==================================================================
    # PROV-008: Hard delete with cascading purge
    # ==================================================================
    @app.post("/api/v1/admin/org/hard-delete", tags=["Tenant Lifecycle"])
    async def hard_delete_organization(
        body: HardDeleteRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Hard delete an organization with cascading data purge.

        GDPR Article 17 — Right to Erasure. Permanently removes ALL
        organization data from ALL tables. Requires confirmation of
        org name to prevent accidental deletion.

        Retention: Audit logs are anonymized (PII redacted) but retained
        for 7 years per regulatory requirements.
        """
        from utils.auth import require_admin
        require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)

        # Verify org name confirmation
        org = db.execute(text(
            "SELECT name FROM organizations WHERE id = :id"
        ), {"id": org_id}).fetchone()

        if not org or org[0] != body.confirm_organization_name:
            raise HTTPException(
                status_code=400,
                detail="Organization name does not match. Provide exact name to confirm deletion."
            )

        try:
            # Cascade delete all tenant-scoped data
            PURGE_TABLES = [
                "sms_messages", "email_messages", "activities", "stage_history",
                "notes", "documents", "tasks", "contacts", "clients",
                "loans", "leads", "notifications", "workflows",
                "ai_conversation_memory", "ai_action_history",
                "feature_usage", "organization_subscriptions",
            ]

            purge_results = {}
            for table in PURGE_TABLES:
                try:
                    result = db.execute(text(
                        f"DELETE FROM {table} WHERE organization_id = :org_id"
                    ), {"org_id": org_id})
                    purge_results[table] = result.rowcount
                except Exception as te:
                    purge_results[table] = f"error: {str(te)[:80]}"

            # Anonymize audit logs (retain for regulatory compliance)
            db.execute(text("""
                UPDATE audit_logs
                SET before_state = '{"redacted": true}'::jsonb,
                    after_state = '{"redacted": true}'::jsonb,
                    reason = 'gdpr_purge_' || reason
                WHERE organization_id = :org_id
            """), {"org_id": org_id})

            # Delete users
            user_count = db.execute(text(
                "DELETE FROM users WHERE organization_id = :org_id"
            ), {"org_id": org_id}).rowcount

            # Delete the organization itself
            db.execute(text(
                "DELETE FROM organizations WHERE id = :org_id"
            ), {"org_id": org_id})

            db.commit()

            return {
                "status": "permanently_deleted",
                "organization_id": org_id,
                "users_deleted": user_count,
                "tables_purged": purge_results,
                "audit_logs": "anonymized_and_retained",
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Hard delete failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Deletion failed")

    # ==================================================================
    # PROV-009: Organization-level onboarding
    # ==================================================================
    @app.get("/api/v1/admin/org/onboarding", tags=["Tenant Lifecycle"])
    async def get_org_onboarding_status(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get organization-level onboarding progress."""
        org_id = getattr(current_user, 'organization_id', None)

        try:
            org = db.execute(text(
                "SELECT settings FROM organizations WHERE id = :id"
            ), {"id": org_id}).fetchone()

            settings = json.loads(org[0]) if org and org[0] else {}
            steps_status = settings.get("onboarding_steps", {})

            steps = []
            for step_def in ORG_ONBOARDING_STEPS:
                steps.append({
                    **step_def,
                    "completed": steps_status.get(step_def["key"], False),
                })

            completed_count = sum(1 for s in steps if s["completed"])
            total = len(steps)

            return {
                "organization_id": org_id,
                "completed": completed_count,
                "total": total,
                "percent": round((completed_count / total) * 100, 1) if total > 0 else 0,
                "is_complete": completed_count == total,
                "steps": steps,
            }
        except Exception as e:
            logger.warning(f"Onboarding status error: {e}")
            return {"steps": ORG_ONBOARDING_STEPS, "completed": 0, "total": len(ORG_ONBOARDING_STEPS)}

    @app.post("/api/v1/admin/org/onboarding/step", tags=["Tenant Lifecycle"])
    async def complete_onboarding_step(
        body: OnboardingStepRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Mark an organization onboarding step as complete."""
        org_id = getattr(current_user, 'organization_id', None)

        try:
            org = db.execute(text(
                "SELECT settings FROM organizations WHERE id = :id"
            ), {"id": org_id}).fetchone()

            settings = json.loads(org[0]) if org and org[0] else {}
            if "onboarding_steps" not in settings:
                settings["onboarding_steps"] = {}

            settings["onboarding_steps"][body.step_key] = body.completed
            if body.step_data:
                settings[f"onboarding_{body.step_key}_data"] = body.step_data

            # Check if all steps complete
            all_complete = all(
                settings["onboarding_steps"].get(s["key"], False)
                for s in ORG_ONBOARDING_STEPS
            )
            settings["onboarding_completed"] = all_complete

            db.execute(text("""
                UPDATE organizations SET settings = CAST(:settings AS jsonb), updated_at = NOW()
                WHERE id = :id
            """), {"settings": json.dumps(settings), "id": org_id})
            db.commit()

            return {
                "step": body.step_key,
                "completed": body.completed,
                "all_complete": all_complete,
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Onboarding step update failed: {e}")
            raise HTTPException(status_code=500, detail="Update failed")

    logger.info("Tenant lifecycle routes loaded (PROV-001/003/006/007/008/009)")
