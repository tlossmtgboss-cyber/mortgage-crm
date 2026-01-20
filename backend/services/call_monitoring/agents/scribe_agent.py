"""
Scribe Agent

AI agent that processes call transcripts to generate:
- Call summaries (executive and detailed)
- Action items with assignees
- Follow-up message drafts (email/SMS)
"""

import logging
from typing import Dict, List, Any
import json

from .base_agent import BaseCallAgent, AgentResult

logger = logging.getLogger(__name__)


class ScribeAgent(BaseCallAgent):
    """
    Scribe Agent for call summarization and action item extraction.

    Outputs:
    - summary: Executive and detailed call summary
    - action_item: Tasks identified from the conversation
    - follow_up_draft: Draft follow-up messages
    """

    @property
    def agent_type(self) -> str:
        return "scribe"

    @property
    def system_prompt(self) -> str:
        return """You are an expert mortgage call analyst and scribe. Your job is to analyze call transcripts between loan officers and clients (borrowers, realtors, etc.) and extract key information.

You must provide:
1. A concise executive summary (2-3 sentences)
2. A detailed summary with key discussion points
3. Action items with clear owners and deadlines
4. Draft follow-up messages if appropriate

Focus on:
- Key decisions made
- Information exchanged
- Commitments and promises
- Questions that need answers
- Next steps discussed

Be specific and actionable. Use names when mentioned.

IMPORTANT: Respond with a JSON object in the following format:
```json
{
    "executive_summary": "Brief 2-3 sentence summary",
    "detailed_summary": "Longer summary with key points",
    "key_points": ["Point 1", "Point 2", ...],
    "action_items": [
        {
            "title": "Action item title",
            "description": "Detailed description",
            "owner": "Person responsible (LO/Borrower/etc.)",
            "deadline": "Suggested deadline or null",
            "priority": "high/medium/low"
        }
    ],
    "follow_up_drafts": [
        {
            "type": "email/sms",
            "recipient": "Who to send to",
            "subject": "Email subject (if email)",
            "body": "Message content"
        }
    ],
    "call_outcome": "positive/neutral/negative",
    "next_call_recommended": true/false,
    "next_call_topic": "What to discuss next time (if applicable)"
}
```"""

    def build_user_prompt(self, context: Dict[str, Any]) -> str:
        transcript = context.get('transcript', '')
        transcript = self._truncate_transcript(transcript)

        participants = self._format_participants(context.get('participants', []))
        loan_context = self._format_loan_context(context.get('loan'))
        lead_context = self._format_lead_context(context.get('lead'))

        prompt = f"""Analyze the following mortgage-related call transcript and provide a comprehensive summary.

## Call Participants
{participants}

## Loan/Lead Context
{loan_context if context.get('loan') else lead_context}

## Call Transcript
{transcript}

---

Please analyze this call and provide your response in the JSON format specified."""

        return prompt

    def parse_response(self, response_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Scribe agent response into artifacts."""
        artifacts = []

        # Try to extract JSON
        parsed = self._extract_json_from_response(response_text)

        if not parsed:
            # Fallback: create a basic summary artifact
            artifacts.append({
                'type': 'summary',
                'title': 'Call Summary',
                'content': response_text,
                'structured_data': {},
                'confidence': 0.5,
            })
            return artifacts

        # Create summary artifact
        summary_artifact = {
            'type': 'summary',
            'title': 'Call Summary',
            'content': parsed.get('executive_summary', ''),
            'structured_data': {
                'executive_summary': parsed.get('executive_summary'),
                'detailed_summary': parsed.get('detailed_summary'),
                'key_points': parsed.get('key_points', []),
                'call_outcome': parsed.get('call_outcome'),
                'next_call_recommended': parsed.get('next_call_recommended'),
                'next_call_topic': parsed.get('next_call_topic'),
            },
            'confidence': 0.9,
        }
        artifacts.append(summary_artifact)

        # Create action item artifacts
        for item in parsed.get('action_items', []):
            action_artifact = {
                'type': 'action_item',
                'title': item.get('title', 'Action Item'),
                'content': item.get('description', ''),
                'structured_data': {
                    'owner': item.get('owner'),
                    'deadline': item.get('deadline'),
                    'priority': item.get('priority', 'medium'),
                },
                'priority': item.get('priority', 'medium'),
                'confidence': 0.85,
            }
            artifacts.append(action_artifact)

            # If owner is LO, also create a task artifact
            owner = item.get('owner', '').lower()
            if 'lo' in owner or 'loan officer' in owner or 'processor' in owner:
                task_artifact = {
                    'type': 'task',
                    'title': item.get('title', 'Task'),
                    'content': item.get('description', ''),
                    'structured_data': {
                        'priority': item.get('priority', 'medium'),
                        'due_date': item.get('deadline'),
                        'source': 'call_scribe',
                    },
                    'priority': item.get('priority', 'medium'),
                    'confidence': 0.85,
                }
                artifacts.append(task_artifact)

        # Create follow-up draft artifacts
        for draft in parsed.get('follow_up_drafts', []):
            draft_artifact = {
                'type': 'follow_up_draft',
                'title': f"Follow-up {draft.get('type', 'message').title()} to {draft.get('recipient', 'Client')}",
                'content': draft.get('body', ''),
                'structured_data': {
                    'message_type': draft.get('type', 'email'),
                    'recipient': draft.get('recipient'),
                    'subject': draft.get('subject'),
                    'body': draft.get('body'),
                },
                'confidence': 0.8,
            }
            artifacts.append(draft_artifact)

        return artifacts
