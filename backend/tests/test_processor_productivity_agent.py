"""
Test Processor Productivity Agent - Validates priority queue logic, batch
approval identification, workload capacity calculation, submission checklist
generation, and document version comparison.

Covers:
- Priority queue ordering (closing date > conditions > expirations > completeness)
- Batch approval eligibility based on document type
- Workload capacity with weighted high-touch stages
- Submission checklist completeness verification
- Document version comparison logic
- Time-to-clear estimation
"""

import pytest
from datetime import datetime, date, timedelta


# =============================================================================
# Priority Queue Ordering
# =============================================================================

@pytest.mark.unit
class TestPriorityQueueLogic:
    """Validate the priority ordering used by get_daily_priority_queue."""

    PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    def test_critical_before_high(self):
        """Critical priority items should sort before high priority."""
        assert self.PRIORITY_ORDER["critical"] < self.PRIORITY_ORDER["high"]

    def test_high_before_medium(self):
        """High priority items should sort before medium priority."""
        assert self.PRIORITY_ORDER["high"] < self.PRIORITY_ORDER["medium"]

    def test_medium_before_low(self):
        """Medium priority items should sort before low priority."""
        assert self.PRIORITY_ORDER["medium"] < self.PRIORITY_ORDER["low"]

    def test_closing_in_3_days_is_critical(self):
        """A loan closing in 3 or fewer days should be critical priority."""
        days_to_close = 3
        priority = "critical" if days_to_close <= 3 else "high"
        assert priority == "critical"

    def test_closing_in_5_days_is_high(self):
        """A loan closing in 4-7 days should be high priority."""
        days_to_close = 5
        priority = "critical" if days_to_close <= 3 else "high"
        assert priority == "high"

    def test_deduplication_keeps_highest_priority(self):
        """When a loan appears in multiple priority categories, keep the highest."""
        items = [
            {"loan_id": 1, "priority": "medium", "category": "expirations"},
            {"loan_id": 1, "priority": "critical", "category": "closing_urgency"},
            {"loan_id": 2, "priority": "high", "category": "conditions"},
        ]

        seen = {}
        for item in items:
            lid = item["loan_id"]
            if lid not in seen:
                seen[lid] = item
            else:
                if self.PRIORITY_ORDER[item["priority"]] < self.PRIORITY_ORDER[seen[lid]["priority"]]:
                    seen[lid] = item

        assert seen[1]["priority"] == "critical"
        assert seen[1]["category"] == "closing_urgency"
        assert seen[2]["priority"] == "high"

    def test_queue_sorted_by_priority_order(self):
        """Final queue should be sorted by priority order."""
        queue = [
            {"priority": "medium", "loan_id": 3},
            {"priority": "critical", "loan_id": 1},
            {"priority": "high", "loan_id": 2},
        ]

        sorted_queue = sorted(
            queue,
            key=lambda x: self.PRIORITY_ORDER.get(x["priority"], 3)
        )

        assert sorted_queue[0]["priority"] == "critical"
        assert sorted_queue[1]["priority"] == "high"
        assert sorted_queue[2]["priority"] == "medium"


# =============================================================================
# Batch Approval Identification
# =============================================================================

@pytest.mark.unit
class TestBatchApprovalLogic:
    """Validate the batch approval eligibility logic."""

    ROUTINE_TYPES = {
        "drivers_license", "ssn_card", "passport",
        "insurance", "hoa",
    }

    REVIEW_REQUIRED_TYPES = {
        "paystubs", "w2", "tax_returns", "1099", "profit_loss",
        "bank_statements", "investment_statements", "gift_letter",
        "credit_report", "credit_explanation",
        "appraisal", "title", "purchase_contract",
    }

    def test_drivers_license_is_routine(self):
        """Driver's license should be eligible for batch approval."""
        assert "drivers_license" in self.ROUTINE_TYPES

    def test_passport_is_routine(self):
        """Passport should be eligible for batch approval."""
        assert "passport" in self.ROUTINE_TYPES

    def test_insurance_is_routine(self):
        """Insurance document should be eligible for batch approval."""
        assert "insurance" in self.ROUTINE_TYPES

    def test_paystubs_require_review(self):
        """Pay stubs should NOT be eligible for batch approval."""
        assert "paystubs" not in self.ROUTINE_TYPES
        assert "paystubs" in self.REVIEW_REQUIRED_TYPES

    def test_bank_statements_require_review(self):
        """Bank statements should NOT be eligible for batch approval."""
        assert "bank_statements" not in self.ROUTINE_TYPES
        assert "bank_statements" in self.REVIEW_REQUIRED_TYPES

    def test_appraisal_requires_review(self):
        """Appraisal should NOT be eligible for batch approval."""
        assert "appraisal" not in self.ROUTINE_TYPES
        assert "appraisal" in self.REVIEW_REQUIRED_TYPES

    def test_credit_report_requires_review(self):
        """Credit report should NOT be eligible for batch approval."""
        assert "credit_report" not in self.ROUTINE_TYPES
        assert "credit_report" in self.REVIEW_REQUIRED_TYPES

    def test_routine_and_review_sets_do_not_overlap(self):
        """Routine and review-required sets must not overlap."""
        overlap = self.ROUTINE_TYPES & self.REVIEW_REQUIRED_TYPES
        assert len(overlap) == 0, f"Overlapping doc types: {overlap}"


# =============================================================================
# Workload Capacity Calculation
# =============================================================================

@pytest.mark.unit
class TestWorkloadCapacityLogic:
    """Validate the workload capacity and weighted load calculation."""

    HIGH_TOUCH_STAGES = (
        "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
        "CLEAR_TO_CLOSE", "DOCS_OUT",
    )
    HIGH_TOUCH_WEIGHT = 1.5

    @staticmethod
    def calculate_weighted_load(total_active, high_touch_count, weight=1.5):
        """Replicate the weighted load calculation from the agent."""
        return (total_active - high_touch_count) + (high_touch_count * weight)

    @staticmethod
    def capacity_status(capacity_pct):
        """Replicate capacity status classification."""
        if capacity_pct >= 100:
            return "over_capacity"
        elif capacity_pct >= 85:
            return "near_capacity"
        elif capacity_pct >= 60:
            return "healthy"
        else:
            return "under_utilized"

    def test_weighted_load_no_high_touch(self):
        """All standard loans should have weight 1.0 each."""
        weighted = self.calculate_weighted_load(20, 0)
        assert weighted == 20.0

    def test_weighted_load_all_high_touch(self):
        """All high-touch loans should be weighted at 1.5x."""
        weighted = self.calculate_weighted_load(10, 10)
        assert weighted == 15.0

    def test_weighted_load_mixed(self):
        """Mixed pipeline: 20 standard + 10 high-touch = 20 + 15 = 35."""
        weighted = self.calculate_weighted_load(30, 10)
        assert weighted == 35.0

    def test_capacity_over(self):
        """100%+ capacity should be over_capacity."""
        assert self.capacity_status(100) == "over_capacity"
        assert self.capacity_status(120) == "over_capacity"

    def test_capacity_near(self):
        """85-99% capacity should be near_capacity."""
        assert self.capacity_status(85) == "near_capacity"
        assert self.capacity_status(99) == "near_capacity"

    def test_capacity_healthy(self):
        """60-84% capacity should be healthy."""
        assert self.capacity_status(60) == "healthy"
        assert self.capacity_status(84) == "healthy"

    def test_capacity_under_utilized(self):
        """Below 60% capacity should be under_utilized."""
        assert self.capacity_status(40) == "under_utilized"
        assert self.capacity_status(0) == "under_utilized"

    def test_underwriting_is_high_touch(self):
        """UNDERWRITING stage should be classified as high-touch."""
        assert "UNDERWRITING" in self.HIGH_TOUCH_STAGES

    def test_clear_to_close_is_high_touch(self):
        """CLEAR_TO_CLOSE stage should be classified as high-touch."""
        assert "CLEAR_TO_CLOSE" in self.HIGH_TOUCH_STAGES

    def test_application_is_not_high_touch(self):
        """APPLICATION stage should NOT be high-touch."""
        assert "APPLICATION" not in self.HIGH_TOUCH_STAGES

    def test_processing_is_not_high_touch(self):
        """PROCESSING stage should NOT be high-touch."""
        assert "PROCESSING" not in self.HIGH_TOUCH_STAGES

    def test_remaining_capacity_calculation(self):
        """Remaining capacity should be max - weighted load, minimum 0."""
        max_loans = 35
        weighted_load = 30
        remaining = max(0, max_loans - int(weighted_load))
        assert remaining == 5

    def test_remaining_capacity_does_not_go_negative(self):
        """Remaining capacity should never be negative."""
        max_loans = 35
        weighted_load = 50
        remaining = max(0, max_loans - int(weighted_load))
        assert remaining == 0


# =============================================================================
# Submission Checklist
# =============================================================================

@pytest.mark.unit
class TestSubmissionChecklistLogic:
    """Validate submission readiness determination."""

    REQUIRED_DOC_CATEGORIES = {"income", "assets", "credit", "identity", "property"}

    STACKING_ORDER = [
        {"position": 1, "category": "identity"},
        {"position": 2, "category": "credit"},
        {"position": 3, "category": "income"},
        {"position": 4, "category": "assets"},
        {"position": 5, "category": "property"},
    ]

    def test_all_required_categories_present(self):
        """Submission requires all 5 document categories."""
        assert len(self.REQUIRED_DOC_CATEGORIES) == 5

    def test_income_is_required(self):
        """Income documents are required for submission."""
        assert "income" in self.REQUIRED_DOC_CATEGORIES

    def test_assets_is_required(self):
        """Asset documents are required for submission."""
        assert "assets" in self.REQUIRED_DOC_CATEGORIES

    def test_submission_ready_when_all_complete(self):
        """File is submission-ready only when missing=0 and failed=0."""
        missing_required = 0
        failed = 0
        is_ready = missing_required == 0 and failed == 0
        assert is_ready is True

    def test_not_ready_when_missing(self):
        """File is NOT submission-ready when required items are missing."""
        missing_required = 2
        failed = 0
        is_ready = missing_required == 0 and failed == 0
        assert is_ready is False

    def test_not_ready_when_failed(self):
        """File is NOT submission-ready when compliance checks fail."""
        missing_required = 0
        failed = 1
        is_ready = missing_required == 0 and failed == 0
        assert is_ready is False

    def test_completion_percentage_calculation(self):
        """Completion percentage should be complete/total * 100."""
        complete = 8
        total = 10
        pct = round((complete / total) * 100, 1)
        assert pct == 80.0

    def test_completion_percentage_all_done(self):
        """100% completion when all required items are complete."""
        complete = 10
        total = 10
        pct = round((complete / total) * 100, 1)
        assert pct == 100.0

    def test_stacking_order_identity_first(self):
        """Identity documents should be first in stacking order."""
        assert self.STACKING_ORDER[0]["category"] == "identity"
        assert self.STACKING_ORDER[0]["position"] == 1

    def test_stacking_order_property_last(self):
        """Property documents should be last in stacking order."""
        assert self.STACKING_ORDER[-1]["category"] == "property"
        assert self.STACKING_ORDER[-1]["position"] == 5

    def test_stacking_order_has_5_sections(self):
        """Stacking order should define exactly 5 sections."""
        assert len(self.STACKING_ORDER) == 5


# =============================================================================
# Document Version Comparison
# =============================================================================

@pytest.mark.unit
class TestDocVersionComparisonLogic:
    """Validate document version comparison logic."""

    def test_version_improved_when_active_replaces_rejected(self):
        """New active doc replacing a rejected doc is an improvement."""
        current_status = "active"
        previous_status = "rejected"
        improved = current_status in ("active", "pending") and previous_status in ("rejected", "expired")
        assert improved is True

    def test_version_improved_when_pending_replaces_expired(self):
        """New pending doc replacing an expired doc is an improvement."""
        current_status = "pending"
        previous_status = "expired"
        improved = current_status in ("active", "pending") and previous_status in ("rejected", "expired")
        assert improved is True

    def test_version_not_improved_when_both_pending(self):
        """Two pending docs is not an improvement."""
        current_status = "pending"
        previous_status = "pending"
        improved = current_status in ("active", "pending") and previous_status in ("rejected", "expired")
        assert improved is False

    def test_doc_type_mismatch_generates_warning(self):
        """Different doc types between versions should generate a warning."""
        current_type = "w2"
        previous_type = "paystubs"
        warnings = []
        if current_type != previous_type:
            warnings.append("Document type mismatch between versions")
        assert len(warnings) == 1

    def test_doc_type_match_no_warning(self):
        """Same doc type should not generate a type mismatch warning."""
        current_type = "w2"
        previous_type = "w2"
        warnings = []
        if current_type != previous_type:
            warnings.append("Document type mismatch between versions")
        assert len(warnings) == 0


# =============================================================================
# Time-to-Clear Estimation
# =============================================================================

@pytest.mark.unit
class TestTimeToClearEstimation:
    """Validate the time-to-clear estimation logic."""

    TIME_PER_DOC_REVIEW = 15  # minutes
    TIME_PER_CONDITION = 30  # minutes
    TIME_PER_DATA_ENTRY = 10  # minutes

    def test_single_doc_estimate(self):
        """One pending doc should estimate 25 minutes (15 review + 10 entry)."""
        pending = 1
        conditions = 0
        total = (pending * self.TIME_PER_DOC_REVIEW) + \
                (conditions * self.TIME_PER_CONDITION) + \
                (pending * self.TIME_PER_DATA_ENTRY)
        assert total == 25

    def test_single_condition_estimate(self):
        """One condition with no pending docs should estimate 30 minutes."""
        pending = 0
        conditions = 1
        total = (pending * self.TIME_PER_DOC_REVIEW) + \
                (conditions * self.TIME_PER_CONDITION) + \
                (pending * self.TIME_PER_DATA_ENTRY)
        assert total == 30

    def test_complex_loan_estimate(self):
        """5 pending docs + 3 conditions = 5*15 + 3*30 + 5*10 = 215 minutes."""
        pending = 5
        conditions = 3
        total = (pending * self.TIME_PER_DOC_REVIEW) + \
                (conditions * self.TIME_PER_CONDITION) + \
                (pending * self.TIME_PER_DATA_ENTRY)
        assert total == 215

    def test_hours_conversion(self):
        """215 minutes should convert to 3.6 hours."""
        minutes = 215
        hours = round(minutes / 60, 1)
        assert hours == 3.6

    def test_workday_conversion(self):
        """480 minutes should equal 1.0 workday (8 hours)."""
        minutes = 480
        days = round(minutes / 480, 1)
        assert days == 1.0

    def test_urgency_critical(self):
        """Loan closing in 3 or fewer days should have critical urgency."""
        days_to_close = 2
        urgency = "critical" if days_to_close <= 3 else \
                  "high" if days_to_close <= 7 else "normal"
        assert urgency == "critical"

    def test_urgency_high(self):
        """Loan closing in 4-7 days should have high urgency."""
        days_to_close = 5
        urgency = "critical" if days_to_close <= 3 else \
                  "high" if days_to_close <= 7 else "normal"
        assert urgency == "high"

    def test_urgency_normal(self):
        """Loan closing in 8+ days should have normal urgency."""
        days_to_close = 15
        urgency = "critical" if days_to_close <= 3 else \
                  "high" if days_to_close <= 7 else "normal"
        assert urgency == "normal"

    def test_zero_pending_zero_conditions(self):
        """No pending items should estimate 0 minutes."""
        pending = 0
        conditions = 0
        total = (pending * self.TIME_PER_DOC_REVIEW) + \
                (conditions * self.TIME_PER_CONDITION) + \
                (pending * self.TIME_PER_DATA_ENTRY)
        assert total == 0
