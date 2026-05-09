import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import api from '../../services/api';
import { toast } from '../../utils/toast';
import './MarketingSettings.css';

function POSSettings() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccess = isAdmin || hasAnyPermission(['marketing.view', 'marketing.manage', 'admin.manage']) || userRole === 'admin' || userRole === 'sales' || userRole === 'loan_officer';

  const [team, setTeam] = useState([]);
  const [calendarAssignment, setCalendarAssignment] = useState(null);
  const [orgSlug, setOrgSlug] = useState('');
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [teamRes, settingsRes] = await Promise.allSettled([
        api.get('/api/v1/settings/team-roles'),
        api.get('/api/v1/pos/settings'),
      ]);

      if (teamRes.status === 'fulfilled') {
        const assignments = teamRes.value?.data?.assignments || [];
        const members = assignments
          .filter(a => a.user_id)
          .reduce((acc, a) => {
            const existing = acc.find(m => m.user_id === a.user_id);
            if (existing) {
              existing.roles.push(a.role_name);
            } else {
              acc.push({
                user_id: a.user_id,
                name: a.user_name,
                email: a.user_email,
                roles: [a.role_name],
              });
            }
            return acc;
          }, []);
        setTeam(members);
      }

      if (settingsRes.status === 'fulfilled') {
        const data = settingsRes.value?.data;
        if (data?.org_slug) setOrgSlug(data.org_slug);
        if (data?.calendar_user) setCalendarAssignment(data.calendar_user);
      }
    } catch {
      // individual failures handled above via allSettled
    } finally {
      setLoading(false);
    }
  };

  const posUrl = orgSlug
    ? `${window.location.origin}/apply/v3/purchase?lo=${orgSlug}`
    : `${window.location.origin}/apply/v3/purchase`;

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(posUrl).then(() => {
      setCopied(true);
      toast.success('Application link copied');
      setTimeout(() => setCopied(false), 2000);
    });
  }, [posUrl]);

  if (!canAccess) {
    return (
      <div className="marketing-settings-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access POS Settings.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="pos-settings">
      {/* Application Link */}
      <section className="pos-settings__section">
        <h2 className="pos-settings__heading">Application Link</h2>
        <p className="pos-settings__desc">
          Share this link with borrowers to start a loan application. The application is associated with your team.
        </p>
        <div className="pos-settings__link-box">
          <input
            type="text"
            readOnly
            value={posUrl}
            className="pos-settings__link-input"
            onClick={e => e.target.select()}
          />
          <button
            type="button"
            className="pos-settings__copy-btn"
            onClick={handleCopy}
          >
            {copied ? 'Copied' : 'Copy Link'}
          </button>
        </div>
      </section>

      {/* Team Members */}
      <section className="pos-settings__section">
        <div className="pos-settings__section-header">
          <div>
            <h2 className="pos-settings__heading">Team Members</h2>
            <p className="pos-settings__desc">
              These team members are visible to borrowers on their application portal. Manage assignments in{' '}
              <button
                type="button"
                className="pos-settings__link-btn"
                onClick={() => navigate('/settings?tab=team-roles')}
              >
                Team Settings
              </button>.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="pos-settings__loading">Loading team...</div>
        ) : team.length === 0 ? (
          <div className="pos-settings__empty">
            <p>No team members assigned yet.</p>
            <p>Go to <strong>Settings &gt; Team Roles</strong> to assign team members to workflow roles.</p>
          </div>
        ) : (
          <div className="pos-settings__team-grid">
            {team.map(member => (
              <div key={member.user_id} className="pos-settings__member-card">
                <div className="pos-settings__member-avatar">
                  {getInitials(member.name || member.email)}
                </div>
                <div className="pos-settings__member-info">
                  <span className="pos-settings__member-name">
                    {member.name || member.email}
                  </span>
                  <span className="pos-settings__member-roles">
                    {member.roles.join(' · ')}
                  </span>
                  {member.email && (
                    <span className="pos-settings__member-email">{member.email}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Calendar Association */}
      <section className="pos-settings__section">
        <h2 className="pos-settings__heading">Calendar Association</h2>
        <p className="pos-settings__desc">
          When a borrower schedules a call through the application, the appointment is booked on the assigned loan officer's calendar.
          The loan officer is determined by the lead/loan assignment at the time of application.
        </p>

        <div className="pos-settings__calendar-info">
          <div className="pos-settings__calendar-row">
            <span className="pos-settings__calendar-label">Scheduling for</span>
            <span className="pos-settings__calendar-value">
              {calendarAssignment
                ? `${calendarAssignment.name} (${calendarAssignment.email})`
                : 'Primary Loan Officer assigned to the lead'}
            </span>
          </div>
          <div className="pos-settings__calendar-row">
            <span className="pos-settings__calendar-label">Calendar source</span>
            <span className="pos-settings__calendar-value">
              Smart Calendar — synced with loan officer's connected calendar
            </span>
          </div>
          <div className="pos-settings__calendar-row">
            <span className="pos-settings__calendar-label">Appointment types</span>
            <span className="pos-settings__calendar-value">
              Check-in · Application Review · Full Consultation
            </span>
          </div>
        </div>

        <div className="pos-settings__calendar-note">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <span>
            To change calendar availability or meeting duration, go to{' '}
            <button
              type="button"
              className="pos-settings__link-btn"
              onClick={() => navigate('/calendar')}
            >
              Calendar Settings
            </button>.
          </span>
        </div>
      </section>

      {/* How It Works */}
      <section className="pos-settings__section">
        <h2 className="pos-settings__heading">How It Works</h2>
        <div className="pos-settings__flow">
          <div className="pos-settings__flow-step">
            <div className="pos-settings__flow-number">1</div>
            <div>
              <strong>Borrower opens link</strong>
              <p>Borrower clicks the application link and verifies their identity with an email code.</p>
            </div>
          </div>
          <div className="pos-settings__flow-step">
            <div className="pos-settings__flow-number">2</div>
            <div>
              <strong>Completes application</strong>
              <p>Aria guides them through each section. They see your team contacts and can message or schedule calls.</p>
            </div>
          </div>
          <div className="pos-settings__flow-step">
            <div className="pos-settings__flow-number">3</div>
            <div>
              <strong>Lead + loan created</strong>
              <p>On submission, a lead and loan record are created in your pipeline, assigned to your team.</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function getInitials(name) {
  if (!name) return '??';
  return name
    .split(' ')
    .filter(Boolean)
    .map(w => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

export default POSSettings;
