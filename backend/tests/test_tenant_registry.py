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
    """
    from db import Base

    # Force all model modules to be imported so mappers are registered
    import database.models  # noqa: F401

    models = {}
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if hasattr(cls, "__tablename__") and not getattr(cls, "__abstract__", False):
            # Use the class name as-is. Handle aliased imports
            # (e.g. SmartDocsEscalationRule is an alias for EscalationRule)
            name = cls.__name__
            # The __init__.py may export under an alias — check if the name
            # or an alias appears in the registry
            models[name] = cls
    return models


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
        all_models = _discover_all_models()

        missing_org_id = []
        for name in sorted(tenant):
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
        all_models = _discover_all_models()

        has_org_id = []
        for name in sorted(system):
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
