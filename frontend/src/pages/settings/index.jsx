import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import { getToken, getUserData, setTokens, clearTokens } from '../../utils/tokenStore';
import { toast } from '../../utils/toast';
import { getAuthHeaders } from '../../utils/auth';
import { formatPhoneNumber } from '../../utils/phoneUtils';
import { API_BASE, DEFAULT_SIDEBAR_ITEMS } from './shared/constants';
import '../Settings.css';

// Extracted section components
import MorningBriefingSettings from './MorningBriefingSettings';
import AgentGovernanceSettings from './AgentGovernanceSettings';
import AccountManagementSection from './AccountManagementSection';
import { ProfileInfoSection, AccountSettingsSection, SecuritySection, WorkHoursSection } from './UserProfileSections';

// Existing external components
import AIReceptionist from '../../components/AIReceptionist';
import DocumentIntakeManager from '../../components/DocumentIntakeManager';
import EmailMonitorDashboard from '../EmailMonitorDashboard';
import EmailSignatureTab from '../../components/EmailSignatureTab';
import VideoMeetings from '../../components/VideoMeetings';
import AIFeedbackLog from '../../components/AIFeedbackLog';
import ITHelpdeskAdmin from '../../components/ITHelpdeskAdmin';
import PURLManager from '../../components/admin/PURLManager';
import AIEmailTraining from '../../components/AIEmailTraining';
import AIEmailSetup from '../../components/AIEmailSetup';
import ContactCardSettings from '../../components/ContactCardSettings';
import BusinessOpsDashboard from '../BusinessOpsDashboard';
import IntegrationSettings from '../IntegrationSettings';

// Import the inline DialerSettingsSection and integration detail content
// These remain inline in this file since they share significant state
import IntegrationDetailSections from './IntegrationDetailSections';
import UserManagementSection from './UserManagementSection';
import ITHelpdeskSection from './ITHelpdeskSection';
import ApiKeysSection from './ApiKeysSection';
import ClearDataSection from './ClearDataSection';

function Settings() {
  const navigate = useNavigate();
  const { isAdmin, loading: permissionsLoading } = usePermissions();
  const currentUser = getUserData() || {};

  // --- Core UI state ---
  const [activeSection, setActiveSection] = useState('profile-info');
  const [expandedSections, setExpandedSections] = useState({
    userProfile: false, integrations: false, organizational: false,
    scheduling: false, onboarding: false, masterAdmin: false,
    landingPages: false, agentGovernance: false, production: false
  });

  // --- Sidebar drag state ---
  const [sidebarOrder, setSidebarOrder] = useState(() => {
    const saved = localStorage.getItem('settings_sidebar_order');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        const savedIds = new Set(parsed.map(item => item.id));
        const defaultIds = new Set(DEFAULT_SIDEBAR_ITEMS.map(item => item.id));
        const filtered = parsed.filter(item => defaultIds.has(item.id));
        DEFAULT_SIDEBAR_ITEMS.forEach(item => { if (!savedIds.has(item.id)) filtered.push(item); });
        return filtered;
      } catch (e) { return DEFAULT_SIDEBAR_ITEMS; }
    }
    return DEFAULT_SIDEBAR_ITEMS;
  });
  const [draggedItem, setDraggedItem] = useState(null);
  const [dragOverItem, setDragOverItem] = useState(null);

  const handleDragStart = (e, item) => { setDraggedItem(item); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/html', e.target.outerHTML); e.target.style.opacity = '0.5'; };
  const handleDragEnd = (e) => { e.target.style.opacity = '1'; setDraggedItem(null); setDragOverItem(null); };
  const handleDragOver = (e, item) => { e.preventDefault(); if (draggedItem && draggedItem.id !== item.id) setDragOverItem(item); };
  const handleDragLeave = (e) => { e.preventDefault(); setDragOverItem(null); };
  const handleDrop = (e, targetItem) => {
    e.preventDefault();
    if (!draggedItem || draggedItem.id === targetItem.id) return;
    const newOrder = [...sidebarOrder];
    const draggedIndex = newOrder.findIndex(item => item.id === draggedItem.id);
    const targetIndex = newOrder.findIndex(item => item.id === targetItem.id);
    const [removed] = newOrder.splice(draggedIndex, 1);
    newOrder.splice(targetIndex, 0, removed);
    setSidebarOrder(newOrder);
    localStorage.setItem('settings_sidebar_order', JSON.stringify(newOrder));
    setDraggedItem(null);
    setDragOverItem(null);
  };
  const resetSidebarOrder = () => { setSidebarOrder(DEFAULT_SIDEBAR_ITEMS); localStorage.removeItem('settings_sidebar_order'); };
  const toggleSection = (section) => { setExpandedSections({ ...expandedSections, [section]: !expandedSections[section] }); };

  // --- User Profile state ---
  const [userProfile, setUserProfile] = useState({
    id: null, slug: '', first_name: '', last_name: '', email: '', phone: '',
    nmls_number: '', job_title: '', work_hours_start: '09:00', work_hours_end: '17:00',
    work_days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
    daily_hours: {}, blocked_times: []
  });
  const [passwordData, setPasswordData] = useState({ current_password: '', new_password: '', confirm_password: '' });
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [profileMessage, setProfileMessage] = useState({ type: '', text: '' });

  const loadUserProfile = async () => {
    setLoadingProfile(true);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE}/api/v1/users/me`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (response.ok) {
        const data = await response.json();
        const nameParts = (data.full_name || '').trim().split(' ');
        setUserProfile({
          id: data.id || null, slug: data.slug || '',
          first_name: nameParts[0] || '', last_name: nameParts.slice(1).join(' ') || '',
          email: data.email || '', phone: data.phone || '',
          nmls_number: data.nmls_number || '', job_title: data.job_title || '',
          work_hours_start: data.work_hours_start || '09:00', work_hours_end: data.work_hours_end || '17:00',
          work_days: data.work_days || ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
          daily_hours: data.daily_hours || {}, blocked_times: data.blocked_times || []
        });
      }
    } catch (error) {
      console.error('Error loading profile:', error);
      setProfileMessage({ type: 'error', text: 'Failed to load profile. Please try refreshing the page.' });
    } finally { setLoadingProfile(false); }
  };

  const saveUserProfile = async () => {
    setSavingProfile(true);
    setProfileMessage({ type: '', text: '' });
    try {
      const token = getToken();
      const fullName = `${userProfile.first_name} ${userProfile.last_name}`.trim();
      const response = await fetch(`${API_BASE}/api/v1/users/me`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: fullName, phone: userProfile.phone, nmls_number: userProfile.nmls_number,
          job_title: userProfile.job_title, work_hours_start: userProfile.work_hours_start,
          work_hours_end: userProfile.work_hours_end, work_days: userProfile.work_days,
          daily_hours: userProfile.daily_hours, blocked_times: userProfile.blocked_times
        })
      });
      if (response.ok) {
        setProfileMessage({ type: 'success', text: 'Profile updated successfully!' });
        const storedUser = (getUserData() || {});
        await setTokens({ user_data: { ...storedUser, full_name: fullName } });
      } else {
        const error = await response.json();
        setProfileMessage({ type: 'error', text: error.detail || 'Failed to update profile' });
      }
    } catch (error) {
      setProfileMessage({ type: 'error', text: 'Failed to update profile' });
    } finally { setSavingProfile(false); }
  };

  const changePassword = async () => {
    if (passwordData.new_password !== passwordData.confirm_password) { setProfileMessage({ type: 'error', text: 'New passwords do not match' }); return; }
    if (passwordData.new_password.length < 6) { setProfileMessage({ type: 'error', text: 'Password must be at least 6 characters' }); return; }
    setChangingPassword(true);
    setProfileMessage({ type: '', text: '' });
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE}/api/v1/users/me/password`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: passwordData.current_password, new_password: passwordData.new_password })
      });
      if (response.ok) {
        setProfileMessage({ type: 'success', text: 'Password changed successfully!' });
        setPasswordData({ current_password: '', new_password: '', confirm_password: '' });
      } else {
        const error = await response.json();
        setProfileMessage({ type: 'error', text: error.detail || 'Failed to change password' });
      }
    } catch (error) { setProfileMessage({ type: 'error', text: 'Failed to change password' }); }
    finally { setChangingPassword(false); }
  };

  useEffect(() => {
    if (['profile-info', 'account-settings', 'security', 'work-hours', 'morning-briefing'].includes(activeSection)) {
      loadUserProfile();
    }
  }, [activeSection]);

  const handleLogout = async () => {
    if (window.confirm('Are you sure you want to log out?')) {
      await clearTokens();
      navigate('/login');
    }
  };

  // Common drag props for sidebar items
  const dragProps = (item) => ({
    draggable: true,
    onDragStart: (e) => handleDragStart(e, item),
    onDragEnd: handleDragEnd,
    onDragOver: (e) => handleDragOver(e, item),
    onDragLeave: handleDragLeave,
    onDrop: (e) => handleDrop(e, item),
  });

  // --- Render sidebar parent with children helper ---
  const renderParentSection = (item, sectionKey, children) => {
    const hideAdminItem = item.adminOnly && !isAdmin && !permissionsLoading;
    if (hideAdminItem) return null;
    return (
      <div key={item.id}>
        <button
          className={`sidebar-btn parent ${expandedSections[sectionKey] ? 'expanded' : ''} ${dragOverItem?.id === item.id ? 'drag-over' : ''}`}
          onClick={() => toggleSection(sectionKey)}
          {...dragProps(item)}
        >
          <span>{item.label}</span>
          <span className="expand-icon">{expandedSections[sectionKey] ? '▼' : '▶'}</span>
        </button>
        {expandedSections[sectionKey] && <div className="sidebar-children">{children}</div>}
      </div>
    );
  };

  const sidebarChild = (section, label, onClick) => (
    <button key={section} className={`sidebar-btn child ${activeSection === section ? 'active' : ''}`} onClick={onClick || (() => setActiveSection(section))}><span>{label}</span></button>
  );

  return (
    <div className="settings-page">
      <div className="settings-header">
        <div className="settings-header-left">
          <h1>Settings</h1>
          <p>Manage your integrations and preferences</p>
        </div>
        <button className="logout-btn-settings" onClick={handleLogout}>Logout</button>
      </div>

      <div className="settings-content">
        {/* Sidebar */}
        <div className="settings-sidebar">
          <div className="sidebar-header">
            <div className="drag-hint-container">
              <span className="drag-icon">&#9776;</span>
              <span className="drag-hint">Drag to reorder</span>
            </div>
            <button className="reset-order-btn" onClick={resetSidebarOrder} title="Reset to default order">&#8634;</button>
          </div>
          {sidebarOrder.map((item) => {
            const hideAdminItem = item.adminOnly && !isAdmin && !permissionsLoading;

            if (item.id === 'user-profile') {
              return renderParentSection(item, 'userProfile', <>
                {sidebarChild('profile-info', 'Profile Info')}
                {sidebarChild('account-settings', 'Account Settings')}
                {sidebarChild('security', 'Security')}
                {sidebarChild('email-signature', 'Email Signature')}
                {sidebarChild('contact-card-team', 'Contact Card')}
                {sidebarChild('work-hours', 'Work Hours')}
                {sidebarChild('morning-briefing', 'Morning Briefing')}
              </>);
            }

            if (item.id === 'organizational') {
              return renderParentSection(item, 'organizational', <>
                {sidebarChild('account-mgmt', 'Account Management')}
                {sidebarChild('company-info', 'Company Info')}
                {sidebarChild('team-members', 'Team Members', () => navigate('/team-members'))}
                {sidebarChild('add-team-member', 'Add Team Member', () => navigate('/users/create'))}
                {sidebarChild('bulk-upload', 'Bulk Upload Users', () => navigate('/users/bulk-upload'))}
                {sidebarChild('branding', 'Branding')}
              </>);
            }

            if (item.id === 'agent-governance') {
              return renderParentSection(item, 'agentGovernance', <>
                {sidebarChild('agent-governance-system', 'System Settings')}
                {sidebarChild('agent-governance-thresholds', 'Performance Thresholds')}
                {sidebarChild('agent-governance-costs', 'Cost Budgets')}
                {sidebarChild('agent-governance-alerts', 'Alerts & Notifications')}
                {sidebarChild('agent-governance-compliance', 'Compliance')}
                {sidebarChild('agent-governance-gym', 'Agent Gym Settings')}
                {sidebarChild('ai-email-training', 'AI Email Training')}
                {sidebarChild('ai-email-setup', 'AI Email Setup')}
              </>);
            }

            if (item.id === 'production') {
              return renderParentSection(item, 'production', <>
                <button className="sidebar-btn child" onClick={() => navigate('/calendar-settings')}><span>Smart Calendar</span><i className="fas fa-external-link-alt" style={{ fontSize: '0.7em', marginLeft: 6, opacity: 0.5 }}></i></button>
                {sidebarChild('video-meetings', 'Video Meetings')}
                {sidebarChild('dialer-settings', 'Power Dialer')}
                {sidebarChild('voice-os', 'Voice OS', () => navigate('/voice-os-dashboard'))}
                {sidebarChild('ai-receptionist', 'AI Receptionist')}
              </>);
            }

            if (item.id === 'master-admin') {
              return renderParentSection(item, 'masterAdmin', <>
                {sidebarChild('account-mgmt', 'Account Management', () => { setActiveSection('account-mgmt'); })}
                {sidebarChild('integration-marketplace', 'Integrations')}
                {sidebarChild('clear-data', 'Clear Dummy Data')}
                {sidebarChild('ai-feedback-log', 'AI Feedback Log')}
                {sidebarChild('it-helpdesk-admin', 'IT Helpdesk Admin')}
                {sidebarChild('api-keys', 'API Keys')}
                {sidebarChild('business-ops', 'Business Operations')}
                <button className="sidebar-btn child" onClick={() => navigate('/settings/account-management')}><span>Account Management</span></button>
              </>);
            }

            if (hideAdminItem) return null;

            return (
              <button
                key={item.id}
                className={`sidebar-btn ${activeSection === item.section ? 'active' : ''} ${dragOverItem?.id === item.id ? 'drag-over' : ''}`}
                onClick={() => item.navigate ? navigate(item.navigate) : setActiveSection(item.section)}
                {...dragProps(item)}
              >
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>

        {/* Main Content */}
        <div className="settings-main">
          {/* External components */}
          {activeSection === 'ai-receptionist' && <AIReceptionist />}
          {activeSection === 'email-monitor' && <EmailMonitorDashboard />}
          {activeSection === 'ai-email-training' && <AIEmailTraining />}
          {activeSection === 'ai-email-setup' && <AIEmailSetup />}
          {activeSection === 'email-signature' && <EmailSignatureTab />}
          {activeSection === 'document-intake' && <DocumentIntakeManager />}
          {activeSection === 'ai-feedback-log' && <AIFeedbackLog />}
          {activeSection === 'it-helpdesk-admin' && <ITHelpdeskAdmin />}
          {activeSection === 'business-ops' && <BusinessOpsDashboard />}
          {activeSection === 'video-meetings' && <VideoMeetings />}
          {activeSection === 'client-portals' && <PURLManager />}
          {activeSection === 'integration-settings' && <IntegrationSettings />}
          {activeSection === 'contact-card-team' && <ContactCardSettings />}

          {/* User Profile sections */}
          {activeSection === 'profile-info' && (
            <ProfileInfoSection userProfile={userProfile} setUserProfile={setUserProfile}
              profileMessage={profileMessage} loadingProfile={loadingProfile}
              savingProfile={savingProfile} saveUserProfile={saveUserProfile} />
          )}
          {activeSection === 'account-settings' && <AccountSettingsSection userProfile={userProfile} />}
          {activeSection === 'security' && (
            <SecuritySection profileMessage={profileMessage} passwordData={passwordData}
              setPasswordData={setPasswordData} changingPassword={changingPassword}
              changePassword={changePassword} />
          )}
          {activeSection === 'work-hours' && (
            <WorkHoursSection userProfile={userProfile} setUserProfile={setUserProfile}
              profileMessage={profileMessage} loadingProfile={loadingProfile}
              savingProfile={savingProfile} saveUserProfile={saveUserProfile} />
          )}
          {activeSection === 'morning-briefing' && <MorningBriefingSettings />}

          {/* Standalone sections */}
          {activeSection === 'dialer-settings' && <DialerSettingsSection />}
          {activeSection === 'account-management' && <AccountManagementSection />}
          {activeSection === 'account-mgmt' && <UserManagementSection />}
          {activeSection === 'it-helpdesk' && <ITHelpdeskSection />}
          {activeSection === 'api-keys' && <ApiKeysSection />}
          {activeSection === 'clear-data' && <ClearDataSection />}

          {/* Simple placeholder sections */}
          {activeSection === 'company-info' && (
            <div className="company-info-section"><h2>Company Information</h2><p className="section-description">Manage your company profile and contact information</p><p>Coming soon...</p></div>
          )}
          {activeSection === 'branding' && (
            <div className="branding-section"><h2>Branding</h2><p className="section-description">Customize your company's branding and appearance</p><p>Coming soon...</p></div>
          )}

          {/* Agent Governance sections */}
          {activeSection.startsWith('agent-governance-') && <AgentGovernanceSettings activeSection={activeSection} />}

          {/* Integration detail sections */}
          <IntegrationDetailSections activeSection={activeSection} setActiveSection={setActiveSection} />
        </div>
      </div>
    </div>
  );
}

// DialerSettingsSection - kept inline since it was originally inline in Settings.js
const DialerSettingsSection = () => {
  const [settings, setSettings] = useState({
    cell_phone: '', business_caller_id: '', dialer_enabled: false,
    max_calls_per_day: 100, auto_advance: true, pause_between_calls: 3
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [verifiedCallerIds, setVerifiedCallerIds] = useState([]);
  const [verifyPhone, setVerifyPhone] = useState('');
  const [verifyName, setVerifyName] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => { fetchSettings(); fetchVerifiedCallerIds(); }, []);

  const fetchSettings = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/settings`, { headers: getAuthHeaders() });
      if (response.ok) setSettings(await response.json());
    } catch (err) { console.error('Error fetching dialer settings:', err); }
    finally { setLoading(false); }
  };

  const fetchVerifiedCallerIds = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/verified-caller-ids`, { headers: getAuthHeaders() });
      if (response.ok) { const data = await response.json(); setVerifiedCallerIds(data.caller_ids || []); }
    } catch (err) { console.error('Error fetching verified caller IDs:', err); }
  };

  const saveSettings = async () => {
    setSaving(true); setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/settings`, { method: 'PUT', headers: getAuthHeaders(), body: JSON.stringify(settings) });
      if (response.ok) { setMessage({ type: 'success', text: 'Settings saved successfully!' }); }
      else { const err = await response.json(); setMessage({ type: 'error', text: err.detail || 'Failed to save settings' }); }
    } catch (err) { setMessage({ type: 'error', text: 'Error saving settings: ' + err.message }); }
    finally { setSaving(false); }
  };

  const startVerification = async () => {
    if (!verifyPhone || !verifyName) { setMessage({ type: 'error', text: 'Please enter phone number and name' }); return; }
    setVerifying(true); setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/verify-caller-id`, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ phone_number: verifyPhone, friendly_name: verifyName }) });
      const data = await response.json();
      if (data.success) { setMessage({ type: 'success', text: `Verification call initiated! Enter code: ${data.validation_code} when you receive the call. After completing the call, click "Check Verification Status".` }); setVerifyName(''); }
      else { setMessage({ type: 'error', text: data.error || 'Failed to start verification' }); }
    } catch (err) { setMessage({ type: 'error', text: 'Error starting verification: ' + err.message }); }
    finally { setVerifying(false); }
  };

  const checkVerification = async () => {
    if (!verifyPhone) { setMessage({ type: 'error', text: 'Please enter a phone number to check' }); return; }
    setVerifying(true); setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/check-verification/${encodeURIComponent(verifyPhone)}`, { method: 'POST', headers: getAuthHeaders() });
      const data = await response.json();
      if (data.verified) { setMessage({ type: 'success', text: data.message }); setVerifyPhone(''); await fetchVerifiedCallerIds(); }
      else { setMessage({ type: 'warning', text: data.message }); }
    } catch (err) { setMessage({ type: 'error', text: 'Error checking verification: ' + err.message }); }
    finally { setVerifying(false); }
  };

  if (loading) return <div className="loading-state">Loading dialer settings...</div>;

  return (
    <div className="dialer-settings-section">
      <h2>Power Dialer Settings</h2>
      <p className="section-description">Configure your click-to-dial and power dialer settings for outbound calls</p>
      {message && <div className={`message-banner ${message.type}`}>{message.text}<button onClick={() => setMessage(null)}>&times;</button></div>}
      <div className="settings-card">
        <h3>Phone Numbers</h3>
        <div className="form-group">
          <label>Your Cell Phone</label>
          <input type="tel" value={settings.cell_phone || ''} onChange={(e) => setSettings({ ...settings, cell_phone: formatPhoneNumber(e.target.value) })} placeholder="+1 (555) 123-4567" />
          <small>Your personal phone number for receiving calls</small>
        </div>
        <div className="form-group">
          <label>Business Caller ID</label>
          <select value={settings.business_caller_id || ''} onChange={(e) => setSettings({ ...settings, business_caller_id: e.target.value })}>
            <option value="">Select a verified caller ID...</option>
            {verifiedCallerIds.map((cid) => <option key={cid.sid} value={cid.phone_number}>{cid.friendly_name} ({cid.phone_number})</option>)}
          </select>
          <small>The phone number shown to contacts when you call them</small>
        </div>
        <div className="verify-caller-id">
          <h4>Add New Caller ID</h4>
          <p>Verify a new business phone number to use as your caller ID</p>
          <div className="verify-form">
            <input type="tel" value={verifyPhone} onChange={(e) => setVerifyPhone(formatPhoneNumber(e.target.value))} placeholder="+1 (555) 123-4567" />
            <input type="text" value={verifyName} onChange={(e) => setVerifyName(e.target.value)} placeholder="Display Name (e.g., Your Company)" />
            <div className="verify-buttons">
              <button onClick={startVerification} disabled={verifying} className="btn-primary">{verifying ? 'Processing...' : 'Start Verification'}</button>
              <button onClick={checkVerification} disabled={verifying || !verifyPhone} className="btn-secondary">Check Status</button>
            </div>
          </div>
          <small>
            <strong>Step 1:</strong> Enter your phone number and click "Start Verification". You will receive a call with a verification code.<br />
            <strong>Step 2:</strong> Answer the call and enter the code when prompted.<br />
            <strong>Step 3:</strong> Click "Check Status" to confirm verification is complete.
          </small>
        </div>
      </div>
      <div className="settings-card">
        <h3>Dialer Preferences</h3>
        <div className="form-group checkbox">
          <label><input type="checkbox" checked={settings.dialer_enabled} onChange={(e) => setSettings({ ...settings, dialer_enabled: e.target.checked })} /> Enable Power Dialer</label>
          <small>Allow batch calling through the power dialer interface</small>
        </div>
        <div className="form-group checkbox">
          <label><input type="checkbox" checked={settings.auto_advance} onChange={(e) => setSettings({ ...settings, auto_advance: e.target.checked })} /> Auto-Advance to Next Call</label>
          <small>Automatically dial the next contact after setting disposition</small>
        </div>
        <div className="form-group">
          <label>Max Calls Per Day</label>
          <input type="number" min="1" max="500" value={settings.max_calls_per_day || 100} onChange={(e) => setSettings({ ...settings, max_calls_per_day: parseInt(e.target.value) || 100 })} />
          <small>Daily call limit to prevent burnout and maintain quality</small>
        </div>
        <div className="form-group">
          <label>Pause Between Calls (seconds)</label>
          <input type="number" min="0" max="30" value={settings.pause_between_calls || 3} onChange={(e) => setSettings({ ...settings, pause_between_calls: parseInt(e.target.value) || 3 })} />
          <small>Time to wait before auto-dialing the next contact</small>
        </div>
      </div>
      <div className="settings-actions">
        <button onClick={saveSettings} disabled={saving} className="btn-primary btn-large">{saving ? 'Saving...' : 'Save Settings'}</button>
      </div>
    </div>
  );
};

export default Settings;
