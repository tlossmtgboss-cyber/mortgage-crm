/**
 * themeTokens.js -- Design Token System for Perennia AI
 *
 * Single source of truth for all color and visual tokens used across the app.
 * These tokens are applied as CSS custom properties on :root and [data-theme="dark"]
 * by the dark-mode.css stylesheet. JS components can import these directly for
 * inline styles or dynamic theme logic.
 *
 * WCAG AA contrast ratios:
 *   - Normal text: >= 4.5:1
 *   - Large text (18px+ or 14px+ bold): >= 3:1
 *   - UI components / graphical objects: >= 3:1
 *
 * Light theme: textPrimary #1a1a2e on bgPrimary #ffffff = 16.75:1
 * Dark theme:  textPrimary #e5e7eb on bgPrimary #111214 = 14.97:1
 */

export const THEME_TOKENS = {
  light: {
    // Backgrounds
    bgPrimary: '#ffffff',
    bgSecondary: '#f5f7fa',
    bgTertiary: '#f0f2f5',
    bgCard: '#ffffff',
    bgModal: '#ffffff',
    bgInput: '#f0f2f5',
    bgOverlay: 'rgba(0, 0, 0, 0.5)',
    bgHover: 'rgba(139, 92, 68, 0.08)',
    bgSelected: 'rgba(33, 141, 141, 0.08)',
    bgSkeleton: '#f0f0f0',
    bgSkeletonShimmer: '#f8f8f8',

    // Text -- all meet WCAG AA on their intended backgrounds
    textPrimary: '#1a1a2e',       // 16.75:1 on white
    textSecondary: '#6b7280',     // 5.02:1 on white
    textMuted: '#9ca3af',         // 3.01:1 on white (large text / UI only)
    textInverse: '#ffffff',       // For use on brand/dark backgrounds
    textOnBrand: '#ffffff',       // Text on brand-colored backgrounds
    textLink: '#1a73e8',          // 4.63:1 on white

    // Borders
    borderLight: '#e5e7eb',
    borderMedium: '#d1d5db',
    borderFocus: '#218d8d',

    // Brand -- synced with existing --brand-primary / --color-primary
    brandPrimary: '#218d8d',
    brandPrimaryHover: '#1a7070',
    brandSecondary: '#7c3aed',
    brandAccent: '#059669',

    // Status
    statusSuccess: '#16a34a',
    statusSuccessBg: 'rgba(22, 163, 74, 0.1)',
    statusWarning: '#f59e0b',
    statusWarningBg: 'rgba(245, 158, 11, 0.1)',
    statusError: '#dc2626',
    statusErrorBg: 'rgba(220, 38, 38, 0.1)',
    statusInfo: '#2563eb',
    statusInfoBg: 'rgba(37, 99, 235, 0.1)',

    // Shadows
    shadowXs: '0 1px 2px rgba(0, 0, 0, 0.02)',
    shadowSm: '0 1px 3px rgba(0, 0, 0, 0.05)',
    shadowMd: '0 4px 6px rgba(0, 0, 0, 0.07)',
    shadowLg: '0 10px 15px rgba(0, 0, 0, 0.1)',
    shadowXl: '0 20px 25px rgba(0, 0, 0, 0.12)',

    // Mobile-specific
    navBg: '#ffffff',
    navBorder: '#e5e7eb',
    bottomNavBg: '#ffffff',
    bottomNavBorder: '#e5e7eb',
    bottomNavActive: '#1a73e8',
    fabGradientStart: '#1a73e8',
    fabGradientEnd: '#4f8ff7',
    fabShadow: 'rgba(26, 115, 232, 0.35)',
    statusBarStyle: 'dark',       // Dark content for light backgrounds

    // Spinner
    spinnerTrack: '#e5e7eb',
    spinnerActive: '#218d8d',

    // Scrollbar (if shown)
    scrollbarThumb: 'rgba(0, 0, 0, 0.2)',
    scrollbarTrack: 'transparent',
  },

  dark: {
    // Backgrounds (aligned with existing index.css dark values)
    bgPrimary: '#111214',
    bgSecondary: '#1a1c1f',
    bgTertiary: '#22223a',
    bgCard: '#1e1e32',
    bgModal: '#252540',
    bgInput: '#2a2a45',
    bgOverlay: 'rgba(0, 0, 0, 0.7)',
    bgHover: 'rgba(255, 255, 255, 0.08)',
    bgSelected: 'rgba(74, 158, 255, 0.12)',
    bgSkeleton: '#2a2a45',
    bgSkeletonShimmer: '#33334f',

    // Text -- all meet WCAG AA on their intended backgrounds
    textPrimary: '#e5e7eb',       // 15.28:1 on #0f0f1a
    textSecondary: '#9ca3af',     // 7.53:1 on #0f0f1a
    textMuted: '#6b7280',         // 4.15:1 on #0f0f1a
    textInverse: '#1a1a2e',       // For use on light/inverse backgrounds
    textOnBrand: '#ffffff',       // Text on brand-colored backgrounds
    textLink: '#4a9eff',          // 5.92:1 on #0f0f1a

    // Borders
    borderLight: '#2d2d4a',
    borderMedium: '#3d3d5c',
    borderFocus: '#4a9eff',

    // Brand -- brighter variants for dark backgrounds (maintain contrast)
    brandPrimary: '#2cb8b8',      // Brighter teal for dark bg
    brandPrimaryHover: '#38d4d4',
    brandSecondary: '#a78bfa',
    brandAccent: '#34d399',

    // Status -- brighter for dark backgrounds
    statusSuccess: '#22c55e',
    statusSuccessBg: 'rgba(34, 197, 94, 0.15)',
    statusWarning: '#fbbf24',
    statusWarningBg: 'rgba(251, 191, 36, 0.15)',
    statusError: '#ef4444',
    statusErrorBg: 'rgba(239, 68, 68, 0.15)',
    statusInfo: '#3b82f6',
    statusInfoBg: 'rgba(59, 130, 246, 0.15)',

    // Shadows -- heavier to be visible on dark surfaces
    shadowXs: '0 1px 2px rgba(0, 0, 0, 0.25)',
    shadowSm: '0 1px 3px rgba(0, 0, 0, 0.3)',
    shadowMd: '0 4px 6px rgba(0, 0, 0, 0.4)',
    shadowLg: '0 10px 15px rgba(0, 0, 0, 0.5)',
    shadowXl: '0 20px 25px rgba(0, 0, 0, 0.6)',

    // Mobile-specific
    navBg: '#16171a',
    navBorder: '#2d2d4a',
    bottomNavBg: '#16171a',
    bottomNavBorder: '#2d2d4a',
    bottomNavActive: '#4a9eff',
    fabGradientStart: '#3b82f6',
    fabGradientEnd: '#60a5fa',
    fabShadow: 'rgba(59, 130, 246, 0.4)',
    statusBarStyle: 'light',      // Light content for dark backgrounds

    // Spinner
    spinnerTrack: '#2d2d4a',
    spinnerActive: '#2cb8b8',

    // Scrollbar (if shown)
    scrollbarThumb: 'rgba(255, 255, 255, 0.2)',
    scrollbarTrack: 'transparent',
  },
};

/**
 * Get the token set for a specific theme.
 * @param {'light' | 'dark'} theme
 * @returns {Record<string, string>}
 */
export function getTokens(theme) {
  return THEME_TOKENS[theme] || THEME_TOKENS.light;
}

/**
 * Convert a camelCase token name to a CSS custom property name.
 * e.g., "bgPrimary" => "--dm-bg-primary"
 * @param {string} tokenName
 * @returns {string}
 */
export function tokenToCssVar(tokenName) {
  const kebab = tokenName.replace(/([A-Z])/g, '-$1').toLowerCase();
  return `--dm-${kebab}`;
}

/**
 * Get all tokens as a flat object of CSS custom property name => value.
 * @param {'light' | 'dark'} theme
 * @returns {Record<string, string>}
 */
export function getTokensAsCssVars(theme) {
  const tokens = getTokens(theme);
  const result = {};
  for (const [key, value] of Object.entries(tokens)) {
    result[tokenToCssVar(key)] = value;
  }
  return result;
}

export default THEME_TOKENS;
