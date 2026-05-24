"""
Shadow Evaluator

Comparison harness for shadow mode. Queries shadow/staging items,
computes precision/recall/exclusion metrics, checks exit criteria.
"""

import logging
from datetime import datetime, timezone
from typing import Dict

from sqlalchemy import text, func
from sqlalchemy.orm import Session

logger = logging.getLogger("aria.shadow_evaluator")

EXIT_CRITERIA = {
    "min_calls_reviewed": 200,
    "min_precision": 0.95,
    "min_recall": 0.80,
    "max_exclusion_violations": 0,
}


class ShadowEvaluator:
    def __init__(self, db: Session):
        self._db = db

    def compute_metrics(self, tenant_id: int = None) -> Dict:
        from database.models.memory_staging import MemoryStaging

        query = self._db.query(MemoryStaging).filter(
            MemoryStaging.review_action.isnot(None)
        )
        if tenant_id:
            query = query.filter(MemoryStaging.organization_id == tenant_id)

        reviewed = query.all()
        if not reviewed:
            return {
                "calls_reviewed": 0,
                "precision": 0.0,
                "recall": 0.0,
                "exclusion_violations": 0,
                "exit_ready": False,
            }

        call_ids = set(r.source_call_id for r in reviewed)
        calls_reviewed = len(call_ids)

        approved = sum(1 for r in reviewed if r.review_action == "approved")
        edited = sum(1 for r in reviewed if r.review_action == "edited")
        rejected = sum(1 for r in reviewed if r.review_action == "rejected")
        total = approved + edited + rejected

        precision = approved / total if total > 0 else 0.0

        sql = text("""
            SELECT COUNT(*) FROM memory_audit_events
            WHERE event_type = 'exclusion'
            AND (:tenant_id IS NULL OR organization_id = :tenant_id)
        """)
        exclusion_violations = self._db.execute(sql, {"tenant_id": tenant_id}).scalar() or 0

        fn_sql = text("""
            SELECT COUNT(*) FROM memory_audit_events
            WHERE event_type = 'false_negative_detected'
            AND (:tenant_id IS NULL OR organization_id = :tenant_id)
        """)
        false_negatives = self._db.execute(fn_sql, {"tenant_id": tenant_id}).scalar() or 0
        total_opportunities = approved + false_negatives
        recall = approved / total_opportunities if total_opportunities > 0 else 0.0

        exit_ready = (
            calls_reviewed >= EXIT_CRITERIA["min_calls_reviewed"]
            and precision >= EXIT_CRITERIA["min_precision"]
            and recall >= EXIT_CRITERIA["min_recall"]
            and exclusion_violations <= EXIT_CRITERIA["max_exclusion_violations"]
        )

        return {
            "calls_reviewed": calls_reviewed,
            "precision": round(precision, 4),
            "precision_with_edits": round((approved + edited) / total, 4) if total > 0 else 0.0,
            "approved": approved,
            "edited": edited,
            "rejected": rejected,
            "recall": round(recall, 4),
            "exclusion_violations": exclusion_violations,
            "exit_ready": exit_ready,
        }

    def run_daily_evaluation(self, tenant_id: int = None) -> Dict:
        metrics = self.compute_metrics(tenant_id)

        from database.models.memory_audit import MemoryAuditEvent
        event_type = "shadow_exit_ready" if metrics["exit_ready"] else "shadow_evaluation"
        event = MemoryAuditEvent(
            organization_id=tenant_id or 0,
            event_type=event_type,
            details=metrics,
        )
        self._db.add(event)
        self._db.flush()

        if metrics["exit_ready"]:
            logger.info("Shadow mode exit criteria met! Manual graduation required.")

        return metrics

    def check_post_graduation_precision(self, tenant_id: int = None) -> Dict:
        sql = text("""
            SELECT
                COUNT(*) FILTER (WHERE details->>'review_action' = 'approved') AS approved,
                COUNT(*) FILTER (WHERE details->>'review_action' = 'rejected') AS rejected,
                COUNT(*) AS total
            FROM memory_audit_events
            WHERE event_type = 'staging_review'
              AND details->>'audit_sample' = 'true'
              AND created_at > NOW() - interval '7 days'
        """)
        row = self._db.execute(sql).fetchone()
        total = (row.approved or 0) + (row.rejected or 0)
        precision = row.approved / total if total > 0 else 1.0

        alert = precision < 0.90 and total >= 10

        return {
            "rolling_7d_precision": round(precision, 4),
            "sample_count": total,
            "alert_triggered": alert,
        }
