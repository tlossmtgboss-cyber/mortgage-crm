import { useEffect, useRef, useCallback } from 'react';

/**
 * Hook to fix layout calculation issues that occur when content loads asynchronously.
 * Forces browser to recalculate layout after content arrives.
 *
 * @param {Array} dependencies - Array of values that, when changed, trigger recalculation
 * @returns {{ containerRef: React.RefObject, triggerRecalculation: Function }}
 */
export const useLayoutFix = (dependencies = []) => {
  const containerRef = useRef(null);
  const resizeObserverRef = useRef(null);

  const recalculateLayout = useCallback(() => {
    if (containerRef.current) {
      // Reset min-height to auto to get true content height
      containerRef.current.style.minHeight = 'auto';
      const height = containerRef.current.scrollHeight;

      if (height > 0) {
        containerRef.current.style.minHeight = `${height}px`;
      }

      // Force browser repaint
      window.dispatchEvent(new Event('resize'));

      // Ensure body can scroll if content exceeds viewport
      requestAnimationFrame(() => {
        if (containerRef.current) {
          const rect = containerRef.current.getBoundingClientRect();
          if (rect.bottom > window.innerHeight) {
            document.body.style.overflow = 'auto';
          }
        }
      });
    }
  }, []);

  useEffect(() => {
    // Run recalculation at multiple intervals to catch async content
    const timer = setTimeout(recalculateLayout, 100);
    const timer2 = setTimeout(recalculateLayout, 500);

    // Set up ResizeObserver to detect content size changes
    if (containerRef.current && 'ResizeObserver' in window) {
      resizeObserverRef.current = new ResizeObserver(() => {
        recalculateLayout();
      });
      resizeObserverRef.current.observe(containerRef.current);
    }

    // Listen for window resize
    window.addEventListener('resize', recalculateLayout);

    return () => {
      clearTimeout(timer);
      clearTimeout(timer2);
      window.removeEventListener('resize', recalculateLayout);
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);

  const triggerRecalculation = useCallback(() => {
    setTimeout(recalculateLayout, 0);
    setTimeout(recalculateLayout, 100);
  }, [recalculateLayout]);

  return { containerRef, triggerRecalculation };
};

/**
 * Simplified hook for list-based pages that load data asynchronously.
 *
 * @param {boolean} isLoading - Whether data is currently loading
 * @param {boolean} hasData - Whether data has been loaded
 * @returns {React.RefObject} - Ref to attach to container element
 */
export const useListLayoutFix = (isLoading, hasData) => {
  const { containerRef, triggerRecalculation } = useLayoutFix([isLoading, hasData]);

  useEffect(() => {
    if (!isLoading && hasData) {
      triggerRecalculation();
    }
  }, [isLoading, hasData, triggerRecalculation]);

  return containerRef;
};

export default useLayoutFix;
