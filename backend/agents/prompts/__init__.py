# Agent Prompts
from .system import (
    MORTGAGE_AI_SYSTEM_PROMPT,
    SPECIALIZED_AGENT_PROMPTS,
    get_role_context,
    get_specialized_prompt
)
from .lead_pipeline import (
    LEAD_PIPELINE_INSTRUCTIONS,
    DAILY_LEAD_BRIEFING_PROMPT,
    LEAD_OUTREACH_TEMPLATES,
    get_lead_pipeline_instructions,
    get_daily_briefing_prompt,
    get_outreach_template
)

__all__ = [
    "MORTGAGE_AI_SYSTEM_PROMPT",
    "SPECIALIZED_AGENT_PROMPTS",
    "get_role_context",
    "get_specialized_prompt",
    "LEAD_PIPELINE_INSTRUCTIONS",
    "DAILY_LEAD_BRIEFING_PROMPT",
    "LEAD_OUTREACH_TEMPLATES",
    "get_lead_pipeline_instructions",
    "get_daily_briefing_prompt",
    "get_outreach_template"
]
