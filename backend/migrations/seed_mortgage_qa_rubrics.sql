-- Seed Mortgage QA Rubrics for Conversation Intelligence Platform
-- Comprehensive scoring criteria for mortgage call quality assessment

-- =============================================================================
-- GREETING & OPENING RUBRICS
-- =============================================================================

INSERT INTO ci_qa_rubrics (id, name, description, category, max_points, weight, criteria, scoring_guide, auto_score_enabled, auto_score_keywords, call_types, required, is_active)
VALUES
(
    uuid_generate_v4(),
    'Professional Greeting',
    'Agent greets caller professionally with company name and their name',
    'greeting',
    10,
    1.0,
    '{
        "criteria": [
            {"points": 3, "description": "Agent states company name"},
            {"points": 3, "description": "Agent provides their full name"},
            {"points": 2, "description": "Greeting is warm and welcoming"},
            {"points": 2, "description": "Offers assistance appropriately"}
        ],
        "examples": {
            "excellent": "Thank you for calling ABC Mortgage, this is John Smith, how may I help you today?",
            "poor": "Hello?"
        }
    }',
    'Score based on completeness and warmth of greeting. Full credit requires company name, agent name, and offer of assistance.',
    true,
    '{"required": ["mortgage", "lending", "loan"], "bonus": ["thank you for calling", "how may I help"]}',
    '{inbound}',
    true,
    true
),
(
    uuid_generate_v4(),
    'Outbound Introduction',
    'Agent introduces themselves professionally on outbound calls',
    'greeting',
    10,
    1.0,
    '{
        "criteria": [
            {"points": 3, "description": "Agent states their name and company"},
            {"points": 3, "description": "States reason for calling clearly"},
            {"points": 2, "description": "Asks if it is a good time"},
            {"points": 2, "description": "Professional and courteous tone"}
        ],
        "examples": {
            "excellent": "Hi, this is John Smith from ABC Mortgage. Is this a good time to discuss your loan application?",
            "poor": "Hey, I am calling about your loan"
        }
    }',
    'Full credit requires name, company, purpose, and courtesy check.',
    true,
    '{"required": ["calling from", "this is"], "bonus": ["good time", "convenient"]}',
    '{outbound}',
    true,
    true
);

-- =============================================================================
-- DISCOVERY & NEEDS ASSESSMENT RUBRICS
-- =============================================================================

INSERT INTO ci_qa_rubrics (id, name, description, category, max_points, weight, criteria, scoring_guide, auto_score_enabled, auto_score_keywords, call_types, required, is_active)
VALUES
(
    uuid_generate_v4(),
    'Loan Purpose Discovery',
    'Agent effectively identifies the purpose of the loan (purchase, refinance, cash-out)',
    'discovery',
    10,
    1.5,
    '{
        "criteria": [
            {"points": 4, "description": "Clearly identifies purchase vs refinance vs cash-out"},
            {"points": 3, "description": "Asks clarifying questions about specific needs"},
            {"points": 3, "description": "Listens actively and confirms understanding"}
        ],
        "key_questions": [
            "Are you looking to purchase a new home or refinance?",
            "Is this a rate and term refinance or are you looking to take cash out?",
            "What are you hoping to accomplish with this loan?"
        ]
    }',
    'Agent should clearly establish loan purpose within first 2 minutes of substantive conversation.',
    true,
    '{"required": ["purchase", "refinance", "cash out", "cash-out"], "bonus": ["what are you looking to accomplish", "goals"]}',
    '{inbound,outbound}',
    true,
    true
),
(
    uuid_generate_v4(),
    'Financial Qualification Questions',
    'Agent asks appropriate questions to understand borrower financial situation',
    'discovery',
    10,
    1.5,
    '{
        "criteria": [
            {"points": 2, "description": "Asks about employment status and income"},
            {"points": 2, "description": "Inquires about credit situation appropriately"},
            {"points": 2, "description": "Discusses down payment or equity"},
            {"points": 2, "description": "Asks about existing debts/obligations"},
            {"points": 2, "description": "Questions are asked tactfully"}
        ],
        "key_questions": [
            "What is your current employment situation?",
            "Do you have an estimate of your credit score?",
            "What down payment are you planning to make?",
            "Are there any other debts we should consider?"
        ]
    }',
    'Agent should gather enough information to provide meaningful guidance without being intrusive.',
    true,
    '{"required": ["income", "employment", "credit", "down payment"], "bonus": ["debt to income", "DTI", "assets"]}',
    '{inbound,outbound}',
    true,
    true
),
(
    uuid_generate_v4(),
    'Timeline & Urgency Assessment',
    'Agent determines borrower timeline and urgency',
    'discovery',
    10,
    1.0,
    '{
        "criteria": [
            {"points": 4, "description": "Asks about desired closing timeline"},
            {"points": 3, "description": "Understands any rate lock needs"},
            {"points": 3, "description": "Identifies any urgent circumstances"}
        ],
        "key_questions": [
            "When are you looking to close?",
            "Do you have a contract date we need to work toward?",
            "Are you concerned about rate changes?"
        ]
    }',
    'Understanding timeline helps set expectations and urgency.',
    true,
    '{"required": ["when", "timeline", "close", "closing"], "bonus": ["lock", "rate lock", "contract"]}',
    '{inbound,outbound}',
    false,
    true
);

-- =============================================================================
-- PRODUCT PRESENTATION RUBRICS
-- =============================================================================

INSERT INTO ci_qa_rubrics (id, name, description, category, max_points, weight, criteria, scoring_guide, auto_score_enabled, auto_score_keywords, call_types, required, is_active)
VALUES
(
    uuid_generate_v4(),
    'Loan Options Explanation',
    'Agent clearly explains relevant loan options',
    'presentation',
    10,
    1.5,
    '{
        "criteria": [
            {"points": 3, "description": "Presents options relevant to borrower situation"},
            {"points": 3, "description": "Explains key differences between options"},
            {"points": 2, "description": "Uses clear, non-jargon language"},
            {"points": 2, "description": "Provides pros and cons of each option"}
        ],
        "loan_types_to_discuss": ["conventional", "FHA", "VA", "USDA", "jumbo"],
        "key_points": ["rate", "term", "down payment requirements", "PMI/MIP"]
    }',
    'Agent should present 2-3 relevant options based on borrower profile.',
    true,
    '{"required": ["conventional", "FHA", "fixed", "adjustable"], "bonus": ["compare", "option", "alternative"]}',
    '{inbound,outbound}',
    true,
    true
),
(
    uuid_generate_v4(),
    'Rate & Terms Communication',
    'Agent accurately communicates current rates and terms',
    'presentation',
    10,
    1.5,
    '{
        "criteria": [
            {"points": 3, "description": "Provides accurate rate information"},
            {"points": 3, "description": "Explains factors affecting rate (credit, LTV, etc.)"},
            {"points": 2, "description": "Discusses rate lock options"},
            {"points": 2, "description": "Clarifies that rates are subject to change"}
        ],
        "compliance_note": "Must not guarantee rates without locked commitment"
    }',
    'Rates must be current and agent should explain they are estimates subject to verification.',
    true,
    '{"required": ["rate", "APR", "interest"], "bonus": ["rate lock", "points", "buy down"]}',
    '{inbound,outbound}',
    true,
    true
),
(
    uuid_generate_v4(),
    'Cost & Fees Transparency',
    'Agent provides clear information about costs and fees',
    'presentation',
    10,
    1.5,
    '{
        "criteria": [
            {"points": 3, "description": "Discusses closing costs range"},
            {"points": 3, "description": "Explains origination fees"},
            {"points": 2, "description": "Mentions third-party fees (appraisal, title, etc.)"},
            {"points": 2, "description": "Offers to provide detailed estimate"}
        ],
        "fee_categories": ["origination", "appraisal", "title", "escrow", "prepaid items"]
    }',
    'Transparency about fees builds trust and reduces surprises at closing.',
    true,
    '{"required": ["closing costs", "fees", "cost"], "bonus": ["estimate", "LE", "loan estimate"]}',
    '{inbound,outbound}',
    true,
    true
);

-- =============================================================================
-- OBJECTION HANDLING RUBRICS
-- =============================================================================

INSERT INTO ci_qa_rubrics (id, name, description, category, max_points, weight, criteria, scoring_guide, auto_score_enabled, auto_score_keywords, call_types, required, is_active)
VALUES
(
    uuid_generate_v4(),
    'Rate Objection Handling',
    'Agent effectively handles objections about rates',
    'objection_handling',
    10,
    1.0,
    '{
        "criteria": [
            {"points": 3, "description": "Acknowledges the concern without being defensive"},
            {"points": 3, "description": "Provides context about rate factors"},
            {"points": 2, "description": "Offers alternatives or solutions"},
            {"points": 2, "description": "Maintains positive relationship"}
        ],
        "common_objections": [
            "Your rates are too high",
            "I saw a lower rate online",
            "Bank X quoted me less"
        ],
        "response_strategies": [
            "Compare total costs, not just rate",
            "Explain what factors into the rate",
            "Discuss rate lock and points options"
        ]
    }',
    'Agent should address rate concerns professionally without disparaging competitors.',
    true,
    '{"triggers": ["rate is too high", "better rate", "lower rate", "competitor"], "good_responses": ["understand", "let me explain", "total cost"]}',
    '{inbound,outbound}',
    false,
    true
),
(
    uuid_generate_v4(),
    'Timing Objection Handling',
    'Agent handles objections about timing or readiness',
    'objection_handling',
    10,
    1.0,
    '{
        "criteria": [
            {"points": 3, "description": "Acknowledges and respects their timeline"},
            {"points": 3, "description": "Provides value for future engagement"},
            {"points": 2, "description": "Offers to stay in touch appropriately"},
            {"points": 2, "description": "Leaves door open without pressure"}
        ],
        "common_objections": [
            "Just looking right now",
            "Not ready to commit",
            "Need to think about it",
            "Still comparing options"
        ]
    }',
    'Respect timing while providing enough value to maintain relationship.',
    true,
    '{"triggers": ["just looking", "not ready", "think about it", "shopping around"], "good_responses": ["understand", "when you are ready", "keep in touch"]}',
    '{inbound,outbound}',
    false,
    true
);

-- =============================================================================
-- CLOSING & NEXT STEPS RUBRICS
-- =============================================================================

INSERT INTO ci_qa_rubrics (id, name, description, category, max_points, weight, criteria, scoring_guide, auto_score_enabled, auto_score_keywords, call_types, required, is_active)
VALUES
(
    uuid_generate_v4(),
    'Clear Next Steps',
    'Agent provides clear next steps and action items',
    'closing',
    10,
    1.5,
    '{
        "criteria": [
            {"points": 3, "description": "Summarizes what was discussed"},
            {"points": 3, "description": "Clearly states next steps for both parties"},
            {"points": 2, "description": "Sets expectations for timeline"},
            {"points": 2, "description": "Confirms contact information"}
        ],
        "key_elements": [
            "Application submission",
            "Document collection",
            "Follow-up call scheduled",
            "Email with information to follow"
        ]
    }',
    'Every call should end with clear understanding of what happens next.',
    true,
    '{"required": ["next step", "follow up", "send you", "email"], "bonus": ["summarize", "to confirm", "action item"]}',
    '{inbound,outbound}',
    true,
    true
),
(
    uuid_generate_v4(),
    'Application Advancement',
    'Agent effectively moves borrower toward application',
    'closing',
    10,
    1.5,
    '{
        "criteria": [
            {"points": 4, "description": "Asks for the application or next commitment"},
            {"points": 3, "description": "Handles hesitation appropriately"},
            {"points": 3, "description": "Provides compelling reason to act"}
        ],
        "advancement_actions": [
            "Start application on the call",
            "Schedule follow-up to complete application",
            "Send application link with deadline",
            "Pre-qualification submission"
        ]
    }',
    'Agent should attempt to advance the process while respecting borrower pace.',
    true,
    '{"required": ["application", "apply", "get started", "pre-approval"], "bonus": ["right now", "today", "ready to move forward"]}',
    '{inbound,outbound}',
    true,
    true
),
(
    uuid_generate_v4(),
    'Professional Closing',
    'Agent ends call professionally',
    'closing',
    10,
    1.0,
    '{
        "criteria": [
            {"points": 4, "description": "Thanks borrower for their time"},
            {"points": 3, "description": "Confirms best way to reach them"},
            {"points": 3, "description": "Ends on positive note"}
        ],
        "examples": {
            "excellent": "Thank you so much for speaking with me today. I will send you that information right away. Please do not hesitate to call if you have any questions. Have a great day!",
            "poor": "Okay, bye."
        }
    }',
    'End every call professionally regardless of outcome.',
    true,
    '{"required": ["thank you", "thanks"], "bonus": ["great day", "questions", "reach out"]}',
    '{inbound,outbound}',
    true,
    true
);

-- =============================================================================
-- COMPLIANCE RUBRICS
-- =============================================================================

INSERT INTO ci_qa_rubrics (id, name, description, category, max_points, weight, criteria, scoring_guide, auto_score_enabled, auto_score_keywords, call_types, required, is_active)
VALUES
(
    uuid_generate_v4(),
    'NMLS Disclosure',
    'Agent provides NMLS ID when required',
    'compliance',
    10,
    2.0,
    '{
        "criteria": [
            {"points": 10, "description": "NMLS ID provided when requested or at appropriate time"}
        ],
        "requirement": "NMLS ID must be provided upon request or when discussing specific loan terms",
        "auto_fail": true
    }',
    'NMLS disclosure is a regulatory requirement. Failure to provide when requested is an auto-fail.',
    true,
    '{"triggers": ["NMLS", "license number", "ID number"], "required_response": ["NMLS", "license"]}',
    '{inbound,outbound}',
    true,
    true
),
(
    uuid_generate_v4(),
    'Equal Housing Compliance',
    'Agent does not discriminate based on protected classes',
    'compliance',
    10,
    2.0,
    '{
        "criteria": [
            {"points": 10, "description": "No discriminatory language or treatment"}
        ],
        "protected_classes": ["race", "color", "religion", "national origin", "sex", "familial status", "disability"],
        "auto_fail": true
    }',
    'Any discriminatory language or treatment is an automatic failure.',
    true,
    '{"prohibited": ["cannot lend to", "we dont work with", "not for your kind"]}',
    '{inbound,outbound}',
    true,
    true
),
(
    uuid_generate_v4(),
    'Rate Advertising Compliance',
    'Agent does not make misleading rate claims',
    'compliance',
    10,
    2.0,
    '{
        "criteria": [
            {"points": 5, "description": "Does not guarantee rates without lock"},
            {"points": 5, "description": "Does not make misleading comparisons"}
        ],
        "prohibited_language": [
            "Guaranteed lowest rate",
            "We will beat any rate",
            "Best rate in the market"
        ]
    }',
    'Rate claims must be accurate and properly qualified.',
    true,
    '{"prohibited": ["guaranteed rate", "lowest rate", "beat any rate", "best rate"]}',
    '{inbound,outbound}',
    true,
    true
),
(
    uuid_generate_v4(),
    'Privacy & Data Security',
    'Agent handles sensitive information appropriately',
    'compliance',
    10,
    1.5,
    '{
        "criteria": [
            {"points": 4, "description": "Verifies identity before discussing loan details"},
            {"points": 3, "description": "Does not read full SSN or account numbers aloud"},
            {"points": 3, "description": "Directs to secure channels for sensitive data"}
        ],
        "sensitive_data": ["SSN", "bank account numbers", "tax returns", "income details"]
    }',
    'Sensitive information must be handled securely.',
    true,
    '{"triggers": ["social security", "SSN", "account number"], "good_responses": ["secure portal", "encrypted", "verify identity"]}',
    '{inbound,outbound}',
    true,
    true
);

-- =============================================================================
-- SOFT SKILLS RUBRICS
-- =============================================================================

INSERT INTO ci_qa_rubrics (id, name, description, category, max_points, weight, criteria, scoring_guide, auto_score_enabled, auto_score_keywords, call_types, required, is_active)
VALUES
(
    uuid_generate_v4(),
    'Active Listening',
    'Agent demonstrates active listening skills',
    'soft_skills',
    10,
    1.0,
    '{
        "criteria": [
            {"points": 3, "description": "Allows borrower to complete thoughts"},
            {"points": 3, "description": "Acknowledges and reflects back key points"},
            {"points": 2, "description": "Asks clarifying questions based on what was said"},
            {"points": 2, "description": "Does not interrupt unnecessarily"}
        ],
        "indicators": {
            "positive": ["I understand", "So you mentioned", "Let me make sure I have this right"],
            "negative": ["Frequent interruptions", "Ignoring stated concerns", "Repeating same questions"]
        }
    }',
    'Look for evidence of understanding borrower needs and concerns.',
    true,
    '{"positive": ["I understand", "I hear you", "you mentioned", "let me confirm"], "negative": ["interruption", "talked over"]}',
    '{inbound,outbound}',
    false,
    true
),
(
    uuid_generate_v4(),
    'Empathy & Rapport',
    'Agent builds rapport and shows empathy',
    'soft_skills',
    10,
    1.0,
    '{
        "criteria": [
            {"points": 3, "description": "Acknowledges borrower emotions and concerns"},
            {"points": 3, "description": "Uses warm, friendly tone"},
            {"points": 2, "description": "Personalizes the conversation"},
            {"points": 2, "description": "Shows genuine interest in helping"}
        ],
        "examples": {
            "empathetic": "I completely understand how stressful the home buying process can be. Let me help make this easier for you.",
            "cold": "Just fill out the application and we will get back to you."
        }
    }',
    'Empathy builds trust and improves conversion.',
    true,
    '{"positive": ["understand", "help you", "here for you", "makes sense"], "negative": ["just do", "have to", "must"]}',
    '{inbound,outbound}',
    false,
    true
),
(
    uuid_generate_v4(),
    'Knowledge & Confidence',
    'Agent demonstrates product knowledge and confidence',
    'soft_skills',
    10,
    1.0,
    '{
        "criteria": [
            {"points": 4, "description": "Answers questions accurately and confidently"},
            {"points": 3, "description": "Admits when unsure and offers to find answer"},
            {"points": 3, "description": "Explains complex concepts clearly"}
        ],
        "key_areas": ["loan programs", "rates", "process", "requirements", "timeline"]
    }',
    'Agent should be knowledgeable but honest when unsure.',
    false,
    null,
    '{inbound,outbound}',
    false,
    true
);

-- =============================================================================
-- COMPLIANCE RULES FOR AUTOMATED CHECKING
-- =============================================================================

INSERT INTO ci_compliance_rules (id, name, description, category, rule_type, rule_config, severity, is_auto_fail, states, loan_types, is_active)
VALUES
(
    uuid_generate_v4(),
    'NMLS Disclosure Required',
    'NMLS ID must be provided when requested',
    'disclosure',
    'keyword_required',
    '{
        "trigger_phrases": ["what is your NMLS", "license number", "are you licensed"],
        "required_response_within_seconds": 30,
        "required_elements": ["NMLS", "license"]
    }',
    'high',
    true,
    null,
    null,
    true
),
(
    uuid_generate_v4(),
    'No Guaranteed Rate Claims',
    'Cannot guarantee rates without a locked commitment',
    'disclosure',
    'keyword_prohibited',
    '{
        "prohibited_phrases": ["guarantee you", "guaranteed rate", "lock that in right now", "promise you that rate"],
        "exceptions": ["I cannot guarantee", "rates are subject to"]
    }',
    'high',
    false,
    null,
    null,
    true
),
(
    uuid_generate_v4(),
    'APR Disclosure',
    'APR must be mentioned when discussing rates',
    'disclosure',
    'pattern_match',
    '{
        "trigger_context": "rate discussion",
        "required_mention": ["APR", "annual percentage rate"],
        "within_context_seconds": 60
    }',
    'medium',
    false,
    null,
    null,
    true
),
(
    uuid_generate_v4(),
    'Fair Lending - No Steering',
    'Cannot steer borrowers to specific products based on protected characteristics',
    'fair_lending',
    'keyword_prohibited',
    '{
        "prohibited_patterns": [
            "people like you usually",
            "in your neighborhood",
            "for your type",
            "we dont do loans in that area"
        ]
    }',
    'critical',
    true,
    null,
    null,
    true
),
(
    uuid_generate_v4(),
    'Privacy - SSN Handling',
    'Should not read full SSN aloud',
    'privacy',
    'pattern_match',
    '{
        "pattern": "\\b\\d{3}[-\\s]?\\d{2}[-\\s]?\\d{4}\\b",
        "context": "spoken by agent",
        "exception": "last four digits"
    }',
    'medium',
    false,
    null,
    null,
    true
),
(
    uuid_generate_v4(),
    'California - DBO Disclosure',
    'California requires DBO license disclosure',
    'state_specific',
    'keyword_required',
    '{
        "required_for_states": ["CA"],
        "required_elements": ["DBO", "Department of Business Oversight", "DFPI"],
        "trigger": "loan discussion"
    }',
    'medium',
    false,
    '{CA}',
    null,
    true
),
(
    uuid_generate_v4(),
    'Texas - Home Equity Restrictions',
    'Texas has specific home equity restrictions',
    'state_specific',
    'pattern_match',
    '{
        "required_for_states": ["TX"],
        "applies_to_loan_types": ["cash_out_refinance"],
        "required_disclosures": ["80% LTV limit", "12-day cooling off"]
    }',
    'high',
    false,
    '{TX}',
    '{cash_out_refinance}',
    true
);
