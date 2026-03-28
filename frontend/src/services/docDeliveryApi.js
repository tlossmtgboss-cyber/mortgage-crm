/**
 * Document Delivery API Service
 *
 * Client-side API functions for sending needs lists, reminders,
 * batch notifications, and portal link resends to borrowers.
 * Wraps 4 endpoints under /api/v1/smart-docs/delivery/*
 */
import { API_BASE_URL } from './api';

const API_BASE = `${API_BASE_URL}/api/v1/smart-docs/delivery`;

/**
 * Handle API responses — parse JSON, throw on error using `detail` field.
 */
async function handleResponse(response) {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

/**
 * Build standard auth + content-type headers.
 */
function getHeaders() {
  const token = localStorage.getItem('token');
  return {
    'Authorization': token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

// =============================================================================
// Send Needs List
// =============================================================================

/**
 * Send a needs list to a borrower for a given loan.
 *
 * @param {number|string} loanId
 * @param {string[]} [channels=['email']]  - Delivery channels: 'email', 'sms'
 * @param {string|null} [message=null]     - Optional custom message
 */
export async function sendNeedsList(loanId, channels = ['email'], message = null) {
  const body = { loan_id: loanId, channels };
  if (message) body.message = message;

  const response = await fetch(`${API_BASE}/send-needs-list`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse(response);
}

// =============================================================================
// Send Reminder
// =============================================================================

/**
 * Send a reminder for outstanding documents on a loan.
 *
 * @param {number|string} loanId
 * @param {string[]} [channels=['email']]            - Delivery channels
 * @param {Array<number|string>|null} [documentRequestIds=null] - Specific doc request IDs, or null for all
 */
export async function sendReminder(loanId, channels = ['email'], documentRequestIds = null) {
  const body = { loan_id: loanId, channels };
  if (documentRequestIds) body.document_request_ids = documentRequestIds;

  const response = await fetch(`${API_BASE}/send-reminder`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse(response);
}

// =============================================================================
// Send Batch
// =============================================================================

/**
 * Send batch reminders/needs lists across multiple loans.
 *
 * @param {Array<number|string>} loanIds
 * @param {string[]} [channels=['email']]
 * @param {string} [template='needs_list']
 */
export async function sendBatch(loanIds, channels = ['email'], template = 'needs_list') {
  const response = await fetch(`${API_BASE}/send-batch`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ loan_ids: loanIds, channels, template }),
  });
  return handleResponse(response);
}

// =============================================================================
// Resend Portal Link
// =============================================================================

/**
 * Resend the borrower portal link for a loan.
 *
 * @param {number|string} loanId
 * @param {string} [channel='email']  - 'email' or 'sms'
 */
export async function resendPortalLink(loanId, channel = 'email') {
  const response = await fetch(`${API_BASE}/resend-portal-link`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ loan_id: loanId, channel }),
  });
  return handleResponse(response);
}

// =============================================================================
// Default export — all functions as properties of a single object
// =============================================================================

const docDeliveryApi = {
  sendNeedsList,
  sendReminder,
  sendBatch,
  resendPortalLink,
};

export default docDeliveryApi;
