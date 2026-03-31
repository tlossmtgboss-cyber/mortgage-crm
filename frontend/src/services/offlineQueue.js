/**
 * offlineQueue.js - Offline command queue for Aria AI actions
 *
 * Queues API calls when offline and auto-retries when connectivity returns.
 * Uses localStorage for persistence across app restarts.
 */

const QUEUE_KEY = 'aria_offline_queue';
const MAX_RETRIES = 3;

let listeners = [];
let processing = false;

function getQueue() {
  try {
    const raw = localStorage.getItem(QUEUE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveQueue(queue) {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
  } catch {
    // Storage full — drop oldest entries
    if (queue.length > 1) {
      saveQueue(queue.slice(1));
    }
  }
}

function notify() {
  const queue = getQueue();
  listeners.forEach((fn) => fn(queue));
}

/**
 * Add a command to the offline queue.
 * @param {Object} command
 * @param {string} command.type - 'chat' | 'task' | 'sms' | 'custom'
 * @param {string} command.endpoint - API endpoint path
 * @param {string} command.method - 'POST' | 'GET' etc.
 * @param {Object} command.body - Request body
 * @param {string} [command.label] - Human-readable label for UI
 */
export function enqueue(command) {
  const queue = getQueue();
  queue.push({
    id: `oq_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    ...command,
    retries: 0,
    createdAt: new Date().toISOString(),
    status: 'pending',
  });
  saveQueue(queue);
  notify();
  // Try to flush immediately if online
  if (navigator.onLine) {
    flush();
  }
}

/**
 * Remove a specific item from the queue.
 */
export function remove(id) {
  const queue = getQueue().filter((item) => item.id !== id);
  saveQueue(queue);
  notify();
}

/**
 * Clear the entire queue.
 */
export function clear() {
  saveQueue([]);
  notify();
}

/**
 * Get current queue contents.
 */
export function getAll() {
  return getQueue();
}

/**
 * Get count of pending items.
 */
export function pendingCount() {
  return getQueue().filter((item) => item.status === 'pending').length;
}

/**
 * Subscribe to queue changes.
 * @param {Function} fn - Callback receiving the full queue array
 * @returns {Function} Unsubscribe function
 */
export function subscribe(fn) {
  listeners.push(fn);
  return () => {
    listeners = listeners.filter((l) => l !== fn);
  };
}

/**
 * Process all pending items in the queue.
 */
export async function flush() {
  if (processing || !navigator.onLine) return;
  processing = true;

  const queue = getQueue();
  const pending = queue.filter((item) => item.status === 'pending');

  for (const item of pending) {
    try {
      // Dynamic import to avoid circular dependency
      const { default: api } = await import('./api');

      const method = (item.method || 'POST').toLowerCase();
      await api[method](item.endpoint, item.body);

      // Mark as completed
      const updated = getQueue().map((q) =>
        q.id === item.id ? { ...q, status: 'completed' } : q
      );
      saveQueue(updated);
      notify();
    } catch (err) {
      // Increment retry count
      const updated = getQueue().map((q) => {
        if (q.id !== item.id) return q;
        const retries = (q.retries || 0) + 1;
        return {
          ...q,
          retries,
          status: retries >= MAX_RETRIES ? 'failed' : 'pending',
          lastError: err.message || 'Unknown error',
        };
      });
      saveQueue(updated);
      notify();

      // If we're offline now, stop processing
      if (!navigator.onLine) break;
    }
  }

  // Clean up completed items older than 1 hour
  const oneHourAgo = Date.now() - 3600000;
  const cleaned = getQueue().filter(
    (item) => item.status !== 'completed' || new Date(item.createdAt).getTime() > oneHourAgo
  );
  saveQueue(cleaned);

  processing = false;
  notify();
}

// Auto-flush when coming back online
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => {
    flush();
  });
}

export default { enqueue, remove, clear, getAll, pendingCount, subscribe, flush };
