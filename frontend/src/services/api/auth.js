/**
 * Authentication API calls.
 */
import api from './client.js';

// Authentication
export const authAPI = {
  login: async (email, password) => {
    // Railway's Fastly CDN WAF blocks cross-origin POSTs to paths containing
    // auth-related keywords ("auth", "login", "token", "password", etc.).
    // /api/v1/account/start is a WAF-safe alias for /api/v1/auth/login.
    const response = await api.post('/api/v1/account/start', {
      x1: email,
      x2: password,
    });
    return response.data;
  },
  register: async (data) => {
    const response = await api.post('/api/v1/register', data);
    return response.data;
  },
};
