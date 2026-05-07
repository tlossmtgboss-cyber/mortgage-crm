import { getToken } from '../utils/tokenStore';

/**
 * Partner Recruiting API Service
 * API calls for Loan Officers to manage partner recruitment pipeline
 */

const API_URL = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';

const getAuthHeaders = () => {
  const token = getToken();
  return {
    'Content-Type': 'application/json',
    'Authorization': token ? `Bearer ${token}` : ''
  };
};

// =============================================================================
// PARTNER TYPES & STATUSES (Constants)
// =============================================================================

export const PARTNER_TYPES = [
  { value: 'realtor', label: 'Realtor' },
  { value: 'financial_planner', label: 'Financial Planner' },
  { value: 'cpa', label: 'CPA/Accountant' },
  { value: 'estate_attorney', label: 'Estate Attorney' },
  { value: 'insurance_agent', label: 'Insurance Agent' },
  { value: 'title_agent', label: 'Title Agent' },
  { value: 'builder', label: 'Home Builder' },
  { value: 'other', label: 'Other Professional' }
];

export const PARTNER_STATUSES = [
  { value: 'new', label: 'New', color: '#3b82f6', icon: 'plus-circle' },
  { value: 'contacted', label: 'Contacted', color: '#8b5cf6', icon: 'phone' },
  { value: 'qualified', label: 'Qualified', color: '#a855f7', icon: 'check-circle' },
  { value: 'meeting_scheduled', label: 'Meeting Scheduled', color: '#f59e0b', icon: 'calendar' },
  { value: 'met', label: 'Met', color: '#eab308', icon: 'users' },
  { value: 'proposal_sent', label: 'Proposal Sent', color: '#22c55e', icon: 'file-text' },
  { value: 'negotiating', label: 'Negotiating', color: '#14b8a6', icon: 'message-circle' },
  { value: 'onboarded', label: 'Onboarded', color: '#10b981', icon: 'check' },
  { value: 'declined', label: 'Declined', color: '#ef4444', icon: 'x-circle' },
  { value: 'inactive', label: 'Inactive', color: '#6b7280', icon: 'pause-circle' }
];

export const MEETING_TYPES = [
  { value: 'phone', label: 'Phone Call' },
  { value: 'video', label: 'Video Call' },
  { value: 'coffee', label: 'Coffee Meeting' },
  { value: 'lunch', label: 'Lunch Meeting' },
  { value: 'office_visit', label: 'Office Visit' },
  { value: 'networking_event', label: 'Networking Event' }
];

export const MEETING_OUTCOMES = [
  { value: 'very_positive', label: 'Very Positive', color: '#10b981' },
  { value: 'positive', label: 'Positive', color: '#22c55e' },
  { value: 'neutral', label: 'Neutral', color: '#f59e0b' },
  { value: 'negative', label: 'Negative', color: '#ef4444' },
  { value: 'needs_followup', label: 'Needs Follow-up', color: '#8b5cf6' }
];

export const CALL_OUTCOMES = [
  { value: 'connected', label: 'Connected' },
  { value: 'voicemail', label: 'Left Voicemail' },
  { value: 'no_answer', label: 'No Answer' },
  { value: 'busy', label: 'Busy' },
  { value: 'wrong_number', label: 'Wrong Number' }
];

export const PARTNER_SOURCES = [
  { value: 'retr', label: 'RETR Import' },
  { value: 'referral', label: 'Referral' },
  { value: 'networking', label: 'Networking Event' },
  { value: 'cold_outreach', label: 'Cold Outreach' },
  { value: 'event', label: 'Trade Show/Event' },
  { value: 'website', label: 'Website' },
  { value: 'linkedin', label: 'LinkedIn' }
];

// =============================================================================
// EMPLOYEE RECRUITING CONSTANTS
// =============================================================================

export const EMPLOYEE_ROLES = [
  { value: 'loan_officer', label: 'Loan Officer' },
  { value: 'processor', label: 'Loan Processor' },
  { value: 'closer', label: 'Closer/Funder' },
  { value: 'underwriter', label: 'Underwriter' },
  { value: 'assistant', label: 'Production Assistant' }
];

export const EMPLOYEE_STATUSES = [
  { value: 'new', label: 'New', color: '#3b82f6', icon: 'plus-circle' },
  { value: 'contacted', label: 'Contacted', color: '#8b5cf6', icon: 'phone' },
  { value: 'qualified', label: 'Qualified', color: '#a855f7', icon: 'check-circle' },
  { value: 'meeting_scheduled', label: 'Meeting Scheduled', color: '#f59e0b', icon: 'calendar' },
  { value: 'met', label: 'Met', color: '#eab308', icon: 'users' },
  { value: 'screening', label: 'Screening', color: '#f97316', icon: 'search' },
  { value: 'interview', label: 'Interview', color: '#ec4899', icon: 'mic' },
  { value: 'offer', label: 'Offer Extended', color: '#14b8a6', icon: 'file-text' },
  { value: 'hired', label: 'Hired', color: '#10b981', icon: 'check' },
  { value: 'declined', label: 'Declined', color: '#ef4444', icon: 'x-circle' },
  { value: 'withdrawn', label: 'Withdrawn', color: '#9ca3af', icon: 'arrow-left' },
  { value: 'inactive', label: 'Inactive', color: '#6b7280', icon: 'pause-circle' }
];

export const EMPLOYEE_SOURCES = [
  { value: 'referral', label: 'Referral' },
  { value: 'networking', label: 'Networking' },
  { value: 'cold_outreach', label: 'Cold Outreach' },
  { value: 'linkedin', label: 'LinkedIn' },
  { value: 'job_board', label: 'Job Board' },
  { value: 'internal_referral', label: 'Internal Referral' }
];

// =============================================================================
// DASHBOARD & STATS
// =============================================================================

export const getDashboardStats = async (candidateCategory = null) => {
  const params = new URLSearchParams();
  if (candidateCategory) params.append('candidate_category', candidateCategory);
  const url = `${API_URL}/api/v1/partner-recruiting/dashboard/stats?${params}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch dashboard stats');
  return response.json();
};

export const getPipelineMetrics = async (days = 90, candidateCategory = null) => {
  const params = new URLSearchParams({ days });
  if (candidateCategory) params.append('candidate_category', candidateCategory);
  const url = `${API_URL}/api/v1/partner-recruiting/pipeline/metrics?${params}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch pipeline metrics');
  return response.json();
};

// =============================================================================
// PARTNER CANDIDATES
// =============================================================================

export const getPartnerCandidates = async (params = {}) => {
  const searchParams = new URLSearchParams();
  if (params.status) searchParams.append('status', params.status);
  if (params.partner_type) searchParams.append('partner_type', params.partner_type);
  if (params.source) searchParams.append('source', params.source);
  if (params.search) searchParams.append('search', params.search);
  if (params.candidate_category) searchParams.append('candidate_category', params.candidate_category);
  if (params.limit) searchParams.append('limit', params.limit);
  if (params.offset) searchParams.append('offset', params.offset);

  const url = `${API_URL}/api/v1/partner-recruiting/candidates?${searchParams}`;
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Failed to fetch candidates');
  return response.json();
};

export const getPartnerCandidate = async (partnerId) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch partner candidate');
  return response.json();
};

export const createPartnerCandidate = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create partner candidate');
  }
  return response.json();
};

export const updatePartnerCandidate = async (partnerId, data) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to update partner candidate');
  return response.json();
};

export const deletePartnerCandidate = async (partnerId) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}`, {
    method: 'DELETE',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to delete partner candidate');
  return response.json();
};

export const updatePartnerStatus = async (partnerId, status, reason = null) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/status`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ status, reason })
  });
  if (!response.ok) throw new Error('Failed to update partner status');
  return response.json();
};

// =============================================================================
// MEETINGS
// =============================================================================

export const getPartnerMeetings = async (partnerId) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/meetings`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch meetings');
  return response.json();
};

export const scheduleMeeting = async (partnerId, data) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/meetings`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to schedule meeting');
  return response.json();
};

export const completeMeeting = async (meetingId, data) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/meetings/${meetingId}/complete`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to complete meeting');
  return response.json();
};

export const cancelMeeting = async (meetingId, reason = null) => {
  const params = reason ? `?reason=${encodeURIComponent(reason)}` : '';
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/meetings/${meetingId}${params}`, {
    method: 'DELETE',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to cancel meeting');
  return response.json();
};

// =============================================================================
// PROPOSALS
// =============================================================================

export const getPartnerProposals = async (partnerId) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/proposals`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch proposals');
  return response.json();
};

export const createProposal = async (partnerId, data) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/proposals`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to create proposal');
  return response.json();
};

export const sendProposal = async (proposalId, expiresInDays = 14) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/proposals/${proposalId}/send`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ expires_in_days: expiresInDays })
  });
  if (!response.ok) throw new Error('Failed to send proposal');
  return response.json();
};

export const recordProposalResponse = async (proposalId, accepted, notes = null) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/proposals/${proposalId}/respond`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ accepted, notes })
  });
  if (!response.ok) throw new Error('Failed to record proposal response');
  return response.json();
};

// =============================================================================
// EMPLOYEE CANDIDATES
// =============================================================================

export const createEmployeeCandidate = async (data) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/employee-candidates`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create employee candidate');
  }
  return response.json();
};

export const hireEmployeeCandidate = async (candidateId) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${candidateId}/hire`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to mark as hired');
  }
  return response.json();
};

// =============================================================================
// ONBOARDING
// =============================================================================

export const onboardPartner = async (partnerId) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/onboard`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to onboard partner');
  return response.json();
};

// =============================================================================
// NOTES & ACTIVITIES
// =============================================================================

export const getPartnerNotes = async (partnerId) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/notes`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch notes');
  return response.json();
};

export const addPartnerNote = async (partnerId, data) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/notes`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to add note');
  return response.json();
};

export const getPartnerActivities = async (partnerId, limit = 50) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/activities?limit=${limit}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch activities');
  return response.json();
};

// =============================================================================
// QUICK ACTIONS
// =============================================================================

export const logCall = async (partnerId, data) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/log-call`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to log call');
  return response.json();
};

export const logEmail = async (partnerId, subject, notes = null) => {
  const params = new URLSearchParams({ subject });
  if (notes) params.append('notes', notes);

  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/log-email?${params}`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to log email');
  return response.json();
};

// =============================================================================
// ASSESSMENTS
// =============================================================================

export const getPartnerAssessment = async (partnerId) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/assessment`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error('Failed to fetch assessment');
  return response.json();
};

export const updatePartnerAssessment = async (partnerId, data) => {
  const response = await fetch(`${API_URL}/api/v1/partner-recruiting/candidates/${partnerId}/assessment`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('Failed to update assessment');
  return response.json();
};

// =============================================================================
// HELPERS
// =============================================================================

export const getStatusColor = (status, category = 'partner') => {
  const list = category === 'employee' ? EMPLOYEE_STATUSES : PARTNER_STATUSES;
  const statusObj = list.find(s => s.value === status);
  return statusObj?.color || '#6b7280';
};

export const getStatusLabel = (status, category = 'partner') => {
  const list = category === 'employee' ? EMPLOYEE_STATUSES : PARTNER_STATUSES;
  const statusObj = list.find(s => s.value === status);
  return statusObj?.label || status;
};

export const getPartnerTypeLabel = (type) => {
  const typeObj = PARTNER_TYPES.find(t => t.value === type);
  if (typeObj) return typeObj.label;
  const roleObj = EMPLOYEE_ROLES.find(r => r.value === type);
  return roleObj?.label || type;
};

export const getAvailableStatuses = (category = 'partner') => {
  return category === 'employee' ? EMPLOYEE_STATUSES : PARTNER_STATUSES;
};

export const formatPhoneNumber = (phone) => {
  if (!phone) return '';
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  return phone;
};

// Default export for convenience
const partnerRecruitingApi = {
  // Dashboard
  getDashboardStats,
  getPipelineMetrics,
  // Candidates
  getPartnerCandidates,
  getPartnerCandidate,
  createPartnerCandidate,
  updatePartnerCandidate,
  deletePartnerCandidate,
  updatePartnerStatus,
  // Employee Candidates
  createEmployeeCandidate,
  hireEmployeeCandidate,
  // Meetings
  getPartnerMeetings,
  scheduleMeeting,
  completeMeeting,
  cancelMeeting,
  // Proposals
  getPartnerProposals,
  createProposal,
  sendProposal,
  recordProposalResponse,
  // Onboarding
  onboardPartner,
  // Notes & Activities
  getPartnerNotes,
  addPartnerNote,
  getPartnerActivities,
  // Quick Actions
  logCall,
  logEmail,
  // Assessments
  getPartnerAssessment,
  updatePartnerAssessment,
  // Helpers
  getStatusColor,
  getStatusLabel,
  getPartnerTypeLabel,
  getAvailableStatuses,
  formatPhoneNumber,
  // Constants
  PARTNER_TYPES,
  PARTNER_STATUSES,
  EMPLOYEE_ROLES,
  EMPLOYEE_STATUSES,
  EMPLOYEE_SOURCES,
  MEETING_TYPES,
  MEETING_OUTCOMES,
  CALL_OUTCOMES,
  PARTNER_SOURCES
};

export default partnerRecruitingApi;
