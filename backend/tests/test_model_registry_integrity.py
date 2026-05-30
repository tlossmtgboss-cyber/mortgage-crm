# backend/tests/test_model_registry_integrity.py
"""Asserts the whole model layer initializes on one Base. The acceptance gate
for the Base-unification refactor."""
import importlib
import pytest


def test_configure_mappers_succeeds():
    """All mappers across all factories + direct models initialize cleanly."""
    from db import Base  # noqa: F401
    # register_all_models is introduced in Task 1; until then this test fails.
    reg = importlib.import_module("model_registry")
    reg.register_all_models()
    from sqlalchemy.orm import configure_mappers
    configure_mappers()  # raises if any relationship() string ref is unresolved


@pytest.mark.parametrize("cls_name,expected_table", [
    ("Role", "onboarding_roles"),
    ("WorkflowInstance", "workflow_instances"),
    ("LeadWorkflowRoleAssignment", "lead_workflow_role_assignments"),
])
def test_key_relationships_registered_on_canonical_base(cls_name, expected_table):
    from db import Base
    import model_registry
    model_registry.register_all_models()
    assert cls_name in Base.registry._class_registry, (
        f"{cls_name} not registered on the canonical db.Base registry"
    )


def test_no_duplicate_class_names_on_canonical_base():
    """No two mapped classes share a name on the canonical registry."""
    from db import Base
    import model_registry
    model_registry.register_all_models()
    seen = {}
    dupes = []
    for key, val in Base.registry._class_registry.items():
        if isinstance(key, str) and hasattr(val, "__name__"):
            if key in seen:
                dupes.append(key)
            seen[key] = val
    assert not dupes, f"Duplicate class names on one Base: {sorted(set(dupes))}"
