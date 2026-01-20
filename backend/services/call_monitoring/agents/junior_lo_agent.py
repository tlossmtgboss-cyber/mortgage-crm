"""
Junior LO Agent

AI agent that processes call transcripts to:
- Extract 1003/URLA intake fields
- Identify required documents based on loan scenario
- Suggest pricing scenarios discussed
"""

import logging
from typing import Dict, List, Any
import json

from .base_agent import BaseCallAgent, AgentResult

logger = logging.getLogger(__name__)


# Document types mapped to triggering keywords/scenarios
DOCUMENT_RULES = {
    "paystubs": {
        "triggers": ["w2 employee", "salaried", "hourly", "paycheck", "pay stub"],
        "description": "Most recent 30 days of pay stubs",
    },
    "w2": {
        "triggers": ["w2 employee", "w-2", "employed", "employer"],
        "description": "W-2 forms for past 2 years",
    },
    "tax_returns": {
        "triggers": ["self-employed", "1099", "business owner", "commission", "bonus over 25%", "rental income"],
        "description": "Federal tax returns for past 2 years",
    },
    "bank_statements": {
        "triggers": ["bank statement", "assets", "down payment", "closing costs", "reserves"],
        "description": "Bank statements for past 2 months",
    },
    "gift_letter": {
        "triggers": ["gift", "family help", "parents helping", "gift funds"],
        "description": "Gift letter with donor information",
    },
    "purchase_contract": {
        "triggers": ["purchase", "buying", "offer accepted", "under contract"],
        "description": "Fully executed purchase contract",
    },
    "drivers_license": {
        "triggers": ["id", "identification", "verify identity"],
        "description": "Valid driver's license or government ID",
    },
    "social_security_card": {
        "triggers": ["ssn", "social security"],
        "description": "Social Security card",
    },
    "va_certificate": {
        "triggers": ["va", "veteran", "military", "coe"],
        "description": "VA Certificate of Eligibility (COE)",
    },
    "divorce_decree": {
        "triggers": ["divorce", "divorced", "alimony", "child support"],
        "description": "Divorce decree and settlement agreement",
    },
    "bankruptcy_discharge": {
        "triggers": ["bankruptcy", "chapter 7", "chapter 13"],
        "description": "Bankruptcy discharge papers",
    },
    "rental_agreement": {
        "triggers": ["rental income", "investment property", "landlord", "tenant"],
        "description": "Current lease agreements",
    },
    "business_license": {
        "triggers": ["self-employed", "business owner", "llc", "corporation"],
        "description": "Business license and registration",
    },
    "profit_loss": {
        "triggers": ["self-employed", "business owner", "year to date"],
        "description": "Year-to-date profit and loss statement",
    },
}


class JuniorLOAgent(BaseCallAgent):
    """
    Junior LO Agent for intake field extraction and document identification.

    Outputs:
    - intake_field: 1003/URLA field values extracted from conversation
    - document_request: Documents needed based on loan scenario
    - pricing_scenario: Pricing scenarios discussed
    """

    @property
    def agent_type(self) -> str:
        return "junior_lo"

    @property
    def system_prompt(self) -> str:
        return """You are an expert junior loan officer assistant. Your job is to analyze call transcripts and extract loan application information.

You must identify:
1. Personal information mentioned (names, contact info, SSN, DOB)
2. Employment details (employer, position, income, years employed)
3. Property information (address, type, value, intended use)
4. Financial details (assets, debts, down payment, credit score)
5. Loan parameters discussed (amount, term, type, rate)
6. Documents that will be needed based on the conversation
7. Any pricing scenarios or rate quotes discussed

Be thorough but only extract information that is clearly stated. Mark confidence levels.

IMPORTANT: Respond with a JSON object in the following format:
```json
{
    "intake_fields": [
        {
            "field_name": "Human readable field name",
            "field_path": "database_column_name",
            "value": "Extracted value",
            "confidence": 0.0-1.0,
            "evidence": "Quote from transcript"
        }
    ],
    "document_requests": [
        {
            "document_type": "Document type code",
            "document_name": "Human readable name",
            "reason": "Why this document is needed",
            "priority": "high/medium/low",
            "evidence": "What in the call triggered this"
        }
    ],
    "pricing_scenarios": [
        {
            "loan_amount": 0,
            "loan_term": 30,
            "loan_type": "Conventional/FHA/VA/etc.",
            "interest_rate": 0.0,
            "points": 0,
            "monthly_payment": 0,
            "notes": "Any additional context"
        }
    ],
    "borrower_profile": {
        "employment_type": "W2/Self-Employed/Retired/etc.",
        "income_sources": ["List of income sources"],
        "property_use": "Primary/Secondary/Investment",
        "estimated_credit": "Excellent/Good/Fair/Poor or score",
        "first_time_buyer": true/false/null
    }
}
```"""

    def build_user_prompt(self, context: Dict[str, Any]) -> str:
        transcript = context.get('transcript', '')
        transcript = self._truncate_transcript(transcript)

        participants = self._format_participants(context.get('participants', []))
        loan_context = self._format_loan_context(context.get('loan'))
        lead_context = self._format_lead_context(context.get('lead'))

        # Include current known data for comparison
        current_data = ""
        if context.get('loan'):
            loan = context['loan']
            current_data = f"""
## Current Loan Data (for reference)
- Borrower Name: {loan.get('borrower_name', 'Unknown')}
- Loan Amount: ${loan.get('loan_amount', 0):,.2f}
- Loan Type: {loan.get('loan_type', 'Unknown')}
- Property: {loan.get('property_address', 'Unknown')}
- Credit Score: {loan.get('credit_score', 'Unknown')}
"""
        elif context.get('lead'):
            lead = context['lead']
            current_data = f"""
## Current Lead Data (for reference)
- Name: {lead.get('name', 'Unknown')}
- Email: {lead.get('email', 'Unknown')}
- Phone: {lead.get('phone', 'Unknown')}
- Stage: {lead.get('stage', 'Unknown')}
"""

        prompt = f"""Analyze the following mortgage call transcript and extract all loan application information discussed.

## Call Participants
{participants}
{current_data}

## Call Transcript
{transcript}

---

Extract all intake fields, identify needed documents, and note any pricing scenarios discussed.
Respond in the JSON format specified.

Note: Only extract information that was clearly stated in the conversation. Do not infer or assume values."""

        return prompt

    def parse_response(self, response_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Junior LO agent response into artifacts."""
        artifacts = []

        # Try to extract JSON
        parsed = self._extract_json_from_response(response_text)

        if not parsed:
            logger.warning("Junior LO agent: Could not parse JSON response")
            return artifacts

        # Create intake field artifacts
        for field in parsed.get('intake_fields', []):
            if field.get('value') is not None:
                field_artifact = {
                    'type': 'intake_field',
                    'title': f"Update: {field.get('field_name', 'Unknown Field')}",
                    'content': f"{field.get('field_name')}: {field.get('value')}",
                    'structured_data': {
                        'field_name': field.get('field_name'),
                        'field_path': field.get('field_path'),
                        'proposed_value': field.get('value'),
                    },
                    'evidence': field.get('evidence'),
                    'confidence': field.get('confidence', 0.7),
                }
                artifacts.append(field_artifact)

        # Create document request artifacts
        for doc in parsed.get('document_requests', []):
            doc_artifact = {
                'type': 'document_request',
                'title': doc.get('document_name', doc.get('document_type', 'Document')),
                'content': doc.get('reason', ''),
                'structured_data': {
                    'document_type': doc.get('document_type'),
                    'document_name': doc.get('document_name'),
                    'reason': doc.get('reason'),
                },
                'evidence': doc.get('evidence'),
                'priority': doc.get('priority', 'medium'),
                'confidence': 0.85,
            }
            artifacts.append(doc_artifact)

        # Create pricing scenario artifacts
        for scenario in parsed.get('pricing_scenarios', []):
            scenario_artifact = {
                'type': 'pricing_scenario',
                'title': f"Pricing: ${scenario.get('loan_amount', 0):,.0f} {scenario.get('loan_type', '')}",
                'content': self._format_pricing_scenario(scenario),
                'structured_data': scenario,
                'confidence': 0.8,
            }
            artifacts.append(scenario_artifact)

        # Add additional document requests based on borrower profile
        borrower_profile = parsed.get('borrower_profile', {})
        additional_docs = self._infer_documents_from_profile(borrower_profile, context)
        for doc in additional_docs:
            # Check if already requested
            existing = [a for a in artifacts if a['type'] == 'document_request' and
                       a['structured_data'].get('document_type') == doc['document_type']]
            if not existing:
                artifacts.append(doc)

        return artifacts

    def _format_pricing_scenario(self, scenario: Dict) -> str:
        """Format a pricing scenario as readable text."""
        lines = []

        if scenario.get('loan_amount'):
            lines.append(f"Loan Amount: ${scenario['loan_amount']:,.2f}")
        if scenario.get('loan_type'):
            lines.append(f"Loan Type: {scenario['loan_type']}")
        if scenario.get('loan_term'):
            lines.append(f"Term: {scenario['loan_term']} years")
        if scenario.get('interest_rate'):
            lines.append(f"Rate: {scenario['interest_rate']}%")
        if scenario.get('points') is not None:
            lines.append(f"Points: {scenario['points']}")
        if scenario.get('monthly_payment'):
            lines.append(f"Est. Payment: ${scenario['monthly_payment']:,.2f}")
        if scenario.get('notes'):
            lines.append(f"Notes: {scenario['notes']}")

        return "\n".join(lines)

    def _infer_documents_from_profile(self, profile: Dict, context: Dict) -> List[Dict]:
        """Infer additional required documents based on borrower profile."""
        documents = []

        employment_type = (profile.get('employment_type') or '').lower()
        income_sources = [s.lower() for s in profile.get('income_sources', [])]
        property_use = (profile.get('property_use') or '').lower()

        # Self-employed documentation
        if 'self-employed' in employment_type or 'self employed' in employment_type:
            documents.append({
                'type': 'document_request',
                'title': 'Business Tax Returns',
                'content': 'Required for self-employed borrowers',
                'structured_data': {
                    'document_type': 'business_tax_returns',
                    'document_name': 'Business Tax Returns (2 years)',
                    'reason': 'Self-employment income verification',
                },
                'priority': 'high',
                'confidence': 0.9,
            })
            documents.append({
                'type': 'document_request',
                'title': 'Year-to-Date P&L',
                'content': 'Required for self-employed borrowers',
                'structured_data': {
                    'document_type': 'profit_loss',
                    'document_name': 'Year-to-Date Profit & Loss Statement',
                    'reason': 'Current year income verification',
                },
                'priority': 'high',
                'confidence': 0.9,
            })

        # Rental income documentation
        if 'rental' in ' '.join(income_sources) or 'investment' in property_use:
            documents.append({
                'type': 'document_request',
                'title': 'Lease Agreements',
                'content': 'Required for rental income verification',
                'structured_data': {
                    'document_type': 'rental_agreement',
                    'document_name': 'Current Lease Agreements',
                    'reason': 'Rental income documentation',
                },
                'priority': 'medium',
                'confidence': 0.85,
            })

        # VA loan documentation
        loan = context.get('loan', {})
        if loan.get('loan_type', '').upper() == 'VA':
            documents.append({
                'type': 'document_request',
                'title': 'VA Certificate of Eligibility',
                'content': 'Required for VA loans',
                'structured_data': {
                    'document_type': 'va_certificate',
                    'document_name': 'VA Certificate of Eligibility (COE)',
                    'reason': 'Required for VA loan program',
                },
                'priority': 'high',
                'confidence': 0.95,
            })

        return documents
