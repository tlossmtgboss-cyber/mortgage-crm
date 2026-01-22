"""
Marketing Agent - Borrower Story Builder

AI agent that listens to calls and builds the borrower's story over time.
Creates content for:
- Testimonials and success stories
- Social media posts
- Heartfelt narratives for closing celebrations
- Marketing content ideas

Every customer has a story - this agent captures it.
"""

import logging
from typing import Dict, List, Any
import json

from .base_agent import BaseCallAgent, AgentResult

logger = logging.getLogger(__name__)


class MarketingAgent(BaseCallAgent):
    """
    Marketing Agent for capturing borrower stories and content ideas.

    Capabilities:
    - Captures emotional moments and milestones
    - Identifies story themes (first-time buyer, growing family, etc.)
    - Extracts quotable moments from conversations
    - Creates content ideas for testimonials and social posts
    - Builds a narrative arc across multiple calls

    The goal is to tell every borrower's heartfelt story when
    their loan closes - celebrating their journey to homeownership.
    """

    @property
    def agent_type(self) -> str:
        return "marketing"

    @property
    def system_prompt(self) -> str:
        return """You are an expert content strategist and storyteller specializing in the mortgage industry. Your role is to listen to calls between loan officers and borrowers to capture the human elements of their homeownership journey.

## YOUR PURPOSE:
Every borrower has a unique story. First-time homebuyers achieving the American dream. Families growing and needing more space. Veterans earning their VA benefit. Couples refinancing to start a new chapter. Your job is to capture these stories so we can celebrate them.

## WHAT TO LISTEN FOR:

**Emotional Moments:**
- Why they want to buy a home (the deeper motivation)
- Family situations (kids, aging parents, pets)
- Life changes prompting the purchase
- Dreams and aspirations for the new home
- Challenges they've overcome
- Excitement and milestone moments

**Story Themes:**
- First-time homebuyer journey
- Growing family needs more space
- Military/Veteran homecoming
- Empty nesters downsizing
- Investment in their future
- Escape from renting
- Multi-generational living
- Dream home finally achievable
- Starting over after life change
- Building generational wealth

**Quotable Moments:**
- Authentic expressions of emotion
- Memorable descriptions of their goals
- Heartfelt statements about family
- Expressions of gratitude or excitement

## TRANSACTION TEAM AWARENESS:
You'll be given context about everyone involved in the transaction:
- Loan Officer (LO) and their Production Assistant (PA)
- Borrower(s) and their family
- Real estate agent(s)
- Other parties

Understand their relationships and capture how they work together.

## OUTPUT FORMAT:

Respond with a JSON object:
```json
{
    "story_notes": [
        {
            "moment_type": "emotional/milestone/quote/background",
            "content": "What happened or was said",
            "context": "The situation around this moment",
            "emotion": "excitement/gratitude/determination/hope/relief/joy",
            "marketing_potential": "high/medium/low"
        }
    ],
    "borrower_profile": {
        "story_theme": "Primary theme of their journey",
        "why_buying": "Their core motivation",
        "family_situation": "Family details if mentioned",
        "challenges_overcome": ["Challenge 1", "Challenge 2"],
        "dreams_for_home": "What they envision",
        "quotable_moments": ["Direct quote 1", "Direct quote 2"]
    },
    "content_ideas": [
        {
            "type": "testimonial/social_post/video_script/closing_celebration",
            "concept": "Brief description of the content idea",
            "key_elements": ["Element to include 1", "Element 2"],
            "best_timing": "When to create/use this content"
        }
    ],
    "milestone_captured": {
        "milestone_type": "first_call/pre_approval/offer_accepted/clear_to_close/closing/etc",
        "significance": "Why this matters to their story",
        "celebration_note": "How we might celebrate this moment"
    },
    "story_arc_position": "beginning/building/climax/resolution",
    "follow_up_questions": ["Question to learn more about their story"]
}
```

## GUIDELINES:

1. **Be Authentic**: Only capture genuine moments, never fabricate
2. **Be Respectful**: Some stories involve hardship - handle with care
3. **Be Specific**: Names, details, and exact quotes are valuable
4. **Think Long-Term**: Build the story over multiple calls
5. **Consider Privacy**: Flag anything that might be too personal to share
6. **Celebrate Diversity**: Every journey is unique and valuable"""

    def build_user_prompt(self, context: Dict[str, Any]) -> str:
        transcript = context.get('transcript', '')
        transcript = self._truncate_transcript(transcript, max_words=5000)

        participants = self._format_participants(context.get('participants', []))
        transaction_team = self._format_transaction_team(context.get('transaction_team', {}))
        loan_context = self._format_loan_context(context.get('loan'))
        lead_context = self._format_lead_context(context.get('lead'))

        # Check for prior story notes
        prior_story = context.get('prior_story_notes', [])
        prior_context = ""
        if prior_story:
            prior_context = "\n## Previously Captured Story Elements:\n"
            for note in prior_story[:5]:
                prior_context += f"- {note.get('content', '')}\n"

        # Get milestone info
        milestone_context = ""
        current_stage = context.get('loan', {}).get('status') or context.get('lead', {}).get('stage')
        if current_stage:
            milestone_context = f"\n## Current Stage in Journey: {current_stage}"

        prompt = f"""Listen to this call and capture elements of the borrower's story for future marketing content.

## Call Participants
{participants}

## Transaction Team (People Involved)
{transaction_team}

## Loan/Lead Context
{loan_context if context.get('loan') else lead_context if context.get('lead') else 'New inquiry'}
{milestone_context}
{prior_context}

## Call Transcript
{transcript}

---

As you analyze this call:
1. Listen for emotional moments and what drives this borrower
2. Identify their story theme (first-time buyer, growing family, etc.)
3. Capture any quotable moments or memorable statements
4. Note where they are in their journey
5. Think about content we could create to tell their story
6. Consider how we'll celebrate when they close

Provide your analysis in the JSON format. Focus on the human elements - this is about their story, not just the transaction."""

        return prompt

    def _format_transaction_team(self, team: Dict[str, Any]) -> str:
        """Format transaction team members for context."""
        if not team:
            return "Transaction team details not provided"

        lines = []

        # Loan Officer
        if team.get('loan_officer'):
            lo = team['loan_officer']
            lines.append(f"**Loan Officer:** {lo.get('name', 'Unknown')} ({lo.get('email', '')})")

        # Production Assistant
        if team.get('production_assistant'):
            pa = team['production_assistant']
            lines.append(f"**Production Assistant:** {pa.get('name', 'Unknown')} ({pa.get('email', '')})")

        # Processor
        if team.get('processor'):
            proc = team['processor']
            lines.append(f"**Processor:** {proc.get('name', 'Unknown')}")

        # Borrower(s)
        if team.get('borrowers'):
            for i, borrower in enumerate(team['borrowers'], 1):
                label = "Primary Borrower" if i == 1 else f"Co-Borrower {i-1}"
                lines.append(f"**{label}:** {borrower.get('name', 'Unknown')}")
                if borrower.get('notes'):
                    lines.append(f"  - Note: {borrower['notes']}")

        # Real Estate Agent(s)
        if team.get('buyer_agent'):
            agent = team['buyer_agent']
            lines.append(f"**Buyer's Agent:** {agent.get('name', 'Unknown')} at {agent.get('brokerage', 'Unknown')}")

        if team.get('listing_agent'):
            agent = team['listing_agent']
            lines.append(f"**Listing Agent:** {agent.get('name', 'Unknown')} at {agent.get('brokerage', 'Unknown')}")

        # Other parties
        if team.get('title_company'):
            lines.append(f"**Title Company:** {team['title_company'].get('name', 'Unknown')}")

        if team.get('insurance_agent'):
            lines.append(f"**Insurance Agent:** {team['insurance_agent'].get('name', 'Unknown')}")

        return "\n".join(lines) if lines else "Transaction team not yet defined"

    def parse_response(self, response_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Marketing agent response into artifacts."""
        artifacts = []

        parsed = self._extract_json_from_response(response_text)

        if not parsed:
            logger.warning("Marketing agent: Could not parse JSON response")
            return artifacts

        # Create story note artifacts
        for note in parsed.get('story_notes', []):
            if not note.get('content'):
                continue

            artifact = {
                'type': 'borrower_story_note',
                'title': f"Story Note: {note.get('moment_type', 'Moment').title()}",
                'content': note.get('content', ''),
                'structured_data': {
                    'moment_type': note.get('moment_type'),
                    'context': note.get('context'),
                    'emotion': note.get('emotion'),
                    'marketing_potential': note.get('marketing_potential'),
                },
                'confidence': 0.85 if note.get('marketing_potential') == 'high' else 0.75,
            }
            artifacts.append(artifact)

        # Create borrower profile / story theme artifact
        profile = parsed.get('borrower_profile', {})
        if profile.get('story_theme') or profile.get('why_buying'):
            theme_artifact = {
                'type': 'story_theme',
                'title': f"Borrower Story: {profile.get('story_theme', 'Their Journey')}",
                'content': profile.get('why_buying', ''),
                'structured_data': {
                    'story_theme': profile.get('story_theme'),
                    'why_buying': profile.get('why_buying'),
                    'family_situation': profile.get('family_situation'),
                    'challenges_overcome': profile.get('challenges_overcome', []),
                    'dreams_for_home': profile.get('dreams_for_home'),
                },
                'confidence': 0.80,
            }
            artifacts.append(theme_artifact)

        # Create quotable moment artifacts
        for quote in profile.get('quotable_moments', []):
            if len(quote) > 10:  # Meaningful quote
                quote_artifact = {
                    'type': 'borrower_quote',
                    'title': 'Quotable Moment',
                    'content': quote,
                    'structured_data': {
                        'quote': quote,
                        'context': profile.get('story_theme'),
                    },
                    'confidence': 0.85,
                }
                artifacts.append(quote_artifact)

        # Create content idea artifacts
        for idea in parsed.get('content_ideas', []):
            idea_artifact = {
                'type': 'content_idea',
                'title': f"Content Idea: {idea.get('type', 'Unknown').replace('_', ' ').title()}",
                'content': idea.get('concept', ''),
                'structured_data': {
                    'content_type': idea.get('type'),
                    'concept': idea.get('concept'),
                    'key_elements': idea.get('key_elements', []),
                    'best_timing': idea.get('best_timing'),
                },
                'confidence': 0.75,
            }
            artifacts.append(idea_artifact)

        # Create milestone artifact if captured
        milestone = parsed.get('milestone_captured', {})
        if milestone.get('milestone_type'):
            milestone_artifact = {
                'type': 'marketing_milestone',
                'title': f"Milestone: {milestone.get('milestone_type', '').replace('_', ' ').title()}",
                'content': milestone.get('significance', ''),
                'structured_data': {
                    'milestone_type': milestone.get('milestone_type'),
                    'significance': milestone.get('significance'),
                    'celebration_note': milestone.get('celebration_note'),
                    'story_arc_position': parsed.get('story_arc_position'),
                },
                'confidence': 0.85,
            }
            artifacts.append(milestone_artifact)

        # Create stacked note for chronological view
        story_summary = []
        if profile.get('story_theme'):
            story_summary.append(f"**Theme:** {profile['story_theme']}")
        if profile.get('why_buying'):
            story_summary.append(f"**Why:** {profile['why_buying']}")
        if milestone.get('milestone_type'):
            story_summary.append(f"**Milestone:** {milestone['milestone_type'].replace('_', ' ').title()}")

        if story_summary:
            stacked_note = {
                'type': 'stacked_note',
                'title': 'Marketing Notes - Borrower Story',
                'content': '\n'.join(story_summary),
                'structured_data': {
                    'source': 'marketing',
                    'story_theme': profile.get('story_theme'),
                    'key_points': [profile.get('why_buying')] if profile.get('why_buying') else [],
                    'story_arc_position': parsed.get('story_arc_position'),
                },
                'confidence': 0.80,
            }
            artifacts.append(stacked_note)

        return artifacts
