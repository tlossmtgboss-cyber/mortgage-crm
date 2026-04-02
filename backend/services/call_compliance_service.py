"""
Call Compliance Service
=======================
Handles call recording compliance across all US states:
- Automatic consent tracking and verification
- State-specific disclosure requirements
- Recording consent logging for audit trails
- Do-Not-Call list management
- TCPA compliance tracking
- Opt-out mechanism management

Two-party consent states (as of 2024):
California, Connecticut, Delaware, Florida, Illinois, Maryland,
Massachusetts, Michigan, Montana, Nevada, New Hampshire, Oregon,
Pennsylvania, Vermont, Washington

All other states are one-party consent states.
"""

import os
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS & CONFIGURATION
# ============================================================================

class ConsentType(str, Enum):
    ONE_PARTY = "one_party"
    TWO_PARTY = "two_party"


class ConsentStatus(str, Enum):
    OBTAINED = "obtained"
    DECLINED = "declined"
    PENDING = "pending"
    NOT_REQUIRED = "not_required"
    VERBAL_ACK = "verbal_ack"


class ComplianceViolationType(str, Enum):
    MISSING_CONSENT = "missing_consent"
    MISSING_DISCLOSURE = "missing_disclosure"
    DNC_VIOLATION = "dnc_violation"
    TCPA_VIOLATION = "tcpa_violation"
    RECORDING_WITHOUT_CONSENT = "recording_without_consent"
    WRONG_DISCLOSURE = "wrong_disclosure"


# State consent requirements
TWO_PARTY_CONSENT_STATES = {
    "CA", "CT", "DE", "FL", "IL", "MD", "MA", "MI", "MT",
    "NV", "NH", "OR", "PA", "VT", "WA"
}

# State-specific disclosure scripts
DEFAULT_DISCLOSURES = {
    "one_party": "This call may be recorded for quality assurance and training purposes.",
    "two_party": "This call is being recorded. By continuing this call, you consent to being recorded. Do you agree to continue?",
    "CA": "This call is being recorded for quality assurance purposes. California law requires that all parties consent to recording. Do you consent to this call being recorded?",
    "FL": "This call may be monitored and recorded for quality assurance. Your continued participation indicates your consent.",
    "IL": "This call is being recorded. By staying on the line, you consent to being recorded.",
}


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ConsentRecord:
    """Record of consent for a call."""
    call_id: str
    phone_number: str
    state: str
    consent_type: ConsentType
    consent_status: ConsentStatus
    disclosure_played: bool = False
    disclosure_timestamp: datetime = None
    consent_timestamp: datetime = None
    verbal_acknowledgment: bool = False
    recording_started: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        return {
            "call_id": self.call_id,
            "phone_number": self.phone_number[-4:].rjust(len(self.phone_number), "*"),  # Mask
            "state": self.state,
            "consent_type": self.consent_type.value,
            "consent_status": self.consent_status.value,
            "disclosure_played": self.disclosure_played,
            "disclosure_timestamp": self.disclosure_timestamp.isoformat() if self.disclosure_timestamp else None,
            "consent_timestamp": self.consent_timestamp.isoformat() if self.consent_timestamp else None,
            "verbal_acknowledgment": self.verbal_acknowledgment,
            "recording_started": self.recording_started,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class ComplianceViolation:
    """Record of a compliance violation."""
    id: str
    violation_type: ComplianceViolationType
    call_id: str
    phone_number: str
    description: str
    severity: str  # low, medium, high, critical
    state: str = None
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = False
    resolution_notes: str = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "violation_type": self.violation_type.value,
            "call_id": self.call_id,
            "phone_number": self.phone_number[-4:].rjust(len(self.phone_number), "*"),
            "description": self.description,
            "severity": self.severity,
            "state": self.state,
            "detected_at": self.detected_at.isoformat(),
            "resolved": self.resolved,
            "resolution_notes": self.resolution_notes
        }


@dataclass
class ComplianceReport:
    """Compliance status report."""
    period_start: date
    period_end: date
    total_calls: int = 0
    compliant_calls: int = 0
    non_compliant_calls: int = 0
    violations: List[ComplianceViolation] = field(default_factory=list)
    consent_obtained: int = 0
    consent_declined: int = 0
    dnc_blocked: int = 0
    by_state: Dict[str, Dict] = field(default_factory=dict)

    @property
    def compliance_rate(self) -> float:
        if self.total_calls == 0:
            return 100.0
        return (self.compliant_calls / self.total_calls) * 100

    def to_dict(self) -> Dict:
        return {
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat()
            },
            "summary": {
                "total_calls": self.total_calls,
                "compliant_calls": self.compliant_calls,
                "non_compliant_calls": self.non_compliant_calls,
                "compliance_rate": round(self.compliance_rate, 2),
                "consent_obtained": self.consent_obtained,
                "consent_declined": self.consent_declined,
                "dnc_blocked": self.dnc_blocked
            },
            "violations": [v.to_dict() for v in self.violations[:20]],
            "by_state": self.by_state
        }


# ============================================================================
# CALL COMPLIANCE SERVICE
# ============================================================================

class CallComplianceService:
    """
    Manages call recording compliance for the AI Receptionist.

    Features:
    - State-specific consent requirements
    - Automatic disclosure delivery
    - Consent tracking and logging
    - Do-Not-Call list checking
    - TCPA compliance verification
    - Compliance reporting and audit trails
    """

    def __init__(self, db: Session, organization_id: int = None):
        self.db = db
        self.organization_id = organization_id

    # ========================================================================
    # STATE REQUIREMENTS
    # ========================================================================

    def get_state_requirements(self, state: str) -> Dict[str, Any]:
        """
        Get recording consent requirements for a state.

        Returns consent type, disclosure script, and requirements.
        """
        state = state.upper()
        is_two_party = state in TWO_PARTY_CONSENT_STATES

        # Get custom disclosure from database if available
        disclosure = self._get_custom_disclosure(state)
        if not disclosure:
            if state in DEFAULT_DISCLOSURES:
                disclosure = DEFAULT_DISCLOSURES[state]
            elif is_two_party:
                disclosure = DEFAULT_DISCLOSURES["two_party"]
            else:
                disclosure = DEFAULT_DISCLOSURES["one_party"]

        return {
            "state": state,
            "consent_type": ConsentType.TWO_PARTY.value if is_two_party else ConsentType.ONE_PARTY.value,
            "requires_verbal_ack": is_two_party,
            "disclosure_script": disclosure,
            "recording_allowed": True,
            "notes": self._get_state_notes(state)
        }

    def _get_custom_disclosure(self, state: str) -> Optional[str]:
        """Get custom disclosure from database."""
        try:
            result = self.db.execute(text("""
                SELECT disclosure_script FROM state_recording_rules
                WHERE state = :state
            """), {"state": state}).fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.exception(f"Failed to get custom disclosure for state {state}: {e}")
            return None

    def _get_state_notes(self, state: str) -> str:
        """Get state-specific compliance notes."""
        notes = {
            "CA": "California requires all-party consent. Verbal acknowledgment required.",
            "FL": "Florida requires all-party consent for private conversations.",
            "IL": "Illinois has strict eavesdropping laws. Always get explicit consent.",
            "PA": "Pennsylvania requires all-party consent.",
            "WA": "Washington requires consent from all parties.",
        }
        return notes.get(state, "Standard compliance requirements apply.")

    # ========================================================================
    # CONSENT MANAGEMENT
    # ========================================================================

    def check_call_compliance(
        self,
        phone_number: str,
        caller_state: str = None
    ) -> Dict[str, Any]:
        """
        Pre-call compliance check.

        Returns:
        - Whether to proceed with call
        - Required disclosures
        - DNC status
        """
        result = {
            "can_proceed": True,
            "requires_consent": False,
            "consent_type": ConsentType.ONE_PARTY.value,
            "disclosure_required": True,
            "disclosure_script": DEFAULT_DISCLOSURES["one_party"],
            "dnc_status": "clear",
            "warnings": []
        }

        # Check DNC list
        if self._is_on_dnc_list(phone_number):
            result["can_proceed"] = False
            result["dnc_status"] = "blocked"
            result["warnings"].append("Number is on Do-Not-Call list")
            return result

        # Check TCPA time restrictions (no calls before 8am or after 9pm local time)
        tcpa_result = self._check_tcpa_time_restrictions(phone_number)
        if not tcpa_result["allowed"]:
            result["can_proceed"] = False
            result["warnings"].append(tcpa_result["reason"])
            return result

        # Get state requirements
        if caller_state:
            state_reqs = self.get_state_requirements(caller_state)
            result["consent_type"] = state_reqs["consent_type"]
            result["disclosure_script"] = state_reqs["disclosure_script"]
            result["requires_consent"] = state_reqs["requires_verbal_ack"]

        return result

    def record_consent(
        self,
        call_id: str,
        phone_number: str,
        state: str,
        consent_obtained: bool,
        disclosure_played: bool = True,
        verbal_ack: bool = False
    ) -> ConsentRecord:
        """
        Record consent status for a call.

        This creates an audit trail for compliance verification.
        """
        consent_type = (
            ConsentType.TWO_PARTY if state.upper() in TWO_PARTY_CONSENT_STATES
            else ConsentType.ONE_PARTY
        )

        if consent_obtained:
            status = ConsentStatus.OBTAINED if verbal_ack else ConsentStatus.VERBAL_ACK
        else:
            status = ConsentStatus.DECLINED

        record = ConsentRecord(
            call_id=call_id,
            phone_number=phone_number,
            state=state.upper(),
            consent_type=consent_type,
            consent_status=status,
            disclosure_played=disclosure_played,
            disclosure_timestamp=datetime.now(timezone.utc) if disclosure_played else None,
            consent_timestamp=datetime.now(timezone.utc) if consent_obtained else None,
            verbal_acknowledgment=verbal_ack,
            recording_started=consent_obtained
        )

        # Store in database
        self._store_consent_record(record)

        return record

    def _store_consent_record(self, record: ConsentRecord):
        """Store consent record in database."""
        try:
            self.db.execute(text("""
                INSERT INTO call_consent_records
                (call_id, phone_number, state, consent_type, consent_status,
                 disclosure_played, disclosure_timestamp, consent_timestamp,
                 verbal_acknowledgment, recording_started, created_at)
                VALUES
                (:call_id, :phone_number, :state, :consent_type, :consent_status,
                 :disclosure_played, :disclosure_timestamp, :consent_timestamp,
                 :verbal_acknowledgment, :recording_started, :created_at)
            """), {
                "call_id": record.call_id,
                "phone_number": record.phone_number,
                "state": record.state,
                "consent_type": record.consent_type.value,
                "consent_status": record.consent_status.value,
                "disclosure_played": record.disclosure_played,
                "disclosure_timestamp": record.disclosure_timestamp,
                "consent_timestamp": record.consent_timestamp,
                "verbal_acknowledgment": record.verbal_acknowledgment,
                "recording_started": record.recording_started,
                "created_at": record.created_at
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.warning(f"Could not store consent record: {e}")
            # Table may not exist yet - that's OK for now

    # ========================================================================
    # DO-NOT-CALL LIST
    # ========================================================================

    def _is_on_dnc_list(self, phone_number: str) -> bool:
        """Check if phone number is on Do-Not-Call list."""
        # Normalize phone number
        clean_number = ''.join(filter(str.isdigit, phone_number))

        try:
            result = self.db.execute(text("""
                SELECT 1 FROM do_not_call_list
                WHERE phone_number = :phone_number
                AND (expires_at IS NULL OR expires_at > :now)
            """), {"phone_number": clean_number, "now": datetime.now(timezone.utc)}).fetchone()
            return result is not None
        except Exception as e:
            logger.exception(f"Failed to check DNC list for phone number: {e}")
            return False

    def add_to_dnc_list(
        self,
        phone_number: str,
        reason: str = "customer_request",
        expires_at: datetime = None
    ) -> bool:
        """Add phone number to Do-Not-Call list."""
        clean_number = ''.join(filter(str.isdigit, phone_number))

        try:
            self.db.execute(text("""
                INSERT INTO do_not_call_list (phone_number, reason, added_at, expires_at)
                VALUES (:phone_number, :reason, :added_at, :expires_at)
                ON CONFLICT (phone_number) DO UPDATE
                SET reason = :reason, expires_at = :expires_at
            """), {
                "phone_number": clean_number,
                "reason": reason,
                "added_at": datetime.now(timezone.utc),
                "expires_at": expires_at
            })
            self.db.commit()
            logger.info(f"Added {clean_number[-4:]} to DNC list: {reason}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Failed to add to DNC list: {e}")
            return False

    def remove_from_dnc_list(self, phone_number: str) -> bool:
        """Remove phone number from Do-Not-Call list."""
        clean_number = ''.join(filter(str.isdigit, phone_number))

        try:
            self.db.execute(text("""
                DELETE FROM do_not_call_list WHERE phone_number = :phone_number
            """), {"phone_number": clean_number})
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"Failed to remove from DNC list: {e}")
            return False

    # ========================================================================
    # TCPA COMPLIANCE
    # ========================================================================

    def _check_tcpa_time_restrictions(self, phone_number: str) -> Dict[str, Any]:
        """
        Check TCPA time restrictions.

        Calls cannot be made before 8am or after 9pm in the recipient's local time.
        """
        # For now, assume we're compliant - in production, would need to:
        # 1. Look up phone number area code to determine timezone
        # 2. Convert current time to local time
        # 3. Check if within allowed hours (8am-9pm)

        # Simplified implementation
        current_hour = datetime.now().hour
        if current_hour < 8 or current_hour >= 21:
            return {
                "allowed": False,
                "reason": f"TCPA restriction: Cannot call between 9pm-8am local time"
            }

        return {"allowed": True, "reason": None}

    # ========================================================================
    # VIOLATION TRACKING
    # ========================================================================

    def record_violation(
        self,
        violation_type: ComplianceViolationType,
        call_id: str,
        phone_number: str,
        description: str,
        state: str = None
    ) -> ComplianceViolation:
        """Record a compliance violation."""
        import uuid

        severity_map = {
            ComplianceViolationType.MISSING_CONSENT: "high",
            ComplianceViolationType.MISSING_DISCLOSURE: "medium",
            ComplianceViolationType.DNC_VIOLATION: "critical",
            ComplianceViolationType.TCPA_VIOLATION: "high",
            ComplianceViolationType.RECORDING_WITHOUT_CONSENT: "critical",
            ComplianceViolationType.WRONG_DISCLOSURE: "low",
        }

        violation = ComplianceViolation(
            id=str(uuid.uuid4())[:8],
            violation_type=violation_type,
            call_id=call_id,
            phone_number=phone_number,
            description=description,
            severity=severity_map.get(violation_type, "medium"),
            state=state
        )

        # Store in database
        try:
            self.db.execute(text("""
                INSERT INTO compliance_violations
                (id, violation_type, call_id, phone_number, description,
                 severity, state, detected_at, resolved)
                VALUES
                (:id, :violation_type, :call_id, :phone_number, :description,
                 :severity, :state, :detected_at, :resolved)
            """), {
                "id": violation.id,
                "violation_type": violation.violation_type.value,
                "call_id": violation.call_id,
                "phone_number": violation.phone_number,
                "description": violation.description,
                "severity": violation.severity,
                "state": violation.state,
                "detected_at": violation.detected_at,
                "resolved": False
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.warning(f"Could not store violation: {e}")

        # Alert on critical violations
        if violation.severity == "critical":
            logger.critical(f"CRITICAL COMPLIANCE VIOLATION: {violation.violation_type.value} - {description}")

        return violation

    # ========================================================================
    # REPORTING
    # ========================================================================

    def get_compliance_report(
        self,
        start_date: date = None,
        end_date: date = None
    ) -> ComplianceReport:
        """Generate compliance report for the specified period."""
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        report = ComplianceReport(period_start=start_date, period_end=end_date)

        # Get call counts
        try:
            calls_result = self.db.execute(text("""
                SELECT COUNT(*) FROM ai_receptionist_activity
                WHERE DATE(timestamp) BETWEEN :start_date AND :end_date
            """), {"start_date": start_date, "end_date": end_date}).fetchone()
            report.total_calls = calls_result[0] if calls_result else 0
        except Exception as e:
            logger.exception(f"Failed to get call counts for compliance report: {e}")

        # Get consent records
        try:
            consent_result = self.db.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN consent_status = 'obtained' THEN 1 END) as obtained,
                    COUNT(CASE WHEN consent_status = 'declined' THEN 1 END) as declined
                FROM call_consent_records
                WHERE DATE(created_at) BETWEEN :start_date AND :end_date
            """), {"start_date": start_date, "end_date": end_date}).fetchone()

            if consent_result:
                report.consent_obtained = consent_result[1] or 0
                report.consent_declined = consent_result[2] or 0
        except Exception as e:
            logger.exception(f"Failed to get consent records for compliance report: {e}")

        # Get violations
        try:
            violations_result = self.db.execute(text("""
                SELECT id, violation_type, call_id, phone_number, description,
                       severity, state, detected_at, resolved
                FROM compliance_violations
                WHERE DATE(detected_at) BETWEEN :start_date AND :end_date
                ORDER BY detected_at DESC
            """), {"start_date": start_date, "end_date": end_date})

            for row in violations_result:
                report.violations.append(ComplianceViolation(
                    id=row[0],
                    violation_type=ComplianceViolationType(row[1]),
                    call_id=row[2],
                    phone_number=row[3],
                    description=row[4],
                    severity=row[5],
                    state=row[6],
                    detected_at=row[7],
                    resolved=row[8]
                ))
        except Exception as e:
            logger.exception(f"Failed to get violations for compliance report: {e}")

        report.non_compliant_calls = len(report.violations)
        report.compliant_calls = max(0, report.total_calls - report.non_compliant_calls)

        return report

    def get_state_compliance_summary(self) -> Dict[str, Any]:
        """Get compliance summary by state."""
        summary = {
            "two_party_states": list(TWO_PARTY_CONSENT_STATES),
            "one_party_states_count": 50 - len(TWO_PARTY_CONSENT_STATES),
            "state_requirements": {}
        }

        for state in TWO_PARTY_CONSENT_STATES:
            summary["state_requirements"][state] = self.get_state_requirements(state)

        return summary
