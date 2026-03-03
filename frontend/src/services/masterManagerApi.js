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
  const response = await fetch(`${API_URL}/api/v1/master-manager/admin/run-migration`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to run migration');
  return response.json();
};

export const initializeCapacities = async () => {
  const response = await fetch(`${API_URL}/api/v1/master-manager/admin/initialize-capacities`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to initialize capacities');
  return response.json();
};

// =============================================================================
// RECRUITING ENDPOINTS
// =============================================================================

export const getRecruitingPipelineMetrics = async (days = 90) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/pipeline/metrics?days=${days}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch pipeline metrics');
  return response.json();
};

export const getRecruitingDashboardStats = async () => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/dashboard/stats`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch dashboard stats');
  return response.json();
};

export const getUpcomingInterviews = async (limit = 10) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/dashboard/upcoming-interviews?limit=${limit}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch upcoming interviews');
  return response.json();
};

export const getCandidates = async (params = {}) => {
  const searchParams = new URLSearchParams();
  if (params.status) searchParams.append('status', params.status);
  if (params.role_id) searchParams.append('role_id', params.role_id);
  if (params.source) searchParams.append('source', params.source);
  if (params.search) searchParams.append('search', params.search);
  if (params.limit) searchParams.append('limit', params.limit);
  if (params.offset) searchParams.append('offset', params.offset);

  const response = await fetch(`${API_URL}/api/v1/recruiting/candidates?${searchParams}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch candidates');
  return response.json();
};

export const getCandidateDetail = async (candidateId) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/candidates/${candidateId}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch candidate');
  return response.json();
};

export const createCandidate = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/candidates`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to create candidate');
  return response.json();
};

export const updateCandidateStatus = async (candidateId, status, reason = null) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/candidates/${candidateId}/status`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ status, reason })
  });
  if (!response.ok) throw new Error('Failed to update candidate status');
  return response.json();
};

export const getJobPostings = async (params = {}) => {
  const searchParams = new URLSearchParams();
  if (params.is_published !== undefined) searchParams.append('is_published', params.is_published);
  if (params.limit) searchParams.append('limit', params.limit);

  const response = await fetch(`${API_URL}/api/v1/recruiting/job-postings?${searchParams}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch job postings');
  return response.json();
};

export const createJobPosting = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/job-postings`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to create job posting');
  return response.json();
};

export const publishJobPosting = async (postingId) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/job-postings/${postingId}/publish`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to publish job posting');
  return response.json();
};

export const submitInterviewFeedback = async (interviewId, feedback) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/interviews/${interviewId}/feedback`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(feedback)
  });
  if (!response.ok) throw new Error('Failed to submit feedback');
  return response.json();
};

export const getOffers = async (status = null) => {
  const params = status ? `?status=${status}` : '';
  const response = await fetch(`${API_URL}/api/v1/recruiting/offers${params}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch offers');
  return response.json();
};

export const createOffer = async (candidateId, data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/candidates/${candidateId}/offers`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to create offer');
  return response.json();
};

export const sendOffer = async (offerId, expiresInDays = 7) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/offers/${offerId}/send`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ expires_in_days: expiresInDays })
  });
  if (!response.ok) throw new Error('Failed to send offer');
  return response.json();
};

export const addCandidateNote = async (candidateId, data) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/candidates/${candidateId}/notes`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to add note');
  return response.json();
};

export const scheduleInterview = async (candidateId, interviewData) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/candidates/${candidateId}/interviews`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(interviewData)
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to schedule interview');
  }
  return response.json();
};

// =============================================================================
// PARTNER RECRUITING ENDPOINTS (Realtors from RETR)
// =============================================================================

export const getPartnerRecruits = async (params = {}) => {
  const searchParams = new URLSearchParams();
  if (params.status) searchParams.append('status', params.status);
  if (params.source) searchParams.append('source', params.source);
  if (params.search) searchParams.append('search', params.search);
  if (params.limit) searchParams.append('limit', params.limit);
  if (params.offset) searchParams.append('offset', params.offset);

  const response = await fetch(`${API_URL}/api/v1/recruiting/partners?${searchParams}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch partner recruits');
  return response.json();
};

export const getPartnerRecruitDetail = async (partnerId) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/partners/${partnerId}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch partner recruit');
  return response.json();
};

export const updatePartnerRecruitStatus = async (partnerId, status) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/partners/${partnerId}/status?status=${status}`, {
    method: 'PATCH',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to update partner recruit status');
  return response.json();
};

export const getPartnerRecruitStats = async () => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/partners/stats/overview`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch partner recruit stats');
  return response.json();
};

// =============================================================================
// CANDIDATE DETAIL ENDPOINTS (Full Profile with Social/Production)
// =============================================================================

export const getCandidateFullProfile = async (candidateId) => {
  const response = await fetch(`${API_URL}/api/v1/recruiting/candidates/${candidateId}/full-profile`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch candidate profile');
  return response.json();
};

export const updateCandidateSocialMedia = async (candidateId, socialData) => {
  const params = new URLSearchParams();
  if (socialData.facebook_url) params.append('facebook_url', socialData.facebook_url);
  if (socialData.instagram_url) params.append('instagram_url', socialData.instagram_url);
  if (socialData.twitter_url) params.append('twitter_url', socialData.twitter_url);
  if (socialData.linkedin_url) params.append('linkedin_url', socialData.linkedin_url);

  const response = await fetch(`${API_URL}/api/v1/recruiting/candidates/${candidateId}/social-media?${params}`, {
    method: 'PUT',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to update social media');
  return response.json();
};

export const updateCandidateProduction = async (candidateId, productionData) => {
  const params = new URLSearchParams();
  if (productionData.annual_volume) params.append('annual_volume', productionData.annual_volume);
  if (productionData.annual_units) params.append('annual_units', productionData.annual_units);
  if (productionData.nmls_id) params.append('nmls_id', productionData.nmls_id);
  if (productionData.current_company) params.append('current_company', productionData.current_company);
  if (productionData.current_title) params.append('current_title', productionData.current_title);

  const response = await fetch(`${API_URL}/api/v1/recruiting/candidates/${candidateId}/production?${params}`, {
    method: 'PUT',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to update production data');
  return response.json();
};

export const updateCandidateBasicInfo = async (candidateId, basicData) => {
  const params = new URLSearchParams();
  if (basicData.first_name) params.append('first_name', basicData.first_name);
  if (basicData.last_name) params.append('last_name', basicData.last_name);
  if (basicData.email) params.append('email', basicData.email);
  if (basicData.phone) params.append('phone', basicData.phone);

  const response = await fetch(`${API_URL}/api/v1/recruiting/candidates/${candidateId}/basic-info?${params}`, {
    method: 'PUT',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to update basic info');
  return response.json();
};

// Migration endpoint removed — run backend/migrations/ scripts directly.

// =============================================================================
// RECRUIT PORTAL ENDPOINTS
// =============================================================================

export const createCandidatePortalWorkspace = async (candidateId, slug = null) => {
  const params = new URLSearchParams();
  params.append('candidate_id', candidateId);
  if (slug) params.append('slug', slug);

  const response = await fetch(`${API_URL}/api/v1/recruit-portal/admin/workspaces?${params}`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to create portal workspace');
  return response.json();
};

export const getCandidatePortalWorkspace = async (candidateId) => {
  const response = await fetch(`${API_URL}/api/v1/recruit-portal/admin/workspaces/by-candidate/${candidateId}`, {
    headers: getAuthHeaders()
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error('Failed to fetch portal workspace');
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
  initializeCapacities,
  // Recruiting
  getRecruitingPipelineMetrics,
  getRecruitingDashboardStats,
  getUpcomingInterviews,
  getCandidates,
  getCandidateDetail,
  createCandidate,
  updateCandidateStatus,
  getJobPostings,
  createJobPosting,
  publishJobPosting,
  scheduleInterview,
  submitInterviewFeedback,
  getOffers,
  createOffer,
  sendOffer,
  addCandidateNote,
  // Partner Recruiting
  getPartnerRecruits,
  getPartnerRecruitDetail,
  updatePartnerRecruitStatus,
  getPartnerRecruitStats,
  // Candidate Full Profile
  getCandidateFullProfile,
  updateCandidateSocialMedia,
  updateCandidateProduction,
  runSocialProductionMigration,
  // Recruit Portal
  createCandidatePortalWorkspace,
  getCandidatePortalWorkspace
};
