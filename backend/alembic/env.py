"""
Alembic Environment Configuration
Perennia AI - Mortgage CRM

This module configures Alembic to:
1. Read DATABASE_URL from environment (never hardcoded)
2. Import all SQLAlchemy models so autogenerate can diff them
3. Support both online and offline migrations
4. Handle PostgreSQL-specific features (postgres:// -> postgresql://)
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add parent directory (backend/) to path so that `from database import Base`
# and `import database.models` resolve correctly regardless of cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Alembic Config object (reads alembic.ini)
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import models for autogenerate support
# ---------------------------------------------------------------------------
# Base comes from db.py via database/__init__.py.
# Importing database.models triggers all model module imports, which registers
# every table on Base.metadata so that `--autogenerate` can diff them.
import logging as _logging
from database import Base
import database.models  # noqa: F401 — registers all model classes with Base
import engine.models  # noqa: F401 — registers CIE tables with Base

# ---------------------------------------------------------------------------
# database/models/ submodules not imported by database/models/__init__.py
# Each file defines SQLAlchemy tables that must appear in target_metadata for
# autogenerate to produce a complete diff.  Wrapped individually so a single
# broken import does not abort the whole alembic command.
# ---------------------------------------------------------------------------
_EXTRA_DB_MODEL_SUBMODULES = [
    "database.models.agent_context",
    "database.models.agent_escalation",
    "database.models.agent_registry",
    "database.models.audit",
    "database.models.audit_event",
    "database.models.borrower_prep",
    "database.models.call_authorization",
    "database.models.call_disposition",
    "database.models.content_governance",
    "database.models.demo_data",
    "database.models.doc_notification",
    "database.models.drip_enrollment",
    "database.models.email_tracking",
    "database.models.engagement_event",
    "database.models.file_collaborator",
    "database.models.file_communication",
    "database.models.income_calculation",
    "database.models.live_transfer",
    "database.models.lo_availability",
    "database.models.memory_topic_config",
    "database.models.notification_preference",
    "database.models.oauth_token",
    "database.models.pos",
    "database.models.pos_consent",
    "database.models.recovery_opt_out",
    "database.models.registry",
    "database.models.sms_compliance",
    "database.models.sms_conversation",
    "database.models.sms_dead_letter",
    "database.models.sms_task",
    "database.models.tcpa_consent",
    "database.models.vendor",
    "database.models.voice_call_session",
    "database.models.voice_workflow",
    "database.models.webhook_idempotency",
]

import importlib as _importlib

for _mod_name in _EXTRA_DB_MODEL_SUBMODULES:
    try:
        _importlib.import_module(_mod_name)
    except ImportError as _exc:
        _logging.getLogger("alembic.env").warning(
            "Could not import %s for autogenerate: %s", _mod_name, _exc
        )

# ---------------------------------------------------------------------------
# models/ package — secondary SQLAlchemy models (profile types, agent
# governance, microsite, billing, etc.)  The package __init__.py only
# imports a subset; import the rest individually here.
# ---------------------------------------------------------------------------
_EXTRA_MODELS_SUBMODULES = [
    "models.ai_daily_blog",
    "models.bank_statement_models",
    "models.billing",
    "models.business_operations",
    "models.calendar_sync_models",
    "models.call_monitoring_models",
    "models.call_screening_models",
    "models.carousel_builder",
    "models.content_marketing",
    "models.conversation_intelligence_models",
    "models.custom_domains",
    "models.document_extraction",
    "models.document_visibility",
    "models.email_monitor",
    "models.financial_intelligence",
    "models.followupboss_models",
    "models.income_engine_models",
    "models.income_models",
    "models.master_manager_models",
    "models.pii_audit_log",
    "models.portal_models",
    "models.presentation",
    "models.profitability",
    "models.purl",
    "models.rate_monitor",
    "models.rate_sheet",
    "models.salesforce_sync_log",
    "models.surveying_models",
    "models.tenant",
    "models.usage_tracking",
    "models.user_onboarding",
]

for _mod_name in _EXTRA_MODELS_SUBMODULES:
    try:
        _importlib.import_module(_mod_name)
    except ImportError as _exc:
        _logging.getLogger("alembic.env").warning(
            "Could not import %s for autogenerate: %s", _mod_name, _exc
        )

# ---------------------------------------------------------------------------
# Factory-based model packages
# These modules define tables inside factory functions (create_X_models(Base)).
# Call each factory so the resulting classes are registered on Base.metadata.
# ---------------------------------------------------------------------------
try:
    from models.esign_models import create_esign_models as _create_esign_models
    _create_esign_models(Base)
except Exception as _exc:
    _logging.getLogger("alembic.env").warning(
        "Could not register esign models: %s", _exc
    )

try:
    from models.feature_flags import create_feature_models as _create_feature_models
    _create_feature_models(Base)
except Exception as _exc:
    _logging.getLogger("alembic.env").warning(
        "Could not register feature flag models: %s", _exc
    )

try:
    from models.workflow_sla import create_workflow_sla_models as _create_workflow_sla_models
    _create_workflow_sla_models(Base)
except Exception as _exc:
    _logging.getLogger("alembic.env").warning(
        "Could not register workflow SLA models: %s", _exc
    )

try:
    from models.perennia_docs import create_perennia_docs_models as _create_perennia_docs_models
    _create_perennia_docs_models(Base)
except Exception as _exc:
    _logging.getLogger("alembic.env").warning(
        "Could not register Perennia Docs models: %s", _exc
    )

try:
    from workflow_config_models import create_workflow_config_models as _create_workflow_config_models
    _create_workflow_config_models(Base)
except Exception as _exc:
    _logging.getLogger("alembic.env").warning(
        "Could not register workflow config models: %s", _exc
    )

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Database URL helper
# ---------------------------------------------------------------------------
def get_url() -> str:
    """Get database URL from the DATABASE_URL environment variable.

    Applies the postgres:// -> postgresql:// fix needed by Railway/Heroku
    URLs that use the older prefix unsupported by SQLAlchemy 1.4+.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError(
            "DATABASE_URL environment variable is not set. "
            "Set it before running Alembic commands."
        )

    # Fix for Railway/Heroku postgres:// prefix
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


# ---------------------------------------------------------------------------
# Tables / types to exclude from autogenerate diffs
# ---------------------------------------------------------------------------
def include_object(object, name, type_, reflected, compare_to):
    """Filter objects from autogenerate comparison.

    Excludes:
    - The alembic_version table itself
    - Any spatial/PostGIS internal tables if they appear
    """
    if type_ == "table" and name == "alembic_version":
        return False
    return True


# ---------------------------------------------------------------------------
# Offline migrations (emit SQL without connecting)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL. Calls to context.execute()
    emit SQL strings to the script output — useful for generating SQL
    scripts to be applied by a DBA.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations (connect to DB and run)
# ---------------------------------------------------------------------------
def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine, connects to the database, and runs migration
    operations inside a transaction.
    """
    # Override the placeholder sqlalchemy.url from alembic.ini with the
    # real URL from the environment variable.
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Don't pool — migrations are short-lived
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,             # Detect column type changes
            compare_server_default=True,   # Detect server default changes
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
