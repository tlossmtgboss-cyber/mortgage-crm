/**
 * Environment variable compatibility layer for CRA to Vite migration
 *
 * This module provides a unified way to access environment variables
 * that works with both Create React App (process.env.REACT_APP_*) and
 * Vite (import.meta.env.VITE_*).
 */

// Detect if running in Vite or CRA
const isVite = typeof import.meta !== 'undefined' && import.meta.env;

/**
 * Get environment variable value with fallback support
 * Checks both VITE_ and REACT_APP_ prefixes for compatibility
 */
function getEnvVar(name: string, defaultValue: string = ''): string {
  if (isVite) {
    // Try VITE_ prefix first, then REACT_APP_ for backward compatibility
    return (import.meta.env[`VITE_${name}`] as string)
      ?? (import.meta.env[`REACT_APP_${name}`] as string)
      ?? defaultValue;
  }
  // CRA fallback
  return (process.env[`REACT_APP_${name}`] as string) ?? defaultValue;
}

export interface EnvConfig {
  // API Configuration
  API_URL: string;
  WS_URL: string;

  // Microsoft Authentication
  MICROSOFT_CLIENT_ID: string;

  // Google
  GOOGLE_PLACES_API_KEY: string;
  GOOGLE_CLIENT_ID: string;

  // Social Login
  FACEBOOK_APP_ID: string;
  LINKEDIN_CLIENT_ID: string;
  APPLE_CLIENT_ID: string;

  // Feature Flags
  ENABLE_AGENT_DASHBOARD: boolean;
  ENABLE_AGENT_GYM: boolean;
  ENABLE_PURL_PORTAL: boolean;
  ENABLE_VIDEO_FEATURE: boolean;

  // Analytics
  SENTRY_DSN: string;
  GA_TRACKING_ID: string;
  MIXPANEL_TOKEN: string;

  // Environment
  ENVIRONMENT: string;
  DEBUG: boolean;

  // PURL
  PURL_SESSION_TIMEOUT: number;
  PURL_DEBUG: boolean;

  // Runtime checks
  isDevelopment: boolean;
  isProduction: boolean;
  mode: string;
}

/**
 * Environment configuration object
 * Access environment variables through this object for consistency
 */
export const env: EnvConfig = {
  // API Configuration
  API_URL: getEnvVar('API_URL', 'http://localhost:8000'),
  WS_URL: getEnvVar('WS_URL', 'ws://localhost:8000'),

  // Microsoft Authentication
  MICROSOFT_CLIENT_ID: getEnvVar('MICROSOFT_CLIENT_ID', ''),

  // Google
  GOOGLE_PLACES_API_KEY: getEnvVar('GOOGLE_PLACES_API_KEY', ''),
  GOOGLE_CLIENT_ID: getEnvVar('GOOGLE_CLIENT_ID', ''),

  // Social Login
  FACEBOOK_APP_ID: getEnvVar('FACEBOOK_APP_ID', ''),
  LINKEDIN_CLIENT_ID: getEnvVar('LINKEDIN_CLIENT_ID', ''),
  APPLE_CLIENT_ID: getEnvVar('APPLE_CLIENT_ID', ''),

  // Feature Flags
  ENABLE_AGENT_DASHBOARD: getEnvVar('ENABLE_AGENT_DASHBOARD', 'true') === 'true',
  ENABLE_AGENT_GYM: getEnvVar('ENABLE_AGENT_GYM', 'true') === 'true',
  ENABLE_PURL_PORTAL: getEnvVar('ENABLE_PURL_PORTAL', 'true') === 'true',
  ENABLE_VIDEO_FEATURE: getEnvVar('ENABLE_VIDEO_FEATURE', 'true') === 'true',

  // Analytics
  SENTRY_DSN: getEnvVar('SENTRY_DSN', ''),
  GA_TRACKING_ID: getEnvVar('GA_TRACKING_ID', ''),
  MIXPANEL_TOKEN: getEnvVar('MIXPANEL_TOKEN', ''),

  // Environment
  ENVIRONMENT: getEnvVar('ENVIRONMENT', 'development'),
  DEBUG: getEnvVar('DEBUG', 'false') === 'true',

  // PURL
  PURL_SESSION_TIMEOUT: parseInt(getEnvVar('PURL_SESSION_TIMEOUT', '30'), 10),
  PURL_DEBUG: getEnvVar('PURL_DEBUG', 'false') === 'true',

  // Runtime checks
  isDevelopment: isVite
    ? import.meta.env.DEV
    : process.env.NODE_ENV === 'development',
  isProduction: isVite
    ? import.meta.env.PROD
    : process.env.NODE_ENV === 'production',
  mode: isVite
    ? import.meta.env.MODE
    : (process.env.NODE_ENV || 'development'),
};

/**
 * Raw access to import.meta.env or process.env
 * Use this when you need direct access to all environment variables
 */
export const rawEnv: Record<string, string | boolean | undefined> = isVite
  ? (import.meta.env as unknown as Record<string, string | boolean | undefined>)
  : (process.env as unknown as Record<string, string | boolean | undefined>);

export default env;
