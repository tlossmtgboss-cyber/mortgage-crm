/**
 * Environment variable compatibility layer for CRA to Vite migration
 *
 * This module provides a unified way to access environment variables
 * that works with both Create React App (process.env.REACT_APP_*) and
 * Vite (import.meta.env.VITE_*).
 *
 * MIGRATION GUIDE:
 * ================
 *
 * 1. Environment Variable Naming:
 *    - CRA uses: REACT_APP_* prefix
 *    - Vite uses: VITE_* prefix
 *
 *    During migration, you can rename variables in your .env files:
 *    - REACT_APP_API_URL -> VITE_API_URL
 *    - REACT_APP_WS_URL -> VITE_WS_URL
 *    - etc.
 *
 * 2. Code Updates:
 *    Instead of:
 *      process.env.REACT_APP_API_URL
 *
 *    Use:
 *      import { env } from '@/utils/env';
 *      env.VITE_API_URL
 *
 *    Or for direct access:
 *      import.meta.env.VITE_API_URL
 *
 * 3. Environment Variables Mapping:
 *    REACT_APP_API_URL           -> VITE_API_URL
 *    REACT_APP_WS_URL            -> VITE_WS_URL
 *    REACT_APP_MICROSOFT_CLIENT_ID -> VITE_MICROSOFT_CLIENT_ID
 *    REACT_APP_GOOGLE_PLACES_API_KEY -> VITE_GOOGLE_PLACES_API_KEY
 *    REACT_APP_GOOGLE_CLIENT_ID  -> VITE_GOOGLE_CLIENT_ID
 *    REACT_APP_FACEBOOK_APP_ID   -> VITE_FACEBOOK_APP_ID
 *    REACT_APP_LINKEDIN_CLIENT_ID -> VITE_LINKEDIN_CLIENT_ID
 *    REACT_APP_APPLE_CLIENT_ID   -> VITE_APPLE_CLIENT_ID
 *    REACT_APP_ENABLE_*          -> VITE_ENABLE_*
 *    REACT_APP_SENTRY_DSN        -> VITE_SENTRY_DSN
 *    REACT_APP_GA_TRACKING_ID    -> VITE_GA_TRACKING_ID
 *    REACT_APP_MIXPANEL_TOKEN    -> VITE_MIXPANEL_TOKEN
 *    REACT_APP_ENVIRONMENT       -> VITE_ENVIRONMENT
 *    REACT_APP_DEBUG             -> VITE_DEBUG
 *    REACT_APP_PURL_*            -> VITE_PURL_*
 */

// Detect if running in Vite or CRA
const isVite = typeof import.meta !== 'undefined' && import.meta.env;

/**
 * Get environment variable value with fallback support
 * Checks both VITE_ and REACT_APP_ prefixes for compatibility
 */
function getEnvVar(name, defaultValue = '') {
  if (isVite) {
    // Try VITE_ prefix first, then REACT_APP_ for backward compatibility
    return import.meta.env[`VITE_${name}`]
      ?? import.meta.env[`REACT_APP_${name}`]
      ?? defaultValue;
  }
  // CRA fallback
  return process.env[`REACT_APP_${name}`] ?? defaultValue;
}

/**
 * Environment configuration object
 * Access environment variables through this object for consistency
 */
export const env = {
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
    : process.env.NODE_ENV,
};

/**
 * Raw access to import.meta.env or process.env
 * Use this when you need direct access to all environment variables
 */
export const rawEnv = isVite ? import.meta.env : process.env;

export default env;
