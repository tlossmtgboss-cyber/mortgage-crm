/**
 * Listing Agent Portal API Service
 *
 * Client-side API functions for the transaction-scoped listing agent portal.
 * Provides both admin (LO) and public portal (listing agent) endpoints.
 */
import { API_BASE_URL } from './api';
import { getToken } from '../utils/tokenStore';

const API_BASE = `${API_BASE_URL}/api/v1/listing-portal`;

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
 * Get auth headers for LO/admin requests
 */
function getHeaders() {
  const token = getToken();
  return {
    'Authorization': token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

/**
 * Get portal session headers for listing agent requests
 */
function getPortalHeaders() {
  const sessionToken = localStorage.getItem('listing_portal_session');
  return {
    'X-Session-Token': sessionToken || '',
    'Content-Type': 'application/json',
  };
}

// =============================================================================
// ADMIN ROUTES (For Loan Officers)
// =============================================================================

/**
 * Create a new listing transaction from a loan
 */
export async function createTransaction(data) {
  const response = await fetch(`${API_BASE}/transactions`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

/**
 * List all transactions for the current organization
 */
export async function listTransactions() {
  const response = await fetch(`${API_BASE}/transactions`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get transaction details with parties and milestones
 */
export async function getTransaction(transactionId) {
  const response = await fetch(`${API_BASE}/transactions/${transactionId}`, {
    headers: getHeaders(),
  });
  return handleResponse(response);
}

/**
 * Add a party (listing agent, escrow officer, etc.) to a transaction
 */
export async function addParty(transactionId, data) {
  const response = await fetch(`${API_BASE}/transactions/${transactionId}/parties`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

/**
 * Send portal invite email with magic link to a party
 */
export async function sendPortalInvite(transactionId, partyId) {
  const response = await fetch(
    `${API_BASE}/transactions/${transactionId}/parties/${partyId}/invite`,
    {
      method: 'POST',
      headers: getHeaders(),
    }
  );
  return handleResponse(response);
}

/**
 * Update a milestone status
 */
export async function updateMilestone(transactionId, milestoneId, data) {
  const response = await fetch(
    `${API_BASE}/transactions/${transactionId}/milestones/${milestoneId}`,
    {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(data),
    }
  );
  return handleResponse(response);
}

/**
 * Send a message as the loan officer
 */
export async function sendMessageAsLO(transactionId, content) {
  const response = await fetch(`${API_BASE}/transactions/${transactionId}/messages`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ content }),
  });
  return handleResponse(response);
}

/**
 * Get messages for a transaction (as LO)
 */
export async function getMessages(transactionId, limit = 50, offset = 0) {
  const response = await fetch(
    `${API_BASE}/transactions/${transactionId}/messages?limit=${limit}&offset=${offset}`,
    {
      headers: getHeaders(),
    }
  );
  return handleResponse(response);
}

// =============================================================================
// PUBLIC PORTAL ROUTES (For Listing Agents via Magic Link)
// =============================================================================

/**
 * Authenticate using a magic link token
 */
export async function authenticateMagicLink(token) {
  const response = await fetch(`${API_BASE}/auth/magic-link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  return handleResponse(response);
}

/**
 * Validate the current session
 */
export async function validateSession() {
  const response = await fetch(`${API_BASE}/auth/session`, {
    headers: getPortalHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get portal dashboard data
 */
export async function getPortalDashboard() {
  const response = await fetch(`${API_BASE}/portal/dashboard`, {
    headers: getPortalHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get messages in the portal
 */
export async function getPortalMessages(limit = 50, offset = 0) {
  const response = await fetch(
    `${API_BASE}/portal/messages?limit=${limit}&offset=${offset}`,
    {
      headers: getPortalHeaders(),
    }
  );
  return handleResponse(response);
}

/**
 * Send a message as a party in the portal
 */
export async function sendPortalMessage(content) {
  const response = await fetch(`${API_BASE}/portal/messages`, {
    method: 'POST',
    headers: getPortalHeaders(),
    body: JSON.stringify({ content }),
  });
  return handleResponse(response);
}

// =============================================================================
// SESSION MANAGEMENT
// =============================================================================

/**
 * Store portal session token
 */
export function storePortalSession(sessionToken) {
  localStorage.setItem('listing_portal_session', sessionToken);
}

/**
 * Clear portal session token
 */
export function clearPortalSession() {
  localStorage.removeItem('listing_portal_session');
}

/**
 * Check if portal session exists
 */
export function hasPortalSession() {
  return !!localStorage.getItem('listing_portal_session');
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Format currency for display
 */
export function formatCurrency(amount) {
  if (!amount) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Format date for display
 */
export function formatDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

/**
 * Get status display info
 */
export function getStatusInfo(status) {
  const statusMap = {
    active: { label: 'Active', color: '#3b82f6', bg: '#eff6ff' },
    pending: { label: 'Pending', color: '#f59e0b', bg: '#fffbeb' },
    closing: { label: 'Closing', color: '#B8924A', bg: '#FDF9F0' },
    closed: { label: 'Closed', color: '#2D7A52', bg: '#ecfdf5' },
    cancelled: { label: 'Cancelled', color: '#ef4444', bg: '#fef2f2' },
    on_hold: { label: 'On Hold', color: '#6b7280', bg: '#f3f4f6' },
  };
  return statusMap[status] || { label: status, color: '#6b7280', bg: '#f3f4f6' };
}

/**
 * Get milestone status display info
 */
export function getMilestoneStatusInfo(status) {
  const statusMap = {
    pending: { label: 'Pending', color: '#6b7280', icon: '○' },
    in_progress: { label: 'In Progress', color: '#3b82f6', icon: '◐' },
    completed: { label: 'Completed', color: '#2D7A52', icon: '●' },
    skipped: { label: 'Skipped', color: '#9ca3af', icon: '—' },
    blocked: { label: 'Blocked', color: '#ef4444', icon: '!' },
  };
  return statusMap[status] || { label: status, color: '#6b7280', icon: '?' };
}

/**
 * Get party role display name
 */
export function getRoleDisplayName(role) {
  const roleMap = {
    listing_agent: 'Listing Agent',
    selling_agent: 'Selling Agent',
    escrow_officer: 'Escrow Officer',
    title_officer: 'Title Officer',
    attorney: 'Attorney',
    other: 'Other',
  };
  return roleMap[role] || role;
}

export default {
  // Admin routes
  createTransaction,
  listTransactions,
  getTransaction,
  addParty,
  sendPortalInvite,
  updateMilestone,
  sendMessageAsLO,
  getMessages,
  // Portal routes
  authenticateMagicLink,
  validateSession,
  getPortalDashboard,
  getPortalMessages,
  sendPortalMessage,
  // Session management
  storePortalSession,
  clearPortalSession,
  hasPortalSession,
  // Utilities
  formatCurrency,
  formatDate,
  getStatusInfo,
  getMilestoneStatusInfo,
  getRoleDisplayName,
};
