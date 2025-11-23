import { UserMessage, TaskRoutingResult, TaskCategory, ContextType } from "../orchestrator/types";
import { callLLM } from "../../lib/llm";
import { parseLLMJson } from "../../lib/jsonLLM";

const VALID_CATEGORIES: TaskCategory[] = [
  "MORTGAGE_GUIDELINE",
  "LOAN_STATUS",
  "CLIENT_FOLLOW_UP",
  "APPOINTMENT_SCHEDULING",
  "LOAN_PRICING",
  "CRM_NAVIGATION",
  "PORTFOLIO_ANALYSIS",
  "OPERATIONS",
  "COMPLIANCE",
  "GENERAL_KNOWLEDGE"
];

const VALID_CONTEXT_TYPES: ContextType[] = [
  "LEAD",
  "LOAN",
  "PIPELINE",
  "EMAIL_THREAD",
  "SMS_THREAD",
  "CALENDAR",
  "NOTES",
  "RATE_SHEET",
  "KNOWLEDGE_BASE"
];

function asContextType(value: any): ContextType[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((v) => typeof v === "string")
    .map((v) => v.toUpperCase().trim())
    .filter((v) => (VALID_CONTEXT_TYPES as string[]).includes(v)) as ContextType[];
}

export async function routeTask(message: UserMessage): Promise<TaskRoutingResult> {
  const systemPrompt = `
You are a classifier for a mortgage-focused CRM AI assistant.
Your ONLY job is to classify the user's latest message.

Return STRICT JSON with:
{
  "category": string,
  "requiresContext": boolean,
  "requiredContextTypes": string[]
}

### TaskCategory options:
- MORTGAGE_GUIDELINE
- LOAN_STATUS
- CLIENT_FOLLOW_UP
- APPOINTMENT_SCHEDULING
- LOAN_PRICING
- CRM_NAVIGATION
- PORTFOLIO_ANALYSIS
- OPERATIONS
- COMPLIANCE
- GENERAL_KNOWLEDGE

If you are not sure, use GENERAL_KNOWLEDGE and requiresContext=false.

### Few-shot examples
User: "What is the status of my refinance file?"
-> { "category": "LOAN_STATUS", "requiresContext": true, "requiredContextTypes": ["LOAN", "PIPELINE", "NOTES"] }

User: "Can you call the client and schedule a follow up next Tuesday?"
-> { "category": "APPOINTMENT_SCHEDULING", "requiresContext": true, "requiredContextTypes": ["CALENDAR", "LEAD"] }

User: "What is the max seller concession on an investment property?"
-> { "category": "MORTGAGE_GUIDELINE", "requiresContext": true, "requiredContextTypes": ["KNOWLEDGE_BASE"] }

User: "Walk me through how to add a new loan in the CRM."
-> { "category": "CRM_NAVIGATION", "requiresContext": false, "requiredContextTypes": [] }

User: "Should I refinance if my rate is 7.25% and today's rate is 6.5%?"
-> { "category": "PORTFOLIO_ANALYSIS", "requiresContext": true, "requiredContextTypes": ["LOAN", "RATE_SHEET"] }
`;

  const history = message.metadata?.conversationHistory ?? [];
  const historyText = history.length > 0 ? history
    .slice(-5)
    .map(t => `${t.role.toUpperCase()}: ${t.text}`)
    .join("\n") : "(no prior history)";

  const userPrompt = `
Conversation history (last turns):
${historyText}

Active leadId: ${message.metadata?.activeLeadId ?? "none"}
Active loanId: ${message.metadata?.activeLoanId ?? "none"}

Latest user message:
"${message.text}"
`;

  const raw = await callLLM(
    `${systemPrompt}\n\n${userPrompt}`,
    { json: true, temperature: 0.0, modelName: "router" }
  );

  const parsed = await parseLLMJson(raw, {
    purpose: "task-routing",
    onErrorFallback: () => heuristicFallback(message.text)
  });

  if (!parsed || typeof parsed !== "object") {
    return heuristicFallback(message.text);
  }

  const validated = validateRouting(parsed);
  return validated ?? heuristicFallback(message.text);
}

function validateRouting(obj: any): TaskRoutingResult | null {
  if (!obj || typeof obj !== "object") return null;
  if (typeof obj.category !== "string") return null;
  if (typeof obj.requiresContext !== "boolean") return null;

  const category = obj.category as TaskCategory;
  if (!VALID_CATEGORIES.includes(category)) return null;

  const ctxTypes = asContextType(obj.requiredContextTypes);

  return {
    category,
    requiresContext: !!obj.requiresContext,
    requiredContextTypes: ctxTypes
  };
}

function heuristicFallback(text: string): TaskRoutingResult {
  const lower = text.toLowerCase();

  if (lower.includes("status") || lower.includes("file") || lower.includes("clear to close")) {
    return {
      category: "LOAN_STATUS",
      requiresContext: true,
      requiredContextTypes: ["LOAN", "PIPELINE", "NOTES"]
    };
  }

  if (lower.includes("rate") || lower.includes("apr") || lower.includes("pricing")) {
    return {
      category: "LOAN_PRICING",
      requiresContext: true,
      requiredContextTypes: ["LOAN", "RATE_SHEET"]
    };
  }

  if (lower.includes("guideline") || lower.includes("max seller") || lower.includes("dti")) {
    return {
      category: "MORTGAGE_GUIDELINE",
      requiresContext: true,
      requiredContextTypes: ["KNOWLEDGE_BASE"]
    };
  }

  if (lower.includes("schedule") || lower.includes("appointment") || lower.includes("call me")) {
    return {
      category: "APPOINTMENT_SCHEDULING",
      requiresContext: true,
      requiredContextTypes: ["CALENDAR", "LEAD"]
    };
  }

  return {
    category: "GENERAL_KNOWLEDGE",
    requiresContext: false,
    requiredContextTypes: []
  };
}
