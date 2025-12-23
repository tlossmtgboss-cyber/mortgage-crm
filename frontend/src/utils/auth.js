import { getItem, setItem, removeItem, getJSON, setJSON, STORAGE_KEYS } from './storage';

export const setAuth = async (token, user) => {
  await setItem(STORAGE_KEYS.TOKEN, token);
  await setJSON(STORAGE_KEYS.USER, user);
};

export const getAuth = async () => {
  const token = await getItem(STORAGE_KEYS.TOKEN);
  const user = await getJSON(STORAGE_KEYS.USER);
  return { token, user };
};

export const clearAuth = async () => {
  await removeItem(STORAGE_KEYS.TOKEN);
  await removeItem(STORAGE_KEYS.USER);
};

export const isAuthenticated = async () => {
  const token = await getItem(STORAGE_KEYS.TOKEN);
  return !!token;
};

// Synchronous versions for backwards compatibility (web only)
// These use localStorage directly and should only be used where async isn't possible
export const getAuthSync = () => {
  const token = localStorage.getItem(STORAGE_KEYS.TOKEN);
  const userStr = localStorage.getItem(STORAGE_KEYS.USER);
  const user = userStr ? JSON.parse(userStr) : null;
  return { token, user };
};

export const isAuthenticatedSync = () => {
  return !!localStorage.getItem(STORAGE_KEYS.TOKEN);
};

/**
 * Get authorization headers for API requests
 * Returns headers object with Bearer token and Content-Type
 * @returns {Object} Headers object with Authorization and Content-Type
 */
export const getAuthHeaders = () => {
  const token = localStorage.getItem(STORAGE_KEYS.TOKEN);
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
};

/**
 * Get authorization headers only if token exists
 * Returns headers with auth if logged in, just content-type if not
 * @returns {Object} Headers object
 */
export const getAuthHeadersIfPresent = () => {
  const token = localStorage.getItem(STORAGE_KEYS.TOKEN);
  if (token) {
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }
  return {
    'Content-Type': 'application/json'
  };
};
