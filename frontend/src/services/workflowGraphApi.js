import api from './api';

export const workflowGraphApi = {
  // Definitions
  listDefinitions: (includeInactive = false) =>
    api.get(`/api/v1/workflow-builder/definitions?include_inactive=${includeInactive}`),

  createDefinition: (data) =>
    api.post('/api/v1/workflow-builder/definitions', data),

  updateDefinition: (id, data) =>
    api.put(`/api/v1/workflow-builder/definitions/${id}`, data),

  deleteDefinition: (id) =>
    api.delete(`/api/v1/workflow-builder/definitions/${id}`),

  reorderDefinitions: (orderedIds) =>
    api.put('/api/v1/workflow-builder/definitions/reorder', { ordered_ids: orderedIds }),

  // Graph
  getGraph: (workflowKey) =>
    api.get(`/api/v1/workflow-builder/${workflowKey}/graph`),

  // Nodes
  addNode: (workflowKey, data) =>
    api.post(`/api/v1/workflow-builder/${workflowKey}/nodes`, data),

  updateNode: (workflowKey, nodeId, data) =>
    api.put(`/api/v1/workflow-builder/${workflowKey}/nodes/${nodeId}`, data),

  deleteNode: (workflowKey, nodeId) =>
    api.delete(`/api/v1/workflow-builder/${workflowKey}/nodes/${nodeId}`),

  bulkUpdatePositions: (workflowKey, positions) =>
    api.put(`/api/v1/workflow-builder/${workflowKey}/nodes/positions`, { positions }),

  // Edges
  addEdge: (workflowKey, data) =>
    api.post(`/api/v1/workflow-builder/${workflowKey}/edges`, data),

  deleteEdge: (workflowKey, edgeId) =>
    api.delete(`/api/v1/workflow-builder/${workflowKey}/edges/${edgeId}`),

  // Live Data
  getNodeLeads: (workflowKey, nodeId, page = 1, perPage = 20) =>
    api.get(`/api/v1/workflow-builder/${workflowKey}/nodes/${nodeId}/leads?page=${page}&per_page=${perPage}`),

  getNodeHistory: (workflowKey, nodeId, limit = 50) =>
    api.get(`/api/v1/workflow-builder/${workflowKey}/nodes/${nodeId}/history?limit=${limit}`),

  getNodeMetrics: (workflowKey, nodeId) =>
    api.get(`/api/v1/workflow-builder/${workflowKey}/nodes/${nodeId}/metrics`),

  // AI Review Loop (supervised mode)
  getPendingAIActions: (workflowKey) =>
    api.get(`/api/v1/workflow-builder/${workflowKey}/ai-actions/pending`),

  submitAIReview: (workflowKey, actionId, data) =>
    api.post(`/api/v1/workflow-builder/${workflowKey}/ai-actions/${actionId}/review`, data),
};
