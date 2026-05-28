/**
 * Leads API calls.
 */
import api, { ensureArray } from './client.js';

// Leads
export const leadsAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/leads/', { params });
    return ensureArray(response.data, 'leads');
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/leads/${id}`);
    return response.data;
  },
  create: async (data) => {
    const response = await api.post('/api/v1/leads/', data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await api.patch(`/api/v1/leads/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    const maxRetries = 2;
    let lastError;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        await api.delete(`/api/v1/leads/${id}`);
        return;
      } catch (error) {
        lastError = error;
        if ((error.retryable || error.message === 'Network Error') && attempt < maxRetries) {
          await new Promise(resolve => setTimeout(resolve, 1000));
          continue;
        }
        throw error;
      }
    }
    throw lastError;
  },
  bulkDelete: async (leadIds) => {
    const maxRetries = 2;
    let lastError;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const response = await api.post('/api/v1/leads/bulk-delete', leadIds);
        return response.data;
      } catch (error) {
        lastError = error;
        if ((error.retryable || error.message === 'Network Error') && attempt < maxRetries) {
          await new Promise(resolve => setTimeout(resolve, 1000));
          continue;
        }
        throw error;
      }
    }
    throw lastError;
  },
  bulkUpdateStatus: async (leadIds, status) => {
    const maxRetries = 2;
    let lastError;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const response = await api.post('/api/v1/leads/bulk-update-status', {
          lead_ids: leadIds,
          status: status
        });
        return response.data;
      } catch (error) {
        lastError = error;
        if ((error.retryable || error.message === 'Network Error') && attempt < maxRetries) {
          await new Promise(resolve => setTimeout(resolve, 1000));
          continue;
        }
        throw error;
      }
    }
    throw lastError;
  },
  getDocuments: async (leadId) => {
    const response = await api.get(`/api/v1/leads/${leadId}/documents`);
    return response.data;
  },
};
