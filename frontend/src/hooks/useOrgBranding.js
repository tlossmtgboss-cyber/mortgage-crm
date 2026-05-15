import { useState, useEffect, useCallback, useRef } from 'react';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

// Default Perennia branding (fallback when org has no custom branding)
const DEFAULT_BRANDING = {
  org_name: 'Perennia AI',
  logo_url: null,
  primary_color: '#1F3D2E',
  accent_color: '#34a853',
  tagline: null,
  welcome_message: null,
  custom_css: null,
  cover_image_url: null,
  show_testimonials: false,
  testimonials: [],
  lo: null,
};

// In-memory cache keyed by slug (or slug/lo_slug)
const brandingCache = {};

/**
 * Hook to fetch and apply organization branding for public booking pages.
 *
 * @param {string} orgSlug      - Organization booking slug from the URL
 * @param {string} [loSlug]     - Optional LO slug for LO-specific branding
 * @returns {{ branding, loading, error }}
 */
export default function useOrgBranding(orgSlug, loSlug) {
  const [branding, setBranding] = useState(DEFAULT_BRANDING);
  const [loading, setLoading] = useState(!!orgSlug);
  const [error, setError] = useState(null);
  const styleRef = useRef(null);

  const cacheKey = loSlug ? `${orgSlug}/${loSlug}` : orgSlug;

  // Apply CSS custom properties to document root
  const applyBranding = useCallback((data) => {
    const root = document.documentElement;
    root.style.setProperty('--booking-primary', data.primary_color || '#1F3D2E');
    root.style.setProperty('--booking-accent', data.accent_color || '#34a853');

    // Compute a darker shade for hover states
    const darken = (hex, amount) => {
      const num = parseInt(hex.replace('#', ''), 16);
      const r = Math.max(0, (num >> 16) - amount);
      const g = Math.max(0, ((num >> 8) & 0x00FF) - amount);
      const b = Math.max(0, (num & 0x0000FF) - amount);
      return `#${(r << 16 | g << 8 | b).toString(16).padStart(6, '0')}`;
    };
    root.style.setProperty('--booking-primary-dark', darken(data.primary_color || '#1F3D2E', 25));
    root.style.setProperty('--booking-accent-dark', darken(data.accent_color || '#34a853', 25));

    // Inject custom CSS if provided.
    // Defense-in-depth: strip dangerous CSS constructs client-side even though
    // the server is expected to sanitize. CSS injection can exfiltrate data via
    // url(), execute JS via expression() (legacy IE), or import external sheets.
    if (data.custom_css) {
      let safeCss = data.custom_css;
      // Block @import (external stylesheet injection)
      safeCss = safeCss.replace(/@import\b[^;]*/gi, '/* blocked @import */');
      // Block expression() (IE JS execution in CSS)
      safeCss = safeCss.replace(/expression\s*\(/gi, '/* blocked-expression */(');
      // Block javascript: and data: URLs in url()
      safeCss = safeCss.replace(/url\s*\(\s*(['"]?)\s*(javascript|data)\s*:/gi, 'url($1blocked:');
      // Block -moz-binding (XBL binding, Firefox XSS vector)
      safeCss = safeCss.replace(/-moz-binding\s*:/gi, '/* blocked-binding */:');
      // Block behavior (IE HTC component)
      safeCss = safeCss.replace(/behavior\s*:/gi, '/* blocked-behavior */:');

      if (!styleRef.current) {
        styleRef.current = document.createElement('style');
        styleRef.current.setAttribute('data-org-branding', 'true');
        document.head.appendChild(styleRef.current);
      }
      styleRef.current.textContent = safeCss;
    }
  }, []);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (styleRef.current) {
        styleRef.current.remove();
        styleRef.current = null;
      }
      // Reset CSS custom properties to defaults
      const root = document.documentElement;
      root.style.removeProperty('--booking-primary');
      root.style.removeProperty('--booking-accent');
      root.style.removeProperty('--booking-primary-dark');
      root.style.removeProperty('--booking-accent-dark');
    };
  }, []);

  useEffect(() => {
    if (!orgSlug) {
      setBranding(DEFAULT_BRANDING);
      applyBranding(DEFAULT_BRANDING);
      setLoading(false);
      return;
    }

    // Check cache first
    if (brandingCache[cacheKey]) {
      setBranding(brandingCache[cacheKey]);
      applyBranding(brandingCache[cacheKey]);
      setLoading(false);
      return;
    }

    let cancelled = false;

    const fetchBranding = async () => {
      setLoading(true);
      setError(null);

      try {
        const url = loSlug
          ? `${API_BASE}/api/v1/booking/org/${orgSlug}/lo/${loSlug}`
          : `${API_BASE}/api/v1/booking/org/${orgSlug}`;

        const response = await fetch(url);

        if (!response.ok) {
          // Fall back to defaults silently -- the org might not have branding configured
          if (!cancelled) {
            setBranding(DEFAULT_BRANDING);
            applyBranding(DEFAULT_BRANDING);
            setLoading(false);
          }
          return;
        }

        const data = await response.json();
        const merged = { ...DEFAULT_BRANDING, ...data };

        // Cache the result
        brandingCache[cacheKey] = merged;

        if (!cancelled) {
          setBranding(merged);
          applyBranding(merged);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
          setBranding(DEFAULT_BRANDING);
          applyBranding(DEFAULT_BRANDING);
          setLoading(false);
        }
      }
    };

    fetchBranding();

    return () => {
      cancelled = true;
    };
  }, [orgSlug, loSlug, cacheKey, applyBranding]);

  return { branding, loading, error };
}

export { DEFAULT_BRANDING };
