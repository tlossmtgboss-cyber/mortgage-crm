/**
 * Centralized React Query hooks for API data fetching
 * These hooks provide caching, background refetching, and optimistic updates
 * for lightning-fast navigation across the CRM
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getToken } from '../utils/tokenStore';

// API Base URL
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE_URL = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Helper to get auth headers
const getAuthHeaders = () => ({
  'Authorization': `Bearer ${getToken()}`,
  'Content-Type': 'application/json',
});

// Generic fetch function with error handling
const fetchWithAuth = async (endpoint, options = {}) => {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      ...getAuthHeaders(),
      ...options.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
};

// ============================================================================
// LEADS QUERIES
// ============================================================================

export const useLeads = (options = {}) => {
  return useQuery({
    queryKey: ['leads', options],
    queryFn: () => fetchWithAuth('/api/v1/leads/'),
    staleTime: 1000 * 60 * 5, // 5 minutes
    ...options,
  });
};

export const useLead = (leadId, options = {}) => {
  return useQuery({
    queryKey: ['lead', leadId],
    queryFn: () => fetchWithAuth(`/api/v1/leads/${leadId}`),
    enabled: !!leadId,
    staleTime: 1000 * 60 * 5,
    ...options,
  });
};

export const useLeadStats = (options = {}) => {
  return useQuery({
    queryKey: ['leadStats'],
    queryFn: () => fetchWithAuth('/api/v1/leads/stats'),
    staleTime: 1000 * 60 * 2, // 2 minutes for stats
    ...options,
  });
};

// ============================================================================
// LOANS QUERIES
// ============================================================================

export const useLoans = (options = {}) => {
  return useQuery({
    queryKey: ['loans', options],
    queryFn: () => fetchWithAuth('/api/v1/loans/'),
    staleTime: 1000 * 60 * 5,
    ...options,
  });
};

export const useLoan = (loanId, options = {}) => {
  return useQuery({
    queryKey: ['loan', loanId],
    queryFn: () => fetchWithAuth(`/api/v1/loans/${loanId}`),
    enabled: !!loanId,
    staleTime: 1000 * 60 * 5,
    ...options,
  });
};

// ============================================================================
// DASHBOARD QUERIES
// ============================================================================

export const useDashboard = (options = {}) => {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: () => fetchWithAuth('/api/v1/dashboard'),
    staleTime: 1000 * 60 * 2, // 2 minutes for dashboard
    ...options,
  });
};

export const useDashboardStats = (options = {}) => {
  return useQuery({
    queryKey: ['dashboardStats'],
    queryFn: () => fetchWithAuth('/api/v1/dashboard/stats'),
    staleTime: 1000 * 60 * 2,
    ...options,
  });
};

// ============================================================================
// TASKS QUERIES
// ============================================================================

export const useTasks = (options = {}) => {
  return useQuery({
    queryKey: ['tasks', options],
    queryFn: () => fetchWithAuth('/api/v1/tasks'),
    staleTime: 1000 * 60 * 2,
    ...options,
  });
};

export const useTask = (taskId, options = {}) => {
  return useQuery({
    queryKey: ['task', taskId],
    queryFn: () => fetchWithAuth(`/api/v1/tasks/${taskId}`),
    enabled: !!taskId,
    staleTime: 1000 * 60 * 2,
    ...options,
  });
};

// ============================================================================
// PORTFOLIO / CLIENTS QUERIES
// ============================================================================

export const usePortfolio = (options = {}) => {
  return useQuery({
    queryKey: ['portfolio', options],
    queryFn: () => fetchWithAuth('/api/v1/mum-clients/'),
    staleTime: 1000 * 60 * 5,
    ...options,
  });
};

export const useClient = (clientId, options = {}) => {
  return useQuery({
    queryKey: ['client', clientId],
    queryFn: () => fetchWithAuth(`/api/v1/mum-clients/${clientId}`),
    enabled: !!clientId,
    staleTime: 1000 * 60 * 5,
    ...options,
  });
};

// ============================================================================
// REFERRAL PARTNERS QUERIES
// ============================================================================

export const useReferralPartners = (options = {}) => {
  return useQuery({
    queryKey: ['referralPartners', options],
    queryFn: () => fetchWithAuth('/api/v1/referral-partners'),
    staleTime: 1000 * 60 * 5,
    ...options,
  });
};

export const useReferralPartner = (partnerId, options = {}) => {
  return useQuery({
    queryKey: ['referralPartner', partnerId],
    queryFn: () => fetchWithAuth(`/api/v1/referral-partners/${partnerId}`),
    enabled: !!partnerId,
    staleTime: 1000 * 60 * 5,
    ...options,
  });
};

// ============================================================================
// TEAM QUERIES
// ============================================================================

export const useTeamMembers = (options = {}) => {
  return useQuery({
    queryKey: ['teamMembers', options],
    queryFn: () => fetchWithAuth('/api/v1/team/members'),
    staleTime: 1000 * 60 * 10, // 10 minutes for team data
    ...options,
  });
};

// ============================================================================
// PREFETCH UTILITIES
// ============================================================================

/**
 * Prefetch data for a route before navigation
 * Call this on hover or route change anticipation
 */
export const usePrefetch = () => {
  const queryClient = useQueryClient();

  const prefetchLeads = () => {
    queryClient.prefetchQuery({
      queryKey: ['leads', {}],
      queryFn: () => fetchWithAuth('/api/v1/leads/'),
      staleTime: 1000 * 60 * 5,
    });
  };

  const prefetchLoans = () => {
    queryClient.prefetchQuery({
      queryKey: ['loans', {}],
      queryFn: () => fetchWithAuth('/api/v1/loans/'),
      staleTime: 1000 * 60 * 5,
    });
  };

  const prefetchDashboard = () => {
    queryClient.prefetchQuery({
      queryKey: ['dashboard'],
      queryFn: () => fetchWithAuth('/api/v1/dashboard'),
      staleTime: 1000 * 60 * 2,
    });
  };

  const prefetchTasks = () => {
    queryClient.prefetchQuery({
      queryKey: ['tasks', {}],
      queryFn: () => fetchWithAuth('/api/v1/tasks'),
      staleTime: 1000 * 60 * 2,
    });
  };

  const prefetchPortfolio = () => {
    queryClient.prefetchQuery({
      queryKey: ['portfolio', {}],
      queryFn: () => fetchWithAuth('/api/v1/mum-clients/'),
      staleTime: 1000 * 60 * 5,
    });
  };

  const prefetchPartners = () => {
    queryClient.prefetchQuery({
      queryKey: ['referralPartners', {}],
      queryFn: () => fetchWithAuth('/api/v1/referral-partners'),
      staleTime: 1000 * 60 * 5,
    });
  };

  return {
    prefetchLeads,
    prefetchLoans,
    prefetchDashboard,
    prefetchTasks,
    prefetchPortfolio,
    prefetchPartners,
  };
};

// ============================================================================
// MUTATION HOOKS (for updates with optimistic UI)
// ============================================================================

export const useUpdateLead = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ leadId, data }) =>
      fetchWithAuth(`/api/v1/leads/${leadId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: (data, variables) => {
      // Update the specific lead in cache
      queryClient.setQueryData(['lead', variables.leadId], data);
      // Invalidate the leads list to refetch on next view
      queryClient.invalidateQueries({ queryKey: ['leads'] });
    },
  });
};

export const useUpdateLoan = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ loanId, data }) =>
      fetchWithAuth(`/api/v1/loans/${loanId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(['loan', variables.loanId], data);
      queryClient.invalidateQueries({ queryKey: ['loans'] });
    },
  });
};

export const useUpdateTask = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ taskId, data }) =>
      fetchWithAuth(`/api/v1/tasks/${taskId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(['task', variables.taskId], data);
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });
};
