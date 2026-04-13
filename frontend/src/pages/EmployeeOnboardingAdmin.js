import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import InviteManagementTable from '../components/admin/InviteManagementTable';
import EmployeeInviteWizard from '../components/admin/EmployeeInviteWizard';
import './EmployeeOnboardingAdmin.css';

function EmployeeOnboardingAdmin() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - only admins/managers can onboard employees
  const canAccessOnboarding = isAdmin || hasAnyPermission(['admin.manage', 'team.manage', 'users.manage', 'system.admin']) ||
    userRole === 'admin' || userRole === 'site_admin' || userRole === 'management';

  const [showWizard, setShowWizard] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleOpenWizard = () => {
    setShowWizard(true);
  };

  const handleCloseWizard = () => {
    setShowWizard(false);
  };

  const handleWizardComplete = () => {
    setShowWizard(false);
    // Trigger table refresh
    setRefreshKey(prev => prev + 1);
  };

  // Access denied if user doesn't have admin permissions
  if (!canAccessOnboarding) {
    return (
      <div className="employee-onboarding-admin">
        <div style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Employee Onboarding.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')} style={{ marginTop: '16px' }}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="employee-onboarding-admin">
      {/* Header */}
      <div className="page-header">
        <div className="header-content">
          <h1>Employee Onboarding</h1>
          <p>Invite new team members and manage their access permissions</p>
        </div>
        <button className="header-action-btn" onClick={handleOpenWizard}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
            <circle cx="8.5" cy="7" r="4" />
            <path d="M20 8v6M23 11h-6" />
          </svg>
          Invite Employee
        </button>
      </div>

      {/* Main Content */}
      <InviteManagementTable
        key={refreshKey}
        onInviteNew={handleOpenWizard}
      />

      {/* Wizard Modal */}
      {showWizard && (
        <div className="wizard-modal-overlay" onClick={handleCloseWizard}>
          <div className="wizard-modal-content" onClick={e => e.stopPropagation()}>
            <EmployeeInviteWizard
              onComplete={handleWizardComplete}
              onCancel={handleCloseWizard}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default EmployeeOnboardingAdmin;
