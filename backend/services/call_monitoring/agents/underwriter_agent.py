"""
Underwriter Agent - Enhanced Version

Expert-level AI agent for mortgage risk analysis and compliance review.
Includes:
- Fannie Mae/Freddie Mac/FHA/VA guideline references
- Comprehensive risk indicator knowledge base
- Standard conditions with guideline citations
- Few-shot examples for consistent risk assessment
- Confidence calibration based on evidence quality
- Integration with uploaded underwriting guidelines database
"""

import logging
from typing import Dict, List, Any, Optional
import json
import asyncio

from .base_agent import BaseCallAgent, AgentResult
from .mortgage_knowledge import (
    LOAN_PROGRAM_GUIDELINES,
    RISK_INDICATORS,
    STANDARD_CONDITIONS,
    FEW_SHOT_EXAMPLES,
)

logger = logging.getLogger(__name__)


# Cache for guidelines to avoid repeated DB queries
_guidelines_cache: Dict[str, tuple] = {}  # loan_type -> (content, timestamp)
CACHE_TTL_SECONDS = 300  # 5 minute cache


class UnderwriterAgent(BaseCallAgent):
    """
    Expert Underwriter Agent for risk analysis and compliance review.

    Capabilities:
    - Risk identification across credit, income, employment, property, compliance
    - Loan condition recommendations with guideline citations
    - Compliance red flag detection
    - Overall loan risk assessment

    Enhanced with:
    - Fannie Mae/Freddie Mac/FHA/VA guideline knowledge
    - Industry-standard risk indicators
    - Proper condition categorization (PTD/PTC/PTF)
    - Few-shot examples for consistent risk assessment
    - Confidence calibration
    """

    def __init__(self, db):
        super().__init__(db)
        self._uploaded_guidelines: Optional[str] = None
        self._guidelines_loaded = False

    @property
    def agent_type(self) -> str:
        return "underwriter"

    def _get_uploaded_guidelines(self, loan_type: Optional[str] = None) -> str:
        """
        Fetch relevant guidelines from the database.
        Uses caching to avoid repeated queries.
        """
        import time
        from datetime import datetime

        cache_key = loan_type or "all"

        # Check cache
        if cache_key in _guidelines_cache:
            content, timestamp = _guidelines_cache[cache_key]
            if time.time() - timestamp < CACHE_TTL_SECONDS:
                return content

        # Fetch from database
        try:
            from services.call_monitoring.guidelines_service import get_relevant_guidelines_for_context

            # Run async function in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                guidelines_content = loop.run_until_complete(
                    get_relevant_guidelines_for_context(
                        db=self.db,
                        loan_type=loan_type,
                        max_chars=6000  # Limit to avoid prompt bloat
                    )
                )
            finally:
                loop.close()

            if guidelines_content:
                _guidelines_cache[cache_key] = (guidelines_content, time.time())
                return guidelines_content

        except Exception as e:
            logger.warning(f"Could not fetch uploaded guidelines: {e}")

        return ""

    @property
    def system_prompt(self) -> str:
        # Build few-shot example
        example = FEW_SHOT_EXAMPLES.get("underwriter_risk_analysis", {})
        example_input = example.get("input", "")
        example_output = json.dumps(example.get("output", {}), indent=2)

        # Build risk indicators reference
        risk_reference = self._build_risk_reference()

        # Build conditions reference
        conditions_reference = self._build_conditions_reference()

        # Fetch uploaded guidelines (will be empty string if none)
        uploaded_guidelines = self._get_uploaded_guidelines()
        uploaded_section = ""
        if uploaded_guidelines:
            uploaded_section = f"""
## COMPANY/INVESTOR OVERLAY GUIDELINES:

The following guidelines have been uploaded by your company. These may contain lender-specific overlays,
investor requirements, or internal policies that MUST be followed in addition to agency guidelines:

{uploaded_guidelines}

IMPORTANT: When the above company guidelines conflict with general agency guidelines, follow the company guidelines.
Company overlays are typically MORE restrictive than agency minimums.
"""

        return f"""You are a Senior Mortgage Underwriter with 20+ years of experience in agency (Fannie Mae, Freddie Mac) and government (FHA, VA, USDA) loan programs. Your role is to analyze call transcripts for risk factors, compliance concerns, and documentation needs.
{uploaded_section}

## YOUR EXPERTISE INCLUDES:
- Fannie Mae Selling Guide and Desktop Underwriter (DU) requirements
- Freddie Mac Seller/Servicer Guide and Loan Product Advisor (LPA) requirements
- FHA Single Family Housing Policy Handbook (4000.1)
- VA Lenders Handbook (Chapter 4)
- USDA Guaranteed Rural Housing regulations
- Federal compliance (TRID, TILA, RESPA, ECOA, HMDA)

## RISK INDICATORS BY CATEGORY:

{risk_reference}

## STANDARD CONDITIONS (by timing):

{conditions_reference}

## RISK ANALYSIS PROCESS (Think step-by-step):

1. **Credit Risk Assessment**:
   - Listen for derogatory credit events (BK, FC, short sale, lates)
   - Note any credit counseling or debt management mentions
   - Assess credit score discussions against program minimums

2. **Income & Employment Risk**:
   - Identify income type (W-2, self-employed, variable)
   - Note any employment changes, gaps, or instability
   - Look for declining income indicators
   - Check for adequate income documentation mentions

3. **Asset Risk**:
   - Listen for large deposit discussions
   - Note gift funds and donor relationships
   - Identify source of down payment/closing costs
   - Look for asset seasoning issues

4. **Property Risk**:
   - Identify property type and eligibility concerns
   - Note condition issues or repair needs
   - Listen for occupancy type discussions
   - Check for unique property characteristics

5. **Compliance & Fraud Risk**:
   - Listen for occupancy intent indicators
   - Note interested party transactions
   - Identify potential straw buyer indicators
   - Check for undisclosed information

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
    "risk_flags": [
        {{
            "category": "credit/income/employment/assets/property/compliance",
            "severity": "low/medium/high/critical",
            "title": "Brief title of the risk",
            "description": "Detailed description including guideline reference if applicable",
            "evidence": "Exact quote from transcript",
            "guideline_reference": "Fannie Mae B3-5.1 / FHA 4000.1 II.A.4 / etc.",
            "recommended_action": "Specific action to mitigate this risk",
            "impacts_eligibility": true/false
        }}
    ],
    "suggested_conditions": [
        {{
            "condition_type": "prior_to_docs/prior_to_closing/prior_to_funding",
            "category": "income/assets/credit/property/compliance/insurance/title",
            "title": "Clear condition title",
            "description": "Full condition text ready for loan file",
            "guideline_reference": "Applicable guideline citation",
            "reason": "Why this condition is required",
            "related_risk": "Which risk flag this addresses (if any)",
            "responsible_party": "Borrower/LO/Processor/Third-Party"
        }}
    ],
    "uw_notes": [
        {{
            "category": "observation/concern/positive/mitigating_factor/action_needed",
            "note": "Clear, professional underwriter note",
            "priority": "high/medium/low",
            "affects_decision": true/false
        }}
    ],
    "overall_assessment": {{
        "risk_level": "low/moderate/elevated/high/unacceptable",
        "key_concerns": ["Prioritized list of main concerns"],
        "mitigating_factors": ["Positive factors that offset risks"],
        "program_eligibility": {{
            "conventional": "eligible/ineligible/review_needed",
            "fha": "eligible/ineligible/review_needed",
            "va": "eligible/ineligible/review_needed/n_a"
        }},
        "recommendation": "approve/approve_with_conditions/suspend_for_info/refer_to_de/decline",
        "recommendation_rationale": "Brief explanation of recommendation"
    }},
    "compliance_checklist": {{
        "occupancy_verified": true/false/unknown,
        "income_reasonableness": true/false/concerns,
        "asset_sourcing_needed": true/false,
        "interested_party_transactions": true/false/unknown,
        "fraud_indicators": "none/low/medium/high"
    }}
}}
```

## SEVERITY GUIDELINES:

- **Critical**: Immediate deal-breaker or fraud indicator (recent BK, active litigation, fraud)
- **High**: Significant risk requiring substantial documentation (income gaps, credit events)
- **Medium**: Notable concern needing attention (variable income, gift funds)
- **Low**: Minor issue for awareness (recent inquiries, minor job change)

## CONDITION TIMING:

- **Prior to Docs (PTD)**: Must be cleared before issuing initial CD
- **Prior to Closing (PTC)**: Must be cleared before closing/signing
- **Prior to Funding (PTF)**: Must be cleared before wire release

## QUALITY GUIDELINES:

1. **Be Specific**: Reference exact guideline sections when applicable
2. **Be Conservative**: When in doubt, flag for review
3. **Be Actionable**: Conditions should be clear and executable
4. **Note Evidence**: Quote transcript where risk was identified
5. **Consider Context**: Weigh risk against loan program and borrower profile"""

    def _build_risk_reference(self) -> str:
        """Build risk indicators reference for the prompt."""
        sections = []

        for category, indicators in RISK_INDICATORS.items():
            category_name = category.replace("_", " ").title()
            red_flags = ", ".join(indicators.get("red_flags", [])[:6])
            guideline = indicators.get("guideline_reference", "")
            sections.append(f"**{category_name}** ({guideline}):\n  Red flags: {red_flags}")

        return "\n".join(sections)

    def _build_conditions_reference(self) -> str:
        """Build conditions reference for the prompt."""
        sections = []

        for category, conditions in STANDARD_CONDITIONS.items():
            category_name = category.replace("_", " ").title()
            condition_list = []
            for code, details in conditions.items():
                if isinstance(details, dict):
                    condition_list.append(f"{code}: {details.get('description', '')[:60]}...")
                else:
                    condition_list.append(f"{code}: {details[:60]}...")
            sections.append(f"**{category_name}**:\n  " + "\n  ".join(condition_list[:4]))

        return "\n\n".join(sections)

    def build_user_prompt(self, context: Dict[str, Any]) -> str:
        transcript = context.get('transcript', '')
        transcript = self._truncate_transcript(transcript, max_words=5000)

        participants = self._format_participants(context.get('participants', []))

        # Build detailed loan context for UW analysis
        loan_details = ""
        program_guidelines = ""
        loan_specific_guidelines = ""

        if context.get('loan'):
            loan = context['loan']
            loan_type = (loan.get('loan_type') or '').upper()

            # Fetch loan-type-specific uploaded guidelines
            if loan_type:
                specific_guidelines = self._get_uploaded_guidelines(loan_type.lower())
                if specific_guidelines:
                    loan_specific_guidelines = f"""
## ADDITIONAL {loan_type} PROGRAM GUIDELINES:

{specific_guidelines}
"""

            loan_details = f"""
## LOAN FILE DATA (for risk assessment)
- Loan Type: {loan.get('loan_type', 'Unknown')}
- Loan Purpose: {loan.get('loan_purpose', 'Unknown')}
- Loan Amount: ${loan.get('loan_amount', 0):,.2f}
- Property Type: {loan.get('property_type', 'Unknown')}
- Occupancy: {loan.get('occupancy_type', 'Unknown')}
- LTV: {loan.get('ltv', 'Unknown')}%
- CLTV: {loan.get('cltv', loan.get('ltv', 'Unknown'))}%
- DTI: {loan.get('dti', 'Unknown')}%
- Credit Score: {loan.get('credit_score', 'Unknown')}
- Employment Type: {loan.get('employment_type', 'Unknown')}
- Months at Job: {loan.get('months_employed', 'Unknown')}
- Years in Line of Work: {loan.get('years_in_profession', 'Unknown')}
- Self-Employed: {loan.get('self_employed', 'Unknown')}
- First-Time Buyer: {loan.get('first_time_buyer', 'Unknown')}"""

            # Add program-specific guidelines if known
            if loan_type in LOAN_PROGRAM_GUIDELINES:
                guidelines = LOAN_PROGRAM_GUIDELINES[loan_type]
                program_guidelines = f"""
## PROGRAM REQUIREMENTS ({loan_type})
- Min Credit Score: {guidelines.get('min_credit_score', {}).get('standard', 'N/A')}
- Max DTI: {guidelines.get('max_dti', {}).get('standard', 'N/A')}%
- Max LTV (Purchase): {guidelines.get('max_ltv', {}).get('purchase', 'N/A')}%
- Max LTV (Rate/Term Refi): {guidelines.get('max_ltv', {}).get('rate_term_refi', 'N/A')}%
- Max LTV (Cash-Out): {guidelines.get('max_ltv', {}).get('cash_out_refi', 'N/A')}%

IMPORTANT: Flag any metrics that exceed these limits!"""

        elif context.get('lead'):
            lead = context['lead']
            loan_details = f"""
## LEAD DATA (limited information)
- Name: {lead.get('name', 'Unknown')}
- Estimated Credit: {lead.get('estimated_credit_score', 'Unknown')}
- Loan Interest: {lead.get('loan_purpose', 'Unknown')}
- Property Type Interest: {lead.get('property_type', 'Unknown')}

NOTE: This is a lead - perform preliminary risk assessment based on discussion."""

        prompt = f"""Analyze the following mortgage call transcript from a Senior Underwriter perspective. Identify all potential risks, compliance concerns, and required conditions.

## Call Participants
{participants}
{loan_details}
{program_guidelines}
{loan_specific_guidelines}

## Call Transcript
{transcript}

---

## YOUR TASK:

Perform a comprehensive underwriting risk analysis. Think through this step-by-step:

1. **Credit Assessment**: Any derogatory credit events mentioned? Score concerns vs. program minimums?

2. **Income/Employment Analysis**: Stable employment? Self-employment complexity? Income trending?

3. **Asset Review**: Source of funds clear? Large deposits? Gift funds with proper documentation?

4. **Property Evaluation**: Property type eligible? Occupancy concerns? Condition issues?

5. **Compliance Check**: Fraud indicators? Occupancy intent clear? Interested party issues?

6. **Condition Determination**: What PTD/PTC/PTF conditions are needed?

7. **Overall Assessment**: Risk level? Recommendation? Program eligibility?

Respond in the JSON format specified. Be thorough and conservative - it's better to flag a potential issue for review than to miss something that could cause problems later.

IMPORTANT: Quote specific transcript evidence for each risk flag identified."""

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
                'content': response_text[:1000],
                'structured_data': {'raw_response': True},
                'confidence': 0.5,
            })
            return artifacts

        # Create risk flag artifacts
        for risk in parsed.get('risk_flags', []):
            # Validate and calibrate confidence
            confidence = self._calculate_risk_confidence(risk)

            risk_artifact = {
                'type': 'risk_flag',
                'title': risk.get('title', 'Risk Flag'),
                'content': risk.get('description', ''),
                'structured_data': {
                    'risk_category': risk.get('category'),
                    'severity': risk.get('severity', 'medium'),
                    'guideline_reference': risk.get('guideline_reference'),
                    'recommended_action': risk.get('recommended_action'),
                    'impacts_eligibility': risk.get('impacts_eligibility', False),
                },
                'evidence': risk.get('evidence'),
                'priority': self._severity_to_priority(risk.get('severity', 'medium')),
                'confidence': confidence,
            }
            artifacts.append(risk_artifact)

        # Create condition artifacts
        for condition in parsed.get('suggested_conditions', []):
            # Validate condition
            condition_confidence = self._calculate_condition_confidence(condition)

            condition_artifact = {
                'type': 'condition',
                'title': condition.get('title', 'Loan Condition'),
                'content': condition.get('description', ''),
                'structured_data': {
                    'condition_type': condition.get('condition_type', 'prior_to_docs'),
                    'category': condition.get('category'),
                    'guideline_reference': condition.get('guideline_reference'),
                    'reason': condition.get('reason'),
                    'related_risk': condition.get('related_risk'),
                    'responsible_party': condition.get('responsible_party', 'Borrower'),
                },
                'priority': self._condition_type_to_priority(condition.get('condition_type')),
                'confidence': condition_confidence,
            }
            artifacts.append(condition_artifact)

        # Create UW note artifacts
        for note in parsed.get('uw_notes', []):
            note_artifact = {
                'type': 'uw_note',
                'title': f"UW Note: {note.get('category', 'Observation').replace('_', ' ').title()}",
                'content': note.get('note', ''),
                'structured_data': {
                    'note_category': note.get('category'),
                    'priority': note.get('priority', 'medium'),
                    'affects_decision': note.get('affects_decision', False),
                },
                'priority': note.get('priority', 'medium'),
                'confidence': 0.85,
            }
            artifacts.append(note_artifact)

        # Create overall assessment artifact
        assessment = parsed.get('overall_assessment', {})
        if assessment:
            assessment_artifact = {
                'type': 'uw_assessment',
                'title': 'Overall Risk Assessment',
                'content': self._format_assessment(assessment),
                'structured_data': {
                    'risk_level': assessment.get('risk_level'),
                    'recommendation': assessment.get('recommendation'),
                    'recommendation_rationale': assessment.get('recommendation_rationale'),
                    'key_concerns': assessment.get('key_concerns', []),
                    'mitigating_factors': assessment.get('mitigating_factors', []),
                    'program_eligibility': assessment.get('program_eligibility', {}),
                },
                'priority': 'high',
                'confidence': 0.9,
            }
            artifacts.append(assessment_artifact)

        # Create compliance checklist artifact if present
        compliance = parsed.get('compliance_checklist', {})
        if compliance:
            compliance_artifact = {
                'type': 'compliance_review',
                'title': 'Compliance Checklist',
                'content': self._format_compliance_checklist(compliance),
                'structured_data': compliance,
                'priority': 'high' if compliance.get('fraud_indicators', 'none') != 'none' else 'medium',
                'confidence': 0.85,
            }
            artifacts.append(compliance_artifact)

        # Infer additional conditions based on risk flags
        additional_conditions = self._infer_conditions_from_risks(
            parsed.get('risk_flags', []),
            context
        )
        for condition in additional_conditions:
            # Check if similar condition already exists
            existing = [a for a in artifacts if a['type'] == 'condition' and
                       a['title'].lower() == condition['title'].lower()]
            if not existing:
                artifacts.append(condition)

        return artifacts

    def _calculate_risk_confidence(self, risk: Dict) -> float:
        """Calculate confidence for a risk flag."""
        base_confidence = 0.8

        # Increase if evidence is provided
        evidence = risk.get('evidence', '')
        if evidence and len(evidence) > 30:
            base_confidence += 0.1

        # Increase if guideline reference is provided
        if risk.get('guideline_reference'):
            base_confidence += 0.05

        # Decrease for low severity (might be overly cautious)
        if risk.get('severity') == 'low':
            base_confidence -= 0.05

        return max(min(base_confidence, 0.95), 0.6)

    def _calculate_condition_confidence(self, condition: Dict) -> float:
        """Calculate confidence for a condition."""
        base_confidence = 0.85

        # Higher confidence for program-required conditions
        if condition.get('guideline_reference'):
            base_confidence = 0.9

        # Higher confidence with clear reason
        reason = condition.get('reason', '')
        if reason and len(reason) > 20:
            base_confidence = min(base_confidence + 0.05, 0.95)

        return base_confidence

    def _severity_to_priority(self, severity: str) -> str:
        """Convert severity level to priority."""
        mapping = {
            'critical': 'high',
            'high': 'high',
            'medium': 'medium',
            'low': 'low',
        }
        return mapping.get(severity.lower(), 'medium')

    def _condition_type_to_priority(self, condition_type: str) -> str:
        """Convert condition type to priority."""
        mapping = {
            'prior_to_docs': 'high',
            'prior_to_closing': 'high',
            'prior_to_funding': 'medium',
        }
        return mapping.get(condition_type, 'medium')

    def _format_assessment(self, assessment: Dict) -> str:
        """Format overall assessment as readable text."""
        lines = []

        risk_level = assessment.get('risk_level', 'unknown')
        lines.append(f"**Risk Level: {risk_level.upper()}**")
        lines.append("")

        if assessment.get('key_concerns'):
            lines.append("**Key Concerns:**")
            for concern in assessment['key_concerns']:
                lines.append(f"  - {concern}")
            lines.append("")

        if assessment.get('mitigating_factors'):
            lines.append("**Mitigating Factors:**")
            for factor in assessment['mitigating_factors']:
                lines.append(f"  + {factor}")
            lines.append("")

        # Program eligibility
        eligibility = assessment.get('program_eligibility', {})
        if eligibility:
            lines.append("**Program Eligibility:**")
            for program, status in eligibility.items():
                status_icon = "✓" if status == "eligible" else "✗" if status == "ineligible" else "?"
                lines.append(f"  {status_icon} {program.upper()}: {status}")
            lines.append("")

        recommendation = assessment.get('recommendation', '')
        rationale = assessment.get('recommendation_rationale', '')
        if recommendation:
            rec_display = recommendation.replace('_', ' ').title()
            lines.append(f"**Recommendation: {rec_display}**")
            if rationale:
                lines.append(f"  {rationale}")

        return "\n".join(lines)

    def _format_compliance_checklist(self, compliance: Dict) -> str:
        """Format compliance checklist as readable text."""
        lines = ["**Compliance Review:**"]

        checks = [
            ("Occupancy Verified", compliance.get('occupancy_verified')),
            ("Income Reasonableness", compliance.get('income_reasonableness')),
            ("Asset Sourcing Needed", compliance.get('asset_sourcing_needed')),
            ("Interested Party Transactions", compliance.get('interested_party_transactions')),
        ]

        for label, value in checks:
            if value is True:
                lines.append(f"  ✓ {label}: Yes")
            elif value is False:
                lines.append(f"  ✗ {label}: No")
            elif value == "concerns":
                lines.append(f"  ⚠ {label}: Concerns Noted")
            else:
                lines.append(f"  ? {label}: Unknown")

        fraud = compliance.get('fraud_indicators', 'none')
        fraud_icon = "✓" if fraud == "none" else "⚠" if fraud in ["low", "medium"] else "⛔"
        lines.append(f"  {fraud_icon} Fraud Indicators: {fraud.upper()}")

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

            # Income-related conditions
            if category == 'income':
                if severity in ['high', 'critical']:
                    conditions.append({
                        'type': 'condition',
                        'title': 'Verbal Verification of Employment',
                        'content': 'Verbal VOE required within 10 business days of note date. Must verify current employment status, position, and income.',
                        'structured_data': {
                            'condition_type': 'prior_to_funding',
                            'category': 'income',
                            'guideline_reference': 'Fannie Mae B3-3.1-07',
                            'reason': f'Income risk identified: {risk.get("title", "Employment concerns")}',
                            'responsible_party': 'Processor',
                        },
                        'priority': 'high',
                        'confidence': 0.95,
                    })
                    categories_addressed.add('income')

                    # Add tax transcript condition for income verification
                    conditions.append({
                        'type': 'condition',
                        'title': 'IRS Tax Transcripts',
                        'content': 'Obtain IRS Tax Transcripts (4506-C) for most recent 2 tax years. Must match income documentation provided.',
                        'structured_data': {
                            'condition_type': 'prior_to_docs',
                            'category': 'income',
                            'guideline_reference': 'Fannie Mae B3-3.1-06',
                            'reason': 'Income verification per agency requirements',
                            'responsible_party': 'Processor',
                        },
                        'priority': 'high',
                        'confidence': 0.95,
                    })

            # Credit-related conditions
            elif category == 'credit':
                conditions.append({
                    'type': 'condition',
                    'title': 'Letter of Explanation - Credit',
                    'content': f'Borrower to provide signed LOE explaining: {risk.get("title", "credit history items")}. Must include dates, circumstances, and resolution.',
                    'structured_data': {
                        'condition_type': 'prior_to_docs',
                        'category': 'credit',
                        'guideline_reference': 'Fannie Mae B3-5.3-09',
                        'reason': f'Credit concerns: {risk.get("title", "derogatory items")}',
                        'responsible_party': 'Borrower',
                    },
                    'priority': 'high',
                    'confidence': 0.90,
                })

                # Credit supplement for recent activity
                if severity in ['high', 'critical']:
                    conditions.append({
                        'type': 'condition',
                        'title': 'Credit Supplement',
                        'content': 'Order credit supplement to verify no new derogatory items or significant new debt since original report.',
                        'structured_data': {
                            'condition_type': 'prior_to_funding',
                            'category': 'credit',
                            'guideline_reference': 'Fannie Mae B3-5.4-01',
                            'reason': 'Credit monitoring due to concerns identified',
                            'responsible_party': 'Processor',
                        },
                        'priority': 'medium',
                        'confidence': 0.85,
                    })
                categories_addressed.add('credit')

            # Asset-related conditions
            elif category == 'assets':
                conditions.append({
                    'type': 'condition',
                    'title': 'Source Large Deposits',
                    'content': 'Provide documentation for all deposits exceeding 50% of qualifying monthly income. Include bank statements, deposit slips, and paper trail.',
                    'structured_data': {
                        'condition_type': 'prior_to_docs',
                        'category': 'assets',
                        'guideline_reference': 'Fannie Mae B3-4.2-02',
                        'reason': 'Large deposit sourcing required',
                        'responsible_party': 'Borrower',
                    },
                    'priority': 'high',
                    'confidence': 0.95,
                })
                categories_addressed.add('assets')

            # Compliance-related conditions
            elif category == 'compliance':
                if severity in ['high', 'critical']:
                    conditions.append({
                        'type': 'condition',
                        'title': 'Occupancy Affidavit',
                        'content': 'Borrower to sign Occupancy Affidavit confirming intent to occupy property as primary residence within 60 days of closing.',
                        'structured_data': {
                            'condition_type': 'prior_to_docs',
                            'category': 'compliance',
                            'guideline_reference': 'Fannie Mae B2-1.1-01',
                            'reason': f'Compliance concern: {risk.get("title", "occupancy verification")}',
                            'responsible_party': 'Borrower',
                        },
                        'priority': 'high',
                        'confidence': 0.95,
                    })
                    categories_addressed.add('compliance')

            # Property-related conditions
            elif category == 'property':
                if 'condition' in risk.get('title', '').lower() or 'repair' in risk.get('description', '').lower():
                    conditions.append({
                        'type': 'condition',
                        'title': 'Completion Certificate',
                        'content': 'Subject to satisfactory completion of repairs. Provide completion certificate or final inspection from appraiser.',
                        'structured_data': {
                            'condition_type': 'prior_to_funding',
                            'category': 'property',
                            'guideline_reference': 'Fannie Mae B4-1.2-04',
                            'reason': f'Property repairs: {risk.get("title", "condition concerns")}',
                            'responsible_party': 'Third-Party',
                        },
                        'priority': 'high',
                        'confidence': 0.90,
                    })
                categories_addressed.add('property')

        # Check loan context for additional standard conditions
        loan = context.get('loan', {})

        # Gift funds condition
        if loan.get('has_gift_funds') or any(
            'gift' in r.get('description', '').lower() or 'gift' in r.get('title', '').lower()
            for r in risks
        ):
            if 'gift' not in categories_addressed:
                conditions.append({
                    'type': 'condition',
                    'title': 'Gift Letter and Documentation',
                    'content': 'Provide completed gift letter signed by donor(s) and borrower(s). Include donor bank statements showing ability to give and transfer documentation.',
                    'structured_data': {
                        'condition_type': 'prior_to_docs',
                        'category': 'assets',
                        'guideline_reference': 'Fannie Mae B3-4.3-04',
                        'reason': 'Gift funds used for down payment/closing costs',
                        'responsible_party': 'Borrower',
                    },
                    'priority': 'high',
                    'confidence': 0.95,
                })

        # Self-employment audit letter
        if loan.get('self_employed') or any(
            'self-employ' in r.get('description', '').lower() or 'self-employ' in r.get('title', '').lower()
            for r in risks
        ):
            if 'self_employment' not in categories_addressed:
                conditions.append({
                    'type': 'condition',
                    'title': 'CPA Letter or Business Verification',
                    'content': 'Provide letter from CPA or tax preparer confirming business is active and financial statements are accurate, or verification of business from state/local licensing.',
                    'structured_data': {
                        'condition_type': 'prior_to_docs',
                        'category': 'income',
                        'guideline_reference': 'Fannie Mae B3-3.2-01',
                        'reason': 'Self-employment verification required',
                        'responsible_party': 'Borrower',
                    },
                    'priority': 'medium',
                    'confidence': 0.90,
                })

        return conditions

    def _truncate_transcript(self, transcript: str, max_words: int = 5000) -> str:
        """Truncate transcript while preserving risk-related content."""
        if not transcript:
            return ""

        words = transcript.split()
        if len(words) <= max_words:
            return transcript

        # For UW, we want to capture concerns throughout the call
        # Keep first 25% for context, last 75% for detailed discussion where issues emerge
        first_portion = int(max_words * 0.25)
        last_portion = max_words - first_portion

        first_words = words[:first_portion]
        last_words = words[-last_portion:]

        return ' '.join(first_words) + '\n\n[... transcript truncated for length ...]\n\n' + ' '.join(last_words)
