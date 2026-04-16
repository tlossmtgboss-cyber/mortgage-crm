/**
 * usePagePermissions Hook
 *
 * Provides page-level access control functionality.
 * Uses the page permissions backend API to check if the current user
 * has access to specific pages based on their role and any overrides.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { API_BASE_URL } from '../services/api';
import { getToken } from '../utils/tokenStore';

/**
 * Hook for checking page-level permissions
 * @returns {Object} Page permission utilities and state
 */
export const usePagePermissions = () => {
  const [accessiblePages, setAccessiblePages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastFetched, setLastFetched] = useState(null);

  // Cache duration in milliseconds (5 minutes)
  const CACHE_DURATION = 5 * 60 * 1000;

  /**
   * Get auth headers for API requests
   */
  const getHeaders = useCallback(() => {
    const token = getToken();
    const headers = {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };

    // Add impersonation token if present
    const impersonationData = localStorage.getItem('impersonation');
    if (impersonationData) {
      try {
        const data = JSON.parse(impersonationData);
        if (data.session_token) {
          headers['X-Impersonation-Token'] = data.session_token;
        }
      } catch (e) {
        console.error('Error parsing impersonation data:', e);
      }
    }

    return headers;
  }, []);

  /**
   * Fetch accessible pages for the current user
   */
  const fetchAccessiblePages = useCallback(async (force = false) => {
    // Check cache unless forced refresh
    if (!force && lastFetched && (Date.now() - lastFetched < CACHE_DURATION)) {
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const response = await fetch(
        `${API_BASE_URL}/api/v1/page-permissions/user/accessible-pages`,
        { headers: getHeaders() }
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch accessible pages: ${response.status}`);
      }

      const data = await response.json();
      setAccessiblePages(data.accessible_pages || []);
      setLastFetched(Date.now());

    } catch (err) {
      console.error('Error fetching accessible pages:', err);
      setError(err.message);
      // On error, allow access by default to prevent lockouts
      setAccessiblePages([]);
    } finally {
      setLoading(false);
    }
  }, [getHeaders, lastFetched]);

  // Fetch on mount
  useEffect(() => {
    fetchAccessiblePages();
  }, []);

  /**
   * Check if user can access a specific page
   * @param {string} pageKey - The page key to check (e.g., 'dashboard', 'leads')
   * @returns {boolean} Whether the user can access the page
   */
  const canAccessPage = useCallback((pageKey) => {
    // During loading, allow access to prevent UI flicker
    if (loading) return true;

    // If no pages loaded (error state), allow access to prevent lockout
    if (accessiblePages.length === 0 && error) return true;

    return accessiblePages.some(page => page.page_key === pageKey);
  }, [accessiblePages, loading, error]);

  /**
   * Check if user can access any of the given pages
   * @param {string[]} pageKeys - Array of page keys to check
   * @returns {boolean} Whether the user can access any of the pages
   */
  const canAccessAnyPage = useCallback((pageKeys) => {
    if (loading) return true;
    if (accessiblePages.length === 0 && error) return true;

    return pageKeys.some(key =>
      accessiblePages.some(page => page.page_key === key)
    );
  }, [accessiblePages, loading, error]);

  /**
   * Check if user can access all of the given pages
   * @param {string[]} pageKeys - Array of page keys to check
   * @returns {boolean} Whether the user can access all of the pages
   */
  const canAccessAllPages = useCallback((pageKeys) => {
    if (loading) return true;
    if (accessiblePages.length === 0 && error) return true;

    return pageKeys.every(key =>
      accessiblePages.some(page => page.page_key === key)
    );
  }, [accessiblePages, loading, error]);

  /**
   * Get accessible pages for a specific category
   * @param {string} category - The category to filter by
   * @returns {Array} Pages in the specified category
   */
  const getPagesByCategory = useCallback((category) => {
    return accessiblePages.filter(page => page.category === category);
  }, [accessiblePages]);

  /**
   * Get all unique categories from accessible pages
   * @returns {string[]} Array of category names
   */
  const getAccessibleCategories = useMemo(() => {
    const categories = new Set(accessiblePages.map(page => page.category));
    return Array.from(categories);
  }, [accessiblePages]);

  /**
   * Check a specific page permission via API (for real-time checks)
   * @param {string} pageKey - The page key to check
   * @returns {Promise<boolean>} Whether the user has access
   */
  const checkPagePermission = useCallback(async (pageKey) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/page-permissions/check`,
        {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({ page_key: pageKey })
        }
      );

      if (!response.ok) {
        throw new Error(`Permission check failed: ${response.status}`);
      }

      const data = await response.json();
      return data.has_access === true;

    } catch (err) {
      console.error('Error checking page permission:', err);
      // Allow access on error to prevent lockouts
      return true;
    }
  }, [getHeaders]);

  /**
   * Check multiple page permissions via API (for real-time checks)
   * @param {string[]} pageKeys - Array of page keys to check
   * @returns {Promise<Object>} Object mapping page keys to access status
   */
  const checkBulkPermissions = useCallback(async (pageKeys) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/page-permissions/check-bulk`,
        {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({ page_keys: pageKeys })
        }
      );

      if (!response.ok) {
        throw new Error(`Bulk permission check failed: ${response.status}`);
      }

      const data = await response.json();
      return data.permissions || {};

    } catch (err) {
      console.error('Error checking bulk permissions:', err);
      // Allow access on error
      return pageKeys.reduce((acc, key) => ({ ...acc, [key]: true }), {});
    }
  }, [getHeaders]);

  /**
   * Force refresh of accessible pages
   */
  const refresh = useCallback(() => {
    return fetchAccessiblePages(true);
  }, [fetchAccessiblePages]);

  return {
    // State
    accessiblePages,
    loading,
    error,

    // Page access checks (cached)
    canAccessPage,
    canAccessAnyPage,
    canAccessAllPages,
    getPagesByCategory,
    getAccessibleCategories,

    // Real-time API checks
    checkPagePermission,
    checkBulkPermissions,

    // Utilities
    refresh
  };
};

/**
 * Higher-order component for page access protection
 * @param {React.Component} WrappedComponent - Component to protect
 * @param {string} pageKey - Required page key for access
 * @param {React.Component} FallbackComponent - Component to show if no access
 */
export const withPageAccess = (WrappedComponent, pageKey, FallbackComponent = null) => {
  return function PageAccessWrapper(props) {
    const { canAccessPage, loading } = usePagePermissions();

    if (loading) {
      return <div className="loading-permissions">Checking permissions...</div>;
    }

    if (!canAccessPage(pageKey)) {
      if (FallbackComponent) {
        return <FallbackComponent />;
      }
      return (
        <div className="access-denied">
          <h2>Access Denied</h2>
          <p>You do not have permission to view this page.</p>
        </div>
      );
    }

    return <WrappedComponent {...props} />;
  };
};

export default usePagePermissions;
