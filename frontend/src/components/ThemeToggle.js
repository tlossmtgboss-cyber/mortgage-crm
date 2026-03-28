/**
 * ThemeToggle — Sun/Moon toggle for light/dark mode.
 *
 * Sits in the Navigation bar's nav-actions section.
 * Uses pure CSS for the icon morph animation (no dependencies).
 */

import React from 'react';
import { useTheme } from '../contexts/ThemeContext';
import './ThemeToggle.css';

function ThemeToggle() {
  const { resolvedTheme, toggleTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  return (
    <button
      className={`theme-toggle ${isDark ? 'theme-toggle--dark' : ''}`}
      onClick={toggleTheme}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={isDark ? 'Light mode' : 'Dark mode'}
      type="button"
    >
      <svg
        className="theme-toggle__icon"
        viewBox="0 0 24 24"
        width="18"
        height="18"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {/* Sun rays — fade out in dark mode */}
        <g className="theme-toggle__rays">
          <line x1="12" y1="1" x2="12" y2="3" />
          <line x1="12" y1="21" x2="12" y2="23" />
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
          <line x1="1" y1="12" x2="3" y2="12" />
          <line x1="21" y1="12" x2="23" y2="12" />
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
        </g>
        {/* Circle — morphs from sun to moon via clip path */}
        <circle className="theme-toggle__circle" cx="12" cy="12" r="5" />
        {/* Moon mask — slides in for dark mode */}
        <circle className="theme-toggle__mask" cx="16" cy="8" r="4" fill="var(--color-bg-surface)" stroke="none" />
      </svg>
    </button>
  );
}

export default ThemeToggle;
