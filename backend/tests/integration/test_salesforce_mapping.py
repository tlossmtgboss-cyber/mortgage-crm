"""
Unit-style integration tests for the Salesforce sync mapping helpers.

Targets backend/services/salesforce/_mapping.py — CRM stage → SF stage
translation, lead/loan stage maps, field grouping by object/entity, and the
LOAN_TO_LEAD_FIELD_MAP rename rules.

Loaded via importlib.util.spec_from_file_location to bypass package __init__
side effects.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_mapping():
    target = _BACKEND_DIR / "services" / "salesforce" / "_mapping.py"
    if not target.exists():
        pytest.skip("salesforce/_mapping.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_sf_mapping", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_m = _load_mapping()


# ---------------------------------------------------------------------------
# Test 1: All canonical CRM loan stages map to a Salesforce stage
# ---------------------------------------------------------------------------

def test_all_loan_stages_have_sf_mapping():
    for crm_stage in ["Application", "Processing", "Submitted", "Underwriting",
                      "Approved", "Funded", "Cancelled", "Denied"]:
        assert crm_stage in _m.CRM_LOAN_STAGE_TO_SF


# ---------------------------------------------------------------------------
# Test 2: Funded → Closed Won
# ---------------------------------------------------------------------------

def test_funded_maps_to_closed_won():
    assert _m.map_crm_stage_to_salesforce("Funded") == "Closed Won"


# ---------------------------------------------------------------------------
# Test 3: Cancelled and Denied both map to Closed Lost
# ---------------------------------------------------------------------------

def test_cancelled_and_denied_map_to_closed_lost():
    assert _m.map_crm_stage_to_salesforce("Cancelled") == "Closed Lost"
    assert _m.map_crm_stage_to_salesforce("Denied") == "Closed Lost"


# ---------------------------------------------------------------------------
# Test 4: Unknown CRM stage falls back to "Qualification"
# ---------------------------------------------------------------------------

def test_unknown_stage_defaults_to_qualification():
    assert _m.map_crm_stage_to_salesforce("CompletelyUnknownStage") == "Qualification"


# ---------------------------------------------------------------------------
# Test 5: Lead stage map round-trips known statuses
# ---------------------------------------------------------------------------

def test_lead_stage_mapping_known_values():
    assert _m.map_crm_lead_stage_to_salesforce("new") == "Open - Not Contacted"
    assert _m.map_crm_lead_stage_to_salesforce("contacted") == "Working - Contacted"
    assert _m.map_crm_lead_stage_to_salesforce("converted") == "Closed - Converted"


# ---------------------------------------------------------------------------
# Test 6: Unknown lead stage defaults to "Open - Not Contacted"
# ---------------------------------------------------------------------------

def test_unknown_lead_stage_defaults():
    assert _m.map_crm_lead_stage_to_salesforce("zzz") == "Open - Not Contacted"


# ---------------------------------------------------------------------------
# Test 7: remap_loan_fields_for_lead renames loan-shaped fields
# ---------------------------------------------------------------------------

def test_remap_loan_fields_renames_to_lead_columns():
    valid_lead_cols = {"name", "email", "phone", "loan_amount", "city",
                       "state", "zip_code", "interest_rate"}
    src = {
        "borrower_name": "Jane Doe",
        "borrower_email": "jane@example.com",
        "borrower_phone": "+18435551234",
        "amount": 350000,
        "property_city": "Charleston",
    }
    out = _m.remap_loan_fields_for_lead(src, valid_lead_cols)
    assert out["name"] == "Jane Doe"
    assert out["email"] == "jane@example.com"
    assert out["phone"] == "+18435551234"
    assert out["loan_amount"] == 350000
    assert out["city"] == "Charleston"


# ---------------------------------------------------------------------------
# Test 8: remap drops fields with no lead equivalent
# ---------------------------------------------------------------------------

def test_remap_drops_unknown_fields():
    out = _m.remap_loan_fields_for_lead(
        {"borrower_name": "X", "weird_unknown_col": "drop_me"},
        valid_lead_columns={"name"},
    )
    assert "weird_unknown_col" not in out


# ---------------------------------------------------------------------------
# Test 9: group_mappings_by_object buckets by source_object
# ---------------------------------------------------------------------------

def test_group_mappings_by_object_partitions():
    mappings = [
        SimpleNamespace(source_object="Account", target_entity="leads"),
        SimpleNamespace(source_object="Account", target_entity="loans"),
        SimpleNamespace(source_object="Opportunity", target_entity="loans"),
    ]
    grouped = _m.group_mappings_by_object(mappings)
    assert set(grouped.keys()) == {"Account", "Opportunity"}
    assert len(grouped["Account"]) == 2
    assert len(grouped["Opportunity"]) == 1


# ---------------------------------------------------------------------------
# Test 10: group_mappings_by_entity buckets by target_entity
# ---------------------------------------------------------------------------

def test_group_mappings_by_entity_partitions():
    mappings = [
        SimpleNamespace(source_object="Account", target_entity="leads"),
        SimpleNamespace(source_object="Account", target_entity="loans"),
        SimpleNamespace(source_object="Opportunity", target_entity="loans"),
    ]
    grouped = _m.group_mappings_by_entity(mappings)
    assert set(grouped.keys()) == {"leads", "loans"}
    assert len(grouped["loans"]) == 2
