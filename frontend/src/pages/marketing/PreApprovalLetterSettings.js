import React from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import PreApprovalLetterSettings from '../../components/PreApprovalLetterSettings';
import './MarketingSettings.css';

function PreApprovalLetterSettingsPage() {
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
      <PreApprovalLetterSettings />
    </div>
  );
}

export default PreApprovalLetterSettingsPage;
