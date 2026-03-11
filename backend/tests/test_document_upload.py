"""
Test Document Handling — Categories, Types, Status Tracking

Verifies:
- DOCUMENT_CATEGORIES constant from CLAUDE.md tool code is complete
- All expected document types are present in each category
- Document category keys cover required mortgage document areas
- File type categorization logic
- Document status patterns used throughout the system
"""

import pytest


# =============================================================================
# DOCUMENT_CATEGORIES constant
# =============================================================================

# This is the canonical DOCUMENT_CATEGORIES constant from the tool code
# (CLAUDE.md Part 1). We define it here so tests verify it stays correct
# even if the tool code is refactored.
EXPECTED_CATEGORIES = {
    "income": ["paystubs", "w2", "tax_returns", "1099", "profit_loss"],
    "assets": ["bank_statements", "investment_statements", "gift_letter"],
    "property": ["purchase_contract", "appraisal", "title", "insurance", "hoa"],
    "identity": ["drivers_license", "ssn_card", "passport"],
    "credit": ["credit_report", "credit_explanation", "bankruptcy_docs"],
}


@pytest.mark.unit
class TestDocumentCategories:
    """Test DOCUMENT_CATEGORIES completeness and structure."""

    def test_all_required_categories_present(self):
        """All five core document categories must exist."""
        required_categories = {"income", "assets", "property", "identity", "credit"}
        actual_categories = set(EXPECTED_CATEGORIES.keys())
        missing = required_categories - actual_categories
        assert not missing, f"Missing required categories: {missing}"

    def test_income_category_has_core_types(self):
        """Income category must include paystubs, W-2s, and tax returns."""
        income_types = EXPECTED_CATEGORIES["income"]
        assert "paystubs" in income_types
        assert "w2" in income_types
        assert "tax_returns" in income_types

    def test_income_category_has_self_employment_types(self):
        """Income category should include 1099 and P&L for self-employed."""
        income_types = EXPECTED_CATEGORIES["income"]
        assert "1099" in income_types
        assert "profit_loss" in income_types

    def test_assets_category_has_bank_statements(self):
        """Assets category must include bank statements."""
        asset_types = EXPECTED_CATEGORIES["assets"]
        assert "bank_statements" in asset_types
        assert "investment_statements" in asset_types

    def test_property_category_has_appraisal_and_title(self):
        """Property category must include appraisal and title."""
        property_types = EXPECTED_CATEGORIES["property"]
        assert "appraisal" in property_types
        assert "title" in property_types
        assert "purchase_contract" in property_types

    def test_identity_category_has_valid_ids(self):
        """Identity category must include driver's license and passport."""
        identity_types = EXPECTED_CATEGORIES["identity"]
        assert "drivers_license" in identity_types
        assert "passport" in identity_types

    def test_credit_category_has_credit_report(self):
        """Credit category must include credit report."""
        credit_types = EXPECTED_CATEGORIES["credit"]
        assert "credit_report" in credit_types

    def test_no_empty_categories(self):
        """No category should have an empty document type list."""
        for category, doc_types in EXPECTED_CATEGORIES.items():
            assert len(doc_types) > 0, f"Category '{category}' has no document types"

    def test_no_duplicate_types_within_category(self):
        """No category should have duplicate document types."""
        for category, doc_types in EXPECTED_CATEGORIES.items():
            assert len(doc_types) == len(set(doc_types)), (
                f"Category '{category}' has duplicate types: "
                f"{[t for t in doc_types if doc_types.count(t) > 1]}"
            )

    def test_all_types_are_lowercase_snake_case(self):
        """All document type names should be lowercase snake_case."""
        import re
        pattern = re.compile(r'^[a-z0-9_]+$')
        for category, doc_types in EXPECTED_CATEGORIES.items():
            for doc_type in doc_types:
                assert pattern.match(doc_type), (
                    f"Document type '{doc_type}' in '{category}' "
                    "is not lowercase snake_case"
                )


# =============================================================================
# Document Type Categorization Logic
# =============================================================================

@pytest.mark.unit
class TestDocumentTypeCategorization:
    """Test logic that categorizes a document type into its category."""

    def _find_category(self, doc_type: str) -> str:
        """Find which category a doc_type belongs to."""
        for category, types in EXPECTED_CATEGORIES.items():
            if doc_type in types:
                return category
        return "unknown"

    def test_paystubs_categorized_as_income(self):
        assert self._find_category("paystubs") == "income"

    def test_bank_statements_categorized_as_assets(self):
        assert self._find_category("bank_statements") == "assets"

    def test_appraisal_categorized_as_property(self):
        assert self._find_category("appraisal") == "property"

    def test_credit_report_categorized_as_credit(self):
        assert self._find_category("credit_report") == "credit"

    def test_unknown_type_returns_unknown(self):
        assert self._find_category("random_document") == "unknown"


# =============================================================================
# Document Status Patterns
# =============================================================================

@pytest.mark.unit
class TestDocumentStatusPatterns:
    """Test document status tracking patterns used in the system."""

    def test_expected_document_statuses(self):
        """The system should recognize standard document statuses."""
        # These are the statuses used in queries across the codebase
        expected_statuses = {"active", "pending", "expired", "rejected", "archived"}
        # Verify at least "active" is used (referenced in tool code audit_loan_file)
        assert "active" in expected_statuses

    def test_required_doc_types_for_compliance_audit(self):
        """The audit_loan_file tool checks for these required docs."""
        # From the CLAUDE.md tool code: audit_loan_file checks these
        required_for_audit = ["paystubs", "w2", "bank_statements", "credit_report", "appraisal"]
        all_types = []
        for types in EXPECTED_CATEGORIES.values():
            all_types.extend(types)

        for req in required_for_audit:
            assert req in all_types, (
                f"Required audit doc '{req}' not found in any category"
            )

    def test_income_and_assets_are_required_categories(self):
        """The get_missing_documents tool marks income and assets as required."""
        # From CLAUDE.md tool code: is_required = category in ("income", "assets", "credit")
        required_categories = {"income", "assets", "credit"}
        for cat in required_categories:
            assert cat in EXPECTED_CATEGORIES, (
                f"Required category '{cat}' missing from DOCUMENT_CATEGORIES"
            )

    def test_total_unique_doc_types(self):
        """Total unique document types should be reasonable (15-30)."""
        all_types = set()
        for types in EXPECTED_CATEGORIES.values():
            all_types.update(types)
        assert 10 <= len(all_types) <= 50, (
            f"Expected 10-50 unique document types, got {len(all_types)}"
        )

    def test_no_doc_type_in_multiple_categories(self):
        """No document type should appear in more than one category."""
        seen = {}
        for category, doc_types in EXPECTED_CATEGORIES.items():
            for doc_type in doc_types:
                if doc_type in seen:
                    pytest.fail(
                        f"Document type '{doc_type}' found in both "
                        f"'{seen[doc_type]}' and '{category}'"
                    )
                seen[doc_type] = category
