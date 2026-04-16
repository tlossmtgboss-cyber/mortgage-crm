/**
 * DISC Assessment API Service
 * Handles all API calls related to DISC + Motivators assessments
 */

import React from 'react';
import { getToken } from '../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

/**
 * Get auth headers
 */
function getHeaders() {
  const token = getToken();
  return {
    'Content-Type': 'application/json',
    ...(token && { 'Authorization': `Bearer ${token}` })
  };
}

/**
 * Start a new DISC assessment session for a candidate
 */
export async function startAssessmentSession(candidateId, assessmentId = 1) {
  const response = await fetch(`${API_BASE}/api/v1/disc/sessions/start`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({
      candidate_id: candidateId,
      assessment_id: assessmentId
    })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start assessment session');
  }

  return response.json();
}

/**
 * Get assessment session details
 */
export async function getSession(sessionId) {
  const response = await fetch(`${API_BASE}/api/v1/disc/sessions/${sessionId}`, {
    headers: getHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to get session');
  }

  return response.json();
}

/**
 * Get questions for an assessment session
 */
export async function getSessionQuestions(sessionId) {
  const response = await fetch(`${API_BASE}/api/v1/disc/sessions/${sessionId}/questions`, {
    headers: getHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to get questions');
  }

  return response.json();
}

/**
 * Submit an answer for a question
 */
export async function submitAnswer(sessionId, questionId, responseValue, responseTimeMs = null) {
  const response = await fetch(`${API_BASE}/api/v1/disc/sessions/${sessionId}/answer`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({
      question_id: questionId,
      response_value: responseValue,
      response_time_ms: responseTimeMs
    })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to submit answer');
  }

  return response.json();
}

/**
 * Complete the assessment session and get results
 */
export async function completeSession(sessionId) {
  const response = await fetch(`${API_BASE}/api/v1/disc/sessions/${sessionId}/complete`, {
    method: 'POST',
    headers: getHeaders()
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to complete session');
  }

  return response.json();
}

/**
 * Get DISC results for a candidate
 */
export async function getDISCResults(candidateId) {
  const response = await fetch(`${API_BASE}/api/v1/disc/results/${candidateId}`, {
    headers: getHeaders()
  });

  if (!response.ok) {
    if (response.status === 404) {
      return null; // No results yet
    }
    throw new Error('Failed to get DISC results');
  }

  return response.json();
}

/**
 * Get DISC results summary for a candidate
 */
export async function getDISCResultsSummary(candidateId) {
  const response = await fetch(`${API_BASE}/api/v1/disc/results/${candidateId}/summary`, {
    headers: getHeaders()
  });

  if (!response.ok) {
    if (response.status === 404) {
      return null;
    }
    throw new Error('Failed to get DISC summary');
  }

  return response.json();
}

/**
 * Generate AI content for DISC results
 */
export async function generateDISCContent(candidateId) {
  const response = await fetch(`${API_BASE}/api/v1/disc/results/${candidateId}/generate-content`, {
    method: 'POST',
    headers: getHeaders()
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to generate content');
  }

  return response.json();
}

/**
 * Get public session by token (for candidate taking assessment)
 */
export async function getPublicSession(token) {
  const response = await fetch(`${API_BASE}/api/v1/disc/public/session/${token}`, {
    headers: { 'Content-Type': 'application/json' }
  });

  if (!response.ok) {
    throw new Error('Invalid or expired assessment link');
  }

  return response.json();
}

/**
 * Send assessment invite to a candidate
 */
export async function sendAssessmentInvite(candidateId, options = {}) {
  const response = await fetch(`${API_BASE}/api/v1/recruiting/candidates/${candidateId}/disc/invite`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({
      send_email: options.sendEmail !== false,
      send_sms: options.sendSms || false,
      custom_message: options.customMessage
    })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to send invite');
  }

  return response.json();
}

/**
 * Download DISC PDF report
 */
export async function downloadDISCReport(candidateId) {
  const response = await fetch(`${API_BASE}/api/v1/disc/results/${candidateId}/pdf`, {
    headers: getHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to download report');
  }

  // Get the blob and create download link
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `DISC_Report_${candidateId}.pdf`;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  a.remove();
}

/**
 * Get Motivators results for a candidate
 */
export async function getMotivatorsResults(candidateId) {
  const response = await fetch(`${API_BASE}/api/v1/disc/motivators/${candidateId}`, {
    headers: getHeaders()
  });

  if (!response.ok) {
    if (response.status === 404) {
      return null;
    }
    throw new Error('Failed to get Motivators results');
  }

  return response.json();
}

/**
 * Hook for DISC data fetching
 */
export function useDISCResults(candidateId) {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    if (!candidateId) {
      setLoading(false);
      return;
    }

    async function fetchResults() {
      try {
        setLoading(true);
        const results = await getDISCResults(candidateId);
        setData(results);
        setError(null);
      } catch (err) {
        setError(err.message);
        setData(null);
      } finally {
        setLoading(false);
      }
    }

    fetchResults();
  }, [candidateId]);

  return { data, loading, error, refetch: () => getDISCResults(candidateId).then(setData) };
}

export default {
  startAssessmentSession,
  getSession,
  getSessionQuestions,
  submitAnswer,
  completeSession,
  getDISCResults,
  getDISCResultsSummary,
  generateDISCContent,
  getPublicSession,
  sendAssessmentInvite,
  downloadDISCReport,
  getMotivatorsResults,
  useDISCResults
};
