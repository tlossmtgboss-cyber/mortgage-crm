/**
 * Background Sync Service
 *
 * Coordinates periodic data refresh and offline queue processing
 * for the Perennia AI mobile app. Manages sync priorities, app state
 * awareness, network-aware fetching, and iOS background task integration.
 */

import { Capacitor } from '@capacitor/core';
import { getItem, setItem, getJSON, setJSON } from '../utils/storage';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SYNC_PREFIX = 'bg_sync_';
const OFFLINE_QUEUE_KEY = 'bg_sync_offline_queue';
const LAST_SYNC_KEY = 'bg_sync_last_sync';
const BACKGROUND_TASK_ID = 'com.perenniaai.crm.background-refresh';

/** Refresh intervals in milliseconds. */
export const SYNC_INTERVALS = {
  NOTIFICATIONS: 30 * 1000,       // 30 seconds
  TASKS_TODAY: 2 * 60 * 1000,     // 2 minutes
  PIPELINE: 5 * 60 * 1000,        // 5 minutes
  LEADS: 5 * 60 * 1000,           // 5 minutes
};

/** Sync priority levels — lower number = higher priority. */
const SYNC_PRIORITY = {
  HIGH: 1,    // Offline mutation queue (writes)
  MEDIUM: 2,  // Notifications, tasks
  LOW: 3,     // Pipeline data, analytics
};

// ---------------------------------------------------------------------------
// Internal state
// ---------------------------------------------------------------------------

let _initialized = false;
let _timers = {};
let _appIsActive = true;
let _syncInProgress = false;
let _networkStatus = { connected: true, connectionType: 'wifi' };
let _listeners = [];
let _appStateListener = null;
let _networkListener = null;

// Cached values for synchronous reads in getSyncStatus.
// Kept warm by _refreshCaches(), called after every state change.
let _lastSyncTimeCache = null;
let _offlineQueueCountCache = 0;

// ---------------------------------------------------------------------------
// Offline mutation queue
// ---------------------------------------------------------------------------

/**
 * Read the offline mutation queue from storage.
 * Each entry: { id, method, url, data, createdAt, retries }
 */
async function _getOfflineQueue() {
  const queue = await getJSON(OFFLINE_QUEUE_KEY);
  return Array.isArray(queue) ? queue : [];
}

async function _setOfflineQueue(queue) {
  await setJSON(OFFLINE_QUEUE_KEY, queue);
}

/**
 * Enqueue a failed write operation for later retry.
 * Call this from your API interceptor when a mutation fails due to
 * network issues.
 */
export async function enqueueOfflineMutation(method, url, data) {
  const queue = await _getOfflineQueue();
  queue.push({
    id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    method,
    url,
    data,
    createdAt: new Date().toISOString(),
    retries: 0,
  });
  await _setOfflineQueue(queue);
  _notifyListeners();
}

/**
 * Process the offline mutation queue. Sends each queued write in order.
 * Failed items are kept in the queue with an incremented retry count.
 * Items that exceed 5 retries are discarded.
 */
async function _processOfflineQueue() {
  const queue = await _getOfflineQueue();
  if (queue.length === 0) return;

  // Lazy-import api to avoid circular dependency at module load
  const { default: api } = await import('./api');

  const remaining = [];

  for (const entry of queue) {
    try {
      const method = (entry.method || 'post').toLowerCase();
      if (method === 'delete') {
        await api.delete(entry.url);
      } else if (method === 'put') {
        await api.put(entry.url, entry.data);
      } else if (method === 'patch') {
        await api.patch(entry.url, entry.data);
      } else {
        await api.post(entry.url, entry.data);
      }
      // Success — entry is removed from queue (not pushed to remaining)
    } catch (error) {
      const nextRetries = (entry.retries || 0) + 1;
      if (nextRetries < 5) {
        remaining.push({ ...entry, retries: nextRetries });
      } else {
        console.warn(`[BackgroundSync] Dropping mutation after 5 retries: ${entry.method} ${entry.url}`);
      }
    }
  }

  await _setOfflineQueue(remaining);
  _notifyListeners();
}

// ---------------------------------------------------------------------------
// Data fetchers
// ---------------------------------------------------------------------------

async function _fetchNotifications() {
  try {
    const { notificationsApi } = await import('./api');
    const result = await notificationsApi.getNotifications(true, 50);
    await setJSON(`${SYNC_PREFIX}notifications`, {
      data: result.data,
      fetchedAt: new Date().toISOString(),
    });
  } catch (error) {
    console.warn('[BackgroundSync] Notifications fetch failed:', error.message);
  }
}

async function _fetchTasksToday() {
  try {
    const { tasksAPI } = await import('./api');
    const today = new Date().toISOString().split('T')[0];
    const tasks = await tasksAPI.getAll({ due_date: today });
    await setJSON(`${SYNC_PREFIX}tasks_today`, {
      data: tasks,
      fetchedAt: new Date().toISOString(),
    });
  } catch (error) {
    console.warn('[BackgroundSync] Tasks fetch failed:', error.message);
  }
}

async function _fetchPipeline() {
  try {
    const { analyticsAPI } = await import('./api');
    const data = await analyticsAPI.getPipeline();
    await setJSON(`${SYNC_PREFIX}pipeline`, {
      data,
      fetchedAt: new Date().toISOString(),
    });
  } catch (error) {
    console.warn('[BackgroundSync] Pipeline fetch failed:', error.message);
  }
}

async function _fetchLeads() {
  try {
    const { leadsAPI } = await import('./api');
    // Fetch recent leads (last modified, limited set for background refresh)
    const leads = await leadsAPI.getAll({ limit: 50, sort: '-updated_at' });
    await setJSON(`${SYNC_PREFIX}leads`, {
      data: leads,
      fetchedAt: new Date().toISOString(),
    });
  } catch (error) {
    console.warn('[BackgroundSync] Leads fetch failed:', error.message);
  }
}

// ---------------------------------------------------------------------------
// Sync orchestrator
// ---------------------------------------------------------------------------

/**
 * Run a full sync cycle ordered by priority.
 *
 * @param {'full'|'essential'} mode
 *   - full: all data (on WiFi)
 *   - essential: mutations + notifications + tasks only (on cellular)
 */
async function _runSync(mode = 'full') {
  if (_syncInProgress) return;
  _syncInProgress = true;
  _notifyListeners();

  try {
    // HIGH priority — always process offline queue first
    await _processOfflineQueue();

    // MEDIUM priority — notifications and tasks
    await _fetchNotifications();
    await _fetchTasksToday();

    // LOW priority — only on full sync (WiFi)
    if (mode === 'full') {
      await _fetchPipeline();
      await _fetchLeads();
    }

    // Persist last sync timestamp
    const now = new Date().toISOString();
    await setItem(LAST_SYNC_KEY, now);
  } catch (error) {
    console.error('[BackgroundSync] Sync cycle error:', error);
  } finally {
    _syncInProgress = false;
    _notifyListeners();
  }
}

/**
 * Determine sync mode based on current network state.
 * Returns null if offline (skip sync).
 */
function _getSyncMode() {
  if (!_networkStatus.connected) return null;
  if (_networkStatus.connectionType === 'wifi') return 'full';
  // Cellular — essential only
  return 'essential';
}

// ---------------------------------------------------------------------------
// Periodic timers
// ---------------------------------------------------------------------------

function _startTimers() {
  _stopTimers();

  // Notifications — every 30s
  _timers.notifications = setInterval(async () => {
    const mode = _getSyncMode();
    if (!mode) return;
    try { await _fetchNotifications(); } catch {}
  }, SYNC_INTERVALS.NOTIFICATIONS);

  // Tasks due today — every 2min
  _timers.tasksToday = setInterval(async () => {
    const mode = _getSyncMode();
    if (!mode) return;
    try { await _fetchTasksToday(); } catch {}
  }, SYNC_INTERVALS.TASKS_TODAY);

  // Pipeline — every 5min (full mode only)
  _timers.pipeline = setInterval(async () => {
    const mode = _getSyncMode();
    if (mode !== 'full') return;
    try { await _fetchPipeline(); } catch {}
  }, SYNC_INTERVALS.PIPELINE);

  // Leads — every 5min (full mode only)
  _timers.leads = setInterval(async () => {
    const mode = _getSyncMode();
    if (mode !== 'full') return;
    try { await _fetchLeads(); } catch {}
  }, SYNC_INTERVALS.LEADS);
}

function _stopTimers() {
  Object.values(_timers).forEach(timer => clearInterval(timer));
  _timers = {};
}

// ---------------------------------------------------------------------------
// App state awareness
// ---------------------------------------------------------------------------

async function _setupAppStateListener() {
  if (!Capacitor.isNativePlatform()) {
    // Web fallback: use visibilitychange
    const handler = () => {
      const active = document.visibilityState === 'visible';
      _handleAppStateChange(active);
    };
    document.addEventListener('visibilitychange', handler);
    _appStateListener = () => document.removeEventListener('visibilitychange', handler);
    return;
  }

  try {
    const { App } = await import('@capacitor/app');
    const listener = await App.addListener('appStateChange', ({ isActive }) => {
      _handleAppStateChange(isActive);
    });
    _appStateListener = listener;
  } catch (error) {
    console.warn('[BackgroundSync] Could not register app state listener:', error.message);
  }
}

function _handleAppStateChange(isActive) {
  _appIsActive = isActive;

  if (isActive) {
    // Foreground: trigger immediate sync, resume periodic refresh
    const mode = _getSyncMode();
    if (mode) {
      _runSync(mode);
    }
    _startTimers();
  } else {
    // Background: pause periodic refresh, flush offline queue
    _stopTimers();
    _processOfflineQueue().catch(() => {});
  }

  _notifyListeners();
}

// ---------------------------------------------------------------------------
// Network awareness
// ---------------------------------------------------------------------------

async function _setupNetworkListener() {
  if (!Capacitor.isNativePlatform()) {
    // Web fallback
    const updateOnline = () => {
      _networkStatus = { connected: navigator.onLine, connectionType: 'unknown' };
      _notifyListeners();
    };
    window.addEventListener('online', updateOnline);
    window.addEventListener('offline', updateOnline);
    _networkStatus = { connected: navigator.onLine, connectionType: 'unknown' };
    _networkListener = () => {
      window.removeEventListener('online', updateOnline);
      window.removeEventListener('offline', updateOnline);
    };
    return;
  }

  try {
    const { Network } = await import('@capacitor/network');

    // Get initial status
    const status = await Network.getStatus();
    _networkStatus = { connected: status.connected, connectionType: status.connectionType };

    // Listen for changes
    const listener = await Network.addListener('networkStatusChange', (status) => {
      _networkStatus = { connected: status.connected, connectionType: status.connectionType };

      if (status.connected && _appIsActive) {
        // Reconnected while active — trigger sync
        const mode = _getSyncMode();
        if (mode) _runSync(mode);
      }

      _notifyListeners();
    });

    _networkListener = listener;
  } catch (error) {
    console.warn('[BackgroundSync] Could not register network listener:', error.message);
  }
}

// ---------------------------------------------------------------------------
// iOS Background Task (BGTaskScheduler)
// ---------------------------------------------------------------------------

async function _registerBackgroundTask() {
  if (!Capacitor.isNativePlatform()) return;

  try {
    // Capacitor does not have a first-party BGTaskScheduler plugin.
    // The background-refresh identifier is declared in Info.plist and
    // handled by the native Swift/ObjC bridge. When the OS grants
    // background execution time, the WebView receives a custom event
    // that we listen for here.
    //
    // If a community plugin like @nicklason/capacitor-background-task
    // is installed, we use it. Otherwise we register via the custom
    // event path that our native code dispatches.
    try {
      const { BackgroundTask } = await import('@nicklason/capacitor-background-task');
      BackgroundTask.beforeExit(async () => {
        const taskId = BackgroundTask.beginBackgroundTask();
        try {
          await _processOfflineQueue();
          await _fetchNotifications();
          await _fetchTasksToday();
        } catch (error) {
          console.warn('[BackgroundSync] Background task error:', error.message);
        }
        BackgroundTask.endBackgroundTask({ taskId });
      });
    } catch {
      // No background task plugin — listen for custom event from native bridge
      document.addEventListener('backgroundRefresh', async () => {
        try {
          await _processOfflineQueue();
          await _fetchNotifications();
          await _fetchTasksToday();
        } catch (error) {
          console.warn('[BackgroundSync] Background event handler error:', error.message);
        }
      });
    }
  } catch (error) {
    console.warn('[BackgroundSync] Background task registration skipped:', error.message);
  }
}

// ---------------------------------------------------------------------------
// Cache management
// ---------------------------------------------------------------------------

async function _refreshCaches() {
  try {
    _lastSyncTimeCache = await getItem(LAST_SYNC_KEY) || null;
    const queue = await _getOfflineQueue();
    _offlineQueueCountCache = queue.length;
  } catch {}
}

// Warm caches on module load
_refreshCaches();

// ---------------------------------------------------------------------------
// Listener management (pub/sub for UI components)
// ---------------------------------------------------------------------------

function _notifyListeners() {
  // Refresh caches (fire-and-forget) so next getSyncStatus() call is current
  _refreshCaches();
  const status = getSyncStatus();
  _listeners.forEach(fn => {
    try { fn(status); } catch {}
  });
}

/**
 * Subscribe to sync status changes.
 * Returns an unsubscribe function.
 *
 * @param {(status: SyncStatus) => void} callback
 * @returns {() => void}
 */
export function onSyncStatusChange(callback) {
  _listeners.push(callback);
  return () => {
    _listeners = _listeners.filter(fn => fn !== callback);
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Initialize the background sync service. Call once on app startup.
 * Safe to call multiple times — subsequent calls are no-ops.
 */
export async function initBackgroundSync() {
  if (_initialized) return;
  _initialized = true;

  // Set up listeners
  await _setupNetworkListener();
  await _setupAppStateListener();

  // Register iOS background task
  await _registerBackgroundTask();

  // Initial sync
  const mode = _getSyncMode();
  if (mode) {
    // Fire-and-forget — do not block startup
    _runSync(mode);
  }

  // Start periodic timers
  _startTimers();

  console.log('[BackgroundSync] Initialized');
}

/**
 * Manually trigger a sync cycle. Useful for pull-to-refresh.
 *
 * @param {'full'|'essential'} [forceMode] — Override network-based mode selection.
 */
export async function triggerSync(forceMode) {
  const mode = forceMode || _getSyncMode();
  if (!mode) {
    console.warn('[BackgroundSync] Cannot sync — device is offline');
    return;
  }
  await _runSync(mode);
}

/**
 * Get current sync status for UI display.
 *
 * @returns {SyncStatus}
 *
 * @typedef {Object} SyncStatus
 * @property {string|null} lastSyncTime  — ISO timestamp of last completed sync
 * @property {number}      pendingCount  — Number of queued offline mutations
 * @property {'idle'|'syncing'|'offline'} status
 * @property {boolean}     appIsActive
 * @property {string}      connectionType
 */
export function getSyncStatus() {
  // lastSyncTime is read synchronously from a module-level cache
  // and updated asynchronously after each sync. For the first call
  // before the async read completes, it may be null.
  return {
    lastSyncTime: _lastSyncTimeCache,
    pendingCount: _offlineQueueCountCache,
    status: !_networkStatus.connected ? 'offline'
          : _syncInProgress ? 'syncing'
          : 'idle',
    appIsActive: _appIsActive,
    connectionType: _networkStatus.connectionType,
  };
}

/**
 * Tear down the background sync service. Primarily useful for tests.
 */
export async function destroyBackgroundSync() {
  _stopTimers();

  if (_appStateListener) {
    if (typeof _appStateListener === 'function') {
      _appStateListener();
    } else if (_appStateListener.remove) {
      await _appStateListener.remove();
    }
    _appStateListener = null;
  }

  if (_networkListener) {
    if (typeof _networkListener === 'function') {
      _networkListener();
    } else if (_networkListener.remove) {
      await _networkListener.remove();
    }
    _networkListener = null;
  }

  _listeners = [];
  _initialized = false;
  _syncInProgress = false;
}
