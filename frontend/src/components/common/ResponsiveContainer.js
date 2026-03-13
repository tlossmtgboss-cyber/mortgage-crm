import React, { useRef, useState, useEffect, useCallback } from 'react';

/**
 * BREAKPOINTS - Defaults for container-width-based responsiveness.
 * These are element widths, NOT window widths.
 */
const DEFAULT_BREAKPOINTS = {
  mobile: 0,     // 0 - 767
  tablet: 768,   // 768 - 1023
  desktop: 1024, // 1024+
};

/**
 * useContainerQuery - Custom hook that uses ResizeObserver
 * to track the width of a container element and return
 * the current breakpoint name.
 *
 * Returns { ref, breakpoint, width }
 */
export function useContainerQuery(breakpoints = DEFAULT_BREAKPOINTS) {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);

  const getBreakpoint = useCallback((w) => {
    if (w >= breakpoints.desktop) return 'desktop';
    if (w >= breakpoints.tablet) return 'tablet';
    return 'mobile';
  }, [breakpoints]);

  const [breakpoint, setBreakpoint] = useState('desktop');

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    // Initial measurement
    const rect = element.getBoundingClientRect();
    setWidth(rect.width);
    setBreakpoint(getBreakpoint(rect.width));

    if (typeof ResizeObserver === 'undefined') {
      // Fallback: listen to window resize
      const handleResize = () => {
        if (ref.current) {
          const r = ref.current.getBoundingClientRect();
          setWidth(r.width);
          setBreakpoint(getBreakpoint(r.width));
        }
      };
      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
    }

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const entryWidth = entry.contentBoxSize
          ? entry.contentBoxSize[0]?.inlineSize || entry.contentRect.width
          : entry.contentRect.width;
        setWidth(entryWidth);
        setBreakpoint(getBreakpoint(entryWidth));
      }
    });

    observer.observe(element);
    return () => observer.disconnect();
  }, [getBreakpoint]);

  return { ref, breakpoint, width };
}

/**
 * useScreenOrientation - Custom hook to detect landscape vs portrait.
 * Returns 'landscape' | 'portrait'
 */
export function useScreenOrientation() {
  const [orientation, setOrientation] = useState(() => {
    if (typeof window === 'undefined') return 'portrait';
    return window.innerWidth > window.innerHeight ? 'landscape' : 'portrait';
  });

  useEffect(() => {
    const handleChange = () => {
      setOrientation(
        window.innerWidth > window.innerHeight ? 'landscape' : 'portrait'
      );
    };

    // Use the modern screen.orientation API when available
    if (window.screen?.orientation) {
      window.screen.orientation.addEventListener('change', handleChange);
    }
    window.addEventListener('resize', handleChange);
    window.addEventListener('orientationchange', handleChange);

    return () => {
      if (window.screen?.orientation) {
        window.screen.orientation.removeEventListener('change', handleChange);
      }
      window.removeEventListener('resize', handleChange);
      window.removeEventListener('orientationchange', handleChange);
    };
  }, []);

  return orientation;
}

/**
 * useIsTablet - Simple hook to detect tablet-range viewport widths.
 * Uses window.innerWidth (not container width).
 * Returns boolean.
 */
export function useIsTablet(minWidth = 768, maxWidth = 1024) {
  const [isTablet, setIsTablet] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.innerWidth >= minWidth && window.innerWidth <= maxWidth;
  });

  useEffect(() => {
    const handleResize = () => {
      setIsTablet(window.innerWidth >= minWidth && window.innerWidth <= maxWidth);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [minWidth, maxWidth]);

  return isTablet;
}

/**
 * ResponsiveContainer - Wrapper component that adapts children layout
 * based on the container's own width (using ResizeObserver).
 *
 * Props:
 *   mobileLayout   - CSS class or render function for mobile (<768px container)
 *   tabletLayout   - CSS class or render function for tablet (768-1023px container)
 *   desktopLayout  - CSS class or render function for desktop (>=1024px container)
 *   mobile         - React node to render ONLY on mobile (exclusive rendering mode)
 *   tablet         - React node to render ONLY on tablet (exclusive rendering mode)
 *   desktop        - React node to render ONLY on desktop (exclusive rendering mode)
 *   breakpoints    - Custom breakpoint thresholds { mobile, tablet, desktop }
 *   className      - Additional class names
 *   as             - HTML element to render (default: 'div')
 *   children       - Child content (or function receiving { breakpoint, width, orientation })
 *
 * Usage modes:
 * 1. Layout classes: <ResponsiveContainer mobileLayout="stack" tabletLayout="grid-2">...</ResponsiveContainer>
 * 2. Render function: <ResponsiveContainer>{({ breakpoint }) => ...}</ResponsiveContainer>
 * 3. Exclusive rendering: <ResponsiveContainer mobile={<MobileView />} tablet={<TabletView />} desktop={<DesktopView />} />
 */
const ResponsiveContainer = React.memo(function ResponsiveContainer({
  mobileLayout = '',
  tabletLayout = '',
  desktopLayout = '',
  mobile,
  tablet,
  desktop,
  breakpoints,
  className = '',
  as: Component = 'div',
  children,
  ...restProps
}) {
  const { ref, breakpoint, width } = useContainerQuery(breakpoints);
  const orientation = useScreenOrientation();

  // Select the layout class for the current breakpoint
  const layoutClass =
    breakpoint === 'desktop' ? desktopLayout :
    breakpoint === 'tablet' ? tabletLayout :
    mobileLayout;

  const combinedClassName = [
    'responsive-container',
    `responsive-container--${breakpoint}`,
    layoutClass,
    className,
  ].filter(Boolean).join(' ');

  // Exclusive rendering mode: if mobile/tablet/desktop props are provided,
  // render only the one matching the current breakpoint
  const hasExclusiveProps = mobile !== undefined || tablet !== undefined || desktop !== undefined;

  let content;
  if (hasExclusiveProps) {
    if (breakpoint === 'desktop') {
      content = desktop !== undefined ? desktop : children;
    } else if (breakpoint === 'tablet') {
      content = tablet !== undefined ? tablet : children;
    } else {
      content = mobile !== undefined ? mobile : children;
    }
    // If the selected content is a function, call it with context
    if (typeof content === 'function') {
      content = content({ breakpoint, width, orientation });
    }
  } else if (typeof children === 'function') {
    // Render-function children for maximum flexibility
    content = children({ breakpoint, width, orientation });
  } else {
    content = children;
  }

  return (
    <Component
      ref={ref}
      className={combinedClassName}
      data-breakpoint={breakpoint}
      data-orientation={orientation}
      {...restProps}
    >
      {content}
    </Component>
  );
});

export default ResponsiveContainer;
