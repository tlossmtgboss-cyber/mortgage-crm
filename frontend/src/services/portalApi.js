/**
 * Portal API Service
 *
 * Handles all API calls to the Perennia Portal backend endpoints.
 */

import { API_BASE_URL } from './api';
import { getToken } from '../utils/tokenStore';

const API_BASE = API_BASE_URL;

/**
 * Make an authenticated API request
 */
async function apiRequest(endpoint, options = {}) {
  const token = getToken();

  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    },
    ...options,
  };

  const response = await fetch(`${API_BASE}${endpoint}`, config);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'An error occurred' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

// =============================================================================
// LIFECYCLE ENDPOINTS
// =============================================================================

export const lifecycleApi = {
  /**
   * Get portal status for a loan
   */
  getPortalStatus: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/status`),

  /**
   * Get current lifecycle stage
   */
  getLifecycleStage: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/lifecycle`),

  /**
   * Transition to a new lifecycle stage
   */
  transitionStage: (loanId, newStage, reason = null, force = false) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/lifecycle/transition`, {
      method: 'POST',
      body: JSON.stringify({ new_stage: newStage, reason, force }),
    }),

  /**
   * Get lifecycle history
   */
  getLifecycleHistory: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/lifecycle/history`),

  /**
   * Get valid transitions
   */
  getValidTransitions: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/lifecycle/valid-transitions`),

  /**
   * Record heartbeat activity
   */
  recordHeartbeat: (loanId, activityType, description, metadata = null) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/heartbeat`, {
      method: 'POST',
      body: JSON.stringify({
        activity_type: activityType,
        description,
        metadata,
        is_visible_to_borrower: true,
      }),
    }),

  /**
   * Get recent activity
   */
  getRecentActivity: (loanId, limit = 20, borrowerVisibleOnly = false) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/activity?limit=${limit}&borrower_visible_only=${borrowerVisibleOnly}`),

  /**
   * Get active risks
   */
  getActiveRisks: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/risks`),

  /**
   * Add risk flag
   */
  addRiskFlag: (loanId, riskType, severity, description, recommendedAction = null) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/risks`, {
      method: 'POST',
      body: JSON.stringify({
        risk_type: riskType,
        severity,
        description,
        recommended_action: recommendedAction,
      }),
    }),

  /**
   * Resolve risk flag
   */
  resolveRiskFlag: (flagId, resolutionNotes = null) =>
    apiRequest(`/api/v1/portal/risks/${flagId}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ resolution_notes: resolutionNotes }),
    }),
};

// =============================================================================
// MILESTONE ENDPOINTS
// =============================================================================

export const milestoneApi = {
  /**
   * Get loan milestones
   */
  getLoanMilestones: (loanId, includeTasks = true, borrowerView = false) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/milestones?include_tasks=${includeTasks}&borrower_view=${borrowerView}`),

  /**
   * Get milestone progress
   */
  getMilestoneProgress: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/milestones/progress`),

  /**
   * Generate milestones for a loan
   */
  generateMilestones: (loanId, stage, expectedCloseDate = null) => {
    let url = `/api/v1/portal/loans/${loanId}/milestones/generate?stage=${stage}`;
    if (expectedCloseDate) {
      url += `&expected_close_date=${expectedCloseDate}`;
    }
    return apiRequest(url, { method: 'POST' });
  },

  /**
   * Update milestone status
   */
  updateMilestone: (milestoneId, status, notes = null) =>
    apiRequest(`/api/v1/portal/milestones/${milestoneId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status, notes }),
    }),

  /**
   * Get timeline data
   */
  getTimelineData: (loanId, viewType = 'horizontal', borrowerView = false) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/milestones/timeline?view_type=${viewType}&borrower_view=${borrowerView}`),

  /**
   * Get journey summary
   */
  getJourneySummary: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/milestones/summary`),

  /**
   * Get task details
   */
  getTaskDetails: (taskId) =>
    apiRequest(`/api/v1/portal/tasks/${taskId}`),

  /**
   * Update task status
   */
  updateTask: (taskId, status, metadata = null) =>
    apiRequest(`/api/v1/portal/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status, metadata }),
    }),

  /**
   * Get pending borrower tasks
   */
  getBorrowerTasks: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/tasks/borrower`),
};

// =============================================================================
// CLOSE-ON-TIME ENDPOINTS
// =============================================================================

export const closeOnTimeApi = {
  /**
   * Create close schedule
   */
  createCloseSchedule: (loanId, targetCloseDate, contractDate = null) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/close-schedule`, {
      method: 'POST',
      body: JSON.stringify({
        target_close_date: targetCloseDate,
        contract_date: contractDate,
      }),
    }),

  /**
   * Get close schedule
   */
  getCloseSchedule: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/close-schedule`),

  /**
   * Get countdown data
   */
  getCountdownData: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/close-countdown`),

  /**
   * Get calendar view
   */
  getCalendarView: (loanId, startDate = null, weeks = 6) => {
    let url = `/api/v1/portal/loans/${loanId}/close-calendar?weeks=${weeks}`;
    if (startDate) {
      url += `&start_date=${startDate}`;
    }
    return apiRequest(url);
  },

  /**
   * Complete close milestone
   */
  completeCloseMilestone: (milestoneId) =>
    apiRequest(`/api/v1/portal/close-milestones/${milestoneId}/complete`, {
      method: 'POST',
    }),

  /**
   * Get federal holidays
   */
  getFederalHolidays: (year) =>
    apiRequest(`/api/v1/portal/holidays/${year}`),

  /**
   * Count business days
   */
  countBusinessDays: (startDate, endDate) =>
    apiRequest(`/api/v1/portal/business-days/count?start_date=${startDate}&end_date=${endDate}`),
};

// =============================================================================
// HOME VALUE ENDPOINTS
// =============================================================================

export const homeValueApi = {
  /**
   * Set property baseline
   */
  setPropertyBaseline: (loanId, baselineData) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/property-baseline`, {
      method: 'POST',
      body: JSON.stringify(baselineData),
    }),

  /**
   * Get property baseline
   */
  getPropertyBaseline: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/property-baseline`),

  /**
   * Get current home value
   */
  getCurrentHomeValue: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/home-value`),

  /**
   * Get home value dashboard
   */
  getHomeValueDashboard: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/home-value/dashboard`),

  /**
   * Calculate equity
   */
  calculateEquity: (loanId, currentLoanBalance) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/equity?current_loan_balance=${currentLoanBalance}`),

  /**
   * Calculate equity unlock potential
   */
  calculateEquityUnlock: (loanId, currentLoanBalance, maxLtv = 0.80) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/equity-unlock?current_loan_balance=${currentLoanBalance}&max_ltv=${maxLtv}`),

  /**
   * Get home value insights
   */
  getHomeValueInsights: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/home-value/insights`),

  /**
   * Generate insights
   */
  generateInsights: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/home-value/generate-insights`, {
      method: 'POST',
    }),

  /**
   * Dismiss insight
   */
  dismissInsight: (insightId) =>
    apiRequest(`/api/v1/portal/insights/${insightId}/dismiss`, {
      method: 'POST',
    }),
};

// =============================================================================
// DOCUMENT ENDPOINTS
// =============================================================================

export const documentApi = {
  /**
   * Get loan documents
   */
  getLoanDocuments: (loanId, documentType = null, status = null, borrowerView = false) => {
    let url = `/api/v1/portal/loans/${loanId}/documents?borrower_view=${borrowerView}`;
    if (documentType) url += `&document_type=${documentType}`;
    if (status) url += `&status=${status}`;
    return apiRequest(url);
  },

  /**
   * Get document details
   */
  getDocument: (documentId) =>
    apiRequest(`/api/v1/portal/documents/${documentId}`),

  /**
   * Update document status
   */
  updateDocumentStatus: (documentId, status, rejectionReason = null) =>
    apiRequest(`/api/v1/portal/documents/${documentId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, rejection_reason: rejectionReason }),
    }),

  /**
   * Get document extraction
   */
  getDocumentExtraction: (documentId) =>
    apiRequest(`/api/v1/portal/documents/${documentId}/extraction`),

  /**
   * Get document checklist
   */
  getDocumentChecklist: (loanId, lifecycleStage) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/documents/checklist?lifecycle_stage=${lifecycleStage}`),

  /**
   * Get document summary
   */
  getDocumentSummary: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/documents/summary`),

  /**
   * Set property costs
   */
  setPropertyCosts: (loanId, costs) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/property-costs`, {
      method: 'POST',
      body: JSON.stringify(costs),
    }),

  /**
   * Get property costs
   */
  getPropertyCosts: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/property-costs`),
};

// =============================================================================
// NOTIFICATION ENDPOINTS
// =============================================================================

export const notificationApi = {
  /**
   * Queue a notification
   */
  queueNotification: (loanId, eventType, recipientEmail, context = {}, channel = 'email') =>
    apiRequest(`/api/v1/portal/loans/${loanId}/notifications/queue`, {
      method: 'POST',
      body: JSON.stringify({
        event_type: eventType,
        recipient_email: recipientEmail,
        context,
        channel,
      }),
    }),

  /**
   * Get notification history
   */
  getNotificationHistory: (loanId, limit = 50) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/notifications/history?limit=${limit}`),

  /**
   * Get notification templates
   */
  getNotificationTemplates: (eventType = null, channel = null) => {
    let url = '/api/v1/portal/notifications/templates';
    const params = [];
    if (eventType) params.push(`event_type=${eventType}`);
    if (channel) params.push(`channel=${channel}`);
    if (params.length) url += `?${params.join('&')}`;
    return apiRequest(url);
  },
};

// =============================================================================
// BORROWER PORTAL ENDPOINTS
// =============================================================================

export const borrowerPortalApi = {
  /**
   * Get portal by access token (magic link)
   */
  getPortalByToken: (token) =>
    apiRequest(`/api/v1/portal/access/${token}`),

  /**
   * Get dashboard data by loan ID
   */
  getDashboard: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/status`),

  /**
   * Get borrower dashboard
   */
  getBorrowerDashboard: (loanId) =>
    apiRequest(`/api/v1/portal/borrower/${loanId}/dashboard`),

  /**
   * Get MUM dashboard
   */
  getMumDashboard: (loanId) =>
    apiRequest(`/api/v1/portal/borrower/${loanId}/mum-dashboard`),

  /**
   * Get recent activity
   */
  getRecentActivity: (loanId, limit = 20, borrowerVisibleOnly = false) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/activity?limit=${limit}&borrower_visible_only=${borrowerVisibleOnly}`),
};

// =============================================================================
// PARTNER PORTAL ENDPOINTS
// =============================================================================

export const partnerPortalApi = {
  /**
   * Get partner portal data by access token
   */
  getPortalByToken: (accessToken) =>
    apiRequest(`/api/v1/portal/partner/${accessToken}`),

  /**
   * Get partner portal data (alias for compatibility)
   */
  getPartnerPortalData: (accessToken) =>
    apiRequest(`/api/v1/portal/partner/${accessToken}`),

  /**
   * Get filtered milestones for partner view
   */
  getPartnerMilestones: (accessToken) =>
    apiRequest(`/api/v1/portal/partner/${accessToken}/milestones`),

  /**
   * Get critical dates visible to partners
   */
  getCriticalDates: (accessToken) =>
    apiRequest(`/api/v1/portal/partner/${accessToken}/critical-dates`),

  /**
   * Get risk flags visible to partners
   */
  getRiskFlags: (accessToken) =>
    apiRequest(`/api/v1/portal/partner/${accessToken}/risk-flags`),
};

// =============================================================================
// ACTIVE LOAN PORTAL ENDPOINTS
// =============================================================================

export const activeLoanPortalApi = {
  /**
   * Get complete loan portal data
   */
  getPortalData: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/complete`),

  /**
   * Get portal by access token
   */
  getPortalByToken: (token) =>
    apiRequest(`/api/v1/portal/access/${token}`),

  /**
   * Get Close On Time milestones for arrow timeline
   */
  getCloseOnTimeMilestones: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/close-on-time/milestones`),

  /**
   * Get document summary for portal
   */
  getDocumentSummary: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/documents/summary`),

  /**
   * Get pending tasks for borrower
   */
  getPendingTasks: (loanId) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/tasks/borrower`),

  /**
   * Get recent activity
   */
  getRecentActivity: (loanId, limit = 20) =>
    apiRequest(`/api/v1/portal/loans/${loanId}/activity?limit=${limit}`),
};

// Export all APIs as default
export default {
  lifecycle: lifecycleApi,
  milestone: milestoneApi,
  closeOnTime: closeOnTimeApi,
  homeValue: homeValueApi,
  document: documentApi,
  notification: notificationApi,
  borrowerPortal: borrowerPortalApi,
  partnerPortal: partnerPortalApi,
  activeLoanPortal: activeLoanPortalApi,
};
