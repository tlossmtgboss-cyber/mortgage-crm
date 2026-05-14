/**
 * Structured API error builder.
 *
 * Every rejected promise from the interceptor carries this shape so callers
 * can rely on a consistent contract:
 *   { error: true, status, message, retryable, code, detail }
 * The original axios error is preserved as `_axiosError` for callers that
 * need low-level access (e.g. response headers).
 */

/**
 * Build a structured error object from an axios error.
 * @param status   HTTP status (0 for network errors)
 * @param message  User-facing message
 * @param opts     Additional fields (retryable, code, detail, _axiosError)
 * @returns Error instance with structured fields
 */
export function buildApiError(
  status: number,
  message: string,
  opts: {
    retryable?: boolean;
    code?: string | null;
    detail?: string | null;
    _axiosError?: any;
  } = {}
): Error & { error: true; status: number; retryable: boolean; code: string | null; detail: string | null; response?: any; config?: any } {
  const err = new Error(message) as any;
  err.error = true;
  err.status = status;
  err.message = message;
  err.retryable = opts.retryable ?? false;
  err.code = opts.code || null;
  err.detail = opts.detail || null;
  if (opts._axiosError) {
    err._axiosError = opts._axiosError;
    // Preserve response for callers that inspect error.response
    err.response = opts._axiosError.response;
    err.config = opts._axiosError.config;
  }
  return err;
}

/** Safe error messages for known HTTP status codes. */
export const SAFE_ERROR_MESSAGES: Record<number, string> = {
  400: "Invalid request. Please check your input.",
  403: "You don't have permission for this action.",
  404: "The requested resource was not found.",
  409: "A conflict occurred. Please refresh and try again.",
  422: "Invalid data submitted.",
};

/**
 * Type guard to check if an error is a structured API error.
 * Usage:
 *   try { await leadsAPI.getAll(); }
 *   catch (err) {
 *     if (isApiError(err)) {
 *       console.log(err.status, err.message, err.retryable);
 *     }
 *   }
 */
export function isApiError(err: any): boolean {
  return err && err.error === true && typeof err.status === 'number';
}

/**
 * Check if the browser is currently offline.
 * Use this to guard UI actions before attempting API calls.
 */
export function isOffline(): boolean {
  return !navigator.onLine;
}
