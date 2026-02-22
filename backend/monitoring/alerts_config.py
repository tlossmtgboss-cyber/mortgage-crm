"""
DataDog Alerts Configuration
============================
Defines alert thresholds and monitors for the Mortgage CRM.

These configurations can be applied via:
1. DataDog Terraform provider
2. DataDog API (POST /api/v1/monitor)
3. Manual setup in DataDog UI

Environment Variables:
    DD_API_KEY: Required for API operations
    DD_APP_KEY: Required for API operations
    ALERT_EMAIL: Email for alert notifications
    ALERT_SLACK_CHANNEL: Slack channel for alerts
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

DD_SERVICE = os.getenv("DD_SERVICE", "mortgage-crm")
DD_ENV = os.getenv("DD_ENV") or os.getenv("ENVIRONMENT", "production")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "alerts@example.com")
ALERT_SLACK_CHANNEL = os.getenv("ALERT_SLACK_CHANNEL", "#mortgage-crm-alerts")


# ============================================================================
# ALERT DEFINITIONS
# ============================================================================

@dataclass
class AlertThreshold:
    """Alert threshold configuration."""
    warning: float
    critical: float


@dataclass
class MonitorConfig:
    """DataDog monitor configuration."""
    name: str
    type: str  # metric alert, service check, log alert, etc.
    query: str
    message: str
    thresholds: Dict[str, float]
    tags: List[str] = field(default_factory=list)
    priority: int = 3  # 1-5, 1 being highest
    notify_no_data: bool = False
    no_data_timeframe: int = 10  # minutes
    renotify_interval: int = 0  # 0 = don't renotify
    escalation_message: str = ""
    include_tags: bool = True

    def to_datadog_api(self) -> Dict:
        """Convert to DataDog API format."""
        notification_targets = []
        if ALERT_EMAIL:
            notification_targets.append(f"@{ALERT_EMAIL}")
        if ALERT_SLACK_CHANNEL:
            notification_targets.append(f"@slack-{ALERT_SLACK_CHANNEL.lstrip('#')}")

        full_message = f"{self.message}\n\n{' '.join(notification_targets)}"

        return {
            "name": f"[{DD_ENV.upper()}] {self.name}",
            "type": self.type,
            "query": self.query,
            "message": full_message,
            "tags": self.tags + [f"service:{DD_SERVICE}", f"env:{DD_ENV}"],
            "priority": self.priority,
            "options": {
                "thresholds": self.thresholds,
                "notify_no_data": self.notify_no_data,
                "no_data_timeframe": self.no_data_timeframe,
                "renotify_interval": self.renotify_interval,
                "escalation_message": self.escalation_message,
                "include_tags": self.include_tags
            }
        }


# ============================================================================
# ALERT DEFINITIONS
# ============================================================================

def get_monitor_configs() -> List[MonitorConfig]:
    """
    Get all monitor configurations for the Mortgage CRM.

    Returns list of MonitorConfig objects ready for DataDog API.
    """
    return [
        # ====================================================================
        # INFRASTRUCTURE ALERTS
        # ====================================================================

        MonitorConfig(
            name="High Error Rate",
            type="metric alert",
            query=f"sum(last_5m):sum:mortgage_crm.http.errors.5xx{{service:{DD_SERVICE},env:{DD_ENV}}}.as_rate() / sum:mortgage_crm.http.requests{{service:{DD_SERVICE},env:{DD_ENV}}}.as_rate() * 100 > 5",
            message="Error rate is above threshold.\n\n"
                    "Current error rate: {{value}}%\n"
                    "Investigate recent deployments and check application logs.",
            thresholds={"warning": 2, "critical": 5},
            priority=1,
            tags=["team:platform", "category:availability"]
        ),

        MonitorConfig(
            name="High Response Time (P95)",
            type="metric alert",
            query=f"avg(last_5m):p95:mortgage_crm.http.duration_ms{{service:{DD_SERVICE},env:{DD_ENV}}} > 3000",
            message="P95 response time is high.\n\n"
                    "Current P95: {{value}}ms\n"
                    "Check database queries and external API calls.",
            thresholds={"warning": 2000, "critical": 3000},
            priority=2,
            tags=["team:platform", "category:performance"]
        ),

        MonitorConfig(
            name="Database Connection Pool Exhaustion",
            type="metric alert",
            query=f"avg(last_5m):avg:mortgage_crm.db.pool.checked_out{{service:{DD_SERVICE},env:{DD_ENV}}} / avg:mortgage_crm.db.pool.max_connections{{service:{DD_SERVICE},env:{DD_ENV}}} * 100 > 80",
            message="Database connection pool is nearly exhausted.\n\n"
                    "Pool utilization: {{value}}%\n"
                    "Check for connection leaks or increase pool size.",
            thresholds={"warning": 70, "critical": 80},
            priority=1,
            tags=["team:platform", "category:database"]
        ),

        MonitorConfig(
            name="High Slow Query Rate",
            type="metric alert",
            query=f"sum(last_15m):sum:mortgage_crm.db.slow_queries{{service:{DD_SERVICE},env:{DD_ENV}}}.as_count() > 50",
            message="High number of slow database queries.\n\n"
                    "Slow queries in last 15m: {{value}}\n"
                    "Review query patterns and add appropriate indices.",
            thresholds={"warning": 20, "critical": 50},
            priority=2,
            tags=["team:platform", "category:database"]
        ),

        # ====================================================================
        # BUSINESS ALERTS
        # ====================================================================

        MonitorConfig(
            name="Lead Conversion Drop",
            type="metric alert",
            query=f"pct_change(avg(last_1d),last_1d):sum:mortgage_crm.leads.converted{{service:{DD_SERVICE},env:{DD_ENV}}}.as_count() < -30",
            message="Lead conversions dropped significantly.\n\n"
                    "Change from yesterday: {{value}}%\n"
                    "Review lead pipeline and check for issues.",
            thresholds={"warning": -20, "critical": -30},
            priority=2,
            tags=["team:business", "category:leads"]
        ),

        MonitorConfig(
            name="Zero Leads Created (Business Hours)",
            type="metric alert",
            query=f"sum(last_4h):sum:mortgage_crm.leads.created{{service:{DD_SERVICE},env:{DD_ENV}}}.as_count() < 1",
            message="No new leads created in the last 4 hours.\n\n"
                    "This may indicate an issue with lead intake systems.",
            thresholds={"warning": 1, "critical": 0.5},
            priority=2,
            notify_no_data=True,
            no_data_timeframe=60,
            tags=["team:business", "category:leads"]
        ),

        # ====================================================================
        # AI SYSTEM ALERTS
        # ====================================================================

        MonitorConfig(
            name="AI Request Failures",
            type="metric alert",
            query=f"sum(last_15m):sum:mortgage_crm.ai.requests{{service:{DD_SERVICE},env:{DD_ENV},success:false}}.as_count() > 10",
            message="High number of AI request failures.\n\n"
                    "Failed requests: {{value}}\n"
                    "Check AI provider status and API keys.",
            thresholds={"warning": 5, "critical": 10},
            priority=1,
            tags=["team:ai", "category:availability"]
        ),

        MonitorConfig(
            name="AI Response Time Degradation",
            type="metric alert",
            query=f"avg(last_10m):avg:mortgage_crm.ai.duration_ms{{service:{DD_SERVICE},env:{DD_ENV}}} > 15000",
            message="AI response times are degraded.\n\n"
                    "Average response time: {{value}}ms\n"
                    "Check AI provider performance and consider caching.",
            thresholds={"warning": 10000, "critical": 15000},
            priority=2,
            tags=["team:ai", "category:performance"]
        ),

        MonitorConfig(
            name="AI Receptionist Call Failure Rate",
            type="metric alert",
            query=f"sum(last_1h):sum:mortgage_crm.ai_receptionist.calls{{service:{DD_SERVICE},env:{DD_ENV},outcome:failed}}.as_count() / sum:mortgage_crm.ai_receptionist.calls{{service:{DD_SERVICE},env:{DD_ENV}}}.as_count() * 100 > 10",
            message="AI Receptionist call failure rate is high.\n\n"
                    "Failure rate: {{value}}%\n"
                    "Check VAPI/Telnyx status and call logs.",
            thresholds={"warning": 5, "critical": 10},
            priority=1,
            tags=["team:ai", "category:voice"]
        ),

        # ====================================================================
        # CACHE ALERTS
        # ====================================================================

        MonitorConfig(
            name="Cache Hit Rate Drop",
            type="metric alert",
            query=f"avg(last_30m):avg:mortgage_crm.cache.hit_rate{{service:{DD_SERVICE},env:{DD_ENV}}} < 50",
            message="Cache hit rate has dropped.\n\n"
                    "Current hit rate: {{value}}%\n"
                    "Check Redis connectivity and cache warming.",
            thresholds={"warning": 60, "critical": 50},
            priority=3,
            tags=["team:platform", "category:cache"]
        ),

        MonitorConfig(
            name="Redis Connection Failure",
            type="service check",
            query=f"\"redis.can_connect\".over(\"service:{DD_SERVICE}\",\"env:{DD_ENV}\").by(\"host\").last(2).count_by_status()",
            message="Redis connection check failed.\n\n"
                    "Cache functionality may be degraded.",
            thresholds={"warning": 1, "critical": 1},
            priority=2,
            tags=["team:platform", "category:cache"]
        ),

        # ====================================================================
        # INTEGRATION ALERTS
        # ====================================================================

        MonitorConfig(
            name="Salesforce Sync Failures",
            type="metric alert",
            query=f"sum(last_1h):sum:mortgage_crm.integrations.salesforce.sync_failures{{service:{DD_SERVICE},env:{DD_ENV}}}.as_count() > 5",
            message="Salesforce sync failures detected.\n\n"
                    "Failures in last hour: {{value}}\n"
                    "Check Salesforce connection and credentials.",
            thresholds={"warning": 3, "critical": 5},
            priority=2,
            tags=["team:integrations", "category:salesforce"]
        ),

        MonitorConfig(
            name="SMS Delivery Failures",
            type="metric alert",
            query=f"sum(last_1h):sum:mortgage_crm.sms.delivery_failures{{service:{DD_SERVICE},env:{DD_ENV}}}.as_count() > 10",
            message="High SMS delivery failure rate.\n\n"
                    "Failed deliveries: {{value}}\n"
                    "Check Telnyx status and account balance.",
            thresholds={"warning": 5, "critical": 10},
            priority=2,
            tags=["team:communications", "category:sms"]
        ),
    ]


# ============================================================================
# API UTILITIES
# ============================================================================

def create_monitors_via_api(api_key: str = None, app_key: str = None) -> Dict[str, Any]:
    """
    Create all monitors via DataDog API.

    Args:
        api_key: DataDog API key (defaults to DD_API_KEY env var)
        app_key: DataDog App key (defaults to DD_APP_KEY env var)

    Returns:
        Dict with creation results
    """
    api_key = api_key or os.getenv("DD_API_KEY")
    app_key = app_key or os.getenv("DD_APP_KEY")

    if not api_key or not app_key:
        return {
            "success": False,
            "error": "DD_API_KEY and DD_APP_KEY environment variables required"
        }

    try:
        import requests

        results = []
        for config in get_monitor_configs():
            monitor_data = config.to_datadog_api()

            response = requests.post(
                "https://api.datadoghq.com/api/v1/monitor",
                headers={
                    "DD-API-KEY": api_key,
                    "DD-APPLICATION-KEY": app_key,
                    "Content-Type": "application/json"
                },
                json=monitor_data
            )

            results.append({
                "name": config.name,
                "status_code": response.status_code,
                "success": response.status_code == 200,
                "response": response.json() if response.status_code == 200 else response.text
            })

        return {
            "success": all(r["success"] for r in results),
            "created": len([r for r in results if r["success"]]),
            "failed": len([r for r in results if not r["success"]]),
            "results": results
        }

    except ImportError:
        return {
            "success": False,
            "error": "requests library required - pip install requests"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


def export_monitors_json(filename: str = "datadog_monitors.json") -> str:
    """
    Export monitor configurations to JSON file.

    Can be used with:
    - DataDog Terraform provider
    - Manual API import
    - Documentation
    """
    monitors = [config.to_datadog_api() for config in get_monitor_configs()]

    with open(filename, 'w') as f:
        json.dump(monitors, f, indent=2)

    logger.info(f"Exported {len(monitors)} monitors to {filename}")
    return filename


def get_monitors_summary() -> Dict[str, Any]:
    """Get summary of all configured monitors."""
    configs = get_monitor_configs()

    by_category = {}
    by_priority = {1: [], 2: [], 3: [], 4: [], 5: []}

    for config in configs:
        # Group by category tag
        category = next(
            (t.split(":")[1] for t in config.tags if t.startswith("category:")),
            "other"
        )
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(config.name)

        # Group by priority
        by_priority[config.priority].append(config.name)

    return {
        "total_monitors": len(configs),
        "by_category": by_category,
        "by_priority": {
            f"P{k}": v for k, v in by_priority.items() if v
        },
        "monitors": [
            {
                "name": c.name,
                "type": c.type,
                "priority": c.priority,
                "tags": c.tags
            }
            for c in configs
        ]
    }


# ============================================================================
# CLI USAGE
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "export":
            filename = sys.argv[2] if len(sys.argv) > 2 else "datadog_monitors.json"
            export_monitors_json(filename)
            print(f"Exported to {filename}")

        elif command == "create":
            result = create_monitors_via_api()
            print(json.dumps(result, indent=2))

        elif command == "summary":
            summary = get_monitors_summary()
            print(json.dumps(summary, indent=2))

        else:
            print(f"Unknown command: {command}")
            print("Usage: python alerts_config.py [export|create|summary]")
    else:
        # Default: print summary
        summary = get_monitors_summary()
        print(json.dumps(summary, indent=2))
