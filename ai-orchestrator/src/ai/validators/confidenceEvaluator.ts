import {
  ConfidenceEvaluation,
  BrainStructuredOutput,
  UserMessage,
  GroundingSnapshot
} from "../orchestrator/types";
import { callLLM } from "../../lib/llm";
import { parseLLMJson } from "../../lib/jsonLLM";

export async function evaluateConfidence(
  userMessage: UserMessage,
  brainOutput: BrainStructuredOutput,
  grounding: GroundingSnapshot
): Promise<ConfidenceEvaluation> {
  const systemPrompt = `
You are a strict evaluator of AI answers in a mortgage CRM.

You will assess:
- Grounding: how well the answer is supported by the grounding snapshot.
- Completeness: did it address the user's question fully?
- Risk: any regulatory/compliance or factual risk?

Return STRICT JSON:
{
  "confidence": number,
  "groundingScore": number,
  "completenessScore": number,
  "riskScore": number,
  "issues": string[],
  "riskLevel": "LOW" | "MEDIUM" | "HIGH"
}
`;

  const groundingJson = JSON.stringify(grounding, null, 2);

  const userPrompt = `
User message:
"${userMessage.text}"

Grounding snapshot:
${groundingJson}

AI structured output:
${JSON.stringify(brainOutput, null, 2)}
`;

  // Call your LLM provider for evaluation
  const raw = await callLLM(
    `${systemPrompt}\n\n${userPrompt}`,
    { json: true, temperature: 0.0, modelName: "evaluator" }
  );

  const parsed = await parseLLMJson<any>(raw, {
    purpose: "confidence-evaluator",
    onErrorFallback: () => null
  });

  if (!parsed) {
    return {
      confidence: 0.5,
      groundingScore: 0.5,
      completenessScore: 0.5,
      riskScore: 0.5,
      issues: ["Confidence evaluator failed to parse JSON"],
      riskLevel: "MEDIUM"
    };
  }

  return {
    confidence: clamp(parsed.confidence, 0, 1),
    groundingScore: clamp(parsed.groundingScore, 0, 1),
    completenessScore: clamp(parsed.completenessScore, 0, 1),
    riskScore: clamp(parsed.riskScore, 0, 1),
    issues: Array.isArray(parsed.issues) ? parsed.issues : [],
    riskLevel: parsed.riskLevel === "HIGH" || parsed.riskLevel === "LOW" ? parsed.riskLevel : "MEDIUM"
  };
}

function clamp(n: any, min: number, max: number): number {
  const x = Number(n);
  if (isNaN(x)) return min;
  return Math.max(min, Math.min(max, x));
}
