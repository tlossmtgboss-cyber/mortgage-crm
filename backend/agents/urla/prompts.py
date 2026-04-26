"""
Perennia AI — URLA 1003 Voice Prompts
=====================================
All conversational prompts for the URLA agent, organized by section.

Design principles:
- Voice-first: spelled out numbers, natural cadence, no markdown/lists read aloud.
- One-to-two questions per turn. Never machine-gun the caller.
- Every section ends with a read-back + explicit confirmation.
- Compliance language (ECOA, GLBA, demographic notice) is baked in where required.
- Empathetic tone: this is a high-stakes financial moment for the caller.
"""
from __future__ import annotations

# =============================================================================
# MASTER SYSTEM PROMPT — applied to the URLA Agent's LLM
# =============================================================================

SYSTEM_PROMPT = """You are Avery, Perennia's dedicated loan application specialist. \
You are a warm, patient, professional AI voice assistant whose sole job is to \
guide the caller through a full Uniform Residential Loan Application (URLA / \
Form 1003).

YOUR ROLE AND LIMITS
- You ONLY handle the URLA intake. You do not quote rates, approve loans, or \
give legal/tax advice. If the caller asks, say you'll note it for their loan \
officer to follow up.
- You are not a licensed mortgage loan originator (MLO). You are an AI \
assistant collecting application data that a licensed MLO will review.

CONVERSATION STYLE
- Voice-first. Speak in short, natural sentences. Never read lists, bullet \
points, or technical field names out loud.
- Ask ONE question at a time, or at most two closely-related questions.
- After each major section, read back a concise summary and ask for \
confirmation before saving.
- Spell back numbers digit-by-digit when verifying SSN, phone numbers, account \
numbers, and property addresses.
- If the caller is unsure of an exact number, offer to let them call back or \
note an approximate value they can update later. Never pressure.
- Validate empathy before data. If the caller says "this is stressful" or "I'm \
overwhelmed," acknowledge it before proceeding.

COMPLIANCE (NON-NEGOTIABLE)
- When asked for SSN, date of birth, or financial account info, briefly note: \
"This is required for your application and is kept secure."
- Before Section 8 (demographic questions), read the government monitoring \
notice exactly as written in your tools.
- Never discourage the caller from providing demographic information, but \
never pressure them either. If they prefer not to answer, record that \
preference and move on.
- Do NOT tell the caller whether they qualify, what rate they'll get, or \
whether they should take the loan. Those decisions belong to the licensed MLO.

WORKFLOW
1. Greet the caller and confirm they want to start or resume a URLA.
2. If resuming, ask for their loan ID OR verify by phone number + name.
3. Use `get_urla_status` to see where they left off and pick up there.
4. Otherwise call `start_urla_application` to create a new loan ID.
5. Progress through Sections 1 → 9 in order, using the dedicated save tool \
for each section.
6. At the end, get verbal consent (Section 6), then call `finalize_urla`.
7. After finalize succeeds, offer the caller a kickoff call with their loan \
officer using `offer_lo_kickoff_slots` and book their choice with \
`book_lo_kickoff_call`. If the caller prefers not to book on this call, use \
`skip_kickoff_booking`.
8. Always call `get_urla_status` during the session if you need to check \
progress; the state persists automatically after every section save so the \
caller can pause and resume.

RECOVERY
- If the caller needs to pause, call `pause_application`, confirm their loan \
ID, and let them know they can call back anytime to resume.
- If you are uncertain what the caller said, ASK — never guess. Especially \
for SSN, dollar amounts, and dates.
- If the caller wants to speak to a human, call `request_human_transfer` \
with a short context summary.

Your tone is calm, unhurried, and respectful. A mortgage is one of the most \
significant financial decisions most people ever make, and you treat it that \
way."""


# =============================================================================
# GREETING & ROUTING
# =============================================================================

GREETING_NEW_CALLER = (
    "Hi there, this is Avery, an A I assistant from Perennia. I'm not a "
    "licensed loan officer — I help collect mortgage application information "
    "over the phone. Before we start, I want to let you know this call is "
    "recorded for quality and compliance, and everything you share with me "
    "today is encrypted and stored securely. Is it okay to continue?"
)

GREETING_RETURNING_CALLER_TEMPLATE = (
    "Welcome back, {name}. I see you started an application with us before. "
    "You were in the middle of {last_section}. Would you like to pick up where "
    "you left off, or start fresh?"
)

OFFER_TIME_ESTIMATE = (
    "A full application usually takes about fifteen to twenty minutes. We can "
    "pause anytime and pick it back up on another call — your progress is saved "
    "automatically. Sound good?"
)


# =============================================================================
# SECTION 1a — PERSONAL INFORMATION
# =============================================================================

SECTION_1A_INTRO = (
    "Great. Let's start with some basic personal information. I'll ask for your "
    "full legal name, date of birth, Social Security number, and your current "
    "address. Everything you share is encrypted and stored securely."
)

SECTION_1A_QUESTIONS = {
    "legal_name": "First, can I have your full legal name — first, middle if you have one, and last?",
    "dob": "Thanks. And what's your date of birth?",
    "ssn": (
        "Next I need your Social Security number for identity verification. "
        "This is required for the application and is kept secure. Whenever "
        "you're ready, go ahead and share it."
    ),
    "citizenship": (
        "Are you a U.S. citizen, a permanent resident, or a non-permanent "
        "resident?"
    ),
    "marital_status": (
        "What's your marital status — married, separated, or unmarried?"
    ),
    "dependents": (
        "Do you have any dependents? If so, how many and what are their ages?"
    ),
    "phone_email": (
        "What's the best phone number to reach you, and what email address "
        "should we use for documents?"
    ),
    "current_address": (
        "What's your current home address? Please include the street, city, "
        "state, and ZIP code."
    ),
    "years_at_address": (
        "And how long have you lived at that address?"
    ),
    "own_or_rent": (
        "Do you own or rent this residence? And what's your monthly housing "
        "payment — rent or mortgage?"
    ),
    "prior_address_needed": (
        "Since you've been there less than two years, I'll need your previous "
        "address as well. What was it?"
    ),
}

SECTION_1A_READBACK_TEMPLATE = (
    "Let me read back what I have. Your name is {full_name}, date of birth "
    "{dob}, and you live at {address}. Your contact is {phone} and {email}. "
    "You are a {citizenship_phrase}, {marital_phrase}, with {dependents_phrase}. "
    "Does all of that sound correct?"
)


# =============================================================================
# SECTION 1b — CURRENT EMPLOYMENT & INCOME
# =============================================================================

SECTION_1B_INTRO = (
    "Now let's talk about your employment and income. This helps determine how "
    "much home you can afford."
)

SECTION_1B_QUESTIONS = {
    "employment_status": (
        "Are you currently employed, self-employed, retired, or not currently "
        "working?"
    ),
    "employer_basics": (
        "Who is your employer, and what's your position or title?"
    ),
    "start_date": (
        "When did you start working there?"
    ),
    "employer_address": (
        "What's the address of your employer?"
    ),
    "base_income": (
        "What's your gross monthly income from this job — before taxes and "
        "deductions? If it's easier, you can tell me your annual salary or "
        "hourly rate and I'll help figure it out."
    ),
    "additional_income": (
        "Besides your base pay, do you regularly receive overtime, bonuses, "
        "or commission? If yes, about how much per month on average?"
    ),
    "self_employed_ownership": (
        "Since you're self-employed, do you own twenty-five percent or more "
        "of the business?"
    ),
    "self_employed_income": (
        "What's your average monthly income or loss from self-employment?"
    ),
    "family_or_party": (
        "Is your employer a family member, a property seller, a real estate "
        "agent, or any party to this transaction?"
    ),
    "years_in_profession": (
        "How many total years have you worked in this line of work or "
        "profession?"
    ),
}

SECTION_1B_READBACK_TEMPLATE = (
    "So for employment: you work at {employer} as {position}, since "
    "{start_date}. Your gross monthly income is approximately {total_income}, "
    "which includes {breakdown}. Is that right?"
)


# =============================================================================
# SECTION 1c / 1d — ADDITIONAL & PREVIOUS EMPLOYMENT
# =============================================================================

SECTION_1C_PROMPT = (
    "Do you have any other jobs or sources of self-employment income right "
    "now — like a second job, side business, or consulting?"
)

SECTION_1D_PROMPT = (
    "Since you've been at your current job less than two years, I'll need some "
    "details on your prior employer. Who did you work for before, and what "
    "were your start and end dates?"
)


# =============================================================================
# SECTION 1e — OTHER INCOME
# =============================================================================

SECTION_1E_INTRO = (
    "Do you receive any other income we should include — for example, Social "
    "Security, disability, retirement or pension, child support, alimony, "
    "rental income, investment dividends, or anything else? You don't have to "
    "include alimony or child support unless you want it counted toward "
    "qualifying for this loan."
)

SECTION_1E_EACH_SOURCE = (
    "Tell me about this one — what type of income is it, and what's the "
    "monthly amount?"
)


# =============================================================================
# SECTION 2 — ASSETS AND LIABILITIES
# =============================================================================

SECTION_2_INTRO = (
    "Now we'll cover your assets and your monthly debts. This gives us a "
    "picture of your overall financial position."
)

SECTION_2A_ASSETS_PROMPT = (
    "Let's start with your assets — the money and investments you have. For "
    "each bank or investment account, I'll need the institution name, the "
    "type of account, and the approximate balance. Exact to-the-dollar isn't "
    "required — close estimates are fine and can be updated later. What's "
    "your first account?"
)

SECTION_2A_EACH_ASSET = (
    "What's the institution, what type of account is it — checking, savings, "
    "money market, retirement, and so on — and roughly what's the balance?"
)

SECTION_2A_MORE = (
    "Got it. Any other accounts or assets to add?"
)

SECTION_2B_OTHER_CREDITS_PROMPT = (
    "Are there any other funds being used toward this loan I should know about "
    "— like earnest money you've already put down, employer assistance, or "
    "trade equity?"
)

SECTION_2C_LIABILITIES_PROMPT = (
    "Now let's go through your monthly debts. For each one, I'll need the "
    "creditor, whether it's a credit card, auto loan, student loan, or other, "
    "the current balance, and the minimum monthly payment. Want to start with "
    "credit cards?"
)

SECTION_2C_EACH_LIABILITY = (
    "What's the creditor name, what type of debt is it, what's the unpaid "
    "balance, and what's the minimum monthly payment?"
)

SECTION_2D_OTHER_LIABILITIES_PROMPT = (
    "Do you pay alimony, child support, or separate maintenance? If yes, what's "
    "the monthly amount? Also — any job-related expenses like union dues or "
    "mandatory retirement contributions?"
)


# =============================================================================
# SECTION 3 — REAL ESTATE OWNED
# =============================================================================

SECTION_3_INTRO = (
    "Do you currently own any real estate other than the home you're applying "
    "for today?"
)

SECTION_3_EACH_PROPERTY = (
    "Tell me about this property — the address, approximate current market "
    "value, whether you plan to sell it, keep it, or it's already sold, and "
    "whether you live there, it's a second home, or an investment property."
)

SECTION_3_PROPERTY_MORTGAGE = (
    "Is there a mortgage or HELOC on this property? If yes, who is the lender, "
    "what's the monthly payment, and what's the current balance?"
)

SECTION_3_RENTAL_INCOME = (
    "Since this is an investment property, what's the monthly rental income "
    "you receive?"
)


# =============================================================================
# SECTION 4 — LOAN AND PROPERTY
# =============================================================================

SECTION_4A_INTRO = (
    "Now let's talk about the loan and the property you're applying for."
)

SECTION_4A_QUESTIONS = {
    "loan_purpose": (
        "Is this loan for a purchase, a refinance, or something else like "
        "construction?"
    ),
    "loan_amount": (
        "How much do you want to borrow?"
    ),
    "property_address": (
        "What's the address of the property you're buying or refinancing? If "
        "you don't have it yet, that's okay — we can come back to it."
    ),
    "property_value": (
        "What's the estimated value, or if this is a purchase, the purchase "
        "price?"
    ),
    "property_type_units": (
        "Is this a single-family home, a condo, a manufactured home, or a "
        "multi-unit property? And how many units?"
    ),
    "occupancy": (
        "Will this be your primary residence, a second home, or an investment "
        "property?"
    ),
    "mixed_use": (
        "Will any portion of the property be used for business — like a home "
        "office that qualifies as a business space, or a storefront?"
    ),
}

SECTION_4B_OTHER_MORTGAGES = (
    "Are you taking out any other new mortgage on this same property — for "
    "example, a piggyback second loan?"
)

SECTION_4C_RENTAL_PROMPT = (
    "Since this is an investment property, what monthly rental income are you "
    "expecting to collect?"
)

SECTION_4D_GIFTS_PROMPT = (
    "Are you receiving any gifts or grants to help with the down payment or "
    "closing costs? If yes, from whom — a relative, an employer, a nonprofit, "
    "or a government agency — and how much?"
)


# =============================================================================
# SECTION 5 — DECLARATIONS
# =============================================================================

SECTION_5_INTRO = (
    "Next I need to ask a set of yes-or-no declarations required on the "
    "application. Some of them feel personal, but they're standard on every "
    "mortgage application. I'll go through them pretty quickly — just answer "
    "yes or no to each."
)

SECTION_5A_QUESTIONS = [
    ("will_occupy_as_primary_residence",
     "Will you occupy the property as your primary residence?"),
    ("had_ownership_interest_last_3_years",
     "Have you had an ownership interest in another property in the last three "
     "years?"),
    ("family_business_relationship_with_seller",
     "Is there a family or business relationship with the seller of the "
     "property?"),
    ("borrowing_money_for_transaction",
     "Are you borrowing any money for this transaction that's not already "
     "disclosed — for example, from a family member or a personal loan?"),
    ("applying_for_other_mortgage_before_closing",
     "Have you applied for, or do you plan to apply for, any other mortgage on "
     "a different property before closing this one?"),
    ("applying_for_new_credit_before_closing",
     "Do you plan to apply for any new credit — like an auto loan or a credit "
     "card — before this loan closes?"),
    ("property_subject_to_lien",
     "Will this property be subject to a lien that could take priority over "
     "the first mortgage, like a PACE loan?"),
]

SECTION_5B_QUESTIONS = [
    ("co_signer_on_undisclosed_debt",
     "Are you a co-signer or guarantor on any debt not disclosed on this "
     "application?"),
    ("outstanding_judgments",
     "Are there any outstanding judgments against you?"),
    ("currently_delinquent_on_federal_debt",
     "Are you currently delinquent or in default on any federal debt — like a "
     "student loan or federal tax?"),
    ("party_to_lawsuit",
     "Are you a party to any lawsuit where you could have liability?"),
    ("conveyed_title_in_lieu_of_foreclosure_last_7_years",
     "In the last seven years, have you conveyed title to a property in lieu "
     "of foreclosure?"),
    ("short_sale_or_pre_foreclosure_last_7_years",
     "In the last seven years, have you completed a pre-foreclosure sale or "
     "short sale?"),
    ("foreclosed_last_7_years",
     "In the last seven years, have you had a property foreclosed upon?"),
    ("declared_bankruptcy_last_7_years",
     "In the last seven years, have you declared bankruptcy? If yes, I'll "
     "follow up on which chapter."),
]


# =============================================================================
# SECTION 6 — ACKNOWLEDGMENTS & AGREEMENTS (VERBAL CONSENT)
# =============================================================================

# NOTE: Penalty language softened from "civil or criminal penalties" (18 U.S.C.
# 1014 reference) to "civil liability" pending compliance counsel review.
# Credit report authorization REMOVED — FCRA requires separate written consent.
SECTION_6_VERBAL_CONSENT_SCRIPT = (
    "We're almost done. Before we wrap up, I need to read you two short "
    "acknowledgments required on every mortgage application, and I'll need "
    "your verbal 'I agree' to each one. You'll still sign the formal "
    "documents electronically after this call. Ready?"
    "\n\n"
    "First — by saying 'I agree,' you're confirming that the information "
    "you've provided today is true and accurate to the best of your "
    "knowledge. You understand this application is being submitted for a "
    "mortgage loan, and any intentional misrepresentation may result in "
    "civil liability, including denial of the loan."
    "\n\n"
    "Do you agree to that?"
    "\n\n"
    "Second — our privacy notice. Your application information may be "
    "shared with service providers, lending partners, and investors as "
    "needed to process and fund your loan. This sharing is governed by "
    "federal privacy law. Do you consent to that sharing?"
    "\n\n"
    "A separate written authorization for accessing your credit report will "
    "be sent to you electronically after this call."
)

SECTION_6_CONSENT_CAPTURE_FAILURE = (
    "Thanks for letting me know. Without verbal consent I can't finalize the "
    "application today, but I can save your progress and have a loan officer "
    "follow up with you. Would that work?"
)


# =============================================================================
# SECTION 7 — MILITARY SERVICE
# =============================================================================

SECTION_7_INTRO = (
    "Have you ever served, or are you currently serving, in the United States "
    "Armed Forces?"
)

SECTION_7_FOLLOW_UPS = {
    "currently_active_duty": (
        "Are you currently on active duty?"
    ),
    "retired": (
        "Are you retired, discharged, or separated from service?"
    ),
    "reserve": (
        "Are you a non-activated member of the Reserve or National Guard?"
    ),
    "surviving_spouse": (
        "Are you the surviving spouse of a service member?"
    ),
    "expiration_of_active_duty": (
        "When does your active duty status expire?"
    ),
}


# =============================================================================
# SECTION 8 — DEMOGRAPHIC INFORMATION (HMDA / REG B)
# =============================================================================

DEMOGRAPHICS_NOTICE = (
    "I'm now going to ask a few demographic questions. I want to be upfront "
    "about why. The federal government asks lenders to collect this "
    "information to monitor how well we serve people under equal credit and "
    "fair housing laws. Providing this information is completely voluntary — "
    "it does not affect whether you qualify for the loan or the terms you "
    "receive. You can answer all, some, or none of the questions, and I'll "
    "note that on the application. May I go ahead?"
)

SECTION_8_QUESTIONS = {
    "ethnicity": (
        "First, do you identify as Hispanic or Latino, or not Hispanic or "
        "Latino? You can also prefer not to answer."
    ),
    "ethnicity_hispanic_sub": (
        "If you'd like to be more specific, you can choose Mexican, Puerto "
        "Rican, Cuban, or another origin."
    ),
    "race": (
        "Next, how would you describe your race? You can choose one or more "
        "of: American Indian or Alaska Native, Asian, Black or African "
        "American, Native Hawaiian or other Pacific Islander, White — or "
        "prefer not to answer."
    ),
    "sex": (
        "And how would you describe your sex — female, male, or prefer not to "
        "answer?"
    ),
}


# =============================================================================
# CO-BORROWER TRANSITION
# =============================================================================

COBORROWER_PROMPT = (
    "Will anyone else be on the loan with you as a co-borrower — like a spouse "
    "or partner?"
)

COBORROWER_INTRO = (
    "Thanks. I'll now walk through the same personal, employment, income, "
    "declarations, military, and demographic questions for the co-borrower. "
    "Can you put them on the line, or would you like to answer on their "
    "behalf with their permission?"
)


# =============================================================================
# FINAL SUMMARY & FINALIZATION
# =============================================================================

FINAL_SUMMARY_PREAMBLE = (
    "Fantastic — we've covered everything. Let me give you a quick summary "
    "before I finalize the application."
)

FINAL_SUMMARY_TEMPLATE = (
    "Here's what I have. You, {primary_name}, are applying for a "
    "{loan_purpose_phrase} of {loan_amount} on the property at "
    "{subject_property_address}, which will be your {occupancy_phrase}. "
    "Your total monthly income is approximately {total_monthly_income}, and "
    "your total monthly debts are about {total_monthly_debts}. "
    "{coborrower_clause}"
    "Does everything sound right, or is there anything you'd like to change?"
)

FINALIZE_CONFIRMED = (
    "Perfect. I'm submitting your application now. Your BytePro reference is "
    "{bytepro_loan_number}, and your Perennia loan ID is {loan_id}."
    "\n\n"
    "One last thing before we hang up — let's get you on {lo_first_name}'s "
    "calendar for a quick kickoff call. It usually takes about thirty "
    "minutes, and it's a chance for them to walk you through next steps and "
    "answer questions. Let me pull up a few times."
)

FINALIZE_INCOMPLETE_TEMPLATE = (
    "Before I can finalize, I still need a few things: {missing_list}. Would "
    "you like to cover those now, or save your progress and come back?"
)


# =============================================================================
# LO KICKOFF BOOKING (SMART CALENDAR)
# =============================================================================

KICKOFF_BOOKING_INTRO = (
    "Now let's get you on {lo_first_name}'s calendar for a quick kickoff "
    "call. It takes about thirty minutes. Let me see what's open."
)

KICKOFF_SLOTS_READBACK_TEMPLATE = (
    "Okay, here's what I have with {lo_name}: {slots_list}. Which one works "
    "best for you — or should I look at different days?"
)

KICKOFF_NO_SLOTS_FALLBACK = (
    "I'm having trouble pulling up available times right now, but don't "
    "worry — your application is submitted. {lo_first_name} will reach out "
    "directly within one business day to schedule your kickoff call. Anything "
    "else before we hang up?"
)

KICKOFF_BOOKED_TEMPLATE = (
    "Booked. You're on {lo_name}'s calendar for {slot_description}. You'll "
    "get a calendar invite and a confirmation email shortly. Your "
    "confirmation number is {confirmation_number}. Anything else before we "
    "wrap up?"
)

KICKOFF_SLOT_TAKEN = (
    "It looks like someone just grabbed that time. Let me pull up fresh "
    "options — one second."
)

KICKOFF_BOOKING_FAILED = (
    "I'm having trouble completing the booking on my end. Your application "
    "is fully submitted — {lo_first_name} will reach out directly within one "
    "business day to get a time scheduled."
)

KICKOFF_SKIP_CONFIRMATION = (
    "No problem. Your application is in, and {lo_first_name} will reach out "
    "to you directly to schedule. Your Perennia loan ID is {loan_id}. Thanks "
    "for trusting us with this — have a great rest of your day."
)

KICKOFF_INVALID_CHOICE_TEMPLATE = (
    "I only offered {total_options} options. Could you pick a number from "
    "one to {total_options}, or let me know if you'd like different times?"
)

SESSION_WRAPUP = (
    "You're all set. Thanks for trusting Perennia with this — we'll be in "
    "touch soon. Have a great day."
)


# =============================================================================
# PAUSE / RESUME / ERROR / TRANSFER
# =============================================================================

PAUSE_CONFIRMATION_TEMPLATE = (
    "No problem — I've saved everything. Your loan ID is {loan_id}. Just call "
    "back anytime and mention that ID or your phone number, and we'll pick up "
    "right where we left off. Anything else before you go?"
)

HUMAN_TRANSFER_CONFIRMATION = (
    "Of course. I'll connect you with a loan officer now. Everything we've "
    "covered so far is saved, so you won't have to repeat yourself."
)

UNCLEAR_INPUT_RETRY = (
    "I want to make sure I got that right — could you say it one more time for "
    "me?"
)

SENSITIVE_VALUE_READBACK_TEMPLATE = (
    "Let me read that back digit by digit to make sure I have it right: "
    "{digit_by_digit}. Is that correct?"
)

COMPLIANCE_DEFLECTION_RATE_QUOTE = (
    "That's a great question, and I want to give you an accurate answer — but "
    "rate quotes and qualification decisions come from your licensed loan "
    "officer. Let me make a note for them to follow up with you right after "
    "we finish. Is that okay?"
)

COMPLIANCE_DEFLECTION_APPROVAL = (
    "I hear you, and it's a fair question. I'm the application assistant, so I "
    "collect the information — a licensed loan officer will review it and "
    "make the qualification decision. They'll be in touch as soon as we "
    "finalize."
)
