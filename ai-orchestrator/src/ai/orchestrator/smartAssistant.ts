import {
  UserMessage,
  RetrievedContext,
  AssistantFinalAnswer,
  BrainInput,
  PlannedAction
} from "./types";
import { routeTask } from "../router/taskRouter";
import { buildGroundingSnapshot } from "../contexts/contextFormatter";
import { advisorBrain } from "../brains/advisorBrain";
import { evaluateConfidence } from "../validators/confidenceEvaluator";
import { executeActions } from "../tools/toolExecutor";
import { formatForChannel } from "./formatting";
import { shouldEscalate, canAutoExecuteAction } from "../config/aiConfig";
import {
  getSessionMemory,
  appendToHistory,
  setActiveContext,
  getConversationHistory
} from "../memory/memoryService";
import { logInteraction } from "../../lib/logger";

const API_BASE_URL = process.env.CRM_API_URL || "https://api.perenniaai.com";

async function apiCall(endpoint: string, token?: string): Promise<any> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json"
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);

  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      headers,
      signal: controller.signal
    });
    clearTimeout(timeout);

    if (!response.ok) {
      console.error(`[CONTEXT] API error ${response.status} for ${endpoint}`);
      return null;
    }

    const text = await response.text();
    try {
      return JSON.parse(text);
    } catch {
      console.error(`[CONTEXT] Non-JSON response for ${endpoint}: ${text.slice(0, 100)}`);
      return null;
    }
  } catch (error: any) {
    clearTimeout(timeout);
    if (error.name === "AbortError") {
      console.error(`[CONTEXT] Timeout after 10s for ${endpoint}`);
    } else {
      console.error(`[CONTEXT] Fetch failed for ${endpoint}: ${error.message}`);
    }
    return null;
  }
}

async function retrieveContext(
  contextTypes: string[],
  leadId?: string,
  loanId?: string,
  authToken?: string
): Promise<RetrievedContext> {
  console.log("[CONTEXT] Retrieving:", contextTypes, { leadId, loanId });

  const context: RetrievedContext = {};

  // Fetch lead if needed
  if (contextTypes.includes("LEAD") && leadId) {
    try {
      context.lead = await apiCall(`/api/v1/leads/${leadId}`, authToken);
    } catch (e) {
      console.error("[CONTEXT] Failed to fetch lead:", e);
    }
  }

  // Fetch loan if needed
  if (contextTypes.includes("LOAN") && loanId) {
    try {
      context.loan = await apiCall(`/api/v1/loans/${loanId}`, authToken);
    } catch (e) {
      console.error("[CONTEXT] Failed to fetch loan:", e);
    }
  }

  // Fetch pipeline/tasks
  if (contextTypes.includes("PIPELINE")) {
    try {
      const tasks = await apiCall(`/api/v1/tasks/?limit=20`, authToken);
      context.pipeline = {
        openTasks: Array.isArray(tasks) ? tasks.filter((t: any) => t.status !== "completed") : []
      };
    } catch (e) {
      console.error("[CONTEXT] Failed to fetch pipeline:", e);
    }
  }

  // Fetch calendar events
  if (contextTypes.includes("CALENDAR")) {
    try {
      context.calendar = await apiCall(`/api/v1/calendar/events?limit=10`, authToken);
    } catch (e) {
      console.error("[CONTEXT] Failed to fetch calendar:", e);
    }
  }

  // Fetch emails if lead has email threads
  if (contextTypes.includes("EMAIL_THREAD") && leadId) {
    try {
      // Emails are typically fetched via email sync endpoints
      context.emails = [];
    } catch (e) {
      console.error("[CONTEXT] Failed to fetch emails:", e);
    }
  }

  // Fetch SMS threads
  if (contextTypes.includes("SMS_THREAD") && leadId) {
    try {
      context.sms = [];
    } catch (e) {
      console.error("[CONTEXT] Failed to fetch SMS:", e);
    }
  }

  // Notes are stored on lead/loan objects
  if (contextTypes.includes("NOTES")) {
    context.notes = [];
    if (context.lead?.notes) {
      context.notes.push({ text: context.lead.notes, date: context.lead.updated_at });
    }
    if (context.loan?.notes) {
      context.notes.push({ text: context.loan.notes, date: context.loan.updated_at });
    }
  }

  // Knowledge base articles
  if (contextTypes.includes("KNOWLEDGE_BASE")) {
    try {
      // Try guideline updates endpoint
      const guidelines = await apiCall(`/api/v1/guideline-updates?limit=5`, authToken);
      context.kbArticles = Array.isArray(guidelines) ? guidelines : [];
    } catch (e) {
      // KB not available, continue without it
      context.kbArticles = [];
    }
  }

  // Rate sheet (placeholder - would need specific endpoint)
  if (contextTypes.includes("RATE_SHEET")) {
    context.rateSheet = null;
  }

  return context;
}

export async function processMessage(
  message: UserMessage
): Promise<AssistantFinalAnswer> {
  const startTime = Date.now();

  // 1. Get/update session memory
  const sessionMemory = getSessionMemory(message.sessionId);
  const conversationHistory = getConversationHistory(message.sessionId);

  // Inject history into message metadata
  message.metadata = {
    ...message.metadata,
    conversationHistory,
    activeLeadId: message.metadata?.activeLeadId || sessionMemory.activeLeadId,
    activeLoanId: message.metadata?.activeLoanId || sessionMemory.activeLoanId
  };

  // 2. Route the task
  const routing = await routeTask(message);

  // 3. Retrieve context if needed
  let context: RetrievedContext = {};
  const authToken = message.metadata?.authToken;
  if (routing.requiresContext) {
    context = await retrieveContext(
      routing.requiredContextTypes,
      message.metadata?.activeLeadId,
      message.metadata?.activeLoanId,
      authToken
    );
  }

  // 4. Build grounding snapshot
  const grounding = buildGroundingSnapshot(context);

  // Update active context in session
  if (grounding.rawIds.leadId) {
    setActiveContext(message.sessionId, grounding.rawIds.leadId, grounding.rawIds.loanId);
  }

  // 5. Call the brain
  const brainInput: BrainInput = {
    userMessage: message,
    routing,
    context,
    grounding
  };

  const brainOutput = await advisorBrain(brainInput);

  // 6. Evaluate confidence
  const evaluation = await evaluateConfidence(message, brainOutput, grounding);

  // 7. Determine escalation
  const escalationRequired = shouldEscalate(
    routing.category,
    evaluation.confidence,
    evaluation.riskLevel
  );

  // 8. Execute auto-actions
  const actionsToExecute: PlannedAction[] = [];
  const actionsPendingApproval: PlannedAction[] = [];

  for (const action of brainOutput.actions) {
    if (canAutoExecuteAction(routing.category, action.type, action.requiresApproval)) {
      actionsToExecute.push(action);
    } else {
      actionsPendingApproval.push(action);
    }
  }

  let executedActions: PlannedAction[] = [];
  if (actionsToExecute.length > 0 && !escalationRequired) {
    await executeActions(actionsToExecute, {
      userId: message.userId,
      leadId: grounding.rawIds.leadId,
      loanId: grounding.rawIds.loanId,
      authToken
    });
    executedActions = actionsToExecute;
  }

  // 9. Format answer for channel
  const formattedAnswer = formatForChannel(
    brainOutput.answer,
    message.channel,
    executedActions.length > 0 ? executedActions : undefined
  );

  // 10. Update session memory
  appendToHistory(message.sessionId, "user", message.text);
  appendToHistory(message.sessionId, "assistant", formattedAnswer);

  // 11. Build final response
  const finalAnswer: AssistantFinalAnswer = {
    answer: formattedAnswer,
    confidence: evaluation.confidence,
    escalationRequired,
    escalationReason: escalationRequired
      ? `Confidence ${evaluation.confidence}% below threshold or risk level ${evaluation.riskLevel}`
      : undefined,
    actionsExecuted: executedActions,
    meta: {
      category: routing.category,
      evaluation,
      warnings: brainOutput.warnings,
      assumptions: brainOutput.assumptions,
      pendingActions: actionsPendingApproval,
      processingTimeMs: Date.now() - startTime
    }
  };

  // 12. Log interaction
  await logInteraction({
    sessionId: message.sessionId,
    userId: message.userId,
    channel: message.channel,
    category: routing.category,
    confidence: evaluation.confidence,
    escalationRequired,
    actionsExecuted: executedActions.length,
    processingTimeMs: Date.now() - startTime
  });

  return finalAnswer;
}

// Export for external use
export { UserMessage, AssistantFinalAnswer } from "./types";
