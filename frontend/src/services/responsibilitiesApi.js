/**
 * Responsibilities API Service
 *
 * Provides all API calls for managing user responsibilities and skills
 */

import { ensureArray } from '../utils/arrayHelpers';

const API_BASE = '/api/v1';

// Helper to get auth headers
const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
};

// Helper to handle API errors
const handleResponse = async (response) => {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API error: ${response.status}`);
  }
  return await response.json();
};

/**
 * Responsibilities API
 */

export const fetchResponsibilities = async (userId) => {
  const response = await fetch(`${API_BASE}/users/${userId}/responsibilities`, {
    headers: getAuthHeaders()
  });
  const data = await handleResponse(response);
  return ensureArray(data, 'responsibilities');
};

export const fetchArchivedResponsibilities = async (userId) => {
  const response = await fetch(`${API_BASE}/users/${userId}/responsibilities/archived`, {
    headers: getAuthHeaders()
  });
  const data = await handleResponse(response);
  return ensureArray(data, 'responsibilities');
};

export const createResponsibility = async (userId, data) => {
  const response = await fetch(`${API_BASE}/users/${userId}/responsibilities`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  return handleResponse(response);
};

export const updateResponsibility = async (userId, respId, data) => {
  const response = await fetch(`${API_BASE}/users/${userId}/responsibilities/${respId}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  return handleResponse(response);
};

export const archiveResponsibility = async (userId, respId) => {
  const response = await fetch(`${API_BASE}/users/${userId}/responsibilities/${respId}`, {
    method: 'DELETE',
    headers: getAuthHeaders()
  });
  return handleResponse(response);
};

export const restoreResponsibility = async (userId, respId) => {
  const response = await fetch(`${API_BASE}/users/${userId}/responsibilities/${respId}/restore`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  return handleResponse(response);
};

export const reorderResponsibilities = async (userId, orderedIds) => {
  const response = await fetch(`${API_BASE}/users/${userId}/responsibilities/reorder`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify({ ordered_ids: orderedIds })
  });
  return handleResponse(response);
};

/**
 * Skills Library API
 */

export const fetchSkillsLibrary = async () => {
  const response = await fetch(`${API_BASE}/skills/library`, {
    headers: getAuthHeaders()
  });
  const data = await handleResponse(response);
  return ensureArray(data, 'skills');
};

export const addSkillToLibrary = async (skillData) => {
  const response = await fetch(`${API_BASE}/skills/library`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(skillData)
  });
  return handleResponse(response);
};

/**
 * Skills Assessment API
 */

export const getUserSkills = async (userId) => {
  const response = await fetch(`${API_BASE}/users/${userId}/skills`, {
    headers: getAuthHeaders()
  });
  const data = await handleResponse(response);
  return ensureArray(data);
};

export const addUserSkill = async (userId, data) => {
  const response = await fetch(`${API_BASE}/users/${userId}/skills`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  return handleResponse(response);
};

export const assessSkill = async (userId, skillId, data) => {
  const response = await fetch(`${API_BASE}/users/${userId}/skills/${skillId}/assess`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  return handleResponse(response);
};

export const removeUserSkill = async (userId, skillId) => {
  const response = await fetch(`${API_BASE}/users/${userId}/skills/${skillId}`, {
    method: 'DELETE',
    headers: getAuthHeaders()
  });
  return handleResponse(response);
};

// Export all as a single object for convenience
const responsibilitiesApi = {
  // Responsibilities
  fetchResponsibilities,
  fetchArchivedResponsibilities,
  createResponsibility,
  updateResponsibility,
  archiveResponsibility,
  restoreResponsibility,
  reorderResponsibilities,

  // Skills Library
  fetchSkillsLibrary,
  addSkillToLibrary,

  // Skills Assessment
  getUserSkills,
  addUserSkill,
  assessSkill,
  removeUserSkill
};

export default responsibilitiesApi;
