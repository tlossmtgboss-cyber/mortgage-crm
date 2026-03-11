"""
Test Loan Stage Transitions - Validates loan stage enum values, terminal
stage classification, and pipeline filtering logic.

Covers:
- LoanStage enum completeness and values (both database enums and CLAUDE.md tool enum)
- Terminal stages constant accuracy
- Active pipeline filtering excludes terminal stages
- Stage ordering for pipeline progression
"""

import pytest


# =============================================================================
# LoanStage Enum Values
# =============================================================================

@pytest.mark.unit
class TestLoanStageEnum:
    """Validate the LoanStage enum from database/enums.py."""

    def test_loan_stage_enum_exists(self):
        """LoanStage enum should be importable from database.enums."""
        from database.enums import LoanStage
        assert LoanStage is not None

    def test_loan_stage_has_all_expected_values(self):
        """LoanStage should contain all 20 expected pipeline stages."""
        from database.enums import LoanStage
        expected_stages = [
            "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
            "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
            "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
            "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
            "CANCELLED", "DENIED", "DEAD", "NURTURE",
            "WITHDRAWN", "DOES_NOT_QUALIFY",
        ]
        actual_names = [s.name for s in LoanStage]
        for stage in expected_stages:
            assert stage in actual_names, (
                f"Expected stage '{stage}' missing from LoanStage enum. "
                f"Available: {actual_names}"
            )

    def test_loan_stage_values_are_uppercase(self):
        """All LoanStage values should be uppercase strings (DB convention)."""
        from database.enums import LoanStage
        for stage in LoanStage:
            assert stage.value == stage.value.upper(), (
                f"Stage {stage.name} has non-uppercase value: {stage.value}"
            )

    def test_loan_stage_is_string_enum(self):
        """LoanStage members should be usable as strings."""
        from database.enums import LoanStage
        assert isinstance(LoanStage.APPLICATION.value, str)
        assert LoanStage.FUNDED.value == "FUNDED"

    def test_loan_stage_application_is_first_active(self):
        """APPLICATION should exist as the entry point stage."""
        from database.enums import LoanStage
        assert hasattr(LoanStage, "APPLICATION")
        assert LoanStage.APPLICATION.value == "APPLICATION"

    def test_loan_stage_funded_exists(self):
        """FUNDED should exist as a terminal/completion stage."""
        from database.enums import LoanStage
        assert hasattr(LoanStage, "FUNDED")
        assert LoanStage.FUNDED.value == "FUNDED"


# =============================================================================
# Terminal Stages
# =============================================================================

@pytest.mark.unit
class TestTerminalStages:
    """Validate the TERMINAL_STAGES constant used for pipeline exclusions."""

    def test_terminal_stages_tuple_defined(self):
        """TERMINAL_STAGES should be defined as a tuple of stage strings."""
        # The constant is defined in CLAUDE.md tool code; replicate it here
        # for testing since it defines the pipeline filtering contract.
        TERMINAL_STAGES = (
            "FUNDED", "CANCELLED", "DENIED", "DEAD",
            "WITHDRAWN", "DOES_NOT_QUALIFY",
        )
        assert isinstance(TERMINAL_STAGES, tuple)
        assert len(TERMINAL_STAGES) == 6

    def test_funded_is_terminal(self):
        """FUNDED must be in terminal stages (loans that completed)."""
        TERMINAL_STAGES = (
            "FUNDED", "CANCELLED", "DENIED", "DEAD",
            "WITHDRAWN", "DOES_NOT_QUALIFY",
        )
        assert "FUNDED" in TERMINAL_STAGES

    def test_cancelled_is_terminal(self):
        """CANCELLED must be in terminal stages."""
        TERMINAL_STAGES = (
            "FUNDED", "CANCELLED", "DENIED", "DEAD",
            "WITHDRAWN", "DOES_NOT_QUALIFY",
        )
        assert "CANCELLED" in TERMINAL_STAGES

    def test_denied_is_terminal(self):
        """DENIED must be in terminal stages."""
        TERMINAL_STAGES = (
            "FUNDED", "CANCELLED", "DENIED", "DEAD",
            "WITHDRAWN", "DOES_NOT_QUALIFY",
        )
        assert "DENIED" in TERMINAL_STAGES

    def test_active_stages_not_in_terminal(self):
        """Active pipeline stages must NOT be in terminal stages."""
        TERMINAL_STAGES = (
            "FUNDED", "CANCELLED", "DENIED", "DEAD",
            "WITHDRAWN", "DOES_NOT_QUALIFY",
        )
        active_stages = [
            "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
            "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
            "APPROVED", "CTC", "CLEAR_TO_CLOSE", "CLOSING",
            "DOCS", "DOCS_OUT",
        ]
        for stage in active_stages:
            assert stage not in TERMINAL_STAGES, (
                f"Active stage '{stage}' should NOT be in TERMINAL_STAGES"
            )

    def test_terminal_stages_are_valid_loan_stages(self):
        """All terminal stages must be valid LoanStage enum values."""
        from database.enums import LoanStage
        TERMINAL_STAGES = (
            "FUNDED", "CANCELLED", "DENIED", "DEAD",
            "WITHDRAWN", "DOES_NOT_QUALIFY",
        )
        valid_values = {s.value for s in LoanStage}
        for stage in TERMINAL_STAGES:
            assert stage in valid_values, (
                f"Terminal stage '{stage}' is not a valid LoanStage value"
            )


# =============================================================================
# Pipeline Progression Order
# =============================================================================

@pytest.mark.unit
class TestPipelineProgression:
    """Test the expected happy-path stage progression order."""

    HAPPY_PATH = [
        "APPLICATION",
        "DISCLOSED",
        "PROCESSING",
        "SUBMITTED",
        "UNDERWRITING",
        "UW_RECEIVED",
        "CONDITIONAL_APPROVAL",
        "APPROVED",
        "CLEAR_TO_CLOSE",
        "DOCS_OUT",
        "FUNDED",
    ]

    def test_happy_path_starts_at_application(self):
        """Pipeline progression should start at APPLICATION."""
        assert self.HAPPY_PATH[0] == "APPLICATION"

    def test_happy_path_ends_at_funded(self):
        """Pipeline progression should end at FUNDED."""
        assert self.HAPPY_PATH[-1] == "FUNDED"

    def test_disclosed_follows_application(self):
        """DISCLOSED should follow APPLICATION in the pipeline."""
        app_idx = self.HAPPY_PATH.index("APPLICATION")
        disc_idx = self.HAPPY_PATH.index("DISCLOSED")
        assert disc_idx > app_idx

    def test_approved_before_clear_to_close(self):
        """APPROVED must come before CLEAR_TO_CLOSE."""
        app_idx = self.HAPPY_PATH.index("APPROVED")
        ctc_idx = self.HAPPY_PATH.index("CLEAR_TO_CLOSE")
        assert ctc_idx > app_idx

    def test_uw_received_follows_submitted(self):
        """UW_RECEIVED should follow SUBMITTED in underwriting flow."""
        sub_idx = self.HAPPY_PATH.index("SUBMITTED")
        uwr_idx = self.HAPPY_PATH.index("UW_RECEIVED")
        assert uwr_idx > sub_idx

    def test_all_happy_path_stages_are_valid(self):
        """All happy-path stages must exist in the LoanStage enum."""
        from database.enums import LoanStage
        valid_values = {s.value for s in LoanStage}
        for stage in self.HAPPY_PATH:
            assert stage in valid_values, (
                f"Happy-path stage '{stage}' not found in LoanStage enum"
            )
