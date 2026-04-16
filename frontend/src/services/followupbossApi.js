/**
 * Follow Up Boss Integration API Service
 *
 * Handles all API calls to the Follow Up Boss integration backend endpoints.
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
// CONNECTION MANAGEMENT
// =============================================================================

export const connectionApi = {
  /**
   * Connect Follow Up Boss account with API key
   */
  connect: (apiKey) =>
    apiRequest('/api/v1/integrations/followupboss/connect', {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey }),
    }),

  /**
   * Disconnect Follow Up Boss account
   */
  disconnect: () =>
    apiRequest('/api/v1/integrations/followupboss/disconnect', {
      method: 'DELETE',
    }),

  /**
   * Get connection status
   */
  getStatus: () =>
    apiRequest('/api/v1/integrations/followupboss/status'),

  /**
   * Verify API connection is still valid
   */
  verify: () =>
    apiRequest('/api/v1/integrations/followupboss/verify'),

  /**
   * Get webhook URL for FUB configuration
   */
  getWebhookUrl: () =>
    apiRequest('/api/v1/integrations/followupboss/webhook-url'),
};

// =============================================================================
// SYNC SETTINGS
// =============================================================================

export const settingsApi = {
  /**
   * Update sync settings
   */
  updateSettings: (settings) =>
    apiRequest('/api/v1/integrations/followupboss/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),
};

// =============================================================================
// STAGE MAPPINGS
// =============================================================================

export const stageMappingApi = {
  /**
   * Get stage mappings between FUB and CRM
   */
  getMappings: () =>
    apiRequest('/api/v1/integrations/followupboss/stage-mappings'),

  /**
   * Update stage mappings
   */
  updateMappings: (mappings) =>
    apiRequest('/api/v1/integrations/followupboss/stage-mappings', {
      method: 'PUT',
      body: JSON.stringify({ mappings }),
    }),

  /**
   * Refresh stages from FUB
   */
  refreshStages: () =>
    apiRequest('/api/v1/integrations/followupboss/stage-mappings/refresh', {
      method: 'POST',
    }),
};

// =============================================================================
// SYNC OPERATIONS
// =============================================================================

export const syncApi = {
  /**
   * Trigger manual sync from FUB
   */
  triggerSync: (limit = 100) =>
    apiRequest(`/api/v1/integrations/followupboss/sync?limit=${limit}`, {
      method: 'POST',
    }),

  /**
   * Get sync history
   */
  getHistory: (limit = 50, offset = 0, status = null) => {
    let url = `/api/v1/integrations/followupboss/sync-history?limit=${limit}&offset=${offset}`;
    if (status) url += `&status=${status}`;
    return apiRequest(url);
  },
};

// =============================================================================
// LEAD MAPPINGS
// =============================================================================

export const leadMappingApi = {
  /**
   * Get lead mappings between FUB and CRM
   */
  getMappings: (limit = 50, offset = 0) =>
    apiRequest(`/api/v1/integrations/followupboss/lead-mappings?limit=${limit}&offset=${offset}`),

  /**
   * Delete a specific lead mapping
   */
  deleteMapping: (mappingId) =>
    apiRequest(`/api/v1/integrations/followupboss/lead-mappings/${mappingId}`, {
      method: 'DELETE',
    }),
};

// =============================================================================
// EXPORT DEFAULT
// =============================================================================

export default {
  connection: connectionApi,
  settings: settingsApi,
  stageMapping: stageMappingApi,
  sync: syncApi,
  leadMapping: leadMappingApi,
};
