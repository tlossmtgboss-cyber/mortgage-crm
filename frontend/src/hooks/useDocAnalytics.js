/**
 * useDocAnalytics Hook
 *
 * Loads analytics dashboard data (dashboard summary, SLA compliance,
 * and bottleneck analysis) in parallel. Re-fetches when `days` changes.
 */

import { useState, useEffect, useCallback } from 'react';
import { getDashboard, getSlaCompliance, getBottlenecks } from '../services/docAnalyticsApi';

/**
 * @param {number} days - Lookback window in days (default 30)
 * @returns {{ dashboard, sla, bottlenecks, loading, error, refresh }}
 */
export function useDocAnalytics(days = 30) {
  const [dashboard, setDashboard] = useState(null);
  const [sla, setSla] = useState(null);
  const [bottlenecks, setBottlenecks] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashboardData, slaData, bottlenecksData] = await Promise.all([
        getDashboard(days),
        getSlaCompliance(days),
        getBottlenecks(days),
      ]);
      setDashboard(dashboardData);
      setSla(slaData);
      setBottlenecks(bottlenecksData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  return {
    dashboard,
    sla,
    bottlenecks,
    loading,
    error,
    refresh: fetchAll,
  };
}

export default useDocAnalytics;
