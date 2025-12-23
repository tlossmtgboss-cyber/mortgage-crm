/**
 * Goals & OKRs API Service
 *
 * Provides all API calls for managing user goals, key results, and assessments
 */

import { ensureArray } from '../utils/arrayHelpers';
import { getAuthHeaders } from '../utils/auth';

const API_BASE = '/api/v1';

// Helper to handle API errors
const handleResponse = async (response) => {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API error: ${response.status}`);
  }
  return await response.json();
};

/**
 * Goals API
 */

export const getUserGoals = async (userId, params = {}) => {
  const queryParams = new URLSearchParams();
  if (params.period) queryParams.append('period', params.period);
  if (params.status) queryParams.append('status', params.status);

  const url = `${API_BASE}/users/${userId}/goals${queryParams.toString() ? '?' + queryParams.toString() : ''}`;

  const response = await fetch(url, {
    headers: getAuthHeaders()
  });
  const data = await handleResponse(response);
  return ensureArray(data, 'goals');
};

export const createGoal = async (userId, data) => {
  const response = await fetch(`${API_BASE}/users/${userId}/goals`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  return handleResponse(response);
};

export const updateGoal = async (userId, goalId, data) => {
  const response = await fetch(`${API_BASE}/users/${userId}/goals/${goalId}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  return handleResponse(response);
};

export const deleteGoal = async (userId, goalId) => {
  const response = await fetch(`${API_BASE}/users/${userId}/goals/${goalId}`, {
    method: 'DELETE',
    headers: getAuthHeaders()
  });
  return handleResponse(response);
};

/**
 * Key Results API
 */

export const updateKeyResult = async (userId, goalId, krId, data) => {
  const response = await fetch(`${API_BASE}/users/${userId}/goals/${goalId}/key-results/${krId}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  return handleResponse(response);
};

/**
 * Assessments API
 */

export const employeeSelfAssess = async (userId, goalId, data) => {
  const response = await fetch(`${API_BASE}/users/${userId}/goals/${goalId}/self-assess`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  return handleResponse(response);
};

export const managerAssess = async (userId, goalId, data) => {
  const response = await fetch(`${API_BASE}/users/${userId}/goals/${goalId}/manager-assess`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  return handleResponse(response);
};

// Export all as a single object for convenience
const goalsApi = {
  // Goals
  getUserGoals,
  createGoal,
  updateGoal,
  deleteGoal,

  // Key Results
  updateKeyResult,

  // Assessments
  employeeSelfAssess,
  managerAssess
};

export default goalsApi;
