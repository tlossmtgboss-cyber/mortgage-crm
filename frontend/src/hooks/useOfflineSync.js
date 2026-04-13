/**
 * useOfflineSync — Convenience hook that combines network status with an
 * offline mutation queue stored in localStorage (key: "perennia_offline_queue").
 *
 * This hook provides a simplified interface for components that want to queue
 * mutations while offline and auto-sync when connectivity is restored.
 *
 * For the full-featured queue (retries, conflict detection, Capacitor Preferences
 * persistence), use useOfflineMutation instead.
 *
 * Returns { isOnline, pendingCount, queueMutation, syncNow }
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useNetworkStatus } from './useNetworkStatus';
import api from '../services/api';

const QUEUE_KEY = 'perennia_offline_queue';

// ---------------------------------------------------------------------------
// localStorage helpers
// ---------------------------------------------------------------------------

function _readQueue() {
  try {
    const raw = localStorage.getItem(QUEUE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function _writeQueue(queue) {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
  } catch {
    // Quota exceeded — trim completed items and retry
    const trimmed = queue.filter((m) => m.status !== 'completed');
    try {
      localStorage.setItem(QUEUE_KEY, JSON.stringify(trimmed));
    } catch {
      // Still too large — nothing we can do
    }
  }
}

function _uuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useOfflineSync() {
  const { isOnline } = useNetworkStatus();
  const [pendingCount, setPendingCount] = useState(0);
  const [isSyncing, setIsSyncing] = useState(false);
  const syncingRef = useRef(false);
  const mountedRef = useRef(true);

  // Track mount state
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Refresh pending count from localStorage
  const refreshCount = useCallback(() => {
    const queue = _readQueue();
    const pending = queue.filter((m) => m.status === 'pending').length;
    if (mountedRef.current) setPendingCount(pending);
    return pending;
  }, []);

  // Initialize count on mount
  useEffect(() => {
    refreshCount();
  }, [refreshCount]);

  // Listen for cross-tab storage changes
  useEffect(() => {
    const handleStorage = (e) => {
      if (e.key === QUEUE_KEY) refreshCount();
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [refreshCount]);

  /**
   * Add a mutation to the offline queue.
   *
   * @param {string} type - Mutation type identifier (e.g. "create_lead", "update_loan")
   * @param {object} data - Payload for the mutation
   * @returns {string} The mutation ID
   */
  const queueMutation = useCallback(
    (type, data) => {
      const entry = {
        id: _uuid(),
        type,
        data,
        status: 'pending',
        createdAt: Date.now(),
        retryCount: 0,
        lastError: null,
      };

      const queue = _readQueue();
      queue.push(entry);
      _writeQueue(queue);

      if (mountedRef.current) {
        setPendingCount(queue.filter((m) => m.status === 'pending').length);
      }

      return entry.id;
    },
    [],
  );

  /**
   * Process the queue by sending each pending mutation to the batch sync
   * endpoint. Falls back to individual requests if the batch endpoint
   * is unavailable (404).
   */
  const syncNow = useCallback(async () => {
    if (!isOnline || syncingRef.current) return;
    syncingRef.current = true;
    if (mountedRef.current) setIsSyncing(true);

    try {
      const queue = _readQueue();
      const pending = queue.filter((m) => m.status === 'pending');

      if (pending.length === 0) return;

      // Attempt batch sync first
      let useBatch = true;
      try {
        const batchPayload = pending.map((m) => ({
          id: m.id,
          type: m.type,
          data: m.data,
          created_at: m.createdAt,
        }));

        const response = await api.post('/api/v1/mobile/sync/batch', {
          mutations: batchPayload,
        });

        // Mark items based on batch response
        const results = response.data?.results || [];
        const resultMap = new Map(results.map((r) => [r.id, r]));

        for (const entry of queue) {
          if (entry.status !== 'pending') continue;
          const result = resultMap.get(entry.id);
          if (result) {
            entry.status = result.success ? 'completed' : 'failed';
            entry.lastError = result.error || null;
            entry.syncedAt = Date.now();
          }
        }
      } catch (batchErr) {
        if (batchErr?.response?.status === 404) {
          // Batch endpoint not available — fall back to individual requests
          useBatch = false;
        } else if (!batchErr?.response) {
          // Network error — leave pending for next attempt
          return;
        } else {
          useBatch = false;
        }
      }

      // Individual fallback
      if (!useBatch) {
        for (const entry of queue) {
          if (entry.status !== 'pending') continue;

          try {
            await api.post('/api/v1/mobile/sync/batch', {
              mutations: [
                {
                  id: entry.id,
                  type: entry.type,
                  data: entry.data,
                  created_at: entry.createdAt,
                },
              ],
            });
            entry.status = 'completed';
            entry.syncedAt = Date.now();
          } catch (err) {
            entry.retryCount += 1;
            entry.lastError = err?.response?.data?.detail || err.message || 'Sync failed';
            if (entry.retryCount >= 3) {
              entry.status = 'failed';
            }
          }
        }
      }

      // Remove completed items older than 1 minute to keep storage lean
      const cutoff = Date.now() - 60_000;
      const cleaned = queue.filter(
        (m) => !(m.status === 'completed' && m.syncedAt && m.syncedAt < cutoff),
      );
      _writeQueue(cleaned);
    } finally {
      syncingRef.current = false;
      if (mountedRef.current) {
        setIsSyncing(false);
        refreshCount();
      }
    }
  }, [isOnline, refreshCount]);

  // Auto-sync when transitioning from offline to online
  const prevOnlineRef = useRef(isOnline);
  useEffect(() => {
    const wasOffline = !prevOnlineRef.current;
    prevOnlineRef.current = isOnline;

    if (isOnline && wasOffline) {
      // Small delay to let the connection stabilize
      const timer = setTimeout(() => syncNow(), 800);
      return () => clearTimeout(timer);
    }
  }, [isOnline, syncNow]);

  return {
    isOnline,
    pendingCount,
    isSyncing,
    queueMutation,
    syncNow,
  };
}

export default useOfflineSync;
