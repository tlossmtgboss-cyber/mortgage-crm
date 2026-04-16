import { API_BASE_URL } from './api';
import { getToken } from '../utils/tokenStore';

const getAuthHeaders = () => {
  const token = getToken();
  return {
    'Content-Type': 'application/json',
    ...(token && { Authorization: `Bearer ${token}` }),
  };
};

export const decisionLabAPI = {
  // Session Management
  startSession: async (borrowerId = null) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/sessions`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ borrower_profile_id: borrowerId }),
    });
    if (!response.ok) throw new Error('Failed to start session');
    return response.json();
  },

  getProgress: async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/sessions/${sessionId}/progress`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get progress');
    return response.json();
  },

  // Confidence Questions
  getNextQuestion: async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/questions/next?session_id=${sessionId}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get next question');
    return response.json();
  },

  submitResponse: async (sessionId, questionId, responseValue, confidenceLevel = 3) => {
    // Backend expects session_id as query param and response_value as a dict
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/questions/respond?session_id=${sessionId}`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        question_id: questionId,
        response_value: { value: responseValue },
        confidence_level: confidenceLevel,
      }),
    });
    if (!response.ok) throw new Error('Failed to submit response');
    return response.json();
  },

  // Confidence Scoring
  calculateScore: async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/score?session_id=${sessionId}`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to calculate score');
    return response.json();
  },

  getScore: async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/score/${sessionId}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get score');
    return response.json();
  },

  // Loan Scenarios
  createScenario: async (sessionId, scenarioData) => {
    // Map frontend field names to backend expected names
    const backendData = {
      loan_amount: scenarioData.loan_amount,
      purchase_price: scenarioData.purchase_price,
      down_payment: scenarioData.down_payment,
      property_type: scenarioData.property_type,
      occupancy_type: scenarioData.occupancy,  // frontend uses 'occupancy'
      property_state: scenarioData.state,       // frontend uses 'state'
      credit_score: scenarioData.credit_score,
      is_baseline: false,
    };
    // session_id must be a query parameter
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/scenarios?session_id=${sessionId}`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(backendData),
    });
    if (!response.ok) throw new Error('Failed to create scenario');
    return response.json();
  },

  calculateLoanOptions: async (scenarioId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/scenarios/${scenarioId}/calculate`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to calculate loan options');
    return response.json();
  },

  getScenarios: async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/scenarios?session_id=${sessionId}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get scenarios');
    return response.json();
  },

  getScenario: async (scenarioId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/scenarios/${scenarioId}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get scenario');
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

  getLesson: async (lessonId) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/education/lessons/${lessonId}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get lesson');
    return response.json();
  },

  trackLessonProgress: async (sessionId, lessonId, completed = false) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/track`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        session_id: sessionId,
        lesson_id: lessonId,
        completed
      }),
    });
    if (!response.ok) throw new Error('Failed to track progress');
    return response.json();
  },

  // Recommendations - derived from score
  getRecommendations: async (sessionId) => {
    // Get score which includes recommendations
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/score/${sessionId}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get recommendations');
    const data = await response.json();
    return { recommendations: data.recommendations || [] };
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

  runMigration: async (adminKey) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/decision-lab/admin/run-migration?admin_key=${adminKey}`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error('Failed to run migration');
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
