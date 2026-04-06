"""
Vendor Management Service

Tracks appraisal, title, HOI, and survey vendors. Monitors performance
(turnaround time, quality, issue rate), flags slow vendors (> 2x average
turnaround), and surfaces preferred-vendor rankings per organization.

Usage:
    from services.vendor_management_service import VendorManagementService

    svc = VendorManagementService()
    perf = await svc.get_vendor_performance(vendor_id=42, db=session)
    slow = await svc.flag_slow_vendors(org_id=1, db=session)
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from database.models.vendor import Vendor, VendorOrder

logger = logging.getLogger(__name__)

# Vendor is "slow" when avg turnaround > 2x the org-wide average for that type
SLOW_VENDOR_MULTIPLIER = 2.0

VALID_ORDER_TYPES = frozenset({"appraisal", "title", "hoi", "survey"})


class VendorManagementService:
    """Service layer for vendor tracking and performance monitoring."""

    # ------------------------------------------------------------------
    # Order lifecycle
    # ------------------------------------------------------------------

    async def track_vendor_order(
        self,
        vendor_id: int,
        order_type: str,
        loan_id: int,
        db: Session,
        *,
        org_id: int | None = None,
        due_at: datetime | None = None,
        amount: float | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Create a new vendor order and return its details.

        Args:
            vendor_id: FK to vendors table.
            order_type: One of appraisal, title, hoi, survey.
            loan_id: FK to loans table.
            db: Active SQLAlchemy session.
            org_id: Override org; otherwise derived from vendor record.
            due_at: Expected completion datetime.
            amount: Dollar amount for this order.
            notes: Free-text notes.

        Returns:
            Dict with order_id and order details.
        """
        vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not vendor:
            raise ValueError(f"Vendor {vendor_id} not found")

        resolved_org = org_id or vendor.organization_id
        now = datetime.now(timezone.utc)

        order = VendorOrder(
            organization_id=resolved_org,
            vendor_id=vendor_id,
            loan_id=loan_id,
            order_type=order_type,
            status="ordered",
            ordered_at=now,
            due_at=due_at,
            amount=amount,
            notes=notes,
        )
        db.add(order)

        # Bump total_orders counter on vendor
        vendor.total_orders = (vendor.total_orders or 0) + 1
        vendor.updated_at = now

        db.flush()  # Populate order.id

        logger.info(
            "Vendor order %s created: vendor=%s type=%s loan=%s",
            order.id, vendor_id, order_type, loan_id,
        )

        return {
            "order_id": order.id,
            "vendor_id": vendor_id,
            "vendor_name": vendor.name,
            "loan_id": loan_id,
            "order_type": order_type,
            "status": order.status,
            "ordered_at": now.isoformat(),
            "due_at": due_at.isoformat() if due_at else None,
        }

    async def complete_order(
        self,
        order_id: int,
        db: Session,
        *,
        has_issues: bool = False,
        issue_description: str | None = None,
    ) -> dict[str, Any]:
        """Mark an order complete and recalculate vendor metrics."""
        order = db.query(VendorOrder).filter(VendorOrder.id == order_id).first()
        if not order:
            raise ValueError(f"VendorOrder {order_id} not found")

        now = datetime.now(timezone.utc)
        order.status = "completed"
        order.completed_at = now
        order.has_issues = has_issues
        order.issue_description = issue_description
        order.updated_at = now

        # Compute turnaround
        if order.ordered_at:
            delta = (now - order.ordered_at).total_seconds() / 86400.0
            order.turnaround_days = round(delta, 2)

        # Update vendor aggregate metrics
        vendor = db.query(Vendor).filter(Vendor.id == order.vendor_id).first()
        if vendor:
            vendor.completed_orders = (vendor.completed_orders or 0) + 1
            if has_issues:
                vendor.issue_count = (vendor.issue_count or 0) + 1
            self._recalculate_vendor_metrics(vendor, db)
            vendor.updated_at = now

        db.flush()
        return {
            "order_id": order_id,
            "status": "completed",
            "turnaround_days": float(order.turnaround_days) if order.turnaround_days else None,
            "has_issues": has_issues,
        }

    # ------------------------------------------------------------------
    # Performance reporting
    # ------------------------------------------------------------------

    async def get_vendor_performance(self, vendor_id: int, db: Session) -> dict[str, Any]:
        """Return performance metrics for a single vendor.

        Returns:
            {
                "vendor_id": int,
                "name": str,
                "vendor_type": str,
                "total_orders": int,
                "completed_orders": int,
                "avg_turnaround_days": float | None,
                "quality_score": float | None,
                "issue_rate": float,
                "is_preferred": bool,
                "recent_orders": [...],
            }
        """
        vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not vendor:
            raise ValueError(f"Vendor {vendor_id} not found")

        total = vendor.total_orders or 0
        completed = vendor.completed_orders or 0
        issues = vendor.issue_count or 0
        issue_rate = (issues / completed * 100.0) if completed > 0 else 0.0

        recent = (
            db.query(VendorOrder)
            .filter(VendorOrder.vendor_id == vendor_id)
            .order_by(VendorOrder.ordered_at.desc())
            .limit(10)
            .all()
        )

        return {
            "vendor_id": vendor.id,
            "name": vendor.name,
            "vendor_type": vendor.vendor_type,
            "total_orders": total,
            "completed_orders": completed,
            "avg_turnaround_days": float(vendor.avg_turnaround_days) if vendor.avg_turnaround_days else None,
            "quality_score": float(vendor.quality_score) if vendor.quality_score else None,
            "issue_rate": round(issue_rate, 2),
            "is_preferred": vendor.is_preferred,
            "recent_orders": [
                {
                    "order_id": o.id,
                    "loan_id": o.loan_id,
                    "order_type": o.order_type,
                    "status": o.status,
                    "ordered_at": o.ordered_at.isoformat() if o.ordered_at else None,
                    "completed_at": o.completed_at.isoformat() if o.completed_at else None,
                    "turnaround_days": float(o.turnaround_days) if o.turnaround_days else None,
                }
                for o in recent
            ],
        }

    async def flag_slow_vendors(self, org_id: int, db: Session) -> list[dict[str, Any]]:
        """Identify vendors whose avg turnaround > 2x the org average for their type.

        Returns:
            List of dicts describing slow vendors with their stats.
        """
        # Compute org-wide average turnaround per order type
        type_avgs_q = (
            db.query(
                VendorOrder.order_type,
                func.avg(VendorOrder.turnaround_days).label("avg_days"),
            )
            .filter(
                VendorOrder.organization_id == org_id,
                VendorOrder.status == "completed",
                VendorOrder.turnaround_days.isnot(None),
            )
            .group_by(VendorOrder.order_type)
            .all()
        )
        type_avg_map: dict[str, float] = {
            row.order_type: float(row.avg_days) for row in type_avgs_q if row.avg_days
        }

        if not type_avg_map:
            return []

        slow_vendors: list[dict[str, Any]] = []
        vendors = (
            db.query(Vendor)
            .filter(
                Vendor.organization_id == org_id,
                Vendor.is_active == True,  # noqa: E712
                Vendor.avg_turnaround_days.isnot(None),
            )
            .all()
        )

        for v in vendors:
            org_avg = type_avg_map.get(v.vendor_type)
            if org_avg is None:
                continue
            vendor_avg = float(v.avg_turnaround_days)
            if vendor_avg > org_avg * SLOW_VENDOR_MULTIPLIER:
                slow_vendors.append({
                    "vendor_id": v.id,
                    "name": v.name,
                    "vendor_type": v.vendor_type,
                    "avg_turnaround_days": vendor_avg,
                    "org_avg_turnaround_days": round(org_avg, 2),
                    "ratio": round(vendor_avg / org_avg, 2) if org_avg > 0 else None,
                    "total_orders": v.total_orders or 0,
                    "issue_count": v.issue_count or 0,
                })

        slow_vendors.sort(key=lambda x: x.get("ratio") or 0, reverse=True)
        logger.info("Flagged %d slow vendors for org %s", len(slow_vendors), org_id)
        return slow_vendors

    async def get_preferred_vendors(
        self, org_id: int, order_type: str, db: Session,
    ) -> list[dict[str, Any]]:
        """Return ranked list of preferred vendors for a given order type.

        Preferred vendors appear first, then sorted by quality_score desc,
        then by avg_turnaround_days asc.
        """
        vendors = (
            db.query(Vendor)
            .filter(
                Vendor.organization_id == org_id,
                Vendor.vendor_type == order_type,
                Vendor.is_active == True,  # noqa: E712
            )
            .order_by(
                Vendor.is_preferred.desc(),
                Vendor.quality_score.desc().nullslast(),
                Vendor.avg_turnaround_days.asc().nullslast(),
            )
            .all()
        )

        return [
            {
                "vendor_id": v.id,
                "name": v.name,
                "vendor_type": v.vendor_type,
                "avg_turnaround_days": float(v.avg_turnaround_days) if v.avg_turnaround_days else None,
                "quality_score": float(v.quality_score) if v.quality_score else None,
                "is_preferred": v.is_preferred,
                "total_orders": v.total_orders or 0,
                "completed_orders": v.completed_orders or 0,
            }
            for v in vendors
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recalculate_vendor_metrics(self, vendor: Vendor, db: Session) -> None:
        """Recompute avg_turnaround_days and quality_score from completed orders."""
        completed_orders = (
            db.query(VendorOrder)
            .filter(
                VendorOrder.vendor_id == vendor.id,
                VendorOrder.status == "completed",
                VendorOrder.turnaround_days.isnot(None),
            )
            .all()
        )
        if not completed_orders:
            return

        turnarounds = [float(o.turnaround_days) for o in completed_orders]
        vendor.avg_turnaround_days = round(sum(turnarounds) / len(turnarounds), 2)

        # Quality score: 100 - (issue_rate * 100)
        issue_orders = sum(1 for o in completed_orders if o.has_issues)
        issue_rate = issue_orders / len(completed_orders)
        vendor.quality_score = round((1.0 - issue_rate) * 100.0, 2)
