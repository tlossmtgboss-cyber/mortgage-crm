/**
 * Perennia AI - API Client
 *
 * Enhanced fetch wrapper with error handling, retries, and timeouts.
 */

import { APIError, ErrorCode } from './errors';
import { getAuthHeaders } from '../auth';

// API base URL configuration
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const DEFAULT_BASE_URL = isProduction
  ? 'https://mortgage-crm-production-7a9a.up.railway.app'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

/**
 * Generate unique request ID for tracking
 */
function generateRequestId() {
  return `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Sleep utility for retry delays
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * API Client class with comprehensive error handling
 */
class APIClient {
  constructor(config = {}) {
    this.baseURL = config.baseURL || DEFAULT_BASE_URL;
    this.timeout = config.timeout || 15000;
    this.defaultHeaders = config.defaultHeaders || {};
    this.onUnauthorized = config.onUnauthorized || (() => {
      window.location.href = '/login';
    });
    this.onError = config.onError || ((error) => {
      console.error('API Error:', error.toJSON ? error.toJSON() : error);
    });
  }

  /**
   * Make API request with comprehensive error handling
   *
   * @param {string} endpoint - API endpoint (e.g., '/api/v1/settings')
   * @param {Object} options - Request options
   * @returns {Promise<any>} Response data
   */
  async request(endpoint, options = {}) {
    const {
      timeout = this.timeout,
      retry = 0,
      retryDelay = 1000,
      body,
      skipAuth = false,
      ...fetchOptions
    } = options;

    const url = `${this.baseURL}${endpoint}`;
    const requestId = generateRequestId();

    // Prepare headers
    const headers = {
      'Content-Type': 'application/json',
      'X-Request-ID': requestId,
      ...this.defaultHeaders,
      ...(skipAuth ? {} : getAuthHeaders()),
      ...(fetchOptions.headers || {}),
    };

    // Remove Content-Type for FormData
    if (body instanceof FormData) {
      delete headers['Content-Type'];
    }

    // Prepare request options
    const requestOptions = {
      ...fetchOptions,
      headers,
      body: body instanceof FormData ? body : (body ? JSON.stringify(body) : undefined),
    };

    // Create abort controller for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    requestOptions.signal = controller.signal;

    try {
      // Make request
      const response = await fetch(url, requestOptions);
      clearTimeout(timeoutId);

      // Parse response
      let data;
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        data = await response.json();
      } else {
        data = await response.text();
      }

      // Handle error response
      if (!response.ok) {
        const error = typeof data === 'object' && data.message
          ? APIError.fromResponse(data, response.status)
          : new APIError(
              data || `Request failed with status ${response.status}`,
              ErrorCode.SERVER_ERROR,
              { statusCode: response.status }
            );

        // Handle unauthorized
        if (error.requiresAuth()) {
          this.onUnauthorized();
        }

        // Trigger error callback
        this.onError(error);

        throw error;
      }

      // Return data (handle both {success, data} and raw responses)
      return data.data !== undefined ? data.data : data;

    } catch (error) {
      clearTimeout(timeoutId);

      // Convert to APIError if needed
      let apiError;

      if (error instanceof APIError) {
        apiError = error;
      } else if (error instanceof Error) {
        apiError = APIError.fromNativeError(error);
      } else {
        apiError = new APIError('Unknown error occurred', ErrorCode.UNKNOWN_ERROR);
      }

      // Retry logic for recoverable errors
      if (retry > 0 && apiError.isRecoverable()) {
        await sleep(retryDelay);
        return this.request(endpoint, {
          ...options,
          retry: retry - 1,
          retryDelay: retryDelay * 2, // Exponential backoff
        });
      }

      throw apiError;
    }
  }

  /**
   * GET request
   */
  async get(endpoint, options = {}) {
    return this.request(endpoint, {
      ...options,
      method: 'GET',
    });
  }

  /**
   * POST request
   */
  async post(endpoint, body, options = {}) {
    return this.request(endpoint, {
      ...options,
      method: 'POST',
      body,
    });
  }

  /**
   * PUT request
   */
  async put(endpoint, body, options = {}) {
    return this.request(endpoint, {
      ...options,
      method: 'PUT',
      body,
    });
  }

  /**
   * PATCH request
   */
  async patch(endpoint, body, options = {}) {
    return this.request(endpoint, {
      ...options,
      method: 'PATCH',
      body,
    });
  }

  /**
   * DELETE request
   */
  async delete(endpoint, options = {}) {
    return this.request(endpoint, {
      ...options,
      method: 'DELETE',
    });
  }

  /**
   * Upload file(s)
   */
  async upload(endpoint, files, additionalData = {}, options = {}) {
    const formData = new FormData();

    // Handle single file or array of files
    if (Array.isArray(files)) {
      files.forEach((file, index) => {
        formData.append('files', file);
      });
    } else {
      formData.append('file', files);
    }

    // Add additional form data
    Object.entries(additionalData).forEach(([key, value]) => {
      formData.append(key, value);
    });

    return this.request(endpoint, {
      ...options,
      method: 'POST',
      body: formData,
      timeout: options.timeout || 60000, // Longer timeout for uploads
    });
  }
}

// Create singleton instance
export const apiClient = new APIClient();

// Export class for custom instances
export { APIClient };

// Convenience exports
export const api = {
  get: (endpoint, options) => apiClient.get(endpoint, options),
  post: (endpoint, body, options) => apiClient.post(endpoint, body, options),
  put: (endpoint, body, options) => apiClient.put(endpoint, body, options),
  patch: (endpoint, body, options) => apiClient.patch(endpoint, body, options),
  delete: (endpoint, options) => apiClient.delete(endpoint, options),
  upload: (endpoint, files, data, options) => apiClient.upload(endpoint, files, data, options),
};

export default apiClient;
