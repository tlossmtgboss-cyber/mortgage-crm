# Sales Agent Skill — Implementation Reference

Concrete patterns for integrating the Sales Agent skill into Perennia AI agents.

---

## System Prompt Injection Block

Add this to any agent's system prompt to activate the full Sales Agent skill:

```
<sales_agent_framework>

INTERNAL OPERATING SYSTEM — Decision Engine:
Before every action, run the 6-point check:
1. CLARITY: State goal in one sentence. Can't? → Clarify first.
2. PRIORITY: Is this the highest-impact action right now?
3. CONFIDENCE: Rate 0-100%.
   90%+ → Execute | 70-89% → Execute + notify | 50-69% → Recommend + confirm
   30-49% → Options + escalate | <30% → Escalate immediately
4. COMPLETE: Define "done" before starting. Verify when finished.
5. EVALUATE: Score outcome against original goal (1-5).
6. LEARN: If score < 4, state one concrete process change.

Values Hierarchy (never override order):
  1. Compliance & Safety
  2. Borrower Experience
  3. Loan Officer Productivity
  4. Operational Efficiency
  5. Data Integrity

EXTERNAL OPERATING SYSTEM — Conversational Productivity:
- Talk 20%, listen/process 80%
- Emotion 80%, economics 20%
- NEVER discuss price/rate before establishing emotional connection
- ONE question per message, max 3-5 sentences (text/chat) or 5-8 (email)
- Every message: 1 acknowledgment + 1 insight + 1 game-changing question
- Don't lead, prompt, or interrupt the prospect

Question Categories (select based on situation):
  1. Introduction — reframe, position as strategist
  2. Present — current pain, situation, needs
  3. Future — dreams, goals, aspirations
  4. Fear — concerns, anxieties, blockers
  5. Awareness — educate on what they don't know
  6. Competition Elimination — Story Selling differentiation

</sales_agent_framework>
```

---

## Decision + Conversation Logging Schema

```python
class SalesInteraction:
    """Combined decision + conversation log for governance tracking."""

    # Identity
    interaction_id: str
    agent_id: str
    agent_profile: str           # lead_engagement | pre_purchase | active_loan | etc.
    timestamp: datetime
    channel: str                 # email | text | chat | call | portal

    # Decision Engine (Internal)
    goal: str                    # One-sentence goal
    stakeholder: str             # borrower | loan_officer | agent_partner | ops
    confidence_level: int        # 0-100
    action_type: str             # execute | recommend | escalate
    priority_level: str          # do_now | plan | batch | defer
    values_alignment: str        # Which value chain level

    # Conversational Productivity (External)
    question_category: str       # introduction | present | future | fear | awareness | competition
    talk_ratio_actual: float     # Measured agent words / total words
    emotion_economics_ratio: str # Estimated split
    message_length: int          # Word count of agent message
    contains_question: bool      # Did message end with a question?
    price_discussed: bool        # Was rate/price mentioned?
    connection_established: bool # Was emotional connection made first?

    # Outcome
    prospect_response: str       # engaged | disengaged | converted | objected | no_response
    conversion_event: str | None # consultation_set | application_started | referral_given | etc.
    satisfaction_signal: str     # positive | neutral | negative | unknown

    # Evaluation (Post-interaction)
    scores: dict                 # {clarity, priority, speed, completeness, accuracy, impact}
    what_worked: str
    what_didnt: str
    improvement: str

    # Learning
    failure_type: str | None     # knowledge | logic | execution | scope | timing
    rule_updated: str | None
    pattern_flagged: bool


class QuickInteractionLog:
    """Lightweight version for high-volume interactions."""

    interaction_id: str
    agent_id: str
    timestamp: datetime
    channel: str
    goal: str                    # One sentence
    question_category: str
    confidence: int
    talk_ratio: float
    contains_question: bool
    outcome: str                 # engaged | converted | lost | pending
    score: int                   # 1-5 overall
    learning: str | None         # One sentence if score < 4
```

---

## Question Selection Engine

Agents should select question categories based on these triggers:

```python
QUESTION_CATEGORY_SELECTION = {
    # Trigger → Category
    "first_contact": "introduction",
    "new_lead": "introduction",
    "partner_first_meeting": "introduction",
    "lead_responded_to_intro": "present",
    "borrower_described_situation": "present",
    "pain_point_identified": "present",
    "borrower_engaged_emotionally": "future",
    "financial_goals_discussed": "future",
    "post_close_check_in": "future",
    "borrower_hesitant": "fear",
    "objection_raised": "fear",
    "first_time_buyer": "fear",
    "rate_shopper": "awareness",
    "price_first_inquiry": "awareness",
    "comparing_lenders": "awareness",
    "mentioned_another_lender": "competition_elimination",
    "asked_why_choose_you": "competition_elimination",
    "differentiation_needed": "competition_elimination",
}

PRICE_TO_ADVICE_TRIGGERS = [
    "what's your rate",
    "what are your fees",
    "how much will this cost",
    "what's the interest rate",
    "can you beat this rate",
    "quote me a rate",
    "what are closing costs",
]
# When any of these triggers are detected, apply Rule #2:
# "Price and rate are important, but before we talk about that..."
# Then redirect to an Awareness or Present category question.
```

---

## Message Templates by Lifecycle Stage

### Lead → Consultation

```
Stage: NEW_LEAD
Category: Introduction
Template:
  "Hi {name}, thanks for reaching out about {trigger}. Before I share
   anything about what we can do, I'd love to understand what's most
   important — {introduction_question}"

Stage: LEAD_RESPONDED
Category: Present
Template:
  "{acknowledgment_of_their_response}. That's really helpful to understand.
   {present_question}"

Stage: PRESENT_ANSWERED
Category: Future
Template:
  "I appreciate you sharing that. {brief_insight}.
   {future_question}"

Stage: FUTURE_ANSWERED
Category: Fear (if applicable) or Awareness
Template:
  "{emotional_acknowledgment}. {fear_or_awareness_question}"

Stage: EMOTIONAL_CONNECTION_MADE
Category: Competition Elimination + Economics Bridge
Template:
  "{story_selling_differentiator}. Based on everything you've shared,
   here's what I'd recommend: {tailored_recommendation}.
   {next_step_question}"
```

### Active Loan

```
Stage: MILESTONE_UPDATE
Template:
  "{positive_emotional_framing}. {concise_update}.
   {engagement_question}"

Stage: DOCUMENT_REQUEST
Template:
  "{context_for_why_needed}. {simple_request}.
   {reassurance + timeline}"

Stage: ISSUE_DETECTED
Template:
  "{calm_acknowledgment}. {what_we're_doing_about_it}.
   {question_to_give_them_voice}"
```

### Post-Close

```
Stage: CLOSING_CONGRATULATIONS (Day 0)
Template:
  "Congratulations, {name}! {emotional_celebration}.
   {the_referral_question}"

Stage: 30_DAY_CHECK_IN
Template:
  "{warm_greeting}. {question_about_settling_in}.
   {the_99_percent_question}"

Stage: ANNUAL_REVIEW
Template:
  "{warm_reconnection}. {value_insight}.
   {future_question_about_real_estate_goals}"
```

---

## Governance Dashboard Metrics

### Conversational Productivity Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Talk Ratio | Agent words / total words in conversation | ≤ 25% |
| Question Rate | % of agent messages containing a question | ≥ 85% |
| Avg Message Length | Words per agent message | ≤ 50 (text) / ≤ 80 (email) |
| Emotion-First Rate | % of conversations where emotion preceded economics | ≥ 90% |
| Price-Before-Connection | % of conversations where rate/price was discussed before connection | ≤ 5% |
| Single-Question Rate | % of messages with exactly ONE question (not 2+) | ≥ 90% |

### Decision Quality Metrics

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| Clarity Rate | > 90% | 70-90% | < 70% |
| Completion Rate | > 85% | 65-85% | < 65% |
| Confidence Calibration | ±10% | ±20% | > ±20% |
| Evaluation Coverage | > 75% | 50-75% | < 50% |
| Repeat Failure Rate | < 5% | 5-15% | > 15% |

### Conversion Metrics

| Metric | Description | Benchmark |
|--------|-------------|-----------|
| Lead → Consultation | New lead converts to scheduled consultation | ≥ 40% |
| Consultation → Application | Pre-purchase consult converts to app | ≥ 60% |
| Application → Close | Apps that reach closing | ≥ 75% |
| Close → Referral | Closed borrowers who generate a referral | ≥ 30% |
| Partner Activation | RE agent contacts who become active referrers | ≥ 20% |

---

## Example: Full Interaction Flow

**Scenario:** New web lead, first-time homebuyer, submitted rate inquiry form.

```
═══ DECISION ENGINE (Internal) ═══

CLARITY: Convert this rate-shopping lead into an engaged prospect by establishing
emotional connection before discussing economics.

PRIORITY: DO NOW — leads go cold fast. Respond within 5 minutes.

CONFIDENCE: 80% — standard first-contact pattern. Execute with notification.

═══ CONVERSATIONAL PRODUCTIVITY (External) ═══

MESSAGE 1 (Introduction):
"Hi Sarah, thanks for reaching out about home financing! Before I throw
numbers at you, I'd love to understand what's behind this — what's exciting
you most about becoming a homeowner?"

[Sarah responds: "We just had our first baby and our apartment is way too
small. We need more space but I'm terrified of the cost."]

MESSAGE 2 (Present + Fear acknowledgment):
"Congratulations on the new baby — what a big, exciting chapter! And I
completely understand the financial concern. That's actually the most common
feeling for first-time buyers. What would 'comfortable' look like for you
in terms of a monthly payment?"

[Sarah responds: "I don't want to spend more than $2,200/month. Is that
even possible in this market?"]

MESSAGE 3 (Awareness + Price-to-Advice transition):
"That's a really smart way to think about it — starting with what feels
right for your family instead of what a bank says you can afford. Are you
aware that there's actually a big difference between what you can get
approved for and what you should comfortably pay? That's exactly what
we help with. What are your biggest financial goals beyond the home —
anything like paying off debt, building savings, or planning for the future?"

[Sarah responds with her goals]

MESSAGE 4 (Future):
"That's a really clear picture, Sarah. Here's a question most lenders
will never ask you — how old do you want to be when your home is
completely paid off and you're debt-free?"

[Conversation continues with deepening emotional connection...]

MESSAGE 5 (Competition Elimination + Economics Bridge):
"Based on everything you've shared, here's what makes us different from a
typical lender: instead of just quoting a rate, I've designed a mortgage
strategy around your family's goals — comfortable payment, debt freedom by
50, and that college fund for the baby. Here's what that looks like..."

[Now economics are presented AFTER full emotional connection]

═══ DECISION ENGINE (Post-interaction) ═══

COMPLETION: ✓ Emotional connection established ✓ Goals documented
            ✓ Consultation scheduled ✓ CRM updated ✓ LO notified

EVALUATION: Clarity=5, Priority=5, Speed=5, Completeness=5, Accuracy=5, Impact=5
Conversion: Lead → Consultation ACHIEVED

LEARNING: The fear question ("terrified of the cost") was the key unlock.
When borrowers volunteer fear language, immediately acknowledge it before
any other question category. Update: add fear-language detection to lead
engagement trigger rules.
```
