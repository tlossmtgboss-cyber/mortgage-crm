/**
 * Document Bank Analysis API Service
 *
 * Client-side API functions for bank statement analysis including large
 * deposits, NSF/overdrafts, undisclosed debts, IRS payments, risk scoring,
 * and deposit sourcing.
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
// Bank Statement Analysis
// =============================================================================

/**
 * Analyze a bank statement document
 * @param {string} documentId
 */
export async function analyzeBankStatement(documentId) {
  const response = await fetch(`${API_BASE}/bank-analysis/analyze/${documentId}`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get large deposits for a loan
 * @param {string} loanId
 * @param {number} [threshold] - Optional minimum deposit amount
 */
export async function getLargeDeposits(loanId, threshold) {
  const params = new URLSearchParams();
  if (threshold !== undefined) params.append('threshold', threshold);
  const query = params.toString() ? `?${params}` : '';
  const response = await fetch(`${API_BASE}/bank-analysis/large-deposits/${loanId}${query}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get NSF and overdraft events for a loan
 * @param {string} loanId
 */
export async function getNsfOverdrafts(loanId) {
  const response = await fetch(`${API_BASE}/bank-analysis/nsf-overdrafts/${loanId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get undisclosed debt indicators for a loan
 * @param {string} loanId
 */
export async function getUndisclosedDebts(loanId) {
  const response = await fetch(`${API_BASE}/bank-analysis/undisclosed-debts/${loanId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get IRS payment activity for a loan
 * @param {string} loanId
 */
export async function getIrsPayments(loanId) {
  const response = await fetch(`${API_BASE}/bank-analysis/irs-payments/${loanId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get bank analysis risk score for a loan
 * @param {string} loanId
 */
export async function getRiskScore(loanId) {
  const response = await fetch(`${API_BASE}/bank-analysis/risk-score/${loanId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get bank analysis summary for a loan
 * @param {string} loanId
 */
export async function getBankSummary(loanId) {
  const response = await fetch(`${API_BASE}/bank-analysis/summary/${loanId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Source a specific deposit (document its origin)
 * @param {string} depositId
 * @param {Object} sourcing - Sourcing details
 */
export async function sourceDeposit(depositId, sourcing) {
  const response = await fetch(`${API_BASE}/bank-analysis/source-deposit/${depositId}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(sourcing),
  });
  return handleResponse(response);
}

// =============================================================================
// Export all functions
// =============================================================================

export const docBankAnalysisAPI = {
  analyzeBankStatement,
  getLargeDeposits,
  getNsfOverdrafts,
  getUndisclosedDebts,
  getIrsPayments,
  getRiskScore,
  getBankSummary,
  sourceDeposit,
};

export default docBankAnalysisAPI;
