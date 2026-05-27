"""
Agent Governance Service

Provides business logic for agent governance operations including:
- Agent health monitoring and status management
- Execution tracking and metrics aggregation
- Alert management
- System-wide health reporting
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_, case

from models.agent_governance import (
    AgentProfile,
    AgentTool,
    AgentExecution,
    AgentAlert,
    AgentMetricsTimeseries,
    AgentChatSession,
    AgentChatMessage
)
from agents.specialized import AgentRegistry
from agents.specialized.base import SpecializedAgent, AgentContext

logger = logging.getLogger(__name__)


class AgentGovernanceService:
    """
    Service for agent governance operations.
    Manages agent health, executions, metrics, and alerts.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # AGENT PROFILE OPERATIONS
    # =========================================================================

    def get_all_agents(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        health_status: Optional[str] = None,
        include_metrics: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all agent profiles with optional filtering.
        """
        query = self.db.query(AgentProfile)

        if status:
            query = query.filter(AgentProfile.status == status)
        if category:
            query = query.filter(AgentProfile.category == category)
        if health_status:
            query = query.filter(AgentProfile.health_status == health_status)

        agents = query.order_by(AgentProfile.category, AgentProfile.agent_name).all()

        result = []
        for agent in agents:
            agent_dict = agent.to_dict()
            if include_metrics:
                agent_dict["recent_metrics"] = self._get_recent_metrics(agent.id)
            result.append(agent_dict)

        return result

    def list_agents(
        self,
        agent_type: Optional[str] = None,
        status: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        List agent profiles with filtering and pagination.
        Used by the agent profiles API endpoint.
        """
        query = self.db.query(AgentProfile)

        # Filter by category (agent_type maps to category)
        if agent_type:
            query = query.filter(AgentProfile.category == agent_type)
        # Filter by status
        if status:
            query = query.filter(AgentProfile.status == status)
        # is_active maps to status == 'active'
        if is_active is True:
            query = query.filter(AgentProfile.status == 'active')
        elif is_active is False:
            query = query.filter(AgentProfile.status != 'active')

        total = query.count()
        agents = query.order_by(AgentProfile.category, AgentProfile.agent_name).offset(offset).limit(limit).all()

        return {
            "agents": [agent.to_dict() for agent in agents],
            "total": total,
            "limit": limit,
            "offset": offset
        }

    def get_agent_by_name(self, agent_name: str) -> Optional[AgentProfile]:
        """Get agent profile by name."""
        return self.db.query(AgentProfile).filter(
            AgentProfile.agent_name == agent_name
        ).first()

    def get_agent_health_summary(self, agent_name: str) -> Dict[str, Any]:
        """
        Get comprehensive health summary for an agent.
        """
        agent = self.get_agent_by_name(agent_name)
        if not agent:
            return {"error": f"Agent '{agent_name}' not found"}

        # Get recent executions (last 24 hours)
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_executions = self.db.query(AgentExecution).filter(
            AgentExecution.agent_id == agent.id,
            AgentExecution.created_at >= since
        ).all()

        # Calculate health metrics
        total_recent = len(recent_executions)
        successful = len([e for e in recent_executions if e.success])
        failed = len([e for e in recent_executions if e.success is False])
        avg_response = sum(e.response_time_ms or 0 for e in recent_executions) / total_recent if total_recent > 0 else 0

        # Get active alerts
        active_alerts = self.db.query(AgentAlert).filter(
            AgentAlert.agent_id == agent.id,
            AgentAlert.status == 'active'
        ).count()

        # Determine health status
        error_rate = (failed / total_recent * 100) if total_recent > 0 else 0
        health_status = self._calculate_health_status(error_rate, avg_response, active_alerts)

        return {
            "agent_name": agent_name,
            "status": agent.status,
            "health_status": health_status,
            "metrics_24h": {
                "total_executions": total_recent,
                "successful": successful,
                "failed": failed,
                "error_rate": round(error_rate, 2),
                "avg_response_time_ms": round(avg_response, 2)
            },
            "active_alerts": active_alerts,
            "last_execution": agent.last_execution_at.isoformat() if agent.last_execution_at else None,
            "last_health_check": agent.last_health_check.isoformat() if agent.last_health_check else None,
            "tool_count": agent.tool_count,
            "risk_tier": agent.risk_tier
        }

    def update_agent_config(
        self,
        agent_name: str,
        config: Dict[str, Any]
    ) -> Optional[AgentProfile]:
        """Update agent configuration."""
        agent = self.get_agent_by_name(agent_name)
        if not agent:
            return None

        # Merge with existing config
        current_config = agent.config or {}
        current_config.update(config)
        agent.config = current_config
        agent.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(agent)
        return agent

    def pause_agent(self, agent_name: str, reason: Optional[str] = None) -> bool:
        """Pause an agent."""
        agent = self.get_agent_by_name(agent_name)
        if not agent:
            return False

        agent.status = 'paused'
        agent.updated_at = datetime.now(timezone.utc)

        # Create alert for pause
        self._create_alert(
            agent_id=agent.id,
            agent_name=agent_name,
            alert_type='status_change',
            severity='medium',
            title=f"Agent {agent_name} paused",
            message=reason or "Agent paused by administrator"
        )

        self.db.commit()
        return True

    def resume_agent(self, agent_name: str) -> bool:
        """Resume a paused agent."""
        agent = self.get_agent_by_name(agent_name)
        if not agent:
            return False

        agent.status = 'active'
        agent.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return True

    # =========================================================================
    # EXECUTION TRACKING
    # =========================================================================

    def log_execution_start(
        self,
        agent_name: str,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        input_text: Optional[str] = None,
        input_data: Optional[Dict] = None,
        tool_name: Optional[str] = None
    ) -> AgentExecution:
        """
        Log the start of an agent execution.
        Returns the execution record for later completion.
        """
        agent = self.get_agent_by_name(agent_name)

        execution = AgentExecution(
            execution_id=uuid.uuid4(),
            agent_id=agent.id if agent else None,
            agent_name=agent_name,
            tool_name=tool_name,
            user_id=user_id,
            user_email=user_email,
            input_text=input_text,
            input_data=input_data or {},
            status='running',
            started_at=datetime.now(timezone.utc)
        )

        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)
        return execution

    def log_execution_complete(
        self,
        execution_id: uuid.UUID,
        success: bool,
        output_data: Optional[Dict] = None,
        error_message: Optional[str] = None,
        trajectory: Optional[List] = None,
        tool_calls: Optional[List] = None,
        tokens_used: int = 0,
        total_cost: Decimal = Decimal(0)
    ) -> Optional[AgentExecution]:
        """
        Log the completion of an agent execution.
        """
        execution = self.db.query(AgentExecution).filter(
            AgentExecution.execution_id == execution_id
        ).first()

        if not execution:
            logger.error(f"Execution {execution_id} not found")
            return None

        now = datetime.now(timezone.utc)
        execution.status = 'completed' if success else 'failed'
        execution.success = success
        execution.output_data = output_data or {}
        execution.error_message = error_message
        execution.trajectory = trajectory or []
        execution.tool_calls = tool_calls or []
        execution.tokens_used = tokens_used
        execution.total_cost = total_cost
        execution.completed_at = now

        # Calculate response time
        if execution.started_at:
            delta = now - execution.started_at
            execution.response_time_ms = int(delta.total_seconds() * 1000)

        # Update agent profile
        if execution.agent_id:
            self._update_agent_metrics(execution.agent_id, execution)

        self.db.commit()
        self.db.refresh(execution)
        return execution

    def get_agent_executions(
        self,
        agent_name: str,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        success: Optional[bool] = None,
        since: Optional[datetime] = None
    ) -> Tuple[List[AgentExecution], int]:
        """
        Get execution history for an agent.
        Returns (executions, total_count).
        """
        query = self.db.query(AgentExecution).filter(
            AgentExecution.agent_name == agent_name
        )

        if status:
            query = query.filter(AgentExecution.status == status)
        if success is not None:
            query = query.filter(AgentExecution.success == success)
        if since:
            query = query.filter(AgentExecution.created_at >= since)

        total = query.count()
        executions = query.order_by(desc(AgentExecution.created_at)).offset(offset).limit(limit).all()

        return executions, total

    def get_execution_details(self, execution_id: uuid.UUID) -> Optional[AgentExecution]:
        """Get detailed execution record."""
        return self.db.query(AgentExecution).filter(
            AgentExecution.execution_id == execution_id
        ).first()

    def get_agent_failures(
        self,
        agent_name: str,
        limit: int = 20,
        since: Optional[datetime] = None
    ) -> List[AgentExecution]:
        """Get recent failures for an agent."""
        since = since or (datetime.now(timezone.utc) - timedelta(days=7))

        return self.db.query(AgentExecution).filter(
            AgentExecution.agent_name == agent_name,
            AgentExecution.success == False,
            AgentExecution.created_at >= since
        ).order_by(desc(AgentExecution.created_at)).limit(limit).all()

    def list_executions(
        self,
        agent_name: Optional[str] = None,
        agent_id: Optional[int] = None,
        status: Optional[str] = None,
        success: Optional[bool] = None,
        days: int = 30,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        List executions with filtering and pagination.
        Used by the statistics and executions API endpoints.
        """
        query = self.db.query(AgentExecution)

        # Filter by date range
        since = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(AgentExecution.created_at >= since)

        if agent_name:
            query = query.filter(AgentExecution.agent_name == agent_name)
        if agent_id:
            query = query.filter(AgentExecution.agent_id == agent_id)
        if status:
            query = query.filter(AgentExecution.status == status)
        if success is not None:
            query = query.filter(AgentExecution.success == success)

        total = query.count()
        executions = query.order_by(desc(AgentExecution.created_at)).offset(offset).limit(limit).all()

        return {
            "executions": executions,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    # =========================================================================
    # METRICS & ANALYTICS
    # =========================================================================

    def get_agent_metrics(
        self,
        agent_name: str,
        period: str = '24h'
    ) -> Dict[str, Any]:
        """
        Get metrics for an agent over a specified period.
        Period can be: 1h, 6h, 24h, 7d, 30d
        """
        agent = self.get_agent_by_name(agent_name)
        if not agent:
            return {"error": f"Agent '{agent_name}' not found"}

        # Parse period
        period_map = {
            '1h': timedelta(hours=1),
            '6h': timedelta(hours=6),
            '24h': timedelta(hours=24),
            '7d': timedelta(days=7),
            '30d': timedelta(days=30)
        }
        delta = period_map.get(period, timedelta(hours=24))
        since = datetime.now(timezone.utc) - delta

        # Get executions in period
        executions = self.db.query(AgentExecution).filter(
            AgentExecution.agent_id == agent.id,
            AgentExecution.created_at >= since
        ).all()

        total = len(executions)
        successful = len([e for e in executions if e.success])
        failed = len([e for e in executions if e.success is False])
        response_times = [e.response_time_ms for e in executions if e.response_time_ms]

        return {
            "agent_name": agent_name,
            "period": period,
            "metrics": {
                "total_executions": total,
                "successful": successful,
                "failed": failed,
                "success_rate": round((successful / total * 100) if total > 0 else 0, 2),
                "error_rate": round((failed / total * 100) if total > 0 else 0, 2),
                "avg_response_time_ms": round(sum(response_times) / len(response_times) if response_times else 0, 2),
                "min_response_time_ms": min(response_times) if response_times else 0,
                "max_response_time_ms": max(response_times) if response_times else 0,
                "total_tokens": sum(e.tokens_used or 0 for e in executions),
                "total_cost": float(sum(e.total_cost or 0 for e in executions))
            }
        }

    def get_cost_analytics(
        self,
        agent_name: str,
        period: str = '30d'
    ) -> Dict[str, Any]:
        """
        Get cost analytics for an agent.
        """
        agent = self.get_agent_by_name(agent_name)
        if not agent:
            return {"error": f"Agent '{agent_name}' not found"}

        period_map = {
            '7d': timedelta(days=7),
            '30d': timedelta(days=30),
            '90d': timedelta(days=90)
        }
        delta = period_map.get(period, timedelta(days=30))
        since = datetime.now(timezone.utc) - delta

        # Get daily costs
        daily_costs = self.db.query(
            func.date(AgentExecution.created_at).label('date'),
            func.sum(AgentExecution.total_cost).label('cost'),
            func.sum(AgentExecution.tokens_used).label('tokens'),
            func.count().label('count')
        ).filter(
            AgentExecution.agent_id == agent.id,
            AgentExecution.created_at >= since
        ).group_by(
            func.date(AgentExecution.created_at)
        ).order_by(
            func.date(AgentExecution.created_at)
        ).all()

        return {
            "agent_name": agent_name,
            "period": period,
            "total_cost": float(agent.total_cost or 0),
            "cost_this_month": float(agent.cost_this_month or 0),
            "daily_breakdown": [
                {
                    "date": str(row.date),
                    "cost": float(row.cost or 0),
                    "tokens": row.tokens or 0,
                    "executions": row.count
                }
                for row in daily_costs
            ]
        }

    def aggregate_metrics(self, period_type: str = 'hour') -> int:
        """
        Aggregate execution metrics into time-series buckets.
        Called by background scheduler.
        Returns number of metrics records created.
        """
        now = datetime.now(timezone.utc)

        if period_type == 'hour':
            bucket_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
            bucket_end = bucket_start + timedelta(hours=1)
        elif period_type == 'day':
            bucket_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            bucket_end = bucket_start + timedelta(days=1)
        else:
            bucket_start = now - timedelta(hours=1)
            bucket_end = now

        # Get all agents
        agents = self.db.query(AgentProfile).all()
        count = 0

        for agent in agents:
            # Get executions in bucket
            executions = self.db.query(AgentExecution).filter(
                AgentExecution.agent_id == agent.id,
                AgentExecution.created_at >= bucket_start,
                AgentExecution.created_at < bucket_end
            ).all()

            if not executions:
                continue

            # Calculate metrics
            total = len(executions)
            successful = len([e for e in executions if e.success])
            failed = len([e for e in executions if e.success is False])
            response_times = sorted([e.response_time_ms for e in executions if e.response_time_ms])

            # Create metrics record
            metrics = AgentMetricsTimeseries(
                agent_id=agent.id,
                agent_name=agent.agent_name,
                timestamp=bucket_start,
                period_type=period_type,
                execution_count=total,
                success_count=successful,
                failure_count=failed,
                avg_response_time_ms=sum(response_times) / len(response_times) if response_times else 0,
                min_response_time_ms=min(response_times) if response_times else None,
                max_response_time_ms=max(response_times) if response_times else None,
                p95_response_time_ms=response_times[int(len(response_times) * 0.95)] if len(response_times) > 20 else None,
                p99_response_time_ms=response_times[int(len(response_times) * 0.99)] if len(response_times) > 100 else None,
                total_cost=sum(e.total_cost or 0 for e in executions),
                total_tokens=sum(e.tokens_used or 0 for e in executions),
                error_rate=(failed / total * 100) if total > 0 else 0
            )

            self.db.add(metrics)
            count += 1

        self.db.commit()
        logger.info(f"Aggregated metrics for {count} agents (period: {period_type})")
        return count

    # =========================================================================
    # ALERT MANAGEMENT
    # =========================================================================

    def get_alerts(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        agent_name: Optional[str] = None,
        limit: int = 50
    ) -> List[AgentAlert]:
        """Get alerts with optional filtering."""
        query = self.db.query(AgentAlert)

        if status:
            query = query.filter(AgentAlert.status == status)
        if severity:
            query = query.filter(AgentAlert.severity == severity)
        if agent_name:
            query = query.filter(AgentAlert.agent_name == agent_name)

        return query.order_by(desc(AgentAlert.triggered_at)).limit(limit).all()

    def list_alerts(
        self,
        agent_id: Optional[str] = None,
        alert_type: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        days: int = 7,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        List alerts with filtering and pagination.
        Used by the alerts API endpoint.
        """
        query = self.db.query(AgentAlert)

        # Filter by date range
        since = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(AgentAlert.triggered_at >= since)

        if agent_id:
            query = query.filter(AgentAlert.agent_id == agent_id)
        if alert_type:
            query = query.filter(AgentAlert.alert_type == alert_type)
        if severity:
            query = query.filter(AgentAlert.severity == severity)
        if status:
            query = query.filter(AgentAlert.status == status)

        total = query.count()
        alerts = query.order_by(desc(AgentAlert.triggered_at)).offset(offset).limit(limit).all()

        return {
            "alerts": alerts,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    def acknowledge_alert(
        self,
        alert_id: int,
        user_id: int
    ) -> Optional[AgentAlert]:
        """Acknowledge an alert."""
        alert = self.db.query(AgentAlert).filter(AgentAlert.id == alert_id).first()
        if not alert:
            return None

        alert.status = 'acknowledged'
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by_id = user_id
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def resolve_alert(
        self,
        alert_id: int,
        user_id: int,
        resolution_notes: Optional[str] = None
    ) -> Optional[AgentAlert]:
        """Resolve an alert."""
        alert = self.db.query(AgentAlert).filter(AgentAlert.id == alert_id).first()
        if not alert:
            return None

        alert.status = 'resolved'
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolved_by_id = user_id
        alert.resolution_notes = resolution_notes
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def _create_alert(
        self,
        agent_id: int,
        agent_name: str,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        details: Optional[Dict] = None
    ) -> AgentAlert:
        """Create a new alert."""
        alert = AgentAlert(
            agent_id=agent_id,
            agent_name=agent_name,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            details=details or {},
            status='active'
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    # =========================================================================
    # DASHBOARD
    # =========================================================================

    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Get comprehensive dashboard data combining agents, executions, and alerts.
        """
        try:
            # Get all agents
            agents = self.db.query(AgentProfile).all()

            # Agent summary
            agent_summary = {
                "total": len(agents),
                "active": len([a for a in agents if a.status == 'active']),
                "paused": len([a for a in agents if a.status == 'paused']),
                "maintenance": len([a for a in agents if a.status == 'maintenance']),
                "by_health": {
                    "healthy": len([a for a in agents if a.health_status == 'healthy']),
                    "warning": len([a for a in agents if a.health_status == 'warning']),
                    "critical": len([a for a in agents if a.health_status == 'critical']),
                }
            }

            # Recent executions (last 24h)
            since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
            recent_execs = self.db.query(AgentExecution).filter(
                AgentExecution.created_at >= since_24h
            ).all()

            exec_summary = {
                "total_24h": len(recent_execs),
                "successful": len([e for e in recent_execs if e.success]),
                "failed": len([e for e in recent_execs if e.success == False]),
                "avg_time_ms": round(
                    sum(e.execution_time_ms or 0 for e in recent_execs) / len(recent_execs), 2
                ) if recent_execs else 0
            }

            # Fallback: if agent_executions is empty, query agent_invocations
            # for real execution data from the performance tracker
            if exec_summary["total_24h"] == 0:
                try:
                    from database.models.agent_metrics import AgentInvocation
                    inv_stats = self.db.query(
                        func.count(AgentInvocation.id).label("total"),
                        func.sum(case(
                            (AgentInvocation.status == "success", 1),
                            else_=0
                        )).label("successful"),
                        func.sum(case(
                            (AgentInvocation.status != "success", 1),
                            else_=0
                        )).label("failed"),
                        func.avg(AgentInvocation.duration_ms).label("avg_duration")
                    ).filter(
                        AgentInvocation.created_at >= since_24h
                    ).first()

                    if inv_stats and (inv_stats.total or 0) > 0:
                        exec_summary = {
                            "total_24h": int(inv_stats.total or 0),
                            "successful": int(inv_stats.successful or 0),
                            "failed": int(inv_stats.failed or 0),
                            "avg_time_ms": round(float(inv_stats.avg_duration or 0), 2),
                            "source": "agent_invocations"
                        }
                except Exception as e:
                    logger.debug(f"agent_invocations fallback failed: {e}")

            # Active alerts
            active_alerts = self.db.query(AgentAlert).filter(
                AgentAlert.status == 'active'
            ).all()

            alert_summary = {
                "total_active": len(active_alerts),
                "critical": len([a for a in active_alerts if a.severity == 'critical']),
                "high": len([a for a in active_alerts if a.severity == 'high']),
                "medium": len([a for a in active_alerts if a.severity == 'medium']),
                "low": len([a for a in active_alerts if a.severity == 'low']),
            }

            # Top agents by execution count
            top_agents = []
            use_invocations_for_top = exec_summary.get("source") == "agent_invocations"

            if use_invocations_for_top:
                # Query agent_invocations grouped by agent_role for top agents
                try:
                    from database.models.agent_metrics import AgentInvocation
                    inv_by_role = self.db.query(
                        AgentInvocation.agent_role,
                        func.count(AgentInvocation.id).label("cnt")
                    ).filter(
                        AgentInvocation.created_at >= since_24h
                    ).group_by(
                        AgentInvocation.agent_role
                    ).order_by(desc(func.count(AgentInvocation.id))).limit(10).all()

                    for row in inv_by_role:
                        # Try to find matching agent profile
                        agent = self.db.query(AgentProfile).filter(
                            AgentProfile.agent_name == row.agent_role
                        ).first()
                        top_agents.append({
                            "name": row.agent_role,
                            "display_name": agent.display_name if agent else row.agent_role,
                            "status": agent.status if agent else "active",
                            "health": agent.health_status if agent else "unknown",
                            "executions_24h": row.cnt
                        })
                except Exception as e:
                    logger.debug(f"agent_invocations top agents fallback failed: {e}")
            else:
                for agent in agents[:10]:
                    exec_count = self.db.query(AgentExecution).filter(
                        AgentExecution.agent_id == agent.id,
                        AgentExecution.created_at >= since_24h
                    ).count()
                    top_agents.append({
                        "name": agent.agent_name,
                        "display_name": agent.display_name,
                        "status": agent.status,
                        "health": agent.health_status,
                        "executions_24h": exec_count
                    })

            top_agents.sort(key=lambda x: x["executions_24h"], reverse=True)

            return {
                "agents": agent_summary,
                "executions": exec_summary,
                "alerts": alert_summary,
                "top_agents": top_agents[:5],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}")
            # Return minimal data on error
            return {
                "agents": {"total": 0, "active": 0, "paused": 0, "maintenance": 0, "by_health": {}},
                "executions": {"total_24h": 0, "successful": 0, "failed": 0, "avg_time_ms": 0},
                "alerts": {"total_active": 0, "critical": 0, "high": 0, "medium": 0, "low": 0},
                "top_agents": [],
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "error": "Internal server error"
            }

    # =========================================================================
    # SYSTEM HEALTH
    # =========================================================================

    def get_system_health(self) -> Dict[str, Any]:
        """
        Get overall system health status.
        """
        agents = self.db.query(AgentProfile).all()

        total = len(agents)
        healthy = len([a for a in agents if a.health_status == 'healthy'])
        warning = len([a for a in agents if a.health_status == 'warning'])
        critical = len([a for a in agents if a.health_status == 'critical'])
        active = len([a for a in agents if a.status == 'active'])
        paused = len([a for a in agents if a.status == 'paused'])

        # Get recent system-wide metrics
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_executions = self.db.query(AgentExecution).filter(
            AgentExecution.created_at >= since
        ).count()

        active_alerts = self.db.query(AgentAlert).filter(
            AgentAlert.status == 'active'
        ).count()

        critical_alerts = self.db.query(AgentAlert).filter(
            AgentAlert.status == 'active',
            AgentAlert.severity == 'critical'
        ).count()

        # Determine overall status
        if critical_alerts > 0 or critical > 0:
            overall_status = 'critical'
        elif warning > 0 or active_alerts > 5:
            overall_status = 'warning'
        else:
            overall_status = 'healthy'

        return {
            "overall_status": overall_status,
            "agents": {
                "total": total,
                "active": active,
                "paused": paused,
                "healthy": healthy,
                "warning": warning,
                "critical": critical
            },
            "metrics_24h": {
                "total_executions": recent_executions
            },
            "alerts": {
                "total_active": active_alerts,
                "critical": critical_alerts
            },
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

    def calculate_health_scores(self) -> int:
        """
        Calculate and update health scores for all agents.
        Called by background scheduler.
        Returns number of agents updated.
        """
        agents = self.db.query(AgentProfile).all()
        count = 0

        for agent in agents:
            health_summary = self.get_agent_health_summary(agent.agent_name)
            new_health = health_summary.get('health_status', 'unknown')

            if agent.health_status != new_health:
                old_health = agent.health_status
                agent.health_status = new_health
                agent.last_health_check = datetime.now(timezone.utc)

                # Create alert if degraded
                if new_health in ['warning', 'critical'] and old_health == 'healthy':
                    self._create_alert(
                        agent_id=agent.id,
                        agent_name=agent.agent_name,
                        alert_type='health_degraded',
                        severity='high' if new_health == 'critical' else 'medium',
                        title=f"Agent {agent.agent_name} health degraded to {new_health}",
                        message=f"Error rate: {health_summary.get('metrics_24h', {}).get('error_rate', 0)}%"
                    )

                count += 1

        self.db.commit()
        logger.info(f"Updated health scores for {count} agents")
        return count

    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Get comprehensive dashboard data for agent governance.
        Combines health, metrics, alerts, and cost data.

        Falls back to agent_invocations table (written by performance_tracker)
        when agent_executions has no data.
        """
        # Get system health
        health = self.get_system_health()

        # Get recent executions summary
        since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        since_7d = datetime.now(timezone.utc) - timedelta(days=7)

        executions_24h = self.db.query(AgentExecution).filter(
            AgentExecution.created_at >= since_24h
        ).all()

        executions_7d = self.db.query(AgentExecution).filter(
            AgentExecution.created_at >= since_7d
        ).all()

        # Calculate metrics
        total_24h = len(executions_24h)
        success_24h = len([e for e in executions_24h if e.success])
        failed_24h = total_24h - success_24h

        total_7d = len(executions_7d)
        success_7d = len([e for e in executions_7d if e.success])

        # Calculate costs
        cost_24h = sum(float(e.total_cost or 0) for e in executions_24h)
        cost_7d = sum(float(e.total_cost or 0) for e in executions_7d)

        # Get top agents by usage
        agent_usage = {}
        for e in executions_24h:
            agent_usage[e.agent_name] = agent_usage.get(e.agent_name, 0) + 1

        top_agents = sorted(agent_usage.items(), key=lambda x: x[1], reverse=True)[:5]

        # Fallback: if agent_executions is empty, query agent_invocations
        # for real execution data from the performance tracker
        _invocation_source = False
        if total_24h == 0 or total_7d == 0:
            try:
                from database.models.agent_metrics import AgentInvocation

                if total_24h == 0:
                    inv_24h = self.db.query(
                        func.count(AgentInvocation.id).label("total"),
                        func.sum(case(
                            (AgentInvocation.status == "success", 1),
                            else_=0
                        )).label("successful"),
                        func.sum(case(
                            (AgentInvocation.status != "success", 1),
                            else_=0
                        )).label("failed"),
                        func.sum(AgentInvocation.cost_estimate).label("cost")
                    ).filter(
                        AgentInvocation.created_at >= since_24h
                    ).first()

                    if inv_24h and (inv_24h.total or 0) > 0:
                        total_24h = int(inv_24h.total or 0)
                        success_24h = int(inv_24h.successful or 0)
                        failed_24h = int(inv_24h.failed or 0)
                        cost_24h = float(inv_24h.cost or 0)
                        _invocation_source = True

                if total_7d == 0:
                    inv_7d = self.db.query(
                        func.count(AgentInvocation.id).label("total"),
                        func.sum(case(
                            (AgentInvocation.status == "success", 1),
                            else_=0
                        )).label("successful"),
                        func.sum(AgentInvocation.cost_estimate).label("cost")
                    ).filter(
                        AgentInvocation.created_at >= since_7d
                    ).first()

                    if inv_7d and (inv_7d.total or 0) > 0:
                        total_7d = int(inv_7d.total or 0)
                        success_7d = int(inv_7d.successful or 0)
                        cost_7d = float(inv_7d.cost or 0)

                # Top agents from invocations if needed
                if _invocation_source and not top_agents:
                    inv_top = self.db.query(
                        AgentInvocation.agent_role,
                        func.count(AgentInvocation.id).label("cnt")
                    ).filter(
                        AgentInvocation.created_at >= since_24h
                    ).group_by(
                        AgentInvocation.agent_role
                    ).order_by(desc(func.count(AgentInvocation.id))).limit(5).all()

                    top_agents = [(row.agent_role, row.cnt) for row in inv_top]

            except Exception as e:
                logger.debug(f"agent_invocations fallback failed in dashboard v2: {e}")

        # Get active alerts
        alerts = self.db.query(AgentAlert).filter(
            AgentAlert.status == 'active'
        ).order_by(AgentAlert.created_at.desc()).limit(10).all()

        return {
            "health": health,
            "metrics": {
                "last_24h": {
                    "total_executions": total_24h,
                    "successful": success_24h,
                    "failed": failed_24h,
                    "success_rate": round((success_24h / total_24h * 100) if total_24h > 0 else 100, 1),
                    "total_cost": round(cost_24h, 4)
                },
                "last_7d": {
                    "total_executions": total_7d,
                    "successful": success_7d,
                    "failed": total_7d - success_7d,
                    "success_rate": round((success_7d / total_7d * 100) if total_7d > 0 else 100, 1),
                    "total_cost": round(cost_7d, 4)
                },
                "source": "agent_invocations" if _invocation_source else "agent_executions"
            },
            "top_agents": [{"name": name, "executions": count} for name, count in top_agents],
            "recent_alerts": [
                {
                    "id": str(a.id),
                    "agent_name": a.agent_name,
                    "alert_type": a.alert_type,
                    "severity": a.severity,
                    "title": a.title,
                    "created_at": a.created_at.isoformat() if a.created_at else None
                }
                for a in alerts
            ],
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    # =========================================================================
    # TOOL MANAGEMENT
    # =========================================================================

    def get_agent_tools(self, agent_name: str) -> List[AgentTool]:
        """Get all tools for an agent."""
        agent = self.get_agent_by_name(agent_name)
        if not agent:
            return []
        return self.db.query(AgentTool).filter(AgentTool.agent_id == agent.id).all()

    def sync_tools_from_registry(self, agent_name: str) -> int:
        """
        Sync tools from AgentRegistry to database.
        Returns number of tools synced.
        """
        agent = self.get_agent_by_name(agent_name)
        if not agent:
            return 0

        # Get agent instance from registry
        context: AgentContext = {
            'user_id': 'system',
            'user_email': 'system@perennia.ai',
            'db_session': self.db
        }

        registry_agent = AgentRegistry.get_agent(agent_name, context)
        if not registry_agent:
            return 0

        count = 0
        for tool_name, tool in registry_agent.tools.items():
            existing = self.db.query(AgentTool).filter(
                AgentTool.agent_id == agent.id,
                AgentTool.tool_name == tool_name
            ).first()

            if existing:
                # Update existing
                existing.description = tool.description
                existing.category = tool.category.value if hasattr(tool.category, 'value') else tool.category
                existing.risk_level = tool.risk_level.value if hasattr(tool.risk_level, 'value') else tool.risk_level
                existing.requires_confirmation = tool.requires_confirmation
            else:
                # Create new
                new_tool = AgentTool(
                    agent_id=agent.id,
                    tool_name=tool_name,
                    description=tool.description,
                    category=tool.category.value if hasattr(tool.category, 'value') else tool.category,
                    risk_level=tool.risk_level.value if hasattr(tool.risk_level, 'value') else tool.risk_level,
                    requires_confirmation=tool.requires_confirmation,
                    cooldown_seconds=tool.cooldown_seconds,
                    max_per_hour=tool.max_per_hour
                )
                self.db.add(new_tool)
                count += 1

        # Update agent tool count
        agent.tool_count = len(registry_agent.tools)
        self.db.commit()
        return count

    # =========================================================================
    # AGENT COMPARISON
    # =========================================================================

    def compare_agents(
        self,
        agent_names: List[str],
        period: str = '7d'
    ) -> Dict[str, Any]:
        """
        Compare metrics across multiple agents.
        """
        period_map = {
            '24h': timedelta(hours=24),
            '7d': timedelta(days=7),
            '30d': timedelta(days=30)
        }
        delta = period_map.get(period, timedelta(days=7))
        since = datetime.now(timezone.utc) - delta

        comparisons = []
        for name in agent_names:
            agent = self.get_agent_by_name(name)
            if not agent:
                continue

            executions = self.db.query(AgentExecution).filter(
                AgentExecution.agent_id == agent.id,
                AgentExecution.created_at >= since
            ).all()

            total = len(executions)
            successful = len([e for e in executions if e.success])
            response_times = [e.response_time_ms for e in executions if e.response_time_ms]

            comparisons.append({
                "agent_name": name,
                "category": agent.category,
                "status": agent.status,
                "health_status": agent.health_status,
                "total_executions": total,
                "success_rate": round((successful / total * 100) if total > 0 else 0, 2),
                "avg_response_time_ms": round(sum(response_times) / len(response_times) if response_times else 0, 2),
                "total_cost": float(sum(e.total_cost or 0 for e in executions))
            })

        return {
            "period": period,
            "agents": comparisons
        }

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _get_recent_metrics(self, agent_id: int) -> Dict[str, Any]:
        """Get recent metrics snapshot for an agent."""
        since = datetime.now(timezone.utc) - timedelta(hours=24)

        result = self.db.query(
            func.count().label('total'),
            func.sum(func.cast(AgentExecution.success, Integer)).label('successful'),
            func.avg(AgentExecution.response_time_ms).label('avg_response')
        ).filter(
            AgentExecution.agent_id == agent_id,
            AgentExecution.created_at >= since
        ).first()

        return {
            "executions_24h": result.total or 0,
            "success_rate_24h": round((result.successful or 0) / (result.total or 1) * 100, 2),
            "avg_response_ms_24h": round(result.avg_response or 0, 2)
        }

    def _calculate_health_status(
        self,
        error_rate: float,
        avg_response: float,
        active_alerts: int
    ) -> str:
        """Calculate health status based on metrics."""
        if error_rate > 20 or active_alerts >= 3:
            return 'critical'
        elif error_rate > 10 or avg_response > 5000 or active_alerts >= 1:
            return 'warning'
        else:
            return 'healthy'

    def _update_agent_metrics(self, agent_id: int, execution: AgentExecution):
        """Update agent profile metrics after execution."""
        agent = self.db.query(AgentProfile).filter(AgentProfile.id == agent_id).first()
        if not agent:
            return

        agent.total_executions = (agent.total_executions or 0) + 1
        if execution.success:
            agent.successful_executions = (agent.successful_executions or 0) + 1
        else:
            agent.failed_executions = (agent.failed_executions or 0) + 1

        agent.last_execution_at = execution.completed_at or datetime.now(timezone.utc)

        # Update success rate
        if agent.total_executions > 0:
            agent.success_rate = (agent.successful_executions / agent.total_executions) * 100

        # Update cost
        if execution.total_cost:
            agent.total_cost = (agent.total_cost or Decimal(0)) + execution.total_cost
            agent.cost_this_month = (agent.cost_this_month or Decimal(0)) + execution.total_cost

        # Update average response time (moving average)
        if execution.response_time_ms:
            current_avg = agent.avg_response_time_ms or 0
            n = agent.total_executions
            agent.avg_response_time_ms = ((current_avg * (n - 1)) + execution.response_time_ms) / n


# Add missing import for Integer cast
from sqlalchemy import Integer
from sqlalchemy.exc import SQLAlchemyError
