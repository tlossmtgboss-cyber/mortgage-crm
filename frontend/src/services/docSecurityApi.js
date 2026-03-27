/**
 * Document Security API Service
 *
 * Client-side API functions for document security, audit logging, integrity
 * checks, fraud analysis, retention policies, watermarking, and encryption.
 */
import { API_BASE_URL } from './api';

const API_BASE = `${API_BASE_URL}/api/v1/smart-docs`;

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
// Audit Log
// =============================================================================

/**
 * Get audit log entries with optional filters
 * @param {Object} params
 * @param {number} [params.days=30]
 * @param {string} [params.documentId]
 * @param {string} [params.action]
 * @param {number} [params.limit=100]
 * @param {number} [params.offset=0]
 */
export async function getAuditLog({ days = 30, documentId, action, limit = 100, offset = 0 } = {}) {
  const params = new URLSearchParams({ days, limit, offset });
  if (documentId) params.append('document_id', documentId);
  if (action) params.append('action', action);

  const response = await fetch(`${API_BASE}/doc-security/audit-log?${params}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get audit log for a specific document
 * @param {string} documentId
 */
export async function getDocumentAuditLog(documentId) {
  const response = await fetch(`${API_BASE}/doc-security/audit-log/${documentId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Log an access event for a document
 * @param {string} documentId
 * @param {string} action
 * @param {string} [details='']
 */
export async function logAccess(documentId, action, details = '') {
  const response = await fetch(`${API_BASE}/doc-security/log-access`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ document_id: documentId, action, details }),
  });
  return handleResponse(response);
}

// =============================================================================
// Integrity Checks
// =============================================================================

/**
 * Run an integrity check on a document
 * @param {string} documentId
 */
export async function checkIntegrity(documentId) {
  const response = await fetch(`${API_BASE}/doc-security/integrity-check/${documentId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Run integrity checks on multiple documents
 * @param {string[]} documentIds
 */
export async function batchIntegrityCheck(documentIds) {
  const response = await fetch(`${API_BASE}/doc-security/integrity-check/batch`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ document_ids: documentIds }),
  });
  return handleResponse(response);
}

/**
 * Get integrity check history for a document
 * @param {string} documentId
 */
export async function getIntegrityHistory(documentId) {
  const response = await fetch(`${API_BASE}/doc-security/integrity-history/${documentId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Fraud Analysis
// =============================================================================

/**
 * Get fraud analysis for a loan
 * @param {string} loanId
 */
export async function getFraudAnalysis(loanId) {
  const response = await fetch(`${API_BASE}/doc-security/fraud-analysis/${loanId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get fraud summary for a loan (or overall if no loanId)
 * @param {string} [loanId]
 */
export async function getFraudSummary(loanId) {
  const url = loanId
    ? `${API_BASE}/doc-security/fraud/${loanId}/summary`
    : `${API_BASE}/doc-security/fraud-summary`;
  const response = await fetch(url, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Retention Policies
// =============================================================================

/**
 * Get all retention policies
 */
export async function getRetentionPolicies() {
  const response = await fetch(`${API_BASE}/doc-security/retention-policies`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Create a new retention policy
 * @param {Object} policy
 */
export async function createRetentionPolicy(policy) {
  const response = await fetch(`${API_BASE}/doc-security/retention-policies`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(policy),
  });
  return handleResponse(response);
}

/**
 * Update an existing retention policy
 * @param {string} policyId
 * @param {Object} policy
 */
export async function updateRetentionPolicy(policyId, policy) {
  const response = await fetch(`${API_BASE}/doc-security/retention-policies/${policyId}`, {
    method: 'PUT',
    headers: getHeaders(),
    body: JSON.stringify(policy),
  });
  return handleResponse(response);
}

/**
 * Get documents with expiring retentions
 * @param {number} [days=30]
 */
export async function getExpiringRetentions(days = 30) {
  const response = await fetch(`${API_BASE}/doc-security/retention-expiring?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Watermarking & Encryption
// =============================================================================

/**
 * Watermark a document
 * @param {string} documentId
 * @param {Object} [options={}]
 */
export async function watermarkDocument(documentId, options = {}) {
  const response = await fetch(`${API_BASE}/doc-security/watermark/${documentId}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(options),
  });
  return handleResponse(response);
}

/**
 * Get encryption status of a document
 * @param {string} documentId
 */
export async function getEncryptionStatus(documentId) {
  const response = await fetch(`${API_BASE}/doc-security/encryption-status/${documentId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Encrypt a document
 * @param {string} documentId
 */
export async function encryptDocument(documentId) {
  const response = await fetch(`${API_BASE}/doc-security/encrypt/${documentId}`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Compliance & Suspicious Activity
// =============================================================================

/**
 * Get compliance report
 * @param {number} [days=30]
 */
export async function getComplianceReport(days = 30) {
  const response = await fetch(`${API_BASE}/doc-security/compliance-report?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get suspicious activity report
 * @param {number} [days=30]
 */
export async function getSuspiciousActivity(days = 30) {
  const response = await fetch(`${API_BASE}/doc-security/suspicious-activity?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Export all functions
// =============================================================================

export const docSecurityAPI = {
  // Audit Log
  getAuditLog,
  getDocumentAuditLog,
  logAccess,
  // Integrity
  checkIntegrity,
  batchIntegrityCheck,
  getIntegrityHistory,
  // Fraud
  getFraudAnalysis,
  getFraudSummary,
  // Retention
  getRetentionPolicies,
  createRetentionPolicy,
  updateRetentionPolicy,
  getExpiringRetentions,
  // Watermark & Encryption
  watermarkDocument,
  getEncryptionStatus,
  encryptDocument,
  // Compliance
  getComplianceReport,
  getSuspiciousActivity,
};

export default docSecurityAPI;
