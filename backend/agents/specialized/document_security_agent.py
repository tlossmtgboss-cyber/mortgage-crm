"""
Document Security Agent

Specialized agent for document security monitoring and enforcement with 15 tools:
1. audit_document_access - Review who accessed which documents and when
2. detect_unusual_access_patterns - Flag anomalous access (bulk downloads, off-hours)
3. verify_document_integrity - Run integrity checks on all documents for a loan
4. check_encryption_status - Verify PII documents are encrypted at rest
5. enforce_retention_policy - Check documents against retention requirements
6. track_document_sharing - Monitor external sharing (email forwards, portal downloads)
7. generate_security_incident_report - Generate incident report for tampering/breach
8. assess_data_exposure_risk - Score a loan's data exposure risk
9. verify_watermark_compliance - Check sensitive documents for proper watermarks
10. audit_user_permissions - Review who has access to what and flag over-privileged users
11. monitor_failed_access_attempts - Track and alert on failed access/auth attempts
12. generate_privacy_impact_assessment - PIA for document handling workflows
13. check_cross_border_data_transfer - Verify compliance for geo-diverse access
14. create_breach_notification_draft - Draft breach notification per state laws
15. generate_security_compliance_report - Monthly security compliance report
"""

import logging
import hashlib
from typing import Any, Dict, Optional, List
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from sqlalchemy import text

logger = logging.getLogger(__name__)

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class AuditDocumentAccessInput(BaseModel):
    """Input schema for audit_document_access tool"""
    loan_id: Optional[int] = Field(None, description="Filter by loan ID")
    user_id: Optional[int] = Field(None, description="Filter by user ID")
    days: int = Field(default=30, description="Number of days to look back")
    limit: int = Field(default=100, description="Maximum results to return")


class DetectUnusualAccessInput(BaseModel):
    """Input schema for detect_unusual_access_patterns tool"""
    user_id: Optional[int] = Field(None, description="Specific user to analyze")
    days: int = Field(default=7, description="Window in days for pattern analysis")
    bulk_threshold: int = Field(default=20, description="Number of downloads to consider bulk")


class VerifyDocumentIntegrityInput(BaseModel):
    """Input schema for verify_document_integrity tool"""
    loan_id: int = Field(..., description="Loan ID to check documents for")


class CheckEncryptionStatusInput(BaseModel):
    """Input schema for check_encryption_status tool"""
    loan_id: Optional[int] = Field(None, description="Specific loan ID or None for org-wide")
    doc_categories: Optional[List[str]] = Field(
        None, description="Document categories to check (e.g., income, identity, credit)"
    )


class EnforceRetentionPolicyInput(BaseModel):
    """Input schema for enforce_retention_policy tool"""
    loan_id: Optional[int] = Field(None, description="Specific loan or None for org-wide")
    include_funded: bool = Field(default=True, description="Include funded/closed loans")


class TrackDocumentSharingInput(BaseModel):
    """Input schema for track_document_sharing tool"""
    loan_id: Optional[int] = Field(None, description="Filter by loan ID")
    days: int = Field(default=30, description="Days to look back")


class GenerateSecurityIncidentInput(BaseModel):
    """Input schema for generate_security_incident_report tool"""
    loan_id: int = Field(..., description="Loan ID involved in the incident")
    incident_type: str = Field(
        ..., description="Type: unauthorized_access, data_breach, document_tampering, "
                         "phishing, insider_threat, lost_device"
    )
    description: str = Field(..., description="Description of the incident")
    affected_documents: Optional[List[str]] = Field(None, description="List of affected document types")
    severity: str = Field(default="high", description="Severity: low, medium, high, critical")


class AssessDataExposureRiskInput(BaseModel):
    """Input schema for assess_data_exposure_risk tool"""
    loan_id: int = Field(..., description="Loan ID to assess")


class VerifyWatermarkComplianceInput(BaseModel):
    """Input schema for verify_watermark_compliance tool"""
    loan_id: int = Field(..., description="Loan ID to check")


class AuditUserPermissionsInput(BaseModel):
    """Input schema for audit_user_permissions tool"""
    user_id: Optional[int] = Field(None, description="Specific user or None for org-wide audit")
    role_filter: Optional[str] = Field(None, description="Filter by role: admin, lo, processor, closer")


class MonitorFailedAccessInput(BaseModel):
    """Input schema for monitor_failed_access_attempts tool"""
    user_id: Optional[int] = Field(None, description="Specific user or None for all")
    days: int = Field(default=7, description="Days to look back")
    threshold: int = Field(default=5, description="Number of failures to flag as suspicious")


class GeneratePrivacyImpactInput(BaseModel):
    """Input schema for generate_privacy_impact_assessment tool"""
    workflow_name: str = Field(..., description="Workflow to assess: document_upload, borrower_portal, "
                                                "email_attachment, third_party_sharing")


class CheckCrossBorderTransferInput(BaseModel):
    """Input schema for check_cross_border_data_transfer tool"""
    loan_id: Optional[int] = Field(None, description="Specific loan or None for org-wide")
    days: int = Field(default=30, description="Days to look back")


class CreateBreachNotificationInput(BaseModel):
    """Input schema for create_breach_notification_draft tool"""
    loan_id: int = Field(..., description="Loan ID affected by the breach")
    breach_type: str = Field(..., description="Type: pii_exposure, ssn_leak, financial_data, identity_docs")
    affected_count: int = Field(default=1, description="Number of affected individuals")
    state_code: str = Field(..., description="State code for notification requirements (e.g., CA, TX, NY)")
    discovery_date: Optional[str] = Field(None, description="Date breach was discovered (YYYY-MM-DD)")


class GenerateSecurityComplianceReportInput(BaseModel):
    """Input schema for generate_security_compliance_report tool"""
    period_days: int = Field(default=30, description="Report period in days")
    include_recommendations: bool = Field(default=True, description="Include improvement recommendations")


# ============================================================================
# PII DOCUMENT CATEGORIES
# ============================================================================

PII_DOCUMENT_TYPES = {
    "identity": ["drivers_license", "ssn_card", "passport"],
    "credit": ["credit_report", "credit_explanation", "bankruptcy_docs"],
    "income": ["tax_returns", "w2", "1099", "paystubs", "profit_loss"],
    "assets": ["bank_statements", "investment_statements"],
}

# Retention periods in years by loan stage
RETENTION_POLICY = {
    "FUNDED": 7,       # 7 years post-funding per GLBA/ECOA
    "CANCELLED": 3,    # 3 years for cancelled applications
    "DENIED": 3,       # 3 years for denied applications (ECOA)
    "DEAD": 2,         # 2 years for dead leads
    "WITHDRAWN": 3,    # 3 years for withdrawn
    "active": 0,       # No expiry while active
}

# State breach notification deadlines (days after discovery)
STATE_NOTIFICATION_DEADLINES = {
    "CA": 45,   # California: "expedient" interpreted as 45 days
    "TX": 60,   # Texas: 60 days
    "NY": 30,   # New York: 30 days (SHIELD Act)
    "FL": 30,   # Florida: 30 days
    "IL": 45,   # Illinois: 45 days (PIPA)
    "VA": 60,   # Virginia: 60 days
    "CO": 30,   # Colorado: 30 days
    "WA": 30,   # Washington: 30 days
    "MA": 14,   # Massachusetts: 14 days (fastest)
    "DEFAULT": 60,
}


# ============================================================================
# DOCUMENT SECURITY AGENT
# ============================================================================

@AgentRegistry.register
class DocumentSecurityAgent(SpecializedAgent):
    """
    Specialized agent for document security monitoring and enforcement.

    Acts as a CISO/DPO for mortgage document handling. Monitors access patterns,
    enforces encryption and retention policies, detects anomalies, and manages
    breach notification workflows. All operations enforce tenant isolation.
    """

    @property
    def name(self) -> str:
        return "DocumentSecurityAgent"

    @property
    def description(self) -> str:
        return ("Monitors document security: access auditing, anomaly detection, "
                "encryption verification, retention enforcement, breach response, "
                "and privacy compliance")

    def _register_tools(self):
        """Register all document security tools"""

        # Tool 1: Audit Document Access
        self.register_tool(AgentTool(
            name="audit_document_access",
            description="Review who accessed which documents and when. Returns a chronological "
                       "access log with user, document, action type, and timestamp. Use for "
                       "compliance audits or investigating suspicious access.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._audit_document_access,
            input_schema=AuditDocumentAccessInput
        ))

        # Tool 2: Detect Unusual Access Patterns
        self.register_tool(AgentTool(
            name="detect_unusual_access_patterns",
            description="Flag anomalous document access patterns including bulk downloads, "
                       "off-hours access, unusual volume spikes, and access to unrelated loans. "
                       "Critical for insider threat detection.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._detect_unusual_access_patterns,
            input_schema=DetectUnusualAccessInput
        ))

        # Tool 3: Verify Document Integrity
        self.register_tool(AgentTool(
            name="verify_document_integrity",
            description="Run integrity checks on all documents for a loan by verifying checksums "
                       "and metadata consistency. Detects tampering or corruption.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._verify_document_integrity,
            input_schema=VerifyDocumentIntegrityInput
        ))

        # Tool 4: Check Encryption Status
        self.register_tool(AgentTool(
            name="check_encryption_status",
            description="Verify all PII documents (SSN, tax returns, credit reports) are "
                       "encrypted at rest. Flags unencrypted sensitive documents for remediation.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_encryption_status,
            input_schema=CheckEncryptionStatusInput
        ))

        # Tool 5: Enforce Retention Policy
        self.register_tool(AgentTool(
            name="enforce_retention_policy",
            description="Check documents against GLBA/ECOA retention requirements. Identifies "
                       "documents past retention that should be archived or deleted, and documents "
                       "that must be retained for regulatory compliance.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.MEDIUM,
            handler=self._enforce_retention_policy,
            input_schema=EnforceRetentionPolicyInput
        ))

        # Tool 6: Track Document Sharing
        self.register_tool(AgentTool(
            name="track_document_sharing",
            description="Monitor external document sharing including email forwards, portal "
                       "downloads, and third-party access. Ensures PII is not being shared "
                       "outside authorized channels.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._track_document_sharing,
            input_schema=TrackDocumentSharingInput
        ))

        # Tool 7: Generate Security Incident Report
        self.register_tool(AgentTool(
            name="generate_security_incident_report",
            description="When tampering, unauthorized access, or a breach is detected, generate "
                       "a formal incident report with timeline, affected data, severity assessment, "
                       "and remediation steps.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._generate_security_incident_report,
            input_schema=GenerateSecurityIncidentInput,
            requires_confirmation=True
        ))

        # Tool 8: Assess Data Exposure Risk
        self.register_tool(AgentTool(
            name="assess_data_exposure_risk",
            description="Score a loan's data exposure risk (0-100) based on sharing patterns, "
                       "access breadth, encryption gaps, and PII sensitivity. Higher scores "
                       "indicate greater risk requiring immediate attention.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._assess_data_exposure_risk,
            input_schema=AssessDataExposureRiskInput
        ))

        # Tool 9: Verify Watermark Compliance
        self.register_tool(AgentTool(
            name="verify_watermark_compliance",
            description="Check that sensitive documents (credit reports, tax returns, SSN-containing "
                       "docs) have proper watermarks applied. Required for audit trail and "
                       "unauthorized redistribution prevention.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._verify_watermark_compliance,
            input_schema=VerifyWatermarkComplianceInput
        ))

        # Tool 10: Audit User Permissions
        self.register_tool(AgentTool(
            name="audit_user_permissions",
            description="Review document access permissions and flag over-privileged users. "
                       "Enforces least-privilege principle by identifying users with broader "
                       "access than their role requires.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._audit_user_permissions,
            input_schema=AuditUserPermissionsInput
        ))

        # Tool 11: Monitor Failed Access Attempts
        self.register_tool(AgentTool(
            name="monitor_failed_access_attempts",
            description="Track and alert on failed document access and authentication attempts. "
                       "Multiple failures from the same user or IP may indicate credential "
                       "stuffing or unauthorized access attempts.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._monitor_failed_access_attempts,
            input_schema=MonitorFailedAccessInput
        ))

        # Tool 12: Generate Privacy Impact Assessment
        self.register_tool(AgentTool(
            name="generate_privacy_impact_assessment",
            description="Generate a Privacy Impact Assessment (PIA) for document handling "
                       "workflows. Evaluates data collection, storage, sharing, and disposal "
                       "practices against GLBA, SOC 2, and state privacy requirements.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_privacy_impact_assessment,
            input_schema=GeneratePrivacyImpactInput
        ))

        # Tool 13: Check Cross-Border Data Transfer
        self.register_tool(AgentTool(
            name="check_cross_border_data_transfer",
            description="If documents are accessed from different geographic locations, verify "
                       "compliance with data residency requirements. Flags access from unexpected "
                       "regions that could indicate compromised credentials.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.MEDIUM,
            handler=self._check_cross_border_data_transfer,
            input_schema=CheckCrossBorderTransferInput
        ))

        # Tool 14: Create Breach Notification Draft
        self.register_tool(AgentTool(
            name="create_breach_notification_draft",
            description="If PII breach is detected, draft notification per state-specific laws. "
                       "Includes notification deadline, required content, AG reporting requirements, "
                       "and credit monitoring obligations.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._create_breach_notification_draft,
            input_schema=CreateBreachNotificationInput,
            requires_confirmation=True
        ))

        # Tool 15: Generate Security Compliance Report
        self.register_tool(AgentTool(
            name="generate_security_compliance_report",
            description="Generate a monthly security compliance report for management covering "
                       "access patterns, incidents, encryption status, retention compliance, "
                       "and risk trends. Aligns with GLBA, SOC 2, and NIST frameworks.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_security_compliance_report,
            input_schema=GenerateSecurityComplianceReportInput
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _audit_document_access(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Review who accessed which documents and when"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            days = input_data.get("days", 30)
            loan_id = input_data.get("loan_id")
            user_id = input_data.get("user_id")
            limit = input_data.get("limit", 100)

            params = {"org_id": org_id, "days": days, "limit": limit}
            filters = [
                "l.organization_id = :org_id",
                "a.created_at >= CURRENT_DATE - :days"
            ]

            if loan_id:
                filters.append("d.loan_id = :loan_id")
                params["loan_id"] = loan_id
            if user_id:
                filters.append("a.user_id = :user_id")
                params["user_id"] = user_id

            where_sql = " AND ".join(filters)

            query = text(f"""
                SELECT
                    a.id, a.type as action_type, a.content,
                    a.created_at,
                    a.user_id,
                    CONCAT(u.first_name, ' ', u.last_name) as user_name,
                    u.role as user_role,
                    d.doc_type, d.doc_category, d.filename,
                    d.loan_id, l.loan_number
                FROM activities a
                JOIN users u ON u.id = a.user_id
                JOIN documents d ON d.loan_id = a.loan_id
                JOIN loans l ON l.id = d.loan_id
                WHERE {where_sql}
                    AND a.type IN ('document_view', 'document_download',
                                   'document_upload', 'document_share',
                                   'document_delete', 'document_print')
                ORDER BY a.created_at DESC
                LIMIT :limit
            """)

            results = db.execute(query, params).fetchall()

            access_log = []
            for r in results:
                access_log.append({
                    "action_id": r.id,
                    "action_type": r.action_type,
                    "user_id": r.user_id,
                    "user_name": r.user_name,
                    "user_role": r.user_role,
                    "doc_type": r.doc_type,
                    "doc_category": r.doc_category,
                    "filename": r.filename,
                    "loan_id": r.loan_id,
                    "loan_number": r.loan_number,
                    "timestamp": r.created_at.isoformat() if r.created_at else None,
                })

            # Summarize by action type
            action_counts = {}
            for entry in access_log:
                action = entry["action_type"]
                action_counts[action] = action_counts.get(action, 0) + 1

            self.audit_log("audit_document_access", details={
                "days": days, "loan_id": loan_id, "user_id": user_id,
                "results_count": len(access_log),
            })

            return ToolResult(
                success=True,
                data={
                    "access_log": access_log,
                    "total_events": len(access_log),
                    "action_summary": action_counts,
                    "period_days": days,
                },
                message=f"{len(access_log)} document access events in the last {days} days"
            )

        except Exception as e:
            logger.exception("audit_document_access failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _detect_unusual_access_patterns(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Flag anomalous document access patterns"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            days = input_data.get("days", 7)
            user_id = input_data.get("user_id")
            bulk_threshold = input_data.get("bulk_threshold", 20)

            params = {"org_id": org_id, "days": days, "bulk_threshold": bulk_threshold}
            user_filter = ""
            if user_id:
                user_filter = "AND a.user_id = :user_id"
                params["user_id"] = user_id

            # Detect bulk downloads per user per day
            bulk_query = text(f"""
                SELECT
                    a.user_id,
                    CONCAT(u.first_name, ' ', u.last_name) as user_name,
                    u.role,
                    DATE(a.created_at) as access_date,
                    COUNT(*) as download_count
                FROM activities a
                JOIN users u ON u.id = a.user_id
                JOIN loans l ON l.id = a.loan_id AND l.organization_id = :org_id
                WHERE a.type IN ('document_download', 'document_print')
                    AND a.created_at >= CURRENT_DATE - :days
                    {user_filter}
                GROUP BY a.user_id, u.first_name, u.last_name, u.role, DATE(a.created_at)
                HAVING COUNT(*) >= :bulk_threshold
                ORDER BY download_count DESC
            """)

            bulk_results = db.execute(bulk_query, params).fetchall()

            # Detect off-hours access (before 6 AM or after 10 PM)
            offhours_query = text(f"""
                SELECT
                    a.user_id,
                    CONCAT(u.first_name, ' ', u.last_name) as user_name,
                    COUNT(*) as offhours_count,
                    MIN(a.created_at) as earliest,
                    MAX(a.created_at) as latest
                FROM activities a
                JOIN users u ON u.id = a.user_id
                JOIN loans l ON l.id = a.loan_id AND l.organization_id = :org_id
                WHERE a.type IN ('document_view', 'document_download',
                                 'document_share', 'document_print')
                    AND a.created_at >= CURRENT_DATE - :days
                    AND (EXTRACT(HOUR FROM a.created_at) < 6
                         OR EXTRACT(HOUR FROM a.created_at) >= 22)
                    {user_filter}
                GROUP BY a.user_id, u.first_name, u.last_name
                HAVING COUNT(*) >= 3
                ORDER BY offhours_count DESC
            """)

            offhours_results = db.execute(offhours_query, params).fetchall()

            # Detect access to unassigned loans
            unassigned_query = text(f"""
                SELECT
                    a.user_id,
                    CONCAT(u.first_name, ' ', u.last_name) as user_name,
                    COUNT(DISTINCT a.loan_id) as foreign_loan_count
                FROM activities a
                JOIN users u ON u.id = a.user_id
                JOIN loans l ON l.id = a.loan_id AND l.organization_id = :org_id
                WHERE a.type IN ('document_view', 'document_download')
                    AND a.created_at >= CURRENT_DATE - :days
                    AND l.loan_officer_id != a.user_id
                    AND u.role NOT IN ('admin', 'manager', 'processor', 'closer')
                    {user_filter}
                GROUP BY a.user_id, u.first_name, u.last_name
                HAVING COUNT(DISTINCT a.loan_id) >= 3
                ORDER BY foreign_loan_count DESC
            """)

            unassigned_results = db.execute(unassigned_query, params).fetchall()

            anomalies = []
            for r in bulk_results:
                anomalies.append({
                    "type": "bulk_download",
                    "severity": "high",
                    "user_id": r.user_id,
                    "user_name": r.user_name,
                    "role": r.role,
                    "detail": f"{r.download_count} downloads on {r.access_date}",
                    "count": r.download_count,
                })

            for r in offhours_results:
                anomalies.append({
                    "type": "off_hours_access",
                    "severity": "medium",
                    "user_id": r.user_id,
                    "user_name": r.user_name,
                    "detail": f"{r.offhours_count} off-hours accesses",
                    "count": r.offhours_count,
                })

            for r in unassigned_results:
                anomalies.append({
                    "type": "unassigned_loan_access",
                    "severity": "high",
                    "user_id": r.user_id,
                    "user_name": r.user_name,
                    "detail": f"Accessed {r.foreign_loan_count} loans not assigned to them",
                    "count": r.foreign_loan_count,
                })

            # Sort by severity
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            anomalies.sort(key=lambda a: severity_order.get(a["severity"], 4))

            self.audit_log("detect_unusual_access_patterns", details={
                "days": days, "anomaly_count": len(anomalies),
            })

            return ToolResult(
                success=True,
                data={
                    "anomalies": anomalies,
                    "total_anomalies": len(anomalies),
                    "high_severity_count": len([a for a in anomalies if a["severity"] in ("high", "critical")]),
                    "period_days": days,
                    "bulk_threshold": bulk_threshold,
                },
                message=f"{len(anomalies)} anomalous access patterns detected in {days} days"
            )

        except Exception as e:
            logger.exception("detect_unusual_access_patterns failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _verify_document_integrity(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Run integrity checks on all documents for a loan"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            loan_id = input_data["loan_id"]
            org_id = self.require_org_id()

            self.verify_loan_tenant(db, loan_id)

            docs = db.execute(text("""
                SELECT
                    d.id, d.doc_type, d.doc_category, d.filename,
                    d.status, d.uploaded_at, d.file_size, d.checksum,
                    d.source
                FROM documents d
                JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                WHERE d.loan_id = :loan_id
                ORDER BY d.uploaded_at DESC
            """), {"loan_id": loan_id, "org_id": org_id}).fetchall()

            if not docs:
                return ToolResult(
                    success=True,
                    data={"loan_id": loan_id, "documents_checked": 0},
                    message=f"No documents found for loan {loan_id}"
                )

            passed = []
            warnings = []
            failures = []

            for d in docs:
                checks = {
                    "doc_id": d.id,
                    "doc_type": d.doc_type,
                    "filename": d.filename,
                }

                # Check 1: File has a checksum on record
                if d.checksum:
                    checks["checksum_present"] = True
                    passed.append({**checks, "check": "checksum_present",
                                   "detail": "Integrity hash on file"})
                else:
                    checks["checksum_present"] = False
                    warnings.append({**checks, "check": "checksum_missing",
                                     "detail": "No integrity hash recorded — cannot verify tampering"})

                # Check 2: File size is reasonable (> 0 and < 100MB)
                if d.file_size and d.file_size > 0:
                    if d.file_size > 100_000_000:
                        warnings.append({**checks, "check": "file_size_large",
                                         "detail": f"File size {d.file_size:,} bytes exceeds 100MB"})
                    else:
                        passed.append({**checks, "check": "file_size_valid",
                                       "detail": f"File size {d.file_size:,} bytes"})
                elif d.file_size == 0:
                    failures.append({**checks, "check": "file_size_zero",
                                     "detail": "Zero-byte file — likely corrupt or incomplete upload"})

                # Check 3: Upload timestamp is valid (not in the future)
                if d.uploaded_at and d.uploaded_at > datetime.utcnow():
                    failures.append({**checks, "check": "timestamp_future",
                                     "detail": "Upload timestamp is in the future — possible clock manipulation"})
                elif d.uploaded_at:
                    passed.append({**checks, "check": "timestamp_valid",
                                   "detail": "Upload timestamp valid"})

                # Check 4: Document status is valid
                valid_statuses = ("active", "archived", "deleted", "pending", "expired")
                if d.status and d.status.lower() not in valid_statuses:
                    warnings.append({**checks, "check": "invalid_status",
                                     "detail": f"Unknown document status: {d.status}"})

            integrity_score = round(
                len(passed) / (len(passed) + len(warnings) + len(failures)) * 100, 1
            ) if (passed or warnings or failures) else 100.0

            self.audit_log("verify_document_integrity", "loan", entity_id=loan_id, details={
                "documents_checked": len(docs),
                "passed": len(passed), "warnings": len(warnings), "failures": len(failures),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "documents_checked": len(docs),
                    "integrity_score": integrity_score,
                    "passed": len(passed),
                    "warnings": len(warnings),
                    "failures": len(failures),
                    "passed_details": passed,
                    "warning_details": warnings,
                    "failure_details": failures,
                },
                message=f"Integrity: {integrity_score}% — {len(failures)} failures, {len(warnings)} warnings across {len(docs)} documents"
            )

        except Exception as e:
            logger.exception("verify_document_integrity failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_encryption_status(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Verify all PII documents are encrypted at rest"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            loan_id = input_data.get("loan_id")
            doc_categories = input_data.get("doc_categories") or list(PII_DOCUMENT_TYPES.keys())

            # Flatten the PII types we need to check
            pii_types = []
            for cat in doc_categories:
                pii_types.extend(PII_DOCUMENT_TYPES.get(cat, []))

            params = {"org_id": org_id, "pii_types": tuple(pii_types) if pii_types else ("__none__",)}
            loan_filter = ""
            if loan_id:
                loan_filter = "AND d.loan_id = :loan_id"
                params["loan_id"] = loan_id

            query = text(f"""
                SELECT
                    d.id, d.doc_type, d.doc_category, d.loan_id,
                    l.loan_number, d.filename,
                    d.encrypted as is_encrypted,
                    d.status
                FROM documents d
                JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                WHERE d.doc_type IN :pii_types
                    AND d.status = 'active'
                    {loan_filter}
                ORDER BY d.doc_category, d.doc_type
            """)

            results = db.execute(query, params).fetchall()

            encrypted = []
            unencrypted = []

            for r in results:
                doc_info = {
                    "doc_id": r.id,
                    "doc_type": r.doc_type,
                    "doc_category": r.doc_category,
                    "loan_id": r.loan_id,
                    "loan_number": r.loan_number,
                    "filename": r.filename,
                }
                if r.is_encrypted:
                    encrypted.append(doc_info)
                else:
                    unencrypted.append(doc_info)

            total = len(encrypted) + len(unencrypted)
            compliance_rate = round(len(encrypted) / total * 100, 1) if total > 0 else 100.0

            self.audit_log("check_encryption_status", details={
                "total_pii_docs": total,
                "encrypted": len(encrypted),
                "unencrypted": len(unencrypted),
            })

            return ToolResult(
                success=True,
                data={
                    "total_pii_documents": total,
                    "encrypted_count": len(encrypted),
                    "unencrypted_count": len(unencrypted),
                    "compliance_rate": compliance_rate,
                    "unencrypted_documents": unencrypted,
                    "categories_checked": doc_categories,
                    "is_compliant": len(unencrypted) == 0,
                },
                message=f"Encryption: {compliance_rate}% compliant — {len(unencrypted)} PII documents unencrypted"
            )

        except Exception as e:
            logger.exception("check_encryption_status failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _enforce_retention_policy(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check documents against retention requirements"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            loan_id = input_data.get("loan_id")
            include_funded = input_data.get("include_funded", True)

            params = {"org_id": org_id}
            loan_filter = ""
            stage_filter = ""

            if loan_id:
                loan_filter = "AND l.id = :loan_id"
                params["loan_id"] = loan_id

            if not include_funded:
                stage_filter = ("AND l.stage NOT IN "
                                "('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')")

            query = text(f"""
                SELECT
                    l.id as loan_id, l.loan_number, l.stage,
                    l.funded_date, l.created_at as loan_created,
                    COUNT(d.id) as doc_count,
                    MIN(d.uploaded_at) as earliest_doc,
                    MAX(d.uploaded_at) as latest_doc
                FROM loans l
                LEFT JOIN documents d ON d.loan_id = l.id AND d.status = 'active'
                WHERE l.organization_id = :org_id
                    {loan_filter}
                    {stage_filter}
                GROUP BY l.id, l.loan_number, l.stage, l.funded_date, l.created_at
                HAVING COUNT(d.id) > 0
                ORDER BY l.funded_date ASC NULLS LAST
            """)

            results = db.execute(query, params).fetchall()

            eligible_for_archive = []
            must_retain = []
            retention_violations = []
            today = date.today()

            for r in results:
                stage = r.stage or "active"
                retention_years = RETENTION_POLICY.get(stage, RETENTION_POLICY.get("active", 0))

                # For terminal stages, calculate retention from funded_date or loan_created
                reference_date = r.funded_date or r.loan_created
                if reference_date and isinstance(reference_date, datetime):
                    reference_date = reference_date.date()

                loan_info = {
                    "loan_id": r.loan_id,
                    "loan_number": r.loan_number,
                    "stage": stage,
                    "doc_count": r.doc_count,
                    "retention_years": retention_years,
                    "reference_date": reference_date.isoformat() if reference_date else None,
                }

                if retention_years == 0:
                    # Active loan — must retain
                    must_retain.append(loan_info)
                elif reference_date:
                    retention_end = reference_date + timedelta(days=retention_years * 365)
                    loan_info["retention_expires"] = retention_end.isoformat()

                    if retention_end < today:
                        loan_info["days_past_retention"] = (today - retention_end).days
                        eligible_for_archive.append(loan_info)
                    else:
                        loan_info["days_until_expiry"] = (retention_end - today).days
                        must_retain.append(loan_info)

                # Check if any documents were prematurely deleted (compliance violation)
                if retention_years > 0 and reference_date:
                    retention_end = reference_date + timedelta(days=retention_years * 365)
                    if retention_end >= today and r.doc_count == 0:
                        retention_violations.append({
                            **loan_info,
                            "violation": "Documents deleted before retention period expired"
                        })

            self.audit_log("enforce_retention_policy", details={
                "loans_checked": len(results),
                "eligible_for_archive": len(eligible_for_archive),
                "violations": len(retention_violations),
            })

            return ToolResult(
                success=True,
                data={
                    "loans_checked": len(results),
                    "eligible_for_archive": eligible_for_archive,
                    "must_retain": must_retain[:50],
                    "retention_violations": retention_violations,
                    "summary": {
                        "archive_eligible": len(eligible_for_archive),
                        "must_retain_count": len(must_retain),
                        "violation_count": len(retention_violations),
                    },
                },
                message=f"Retention: {len(eligible_for_archive)} eligible for archive, "
                        f"{len(retention_violations)} violations"
            )

        except Exception as e:
            logger.exception("enforce_retention_policy failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _track_document_sharing(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Monitor external document sharing"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            loan_id = input_data.get("loan_id")
            days = input_data.get("days", 30)

            params = {"org_id": org_id, "days": days}
            loan_filter = ""
            if loan_id:
                loan_filter = "AND a.loan_id = :loan_id"
                params["loan_id"] = loan_id

            query = text(f"""
                SELECT
                    a.id, a.type as share_type, a.content,
                    a.created_at,
                    a.user_id,
                    CONCAT(u.first_name, ' ', u.last_name) as shared_by,
                    a.loan_id, l.loan_number,
                    l.borrower_name
                FROM activities a
                JOIN users u ON u.id = a.user_id
                JOIN loans l ON l.id = a.loan_id AND l.organization_id = :org_id
                WHERE a.type IN ('document_share', 'document_email', 'document_portal_download',
                                 'document_external_share')
                    AND a.created_at >= CURRENT_DATE - :days
                    {loan_filter}
                ORDER BY a.created_at DESC
            """)

            results = db.execute(query, params).fetchall()

            sharing_events = []
            pii_shares = 0
            external_shares = 0

            for r in results:
                event = {
                    "event_id": r.id,
                    "share_type": r.share_type,
                    "shared_by": r.shared_by,
                    "user_id": r.user_id,
                    "loan_id": r.loan_id,
                    "loan_number": r.loan_number,
                    "borrower": r.borrower_name,
                    "content": (r.content or "")[:200],
                    "timestamp": r.created_at.isoformat() if r.created_at else None,
                }

                # Flag PII-containing shares
                pii_keywords = ["ssn", "tax", "credit_report", "w2", "1099", "bank_statement",
                                "drivers_license", "passport"]
                content_lower = (r.content or "").lower()
                is_pii = any(kw in content_lower for kw in pii_keywords)
                event["contains_pii"] = is_pii
                if is_pii:
                    pii_shares += 1

                if r.share_type in ("document_external_share", "document_email"):
                    external_shares += 1
                    event["is_external"] = True
                else:
                    event["is_external"] = False

                sharing_events.append(event)

            self.audit_log("track_document_sharing", details={
                "events": len(sharing_events),
                "pii_shares": pii_shares,
                "external_shares": external_shares,
            })

            return ToolResult(
                success=True,
                data={
                    "sharing_events": sharing_events,
                    "total_events": len(sharing_events),
                    "pii_sharing_count": pii_shares,
                    "external_sharing_count": external_shares,
                    "period_days": days,
                    "risk_flags": {
                        "pii_externally_shared": pii_shares > 0 and external_shares > 0,
                        "high_volume_sharing": len(sharing_events) > 50,
                    },
                },
                message=f"{len(sharing_events)} sharing events — {pii_shares} PII, {external_shares} external"
            )

        except Exception as e:
            logger.exception("track_document_sharing failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_security_incident_report(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Generate a formal security incident report"""
        from database import SessionLocal
        import uuid

        db = SessionLocal()
        try:
            loan_id = input_data["loan_id"]
            org_id = self.require_org_id()

            self.verify_loan_tenant(db, loan_id)

            incident_type = input_data["incident_type"]
            description = input_data["description"]
            severity = input_data.get("severity", "high")
            affected_documents = input_data.get("affected_documents") or []

            # Get loan details
            loan = db.execute(text("""
                SELECT l.loan_number, l.borrower_name, l.borrower_email,
                       CONCAT(u.first_name, ' ', u.last_name) as lo_name
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get document count for affected types
            doc_count = 0
            if affected_documents:
                result = db.execute(text("""
                    SELECT COUNT(*) as cnt
                    FROM documents d
                    JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                    WHERE d.loan_id = :loan_id
                        AND d.doc_type IN :doc_types
                """), {"loan_id": loan_id, "org_id": org_id,
                       "doc_types": tuple(affected_documents)}).fetchone()
                doc_count = result.cnt if result else 0

            incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
            now = datetime.utcnow()

            # Determine response requirements based on severity
            response_requirements = {
                "critical": {
                    "response_time": "1 hour",
                    "notify": ["CISO", "Legal", "Compliance", "Branch Manager"],
                    "regulatory_report": True,
                    "borrower_notification": True,
                },
                "high": {
                    "response_time": "4 hours",
                    "notify": ["Compliance", "Branch Manager", "IT Security"],
                    "regulatory_report": True,
                    "borrower_notification": True,
                },
                "medium": {
                    "response_time": "24 hours",
                    "notify": ["IT Security", "Compliance"],
                    "regulatory_report": False,
                    "borrower_notification": False,
                },
                "low": {
                    "response_time": "72 hours",
                    "notify": ["IT Security"],
                    "regulatory_report": False,
                    "borrower_notification": False,
                },
            }

            requirements = response_requirements.get(severity, response_requirements["medium"])

            report = {
                "incident_id": incident_id,
                "incident_type": incident_type,
                "severity": severity,
                "status": "open",
                "reported_at": now.isoformat(),
                "reported_by": context.get("user_id"),
                "loan_details": {
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_name": loan.borrower_name,
                    "loan_officer": loan.lo_name,
                },
                "description": description,
                "affected_documents": {
                    "types": affected_documents,
                    "count": doc_count,
                },
                "response_requirements": requirements,
                "remediation_steps": [
                    "1. Immediately revoke access to affected documents",
                    "2. Preserve all audit logs related to the incident",
                    "3. Document the scope of the exposure",
                    "4. Assess whether PII was compromised",
                    "5. Notify affected parties per regulatory requirements",
                    "6. Implement corrective controls to prevent recurrence",
                    "7. Conduct post-incident review within 72 hours",
                ],
                "regulatory_frameworks": ["GLBA Safeguards Rule", "SOC 2 Type II",
                                          "State Data Breach Notification Laws"],
            }

            self.audit_log("generate_security_incident_report", "loan", entity_id=loan_id, details={
                "incident_id": incident_id,
                "incident_type": incident_type,
                "severity": severity,
            })

            return ToolResult(
                success=True,
                data=report,
                message=f"Incident {incident_id} ({severity}) created for loan {loan.loan_number}"
            )

        except Exception as e:
            logger.exception("generate_security_incident_report failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _assess_data_exposure_risk(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Score a loan's data exposure risk"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            loan_id = input_data["loan_id"]
            org_id = self.require_org_id()

            self.verify_loan_tenant(db, loan_id)

            # Get document profile
            doc_profile = db.execute(text("""
                SELECT
                    COUNT(*) as total_docs,
                    COUNT(CASE WHEN d.doc_type IN ('ssn_card', 'drivers_license', 'passport')
                          THEN 1 END) as identity_docs,
                    COUNT(CASE WHEN d.doc_type IN ('tax_returns', 'w2', '1099')
                          THEN 1 END) as tax_docs,
                    COUNT(CASE WHEN d.doc_type = 'credit_report' THEN 1 END) as credit_docs,
                    COUNT(CASE WHEN d.encrypted = true THEN 1 END) as encrypted_count,
                    COUNT(CASE WHEN d.encrypted = false OR d.encrypted IS NULL THEN 1 END) as unencrypted_count
                FROM documents d
                JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                WHERE d.loan_id = :loan_id AND d.status = 'active'
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            # Get access breadth (unique users who accessed)
            access_breadth = db.execute(text("""
                SELECT COUNT(DISTINCT a.user_id) as unique_accessors
                FROM activities a
                JOIN loans l ON l.id = a.loan_id AND l.organization_id = :org_id
                WHERE a.loan_id = :loan_id
                    AND a.type IN ('document_view', 'document_download')
                    AND a.created_at >= CURRENT_DATE - 90
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            # Get sharing count
            sharing_count = db.execute(text("""
                SELECT COUNT(*) as share_count
                FROM activities a
                JOIN loans l ON l.id = a.loan_id AND l.organization_id = :org_id
                WHERE a.loan_id = :loan_id
                    AND a.type IN ('document_share', 'document_email',
                                   'document_external_share')
                    AND a.created_at >= CURRENT_DATE - 90
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            # Calculate risk score (0-100)
            risk_score = 0
            risk_factors = []

            # Factor 1: PII document density (0-25)
            pii_count = (doc_profile.identity_docs or 0) + (doc_profile.tax_docs or 0) + (doc_profile.credit_docs or 0)
            if pii_count >= 5:
                risk_score += 25
                risk_factors.append({"factor": "high_pii_density", "score": 25,
                                     "detail": f"{pii_count} PII-containing documents"})
            elif pii_count >= 2:
                risk_score += 15
                risk_factors.append({"factor": "moderate_pii_density", "score": 15,
                                     "detail": f"{pii_count} PII-containing documents"})

            # Factor 2: Encryption gaps (0-25)
            unenc = doc_profile.unencrypted_count or 0
            if unenc > 0 and pii_count > 0:
                enc_gap_score = min(25, unenc * 5)
                risk_score += enc_gap_score
                risk_factors.append({"factor": "encryption_gaps", "score": enc_gap_score,
                                     "detail": f"{unenc} unencrypted documents"})

            # Factor 3: Access breadth (0-25)
            accessors = access_breadth.unique_accessors or 0
            if accessors > 10:
                risk_score += 25
                risk_factors.append({"factor": "wide_access", "score": 25,
                                     "detail": f"{accessors} unique users accessed documents"})
            elif accessors > 5:
                risk_score += 15
                risk_factors.append({"factor": "moderate_access", "score": 15,
                                     "detail": f"{accessors} unique users accessed documents"})

            # Factor 4: External sharing (0-25)
            shares = sharing_count.share_count or 0
            if shares > 10:
                risk_score += 25
                risk_factors.append({"factor": "high_sharing", "score": 25,
                                     "detail": f"{shares} sharing events in 90 days"})
            elif shares > 3:
                risk_score += 15
                risk_factors.append({"factor": "moderate_sharing", "score": 15,
                                     "detail": f"{shares} sharing events in 90 days"})

            # Determine risk level
            if risk_score >= 75:
                risk_level = "critical"
            elif risk_score >= 50:
                risk_level = "high"
            elif risk_score >= 25:
                risk_level = "medium"
            else:
                risk_level = "low"

            self.audit_log("assess_data_exposure_risk", "loan", entity_id=loan_id, details={
                "risk_score": risk_score, "risk_level": risk_level,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "risk_factors": risk_factors,
                    "document_profile": {
                        "total_docs": doc_profile.total_docs or 0,
                        "identity_docs": doc_profile.identity_docs or 0,
                        "tax_docs": doc_profile.tax_docs or 0,
                        "credit_docs": doc_profile.credit_docs or 0,
                        "encrypted": doc_profile.encrypted_count or 0,
                        "unencrypted": doc_profile.unencrypted_count or 0,
                    },
                    "access_metrics": {
                        "unique_accessors": accessors,
                        "sharing_events": shares,
                    },
                    "recommendations": self._get_risk_recommendations(risk_level, risk_factors),
                },
                message=f"Data exposure risk: {risk_score}/100 ({risk_level})"
            )

        except Exception as e:
            logger.exception("assess_data_exposure_risk failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    @staticmethod
    def _get_risk_recommendations(risk_level: str, risk_factors: List[Dict]) -> List[str]:
        """Generate risk-based recommendations"""
        recommendations = []
        factor_names = {f["factor"] for f in risk_factors}

        if "encryption_gaps" in factor_names:
            recommendations.append("Encrypt all PII documents at rest immediately")
        if "wide_access" in factor_names or "moderate_access" in factor_names:
            recommendations.append("Review and restrict document access permissions to essential users only")
        if "high_sharing" in factor_names or "moderate_sharing" in factor_names:
            recommendations.append("Implement document sharing approval workflow for PII-containing files")
        if "high_pii_density" in factor_names:
            recommendations.append("Enable enhanced audit logging for all PII document access")

        if risk_level == "critical":
            recommendations.insert(0, "IMMEDIATE: Conduct full security review of this loan file")
        elif risk_level == "high":
            recommendations.insert(0, "Schedule security review within 48 hours")

        return recommendations

    async def _verify_watermark_compliance(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check that sensitive documents have proper watermarks"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            loan_id = input_data["loan_id"]
            org_id = self.require_org_id()

            self.verify_loan_tenant(db, loan_id)

            # Documents that should be watermarked
            watermark_required_types = [
                "credit_report", "tax_returns", "w2", "1099",
                "bank_statements", "ssn_card", "drivers_license",
                "appraisal", "title",
            ]

            docs = db.execute(text("""
                SELECT
                    d.id, d.doc_type, d.filename,
                    d.watermarked, d.status
                FROM documents d
                JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                WHERE d.loan_id = :loan_id
                    AND d.doc_type IN :required_types
                    AND d.status = 'active'
                ORDER BY d.doc_type
            """), {
                "loan_id": loan_id, "org_id": org_id,
                "required_types": tuple(watermark_required_types),
            }).fetchall()

            compliant = []
            non_compliant = []

            for d in docs:
                doc_info = {
                    "doc_id": d.id,
                    "doc_type": d.doc_type,
                    "filename": d.filename,
                }
                if d.watermarked:
                    compliant.append(doc_info)
                else:
                    non_compliant.append(doc_info)

            total = len(compliant) + len(non_compliant)
            compliance_rate = round(len(compliant) / total * 100, 1) if total > 0 else 100.0

            self.audit_log("verify_watermark_compliance", "loan", entity_id=loan_id, details={
                "total_checked": total,
                "compliant": len(compliant),
                "non_compliant": len(non_compliant),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "total_checked": total,
                    "compliant_count": len(compliant),
                    "non_compliant_count": len(non_compliant),
                    "compliance_rate": compliance_rate,
                    "non_compliant_documents": non_compliant,
                    "is_compliant": len(non_compliant) == 0,
                },
                message=f"Watermark compliance: {compliance_rate}% — {len(non_compliant)} documents need watermarking"
            )

        except Exception as e:
            logger.exception("verify_watermark_compliance failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _audit_user_permissions(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Review who has access to what and flag over-privileged users"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            user_id = input_data.get("user_id")
            role_filter = input_data.get("role_filter")

            params = {"org_id": org_id}
            filters = ["u.organization_id = :org_id", "u.is_active = true"]

            if user_id:
                filters.append("u.id = :user_id")
                params["user_id"] = user_id
            if role_filter:
                filters.append("u.role = :role_filter")
                params["role_filter"] = role_filter

            where_sql = " AND ".join(filters)

            users = db.execute(text(f"""
                SELECT
                    u.id, CONCAT(u.first_name, ' ', u.last_name) as name,
                    u.role, u.email, u.is_admin,
                    u.last_login,
                    COUNT(DISTINCT l.id) as assigned_loans,
                    COUNT(DISTINCT a.loan_id) as accessed_loans
                FROM users u
                LEFT JOIN loans l ON l.loan_officer_id = u.id
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD',
                                        'WITHDRAWN', 'DOES_NOT_QUALIFY')
                LEFT JOIN activities a ON a.user_id = u.id
                    AND a.type IN ('document_view', 'document_download')
                    AND a.created_at >= CURRENT_DATE - 90
                WHERE {where_sql}
                GROUP BY u.id, u.first_name, u.last_name, u.role, u.email,
                         u.is_admin, u.last_login
                ORDER BY u.role, u.last_name
            """), params).fetchall()

            user_audits = []
            over_privileged = []

            # Expected permissions by role
            expected_access = {
                "lo": {"own_loans_only": True, "admin_panel": False},
                "processor": {"own_loans_only": False, "admin_panel": False},
                "closer": {"own_loans_only": False, "admin_panel": False},
                "manager": {"own_loans_only": False, "admin_panel": True},
                "admin": {"own_loans_only": False, "admin_panel": True},
            }

            for u in users:
                role = u.role or "unknown"
                expected = expected_access.get(role, {"own_loans_only": True, "admin_panel": False})

                audit_entry = {
                    "user_id": u.id,
                    "name": u.name,
                    "role": role,
                    "email": u.email,
                    "is_admin": u.is_admin,
                    "assigned_loans": u.assigned_loans or 0,
                    "accessed_loans_90d": u.accessed_loans or 0,
                    "last_login": u.last_login.isoformat() if u.last_login else None,
                    "flags": [],
                }

                # Flag over-privileged scenarios
                if u.is_admin and role not in ("admin", "manager"):
                    audit_entry["flags"].append({
                        "type": "admin_privilege_mismatch",
                        "severity": "high",
                        "detail": f"User has admin access but role is '{role}'"
                    })
                    over_privileged.append(audit_entry)

                if expected.get("own_loans_only") and (u.accessed_loans or 0) > (u.assigned_loans or 0) + 2:
                    audit_entry["flags"].append({
                        "type": "excessive_loan_access",
                        "severity": "medium",
                        "detail": f"Accessed {u.accessed_loans} loans but only assigned {u.assigned_loans}"
                    })
                    over_privileged.append(audit_entry)

                # Flag dormant accounts with access
                if u.last_login:
                    days_since_login = (datetime.utcnow() - u.last_login).days
                    if days_since_login > 90 and u.is_admin:
                        audit_entry["flags"].append({
                            "type": "dormant_admin",
                            "severity": "high",
                            "detail": f"Admin account inactive for {days_since_login} days"
                        })
                        over_privileged.append(audit_entry)

                user_audits.append(audit_entry)

            # Deduplicate over_privileged (a user could appear multiple times)
            seen_ids = set()
            unique_over_privileged = []
            for entry in over_privileged:
                if entry["user_id"] not in seen_ids:
                    seen_ids.add(entry["user_id"])
                    unique_over_privileged.append(entry)

            self.audit_log("audit_user_permissions", details={
                "users_audited": len(user_audits),
                "over_privileged": len(unique_over_privileged),
            })

            return ToolResult(
                success=True,
                data={
                    "users_audited": len(user_audits),
                    "over_privileged_count": len(unique_over_privileged),
                    "over_privileged_users": unique_over_privileged,
                    "all_users": user_audits,
                    "least_privilege_compliant": len(unique_over_privileged) == 0,
                },
                message=f"Permissions audit: {len(unique_over_privileged)} over-privileged users "
                        f"out of {len(user_audits)} audited"
            )

        except Exception as e:
            logger.exception("audit_user_permissions failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _monitor_failed_access_attempts(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Track and alert on failed document access/auth attempts"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            user_id = input_data.get("user_id")
            days = input_data.get("days", 7)
            threshold = input_data.get("threshold", 5)

            params = {"org_id": org_id, "days": days, "threshold": threshold}
            user_filter = ""
            if user_id:
                user_filter = "AND a.user_id = :user_id"
                params["user_id"] = user_id

            query = text(f"""
                SELECT
                    a.user_id,
                    CONCAT(u.first_name, ' ', u.last_name) as user_name,
                    u.role, u.email,
                    COUNT(*) as failure_count,
                    MIN(a.created_at) as first_failure,
                    MAX(a.created_at) as last_failure,
                    COUNT(DISTINCT a.loan_id) as distinct_loans_attempted
                FROM activities a
                JOIN users u ON u.id = a.user_id AND u.organization_id = :org_id
                WHERE a.type IN ('document_access_denied', 'auth_failure',
                                 'permission_denied', 'document_not_found')
                    AND a.created_at >= CURRENT_DATE - :days
                    {user_filter}
                GROUP BY a.user_id, u.first_name, u.last_name, u.role, u.email
                HAVING COUNT(*) >= :threshold
                ORDER BY failure_count DESC
            """)

            results = db.execute(query, params).fetchall()

            suspicious_users = []
            for r in results:
                severity = "critical" if r.failure_count > threshold * 3 else \
                           "high" if r.failure_count > threshold * 2 else "medium"

                suspicious_users.append({
                    "user_id": r.user_id,
                    "user_name": r.user_name,
                    "role": r.role,
                    "email": r.email,
                    "failure_count": r.failure_count,
                    "distinct_loans_attempted": r.distinct_loans_attempted,
                    "first_failure": r.first_failure.isoformat() if r.first_failure else None,
                    "last_failure": r.last_failure.isoformat() if r.last_failure else None,
                    "severity": severity,
                    "recommended_action": "Lock account and investigate" if severity == "critical"
                                          else "Review access patterns" if severity == "high"
                                          else "Monitor closely",
                })

            self.audit_log("monitor_failed_access_attempts", details={
                "suspicious_users": len(suspicious_users),
                "threshold": threshold, "days": days,
            })

            return ToolResult(
                success=True,
                data={
                    "suspicious_users": suspicious_users,
                    "total_flagged": len(suspicious_users),
                    "critical_count": len([u for u in suspicious_users if u["severity"] == "critical"]),
                    "period_days": days,
                    "threshold": threshold,
                },
                message=f"{len(suspicious_users)} users with suspicious failed access patterns"
            )

        except Exception as e:
            logger.exception("monitor_failed_access_attempts failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_privacy_impact_assessment(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Generate a Privacy Impact Assessment for document workflows"""
        org_id = self.require_org_id()
        workflow_name = input_data["workflow_name"]

        # PIA templates by workflow
        workflow_assessments = {
            "document_upload": {
                "workflow": "Document Upload",
                "data_collected": [
                    "Borrower PII (SSN, DOB, address)",
                    "Financial data (income, assets, debts)",
                    "Government-issued identification",
                    "Credit history and scores",
                ],
                "storage_method": "Encrypted cloud storage (AES-256)",
                "retention_period": "7 years post-loan funding (GLBA requirement)",
                "access_controls": [
                    "Role-based access control (RBAC)",
                    "Multi-factor authentication required",
                    "Audit logging on all access",
                ],
                "sharing_parties": [
                    "Loan officer (assigned)",
                    "Processor (assigned)",
                    "Underwriter (on submission)",
                    "Compliance team (on review)",
                ],
                "risks": [
                    {"risk": "Unauthorized access during upload transit", "likelihood": "low",
                     "impact": "high", "mitigation": "TLS 1.3 encryption in transit"},
                    {"risk": "Over-broad access permissions", "likelihood": "medium",
                     "impact": "medium", "mitigation": "Least-privilege RBAC enforcement"},
                    {"risk": "Document retained past retention period", "likelihood": "medium",
                     "impact": "low", "mitigation": "Automated retention policy enforcement"},
                ],
                "compliance_frameworks": ["GLBA", "SOC 2 Type II", "NIST 800-53", "CCPA/CPRA"],
            },
            "borrower_portal": {
                "workflow": "Borrower Portal Access",
                "data_collected": [
                    "Borrower login credentials",
                    "Document upload/download activity",
                    "IP address and device fingerprint",
                    "Session data",
                ],
                "storage_method": "Encrypted database with session tokens",
                "retention_period": "Session data: 90 days. Documents: 7 years.",
                "access_controls": [
                    "Email-verified authentication",
                    "Session timeout after 30 minutes",
                    "IP-based anomaly detection",
                ],
                "sharing_parties": [
                    "Borrower (self-service)",
                    "Loan officer (view access)",
                ],
                "risks": [
                    {"risk": "Credential compromise via phishing", "likelihood": "medium",
                     "impact": "high", "mitigation": "MFA and suspicious login alerts"},
                    {"risk": "Session hijacking", "likelihood": "low",
                     "impact": "high", "mitigation": "Secure session tokens, CSRF protection"},
                ],
                "compliance_frameworks": ["GLBA", "SOC 2", "State privacy laws"],
            },
            "email_attachment": {
                "workflow": "Email Document Attachment",
                "data_collected": [
                    "Document files with PII",
                    "Email metadata (sender, recipient, timestamp)",
                ],
                "storage_method": "Email server + CRM document storage",
                "retention_period": "7 years (documents), 3 years (email metadata)",
                "access_controls": [
                    "Email encryption (TLS)",
                    "DLP scanning on outbound email",
                    "Approved recipient validation",
                ],
                "sharing_parties": [
                    "Internal team members",
                    "Borrower (via encrypted email)",
                ],
                "risks": [
                    {"risk": "PII sent to wrong recipient", "likelihood": "medium",
                     "impact": "critical", "mitigation": "Recipient verification + DLP alerts"},
                    {"risk": "Unencrypted email with PII", "likelihood": "medium",
                     "impact": "high", "mitigation": "Mandatory TLS, auto-encrypt PII attachments"},
                ],
                "compliance_frameworks": ["GLBA", "SOC 2", "CAN-SPAM", "State breach laws"],
            },
            "third_party_sharing": {
                "workflow": "Third-Party Document Sharing",
                "data_collected": [
                    "Loan documents shared with title, appraisal, insurance vendors",
                    "Borrower PII included in shared packages",
                ],
                "storage_method": "Secure file transfer or vendor portal",
                "retention_period": "Vendor retains per their agreement; we retain 7 years",
                "access_controls": [
                    "Vendor NDA and data processing agreement required",
                    "Time-limited access links",
                    "Watermarking on shared documents",
                ],
                "sharing_parties": [
                    "Title company",
                    "Appraiser",
                    "Insurance provider",
                    "Investor/secondary market",
                ],
                "risks": [
                    {"risk": "Vendor data breach exposes borrower PII", "likelihood": "low",
                     "impact": "critical", "mitigation": "Vendor security audits, DPA requirements"},
                    {"risk": "Documents shared without authorization", "likelihood": "medium",
                     "impact": "high", "mitigation": "Approval workflow for external sharing"},
                ],
                "compliance_frameworks": ["GLBA", "SOC 2", "TRID", "Vendor management policies"],
            },
        }

        assessment = workflow_assessments.get(workflow_name)
        if not assessment:
            return ToolResult(
                success=False,
                error=f"Unknown workflow '{workflow_name}'. Valid workflows: "
                      f"{', '.join(workflow_assessments.keys())}"
            )

        # Add metadata
        assessment["assessment_date"] = datetime.utcnow().isoformat()
        assessment["assessor"] = "DocumentSecurityAgent"
        assessment["organization_id"] = org_id

        # Calculate overall risk rating
        risks = assessment.get("risks", [])
        severity_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        if risks:
            max_impact = max(severity_map.get(r["impact"], 0) for r in risks)
            max_likelihood = max(severity_map.get(r["likelihood"], 0) for r in risks)
            overall_risk = {1: "low", 2: "medium", 3: "high", 4: "critical"}.get(
                max(max_impact, max_likelihood), "medium"
            )
        else:
            overall_risk = "low"

        assessment["overall_risk_rating"] = overall_risk

        self.audit_log("generate_privacy_impact_assessment", details={
            "workflow": workflow_name, "overall_risk": overall_risk,
        })

        return ToolResult(
            success=True,
            data=assessment,
            message=f"PIA for '{workflow_name}': overall risk = {overall_risk}"
        )

    async def _check_cross_border_data_transfer(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check for cross-border/cross-region document access"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            loan_id = input_data.get("loan_id")
            days = input_data.get("days", 30)

            params = {"org_id": org_id, "days": days}
            loan_filter = ""
            if loan_id:
                loan_filter = "AND a.loan_id = :loan_id"
                params["loan_id"] = loan_id

            # Check for access from different IP regions (via activities metadata)
            query = text(f"""
                SELECT
                    a.user_id,
                    CONCAT(u.first_name, ' ', u.last_name) as user_name,
                    a.loan_id, l.loan_number,
                    a.content as access_detail,
                    a.created_at
                FROM activities a
                JOIN users u ON u.id = a.user_id AND u.organization_id = :org_id
                JOIN loans l ON l.id = a.loan_id AND l.organization_id = :org_id
                WHERE a.type IN ('document_view', 'document_download')
                    AND a.created_at >= CURRENT_DATE - :days
                    {loan_filter}
                ORDER BY a.created_at DESC
                LIMIT 500
            """)

            results = db.execute(query, params).fetchall()

            # Group by user and check for geographic diversity
            user_access_patterns = {}
            for r in results:
                uid = r.user_id
                if uid not in user_access_patterns:
                    user_access_patterns[uid] = {
                        "user_name": r.user_name,
                        "loans_accessed": set(),
                        "access_times": [],
                    }
                user_access_patterns[uid]["loans_accessed"].add(r.loan_id)
                user_access_patterns[uid]["access_times"].append(r.created_at)

            # Flag users accessing from multiple rapid time-zone-indicative patterns
            cross_border_flags = []
            for uid, pattern in user_access_patterns.items():
                times = sorted(pattern["access_times"])
                if len(times) >= 2:
                    # Check for impossibly fast geographic shifts
                    # (access within a short window but content suggests different locations)
                    for i in range(1, len(times)):
                        gap_hours = (times[i] - times[i - 1]).total_seconds() / 3600
                        if gap_hours < 0.5 and len(pattern["loans_accessed"]) > 5:
                            cross_border_flags.append({
                                "user_id": uid,
                                "user_name": pattern["user_name"],
                                "detail": f"Rapid access to {len(pattern['loans_accessed'])} "
                                          f"loans within {gap_hours:.1f} hours",
                                "severity": "medium",
                                "loans_accessed_count": len(pattern["loans_accessed"]),
                            })
                            break

            self.audit_log("check_cross_border_data_transfer", details={
                "events_analyzed": len(results),
                "flags": len(cross_border_flags),
            })

            return ToolResult(
                success=True,
                data={
                    "events_analyzed": len(results),
                    "users_analyzed": len(user_access_patterns),
                    "cross_border_flags": cross_border_flags,
                    "flag_count": len(cross_border_flags),
                    "period_days": days,
                    "compliance_note": "US mortgage data should remain within US data centers. "
                                      "Any cross-border transfer requires GLBA compliance review.",
                },
                message=f"Analyzed {len(results)} access events — {len(cross_border_flags)} flags"
            )

        except Exception as e:
            logger.exception("check_cross_border_data_transfer failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _create_breach_notification_draft(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Draft breach notification per state laws"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            loan_id = input_data["loan_id"]
            org_id = self.require_org_id()

            self.verify_loan_tenant(db, loan_id)

            breach_type = input_data["breach_type"]
            affected_count = input_data.get("affected_count", 1)
            state_code = input_data["state_code"].upper()
            discovery_date_str = input_data.get("discovery_date")
            discovery_date = (datetime.fromisoformat(discovery_date_str).date()
                              if discovery_date_str else date.today())

            # Get loan/borrower info
            loan = db.execute(text("""
                SELECT l.loan_number, l.borrower_name, l.borrower_email,
                       l.property_address, l.property_state
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # State-specific notification deadline
            notification_days = STATE_NOTIFICATION_DEADLINES.get(
                state_code, STATE_NOTIFICATION_DEADLINES["DEFAULT"]
            )
            notification_deadline = discovery_date + timedelta(days=notification_days)

            # Determine AG reporting requirement
            ag_report_thresholds = {
                "CA": 500, "NY": 1, "TX": 250, "FL": 500,
                "IL": 500, "MA": 1, "DEFAULT": 500,
            }
            ag_threshold = ag_report_thresholds.get(state_code, ag_report_thresholds["DEFAULT"])
            ag_report_required = affected_count >= ag_threshold

            # Determine credit monitoring obligation
            credit_monitoring_required = breach_type in ("ssn_leak", "identity_docs", "pii_exposure")

            # Draft the notification
            breach_descriptions = {
                "pii_exposure": "personally identifiable information",
                "ssn_leak": "Social Security numbers",
                "financial_data": "financial account information",
                "identity_docs": "government-issued identification documents",
            }
            breach_desc = breach_descriptions.get(breach_type, "personal information")

            notification_draft = {
                "to": loan.borrower_name,
                "subject": f"Important Notice: Data Security Incident — {state_code} Notification",
                "body": (
                    f"Dear {loan.borrower_name},\n\n"
                    f"We are writing to notify you of a data security incident that may have "
                    f"involved your {breach_desc}. We discovered this incident on "
                    f"{discovery_date.strftime('%B %d, %Y')}.\n\n"
                    f"What Happened: During our security monitoring, we identified that "
                    f"{breach_desc} associated with your mortgage application may have been "
                    f"accessed without authorization.\n\n"
                    f"What Information Was Involved: The incident may have involved your "
                    f"{breach_desc} related to loan #{loan.loan_number}.\n\n"
                    f"What We Are Doing: We have taken immediate steps to contain the incident, "
                    f"launched a thorough investigation, and are implementing additional security "
                    f"measures to prevent similar incidents.\n\n"
                ),
            }

            if credit_monitoring_required:
                notification_draft["body"] += (
                    "What You Can Do: We are offering complimentary credit monitoring and "
                    "identity protection services for 12 months. You will receive enrollment "
                    "instructions under separate cover.\n\n"
                )

            notification_draft["body"] += (
                f"For More Information: If you have questions, please contact our dedicated "
                f"incident response line.\n\n"
                f"Sincerely,\n"
                f"Data Security Team"
            )

            self.audit_log("create_breach_notification_draft", "loan", entity_id=loan_id, details={
                "breach_type": breach_type, "state": state_code,
                "affected_count": affected_count,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "state": state_code,
                    "breach_type": breach_type,
                    "discovery_date": discovery_date.isoformat(),
                    "notification_deadline": notification_deadline.isoformat(),
                    "days_until_deadline": (notification_deadline - date.today()).days,
                    "state_requirements": {
                        "notification_window_days": notification_days,
                        "ag_report_required": ag_report_required,
                        "ag_report_threshold": ag_threshold,
                        "credit_monitoring_required": credit_monitoring_required,
                    },
                    "notification_draft": notification_draft,
                    "affected_count": affected_count,
                    "status": "draft_pending_review",
                },
                message=f"Breach notification draft for {state_code} — deadline: "
                        f"{notification_deadline.isoformat()} ({(notification_deadline - date.today()).days} days remaining)"
            )

        except Exception as e:
            logger.exception("create_breach_notification_draft failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_security_compliance_report(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Generate monthly security compliance report"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            period_days = input_data.get("period_days", 30)
            include_recommendations = input_data.get("include_recommendations", True)

            params = {"org_id": org_id, "days": period_days}

            # Section 1: Access statistics
            access_stats = db.execute(text("""
                SELECT
                    COUNT(*) as total_events,
                    COUNT(DISTINCT a.user_id) as unique_users,
                    COUNT(DISTINCT a.loan_id) as unique_loans,
                    COUNT(CASE WHEN a.type = 'document_download' THEN 1 END) as downloads,
                    COUNT(CASE WHEN a.type = 'document_view' THEN 1 END) as views,
                    COUNT(CASE WHEN a.type = 'document_share' THEN 1 END) as shares,
                    COUNT(CASE WHEN a.type IN ('document_access_denied', 'permission_denied')
                          THEN 1 END) as denied
                FROM activities a
                JOIN loans l ON l.id = a.loan_id AND l.organization_id = :org_id
                WHERE a.type LIKE 'document%%'
                    AND a.created_at >= CURRENT_DATE - :days
            """), params).fetchone()

            # Section 2: Document inventory
            doc_inventory = db.execute(text("""
                SELECT
                    COUNT(*) as total_docs,
                    COUNT(CASE WHEN d.encrypted = true THEN 1 END) as encrypted,
                    COUNT(CASE WHEN d.encrypted = false OR d.encrypted IS NULL THEN 1 END) as unencrypted,
                    COUNT(CASE WHEN d.watermarked = true THEN 1 END) as watermarked,
                    COUNT(CASE WHEN d.doc_type IN ('ssn_card', 'drivers_license', 'passport',
                                                   'credit_report', 'tax_returns', 'w2')
                          THEN 1 END) as pii_docs
                FROM documents d
                JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                WHERE d.status = 'active'
            """), params).fetchone()

            # Section 3: Incident count
            incident_count = db.execute(text("""
                SELECT
                    COUNT(*) as total_incidents,
                    COUNT(CASE WHEN ca.severity = 'critical' THEN 1 END) as critical,
                    COUNT(CASE WHEN ca.severity = 'high' THEN 1 END) as high,
                    COUNT(CASE WHEN ca.status = 'open' THEN 1 END) as open_incidents
                FROM compliance_alerts ca
                JOIN loans l ON l.id = ca.loan_id AND l.organization_id = :org_id
                WHERE ca.alert_type LIKE '%%security%%'
                    AND ca.created_at >= CURRENT_DATE - :days
            """), params).fetchone()

            # Section 4: User permission summary
            user_summary = db.execute(text("""
                SELECT
                    COUNT(*) as total_users,
                    COUNT(CASE WHEN u.is_admin = true THEN 1 END) as admin_users,
                    COUNT(CASE WHEN u.last_login < CURRENT_DATE - 90 THEN 1 END) as dormant_users
                FROM users u
                WHERE u.organization_id = :org_id AND u.is_active = true
            """), params).fetchone()

            # Calculate compliance scores
            total_docs = doc_inventory.total_docs or 0
            encryption_compliance = round(
                (doc_inventory.encrypted or 0) / total_docs * 100, 1
            ) if total_docs > 0 else 100.0

            pii_docs = doc_inventory.pii_docs or 0
            watermark_compliance = round(
                (doc_inventory.watermarked or 0) / pii_docs * 100, 1
            ) if pii_docs > 0 else 100.0

            # Overall security score
            scores = [encryption_compliance, watermark_compliance]
            access_denied_rate = round(
                (access_stats.denied or 0) / (access_stats.total_events or 1) * 100, 1
            )
            if access_denied_rate < 5:
                scores.append(90)
            elif access_denied_rate < 15:
                scores.append(70)
            else:
                scores.append(50)

            overall_score = round(sum(scores) / len(scores), 1)

            report = {
                "report_date": datetime.utcnow().isoformat(),
                "period_days": period_days,
                "overall_security_score": overall_score,
                "access_statistics": {
                    "total_events": access_stats.total_events or 0,
                    "unique_users": access_stats.unique_users or 0,
                    "unique_loans": access_stats.unique_loans or 0,
                    "downloads": access_stats.downloads or 0,
                    "views": access_stats.views or 0,
                    "shares": access_stats.shares or 0,
                    "access_denied": access_stats.denied or 0,
                    "denial_rate_pct": access_denied_rate,
                },
                "document_security": {
                    "total_documents": total_docs,
                    "encrypted_count": doc_inventory.encrypted or 0,
                    "unencrypted_count": doc_inventory.unencrypted or 0,
                    "encryption_rate_pct": encryption_compliance,
                    "watermarked_count": doc_inventory.watermarked or 0,
                    "watermark_rate_pct": watermark_compliance,
                    "pii_documents": pii_docs,
                },
                "incidents": {
                    "total": incident_count.total_incidents or 0,
                    "critical": incident_count.critical or 0,
                    "high": incident_count.high or 0,
                    "open": incident_count.open_incidents or 0,
                },
                "user_access": {
                    "total_users": user_summary.total_users or 0,
                    "admin_users": user_summary.admin_users or 0,
                    "dormant_users": user_summary.dormant_users or 0,
                },
                "compliance_frameworks": {
                    "glba": "GLBA Safeguards Rule compliance monitoring active",
                    "soc2": "SOC 2 Type II controls evaluated",
                    "nist": "NIST 800-53 baseline controls applied",
                },
            }

            if include_recommendations:
                recommendations = []
                if encryption_compliance < 100:
                    recommendations.append({
                        "priority": "high",
                        "action": f"Encrypt {doc_inventory.unencrypted or 0} unencrypted documents",
                        "framework": "GLBA Safeguards Rule",
                    })
                if (user_summary.dormant_users or 0) > 0:
                    recommendations.append({
                        "priority": "medium",
                        "action": f"Review and disable {user_summary.dormant_users} dormant accounts",
                        "framework": "SOC 2 CC6.1",
                    })
                if watermark_compliance < 100:
                    recommendations.append({
                        "priority": "medium",
                        "action": "Apply watermarks to all PII-containing documents",
                        "framework": "Internal policy",
                    })
                if access_denied_rate > 10:
                    recommendations.append({
                        "priority": "high",
                        "action": "Investigate high access denial rate — possible unauthorized access attempts",
                        "framework": "NIST 800-53 AC-7",
                    })
                report["recommendations"] = recommendations

            self.audit_log("generate_security_compliance_report", details={
                "overall_score": overall_score, "period_days": period_days,
            })

            return ToolResult(
                success=True,
                data=report,
                message=f"Security compliance report: score {overall_score}/100 "
                        f"({access_stats.total_events or 0} events, "
                        f"{incident_count.total_incidents or 0} incidents)"
            )

        except Exception as e:
            logger.exception("generate_security_compliance_report failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
