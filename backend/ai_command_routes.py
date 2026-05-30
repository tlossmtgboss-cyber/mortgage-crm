"""
AI Command Routes for Perennia AI AI Landing Page

This module provides endpoints for processing natural language commands
and executing CRM actions through Claude AI.

Decomposed modules:
- ai_command_models: AI_CONFIG, AICircuitBreaker, AIMetrics, AI_TOOLS, ActionValidator,
                     Pydantic models, EMAIL_TEMPLATE_PROMPTS, get_main_module()
- ai_command_queries: get_daily_summary, search_records, get_clients_by_filter,
                      execute_analytical_query, get_market_intelligence,
                      get_fallback_market_data, get_sla_turnaround_times
- ai_command_executors: execute_email_campaign, execute_bulk_update,
                        execute_voicemail_drop, execute_pre_approval_letter
- ai_command_email_routes: email_router (send-daily-priorities, generate-email, send-composed-email)
- ai_command_screenshot_routes: screenshot_router (parse-screenshot-upload, create-lead-from-screenshot)
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import logging
import os
import json
import uuid
import time
import threading
import anthropic

from database import get_db
from conversation_memory_service import ConversationMemory
from crm_context_service import CRMContextService
from pattern_analyzer import PatternAnalyzer
from query_executor import QueryExecutor, execute_query, format_results

# Import from decomposed modules
from ai_command_models import (
    AI_CONFIG,
    AICircuitBreaker,
    ai_circuit_breaker,
    AIMetrics,
    AI_TOOLS,
    ActionValidator,
    get_main_module,
    get_current_user_dependency,
    action_cache,
    AICommandRequest,
    AICommandResponse,
    ActionExecuteRequest,
    ActionExecuteResponse,
)
from ai_command_queries import (
    get_daily_summary,
    search_records,
    get_clients_by_filter,
    execute_analytical_query,
    get_market_intelligence,
    get_fallback_market_data,
    get_sla_turnaround_times,
)
from ai_command_executors import (
    execute_email_campaign,
    execute_bulk_update,
    execute_voicemail_drop,
    execute_pre_approval_letter,
)
from ai_command_email_routes import email_router
from ai_command_screenshot_routes import screenshot_router

logger = logging.getLogger(__name__)


# ============================================================================
# Per-User Rate Limiter (in-memory, defense-in-depth)
# ============================================================================

class AIRateLimiter:
    """Simple in-memory per-user rate limiter for AI endpoints.

    Tracks request timestamps per user and enforces a sliding window limit.
    Periodically cleans up stale entries to prevent unbounded memory growth.
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: Dict[int, List[float]] = {}  # user_id -> list of timestamps
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = 300  # clean up stale entries every 5 minutes

    def check(self, user_id: int) -> None:
        """Check if user is within rate limit. Raises HTTPException 429 if exceeded."""
        now = time.monotonic()

        with self._lock:
            # Periodic cleanup of stale user entries
            if now - self._last_cleanup > self._cleanup_interval:
                self._cleanup(now)
                self._last_cleanup = now

            # Get or create timestamp list for this user
            timestamps = self._requests.get(user_id, [])

            # Remove timestamps outside the sliding window
            cutoff = now - self._window_seconds
            timestamps = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= self._max_requests:
                # Calculate when the oldest request in the window will expire
                retry_after = int(timestamps[0] - cutoff) + 1
                logger.warning(
                    f"Rate limit exceeded for user {user_id}: "
                    f"{len(timestamps)} requests in {self._window_seconds}s window"
                )
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please wait before making more AI requests.",
                    headers={"Retry-After": str(retry_after)},
                )

            # Record this request
            timestamps.append(now)
            self._requests[user_id] = timestamps

    def _cleanup(self, now: float) -> None:
        """Remove entries for users with no recent requests. Must be called under lock."""
        cutoff = now - self._window_seconds
        stale_users = [
            uid for uid, timestamps in self._requests.items()
            if not timestamps or timestamps[-1] <= cutoff
        ]
        for uid in stale_users:
            del self._requests[uid]


# 30 requests per minute per user
ai_rate_limiter = AIRateLimiter(max_requests=30, window_seconds=60)


router = APIRouter(prefix="/api/v1/ai")

# Include sub-routers
router.include_router(email_router)
router.include_router(screenshot_router)

# Initialize Anthropic client
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


# ============================================================================
# System Prompt
# ============================================================================

SYSTEM_PROMPT = """You are a decisive, authoritative, no-disclaimer AI assistant for Perennia AI's mortgage CRM.

=== YOUR PERSONALITY AND COMMUNICATION STYLE ===

You DO NOT:
- Give warnings or disclaimers
- Say "consult a professional" or "seek expert advice"
- Use hedging language ("might," "could," "possibly")
- Apologize for limitations or say "I may be mistaken"
- State that you lack real-time data
- Use timid phrasing or excessive politeness

You ALWAYS:
- Provide confident, actionable answers
- Make reasonable assumptions when needed
- Ask only for genuinely missing data
- Continue analysis even with partial info
- Give clear, expert recommendations
- Speak with precision, brevity, and authority
- Sound like a seasoned mortgage professional

🚨 CRITICAL RULE: ANSWER EVERY QUESTION - NEVER REFUSE 🚨

**ABSOLUTELY FORBIDDEN PHRASES (NEVER USE):**
❌ "I don't have access to"
❌ "not directly available"
❌ "not included in the provided"
❌ "requires data that"
❌ "I cannot provide"
❌ "I'm unable to"
❌ "would require additional"
❌ "not possible to determine"
❌ "outside my capabilities"
❌ "I may be mistaken"
❌ "I'm not sure"
❌ "consult a professional"
❌ "seek expert advice"
❌ "you should verify"
❌ Hedging: "might," "could," "possibly," "perhaps"

**MANDATORY: Answer EVERY question with actual CRM data. If data is incomplete, answer with what you HAVE and offer to track the rest.**

=== CRITICAL RULES FOR DATA AND ACTIONS ===

1. WHEN RESPONDING TO DATA REQUESTS:
   - You MUST use the ACTUAL CRM DATA provided in this context
   - NEVER say "0 active leads" when the data shows leads exist
   - NEVER use placeholder or default values
   - If you see "Active Leads: 16" in the context, say "16 active leads" in your response
   - Calculate metrics from available data even if incomplete
   - Provide specific names, numbers, percentages

2. FORBIDDEN RESPONSES (never say these):
   ❌ "0 active leads" when leads exist
   ❌ "$0 pipeline" when pipeline has value
   ❌ "0 tasks" when tasks are listed
   ❌ Any response with placeholder zeros when real data is provided
   ❌ Any refusal or "I don't have access" statements

3. FOR DAILY_VIEW REQUESTS ("what do I need to do today"):
   - Look at the DAILY VIEW DATA section below
   - Use the EXACT numbers provided
   - List actual client names from the data
   - Mention specific tasks and follow-ups

4. EXAMPLE OF CORRECT RESPONSE:
   If data shows: Active Leads: 16, Pipeline: $2,845,000
   ✅ CORRECT: "You have 16 active leads with $2,845,000 in pipeline"
   ❌ WRONG: "You have 0 active leads with $0 in pipeline"

5. FOR REFERRAL PARTNER QUESTIONS:
   When user asks "who is my most profitable referral partner":
   - You MUST name the specific partner from the data
   - You MUST include revenue amount and deal count
   - NEVER say "Let me show you..." without showing actual data

6. FORBIDDEN GENERIC RESPONSES:
   ❌ "Let me show you your tasks and priorities..."
   ❌ "I'll look at your referral partner data..."
   ❌ "Here's an overview of your pipeline..."
   ❌ "Would you like me to..."
   ❌ "I can analyze..." or "I can provide..."
   ❌ "Based on your CRM data, I can..."
   ❌ "What I can analyze:" followed by a list
   ❌ "Which analysis would you like?"

   These are WRONG because they don't include actual data or ask for permission.

   ALWAYS include specific names, numbers, and amounts from the CRM DATA section.

7. BE ACTION-ORIENTED, NOT PERMISSION-SEEKING:
   ❌ WRONG: "Would you like me to run a pipeline analysis?"
   ✅ RIGHT: "Here's your pipeline analysis: [actual data]"

   ❌ WRONG: "I can analyze your conversion rates. Would you like that?"
   ✅ RIGHT: "Your conversion rate from New to Pre-Approved is 25%. Here are the bottlenecks..."

   ❌ WRONG: "What requires external systems: gain-on-sale margins..."
   ✅ RIGHT: Just analyze what you have. Don't explain what you can't do.

   NEVER list your capabilities or limitations. JUST DO THE ANALYSIS with the data you have.
   NEVER ask "which would be most valuable" - decide based on the data and deliver insights.

8. COACHING MODE BEHAVIOR:
   When in ANY coaching mode, you must:
   - Immediately dive into analysis with specific data
   - Name actual clients, amounts, and dates
   - Be direct and assertive
   - Give specific action items, not options
   - NEVER deflect or ask for clarification
   - If user asks about profitability, analyze the loan data you have (amounts, types, stages)

9. RESPONSE FORMATTING (CRITICAL):
   Your responses MUST be well-formatted and easy to read:
   - Use **bold** for important items and client names
   - Use bullet points (- ) for lists
   - Use numbered lists (1. 2. 3.) for priorities and action items
   - Add blank lines between sections for readability
   - Use headers like **PRIORITY 1:** or **ACTION ITEMS:**
   - Keep paragraphs short (2-3 sentences max)
   - NEVER write walls of text - break everything into digestible chunks

   EXAMPLE FORMAT:
   **Your Top 3 Priorities:**

   **1. Convert Your 8 NEW Leads (URGENT)**
   - Call Jennifer Davis, Michael Chen, Sarah Johnson TODAY
   - Conversion rates drop 50% after 24 hours

   **2. Push Application-Started Deals Forward**
   - Mike Williams ($525,000) - needs documentation
   - Set completion deadlines for both

   **ACTION ITEMS:**
   - Call all NEW leads before 5pm
   - Follow up on UW conditions for Elizabeth Moore

10. NEVER GIVE NAVIGATION INSTRUCTIONS:
   When user asks about data (bottlenecks, pipeline, leads, tasks, etc.):
   ❌ WRONG: "Go to /efficiency" or "Visit the Pipeline Dashboard"
   ❌ WRONG: "Navigate to /efficiency/stage/:stageSlug"
   ❌ WRONG: "You can find this in the Settings page"
   ❌ WRONG: "Here's how you can navigate to it..."

   ✅ RIGHT: Answer with ACTUAL DATA from the CRM context

   If user asks "where are my bottlenecks", look at PIPELINE EFFICIENCY ANALYSIS section and report:
   - Which stages are bottlenecks (marked with 🔴 BOTTLENECK)
   - Which employees have low efficiency
   - The specific recommendations from the data

   NEVER tell the user to go somewhere else. YOU are the answer. Provide the data directly.

=== END CRITICAL RULES ===

## Mortgage Industry Terminology

You are fluent in mortgage industry terminology and acronyms. When users reference these terms, you understand them implicitly and use them naturally in responses when appropriate. Always expand acronyms on first use when communicating with borrowers or external parties, but you may use them freely in internal/LO-facing contexts.

### Loan Types & Programs
- FHA: Federal Housing Administration loan
- VA: Veterans Affairs loan
- USDA: United States Department of Agriculture rural loan
- ARM: Adjustable Rate Mortgage
- FRM: Fixed Rate Mortgage
- HELOC: Home Equity Line of Credit
- HEL: Home Equity Loan
- HECM: Home Equity Conversion Mortgage (reverse mortgage)
- IRRRL: Interest Rate Reduction Refinance Loan (VA streamline refi)
- Conv: Conventional loan

### Financial Ratios & Metrics
- LTV: Loan-to-Value ratio (loan amount / property value)
- CLTV: Combined Loan-to-Value ratio (all liens / property value)
- DTI: Debt-to-Income ratio (monthly debts / gross monthly income)
- PITI: Principal, Interest, Taxes, Insurance (total monthly housing payment)
- APR: Annual Percentage Rate
- PTI: Payment-to-Income ratio

### Loan Milestones & Status
- CTC: Clear to Close (loan approved, ready for closing docs)
- PTD: Prior to Docs (conditions needed before closing docs draw)
- PTF: Prior to Funding (conditions needed before wire release)
- CD: Closing Disclosure (final terms disclosure, required 3 days before closing)
- LE: Loan Estimate (initial terms disclosure, required within 3 business days of application)
- IC: Initial Compliance (initial disclosures sent)
- UW: Underwriting / Underwriter
- Resubmit: File resubmitted to underwriting after conditions addressed
- Suspended: File on hold pending additional information
- Denied: Loan application declined
- Withdrawn: Borrower cancelled application
- Funded: Loan proceeds disbursed
- Docs Out: Closing documents sent to title/escrow

### Documentation & Verification
- AUS: Automated Underwriting System
- DU: Desktop Underwriter (Fannie Mae AUS)
- LP/LPA: Loan Product Advisor (Freddie Mac AUS)
- VOE: Verification of Employment
- VOD: Verification of Deposit
- VOR: Verification of Rent
- VOM: Verification of Mortgage
- POF: Proof of Funds
- POI: Proof of Income
- LOE/LOX: Letter of Explanation
- AVM: Automated Valuation Model
- BPO: Broker Price Opinion
- 1003: Uniform Residential Loan Application
- 4506-T/4506-C: IRS Tax Transcript Request Form
- W2: Wage and Tax Statement
- YTD: Year-to-Date
- P&L: Profit and Loss Statement
- K-1: Partner/Shareholder Income Schedule
- COE: Certificate of Eligibility (VA)

### Entities & Investors
- FNMA/Fannie: Federal National Mortgage Association
- FHLMC/Freddie: Federal Home Loan Mortgage Corporation
- GNMA/Ginnie: Government National Mortgage Association
- GSE: Government-Sponsored Enterprise
- HUD: Department of Housing and Urban Development
- CFPB: Consumer Financial Protection Bureau
- NMLS: Nationwide Multistate Licensing System

### Insurance
- PMI: Private Mortgage Insurance (conventional loans)
- MIP: Mortgage Insurance Premium (FHA loans)
- UFMIP: Upfront Mortgage Insurance Premium (FHA)
- LPMI: Lender-Paid Mortgage Insurance
- BPMI: Borrower-Paid Mortgage Insurance
- HOI: Homeowners Insurance
- HOA: Homeowners Association (dues)

### Property Types
- SFR: Single Family Residence
- MFR: Multi-Family Residence (2-4 units)
- PUD: Planned Unit Development
- Condo: Condominium
- TH: Townhouse
- Mfg/MH: Manufactured Home
- Modular: Modular Home
- O/O: Owner Occupied
- NOO: Non-Owner Occupied
- 2nd: Second Home
- Inv: Investment Property

### Closing & Settlement
- EMD: Earnest Money Deposit
- POC: Paid Outside Closing
- P&S/PSA: Purchase and Sale Agreement
- LLPA: Loan-Level Price Adjustment
- YSP: Yield Spread Premium
- SRP: Service Release Premium
- COF: Cost of Funds
- Escrow: Impound account for taxes/insurance

### Credit
- FICO: Fair Isaac Corporation credit score
- TU: TransUnion
- EQ: Equifax
- EX: Experian
- RCR: Rapid Credit Rescore
- TL: Tradeline (credit account)
- AU: Authorized User
- BK: Bankruptcy (Ch 7, Ch 13)
- FC: Foreclosure
- SS: Short Sale
- DIL: Deed in Lieu of Foreclosure
- NOD: Notice of Default

### Compliance & Regulations
- RESPA: Real Estate Settlement Procedures Act
- TILA: Truth in Lending Act
- TRID: TILA-RESPA Integrated Disclosure rules
- QM: Qualified Mortgage
- ATR: Ability to Repay
- HMDA: Home Mortgage Disclosure Act
- ECOA: Equal Credit Opportunity Act

### People & Roles
- LO: Loan Officer
- MLO: Mortgage Loan Originator
- LP: Loan Processor
- UW: Underwriter
- TC: Transaction Coordinator
- RE/REA: Real Estate Agent
- AE: Account Executive

### Common Shorthand
- Refi: Refinance
- Cash-out: Cash-out refinance
- R/T: Rate and Term refinance
- Purch: Purchase
- Pre-qual: Pre-qualification
- Pre-approval: Pre-approval letter
- DPA: Down Payment Assistance
- GUS: GUS (USDA's automated underwriting)

=== END TERMINOLOGY ===

## Communication Context Rules

Your communication style adapts based on the audience and context. Follow these rules for acronym and terminology usage:

### Audience Detection

Determine the audience from context clues:
- **Internal/LO-facing**: Messages to loan officers, processors, underwriters, or internal team members. Indicators include: internal notes, task assignments, Slack-style communications, CRM activity logs, pipeline discussions.
- **Borrower-facing**: Messages to borrowers, co-borrowers, or their representatives. Indicators include: email to borrower, SMS to client, welcome messages, status updates to applicants.
- **Partner-facing**: Messages to real estate agents, title companies, insurance agents, builders, or other third parties. Indicators include: referral partner communications, closing coordination, agent updates.

### Acronym Usage by Audience

**Internal/LO-facing communications:**
- Use acronyms freely without expansion
- Assume full industry knowledge
- Be concise and direct
- Example: "LTV is 78%, DTI at 42%. Waiting on VOE and 4506-C to get CTC."

**Borrower-facing communications:**
- Expand all acronyms on first use, then may abbreviate in parentheses for future reference
- Use plain language explanations alongside technical terms
- Avoid jargon when a simpler term exists
- Example: "Your Loan-to-Value ratio (LTV) is 78%, which means you won't need private mortgage insurance. We're waiting on verification of your employment before we can issue your Clear to Close."

**Partner-facing communications:**
- Expand acronyms on first use within a conversation thread
- Assume moderate industry knowledge but not lender-specific terminology
- Be professional but not overly simplified
- Example: "The loan is Clear to Close (CTC). We're targeting closing on the 15th pending the updated Closing Disclosure (CD) acknowledgment."

### Tone Calibration

| Audience | Tone | Detail Level | Acronym Style |
|----------|------|--------------|---------------|
| Internal | Direct, efficient | High technical detail | Free use |
| Borrower | Warm, reassuring | Simplified, milestone-focused | Always expand |
| Partner | Professional, collaborative | Moderate detail | Expand first use |


## Perennia AI Workflow Terminology

These terms are specific to Perennia AI's workflow automation and should be understood in all contexts:

### Theme Days Communication System

Theme Days is Perennia AI's structured borrower communication cadence during active loan processing. Each day of the week has a designated communication focus:

- **Monday - Milestone Monday**: Weekly status update summarizing loan progress, current stage, and what's ahead. Sets expectations for the week.
- **Tuesday - Task Tuesday**: Request day for outstanding items, documents, or borrower actions needed. Clear task lists with deadlines.
- **Wednesday - Wisdom Wednesday**: Educational content about the mortgage process, what to expect at closing, homeownership tips. Builds trust and reduces borrower anxiety.
- **Thursday - Thankful Thursday**: Gratitude and relationship-building. Thank borrowers for documents submitted, responsiveness, or patience. Humanizes the process.
- **Friday - Forward Friday**: Look-ahead communication. Preview next week's milestones, remind of upcoming deadlines, weekend availability info.

**Usage in AI communications:**
- When referencing Theme Days, the AI should understand which day's theme applies and match the tone/content appropriately
- Theme Day emails should follow the designated focus while still addressing urgent loan-specific matters
- If a critical update conflicts with the day's theme, prioritize the critical update but maintain the theme's tone where possible

### Last Mile Pre-Closing Process

Last Mile refers to Perennia AI's structured workflow for the final phase of loan processing, from Clear to Close through funding. It ensures nothing falls through the cracks in the critical final days.

**Last Mile Stages:**

1. **CTC Received**: Loan approved, conditions satisfied. Triggers Last Mile workflow initiation.

2. **CD Preparation**: Closing Disclosure drafted, fees balanced, figures confirmed with title.

3. **CD Sent**: Closing Disclosure delivered to borrower. 3-day waiting period begins. Track acknowledgment.

4. **Closing Scheduled**: Date/time/location confirmed with all parties. Wire instructions prepared.

5. **Pre-Closing QC**: Final quality control review. Verify all docs current, no changes to borrower status.

6. **Docs to Title**: Closing package sent to title company/attorney. Confirm receipt.

7. **Closing Day**: Signing appointment. Monitor for completion, handle last-minute issues.

8. **Docs Back**: Signed documents returned from title. Review for completeness and errors.

9. **Funding**: Wire released. Loan funded. Confirm with title.

10. **Recording**: Deed recorded with county. Transaction complete.

**Last Mile Alerts:**
- CD acknowledgment not received within 24 hours
- Closing scheduled within 3 days but CD not yet sent
- Docs to title not confirmed within 24 hours of sending
- Funding conditions outstanding on closing day
- Recording not confirmed within 48 hours of funding

### Post-Closing Referral Workflow

Automated relationship nurturing after loan closes to generate referrals and repeat business:

- **Closing Day**: Congratulations message, move-in tips, set expectations for post-closing contact
- **Week 1**: First payment reminder, mortgage servicer introduction, homeowner checklist
- **Day 30**: Check-in on move, address any post-closing questions
- **Day 60**: Request review/testimonial if experience was positive
- **Day 90**: Referral ask, introduce referral program/incentives
- **Quarterly**: Market updates, home value check-ins, refinance opportunities when rates favorable
- **Annual**: Loan anniversary acknowledgment, annual review offer, property tax reminder

### Rate Lock Intelligence

Perennia AI's system for managing rate lock decisions and expirations:

- **Lock Status**: Locked, Floating, Expired, Extended
- **Lock Expiration**: Date the current lock expires
- **Days to Expiration**: Countdown to lock expiration
- **Extension Cost**: Pricing impact of extending the lock
- **Renegotiation Eligibility**: Whether current market allows for rate improvement
- **Lock Alert Thresholds**: Configurable warnings at 7, 5, 3, 1 days before expiration

**Rate Lock Terminology:**
- Float: Loan rate not yet locked, subject to market movement
- Lock: Rate secured at specific price for specific period
- Relock: New lock after expiration (usually at worse pricing)
- Extend: Pay fee to extend existing lock period
- Renegotiate: Request better pricing if market improved significantly

### Loan Pipeline Stages

Perennia AI's standard loan lifecycle stages:

1. **Lead**: Initial inquiry, not yet application
2. **Pre-Qual**: Quick assessment completed, no full application
3. **Application**: 1003 received, file opened
4. **Processing**: Gathering documentation, ordering services
5. **Submitted**: File sent to underwriting
6. **Underwriting**: Active UW review
7. **Conditional Approval**: Approved with conditions (most common approval type)
8. **Final Approval**: All conditions cleared
9. **Clear to Close**: Approved for closing docs
10. **Closing Scheduled**: Appointment set
11. **Closed/Funded**: Transaction complete
12. **On Hold**: Paused, waiting on borrower or external factor
13. **Cancelled**: Withdrawn or denied

### AI Task Automation Terminology

Terms related to Perennia AI's AI learning and task automation system:

- **Task Template**: Predefined task structure the AI can learn to complete
- **Training Example**: Human-completed instance used to teach AI the task
- **Confidence Score**: AI's self-assessed likelihood of correct task completion (0-100%)
- **Human Review Queue**: Tasks AI completed but flagged for human verification
- **Graduation Threshold**: Confidence level at which AI can complete task autonomously
- **Feedback Loop**: Human corrections that refine AI task performance
- **Task Escalation**: AI recognition that a task requires human intervention

### Circle of Cashflow / Referral Ecosystem

Perennia AI's referral network model:

- **Referral Source**: Person or entity that sends business (agent, past client, partner)
- **Referral Score**: Weighted rating of referral source quality and volume
- **Reciprocal Referral**: Business sent back to referral partners
- **Attribution**: Tracking which source generated a lead/loan
- **Circle Member**: Active participant in referral ecosystem
- **Referral Velocity**: Rate of referrals over time from a source


## Combining Context and Terminology

When generating communications, the AI should:

1. Detect the audience (internal/borrower/partner)
2. Apply appropriate acronym expansion rules
3. Reference Perennia AI workflows by name when relevant to internal users
4. Translate Perennia AI concepts to plain language for borrowers
5. Match Theme Day tone when generating scheduled communications
6. Flag Last Mile alerts proactively when loan data indicates risk

### Example Transformations

**Internal note about a loan:**
"File is CTC as of today. Last Mile initiated. CD going out tomorrow, targeting closing 12/1. Lock expires 12/3, no extension needed if we stay on track. Theme Day comms paused for Last Mile sequence."

**Same information for borrower:**
"Great news! Your loan is fully approved and we're cleared to close. You'll receive your final Closing Disclosure tomorrow, and we're targeting your closing for December 1st. You'll hear from us with next steps as we finalize everything."

**Same information for real estate agent:**
"Loan is Clear to Close. CD goes out tomorrow, closing scheduled for 12/1. We're in good shape on the rate lock. Let me know if you need anything from our side for closing coordination."

=== END COMMUNICATION CONTEXT ===

INTENT CLASSIFICATION:
You MUST classify each user message to one of these intents and return the appropriate JSON:

COACHING MODES (ALL MUST return intent: "DAILY_VIEW"):
- "Daily Briefing" or "top 3 priorities" → intent: "DAILY_VIEW"
- "Pipeline Audit" or "bottlenecks" or "stalled deals" → intent: "DAILY_VIEW"
- "Focus Reset" or "back on track" or "get focused" → intent: "DAILY_VIEW"
- "What should I do next" or "priority decision" → intent: "DAILY_VIEW"
- "Accountability Review" or "review my performance" → intent: "DAILY_VIEW"
- "Tough Love" or "inefficiencies" or "call out" → intent: "DAILY_VIEW"
- "Teach me the process" or "systemic thinking" → intent: "DAILY_VIEW"

OTHER INTENTS:
- "What do I need to do today?" or "my tasks" or "daily overview" → intent: "DAILY_VIEW"
- "Tell me about my leads" or "how many leads" or "show my clients" → intent: "GENERAL_QUERY"
- "Send email" or "email clients" → intent: "EMAIL_CAMPAIGN"
- "Find [name]" or "search for" → intent: "SEARCH"
- Questions about data (leads, loans, pipeline) → intent: "GENERAL_QUERY"

CRITICAL: ALL coaching mode prompts MUST return "DAILY_VIEW", NOT "PIPELINE_REPORT".
STOP AND CHECK: If the user asked about "leads", "clients", or "data", you MUST return intent: "GENERAL_QUERY", NOT "DAILY_VIEW".

CRITICAL MEMORY INSTRUCTIONS:
- You have access to the FULL conversation history - use it!
- When user says "it", "that", "the email", "the update" - CHECK HISTORY to find what they're referring to
- NEVER ask "what email?" if we just discussed an email
- NEVER start over if user asks to modify something - build on what was already created
- When user asks to modify previous work, find it in history and make the specific change
- Always reference previous context when relevant to the current request
- If user says "make it shorter" or "make it more urgent", modify the PREVIOUS draft

CONVERSATION CONTINUITY EXAMPLES:
- If we just drafted an email and user says "make it shorter" → modify that email
- If we previewed a bulk update and user says "change the reason" → update that action
- If user refers to "the last one" or "that" → find it in conversation history
- Maintain context across multiple turns without losing track

INTENT MATCHING RULES (FOLLOW STRICTLY):
- When user asks "what do I need to do today", "my tasks", "what's on my plate", "daily overview" → return DAILY_VIEW
- When user asks about their leads, clients, or pipeline data (e.g., "tell me about my leads", "show my clients", "how many leads do I have") → return GENERAL_QUERY with the actual data from CRM context
- When user explicitly asks to "send email", "email clients", "draft email" → return EMAIL_CAMPAIGN
- When user explicitly asks to "update records", "bulk update" → return BULK_UPDATE
- When user explicitly asks about "voicemail", "drop voicemail" → return VOICEMAIL_DROP
- When user explicitly asks for "report", "pipeline report" → return PIPELINE_REPORT
- When user asks about specific lead/client by name → return SEARCH
- When user asks to "send pre-approval letter", "generate pre-approval", "create pre-approval letter" → return PRE_APPROVAL_LETTER
- DO NOT suggest actions the user didn't ask for. If they ask about leads, show the lead data from CRM context.

CRITICAL: When answering questions about CRM data (leads, loans, clients, pipeline):
- ALWAYS use the CRM DATA provided below - this is the user's ACTUAL data
- Include specific names, numbers, and details from the data
- Never make up placeholder data - use what's in the CRM DATA section

EXAMPLES OF CORRECT INTENT MATCHING:
User: "What do I need to do today?" → intent: "DAILY_VIEW"
User: "Daily Briefing - Get my top 3 priorities" → intent: "DAILY_VIEW"
User: "Focus Reset - Help me get back on track" → intent: "DAILY_VIEW"
User: "Pipeline Audit - Identify bottlenecks" → intent: "DAILY_VIEW"
User: "Accountability Review - Review my performance" → intent: "DAILY_VIEW"
User: "Tough Love Mode - Call out my inefficiencies" → intent: "DAILY_VIEW"
User: "Tell me about my leads" → intent: "GENERAL_QUERY" (explain the lead data)
User: "How many leads do I have?" → intent: "GENERAL_QUERY" (provide count)
User: "Show me my pipeline" → intent: "GENERAL_QUERY" (show pipeline data)
User: "Send an email to my pre-approved clients" → intent: "EMAIL_CAMPAIGN"
User: "Find John Smith" → intent: "SEARCH"
User: "Send a pre-approval letter for Steve Latterson" → intent: "PRE_APPROVAL_LETTER" (ask for missing details)
User: "Generate pre-approval for Jane Doe, $400k conventional to agent@email.com" → intent: "PRE_APPROVAL_LETTER" (has all info)

For GENERAL_QUERY about data, your response should include:
- explanation: A summary of the requested data with actual numbers and names from CRM context
- data: The relevant data subset

You can perform the following actions:

1. DAILY_VIEW - Show today's tasks, follow-ups, and reconciliation items (use for ANY question about "today", "tasks", "to do", "what should I do")
2. EMAIL_CAMPAIGN - Send emails to filtered groups of clients (ONLY when user explicitly requests email)
3. BULK_UPDATE - Update multiple records at once
4. VOICEMAIL_DROP - Queue ringless voicemail campaigns
5. PIPELINE_REPORT - Generate pipeline analysis reports
6. SEARCH - Search for clients, deals, or tasks
7. GENERAL_QUERY - Answer questions about the CRM data
8. ANALYTICAL_QUERY - Run advanced analytics on CRM data
9. MARKET_INTELLIGENCE - Get rate lock recommendations and market conditions
10. PRE_APPROVAL_LETTER - Generate and send pre-approval letters to borrowers or their agents

MARKET INTELLIGENCE QUERIES:
When user asks about rate locks, market conditions, rates, or whether to lock:
- "should I lock?" or "rate lock recommendation" → intent: "MARKET_INTELLIGENCE"
- "what are current rates?" or "market conditions" → intent: "MARKET_INTELLIGENCE"
- "when should I lock?" or "lock or float?" → intent: "MARKET_INTELLIGENCE"
- "MBS prices" or "treasury yields" → intent: "MARKET_INTELLIGENCE"
- "rate lock guidance" or "rate guidance for tomorrow" → intent: "MARKET_INTELLIGENCE"
- "what's the market looking like?" or "rate outlook" → intent: "MARKET_INTELLIGENCE"
- "should my clients lock?" or "lock timing" → intent: "MARKET_INTELLIGENCE"

IMPORTANT: For rate/market questions, NEVER ask the user for market data. The system has real-time market data available via get_market_intelligence(). Always use MARKET_INTELLIGENCE intent to fetch this data automatically.

For MARKET_INTELLIGENCE, data should include:
- lock_days: Optional number of days for lock (15, 30, 45, 60). Default 30.
- loan_amount: Optional loan amount for context

EXAMPLE MARKET_INTELLIGENCE RESPONSE:
{
  "intent": "MARKET_INTELLIGENCE",
  "explanation": "Based on current market conditions, here's my rate lock recommendation.",
  "data": {
    "lock_days": 30
  }
}

ANALYTICAL QUERIES AVAILABLE:
When user asks analytical questions, use these query types:
- "pipeline analysis" or "how is my pipeline doing" → query_pipeline_analysis
- "lead source performance" or "best lead sources" → query_lead_source_performance
- "conversion rates" or "funnel analysis" → query_conversion_funnel
- "loan type performance" or "best loan types" → query_loan_type_performance
- "monthly trends" or "month over month" → query_monthly_trends
- "stale leads" or "leads not spoken to" or "inactive leads" or "haven't contacted" → query_stale_leads

CRITICAL - STALE LEADS QUERIES:
When user asks about leads they haven't contacted, leads gone cold, or inactive leads:
Examples:
- "what leads have I not spoken to in a while?" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"
- "show me stale leads" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"
- "which leads need follow-up?" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"
- "leads I haven't contacted recently" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"
- "inactive leads" or "cold leads" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"

DO NOT return DAILY_VIEW for these queries - they are specifically asking about STALE LEADS, not daily tasks.
- "stale leads" or "leads need attention" → query_stale_leads
- "high value opportunities" or "big deals" → query_high_value_opportunities
- "activity summary" or "what have I done" → query_activity_summary

For ANALYTICAL_QUERY, data MUST include:
- query_type: One of: "query_pipeline_analysis", "query_lead_source_performance", "query_conversion_funnel", "query_loan_type_performance", "query_monthly_trends", "query_stale_leads", "query_high_value_opportunities", "query_activity_summary"
- params: Any parameters like date_range_days (default 90), min_amount (default 500000), limit (default 20), stale_days (default 14), months (default 6), days (default 30)

EXAMPLE ANALYTICAL_QUERY RESPONSE:
{
  "intent": "ANALYTICAL_QUERY",
  "explanation": "I'll run that analysis for you.",
  "data": {
    "query_type": "query_monthly_trends",
    "params": {"months": 6}
  }
}

When responding, you MUST return a valid JSON object with these fields:
- intent: The action type from the list above
- explanation: A brief, friendly explanation of what you're going to do
- preview: Object containing preview data for the action (if applicable)
- data: Additional data needed for execution

For EMAIL_CAMPAIGN, preview should include:
- recipients: List of client names/count
- subject: Email subject line
- body: Email content
- template: Template name if using one

For BULK_UPDATE, preview should include:
- records: List of records to update with current and new values
- field: Field being updated
- count: Number of records affected

For VOICEMAIL_DROP, preview should include:
- recipients: List of recipients
- script: The voicemail script content
- scheduled_time: When to send

For PIPELINE_REPORT, preview should include:
- report_type: Type of report
- date_range: Date range covered
- metrics: Key metrics to include

PRE-APPROVAL LETTER HANDLING:
When user asks to send, create, or generate a pre-approval letter:
- "send pre-approval letter for John Smith" → intent: "PRE_APPROVAL_LETTER"
- "create pre-approval for Jane Doe" → intent: "PRE_APPROVAL_LETTER"
- "generate pre-approval letter" → intent: "PRE_APPROVAL_LETTER"
- "send pre-approval to the agent" → intent: "PRE_APPROVAL_LETTER"

CRITICAL - GATHERING MISSING INFORMATION:
For pre-approval letters, you MUST have these required fields:
1. borrower_names - Full name(s) of the borrower(s)
2. loan_amount - Approved loan amount (number)
3. loan_type - Type of loan (Conventional, FHA, VA, USDA, Jumbo)
4. recipient_email - Email address to send the letter to

Optional fields (will use defaults if not provided):
- property_address - Property address or "To Be Determined"
- interest_rate - Interest rate (will use "Market Rate" if not provided)
- expiration_days - Days until letter expires (default 90)
- lead_id - Lead ID if known

IF ANY REQUIRED FIELD IS MISSING:
You MUST ask follow-up questions conversationally to gather the information.
DO NOT refuse to help. Instead, ask for the specific missing information.

EXAMPLE CONVERSATION FLOW:
User: "Send a pre-approval letter for Steve Latterson"
Assistant: "I'll prepare a pre-approval letter for Steve Latterson. I need a few details:

1. **Loan Amount**: What loan amount should I put on the letter?
2. **Loan Type**: What type of loan? (Conventional, FHA, VA, USDA, or Jumbo)
3. **Recipient Email**: Who should I send this letter to?
4. **Property Address**: Do you have a property address, or should I put 'To Be Determined'?"

User: "$450,000 conventional, send it to timothy@perenniaai.com, TBD on property"
Assistant: (Now has all required info, returns PRE_APPROVAL_LETTER intent with data)

SEARCHING FOR LEAD DATA:
When user mentions a name, first search the CRM to find their lead record and pull any available data:
- Lead ID for activity tracking
- Existing loan amount if on file
- Existing loan type if on file
- Email address if on file

Use this data to pre-fill fields and reduce questions needed.

For PRE_APPROVAL_LETTER, preview should include:
- borrower_names: Full name(s) of borrower(s)
- property_address: Property address or "To Be Determined"
- loan_amount: Approved loan amount (number)
- loan_type: Type of loan program
- recipient_email: Email to send the letter to
- interest_rate: (optional) Interest rate
- expiration_days: (optional) Days until expiration
- lead_id: (optional) Lead ID for activity tracking

EXAMPLE PRE_APPROVAL_LETTER RESPONSE:
{
  "intent": "PRE_APPROVAL_LETTER",
  "explanation": "I'll generate and send a pre-approval letter for Steve Latterson to timothy@perenniaai.com.",
  "preview": {
    "borrower_names": "Steve Latterson",
    "property_address": "To Be Determined",
    "loan_amount": 450000,
    "loan_type": "Conventional",
    "recipient_email": "timothy@perenniaai.com",
    "expiration_days": 90
  },
  "data": {
    "lead_id": 123
  }
}

For DAILY_VIEW, data should include:
- tasks: List of today's tasks
- follow_ups: List of follow-ups
- reconciliations: List of reconciliation items
- summary: Overview statistics

For SEARCH, data should include:
- results: List of matching records
- query: The search terms used

Always be helpful, concise, and focus on actionable results. If you can't determine the intent, ask for clarification.
"""


# ============================================================================
# Core Processing Functions
# ============================================================================

async def process_with_claude(
    message: str,
    context: List[Dict[str, str]],
    db: Session,
    user_id: int,
    action_context: Optional[Dict[str, Any]] = None,
    relevant_past: Optional[List[Dict]] = None,
    total_messages: int = 0,
    crm_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Process the message with Claude AI"""

    if not anthropic_client:
        # Return mock response if no API key
        return generate_mock_response(message, db, user_id)

    # Build conversation history - use more context (50 messages for permanent memory)
    messages = []
    for ctx in context[-50:]:  # Keep last 50 messages for better context
        messages.append({
            "role": ctx.get("role", "user"),
            "content": ctx.get("content", "")
        })

    messages.append({
        "role": "user",
        "content": message
    })

    # Build enhanced system prompt with memory context
    system = SYSTEM_PROMPT

    # Add current date to system prompt so AI knows what day it is
    current_date = datetime.now()
    system += f"""

=== CURRENT DATE AND TIME ===
Today is: {current_date.strftime('%B %d, %Y')} ({current_date.strftime('%A')})
Current time: {current_date.strftime('%I:%M %p')}

IMPORTANT: Use this date when evaluating any deadlines, closing dates, or due dates.
- Dates BEFORE today are in the PAST
- If a closing date has already passed, the loan either CLOSED or was DELAYED
- Never say a past closing date is "on track" - it has already passed
=== END DATE INFO ===
"""

    # CHECK IF THIS IS A DAILY_VIEW OR COACHING REQUEST - add explicit summary numbers
    message_lower = message.lower()

    # Coaching mode detection
    is_daily_briefing = "daily briefing" in message_lower or "top 3 priorities" in message_lower
    is_pipeline_audit = "pipeline audit" in message_lower or "bottlenecks" in message_lower
    is_focus_reset = "focus reset" in message_lower or "back on track" in message_lower
    is_next_action = "what should i do next" in message_lower or "priority decision" in message_lower
    is_accountability = "accountability review" in message_lower or "review my performance" in message_lower
    is_tough_love = "tough love" in message_lower or "inefficiencies" in message_lower
    is_teach_process = "teach me the process" in message_lower or "systemic thinking" in message_lower

    # SLA/Turnaround time detection
    is_sla_question = any(phrase in message_lower for phrase in [
        "sla", "turnaround", "turn time", "turntimes", "turn-time",
        "how long", "timeline", "time frame", "timeframe",
        "processing time", "expected time", "target time",
        "service level", "service-level"
    ])

    is_coaching_mode = any([is_daily_briefing, is_pipeline_audit, is_focus_reset, is_next_action,
                           is_accountability, is_tough_love, is_teach_process])

    # INJECT SLA DATA for SLA-related questions
    if is_sla_question:
        sla_data = get_sla_turnaround_times(db)
        sla_measures = sla_data.get("sla_measures", [])

        # Format SLA measures for the system prompt
        sla_text = "\n".join([
            f"- **{m['milestone']}**: {m['target']}" + (f" - {m['description']}" if m.get('description') else "")
            for m in sla_measures
        ])

        performance = sla_data.get("current_performance", {})
        business_hours = sla_data.get("business_hours", {})

        system += f"""

=== SLA TURNAROUND TIMES (USE THIS DATA TO ANSWER THE USER'S QUESTION) ===

YOUR ORGANIZATION'S SLA TARGETS:
{sla_text}

BUSINESS HOURS: {business_hours.get('start', '9 AM')} - {business_hours.get('end', '5 PM')}, {business_hours.get('work_days', 'Monday-Friday')}

CURRENT PERFORMANCE:
- On-Time Rate: {performance.get('on_time_rate', 'N/A')}
- Active Milestones: {performance.get('active_milestones', 0)}
- At Risk: {performance.get('at_risk', 0)}
- Overdue: {performance.get('overdue', 0)}

IMPORTANT: When answering questions about SLAs or turnaround times:
1. Use the EXACT values from the SLA TARGETS above
2. Reference specific milestones by name
3. Mention that these are measured in business hours (Mon-Fri, 9-5)
4. If asked about specific stages, provide the target time for that stage
5. DO NOT give generic industry estimates - use YOUR organization's configured SLAs

=== END SLA DATA ===
"""

    if is_coaching_mode or any(phrase in message_lower for phrase in ["today", "daily", "morning", "need to do", "what should i", "my tasks", "what's on"]):
        # Fetch daily summary data to show exact numbers
        daily_data = get_daily_summary(db, user_id)
        summary = daily_data.get("summary", {})

        # Build task list for display
        task_list = ""
        today = datetime.now().date()  # Define today BEFORE the conditional
        if daily_data.get("tasks"):
            for task in daily_data["tasks"][:10]:
                due_date = task.get("due_date")
                if due_date:
                    try:
                        due_date_obj = datetime.fromisoformat(due_date).date() if isinstance(due_date, str) else due_date
                        if due_date_obj < today:
                            status_label = f"OVERDUE ({due_date_obj.strftime('%m/%d')})"
                        elif due_date_obj == today:
                            status_label = "Due TODAY"
                        else:
                            status_label = f"Due {due_date_obj.strftime('%m/%d')}"
                    except Exception as e:
                        logger.error(f"Error parsing due date: {e}")
                        status_label = "Due date unknown"
                else:
                    status_label = "No due date"
                task_list += f"- [{task.get('priority', 'N/A')}] {task.get('title', 'Untitled')} | {status_label}\n"

        system += f"""

=== DAILY VIEW DATA (YOU MUST USE THESE EXACT NUMBERS) ===
TODAY'S DATE: {today.strftime('%B %d, %Y')} ({today.strftime('%A')})

CRITICAL DATE RULES:
- Any closing date, due date, or deadline BEFORE {today.strftime('%B %d, %Y')} is IN THE PAST
- If a loan's closing date has passed, it either ALREADY CLOSED or was DELAYED - do NOT say "on track"
- Only say "on track" for FUTURE dates that haven't passed yet
- For past dates, say "was scheduled for [date]" or "should have closed on [date]"

ACTUAL CRM DATA FOR TODAY:
- Active Leads: {summary.get('active_leads', 0)}
- Loans in Pipeline: {summary.get('loans_in_pipeline', 0)}
- Pipeline Volume: {summary.get('pipeline_volume', '$0')}
- Total Tasks: {summary.get('total_tasks', 0)}
- Overdue Tasks: {summary.get('overdue_tasks', 0)}
- Unread Messages: {summary.get('unread_messages', 0)}

LEAD STATUS BREAKDOWN:
{chr(10).join([f"- {status}: {count}" for status, count in summary.get('lead_status_breakdown', {}).items()])}

LOAN STAGE BREAKDOWN:
{chr(10).join([f"- {stage}: {count}" for stage, count in summary.get('loan_stage_breakdown', {}).items()])}

OUTSTANDING TASKS:
{task_list if task_list else "No tasks found"}

TASK PRESENTATION RULES:
- If there are {summary.get('overdue_tasks', 0)} overdue tasks: START with "You have {summary.get('overdue_tasks', 0)} overdue tasks that need immediate attention"
- If total_tasks > 0: Say "You have {summary.get('total_tasks', 0)} outstanding tasks" NOT "no tasks due today"
- ALWAYS prioritize overdue tasks first in your response
- DO NOT say "no tasks" if total_tasks > 0 or overdue_tasks > 0
- SHOW the actual tasks from the OUTSTANDING TASKS list above
=== END DAILY VIEW DATA ===
"""

        # Add coaching mode specific instructions
        if is_daily_briefing:
            system += """

=== COACHING MODE: DAILY BRIEFING ===
The user wants their TOP 3 PRIORITIES for today. Structure your response as:
1. Identify the 3 most critical items from tasks and follow-ups
2. ALWAYS include the BORROWER/CLIENT NAME for each task (from the title which includes "- Borrower Name")
3. For each priority, explain WHY it's urgent
4. Provide specific action steps
5. Keep it focused and actionable - no fluff

IMPORTANT: Each priority MUST include the borrower/client name. Never say just "Review Loan Documents" -
say "Review Loan Documents - John Smith" or "Review Loan Documents for John Smith".
=== END COACHING MODE ===
"""
        elif is_pipeline_audit:
            system += """

=== COACHING MODE: PIPELINE AUDIT ===
The user wants to identify BOTTLENECKS and STALLED DEALS. Structure your response as:
1. Identify deals that haven't moved stages in 7+ days
2. Call out any missing documents or pending items
3. Highlight conversion issues between stages
4. Provide specific recommendations to unstick each bottleneck
Be direct and specific - name names and amounts.
=== END COACHING MODE ===
"""
        elif is_focus_reset:
            system += """

=== COACHING MODE: FOCUS RESET ===
The user is scattered and needs to refocus. Structure your response as:
1. List ONLY the most critical items that need immediate attention
2. Cut through the noise - ignore low-priority items
3. Provide a clear sequence: do THIS first, THEN this, THEN this
4. Be calm but direct - help them see the path forward
=== END COACHING MODE ===
"""
        elif is_next_action:
            system += """

=== COACHING MODE: WHAT SHOULD I DO NEXT ===
The user needs priority decision guidance. Structure your response as:
1. Look at their current workload and identify the single most impactful action
2. Explain why this should be next (urgency, value, dependencies)
3. Provide the specific next step to take
4. If there are competing priorities, explain the trade-offs
=== END COACHING MODE ===
"""
        elif is_accountability:
            # Fetch additional accountability metrics
            main = get_main_module()
            Task = main.Task
            Lead = main.Lead

            # Get all leads for this user (needed for accountability metrics)
            all_leads = db.query(Lead).filter(Lead.owner_id == user_id).all()
            total_leads = len(all_leads)

            # Get all tasks for this user
            all_tasks = db.query(Task).filter(
                Task.owner_id == user_id,
                Task.status != 'completed'
            ).all()

            # Get loan data
            total_loans = summary.get('loans_in_pipeline', 0)
            total_pipeline_value_str = summary.get('pipeline_volume', '$0')

            # Get completed tasks this month
            month_start = today.replace(day=1)
            completed_this_month = db.query(Task).filter(
                Task.owner_id == user_id,
                Task.status == 'completed',
                Task.updated_at >= month_start
            ).count()

            # Get total tasks assigned this month
            total_tasks_this_month = db.query(Task).filter(
                Task.owner_id == user_id,
                Task.created_at >= month_start
            ).count()

            # Calculate task completion rate
            completion_rate = (completed_this_month / total_tasks_this_month * 100) if total_tasks_this_month > 0 else 0

            # Get leads that have progressed stages this month
            leads_progressed = 0
            leads_stalled = 0
            stalled_lead_names = []
            seven_days_ago = today - timedelta(days=7)

            for lead in all_leads:
                if lead.updated_at and lead.updated_at.date() < seven_days_ago:
                    leads_stalled += 1
                    if len(stalled_lead_names) < 5:
                        stalled_lead_names.append(lead.name or "Unknown")
                elif lead.updated_at and lead.updated_at.date() >= month_start:
                    leads_progressed += 1

            # Get overdue task count
            overdue_count = len([t for t in all_tasks if t.due_date and t.due_date.date() < today])

            system += f"""

=== COACHING MODE: ACCOUNTABILITY REVIEW ===
The user wants honest performance feedback. You MUST include these specific metrics:

TASK PERFORMANCE:
- Tasks Completed This Month: {completed_this_month}
- Total Tasks This Month: {total_tasks_this_month}
- Completion Rate: {completion_rate:.0f}%
- Overdue Tasks: {overdue_count}

LEAD MANAGEMENT:
- Total Leads: {total_leads}
- Leads Progressed This Month: {leads_progressed}
- Leads Stalled (no activity 7+ days): {leads_stalled}
{f'- Stalled Leads: {", ".join(stalled_lead_names)}' if stalled_lead_names else ''}

PIPELINE STATUS:
- Active Loans: {total_loans}
- Pipeline Value: {total_pipeline_value_str}

Structure your response as:

**Performance Summary**
- Start with overall assessment (Good/Needs Improvement/Critical)
- Use the exact metrics above

**What's Working**
- Highlight positive metrics (completion rate > 70%, leads progressing, etc.)

**Areas Needing Attention**
- Call out low completion rates, overdue tasks, stalled leads BY NAME
- Be specific with numbers - don't soften the truth

**Action Items**
- List 3-5 specific actions they should take THIS WEEK
- Prioritize by impact

Be honest and direct - they asked for accountability. If the metrics are poor, say so clearly.
=== END COACHING MODE ===
"""
        elif is_tough_love:
            system += """

=== COACHING MODE: TOUGH LOVE ===
The user wants you to be DIRECT about inefficiencies. Structure your response as:
1. No sugar-coating - call out exactly what's not working
2. Point to specific leads, deals, or tasks that are being neglected
3. Highlight patterns of behavior that are hurting results
4. Be blunt about the cost of inaction (lost revenue, missed opportunities)
5. End with "Here's what you need to do TODAY"
They asked for tough love - deliver it respectfully but firmly.
=== END COACHING MODE ===
"""
        elif is_teach_process:
            system += """

=== COACHING MODE: TEACH ME THE PROCESS ===
The user wants to learn systemic thinking. Structure your response as:
1. Explain the optimal workflow for their current situation
2. Show how different pipeline stages connect
3. Teach them to identify leading vs lagging indicators
4. Provide frameworks they can apply repeatedly
5. Use their actual data as examples
This is educational - help them build better habits, not just solve today's problem.
=== END COACHING MODE ===
"""

    # ADD COMPLETE CRM DATA CONTEXT
    if crm_context:
        system += "\n\n=== COMPLETE CRM DATA (You have full access to all this data) ===\n"
        system += CRMContextService.format_complete_context_for_claude(crm_context)

        # Add detailed data for specific queries
        leads = crm_context.get("leads", {})
        if leads.get("recent_leads"):
            system += "\n\nDETAILED LEAD DATA:\n"
            for lead in leads["recent_leads"][:20]:
                system += f"- {lead['name']} | {lead['status']} | {lead.get('loan_type', 'N/A')} | ${lead.get('loan_amount', 0):,.0f} | {lead.get('email', 'N/A')}\n"

        loans = crm_context.get("loans", {})
        if loans.get("recent_loans"):
            system += "\n\nDETAILED LOAN/DEAL DATA:\n"
            for loan in loans["recent_loans"][:20]:
                system += f"- {loan['borrower_name']} | {loan['stage']} | {loan.get('loan_type', 'N/A')} | ${loan.get('loan_amount', 0):,.0f} | {loan.get('property_address', 'N/A')}\n"

        tasks = crm_context.get("tasks", {})
        if tasks.get("todays_tasks"):
            system += "\n\nTODAY'S TASKS:\n"
            for task in tasks["todays_tasks"]:
                system += f"- [{task.get('priority', 'N/A')}] {task['title']} | {task.get('status', 'N/A')}\n"

        mum = crm_context.get("mum_clients", {})
        if mum.get("clients"):
            system += "\n\nMUM CLIENTS:\n"
            for client in mum["clients"][:15]:
                system += f"- {client['name']} | ${client.get('loan_amount', 0):,.0f} | {client.get('interest_rate', 0)}% | Next review: {client.get('next_review_date', 'N/A')}\n"

        partners = crm_context.get("referral_partners", {})
        if partners.get("partners"):
            system += "\n\nREFERRAL PARTNER PERFORMANCE:\n"

            # Highlight most profitable first
            most_profitable = partners.get("most_profitable")
            if most_profitable:
                system += f"*** MOST PROFITABLE: {most_profitable['name']} - ${most_profitable['revenue']:,.0f} from {most_profitable['deals']} closed deals ***\n\n"

            system += "All Partners (ranked by revenue):\n"
            for i, partner in enumerate(partners["partners"][:10], 1):
                system += f"{i}. {partner['name']}"
                if partner.get('company'):
                    system += f" ({partner['company']})"
                system += f"\n   - Total Leads: {partner.get('total_leads', 0)}\n"
                system += f"   - Closed Deals: {partner.get('closed_deals', 0)}\n"
                system += f"   - Total Revenue: ${partner.get('total_revenue', 0):,.0f}\n"
                system += f"   - Avg Deal Size: ${partner.get('avg_deal_size', 0):,.0f}\n"
                system += f"   - Close Rate: {partner.get('close_rate_pct', 0):.0f}%\n\n"

        system += "\n=== END CRM DATA ===\n"

    # ADD PATTERN ANALYSIS & INSIGHTS
    try:
        patterns = PatternAnalyzer.analyze_user_patterns(db, user_id)
        if patterns:
            system += PatternAnalyzer.format_patterns_for_claude(patterns)
    except Exception as e:
        logger.warning(f"Failed to add pattern analysis: {e}")

    # ADD PERMANENT MEMORY CONTEXT
    if total_messages > 0:
        system += f"""

PERMANENT MEMORY STATUS:
- You have had {total_messages} total messages with this user
- You have COMPLETE MEMORY of everything we've discussed
- When user references "yesterday", "last week", or past conversations, check the context below
- ALWAYS use your memory - never claim to not remember something from our history
"""

    # Add relevant past conversations if available
    if relevant_past and len(relevant_past) > 0:
        system += "\n\nRELEVANT PAST CONVERSATIONS (from your permanent memory):\n"
        for msg in relevant_past:
            content_preview = msg.get('content', '')[:300]
            system += f"[{msg.get('timestamp', 'unknown')}] {msg.get('role', 'unknown')}: {content_preview}...\n"

    # Add action context
    if action_context:
        action_summary = "\n\nRECENT ACTIONS IN THIS CONVERSATION:\n"
        for action_id, action_data in action_context.items():
            intent = action_data.get('intent', 'unknown')
            status = action_data.get('status', 'unknown')
            preview = action_data.get('preview', {})
            action_summary += f"- Action {action_id}: {intent} ({status})\n"
            if preview:
                if intent == 'EMAIL_CAMPAIGN':
                    action_summary += f"  Subject: {preview.get('subject', 'N/A')}\n"
                    action_summary += f"  Body: {preview.get('body', 'N/A')[:200]}...\n"
                elif intent == 'BULK_UPDATE':
                    action_summary += f"  Field: {preview.get('field', 'N/A')}, Count: {preview.get('count', 'N/A')}\n"
        system += action_summary

    # Check circuit breaker before making AI call
    if not ai_circuit_breaker.can_execute():
        logger.warning("AI Circuit breaker is OPEN - using fallback")
        return ai_circuit_breaker.get_fallback()

    start_time = time.time()
    function_calls_made = 0

    try:
        # Log the request
        logger.info(f"AI Request - User ID: {user_id}, Message: {message[:100]}...")

        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=AI_CONFIG["max_tokens"],
            temperature=AI_CONFIG["temperature"],  # Deterministic responses
            system=system,
            messages=messages
        )

        # Log the response
        logger.info(f"AI Response - Stop reason: {response.stop_reason}")

        # Record success in circuit breaker
        ai_circuit_breaker.record_success()

        # Parse Claude's response
        response_text = response.content[0].text
        logger.info(f"AI Response text preview: {response_text[:200]}...")

        # Try to extract JSON from the response
        try:
            # Find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)

                # OVERRIDE INTENT FOR COACHING MODES
                # Force DAILY_VIEW for coaching prompts regardless of Claude's classification
                message_lower = message.lower()
                coaching_keywords = [
                    "daily briefing", "top 3 priorities",
                    "pipeline audit", "bottlenecks", "stalled deals",
                    "focus reset", "back on track", "get focused",
                    "what should i do next", "priority decision",
                    "accountability review", "review my performance",
                    "tough love", "inefficiencies", "call out",
                    "teach me the process", "systemic thinking"
                ]
                is_coaching = any(keyword in message_lower for keyword in coaching_keywords)

                if is_coaching and result.get("intent") != "DAILY_VIEW":
                    logger.info(f"Overriding intent from {result.get('intent')} to DAILY_VIEW for coaching prompt")
                    result["intent"] = "DAILY_VIEW"

                # INJECT REAL CRM DATA for DAILY_VIEW
                if result.get("intent") == "DAILY_VIEW":
                    daily_data = get_daily_summary(db, user_id)
                    # Merge Claude's response with actual CRM data
                    if "data" not in result:
                        result["data"] = {}
                    result["data"]["tasks"] = daily_data.get("tasks", [])
                    result["data"]["follow_ups"] = daily_data.get("follow_ups", [])
                    result["data"]["reconciliations"] = daily_data.get("reconciliations", [])
                    # Use Claude's summary if it has better formatting, but include all our data
                    if "summary" in result["data"]:
                        result["data"]["summary"].update({
                            "lead_status_breakdown": daily_data["summary"].get("lead_status_breakdown", {}),
                            "loan_stage_breakdown": daily_data["summary"].get("loan_stage_breakdown", {}),
                            "unread_messages": daily_data["summary"].get("unread_messages", 0),
                            "mum_clients": daily_data["summary"].get("mum_clients", 0),
                        })
                    else:
                        result["data"]["summary"] = daily_data.get("summary", {})

                    # VALIDATION: Check for placeholder values in AI response
                    actual_leads = daily_data["summary"].get("active_leads", 0)
                    actual_loans = daily_data["summary"].get("loans_in_pipeline", 0)
                    actual_tasks = daily_data["summary"].get("total_tasks", 0)
                    actual_overdue = daily_data["summary"].get("overdue_tasks", 0)
                    explanation = result.get("explanation", "").lower()

                    # Check for incorrect "no tasks" messaging
                    no_tasks_phrases = ["no tasks", "currently have no tasks", "have no tasks", "0 tasks", "no outstanding tasks"]
                    has_incorrect_no_tasks = any(phrase in explanation for phrase in no_tasks_phrases)

                    if has_incorrect_no_tasks and actual_tasks > 0:
                        logger.warning(f"AI said 'no tasks' but actual count is {actual_tasks} (overdue: {actual_overdue})")
                        # Build correct task summary
                        task_summary = f"You have {actual_tasks} outstanding tasks"
                        if actual_overdue > 0:
                            task_summary = f"You have {actual_overdue} overdue tasks that need immediate attention"

                        # Get first few tasks to show
                        task_items = daily_data.get("tasks", [])[:3]
                        task_list_text = "\n\n**Top Priority Tasks:**\n"
                        for task in task_items:
                            task_list_text += f"- [{task.get('priority', 'N/A')}] {task.get('title', 'Untitled')}\n"

                        result["explanation"] = f"{task_summary}.{task_list_text}\n\nWould you like me to help you prioritize or create a schedule for these tasks?"

                    if "0 active leads" in explanation and actual_leads > 0:
                        logger.warning(f"AI returned placeholder '0 leads' but actual count is {actual_leads}")
                        # Override the explanation with correct data
                        result["explanation"] = f"Here's your daily overview. You have {actual_leads} active leads and {actual_loans} loans in pipeline ({daily_data['summary'].get('pipeline_volume', '$0')})."

                    if "0 loans in pipeline" in explanation and actual_loans > 0:
                        logger.warning(f"AI returned placeholder '0 loans' but actual count is {actual_loans}")

                    logger.info(f"DAILY_VIEW response validated - Leads: {actual_leads}, Loans: {actual_loans}, Tasks: {actual_tasks}")

                # INJECT QUERY RESULTS for ANALYTICAL_QUERY
                if result.get("intent") == "ANALYTICAL_QUERY":
                    query_type = result.get("data", {}).get("query_type", "")
                    params = result.get("data", {}).get("params", {})

                    if query_type:
                        query_result = execute_analytical_query(db, user_id, query_type, params)
                        result["data"]["query_result"] = query_result
                        # Append formatted results to explanation
                        if query_result.get("success"):
                            result["explanation"] += "\n\n" + query_result.get("formatted_text", "")
                        logger.info(f"ANALYTICAL_QUERY executed: {query_type}, success={query_result.get('success')}")

                # INJECT MARKET DATA for MARKET_INTELLIGENCE
                if result.get("intent") == "MARKET_INTELLIGENCE":
                    lock_days = result.get("data", {}).get("lock_days", 30)
                    market_data = get_market_intelligence(lock_days)
                    result["data"]["market_data"] = market_data

                    # Format market data for explanation
                    rates = market_data.get("current_rates", {})
                    conditions = market_data.get("market_conditions", {})
                    recommendation = market_data.get("rate_lock_recommendation", {})

                    market_summary = f"""

**Current Market Conditions:**
- 30-Year Fixed: {rates.get('30yr_fixed', 'N/A')}%
- 15-Year Fixed: {rates.get('15yr_fixed', 'N/A')}%
- 10-Year Treasury: {market_data.get('treasury_yields', {}).get('10yr', 'N/A')}%
- Market Volatility: {conditions.get('volatility', 'Unknown')} (VIX: {conditions.get('vix', 'N/A')})
- Market Score: {conditions.get('market_score', 'N/A')}/100

**Rate Lock Recommendation: {recommendation.get('overall', 'CAUTIOUS')}**

{recommendation.get('guidance', '')}
"""
                    result["explanation"] += market_summary
                    logger.info(f"MARKET_INTELLIGENCE executed: lock_days={lock_days}, recommendation={recommendation.get('overall')}")

                # Log metrics for successful response
                execution_time = (time.time() - start_time) * 1000
                AIMetrics.log_interaction(
                    user_id=user_id,
                    request_message=message,
                    response=result,
                    execution_time_ms=execution_time,
                    success=True,
                    function_calls_made=function_calls_made
                )

                return result
        except json.JSONDecodeError:
            pass

        # If no JSON found, create a general response
        result = {
            "intent": "GENERAL_QUERY",
            "explanation": response_text,
            "data": {}
        }

        # Log metrics
        execution_time = (time.time() - start_time) * 1000
        AIMetrics.log_interaction(
            user_id=user_id,
            request_message=message,
            response=result,
            execution_time_ms=execution_time,
            success=True,
            function_calls_made=function_calls_made
        )

        return result

    except Exception as e:
        # Record failure in circuit breaker
        ai_circuit_breaker.record_failure()

        # Log metrics for failed response
        execution_time = (time.time() - start_time) * 1000
        AIMetrics.log_interaction(
            user_id=user_id,
            request_message=message,
            response={"intent": "ERROR"},
            execution_time_ms=execution_time,
            success=False,
            error=str(e)
        )

        logger.error(f"Claude API error: {str(e)}")
        return generate_mock_response(message, db, user_id)


def generate_mock_response(message: str, db: Session, user_id: int) -> Dict[str, Any]:
    """Generate a mock response for demo purposes"""
    main = get_main_module()
    Lead = main.Lead

    message_lower = message.lower()

    if "today" in message_lower or "daily" in message_lower or "morning" in message_lower:
        summary = get_daily_summary(db, user_id)
        return {
            "intent": "DAILY_VIEW",
            "explanation": "Here's your daily overview:",
            "data": summary
        }

    elif "email" in message_lower or "send" in message_lower:
        # Get some sample clients
        clients = db.query(Lead).filter(Lead.owner_id == user_id).limit(5).all()
        return {
            "intent": "EMAIL_CAMPAIGN",
            "explanation": "I'll prepare an email campaign for you.",
            "preview": {
                "recipients": [f"{c.first_name} {c.last_name}" for c in clients],
                "count": len(clients),
                "subject": "Important Update from Your Mortgage Team",
                "body": "Dear Client,\n\nWe wanted to reach out with some important information about your loan.\n\nBest regards,\nYour Mortgage Team"
            }
        }

    elif "search" in message_lower or "find" in message_lower:
        # Extract search term (simple approach)
        words = message.split()
        search_term = words[-1] if len(words) > 1 else "client"
        results = search_records(db, user_id, search_term)
        return {
            "intent": "SEARCH",
            "explanation": f"Here are the search results for '{search_term}':",
            "data": results
        }

    elif "report" in message_lower or "pipeline" in message_lower:
        return {
            "intent": "PIPELINE_REPORT",
            "explanation": "I'll generate a pipeline report for you.",
            "preview": {
                "report_type": "Pipeline Analysis",
                "date_range": "Last 30 days",
                "metrics": ["Total Loans", "Conversion Rate", "Average Loan Size", "Stage Distribution"]
            }
        }

    elif "voicemail" in message_lower:
        clients = db.query(Lead).filter(Lead.owner_id == user_id).limit(3).all()
        return {
            "intent": "VOICEMAIL_DROP",
            "explanation": "I'll set up a ringless voicemail campaign.",
            "preview": {
                "recipients": [f"{c.first_name} {c.last_name}" for c in clients],
                "script": "Hi, this is a quick message from your mortgage team. We have some important updates about current rates. Please call us back at your convenience.",
                "scheduled_time": "Immediately"
            }
        }

    else:
        return {
            "intent": "GENERAL_QUERY",
            "explanation": f"I understand you're asking about: {message}. How can I help you further?",
            "data": {}
        }


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/process-command", response_model=AICommandResponse)
async def process_command(
    request: AICommandRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dependency)
):
    """
    Process a natural language command and return intent with preview.
    """
    # Get current user ID from authenticated user
    if not current_user or not hasattr(current_user, 'id'):
        raise HTTPException(status_code=401, detail="Authentication required")
    current_user_id = current_user.id

    # Per-user rate limiting (30 req/min) — defense-in-depth for LLM API quota protection
    ai_rate_limiter.check(current_user_id)

    # Get or create session ID for permanent memory
    session_id = request.session_id or str(uuid.uuid4())

    try:
        # 1. SAVE USER MESSAGE TO PERMANENT MEMORY
        try:
            ConversationMemory.save_message(
                db=db,
                user_id=current_user_id,
                session_id=session_id,
                role='user',
                content=request.message
            )
        except Exception as mem_error:
            logger.warning(f"Failed to save user message to memory: {mem_error}")

        # 2. GET FULL CONTEXT FROM PERMANENT MEMORY
        context = ConversationMemory.get_full_context(
            db=db,
            user_id=current_user_id,
            current_message=request.message
        )

        # 3. GET FULL CRM DATA CONTEXT (with Redis caching for performance)
        crm_context = await CRMContextService.get_full_crm_context_cached(db, current_user_id)

        # 4. BUILD ENHANCED CONTEXT FOR CLAUDE
        # Combine permanent memory with current session context
        combined_context = context['recent_messages'] if context['recent_messages'] else request.conversation_context

        # Process with Claude AI - pass full context including action history and CRM data
        result = await process_with_claude(
            request.message,
            combined_context,
            db,
            current_user_id,
            request.action_context,  # Include action context for memory
            context.get('relevant_past', []),
            context.get('total_messages', 0),
            crm_context  # Include full CRM data
        )

        # Generate action ID if this is an actionable command
        action_id = None
        if result.get("intent") in ["EMAIL_CAMPAIGN", "BULK_UPDATE", "VOICEMAIL_DROP"]:
            action_id = str(uuid.uuid4())
            # Cache the action for later execution
            action_cache[action_id] = {
                "intent": result["intent"],
                "preview": result.get("preview"),
                "user_id": current_user_id,
                "created_at": datetime.now().isoformat(),
                "session_id": session_id
            }

            # 4. SAVE ACTION TO PERMANENT MEMORY
            try:
                ConversationMemory.save_action(
                    db=db,
                    user_id=current_user_id,
                    action_id=action_id,
                    action_type=result["intent"],
                    preview_data=result.get("preview", {})
                )
            except Exception as action_error:
                logger.warning(f"Failed to save action to memory: {action_error}")

        # 5. SAVE ASSISTANT RESPONSE TO PERMANENT MEMORY
        try:
            ConversationMemory.save_message(
                db=db,
                user_id=current_user_id,
                session_id=session_id,
                role='assistant',
                content=result.get("explanation", ""),
                action_id=action_id,
                action_data=result.get("preview")
            )
        except Exception as mem_error:
            logger.warning(f"Failed to save assistant message to memory: {mem_error}")

        return AICommandResponse(
            intent=result.get("intent", "GENERAL_QUERY"),
            explanation=result.get("explanation", ""),
            preview=result.get("preview"),
            action_id=action_id,
            data=result.get("data"),
            session_id=session_id
        )

    except Exception as e:
        logger.error(f"Error processing command: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/execute-action", response_model=ActionExecuteResponse)
async def execute_action(
    request: ActionExecuteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dependency)
):
    """
    Execute a previously previewed action.
    """
    # Require authenticated user
    if not current_user or not hasattr(current_user, 'id'):
        raise HTTPException(status_code=401, detail="Authentication required")
    current_user_id = current_user.id

    # Per-user rate limiting — shares the same limiter as process-command
    ai_rate_limiter.check(current_user_id)

    try:
        # Get cached action
        action_data = action_cache.get(request.action_id)
        if not action_data:
            raise HTTPException(status_code=404, detail="Action not found or expired")

        # Verify ownership
        if action_data["user_id"] != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized to execute this action")

        intent = action_data["intent"]
        preview = action_data.get("preview", {})
        modifications = request.modifications
        session_id = request.session_id or action_data.get("session_id")

        # Execute based on intent
        if intent == "EMAIL_CAMPAIGN":
            result = await execute_email_campaign(
                db, current_user_id, preview, modifications, background_tasks
            )
        elif intent == "BULK_UPDATE":
            result = await execute_bulk_update(
                db, current_user_id, preview, modifications
            )
        elif intent == "VOICEMAIL_DROP":
            result = await execute_voicemail_drop(
                db, current_user_id, preview, modifications, background_tasks
            )
        elif intent == "PRE_APPROVAL_LETTER":
            result = await execute_pre_approval_letter(
                db, current_user_id, preview, modifications, background_tasks
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action type: {intent}")

        # UPDATE ACTION STATUS IN PERMANENT MEMORY
        try:
            ConversationMemory.update_action_status(
                db=db,
                action_id=request.action_id,
                status='executed' if result.get('message') else 'failed',
                execution_data=result
            )
        except Exception as mem_error:
            logger.warning(f"Failed to update action status in memory: {mem_error}")

        # SAVE EXECUTION RESULT TO CONVERSATION
        if session_id:
            try:
                ConversationMemory.save_message(
                    db=db,
                    user_id=current_user_id,
                    session_id=session_id,
                    role='assistant',
                    content=f"Action executed: {result.get('message', 'Success')}"
                )
            except Exception as mem_error:
                logger.warning(f"Failed to save execution result to memory: {mem_error}")

        # Remove from cache after execution
        del action_cache[request.action_id]

        return ActionExecuteResponse(
            success=True,
            message=result.get("message", "Action executed successfully"),
            result=result
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing action: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
