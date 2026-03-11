"""
Test Salesforce Sync — Field Mapping, Stage Mapping, and Sync Logic

Verifies:
- TRANSACTION_PROPERTY_MAPPINGS structure and completeness
- SALESFORCE_STAGE_MAPPING correctness (SF stages -> CRM LoanStage)
- Field mapping validation logic (required fields, type compatibility)
- transform_value() for direct, stage_map, date_format, phone_format, currency
- Null/empty field handling during sync
- DEFAULT_STAGE_MAPPINGS consistency with canonical stage mapping
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


# =============================================================================
# SALESFORCE_STAGE_MAPPING tests
# =============================================================================

@pytest.mark.unit
class TestSalesforceStageMapping:
    """Test the canonical Salesforce -> CRM stage mapping."""

    def test_stage_mapping_imports(self):
        """SALESFORCE_STAGE_MAPPING is importable and non-empty."""
        from services.salesforce.stage_mapping import SALESFORCE_STAGE_MAPPING
        assert isinstance(SALESFORCE_STAGE_MAPPING, dict)
        assert len(SALESFORCE_STAGE_MAPPING) > 50, (
            "Expected 50+ stage mappings to cover common SF status values"
        )

    def test_closed_maps_to_funded(self):
        """SF 'Closed' and 'Closed Won' must map to CRM FUNDED."""
        from services.salesforce.stage_mapping import SALESFORCE_STAGE_MAPPING
        assert SALESFORCE_STAGE_MAPPING["Closed"] == "FUNDED"
        assert SALESFORCE_STAGE_MAPPING["Closed Won"] == "FUNDED"

    def test_funded_maps_to_funded(self):
        """SF 'Funded' and 'Loan Funded' must map to CRM FUNDED."""
        from services.salesforce.stage_mapping import SALESFORCE_STAGE_MAPPING
        assert SALESFORCE_STAGE_MAPPING["Funded"] == "FUNDED"
        assert SALESFORCE_STAGE_MAPPING["Loan Funded"] == "FUNDED"

    def test_terminal_stages_mapped(self):
        """Cancelled, Denied, Withdrawn must map to their CRM equivalents."""
        from services.salesforce.stage_mapping import SALESFORCE_STAGE_MAPPING
        assert SALESFORCE_STAGE_MAPPING["Cancelled"] == "CANCELLED"
        assert SALESFORCE_STAGE_MAPPING["Denied"] == "DENIED"
        assert SALESFORCE_STAGE_MAPPING["Withdrawn"] == "WITHDRAWN"
        assert SALESFORCE_STAGE_MAPPING["Dead"] == "DEAD"

    def test_all_mapped_values_are_valid_loan_stages(self):
        """Every mapped value must be a valid LoanStage enum value."""
        from services.salesforce.stage_mapping import SALESFORCE_STAGE_MAPPING
        from database.enums import LoanStage

        valid_stages = {s.value for s in LoanStage}
        for sf_stage, crm_stage in SALESFORCE_STAGE_MAPPING.items():
            assert crm_stage in valid_stages, (
                f"SF stage '{sf_stage}' maps to '{crm_stage}' "
                f"which is not a valid LoanStage enum value"
            )

    def test_map_salesforce_stage_function_returns_none_for_unknown(self):
        """map_salesforce_stage() returns None for unmapped stages."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage("SomeUnknownStage") is None

    def test_map_salesforce_stage_returns_none_for_empty(self):
        """map_salesforce_stage() returns None for empty/None input."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage("") is None
        assert map_salesforce_stage(None) is None

    def test_processing_variants_all_map_to_processing(self):
        """Multiple SF processing stage variants must all map to PROCESSING."""
        from services.salesforce.stage_mapping import SALESFORCE_STAGE_MAPPING
        processing_variants = [
            "Processing", "Processed", "In Processing",
            "Submitted to Processing", "Loan in Process",
        ]
        for variant in processing_variants:
            assert SALESFORCE_STAGE_MAPPING.get(variant) == "PROCESSING", (
                f"Expected '{variant}' to map to PROCESSING"
            )


# =============================================================================
# TRANSACTION_PROPERTY_MAPPINGS tests
# =============================================================================

@pytest.mark.unit
class TestTransactionPropertyMappings:
    """Test the default SF Transaction_Property field mappings."""

    def test_mappings_importable_and_nonempty(self):
        """TRANSACTION_PROPERTY_MAPPINGS is importable and has entries."""
        from routes.salesforce_integration_routes import TRANSACTION_PROPERTY_MAPPINGS
        assert isinstance(TRANSACTION_PROPERTY_MAPPINGS, list)
        assert len(TRANSACTION_PROPERTY_MAPPINGS) > 30, (
            "Expected 30+ field mappings for Transaction_Property object"
        )

    def test_all_mappings_have_required_keys(self):
        """Each mapping must have source_field, target_entity, target_field, transform_type."""
        from routes.salesforce_integration_routes import TRANSACTION_PROPERTY_MAPPINGS
        required_keys = {"source_field", "target_entity", "target_field", "transform_type"}
        for i, mapping in enumerate(TRANSACTION_PROPERTY_MAPPINGS):
            missing = required_keys - set(mapping.keys())
            assert not missing, (
                f"Mapping index {i} ({mapping.get('source_field', '?')}) "
                f"missing keys: {missing}"
            )

    def test_all_target_entities_are_loan(self):
        """All Transaction_Property mappings should target the 'loan' entity."""
        from routes.salesforce_integration_routes import TRANSACTION_PROPERTY_MAPPINGS
        for mapping in TRANSACTION_PROPERTY_MAPPINGS:
            assert mapping["target_entity"] == "loan", (
                f"Expected target_entity='loan' for {mapping['source_field']}, "
                f"got '{mapping['target_entity']}'"
            )

    def test_stage_field_uses_stage_map_transform(self):
        """The status/stage field must use stage_map transform, not direct."""
        from routes.salesforce_integration_routes import TRANSACTION_PROPERTY_MAPPINGS
        stage_mappings = [
            m for m in TRANSACTION_PROPERTY_MAPPINGS
            if m["target_field"] == "stage"
        ]
        assert len(stage_mappings) == 1, "Expected exactly one stage field mapping"
        assert stage_mappings[0]["transform_type"] == "stage_map", (
            "Stage field should use 'stage_map' transform, not "
            f"'{stage_mappings[0]['transform_type']}'"
        )

    def test_date_fields_use_date_format_transform(self):
        """Date target fields (closing_date, funded_date, etc.) must use date_format."""
        from routes.salesforce_integration_routes import TRANSACTION_PROPERTY_MAPPINGS
        date_target_fields = {
            "closing_date", "funded_date", "application_date",
            "lock_expiration_date", "lock_date"
        }
        for mapping in TRANSACTION_PROPERTY_MAPPINGS:
            if mapping["target_field"] in date_target_fields:
                assert mapping["transform_type"] == "date_format", (
                    f"Date field '{mapping['target_field']}' should use 'date_format' "
                    f"transform, got '{mapping['transform_type']}'"
                )

    def test_no_duplicate_target_fields(self):
        """No two mappings should write to the same target_field."""
        from routes.salesforce_integration_routes import TRANSACTION_PROPERTY_MAPPINGS
        seen = {}
        for mapping in TRANSACTION_PROPERTY_MAPPINGS:
            target = mapping["target_field"]
            if target in seen:
                pytest.fail(
                    f"Duplicate target_field '{target}': "
                    f"'{seen[target]}' and '{mapping['source_field']}'"
                )
            seen[target] = mapping["source_field"]


# =============================================================================
# FieldMappingService.transform_value tests
# =============================================================================

@pytest.mark.unit
class TestFieldMappingTransformValue:
    """Test the transform_value method on FieldMappingService."""

    def _get_service(self):
        from services.salesforce.field_mapping_service import FieldMappingService
        return FieldMappingService()

    def test_direct_transform_passes_through(self):
        """Direct transform returns value unchanged."""
        svc = self._get_service()
        assert svc.transform_value("hello", "direct", {}) == "hello"
        assert svc.transform_value(42, "direct", {}) == 42

    def test_stage_map_transform_maps_known_value(self):
        """Stage map transform maps known values."""
        svc = self._get_service()
        config = {"mappings": {"Closed Won": "FUNDED", "New Lead": "APPLICATION"}}
        assert svc.transform_value("Closed Won", "stage_map", config) == "FUNDED"
        assert svc.transform_value("New Lead", "stage_map", config) == "APPLICATION"

    def test_stage_map_transform_uses_default_for_unknown(self):
        """Stage map returns default value for unknown input."""
        svc = self._get_service()
        config = {"mappings": {"Closed Won": "FUNDED"}, "default": "APPLICATION"}
        assert svc.transform_value("UnknownStage", "stage_map", config) == "APPLICATION"

    def test_null_value_returns_config_default(self):
        """None input returns config default if present."""
        svc = self._get_service()
        config = {"default": "APPLICATION"}
        result = svc.transform_value(None, "stage_map", config)
        assert result == "APPLICATION"

    def test_null_value_without_config_returns_none(self):
        """None input with no config returns None."""
        svc = self._get_service()
        result = svc.transform_value(None, "direct", None)
        assert result is None

    def test_phone_format_transform_10_digits(self):
        """Phone format transform formats 10-digit numbers."""
        svc = self._get_service()
        config = {"format": "national", "defaultCountry": "US"}
        result = svc.transform_value("5551234567", "phone_format", config)
        assert result == "(555) 123-4567"

    def test_currency_convert_rounds_correctly(self):
        """Currency convert respects decimal places."""
        svc = self._get_service()
        config = {"decimalPlaces": 2}
        result = svc.transform_value("450000.567", "currency_convert", config)
        assert result == 450000.57

    def test_date_format_transform_iso_string(self):
        """Date format transform handles ISO date strings."""
        svc = self._get_service()
        config = {"outputFormat": "iso8601"}
        result = svc.transform_value("2026-03-15T10:00:00Z", "date_format", config)
        assert "2026-03-15" in str(result)


# =============================================================================
# FieldMappingService._validate_mapping tests
# =============================================================================

@pytest.mark.unit
class TestFieldMappingValidation:
    """Test mapping validation logic."""

    def _get_service(self):
        from services.salesforce.field_mapping_service import FieldMappingService
        return FieldMappingService()

    def test_missing_source_object_fails_validation(self):
        """Mapping without source_object should fail validation."""
        svc = self._get_service()
        mock_db = MagicMock()
        mapping = {
            "source_object": "",
            "source_field": "Name",
            "target_entity": "loan",
            "target_field": "borrower_name",
            "transform_type": "direct",
        }
        result = svc._validate_mapping(mock_db, mapping)
        assert not result["is_valid"]
        assert any("Source object" in e for e in result["errors"])

    def test_missing_target_field_fails_validation(self):
        """Mapping without target_field should fail validation."""
        svc = self._get_service()
        mock_db = MagicMock()
        mapping = {
            "source_object": "Lead",
            "source_field": "Name",
            "target_entity": "loan",
            "target_field": "",
            "transform_type": "direct",
        }
        result = svc._validate_mapping(mock_db, mapping)
        assert not result["is_valid"]
        assert any("Target field" in e for e in result["errors"])

    def test_required_field_without_default_warns(self):
        """Required field with non-direct transform and no default should warn."""
        svc = self._get_service()
        mock_db = MagicMock()
        mapping = {
            "source_object": "Lead",
            "source_field": "Status",
            "target_entity": "loan",
            "target_field": "stage",
            "transform_type": "stage_map",
            "transform_config": {"mappings": {}},
            "required": True,
            "default_value": None,
            "data_type": None,
        }
        result = svc._validate_mapping(mock_db, mapping)
        assert any("Required field" in w for w in result["warnings"])
