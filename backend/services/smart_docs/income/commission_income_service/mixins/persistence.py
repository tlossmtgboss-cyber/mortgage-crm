"""Persistence of calculation results and org verification."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy import text

from .._shared import CommissionIncomeResult

logger = logging.getLogger(__name__)


class PersistenceMixin:
    # =========================================================================
    # INTERNAL: PERSISTENCE
    # =========================================================================

    def _save_calculation(self, result: CommissionIncomeResult) -> None:
        """
        Persist commission income calculation to income_calculations and
        income_sources tables.
        """
        try:
            now = datetime.now(timezone.utc)

            # Insert into income_calculations
            calc_row = self.db.execute(
                text("""
                    INSERT INTO income_calculations (
                        loan_id, borrower_id,
                        calculation_type, status,
                        total_qualifying_monthly_income,
                        total_qualifying_annual_income,
                        calculation_method,
                        ai_confidence_score,
                        ai_flags, ai_recommendations,
                        source_documents,
                        calculation_duration_ms,
                        created_at, updated_at
                    ) VALUES (
                        :loan_id, :borrower_id,
                        :calc_type, :status,
                        :total_monthly, :total_annual,
                        :method,
                        :confidence,
                        :flags, :recommendations,
                        :source_docs,
                        :duration,
                        :now, :now
                    )
                    RETURNING id
                """),
                {
                    "loan_id": result.loan_id,
                    "borrower_id": result.borrower_id,
                    "calc_type": "commission",
                    "status": "needs_review" if result.flags else "completed",
                    "total_monthly": float(result.total_qualifying_monthly),
                    "total_annual": float(result.total_qualifying_annual),
                    "method": result.primary_calculation_method.value,
                    "confidence": result.confidence,
                    "flags": json.dumps(result.flags),
                    "recommendations": json.dumps(result.recommendations),
                    "source_docs": json.dumps(
                        list({did for s in result.sources for did in s.source_doc_ids})
                    ),
                    "duration": result.duration_ms,
                    "now": now,
                },
            )
            db_calc_id = calc_row.fetchone()[0]

            # Insert income_sources for each commission source
            for idx, source in enumerate(result.sources):
                source_row = self.db.execute(
                    text("""
                        INSERT INTO income_sources (
                            calculation_id, borrower_id,
                            source_type, employer_name, position_title,
                            is_primary,
                            base_monthly_income, commission_monthly,
                            total_monthly_income, total_annual_income,
                            trending_direction,
                            year1_income, year2_income,
                            year_over_year_change_pct,
                            verification_status,
                            source_document_ids,
                            ai_confidence, ai_notes,
                            created_at, updated_at
                        ) VALUES (
                            :calc_id, :borrower_id,
                            :source_type, :employer, :position,
                            :is_primary,
                            :base, :commission,
                            :total_monthly, :total_annual,
                            :trending,
                            :year1, :year2,
                            :yoy_pct,
                            :verification_status,
                            :doc_ids,
                            :confidence, :notes,
                            :now, :now
                        )
                        RETURNING id
                    """),
                    {
                        "calc_id": db_calc_id,
                        "borrower_id": result.borrower_id,
                        "source_type": source.commission_type.value,
                        "employer": source.employer_name,
                        "position": source.position_title,
                        "is_primary": idx == 0,
                        "base": float(source.qualifying_monthly_base),
                        "commission": float(source.qualifying_monthly_commission),
                        "total_monthly": float(source.qualifying_monthly_total),
                        "total_annual": float(source.qualifying_monthly_total * MONTHS_PER_YEAR),
                        "trending": source.trend_analysis.direction.value if source.trend_analysis else "unknown",
                        "year1": float(source.year1_commission) if source.year1_commission else None,
                        "year2": float(source.year2_commission) if source.year2_commission > ZERO else None,
                        "yoy_pct": float(source.trend_analysis.yoy_change_pct) if source.trend_analysis and source.trend_analysis.yoy_change_pct is not None else None,
                        "verification_status": "unverified",
                        "doc_ids": json.dumps(source.source_doc_ids),
                        "confidence": source.confidence,
                        "notes": source.notes,
                        "now": now,
                    },
                )
                source_id = source_row.fetchone()[0]

                # Insert verification tasks linked to this source
                for task in result.tasks_to_create:
                    self.db.execute(
                        text("""
                            INSERT INTO income_verification_tasks (
                                calculation_id, income_source_id,
                                loan_id, organization_id,
                                task_type, title, description,
                                priority, status,
                                ai_recommendation,
                                created_at, updated_at
                            ) VALUES (
                                :calc_id, :source_id,
                                :loan_id, :org_id,
                                :task_type, :title, :description,
                                :priority, 'open',
                                :ai_rec,
                                :now, :now
                            )
                        """),
                        {
                            "calc_id": db_calc_id,
                            "source_id": source_id,
                            "loan_id": result.loan_id,
                            "org_id": self.org_id,
                            "task_type": task["task_type"],
                            "title": task["title"],
                            "description": task["description"],
                            "priority": task["priority"],
                            "ai_rec": task.get("ai_recommendation", ""),
                            "now": now,
                        },
                    )

            self.db.commit()

            # Update result with DB ID
            result.calculation_id = str(db_calc_id)

            logger.info(
                "Commission income calculation saved: db_id=%s loan=%s borrower=%s "
                "org=%s sources=%d tasks=%d",
                db_calc_id, result.loan_id, result.borrower_id,
                self.org_id,
                len(result.sources), len(result.tasks_to_create),
            )

        except Exception as e:
            self.db.rollback()
            logger.exception(
                "Failed to save commission income calculation: loan=%s borrower=%s org=%s: %s",
                result.loan_id, result.borrower_id, self.org_id, e,
            )
            result.flags.append(f"PERSISTENCE_ERROR: Failed to save calculation: {e}")

    # =========================================================================
    # INTERNAL: ORG VERIFICATION
    # =========================================================================

    def _verify_loan_org(self, loan_id: int) -> None:
        """Verify loan belongs to this organization."""
        row = self.db.execute(
            text("SELECT organization_id FROM loans WHERE id = :loan_id"),
            {"loan_id": loan_id},
        ).fetchone()

        if not row:
            raise ValueError(f"Loan {loan_id} not found.")

        if row.organization_id != self.org_id:
            from exceptions import TenantIsolationError
            raise TenantIsolationError(
                message=f"Loan {loan_id} belongs to org {row.organization_id}, not {self.org_id}",
                requesting_org_id=self.org_id,
                target_org_id=row.organization_id,
            )
