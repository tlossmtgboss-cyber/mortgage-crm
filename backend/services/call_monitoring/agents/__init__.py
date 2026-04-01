"""
Call Monitoring AI Agents

Six specialized agents for processing call transcripts:
- ScribeAgent: Summary, action items, follow-up drafts
- JuniorLOAgent: Pricing scenarios, document requests, intake fields, 5 C's analysis
- UnderwriterAgent: Risk flags, conditions, compliance checks
- CalculatorAgent: Mortgage calculations from conversation data
- MarketingAgent: Borrower story capture for testimonials and content
- CallSchedulingAgent: Calendar scheduling and appointment coordination
"""

from .base_agent import BaseCallAgent, AgentResult, AGENT_MODEL, AGENT_MODEL_FAST, AGENT_MODEL_MAP
from .scribe_agent import ScribeAgent
from .junior_lo_agent import JuniorLOAgent
from .underwriter_agent import UnderwriterAgent
from .calculator_agent import CalculatorAgent
from .marketing_agent import MarketingAgent
from .receptionist_agent import CallSchedulingAgent

# Backward compat alias
ReceptionistAgent = CallSchedulingAgent

__all__ = [
    'BaseCallAgent',
    'AgentResult',
    'AGENT_MODEL',
    'AGENT_MODEL_FAST',
    'AGENT_MODEL_MAP',
    'ScribeAgent',
    'JuniorLOAgent',
    'UnderwriterAgent',
    'CalculatorAgent',
    'MarketingAgent',
    'CallSchedulingAgent',
    'ReceptionistAgent',  # backward compat alias
]
