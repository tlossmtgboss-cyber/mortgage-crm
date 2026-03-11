"""
Salesforce Agent

Specialized agent for Salesforce integration management.

Data flows ONE-WAY: Salesforce → CRM
When records are updated in Salesforce, those changes sync to the CRM.
The CRM does NOT push data back to Salesforce.

Tools available:
1. get_salesforce_status - Get current Salesforce connection status
2. sync_from_salesforce - Pull latest data from Salesforce into CRM
3. sync_emails_from_salesforce - Pull emails from Salesforce
4. sync_calendar_from_salesforce - Pull calendar events from Salesforce
5. get_sync_history - Get sync history and logs
6. diagnose_sync_issues - Diagnose sync problems
7. get_field_mappings - Get current field mappings
8. update_field_mapping - Update a field mapping (inbound only)
9. test_salesforce_connection - Test the Salesforce API connection
10. get_linked_records - Get CRM records linked to Salesforce
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


class SyncFromSalesforceInput(BaseModel):
    entity_type: Optional[str] = Field(None, description="Entity type to sync: loan, lead, contact, or all")
    entity_id: Optional[str] = Field(None, description="Specific entity ID to refresh (optional)")
    full_sync: bool = Field(default=False, description="Force a full sync instead of incremental")


class SyncEmailsInput(BaseModel):
    days_back: int = Field(default=7, description="Number of days back to sync emails")
    force_full_sync: bool = Field(default=False, description="Force a full sync instead of incremental")


class SyncCalendarInput(BaseModel):
    days_back: int = Field(default=7, description="Number of days back to sync")
    days_forward: int = Field(default=30, description="Number of days forward to sync")


class SyncHistoryInput(BaseModel):
    limit: int = Field(default=50, description="Number of records to return")
    status: Optional[str] = Field(None, description="Filter by status: success, error, partial")


class DiagnoseIssuesInput(BaseModel):
    issue_type: Optional[str] = Field(None, description="Specific issue type: auth, sync, mapping, rate_limit")


class FieldMappingsInput(BaseModel):
    entity_type: Optional[str] = Field(None, description="Entity type: loan, lead, contact, email, event")


class UpdateFieldMappingInput(BaseModel):
    entity_type: str = Field(..., description="Entity type: loan, lead, contact, email, event")
    crm_field: str = Field(..., description="CRM field name")
    salesforce_field: str = Field(..., description="Salesforce field name")


class TestConnectionInput(BaseModel):
    test_type: str = Field(default="basic", description="Test type: basic, full, permissions")


class LinkedRecordsInput(BaseModel):
    entity_type: Optional[str] = Field(None, description="Entity type: loan, lead, contact")
    limit: int = Field(default=50, description="Number of records to return")
    only_linked: bool = Field(default=True, description="Only show records linked to Salesforce")


# ============================================================================
# SALESFORCE AGENT
# ============================================================================

@AgentRegistry.register
class SalesforceAgent(SpecializedAgent):
    """
    Salesforce integration agent for managing inbound sync from Salesforce.

    Data flows ONE-WAY: Salesforce → CRM
    When Salesforce records are updated, those changes sync to the CRM.
    """

    @property
    def name(self) -> str:
        return "SalesforceAgent"

    @property
    def description(self) -> str:
        return "Manages Salesforce integration - syncs data FROM Salesforce TO CRM"

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
            name="sync_from_salesforce",
            description="Pull latest data from Salesforce into CRM (loans, leads, contacts)",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._sync_from_salesforce,
            input_schema=SyncFromSalesforceInput
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
            description="Get current field mappings between Salesforce and CRM",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_field_mappings,
            input_schema=FieldMappingsInput
        ))

        self.register_tool(AgentTool(
            name="update_field_mapping",
            description="Update a field mapping (Salesforce → CRM direction only)",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._update_field_mapping,
            input_schema=UpdateFieldMappingInput,
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

        self.register_tool(AgentTool(
            name="get_linked_records",
            description="Get CRM records that are linked to Salesforce records",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_linked_records,
            input_schema=LinkedRecordsInput
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
            org_id = self.require_org_id()

            if not db:
                return ToolResult(
                    success=False,
                    error="Database session not available"
                )

            from models.integration_profile import IntegrationProfile
            from sqlalchemy import and_

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce",
                    IntegrationProfile.organization_id == org_id
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
                "sync_direction": "Salesforce → CRM (inbound only)",
                "sync_stats_24h": {
                    "total": len(recent_syncs),
                    "success": success_count,
                    "errors": error_count,
                    "success_rate": f"{(success_count / len(recent_syncs) * 100):.1f}%" if recent_syncs else "N/A"
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

    async def _sync_from_salesforce(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Sync data from Salesforce to CRM"""
        try:
            db = self._get_db_session()
            user_id = self._get_user_id()
            org_id = self.require_org_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            from models.integration_profile import IntegrationProfile
            from services.salesforce.sync_service import SalesforceSyncService
            from sqlalchemy import and_

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce",
                    IntegrationProfile.status.in_(["connected", "active"]),
                    IntegrationProfile.organization_id == org_id
                )
            ).first()

            if not profile:
                return ToolResult(
                    success=False,
                    error="Salesforce not connected",
                    message="Please connect Salesforce before syncing"
                )

            sync_service = SalesforceSyncService()
            entity_type = input_data.get("entity_type")
            entity_id = input_data.get("entity_id")
            full_sync = input_data.get("full_sync", False)

            # If specific entity requested, pull just that one
            if entity_id and entity_type == "loan":
                result = await sync_service.pull_single_record(
                    db=db,
                    integration_profile_id=profile.id,
                    record_type="loan",
                    record_id=entity_id
                )
            else:
                # Full or incremental sync from Salesforce
                result = await sync_service.sync(
                    db=db,
                    integration_profile_id=profile.id,
                    direction='inbound',
                    full_sync=full_sync
                )

            return ToolResult(
                success=True,
                data={
                    "records_synced": result.records_succeeded if hasattr(result, 'records_succeeded') else result.get('records_synced', 0),
                    "records_updated": result.get('records_updated', 0) if isinstance(result, dict) else 0,
                    "errors": result.errors if hasattr(result, 'errors') else [],
                    "sync_direction": "Salesforce → CRM",
                    "synced_at": datetime.utcnow().isoformat()
                },
                message=f"Synced data from Salesforce to CRM"
            )

        except Exception as e:
            logger.error(f"Error syncing from Salesforce: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))

    async def _sync_emails_from_salesforce(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Sync emails from Salesforce"""
        try:
            db = self._get_db_session()
            user_id = self._get_user_id()
            org_id = self.require_org_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            from models.integration_profile import IntegrationProfile
            from services.salesforce.sync_service import SalesforceSyncService
            from sqlalchemy import and_

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce",
                    IntegrationProfile.status.in_(["connected", "active"]),
                    IntegrationProfile.organization_id == org_id
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
                    "sync_direction": "Salesforce → CRM",
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
            org_id = self.require_org_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            from models.integration_profile import IntegrationProfile
            from services.salesforce.sync_service import SalesforceSyncService
            from sqlalchemy import and_

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce",
                    IntegrationProfile.status.in_(["connected", "active"]),
                    IntegrationProfile.organization_id == org_id
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
                    "sync_direction": "Salesforce → CRM",
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

    async def _get_sync_history(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get Salesforce sync history"""
        try:
            db = self._get_db_session()
            user_id = self._get_user_id()
            org_id = self.require_org_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            from models.integration_profile import IntegrationProfile
            from models.salesforce_sync_log import SalesforceSyncLog
            from sqlalchemy import and_, desc

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce",
                    IntegrationProfile.organization_id == org_id
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
                    "direction": "Salesforce → CRM",
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
                    "total": len(log_data),
                    "sync_direction": "Salesforce → CRM (inbound only)"
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
            org_id = self.require_org_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            from models.integration_profile import IntegrationProfile
            from models.salesforce_sync_log import SalesforceSyncLog
            from sqlalchemy import and_, desc

            issues = []
            recommendations = []

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce",
                    IntegrationProfile.organization_id == org_id
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
                        "message": f"No sync from Salesforce in {int(hours_since_sync)} hours"
                    })
                    recommendations.append("Check if the scheduled sync job is running")
            else:
                issues.append({
                    "type": "no_sync",
                    "severity": "warning",
                    "message": "No sync has been performed yet"
                })
                recommendations.append("Run an initial sync to pull data from Salesforce")

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
                    "recent_error_count": len(recent_errors),
                    "sync_direction": "Salesforce → CRM (inbound only)",
                    "diagnosed_at": datetime.utcnow().isoformat()
                },
                message=f"Found {len([i for i in issues if i['severity'] != 'info'])} issues"
            )

        except Exception as e:
            logger.error(f"Error diagnosing sync issues: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))

    async def _get_field_mappings(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get actual field mappings from the database."""
        db = self._get_db_session()
        if not db:
            return ToolResult(success=False, error="Database session not available")

        try:
            from sqlalchemy import text

            user_id = self._get_user_id()
            org_id = self.require_org_id()

            # Get the user's active Salesforce integration profile
            profile = db.execute(
                text("""
                    SELECT id, user_id FROM integration_profiles
                    WHERE user_id = :user_id AND provider = 'salesforce'
                    AND status IN ('connected', 'active')
                    AND organization_id = :org_id
                    ORDER BY updated_at DESC LIMIT 1
                """),
                {"user_id": user_id, "org_id": org_id}
            ).fetchone()

            if not profile:
                return ToolResult(
                    success=True,
                    data={
                        "mappings": [],
                        "message": "No active Salesforce integration found. Connect your Salesforce account first."
                    },
                    message="No active Salesforce integration found"
                )

            # Build filter for entity_type if provided
            entity_type = input_data.get("entity_type")
            params = {"profile_id": profile.id}
            entity_filter = ""
            if entity_type:
                entity_filter = "AND target_entity = :entity_type"
                params["entity_type"] = entity_type

            # Get live field mappings from database
            mappings = db.execute(
                text(f"""
                    SELECT source_object, source_field, target_entity, target_field,
                           transform_type, sync_direction, enabled, mapping_category
                    FROM field_mappings
                    WHERE integration_profile_id = :profile_id AND enabled = true
                    {entity_filter}
                    ORDER BY source_object, source_field
                """),
                params
            ).fetchall()

            # Get stage mapping count for reference
            stage_mapping_count = 0
            try:
                from services.salesforce.stage_mapping import SALESFORCE_STAGE_MAPPING
                stage_mapping_count = len(SALESFORCE_STAGE_MAPPING)
            except ImportError:
                pass

            mapping_list = [
                {
                    "source": f"{m.source_object}.{m.source_field}",
                    "target": f"{m.target_entity}.{m.target_field}",
                    "transform": m.transform_type,
                    "direction": m.sync_direction,
                    "category": m.mapping_category,
                }
                for m in mappings
            ]

            return ToolResult(
                success=True,
                data={
                    "profile_id": profile.id,
                    "total_mappings": len(mapping_list),
                    "mappings": mapping_list,
                    "stage_mapping_count": stage_mapping_count,
                    "sync_direction": "Salesforce -> CRM (inbound only)",
                },
                message=f"Retrieved {len(mapping_list)} field mappings"
            )
        except Exception as e:
            logger.exception("Failed to get field mappings")
            return ToolResult(success=False, error=f"Failed to get field mappings: {str(e)}")

    async def _update_field_mapping(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Update a field mapping in the database."""
        db = self._get_db_session()
        if not db:
            return ToolResult(success=False, error="Database session not available")

        try:
            from sqlalchemy import text

            user_id = self._get_user_id()
            org_id = self.require_org_id()

            entity_type = input_data.get("entity_type")
            crm_field = input_data.get("crm_field")
            salesforce_field = input_data.get("salesforce_field")

            if not entity_type or not crm_field or not salesforce_field:
                return ToolResult(success=False, error="entity_type, crm_field, and salesforce_field are required")

            # Find the user's active Salesforce profile
            profile = db.execute(
                text("""
                    SELECT id FROM integration_profiles
                    WHERE user_id = :user_id AND provider = 'salesforce'
                    AND status IN ('connected', 'active')
                    AND organization_id = :org_id
                    ORDER BY updated_at DESC LIMIT 1
                """),
                {"user_id": user_id, "org_id": org_id}
            ).fetchone()

            if not profile:
                return ToolResult(success=False, error="No active Salesforce integration found")

            # Find the existing mapping by target entity and field
            mapping = db.execute(
                text("""
                    SELECT id, source_object, source_field, target_entity, target_field
                    FROM field_mappings
                    WHERE integration_profile_id = :profile_id
                    AND target_entity = :entity_type
                    AND target_field = :crm_field
                """),
                {"profile_id": profile.id, "entity_type": entity_type, "crm_field": crm_field}
            ).fetchone()

            if mapping:
                # Update the source field mapping
                db.execute(
                    text("""
                        UPDATE field_mappings
                        SET source_field = :sf_field, updated_at = NOW()
                        WHERE id = :mapping_id
                    """),
                    {"sf_field": salesforce_field, "mapping_id": mapping.id}
                )
                db.commit()
                action = "updated"
            else:
                # Create a new mapping
                db.execute(
                    text("""
                        INSERT INTO field_mappings (
                            integration_profile_id, source_object, source_field,
                            target_entity, target_field, transform_type,
                            sync_direction, enabled, created_at, updated_at
                        ) VALUES (
                            :profile_id, :source_object, :sf_field,
                            :entity_type, :crm_field, 'direct',
                            'inbound', true, NOW(), NOW()
                        )
                    """),
                    {
                        "profile_id": profile.id,
                        "source_object": "MtgPlanner_CRM__Transaction_Property__c",
                        "sf_field": salesforce_field,
                        "entity_type": entity_type,
                        "crm_field": crm_field,
                    }
                )
                db.commit()
                action = "created"

            self.audit_log(
                action="update_field_mapping",
                entity_type="field_mapping",
                details={
                    "entity_type": entity_type,
                    "crm_field": crm_field,
                    "salesforce_field": salesforce_field,
                    "organization_id": org_id,
                    "action": action,
                }
            )

            return ToolResult(
                success=True,
                data={
                    "entity_type": entity_type,
                    "crm_field": crm_field,
                    "salesforce_field": salesforce_field,
                    "action": action,
                    "sync_direction": "Salesforce -> CRM",
                    "updated_at": datetime.utcnow().isoformat()
                },
                message=f"Mapping {action}: SF:{salesforce_field} -> CRM:{crm_field}"
            )
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.exception("Failed to update field mapping")
            return ToolResult(success=False, error=f"Failed to update mapping: {str(e)}")

    async def _test_salesforce_connection(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Test Salesforce connection"""
        try:
            db = self._get_db_session()
            user_id = self._get_user_id()
            org_id = self.require_org_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            from models.integration_profile import IntegrationProfile
            from sqlalchemy import and_

            profile = db.query(IntegrationProfile).filter(
                and_(
                    IntegrationProfile.user_id == user_id,
                    IntegrationProfile.provider == "salesforce",
                    IntegrationProfile.organization_id == org_id
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

            all_passed = all(c["status"] == "passed" for c in checks)

            return ToolResult(
                success=True,
                data={
                    "test_type": test_type,
                    "test_result": "passed" if all_passed else "failed",
                    "checks": checks,
                    "passed_count": len([c for c in checks if c["status"] == "passed"]),
                    "failed_count": len([c for c in checks if c["status"] == "failed"]),
                    "sync_direction": "Salesforce → CRM (inbound only)",
                    "tested_at": datetime.utcnow().isoformat()
                },
                message=f"Connection test {'passed' if all_passed else 'failed'}"
            )

        except Exception as e:
            logger.error(f"Error testing Salesforce connection: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))

    async def _get_linked_records(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get CRM records linked to Salesforce"""
        try:
            db = self._get_db_session()
            org_id = self.require_org_id()

            if not db:
                return ToolResult(success=False, error="Database session not available")

            entity_type = input_data.get("entity_type")
            limit = input_data.get("limit", 50)
            only_linked = input_data.get("only_linked", True)

            results = {}

            # Get linked loans
            if not entity_type or entity_type == "loan":
                from models.loan import Loan

                query = db.query(Loan).filter(Loan.organization_id == org_id)
                if only_linked:
                    query = query.filter(Loan.salesforce_id.isnot(None))

                loans = query.limit(limit).all()
                results["loans"] = [
                    {
                        "id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower_name": loan.borrower_name,
                        "salesforce_id": loan.salesforce_id,
                        "last_synced_at": loan.salesforce_last_synced_at.isoformat() if loan.salesforce_last_synced_at else None,
                        "linked": loan.salesforce_id is not None
                    }
                    for loan in loans
                ]

            # Get linked leads
            if not entity_type or entity_type == "lead":
                from models.lead import Lead

                query = db.query(Lead).filter(Lead.organization_id == org_id)
                if only_linked:
                    query = query.filter(Lead.salesforce_id.isnot(None))

                leads = query.limit(limit).all()
                results["leads"] = [
                    {
                        "id": lead.id,
                        "name": f"{lead.first_name} {lead.last_name}",
                        "email": lead.email,
                        "salesforce_id": lead.salesforce_id,
                        "last_synced_at": lead.salesforce_last_synced_at.isoformat() if hasattr(lead, 'salesforce_last_synced_at') and lead.salesforce_last_synced_at else None,
                        "linked": lead.salesforce_id is not None
                    }
                    for lead in leads
                ]

            total_linked = sum(
                len([r for r in records if r.get("linked")])
                for records in results.values()
            )

            return ToolResult(
                success=True,
                data={
                    **results,
                    "total_linked": total_linked,
                    "sync_direction": "Salesforce → CRM (inbound only)"
                },
                message=f"Found {total_linked} records linked to Salesforce"
            )

        except Exception as e:
            logger.error(f"Error getting linked records: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
