/**
 * Onboarding API Service
 * Handles all API calls related to employee onboarding and invites
 */

const API_BASE = 'https://mortgage-crm-production-7a9a.up.railway.app';

// Helper to get auth headers
const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
};

// ============== ONBOARDING WIZARD ==============

/**
 * Start a new onboarding session
 * @param {string|null} inviteToken - Optional invite token
 */
export const startOnboarding = async (inviteToken = null) => {
  const response = await fetch(`${API_BASE}/api/v1/onboarding/start`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      invite_token: inviteToken
    })
  });

  if (!response.ok) {
    throw new Error('Failed to start onboarding');
  }

  return response.json();
};

/**
 * Resume an existing onboarding session
 */
export const resumeOnboarding = async () => {
  const response = await fetch(`${API_BASE}/api/v1/onboarding/resume`, {
    headers: getAuthHeaders()
  });

  if (response.status === 404) {
    return null; // No existing session
  }

  if (!response.ok) {
    throw new Error('Failed to resume onboarding');
  }

  return response.json();
};

/**
 * Auto-save step data
 * @param {number} stepNumber - The step number (1-5)
 * @param {Object} stepData - The data to save
 */
export const autoSaveStep = async (stepNumber, stepData) => {
  const response = await fetch(`${API_BASE}/api/v1/onboarding/auto-save`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      step_number: stepNumber,
      step_data: stepData
    })
  });

  if (!response.ok) {
    throw new Error('Failed to auto-save');
  }

  return response.json();
};

/**
 * Save step data
 * @param {number} stepNumber - The step number (1-5)
 * @param {Object} data - The step data to save
 */
export const saveStepData = async (stepNumber, data) => {
  const response = await fetch(`${API_BASE}/api/v1/onboarding/step-${stepNumber}/save`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to save step');
  }

  return response.json();
};

/**
 * Mark a step as complete
 * @param {number} stepNumber - The step number (1-5)
 */
export const completeStep = async (stepNumber) => {
  const response = await fetch(`${API_BASE}/api/v1/onboarding/step/${stepNumber}/complete`, {
    method: 'POST',
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to complete step');
  }

  return response.json();
};

/**
 * Complete the entire onboarding process
 * @param {string|null} inviteToken - Optional invite token
 */
export const completeOnboarding = async (inviteToken = null) => {
  const response = await fetch(`${API_BASE}/api/v1/onboarding/complete`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      invite_token: inviteToken
    })
  });

  if (!response.ok) {
    throw new Error('Failed to complete onboarding');
  }

  return response.json();
};

// ============== INVITE MANAGEMENT ==============

/**
 * Validate an invite token (public endpoint)
 * @param {string} token - The invite token
 */
export const validateInviteToken = async (token) => {
  const response = await fetch(`${API_BASE}/api/invite/${token}`);

  if (response.status === 404) {
    return { valid: false, error: 'Invite not found' };
  }

  if (response.status === 400) {
    const data = await response.json();
    return { valid: false, error: data.detail || 'Invalid invite' };
  }

  if (!response.ok) {
    throw new Error('Failed to validate invite');
  }

  const data = await response.json();
  return { valid: true, ...data };
};

/**
 * Accept an invite and create user account
 * @param {string} token - The invite token
 * @param {Object} data - Object containing password
 */
export const acceptInvite = async (token, data) => {
  const response = await fetch(`${API_BASE}/api/invite/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password: data.password })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to accept invite');
  }

  return response.json();
};

/**
 * Create a new employee invite (admin only)
 * @param {Object} inviteData - The invite data
 */
export const createInvite = async (inviteData) => {
  const response = await fetch(`${API_BASE}/api/admin/users/onboarding`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(inviteData)
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create invite');
  }

  return response.json();
};

/**
 * Check if email is available for invite
 * @param {string} email - The email to check
 */
export const checkEmailAvailability = async (email) => {
  const response = await fetch(`${API_BASE}/api/admin/users/check-email?email=${encodeURIComponent(email)}`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to check email');
  }

  return response.json();
};

/**
 * List all invites (admin only)
 * @param {string|null} status - Optional status filter (pending, accepted, expired, revoked)
 */
export const listInvites = async (status = null) => {
  const url = status
    ? `${API_BASE}/api/admin/invites?status=${status}`
    : `${API_BASE}/api/admin/invites`;

  const response = await fetch(url, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to fetch invites');
  }

  return response.json();
};

/**
 * List pending invites (admin only)
 */
export const listPendingInvites = async () => {
  return listInvites('pending');
};

/**
 * Revoke an invite (admin only)
 * @param {number} inviteId - The invite ID
 */
export const revokeInvite = async (inviteId) => {
  const response = await fetch(`${API_BASE}/api/admin/invites/${inviteId}/revoke`, {
    method: 'POST',
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to revoke invite');
  }

  return response.json();
};

/**
 * Get onboarding options (roles, branches, pages, responsibilities)
 */
export const getOnboardingOptions = async () => {
  const response = await fetch(`${API_BASE}/api/user-onboarding/options`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to fetch onboarding options');
  }

  return response.json();
};

/**
 * Get permissions preview for a role
 * @param {string} role - The role to preview
 */
export const getRolePermissionsPreview = async (role) => {
  const response = await fetch(`${API_BASE}/api/user-onboarding/permissions-preview/${role}`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to fetch role permissions');
  }

  return response.json();
};

// ============== VERIFICATION ==============

/**
 * Send email verification code
 * @param {string} email - The email to verify
 */
export const sendEmailVerification = async (email) => {
  const response = await fetch(`${API_BASE}/api/v1/onboarding/step-1/send-email-verification`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ email })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to send verification email');
  }

  return response.json();
};

/**
 * Verify email code
 * @param {string} email - The email
 * @param {string} code - The verification code
 */
export const verifyEmailCode = async (email, code) => {
  const response = await fetch(`${API_BASE}/api/v1/onboarding/step-1/verify-email`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ email, code })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Invalid verification code');
  }

  return response.json();
};

/**
 * Send SMS verification code
 * @param {string} phone - The phone number to verify
 */
export const sendPhoneVerification = async (phone) => {
  const response = await fetch(`${API_BASE}/api/v1/onboarding/step-1/send-sms-verification`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ phone })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to send verification SMS');
  }

  return response.json();
};

/**
 * Verify phone code
 * @param {string} phone - The phone number
 * @param {string} code - The verification code
 */
export const verifyPhoneCode = async (phone, code) => {
  const response = await fetch(`${API_BASE}/api/v1/onboarding/step-1/verify-sms`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ phone, code })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Invalid verification code');
  }

  return response.json();
};

// ============== AI QUICK ACTIONS ==============

/**
 * Get available AI quick actions for the current user
 */
export const getAvailableQuickActions = async () => {
  const response = await fetch(`${API_BASE}/api/ai/quick-actions`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to fetch quick actions');
  }

  return response.json();
};

// ============== USER PERMISSIONS ==============

/**
 * Get user's page permissions
 */
export const getUserPagePermissions = async () => {
  const response = await fetch(`${API_BASE}/api/v1/users/me/permissions`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to fetch permissions');
  }

  return response.json();
};

/**
 * Update user's AI preferences
 * @param {Object} preferences - The AI preferences
 */
export const updateAIPreferences = async (preferences) => {
  const response = await fetch(`${API_BASE}/api/v1/users/me/ai-preferences`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(preferences)
  });

  if (!response.ok) {
    throw new Error('Failed to update AI preferences');
  }

  return response.json();
};

export default {
  // Onboarding wizard
  startOnboarding,
  resumeOnboarding,
  autoSaveStep,
  saveStepData,
  completeStep,
  completeOnboarding,
  // Invite management
  validateInviteToken,
  acceptInvite,
  createInvite,
  checkEmailAvailability,
  listInvites,
  listPendingInvites,
  revokeInvite,
  getOnboardingOptions,
  getRolePermissionsPreview,
  // Verification
  sendEmailVerification,
  verifyEmailCode,
  sendPhoneVerification,
  verifyPhoneCode,
  // AI quick actions
  getAvailableQuickActions,
  // User permissions
  getUserPagePermissions,
  updateAIPreferences
};
