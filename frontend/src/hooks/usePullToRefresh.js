import { useState, useRef, useCallback, useEffect } from 'react';
import { haptics } from '../services/nativeServices';

/**
 * usePullToRefresh - Touch-driven pull-to-refresh gesture for mobile.
 *
 * Tracks touch start/move/end on a scrollable container. Only activates
 * when the container is scrolled to the top. Fires an async onRefresh
 * callback when the user pulls past a configurable threshold and releases.
 *
 * Includes haptic feedback at the threshold crossing and respects the
 * prefers-reduced-motion media query.
 *
 * @param {Object} options
 * @param {function} options.onRefresh  - Async function to call on refresh trigger
 * @param {number}   [options.threshold=80]  - Pull distance (px) before triggering
 * @param {number}   [options.maxPull=120]   - Maximum pull distance (px)
 * @param {boolean}  [options.disabled=false] - Disable the gesture entirely
 * @param {React.RefObject} [options.containerRef] - Ref to the scroll container (defaults to an internal ref)
 *
 * @returns {{
 *   isRefreshing: boolean,
 *   pullProgress: number,
 *   pullDistance: number,
 *   isDragging: boolean,
 *   containerRef: React.RefObject
 * }}
 */
const usePullToRefresh = ({
  onRefresh,
  threshold = 80,
  maxPull = 120,
  disabled = false,
  containerRef: externalRef,
} = {}) => {
  const internalRef = useRef(null);
  const containerRef = externalRef || internalRef;

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const [isDragging, setIsDragging] = useState(false);

  // Mutable tracking state (no re-renders during touch movement)
  const touchState = useRef({
    startY: 0,
    currentY: 0,
    isTracking: false,
    didCrossThreshold: false,
  });

  // Check prefers-reduced-motion once on mount
  const prefersReducedMotion = useRef(false);
  useEffect(() => {
    if (typeof window !== 'undefined' && window.matchMedia) {
      prefersReducedMotion.current = window.matchMedia(
        '(prefers-reduced-motion: reduce)'
      ).matches;
    }
  }, []);

  const handleTouchStart = useCallback(
    (e) => {
      if (disabled || isRefreshing) return;

      const container = containerRef.current;
      if (!container) return;

      // Only activate when the scroll container is at the very top
      if (container.scrollTop > 0) return;

      const touch = e.touches[0];
      if (!touch) return;

      touchState.current = {
        startY: touch.clientY,
        currentY: touch.clientY,
        isTracking: true,
        didCrossThreshold: false,
      };
      setIsDragging(true);
    },
    [disabled, isRefreshing, containerRef]
  );

  const handleTouchMove = useCallback(
    (e) => {
      const state = touchState.current;
      if (!state.isTracking || disabled || isRefreshing) return;

      const touch = e.touches[0];
      if (!touch) return;

      const container = containerRef.current;
      if (!container) return;

      // If the user scrolled down during the gesture, cancel tracking
      if (container.scrollTop > 0) {
        state.isTracking = false;
        setIsDragging(false);
        setPullDistance(0);
        return;
      }

      state.currentY = touch.clientY;
      const rawDelta = state.currentY - state.startY;

      // Only respond to downward pulls
      if (rawDelta <= 0) {
        setPullDistance(0);
        return;
      }

      // Prevent native scroll while pulling
      e.preventDefault();

      // Apply rubber-band resistance: diminishing returns past threshold
      let distance;
      if (rawDelta <= threshold) {
        distance = rawDelta;
      } else {
        const overPull = rawDelta - threshold;
        // Logarithmic damping for rubber-band feel
        distance = threshold + overPull * 0.4;
      }

      // Clamp to maxPull
      distance = Math.min(distance, maxPull);

      // Haptic feedback when crossing the threshold (once per gesture)
      if (distance >= threshold && !state.didCrossThreshold) {
        state.didCrossThreshold = true;
        if (!prefersReducedMotion.current) {
          haptics.medium();
        }
      } else if (distance < threshold && state.didCrossThreshold) {
        // Reset if user pulls back above threshold
        state.didCrossThreshold = false;
      }

      setPullDistance(distance);
    },
    [disabled, isRefreshing, containerRef, threshold, maxPull]
  );

  const handleTouchEnd = useCallback(async () => {
    const state = touchState.current;
    if (!state.isTracking) return;

    state.isTracking = false;
    setIsDragging(false);

    const wasOverThreshold = state.didCrossThreshold;
    state.didCrossThreshold = false;

    if (wasOverThreshold && onRefresh && !isRefreshing) {
      setIsRefreshing(true);
      // Snap to a settled refresh position (slightly past threshold)
      setPullDistance(threshold * 0.75);

      try {
        await onRefresh();
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('Pull-to-refresh callback failed:', err);
      } finally {
        setIsRefreshing(false);
        setPullDistance(0);
      }
    } else {
      // Didn't cross threshold -- animate back to zero
      setPullDistance(0);
    }
  }, [onRefresh, isRefreshing, threshold]);

  // Attach touch listeners with passive: false so we can preventDefault on touchmove
  useEffect(() => {
    const container = containerRef.current;
    if (!container || disabled) return;

    container.addEventListener('touchstart', handleTouchStart, { passive: true });
    container.addEventListener('touchmove', handleTouchMove, { passive: false });
    container.addEventListener('touchend', handleTouchEnd, { passive: true });

    return () => {
      container.removeEventListener('touchstart', handleTouchStart);
      container.removeEventListener('touchmove', handleTouchMove);
      container.removeEventListener('touchend', handleTouchEnd);
    };
  }, [containerRef, disabled, handleTouchStart, handleTouchMove, handleTouchEnd]);

  // pullProgress: 0 to 1, clamped
  const pullProgress = Math.min(pullDistance / threshold, 1);

  return {
    isRefreshing,
    pullProgress,
    pullDistance,
    isDragging,
    containerRef,
  };
};

export default usePullToRefresh;
