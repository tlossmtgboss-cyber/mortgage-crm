/**
 * Portal Authentication Provider
 *
 * React Context provider for managing borrower portal authentication.
 * Integrates with FastAPI magic link authentication.
 */

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { api, usePortalSession, useSendMagicLink, useVerifyMagicLink } from './index';

// Auth context
const PortalAuthContext = createContext(null);

/**
 * Portal Auth Provider Component
 */
export function PortalAuthProvider({ children, workspaceSlug }) {
  const [isInitialized, setIsInitialized] = useState(false);

  // Use session hook for state management
  const {
    session,
    loading: sessionLoading,
    error: sessionError,
    isAuthenticated,
    logout: doLogout,
    refresh: refreshSession,
    checkSession,
  } = usePortalSession();

  // Magic link hooks
  const {
    mutate: sendMagicLink,
    loading: sendingLink,
    error: sendLinkError,
  } = useSendMagicLink();

  const {
    mutate: verifyToken,
    loading: verifyingToken,
    error: verifyError,
  } = useVerifyMagicLink();

  // Check for token in URL on mount
  useEffect(() => {
    const checkUrlToken = async () => {
      const urlParams = new URLSearchParams(window.location.search);
      const token = urlParams.get('token');

      if (token) {
        try {
          await verifyToken(token);
          // Clear token from URL
          const newUrl = new URL(window.location.href);
          newUrl.searchParams.delete('token');
          window.history.replaceState({}, '', newUrl.toString());
          // Refresh session after verification
          await checkSession();
        } catch (err) {
          console.error('Token verification failed:', err);
        }
      }
      setIsInitialized(true);
    };

    checkUrlToken();
  }, [verifyToken, checkSession]);

  // Request magic link
  const requestMagicLink = useCallback(async (email, redirectPath = null) => {
    const response = await sendMagicLink({
      workspaceId: session?.workspace_id,
      email,
      redirectPath,
    });
    return response;
  }, [sendMagicLink, session?.workspace_id]);

  // Logout handler
  const logout = useCallback(async () => {
    try {
      await doLogout();
      // Clear local storage tokens
      if (workspaceSlug) {
        localStorage.removeItem(`purl_token_${workspaceSlug}`);
      }
      // Clear API client auth
      api.clearAuthToken();
    } catch (err) {
      console.error('Logout failed:', err);
    }
  }, [doLogout, workspaceSlug]);

  // Memoized context value
  const contextValue = useMemo(() => ({
    // State
    isInitialized,
    isAuthenticated,
    session,
    loading: sessionLoading || !isInitialized,
    error: sessionError || sendLinkError || verifyError,

    // Auth status helpers
    user: session ? {
      email: session.email,
      name: session.contact_name,
      workspaceId: session.workspace_id,
    } : null,

    // Actions
    requestMagicLink,
    logout,
    refreshSession,
    checkSession,

    // Loading states
    sendingLink,
    verifyingToken,
  }), [
    isInitialized,
    isAuthenticated,
    session,
    sessionLoading,
    sessionError,
    sendLinkError,
    verifyError,
    requestMagicLink,
    logout,
    refreshSession,
    checkSession,
    sendingLink,
    verifyingToken,
  ]);

  return (
    <PortalAuthContext.Provider value={contextValue}>
      {children}
    </PortalAuthContext.Provider>
  );
}

/**
 * Hook to access portal auth context
 */
export function usePortalAuth() {
  const context = useContext(PortalAuthContext);
  if (!context) {
    throw new Error('usePortalAuth must be used within a PortalAuthProvider');
  }
  return context;
}

/**
 * Higher-order component for protected routes
 */
export function withPortalAuth(WrappedComponent) {
  return function AuthenticatedComponent(props) {
    const { isAuthenticated, loading, isInitialized } = usePortalAuth();

    if (!isInitialized || loading) {
      return (
        <div className="auth-loading">
          <div className="spinner" />
          <p>Loading...</p>
        </div>
      );
    }

    if (!isAuthenticated) {
      return (
        <div className="auth-required">
          <h2>Access Required</h2>
          <p>Please use your portal access link to view this page.</p>
        </div>
      );
    }

    return <WrappedComponent {...props} />;
  };
}

/**
 * Component that only renders when authenticated
 */
export function RequirePortalAuth({ children, fallback = null }) {
  const { isAuthenticated, loading, isInitialized } = usePortalAuth();

  if (!isInitialized || loading) {
    return fallback || (
      <div className="auth-loading">
        <div className="spinner" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return fallback;
  }

  return children;
}

export default PortalAuthProvider;
