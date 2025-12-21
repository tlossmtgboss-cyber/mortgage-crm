/**
 * ThemeRenderer - Dynamic Theme Loading Component
 *
 * This component fetches the microsite data from the API and renders
 * the appropriate theme based on the user's configuration.
 */

import React, { useState, useEffect, Suspense, lazy } from 'react';
import { useParams } from 'react-router-dom';

// API base URL
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

// Lazy load theme components with error handling
const themeComponents = {
  BoldImpact: lazy(() => import('./themes/BoldImpact').catch((err) => {
    console.error('Failed to load BoldImpact theme:', err);
    return import('./LOMicrosite');
  })),
  ProfessionalClean: lazy(() => import('./themes/ProfessionalClean').catch(() => ({ default: FallbackTheme }))),
  ModernGradient: lazy(() => import('./themes/ModernGradient').catch(() => ({ default: FallbackTheme }))),
  MinimalFocus: lazy(() => import('./themes/MinimalFocus').catch(() => ({ default: FallbackTheme }))),
  // Default fallback to LOMicrosite
  LOMicrosite: lazy(() => import('./LOMicrosite')),
};

// Fallback theme for themes not yet implemented
const FallbackTheme = ({ user, profile, themeConfig }) => {
  // Import and render the legacy LOMicrosite as fallback
  const LegacyMicrosite = lazy(() => import('./LOMicrosite'));
  return (
    <Suspense fallback={<LoadingState />}>
      <LegacyMicrosite />
    </Suspense>
  );
};

// Loading state component
const LoadingState = () => (
  <div style={{
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    background: '#f9fafb',
    fontFamily: 'Inter, -apple-system, sans-serif'
  }}>
    <div style={{
      width: '48px',
      height: '48px',
      border: '3px solid #e5e7eb',
      borderTopColor: '#c9a227',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite'
    }} />
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    <p style={{ marginTop: '16px', color: '#6b7280' }}>Loading...</p>
  </div>
);

// Error state component
const ErrorState = ({ message }) => (
  <div style={{
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    background: '#f9fafb',
    fontFamily: 'Inter, -apple-system, sans-serif',
    padding: '24px',
    textAlign: 'center'
  }}>
    <div style={{ fontSize: '48px', marginBottom: '16px' }}>😕</div>
    <h2 style={{ margin: '0 0 8px', color: '#111827' }}>Page Not Found</h2>
    <p style={{ margin: 0, color: '#6b7280' }}>{message || 'The loan officer profile you\'re looking for doesn\'t exist.'}</p>
  </div>
);

const ThemeRenderer = () => {
  const { slug, userId, pageSlug } = useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [micrositeData, setMicrositeData] = useState(null);
  const [pages, setPages] = useState([]);

  useEffect(() => {
    fetchMicrositeData();
    fetchPages();
  }, [slug, userId]);

  const fetchMicrositeData = async () => {
    try {
      const identifier = slug || userId;

      if (!identifier) {
        setError('No loan officer specified');
        setLoading(false);
        return;
      }

      // Fetch public microsite data
      const response = await fetch(`${API_BASE}/api/v1/public/themes/render/${identifier}`);

      if (response.ok) {
        const data = await response.json();
        setMicrositeData(data);
      } else if (response.status === 404) {
        setError('Loan officer profile not found');
      } else {
        throw new Error('Failed to load microsite');
      }
    } catch (err) {
      console.error('Error fetching microsite data:', err);
      setError('Unable to load this page');
    } finally {
      setLoading(false);
    }
  };

  const fetchPages = async () => {
    try {
      const identifier = slug || userId;
      if (!identifier) return;

      const response = await fetch(`${API_BASE}/api/v1/public/themes/render/${identifier}/pages`);
      if (response.ok) {
        const data = await response.json();
        setPages(data.pages || []);
      }
    } catch (err) {
      console.error('Error fetching pages:', err);
    }
  };

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} />;
  }

  if (!micrositeData) {
    return <ErrorState message="Microsite data not available" />;
  }

  // Determine which theme component to render
  const { theme, themeConfig, profile, user } = micrositeData;
  const componentName = theme?.componentName || 'LOMicrosite';

  // Get the theme component
  const ThemeComponent = themeComponents[componentName] || themeComponents.LOMicrosite;

  return (
    <Suspense fallback={<LoadingState />}>
      <ThemeComponent
        user={user}
        profile={profile}
        themeConfig={themeConfig}
        pages={pages}
        activePage={pageSlug || 'home'}
      />
    </Suspense>
  );
};

export default ThemeRenderer;
