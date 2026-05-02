/**
 * API client for the Microsoft 365 integration.
 * Uses the PerenniaAPI client from lib/api/client.js.
 */
import { api } from "../../lib/api/client";

export type ReconciliationStatus =
  | "unmatched"
  | "suggested"
  | "auto_linked"
  | "manually_linked"
  | "dismissed";

export type ReconciliationLinkType = "lead" | "loan" | "partner";

export type SubscriptionKind = "calendar" | "email" | "teams_chats";

export interface SuggestedLink {
  link_type: ReconciliationLinkType;
  link_id: number;
  label: string;
  confidence: number;
  strategy: string;
  metadata: Record<string, unknown>;
}

export interface EmailReconciliationItem {
  id: number;
  subject: string;
  sender_email: string;
  sender_name: string | null;
  recipient_emails: string[];
  received_at: string;
  has_attachments: boolean;
  body_preview: string | null;
  web_link: string | null;
  status: ReconciliationStatus;
  match_confidence: number | null;
  match_strategy: string | null;
  matched_link_type: ReconciliationLinkType | null;
  matched_link_id: number | null;
  suggested_links: SuggestedLink[] | null;
}

export interface TeamsChatReconciliationItem {
  id: number;
  chat_topic: string | null;
  sender_email: string;
  sender_name: string | null;
  sent_at: string;
  body_text: string | null;
  web_link: string | null;
  status: ReconciliationStatus;
  match_confidence: number | null;
  match_strategy: string | null;
  matched_link_type: ReconciliationLinkType | null;
  matched_link_id: number | null;
  suggested_links: SuggestedLink[] | null;
}

export interface ReconciliationListResponse {
  emails: EmailReconciliationItem[];
  teams_chats: TeamsChatReconciliationItem[];
  total_unmatched: number;
  total_suggested: number;
}

export interface MSAccountStatus {
  id: number;
  upn: string;
  display_name: string | null;
  is_active: boolean;
  scopes: string[];
  last_error: string | null;
  connected_at: string;
  subscriptions: Array<{
    kind: SubscriptionKind;
    expiration_datetime: string;
    last_renewed_at: string | null;
    failure_count: number;
  }>;
}

export interface CalendarSyncStatus {
  total_mapped_events: number;
  last_inbound_sync_at: string | null;
  last_outbound_sync_at: string | null;
  pending_outbound: number;
}

const BASE = "/api/v1/microsoft";

export const microsoftApi = {
  // OAuth
  initOAuth: () => api.post(`${BASE}/oauth/init`),

  // Account
  getAccount: () => api.get(`${BASE}/account`),
  disconnect: () => api.delete(`${BASE}/account`),

  // Calendar
  calendarStatus: () => api.get(`${BASE}/calendar/status`),
  pushEvent: (event: {
    crm_event_id: number;
    title: string;
    body_html?: string;
    start: string;
    end: string;
    timezone?: string;
    location?: string;
    attendees?: string[];
    is_online_meeting?: boolean;
  }) => api.post(`${BASE}/calendar/push`, event),
  deleteEvent: (crmEventId: number) =>
    api.delete(`${BASE}/calendar/${crmEventId}`),

  // Reconciliation
  listReconciliation: (params?: { status?: ReconciliationStatus[]; limit?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.status) {
      params.status.forEach((s) => searchParams.append("status", s));
    }
    if (params?.limit) {
      searchParams.set("limit", String(params.limit));
    }
    const qs = searchParams.toString();
    return api.get(`${BASE}/reconciliation${qs ? `?${qs}` : ""}`);
  },
  linkEmail: (emailId: number, body: { link_type: ReconciliationLinkType; link_id: number }) =>
    api.post(`${BASE}/reconciliation/email/${emailId}/link`, body),
  dismissEmail: (emailId: number, reason?: string) =>
    api.post(`${BASE}/reconciliation/email/${emailId}/dismiss`, { reason }),
  linkTeamsMessage: (
    messageId: number,
    body: { link_type: ReconciliationLinkType; link_id: number },
  ) => api.post(`${BASE}/reconciliation/teams/${messageId}/link`, body),
};
