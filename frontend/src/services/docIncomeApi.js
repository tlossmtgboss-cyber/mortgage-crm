/**
 * Document Income API Service
 *
 * Client-side API functions for income calculation, history, source management,
 * and approval workflows.
 */
import { API_BASE_URL } from './api';

const API_BASE = `${API_BASE_URL}/api/v1/smart-docs`;

/**
 * Helper to handle API responses
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
// Income Calculation
// =============================================================================

/**
 * Calculate income for a loan
 * @param {string} loanId
 * @param {Object} [options={}] - Calculation options
 */
export async function calculateIncome(loanId, options = {}) {
  const response = await fetch(`${API_BASE}/income/calculate/${loanId}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(options),
  });
  return handleResponse(response);
}

/**
 * Get income calculation history for a loan
 * @param {string} loanId
 */
export async function getIncomeHistory(loanId) {
  const response = await fetch(`${API_BASE}/income/history/${loanId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get income sources for a loan
 * @param {string} loanId
 */
export async function getIncomeSources(loanId) {
  const response = await fetch(`${API_BASE}/income/sources/${loanId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Override an income source value
 * @param {string} sourceId
 * @param {Object} override - Override details
 */
export async function overrideSource(sourceId, override) {
  const response = await fetch(`${API_BASE}/income/sources/${sourceId}/override`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(override),
  });
  return handleResponse(response);
}

// =============================================================================
// Income Approval Workflow
// =============================================================================

/**
 * Submit income calculation for approval
 * @param {string} loanId
 */
export async function submitForApproval(loanId) {
  const response = await fetch(`${API_BASE}/income/submit/${loanId}`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Approve income calculation
 * @param {string} loanId
 * @param {string} [notes] - Optional approval notes
 */
export async function approveIncome(loanId, notes) {
  const response = await fetch(`${API_BASE}/income/approve/${loanId}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ notes }),
  });
  return handleResponse(response);
}

/**
 * Reject income calculation
 * @param {string} loanId
 * @param {string} reason - Rejection reason
 */
export async function rejectIncome(loanId, reason) {
  const response = await fetch(`${API_BASE}/income/reject/${loanId}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ reason }),
  });
  return handleResponse(response);
}

// =============================================================================
// Export all functions
// =============================================================================

export const docIncomeAPI = {
  calculateIncome,
  getIncomeHistory,
  getIncomeSources,
  overrideSource,
  submitForApproval,
  approveIncome,
  rejectIncome,
};

export default docIncomeAPI;
