"""
Junior LO Agent - Enhanced Version

Expert-level AI agent for loan application intake and document identification.
Includes:
- Complete 1003/URLA field extraction with proper field mappings
- Document requirements based on loan scenario and program
- Pricing scenario capture
- Few-shot examples for consistent extraction
- Confidence calibration based on evidence quality
"""

import logging
from typing import Dict, List, Any
import json

from .base_agent import BaseCallAgent, AgentResult
from .mortgage_knowledge import (
    URLA_FIELDS,
    LOAN_PROGRAM_GUIDELINES,
    DOCUMENT_REQUIREMENTS,
    FEW_SHOT_EXAMPLES,
)

logger = logging.getLogger(__name__)


class JuniorLOAgent(BaseCallAgent):
    """
    Expert Junior LO Agent for intake field extraction and document identification.

    Capabilities:
    - Complete 1003/URLA field extraction with proper database mappings
    - Document requirement identification based on loan scenario
    - Pricing scenario capture from rate discussions
    - Borrower profile assessment

    Enhanced with:
    - Full URLA field schema knowledge
    - Loan program-specific document requirements
    - Few-shot examples for consistent extraction
    - Confidence calibration based on evidence quality
    """

    @property
    def agent_type(self) -> str:
        return "junior_lo"

    @property
    def system_prompt(self) -> str:
        # Build few-shot example
        example = FEW_SHOT_EXAMPLES.get("junior_lo_extraction", {})
        example_input = example.get("input", "")
        example_output = json.dumps(example.get("output", {}), indent=2)

        # Build URLA field reference (key fields only for prompt length)
        urla_reference = self._build_urla_reference()

        # Build document requirements reference
        doc_reference = self._build_document_reference()

        return f"""You are an expert Junior Loan Officer with deep knowledge of the 1003/URLA application form and mortgage documentation requirements. Your role is to extract application data from call transcripts with precision and identify all required documents.

## YOUR EXPERTISE INCLUDES:
- Complete understanding of Uniform Residential Loan Application (URLA/1003)
- Knowledge of documentation requirements for all loan programs
- Understanding of income calculation methods
- Awareness of Fannie Mae/Freddie Mac eligibility requirements

## 1003/URLA FIELD REFERENCE:
{urla_reference}

## DOCUMENT REQUIREMENTS BY SCENARIO:
{doc_reference}

## EXTRACTION PROCESS (Think step-by-step):

1. **Listen for Borrower Information**: Names, SSN (last 4), DOB, contact info, citizenship
2. **Identify Employment Details**: Employer name, position, tenure, income type (W-2, 1099, SE)
3. **Capture Income Figures**: Base salary, overtime, bonus, commission, rental, other
4. **Note Asset Information**: Bank accounts, investments, retirement, gift funds
5. **Record Property Details**: Address, type, use (primary/secondary/investment), value
6. **Extract Loan Parameters**: Amount, type, purpose, term, rate discussed
7. **Identify Document Needs**: Based on income type, property type, loan program

## FEW-SHOT EXAMPLE:

**Input Transcript:**
{example_input}

**Expected Output:**
```json
{example_output}
```

## THE 5 C'S OF CREDIT ANALYSIS FRAMEWORK:

Your analysis MUST include assessment of the 5 C's of Credit based on what was discussed:

1. **CREDIT** - Credit history and score
   - Credit score mentioned or estimated tier
   - Payment history issues discussed
   - Derogatory items (late payments, collections, bankruptcy)
   - Credit utilization concerns

2. **COLLATERAL** - Property being financed
   - Property type and condition
   - Property value discussed
   - Location and marketability
   - LTV ratio implications

3. **CAPACITY** - Ability to repay
   - Income stability and documentation
   - DTI ratio (discussed or calculated)
   - Employment tenure
   - Other financial obligations mentioned

4. **CHARACTERISTICS** - Borrower stability factors
   - Employment history and stability
   - Time in residence
   - Banking relationships
   - Overall financial behavior patterns

5. **CASH** - Reserves and down payment
   - Down payment source and amount
   - Reserves after closing
   - Gift funds discussed
   - Asset verification needs

## YOUR OUTPUT FORMAT:

Respond with a JSON object in this exact format:
```json
{{
    "intake_fields": [
        {{
            "field_name": "Human readable field name",
            "field_path": "Section.field_name (e.g., borrower.first_name)",
            "urla_section": "1a/1b/2/3/etc.",
            "value": "Extracted value exactly as stated",
            "confidence": 0.0-1.0,
            "evidence": "Exact quote from transcript"
        }}
    ],
    "document_requests": [
        {{
            "document_type": "document_code",
            "document_name": "Human readable document name",
            "reason": "Why this document is needed",
            "loan_program_required": true/false,
            "priority": "high/medium/low",
            "evidence": "What in the call triggered this requirement"
        }}
    ],
    "five_c_analysis": {{
        "credit": {{
            "score": null,
            "tier": "Excellent/Good/Fair/Poor/Unknown",
            "issues": ["List of credit issues discussed"],
            "assessment": "Strong/Adequate/Weak/Unknown",
            "notes": "Summary of credit discussion"
        }},
        "collateral": {{
            "property_type": "SFR/Condo/Townhouse/Multi/etc.",
            "property_value": null,
            "ltv": null,
            "assessment": "Strong/Adequate/Weak/Unknown",
            "notes": "Property-related observations"
        }},
        "capacity": {{
            "dti": null,
            "income_stability": "Stable/Variable/Uncertain/Unknown",
            "employment_tenure": null,
            "assessment": "Strong/Adequate/Weak/Unknown",
            "notes": "Income and repayment ability observations"
        }},
        "characteristics": {{
            "employment_years": null,
            "residence_years": null,
            "financial_stability": "Stable/Variable/Unknown",
            "assessment": "Strong/Adequate/Weak/Unknown",
            "notes": "Borrower stability factors"
        }},
        "cash": {{
            "down_payment_pct": null,
            "reserves_months": null,
            "down_payment_source": "Savings/Gift/Sale of Home/Other/Unknown",
            "assets_discussed": [],
            "assessment": "Strong/Adequate/Weak/Unknown",
            "notes": "Cash and reserves observations"
        }}
    }},
    "review_items": [
        {{
            "category": "credit/collateral/capacity/characteristics/cash",
            "item": "What needs to be addressed",
            "priority": "high/medium/low",
            "action_required": "Specific action needed"
        }}
    ],
    "pricing_scenarios": [
        {{
            "loan_amount": 0,
            "loan_term": 30,
            "loan_type": "Conventional/FHA/VA/USDA",
            "interest_rate": 0.00,
            "apr": 0.00,
            "points": 0.00,
            "monthly_pi": 0,
            "estimated_piti": 0,
            "ltv": 0,
            "notes": "Any additional context"
        }}
    ],
    "borrower_profile": {{
        "employment_type": "W2/Self-Employed/Retired/Mixed",
        "years_in_profession": 0,
        "income_sources": ["List of all income sources mentioned"],
        "monthly_income_discussed": 0,
        "property_use": "Primary/Secondary/Investment",
        "loan_purpose": "Purchase/Refinance/Cash-Out",
        "estimated_credit_tier": "Excellent/Good/Fair/Poor",
        "credit_score_mentioned": null,
        "first_time_buyer": true/false/null,
        "citizen_status": "US Citizen/Permanent Resident/Non-Permanent/Unknown"
    }},
    "data_quality_notes": "Any concerns about data quality, contradictions, or missing critical info"
}}
```

## EXTRACTION GUIDELINES:

1. **Be Precise**: Use exact values stated - don't round or estimate
2. **Quote Evidence**: Include the exact phrase where information was stated
3. **Map to URLA**: Use proper field paths that match 1003 sections
4. **Flag Uncertainty**: Lower confidence when information is partial or unclear
5. **Don't Assume**: Only extract what is explicitly stated
6. **Note Contradictions**: If borrower gives conflicting info, note in data_quality_notes

## CONFIDENCE SCORING:

- **0.95+**: Explicitly stated with clear context
- **0.85-0.94**: Clearly stated but context is partial
- **0.70-0.84**: Inferred from conversation but not explicitly stated
- **0.50-0.69**: Mentioned in passing, may need verification
- **Below 0.50**: Do not include - too uncertain"""

    def _build_urla_reference(self) -> str:
        """Build a compact URLA field reference for the prompt."""
        sections = []

        # Section 1a - Borrower Information
        sections.append("""**Section 1a - Borrower Information:**
- first_name, middle_name, last_name, suffix
- social_security_number (last 4 only typically discussed)
- date_of_birth, citizenship_status
- contact_info: email, phone, current_address""")

        # Section 1b - Current Address
        sections.append("""**Section 1b - Current Address:**
- street_address, unit, city, state, zip
- housing_type: Own/Rent/No Payment
- years_at_address, monthly_rent (if renting)""")

        # Section 2 - Employment
        sections.append("""**Section 2 - Employment Information:**
- employer_name, employer_address, employer_phone
- position_title, start_date, years_in_profession
- self_employed: true/false
- monthly_income: base, overtime, bonus, commission, other""")

        # Section 3 - Income
        sections.append("""**Section 3 - Monthly Income:**
- base_employment_income
- overtime, bonus, commission (if applicable)
- self_employment_income
- rental_income, social_security, pension, other""")

        # Section 4 - Assets
        sections.append("""**Section 4 - Assets:**
- checking_accounts, savings_accounts (bank name, balance)
- retirement_accounts (401k, IRA)
- stocks_bonds, real_estate_owned
- gift_funds (donor relationship, amount)""")

        # Section 5 - Liabilities
        sections.append("""**Section 5 - Liabilities:**
- current_mortgage (lender, balance, payment)
- auto_loans, student_loans, credit_cards
- other_debts, alimony, child_support""")

        # Section 6 - Property
        sections.append("""**Section 6 - Property & Loan:**
- property_address, property_type (SFR/Condo/Multi/etc.)
- occupancy_type: Primary/Secondary/Investment
- purchase_price, down_payment_amount, down_payment_source
- loan_amount, loan_type, loan_term, loan_purpose""")

        return "\n\n".join(sections)

    def _build_document_reference(self) -> str:
        """Build document requirements reference for the prompt."""
        doc_sections = []

        for category, docs in DOCUMENT_REQUIREMENTS.items():
            category_name = category.replace("_", " ").title()
            doc_list = ", ".join(docs[:5])  # Limit to first 5 for brevity
            if len(docs) > 5:
                doc_list += f", +{len(docs) - 5} more"
            doc_sections.append(f"**{category_name}**: {doc_list}")

        return "\n".join(doc_sections)

    def build_user_prompt(self, context: Dict[str, Any]) -> str:
        transcript = context.get('transcript', '')
        transcript = self._truncate_transcript(transcript, max_words=5000)

        participants = self._format_participants(context.get('participants', []))
        loan_context = self._format_loan_context(context.get('loan'))
        lead_context = self._format_lead_context(context.get('lead'))

        # Include current known data for comparison
        current_data = ""
        if context.get('loan'):
            loan = context['loan']
            current_data = f"""
## EXISTING LOAN FILE DATA (compare for updates/confirmations)
- Borrower: {loan.get('borrower_name', 'Unknown')}
- Property: {loan.get('property_address', 'Unknown')}
- Loan Amount: ${loan.get('loan_amount', 0):,.2f}
- Loan Type: {loan.get('loan_type', 'Unknown')}
- Loan Purpose: {loan.get('loan_purpose', 'Unknown')}
- Credit Score on File: {loan.get('credit_score', 'Unknown')}
- Current Stage: {loan.get('status', 'Unknown')}

IMPORTANT: Flag any information that differs from what's on file."""

        elif context.get('lead'):
            lead = context['lead']
            current_data = f"""
## EXISTING LEAD DATA
- Name: {lead.get('name', 'Unknown')}
- Email: {lead.get('email', 'Unknown')}
- Phone: {lead.get('phone', 'Unknown')}
- Source: {lead.get('source', 'Unknown')}
- Stage: {lead.get('stage', 'New')}

NOTE: This may be a new application - extract all information mentioned."""

        # Loan program context if known
        loan_program_context = ""
        loan = context.get('loan', {})
        loan_type = loan.get('loan_type', '').upper()
        if loan_type in LOAN_PROGRAM_GUIDELINES:
            guidelines = LOAN_PROGRAM_GUIDELINES[loan_type]
            loan_program_context = f"""
## LOAN PROGRAM: {loan_type}
- Max LTV (Purchase): {guidelines.get('max_ltv', {}).get('purchase', 'N/A')}%
- Max DTI: {guidelines.get('max_dti', {}).get('standard', 'N/A')}%
- Min Credit Score: {guidelines.get('min_credit_score', {}).get('standard', 'N/A')}
Pay attention to program-specific requirements!"""

        prompt = f"""Analyze the following mortgage call transcript and extract ALL loan application information.

## Call Participants
{participants}
{current_data}
{loan_program_context}

## Call Transcript
{transcript}

---

## YOUR TASK:

Think through this step-by-step:

1. **Identify all borrower personal information** mentioned (names, DOB, SSN, contact info)
2. **Extract employment and income details** (employer, position, tenure, income figures)
3. **Note any asset information** discussed (bank accounts, retirement, down payment source)
4. **Capture property information** (address, type, value, intended use)
5. **Record loan parameters** (amount, type, rate, term discussed)
6. **List all documents needed** based on the scenario
7. **Flag any data quality concerns** (contradictions, missing critical info)

Respond with the JSON format specified in your instructions.

CRITICAL: Only extract information explicitly stated in the transcript. Do not infer or assume values that weren't mentioned."""

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
            if field.get('value') is not None and field.get('value') != '':
                # Validate confidence
                confidence = self._validate_field_confidence(field)

                field_artifact = {
                    'type': 'intake_field',
                    'title': f"Update: {field.get('field_name', 'Unknown Field')}",
                    'content': f"{field.get('field_name')}: {field.get('value')}",
                    'structured_data': {
                        'field_name': field.get('field_name'),
                        'field_path': field.get('field_path'),
                        'urla_section': field.get('urla_section'),
                        'proposed_value': field.get('value'),
                    },
                    'evidence': field.get('evidence'),
                    'confidence': confidence,
                }
                artifacts.append(field_artifact)

        # Create document request artifacts
        for doc in parsed.get('document_requests', []):
            # Validate document request
            doc_confidence = self._validate_document_confidence(doc)

            doc_artifact = {
                'type': 'document_request',
                'title': doc.get('document_name', doc.get('document_type', 'Document')),
                'content': doc.get('reason', ''),
                'structured_data': {
                    'document_type': doc.get('document_type'),
                    'document_name': doc.get('document_name'),
                    'reason': doc.get('reason'),
                    'loan_program_required': doc.get('loan_program_required', False),
                },
                'evidence': doc.get('evidence'),
                'priority': doc.get('priority', 'medium'),
                'confidence': doc_confidence,
            }
            artifacts.append(doc_artifact)

        # Create pricing scenario artifacts
        for scenario in parsed.get('pricing_scenarios', []):
            if scenario.get('loan_amount') or scenario.get('interest_rate'):
                scenario_artifact = {
                    'type': 'pricing_scenario',
                    'title': self._format_pricing_title(scenario),
                    'content': self._format_pricing_scenario(scenario),
                    'structured_data': scenario,
                    'confidence': 0.85,
                }
                artifacts.append(scenario_artifact)

        # Create borrower profile artifact if substantial info exists
        profile = parsed.get('borrower_profile', {})
        if self._has_substantial_profile(profile):
            profile_artifact = {
                'type': 'borrower_profile',
                'title': 'Borrower Profile Assessment',
                'content': self._format_borrower_profile(profile),
                'structured_data': profile,
                'confidence': 0.8,
            }
            artifacts.append(profile_artifact)

        # Add additional document requests based on borrower profile
        additional_docs = self._infer_documents_from_profile(profile, context)
        for doc in additional_docs:
            # Check if already requested
            existing = [a for a in artifacts if a['type'] == 'document_request' and
                       a['structured_data'].get('document_type') == doc['structured_data']['document_type']]
            if not existing:
                artifacts.append(doc)

        # Add data quality note if present
        quality_notes = parsed.get('data_quality_notes')
        if quality_notes and quality_notes.strip():
            note_artifact = {
                'type': 'data_quality_note',
                'title': 'Data Quality Concerns',
                'content': quality_notes,
                'structured_data': {'note': quality_notes},
                'confidence': 1.0,
                'priority': 'high',
            }
            artifacts.append(note_artifact)

        # Create 5 C's analysis artifacts
        five_c_analysis = parsed.get('five_c_analysis', {})

        # Credit
        credit_data = five_c_analysis.get('credit', {})
        if credit_data:
            credit_artifact = {
                'type': 'five_c_credit',
                'title': f"Credit Analysis - {credit_data.get('assessment', 'Unknown')}",
                'content': credit_data.get('notes', ''),
                'structured_data': {
                    'score': credit_data.get('score'),
                    'tier': credit_data.get('tier'),
                    'issues': credit_data.get('issues', []),
                    'assessment': credit_data.get('assessment', 'Unknown'),
                    'notes': credit_data.get('notes'),
                },
                'confidence': 0.85 if credit_data.get('score') else 0.70,
            }
            artifacts.append(credit_artifact)

        # Collateral
        collateral_data = five_c_analysis.get('collateral', {})
        if collateral_data:
            collateral_artifact = {
                'type': 'five_c_collateral',
                'title': f"Collateral Analysis - {collateral_data.get('assessment', 'Unknown')}",
                'content': collateral_data.get('notes', ''),
                'structured_data': {
                    'property_type': collateral_data.get('property_type'),
                    'property_value': collateral_data.get('property_value'),
                    'ltv': collateral_data.get('ltv'),
                    'assessment': collateral_data.get('assessment', 'Unknown'),
                    'notes': collateral_data.get('notes'),
                },
                'confidence': 0.85 if collateral_data.get('property_value') else 0.70,
            }
            artifacts.append(collateral_artifact)

        # Capacity
        capacity_data = five_c_analysis.get('capacity', {})
        if capacity_data:
            capacity_artifact = {
                'type': 'five_c_capacity',
                'title': f"Capacity Analysis - {capacity_data.get('assessment', 'Unknown')}",
                'content': capacity_data.get('notes', ''),
                'structured_data': {
                    'dti': capacity_data.get('dti'),
                    'income_stability': capacity_data.get('income_stability'),
                    'employment_tenure': capacity_data.get('employment_tenure'),
                    'assessment': capacity_data.get('assessment', 'Unknown'),
                    'notes': capacity_data.get('notes'),
                },
                'confidence': 0.85 if capacity_data.get('dti') else 0.70,
            }
            artifacts.append(capacity_artifact)

        # Characteristics
        char_data = five_c_analysis.get('characteristics', {})
        if char_data:
            char_artifact = {
                'type': 'five_c_characteristics',
                'title': f"Characteristics Analysis - {char_data.get('assessment', 'Unknown')}",
                'content': char_data.get('notes', ''),
                'structured_data': {
                    'employment_years': char_data.get('employment_years'),
                    'residence_years': char_data.get('residence_years'),
                    'financial_stability': char_data.get('financial_stability'),
                    'assessment': char_data.get('assessment', 'Unknown'),
                    'notes': char_data.get('notes'),
                },
                'confidence': 0.75,
            }
            artifacts.append(char_artifact)

        # Cash
        cash_data = five_c_analysis.get('cash', {})
        if cash_data:
            cash_artifact = {
                'type': 'five_c_cash',
                'title': f"Cash/Reserves Analysis - {cash_data.get('assessment', 'Unknown')}",
                'content': cash_data.get('notes', ''),
                'structured_data': {
                    'down_payment_pct': cash_data.get('down_payment_pct'),
                    'reserves_months': cash_data.get('reserves_months'),
                    'down_payment_source': cash_data.get('down_payment_source'),
                    'assets_discussed': cash_data.get('assets_discussed', []),
                    'assessment': cash_data.get('assessment', 'Unknown'),
                    'notes': cash_data.get('notes'),
                },
                'confidence': 0.85 if cash_data.get('reserves_months') else 0.70,
            }
            artifacts.append(cash_artifact)

        # Create review item tasks from 5 C's analysis
        for item in parsed.get('review_items', []):
            review_artifact = {
                'type': 'task',
                'title': f"Review: {item.get('item', 'Item to Review')}",
                'content': item.get('action_required', ''),
                'structured_data': {
                    'category': item.get('category'),
                    'item': item.get('item'),
                    'priority': item.get('priority', 'medium'),
                    'action_required': item.get('action_required'),
                    'source': 'jrlo_5c_analysis',
                },
                'priority': item.get('priority', 'medium'),
                'confidence': 0.85,
            }
            artifacts.append(review_artifact)

        # Create stacked_note artifact summarizing 5 C's analysis
        five_c_summary = self._format_five_c_summary(five_c_analysis)
        if five_c_summary:
            stacked_note_artifact = {
                'type': 'stacked_note',
                'title': 'JR LO 5 C\'s Analysis',
                'content': five_c_summary,
                'structured_data': {
                    'source': 'jrlo',
                    'analysis_type': '5_c_analysis',
                    'assessments': {
                        'credit': credit_data.get('assessment'),
                        'collateral': collateral_data.get('assessment'),
                        'capacity': capacity_data.get('assessment'),
                        'characteristics': char_data.get('assessment'),
                        'cash': cash_data.get('assessment'),
                    },
                    'key_points': [item.get('item') for item in parsed.get('review_items', [])],
                },
                'confidence': 0.80,
            }
            artifacts.append(stacked_note_artifact)

        return artifacts

    def _format_five_c_summary(self, five_c: Dict) -> str:
        """Format 5 C's analysis as a summary for stacked notes."""
        if not five_c:
            return ""

        lines = ["**5 C's ANALYSIS**\n"]

        c_mapping = [
            ('credit', 'Credit'),
            ('collateral', 'Collateral'),
            ('capacity', 'Capacity'),
            ('characteristics', 'Characteristics'),
            ('cash', 'Cash/Reserves'),
        ]

        for key, label in c_mapping:
            data = five_c.get(key, {})
            assessment = data.get('assessment', 'Unknown')
            notes = data.get('notes', '')

            # Format assessment with indicator
            if assessment == 'Strong':
                indicator = '✓'
            elif assessment == 'Adequate':
                indicator = '~'
            elif assessment == 'Weak':
                indicator = '!'
            else:
                indicator = '?'

            line = f"• **{label}** [{indicator} {assessment}]"
            if notes:
                line += f": {notes[:100]}"
            lines.append(line)

        return "\n".join(lines)

    def _validate_field_confidence(self, field: Dict) -> float:
        """Validate and adjust field confidence based on evidence quality."""
        base_confidence = field.get('confidence', 0.7)

        # Increase confidence if evidence is provided
        evidence = field.get('evidence', '')
        if evidence and len(evidence) > 20:
            base_confidence = min(base_confidence + 0.05, 0.95)

        # Decrease for certain uncertain field types
        field_path = field.get('field_path', '').lower()
        uncertain_fields = ['ssn', 'social_security', 'credit_score']
        if any(uf in field_path for uf in uncertain_fields):
            base_confidence = min(base_confidence, 0.85)

        return max(min(base_confidence, 0.95), 0.5)

    def _validate_document_confidence(self, doc: Dict) -> float:
        """Validate document request confidence."""
        base_confidence = 0.85

        # Higher confidence for program-required docs
        if doc.get('loan_program_required'):
            base_confidence = 0.95

        # Higher confidence with clear evidence
        evidence = doc.get('evidence', '')
        if evidence and len(evidence) > 20:
            base_confidence = min(base_confidence + 0.05, 0.95)

        return base_confidence

    def _format_pricing_title(self, scenario: Dict) -> str:
        """Format pricing scenario title."""
        parts = []
        if scenario.get('loan_amount'):
            parts.append(f"${scenario['loan_amount']:,.0f}")
        if scenario.get('loan_type'):
            parts.append(scenario['loan_type'])
        if scenario.get('interest_rate'):
            parts.append(f"@ {scenario['interest_rate']}%")
        return f"Pricing: {' '.join(parts)}" if parts else "Pricing Scenario"

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
            lines.append(f"Interest Rate: {scenario['interest_rate']}%")
        if scenario.get('apr'):
            lines.append(f"APR: {scenario['apr']}%")
        if scenario.get('points') is not None:
            lines.append(f"Points: {scenario['points']}")
        if scenario.get('monthly_pi'):
            lines.append(f"P&I Payment: ${scenario['monthly_pi']:,.2f}")
        if scenario.get('estimated_piti'):
            lines.append(f"Est. PITI: ${scenario['estimated_piti']:,.2f}")
        if scenario.get('ltv'):
            lines.append(f"LTV: {scenario['ltv']}%")
        if scenario.get('notes'):
            lines.append(f"Notes: {scenario['notes']}")

        return "\n".join(lines)

    def _format_borrower_profile(self, profile: Dict) -> str:
        """Format borrower profile as readable text."""
        lines = []

        if profile.get('employment_type'):
            lines.append(f"Employment: {profile['employment_type']}")
        if profile.get('years_in_profession'):
            lines.append(f"Years in Profession: {profile['years_in_profession']}")
        if profile.get('income_sources'):
            lines.append(f"Income Sources: {', '.join(profile['income_sources'])}")
        if profile.get('monthly_income_discussed'):
            lines.append(f"Monthly Income Discussed: ${profile['monthly_income_discussed']:,.2f}")
        if profile.get('property_use'):
            lines.append(f"Property Use: {profile['property_use']}")
        if profile.get('loan_purpose'):
            lines.append(f"Loan Purpose: {profile['loan_purpose']}")
        if profile.get('estimated_credit_tier'):
            lines.append(f"Credit Tier: {profile['estimated_credit_tier']}")
        if profile.get('credit_score_mentioned'):
            lines.append(f"Credit Score: {profile['credit_score_mentioned']}")
        if profile.get('first_time_buyer') is not None:
            lines.append(f"First-Time Buyer: {'Yes' if profile['first_time_buyer'] else 'No'}")

        return "\n".join(lines)

    def _has_substantial_profile(self, profile: Dict) -> bool:
        """Check if profile has enough data to be useful."""
        filled_fields = sum(1 for v in profile.values() if v is not None and v != '' and v != [])
        return filled_fields >= 3

    def _infer_documents_from_profile(self, profile: Dict, context: Dict) -> List[Dict]:
        """Infer additional required documents based on borrower profile."""
        documents = []

        employment_type = (profile.get('employment_type') or '').lower()
        income_sources = [s.lower() for s in profile.get('income_sources', [])]
        property_use = (profile.get('property_use') or '').lower()
        loan_purpose = (profile.get('loan_purpose') or '').lower()

        # Self-employed documentation
        if 'self-employed' in employment_type or 'self employed' in employment_type:
            documents.append({
                'type': 'document_request',
                'title': 'Business Tax Returns',
                'content': 'Required for self-employed borrowers - 2 most recent years',
                'structured_data': {
                    'document_type': 'business_tax_returns',
                    'document_name': 'Business Tax Returns (2 years)',
                    'reason': 'Self-employment income verification per Fannie Mae guidelines',
                    'loan_program_required': True,
                },
                'priority': 'high',
                'confidence': 0.95,
            })
            documents.append({
                'type': 'document_request',
                'title': 'Year-to-Date P&L',
                'content': 'Required for self-employed borrowers when > 3 months into current year',
                'structured_data': {
                    'document_type': 'profit_loss',
                    'document_name': 'Year-to-Date Profit & Loss Statement',
                    'reason': 'Current year income trending per Fannie Mae B3-3.2',
                    'loan_program_required': True,
                },
                'priority': 'high',
                'confidence': 0.95,
            })
            documents.append({
                'type': 'document_request',
                'title': 'Business License',
                'content': 'Required to verify business existence and ownership',
                'structured_data': {
                    'document_type': 'business_license',
                    'document_name': 'Business License / Articles of Incorporation',
                    'reason': 'Verify business exists and borrower is owner',
                    'loan_program_required': False,
                },
                'priority': 'medium',
                'confidence': 0.85,
            })

        # Rental income documentation
        if any('rental' in s for s in income_sources) or 'investment' in property_use:
            documents.append({
                'type': 'document_request',
                'title': 'Lease Agreements',
                'content': 'Required for rental income verification',
                'structured_data': {
                    'document_type': 'rental_agreement',
                    'document_name': 'Current Lease Agreements',
                    'reason': 'Rental income documentation per Fannie Mae B3-3.1-09',
                    'loan_program_required': True,
                },
                'priority': 'medium',
                'confidence': 0.90,
            })
            documents.append({
                'type': 'document_request',
                'title': 'Schedule E (Tax Returns)',
                'content': 'Required for rental income history',
                'structured_data': {
                    'document_type': 'schedule_e',
                    'document_name': 'Schedule E from Tax Returns (2 years)',
                    'reason': 'Rental income history verification',
                    'loan_program_required': True,
                },
                'priority': 'high',
                'confidence': 0.90,
            })

        # Cash-out refinance documentation
        if 'cash-out' in loan_purpose or 'cash out' in loan_purpose:
            documents.append({
                'type': 'document_request',
                'title': 'Mortgage Statement',
                'content': 'Required to verify current loan balance for payoff',
                'structured_data': {
                    'document_type': 'mortgage_statement',
                    'document_name': 'Current Mortgage Statement',
                    'reason': 'Required for refinance payoff calculation',
                    'loan_program_required': True,
                },
                'priority': 'high',
                'confidence': 0.95,
            })

        # VA loan documentation
        loan = context.get('loan', {})
        if loan.get('loan_type', '').upper() == 'VA':
            documents.append({
                'type': 'document_request',
                'title': 'VA Certificate of Eligibility',
                'content': 'Required for VA loans - can be ordered by lender',
                'structured_data': {
                    'document_type': 'va_coe',
                    'document_name': 'VA Certificate of Eligibility (COE)',
                    'reason': 'Required for VA loan program eligibility',
                    'loan_program_required': True,
                },
                'priority': 'high',
                'confidence': 0.98,
            })
            documents.append({
                'type': 'document_request',
                'title': 'DD-214',
                'content': 'Required for veteran status verification (if not already on file)',
                'structured_data': {
                    'document_type': 'dd214',
                    'document_name': 'DD-214 (Certificate of Release or Discharge)',
                    'reason': 'Military service verification for VA eligibility',
                    'loan_program_required': True,
                },
                'priority': 'high',
                'confidence': 0.90,
            })

        # FHA loan documentation
        if loan.get('loan_type', '').upper() == 'FHA':
            if profile.get('first_time_buyer'):
                documents.append({
                    'type': 'document_request',
                    'title': 'Homebuyer Education Certificate',
                    'content': 'May be required for FHA first-time buyers',
                    'structured_data': {
                        'document_type': 'homebuyer_education',
                        'document_name': 'HUD-Approved Homebuyer Education Certificate',
                        'reason': 'May reduce MIP or be required by state/lender',
                        'loan_program_required': False,
                    },
                    'priority': 'low',
                    'confidence': 0.70,
                })

        return documents

    def _truncate_transcript(self, transcript: str, max_words: int = 5000) -> str:
        """Truncate transcript while preserving key information."""
        if not transcript:
            return ""

        words = transcript.split()
        if len(words) <= max_words:
            return transcript

        # For JuniorLO, we want to capture intro (names, purpose) and details throughout
        # Keep first 30% for introductions, last 70% for detailed discussion
        first_portion = int(max_words * 0.3)
        last_portion = max_words - first_portion

        first_words = words[:first_portion]
        last_words = words[-last_portion:]

        return ' '.join(first_words) + '\n\n[... transcript truncated for length ...]\n\n' + ' '.join(last_words)
