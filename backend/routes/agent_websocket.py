"""
WebSocket endpoints for real-time agent metrics
Provides real-time updates to the frontend dashboard
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from typing import Dict, List
from datetime import datetime, timedelta
import asyncio
import logging

from database import get_db
from models.agent_governance import AgentProfile, AgentMetricsTimeseries, AgentAlert

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""

    def __init__(self):
        # Agent-specific connections
        self.agent_connections: Dict[int, List[WebSocket]] = {}
        # System-wide connections
        self.system_connections: List[WebSocket] = []

    async def connect_agent(self, websocket: WebSocket, agent_id: int):
        """Connect to agent-specific updates"""
        await websocket.accept()
        if agent_id not in self.agent_connections:
            self.agent_connections[agent_id] = []
        self.agent_connections[agent_id].append(websocket)
        logger.info(f"WebSocket connected for agent {agent_id}")

    async def connect_system(self, websocket: WebSocket):
        """Connect to system-wide updates"""
        await websocket.accept()
        self.system_connections.append(websocket)
        logger.info("WebSocket connected for system health")

    def disconnect_agent(self, websocket: WebSocket, agent_id: int):
        """Disconnect from agent-specific updates"""
        if agent_id in self.agent_connections:
            if websocket in self.agent_connections[agent_id]:
                self.agent_connections[agent_id].remove(websocket)
        logger.info(f"WebSocket disconnected for agent {agent_id}")

    def disconnect_system(self, websocket: WebSocket):
        """Disconnect from system-wide updates"""
        if websocket in self.system_connections:
            self.system_connections.remove(websocket)
        logger.info("WebSocket disconnected for system health")

    async def send_to_agent(self, agent_id: int, message: dict):
        """Send message to all connections for a specific agent"""
        if agent_id in self.agent_connections:
            disconnected = []
            for connection in self.agent_connections[agent_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending to agent WebSocket: {e}")
                    disconnected.append(connection)
            # Clean up disconnected
            for conn in disconnected:
                self.agent_connections[agent_id].remove(conn)

    async def broadcast_system(self, message: dict):
        """Broadcast message to all system connections"""
        disconnected = []
        for connection in self.system_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to system WebSocket: {e}")
                disconnected.append(connection)
        # Clean up disconnected
        for conn in disconnected:
            self.system_connections.remove(conn)


manager = ConnectionManager()


async def get_agent_metrics_data(db: Session, agent_id: int) -> dict:
    """Get latest metrics for an agent"""
    agent = db.query(AgentProfile).filter(AgentProfile.id == agent_id).first()
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


async def get_system_health_data(db: Session) -> dict:
    """Get system-wide health metrics"""
    total_agents = db.query(AgentProfile).count()

    healthy = db.query(AgentProfile).filter(
        AgentProfile.health_status == "healthy"
    ).count()

    warning = db.query(AgentProfile).filter(
        AgentProfile.health_status == "warning"
    ).count()

    critical = db.query(AgentProfile).filter(
        AgentProfile.health_status == "critical"
    ).count()

    # 24h execution stats
    one_day_ago = datetime.utcnow() - timedelta(hours=24)
    recent_metrics = db.query(AgentMetricsTimeseries).filter(
        AgentMetricsTimeseries.timestamp >= one_day_ago
    ).all()

    total_executions = sum(m.execution_count or 0 for m in recent_metrics)
    total_success = sum(m.success_count or 0 for m in recent_metrics)

    success_rate = (total_success / total_executions * 100) if total_executions > 0 else 0

    # Active alerts
    active_alerts = db.query(AgentAlert).filter(
        AgentAlert.status == "active"
    ).count()

    critical_alerts = db.query(AgentAlert).filter(
        AgentAlert.status == "active",
        AgentAlert.severity == "critical"
    ).count()

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
        "timestamp": datetime.utcnow().isoformat()
    }


@router.websocket("/ws/agents/{agent_id}/metrics")
async def agent_metrics_websocket(websocket: WebSocket, agent_id: int):
    """
    Real-time metrics updates for a specific agent.
    Updates every 5 seconds.
    """
    await manager.connect_agent(websocket, agent_id)

    try:
        while True:
            # Get fresh database session
            db = next(get_db())
            try:
                metrics_data = await get_agent_metrics_data(db, agent_id)

                if metrics_data:
                    await websocket.send_json({
                        "type": "metrics_update",
                        "data": metrics_data,
                        "timestamp": datetime.utcnow().isoformat()
                    })
            finally:
                db.close()

            # Wait 5 seconds before next update
            await asyncio.sleep(5)

    except WebSocketDisconnect:
        manager.disconnect_agent(websocket, agent_id)
    except Exception as e:
        logger.error(f"Agent WebSocket error: {e}")
        manager.disconnect_agent(websocket, agent_id)


@router.websocket("/ws/system/health")
async def system_health_websocket(websocket: WebSocket):
    """
    Real-time system-wide health updates.
    Updates every 10 seconds.
    """
    await manager.connect_system(websocket)

    try:
        while True:
            # Get fresh database session
            db = next(get_db())
            try:
                health_data = await get_system_health_data(db)

                await websocket.send_json({
                    "type": "system_health_update",
                    "data": health_data,
                    "timestamp": datetime.utcnow().isoformat()
                })
            finally:
                db.close()

            # Wait 10 seconds before next update
            await asyncio.sleep(10)

    except WebSocketDisconnect:
        manager.disconnect_system(websocket)
    except Exception as e:
        logger.error(f"System WebSocket error: {e}")
        manager.disconnect_system(websocket)


@router.websocket("/ws/alerts")
async def alerts_websocket(websocket: WebSocket):
    """
    Real-time alerts feed.
    Sends new alerts as they arrive.
    """
    await websocket.accept()
    last_check = datetime.utcnow()

    try:
        while True:
            db = next(get_db())
            try:
                # Check for new alerts since last check
                new_alerts = db.query(AgentAlert).filter(
                    AgentAlert.created_at > last_check
                ).all()

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

                last_check = datetime.utcnow()
            finally:
                db.close()

            # Check every 3 seconds
            await asyncio.sleep(3)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Alerts WebSocket error: {e}")


# Export manager for use in other modules (e.g., to broadcast on events)
def get_connection_manager():
    return manager
