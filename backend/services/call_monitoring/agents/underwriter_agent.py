"""
Underwriter Agent

AI agent that processes call transcripts to:
- Identify risk factors and red flags
- Suggest potential conditions
- Check for compliance concerns
- Generate underwriter summary bullets
"""

import logging
from typing import Dict, List, Any

from .base_agent import BaseCallAgent, AgentResult

logger = logging.getLogger(__name__)


# Risk categories and their indicators
RISK_INDICATORS = {
    "credit": {
        "triggers": [
            "bankruptcy", "foreclosure", "short sale", "late payments",
            "collections", "charge-off", "judgement", "credit issues",
            "credit repair", "low score", "bad credit"
        ],
        "severity_keywords": {
            "critical": ["recent bankruptcy", "active foreclosure", "fraud"],
            "high": ["bankruptcy", "foreclosure", "multiple lates"],
            "medium": ["late payment", "collection", "credit repair"],
        }
    },
    "income": {
        "triggers": [
            "self-employed", "1099", "variable income", "commission",
            "bonus", "overtime", "part-time", "gap in employment",
            "new job", "job change", "unemployment", "seasonal"
        ],
        "severity_keywords": {
            "critical": ["fraud", "misrepresentation"],
            "high": ["gap in employment", "income decline", "unstable"],
            "medium": ["new job", "variable income", "seasonal"],
        }
    },
    "employment": {
        "triggers": [
            "probation", "contract", "temporary", "seasonal",
            "self-employed", "business owner", "gig economy",
            "multiple jobs", "changing jobs"
        ],
        "severity_keywords": {
            "high": ["probation period", "temporary position", "job ending"],
            "medium": ["contract work", "gig economy", "multiple employers"],
        }
    },
    "property": {
        "triggers": [
            "flip", "investment", "non-warrantable", "mixed use",
            "commercial", "unique property", "rural", "manufactured",
            "condition issues", "repairs needed", "as-is"
        ],
        "severity_keywords": {
            "high": ["non-warrantable", "major repairs", "structural issues"],
            "medium": ["investment property", "mixed use", "rural"],
        }
    },
    "compliance": {
        "triggers": [
            "cash", "large deposit", "gift", "down payment assistance",
            "seller concession", "interested party", "related party",
            "straw buyer", "occupancy", "primary residence"
        ],
        "severity_keywords": {
            "critical": ["straw buyer", "occupancy fraud", "income fraud"],
            "high": ["undisclosed debt", "undisclosed property", "large deposits"],
            "medium": ["gift funds", "seller concessions"],
        }
    },
}


# Standard conditions by category
STANDARD_CONDITIONS = {
    "income_verification": {
        "voe": "Verbal Verification of Employment within 10 days of closing",
        "ytd_paystub": "Most recent 30-day paystub showing YTD earnings",
        "tax_transcripts": "IRS Tax Transcripts (4506-C) for most recent 2 years",
    },
    "asset_verification": {
        "source_large_deposit": "Source and document any deposits over $500",
        "gift_letter": "Gift letter with donor statement showing source of funds",
        "asset_seasoning": "60-day asset seasoning documentation",
    },
    "credit": {
        "loe_credit": "Letter of explanation for credit inquiries",
        "loe_lates": "Letter of explanation for late payments",
        "credit_supplement": "Credit supplement for recent activity",
    },
    "property": {
        "appraisal_conditions": "Subject to satisfactory completion of repairs",
        "condo_questionnaire": "Completed condo questionnaire",
        "flood_certification": "Flood zone certification",
    },
    "compliance": {
        "identity_verification": "Clear copy of government-issued ID",
        "occupancy_affidavit": "Signed occupancy affidavit",
        "anti_steering": "Anti-steering disclosure acknowledgment",
    },
}


class UnderwriterAgent(BaseCallAgent):
    """
    Underwriter Agent for risk analysis and condition identification.

    Outputs:
    - risk_flag: Risk factors identified from conversation
    - uw_note: Underwriter notes and observations
    - condition: Suggested loan conditions
    """

    @property
    def agent_type(self) -> str:
        return "underwriter"

    @property
    def system_prompt(self) -> str:
        return """You are an expert mortgage underwriter analyst. Your job is to analyze call transcripts between loan officers and borrowers to identify potential risks, red flags, and compliance concerns.

You must identify:
1. Credit risks (bankruptcies, foreclosures, payment history issues)
2. Income risks (unstable employment, variable income, gaps)
3. Employment risks (job changes, self-employment complexities)
4. Property risks (condition, eligibility, valuation concerns)
5. Compliance concerns (fraud indicators, occupancy issues, undisclosed information)
6. Documentation that will be needed to mitigate risks
7. Conditions that should be placed on the loan

Be thorough and conservative. Flag anything that could cause issues in underwriting.
When in doubt, flag it for review.

IMPORTANT: Respond with a JSON object in the following format:
```json
{
    "risk_flags": [
        {
            "category": "credit/income/employment/property/compliance",
            "severity": "low/medium/high/critical",
            "title": "Brief title of the risk",
            "description": "Detailed description of the risk",
            "evidence": "Quote or reference from transcript",
            "recommended_action": "What should be done to address this"
        }
    ],
    "suggested_conditions": [
        {
            "condition_type": "prior_to_docs/prior_to_funding/prior_to_closing",
            "category": "income/assets/credit/property/compliance",
            "title": "Condition title",
            "description": "Full condition text",
            "reason": "Why this condition is needed",
            "related_risk": "Which risk flag this addresses (if any)"
        }
    ],
    "uw_notes": [
        {
            "category": "observation/concern/positive/action_needed",
            "note": "Underwriter note text",
            "priority": "high/medium/low"
        }
    ],
    "overall_assessment": {
        "risk_level": "low/moderate/elevated/high",
        "key_concerns": ["List of main concerns"],
        "strengths": ["List of positive factors"],
        "recommendation": "approve/approve_with_conditions/additional_review/decline_risk"
    }
}
```"""

    def build_user_prompt(self, context: Dict[str, Any]) -> str:
        transcript = context.get('transcript', '')
        transcript = self._truncate_transcript(transcript)

        participants = self._format_participants(context.get('participants', []))
        loan_context = self._format_loan_context(context.get('loan'))
        lead_context = self._format_lead_context(context.get('lead'))

        # Build detailed loan context for UW analysis
        loan_details = ""
        if context.get('loan'):
            loan = context['loan']
            loan_details = f"""
## Loan Details (for risk assessment)
- Loan Type: {loan.get('loan_type', 'Unknown')}
- Loan Amount: ${loan.get('loan_amount', 0):,.2f}
- Property Type: {loan.get('property_type', 'Unknown')}
- Occupancy: {loan.get('occupancy_type', 'Unknown')}
- LTV: {loan.get('ltv', 'Unknown')}%
- DTI: {loan.get('dti', 'Unknown')}%
- Credit Score: {loan.get('credit_score', 'Unknown')}
- Employment Type: {loan.get('employment_type', 'Unknown')}
"""

        prompt = f"""Analyze the following mortgage call transcript from an underwriting perspective. Identify all potential risks, red flags, and compliance concerns.

## Call Participants
{participants}

{loan_details if loan_details else loan_context if context.get('loan') else lead_context}

## Call Transcript
{transcript}

---

Perform a thorough underwriting risk analysis. Identify all risks, suggest conditions, and provide your assessment.

Focus on:
1. Any statements that could indicate credit issues
2. Income stability and verification concerns
3. Employment status and history
4. Property-related risks
5. Compliance red flags (occupancy, fraud indicators, undisclosed information)
6. Anything the borrower mentioned that requires documentation or verification

Respond in the JSON format specified. Be conservative - it's better to flag something for review than to miss a potential issue."""

        return prompt

    def parse_response(self, response_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Underwriter agent response into artifacts."""
        artifacts = []

        # Try to extract JSON
        parsed = self._extract_json_from_response(response_text)

        if not parsed:
            logger.warning("Underwriter agent: Could not parse JSON response")
            # Create a basic note artifact with the raw response
            artifacts.append({
                'type': 'uw_note',
                'title': 'Underwriter Analysis',
                'content': response_text,
                'structured_data': {},
                'confidence': 0.5,
            })
            return artifacts

        # Create risk flag artifacts
        for risk in parsed.get('risk_flags', []):
            risk_artifact = {
                'type': 'risk_flag',
                'title': risk.get('title', 'Risk Flag'),
                'content': risk.get('description', ''),
                'structured_data': {
                    'risk_category': risk.get('category'),
                    'severity': risk.get('severity', 'medium'),
                    'recommended_action': risk.get('recommended_action'),
                },
                'evidence': risk.get('evidence'),
                'priority': self._severity_to_priority(risk.get('severity', 'medium')),
                'confidence': 0.85,
            }
            artifacts.append(risk_artifact)

        # Create condition artifacts
        for condition in parsed.get('suggested_conditions', []):
            condition_artifact = {
                'type': 'condition',
                'title': condition.get('title', 'Loan Condition'),
                'content': condition.get('description', ''),
                'structured_data': {
                    'condition_type': condition.get('condition_type', 'prior_to_docs'),
                    'category': condition.get('category'),
                    'reason': condition.get('reason'),
                    'related_risk': condition.get('related_risk'),
                },
                'priority': 'high' if condition.get('condition_type') == 'prior_to_docs' else 'medium',
                'confidence': 0.8,
            }
            artifacts.append(condition_artifact)

        # Create UW note artifacts
        for note in parsed.get('uw_notes', []):
            note_artifact = {
                'type': 'uw_note',
                'title': f"UW Note: {note.get('category', 'Observation').title()}",
                'content': note.get('note', ''),
                'structured_data': {
                    'note_category': note.get('category'),
                    'priority': note.get('priority', 'medium'),
                },
                'priority': note.get('priority', 'medium'),
                'confidence': 0.85,
            }
            artifacts.append(note_artifact)

        # Create overall assessment artifact
        assessment = parsed.get('overall_assessment', {})
        if assessment:
            assessment_artifact = {
                'type': 'uw_note',
                'title': 'Overall Risk Assessment',
                'content': self._format_assessment(assessment),
                'structured_data': {
                    'note_category': 'assessment',
                    'risk_level': assessment.get('risk_level'),
                    'recommendation': assessment.get('recommendation'),
                    'key_concerns': assessment.get('key_concerns', []),
                    'strengths': assessment.get('strengths', []),
                },
                'priority': 'high',
                'confidence': 0.9,
            }
            artifacts.append(assessment_artifact)

        # Infer additional conditions based on risk flags
        additional_conditions = self._infer_conditions_from_risks(
            parsed.get('risk_flags', []),
            context
        )
        for condition in additional_conditions:
            # Check if similar condition already exists
            existing = [a for a in artifacts if a['type'] == 'condition' and
                       a['structured_data'].get('category') == condition['structured_data'].get('category')]
            if not existing:
                artifacts.append(condition)

        return artifacts

    def _severity_to_priority(self, severity: str) -> str:
        """Convert severity level to priority."""
        mapping = {
            'critical': 'high',
            'high': 'high',
            'medium': 'medium',
            'low': 'low',
        }
        return mapping.get(severity.lower(), 'medium')

    def _format_assessment(self, assessment: Dict) -> str:
        """Format overall assessment as readable text."""
        lines = []

        risk_level = assessment.get('risk_level', 'unknown')
        lines.append(f"Risk Level: {risk_level.upper()}")
        lines.append("")

        if assessment.get('key_concerns'):
            lines.append("Key Concerns:")
            for concern in assessment['key_concerns']:
                lines.append(f"  - {concern}")
            lines.append("")

        if assessment.get('strengths'):
            lines.append("Strengths:")
            for strength in assessment['strengths']:
                lines.append(f"  + {strength}")
            lines.append("")

        recommendation = assessment.get('recommendation', '')
        if recommendation:
            rec_display = recommendation.replace('_', ' ').title()
            lines.append(f"Recommendation: {rec_display}")

        return "\n".join(lines)

    def _infer_conditions_from_risks(self, risks: List[Dict], context: Dict) -> List[Dict]:
        """Infer standard conditions based on identified risks."""
        conditions = []
        categories_addressed = set()

        for risk in risks:
            category = risk.get('category', '').lower()
            severity = risk.get('severity', 'medium').lower()

            # Skip if we already have conditions for this category
            if category in categories_addressed:
                continue

            if category == 'income' and severity in ['high', 'critical']:
                conditions.append({
                    'type': 'condition',
                    'title': 'Verbal VOE Required',
                    'content': STANDARD_CONDITIONS['income_verification']['voe'],
                    'structured_data': {
                        'condition_type': 'prior_to_funding',
                        'category': 'income',
                        'reason': 'Income risk identified - verbal verification required',
                    },
                    'priority': 'high',
                    'confidence': 0.9,
                })
                categories_addressed.add('income')

            elif category == 'credit':
                conditions.append({
                    'type': 'condition',
                    'title': 'Credit Letter of Explanation',
                    'content': STANDARD_CONDITIONS['credit']['loe_credit'],
                    'structured_data': {
                        'condition_type': 'prior_to_docs',
                        'category': 'credit',
                        'reason': 'Credit concerns identified - explanation required',
                    },
                    'priority': 'high',
                    'confidence': 0.85,
                })
                categories_addressed.add('credit')

            elif category == 'compliance' and severity in ['high', 'critical']:
                conditions.append({
                    'type': 'condition',
                    'title': 'Occupancy Affidavit',
                    'content': STANDARD_CONDITIONS['compliance']['occupancy_affidavit'],
                    'structured_data': {
                        'condition_type': 'prior_to_docs',
                        'category': 'compliance',
                        'reason': 'Compliance concern - occupancy verification required',
                    },
                    'priority': 'high',
                    'confidence': 0.9,
                })
                categories_addressed.add('compliance')

        # Check for large deposit mentions in transcript
        loan = context.get('loan', {})
        if loan.get('has_large_deposits') or any(
            'large deposit' in r.get('description', '').lower() or
            'deposit' in r.get('title', '').lower()
            for r in risks
        ):
            if 'assets' not in categories_addressed:
                conditions.append({
                    'type': 'condition',
                    'title': 'Source Large Deposits',
                    'content': STANDARD_CONDITIONS['asset_verification']['source_large_deposit'],
                    'structured_data': {
                        'condition_type': 'prior_to_docs',
                        'category': 'assets',
                        'reason': 'Large deposits mentioned - sourcing required',
                    },
                    'priority': 'high',
                    'confidence': 0.9,
                })

        return conditions
