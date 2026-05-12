import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '../contexts/ThemeContext';
import { ImpersonationProvider } from '../contexts/ImpersonationContext';
import { PermissionProvider } from '../contexts/PermissionContext';
import { ModuleProvider } from '../contexts/ModuleContext';
import ErrorBoundary from '../components/ErrorBoundary';
import { toast } from '../utils/toast';

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
          return;
        }
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

// Export queryClient for use in App component (auth change handler)
export { queryClient };

/**
 * AppProviders - Composes all context providers for the application
 * Wraps children with QueryClient, ErrorBoundary, and auth/permission contexts
 */
function AppProviders({ children }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ErrorBoundary>
          <ImpersonationProvider>
            <PermissionProvider>
              <ModuleProvider>
                {children}
              </ModuleProvider>
            </PermissionProvider>
          </ImpersonationProvider>
        </ErrorBoundary>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default AppProviders;
