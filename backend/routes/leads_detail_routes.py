"""
Leads Detail/CRUD Routes

Extracted from inline_legacy_routes.py.
Provides bulk operations, individual CRUD by ID, documents, and orphan claiming.

Routes:
  DELETE/POST /api/v1/leads/bulk-delete
  POST /api/v1/leads/bulk-update-status
  GET /api/v1/leads/{lead_id}
  GET /api/v1/leads/{lead_id}/documents
  PATCH /api/v1/leads/{lead_id}
  DELETE /api/v1/leads/{lead_id}
  POST /api/v1/leads/claim-orphans
"""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
import asyncio
import logging

logger = logging.getLogger(__name__)

# Cache table names to avoid expensive metadata reflection per-request
_cached_table_names: set | None = None


def _get_table_names(db):
    global _cached_table_names
    if _cached_table_names is None:
        from sqlalchemy import inspect as sa_inspect
        _cached_table_names = set(sa_inspect(db.bind).get_table_names())
    return _cached_table_names


def register_leads_detail_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register leads detail/CRUD routes."""
    # Lazy imports to avoid circular dependencies
    from database.models import Lead, Loan, User, Document, StageHistory
    from schemas.core import LeadUpdate
    from routes.permission_core_routes import (
        filter_leads_by_permissions, has_permission,
        check_resource_access, require_permission_or_403,
    )
    from services.dre_helpers import calculate_lead_score

    def _org_scoped_lead(db, lead_id, current_user):
        """Query a lead with organization scoping to prevent cross-tenant access.
        Platform admins bypass org scoping (matches filter_leads_by_permissions logic).
        """
        query = db.query(Lead).filter(Lead.id == lead_id)
        is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
        if not is_platform_admin:
            org_id = getattr(current_user, 'organization_id', None)
            if org_id:
                query = query.filter(Lead.organization_id == org_id)
        return query.first()

    # IMPORTANT: This route MUST be defined BEFORE /leads/{lead_id} to avoid route conflicts
    @app.delete("/api/v1/leads/bulk-delete")
    @app.post("/api/v1/leads/bulk-delete")
    async def bulk_delete_leads_v2(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user_flexible)
    ):
        """
        Bulk delete multiple leads. Admin users, master user (id=1), or users with leads.delete_all permission can use this.
        """
        # Parse lead_ids from request body
        try:
            body = await request.json()
            # Handle both array format [1,2,3] and object format {"lead_ids": [1,2,3]}
            if isinstance(body, list):
                lead_ids = body
            elif isinstance(body, dict):
                lead_ids = body.get('lead_ids', body.get('ids', []))
            else:
                lead_ids = []
            lead_ids = [int(id) for id in lead_ids]  # Ensure integers
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid request body")

        # Permission check: require leads.delete or leads.update permission
        is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
        if not is_platform_admin:
            has_delete_permission = (
                has_permission(current_user.id, 'leads.delete', db)
                or has_permission(current_user.id, 'leads.delete_all', db)
                or has_permission(current_user.id, 'leads.update', db)
                or has_permission(current_user.id, 'leads.update_all', db)
            )
            if not has_delete_permission:
                raise HTTPException(status_code=403, detail="Permission denied: leads.delete")

        if not lead_ids:
            raise HTTPException(status_code=400, detail="No lead IDs provided")

        deleted_count = 0
        errors = []

        # Batch-fetch all leads at once to avoid N+1 queries (1 query instead of N)
        lead_query = db.query(Lead).filter(Lead.id.in_(lead_ids), Lead.deleted_at.is_(None))
        if not is_platform_admin:
            org_id = getattr(current_user, 'organization_id', None)
            if org_id:
                lead_query = lead_query.filter(Lead.organization_id == org_id)
        leads_map = {lead.id: lead for lead in lead_query.all()}

        for lead_id in lead_ids:
            # Use savepoint for each lead so failures don't cascade
            savepoint = db.begin_nested()
            try:
                lead = leads_map.get(lead_id)
                if not lead:
                    errors.append(f"Lead {lead_id} not found")
                    savepoint.rollback()
                    continue

                # Soft-delete: set deleted_at timestamp instead of removing data
                lead.deleted_at = datetime.now(timezone.utc)
                savepoint.commit()  # Commit the savepoint
                deleted_count += 1

            except Exception as e:
                savepoint.rollback()  # Rollback only this lead's savepoint
                logger.error(f"Failed to delete lead {lead_id}: {e}")
                errors.append(f"Failed to delete lead {lead_id}")

        # Final commit
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Final commit failed: {e}")

        return {
            "success": True,
            "deleted_count": deleted_count,
            "errors": errors,
            "message": f"Successfully deleted {deleted_count} leads" + (f" with {len(errors)} errors" if errors else "")
        }


    @app.post("/api/v1/leads/bulk-update-status")
    async def bulk_update_lead_status(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user_flexible)
    ):
        """
        Bulk update status/stage for multiple leads.
        Body: { "lead_ids": [1, 2, 3], "status": "Withdraw" }
        """
        logger.info(f"[bulk-update-status] Request received from user {current_user.id} ({current_user.email})")
        try:
            body = await request.json()
            logger.info(f"[bulk-update-status] Request body: {body}")
            lead_ids = body.get('lead_ids', body.get('ids', []))
            new_status = body.get('status', body.get('stage'))

            if isinstance(lead_ids, list) == False:
                lead_ids = [lead_ids]
            lead_ids = [int(id) for id in lead_ids]
            logger.info(f"[bulk-update-status] Parsed {len(lead_ids)} lead IDs, new_status={new_status}")
        except Exception as e:
            logger.error(f"[bulk-update-status] Failed to parse request: {e}")
            raise HTTPException(status_code=400, detail="Invalid request body")

        if not lead_ids:
            raise HTTPException(status_code=400, detail="No lead IDs provided")

        if not new_status:
            raise HTTPException(status_code=400, detail="No status provided")

        # Check update permission (platform admins bypass)
        is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
        if not is_platform_admin:
            has_update_permission = has_permission(current_user.id, 'leads.update', db) or has_permission(current_user.id, 'leads.update_all', db)
            if not has_update_permission:
                raise HTTPException(status_code=403, detail="Permission denied: leads.update")

        updated_count = 0
        updated_lead_ids = []  # Track actually-updated IDs (not just a slice of input)
        errors = []
        cascade_totals = {"loans_updated": 0, "mum_clients_updated": 0}

        # Batch-fetch all leads at once to avoid N+1 queries
        bulk_query = db.query(Lead).filter(Lead.id.in_(lead_ids))
        if not is_platform_admin:
            org_id = getattr(current_user, 'organization_id', None)
            if org_id:
                bulk_query = bulk_query.filter(Lead.organization_id == org_id)
        bulk_leads_map = {lead.id: lead for lead in bulk_query.all()}

        # Pre-fetch Encompass config once (same org for all leads in bulk update)
        _enc_cfg_cache = {}
        LOS_PUSH_STAGES = {"Application", "Converted", "Pre-Approved"}
        if new_status in LOS_PUSH_STAGES:
            try:
                from sqlalchemy import text as sa_text
                user_org_id = getattr(current_user, 'organization_id', None)
                if user_org_id:
                    enc_cfg = db.execute(sa_text("""
                        SELECT auto_push_on_stage_change, is_connected
                        FROM encompass_configs
                        WHERE organization_id = :org_id
                    """), {"org_id": user_org_id}).fetchone()
                    if enc_cfg:
                        _enc_cfg_cache[user_org_id] = enc_cfg
            except Exception:
                pass  # Encompass table may not exist

        for lead_id in lead_ids:
            try:
                lead = bulk_leads_map.get(lead_id)

                if not lead:
                    errors.append(f"Lead {lead_id} not found or access denied")
                    continue

                # Update the stage
                old_lead_status = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage) if lead.stage else None
                lead.stage = new_status
                now = datetime.now(timezone.utc)
                lead.updated_at = now
                lead.stage_changed_at = now
                lead.workflow_day = 0

                # Auto-stamp the SLA milestone date for the new stage
                LEAD_STAGE_TO_DATE_FIELD = {
                    "New": "lead_received_date",
                    "Attempted Contact": "first_contact_attempt_date",
                    "Prospect": "first_contact_successful_date",
                    "Pre-Qualified": "lead_qualification_date",
                    "Initial Consultation": "initial_consultation_date",
                    "Application": "application_started_date",
                    "APPLICATION_STARTED": "application_started_date",
                    "Application Complete": "application_completed_date",
                    "Document Fulfillment": "application_completed_date",
                    "Pre-Approved": "preapproval_issued_date",
                    "Under Contract": "preapproval_issued_date",
                    "Credit Repair": "credit_pulled_date",
                    "Disclosed": "application_completed_date",
                    "Closed": "application_completed_date",
                    "Funded": "application_completed_date",
                }
                date_field = LEAD_STAGE_TO_DATE_FIELD.get(new_status)
                if date_field and hasattr(lead, date_field) and not getattr(lead, date_field):
                    setattr(lead, date_field, now)
                    logger.info(f"Auto-stamped {date_field} for lead {lead.id} on bulk stage change to {new_status}")

                # Record stage change in history
                try:
                    stage_history = StageHistory(
                        entity_type='lead',
                        entity_id=lead.id,
                        lead_id=lead.id,
                        from_stage=old_lead_status,
                        to_stage=new_status,
                        changed_at=now,
                        changed_by_id=current_user.id,
                    )
                    db.add(stage_history)
                except Exception as hist_err:
                    logger.error(f"Failed to record stage history for lead {lead_id}: {hist_err}")

                updated_count += 1
                updated_lead_ids.append(lead_id)

                # Cascade to loans and MUM clients
                try:
                    from services.lead_cascade_service import cascade_lead_status
                    cr = cascade_lead_status(
                        db=db,
                        lead_id=lead.id,
                        new_lead_stage=new_status,
                        changed_by_id=current_user.id,
                        lead_loan_number=lead.loan_number,
                        organization_id=getattr(lead, 'organization_id', None),
                    )
                    cascade_totals["loans_updated"] += len(cr["loans_updated"])
                    cascade_totals["mum_clients_updated"] += len(cr["mum_clients_updated"])
                except Exception as cascade_err:
                    logger.error(f"Cascade error for lead {lead_id}: {cascade_err}")

                # LOS auto-push: when lead transitions to Application-stage,
                # push to Encompass if org has auto_push_on_stage_change enabled
                if new_status in LOS_PUSH_STAGES and lead.loan_number:
                    try:
                        from sqlalchemy import text as sa_text
                        lead_org_id = getattr(lead, 'organization_id', None)
                        enc_cfg = _enc_cfg_cache.get(lead_org_id)

                        if enc_cfg and enc_cfg.auto_push_on_stage_change and enc_cfg.is_connected:
                            loan_row = db.execute(sa_text(
                                "SELECT id FROM loans WHERE loan_number = :ln LIMIT 1"
                            ), {"ln": lead.loan_number}).fetchone()

                            if loan_row:
                                from services.los_integration.encompass_oauth_service import EncompassOAuthService
                                from services.los_integration.sync_service import LOSSyncService
                                oauth_svc = EncompassOAuthService()
                                client = await oauth_svc.get_authenticated_client(db=db, org_id=lead_org_id)
                                sync_svc = LOSSyncService(client=client)
                                sync_result = await sync_svc.push_to_los(db=db, loan_id=loan_row.id, organization_id=lead_org_id)
                                logger.info(f"LOS auto-push triggered for lead {lead_id} → loan {loan_row.id} (stage={new_status}, result={sync_result.status.value})")
                    except ImportError:
                        pass  # Encompass integration not installed
                    except Exception as los_err:
                        logger.warning(f"LOS auto-push failed for lead {lead_id}: {los_err}")

            except Exception as e:
                logger.error(f"Failed to update lead {lead_id}: {e}")
                errors.append(f"Failed to update lead {lead_id}")

        try:
            db.commit()
            logger.info(f"[bulk-update-status] Successfully committed. Updated {updated_count}, errors: {len(errors)}")

            # Event-driven workflow enrollment for all updated leads (post-commit)
            try:
                from services.workflow_scheduler import trigger_workflow_evaluation_for_lead
                for lead_id in updated_lead_ids:
                    try:
                        trigger_workflow_evaluation_for_lead(
                            db, lead_id, new_status,
                            user_id=current_user.id,
                        )
                    except Exception as wf_err:
                        logger.warning(f"Workflow trigger failed for lead {lead_id} in bulk update: {wf_err}")
            except Exception as wf_import_err:
                logger.warning(f"Workflow trigger import failed in bulk update: {wf_import_err}")
        except Exception as e:
            db.rollback()
            logger.error(f"[bulk-update-status] Failed to commit: {e}")
            raise HTTPException(status_code=500, detail="Failed to save changes")

        cascade_msg = ""
        if cascade_totals["loans_updated"] or cascade_totals["mum_clients_updated"]:
            cascade_msg = f" (cascaded to {cascade_totals['loans_updated']} loans, {cascade_totals['mum_clients_updated']} MUM clients)"

        result = {
            "success": True,
            "updated_count": updated_count,
            "new_status": new_status,
            "errors": errors,
            "message": f"Successfully updated {updated_count} leads to '{new_status}'" + (f" with {len(errors)} errors" if errors else "") + cascade_msg,
            "cascade_summary": cascade_totals,
        }
        logger.info(f"[bulk-update-status] Returning result: {result}")
        return result


    @app.get("/api/v1/leads/{lead_id}")
    async def get_lead(lead_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
        lead = _org_scoped_lead(db, lead_id, current_user)
        if not lead or lead.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Handle stage value - it might be an enum or a string depending on DB content
        stage_value = None
        if lead.stage:
            stage_value = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage)

        # Return dict to avoid Pydantic validation issues with enum
        return {
            "id": lead.id,
            "name": lead.name,
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "email": lead.email,
            "phone": lead.phone,
            "co_applicant_name": lead.co_applicant_name,
            "co_applicant_email": lead.co_applicant_email,
            "co_applicant_phone": lead.co_applicant_phone,
            "preferred_communication": lead.preferred_communication,
            "stage": stage_value,
            "source": lead.source,
            "production_assistant": getattr(lead, 'production_assistant', None),
            "ai_score": lead.ai_score,
            "sentiment": lead.sentiment,
            "next_action": lead.next_action,
            "preapproval_amount": lead.preapproval_amount,
            "credit_score": lead.credit_score,
            "loan_type": lead.loan_type,
            "notes": lead.notes,
            "owner_id": lead.owner_id,
            # Property Information
            "address": lead.address,
            "city": lead.city,
            "state": lead.state,
            "zip_code": lead.zip_code,
            "property_type": lead.property_type,
            "property_value": lead.property_value,
            "down_payment": lead.down_payment,
            # Financial Information
            "employment_status": lead.employment_status,
            "employer_name": getattr(lead, 'employer_name', None),
            "annual_income": lead.annual_income,
            "monthly_debts": lead.monthly_debts,
            "first_time_buyer": lead.first_time_buyer,
            # Metadata
            "user_metadata": getattr(lead, 'user_metadata', None),
            # Loan Details
            "loan_number": lead.loan_number,
            "loan_amount": lead.loan_amount,
            "interest_rate": lead.interest_rate,
            "loan_term": lead.loan_term,
            "apr": lead.apr,
            "points": lead.points,
            "lock_date": lead.lock_date.isoformat() if lead.lock_date else None,
            "lock_expiration": lead.lock_expiration.isoformat() if lead.lock_expiration else None,
            "closing_date": lead.closing_date.isoformat() if lead.closing_date else None,
            "lender": lead.lender,
            "loan_officer": lead.loan_officer,
            "processor": lead.processor,
            "underwriter": lead.underwriter,
            "appraisal_value": lead.appraisal_value,
            "ltv": lead.ltv,
            "dti": lead.dti,
            "cltv": lead.cltv,
            # Salesforce Sync Fields - Property Details
            "occupancy_type": lead.occupancy_type,
            "property_county": lead.property_county,
            "property_ownership_type": lead.property_ownership_type,
            "property_units": lead.property_units,
            # Salesforce Sync Fields - 1st Loan Financial Details
            "rate_type": lead.rate_type,
            "monthly_payment": lead.monthly_payment,
            "property_tax": lead.property_tax,
            "hazard_insurance": lead.hazard_insurance,
            "mortgage_insurance": lead.mortgage_insurance,
            "hoa_amount": lead.hoa_amount,
            "origination_fee": lead.origination_fee,
            "estimated_prepaid_interest": lead.estimated_prepaid_interest,
            "index_rate": lead.index_rate,
            "margin": lead.margin,
            # Salesforce Sync Fields - LTV/CLTV and Purpose
            "loan_purpose": lead.loan_purpose,
            "file_state": lead.file_state,
            # Salesforce Sync Fields - 2nd Loan Details
            "second_loan_amount": lead.second_loan_amount,
            "second_loan_rate": lead.second_loan_rate,
            "second_loan_payment": lead.second_loan_payment,
            # Salesforce Sync Fields - Present vs Proposed Housing
            "present_housing_expense": lead.present_housing_expense,
            "proposed_housing_expense": lead.proposed_housing_expense,
            "present_monthly_payment": lead.present_monthly_payment,
            "proposed_monthly_payment": lead.proposed_monthly_payment,
            # Salesforce Integration
            "salesforce_id": getattr(lead, 'salesforce_id', None),
            "salesforce_last_synced_at": (getattr(lead, 'salesforce_last_synced_at', None).isoformat() if getattr(lead, 'salesforce_last_synced_at', None) else
                                          (lead.meta_data or {}).get('salesforce_synced_at') if getattr(lead, 'meta_data', None) else None),
            # Timestamps
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
            "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
            "stage_changed_at": lead.stage_changed_at.isoformat() if lead.stage_changed_at else None,
            # SLA Milestone Dates
            "lead_received_date": lead.lead_received_date.isoformat() if lead.lead_received_date else None,
            "first_contact_attempt_date": lead.first_contact_attempt_date.isoformat() if lead.first_contact_attempt_date else None,
            "first_contact_successful_date": lead.first_contact_successful_date.isoformat() if lead.first_contact_successful_date else None,
            "application_started_date": lead.application_started_date.isoformat() if lead.application_started_date else None,
            "application_completed_date": lead.application_completed_date.isoformat() if lead.application_completed_date else None,
            "preapproval_issued_date": lead.preapproval_issued_date.isoformat() if lead.preapproval_issued_date else None,
        }


    @app.get("/api/v1/leads/{lead_id}/documents")
    async def get_lead_documents(lead_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
        """Get all documents associated with a lead"""
        lead = _org_scoped_lead(db, lead_id, current_user)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Fetch documents for this lead
        documents = db.query(Document).filter(Document.borrower_id == lead_id, Document.status == "active").all()

        # Organize documents by category
        categorized = {
            "income_verification": [],
            "credit_reports": [],
            "property_documents": [],
            "disclosures_forms": [],
            "bank_statements": [],
            "other": [],
        }

        category_mapping = {
            "Income": "income_verification",
            "Credit": "credit_reports",
            "Property": "property_documents",
            "Disclosures": "disclosures_forms",
            "Assets": "bank_statements",
            "Miscellaneous": "other",
        }

        for doc in documents:
            doc_data = {
                "id": doc.id,
                "filename": doc.filename,
                "original_filename": doc.original_filename,
                "doc_type": doc.doc_type.value if hasattr(doc.doc_type, 'value') else str(doc.doc_type),
                "doc_category": doc.doc_category.value if doc.doc_category and hasattr(doc.doc_category, 'value') else str(doc.doc_category) if doc.doc_category else None,
                "file_size": doc.file_size,
                "mime_type": doc.mime_type,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                "source": doc.source,
            }

            # Determine category
            cat_key = "other"
            if doc.doc_category:
                cat_value = doc.doc_category.value if hasattr(doc.doc_category, 'value') else str(doc.doc_category)
                cat_key = category_mapping.get(cat_value, "other")

            categorized[cat_key].append(doc_data)

        return {
            "lead_id": lead_id,
            "total_documents": len(documents),
            "documents": categorized,
        }


    @app.patch("/api/v1/leads/{lead_id}")
    async def update_lead(lead_id: int, lead_update: LeadUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
        is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
        if not is_platform_admin:
            has_update_permission = (
                has_permission(current_user.id, 'leads.update', db)
                or has_permission(current_user.id, 'leads.update_all', db)
            )
            if not has_update_permission:
                raise HTTPException(status_code=403, detail="Permission denied: leads.update")

        lead = _org_scoped_lead(db, lead_id, current_user)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Capture old status for workflow trigger
        old_status = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage) if lead.stage else None

        # Enterprise Readiness 3.1: Prevent clearing both contact methods
        update_data = lead_update.dict(exclude_unset=True)
        resulting_email = update_data.get('email', lead.email)
        resulting_phone = update_data.get('phone', lead.phone)
        # Treat empty string as None for contact method check
        if not resulting_email and not resulting_phone:
            raise HTTPException(
                status_code=422,
                detail="At least one contact method is required: cannot clear both email and phone"
            )

        _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id', 'owner_id'}
        for key, value in update_data.items():
            if key not in _protected:
                setattr(lead, key, value)

        # Recalculate AI score
        lead.ai_score = calculate_lead_score(lead)
        lead.updated_at = datetime.now(timezone.utc)

        # Detect stage change BEFORE commit so SLA dates are committed atomically
        new_status = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage) if lead.stage else None
        cascade_result = None
        duration_days = None
        stage_changed = old_status != new_status and new_status

        if stage_changed:
            # Validate transition against workflow engine's state machine
            from workflows.lead_workflow_engine import VALID_TRANSITIONS as _LEAD_VALID_TRANSITIONS
            allowed = _LEAD_VALID_TRANSITIONS.get(old_status, [])
            if allowed and new_status not in allowed:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid stage transition: '{old_status}' -> '{new_status}'. "
                           f"Allowed transitions: {allowed}",
                )

            now = datetime.now(timezone.utc)

            # Calculate duration in previous stage
            if lead.stage_changed_at:
                try:
                    duration_days = (now - lead.stage_changed_at.replace(tzinfo=timezone.utc)).days
                except Exception:
                    duration_days = None

            # Track when stage changed for workflow day calculations
            lead.stage_changed_at = now
            lead.workflow_day = 0  # Reset workflow day counter

            # Auto-stamp the SLA milestone date for the new stage
            LEAD_STAGE_TO_DATE_FIELD = {
                "New": "lead_received_date",
                "Attempted Contact": "first_contact_attempt_date",
                "Prospect": "first_contact_successful_date",
                "Pre-Qualified": "lead_qualification_date",
                "Initial Consultation": "initial_consultation_date",
                "Application": "application_started_date",
                "APPLICATION_STARTED": "application_started_date",
                "Application Complete": "application_completed_date",
                "Document Fulfillment": "application_completed_date",
                "Pre-Approved": "preapproval_issued_date",
                "Under Contract": "preapproval_issued_date",
                "Credit Repair": "credit_pulled_date",
                "Disclosed": "application_completed_date",
                "Closed": "application_completed_date",
                "Funded": "application_completed_date",
            }
            date_field = LEAD_STAGE_TO_DATE_FIELD.get(new_status)
            if date_field and hasattr(lead, date_field):
                # Only stamp if not already set (don't overwrite manual entries)
                if not getattr(lead, date_field):
                    setattr(lead, date_field, now)
                    logger.info(f"Auto-stamped {date_field} for lead {lead.id} on stage change to {new_status}")

            # Record stage change in history
            stage_history = StageHistory(
                entity_type='lead',
                entity_id=lead.id,
                lead_id=lead.id,
                from_stage=old_status,
                to_stage=new_status,
                changed_at=now,
                changed_by_id=current_user.id,
                duration_in_previous_stage=duration_days
            )
            db.add(stage_history)

        db.commit()
        db.refresh(lead)
        if stage_changed:
            logger.info(f"Stage changed for lead {lead.id}: {old_status} -> {new_status}, stage_changed_at + SLA dates committed")
        else:
            logger.info(f"Lead updated: {lead.name}")

        if stage_changed:
            # Cascade status to associated loans and MUM clients
            cascade_result = {"loans_updated": [], "mum_clients_updated": []}
            try:
                from services.lead_cascade_service import cascade_lead_status
                cascade_result = cascade_lead_status(
                    db=db,
                    lead_id=lead.id,
                    new_lead_stage=new_status,
                    changed_by_id=current_user.id,
                    lead_loan_number=lead.loan_number,
                    organization_id=getattr(lead, 'organization_id', None),
                )
                if cascade_result["loans_updated"] or cascade_result["mum_clients_updated"]:
                    db.commit()
                    logger.info(f"Cascade for lead {lead.id}: {len(cascade_result['loans_updated'])} loans, {len(cascade_result['mum_clients_updated'])} MUM clients updated")
            except Exception as cascade_err:
                logger.error(f"Cascade error for lead {lead.id}: {cascade_err}")

            try:
                from workflows.lead_workflow_engine import LeadStatusChange, LeadWorkflowEngine
                from workflows.workflow_actions import WorkflowActionExecutor

                # Create status change event
                status_change = LeadStatusChange(
                    lead_id=lead.id,
                    lead_name=lead.name,
                    lead_email=lead.email,
                    lead_phone=lead.phone,
                    old_status=old_status or "None",
                    new_status=new_status,
                    loan_officer_id=current_user.id,
                    loan_officer_name=current_user.full_name or current_user.email,
                    loan_officer_email=current_user.email,
                    loan_type=lead.loan_type if hasattr(lead, 'loan_type') else None,
                    loan_amount=lead.loan_amount if hasattr(lead, 'loan_amount') else None,
                    changed_at=datetime.now(timezone.utc)
                )

                # Process workflow
                workflow_engine = LeadWorkflowEngine(db)
                workflow_result = await workflow_engine.process_status_change(status_change)

                # Execute actions
                if workflow_result.get("actions"):
                    action_executor = WorkflowActionExecutor(db)
                    await action_executor.execute_actions(workflow_result["actions"])

                logger.info(f"Workflow triggered for {lead.name}: {old_status} -> {new_status} ({workflow_result.get('action_count', 0)} actions)")
            except Exception as e:
                logger.error(f"Workflow error for lead {lead.id}: {e}")
                # Don't fail the update if workflow fails

            # Track SLA milestone for stage change
            try:
                from services.sla_tracking_service import track_lead_stage_change
                track_lead_stage_change(db, lead.id, old_status, new_status, current_user.id)
                logger.info(f"SLA milestone tracked for lead {lead.id} stage change: {old_status} -> {new_status}")
            except Exception as e:
                logger.warning(f"Failed to track SLA milestone for lead {lead.id}: {e}")

            # Event-driven workflow enrollment (eliminates 60s polling delay)
            try:
                from services.workflow_scheduler import trigger_workflow_evaluation_for_lead
                trigger_workflow_evaluation_for_lead(
                    db, lead.id, new_status,
                    lead_source=getattr(lead, 'source', None),
                    user_id=current_user.id,
                )
            except Exception as e:
                logger.warning(f"Workflow evaluation trigger failed for lead {lead.id}: {e}")

            # Fire lead status change triggers for automated outreach (nurture, etc.)
            try:
                from routes.automated_outreach_routes import execute_trigger, TriggerType
                asyncio.create_task(execute_trigger(
                    trigger_type=TriggerType.LEAD_STATUS_CHANGE,
                    lead_id=lead.id,
                    context={"old_status": old_status, "new_status": new_status},
                    db=db
                ))
                logger.info(f"Lead status change trigger fired for lead {lead.id}: {old_status} -> {new_status}")
            except Exception as trigger_error:
                logger.error(f"Error firing lead status trigger: {trigger_error}")

        # Handle stage value - it might be an enum or a string depending on DB content
        stage_value = None
        if lead.stage:
            stage_value = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage)

        # Return dict to avoid Pydantic validation issues with enum
        result = {
            "id": lead.id,
            "name": lead.name,
            "email": lead.email,
            "phone": lead.phone,
            "stage": stage_value,
            "source": lead.source,
            "production_assistant": getattr(lead, 'production_assistant', None),
            "ai_score": lead.ai_score,
            "sentiment": lead.sentiment,
            "next_action": lead.next_action,
            "preapproval_amount": lead.preapproval_amount,
            "credit_score": lead.credit_score,
            "loan_type": lead.loan_type,
            "notes": lead.notes,
            "owner_id": lead.owner_id,
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
            "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
            # SLA milestone dates
            "lead_received_date": lead.lead_received_date.isoformat() if lead.lead_received_date else None,
            "first_contact_attempt_date": lead.first_contact_attempt_date.isoformat() if lead.first_contact_attempt_date else None,
            "first_contact_successful_date": lead.first_contact_successful_date.isoformat() if lead.first_contact_successful_date else None,
            "lead_qualification_date": lead.lead_qualification_date.isoformat() if lead.lead_qualification_date else None,
            "initial_consultation_date": lead.initial_consultation_date.isoformat() if lead.initial_consultation_date else None,
            "application_started_date": lead.application_started_date.isoformat() if lead.application_started_date else None,
            "application_completed_date": lead.application_completed_date.isoformat() if lead.application_completed_date else None,
            "credit_pulled_date": lead.credit_pulled_date.isoformat() if lead.credit_pulled_date else None,
            "preapproval_issued_date": lead.preapproval_issued_date.isoformat() if lead.preapproval_issued_date else None,
            "stage_changed_at": lead.stage_changed_at.isoformat() if lead.stage_changed_at else None,
        }

        # Include cascade info if a status change triggered it
        if old_status != new_status and cascade_result and (cascade_result["loans_updated"] or cascade_result["mum_clients_updated"]):
            result["cascade"] = {
                "loans_updated": len(cascade_result["loans_updated"]),
                "mum_clients_updated": len(cascade_result["mum_clients_updated"]),
                "loan_details": cascade_result["loans_updated"],
            }

        return result

    @app.delete("/api/v1/leads/{lead_id}", status_code=204)
    async def delete_lead(lead_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
        is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
        if not is_platform_admin:
            has_delete_permission = (
                has_permission(current_user.id, 'leads.delete', db)
                or has_permission(current_user.id, 'leads.delete_all', db)
            )
            if not has_delete_permission:
                raise HTTPException(status_code=403, detail="Permission denied: leads.delete")

        lead = _org_scoped_lead(db, lead_id, current_user)
        if not lead or lead.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Lead not found")

        lead_name = lead.name

        try:
            # Soft-delete: set deleted_at timestamp instead of removing data
            lead.deleted_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(f"Lead soft-deleted: {lead_name} (ID: {lead_id})")
            return None

        except Exception as e:
            logger.error(f"Error soft-deleting lead {lead_id}: {str(e)}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Failed to delete lead")


    @app.post("/api/v1/leads/claim-orphans")
    async def claim_orphan_leads(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Claim all orphan leads (leads with no owner) and assign them to the current user.
        This fixes the AI chat issue where leads aren't visible because they have no owner.
        Also claims loans that don't belong to any valid user.

        Uses SELECT ... FOR UPDATE SKIP LOCKED to prevent concurrent requests from
        double-claiming the same leads/loans.
        """
        try:
            # Lock and claim orphan leads atomically using FOR UPDATE SKIP LOCKED
            # This prevents concurrent requests from claiming the same leads
            result = db.execute(
                text("""
                    UPDATE leads SET owner_id = :user_id
                    WHERE id IN (
                        SELECT id FROM leads
                        WHERE owner_id IS NULL
                        FOR UPDATE SKIP LOCKED
                    )
                """),
                {"user_id": current_user.id}
            )
            leads_claimed = result.rowcount

            # Lock and claim orphan loans atomically using FOR UPDATE SKIP LOCKED
            result = db.execute(
                text("""
                    UPDATE loans SET loan_officer_id = :user_id
                    WHERE id IN (
                        SELECT id FROM loans
                        WHERE loan_officer_id IS NULL
                           OR loan_officer_id NOT IN (SELECT id FROM users)
                        FOR UPDATE SKIP LOCKED
                    )
                """),
                {"user_id": current_user.id}
            )
            loans_claimed = result.rowcount

            db.commit()

            # Get totals
            result = db.execute(
                text("""
                    SELECT
                        (SELECT COUNT(*) FROM leads WHERE owner_id = :user_id) as leads,
                        (SELECT COUNT(*) FROM loans WHERE loan_officer_id = :user_id) as loans
                """),
                {"user_id": current_user.id}
            )
            totals = result.fetchone()

            logger.info(f"User {current_user.id} claimed {leads_claimed} leads, {loans_claimed} loans")

            return {
                "success": True,
                "message": f"Successfully claimed {leads_claimed} leads and {loans_claimed} loans",
                "claimed": {
                    "leads": leads_claimed,
                    "loans": loans_claimed
                },
                "totals": {
                    "leads": totals[0],
                    "loans": totals[1]
                }
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error claiming orphan leads: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to claim orphan leads")

    logger.info("Leads detail/CRUD routes loaded")
