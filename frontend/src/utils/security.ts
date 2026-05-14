/**
 * Security Utilities for Frontend
 *
 * Provides CSRF protection and secure authentication helpers.
 */

import { getAuthHeaders as getBaseAuthHeaders } from './auth';
import { API_BASE_URL } from '../services/api';
import { clearTokens, getToken } from '../utils/tokenStore';

// CSRF token handling
let csrfToken: string | null = null;

/**
 * Get CSRF token from cookie
 */
export const getCSRFTokenFromCookie = (): string | null => {
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
export const getCSRFToken = async (): Promise<string | null> => {
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
        csrfToken = data.csrf_token as string;
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
export const clearCSRFToken = (): void => {
  csrfToken = null;
};

/**
 * Get headers for API requests with CSRF protection
 *
 * Use this for all state-changing requests (POST, PUT, PATCH, DELETE)
 */
export const getSecureHeaders = async (): Promise<Record<string, string>> => {
  const baseHeaders = getBaseAuthHeaders();
  const token = await getCSRFToken();

  return {
    ...baseHeaders,
    ...(token ? { 'X-CSRF-Token': token } : {}),
  };
};

/**
 * Secure fetch wrapper that automatically includes CSRF token
 */
export const secureFetch = async (
  url: string,
  options: RequestInit = {}
): Promise<Response> => {
  const method = ((options.method as string) || 'GET').toUpperCase();
  const needsCSRF = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
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
export const isSessionAuthenticated = (): boolean => {
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
export const secureLogout = async (): Promise<void> => {
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
export const sanitizeHTML = (str: string | null | undefined): string => {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
};

/**
 * Validate URL to prevent javascript: and data: URLs
 */
export const isValidURL = (url: string | null | undefined): boolean => {
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
