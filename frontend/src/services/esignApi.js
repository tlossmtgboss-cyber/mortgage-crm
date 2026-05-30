/**
 * E-Signature API Service
 *
 * Frontend API client for the e-signature system.
 * Handles envelope management, field placement, and signing sessions.
 *
 * Migrated from the retired utils/api/client to the canonical services/api/client:
 * - apiRequest() returns parsed response data and routes through the shared axios
 *   interceptors (auth + CSRF + token refresh), matching the prior data-returning
 *   behavior of the old `api` helper.
 * - Public (unauthenticated) borrower-signing endpoints used `{ skipAuth: true }`
 *   on the old client; they now use bare re-exported `axios` against the absolute
 *   URL so NO auth/CSRF headers are attached, preserving that behavior exactly.
 */

import { apiRequest, axios, API_BASE_URL } from './api/client';

const ESIGN_BASE = '/api/v1/esign';

// Public borrower-signing calls — no auth/CSRF interceptors. Unwrap data to
// match the old contract (callers await parsed data).
const publicGet = (url) => axios.get(`${API_BASE_URL}${url}`).then((r) => r.data);
const publicPost = (url, body) => axios.post(`${API_BASE_URL}${url}`, body).then((r) => r.data);

/**
 * E-Signature API methods
 */
export const esignApi = {
  // =========================================================================
  // ENVELOPE MANAGEMENT
  // =========================================================================

  /**
   * Create a new envelope from a PDF
   */
  createEnvelope: async (data) => {
    return apiRequest(`${ESIGN_BASE}/envelopes`, { method: 'POST', data });
  },

  /**
   * List envelopes with filters
   */
  listEnvelopes: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`${ESIGN_BASE}/envelopes${query ? `?${query}` : ''}`, { method: 'GET' });
  },

  /**
   * Get envelope details with signers and fields
   */
  getEnvelope: async (envelopeId) => {
    return apiRequest(`${ESIGN_BASE}/envelopes/${envelopeId}`, { method: 'GET' });
  },

  /**
   * Send envelope to signers
   */
  sendEnvelope: async (envelopeId) => {
    return apiRequest(`${ESIGN_BASE}/envelopes/${envelopeId}/send`, { method: 'POST' });
  },

  /**
   * Void an envelope
   */
  voidEnvelope: async (envelopeId, reason = null) => {
    return apiRequest(`${ESIGN_BASE}/envelopes/${envelopeId}/void`, { method: 'POST', data: { reason } });
  },

  // =========================================================================
  // SIGNER MANAGEMENT
  // =========================================================================

  /**
   * Add a signer to an envelope
   */
  addSigner: async (envelopeId, signer) => {
    return apiRequest(`${ESIGN_BASE}/envelopes/${envelopeId}/signers`, { method: 'POST', data: signer });
  },

  /**
   * Remove a signer from an envelope
   */
  removeSigner: async (envelopeId, signerId) => {
    return apiRequest(`${ESIGN_BASE}/envelopes/${envelopeId}/signers/${signerId}`, { method: 'DELETE' });
  },

  // =========================================================================
  // FIELD PLACEMENT
  // =========================================================================

  /**
   * Add a field to an envelope
   */
  addField: async (envelopeId, field) => {
    return apiRequest(`${ESIGN_BASE}/envelopes/${envelopeId}/fields`, { method: 'POST', data: field });
  },

  /**
   * Update a field
   */
  updateField: async (envelopeId, fieldId, updates) => {
    return apiRequest(`${ESIGN_BASE}/envelopes/${envelopeId}/fields/${fieldId}`, { method: 'PUT', data: updates });
  },

  /**
   * Delete a field
   */
  deleteField: async (envelopeId, fieldId) => {
    return apiRequest(`${ESIGN_BASE}/envelopes/${envelopeId}/fields/${fieldId}`, { method: 'DELETE' });
  },

  /**
   * Bulk save fields (replaces all existing fields)
   */
  bulkSaveFields: async (envelopeId, fields) => {
    return apiRequest(`${ESIGN_BASE}/envelopes/${envelopeId}/fields/bulk`, { method: 'POST', data: { fields } });
  },

  // =========================================================================
  // SIGNING SESSION (Public - No Auth)
  // =========================================================================

  /**
   * Validate signing token and get session data
   */
  validateSigningToken: async (token) => {
    return publicGet(`${ESIGN_BASE}/sign/${token}`);
  },

  /**
   * Get document URL for signing
   */
  getSigningDocument: async (token) => {
    return publicGet(`${ESIGN_BASE}/sign/${token}/document`);
  },

  /**
   * Adopt a typed signature
   */
  adoptSignature: async (token, signatureText, signatureFont) => {
    return publicPost(`${ESIGN_BASE}/sign/${token}/adopt`, {
      signature_text: signatureText,
      signature_font: signatureFont,
    });
  },

  /**
   * Submit a field value
   */
  submitFieldValue: async (token, fieldId, value) => {
    return publicPost(`${ESIGN_BASE}/sign/${token}/fields/${fieldId}`, {
      value,
    });
  },

  /**
   * Complete signing session
   */
  completeSigning: async (token) => {
    return publicPost(`${ESIGN_BASE}/sign/${token}/complete`, {});
  },

  // =========================================================================
  // DOCUMENT GENERATION
  // =========================================================================

  /**
   * Generate signed PDF and audit trail
   */
  generateSignedDocument: async (envelopeId) => {
    return apiRequest(`${ESIGN_BASE}/envelopes/${envelopeId}/generate`, { method: 'POST' });
  },

  /**
   * List completed documents for an envelope
   */
  listCompletedDocuments: async (envelopeId) => {
    return apiRequest(`${ESIGN_BASE}/envelopes/${envelopeId}/documents`, { method: 'GET' });
  },

  /**
   * Get audit trail for an envelope
   */
  getAuditTrail: async (envelopeId) => {
    return apiRequest(`${ESIGN_BASE}/envelopes/${envelopeId}/audit`, { method: 'GET' });
  },

  // =========================================================================
  // PDF UTILITIES
  // =========================================================================

  /**
   * Extract metadata from a PDF file
   */
  extractPdfMetadata: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest(`${ESIGN_BASE}/pdf/metadata`, {
      method: 'POST',
      data: formData,
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    });
  },
};

// =========================================================================
// COORDINATE TRANSFORMATION UTILITIES
// =========================================================================

/**
 * Convert screen coordinates to PDF points.
 * PDF coordinates: origin at bottom-left, 72 points per inch.
 *
 * @param {number} screenX - X position in screen pixels (from viewer left)
 * @param {number} screenY - Y position in screen pixels (from viewer top)
 * @param {DOMRect} viewerRect - Bounding rect of the PDF viewer
 * @param {Object} pageDimensions - { width_points, height_points }
 * @param {number} zoom - Current zoom level (100 = 100%)
 * @returns {{ x: number, y: number }} PDF point coordinates
 */
export function screenToPdfPoints(screenX, screenY, viewerRect, pageDimensions, zoom = 100) {
  // Scale factors
  const scaleX = pageDimensions.width_points / (viewerRect.width / (zoom / 100));
  const scaleY = pageDimensions.height_points / (viewerRect.height / (zoom / 100));

  // Convert X (direct mapping)
  const pdfX = screenX * scaleX;

  // Convert Y (flip from top-left to bottom-left origin)
  const pdfY = pageDimensions.height_points - (screenY * scaleY);

  return { x: pdfX, y: pdfY };
}

/**
 * Convert PDF points to screen coordinates for display.
 *
 * @param {number} pdfX - X position in PDF points
 * @param {number} pdfY - Y position in PDF points (from bottom)
 * @param {DOMRect} viewerRect - Bounding rect of the PDF viewer
 * @param {Object} pageDimensions - { width_points, height_points }
 * @param {number} zoom - Current zoom level (100 = 100%)
 * @returns {{ x: number, y: number }} Screen pixel coordinates
 */
export function pdfPointsToScreen(pdfX, pdfY, viewerRect, pageDimensions, zoom = 100) {
  // Scale factors
  const scaleX = (viewerRect.width / (zoom / 100)) / pageDimensions.width_points;
  const scaleY = (viewerRect.height / (zoom / 100)) / pageDimensions.height_points;

  // Convert X (direct mapping)
  const screenX = pdfX * scaleX;

  // Convert Y (flip from bottom-left to top-left origin)
  const screenY = (pageDimensions.height_points - pdfY) * scaleY;

  return { x: screenX, y: screenY };
}

/**
 * Convert PDF point dimensions to screen pixels.
 *
 * @param {number} widthPoints - Width in PDF points
 * @param {number} heightPoints - Height in PDF points
 * @param {DOMRect} viewerRect - Bounding rect of the PDF viewer
 * @param {Object} pageDimensions - { width_points, height_points }
 * @param {number} zoom - Current zoom level (100 = 100%)
 * @returns {{ width: number, height: number }} Screen pixel dimensions
 */
export function pdfSizeToScreen(widthPoints, heightPoints, viewerRect, pageDimensions, zoom = 100) {
  const scaleX = (viewerRect.width / (zoom / 100)) / pageDimensions.width_points;
  const scaleY = (viewerRect.height / (zoom / 100)) / pageDimensions.height_points;

  return {
    width: widthPoints * scaleX,
    height: heightPoints * scaleY,
  };
}

// =========================================================================
// FIELD TYPE CONFIGURATIONS
// =========================================================================

export const FIELD_TYPES = {
  signature: {
    label: 'Signature',
    icon: 'edit',
    defaultWidth: 200,
    defaultHeight: 50,
    widthPoints: 144,
    heightPoints: 36,
    color: '#1a73e8',
  },
  initial: {
    label: 'Initial',
    icon: 'create',
    defaultWidth: 80,
    defaultHeight: 40,
    widthPoints: 57.6,
    heightPoints: 28.8,
    color: '#7c4dff',
  },
  date_signed: {
    label: 'Date Signed',
    icon: 'event',
    defaultWidth: 120,
    defaultHeight: 30,
    widthPoints: 86.4,
    heightPoints: 21.6,
    color: '#00897b',
  },
  text: {
    label: 'Text',
    icon: 'text_fields',
    defaultWidth: 200,
    defaultHeight: 30,
    widthPoints: 144,
    heightPoints: 21.6,
    color: '#6d4c41',
  },
  checkbox: {
    label: 'Checkbox',
    icon: 'check_box',
    defaultWidth: 24,
    defaultHeight: 24,
    widthPoints: 17.28,
    heightPoints: 17.28,
    color: '#f4511e',
  },
  dropdown: {
    label: 'Dropdown',
    icon: 'arrow_drop_down_circle',
    defaultWidth: 180,
    defaultHeight: 30,
    widthPoints: 129.6,
    heightPoints: 21.6,
    color: '#5e35b1',
  },
};

// =========================================================================
// SIGNATURE FONTS (Google Fonts cursive styles)
// =========================================================================

export const SIGNATURE_FONTS = [
  { id: 'great_vibes', name: 'Great Vibes', family: "'Great Vibes', cursive" },
  { id: 'dancing_script', name: 'Dancing Script', family: "'Dancing Script', cursive" },
  { id: 'pacifico', name: 'Pacifico', family: "'Pacifico', cursive" },
  { id: 'sacramento', name: 'Sacramento', family: "'Sacramento', cursive" },
  { id: 'allura', name: 'Allura', family: "'Allura', cursive" },
];

export default esignApi;
