"""
Call Monitoring AI System Services

Multi-agent call monitoring supporting:
- 4 capture modes (mobile app, CRM web call, ambient mic, video call)
- 3 parallel AI agents (Scribe, Junior LO, Underwriter)
- Artifact generation with approval workflow
- CI Voice integration for automatic processing
"""

from .orchestrator_service import CallMonitoringOrchestrator
from .ci_integration_service import CIIntegrationService, trigger_call_monitoring_agents

__all__ = [
    'CallMonitoringOrchestrator',
    'CIIntegrationService',
    'trigger_call_monitoring_agents',
]
