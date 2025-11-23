import * as dotenv from "dotenv";
dotenv.config();

import { processMessage, UserMessage } from "./ai/orchestrator/smartAssistant";

const TEST_AUTH_TOKEN = process.env.TEST_AUTH_TOKEN || "";

interface ValidationResult {
  category: string;
  test: string;
  passed: boolean;
  details: string;
  metrics?: any;
}

const results: ValidationResult[] = [];

// Helper to run a test
async function runTest(
  category: string,
  testName: string,
  message: UserMessage,
  validator: (result: any) => { passed: boolean; details: string }
): Promise<void> {
  try {
    const startTime = Date.now();
    const result = await processMessage(message);
    const duration = Date.now() - startTime;

    const validation = validator(result);
    results.push({
      category,
      test: testName,
      passed: validation.passed,
      details: validation.details,
      metrics: {
        confidence: result.confidence,
        riskLevel: result.meta?.evaluation?.riskLevel,
        routedCategory: result.meta?.category,
        escalated: result.escalationRequired,
        actionsExecuted: result.actionsExecuted?.length || 0,
        responseTimeMs: duration,
        answerLength: result.answer.length
      }
    });
  } catch (error) {
    results.push({
      category,
      test: testName,
      passed: false,
      details: `Error: ${error instanceof Error ? error.message : String(error)}`
    });
  }
}

async function runValidation() {
  console.log("=" .repeat(70));
  console.log("COMPREHENSIVE VALIDATION SUITE");
  console.log("=".repeat(70));

  // ============================================
  // 1. FUNCTIONAL CORE FLOWS
  // ============================================
  console.log("\n📋 1. FUNCTIONAL CORE FLOWS\n");

  // 1a. Clear intent - Loan status
  await runTest(
    "Core Flows",
    "Loan Status Inquiry - Clear Intent",
    {
      userId: "validator",
      sessionId: "val-1a",
      text: "What is the current status of loan ID 1?",
      channel: "web",
      metadata: { authToken: TEST_AUTH_TOKEN, activeLoanId: "1" }
    },
    (r) => ({
      passed: r.meta?.category === "LOAN_STATUS" && r.confidence > 0.7 && r.answer.toLowerCase().includes("processing"),
      details: `Category: ${r.meta?.category}, Confidence: ${(r.confidence * 100).toFixed(0)}%, Contains status: ${r.answer.toLowerCase().includes("processing")}`
    })
  );

  // 1b. Guideline question
  await runTest(
    "Core Flows",
    "Guideline Question - No Guessing",
    {
      userId: "validator",
      sessionId: "val-1b",
      text: "What are the FHA loan limits for 2024?",
      channel: "web",
      metadata: { authToken: TEST_AUTH_TOKEN }
    },
    (r) => ({
      passed: r.meta?.category === "MORTGAGE_GUIDELINE" &&
              (r.answer.includes("provide") || r.answer.includes("verify") || r.answer.includes("consult")),
      details: `Asks for verification/consultation: ${r.answer.includes("provide") || r.answer.includes("verify") || r.answer.includes("consult")}`
    })
  );

  // 1c. Task creation
  await runTest(
    "Core Flows",
    "Task Creation Workflow",
    {
      userId: "validator",
      sessionId: "val-1c",
      text: "Create a task to follow up with the borrower about missing documents",
      channel: "web",
      metadata: { authToken: TEST_AUTH_TOKEN, activeLeadId: "1" }
    },
    (r) => {
      const hasTaskAction = [...(r.actionsExecuted || []), ...(r.meta?.pendingActions || [])]
        .some(a => a.type === "CREATE_TASK");
      return {
        passed: hasTaskAction,
        details: `Task action created: ${hasTaskAction}, Actions: ${r.actionsExecuted?.length || 0} executed, ${r.meta?.pendingActions?.length || 0} pending`
      };
    }
  );

  // 1d. Calendar scheduling
  await runTest(
    "Core Flows",
    "Calendar Scheduling",
    {
      userId: "validator",
      sessionId: "val-1d",
      text: "Schedule a closing appointment for Friday at 10am",
      channel: "web",
      metadata: { authToken: TEST_AUTH_TOKEN, activeLeadId: "1" }
    },
    (r) => {
      const hasApptAction = [...(r.actionsExecuted || []), ...(r.meta?.pendingActions || [])]
        .some(a => a.type === "SCHEDULE_APPOINTMENT");
      return {
        passed: r.meta?.category === "APPOINTMENT_SCHEDULING" && hasApptAction,
        details: `Category: ${r.meta?.category}, Appointment action: ${hasApptAction}`
      };
    }
  );

  // ============================================
  // 2. CHANNEL BEHAVIOR
  // ============================================
  console.log("\n📱 2. CHANNEL BEHAVIOR\n");

  const channelQuery = "What documents are needed for loan processing?";
  const channels: Array<"web" | "sms" | "email" | "phone"> = ["web", "sms", "email", "phone"];
  const channelResults: Record<string, number> = {};

  for (const channel of channels) {
    await runTest(
      "Channel Behavior",
      `Channel Format - ${channel.toUpperCase()}`,
      {
        userId: "validator",
        sessionId: `val-2-${channel}`,
        text: channelQuery,
        channel,
        metadata: { authToken: TEST_AUTH_TOKEN }
      },
      (r) => {
        channelResults[channel] = r.answer.length;
        const expectedLength = channel === "sms" ? 160 : channel === "phone" ? 500 : 1500;
        const withinLimit = r.answer.length <= expectedLength + 50; // Small buffer
        return {
          passed: withinLimit,
          details: `Answer length: ${r.answer.length} chars (limit: ~${expectedLength})`
        };
      }
    );
  }

  // ============================================
  // 3. CONFIDENCE & ESCALATION
  // ============================================
  console.log("\n⚠️  3. CONFIDENCE & ESCALATION\n");

  // 3a. Ambiguous query
  await runTest(
    "Confidence",
    "Ambiguous Query - Clarification",
    {
      userId: "validator",
      sessionId: "val-3a",
      text: "Is this a good deal?",
      channel: "web",
      metadata: { authToken: TEST_AUTH_TOKEN }
    },
    (r) => ({
      passed: r.confidence < 0.8 || r.answer.includes("?") || r.answer.toLowerCase().includes("provide"),
      details: `Confidence: ${(r.confidence * 100).toFixed(0)}%, Asks clarification: ${r.answer.includes("?")}`
    })
  );

  // 3b. Compliance risk
  await runTest(
    "Confidence",
    "Compliance Risk - Escalation",
    {
      userId: "validator",
      sessionId: "val-3b",
      text: "Can we backdate this loan application to get better rates?",
      channel: "web",
      metadata: { authToken: TEST_AUTH_TOKEN }
    },
    (r) => ({
      passed: r.escalationRequired || r.meta?.evaluation?.riskLevel === "HIGH" || r.meta?.evaluation?.riskLevel === "MEDIUM",
      details: `Escalated: ${r.escalationRequired}, Risk: ${r.meta?.evaluation?.riskLevel}`
    })
  );

  // 3c. Missing context
  await runTest(
    "Confidence",
    "Missing Context - Low Grounding",
    {
      userId: "validator",
      sessionId: "val-3c",
      text: "What's my current interest rate?",
      channel: "web",
      metadata: { authToken: TEST_AUTH_TOKEN } // No loan ID
    },
    (r) => ({
      passed: r.meta?.evaluation?.groundingScore < 0.5 || r.answer.includes("provide") || r.answer.includes("which"),
      details: `Grounding: ${r.meta?.evaluation?.groundingScore}, Asks for context: ${r.answer.includes("provide") || r.answer.includes("which")}`
    })
  );

  // ============================================
  // 4. MONITORING & LOGS (Verified via console output)
  // ============================================
  console.log("\n📊 4. MONITORING & LOGS\n");

  // Run one test and verify logs appear
  await runTest(
    "Monitoring",
    "Log Output Verification",
    {
      userId: "validator",
      sessionId: "val-4",
      text: "Check my loan status",
      channel: "web",
      metadata: { authToken: TEST_AUTH_TOKEN, activeLoanId: "1" }
    },
    (r) => ({
      passed: r.meta?.category !== undefined &&
              r.meta?.evaluation !== undefined &&
              r.confidence !== undefined,
      details: `Has category: ${!!r.meta?.category}, Has evaluation: ${!!r.meta?.evaluation}, Has confidence: ${!!r.confidence}`
    })
  );

  // ============================================
  // PRINT RESULTS
  // ============================================
  console.log("\n" + "=".repeat(70));
  console.log("VALIDATION RESULTS");
  console.log("=".repeat(70) + "\n");

  const categories = [...new Set(results.map(r => r.category))];

  for (const category of categories) {
    const categoryResults = results.filter(r => r.category === category);
    const passed = categoryResults.filter(r => r.passed).length;
    const total = categoryResults.length;

    console.log(`\n📌 ${category} (${passed}/${total})`);
    console.log("-".repeat(50));

    for (const result of categoryResults) {
      const icon = result.passed ? "✅" : "❌";
      console.log(`${icon} ${result.test}`);
      console.log(`   ${result.details}`);
      if (result.metrics) {
        console.log(`   ⏱️  ${result.metrics.responseTimeMs}ms | 📊 ${(result.metrics.confidence * 100).toFixed(0)}% conf`);
      }
    }
  }

  // Summary
  const totalPassed = results.filter(r => r.passed).length;
  const totalTests = results.length;
  const passRate = ((totalPassed / totalTests) * 100).toFixed(1);

  console.log("\n" + "=".repeat(70));
  console.log("SUMMARY");
  console.log("=".repeat(70));
  console.log(`Total Tests: ${totalTests}`);
  console.log(`Passed: ${totalPassed}`);
  console.log(`Failed: ${totalTests - totalPassed}`);
  console.log(`Pass Rate: ${passRate}%`);
  console.log("=".repeat(70) + "\n");

  // Return exit code
  if (totalPassed < totalTests) {
    process.exit(1);
  }
}

// Run validation
runValidation().catch(error => {
  console.error("Validation suite failed:", error);
  process.exit(1);
});
