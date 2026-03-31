import { useState, useEffect, useMemo, useCallback } from 'react';

/**
 * iOS Dynamic Type scale categories.
 *
 * These correspond to the UIContentSizeCategory values that iOS maps
 * onto the root font-size of WKWebView when Dynamic Type is enabled.
 * The float value represents the ratio vs the system default (Large = 1.0).
 */
const SCALE_FACTORS = {
  xSmall: 0.82,
  small: 0.88,
  medium: 0.94,
  large: 1.0, // Default
  xLarge: 1.12,
  xxLarge: 1.24,
  xxxLarge: 1.35,
  accessibility1: 1.6,
  accessibility2: 1.9,
  accessibility3: 2.35,
};

/**
 * The baseline font-size that iOS WKWebView uses at the "Large" (default)
 * Dynamic Type setting. When the user increases text size in iOS Settings,
 * the browser's root font-size changes proportionally.
 */
const BASE_FONT_SIZE_PX = 16;

/**
 * Threshold above which we consider the user to be in an iOS Accessibility
 * size category (accessibility1 / accessibility2 / accessibility3).
 */
const ACCESSIBILITY_THRESHOLD = 1.35;

/**
 * Threshold at which layouts should aggressively reflow -- horizontal
 * arrangements become vertical, decorative chrome is hidden, etc.
 */
const REFLOW_THRESHOLD = 1.6;

/**
 * Determine the closest named scale category for a given numeric factor.
 */
function classifyScale(factor) {
  const entries = Object.entries(SCALE_FACTORS);
  let closest = entries[0];
  let minDiff = Math.abs(factor - closest[1]);

  for (let i = 1; i < entries.length; i++) {
    const diff = Math.abs(factor - entries[i][1]);
    if (diff < minDiff) {
      minDiff = diff;
      closest = entries[i];
    }
  }

  return closest[0]; // category name
}

/**
 * Read the current computed font-size on <html> and derive the scale factor.
 * Returns 1.0 when running outside a browser or when the root size matches
 * the baseline.
 */
function readScaleFactor() {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return 1.0;
  }

  const html = document.documentElement;
  const computedSize = parseFloat(window.getComputedStyle(html).fontSize);

  if (!computedSize || isNaN(computedSize)) {
    return 1.0;
  }

  return computedSize / BASE_FONT_SIZE_PX;
}

/**
 * Apply Dynamic-Type-related CSS custom properties and data attributes to
 * the <html> element so that pure-CSS rules can respond to the current scale.
 */
function applyRootAttributes(scaleFactor, category) {
  if (typeof document === 'undefined') return;

  const html = document.documentElement;

  // Expose the numeric scale as a CSS custom property for calc()-based sizing.
  html.style.setProperty('--dt-scale', scaleFactor.toFixed(3));

  // Expose the named category so CSS attribute selectors can key off it,
  // e.g. [data-dt-size="accessibility1"] .stat-row { flex-direction: column; }
  html.dataset.dtSize = category;

  // Boolean flags for quick CSS targeting.
  if (scaleFactor > ACCESSIBILITY_THRESHOLD) {
    html.dataset.dtAccessibility = 'true';
  } else {
    delete html.dataset.dtAccessibility;
  }

  if (scaleFactor > REFLOW_THRESHOLD) {
    html.dataset.dtReflow = 'true';
  } else {
    delete html.dataset.dtReflow;
  }
}

/**
 * useDynamicType
 *
 * React hook that detects the current iOS Dynamic Type scale factor by
 * reading the computed font-size on <html> (WKWebView adjusts this when
 * the user changes their preferred text size in iOS Settings).
 *
 * It re-evaluates whenever:
 *   - The window is resized (covers orientation changes)
 *   - The document regains visibility (covers returning from Settings)
 *   - A MutationObserver detects style changes on <html>
 *
 * Returns:
 *   scaleFactor        - numeric ratio vs baseline (1.0 = default)
 *   fontScale          - same value, kept for caller convenience
 *   category           - named size category (e.g. "large", "accessibility1")
 *   isAccessibilitySize - true when scaleFactor > 1.35
 *   shouldReflow       - true when scaleFactor > 1.6 (stack layouts)
 *   shouldReduceChrome - true when scaleFactor > 1.6 (hide decorative UI)
 *   scaleValue(px)     - helper to scale a pixel value by the current factor
 */
export function useDynamicType() {
  const [scaleFactor, setScaleFactor] = useState(() => readScaleFactor());

  const update = useCallback(() => {
    const next = readScaleFactor();
    setScaleFactor((prev) => {
      // Avoid unnecessary re-renders when the value has not meaningfully changed.
      if (Math.abs(prev - next) < 0.005) return prev;
      return next;
    });
  }, []);

  useEffect(() => {
    // Initial read (may differ from the SSR/pre-hydration value).
    update();

    // --- Resize listener (orientation changes, split-view resize) ----------
    window.addEventListener('resize', update);

    // --- Visibility change (user returns from iOS Settings) ----------------
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        // Small delay: iOS may not have updated the root font-size yet.
        setTimeout(update, 100);
      }
    };
    document.addEventListener('visibilitychange', onVisibility);

    // --- MutationObserver on <html> style attribute -----------------------
    // Some WebView implementations patch the style directly.
    let observer;
    if (typeof MutationObserver !== 'undefined') {
      observer = new MutationObserver(update);
      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['style'],
      });
    }

    // --- Periodic fallback (300 ms) for edge cases where none of the above
    // fire (e.g. WKWebView internal reflow without a resize event). We use a
    // low-frequency interval to keep CPU overhead negligible.
    const interval = setInterval(update, 300);

    return () => {
      window.removeEventListener('resize', update);
      document.removeEventListener('visibilitychange', onVisibility);
      if (observer) observer.disconnect();
      clearInterval(interval);
    };
  }, [update]);

  // --- Derived values (memoized to avoid recalculation on every render) ----

  const derived = useMemo(() => {
    const category = classifyScale(scaleFactor);
    const isAccessibilitySize = scaleFactor > ACCESSIBILITY_THRESHOLD;
    const shouldReflow = scaleFactor > REFLOW_THRESHOLD;
    const shouldReduceChrome = scaleFactor > REFLOW_THRESHOLD;

    // Push attributes to <html> so CSS can respond without JS.
    applyRootAttributes(scaleFactor, category);

    return {
      scaleFactor,
      fontScale: scaleFactor, // alias
      category,
      isAccessibilitySize,
      shouldReflow,
      shouldReduceChrome,
    };
  }, [scaleFactor]);

  /**
   * Scale a raw pixel value by the current Dynamic Type factor.
   * Useful for inline styles that must remain proportional to text.
   *
   * @param {number} px - Base pixel value at 1x scale
   * @returns {number} Scaled value (rounded to 1 decimal)
   */
  const scaleValue = useCallback(
    (px) => Math.round(px * scaleFactor * 10) / 10,
    [scaleFactor],
  );

  return {
    ...derived,
    scaleValue,
  };
}

export { SCALE_FACTORS };
export default useDynamicType;
