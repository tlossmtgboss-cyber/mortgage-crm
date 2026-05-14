/**
 * Shared types for the API layer.
 */

/** Structured API error shape — every rejected promise carries this contract. */
export interface ApiError extends Error {
  error: true;
  status: number;
  message: string;
  retryable: boolean;
  code: string | null;
  detail: string | null;
  _axiosError?: any;
  response?: any;
  config?: any;
}

/** Shape returned by the offline cache for GET fallback responses. */
export interface OfflineCacheEntry {
  data: any;
  ts: number;
}

/** Options for the apiRequest helper. */
export interface ApiRequestOptions {
  timeout?: number;
  method?: string;
  data?: any;
  params?: Record<string, any>;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  responseType?: string;
  onUploadProgress?: (progressEvent: any) => void;
  [key: string]: any;
}
