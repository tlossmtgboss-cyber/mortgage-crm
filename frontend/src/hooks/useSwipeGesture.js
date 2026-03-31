import { useRef, useCallback, useEffect, useState } from 'react';

/**
 * useSwipeGesture - Pure touch event handling for swipe gesture detection.
 *
 * No external gesture libraries. Handles touchstart, touchmove, touchend
 * with configurable threshold, direction detection, and velocity calculation.
 *
 * Features:
 * - Ignores touches starting in iOS edge gesture zones (first/last 20px)
 * - Distinguishes horizontal vs vertical swipes with direction lock
 * - Calculates velocity for flick detection
 * - Exposes live swipeState for tracking drag progress
 * - Prevents scroll jank during horizontal swipes via passive:false touchmove
 *
 * @param {Object} options
 * @param {number} [options.threshold=50] - Minimum distance in px to register a swipe
 * @param {number} [options.velocityThreshold=0.3] - Minimum velocity (px/ms) for flick detection
 * @param {function} [options.onSwipeLeft] - Callback for left swipe
 * @param {function} [options.onSwipeRight] - Callback for right swipe
 * @param {function} [options.onSwipeUp] - Callback for up swipe
 * @param {function} [options.onSwipeDown] - Callback for down swipe
 * @param {boolean} [options.preventScrollOnHorizontal=true] - Prevent vertical scroll during horizontal swipe
 * @param {function} [options.onSwipeMove] - Called on every touchmove with current delta (for live tracking)
 * @returns {{ ref: React.RefObject, handlers: Object, swipeState: Object }}
 */

const EDGE_IGNORE_PX = 20;
const DIRECTION_LOCK_PX = 10;

const useSwipeGesture = ({
  threshold = 50,
  velocityThreshold = 0.3,
  onSwipeLeft,
  onSwipeRight,
  onSwipeUp,
  onSwipeDown,
  onSwipeMove,
  preventScrollOnHorizontal = true,
} = {}) => {
  const ref = useRef(null);
  const touchState = useRef({
    startX: 0,
    startY: 0,
    startTime: 0,
    currentX: 0,
    currentY: 0,
    isTracking: false,
    direction: null, // 'horizontal' | 'vertical' | null
  });

  const [swipeState, setSwipeState] = useState({
    deltaX: 0,
    deltaY: 0,
    direction: null,
    isSwiping: false,
    velocity: 0,
  });

  const handleTouchStart = useCallback((e) => {
    const touch = e.touches[0];
    if (!touch) return;

    // Ignore touches starting in iOS back/forward gesture edge zones
    const viewportWidth = window.innerWidth;
    if (touch.clientX < EDGE_IGNORE_PX || touch.clientX > viewportWidth - EDGE_IGNORE_PX) {
      touchState.current.isTracking = false;
      return;
    }

    touchState.current = {
      startX: touch.clientX,
      startY: touch.clientY,
      startTime: Date.now(),
      currentX: touch.clientX,
      currentY: touch.clientY,
      isTracking: true,
      direction: null,
    };

    setSwipeState({
      deltaX: 0,
      deltaY: 0,
      direction: null,
      isSwiping: true,
      velocity: 0,
    });
  }, []);

  const handleTouchMove = useCallback((e) => {
    const state = touchState.current;
    if (!state.isTracking) return;

    const touch = e.touches[0];
    if (!touch) return;

    state.currentX = touch.clientX;
    state.currentY = touch.clientY;

    const deltaX = state.currentX - state.startX;
    const deltaY = state.currentY - state.startY;
    const absDeltaX = Math.abs(deltaX);
    const absDeltaY = Math.abs(deltaY);

    // Lock direction on first significant movement
    if (!state.direction && (absDeltaX > DIRECTION_LOCK_PX || absDeltaY > DIRECTION_LOCK_PX)) {
      state.direction = absDeltaX > absDeltaY ? 'horizontal' : 'vertical';
    }

    // Prevent vertical scroll when a horizontal swipe is detected
    if (preventScrollOnHorizontal && state.direction === 'horizontal') {
      e.preventDefault();
    }

    // Update live swipe state for consumers tracking drag progress
    const elapsed = Math.max(Date.now() - state.startTime, 1);
    const velocity = Math.max(absDeltaX, absDeltaY) / elapsed;

    setSwipeState({
      deltaX,
      deltaY,
      direction: state.direction,
      isSwiping: true,
      velocity,
    });

    if (onSwipeMove) {
      onSwipeMove({ deltaX, deltaY, direction: state.direction, velocity });
    }
  }, [preventScrollOnHorizontal, onSwipeMove]);

  const handleTouchEnd = useCallback(() => {
    const state = touchState.current;
    if (!state.isTracking) return;

    state.isTracking = false;

    const deltaX = state.currentX - state.startX;
    const deltaY = state.currentY - state.startY;
    const absDeltaX = Math.abs(deltaX);
    const absDeltaY = Math.abs(deltaY);
    const elapsed = Math.max(Date.now() - state.startTime, 1);

    // Calculate velocity in px/ms
    const velocityX = absDeltaX / elapsed;
    const velocityY = absDeltaY / elapsed;

    const gestureInfo = {
      deltaX,
      deltaY,
      velocityX,
      velocityY,
      velocity: Math.max(velocityX, velocityY),
      elapsed,
      direction: state.direction,
      isFlick: false,
    };

    // Determine if threshold is met (distance OR velocity for fast flicks)
    const meetsThreshold = (dist, vel) =>
      dist >= threshold || (vel >= velocityThreshold && dist >= threshold * 0.4);

    // Horizontal swipe detection
    if (state.direction === 'horizontal' && meetsThreshold(absDeltaX, velocityX)) {
      gestureInfo.isFlick = velocityX >= velocityThreshold && absDeltaX < threshold;

      if (deltaX < 0) {
        onSwipeLeft?.(gestureInfo);
      } else {
        onSwipeRight?.(gestureInfo);
      }
    }

    // Vertical swipe detection
    if (state.direction === 'vertical' && meetsThreshold(absDeltaY, velocityY)) {
      gestureInfo.isFlick = velocityY >= velocityThreshold && absDeltaY < threshold;

      if (deltaY < 0) {
        onSwipeUp?.(gestureInfo);
      } else {
        onSwipeDown?.(gestureInfo);
      }
    }

    // Reset swipe state
    setSwipeState({
      deltaX: 0,
      deltaY: 0,
      direction: null,
      isSwiping: false,
      velocity: 0,
    });
  }, [threshold, velocityThreshold, onSwipeLeft, onSwipeRight, onSwipeUp, onSwipeDown]);

  const handleTouchCancel = useCallback(() => {
    touchState.current.isTracking = false;
    touchState.current.direction = null;
    setSwipeState({
      deltaX: 0,
      deltaY: 0,
      direction: null,
      isSwiping: false,
      velocity: 0,
    });
  }, []);

  // Attach listeners directly for passive:false support (needed for preventDefault)
  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    element.addEventListener('touchstart', handleTouchStart, { passive: true });
    element.addEventListener('touchmove', handleTouchMove, { passive: false });
    element.addEventListener('touchend', handleTouchEnd, { passive: true });
    element.addEventListener('touchcancel', handleTouchCancel, { passive: true });

    return () => {
      element.removeEventListener('touchstart', handleTouchStart);
      element.removeEventListener('touchmove', handleTouchMove);
      element.removeEventListener('touchend', handleTouchEnd);
      element.removeEventListener('touchcancel', handleTouchCancel);
    };
  }, [handleTouchStart, handleTouchMove, handleTouchEnd, handleTouchCancel]);

  // Also return handlers for manual spread-on-element attachment
  const handlers = {
    onTouchStart: handleTouchStart,
    onTouchMove: handleTouchMove,
    onTouchEnd: handleTouchEnd,
    onTouchCancel: handleTouchCancel,
  };

  return { ref, handlers, swipeState };
};

export default useSwipeGesture;
