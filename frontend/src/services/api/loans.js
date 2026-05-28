/**
 * Loans API calls.
 */
import api, { ensureArray } from './client.js';

// Loans
export const loansAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/loans/', { params });
    return ensureArray(response.data, 'loans');
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/loans/${id}`);
    return response.data;
  },
  create: async (data, skipDuplicateCheck = false, retryCount = 0) => {
    const maxRetries = 2;
    try {
      const url = skipDuplicateCheck
        ? '/api/v1/loans/?skip_duplicate_check=true'
        : '/api/v1/loans/';
      const response = await api.post(url, data);
      return response.data;
    } catch (error) {
      // Retry on Network Error (up to maxRetries times)
      if ((error.retryable || error.message === 'Network Error') && retryCount < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1 second
        return loansAPI.create(data, skipDuplicateCheck, retryCount + 1);
      }

      // If 405 error, try without trailing slash as fallback
      if (error.response?.status === 405) {
        try {
          const url = skipDuplicateCheck
            ? '/api/v1/loans?skip_duplicate_check=true'
            : '/api/v1/loans';
          const retryResponse = await api.post(url, data);
          return retryResponse.data;
        } catch (retryError) {
          throw retryError;
        }
      }

      throw error;
    }
  },
  update: async (id, data) => {
    const response = await api.patch(`/api/v1/loans/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/loans/${id}`);
  },
  bulkDelete: async (loanIds) => {
    const response = await api.post('/api/v1/loans/bulk-delete', loanIds);
    return response.data;
  },
};
