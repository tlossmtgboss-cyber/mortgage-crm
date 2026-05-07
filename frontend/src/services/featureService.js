import { getToken } from '../utils/tokenStore';

/**
 * Feature Service
 *
 * Centralized service for managing feature visibility across the application.
 * Handles feature flag checks, caching, and API interactions.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';

// Cache for user's visible features
let featureCache = null;
let cacheTimestamp = null;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * Get authorization headers
 */
const getHeaders = () => {
  const token = getToken();
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
};

/**
 * Check if cache is valid
 */
const isCacheValid = () => {
  return featureCache && cacheTimestamp && (Date.now() - cacheTimestamp < CACHE_TTL);
};

/**
 * Clear the feature cache
 */
export const clearFeatureCache = () => {
  featureCache = null;
  cacheTimestamp = null;
};

/**
 * Fetch user's visible features from the API
 */
export const fetchUserVisibleFeatures = async (forceRefresh = false) => {
  if (!forceRefresh && isCacheValid()) {
    return featureCache;
  }

  try {
    const response = await fetch(`${API_BASE}/api/v1/features/user-visible`, {
      headers: getHeaders()
    });

    if (!response.ok) {
      throw new Error('Failed to fetch user features');
    }

    const data = await response.json();
    featureCache = data;
    cacheTimestamp = Date.now();

    return data;
  } catch (error) {
    console.error('Error fetching user features:', error);
    // Return cached data even if expired, or empty default
    return featureCache || { features: [], enabled_features: [], has_premium_access: false };
  }
};

/**
 * Check if a specific feature is enabled for the current user
 * @param {string} featureKey - The feature key to check
 * @returns {Promise<boolean>} - Whether the feature is enabled
 */
export const isFeatureEnabled = async (featureKey) => {
  const data = await fetchUserVisibleFeatures();
  return data.enabled_features?.includes(featureKey) || false;
};

/**
 * Check multiple features at once
 * @param {string[]} featureKeys - Array of feature keys to check
 * @returns {Promise<Object>} - Object mapping feature keys to enabled status
 */
export const checkFeatures = async (featureKeys) => {
  const data = await fetchUserVisibleFeatures();
  const result = {};
  for (const key of featureKeys) {
    result[key] = data.enabled_features?.includes(key) || false;
  }
  return result;
};

/**
 * Get all available features (for admin use)
 * @param {boolean} includeDevelopment - Whether to include development features
 */
export const fetchAvailableFeatures = async (includeDevelopment = false) => {
  try {
    const url = new URL(`${API_BASE}/api/v1/features/available`);
    if (includeDevelopment) {
      url.searchParams.set('include_development', 'true');
    }

    const response = await fetch(url.toString(), {
      headers: getHeaders()
    });

    if (!response.ok) {
      throw new Error('Failed to fetch available features');
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching available features:', error);
    return [];
  }
};

/**
 * Get all features (admin only)
 */
export const fetchAllFeatures = async () => {
  try {
    const response = await fetch(`${API_BASE}/api/v1/features/all`, {
      headers: getHeaders()
    });

    if (!response.ok) {
      throw new Error('Failed to fetch all features');
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching all features:', error);
    return [];
  }
};

/**
 * Get company feature access (for admin management)
 * @param {number} companyId - The company ID
 */
export const fetchCompanyFeatureAccess = async (companyId) => {
  try {
    const response = await fetch(`${API_BASE}/api/v1/features/company/${companyId}/access`, {
      headers: getHeaders()
    });

    if (!response.ok) {
      throw new Error('Failed to fetch company feature access');
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching company feature access:', error);
    return { features: [] };
  }
};

/**
 * Update company feature access
 * @param {number} companyId - The company ID
 * @param {string} featureKey - The feature key
 * @param {Object} accessData - Access configuration
 */
export const updateCompanyFeatureAccess = async (companyId, featureKey, accessData) => {
  try {
    const response = await fetch(
      `${API_BASE}/api/v1/features/company/${companyId}/access/${featureKey}`,
      {
        method: 'PUT',
        headers: getHeaders(),
        body: JSON.stringify(accessData)
      }
    );

    if (!response.ok) {
      throw new Error('Failed to update feature access');
    }

    // Clear cache so changes are reflected
    clearFeatureCache();

    return await response.json();
  } catch (error) {
    console.error('Error updating feature access:', error);
    throw error;
  }
};

/**
 * Bulk update company feature access
 * @param {number} companyId - The company ID
 * @param {string[]} featureKeys - Array of feature keys
 * @param {boolean} isEnabled - Enable or disable
 */
export const bulkUpdateCompanyFeatureAccess = async (companyId, featureKeys, isEnabled) => {
  try {
    const response = await fetch(
      `${API_BASE}/api/v1/features/company/${companyId}/access/bulk`,
      {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ feature_keys: featureKeys, is_enabled: isEnabled })
      }
    );

    if (!response.ok) {
      throw new Error('Failed to bulk update feature access');
    }

    // Clear cache so changes are reflected
    clearFeatureCache();

    return await response.json();
  } catch (error) {
    console.error('Error bulk updating feature access:', error);
    throw error;
  }
};

/**
 * Run feature system setup (admin only)
 */
export const runFeatureSetup = async () => {
  try {
    const response = await fetch(`${API_BASE}/api/v1/features/migrate/full-setup`, {
      method: 'POST',
      headers: getHeaders()
    });

    if (!response.ok) {
      throw new Error('Failed to run feature setup');
    }

    return await response.json();
  } catch (error) {
    console.error('Error running feature setup:', error);
    throw error;
  }
};

/**
 * Feature key constants for type safety
 */
export const FEATURE_KEYS = {
  AI_RECEPTIONIST: 'ai_receptionist',
  POWER_DIALER: 'power_dialer',
  AI_UNDERWRITING: 'ai_underwriting',
  PARTNERS: 'partners',
  MARKET: 'market',
  PROFITABILITY: 'profitability',
  VOICE_OS: 'voice_os',
  MARKETING: 'marketing',
  INTEGRATIONS: 'integrations',
  API_KEYS: 'api_keys',
  IT_HELP_DESK: 'it_help_desk',
  SMART_SCHEDULER: 'smart_scheduler',
  VIDEO_MEETINGS: 'video_meetings',
  DATA_MANAGEMENT: 'data_management',
  MASTER_ADMIN: 'master_admin'
};

/**
 * Feature categories
 */
export const FEATURE_CATEGORIES = {
  AI_TOOLS: 'ai_tools',
  COMMUNICATION: 'communication',
  ANALYTICS: 'analytics',
  OPERATIONS: 'operations',
  ADMINISTRATION: 'administration',
  INTEGRATIONS: 'integrations'
};

/**
 * React hook for checking feature access
 * Usage: const hasFeature = useFeatureCheck('power_dialer');
 */
export const useFeatureCheck = (featureKey) => {
  // This is a simplified version - in production you'd use React state/effects
  // For now, returns a synchronous check if cache exists
  if (featureCache) {
    return featureCache.enabled_features?.includes(featureKey) || false;
  }
  return false;
};

export default {
  fetchUserVisibleFeatures,
  isFeatureEnabled,
  checkFeatures,
  fetchAvailableFeatures,
  fetchAllFeatures,
  fetchCompanyFeatureAccess,
  updateCompanyFeatureAccess,
  bulkUpdateCompanyFeatureAccess,
  runFeatureSetup,
  clearFeatureCache,
  FEATURE_KEYS,
  FEATURE_CATEGORIES,
  useFeatureCheck
};
