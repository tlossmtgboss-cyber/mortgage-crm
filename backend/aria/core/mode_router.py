"""
Mode Router — classifies incoming messages into action/query/campaign.

Uses a lightweight Claude Haiku call (~100ms) to determine which Aria engine
should handle the message. Runs before the NLU/intent node.
"""

import json
import logging
from enum import Enum

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

llm_haiku = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    temperature=0,
    max_tokens=64,
)


class AriaMode(str, Enum):
    ACTION = "action"
    QUERY = "query"
    CAMPAIGN = "campaign"


ROUTER_PROMPT = """Classify the user's message into exactly one mode:

- "action" — user requests a state-changing operation: send, text, schedule, book, generate, create, update, move, add, remind
- "query" — user asks a question: how many, what's the, show me, who, which, when did, where is, check, look up, pull up, pipeline, status, report
- "campaign" — user describes a mass outreach: send a text to everyone, reach out to all, mass text, text everyone with, bulk message, campaign

Respond ONLY with JSON: {"mode": "action" | "query" | "campaign"}"""


async def classify_mode(message: str) -> AriaMode:
    try:
        response = await llm_haiku.ainvoke([
            SystemMessage(content=ROUTER_PROMPT),
            HumanMessage(content=message),
        ])
        parsed = json.loads(response.content.strip())
        mode_str = parsed.get("mode", "query")
        return AriaMode(mode_str)
    except Exception as e:
        logger.warning("Mode router classification failed: %s — defaulting to query", e)
        return AriaMode.QUERY
