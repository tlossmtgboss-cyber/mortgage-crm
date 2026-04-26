"""
Agent Prompt Builder

Systematic prompt construction using principles from "The Instant AI Agency":
- Clear persona definition
- One question at a time rule
- No conciliatory phrases
- Persistent engagement
- SPIN Selling & Challenger Sale methodologies
"""

from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


class ConversationStyle(Enum):
    """Defines conversation styles for different contexts"""
    CASUAL = "casual message, conversational, US Idiom, American dialect"
    PROFESSIONAL = "professional, business-appropriate, clear and concise"
    CONSULTATIVE = "consultative, advisory, expert guidance"
    FRIENDLY = "warm, approachable, personable"
    URGENT = "urgent, data-driven, action-oriented"
    EFFICIENT = "efficient, precise, task-focused"


class SalesMethodology(Enum):
    """Sales training methodologies to embed in agents"""
    SPIN_SELLING = "SPIN Selling"
    CHALLENGER_SALE = "The Challenger Sale"
    CONSULTATIVE_SELLING = "Consultative Selling"
    SOLUTION_SELLING = "Solution Selling"


@dataclass
class AgentPersona:
    """Defines the agent's identity and role"""
    name: str
    role: str
    company: str = "The Tim Loss Team"
    expertise: List[str] = field(default_factory=list)
    personality_traits: List[str] = field(default_factory=lambda: ["professional", "helpful"])

    def to_prompt_section(self) -> str:
        """Convert persona to prompt text"""
        traits = ", ".join(self.personality_traits) if self.personality_traits else "helpful and efficient"
        expertise = ", ".join(self.expertise) if self.expertise else "mortgage services"

        return f"""### Your Identity:
You are {self.name}, a {self.role} at {self.company}.
Your expertise includes: {expertise}.
You are {traits}.
You are NOT an AI assistant - you are a real person doing your job.

If asked if you're AI, respond naturally:
"Ha! I wish - then I wouldn't need coffee. I'm {self.name}, I handle {self.role.lower()} for our team."
"""


@dataclass
class QualificationCriteria:
    """Defines what makes a qualified lead/request"""
    required_info: List[str] = field(default_factory=list)
    qualifying_questions: List[str] = field(default_factory=list)
    disqualifying_factors: List[str] = field(default_factory=list)

    def to_prompt_section(self) -> str:
        """Convert qualification criteria to prompt text"""
        sections = ["### Qualification Section:"]

        if self.required_info:
            sections.append("\nYou must gather the following information:")
            sections.extend([f"- {info}" for info in self.required_info])

        if self.qualifying_questions:
            sections.append("\nAsk these questions to qualify (ONE at a time):")
            sections.extend([f"{i+1}. {q}" for i, q in enumerate(self.qualifying_questions)])

        if self.disqualifying_factors:
            sections.append("\nDisqualifying factors:")
            sections.extend([f"- {factor}" for factor in self.disqualifying_factors])
        else:
            sections.append("\nDisqualifying factors: None specified")

        return "\n".join(sections)


@dataclass
class ConversationRules:
    """Core rules for conversation management"""
    max_questions_per_message: int = 1
    max_response_words: int = 60
    avoid_conciliatory_phrases: bool = True
    stay_on_topic: bool = True
    persistent_engagement: bool = True
    acknowledge_rejection: bool = False

    def to_prompt_section(self) -> str:
        """Convert rules to prompt text"""
        rules = [
            f"Only ask {self.max_questions_per_message} question at a time to find out one piece of information.",
            f"Keep responses under {self.max_response_words} words unless answering complex questions.",
        ]

        if self.avoid_conciliatory_phrases:
            rules.append('Do NOT use conciliatory phrases ("I understand," "I hear you," "No worries," "That\'s okay") when the user expresses disinterest.')

        if self.persistent_engagement:
            rules.append("Persistently engage with the user, avoiding any phrases that acknowledge rejection.")

        if self.stay_on_topic:
            rules.append("Always stay on topic and guide the conversation toward your objective.")

        rules.extend([
            "Use their first name naturally in conversation.",
            "Never end a conversation without a clear next step or call-to-action.",
        ])

        return "### Rules (ALWAYS FOLLOW):\n" + "\n".join([f"- {rule}" for rule in rules])


@dataclass
class ObjectionHandling:
    """Framework for handling objections"""
    common_objections: Dict[str, str] = field(default_factory=dict)
    default_strategy: str = "Ask what would need to change to make this worth their time"

    def to_prompt_section(self) -> str:
        """Convert objection handling to prompt text"""
        sections = [
            "### Objection Handling:",
            "Use SPIN Selling & Challenger Sale methodologies to navigate objections.",
            ""
        ]

        for objection, strategy in self.common_objections.items():
            sections.append(f'If they say: "{objection}"')
            sections.append(f'You say: "{strategy}"')
            sections.append("")

        sections.append(f"Default strategy: {self.default_strategy}")
        sections.append("\nIMPORTANT: Never accept rejection on the first attempt. Always try at least one re-engagement strategy.")

        return "\n".join(sections)


@dataclass
class FAQConfig:
    """FAQ configuration"""
    faqs: Dict[str, str] = field(default_factory=dict)
    out_of_scope_response: str = "That's a great question for our specialist. Would you like to schedule a quick call?"

    def to_prompt_section(self) -> str:
        """Convert FAQs to prompt text"""
        if not self.faqs:
            return ""

        sections = ["### FAQ:"]
        for question, answer in self.faqs.items():
            sections.append(f"\nQ: {question}")
            sections.append(f"A: {answer}")

        sections.append(f"\n### Out of Scope Questions:\n{self.out_of_scope_response}")

        return "\n".join(sections)


class AgentPromptBuilder:
    """
    Enhanced prompt builder using principles from "The Instant AI Agency"

    Usage:
        builder = AgentPromptBuilder()
        prompt = builder \
            .set_objective("qualify mortgage leads over SMS") \
            .set_conversation_style(ConversationStyle.PROFESSIONAL) \
            .set_training([SalesMethodology.SPIN_SELLING], "Mortgage Lending") \
            .set_persona(persona) \
            .set_qualification(qualification) \
            .set_rules(rules) \
            .build()
    """

    def __init__(self):
        self.components: Dict[str, str] = {}

    def set_objective(self, objective: str) -> 'AgentPromptBuilder':
        """Define what the agent needs to accomplish"""
        self.components['objective'] = f"Your job is to {objective}."
        return self

    def set_conversation_style(self, style: ConversationStyle) -> 'AgentPromptBuilder':
        """Set the conversation style"""
        self.components['style'] = f"### Your Output Style:\n{style.value}"
        return self

    def set_training(
        self,
        methodologies: List[SalesMethodology],
        domain: str
    ) -> 'AgentPromptBuilder':
        """Set sales training and domain expertise"""
        methods = ", ".join([m.value for m in methodologies])
        self.components['training'] = f"### Your Training:\n{methods}, {domain}"
        return self

    def set_persona(self, persona: AgentPersona) -> 'AgentPromptBuilder':
        """Set the agent's persona"""
        self.components['persona'] = persona.to_prompt_section()
        return self

    def set_first_message(self, message: str) -> 'AgentPromptBuilder':
        """Set the opening message template"""
        self.components['first_message'] = f"""### FIRST Message:
"{message}"

Note: This is the message they're responding to. Omit introductions and continue the conversation naturally."""
        return self

    def set_qualification(self, criteria: QualificationCriteria) -> 'AgentPromptBuilder':
        """Set qualification criteria"""
        self.components['qualification'] = criteria.to_prompt_section()
        return self

    def set_rules(self, rules: ConversationRules) -> 'AgentPromptBuilder':
        """Set conversation rules"""
        self.components['rules'] = rules.to_prompt_section()
        return self

    def set_objection_handling(self, handling: ObjectionHandling) -> 'AgentPromptBuilder':
        """Set objection handling strategies"""
        self.components['objections'] = handling.to_prompt_section()
        return self

    def set_faqs(self, faqs: FAQConfig) -> 'AgentPromptBuilder':
        """Set FAQ configuration"""
        faq_section = faqs.to_prompt_section()
        if faq_section:
            self.components['faqs'] = faq_section
        return self

    def add_context_notes(self, notes: Dict[str, str]) -> 'AgentPromptBuilder':
        """Add contextual notes"""
        section = "### Notes:\n"
        for key, value in notes.items():
            section += f"- {key}: {value}\n"
        self.components['notes'] = section
        return self

    def add_success_criteria(self, criteria: str) -> 'AgentPromptBuilder':
        """Define what success looks like"""
        self.components['success'] = f"### Success Criteria:\n{criteria}"
        return self

    def add_output_format(self, format_spec: str) -> 'AgentPromptBuilder':
        """Specify output format (e.g., JSON)"""
        self.components['output_format'] = f"### Output Format:\n{format_spec}"
        return self

    def add_custom_section(self, name: str, content: str) -> 'AgentPromptBuilder':
        """Add a custom section"""
        self.components[name] = content
        return self

    def build(self) -> str:
        """Build the complete prompt"""
        # Order matters for optimal results
        ordered_sections = [
            'objective',
            'style',
            'training',
            'persona',
            'first_message',
            'qualification',
            'objections',
            'rules',
            'output_format',
            'faqs',
            'notes',
            'success'
        ]

        prompt_parts = []
        for section in ordered_sections:
            if section in self.components:
                prompt_parts.append(self.components[section])

        # Add any custom sections at the end
        for key, value in self.components.items():
            if key not in ordered_sections:
                prompt_parts.append(value)

        return "\n\n".join(prompt_parts)

    def estimate_tokens(self) -> int:
        """Estimate token count (rough: 1 token ~= 4 characters)"""
        prompt = self.build()
        return len(prompt) // 4


# =============================================================================
# PRE-BUILT AGENT TEMPLATES
# =============================================================================

def create_lead_qualification_agent(
    agent_name: str = "Sarah",
    company: str = "The Tim Loss Team"
) -> str:
    """Create a lead qualification agent prompt"""
    persona = AgentPersona(
        name=agent_name,
        role="Mortgage Specialist",
        company=company,
        expertise=["Mortgage products", "Rate comparisons", "Qualification requirements"],
        personality_traits=["professional", "knowledgeable", "helpful"]
    )

    qualification = QualificationCriteria(
        required_info=[
            "Purchase or refinance intent",
            "Estimated property value",
            "Target closing date",
            "Pre-approval status"
        ],
        qualifying_questions=[
            "Are you looking to purchase or refinance?",
            "What's your estimated property value?",
            "Do you have a target closing date?",
            "Have you been pre-approved yet?"
        ],
        disqualifying_factors=[
            "No income source",
            "Active bankruptcy",
            "Timeline beyond 12 months"
        ]
    )

    rules = ConversationRules(
        max_questions_per_message=1,
        max_response_words=60,
        avoid_conciliatory_phrases=True,
        persistent_engagement=True
    )

    objections = ObjectionHandling(
        common_objections={
            "I'm just looking": "That's perfect timing! Most people who are just looking don't realize how much rates vary. Would you like to see what you might qualify for?",
            "I already have a lender": "Smart to have options! Would you like to see if we can beat their rate? No obligation.",
            "I need to think about it": "Absolutely. What specific information would help you make the best choice?",
            "Can't afford it right now": "Many people are surprised at the programs available. Would you like to see what you might actually qualify for?"
        }
    )

    builder = AgentPromptBuilder()
    return builder \
        .set_objective("qualify mortgage leads over SMS and email and book them into loan officer calls") \
        .set_conversation_style(ConversationStyle.PROFESSIONAL) \
        .set_training([SalesMethodology.SPIN_SELLING, SalesMethodology.CHALLENGER_SALE], "Mortgage Lending") \
        .set_persona(persona) \
        .set_first_message(
            f"Hi {{{{first_name}}}}! It's {agent_name} from {company}. "
            "I see you were looking into mortgage options recently. Are you still exploring rates?"
        ) \
        .set_qualification(qualification) \
        .set_rules(rules) \
        .set_objection_handling(objections) \
        .add_success_criteria(
            "A qualified lead who books a call with our specialist and is ready to move forward within 90 days."
        ) \
        .build()


def create_email_intelligence_agent() -> str:
    """Create an email intelligence agent prompt"""
    builder = AgentPromptBuilder()
    return builder \
        .set_objective("analyze incoming mortgage emails and extract actionable intelligence") \
        .set_conversation_style(ConversationStyle.EFFICIENT) \
        .set_training([], "Email Classification, Information Extraction, Mortgage Operations") \
        .add_custom_section('identity', """### Your Identity:
You are the automated email classification system for The Tim Loss Team's operations team.
You process emails quickly and accurately, extracting key information for routing.""") \
        .add_custom_section('extraction', """### Extract These Fields:
- loan_number (format: LOAN-######, if present)
- borrower_name
- urgency (Low/Medium/High/Critical)
- category (see below)
- action_items (list)
- deadline (YYYY-MM-DD if mentioned)
- routing_team

### Categories (Choose ONE):
1. rate_lock - Rate lock request (High urgency)
2. document_upload - Document submission
3. status_inquiry - "Where's my loan?" questions
4. new_application - Fresh application
5. problem_escalation - Issues, complaints, errors
6. general_question - Everything else

### Urgency Rules:
- Critical: Rate lock expires today, closing in jeopardy, compliance issue
- High: Rate lock within 48hrs, missing critical doc, borrower frustrated
- Medium: Standard questions, routine updates
- Low: General inquiries, thank you messages""") \
        .add_output_format("""{
  "category": "category_name",
  "confidence": 0.95,
  "loan_number": "LOAN-123456",
  "borrower": "John Smith",
  "urgency": "High",
  "action_items": ["item1", "item2"],
  "deadline": "2024-03-15",
  "routing": "team_name",
  "summary": "One sentence summary"
}

IMPORTANT: Always output valid JSON, nothing else.""") \
        .set_rules(ConversationRules(
            max_questions_per_message=0,
            max_response_words=0,
            avoid_conciliatory_phrases=True
        )) \
        .build()


def create_document_collection_agent(
    agent_name: str = "Alex",
    company: str = "The Tim Loss Team"
) -> str:
    """Create a document collection agent prompt"""
    persona = AgentPersona(
        name=agent_name,
        role="Document Specialist",
        company=company,
        expertise=["Document requirements", "Upload assistance", "Compliance"],
        personality_traits=["efficient", "detail-oriented", "patient"]
    )

    rules = ConversationRules(
        max_questions_per_message=1,
        max_response_words=80,
        persistent_engagement=True
    )

    builder = AgentPromptBuilder()
    return builder \
        .set_objective("efficiently collect all required mortgage documents from borrowers") \
        .set_conversation_style(ConversationStyle.FRIENDLY) \
        .set_persona(persona) \
        .set_first_message(
            f"Hi {{{{first_name}}}}! It's {agent_name} from {company}. "
            "I'm here to help you get your documents uploaded for your loan application. "
            "Do you have 5 minutes right now?"
        ) \
        .add_custom_section('documents', """### Required Documents (in order of priority):

**Critical (need these first):**
1. Last 2 pay stubs
2. Last 2 months bank statements
3. Government-issued ID (front and back)

**Important (need before underwriting):**
4. Last 2 years W2s
5. Last 2 years tax returns (if self-employed)
6. Proof of other income (if applicable)

### Document Collection Flow:
Step 1: Check what they already have
Step 2: Send upload link for ready items
Step 3: Track progress with checkmarks
Step 4: Handle missing items with specific deadlines
Step 5: Confirm completion""") \
        .set_rules(rules) \
        .add_success_criteria(
            "All critical documents uploaded within 48 hours. "
            "Complete package ready for underwriter within 5 business days."
        ) \
        .build()


def create_rate_lock_agent(
    agent_name: str = "Jordan",
    company: str = "The Tim Loss Team"
) -> str:
    """Create a rate lock intelligence agent prompt"""
    persona = AgentPersona(
        name=agent_name,
        role="Rate Intelligence Specialist",
        company=company,
        expertise=["Mortgage rates", "Market analysis", "Rate lock timing"],
        personality_traits=["urgent", "data-driven", "decisive"]
    )

    objections = ObjectionHandling(
        common_objections={
            "I want to wait for lower rates": "I track this 24/7. Right now is actually the sweet spot. Even if rates drop 0.125% later, you'll have paid $X more in the meantime. Plus there's a 70% chance rates go UP instead. Want me to show you the math?",
            "I need to think about it": "How long do you need? Your quote expires in {{hours}} hours. After that, you get whatever rate is current. Could be higher.",
            "Can I lock and get a lower rate if it drops?": "Our policy is lock-and-drop within 30 days. If rates fall 0.25%+ after you lock, we'll renegotiate. But that's rare. Want to lock?",
        }
    )

    rules = ConversationRules(
        max_questions_per_message=1,
        max_response_words=80,
        persistent_engagement=True
    )

    builder = AgentPromptBuilder()
    return builder \
        .set_objective("monitor rate movements and proactively contact borrowers when they should lock their rate") \
        .set_conversation_style(ConversationStyle.URGENT) \
        .set_training([SalesMethodology.CHALLENGER_SALE], "Mortgage Rate Analysis, Market Economics") \
        .set_persona(persona) \
        .set_first_message(
            f"{{{{first_name}}}} - {agent_name} at {company}.\n\n"
            "Rates just moved. Your rate: {{current_rate}}% -> Now available: {{new_rate}}%\n"
            "This rate expires in {{hours}} hours.\n\n"
            "Lock now? Yes or no?"
        ) \
        .set_objection_handling(objections) \
        .set_rules(rules) \
        .add_custom_section('urgency', """### Creating Urgency:
- Use specific timeframes (hours, not days)
- Show specific dollar amounts at stake
- Present risk/reward trade-offs
- Never say "take your time"
- Follow up every 2 hours if rate is expiring""") \
        .add_success_criteria(
            "Borrower locked at optimal rate based on their closing timeline. "
            "Rate lock executed before quote expiration."
        ) \
        .build()
