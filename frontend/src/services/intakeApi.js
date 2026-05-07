/**
 * Intake Engine API Service
 * Handles all API calls for the conversational loan intake system
 */

import { getAuthHeaders } from '../utils/auth';

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';

// ============== SESSION MANAGEMENT ==============

/**
 * Create a new intake session
 * @param {Object} data - Session data (lead_id, loan_id, party_type)
 */
export const createSession = async (data) => {
  const response = await fetch(`${API_BASE}/api/v1/intake/sessions`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to create intake session');
  }

  return response.json();
};

/**
 * Get session status and details
 * @param {string} sessionId - The session ID
 */
export const getSession = async (sessionId) => {
  const response = await fetch(`${API_BASE}/api/v1/intake/sessions/${sessionId}`, {
    headers: getAuthHeaders()
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error('Failed to get session');
  }

  return response.json();
};

// ============== QUESTION FLOW ==============

/**
 * Get the next question in the sequence
 * @param {string} sessionId - The session ID
 */
export const getNextQuestion = async (sessionId) => {
  const response = await fetch(`${API_BASE}/api/v1/intake/sessions/${sessionId}/next`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to get next question');
  }

  return response.json();
};

/**
 * Get the previous question (for going back in the flow)
 * @param {string} sessionId - The session ID
 */
export const getPreviousQuestion = async (sessionId) => {
  const response = await fetch(`${API_BASE}/api/v1/intake/sessions/${sessionId}/previous`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to get previous question');
  }

  return response.json();
};

/**
 * Submit an answer to the current question
 * @param {string} sessionId - The session ID
 * @param {Object} data - Answer data (question_id, value, metadata)
 */
export const submitAnswer = async (sessionId, data) => {
  // Map 'answer' to 'value' for API compatibility
  const payload = {
    question_id: data.question_id,
    value: data.answer !== undefined ? data.answer : data.value,
    party_id: data.party_id,
    metadata: data.metadata
  };

  const response = await fetch(`${API_BASE}/api/v1/intake/sessions/${sessionId}/answer`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to submit answer');
  }

  return response.json();
};

// ============== SCORING ==============

/**
 * Get current scores for a session
 * @param {string} sessionId - The session ID
 */
export const getScores = async (sessionId) => {
  const response = await fetch(`${API_BASE}/api/v1/intake/sessions/${sessionId}/scores`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to get scores');
  }

  return response.json();
};

/**
 * Get coaching suggestions for a session
 * @param {string} sessionId - The session ID
 */
export const getCoaching = async (sessionId) => {
  const response = await fetch(`${API_BASE}/api/v1/intake/sessions/${sessionId}/coaching`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to get coaching suggestions');
  }

  return response.json();
};

/**
 * Get behavioral flags for a session
 * @param {string} sessionId - The session ID
 */
export const getFlags = async (sessionId) => {
  const response = await fetch(`${API_BASE}/api/v1/intake/sessions/${sessionId}/flags`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to get flags');
  }

  return response.json();
};

// ============== AUDIT ==============

/**
 * Get audit trail for a session
 * @param {string} sessionId - The session ID
 */
export const getAuditTrail = async (sessionId) => {
  const response = await fetch(`${API_BASE}/api/v1/intake/sessions/${sessionId}/audit`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to get audit trail');
  }

  return response.json();
};

export const intakeApi = {
  createSession,
  getSession,
  getNextQuestion,
  getPreviousQuestion,
  submitAnswer,
  getScores,
  getCoaching,
  getFlags,
  getAuditTrail
};

export default intakeApi;
