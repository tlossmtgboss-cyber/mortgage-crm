"""
Call Monitoring AI Agents

Three specialized agents for processing call transcripts:
- ScribeAgent: Summary, action items, follow-up drafts
- JuniorLOAgent: Pricing scenarios, document requests, intake fields
- UnderwriterAgent: Risk flags, conditions, compliance checks
"""

from .base_agent import BaseCallAgent, AgentResult, AGENT_MODEL
from .scribe_agent import ScribeAgent
from .junior_lo_agent import JuniorLOAgent
from .underwriter_agent import UnderwriterAgent

__all__ = [
    'BaseCallAgent',
    'AgentResult',
    'AGENT_MODEL',
    'ScribeAgent',
    'JuniorLOAgent',
    'UnderwriterAgent',
]
