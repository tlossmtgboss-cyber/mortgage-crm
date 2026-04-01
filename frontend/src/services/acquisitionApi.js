/**
 * Acquisition Engine API Service
 * Handles all API calls for the Client Acquisition Engine
 */

// Use shared api instance for CSRF, auth, and impersonation support
import api from './api';

/**
 * Acquisition Engine API
 */
export const acquisitionAPI = {
  // ==========================================================================
  // DASHBOARD
  // ==========================================================================

  /**
   * Get acquisition dashboard data
   */
  getDashboard: async () => {
    const response = await api.get('/api/v1/acquisition/dashboard');
    return response.data;
  },

  // ==========================================================================
  // CAMPAIGNS
  // ==========================================================================

  /**
   * Launch a new campaign
   */
  launchCampaign: async (campaignData) => {
    const response = await api.post('/api/v1/acquisition/campaigns/launch', campaignData);
    return response.data;
  },

  /**
   * Get all campaigns
   */
  getCampaigns: async (params = {}) => {
    const response = await api.get('/api/v1/acquisition/campaigns', { params });
    return response.data;
  },

  /**
   * Get a specific campaign
   */
  getCampaign: async (campaignId) => {
    const response = await api.get(`/api/v1/acquisition/campaigns/${campaignId}`);
    return response.data;
  },

  /**
   * Pause a campaign
   */
  pauseCampaign: async (campaignId) => {
    const response = await api.post(`/api/v1/acquisition/campaigns/${campaignId}/pause`);
    return response.data;
  },

  /**
   * Resume a campaign
   */
  resumeCampaign: async (campaignId) => {
    const response = await api.post(`/api/v1/acquisition/campaigns/${campaignId}/resume`);
    return response.data;
  },

  // ==========================================================================
  // BLUEPRINTS
  // ==========================================================================

  /**
   * Get available campaign blueprints
   */
  getBlueprints: async (goalType = null) => {
    const params = goalType ? { goal_type: goalType } : {};
    const response = await api.get('/api/v1/acquisition/blueprints', { params });
    return response.data;
  },

  // ==========================================================================
  // EVENTS
  // ==========================================================================

  /**
   * Ingest a new event
   */
  ingestEvent: async (eventData) => {
    const response = await api.post('/api/v1/acquisition/events', eventData);
    return response.data;
  },

  /**
   * Get events for a lead
   */
  getLeadEvents: async (leadId, limit = 50) => {
    const response = await api.get(`/api/v1/acquisition/events/${leadId}`, {
      params: { limit }
    });
    return response.data;
  },

  // ==========================================================================
  // TEMPERATURE
  // ==========================================================================

  /**
   * Get lead temperature
   */
  getLeadTemperature: async (leadId) => {
    const response = await api.get(`/api/v1/acquisition/temperature/${leadId}`);
    return response.data;
  },

  /**
   * Get all hot leads
   */
  getHotLeads: async (campaignId = null, limit = 50) => {
    const params = { limit };
    if (campaignId) params.campaign_id = campaignId;
    const response = await api.get('/api/v1/acquisition/temperature/hot', { params });
    return response.data;
  },

  // ==========================================================================
  // SPEED-TO-LEAD
  // ==========================================================================

  /**
   * Get speed-to-lead metrics
   */
  getSpeedToLeadMetrics: async (campaignId = null, days = 30) => {
    const params = { days };
    if (campaignId) params.campaign_id = campaignId;
    const response = await api.get('/api/v1/acquisition/speed-to-lead', { params });
    return response.data;
  },

  /**
   * Trigger speed-to-lead for a lead
   */
  triggerSpeedToLead: async (leadId, options = {}) => {
    const response = await api.post(`/api/v1/acquisition/speed-to-lead/${leadId}/trigger`, options);
    return response.data;
  },

  /**
   * Get detailed speed-to-lead metrics for a campaign
   */
  getSpeedToLeadDetailed: async (campaignId, days = 7) => {
    const response = await api.get(`/api/v1/acquisition/speed-to-lead/${campaignId}/detailed`, {
      params: { days }
    });
    return response.data;
  },

  // ==========================================================================
  // CONVERSIONS
  // ==========================================================================

  /**
   * Track a conversion
   */
  trackConversion: async (conversionData) => {
    const response = await api.post('/api/v1/acquisition/conversions', conversionData);
    return response.data;
  },

  /**
   * Get conversions for a lead
   */
  getLeadConversions: async (leadId) => {
    const response = await api.get(`/api/v1/acquisition/conversions/${leadId}`);
    return response.data;
  },

  // ==========================================================================
  // FUNNEL
  // ==========================================================================

  /**
   * Get funnel metrics
   */
  getFunnelMetrics: async (campaignId = null, days = 30) => {
    const params = { days };
    if (campaignId) params.campaign_id = campaignId;
    const response = await api.get('/api/v1/acquisition/funnel', { params });
    return response.data;
  },

  /**
   * Get campaign-specific funnel
   */
  getCampaignFunnel: async (campaignId, days = 30) => {
    const response = await api.get(`/api/v1/acquisition/funnel/${campaignId}`, {
      params: { days }
    });
    return response.data;
  },

  // ==========================================================================
  // ATTRIBUTION
  // ==========================================================================

  /**
   * Get attribution report
   */
  getAttributionReport: async (campaignId = null, days = 30) => {
    const params = { days };
    if (campaignId) params.campaign_id = campaignId;
    const response = await api.get('/api/v1/acquisition/attribution', { params });
    return response.data;
  },
};

export default acquisitionAPI;
