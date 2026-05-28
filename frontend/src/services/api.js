/**
 * API barrel file — re-exports all domain modules for backward compatibility.
 *
 * Existing imports like:
 *   import api, { leadsAPI, loansAPI } from '../services/api';
 *   import { API_BASE_URL } from '../services/api';
 *
 * continue to work unchanged. For targeted imports, use domain modules directly:
 *   import { leadsAPI } from '../services/api/leads';
 *   import { calendarAPI } from '../services/api/calendar';
 */

// ---- Shared infrastructure ----
export { default, API_BASE_URL, apiRequest, attemptTokenRefresh, isOffline, isApiError } from './api/client.js';

// ---- Auth ----
export { authAPI } from './api/auth.js';

// ---- Core CRM ----
export { leadsAPI } from './api/leads.js';
export { loansAPI } from './api/loans.js';
export { tasksAPI, activitiesAPI } from './api/tasks.js';

// ---- Pipeline / Dashboard / Analytics ----
export { dashboardAPI, analyticsAPI, portfolioAPI } from './api/pipeline.js';

// ---- AI / Agents ----
export { aiAPI, conversationsAPI, agentAPI, agentGymAPI, agentChatAPI, agentMetricsAPI } from './api/ai.js';

// ---- Telephony / Voice / Outreach ----
export {
  dialerAPI,
  voiceAPI,
  voicemailAPI,
  aiReceptionistDashboardAPI,
  outreachAPI,
  callMonitoringAPI,
} from './api/telephony.js';

// ---- Calendar / Scheduler ----
export {
  calendarAPI,
  crmCalendarAPI,
  unifiedCalendarAPI,
  schedulerAPI,
  calendarAnalyticsAPI,
  calendarLabelsAPI,
  teamCalendarAPI,
  calendarSettingsAPI,
} from './api/calendar.js';

// ---- Documents ----
export { emailDropAPI, documentDropAPI, perenniaDocsAPI } from './api/documents.js';

// ---- Admin / Team / Permissions / Compliance ----
export {
  teamAPI,
  permissionsAPI,
  impersonationAPI,
  accessAuditAPI,
  auditAPI,
  permissionsApi,
  notificationsApi,
  certificationsApi,
  complianceApi,
  processTemplatesAPI,
  onboardingAPI,
} from './api/admin.js';

// ---- Misc domains ----
export {
  partnersAPI,
  mumAPI,
  mumPortalAPI,
  circleOfCashflowAPI,
  profitabilityAPI,
  financialIntelligenceAPI,
  emailSignatureAPI,
  commandCenterAPI,
  reconciliationAPI,
  borrowerApplicationAPI,
  publicApplicationAPI,
  coborrowerAPI,
  prequalifyAPI,
  purlAPI,
  incomeAPI,
  salesforceAPI,
  rateMonitorAPI,
  rateSheetAPI,
  emailDraftsAPI,
  builderApplicationsAPI,
  guidelinesAPI,
} from './api/misc.js';
