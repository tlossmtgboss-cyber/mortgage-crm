/**
 * AI Daily Blog API Service
 *
 * Handles all API interactions for the blog content factory.
 */

// Use shared api instance for CSRF, auth, and impersonation support
import api from './api';

const API_BASE = '/api/v1/blog';

// Both clients use the shared api; AI generation requests override timeout per-request
const apiClient = api;
const quickClient = api;

// ============ Voice Profiles ============

export const getVoiceProfiles = async (activeOnly = true) => {
  const response = await quickClient.get(`${API_BASE}/voice-profiles`, {
    params: { active_only: activeOnly }
  });
  return response.data;
};

export const createVoiceProfile = async (data) => {
  const response = await quickClient.post(`${API_BASE}/voice-profiles`, data);
  return response.data;
};

export const updateVoiceProfile = async (profileId, data) => {
  const response = await quickClient.put(`${API_BASE}/voice-profiles/${profileId}`, data);
  return response.data;
};

export const deleteVoiceProfile = async (profileId) => {
  const response = await quickClient.delete(`${API_BASE}/voice-profiles/${profileId}`);
  return response.data;
};

// ============ Compliance Profiles ============

export const getComplianceProfiles = async (activeOnly = true) => {
  const response = await quickClient.get(`${API_BASE}/compliance-profiles`, {
    params: { active_only: activeOnly }
  });
  return response.data;
};

export const createComplianceProfile = async (data) => {
  const response = await quickClient.post(`${API_BASE}/compliance-profiles`, data);
  return response.data;
};

// ============ Source Documents ============

export const getSourceDocuments = async (processedOnly = false) => {
  const response = await quickClient.get(`${API_BASE}/source-documents`, {
    params: { processed_only: processedOnly }
  });
  return response.data;
};

export const uploadSourceDocument = async (file, title, author, rightsAttestation) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('title', title);
  if (author) formData.append('author', author);
  formData.append('rights_attestation', rightsAttestation);

  const response = await apiClient.post(`${API_BASE}/source-documents/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return response.data;
};

export const getSourceDocument = async (docId) => {
  const response = await quickClient.get(`${API_BASE}/source-documents/${docId}`);
  return response.data;
};

// ============ Campaigns ============

export const getCampaigns = async (activeOnly = true) => {
  const response = await quickClient.get(`${API_BASE}/campaigns`, {
    params: { active_only: activeOnly }
  });
  return response.data;
};

export const createCampaign = async (data) => {
  const response = await quickClient.post(`${API_BASE}/campaigns`, data);
  return response.data;
};

// ============ Content Generation ============

export const generateContent = async (data) => {
  const response = await apiClient.post(`${API_BASE}/content/generate`, data);
  return response.data;
};

export const getContentList = async (params = {}) => {
  const response = await quickClient.get(`${API_BASE}/content`, { params });
  return response.data;
};

export const getContent = async (contentId) => {
  const response = await quickClient.get(`${API_BASE}/content/${contentId}`);
  return response.data;
};

export const updateContent = async (contentId, data) => {
  const response = await quickClient.put(`${API_BASE}/content/${contentId}`, data);
  return response.data;
};

export const deleteContent = async (contentId) => {
  const response = await quickClient.delete(`${API_BASE}/content/${contentId}`);
  return response.data;
};

// ============ Topic Mining ============

export const mineTopics = async (sourceDocumentId, count = 10, campaignId = null) => {
  const response = await apiClient.post(`${API_BASE}/topics/mine`, {
    source_document_id: sourceDocumentId,
    count,
    campaign_id: campaignId
  });
  return response.data;
};

export const getTopics = async (campaignId = null, used = null) => {
  const response = await quickClient.get(`${API_BASE}/topics`, {
    params: { campaign_id: campaignId, used }
  });
  return response.data;
};

// ============ Compliance & Similarity ============

export const checkCompliance = async (content, complianceProfileId = null) => {
  const formData = new FormData();
  formData.append('content', content);
  if (complianceProfileId) {
    formData.append('compliance_profile_id', complianceProfileId);
  }
  const response = await apiClient.post(`${API_BASE}/compliance/check`, formData);
  return response.data;
};

export const checkSimilarity = async (content, sourceDocumentId = null) => {
  const formData = new FormData();
  formData.append('content', content);
  if (sourceDocumentId) {
    formData.append('source_document_id', sourceDocumentId);
  }
  const response = await apiClient.post(`${API_BASE}/similarity/check`, formData);
  return response.data;
};

// ============ User Settings ============

export const getUserSettings = async () => {
  const response = await quickClient.get(`${API_BASE}/settings`);
  return response.data;
};

export const updateUserSettings = async (data) => {
  const response = await quickClient.put(`${API_BASE}/settings`, data);
  return response.data;
};

// ============ Trending Topics ============

export const getTrendingTopics = async () => {
  const response = await quickClient.get(`${API_BASE}/trending-topics`);
  return response.data;
};

// ============ Analytics ============

export const getAnalyticsOverview = async (days = 30) => {
  const response = await quickClient.get(`${API_BASE}/analytics/overview`, {
    params: { days }
  });
  return response.data;
};

export const getContentPerformance = async (contentId) => {
  const response = await quickClient.get(`${API_BASE}/content/${contentId}/performance`);
  return response.data;
};

// ============ Status Check ============

export const getStatus = async () => {
  const response = await quickClient.get(`${API_BASE}/status`);
  return response.data;
};

// Export all functions as a named object for convenience
export const blogAPI = {
  // Voice Profiles
  getVoiceProfiles,
  createVoiceProfile,
  updateVoiceProfile,
  deleteVoiceProfile,
  // Compliance Profiles
  getComplianceProfiles,
  createComplianceProfile,
  // Source Documents
  getSourceDocuments,
  uploadSourceDocument,
  getSourceDocument,
  // Campaigns
  getCampaigns,
  createCampaign,
  // Content
  generateContent,
  getContentList,
  getContent,
  updateContent,
  deleteContent,
  // Topics
  mineTopics,
  getTopics,
  getTrendingTopics,
  // Compliance & Similarity
  checkCompliance,
  checkSimilarity,
  // Settings
  getUserSettings,
  updateUserSettings,
  // Analytics
  getAnalyticsOverview,
  getContentPerformance,
  // Status
  getStatus,
};

export default blogAPI;
