/**
 * Security Utilities for Frontend
 *
 * Provides CSRF protection and secure authentication helpers.
 *
 * MIGRATION GUIDE:
 * 1. Import { getSecureAuthHeaders } instead of { getAuthHeaders }
 * 2. CSRF tokens are automatically included for state-changing requests
 * 3. Eventually, auth will move to HttpOnly cookies (transparent to frontend)
 */

import { getAuthHeaders as getBaseAuthHeaders } from './auth';
import { API_BASE_URL } from '../services/api';
import { clearTokens, getToken } from '../utils/tokenStore';

// CSRF token handling
let csrfToken = null;

/**
 * Get CSRF token from cookie
 */
export const getCSRFTokenFromCookie = () => {
  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === 'csrf_token') {
      return decodeURIComponent(value);
    }
  }
  return null;
};

/**
 * Fetch CSRF token from server if not already cached
 */
export const getCSRFToken = async () => {
  // Try cookie first
  const cookieToken = getCSRFTokenFromCookie();
  if (cookieToken) {
    csrfToken = cookieToken;
    return csrfToken;
  }

  // If no cookie, fetch from server
  if (!csrfToken) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/csrf-token`, {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        csrfToken = data.csrf_token;
      }
    } catch (error) {
      console.warn('Could not fetch CSRF token:', error);
    }
  }
  return csrfToken;
};

/**
 * Clear cached CSRF token (call on logout)
 */
export const clearCSRFToken = () => {
  csrfToken = null;
};

/**
 * Get headers for API requests with CSRF protection
 *
 * Use this for all state-changing requests (POST, PUT, PATCH, DELETE)
 */
export const getSecureHeaders = async () => {
  const baseHeaders = getBaseAuthHeaders();
  const token = await getCSRFToken();

  return {
    ...baseHeaders,
    ...(token ? { 'X-CSRF-Token': token } : {}),
  };
};

/**
 * Secure fetch wrapper that automatically includes CSRF token
 *
 * Usage:
 *   const response = await secureFetch('/api/v1/leads', {
 *     method: 'POST',
 *     body: JSON.stringify(data),
 *   });
 */
export const secureFetch = async (url, options = {}) => {
  const method = (options.method || 'GET').toUpperCase();
  const needsCSRF = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  // Add CSRF token for state-changing requests
  if (needsCSRF) {
    const csrfToken = await getCSRFToken();
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }
  }

  return fetch(url, {
    ...options,
    headers,
    credentials: 'include', // Always include cookies
  });
};

/**
 * Check if the current session is authenticated
 * Works with both localStorage tokens and HttpOnly cookies
 */
export const isSessionAuthenticated = () => {
  // Check localStorage (current implementation)
  const token = getToken();
  if (token) return true;

  // Check for auth cookie presence (future implementation)
  // Note: We can't read HttpOnly cookies, but we can check for non-HttpOnly session indicator
  const hasSessionCookie = document.cookie.includes('session_active=');
  return hasSessionCookie;
};

/**
 * Logout helper that clears all auth state
 */
export const secureLogout = async () => {
  try {
    // Call logout endpoint to clear HttpOnly cookies and blacklist token
    await secureFetch('/api/v1/account/signoff', {
      method: 'POST',
    });
  } catch (error) {
    console.warn('Logout request failed:', error);
  }

  // Clear localStorage (current implementation)
  await clearTokens();
  localStorage.removeItem('impersonation');

  // Clear CSRF token
  clearCSRFToken();

  // Redirect to login
  window.location.href = '/login';
};

/**
 * Sanitize user input to prevent XSS
 * Use this when displaying user-generated content
 */
export const sanitizeHTML = (str) => {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
};

/**
 * Validate URL to prevent javascript: and data: URLs
 */
export const isValidURL = (url) => {
  if (!url) return false;
  try {
    const parsed = new URL(url, window.location.origin);
    return ['http:', 'https:'].includes(parsed.protocol);
  } catch {
    return false;
  }
};

export default {
  getCSRFToken,
  getCSRFTokenFromCookie,
  clearCSRFToken,
  getSecureHeaders,
  secureFetch,
  isSessionAuthenticated,
  secureLogout,
  sanitizeHTML,
  isValidURL,
};
