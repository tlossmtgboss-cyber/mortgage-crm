import { useState, useCallback, useRef, useEffect } from 'react';

/**
 * Hook providing retry logic with exponential backoff for async operations.
 *
 * Returns:
 *   {
 *     error,        // The last Error (or null)
 *     isRetrying,   // True while a retry attempt is in-flight
 *     retryCount,   // How many retries have been attempted
 *     retry,        // Call to trigger a manual retry
 *     reset,        // Clears error state entirely
 *     execute,      // Wraps an async fn: auto-retries on network errors
 *   }
 *
 * Options:
 *   maxRetries      (number, default 3)   Maximum automatic retries
 *   baseDelay       (number, default 1000) Base delay in ms (doubled each retry)
 *   maxDelay        (number, default 10000) Cap on delay
 *   shouldRetry     (function(error) => boolean)  Override which errors trigger
 *                   auto-retry. Defaults to network-like errors.
 *   onError         (function(error, retryCount))  Called each time an error occurs
 *   onSuccess       (function(data))  Called on successful execution
 */
export function useErrorRecovery({
  maxRetries = 3,
  baseDelay = 1000,
  maxDelay = 10000,
  shouldRetry = isNetworkError,
  onError,
  onSuccess,
} = {}) {
  const [error, setError] = useState(null);
  const [isRetrying, setIsRetrying] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  // Store the last operation so `retry()` can re-invoke it
  const lastOperationRef = useRef(null);
  const timeoutRef = useRef(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  /**
   * Wrap an async function with automatic retry on failure.
   *
   *   const { execute } = useErrorRecovery();
   *   const loadEvents = () => execute(() => api.getEvents());
   *
   * Returns the result on success, or undefined on failure after exhausting retries.
   */
  const execute = useCallback(
    async (asyncFn) => {
      lastOperationRef.current = asyncFn;
      setError(null);
      setRetryCount(0);
      setIsRetrying(false);

      const attempt = async (attemptNum) => {
        try {
          const result = await asyncFn();
          if (!mountedRef.current) return undefined;
          setError(null);
          setIsRetrying(false);
          setRetryCount(0);
          if (typeof onSuccess === 'function') onSuccess(result);
          return result;
        } catch (err) {
          if (!mountedRef.current) return undefined;

          if (typeof onError === 'function') onError(err, attemptNum);

          if (attemptNum < maxRetries && shouldRetry(err)) {
            // Schedule next attempt with exponential backoff
            const delay = Math.min(
              baseDelay * Math.pow(2, attemptNum),
              maxDelay
            );
            setIsRetrying(true);
            setRetryCount(attemptNum + 1);
            setError(err);

            return new Promise((resolve) => {
              timeoutRef.current = setTimeout(async () => {
                if (!mountedRef.current) {
                  resolve(undefined);
                  return;
                }
                const result = await attempt(attemptNum + 1);
                resolve(result);
              }, delay);
            });
          }

          // Exhausted retries or not a retryable error
          setError(err);
          setIsRetrying(false);
          return undefined;
        }
      };

      return attempt(0);
    },
    [maxRetries, baseDelay, maxDelay, shouldRetry, onError, onSuccess]
  );

  /**
   * Manually retry the last operation.
   */
  const retry = useCallback(() => {
    if (lastOperationRef.current) {
      return execute(lastOperationRef.current);
    }
    return Promise.resolve(undefined);
  }, [execute]);

  /**
   * Clear all error state without retrying.
   */
  const reset = useCallback(() => {
    setError(null);
    setIsRetrying(false);
    setRetryCount(0);
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  return {
    error,
    isRetrying,
    retryCount,
    retry,
    reset,
    execute,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Heuristic to decide whether an error is a transient network issue
 * that warrants an automatic retry.
 */
function isNetworkError(err) {
  if (!err) return false;

  // Fetch/XHR network failures
  if (err.name === 'TypeError' && /fetch|network/i.test(err.message)) {
    return true;
  }

  // Axios-style network errors
  if (err.code === 'ERR_NETWORK' || err.code === 'ECONNABORTED') {
    return true;
  }

  // HTTP 5xx or 429 (rate-limited) responses
  const status = err.response?.status || err.status;
  if (status && (status >= 500 || status === 429)) {
    return true;
  }

  // Explicitly marked as retryable
  if (err.retryable === true) {
    return true;
  }

  return false;
}

export default useErrorRecovery;
