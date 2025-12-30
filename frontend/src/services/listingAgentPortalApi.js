/**
 * Listing Agent Portal API Service
 *
 * Handles all API calls to the Listing Agent Portal backend endpoints.
 * Provides transaction-scoped access for listing agents to track loan progress.
 */

const API_BASE = process.env.REACT_APP_API_URL || '';

/**
 * Make an authenticated API request for listing agent portal
 */
async function apiRequest(endpoint, options = {}) {
  // Use portal session token (from magic link auth)
  const sessionToken = sessionStorage.getItem('listingAgentSessionToken');
  const authToken = localStorage.getItem('authToken');

  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...(sessionToken && { 'X-Portal-Session': sessionToken }),
      ...(authToken && { Authorization: `Bearer ${authToken}` }),
      ...options.headers,
    },
    ...options,
  };

  const response = await fetch(`${API_BASE}${endpoint}`, config);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'An error occurred' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

// =============================================================================
// AUTHENTICATION ENDPOINTS
// =============================================================================

export const authApi = {
  /**
   * Authenticate via magic link token
   */
  authenticateMagicLink: (token) =>
    apiRequest('/api/v1/listing-portal/auth/magic-link', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),

  /**
   * Get current session info
   */
  getSession: () =>
    apiRequest('/api/v1/listing-portal/auth/session'),

  /**
   * Refresh session
   */
  refreshSession: (sessionToken) =>
    apiRequest('/api/v1/listing-portal/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ session_token: sessionToken }),
    }),

  /**
   * Handle unsubscribe request
   */
  unsubscribe: (token, unsubscribeType = 'all') =>
    apiRequest('/api/v1/listing-portal/unsubscribe', {
      method: 'POST',
      body: JSON.stringify({ token, unsubscribe_type: unsubscribeType }),
    }),
};

// =============================================================================
// TRANSACTION ENDPOINTS
// =============================================================================

export const transactionApi = {
  /**
   * Get all transactions for the authenticated party
   */
  getTransactions: (status = null, limit = 50, offset = 0) => {
    let url = `/api/v1/listing-portal/transactions?limit=${limit}&offset=${offset}`;
    if (status) url += `&status=${status}`;
    return apiRequest(url);
  },

  /**
   * Get transaction details
   */
  getTransaction: (transactionId) =>
    apiRequest(`/api/v1/listing-portal/transactions/${transactionId}`),

  /**
   * Create a new transaction (LO only)
   */
  createTransaction: (transactionData) =>
    apiRequest('/api/v1/listing-portal/transactions', {
      method: 'POST',
      body: JSON.stringify(transactionData),
    }),

  /**
   * Update transaction status (LO only)
   */
  updateTransaction: (transactionId, updateData) =>
    apiRequest(`/api/v1/listing-portal/transactions/${transactionId}`, {
      method: 'PATCH',
      body: JSON.stringify(updateData),
    }),
};

// =============================================================================
// PARTY ENDPOINTS
// =============================================================================

export const partyApi = {
  /**
   * Get parties for a transaction
   */
  getParties: (transactionId) =>
    apiRequest(`/api/v1/listing-portal/transactions/${transactionId}/parties`),

  /**
   * Add a party to a transaction (LO only)
   */
  addParty: (transactionId, partyData) =>
    apiRequest(`/api/v1/listing-portal/transactions/${transactionId}/parties`, {
      method: 'POST',
      body: JSON.stringify(partyData),
    }),

  /**
   * Update party information
   */
  updateParty: (transactionId, partyId, updateData) =>
    apiRequest(`/api/v1/listing-portal/transactions/${transactionId}/parties/${partyId}`, {
      method: 'PATCH',
      body: JSON.stringify(updateData),
    }),

  /**
   * Remove a party from a transaction (LO only)
   */
  removeParty: (transactionId, partyId) =>
    apiRequest(`/api/v1/listing-portal/transactions/${transactionId}/parties/${partyId}`, {
      method: 'DELETE',
    }),
};

// =============================================================================
// MILESTONE ENDPOINTS
// =============================================================================

export const milestoneApi = {
  /**
   * Get milestones for a transaction
   */
  getMilestones: (transactionId) =>
    apiRequest(`/api/v1/listing-portal/transactions/${transactionId}/milestones`),

  /**
   * Update milestone status (LO only)
   */
  updateMilestone: (transactionId, milestoneId, updateData) =>
    apiRequest(`/api/v1/listing-portal/transactions/${transactionId}/milestones/${milestoneId}`, {
      method: 'PUT',
      body: JSON.stringify(updateData),
    }),
};

// =============================================================================
// MESSAGING ENDPOINTS
// =============================================================================

export const messagingApi = {
  /**
   * Get messages for a transaction
   */
  getMessages: (transactionId, limit = 50, offset = 0) =>
    apiRequest(`/api/v1/listing-portal/transactions/${transactionId}/messages?limit=${limit}&offset=${offset}`),

  /**
   * Send a message
   */
  sendMessage: (transactionId, content, attachments = null) =>
    apiRequest(`/api/v1/listing-portal/transactions/${transactionId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content, attachments }),
    }),

  /**
   * Mark messages as read
   */
  markAsRead: (transactionId, messageIds) =>
    apiRequest(`/api/v1/listing-portal/transactions/${transactionId}/messages/read`, {
      method: 'POST',
      body: JSON.stringify({ message_ids: messageIds }),
    }),
};

// =============================================================================
// PORTAL DASHBOARD ENDPOINTS
// =============================================================================

export const dashboardApi = {
  /**
   * Get portal dashboard data
   */
  getDashboard: () =>
    apiRequest('/api/v1/listing-portal/portal/dashboard'),

  /**
   * Get portal transaction view (PII-safe)
   */
  getPortalTransaction: (transactionId) =>
    apiRequest(`/api/v1/listing-portal/portal/transactions/${transactionId}`),
};

// =============================================================================
// INVITE ENDPOINTS
// =============================================================================

export const inviteApi = {
  /**
   * Send portal invite to a party (LO only)
   */
  sendInvite: (transactionId, partyId, channel = 'email') =>
    apiRequest(`/api/v1/listing-portal/transactions/${transactionId}/parties/${partyId}/invite`, {
      method: 'POST',
      body: JSON.stringify({ channel }),
    }),

  /**
   * Resend invite
   */
  resendInvite: (inviteId) =>
    apiRequest(`/api/v1/listing-portal/invites/${inviteId}/resend`, {
      method: 'POST',
    }),
};

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Store session token after magic link authentication
 */
export const storeSessionToken = (token) => {
  sessionStorage.setItem('listingAgentSessionToken', token);
};

/**
 * Clear session token
 */
export const clearSessionToken = () => {
  sessionStorage.removeItem('listingAgentSessionToken');
};

/**
 * Check if user has valid session
 */
export const hasValidSession = () => {
  return !!sessionStorage.getItem('listingAgentSessionToken');
};

// Export all APIs as default
export default {
  auth: authApi,
  transaction: transactionApi,
  party: partyApi,
  milestone: milestoneApi,
  messaging: messagingApi,
  dashboard: dashboardApi,
  invite: inviteApi,
  storeSessionToken,
  clearSessionToken,
  hasValidSession,
};
