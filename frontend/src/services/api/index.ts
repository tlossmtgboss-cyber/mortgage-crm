/**
 * API module -- backward-compatible re-export facade.
 *
 * This file ensures that `import api from '../services/api'` and
 * `import { leadsAPI, loansAPI, ... } from '../services/api'` continue
 * to work after the decomposition.
 *
 * Domain-specific modules are available for targeted imports:
 *   import { calendarAPI } from '../services/api/calendar';
 *   import { aiAPI } from '../services/api/ai';
 *   import { leadsAPI } from '../services/api/leads';
 */

// Re-export everything from the barrel file (../api.js).
// The barrel in turn re-exports from the domain modules in this directory.
export {
  default,
  API_BASE_URL,
  apiRequest,
  attemptTokenRefresh,
  authAPI,
  dashboardAPI,
  leadsAPI,
  loansAPI,
  tasksAPI,
  partnersAPI,
  mumAPI,
  mumPortalAPI,
  activitiesAPI,
  analyticsAPI,
  aiAPI,
  conversationsAPI,
  portfolioAPI,
  calendarAPI,
  crmCalendarAPI,
  unifiedCalendarAPI,
  schedulerAPI,
  calendarAnalyticsAPI,
  calendarLabelsAPI,
  teamCalendarAPI,
  calendarSettingsAPI,
  processTemplatesAPI,
  onboardingAPI,
  teamAPI,
  dialerAPI,
  voiceAPI,
  voicemailAPI,
  aiReceptionistDashboardAPI,
  permissionsAPI,
  impersonationAPI,
  accessAuditAPI,
  auditAPI,
  permissionsApi,
  notificationsApi,
  certificationsApi,
  complianceApi,
  circleOfCashflowAPI,
  profitabilityAPI,
  financialIntelligenceAPI,
  emailSignatureAPI,
  emailDropAPI,
  commandCenterAPI,
  reconciliationAPI,
  documentDropAPI,
  borrowerApplicationAPI,
  publicApplicationAPI,
  coborrowerAPI,
  prequalifyAPI,
  agentAPI,
  agentGymAPI,
  agentChatAPI,
  purlAPI,
  perenniaDocsAPI,
  outreachAPI,
  incomeAPI,
  salesforceAPI,
  rateMonitorAPI,
  rateSheetAPI,
  callMonitoringAPI,
  emailDraftsAPI,
  agentMetricsAPI,
  isOffline,
  isApiError,
  builderApplicationsAPI,
  guidelinesAPI,
} from '../api.js';

// Re-export infrastructure utilities for targeted imports
export type { ApiError, OfflineCacheEntry, ApiRequestOptions } from './types';
export { buildApiError, SAFE_ERROR_MESSAGES, isApiError as isApiErrorGuard } from './errors';
export { isOffline as checkOffline } from './errors';
export { cacheSet, cacheGet, dispatchMutationDebounced } from './offline';
export { attachInterceptors } from './interceptors';
