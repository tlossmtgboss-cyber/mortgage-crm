"""
Context Manager for Token-Optimized Prompt Loading

Reduces token usage from 90k to 12-18k by intelligently loading
only the prompt components needed for the current conversation context.

Key Strategies:
1. Core prompt always loaded (~2k tokens)
2. Stage-specific prompts loaded on-demand (~3-5k tokens)
3. User context limited to last 3 interactions (~2-3k tokens)
4. FAQs loaded only when user asks questions (~3k tokens)
5. Objection handling loaded only when objection detected (~2-3k tokens)

Dynamic Company Name Integration:
- Supports white-label functionality via {{company_name}} variables
- Injects organization branding into prompts dynamically
- Supports custom agent personas per organization
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
import json
import logging
import re

logger = logging.getLogger(__name__)


# Default organization for fallback
DEFAULT_ORGANIZATION = {
    "id": None,
    "name": "The Tim Loss Team",
    "brand_name": "The Tim Loss Team",
    "display_name": "The Tim Loss Team",
    "website": None,
    "phone": None,
    "agent_personas": {},
    "custom_prompts": {},
}


class ContextManager:
    """
    Intelligently loads prompt components based on conversation context.
    Target: 12-18k tokens (down from 90k)
    """

    # Conversation stage definitions
    STAGES = {
        "initial_contact": {
            "objective": "Get them to respond and show interest",
            "max_messages": 3,
            "next_stages": ["qualification", "objection_handling", "dormant"]
        },
        "qualification": {
            "objective": "Gather required information to assess fit",
            "max_messages": 7,
            "next_stages": ["booking", "objection_handling", "disqualified"]
        },
        "objection_handling": {
            "objective": "Address concerns and move forward",
            "max_messages": 5,
            "next_stages": ["qualification", "booking", "rejected"]
        },
        "booking": {
            "objective": "Schedule appointment or next step",
            "max_messages": 3,
            "next_stages": ["confirmed", "objection_handling"]
        },
        "follow_up": {
            "objective": "Re-engage dormant leads",
            "max_messages": 5,
            "next_stages": ["qualification", "rejected"]
        },
        "email_analysis": {
            "objective": "Extract intelligence from email",
            "max_messages": 1,
            "next_stages": ["complete"]
        },
        "document_collection": {
            "objective": "Collect required documents",
            "max_messages": 10,
            "next_stages": ["complete", "escalation"]
        }
    }

    # Indicators for detecting conversation context
    QUESTION_INDICATORS = ['?', 'what', 'how', 'when', 'why', 'who', 'where', 'which', 'can you', 'do you']
    OBJECTION_INDICATORS = [
        'not interested',
        'too expensive',
        'think about it',
        'call me later',
        'already have',
        "can't afford",
        'not now',
        'maybe later',
        'busy',
        "don't need",
        'no thanks',
        'unsubscribe',
        'stop'
    ]
    POSITIVE_INDICATORS = [
        'yes', 'sure', 'okay', 'sounds good', 'interested',
        "let's do it", 'tell me more', 'how do i', 'sign me up'
    ]

    def __init__(self, prompts_dir: Path):
        """
        Initialize the context manager.

        Args:
            prompts_dir: Path to the perennia-prompts directory
        """
        self.prompts_dir = Path(prompts_dir)
        self.manifest = self._load_manifest()
        self._cache: Dict[str, str] = {}

    def _load_manifest(self) -> Dict:
        """Load the prompt manifest"""
        manifest_path = self.prompts_dir / "manifest.json"
        try:
            with open(manifest_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Manifest not found at {manifest_path}")
            return {"sections": []}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid manifest JSON: {e}")
            return {"sections": []}

    async def get_optimized_prompt(
        self,
        agent_id: str,
        conversation_stage: str,
        conversation_history: List[Dict[str, str]],
        user_profile: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        organization: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build context-aware prompt with only necessary components.
        Target: 12-18k tokens (down from 90k)

        Args:
            agent_id: Identifier for the agent (e.g., "lead_agent", "email_intel")
            conversation_stage: Current stage (e.g., "initial_contact", "qualification")
            conversation_history: List of messages [{role: "user"|"assistant", content: "..."}]
            user_profile: User/lead information
            metadata: Additional context (dates, IDs, etc.)
            organization: Organization info for white-label branding

        Returns:
            Optimized prompt string with company name injected
        """
        # Use default organization if not provided
        org = organization or DEFAULT_ORGANIZATION

        components = []

        # 1. Core prompt (ALWAYS loaded) - ~2k tokens
        core = await self._load_core_prompt(agent_id)
        components.append(core)

        # 2. Stage-specific prompt - ~3-5k tokens
        stage_prompt = await self._load_stage_prompt(agent_id, conversation_stage)
        if stage_prompt:
            components.append(stage_prompt)

        # 3. User context (last 3 interactions only) - ~2-3k tokens
        recent_history = conversation_history[-3:] if conversation_history else []
        user_context = self._build_user_context(user_profile, recent_history)
        components.append(user_context)

        # 4. Conditional: FAQs (only if user is asking questions) - ~3k tokens
        if self._is_asking_questions(conversation_history):
            faqs = await self._load_relevant_faqs(
                agent_id,
                conversation_history[-1]['content'] if conversation_history else ""
            )
            if faqs:
                components.append(faqs)

        # 5. Conditional: Objections (only if user is objecting) - ~2-3k tokens
        if self._is_objecting(conversation_history):
            objections = await self._load_objection_handling(agent_id)
            if objections:
                components.append(objections)

        # 6. Context variables
        context_vars = self._build_context_variables(user_profile, metadata)
        components.append(context_vars)

        # Combine components
        prompt = "\n\n".join(filter(None, components))

        # 7. NEW: Inject company name and other variables
        prompt = self._inject_variables(prompt, agent_id, user_profile, org, metadata)

        # Log token estimate (rough: 1 token ~= 4 characters)
        estimated_tokens = len(prompt) // 4
        company_name = org.get('brand_name') or org.get('name') or 'Unknown'
        logger.info(f"Generated prompt for {agent_id}/{conversation_stage} [{company_name}]: ~{estimated_tokens} tokens")

        return prompt

    def _inject_variables(
        self,
        prompt: str,
        agent_id: str,
        user_profile: Dict[str, Any],
        organization: Dict[str, Any],
        metadata: Optional[Dict[str, Any]]
    ) -> str:
        """
        Replace template variables with actual values.

        Supports:
        - {{company_name}} → "ABC Mortgage Co"
        - {{company}} → "ABC Mortgage Co" (alias)
        - {{agent_name}} → "Sarah" (from org personas or default)
        - {{agent_role}} → "Mortgage Specialist"
        - {{first_name}} → "John"
        - {{current_date}} → "2024-03-15"
        - And more...

        Args:
            prompt: Template prompt with {{variable}} placeholders
            agent_id: Current agent identifier
            user_profile: User/lead data
            organization: Organization branding data
            metadata: Additional context

        Returns:
            Prompt with all variables replaced
        """
        # Get company name with fallback chain
        company_name = (
            organization.get('brand_name') or
            organization.get('display_name') or
            organization.get('name') or
            'The Tim Loss Team'
        )

        # Get custom agent persona for this organization (if set)
        agent_personas = organization.get('agent_personas', {})
        agent_persona = agent_personas.get(agent_id, {})

        # Default agent names by agent type
        default_agent_names = {
            'lead_agent': ('Sarah', 'Mortgage Specialist'),
            'email_intel': ('System', 'Email Classifier'),
            'document_agent': ('Alex', 'Document Specialist'),
            'rate_advisor': ('Jamie', 'Rate Lock Advisor'),
            'sla_agent': ('System', 'SLA Monitor'),
            'receptionist_agent': ('Taylor', 'Client Services'),
            'compliance_agent': ('System', 'Compliance Monitor'),
            'coaching_agent': ('Morgan', 'Performance Coach'),
        }

        default_name, default_role = default_agent_names.get(agent_id, ('Assistant', 'Specialist'))

        agent_name = agent_persona.get('name', default_name)
        agent_role = agent_persona.get('role', default_role)

        # Extract first name properly
        first_name = user_profile.get('first_name', user_profile.get('name', 'there'))
        if first_name and ' ' in str(first_name):
            first_name = first_name.split()[0]

        # Build variable map
        variables = {
            # Company branding
            'company_name': company_name,
            'company': company_name,
            'company_website': organization.get('website', ''),
            'company_phone': organization.get('phone', ''),

            # Agent persona
            'agent_name': agent_name,
            'agent_role': agent_role,

            # User info
            'first_name': first_name,
            'last_name': user_profile.get('last_name', ''),
            'full_name': f"{first_name} {user_profile.get('last_name', '')}".strip(),
            'email': user_profile.get('email', ''),
            'phone': user_profile.get('phone', ''),
            'loan_number': user_profile.get('loan_number', ''),

            # Date/time
            'current_date': datetime.now().strftime('%Y-%m-%d'),
            'current_time': datetime.now().strftime('%H:%M'),
            'current_datetime': datetime.now().isoformat(),
            'day_of_week': datetime.now().strftime('%A'),
        }

        # Add any metadata variables
        if metadata:
            for key, value in metadata.items():
                if key not in variables:  # Don't override core variables
                    variables[key] = value

        # Add user profile metadata
        user_metadata = user_profile.get('metadata', {})
        if isinstance(user_metadata, dict):
            for key, value in user_metadata.items():
                if key not in variables:
                    variables[key] = value

        # Replace all {{variable}} patterns
        def replace_var(match):
            var_name = match.group(1)
            value = variables.get(var_name)
            if value is not None:
                return str(value)
            # Keep original if variable not found (allows for optional vars)
            return match.group(0)

        prompt = re.sub(r'\{\{(\w+)\}\}', replace_var, prompt)

        return prompt

    async def _load_core_prompt(self, agent_id: str) -> str:
        """
        Load core prompt components that are ALWAYS needed:
        - Identity
        - Basic rules
        - Output style

        ~2k tokens
        """
        cache_key = f"core_{agent_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try agent-specific core first
        core_paths = [
            self.prompts_dir / "core" / f"{agent_id}_core.md",
            self.prompts_dir / "core" / f"{agent_id}_core.txt",
            self.prompts_dir / "raw" / f"{agent_id}_core.md",
        ]

        for path in core_paths:
            if path.exists():
                with open(path, 'r') as f:
                    content = f.read()
                    self._cache[cache_key] = content
                    return content

        # Fallback: Build from manifest core sections
        core_content = await self._build_core_from_manifest(agent_id)
        self._cache[cache_key] = core_content
        return core_content

    async def _build_core_from_manifest(self, agent_id: str) -> str:
        """Build core prompt from manifest sections"""
        core_sections = []

        # Load core identity and guidelines
        core_files = [
            "core/core_identity.md",
            "core/core_guidelines.md",
            "conditional/tone_and_style.md",
        ]

        for file_path in core_files:
            full_path = self.prompts_dir / file_path
            if full_path.exists():
                with open(full_path, 'r') as f:
                    core_sections.append(f.read())

        # Add essential rules (from "The Instant AI Agency")
        essential_rules = """
### Core Rules (ALWAYS FOLLOW):
- Only ask ONE question at a time to find out one piece of information
- Do NOT use conciliatory phrases ("I understand," "I hear you," "No worries") when user expresses disinterest
- Persistently engage - avoid phrases that acknowledge rejection
- Stay on topic and guide the conversation toward your objective
- Keep responses under 60 words unless answering complex questions
- Use their first name naturally in conversation
"""
        core_sections.append(essential_rules)

        return "\n\n".join(core_sections)

    async def _load_stage_prompt(
        self,
        agent_id: str,
        stage: str
    ) -> Optional[str]:
        """
        Load stage-specific prompt.
        Only loads the current stage, not all stages.

        ~3-5k tokens
        """
        cache_key = f"stage_{agent_id}_{stage}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try multiple paths
        stage_paths = [
            self.prompts_dir / "conditional" / agent_id / f"{stage}.md",
            self.prompts_dir / "conditional" / agent_id / f"{stage}.txt",
            self.prompts_dir / "conditional" / f"{agent_id}_{stage}.md",
            self.prompts_dir / "raw" / f"{agent_id}_{stage}.md",
        ]

        for path in stage_paths:
            if path.exists():
                with open(path, 'r') as f:
                    content = f.read()
                    self._cache[cache_key] = content
                    return content

        # Generate default stage prompt
        stage_info = self.STAGES.get(stage, {})
        if stage_info:
            default_prompt = f"""
### Current Stage: {stage.replace('_', ' ').title()}
### Objective: {stage_info.get('objective', 'Engage with the user')}

Focus on achieving this objective before moving to the next stage.
"""
            return default_prompt

        return None

    def _build_user_context(
        self,
        user_profile: Dict[str, Any],
        recent_history: List[Dict[str, str]]
    ) -> str:
        """
        Build minimal user context.
        Only includes recent history and essential profile data.

        ~2-3k tokens
        """
        # Extract key user fields
        first_name = user_profile.get('first_name', user_profile.get('name', 'there'))
        if ' ' in str(first_name):
            first_name = first_name.split()[0]

        context_parts = [
            "### User Context:",
            f"Name: {first_name}",
        ]

        # Add stage if available
        if 'current_stage' in user_profile:
            context_parts.append(f"Current Stage: {user_profile['current_stage']}")

        # Add key metadata fields if present
        key_fields = ['email', 'phone', 'loan_purpose', 'property_type', 'estimated_amount']
        for field in key_fields:
            if field in user_profile and user_profile[field]:
                context_parts.append(f"{field.replace('_', ' ').title()}: {user_profile[field]}")

        # Add conversation history
        if recent_history:
            context_parts.append("\n### Recent Conversation:")
            context_parts.append(self._format_conversation(recent_history))

        return "\n".join(context_parts)

    def _format_conversation(self, history: List[Dict[str, str]]) -> str:
        """Format conversation history"""
        formatted = []
        for msg in history:
            role = msg.get('role', 'user').capitalize()
            content = msg.get('content', '')
            # Truncate long messages
            if len(content) > 500:
                content = content[:500] + "..."
            formatted.append(f"{role}: {content}")
        return "\n".join(formatted)

    def _is_asking_questions(self, history: List[Dict[str, str]]) -> bool:
        """Detect if user is asking questions"""
        if not history:
            return False

        # Check last 2 messages
        for msg in history[-2:]:
            if msg.get('role') == 'user':
                content = msg.get('content', '').lower()
                if any(ind in content for ind in self.QUESTION_INDICATORS):
                    return True
        return False

    def _is_objecting(self, history: List[Dict[str, str]]) -> bool:
        """Detect if user is objecting"""
        if not history:
            return False

        last_user_msg = None
        for msg in reversed(history):
            if msg.get('role') == 'user':
                last_user_msg = msg.get('content', '').lower()
                break

        if not last_user_msg:
            return False

        return any(ind in last_user_msg for ind in self.OBJECTION_INDICATORS)

    def _is_positive(self, history: List[Dict[str, str]]) -> bool:
        """Detect if user is responding positively"""
        if not history:
            return False

        last_user_msg = None
        for msg in reversed(history):
            if msg.get('role') == 'user':
                last_user_msg = msg.get('content', '').lower()
                break

        if not last_user_msg:
            return False

        return any(ind in last_user_msg for ind in self.POSITIVE_INDICATORS)

    async def _load_relevant_faqs(
        self,
        agent_id: str,
        question: str
    ) -> Optional[str]:
        """
        Load only relevant FAQs.
        Uses keyword matching (can be upgraded to semantic search).

        ~3k tokens
        """
        faq_paths = [
            self.prompts_dir / "optional" / f"{agent_id}_faqs.json",
            self.prompts_dir / "conditional" / f"{agent_id}_faqs.json",
            self.prompts_dir / "raw" / f"{agent_id}_faqs.json",
        ]

        all_faqs = []
        for path in faq_paths:
            if path.exists():
                try:
                    with open(path, 'r') as f:
                        all_faqs = json.load(f)
                    break
                except json.JSONDecodeError:
                    continue

        if not all_faqs:
            return None

        # Simple keyword matching (upgrade to semantic search later)
        question_lower = question.lower()
        keywords = set(re.findall(r'\b\w{4,}\b', question_lower))

        scored_faqs = []
        for faq in all_faqs:
            faq_text = (faq.get('question', '') + ' ' + faq.get('keywords', '')).lower()
            score = sum(1 for kw in keywords if kw in faq_text)
            if score > 0:
                scored_faqs.append((score, faq))

        # Get top 3 relevant FAQs
        scored_faqs.sort(key=lambda x: x[0], reverse=True)
        relevant_faqs = [faq for _, faq in scored_faqs[:3]]

        if not relevant_faqs:
            # Return top 3 FAQs as fallback
            relevant_faqs = all_faqs[:3]

        return "### Relevant FAQs:\n" + "\n".join([
            f"Q: {faq.get('question', '')}\nA: {faq.get('answer', '')}\n"
            for faq in relevant_faqs
        ])

    async def _load_objection_handling(self, agent_id: str) -> Optional[str]:
        """
        Load objection handling strategies.

        ~2-3k tokens
        """
        cache_key = f"objections_{agent_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        obj_paths = [
            self.prompts_dir / "conditional" / f"{agent_id}_objections.md",
            self.prompts_dir / "conditional" / f"{agent_id}_objections.txt",
            self.prompts_dir / "raw" / f"{agent_id}_objections.md",
        ]

        for path in obj_paths:
            if path.exists():
                with open(path, 'r') as f:
                    content = f.read()
                    self._cache[cache_key] = content
                    return content

        # Return default objection handling
        default_objections = """
### Objection Handling (Use SPIN Selling & Challenger Sale):

If they say: "I'm just looking"
You say: "That's exactly the right time to compare options! Most people don't realize how much they vary. Would you like to see what you might qualify for? Zero obligation."

If they say: "I already have someone"
You say: "Smart to have options! A second opinion never hurts. Would you like to see if we can do better? Takes 15 minutes."

If they say: "I need to think about it"
You say: "Makes sense. What specific information would help you decide? I can probably answer it right now."

If they say: "Can't afford it" / "Too expensive"
You say: "I get that. Many people are surprised at the programs available. Would you like to see what you actually qualify for? Might be different than you think."

If they say: "Not interested"
You say: "What would need to change to make this worth 15 minutes of your time?"

If they say: "Call me later"
You say: "Happy to! When specifically works best for you? I'll put it on my calendar."

IMPORTANT: Never accept rejection on the first attempt. Use these strategies to re-engage.
"""
        self._cache[cache_key] = default_objections
        return default_objections

    def _build_context_variables(
        self,
        user_profile: Dict[str, Any],
        metadata: Optional[Dict[str, Any]]
    ) -> str:
        """Build context variables section"""
        variables = {
            "current_date": datetime.now().strftime('%Y-%m-%d'),
            "current_time": datetime.now().strftime('%H:%M'),
            "day_of_week": datetime.now().strftime('%A'),
        }

        # Add user profile variables
        for key in ['first_name', 'email', 'phone', 'loan_number', 'closing_date']:
            if key in user_profile and user_profile[key]:
                variables[key] = user_profile[key]

        # Add metadata variables
        if metadata:
            variables.update(metadata)

        return "### Context Variables:\n" + "\n".join([
            f"- {k}: {v}" for k, v in variables.items()
        ])

    def detect_stage_transition(
        self,
        current_stage: str,
        conversation_history: List[Dict[str, str]],
        qualification_data: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Detect if conversation should transition to a new stage.

        Returns new stage name or None if no transition.
        """
        stage_info = self.STAGES.get(current_stage, {})

        # Check for objection
        if self._is_objecting(conversation_history):
            next_stages: Any = stage_info.get('next_stages', [])
            if "objection_handling" in next_stages:
                return "objection_handling"

        # Check for positive response
        if self._is_positive(conversation_history):
            if current_stage == "initial_contact":
                return "qualification"
            elif current_stage == "objection_handling":
                return "qualification"
            elif current_stage == "qualification" and qualification_data:
                # Check if all required info gathered
                required_fields = ['loan_purpose', 'property_value', 'timeline']
                if all(qualification_data.get(f) for f in required_fields):
                    return "booking"

        # Check for max messages reached
        user_messages = sum(1 for msg in conversation_history if msg.get('role') == 'user')
        max_messages: Any = stage_info.get('max_messages', 10)

        if user_messages >= max_messages:
            if current_stage == "initial_contact":
                return "dormant"
            elif current_stage == "objection_handling":
                return "rejected"

        return None

    def clear_cache(self):
        """Clear the prompt cache"""
        self._cache.clear()
        logger.info("Context manager cache cleared")
