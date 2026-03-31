/**
 * useLongPress — Custom hook for detecting long-press gestures on mobile.
 *
 * Triggers after holding for a configurable duration (default 500ms).
 * Cancels if the finger moves more than 10px (scroll detection).
 * Fires haptic feedback (medium impact) on activation.
 * Prevents the browser's default context menu.
 *
 * Usage:
 *   const handlers = useLongPress({
 *     onLongPress: (event) => { ... },
 *     duration: 500,
 *     onStart: () => {},
 *     onCancel: () => {},
 *   });
 *   // Spread handlers onto the target element:
 *   <div {...handlers}>...</div>
 */
import { useCallback, useRef } from 'react';
import { haptics } from '../services/nativeServices';

const MOVE_THRESHOLD = 10; // px — cancel if finger drifts further than this

export function useLongPress({
  onLongPress,
  duration = 500,
  onStart,
  onCancel,
} = {}) {
  const timerRef = useRef(null);
  const startPos = useRef({ x: 0, y: 0 });
  const activeRef = useRef(false);
  const firedRef = useRef(false);

  const clear = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (activeRef.current && !firedRef.current) {
      onCancel?.();
    }
    activeRef.current = false;
    firedRef.current = false;
  }, [onCancel]);

  const onTouchStart = useCallback(
    (event) => {
      // Record starting position for scroll detection
      const touch = event.touches[0];
      startPos.current = { x: touch.clientX, y: touch.clientY };
      activeRef.current = true;
      firedRef.current = false;

      onStart?.();

      timerRef.current = setTimeout(() => {
        firedRef.current = true;
        // Haptic feedback on activation
        haptics.medium();
        onLongPress?.(event);
      }, duration);
    },
    [onLongPress, duration, onStart],
  );

  const onTouchMove = useCallback(
    (event) => {
      if (!activeRef.current) return;

      const touch = event.touches[0];
      const dx = Math.abs(touch.clientX - startPos.current.x);
      const dy = Math.abs(touch.clientY - startPos.current.y);

      // If finger moved beyond threshold, it is a scroll — cancel the long press
      if (dx > MOVE_THRESHOLD || dy > MOVE_THRESHOLD) {
        clear();
      }
    },
    [clear],
  );

  const onTouchEnd = useCallback(() => {
    clear();
  }, [clear]);

  const onContextMenu = useCallback((event) => {
    // Prevent the native context menu on all platforms
    event.preventDefault();
    event.stopPropagation();
  }, []);

  return {
    onTouchStart,
    onTouchEnd,
    onTouchMove,
    onContextMenu,
  };
}

export default useLongPress;
