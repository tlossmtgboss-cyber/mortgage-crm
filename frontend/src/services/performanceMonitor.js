/**
 * Performance Monitor Service — Real-user metrics for the Perennia AI mobile app.
 *
 * Tracks Core Web Vitals, custom mobile metrics, memory usage, and network
 * performance.  Metrics are buffered and sent in batches to the backend every
 * 60 seconds.
 *
 * Usage (singleton):
 *   import performanceMonitor from './performanceMonitor';
 *   performanceMonitor.init();
 *   performanceMonitor.trackMetric('custom_timing', 42, { screen: 'Pipeline' });
 */

// ---------------------------------------------------------------------------
// Performance budgets — thresholds beyond which we log a warning.
// ---------------------------------------------------------------------------

const BUDGETS = {
  LCP: 2500,            // ms — Largest Contentful Paint
  FID: 100,             // ms — First Input Delay
  CLS: 0.1,             // score — Cumulative Layout Shift
  TTI: 3000,            // ms — Time to Interactive
  TTFB: 800,            // ms — Time to First Byte
  FCP: 1800,            // ms — First Contentful Paint
  apiResponse: 3000,    // ms — slow API call threshold
  routeTransition: 500, // ms — route change -> render complete
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PERFORMANCE_ENDPOINT = '/api/v1/analytics/performance';
const FLUSH_INTERVAL_MS = 60_000;          // send batch every 60 s
const MEMORY_CHECK_INTERVAL_MS = 30_000;   // poll memory every 30 s
const MEMORY_WARNING_PERCENT = 70;
const SLOW_API_THRESHOLD_MS = BUDGETS.apiResponse;
const MAX_BUFFER_SIZE = 500;               // safety cap for the metric buffer

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function generateSessionId() {
  // Compact pseudo-UUID (no crypto dependency required)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function getDeviceInfo() {
  const info = {
    platform: 'web',
    userAgent: navigator.userAgent,
    screenSize: `${window.screen.width}x${window.screen.height}`,
    pixelRatio: window.devicePixelRatio || 1,
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    language: navigator.language,
  };

  // Device memory (Chrome-only, but useful on Android WebView)
  if (navigator.deviceMemory) {
    info.deviceMemory = navigator.deviceMemory; // GB
  }

  // Hardware concurrency
  if (navigator.hardwareConcurrency) {
    info.cpuCores = navigator.hardwareConcurrency;
  }

  // Connection info (Network Information API)
  const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  if (conn) {
    info.connectionType = conn.effectiveType || conn.type || 'unknown';
    if (conn.downlink != null) info.downlinkMbps = conn.downlink;
    if (conn.rtt != null) info.rttMs = conn.rtt;
    if (conn.saveData != null) info.saveData = conn.saveData;
  }

  // Rough platform detection (Capacitor sets this on the user agent)
  if (/PerenniaAI\/ios/i.test(navigator.userAgent) || /iPhone|iPad/i.test(navigator.userAgent)) {
    info.platform = 'ios';
  } else if (/PerenniaAI\/android/i.test(navigator.userAgent) || /Android/i.test(navigator.userAgent)) {
    info.platform = 'android';
  }

  return info;
}

// ---------------------------------------------------------------------------
// PerformanceMonitor class
// ---------------------------------------------------------------------------

class PerformanceMonitor {
  constructor() {
    this._initialized = false;
    this._sessionId = generateSessionId();
    this._device = null;
    this._buffer = [];             // buffered metrics awaiting flush
    this._observers = [];          // PerformanceObserver handles
    this._flushTimer = null;
    this._memoryTimer = null;
    this._appLaunchStart = null;   // timestamp: splash shown
    this._routeChangeStart = null; // timestamp: route navigation started
    this._memorySnapshots = [];    // recent memory readings for trend analysis
    this._endpointTimings = {};    // { endpoint: [durations] }
    this._failedRequests = [];     // recent failed request records
  }

  // -----------------------------------------------------------------------
  // Lifecycle
  // -----------------------------------------------------------------------

  /**
   * Initialise the monitor.  Safe to call multiple times — subsequent calls
   * are no-ops.
   */
  init() {
    if (this._initialized) return;
    this._initialized = true;
    this._device = getDeviceInfo();
    this._appLaunchStart = performance.now();

    if (process.env.NODE_ENV === 'development') {
      console.log('[PerfMon] Initialized', { session: this._sessionId });
    }

    this._observeCoreWebVitals();
    this._observeResourceTiming();
    this._startMemoryMonitoring();
    this._startFlushTimer();
  }

  /**
   * Tear down observers and timers (e.g. on app background / unmount).
   */
  destroy() {
    this._observers.forEach((obs) => {
      try { obs.disconnect(); } catch { /* ignore */ }
    });
    this._observers = [];
    if (this._flushTimer) clearInterval(this._flushTimer);
    if (this._memoryTimer) clearInterval(this._memoryTimer);
    // Best-effort final flush
    this._flush();
    this._initialized = false;
  }

  // -----------------------------------------------------------------------
  // Public API — generic metric tracking
  // -----------------------------------------------------------------------

  /**
   * Record a single metric.
   *
   * @param {string}  name      Metric name (e.g. 'LCP', 'screen_transition')
   * @param {number}  value     Numeric value
   * @param {object}  metadata  Optional key/value pairs
   */
  trackMetric(name, value, metadata = {}) {
    if (!this._initialized) return;

    const entry = {
      name,
      value,
      timestamp: new Date().toISOString(),
      url: window.location.pathname,
      ...metadata,
    };

    // Budget check
    const budget = BUDGETS[name];
    if (budget != null && value > budget) {
      entry.budgetExceeded = true;
      entry.budget = budget;
      if (process.env.NODE_ENV === 'development') {
        console.warn(
          `[PerfMon] Budget exceeded: ${name} = ${value} (budget: ${budget})`,
        );
      }
    }

    this._push(entry);
  }

  // -----------------------------------------------------------------------
  // Public API — mobile-specific metrics
  // -----------------------------------------------------------------------

  /**
   * Call when the first interactive screen is painted (e.g. after splash).
   */
  markAppInteractive() {
    if (this._appLaunchStart == null) return;
    const launchTime = performance.now() - this._appLaunchStart;
    this.trackMetric('app_launch_time', Math.round(launchTime), {
      category: 'mobile',
    });
    this._appLaunchStart = null; // one-shot
  }

  /**
   * Call when the first API response is received after launch.
   */
  markFirstApiResponse() {
    if (this._appLaunchStart == null && !this._firstApiMarked) return;
    this._firstApiMarked = true;
    const elapsed = performance.now(); // from navigation start
    this.trackMetric('time_to_first_api', Math.round(elapsed), {
      category: 'mobile',
    });
  }

  /**
   * Call at the start of a route change.
   */
  startRouteTransition(routeName) {
    this._routeChangeStart = performance.now();
    this._pendingRoute = routeName || 'unknown';
  }

  /**
   * Call once the target route's first meaningful paint is done.
   */
  endRouteTransition() {
    if (this._routeChangeStart == null) return;
    const elapsed = performance.now() - this._routeChangeStart;
    this.trackMetric('route_transition', Math.round(elapsed), {
      category: 'navigation',
      route: this._pendingRoute,
    });
    this._routeChangeStart = null;
    this._pendingRoute = null;
  }

  /**
   * Track an individual API request timing.
   *
   * @param {string} endpoint  e.g. '/api/v1/leads'
   * @param {number} durationMs
   * @param {object} opts      { method, status, failed }
   */
  trackApiCall(endpoint, durationMs, opts = {}) {
    const { method = 'GET', status = 200, failed = false } = opts;

    // Per-endpoint running stats
    if (!this._endpointTimings[endpoint]) {
      this._endpointTimings[endpoint] = [];
    }
    // Keep a rolling window of 100 recent timings per endpoint
    const arr = this._endpointTimings[endpoint];
    arr.push(durationMs);
    if (arr.length > 100) arr.shift();

    if (failed) {
      this._failedRequests.push({
        endpoint,
        method,
        status,
        timestamp: new Date().toISOString(),
      });
      // Cap stored failures
      if (this._failedRequests.length > 50) this._failedRequests.shift();
    }

    if (durationMs > SLOW_API_THRESHOLD_MS) {
      this.trackMetric('slow_api_call', durationMs, {
        category: 'network',
        endpoint,
        method,
        status,
      });
    }
  }

  /**
   * Track a scroll frame rate sample.  Callers should measure via
   * requestAnimationFrame in a scroll handler, passing the fps value.
   *
   * @param {number} fps  Measured frames per second during scroll
   * @param {string} screen  The screen/component where jank was measured
   */
  trackScrollFps(fps, screen) {
    if (fps < 30) {
      this.trackMetric('scroll_jank', fps, {
        category: 'rendering',
        screen,
        severity: fps < 15 ? 'critical' : 'warning',
      });
    }
  }

  // -----------------------------------------------------------------------
  // Public API — queries
  // -----------------------------------------------------------------------

  /**
   * Get current memory usage snapshot (Chrome/Chromium-based only).
   */
  getMemoryUsage() {
    if (!performance.memory) return null;
    const { usedJSHeapSize, totalJSHeapSize, jsHeapSizeLimit } = performance.memory;
    return {
      usedJSHeapSize,
      totalJSHeapSize,
      jsHeapSizeLimit,
      usagePercent: jsHeapSizeLimit > 0
        ? Math.round((usedJSHeapSize / jsHeapSizeLimit) * 10000) / 100
        : 0,
      usedMB: Math.round(usedJSHeapSize / 1048576 * 10) / 10,
      totalMB: Math.round(totalJSHeapSize / 1048576 * 10) / 10,
      limitMB: Math.round(jsHeapSizeLimit / 1048576 * 10) / 10,
    };
  }

  /**
   * Return the average API response time for a given endpoint (or all).
   */
  getAverageResponseTime(endpoint) {
    if (endpoint) {
      const arr = this._endpointTimings[endpoint];
      if (!arr || arr.length === 0) return null;
      return Math.round(arr.reduce((a, b) => a + b, 0) / arr.length);
    }
    // All endpoints combined
    let total = 0;
    let count = 0;
    for (const arr of Object.values(this._endpointTimings)) {
      for (const v of arr) { total += v; count++; }
    }
    return count > 0 ? Math.round(total / count) : null;
  }

  /**
   * Return recent failed requests.
   */
  getFailedRequests() {
    return [...this._failedRequests];
  }

  /**
   * Return memory trend over the session (array of { timestamp, usedMB }).
   */
  getMemoryTrend() {
    return [...this._memorySnapshots];
  }

  /**
   * Return the session id.
   */
  getSessionId() {
    return this._sessionId;
  }

  // -----------------------------------------------------------------------
  // Core Web Vitals — via PerformanceObserver
  // -----------------------------------------------------------------------

  _observeCoreWebVitals() {
    if (typeof PerformanceObserver === 'undefined') return;

    // LCP
    this._observe('largest-contentful-paint', (entries) => {
      const last = entries[entries.length - 1];
      if (last) {
        this.trackMetric('LCP', Math.round(last.startTime), { category: 'web_vital' });
      }
    });

    // FID
    this._observe('first-input', (entries) => {
      const first = entries[0];
      if (first) {
        this.trackMetric('FID', Math.round(first.processingStart - first.startTime), {
          category: 'web_vital',
        });
      }
    });

    // CLS
    let clsValue = 0;
    this._observe('layout-shift', (entries) => {
      for (const entry of entries) {
        if (!entry.hadRecentInput) {
          clsValue += entry.value;
        }
      }
      this.trackMetric('CLS', Math.round(clsValue * 10000) / 10000, {
        category: 'web_vital',
      });
    });

    // FCP
    this._observe('paint', (entries) => {
      for (const entry of entries) {
        if (entry.name === 'first-contentful-paint') {
          this.trackMetric('FCP', Math.round(entry.startTime), { category: 'web_vital' });
        }
      }
    });

    // TTFB from navigation timing
    this._observe('navigation', (entries) => {
      const nav = entries[0];
      if (nav) {
        this.trackMetric('TTFB', Math.round(nav.responseStart), { category: 'web_vital' });
      }
    });
  }

  // -----------------------------------------------------------------------
  // Resource / network timing
  // -----------------------------------------------------------------------

  _observeResourceTiming() {
    if (typeof PerformanceObserver === 'undefined') return;

    this._observe('resource', (entries) => {
      for (const entry of entries) {
        // Only track API calls (fetch/xhr to our backend)
        if (
          entry.initiatorType === 'fetch' ||
          entry.initiatorType === 'xmlhttprequest'
        ) {
          const url = entry.name;
          // Only our own API
          if (!url.includes('/api/')) continue;

          const duration = Math.round(entry.responseEnd - entry.startTime);
          // Extract pathname from URL
          let endpoint;
          try {
            endpoint = new URL(url).pathname;
          } catch {
            endpoint = url;
          }

          this.trackApiCall(endpoint, duration, {
            method: 'GET', // resource timing doesn't expose method
            status: entry.responseStatus || 200,
            failed: entry.responseStatus >= 400,
          });
        }
      }
    });
  }

  // -----------------------------------------------------------------------
  // Memory monitoring
  // -----------------------------------------------------------------------

  _startMemoryMonitoring() {
    if (!performance.memory) return;

    this._memoryTimer = setInterval(() => {
      const usage = this.getMemoryUsage();
      if (!usage) return;

      // Record snapshot for trend
      this._memorySnapshots.push({
        timestamp: new Date().toISOString(),
        usedMB: usage.usedMB,
        totalMB: usage.totalMB,
        usagePercent: usage.usagePercent,
      });
      // Keep last 60 snapshots (~30 min at 30 s interval)
      if (this._memorySnapshots.length > 60) this._memorySnapshots.shift();

      // Warn if above threshold
      if (usage.usagePercent > MEMORY_WARNING_PERCENT) {
        this.trackMetric('memory_warning', usage.usagePercent, {
          category: 'memory',
          usedMB: usage.usedMB,
          limitMB: usage.limitMB,
        });

        if (process.env.NODE_ENV === 'development') {
          console.warn(
            `[PerfMon] High memory usage: ${usage.usagePercent}% ` +
            `(${usage.usedMB} MB / ${usage.limitMB} MB)`,
          );
        }
      }
    }, MEMORY_CHECK_INTERVAL_MS);
  }

  // -----------------------------------------------------------------------
  // Batch flush
  // -----------------------------------------------------------------------

  _startFlushTimer() {
    this._flushTimer = setInterval(() => this._flush(), FLUSH_INTERVAL_MS);

    // Also flush on page hide (mobile: app backgrounded)
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
          this._flush();
        }
      });
    }
  }

  _flush() {
    if (this._buffer.length === 0) return;

    const payload = {
      sessionId: this._sessionId,
      device: this._device,
      metrics: this._buffer.splice(0), // drain buffer
      timestamp: new Date().toISOString(),
    };

    if (process.env.NODE_ENV === 'development') {
      console.log('[PerfMon] Flushing', payload.metrics.length, 'metrics');
    }

    const token = localStorage.getItem('token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    // Use sendBeacon for reliability on page hide, fall back to fetch.
    const body = JSON.stringify(payload);

    if (
      document.visibilityState === 'hidden' &&
      typeof navigator.sendBeacon === 'function'
    ) {
      try {
        const sent = navigator.sendBeacon(PERFORMANCE_ENDPOINT, body);
        if (!sent) {
          this._fetchSend(headers, body);
        }
      } catch {
        this._fetchSend(headers, body);
      }
    } else {
      this._fetchSend(headers, body);
    }
  }

  _fetchSend(headers, body) {
    fetch(PERFORMANCE_ENDPOINT, {
      method: 'POST',
      headers,
      body,
      keepalive: true, // allow in-flight after navigation
    }).catch(() => {
      // Silently swallow — never let monitoring break the app.
    });
  }

  // -----------------------------------------------------------------------
  // Internal helpers
  // -----------------------------------------------------------------------

  _push(entry) {
    if (this._buffer.length >= MAX_BUFFER_SIZE) {
      // Drop oldest to prevent unbounded growth
      this._buffer.shift();
    }
    this._buffer.push(entry);
  }

  /**
   * Safely create a PerformanceObserver.  If the entry type is not
   * supported, the call is silently skipped.
   */
  _observe(entryType, callback) {
    try {
      // Feature-detect supported entry types
      if (
        typeof PerformanceObserver.supportedEntryTypes !== 'undefined' &&
        !PerformanceObserver.supportedEntryTypes.includes(entryType)
      ) {
        return;
      }

      const observer = new PerformanceObserver((list) => {
        try {
          callback(list.getEntries());
        } catch (err) {
          if (process.env.NODE_ENV === 'development') {
            console.warn(`[PerfMon] Observer callback error (${entryType}):`, err);
          }
        }
      });

      observer.observe({ type: entryType, buffered: true });
      this._observers.push(observer);
    } catch {
      // Entry type not supported in this browser — silently skip.
    }
  }
}

// ---------------------------------------------------------------------------
// Singleton export
// ---------------------------------------------------------------------------

const performanceMonitor = new PerformanceMonitor();

export { performanceMonitor, BUDGETS };
export default performanceMonitor;
