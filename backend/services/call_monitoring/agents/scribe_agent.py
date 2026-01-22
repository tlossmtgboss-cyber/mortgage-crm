"""
Scribe Agent - Enhanced Version

Expert-level AI agent for call summarization and action item extraction.
Includes:
- Mortgage-specific domain knowledge
- Few-shot examples for high-quality outputs
- Chain-of-thought reasoning for complex calls
- Calibrated confidence scoring
"""

import logging
from typing import Dict, List, Any
import json

from .base_agent import BaseCallAgent, AgentResult
from .mortgage_knowledge import (
    CALL_OUTCOME_PATTERNS,
    FOLLOW_UP_TEMPLATES,
    FEW_SHOT_EXAMPLES,
)

logger = logging.getLogger(__name__)


class ScribeAgent(BaseCallAgent):
    """
    Expert Scribe Agent for mortgage call analysis.

    Capabilities:
    - Executive and detailed call summaries
    - Action item extraction with clear ownership
    - Follow-up message drafts (email/SMS)
    - Call outcome classification
    - Next steps identification

    Enhanced with:
    - Mortgage industry terminology understanding
    - Few-shot examples for consistent quality
    - Confidence calibration based on transcript clarity
    """

    @property
    def agent_type(self) -> str:
        return "scribe"

    @property
    def system_prompt(self) -> str:
        # Build few-shot example
        example = FEW_SHOT_EXAMPLES.get("scribe_summary", {})
        example_input = example.get("input", "")
        example_output = json.dumps(example.get("output", {}), indent=2)

        return f"""You are an expert mortgage industry call analyst with 15+ years of experience. Your role is to analyze calls between loan officers and clients, extracting key information with precision and creating actionable summaries.

## YOUR EXPERTISE INCLUDES:
- Deep understanding of mortgage terminology (LTV, DTI, PITI, escrow, etc.)
- Knowledge of loan programs (Conventional, FHA, VA, USDA, Jumbo)
- Understanding of the loan process (application, processing, underwriting, closing)
- Recognition of common borrower concerns and objections
- Best practices for loan officer follow-up

## CALL OUTCOME PATTERNS TO RECOGNIZE:

**Positive Outcomes:**
{chr(10).join('- ' + p for p in CALL_OUTCOME_PATTERNS['positive'])}

**Neutral/Information Gathering:**
{chr(10).join('- ' + p for p in CALL_OUTCOME_PATTERNS['neutral'])}

**Needs Follow-Up:**
{chr(10).join('- ' + p for p in CALL_OUTCOME_PATTERNS['needs_follow_up'])}

**Negative Outcomes:**
{chr(10).join('- ' + p for p in CALL_OUTCOME_PATTERNS['negative'])}

## ANALYSIS PROCESS (Think step-by-step):

1. **Identify Participants**: Who is speaking? What are their roles?
2. **Determine Call Purpose**: Why was this call made?
3. **Extract Key Information**: What important facts were discussed?
4. **Identify Commitments**: What did each party agree to do?
5. **Assess Outcome**: How did the call end? What's the borrower's sentiment?
6. **Plan Follow-Up**: What should happen next?

## FEW-SHOT EXAMPLE:

**Input Transcript:**
{example_input}

**Expected Output:**
```json
{example_output}
```

## YOUR OUTPUT FORMAT:

Respond with a JSON object in this exact format:
```json
{{
    "executive_summary": "2-3 sentence summary of the call's key outcome",
    "detailed_summary": "Comprehensive summary with all important discussion points",
    "key_points": [
        "Specific, actionable point 1",
        "Specific, actionable point 2"
    ],
    "action_items": [
        {{
            "title": "Clear, specific action title",
            "description": "Detailed description of what needs to be done",
            "owner": "Borrower/LO/Processor/Realtor/etc.",
            "deadline": "Specific date or timeframe, or null if not discussed",
            "priority": "high/medium/low"
        }}
    ],
    "follow_up_drafts": [
        {{
            "type": "email/sms",
            "recipient": "Borrower name or role",
            "subject": "Email subject line (for email type)",
            "body": "Professional, personalized message content"
        }}
    ],
    "call_outcome": "positive/neutral/needs_follow_up/negative",
    "borrower_sentiment": "enthusiastic/positive/neutral/hesitant/concerned/negative",
    "next_call_recommended": true/false,
    "next_call_topic": "Specific topic for next conversation",
    "confidence_notes": "Any areas where transcript was unclear or you're less certain"
}}
```

## QUALITY GUIDELINES:

1. **Be Specific**: Use names, amounts, dates when mentioned
2. **Be Actionable**: Action items should be clear enough to execute
3. **Be Professional**: Follow-up drafts should be polished and ready to send
4. **Be Accurate**: Only include information explicitly stated in the call
5. **Note Uncertainty**: If something is unclear, note it in confidence_notes"""

    def build_user_prompt(self, context: Dict[str, Any]) -> str:
        transcript = context.get('transcript', '')
        transcript = self._truncate_transcript(transcript, max_words=6000)

        participants = self._format_participants(context.get('participants', []))
        loan_context = self._format_loan_context(context.get('loan'))
        lead_context = self._format_lead_context(context.get('lead'))

        # Add call metadata if available
        call_metadata = ""
        session = context.get('session', {})
        if session:
            duration = session.get('duration_seconds', 0)
            if duration:
                minutes = duration // 60
                call_metadata = f"\n## Call Duration: {minutes} minutes"

        # Check for prior calls
        prior_calls = context.get('prior_calls', [])
        prior_context = ""
        if prior_calls:
            prior_context = f"\n## Prior Call History ({len(prior_calls)} previous calls)"
            for i, call in enumerate(prior_calls[:3], 1):  # Last 3 calls
                outcome = call.get('outcome', 'unknown')
                date = call.get('date', 'unknown')
                prior_context += f"\n- Call {i}: {date} - {outcome}"

        prompt = f"""Analyze the following mortgage call transcript and provide a comprehensive expert summary.

## Call Participants
{participants}
{call_metadata}
{prior_context}

## Loan/Lead Context
{loan_context if context.get('loan') else lead_context if context.get('lead') else 'New inquiry - no existing file'}

## Call Transcript
{transcript}

---

Think through this step-by-step:
1. First, identify all participants and their roles
2. Determine the main purpose and outcome of this call
3. Extract all commitments and action items with clear owners
4. Assess the borrower's sentiment and likelihood to proceed
5. Draft appropriate follow-up communications

Provide your analysis in the JSON format specified. Be thorough but precise - only include information actually discussed in the call."""

        return prompt

    def parse_response(self, response_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Scribe agent response into artifacts."""
        artifacts = []

        # Try to extract JSON
        parsed = self._extract_json_from_response(response_text)

        if not parsed:
            # Fallback: create a basic summary artifact
            logger.warning("Scribe agent: Could not parse JSON, creating basic summary")
            artifacts.append({
                'type': 'summary',
                'title': 'Call Summary',
                'content': response_text[:500],
                'structured_data': {'raw_response': response_text},
                'confidence': 0.4,
            })
            return artifacts

        # Calculate base confidence from response quality
        base_confidence = self._calculate_confidence(parsed)

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
                'borrower_sentiment': parsed.get('borrower_sentiment'),
                'next_call_recommended': parsed.get('next_call_recommended'),
                'next_call_topic': parsed.get('next_call_topic'),
                'confidence_notes': parsed.get('confidence_notes'),
            },
            'confidence': base_confidence,
        }
        artifacts.append(summary_artifact)

        # Create scribe_recap artifact with comprehensive recap and next steps
        next_steps = []
        for item in parsed.get('action_items', []):
            owner = item.get('owner', 'LO')
            deadline = item.get('deadline')
            next_steps.append({
                'step': item.get('title', item.get('description', '')),
                'timeline': deadline if deadline else 'As soon as possible',
                'owner': owner,
            })

        scribe_recap_artifact = {
            'type': 'scribe_recap',
            'title': 'Call Recap',
            'content': parsed.get('detailed_summary', parsed.get('executive_summary', '')),
            'structured_data': {
                'detailed_recap': parsed.get('detailed_summary', ''),
                'executive_summary': parsed.get('executive_summary', ''),
                'next_steps': next_steps,
                'key_commitments': parsed.get('key_points', []),
                'follow_up_timeline': parsed.get('next_call_topic', 'Follow up as needed'),
                'call_outcome': parsed.get('call_outcome'),
                'borrower_sentiment': parsed.get('borrower_sentiment'),
            },
            'confidence': base_confidence,
        }
        artifacts.append(scribe_recap_artifact)

        # Create stacked_note artifact for chronological note stacking
        key_points = parsed.get('key_points', [])
        stacked_note_content = f"**{parsed.get('call_outcome', 'Call').upper()} CALL**\n\n"
        stacked_note_content += parsed.get('executive_summary', '') + "\n\n"
        if key_points:
            stacked_note_content += "**Key Points:**\n"
            for point in key_points[:5]:  # Limit to 5 key points
                stacked_note_content += f"• {point}\n"

        stacked_note_artifact = {
            'type': 'stacked_note',
            'title': f"Scribe Notes - {parsed.get('call_outcome', 'Call').title()}",
            'content': stacked_note_content,
            'structured_data': {
                'source': 'scribe',
                'call_outcome': parsed.get('call_outcome'),
                'key_points': key_points,
                'borrower_sentiment': parsed.get('borrower_sentiment'),
                'next_call_recommended': parsed.get('next_call_recommended'),
            },
            'confidence': base_confidence,
        }
        artifacts.append(stacked_note_artifact)

        # Create action item artifacts
        for item in parsed.get('action_items', []):
            # Determine confidence based on specificity
            item_confidence = self._score_action_item_confidence(item)

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
                'confidence': item_confidence,
            }
            artifacts.append(action_artifact)

            # If owner is LO/internal, also create a task artifact
            owner = (item.get('owner') or '').lower()
            internal_owners = ['lo', 'loan officer', 'processor', 'underwriter', 'closer', 'assistant']
            if any(o in owner for o in internal_owners):
                task_artifact = {
                    'type': 'task',
                    'title': item.get('title', 'Task'),
                    'content': item.get('description', ''),
                    'structured_data': {
                        'priority': item.get('priority', 'medium'),
                        'due_date': item.get('deadline'),
                        'owner_role': item.get('owner'),
                        'source': 'call_scribe',
                    },
                    'priority': item.get('priority', 'medium'),
                    'confidence': item_confidence,
                }
                artifacts.append(task_artifact)

        # Create follow-up draft artifacts
        for draft in parsed.get('follow_up_drafts', []):
            # Validate draft quality
            if not draft.get('body') or len(draft.get('body', '')) < 20:
                continue

            draft_artifact = {
                'type': 'follow_up_draft',
                'title': f"Follow-up {draft.get('type', 'email').title()} to {draft.get('recipient', 'Client')}",
                'content': draft.get('body', ''),
                'structured_data': {
                    'message_type': draft.get('type', 'email'),
                    'recipient': draft.get('recipient'),
                    'subject': draft.get('subject'),
                    'body': draft.get('body'),
                },
                'confidence': base_confidence * 0.95,  # Slightly lower for drafts
            }
            artifacts.append(draft_artifact)

        return artifacts

    def _calculate_confidence(self, parsed: Dict) -> float:
        """Calculate overall confidence based on response quality."""
        confidence = 0.7  # Base confidence

        # Increase for completeness
        if parsed.get('executive_summary') and len(parsed['executive_summary']) > 50:
            confidence += 0.05
        if parsed.get('detailed_summary') and len(parsed['detailed_summary']) > 100:
            confidence += 0.05
        if parsed.get('key_points') and len(parsed['key_points']) >= 2:
            confidence += 0.05
        if parsed.get('call_outcome') in ['positive', 'neutral', 'needs_follow_up', 'negative']:
            confidence += 0.05

        # Decrease for uncertainty markers
        confidence_notes = parsed.get('confidence_notes', '')
        if confidence_notes:
            if 'unclear' in confidence_notes.lower():
                confidence -= 0.1
            if 'uncertain' in confidence_notes.lower():
                confidence -= 0.05

        return min(max(confidence, 0.4), 0.95)  # Clamp between 0.4 and 0.95

    def _score_action_item_confidence(self, item: Dict) -> float:
        """Score confidence for an action item based on specificity."""
        confidence = 0.7

        # Has clear owner
        if item.get('owner') and len(item['owner']) > 2:
            confidence += 0.1

        # Has deadline
        if item.get('deadline'):
            confidence += 0.1

        # Has detailed description
        if item.get('description') and len(item['description']) > 30:
            confidence += 0.05

        return min(confidence, 0.95)

    def _truncate_transcript(self, transcript: str, max_words: int = 6000) -> str:
        """Truncate transcript to fit context window while preserving important parts."""
        if not transcript:
            return ""

        words = transcript.split()
        if len(words) <= max_words:
            return transcript

        # Keep first 20% and last 80% to capture intro and recent discussion
        first_portion = int(max_words * 0.2)
        last_portion = max_words - first_portion

        first_words = words[:first_portion]
        last_words = words[-last_portion:]

        return ' '.join(first_words) + '\n\n[... transcript truncated for length ...]\n\n' + ' '.join(last_words)
