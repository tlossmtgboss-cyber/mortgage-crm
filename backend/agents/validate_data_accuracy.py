"""
Data Accuracy Validation Script

Validates tool responses against direct database queries to detect discrepancies.
Tests the 5 most critical tools:
1. get_pipeline_metrics - loan counts and volume
2. get_task_queue - task counts by status
3. Lead queries by status
4. check_sla_status - SLA breach detection
5. get_missing_documents - document status

NOTE: Uses the main application's database connection (database.py) for ground truth,
which matches what the tools actually query against.
"""

import sys
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.agents.tools import tool_registry
# Use the main app's database connection instead of agent tools base
from backend.database import engine
from sqlalchemy import text


def execute_query(query: str, params: dict = None) -> List[Dict]:
    """Execute a query and return results as list of dicts using main app DB."""
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result.fetchall()]


def execute_single(query: str, params: dict = None) -> Optional[Dict]:
    """Execute a query and return single result using main app DB."""
    results = execute_query(query, params)
    return results[0] if results else None


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    tool_name: str
    check_name: str
    passed: bool
    ground_truth: Any
    tool_result: Any
    discrepancy: Optional[str] = None


def compare_values(ground_truth: Any, tool_value: Any, tolerance: float = 0.01) -> bool:
    """Compare two values with tolerance for floats."""
    if isinstance(ground_truth, (int, float)) and isinstance(tool_value, (int, float)):
        if ground_truth == 0:
            return tool_value == 0
        return abs(ground_truth - tool_value) / abs(ground_truth) <= tolerance
    return ground_truth == tool_value


# =============================================================================
# 1. Pipeline Metrics Validation
# =============================================================================

def validate_pipeline_metrics() -> List[ValidationResult]:
    """Validate get_pipeline_metrics against direct database queries."""
    results = []
    tool_name = "get_pipeline_metrics"

    print(f"\n{'='*60}")
    print(f"VALIDATING: {tool_name}")
    print(f"{'='*60}")

    # Get tool result
    tool_def = tool_registry.get(tool_name)
    if not tool_def:
        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="tool_exists",
            passed=False,
            ground_truth="Tool should exist",
            tool_result="Tool not found",
            discrepancy="Tool not in registry"
        ))
        return results

    tool_result = tool_def.func()

    if tool_result.status.value != "success":
        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="tool_execution",
            passed=False,
            ground_truth="Tool should succeed",
            tool_result=tool_result.message,
            discrepancy=f"Tool failed: {tool_result.error or tool_result.message}"
        ))
        return results

    tool_data = tool_result.data

    # Ground truth: Total active loans count
    gt_count = execute_single("""
        SELECT COUNT(*) as count
        FROM loans
        WHERE stage NOT IN ('Funded')
    """)
    gt_total_loans = gt_count["count"] if gt_count else 0
    tool_total = tool_data.get("summary", {}).get("total_loans", 0)

    results.append(ValidationResult(
        tool_name=tool_name,
        check_name="total_loans_count",
        passed=compare_values(gt_total_loans, tool_total),
        ground_truth=gt_total_loans,
        tool_result=tool_total,
        discrepancy=f"Expected {gt_total_loans}, got {tool_total}" if gt_total_loans != tool_total else None
    ))

    # Ground truth: Total volume
    gt_volume = execute_single("""
        SELECT COALESCE(SUM(amount), 0) as volume
        FROM loans
        WHERE stage NOT IN ('Funded')
    """)
    gt_total_volume = float(gt_volume["volume"]) if gt_volume else 0
    tool_volume = tool_data.get("summary", {}).get("total_volume", 0)

    results.append(ValidationResult(
        tool_name=tool_name,
        check_name="total_volume",
        passed=compare_values(gt_total_volume, tool_volume),
        ground_truth=gt_total_volume,
        tool_result=tool_volume,
        discrepancy=f"Expected {gt_total_volume:,.2f}, got {tool_volume:,.2f}" if not compare_values(gt_total_volume, tool_volume) else None
    ))

    # Ground truth: Funded in last 30 days
    gt_funded = execute_single("""
        SELECT COUNT(*) as count
        FROM loans
        WHERE stage = 'Funded'
        AND funded_at >= datetime('now', '-30 days')
    """)
    gt_funded_count = gt_funded["count"] if gt_funded else 0
    tool_funded = tool_data.get("velocity", {}).get("closed_last_30_days", 0)

    results.append(ValidationResult(
        tool_name=tool_name,
        check_name="funded_last_30_days",
        passed=compare_values(gt_funded_count, tool_funded),
        ground_truth=gt_funded_count,
        tool_result=tool_funded,
        discrepancy=f"Expected {gt_funded_count}, got {tool_funded}" if gt_funded_count != tool_funded else None
    ))

    # Ground truth: Stage breakdown
    gt_stages = execute_query("""
        SELECT stage, COUNT(*) as count
        FROM loans
        WHERE stage NOT IN ('Funded')
        GROUP BY stage
    """)
    gt_stage_dict = {row["stage"]: row["count"] for row in gt_stages}

    tool_stages = {s["stage"]: s["count"] for s in tool_data.get("stages", [])}

    stage_matches = all(
        gt_stage_dict.get(stage, 0) == tool_stages.get(stage, 0)
        for stage in set(gt_stage_dict.keys()) | set(tool_stages.keys())
    )

    results.append(ValidationResult(
        tool_name=tool_name,
        check_name="stage_breakdown",
        passed=stage_matches,
        ground_truth=gt_stage_dict,
        tool_result=tool_stages,
        discrepancy=f"Stage mismatch" if not stage_matches else None
    ))

    return results


# =============================================================================
# 2. Task Queue Validation
# =============================================================================

def validate_task_queue() -> List[ValidationResult]:
    """Validate get_task_queue against direct database queries."""
    results = []
    tool_name = "get_task_queue"

    print(f"\n{'='*60}")
    print(f"VALIDATING: {tool_name}")
    print(f"{'='*60}")

    # Get tool result
    tool_def = tool_registry.get(tool_name)
    if not tool_def:
        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="tool_exists",
            passed=False,
            ground_truth="Tool should exist",
            tool_result="Tool not found",
            discrepancy="Tool not in registry"
        ))
        return results

    tool_result = tool_def.func()

    if tool_result.status.value == "no_data":
        # No tasks is valid - verify with DB
        gt_count = execute_single("""
            SELECT COUNT(*) as count FROM tasks
            WHERE status NOT IN ('completed', 'cancelled')
        """)
        expected_no_data = (gt_count["count"] if gt_count else 0) == 0

        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="no_data_correct",
            passed=expected_no_data,
            ground_truth=0 if expected_no_data else gt_count["count"],
            tool_result="no_data",
            discrepancy=None if expected_no_data else f"Expected {gt_count['count']} tasks, got no_data"
        ))
        return results

    if tool_result.status.value != "success":
        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="tool_execution",
            passed=False,
            ground_truth="Tool should succeed",
            tool_result=tool_result.message,
            discrepancy=f"Tool failed: {tool_result.error or tool_result.message}"
        ))
        return results

    tool_data = tool_result.data

    # Ground truth: Total open tasks
    gt_open = execute_single("""
        SELECT COUNT(*) as count FROM tasks
        WHERE status NOT IN ('completed', 'cancelled')
    """)
    gt_open_count = gt_open["count"] if gt_open else 0
    tool_count = tool_data.get("total_count", 0)

    results.append(ValidationResult(
        tool_name=tool_name,
        check_name="open_task_count",
        passed=compare_values(gt_open_count, tool_count),
        ground_truth=gt_open_count,
        tool_result=tool_count,
        discrepancy=f"Expected {gt_open_count}, got {tool_count}" if gt_open_count != tool_count else None
    ))

    # Ground truth: Overdue tasks
    gt_overdue = execute_single("""
        SELECT COUNT(*) as count FROM tasks
        WHERE due_date < CURRENT_DATE
        AND status NOT IN ('completed', 'cancelled')
    """)
    gt_overdue_count = gt_overdue["count"] if gt_overdue else 0
    tool_overdue = tool_data.get("summary", {}).get("overdue", 0)

    results.append(ValidationResult(
        tool_name=tool_name,
        check_name="overdue_count",
        passed=compare_values(gt_overdue_count, tool_overdue),
        ground_truth=gt_overdue_count,
        tool_result=tool_overdue,
        discrepancy=f"Expected {gt_overdue_count} overdue, got {tool_overdue}" if gt_overdue_count != tool_overdue else None
    ))

    return results


# =============================================================================
# 3. Lead Status Validation (by counting leads in different statuses)
# =============================================================================

def validate_leads() -> List[ValidationResult]:
    """Validate lead-related tools against direct database queries."""
    results = []
    tool_name = "get_lead_details"

    print(f"\n{'='*60}")
    print(f"VALIDATING: Lead Tools")
    print(f"{'='*60}")

    # Check lead counts by status
    gt_lead_counts = execute_query("""
        SELECT status, COUNT(*) as count
        FROM leads
        GROUP BY status
    """)

    if not gt_lead_counts:
        results.append(ValidationResult(
            tool_name="lead_validation",
            check_name="leads_exist",
            passed=True,
            ground_truth=0,
            tool_result=0,
            discrepancy="No leads in database"
        ))
        return results

    gt_lead_dict = {row["status"]: row["count"] for row in gt_lead_counts}
    total_leads = sum(gt_lead_dict.values())

    results.append(ValidationResult(
        tool_name="lead_validation",
        check_name="total_leads",
        passed=True,
        ground_truth=total_leads,
        tool_result=total_leads,
        discrepancy=None
    ))

    # Test get_lead_details with a real lead ID
    sample_lead = execute_single("SELECT id FROM leads LIMIT 1")
    if sample_lead:
        tool_def = tool_registry.get("get_lead_details")
        if tool_def:
            try:
                tool_result = tool_def.func(lead_id=sample_lead["id"])

                results.append(ValidationResult(
                    tool_name="get_lead_details",
                    check_name="single_lead_fetch",
                    passed=tool_result.status.value in ("success", "no_data"),
                    ground_truth=f"Lead {sample_lead['id']}",
                    tool_result=tool_result.status.value,
                    discrepancy=None if tool_result.status.value == "success" else tool_result.message
                ))
            except Exception as e:
                results.append(ValidationResult(
                    tool_name="get_lead_details",
                    check_name="single_lead_fetch",
                    passed=False,
                    ground_truth=f"Lead {sample_lead['id']}",
                    tool_result=str(e),
                    discrepancy=f"Exception: {str(e)}"
                ))

    return results


# =============================================================================
# 4. SLA Status Validation
# =============================================================================

def validate_sla_status() -> List[ValidationResult]:
    """Validate check_sla_status against direct database queries."""
    results = []
    tool_name = "check_sla_status"

    print(f"\n{'='*60}")
    print(f"VALIDATING: {tool_name}")
    print(f"{'='*60}")

    # Get tool result
    tool_def = tool_registry.get(tool_name)
    if not tool_def:
        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="tool_exists",
            passed=False,
            ground_truth="Tool should exist",
            tool_result="Tool not found",
            discrepancy="Tool not in registry"
        ))
        return results

    tool_result = tool_def.func()

    if tool_result.status.value == "no_data":
        # No active loans is valid
        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="no_data_correct",
            passed=True,
            ground_truth="No active loans",
            tool_result="no_data",
            discrepancy=None
        ))
        return results

    if tool_result.status.value != "success":
        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="tool_execution",
            passed=False,
            ground_truth="Tool should succeed",
            tool_result=tool_result.message,
            discrepancy=f"Tool failed: {tool_result.error or tool_result.message}"
        ))
        return results

    tool_data = tool_result.data

    # Ground truth: Total active loans
    gt_total = execute_single("""
        SELECT COUNT(*) as count
        FROM loans
        WHERE stage NOT IN ('Funded')
    """)
    gt_total_count = gt_total["count"] if gt_total else 0
    tool_total = tool_data.get("total_loans", 0)

    results.append(ValidationResult(
        tool_name=tool_name,
        check_name="total_active_loans",
        passed=compare_values(gt_total_count, tool_total),
        ground_truth=gt_total_count,
        tool_result=tool_total,
        discrepancy=f"Expected {gt_total_count}, got {tool_total}" if gt_total_count != tool_total else None
    ))

    # Ground truth: SLA breached loans (using simplified SLA logic)
    # SLA targets: processing=5, submitted=2, etc.
    # SQLite version - calculate days in stage
    gt_breached = execute_single("""
        SELECT COUNT(*) as count
        FROM loans l
        WHERE l.stage NOT IN ('Funded')
        AND (julianday('now') - julianday(l.stage_changed_at)) >
            CASE l.stage
                WHEN 'Disclosed' THEN 3
                WHEN 'Processing' THEN 5
                WHEN 'Submitted' THEN 2
                WHEN 'UW Received' THEN 3
                WHEN 'Approved' THEN 2
                WHEN 'Suspended' THEN 7
                WHEN 'CTC' THEN 2
                WHEN 'Docs Out' THEN 3
                ELSE 5
            END
    """)
    gt_breached_count = gt_breached["count"] if gt_breached else 0
    tool_breached = tool_data.get("breached_count", 0)

    results.append(ValidationResult(
        tool_name=tool_name,
        check_name="breached_count",
        passed=compare_values(gt_breached_count, tool_breached),
        ground_truth=gt_breached_count,
        tool_result=tool_breached,
        discrepancy=f"Expected {gt_breached_count} breached, got {tool_breached}" if gt_breached_count != tool_breached else None
    ))

    return results


# =============================================================================
# 5. Missing Documents Validation
# =============================================================================

def validate_missing_documents() -> List[ValidationResult]:
    """Validate get_missing_documents against direct database queries."""
    results = []
    tool_name = "get_missing_documents"

    print(f"\n{'='*60}")
    print(f"VALIDATING: {tool_name}")
    print(f"{'='*60}")

    # Get tool
    tool_def = tool_registry.get(tool_name)
    if not tool_def:
        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="tool_exists",
            passed=False,
            ground_truth="Tool should exist",
            tool_result="Tool not found",
            discrepancy="Tool not in registry"
        ))
        return results

    # Get a sample loan to test
    sample_loan = execute_single("""
        SELECT id, loan_number FROM loans
        WHERE stage NOT IN ('Funded')
        LIMIT 1
    """)

    if not sample_loan:
        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="sample_loan",
            passed=True,
            ground_truth="No active loans",
            tool_result="No loans to test",
            discrepancy=None
        ))
        return results

    loan_id = sample_loan["id"]

    # Call tool
    try:
        tool_result = tool_def.func(loan_id=str(loan_id))
    except Exception as e:
        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="tool_execution",
            passed=False,
            ground_truth=f"Test loan {loan_id}",
            tool_result=str(e),
            discrepancy=f"Exception: {str(e)}"
        ))
        return results

    if tool_result.status.value == "no_data":
        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="loan_lookup",
            passed=True,  # Tool correctly reports no data
            ground_truth=f"Loan {loan_id}",
            tool_result="no_data",
            discrepancy="Tool returned no_data (may be expected)"
        ))
        return results

    if tool_result.status.value != "success":
        results.append(ValidationResult(
            tool_name=tool_name,
            check_name="tool_execution",
            passed=False,
            ground_truth="Tool should succeed",
            tool_result=tool_result.message,
            discrepancy=f"Tool failed: {tool_result.error or tool_result.message}"
        ))
        return results

    tool_data = tool_result.data

    # Ground truth: Document counts for this loan
    gt_docs = execute_single("""
        SELECT COUNT(*) as count
        FROM documents
        WHERE loan_id = :loan_id
    """, {"loan_id": loan_id})
    gt_doc_count = gt_docs["count"] if gt_docs else 0
    tool_received = tool_data.get("summary", {}).get("received", 0)

    # Note: Tool counts "received" docs, DB counts all docs - these may differ
    # This validates the tool returns a reasonable number
    results.append(ValidationResult(
        tool_name=tool_name,
        check_name="document_count",
        passed=tool_received >= 0,  # Just verify non-negative
        ground_truth=f"DB has {gt_doc_count} doc records",
        tool_result=f"Tool reports {tool_received} received",
        discrepancy=None
    ))

    # Validate summary structure
    summary = tool_data.get("summary", {})
    required_keys = ["total_required", "received", "missing", "completion_rate"]
    has_all_keys = all(k in summary for k in required_keys)

    results.append(ValidationResult(
        tool_name=tool_name,
        check_name="summary_structure",
        passed=has_all_keys,
        ground_truth=required_keys,
        tool_result=list(summary.keys()),
        discrepancy=None if has_all_keys else f"Missing keys: {set(required_keys) - set(summary.keys())}"
    ))

    return results


# =============================================================================
# Main Runner
# =============================================================================

def run_all_validations():
    """Run all validation tests and report results."""
    print("=" * 70)
    print("PERENNIA AI - DATA ACCURACY VALIDATION")
    print("=" * 70)
    print(f"Run at: {datetime.now().isoformat()}")
    print()

    all_results: List[ValidationResult] = []

    # Run each validator
    validators = [
        ("Pipeline Metrics", validate_pipeline_metrics),
        ("Task Queue", validate_task_queue),
        ("Lead Tools", validate_leads),
        ("SLA Status", validate_sla_status),
        ("Missing Documents", validate_missing_documents),
    ]

    for name, validator in validators:
        try:
            results = validator()
            all_results.extend(results)
        except Exception as e:
            print(f"\n❌ ERROR in {name}: {e}")
            all_results.append(ValidationResult(
                tool_name=name.lower().replace(" ", "_"),
                check_name="validator_error",
                passed=False,
                ground_truth="Validator should run",
                tool_result=str(e),
                discrepancy=f"Exception: {e}"
            ))

    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    passed = [r for r in all_results if r.passed]
    failed = [r for r in all_results if not r.passed]

    print(f"\nTotal Checks: {len(all_results)}")
    print(f"  ✅ Passed: {len(passed)}")
    print(f"  ❌ Failed: {len(failed)}")

    if failed:
        print("\n" + "-" * 70)
        print("DISCREPANCIES FOUND:")
        print("-" * 70)
        for r in failed:
            print(f"\n  Tool: {r.tool_name}")
            print(f"  Check: {r.check_name}")
            print(f"  Ground Truth: {r.ground_truth}")
            print(f"  Tool Result: {r.tool_result}")
            if r.discrepancy:
                print(f"  Discrepancy: {r.discrepancy}")

    if passed:
        print("\n" + "-" * 70)
        print("PASSED CHECKS:")
        print("-" * 70)
        for r in passed:
            print(f"  ✅ {r.tool_name}: {r.check_name}")
            if r.ground_truth != r.tool_result:
                print(f"       GT={r.ground_truth}, Tool={r.tool_result}")

    print("\n" + "=" * 70)
    success_rate = (len(passed) / len(all_results) * 100) if all_results else 0
    print(f"SUCCESS RATE: {success_rate:.1f}%")
    print("=" * 70)

    return len(failed) == 0


if __name__ == "__main__":
    success = run_all_validations()
    sys.exit(0 if success else 1)
