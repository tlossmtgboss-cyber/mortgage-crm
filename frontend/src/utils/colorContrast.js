/**
 * Color Contrast Compliance Utilities
 * WCAG 2.1 AA/AAA contrast ratio calculations and accessible color palette.
 *
 * Legal requirement: WCAG AA mandates 4.5:1 for normal text, 3:1 for large text.
 * Large text = >= 18pt (24px) or >= 14pt (18.66px) bold.
 */

// ---------------------------------------------------------------------------
// Hex / RGB conversion helpers
// ---------------------------------------------------------------------------

/**
 * Parse a hex color string to { r, g, b } values (0-255).
 * Accepts #RGB, #RRGGBB, RGB, RRGGBB.
 */
export function hexToRgb(hex) {
  let h = hex.replace(/^#/, '');

  // Expand shorthand (#abc -> #aabbcc)
  if (h.length === 3) {
    h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  }

  if (h.length !== 6) {
    throw new Error(`Invalid hex color: ${hex}`);
  }

  const num = parseInt(h, 16);
  return {
    r: (num >> 16) & 255,
    g: (num >> 8) & 255,
    b: num & 255,
  };
}

/**
 * Convert { r, g, b } (0-255) back to a #RRGGBB hex string.
 */
export function rgbToHex({ r, g, b }) {
  const toHex = (c) => {
    const clamped = Math.max(0, Math.min(255, Math.round(c)));
    return clamped.toString(16).padStart(2, '0');
  };
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

// ---------------------------------------------------------------------------
// Relative luminance (WCAG 2.1 definition)
// ---------------------------------------------------------------------------

/**
 * Apply inverse sRGB companding to a single channel value (0-255 -> linear 0-1).
 */
function linearize(channel) {
  const srgb = channel / 255;
  return srgb <= 0.04045
    ? srgb / 12.92
    : Math.pow((srgb + 0.055) / 1.055, 2.4);
}

/**
 * Calculate relative luminance per WCAG 2.1.
 * @param {string} hex - Hex color string
 * @returns {number} Luminance in range [0, 1]
 */
export function getRelativeLuminance(hex) {
  const { r, g, b } = hexToRgb(hex);
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b);
}

// ---------------------------------------------------------------------------
// Contrast ratio
// ---------------------------------------------------------------------------

/**
 * Calculate the WCAG contrast ratio between two hex colors.
 * Result is always >= 1 (1:1 = identical, 21:1 = black on white).
 *
 * @param {string} color1 - First hex color
 * @param {string} color2 - Second hex color
 * @returns {number} Contrast ratio rounded to two decimal places
 */
export function getContrastRatio(color1, color2) {
  const l1 = getRelativeLuminance(color1);
  const l2 = getRelativeLuminance(color2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return Math.round(((lighter + 0.05) / (darker + 0.05)) * 100) / 100;
}

// ---------------------------------------------------------------------------
// WCAG pass / fail check
// ---------------------------------------------------------------------------

/**
 * Thresholds per WCAG 2.1 success criteria.
 */
const WCAG_THRESHOLDS = {
  AA: { normal: 4.5, large: 3 },
  AAA: { normal: 7, large: 4.5 },
};

/**
 * Check whether a color pair meets a given WCAG level and text size.
 *
 * @param {string} color1 - Foreground hex
 * @param {string} color2 - Background hex
 * @param {'AA'|'AAA'} level - Conformance level (default AA)
 * @param {'normal'|'large'} size - Text size category (default normal)
 * @returns {{ passes: boolean, ratio: number, required: number }}
 */
export function meetsWCAG(color1, color2, level = 'AA', size = 'normal') {
  const ratio = getContrastRatio(color1, color2);
  const thresholds = WCAG_THRESHOLDS[level] || WCAG_THRESHOLDS.AA;
  const required = thresholds[size] || thresholds.normal;
  return {
    passes: ratio >= required,
    ratio,
    required,
  };
}

// ---------------------------------------------------------------------------
// Accessible color suggestion
// ---------------------------------------------------------------------------

/**
 * Attempt to adjust a foreground color so it meets the target contrast ratio
 * against the given background. Darkens or lightens the foreground depending
 * on whether the background is light or dark.
 *
 * @param {string} foreground - Hex foreground color to adjust
 * @param {string} background - Hex background color (not changed)
 * @param {number} targetRatio - Minimum contrast ratio to achieve (default 4.5)
 * @returns {string} Adjusted hex color that meets the target, or the closest
 *   achievable color if the target cannot be met.
 */
export function suggestAccessibleColor(foreground, background, targetRatio = 4.5) {
  // If it already passes, return as-is
  if (getContrastRatio(foreground, background) >= targetRatio) {
    return foreground;
  }

  const bgLuminance = getRelativeLuminance(background);
  const bgIsLight = bgLuminance > 0.5;

  // Convert foreground to HSL for adjustment
  const { r, g, b } = hexToRgb(foreground);
  let [h, s, l] = rgbToHsl(r, g, b);

  // Binary search for the right lightness
  let lo = bgIsLight ? 0 : l;
  let hi = bgIsLight ? l : 1;
  let bestColor = foreground;
  let bestRatio = getContrastRatio(foreground, background);

  for (let i = 0; i < 30; i++) {
    const mid = (lo + hi) / 2;
    const [cr, cg, cb] = hslToRgb(h, s, mid);
    const candidate = rgbToHex({ r: cr, g: cg, b: cb });
    const ratio = getContrastRatio(candidate, background);

    if (ratio >= targetRatio) {
      bestColor = candidate;
      bestRatio = ratio;
      // Try to get closer to original lightness
      if (bgIsLight) {
        lo = mid;
      } else {
        hi = mid;
      }
    } else {
      if (bgIsLight) {
        hi = mid;
      } else {
        lo = mid;
      }
    }
  }

  // If we still cannot meet the target (e.g., colors too close in hue),
  // fall back to black or white
  if (bestRatio < targetRatio) {
    const blackRatio = getContrastRatio('#000000', background);
    const whiteRatio = getContrastRatio('#ffffff', background);
    return blackRatio >= whiteRatio ? '#000000' : '#ffffff';
  }

  return bestColor;
}

// ---------------------------------------------------------------------------
// HSL helpers (internal)
// ---------------------------------------------------------------------------

/**
 * RGB (0-255) -> HSL (h: 0-360, s: 0-1, l: 0-1)
 */
function rgbToHsl(r, g, b) {
  r /= 255;
  g /= 255;
  b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h = 0;
  let s = 0;
  const l = (max + min) / 2;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
  }

  return [h * 360, s, l];
}

/**
 * HSL (h: 0-360, s: 0-1, l: 0-1) -> RGB (0-255 each)
 */
function hslToRgb(h, s, l) {
  h /= 360;
  let r, g, b;

  if (s === 0) {
    r = g = b = l;
  } else {
    const hue2rgb = (p, q, t) => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1 / 3);
  }

  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

// ---------------------------------------------------------------------------
// Pre-verified accessible palette
// ---------------------------------------------------------------------------

/**
 * Pre-verified color pairs for common UI patterns.
 * Every value has been checked against the stated background to meet WCAG AA
 * for normal text (>= 4.5:1) unless noted as large-text-only (>= 3:1).
 *
 * Background assumptions:
 *   "OnWhite"  = #ffffff
 *   "OnDark"   = #1a1a2e
 */
export const ACCESSIBLE_PALETTE = Object.freeze({
  // -----------------------------------------------------------------------
  // Status text colors on white (#ffffff) background
  // -----------------------------------------------------------------------
  successOnWhite: '#15803d', // green-700  — 5.0:1
  warningOnWhite: '#92400e', // amber-800  — 7.1:1  (NOT #f59e0b which is 2.2:1)
  errorOnWhite: '#b91c1c', // red-700    — 6.5:1
  infoOnWhite: '#1d4ed8', // blue-700   — 6.7:1

  // -----------------------------------------------------------------------
  // Status text colors on dark (#1a1a2e) background
  // -----------------------------------------------------------------------
  successOnDark: '#4ade80', // green-400  — 9.8:1
  warningOnDark: '#fbbf24', // amber-400  — 10.2:1
  errorOnDark: '#f87171', // red-400    — 6.2:1
  infoOnDark: '#60a5fa', // blue-400   — 6.7:1

  // -----------------------------------------------------------------------
  // Muted / secondary text
  // -----------------------------------------------------------------------
  mutedOnWhite: '#4b5563', // gray-600   — 7.6:1  (NOT #9ca3af which is 2.5:1)
  mutedOnDark: '#9ca3af', // gray-400   — 6.7:1 on #1a1a2e

  // -----------------------------------------------------------------------
  // Badge / tag color pairs (background + text)
  // -----------------------------------------------------------------------
  badgeRed: Object.freeze({ bg: '#fef2f2', text: '#991b1b' }), // 7.6:1
  badgeGreen: Object.freeze({ bg: '#f0fdf4', text: '#166534' }), // 6.8:1
  badgeAmber: Object.freeze({ bg: '#fffbeb', text: '#92400e' }), // 6.8:1
  badgeBlue: Object.freeze({ bg: '#eff6ff', text: '#1e40af' }), // 8.0:1

  // -----------------------------------------------------------------------
  // Core background references (for lookups)
  // -----------------------------------------------------------------------
  bgWhite: '#ffffff',
  bgDark: '#1a1a2e',

  // -----------------------------------------------------------------------
  // Link colors
  // -----------------------------------------------------------------------
  linkOnWhite: '#1d4ed8', // blue-700   — 6.7:1
  linkOnDark: '#60a5fa', // blue-400   — 6.7:1
  linkVisitedOnWhite: '#6d28d9', // violet-700 — 7.1:1
  linkVisitedOnDark: '#a78bfa', // violet-400 — 6.3:1

  // -----------------------------------------------------------------------
  // Disabled / placeholder
  // -----------------------------------------------------------------------
  disabledTextOnWhite: '#6b7280', // gray-500   — 4.8:1 (still readable)
  placeholderOnWhite: '#6b7280', // gray-500   — 4.8:1
});

// ---------------------------------------------------------------------------
// Batch audit helper
// ---------------------------------------------------------------------------

/**
 * Audit an array of { foreground, background, label } objects and return
 * pass / fail results with suggested fixes for failures.
 *
 * @param {Array<{foreground: string, background: string, label?: string}>} pairs
 * @param {'AA'|'AAA'} level
 * @param {'normal'|'large'} size
 * @returns {Array<{label: string, foreground: string, background: string, ratio: number, required: number, passes: boolean, suggested?: string}>}
 */
export function auditColorPairs(pairs, level = 'AA', size = 'normal') {
  return pairs.map(({ foreground, background, label = '' }) => {
    const result = meetsWCAG(foreground, background, level, size);
    const entry = {
      label,
      foreground,
      background,
      ratio: result.ratio,
      required: result.required,
      passes: result.passes,
    };
    if (!result.passes) {
      entry.suggested = suggestAccessibleColor(foreground, background, result.required);
    }
    return entry;
  });
}
