/**
 * Tasks API calls.
 */
import api, { ensureArray } from './client.js';

// Tasks
export const tasksAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/tasks', { params });
    return ensureArray(response.data, 'tasks');
  },
  getUnified: async () => {
    const response = await api.get('/api/v1/unified-tasks');
    return response.data;
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/tasks/${id}`);
    return response.data;
  },
  create: async (data) => {
    const response = await api.post('/api/v1/tasks', data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await api.patch(`/api/v1/tasks/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/tasks/${id}`);
  },
  delegate: async (id, delegateToId) => {
    const response = await api.post(`/api/v1/tasks/${id}/delegate`, { delegate_to_id: delegateToId });
    return response.data;
  },
};

// Activities
export const activitiesAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/activities/', { params });
    return ensureArray(response.data, 'activities');
  },
  create: async (data) => {
    const response = await api.post('/api/v1/activities/', data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/activities/${id}`);
  },
};
