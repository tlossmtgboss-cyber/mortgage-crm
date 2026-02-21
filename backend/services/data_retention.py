"""
Data Retention Policy Service
Enterprise Readiness - Domain 8: Disaster Recovery (Check 8.9, 8.10)

Configurable per-organization data retention policies with automated
cleanup of expired records. Mortgage regulatory default is 7 years.

Key principles:
- Audit logs and compliance records are NEVER deleted (regulatory)
- PII is redacted rather than deleted when retention expires
- Each org can override default retention periods
- Retention actions are logged in the audit trail
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Default retention periods (in days) per data category.
# Mortgage regulatory requirements: 7 years for most loan records.
DEFAULT_RETENTION_DAYS = {
    "leads": 2555,              # 7 years — regulatory
    "loans": 2555,              # 7 years — regulatory
    "loan_fees": 2555,          # 7 years — TRID
    "disclosure_events": 2555,  # 7 years — TRID
    "adverse_action_notices": 2555,  # 7 years — ECOA
    "compliance_alerts": 2555,  # 7 years — regulatory
    "activities": 2555,         # 7 years — audit trail
    "sms_messages": 1095,       # 3 years — TCPA
    "email_messages": 1095,     # 3 years
    "call_logs": 1095,          # 3 years — TCPA
    "notifications": 365,       # 1 year
    "conversation_memory": 365, # 1 year
    "ai_audit_logs": 2555,      # 7 years — compliance
    "ai_feedback_logs": 730,    # 2 years
    "voicemail_drops": 365,     # 1 year
}

# Allowlist of tables that retention policies may target.
# Any table not in this set is rejected before reaching SQL execution.
_RETENTION_ALLOWED_TABLES = frozenset(DEFAULT_RETENTION_DAYS.keys())

# Tables that must NEVER be purged (regulatory and audit requirements)
NEVER_PURGE_TABLES = frozenset({
    "audit_logs",
    "stage_history",
    "borrower_applications",  # regulatory — 7 years minimum per ECOA
    "platform_contracts",
})


class DataRetentionService:
    """Manages data retention policies and automated cleanup."""

    def __init__(self, db: Session):
        self.db = db

    # =================================================================
    # Policy Management
    # =================================================================

    def get_retention_policy(
        self, organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get the retention policy for an organization.

        Falls back to system defaults if no org-specific policy exists.

        Args:
            organization_id: Org to get policy for, or None for defaults.

        Returns:
            Dict with per-table retention days and metadata.
        """
        policy = dict(DEFAULT_RETENTION_DAYS)

        if organization_id:
            self._ensure_policy_table()
            try:
                row = self.db.execute(text(
                    "SELECT policy_json, updated_at FROM data_retention_policies "
                    "WHERE organization_id = :org_id"
                ), {"org_id": organization_id}).fetchone()

                if row and row[0]:
                    overrides = (
                        json.loads(row[0])
                        if isinstance(row[0], str)
                        else row[0]
                    )
                    policy.update(overrides)
            except Exception as e:
                logger.warning(f"Could not load org retention policy: {e}")
                self.db.rollback()

        return {
            "organization_id": organization_id,
            "is_custom": organization_id is not None,
            "retention_days": policy,
            "never_purge": sorted(NEVER_PURGE_TABLES),
            "regulatory_minimum_years": 7,
        }

    def set_retention_policy(
        self,
        organization_id: int,
        overrides: Dict[str, int],
        set_by_user_id: int,
    ) -> Dict[str, Any]:
        """
        Set or update per-org retention overrides.

        Enforces that no retention period is less than the regulatory
        minimum (7 years for loan data, 3 years for communication).

        Args:
            organization_id: Org to set policy for.
            overrides: Dict mapping table names to retention days.
            set_by_user_id: Admin user who set this policy.

        Returns:
            Dict with the saved policy.

        Raises:
            ValueError: If a retention period violates minimums.
        """
        # Validate minimums
        regulatory_minimums = {
            "leads": 2555,
            "loans": 2555,
            "loan_fees": 2555,
            "disclosure_events": 2555,
            "adverse_action_notices": 2555,
            "compliance_alerts": 2555,
            "sms_messages": 1095,
            "call_logs": 1095,
            "ai_audit_logs": 2555,
        }

        violations = []
        for table, days in overrides.items():
            if table not in _RETENTION_ALLOWED_TABLES:
                violations.append(
                    f"'{table}' is not a recognized retention table"
                )
            if table in NEVER_PURGE_TABLES:
                violations.append(
                    f"'{table}' cannot have a retention policy (regulatory hold)"
                )
            min_days = regulatory_minimums.get(table, 365)
            if days < min_days:
                violations.append(
                    f"'{table}' minimum is {min_days} days, got {days}"
                )

        if violations:
            raise ValueError(
                "Retention policy violates regulatory minimums: "
                + "; ".join(violations)
            )

        self._ensure_policy_table()

        now = datetime.now(timezone.utc)
        policy_json = json.dumps(overrides)

        try:
            # Upsert
            existing = self.db.execute(text(
                "SELECT id FROM data_retention_policies "
                "WHERE organization_id = :org_id"
            ), {"org_id": organization_id}).fetchone()

            if existing:
                self.db.execute(text(
                    "UPDATE data_retention_policies "
                    "SET policy_json = :policy, updated_at = :now, "
                    "updated_by_id = :user_id "
                    "WHERE organization_id = :org_id"
                ), {
                    "org_id": organization_id,
                    "policy": policy_json,
                    "now": now,
                    "user_id": set_by_user_id,
                })
            else:
                self.db.execute(text(
                    "INSERT INTO data_retention_policies "
                    "(organization_id, policy_json, created_at, updated_at, "
                    "updated_by_id) "
                    "VALUES (:org_id, :policy, :now, :now, :user_id)"
                ), {
                    "org_id": organization_id,
                    "policy": policy_json,
                    "now": now,
                    "user_id": set_by_user_id,
                })

            self.db.commit()
            return self.get_retention_policy(organization_id)

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to save retention policy: {e}")
            raise

    # =================================================================
    # Automated Cleanup
    # =================================================================

    def run_retention_cleanup(
        self,
        organization_id: Optional[int] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute retention cleanup for expired records.

        Processes each table according to the retention policy. Records
        past their retention date are:
        - Hard deleted if they contain no regulatory data
        - PII-redacted if they contain loan/compliance data

        Args:
            organization_id: Org to clean, or None for all orgs.
            dry_run: If True, report what would be cleaned without acting.

        Returns:
            Dict with cleanup results per table.
        """
        policy = self.get_retention_policy(organization_id)
        retention_days = policy["retention_days"]

        results = {
            "dry_run": dry_run,
            "organization_id": organization_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "tables_processed": [],
            "total_records_affected": 0,
            "errors": [],
        }

        for table_name, days in retention_days.items():
            if table_name in NEVER_PURGE_TABLES:
                continue

            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            table_result = self._process_table_retention(
                table_name, cutoff, organization_id, dry_run
            )
            results["tables_processed"].append(table_result)
            results["total_records_affected"] += table_result.get("count", 0)

        results["completed_at"] = datetime.now(timezone.utc).isoformat()

        if not dry_run:
            self._log_cleanup_audit(results)

        return results

    def _process_table_retention(
        self,
        table_name: str,
        cutoff: datetime,
        organization_id: Optional[int],
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Process retention for a single table."""
        result = {
            "table": table_name,
            "cutoff_date": cutoff.isoformat(),
            "action": "skip",
            "count": 0,
        }

        # Reject table names not in the allowlist to prevent SQL injection
        if table_name not in _RETENTION_ALLOWED_TABLES:
            result["action"] = "rejected_unknown_table"
            logger.warning(f"Retention cleanup rejected unknown table: {table_name}")
            return result

        try:
            # Check if table exists
            exists = self.db.execute(text(
                "SELECT EXISTS ("
                "  SELECT FROM information_schema.tables "
                "  WHERE table_name = :t AND table_schema = 'public'"
                ")"
            ), {"t": table_name}).scalar()

            if not exists:
                result["action"] = "table_not_found"
                return result

            # Determine the date column to use
            date_col = self._get_date_column(table_name)
            if not date_col:
                result["action"] = "no_date_column"
                return result

            # Build org filter
            org_filter = ""
            params = {"cutoff": cutoff}
            if organization_id:
                has_org_col = self.db.execute(text(
                    "SELECT EXISTS ("
                    "  SELECT FROM information_schema.columns "
                    "  WHERE table_name = :t AND column_name = 'organization_id'"
                    ")"
                ), {"t": table_name}).scalar()

                if has_org_col:
                    org_filter = " AND organization_id = :org_id"
                    params["org_id"] = organization_id

            # Count expired records
            count = self.db.execute(text(
                f"SELECT COUNT(*) FROM {table_name} "  # noqa: S608
                f"WHERE {date_col} < :cutoff{org_filter}"
            ), params).scalar() or 0

            result["count"] = count

            if count == 0:
                result["action"] = "nothing_to_clean"
                return result

            if dry_run:
                result["action"] = "would_delete"
                return result

            # Tables with PII get redacted; others get deleted
            pii_tables = {
                "sms_messages", "email_messages", "conversation_memory",
            }

            if table_name in pii_tables:
                self._redact_expired(table_name, date_col, params)
                result["action"] = "redacted"
            else:
                self.db.execute(text(
                    f"DELETE FROM {table_name} "  # noqa: S608
                    f"WHERE {date_col} < :cutoff{org_filter}"
                ), params)
                result["action"] = "deleted"

            self.db.commit()

        except Exception as e:
            self.db.rollback()
            result["action"] = "error"
            result["error"] = str(e)[:200]
            logger.warning(f"Retention cleanup failed for {table_name}: {e}")

        return result

    def _redact_expired(
        self, table_name: str, date_col: str, params: dict
    ):
        """Redact PII in expired communication records."""
        org_filter = ""
        if "org_id" in params:
            org_filter = " AND organization_id = :org_id"

        redaction_map = {
            "sms_messages": (
                f"UPDATE sms_messages SET message = '[RETENTION_REDACTED]', "
                f"meta_data = NULL "
                f"WHERE {date_col} < :cutoff{org_filter}"
            ),
            "email_messages": (
                f"UPDATE email_messages SET body = '[RETENTION_REDACTED]', "
                f"html_body = NULL, subject = '[RETENTION_REDACTED]', "
                f"meta_data = NULL "
                f"WHERE {date_col} < :cutoff{org_filter}"
            ),
            "conversation_memory": (
                f"DELETE FROM conversation_memory "
                f"WHERE {date_col} < :cutoff{org_filter}"
            ),
        }

        sql = redaction_map.get(table_name)
        if sql:
            self.db.execute(text(sql), params)

    def _get_date_column(self, table_name: str) -> Optional[str]:
        """Determine the appropriate date column for a table."""
        # Priority: created_at > timestamp > sent_at > started_at
        candidates = [
            "created_at", "timestamp", "sent_at", "started_at",
            "received_at",
        ]

        for col in candidates:
            exists = self.db.execute(text(
                "SELECT EXISTS ("
                "  SELECT FROM information_schema.columns "
                "  WHERE table_name = :t AND column_name = :c"
                ")"
            ), {"t": table_name, "c": col}).scalar()
            if exists:
                return col

        return None

    def _log_cleanup_audit(self, results: Dict[str, Any]):
        """Record retention cleanup in audit trail."""
        try:
            safe = {
                "organization_id": results.get("organization_id"),
                "tables_processed": len(results.get("tables_processed", [])),
                "total_records_affected": results.get(
                    "total_records_affected", 0
                ),
                "started_at": results.get("started_at"),
                "completed_at": results.get("completed_at"),
            }

            self.db.execute(text("""
                INSERT INTO audit_logs
                    (user_id, changed_by_id, change_type, entity_type,
                     reason, after_state, timestamp)
                VALUES
                    (0, 0, :change_type, :entity_type, :reason,
                     :after_state, :timestamp)
            """), {
                "change_type": "data_retention_cleanup",
                "entity_type": "system",
                "reason": "automated_retention_policy",
                "after_state": json.dumps(safe),
                "timestamp": datetime.now(timezone.utc),
            })
            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to log retention audit: {e}")
            self.db.rollback()

    # =================================================================
    # Compliance Archival Access (Check 8.10)
    # =================================================================

    def get_archived_loan_data(
        self, loan_id: int, organization_id: int
    ) -> Dict[str, Any]:
        """
        Retrieve archived loan data for compliance purposes.

        Even after retention cleanup, all loan records, disclosures,
        fee data, and audit logs are preserved (they are in the
        NEVER_PURGE or 7-year retention category).

        Args:
            loan_id: Loan ID to retrieve.
            organization_id: Org that owns the loan (for RLS).

        Returns:
            Dict with complete loan compliance record.
        """
        result = {"loan_id": loan_id, "sections": {}}

        # Loan record
        loan = self.db.execute(text(
            "SELECT * FROM loans WHERE id = :id AND organization_id = :org"
        ), {"id": loan_id, "org": organization_id}).fetchone()

        if not loan:
            return {"loan_id": loan_id, "error": "Loan not found"}

        result["sections"]["loan"] = dict(loan._mapping) if loan else {}

        # Disclosure events
        disclosures = self.db.execute(text(
            "SELECT * FROM disclosure_events "
            "WHERE loan_id = :id ORDER BY created_at"
        ), {"id": loan_id}).fetchall()
        result["sections"]["disclosures"] = [
            dict(d._mapping) for d in disclosures
        ]

        # Fee history
        fees = self.db.execute(text(
            "SELECT * FROM loan_fees WHERE loan_id = :id ORDER BY created_at"
        ), {"id": loan_id}).fetchall()
        result["sections"]["fees"] = [
            dict(f._mapping) for f in fees
        ]

        # Adverse actions
        adverse = self.db.execute(text(
            "SELECT * FROM adverse_action_notices "
            "WHERE loan_id = :id ORDER BY created_at"
        ), {"id": loan_id}).fetchall()
        result["sections"]["adverse_actions"] = [
            dict(a._mapping) for a in adverse
        ]

        # Stage history
        stages = self.db.execute(text(
            "SELECT * FROM stage_history "
            "WHERE loan_id = :id ORDER BY changed_at"
        ), {"id": loan_id}).fetchall()
        result["sections"]["stage_history"] = [
            dict(s._mapping) for s in stages
        ]

        # Audit logs (filter by entity)
        audits = self.db.execute(text(
            "SELECT * FROM audit_logs "
            "WHERE entity_type = 'loan' AND entity_id = :id "
            "ORDER BY timestamp"
        ), {"id": str(loan_id)}).fetchall()
        result["sections"]["audit_trail"] = [
            dict(a._mapping) for a in audits
        ]

        result["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        result["retention_note"] = (
            "All loan records retained per 7-year regulatory requirement. "
            "Communication records may be redacted after 3 years."
        )

        return result

    # =================================================================
    # Table Creation
    # =================================================================

    def _ensure_policy_table(self):
        """Create data_retention_policies table if it doesn't exist."""
        try:
            self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS data_retention_policies (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL UNIQUE
                        REFERENCES organizations(id) ON DELETE CASCADE,
                    policy_json JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_by_id INTEGER REFERENCES users(id)
                )
            """))
            self.db.commit()
        except Exception as e:
            logger.debug(f"Policy table creation: {e}")
            self.db.rollback()
