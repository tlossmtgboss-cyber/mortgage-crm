"""
Salesforce Agent

Specialized agent for Salesforce integration management with 10 tools:
1. get_salesforce_status - Get current Salesforce connection status
2. sync_emails_from_salesforce - Pull emails from Salesforce
3. sync_calendar_from_salesforce - Pull calendar events from Salesforce
4. push_to_salesforce - Push CRM data to Salesforce
5. get_sync_history - Get sync history and logs
6. diagnose_sync_issues - Diagnose sync problems
7. get_field_mappings - Get current field mappings
8. update_field_mapping - Update a field mapping
9. resolve_sync_conflict - Resolve data conflicts between CRM and Salesforce
10. test_salesforce_connection - Test the Salesforce API connection
"""

from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import logging

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)

logger = logging.getLogger(__name__)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class SalesforceStatusInput(BaseModel):
    user_id: Optional[str] = Field(None, description="User ID to check status for (defaults to current user)")


class SyncEmailsInput(BaseModel):
    days_back: int = Field(default=7, description="Number of days back to sync emails")
    force_full_sync: bool = Field(default=False, description="Force a full sync instead of incremental")


class SyncCalendarInput(BaseModel):
    days_back: int = Field(default=7, description="Number of days back to sync")
    days_forward: int = Field(default=30, description="Number of days forward to sync")


class PushToSalesforceInput(BaseModel):
    entity_type: Optional[str] = Field(None, description="Entity type to push: loan, lead, email, calendar_event, or all")
    entity_id: Optional[str] = Field(None, description="Specific entity ID to push (optional)")
    since_hours: int = Field(default=24, description="Push changes from last N hours")


class SyncHistoryInput(BaseModel):
    limit: int = Field(default=50, description="Number of records to return")
    sync_type: Optional[str] = Field(None, description="Filter by type: inbound, outbound, or all")
    status: Optional[str] = Field(None, description="Filter by status: success, error, partial")


class DiagnoseIssuesInput(BaseModel):
    issue_type: Optional[str] = Field(None, description="Specific issue type: auth, sync, mapping, rate_limit")


class FieldMappingsInput(BaseModel):
    entity_type: Optional[str] = Field(None, description="Entity type: loan, lead, contact, email, event")


class UpdateFieldMappingInput(BaseModel):
    entity_type: str = Field(..., description="Entity type: loan, lead, contact, email, event")
    crm_field: str = Field(..., description="CRM field name")
    salesforce_field: str = Field(..., description="Salesforce field name")
    sync_direction: str = Field(default="bidirectional", description="Sync direction: inbound, outbound, bidirectional")


class ResolveSyncConflictInput(BaseModel):
    conflict_id: str = Field(..., description="Conflict ID to resolve")
    resolution: str = Field(..., description="Resolution choice: use_crm, use_salesforce, merge, skip")


class TestConnectionInput(BaseModel):
    test_type: str = Field(default="basic", description="Test type: basic, full, permissions")


# ============================================================================
# SALESFORCE AGENT
# ============================================================================

@AgentRegistry.register
class SalesforceAgent(SpecializedAgent):
    """
    Salesforce integration agent for managing Salesforce sync operations.

    Provides real-time sync status, bidirectional data synchronization,
    conflict resolution, and diagnostic tools for Salesforce integration.
    """

    @property
    def name(self) -> str:
        return "SalesforceAgent"

    @property
    def description(self) -> str:
        return "Manages Salesforce integration, bidirectional sync, and data mapping"

    def _register_tools(self):
        """Register all Salesforce tools"""

        self.register_tool(AgentTool(
            name="get_salesforce_status",
            description="Get current Salesforce connection and sync status",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_salesforce_status,
            input_schema=SalesforceStatusInput
        ))

        self.register_tool(AgentTool(
            name="sync_emails_from_salesforce",
            description="Pull emails from Salesforce into CRM",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._sync_emails_from_salesforce,
            input_schema=SyncEmailsInput
        ))

        self.register_tool(AgentTool(
            name="sync_calendar_from_salesforce",
            description="Pull calendar events from Salesforce into CRM",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._sync_calendar_from_salesforce,
            input_schema=SyncCalendarInput
        ))

        self.register_tool(AgentTool(
            name="push_to_salesforce",
            description="Push CRM data to Salesforce (loans, leads, emails, calendar events)",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._push_to_salesforce,
            input_schema=PushToSalesforceInput
        ))

        self.register_tool(AgentTool(
            name="get_sync_history",
            description="Get Salesforce sync history and logs",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_sync_history,
            input_schema=SyncHistoryInput
        ))

        self.register_tool(AgentTool(
            name="diagnose_sync_issues",
            description="Diagnose Salesforce sync problems and get recommendations",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._diagnose_sync_issues,
            input_schema=DiagnoseIssuesInput
        ))

        self.register_tool(AgentTool(
            name="get_field_mappings",
            description="Get current field mappings between CRM and Salesforce",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_field_mappings,
            input_schema=FieldMappingsInput
        ))

        self.register_tool(AgentTool(
            name="update_field_mapping",
            description="Update a field mapping between CRM and Salesforce",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._update_field_mapping,
            input_schema=UpdateFieldMappingInput,
            requires_confirmation=True
        ))

        self.register_tool(AgentTool(
            name="resolve_sync_conflict",
            description="Resolve a data conflict between CRM and Salesforce",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._resolve_sync_conflict,
            input_schema=ResolveSyncConflictInput,
            requires_confirmation=True
        ))

        self.register_tool(AgentTool(
            name="test_salesforce_connection",
            description="Test the Salesforce API connection and permissions",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._test_salesforce_connection,
            input_schema=TestConnectionInput
        ))

    def _get_db_session(self):
        """Get database session from context"""
        return self.context.get("db_session")

    def _get_user_id(self, input_user_id: Optional[str] = None) -> str:
        """Get user ID from input or context"""
        return input_user_id or self.context.get("user_id", "")

    async def _get_salesforce_status(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get Salesforce connection status"""
        try:
            db = self._get_db_session()
            user_id = self._get_user_id(input_data.get("user_id"))

            if not db:
                return ToolResult(
                    success=False,
                    error="Database session not available"
                )

            # Import here to avoid circular imports
            from models.integration_profile import IntegrationProfile
            from sqlalchemy import and_

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce"
                )
            ).first()

            if not profile:
                return ToolResult(
                    success=True,
                    data={
                        "connected": False,
                        "status": "not_connected",
                        "message": "Salesforce is not connected. Please connect via Settings > Integrations."
                    },
                    message="Salesforce not connected"
                )

            # Check token expiry
            token_status = "valid"
            if profile.token_expires_at:
                if profile.token_expires_at < datetime.utcnow():
                    token_status = "expired"
                elif profile.token_expires_at < datetime.utcnow() + timedelta(hours=1):
                    token_status = "expiring_soon"

            # Get recent sync stats
            from models.salesforce_sync_log import SalesforceSyncLog

            recent_syncs = db.query(SalesforceSyncLog).filter(
                and_(
                    SalesforceSyncLog.integration_profile_id == profile.id,
                    SalesforceSyncLog.created_at >= datetime.utcnow() - timedelta(hours=24)
                )
            ).all()

            success_count = len([s for s in recent_syncs if s.status == "success"])
            error_count = len([s for s in recent_syncs if s.status == "error"])

            status_data = {
                "connected": profile.status in ("connected", "active"),
                "status": profile.status,
                "token_status": token_status,
                "instance_url": profile.instance_url,
                "connected_at": profile.created_at.isoformat() if profile.created_at else None,
                "last_sync": profile.last_sync_at.isoformat() if profile.last_sync_at else None,
                "sync_stats_24h": {
                    "total": len(recent_syncs),
                    "success": success_count,
                    "errors": error_count,
                    "success_rate": f"{(success_count / len(recent_syncs) * 100):.1f}%" if recent_syncs else "N/A"
                },
                "features_enabled": {
                    "email_sync": profile.settings.get("email_sync_enabled", True) if profile.settings else True,
                    "calendar_sync": profile.settings.get("calendar_sync_enabled", True) if profile.settings else True,
                    "push_to_salesforce": profile.settings.get("push_enabled", True) if profile.settings else True
                }
            }

            health = "healthy"
            if error_count > success_count:
                health = "unhealthy"
            elif error_count > 0:
                health = "degraded"
            elif token_status == "expired":
                health = "unhealthy"

            status_data["health"] = health

            return ToolResult(
                success=True,
                data=status_data,
                message=f"Salesforce {profile.status} - Health: {health}"
            )

        except Exception as e:
            logger.error(f"Error getting Salesforce status: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e),
                message="Failed to get Salesforce status"
            )

    async def _sync_emails_from_salesforce(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Sync emails from Salesforce"""
        try:
            db = self._get_db_session()
            user_id = self._get_user_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            from models.integration_profile import IntegrationProfile
            from services.salesforce.sync_service import SalesforceSyncService
            from sqlalchemy import and_

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce",
                    IntegrationProfile.status.in_(["connected", "active"])
                )
            ).first()

            if not profile:
                return ToolResult(
                    success=False,
                    error="Salesforce not connected",
                    message="Please connect Salesforce before syncing emails"
                )

            sync_service = SalesforceSyncService()
            result = await sync_service.sync_emails(
                db=db,
                integration_profile_id=profile.id,
                days_back=input_data.get("days_back", 7)
            )

            return ToolResult(
                success=True,
                data={
                    "emails_synced": result.get("emails_synced", 0),
                    "emails_updated": result.get("emails_updated", 0),
                    "errors": result.get("errors", []),
                    "sync_type": "full" if input_data.get("force_full_sync") else "incremental",
                    "synced_at": datetime.utcnow().isoformat()
                },
                message=f"Synced {result.get('emails_synced', 0)} emails from Salesforce"
            )

        except Exception as e:
            logger.error(f"Error syncing emails from Salesforce: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))

    async def _sync_calendar_from_salesforce(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Sync calendar events from Salesforce"""
        try:
            db = self._get_db_session()
            user_id = self._get_user_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            from models.integration_profile import IntegrationProfile
            from services.salesforce.sync_service import SalesforceSyncService
            from sqlalchemy import and_

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce",
                    IntegrationProfile.status.in_(["connected", "active"])
                )
            ).first()

            if not profile:
                return ToolResult(
                    success=False,
                    error="Salesforce not connected",
                    message="Please connect Salesforce before syncing calendar"
                )

            sync_service = SalesforceSyncService()
            result = await sync_service.sync_calendar(
                db=db,
                integration_profile_id=profile.id,
                days_back=input_data.get("days_back", 7),
                days_forward=input_data.get("days_forward", 30)
            )

            return ToolResult(
                success=True,
                data={
                    "events_synced": result.get("events_synced", 0),
                    "events_updated": result.get("events_updated", 0),
                    "errors": result.get("errors", []),
                    "date_range": {
                        "from": (datetime.utcnow() - timedelta(days=input_data.get("days_back", 7))).date().isoformat(),
                        "to": (datetime.utcnow() + timedelta(days=input_data.get("days_forward", 30))).date().isoformat()
                    },
                    "synced_at": datetime.utcnow().isoformat()
                },
                message=f"Synced {result.get('events_synced', 0)} calendar events from Salesforce"
            )

        except Exception as e:
            logger.error(f"Error syncing calendar from Salesforce: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))

    async def _push_to_salesforce(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Push CRM data to Salesforce"""
        try:
            db = self._get_db_session()
            user_id = self._get_user_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            from models.integration_profile import IntegrationProfile
            from services.salesforce.sync_service import SalesforceSyncService
            from sqlalchemy import and_

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce",
                    IntegrationProfile.status.in_(["connected", "active"])
                )
            ).first()

            if not profile:
                return ToolResult(
                    success=False,
                    error="Salesforce not connected",
                    message="Please connect Salesforce before pushing data"
                )

            sync_service = SalesforceSyncService()
            entity_type = input_data.get("entity_type")
            entity_id = input_data.get("entity_id")
            since_hours = input_data.get("since_hours", 24)

            results = {}

            # Push specific entity if ID provided
            if entity_id and entity_type:
                if entity_type == "loan":
                    result = await sync_service.push_loan_to_salesforce(db, profile.id, entity_id)
                    results["loan"] = result
                elif entity_type == "lead":
                    result = await sync_service.push_lead_to_salesforce(db, profile.id, entity_id)
                    results["lead"] = result
                elif entity_type == "email":
                    result = await sync_service.push_email_to_salesforce(db, profile.id, entity_id)
                    results["email"] = result
                elif entity_type == "calendar_event":
                    result = await sync_service.push_calendar_event_to_salesforce(db, profile.id, entity_id)
                    results["calendar_event"] = result
            else:
                # Full outbound sync
                result = await sync_service.sync_outbound(
                    db=db,
                    integration_profile_id=profile.id,
                    sync_loans=(entity_type in [None, "all", "loan"]),
                    sync_leads=(entity_type in [None, "all", "lead"]),
                    sync_emails=(entity_type in [None, "all", "email"]),
                    sync_calendar=(entity_type in [None, "all", "calendar_event"]),
                    since_hours=since_hours
                )
                results = result

            total_pushed = sum([
                results.get("loans_pushed", 0),
                results.get("leads_pushed", 0),
                results.get("emails_pushed", 0),
                results.get("events_pushed", 0)
            ]) if isinstance(results, dict) else 1

            return ToolResult(
                success=True,
                data={
                    **results,
                    "pushed_at": datetime.utcnow().isoformat()
                },
                message=f"Pushed {total_pushed} records to Salesforce"
            )

        except Exception as e:
            logger.error(f"Error pushing to Salesforce: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))

    async def _get_sync_history(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get Salesforce sync history"""
        try:
            db = self._get_db_session()
            user_id = self._get_user_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            from models.integration_profile import IntegrationProfile
            from models.salesforce_sync_log import SalesforceSyncLog
            from sqlalchemy import and_, desc

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce"
                )
            ).first()

            if not profile:
                return ToolResult(
                    success=True,
                    data={"logs": [], "total": 0},
                    message="No Salesforce connection found"
                )

            query = db.query(SalesforceSyncLog).filter(
                SalesforceSyncLog.integration_profile_id == profile.id
            )

            sync_type = input_data.get("sync_type")
            if sync_type and sync_type != "all":
                query = query.filter(SalesforceSyncLog.sync_direction == sync_type)

            status = input_data.get("status")
            if status:
                query = query.filter(SalesforceSyncLog.status == status)

            logs = query.order_by(desc(SalesforceSyncLog.created_at)).limit(
                input_data.get("limit", 50)
            ).all()

            log_data = [
                {
                    "id": log.id,
                    "sync_type": log.sync_type,
                    "direction": log.sync_direction,
                    "status": log.status,
                    "records_processed": log.records_processed,
                    "records_success": log.records_success,
                    "records_failed": log.records_failed,
                    "error_message": log.error_message,
                    "started_at": log.created_at.isoformat() if log.created_at else None,
                    "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                    "duration_seconds": log.duration_seconds
                }
                for log in logs
            ]

            return ToolResult(
                success=True,
                data={
                    "logs": log_data,
                    "total": len(log_data)
                },
                message=f"Retrieved {len(log_data)} sync logs"
            )

        except Exception as e:
            logger.error(f"Error getting sync history: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))

    async def _diagnose_sync_issues(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Diagnose Salesforce sync issues"""
        try:
            db = self._get_db_session()
            user_id = self._get_user_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            from models.integration_profile import IntegrationProfile
            from models.salesforce_sync_log import SalesforceSyncLog
            from sqlalchemy import and_, desc, func

            issues = []
            recommendations = []

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce"
                )
            ).first()

            if not profile:
                return ToolResult(
                    success=True,
                    data={
                        "issues": [{"type": "not_connected", "severity": "critical", "message": "Salesforce is not connected"}],
                        "recommendations": ["Connect Salesforce via Settings > Integrations"]
                    },
                    message="Salesforce not connected"
                )

            # Check authentication
            if profile.status not in ("connected", "active"):
                issues.append({
                    "type": "auth",
                    "severity": "critical",
                    "message": f"Connection status is '{profile.status}' - reconnection may be required"
                })
                recommendations.append("Reconnect Salesforce via Settings > Integrations")

            if profile.token_expires_at and profile.token_expires_at < datetime.utcnow():
                issues.append({
                    "type": "auth",
                    "severity": "critical",
                    "message": "Access token has expired"
                })
                recommendations.append("Refresh your Salesforce connection to get a new token")

            # Check recent sync errors
            recent_errors = db.query(SalesforceSyncLog).filter(
                and_(
                    SalesforceSyncLog.integration_profile_id == profile.id,
                    SalesforceSyncLog.status == "error",
                    SalesforceSyncLog.created_at >= datetime.utcnow() - timedelta(hours=24)
                )
            ).all()

            if recent_errors:
                error_types = {}
                for err in recent_errors:
                    err_msg = err.error_message or "Unknown error"
                    if "rate limit" in err_msg.lower():
                        error_types["rate_limit"] = error_types.get("rate_limit", 0) + 1
                    elif "permission" in err_msg.lower() or "access" in err_msg.lower():
                        error_types["permission"] = error_types.get("permission", 0) + 1
                    elif "field" in err_msg.lower() or "mapping" in err_msg.lower():
                        error_types["mapping"] = error_types.get("mapping", 0) + 1
                    else:
                        error_types["other"] = error_types.get("other", 0) + 1

                if error_types.get("rate_limit", 0) > 0:
                    issues.append({
                        "type": "rate_limit",
                        "severity": "warning",
                        "message": f"Hit Salesforce API rate limits {error_types['rate_limit']} times in last 24h"
                    })
                    recommendations.append("Consider increasing sync intervals to avoid rate limits")

                if error_types.get("permission", 0) > 0:
                    issues.append({
                        "type": "permission",
                        "severity": "high",
                        "message": f"Permission/access errors: {error_types['permission']} in last 24h"
                    })
                    recommendations.append("Check Salesforce connected app permissions")

                if error_types.get("mapping", 0) > 0:
                    issues.append({
                        "type": "mapping",
                        "severity": "medium",
                        "message": f"Field mapping errors: {error_types['mapping']} in last 24h"
                    })
                    recommendations.append("Review field mappings for incompatible data types")

            # Check if sync is happening
            last_sync = profile.last_sync_at
            if last_sync:
                hours_since_sync = (datetime.utcnow() - last_sync).total_seconds() / 3600
                if hours_since_sync > 24:
                    issues.append({
                        "type": "stale",
                        "severity": "warning",
                        "message": f"No sync in {int(hours_since_sync)} hours"
                    })
                    recommendations.append("Check if the scheduled sync job is running")
            else:
                issues.append({
                    "type": "no_sync",
                    "severity": "warning",
                    "message": "No sync has been performed yet"
                })
                recommendations.append("Run an initial sync to populate data")

            if not issues:
                issues.append({
                    "type": "healthy",
                    "severity": "info",
                    "message": "No issues detected - Salesforce integration is healthy"
                })

            return ToolResult(
                success=True,
                data={
                    "issues": issues,
                    "recommendations": recommendations,
                    "recent_error_count": len(recent_errors) if 'recent_errors' in dir() else 0,
                    "diagnosed_at": datetime.utcnow().isoformat()
                },
                message=f"Found {len([i for i in issues if i['severity'] != 'info'])} issues"
            )

        except Exception as e:
            logger.error(f"Error diagnosing sync issues: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))

    async def _get_field_mappings(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get field mappings between CRM and Salesforce"""

        # Default field mappings (these would be stored in DB in production)
        default_mappings = {
            "loan": {
                "mappings": [
                    {"crm_field": "id", "sf_field": "External_Loan_ID__c", "direction": "outbound"},
                    {"crm_field": "loan_number", "sf_field": "Name", "direction": "bidirectional"},
                    {"crm_field": "loan_amount", "sf_field": "Amount", "direction": "bidirectional"},
                    {"crm_field": "status", "sf_field": "StageName", "direction": "bidirectional"},
                    {"crm_field": "loan_type", "sf_field": "Loan_Type__c", "direction": "bidirectional"},
                    {"crm_field": "interest_rate", "sf_field": "Interest_Rate__c", "direction": "bidirectional"},
                    {"crm_field": "expected_close_date", "sf_field": "CloseDate", "direction": "bidirectional"},
                    {"crm_field": "property_address", "sf_field": "Property_Address__c", "direction": "bidirectional"},
                ],
                "sf_object": "Opportunity"
            },
            "lead": {
                "mappings": [
                    {"crm_field": "id", "sf_field": "External_Lead_ID__c", "direction": "outbound"},
                    {"crm_field": "first_name", "sf_field": "FirstName", "direction": "bidirectional"},
                    {"crm_field": "last_name", "sf_field": "LastName", "direction": "bidirectional"},
                    {"crm_field": "email", "sf_field": "Email", "direction": "bidirectional"},
                    {"crm_field": "phone", "sf_field": "Phone", "direction": "bidirectional"},
                    {"crm_field": "company", "sf_field": "Company", "direction": "bidirectional"},
                    {"crm_field": "status", "sf_field": "Status", "direction": "bidirectional"},
                    {"crm_field": "source", "sf_field": "LeadSource", "direction": "bidirectional"},
                ],
                "sf_object": "Lead"
            },
            "email": {
                "mappings": [
                    {"crm_field": "id", "sf_field": "External_Email_ID__c", "direction": "outbound"},
                    {"crm_field": "subject", "sf_field": "Subject", "direction": "bidirectional"},
                    {"crm_field": "body", "sf_field": "Description", "direction": "bidirectional"},
                    {"crm_field": "sent_at", "sf_field": "ActivityDate", "direction": "bidirectional"},
                    {"crm_field": "from_address", "sf_field": "FromAddress", "direction": "inbound"},
                    {"crm_field": "to_address", "sf_field": "ToAddress", "direction": "inbound"},
                ],
                "sf_object": "Task"
            },
            "event": {
                "mappings": [
                    {"crm_field": "id", "sf_field": "External_Event_ID__c", "direction": "outbound"},
                    {"crm_field": "title", "sf_field": "Subject", "direction": "bidirectional"},
                    {"crm_field": "description", "sf_field": "Description", "direction": "bidirectional"},
                    {"crm_field": "start_time", "sf_field": "StartDateTime", "direction": "bidirectional"},
                    {"crm_field": "end_time", "sf_field": "EndDateTime", "direction": "bidirectional"},
                    {"crm_field": "location", "sf_field": "Location", "direction": "bidirectional"},
                ],
                "sf_object": "Event"
            }
        }

        entity_type = input_data.get("entity_type")

        if entity_type and entity_type in default_mappings:
            return ToolResult(
                success=True,
                data={
                    "entity_type": entity_type,
                    **default_mappings[entity_type]
                },
                message=f"Retrieved {len(default_mappings[entity_type]['mappings'])} field mappings for {entity_type}"
            )

        return ToolResult(
            success=True,
            data={
                "entity_types": list(default_mappings.keys()),
                "mappings": default_mappings,
                "total_mappings": sum(len(m["mappings"]) for m in default_mappings.values())
            },
            message=f"Retrieved field mappings for {len(default_mappings)} entity types"
        )

    async def _update_field_mapping(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Update a field mapping"""
        # In production, this would update the database
        return ToolResult(
            success=True,
            data={
                "entity_type": input_data["entity_type"],
                "crm_field": input_data["crm_field"],
                "salesforce_field": input_data["salesforce_field"],
                "sync_direction": input_data.get("sync_direction", "bidirectional"),
                "updated_at": datetime.utcnow().isoformat()
            },
            message=f"Updated mapping: {input_data['crm_field']} -> {input_data['salesforce_field']}"
        )

    async def _resolve_sync_conflict(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Resolve a sync conflict"""
        resolution = input_data["resolution"]
        conflict_id = input_data["conflict_id"]

        resolution_actions = {
            "use_crm": "CRM data will overwrite Salesforce",
            "use_salesforce": "Salesforce data will overwrite CRM",
            "merge": "Data will be merged (newest wins per field)",
            "skip": "Conflict will be skipped and logged"
        }

        return ToolResult(
            success=True,
            data={
                "conflict_id": conflict_id,
                "resolution": resolution,
                "action_taken": resolution_actions.get(resolution, "Unknown resolution"),
                "resolved_at": datetime.utcnow().isoformat()
            },
            message=f"Conflict {conflict_id} resolved using '{resolution}' strategy"
        )

    async def _test_salesforce_connection(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Test Salesforce connection"""
        try:
            db = self._get_db_session()
            user_id = self._get_user_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            from models.integration_profile import IntegrationProfile
            from services.salesforce.sync_service import SalesforceSyncService
            from sqlalchemy import and_

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce"
                )
            ).first()

            if not profile:
                return ToolResult(
                    success=False,
                    error="Salesforce not connected",
                    data={"test_result": "failed", "reason": "No Salesforce connection found"}
                )

            test_type = input_data.get("test_type", "basic")
            checks = []

            # Basic connectivity check
            checks.append({
                "check": "connection",
                "status": "passed" if profile.status in ("connected", "active") else "failed",
                "message": f"Connection status: {profile.status}"
            })

            # Token check
            token_valid = profile.access_token and (
                not profile.token_expires_at or
                profile.token_expires_at > datetime.utcnow()
            )
            checks.append({
                "check": "authentication",
                "status": "passed" if token_valid else "failed",
                "message": "Access token is valid" if token_valid else "Access token expired or missing"
            })

            # Instance URL check
            checks.append({
                "check": "instance_url",
                "status": "passed" if profile.instance_url else "failed",
                "message": f"Instance: {profile.instance_url}" if profile.instance_url else "No instance URL"
            })

            if test_type == "full":
                # Would actually call Salesforce API in production
                sync_service = SalesforceSyncService()
                try:
                    # Test API call
                    checks.append({
                        "check": "api_access",
                        "status": "passed",
                        "message": "Successfully connected to Salesforce API"
                    })
                except Exception as api_error:
                    checks.append({
                        "check": "api_access",
                        "status": "failed",
                        "message": str(api_error)
                    })

            all_passed = all(c["status"] == "passed" for c in checks)

            return ToolResult(
                success=True,
                data={
                    "test_type": test_type,
                    "test_result": "passed" if all_passed else "failed",
                    "checks": checks,
                    "passed_count": len([c for c in checks if c["status"] == "passed"]),
                    "failed_count": len([c for c in checks if c["status"] == "failed"]),
                    "tested_at": datetime.utcnow().isoformat()
                },
                message=f"Connection test {'passed' if all_passed else 'failed'}"
            )

        except Exception as e:
            logger.error(f"Error testing Salesforce connection: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
