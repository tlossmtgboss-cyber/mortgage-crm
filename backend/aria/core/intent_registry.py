"""
aria/core/intent_registry.py
Perennia AI — Aria Intent & Slot Registry

Defines every task Aria understands. Each intent has:
  - Required slots (info Aria must collect before executing)
  - Optional slots (info that improves the output but isn't blocking)
  - Confirmation requirement (true for any irreversible action)
  - Execution handler reference

Adding a new capability to Aria = add an Intent here + a handler in task_executor.py
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class SlotSpec:
    name: str
    description: str
    slot_type: str          # "text" | "number" | "email" | "phone" | "date" | "choice" | "borrower" | "contact"
    required: bool = True
    choices: List[str] = field(default_factory=list)
    default: Any = None
    extraction_hint: str = ""   # hint to NLU for extracting this slot from natural language


@dataclass
class Intent:
    name: str
    description: str
    trigger_phrases: List[str]              # example phrases that trigger this intent
    required_slots: List[SlotSpec]
    optional_slots: List[SlotSpec] = field(default_factory=list)
    requires_confirmation: bool = True      # show preview before executing
    category: str = "general"

    def get_slot(self, name: str) -> Optional[SlotSpec]:
        for s in self.required_slots + self.optional_slots:
            if s.name == name:
                return s
        return None


class IntentRegistry:
    _instance: Optional["IntentRegistry"] = None

    def __init__(self):
        self.intents: List[Intent] = _build_intents()
        self._by_name: Dict[str, Intent] = {i.name: i for i in self.intents}

    @classmethod
    def get(cls) -> "IntentRegistry":
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def get_intent(self, name: str) -> Optional[Intent]:
        return self._by_name.get(name)


def _build_intents() -> List[Intent]:
    return [

        # ── Documents ──────────────────────────────────────────────────────────

        Intent(
            name="send_preapproval_letter",
            description="Generate and send a mortgage pre-approval letter to a realtor or borrower via email or SMS",
            category="documents",
            trigger_phrases=[
                "send a pre-approval letter",
                "pre-approval for",
                "send preapproval",
                "generate pre-approval",
                "prequal letter",
                "pre-qual for",
                "text a pre-approval letter",
                "send pre-approval via sms",
                "send preapproval via text",
                "sms pre-approval",
                "text the pre-approval to",
            ],
            required_slots=[
                SlotSpec("borrower_id",      "Which borrower this letter is for",                  "borrower",  extraction_hint="borrower name or loan number"),
                SlotSpec("recipient",        "Who to send the letter to — name, email, or phone",  "contact",   extraction_hint="recipient name, email address, or phone number"),
                SlotSpec("approval_amount",  "Dollar amount to show on the letter",                 "number",    extraction_hint="dollar amount, may say 'full amount' or specific figure"),
            ],
            optional_slots=[
                SlotSpec("delivery_channel", "How to deliver: email or sms",                        "choice",  required=False, default="email",
                         choices=["email", "sms"],
                         extraction_hint="'via sms', 'via text', 'text it', 'by text' = sms. 'via email', 'email it' = email. Default: email"),
                SlotSpec("property_address", "Property address if specific property is involved",   "text",    required=False),
                SlotSpec("expiry_days",      "How many days until the letter expires (default 30)", "number",  required=False, default=30),
                SlotSpec("custom_note",      "Any custom note to include",                          "text",    required=False),
            ],
        ),

        Intent(
            name="send_conditional_approval",
            description="Generate and send a conditional approval letter with outstanding conditions listed",
            category="documents",
            trigger_phrases=["conditional approval", "approval letter with conditions", "send conditions letter"],
            required_slots=[
                SlotSpec("borrower_id",     "Which borrower",          "borrower"),
                SlotSpec("recipient_email", "Who to send it to",       "email"),
                SlotSpec("conditions",      "List of outstanding conditions to include", "text"),
            ],
            optional_slots=[
                SlotSpec("due_date", "Deadline for conditions to be cleared", "date", required=False),
            ],
        ),

        Intent(
            name="send_adverse_action_notice",
            description="Generate and send a required ECOA/FCRA adverse action notice to a declined applicant",
            category="documents",
            trigger_phrases=["adverse action", "denial notice", "send denial", "decline notice"],
            required_slots=[
                SlotSpec("borrower_id",     "Which borrower",                "borrower"),
                SlotSpec("denial_reasons",  "Reasons for adverse action",    "text"),
                SlotSpec("credit_score",    "Applicant's credit score used", "number"),
            ],
        ),

        Intent(
            name="generate_loe",
            description="Generate a Letter of Explanation for an underwriter regarding a specific issue",
            category="documents",
            trigger_phrases=["LOE", "letter of explanation", "explain the", "write an explanation for"],
            required_slots=[
                SlotSpec("borrower_id", "Which borrower",       "borrower"),
                SlotSpec("loe_topic",   "What needs explaining", "text", extraction_hint="credit inquiry, employment gap, large deposit, late payment, etc."),
            ],
            optional_slots=[
                SlotSpec("details", "Additional details to include in the explanation", "text", required=False),
            ],
        ),

        # ── Communications ─────────────────────────────────────────────────────

        Intent(
            name="send_sms",
            description="Send an SMS message to a borrower, realtor, or other contact",
            category="communication",
            trigger_phrases=["text", "sms", "send a message", "text message to"],
            required_slots=[
                SlotSpec("recipient",   "Who to text — borrower, realtor, or contact name", "contact"),
                SlotSpec("message",     "What to say in the message",                        "text"),
            ],
            optional_slots=[
                SlotSpec("send_time", "When to send (default: now)", "text", required=False, default="now"),
            ],
        ),

        Intent(
            name="send_email",
            description="Send an email to a borrower, realtor, title company, or other contact",
            category="communication",
            trigger_phrases=["send an email", "email", "reach out to", "follow up with"],
            required_slots=[
                SlotSpec("recipient",  "Who to email",        "contact"),
                SlotSpec("subject",    "Email subject line",  "text"),
                SlotSpec("body",       "Email body content",  "text"),
            ],
            optional_slots=[
                SlotSpec("cc",         "Anyone to CC",              "email",    required=False),
                SlotSpec("attachments","Any documents to attach",    "text",     required=False),
            ],
        ),

        Intent(
            name="schedule_call",
            description="Schedule a call and send a calendar invite",
            category="communication",
            trigger_phrases=["schedule a call", "book a call", "set up a call", "schedule time with"],
            required_slots=[
                SlotSpec("with_person", "Who to schedule the call with", "contact"),
                SlotSpec("call_date",   "Date for the call",             "date"),
                SlotSpec("call_time",   "Time for the call",             "text"),
            ],
            optional_slots=[
                SlotSpec("duration_minutes", "Duration in minutes (default 30)", "number", required=False, default=30),
                SlotSpec("call_topic",       "What the call is about",           "text",   required=False),
            ],
        ),

        # ── Pipeline actions ────────────────────────────────────────────────────

        Intent(
            name="update_loan_status",
            description="Move a loan to a new stage in the pipeline",
            category="pipeline",
            trigger_phrases=["move loan to", "update status", "change stage", "mark as", "pipeline stage"],
            required_slots=[
                SlotSpec("borrower_id", "Which borrower/loan", "borrower"),
                SlotSpec("new_stage",   "New pipeline stage",  "choice",
                         choices=["lead", "application", "processing", "underwriting",
                                  "conditional_approval", "clear_to_close", "closing", "funded", "denied"]),
            ],
        ),

        Intent(
            name="add_loan_note",
            description="Add a note to a loan file",
            category="pipeline",
            trigger_phrases=["add a note", "note on", "log that", "make a note"],
            required_slots=[
                SlotSpec("borrower_id", "Which loan/borrower", "borrower"),
                SlotSpec("note_text",   "What to note",        "text"),
            ],
            requires_confirmation=False,   # Low risk — no confirmation needed
        ),

        Intent(
            name="create_task",
            description="Create a task or reminder, optionally assigned to someone",
            category="pipeline",
            trigger_phrases=["create a task", "remind me", "set a reminder", "add a task", "follow up on"],
            required_slots=[
                SlotSpec("task_description", "What the task is",      "text"),
                SlotSpec("due_date",         "When it's due",         "date"),
            ],
            optional_slots=[
                SlotSpec("assigned_to",  "Who to assign it to (default: self)", "text", required=False),
                SlotSpec("borrower_id",  "Linked borrower if applicable",       "borrower", required=False),
            ],
            requires_confirmation=False,
        ),

        Intent(
            name="request_documents",
            description="Send a document request to a borrower via their portal",
            category="pipeline",
            trigger_phrases=["request documents", "ask for docs", "document request", "need documents from"],
            required_slots=[
                SlotSpec("borrower_id",   "Which borrower",           "borrower"),
                SlotSpec("doc_list",      "Which documents to request", "text"),
            ],
            optional_slots=[
                SlotSpec("due_date",  "When documents are needed by", "date", required=False),
                SlotSpec("note",      "Custom note to the borrower",  "text", required=False),
            ],
        ),

        # ── Lookups & analysis ──────────────────────────────────────────────────

        Intent(
            name="loan_status_lookup",
            description="Look up the current status and details of a loan",
            category="lookup",
            trigger_phrases=["what's the status", "how is", "where are we with", "pull up", "check on"],
            required_slots=[
                SlotSpec("borrower_id", "Which borrower/loan to look up", "borrower"),
            ],
            requires_confirmation=False,
        ),

        Intent(
            name="mortgage_guideline_question",
            description="Answer a question about mortgage guidelines (FHA, VA, Conventional, USDA)",
            category="knowledge",
            trigger_phrases=[
                "what are the guidelines", "guideline question", "does FHA allow",
                "VA requirement", "conventional limit", "can a borrower with", "minimum credit score"
            ],
            required_slots=[
                SlotSpec("question", "The specific guideline question", "text"),
            ],
            requires_confirmation=False,
        ),

        Intent(
            name="pipeline_report",
            description="Generate a summary report of pipeline performance or activity",
            category="reporting",
            trigger_phrases=["pipeline report", "how many loans", "pipeline summary", "show me my pipeline"],
            required_slots=[],
            optional_slots=[
                SlotSpec("time_period", "Time period to report on", "text", required=False, default="this month"),
                SlotSpec("filter_by",   "Filter by stage, LO, or status", "text", required=False),
            ],
            requires_confirmation=False,
        ),

        Intent(
            name="run_income_analysis",
            description="Run an AI income analysis on a borrower to calculate qualifying income",
            category="analysis",
            trigger_phrases=["income analysis", "calculate income", "qualifying income for", "what income qualifies"],
            required_slots=[
                SlotSpec("borrower_id", "Which borrower", "borrower"),
            ],
            requires_confirmation=False,
        ),
    ]
