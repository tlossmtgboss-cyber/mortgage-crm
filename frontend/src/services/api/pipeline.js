/**
 * Dashboard, Analytics, and Portfolio API calls.
 */
import api, { ensureArray } from './client.js';

// Dashboard
export const dashboardAPI = {
  getDashboard: async () => {
    const response = await api.get('/api/v1/dashboard');
    return response.data;
  },
};

// Analytics
export const analyticsAPI = {
  getConversionFunnel: async () => {
    const response = await api.get('/api/v1/analytics/conversion-funnel');
    return response.data;
  },
  getPipeline: async () => {
    const response = await api.get('/api/v1/analytics/pipeline');
    return response.data;
  },
  getScorecard: async () => {
    const response = await api.get('/api/v1/scorecard');
    return response.data;
  },
};

// Portfolio
export const portfolioAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/portfolio/', { params });
    return ensureArray(response.data, 'portfolio');
  },
  getStats: async () => {
    const response = await api.get('/api/v1/portfolio/stats');
    return response.data;
  },
};
