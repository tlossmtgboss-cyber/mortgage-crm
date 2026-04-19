/**
 * Smart Document Collection API Service
 *
 * Client-side API functions for the intelligent document collection system.
 */
import { API_BASE_URL } from './api';
import { getToken } from '../utils/tokenStore';

const API_BASE = `${API_BASE_URL}/api/v1/smart-docs`;

/**
 * Helper to handle API responses
 */
async function handleResponse(response) {
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = error.detail;
    let message;
    if (Array.isArray(detail)) {
      message = detail.map(d => d.msg || JSON.stringify(d)).join('; ');
    } else if (typeof detail === 'object' && detail !== null) {
      message = detail.msg || JSON.stringify(detail);
    } else {
      message = detail;
    }
    if (response.status === 403) {
      throw new Error(message || 'Access denied. You do not have permission for this action.');
    }
    if (response.status === 401) {
      throw new Error('Session expired. Please log in again.');
    }
    if (response.status === 429) {
      throw new Error('Too many requests. Please wait a moment and try again.');
    }
    throw new Error(message || `Request failed (${response.status})`);
  }
  return response.json();
}

/**
 * Get auth headers (assumes token in localStorage)
 */
function getHeaders() {
  const token = getToken();
  return {
    'Authorization': token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

// =============================================================================
// Needs List
// =============================================================================

/**
 * Generate a needs list for a loan
 */
export async function generateNeedsList(params) {
  const response = await fetch(`${API_BASE}/needs-list/generate`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(params),
  });
  return handleResponse(response);
}

/**
 * Get needs list for a loan
 */
export async function getNeedsList(loanId) {
  const response = await fetch(`${API_BASE}/needs-list/${loanId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Add a custom document request
 */
export async function addCustomRequest(loanId, borrowerId, data) {
  const params = borrowerId ? `?borrower_id=${borrowerId}` : '';
  const response = await fetch(
    `${API_BASE}/needs-list/${loanId}/custom-request${params}`,
    {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(data),
    }
  );
  return handleResponse(response);
}

/**
 * Add multiple custom document requests in parallel (concurrency-capped).
 * Returns per-document success/failure results preserving original order.
 */
export async function addBulkCustomRequests(loanId, borrowerId, requests, concurrency = 5) {
  const results = new Array(requests.length);
  let cursor = 0;

  async function worker() {
    while (cursor < requests.length) {
      const idx = cursor++;
      const req = requests[idx];
      try {
        const result = await addCustomRequest(loanId, borrowerId, req);
        results[idx] = { success: true, title: req.title, result };
      } catch (err) {
        results[idx] = { success: false, title: req.title, error: err.message };
      }
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, requests.length) }, () => worker());
  await Promise.all(workers);
  return results;
}

/**
 * Waive a document request
 */
export async function waiveRequest(requestId, reason, waivedBy) {
  const response = await fetch(`${API_BASE}/needs-list/request/${requestId}/waive`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ reason, waived_by: waivedBy }),
  });
  return handleResponse(response);
}

// =============================================================================
// Document Upload & Processing
// =============================================================================

/**
 * Upload a document
 */
export async function uploadDocument(file, loanId, borrowerId, requestId = null, docType = null) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('loan_id', loanId);
  formData.append('borrower_id', borrowerId);
  if (requestId) formData.append('request_id', requestId);
  if (docType) formData.append('doc_type', docType);

  const token = getToken();
  const response = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    headers: {
      'Authorization': token ? `Bearer ${token}` : '',
    },
    body: formData,
  });
  return handleResponse(response);
}

/**
 * Get document details
 */
export async function getDocument(documentId) {
  const response = await fetch(`${API_BASE}/document/${documentId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get all documents for a loan
 */
export async function getLoanDocuments(loanId, status = null) {
  const params = status ? `?status=${status}` : '';
  const response = await fetch(`${API_BASE}/documents/${loanId}${params}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Submit manual review decision
 */
export async function manualReview(documentId, decision, reviewer, notes = null) {
  const response = await fetch(`${API_BASE}/document/${documentId}/manual-review`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ decision, reviewer, notes }),
  });
  return handleResponse(response);
}

// =============================================================================
// Freshness & Expiration
// =============================================================================

/**
 * Get expiring documents
 */
export async function getExpiringDocuments(loanId = null, daysAhead = 14) {
  const params = new URLSearchParams({ days_ahead: daysAhead });
  if (loanId) params.append('loan_id', loanId);

  const response = await fetch(`${API_BASE}/expiring?${params}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Run expiration check
 */
export async function runExpirationCheck() {
  const response = await fetch(`${API_BASE}/check-expiration`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Process pending renewals
 */
export async function processRenewals() {
  const response = await fetch(`${API_BASE}/process-renewals`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Payroll Frequency
// =============================================================================

/**
 * Infer payroll frequency from historical data
 */
export async function inferPayrollFrequency(borrowerId) {
  const response = await fetch(`${API_BASE}/infer-payroll-frequency/${borrowerId}`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Update payroll frequency
 */
export async function updatePayrollFrequency(loanId, borrowerId, frequency) {
  const response = await fetch(`${API_BASE}/payroll-frequency/${loanId}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ borrower_id: borrowerId, frequency }),
  });
  return handleResponse(response);
}

// =============================================================================
// Templates
// =============================================================================

/**
 * Get available templates
 */
export async function getTemplates(activeOnly = true) {
  const response = await fetch(`${API_BASE}/templates?active_only=${activeOnly}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get template details
 */
export async function getTemplate(templateId) {
  const response = await fetch(`${API_BASE}/templates/${templateId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Events
// =============================================================================

/**
 * Get document events for a loan
 */
export async function getLoanEvents(loanId, limit = 50) {
  const response = await fetch(`${API_BASE}/events/${loanId}?limit=${limit}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Applicant Dashboard Views
// =============================================================================

/**
 * Get applicants with documents pending review
 */
export async function getApplicantsPendingReview(page = 1, limit = 20) {
  const response = await fetch(`${API_BASE}/applicants/pending-review?page=${page}&limit=${limit}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get applicants with outstanding document requests
 */
export async function getApplicantsOutstandingDocs(page = 1, limit = 20, overdueOnly = false) {
  const params = new URLSearchParams({ page, limit });
  if (overdueOnly) params.append('include_overdue_only', 'true');

  const response = await fetch(`${API_BASE}/applicants/outstanding-docs?${params}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get dashboard summary statistics
 */
export async function getDashboardSummary() {
  const response = await fetch(`${API_BASE}/dashboard/summary`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Queue View
// =============================================================================

/**
 * Get the prioritized document queue
 */
export async function getQueue(page = 1, limit = 20, slaStatus = null, search = null) {
  const params = new URLSearchParams({ page, limit });
  if (slaStatus) params.append('sla_status', slaStatus);
  if (search) params.append('search', search);

  const response = await fetch(`${API_BASE}/queue?${params}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get queue summary statistics
 */
export async function getQueueSummary() {
  const response = await fetch(`${API_BASE}/queue/summary`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get detailed queue info for a client
 */
export async function getQueueDetail(loanId) {
  const response = await fetch(`${API_BASE}/queue/${loanId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Reminder Settings
// =============================================================================

/**
 * Get reminder settings for a loan
 */
export async function getReminderSettings(loanId) {
  const response = await fetch(`${API_BASE}/reminders/${loanId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Update reminder settings for a loan
 */
export async function updateReminderSettings(loanId, settings) {
  const response = await fetch(`${API_BASE}/reminders/${loanId}`, {
    method: 'PUT',
    headers: getHeaders(),
    body: JSON.stringify(settings),
  });
  return handleResponse(response);
}

/**
 * Manually send a reminder for a loan
 */
export async function sendReminder(loanId) {
  const response = await fetch(`${API_BASE}/reminders/${loanId}/send`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// DocuSign / Portal Integration
// =============================================================================

/**
 * Send a document request to the client portal for DocuSign or LOE
 */
export async function sendToPortalForDocuSign(loanId, data) {
  const response = await fetch(`${API_BASE}/portal/send-for-signature/${loanId}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

/**
 * Analyze loan ID mismatches between Smart Docs and PURL system
 */
export async function analyzeLoanIdMismatches() {
  const response = await fetch(`${API_BASE}/portal/loan-id-mismatches`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Fix loan ID mismatches between Smart Docs and PURL system
 * @param {boolean} dryRun - If true, only report what would be fixed
 */
export async function fixLoanIdMismatches(dryRun = true) {
  const response = await fetch(`${API_BASE}/portal/fix-loan-id-mismatches?dry_run=${dryRun}`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Export all functions
// =============================================================================

export const smartDocsAPI = {
  // Needs List
  generateNeedsList,
  getNeedsList,
  addCustomRequest,
  addBulkCustomRequests,
  waiveRequest,
  // Documents
  uploadDocument,
  getDocument,
  getLoanDocuments,
  manualReview,
  // Freshness
  getExpiringDocuments,
  runExpirationCheck,
  processRenewals,
  // Payroll
  inferPayrollFrequency,
  updatePayrollFrequency,
  // Templates
  getTemplates,
  getTemplate,
  // Events
  getLoanEvents,
  // Dashboard
  getApplicantsPendingReview,
  getApplicantsOutstandingDocs,
  getDashboardSummary,
  // Queue
  getQueue,
  getQueueSummary,
  getQueueDetail,
  // Reminders
  getReminderSettings,
  updateReminderSettings,
  sendReminder,
  // DocuSign / Portal
  sendToPortalForDocuSign,
  analyzeLoanIdMismatches,
  fixLoanIdMismatches,
};

export default smartDocsAPI;
