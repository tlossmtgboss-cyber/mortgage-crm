// ─────────────────────────────────────────────────────────────
// URLA CALL INTELLIGENCE API SERVICE
// src/services/urlaCallIntelligenceApi.js
// ─────────────────────────────────────────────────────────────

import api from './api';

export const urlaCallIntelligenceApi = {

  // ── Trigger URLA analysis for a loan's call recordings ────
  async analyzeCall(loanId) {
    try {
      const response = await api.post(`/api/v1/urla/calls/${loanId}/analyze`);
      return response.data;
    } catch (error) {
      console.error('[UrlaCallIntelligence] analyzeCall error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to analyze call';
      throw new Error(errMsg);
    }
  },

  // ── Get full intelligence report for a loan ───────────────
  async getCallIntelligence(loanId) {
    try {
      const response = await api.get(`/api/v1/urla/calls/${loanId}/intelligence`);
      return response.data;
    } catch (error) {
      console.error('[UrlaCallIntelligence] getCallIntelligence error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to get call intelligence';
      throw new Error(errMsg);
    }
  },

  // ── Get LO briefing (JSON) ────────────────────────────────
  async getLOBriefing(loanId) {
    try {
      const response = await api.get(`/api/v1/urla/calls/${loanId}/briefing`);
      return response.data;
    } catch (error) {
      console.error('[UrlaCallIntelligence] getLOBriefing error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to get LO briefing';
      throw new Error(errMsg);
    }
  },

  // ── Get LO briefing (rendered HTML) ───────────────────────
  async getLOBriefingHtml(loanId) {
    try {
      const response = await api.get(`/api/v1/urla/calls/${loanId}/briefing/html`);
      return response.data;
    } catch (error) {
      console.error('[UrlaCallIntelligence] getLOBriefingHtml error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to get LO briefing HTML';
      throw new Error(errMsg);
    }
  },

  // ── Get call quality/compliance score ─────────────────────
  async getCallScore(loanId) {
    try {
      const response = await api.get(`/api/v1/urla/calls/${loanId}/score`);
      return response.data;
    } catch (error) {
      console.error('[UrlaCallIntelligence] getCallScore error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to get call score';
      throw new Error(errMsg);
    }
  },

  // ── Get extracted tasks from call ─────────────────────────
  async getCallTasks(loanId) {
    try {
      const response = await api.get(`/api/v1/urla/calls/${loanId}/tasks`);
      return response.data;
    } catch (error) {
      console.error('[UrlaCallIntelligence] getCallTasks error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to get call tasks';
      throw new Error(errMsg);
    }
  },

  // ── Push extracted tasks into CRM task system ─────────────
  async pushTasksToCrm(loanId) {
    try {
      const response = await api.post(`/api/v1/urla/calls/${loanId}/tasks/push-to-crm`);
      return response.data;
    } catch (error) {
      console.error('[UrlaCallIntelligence] pushTasksToCrm error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to push tasks to CRM';
      throw new Error(errMsg);
    }
  },

  // ── Get URLA analytics for a date range ───────────────────
  async getAnalytics(startDate, endDate) {
    try {
      const response = await api.get('/api/v1/urla/analytics', {
        params: { start_date: startDate, end_date: endDate },
      });
      return response.data;
    } catch (error) {
      console.error('[UrlaCallIntelligence] getAnalytics error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to get analytics';
      throw new Error(errMsg);
    }
  },

  // ── List URLA sessions with optional filters ──────────────
  async listSessions(params = {}) {
    try {
      const response = await api.get('/api/v1/urla/sessions', {
        params: {
          limit: params.limit || 20,
          ...(params.status && { status: params.status }),
        },
      });
      return response.data;
    } catch (error) {
      console.error('[UrlaCallIntelligence] listSessions error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to list sessions';
      throw new Error(errMsg);
    }
  },

  // ── Get call transcript for a loan ────────────────────────
  async getTranscript(loanId) {
    try {
      const response = await api.get(`/api/v1/urla/calls/${loanId}/transcript`);
      return response.data;
    } catch (error) {
      console.error('[UrlaCallIntelligence] getTranscript error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to get transcript';
      throw new Error(errMsg);
    }
  },
};
