/**
 * Smart Docs Analytics API Service
 *
 * Client-side API functions for the doc analytics dashboard endpoints.
 * All 12 endpoints are under /api/v1/smart-docs/doc-analytics/*.
 */
import { API_BASE_URL } from './api';

const API_BASE = `${API_BASE_URL}/api/v1/smart-docs`;

// =============================================================================
// Shared helpers (same pattern as smartDocsApi.js)
// =============================================================================

async function handleResponse(response) {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function getHeaders() {
  const token = localStorage.getItem('token');
  return {
    'Authorization': token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

// =============================================================================
// Analytics endpoints
// =============================================================================

/**
 * Get top-level analytics dashboard summary.
 * @param {number} days - Lookback window in days (default 30)
 */
export async function getDashboard(days = 30) {
  const response = await fetch(`${API_BASE}/doc-analytics/dashboard?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get pipeline completeness data.
 * @param {number} [minPct] - Optional minimum completeness percentage filter
 * @param {number} [maxPct] - Optional maximum completeness percentage filter
 */
export async function getPipelineCompleteness(minPct, maxPct) {
  const params = new URLSearchParams();
  if (minPct !== undefined && minPct !== null) params.append('min_pct', minPct);
  if (maxPct !== undefined && maxPct !== null) params.append('max_pct', maxPct);

  const qs = params.toString();
  const url = qs
    ? `${API_BASE}/doc-analytics/pipeline-completeness?${qs}`
    : `${API_BASE}/doc-analytics/pipeline-completeness`;

  const response = await fetch(url, { headers: getHeaders() });
  return handleResponse(response);
}

/**
 * Get SLA compliance report.
 * @param {number} days - Lookback window in days (default 30)
 */
export async function getSlaCompliance(days = 30) {
  const response = await fetch(`${API_BASE}/doc-analytics/sla-compliance?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get AI document classification performance metrics.
 * @param {number} days - Lookback window in days (default 30)
 */
export async function getAiPerformance(days = 30) {
  const response = await fetch(`${API_BASE}/doc-analytics/ai-performance?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get follow-up effectiveness metrics.
 * @param {number} days - Lookback window in days (default 30)
 */
export async function getFollowupEffectiveness(days = 30) {
  const response = await fetch(`${API_BASE}/doc-analytics/followup-effectiveness?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get income verification analysis summary.
 * @param {number} days - Lookback window in days (default 30)
 */
export async function getIncomeSummary(days = 30) {
  const response = await fetch(`${API_BASE}/doc-analytics/income-summary?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get bank statement analysis summary.
 * @param {number} days - Lookback window in days (default 30)
 */
export async function getBankAnalysisSummary(days = 30) {
  const response = await fetch(`${API_BASE}/doc-analytics/bank-analysis-summary?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get e-signature metrics.
 * @param {number} days - Lookback window in days (default 30)
 */
export async function getEsignMetrics(days = 30) {
  const response = await fetch(`${API_BASE}/doc-analytics/esign-metrics?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get processor productivity report.
 * @param {number} days - Lookback window in days (default 30)
 */
export async function getProcessorProductivity(days = 30) {
  const response = await fetch(`${API_BASE}/doc-analytics/processor-productivity?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get document collection timeline for a specific loan.
 * @param {string} loanId - The loan identifier
 */
export async function getLoanTimeline(loanId) {
  const response = await fetch(`${API_BASE}/doc-analytics/loan/${loanId}/timeline`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get trend data over time.
 * @param {string} period - Aggregation period: 'daily', 'weekly', or 'monthly' (default 'weekly')
 * @param {number} days  - Total lookback window in days (default 90)
 */
export async function getTrends(period = 'weekly', days = 90) {
  const response = await fetch(
    `${API_BASE}/doc-analytics/trends?period=${period}&days=${days}`,
    { headers: getHeaders() },
  );
  return handleResponse(response);
}

/**
 * Get pipeline bottleneck analysis.
 * @param {number} days - Lookback window in days (default 30)
 */
export async function getBottlenecks(days = 30) {
  const response = await fetch(`${API_BASE}/doc-analytics/bottlenecks?days=${days}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Default export — all functions grouped on one object
// =============================================================================

export const docAnalyticsAPI = {
  getDashboard,
  getPipelineCompleteness,
  getSlaCompliance,
  getAiPerformance,
  getFollowupEffectiveness,
  getIncomeSummary,
  getBankAnalysisSummary,
  getEsignMetrics,
  getProcessorProductivity,
  getLoanTimeline,
  getTrends,
  getBottlenecks,
};

export default docAnalyticsAPI;
