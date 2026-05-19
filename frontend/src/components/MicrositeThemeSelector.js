/**
 * MicrositeThemeSelector - Microsite Customization Component
 *
 * Single template design based on the master template at /lo/tim-loss
 * Allows users to customize colors and content for their microsite.
 */

import React, { useState, useEffect } from 'react';
import api from '../services/api';
import './MicrositeThemeSelector.css';
import MicrositeThemeCustomizer from './MicrositeThemeCustomizer';

const MicrositeThemeSelector = ({ onThemeSelect }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [microsite, setMicrosite] = useState(null);
  const [saving, setSaving] = useState(false);
  const [userSlug, setUserSlug] = useState(null);
  const [showCustomizer, setShowCustomizer] = useState(false);
  const [themeConfig, setThemeConfig] = useState({});
  const [successMessage, setSuccessMessage] = useState('');

  useEffect(() => {
    fetchMicrosite();
    fetchUserSlug();
  }, []);

  const fetchMicrosite = async () => {
    try {
      const { data } = await api.get('/api/v1/microsites/my-microsite');
      setMicrosite(data);
      if (data.themeConfig) {
        setThemeConfig(data.themeConfig);
      }
    } catch (err) {
      console.error('Error fetching microsite:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchUserSlug = async () => {
    try {
      const { data } = await api.get('/api/v1/microsites/preview-url');
      setUserSlug(data.slug);
    } catch (err) {
      console.error('Error fetching user slug:', err);
    }
  };

  // Publish microsite
  const handlePublish = async () => {
    setSaving(true);
    try {
      await api.post('/api/v1/microsites/my-microsite/publish');
      await fetchMicrosite();
      setSuccessMessage('Microsite published successfully!');
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (err) {
      console.error('Error publishing:', err);
      setError(err.response?.data?.detail || 'Failed to publish microsite');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="theme-selector-loading">
        <div className="loading-spinner"></div>
        <p>Loading your microsite...</p>
      </div>
    );
  }

  return (
    <div className="theme-selector">
      {/* Success Message */}
      {successMessage && (
        <div style={{
          background: '#d1fae5',
          color: '#065f46',
          padding: '12px 20px',
          borderRadius: '8px',
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px'
        }}>
          <span>✓</span> {successMessage}
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div style={{
          background: '#fee2e2',
          color: '#991b1b',
          padding: '12px 20px',
          borderRadius: '8px',
          marginBottom: '20px'
        }}>
          {error}
          <button
            onClick={() => setError(null)}
            style={{ marginLeft: '12px', background: 'none', border: 'none', cursor: 'pointer' }}
          >
            ×
          </button>
        </div>
      )}

      {/* Header */}
      <div className="theme-selector-header" style={{ marginBottom: '24px' }}>
        <div className="header-content">
          <h2 style={{ margin: '0 0 8px 0', fontSize: '20px', fontWeight: '600' }}>Your Microsite</h2>
          <p style={{ margin: 0, color: '#6b7280', fontSize: '14px' }}>
            Customize your professional loan officer microsite
          </p>
        </div>
      </div>

      {/* Microsite Preview Card */}
      <div style={{
        background: '#fff',
        border: '1px solid #e5e7eb',
        borderRadius: '12px',
        overflow: 'hidden',
        marginBottom: '24px'
      }}>
        {/* Preview Header */}
        <div style={{
          background: 'linear-gradient(135deg, #1e3a5f 0%, #2d4a6f 100%)',
          padding: '32px',
          color: 'white',
          textAlign: 'center'
        }}>
          <div style={{
            width: '80px',
            height: '80px',
            background: 'rgba(255,255,255,0.2)',
            borderRadius: '50%',
            margin: '0 auto 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '32px'
          }}>
            🏠
          </div>
          <h3 style={{ margin: '0 0 8px 0', fontSize: '18px' }}>Professional Microsite Template</h3>
          <p style={{ margin: 0, opacity: 0.9, fontSize: '14px' }}>
            Clean, modern design optimized for lead generation
          </p>
        </div>

        {/* Features List */}
        <div style={{ padding: '24px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', marginBottom: '24px' }}>
            {[
              { icon: '👤', label: 'Professional Profile' },
              { icon: '📝', label: 'Lead Capture Form' },
              { icon: '🤖', label: 'AI Chat Assistant' },
              { icon: '📱', label: 'Mobile Responsive' },
              { icon: '🎨', label: 'Custom Colors' },
              { icon: '🔗', label: 'Social Links' },
            ].map((feature, idx) => (
              <div key={idx} style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 12px',
                background: '#f9fafb',
                borderRadius: '6px',
                fontSize: '14px'
              }}>
                <span>{feature.icon}</span>
                <span>{feature.label}</span>
              </div>
            ))}
          </div>

          {/* Action Buttons */}
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            {userSlug && (
              <a
                href={`/lo/${userSlug}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  flex: 1,
                  minWidth: '140px',
                  padding: '12px 20px',
                  background: '#c9a227',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '14px',
                  textDecoration: 'none',
                  textAlign: 'center',
                  display: 'inline-block'
                }}
              >
                View Live Microsite
              </a>
            )}
            <button
              onClick={() => setShowCustomizer(!showCustomizer)}
              style={{
                flex: 1,
                minWidth: '140px',
                padding: '12px 20px',
                background: showCustomizer ? '#374151' : '#f3f4f6',
                color: showCustomizer ? 'white' : '#374151',
                border: '1px solid #d1d5db',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: '500',
                fontSize: '14px'
              }}
            >
              {showCustomizer ? 'Hide Customizer' : 'Customize Site'}
            </button>
            {microsite && !microsite.isPublished && (
              <button
                onClick={handlePublish}
                disabled={saving}
                style={{
                  flex: 1,
                  minWidth: '140px',
                  padding: '12px 20px',
                  background: '#2D7A52',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  cursor: saving ? 'not-allowed' : 'pointer',
                  fontWeight: '600',
                  fontSize: '14px',
                  opacity: saving ? 0.7 : 1
                }}
              >
                {saving ? 'Publishing...' : 'Publish Microsite'}
              </button>
            )}
          </div>

          {/* Published Status */}
          {microsite && microsite.isPublished && (
            <div style={{
              marginTop: '16px',
              padding: '12px 16px',
              background: '#d1fae5',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              color: '#065f46',
              fontSize: '14px'
            }}>
              <span>✓</span>
              <span>Your microsite is live and published</span>
            </div>
          )}
        </div>
      </div>

      {/* Theme Customizer */}
      {showCustomizer && (
        <div style={{
          background: '#fff',
          border: '1px solid #e5e7eb',
          borderRadius: '12px',
          padding: '24px'
        }}>
          <MicrositeThemeCustomizer
            theme={{ id: 'default', name: 'Professional Template' }}
            currentConfig={themeConfig}
            onConfigChange={(newConfig) => setThemeConfig(newConfig)}
            onSave={(savedConfig) => {
              setThemeConfig(savedConfig);
              fetchMicrosite();
              setSuccessMessage('Customization saved!');
              setTimeout(() => setSuccessMessage(''), 3000);
            }}
          />
        </div>
      )}
    </div>
  );
};

export default MicrositeThemeSelector;
