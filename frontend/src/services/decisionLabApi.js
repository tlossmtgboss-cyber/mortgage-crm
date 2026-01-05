import { API_BASE_URL } from './api';

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token && { Authorization: `Bearer ${token}` }),
  };
};

export const decisionLabAPI = {
  // Session Management
  startSession: async (borrowerId = null) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/session/start`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ borrower_id: borrowerId }),
    });
    if (!response.ok) throw new Error('Failed to start session');
    return response.json();
  },

  getProgress: async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/session/${sessionId}/progress`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get progress');
    return response.json();
  },

  // Confidence Questions
  getNextQuestion: async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/session/${sessionId}/next-question`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get next question');
    return response.json();
  },

  submitResponse: async (sessionId, questionId, responseValue, confidenceLevel = 3) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/session/${sessionId}/response`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        question_id: questionId,
        response_value: responseValue,
        confidence_level: confidenceLevel,
      }),
    });
    if (!response.ok) throw new Error('Failed to submit response');
    return response.json();
  },

  // Confidence Scoring
  calculateScore: async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/session/${sessionId}/score`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to calculate score');
    return response.json();
  },

  // Loan Scenarios
  createScenario: async (sessionId, scenarioData) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/session/${sessionId}/scenario`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(scenarioData),
    });
    if (!response.ok) throw new Error('Failed to create scenario');
    return response.json();
  },

  calculateLoanOptions: async (scenarioId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/scenario/${scenarioId}/calculate`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to calculate loan options');
    return response.json();
  },

  getScenarios: async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/session/${sessionId}/scenarios`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get scenarios');
    return response.json();
  },

  compareScenarios: async (scenarioIds) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/scenarios/compare`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ scenario_ids: scenarioIds }),
    });
    if (!response.ok) throw new Error('Failed to compare scenarios');
    return response.json();
  },

  // Education Content
  getOverlays: async () => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/education/overlays`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get overlays');
    return response.json();
  },

  getOverlay: async (overlayId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/education/overlay/${overlayId}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get overlay');
    return response.json();
  },

  createOverlay: async (overlayData) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/education/overlay`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(overlayData),
    });
    if (!response.ok) throw new Error('Failed to create overlay');
    return response.json();
  },

  updateOverlay: async (overlayId, overlayData) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/education/overlay/${overlayId}`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify(overlayData),
    });
    if (!response.ok) throw new Error('Failed to update overlay');
    return response.json();
  },

  deleteOverlay: async (overlayId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/education/overlay/${overlayId}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to delete overlay');
    return response.json();
  },

  getLessons: async (category = null) => {
    const url = category
      ? `${API_BASE_URL}/api/v1/decision-lab/education/lessons?category=${category}`
      : `${API_BASE_URL}/api/v1/decision-lab/education/lessons`;
    const response = await fetch(url, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get lessons');
    return response.json();
  },

  trackLessonProgress: async (sessionId, lessonId, completed = false) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/session/${sessionId}/lesson/${lessonId}/progress`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ completed }),
    });
    if (!response.ok) throw new Error('Failed to track progress');
    return response.json();
  },

  // Recommendations
  getRecommendations: async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/session/${sessionId}/recommendations`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get recommendations');
    return response.json();
  },

  // Admin
  seedQuestions: async (adminKey) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/admin/seed-questions?admin_key=${adminKey}`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to seed questions');
    return response.json();
  },

  getAllQuestions: async () => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/questions`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get questions');
    return response.json();
  },
};

export default decisionLabAPI;
