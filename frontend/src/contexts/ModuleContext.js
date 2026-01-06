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

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

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

      const response = await fetch(`${API_BASE}/api/v1/modules/my-modules`, {
        headers: getAuthHeaders()
      });

      if (!response.ok) {
        // If 401/403, user might not be logged in - use defaults
        if (response.status === 401 || response.status === 403) {
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

    // Fetch fresh data
    fetchModules();
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
