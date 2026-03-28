"""
Vendor BAA/DPA Agreement Tracking Service — Track and manage vendor data
processing and business associate agreements.
SOC 2 Criteria: CC9 (Risk Mitigation), C1 (Confidentiality), P1-P8 (Privacy)

Provides methods for:
- Querying agreement status for individual vendors
- Updating/creating vendor agreements
- Generating compliance summaries across all vendors
- Identifying agreements approaching expiry or missing entirely

Usage:
    svc = VendorAgreementService(db)
    status = svc.get_vendor_agreement_status(vendor_id=1)
    summary = svc.get_all_vendor_compliance_summary()
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..constants import AgreementStatus, AgreementType

logger = logging.getLogger("soc2.vendor_agreements")


class VendorAgreementService:
    """
    Manage BAA/DPA agreements for vendors in the soc2_vendor_registry.

    All methods operate within the caller's database session and do NOT
    call ``session.commit()`` — the caller is responsible for committing
    or rolling back the transaction.
    """

    # Vendors whose data_access_level means they likely need agreements
    _LEVELS_REQUIRING_AGREEMENT = {"full", "content", "limited"}

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_vendor_agreement_status(
        self,
        vendor_id: Optional[int] = None,
        vendor_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get the current BAA/DPA agreement status for a single vendor.

        Looks up the vendor by ``vendor_id`` (preferred) or ``vendor_name``.
        Returns vendor metadata together with all associated agreements.

        Raises:
            ValueError: If neither vendor_id nor vendor_name is provided.
            LookupError: If the vendor is not found in the registry.
        """
        if vendor_id is None and vendor_name is None:
            raise ValueError("Either vendor_id or vendor_name must be provided")

        # Resolve vendor
        if vendor_id is not None:
            vendor = self._get_vendor_by_id(vendor_id)
        else:
            vendor = self._get_vendor_by_name(vendor_name)

        if vendor is None:
            identifier = vendor_id if vendor_id is not None else vendor_name
            raise LookupError(f"Vendor not found: {identifier}")

        # Fetch all agreements for this vendor
        agreements = self._fetch_agreements(vendor["id"])

        # Determine overall compliance posture
        needs_agreement = vendor["data_access_level"] in self._LEVELS_REQUIRING_AGREEMENT
        has_signed_agreement = any(
            a["status"] == AgreementStatus.SIGNED for a in agreements
        )
        has_expired = any(
            a["status"] == AgreementStatus.SIGNED
            and a["expiry_date"] is not None
            and a["expiry_date"] < date.today()
            for a in agreements
        )

        if not needs_agreement:
            compliance_status = "not_required"
        elif has_expired:
            compliance_status = "expired"
        elif has_signed_agreement:
            compliance_status = "compliant"
        elif agreements:
            compliance_status = "in_progress"
        else:
            compliance_status = "missing"

        return {
            "vendor": {
                "id": vendor["id"],
                "vendor_name": vendor["vendor_name"],
                "category": vendor["category"],
                "data_access_level": vendor["data_access_level"],
                "risk_level": vendor["risk_level"],
                "soc2_status": vendor["soc2_status"],
            },
            "compliance_status": compliance_status,
            "needs_agreement": needs_agreement,
            "agreements": [
                self._format_agreement(a) for a in agreements
            ],
        }

    def get_all_vendor_compliance_summary(self) -> Dict[str, Any]:
        """
        Generate a compliance summary across all registered vendors.

        Returns counts by status, a list of vendors missing required
        agreements, and a list of agreements expiring within the
        configured renewal notice window.
        """
        vendors = self._fetch_all_vendors()
        if not vendors:
            logger.warning("No vendors found in soc2_vendor_registry")
            return {
                "total_vendors": 0,
                "summary": {},
                "vendors_needing_agreements": [],
                "missing_agreements": [],
                "expiring_soon": [],
                "all_vendors": [],
            }

        # Build lookup: vendor_id -> list of agreements
        all_agreements = self._fetch_all_agreements()
        agreements_by_vendor: Dict[int, List[Dict]] = {}
        for agreement in all_agreements:
            vid = agreement["vendor_id"]
            agreements_by_vendor.setdefault(vid, []).append(agreement)

        today = date.today()
        vendors_needing = []
        missing = []
        expiring_soon = []
        vendor_details = []

        status_counts = {
            "compliant": 0,
            "missing": 0,
            "expired": 0,
            "in_progress": 0,
            "not_required": 0,
        }

        for vendor in vendors:
            vid = vendor["id"]
            vendor_agreements = agreements_by_vendor.get(vid, [])
            needs_agreement = vendor["data_access_level"] in self._LEVELS_REQUIRING_AGREEMENT

            has_signed = any(
                a["status"] == AgreementStatus.SIGNED for a in vendor_agreements
            )
            has_expired = any(
                a["status"] == AgreementStatus.SIGNED
                and a["expiry_date"] is not None
                and a["expiry_date"] < today
                for a in vendor_agreements
            )

            if not needs_agreement:
                compliance = "not_required"
            elif has_expired:
                compliance = "expired"
            elif has_signed:
                compliance = "compliant"
            elif vendor_agreements:
                compliance = "in_progress"
            else:
                compliance = "missing"

            status_counts[compliance] += 1

            vendor_summary = {
                "vendor_id": vid,
                "vendor_name": vendor["vendor_name"],
                "category": vendor["category"],
                "data_access_level": vendor["data_access_level"],
                "risk_level": vendor["risk_level"],
                "compliance_status": compliance,
                "agreement_count": len(vendor_agreements),
            }
            vendor_details.append(vendor_summary)

            if needs_agreement:
                vendors_needing.append(vendor["vendor_name"])

            if compliance == "missing":
                missing.append({
                    "vendor_id": vid,
                    "vendor_name": vendor["vendor_name"],
                    "data_access_level": vendor["data_access_level"],
                    "risk_level": vendor["risk_level"],
                })

            # Check for expiring agreements
            for agreement in vendor_agreements:
                if (
                    agreement["status"] == AgreementStatus.SIGNED
                    and agreement["expiry_date"] is not None
                ):
                    renewal_days = agreement.get("renewal_notice_days") or 90
                    alert_date = agreement["expiry_date"] - timedelta(days=renewal_days)
                    if today >= alert_date:
                        days_until = (agreement["expiry_date"] - today).days
                        expiring_soon.append({
                            "vendor_id": vid,
                            "vendor_name": vendor["vendor_name"],
                            "agreement_type": agreement["agreement_type"],
                            "expiry_date": agreement["expiry_date"].isoformat(),
                            "days_until_expiry": days_until,
                            "is_expired": days_until < 0,
                        })

        # Sort expiring by urgency
        expiring_soon.sort(key=lambda x: x["days_until_expiry"])

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_vendors": len(vendors),
            "vendors_needing_agreements": vendors_needing,
            "summary": status_counts,
            "missing_agreements": missing,
            "expiring_soon": expiring_soon,
            "all_vendors": vendor_details,
        }

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def update_vendor_agreement(
        self,
        vendor_id: int,
        agreement_type: str,
        status: str = AgreementStatus.PENDING,
        signed_date: Optional[date] = None,
        effective_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
        signed_by: Optional[str] = None,
        vendor_signer: Optional[str] = None,
        vendor_signer_title: Optional[str] = None,
        document_url: Optional[str] = None,
        document_hash: Optional[str] = None,
        data_categories: Optional[List[str]] = None,
        processing_purposes: Optional[List[str]] = None,
        sub_processors: Optional[List[str]] = None,
        auto_renew: bool = False,
        renewal_notice_days: int = 90,
        notes: Optional[str] = None,
        reviewed_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create or update a vendor agreement (upsert on vendor_id + agreement_type).

        Validates the agreement_type and status against allowed enum values
        before persisting.

        Returns the upserted agreement record as a dict.

        Raises:
            ValueError: If agreement_type or status is invalid.
            LookupError: If vendor_id does not exist.
        """
        # Validate enum values
        try:
            agreement_type_enum = AgreementType(agreement_type)
        except ValueError:
            valid = [e.value for e in AgreementType]
            raise ValueError(
                f"Invalid agreement_type '{agreement_type}'. Must be one of: {valid}"
            )

        try:
            status_enum = AgreementStatus(status)
        except ValueError:
            valid = [e.value for e in AgreementStatus]
            raise ValueError(
                f"Invalid status '{status}'. Must be one of: {valid}"
            )

        # Verify vendor exists
        vendor = self._get_vendor_by_id(vendor_id)
        if vendor is None:
            raise LookupError(f"Vendor with id {vendor_id} not found")

        # Auto-set effective_date to signed_date if not provided
        if effective_date is None and signed_date is not None:
            effective_date = signed_date

        # Compute next_review_date: 1 year from effective_date or today
        review_base = effective_date or date.today()
        next_review = date(review_base.year + 1, review_base.month, review_base.day)

        now = datetime.now(timezone.utc)

        result = self.db.execute(
            text("""
                INSERT INTO soc2_vendor_agreements (
                    created_at, updated_at, vendor_id, agreement_type, status,
                    signed_date, effective_date, expiry_date,
                    signed_by, vendor_signer, vendor_signer_title,
                    document_url, document_hash,
                    data_categories, processing_purposes, sub_processors,
                    auto_renew, renewal_notice_days,
                    last_review_date, next_review_date,
                    notes, reviewed_by
                ) VALUES (
                    :now, :now, :vendor_id, :agreement_type, :status,
                    :signed_date, :effective_date, :expiry_date,
                    :signed_by, :vendor_signer, :vendor_signer_title,
                    :document_url, :document_hash,
                    :data_categories, :processing_purposes, :sub_processors,
                    :auto_renew, :renewal_notice_days,
                    :last_review_date, :next_review_date,
                    :notes, :reviewed_by
                )
                ON CONFLICT (vendor_id, agreement_type) DO UPDATE SET
                    updated_at = :now,
                    status = EXCLUDED.status,
                    signed_date = EXCLUDED.signed_date,
                    effective_date = EXCLUDED.effective_date,
                    expiry_date = EXCLUDED.expiry_date,
                    signed_by = EXCLUDED.signed_by,
                    vendor_signer = EXCLUDED.vendor_signer,
                    vendor_signer_title = EXCLUDED.vendor_signer_title,
                    document_url = EXCLUDED.document_url,
                    document_hash = EXCLUDED.document_hash,
                    data_categories = EXCLUDED.data_categories,
                    processing_purposes = EXCLUDED.processing_purposes,
                    sub_processors = EXCLUDED.sub_processors,
                    auto_renew = EXCLUDED.auto_renew,
                    renewal_notice_days = EXCLUDED.renewal_notice_days,
                    last_review_date = EXCLUDED.last_review_date,
                    next_review_date = EXCLUDED.next_review_date,
                    notes = EXCLUDED.notes,
                    reviewed_by = EXCLUDED.reviewed_by
                RETURNING id, vendor_id, agreement_type, status,
                          signed_date, effective_date, expiry_date,
                          signed_by, vendor_signer
            """),
            {
                "now": now,
                "vendor_id": vendor_id,
                "agreement_type": agreement_type_enum.value,
                "status": status_enum.value,
                "signed_date": signed_date,
                "effective_date": effective_date,
                "expiry_date": expiry_date,
                "signed_by": signed_by,
                "vendor_signer": vendor_signer,
                "vendor_signer_title": vendor_signer_title,
                "document_url": document_url,
                "document_hash": document_hash,
                "data_categories": data_categories,
                "processing_purposes": processing_purposes,
                "sub_processors": sub_processors,
                "auto_renew": auto_renew,
                "renewal_notice_days": renewal_notice_days,
                "last_review_date": date.today() if reviewed_by else None,
                "next_review_date": next_review,
                "notes": notes,
                "reviewed_by": reviewed_by,
            },
        )

        row = result.fetchone()
        columns = result.keys()
        record = dict(zip(columns, row))

        logger.info(
            "Vendor agreement upserted: vendor_id=%s type=%s status=%s",
            vendor_id,
            agreement_type_enum.value,
            status_enum.value,
        )

        return {
            "id": record["id"],
            "vendor_id": record["vendor_id"],
            "vendor_name": vendor["vendor_name"],
            "agreement_type": record["agreement_type"],
            "status": record["status"],
            "signed_date": record["signed_date"].isoformat() if record["signed_date"] else None,
            "effective_date": record["effective_date"].isoformat() if record["effective_date"] else None,
            "expiry_date": record["expiry_date"].isoformat() if record["expiry_date"] else None,
            "signed_by": record["signed_by"],
            "vendor_signer": record["vendor_signer"],
        }

    def mark_agreement_expired(self, vendor_id: int, agreement_type: str) -> bool:
        """
        Mark a specific agreement as expired.

        Returns True if a row was updated, False if no matching agreement found.
        """
        result = self.db.execute(
            text("""
                UPDATE soc2_vendor_agreements
                SET status = :expired, updated_at = NOW()
                WHERE vendor_id = :vendor_id
                  AND agreement_type = :agreement_type
                  AND status = :signed
            """),
            {
                "expired": AgreementStatus.EXPIRED.value,
                "vendor_id": vendor_id,
                "agreement_type": agreement_type,
                "signed": AgreementStatus.SIGNED.value,
            },
        )
        updated = result.rowcount > 0
        if updated:
            logger.info(
                "Agreement marked expired: vendor_id=%s type=%s",
                vendor_id,
                agreement_type,
            )
        return updated

    def expire_overdue_agreements(self) -> int:
        """
        Bulk-expire all signed agreements whose expiry_date has passed.

        Intended to be called from a scheduled task (e.g., daily Celery beat).
        Returns the number of agreements expired.
        """
        result = self.db.execute(
            text("""
                UPDATE soc2_vendor_agreements
                SET status = :expired, updated_at = NOW()
                WHERE status = :signed
                  AND expiry_date IS NOT NULL
                  AND expiry_date < CURRENT_DATE
            """),
            {
                "expired": AgreementStatus.EXPIRED.value,
                "signed": AgreementStatus.SIGNED.value,
            },
        )
        count = result.rowcount
        if count > 0:
            logger.warning("Expired %d overdue vendor agreements", count)
        return count

    def get_expiring_agreements(self, days_ahead: int = 90) -> List[Dict[str, Any]]:
        """
        Get agreements expiring within the next N days.

        Useful for generating renewal reminders or compliance reports.
        """
        rows = self.db.execute(
            text("""
                SELECT
                    va.id, va.vendor_id, va.agreement_type, va.status,
                    va.signed_date, va.expiry_date, va.auto_renew,
                    va.renewal_notice_days, va.signed_by, va.vendor_signer,
                    vr.vendor_name, vr.category, vr.risk_level
                FROM soc2_vendor_agreements va
                JOIN soc2_vendor_registry vr ON vr.id = va.vendor_id
                WHERE va.status = :signed
                  AND va.expiry_date IS NOT NULL
                  AND va.expiry_date <= CURRENT_DATE + :days_ahead
                ORDER BY va.expiry_date ASC
            """),
            {
                "signed": AgreementStatus.SIGNED.value,
                "days_ahead": days_ahead,
            },
        ).fetchall()

        today = date.today()
        results = []
        for row in rows:
            row_dict = dict(row._mapping)
            days_until = (row_dict["expiry_date"] - today).days
            results.append({
                "agreement_id": row_dict["id"],
                "vendor_id": row_dict["vendor_id"],
                "vendor_name": row_dict["vendor_name"],
                "category": row_dict["category"],
                "risk_level": row_dict["risk_level"],
                "agreement_type": row_dict["agreement_type"],
                "expiry_date": row_dict["expiry_date"].isoformat(),
                "days_until_expiry": days_until,
                "is_expired": days_until < 0,
                "auto_renew": row_dict["auto_renew"],
                "signed_by": row_dict["signed_by"],
            })

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_vendor_by_id(self, vendor_id: int) -> Optional[Dict[str, Any]]:
        """Fetch vendor from registry by ID."""
        row = self.db.execute(
            text("""
                SELECT id, vendor_name, category, data_access_level,
                       soc2_status, risk_level, notes
                FROM soc2_vendor_registry
                WHERE id = :vendor_id
            """),
            {"vendor_id": vendor_id},
        ).fetchone()
        return dict(row._mapping) if row else None

    def _get_vendor_by_name(self, vendor_name: str) -> Optional[Dict[str, Any]]:
        """Fetch vendor from registry by name (case-insensitive)."""
        row = self.db.execute(
            text("""
                SELECT id, vendor_name, category, data_access_level,
                       soc2_status, risk_level, notes
                FROM soc2_vendor_registry
                WHERE LOWER(vendor_name) = LOWER(:vendor_name)
            """),
            {"vendor_name": vendor_name},
        ).fetchone()
        return dict(row._mapping) if row else None

    def _fetch_agreements(self, vendor_id: int) -> List[Dict[str, Any]]:
        """Fetch all agreements for a vendor."""
        rows = self.db.execute(
            text("""
                SELECT id, vendor_id, agreement_type, status,
                       signed_date, effective_date, expiry_date,
                       signed_by, vendor_signer, vendor_signer_title,
                       document_url, document_hash,
                       data_categories, processing_purposes, sub_processors,
                       auto_renew, renewal_notice_days,
                       last_review_date, next_review_date,
                       notes, reviewed_by, created_at, updated_at
                FROM soc2_vendor_agreements
                WHERE vendor_id = :vendor_id
                ORDER BY agreement_type
            """),
            {"vendor_id": vendor_id},
        ).fetchall()
        return [dict(row._mapping) for row in rows]

    def _fetch_all_vendors(self) -> List[Dict[str, Any]]:
        """Fetch all vendors from the registry."""
        rows = self.db.execute(
            text("""
                SELECT id, vendor_name, category, data_access_level,
                       soc2_status, risk_level
                FROM soc2_vendor_registry
                ORDER BY vendor_name
            """),
        ).fetchall()
        return [dict(row._mapping) for row in rows]

    def _fetch_all_agreements(self) -> List[Dict[str, Any]]:
        """Fetch all agreements across all vendors."""
        rows = self.db.execute(
            text("""
                SELECT id, vendor_id, agreement_type, status,
                       signed_date, effective_date, expiry_date,
                       signed_by, vendor_signer,
                       auto_renew, renewal_notice_days,
                       created_at, updated_at
                FROM soc2_vendor_agreements
                ORDER BY vendor_id, agreement_type
            """),
        ).fetchall()
        return [dict(row._mapping) for row in rows]

    @staticmethod
    def _format_agreement(agreement: Dict[str, Any]) -> Dict[str, Any]:
        """Format an agreement record for API responses."""
        def _iso(val: Any) -> Optional[str]:
            if val is None:
                return None
            if isinstance(val, (date, datetime)):
                return val.isoformat()
            return str(val)

        return {
            "id": agreement["id"],
            "agreement_type": agreement["agreement_type"],
            "status": agreement["status"],
            "signed_date": _iso(agreement.get("signed_date")),
            "effective_date": _iso(agreement.get("effective_date")),
            "expiry_date": _iso(agreement.get("expiry_date")),
            "signed_by": agreement.get("signed_by"),
            "vendor_signer": agreement.get("vendor_signer"),
            "vendor_signer_title": agreement.get("vendor_signer_title"),
            "document_url": agreement.get("document_url"),
            "data_categories": agreement.get("data_categories") or [],
            "processing_purposes": agreement.get("processing_purposes") or [],
            "sub_processors": agreement.get("sub_processors") or [],
            "auto_renew": agreement.get("auto_renew", False),
            "renewal_notice_days": agreement.get("renewal_notice_days", 90),
            "last_review_date": _iso(agreement.get("last_review_date")),
            "next_review_date": _iso(agreement.get("next_review_date")),
            "notes": agreement.get("notes"),
            "reviewed_by": agreement.get("reviewed_by"),
        }
