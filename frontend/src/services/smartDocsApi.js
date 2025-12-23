/**
 * Smart Document Collection API Service
 *
 * Client-side API functions for the intelligent document collection system.
 */

// Use localhost:8000 for development, relative path for production
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_HOST = isProduction ? '' : 'http://localhost:8000';
const API_BASE = `${API_HOST}/api/v1/smart-docs`;

/**
 * Helper to handle API responses
 */
async function handleResponse(response) {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

/**
 * Get auth headers (assumes token in localStorage)
 */
function getHeaders() {
  const token = localStorage.getItem('token');
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
  const response = await fetch(
    `${API_BASE}/needs-list/${loanId}/custom-request?borrower_id=${borrowerId}`,
    {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(data),
    }
  );
  return handleResponse(response);
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

  const token = localStorage.getItem('token');
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
// Export all functions
// =============================================================================

export const smartDocsAPI = {
  // Needs List
  generateNeedsList,
  getNeedsList,
  addCustomRequest,
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
};

export default smartDocsAPI;
