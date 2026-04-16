import { getToken } from '../utils/tokenStore';

/**
 * Candidate Grading API Service
 * API wrapper for LO candidate assessment and grading operations.
 */

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

/**
 * Get auth headers for API requests
 */
const getHeaders = () => {
  const token = getToken();
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
};

/**
 * Handle API response
 */
const handleResponse = async (response) => {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `API Error: ${response.status}`);
  }
  return response.json();
};

// =============================================================================
// ASSESSMENT CRUD OPERATIONS
// =============================================================================

/**
 * Get current assessment for a candidate
 * @param {number} candidateId - Candidate ID
 * @returns {Promise<Object>} Assessment data
 */
export const getCandidateAssessment = async (candidateId) => {
  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/${candidateId}/assessment`,
    { headers: getHeaders() }
  );
  return handleResponse(response);
};

/**
 * Create a new assessment for a candidate
 * @param {number} candidateId - Candidate ID
 * @param {Object} data - Assessment data
 * @param {number} assessedBy - User ID of assessor
 * @returns {Promise<Object>} Created assessment
 */
export const createAssessment = async (candidateId, data, assessedBy) => {
  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/${candidateId}/assessment?assessed_by=${assessedBy}`,
    {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(data)
    }
  );
  return handleResponse(response);
};

/**
 * Update an existing assessment
 * @param {number} candidateId - Candidate ID
 * @param {Object} data - Updated assessment data
 * @param {number} updatedBy - User ID making the update
 * @returns {Promise<Object>} Updated assessment
 */
export const updateAssessment = async (candidateId, data, updatedBy) => {
  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/${candidateId}/assessment?updated_by=${updatedBy}`,
    {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(data)
    }
  );
  return handleResponse(response);
};

/**
 * Get assessment history for a candidate
 * @param {number} candidateId - Candidate ID
 * @returns {Promise<Object>} Assessment history
 */
export const getAssessmentHistory = async (candidateId) => {
  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/${candidateId}/assessment/history`,
    { headers: getHeaders() }
  );
  return handleResponse(response);
};

/**
 * Get detailed breakdown of how overall grade was calculated
 * @param {number} candidateId - Candidate ID
 * @returns {Promise<Object>} Grade breakdown
 */
export const getAssessmentBreakdown = async (candidateId) => {
  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/${candidateId}/assessment/breakdown`,
    { headers: getHeaders() }
  );
  return handleResponse(response);
};

// =============================================================================
// CATEGORY-SPECIFIC UPDATES
// =============================================================================

/**
 * Update DISC personality scores
 * @param {number} candidateId - Candidate ID
 * @param {Object} scores - DISC scores { d_score, i_score, s_score, c_score, notes }
 * @param {number} updatedBy - User ID
 * @returns {Promise<Object>} Updated assessment
 */
export const updateDISCScores = async (candidateId, scores, updatedBy) => {
  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/${candidateId}/assessment/disc?updated_by=${updatedBy}`,
    {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(scores)
    }
  );
  return handleResponse(response);
};

/**
 * Update character assessment scores
 * @param {number} candidateId - Candidate ID
 * @param {Object} data - Character breakdown
 * @param {number} updatedBy - User ID
 * @returns {Promise<Object>} Updated assessment
 */
export const updateCharacterScores = async (candidateId, data, updatedBy) => {
  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/${candidateId}/assessment/character?updated_by=${updatedBy}`,
    {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(data)
    }
  );
  return handleResponse(response);
};

/**
 * Update skills assessment scores
 * @param {number} candidateId - Candidate ID
 * @param {Object} data - Skills breakdown
 * @param {number} updatedBy - User ID
 * @returns {Promise<Object>} Updated assessment
 */
export const updateSkillsScores = async (candidateId, data, updatedBy) => {
  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/${candidateId}/assessment/skills?updated_by=${updatedBy}`,
    {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(data)
    }
  );
  return handleResponse(response);
};

/**
 * Update culture fit scores
 * @param {number} candidateId - Candidate ID
 * @param {Object} data - Culture fit breakdown
 * @param {number} updatedBy - User ID
 * @returns {Promise<Object>} Updated assessment
 */
export const updateCultureFitScores = async (candidateId, data, updatedBy) => {
  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/${candidateId}/assessment/culture-fit?updated_by=${updatedBy}`,
    {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(data)
    }
  );
  return handleResponse(response);
};

// =============================================================================
// OVERRIDE OPERATIONS
// =============================================================================

/**
 * Override AI-suggested or calculated scores
 * @param {number} candidateId - Candidate ID
 * @param {Object} data - Override data with reason and new scores
 * @param {number} overrideBy - User ID
 * @returns {Promise<Object>} Override result
 */
export const overrideScores = async (candidateId, data, overrideBy) => {
  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/${candidateId}/assessment/override?override_by=${overrideBy}`,
    {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(data)
    }
  );
  return handleResponse(response);
};

// =============================================================================
// AI ANALYSIS
// =============================================================================

/**
 * Run AI analysis on candidate data
 * @param {number} candidateId - Candidate ID
 * @returns {Promise<Object>} AI analysis results
 */
export const runAIAnalysis = async (candidateId) => {
  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/${candidateId}/assessment/ai-analyze`,
    {
      method: 'POST',
      headers: getHeaders()
    }
  );
  return handleResponse(response);
};

// =============================================================================
// UTILITY ENDPOINTS
// =============================================================================

/**
 * Get grading weights and thresholds configuration
 * @returns {Promise<Object>} Grading configuration
 */
export const getGradingWeights = async () => {
  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/grading/weights`,
    { headers: getHeaders() }
  );
  return handleResponse(response);
};

/**
 * Preview what grade would result from given scores
 * @param {Object} scores - Category scores
 * @returns {Promise<Object>} Grade preview
 */
export const calculateGradePreview = async (scores) => {
  const params = new URLSearchParams();
  if (scores.production_score !== undefined) params.append('production_score', scores.production_score);
  if (scores.disc_score !== undefined) params.append('disc_score', scores.disc_score);
  if (scores.character_score !== undefined) params.append('character_score', scores.character_score);
  if (scores.skills_score !== undefined) params.append('skills_score', scores.skills_score);
  if (scores.culture_fit_score !== undefined) params.append('culture_fit_score', scores.culture_fit_score);

  const response = await fetch(
    `${API_BASE}/api/v1/recruiting/candidates/grading/calculate-preview?${params}`,
    {
      method: 'POST',
      headers: getHeaders()
    }
  );
  return handleResponse(response);
};

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Get grade info from score (client-side calculation)
 * @param {number} score - Numeric score (0-100)
 * @returns {Object} Grade info { grade, color, description }
 */
export const getGradeFromScore = (score) => {
  if (score === null || score === undefined) {
    return { grade: 'N/A', color: '#9ca3af', description: 'Not assessed' };
  }

  const grades = [
    { min: 95, grade: 'A+', color: '#10b981', description: 'Exceptional' },
    { min: 90, grade: 'A', color: '#10b981', description: 'Excellent' },
    { min: 85, grade: 'A-', color: '#22c55e', description: 'Very Good' },
    { min: 80, grade: 'B+', color: '#84cc16', description: 'Good' },
    { min: 75, grade: 'B', color: '#84cc16', description: 'Above Average' },
    { min: 70, grade: 'B-', color: '#eab308', description: 'Average' },
    { min: 65, grade: 'C+', color: '#f59e0b', description: 'Below Average' },
    { min: 60, grade: 'C', color: '#f59e0b', description: 'Weak' },
    { min: 55, grade: 'C-', color: '#f97316', description: 'Poor' },
    { min: 50, grade: 'D', color: '#ef4444', description: 'Very Poor' },
    { min: 0, grade: 'F', color: '#dc2626', description: 'Failing' }
  ];

  for (const g of grades) {
    if (score >= g.min) return g;
  }
  return grades[grades.length - 1];
};

/**
 * Calculate overall score from component scores (client-side)
 * @param {Object} scores - Component scores
 * @returns {number} Overall weighted score
 */
export const calculateOverallScore = (scores) => {
  const weights = {
    production: 0.45,
    disc: 0.20,
    character: 0.15,
    skills: 0.10,
    culture_fit: 0.10
  };

  let total = 0;
  for (const [key, weight] of Object.entries(weights)) {
    const score = scores[key] || 0;
    total += score * weight;
  }

  return Math.round(total * 10) / 10;
};

export default {
  getCandidateAssessment,
  createAssessment,
  updateAssessment,
  getAssessmentHistory,
  getAssessmentBreakdown,
  updateDISCScores,
  updateCharacterScores,
  updateSkillsScores,
  updateCultureFitScores,
  overrideScores,
  runAIAnalysis,
  getGradingWeights,
  calculateGradePreview,
  getGradeFromScore,
  calculateOverallScore
};
