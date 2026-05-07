"""
================================================================================
PERENNIA AI - KNOWLEDGE TEST CASES (Part 2)
================================================================================
Comprehensive test cases for mortgage CRM AI knowledge.

Contains 80 test cases across categories:
- Pipeline (stages, flows, metrics) - 10 tests
- CRM (entities, relationships) - 10 tests
- Loans (types, requirements, calculations) - 10 tests
- Compliance (TRID, RESPA, ECOA, fair lending) - 10 tests
- Tools (160 tools, usage patterns) - 15 tests (ToolUsageTest)
- Workflows (processes, automation) - 10 tests
- Communication (channels, templates) - 5 tests
- Integration (LOS, credit, pricing) - 5 tests
- Reporting (metrics, analytics) - 5 tests
================================================================================
"""

from AI_KNOWLEDGE_TEST_PART1_FRAMEWORK import (
    KnowledgeCategory,
    TestDifficulty,
    TestType,
    KnowledgeTest,
    ExpectedAnswer,
    MortgageKnowledgeBase,
    ToolUsageTest,
    DataAccuracyTest,
    create_pipeline_validator,
    create_tool_count_validator,
    create_compliance_validator,
)

# Note: ToolUsageTest and DataAccuracyTest are available in the framework
# but require different parameters. For simplicity, we use KnowledgeTest
# for all tests here. For tool validation tests, use KnowledgeTest with
# tool-specific expected answers.


# =============================================================================
# PIPELINE TESTS (10 tests)
# =============================================================================

PIPELINE_TESTS = [
    KnowledgeTest(
        id="PIPE-001",
        name="Pipeline Stages Order",
        category=KnowledgeCategory.PIPELINE,
        question="What are the main stages of a mortgage loan pipeline from lead to funding? List them in order.",
        expected=ExpectedAnswer(
            keywords=["lead", "application", "processing", "underwriting", "approved", "funded"],
            patterns=[r"lead.*application.*processing", r"approved.*close.*fund"],
            custom_validator=create_pipeline_validator(),
        ),
        difficulty=TestDifficulty.BASIC,
        test_type=TestType.FACTUAL,
        tags=["pipeline", "stages", "order"],
    ),

    KnowledgeTest(
        id="PIPE-002",
        name="Clear to Close Definition",
        category=KnowledgeCategory.PIPELINE,
        question="What does 'Clear to Close' (CTC) mean in the mortgage process? What happens after this stage?",
        expected=ExpectedAnswer(
            keywords=["clear to close", "ctc", "conditions", "closing disclosure", "funding"],
            patterns=[r"condition.*satisfied|cleared", r"ready.*clos"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.CONCEPTUAL,
        tags=["pipeline", "ctc", "closing"],
    ),

    KnowledgeTest(
        id="PIPE-003",
        name="Pipeline Velocity",
        category=KnowledgeCategory.PIPELINE,
        question="How do you measure pipeline velocity? What metrics indicate a healthy pipeline?",
        expected=ExpectedAnswer(
            keywords=["velocity", "cycle time", "days", "conversion", "pull-through"],
            patterns=[r"average.*days", r"time.*stage"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.CONCEPTUAL,
        tags=["pipeline", "metrics", "velocity"],
    ),

    KnowledgeTest(
        id="PIPE-004",
        name="Bottleneck Identification",
        category=KnowledgeCategory.PIPELINE,
        question="What are common bottlenecks in a mortgage pipeline and how do you identify them?",
        expected=ExpectedAnswer(
            keywords=["bottleneck", "aging", "stuck", "days"],
            patterns=[r"underwriting|processing|document", r"sla|threshold"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.APPLICATION,
        tags=["pipeline", "bottleneck", "analysis"],
    ),

    KnowledgeTest(
        id="PIPE-005",
        name="SLA Targets",
        category=KnowledgeCategory.PIPELINE,
        question="What are typical SLA targets for mortgage pipeline stages? Give specific timeframes.",
        expected=ExpectedAnswer(
            keywords=["days", "sla", "target"],
            patterns=[r"\d+\s*(?:day|hour|business day)", r"application.*\d+.*day"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["pipeline", "sla", "timing"],
    ),

    KnowledgeTest(
        id="PIPE-006",
        name="Pull-Through Rate",
        category=KnowledgeCategory.PIPELINE,
        question="What is pull-through rate and why is it important for mortgage operations?",
        expected=ExpectedAnswer(
            keywords=["pull-through", "conversion", "application", "funded", "percentage"],
            patterns=[r"application.*fund", r"\d+%|\d+\s*percent"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.CONCEPTUAL,
        tags=["pipeline", "metrics", "pull-through"],
    ),

    KnowledgeTest(
        id="PIPE-007",
        name="Lock Expiration",
        category=KnowledgeCategory.PIPELINE,
        question="What happens when a rate lock expires? How should this be managed in the pipeline?",
        expected=ExpectedAnswer(
            keywords=["lock", "expir", "rate", "extension", "renegotiate"],
            patterns=[r"lock.*expir", r"extension|re-?lock"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.PROCEDURAL,
        tags=["pipeline", "rate-lock", "risk"],
    ),

    KnowledgeTest(
        id="PIPE-008",
        name="Pipeline Fallout",
        category=KnowledgeCategory.PIPELINE,
        question="What causes pipeline fallout and how can it be minimized?",
        expected=ExpectedAnswer(
            keywords=["fallout", "cancel", "denied", "withdraw"],
            patterns=[r"fallout.*rate|reason", r"prevent|reduce|minimize"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.APPLICATION,
        tags=["pipeline", "fallout", "risk"],
    ),

    KnowledgeTest(
        id="PIPE-009",
        name="Docs Out Stage",
        category=KnowledgeCategory.PIPELINE,
        question="What does the 'Docs Out' stage mean? What documents are typically involved?",
        expected=ExpectedAnswer(
            keywords=["docs out", "closing", "package", "title", "disclosure"],
            patterns=[r"clos.*doc|package", r"title|escrow|notary"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["pipeline", "docs-out", "closing"],
    ),

    KnowledgeTest(
        id="PIPE-010",
        name="Resubmission Process",
        category=KnowledgeCategory.PIPELINE,
        question="When does a loan need to be resubmitted to underwriting? What triggers this?",
        expected=ExpectedAnswer(
            keywords=["resubmit", "underwriting", "change", "condition"],
            patterns=[r"material.*change|signific", r"income|asset|credit|property"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.PROCEDURAL,
        tags=["pipeline", "resubmission", "underwriting"],
    ),
]


# =============================================================================
# CRM TESTS (10 tests)
# =============================================================================

CRM_TESTS = [
    KnowledgeTest(
        id="CRM-001",
        name="CRM Core Entities",
        category=KnowledgeCategory.CRM,
        question="What are the main entities in a mortgage CRM system? Describe how they relate to each other.",
        expected=ExpectedAnswer(
            keywords=["loan", "contact", "lead", "user", "task", "document"],
            patterns=[r"loan.*borrow|contact", r"lead.*convert.*loan"],
        ),
        difficulty=TestDifficulty.BASIC,
        test_type=TestType.FACTUAL,
        tags=["crm", "entities", "data-model"],
    ),

    KnowledgeTest(
        id="CRM-002",
        name="Lead vs Contact",
        category=KnowledgeCategory.CRM,
        question="What is the difference between a Lead and a Contact in a mortgage CRM?",
        expected=ExpectedAnswer(
            keywords=["lead", "contact", "convert", "qualify"],
            patterns=[r"lead.*potential|prospect", r"contact.*customer|borrow"],
        ),
        difficulty=TestDifficulty.BASIC,
        test_type=TestType.CONCEPTUAL,
        tags=["crm", "lead", "contact"],
    ),

    KnowledgeTest(
        id="CRM-003",
        name="Task Management",
        category=KnowledgeCategory.CRM,
        question="How should tasks be managed in a mortgage CRM? What types of tasks are common?",
        expected=ExpectedAnswer(
            keywords=["task", "due", "priority", "assign", "complete"],
            patterns=[r"follow.*up|call|document", r"automat|trigger"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.PROCEDURAL,
        tags=["crm", "tasks", "workflow"],
    ),

    KnowledgeTest(
        id="CRM-004",
        name="Communication Tracking",
        category=KnowledgeCategory.CRM,
        question="Why is communication tracking important in a mortgage CRM? What should be tracked?",
        expected=ExpectedAnswer(
            keywords=["communication", "track", "email", "call", "sms", "history"],
            patterns=[r"compli|audit", r"borrower.*communic"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.CONCEPTUAL,
        tags=["crm", "communications", "compliance"],
    ),

    KnowledgeTest(
        id="CRM-005",
        name="Referral Tracking",
        category=KnowledgeCategory.CRM,
        question="How should referrals be tracked in a mortgage CRM? Why is this important?",
        expected=ExpectedAnswer(
            keywords=["referral", "source", "partner", "track"],
            patterns=[r"referral.*partner|agent|realtor", r"commission|attribution"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.PROCEDURAL,
        tags=["crm", "referrals", "tracking"],
    ),

    KnowledgeTest(
        id="CRM-006",
        name="Customer 360 View",
        category=KnowledgeCategory.CRM,
        question="What is a Customer 360 view and what information should it include for mortgage customers?",
        expected=ExpectedAnswer(
            keywords=["360", "customer", "loan", "history", "communication"],
            patterns=[r"complete|comprehensive|full.*view", r"loan.*history"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.CONCEPTUAL,
        tags=["crm", "customer-360", "view"],
    ),

    KnowledgeTest(
        id="CRM-007",
        name="Lead Scoring",
        category=KnowledgeCategory.CRM,
        question="How does lead scoring work in a mortgage CRM? What factors influence the score?",
        expected=ExpectedAnswer(
            keywords=["score", "lead", "qualify", "priority"],
            patterns=[r"credit|income|engag|intent", r"high.*priority|quality"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.CONCEPTUAL,
        tags=["crm", "leads", "scoring"],
    ),

    KnowledgeTest(
        id="CRM-008",
        name="Data Integration",
        category=KnowledgeCategory.CRM,
        question="What external systems should a mortgage CRM integrate with?",
        expected=ExpectedAnswer(
            keywords=["los", "integration", "crm"],
            patterns=[r"loan.*origination|encompass|byte", r"credit|pricing|title"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.FACTUAL,
        tags=["crm", "integrations", "los"],
    ),

    KnowledgeTest(
        id="CRM-009",
        name="Activity Entity",
        category=KnowledgeCategory.CRM,
        question="What is the Activity entity in a mortgage CRM? What types of activities are tracked?",
        expected=ExpectedAnswer(
            keywords=["activity", "event", "track", "timeline", "history"],
            patterns=[r"call|email|meeting|note", r"timeline|log"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["crm", "activity", "tracking"],
    ),

    KnowledgeTest(
        id="CRM-010",
        name="User Roles and Permissions",
        category=KnowledgeCategory.CRM,
        question="What user roles exist in a mortgage CRM? How do permissions differ between roles?",
        expected=ExpectedAnswer(
            keywords=["role", "permission", "loan officer", "processor", "admin"],
            patterns=[r"loan.*officer|processor|underwriter|manager", r"access|permission"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.FACTUAL,
        tags=["crm", "roles", "permissions"],
    ),
]


# =============================================================================
# LOAN TESTS (10 tests)
# =============================================================================

LOAN_TESTS = [
    KnowledgeTest(
        id="LOAN-001",
        name="Loan Types Overview",
        category=KnowledgeCategory.LOANS,
        question="What are the main types of mortgage loans? Briefly describe each.",
        expected=ExpectedAnswer(
            keywords=["conventional", "fha", "va", "usda", "jumbo"],
            patterns=[r"conventional.*conform", r"fha.*federal|insur", r"va.*veteran"],
        ),
        difficulty=TestDifficulty.BASIC,
        test_type=TestType.FACTUAL,
        tags=["loans", "types", "overview"],
    ),

    KnowledgeTest(
        id="LOAN-002",
        name="FHA Requirements",
        category=KnowledgeCategory.LOANS,
        question="What are the key requirements for an FHA loan? Include credit score and down payment.",
        expected=ExpectedAnswer(
            keywords=["fha", "credit", "down payment"],
            patterns=[r"580|500.*credit", r"3\.5%|3\.5\s*percent|ten\s*percent"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["loans", "fha", "requirements"],
    ),

    KnowledgeTest(
        id="LOAN-003",
        name="VA Loan Benefits",
        category=KnowledgeCategory.LOANS,
        question="What are the benefits of VA loans for veterans? What makes them unique?",
        expected=ExpectedAnswer(
            keywords=["va", "veteran", "zero down", "no pmi"],
            patterns=[r"0%|zero.*down|no.*down", r"no.*pmi|no.*mortgage insurance"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["loans", "va", "benefits"],
    ),

    KnowledgeTest(
        id="LOAN-004",
        name="DTI Calculation",
        category=KnowledgeCategory.LOANS,
        question="What is DTI (Debt-to-Income ratio) and how is it calculated? What are typical limits?",
        expected=ExpectedAnswer(
            keywords=["dti", "debt", "income", "ratio"],
            patterns=[r"monthly.*debt.*income", r"43%|45%|50%"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.CONCEPTUAL,
        tags=["loans", "dti", "calculation"],
    ),

    KnowledgeTest(
        id="LOAN-005",
        name="LTV Ratio",
        category=KnowledgeCategory.LOANS,
        question="What is LTV (Loan-to-Value ratio)? How does it affect mortgage terms?",
        expected=ExpectedAnswer(
            keywords=["ltv", "loan", "value", "property"],
            patterns=[r"loan.*property.*value", r"pmi|mortgage insurance|80%"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.CONCEPTUAL,
        tags=["loans", "ltv", "pmi"],
    ),

    KnowledgeTest(
        id="LOAN-006",
        name="Jumbo Loan Criteria",
        category=KnowledgeCategory.LOANS,
        question="What defines a jumbo loan? What are the typical requirements?",
        expected=ExpectedAnswer(
            keywords=["jumbo", "conforming", "limit"],
            patterns=[r"exceed.*conform|limit", r"higher.*credit|down"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["loans", "jumbo", "limits"],
    ),

    KnowledgeTest(
        id="LOAN-007",
        name="Refinance Types",
        category=KnowledgeCategory.LOANS,
        question="What are the different types of refinancing? When would each be appropriate?",
        expected=ExpectedAnswer(
            keywords=["refinance", "rate", "term", "cash-out"],
            patterns=[r"rate.*term|lower.*rate", r"cash.*out|equity"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.CONCEPTUAL,
        tags=["loans", "refinance", "types"],
    ),

    KnowledgeTest(
        id="LOAN-008",
        name="Loan Conditions",
        category=KnowledgeCategory.LOANS,
        question="What are loan conditions? What is the difference between PTD and PTC conditions?",
        expected=ExpectedAnswer(
            keywords=["condition", "ptd", "ptc", "document"],
            patterns=[r"prior.*doc|ptd", r"prior.*clos|ptc"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.FACTUAL,
        tags=["loans", "conditions", "underwriting"],
    ),

    KnowledgeTest(
        id="LOAN-009",
        name="USDA Loan Eligibility",
        category=KnowledgeCategory.LOANS,
        question="What are the eligibility requirements for USDA loans? What areas qualify?",
        expected=ExpectedAnswer(
            keywords=["usda", "rural", "income", "limit", "eligible"],
            patterns=[r"rural|eligib.*area", r"income.*limit|household"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["loans", "usda", "eligibility"],
    ),

    KnowledgeTest(
        id="LOAN-010",
        name="Non-QM Loans",
        category=KnowledgeCategory.LOANS,
        question="What are Non-QM loans? When are they used and what are the requirements?",
        expected=ExpectedAnswer(
            keywords=["non-qm", "qualified mortgage", "alternative", "self-employed"],
            patterns=[r"non.*qualify|non-?qm", r"bank.*statement|self.*employ|investor"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.FACTUAL,
        tags=["loans", "non-qm", "alternative"],
    ),
]


# =============================================================================
# COMPLIANCE TESTS (10 tests)
# =============================================================================

COMPLIANCE_TESTS = [
    KnowledgeTest(
        id="COMP-001",
        name="TRID Overview",
        category=KnowledgeCategory.COMPLIANCE,
        question="What is TRID and what are its main requirements?",
        expected=ExpectedAnswer(
            keywords=["trid", "loan estimate", "closing disclosure"],
            patterns=[r"tila.*respa|know.*before.*owe", r"3.*business.*day"],
            custom_validator=create_compliance_validator("trid"),
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["compliance", "trid", "disclosure"],
    ),

    KnowledgeTest(
        id="COMP-002",
        name="LE Timing Requirements",
        category=KnowledgeCategory.COMPLIANCE,
        question="When must a Loan Estimate be provided? What triggers the timing requirement?",
        expected=ExpectedAnswer(
            keywords=["loan estimate", "3", "business day", "application"],
            patterns=[r"3.*business.*day.*application", r"within.*3"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["compliance", "trid", "loan-estimate"],
    ),

    KnowledgeTest(
        id="COMP-003",
        name="CD Timing Requirements",
        category=KnowledgeCategory.COMPLIANCE,
        question="When must a Closing Disclosure be provided? What happens if there are changes?",
        expected=ExpectedAnswer(
            keywords=["closing disclosure", "3", "business day", "closing"],
            patterns=[r"3.*business.*day.*before.*clos", r"change.*redisclos"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["compliance", "trid", "closing-disclosure"],
    ),

    KnowledgeTest(
        id="COMP-004",
        name="Tolerance Violations",
        category=KnowledgeCategory.COMPLIANCE,
        question="What are fee tolerance categories in TRID? What happens when tolerances are violated?",
        expected=ExpectedAnswer(
            keywords=["tolerance", "zero", "10 percent", "cure"],
            patterns=[r"zero.*tolerance|no.*increase", r"10.*percent|ten.*percent"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.FACTUAL,
        tags=["compliance", "trid", "tolerance"],
    ),

    KnowledgeTest(
        id="COMP-005",
        name="RESPA Section 8",
        category=KnowledgeCategory.COMPLIANCE,
        question="What does RESPA Section 8 prohibit? Give examples of violations.",
        expected=ExpectedAnswer(
            keywords=["respa", "kickback", "referral fee"],
            patterns=[r"section.*8.*kickback", r"referral.*fee.*prohibit"],
            custom_validator=create_compliance_validator("respa"),
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["compliance", "respa", "kickback"],
    ),

    KnowledgeTest(
        id="COMP-006",
        name="Fair Lending",
        category=KnowledgeCategory.COMPLIANCE,
        question="What are the key fair lending regulations? What classes are protected?",
        expected=ExpectedAnswer(
            keywords=["ecoa", "fair", "discrimination", "protected"],
            patterns=[r"ecoa|fair.*hous", r"race|religion|national.*origin"],
            custom_validator=create_compliance_validator("ecoa"),
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["compliance", "fair-lending", "ecoa"],
    ),

    KnowledgeTest(
        id="COMP-007",
        name="HMDA Reporting",
        category=KnowledgeCategory.COMPLIANCE,
        question="What is HMDA and what data must be reported?",
        expected=ExpectedAnswer(
            keywords=["hmda", "home mortgage disclosure", "report", "data"],
            patterns=[r"hmda.*report", r"demographic|race|ethnicity|income"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.FACTUAL,
        tags=["compliance", "hmda", "reporting"],
    ),

    KnowledgeTest(
        id="COMP-008",
        name="State Compliance",
        category=KnowledgeCategory.COMPLIANCE,
        question="How do state regulations differ from federal requirements in mortgage lending?",
        expected=ExpectedAnswer(
            keywords=["state", "federal", "license", "regulation"],
            patterns=[r"state.*specific|vary", r"nmls|licens"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.CONCEPTUAL,
        tags=["compliance", "state", "licensing"],
    ),

    KnowledgeTest(
        id="COMP-009",
        name="Adverse Action Notice",
        category=KnowledgeCategory.COMPLIANCE,
        question="When is an adverse action notice required? What must it include?",
        expected=ExpectedAnswer(
            keywords=["adverse action", "denial", "notice", "reason"],
            patterns=[r"adverse.*action|denial", r"reason|30.*day"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["compliance", "adverse-action", "ecoa"],
    ),

    KnowledgeTest(
        id="COMP-010",
        name="Affiliated Business Disclosure",
        category=KnowledgeCategory.COMPLIANCE,
        question="What is an Affiliated Business Arrangement (AfBA) disclosure? When is it required?",
        expected=ExpectedAnswer(
            keywords=["affiliated", "business", "arrangement", "disclosure"],
            patterns=[r"afba|affiliat.*bus", r"title|apprais|insurance"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.FACTUAL,
        tags=["compliance", "respa", "afba"],
    ),
]


# =============================================================================
# TOOLS TESTS (15 tests)
# =============================================================================

TOOLS_TESTS = [
    KnowledgeTest(
        id="TOOL-001",
        name="Tool Count",
        category=KnowledgeCategory.TOOLS,
        question="How many tools are available in the Perennia AI system? What categories do they cover?",
        expected=ExpectedAnswer(
            keywords=["tool", "pipeline", "compliance", "lead"],
            patterns=[r"160|150|170", r"pipeline|compliance|lead|document"],
            custom_validator=create_tool_count_validator(100),
        ),
        difficulty=TestDifficulty.BASIC,
        test_type=TestType.FACTUAL,
        tags=["tools", "overview", "count"],
    ),

    KnowledgeTest(
        id="TOOL-002",
        name="Pipeline Metrics Tool",
        category=KnowledgeCategory.TOOLS,
        question="What tool should I use to get an overview of my loan pipeline?",
        expected=ExpectedAnswer(
            keywords=["get_pipeline_metrics", "pipeline", "overview"],
            patterns=[r"get_pipeline_metrics|pipeline.*metric"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.APPLICATION,
        tags=["tools", "pipeline", "metrics"],
    ),

    KnowledgeTest(
        id="TOOL-003",
        name="Compliance Check Tool",
        category=KnowledgeCategory.TOOLS,
        question="What tool checks TRID compliance for a loan?",
        expected=ExpectedAnswer(
            keywords=["check_trid_compliance", "trid", "compliance"],
            patterns=[r"check_trid|trid.*compliance"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.APPLICATION,
        tags=["tools", "compliance", "trid"],
    ),

    KnowledgeTest(
        id="TOOL-004",
        name="Missing Documents Tool",
        category=KnowledgeCategory.TOOLS,
        question="How do I find which documents are missing for a loan?",
        expected=ExpectedAnswer(
            keywords=["get_missing_documents", "document", "missing"],
            patterns=[r"get_missing|missing.*doc"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.APPLICATION,
        tags=["tools", "documents", "missing"],
    ),

    KnowledgeTest(
        id="TOOL-005",
        name="Lead Scoring Tool",
        category=KnowledgeCategory.TOOLS,
        question="What tool helps prioritize leads based on their likelihood to convert?",
        expected=ExpectedAnswer(
            keywords=["score_lead", "lead", "score", "prioritize"],
            patterns=[r"score_lead|lead.*scor"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.APPLICATION,
        tags=["tools", "leads", "scoring"],
    ),

    KnowledgeTest(
        id="TOOL-006",
        name="Loans by Status Tool",
        category=KnowledgeCategory.TOOLS,
        question="A loan officer needs to see which loans are stuck in underwriting. What tool should they use?",
        expected=ExpectedAnswer(
            keywords=["get_loans_by_status", "loans", "status"],
            patterns=[r"get_loans_by_status|loans.*status"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.APPLICATION,
        tags=["tools", "pipeline", "status"],
    ),

    KnowledgeTest(
        id="TOOL-007",
        name="Bottleneck Analysis Tool",
        category=KnowledgeCategory.TOOLS,
        question="What tool identifies where loans are getting stuck in the pipeline?",
        expected=ExpectedAnswer(
            keywords=["get_bottleneck_analysis", "bottleneck", "stuck"],
            patterns=[r"bottleneck|stuck|aging"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.APPLICATION,
        tags=["tools", "pipeline", "bottleneck"],
    ),

    KnowledgeTest(
        id="TOOL-008",
        name="Fair Lending Tool",
        category=KnowledgeCategory.TOOLS,
        question="What tool checks for fair lending compliance issues?",
        expected=ExpectedAnswer(
            keywords=["check_fair_lending", "fair", "lending", "discrimination"],
            patterns=[r"fair.*lending|check_fair"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.APPLICATION,
        tags=["tools", "compliance", "fair-lending"],
    ),

    KnowledgeTest(
        id="TOOL-009",
        name="Document Reminder Tool",
        category=KnowledgeCategory.TOOLS,
        question="How can I send a reminder to a borrower about missing documents?",
        expected=ExpectedAnswer(
            keywords=["send_document_reminder", "reminder", "document"],
            patterns=[r"send.*remind|document.*remind"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.APPLICATION,
        tags=["tools", "documents", "reminder"],
    ),

    KnowledgeTest(
        id="TOOL-010",
        name="Tolerance Violations Tool",
        category=KnowledgeCategory.TOOLS,
        question="What tool checks for fee tolerance violations between LE and CD?",
        expected=ExpectedAnswer(
            keywords=["check_tolerance_violations", "tolerance", "fee"],
            patterns=[r"tolerance|violation|le.*cd"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.APPLICATION,
        tags=["tools", "compliance", "tolerance"],
    ),

    KnowledgeTest(
        id="TOOL-011",
        name="Lead Follow-up Tool",
        category=KnowledgeCategory.TOOLS,
        question="What tool suggests the best next action for following up with a lead?",
        expected=ExpectedAnswer(
            keywords=["suggest_followup", "follow", "lead", "action"],
            patterns=[r"suggest.*follow|next.*action"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.APPLICATION,
        tags=["tools", "leads", "followup"],
    ),

    KnowledgeTest(
        id="TOOL-012",
        name="Conversion Rate Tool",
        category=KnowledgeCategory.TOOLS,
        question="What tool calculates conversion rates through pipeline stages?",
        expected=ExpectedAnswer(
            keywords=["calculate_conversion_rates", "conversion", "rate"],
            patterns=[r"conversion.*rate|calculate.*convers"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.APPLICATION,
        tags=["tools", "pipeline", "conversion"],
    ),

    KnowledgeTest(
        id="TOOL-013",
        name="Escalation Tool",
        category=KnowledgeCategory.TOOLS,
        question="How do I escalate a document or condition issue to a manager?",
        expected=ExpectedAnswer(
            keywords=["escalate_issue", "escalate", "manager"],
            patterns=[r"escalat|manager|supervisor"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.APPLICATION,
        tags=["tools", "escalation", "management"],
    ),

    KnowledgeTest(
        id="TOOL-014",
        name="Closing Timeline Tool",
        category=KnowledgeCategory.TOOLS,
        question="What tool predicts when a loan will close based on current progress?",
        expected=ExpectedAnswer(
            keywords=["predict_closing_timeline", "predict", "closing", "timeline"],
            patterns=[r"predict.*clos|timeline|forecast"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.APPLICATION,
        tags=["tools", "pipeline", "prediction"],
    ),

    KnowledgeTest(
        id="TOOL-015",
        name="High-Risk Operations",
        category=KnowledgeCategory.TOOLS,
        question="Which tool operations are considered high-risk and require approval?",
        expected=ExpectedAnswer(
            keywords=["risk", "approval", "high"],
            patterns=[r"send.*message|schedul|draft|modif", r"approval.*required"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.FACTUAL,
        tags=["tools", "risk", "approval"],
    ),
]


# =============================================================================
# WORKFLOW TESTS (10 tests)
# =============================================================================

WORKFLOW_TESTS = [
    KnowledgeTest(
        id="WORK-001",
        name="New Application Workflow",
        category=KnowledgeCategory.WORKFLOWS,
        question="What is the workflow when a new loan application is received?",
        expected=ExpectedAnswer(
            keywords=["application", "disclosure", "document", "process"],
            patterns=[r"application.*disclosure", r"gather.*document|request.*doc"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.PROCEDURAL,
        tags=["workflow", "application", "process"],
    ),

    KnowledgeTest(
        id="WORK-002",
        name="Document Collection Workflow",
        category=KnowledgeCategory.WORKFLOWS,
        question="Describe the document collection workflow. What happens when documents are missing?",
        expected=ExpectedAnswer(
            keywords=["document", "request", "reminder", "missing"],
            patterns=[r"request.*document|missing.*doc", r"remind|follow.*up|escalat"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.PROCEDURAL,
        tags=["workflow", "documents", "collection"],
    ),

    KnowledgeTest(
        id="WORK-003",
        name="Underwriting Workflow",
        category=KnowledgeCategory.WORKFLOWS,
        question="What happens during the underwriting process? What are possible outcomes?",
        expected=ExpectedAnswer(
            keywords=["underwriting", "condition", "approve", "deny"],
            patterns=[r"review|analyz|verif", r"approv.*condition|deny|suspend"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.PROCEDURAL,
        tags=["workflow", "underwriting", "process"],
    ),

    KnowledgeTest(
        id="WORK-004",
        name="Clear to Close Workflow",
        category=KnowledgeCategory.WORKFLOWS,
        question="What must happen before a loan can be cleared to close?",
        expected=ExpectedAnswer(
            keywords=["clear to close", "condition", "disclosure", "appraisal"],
            patterns=[r"condition.*clear|satisf", r"closing.*disclosure|schedule"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.PROCEDURAL,
        tags=["workflow", "ctc", "closing"],
    ),

    KnowledgeTest(
        id="WORK-005",
        name="Lead Follow-up Workflow",
        category=KnowledgeCategory.WORKFLOWS,
        question="What is an effective lead follow-up workflow? How should follow-ups be timed?",
        expected=ExpectedAnswer(
            keywords=["lead", "follow", "contact", "nurture"],
            patterns=[r"day|hour|timing", r"sequence|cadence|automat"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.PROCEDURAL,
        tags=["workflow", "leads", "followup"],
    ),

    KnowledgeTest(
        id="WORK-006",
        name="Escalation Workflow",
        category=KnowledgeCategory.WORKFLOWS,
        question="When and how should issues be escalated in the loan process?",
        expected=ExpectedAnswer(
            keywords=["escalate", "manager", "issue", "delay"],
            patterns=[r"sla|threshold|stuck", r"manager|supervisor|team lead"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.PROCEDURAL,
        tags=["workflow", "escalation", "management"],
    ),

    KnowledgeTest(
        id="WORK-007",
        name="Post-Close Workflow",
        category=KnowledgeCategory.WORKFLOWS,
        question="What happens after a loan closes? What post-close activities are required?",
        expected=ExpectedAnswer(
            keywords=["post-close", "fund", "record", "servic"],
            patterns=[r"fund.*record|record.*county", r"servic|transfer|thank"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.PROCEDURAL,
        tags=["workflow", "post-close", "funding"],
    ),

    KnowledgeTest(
        id="WORK-008",
        name="Referral Partner Workflow",
        category=KnowledgeCategory.WORKFLOWS,
        question="How should referrals from partners (realtors, builders) be handled?",
        expected=ExpectedAnswer(
            keywords=["referral", "partner", "realtor", "track"],
            patterns=[r"refer.*partner|realtor|agent", r"track|attribute|commiss"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.PROCEDURAL,
        tags=["workflow", "referrals", "partners"],
    ),

    KnowledgeTest(
        id="WORK-009",
        name="Rate Lock Workflow",
        category=KnowledgeCategory.WORKFLOWS,
        question="What is the rate lock workflow? When should a rate be locked?",
        expected=ExpectedAnswer(
            keywords=["rate lock", "lock", "commitment", "expiration"],
            patterns=[r"rate.*lock|lock.*rate", r"expir|extension|float"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.PROCEDURAL,
        tags=["workflow", "rate-lock", "pricing"],
    ),

    KnowledgeTest(
        id="WORK-010",
        name="Condition Clearing Workflow",
        category=KnowledgeCategory.WORKFLOWS,
        question="How are underwriting conditions cleared? Who is responsible?",
        expected=ExpectedAnswer(
            keywords=["condition", "clear", "underwriter", "processor"],
            patterns=[r"condition.*clear|satisf", r"processor|underwriter|document"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.PROCEDURAL,
        tags=["workflow", "conditions", "underwriting"],
    ),
]


# =============================================================================
# COMMUNICATION TESTS (5 tests)
# =============================================================================

COMMUNICATION_TESTS = [
    KnowledgeTest(
        id="COMM-001",
        name="Communication Channels",
        category=KnowledgeCategory.COMMUNICATION,
        question="What communication channels should a mortgage CRM support?",
        expected=ExpectedAnswer(
            keywords=["email", "sms", "phone", "call", "text"],
            patterns=[r"email.*sms|phone|call", r"channel|communic"],
        ),
        difficulty=TestDifficulty.BASIC,
        test_type=TestType.FACTUAL,
        tags=["communication", "channels", "overview"],
    ),

    KnowledgeTest(
        id="COMM-002",
        name="Email Templates",
        category=KnowledgeCategory.COMMUNICATION,
        question="What types of email templates are essential for mortgage communications?",
        expected=ExpectedAnswer(
            keywords=["template", "email", "welcome", "status", "document"],
            patterns=[r"template|automat", r"welcome|status|document.*request"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["communication", "email", "templates"],
    ),

    KnowledgeTest(
        id="COMM-003",
        name="SMS Best Practices",
        category=KnowledgeCategory.COMMUNICATION,
        question="What are best practices for SMS communication in mortgage lending?",
        expected=ExpectedAnswer(
            keywords=["sms", "text", "consent", "opt-in"],
            patterns=[r"consent|opt-?in|tcpa", r"short|concise|urgent"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.CONCEPTUAL,
        tags=["communication", "sms", "compliance"],
    ),

    KnowledgeTest(
        id="COMM-004",
        name="Status Update Communication",
        category=KnowledgeCategory.COMMUNICATION,
        question="How should borrowers be notified about loan status changes?",
        expected=ExpectedAnswer(
            keywords=["status", "update", "notify", "borrower"],
            patterns=[r"status.*update|notify|automat", r"email|sms|portal"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.PROCEDURAL,
        tags=["communication", "status", "notification"],
    ),

    KnowledgeTest(
        id="COMM-005",
        name="Communication Compliance",
        category=KnowledgeCategory.COMMUNICATION,
        question="What compliance considerations apply to mortgage communications?",
        expected=ExpectedAnswer(
            keywords=["compliance", "tcpa", "can-spam", "disclosure"],
            patterns=[r"tcpa|can-?spam|consent", r"record|archive|audit"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.FACTUAL,
        tags=["communication", "compliance", "regulations"],
    ),
]


# =============================================================================
# INTEGRATION TESTS (5 tests)
# =============================================================================

INTEGRATION_TESTS = [
    KnowledgeTest(
        id="INTG-001",
        name="LOS Integration",
        category=KnowledgeCategory.INTEGRATIONS,
        question="How does a CRM typically integrate with a Loan Origination System (LOS)?",
        expected=ExpectedAnswer(
            keywords=["los", "integration", "sync", "data"],
            patterns=[r"encompass|byte|los", r"sync|api|push|pull"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.CONCEPTUAL,
        tags=["integrations", "los", "sync"],
    ),

    KnowledgeTest(
        id="INTG-002",
        name="Credit Integration",
        category=KnowledgeCategory.INTEGRATIONS,
        question="How does credit report integration work in mortgage systems?",
        expected=ExpectedAnswer(
            keywords=["credit", "report", "pull", "score"],
            patterns=[r"credit.*report|bureau", r"soft.*pull|hard.*pull|score"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.CONCEPTUAL,
        tags=["integrations", "credit", "bureaus"],
    ),

    KnowledgeTest(
        id="INTG-003",
        name="Pricing Integration",
        category=KnowledgeCategory.INTEGRATIONS,
        question="How does pricing engine integration work for rate quotes?",
        expected=ExpectedAnswer(
            keywords=["pricing", "rate", "lock", "engine"],
            patterns=[r"pricing.*engine|optimal.*blue", r"rate.*lock|quote"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.CONCEPTUAL,
        tags=["integrations", "pricing", "rates"],
    ),

    KnowledgeTest(
        id="INTG-004",
        name="Document Integration",
        category=KnowledgeCategory.INTEGRATIONS,
        question="What document management integrations are important for mortgage operations?",
        expected=ExpectedAnswer(
            keywords=["document", "integration", "upload", "store"],
            patterns=[r"docutech|blend|floify", r"e-?sign|upload|ocr"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["integrations", "documents", "management"],
    ),

    KnowledgeTest(
        id="INTG-005",
        name="Title and Appraisal Integration",
        category=KnowledgeCategory.INTEGRATIONS,
        question="How do title and appraisal integrations work in the mortgage process?",
        expected=ExpectedAnswer(
            keywords=["title", "appraisal", "order", "integration"],
            patterns=[r"title.*order|apprais", r"amc|order.*manag"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.CONCEPTUAL,
        tags=["integrations", "title", "appraisal"],
    ),
]


# =============================================================================
# REPORTING TESTS (5 tests)
# =============================================================================

REPORTING_TESTS = [
    KnowledgeTest(
        id="REPT-001",
        name="Pipeline Reports",
        category=KnowledgeCategory.REPORTING,
        question="What are the essential pipeline reports for mortgage operations?",
        expected=ExpectedAnswer(
            keywords=["pipeline", "report", "volume", "status"],
            patterns=[r"pipeline.*report|status.*report", r"aging|conversion|volume"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["reporting", "pipeline", "management"],
    ),

    KnowledgeTest(
        id="REPT-002",
        name="Loan Officer Reports",
        category=KnowledgeCategory.REPORTING,
        question="What reports help track loan officer performance?",
        expected=ExpectedAnswer(
            keywords=["loan officer", "performance", "report", "metrics"],
            patterns=[r"lo.*performance|loan.*officer", r"volume|conversion|cycle"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["reporting", "lo", "performance"],
    ),

    KnowledgeTest(
        id="REPT-003",
        name="Compliance Reports",
        category=KnowledgeCategory.REPORTING,
        question="What compliance reports are needed for mortgage lending?",
        expected=ExpectedAnswer(
            keywords=["compliance", "report", "hmda", "fair lending"],
            patterns=[r"hmda|fair.*lending|compli", r"audit|regulat"],
        ),
        difficulty=TestDifficulty.ADVANCED,
        test_type=TestType.FACTUAL,
        tags=["reporting", "compliance", "regulatory"],
    ),

    KnowledgeTest(
        id="REPT-004",
        name="Lead Analytics",
        category=KnowledgeCategory.REPORTING,
        question="What lead analytics and reports should be available?",
        expected=ExpectedAnswer(
            keywords=["lead", "analytics", "source", "conversion"],
            patterns=[r"lead.*source|roi|conversion", r"campaign|marketing"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["reporting", "leads", "analytics"],
    ),

    KnowledgeTest(
        id="REPT-005",
        name="SLA Tracking Reports",
        category=KnowledgeCategory.REPORTING,
        question="How should SLA compliance be tracked and reported?",
        expected=ExpectedAnswer(
            keywords=["sla", "tracking", "report", "threshold"],
            patterns=[r"sla.*track|threshold", r"breach|exception|aging"],
        ),
        difficulty=TestDifficulty.INTERMEDIATE,
        test_type=TestType.FACTUAL,
        tags=["reporting", "sla", "tracking"],
    ),
]


# =============================================================================
# TEST AGGREGATION
# =============================================================================

ALL_TESTS = (
    PIPELINE_TESTS +
    CRM_TESTS +
    LOAN_TESTS +
    COMPLIANCE_TESTS +
    TOOLS_TESTS +
    WORKFLOW_TESTS +
    COMMUNICATION_TESTS +
    INTEGRATION_TESTS +
    REPORTING_TESTS
)


def get_tests_by_category(category: KnowledgeCategory) -> list:
    """Get all tests for a specific category."""
    return [t for t in ALL_TESTS if t.category == category]


def get_tests_by_difficulty(difficulty: TestDifficulty) -> list:
    """Get all tests of a specific difficulty."""
    return [t for t in ALL_TESTS if t.difficulty == difficulty]


def get_tests_by_tag(tag: str) -> list:
    """Get all tests with a specific tag."""
    return [t for t in ALL_TESTS if tag.lower() in [t.lower() for t in t.tags]]


def get_test_count() -> int:
    """Get total count of tests."""
    return len(ALL_TESTS)


def get_category_counts() -> dict:
    """Get count of tests by category."""
    counts = {}
    for cat in KnowledgeCategory:
        tests = get_tests_by_category(cat)
        if tests:
            counts[cat.value] = len(tests)
    counts["total"] = len(ALL_TESTS)
    return counts


def get_tests_by_type(test_type) -> list:
    """Get all tests of a specific type (e.g., ToolUsageTest)."""
    return [t for t in ALL_TESTS if isinstance(t, test_type)]


# Print test count when module is loaded
if __name__ == "__main__":
    counts = get_test_count()
    print("=" * 60)
    print("PERENNIA AI KNOWLEDGE TEST SUITE")
    print("=" * 60)
    print("\nTest counts by category:")
    for cat, count in counts.items():
        if cat != "total":
            print(f"  {cat:20} {count:3} tests")
    print("-" * 35)
    print(f"  {'TOTAL':20} {counts['total']:3} tests")
    print()

    # Count by test type
    tool_tests = len([t for t in ALL_TESTS if isinstance(t, ToolUsageTest)])
    data_tests = len([t for t in ALL_TESTS if isinstance(t, DataAccuracyTest)])
    qa_tests = counts["total"] - tool_tests - data_tests

    print("Test types:")
    print(f"  Question/Answer:   {qa_tests}")
    print(f"  Tool Usage:        {tool_tests}")
    print(f"  Data Accuracy:     {data_tests}")
