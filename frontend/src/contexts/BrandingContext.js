/**
 * BrandingContext
 *
 * Fetches per-organization branding from /api/v1/branding on mount (when the
 * user is authenticated) and applies it as CSS custom properties on
 * document.documentElement so every component can consume brand colors via
 * var(--brand-primary) etc.
 *
 * It also keeps document.title and the favicon in sync with the org config.
 *
 * Usage:
 *   const { brandName, primaryColor, logoUrl, loading } = useBranding();
 */

import React, { createContext, useContext, useState, useEffect, useMemo } from 'react';
import { getAuthHeaders } from '../utils/auth';
import { API_BASE_URL } from '../services/api';

// ─── Defaults (match current Perennia AI branding so nothing changes for ────
// orgs without a WhiteLabelConfig)
const DEFAULTS = {
  brandName: 'Perennia AI',
  logoUrl: null,
  faviconUrl: null,
  primaryColor: '#218d8d',
  secondaryColor: '#7c3aed',
  accentColor: '#059669',
  headerBgColor: '#ffffff',
  fontFamily: 'Inter, sans-serif',
};

const BrandingContext = createContext(null);

/**
 * Apply CSS custom properties to :root so all components can use
 * var(--brand-primary), var(--brand-secondary), etc.
 */
function applyCSSVars(config) {
  const root = document.documentElement;
  root.style.setProperty('--brand-primary', config.primaryColor);
  root.style.setProperty('--brand-secondary', config.secondaryColor);
  root.style.setProperty('--brand-accent', config.accentColor);
  root.style.setProperty('--brand-header-bg', config.headerBgColor);
  root.style.setProperty('--brand-font', config.fontFamily);
}

/**
 * Update the favicon <link> element if a custom favicon URL was provided.
 */
function updateFavicon(faviconUrl) {
  if (!faviconUrl) return;
  let link = document.querySelector("link[rel~='icon']");
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  link.href = faviconUrl;
}

export const BrandingProvider = ({ children }) => {
  const [branding, setBranding] = useState(DEFAULTS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Only fetch when a token is present (authenticated session)
    const token = localStorage.getItem('token');
    if (!token) {
      // Apply defaults so CSS vars are always defined
      applyCSSVars(DEFAULTS);
      setLoading(false);
      return;
    }

    let cancelled = false;

    const fetchBranding = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/branding`, {
          headers: getAuthHeaders(),
        });

        if (cancelled) return;

        if (!response.ok) {
          // Non-2xx — silently use defaults (do NOT redirect; auth errors are
          // handled by PermissionContext / ModuleContext already)
          applyCSSVars(DEFAULTS);
          setLoading(false);
          return;
        }

        const data = await response.json();

        const resolved = {
          brandName: data.company_name || DEFAULTS.brandName,
          logoUrl: data.logo_url || null,
          faviconUrl: data.favicon_url || null,
          primaryColor: data.primary_color || DEFAULTS.primaryColor,
          secondaryColor: data.secondary_color || DEFAULTS.secondaryColor,
          accentColor: data.accent_color || DEFAULTS.accentColor,
          headerBgColor: data.header_bg_color || DEFAULTS.headerBgColor,
          fontFamily: data.font_family || DEFAULTS.fontFamily,
        };

        setBranding(resolved);
        applyCSSVars(resolved);
        updateFavicon(resolved.faviconUrl);

        // Update document title (e.g. "Acme Lending | Perennia AI")
        if (resolved.brandName && resolved.brandName !== DEFAULTS.brandName) {
          document.title = resolved.brandName;
        }
      } catch (err) {
        if (!cancelled) {
          // Network errors — fall back to defaults silently
          console.warn('[BrandingContext] Could not fetch branding config:', err.message);
          applyCSSVars(DEFAULTS);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchBranding();

    // Re-fetch when the user logs in / out in the same tab
    const handleAuthChange = (e) => {
      if (e.detail?.type === 'login') {
        fetchBranding();
      } else if (e.detail?.type === 'logout') {
        setBranding(DEFAULTS);
        applyCSSVars(DEFAULTS);
      }
    };
    window.addEventListener('authChange', handleAuthChange);

    return () => {
      cancelled = true;
      window.removeEventListener('authChange', handleAuthChange);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const value = useMemo(
    () => ({ ...branding, loading }),
    [branding, loading]
  );

  return (
    <BrandingContext.Provider value={value}>
      {children}
    </BrandingContext.Provider>
  );
};

/**
 * Hook to consume branding values.
 * Returns: { brandName, logoUrl, faviconUrl, primaryColor, secondaryColor,
 *            accentColor, headerBgColor, fontFamily, loading }
 */
export const useBranding = () => {
  const ctx = useContext(BrandingContext);
  if (!ctx) {
    throw new Error('useBranding must be used within a BrandingProvider');
  }
  return ctx;
};

export default BrandingContext;
