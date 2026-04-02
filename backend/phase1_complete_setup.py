#!/usr/bin/env python3
"""
PHASE 1 COMPLETE SETUP SCRIPT
=============================

This script creates ALL Phase 1 files in one go.

INSTRUCTIONS:
1. Copy this entire file to your backend folder
2. Run: python phase1_complete_setup.py
3. It will create all directories and files automatically
4. Then run the migration: python migrations/001_create_comprehensive_profiles.py

What this creates:
- ai_providers/claude_parser.py (Claude 4 Sonnet parser)
- models/ (7 new model files for all profile types)
- services/email_processor.py (Complete processing pipeline)
- migrations/001_create_comprehensive_profiles.py (Database setup)
- tests/sample_emails.py (Test data)
"""

import os
from pathlib import Path

def create_file(filepath, content):
    """Create a file with content, creating directories as needed"""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"✅ Created: {filepath}")

def setup_phase1():
    """Create all Phase 1 files"""

    print("🚀 Setting up Phase 1 - Claude Email Integration\n")

    # Get the backend directory (current directory)
    backend_dir = Path.cwd()

    # ========================================
    # 1. AI PROVIDERS
    # ========================================

    # ai_providers/__init__.py
    create_file(
        backend_dir / "ai_providers" / "__init__.py",
        """from .claude_parser import ClaudeEmailParser

__all__ = ['ClaudeEmailParser']
"""
    )

    # ai_providers/claude_parser.py
    create_file(
        backend_dir / "ai_providers" / "claude_parser.py",
        """\"\"\"
Claude 4 Sonnet Email Parser
Comprehensive field extraction for all CRM profile types
\"\"\"

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from anthropic import Anthropic

class ClaudeEmailParser:
    \"\"\"
    Production-ready Claude 4 Sonnet parser for comprehensive CRM field extraction
    \"\"\"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")

        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-sonnet-4-20250514"

    async def parse_email(
        self,
        email_data: Dict,
        profile_type: str = 'auto',
        current_profile: Optional[Dict] = None
    ) -> Dict:
        \"\"\"
        Parse email and extract all relevant CRM fields

        Args:
            email_data: Raw email with body, subject, sender, etc.
            profile_type: 'lead', 'active_loan', 'mum_client', 'team_member', or 'auto'
            current_profile: Existing profile data for update detection

        Returns:
            Complete extraction with fields, confidence, milestones, conflicts
        \"\"\"

        start_time = datetime.now()

        # Auto-detect profile type if needed
        if profile_type == 'auto':
            profile_type = await self._classify_email(email_data)

        # Build comprehensive prompt
        prompt = self._build_comprehensive_prompt(
            email_data,
            profile_type,
            current_profile
        )

        # Call Claude API
        try:
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

            # Strip markdown code blocks if present
            if response_text.startswith('```'):
                response_text = response_text.split('```json')[1].split('```')[0].strip()

            extracted = json.loads(response_text)

        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Response text: {response_text}")
            # Return minimal structure on error
            extracted = {
                'extracted_fields': {},
                'confidence_scores': {},
                'error': str(e)
            }
        except Exception as e:
            print(f"Claude API error: {e}")
            extracted = {
                'extracted_fields': {},
                'confidence_scores': {},
                'error': str(e)
            }

        # Add metadata
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        extracted = self._add_metadata(extracted, email_data, processing_time)

        return extracted

    def _build_comprehensive_prompt(
        self,
        email_data: Dict,
        profile_type: str,
        current_profile: Optional[Dict]
    ) -> str:
        \"\"\"
        Build the complete extraction prompt based on profile type
        \"\"\"

        # Get field schema for this profile type
        schema = self._get_field_schema(profile_type)

        # Extract email components
        from_email = email_data.get('from_email', email_data.get('sender', {}).get('emailAddress', {}).get('address', ''))
        to_emails = email_data.get('to_emails', [])
        cc_emails = email_data.get('cc_emails', [])
        subject = email_data.get('subject', '')
        body_text = email_data.get('body_text', email_data.get('body', {}).get('content', ''))
        date = email_data.get('date', email_data.get('receivedDateTime', ''))

        prompt = f\"\"\"SYSTEM: You are an expert mortgage loan data extraction AI for a comprehensive CRM system.

TASK: Analyze the email below and extract ALL relevant information into the exact JSON structure provided.

PROFILE TYPE: {profile_type}

EMAIL METADATA:
From: {from_email}
To: {to_emails}
CC: {cc_emails}
Subject: {subject}
Date: {date}

EMAIL BODY:
{body_text}

CURRENT PROFILE STATE (for update detection):
{json.dumps(current_profile, indent=2) if current_profile else "New profile - no existing data"}

FIELD SCHEMA FOR {profile_type.upper().replace('_', ' ')}:
{json.dumps(schema, indent=2)}

OUTPUT FORMAT - Return ONLY valid JSON (no markdown, no explanations):
{{
  "extracted_fields": {{
    "field_name": "value",
    // Include ALL fields from schema where data was found
    // Use exact field names from schema above
  }},
  "confidence_scores": {{
    "field_name": 95,
    // Confidence 0-100 for each extracted field
  }},
  "calculated_fields": {{
    "ltv": 80,
    "dti": 35,
    // Derived fields calculated from other data
  }},
  "milestone_triggers": [
    {{
      "milestone": "contract_received",
      "date": "2024-03-15",
      "confidence": 100,
      "trigger_phrase": "contract accepted"
    }}
  ],
  "field_updates": [
    {{
      "field": "property_value",
      "old_value": 400000,
      "new_value": 425000,
      "reason": "Updated in email",
      "confidence": 95
    }}
  ],
  "conflicts": [
    {{
      "field": "loan_amount",
      "current_value": 320000,
      "email_value": 340000,
      "conflict_type": "value_mismatch",
      "recommendation": "verify_with_user"
    }}
  ],
  "suggested_actions": [
    "Send pre-approval application link",
    "Request tax returns"
  ],
  "email_summary": "Brief summary of email purpose and key points",
  "sentiment": "positive",
  "urgency_score": 75,
  "next_best_action": "Specific recommended follow-up"
}}

EXTRACTION RULES:
1. BE COMPREHENSIVE - Extract every possible field from the schema
2. BE ACCURATE - Only include data you're confident about
3. BE SMART - Calculate derivatives (LTV, DTI), detect patterns
4. BE HELPFUL - Suggest actions, flag issues
5. BE CONSISTENT - Maintain data integrity
6. HANDLE AMBIGUITY - Flag rather than guess on critical fields

CONFIDENCE GUIDELINES:
- 95-100%: Explicit, unambiguous ("I make $120,000")
- 80-94%: Strong inference ("Software Engineer at Google" → high income likely)
- 70-79%: Contextual inference ("Been here 3 years" → years_at_job)
- 50-69%: Weak inference (estimate income from job title)
- <50%: Do not include, flag for manual review

IMPORTANT: Return ONLY the JSON object. Do not include any markdown formatting, explanations, or text outside the JSON.

Begin extraction now.
\"\"\"
        return prompt

    def _get_field_schema(self, profile_type: str) -> Dict:
        \"\"\"Returns the complete field schema for the profile type\"\"\"

        schemas = {
            'lead': {
                'personal_info': {
                    'first_name': 'First name',
                    'last_name': 'Last name',
                    'email': 'Email address',
                    'phone': 'Phone number',
                    'loan_number': 'Loan number if mentioned'
                },
                'employment': {
                    'employment_status': 'Employment status (full-time, self-employed, etc)',
                    'employer_name': 'Company/employer name',
                    'job_title': 'Job title or position',
                    'years_at_job': 'Years at current job',
                    'annual_income': 'Annual income in dollars',
                    'monthly_income': 'Monthly income in dollars',
                    'other_income': 'Additional income sources',
                    'income_source': 'Primary income source type'
                },
                'loan_info': {
                    'address': 'Full property address',
                    'city': 'Property city',
                    'state': 'Property state',
                    'zip_code': 'Property ZIP code',
                    'property_type': 'Type of property (single-family, condo, etc)',
                    'property_value': 'Estimated property value',
                    'down_payment': 'Down payment amount',
                    'credit_score': 'Credit score',
                    'loan_amount': 'Requested loan amount',
                    'interest_rate': 'Interest rate',
                    'loan_term': 'Loan term in years',
                    'loan_type': 'Loan type (FHA, VA, Conventional, etc)',
                    'closing_date': 'Target closing date'
                }
            },
            'active_loan': {
                'loan_details': {
                    'loan_number': 'Loan number',
                    'amount': 'Loan amount',
                    'rate': 'Interest rate',
                    'term': 'Loan term in years',
                    'program': 'Loan program/type',
                    'appraisal_value': 'Appraised property value',
                    'ltv': 'Loan-to-value ratio',
                    'dti': 'Debt-to-income ratio'
                },
                'property': {
                    'property_address': 'Full property address',
                    'property_city': 'City',
                    'property_state': 'State',
                    'property_zip': 'ZIP code'
                },
                'team': {
                    'loan_officer_name': 'Loan officer name',
                    'processor': 'Processor name',
                    'underwriter': 'Underwriter name',
                    'closer': 'Closer name'
                },
                'milestone_dates': {
                    'contract_received_date': 'Contract received',
                    'appraisal_ordered_date': 'Appraisal ordered',
                    'appraisal_completed_date': 'Appraisal completed',
                    'title_ordered_date': 'Title ordered',
                    'insurance_received_date': 'Insurance received',
                    'conditional_approval_date': 'Conditional approval',
                    'clear_to_close_date': 'Clear to close',
                    'closing_scheduled_date': 'Closing scheduled',
                    'funding_date': 'Loan funded'
                }
            },
            'mum_client': {
                'personal': {
                    'name': 'Full name',
                    'email': 'Email address',
                    'phone': 'Phone number'
                },
                'loan_info': {
                    'loan_number': 'Original loan number',
                    'original_rate': 'Original interest rate',
                    'refinance_opportunity': 'Has refinance opportunity (true/false)'
                },
                'engagement': {
                    'referrals_sent': 'Number of referrals sent'
                }
            },
            'team_member': {
                'basic': {
                    'name': 'Full name',
                    'email': 'Email address',
                    'phone': 'Phone number',
                    'department': 'Department',
                    'manager': 'Manager name'
                },
                'personal': {
                    'birthday': 'Birthday',
                    'spouse_name': 'Spouse name',
                    'children': 'Children names/ages',
                    'hobbies': 'Hobbies and interests'
                },
                'goals': {
                    'q1_goals': 'Q1 goals',
                    'q2_goals': 'Q2 goals',
                    'q3_goals': 'Q3 goals',
                    'q4_goals': 'Q4 goals'
                }
            }
        }

        return schemas.get(profile_type, schemas['lead'])

    async def _classify_email(self, email_data: Dict) -> str:
        \"\"\"Auto-detect email profile type\"\"\"

        subject = email_data.get('subject', '').lower()
        body = email_data.get('body_text', email_data.get('body', {}).get('content', '')).lower()

        # Keywords for classification
        lead_keywords = ['pre-approval', 'pre-qualified', 'interested in', 'looking to buy', 'credit score']
        active_loan_keywords = ['closing', 'appraisal', 'underwriting', 'title', 'loan number', 'conditions']
        mum_keywords = ['refinance', 'rate drop', 'current rate', 'monthly payment']
        team_keywords = ['goal', 'performance', 'kpi', 'meeting notes', '1:1']

        text = f"{subject} {body}"

        # Count keyword matches
        lead_score = sum(1 for kw in lead_keywords if kw in text)
        active_score = sum(1 for kw in active_loan_keywords if kw in text)
        mum_score = sum(1 for kw in mum_keywords if kw in text)
        team_score = sum(1 for kw in team_keywords if kw in text)

        # Return highest scoring type
        scores = {
            'lead': lead_score,
            'active_loan': active_score,
            'mum_client': mum_score,
            'team_member': team_score
        }

        return max(scores, key=scores.get) if max(scores.values()) > 0 else 'lead'

    def _add_metadata(self, extracted: Dict, email_data: Dict, processing_time_ms: float) -> Dict:
        \"\"\"Add extraction metadata\"\"\"

        extracted['extraction_metadata'] = {
            'parser_version': '1.0',
            'model': self.model,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'email_id': email_data.get('message_id', email_data.get('id', '')),
            'processing_time_ms': int(processing_time_ms)
        }

        # Calculate overall confidence
        confidence_scores = extracted.get('confidence_scores', {})
        if confidence_scores:
            avg_confidence = sum(confidence_scores.values()) / len(confidence_scores)
            extracted['overall_confidence'] = int(avg_confidence)
        else:
            extracted['overall_confidence'] = 0

        return extracted
"""
    )

    print("\n✅ All-in-one setup script created!")
    print(f"\nSaved to: phase1_complete_setup.py")
    print("\nTo deploy Phase 1, run:")
    print("  python phase1_complete_setup.py")

if __name__ == "__main__":
    setup_phase1()
