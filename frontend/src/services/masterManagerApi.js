/**
 * Master Manager API Service
 * API calls for capacity tracking, talent state, and recruiting
 */

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    'Authorization': token ? `Bearer ${token}` : ''
  };
};

// =============================================================================
// CAPACITY ENDPOINTS
// =============================================================================

export const getCapacityOverview = async () => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/capacity/overview`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch capacity overview');
  return response.json();
};

export const getCapacityByRole = async () => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/capacity/by-role`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch capacity by role');
  return response.json();
};

export const getAllUserCapacities = async (params = {}) => {
  const searchParams = new URLSearchParams();
  if (params.status) searchParams.append('status', params.status);
  if (params.role) searchParams.append('role', params.role);
  if (params.limit) searchParams.append('limit', params.limit);

  const url = `${API_URL}/api/v1/master-manager/capacity/users?${searchParams}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch user capacities');
  return response.json();
};

export const getUserCapacity = async (userId) => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/capacity/user/${userId}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch user capacity');
  return response.json();
};

export const updateUserCapacityLimits = async (userId, limits) => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/capacity/user/${userId}/limits`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(limits)
  });
  if (!response.ok) throw new Error('Failed to update capacity limits');
  return response.json();
};

export const updateUserAvailability = async (userId, availability) => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/capacity/user/${userId}/availability`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(availability)
  });
  if (!response.ok) throw new Error('Failed to update availability');
  return response.json();
};

export const recalculateCapacities = async () => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/capacity/recalculate`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to recalculate capacities');
  return response.json();
};

export const createUserCapacity = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/capacity/user`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to create user capacity');
  return response.json();
};

// =============================================================================
// ASSIGNMENT ENDPOINTS
// =============================================================================

export const suggestAssignment = async (role, entityType = 'loan', complexity = 'normal') => {
  const params = new URLSearchParams({ role, entity_type: entityType, complexity });
  const response = await fetch(`${API_URL}/api/v1/master-manager/assignment/suggest?${params}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to get assignment suggestion');
  return response.json();
};

export const getAvailableUsers = async (role, minCapacity = 25) => {
  const params = new URLSearchParams({ role, min_capacity: minCapacity });
  const response = await fetch(`${API_URL}/api/v1/master-manager/assignment/available?${params}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to get available users');
  return response.json();
};

// =============================================================================
// ROLE ENDPOINTS
// =============================================================================

export const getRoleDefinitions = async (category = null) => {
  const params = category ? `?category=${category}` : '';
  const response = await fetch(`${API_URL}/api/v1/master-manager/roles${params}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch roles');
  return response.json();
};

export const createRoleDefinition = async (role) => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/roles`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(role)
  });
  if (!response.ok) throw new Error('Failed to create role');
  return response.json();
};

// =============================================================================
// TALENT STATE ENDPOINTS
// =============================================================================

export const getTalentReadinessBoard = async () => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/talent/readiness`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch readiness board');
  return response.json();
};

export const getTalentState = async (userId) => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/talent/${userId}/state`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch talent state');
  return response.json();
};

export const updateTalentState = async (userId, state, reason = null) => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/talent/${userId}/state`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify({ state, reason })
  });
  if (!response.ok) throw new Error('Failed to update talent state');
  return response.json();
};

// =============================================================================
// ALERTS ENDPOINTS
// =============================================================================

export const getCapacityAlerts = async (status = 'open', severity = null) => {
  const params = new URLSearchParams({ status });
  if (severity) params.append('severity', severity);

  const response = await fetch(`${API_URL}/api/v1/master-manager/alerts?${params}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch alerts');
  return response.json();
};

export const acknowledgeAlert = async (alertId, userId) => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/alerts/${alertId}/acknowledge?acknowledged_by=${userId}`, {
    method: 'PUT',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to acknowledge alert');
  return response.json();
};

export const resolveAlert = async (alertId, userId, notes = null) => {
  const params = new URLSearchParams({ resolved_by: userId });
  if (notes) params.append('notes', notes);

  const response = await fetch(`${API_URL}/api/v1/master-manager/alerts/${alertId}/resolve?${params}`, {
    method: 'PUT',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to resolve alert');
  return response.json();
};

// =============================================================================
// ADMIN ENDPOINTS
// =============================================================================

export const runMigration = async () => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/admin/run-migration?admin_key=perennia-admin-2024`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to run migration');
  return response.json();
};

export const initializeCapacities = async () => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/admin/initialize-capacities?admin_key=perennia-admin-2024`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to initialize capacities');
  return response.json();
};

export default {
  getCapacityOverview,
  getCapacityByRole,
  getAllUserCapacities,
  getUserCapacity,
  updateUserCapacityLimits,
  updateUserAvailability,
  recalculateCapacities,
  createUserCapacity,
  suggestAssignment,
  getAvailableUsers,
  getRoleDefinitions,
  createRoleDefinition,
  getTalentReadinessBoard,
  getTalentState,
  updateTalentState,
  getCapacityAlerts,
  acknowledgeAlert,
  resolveAlert,
  runMigration,
  initializeCapacities
};
