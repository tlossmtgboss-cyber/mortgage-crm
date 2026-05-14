"""
Tests for the tenant/system model registry.

Validates that every SQLAlchemy model is classified in exactly one registry
and that the classification matches the actual schema.
"""

import sys
from pathlib import Path

import pytest

# Ensure backend is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _discover_all_models():
    """Discover all SQLAlchemy model classes registered with Base.

    Returns a dict of {class_name: model_class} for every concrete model
    that has a __tablename__ (excluding abstract bases and enum classes).

    We must import every module that defines SQLAlchemy models so that
    their mappers are registered before we enumerate them. This mirrors
    what happens when main.py boots the FastAPI app.
    """
    import importlib
    from pathlib import Path
    from db import Base

    # Force all model modules to be imported so mappers are registered.
    # 1) Primary models package (database/models/__init__.py re-exports)
    import database.models  # noqa: F401

    # 2) ALL sub-modules in database/models/ (many are not re-exported
    #    by __init__.py but define models used by routes/services)
    models_dir = Path(__file__).parent.parent / "database" / "models"
    for py_file in sorted(models_dir.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        module_name = f"database.models.{py_file.stem}"
        _safe_import(module_name)

    # 3) Legacy models in backend/models/ directory.
    #    Skip modules that define factory functions which create models
    #    with conflicting class names (e.g., perennia_docs.DocumentRequest
    #    vs smart_docs_models.DocumentRequest).  Also skip modules whose
    #    tables collide with database/models/ tables (income_models ->
    #    income_sources, user_onboarding -> onboarding_roles, etc.).
    _SKIP_LEGACY = {
        "perennia_docs",       # Factory creates conflicting DocumentRequest
        "income_models",       # Table 'income_sources' conflicts with database/models/income_calculation.py
        "user_onboarding",     # Table names conflict with user_onboarding_integration.py
    }
    legacy_models_dir = Path(__file__).parent.parent / "models"
    for py_file in sorted(legacy_models_dir.glob("*.py")):
        if py_file.name == "__init__.py" or py_file.stem in _SKIP_LEGACY:
            continue
        _safe_import(f"models.{py_file.stem}")
    # Legacy models sub-packages
    for sub_dir in sorted(legacy_models_dir.iterdir()):
        if sub_dir.is_dir() and (sub_dir / "__init__.py").exists():
            for py_file in sorted(sub_dir.glob("*.py")):
                if py_file.name == "__init__.py":
                    continue
                _safe_import(f"models.{sub_dir.name}.{py_file.stem}")

    # 4) Scattered backend-root model files.
    #    Skip modules_mum (table 'mum_clients' conflicts with database/models/referral.py)
    #    and workflow_models (table 'workflow_executions' conflicts with database/models/workflow.py).
    for name in [
        "ab_testing_models", "ai_receptionist_dashboard_models",
        "chat_state_machine_models", "conversation_memory_models",
        "guideline_updates_models", "microsite_models",
        "salesforce_integration_models", "scheduler_enhancements",
        "subscription_models", "user_onboarding_integration",
        "vapi_models", "video_clip_models", "video_meeting_models",
        "workflow_config_models",
    ]:
        _safe_import(name)

    # 5) Route/service files that define models inline
    for name in [
        "routes.ai_activity_routes", "routes.ai_email_settings_routes",
        "routes.analytics_tracking_routes", "routes.beta_routes",
        "routes.calendly_routes", "routes.email_integration_settings_routes",
        "routes.email_training_routes", "routes.file_collaborator_routes",
        "routes.pre_approval_letter_settings_routes",
        "routes.support_tickets_routes",
        "services.pipeline_appointment_trigger",
        "services.smart_scheduler_service", "services.holiday_service",
    ]:
        _safe_import(name)

    # 6) Integration model files
    _safe_import("integrations.microsoft365.models")
    _safe_import("integrations.imessage.models")

    # 7) Call factory functions that create models inside closures.
    #    These models only register when the factory is invoked.
    _call_factory("models.workflow_sla", "create_workflow_sla_models", Base)
    # NOTE: perennia_docs factory skipped — its DocumentRequest class replaces
    # the smart_docs_models.DocumentRequest in the mapper, causing name conflict.
    # The perennia_docs models (PerenniaDocument, TemplatePack, etc.) are imported
    # via the legacy models directory instead.
    _call_factory("models.esign_models", "create_esign_models", Base)
    _call_factory("models.feature_flags", "create_feature_models", Base)
    _call_factory("user_onboarding_integration", "create_user_onboarding_models", Base)
    _call_factory("video_clip_models", "create_video_clip_models", Base)
    _call_factory("video_meeting_models", "create_video_meeting_models", Base)
    _call_factory("workflow_config_models", "create_workflow_config_models", Base)
    _call_factory("scheduler_enhancements", "create_scheduler_enhancement_models", Base)
    _call_factory("services.holiday_service", "create_holiday_models", Base)

    models = {}
    for manager in Base.registry._managers:
        try:
            mapper = manager.mapper
        except Exception:
            # Skip classes that were replaced in the string-lookup table
            # due to name collisions between legacy and primary models.
            continue
        cls = mapper.class_
        if hasattr(cls, "__tablename__") and not getattr(cls, "__abstract__", False):
            name = cls.__name__
            models[name] = cls
    return models


def _call_factory(module_name, func_name, Base):
    """Import a module and call a model factory function."""
    import importlib
    try:
        mod = importlib.import_module(module_name)
        factory = getattr(mod, func_name, None)
        if factory:
            factory(Base)
    except Exception:
        pass


def _safe_import(module_name):
    """Import a module, ignoring errors from unavailable dependencies.

    Logs warnings for unexpected failures to aid debugging.
    """
    import importlib
    import warnings
    try:
        importlib.import_module(module_name)
    except ImportError:
        # Missing dependency is expected for some optional integrations
        pass
    except Exception as exc:
        warnings.warn(f"Failed to import {module_name}: {exc}")


def _get_registry_names():
    """Return (tenant_set, system_set) from the tenant_registry module."""
    from database.tenant_registry import TENANT_SCOPED_MODELS, SYSTEM_SCOPED_MODELS
    return TENANT_SCOPED_MODELS, SYSTEM_SCOPED_MODELS


def _get_aliases():
    """Return a mapping of alias_name -> real_class_name for models
    exported under a different name in __init__.py.

    Example: SmartDocsEscalationRule is exported from __init__.py but the
    actual class is EscalationRule in escalation_rule.py.
    """
    return {
        "SmartDocsEscalationRule": "EscalationRule",
        "SmartDocsEscalationEvent": "EscalationEvent",
        "SmartDocsEmailTemplate": "EmailTemplate",
        "SchedulerAppointment": "Appointment",
        "SchedulerAppointmentReminder": "AppointmentReminder",
    }


def _get_class_name_collisions():
    """Return a set of model names where multiple SQLAlchemy classes share
    the same Python class name but map to different tables.

    When two classes collide, the last-registered one wins the mapper
    string-lookup, so the discovered class may have different columns than
    the registry entry intends. These names are excluded from org_id
    validation tests (but still checked for completeness).

    Example: smart_docs_models.DocumentRequest (smart_document_requests,
    has org_id) vs perennia_docs.DocumentRequest (perennia_document_requests,
    no org_id). The registry entry refers to the smart_docs version.
    """
    return {
        "DocumentRequest",
    }


class TestTenantRegistry:
    """Validate the TENANT_SCOPED_MODELS and SYSTEM_SCOPED_MODELS registries."""

    def test_no_model_in_both_registries(self):
        """No model can be both tenant-scoped and system-scoped."""
        tenant, system = _get_registry_names()
        overlap = tenant & system
        assert overlap == set(), (
            f"Models appear in BOTH registries (must be in exactly one): {sorted(overlap)}"
        )

    def test_every_model_in_exactly_one_registry(self):
        """Every discovered SQLAlchemy model must be classified."""
        tenant, system = _get_registry_names()
        aliases = _get_aliases()
        all_models = _discover_all_models()

        # Build the set of names that the registry knows about,
        # resolving aliases to real class names
        registry_real_names = set()
        for name in (tenant | system):
            if name in aliases:
                registry_real_names.add(aliases[name])
            else:
                registry_real_names.add(name)

        missing = set()
        for model_name in all_models:
            if model_name not in registry_real_names and model_name not in (tenant | system):
                missing.add(model_name)

        assert missing == set(), (
            f"Models not in either registry (add to TENANT_SCOPED_MODELS or "
            f"SYSTEM_SCOPED_MODELS in database/tenant_registry.py): {sorted(missing)}"
        )

    def test_tenant_scoped_models_have_org_id(self):
        """All tenant-scoped models must have an organization_id column."""
        tenant, _ = _get_registry_names()
        aliases = _get_aliases()
        collisions = _get_class_name_collisions()
        all_models = _discover_all_models()

        missing_org_id = []
        for name in sorted(tenant):
            if name in collisions:
                continue  # Skip: runtime class may differ from intended class
            # Resolve alias to real class name
            real_name = aliases.get(name, name)
            cls = all_models.get(real_name) or all_models.get(name)
            if cls is None:
                # Model in registry but not discovered — could be a stale entry
                continue

            columns = {c.name for c in cls.__table__.columns}
            if "organization_id" not in columns:
                missing_org_id.append(name)

        assert missing_org_id == [], (
            f"Models in TENANT_SCOPED_MODELS that lack organization_id column "
            f"(move to SYSTEM_SCOPED_MODELS or add the column): {missing_org_id}"
        )

    def test_system_scoped_models_lack_org_id(self):
        """System-scoped models should NOT have organization_id.

        If a model has organization_id it should be in TENANT_SCOPED_MODELS
        so RLS policies can filter it. This test warns about potential
        misclassifications.
        """
        _, system = _get_registry_names()
        aliases = _get_aliases()
        collisions = _get_class_name_collisions()
        all_models = _discover_all_models()

        has_org_id = []
        for name in sorted(system):
            if name in collisions:
                continue  # Skip: runtime class may differ from intended class
            real_name = aliases.get(name, name)
            cls = all_models.get(real_name) or all_models.get(name)
            if cls is None:
                continue

            columns = {c.name for c in cls.__table__.columns}
            if "organization_id" in columns:
                has_org_id.append(name)

        assert has_org_id == [], (
            f"Models in SYSTEM_SCOPED_MODELS that HAVE organization_id column "
            f"(should they be in TENANT_SCOPED_MODELS?): {has_org_id}"
        )

    def test_no_stale_registry_entries(self):
        """Registry entries must correspond to actual model classes."""
        tenant, system = _get_registry_names()
        aliases = _get_aliases()
        all_models = _discover_all_models()

        all_real_names = set(all_models.keys())
        stale = []

        for name in sorted(tenant | system):
            real_name = aliases.get(name, name)
            if real_name not in all_real_names and name not in all_real_names:
                stale.append(name)

        assert stale == [], (
            f"Registry entries with no corresponding SQLAlchemy model "
            f"(remove from registry): {stale}"
        )
