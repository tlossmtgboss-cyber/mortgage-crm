// API client for the POS feature.
//
// Assumes a PURL token is set via setPurlToken() or present in
// sessionStorage under key "perennia_purl_token".
//
// SECURITY: The PURL token is stored in sessionStorage (not localStorage)
// so it cannot be exfiltrated by an XSS payload that persists across tabs
// or page reloads of other origins. Borrower sessions are short-lived
// (the URLA flow typically takes < 1 hour), so the per-tab inconvenience
// is acceptable. If the borrower opted into "Remember this device" during
// verify, the httpOnly `pos_device_token` cookie set by the verify endpoint
// restores their session on next login — so long-lived trust is still
// supported without keeping a JS-readable bearer token sitting around.
//
// One-time migration: if a token is found under the legacy `localStorage`
// key, it is copied into `sessionStorage` and removed from `localStorage`
// so previously-issued tokens are not lost.

import type {
  ApplicationResponse,
  ApplicationSubmitRequest,
  ApplicationSubmitResponse,
  AskRequest,
  AskResponse,
  AssignedLOResponse,
  AvailableSlotsResponse,
  BookingRequest,
  BookingResponse,
  BorrowerMessage,
  BorrowerMessagesResponse,
  BorrowerTasksResponse,
  BorrowerTask,
  DocumentsResponse,
  QAHistoryResponse,
  SectionKey,
  SectionResponse,
  SectionUpdateRequest,
  SlotHoldResponse,
  TeamResponse,
} from '../types';

import { API_BASE_URL } from '../../../services/api';

const API_BASE =
  (typeof window !== 'undefined' && (window as any).__PERENNIA_API_BASE__) ||
  process.env.REACT_APP_PERENNIA_API_BASE ||
  API_BASE_URL;

// Module-scoped PURL token — avoids exposing credentials on window globals.
let _purlToken: string | null = null;

export function setPurlToken(token: string | null): void {
  _purlToken = token;
}

const PURL_TOKEN_KEY = 'perennia_purl_token';

function getPurlToken(): string {
  if (_purlToken) return _purlToken;
  if (typeof window === 'undefined') return '';
  // Prefer sessionStorage (XSS-resistant for cross-tab persistence).
  const fromSession = window.sessionStorage?.getItem(PURL_TOKEN_KEY);
  if (fromSession) return fromSession;
  // One-time migration: legacy tokens in localStorage are moved into
  // sessionStorage and removed from localStorage so we don't keep an
  // XSS-readable copy lying around. Subsequent reads will hit sessionStorage.
  try {
    const fromLocal = window.localStorage?.getItem(PURL_TOKEN_KEY);
    if (fromLocal) {
      window.sessionStorage?.setItem(PURL_TOKEN_KEY, fromLocal);
      window.localStorage?.removeItem(PURL_TOKEN_KEY);
      return fromLocal;
    }
  } catch {
    // storage disabled — best effort
  }
  return '';
}

class APIError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly response?: Response,
  ) {
    super(`API ${status}: ${detail}`);
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  _retries = 0,
  signal?: AbortSignal,
): Promise<T> {
  const token = getPurlToken();
  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: 'include',
    signal,
  });

  if (resp.status === 429 && _retries < 3) {
    const retryAfter = parseInt(resp.headers.get('Retry-After') || '0', 10);
    const backoff = Math.min(Math.pow(2, _retries) * 1000, 30000);
    const jitter = Math.random() * 500;
    const delay = Math.max(retryAfter * 1000, backoff) + jitter;
    await new Promise(r => setTimeout(r, delay));
    return request<T>(method, path, body, _retries + 1, signal);
  }

  if (!resp.ok) {
    let detail = `Request failed`;
    try {
      const err = await resp.json();
      detail = err.detail || detail;
    } catch {
      // ignore parse errors
    }
    throw new APIError(resp.status, detail, resp);
  }

  if (resp.status === 204) {
    return undefined as T;
  }
  return (await resp.json()) as T;
}

// ---------- Application ----------

export const posApi = {
  getOrStart: (loanId?: number, sourceChannel?: string) => {
    const params = new URLSearchParams();
    if (loanId != null) params.set('loan_id', String(loanId));
    if (sourceChannel) params.set('source_channel', sourceChannel);
    const qs = params.toString();
    return request<ApplicationResponse>(
      'GET',
      `/api/v1/pos/applications/me${qs ? `?${qs}` : ''}`,
    );
  },

  getApplication: (applicationId: string) =>
    request<ApplicationResponse>(
      'GET',
      `/api/v1/pos/applications/${applicationId}`,
    ),

  getSection: (applicationId: string, sectionKey: SectionKey) =>
    request<SectionResponse>(
      'GET',
      `/api/v1/pos/applications/${applicationId}/sections/${sectionKey}`,
    ),

  updateSection: (
    applicationId: string,
    sectionKey: SectionKey,
    body: SectionUpdateRequest,
  ) =>
    request<SectionResponse>(
      'PATCH',
      `/api/v1/pos/applications/${applicationId}/sections/${sectionKey}`,
      body,
    ),

  submit: (applicationId: string, body: ApplicationSubmitRequest) =>
    request<ApplicationSubmitResponse>(
      'POST',
      `/api/v1/pos/applications/${applicationId}/submit`,
      body,
    ),

  // ---------- Calendar ----------

  getAssignedLO: (applicationId: string) =>
    request<AssignedLOResponse>(
      'GET',
      `/api/v1/pos/calendar/applications/${applicationId}/assigned-lo`,
    ),

  getAvailableSlots: (
    applicationId: string,
    params: {
      start_date: string;
      end_date: string;
      duration_minutes?: number;
      timezone?: string;
    },
  ) => {
    const qs = new URLSearchParams({
      start_date: params.start_date,
      end_date: params.end_date,
      duration_minutes: String(params.duration_minutes ?? 30),
      timezone: params.timezone ?? 'America/New_York',
    });
    return request<AvailableSlotsResponse>(
      'GET',
      `/api/v1/pos/calendar/applications/${applicationId}/available-slots?${qs}`,
    );
  },

  holdSlot: (
    applicationId: string,
    slotStart: string,
    slotEnd: string,
    durationMinutes: number = 30,
  ) =>
    request<SlotHoldResponse>('POST', '/api/v1/pos/calendar/holds', {
      application_id: applicationId,
      slot_start: slotStart,
      slot_end: slotEnd,
      duration_minutes: durationMinutes,
    }),

  bookSlot: (body: BookingRequest) =>
    request<BookingResponse>('POST', '/api/v1/pos/calendar/bookings', body),

  cancelBooking: (appointmentId: number, reason?: string) =>
    request<{
      appointment_id: number;
      cancelled_at: string;
      notification_sent: boolean;
    }>('DELETE', `/api/v1/pos/calendar/bookings/${appointmentId}`, {
      reason: reason ?? null,
    }),

  // ---------- AI Q&A ----------

  ask: (body: AskRequest, signal?: AbortSignal) =>
    request<AskResponse>('POST', '/api/v1/pos/ai-qa/ask', body, 0, signal),

  getQAHistory: (applicationId: string, limit: number = 50) =>
    request<QAHistoryResponse>(
      'GET',
      `/api/v1/pos/ai-qa/applications/${applicationId}/history?limit=${limit}`,
    ),

  getAriaContext: (applicationId: string) =>
    request<{
      borrower_name: string | null;
      lo_name: string | null;
      lo_user_id: number | null;
      lo_phone: string | null;
      lo_email: string | null;
      completion_pct: number;
      current_step: string;
    }>('GET', `/api/v1/pos/ai-qa/applications/${applicationId}/context`),

  // ---------- Documents ----------

  getDocuments: (loanId: number) =>
    request<DocumentsResponse>(
      'GET',
      `/api/v1/pos/documents?loan_id=${loanId}`,
    ),

  // ---------- Borrower Tasks ----------

  getTasks: (applicationId: string, includeCompleted = false) =>
    request<BorrowerTasksResponse>(
      'GET',
      `/api/v1/pos/applications/${applicationId}/tasks${includeCompleted ? '?include_completed=true' : ''}`,
    ),

  completeTask: (applicationId: string, taskId: number) =>
    request<BorrowerTask>(
      'PATCH',
      `/api/v1/pos/applications/${applicationId}/tasks/${taskId}`,
      { status: 'completed' },
    ),

  // ---------- Borrower Messages ----------

  getMessages: (applicationId: string) =>
    request<BorrowerMessagesResponse>(
      'GET',
      `/api/v1/pos/applications/${applicationId}/messages`,
    ),

  markMessageRead: (applicationId: string, messageId: number) =>
    request<BorrowerMessage>(
      'PATCH',
      `/api/v1/pos/applications/${applicationId}/messages/${messageId}/read`,
    ),

  markAllMessagesRead: (applicationId: string) =>
    request<BorrowerMessagesResponse>(
      'PATCH',
      `/api/v1/pos/applications/${applicationId}/messages/read-all`,
    ),

  sendMessage: (applicationId: string, content: string) =>
    request<BorrowerMessage>(
      'POST',
      `/api/v1/pos/applications/${applicationId}/messages`,
      { content },
    ),

  // ---------- Team ----------

  getTeam: (applicationId: string) =>
    request<TeamResponse>(
      'GET',
      `/api/v1/pos/applications/${applicationId}/team`,
    ),
};

export { APIError };
