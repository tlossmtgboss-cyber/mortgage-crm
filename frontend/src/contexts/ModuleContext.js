/**
 * ModuleContext
 *
 * Provides subscription module access checking throughout the application.
 * Organizations can have different modules enabled based on their subscription.
 *
 * Usage:
 *   const { hasModule, isRouteAccessible, enabledModules } = useModules();
 *   if (hasModule('ai_assistant')) { ... }
 */

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { getAuthHeaders } from '../utils/auth';
import { API_BASE_URL } from '../services/api';
import { getToken } from '../utils/tokenStore';

// Use the same API URL as the rest of the app (handles production vs dev)
const API_BASE = API_BASE_URL;

// Cache duration in milliseconds (5 minutes)
const CACHE_TTL = 5 * 60 * 1000;

const ModuleContext = createContext(null);

export const ModuleProvider = ({ children }) => {
  const [enabledModules, setEnabledModules] = useState(['base']); // Base is always enabled
  const [allModules, setAllModules] = useState([]);
  const [pricing, setPricing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastFetch, setLastFetch] = useState(null);

  // Fetch modules from API
  const fetchModules = useCallback(async (force = false) => {
    // Skip if recently fetched (unless forced)
    if (!force && lastFetch && Date.now() - lastFetch < CACHE_TTL) {
      return;
    }

    try {
      setLoading(true);
      setError(null);

      // Skip module fetching on public routes (booking, portals, applications, etc.)
      const publicRoutes = ['/apply/', '/purl/', '/borrower-portal/', '/book/', '/embed/book/', '/booking/', '/portal/', '/partner/', '/sign/', '/lo/', '/shared/', '/meeting/'];
      const currentPath = window.location.pathname;
      if (publicRoutes.some(route => currentPath.startsWith(route))) {
        setLoading(false);
        return;
      }

      const response = await fetch(`${API_BASE}/api/v1/modules/my-modules`, {
        headers: getAuthHeaders()
      });

      if (!response.ok) {
        // On 401, don't clear tokens or redirect — the api.js interceptor
        // handles session management with retry-with-refresh logic.
        // Redirecting here races with login navigation and causes loops.
        if (response.status === 401) {
          console.warn('[ModuleContext] 401 on modules fetch — using defaults');
          return;
        }
        // If 403, user is logged in but lacks permission — use defaults
        if (response.status === 403) {
          setEnabledModules(['base']);
          setAllModules([]);
          return;
        }
        throw new Error('Failed to fetch modules');
      }

      const data = await response.json();

      // Extract enabled module keys
      const enabled = data.modules
        .filter(m => m.is_enabled)
        .map(m => m.module_key);

      setEnabledModules(enabled.length > 0 ? enabled : ['base']);
      setAllModules(data.modules);
      setPricing(data.pricing);
      setLastFetch(Date.now());

      // Cache in localStorage for faster initial load
      localStorage.setItem('moduleCache', JSON.stringify({
        enabledModules: enabled,
        timestamp: Date.now()
      }));

    } catch (err) {
      console.error('Error fetching modules:', err);
      setError(err.message);

      // Try to use cached data
      const cached = localStorage.getItem('moduleCache');
      if (cached) {
        try {
          const { enabledModules: cachedModules } = JSON.parse(cached);
          setEnabledModules(cachedModules || ['base']);
        } catch {
          setEnabledModules(['base']);
        }
      }
    } finally {
      setLoading(false);
    }
  }, [lastFetch]);

  // Load cached modules on mount, then fetch fresh data
  useEffect(() => {
    // Skip module fetching on public routes (application pages, etc.)
    const publicRoutes = ['/apply/', '/purl/', '/borrower-portal/'];
    const currentPath = window.location.pathname;
    if (publicRoutes.some(route => currentPath.startsWith(route))) {
      setLoading(false);
      return;
    }

    // Quick load from cache
    const cached = localStorage.getItem('moduleCache');
    if (cached) {
      try {
        const { enabledModules: cachedModules, timestamp } = JSON.parse(cached);
        if (cachedModules && Date.now() - timestamp < CACHE_TTL) {
          setEnabledModules(cachedModules);
          setLoading(false);
        }
      } catch {
        // Ignore cache errors
      }
    }

    // Only fetch if user is logged in (token exists)
    const token = getToken();
    if (token) {
      fetchModules();
    } else {
      setLoading(false);
    }
  }, [fetchModules]);

  // Re-fetch modules when auth token changes (login/logout)
  useEffect(() => {
    // Handle storage changes from other tabs
    const handleStorageChange = (e) => {
      if (e.key === 'token') {
        if (e.newValue) {
          // Token was set (login) - fetch modules
          fetchModules(true);
        } else {
          // Token was removed (logout) - reset to base
          setEnabledModules(['base']);
          setAllModules([]);
          localStorage.removeItem('moduleCache');
        }
      }
    };

    // Handle auth changes within the same tab (custom event)
    const handleAuthChange = (e) => {
      if (e.detail?.type === 'login') {
        fetchModules(true);
      } else if (e.detail?.type === 'logout') {
        setEnabledModules(['base']);
        setAllModules([]);
        localStorage.removeItem('moduleCache');
      }
    };

    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('authChange', handleAuthChange);
    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('authChange', handleAuthChange);
    };
  }, [fetchModules]);

  /**
   * Check if organization has access to a specific module
   */
  const hasModule = useCallback((moduleKey) => {
    // Base module is always available
    if (moduleKey === 'base') return true;
    return enabledModules.includes(moduleKey);
  }, [enabledModules]);

  /**
   * Check if organization has access to a specific feature
   */
  const hasFeature = useCallback((featureKey) => {
    return allModules.some(module =>
      enabledModules.includes(module.module_key) &&
      module.included_features?.includes(featureKey)
    );
  }, [enabledModules, allModules]);

  /**
   * Check if a route is accessible based on modules
   * Returns { accessible: boolean, requiredModule?: object }
   */
  const isRouteAccessible = useCallback((routePath) => {
    // Find which module gates this route
    for (const module of allModules) {
      const gatedRoutes = module.gated_routes || [];
      for (const gatedRoute of gatedRoutes) {
        if (routePath.startsWith(gatedRoute)) {
          if (enabledModules.includes(module.module_key)) {
            return { accessible: true, module: null };
          } else {
            return {
              accessible: false,
              module: {
                module_key: module.module_key,
                module_name: module.module_name,
                monthly_price: module.monthly_price,
                description: module.description,
                icon: module.icon
              }
            };
          }
        }
      }
    }

    // Route not gated by any module
    return { accessible: true, module: null };
  }, [enabledModules, allModules]);

  /**
   * Get module info by key
   */
  const getModule = useCallback((moduleKey) => {
    return allModules.find(m => m.module_key === moduleKey) || null;
  }, [allModules]);

  /**
   * Get all premium modules (for upgrade UI)
   */
  const premiumModules = useMemo(() => {
    return allModules.filter(m => m.category === 'premium');
  }, [allModules]);

  /**
   * Get locked modules (premium modules not enabled)
   */
  const lockedModules = useMemo(() => {
    return allModules.filter(m =>
      m.category === 'premium' && !enabledModules.includes(m.module_key)
    );
  }, [allModules, enabledModules]);

  /**
   * Refresh modules from API
   */
  const refreshModules = useCallback(() => {
    return fetchModules(true);
  }, [fetchModules]);

  const value = useMemo(() => ({
    // State
    enabledModules,
    allModules,
    premiumModules,
    lockedModules,
    pricing,
    loading,
    error,

    // Methods
    hasModule,
    hasFeature,
    isRouteAccessible,
    getModule,
    refreshModules
  }), [
    enabledModules,
    allModules,
    premiumModules,
    lockedModules,
    pricing,
    loading,
    error,
    hasModule,
    hasFeature,
    isRouteAccessible,
    getModule,
    refreshModules
  ]);

  return (
    <ModuleContext.Provider value={value}>
      {children}
    </ModuleContext.Provider>
  );
};

/**
 * Hook to access module context
 */
export const useModules = () => {
  const context = useContext(ModuleContext);
  if (!context) {
    throw new Error('useModules must be used within a ModuleProvider');
  }
  return context;
};

/**
 * HOC to require a specific module
 */
export const withModule = (moduleKey, FallbackComponent = null) => (WrappedComponent) => {
  return function ModuleGatedComponent(props) {
    const { hasModule } = useModules();

    if (!hasModule(moduleKey)) {
      if (FallbackComponent) {
        return <FallbackComponent moduleKey={moduleKey} {...props} />;
      }
      return null;
    }

    return <WrappedComponent {...props} />;
  };
};

/**
 * Component to gate content based on module access
 */
export const ModuleGate = ({
  module,
  children,
  fallback = null,
  showLocked = false
}) => {
  const { hasModule, getModule } = useModules();

  if (hasModule(module)) {
    return children;
  }

  if (showLocked) {
    const moduleInfo = getModule(module);
    return (
      <div className="module-locked">
        <div className="locked-content">
          <span className="lock-icon">🔒</span>
          <span className="locked-text">
            Requires {moduleInfo?.module_name || module} module
          </span>
          <button className="upgrade-btn">Upgrade</button>
        </div>
      </div>
    );
  }

  return fallback;
};

export default ModuleContext;
