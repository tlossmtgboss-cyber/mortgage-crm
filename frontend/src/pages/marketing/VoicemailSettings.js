import React from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import './MarketingSettings.css';

function VoicemailSettings() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessMarketing = isAdmin || hasAnyPermission(['marketing.view', 'marketing.manage', 'admin.manage']) || userRole === 'admin' || userRole === 'sales' || userRole === 'loan_officer';

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
        <h2>Voicemail Drops</h2>
        <p>Create and manage ringless voicemail campaigns</p>
      </div>

      <div className="empty-state">
        <div className="icon">🎙️</div>
        <h4>Voicemail Templates Coming Soon</h4>
        <p>
          Record voicemail templates for ringless voicemail drops and automated outreach
        </p>
        <button className="btn-add">
          + Record Voicemail
        </button>
      </div>
    </div>
  );
}

export default VoicemailSettings;
