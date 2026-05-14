import { useState, useEffect, useCallback } from 'react';

/**
 * useMediaQuery - Simple hook that tracks whether a CSS media query matches.
 *
 * Uses window.matchMedia for efficient, event-driven matching.
 * Returns a boolean indicating whether the query currently matches.
 */
export function useMediaQuery(query: string): boolean {
  const getMatches = useCallback((): boolean => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(query).matches;
  }, [query]);

  const [matches, setMatches] = useState<boolean>(getMatches);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const mediaQueryList = window.matchMedia(query);

    // Set initial value (query may have changed)
    setMatches(mediaQueryList.matches);

    const handler = (event: MediaQueryListEvent): void => {
      setMatches(event.matches);
    };

    // Modern browsers support addEventListener on MediaQueryList
    if (mediaQueryList.addEventListener) {
      mediaQueryList.addEventListener('change', handler);
      return () => mediaQueryList.removeEventListener('change', handler);
    }

    // Fallback for older browsers (Safari < 14)
    mediaQueryList.addListener(handler);
    return () => mediaQueryList.removeListener(handler);
  }, [query]);

  return matches;
}

/**
 * useIsTablet - Detects tablet viewport (768px - 1024px).
 */
export function useIsTablet(): boolean {
  return useMediaQuery('(min-width: 768px) and (max-width: 1024px)');
}

/**
 * useIsMobile - Detects mobile viewport (below 768px).
 */
export function useIsMobile(): boolean {
  return useMediaQuery('(max-width: 767px)');
}

/**
 * useIsDesktop - Detects desktop viewport (above 1024px).
 */
export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 1025px)');
}

/**
 * useIsPortrait - Detects portrait orientation.
 */
export function useIsPortrait(): boolean {
  return useMediaQuery('(orientation: portrait)');
}

/**
 * useIsLandscape - Detects landscape orientation.
 */
export function useIsLandscape(): boolean {
  return useMediaQuery('(orientation: landscape)');
}

/**
 * useIsTabletPortrait - Detects tablet in portrait orientation.
 */
export function useIsTabletPortrait(): boolean {
  return useMediaQuery('(min-width: 768px) and (max-width: 1024px) and (orientation: portrait)');
}

/**
 * useIsTabletLandscape - Detects tablet in landscape orientation.
 */
export function useIsTabletLandscape(): boolean {
  return useMediaQuery('(min-width: 768px) and (max-width: 1024px) and (orientation: landscape)');
}

export default useMediaQuery;
