import { BrainInput, BrainStructuredOutput } from "../orchestrator/types";
import { callLLM } from "../../lib/llm";
import { parseLLMJson } from "../../lib/jsonLLM";
import { groundingSummaryBullets } from "../contexts/contextFormatter";

export async function advisorBrain(input: BrainInput): Promise<BrainStructuredOutput> {
  const { userMessage, context, grounding, routing } = input;

  const systemPrompt = `
You are an expert Mortgage Advisor AI embedded in a CRM.

Rules:
- Always ground your answer in the provided grounding snapshot.
- Never invent loan data. If something is missing, ask a clarifying question.
- Be precise and conservative with guidelines and numbers.
- If there is any regulatory or compliance uncertainty, mention it and suggest escalation.
- Return STRICT JSON with:
  {
    "answer": string,
    "assumptions": string[],
    "actions": { "type": string, "payload": object, "requiresApproval": boolean }[],
    "warnings": string[],
    "reasoningSummary": string
  }

Available action types (use EXACTLY these strings):
- CREATE_TASK: Create a task with payload { title, description, dueDate, priority }
- ADD_NOTE: Add a note with payload { content }
- UPDATE_LOAN_STATUS: Update loan status with payload { status, stage }
- SCHEDULE_APPOINTMENT: Schedule appointment with payload { title, datetime, duration, attendees }
- SEND_EMAIL_DRAFT: Draft email with payload { to, subject, body }
- SEND_SMS_DRAFT: Draft SMS with payload { to, message }

Action guidelines:
- When user requests scheduling with date/time, CREATE the SCHEDULE_APPOINTMENT action with best-effort datetime
- When user requests task creation, CREATE the CREATE_TASK action immediately
- Use requiresApproval: true only for high-risk actions
- Prefer action execution over asking clarifying questions when intent is clear
`;

  const bulletSummary = groundingSummaryBullets(grounding);
  const compactGroundingJson = JSON.stringify(grounding, null, 2);

  const userPrompt = `
User message:
"${userMessage.text}"

Routing category: ${routing.category}

Grounding snapshot summary:
${bulletSummary}

Grounding snapshot JSON:
${compactGroundingJson}

Task:
1) Understand the user's intent.
2) Use the grounding snapshot to provide a clear, client-ready answer.
3) If necessary data is missing, clearly state what is missing and include a follow-up question in "answer".
4) If operational work is required (task, note, follow-up), include it as planned "actions".
`;

  const raw = await callLLM(
    `${systemPrompt}\n\n${userPrompt}`,
    { json: true, temperature: 0.2, maxTokens: 900, modelName: "advisor" }
  );

  const parsed = await parseLLMJson<any>(raw, {
    purpose: "advisor-brain",
    onErrorFallback: () => null
  });

  if (!parsed) {
    return {
      answer: raw,
      assumptions: [],
      actions: [],
      warnings: ["Failed to parse structured advisor brain output"],
      reasoningSummary: "Fallback unstructured output",
      usedContextKeys: Object.keys(context).filter((k) => (context as any)[k] != null)
    };
  }

  return {
    answer: parsed.answer ?? "",
    assumptions: parsed.assumptions ?? [],
    actions: parsed.actions ?? [],
    warnings: parsed.warnings ?? [],
    reasoningSummary: parsed.reasoningSummary ?? "",
    usedContextKeys: Object.keys(context).filter((k) => (context as any)[k] != null)
  };
}
