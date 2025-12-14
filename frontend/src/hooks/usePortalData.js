/**
 * usePortalData Hook
 *
 * Custom hook for managing portal data state with loading, error handling,
 * and automatic refresh capabilities.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  lifecycleApi,
  milestoneApi,
  closeOnTimeApi,
  homeValueApi,
  documentApi,
  borrowerPortalApi,
} from '../services/portalApi';

/**
 * Generic data fetching hook with caching and refresh
 */
export function useAsyncData(fetchFn, dependencies = [], options = {}) {
  const {
    initialData = null,
    refreshInterval = null,
    onError = null,
    enabled = true,
  } = options;

  const [data, setData] = useState(initialData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);

  const fetchData = useCallback(async () => {
    if (!enabled) return;

    try {
      setLoading(true);
      setError(null);
      const result = await fetchFn();
      if (mountedRef.current) {
        setData(result);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message || 'An error occurred');
        if (onError) onError(err);
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [fetchFn, enabled, onError]);

  useEffect(() => {
    mountedRef.current = true;
    fetchData();

    return () => {
      mountedRef.current = false;
    };
  }, [...dependencies, fetchData]);

  // Set up refresh interval if specified
  useEffect(() => {
    if (!refreshInterval || !enabled) return;

    const interval = setInterval(fetchData, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval, enabled, fetchData]);

  return {
    data,
    loading,
    error,
    refetch: fetchData,
    setData,
  };
}

/**
 * Hook for portal status data
 */
export function usePortalStatus(loanId) {
  return useAsyncData(
    () => lifecycleApi.getPortalStatus(loanId),
    [loanId],
    { enabled: !!loanId }
  );
}

/**
 * Hook for lifecycle stage data
 */
export function useLifecycleStage(loanId) {
  return useAsyncData(
    () => lifecycleApi.getLifecycleStage(loanId),
    [loanId],
    { enabled: !!loanId }
  );
}

/**
 * Hook for milestone data
 */
export function useMilestones(loanId, options = {}) {
  const { includeTasks = true, borrowerView = false } = options;

  return useAsyncData(
    () => milestoneApi.getLoanMilestones(loanId, includeTasks, borrowerView),
    [loanId, includeTasks, borrowerView],
    { enabled: !!loanId }
  );
}

/**
 * Hook for milestone progress
 */
export function useMilestoneProgress(loanId) {
  return useAsyncData(
    () => milestoneApi.getMilestoneProgress(loanId),
    [loanId],
    { enabled: !!loanId }
  );
}

/**
 * Hook for timeline data
 */
export function useTimelineData(loanId, viewType = 'horizontal', borrowerView = false) {
  return useAsyncData(
    () => milestoneApi.getTimelineData(loanId, viewType, borrowerView),
    [loanId, viewType, borrowerView],
    { enabled: !!loanId }
  );
}

/**
 * Hook for close-on-time countdown
 */
export function useCloseCountdown(loanId) {
  return useAsyncData(
    () => closeOnTimeApi.getCountdownData(loanId),
    [loanId],
    {
      enabled: !!loanId,
      refreshInterval: 60000, // Refresh every minute
    }
  );
}

/**
 * Hook for close-on-time calendar
 */
export function useCloseCalendar(loanId, startDate = null, weeks = 6) {
  return useAsyncData(
    () => closeOnTimeApi.getCalendarView(loanId, startDate, weeks),
    [loanId, startDate, weeks],
    { enabled: !!loanId }
  );
}

/**
 * Hook for home value dashboard
 */
export function useHomeValueDashboard(loanId) {
  return useAsyncData(
    () => homeValueApi.getHomeValueDashboard(loanId),
    [loanId],
    { enabled: !!loanId }
  );
}

/**
 * Hook for document checklist
 */
export function useDocumentChecklist(loanId, lifecycleStage) {
  return useAsyncData(
    () => documentApi.getDocumentChecklist(loanId, lifecycleStage),
    [loanId, lifecycleStage],
    { enabled: !!loanId && !!lifecycleStage }
  );
}

/**
 * Hook for document summary
 */
export function useDocumentSummary(loanId) {
  return useAsyncData(
    () => documentApi.getDocumentSummary(loanId),
    [loanId],
    { enabled: !!loanId }
  );
}

/**
 * Hook for recent activity
 */
export function useRecentActivity(loanId, limit = 20, borrowerVisibleOnly = false) {
  return useAsyncData(
    () => lifecycleApi.getRecentActivity(loanId, limit, borrowerVisibleOnly),
    [loanId, limit, borrowerVisibleOnly],
    {
      enabled: !!loanId,
      refreshInterval: 30000, // Refresh every 30 seconds
    }
  );
}

/**
 * Hook for borrower tasks
 */
export function useBorrowerTasks(loanId) {
  return useAsyncData(
    () => milestoneApi.getBorrowerTasks(loanId),
    [loanId],
    { enabled: !!loanId }
  );
}

/**
 * Comprehensive hook for borrower dashboard data
 */
export function useBorrowerDashboard(loanId) {
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchDashboard = useCallback(async () => {
    if (!loanId) return;

    try {
      setLoading(true);
      setError(null);

      // Fetch all data in parallel
      const [
        portalStatus,
        milestoneProgress,
        countdown,
        documentSummary,
        recentActivity,
        borrowerTasks,
      ] = await Promise.all([
        lifecycleApi.getPortalStatus(loanId),
        milestoneApi.getMilestoneProgress(loanId),
        closeOnTimeApi.getCountdownData(loanId).catch(() => null),
        documentApi.getDocumentSummary(loanId),
        lifecycleApi.getRecentActivity(loanId, 5, true),
        milestoneApi.getBorrowerTasks(loanId),
      ]);

      setDashboardData({
        portalStatus,
        milestoneProgress,
        countdown,
        documentSummary,
        recentActivity,
        borrowerTasks,
      });
    } catch (err) {
      setError(err.message || 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  return {
    data: dashboardData,
    loading,
    error,
    refetch: fetchDashboard,
  };
}

/**
 * Hook for MUM (Member Until Maturity) dashboard
 */
export function useMumDashboard(loanId) {
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchDashboard = useCallback(async () => {
    if (!loanId) return;

    try {
      setLoading(true);
      setError(null);

      const [
        portalStatus,
        homeValueDashboard,
        recentActivity,
      ] = await Promise.all([
        lifecycleApi.getPortalStatus(loanId),
        homeValueApi.getHomeValueDashboard(loanId),
        lifecycleApi.getRecentActivity(loanId, 10, true),
      ]);

      setDashboardData({
        portalStatus,
        homeValueDashboard,
        recentActivity,
      });
    } catch (err) {
      setError(err.message || 'Failed to load MUM dashboard');
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  return {
    data: dashboardData,
    loading,
    error,
    refetch: fetchDashboard,
  };
}

/**
 * Hook for milestone mutations
 */
export function useMilestoneMutations() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const updateMilestone = useCallback(async (milestoneId, status, notes = null) => {
    try {
      setLoading(true);
      setError(null);
      const result = await milestoneApi.updateMilestone(milestoneId, status, notes);
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const updateTask = useCallback(async (taskId, status, metadata = null) => {
    try {
      setLoading(true);
      setError(null);
      const result = await milestoneApi.updateTask(taskId, status, metadata);
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    updateMilestone,
    updateTask,
    loading,
    error,
  };
}

/**
 * Hook for lifecycle mutations
 */
export function useLifecycleMutations() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const transitionStage = useCallback(async (loanId, newStage, reason = null, force = false) => {
    try {
      setLoading(true);
      setError(null);
      const result = await lifecycleApi.transitionStage(loanId, newStage, reason, force);
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const recordHeartbeat = useCallback(async (loanId, activityType, description, metadata = null) => {
    try {
      setLoading(true);
      setError(null);
      const result = await lifecycleApi.recordHeartbeat(loanId, activityType, description, metadata);
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    transitionStage,
    recordHeartbeat,
    loading,
    error,
  };
}

export default {
  useAsyncData,
  usePortalStatus,
  useLifecycleStage,
  useMilestones,
  useMilestoneProgress,
  useTimelineData,
  useCloseCountdown,
  useCloseCalendar,
  useHomeValueDashboard,
  useDocumentChecklist,
  useDocumentSummary,
  useRecentActivity,
  useBorrowerTasks,
  useBorrowerDashboard,
  useMumDashboard,
  useMilestoneMutations,
  useLifecycleMutations,
};
