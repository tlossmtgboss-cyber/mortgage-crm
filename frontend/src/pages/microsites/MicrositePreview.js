/**
 * MicrositePreview - Preview the current user's microsite
 *
 * This component fetches the logged-in user's microsite settings
 * and renders a preview of their configured theme.
 */

import React, { useState, useEffect, Suspense, lazy } from 'react';
import { getToken } from '../../utils/tokenStore';

// API base URL
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

// Lazy load theme components
const themeComponents = {
  BoldImpact: lazy(() => import('./themes/BoldImpact')),
  ProfessionalClean: lazy(() => import('./themes/ProfessionalClean')),
  ModernGradient: lazy(() => import('./themes/ModernGradient')),
  MinimalFocus: lazy(() => import('./themes/MinimalFocus')),
  LOMicrosite: lazy(() => import('./LOMicrosite')),
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
      borderTopColor: '#1F3D2E',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite'
    }} />
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    <p style={{ marginTop: '16px', color: '#6b7280' }}>Loading preview...</p>
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
    <h2 style={{ margin: '0 0 8px', color: '#111827' }}>Unable to Load Preview</h2>
    <p style={{ margin: 0, color: '#6b7280' }}>{message}</p>
    <button
      onClick={() => window.close()}
      style={{
        marginTop: '24px',
        padding: '10px 20px',
        background: '#1F3D2E',
        color: 'white',
        border: 'none',
        borderRadius: '6px',
        cursor: 'pointer',
        fontWeight: 500
      }}
    >
      Close
    </button>
  </div>
);

// Preview banner component
const PreviewBanner = ({ onClose }) => (
  <div style={{
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    background: 'linear-gradient(90deg, #1F3D2E, #1a6670)',
    color: 'white',
    padding: '12px 24px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    zIndex: 10000,
    boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
    fontFamily: 'Inter, -apple-system, sans-serif'
  }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <span style={{ fontSize: '18px' }}>👁️</span>
      <span style={{ fontWeight: 600 }}>Preview Mode</span>
      <span style={{ opacity: 0.9 }}>— This is how your microsite will appear to visitors</span>
    </div>
    <button
      onClick={onClose}
      style={{
        background: 'rgba(255,255,255,0.2)',
        border: 'none',
        color: 'white',
        padding: '8px 16px',
        borderRadius: '6px',
        cursor: 'pointer',
        fontWeight: 500,
        fontSize: '14px'
      }}
    >
      Close Preview
    </button>
  </div>
);

const MicrositePreview = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [micrositeData, setMicrositeData] = useState(null);
  const [userData, setUserData] = useState(null);

  useEffect(() => {
    fetchMicrositeData();
  }, []);

  const fetchMicrositeData = async () => {
    try {
      const token = getToken();

      if (!token) {
        setError('Please log in to preview your microsite');
        setLoading(false);
        return;
      }

      // Fetch user's microsite settings
      const response = await fetch(`${API_BASE}/api/v1/microsites/my-microsite`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) {
        if (response.status === 404) {
          setError('You haven\'t set up your microsite yet. Please configure it in Settings first.');
        } else {
          throw new Error('Failed to load microsite data');
        }
        setLoading(false);
        return;
      }

      const data = await response.json();
      setMicrositeData(data);

      // Also fetch user profile data
      const userResponse = await fetch(`${API_BASE}/api/v1/auth/profile`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (userResponse.ok) {
        const userData = await userResponse.json();
        setUserData(userData);
      }

      setLoading(false);
    } catch (err) {
      console.error('Error fetching microsite data:', err);
      setError('Unable to load your microsite preview. Please try again.');
      setLoading(false);
    }
  };

  const handleClose = () => {
    window.close();
  };

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} />;
  }

  if (!micrositeData) {
    return <ErrorState message="No microsite data available" />;
  }

  // Determine which theme component to use
  const themeName = micrositeData.theme_name || micrositeData.themeName || 'BoldImpact';
  const ThemeComponent = themeComponents[themeName] || themeComponents.BoldImpact;

  // Build user object for theme
  const user = {
    id: userData?.id || 0,
    name: userData?.full_name || userData?.name || 'Your Name',
    email: userData?.email || '',
    phone: userData?.phone || micrositeData.phone || '',
    nmls_id: userData?.nmls_id || micrositeData.nmls_id || '',
    photo_url: userData?.photo_url || micrositeData.photo_url || '',
    avatar_url: userData?.avatar_url || micrositeData.photo_url || '',
    bio: micrositeData.bio || '',
    slug: micrositeData.slug || '',
    company: micrositeData.company_name || 'Your Company'
  };

  // Extract branding data (where uploaded images are stored)
  const branding = micrositeData.branding_json || {};

  // Build profile object for theme
  const profile = {
    headline: micrositeData.headline || '',
    tagline: micrositeData.tagline || '',
    bioExtended: micrositeData.bio_extended || micrositeData.bio || '',
    heroImageUrl: branding.heroImageUrl || micrositeData.hero_image_url || micrositeData.photo_url || '',
    logoUrl: branding.logoUrl || micrositeData.logo_url || '',
    yearsExperience: micrositeData.years_experience || 0,
    totalLoansFunded: micrositeData.total_loans_funded || 0,
    totalVolumeFunded: micrositeData.total_volume_funded || 0,
    specialties: micrositeData.specialties || [],
    certifications: micrositeData.certifications || [],
    testimonials: micrositeData.testimonials || [],
    socialLinks: micrositeData.social_links || {},
    calendlyUrl: micrositeData.calendly_url || '',
    contactFormEnabled: micrositeData.contact_form_enabled !== false,
    showPhone: micrositeData.show_phone !== false,
    showEmail: micrositeData.show_email !== false,
    ctaText: micrositeData.cta_text || 'Get Started',
    ctaSecondaryText: micrositeData.cta_secondary_text || ''
  };

  // Theme config
  const themeConfig = micrositeData.theme_config || micrositeData.themeConfig || {};

  return (
    <Suspense fallback={<LoadingState />}>
      <PreviewBanner onClose={handleClose} />
      <div style={{ paddingTop: '52px' }}>
        <ThemeComponent
          user={user}
          profile={profile}
          themeConfig={themeConfig}
        />
      </div>
    </Suspense>
  );
};

export default MicrositePreview;
