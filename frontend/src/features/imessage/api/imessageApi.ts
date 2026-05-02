// Perennia iMessage — API client
// Uses getToken() + raw fetch with Bearer auth (standard Perennia pattern).

import { getToken } from "../../../utils/tokenStore";
import type {
  ConversationThread,
  IMessageDetectionResult,
  SendMessageRequest,
  SendMessageResponse,
  TapbackRequest,
  ConversationMessage,
} from "../types";

const API_BASE_URL =
  process.env.REACT_APP_API_URL || "http://localhost:8000";
const BASE = "/api/imessage";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { ...headers, ...(init?.headers as Record<string, string> || {}) },
  });
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`iMessage API ${resp.status}: ${body}`);
  }
  // 204 No Content has no body
  if (resp.status === 204) return undefined as unknown as T;
  return resp.json() as Promise<T>;
}

export const imessageApi = {
  async getThread(contactId: number, limit = 200): Promise<ConversationThread> {
    return apiFetch<ConversationThread>(
      `${BASE}/contacts/${contactId}/thread?limit=${limit}`,
    );
  },

  async send(req: SendMessageRequest): Promise<SendMessageResponse> {
    return apiFetch<SendMessageResponse>(`${BASE}/messages`, {
      method: "POST",
      body: JSON.stringify(req),
    });
  },

  async sendTapback(req: TapbackRequest): Promise<ConversationMessage> {
    return apiFetch<ConversationMessage>(`${BASE}/tapbacks`, {
      method: "POST",
      body: JSON.stringify(req),
    });
  },

  async detectIMessage(
    handle: string,
    opts?: { force?: boolean; lineId?: string },
  ): Promise<IMessageDetectionResult> {
    return apiFetch<IMessageDetectionResult>(`${BASE}/detect-imessage`, {
      method: "POST",
      body: JSON.stringify({
        handle,
        force: opts?.force ?? false,
        line_id: opts?.lineId ?? null,
      }),
    });
  },

  async typing(contactId: number, on: boolean): Promise<void> {
    await apiFetch<void>(`${BASE}/typing`, {
      method: "POST",
      body: JSON.stringify({ contact_id: contactId, on }),
    });
  },
};
