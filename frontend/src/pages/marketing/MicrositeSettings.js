import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import MicrositeThemeSelector from '../../components/MicrositeThemeSelector';
import './MarketingSettings.css';
import { getUserData } from '../../utils/tokenStore';

function MicrositeSettings() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessMarketing = isAdmin || hasAnyPermission(['marketing.view', 'marketing.manage', 'admin.manage']) || userRole === 'admin' || userRole === 'sales' || userRole === 'loan_officer';
  const [userProfile, setUserProfile] = useState({});
  const [message, setMessage] = useState({ type: '', text: '' });

  useEffect(() => {
    // Load user profile from localStorage
    try {
      const user = JSON.parse(getUserData() || '{}');
      setUserProfile(user);
    } catch (e) {
      console.error('Error loading user profile:', e);
    }
  }, []);

  const copyUrl = () => {
    const url = `${window.location.origin}/lo/${userProfile.slug || userProfile.id || ''}`;
    navigator.clipboard.writeText(url);
    setMessage({ type: 'success', text: 'URL copied to clipboard!' });
    setTimeout(() => setMessage({ type: '', text: '' }), 3000);
  };

  const shareOnLinkedIn = () => {
    const url = `${window.location.origin}/lo/${userProfile.slug || userProfile.id || ''}`;
    window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}`, '_blank');
  };

  const shareViaEmail = () => {
    const url = `${window.location.origin}/lo/${userProfile.slug || userProfile.id || ''}`;
    const subject = encodeURIComponent('Your Trusted Loan Officer');
    const body = encodeURIComponent(`Hi,\n\nI wanted to share my loan officer page with you:\n\n${url}\n\nLooking forward to helping you!`);
    window.location.href = `mailto:?subject=${subject}&body=${body}`;
  };

  if (!canAccessMarketing) {
    return (
      <div className="marketing-settings-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Marketing Settings.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="marketing-settings-page">
      <div className="settings-header">
        <h2>Microsite Builder</h2>
        <p>Customize your personal marketing microsite</p>
      </div>

      {/* Microsite URL Banner */}
      <div className="microsite-banner">
        <h3>Your Microsite URL</h3>
        <div className="microsite-url-box">
          <code>
            {window.location.origin}/lo/{userProfile.slug || userProfile.id || 'your-name'}
          </code>
          <button className="btn-copy" onClick={copyUrl}>
            Copy URL
          </button>
        </div>
      </div>

      {message.text && (
        <div className={`message ${message.type}`} style={{
          padding: '12px 16px',
          borderRadius: '8px',
          marginBottom: '20px',
          background: message.type === 'success' ? '#d1fae5' : '#fee2e2',
          color: message.type === 'success' ? '#065f46' : '#991b1b'
        }}>
          {message.text}
        </div>
      )}

      {/* Quick Actions */}
      <div className="quick-actions-grid">
        <button
          className="quick-action-btn"
          onClick={() => window.open(`/lo/${userProfile.slug || userProfile.id || ''}`, '_blank')}
        >
          <span>👁️</span> Preview Microsite
        </button>
        <button className="quick-action-btn linkedin" onClick={shareOnLinkedIn}>
          <span>🔗</span> Share on LinkedIn
        </button>
        <button className="quick-action-btn email" onClick={shareViaEmail}>
          <span>✉️</span> Share via Email
        </button>
      </div>

      {/* Theme Selector */}
      <MicrositeThemeSelector />
    </div>
  );
}

export default MicrositeSettings;
