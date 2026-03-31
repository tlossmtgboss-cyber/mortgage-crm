/**
 * offlineMutationQueue — Persistent offline mutation queue for Capacitor mobile app.
 *
 * Queues write operations (POST, PUT, PATCH, DELETE) in @capacitor/preferences
 * so they survive app restarts. Processes FIFO when connectivity is restored,
 * with exponential backoff on transient failures.
 *
 * Storage key: "offline_mutation_queue"
 */
import { Capacitor } from '@capacitor/core';
import api from './api';

// ---------------------------------------------------------------------------
// Storage helpers — Preferences on native, localStorage on web
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'offline_mutation_queue';

async function _readQueue() {
  let raw;
  if (Capacitor.isNativePlatform()) {
    const { Preferences } = await import('@capacitor/preferences');
    const result = await Preferences.get({ key: STORAGE_KEY });
    raw = result.value;
  } else {
    raw = localStorage.getItem(STORAGE_KEY);
  }
  if (!raw) return [];
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

async function _writeQueue(queue) {
  const serialized = JSON.stringify(queue);
  if (Capacitor.isNativePlatform()) {
    const { Preferences } = await import('@capacitor/preferences');
    await Preferences.set({ key: STORAGE_KEY, value: serialized });
  } else {
    try {
      localStorage.setItem(STORAGE_KEY, serialized);
    } catch {
      // localStorage quota exceeded — drop oldest completed items
      const trimmed = queue.filter((m) => m.status !== 'completed');
      localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
    }
  }
}

// ---------------------------------------------------------------------------
// UUID helper (no crypto dependency needed for queue IDs)
// ---------------------------------------------------------------------------

function _uuid() {
  // Simple v4-ish random ID
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_RETRIES = 3;
const BASE_BACKOFF_MS = 1000; // 1s, 2s, 4s

// ---------------------------------------------------------------------------
// Event emitter (lightweight, no dependency)
// ---------------------------------------------------------------------------

const _listeners = new Set();

function _emit(event) {
  _listeners.forEach((fn) => {
    try {
      fn(event);
    } catch {
      // Listener errors must not break the queue
    }
  });
}

// ---------------------------------------------------------------------------
// Processing lock — prevents concurrent processQueue() runs
// ---------------------------------------------------------------------------

let _processing = false;

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Add a mutation to the persistent queue.
 *
 * @param {{ method: string, url: string, body?: any, headers?: object }} mutation
 * @returns {Promise<string>} The mutation ID
 */
export async function enqueue(mutation) {
  const entry = {
    id: _uuid(),
    method: (mutation.method || 'POST').toUpperCase(),
    url: mutation.url,
    body: mutation.body || null,
    headers: mutation.headers || {},
    createdAt: Date.now(),
    retryCount: 0,
    status: 'pending', // pending | syncing | failed | completed | conflict
    lastError: null,
  };

  const queue = await _readQueue();
  queue.push(entry);
  await _writeQueue(queue);

  _emit({ type: 'enqueued', mutation: entry });

  return entry.id;
}

/**
 * Process the queue FIFO. Only pending and failed (with retries left) items
 * are attempted. Runs one item at a time to preserve ordering.
 *
 * Safe to call multiple times — concurrent calls are no-ops.
 */
export async function processQueue() {
  if (_processing) return;
  _processing = true;

  try {
    _emit({ type: 'processing_start' });

    let queue = await _readQueue();
    let changed = false;

    for (let i = 0; i < queue.length; i++) {
      const entry = queue[i];

      // Skip items that aren't actionable
      if (entry.status === 'completed' || entry.status === 'conflict') continue;
      if (entry.status === 'failed' && entry.retryCount >= MAX_RETRIES) continue;

      // Mark syncing
      entry.status = 'syncing';
      entry.lastError = null;
      await _writeQueue(queue);
      _emit({ type: 'syncing', mutation: entry });

      try {
        await api.request({
          method: entry.method,
          url: entry.url,
          data: entry.body,
          headers: entry.headers,
        });

        entry.status = 'completed';
        entry.syncedAt = Date.now();
        changed = true;
        _emit({ type: 'synced', mutation: entry });
      } catch (err) {
        const status = err?.response?.status;

        if (status === 409) {
          // Conflict — server rejected; surface for manual resolution
          entry.status = 'conflict';
          entry.lastError = err?.response?.data?.detail || 'Conflict: server version differs';
          changed = true;
          _emit({ type: 'conflict', mutation: entry });
        } else if (status >= 400 && status < 500 && status !== 408 && status !== 429) {
          // Permanent client error (except timeout/rate-limit) — no retry
          entry.status = 'failed';
          entry.retryCount = MAX_RETRIES;
          entry.lastError = err?.response?.data?.detail || err.message || 'Request failed';
          changed = true;
          _emit({ type: 'failed', mutation: entry });
        } else {
          // Transient error — increment retry, apply backoff
          entry.retryCount += 1;
          entry.status = entry.retryCount >= MAX_RETRIES ? 'failed' : 'pending';
          entry.lastError = err.message || 'Network error';
          changed = true;

          if (entry.retryCount < MAX_RETRIES) {
            const backoff = BASE_BACKOFF_MS * Math.pow(2, entry.retryCount - 1);
            await new Promise((r) => setTimeout(r, backoff));
          }

          _emit({ type: 'retry', mutation: entry, retryCount: entry.retryCount });
        }
      }

      // Persist state after each item
      await _writeQueue(queue);
    }

    // Re-read to pick up any items enqueued during processing
    if (changed) {
      queue = await _readQueue();
    }

    _emit({ type: 'processing_end', status: await getQueueStatus() });
  } finally {
    _processing = false;
  }
}

/**
 * Return a snapshot of queue counts.
 *
 * @returns {Promise<{ pending: number, syncing: number, failed: number, conflict: number, completed: number, total: number }>}
 */
export async function getQueueStatus() {
  const queue = await _readQueue();
  const counts = { pending: 0, syncing: 0, failed: 0, conflict: 0, completed: 0, total: queue.length };

  for (const entry of queue) {
    if (entry.status in counts) {
      counts[entry.status] += 1;
    }
  }

  return counts;
}

/**
 * Return the full queue (for debugging / conflict resolution UI).
 */
export async function getQueue() {
  return _readQueue();
}

/**
 * Remove all completed items from storage.
 */
export async function clearCompleted() {
  const queue = await _readQueue();
  const remaining = queue.filter((m) => m.status !== 'completed');
  await _writeQueue(remaining);
  _emit({ type: 'cleared', removed: queue.length - remaining.length });
}

/**
 * Remove a single mutation by ID (e.g. after manual conflict resolution).
 */
export async function removeMutation(id) {
  const queue = await _readQueue();
  const remaining = queue.filter((m) => m.id !== id);
  await _writeQueue(remaining);
  _emit({ type: 'removed', id });
}

/**
 * Reset a failed/conflict mutation back to pending for retry.
 */
export async function retryMutation(id) {
  const queue = await _readQueue();
  const entry = queue.find((m) => m.id === id);
  if (entry) {
    entry.status = 'pending';
    entry.retryCount = 0;
    entry.lastError = null;
    await _writeQueue(queue);
    _emit({ type: 'retry_reset', mutation: entry });
  }
}

/**
 * Reset ALL failed mutations back to pending.
 */
export async function retryAllFailed() {
  const queue = await _readQueue();
  let count = 0;
  for (const entry of queue) {
    if (entry.status === 'failed') {
      entry.status = 'pending';
      entry.retryCount = 0;
      entry.lastError = null;
      count++;
    }
  }
  if (count > 0) {
    await _writeQueue(queue);
    _emit({ type: 'retry_all', count });
  }
  return count;
}

/**
 * Subscribe to queue events. Returns an unsubscribe function.
 *
 * Event types: enqueued, processing_start, syncing, synced, conflict,
 *              failed, retry, processing_end, cleared, removed, retry_reset, retry_all
 */
export function subscribe(listener) {
  _listeners.add(listener);
  return () => _listeners.delete(listener);
}

// ---------------------------------------------------------------------------
// Network listener — auto-process queue when connectivity is restored
// ---------------------------------------------------------------------------

let _networkListenerInitialized = false;

export function initNetworkListener() {
  if (_networkListenerInitialized) return;
  _networkListenerInitialized = true;

  if (Capacitor.isNativePlatform()) {
    import('@capacitor/network').then(({ Network }) => {
      Network.addListener('networkStatusChange', (status) => {
        if (status.connected) {
          // Small delay to let the connection stabilize
          setTimeout(() => processQueue(), 500);
        }
      });
    });
  } else {
    window.addEventListener('online', () => {
      setTimeout(() => processQueue(), 500);
    });
  }
}

// Auto-init when module is imported
initNetworkListener();
