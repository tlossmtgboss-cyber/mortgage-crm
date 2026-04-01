/**
 * Content Marketing API Service
 *
 * Handles all API interactions for content marketing:
 * - Brand voice management
 * - Content calendars
 * - Content briefs
 * - SEO keywords
 */

// Use shared api instance for CSRF, auth, and impersonation support
import api from './api';

const API_BASE = '/api/v1/content-marketing';

// Both clients use the shared api; AI operations override timeout per-request
const apiClient = api;
const quickClient = api;

// ============ Brand Voice ============

export const listBrandVoices = async (activeOnly = true) => {
  const response = await quickClient.get(`${API_BASE}/brand-voice`, {
    params: { active_only: activeOnly }
  });
  return response.data;
};

export const getBrandVoice = async (profileId) => {
  const response = await quickClient.get(`${API_BASE}/brand-voice/${profileId}`);
  return response.data;
};

export const createBrandVoice = async (data) => {
  const response = await apiClient.post(`${API_BASE}/brand-voice`, data);
  return response.data;
};

export const updateBrandVoice = async (profileId, data) => {
  const response = await quickClient.put(`${API_BASE}/brand-voice/${profileId}`, data);
  return response.data;
};

export const deleteBrandVoice = async (profileId) => {
  const response = await quickClient.delete(`${API_BASE}/brand-voice/${profileId}`);
  return response.data;
};

export const analyzeBrandVoice = async (url) => {
  const response = await apiClient.post(`${API_BASE}/brand-voice/analyze`, null, {
    params: { url }
  });
  return response.data;
};

// ============ Content Calendars ============

export const listCalendars = async (params = {}) => {
  const response = await quickClient.get(`${API_BASE}/calendars`, { params });
  return response.data;
};

export const getCalendar = async (calendarId) => {
  const response = await quickClient.get(`${API_BASE}/calendars/${calendarId}`);
  return response.data;
};

export const createCalendar = async (data) => {
  const response = await apiClient.post(`${API_BASE}/calendars`, data);
  return response.data;
};

export const updateCalendar = async (calendarId, data) => {
  const response = await quickClient.put(`${API_BASE}/calendars/${calendarId}`, data);
  return response.data;
};

export const deleteCalendar = async (calendarId, deleteBriefs = false) => {
  const response = await quickClient.delete(`${API_BASE}/calendars/${calendarId}`, {
    params: { delete_briefs: deleteBriefs }
  });
  return response.data;
};

export const getCalendarStats = async (calendarId) => {
  const response = await quickClient.get(`${API_BASE}/calendars/${calendarId}/stats`);
  return response.data;
};

export const getCalendarWeekly = async (calendarId, weekStart) => {
  const response = await quickClient.get(`${API_BASE}/calendars/${calendarId}/weekly`, {
    params: { week_start: weekStart }
  });
  return response.data;
};

export const getCalendarMonthly = async (calendarId, year, month) => {
  const response = await quickClient.get(`${API_BASE}/calendars/${calendarId}/monthly`, {
    params: { year, month }
  });
  return response.data;
};

export const activateCalendar = async (calendarId) => {
  const response = await quickClient.post(`${API_BASE}/calendars/${calendarId}/activate`);
  return response.data;
};

export const pauseCalendar = async (calendarId) => {
  const response = await quickClient.post(`${API_BASE}/calendars/${calendarId}/pause`);
  return response.data;
};

export const generateCalendarBriefs = async (calendarId, regenerate = false) => {
  const response = await apiClient.post(`${API_BASE}/calendars/${calendarId}/generate-briefs`, null, {
    params: { regenerate }
  });
  return response.data;
};

// ============ Content Briefs ============

export const listBriefs = async (params = {}) => {
  const response = await quickClient.get(`${API_BASE}/briefs`, { params });
  return response.data;
};

export const getBrief = async (briefId) => {
  const response = await quickClient.get(`${API_BASE}/briefs/${briefId}`);
  return response.data;
};

export const createBrief = async (data) => {
  const response = await quickClient.post(`${API_BASE}/briefs`, data);
  return response.data;
};

export const updateBrief = async (briefId, data) => {
  const response = await quickClient.put(`${API_BASE}/briefs/${briefId}`, data);
  return response.data;
};

export const deleteBrief = async (briefId) => {
  const response = await quickClient.delete(`${API_BASE}/briefs/${briefId}`);
  return response.data;
};

export const getUpcomingBriefs = async (daysAhead = 7, status = null) => {
  const response = await quickClient.get(`${API_BASE}/briefs/upcoming`, {
    params: { days_ahead: daysAhead, status }
  });
  return response.data;
};

// ============ Comments ============

export const listComments = async (briefId) => {
  const response = await quickClient.get(`${API_BASE}/comments`, {
    params: { brief_id: briefId }
  });
  return response.data;
};

export const createComment = async (data) => {
  const response = await quickClient.post(`${API_BASE}/comments`, data);
  return response.data;
};

export const resolveComment = async (commentId) => {
  const response = await quickClient.post(`${API_BASE}/comments/${commentId}/resolve`);
  return response.data;
};

export const deleteComment = async (commentId) => {
  const response = await quickClient.delete(`${API_BASE}/comments/${commentId}`);
  return response.data;
};

// ============ Approvals ============

export const listApprovals = async (params = {}) => {
  const response = await quickClient.get(`${API_BASE}/approvals`, { params });
  return response.data;
};

export const requestApproval = async (data) => {
  const response = await quickClient.post(`${API_BASE}/approvals`, data);
  return response.data;
};

export const approveContent = async (approvalId, notes = null) => {
  const response = await quickClient.post(`${API_BASE}/approvals/${approvalId}/approve`, { notes });
  return response.data;
};

export const rejectContent = async (approvalId, notes = null) => {
  const response = await quickClient.post(`${API_BASE}/approvals/${approvalId}/reject`, { notes });
  return response.data;
};

export const requestChanges = async (approvalId, notes) => {
  const response = await quickClient.post(`${API_BASE}/approvals/${approvalId}/request-changes`, { notes });
  return response.data;
};

// ============ SEO Keywords ============

export const listKeywords = async (params = {}) => {
  const response = await quickClient.get(`${API_BASE}/keywords`, { params });
  return response.data;
};

export const getKeyword = async (keywordId) => {
  const response = await quickClient.get(`${API_BASE}/keywords/${keywordId}`);
  return response.data;
};

export const addKeyword = async (data) => {
  const response = await quickClient.post(`${API_BASE}/keywords`, data);
  return response.data;
};

export const updateKeyword = async (keywordId, data) => {
  const response = await quickClient.put(`${API_BASE}/keywords/${keywordId}`, data);
  return response.data;
};

export const deleteKeyword = async (keywordId) => {
  const response = await quickClient.delete(`${API_BASE}/keywords/${keywordId}`);
  return response.data;
};

export const getKeywordAnalytics = async () => {
  const response = await quickClient.get(`${API_BASE}/keywords/analytics`);
  return response.data;
};

export const updateKeywordRanking = async (keywordId, ranking, url = null) => {
  const response = await quickClient.post(`${API_BASE}/keywords/${keywordId}/ranking`, {
    ranking,
    url
  });
  return response.data;
};

// Export all functions as a named object
export const contentMarketingAPI = {
  // Brand Voice
  listBrandVoices,
  getBrandVoice,
  createBrandVoice,
  updateBrandVoice,
  deleteBrandVoice,
  analyzeBrandVoice,
  // Calendars
  listCalendars,
  getCalendar,
  createCalendar,
  updateCalendar,
  deleteCalendar,
  getCalendarStats,
  getCalendarWeekly,
  getCalendarMonthly,
  activateCalendar,
  pauseCalendar,
  generateCalendarBriefs,
  // Briefs
  listBriefs,
  getBrief,
  createBrief,
  updateBrief,
  deleteBrief,
  getUpcomingBriefs,
  // Comments
  listComments,
  createComment,
  resolveComment,
  deleteComment,
  // Approvals
  listApprovals,
  requestApproval,
  approveContent,
  rejectContent,
  requestChanges,
  // Keywords
  listKeywords,
  getKeyword,
  addKeyword,
  updateKeyword,
  deleteKeyword,
  getKeywordAnalytics,
  updateKeywordRanking,
};

export default contentMarketingAPI;
