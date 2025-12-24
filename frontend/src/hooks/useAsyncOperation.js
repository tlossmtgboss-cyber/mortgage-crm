/**
 * Perennia AI - useAsyncOperation Hook
 *
 * React hook for handling async operations with loading, error, and success states.
 *
 * Usage:
 *   const { execute, isLoading, error, isSuccess } = useAsyncOperation(
 *     async (data) => apiClient.put('/api/settings', data),
 *     {
 *       showSuccessToast: true,
 *       successMessage: 'Settings saved successfully',
 *       onError: (error) => console.error(error),
 *     }
 *   );
 *
 *   // In form submit handler:
 *   try {
 *     await execute(formData);
 *   } catch (error) {
 *     // Error already handled by hook
 *   }
 */

import { useState, useCallback } from 'react';
import { APIError } from '../utils/api/errors';
import { toast } from '../utils/toast';

/**
 * Hook for handling async operations with automatic state management
 *
 * @param {Function} operation - Async function to execute
 * @param {Object} options - Configuration options
 * @param {Function} options.onSuccess - Callback on success
 * @param {Function} options.onError - Callback on error
 * @param {boolean} options.showSuccessToast - Show success toast (default: false)
 * @param {boolean} options.showErrorToast - Show error toast (default: true)
 * @param {string} options.successMessage - Custom success message
 * @param {string} options.errorMessage - Custom error message
 * @param {boolean} options.resetOnExecute - Reset state on new execution (default: true)
 */
export function useAsyncOperation(operation, options = {}) {
  const [state, setState] = useState({
    data: null,
    error: null,
    isLoading: false,
    isSuccess: false,
    isError: false,
  });

  const execute = useCallback(
    async (...args) => {
      // Reset state if configured
      if (options.resetOnExecute !== false) {
        setState({
          data: null,
          error: null,
          isLoading: true,
          isSuccess: false,
          isError: false,
        });
      } else {
        setState(prev => ({ ...prev, isLoading: true, error: null }));
      }

      try {
        // Execute operation
        const data = await operation(...args);

        // Update state
        setState({
          data,
          error: null,
          isLoading: false,
          isSuccess: true,
          isError: false,
        });

        // Success callback
        if (options.onSuccess) {
          options.onSuccess(data);
        }

        // Show success toast
        if (options.showSuccessToast) {
          toast.success(options.successMessage || 'Operation completed successfully');
        }

        return data;

      } catch (error) {
        // Ensure error is APIError
        const apiError = error instanceof APIError
          ? error
          : APIError.fromNativeError(error);

        // Update state
        setState({
          data: null,
          error: apiError,
          isLoading: false,
          isSuccess: false,
          isError: true,
        });

        // Error callback
        if (options.onError) {
          options.onError(apiError);
        }

        // Show error toast (default: true)
        if (options.showErrorToast !== false) {
          toast.error(options.errorMessage || apiError.getUserMessage());
        }

        throw apiError;
      }
    },
    [operation, options]
  );

  const reset = useCallback(() => {
    setState({
      data: null,
      error: null,
      isLoading: false,
      isSuccess: false,
      isError: false,
    });
  }, []);

  return {
    ...state,
    execute,
    reset,
  };
}

/**
 * Hook for form submission with validation
 *
 * Usage:
 *   const { submit, isSubmitting, error } = useFormSubmit({
 *     onSubmit: async (data) => apiClient.post('/api/users', data),
 *     validate: (data) => {
 *       const errors = {};
 *       if (!data.email) errors.email = 'Email is required';
 *       return errors;
 *     },
 *     successMessage: 'User created successfully',
 *   });
 */
export function useFormSubmit(options = {}) {
  const [fieldErrors, setFieldErrors] = useState({});

  const { execute, isLoading, error, isSuccess, reset: resetAsync } = useAsyncOperation(
    async (data) => {
      // Run validation if provided
      if (options.validate) {
        const validationErrors = options.validate(data);
        if (Object.keys(validationErrors).length > 0) {
          setFieldErrors(validationErrors);
          throw new APIError(
            'Please fix the validation errors',
            'VALIDATION_ERROR',
            { details: { fieldErrors: validationErrors } }
          );
        }
      }

      // Clear field errors
      setFieldErrors({});

      // Execute submit
      return options.onSubmit(data);
    },
    {
      showSuccessToast: options.showSuccessToast ?? true,
      showErrorToast: options.showErrorToast ?? true,
      successMessage: options.successMessage,
      errorMessage: options.errorMessage,
      onSuccess: options.onSuccess,
      onError: (err) => {
        // Extract field errors from API response
        if (err.details?.field_errors || err.details?.fieldErrors) {
          setFieldErrors(err.details.field_errors || err.details.fieldErrors);
        }
        if (options.onError) {
          options.onError(err);
        }
      },
    }
  );

  const reset = useCallback(() => {
    setFieldErrors({});
    resetAsync();
  }, [resetAsync]);

  const clearFieldError = useCallback((field) => {
    setFieldErrors(prev => {
      const { [field]: removed, ...rest } = prev;
      return rest;
    });
  }, []);

  return {
    submit: execute,
    isSubmitting: isLoading,
    error,
    isSuccess,
    fieldErrors,
    clearFieldError,
    reset,
  };
}

export default useAsyncOperation;
