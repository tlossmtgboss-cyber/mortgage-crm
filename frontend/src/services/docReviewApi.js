/**
 * Document Review Queue API Service
 *
 * Client-side API functions for the AI document review and review queue system.
 * Wraps 13 endpoints under /api/v1/smart-docs/doc-review/*
 */
import { API_BASE_URL } from './api';

const API_BASE = `${API_BASE_URL}/api/v1/smart-docs/doc-review`;

/**
 * Handle API responses — parse JSON, throw on error using `detail` field.
 */
async function handleResponse(response) {
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    if (response.status === 403) {
      throw new Error(error.detail || 'Access denied. You do not have permission for this action.');
    }
    if (response.status === 401) {
      throw new Error('Session expired. Please log in again.');
    }
    if (response.status === 429) {
      throw new Error('Too many requests. Please wait a moment and try again.');
    }
    throw new Error(error.detail || `Request failed (${response.status})`);
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
// Queue
// =============================================================================

/**
 * Get the review queue, with optional filters.
 *
 * @param {object} opts
 * @param {string} [opts.priority]  - Filter by priority: CRITICAL, HIGH, NORMAL, LOW
 * @param {string} [opts.docType]   - Filter by document type
 * @param {number} [opts.limit=50]  - Max items to return
 * @param {number} [opts.offset=0]  - Pagination offset
 */
export async function getQueue({ priority, docType, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit, offset });
  if (priority) params.append('priority', priority);
  if (docType) params.append('doc_type', docType);

  const response = await fetch(`${API_BASE}/queue?${params}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get review queue statistics for the current user's organization.
 */
export async function getQueueStats() {
  const response = await fetch(`${API_BASE}/queue/stats`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Claim a document for review (prevents double-claiming).
 *
 * @param {number|string} documentId
 * @param {string} [reviewerId]  - Optional reviewer ID (sent in request body)
 */
export async function claimDocument(documentId, reviewerId) {
  const body = reviewerId ? JSON.stringify({ reviewer_id: reviewerId }) : JSON.stringify({});
  const response = await fetch(`${API_BASE}/queue/${documentId}/claim`, {
    method: 'POST',
    headers: getHeaders(),
    body,
  });
  return handleResponse(response);
}

/**
 * Release a claimed document back to the review queue.
 *
 * @param {number|string} documentId
 */
export async function releaseDocument(documentId) {
  const response = await fetch(`${API_BASE}/queue/${documentId}/release`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// AI Review
// =============================================================================

/**
 * Trigger AI review of a single document.
 *
 * @param {number|string} documentId
 */
export async function aiReview(documentId) {
  const response = await fetch(`${API_BASE}/ai-review/${documentId}`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Batch AI review all unreviewed documents for a loan.
 *
 * @param {number|string} loanId
 * @param {object} [options={}]  - Additional options sent in request body
 */
export async function batchAiReview(loanId, options = {}) {
  const response = await fetch(`${API_BASE}/ai-review/batch/${loanId}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(options),
  });
  return handleResponse(response);
}

// =============================================================================
// Cross-Validation
// =============================================================================

/**
 * Run cross-document consistency validation for a loan.
 *
 * @param {number|string} loanId
 */
export async function crossValidate(loanId) {
  const response = await fetch(`${API_BASE}/cross-validate/${loanId}`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Review History
// =============================================================================

/**
 * Get the review history for a document.
 *
 * @param {number|string} documentId
 */
export async function getReviewHistory(documentId) {
  const response = await fetch(`${API_BASE}/document/${documentId}/review-history`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Auto-Review Settings
// =============================================================================

/**
 * Get the auto-review settings for the current organization.
 */
export async function getAutoReviewSettings() {
  const response = await fetch(`${API_BASE}/auto-review-settings`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Update auto-review settings.
 *
 * @param {object} settings  - Settings object (e.g. auto_approve_threshold, enabled_checks)
 */
export async function updateAutoReviewSettings(settings) {
  const response = await fetch(`${API_BASE}/auto-review-settings`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(settings),
  });
  return handleResponse(response);
}

// =============================================================================
// Stats & Completeness
// =============================================================================

/**
 * Get review statistics over the given number of days.
 *
 * @param {number} [days=30]
 */
export async function getReviewStats(days = 30) {
  const response = await fetch(`${API_BASE}/stats?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get document completeness for a loan.
 *
 * @param {number|string} loanId
 */
export async function getLoanCompleteness(loanId) {
  const response = await fetch(`${API_BASE}/loan/${loanId}/completeness`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// AI Extract and Review
// =============================================================================

/**
 * Run AI extraction and review on a document in a single call.
 *
 * @param {number|string} documentId
 */
export async function aiExtractAndReview(documentId) {
  const response = await fetch(`${API_BASE}/document/${documentId}/ai-extract-and-review`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Default export — all functions as properties of a single object
// =============================================================================

const docReviewApi = {
  getQueue,
  getQueueStats,
  claimDocument,
  releaseDocument,
  aiReview,
  batchAiReview,
  crossValidate,
  getReviewHistory,
  getAutoReviewSettings,
  updateAutoReviewSettings,
  getReviewStats,
  getLoanCompleteness,
  aiExtractAndReview,
};

export default docReviewApi;
