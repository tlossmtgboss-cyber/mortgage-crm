/**
 * API module -- backward-compatible re-export.
 *
 * This file ensures that `import api from '../services/api'` and
 * `import { leadsAPI, loansAPI, ... } from '../services/api'` continue
 * to work after the decomposition.
 *
 * The actual api instance, interceptors, and all endpoint objects remain
 * in the original `../api.js` file which is still the canonical source.
 * This index exists so that if the import path resolves to `api/index.ts`
 * (directory import), it re-exports everything from the parent `api.js`.
 */

// Re-export everything from the original monolith file.
// The original api.js continues to be the single source of truth for all
// endpoint objects (leadsAPI, loansAPI, etc.) until they are individually
// migrated into this directory.
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
} from '../api.js';
