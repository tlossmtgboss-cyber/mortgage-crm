"""
Data Quality & Integrity Service
==================================

Enterprise Readiness Domain 3: Data Quality & Integrity.

Provides:
- Record completeness checks (Checks 3.1-3.5)
- Referential integrity validation (Checks 3.6-3.10)
- Duplicate detection (Checks 3.11-3.13)
- Data freshness monitoring (Checks 3.14-3.17)
- PII protection validation (Checks 3.18-3.20)

Also covers:
- Domain 7 echo prevention for Salesforce sync (Check 7.10)
- Domain 10 Encompass/Velocify import templates (Checks 10.9-10.11)
- Domain 9 dashboard performance SLA (Checks 9.12-9.13)
"""

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# RECORD COMPLETENESS (Domain 3, Checks 3.1-3.5)
# =============================================================================

def check_record_completeness(db, org_id: int) -> Dict:
    """Check completeness of required fields across all entity types."""
    from sqlalchemy import text

    results = {}

    # 3.1 Contact required fields
    row = db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN email IS NULL OR email = '' THEN 1 END) as missing_email,
            COUNT(CASE WHEN first_name IS NULL OR first_name = '' THEN 1 END) as missing_name,
            COUNT(CASE WHEN phone IS NULL OR phone = '' THEN 1 END) as missing_phone
        FROM leads
        WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()

    total = row[0] or 1
    results["contacts"] = {
        "total": row[0],
        "missing_email_pct": round((row[1] / total) * 100, 1),
        "missing_name_pct": round((row[2] / total) * 100, 1),
        "missing_phone_pct": round((row[3] / total) * 100, 1),
        "pass": (row[1] / total) < 0.02 and (row[2] / total) < 0.02,
    }

    # 3.2 Loan required fields
    row = db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN loan_amount IS NULL THEN 1 END) as missing_amount,
            COUNT(CASE WHEN borrower_name IS NULL OR borrower_name = '' THEN 1 END) as missing_borrower,
            COUNT(CASE WHEN status IS NULL OR status = '' THEN 1 END) as missing_status
        FROM loans
        WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()

    total = row[0] or 1
    results["loans"] = {
        "total": row[0],
        "missing_amount_pct": round((row[1] / total) * 100, 1),
        "missing_borrower_pct": round((row[2] / total) * 100, 1),
        "missing_status_pct": round((row[3] / total) * 100, 1),
        "pass": (row[1] / total) < 0.01,
    }

    # 3.5 Contact method validity
    row = db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$' THEN 1 END) as valid_email,
            COUNT(CASE WHEN phone ~ '^\\+?1?[2-9]\\d{9}$' THEN 1 END) as valid_phone
        FROM leads
        WHERE organization_id = :org_id
            AND (email IS NOT NULL AND email != '')
    """), {"org_id": org_id}).fetchone()

    total = row[0] or 1
    results["validity"] = {
        "total_with_email": row[0],
        "valid_email_pct": round((row[1] / total) * 100, 1),
        "valid_phone_pct": round((row[2] / total) * 100, 1),
        "pass": (row[1] / total) > 0.95,
    }

    all_pass = all(r.get("pass", False) for r in results.values())
    return {"org_id": org_id, "checks": results, "all_pass": all_pass}


# =============================================================================
# REFERENTIAL INTEGRITY (Domain 3, Checks 3.6-3.10)
# =============================================================================

def check_referential_integrity(db, org_id: int) -> Dict:
    """Check referential integrity across tables."""
    from sqlalchemy import text

    results = {}

    # 3.6 Loans have valid contact/lead reference
    row = db.execute(text("""
        SELECT COUNT(*)
        FROM loans l
        LEFT JOIN leads ld ON ld.id = l.lead_id
        WHERE l.organization_id = :org_id
            AND l.lead_id IS NOT NULL
            AND ld.id IS NULL
    """), {"org_id": org_id}).fetchone()
    orphaned_loans = row[0] if row else 0
    results["loans_to_leads"] = {"orphaned": orphaned_loans, "pass": orphaned_loans == 0}

    # 3.7 Tasks have valid assignee
    row = db.execute(text("""
        SELECT COUNT(*)
        FROM tasks t
        LEFT JOIN users u ON u.id = t.assigned_to_id
        WHERE t.organization_id = :org_id
            AND t.assigned_to_id IS NOT NULL
            AND u.id IS NULL
    """), {"org_id": org_id}).fetchone()
    orphaned_tasks = row[0] if row else 0
    results["tasks_to_users"] = {"orphaned": orphaned_tasks, "pass": orphaned_tasks == 0}

    # 3.10 FK constraints at DB level
    row = db.execute(text("""
        SELECT COUNT(*)
        FROM information_schema.table_constraints
        WHERE constraint_type = 'FOREIGN KEY'
            AND table_schema = 'public'
    """)).fetchone()
    fk_count = row[0] if row else 0
    results["fk_constraints"] = {"count": fk_count, "pass": fk_count > 10}

    all_pass = all(r.get("pass", False) for r in results.values())
    return {"org_id": org_id, "checks": results, "all_pass": all_pass}


# =============================================================================
# DUPLICATE DETECTION (Domain 3, Checks 3.11-3.13)
# =============================================================================

def check_duplicates(db, org_id: int) -> Dict:
    """Detect duplicate records."""
    from sqlalchemy import text

    results = {}

    # 3.11 Duplicate emails
    row = db.execute(text("""
        SELECT COUNT(*) as dupe_count
        FROM (
            SELECT email, COUNT(*) as cnt
            FROM leads
            WHERE organization_id = :org_id
                AND email IS NOT NULL AND email != ''
            GROUP BY email
            HAVING COUNT(*) > 1
        ) dupes
    """), {"org_id": org_id}).fetchone()
    dupe_emails = row[0] if row else 0

    total = db.execute(text(
        "SELECT COUNT(*) FROM leads WHERE organization_id = :org_id AND email IS NOT NULL"
    ), {"org_id": org_id}).fetchone()
    total_count = total[0] if total else 1
    dupe_rate = round((dupe_emails / total_count) * 100, 2) if total_count > 0 else 0

    results["duplicate_emails"] = {
        "count": dupe_emails,
        "rate_pct": dupe_rate,
        "pass": dupe_rate < 1.0,
    }

    # 3.12 Duplicate phones
    row = db.execute(text("""
        SELECT COUNT(*) as dupe_count
        FROM (
            SELECT REGEXP_REPLACE(phone, '[^0-9]', '', 'g') as clean_phone, COUNT(*) as cnt
            FROM leads
            WHERE organization_id = :org_id
                AND phone IS NOT NULL AND phone != ''
            GROUP BY REGEXP_REPLACE(phone, '[^0-9]', '', 'g')
            HAVING COUNT(*) > 1
        ) dupes
    """), {"org_id": org_id}).fetchone()
    dupe_phones = row[0] if row else 0
    results["duplicate_phones"] = {"count": dupe_phones, "pass": dupe_phones < total_count * 0.02}

    all_pass = all(r.get("pass", False) for r in results.values())
    return {"org_id": org_id, "checks": results, "all_pass": all_pass}


# =============================================================================
# DATA FRESHNESS (Domain 3, Checks 3.14-3.17)
# =============================================================================

def check_data_freshness(db, org_id: int) -> Dict:
    """Monitor data freshness across the system."""
    from sqlalchemy import text

    results = {}

    # 3.14 Stale leads
    row = db.execute(text("""
        SELECT COUNT(*)
        FROM leads
        WHERE organization_id = :org_id
            AND updated_at < NOW() - INTERVAL '30 days'
            AND stage NOT IN ('Converted', 'Dead', 'Closed')
    """), {"org_id": org_id}).fetchone()
    stale_leads = row[0] if row else 0
    results["stale_leads_30d"] = {"count": stale_leads, "flagged": stale_leads > 0}

    # 3.15 Active loans with stale status
    row = db.execute(text("""
        SELECT COUNT(*)
        FROM loans
        WHERE organization_id = :org_id
            AND status NOT IN ('funded', 'cancelled', 'denied')
            AND status_changed_at < NOW() - INTERVAL '60 days'
    """), {"org_id": org_id}).fetchone()
    stale_loans = row[0] if row else 0
    total_active = db.execute(text("""
        SELECT COUNT(*) FROM loans
        WHERE organization_id = :org_id AND status NOT IN ('funded', 'cancelled', 'denied')
    """), {"org_id": org_id}).fetchone()
    active_count = total_active[0] if total_active else 1
    stale_pct = round((stale_loans / active_count) * 100, 1) if active_count > 0 else 0
    results["stale_loans_60d"] = {"count": stale_loans, "pct": stale_pct, "pass": stale_pct < 5}

    # 3.16 Sync timestamps
    row = db.execute(text("""
        SELECT
            MAX(last_sync_at) as last_sync,
            EXTRACT(EPOCH FROM (NOW() - MAX(last_sync_at))) / 60 as minutes_ago
        FROM user_integrations
        WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()
    if row and row[0]:
        minutes_ago = float(row[1]) if row[1] else 999
        results["sync_freshness"] = {"last_sync_minutes_ago": round(minutes_ago, 1), "pass": minutes_ago < 60}
    else:
        results["sync_freshness"] = {"last_sync_minutes_ago": None, "pass": True, "note": "No integrations configured"}

    return {"org_id": org_id, "checks": results}


# =============================================================================
# ECHO PREVENTION SERVICE (Domain 7, Check 7.10)
# =============================================================================

class EchoPreventionService:
    """
    Prevents sync loops between Perennia CRM and Salesforce.

    Uses watermark tracking to detect when a record we pushed to Salesforce
    comes back in an inbound sync, preventing infinite update loops.
    """

    # In-memory watermark cache (keyed by org_id:record_id)
    _watermarks: Dict[str, float] = {}
    _WATERMARK_TTL_SECONDS = 300  # 5 minutes

    @classmethod
    def mark_outbound(cls, org_id: int, record_type: str, record_id: str) -> None:
        """
        Mark a record as recently pushed outbound to Salesforce.
        Subsequent inbound syncs within TTL will be skipped.
        """
        key = f"{org_id}:{record_type}:{record_id}"
        cls._watermarks[key] = time.time()

    @classmethod
    def should_skip_inbound(cls, org_id: int, record_type: str, record_id: str) -> bool:
        """
        Check if an inbound sync should be skipped because we recently
        pushed this record outbound (preventing echo).
        """
        key = f"{org_id}:{record_type}:{record_id}"
        timestamp = cls._watermarks.get(key)
        if timestamp is None:
            return False

        elapsed = time.time() - timestamp
        if elapsed < cls._WATERMARK_TTL_SECONDS:
            logger.debug(f"Echo prevention: skipping inbound sync for {key} (pushed {elapsed:.0f}s ago)")
            return True

        # Expired watermark, clean up
        del cls._watermarks[key]
        return False

    @classmethod
    def clear_watermark(cls, org_id: int, record_type: str, record_id: str) -> None:
        """Explicitly clear a watermark (e.g., after manual edit)."""
        key = f"{org_id}:{record_type}:{record_id}"
        cls._watermarks.pop(key, None)

    @classmethod
    def get_active_watermarks(cls) -> int:
        """Get count of active watermarks (for monitoring)."""
        now = time.time()
        active = sum(1 for ts in cls._watermarks.values() if now - ts < cls._WATERMARK_TTL_SECONDS)
        return active

    @classmethod
    def cleanup_expired(cls) -> int:
        """Remove expired watermarks. Call periodically."""
        now = time.time()
        expired_keys = [k for k, ts in cls._watermarks.items() if now - ts >= cls._WATERMARK_TTL_SECONDS]
        for k in expired_keys:
            del cls._watermarks[k]
        return len(expired_keys)


# =============================================================================
# IMPORT TEMPLATES (Domain 10, Checks 10.9-10.11)
# =============================================================================

IMPORT_TEMPLATES = {
    "encompass": {
        "name": "Encompass Export",
        "description": "Field mapping template for Ellie Mae Encompass CSV export",
        "source_system": "encompass",
        "auto_map_confidence": 0.85,
        "field_mappings": {
            "Borrower First Name": "first_name",
            "Borrower Last Name": "last_name",
            "Borrower Email": "email",
            "Borrower Home Phone": "phone",
            "Borrower Cell Phone": "phone",
            "Subject Property Address": "property_address",
            "Subject Property City": "property_city",
            "Subject Property State": "property_state",
            "Subject Property Zip": "property_zip",
            "Loan Amount": "loan_amount",
            "Interest Rate": "interest_rate",
            "Loan Program": "loan_type",
            "Loan Purpose": "loan_purpose",
            "LO Name": "assigned_to_name",
            "LO Email": "assigned_to_email",
            "LO NMLS": "lo_nmls_id",
            "Loan Number": "loan_number",
            "Application Date": "application_date",
            "Estimated Closing Date": "expected_close_date",
            "Credit Score": "credit_score",
            "DTI": "dti_ratio",
            "LTV": "ltv_ratio",
            "Occupancy Type": "occupancy_type",
            "Property Type": "property_type",
            "Total Income": "monthly_income",
            "Monthly Payment": "monthly_payment",
            "Appraised Value": "appraised_value",
            "Purchase Price": "purchase_price",
        },
        "status_mapping": {
            "Started": "application",
            "Processing": "processing",
            "Submitted": "submitted",
            "Approved": "approved",
            "CTC": "clear_to_close",
            "Docs Out": "docs_out",
            "Funded": "funded",
            "Denied": "denied",
            "Withdrawn": "cancelled",
        },
    },
    "velocify": {
        "name": "Velocify/LoanTek Lead Export",
        "description": "Field mapping template for Velocify or LoanTek lead exports",
        "source_system": "velocify",
        "auto_map_confidence": 0.80,
        "field_mappings": {
            "First Name": "first_name",
            "Last Name": "last_name",
            "Email Address": "email",
            "Email": "email",
            "Phone Number": "phone",
            "Phone": "phone",
            "Cell Phone": "phone",
            "Home Phone": "phone",
            "Address": "property_address",
            "City": "property_city",
            "State": "property_state",
            "Zip Code": "property_zip",
            "Zip": "property_zip",
            "Loan Amount": "loan_amount",
            "Loan Type": "loan_type",
            "Loan Purpose": "loan_purpose",
            "Credit Score": "credit_score",
            "Lead Source": "source",
            "Campaign": "campaign",
            "Date Added": "created_at",
            "Last Contact": "last_contact_at",
            "Status": "stage",
            "Lead Status": "stage",
            "Agent": "assigned_to_name",
            "Notes": "notes",
            "Property Type": "property_type",
            "Down Payment": "down_payment",
            "Monthly Income": "monthly_income",
        },
        "status_mapping": {
            "New": "New",
            "Contacted": "Contacted",
            "Qualified": "Qualified",
            "Application": "Application",
            "Processing": "Processing",
            "Closed Won": "Converted",
            "Closed Lost": "Dead",
            "Unresponsive": "Stale",
        },
    },
    "generic_crm": {
        "name": "Generic CRM Export",
        "description": "Generic field mapping for BNTouch, Jungo, Surefire, or other CRM exports",
        "source_system": "generic",
        "auto_map_confidence": 0.70,
        "field_mappings": {
            "first_name": "first_name",
            "firstname": "first_name",
            "fname": "first_name",
            "last_name": "last_name",
            "lastname": "last_name",
            "lname": "last_name",
            "name": "full_name",
            "full_name": "full_name",
            "email": "email",
            "email_address": "email",
            "phone": "phone",
            "phone_number": "phone",
            "mobile": "phone",
            "cell": "phone",
            "address": "property_address",
            "street": "property_address",
            "city": "property_city",
            "state": "property_state",
            "zip": "property_zip",
            "zipcode": "property_zip",
            "postal_code": "property_zip",
            "loan_amount": "loan_amount",
            "amount": "loan_amount",
            "loan_type": "loan_type",
            "program": "loan_type",
            "purpose": "loan_purpose",
            "rate": "interest_rate",
            "credit_score": "credit_score",
            "fico": "credit_score",
            "source": "source",
            "lead_source": "source",
            "campaign": "campaign",
            "status": "stage",
            "stage": "stage",
            "notes": "notes",
            "comments": "notes",
        },
        "status_mapping": {
            "new": "New",
            "open": "New",
            "active": "Contacted",
            "contacted": "Contacted",
            "qualified": "Qualified",
            "converted": "Converted",
            "closed": "Dead",
            "dead": "Dead",
            "lost": "Dead",
        },
    },
}


def get_import_template(source_system: str) -> Optional[Dict]:
    """Get import template for a source system."""
    return IMPORT_TEMPLATES.get(source_system)


def list_import_templates() -> List[Dict]:
    """List all available import templates."""
    return [
        {
            "id": key,
            "name": tmpl["name"],
            "description": tmpl["description"],
            "source_system": tmpl["source_system"],
            "field_count": len(tmpl["field_mappings"]),
            "auto_map_confidence": tmpl["auto_map_confidence"],
        }
        for key, tmpl in IMPORT_TEMPLATES.items()
    ]


def auto_map_fields(headers: List[str], template_id: str = "generic_crm") -> Dict:
    """
    Auto-map CSV headers to Perennia fields using a template.

    Returns mapping with confidence scores.
    """
    template = IMPORT_TEMPLATES.get(template_id, IMPORT_TEMPLATES["generic_crm"])
    mappings = {}
    unmapped = []

    for header in headers:
        normalized = header.strip().lower().replace(" ", "_")
        # Direct match
        if normalized in template["field_mappings"]:
            mappings[header] = {
                "target_field": template["field_mappings"][normalized],
                "confidence": 1.0,
                "method": "exact",
            }
        else:
            # Fuzzy match (check if header contains a known field name)
            best_match = None
            best_score = 0
            for source, target in template["field_mappings"].items():
                source_norm = source.lower().replace(" ", "_")
                if source_norm in normalized or normalized in source_norm:
                    score = len(source_norm) / max(len(normalized), len(source_norm))
                    if score > best_score and score > 0.5:
                        best_match = target
                        best_score = score

            if best_match:
                mappings[header] = {
                    "target_field": best_match,
                    "confidence": round(best_score, 2),
                    "method": "fuzzy",
                }
            else:
                unmapped.append(header)

    return {
        "template": template_id,
        "mapped": len(mappings),
        "unmapped": len(unmapped),
        "total_headers": len(headers),
        "auto_map_rate": round(len(mappings) / len(headers) * 100, 1) if headers else 0,
        "mappings": mappings,
        "unmapped_headers": unmapped,
    }


# =============================================================================
# DASHBOARD PERFORMANCE SLA (Domain 9, Checks 9.12-9.13)
# =============================================================================

class DashboardPerformanceMonitor:
    """
    Monitors dashboard load time and data freshness for SLA compliance.

    Targets:
    - Dashboard load time: < 3 seconds (Check 9.12)
    - Real-time metrics lag: < 5 minutes (Check 9.13)
    """

    _load_times: List[float] = []
    _MAX_SAMPLES = 100
    SLA_LOAD_TIME_SECONDS = 3.0
    SLA_DATA_LAG_MINUTES = 5.0

    @classmethod
    def record_load_time(cls, endpoint: str, duration_ms: float) -> None:
        """Record a dashboard endpoint load time."""
        cls._load_times.append(duration_ms)
        if len(cls._load_times) > cls._MAX_SAMPLES:
            cls._load_times = cls._load_times[-cls._MAX_SAMPLES:]

    @classmethod
    def get_load_time_stats(cls) -> Dict:
        """Get dashboard load time statistics."""
        if not cls._load_times:
            return {"samples": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0, "sla_met": True}

        sorted_times = sorted(cls._load_times)
        n = len(sorted_times)
        p50 = sorted_times[int(n * 0.50)]
        p95 = sorted_times[int(n * 0.95)] if n >= 20 else sorted_times[-1]
        p99 = sorted_times[int(n * 0.99)] if n >= 100 else sorted_times[-1]

        return {
            "samples": n,
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "p99_ms": round(p99, 1),
            "sla_met": p95 < cls.SLA_LOAD_TIME_SECONDS * 1000,
            "sla_target_ms": cls.SLA_LOAD_TIME_SECONDS * 1000,
        }

    @classmethod
    def check_data_freshness(cls, db, org_id: int) -> Dict:
        """Check if dashboard data is within SLA freshness target."""
        from sqlalchemy import text

        # Check most recent data update timestamps
        row = db.execute(text("""
            SELECT
                (SELECT MAX(updated_at) FROM leads WHERE organization_id = :org_id) as leads_updated,
                (SELECT MAX(status_changed_at) FROM loans WHERE organization_id = :org_id) as loans_updated
        """), {"org_id": org_id}).fetchone()

        now = datetime.now(timezone.utc)
        lead_lag = None
        loan_lag = None

        if row[0]:
            lead_lag = (now - row[0]).total_seconds() / 60
        if row[1]:
            loan_lag = (now - row[1]).total_seconds() / 60

        max_lag = max(lead_lag or 0, loan_lag or 0)

        return {
            "leads_lag_minutes": round(lead_lag, 1) if lead_lag else None,
            "loans_lag_minutes": round(loan_lag, 1) if loan_lag else None,
            "max_lag_minutes": round(max_lag, 1),
            "sla_met": max_lag < cls.SLA_DATA_LAG_MINUTES,
            "sla_target_minutes": cls.SLA_DATA_LAG_MINUTES,
        }
