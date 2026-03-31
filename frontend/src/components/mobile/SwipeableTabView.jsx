import React, { useRef, useState, useCallback, useEffect, useMemo } from 'react';
import useSwipeGesture from '../../hooks/useSwipeGesture';
import { haptics } from '../../services/nativeServices';
import './SwipeableTabView.css';

/**
 * SwipeableTabView - Horizontal swipe navigation between tab panels.
 *
 * Provides a native-feeling tab interface with:
 * - Swipe left/right to change tabs
 * - Animated slide transition with spring easing
 * - Tab indicator bar that tracks swipe progress in real-time
 * - Haptic feedback on tab change (Capacitor native only)
 * - Respects prefers-reduced-motion (instant switch, no animation)
 *
 * Usage:
 *   <SwipeableTabView
 *     tabs={['Pipeline', 'Leads', 'Tasks']}
 *     activeTab={activeTab}
 *     onTabChange={setActiveTab}
 *   >
 *     <PipelineView />
 *     <LeadsView />
 *     <TasksView />
 *   </SwipeableTabView>
 */

function SwipeableTabView({
  tabs,
  activeTab = 0,
  onTabChange,
  children,
  className = '',
  tabBarClassName = '',
  swipeThreshold = 50,
  animationDuration = 320,
}) {
  const containerRef = useRef(null);
  const panelTrackRef = useRef(null);
  const indicatorRef = useRef(null);
  const [dragOffset, setDragOffset] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false);
  const prefersReducedMotion = usePrefersReducedMotion();

  const tabCount = tabs.length;
  const childrenArray = React.Children.toArray(children);

  // Clamp helper
  const clamp = (val, min, max) => Math.min(Math.max(val, min), max);

  // Trigger haptic feedback on tab switch
  const triggerHaptic = useCallback(() => {
    try {
      haptics.light();
    } catch (_e) {
      // Haptics unavailable on web — silently ignore
    }
  }, []);

  const goToTab = useCallback((index) => {
    const clamped = clamp(index, 0, tabCount - 1);
    if (clamped !== activeTab) {
      triggerHaptic();
      onTabChange?.(clamped);
    }
    setDragOffset(0);
  }, [activeTab, tabCount, onTabChange, triggerHaptic]);

  // Swipe handlers
  const handleSwipeLeft = useCallback(() => {
    if (activeTab < tabCount - 1) {
      goToTab(activeTab + 1);
    }
  }, [activeTab, tabCount, goToTab]);

  const handleSwipeRight = useCallback(() => {
    if (activeTab > 0) {
      goToTab(activeTab - 1);
    }
  }, [activeTab, goToTab]);

  const handleSwipeMove = useCallback(({ deltaX, direction }) => {
    if (direction !== 'horizontal') return;

    // Constrain drag: rubber-band at edges
    let offset = deltaX;
    if ((activeTab === 0 && deltaX > 0) || (activeTab === tabCount - 1 && deltaX < 0)) {
      // Rubber-band: diminish movement at edges
      offset = deltaX * 0.3;
    }

    setDragOffset(offset);
  }, [activeTab, tabCount]);

  const { ref: swipeRef } = useSwipeGesture({
    onSwipeLeft: handleSwipeLeft,
    onSwipeRight: handleSwipeRight,
    threshold: swipeThreshold,
    preventScrollOnHorizontal: true,
    onSwipeMove: handleSwipeMove,
  });

  // Combine refs (swipeRef for gesture detection, containerRef for sizing)
  const setRefs = useCallback((node) => {
    swipeRef.current = node;
    containerRef.current = node;
  }, [swipeRef]);

  // Animate the panel track position
  const panelTranslateX = useMemo(() => {
    const baseOffset = -(activeTab * 100);
    if (dragOffset === 0) return `${baseOffset}%`;
    // Convert px drag to percentage of container width
    const containerWidth = containerRef.current?.offsetWidth || 375;
    const dragPct = (dragOffset / containerWidth) * 100;
    return `calc(${baseOffset}% + ${dragPct}%)`;
  }, [activeTab, dragOffset]);

  // Indicator position and width tracking
  const indicatorStyle = useMemo(() => {
    const tabWidth = 100 / tabCount;
    const baseLeft = activeTab * tabWidth;

    if (dragOffset === 0) {
      return { left: `${baseLeft}%`, width: `${tabWidth}%` };
    }

    // Move indicator proportionally with drag
    const containerWidth = containerRef.current?.offsetWidth || 375;
    const dragPct = (dragOffset / containerWidth) * 100;
    const indicatorLeft = clamp(baseLeft - dragPct, 0, 100 - tabWidth);
    return { left: `${indicatorLeft}%`, width: `${tabWidth}%` };
  }, [activeTab, tabCount, dragOffset]);

  // When activeTab changes externally, trigger slide animation
  useEffect(() => {
    if (prefersReducedMotion) return;
    setIsAnimating(true);
    const timer = setTimeout(() => setIsAnimating(false), animationDuration);
    return () => clearTimeout(timer);
  }, [activeTab, animationDuration, prefersReducedMotion]);

  // Reset drag offset when touch ends (swipeState goes to isSwiping=false)
  // This is handled in the swipe callbacks already, but ensure cleanup
  useEffect(() => {
    setDragOffset(0);
  }, [activeTab]);

  const shouldAnimate = !prefersReducedMotion && (isAnimating || dragOffset === 0);
  const transitionStyle = shouldAnimate
    ? `transform ${animationDuration}ms cubic-bezier(0.25, 0.46, 0.45, 0.94)`
    : 'none';

  return (
    <div
      className={`swipeable-tab-view ${className}`}
      ref={setRefs}
      data-reduced-motion={prefersReducedMotion || undefined}
    >
      {/* Tab Bar */}
      <div className={`swipeable-tab-bar ${tabBarClassName}`} role="tablist">
        {tabs.map((tab, index) => (
          <button
            key={index}
            role="tab"
            aria-selected={index === activeTab}
            aria-controls={`swipeable-panel-${index}`}
            className={`swipeable-tab ${index === activeTab ? 'swipeable-tab--active' : ''}`}
            onClick={() => goToTab(index)}
            tabIndex={index === activeTab ? 0 : -1}
          >
            {typeof tab === 'string' ? tab : tab}
          </button>
        ))}
        <div
          className="swipeable-tab-indicator"
          ref={indicatorRef}
          style={{
            ...indicatorStyle,
            transition: shouldAnimate
              ? `left ${animationDuration}ms cubic-bezier(0.25, 0.46, 0.45, 0.94)`
              : 'none',
          }}
        />
      </div>

      {/* Panel Track */}
      <div className="swipeable-panel-viewport">
        <div
          className="swipeable-panel-track"
          ref={panelTrackRef}
          style={{
            width: `${tabCount * 100}%`,
            transform: `translateX(${panelTranslateX})`,
            transition: transitionStyle,
          }}
        >
          {childrenArray.map((child, index) => (
            <div
              key={index}
              id={`swipeable-panel-${index}`}
              role="tabpanel"
              aria-hidden={index !== activeTab}
              className="swipeable-panel"
              style={{ width: `${100 / tabCount}%` }}
            >
              {child}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Hook to detect prefers-reduced-motion media query.
 * Returns true if the user has requested reduced motion.
 */
function usePrefersReducedMotion() {
  const [prefersReduced, setPrefersReduced] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handler = (event) => setPrefersReduced(event.matches);

    // Modern browsers support addEventListener on MediaQueryList
    if (mq.addEventListener) {
      mq.addEventListener('change', handler);
      return () => mq.removeEventListener('change', handler);
    }
    // Fallback for older browsers
    mq.addListener(handler);
    return () => mq.removeListener(handler);
  }, []);

  return prefersReduced;
}

export default SwipeableTabView;
