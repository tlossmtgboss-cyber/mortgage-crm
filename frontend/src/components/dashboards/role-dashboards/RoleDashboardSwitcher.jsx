import React, { useState } from 'react';

export const RoleDashboardSwitcher = ({ currentView, onViewChange, isAdmin }) => {
  const [isOpen, setIsOpen] = useState(false);

  const roles = [
    { id: 'admin', label: 'Administrator', icon: '&#x1F3E2;' },
    { id: 'site_admin', label: 'Site Administrator', icon: '&#x1F527;' },
    { id: 'loan_officer', label: 'Loan Officer', icon: '&#x1F454;' },
    { id: 'production_assistant_1', label: 'Production Assistant 1', icon: '&#x1F4CA;' },
    { id: 'production_assistant_2', label: 'Production Assistant 2', icon: '&#x1F4C8;' },
    { id: 'concierge', label: 'Concierge', icon: '&#x1F6CE;&#xFE0F;' },
    { id: 'processor', label: 'Processor', icon: '&#x1F4C1;' },
    { id: 'underwriter', label: 'Underwriter', icon: '&#x1F50D;' },
    { id: 'closer', label: 'Closer', icon: '&#x1F4C5;' },
    { id: 'manager', label: 'Manager', icon: '&#x1F465;' },
    { id: 'executive', label: 'Executive', icon: '&#x1F3E2;' }
  ];

  const currentRole = roles.find(r => r.id === currentView) || roles[0];

  if (!isAdmin) return null;

  return (
    <div className="role-switcher">
      <button
        className="role-switcher-trigger"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="current-role-label">{currentRole.label}</span>
        <span className="dropdown-arrow">{isOpen ? '▲' : '▼'}</span>
      </button>

      {isOpen && (
        <div className="role-switcher-dropdown">
          {roles.map(role => (
            <button
              key={role.id}
              className={`role-option ${currentView === role.id ? 'active' : ''}`}
              onClick={() => {
                onViewChange(role.id);
                setIsOpen(false);
              }}
            >
              <span className="role-label">{role.label}</span>
              {currentView === role.id && <span className="check-mark">{'✓'}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
