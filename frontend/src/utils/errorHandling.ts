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

// ── Types ────────────────────────────────────────────────────

export interface NormalizedError {
  message: string;
  code: string;
  statusCode?: number;
  stack?: string;
  details?: { fieldErrors?: Record<string, string> };
  fieldErrors?: Record<string, string>;
  getUserMessage: () => string;
  isRecoverable: () => boolean;
}

export interface UseAsyncOperationOptions<T = unknown> {
  onSuccess?: (result: T) => void;
  onError?: (error: NormalizedError) => void;
  showSuccessToast?: boolean;
  showErrorToast?: boolean;
  successMessage?: string;
  errorMessage?: string;
}

export interface UseAsyncOperationReturn<T = unknown> {
  execute: (asyncFn: () => Promise<T>, executeOptions?: UseAsyncOperationOptions<T>) => Promise<T>;
  loading: boolean;
  error: NormalizedError | null;
  data: T | null;
  reset: () => void;
  isLoading: boolean;
  isError: boolean;
  isSuccess: boolean;
}

export interface UseFormSubmitOptions<T = unknown, R = unknown> {
  onSubmit?: (formData: T) => Promise<R>;
  validate?: (formData: T) => Record<string, string> | null;
  onSuccess?: (result: R) => void;
  onError?: (error: NormalizedError) => void;
  showSuccessToast?: boolean;
  showErrorToast?: boolean;
  successMessage?: string;
  resetOnSuccess?: boolean;
}

export interface UseFormSubmitReturn<T = unknown, R = unknown> {
  handleSubmit: (formData: T, event?: Event) => Promise<R>;
  submitting: boolean;
  isSubmitting: boolean;
  errors: Record<string, string>;
  submitError: NormalizedError | null;
  setErrors: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setFieldError: (field: string, message: string) => void;
  clearFieldError: (field: string) => void;
  resetErrors: () => void;
  hasErrors: boolean;
}

export interface WithErrorHandlingOptions {
  showToast?: boolean;
  onError?: (error: NormalizedError) => void;
}

export interface RetryOptions {
  maxRetries?: number;
  initialDelay?: number;
  maxDelay?: number;
  shouldRetry?: (error: NormalizedError) => boolean;
}

/**
 * Hook for handling async operations with loading, error, and success states
 */
export function useAsyncOperation<T = unknown>(
  options: UseAsyncOperationOptions<T> = {}
): UseAsyncOperationReturn<T> {
  const {
    onSuccess,
    onError,
    showSuccessToast = true,
    showErrorToast = true,
    successMessage = 'Operation completed successfully',
    errorMessage = 'Operation failed',
  } = options;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<NormalizedError | null>(null);
  const [data, setData] = useState<T | null>(null);

  // Track if component is mounted to avoid state updates after unmount
  const mountedRef = useRef(true);

  /**
   * Execute an async operation with automatic state management
   */
  const execute = useCallback(async (
    asyncFn: () => Promise<T>,
    executeOptions: UseAsyncOperationOptions<T> = {}
  ): Promise<T> => {
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
 */
export function useFormSubmit<T = unknown, R = unknown>(
  options: UseFormSubmitOptions<T, R> = {}
): UseFormSubmitReturn<T, R> {
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
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<NormalizedError | null>(null);

  /**
   * Handle form submission
   */
  const handleSubmit = useCallback(async (formData: T, event?: Event): Promise<R> => {
    // Prevent default form submission if event provided
    if (event && 'preventDefault' in event) {
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
      let result: R | undefined;
      if (onSubmit) {
        result = await onSubmit(formData);
      }

      setSubmitting(false);

      if (showSuccessToast) {
        toast.success(successMessage);
      }

      if (onSuccess) {
        onSuccess(result as R);
      }

      if (resetOnSuccess) {
        setErrors({});
      }

      return result as R;
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
  const setFieldError = useCallback((field: string, message: string) => {
    setErrors(prev => ({
      ...prev,
      [field]: message,
    }));
  }, []);

  /**
   * Clear a specific field error
   */
  const clearFieldError = useCallback((field: string) => {
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
 */
export function normalizeError(error: unknown): NormalizedError {
  // Already has getUserMessage
  if (error && typeof error === 'object' && 'getUserMessage' in error && typeof (error as NormalizedError).getUserMessage === 'function') {
    return error as NormalizedError;
  }

  const err = error as Record<string, unknown>;

  // Backend error response
  if (err && err.message && err.error_code) {
    const errorCode = err.error_code as string;
    return {
      message: err.message as string,
      code: errorCode,
      details: err.details as NormalizedError['details'],
      fieldErrors: (err.details as Record<string, unknown>)?.fieldErrors as Record<string, string> || err.field_errors as Record<string, string>,
      getUserMessage: () => err.message as string,
      isRecoverable: () => ['NETWORK_ERROR', 'TIMEOUT', 'SERVER_ERROR'].includes(errorCode),
    };
  }

  // Fetch response error
  if (err && typeof err.status === 'number' && err.statusText) {
    const status = err.status as number;
    return {
      message: `Request failed: ${err.statusText}`,
      code: 'HTTP_ERROR',
      statusCode: status,
      getUserMessage: () => getHttpErrorMessage(status),
      isRecoverable: () => status >= 500,
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
function getHttpErrorMessage(status: number): string {
  const messages: Record<number, string> = {
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
 */
export function withErrorHandling<TArgs extends unknown[], TReturn>(
  apiCall: (...args: TArgs) => Promise<TReturn>,
  options: WithErrorHandlingOptions = {}
): (...args: TArgs) => Promise<TReturn> {
  return async (...args: TArgs): Promise<TReturn> => {
    try {
      const response = await apiCall(...args);

      // Check if response indicates an error
      if (response && typeof response === 'object' && (response as Record<string, unknown>).status === 'error') {
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
 */
export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {}
): Promise<T> {
  const {
    maxRetries = 3,
    initialDelay = 1000,
    maxDelay = 10000,
    shouldRetry = (error: NormalizedError) => error.isRecoverable?.() ?? false,
  } = options;

  let lastError: NormalizedError | undefined;
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
