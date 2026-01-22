"""
Call Monitoring AI Agents

Four specialized agents for processing call transcripts:
- ScribeAgent: Summary, action items, follow-up drafts
- JuniorLOAgent: Pricing scenarios, document requests, intake fields
- UnderwriterAgent: Risk flags, conditions, compliance checks
- CalculatorAgent: Mortgage calculations from conversation data
"""

from .base_agent import BaseCallAgent, AgentResult, AGENT_MODEL
from .scribe_agent import ScribeAgent
from .junior_lo_agent import JuniorLOAgent
from .underwriter_agent import UnderwriterAgent
from .calculator_agent import CalculatorAgent

__all__ = [
    'BaseCallAgent',
    'AgentResult',
    'AGENT_MODEL',
    'ScribeAgent',
    'JuniorLOAgent',
    'UnderwriterAgent',
    'CalculatorAgent',
]
