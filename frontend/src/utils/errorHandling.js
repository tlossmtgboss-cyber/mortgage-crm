/**
 * Perennia AI - Error Handling Utilities
 *
 * Provides React hooks and utilities for consistent error handling
 * across settings pages and forms.
 */

import { useState, useCallback, useRef } from 'react';
import { toast } from './toast';

// Re-export from api/errors for convenience
export { APIError, ValidationError, ErrorCode } from './api/errors';

/**
 * Hook for handling async operations with loading, error, and success states
 *
 * @param {Object} options - Configuration options
 * @param {Function} options.onSuccess - Callback on successful operation
 * @param {Function} options.onError - Callback on error
 * @param {boolean} options.showSuccessToast - Show toast on success (default: true)
 * @param {boolean} options.showErrorToast - Show toast on error (default: true)
 * @param {string} options.successMessage - Custom success message
 * @param {string} options.errorMessage - Custom error message prefix
 *
 * @returns {Object} - { execute, loading, error, data, reset }
 */
export function useAsyncOperation(options = {}) {
  const {
    onSuccess,
    onError,
    showSuccessToast = true,
    showErrorToast = true,
    successMessage = 'Operation completed successfully',
    errorMessage = 'Operation failed',
  } = options;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  // Track if component is mounted to avoid state updates after unmount
  const mountedRef = useRef(true);

  /**
   * Execute an async operation with automatic state management
   *
   * @param {Function} asyncFn - The async function to execute
   * @param {Object} executeOptions - Per-call options override
   * @returns {Promise} - Resolves with data or rejects with error
   */
  const execute = useCallback(async (asyncFn, executeOptions = {}) => {
    const finalOptions = { ...options, ...executeOptions };

    setLoading(true);
    setError(null);

    try {
      const result = await asyncFn();

      if (!mountedRef.current) return result;

      setData(result);
      setLoading(false);

      if (finalOptions.showSuccessToast !== false) {
        toast.success(finalOptions.successMessage || successMessage);
      }

      if (finalOptions.onSuccess) {
        finalOptions.onSuccess(result);
      } else if (onSuccess) {
        onSuccess(result);
      }

      return result;
    } catch (err) {
      if (!mountedRef.current) throw err;

      const errorObj = normalizeError(err);
      setError(errorObj);
      setLoading(false);

      if (finalOptions.showErrorToast !== false) {
        const message = errorObj.getUserMessage
          ? errorObj.getUserMessage()
          : errorObj.message || finalOptions.errorMessage || errorMessage;
        toast.error(message);
      }

      if (finalOptions.onError) {
        finalOptions.onError(errorObj);
      } else if (onError) {
        onError(errorObj);
      }

      throw errorObj;
    }
  }, [onSuccess, onError, showSuccessToast, showErrorToast, successMessage, errorMessage, options]);

  /**
   * Reset state to initial values
   */
  const reset = useCallback(() => {
    setLoading(false);
    setError(null);
    setData(null);
  }, []);

  // Cleanup on unmount
  useState(() => {
    return () => {
      mountedRef.current = false;
    };
  });

  return {
    execute,
    loading,
    error,
    data,
    reset,
    isLoading: loading, // Alias for convenience
    isError: !!error,
    isSuccess: !!data && !error && !loading,
  };
}

/**
 * Hook for handling form submissions with validation and error handling
 *
 * @param {Object} options - Configuration options
 * @param {Function} options.onSubmit - The submit handler function
 * @param {Function} options.validate - Optional validation function
 * @param {Function} options.onSuccess - Callback on successful submission
 * @param {Function} options.onError - Callback on error
 * @param {boolean} options.showSuccessToast - Show toast on success (default: true)
 * @param {boolean} options.showErrorToast - Show toast on error (default: true)
 * @param {string} options.successMessage - Custom success message
 * @param {boolean} options.resetOnSuccess - Reset form state on success (default: false)
 *
 * @returns {Object} - { handleSubmit, submitting, errors, setErrors, resetErrors }
 */
export function useFormSubmit(options = {}) {
  const {
    onSubmit,
    validate,
    onSuccess,
    onError,
    showSuccessToast = true,
    showErrorToast = true,
    successMessage = 'Changes saved successfully',
    resetOnSuccess = false,
  } = options;

  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);

  /**
   * Handle form submission
   *
   * @param {Object} formData - The form data to submit
   * @param {Event} event - Optional form event
   * @returns {Promise} - Resolves with result or rejects with error
   */
  const handleSubmit = useCallback(async (formData, event) => {
    // Prevent default form submission if event provided
    if (event && event.preventDefault) {
      event.preventDefault();
    }

    // Reset errors
    setErrors({});
    setSubmitError(null);

    // Run validation if provided
    if (validate) {
      const validationErrors = validate(formData);
      if (validationErrors && Object.keys(validationErrors).length > 0) {
        setErrors(validationErrors);

        if (showErrorToast) {
          toast.error('Please fix the errors before submitting');
        }

        return Promise.reject(new Error('Validation failed'));
      }
    }

    setSubmitting(true);

    try {
      let result;
      if (onSubmit) {
        result = await onSubmit(formData);
      }

      setSubmitting(false);

      if (showSuccessToast) {
        toast.success(successMessage);
      }

      if (onSuccess) {
        onSuccess(result);
      }

      if (resetOnSuccess) {
        setErrors({});
      }

      return result;
    } catch (err) {
      setSubmitting(false);

      const errorObj = normalizeError(err);
      setSubmitError(errorObj);

      // Handle field-specific validation errors from backend
      if (errorObj.fieldErrors) {
        setErrors(errorObj.fieldErrors);
      } else if (errorObj.details?.fieldErrors) {
        setErrors(errorObj.details.fieldErrors);
      }

      if (showErrorToast) {
        const message = errorObj.getUserMessage
          ? errorObj.getUserMessage()
          : errorObj.message || 'Failed to save changes';
        toast.error(message);
      }

      if (onError) {
        onError(errorObj);
      }

      throw errorObj;
    }
  }, [onSubmit, validate, onSuccess, onError, showSuccessToast, showErrorToast, successMessage, resetOnSuccess]);

  /**
   * Reset all error states
   */
  const resetErrors = useCallback(() => {
    setErrors({});
    setSubmitError(null);
  }, []);

  /**
   * Set a specific field error
   */
  const setFieldError = useCallback((field, message) => {
    setErrors(prev => ({
      ...prev,
      [field]: message,
    }));
  }, []);

  /**
   * Clear a specific field error
   */
  const clearFieldError = useCallback((field) => {
    setErrors(prev => {
      const newErrors = { ...prev };
      delete newErrors[field];
      return newErrors;
    });
  }, []);

  return {
    handleSubmit,
    submitting,
    isSubmitting: submitting, // Alias
    errors,
    submitError,
    setErrors,
    setFieldError,
    clearFieldError,
    resetErrors,
    hasErrors: Object.keys(errors).length > 0,
  };
}

/**
 * Normalize various error types to a consistent format
 *
 * @param {Error|Object|string} error - The error to normalize
 * @returns {Object} - Normalized error object
 */
export function normalizeError(error) {
  // Already an API error with getUserMessage
  if (error && typeof error.getUserMessage === 'function') {
    return error;
  }

  // Backend error response
  if (error && error.message && error.error_code) {
    return {
      message: error.message,
      code: error.error_code,
      details: error.details,
      fieldErrors: error.details?.fieldErrors || error.field_errors,
      getUserMessage: () => error.message,
      isRecoverable: () => ['NETWORK_ERROR', 'TIMEOUT', 'SERVER_ERROR'].includes(error.error_code),
    };
  }

  // Fetch response error
  if (error && error.status && error.statusText) {
    return {
      message: `Request failed: ${error.statusText}`,
      code: 'HTTP_ERROR',
      statusCode: error.status,
      getUserMessage: () => getHttpErrorMessage(error.status),
      isRecoverable: () => error.status >= 500,
    };
  }

  // Standard Error object
  if (error instanceof Error) {
    return {
      message: error.message,
      code: 'UNKNOWN_ERROR',
      stack: error.stack,
      getUserMessage: () => error.message || 'An unexpected error occurred',
      isRecoverable: () => false,
    };
  }

  // String error
  if (typeof error === 'string') {
    return {
      message: error,
      code: 'UNKNOWN_ERROR',
      getUserMessage: () => error,
      isRecoverable: () => false,
    };
  }

  // Unknown error type
  return {
    message: 'An unexpected error occurred',
    code: 'UNKNOWN_ERROR',
    getUserMessage: () => 'An unexpected error occurred',
    isRecoverable: () => false,
  };
}

/**
 * Get user-friendly message for HTTP status codes
 */
function getHttpErrorMessage(status) {
  const messages = {
    400: 'Invalid request. Please check your input.',
    401: 'Please log in to continue.',
    403: 'You don\'t have permission to perform this action.',
    404: 'The requested resource was not found.',
    408: 'Request timed out. Please try again.',
    409: 'This conflicts with existing data.',
    422: 'The data provided is invalid.',
    429: 'Too many requests. Please wait a moment.',
    500: 'Server error. Please try again later.',
    502: 'Service temporarily unavailable.',
    503: 'Service unavailable. Please try again later.',
    504: 'Request timed out. Please try again.',
  };

  return messages[status] || `Request failed with status ${status}`;
}

/**
 * Create a wrapper for API calls with automatic error handling
 *
 * @param {Function} apiCall - The API function to wrap
 * @param {Object} options - Error handling options
 * @returns {Function} - Wrapped function with error handling
 */
export function withErrorHandling(apiCall, options = {}) {
  return async (...args) => {
    try {
      const response = await apiCall(...args);

      // Check if response indicates an error
      if (response && response.status === 'error') {
        throw normalizeError(response);
      }

      return response;
    } catch (error) {
      const normalizedError = normalizeError(error);

      if (options.showToast !== false) {
        toast.error(normalizedError.getUserMessage());
      }

      if (options.onError) {
        options.onError(normalizedError);
      }

      throw normalizedError;
    }
  };
}

/**
 * Retry an async operation with exponential backoff
 *
 * @param {Function} fn - Async function to retry
 * @param {Object} options - Retry options
 * @returns {Promise} - Result of successful call
 */
export async function retryWithBackoff(fn, options = {}) {
  const {
    maxRetries = 3,
    initialDelay = 1000,
    maxDelay = 10000,
    shouldRetry = (error) => error.isRecoverable?.() ?? false,
  } = options;

  let lastError;
  let delay = initialDelay;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = normalizeError(error);

      // Don't retry if error is not recoverable or we're out of retries
      if (!shouldRetry(lastError) || attempt === maxRetries) {
        throw lastError;
      }

      // Wait before retrying
      await new Promise(resolve => setTimeout(resolve, delay));

      // Exponential backoff
      delay = Math.min(delay * 2, maxDelay);
    }
  }

  throw lastError;
}

export default {
  useAsyncOperation,
  useFormSubmit,
  normalizeError,
  withErrorHandling,
  retryWithBackoff,
};
