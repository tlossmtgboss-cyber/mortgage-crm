interface SessionMemory {
  history: Array<{ role: "user" | "assistant"; text: string; timestamp: string }>;
  activeLeadId?: string;
  activeLoanId?: string;
  summary?: string;
}

const sessionStore = new Map<string, SessionMemory>();
const MAX_HISTORY_LENGTH = 20;

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

export async function summarizeSession(sessionId: string): Promise<string> {
  const memory = getSessionMemory(sessionId);
  if (memory.history.length === 0) return "";

  // TODO: Implement LLM-based summarization for long conversations
  const lastFive = memory.history.slice(-5);
  return lastFive.map(h => `${h.role}: ${h.text.slice(0, 100)}`).join("\n");
}
