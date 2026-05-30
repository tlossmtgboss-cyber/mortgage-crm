/**
 * usePortalRealtime tests (portal realtime Phase 1 — polling fallback).
 *
 * Verifies the polling contract: initial fetch + onUpdate on success, 30s tick,
 * stop-on-401/403 with onError, and the imperative refreshNow path. The hook
 * only ever talks to api.getWorkspaceData (the PURL-token Bearer path) — it
 * never puts a token in a URL.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const mockApi = vi.hoisted(() => ({
  getWorkspaceData: vi.fn(),
  setAuthToken: vi.fn(),
}));

vi.mock('../../lib/api', () => ({
  api: {
    getWorkspaceData: mockApi.getWorkspaceData,
    setAuthToken: mockApi.setAuthToken,
  },
}));

import usePortalRealtime from '../usePortalRealtime';

describe('usePortalRealtime', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockApi.getWorkspaceData.mockReset().mockResolvedValue({ workspace: { status: 'mum' } });
    mockApi.setAuthToken.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('fetches workspace data on mount and calls onUpdate', async () => {
    const onUpdate = vi.fn();
    renderHook(() => usePortalRealtime({ slug: 'jane-doe', token: 'purl_live_abc', onUpdate }));

    await act(async () => { await Promise.resolve(); });

    expect(mockApi.setAuthToken).toHaveBeenCalledWith('purl_live_abc');
    expect(mockApi.getWorkspaceData).toHaveBeenCalledWith('jane-doe');
    expect(onUpdate).toHaveBeenCalledWith({ workspace: { status: 'mum' } });
  });

  it('reports transport "poll" in Phase 1', () => {
    const { result } = renderHook(() => usePortalRealtime({ slug: 's', token: 't' }));
    expect(result.current.transport).toBe('poll');
  });

  it('does not fetch when disabled', async () => {
    renderHook(() => usePortalRealtime({ slug: 's', token: 't', enabled: false }));
    await act(async () => { await Promise.resolve(); });
    expect(mockApi.getWorkspaceData).not.toHaveBeenCalled();
  });

  it('polls again on the interval tick', async () => {
    renderHook(() => usePortalRealtime({ slug: 's', token: 't', intervalMs: 30000 }));
    await act(async () => { await Promise.resolve(); });
    expect(mockApi.getWorkspaceData).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(30000);
      await Promise.resolve();
    });
    expect(mockApi.getWorkspaceData).toHaveBeenCalledTimes(2);
  });

  it('stops polling and calls onError on a 401', async () => {
    const onError = vi.fn();
    const err = Object.assign(new Error('unauth'), { status: 401 });
    mockApi.getWorkspaceData.mockRejectedValue(err);

    renderHook(() => usePortalRealtime({ slug: 's', token: 't', intervalMs: 30000, onError }));
    await act(async () => { await Promise.resolve(); });

    expect(onError).toHaveBeenCalledWith(err);

    // After the auth stop, a tick must not issue another request.
    const callsAfterStop = mockApi.getWorkspaceData.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(60000);
      await Promise.resolve();
    });
    expect(mockApi.getWorkspaceData).toHaveBeenCalledTimes(callsAfterStop);
  });

  it('refreshNow triggers an immediate refetch', async () => {
    const { result } = renderHook(() => usePortalRealtime({ slug: 's', token: 't' }));
    await act(async () => { await Promise.resolve(); });
    const before = mockApi.getWorkspaceData.mock.calls.length;

    await act(async () => {
      await result.current.refreshNow();
    });
    expect(mockApi.getWorkspaceData.mock.calls.length).toBe(before + 1);
  });

  it('sets lastUpdatedAt after a successful fetch', async () => {
    const { result } = renderHook(() => usePortalRealtime({ slug: 's', token: 't' }));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(result.current.lastUpdatedAt).not.toBeNull();
  });
});
