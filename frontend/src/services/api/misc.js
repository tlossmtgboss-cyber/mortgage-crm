/**
 * Miscellaneous API calls — Partners, MUM, Circle of Cashflow, Profitability,
 * Financial Intelligence, Email, Reconciliation, Applications, PURL, Income,
 * Salesforce, Rate Monitor, Email Drafts, Builder Applications, Guidelines.
 */
import api, { API_BASE_URL, ensureArray } from './client.js';
import axios from 'axios';

// Referral Partners
export const partnersAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/referral-partners', { params });
    return ensureArray(response.data, 'partners');
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/referral-partners/${id}`);
    return response.data;
  },
  getReferrals: async (id) => {
    const response = await api.get(`/api/v1/referral-partners/${id}/referrals`);
    return response.data;
  },
  create: async (data) => {
    const response = await api.post('/api/v1/referral-partners', data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await api.patch(`/api/v1/referral-partners/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/referral-partners/${id}`);
  },
};

// MUM Clients
export const mumAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/mum-clients/', { params });
    return Array.isArray(response.data) ? response.data : response.data.clients || [];
  },
  getMetrics: async () => {
    // Metrics are derived client-side from the MUM clients list
    return null;
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/mum-clients/${id}`);
    return response.data;
  },
  create: async (data) => {
    const response = await api.post('/api/v1/mum-clients/', data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await api.patch(`/api/v1/mum-clients/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/mum-clients/${id}`);
  },

  // Portal management
  getOrCreatePortal: async (clientId) => {
    const response = await api.post(`/api/v1/mum-clients/${clientId}/portal`);
    return response.data;
  },
  getPortalInfo: async (clientId) => {
    const response = await api.get(`/api/v1/mum-clients/${clientId}/portal`);
    return response.data;
  },
  postPortalMessage: async (clientId, content, messageType = 'update') => {
    const response = await api.post(`/api/v1/mum-clients/${clientId}/portal/message`, {
      content,
      message_type: messageType,
    });
    return response.data;
  },
};

// MUM Portal Public API (for client-facing portal)
export const mumPortalAPI = {
  getPortal: async (slug, token = null) => {
    const params = token ? { token } : {};
    const response = await api.get(`/api/v1/mum-portal/${slug}`, { params });
    return response.data;
  },
  getVideos: async (slug, token = null) => {
    const params = token ? { token } : {};
    const response = await api.get(`/api/v1/mum-portal/${slug}/videos`, { params });
    return response.data;
  },
  getDocuments: async (slug, token = null) => {
    const params = token ? { token } : {};
    const response = await api.get(`/api/v1/mum-portal/${slug}/documents`, { params });
    return response.data;
  },
  getMessages: async (slug, token = null, limit = 50) => {
    const params = { limit, ...(token ? { token } : {}) };
    const response = await api.get(`/api/v1/mum-portal/${slug}/messages`, { params });
    return response.data;
  },
  sendHeartbeat: async (slug, page = 'home', token = null) => {
    const response = await api.post(`/api/v1/mum-portal/${slug}/heartbeat`, { page, token });
    return response.data;
  },
  markMessageRead: async (slug, messageId, token = null) => {
    const response = await api.post(`/api/v1/mum-portal/${slug}/messages/${messageId}/read`, { token });
    return response.data;
  },
  markVideoViewed: async (slug, videoId, token = null) => {
    const response = await api.post(`/api/v1/mum-portal/${slug}/videos/${videoId}/viewed`, { token });
    return response.data;
  },
};

// Circle of Cashflow API
export const circleOfCashflowAPI = {
  // Opportunities
  getOpportunities: async (contactId = null) => {
    const params = contactId ? { contact_id: contactId } : {};
    const response = await api.get('/api/v1/circle-of-cashflow/opportunities', { params });
    return response.data;
  },
  acknowledgeOpportunity: async (opportunityId, data) => {
    const response = await api.post(`/api/v1/circle-of-cashflow/opportunities/${opportunityId}/acknowledge`, data);
    return response.data;
  },
  suggestPartner: async (opportunityId) => {
    const response = await api.get(`/api/v1/circle-of-cashflow/opportunities/${opportunityId}/suggest-partner`);
    return response.data;
  },
  sendIntroduction: async (opportunityId, partnerId, method = 'email') => {
    const response = await api.post(`/api/v1/circle-of-cashflow/opportunities/${opportunityId}/send?partner_id=${partnerId}&introduction_method=${method}`);
    return response.data;
  },

  // Partners
  getPartners: async (category = null) => {
    const params = category ? { category } : {};
    const response = await api.get('/api/v1/circle-of-cashflow/partners', { params });
    return response.data;
  },

  // Referrals
  getReferrals: async (contactId = null) => {
    const params = contactId ? { contact_id: contactId } : {};
    const response = await api.get('/api/v1/circle-of-cashflow/referrals', { params });
    return response.data;
  },
  createReferral: async (data) => {
    const response = await api.post('/api/v1/circle-of-cashflow/referrals', data);
    return response.data;
  },

  // Questionnaires
  submitQuestionnaire: async (data) => {
    const response = await api.post('/api/v1/circle-of-cashflow/questionnaires', data);
    return response.data;
  },
  getQuestionnaire: async (id) => {
    const response = await api.get(`/api/v1/circle-of-cashflow/questionnaires/${id}`);
    return response.data;
  },
};

// Profitability Intelligence
export const profitabilityAPI = {
  // Dashboard
  getDashboard: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/dashboard', { params });
    return response.data;
  },
  getMetrics: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/metrics', { params });
    return response.data;
  },
  getTrends: async (months = 12) => {
    const response = await api.get('/api/v1/profitability/trends', { params: { months } });
    return response.data;
  },

  // Expenses
  getExpenses: async (filters = {}) => {
    const response = await api.get('/api/v1/profitability/expenses', { params: filters });
    return response.data;
  },
  createExpense: async (data) => {
    const response = await api.post('/api/v1/profitability/expenses', data);
    return response.data;
  },
  updateExpense: async (id, data) => {
    const response = await api.put(`/api/v1/profitability/expenses/${id}`, data);
    return response.data;
  },
  deleteExpense: async (id) => {
    const response = await api.delete(`/api/v1/profitability/expenses/${id}`);
    return response.data;
  },
  getExpenseCategories: async () => {
    const response = await api.get('/api/v1/profitability/expense-categories');
    return response.data;
  },

  // Roles
  getRoles: async () => {
    const response = await api.get('/api/v1/profitability/roles');
    return response.data;
  },
  createRole: async (data) => {
    const response = await api.post('/api/v1/profitability/roles', data);
    return response.data;
  },
  getRoleProfitability: async (roleId, month = null) => {
    const params = month ? { month } : {};
    const response = await api.get(`/api/v1/profitability/roles/${roleId}/profitability`, { params });
    return response.data;
  },

  // Employees
  getEmployees: async (filters = {}) => {
    const response = await api.get('/api/v1/profitability/employees', { params: filters });
    return response.data;
  },
  createEmployee: async (data) => {
    const response = await api.post('/api/v1/profitability/employees', data);
    return response.data;
  },
  updateEmployee: async (id, data) => {
    const response = await api.put(`/api/v1/profitability/employees/${id}`, data);
    return response.data;
  },
  getEmployeePerformance: async (id, month = null) => {
    const params = month ? { month } : {};
    const response = await api.get(`/api/v1/profitability/employees/${id}/performance`, { params });
    return response.data;
  },

  // Loans
  getLoans: async (filters = {}) => {
    const response = await api.get('/api/v1/profitability/loans', { params: filters });
    return response.data;
  },
  createLoan: async (data) => {
    const response = await api.post('/api/v1/profitability/loans', data);
    return response.data;
  },
  addLoanAttribution: async (loanId, data) => {
    const response = await api.post(`/api/v1/profitability/loans/${loanId}/attributions`, data);
    return response.data;
  },

  // Revenue
  getRevenue: async (filters = {}) => {
    const response = await api.get('/api/v1/profitability/revenue', { params: filters });
    return response.data;
  },
  createRevenue: async (data) => {
    const response = await api.post('/api/v1/profitability/revenue', data);
    return response.data;
  },

  // Scenarios
  getScenarios: async (savedOnly = false) => {
    const response = await api.get('/api/v1/profitability/scenarios', { params: { saved_only: savedOnly } });
    return response.data;
  },
  createScenario: async (data) => {
    const response = await api.post('/api/v1/profitability/scenarios', data);
    return response.data;
  },
  runScenario: async (baseMonth, parameters) => {
    const response = await api.post('/api/v1/profitability/scenarios/run', parameters, {
      params: { base_month: baseMonth }
    });
    return response.data;
  },
  saveScenario: async (id) => {
    const response = await api.put(`/api/v1/profitability/scenarios/${id}/save`);
    return response.data;
  },

  // Snapshots
  getSnapshots: async (limit = 12) => {
    const response = await api.get('/api/v1/profitability/snapshots', { params: { limit } });
    return response.data;
  },
  createSnapshot: async (month) => {
    const response = await api.post('/api/v1/profitability/snapshots', null, { params: { month } });
    return response.data;
  },

  // Insights
  getInsights: async (filters = {}) => {
    const response = await api.get('/api/v1/profitability/insights', { params: filters });
    return response.data;
  },
  generateInsights: async (month) => {
    const response = await api.post('/api/v1/profitability/insights/generate', null, { params: { month } });
    return response.data;
  },
  acknowledgeInsight: async (id) => {
    const response = await api.put(`/api/v1/profitability/insights/${id}/acknowledge`);
    return response.data;
  },

  // Analysis
  getGapsAndGains: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/analysis/gaps-gains', { params });
    return response.data;
  },
  getBreakEvenAnalysis: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/analysis/break-even', { params });
    return response.data;
  },

  // AI Insights
  queryAI: async (question, month = null) => {
    const response = await api.post('/api/v1/profitability/ai/query', { question, month });
    return response.data;
  },
  getAIRecommendations: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/ai/recommendations', { params });
    return response.data;
  },
  analyzeHiring: async (roleName, salary, month = null) => {
    const response = await api.post('/api/v1/profitability/ai/hiring-analysis', {
      role_name: roleName,
      salary: salary,
      month: month
    });
    return response.data;
  },
  getExecutiveDigest: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/ai/executive-digest', { params });
    return response.data;
  },
  getAnomalies: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/ai/anomalies', { params });
    return response.data;
  },
  compareScenarios: async (scenarios, month = null) => {
    const response = await api.post('/api/v1/profitability/ai/compare-scenarios', {
      scenarios: scenarios,
      month: month
    });
    return response.data;
  },
  getQuickInsights: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/ai/quick-insights', { params });
    return response.data;
  },
  getSuggestedQuestions: async () => {
    const response = await api.get('/api/v1/profitability/ai/suggested-questions');
    return response.data;
  },
};

// Financial Intelligence API (Phase 3)
export const financialIntelligenceAPI = {
  getExecutiveDashboard: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/executive-dashboard', { params });
    return response.data;
  },
  getGainOnSale: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/gain-on-sale', { params });
    return response.data;
  },
  getHedgeAnalysis: async () => {
    const response = await api.get('/api/v1/financial-intelligence/hedge-analysis');
    return response.data;
  },
  getProductProfitability: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/product-profitability', { params });
    return response.data;
  },
  getCostPerLoan: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/cost-per-loan', { params });
    return response.data;
  },
  getCashRunway: async () => {
    const response = await api.get('/api/v1/financial-intelligence/cash-runway');
    return response.data;
  },
  getBreakEven: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/break-even', { params });
    return response.data;
  },
  getWarehouseEfficiency: async () => {
    const response = await api.get('/api/v1/financial-intelligence/warehouse-efficiency');
    return response.data;
  },
  getRateExposure: async () => {
    const response = await api.get('/api/v1/financial-intelligence/rate-exposure');
    return response.data;
  },
  getMSRStatus: async () => {
    const response = await api.get('/api/v1/financial-intelligence/msr-status');
    return response.data;
  },
  getPricingAnalysis: async () => {
    const response = await api.get('/api/v1/financial-intelligence/pricing-analysis');
    return response.data;
  },
  getCashForecast: async () => {
    const response = await api.get('/api/v1/financial-intelligence/cash-forecast');
    return response.data;
  },
  getLiquidity: async () => {
    const response = await api.get('/api/v1/financial-intelligence/liquidity');
    return response.data;
  },
  getCapital: async () => {
    const response = await api.get('/api/v1/financial-intelligence/capital');
    return response.data;
  },
  getComplianceRisks: async () => {
    const response = await api.get('/api/v1/financial-intelligence/compliance-risks');
    return response.data;
  },
  getTechROI: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/tech-roi', { params });
    return response.data;
  },
  getOperationalLosses: async () => {
    const response = await api.get('/api/v1/financial-intelligence/operational-losses');
    return response.data;
  },
  getInvestmentRecommendations: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/investment-recommendations', { params });
    return response.data;
  },
};

// Email Signature API
export const emailSignatureAPI = {
  get: async () => {
    const response = await api.get('/api/v1/email-signature');
    return response.data;
  },
  save: async (data) => {
    const response = await api.post('/api/v1/email-signature', data);
    return response.data;
  },
  uploadImage: async (file, imageType) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('image_type', imageType);
    const response = await api.post('/api/v1/email-signature/upload-image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  },
  getHtml: async () => {
    const response = await api.get('/api/v1/email-signature/html');
    return response.data;
  },
  getPreview: async () => {
    const response = await api.get('/api/v1/email-signature/preview');
    return response.data;
  },
};

// Command Center API - Unified Action Items Dashboard
export const commandCenterAPI = {
  // Get all action items across the CRM
  getAll: async () => {
    const response = await api.get('/api/v1/command-center');
    return response.data;
  }
};

// Reconciliation API (AI Engine tasks)
export const reconciliationAPI = {
  // Get pending reconciliation items (optionally filter by status)
  getPending: async (status = null) => {
    const params = status ? { status } : {};
    const response = await api.get('/api/v1/reconciliation/pending', { params });
    return response.data;
  },

  // Delete a reconciliation item
  delete: async (id) => {
    await api.delete(`/api/v1/reconciliation/items/${id}`);
  },

  // Approve a reconciliation item
  approve: async (data) => {
    const response = await api.post('/api/v1/reconciliation/approve', data);
    return response.data;
  },

  // Reject a reconciliation item
  reject: async (data) => {
    const response = await api.post('/api/v1/reconciliation/reject', data);
    return response.data;
  },
};

// Borrower Application API (LO-facing authenticated endpoints)
export const borrowerApplicationAPI = {
  // Create a new borrower application
  create: async (data) => {
    const response = await api.post('/api/v1/applications/', data);
    return response.data;
  },

  // List all applications for current LO
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/applications/', { params });
    return response.data;
  },

  // Get specific application by ID
  getById: async (id) => {
    const response = await api.get(`/api/v1/applications/${id}`);
    return response.data;
  },

  // Get analytics for applications
  getAnalytics: async (days = 30) => {
    const response = await api.get('/api/v1/applications/analytics', { params: { days } });
    return response.data;
  },

  // Generate application link for a lead
  createForLead: async (leadId, options = {}) => {
    const response = await api.post('/api/v1/applications/', {
      lead_id: leadId,
      ...options
    });
    return response.data;
  }
};

// Public Borrower Application API (token-based, no auth required)
export const publicApplicationAPI = {
  // Get application by public token
  get: async (token) => {
    const response = await axios.get(`${API_BASE_URL}/api/v1/apply/${token}`);
    return response.data;
  },

  // Update application data
  update: async (token, data) => {
    const response = await axios.patch(`${API_BASE_URL}/api/v1/apply/${token}`, data);
    return response.data;
  },

  // Save step data
  saveStep: async (token, step, data, markCompleted = false) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/apply/${token}/step`, {
      step,
      data,
      mark_completed: markCompleted
    });
    return response.data;
  },

  // Calculate pre-qualification
  prequalify: async (token, data) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/apply/${token}/prequalify`, data);
    return response.data;
  },

  // Capture credit authorization
  captureCreditAuth: async (token, data) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/apply/${token}/credit-auth`, data);
    return response.data;
  },

  // Submit application
  submit: async (token) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/apply/${token}/submit`);
    return response.data;
  },

  // Upload document
  uploadDocument: async (token, file, category, description) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', category || 'other');
    if (description) formData.append('description', description);

    const response = await axios.post(`${API_BASE_URL}/api/v1/apply/${token}/documents`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  },

  // List documents
  getDocuments: async (token) => {
    const response = await axios.get(`${API_BASE_URL}/api/v1/apply/${token}/documents`);
    return response.data;
  },

  // Delete document
  deleteDocument: async (token, docId) => {
    const response = await axios.delete(`${API_BASE_URL}/api/v1/apply/${token}/documents/${docId}`);
    return response.data;
  },

  // Create co-borrower invitation
  createCoborrowerInvitation: async (token, data) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/apply/${token}/coborrower`, data);
    return response.data;
  }
};

// Co-borrower API (token-based, no auth required)
export const coborrowerAPI = {
  // Get invitation by token
  getInvitation: async (invitationToken) => {
    const response = await axios.get(`${API_BASE_URL}/api/v1/coborrower/${invitationToken}`);
    return response.data;
  },

  // Save co-borrower data
  saveData: async (invitationToken, data) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/coborrower/${invitationToken}/save`, data);
    return response.data;
  },

  // Submit co-borrower section
  submit: async (invitationToken) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/coborrower/${invitationToken}/submit`);
    return response.data;
  },

  // Capture credit authorization
  captureCreditAuth: async (invitationToken, data) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/coborrower/${invitationToken}/credit-auth`, data);
    return response.data;
  }
};

// Public pre-qualification calculator (no auth required)
export const prequalifyAPI = {
  calculate: async (data) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/prequalify`, data);
    return response.data;
  }
};

// PURL (Client Portal) API
export const purlAPI = {
  // Health check for debugging
  healthCheck: async () => {
    try {
      const response = await api.get('/api/v1/purl-admin/health');
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: error.message, details: error.response?.data };
    }
  },

  // Get workspace by lead ID (check if portal exists for this lead)
  getWorkspaceByLead: async (leadId, retryCount = 0) => {
    const maxRetries = 2;
    try {
      const response = await api.get(`/api/v1/purl-admin/workspaces/by-lead/${leadId}`);
      return response.data;
    } catch (error) {
      // Retry on Network Error (transient failures)
      if ((error.retryable || error.message === 'Network Error') && retryCount < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        return purlAPI.getWorkspaceByLead(leadId, retryCount + 1);
      }

      throw error;
    }
  },

  // Get workspace by loan ID
  getWorkspaceByLoan: async (loanId, retryCount = 0) => {
    const maxRetries = 2;
    try {
      const response = await api.get(`/api/v1/purl-admin/workspaces/by-loan/${loanId}`);
      return response.data;
    } catch (error) {
      if ((error.retryable || error.message === 'Network Error') && retryCount < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        return purlAPI.getWorkspaceByLoan(loanId, retryCount + 1);
      }
      throw error;
    }
  },

  // Create new workspace (portal) for a lead/loan
  createWorkspace: async (data, retryCount = 0) => {
    const maxRetries = 2;
    try {
      const response = await api.post('/api/v1/purl-admin/workspaces', data);
      return response.data;
    } catch (error) {
      if ((error.retryable || error.message === 'Network Error') && retryCount < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        return purlAPI.createWorkspace(data, retryCount + 1);
      }

      throw error;
    }
  },

  // Get workspace details
  getWorkspace: async (workspaceId) => {
    const response = await api.get(`/api/v1/purl-admin/workspaces/${workspaceId}`);
    return response.data;
  },

  // Get full PURL URL with active token
  getPurlUrl: async (workspaceId) => {
    const response = await api.get(`/api/v1/purl-admin/workspaces/${workspaceId}/purl-url`);
    return response.data;
  },

  // Create access token for workspace
  createToken: async (workspaceId, data = {}) => {
    const response = await api.post(`/api/v1/purl-admin/workspaces/${workspaceId}/tokens`, data);
    return response.data;
  },

  // Resend portal invitation
  resendInvite: async (workspaceId) => {
    const response = await api.post(`/api/v1/purl-admin/workspaces/${workspaceId}/resend-invite`);
    return response.data;
  },

  // List all workspaces (for admin dashboard)
  listWorkspaces: async (params = {}) => {
    const response = await api.get('/api/v1/purl-admin/workspaces', { params });
    return response.data;
  },

  // Get PURL metrics
  getMetrics: async () => {
    const response = await api.get('/api/v1/purl-admin/metrics');
    return response.data;
  }
};

// Income Engine API
export const incomeAPI = {
  // Get supported income types
  getSupportedTypes: async () => {
    const response = await api.get('/api/v1/income/supported-types');
    return response.data;
  },

  // Calculate income from document facts
  calculate: async (data) => {
    const response = await api.post('/api/v1/income/calculate', data);
    return response.data;
  },

  // Validate documents for calculation
  validateDocuments: async (data) => {
    const response = await api.post('/api/v1/income/validate-documents', data);
    return response.data;
  },

  // Get income summary for a loan
  getLoanSummary: async (loanId, borrowerId = 1) => {
    const response = await api.get(`/api/v1/income/loan/${loanId}/summary`, {
      params: { borrower_id: borrowerId }
    });
    return response.data;
  },

  // Get income streams for a loan
  getLoanStreams: async (loanId, borrowerId = 1) => {
    const response = await api.get(`/api/v1/income/loan/${loanId}/streams`, {
      params: { borrower_id: borrowerId }
    });
    return response.data;
  },

  // Get income flags for a loan
  getLoanFlags: async (loanId, borrowerId = 1, severity = null) => {
    const params = { borrower_id: borrowerId };
    if (severity) params.severity = severity;
    const response = await api.get(`/api/v1/income/loan/${loanId}/flags`, { params });
    return response.data;
  },

  // Resolve an income flag
  resolveFlag: async (loanId, flagId, resolutionNote = '', resolvedBy = null) => {
    const response = await api.post(`/api/v1/income/loan/${loanId}/flags/${flagId}/resolve`, null, {
      params: { resolution_note: resolutionNote, resolved_by: resolvedBy }
    });
    return response.data;
  },

  // Get income worksheets
  getWorksheets: async (loanId, borrowerId = 1, worksheetType = null) => {
    const params = { borrower_id: borrowerId };
    if (worksheetType) params.worksheet_type = worksheetType;
    const response = await api.get(`/api/v1/income/loan/${loanId}/worksheets`, { params });
    return response.data;
  },
};

// Salesforce Integration API
export const salesforceAPI = {
  // Get connection status
  getStatus: async () => {
    const response = await api.get('/api/v1/salesforce/status');
    return response.data;
  },

  // Connect to Salesforce (returns auth URL)
  connect: async (redirectUrl = null) => {
    const params = redirectUrl ? { redirect_url: redirectUrl } : {};
    const response = await api.get('/api/v1/salesforce/connect', { params });
    return response.data;
  },

  // Disconnect from Salesforce
  disconnect: async () => {
    const response = await api.delete('/api/v1/salesforce/disconnect');
    return response.data;
  },

  // Test connection
  testConnection: async () => {
    const response = await api.get('/api/v1/salesforce/test-connection');
    return response.data;
  },

  // Push single loan to Salesforce
  pushLoan: async (loanId, sfObject = null) => {
    const params = sfObject ? { sf_object: sfObject } : {};
    const response = await api.post(`/api/v1/salesforce/push/loan/${loanId}`, null, { params });
    return response.data;
  },

  // Push multiple loans to Salesforce
  pushBatch: async (loanIds, sfObject = null) => {
    const response = await api.post('/api/v1/salesforce/push/batch', {
      loan_ids: loanIds,
      sf_object: sfObject || 'MtgPlanner_CRM__Transaction_Property__c'
    });
    return response.data;
  },

  // Get loans pending push
  getPendingLoans: async (limit = 50) => {
    const response = await api.get('/api/v1/salesforce/push/pending', { params: { limit } });
    return response.data;
  },

  // Get sync status for a loan
  getLoanSyncStatus: async (loanId) => {
    const response = await api.get(`/api/v1/salesforce/loan/${loanId}/sync-status`);
    return response.data;
  },

  // Pull/refresh single loan from Salesforce
  pullLoan: async (loanId, sfObject = null) => {
    const params = sfObject ? { sf_object: sfObject } : {};
    const response = await api.post(`/api/v1/salesforce/pull/loan/${loanId}`, null, { params });
    return response.data;
  },

  // Full sync from Salesforce
  fullSync: async () => {
    const response = await api.post('/api/v1/salesforce/sync/full');
    return response.data;
  },

  // Sync ALL loans from Salesforce (links unlinked loans and pulls all data)
  syncAllLoans: async () => {
    const response = await api.post('/api/v1/salesforce/sync-all-loans');
    return response.data;
  },

  // Get sync history
  getSyncHistory: async (limit = 20) => {
    const response = await api.get('/api/v1/salesforce/sync/history', { params: { limit } });
    return response.data;
  },

  // Import closed loans
  importClosedLoans: async () => {
    const response = await api.post('/api/v1/salesforce/import-closed-loans');
    return response.data;
  },

  // Get field mappings
  getMappings: async () => {
    const response = await api.get('/api/v1/salesforce/mappings');
    return response.data;
  },

  // Save field mapping
  saveMapping: async (mapping) => {
    const response = await api.post('/api/v1/salesforce/mappings', mapping);
    return response.data;
  },

  // Explore objects
  getObjects: async () => {
    const response = await api.get('/api/v1/salesforce/explore/objects');
    return response.data;
  },

  // Get object fields
  getObjectFields: async (objectName) => {
    const response = await api.get(`/api/v1/salesforce/explore/objects/${objectName}`);
    return response.data;
  },
};

// Rate Monitor API
export const rateMonitorAPI = {
  // Dashboard
  getDashboard: async () => {
    const response = await api.get('/api/v1/rate-monitor/dashboard');
    return response.data;
  },

  // Current rates
  getCurrentRates: async (params = {}) => {
    const response = await api.get('/api/v1/rate-monitor/current-rates', { params });
    return response.data;
  },

  // Targets
  getTargets: async (params = {}) => {
    const response = await api.get('/api/v1/rate-monitor/targets', { params });
    return response.data;
  },

  getTarget: async (targetId) => {
    const response = await api.get(`/api/v1/rate-monitor/targets/${targetId}`);
    return response.data;
  },

  createTarget: async (data) => {
    const response = await api.post('/api/v1/rate-monitor/targets', data);
    return response.data;
  },

  updateTarget: async (targetId, data) => {
    const response = await api.patch(`/api/v1/rate-monitor/targets/${targetId}`, data);
    return response.data;
  },

  deleteTarget: async (targetId) => {
    const response = await api.delete(`/api/v1/rate-monitor/targets/${targetId}`);
    return response.data;
  },

  // Check opportunity for a MUM client
  checkOpportunity: async (mumClientId, params = {}) => {
    const response = await api.post(`/api/v1/rate-monitor/check-opportunity/${mumClientId}`, params);
    return response.data;
  },

  // Alerts
  getAlerts: async (params = {}) => {
    const response = await api.get('/api/v1/rate-monitor/alerts', { params });
    return response.data;
  },

  getAlert: async (alertId) => {
    const response = await api.get(`/api/v1/rate-monitor/alerts/${alertId}`);
    return response.data;
  },

  updateAlert: async (alertId, data) => {
    const response = await api.patch(`/api/v1/rate-monitor/alerts/${alertId}`, data);
    return response.data;
  },

  initiateCall: async (alertId, data = {}) => {
    const response = await api.post(`/api/v1/rate-monitor/alerts/${alertId}/initiate-call`, data);
    return response.data;
  },

  // History
  getHistory: async (params = {}) => {
    const response = await api.get('/api/v1/rate-monitor/history', { params });
    return response.data;
  },
};

// Rate Sheet API (Rate Sheet Upload & Refinance Opportunities)
export const rateSheetAPI = {
  // Rate Sheets
  uploadSheet: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/api/v1/rate-monitor/sheets/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  getSheets: async (params = {}) => {
    const response = await api.get('/api/v1/rate-monitor/sheets', { params });
    return response.data;
  },

  getSheet: async (sheetId) => {
    const response = await api.get(`/api/v1/rate-monitor/sheets/${sheetId}`);
    return response.data;
  },

  getSheetRates: async (sheetId, params = {}) => {
    const response = await api.get(`/api/v1/rate-monitor/sheets/${sheetId}/rates`, { params });
    return response.data;
  },

  deleteSheet: async (sheetId) => {
    const response = await api.delete(`/api/v1/rate-monitor/sheets/${sheetId}`);
    return response.data;
  },

  scanForOpportunities: async (sheetId, data = {}) => {
    const response = await api.post(`/api/v1/rate-monitor/sheets/${sheetId}/scan`, data);
    return response.data;
  },

  // Opportunities
  getOpportunities: async (params = {}) => {
    const response = await api.get('/api/v1/rate-monitor/opportunities', { params });
    return response.data;
  },

  getOpportunitiesDashboard: async () => {
    const response = await api.get('/api/v1/rate-monitor/opportunities/dashboard');
    return response.data;
  },

  getOpportunity: async (opportunityId) => {
    const response = await api.get(`/api/v1/rate-monitor/opportunities/${opportunityId}`);
    return response.data;
  },

  updateOpportunity: async (opportunityId, data) => {
    const response = await api.patch(`/api/v1/rate-monitor/opportunities/${opportunityId}`, data);
    return response.data;
  },

  // Outreach
  triggerOutreach: async (opportunityId, data = {}) => {
    const response = await api.post(`/api/v1/rate-monitor/opportunities/${opportunityId}/outreach`, data);
    return response.data;
  },

  sendSMS: async (opportunityId) => {
    const response = await api.post(`/api/v1/rate-monitor/opportunities/${opportunityId}/sms`);
    return response.data;
  },

  initiateCall: async (opportunityId, customMessage = null) => {
    const response = await api.post(`/api/v1/rate-monitor/opportunities/${opportunityId}/call`, null, {
      params: customMessage ? { custom_message: customMessage } : {},
    });
    return response.data;
  },

  bulkOutreach: async (opportunityIds, skipSms = false) => {
    const response = await api.post('/api/v1/rate-monitor/opportunities/bulk-outreach', {
      opportunity_ids: opportunityIds,
      skip_sms: skipSms,
    });
    return response.data;
  },

  markOptedOut: async (opportunityId) => {
    const response = await api.post(`/api/v1/rate-monitor/opportunities/${opportunityId}/opt-out`);
    return response.data;
  },

  markConverted: async (opportunityId, notes = null) => {
    const response = await api.post(`/api/v1/rate-monitor/opportunities/${opportunityId}/convert`, null, {
      params: notes ? { notes } : {},
    });
    return response.data;
  },
};

// Email Drafts API
export const emailDraftsAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/email-drafts', { params });
    return response.data;
  },

  getCallDrafts: async () => {
    const response = await api.get('/api/v1/email-drafts', {
      params: { source_type: 'call_recording', status: 'draft' }
    });
    return response.data.drafts || [];
  },

  getById: async (id) => {
    const response = await api.get(`/api/v1/email-drafts/${id}`);
    return response.data;
  },

  update: async (id, data) => {
    const response = await api.put(`/api/v1/email-drafts/${id}`, data);
    return response.data;
  },

  send: async (id) => {
    const response = await api.post(`/api/v1/email-drafts/${id}/send`);
    return response.data;
  },

  delete: async (id) => {
    const response = await api.delete(`/api/v1/email-drafts/${id}`);
    return response.data;
  },
};

// Builder Applications API
export const builderApplicationsAPI = {
  list: async (params = {}) => {
    const response = await api.get('/api/v1/builder-applications', { params });
    return response.data;
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/builder-applications/${id}`);
    return response.data;
  },
  getDownloadUrl: async (appId, docId) => {
    const response = await api.get(`/api/v1/builder-applications/${appId}/documents/${docId}/download`);
    return response.data;
  },
  review: async (appId, data) => {
    const response = await api.patch(`/api/v1/builder-applications/${appId}/review`, data);
    return response.data;
  },
};

// Underwriting Guidelines API
export const guidelinesAPI = {
  search: (query, filters = {}) =>
    api.post('/api/v1/underwriting-guidelines/search/rag', { query, ...filters }),
  compare: (topic) =>
    api.get(`/api/v1/underwriting-guidelines/compare/${topic}`),
  stats: () =>
    api.get('/api/v1/underwriting-guidelines/stats'),
  list: (params = {}) =>
    api.get('/api/v1/underwriting-guidelines', { params }),
  upload: (formData) =>
    api.post('/api/v1/underwriting-guidelines/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000, // 5 minutes for large guideline PDFs
    }),
  chartCatalog: () =>
    api.get('/api/v1/underwriting-guidelines/compare/catalog'),
  saveQuery: (name, query, filters) =>
    api.post('/api/v1/underwriting-guidelines/library', { name, query, filters }),
  listSavedQueries: () =>
    api.get('/api/v1/underwriting-guidelines/library'),
};
