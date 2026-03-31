/**
 * useOfflineMutation — React hook that routes write operations through
 * the offline mutation queue when the device has no network connectivity.
 *
 * Usage:
 *   const { mutate, isOnline, queueStatus } = useOfflineMutation();
 *
 *   // If online: executes immediately via axios and returns the response.
 *   // If offline: queues the mutation in Preferences for later sync.
 *   const result = await mutate({
 *     method: 'POST',
 *     url: '/api/v1/leads',
 *     body: { first_name: 'Jane', last_name: 'Doe' },
 *   });
 *   // result.queued === true when stored offline
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useNetworkStatus } from './useNetworkStatus';
import api from '../services/api';
import {
  enqueue,
  processQueue,
  getQueueStatus,
  subscribe,
  clearCompleted,
  retryAllFailed,
} from '../services/offlineMutationQueue';

export function useOfflineMutation() {
  const { isOnline } = useNetworkStatus();
  const [queueStatus, setQueueStatus] = useState({
    pending: 0,
    syncing: 0,
    failed: 0,
    conflict: 0,
    completed: 0,
    total: 0,
  });
  const [isSyncing, setIsSyncing] = useState(false);

  // Track mount state to prevent setState after unmount
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // Refresh status on mount
  useEffect(() => {
    getQueueStatus().then((s) => {
      if (mountedRef.current) setQueueStatus(s);
    });
  }, []);

  // Subscribe to queue events to keep status in sync
  useEffect(() => {
    const unsubscribe = subscribe((event) => {
      if (!mountedRef.current) return;

      if (event.type === 'processing_start') {
        setIsSyncing(true);
      } else if (event.type === 'processing_end') {
        setIsSyncing(false);
        if (event.status) setQueueStatus(event.status);
      } else {
        // For any other event, refresh the status
        getQueueStatus().then((s) => {
          if (mountedRef.current) setQueueStatus(s);
        });
      }
    });

    return unsubscribe;
  }, []);

  // When we come back online, process the queue
  useEffect(() => {
    if (isOnline && queueStatus.pending > 0) {
      processQueue();
    }
  }, [isOnline, queueStatus.pending]);

  /**
   * Execute a mutation. Online = immediate. Offline = queued.
   *
   * @param {{ method: string, url: string, body?: any, headers?: object }} mutation
   * @param {{ forceQueue?: boolean }} options  — forceQueue bypasses online check
   * @returns {Promise<{ queued: boolean, data?: any, mutationId?: string }>}
   */
  const mutate = useCallback(
    async (mutation, options = {}) => {
      const shouldQueue = !isOnline || options.forceQueue;

      if (!shouldQueue) {
        // Online path — execute directly
        try {
          const response = await api.request({
            method: (mutation.method || 'POST').toUpperCase(),
            url: mutation.url,
            data: mutation.body,
            headers: mutation.headers || {},
          });
          return { queued: false, data: response.data };
        } catch (err) {
          // If the request failed due to network, queue it instead of throwing
          if (!err.response) {
            const mutationId = await enqueue(mutation);
            return { queued: true, mutationId };
          }
          // Server responded with an error — propagate normally
          throw err;
        }
      }

      // Offline path — queue
      const mutationId = await enqueue(mutation);
      return { queued: true, mutationId };
    },
    [isOnline],
  );

  /**
   * Manually trigger queue processing (e.g. from a "Retry" button).
   */
  const syncNow = useCallback(async () => {
    if (!isOnline) return;
    await processQueue();
  }, [isOnline]);

  /**
   * Retry all failed mutations.
   */
  const retryFailed = useCallback(async () => {
    const count = await retryAllFailed();
    if (count > 0 && isOnline) {
      await processQueue();
    }
    return count;
  }, [isOnline]);

  /**
   * Clear completed mutations from storage.
   */
  const clearSynced = useCallback(async () => {
    await clearCompleted();
    const s = await getQueueStatus();
    if (mountedRef.current) setQueueStatus(s);
  }, []);

  // Convenience: total queued = pending + failed + conflict (items not yet resolved)
  const queueSize = queueStatus.pending + queueStatus.failed + queueStatus.conflict;

  return {
    mutate,
    syncNow,
    retryFailed,
    clearSynced,
    isOnline,
    isSyncing,
    queueSize,
    queueStatus,
  };
}

export default useOfflineMutation;
