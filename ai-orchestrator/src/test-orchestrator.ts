import * as dotenv from "dotenv";
dotenv.config();

import { processMessage, UserMessage } from "./ai/orchestrator/smartAssistant";

// Test configuration
const TEST_AUTH_TOKEN = process.env.TEST_AUTH_TOKEN || "";

interface TestCase {
  name: string;
  message: UserMessage;
  expectedCategory?: string;
  expectedAction?: string;
  checkLowConfidence?: boolean;
  checkEscalation?: boolean;
}

const testCases: TestCase[] = [
  // Test 1: Basic question routing & grounding
  {
    name: "Loan Status Query",
    message: {
      userId: "test-user",
      sessionId: "test-session-1",
      text: "What is the status of my refinance loan?",
      channel: "web",
      metadata: {
        authToken: TEST_AUTH_TOKEN,
        activeLoanId: "1"
      }
    },
    expectedCategory: "LOAN_STATUS"
  },

  // Test 2: Guideline question
  {
    name: "Mortgage Guideline Query",
    message: {
      userId: "test-user",
      sessionId: "test-session-2",
      text: "What's the max seller concession on an investment property?",
      channel: "web",
      metadata: {
        authToken: TEST_AUTH_TOKEN
      }
    },
    expectedCategory: "MORTGAGE_GUIDELINE"
  },

  // Test 3: Task creation workflow
  {
    name: "Task Creation",
    message: {
      userId: "test-user",
      sessionId: "test-session-3",
      text: "Set a follow-up task to call John tomorrow.",
      channel: "web",
      metadata: {
        authToken: TEST_AUTH_TOKEN,
        activeLeadId: "1"
      }
    },
    expectedAction: "CREATE_TASK"
  },

  // Test 4: Channel behavior - SMS
  {
    name: "SMS Channel Format",
    message: {
      userId: "test-user",
      sessionId: "test-session-4",
      text: "What is the status of my refinance loan?",
      channel: "sms",
      metadata: {
        authToken: TEST_AUTH_TOKEN,
        activeLoanId: "1"
      }
    },
    expectedCategory: "LOAN_STATUS"
  },

  // Test 5: Channel behavior - Email
  {
    name: "Email Channel Format",
    message: {
      userId: "test-user",
      sessionId: "test-session-5",
      text: "What is the status of my refinance loan?",
      channel: "email",
      metadata: {
        authToken: TEST_AUTH_TOKEN,
        activeLoanId: "1"
      }
    },
    expectedCategory: "LOAN_STATUS"
  },

  // Test 6: Ambiguous input - should ask for clarification
  {
    name: "Ambiguous Query - Clarification",
    message: {
      userId: "test-user",
      sessionId: "test-session-6",
      text: "Should I refinance?",
      channel: "web",
      metadata: {
        authToken: TEST_AUTH_TOKEN
      }
    },
    expectedCategory: "PORTFOLIO_ANALYSIS"
  },

  // Test 7: Compliance/risk escalation
  {
    name: "Compliance Escalation",
    message: {
      userId: "test-user",
      sessionId: "test-session-7",
      text: "Can I skip the income verification for this borrower?",
      channel: "web",
      metadata: {
        authToken: TEST_AUTH_TOKEN
      }
    },
    checkEscalation: true
  },

  // Test 8: Scheduling
  {
    name: "Appointment Scheduling",
    message: {
      userId: "test-user",
      sessionId: "test-session-8",
      text: "Schedule a call with the client for next Tuesday at 2pm",
      channel: "web",
      metadata: {
        authToken: TEST_AUTH_TOKEN,
        activeLeadId: "1"
      }
    },
    expectedCategory: "APPOINTMENT_SCHEDULING",
    expectedAction: "SCHEDULE_APPOINTMENT"
  }
];

async function runTests() {
  console.log("=".repeat(60));
  console.log("AI ORCHESTRATOR TEST SUITE");
  console.log("=".repeat(60));
  console.log("");

  let passed = 0;
  let failed = 0;
  const results: { name: string; status: string; error?: string; details?: any }[] = [];

  for (const testCase of testCases) {
    console.log(`\n${"─".repeat(60)}`);
    console.log(`TEST: ${testCase.name}`);
    console.log(`Query: "${testCase.message.text}"`);
    console.log(`Channel: ${testCase.message.channel}`);
    console.log(`${"─".repeat(60)}`);

    try {
      const startTime = Date.now();
      const result = await processMessage(testCase.message);
      const duration = Date.now() - startTime;

      console.log(`\nResult (${duration}ms):`);
      console.log(`  Category: ${result.meta?.category}`);
      console.log(`  Confidence: ${(result.confidence * 100).toFixed(1)}%`);
      console.log(`  Risk Level: ${result.meta?.evaluation?.riskLevel}`);
      console.log(`  Escalation Required: ${result.escalationRequired}`);
      console.log(`  Actions Executed: ${result.actionsExecuted?.length || 0}`);
      console.log(`  Pending Actions: ${result.meta?.pendingActions?.length || 0}`);
      console.log(`\nAnswer (truncated):`);
      console.log(`  ${result.answer.slice(0, 200)}${result.answer.length > 200 ? "..." : ""}`);

      // Validate expectations
      let testPassed = true;
      const errors: string[] = [];

      if (testCase.expectedCategory && result.meta?.category !== testCase.expectedCategory) {
        testPassed = false;
        errors.push(`Expected category ${testCase.expectedCategory}, got ${result.meta?.category}`);
      }

      if (testCase.expectedAction) {
        const allActions = [
          ...(result.actionsExecuted || []),
          ...(result.meta?.pendingActions || [])
        ];
        const hasAction = allActions.some(a => a.type === testCase.expectedAction);
        if (!hasAction) {
          testPassed = false;
          errors.push(`Expected action ${testCase.expectedAction} not found`);
        }
      }

      if (testCase.checkLowConfidence && result.confidence > 0.6) {
        testPassed = false;
        errors.push(`Expected low confidence, got ${result.confidence}`);
      }

      if (testCase.checkEscalation && !result.escalationRequired) {
        testPassed = false;
        errors.push(`Expected escalation, but not flagged`);
      }

      if (testPassed) {
        console.log(`\n✅ PASSED`);
        passed++;
        results.push({ name: testCase.name, status: "PASSED", details: result.meta });
      } else {
        console.log(`\n❌ FAILED`);
        errors.forEach(e => console.log(`  - ${e}`));
        failed++;
        results.push({ name: testCase.name, status: "FAILED", error: errors.join("; "), details: result.meta });
      }

    } catch (error) {
      console.log(`\n❌ ERROR`);
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.log(`  ${errorMessage}`);
      failed++;
      results.push({ name: testCase.name, status: "ERROR", error: errorMessage });
    }
  }

  // Summary
  console.log(`\n${"=".repeat(60)}`);
  console.log("TEST SUMMARY");
  console.log(`${"=".repeat(60)}`);
  console.log(`Total: ${testCases.length}`);
  console.log(`Passed: ${passed}`);
  console.log(`Failed: ${failed}`);
  console.log(`Success Rate: ${((passed / testCases.length) * 100).toFixed(1)}%`);
  console.log(`${"=".repeat(60)}\n`);

  // Return results for CI integration
  return {
    total: testCases.length,
    passed,
    failed,
    results
  };
}

// Run tests
runTests()
  .then(summary => {
    if (summary.failed > 0) {
      process.exit(1);
    }
  })
  .catch(error => {
    console.error("Test suite failed:", error);
    process.exit(1);
  });
