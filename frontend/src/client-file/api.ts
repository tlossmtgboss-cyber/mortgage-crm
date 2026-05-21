// ─────────────────────────────────────────────────────────────────────────
// API — fetch wrappers for the LO surface
//
// All requests use httpOnly cookie auth (`credentials: "include"`) so
// Postgres RLS resolves to the right org_id via the `app.current_org_id`
// GUC set by the auth middleware.
//
// Configure the base URL via `setApiBaseUrl()` at app startup if your
// API is at a different origin. Default is same-origin /api/v1.
// ─────────────────────────────────────────────────────────────────────────

import { getToken } from "../utils/tokenStore";

import type {
  ActionPlanRun,
  ActivityCategory,
  ClientFile,
  ClientInsight,
  DocumentSet,
  DocumentsTabData,
  FollowupSequence,
  Relationship,
  SmartDocument,
  Task,
  TeamChatMember,
  TeamChatMessage,
  TeamChatReaction,
  TeamChatReadCursor,
  TimelineEvent,
} from "./types";

function getApiBase(): string {
  const isLocalhost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  const origin = isLocalhost
    ? (process.env.REACT_APP_API_URL || "http://localhost:8000")
    : "https://api.perenniaai.com";
  return origin + "/api/v1";
}

let API_BASE = getApiBase();

export function setApiBaseUrl(base: string): void {
  API_BASE = base;
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

function getAuthToken(): string | null {
  return getToken();
}

async function request<T>(
  path: string,
  opts: {
    method?: string;
    body?: unknown;
    query?: Record<string, string | number | boolean | undefined>;
  } = {},
): Promise<T> {
  const url = new URL(API_BASE + path, window.location.origin);
  if (opts.query) {
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined && v !== null && v !== "") {
        url.searchParams.set(k, String(v));
      }
    }
  }
  const headers: Record<string, string> = {};
  const token = getAuthToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (opts.body) headers["Content-Type"] = "application/json";

  const res = await fetch(url.toString(), {
    method: opts.method ?? "GET",
    credentials: "include",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let body: unknown = undefined;
    try { body = await res.json(); } catch { /* ignore */ }
    throw new ApiError(res.status, `${res.status} ${res.statusText}`, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ─────────────────────────────────────────────────────────────────────────
// Client file
// ─────────────────────────────────────────────────────────────────────────

export const clientFileApi = {
  get: (id: string) => request<ClientFile>(`/clients/${id}`),

  patch: (id: string, patch: Partial<ClientFile>) =>
    request<ClientFile>(`/clients/${id}`, { method: "PATCH", body: patch }),

  setLifecycleStage: (id: string, stage: ClientFile["lifecycle_stage"]) =>
    request<ClientFile>(`/clients/${id}/lifecycle`, {
      method: "POST",
      body: { lifecycle_stage: stage },
    }),

  setStickyNote: (id: string, note: string | null) =>
    request<ClientFile>(`/clients/${id}/sticky-note`, {
      method: "PUT",
      body: { sticky_note: note },
    }),

  addTag: (id: string, tag: string) =>
    request<ClientFile>(`/clients/${id}/tags`, {
      method: "POST",
      body: { tag },
    }),

  removeTag: (id: string, tag: string) =>
    request<ClientFile>(`/clients/${id}/tags/${encodeURIComponent(tag)}`, {
      method: "DELETE",
    }),
};

// ─────────────────────────────────────────────────────────────────────────
// Timeline + notes
// ─────────────────────────────────────────────────────────────────────────

export const timelineApi = {
  list: (clientFileId: string, category: ActivityCategory = "all", limit = 100) =>
    request<TimelineEvent[]>(`/clients/${clientFileId}/timeline`, {
      query: { category, limit },
    }),

  star: (clientFileId: string, eventId: string) =>
    request<TimelineEvent>(`/clients/${clientFileId}/timeline/${eventId}/star`, {
      method: "POST",
    }),

  unstar: (clientFileId: string, eventId: string) =>
    request<TimelineEvent>(`/clients/${clientFileId}/timeline/${eventId}/star`, {
      method: "DELETE",
    }),

  addNote: (clientFileId: string, body: string) =>
    request<TimelineEvent>(`/clients/${clientFileId}/notes`, {
      method: "POST",
      body: { body },
    }),

  sendMessage: (clientFileId: string, input: {
    channel: "email" | "sms" | "voice_brief";
    body: string;
    subject?: string;
    also_start_followup?: boolean;
    followup_goal?: string;
  }) => request<TimelineEvent>(`/clients/${clientFileId}/messages`, {
    method: "POST",
    body: input,
  }),
};

// ─────────────────────────────────────────────────────────────────────────
// Insights
// ─────────────────────────────────────────────────────────────────────────

export const insightApi = {
  get: (clientFileId: string) =>
    request<ClientInsight | null>(`/clients/${clientFileId}/insight`),
  recompute: (clientFileId: string) =>
    request<ClientInsight>(`/clients/${clientFileId}/insight/recompute`, {
      method: "POST",
    }),
};

// ─────────────────────────────────────────────────────────────────────────
// Tasks
// ─────────────────────────────────────────────────────────────────────────

export const taskApi = {
  list: (clientFileId: string, opts: { includeDone?: boolean } = {}) =>
    request<Task[]>(`/clients/${clientFileId}/tasks`, {
      query: { include_done: opts.includeDone ? "true" : "false" },
    }),
  create: (clientFileId: string, input: Partial<Task> & { title: string }) =>
    request<Task>(`/clients/${clientFileId}/tasks`, { method: "POST", body: input }),
  patch: (clientFileId: string, taskId: string, input: {
    title?: string;
    body?: string;
    priority?: string;
    due_at?: string;
    assigned_to_user_id?: number;
  }) =>
    request<Task>(`/clients/${clientFileId}/tasks/${taskId}`, {
      method: "PATCH",
      body: input,
    }),
  complete: (clientFileId: string, taskId: string) =>
    request<Task>(`/clients/${clientFileId}/tasks/${taskId}/complete`, { method: "POST" }),
  reopen: (clientFileId: string, taskId: string) =>
    request<Task>(`/clients/${clientFileId}/tasks/${taskId}/reopen`, { method: "POST" }),
};

// ─────────────────────────────────────────────────────────────────────────
// Documents
// ─────────────────────────────────────────────────────────────────────────

export const documentApi = {
  listSets: (clientFileId: string) =>
    request<DocumentSet[]>(`/clients/${clientFileId}/document-sets`),

  listDocuments: (clientFileId: string, tab: string = "all") =>
    request<DocumentsTabData>(`/clients/${clientFileId}/documents`, {
      query: { tab },
    }),

  getDocument: (clientFileId: string, documentId: number) =>
    request<SmartDocument>(`/clients/${clientFileId}/documents/${documentId}`),

  createRequest: (clientFileId: string, input: {
    doc_type: string;
    title: string;
    description?: string;
    instructions?: string;
    priority?: string;
    due_date?: string;
    require_esign?: boolean;
    send_notification?: boolean;
  }) =>
    request<unknown>(`/clients/${clientFileId}/documents/request`, {
      method: "POST",
      body: input,
    }),

  approveDocument: (clientFileId: string, documentId: number) =>
    request<unknown>(`/clients/${clientFileId}/documents/${documentId}/approve`, {
      method: "POST",
    }),

  rejectDocument: (clientFileId: string, documentId: number, input: {
    reason: string;
    category?: string;
    fix_instructions?: string;
  }) =>
    request<unknown>(`/clients/${clientFileId}/documents/${documentId}/reject`, {
      method: "POST",
      body: input,
    }),

  triggerAiReview: (clientFileId: string, documentId: number) =>
    request<{ document_id: number; decision?: string; reasons?: string[]; fix_instructions?: string }>(
      `/clients/${clientFileId}/documents/${documentId}/ai-review`,
      { method: "POST" },
    ),

  getDownloadUrl: (clientFileId: string, documentId: number) =>
    request<{ url: string; filename: string }>(
      `/clients/${clientFileId}/documents/${documentId}/download-url`,
    ),
};

// ─────────────────────────────────────────────────────────────────────────
// Cadence
// ─────────────────────────────────────────────────────────────────────────

export const cadenceApi = {
  listForClient: (clientFileId: string) =>
    request<FollowupSequence[]>(`/clients/${clientFileId}/cadence-sequences`),
  pause: (sequenceId: string) =>
    request<FollowupSequence>(`/cadence/sequences/${sequenceId}/pause`, { method: "POST" }),
  resume: (sequenceId: string) =>
    request<FollowupSequence>(`/cadence/sequences/${sequenceId}/resume`, { method: "POST" }),
  cancel: (sequenceId: string, reason?: string) =>
    request<FollowupSequence>(`/cadence/sequences/${sequenceId}/cancel`, {
      method: "POST",
      body: { reason: reason ?? "lo_cancelled" },
    }),
};

// ─────────────────────────────────────────────────────────────────────────
// Relationships
// ─────────────────────────────────────────────────────────────────────────

export const relationshipApi = {
  list: (clientFileId: string) =>
    request<Relationship[]>(`/clients/${clientFileId}/relationships`),
};

// ─────────────────────────────────────────────────────────────────────────
// Action Plans
// ─────────────────────────────────────────────────────────────────────────

export const actionPlanApi = {
  listRuns: (clientFileId: string) =>
    request<ActionPlanRun[]>(`/clients/${clientFileId}/action-plan-runs`),
};

// ─────────────────────────────────────────────────────────────────────────
// Team chat
// ─────────────────────────────────────────────────────────────────────────

export const teamChatApi = {
  // The channel is implicit (one per client_file_id). All operations key
  // off client_file_id; the backend resolves the channel.
  listMessages: (clientFileId: string, opts: { before?: string; limit?: number } = {}) =>
    request<TeamChatMessage[]>(`/clients/${clientFileId}/team-chat/messages`, {
      query: { before: opts.before, limit: opts.limit ?? 80 },
    }),

  sendMessage: (clientFileId: string, input: {
    body: string;
    mentioned_user_ids?: string[];
    attachments?: Array<{ kind: "document_upload"; document_upload_id: string }>;
  }) =>
    request<TeamChatMessage>(`/clients/${clientFileId}/team-chat/messages`, {
      method: "POST",
      body: input,
    }),

  editMessage: (clientFileId: string, messageId: string, body: string) =>
    request<TeamChatMessage>(`/clients/${clientFileId}/team-chat/messages/${messageId}`, {
      method: "PATCH",
      body: { body },
    }),

  deleteMessage: (clientFileId: string, messageId: string) =>
    request<void>(`/clients/${clientFileId}/team-chat/messages/${messageId}`, {
      method: "DELETE",
    }),

  pin: (clientFileId: string, messageId: string) =>
    request<TeamChatMessage>(`/clients/${clientFileId}/team-chat/messages/${messageId}/pin`, {
      method: "POST",
    }),

  unpin: (clientFileId: string, messageId: string) =>
    request<TeamChatMessage>(`/clients/${clientFileId}/team-chat/messages/${messageId}/unpin`, {
      method: "POST",
    }),

  getPinned: (clientFileId: string) =>
    request<TeamChatMessage | null>(`/clients/${clientFileId}/team-chat/pinned`),

  react: (clientFileId: string, messageId: string, emoji: string) =>
    request<TeamChatReaction>(`/clients/${clientFileId}/team-chat/messages/${messageId}/reactions`, {
      method: "POST",
      body: { emoji },
    }),

  unreact: (clientFileId: string, messageId: string, emoji: string) =>
    request<void>(`/clients/${clientFileId}/team-chat/messages/${messageId}/reactions/${encodeURIComponent(emoji)}`, {
      method: "DELETE",
    }),

  members: (clientFileId: string) =>
    request<TeamChatMember[]>(`/clients/${clientFileId}/team-chat/members`),

  markRead: (clientFileId: string, lastReadMessageId: string) =>
    request<TeamChatReadCursor>(`/clients/${clientFileId}/team-chat/read`, {
      method: "POST",
      body: { last_read_message_id: lastReadMessageId },
    }),

  unreadCount: (clientFileId: string) =>
    request<{ unread: number; mentions: number }>(`/clients/${clientFileId}/team-chat/unread`),

  setTyping: (clientFileId: string) =>
    request<void>(`/clients/${clientFileId}/team-chat/typing`, { method: "POST" }),

  getTyping: (clientFileId: string) =>
    request<{ typing_user_ids: string[] }>(`/clients/${clientFileId}/team-chat/typing`),
};
