"""
Call Monitoring AI System Services

Multi-agent call monitoring supporting:
- 4 capture modes (mobile app, CRM web call, ambient mic, video call)
- 3 parallel AI agents (Scribe, Junior LO, Underwriter)
- Artifact generation with approval workflow
"""

from .orchestrator_service import CallMonitoringOrchestrator

__all__ = ['CallMonitoringOrchestrator']
