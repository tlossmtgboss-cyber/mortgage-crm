import { useRef, useCallback, useEffect } from 'react';

/**
 * useSwipeGesture - Pure touch event handling for swipe gesture detection.
 *
 * No external gesture libraries. Handles touchstart, touchmove, touchend
 * with configurable threshold, direction detection, and velocity calculation.
 *
 * @param {Object} options
 * @param {number} [options.threshold=50] - Minimum distance in px to register a swipe
 * @param {number} [options.velocityThreshold=0.3] - Minimum velocity (px/ms) for flick detection
 * @param {function} [options.onSwipeLeft] - Callback for left swipe
 * @param {function} [options.onSwipeRight] - Callback for right swipe
 * @param {function} [options.onSwipeUp] - Callback for up swipe
 * @param {function} [options.onSwipeDown] - Callback for down swipe
 * @param {boolean} [options.preventScrollOnHorizontal=true] - Prevent vertical scroll during horizontal swipe
 * @returns {{ ref: React.RefObject, handlers: Object }} Ref to attach and touch event handlers
 */
const useSwipeGesture = ({
  threshold = 50,
  velocityThreshold = 0.3,
  onSwipeLeft,
  onSwipeRight,
  onSwipeUp,
  onSwipeDown,
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

  const handleTouchStart = useCallback((e) => {
    const touch = e.touches[0];
    if (!touch) return;

    touchState.current = {
      startX: touch.clientX,
      startY: touch.clientY,
      startTime: Date.now(),
      currentX: touch.clientX,
      currentY: touch.clientY,
      isTracking: true,
      direction: null,
    };
  }, []);

  const handleTouchMove = useCallback((e) => {
    const state = touchState.current;
    if (!state.isTracking) return;

    const touch = e.touches[0];
    if (!touch) return;

    state.currentX = touch.clientX;
    state.currentY = touch.clientY;

    const deltaX = Math.abs(state.currentX - state.startX);
    const deltaY = Math.abs(state.currentY - state.startY);

    // Determine direction on first significant movement (10px)
    if (!state.direction && (deltaX > 10 || deltaY > 10)) {
      state.direction = deltaX > deltaY ? 'horizontal' : 'vertical';
    }

    // Prevent vertical scroll when a horizontal swipe is detected
    if (preventScrollOnHorizontal && state.direction === 'horizontal') {
      e.preventDefault();
    }
  }, [preventScrollOnHorizontal]);

  const handleTouchEnd = useCallback(() => {
    const state = touchState.current;
    if (!state.isTracking) return;

    state.isTracking = false;

    const deltaX = state.currentX - state.startX;
    const deltaY = state.currentY - state.startY;
    const absDeltaX = Math.abs(deltaX);
    const absDeltaY = Math.abs(deltaY);
    const elapsed = Date.now() - state.startTime;

    // Calculate velocity in px/ms
    const velocityX = elapsed > 0 ? absDeltaX / elapsed : 0;
    const velocityY = elapsed > 0 ? absDeltaY / elapsed : 0;

    const gestureInfo = {
      deltaX,
      deltaY,
      velocityX,
      velocityY,
      elapsed,
      isFlick: false,
    };

    // Horizontal swipe detection
    if (absDeltaX > absDeltaY && (absDeltaX >= threshold || velocityX >= velocityThreshold)) {
      gestureInfo.isFlick = velocityX >= velocityThreshold && absDeltaX < threshold;

      if (deltaX < 0) {
        onSwipeLeft?.(gestureInfo);
      } else {
        onSwipeRight?.(gestureInfo);
      }
      return;
    }

    // Vertical swipe detection
    if (absDeltaY > absDeltaX && (absDeltaY >= threshold || velocityY >= velocityThreshold)) {
      gestureInfo.isFlick = velocityY >= velocityThreshold && absDeltaY < threshold;

      if (deltaY < 0) {
        onSwipeUp?.(gestureInfo);
      } else {
        onSwipeDown?.(gestureInfo);
      }
    }
  }, [threshold, velocityThreshold, onSwipeLeft, onSwipeRight, onSwipeUp, onSwipeDown]);

  // Attach listeners directly for passive: false support (needed for preventDefault)
  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    element.addEventListener('touchstart', handleTouchStart, { passive: true });
    element.addEventListener('touchmove', handleTouchMove, { passive: false });
    element.addEventListener('touchend', handleTouchEnd, { passive: true });

    return () => {
      element.removeEventListener('touchstart', handleTouchStart);
      element.removeEventListener('touchmove', handleTouchMove);
      element.removeEventListener('touchend', handleTouchEnd);
    };
  }, [handleTouchStart, handleTouchMove, handleTouchEnd]);

  // Also return handlers for manual attachment
  const handlers = {
    onTouchStart: handleTouchStart,
    onTouchMove: handleTouchMove,
    onTouchEnd: handleTouchEnd,
  };

  return { ref, handlers };
};

export default useSwipeGesture;
