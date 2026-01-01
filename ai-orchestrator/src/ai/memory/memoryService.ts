import { callLLM } from "../../lib/llm";

interface SessionMemory {
  history: Array<{ role: "user" | "assistant"; text: string; timestamp: string }>;
  activeLeadId?: string;
  activeLoanId?: string;
  summary?: string;
  lastSummarizedAt?: number;
  summarizedUpToIndex?: number;
}

const sessionStore = new Map<string, SessionMemory>();
const MAX_HISTORY_LENGTH = 20;
const SUMMARIZATION_THRESHOLD = 10; // Summarize when history exceeds this
const SUMMARY_CACHE_TTL_MS = 5 * 60 * 1000; // Cache summary for 5 minutes

export function getSessionMemory(sessionId: string): SessionMemory {
  if (!sessionStore.has(sessionId)) {
    sessionStore.set(sessionId, { history: [] });
  }
  return sessionStore.get(sessionId)!;
}

export function appendToHistory(
  sessionId: string,
  role: "user" | "assistant",
  text: string
): void {
  const memory = getSessionMemory(sessionId);
  memory.history.push({
    role,
    text,
    timestamp: new Date().toISOString()
  });

  // Keep history capped
  if (memory.history.length > MAX_HISTORY_LENGTH) {
    memory.history = memory.history.slice(-MAX_HISTORY_LENGTH);
  }
}

export function setActiveContext(
  sessionId: string,
  leadId?: string,
  loanId?: string
): void {
  const memory = getSessionMemory(sessionId);
  if (leadId) memory.activeLeadId = leadId;
  if (loanId) memory.activeLoanId = loanId;
}

export function getConversationHistory(
  sessionId: string
): Array<{ role: "user" | "assistant"; text: string }> {
  const memory = getSessionMemory(sessionId);
  return memory.history.map(h => ({ role: h.role, text: h.text }));
}

export function clearSession(sessionId: string): void {
  sessionStore.delete(sessionId);
}

/**
 * Get a condensed context for the LLM that includes:
 * - Previous summary (if exists)
 * - Recent conversation history
 * - Active context (lead/loan IDs)
 */
export async function getCondensedContext(sessionId: string): Promise<string> {
  const memory = getSessionMemory(sessionId);
  const parts: string[] = [];

  // Include previous summary if exists
  if (memory.summary) {
    parts.push(`Previous conversation summary:\n${memory.summary}`);
  }

  // Include active context
  if (memory.activeLeadId || memory.activeLoanId) {
    const contextItems: string[] = [];
    if (memory.activeLeadId) contextItems.push(`Lead ID: ${memory.activeLeadId}`);
    if (memory.activeLoanId) contextItems.push(`Loan ID: ${memory.activeLoanId}`);
    parts.push(`Active context: ${contextItems.join(", ")}`);
  }

  // Include recent history (last 5 messages always included in full)
  const recentHistory = memory.history.slice(-5);
  if (recentHistory.length > 0) {
    const historyText = recentHistory
      .map(h => `${h.role === "user" ? "User" : "Assistant"}: ${h.text}`)
      .join("\n");
    parts.push(`Recent conversation:\n${historyText}`);
  }

  return parts.join("\n\n");
}

/**
 * Summarize the session using LLM-based summarization.
 * Intelligently condenses long conversations while preserving key context.
 */
export async function summarizeSession(sessionId: string): Promise<string> {
  const memory = getSessionMemory(sessionId);
  if (memory.history.length === 0) return "";

  // If history is short, just return recent messages formatted
  if (memory.history.length <= SUMMARIZATION_THRESHOLD) {
    return memory.history
      .slice(-5)
      .map(h => `${h.role === "user" ? "User" : "Assistant"}: ${h.text.slice(0, 200)}`)
      .join("\n");
  }

  // Check if we have a cached summary that's still valid
  const now = Date.now();
  if (
    memory.summary &&
    memory.lastSummarizedAt &&
    now - memory.lastSummarizedAt < SUMMARY_CACHE_TTL_MS &&
    memory.summarizedUpToIndex === memory.history.length
  ) {
    return memory.summary;
  }

  // Build conversation text for summarization
  const conversationText = memory.history
    .map(h => `${h.role === "user" ? "User" : "Assistant"}: ${h.text}`)
    .join("\n");

  const systemPrompt = `You are a conversation summarizer for a mortgage CRM system.
Your task is to create a concise but comprehensive summary of the conversation.

Focus on extracting and preserving:
1. Key entities mentioned (lead names, loan numbers, property addresses)
2. Important decisions or actions discussed
3. Any pending questions or follow-ups
4. Loan details (amounts, rates, loan types, stages)
5. Compliance or documentation topics
6. Client concerns or objections
7. Next steps or commitments made

Format the summary as a structured brief that can be used to continue the conversation contextually.
Keep the summary under 300 words but ensure no critical information is lost.`;

  try {
    const summary = await callLLM(
      `Please summarize the following mortgage CRM conversation:\n\n${conversationText}`,
      {
        systemPrompt,
        temperature: 0.3,
        maxTokens: 500,
        modelName: "router" // Use faster model for summarization
      }
    );

    // Cache the summary
    memory.summary = summary;
    memory.lastSummarizedAt = now;
    memory.summarizedUpToIndex = memory.history.length;

    return summary;
  } catch (error) {
    console.error("Failed to summarize session:", error);
    // Fallback to simple summarization if LLM fails
    const lastFive = memory.history.slice(-5);
    return lastFive.map(h => `${h.role}: ${h.text.slice(0, 100)}`).join("\n");
  }
}

/**
 * Incrementally update the summary with new messages.
 * More efficient than re-summarizing the entire conversation.
 */
export async function updateSummaryIncremental(sessionId: string): Promise<string> {
  const memory = getSessionMemory(sessionId);

  // If we don't have enough new messages since last summary, skip
  const newMessageCount = memory.history.length - (memory.summarizedUpToIndex || 0);
  if (newMessageCount < 5) {
    return memory.summary || "";
  }

  // Get messages since last summarization
  const newMessages = memory.history.slice(memory.summarizedUpToIndex || 0);
  const newConversation = newMessages
    .map(h => `${h.role === "user" ? "User" : "Assistant"}: ${h.text}`)
    .join("\n");

  const systemPrompt = `You are a conversation summarizer for a mortgage CRM system.
You have an existing summary of the conversation and new messages to incorporate.
Create an updated, consolidated summary that:
1. Preserves critical information from the previous summary
2. Incorporates new developments and context
3. Removes redundant or superseded information
4. Keeps the summary concise (under 300 words)`;

  const prompt = memory.summary
    ? `Previous summary:\n${memory.summary}\n\nNew messages to incorporate:\n${newConversation}\n\nCreate an updated consolidated summary.`
    : `Summarize the following conversation:\n${newConversation}`;

  try {
    const summary = await callLLM(prompt, {
      systemPrompt,
      temperature: 0.3,
      maxTokens: 500,
      modelName: "router"
    });

    // Update cache
    memory.summary = summary;
    memory.lastSummarizedAt = Date.now();
    memory.summarizedUpToIndex = memory.history.length;

    return summary;
  } catch (error) {
    console.error("Failed to update summary:", error);
    return memory.summary || "";
  }
}

/**
 * Extract key entities from the conversation for quick context.
 */
export async function extractKeyEntities(sessionId: string): Promise<{
  leadIds: string[];
  loanIds: string[];
  borrowerNames: string[];
  properties: string[];
  amounts: string[];
  topics: string[];
}> {
  const memory = getSessionMemory(sessionId);

  if (memory.history.length === 0) {
    return {
      leadIds: [],
      loanIds: [],
      borrowerNames: [],
      properties: [],
      amounts: [],
      topics: []
    };
  }

  const conversationText = memory.history
    .map(h => `${h.role}: ${h.text}`)
    .join("\n");

  const systemPrompt = `Extract key entities from this mortgage CRM conversation.
Return a JSON object with these arrays:
- leadIds: Any lead/contact IDs mentioned
- loanIds: Any loan numbers or IDs mentioned
- borrowerNames: Names of borrowers or clients
- properties: Property addresses mentioned
- amounts: Loan amounts or financial figures
- topics: Main topics discussed (e.g., "refinance", "rate lock", "appraisal")

Only include explicitly mentioned items. Return empty arrays if none found.`;

  try {
    const response = await callLLM(
      `Extract entities from:\n${conversationText}`,
      {
        systemPrompt,
        temperature: 0,
        maxTokens: 300,
        json: true,
        modelName: "router"
      }
    );

    return JSON.parse(response);
  } catch (error) {
    console.error("Failed to extract entities:", error);
    return {
      leadIds: memory.activeLeadId ? [memory.activeLeadId] : [],
      loanIds: memory.activeLoanId ? [memory.activeLoanId] : [],
      borrowerNames: [],
      properties: [],
      amounts: [],
      topics: []
    };
  }
}

/**
 * Get memory stats for debugging/monitoring.
 */
export function getMemoryStats(sessionId: string): {
  historyLength: number;
  hasSummary: boolean;
  activeLeadId?: string;
  activeLoanId?: string;
  lastSummarizedAt?: string;
} {
  const memory = getSessionMemory(sessionId);
  return {
    historyLength: memory.history.length,
    hasSummary: !!memory.summary,
    activeLeadId: memory.activeLeadId,
    activeLoanId: memory.activeLoanId,
    lastSummarizedAt: memory.lastSummarizedAt
      ? new Date(memory.lastSummarizedAt).toISOString()
      : undefined
  };
}

/**
 * Prune old sessions to free memory.
 */
export function pruneOldSessions(maxAgeMs: number = 30 * 60 * 1000): number {
  const now = Date.now();
  let pruned = 0;
  const toDelete: string[] = [];

  sessionStore.forEach((memory, sessionId) => {
    if (memory.history.length === 0) {
      toDelete.push(sessionId);
      return;
    }

    const lastActivity = new Date(
      memory.history[memory.history.length - 1].timestamp
    ).getTime();

    if (now - lastActivity > maxAgeMs) {
      toDelete.push(sessionId);
    }
  });

  toDelete.forEach(sessionId => {
    sessionStore.delete(sessionId);
    pruned++;
  });

  return pruned;
}
