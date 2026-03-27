import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

// ---------------------------------------------------------------------------
// Mocks — vi.hoisted ensures mock fns are defined before vi.mock hoisting
// ---------------------------------------------------------------------------

const mockGetDashboard = vi.hoisted(() => vi.fn());
const mockGetSlaCompliance = vi.hoisted(() => vi.fn());
const mockGetBottlenecks = vi.hoisted(() => vi.fn());

vi.mock('../../services/docAnalyticsApi', () => ({
  getDashboard: mockGetDashboard,
  getSlaCompliance: mockGetSlaCompliance,
  getBottlenecks: mockGetBottlenecks,
}));

import useDocAnalytics from '../useDocAnalytics';

// ---------------------------------------------------------------------------
// Sample fixture data
// ---------------------------------------------------------------------------

const DASHBOARD_DATA = {
  total_loans: 42,
  avg_completeness: 78.5,
  missing_docs_count: 12,
};

const SLA_DATA = {
  compliant_count: 35,
  breached_count: 7,
  compliance_rate: 83.3,
};

const BOTTLENECKS_DATA = {
  bottlenecks: [
    { stage: 'UNDERWRITING', avg_days: 9.2, count: 5 },
  ],
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useDocAnalytics', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetDashboard.mockResolvedValue(DASHBOARD_DATA);
    mockGetSlaCompliance.mockResolvedValue(SLA_DATA);
    mockGetBottlenecks.mockResolvedValue(BOTTLENECKS_DATA);
  });

  // =========================================================================
  // 1. Loads dashboard data on mount
  // =========================================================================

  it('sets loading=true initially, then false after data loads', async () => {
    const { result } = renderHook(() => useDocAnalytics());

    // loading starts true synchronously
    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
  });

  it('populates dashboard, sla, and bottlenecks on mount', async () => {
    const { result } = renderHook(() => useDocAnalytics());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.dashboard).toEqual(DASHBOARD_DATA);
    expect(result.current.sla).toEqual(SLA_DATA);
    expect(result.current.bottlenecks).toEqual(BOTTLENECKS_DATA);
    expect(result.current.error).toBeNull();
  });

  it('calls all three API functions with the default days value (30)', async () => {
    const { result } = renderHook(() => useDocAnalytics());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mockGetDashboard).toHaveBeenCalledOnce();
    expect(mockGetDashboard).toHaveBeenCalledWith(30);

    expect(mockGetSlaCompliance).toHaveBeenCalledOnce();
    expect(mockGetSlaCompliance).toHaveBeenCalledWith(30);

    expect(mockGetBottlenecks).toHaveBeenCalledOnce();
    expect(mockGetBottlenecks).toHaveBeenCalledWith(30);
  });

  it('passes a custom days value to all three API functions', async () => {
    const { result } = renderHook(() => useDocAnalytics(90));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mockGetDashboard).toHaveBeenCalledWith(90);
    expect(mockGetSlaCompliance).toHaveBeenCalledWith(90);
    expect(mockGetBottlenecks).toHaveBeenCalledWith(90);
  });

  it('re-fetches when the days prop changes', async () => {
    const { result, rerender } = renderHook(({ days }) => useDocAnalytics(days), {
      initialProps: { days: 30 },
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mockGetDashboard).toHaveBeenCalledTimes(1);

    // Change the days prop
    rerender({ days: 60 });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mockGetDashboard).toHaveBeenCalledTimes(2);
    expect(mockGetDashboard).toHaveBeenLastCalledWith(60);
  });

  // =========================================================================
  // 2. refresh() reloads data
  // =========================================================================

  it('refresh() reloads all three API functions', async () => {
    const { result } = renderHook(() => useDocAnalytics());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mockGetDashboard).toHaveBeenCalledTimes(1);

    // Call refresh
    await act(async () => {
      await result.current.refresh();
    });

    expect(mockGetDashboard).toHaveBeenCalledTimes(2);
    expect(mockGetSlaCompliance).toHaveBeenCalledTimes(2);
    expect(mockGetBottlenecks).toHaveBeenCalledTimes(2);
  });

  it('refresh() sets loading=true while in flight, then false', async () => {
    const { result } = renderHook(() => useDocAnalytics());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Trigger refresh and immediately check loading
    let refreshPromise;
    act(() => {
      refreshPromise = result.current.refresh();
    });

    expect(result.current.loading).toBe(true);

    await act(async () => {
      await refreshPromise;
    });

    expect(result.current.loading).toBe(false);
  });

  it('refresh() updates state with fresh API data', async () => {
    const { result } = renderHook(() => useDocAnalytics());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    const updatedDashboard = { ...DASHBOARD_DATA, total_loans: 99 };
    mockGetDashboard.mockResolvedValueOnce(updatedDashboard);

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.dashboard).toEqual(updatedDashboard);
  });

  // =========================================================================
  // 3. Sets error on failure
  // =========================================================================

  it('sets error message when getDashboard fails', async () => {
    mockGetDashboard.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useDocAnalytics());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Network error');
    expect(result.current.dashboard).toBeNull();
  });

  it('sets error message when getSlaCompliance fails', async () => {
    mockGetSlaCompliance.mockRejectedValue(new Error('SLA endpoint unavailable'));

    const { result } = renderHook(() => useDocAnalytics());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('SLA endpoint unavailable');
  });

  it('sets error message when getBottlenecks fails', async () => {
    mockGetBottlenecks.mockRejectedValue(new Error('Bottlenecks timeout'));

    const { result } = renderHook(() => useDocAnalytics());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Bottlenecks timeout');
  });

  it('clears a previous error on a successful refresh', async () => {
    mockGetDashboard.mockRejectedValueOnce(new Error('First failure'));

    const { result } = renderHook(() => useDocAnalytics());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('First failure');

    // Next call succeeds
    mockGetDashboard.mockResolvedValue(DASHBOARD_DATA);

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.error).toBeNull();
    expect(result.current.dashboard).toEqual(DASHBOARD_DATA);
  });

  it('sets loading=false even when a fetch fails (finally block)', async () => {
    mockGetBottlenecks.mockRejectedValue(new Error('fail'));

    const { result } = renderHook(() => useDocAnalytics());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // loading must be false regardless of the error
    expect(result.current.loading).toBe(false);
  });
});
