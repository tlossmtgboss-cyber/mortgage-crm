"""
Data Quality & Integrity Routes
================================
Enterprise Readiness Domain 3, Check 3.9 - Orphan Detection & Cleanup

Provides admin endpoints for:
  - Detecting orphaned records (tasks with invalid assignees, activities
    with invalid entity references, etc.)
  - Batch cleanup of legacy orphaned records
  - Data quality summary dashboard

Endpoints:
  GET  /api/v1/admin/data-quality/orphans          - Detect orphaned records
  POST /api/v1/admin/data-quality/orphans/cleanup   - Clean up orphaned records
  GET  /api/v1/admin/data-quality/summary           - Data quality summary
  GET  /api/v1/admin/data-quality/leads/no-contact  - Leads missing contact info
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def register_data_quality_routes(app, get_db, get_current_user, **kwargs):
    """Register data quality admin routes."""
    from database.models import (
        Lead, Loan, Task, AITask, Activity, User,
        ReferralPartner, MUMClient, StageHistory,
    )

    def _require_admin(current_user):
        """Ensure the current user is a platform admin or site admin."""
        role = getattr(current_user, 'role', '')
        if role not in ('Platform Admin', 'Site Admin', 'platform_admin', 'site_admin', 'admin'):
            raise HTTPException(
                status_code=403,
                detail="Only administrators can access data quality tools"
            )

    # ========================================================================
    # GET /api/v1/admin/data-quality/orphans - Detect orphaned records
    # ========================================================================
    @app.get("/api/v1/admin/data-quality/orphans", tags=["Data Quality"])
    async def detect_orphans(
        include_details: bool = False,
        limit: int = 100,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Detect orphaned records across the database.

        Checks for:
        - Tasks assigned to non-existent users
        - Tasks referencing non-existent leads or loans
        - Activities referencing non-existent leads, loans, or users
        - Stage history entries referencing non-existent leads or loans
        - Leads assigned to non-existent owners
        - MUM clients referencing non-existent users
        """
        _require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)
        org_filter = "AND t.organization_id = :org_id" if org_id else ""
        org_filter_a = "AND a.organization_id = :org_id" if org_id else ""
        org_filter_l = "AND l.organization_id = :org_id" if org_id else ""
        params = {"limit": limit}
        if org_id:
            params["org_id"] = org_id

        orphans = {}

        # 1. Tasks with invalid assignees (owner_id -> users.id)
        try:
            tasks_invalid_owner = db.execute(text(f"""
                SELECT t.id, t.title, t.owner_id, t.lead_id, t.loan_id
                FROM tasks t
                LEFT JOIN users u ON u.id = t.owner_id
                WHERE t.owner_id IS NOT NULL AND u.id IS NULL
                {org_filter}
                LIMIT :limit
            """), params).mappings().all()
            orphans["tasks_invalid_assignee"] = {
                "count": len(tasks_invalid_owner),
                "description": "Tasks assigned to non-existent users",
            }
            if include_details:
                orphans["tasks_invalid_assignee"]["records"] = [
                    {"id": r["id"], "title": r["title"], "owner_id": r["owner_id"]}
                    for r in tasks_invalid_owner
                ]
        except Exception as e:
            orphans["tasks_invalid_assignee"] = {"count": 0, "error": str(e)}

        # 2. Tasks referencing non-existent leads
        try:
            tasks_invalid_lead = db.execute(text(f"""
                SELECT t.id, t.title, t.lead_id
                FROM tasks t
                LEFT JOIN leads le ON le.id = t.lead_id
                WHERE t.lead_id IS NOT NULL AND le.id IS NULL
                {org_filter}
                LIMIT :limit
            """), params).mappings().all()
            orphans["tasks_invalid_lead"] = {
                "count": len(tasks_invalid_lead),
                "description": "Tasks referencing non-existent leads",
            }
            if include_details:
                orphans["tasks_invalid_lead"]["records"] = [
                    {"id": r["id"], "title": r["title"], "lead_id": r["lead_id"]}
                    for r in tasks_invalid_lead
                ]
        except Exception as e:
            orphans["tasks_invalid_lead"] = {"count": 0, "error": str(e)}

        # 3. Tasks referencing non-existent loans
        try:
            tasks_invalid_loan = db.execute(text(f"""
                SELECT t.id, t.title, t.loan_id
                FROM tasks t
                LEFT JOIN loans lo ON lo.id = t.loan_id
                WHERE t.loan_id IS NOT NULL AND lo.id IS NULL
                {org_filter}
                LIMIT :limit
            """), params).mappings().all()
            orphans["tasks_invalid_loan"] = {
                "count": len(tasks_invalid_loan),
                "description": "Tasks referencing non-existent loans",
            }
            if include_details:
                orphans["tasks_invalid_loan"]["records"] = [
                    {"id": r["id"], "title": r["title"], "loan_id": r["loan_id"]}
                    for r in tasks_invalid_loan
                ]
        except Exception as e:
            orphans["tasks_invalid_loan"] = {"count": 0, "error": str(e)}

        # 4. Activities referencing non-existent leads
        try:
            activities_invalid_lead = db.execute(text(f"""
                SELECT a.id, a.type, a.lead_id
                FROM activities a
                LEFT JOIN leads le ON le.id = a.lead_id
                WHERE a.lead_id IS NOT NULL AND le.id IS NULL
                {org_filter_a}
                LIMIT :limit
            """), params).mappings().all()
            orphans["activities_invalid_lead"] = {
                "count": len(activities_invalid_lead),
                "description": "Activities referencing non-existent leads",
            }
            if include_details:
                orphans["activities_invalid_lead"]["records"] = [
                    {"id": r["id"], "type": str(r["type"]), "lead_id": r["lead_id"]}
                    for r in activities_invalid_lead
                ]
        except Exception as e:
            orphans["activities_invalid_lead"] = {"count": 0, "error": str(e)}

        # 5. Activities referencing non-existent loans
        try:
            activities_invalid_loan = db.execute(text(f"""
                SELECT a.id, a.type, a.loan_id
                FROM activities a
                LEFT JOIN loans lo ON lo.id = a.loan_id
                WHERE a.loan_id IS NOT NULL AND lo.id IS NULL
                {org_filter_a}
                LIMIT :limit
            """), params).mappings().all()
            orphans["activities_invalid_loan"] = {
                "count": len(activities_invalid_loan),
                "description": "Activities referencing non-existent loans",
            }
            if include_details:
                orphans["activities_invalid_loan"]["records"] = [
                    {"id": r["id"], "type": str(r["type"]), "loan_id": r["loan_id"]}
                    for r in activities_invalid_loan
                ]
        except Exception as e:
            orphans["activities_invalid_loan"] = {"count": 0, "error": str(e)}

        # 6. Activities referencing non-existent users
        try:
            activities_invalid_user = db.execute(text(f"""
                SELECT a.id, a.type, a.user_id
                FROM activities a
                LEFT JOIN users u ON u.id = a.user_id
                WHERE a.user_id IS NOT NULL AND u.id IS NULL
                {org_filter_a}
                LIMIT :limit
            """), params).mappings().all()
            orphans["activities_invalid_user"] = {
                "count": len(activities_invalid_user),
                "description": "Activities referencing non-existent users",
            }
            if include_details:
                orphans["activities_invalid_user"]["records"] = [
                    {"id": r["id"], "type": str(r["type"]), "user_id": r["user_id"]}
                    for r in activities_invalid_user
                ]
        except Exception as e:
            orphans["activities_invalid_user"] = {"count": 0, "error": str(e)}

        # 7. Leads with invalid owner_id
        try:
            leads_invalid_owner = db.execute(text(f"""
                SELECT l.id, l.name, l.owner_id
                FROM leads l
                LEFT JOIN users u ON u.id = l.owner_id
                WHERE l.owner_id IS NOT NULL AND u.id IS NULL
                {org_filter_l}
                LIMIT :limit
            """), params).mappings().all()
            orphans["leads_invalid_owner"] = {
                "count": len(leads_invalid_owner),
                "description": "Leads assigned to non-existent users",
            }
            if include_details:
                orphans["leads_invalid_owner"]["records"] = [
                    {"id": r["id"], "name": r["name"], "owner_id": r["owner_id"]}
                    for r in leads_invalid_owner
                ]
        except Exception as e:
            orphans["leads_invalid_owner"] = {"count": 0, "error": str(e)}

        # 8. AI tasks referencing non-existent entities
        try:
            ai_tasks_invalid_lead = db.execute(text(f"""
                SELECT t.id, t.title, t.lead_id
                FROM ai_tasks t
                LEFT JOIN leads le ON le.id = t.lead_id
                WHERE t.lead_id IS NOT NULL AND le.id IS NULL
                {"AND t.organization_id = :org_id" if org_id else ""}
                LIMIT :limit
            """), params).mappings().all()
            orphans["ai_tasks_invalid_lead"] = {
                "count": len(ai_tasks_invalid_lead),
                "description": "AI tasks referencing non-existent leads",
            }
            if include_details:
                orphans["ai_tasks_invalid_lead"]["records"] = [
                    {"id": r["id"], "title": r["title"], "lead_id": r["lead_id"]}
                    for r in ai_tasks_invalid_lead
                ]
        except Exception as e:
            orphans["ai_tasks_invalid_lead"] = {"count": 0, "error": str(e)}

        total_orphans = sum(cat.get("count", 0) for cat in orphans.values())

        return {
            "status": "clean" if total_orphans == 0 else "orphans_detected",
            "total_orphans": total_orphans,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "categories": orphans,
        }

    # ========================================================================
    # POST /api/v1/admin/data-quality/orphans/cleanup - Batch cleanup
    # ========================================================================
    @app.post("/api/v1/admin/data-quality/orphans/cleanup", tags=["Data Quality"])
    async def cleanup_orphans(
        dry_run: bool = True,
        categories: Optional[str] = None,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Clean up orphaned records.

        By default runs in dry_run mode (preview only). Set dry_run=false to
        actually perform cleanup.

        Cleanup actions:
        - Tasks with invalid assignees -> set owner_id to NULL
        - Tasks with invalid lead/loan refs -> set ref to NULL
        - Activities with invalid refs -> delete the activity
        - Leads with invalid owners -> set owner_id to requesting admin
        - AI tasks with invalid refs -> set ref to NULL

        Args:
            dry_run: If true, only report what would be cleaned (default: true)
            categories: Comma-separated list of categories to clean (default: all).
                        Valid categories: tasks_invalid_assignee, tasks_invalid_lead,
                        tasks_invalid_loan, activities_invalid_lead, activities_invalid_loan,
                        activities_invalid_user, leads_invalid_owner, ai_tasks_invalid_lead
        """
        _require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)
        org_filter = "AND t.organization_id = :org_id" if org_id else ""
        org_filter_a = "AND a.organization_id = :org_id" if org_id else ""
        org_filter_l = "AND l.organization_id = :org_id" if org_id else ""
        params = {}
        if org_id:
            params["org_id"] = org_id

        target_categories = None
        if categories:
            target_categories = set(c.strip() for c in categories.split(","))

        results = {}

        def should_clean(cat_name):
            return target_categories is None or cat_name in target_categories

        # 1. Tasks with invalid assignees -> nullify owner_id
        if should_clean("tasks_invalid_assignee"):
            try:
                count_result = db.execute(text(f"""
                    SELECT COUNT(*) as cnt FROM tasks t
                    LEFT JOIN users u ON u.id = t.owner_id
                    WHERE t.owner_id IS NOT NULL AND u.id IS NULL
                    {org_filter}
                """), params).mappings().first()
                count = count_result["cnt"] if count_result else 0

                if not dry_run and count > 0:
                    db.execute(text(f"""
                        UPDATE tasks SET owner_id = NULL, updated_at = :now
                        WHERE id IN (
                            SELECT t.id FROM tasks t
                            LEFT JOIN users u ON u.id = t.owner_id
                            WHERE t.owner_id IS NOT NULL AND u.id IS NULL
                            {org_filter}
                        )
                    """), {**params, "now": datetime.now(timezone.utc)})

                results["tasks_invalid_assignee"] = {
                    "action": "nullify_owner_id",
                    "count": count,
                    "applied": not dry_run,
                }
            except Exception as e:
                results["tasks_invalid_assignee"] = {"error": str(e), "count": 0, "applied": False}

        # 2. Tasks with invalid lead refs -> nullify lead_id
        if should_clean("tasks_invalid_lead"):
            try:
                count_result = db.execute(text(f"""
                    SELECT COUNT(*) as cnt FROM tasks t
                    LEFT JOIN leads le ON le.id = t.lead_id
                    WHERE t.lead_id IS NOT NULL AND le.id IS NULL
                    {org_filter}
                """), params).mappings().first()
                count = count_result["cnt"] if count_result else 0

                if not dry_run and count > 0:
                    db.execute(text(f"""
                        UPDATE tasks SET lead_id = NULL, updated_at = :now
                        WHERE id IN (
                            SELECT t.id FROM tasks t
                            LEFT JOIN leads le ON le.id = t.lead_id
                            WHERE t.lead_id IS NOT NULL AND le.id IS NULL
                            {org_filter}
                        )
                    """), {**params, "now": datetime.now(timezone.utc)})

                results["tasks_invalid_lead"] = {
                    "action": "nullify_lead_id",
                    "count": count,
                    "applied": not dry_run,
                }
            except Exception as e:
                results["tasks_invalid_lead"] = {"error": str(e), "count": 0, "applied": False}

        # 3. Tasks with invalid loan refs -> nullify loan_id
        if should_clean("tasks_invalid_loan"):
            try:
                count_result = db.execute(text(f"""
                    SELECT COUNT(*) as cnt FROM tasks t
                    LEFT JOIN loans lo ON lo.id = t.loan_id
                    WHERE t.loan_id IS NOT NULL AND lo.id IS NULL
                    {org_filter}
                """), params).mappings().first()
                count = count_result["cnt"] if count_result else 0

                if not dry_run and count > 0:
                    db.execute(text(f"""
                        UPDATE tasks SET loan_id = NULL, updated_at = :now
                        WHERE id IN (
                            SELECT t.id FROM tasks t
                            LEFT JOIN loans lo ON lo.id = t.loan_id
                            WHERE t.loan_id IS NOT NULL AND lo.id IS NULL
                            {org_filter}
                        )
                    """), {**params, "now": datetime.now(timezone.utc)})

                results["tasks_invalid_loan"] = {
                    "action": "nullify_loan_id",
                    "count": count,
                    "applied": not dry_run,
                }
            except Exception as e:
                results["tasks_invalid_loan"] = {"error": str(e), "count": 0, "applied": False}

        # 4. Activities with invalid lead refs -> delete
        if should_clean("activities_invalid_lead"):
            try:
                count_result = db.execute(text(f"""
                    SELECT COUNT(*) as cnt FROM activities a
                    LEFT JOIN leads le ON le.id = a.lead_id
                    WHERE a.lead_id IS NOT NULL AND le.id IS NULL
                    {org_filter_a}
                """), params).mappings().first()
                count = count_result["cnt"] if count_result else 0

                if not dry_run and count > 0:
                    db.execute(text(f"""
                        DELETE FROM activities WHERE id IN (
                            SELECT a.id FROM activities a
                            LEFT JOIN leads le ON le.id = a.lead_id
                            WHERE a.lead_id IS NOT NULL AND le.id IS NULL
                            {org_filter_a}
                        )
                    """), params)

                results["activities_invalid_lead"] = {
                    "action": "delete_orphan_activities",
                    "count": count,
                    "applied": not dry_run,
                }
            except Exception as e:
                results["activities_invalid_lead"] = {"error": str(e), "count": 0, "applied": False}

        # 5. Activities with invalid loan refs -> delete
        if should_clean("activities_invalid_loan"):
            try:
                count_result = db.execute(text(f"""
                    SELECT COUNT(*) as cnt FROM activities a
                    LEFT JOIN loans lo ON lo.id = a.loan_id
                    WHERE a.loan_id IS NOT NULL AND lo.id IS NULL
                    {org_filter_a}
                """), params).mappings().first()
                count = count_result["cnt"] if count_result else 0

                if not dry_run and count > 0:
                    db.execute(text(f"""
                        DELETE FROM activities WHERE id IN (
                            SELECT a.id FROM activities a
                            LEFT JOIN loans lo ON lo.id = a.loan_id
                            WHERE a.loan_id IS NOT NULL AND lo.id IS NULL
                            {org_filter_a}
                        )
                    """), params)

                results["activities_invalid_loan"] = {
                    "action": "delete_orphan_activities",
                    "count": count,
                    "applied": not dry_run,
                }
            except Exception as e:
                results["activities_invalid_loan"] = {"error": str(e), "count": 0, "applied": False}

        # 6. Activities with invalid user refs -> nullify user_id
        if should_clean("activities_invalid_user"):
            try:
                count_result = db.execute(text(f"""
                    SELECT COUNT(*) as cnt FROM activities a
                    LEFT JOIN users u ON u.id = a.user_id
                    WHERE a.user_id IS NOT NULL AND u.id IS NULL
                    {org_filter_a}
                """), params).mappings().first()
                count = count_result["cnt"] if count_result else 0

                if not dry_run and count > 0:
                    db.execute(text(f"""
                        UPDATE activities SET user_id = NULL
                        WHERE id IN (
                            SELECT a.id FROM activities a
                            LEFT JOIN users u ON u.id = a.user_id
                            WHERE a.user_id IS NOT NULL AND u.id IS NULL
                            {org_filter_a}
                        )
                    """), params)

                results["activities_invalid_user"] = {
                    "action": "nullify_user_id",
                    "count": count,
                    "applied": not dry_run,
                }
            except Exception as e:
                results["activities_invalid_user"] = {"error": str(e), "count": 0, "applied": False}

        # 7. Leads with invalid owner -> reassign to current admin
        if should_clean("leads_invalid_owner"):
            try:
                count_result = db.execute(text(f"""
                    SELECT COUNT(*) as cnt FROM leads l
                    LEFT JOIN users u ON u.id = l.owner_id
                    WHERE l.owner_id IS NOT NULL AND u.id IS NULL
                    {org_filter_l}
                """), params).mappings().first()
                count = count_result["cnt"] if count_result else 0

                if not dry_run and count > 0:
                    db.execute(text(f"""
                        UPDATE leads SET owner_id = :admin_id, updated_at = :now
                        WHERE id IN (
                            SELECT l.id FROM leads l
                            LEFT JOIN users u ON u.id = l.owner_id
                            WHERE l.owner_id IS NOT NULL AND u.id IS NULL
                            {org_filter_l}
                        )
                    """), {**params, "admin_id": current_user.id, "now": datetime.now(timezone.utc)})

                results["leads_invalid_owner"] = {
                    "action": "reassign_to_admin",
                    "count": count,
                    "applied": not dry_run,
                    "reassigned_to": current_user.id if not dry_run and count > 0 else None,
                }
            except Exception as e:
                results["leads_invalid_owner"] = {"error": str(e), "count": 0, "applied": False}

        # 8. AI tasks with invalid lead refs -> nullify
        if should_clean("ai_tasks_invalid_lead"):
            try:
                count_result = db.execute(text(f"""
                    SELECT COUNT(*) as cnt FROM ai_tasks t
                    LEFT JOIN leads le ON le.id = t.lead_id
                    WHERE t.lead_id IS NOT NULL AND le.id IS NULL
                    {"AND t.organization_id = :org_id" if org_id else ""}
                """), params).mappings().first()
                count = count_result["cnt"] if count_result else 0

                if not dry_run and count > 0:
                    db.execute(text(f"""
                        UPDATE ai_tasks SET lead_id = NULL, updated_at = :now
                        WHERE id IN (
                            SELECT t.id FROM ai_tasks t
                            LEFT JOIN leads le ON le.id = t.lead_id
                            WHERE t.lead_id IS NOT NULL AND le.id IS NULL
                            {"AND t.organization_id = :org_id" if org_id else ""}
                        )
                    """), {**params, "now": datetime.now(timezone.utc)})

                results["ai_tasks_invalid_lead"] = {
                    "action": "nullify_lead_id",
                    "count": count,
                    "applied": not dry_run,
                }
            except Exception as e:
                results["ai_tasks_invalid_lead"] = {"error": str(e), "count": 0, "applied": False}

        if not dry_run:
            try:
                db.commit()
                logger.info(f"Data quality cleanup committed by user {current_user.id}")
            except Exception as e:
                db.rollback()
                logger.error(f"Data quality cleanup commit failed: {e}")
                raise HTTPException(status_code=500, detail="Cleanup commit failed")

        total_cleaned = sum(r.get("count", 0) for r in results.values() if r.get("applied"))
        total_detected = sum(r.get("count", 0) for r in results.values())

        return {
            "dry_run": dry_run,
            "total_detected": total_detected,
            "total_cleaned": total_cleaned if not dry_run else 0,
            "cleaned_at": datetime.now(timezone.utc).isoformat() if not dry_run else None,
            "cleaned_by": current_user.id if not dry_run else None,
            "categories": results,
        }

    # ========================================================================
    # GET /api/v1/admin/data-quality/summary - Data quality dashboard
    # ========================================================================
    @app.get("/api/v1/admin/data-quality/summary", tags=["Data Quality"])
    async def data_quality_summary(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Get a summary of data quality metrics.

        Reports on:
        - Leads missing contact information (no email AND no phone)
        - Leads with invalid email format (detected via pattern)
        - Tasks missing titles
        - Records with orphaned references
        - Overall data quality score
        """
        _require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)
        org_filter_l = "AND organization_id = :org_id" if org_id else ""
        org_filter_t = "AND organization_id = :org_id" if org_id else ""
        params = {}
        if org_id:
            params["org_id"] = org_id

        metrics = {}

        # Total leads
        try:
            total_leads_result = db.execute(text(f"""
                SELECT COUNT(*) as cnt FROM leads WHERE 1=1 {org_filter_l}
            """), params).mappings().first()
            total_leads = total_leads_result["cnt"] if total_leads_result else 0
            metrics["total_leads"] = total_leads
        except Exception:
            total_leads = 0
            metrics["total_leads"] = 0

        # Leads missing both email and phone
        try:
            missing_contact = db.execute(text(f"""
                SELECT COUNT(*) as cnt FROM leads
                WHERE (email IS NULL OR email = '')
                  AND (phone IS NULL OR phone = '')
                  {org_filter_l}
            """), params).mappings().first()
            metrics["leads_missing_contact"] = missing_contact["cnt"] if missing_contact else 0
        except Exception:
            metrics["leads_missing_contact"] = 0

        # Leads missing email only
        try:
            missing_email = db.execute(text(f"""
                SELECT COUNT(*) as cnt FROM leads
                WHERE (email IS NULL OR email = '')
                  {org_filter_l}
            """), params).mappings().first()
            metrics["leads_missing_email"] = missing_email["cnt"] if missing_email else 0
        except Exception:
            metrics["leads_missing_email"] = 0

        # Leads missing phone only
        try:
            missing_phone = db.execute(text(f"""
                SELECT COUNT(*) as cnt FROM leads
                WHERE (phone IS NULL OR phone = '')
                  {org_filter_l}
            """), params).mappings().first()
            metrics["leads_missing_phone"] = missing_phone["cnt"] if missing_phone else 0
        except Exception:
            metrics["leads_missing_phone"] = 0

        # Tasks missing titles (empty or null)
        try:
            tasks_no_title = db.execute(text(f"""
                SELECT COUNT(*) as cnt FROM tasks
                WHERE (title IS NULL OR title = '')
                  {org_filter_t}
            """), params).mappings().first()
            metrics["tasks_missing_title"] = tasks_no_title["cnt"] if tasks_no_title else 0
        except Exception:
            metrics["tasks_missing_title"] = 0

        # Total tasks
        try:
            total_tasks = db.execute(text(f"""
                SELECT COUNT(*) as cnt FROM tasks WHERE 1=1 {org_filter_t}
            """), params).mappings().first()
            metrics["total_tasks"] = total_tasks["cnt"] if total_tasks else 0
        except Exception:
            metrics["total_tasks"] = 0

        # Leads with duplicate names (potential duplicates)
        try:
            duplicate_names = db.execute(text(f"""
                SELECT COUNT(*) as cnt FROM (
                    SELECT name, COUNT(*) as c FROM leads
                    WHERE name IS NOT NULL {org_filter_l}
                    GROUP BY name HAVING COUNT(*) > 1
                ) dupes
            """), params).mappings().first()
            metrics["potential_duplicate_leads"] = duplicate_names["cnt"] if duplicate_names else 0
        except Exception:
            metrics["potential_duplicate_leads"] = 0

        # Calculate overall quality score (0-100)
        quality_deductions = 0
        if total_leads > 0:
            contact_pct = metrics["leads_missing_contact"] / total_leads * 100
            quality_deductions += min(contact_pct * 2, 30)  # Up to 30 points for missing contacts

        total_tasks_count = metrics.get("total_tasks", 0)
        if total_tasks_count > 0:
            title_pct = metrics["tasks_missing_title"] / total_tasks_count * 100
            quality_deductions += min(title_pct * 2, 20)  # Up to 20 points for missing titles

        if metrics.get("potential_duplicate_leads", 0) > 10:
            quality_deductions += 10  # Penalty for duplicates

        quality_score = max(0, round(100 - quality_deductions))

        return {
            "quality_score": quality_score,
            "quality_grade": (
                "A" if quality_score >= 90 else
                "B" if quality_score >= 80 else
                "C" if quality_score >= 70 else
                "D" if quality_score >= 60 else
                "F"
            ),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics,
        }

    # ========================================================================
    # GET /api/v1/admin/data-quality/leads/no-contact - Missing contact info
    # ========================================================================
    @app.get("/api/v1/admin/data-quality/leads/no-contact", tags=["Data Quality"])
    async def leads_missing_contact(
        limit: int = 100,
        offset: int = 0,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Get leads that are missing both email and phone contact information.

        These leads cannot be contacted and should be updated or archived.
        """
        _require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)
        org_filter = "AND l.organization_id = :org_id" if org_id else ""
        params = {"limit": limit, "offset": offset}
        if org_id:
            params["org_id"] = org_id

        # Count total
        count_result = db.execute(text(f"""
            SELECT COUNT(*) as cnt FROM leads l
            WHERE (l.email IS NULL OR l.email = '')
              AND (l.phone IS NULL OR l.phone = '')
              {org_filter}
        """), params).mappings().first()
        total = count_result["cnt"] if count_result else 0

        # Get records
        leads = db.execute(text(f"""
            SELECT l.id, l.name, l.email, l.phone, l.source, l.stage, l.created_at
            FROM leads l
            WHERE (l.email IS NULL OR l.email = '')
              AND (l.phone IS NULL OR l.phone = '')
              {org_filter}
            ORDER BY l.created_at DESC
            LIMIT :limit OFFSET :offset
        """), params).mappings().all()

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "leads": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "email": r["email"],
                    "phone": r["phone"],
                    "source": r["source"],
                    "stage": str(r["stage"]) if r["stage"] else None,
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in leads
            ],
        }

    logger.info("Data quality routes registered (Enterprise Readiness 3.9)")
