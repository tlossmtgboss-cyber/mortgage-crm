import { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Capacitor } from '@capacitor/core';
import { App as CapApp } from '@capacitor/app';
import { SplashScreen } from '@capacitor/splash-screen';
import { isAuthenticatedSync as isAuthenticated, migrateAuthTokens } from './utils/auth';
import { ImpersonationProvider } from './contexts/ImpersonationContext';
import { PermissionProvider, usePermissions } from './contexts/PermissionContext';
import { ModuleProvider, useModules } from './contexts/ModuleContext';
import { BrandingProvider } from './contexts/BrandingContext';
import { ThemeProvider } from './contexts/ThemeContext';
import AIAssistant from './components/AIAssistant';
import ImpersonationBanner from './components/ImpersonationBanner';
import ErrorBoundary from './components/ErrorBoundary';
import UnifiedTaskSidebar from './components/UnifiedTaskSidebar';
import GlobalLayoutFix from './components/GlobalLayoutFix';
import GlobalSearch from './components/GlobalSearch';
import { OfflineIndicator } from './components/OfflineIndicator';
import UpdateRequiredModal from './components/mobile/UpdateRequiredModal';
import SessionTimeoutModal from './components/mobile/SessionTimeoutModal';
import { checkForUpdate, clearVersionCache } from './services/appVersionCheck';
import { initializePushNotifications, teardownPushNotifications } from './services/pushNotificationService';
import { initNotificationActions } from './services/notificationActions';
import { initDeepLinkRouter, consumePendingDeepLink } from './services/deepLinkRouter';
import { API_BASE_URL } from './services/api';
import { getToken } from './utils/tokenStore';
import InboundCallLightbox from './components/InboundCallLightbox';
import { getRoutes, PageLoader } from './routes/index';
import { toast } from './utils/toast';
import './App.css';

// Redirect to an external URL (outside React Router)
function ExternalRedirect({ to }) {
  useEffect(() => { window.location.href = to; }, [to]);
  return null;
}

/**
 * Invisible component that initializes push notifications and notification
 * action routing inside the Router context (so useNavigate is available).
 * Renders nothing.
 */
function PushNotificationInitializer() {
  const navigate = useNavigate();

  useEffect(() => {
    // Wire up notification action routing with the router's navigate function
    initNotificationActions(navigate);

    // Initialize deep link router (listens for appUrlOpen, custom scheme, cold launch)
    const cleanupDeepLinks = initDeepLinkRouter(navigate);

    // Auto-initialize push if user is already authenticated
    if (isAuthenticated()) {
      // Consume any pending deep link that was queued before login
      const pendingRoute = consumePendingDeepLink();
      if (pendingRoute) {
        navigate(pendingRoute);
      }

      // Delay to avoid blocking initial render
      const timer = setTimeout(() => {
        initializePushNotifications().catch((err) =>
          console.warn('Push notification auto-init failed:', err)
        );
      }, 3000);
      return () => {
        clearTimeout(timer);
        if (cleanupDeepLinks) cleanupDeepLinks();
      };
    }

    return () => {
      if (cleanupDeepLinks) cleanupDeepLinks();
    };
  }, [navigate]);

  return null;
}

// PageLoader imported from routes/index.jsx (single source of truth)

// Create a client with optimized defaults for instant navigation
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // Data is fresh for 5 minutes
      gcTime: 1000 * 60 * 30, // Cache persists for 30 minutes (formerly cacheTime)
      refetchOnWindowFocus: false, // Don't refetch on tab focus
      refetchOnMount: true, // Refetch stale/failed data on mount (staleTime still prevents unnecessary refetches)
      retry: 1, // Only retry once on failure
      onError: (error) => {
        if (error?.response?.status === 401) {
          // Don't toast on 401 — the auth flow handles this
          return;
        }
        // Log unexpected query errors for debugging
        console.error('Query error:', error);
      },
    },
    mutations: {
      onError: (error) => {
        toast.error(error?.response?.data?.detail || error?.message || 'Something went wrong');
      },
    },
  },
});

/**
 * PrivateRoute - Blocks rendering until auth + permissions + modules are loaded.
 * This is the authoritative version used by all routes via getRoutes().
 */
function PrivateRoute({ children }) {
  const { loading: permissionsLoading } = usePermissions();
  const { loading: modulesLoading } = useModules();

  if (!isAuthenticated()) {
    return <Navigate to="/login" />;
  }

  // Block rendering until permissions and modules are loaded to prevent partial-load flicker
  if (permissionsLoading || modulesLoading) {
    return <PageLoader />;
  }

  return children;
}

// Floating action button for Aria — only on native (iOS) and mobile browser authenticated screens
function AriaFAB() {
  const location = useLocation();
  const navigate = useNavigate();

  const isMobile = Capacitor.isNativePlatform() || /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
  if (!isMobile) return null;
  if (!isAuthenticated()) return null;

  // Hide on public/auth pages and when already on Aria
  const hiddenPaths = ['/login', '/register', '/forgot-password', '/reset-password',
    '/verify-account', '/verify-email-sent', '/aria-voice', '/aria',
    '/mobile-aria', '/apply', '/aria-test', '/pos'];
  if (hiddenPaths.some(p => location.pathname === p || location.pathname.startsWith(p + '/'))) {
    return null;
  }

  return (
    <>
      <style>{`
        @keyframes aria-fab-pulse {
          0% { box-shadow: 0 4px 12px rgba(126, 184, 247, 0.4); }
          50% { box-shadow: 0 4px 20px rgba(126, 184, 247, 0.7), 0 0 0 8px rgba(126, 184, 247, 0.15); }
          100% { box-shadow: 0 4px 12px rgba(126, 184, 247, 0.4); }
        }
      `}</style>
      <button
        onClick={() => navigate('/aria-voice')}
        aria-label="Open Aria voice assistant"
        style={{
          position: 'fixed',
          bottom: 'calc(80px + env(safe-area-inset-bottom, 0px))',
          right: '20px',
          width: '56px',
          height: '56px',
          borderRadius: '50%',
          background: '#7EB8F7',
          border: 'none',
          boxShadow: '0 4px 12px rgba(126, 184, 247, 0.4)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          zIndex: 9998,
          animation: 'aria-fab-pulse 3s ease-in-out infinite',
          transition: 'transform 0.2s ease',
          WebkitTapHighlightColor: 'transparent',
        }}
        onTouchStart={(e) => { e.currentTarget.style.transform = 'scale(0.92)'; }}
        onTouchEnd={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 1C11.2044 1 10.4413 1.31607 9.87868 1.87868C9.31607 2.44129 9 3.20435 9 4V12C9 12.7956 9.31607 13.5587 9.87868 14.1213C10.4413 14.6839 11.2044 15 12 15C12.7956 15 13.5587 14.6839 14.1213 14.1213C14.6839 13.5587 15 12.7956 15 12V4C15 3.20435 14.6839 2.44129 14.1213 1.87868C13.5587 1.31607 12.7956 1 12 1Z" fill="white"/>
          <path d="M19 10V12C19 13.8565 18.2625 15.637 16.9497 16.9497C15.637 18.2625 13.8565 19 12 19C10.1435 19 8.36301 18.2625 7.05025 16.9497C5.7375 15.637 5 13.8565 5 12V10" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M12 19V23" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M8 23H16" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
    </>
  );
}

function App() {
  // --- App version check state ---
  const [versionStatus, setVersionStatus] = useState(null);
  const [updateBannerDismissed, setUpdateBannerDismissed] = useState(false);

  // Hide Capacitor splash screen on mount and migrate auth tokens
  useEffect(() => {
    // Migrate any localStorage-only auth tokens to Capacitor Preferences
    // before the app makes its first authenticated API call. No-op on web.
    migrateAuthTokens().catch(() => {});
    SplashScreen.hide().catch(() => {});
  }, []);

  // Check app version on launch (native only)
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    checkForUpdate().then(setVersionStatus).catch(() => {});

    // Re-check when the app returns to the foreground
    const listener = CapApp.addListener('appStateChange', ({ isActive }) => {
      if (isActive) {
        clearVersionCache();
        checkForUpdate({ force: true }).then(setVersionStatus).catch(() => {});
      }
    });

    return () => { listener.then(l => l.remove()); };
  }, []);

  // Deep link handling is managed by initDeepLinkRouter() in PushNotificationInitializer.
  // It handles appUrlOpen, custom scheme (perenniaai://), and cold launch URLs.

  const [assistantOpen, setAssistantOpen] = useState(false);
  const [coachOpen, setCoachOpen] = useState(false);
  const [taskSidebarOpen, setTaskSidebarOpen] = useState(false);

  // Task counts for navigation badges (MUM = Client for Life Engine tasks)
  const [taskCounts, setTaskCounts] = useState({
    leads: 0,
    loans: 0,
    portfolio: 3,  // MUM tasks
    tasks: 0,
    urgentTasks: 0,
    partners: 0,
    unifiedTasks: 0,  // New unified task count
    reconciliation: 0,  // Pending reconciliation items
    smartDocs: 0,  // Documents pending review
    smsUnread: 0  // Inbound SMS awaiting response
  });

  const toggleAssistant = () => {
    setAssistantOpen(!assistantOpen);
  };

  const toggleCoach = () => {
    setCoachOpen(!coachOpen);
  };

  const toggleTaskSidebar = () => {
    setTaskSidebarOpen(!taskSidebarOpen);
  };

  const handleUnifiedTaskCountChange = (count) => {
    setTaskCounts(prev => ({ ...prev, unifiedTasks: count }));
  };

  // Clear React Query cache on login/logout to prevent stale data
  useEffect(() => {
    const handleAuthChange = (event) => {
      const { type } = event.detail || {};

      // Clear all cached queries on login or logout
      queryClient.clear();

      // Reset task counts on logout
      if (type === 'logout') {
        setTaskCounts({
          leads: 0,
          loans: 0,
          portfolio: 0,
          tasks: 0,
          urgentTasks: 0,
          partners: 0,
          unifiedTasks: 0,
          reconciliation: 0,
          smartDocs: 0,
          smsUnread: 0
        });
        // Clean up push notification registration on logout
        teardownPushNotifications();
      }

      // Initialize push notifications on login
      if (type === 'login') {
        // Delay slightly so auth token is fully persisted
        setTimeout(() => {
          initializePushNotifications().catch((err) =>
            console.warn('Push notification init failed after login:', err)
          );
        }, 2000);
      }
    };

    window.addEventListener('authChange', handleAuthChange);
    return () => window.removeEventListener('authChange', handleAuthChange);
  }, []);

  // Fetch task counts for navigation badges
  useEffect(() => {
    const fetchTaskCounts = async () => {
      if (!isAuthenticated()) return;

      const headers = {
        'Authorization': `Bearer ${getToken()}`
      };

      try {
        // Fetch all counts in parallel
        const [tasksResponse, reconciliationResponse, smartDocsResponse, smsUnreadResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/v1/tasks`, { headers }).catch(() => null),
          fetch(`${API_BASE_URL}/api/v1/reconciliation/pending`, { headers }).catch(() => null),
          fetch(`${API_BASE_URL}/api/v1/smart-docs/applicants/pending-review`, { headers }).catch(() => null),
          fetch(`${API_BASE_URL}/api/v1/sms/unread-count`, { headers }).catch(() => null)
        ]);

        let updates = {};

        // Process tasks
        if (tasksResponse && tasksResponse.ok) {
          const tasks = await tasksResponse.json();
          const isTaskCompleted = (t) => {
            const s = (t.status || t.type || '').toLowerCase();
            return s === 'completed' || s === 'done';
          };
          const outstandingTasks = tasks.filter(t => !isTaskCompleted(t)).length;
          const urgentTasks = tasks.filter(t => t.priority === 'high' && !isTaskCompleted(t)).length;
          updates.tasks = outstandingTasks;
          updates.urgentTasks = urgentTasks;
        }

        // Process reconciliation count
        if (reconciliationResponse && reconciliationResponse.ok) {
          const reconciliationData = await reconciliationResponse.json();
          const items = Array.isArray(reconciliationData) ? reconciliationData : (reconciliationData.items || []);
          updates.reconciliation = items.length;
        }

        // Process smart docs count
        if (smartDocsResponse && smartDocsResponse.ok) {
          const smartDocsData = await smartDocsResponse.json();
          const totalPending = Array.isArray(smartDocsData)
            ? smartDocsData.reduce((sum, loan) => sum + (loan.pending_count || 0), 0)
            : 0;
          updates.smartDocs = totalPending;
        }

        // Process unread SMS count
        if (smsUnreadResponse && smsUnreadResponse.ok) {
          const smsData = await smsUnreadResponse.json();
          updates.smsUnread = smsData.unread_count || 0;
        }

        setTaskCounts(prev => ({ ...prev, ...updates }));
      } catch (error) {
        console.error('Error fetching task counts:', error);
      }
    };

    // OPTIMIZED: Delay initial fetch by 1 second to not block page load
    const initialTimeout = setTimeout(fetchTaskCounts, 1000);
    // Refresh task counts every 5 minutes (reduced frequency)
    const interval = setInterval(fetchTaskCounts, 300000);
    return () => {
      clearTimeout(initialTimeout);
      clearInterval(interval);
    };
  }, []);

  // Block the entire app when a forced update or maintenance is required
  if (versionStatus?.needsForceUpdate || versionStatus?.maintenanceMode) {
    return (
      <UpdateRequiredModal
        forceUpdate={versionStatus.needsForceUpdate}
        maintenanceMode={versionStatus.maintenanceMode}
        maintenanceMessage={versionStatus.maintenanceMessage}
        updateUrl={versionStatus.updateUrl}
        recommendedVersion={versionStatus.recommendedVersion}
        changelog={versionStatus.changelog}
      />
    );
  }

  // Build layout props once — shared by all routes via getRoutes()
  const layoutProps = {
    toggleAssistant,
    toggleCoach,
    toggleTaskSidebar,
    assistantOpen,
    coachOpen,
    taskSidebarOpen,
    taskCounts,
  };

  // Platform-dependent root element
  const rootElement = (
    Capacitor.isNativePlatform() || window.location.hostname.startsWith('192.168.')
      ? <Navigate to="/dashboard" />
      : <ExternalRedirect to="https://www.perenniaai.com" />
  );

  // Generate all routes from centralized config
  const routes = getRoutes(layoutProps, { PrivateRoute, rootElement });

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
      <ErrorBoundary>
        <OfflineIndicator />
        {/* GLBA-compliant session timeout — warns at 13min, locks at 15min of inactivity */}
        <SessionTimeoutModal />
        {/* Optional update banner (dismissible) */}
        {versionStatus?.updateAvailable && !updateBannerDismissed && (
          <UpdateRequiredModal
            updateAvailable
            updateUrl={versionStatus.updateUrl}
            recommendedVersion={versionStatus.recommendedVersion}
            onDismiss={() => setUpdateBannerDismissed(true)}
          />
        )}
        <ImpersonationProvider>
        <PermissionProvider>
        <ModuleProvider>
        <BrandingProvider>
          <Router>
            <PushNotificationInitializer />
            <GlobalLayoutFix />
            <ImpersonationBanner />
            <div className="app">
        <Routes>
          {routes}
        </Routes>
        {/* Global AI Assistant */}
        <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
        {/* Unified Task Sidebar */}
        <UnifiedTaskSidebar
          isOpen={taskSidebarOpen}
          onClose={() => setTaskSidebarOpen(false)}
          onTaskCountChange={handleUnifiedTaskCountChange}
        />
        {/* Global Search - floating, triggered by Cmd+K */}
        <GlobalSearch />
        {/* Aria FAB - floating mic button on native mobile */}
        <AriaFAB />
        <InboundCallLightbox />
        </div>
      </Router>
        </BrandingProvider>
        </ModuleProvider>
        </PermissionProvider>
        </ImpersonationProvider>
      </ErrorBoundary>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
