"""
External Migrations - Calls to external migration scripts in backend/migrations/.

These are standalone migration scripts that are invoked during init_db()
to ensure database schema is up to date.
"""
import logging

logger = logging.getLogger(__name__)


def run_external_migrations(engine):
    """Run all external migration scripts."""
    _run_comprehensive_column_migration()
    _deploy_soc2_tables(engine)
    _run_eeoc_nmls_migration()
    _run_recruiting_org_id_v2()
    _run_disposition_tracking()
    _run_ai_audit_log()
    _run_assessment_tables()
    _run_social_recruiting(engine)
    _run_social_oauth(engine)
    _run_recruit_workflow_config()
    _run_social_tokens_org_id(engine)
    _run_ops_sweep_results(engine)
    _run_tasktype_enum_sync(engine)
    _run_campaign_template_seed(engine)


def _run_comprehensive_column_migration():
    """Run comprehensive column migration for all missing columns."""
    try:
        from migrations.add_all_missing_columns import run_migration
        run_migration()
        logger.info("Comprehensive column migration completed")
    except Exception as e:
        logger.warning(f"Comprehensive migration note: {e}")


def _deploy_soc2_tables(engine):
    """Deploy SOC 2 compliance tables (idempotent)."""
    try:
        from migrations.deploy_soc2_tables import deploy_soc2_tables
        created = deploy_soc2_tables(engine)
        if created:
            logger.info(f"SOC 2 tables created: {', '.join(created)}")
        else:
            logger.info("SOC 2 tables already exist")
    except Exception as e:
        logger.warning(f"SOC 2 table migration note: {e}")


def _run_eeoc_nmls_migration():
    """Add EEOC demographic + NMLS license tracking fields to mm_candidates."""
    try:
        from migrations.add_eeoc_nmls_candidate_fields import run_migration as run_eeoc_nmls_migration
        eeoc_result = run_eeoc_nmls_migration()
        logger.info(f"EEOC/NMLS migration: {eeoc_result.get('message', 'done')}")
    except Exception as e:
        logger.warning(f"EEOC/NMLS migration note: {e}")


def _run_recruiting_org_id_v2():
    """Add organization_id to remaining recruiting tables."""
    try:
        from migrations.add_org_id_recruiting_tables_v2 import run_migration as run_org_id_v2
        org_v2_result = run_org_id_v2()
        logger.info(f"Recruiting org_id v2: {len(org_v2_result.get('processed', []))} tables")
    except Exception as e:
        logger.warning(f"Recruiting org_id v2 note: {e}")


def _run_disposition_tracking():
    """Add OFCCP disposition tracking columns."""
    try:
        from migrations.add_disposition_tracking import run_migration as run_disposition
        disp_result = run_disposition()
        logger.info(f"Disposition tracking: {len(disp_result.get('added', []))} columns")
    except Exception as e:
        logger.warning(f"Disposition tracking note: {e}")


def _run_ai_audit_log():
    """Create AI decision audit log table."""
    try:
        from migrations.add_recruit_ai_audit_log import run_migration as run_ai_audit
        ai_audit_result = run_ai_audit()
        logger.info(f"AI audit log: created={ai_audit_result.get('created', False)}")
    except Exception as e:
        logger.warning(f"AI audit log note: {e}")


def _run_assessment_tables():
    """Create recruiting assessment quiz + portal tables (11 tables)."""
    try:
        from migrations.add_recruit_assessment_tables import run_migration as run_assessment
        run_assessment()
        logger.info("recruit assessment + portal tables ready")
    except Exception as e:
        logger.warning(f"recruit assessment tables note: {e}")


def _run_social_recruiting(engine):
    """Create recruit_social_posts + candidate_linkedin_posts tables."""
    try:
        from migrations.create_social_recruiting_tables import run_migration as run_social_recruiting
        run_social_recruiting(engine)
        logger.info("recruit social posts tables ready")
    except Exception as e:
        logger.warning(f"recruit social posts tables note: {e}")


def _run_social_oauth(engine):
    """Create social_oauth_states + social_tokens tables."""
    try:
        from migrations.create_social_oauth_tables import run_migration as run_social_oauth
        run_social_oauth(engine)
        logger.info("social_oauth_states + social_tokens tables ready")
    except Exception as e:
        logger.warning(f"social oauth tables note: {e}")


def _run_recruit_workflow_config():
    """Create recruit_workflow_config table for per-org workflow customization."""
    try:
        from migrations.add_recruit_workflow_config import run_migration as run_wf_config
        run_wf_config()
        logger.info("recruit_workflow_config table ready")
    except Exception as e:
        logger.warning(f"recruit workflow config note: {e}")


def _run_social_tokens_org_id(engine):
    """Add organization_id to social_tokens for tenant isolation."""
    try:
        from migrations.add_social_tokens_org_id import run_migration as run_social_tokens_org
        run_social_tokens_org(engine)
        logger.info("social_tokens org_id migration complete")
    except Exception as e:
        logger.warning(f"social_tokens org_id note: {e}")


def _run_ops_sweep_results(engine):
    """Create ops_sweep_results table."""
    try:
        from migrations.create_ops_sweep_results import run_migration as run_ops_sweep
        run_ops_sweep(engine)
        logger.info("ops_sweep_results migration complete")
    except Exception as e:
        logger.warning(f"ops_sweep_results note: {e}")


def _run_tasktype_enum_sync(engine):
    """Sync tasktype enum (ensure Python TaskType values exist in DB)."""
    try:
        from migrations.sync_tasktype_enum import run_migration as run_tasktype_sync
        run_tasktype_sync(engine)
        logger.info("tasktype enum sync complete")
    except Exception as e:
        logger.warning(f"tasktype enum sync note: {e}")


def _run_campaign_template_seed(engine):
    """Seed campaign email templates."""
    try:
        from migrations.seed_campaign_templates import run_migration as run_campaign_seed
        run_campaign_seed(engine)
        logger.info("campaign template seed complete")
    except Exception as e:
        logger.warning(f"campaign template seed note: {e}")
