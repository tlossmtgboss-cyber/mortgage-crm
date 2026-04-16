import { getToken } from '../utils/tokenStore';

/**
 * Document Review API Service
 *
 * API client for document extraction, comparison, and review endpoints.
 */

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

/**
 * Get auth headers for API requests
 */
const getHeaders = () => {
  const token = getToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
  };
};

/**
 * Trigger AI extraction for a document
 * @param {number} documentId - Document ID
 * @returns {Promise<Object>} Extraction result with fields, confidence, owner detection
 */
export const extractDocumentData = async (documentId) => {
  const response = await fetch(
    `${API_BASE}/api/v1/smart-docs/document/${documentId}/extract`,
    {
      method: 'POST',
      headers: getHeaders(),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Extraction failed');
  }

  return response.json();
};

/**
 * Get existing extraction results for a document
 * @param {number} documentId - Document ID
 * @returns {Promise<Object>} Extraction data
 */
export const getDocumentExtraction = async (documentId) => {
  const response = await fetch(
    `${API_BASE}/api/v1/smart-docs/document/${documentId}/extraction`,
    {
      method: 'GET',
      headers: getHeaders(),
    }
  );

  if (!response.ok) {
    if (response.status === 404) {
      return null; // No extraction yet
    }
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to get extraction');
  }

  return response.json();
};

/**
 * Get field comparison between extracted data and profile
 * @param {number} documentId - Document ID
 * @param {string} profileType - 'lead' or 'loan'
 * @param {number} profileId - Profile ID
 * @returns {Promise<Object>} Comparison data with conflicts highlighted
 */
export const getFieldComparison = async (documentId, profileType = 'lead', profileId = null) => {
  const params = new URLSearchParams({ profile_type: profileType });
  if (profileId) {
    params.append('profile_id', profileId);
  }

  const response = await fetch(
    `${API_BASE}/api/v1/smart-docs/document/${documentId}/comparison?${params}`,
    {
      method: 'GET',
      headers: getHeaders(),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to get comparison');
  }

  return response.json();
};

/**
 * Apply selected extracted fields to a profile
 * @param {number} documentId - Document ID
 * @param {string} profileType - 'lead' or 'loan'
 * @param {number} profileId - Profile ID
 * @param {Array} fieldsToApply - Array of {field_name, action, value}
 * @returns {Promise<Object>} Apply result
 */
export const applyExtractedFields = async (documentId, profileType, profileId, fieldsToApply) => {
  const response = await fetch(
    `${API_BASE}/api/v1/smart-docs/document/${documentId}/apply-fields`,
    {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        profile_type: profileType,
        profile_id: profileId,
        fields_to_apply: fieldsToApply,
      }),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to apply fields');
  }

  return response.json();
};

/**
 * Update document display name
 * @param {number} documentId - Document ID
 * @param {string} displayName - New display name
 * @returns {Promise<Object>} Update result
 */
export const updateDocumentName = async (documentId, displayName) => {
  const response = await fetch(
    `${API_BASE}/api/v1/smart-docs/document/${documentId}/name`,
    {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify({ display_name: displayName }),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to update name');
  }

  return response.json();
};

/**
 * Approve a document after review
 * @param {number} documentId - Document ID
 * @param {Object} options - Approval options
 * @param {string} options.reviewer - Reviewer name/ID
 * @param {string} options.assignedOwner - 'BORROWER' or 'CO_BORROWER'
 * @param {Object} options.applyFields - Optional fields to apply
 * @param {string} options.notes - Optional notes
 * @returns {Promise<Object>} Approval result
 */
export const approveDocument = async (documentId, options = {}) => {
  const { reviewer, assignedOwner, applyFields, notes } = options;

  const body = {
    reviewer: reviewer || 'user',
    assigned_owner: assignedOwner,
    notes,
  };

  if (applyFields) {
    body.apply_fields = applyFields;
  }

  const response = await fetch(
    `${API_BASE}/api/v1/smart-docs/document/${documentId}/review-approve`,
    {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(body),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to approve document');
  }

  return response.json();
};

/**
 * Get document details including presigned URL
 * @param {number} documentId - Document ID
 * @returns {Promise<Object>} Document details
 */
export const getDocumentDetails = async (documentId) => {
  const response = await fetch(
    `${API_BASE}/api/v1/smart-docs/document/${documentId}`,
    {
      method: 'GET',
      headers: getHeaders(),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to get document');
  }

  return response.json();
};

/**
 * Get document download URL
 * @param {number} documentId - Document ID
 * @returns {Promise<Object>} Download URL info
 */
export const getDocumentDownloadUrl = async (documentId) => {
  const response = await fetch(
    `${API_BASE}/api/v1/smart-docs/document/${documentId}/download`,
    {
      method: 'GET',
      headers: getHeaders(),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to get download URL');
  }

  return response.json();
};

export default {
  extractDocumentData,
  getDocumentExtraction,
  getFieldComparison,
  applyExtractedFields,
  updateDocumentName,
  approveDocument,
  getDocumentDetails,
  getDocumentDownloadUrl,
};
