"""
Process Transcript and Create Lead

Processes a call transcript through all extraction agents and creates
a lead in the CRM with the extracted data.
"""

import asyncio
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from .data_contracts import TranscriptSegment, SpeakerRole, ExtractionResult
from .agents import (
    IdentityExtractionAgent,
    PropertyExtractionAgent,
    EmploymentExtractionAgent,
    FinancialExtractionAgent,
    ComplianceExtractionAgent,
    IntentExtractionAgent,
)

logger = logging.getLogger(__name__)


# Role-based keywords for speaker identification (case-insensitive)
ROLE_KEYWORDS = {
    SpeakerRole.AI_LO: [
        'loan officer', 'lo', 'agent', 'advisor', 'consultant',
        'mortgage officer', 'lender', 'originator', 'representative',
        'rep', 'assistant', 'ai', 'bot',
    ],
    SpeakerRole.BORROWER: [
        'borrower', 'applicant', 'customer', 'client', 'caller',
        'prospect', 'lead', 'user',
    ],
    SpeakerRole.CO_BORROWER: [
        'co-borrower', 'coborrower', 'co-applicant', 'coapplicant',
        'spouse', 'partner',
    ],
    SpeakerRole.HUMAN_LO: [
        'human lo', 'human agent', 'supervisor', 'manager',
    ],
}

# LO speech patterns - questions and professional language
# Pre-compiled for performance and ReDoS protection
LO_SPEECH_PATTERNS = [
    r'\b(what is your|can you tell me|could you|may i|let me)\b',
    r'\b(perfect|great|got it|sounds good|thank you for)\b',
    r'\b(next step|i\'ll need|we\'ll need|let\'s talk about)\b',
    r'\b(verify|confirm|walk through|process)\b',
    r'\b(do you have|are you|have you ever|will you be)\b',
]
# Pre-compiled patterns for better performance
LO_SPEECH_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in LO_SPEECH_PATTERNS]

# Borrower speech patterns - personal info and short responses
BORROWER_SPEECH_PATTERNS = [
    r'\b(my name is|i am|i\'m|i work|i make|i have)\b',
    r'\b(yes|no|yeah|nope|correct|right)\b',
    r'^(about |around |roughly |approximately )?[\$]?\d',  # Amounts
    r'\b(we\'ve been|we are|we\'re)\b',
]
# Pre-compiled patterns for better performance
BORROWER_SPEECH_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in BORROWER_SPEECH_PATTERNS]

# Default segment duration in seconds when no timestamps are available
DEFAULT_SEGMENT_DURATION_SECONDS = 10


def identify_speaker_role(
    speaker_name: str,
    text: str = "",
    speaker_mapping: Optional[Dict[str, SpeakerRole]] = None,
) -> SpeakerRole:
    """
    Identify speaker role from name and optionally from speech content.

    Args:
        speaker_name: The speaker label from the transcript
        text: The text spoken (used for heuristic inference)
        speaker_mapping: Optional explicit mapping of names to roles

    Returns:
        SpeakerRole enum value
    """
    speaker_lower = speaker_name.lower().strip()

    # 1. Check explicit mapping first (if provided)
    if speaker_mapping:
        for name, role in speaker_mapping.items():
            if name.lower() == speaker_lower:
                return role

    # 2. Check role-based keywords (prioritize longer/more specific matches)
    # Sort roles by checking CO_BORROWER before BORROWER to avoid partial matches
    role_check_order = [
        SpeakerRole.CO_BORROWER,  # Check first (more specific than BORROWER)
        SpeakerRole.AI_LO,
        SpeakerRole.HUMAN_LO,
        SpeakerRole.BORROWER,  # Check last (could be substring of CO_BORROWER)
    ]

    for role in role_check_order:
        keywords = ROLE_KEYWORDS.get(role, [])
        for keyword in keywords:
            # Use word boundary matching for more accuracy
            if keyword == speaker_lower:
                return role
            # Check if keyword is in speaker name (with word boundary awareness)
            if re.search(rf'\b{re.escape(keyword)}\b', speaker_lower):
                return role
            # Also check simple containment for multi-word keywords
            if ' ' in keyword and keyword in speaker_lower:
                return role

    # 3. Check for common prefixes/patterns in speaker labels
    # e.g., "Speaker 1", "Agent (Tim)", "[LO]", etc.
    if re.search(r'\b(speaker\s*1|agent|lo|rep)\b', speaker_lower):
        return SpeakerRole.AI_LO
    if re.search(r'\b(speaker\s*2|caller|customer)\b', speaker_lower):
        return SpeakerRole.BORROWER

    # 4. Use speech content heuristics if text is provided
    if text:
        text_lower = text.lower()

        # Use pre-compiled patterns for performance
        lo_score = sum(1 for p in LO_SPEECH_PATTERNS_COMPILED if p.search(text_lower))
        borrower_score = sum(1 for p in BORROWER_SPEECH_PATTERNS_COMPILED if p.search(text_lower))

        if lo_score > borrower_score and lo_score >= 2:
            return SpeakerRole.AI_LO
        if borrower_score > lo_score and borrower_score >= 2:
            return SpeakerRole.BORROWER

    # 5. Return unknown if we can't determine
    return SpeakerRole.UNKNOWN


def infer_roles_from_conversation(
    raw_segments: List[Tuple[str, str]],
    speaker_mapping: Optional[Dict[str, SpeakerRole]] = None,
) -> Dict[str, SpeakerRole]:
    """
    Infer speaker roles from conversation patterns.

    In mortgage calls, the LO typically:
    - Speaks first (greeting/introduction)
    - Asks questions
    - Uses professional/structured language

    The borrower typically:
    - Responds to questions
    - Provides personal information
    - Gives shorter responses

    Args:
        raw_segments: List of (speaker_name, text) tuples
        speaker_mapping: Optional explicit mapping

    Returns:
        Dict mapping speaker names to inferred roles
    """
    inferred_mapping = {}

    if not raw_segments:
        return inferred_mapping

    # Get unique speakers
    unique_speakers = []
    for speaker, _ in raw_segments:
        if speaker not in unique_speakers:
            unique_speakers.append(speaker)

    num_speakers = len(unique_speakers)

    # Handle edge case: single speaker
    if num_speakers == 1:
        # Can't determine role with only one speaker - assume borrower providing info
        logger.debug(f"Single speaker detected: '{unique_speakers[0]}' - defaulting to BORROWER")
        inferred_mapping[unique_speakers[0]] = SpeakerRole.BORROWER
        return inferred_mapping

    # Handle edge case: 3+ speakers (conference call)
    if num_speakers > 2:
        logger.debug(f"Multi-party call detected with {num_speakers} speakers - scoring each")
        # Score each speaker and assign roles based on LO speech patterns
        speaker_scores = {}
        for speaker in unique_speakers:
            speaker_text = ' '.join(text for s, text in raw_segments if s == speaker)
            lo_score = sum(1 for p in LO_SPEECH_PATTERNS_COMPILED if p.search(speaker_text))
            speaker_scores[speaker] = lo_score

        # Speaker with highest LO score is the loan officer
        sorted_speakers = sorted(speaker_scores.items(), key=lambda x: x[1], reverse=True)
        inferred_mapping[sorted_speakers[0][0]] = SpeakerRole.AI_LO
        # All others are borrowers (could be co-borrower, but we use BORROWER for simplicity)
        for speaker, _ in sorted_speakers[1:]:
            inferred_mapping[speaker] = SpeakerRole.BORROWER

        logger.debug(f"Multi-party inferred roles: {inferred_mapping}")
        return inferred_mapping

    # Standard case: exactly 2 speakers
    if not speaker_mapping:
        speaker1, speaker2 = unique_speakers

        # Aggregate text for each speaker
        speaker1_text = ' '.join(text for s, text in raw_segments if s == speaker1)
        speaker2_text = ' '.join(text for s, text in raw_segments if s == speaker2)

        # Score each speaker using pre-compiled patterns
        s1_lo_score = sum(1 for p in LO_SPEECH_PATTERNS_COMPILED if p.search(speaker1_text))
        s2_lo_score = sum(1 for p in LO_SPEECH_PATTERNS_COMPILED if p.search(speaker2_text))

        # First speaker in mortgage calls is usually the LO
        first_speaker_bonus = 2

        s1_total = s1_lo_score + first_speaker_bonus
        s2_total = s2_lo_score

        if s1_total > s2_total:
            inferred_mapping[speaker1] = SpeakerRole.AI_LO
            inferred_mapping[speaker2] = SpeakerRole.BORROWER
        elif s2_total > s1_total:
            inferred_mapping[speaker1] = SpeakerRole.BORROWER
            inferred_mapping[speaker2] = SpeakerRole.AI_LO
        else:
            # Tie-breaker: first speaker is LO
            inferred_mapping[speaker1] = SpeakerRole.AI_LO
            inferred_mapping[speaker2] = SpeakerRole.BORROWER

        logger.debug(f"Inferred speaker roles: {inferred_mapping}")

    return inferred_mapping


def parse_transcript(
    transcript_text: str,
    speaker_mapping: Optional[Dict[str, SpeakerRole]] = None,
) -> List[TranscriptSegment]:
    """
    Parse a raw transcript into TranscriptSegments.

    Handles formats like:
    - "Speaker Name:" followed by text on next lines
    - "[Speaker Name] text"
    - "Speaker Name: text" on same line

    Args:
        transcript_text: Raw transcript text
        speaker_mapping: Optional dict mapping speaker names to roles.
            Example: {"Tim": SpeakerRole.AI_LO, "Jack": SpeakerRole.BORROWER}
            If not provided, roles are inferred from keywords and patterns.

    Returns:
        List of TranscriptSegment objects
    """
    segments = []
    lines = transcript_text.strip().split('\n')

    # First pass: collect raw segments
    raw_segments = []
    current_speaker = None
    current_text = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for different speaker line formats
        speaker_match = None
        remaining_text = None

        # Format: "[Speaker Name] text" or "(Speaker Name) text"
        bracket_match = re.match(r'[\[\(]([^\]\)]+)[\]\)]\s*(.*)$', line)
        if bracket_match:
            speaker_match = bracket_match.group(1).strip()
            remaining_text = bracket_match.group(2).strip() or None

        # Format: "Speaker Name: text" (inline) - only if not already matched
        if not speaker_match:
            inline_match = re.match(r'^([A-Za-z][A-Za-z0-9\s\-]{0,30}):\s+(.+)$', line)
            if inline_match:
                speaker_match = inline_match.group(1).strip()
                remaining_text = inline_match.group(2).strip() or None

        # Format: "Speaker Name:" (speaker label on its own line) - only if not already matched
        if not speaker_match and line.endswith(':') and len(line) < 50:
            speaker_match = line[:-1].strip()

        if speaker_match:
            # Save previous segment before starting new one
            if current_speaker and current_text:
                text = ' '.join(current_text).strip()
                if text:
                    raw_segments.append((current_speaker, text))

            # Start new segment
            current_speaker = speaker_match
            current_text = [remaining_text] if remaining_text else []
        else:
            # Continue current segment
            current_text.append(line)

    # Don't forget the last segment
    if current_speaker and current_text:
        text = ' '.join(current_text).strip()
        if text:
            raw_segments.append((current_speaker, text))

    # Second pass: infer roles if not explicitly provided
    combined_mapping = speaker_mapping.copy() if speaker_mapping else {}

    # Add inferred roles for speakers not in explicit mapping
    inferred = infer_roles_from_conversation(raw_segments, speaker_mapping)
    for speaker, role in inferred.items():
        if speaker not in combined_mapping:
            combined_mapping[speaker] = role

    # Third pass: create TranscriptSegments with roles
    for idx, (speaker, text) in enumerate(raw_segments):
        # Get role from mapping, or identify from content
        if speaker in combined_mapping:
            role = combined_mapping[speaker]
        else:
            role = identify_speaker_role(speaker, text, combined_mapping)
            # Cache for consistency
            combined_mapping[speaker] = role

        segments.append(TranscriptSegment(
            index=idx,
            speaker=role,
            text=text,
            start_time=float(idx * DEFAULT_SEGMENT_DURATION_SECONDS),
            end_time=float((idx + 1) * DEFAULT_SEGMENT_DURATION_SECONDS),
        ))

    return segments


async def extract_all(
    segments: List[TranscriptSegment],
    existing_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, ExtractionResult]:
    """
    Run all extraction agents on the transcript segments.

    Returns:
        Dict mapping agent name to ExtractionResult
    """
    agents = [
        IdentityExtractionAgent(),
        PropertyExtractionAgent(),
        EmploymentExtractionAgent(),
        FinancialExtractionAgent(),
        ComplianceExtractionAgent(),
        IntentExtractionAgent(),
    ]

    results = {}

    # Run all agents
    for agent in agents:
        try:
            result = await agent.extract(segments, existing_data)
            results[agent.AGENT_NAME] = result
            logger.info(f"{agent.AGENT_NAME}: {len(result.extractions)} fields extracted")
        except Exception as e:
            logger.error(f"Agent {agent.AGENT_NAME} failed: {e}")
            results[agent.AGENT_NAME] = ExtractionResult(agent_name=agent.AGENT_NAME)

    return results


def extractions_to_lead_data(results: Dict[str, ExtractionResult]) -> Dict[str, Any]:
    """
    Map extraction results to Lead model fields.

    Returns:
        Dict of field names to values for Lead creation
    """
    lead_data = {}

    # Flatten all extractions into a lookup dict
    all_extractions = {}
    for agent_name, result in results.items():
        for extraction in result.extractions:
            # Store with confidence for potential conflict resolution
            key = extraction.field_name
            if key not in all_extractions or extraction.confidence > all_extractions[key]['confidence']:
                all_extractions[key] = {
                    'value': extraction.value,
                    'confidence': extraction.confidence,
                    'agent': agent_name,
                }

    def get(field_name: str, default=None):
        """Get extracted value by field name."""
        if field_name in all_extractions:
            return all_extractions[field_name]['value']
        return default

    # Identity fields
    first_name = get('first_name')
    last_name = get('last_name')

    if first_name and last_name:
        lead_data['name'] = f"{first_name} {last_name}"
        lead_data['first_name'] = first_name
        lead_data['last_name'] = last_name

    lead_data['email'] = get('email')
    lead_data['phone'] = get('phone')

    # Property/Address fields
    street = get('street') or get('street_address')
    city = get('city')
    state = get('state')
    zip_code = get('zip') or get('zip_code')

    if street:
        address_parts = [street]
        if city:
            address_parts.append(city)
        if state:
            address_parts.append(state)
        if zip_code:
            address_parts.append(zip_code)
        lead_data['address'] = ', '.join(address_parts)

    lead_data['city'] = city
    lead_data['state'] = state
    lead_data['zip_code'] = zip_code
    lead_data['property_type'] = get('property_type')

    # Financial fields
    purchase_price = get('purchase_price')
    if purchase_price:
        lead_data['property_value'] = float(purchase_price)
        lead_data['loan_amount'] = float(purchase_price) * 0.9  # Assuming 10% down

    down_payment_pct = get('down_payment_percentage') or get('down_payment_percent')
    down_payment_amt = get('down_payment_amount') or get('down_payment')

    if down_payment_amt:
        lead_data['down_payment'] = float(down_payment_amt)
    elif down_payment_pct and purchase_price:
        lead_data['down_payment'] = float(purchase_price) * (float(down_payment_pct) / 100)

    # Income/Employment
    annual_salary = get('annual_salary')
    monthly_salary = get('monthly_salary')

    if annual_salary:
        lead_data['annual_income'] = float(annual_salary)
    elif monthly_salary:
        lead_data['annual_income'] = float(monthly_salary) * 12

    lead_data['employer_name'] = get('employer') or get('employer_name')
    lead_data['employment_status'] = get('employment_type') or 'EMPLOYED'

    # Housing expenses
    monthly_payment = get('monthly_payment') or get('current_housing_payment')
    if monthly_payment:
        lead_data['present_housing_expense'] = float(monthly_payment)
        lead_data['present_monthly_payment'] = float(monthly_payment)

    ownership_status = get('ownership_status') or get('current_housing_status')
    if ownership_status:
        lead_data['property_ownership_type'] = ownership_status

    # Loan details
    lead_data['loan_purpose'] = get('loan_purpose')
    lead_data['loan_type'] = get('loan_type_preference')
    lead_data['rate_type'] = get('rate_type_preference')
    lead_data['occupancy_type'] = 'PRIMARY' if get('will_occupy_as_primary') else get('property_use')

    # Compliance/Declarations
    first_time = get('first_time_buyer') or get('is_first_time_buyer')
    if first_time is not None:
        lead_data['first_time_buyer'] = bool(first_time)

    # Credit score (if mentioned)
    credit_score = get('credit_score') or get('estimated_credit_score')
    if credit_score:
        lead_data['credit_score'] = int(credit_score)

    # Citizenship
    citizenship = get('citizenship_status')
    if citizenship:
        lead_data['meta_data'] = lead_data.get('meta_data', {})
        lead_data['meta_data']['citizenship_status'] = citizenship

    # ECOA: marital_status is stored in meta_data for property-rights analysis
    # (community property states) and HMDA reporting only.  It must NEVER be
    # passed to scoring, pricing, eligibility, or any decisioning function.
    marital = get('marital_status')
    if marital:
        lead_data['meta_data'] = lead_data.get('meta_data', {})
        lead_data['meta_data']['marital_status'] = marital

    # Store all extractions in user_metadata for reference
    lead_data['user_metadata'] = {
        'call_intelligence_extractions': {
            agent: [
                {
                    'field': e.field_name,
                    'value': e.value,
                    'confidence': e.confidence,
                    'method': e.extraction_method,
                }
                for e in result.extractions
            ]
            for agent, result in results.items()
        },
        'extraction_timestamp': datetime.now(timezone.utc).isoformat(),
    }

    # Set source
    lead_data['source'] = 'call_intelligence'
    lead_data['lead_received_date'] = datetime.now(timezone.utc)

    # Filter out None values
    lead_data = {k: v for k, v in lead_data.items() if v is not None}

    return lead_data


async def process_transcript_and_create_lead(
    transcript_text: str,
    db_session: Optional[Any] = None,  # SQLAlchemy Session, Optional to avoid import
    owner_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    speaker_mapping: Optional[Dict[str, SpeakerRole]] = None,
) -> Dict[str, Any]:
    """
    Full pipeline: parse transcript, extract data, create lead.

    Args:
        transcript_text: Raw transcript text
        db_session: SQLAlchemy session (optional - for actual DB creation)
        owner_id: Loan officer user ID
        organization_id: Organization/tenant ID
        speaker_mapping: Optional dict mapping speaker names to roles.
            Example: {"Tim": SpeakerRole.AI_LO, "Jack": SpeakerRole.BORROWER}
            If not provided, roles are inferred automatically from patterns.

    Returns:
        Dict with extraction results and lead data
    """
    # Parse transcript
    logger.info("Parsing transcript...")
    segments = parse_transcript(transcript_text, speaker_mapping)
    logger.info(f"Parsed {len(segments)} segments")

    # Run extraction
    logger.info("Running extraction agents...")
    results = await extract_all(segments)

    # Map to lead data
    logger.info("Mapping to lead fields...")
    lead_data = extractions_to_lead_data(results)

    # Add owner and organization if provided
    if owner_id:
        lead_data['owner_id'] = owner_id
    if organization_id:
        lead_data['organization_id'] = organization_id

    # Create lead in database if session provided
    lead_id = None
    if db_session:
        try:
            from database.models.lead_loan import Lead
            from database.enums import LeadStage

            lead = Lead(
                stage=LeadStage.NEW,
                **lead_data
            )
            db_session.add(lead)
            db_session.commit()
            db_session.refresh(lead)
            lead_id = lead.id
            logger.info(f"Created lead {lead_id}: {lead.name}")
        except Exception as e:
            logger.error(f"Failed to create lead: {e}")
            db_session.rollback()
            raise

    # Build summary
    extraction_summary = {}
    for agent_name, result in results.items():
        extraction_summary[agent_name] = {
            'fields_extracted': len(result.extractions),
            'extractions': [
                {
                    'field': e.field_name,
                    'value': e.value,
                    'confidence': e.confidence,
                    'method': getattr(e, 'extraction_method', 'unknown'),
                }
                for e in result.extractions
            ],
            'warnings': result.warnings,
        }

    # Count segments by speaker role
    speaker_distribution = {}
    for seg in segments:
        role_name = seg.speaker.value if hasattr(seg.speaker, 'value') else str(seg.speaker)
        speaker_distribution[role_name] = speaker_distribution.get(role_name, 0) + 1

    return {
        'lead_id': lead_id,
        'lead_data': lead_data,
        'extraction_summary': extraction_summary,
        'segments_processed': len(segments),
        'speaker_distribution': speaker_distribution,
    }


def format_extraction_report(result: Dict[str, Any]) -> str:
    """
    Format extraction results as a human-readable report string.

    Args:
        result: Dict from process_transcript_and_create_lead() containing:
            - segments_processed: Number of transcript segments
            - speaker_distribution: Dict of role -> segment count
            - lead_id: Created lead ID (optional)
            - extraction_summary: Dict of agent -> extraction details
            - lead_data: Mapped lead fields

    Returns:
        Formatted multi-line string report suitable for logging or display
    """
    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("CALL INTELLIGENCE EXTRACTION REPORT")
    lines.append("=" * 70)

    lines.append(f"\nSegments Processed: {result['segments_processed']}")

    # Show speaker distribution
    if result.get('speaker_distribution'):
        lines.append("\nSpeaker Roles Detected:")
        for role, count in result['speaker_distribution'].items():
            lines.append(f"  - {role}: {count} segments")

    if result.get('lead_id'):
        lines.append(f"\nLead Created: ID {result['lead_id']}")

    lines.append("\n" + "-" * 70)
    lines.append("EXTRACTION RESULTS BY AGENT")
    lines.append("-" * 70)

    for agent_name, summary in result['extraction_summary'].items():
        lines.append(f"\n### {agent_name.upper()} ({summary['fields_extracted']} fields)")

        for ext in summary['extractions']:
            conf = ext['confidence']
            conf_indicator = "[OK]" if conf >= 80 else "[??]" if conf >= 60 else "[!!]"
            method = ext.get('method', 'unknown')
            method_tag = f"[{method}]" if method else ""

            # Format value (truncate long strings)
            value = ext['value']
            if isinstance(value, str) and len(value) > 50:
                value = value[:47] + "..."

            lines.append(f"  {conf_indicator} {ext['field']}: {value} (conf: {conf}) {method_tag}")

        if summary['warnings']:
            lines.append(f"  Warnings: {summary['warnings']}")

    lines.append("\n" + "-" * 70)
    lines.append("LEAD DATA (Mapped Fields)")
    lines.append("-" * 70)

    lead_data = result['lead_data']

    # Group fields for display
    groups = {
        'Identity': ['name', 'first_name', 'last_name', 'email', 'phone'],
        'Address': ['address', 'city', 'state', 'zip_code'],
        'Property': ['property_type', 'property_value', 'loan_amount', 'down_payment', 'occupancy_type'],
        'Employment': ['employer_name', 'employment_status', 'annual_income'],
        'Housing': ['present_housing_expense', 'present_monthly_payment', 'property_ownership_type'],
        'Loan': ['loan_purpose', 'loan_type', 'rate_type', 'first_time_buyer'],
    }

    for group_name, fields in groups.items():
        group_data = {f: lead_data.get(f) for f in fields if f in lead_data}
        if group_data:
            lines.append(f"\n{group_name}:")
            for field, value in group_data.items():
                if isinstance(value, float):
                    if 'payment' in field or 'income' in field or 'value' in field or 'amount' in field:
                        lines.append(f"  {field}: ${value:,.2f}")
                    else:
                        lines.append(f"  {field}: {value}")
                else:
                    lines.append(f"  {field}: {value}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def log_extraction_report(result: Dict[str, Any]) -> None:
    """
    Log extraction results using the logging infrastructure.

    Use this instead of print_extraction_report() in production code.
    Logs each section at INFO level for proper log capture.

    Args:
        result: Dict from process_transcript_and_create_lead()
    """
    report = format_extraction_report(result)
    for line in report.split("\n"):
        if line.strip():  # Skip empty lines
            logger.info(line)


def print_extraction_report(result: Dict[str, Any]) -> None:
    """
    Print a formatted extraction report to stdout.

    Note: For production use, prefer log_extraction_report() which uses
    the logging infrastructure. This function is provided for CLI/debugging.

    Args:
        result: Dict from process_transcript_and_create_lead()
    """
    logger.info(format_extraction_report(result))


# CLI entry point
if __name__ == "__main__":
    # Sample transcript for testing
    sample_transcript = """
Tim:
Hey Jack, this is Tim. How are you today?

Jack:
Hey Tim, I'm doing well. How about you?

Tim:
Doing great, thanks. I appreciate you taking the time to talk today. Did I catch you at a decent time?

Jack:
Yeah, now's fine.

Tim:
Perfect. So the goal of this call is just to walk through everything we need for your loan application in a conversational way, make sure I understand what you're trying to accomplish, and then we'll line up next steps so this stays smooth. If anything I ask feels repetitive or confusing, stop me anytime. Sound good?

Jack:
Yeah, sounds good.

Tim:
Alright, let's start big picture. What's prompting you to buy a home right now?

Jack:
We've been renting for a while and just feel like it's time to own something.

Tim:
That makes sense. Are you already under contract on a home, or are you still looking?

Jack:
Still looking.

Tim:
Okay, perfect. That's actually ideal. Do you have a price range in mind?

Jack:
Probably around four hundred thousand.

Tim:
Got it. And when you buy, will this be your primary residence—where you live full time?

Jack:
Yes.

Tim:
Good. And roughly how much are you thinking about putting down?

Jack:
Probably around ten percent.

Tim:
Okay. Let me grab some personal info next, just so I have everything exactly right. What's your full legal name as it appears on your driver's license?

Jack:
Jack Michael Daniels.

Tim:
Have you ever gone by any other names legally?

Jack:
No.

Tim:
What's your date of birth?

Jack:
March 14th, 1989.

Tim:
And your Social Security number?

Jack:
***-**-****.

Tim:
Thank you. Best phone number for you?

Jack:
Same one I'm calling from.

Tim:
And what's the best email address for you?

Jack:
jack.daniels@email.com

Tim:
Perfect. What's your marital status—married, unmarried, or legally separated?

Jack:
Married.

Tim:
Will your spouse be on the loan with you?

Jack:
No, just me.

Tim:
Okay. Let's go through your housing history. What's your current address?

Jack:
123 Oak Street, Charleston, South Carolina.

Tim:
How long have you lived there?

Jack:
About three years.

Tim:
And you're renting there?

Jack:
Yes.

Tim:
What's your monthly rent?

Jack:
About $2,100.

Tim:
Got it. Before that, did you live anywhere else in the last two years?

Jack:
No, same place.

Tim:
Perfect. Now let's talk about work. Who's your current employer?

Jack:
I work for Atlantic Tech Solutions.

Tim:
What's your job title?

Jack:
Senior project manager.

Tim:
And how long have you been there?

Jack:
About four years.

Tim:
Are you paid salary, hourly, or something else?

Jack:
Salary, with a bonus.

Tim:
What's your base salary?

Jack:
$110,000 a year.

Tim:
And do you receive a bonus every year?

Jack:
Yes.

Tim:
About how long have you been receiving bonuses?

Jack:
At least three years.

Tim:
Any other income coming in—side work, rental income, anything like that?

Jack:
No.

Tim:
Okay. Let's talk about what you have saved. What bank do you primarily use?

Jack:
Wells Fargo.

Tim:
Do you have checking and savings there?

Jack:
Yes.

Tim:
Roughly how much do you have across those accounts right now?

Jack:
Around $65,000.

Tim:
Any retirement accounts like a 401k?

Jack:
Yes, through work.

Tim:
Good. Will any of the money for the down payment be coming from a gift from family?

Jack:
No.

Tim:
Alright. Now I'm going to ask about debts—nothing unusual here. Do you have any car loans?

Jack:
Yes, one.

Tim:
Any student loans?

Jack:
Yes.

Tim:
Credit cards?

Jack:
Yes, but nothing crazy.

Tim:
Do you pay alimony or child support?

Jack:
No.

Tim:
Do you own any real estate currently?

Jack:
No.

Tim:
Okay. Now I'm going to ask a few required yes-or-no questions. Have you ever filed for bankruptcy?

Jack:
No.

Tim:
Ever had a foreclosure, short sale, or deed-in-lieu?

Jack:
No.

Tim:
Are you currently delinquent on any federal debt, like student loans or taxes?

Jack:
No.

Tim:
Are you a co-signer on anyone else's loan?

Jack:
No.

Tim:
Have you borrowed any money for your down payment?

Jack:
No.

Tim:
Have you opened any new credit accounts in the last couple of months?

Jack:
No.

Tim:
Are you currently involved in any lawsuits that could result in a financial obligation?

Jack:
No.

Tim:
And just to confirm, you're a U.S. citizen?

Jack:
Yes.

Tim:
Perfect. The next questions are optional and only for government monitoring—you don't have to answer them if you don't want to. How do you identify your ethnicity?

Jack:
Not Hispanic or Latino.

Tim:
Race?

Jack:
White.

Tim:
Sex?

Jack:
Male.

Tim:
Thanks. The next step after this call is running credit and finalizing your pre-approval. Do I have your permission to pull your credit and verify employment, income, and assets as needed?

Jack:
Yes.

Tim:
Perfect. Here's what happens next. I'm going to introduce you to my Production Assistant—they'll help finalize the application, collect documents, and keep everything organized. It usually takes about 20 minutes. I'm seeing availability tomorrow afternoon or Thursday morning. Which works better for you?

Jack:
Tomorrow afternoon works.

Tim:
Great. After we hang up, you'll also get an email with access to your secure client portal. That's where you'll upload documents, track next steps, and message us anytime. It's very straightforward, and we'll guide you exactly on what's needed.

Jack:
Sounds good.

Tim:
Before we wrap up, what questions do you have for me right now?

Jack:
No questions at the moment.

Tim:
Alright. You're in a good position, Jack. We'll take this step by step and make sure there are no surprises. Thanks again for your time today—I'll talk to you soon.

Jack:
Thanks, Tim.

Tim:
Talk soon.
"""

    async def main():
        result = await process_transcript_and_create_lead(sample_transcript)
        print_extraction_report(result)

    asyncio.run(main())
