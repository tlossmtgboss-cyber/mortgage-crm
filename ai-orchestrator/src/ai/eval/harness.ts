import { processMessage, UserMessage } from "../orchestrator/smartAssistant";

interface TestCase {
  id: string;
  input: UserMessage;
  expectedCategory: string;
  expectedPhrases: string[];
  expectedActions?: string[];
}

interface TestResult {
  id: string;
  passed: boolean;
  categoryCorrect: boolean;
  phraseCoverage: number;
  actionsCovered: boolean;
  confidence: number;
  answer: string;
  errors: string[];
}

export async function runEvaluation(testCases: TestCase[]): Promise<{
  results: TestResult[];
  summary: {
    total: number;
    passed: number;
    failed: number;
    avgConfidence: number;
    avgPhraseCoverage: number;
  };
}> {
  const results: TestResult[] = [];

  for (const testCase of testCases) {
    try {
      const result = await processMessage(testCase.input);
      const errors: string[] = [];

      // Check category
      const categoryCorrect = result.meta?.category === testCase.expectedCategory;
      if (!categoryCorrect) {
        errors.push(`Category mismatch: expected ${testCase.expectedCategory}, got ${result.meta?.category}`);
      }

      // Check phrase coverage
      const answerLower = result.answer.toLowerCase();
      const matchedPhrases = testCase.expectedPhrases.filter(phrase =>
        answerLower.includes(phrase.toLowerCase())
      );
      const phraseCoverage = testCase.expectedPhrases.length > 0
        ? matchedPhrases.length / testCase.expectedPhrases.length
        : 1;

      if (phraseCoverage < 0.5) {
        errors.push(`Low phrase coverage: ${(phraseCoverage * 100).toFixed(0)}%`);
      }

      // Check actions
      let actionsCovered = true;
      if (testCase.expectedActions && testCase.expectedActions.length > 0) {
        const executedTypes = (result.actionsExecuted || []).map(a => a.type);
        const pendingTypes = (result.meta?.pendingActions || []).map((a: any) => a.type);
        const allActions = [...executedTypes, ...pendingTypes];

        actionsCovered = testCase.expectedActions.every(expected =>
          allActions.includes(expected)
        );

        if (!actionsCovered) {
          errors.push(`Missing actions: expected ${testCase.expectedActions.join(", ")}`);
        }
      }

      const passed = categoryCorrect && phraseCoverage >= 0.5 && actionsCovered;

      results.push({
        id: testCase.id,
        passed,
        categoryCorrect,
        phraseCoverage,
        actionsCovered,
        confidence: result.confidence,
        answer: result.answer.slice(0, 200),
        errors
      });
    } catch (error) {
      results.push({
        id: testCase.id,
        passed: false,
        categoryCorrect: false,
        phraseCoverage: 0,
        actionsCovered: false,
        confidence: 0,
        answer: "",
        errors: [error instanceof Error ? error.message : "Unknown error"]
      });
    }
  }

  // Calculate summary
  const passed = results.filter(r => r.passed).length;
  const avgConfidence = results.reduce((sum, r) => sum + r.confidence, 0) / results.length;
  const avgPhraseCoverage = results.reduce((sum, r) => sum + r.phraseCoverage, 0) / results.length;

  return {
    results,
    summary: {
      total: results.length,
      passed,
      failed: results.length - passed,
      avgConfidence,
      avgPhraseCoverage
    }
  };
}

// Example golden dataset
export const EXAMPLE_TEST_CASES: TestCase[] = [
  {
    id: "loan-status-1",
    input: {
      userId: "user1",
      sessionId: "session1",
      text: "What is the status of my refinance file?",
      channel: "web"
    },
    expectedCategory: "LOAN_STATUS",
    expectedPhrases: ["status", "loan", "file"]
  },
  {
    id: "guideline-1",
    input: {
      userId: "user1",
      sessionId: "session2",
      text: "What is the max seller concession on an investment property?",
      channel: "web"
    },
    expectedCategory: "MORTGAGE_GUIDELINE",
    expectedPhrases: ["seller concession", "investment"]
  },
  {
    id: "scheduling-1",
    input: {
      userId: "user1",
      sessionId: "session3",
      text: "Schedule a call with the client for next Tuesday at 2pm",
      channel: "web"
    },
    expectedCategory: "APPOINTMENT_SCHEDULING",
    expectedPhrases: ["schedule", "call"],
    expectedActions: ["SCHEDULE_APPOINTMENT"]
  }
];
