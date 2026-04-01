/**
 * Retell AI API Service
 *
 * Frontend API client for Retell AI voice platform.
 */

// Use shared api instance for CSRF, auth, and impersonation support
import api from './api';

const API_BASE = '/api/v1/retell';
const apiClient = api;

// ============ Connection ============

export const connectRetell = async (apiKey) => {
  const response = await apiClient.post(`${API_BASE}/connect`, { api_key: apiKey });
  return response.data;
};

export const getRetellStatus = async () => {
  const response = await apiClient.get(`${API_BASE}/status`);
  return response.data;
};

// ============ Agents ============

export const listAgents = async () => {
  const response = await apiClient.get(`${API_BASE}/agents`);
  return response.data;
};

export const getAgent = async (agentId) => {
  const response = await apiClient.get(`${API_BASE}/agents/${agentId}`);
  return response.data;
};

export const createAgent = async (data) => {
  const response = await apiClient.post(`${API_BASE}/agents`, data);
  return response.data;
};

export const updateAgent = async (agentId, data) => {
  const response = await apiClient.patch(`${API_BASE}/agents/${agentId}`, data);
  return response.data;
};

export const deleteAgent = async (agentId) => {
  const response = await apiClient.delete(`${API_BASE}/agents/${agentId}`);
  return response.data;
};

// ============ Phone Numbers ============

export const listPhoneNumbers = async () => {
  const response = await apiClient.get(`${API_BASE}/phone-numbers`);
  return response.data;
};

export const createPhoneNumber = async (data) => {
  const response = await apiClient.post(`${API_BASE}/phone-numbers`, data);
  return response.data;
};

export const importPhoneNumber = async (data) => {
  const response = await apiClient.post(`${API_BASE}/phone-numbers/import`, data);
  return response.data;
};

export const updatePhoneNumber = async (phoneNumber, data) => {
  const response = await apiClient.patch(`${API_BASE}/phone-numbers/${encodeURIComponent(phoneNumber)}`, data);
  return response.data;
};

export const deletePhoneNumber = async (phoneNumber) => {
  const response = await apiClient.delete(`${API_BASE}/phone-numbers/${encodeURIComponent(phoneNumber)}`);
  return response.data;
};

// ============ Calls ============

export const createCall = async (data) => {
  const response = await apiClient.post(`${API_BASE}/calls`, data);
  return response.data;
};

export const listCalls = async (params = {}) => {
  const response = await apiClient.get(`${API_BASE}/calls`, { params });
  return response.data;
};

export const getCall = async (callId) => {
  const response = await apiClient.get(`${API_BASE}/calls/${callId}`);
  return response.data;
};

export const endCall = async (callId) => {
  const response = await apiClient.post(`${API_BASE}/calls/${callId}/end`);
  return response.data;
};

export const transferCall = async (callId, transferTo) => {
  const response = await apiClient.post(`${API_BASE}/calls/${callId}/transfer`, null, {
    params: { transfer_to: transferTo }
  });
  return response.data;
};

// ============ Voices ============

export const listVoices = async () => {
  const response = await apiClient.get(`${API_BASE}/voices`);
  return response.data;
};

// ============ Analytics ============

export const getCallAnalytics = async (days = 30, agentId = null) => {
  const params = { days };
  if (agentId) params.agent_id = agentId;
  const response = await apiClient.get(`${API_BASE}/analytics/calls`, { params });
  return response.data;
};

// Export all functions as named object
export const retellAPI = {
  // Connection
  connectRetell,
  getRetellStatus,
  // Agents
  listAgents,
  getAgent,
  createAgent,
  updateAgent,
  deleteAgent,
  // Phone Numbers
  listPhoneNumbers,
  createPhoneNumber,
  importPhoneNumber,
  updatePhoneNumber,
  deletePhoneNumber,
  // Calls
  createCall,
  listCalls,
  getCall,
  endCall,
  transferCall,
  // Voices
  listVoices,
  // Analytics
  getCallAnalytics,
};

export default retellAPI;
