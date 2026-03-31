/**
 * useDarkMode -- Dark mode hook for Perennia AI mobile app.
 *
 * Wraps the existing ThemeContext with mobile-specific enhancements:
 *   1. Syncs theme to Capacitor Preferences (cross-platform persistent storage)
 *   2. Syncs status bar style on iOS/Android via @capacitor/status-bar
 *   3. Updates <meta name="theme-color"> for browser chrome matching
 *   4. Provides a stable API for components that need theme-aware logic
 *
 * This hook is additive -- it does NOT replace ThemeContext. ThemeContext
 * remains the canonical provider. This hook layers mobile-platform concerns
 * on top via useEffect side-effects.
 *
 * Usage:
 *   const { isDark, theme, resolvedTheme, toggle, setTheme } = useDarkMode();
 */

import { useEffect, useCallback, useMemo, useRef } from 'react';
import { Capacitor } from '@capacitor/core';
import { useTheme } from '../contexts/ThemeContext';
import { getTokens } from '../utils/themeTokens';

const isNative = Capacitor.isNativePlatform();

/**
 * Lazy-load Capacitor plugins to avoid import errors on web.
 * StatusBar and Preferences are only available on native platforms.
 */
let _StatusBar = null;
let _Preferences = null;

async function getStatusBar() {
  if (_StatusBar) return _StatusBar;
  if (!isNative) return null;
  try {
    const mod = await import('@capacitor/status-bar');
    _StatusBar = mod.StatusBar;
    return _StatusBar;
  } catch {
    return null;
  }
}

async function getPreferences() {
  if (_Preferences) return _Preferences;
  try {
    const mod = await import('@capacitor/preferences');
    _Preferences = mod.Preferences;
    return _Preferences;
  } catch {
    return null;
  }
}

const PREF_KEY = 'perennia-theme';

/**
 * Sync status bar appearance to match the current theme.
 * On iOS, this controls whether the status bar icons are light or dark.
 */
async function syncStatusBar(resolvedTheme) {
  const StatusBar = await getStatusBar();
  if (!StatusBar) return;

  try {
    if (resolvedTheme === 'dark') {
      // Light icons on dark background
      await StatusBar.setStyle({ style: 'LIGHT' });
    } else {
      // Dark icons on light background
      await StatusBar.setStyle({ style: 'DARK' });
    }

    // Set background color on Android (no-op on iOS)
    const tokens = getTokens(resolvedTheme);
    try {
      await StatusBar.setBackgroundColor({ color: tokens.bgPrimary });
    } catch {
      // setBackgroundColor not available on iOS -- expected
    }
  } catch {
    // StatusBar plugin may not be available in all contexts
  }
}

/**
 * Sync theme preference to Capacitor Preferences for native persistence.
 * Falls back silently if Preferences is unavailable.
 */
async function syncPreferences(theme) {
  const Preferences = await getPreferences();
  if (!Preferences) return;

  try {
    await Preferences.set({ key: PREF_KEY, value: theme });
  } catch {
    // Preferences unavailable -- localStorage fallback handled by ThemeContext
  }
}

/**
 * Update <meta name="theme-color"> to match the current theme.
 * This colors the browser chrome / URL bar on mobile browsers.
 */
function updateMetaThemeColor(resolvedTheme) {
  const tokens = getTokens(resolvedTheme);
  let meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.name = 'theme-color';
    document.head.appendChild(meta);
  }
  meta.content = tokens.bgPrimary;
}

/**
 * Main dark mode hook.
 *
 * @returns {{
 *   isDark: boolean,
 *   theme: 'light' | 'dark' | 'system',
 *   resolvedTheme: 'light' | 'dark',
 *   toggle: () => void,
 *   setTheme: (theme: 'light' | 'dark' | 'system') => void,
 *   tokens: Record<string, string>,
 * }}
 */
export function useDarkMode() {
  const { theme, resolvedTheme, setTheme, toggleTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const prevResolvedRef = useRef(resolvedTheme);

  // Sync status bar whenever resolved theme changes
  useEffect(() => {
    if (prevResolvedRef.current !== resolvedTheme) {
      prevResolvedRef.current = resolvedTheme;
    }
    syncStatusBar(resolvedTheme);
    updateMetaThemeColor(resolvedTheme);
  }, [resolvedTheme]);

  // Sync to Capacitor Preferences whenever the user's explicit choice changes
  useEffect(() => {
    syncPreferences(theme);
  }, [theme]);

  // Load saved preference from Capacitor Preferences on mount (native only).
  // ThemeContext uses localStorage; this ensures native Preferences takes
  // precedence if a value was stored there.
  useEffect(() => {
    let cancelled = false;

    async function loadNativePreference() {
      const Preferences = await getPreferences();
      if (!Preferences || cancelled) return;

      try {
        const { value } = await Preferences.get({ key: PREF_KEY });
        if (value && !cancelled && value !== theme) {
          setTheme(value);
        }
      } catch {
        // Ignore -- fall through to localStorage default
      }
    }

    if (isNative) {
      loadNativePreference();
    }

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run once on mount

  // Memoized token set for the current theme
  const tokens = useMemo(() => getTokens(resolvedTheme), [resolvedTheme]);

  // Stable toggle callback
  const toggle = useCallback(() => {
    toggleTheme();
  }, [toggleTheme]);

  return useMemo(() => ({
    isDark,
    theme,
    resolvedTheme,
    toggle,
    setTheme,
    tokens,
  }), [isDark, theme, resolvedTheme, toggle, setTheme, tokens]);
}

export default useDarkMode;
