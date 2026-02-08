#!/usr/bin/env python3
"""
Test harness for Salesforce Integration Validator.
Uses mock clients to demonstrate the validation flow with sample data.

Run: python tests/test_validation_dry_run.py
"""

import json
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from run_validation import (
    FIELD_MAPPINGS,
    ByteMappingValidator,
    DataPushValidator,
    FieldExistenceValidator,
    ReportGenerator,
    SLAWorkflowValidator,
    ValidationReport,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Mock Clients
# ---------------------------------------------------------------------------


class MockSalesforceClient:
    """Simulated Salesforce responses for testing."""

    def __init__(self):
        # Simulate field metadata for all mapped fields
        self._field_metadata = {}
        for m in FIELD_MAPPINGS:
            obj = m["sf_object"]
            field = m["sf_field"]
            if obj not in self._field_metadata:
                self._field_metadata[obj] = {}
            self._field_metadata[obj][field] = {
                "name": field,
                "type": m["sf_type"],
                "updateable": True,
                "label": field.replace("_", " ").replace("__c", ""),
            }

        # Simulate one field that was deleted (to test failure detection)
        # Remove Appraisal_Ordered_Date__c to simulate a deleted field
        if "Loan__c" in self._field_metadata:
            del self._field_metadata["Loan__c"]["Appraisal_Ordered_Date__c"]

        # Simulate records in Salesforce
        self._records = self._generate_mock_sf_records()

        # Simulate workflow metadata
        self._active_workflows = {
            "Initial_Doc_Review": True,
            "TRID_Compliance_Check": True,
            "Disclosure_Escalation": True,
            "Appraisal_Followup": False,  # Inactive — should trigger failure
            "Appraisal_Review": True,
            "Title_Followup": True,
            "Title_Review": True,
            "UW_Followup": True,
            "Condition_Followup": True,
            "Clear_To_Close_Prep": True,
            "Closing_Package": True,
            "Pre_Closing_Verification": True,
            "Doc_Tracking_Confirmation": True,
            "Post_Closing_Audit": True,
            "Re_Engagement": True,
            "Followup_Reminder": True,
            "Preapproval_Renewal": True,
            "Rate_Lock_Extension": True,
        }

    def _generate_mock_sf_records(self) -> dict:
        """Generate mock Salesforce records with realistic data."""
        records = {}
        base_date = datetime.now(timezone.utc) - timedelta(days=5)

        for i in range(50):
            sf_id = f"a0X{i:012d}"
            loan_date = base_date + timedelta(hours=i * 3)

            record = {
                "Id": sf_id,
                "Application_Received_Date__c": (
                    loan_date.strftime("%Y-%m-%d")
                ),
                "Disclosure_Sent_Date__c": (
                    (loan_date + timedelta(days=1)).strftime("%Y-%m-%d")
                ),
                "Disclosure_Ack_Date__c": (
                    (loan_date + timedelta(days=3)).strftime("%Y-%m-%d")
                    if i % 3 != 0
                    else None
                ),
                "Appraisal_Ordered_Date__c": (
                    (loan_date + timedelta(days=2)).strftime("%Y-%m-%d")
                ),
                "Appraisal_Received_Date__c": (
                    (loan_date + timedelta(days=7)).strftime("%Y-%m-%d")
                    if i % 4 != 0
                    else None
                ),
                "Title_Ordered_Date__c": (
                    (loan_date + timedelta(days=2)).strftime("%Y-%m-%d")
                ),
                "Title_Received_Date__c": (
                    (loan_date + timedelta(days=5)).strftime("%Y-%m-%d")
                    if i % 5 != 0
                    else None
                ),
                "Submitted_To_UW_Date__c": (
                    (loan_date + timedelta(days=3)).strftime("%Y-%m-%d")
                ),
                "Conditions_Sent_Date__c": (
                    (loan_date + timedelta(days=8)).strftime("%Y-%m-%d")
                    if i > 10
                    else None
                ),
                "Conditions_Cleared_Date__c": (
                    (loan_date + timedelta(days=12)).strftime("%Y-%m-%d")
                    if i > 20
                    else None
                ),
                "Clear_To_Close_Date__c": (
                    (loan_date + timedelta(days=13)).strftime("%Y-%m-%d")
                    if i > 25
                    else None  # Missing for record 25 — will trigger FAIL
                ),
                "Closing_Scheduled_Date__c": (
                    (loan_date + timedelta(days=15)).isoformat()
                    if i > 30
                    else None
                ),
                "Docs_Out_Date__c": (
                    (loan_date + timedelta(days=14)).strftime("%Y-%m-%d")
                    if i > 30
                    else None
                ),
                "Funded_Date__c": (
                    (loan_date + timedelta(days=16)).strftime("%Y-%m-%d")
                    if i > 40
                    else None
                ),
                "Loan_Amount__c": 350000.00 + (i * 5000),
                "Interest_Rate__c": 6.25 + (i * 0.05),
                "Loan_Status__c": "Processing",
                "Loan_Type__c": "Conventional",
            }

            # Inject some deliberate errors for testing
            if i == 7:
                # Timezone shift: date off by 1 day
                record["Disclosure_Sent_Date__c"] = (
                    (loan_date + timedelta(days=0)).strftime("%Y-%m-%d")
                )
            if i == 15:
                # Null placeholder instead of actual null
                record["Clear_To_Close_Date__c"] = "1970-01-01"
            if i == 22:
                # Value mismatch
                record["Submitted_To_UW_Date__c"] = "2020-01-01"

            records[sf_id] = record

        return records

    def connect(self):
        pass  # Mock — no real connection needed

    def describe_field(self, object_name: str, field_name: str):
        obj_fields = self._field_metadata.get(object_name, {})
        return obj_fields.get(field_name)

    def get_record(self, object_name: str, record_id: str):
        return self._records.get(record_id)

    def check_workflow_active(self, workflow_name: str) -> bool:
        return self._active_workflows.get(workflow_name, False)

    def check_workflow_references_field(
        self, workflow_name: str, field_name: str
    ) -> bool:
        # Assume all active workflows reference their field correctly
        return self._active_workflows.get(workflow_name, False)

    def get_recent_tasks_by_type(
        self, task_type: str, days_back: int = 7
    ) -> list:
        # Return some mock tasks for most types
        if task_type in ("Follow-up", "Appraisal Review"):
            return []  # No tasks — will trigger warning
        return [
            {"id": f"task_{i}", "type": task_type, "assigned_to": "Processor_Queue"}
            for i in range(3)
        ]


class MockPerenniaClient:
    """Simulated Perennia AI data for testing."""

    def __init__(self):
        self._records = self._generate_mock_records()

    def _generate_mock_records(self) -> list:
        records = []
        base_date = datetime.now(timezone.utc) - timedelta(days=5)

        for i in range(50):
            loan_date = base_date + timedelta(hours=i * 3)
            record = {
                "id": f"loan_{i:06d}",
                "salesforce_id": f"a0X{i:012d}",
                "application_received_at": loan_date.isoformat(),
                "disclosure_sent_at": (
                    loan_date + timedelta(days=1)
                ).isoformat(),
                "disclosure_acknowledged_at": (
                    (loan_date + timedelta(days=3)).isoformat()
                    if i % 3 != 0
                    else None
                ),
                "appraisal_ordered_at": (
                    loan_date + timedelta(days=2)
                ).isoformat(),
                "appraisal_received_at": (
                    (loan_date + timedelta(days=7)).isoformat()
                    if i % 4 != 0
                    else None
                ),
                "title_ordered_at": (
                    loan_date + timedelta(days=2)
                ).isoformat(),
                "title_received_at": (
                    (loan_date + timedelta(days=5)).isoformat()
                    if i % 5 != 0
                    else None
                ),
                "submitted_to_uw_at": (
                    loan_date + timedelta(days=3)
                ).isoformat(),
                "conditions_sent_at": (
                    (loan_date + timedelta(days=8)).isoformat()
                    if i > 10
                    else None
                ),
                "conditions_cleared_at": (
                    (loan_date + timedelta(days=12)).isoformat()
                    if i > 20
                    else None
                ),
                "clear_to_close_at": (
                    (loan_date + timedelta(days=13)).isoformat()
                    if i > 24  # Source has value for record 25 but SF is null
                    else None
                ),
                "closing_scheduled_at": (
                    (loan_date + timedelta(days=15)).isoformat()
                    if i > 30
                    else None
                ),
                "docs_out_at": (
                    (loan_date + timedelta(days=14)).isoformat()
                    if i > 30
                    else None
                ),
                "funded_at": (
                    (loan_date + timedelta(days=16)).isoformat()
                    if i > 40
                    else None
                ),
                "loan_amount": (35000000 + i * 500000),  # In cents
                "interest_rate": 0.0625 + (i * 0.0005),
                "loan_status": "processing",
                "loan_type": "Conventional",
                "byte_mappings": {},
            }

            # Generate byte mappings for date fields
            for field in [
                "application_received_at",
                "disclosure_sent_at",
                "appraisal_ordered_at",
                "submitted_to_uw_at",
            ]:
                val = record.get(field)
                if val:
                    dt = datetime.fromisoformat(val)
                    epoch = int(dt.timestamp())
                    record["byte_mappings"][field] = epoch

            records.append(record)

        return records

    def get_recent_loans(self, limit: int = 50, since=None) -> list:
        return self._records[:limit]

    def get_records_with_byte_mappings(self, limit: int = 50) -> list:
        return self._records[:limit]


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------


def run_dry_run_test():
    """Execute a full validation dry run with mock data."""
    print("=" * 70)
    print("SALESFORCE INTEGRATION VALIDATOR — DRY RUN TEST")
    print("=" * 70)
    print()

    sf_client = MockSalesforceClient()
    perennia_client = MockPerenniaClient()

    report = ValidationReport(
        mode="dry-run-test",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    # ── Test 1: Field Existence ──
    print("▸ Step 1: Validating field existence...")
    validator = FieldExistenceValidator(sf_client, FIELD_MAPPINGS)
    results = validator.validate()
    for r in results:
        report.add_result(r)

    field_fails = [r for r in results if r.status == "FAIL"]
    print(f"  ✓ {len(results)} fields checked, {len(field_fails)} failures")
    for f in field_fails:
        print(
            f"    ✗ {f.details['sf_object']}.{f.details['sf_field']}: "
            f"{f.details.get('error', 'Unknown')}"
        )
    print()

    # ── Test 2: Data Push Completeness ──
    print("▸ Step 2: Validating data push completeness...")
    validator = DataPushValidator(
        sf_client, perennia_client, FIELD_MAPPINGS, sample_size=20
    )
    results = validator.validate()
    for r in results:
        report.add_result(r)

    push_fails = [r for r in results if r.status == "FAIL"]
    print(f"  ✓ {len(results)} field-record checks, {len(push_fails)} failures")
    for f in push_fails[:5]:
        print(
            f"    ✗ {f.details.get('sf_field', 'N/A')} on "
            f"{f.details.get('record_id', 'N/A')}: "
            f"{f.details.get('error_type', 'Unknown')}"
        )
    if len(push_fails) > 5:
        print(f"    ... and {len(push_fails) - 5} more")
    print()

    # ── Test 3: Byte Mapping Accuracy ──
    print("▸ Step 3: Validating byte mapping accuracy...")
    validator = ByteMappingValidator(
        sf_client, perennia_client, FIELD_MAPPINGS, strict=True, sample_size=20
    )
    results = validator.validate()
    for r in results:
        report.add_result(r)

    byte_fails = [r for r in results if r.status == "FAIL"]
    byte_warns = [r for r in results if r.status == "WARNING"]
    print(
        f"  ✓ {len(results)} byte-mapped fields checked, "
        f"{len(byte_fails)} failures, {len(byte_warns)} warnings"
    )
    for f in byte_fails + byte_warns:
        d = f.details
        print(
            f"    {'✗' if f.status == 'FAIL' else '⚠'} {d['sf_field']}: "
            f"exact={d.get('exact_match', 0)}, "
            f"tz_adj={d.get('timezone_adjusted_match', 0)}, "
            f"mismatch={d.get('mismatch', 0)}"
        )
    print()

    # ── Test 4: SLA Workflow Chains ──
    print("▸ Step 4: Validating SLA workflow chains...")
    validator = SLAWorkflowValidator(sf_client, FIELD_MAPPINGS)
    results = validator.validate()
    for r in results:
        report.add_result(r)

    wf_fails = [r for r in results if r.status == "FAIL"]
    wf_warns = [r for r in results if r.status == "WARNING"]
    print(
        f"  ✓ {len(results)} SLA workflows checked, "
        f"{len(wf_fails)} failures, {len(wf_warns)} warnings"
    )
    for f in wf_fails:
        print(
            f"    ✗ {f.details['sf_field']}: "
            f"{f.details.get('error', 'Unknown')}"
        )
    print()

    # ── Finalize Report ──
    report.finalize()

    print("=" * 70)
    print(f"HEALTH SCORE: {report.health_score:.1f} ({report._health_status()})")
    print(
        f"SUMMARY: {report.summary['passed']} passed, "
        f"{report.summary['failed']} failed, "
        f"{report.summary['warnings']} warnings"
    )
    print("=" * 70)
    print()

    # Generate reports
    output_dir = Path(__file__).parent.parent / "reports"
    generator = ReportGenerator(str(output_dir))
    generator.generate(report, formats=["json", "html"])

    # Print critical issues
    critical = report._critical_issues()
    if critical:
        print(f"\n🔴 CRITICAL ISSUES ({len(critical)}):")
        for issue in critical:
            print(
                f"  • {issue['check_name']}: "
                f"{issue['details'].get('error', issue['details'].get('error_type', 'Unknown'))}"
            )

    print(f"\nReports saved to: {output_dir}")
    return report


if __name__ == "__main__":
    report = run_dry_run_test()
    sys.exit(0 if report.health_score >= 85 else 1)
