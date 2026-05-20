# Perennia AI - Database Optimization Script
# Index recommendations and query optimization for agent tools

"""
DATABASE OPTIMIZATION
=====================
This script provides:
1. Index recommendations based on tool queries
2. Query analysis and optimization suggestions
3. Table statistics
4. Connection pool tuning

Save as: backend/agents/db_optimization.py
Run: python -m agents.db_optimization
"""

from typing import Dict, List, Any
from dataclasses import dataclass


# =============================================================================
# INDEX RECOMMENDATIONS
# =============================================================================

@dataclass
class IndexRecommendation:
    table: str
    columns: List[str]
    reason: str
    priority: str  # HIGH, MEDIUM, LOW
    used_by_tools: List[str]
    create_statement: str


def get_recommended_indexes() -> List[IndexRecommendation]:
    """Get all recommended indexes for optimal tool performance."""

    indexes = [
        # =====================================================================
        # LOANS TABLE - Core mortgage data
        # =====================================================================
        IndexRecommendation(
            table="loans",
            columns=["status"],
            reason="Pipeline queries filter by status constantly",
            priority="HIGH",
            used_by_tools=["get_pipeline_metrics", "get_loans_by_status", "get_loan_aging_report"],
            create_statement="CREATE INDEX idx_loans_status ON loans(status);"
        ),
        IndexRecommendation(
            table="loans",
            columns=["loan_officer_id"],
            reason="Most queries filter by LO",
            priority="HIGH",
            used_by_tools=["get_pipeline_metrics", "get_lo_metrics", "compare_to_peers"],
            create_statement="CREATE INDEX idx_loans_lo_id ON loans(loan_officer_id);"
        ),
        IndexRecommendation(
            table="loans",
            columns=["status", "loan_officer_id"],
            reason="Composite for LO-specific pipeline queries",
            priority="HIGH",
            used_by_tools=["get_pipeline_metrics", "get_loans_by_status"],
            create_statement="CREATE INDEX idx_loans_status_lo ON loans(status, loan_officer_id);"
        ),
        IndexRecommendation(
            table="loans",
            columns=["expected_close_date"],
            reason="Closing timeline predictions",
            priority="HIGH",
            used_by_tools=["predict_closing_timeline", "get_bottleneck_analysis"],
            create_statement="CREATE INDEX idx_loans_close_date ON loans(expected_close_date);"
        ),
        IndexRecommendation(
            table="loans",
            columns=["created_at"],
            reason="Date range filtering",
            priority="MEDIUM",
            used_by_tools=["calculate_conversion_rates", "get_profitability_trends"],
            create_statement="CREATE INDEX idx_loans_created ON loans(created_at);"
        ),
        IndexRecommendation(
            table="loans",
            columns=["funded_at"],
            reason="Revenue and profitability queries",
            priority="MEDIUM",
            used_by_tools=["forecast_revenue", "get_profitability_trends"],
            create_statement="CREATE INDEX idx_loans_funded ON loans(funded_at);"
        ),
        IndexRecommendation(
            table="loans",
            columns=["status_changed_at"],
            reason="Aging and velocity calculations",
            priority="MEDIUM",
            used_by_tools=["get_loan_aging_report", "get_bottleneck_analysis"],
            create_statement="CREATE INDEX idx_loans_status_changed ON loans(status_changed_at);"
        ),
        IndexRecommendation(
            table="loans",
            columns=["branch_id"],
            reason="Branch-level reporting",
            priority="LOW",
            used_by_tools=["get_pipeline_metrics", "compare_to_benchmark"],
            create_statement="CREATE INDEX idx_loans_branch ON loans(branch_id);"
        ),
        IndexRecommendation(
            table="loans",
            columns=["loan_type"],
            reason="Segment analysis",
            priority="LOW",
            used_by_tools=["analyze_margins_by_segment", "check_fair_lending"],
            create_statement="CREATE INDEX idx_loans_type ON loans(loan_type);"
        ),

        # =====================================================================
        # LEADS TABLE
        # =====================================================================
        IndexRecommendation(
            table="leads",
            columns=["status"],
            reason="Lead filtering by status",
            priority="HIGH",
            used_by_tools=["get_lead_details", "score_lead"],
            create_statement="CREATE INDEX idx_leads_status ON leads(status);"
        ),
        IndexRecommendation(
            table="leads",
            columns=["assigned_to"],
            reason="LO-specific lead queries",
            priority="HIGH",
            used_by_tools=["get_lead_details", "suggest_followup"],
            create_statement="CREATE INDEX idx_leads_assigned ON leads(assigned_to);"
        ),
        IndexRecommendation(
            table="leads",
            columns=["score"],
            reason="Lead prioritization",
            priority="MEDIUM",
            used_by_tools=["score_lead", "get_similar_converted_leads"],
            create_statement="CREATE INDEX idx_leads_score ON leads(score DESC);"
        ),
        IndexRecommendation(
            table="leads",
            columns=["created_at"],
            reason="Lead age tracking",
            priority="MEDIUM",
            used_by_tools=["get_lead_details", "get_engagement_history"],
            create_statement="CREATE INDEX idx_leads_created ON leads(created_at);"
        ),
        IndexRecommendation(
            table="leads",
            columns=["source_type"],
            reason="Lead source analysis",
            priority="LOW",
            used_by_tools=["get_lead_details"],
            create_statement="CREATE INDEX idx_leads_source ON leads(source_type);"
        ),

        # =====================================================================
        # DOCUMENTS TABLE
        # =====================================================================
        IndexRecommendation(
            table="documents",
            columns=["loan_id"],
            reason="Document lookups by loan",
            priority="HIGH",
            used_by_tools=["get_missing_documents", "get_document_timeline", "audit_loan_file"],
            create_statement="CREATE INDEX IF NOT EXISTS idx_docs_loan ON documents(loan_id);"
        ),
        IndexRecommendation(
            table="documents",
            columns=["loan_id", "doc_type"],
            reason="Specific document checks",
            priority="HIGH",
            used_by_tools=["track_document_request", "check_document_expiration"],
            create_statement="CREATE INDEX IF NOT EXISTS idx_docs_loan_type ON documents(loan_id, doc_type);"
        ),
        IndexRecommendation(
            table="documents",
            columns=["status"],
            reason="Document status filtering",
            priority="MEDIUM",
            used_by_tools=["get_missing_documents", "get_document_timeline"],
            create_statement="CREATE INDEX IF NOT EXISTS idx_docs_status ON documents(status);"
        ),

        # =====================================================================
        # LOAN_CONDITIONS TABLE
        # =====================================================================
        IndexRecommendation(
            table="loan_conditions",
            columns=["loan_id"],
            reason="Condition lookups",
            priority="HIGH",
            used_by_tools=["get_loan_conditions", "get_missing_documents"],
            create_statement="CREATE INDEX idx_conditions_loan ON loan_conditions(loan_id);"
        ),
        IndexRecommendation(
            table="loan_conditions",
            columns=["loan_id", "status"],
            reason="Open conditions by loan",
            priority="HIGH",
            used_by_tools=["get_loan_conditions"],
            create_statement="CREATE INDEX idx_conditions_loan_status ON loan_conditions(loan_id, status);"
        ),
        IndexRecommendation(
            table="loan_conditions",
            columns=["condition_type"],
            reason="Condition type filtering",
            priority="MEDIUM",
            used_by_tools=["get_loan_conditions"],
            create_statement="CREATE INDEX idx_conditions_type ON loan_conditions(condition_type);"
        ),

        # =====================================================================
        # COMMUNICATION_HISTORY TABLE
        # =====================================================================
        IndexRecommendation(
            table="communication_history",
            columns=["contact_id"],
            reason="Customer interaction lookups",
            priority="HIGH",
            used_by_tools=["get_interaction_history", "get_engagement_history"],
            create_statement="CREATE INDEX idx_comms_contact ON communication_history(contact_id);"
        ),
        IndexRecommendation(
            table="communication_history",
            columns=["loan_id"],
            reason="Loan-specific communications",
            priority="HIGH",
            used_by_tools=["get_interaction_history"],
            create_statement="CREATE INDEX idx_comms_loan ON communication_history(loan_id);"
        ),
        IndexRecommendation(
            table="communication_history",
            columns=["created_at"],
            reason="Recent activity queries",
            priority="MEDIUM",
            used_by_tools=["get_engagement_history", "get_optimal_contact_time"],
            create_statement="CREATE INDEX idx_comms_created ON communication_history(created_at DESC);"
        ),
        IndexRecommendation(
            table="communication_history",
            columns=["contact_id", "created_at"],
            reason="Customer activity timeline",
            priority="MEDIUM",
            used_by_tools=["get_interaction_history", "assess_churn_risk"],
            create_statement="CREATE INDEX idx_comms_contact_date ON communication_history(contact_id, created_at DESC);"
        ),

        # =====================================================================
        # CONTACTS/CUSTOMERS TABLE
        # =====================================================================
        IndexRecommendation(
            table="contacts",
            columns=["email"],
            reason="Customer lookup by email",
            priority="HIGH",
            used_by_tools=["get_customer_360", "map_relationships"],
            create_statement="CREATE UNIQUE INDEX idx_contacts_email ON contacts(email);"
        ),
        IndexRecommendation(
            table="contacts",
            columns=["created_at"],
            reason="Customer tenure queries",
            priority="LOW",
            used_by_tools=["calculate_ltv", "get_customer_360"],
            create_statement="CREATE INDEX idx_contacts_created ON contacts(created_at);"
        ),

        # =====================================================================
        # LOAN_STATUS_HISTORY TABLE
        # =====================================================================
        IndexRecommendation(
            table="loan_status_history",
            columns=["loan_id"],
            reason="Status history lookups",
            priority="HIGH",
            used_by_tools=["predict_closing_timeline", "calculate_conversion_rates"],
            create_statement="CREATE INDEX idx_status_history_loan ON loan_status_history(loan_id);"
        ),
        IndexRecommendation(
            table="loan_status_history",
            columns=["changed_at"],
            reason="Recent status changes",
            priority="MEDIUM",
            used_by_tools=["get_pipeline_metrics", "get_bottleneck_analysis"],
            create_statement="CREATE INDEX idx_status_history_date ON loan_status_history(changed_at DESC);"
        ),
        IndexRecommendation(
            table="loan_status_history",
            columns=["loan_id", "changed_at"],
            reason="Loan timeline queries",
            priority="MEDIUM",
            used_by_tools=["predict_closing_timeline"],
            create_statement="CREATE INDEX idx_status_history_loan_date ON loan_status_history(loan_id, changed_at);"
        ),

        # =====================================================================
        # LOAN_FEES TABLE
        # =====================================================================
        IndexRecommendation(
            table="loan_fees",
            columns=["loan_id"],
            reason="Fee lookups by loan",
            priority="HIGH",
            used_by_tools=["check_tolerance_violations", "get_cost_breakdown", "calculate_loan_profitability"],
            create_statement="CREATE INDEX idx_fees_loan ON loan_fees(loan_id);"
        ),

        # =====================================================================
        # DISCLOSURE_EVENTS TABLE
        # =====================================================================
        IndexRecommendation(
            table="disclosure_events",
            columns=["loan_id"],
            reason="Disclosure lookups",
            priority="HIGH",
            used_by_tools=["check_trid_compliance", "get_disclosure_timeline"],
            create_statement="CREATE INDEX IF NOT EXISTS idx_disclosures_loan ON disclosure_events(loan_id);"
        ),

        # =====================================================================
        # COMPLIANCE_ISSUES TABLE
        # =====================================================================
        IndexRecommendation(
            table="compliance_issues",
            columns=["loan_id"],
            reason="Compliance history by loan",
            priority="MEDIUM",
            used_by_tools=["get_compliance_history", "audit_loan_file"],
            create_statement="CREATE INDEX idx_compliance_loan ON compliance_issues(loan_id);"
        ),

        # =====================================================================
        # REFERRALS TABLE
        # =====================================================================
        IndexRecommendation(
            table="referrals",
            columns=["referrer_id"],
            reason="Referral network queries",
            priority="MEDIUM",
            used_by_tools=["get_referral_network", "calculate_ltv"],
            create_statement="CREATE INDEX idx_referrals_referrer ON referrals(referrer_id);"
        ),
        IndexRecommendation(
            table="referrals",
            columns=["referred_id"],
            reason="Incoming referral lookups",
            priority="MEDIUM",
            used_by_tools=["map_relationships"],
            create_statement="CREATE INDEX idx_referrals_referred ON referrals(referred_id);"
        ),

        # =====================================================================
        # USERS TABLE
        # =====================================================================
        IndexRecommendation(
            table="users",
            columns=["role"],
            reason="LO and processor lookups",
            priority="MEDIUM",
            used_by_tools=["get_lo_pipeline_breakdown", "get_lo_metrics"],
            create_statement="CREATE INDEX idx_users_role ON users(role);"
        ),
        IndexRecommendation(
            table="users",
            columns=["branch_id"],
            reason="Branch team queries",
            priority="LOW",
            used_by_tools=["compare_to_peers", "get_lo_pipeline_breakdown"],
            create_statement="CREATE INDEX idx_users_branch ON users(branch_id);"
        ),
    ]

    return indexes


def generate_migration_script() -> str:
    """Generate SQL migration script for all indexes."""
    indexes = get_recommended_indexes()

    lines = [
        "-- Perennia AI Agent Tools - Database Optimization",
        "-- Index Migration Script",
        f"-- Generated: {__import__('datetime').datetime.now().isoformat()}",
        "",
        "-- =============================================",
        "-- HIGH PRIORITY INDEXES",
        "-- =============================================",
        ""
    ]

    for idx in [i for i in indexes if i.priority == "HIGH"]:
        lines.append(f"-- {idx.reason}")
        lines.append(f"-- Used by: {', '.join(idx.used_by_tools)}")
        lines.append(idx.create_statement)
        lines.append("")

    lines.extend([
        "",
        "-- =============================================",
        "-- MEDIUM PRIORITY INDEXES",
        "-- =============================================",
        ""
    ])

    for idx in [i for i in indexes if i.priority == "MEDIUM"]:
        lines.append(f"-- {idx.reason}")
        lines.append(f"-- Used by: {', '.join(idx.used_by_tools)}")
        lines.append(idx.create_statement)
        lines.append("")

    lines.extend([
        "",
        "-- =============================================",
        "-- LOW PRIORITY INDEXES",
        "-- =============================================",
        ""
    ])

    for idx in [i for i in indexes if i.priority == "LOW"]:
        lines.append(f"-- {idx.reason}")
        lines.append(f"-- Used by: {', '.join(idx.used_by_tools)}")
        lines.append(idx.create_statement)
        lines.append("")

    return "\n".join(lines)


def print_index_report():
    """Print formatted index recommendation report."""
    indexes = get_recommended_indexes()

    print("=" * 70)
    print("DATABASE INDEX RECOMMENDATIONS")
    print("=" * 70)

    by_priority = {"HIGH": [], "MEDIUM": [], "LOW": []}
    for idx in indexes:
        by_priority[idx.priority].append(idx)

    for priority in ["HIGH", "MEDIUM", "LOW"]:
        emoji = "🔴" if priority == "HIGH" else "🟡" if priority == "MEDIUM" else "🟢"
        print(f"\n{emoji} {priority} PRIORITY ({len(by_priority[priority])} indexes)")
        print("-" * 50)

        for idx in by_priority[priority]:
            cols = ", ".join(idx.columns)
            print(f"\n  📊 {idx.table}({cols})")
            print(f"     Reason: {idx.reason}")
            print(f"     Tools: {', '.join(idx.used_by_tools[:3])}{'...' if len(idx.used_by_tools) > 3 else ''}")

    print("\n" + "=" * 70)
    print(f"Total: {len(indexes)} recommended indexes")
    print(f"  HIGH: {len(by_priority['HIGH'])}")
    print(f"  MEDIUM: {len(by_priority['MEDIUM'])}")
    print(f"  LOW: {len(by_priority['LOW'])}")
    print("=" * 70)


# =============================================================================
# CONNECTION POOL TUNING
# =============================================================================

def get_pool_recommendations(
    concurrent_users: int = 10,
    avg_query_time_ms: float = 50,
    peak_queries_per_second: float = 100
) -> Dict[str, Any]:
    """Get connection pool tuning recommendations."""

    # Calculate optimal pool size
    # Formula: pool_size = concurrent_connections * (query_time / 1000) * safety_factor
    base_pool = int(peak_queries_per_second * (avg_query_time_ms / 1000) * 1.5)
    pool_size = max(5, min(base_pool, 50))  # Between 5 and 50

    # Max overflow for burst handling
    max_overflow = int(pool_size * 0.5)

    # Timeout based on query patterns
    pool_timeout = max(30, int(avg_query_time_ms * 10 / 1000))

    return {
        "recommendations": {
            "DB_POOL_SIZE": pool_size,
            "DB_MAX_OVERFLOW": max_overflow,
            "DB_POOL_TIMEOUT": pool_timeout,
            "DB_POOL_RECYCLE": 1800,  # 30 minutes
        },
        "rationale": {
            "pool_size": f"Based on {peak_queries_per_second} QPS with {avg_query_time_ms}ms avg query time",
            "max_overflow": f"50% of pool size for burst handling",
            "pool_timeout": f"10x avg query time with 30s minimum",
            "pool_recycle": "Standard 30-minute connection refresh",
        },
        "env_file": f"""
# Database Connection Pool Settings
DB_POOL_SIZE={pool_size}
DB_MAX_OVERFLOW={max_overflow}
DB_POOL_TIMEOUT={pool_timeout}
DB_POOL_RECYCLE=1800
""",
    }


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "report":
            print_index_report()
        elif sys.argv[1] == "migration":
            print(generate_migration_script())
        elif sys.argv[1] == "pool":
            recs = get_pool_recommendations()
            print("Connection Pool Recommendations:")
            print("-" * 40)
            for key, value in recs["recommendations"].items():
                print(f"  {key}={value}")
            print("\nRationale:")
            for key, reason in recs["rationale"].items():
                print(f"  {key}: {reason}")
        else:
            print("Unknown command")
    else:
        print("Usage:")
        print("  python db_optimization.py report    - Show index recommendations")
        print("  python db_optimization.py migration - Generate SQL migration")
        print("  python db_optimization.py pool      - Connection pool tuning")
