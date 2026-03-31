/**
 * usePerformanceTracker — Track component-level performance metrics.
 *
 * Measures mount time, render count, and flags slow renders (> 16 ms,
 * i.e. longer than one 60 fps frame).  Integrates with the global
 * performanceMonitor singleton for batch reporting.
 *
 * Usage:
 *   import { usePerformanceTracker } from '../hooks/usePerformanceTracker';
 *
 *   function MobilePipelineView() {
 *     usePerformanceTracker('MobilePipelineView');
 *     // ... component body
 *   }
 */
import { useRef, useEffect } from 'react';
import performanceMonitor from '../services/performanceMonitor';

const SLOW_RENDER_THRESHOLD_MS = 16; // one frame at 60 fps

/**
 * @param {string} componentName  Human-readable name for the component.
 * @param {object} [options]
 * @param {boolean} [options.trackRenders=true]  Track every re-render.
 * @param {boolean} [options.trackMount=true]    Track mount/unmount timing.
 * @param {number}  [options.slowThreshold=16]   ms threshold for "slow render".
 */
export function usePerformanceTracker(componentName, options = {}) {
  const {
    trackRenders = true,
    trackMount = true,
    slowThreshold = SLOW_RENDER_THRESHOLD_MS,
  } = options;

  // Stable refs that persist across renders
  const renderCountRef = useRef(0);
  const renderStartRef = useRef(null);
  const mountTimeRef = useRef(null);
  const componentNameRef = useRef(componentName);

  // Keep component name up to date without causing effect re-runs
  componentNameRef.current = componentName;

  // -- Render tracking -------------------------------------------------------
  // This runs during the render phase (synchronously), capturing the start
  // timestamp before React commits.  The corresponding useEffect below
  // fires after paint, giving us the commit duration.

  if (trackRenders) {
    renderCountRef.current += 1;
    renderStartRef.current = performance.now();
  }

  useEffect(() => {
    if (!trackRenders || renderStartRef.current == null) return;

    const renderDuration = performance.now() - renderStartRef.current;

    if (renderDuration > slowThreshold) {
      performanceMonitor.trackMetric('slow_render', Math.round(renderDuration * 100) / 100, {
        category: 'rendering',
        component: componentNameRef.current,
        renderCount: renderCountRef.current,
      });

      if (process.env.NODE_ENV === 'development') {
        console.warn(
          `[PerfTracker] Slow render: ${componentNameRef.current} ` +
          `took ${renderDuration.toFixed(1)} ms (render #${renderCountRef.current})`,
        );
      }
    }
  });

  // -- Mount / unmount tracking -----------------------------------------------
  useEffect(() => {
    if (!trackMount) return;

    mountTimeRef.current = performance.now();

    performanceMonitor.trackMetric('component_mount', 0, {
      category: 'lifecycle',
      component: componentNameRef.current,
    });

    return () => {
      const lifespanMs = mountTimeRef.current != null
        ? Math.round(performance.now() - mountTimeRef.current)
        : 0;

      performanceMonitor.trackMetric('component_unmount', lifespanMs, {
        category: 'lifecycle',
        component: componentNameRef.current,
        totalRenders: renderCountRef.current,
      });

      if (process.env.NODE_ENV === 'development') {
        console.log(
          `[PerfTracker] ${componentNameRef.current} unmounted — ` +
          `lifespan ${lifespanMs} ms, ${renderCountRef.current} renders`,
        );
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // mount-only
}

export default usePerformanceTracker;
