/**
 * ThemeContext
 *
 * Provides a user-controlled light/dark theme toggle that persists to
 * localStorage and applies a `data-theme` attribute on <html>.
 *
 * Three modes:
 *   "light"  — force light
 *   "dark"   — force dark
 *   "system" — follow OS preference (default for first-time users)
 *
 * Usage:
 *   const { theme, resolvedTheme, setTheme, toggleTheme } = useTheme();
 */

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';

const ThemeContext = createContext(null);

const STORAGE_KEY = 'perennia-theme';

function getSystemPreference() {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getStoredPreference() {
  try {
    return localStorage.getItem(STORAGE_KEY) || 'system';
  } catch {
    return 'system';
  }
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(getStoredPreference);
  const [systemPref, setSystemPref] = useState(getSystemPreference);

  // Resolve the actual applied theme
  const resolvedTheme = theme === 'system' ? systemPref : theme;

  // Listen for OS-level dark mode changes
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e) => setSystemPref(e.matches ? 'dark' : 'light');
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // Apply data-theme attribute to <html> whenever resolved theme changes
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolvedTheme);
  }, [resolvedTheme]);

  const setTheme = useCallback((newTheme) => {
    setThemeState(newTheme);
    try {
      localStorage.setItem(STORAGE_KEY, newTheme);
    } catch {
      // localStorage unavailable — state still updates for this session
    }
  }, []);

  const toggleTheme = useCallback(() => {
    // Cycle: current resolved → opposite
    setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
  }, [resolvedTheme, setTheme]);

  const value = useMemo(() => ({
    theme,          // "light" | "dark" | "system"
    resolvedTheme,  // "light" | "dark" (the actual applied theme)
    setTheme,       // set to "light", "dark", or "system"
    toggleTheme,    // quick toggle between light and dark
  }), [theme, resolvedTheme, setTheme, toggleTheme]);

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return ctx;
}

export default ThemeContext;
