"""
AI Call Scripts for Outbound Scheduling Calls

Script templates for each caller category (new lead, active client, MUM)
with dynamic personalization and A/B testing support.

Each script provides:
- system_prompt: Instructions for the AI agent's behavior and goals
- first_message: The opening line when the contact answers
- end_call_message: Closing message when the call ends
- key_points: Talking points for the AI to cover
- objection_handling: Guidance for common objections
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CallScript:
    """A fully-built call script ready for Vapi."""
    system_prompt: str
    first_message: str
    end_call_message: str
    key_points: List[str] = field(default_factory=list)
    objection_handling: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class CallScriptEngine:
    """
    Builds personalized call scripts based on caller type, contact data,
    and script variant selection.

    Supports A/B testing via script variants (e.g., "default", "warm", "direct").
    """

    def build_script(
        self,
        caller_type: str,
        contact: Any,  # ContactInfo from ai_outbound_scheduler
        variant: str = "default",
    ) -> CallScript:
        """
        Build a personalized call script.

        Args:
            caller_type: "new_lead", "active_client", or "mum"
            contact: ContactInfo with personalization data
            variant: Script variant for A/B testing

        Returns:
            CallScript ready for Vapi
        """
        # Extract personalization tokens
        tokens = self._extract_tokens(contact)

        if caller_type == "new_lead":
            return self._build_new_lead_script(tokens, variant)
        elif caller_type == "active_client":
            return self._build_active_client_script(tokens, variant)
        elif caller_type == "mum":
            return self._build_mum_script(tokens, variant)
        else:
            logger.warning(f"Unknown caller_type '{caller_type}', using new_lead default")
            return self._build_new_lead_script(tokens, variant)

    def get_available_variants(self, caller_type: str) -> List[Dict[str, str]]:
        """Get available script variants for a caller type."""
        variants = {
            "new_lead": [
                {"id": "default", "name": "Standard Introduction", "description": "Professional intro, focus on needs assessment"},
                {"id": "warm", "name": "Warm & Friendly", "description": "More casual, relationship-focused approach"},
                {"id": "direct", "name": "Direct Value", "description": "Lead with rate/savings, get to the point quickly"},
            ],
            "active_client": [
                {"id": "default", "name": "Progress Update", "description": "Update on loan status, discuss next steps"},
                {"id": "milestone", "name": "Milestone Celebration", "description": "Celebrate progress, build excitement"},
                {"id": "proactive", "name": "Proactive Check-in", "description": "Address potential concerns before they arise"},
            ],
            "mum": [
                {"id": "default", "name": "Annual Review", "description": "Standard annual mortgage review"},
                {"id": "refi", "name": "Refinance Opportunity", "description": "Lead with potential savings from refinancing"},
                {"id": "referral", "name": "Referral Request", "description": "Check in and ask for referrals"},
            ],
        }
        return variants.get(caller_type, variants["new_lead"])

    # =========================================================================
    # NEW LEAD SCRIPTS
    # =========================================================================

    def _build_new_lead_script(self, tokens: Dict[str, str], variant: str) -> CallScript:
        """Build script for new lead outreach."""
        first_name = tokens["first_name"]
        lo_name = tokens["lo_name"]
        company = tokens["company"]
        loan_purpose = tokens.get("loan_purpose", "home loan")
        lead_source = tokens.get("lead_source", "")

        source_context = ""
        if lead_source:
            source_context = f" The lead came in through {lead_source}."

        if variant == "warm":
            return CallScript(
                system_prompt=self._new_lead_warm_prompt(tokens),
                first_message=(
                    f"Hey {first_name}! This is Sam calling on behalf of {lo_name} "
                    f"at {company}. How are you doing today?"
                ),
                end_call_message=(
                    f"It was really great chatting with you, {first_name}! "
                    f"{lo_name} is going to love working with you. Have a wonderful day!"
                ),
                key_points=[
                    "Build rapport before discussing loan needs",
                    f"Mention {lo_name} by name to establish the personal connection",
                    "Ask about their timeline and what's driving the home search",
                    "Offer to schedule a no-obligation consultation",
                    "If they mention a specific property, show enthusiasm",
                ],
                objection_handling=self._standard_objections(tokens),
                metadata={"variant": "warm", "caller_type": "new_lead"},
            )

        elif variant == "direct":
            return CallScript(
                system_prompt=self._new_lead_direct_prompt(tokens),
                first_message=(
                    f"Hi {first_name}, this is Sam from {company}. "
                    f"I'm calling because we have some excellent {loan_purpose} "
                    f"options available right now, and {lo_name} wanted me to "
                    f"reach out before rates move. Do you have a quick minute?"
                ),
                end_call_message=(
                    f"Perfect, {first_name}. {lo_name} will have everything "
                    f"ready for your appointment. Thanks for your time!"
                ),
                key_points=[
                    "Lead with value proposition (rates, savings)",
                    "Be concise and respect their time",
                    "Move quickly toward scheduling",
                    "Mention current market conditions as urgency driver",
                ],
                objection_handling=self._standard_objections(tokens),
                metadata={"variant": "direct", "caller_type": "new_lead"},
            )

        # Default variant
        return CallScript(
            system_prompt=self._new_lead_default_prompt(tokens),
            first_message=(
                f"Hi {first_name}, this is Sam calling on behalf of {lo_name} "
                f"at {company}. {lo_name} asked me to reach out because you "
                f"recently expressed interest in a {loan_purpose}. "
                f"Is this a good time to chat for just a couple minutes?"
            ),
            end_call_message=(
                f"Thank you so much, {first_name}. {lo_name} is looking forward "
                f"to connecting with you. Have a great rest of your day!"
            ),
            key_points=[
                "Confirm their interest and timeline",
                "Understand what type of property they're looking at",
                "Ask about pre-approval status",
                "Schedule a consultation with the loan officer",
                "Collect any initial questions they have",
            ],
            objection_handling=self._standard_objections(tokens),
            metadata={"variant": "default", "caller_type": "new_lead"},
        )

    def _new_lead_default_prompt(self, tokens: Dict[str, str]) -> str:
        return f"""You are Sam, a friendly and professional AI assistant calling on behalf of \
{tokens['lo_name']} at {tokens['company']}.

YOUR GOAL: Schedule a consultation appointment between {tokens['first_name']} and {tokens['lo_name']}.

ABOUT THE CONTACT:
- Name: {tokens['first_name']} {tokens.get('last_name', '')}
- They expressed interest in a {tokens.get('loan_purpose', 'home loan')}
{f"- Lead source: {tokens['lead_source']}" if tokens.get('lead_source') else ''}
{f"- Estimated loan amount: {tokens['loan_amount']}" if tokens.get('loan_amount') else ''}
{f"- Credit score range: {tokens['credit_score']}" if tokens.get('credit_score') else ''}

CONVERSATION FLOW:
1. Introduce yourself and confirm you're speaking with {tokens['first_name']}
2. Briefly explain why you're calling (on behalf of {tokens['lo_name']})
3. Ask about their timeline and home buying goals
4. Explain the value of a consultation (personalized options, rate analysis, pre-approval)
5. Offer specific appointment times: "Would morning or afternoon work better?"
6. Confirm the appointment details

IMPORTANT RULES:
- Be warm, professional, and conversational -- not robotic
- Do NOT quote specific rates or provide financial advice
- If they ask about rates, say "{tokens['lo_name']} can provide personalized rate quotes during your consultation"
- If they're not interested, thank them graciously and ask if they'd like to be contacted in the future
- If it goes to voicemail, leave a brief message: "Hi {tokens['first_name']}, this is Sam calling on behalf of {tokens['lo_name']} at {tokens['company']} regarding your home loan inquiry. Please call us back at your convenience."
- Respect if they say they're busy -- offer to call back at a better time
- Never pressure or use high-pressure sales tactics
- Keep the call under 3 minutes unless the contact wants to talk longer"""

    def _new_lead_warm_prompt(self, tokens: Dict[str, str]) -> str:
        return f"""You are Sam, a warm and personable AI assistant calling on behalf of \
{tokens['lo_name']} at {tokens['company']}.

YOUR GOAL: Build rapport and schedule a consultation with {tokens['lo_name']}.

ABOUT THE CONTACT:
- Name: {tokens['first_name']}
{f"- Looking for a {tokens.get('loan_purpose', 'home loan')}" if tokens.get('loan_purpose') else ''}

APPROACH:
- Start with a genuine, warm greeting
- Ask how they're doing and actually listen
- Transition naturally to why you're calling
- Focus on understanding their situation and goals
- Make scheduling feel like a natural next step, not a sales push
- Use phrases like "I'd love to connect you with {tokens['lo_name']}" rather than "schedule an appointment"

RULES:
- Be genuinely friendly and conversational
- Do NOT quote rates or give financial advice
- Keep it natural and unhurried
- If they seem hesitant, don't push -- offer alternatives (email info, call back later)
- If voicemail, leave a warm message with callback info"""

    def _new_lead_direct_prompt(self, tokens: Dict[str, str]) -> str:
        return f"""You are Sam, a professional and efficient AI assistant calling on behalf of \
{tokens['lo_name']} at {tokens['company']}.

YOUR GOAL: Quickly communicate value and schedule a consultation.

ABOUT THE CONTACT:
- Name: {tokens['first_name']}
{f"- Interest: {tokens.get('loan_purpose', 'home loan')}" if tokens.get('loan_purpose') else ''}

APPROACH:
- Be concise and respectful of their time
- Lead with what's in it for them (competitive rates, fast pre-approval, personalized service)
- Get to the scheduling ask within the first minute
- Offer two specific time options

RULES:
- Professional and efficient, not pushy
- Do NOT quote specific rates
- If they say no, accept gracefully
- Maximum 2-minute call unless they engage further"""

    # =========================================================================
    # ACTIVE CLIENT SCRIPTS
    # =========================================================================

    def _build_active_client_script(self, tokens: Dict[str, str], variant: str) -> CallScript:
        """Build script for active client (in-pipeline borrower) outreach."""
        first_name = tokens["first_name"]
        lo_name = tokens["lo_name"]
        loan_stage = tokens.get("loan_stage", "processing")
        property_address = tokens.get("property_address", "your property")

        if variant == "milestone":
            return CallScript(
                system_prompt=self._active_client_milestone_prompt(tokens),
                first_message=(
                    f"Hi {first_name}! This is Sam calling on behalf of {lo_name}. "
                    f"Great news -- your loan is progressing well and I wanted to give "
                    f"you a quick update. Do you have a minute?"
                ),
                end_call_message=(
                    f"You're doing great, {first_name}! {lo_name} is on top of everything. "
                    f"We'll talk again soon!"
                ),
                key_points=[
                    f"Congratulate on reaching {loan_stage} stage",
                    "Explain what happens next in the process",
                    "Check if they have any questions or concerns",
                    "Confirm any upcoming appointments or deadlines",
                ],
                objection_handling={
                    "taking too long": f"I understand the wait can be frustrating. {lo_name} is actively pushing things forward and will keep you posted on every step.",
                    "worried about rate": f"{lo_name} is monitoring rates closely for you. They can discuss lock options during your next check-in.",
                },
                metadata={"variant": "milestone", "caller_type": "active_client"},
            )

        elif variant == "proactive":
            return CallScript(
                system_prompt=self._active_client_proactive_prompt(tokens),
                first_message=(
                    f"Hi {first_name}, this is Sam from {tokens['company']}. "
                    f"{lo_name} wanted me to check in with you about your loan. "
                    f"Everything is on track, and I wanted to see if you have "
                    f"any questions before the next step. Got a minute?"
                ),
                end_call_message=(
                    f"Thanks for your time, {first_name}. {lo_name} will follow up "
                    f"with you shortly. Don't hesitate to reach out if anything comes up!"
                ),
                key_points=[
                    "Proactively address common concerns for current stage",
                    "Remind about any pending document requests",
                    "Schedule a progress review if needed",
                ],
                objection_handling={},
                metadata={"variant": "proactive", "caller_type": "active_client"},
            )

        # Default variant
        return CallScript(
            system_prompt=self._active_client_default_prompt(tokens),
            first_message=(
                f"Hi {first_name}, this is Sam calling on behalf of {lo_name} "
                f"at {tokens['company']}. I'm calling with a quick update on "
                f"your loan. Is this a good time?"
            ),
            end_call_message=(
                f"Thanks {first_name}! {lo_name} will be in touch with any updates. "
                f"Have a great day!"
            ),
            key_points=[
                f"Provide status update: loan is in {loan_stage} stage",
                "Ask if they have any questions or concerns",
                "Check if any documents are still needed",
                "Offer to schedule a call with the LO for detailed discussion",
                "Remind about upcoming deadlines if any",
            ],
            objection_handling={
                "too many calls": "I completely understand. We just want to make sure you're informed and comfortable. Would you prefer email updates instead?",
                "when will it close": f"Great question! {lo_name} can give you the most accurate timeline. Shall I have them call you with an update?",
            },
            metadata={"variant": "default", "caller_type": "active_client"},
        )

    def _active_client_default_prompt(self, tokens: Dict[str, str]) -> str:
        loan_stage = tokens.get("loan_stage", "processing")
        stage_context = self._get_stage_context(loan_stage)

        return f"""You are Sam, a professional AI assistant calling on behalf of \
{tokens['lo_name']} at {tokens['company']}.

YOUR GOAL: Provide a loan progress update and schedule a review appointment if needed.

ABOUT THE BORROWER:
- Name: {tokens['first_name']}
- Current loan stage: {loan_stage}
{f"- Property: {tokens['property_address']}" if tokens.get('property_address') else ''}
{f"- Loan amount: {tokens['loan_amount']}" if tokens.get('loan_amount') else ''}
{f"- Loan number: {tokens['loan_number']}" if tokens.get('loan_number') else ''}

STAGE CONTEXT:
{stage_context}

CONVERSATION FLOW:
1. Greet and confirm identity
2. Provide brief status update for their loan stage
3. Ask if they have questions or concerns
4. If they need anything, offer to schedule a call with {tokens['lo_name']}
5. Remind about any pending items

RULES:
- Be reassuring and positive about the loan progress
- Do NOT provide specific rate or financial details over the phone
- If they have complex questions, schedule a call with {tokens['lo_name']}
- Keep it brief (2-3 minutes) unless they have questions
- If they seem stressed, acknowledge it and reassure them"""

    def _active_client_milestone_prompt(self, tokens: Dict[str, str]) -> str:
        return f"""You are Sam, a friendly AI assistant celebrating loan progress with {tokens['first_name']}.

YOUR GOAL: Share positive progress update and ensure they're comfortable with next steps.

APPROACH:
- Lead with positive news about their loan progress
- Make them feel good about the process
- Explain what's next in simple terms
- Offer to schedule a detailed review if they want one

ABOUT THE BORROWER:
- Name: {tokens['first_name']}
- Stage: {tokens.get('loan_stage', 'processing')}
- LO: {tokens['lo_name']}

RULES:
- Keep it positive and encouraging
- Don't get into financial specifics
- Schedule a review with {tokens['lo_name']} if they have detailed questions"""

    def _active_client_proactive_prompt(self, tokens: Dict[str, str]) -> str:
        return f"""You are Sam, a proactive AI assistant reaching out to {tokens['first_name']} \
about their loan with {tokens['lo_name']}.

YOUR GOAL: Proactively address common concerns and ensure nothing is blocking progress.

CHECK FOR:
- Outstanding document requests
- Questions about the current stage
- Any changes in their financial situation that might affect the loan
- Upcoming deadlines they should know about

APPROACH:
- Be helpful and proactive
- Ask if there's anything they need
- If they mention any issues, note them and schedule a call with {tokens['lo_name']}

RULES:
- Don't provide financial advice
- If they report changes (job, income, credit), flag it and connect with {tokens['lo_name']}
- Keep it under 3 minutes"""

    # =========================================================================
    # MUM (MORTGAGE UNDER MANAGEMENT) SCRIPTS
    # =========================================================================

    def _build_mum_script(self, tokens: Dict[str, str], variant: str) -> CallScript:
        """Build script for MUM (past client) outreach."""
        first_name = tokens["first_name"]
        lo_name = tokens["lo_name"]

        if variant == "refi":
            return CallScript(
                system_prompt=self._mum_refi_prompt(tokens),
                first_message=(
                    f"Hi {first_name}! This is Sam calling on behalf of {lo_name} "
                    f"at {tokens['company']}. {lo_name} has been monitoring rates for you "
                    f"and wanted me to reach out because there may be an opportunity "
                    f"to lower your monthly payment. Do you have a couple minutes?"
                ),
                end_call_message=(
                    f"Great talking with you, {first_name}! {lo_name} will put together "
                    f"a personalized analysis for you. Talk soon!"
                ),
                key_points=[
                    "Mention that their LO has been monitoring rates on their behalf",
                    "Highlight potential savings without quoting specific numbers",
                    "Offer a free refinance analysis appointment",
                    "Ask about any home improvements or equity needs",
                ],
                objection_handling={
                    "just refinanced": "That's great! We just want to make sure you're always getting the best deal. We'll keep monitoring for you.",
                    "rates aren't low enough": f"I understand. {lo_name} can show you the full picture including closing costs and break-even timeline. Sometimes the savings are bigger than expected.",
                    "not interested in refinancing": "No problem at all! We also do annual mortgage check-ups to make sure everything is still working well for you. Would that be helpful?",
                },
                metadata={"variant": "refi", "caller_type": "mum"},
            )

        elif variant == "referral":
            return CallScript(
                system_prompt=self._mum_referral_prompt(tokens),
                first_message=(
                    f"Hi {first_name}! This is Sam calling on behalf of {lo_name} "
                    f"at {tokens['company']}. {lo_name} just wanted to check in "
                    f"and see how you and the house are doing! Got a minute?"
                ),
                end_call_message=(
                    f"It was wonderful catching up, {first_name}! {lo_name} really "
                    f"appreciates your trust. Have a fantastic day!"
                ),
                key_points=[
                    "Start with genuine interest in how they're enjoying their home",
                    "Ask about any home projects or changes",
                    "Transition naturally to: 'Do you know anyone who might be looking to buy?'",
                    "Offer a small incentive for referrals if the program exists",
                    "Schedule an annual review if they're interested",
                ],
                objection_handling={
                    "don't know anyone": "No worries at all! If anyone ever mentions buying or refinancing, we'd love to take great care of them just like we did for you.",
                },
                metadata={"variant": "referral", "caller_type": "mum"},
            )

        # Default variant (annual review)
        return CallScript(
            system_prompt=self._mum_default_prompt(tokens),
            first_message=(
                f"Hi {first_name}! This is Sam calling on behalf of {lo_name} "
                f"at {tokens['company']}. It's been a while since we connected, "
                f"and {lo_name} wanted to check in on how things are going with "
                f"your home. Do you have a quick moment?"
            ),
            end_call_message=(
                f"Thanks for chatting, {first_name}! {lo_name} is always here "
                f"if you need anything. Enjoy your home!"
            ),
            key_points=[
                "Ask how they're enjoying their home",
                "Mention annual mortgage review service",
                "Ask about any financial goals (renovations, investment property, etc.)",
                "Gently ask if they know anyone looking to buy or refinance",
                "Offer to schedule an annual review appointment",
            ],
            objection_handling={
                "everything is fine": "That's great to hear! We just like to check in once a year to make sure your mortgage is still the best fit. Things change in the market!",
                "too busy": "Totally understand! Would a quick 15-minute phone call work better? We can do it whenever is convenient for you.",
            },
            metadata={"variant": "default", "caller_type": "mum"},
        )

    def _mum_default_prompt(self, tokens: Dict[str, str]) -> str:
        return f"""You are Sam, a friendly AI assistant doing an annual check-in on behalf of \
{tokens['lo_name']} at {tokens['company']}.

YOUR GOAL: Reconnect with a past client, schedule an annual mortgage review, and gently ask for referrals.

ABOUT THE CLIENT:
- Name: {tokens['first_name']}
- Past client of {tokens['lo_name']}
{f"- Original loan amount: {tokens['loan_amount']}" if tokens.get('loan_amount') else ''}
{f"- Original rate: {tokens['rate']}" if tokens.get('rate') else ''}
{f"- Days since last contact: {tokens['days_since_last_contact']}" if tokens.get('days_since_last_contact') else ''}

CONVERSATION FLOW:
1. Warm greeting -- ask how they and the house are doing
2. Listen genuinely to their response
3. Mention the annual mortgage review: "We like to do a quick annual check-up to make sure your mortgage is still the best deal"
4. Ask about any financial goals or home projects
5. If appropriate, ask: "Do you know anyone who might be looking to buy or refinance?"
6. Offer to schedule a 15-minute review call with {tokens['lo_name']}

RULES:
- Be warm, genuine, and not salesy
- This is a relationship maintenance call, not a sales call
- Don't push if they're not interested
- If they mention financial changes, note them for {tokens['lo_name']}
- Keep it conversational (3-5 minutes)
- Always thank them for being a valued client"""

    def _mum_refi_prompt(self, tokens: Dict[str, str]) -> str:
        return f"""You are Sam, an AI assistant reaching out about a potential refinance opportunity \
on behalf of {tokens['lo_name']} at {tokens['company']}.

YOUR GOAL: Discuss potential refinance savings and schedule a detailed analysis appointment.

ABOUT THE CLIENT:
- Name: {tokens['first_name']}
{f"- Current rate: {tokens['rate']}" if tokens.get('rate') else ''}
{f"- Loan amount: {tokens['loan_amount']}" if tokens.get('loan_amount') else ''}

APPROACH:
- Mention that {tokens['lo_name']} has been monitoring rates on their behalf
- Explain there may be savings available (DO NOT quote specific numbers or rates)
- Offer a free, no-obligation refinance analysis
- Schedule an appointment for {tokens['lo_name']} to present the analysis

RULES:
- Never quote specific rates or savings amounts
- Say things like "there may be an opportunity" rather than making promises
- If they have their current rate details, note them
- Be excited but not pushy about the opportunity
- If they say no, respect it and offer to keep monitoring"""

    def _mum_referral_prompt(self, tokens: Dict[str, str]) -> str:
        return f"""You are Sam, a friendly AI assistant doing a client appreciation check-in \
on behalf of {tokens['lo_name']} at {tokens['company']}.

YOUR GOAL: Reconnect with a valued past client and ask for referrals.

ABOUT THE CLIENT:
- Name: {tokens['first_name']}
- Past client of {tokens['lo_name']}

CONVERSATION FLOW:
1. Warm, genuine greeting
2. Ask about the home and how they're enjoying it
3. Share that {tokens['lo_name']} values their relationship
4. Natural transition: "By the way, do you know anyone who's thinking about buying a home or refinancing?"
5. If yes: "That's great! I'll have {tokens['lo_name']} reach out to them. What's the best way to connect?"
6. If no: "No worries at all! If anyone ever comes to mind, {tokens['lo_name']} would love to take great care of them."

RULES:
- This is a relationship call first, referral ask second
- Be genuinely interested in how they're doing
- Don't make it feel transactional
- Keep it light and conversational (2-4 minutes)"""

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _extract_tokens(self, contact: Any) -> Dict[str, str]:
        """Extract personalization tokens from a ContactInfo object."""
        name = getattr(contact, "name", "")
        parts = name.split() if name else []
        first_name = parts[0] if parts else "there"
        last_name = parts[-1] if len(parts) > 1 else ""

        lo_name = getattr(contact, "lo_name", None) or "your loan officer"
        company = "CMG Home Loans"  # Default; could be made configurable

        tokens = {
            "first_name": first_name,
            "last_name": last_name,
            "full_name": name or "there",
            "lo_name": lo_name,
            "company": company,
        }

        # Optional fields
        optional_fields = [
            "loan_stage", "loan_amount", "loan_type", "loan_number",
            "lead_source", "ai_score", "days_since_last_contact",
            "property_address", "rate", "credit_score",
        ]

        for field_name in optional_fields:
            value = getattr(contact, field_name, None)
            if value is not None:
                tokens[field_name] = str(value)

        # Format currency fields
        if tokens.get("loan_amount"):
            try:
                amt = float(tokens["loan_amount"])
                tokens["loan_amount"] = f"${amt:,.0f}"
            except (ValueError, TypeError):
                pass

        if tokens.get("rate"):
            try:
                rate = float(tokens["rate"])
                tokens["rate"] = f"{rate:.3f}%"
            except (ValueError, TypeError):
                pass

        # Infer loan purpose
        loan_purpose = getattr(contact, "loan_type", None)
        if loan_purpose:
            purpose_map = {
                "conventional": "conventional home loan",
                "fha": "FHA home loan",
                "va": "VA home loan",
                "usda": "USDA home loan",
                "jumbo": "jumbo home loan",
                "non_qm": "home loan",
            }
            tokens["loan_purpose"] = purpose_map.get(loan_purpose.lower(), "home loan")
        else:
            tokens["loan_purpose"] = "home loan"

        return tokens

    def _get_stage_context(self, stage: str) -> str:
        """Get human-readable context for a loan stage."""
        stage_contexts = {
            "APPLICATION": "The borrower has submitted their application. They're at the beginning of the process.",
            "DISCLOSED": "Initial disclosures have been sent. Waiting for signatures and document collection.",
            "PROCESSING": "The loan is being processed. Documents are being reviewed and verified.",
            "SUBMITTED": "The loan has been submitted to underwriting. Now we wait for the underwriter's review.",
            "UNDERWRITING": "The loan is actively being reviewed by the underwriter.",
            "UW_RECEIVED": "Underwriting has received the file and is reviewing it.",
            "CONDITIONAL_APPROVAL": "Great news -- the loan is conditionally approved! There may be a few remaining conditions to clear.",
            "APPROVED": "The loan is approved! Next step is getting clear to close.",
            "CTC": "Clear to close! The closing is being prepared.",
            "CLEAR_TO_CLOSE": "The loan is clear to close. Closing documents are being prepared.",
            "CLOSING": "The closing is being finalized. Almost there!",
            "DOCS": "Closing documents are being prepared.",
            "DOCS_OUT": "Closing documents have been sent out. Closing day is approaching!",
        }
        return stage_contexts.get(stage, f"The loan is currently in the {stage} stage.")

    def _standard_objections(self, tokens: Dict[str, str]) -> Dict[str, str]:
        """Standard objection handling responses."""
        lo_name = tokens["lo_name"]
        return {
            "not interested": f"I completely understand! If your situation changes, {lo_name} is always here to help. Can I at least send you some useful resources by email?",
            "already working with someone": f"That's great that you have someone helping you! If you ever want a second opinion or things don't work out, {lo_name} would love to chat.",
            "bad credit": f"That's actually something {lo_name} specializes in. There are programs for many credit situations. A quick consultation could give you a clear picture of your options.",
            "can't afford it": f"I hear you. {lo_name} has helped many people find options they didn't know existed. A quick chat might reveal some possibilities. Would you be open to that?",
            "just browsing": f"No pressure at all! {lo_name} loves helping people explore their options. Even if it's not the right time, a quick call could help you plan for when it is.",
            "call me back later": "Absolutely! When would be a better time to reach you? I'll make sure we follow up then.",
            "how did you get my number": f"You recently inquired about mortgage options, and {lo_name} wanted to personally follow up. Your privacy is very important to us.",
            "put me on do not call": "I'm so sorry to have bothered you. I'll make sure we remove your number right away. Have a great day.",
        }
