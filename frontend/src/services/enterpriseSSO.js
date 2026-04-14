/**
 * Enterprise SSO (Single Sign-On) Service
 *
 * Handles SAML/OIDC SSO authentication flow for enterprise customers,
 * optimized for Capacitor WebView on mobile (iOS/Android).
 *
 * Flow:
 * 1. Check if email domain has SSO configured (discovery)
 * 2. Generate PKCE code verifier/challenge for mobile OAuth2
 * 3. Open SSO provider auth URL in in-app browser
 * 4. Capture redirect via deep link / Universal Link
 * 5. Exchange auth tokens via backend
 * 6. Store tokens securely and proceed to app
 */

import { Capacitor } from '@capacitor/core';
import { App as CapApp } from '@capacitor/app';
import { setAuth, clearAuth } from '../utils/auth';
import { setItem, getItem, removeItem, STORAGE_KEYS } from '../utils/storage';
import { API_BASE_URL } from './api';

const isNative = Capacitor.isNativePlatform();

// Lazy-load @capacitor/browser — it's an optional dependency.
// If not installed, the SSO flow falls back to window.open on web.
// Install with: npm install @capacitor/browser
let _Browser = null;
async function getBrowser() {
  if (_Browser) return _Browser;
  try {
    const mod = await import('@capacitor/browser');
    _Browser = mod.Browser;
    return _Browser;
  } catch {
    // @capacitor/browser not installed — fallback handled in initiateSSO
    return null;
  }
}

// SSO-specific storage keys
const SSO_KEYS = {
  CODE_VERIFIER: 'sso_code_verifier',
  SSO_STATE: 'sso_state',
  SSO_PROVIDER: 'sso_provider',
  SSO_SESSION: 'sso_session',
  SSO_REFRESH_TOKEN: 'sso_refresh_token',
};

// =============================================================================
// PKCE (Proof Key for Code Exchange) — required for mobile OAuth2
// =============================================================================

/**
 * Generate a cryptographically random code verifier for PKCE.
 * @returns {string} A 43-128 character URL-safe random string.
 */
function generateCodeVerifier() {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return base64UrlEncode(array);
}

/**
 * Generate a code challenge from a code verifier using SHA-256.
 * @param {string} verifier - The code verifier.
 * @returns {Promise<string>} The base64url-encoded SHA-256 hash.
 */
async function generateCodeChallenge(verifier) {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return base64UrlEncode(new Uint8Array(digest));
}

/**
 * Base64url encode a Uint8Array (RFC 7636 compliant).
 * @param {Uint8Array} buffer
 * @returns {string}
 */
function base64UrlEncode(buffer) {
  let str = '';
  for (let i = 0; i < buffer.length; i++) {
    str += String.fromCharCode(buffer[i]);
  }
  return btoa(str)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

/**
 * Generate a random state parameter for CSRF protection.
 * @returns {string}
 */
function generateState() {
  const array = new Uint8Array(24);
  crypto.getRandomValues(array);
  return base64UrlEncode(array);
}


// =============================================================================
// SSO DISCOVERY
// =============================================================================

/**
 * Check if an email domain has SSO configured.
 *
 * @param {string} email - User's email address.
 * @returns {Promise<{
 *   hasSso: boolean,
 *   providerType: string|null,
 *   providerName: string|null,
 *   authUrl: string|null,
 *   organizationName: string|null
 * }>}
 */
async function checkSSOConfig(email) {
  if (!email || !email.includes('@')) {
    return { hasSso: false, providerType: null, providerName: null, authUrl: null, organizationName: null };
  }

  const domain = email.split('@')[1].toLowerCase();

  // Skip common public email domains — they never have enterprise SSO
  const publicDomains = [
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com',
    'icloud.com', 'live.com', 'msn.com', 'protonmail.com', 'proton.me',
    'mail.com', 'zoho.com', 'yandex.com', 'gmx.com', 'tutanota.com',
  ];
  if (publicDomains.includes(domain)) {
    return { hasSso: false, providerType: null, providerName: null, authUrl: null, organizationName: null };
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/auth/sso/discover?domain=${encodeURIComponent(domain)}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      return { hasSso: false, providerType: null, providerName: null, authUrl: null, organizationName: null };
    }

    const data = await response.json();

    return {
      hasSso: data.has_sso || false,
      providerType: data.provider_type || null,
      providerName: data.provider_name || null,
      authUrl: data.auth_url || null,
      organizationName: data.organization_name || null,
    };
  } catch (error) {
    console.error('SSO discovery failed:', error);
    return { hasSso: false, providerType: null, providerName: null, authUrl: null, organizationName: null };
  }
}


// =============================================================================
// SSO AUTHENTICATION FLOW
// =============================================================================

/**
 * Initiate SSO login flow.
 *
 * On mobile (Capacitor): Opens the SSO provider URL in an in-app browser
 * (SafariViewController on iOS / Chrome Custom Tabs on Android) and listens
 * for the redirect via Universal Links.
 *
 * On web: Redirects the current window to the SSO provider URL.
 *
 * @param {string} authUrl - The SSO auth URL from discovery.
 * @param {object} [options] - Additional options.
 * @param {function} [options.onSuccess] - Called with { token, user } on success.
 * @param {function} [options.onError] - Called with error message on failure.
 * @returns {Promise<void>}
 */
async function initiateSSO(authUrl, options = {}) {
  const { onSuccess, onError } = options;

  try {
    // Generate PKCE parameters
    const codeVerifier = generateCodeVerifier();
    const codeChallenge = await generateCodeChallenge(codeVerifier);
    const state = generateState();

    // Store PKCE verifier and state for callback validation
    await setItem(SSO_KEYS.CODE_VERIFIER, codeVerifier);
    await setItem(SSO_KEYS.SSO_STATE, state);

    // Append PKCE and state to auth URL
    const separator = authUrl.includes('?') ? '&' : '?';
    const fullAuthUrl = `${authUrl}${separator}code_challenge=${codeChallenge}&code_challenge_method=S256&state=${state}`;

    if (isNative) {
      // Mobile: open in-app browser (SafariViewController / Chrome Custom Tabs)
      const Browser = await getBrowser();

      // Set up deep link listener BEFORE opening browser
      const urlListener = await CapApp.addListener('appUrlOpen', async (event) => {
        const url = event.url;

        // Check if this is our SSO callback
        if (url.includes('/sso/callback') || url.includes('/auth/sso/callback')) {
          // Close the in-app browser
          if (Browser) {
            try {
              await Browser.close();
            } catch (closeErr) {
              // Browser may already be closed
              console.debug('Browser close:', closeErr);
            }
          }

          // Remove the listener
          urlListener.remove();

          // Process the callback
          try {
            const result = await handleSSOCallback(url);
            if (onSuccess) onSuccess(result);
          } catch (callbackError) {
            console.error('SSO callback processing failed:', callbackError);
            if (onError) onError(callbackError.message || 'SSO authentication failed');
          }
        }
      });

      if (Browser) {
        // Also listen for browser close without completing SSO
        const browserListener = await Browser.addListener('browserFinished', () => {
          // User may have closed the browser manually
          browserListener.remove();
          // Give a small delay to see if the URL listener fires first
          setTimeout(() => {
            urlListener.remove();
          }, 2000);
        });

        // Open the SSO URL in SafariViewController / Chrome Custom Tabs
        await Browser.open({
          url: fullAuthUrl,
          presentationStyle: 'popover',
          toolbarColor: '#1a73e8',
        });
      } else {
        // @capacitor/browser not installed — fall back to window.open
        console.warn('SSO: @capacitor/browser not available, falling back to window.open');
        window.open(fullAuthUrl, '_blank');
      }

    } else {
      // Web: redirect to SSO URL, callback will come via page redirect
      // Store state in sessionStorage for web callback handling
      sessionStorage.setItem('sso_state', state);
      sessionStorage.setItem('sso_code_verifier', codeVerifier);
      window.location.href = fullAuthUrl;
    }
  } catch (error) {
    console.error('SSO initiation failed:', error);
    // Clean up stored PKCE data
    await removeItem(SSO_KEYS.CODE_VERIFIER);
    await removeItem(SSO_KEYS.SSO_STATE);
    if (onError) onError(error.message || 'Failed to start SSO login');
    throw error;
  }
}


/**
 * Handle the SSO callback URL (after redirect from IdP).
 *
 * Extracts tokens from the callback URL and validates them
 * with the backend.
 *
 * @param {string} callbackUrl - The full callback URL with query params.
 * @returns {Promise<{ token: string, user: object }>}
 */
async function handleSSOCallback(callbackUrl) {
  let url;
  try {
    url = new URL(callbackUrl);
  } catch (e) {
    // Handle deep link schemes like com.perenniaai.crm://...
    // by converting to a parseable format
    const queryStart = callbackUrl.indexOf('?');
    if (queryStart === -1) throw new Error('No query parameters in SSO callback');
    const fakeUrl = `https://placeholder${callbackUrl.substring(callbackUrl.indexOf('/sso/callback'))}`;
    url = new URL(fakeUrl);
  }

  const params = url.searchParams;
  const accessToken = params.get('access_token');
  const refreshToken = params.get('refresh_token');
  const error = params.get('error');
  const errorDescription = params.get('error_description');

  if (error) {
    throw new Error(errorDescription || error || 'SSO authentication failed');
  }

  if (!accessToken) {
    throw new Error('No access token received from SSO provider');
  }

  // Validate state if we have one stored
  const storedState = isNative
    ? await getItem(SSO_KEYS.SSO_STATE)
    : sessionStorage.getItem('sso_state');
  const returnedState = params.get('state');

  if (storedState && returnedState && storedState !== returnedState) {
    throw new Error('SSO state mismatch - possible CSRF attack');
  }

  // Exchange the token with our backend to get full user info
  const exchangeResponse = await fetch(`${API_BASE_URL}/api/v1/auth/sso/exchange`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      access_token: accessToken,
      refresh_token: refreshToken,
    }),
  });

  if (!exchangeResponse.ok) {
    const errorData = await exchangeResponse.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to validate SSO token');
  }

  const data = await exchangeResponse.json();

  // Store auth tokens and user data (including refresh token for proactive refresh)
  await setAuth(data.access_token, data.user, data.refresh_token);

  // Store SSO-specific data for refresh flow
  if (data.refresh_token) {
    await setItem(SSO_KEYS.SSO_REFRESH_TOKEN, data.refresh_token);
  }
  await setItem(SSO_KEYS.SSO_SESSION, JSON.stringify({
    provider: data.user?.sso_provider || 'sso',
    authenticatedAt: new Date().toISOString(),
  }));

  // Clean up PKCE data
  await removeItem(SSO_KEYS.CODE_VERIFIER);
  await removeItem(SSO_KEYS.SSO_STATE);
  if (!isNative) {
    sessionStorage.removeItem('sso_state');
    sessionStorage.removeItem('sso_code_verifier');
  }

  return {
    token: data.access_token,
    user: data.user,
  };
}


// =============================================================================
// TOKEN MANAGEMENT
// =============================================================================

/**
 * Check if the current session is an SSO session.
 * @returns {Promise<boolean>}
 */
async function isSSOSession() {
  const session = await getItem(SSO_KEYS.SSO_SESSION);
  return !!session;
}

/**
 * Refresh the SSO session token.
 * Uses the stored refresh token to get a new access token.
 *
 * @returns {Promise<{ token: string }|null>} New token or null if refresh fails.
 */
async function refreshSSOToken() {
  const refreshToken = await getItem(SSO_KEYS.SSO_REFRESH_TOKEN);
  if (!refreshToken) {
    return null;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/account/renew`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      // Refresh token expired — clear SSO session
      await clearSSOSession();
      return null;
    }

    const data = await response.json();

    // Update stored token (pass refresh token for proactive refresh)
    const currentUser = await getItem(STORAGE_KEYS.USER);
    const user = currentUser ? JSON.parse(currentUser) : null;
    if (user) {
      await setAuth(data.access_token, user, data.refresh_token);
    }

    // Update refresh token if a new one was issued
    if (data.refresh_token) {
      await setItem(SSO_KEYS.SSO_REFRESH_TOKEN, data.refresh_token);
    }

    return { token: data.access_token };
  } catch (error) {
    console.error('SSO token refresh failed:', error);
    return null;
  }
}

/**
 * Clear SSO session data and log out.
 * @returns {Promise<void>}
 */
async function clearSSOSession() {
  await clearAuth();
  await removeItem(SSO_KEYS.SSO_SESSION);
  await removeItem(SSO_KEYS.SSO_REFRESH_TOKEN);
  await removeItem(SSO_KEYS.CODE_VERIFIER);
  await removeItem(SSO_KEYS.SSO_STATE);
  await removeItem(SSO_KEYS.SSO_PROVIDER);
}

/**
 * Get the SSO session info.
 * @returns {Promise<{ provider: string, authenticatedAt: string }|null>}
 */
async function getSSOSessionInfo() {
  const session = await getItem(SSO_KEYS.SSO_SESSION);
  if (!session) return null;
  try {
    return JSON.parse(session);
  } catch {
    return null;
  }
}


// =============================================================================
// PROVIDER DISPLAY HELPERS
// =============================================================================

/**
 * Get a display-friendly name for the SSO provider.
 * @param {string} providerName - Provider identifier from discovery.
 * @returns {string}
 */
function getProviderDisplayName(providerName) {
  const names = {
    okta: 'Okta',
    azure_ad: 'Microsoft Entra ID',
    google: 'Google Workspace',
    auth0: 'Auth0',
    onelogin: 'OneLogin',
    ping_identity: 'Ping Identity',
    generic: 'SSO',
  };
  return names[providerName] || 'SSO';
}

/**
 * Get the provider's brand color for UI styling.
 * @param {string} providerName
 * @returns {string} Hex color.
 */
function getProviderColor(providerName) {
  const colors = {
    okta: '#007dc1',
    azure_ad: '#0078d4',
    google: '#4285f4',
    auth0: '#eb5424',
    onelogin: '#2c3e50',
    ping_identity: '#b71c1c',
    generic: '#1a73e8',
  };
  return colors[providerName] || '#1a73e8';
}


// =============================================================================
// EXPORTS
// =============================================================================

export {
  checkSSOConfig,
  initiateSSO,
  handleSSOCallback,
  isSSOSession,
  refreshSSOToken,
  clearSSOSession,
  getSSOSessionInfo,
  getProviderDisplayName,
  getProviderColor,
  generateCodeVerifier,
  generateCodeChallenge,
  SSO_KEYS,
};

export default {
  checkSSOConfig,
  initiateSSO,
  handleSSOCallback,
  isSSOSession,
  refreshSSOToken,
  clearSSOSession,
  getSSOSessionInfo,
  getProviderDisplayName,
  getProviderColor,
};
