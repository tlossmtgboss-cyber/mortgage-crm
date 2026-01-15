import React from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import './MarketingSettings.css';

function LandingPagesSettings() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessMarketing = isAdmin || hasAnyPermission(['marketing.view', 'marketing.manage', 'admin.manage']) || userRole === 'admin' || userRole === 'sales' || userRole === 'loan_officer';

  const landingPages = [
    {
      id: 1,
      name: 'Mortgage Planning Questionnaire',
      description: 'Detailed questionnaire for mortgage planning',
      path: '/questionnaire',
      status: 'active'
    },
    {
      id: 2,
      name: 'Estimate Comparison',
      description: 'Compare loan estimates from different lenders',
      path: '/estimate-comparison',
      status: 'active'
    },
    {
      id: 3,
      name: 'Purchase Application',
      description: 'Full mortgage application for home purchase',
      path: '/apply/purchase',
      status: 'active'
    },
    {
      id: 4,
      name: 'Refinance Application',
      description: 'Full mortgage application for refinancing',
      path: '/apply/refinance',
      status: 'active'
    }
  ];

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
        <h2>Active Landing Pages</h2>
        <p>Landing pages for lead generation</p>
      </div>

      <div className="landing-pages-grid">
        {landingPages.map((page) => (
          <div key={page.id} className="landing-page-card">
            <div className="card-header">
              <h4>{page.name}</h4>
              <span className={`status-badge ${page.status}`}>
                {page.status === 'active' ? 'Active' : 'Inactive'}
              </span>
            </div>
            <p className="card-description">{page.description}</p>
            <div className="card-actions">
              <button
                className="btn-primary"
                onClick={() => navigate(page.path)}
              >
                View Page
              </button>
              <button
                className="btn-secondary"
                onClick={() => window.open(page.path, '_blank')}
              >
                ↗
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="add-page-section">
        <button className="btn-add">
          + Create New Landing Page
        </button>
      </div>
    </div>
  );
}

export default LandingPagesSettings;
