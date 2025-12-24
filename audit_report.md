# Perennia AI - Comprehensive Code Quality Audit Report
**Generated**: 2025-12-24 13:10:05
**Files Scanned**: 367

---

## Executive Summary

**Overall Score**: 58.81/100

| Metric | Count |
|--------|-------|
| Total Issues | 2195 |
| Critical | 479 |
| High | 513 |
| Medium | 1196 |
| Low | 7 |

**Grade**: F (Failing)

**NOT READY** - Critical quality issues. Do not deploy.

---

## CRITICAL ISSUES (Must Fix Immediately)

These issues will cause production failures and must be fixed before deployment:

### services/api.js (309 critical)

**Line 195**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  update: async (id, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 199**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  delete: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 206**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAll: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 210**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getUnified: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 214**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getById: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 218**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  create: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 222**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  update: async (id, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 226**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  delete: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 229**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  delegate: async (id, delegateToId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 237**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAll: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 241**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getById: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 245**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getReferrals: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 249**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  create: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 253**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  update: async (id, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 257**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  delete: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 264**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAll: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 268**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getMetrics: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 272**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getById: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 276**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  create: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 280**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  update: async (id, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 284**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  delete: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 291**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAll: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 295**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  create: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 299**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  delete: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 306**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getConversionFunnel: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 310**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getPipeline: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 479**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  executeAction: async (actionId, modifications = {}, sessionId = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 487**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  parseScreenshot: async (imageFile) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 497**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createLeadFromScreenshot: async (leadData) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 501**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  submitTrainingInstruction: async (instruction, taskContext = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 509**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  submitFeedback: async (feedbackData) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 513**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getFeedbackLogs: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 517**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getFeedbackStats: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 521**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateFeedback: async (feedbackId, updateData) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 525**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  deleteFeedback: async (feedbackId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 532**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAll: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 536**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  create: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 544**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAll: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 548**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getStats: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 556**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAll: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 560**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getById: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 564**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  create: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 568**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  update: async (id, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 572**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  delete: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 579**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAppointments: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 583**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAppointmentById: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 587**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createAppointment: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 591**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateAppointment: async (id, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 595**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  cancelAppointment: async (id, reason) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 603**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAll: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 607**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getByRole: async (roleName) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 611**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getRoles: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 615**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  create: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 619**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  update: async (id, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 623**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  delete: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 626**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  analyzeEfficiency: async (roleName = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 633**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  seedDefaults: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 641**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  parseDocumentsUpload: async (files) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 655**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  parseDocuments: async (documentContent, documentName = null, documentType = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 663**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getRoles: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 667**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getMilestones: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 671**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getTasks: async (roleId = null, milestoneId = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 681**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateTask: async (taskId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 685**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  bulkUpdateTasks: async (tasks) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 689**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createTask: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 693**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getProgress: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 697**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateProgress: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 701**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  complete: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 709**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getMembers: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 713**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getWorkflowMembers: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 717**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getMemberDetail: async (userId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 721**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createMember: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 725**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateMember: async (memberId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 729**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  deleteMember: async (memberId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 737**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  clickToDial: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 742**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getSettings: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 747**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateSettings: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 752**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getCallLogs: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 760**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  makeCall: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 764**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getCallHistory: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 768**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getCallStats: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 772**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getConfig: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 776**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateConfig: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 780**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  dropVoicemail: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 789**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  drop: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 795**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  transcribe: async (formData) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 805**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getTemplates: async (category = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 812**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createTemplate: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 818**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getHistory: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 824**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAnalytics: async (startDate = null, endDate = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 836**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getActivityFeed: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 840**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getActivityCount: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 846**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getDailyMetrics: async (startDate, endDate) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 852**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getRealtimeMetrics: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 858**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getSkills: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 862**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getSkillDetail: async (skillName) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 868**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getROI: async (startDate = null, endDate = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 877**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getErrors: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 881**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  approveErrorFix: async (errorId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 887**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getSystemHealth: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 891**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getComponentHealth: async (componentName) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 897**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getConversations: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 901**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getConversationDetail: async (conversationId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 909**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getUserPermissions: async (userId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 913**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getUserTemplate: async (userId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 917**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAvailablePermissions: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 921**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  applyTemplate: async (userId, templateName) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 927**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updatePermissions: async (userId, permissions) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 937**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  start: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 941**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  end: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 945**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getCurrent: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 953**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAuditLog: async (userId, startDate = null, endDate = null, changeType = null, search = null, limit = 50, offset = 0) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 962**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getImpersonationHistory: async (userId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 966**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getActiveSessions: async (userId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 970**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  revokeSession: async (userId, sessionId, reason = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 976**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  revokeAllSessions: async (userId, reason) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 982**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  emergencyRevoke: async (userId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 994**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getUserPermissions: async (userId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1000**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAvailablePermissions: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1006**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getMyPermissionRequests: async (status = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1013**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createPermissionRequest: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1019**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  approvePermissionRequest: async (requestId, notes = '') => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1025**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  denyPermissionRequest: async (requestId, reason) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1034**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getNotifications: async (unreadOnly = false, limit = 50) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1041**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  markAsRead: async (notificationId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1047**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  markAllAsRead: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1056**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getDueCertifications: async (status = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1063**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getCertificationDetails: async (certId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1069**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  certifyAccess: async (certId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1075**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  skipCertification: async (certId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1081**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getCertificationHistory: async (userId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1090**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getOverview: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1096**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getCertificationsByDepartment: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1102**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  exportReport: async (format = 'csv') => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1114**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getOpportunities: async (contactId = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1119**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  acknowledgeOpportunity: async (opportunityId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1123**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  suggestPartner: async (opportunityId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1127**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  sendIntroduction: async (opportunityId, partnerId, method = 'email') => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1133**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getPartners: async (category = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1140**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getReferrals: async (contactId = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1145**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createReferral: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1151**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  submitQuestionnaire: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1155**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getQuestionnaire: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1164**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getDashboard: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1169**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getMetrics: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1174**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getTrends: async (months = 12) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1180**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getExpenses: async (filters = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1184**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createExpense: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1188**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateExpense: async (id, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1192**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  deleteExpense: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1196**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getExpenseCategories: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1202**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getRoles: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1206**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createRole: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1210**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getRoleProfitability: async (roleId, month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1217**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getEmployees: async (filters = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1221**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createEmployee: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1225**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateEmployee: async (id, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1229**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getEmployeePerformance: async (id, month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1236**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getLoans: async (filters = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1240**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createLoan: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1244**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  addLoanAttribution: async (loanId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1250**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getRevenue: async (filters = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1254**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createRevenue: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1260**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getScenarios: async (savedOnly = false) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1264**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createScenario: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1268**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  runScenario: async (baseMonth, parameters) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1274**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  saveScenario: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1280**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getSnapshots: async (limit = 12) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1284**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createSnapshot: async (month) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1290**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getInsights: async (filters = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1294**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  generateInsights: async (month) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1298**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  acknowledgeInsight: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1304**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getGapsAndGains: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1309**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getBreakEvenAnalysis: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1316**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  queryAI: async (question, month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1320**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAIRecommendations: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1325**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  analyzeHiring: async (roleName, salary, month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1333**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getExecutiveDigest: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1338**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAnomalies: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1343**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  compareScenarios: async (scenarios, month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1350**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getQuickInsights: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1355**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getSuggestedQuestions: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1363**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getExecutiveDashboard: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1368**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getGainOnSale: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1373**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getHedgeAnalysis: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1377**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getProductProfitability: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1382**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getCostPerLoan: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1387**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getCashRunway: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1391**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getBreakEven: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1396**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getWarehouseEfficiency: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1400**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getRateExposure: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1404**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getMSRStatus: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1408**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getPricingAnalysis: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1412**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getCashForecast: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1416**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getLiquidity: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1420**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getCapital: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1424**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getComplianceRisks: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1428**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getTechROI: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1433**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getOperationalLosses: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1437**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getInvestmentRecommendations: async (month = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1446**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  get: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1450**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  save: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1454**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  uploadImage: async (file, imageType) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1463**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getHtml: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1467**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getPreview: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1476**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  parse: async (emailData) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1496**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  process: async (action, emailData, extractedFields, targetEntityId, targetEntityType, createNew, userAnswers) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1521**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  searchMatches: async (searchTerm, email, loanNumber) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1531**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  health: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1541**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAll: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1549**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getPending: async (status = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1556**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  delete: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1561**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  approve: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1567**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  reject: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1576**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  upload: async (file, borrowerId, loanId, docType) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1590**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  classify: async (file) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1601**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getDocuments: async (borrowerId, loanId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1614**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  create: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1620**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAll: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1626**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getById: async (id) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1632**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAnalytics: async (days = 30) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1638**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createForLead: async (leadId, options = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1650**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  get: async (token) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1656**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  update: async (token, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1662**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  saveStep: async (token, step, data, markCompleted = false) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1672**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  prequalify: async (token, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1678**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  captureCreditAuth: async (token, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1684**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  submit: async (token) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1690**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  uploadDocument: async (token, file, category, description) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1703**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getDocuments: async (token) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1709**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  deleteDocument: async (token, docId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1715**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createCoborrowerInvitation: async (token, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1724**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getInvitation: async (invitationToken) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1730**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  saveData: async (invitationToken, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1736**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  submit: async (invitationToken) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1742**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  captureCreditAuth: async (invitationToken, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1750**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  calculate: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1759**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAgents: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1763**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAgent: async (agentId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1767**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createAgent: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1771**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateAgent: async (agentId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1775**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  deleteAgent: async (agentId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1779**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateAgentStatus: async (agentId, status, reason = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1783**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAgentHealth: async (agentId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1789**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAgentTypes: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1795**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getExecutions: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1799**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAgentExecutions: async (agentId, params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1803**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getExecution: async (executionId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1809**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAgentMetrics: async (agentId, params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1813**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAggregatedMetrics: async (agentId, params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1819**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAlerts: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1823**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  acknowledgeAlert: async (alertId, userId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1829**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  resolveAlert: async (alertId, userId, notes = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1837**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getDashboard: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1841**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getSystemHealth: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1845**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getHealthSummary: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1849**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getStatistics: async (days = 30) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1855**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  bulkPauseAgents: async (agentIds, reason = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1859**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  bulkActivateAgents: async (agentIds) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1865**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  seedDefaultAgents: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1871**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getSettings: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1875**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateSettings: async (settings) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1881**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getDashboardSummary: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1885**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getProfiles: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1894**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getScenarios: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1898**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getScenario: async (scenarioId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1902**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createScenario: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1906**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateScenario: async (scenarioId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1910**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  deleteScenario: async (scenarioId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1914**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getScenarioStats: async (scenarioId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1920**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  startSession: async (scenarioId, agentId, initiatedBy = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1927**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  completeSession: async (sessionId, results, score, passed, feedback = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1936**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  failSession: async (sessionId, error) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1940**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getSessions: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1944**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getSession: async (sessionId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1950**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  assessAgentSkills: async (agentId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1954**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getRecommendedScenarios: async (agentId, limit = 5) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1960**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  benchmarkAgent: async (agentId, scenarioIds = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1965**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getLeaderboard: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1971**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  generateScenarioFromExecution: async (executionId, difficulty = 'intermediate') => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2130**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getWorkspace: async (workspaceId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2136**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getPurlUrl: async (workspaceId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2142**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createToken: async (workspaceId, data = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2148**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  resendInvite: async (workspaceId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2154**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  listWorkspaces: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2160**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getMetrics: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2169**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getTemplatePacks: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2174**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getTemplatePack: async (packId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2179**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createTemplatePack: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2184**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateTemplatePack: async (packId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2189**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  deleteTemplatePack: async (packId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2194**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getReviewQueue: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2199**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  approveDocuments: async (documentIds) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2206**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  rejectDocuments: async (documentIds, reason) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2214**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  requestDocumentInfo: async (documentId, message) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2222**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getActivityFeed: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2228**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getLoanDocumentRequirements: async (loanId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2233**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  updateLoanDocumentRequirements: async (loanId, documentType, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2242**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  uploadDocument: async (loanId, documentType, file, onProgress) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2268**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getDocumentUrl: async (documentId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2274**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getPortalNotifications: async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2279**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  markNotificationRead: async (notificationId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2284**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  markAllNotificationsRead: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2290**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  sendDocumentReminder: async (loanId, documentTypes = []) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2301**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  sendSMS: async (to, message, leadId = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2311**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  sendEmail: async (to, subject, body, leadId = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2322**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  requestCall: async (phoneNumber, leadId = null, notes = '') => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2332**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  sendVoicemail: async (to, templateId = 'default', leadId = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 2342**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  logActivity: async (leadId, channel, direction, content, outcome = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### services/permissionsService.ts (35 critical)

**Line 209**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getStages(): Promise<LoanStageDefinition[]> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 217**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getEnabledStages(): Promise<LoanStage[]> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 225**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function checkStageAccess(userId: number, stageCode: LoanStage): Promise<boolean> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 237**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getPermissionDefinitions(): Promise<PermissionDefinition[]> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 245**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getGroupedPermissions(): Promise<GroupedPermissions[]> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 253**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getStagePermissions(stageCode: LoanStage): Promise<PermissionDefinition[]> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 265**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getTemplates(): Promise<PermissionTemplate[]> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 273**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getStageTemplates(stageCode: LoanStage): Promise<PermissionTemplate[]> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 281**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getTemplateByCode(code: string): Promise<PermissionTemplate> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 289**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function createTemplate(template: Partial<PermissionTemplate>): Promise<PermissionTemplate> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 297**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function updateTemplate(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 312**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getUserPermissionProfile(userId: number): Promise<UserPermissionProfile> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 320**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getUserStageAccess(userId: number): Promise<UserStageAccess[]> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 328**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function grantStageAccess(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 348**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function revokeStageAccess(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 361**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function applyTemplate(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 378**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function updateDataScope(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 396**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getUserOverrides(userId: number): Promise<PermissionOverride[]> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 404**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function addOverride(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 426**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function removeOverride(userId: number, permissionKey: string): Promise<void> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 437**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function checkPermission(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 450**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function checkAnyPermission(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 463**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function checkAllPermissions(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 476**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getEffectivePermissions(userId: number): Promise<Record<string, boolean>> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 488**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function createPermissionRequest(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 508**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getMyRequests(status?: RequestStatus): Promise<PermissionRequest[]> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 517**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getPendingRequests(): Promise<PermissionRequest[]> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 525**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function approveRequest(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 536**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function denyRequest(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 547**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function requestMoreInfo(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 558**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function cancelRequest(requestId: number): Promise<void> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 569**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getSubscriptionTiers(): Promise<SubscriptionTier[]> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 577**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getCurrentSubscription(): Promise<OrganizationSubscription> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 585**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function updateSubscriptionStages(stages: LoanStage[]): Promise<OrganizationSubscription> {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 597**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getPermissionAuditLog(
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### services/smartDocsApi.js (26 critical)

**Line 13**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
async function handleResponse(response) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 39**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function generateNeedsList(params) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 51**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getNeedsList(loanId) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 61**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function addCustomRequest(loanId, borrowerId, data) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 76**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function waiveRequest(requestId, reason, waivedBy) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 92**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function uploadDocument(file, loanId, borrowerId, requestId = null, docType = null) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 114**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getDocument(documentId) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 124**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getLoanDocuments(loanId, status = null) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 135**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function manualReview(documentId, decision, reviewer, notes = null) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 151**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getExpiringDocuments(loanId = null, daysAhead = 14) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 164**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function runExpirationCheck() {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 175**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function processRenewals() {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 190**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function inferPayrollFrequency(borrowerId) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 201**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function updatePayrollFrequency(loanId, borrowerId, frequency) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 217**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getTemplates(activeOnly = true) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 227**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getTemplate(templateId) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 241**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getLoanEvents(loanId, limit = 50) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 255**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getApplicantsPendingReview(page = 1, limit = 20) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 265**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getApplicantsOutstandingDocs(page = 1, limit = 20, overdueOnly = false) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 278**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getDashboardSummary() {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 292**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getQueue(page = 1, limit = 20, slaStatus = null, search = null) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 306**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getQueueSummary() {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 316**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getQueueDetail(loanId) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 330**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function getReminderSettings(loanId) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 340**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function updateReminderSettings(loanId, settings) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 352**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export async function sendReminder(loanId) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### services/blogApi.js (26 critical)

**Line 52**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getVoiceProfiles = async (activeOnly = true) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 59**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const createVoiceProfile = async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 64**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const updateVoiceProfile = async (profileId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 69**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const deleteVoiceProfile = async (profileId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 76**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getComplianceProfiles = async (activeOnly = true) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 83**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const createComplianceProfile = async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 90**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getSourceDocuments = async (processedOnly = false) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 97**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const uploadSourceDocument = async (file, title, author, rightsAttestation) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 110**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getSourceDocument = async (docId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 117**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getCampaigns = async (activeOnly = true) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 124**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const createCampaign = async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 131**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const generateContent = async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 136**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getContentList = async (params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 141**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getContent = async (contentId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 146**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const updateContent = async (contentId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 151**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const deleteContent = async (contentId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 158**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const mineTopics = async (sourceDocumentId, count = 10, campaignId = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 167**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getTopics = async (campaignId = null, used = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 176**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const checkCompliance = async (content, complianceProfileId = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 186**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const checkSimilarity = async (content, sourceDocumentId = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 198**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getUserSettings = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 203**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const updateUserSettings = async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 210**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getTrendingTopics = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 217**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getAnalyticsOverview = async (days = 30) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 224**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getContentPerformance = async (contentId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 231**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getStatus = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### services/conversationIntelligenceApi.js (25 critical)

**Line 27**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  create: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 35**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  get: async (recordingId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 43**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  list: async (filters = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 60**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  uploadAudio: async (recordingId, file) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 85**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  transcribe: async (recordingId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 93**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  get: async (recordingId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 101**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  waitForCompletion: async (recordingId, maxAttempts = 60, intervalMs = 2000) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 121**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  analyze: async (recordingId, data = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 129**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  get: async (recordingId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 137**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  waitForCompletion: async (recordingId, maxAttempts = 60, intervalMs = 2000) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 157**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createScorecard: async (recordingId, data = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 165**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getScorecards: async (recordingId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 173**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  listRubrics: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 187**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createSession: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 195**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  endSession: async (sessionId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 232**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createClip: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 240**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  listClips: async (filters = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 254**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  createAssignment: async (data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 262**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  listAssignments: async (filters = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 275**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  completeAssignment: async (assignmentId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 289**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getTeamDashboard: async (filters = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 302**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getAgentDashboard: async (agentId, filters = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 316**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  getComplianceDashboard: async (filters = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 334**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  exportRecordings: async (format = 'csv', filters = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 375**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  check: async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### services/onboardingApi.js (22 critical)

**Line 16**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const startOnboarding = async (inviteToken = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 35**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const resumeOnboarding = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 56**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const autoSaveStep = async (stepNumber, stepData) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 78**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const saveStepData = async (stepNumber, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 97**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const completeStep = async (stepNumber) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 114**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const completeOnboarding = async (inviteToken = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 136**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const validateInviteToken = async (token) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 161**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const acceptInvite = async (token, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 180**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const createInvite = async (inviteData) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 199**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const checkEmailAvailability = async (email) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 215**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const listInvites = async (status = null) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 234**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const listPendingInvites = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 242**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const revokeInvite = async (inviteId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 258**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getOnboardingOptions = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 274**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getRolePermissionsPreview = async (role) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 292**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const sendEmailVerification = async (email) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 312**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const verifyEmailCode = async (email, code) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 331**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const sendPhoneVerification = async (phone) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 351**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const verifyPhoneCode = async (phone, code) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 371**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getAvailableQuickActions = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 388**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getUserPagePermissions = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 404**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const updateAIPreferences = async (preferences) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### services/responsibilitiesApi.js (14 critical)

**Line 13**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
const handleResponse = async (response) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 25**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const fetchResponsibilities = async (userId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 33**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const fetchArchivedResponsibilities = async (userId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 41**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const createResponsibility = async (userId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 50**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const updateResponsibility = async (userId, respId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 59**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const archiveResponsibility = async (userId, respId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 67**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const restoreResponsibility = async (userId, respId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 75**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const reorderResponsibilities = async (userId, orderedIds) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 88**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const fetchSkillsLibrary = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 96**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const addSkillToLibrary = async (skillData) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 109**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getUserSkills = async (userId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 117**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const addUserSkill = async (userId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 126**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const assessSkill = async (userId, skillId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 135**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const removeUserSkill = async (userId, skillId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### services/goalsApi.js (8 critical)

**Line 13**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
const handleResponse = async (response) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 25**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const getUserGoals = async (userId, params = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 39**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const createGoal = async (userId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 48**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const updateGoal = async (userId, goalId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 57**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const deleteGoal = async (userId, goalId) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 69**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const updateKeyResult = async (userId, goalId, krId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 82**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const employeeSelfAssess = async (userId, goalId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 91**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
export const managerAssess = async (userId, goalId, data) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### pages/ReconciliationCenter.js (3 critical)

**Line 1167**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  const bulkDeleteReviewItems = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1186**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  const bulkApproveReviewItems = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 1210**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  const bulkBlockSenders = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### pages/UserProfileSettings.js (2 critical)

**Line 150**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
      const response = await saveProfile(async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

**Line 350**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
      const response = await uploadPhoto(async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### hooks/useRealtorPortal.js (1 critical)

**Line 25**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
async function realtorApi(endpoint, options = {}) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### hooks/useAsyncOperation.js (1 critical)

**Line 143**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
 *     onSubmit: async (data) => apiClient.post('/api/users', data),
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### pages/AgentGovernanceSettings.js (1 critical)

**Line 106**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  const apiRequest = async (url, options = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### pages/CommunicationPreferences.js (1 critical)

**Line 125**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
      await saveSettings(async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### pages/SmartSchedulerSettings.js (1 critical)

**Line 145**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  const apiRequest = async (url, options = {}) => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### pages/BorrowerOAuthCallback.js (1 critical)

**Line 25**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
  const handleCallback = async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### pages/ClientPortalSettings.js (1 critical)

**Line 110**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
      await saveSettings(async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### pages/EmailIntegrationSettings.js (1 critical)

**Line 133**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
      const response = await saveSettings(async () => {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

### services/portalApi.js (1 critical)

**Line 12**: Async function makes API calls without try-catch or useAsyncOperation wrapper
```
async function apiRequest(endpoint, options = {}) {
```
**Fix**: Wrap in try-catch or use useAsyncOperation hook

---

## Frontend Analysis

**Files Scanned**: 220
**Average Score**: 58.81/100

### components/VideoMeetings.js
**Score**: 0.0/100 | Critical: 0 | High: 15 | Medium: 14 | Low: 0

[HIGH] **Line 210**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 375**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 412**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 415**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 419**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 433**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 436**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 495**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 505**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 508**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 663**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 666**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1145**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1462**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1465**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 139**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 140**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 141**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 200**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 235**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 268**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 284**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 299**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 315**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 332**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 335**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 368**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 401**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 426**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/SmartScheduler.js
**Score**: 0.0/100 | Critical: 0 | High: 21 | Medium: 14 | Low: 0

[HIGH] **Line 220**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 223**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 227**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 242**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 259**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 288**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 291**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 295**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 309**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 312**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 369**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 403**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 406**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 410**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 667**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1004**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1007**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1011**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1682**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1685**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1689**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 129**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 130**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 131**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 132**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 168**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 195**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 234**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 252**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 274**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 302**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 358**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 394**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 997**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1675**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/OnboardingWizard.js
**Score**: 0.0/100 | Critical: 0 | High: 11 | Medium: 13 | Low: 0

[HIGH] **Line 226**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 232**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 243**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 349**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 736**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 762**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2444**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2489**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2513**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2541**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2833**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 428**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 440**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 483**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3039**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3052**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3110**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3152**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3172**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 164**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2409**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2454**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2504**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2532**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/ITHelpdeskAdmin.js
**Score**: 0.0/100 | Critical: 0 | High: 10 | Medium: 5 | Low: 0

[HIGH] **Line 98**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 102**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 108**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 120**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 124**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 128**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 134**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 146**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 150**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 154**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 39**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 67**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 86**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 113**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 139**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/WorkflowConfigEditor.js
**Score**: 0.0/100 | Critical: 0 | High: 4 | Medium: 18 | Low: 0

[HIGH] **Line 367**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 599**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 665**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 704**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 103**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 131**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 136**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 141**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 162**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 171**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 178**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 230**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 270**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 305**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 340**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 380**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 413**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 445**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 498**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 507**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 571**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 676**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/LoanDetail.js
**Score**: 0.0/100 | Critical: 0 | High: 16 | Medium: 14 | Low: 0

[HIGH] **Line 464**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 495**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 533**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 545**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 548**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 700**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 724**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 748**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 751**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 756**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 775**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 779**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 795**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 822**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 877**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 885**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 294**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2498**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2506**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2913**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3023**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3091**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3216**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 371**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 390**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 423**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 608**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 711**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 728**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 767**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/PartnerDashboardPortal.js
**Score**: 0.0/100 | Critical: 0 | High: 5 | Medium: 16 | Low: 0

[HIGH] **Line 460**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1353**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1368**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1383**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1557**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 524**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 585**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 591**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 775**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 839**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 841**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 843**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1038**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1131**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1153**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1179**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1203**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1207**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1307**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1308**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 209**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/MumClientDetail.js
**Score**: 0.0/100 | Critical: 0 | High: 12 | Medium: 2 | Low: 0

[HIGH] **Line 205**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 252**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 335**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 338**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 436**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 524**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 529**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 538**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 568**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 570**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 620**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 628**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 2021**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2029**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/MeetingRoom.js
**Score**: 0.0/100 | Critical: 0 | High: 13 | Medium: 15 | Low: 0

[HIGH] **Line 512**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 517**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 703**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 707**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 727**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 749**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 753**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 989**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1084**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1087**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1104**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1131**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1162**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 111**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 131**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 539**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 615**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 672**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 732**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 765**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 807**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 848**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 867**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 886**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1014**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1053**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1111**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1135**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/MicrositeEditor.js
**Score**: 0.0/100 | Critical: 0 | High: 0 | Medium: 30 | Low: 0

[MEDIUM] **Line 140**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 160**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 164**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 168**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 192**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 195**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 199**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 216**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 219**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 223**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 240**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 243**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 247**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 276**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 313**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 318**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 339**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 341**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 345**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 355**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 53**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 68**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 95**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 111**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 146**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 178**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 209**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 233**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 261**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 328**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/ClientProfile.js
**Score**: 0.0/100 | Critical: 0 | High: 10 | Medium: 4 | Low: 0

[HIGH] **Line 148**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 195**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 336**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 339**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 437**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 525**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 530**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 539**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 569**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 571**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 1125**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1133**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 216**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 255**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/CommunicationIntelligence.js
**Score**: 0.0/100 | Critical: 0 | High: 10 | Medium: 18 | Low: 0

[HIGH] **Line 336**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 340**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 369**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 373**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 409**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 413**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 428**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 432**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 506**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 535**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 123**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 124**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 134**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 176**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 194**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 216**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 238**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 253**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 268**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 283**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 298**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 327**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 351**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 384**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 397**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 419**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 488**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 518**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/ReconciliationCenter.js
**Score**: 0.0/100 | Critical: 3 | High: 17 | Medium: 21 | Low: 0

[CRITICAL] **Line 1167**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1186**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1210**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[HIGH] **Line 258**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 281**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 285**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 533**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 653**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 657**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 697**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 764**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 768**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 818**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 822**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 883**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 887**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1058**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1098**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1103**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1142**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 173**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 205**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 263**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 292**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 355**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 380**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 384**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 394**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 401**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 480**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 545**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 610**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 720**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 794**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 844**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1067**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1115**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1177**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1196**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1229**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1240**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/Tasks.js
**Score**: 0.0/100 | Critical: 0 | High: 10 | Medium: 9 | Low: 0

[HIGH] **Line 959**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1141**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1192**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1241**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1659**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1663**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1665**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1669**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1702**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1705**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 755**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 770**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 785**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 794**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 803**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 812**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 851**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 897**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1004**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/LeadDetail.js
**Score**: 0.0/100 | Critical: 0 | High: 29 | Medium: 21 | Low: 1

[HIGH] **Line 444**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 464**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 590**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 804**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 810**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 840**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 846**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 892**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 899**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1199**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1297**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1385**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1390**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1399**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1429**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1431**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1465**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1477**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1487**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1603**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1615**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1625**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1634**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1646**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1650**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1653**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1659**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 4131**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 4133**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 283**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3322**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3330**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3546**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3756**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3866**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3934**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 4550**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[LOW] **Line 1511**: Using deprecated pattern: console.log for errors
- **Fix**: Use logger.error() or proper error tracking

[MEDIUM] **Line 618**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 645**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 683**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 691**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 734**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 789**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 828**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 865**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 879**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 938**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1038**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1068**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1110**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/CoborrowerApplication.js
**Score**: 0.0/100 | Critical: 0 | High: 9 | Medium: 7 | Low: 0

[HIGH] **Line 175**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 195**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 198**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 210**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 215**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 220**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 225**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 234**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 238**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 204**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 231**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 237**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 707**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 708**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 727**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 731**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/MergeCenter.js
**Score**: 0.0/100 | Critical: 0 | High: 6 | Medium: 8 | Low: 0

[HIGH] **Line 183**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 187**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 222**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 240**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 243**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 247**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 243**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 744**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 748**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 28**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 53**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 162**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 195**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 227**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/BorrowerApplication.js
**Score**: 0.0/100 | Critical: 0 | High: 0 | Medium: 34 | Low: 0

[MEDIUM] **Line 256**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 271**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 395**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 634**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 684**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 694**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 891**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 932**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 968**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1038**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1071**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1081**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1216**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1275**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1285**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1473**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1502**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1520**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1613**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1642**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1661**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1754**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1792**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1802**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1951**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2090**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2132**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2165**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2177**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2181**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2187**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2280**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2288**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2292**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/AILandingPage.js
**Score**: 0.0/100 | Critical: 0 | High: 9 | Medium: 8 | Low: 0

[HIGH] **Line 257**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 307**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 330**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 455**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 483**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 486**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 547**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 614**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 631**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 329**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2225**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2580**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2584**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1437**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1686**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1714**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1796**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/ExperimentsDashboard.js
**Score**: 0.0/100 | Critical: 0 | High: 10 | Medium: 7 | Low: 0

[HIGH] **Line 117**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 138**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 143**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 161**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 167**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 185**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 191**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 212**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 216**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 261**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 43**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 66**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 91**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 121**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 149**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 173**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 197**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/Loans.js
**Score**: 0.0/100 | Critical: 0 | High: 11 | Medium: 5 | Low: 0

[HIGH] **Line 198**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 201**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 205**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 218**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 223**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 228**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 299**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 325**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 334**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 364**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 414**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 209**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 232**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 686**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1061**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 187**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/SLASettings.js
**Score**: 0.0/100 | Critical: 0 | High: 1 | Medium: 23 | Low: 0

[HIGH] **Line 1**: Missing required imports: useAsyncOperation
- **Fix**: Add: import { useAsyncOperation } from appropriate paths

[MEDIUM] **Line 599**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 665**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 745**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1703**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1715**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1853**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 52**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 59**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 66**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 73**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 80**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 87**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 95**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 121**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 143**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 160**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 182**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 225**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 291**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 311**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 340**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 495**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1883**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/Settings.js
**Score**: 0.0/100 | Critical: 0 | High: 83 | Medium: 66 | Low: 0

[HIGH] **Line 1**: Missing required imports: useAsyncOperation, toast
- **Fix**: Add: import { useAsyncOperation, toast } from appropriate paths

[HIGH] **Line 945**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 949**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 985**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 988**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 992**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1018**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1021**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1025**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1102**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1108**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1128**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1133**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1137**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1173**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1192**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1196**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1200**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1214**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1217**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1221**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1245**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1247**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1251**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1268**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1270**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1274**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1306**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1370**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1373**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1402**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1439**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1441**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1445**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1470**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1493**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1517**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1525**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1533**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1547**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1551**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1673**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1691**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1708**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1712**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1729**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1732**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1736**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1755**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1760**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1764**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1987**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2016**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2025**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2050**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2052**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2071**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2100**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2161**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2187**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2189**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2221**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2230**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2252**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2284**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2301**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2307**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2326**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2331**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2350**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2355**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2374**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2379**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 3237**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 3239**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 3243**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 4741**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 5038**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 5922**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 5936**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 5940**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 6058**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 6060**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 312**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1680**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1708**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3367**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 4834**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 4835**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 4919**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 4922**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 4963**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 5191**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 5425**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 5773**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 5848**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 5972**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 6091**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 6171**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 6248**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 6331**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 6410**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 6504**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 53**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 69**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 86**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 113**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 149**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 697**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 735**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 782**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 892**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 930**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 962**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1001**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1040**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1088**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1113**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1144**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1178**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1206**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1234**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1257**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1284**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1329**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1420**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1454**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1477**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1500**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1537**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1565**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1650**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1680**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1721**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1743**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1934**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1962**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2078**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2107**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2137**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2259**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2291**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2340**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2388**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2411**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2449**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 2466**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 3231**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 5912**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/APIKeysSettings.js
**Score**: 0.0/100 | Critical: 0 | High: 0 | Medium: 20 | Low: 0

[MEDIUM] **Line 3**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 500**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 575**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 636**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 705**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 722**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 792**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 74**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 75**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 76**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 77**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 78**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 123**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 151**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 175**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 196**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 217**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 244**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 264**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 284**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### services/responsibilitiesApi.js
**Score**: 0.0/100 | Critical: 14 | High: 0 | Medium: 13 | Low: 0

[CRITICAL] **Line 13**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 25**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 33**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 41**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 50**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 59**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 67**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 75**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 88**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 96**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 109**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 117**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 126**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 135**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 26**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 34**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 42**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 51**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 60**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 68**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 76**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 89**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 97**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 110**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 118**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 127**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 136**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### services/smartDocsApi.js
**Score**: 0.0/100 | Critical: 26 | High: 0 | Medium: 26 | Low: 0

[CRITICAL] **Line 13**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 39**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 51**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 61**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 76**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 92**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 114**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 124**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 135**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 151**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 164**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 175**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 190**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 201**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 217**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 227**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 241**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 255**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 265**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 278**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 292**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 306**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 316**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 330**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 340**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 352**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 133**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 40**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 52**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 62**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 77**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 101**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 115**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 126**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 136**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 155**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 165**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 176**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 191**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 202**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 218**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 228**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 242**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 256**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 269**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 279**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 297**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 307**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 317**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 331**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 341**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 353**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### services/conversationIntelligenceApi.js
**Score**: 0.0/100 | Critical: 25 | High: 0 | Medium: 0 | Low: 0

[CRITICAL] **Line 27**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 35**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 43**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 60**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 85**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 93**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 101**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 121**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 129**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 137**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 157**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 165**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 173**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 187**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 195**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 232**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 240**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 254**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 262**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 275**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 289**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 302**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 316**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 334**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 375**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook


### services/onboardingApi.js
**Score**: 0.0/100 | Critical: 22 | High: 0 | Medium: 21 | Low: 0

[CRITICAL] **Line 16**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 35**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 56**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 78**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 97**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 114**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 136**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 161**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 180**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 199**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 215**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 234**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 242**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 258**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 274**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 292**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 312**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 331**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 351**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 371**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 388**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 404**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 17**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 36**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 57**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 79**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 98**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 115**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 137**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 162**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 181**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 200**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 220**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 243**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 259**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 275**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 293**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 313**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 332**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 352**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 372**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 389**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 405**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### services/blogApi.js
**Score**: 0.0/100 | Critical: 26 | High: 0 | Medium: 0 | Low: 0

[CRITICAL] **Line 52**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 59**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 64**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 69**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 76**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 83**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 90**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 97**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 110**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 117**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 124**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 131**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 136**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 141**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 146**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 151**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 158**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 167**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 176**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 186**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 198**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 203**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 210**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 217**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 224**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 231**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook


### services/api.js
**Score**: 0.0/100 | Critical: 309 | High: 0 | Medium: 5 | Low: 3

[CRITICAL] **Line 195**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 199**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 206**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 210**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 214**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 218**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 222**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 226**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 229**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 237**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 241**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 245**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 249**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 253**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 257**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 264**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 268**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 272**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 276**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 280**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 284**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 291**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 295**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 299**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 306**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 310**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 479**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 487**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 497**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 501**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 509**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 513**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 517**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 521**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 525**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 532**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 536**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 544**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 548**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 556**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 560**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 564**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 568**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 572**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 579**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 583**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 587**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 591**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 595**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 603**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 607**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 611**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 615**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 619**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 623**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 626**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 633**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 641**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 655**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 663**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 667**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 671**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 681**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 685**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 689**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 693**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 697**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 701**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 709**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 713**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 717**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 721**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 725**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 729**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 737**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 742**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 747**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 752**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 760**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 764**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 768**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 772**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 776**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 780**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 789**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 795**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 805**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 812**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 818**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 824**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 836**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 840**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 846**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 852**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 858**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 862**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 868**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 877**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 881**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 887**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 891**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 897**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 901**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 909**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 913**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 917**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 921**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 927**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 937**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 941**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 945**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 953**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 962**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 966**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 970**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 976**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 982**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 994**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1000**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1006**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1013**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1019**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1025**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1034**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1041**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1047**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1056**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1063**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1069**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1075**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1081**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1090**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1096**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1102**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1114**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1119**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1123**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1127**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1133**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1140**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1145**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1151**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1155**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1164**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1169**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1174**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1180**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1184**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1188**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1192**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1196**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1202**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1206**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1210**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1217**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1221**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1225**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1229**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1236**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1240**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1244**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1250**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1254**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1260**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1264**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1268**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1274**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1280**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1284**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1290**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1294**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1298**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1304**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1309**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1316**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1320**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1325**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1333**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1338**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1343**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1350**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1355**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1363**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1368**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1373**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1377**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1382**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1387**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1391**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1396**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1400**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1404**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1408**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1412**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1416**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1420**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1424**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1428**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1433**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1437**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1446**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1450**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1454**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1463**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1467**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1476**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1496**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1521**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1531**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1541**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1549**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1556**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1561**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1567**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1576**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1590**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1601**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1614**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1620**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1626**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1632**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1638**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1650**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1656**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1662**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1672**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1678**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1684**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1690**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1703**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1709**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1715**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1724**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1730**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1736**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1742**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1750**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1759**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1763**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1767**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1771**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1775**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1779**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1783**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1789**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1795**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1799**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1803**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1809**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1813**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1819**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1823**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1829**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1837**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1841**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1845**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1849**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1855**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1859**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1865**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1871**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1875**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1881**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1885**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1894**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1898**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1902**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1906**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1910**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1914**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1920**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1927**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1936**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1940**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1944**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1950**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1954**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1960**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1965**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 1971**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2130**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2136**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2142**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2148**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2154**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2160**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2169**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2174**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2179**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2184**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2189**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2194**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2199**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2206**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2214**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2222**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2228**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2233**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2242**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2268**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2274**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2279**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2284**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2290**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2301**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2311**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2322**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2332**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 2342**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 1683**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1685**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1735**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1737**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[LOW] **Line 171**: Using deprecated pattern: console.log for errors
- **Fix**: Use logger.error() or proper error tracking

[LOW] **Line 2080**: Using deprecated pattern: console.log for errors
- **Fix**: Use logger.error() or proper error tracking

[LOW] **Line 2120**: Using deprecated pattern: console.log for errors
- **Fix**: Use logger.error() or proper error tracking

[MEDIUM] **Line 423**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### services/goalsApi.js
**Score**: 0.0/100 | Critical: 8 | High: 0 | Medium: 7 | Low: 0

[CRITICAL] **Line 13**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 25**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 39**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 48**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 57**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 69**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 82**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 91**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 32**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 40**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 49**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 58**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 70**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 83**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 92**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/admin/PURLManager.js
**Score**: 0.0/100 | Critical: 0 | High: 7 | Medium: 13 | Low: 0

[HIGH] **Line 156**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 703**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 710**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 733**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 747**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 751**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 761**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 400**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 441**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 652**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 26**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 34**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 48**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 56**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 64**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 74**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 82**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 92**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 100**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 108**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### services/permissionsService.ts
**Score**: 0.0/100 | Critical: 35 | High: 0 | Medium: 0 | Low: 0

[CRITICAL] **Line 209**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 217**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 225**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 237**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 245**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 253**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 265**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 273**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 281**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 289**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 297**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 312**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 320**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 328**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 348**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 361**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 378**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 396**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 404**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 426**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 437**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 450**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 463**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 476**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 488**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 508**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 517**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 525**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 536**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 547**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 558**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 569**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 577**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 585**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 597**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook


### pages/PurchaseApplication.js
**Score**: 5.0/100 | Critical: 0 | High: 4 | Medium: 11 | Low: 0

[HIGH] **Line 2195**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 2200**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 4861**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 4922**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 17**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1955**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1976**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1983**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 2011**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 4944**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 4953**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 5146**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1664**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1784**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1955**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/AccessAuditTab.js
**Score**: 10.0/100 | Critical: 0 | High: 9 | Medium: 0 | Low: 0

[HIGH] **Line 63**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 77**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 103**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 108**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 119**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 124**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 131**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 138**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 151**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### pages/DocumentUploadSettings.js
**Score**: 10.0/100 | Critical: 0 | High: 1 | Medium: 16 | Low: 0

[HIGH] **Line 1**: Missing required imports: toast
- **Fix**: Add: import { toast } from appropriate paths

[MEDIUM] **Line 78**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 190**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 217**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 221**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 253**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 257**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 4**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 23**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 40**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 41**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 42**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 43**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 44**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 196**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 240**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 268**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/Leads.js
**Score**: 10.0/100 | Critical: 0 | High: 7 | Medium: 4 | Low: 0

[HIGH] **Line 190**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 193**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 197**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 229**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 291**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 357**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 502**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 220**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 675**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 983**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 179**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/RefinanceApplication.js
**Score**: 15.0/100 | Critical: 0 | High: 2 | Medium: 13 | Low: 0

[HIGH] **Line 3344**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 3405**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 17**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 475**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1526**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1547**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1642**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1669**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1798**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3427**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3436**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3448**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 3780**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1361**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1526**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/AIOutreach.js
**Score**: 15.0/100 | Critical: 0 | High: 0 | Medium: 17 | Low: 0

[MEDIUM] **Line 124**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 139**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 157**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 175**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 213**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 233**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 260**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 278**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 299**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 317**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 334**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 348**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 362**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 376**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 395**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 413**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 521**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/LeadCaptureSettings.js
**Score**: 15.0/100 | Critical: 0 | High: 1 | Medium: 15 | Low: 0

[HIGH] **Line 1**: Missing required imports: toast
- **Fix**: Add: import { toast } from appropriate paths

[MEDIUM] **Line 74**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 241**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 268**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 272**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 304**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 308**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 4**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 25**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 42**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 43**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 44**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 45**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 187**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 247**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 291**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/CompanyBrandingSettings.js
**Score**: 15.0/100 | Critical: 0 | High: 0 | Medium: 17 | Low: 0

[MEDIUM] **Line 3**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 448**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 519**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 625**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 723**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 829**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 896**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 928**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 50**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 108**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 128**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 145**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 162**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 179**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 196**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 213**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 230**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/UserProfileSettings.js
**Score**: 20.0/100 | Critical: 2 | High: 0 | Medium: 8 | Low: 0

[CRITICAL] **Line 150**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[CRITICAL] **Line 350**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 9**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 64**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 86**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 111**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 127**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 151**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 304**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 352**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/SmartDocs.js
**Score**: 20.0/100 | Critical: 0 | High: 6 | Medium: 4 | Low: 0

[HIGH] **Line 266**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 269**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 273**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 411**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 414**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 418**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 48**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 55**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 209**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 400**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/CertificationModal.js
**Score**: 25.0/100 | Critical: 0 | High: 6 | Medium: 3 | Low: 0

[HIGH] **Line 32**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 37**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 74**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 77**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 106**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 109**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 19**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 56**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 91**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/TeamMemberProfile.js
**Score**: 25.0/100 | Critical: 0 | High: 7 | Medium: 1 | Low: 0

[HIGH] **Line 35**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 46**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 49**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 63**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 69**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 97**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 100**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 79**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/onboarding/OnboardingWizard.jsx
**Score**: 25.0/100 | Critical: 0 | High: 4 | Medium: 7 | Low: 0

[HIGH] **Line 251**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 258**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 311**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 315**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 73**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 100**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 140**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 170**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 198**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 230**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 296**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/ActionSidebar.js
**Score**: 30.0/100 | Critical: 0 | High: 5 | Medium: 4 | Low: 0

[HIGH] **Line 386**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 396**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 423**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 428**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 461**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 35**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 338**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 359**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 404**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/EmailDropZone.js
**Score**: 30.0/100 | Critical: 0 | High: 7 | Medium: 0 | Low: 0

[HIGH] **Line 224**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 274**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 305**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 494**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 496**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 500**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 516**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### pages/CommunicationPreferences.js
**Score**: 30.0/100 | Critical: 1 | High: 0 | Medium: 10 | Low: 0

[CRITICAL] **Line 125**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 2**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 23**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 43**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 65**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 80**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 95**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 110**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 126**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 229**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 255**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/PowerDialer.js
**Score**: 30.0/100 | Critical: 0 | High: 0 | Medium: 14 | Low: 0

[MEDIUM] **Line 129**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 144**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 159**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 174**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 195**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 243**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 272**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 306**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 371**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 410**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 431**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 452**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 474**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 498**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/ReferralPartnerDetail.js
**Score**: 30.0/100 | Critical: 0 | High: 7 | Medium: 0 | Low: 0

[HIGH] **Line 99**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 110**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 129**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 197**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 200**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 323**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 326**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### pages/ClientPortalSettings.js
**Score**: 30.0/100 | Critical: 1 | High: 0 | Medium: 10 | Low: 0

[CRITICAL] **Line 110**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 2**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 22**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 107**: Save function does not validate data before API call
- **Fix**: Add validation check before API call to catch errors early

[MEDIUM] **Line 43**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 65**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 80**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 95**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 111**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 215**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 243**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/BuyerIntake.js
**Score**: 30.0/100 | Critical: 0 | High: 4 | Medium: 6 | Low: 0

[HIGH] **Line 399**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 428**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 512**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 519**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 417**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 572**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 900**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 903**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 904**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 497**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/TeamMembers.js
**Score**: 30.0/100 | Critical: 0 | High: 6 | Medium: 2 | Low: 0

[HIGH] **Line 179**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 182**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 200**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 203**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 258**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 260**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 457**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 541**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/portal/ActiveLoanPortal.jsx
**Score**: 30.0/100 | Critical: 0 | High: 5 | Medium: 4 | Low: 0

[HIGH] **Line 1172**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1223**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1285**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1306**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 1325**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 1374**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1131**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1193**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 1250**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/DocumentIntakeManager.js
**Score**: 35.0/100 | Critical: 0 | High: 2 | Medium: 9 | Low: 0

[HIGH] **Line 502**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 519**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 22**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 25**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 54**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 79**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 82**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 105**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 139**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 170**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 197**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/EmailIntegrationSettings.js
**Score**: 35.0/100 | Critical: 1 | High: 0 | Medium: 9 | Low: 0

[CRITICAL] **Line 133**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 9**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 52**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 72**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 110**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 134**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 238**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 263**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 289**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 306**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/Calendar.js
**Score**: 35.0/100 | Critical: 0 | High: 4 | Medium: 5 | Low: 0

[HIGH] **Line 247**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 270**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 323**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 344**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 658**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 740**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 764**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 777**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 836**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/PURLPortal.js
**Score**: 38.0/100 | Critical: 0 | High: 4 | Medium: 4 | Low: 1

[HIGH] **Line 854**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 906**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 927**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 945**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 1019**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1278**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1291**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[LOW] **Line 796**: Using deprecated pattern: console.log for errors
- **Fix**: Use logger.error() or proper error tracking

[MEDIUM] **Line 875**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/ResponsibilityModal.js
**Score**: 40.0/100 | Critical: 0 | High: 2 | Medium: 8 | Low: 0

[HIGH] **Line 140**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 159**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 106**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 120**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 174**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 351**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 352**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 363**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 380**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 413**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/MarketDashboard.js
**Score**: 40.0/100 | Critical: 0 | High: 0 | Medium: 12 | Low: 0

[MEDIUM] **Line 127**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 135**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 167**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 484**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 557**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 565**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 49**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 75**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 183**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 492**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 592**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 610**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/IntegrationSettings.js
**Score**: 40.0/100 | Critical: 0 | High: 0 | Medium: 12 | Low: 0

[MEDIUM] **Line 2**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 20**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 31**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 52**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 67**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 84**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 99**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 130**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 153**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 186**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 217**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 240**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/EmailIntelligence.js
**Score**: 40.0/100 | Critical: 0 | High: 2 | Medium: 8 | Low: 0

[HIGH] **Line 243**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 247**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 100**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 120**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 138**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 159**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 175**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 191**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 228**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 255**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/SmartDocsClientDetail.js
**Score**: 40.0/100 | Critical: 0 | High: 2 | Medium: 8 | Low: 0

[HIGH] **Line 212**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 252**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 44**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 66**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 99**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 145**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 165**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 201**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 224**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 248**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/VoiceOSDashboard.js
**Score**: 45.0/100 | Critical: 0 | High: 3 | Medium: 5 | Low: 0

[HIGH] **Line 232**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 235**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 238**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 95**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 103**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 111**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 171**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 217**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### utils/errorHandling.js
**Score**: 50.0/100 | Critical: 0 | High: 0 | Medium: 10 | Low: 0

[MEDIUM] **Line 132**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 141**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 143**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 145**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 162**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 166**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 194**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 239**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 271**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 447**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/ApplicationSummaryReview.js
**Score**: 50.0/100 | Critical: 0 | High: 1 | Medium: 8 | Low: 0

[HIGH] **Line 247**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 117**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 244**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 253**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 369**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 405**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 409**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 435**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 437**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/CalendarSidebar.js
**Score**: 50.0/100 | Critical: 0 | High: 3 | Medium: 4 | Low: 0

[HIGH] **Line 444**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 500**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 520**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 715**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 811**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 829**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 947**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### hooks/useAsyncOperation.js
**Score**: 50.0/100 | Critical: 1 | High: 0 | Medium: 6 | Low: 0

[CRITICAL] **Line 143**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 16**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 142**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 142**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 152**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 173**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 207**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/AgentGovernanceSettings.js
**Score**: 50.0/100 | Critical: 1 | High: 0 | Medium: 6 | Low: 0

[CRITICAL] **Line 106**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 14**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 158**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 162**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 403**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 644**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 108**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/RealtorDashboard.js
**Score**: 50.0/100 | Critical: 0 | High: 1 | Medium: 8 | Low: 0

[HIGH] **Line 128**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 102**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 128**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 320**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 412**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 558**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 567**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 698**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 702**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/SmartSchedulerSettings.js
**Score**: 50.0/100 | Critical: 1 | High: 0 | Medium: 6 | Low: 0

[CRITICAL] **Line 145**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 15**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 205**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 209**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 510**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 860**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 147**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/OnboardingWizard.js
**Score**: 50.0/100 | Critical: 0 | High: 5 | Medium: 0 | Low: 0

[HIGH] **Line 61**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 121**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 129**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 134**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 162**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### pages/ConversationIntelligenceRecordingDetail.js
**Score**: 50.0/100 | Critical: 0 | High: 4 | Medium: 2 | Low: 0

[HIGH] **Line 154**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 169**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 171**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 238**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 62**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 140**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/KnowledgeBase.js
**Score**: 50.0/100 | Critical: 0 | High: 0 | Medium: 10 | Low: 0

[MEDIUM] **Line 460**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 518**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 535**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 590**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 56**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 78**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 107**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 145**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 176**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 215**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### services/schedulingService.js
**Score**: 50.0/100 | Critical: 0 | High: 0 | Medium: 10 | Low: 0

[MEDIUM] **Line 28**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 48**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 61**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 96**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 113**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 169**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 217**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 258**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 285**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 303**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/onboarding/steps/Step1Registration.jsx
**Score**: 50.0/100 | Critical: 0 | High: 4 | Medium: 2 | Low: 0

[HIGH] **Line 148**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 152**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 184**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 188**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 135**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 171**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/VideoCallScheduleModal.js
**Score**: 55.0/100 | Critical: 0 | High: 0 | Medium: 9 | Low: 0

[MEDIUM] **Line 324**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 547**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 549**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 553**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 86**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 111**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 206**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 274**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 351**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/GoalModal.js
**Score**: 55.0/100 | Critical: 0 | High: 3 | Medium: 3 | Low: 0

[HIGH] **Line 51**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 62**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 116**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 107**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 139**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 258**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/Users.js
**Score**: 55.0/100 | Critical: 0 | High: 0 | Medium: 9 | Low: 0

[MEDIUM] **Line 252**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 263**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 277**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 295**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 304**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 356**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 374**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 383**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 446**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/EstimateComparison.js
**Score**: 55.0/100 | Critical: 0 | High: 0 | Medium: 9 | Low: 0

[MEDIUM] **Line 956**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 965**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 170**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 200**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 289**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 388**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 478**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 558**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 577**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/AdminCustomDomains.js
**Score**: 55.0/100 | Critical: 0 | High: 0 | Medium: 9 | Low: 0

[MEDIUM] **Line 448**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 485**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 27**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 55**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 90**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 114**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 141**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 167**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 209**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/ScheduleAppointmentModal.js
**Score**: 58.0/100 | Critical: 0 | High: 0 | Medium: 8 | Low: 1

[MEDIUM] **Line 268**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 568**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 570**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 574**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[LOW] **Line 370**: Using deprecated pattern: console.log for errors
- **Fix**: Use logger.error() or proper error tracking

[MEDIUM] **Line 88**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 114**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 300**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 342**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/CalendarManagement.js
**Score**: 60.0/100 | Critical: 0 | High: 0 | Medium: 8 | Low: 0

[MEDIUM] **Line 33**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 34**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 35**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 74**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 86**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 119**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 130**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 161**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/AIAssistant.js
**Score**: 60.0/100 | Critical: 0 | High: 3 | Medium: 2 | Low: 0

[HIGH] **Line 125**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 157**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 159**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 214**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 238**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/MicrositeThemeCustomizer.js
**Score**: 60.0/100 | Critical: 0 | High: 0 | Medium: 8 | Low: 0

[MEDIUM] **Line 1428**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 132**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 191**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 282**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 328**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 419**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 646**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 673**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/PURLApplication.js
**Score**: 60.0/100 | Critical: 0 | High: 0 | Medium: 8 | Low: 0

[MEDIUM] **Line 48**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 544**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 558**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 568**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 666**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 730**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 734**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 378**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/PURLDashboard.js
**Score**: 60.0/100 | Critical: 0 | High: 4 | Medium: 0 | Low: 0

[HIGH] **Line 87**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 101**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 104**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 340**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/VideoClips/ClipLibrary.js
**Score**: 60.0/100 | Critical: 0 | High: 4 | Medium: 0 | Low: 0

[HIGH] **Line 89**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 103**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 114**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 308**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/shared/TaskDetailPanel.js
**Score**: 60.0/100 | Critical: 0 | High: 3 | Medium: 2 | Low: 0

[HIGH] **Line 562**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 600**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 606**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 164**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 574**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/onboarding/steps/VerificationModal.jsx
**Score**: 60.0/100 | Critical: 0 | High: 3 | Medium: 2 | Low: 0

[HIGH] **Line 110**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 113**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 117**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 57**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 96**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/AddSkillModal.js
**Score**: 65.0/100 | Critical: 0 | High: 2 | Medium: 3 | Low: 0

[HIGH] **Line 33**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 44**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 29**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 70**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 119**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/ManagerAssessmentModal.js
**Score**: 65.0/100 | Critical: 0 | High: 2 | Medium: 3 | Low: 0

[HIGH] **Line 19**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 29**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 15**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 79**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 95**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/EscalationPanel.js
**Score**: 65.0/100 | Critical: 0 | High: 0 | Medium: 7 | Low: 0

[MEDIUM] **Line 101**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 187**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 306**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 308**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 49**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 71**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 136**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/CoachCorner.js
**Score**: 65.0/100 | Critical: 0 | High: 3 | Medium: 1 | Low: 0

[HIGH] **Line 226**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 256**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 264**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 341**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/PermissionRequestModal.js
**Score**: 65.0/100 | Critical: 0 | High: 0 | Medium: 7 | Low: 0

[MEDIUM] **Line 10**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 36**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 73**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 76**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 105**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 235**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 239**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### hooks/useRealtorPortal.js
**Score**: 65.0/100 | Critical: 1 | High: 0 | Medium: 3 | Low: 0

[CRITICAL] **Line 25**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 33**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 296**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 333**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/PipelineEfficiency.js
**Score**: 65.0/100 | Critical: 0 | High: 1 | Medium: 5 | Low: 0

[HIGH] **Line 190**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 38**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 39**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 40**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 41**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 42**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/AIUnderwriter.js
**Score**: 65.0/100 | Critical: 0 | High: 1 | Medium: 5 | Low: 0

[HIGH] **Line 90**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 143**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 248**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 473**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 582**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 164**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/ScenarioModeling.js
**Score**: 65.0/100 | Critical: 0 | High: 3 | Medium: 1 | Low: 0

[HIGH] **Line 88**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 106**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 111**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 404**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### services/featureService.js
**Score**: 65.0/100 | Critical: 0 | High: 0 | Medium: 7 | Low: 0

[MEDIUM] **Line 50**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 105**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 125**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 146**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 169**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 200**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 228**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/microsites/themes/MinimalFocus.js
**Score**: 65.0/100 | Critical: 0 | High: 0 | Medium: 7 | Low: 0

[MEDIUM] **Line 55**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 78**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 161**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 216**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 242**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 299**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 61**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/microsites/MicrositeWizard.js
**Score**: 65.0/100 | Critical: 0 | High: 1 | Medium: 5 | Low: 0

[HIGH] **Line 308**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 435**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 158**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 243**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 302**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 634**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/MortgageChat/MortgageChat.js
**Score**: 65.0/100 | Critical: 0 | High: 0 | Medium: 7 | Low: 0

[MEDIUM] **Line 405**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 459**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 469**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 87**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 137**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 190**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 217**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/CoreResponsibilitiesSection.js
**Score**: 70.0/100 | Critical: 0 | High: 3 | Medium: 0 | Low: 0

[HIGH] **Line 102**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 153**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 169**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/EscalationModal.js
**Score**: 70.0/100 | Critical: 0 | High: 0 | Medium: 6 | Low: 0

[MEDIUM] **Line 47**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 123**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 210**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 221**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 23**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 82**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/UnifiedTaskSidebar.js
**Score**: 70.0/100 | Critical: 0 | High: 1 | Medium: 4 | Low: 0

[HIGH] **Line 205**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 32**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 170**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 266**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 304**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/PermissionsTab.js
**Score**: 70.0/100 | Critical: 0 | High: 3 | Medium: 0 | Low: 0

[HIGH] **Line 70**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 90**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 93**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/MortgageAIChat.js
**Score**: 70.0/100 | Critical: 0 | High: 0 | Medium: 6 | Low: 0

[MEDIUM] **Line 248**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 514**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 67**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 88**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 121**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 194**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/AIEmailTraining.js
**Score**: 70.0/100 | Critical: 0 | High: 0 | Medium: 6 | Low: 0

[MEDIUM] **Line 101**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 312**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 316**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 32**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 46**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 86**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/AppointmentModal.js
**Score**: 70.0/100 | Critical: 0 | High: 1 | Medium: 4 | Low: 0

[HIGH] **Line 71**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 14**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 96**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 199**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 34**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/CreateTaskModal.js
**Score**: 70.0/100 | Critical: 0 | High: 1 | Medium: 4 | Low: 0

[HIGH] **Line 56**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 12**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 76**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 149**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 24**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/MicrositePageManager.js
**Score**: 70.0/100 | Critical: 0 | High: 0 | Medium: 6 | Low: 0

[MEDIUM] **Line 76**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 99**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 136**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 169**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 212**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 231**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/Assistant.js
**Score**: 70.0/100 | Critical: 0 | High: 3 | Medium: 0 | Low: 0

[HIGH] **Line 150**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 182**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 184**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### pages/AdaptiveURLA.js
**Score**: 70.0/100 | Critical: 0 | High: 0 | Medium: 6 | Low: 0

[MEDIUM] **Line 26**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 325**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1130**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1206**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1213**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1214**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/AdminPanel.js
**Score**: 70.0/100 | Critical: 0 | High: 2 | Medium: 2 | Low: 0

[HIGH] **Line 177**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 574**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 1015**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 1153**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/PublicBooking.js
**Score**: 70.0/100 | Critical: 0 | High: 0 | Medium: 6 | Low: 0

[MEDIUM] **Line 184**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 485**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 586**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 102**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 150**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 201**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/ProcessTemplates.js
**Score**: 70.0/100 | Critical: 0 | High: 3 | Medium: 0 | Low: 0

[HIGH] **Line 88**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 108**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 118**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/admin/EmployeeInviteWizard.jsx
**Score**: 70.0/100 | Critical: 0 | High: 0 | Medium: 6 | Low: 0

[MEDIUM] **Line 164**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 538**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 49**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 63**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 77**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 169**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/admin/InviteManagementTable.jsx
**Score**: 70.0/100 | Critical: 0 | High: 2 | Medium: 2 | Low: 0

[HIGH] **Line 51**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 55**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 25**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 43**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/TaskWorkflowManager.js
**Score**: 75.0/100 | Critical: 0 | High: 0 | Medium: 5 | Low: 0

[MEDIUM] **Line 55**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 88**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 111**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 132**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 231**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/PreApprovalLetterSettings.js
**Score**: 75.0/100 | Critical: 0 | High: 1 | Medium: 3 | Low: 0

[HIGH] **Line 1**: Missing required imports: useAsyncOperation, toast
- **Fix**: Add: import { useAsyncOperation, toast } from appropriate paths

[MEDIUM] **Line 88**: Save function does not validate data before API call
- **Fix**: Add validation check before API call to catch errors early

[MEDIUM] **Line 47**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 94**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/SelfAssessmentModal.js
**Score**: 75.0/100 | Critical: 0 | High: 1 | Medium: 3 | Low: 0

[HIGH] **Line 37**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 28**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 56**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 148**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/AIEmailSetup.js
**Score**: 75.0/100 | Critical: 0 | High: 0 | Medium: 5 | Low: 0

[MEDIUM] **Line 22**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 37**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 51**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 76**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 108**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/FeatureManagement.js
**Score**: 75.0/100 | Critical: 0 | High: 0 | Medium: 5 | Low: 0

[MEDIUM] **Line 47**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 79**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 106**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 156**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 201**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/AssessSkillModal.js
**Score**: 75.0/100 | Critical: 0 | High: 1 | Medium: 3 | Low: 0

[HIGH] **Line 54**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 47**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 89**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 173**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/Portfolio.js
**Score**: 75.0/100 | Critical: 0 | High: 1 | Medium: 3 | Low: 0

[HIGH] **Line 101**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 599**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 613**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 662**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/ReferralPartners.js
**Score**: 75.0/100 | Critical: 0 | High: 1 | Medium: 3 | Low: 0

[HIGH] **Line 86**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 266**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 280**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 369**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### services/portalApi.js
**Score**: 75.0/100 | Critical: 1 | High: 0 | Medium: 1 | Low: 0

[CRITICAL] **Line 12**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook

[MEDIUM] **Line 24**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/microsites/themes/ModernGradient.js
**Score**: 75.0/100 | Critical: 0 | High: 0 | Medium: 5 | Low: 0

[MEDIUM] **Line 64**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 87**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 284**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 366**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 70**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/microsites/themes/ProfessionalClean.js
**Score**: 75.0/100 | Critical: 0 | High: 0 | Medium: 5 | Low: 0

[MEDIUM] **Line 67**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 90**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 295**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 386**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 73**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### lib/api/client.js
**Score**: 75.0/100 | Critical: 0 | High: 0 | Medium: 5 | Low: 0

[MEDIUM] **Line 102**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 422**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 426**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 483**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 612**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/realtor-portal/LetterDraftModal.js
**Score**: 75.0/100 | Critical: 0 | High: 1 | Medium: 3 | Low: 0

[HIGH] **Line 152**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 45**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 166**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 271**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/AcceptInvite.jsx
**Score**: 75.0/100 | Critical: 0 | High: 0 | Medium: 5 | Low: 0

[MEDIUM] **Line 72**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 98**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 269**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 273**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 337**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/portal/PerenniaClientPortalUltimate.jsx
**Score**: 75.0/100 | Critical: 0 | High: 0 | Medium: 5 | Low: 0

[MEDIUM] **Line 265**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 270**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 275**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 280**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()

[MEDIUM] **Line 288**: Using custom showToast instead of standard toast library
- **Fix**: Replace showToast() with toast.success() or toast.error()


### components/EmailReconciliationModal.js
**Score**: 80.0/100 | Critical: 0 | High: 2 | Medium: 0 | Low: 0

[HIGH] **Line 79**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 95**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/TeamAssignment.js
**Score**: 80.0/100 | Critical: 0 | High: 0 | Medium: 4 | Low: 0

[MEDIUM] **Line 18**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 37**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 70**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 97**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/AI1003Concierge.js
**Score**: 80.0/100 | Critical: 0 | High: 0 | Medium: 4 | Low: 0

[MEDIUM] **Line 176**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 321**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 343**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 106**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/DocumentDropModal.js
**Score**: 80.0/100 | Critical: 0 | High: 2 | Medium: 0 | Low: 0

[HIGH] **Line 90**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 103**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/InlineFollowup.js
**Score**: 80.0/100 | Critical: 0 | High: 0 | Medium: 4 | Low: 0

[MEDIUM] **Line 14**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 33**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 105**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 136**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/AIFeedbackLog.js
**Score**: 80.0/100 | Critical: 0 | High: 2 | Medium: 0 | Low: 0

[HIGH] **Line 49**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 62**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/PreApprovalLetterModal.js
**Score**: 80.0/100 | Critical: 0 | High: 0 | Medium: 4 | Low: 0

[MEDIUM] **Line 121**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 151**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 194**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 223**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/GoalTracker.js
**Score**: 80.0/100 | Critical: 0 | High: 0 | Medium: 4 | Low: 0

[MEDIUM] **Line 391**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 47**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 54**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 173**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/MissionControl.js
**Score**: 80.0/100 | Critical: 0 | High: 0 | Medium: 4 | Low: 0

[MEDIUM] **Line 36**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 37**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 38**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 39**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/ComplianceDashboard.js
**Score**: 80.0/100 | Critical: 0 | High: 2 | Medium: 0 | Low: 0

[HIGH] **Line 26**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 44**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### pages/UserProfile.js
**Score**: 80.0/100 | Critical: 0 | High: 2 | Medium: 0 | Low: 0

[HIGH] **Line 39**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[HIGH] **Line 51**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### pages/WorkflowStagePage.js
**Score**: 80.0/100 | Critical: 0 | High: 0 | Medium: 4 | Low: 0

[MEDIUM] **Line 97**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 105**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 231**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 361**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/MorningCheckin.js
**Score**: 80.0/100 | Critical: 0 | High: 0 | Medium: 4 | Low: 0

[MEDIUM] **Line 189**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 249**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 322**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 357**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/BorrowerOAuthCallback.js
**Score**: 80.0/100 | Critical: 1 | High: 0 | Medium: 0 | Low: 0

[CRITICAL] **Line 25**: Async function makes API calls without try-catch or useAsyncOperation wrapper
- **Fix**: Wrap in try-catch or use useAsyncOperation hook


### pages/MortgagePlannerQuestionnaire.js
**Score**: 80.0/100 | Critical: 0 | High: 0 | Medium: 4 | Low: 0

[MEDIUM] **Line 82**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 96**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 697**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 701**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/BorrowerLogin.js
**Score**: 80.0/100 | Critical: 0 | High: 0 | Medium: 4 | Low: 0

[MEDIUM] **Line 225**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 264**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 62**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 90**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/portal/PortalDocumentRequirements.js
**Score**: 80.0/100 | Critical: 0 | High: 0 | Medium: 4 | Low: 0

[MEDIUM] **Line 167**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 28**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 50**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 71**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/VideoClips/ScheduleMeetingButton.js
**Score**: 80.0/100 | Critical: 0 | High: 0 | Medium: 4 | Low: 0

[MEDIUM] **Line 96**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 122**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 150**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 202**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/JobDescriptionSection.js
**Score**: 85.0/100 | Critical: 0 | High: 0 | Medium: 3 | Low: 0

[MEDIUM] **Line 174**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 55**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 112**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/MicrositeThemeSelector.js
**Score**: 85.0/100 | Critical: 0 | High: 0 | Medium: 3 | Low: 0

[MEDIUM] **Line 35**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 54**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 70**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/CategoryTasksModal.js
**Score**: 85.0/100 | Critical: 0 | High: 0 | Medium: 3 | Low: 0

[MEDIUM] **Line 56**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 97**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 137**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/AdminTemplatePackManagement.js
**Score**: 85.0/100 | Critical: 0 | High: 0 | Medium: 3 | Low: 0

[MEDIUM] **Line 68**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 166**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 197**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/Registration.js
**Score**: 85.0/100 | Critical: 0 | High: 0 | Medium: 3 | Low: 0

[MEDIUM] **Line 101**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 218**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 396**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/AdminSettings.js
**Score**: 85.0/100 | Critical: 0 | High: 1 | Medium: 1 | Low: 0

[HIGH] **Line 1**: Missing required imports: useAsyncOperation
- **Fix**: Add: import { useAsyncOperation } from appropriate paths

[MEDIUM] **Line 14**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/Login.js
**Score**: 85.0/100 | Critical: 0 | High: 0 | Medium: 3 | Low: 0

[MEDIUM] **Line 15**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 45**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 74**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/BetaApplication.js
**Score**: 85.0/100 | Critical: 0 | High: 0 | Medium: 3 | Low: 0

[MEDIUM] **Line 32**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 133**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 296**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/PartnerClientDetail.js
**Score**: 85.0/100 | Critical: 0 | High: 0 | Medium: 3 | Low: 0

[MEDIUM] **Line 311**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 378**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 462**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/microsites/LOMicrosite.js
**Score**: 85.0/100 | Critical: 0 | High: 0 | Medium: 3 | Low: 0

[MEDIUM] **Line 49**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 69**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 93**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/VideoClips/ClipPlayer.js
**Score**: 85.0/100 | Critical: 0 | High: 1 | Medium: 1 | Low: 0

[HIGH] **Line 268**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()

[MEDIUM] **Line 549**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/dialer/DispositionModal.js
**Score**: 85.0/100 | Critical: 0 | High: 0 | Medium: 3 | Low: 0

[MEDIUM] **Line 132**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 339**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 349**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/smart-docs/NeedsListView.js
**Score**: 85.0/100 | Critical: 0 | High: 0 | Medium: 3 | Low: 0

[MEDIUM] **Line 188**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 216**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 288**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/AIReceptionist.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 354**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 386**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/EmbeddedAIChat.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 63**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 136**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/VoiceInput.js
**Score**: 90.0/100 | Critical: 0 | High: 1 | Medium: 0 | Low: 0

[HIGH] **Line 62**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/GoalsOKRsSection.js
**Score**: 90.0/100 | Critical: 0 | High: 1 | Medium: 0 | Low: 0

[HIGH] **Line 70**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/ReviewCallScheduler.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 69**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 135**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/SkillsAssessmentSection.js
**Score**: 90.0/100 | Critical: 0 | High: 1 | Medium: 0 | Low: 0

[HIGH] **Line 72**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/GuidelineUpdatesSidebar.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 18**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 40**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/SMSModal.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 65**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 128**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/EmailComposerModal.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 95**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 146**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/DataUpload.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 72**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 135**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/MyProfile.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 12**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 62**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/ActivateAccount.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 161**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 206**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/BottleneckLoans.js
**Score**: 90.0/100 | Critical: 0 | High: 1 | Medium: 0 | Low: 0

[HIGH] **Line 152**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### pages/AdminActivityFeed.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 42**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 71**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/WorkflowDashboard.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 47**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 60**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/microsites/ThemeRenderer.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 106**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 129**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/microsites/MicrositePreview.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 143**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 163**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### lib/api/hooks.js
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 554**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 319**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/realtor-portal/LoanDetail.js
**Score**: 90.0/100 | Critical: 0 | High: 1 | Medium: 0 | Low: 0

[HIGH] **Line 273**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/profile/PURLWidget.js
**Score**: 90.0/100 | Critical: 0 | High: 1 | Medium: 0 | Low: 0

[HIGH] **Line 156**: Using browser alert() instead of toast notifications
- **Fix**: Replace alert() with toast.success() or toast.error()


### components/portal/MilestoneTimeline.jsx
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 91**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically

[MEDIUM] **Line 328**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/smart-docs/NeedsListView.jsx
**Score**: 90.0/100 | Critical: 0 | High: 0 | Medium: 2 | Low: 0

[MEDIUM] **Line 188**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}

[MEDIUM] **Line 260**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### App.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 227**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### contexts/PermissionContext.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 72**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/GuidelineNotificationBadge.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 17**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/RecordingModal.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 36**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/VoicemailModal.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 62**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/TeamsModal.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 62**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/EmploymentTab.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 15**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/CertificationDueWidget.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 18**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/MortgageStatementUpload.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 59**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/ErrorBoundary.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 110**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/ClickToDialButton.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 31**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/ContentEditor.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 537**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/GlobalSearch.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 42**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/FeatureSelection.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 36**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/WorkflowScorecard.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 48**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/WorkflowUpcomingTasks.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 81**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/OAuthCallback.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 105**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/YearOverYear.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 21**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/CommandCenter.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 18**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/SmartDocsDashboard.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 67**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/WorkflowStatusDetail.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 40**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/Dashboard.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 170**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/MyPermissions.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 262**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### pages/ApplicationAnalytics.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 51**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/RealtorPortal.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 27**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### services/analytics.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 36**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### pages/microsites/ThemePreview.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 197**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/VideoClips/ClipRecorder.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 549**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/Help/HelpPanel.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 252**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### utils/api/client.js
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 94**: Using deprecated pattern: setState before async call
- **Fix**: Use useAsyncOperation hook to handle loading state automatically


### components/portal/ApplicantTasks.jsx
**Score**: 95.0/100 | Critical: 0 | High: 0 | Medium: 1 | Low: 0

[MEDIUM] **Line 427**: Save/submit button does not show loading state
- **Fix**: Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}


### components/ErrorTestButton.js
**Score**: 98.0/100 | Critical: 0 | High: 0 | Medium: 0 | Low: 1

[LOW] **Line 10**: Using deprecated pattern: console.log for errors
- **Fix**: Use logger.error() or proper error tracking


---

## Recommendations

### NOT READY FOR PRODUCTION

**479 critical issues** must be fixed before deployment.
