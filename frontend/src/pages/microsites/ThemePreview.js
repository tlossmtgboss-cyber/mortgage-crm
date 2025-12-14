/**
 * ThemePreview - Preview Theme with Sample Data
 *
 * This component renders a theme with sample demo data so users can
 * preview what each theme looks like before selecting it.
 */

import React, { useState, useEffect, Suspense, lazy } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';

// API base URL
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

// Lazy load theme components
const themeComponents = {
  LeadPopsCardinal: lazy(() => import('./themes/LeadPopsCardinal')),
  ProfessionalClean: lazy(() => import('./themes/ProfessionalClean')),
  ModernGradient: lazy(() => import('./themes/ModernGradient')),
  MinimalFocus: lazy(() => import('./themes/MinimalFocus')),
};

// Sample demo data for previewing themes
const DEMO_USER = {
  id: 0,
  name: 'Sarah Johnson',
  email: 'sarah.johnson@example.com',
  phone: '(555) 123-4567',
  nmls_id: '123456',
  photo_url: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=400&h=400&fit=crop&crop=faces',
  avatar_url: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=400&h=400&fit=crop&crop=faces',
  bio: 'Dedicated mortgage professional with over 15 years of experience helping families achieve their homeownership dreams.',
  slug: 'sarah-johnson',
  company: 'Perennia Mortgage'
};

const DEMO_PROFILE = {
  headline: 'Your Trusted Mortgage Expert',
  tagline: 'Making homeownership dreams a reality since 2009',
  bioExtended: 'With over 15 years of experience in the mortgage industry, I\'ve helped thousands of families navigate the home buying process. My approach is simple: treat every client like family, provide honest guidance, and work tirelessly to find the best loan solution for your unique situation. Whether you\'re a first-time homebuyer or looking to refinance, I\'m here to help you every step of the way.',
  heroImageUrl: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=400&h=400&fit=crop&crop=faces',
  yearsExperience: 15,
  totalLoansFunded: 2500,
  totalVolumeFunded: 850000000,
  specialties: [
    'First-Time Homebuyers',
    'VA Loans',
    'FHA Loans',
    'Jumbo Loans',
    'Investment Properties',
    'Refinancing'
  ],
  certifications: ['CMPS', 'FHA Direct Endorsed', 'VA Automatic'],
  testimonials: [
    {
      name: 'Michael & Jennifer R.',
      text: 'Sarah made our first home purchase so easy! She explained everything clearly and was always available to answer our questions. We couldn\'t have asked for a better experience.',
      rating: 5,
      date: 'November 2024'
    },
    {
      name: 'David T.',
      text: 'Exceptional service from start to finish. Sarah found us a great rate and closed on time. Highly recommend!',
      rating: 5,
      date: 'October 2024'
    },
    {
      name: 'Lisa M.',
      text: 'Sarah helped us refinance and saved us over $400 a month. She really knows her stuff and genuinely cares about her clients.',
      rating: 5,
      date: 'September 2024'
    }
  ],
  socialLinks: {
    linkedin: 'https://linkedin.com/in/example',
    facebook: 'https://facebook.com/example',
    instagram: 'https://instagram.com/example'
  },
  calendlyUrl: 'https://calendly.com/example',
  contactFormEnabled: true,
  showPhone: true,
  showEmail: true,
  ctaText: 'Get Your Free Quote',
  ctaSecondaryText: 'Check Today\'s Rates'
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
    <h2 style={{ margin: '0 0 8px', color: '#111827' }}>Theme Not Found</h2>
    <p style={{ margin: 0, color: '#6b7280' }}>{message || 'The theme you\'re looking for doesn\'t exist.'}</p>
  </div>
);

// Preview banner component
const PreviewBanner = ({ themeName, onClose }) => (
  <div style={{
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    background: 'linear-gradient(90deg, #c9a227, #d4af37)',
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
      <span style={{ opacity: 0.9 }}>— {themeName}</span>
    </div>
    <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
      <span style={{ fontSize: '14px', opacity: 0.9 }}>
        This is sample data. Your actual profile will be displayed when selected.
      </span>
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
  </div>
);

const ThemePreview = () => {
  const { themeSlug } = useParams();
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [themeData, setThemeData] = useState(null);

  useEffect(() => {
    fetchThemeData();
  }, [themeSlug]);

  const fetchThemeData = async () => {
    try {
      // Fetch theme details from API
      const response = await fetch(`${API_BASE}/api/v1/public/themes`);

      if (response.ok) {
        const data = await response.json();
        // Find the theme by slug
        const theme = data.themes?.find(t => t.slug === themeSlug);

        if (theme) {
          setThemeData(theme);
        } else {
          setError(`Theme "${themeSlug}" not found`);
        }
      } else {
        throw new Error('Failed to load themes');
      }
    } catch (err) {
      console.error('Error fetching theme:', err);
      setError('Unable to load theme preview');
    } finally {
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

  if (!themeData) {
    return <ErrorState message="Theme data not available" />;
  }

  // Get the theme component
  const componentName = themeData.componentName || 'LeadPopsCardinal';
  const ThemeComponent = themeComponents[componentName];

  if (!ThemeComponent) {
    return <ErrorState message={`Theme component "${componentName}" not implemented yet`} />;
  }

  // Build theme config from URL params or defaults
  const themeConfig = {
    primaryColor: searchParams.get('primaryColor') || themeData.defaultConfig?.primaryColor,
    secondaryColor: searchParams.get('secondaryColor') || themeData.defaultConfig?.secondaryColor,
    ...themeData.defaultConfig
  };

  return (
    <>
      <PreviewBanner themeName={themeData.name} onClose={handleClose} />
      <div style={{ paddingTop: '52px' }}>
        <Suspense fallback={<LoadingState />}>
          <ThemeComponent
            user={DEMO_USER}
            profile={DEMO_PROFILE}
            themeConfig={themeConfig}
          />
        </Suspense>
      </div>
    </>
  );
};

export default ThemePreview;
