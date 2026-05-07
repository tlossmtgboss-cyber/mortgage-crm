"""
WebSocket endpoints for real-time agent metrics
Provides real-time updates to the frontend dashboard
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from typing import Dict, List, Tuple
from datetime import datetime, timedelta, timezone
import asyncio
import logging

from database import get_db
from models.agent_governance import AgentProfile, AgentMetricsTimeseries, AgentAlert
from sqlalchemy.exc import SQLAlchemyError
from utils.websocket_auth import authenticate_websocket

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates with tenant isolation"""

    def __init__(self):
        # Agent-specific connections keyed by (org_id, agent_id) for tenant isolation
        self.agent_connections: Dict[tuple, List[WebSocket]] = {}
        # System-wide connections keyed by org_id for tenant isolation
        self.system_connections: Dict[int, List[WebSocket]] = {}

    async def connect_agent(self, websocket: WebSocket, agent_id: int, org_id: int = 0):
        """Track agent-specific connection scoped by organization"""
        key = (org_id, agent_id)
        if key not in self.agent_connections:
            self.agent_connections[key] = []
        self.agent_connections[key].append(websocket)
        logger.info(f"WebSocket connected for agent {agent_id} (org={org_id})")

    async def connect_system(self, websocket: WebSocket, org_id: int = 0):
        """Track system-wide connection scoped by organization"""
        if org_id not in self.system_connections:
            self.system_connections[org_id] = []
        self.system_connections[org_id].append(websocket)
        logger.info(f"WebSocket connected for system health (org={org_id})")

    def disconnect_agent(self, websocket: WebSocket, agent_id: int, org_id: int = 0):
        """Disconnect from agent-specific updates"""
        key = (org_id, agent_id)
        if key in self.agent_connections:
            if websocket in self.agent_connections[key]:
                self.agent_connections[key].remove(websocket)
        logger.info(f"WebSocket disconnected for agent {agent_id} (org={org_id})")

    def disconnect_system(self, websocket: WebSocket, org_id: int = 0):
        """Disconnect from system-wide updates"""
        if org_id in self.system_connections:
            if websocket in self.system_connections[org_id]:
                self.system_connections[org_id].remove(websocket)
        logger.info(f"WebSocket disconnected for system health (org={org_id})")

    async def send_to_agent(self, agent_id: int, message: dict, org_id: int = 0):
        """Send message to all connections for a specific agent within an org"""
        key = (org_id, agent_id)
        if key in self.agent_connections:
            disconnected = []
            for connection in self.agent_connections[key]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending to agent WebSocket: {e}")
                    disconnected.append(connection)
            # Clean up disconnected
            for conn in disconnected:
                self.agent_connections[key].remove(conn)

    async def broadcast_system(self, message: dict, org_id: int = 0):
        """Broadcast message to all system connections within an org"""
        if org_id not in self.system_connections:
            return
        disconnected = []
        for connection in self.system_connections[org_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to system WebSocket: {e}")
                disconnected.append(connection)
        # Clean up disconnected
        for conn in disconnected:
            self.system_connections[org_id].remove(conn)


manager = ConnectionManager()


async def get_agent_metrics_data(db: Session, agent_id: int, org_id: int = None) -> dict:
    """Get latest metrics for an agent, scoped to organization"""
    query = db.query(AgentProfile).filter(AgentProfile.id == agent_id)
    if org_id:
        query = query.filter(AgentProfile.organization_id == org_id)
    agent = query.first()
    if not agent:
        return None

    # Get latest metrics
    latest_metric = db.query(AgentMetricsTimeseries).filter(
        AgentMetricsTimeseries.agent_id == agent_id
    ).order_by(AgentMetricsTimeseries.timestamp.desc()).first()

    # Get active alerts count
    active_alerts = db.query(AgentAlert).filter(
        AgentAlert.agent_id == agent_id,
        AgentAlert.status == "active"
    ).count()

    return {
        "agent_id": agent_id,
        "agent_name": agent.agent_name,
        "display_name": agent.display_name,
        "health_status": agent.health_status,
        "success_rate": float(agent.success_rate) if agent.success_rate else 0,
        "total_executions": agent.total_executions or 0,
        "avg_response_time_ms": agent.avg_response_time_ms or 0,
        "active_alerts": active_alerts,
        "latest_metric": {
            "execution_count": latest_metric.execution_count if latest_metric else 0,
            "success_count": latest_metric.success_count if latest_metric else 0,
            "failure_count": latest_metric.failure_count if latest_metric else 0,
            "avg_response_time_ms": latest_metric.avg_response_time_ms if latest_metric else 0,
            "timestamp": latest_metric.timestamp.isoformat() if latest_metric else None
        } if latest_metric else None
    }


async def get_system_health_data(db: Session, org_id: int = None) -> dict:
    """Get system-wide health metrics, scoped to organization"""
    base_query = db.query(AgentProfile)
    if org_id:
        base_query = base_query.filter(AgentProfile.organization_id == org_id)

    total_agents = base_query.count()

    healthy = base_query.filter(
        AgentProfile.health_status == "healthy"
    ).count()

    warning = base_query.filter(
        AgentProfile.health_status == "warning"
    ).count()

    critical = base_query.filter(
        AgentProfile.health_status == "critical"
    ).count()

    # 24h execution stats
    one_day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    # Get org-scoped agent IDs for sub-queries
    org_agent_ids = None
    if org_id:
        org_agent_ids = [a.id for a in base_query.with_entities(AgentProfile.id).all()]

    metrics_query = db.query(AgentMetricsTimeseries).filter(
        AgentMetricsTimeseries.timestamp >= one_day_ago
    )
    if org_id and org_agent_ids:
        metrics_query = metrics_query.filter(AgentMetricsTimeseries.agent_id.in_(org_agent_ids))
    recent_metrics = metrics_query.all()

    total_executions = sum(m.execution_count or 0 for m in recent_metrics)
    total_success = sum(m.success_count or 0 for m in recent_metrics)

    success_rate = (total_success / total_executions * 100) if total_executions > 0 else 0

    # Active alerts — scope to org's agents
    alerts_query = db.query(AgentAlert).filter(AgentAlert.status == "active")
    if org_id and org_agent_ids:
        alerts_query = alerts_query.filter(AgentAlert.agent_id.in_(org_agent_ids))
    active_alerts = alerts_query.count()

    critical_query = alerts_query.filter(AgentAlert.severity == "critical")
    critical_alerts = critical_query.count()

    return {
        "total_agents": total_agents,
        "health_summary": {
            "healthy": healthy,
            "warning": warning,
            "critical": critical,
            "unknown": total_agents - healthy - warning - critical
        },
        "executions_24h": total_executions,
        "success_rate_24h": round(success_rate, 2),
        "active_alerts": active_alerts,
        "critical_alerts": critical_alerts,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.websocket("/ws/agents/{agent_id}/metrics")
async def agent_metrics_websocket(websocket: WebSocket, agent_id: int):
    """
    Real-time metrics updates for a specific agent.
    Updates every 5 seconds. Requires JWT authentication.
    Tenant-isolated: connections only receive data for their organization.
    """
    await websocket.accept()

    # Authenticate
    auth_db = next(get_db())
    try:
        user, auth_error = authenticate_websocket(websocket, auth_db)
        if not user:
            await websocket.send_json({"type": "error", "message": auth_error or "Authentication required"})
            await websocket.close(code=4001, reason="Authentication required")
            return
    finally:
        auth_db.close()

    org_id = user.organization_id or 0
    await manager.connect_agent(websocket, agent_id, org_id)

    try:
        while True:
            # Get fresh database session
            db = next(get_db())
            try:
                metrics_data = await get_agent_metrics_data(db, agent_id, org_id=org_id)

                if metrics_data:
                    await websocket.send_json({
                        "type": "metrics_update",
                        "data": metrics_data,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
            finally:
                db.close()

            # Wait 5 seconds before next update
            await asyncio.sleep(5)

    except WebSocketDisconnect:
        manager.disconnect_agent(websocket, agent_id, org_id)
    except SQLAlchemyError as e:
        logger.error(f"Agent WebSocket error: {e}")
        manager.disconnect_agent(websocket, agent_id, org_id)


@router.websocket("/ws/system/health")
async def system_health_websocket(websocket: WebSocket):
    """
    Real-time system-wide health updates.
    Updates every 10 seconds. Requires JWT authentication.
    Tenant-isolated: connections only receive data for their organization.
    """
    await websocket.accept()

    # Authenticate
    auth_db = next(get_db())
    try:
        user, auth_error = authenticate_websocket(websocket, auth_db)
        if not user:
            await websocket.send_json({"type": "error", "message": auth_error or "Authentication required"})
            await websocket.close(code=4001, reason="Authentication required")
            return
    finally:
        auth_db.close()

    org_id = user.organization_id or 0
    await manager.connect_system(websocket, org_id)

    try:
        while True:
            # Get fresh database session
            db = next(get_db())
            try:
                health_data = await get_system_health_data(db, org_id=org_id)

                await websocket.send_json({
                    "type": "system_health_update",
                    "data": health_data,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            finally:
                db.close()

            # Wait 10 seconds before next update
            await asyncio.sleep(10)

    except WebSocketDisconnect:
        manager.disconnect_system(websocket, org_id)
    except SQLAlchemyError as e:
        logger.error(f"System WebSocket error: {e}")
        manager.disconnect_system(websocket, org_id)


@router.websocket("/ws/alerts")
async def alerts_websocket(websocket: WebSocket):
    """
    Real-time alerts feed.
    Sends new alerts as they arrive. Requires JWT authentication.
    """
    await websocket.accept()

    # Authenticate
    auth_db = next(get_db())
    try:
        user, auth_error = authenticate_websocket(websocket, auth_db)
        if not user:
            await websocket.send_json({"type": "error", "message": auth_error or "Authentication required"})
            await websocket.close(code=4001, reason="Authentication required")
            return
    finally:
        auth_db.close()

    org_id = user.organization_id or 0
    last_check = datetime.now(timezone.utc)

    try:
        while True:
            db = next(get_db())
            try:
                # Check for new alerts since last check, scoped to org
                alerts_query = db.query(AgentAlert).filter(
                    AgentAlert.created_at > last_check
                )
                if org_id:
                    # Scope alerts to agents belonging to this org
                    org_agent_ids = [
                        a.id for a in db.query(AgentProfile).filter(
                            AgentProfile.organization_id == org_id
                        ).with_entities(AgentProfile.id).all()
                    ]
                    if org_agent_ids:
                        alerts_query = alerts_query.filter(AgentAlert.agent_id.in_(org_agent_ids))
                    else:
                        alerts_query = alerts_query.filter(False)  # No agents for org
                new_alerts = alerts_query.all()

                if new_alerts:
                    for alert in new_alerts:
                        await websocket.send_json({
                            "type": "new_alert",
                            "data": {
                                "id": alert.id,
                                "agent_id": alert.agent_id,
                                "agent_name": alert.agent_name,
                                "alert_type": alert.alert_type,
                                "severity": alert.severity,
                                "title": alert.title,
                                "message": alert.message,
                                "status": alert.status,
                                "created_at": alert.created_at.isoformat()
                            }
                        })

                last_check = datetime.now(timezone.utc)
            finally:
                db.close()

            # Check every 3 seconds
            await asyncio.sleep(3)

    except WebSocketDisconnect:
        pass
    except SQLAlchemyError as e:
        logger.error(f"Alerts WebSocket error: {e}")


# Export manager for use in other modules (e.g., to broadcast on events)
def get_connection_manager():
    return manager
