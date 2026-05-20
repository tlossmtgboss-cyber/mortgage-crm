/**
 * Document Income API Service
 *
 * Client-side API functions for income calculation, history, source management,
 * and approval workflows.
 */
import { API_BASE_URL } from './api';
import { getToken } from '../utils/tokenStore';

const API_BASE = `${API_BASE_URL}/api/smart-docs`;

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
  const token = getToken();
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
  const response = await fetch(`${API_BASE}/income/calculations/${loanId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get a single calculation's details
 * @param {string} calculationId
 */
export async function getCalculation(calculationId) {
  const response = await fetch(`${API_BASE}/income/calculation/${calculationId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get income sources for a calculation
 * @param {string} calculationId
 */
export async function getIncomeSources(calculationId) {
  const response = await fetch(`${API_BASE}/income/calculation/${calculationId}/sources`, {
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
  const response = await fetch(`${API_BASE}/income/source/${sourceId}/override`, {
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
 * Submit income calculation for review
 * @param {string} calculationId
 * @param {Object} [reviewData={}] - Review details
 */
export async function submitForApproval(calculationId, reviewData = {}) {
  const response = await fetch(`${API_BASE}/income/calculation/${calculationId}/review`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(reviewData),
  });
  return handleResponse(response);
}

/**
 * Approve income calculation
 * @param {string} calculationId
 * @param {string} [notes] - Optional approval notes
 */
export async function approveIncome(calculationId, notes) {
  const response = await fetch(`${API_BASE}/income/calculation/${calculationId}/approve`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ notes }),
  });
  return handleResponse(response);
}

/**
 * Reject income calculation
 * @param {string} calculationId
 * @param {string} reason - Rejection reason
 */
export async function rejectIncome(calculationId, reason) {
  const response = await fetch(`${API_BASE}/income/calculation/${calculationId}/reject`, {
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
  getCalculation,
  getIncomeHistory,
  getIncomeSources,
  overrideSource,
  submitForApproval,
  approveIncome,
  rejectIncome,
};

export default docIncomeAPI;
