"""
Claude 4 Sonnet Email Parser
Comprehensive AI-powered email parsing for all CRM profile types
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import anthropic

logger = logging.getLogger(__name__)


class ClaudeEmailParser:
    """
    Production-ready Claude 4 Sonnet parser for comprehensive CRM field extraction
    Supports all 4 profile types: Lead, Active Loan, MUM Client, Team Member
    """

    # Field schemas for all profile types
    FIELD_SCHEMAS = {
        'lead': {
            'personal_info': {
                'first_name': {'type': 'string', 'description': 'First name'},
                'last_name': {'type': 'string', 'description': 'Last name'},
                'email': {'type': 'email', 'description': 'Email address'},
                'phone': {'type': 'phone', 'description': 'Phone number'},
                'loan_number': {'type': 'string', 'description': 'Loan number if mentioned'}
            },
            'employment': {
                'employment_status': {'type': 'enum', 'values': ['employed', 'self_employed', 'retired', 'unemployed'], 'description': 'Employment status'},
                'employer_name': {'type': 'string', 'description': 'Current employer'},
                'job_title': {'type': 'string', 'description': 'Job title or position'},
                'years_at_job': {'type': 'number', 'description': 'Years at current job'},
                'annual_income': {'type': 'currency', 'description': 'Annual income'},
                'monthly_income': {'type': 'currency', 'description': 'Monthly income'},
                'other_income': {'type': 'currency', 'description': 'Other income sources'},
                'income_source': {'type': 'string', 'description': 'Source of other income'}
            },
            'loan_info': {
                'address': {'type': 'string', 'description': 'Property address'},
                'city': {'type': 'string', 'description': 'City'},
                'state': {'type': 'string', 'description': 'State (2-letter code)'},
                'zip_code': {'type': 'string', 'description': 'ZIP code'},
                'property_type': {'type': 'enum', 'values': ['single_family', 'condo', 'townhouse', 'multi_family'], 'description': 'Type of property'},
                'property_value': {'type': 'currency', 'description': 'Estimated property value'},
                'down_payment': {'type': 'currency', 'description': 'Down payment amount'},
                'credit_score': {'type': 'integer', 'description': 'Credit score'},
                'loan_amount': {'type': 'currency', 'description': 'Loan amount requested'},
                'interest_rate': {'type': 'percentage', 'description': 'Interest rate'},
                'loan_term': {'type': 'integer', 'description': 'Loan term in years'},
                'loan_type': {'type': 'enum', 'values': ['conventional', 'fha', 'va', 'usda'], 'description': 'Type of loan program'},
                'lock_date': {'type': 'date', 'description': 'Rate lock date'},
                'lock_expiration': {'type': 'date', 'description': 'Rate lock expiration'},
                'apr': {'type': 'percentage', 'description': 'APR'},
                'points': {'type': 'number', 'description': 'Points paid'},
                'lender': {'type': 'string', 'description': 'Lender name'},
                'loan_officer': {'type': 'string', 'description': 'Loan officer name'},
                'processor': {'type': 'string', 'description': 'Loan processor name'},
                'underwriter': {'type': 'string', 'description': 'Underwriter name'},
                'closing_date': {'type': 'date', 'description': 'Estimated closing date'},
                'appraisal_value': {'type': 'currency', 'description': 'Appraisal value'},
                'ltv': {'type': 'percentage', 'description': 'Loan-to-value ratio'},
                'dti': {'type': 'percentage', 'description': 'Debt-to-income ratio'}
            },
            'important_dates': {
                'first_contact_attempt_date': {'type': 'datetime', 'description': 'First contact attempt'},
                'first_contact_successful_date': {'type': 'datetime', 'description': 'First successful contact'},
                'lead_qualification_date': {'type': 'datetime', 'description': 'Lead qualified date'},
                'application_link_sent_date': {'type': 'datetime', 'description': 'Application link sent'},
                'application_started_date': {'type': 'datetime', 'description': 'Application started'},
                'application_completed_date': {'type': 'datetime', 'description': 'Application completed'},
                'credit_pulled_date': {'type': 'datetime', 'description': 'Credit report pulled'},
                'preapproval_submission_date': {'type': 'datetime', 'description': 'Pre-approval submitted'},
                'preapproval_issued_date': {'type': 'datetime', 'description': 'Pre-approval issued'},
                'realtor_referral_date': {'type': 'datetime', 'description': 'Referred to realtor'},
                'preapproval_expiration_date': {'type': 'date', 'description': 'Pre-approval expires'},
                'rate_watch_enrollment_date': {'type': 'datetime', 'description': 'Enrolled in rate watch'}
            }
        },
        'active_loan': {
            'loan_details': {
                'loan_number': {'type': 'string', 'description': 'Loan number', 'required': True},
                'amount': {'type': 'currency', 'description': 'Loan amount'},
                'rate': {'type': 'percentage', 'description': 'Interest rate'},
                'term': {'type': 'integer', 'description': 'Loan term in years'},
                'program': {'type': 'string', 'description': 'Loan program'},
                'lock_date': {'type': 'date', 'description': 'Rate lock date'},
                'lock_expiration': {'type': 'date', 'description': 'Lock expiration'},
                'apr': {'type': 'percentage', 'description': 'APR'},
                'points': {'type': 'number', 'description': 'Points'},
                'lender': {'type': 'string', 'description': 'Lender'},
                'appraisal_value': {'type': 'currency', 'description': 'Appraisal value'},
                'ltv': {'type': 'percentage', 'description': 'LTV ratio'},
                'dti': {'type': 'percentage', 'description': 'DTI ratio'}
            },
            'property': {
                'property_address': {'type': 'string', 'description': 'Property address'},
                'property_city': {'type': 'string', 'description': 'City'},
                'property_state': {'type': 'string', 'description': 'State'},
                'property_zip': {'type': 'string', 'description': 'ZIP code'}
            },
            'team': {
                'loan_officer_name': {'type': 'string', 'description': 'Loan officer'},
                'loan_officer_email': {'type': 'email', 'description': 'LO email'},
                'processor': {'type': 'string', 'description': 'Processor'},
                'processor_email': {'type': 'email', 'description': 'Processor email'},
                'underwriter': {'type': 'string', 'description': 'Underwriter'},
                'underwriter_email': {'type': 'email', 'description': 'Underwriter email'},
                'closer': {'type': 'string', 'description': 'Closer'},
                'closer_email': {'type': 'email', 'description': 'Closer email'}
            },
            'milestone_dates': {
                'contract_received_date': {'type': 'date', 'description': 'Contract received'},
                'appraisal_ordered_date': {'type': 'date', 'description': 'Appraisal ordered'},
                'appraisal_scheduled_date': {'type': 'date', 'description': 'Appraisal scheduled'},
                'appraisal_completed_date': {'type': 'date', 'description': 'Appraisal completed'},
                'appraisal_received_date': {'type': 'date', 'description': 'Appraisal received'},
                'title_ordered_date': {'type': 'date', 'description': 'Title ordered'},
                'title_received_date': {'type': 'date', 'description': 'Title received'},
                'insurance_ordered_date': {'type': 'date', 'description': 'Insurance ordered'},
                'insurance_received_date': {'type': 'date', 'description': 'Insurance received'},
                'initial_disclosures_sent_date': {'type': 'date', 'description': 'Initial disclosures sent'},
                'initial_disclosures_signed_date': {'type': 'date', 'description': 'Initial disclosures signed'},
                'processor_submission_date': {'type': 'date', 'description': 'Submitted to processor'},
                'underwriting_submission_date': {'type': 'date', 'description': 'Submitted to underwriting'},
                'conditional_approval_date': {'type': 'date', 'description': 'Conditional approval'},
                'conditions_sent_date': {'type': 'date', 'description': 'Conditions sent'},
                'conditions_received_date': {'type': 'date', 'description': 'Conditions received'},
                'resubmission_date': {'type': 'date', 'description': 'Resubmitted'},
                'clear_to_close_date': {'type': 'date', 'description': 'Clear to close'},
                'rate_lock_date': {'type': 'date', 'description': 'Rate locked'},
                'rate_lock_expiration_date': {'type': 'date', 'description': 'Lock expires'},
                'rate_lock_extension_date': {'type': 'date', 'description': 'Lock extended'},
                'float_down_trigger_date': {'type': 'date', 'description': 'Float down triggered'},
                'closing_disclosure_sent_date': {'type': 'date', 'description': 'CD sent'},
                'cd_received_signed_date': {'type': 'date', 'description': 'CD signed'},
                'cd_delivered_date': {'type': 'date', 'description': 'CD delivered'},
                'final_cd_issue_date': {'type': 'date', 'description': 'Final CD issued'},
                'final_closing_package_sent_date': {'type': 'date', 'description': 'Final package sent'},
                'closing_scheduled_date': {'type': 'date', 'description': 'Closing scheduled'},
                'funding_date': {'type': 'date', 'description': 'Funding date'}
            }
        },
        'mum_client': {
            'personal': {
                'name': {'type': 'string', 'description': 'Full name'},
                'email': {'type': 'email', 'description': 'Email'},
                'phone': {'type': 'phone', 'description': 'Phone'}
            },
            'loan_info': {
                'loan_number': {'type': 'string', 'description': 'Loan number'},
                'original_close_date': {'type': 'date', 'description': 'Original close date'},
                'original_rate': {'type': 'percentage', 'description': 'Original rate'},
                'current_rate': {'type': 'percentage', 'description': 'Current rate'},
                'loan_balance': {'type': 'currency', 'description': 'Current balance'},
                'estimated_savings': {'type': 'currency', 'description': 'Estimated refinance savings'},
                'refinance_opportunity': {'type': 'boolean', 'description': 'Refinance opportunity exists'},
                'opportunity_notes': {'type': 'string', 'description': 'Opportunity details'}
            },
            'team': {
                'loan_officer': {'type': 'string', 'description': 'Loan officer'},
                'loan_officer_email': {'type': 'email', 'description': 'LO email'},
                'processor': {'type': 'string', 'description': 'Processor'},
                'processor_email': {'type': 'email', 'description': 'Processor email'},
                'underwriter': {'type': 'string', 'description': 'Underwriter'},
                'underwriter_email': {'type': 'email', 'description': 'Underwriter email'},
                'closer': {'type': 'string', 'description': 'Closer'},
                'closer_email': {'type': 'email', 'description': 'Closer email'}
            },
            'engagement': {
                'last_contact': {'type': 'date', 'description': 'Last contact date'},
                'next_touchpoint': {'type': 'date', 'description': 'Next touchpoint'},
                'engagement_score': {'type': 'integer', 'description': 'Engagement score (0-100)'},
                'referrals_sent': {'type': 'integer', 'description': 'Number of referrals'}
            }
        },
        'team_member': {
            'basic': {
                'photo_url': {'type': 'url', 'description': 'Profile photo URL'},
                'employee_id': {'type': 'string', 'description': 'Employee ID'},
                'start_date': {'type': 'date', 'description': 'Start date'},
                'department': {'type': 'string', 'description': 'Department'},
                'manager': {'type': 'string', 'description': 'Manager name'}
            },
            'kpis': {
                'loans_processed': {'type': 'integer', 'description': 'Total loans processed'},
                'avg_close_time': {'type': 'number', 'description': 'Average close time (days)'},
                'satisfaction_score': {'type': 'number', 'description': 'Customer satisfaction'},
                'volume': {'type': 'currency', 'description': 'Total loan volume'}
            },
            'disc': {
                'disc_d': {'type': 'integer', 'description': 'Dominance score (0-100)'},
                'disc_i': {'type': 'integer', 'description': 'Influence score (0-100)'},
                'disc_s': {'type': 'integer', 'description': 'Steadiness score (0-100)'},
                'disc_c': {'type': 'integer', 'description': 'Conscientiousness score (0-100)'},
                'disc_summary': {'type': 'string', 'description': 'DISC summary'}
            },
            'personal': {
                'birthday': {'type': 'date', 'description': 'Birthday'},
                'anniversary': {'type': 'date', 'description': 'Work anniversary'},
                'spouse_name': {'type': 'string', 'description': 'Spouse name'},
                'children': {'type': 'string', 'description': 'Children info'},
                'hobbies': {'type': 'string', 'description': 'Hobbies'},
                'emergency_contact': {'type': 'string', 'description': 'Emergency contact name'},
                'emergency_phone': {'type': 'phone', 'description': 'Emergency phone'}
            },
            'goals': {
                'career_goals': {'type': 'string', 'description': 'Career goals'},
                'q1_goals': {'type': 'string', 'description': 'Q1 goals'},
                'q2_goals': {'type': 'string', 'description': 'Q2 goals'},
                'q3_goals': {'type': 'string', 'description': 'Q3 goals'},
                'q4_goals': {'type': 'string', 'description': 'Q4 goals'},
                'development_areas': {'type': 'string', 'description': 'Development areas'}
            }
        }
    }

    def __init__(self):
        """Initialize Claude client"""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
        logger.info("Claude Email Parser initialized")

    async def parse_email(
        self,
        email_data: Dict[str, Any],
        profile_type: str,
        current_profile: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Parse email and extract all relevant CRM fields

        Args:
            email_data: Raw email with body, subject, sender, etc.
            profile_type: 'lead', 'active_loan', 'mum_client', 'team_member'
            current_profile: Existing profile data for update detection

        Returns:
            Complete extraction with fields, confidence, milestones, conflicts
        """

        if profile_type not in self.FIELD_SCHEMAS:
            raise ValueError(f"Invalid profile_type: {profile_type}")

        start_time = datetime.utcnow()

        try:
            # Build comprehensive prompt
            prompt = self._build_comprehensive_prompt(
                email_data,
                profile_type,
                current_profile
            )

            # Call Claude API
            logger.info(f"Calling Claude API for {profile_type} email parsing")
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.1,  # Low temperature for consistent extraction
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse Claude's JSON response
            response_text = response.content[0].text

            # Extract JSON from response (Claude may wrap it in markdown)
            extracted = self._extract_json(response_text)

            # Validate and enrich
            processing_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            result = self._validate_and_enrich(extracted, email_data, processing_time_ms)

            logger.info(f"Successfully parsed {profile_type} email in {processing_time_ms}ms")
            return result

        except Exception as e:
            logger.error(f"Error parsing email with Claude: {e}")
            raise

    def _build_comprehensive_prompt(
        self,
        email_data: Dict[str, Any],
        profile_type: str,
        current_profile: Optional[Dict]
    ) -> str:
        """
        Build the complete extraction prompt based on profile type
        """

        schema = self.FIELD_SCHEMAS[profile_type]

        # Build field list for prompt
        field_descriptions = []
        for category, fields in schema.items():
            field_descriptions.append(f"\n**{category.upper()}:**")
            for field_name, field_spec in fields.items():
                required = " (REQUIRED)" if field_spec.get('required') else ""
                field_descriptions.append(f"  - {field_name}: {field_spec['description']}{required}")

        fields_text = "\n".join(field_descriptions)

        prompt = f"""You are an expert mortgage loan data extraction AI for a comprehensive CRM system.

TASK: Analyze the email below and extract ALL relevant information into structured JSON format.

PROFILE TYPE: {profile_type}

EMAIL METADATA:
From: {email_data.get('from_email', email_data.get('sender', 'Unknown'))}
To: {email_data.get('to_emails', [])}
Subject: {email_data.get('subject', 'No Subject')}
Date: {email_data.get('sent_date', email_data.get('received_at', 'Unknown'))}

EMAIL BODY:
{email_data.get('body_text', email_data.get('raw_text', ''))}

{f"CURRENT PROFILE STATE (for update detection):{chr(10)}{json.dumps(current_profile, indent=2)}" if current_profile else "NEW PROFILE (no existing data)"}

FIELD SCHEMA FOR {profile_type.upper()}:
{fields_text}

OUTPUT FORMAT (strict JSON):
{{
  "extracted_fields": {{
    // Flat dictionary of field_name: value pairs
    // Only include fields where you found data
    // Example: "first_name": "John", "annual_income": 120000
  }},
  "confidence_scores": {{
    // Confidence 0-100 for each extracted field
    // Example: "first_name": 95, "annual_income": 80
  }},
  "calculated_fields": {{
    // Derived fields (LTV = loan_amount/property_value, DTI calculations, etc.)
  }},
  "milestone_triggers": [
    // Array of detected milestone events
    // {{"milestone": "contract_received", "date": "2025-01-15", "confidence": 90}}
  ],
  "field_updates": [
    // Changes to existing fields with reasoning (if current_profile provided)
    // {{"field": "phone", "old": "555-1111", "new": "555-2222", "reason": "Updated in email"}}
  ],
  "conflicts": [
    // Contradictions or ambiguities requiring review
    // {{"field": "loan_amount", "existing": 400000, "new": 425000, "reason": "Different amount mentioned"}}
  ],
  "suggested_actions": [
    // Recommended next steps based on email content
    // "Send pre-approval letter", "Schedule appraisal", etc.
  ],
  "email_summary": "Brief 2-3 sentence summary of email content",
  "sentiment": "positive|neutral|negative|urgent",
  "urgency_score": 0-100,
  "next_best_action": "Specific single recommended action"
}}

EXTRACTION RULES:
1. BE COMPREHENSIVE - Extract every possible field from the schema
2. BE ACCURATE - Only include data you're confident about
3. BE SMART - Calculate derivatives (LTV = loan_amount/property_value, DTI if you have monthly debt and income)
4. BE HELPFUL - Suggest actions, flag issues, detect milestones
5. BE CONSISTENT - Use standard formats (dates as YYYY-MM-DD, currencies as numbers, percentages as decimals)
6. HANDLE AMBIGUITY - If uncertain, lower the confidence score and note in conflicts

CONFIDENCE GUIDELINES:
- 95-100%: Explicit, unambiguous ("My loan number is 12345")
- 80-94%: Strong inference ("Software Engineer at Google" → likely high income bracket)
- 70-79%: Contextual inference ("Been here 3 years" → years_at_job: 3)
- 50-69%: Weak inference (estimate income from job title)
- <50%: Do not include field, note in conflicts for manual review

SPECIAL INSTRUCTIONS FOR {profile_type.upper()}:
"""

        # Add profile-specific instructions
        if profile_type == 'lead':
            prompt += """
- Focus on initial contact information and qualification data
- Detect pre-approval milestones
- Calculate LTV if both loan_amount and property_value present
- Estimate DTI if income and debts mentioned
- Flag first contact dates
"""
        elif profile_type == 'active_loan':
            prompt += """
- CRITICAL: Extract loan_number if present (required field)
- Track ALL milestone dates mentioned (appraisal, title, closing, etc.)
- Detect status changes (contract received, clear to close, funded)
- Extract team member names and emails
- Calculate days to closing if closing_date present
"""
        elif profile_type == 'mum_client':
            prompt += """
- Focus on portfolio servicing updates
- Detect refinance opportunities (rate drops, cash-out needs)
- Track engagement and touchpoints
- Note referral activity
"""
        elif profile_type == 'team_member':
            prompt += """
- Extract performance metrics (loans, volume, satisfaction)
- Note personal milestones (birthdays, anniversaries)
- Track goals and development areas
- DISC personality info if mentioned
"""

        prompt += "\n\nReturn ONLY valid JSON. Do not include any explanation or markdown formatting outside the JSON."

        return prompt

    def _extract_json(self, response_text: str) -> Dict[str, Any]:
        """Extract JSON from Claude's response, handling markdown wrapping"""

        # Try to parse directly first
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # Try to extract from markdown code block
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find any JSON object
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Failed to extract JSON
        logger.error(f"Failed to extract JSON from Claude response: {response_text[:500]}")
        raise ValueError("Could not extract valid JSON from Claude response")

    def _validate_and_enrich(
        self,
        extracted: Dict[str, Any],
        email_data: Dict[str, Any],
        processing_time_ms: int
    ) -> Dict[str, Any]:
        """
        Validate extracted data and enrich with metadata
        """

        # Ensure all required keys exist
        extracted.setdefault('extracted_fields', {})
        extracted.setdefault('confidence_scores', {})
        extracted.setdefault('calculated_fields', {})
        extracted.setdefault('milestone_triggers', [])
        extracted.setdefault('field_updates', [])
        extracted.setdefault('conflicts', [])
        extracted.setdefault('suggested_actions', [])
        extracted.setdefault('email_summary', '')
        extracted.setdefault('sentiment', 'neutral')
        extracted.setdefault('urgency_score', 50)
        extracted.setdefault('next_best_action', '')

        # Add extraction metadata
        extracted['extraction_metadata'] = {
            'parser_version': '1.0.0',
            'model': self.model,
            'timestamp': datetime.utcnow().isoformat(),
            'email_id': email_data.get('id', email_data.get('email_id', email_data.get('message_id', 'unknown'))),
            'processing_time_ms': processing_time_ms
        }

        # Validate confidence scores
        for field, confidence in extracted.get('confidence_scores', {}).items():
            if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 100):
                logger.warning(f"Invalid confidence score for {field}: {confidence}, setting to 50")
                extracted['confidence_scores'][field] = 50

        # Calculate overall extraction quality
        confidence_values = list(extracted.get('confidence_scores', {}).values())
        if confidence_values:
            avg_confidence = sum(confidence_values) / len(confidence_values)
        else:
            avg_confidence = 0

        extracted['overall_confidence'] = round(avg_confidence, 2)

        # Validate urgency score
        if not isinstance(extracted.get('urgency_score'), (int, float)) or not (0 <= extracted['urgency_score'] <= 100):
            extracted['urgency_score'] = 50

        # Count extracted fields
        extracted['field_count'] = len(extracted.get('extracted_fields', {}))

        return extracted

    def classify_email(self, email_data: Dict[str, Any]) -> str:
        """
        Determine which profile type this email relates to

        Returns: 'lead', 'active_loan', 'mum_client', or 'team_member'
        """

        subject = email_data.get('subject', '').lower()
        body = email_data.get('body_text', email_data.get('raw_text', '')).lower()

        # Simple keyword-based classification
        # In production, this could use a separate Claude call for better accuracy

        # Team member indicators
        if any(kw in subject or kw in body for kw in ['performance review', 'goals', 'disc', 'employee', 'team member']):
            return 'team_member'

        # Active loan indicators (loan number, milestones)
        if any(kw in subject or kw in body for kw in ['loan #', 'loan number', 'appraisal', 'clear to close', 'closing date', 'title company', 'underwriting']):
            return 'active_loan'

        # MUM client indicators
        if any(kw in subject or kw in body for kw in ['refinance', 'rate drop', 'portfolio', 'servicing', 'escrow']):
            return 'mum_client'

        # Default to lead for new inquiries
        return 'lead'


# Singleton instance
_claude_parser = None

def get_claude_parser() -> ClaudeEmailParser:
    """Get or create Claude parser singleton"""
    global _claude_parser
    if _claude_parser is None:
        _claude_parser = ClaudeEmailParser()
    return _claude_parser
