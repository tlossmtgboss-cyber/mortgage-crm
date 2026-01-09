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

// Use the same API URL as the rest of the app (handles production vs dev)
const API_BASE = API_BASE_URL;

// Cache duration in milliseconds (5 minutes)
const CACHE_TTL = 5 * 60 * 1000;

// All premium module keys - admins get access to all
const ALL_PREMIUM_MODULES = [
  'base',
  'ai_assistant',
  'partner_portals',
  'video_os',
  'recruiting_suite',
  'conversation_intelligence',
  'advanced_analytics',
  'integrations'
];

/**
 * Check if current user is an admin from localStorage
 */
const checkIsAdmin = () => {
  try {
    const userStr = localStorage.getItem('user');
    if (!userStr) return false;
    const user = JSON.parse(userStr);
    const role = user.permission_role || user.role;
    return role === 'admin' || role === 'owner' || role === 'management' || role === 'leadership';
  } catch {
    return false;
  }
};

const ModuleContext = createContext(null);

export const ModuleProvider = ({ children }) => {
  const [enabledModules, setEnabledModules] = useState(['base']); // Base is always enabled
  const [isAdmin, setIsAdmin] = useState(checkIsAdmin); // Track admin status
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

    // Check admin status on each fetch
    const adminStatus = checkIsAdmin();
    setIsAdmin(adminStatus);

    // If admin, grant access to all modules immediately
    if (adminStatus) {
      console.log('ModuleContext: Admin user detected - granting full module access');
      setEnabledModules(ALL_PREMIUM_MODULES);
      setLoading(false);
      setLastFetch(Date.now());
      // Still fetch module details for UI, but don't gate on them
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
          // Still grant admin full access even if API fails
          if (adminStatus) {
            setEnabledModules(ALL_PREMIUM_MODULES);
          } else {
            setEnabledModules(['base']);
          }
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

      // Admins get all modules regardless of what API returns
      if (adminStatus) {
        setEnabledModules(ALL_PREMIUM_MODULES);
      } else {
        setEnabledModules(enabled.length > 0 ? enabled : ['base']);
      }
      setAllModules(data.modules);
      setPricing(data.pricing);
      setLastFetch(Date.now());

      // Cache in localStorage for faster initial load
      localStorage.setItem('moduleCache', JSON.stringify({
        enabledModules: adminStatus ? ALL_PREMIUM_MODULES : enabled,
        isAdmin: adminStatus,
        timestamp: Date.now()
      }));

    } catch (err) {
      console.error('Error fetching modules:', err);
      setError(err.message);

      // Admins still get full access even on error
      if (adminStatus) {
        setEnabledModules(ALL_PREMIUM_MODULES);
      } else {
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
      }
    } finally {
      setLoading(false);
    }
  }, [lastFetch]);

  // Load cached modules on mount, then fetch fresh data
  useEffect(() => {
    // Check admin status immediately
    const adminStatus = checkIsAdmin();
    setIsAdmin(adminStatus);

    // If admin, grant full access immediately (don't wait for API)
    if (adminStatus) {
      setEnabledModules(ALL_PREMIUM_MODULES);
      setLoading(false);
    } else {
      // Quick load from cache for non-admins
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
    }

    // Fetch fresh data (for module details even for admins)
    fetchModules();
  }, [fetchModules]);

  /**
   * Check if organization has access to a specific module
   * Admins have access to all modules
   */
  const hasModule = useCallback((moduleKey) => {
    // Admins have access to all modules
    if (isAdmin) return true;
    // Base module is always available
    if (moduleKey === 'base') return true;
    return enabledModules.includes(moduleKey);
  }, [enabledModules, isAdmin]);

  /**
   * Check if organization has access to a specific feature
   * Admins have access to all features
   */
  const hasFeature = useCallback((featureKey) => {
    // Admins have access to all features
    if (isAdmin) return true;
    return allModules.some(module =>
      enabledModules.includes(module.module_key) &&
      module.included_features?.includes(featureKey)
    );
  }, [enabledModules, allModules, isAdmin]);

  /**
   * Check if a route is accessible based on modules
   * Returns { accessible: boolean, requiredModule?: object }
   * Admins have access to all routes
   */
  const isRouteAccessible = useCallback((routePath) => {
    // Admins have access to all routes
    if (isAdmin) {
      return { accessible: true, module: null };
    }

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
  }, [enabledModules, allModules, isAdmin]);

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
   * Admins have no locked modules
   */
  const lockedModules = useMemo(() => {
    // Admins have no locked modules
    if (isAdmin) return [];
    return allModules.filter(m =>
      m.category === 'premium' && !enabledModules.includes(m.module_key)
    );
  }, [allModules, enabledModules, isAdmin]);

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
    isAdmin, // Admin users have full access to all modules

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
    isAdmin,
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
