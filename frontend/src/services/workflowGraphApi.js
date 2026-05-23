import api from './api';

export const workflowGraphApi = {
  // Definitions
  listDefinitions: (includeInactive = false) =>
    api.get(`/api/v1/workflow/definitions?include_inactive=${includeInactive}`),

  createDefinition: (data) =>
    api.post('/api/v1/workflow/definitions', data),

  updateDefinition: (id, data) =>
    api.put(`/api/v1/workflow/definitions/${id}`, data),

  deleteDefinition: (id) =>
    api.delete(`/api/v1/workflow/definitions/${id}`),

  reorderDefinitions: (orderedIds) =>
    api.put('/api/v1/workflow/definitions/reorder', { ordered_ids: orderedIds }),

  // Graph
  getGraph: (workflowKey) =>
    api.get(`/api/v1/workflow/${workflowKey}/graph`),

  // Nodes
  addNode: (workflowKey, data) =>
    api.post(`/api/v1/workflow/${workflowKey}/nodes`, data),

  updateNode: (workflowKey, nodeId, data) =>
    api.put(`/api/v1/workflow/${workflowKey}/nodes/${nodeId}`, data),

  deleteNode: (workflowKey, nodeId) =>
    api.delete(`/api/v1/workflow/${workflowKey}/nodes/${nodeId}`),

  bulkUpdatePositions: (workflowKey, positions) =>
    api.put(`/api/v1/workflow/${workflowKey}/nodes/positions`, { positions }),

  // Edges
  addEdge: (workflowKey, data) =>
    api.post(`/api/v1/workflow/${workflowKey}/edges`, data),

  deleteEdge: (workflowKey, edgeId) =>
    api.delete(`/api/v1/workflow/${workflowKey}/edges/${edgeId}`),

  // Live Data
  getNodeLeads: (workflowKey, nodeId, page = 1, perPage = 20) =>
    api.get(`/api/v1/workflow/${workflowKey}/nodes/${nodeId}/leads?page=${page}&per_page=${perPage}`),

  getNodeHistory: (workflowKey, nodeId, limit = 50) =>
    api.get(`/api/v1/workflow/${workflowKey}/nodes/${nodeId}/history?limit=${limit}`),

  getNodeMetrics: (workflowKey, nodeId) =>
    api.get(`/api/v1/workflow/${workflowKey}/nodes/${nodeId}/metrics`),

  // AI Review Loop (supervised mode)
  getPendingAIActions: (workflowKey) =>
    api.get(`/api/v1/workflow/${workflowKey}/ai-actions/pending`),

  submitAIReview: (workflowKey, actionId, data) =>
    api.post(`/api/v1/workflow/${workflowKey}/ai-actions/${actionId}/review`, data),
};
