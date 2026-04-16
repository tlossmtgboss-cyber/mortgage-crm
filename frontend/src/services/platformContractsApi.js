/**
 * Platform Contracts API Service
 *
 * Client-side API functions for managing licensing agreements, contracts,
 * and e-signed documents with CRM licensees.
 */
import { API_BASE_URL } from './api';
import { getToken } from '../utils/tokenStore';

const API_BASE = `${API_BASE_URL}/api/v1/platform-contracts`;

/**
 * Helper to handle API responses
 */
async function handleResponse(response) {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

/**
 * Get auth headers
 */
function getHeaders() {
  const token = getToken();
  return {
    'Authorization': token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

/**
 * Get auth headers for file upload (no Content-Type — browser sets multipart boundary)
 */
function getUploadHeaders() {
  const token = getToken();
  return {
    'Authorization': token ? `Bearer ${token}` : '',
  };
}

// =============================================================================
// Summary
// =============================================================================

/**
 * Get KPI summary cards
 */
export async function getContractsSummary() {
  const response = await fetch(`${API_BASE}/summary`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// CRUD
// =============================================================================

/**
 * List contracts with optional filters
 */
export async function listContracts({ status, contractType, search, page, limit } = {}) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (contractType) params.set('contract_type', contractType);
  if (search) params.set('search', search);
  if (page) params.set('page', String(page));
  if (limit) params.set('limit', String(limit));

  const url = `${API_BASE}/${params.toString() ? '?' + params.toString() : ''}`;
  const response = await fetch(url, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get single contract detail
 */
export async function getContract(contractId) {
  const response = await fetch(`${API_BASE}/${contractId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Create a draft contract
 */
export async function createContract(data) {
  const response = await fetch(`${API_BASE}/`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

/**
 * Update a contract
 */
export async function updateContract(contractId, data) {
  const response = await fetch(`${API_BASE}/${contractId}`, {
    method: 'PUT',
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

/**
 * Delete (or void) a contract
 */
export async function deleteContract(contractId) {
  const response = await fetch(`${API_BASE}/${contractId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// PDF & E-Sign
// =============================================================================

/**
 * Upload a contract PDF
 */
export async function uploadContractPdf(contractId, file) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE}/${contractId}/upload-pdf`, {
    method: 'POST',
    headers: getUploadHeaders(),
    body: formData,
  });
  return handleResponse(response);
}

/**
 * Get presigned download URL for contract PDF
 */
export async function getDownloadUrl(contractId, { signed = false } = {}) {
  const params = signed ? '?signed=true' : '';
  const response = await fetch(`${API_BASE}/${contractId}/download-url${params}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Send contract for e-signature
 */
export async function sendForSignature(contractId) {
  const response = await fetch(`${API_BASE}/${contractId}/send-for-signature`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse(response);
}

// =============================================================================
// Default export
// =============================================================================

export const platformContractsAPI = {
  getContractsSummary,
  listContracts,
  getContract,
  createContract,
  updateContract,
  deleteContract,
  uploadContractPdf,
  getDownloadUrl,
  sendForSignature,
};

export default platformContractsAPI;
