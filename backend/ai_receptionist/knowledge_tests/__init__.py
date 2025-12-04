"""
================================================================================
PERENNIA AI - KNOWLEDGE TEST SUITE
================================================================================
Test what the AI knows about your mortgage pipeline and CRM.

Usage:
    python run_knowledge_tests.py                    # Run all tests
    python run_knowledge_tests.py --category pipeline  # Test pipeline only
    python run_knowledge_tests.py --interactive      # Interactive mode
    python run_knowledge_tests.py --quick            # Quick summary only
================================================================================
"""

from .AI_KNOWLEDGE_TEST_PART1_FRAMEWORK import (
    KnowledgeCategory,
    TestDifficulty,
    TestType,
    TestStatus,
    KnowledgeTest,
    TestResult,
    ExpectedAnswer,
    CategoryReport,
    FullReport,
    MortgageKnowledgeBase,
)

from .AI_KNOWLEDGE_TEST_PART2_TESTCASES import (
    ALL_TESTS,
    PIPELINE_TESTS,
    CRM_TESTS,
    LOAN_TESTS,
    COMPLIANCE_TESTS,
    TOOLS_TESTS,
    WORKFLOW_TESTS,
    COMMUNICATION_TESTS,
    INTEGRATION_TESTS,
    REPORTING_TESTS,
    get_tests_by_category,
    get_tests_by_difficulty,
    get_tests_by_tag,
    get_test_count,
)

from .AI_KNOWLEDGE_TEST_PART3_RUNNER import (
    BaseAdapter,
    ClaudeAdapter,
    OpenAIAdapter,
    MockAdapter,
    TestRunner,
    ReportGenerator,
    quick_test,
    test_category,
)

__all__ = [
    # Framework
    "KnowledgeCategory",
    "TestDifficulty",
    "TestType",
    "TestStatus",
    "KnowledgeTest",
    "TestResult",
    "ExpectedAnswer",
    "CategoryReport",
    "FullReport",
    "MortgageKnowledgeBase",
    # Test cases
    "ALL_TESTS",
    "PIPELINE_TESTS",
    "CRM_TESTS",
    "LOAN_TESTS",
    "COMPLIANCE_TESTS",
    "TOOLS_TESTS",
    "WORKFLOW_TESTS",
    "COMMUNICATION_TESTS",
    "INTEGRATION_TESTS",
    "REPORTING_TESTS",
    "get_tests_by_category",
    "get_tests_by_difficulty",
    "get_tests_by_tag",
    "get_test_count",
    # Runner
    "BaseAdapter",
    "ClaudeAdapter",
    "OpenAIAdapter",
    "MockAdapter",
    "TestRunner",
    "ReportGenerator",
    "quick_test",
    "test_category",
]
