/**
 * useVirtualList
 *
 * Lightweight list virtualization hook for mobile views.
 * Renders only the visible slice of items plus an overscan buffer,
 * keeping the DOM small even for lists with hundreds of items.
 *
 * Supports two scroll modes:
 *  - Container mode (default): tracks scroll position of a ref'd element
 *  - Window mode (useWindowScroll: true): tracks window scroll, with an
 *    optional listOffsetRef to account for sticky headers above the list
 *
 * Usage (container mode):
 *   const { containerRef, visibleItems, startIndex, totalHeight, offsetY } =
 *     useVirtualList({ items, itemHeight: 160 });
 *
 *   <div ref={containerRef} style={{ overflow: 'auto', height: '100%' }}>
 *     <div style={{ height: totalHeight, position: 'relative' }}>
 *       <div style={{ transform: `translateY(${offsetY}px)` }}>
 *         {visibleItems.map((item, i) => ...)}
 *       </div>
 *     </div>
 *   </div>
 *
 * Usage (window scroll mode):
 *   const { listRef, visibleItems, startIndex, totalHeight, offsetY } =
 *     useVirtualList({ items, itemHeight: 160, useWindowScroll: true });
 *
 *   <div ref={listRef}>
 *     <div style={{ height: totalHeight, position: 'relative' }}>
 *       <div style={{ transform: `translateY(${offsetY}px)` }}>
 *         {visibleItems.map((item, i) => ...)}
 *       </div>
 *     </div>
 *   </div>
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';

const VIRTUALIZATION_THRESHOLD = 50;

export function useVirtualList({
  items,
  itemHeight,
  overscan = 5,
  enabled = true,
  useWindowScroll = false,
}) {
  const containerRef = useRef(null);
  const listRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);
  const [listOffsetTop, setListOffsetTop] = useState(0);

  // Auto-disable virtualization for small lists
  const shouldVirtualize = enabled && items.length > VIRTUALIZATION_THRESHOLD;

  // Measure list offset from top of page (for window scroll mode)
  const measureListOffset = useCallback(() => {
    if (useWindowScroll && listRef.current) {
      const rect = listRef.current.getBoundingClientRect();
      setListOffsetTop(rect.top + window.scrollY);
    }
  }, [useWindowScroll]);

  // Container scroll mode
  useEffect(() => {
    if (useWindowScroll || !shouldVirtualize) return;

    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(([entry]) => {
      setViewportHeight(entry.contentRect.height);
    });
    observer.observe(container);

    const handleScroll = () => setScrollTop(container.scrollTop);
    container.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      observer.disconnect();
      container.removeEventListener('scroll', handleScroll);
    };
  }, [shouldVirtualize, useWindowScroll]);

  // Window scroll mode
  useEffect(() => {
    if (!useWindowScroll || !shouldVirtualize) return;

    setViewportHeight(window.innerHeight);
    measureListOffset();

    const handleScroll = () => setScrollTop(window.scrollY);
    const handleResize = () => {
      setViewportHeight(window.innerHeight);
      measureListOffset();
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('resize', handleResize, { passive: true });

    return () => {
      window.removeEventListener('scroll', handleScroll);
      window.removeEventListener('resize', handleResize);
    };
  }, [shouldVirtualize, useWindowScroll, measureListOffset]);

  // Re-measure list offset when items change (layout may shift)
  useEffect(() => {
    if (useWindowScroll && shouldVirtualize) {
      // Defer measurement to after render
      const raf = requestAnimationFrame(measureListOffset);
      return () => cancelAnimationFrame(raf);
    }
  }, [items.length, useWindowScroll, shouldVirtualize, measureListOffset]);

  const { visibleItems, startIndex, totalHeight, offsetY } = useMemo(() => {
    if (!shouldVirtualize || viewportHeight === 0) {
      return {
        visibleItems: items,
        startIndex: 0,
        totalHeight: 0, // No spacer needed when not virtualizing
        offsetY: 0,
      };
    }

    // For window scroll mode, calculate scroll position relative to the list
    let relativeScrollTop;
    if (useWindowScroll) {
      relativeScrollTop = Math.max(0, scrollTop - listOffsetTop);
    } else {
      relativeScrollTop = scrollTop;
    }

    const startIdx = Math.max(0, Math.floor(relativeScrollTop / itemHeight) - overscan);
    const endIdx = Math.min(
      items.length,
      Math.ceil((relativeScrollTop + viewportHeight) / itemHeight) + overscan
    );

    return {
      visibleItems: items.slice(startIdx, endIdx),
      startIndex: startIdx,
      totalHeight: items.length * itemHeight,
      offsetY: startIdx * itemHeight,
    };
  }, [items, itemHeight, scrollTop, viewportHeight, overscan, shouldVirtualize, useWindowScroll, listOffsetTop]);

  return {
    containerRef,
    listRef,
    visibleItems,
    startIndex,
    totalHeight,
    offsetY,
    isVirtualized: shouldVirtualize,
  };
}
