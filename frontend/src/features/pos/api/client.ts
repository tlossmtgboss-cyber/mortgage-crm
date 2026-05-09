// API client for the POS feature.
//
// Assumes a PURL token is present in either:
//   - localStorage under key "perennia_purl_token", OR
//   - a global window.__PURL_TOKEN__ (set by your portal shell)
//
// Adjust `getPurlToken()` below if your portal stores tokens differently.

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

function getPurlToken(): string {
  if (typeof window === 'undefined') return '';
  return (
    (window as any).__PURL_TOKEN__ ||
    window.localStorage?.getItem('perennia_purl_token') ||
    ''
  );
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
  });

  if (resp.status === 429 && _retries < 3) {
    const retryAfter = parseInt(resp.headers.get('Retry-After') || '0', 10);
    const backoff = Math.min(Math.pow(2, _retries) * 1000, 30000);
    const jitter = Math.random() * 500;
    const delay = Math.max(retryAfter * 1000, backoff) + jitter;
    await new Promise(r => setTimeout(r, delay));
    return request<T>(method, path, body, _retries + 1);
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

  ask: (body: AskRequest) =>
    request<AskResponse>('POST', '/api/v1/pos/ai-qa/ask', body),

  getQAHistory: (applicationId: string, limit: number = 50) =>
    request<QAHistoryResponse>(
      'GET',
      `/api/v1/pos/ai-qa/applications/${applicationId}/history?limit=${limit}`,
    ),

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
