import React, { useState } from 'react';
import InviteManagementTable from '../components/admin/InviteManagementTable';
import EmployeeInviteWizard from '../components/admin/EmployeeInviteWizard';
import './EmployeeOnboardingAdmin.css';

function EmployeeOnboardingAdmin() {
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
