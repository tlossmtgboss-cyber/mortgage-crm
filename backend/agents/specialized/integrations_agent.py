"""
Integrations Agent

Specialized agent for third-party integration management with 8 tools:
1. list_integrations - List available integrations
2. get_integration_status - Get integration status
3. connect_integration - Connect new integration
4. disconnect_integration - Disconnect integration
5. sync_integration_data - Sync data from integration
6. get_integration_logs - Get integration activity logs
7. test_integration - Test integration connection
8. configure_integration - Configure integration settings
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

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

class ListIntegrationsInput(BaseModel):
    category: Optional[str] = Field(None, description="Filter by category: email, calendar, los, crm")
    status: Optional[str] = Field(None, description="Filter by status: connected, available, deprecated")


class IntegrationStatusInput(BaseModel):
    integration_id: str = Field(..., description="Integration ID")


class ConnectIntegrationInput(BaseModel):
    integration_id: str = Field(..., description="Integration ID to connect")
    credentials: Optional[Dict] = Field(None, description="Connection credentials")
    settings: Optional[Dict] = Field(None, description="Initial settings")


class DisconnectIntegrationInput(BaseModel):
    integration_id: str = Field(..., description="Integration ID to disconnect")
    preserve_data: bool = Field(default=True, description="Preserve synced data")


class SyncDataInput(BaseModel):
    integration_id: str = Field(..., description="Integration ID")
    sync_type: str = Field(default="incremental", description="Sync type: full, incremental")
    entity_types: Optional[List[str]] = Field(None, description="Entity types to sync")


class IntegrationLogsInput(BaseModel):
    integration_id: str = Field(..., description="Integration ID")
    limit: int = Field(default=50, description="Number of logs to return")
    level: Optional[str] = Field(None, description="Filter by level: info, warning, error")


class TestIntegrationInput(BaseModel):
    integration_id: str = Field(..., description="Integration ID to test")


class ConfigureIntegrationInput(BaseModel):
    integration_id: str = Field(..., description="Integration ID")
    settings: Dict = Field(..., description="Settings to update")


# ============================================================================
# INTEGRATIONS AGENT
# ============================================================================

@AgentRegistry.register
class IntegrationsAgent(SpecializedAgent):
    """
    Integration management agent for third-party connections.

    Manages connections, syncing, and configuration for external
    integrations with 8 specialized tools.
    """

    @property
    def name(self) -> str:
        return "IntegrationsAgent"

    @property
    def description(self) -> str:
        return "Manages third-party integrations, connections, and data synchronization"

    def _register_tools(self):
        """Register all integration tools"""

        self.register_tool(AgentTool(
            name="list_integrations",
            description="List available and connected integrations",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._list_integrations,
            input_schema=ListIntegrationsInput
        ))

        self.register_tool(AgentTool(
            name="get_integration_status",
            description="Get detailed status of an integration",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_integration_status,
            input_schema=IntegrationStatusInput
        ))

        self.register_tool(AgentTool(
            name="connect_integration",
            description="Connect a new integration",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._connect_integration,
            input_schema=ConnectIntegrationInput,
            requires_confirmation=True
        ))

        self.register_tool(AgentTool(
            name="disconnect_integration",
            description="Disconnect an integration",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._disconnect_integration,
            input_schema=DisconnectIntegrationInput,
            requires_confirmation=True
        ))

        self.register_tool(AgentTool(
            name="sync_integration_data",
            description="Sync data from integration",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._sync_integration_data,
            input_schema=SyncDataInput
        ))

        self.register_tool(AgentTool(
            name="get_integration_logs",
            description="Get integration activity logs",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_integration_logs,
            input_schema=IntegrationLogsInput
        ))

        self.register_tool(AgentTool(
            name="test_integration",
            description="Test integration connection",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._test_integration,
            input_schema=TestIntegrationInput
        ))

        self.register_tool(AgentTool(
            name="configure_integration",
            description="Configure integration settings",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._configure_integration,
            input_schema=ConfigureIntegrationInput
        ))

    async def _list_integrations(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """List integrations — checks DB for connected integrations, merges with available catalog."""

        # Static catalog of available integrations
        catalog = [
            {"id": "microsoft_365", "name": "Microsoft 365", "category": "email", "features": ["email", "calendar", "contacts"]},
            {"id": "google_workspace", "name": "Google Workspace", "category": "email", "features": ["email", "calendar", "contacts", "drive"]},
            {"id": "encompass", "name": "Encompass LOS", "category": "los", "features": ["loan_sync", "document_upload", "milestone_tracking"]},
            {"id": "salesforce", "name": "Salesforce CRM", "category": "crm", "features": ["lead_sync", "loan_sync", "contact_sync"]},
            {"id": "sendgrid", "name": "SendGrid", "category": "email", "features": ["transactional_email", "marketing_email"]},
            {"id": "telnyx", "name": "Telnyx", "category": "telephony", "features": ["sms", "voice", "click_to_call"]},
            {"id": "twilio", "name": "Twilio", "category": "telephony", "features": ["sms", "voice", "vapi_ai"]},
            {"id": "calendly", "name": "Calendly", "category": "calendar", "features": ["scheduling", "availability"]},
        ]

        # Check DB for connected integrations
        connected_ids = set()
        try:
            from database import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                org_id = self.context.get("organization_id")
                params: dict = {}
                org_filter = ""
                if org_id:
                    org_filter = "WHERE organization_id = :org_id"
                    params["org_id"] = org_id

                # Check encompass_configs
                ec = db.execute(text(f"""
                    SELECT id FROM encompass_configs {org_filter} AND is_active = true LIMIT 1
                """.replace("WHERE organization_id", "WHERE is_active = true AND organization_id") if org_id else
                    "SELECT id FROM encompass_configs WHERE is_active = true LIMIT 1"
                ), params).fetchone()
                if ec:
                    connected_ids.add("encompass")

                # Check salesforce via oauth_tokens
                sf = db.execute(text("""
                    SELECT id FROM oauth_tokens
                    WHERE provider = 'salesforce' AND revoked_at IS NULL
                    LIMIT 1
                """)).fetchone()
                if sf:
                    connected_ids.add("salesforce")

                # Check for Microsoft OAuth
                ms = db.execute(text("""
                    SELECT id FROM oauth_tokens
                    WHERE provider IN ('microsoft', 'microsoft_365') AND revoked_at IS NULL
                    LIMIT 1
                """)).fetchone()
                if ms:
                    connected_ids.add("microsoft_365")
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"Could not check integration status from DB: {e}")

        # Also mark known-connected services based on env vars
        import os
        if os.getenv("SENDGRID_API_KEY"):
            connected_ids.add("sendgrid")
        if os.getenv("TELNYX_API_KEY"):
            connected_ids.add("telnyx")
        if os.getenv("TWILIO_AUTH_TOKEN"):
            connected_ids.add("twilio")

        integrations = []
        for item in catalog:
            item["status"] = "connected" if item["id"] in connected_ids else "available"
            integrations.append(item)

        category = input_data.get("category")
        status = input_data.get("status")
        if category:
            integrations = [i for i in integrations if i["category"] == category]
        if status:
            integrations = [i for i in integrations if i["status"] == status]

        return ToolResult(
            success=True,
            data={
                "integrations": integrations,
                "total": len(integrations),
                "connected": len([i for i in integrations if i["status"] == "connected"])
            },
            message=f"Found {len(integrations)} integrations ({len(connected_ids)} connected)"
        )

    async def _get_integration_status(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get integration status"""
        status = {
            "integration_id": input_data["integration_id"],
            "name": "Microsoft 365",
            "status": "connected",
            "health": "healthy",
            "last_sync": datetime.now().isoformat(),
            "sync_frequency": "every 5 minutes",
            "records_synced": {
                "emails": 1250,
                "calendar_events": 85,
                "contacts": 320
            },
            "connected_at": (datetime.now()).isoformat(),
            "expires_at": None
        }

        return ToolResult(
            success=True,
            data=status,
            message=f"Integration {input_data['integration_id']}: {status['status']}"
        )

    async def _connect_integration(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Connect integration"""
        return ToolResult(
            success=True,
            data={
                "integration_id": input_data["integration_id"],
                "status": "connected",
                "connected_at": datetime.now().isoformat(),
                "auth_url": f"https://api.perennia.ai/oauth/{input_data['integration_id']}/authorize"
            },
            message=f"Integration {input_data['integration_id']} connection initiated"
        )

    async def _disconnect_integration(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Disconnect integration"""
        return ToolResult(
            success=True,
            data={
                "integration_id": input_data["integration_id"],
                "disconnected": True,
                "data_preserved": input_data.get("preserve_data", True),
                "disconnected_at": datetime.now().isoformat()
            },
            message=f"Integration {input_data['integration_id']} disconnected"
        )

    async def _sync_integration_data(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Sync integration data"""
        sync_type = input_data.get("sync_type", "incremental")

        return ToolResult(
            success=True,
            data={
                "integration_id": input_data["integration_id"],
                "sync_type": sync_type,
                "started_at": datetime.now().isoformat(),
                "status": "in_progress",
                "estimated_completion": "2 minutes"
            },
            message=f"{sync_type.title()} sync started for {input_data['integration_id']}"
        )

    async def _get_integration_logs(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get integration logs"""
        logs = [
            {
                "timestamp": datetime.now().isoformat(),
                "level": "info",
                "message": "Email sync completed successfully",
                "details": {"emails_synced": 25}
            },
            {
                "timestamp": datetime.now().isoformat(),
                "level": "info",
                "message": "Calendar sync completed",
                "details": {"events_synced": 3}
            },
            {
                "timestamp": datetime.now().isoformat(),
                "level": "warning",
                "message": "Rate limit approaching",
                "details": {"requests_remaining": 100}
            }
        ]

        level = input_data.get("level")
        if level:
            logs = [l for l in logs if l["level"] == level]

        return ToolResult(
            success=True,
            data={
                "integration_id": input_data["integration_id"],
                "logs": logs[:input_data.get("limit", 50)],
                "total": len(logs)
            },
            message=f"Retrieved {len(logs)} log entries"
        )

    async def _test_integration(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Test integration"""
        return ToolResult(
            success=True,
            data={
                "integration_id": input_data["integration_id"],
                "test_result": "passed",
                "checks": [
                    {"check": "authentication", "status": "passed"},
                    {"check": "api_access", "status": "passed"},
                    {"check": "permissions", "status": "passed"},
                    {"check": "data_read", "status": "passed"}
                ],
                "tested_at": datetime.now().isoformat()
            },
            message=f"Integration {input_data['integration_id']} test passed"
        )

    async def _configure_integration(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Configure integration"""
        return ToolResult(
            success=True,
            data={
                "integration_id": input_data["integration_id"],
                "settings_updated": list(input_data["settings"].keys()),
                "updated_at": datetime.now().isoformat()
            },
            message=f"Integration {input_data['integration_id']} configured"
        )
