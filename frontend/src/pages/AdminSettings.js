import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import { toast } from '../utils/toast';
import './AdminSettings.css';
import { getToken } from '../utils/tokenStore';

const AdminSettings = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - require admin access
  const canAccessAdminSettings = isAdmin || hasAnyPermission(['admin.manage', 'settings.manage', 'system.admin']) || userRole === 'admin';

  const [running, setRunning] = useState({});
  const [results, setResults] = useState({});

  const runJob = async (jobType) => {
    setRunning({ ...running, [jobType]: true });
    try {
      const token = getToken();
      const response = await fetch(
        `${API_BASE_URL}/api/v1/admin/certification-jobs/${jobType}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          }
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to run job: ${response.statusText}`);
      }

      const data = await response.json();
      setResults({
        ...results,
        [jobType]: {
          success: true,
          ...data
        }
      });
      toast.success(`${jobType === 'create' ? 'Certifications created' : 'Reminders sent'} successfully`);
    } catch (err) {
      setResults({
        ...results,
        [jobType]: {
          success: false,
          error: err.message
        }
      });
      toast.error(`Failed to run ${jobType} job: ${err.message}`);
    } finally {
      setRunning({ ...running, [jobType]: false });
    }
  };

  // Access denied if user doesn't have admin permissions
  if (!canAccessAdminSettings) {
    return (
      <div className="admin-settings-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Admin Settings.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-settings-page">
      <div className="page-header">
        <h1>Admin Settings</h1>
        <p>System administration and maintenance tools</p>
      </div>

      {/* Certification Jobs */}
      <section className="settings-section">
        <h2>Access Certification Jobs</h2>
        <p className="section-description">
          Manually trigger certification creation and reminder notifications.
          These should be automated via scheduled jobs in production.
        </p>

        <div className="jobs-grid">
          {/* Create Certifications */}
          <div className="job-card">
            <div className="job-header">
              <h3>Create Quarterly Certifications</h3>
              <span className="frequency-badge">Run Quarterly</span>
            </div>
            <div className="job-body">
              <p>
                Creates access certification records for all active employees for the current quarter.
                Run this at the start of each quarter (Q1, Q2, Q3, Q4).
              </p>
              <ul className="job-details">
                <li>Recommended: January 1, April 1, July 1, October 1</li>
                <li>Creates certifications for all active employees</li>
                <li>Sets due date 90 days from creation</li>
                <li>Skips employees who already have a certification for this quarter</li>
              </ul>
            </div>
            <div className="job-actions">
              <button
                onClick={() => runJob('create')}
                disabled={running.create}
                className="btn-primary"
              >
                {running.create ? 'Creating...' : 'Create Certifications'}
              </button>
            </div>
            {results.create && (
              <div className={`job-result ${results.create.success ? 'success' : 'error'}`}>
                {results.create.success ? (
                  <>
                    <strong>✓ Success!</strong>
                    <p>Created {results.create.created} certifications for {results.create.quarter}</p>
                    {results.create.skipped > 0 && (
                      <p>Skipped {results.create.skipped} (already exist)</p>
                    )}
                  </>
                ) : (
                  <>
                    <strong>✗ Error</strong>
                    <p>{results.create.error}</p>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Send Reminders */}
          <div className="job-card">
            <div className="job-header">
              <h3>Send Certification Reminders</h3>
              <span className="frequency-badge">Run Daily</span>
            </div>
            <div className="job-body">
              <p>
                Sends reminder notifications to managers about upcoming and overdue certifications.
                Should run daily, typically in the morning.
              </p>
              <ul className="job-details">
                <li>Recommended: Daily at 9:00 AM</li>
                <li>Sends 30-day advance reminders</li>
                <li>Sends 7-day advance reminders</li>
                <li>Sends overdue notifications with escalation</li>
              </ul>
            </div>
            <div className="job-actions">
              <button
                onClick={() => runJob('reminders')}
                disabled={running.reminders}
                className="btn-primary"
              >
                {running.reminders ? 'Sending...' : 'Send Reminders'}
              </button>
            </div>
            {results.reminders && (
              <div className={`job-result ${results.reminders.success ? 'success' : 'error'}`}>
                {results.reminders.success ? (
                  <>
                    <strong>✓ Success!</strong>
                    <p>
                      Sent {results.reminders.reminders_30d || 0} 30-day reminders, {' '}
                      {results.reminders.reminders_7d || 0} 7-day reminders, {' '}
                      {results.reminders.overdue || 0} overdue notifications
                    </p>
                  </>
                ) : (
                  <>
                    <strong>✗ Error</strong>
                    <p>{results.reminders.error}</p>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Future: Other Admin Tools */}
      <section className="settings-section">
        <h2>System Maintenance</h2>
        <p className="section-description coming-soon">
          Additional admin tools coming soon: Database backup, cache clearing,
          user cleanup, permission audits, etc.
        </p>
      </section>
    </div>
  );
};

export default AdminSettings;
