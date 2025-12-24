/**
 * Perennia AI - Frontend Error Handling Utilities
 *
 * Provides consistent error handling across the application.
 */

/**
 * Standard error codes used across the application
 */
export const ErrorCode = {
  // Validation errors
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  REQUIRED_FIELD: 'REQUIRED_FIELD',
  INVALID_FORMAT: 'INVALID_FORMAT',

  // Authentication/Authorization
  AUTH_ERROR: 'AUTH_ERROR',
  SESSION_EXPIRED: 'SESSION_EXPIRED',
  INSUFFICIENT_PERMISSIONS: 'INSUFFICIENT_PERMISSIONS',

  // Network errors
  NETWORK_ERROR: 'NETWORK_ERROR',
  TIMEOUT: 'TIMEOUT',
  NO_CONNECTION: 'NO_CONNECTION',

  // Server errors
  SERVER_ERROR: 'SERVER_ERROR',
  DATABASE_ERROR: 'DATABASE_ERROR',
  EXTERNAL_SERVICE_ERROR: 'EXTERNAL_SERVICE_ERROR',

  // Rate limiting
  RATE_LIMIT: 'RATE_LIMIT',
  QUOTA_EXCEEDED: 'QUOTA_EXCEEDED',

  // Resource errors
  NOT_FOUND: 'NOT_FOUND',
  ALREADY_EXISTS: 'ALREADY_EXISTS',
  CONFLICT: 'CONFLICT',

  // Generic
  UNKNOWN_ERROR: 'UNKNOWN_ERROR',
};

/**
 * User-friendly error messages for each error code
 */
const ERROR_MESSAGES = {
  [ErrorCode.VALIDATION_ERROR]: 'Please check your input and try again.',
  [ErrorCode.REQUIRED_FIELD]: 'Please fill in all required fields.',
  [ErrorCode.INVALID_FORMAT]: 'Please check the format of your input.',

  [ErrorCode.AUTH_ERROR]: 'Authentication failed. Please log in again.',
  [ErrorCode.SESSION_EXPIRED]: 'Your session has expired. Please log in again.',
  [ErrorCode.INSUFFICIENT_PERMISSIONS]: "You don't have permission to perform this action.",

  [ErrorCode.NETWORK_ERROR]: 'Unable to connect. Please check your internet connection.',
  [ErrorCode.TIMEOUT]: 'Request timed out. Please try again.',
  [ErrorCode.NO_CONNECTION]: 'No internet connection. Please check your network.',

  [ErrorCode.SERVER_ERROR]: 'Something went wrong on our end. Please try again.',
  [ErrorCode.DATABASE_ERROR]: 'Unable to save changes. Please try again.',
  [ErrorCode.EXTERNAL_SERVICE_ERROR]: 'External service is unavailable. Please try again later.',

  [ErrorCode.RATE_LIMIT]: 'Too many requests. Please wait a moment and try again.',
  [ErrorCode.QUOTA_EXCEEDED]: 'You\'ve exceeded your usage quota.',

  [ErrorCode.NOT_FOUND]: 'The requested resource was not found.',
  [ErrorCode.ALREADY_EXISTS]: 'This already exists. Please use a different value.',
  [ErrorCode.CONFLICT]: 'This change conflicts with existing data.',

  [ErrorCode.UNKNOWN_ERROR]: 'An unexpected error occurred. Please try again.',
};

/**
 * Custom API Error class with enhanced context
 */
export class APIError extends Error {
  constructor(message, code = ErrorCode.UNKNOWN_ERROR, options = {}) {
    super(message);
    this.name = 'APIError';
    this.code = code;
    this.details = options.details || null;
    this.requestId = options.requestId || null;
    this.statusCode = options.statusCode || null;
    this.timestamp = new Date();

    // Maintains proper stack trace
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, APIError);
    }
  }

  /**
   * Get user-friendly message based on error code
   */
  getUserMessage() {
    return ERROR_MESSAGES[this.code] || this.message;
  }

  /**
   * Check if error requires authentication
   */
  requiresAuth() {
    return [
      ErrorCode.AUTH_ERROR,
      ErrorCode.SESSION_EXPIRED,
      ErrorCode.INSUFFICIENT_PERMISSIONS,
    ].includes(this.code);
  }

  /**
   * Check if error is recoverable (user can retry)
   */
  isRecoverable() {
    return [
      ErrorCode.NETWORK_ERROR,
      ErrorCode.TIMEOUT,
      ErrorCode.SERVER_ERROR,
      ErrorCode.EXTERNAL_SERVICE_ERROR,
      ErrorCode.RATE_LIMIT,
    ].includes(this.code);
  }

  /**
   * Get suggested action for the user
   */
  getSuggestedAction() {
    const actions = {
      [ErrorCode.SESSION_EXPIRED]: 'Please log in again to continue.',
      [ErrorCode.NO_CONNECTION]: 'Please check your internet connection and try again.',
      [ErrorCode.RATE_LIMIT]: 'Please wait a moment before trying again.',
      [ErrorCode.QUOTA_EXCEEDED]: 'Please upgrade your plan or contact support.',
    };

    return actions[this.code] || null;
  }

  /**
   * Convert to JSON for logging
   */
  toJSON() {
    return {
      name: this.name,
      message: this.message,
      code: this.code,
      details: this.details,
      requestId: this.requestId,
      statusCode: this.statusCode,
      timestamp: this.timestamp.toISOString(),
      stack: this.stack,
    };
  }

  /**
   * Create APIError from backend error response
   */
  static fromResponse(response, statusCode) {
    const code = response.error_code || ErrorCode.UNKNOWN_ERROR;

    return new APIError(response.message, code, {
      details: response.details,
      requestId: response.request_id,
      statusCode,
    });
  }

  /**
   * Create APIError from native Error
   */
  static fromNativeError(error) {
    // Network errors
    if (error.name === 'AbortError') {
      return new APIError('Request timed out', ErrorCode.TIMEOUT);
    }

    if (error.message && error.message.includes('fetch')) {
      return new APIError('Network error occurred', ErrorCode.NETWORK_ERROR);
    }

    // Generic unknown error
    return new APIError(error.message || 'Unknown error', ErrorCode.UNKNOWN_ERROR);
  }
}

/**
 * Validation error with field-specific details
 */
export class ValidationError extends APIError {
  constructor(message = 'Validation failed', fieldErrors = {}) {
    super(message, ErrorCode.VALIDATION_ERROR, {
      details: { fieldErrors },
    });
    this.fieldErrors = fieldErrors;
  }

  /**
   * Check if specific field has error
   */
  hasFieldError(field) {
    return field in this.fieldErrors;
  }

  /**
   * Get error for specific field
   */
  getFieldError(field) {
    return this.fieldErrors[field] || null;
  }

  /**
   * Get all field errors as array of messages
   */
  getAllFieldErrors() {
    return Object.values(this.fieldErrors);
  }
}
