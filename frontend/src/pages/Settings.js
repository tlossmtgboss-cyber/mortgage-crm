import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { teamAPI, agentAPI } from '../services/api';
import { getAuthHeaders } from '../utils/auth';
import { usePermissions } from '../contexts/PermissionContext';
import AIReceptionist from '../components/AIReceptionist';
import TaskWorkflowManager from '../components/TaskWorkflowManager';
import DocumentIntakeManager from '../components/DocumentIntakeManager';
import EmailMonitorDashboard from './EmailMonitorDashboard';
import EmailSignatureTab from '../components/EmailSignatureTab';
import VideoMeetings from '../components/VideoMeetings';
import AIFeedbackLog from '../components/AIFeedbackLog';
import ITHelpdeskAdmin from '../components/ITHelpdeskAdmin';
import PURLManager from '../components/admin/PURLManager';
import AIEmailTraining from '../components/AIEmailTraining';
import AIEmailSetup from '../components/AIEmailSetup';
import AIDailyBlog from './AIDailyBlog';
import PreApprovalLetterSettings from '../components/PreApprovalLetterSettings';
import ApplicationSlidesEditor from '../components/ApplicationSlidesEditor';
import BusinessOpsDashboard from './BusinessOpsDashboard';
import IntegrationSettings from './IntegrationSettings';
import { formatPhoneNumber } from '../utils/phoneUtils';
import './Settings.css';
import { toast } from '../utils/toast';

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Dialer Settings Section Component
const DialerSettingsSection = () => {
  const [settings, setSettings] = useState({
    cell_phone: '',
    business_caller_id: '',
    dialer_enabled: false,
    max_calls_per_day: 100,
    auto_advance: true,
    pause_between_calls: 3
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [verifiedCallerIds, setVerifiedCallerIds] = useState([]);
  const [verifyPhone, setVerifyPhone] = useState('');
  const [verifyName, setVerifyName] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    fetchSettings();
    fetchVerifiedCallerIds();
  }, []);

  const fetchSettings = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/settings`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setSettings(data);
      }
    } catch (err) {
      console.error('Error fetching dialer settings:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchVerifiedCallerIds = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/verified-caller-ids`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        // API returns { caller_ids: [...] }
        setVerifiedCallerIds(data.caller_ids || []);
      }
    } catch (err) {
      console.error('Error fetching verified caller IDs:', err);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/settings`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(settings)
      });
      if (response.ok) {
        setMessage({ type: 'success', text: 'Settings saved successfully!' });
      } else {
        const err = await response.json();
        setMessage({ type: 'error', text: err.detail || 'Failed to save settings' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Error saving settings: ' + err.message });
    } finally {
      setSaving(false);
    }
  };

  const startVerification = async () => {
    if (!verifyPhone || !verifyName) {
      setMessage({ type: 'error', text: 'Please enter phone number and name' });
      return;
    }

    setVerifying(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/verify-caller-id`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          phone_number: verifyPhone,
          friendly_name: verifyName
        })
      });

      const data = await response.json();
      if (data.success) {
        setMessage({
          type: 'success',
          text: `Verification call initiated! Enter code: ${data.validation_code} when you receive the call. After completing the call, click "Check Verification Status".`
        });
        // Don't clear phone - user may need to check verification
        setVerifyName('');
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to start verification' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Error starting verification: ' + err.message });
    } finally {
      setVerifying(false);
    }
  };

  const checkVerification = async () => {
    if (!verifyPhone) {
      setMessage({ type: 'error', text: 'Please enter a phone number to check' });
      return;
    }

    setVerifying(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/check-verification/${encodeURIComponent(verifyPhone)}`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      const data = await response.json();
      if (data.verified) {
        setMessage({ type: 'success', text: data.message });
        setVerifyPhone('');
        // Refresh the caller IDs list
        await fetchVerifiedCallerIds();
      } else {
        setMessage({ type: 'warning', text: data.message });
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Error checking verification: ' + err.message });
    } finally {
      setVerifying(false);
    }
  };

  if (loading) {
    return <div className="loading-state">Loading dialer settings...</div>;
  }

  return (
    <div className="dialer-settings-section">
      <h2>Power Dialer Settings</h2>
      <p className="section-description">
        Configure your click-to-dial and power dialer settings for outbound calls
      </p>

      {message && (
        <div className={`message-banner ${message.type}`}>
          {message.text}
          <button onClick={() => setMessage(null)}>×</button>
        </div>
      )}

      <div className="settings-card">
        <h3>Phone Numbers</h3>

        <div className="form-group">
          <label>Your Cell Phone</label>
          <input
            type="tel"
            value={settings.cell_phone || ''}
            onChange={(e) => setSettings({ ...settings, cell_phone: formatPhoneNumber(e.target.value) })}
            placeholder="+1 (555) 123-4567"
          />
          <small>Your personal phone number for receiving calls</small>
        </div>

        <div className="form-group">
          <label>Business Caller ID</label>
          <select
            value={settings.business_caller_id || ''}
            onChange={(e) => setSettings({ ...settings, business_caller_id: e.target.value })}
          >
            <option value="">Select a verified caller ID...</option>
            {verifiedCallerIds.map((cid) => (
              <option key={cid.sid} value={cid.phone_number}>
                {cid.friendly_name} ({cid.phone_number})
              </option>
            ))}
          </select>
          <small>The phone number shown to contacts when you call them</small>
        </div>

        <div className="verify-caller-id">
          <h4>Add New Caller ID</h4>
          <p>Verify a new business phone number to use as your caller ID</p>
          <div className="verify-form">
            <input
              type="tel"
              value={verifyPhone}
              onChange={(e) => setVerifyPhone(formatPhoneNumber(e.target.value))}
              placeholder="+1 (555) 123-4567"
            />
            <input
              type="text"
              value={verifyName}
              onChange={(e) => setVerifyName(e.target.value)}
              placeholder="Display Name (e.g., Your Company)"
            />
            <div className="verify-buttons">
              <button
                onClick={startVerification}
                disabled={verifying}
                className="btn-primary"
              >
                {verifying ? 'Processing...' : 'Start Verification'}
              </button>
              <button
                onClick={checkVerification}
                disabled={verifying || !verifyPhone}
                className="btn-secondary"
              >
                Check Status
              </button>
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
          <label>
            <input
              type="checkbox"
              checked={settings.dialer_enabled}
              onChange={(e) => setSettings({ ...settings, dialer_enabled: e.target.checked })}
            />
            Enable Power Dialer
          </label>
          <small>Allow batch calling through the power dialer interface</small>
        </div>

        <div className="form-group checkbox">
          <label>
            <input
              type="checkbox"
              checked={settings.auto_advance}
              onChange={(e) => setSettings({ ...settings, auto_advance: e.target.checked })}
            />
            Auto-Advance to Next Call
          </label>
          <small>Automatically dial the next contact after setting disposition</small>
        </div>

        <div className="form-group">
          <label>Max Calls Per Day</label>
          <input
            type="number"
            min="1"
            max="500"
            value={settings.max_calls_per_day || 100}
            onChange={(e) => setSettings({ ...settings, max_calls_per_day: parseInt(e.target.value) || 100 })}
          />
          <small>Daily call limit to prevent burnout and maintain quality</small>
        </div>

        <div className="form-group">
          <label>Pause Between Calls (seconds)</label>
          <input
            type="number"
            min="0"
            max="30"
            value={settings.pause_between_calls || 3}
            onChange={(e) => setSettings({ ...settings, pause_between_calls: parseInt(e.target.value) || 3 })}
          />
          <small>Time to wait before auto-dialing the next contact</small>
        </div>
      </div>

      <div className="settings-actions">
        <button
          onClick={saveSettings}
          disabled={saving}
          className="btn-primary btn-large"
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
};

function Settings() {
  const navigate = useNavigate();
  const { isAdmin, loading: permissionsLoading } = usePermissions();

  // Get current user from localStorage
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');

  const [activeSection, setActiveSection] = useState('profile-info');
  const [expandedSections, setExpandedSections] = useState({
    userProfile: false,
    integrations: false,
    organizational: false,
    scheduling: false,
    onboarding: false,
    masterAdmin: false,
    landingPages: false,
    agentGovernance: false,
    production: false
  });

  // Default sidebar items order
  const defaultSidebarItems = [
    { id: 'user-profile', label: 'User Profile', type: 'parent', section: 'userProfile' },
    { id: 'organizational', label: 'Organizational Settings', type: 'parent', section: 'organizational', adminOnly: true },
    { id: 'workflow', label: 'Workflow', type: 'standalone', section: 'workflow', navigate: '/workflow', adminOnly: true },
    { id: 'sla-tracking', label: 'SLA Tracking', type: 'standalone', section: 'sla-tracking', navigate: '/sla-tracking', adminOnly: true },
    { id: 'agent-governance', label: 'Agent Governance', type: 'parent', section: 'agentGovernance', adminOnly: true },
    { id: 'document-intake', label: 'Document Intake', type: 'standalone', section: 'document-intake', adminOnly: true },
    { id: 'email-monitor', label: 'Email Monitor', type: 'standalone', section: 'email-monitor', adminOnly: true },
    { id: 'it-helpdesk', label: 'IT Helpdesk', type: 'standalone', section: 'it-helpdesk' },
    { id: 'production', label: 'Production Widgets', type: 'parent', section: 'production' },
    { id: 'client-portals', label: 'Client Portals (PURL)', type: 'standalone', section: 'client-portals', adminOnly: true },
    { id: 'client-portal-settings', label: 'Client Portal Settings', type: 'standalone', section: 'client-portal-settings', navigate: '/settings/client-portal', adminOnly: true },
    { id: 'lead-capture', label: 'Lead Capture', type: 'standalone', section: 'lead-capture', navigate: '/settings/lead-capture', adminOnly: true },
    { id: 'communication-preferences', label: 'Communication Preferences', type: 'standalone', section: 'communication-preferences', navigate: '/settings/communication', adminOnly: true },
    { id: 'integration-settings', label: 'Integrations', type: 'standalone', section: 'integration-settings' },
    { id: 'api-keys-settings', label: 'API Keys & Webhooks', type: 'standalone', section: 'api-keys-settings', navigate: '/settings/api-keys', adminOnly: true },
    { id: 'company-branding', label: 'Company & Branding', type: 'standalone', section: 'company-branding', navigate: '/settings/company-branding', adminOnly: true },
    { id: 'data-management', label: 'Data Management', type: 'standalone', section: 'data-management', navigate: '/data-upload', adminOnly: true },
    { id: 'master-admin', label: 'Master Administrator', type: 'parent', section: 'masterAdmin', adminOnly: true },
    { id: 'admin-settings', label: 'Admin Settings', type: 'standalone', section: 'admin-settings', navigate: '/admin/settings', adminOnly: true },
    { id: 'custom-domains', label: 'Custom Domains', type: 'standalone', section: 'custom-domains', navigate: '/admin/domains', adminOnly: true },
    { id: 'call-routing', label: 'Call Routing', type: 'standalone', section: 'call-routing', navigate: '/call-routing-config', adminOnly: true }
  ];

  // Load sidebar order from localStorage or use defaults
  const [sidebarOrder, setSidebarOrder] = useState(() => {
    const saved = localStorage.getItem('settings_sidebar_order');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        const savedIds = new Set(parsed.map(item => item.id));
        const defaultIds = new Set(defaultSidebarItems.map(item => item.id));

        // Filter out any removed/deprecated items that are no longer in defaults
        const filtered = parsed.filter(item => defaultIds.has(item.id));

        // Add any new default items that weren't in saved
        defaultSidebarItems.forEach(item => {
          if (!savedIds.has(item.id)) {
            filtered.push(item);
          }
        });

        return filtered;
      } catch (e) {
        return defaultSidebarItems;
      }
    }
    return defaultSidebarItems;
  });

  // Drag state
  const [draggedItem, setDraggedItem] = useState(null);
  const [dragOverItem, setDragOverItem] = useState(null);

  // Drag handlers
  const handleDragStart = (e, item) => {
    setDraggedItem(item);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', e.target.outerHTML);
    e.target.style.opacity = '0.5';
  };

  const handleDragEnd = (e) => {
    e.target.style.opacity = '1';
    setDraggedItem(null);
    setDragOverItem(null);
  };

  const handleDragOver = (e, item) => {
    e.preventDefault();
    if (draggedItem && draggedItem.id !== item.id) {
      setDragOverItem(item);
    }
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setDragOverItem(null);
  };

  const handleDrop = (e, targetItem) => {
    e.preventDefault();
    if (!draggedItem || draggedItem.id === targetItem.id) return;

    const newOrder = [...sidebarOrder];
    const draggedIndex = newOrder.findIndex(item => item.id === draggedItem.id);
    const targetIndex = newOrder.findIndex(item => item.id === targetItem.id);

    // Remove dragged item and insert at target position
    const [removed] = newOrder.splice(draggedIndex, 1);
    newOrder.splice(targetIndex, 0, removed);

    setSidebarOrder(newOrder);
    localStorage.setItem('settings_sidebar_order', JSON.stringify(newOrder));
    setDraggedItem(null);
    setDragOverItem(null);
  };

  // Reset sidebar order to default
  const resetSidebarOrder = () => {
    setSidebarOrder(defaultSidebarItems);
    localStorage.removeItem('settings_sidebar_order');
  };

  const [searchTerm, setSearchTerm] = useState('');
  const [connectedIntegrations, setConnectedIntegrations] = useState(new Set());
  const [calendlyEventTypes, setCalendlyEventTypes] = useState([]);
  const [calendarMappings, setCalendarMappings] = useState([]);
  const [loadingCalendly, setLoadingCalendly] = useState(false);
  const [selectedStage, setSelectedStage] = useState('');
  const [selectedEventType, setSelectedEventType] = useState('');
    const [apiKeys, setApiKeys] = useState([]);
  const [loadingApiKeys, setLoadingApiKeys] = useState(false);
  const [newApiKeyName, setNewApiKeyName] = useState('');
  const [createdKey, setCreatedKey] = useState(null);

  // User Management state
  const [users, setUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [usersError, setUsersError] = useState(null);
  const [editingUser, setEditingUser] = useState(null);
  const [showAddUserModal, setShowAddUserModal] = useState(false);
  const [addingUser, setAddingUser] = useState(false);
  const [newUser, setNewUser] = useState({
    email: '',
    first_name: '',
    last_name: '',
    role: 'loan_officer',
    is_active: true
  });
  const [selectedUsers, setSelectedUsers] = useState([]);
  const [deletingUsers, setDeletingUsers] = useState(false);

  // Account Management expandable cards state
  const [expandedCards, setExpandedCards] = useState({
    userManagement: false,
    securityMonitoring: false
  });

  // Security monitoring state
  const [securityData, setSecurityData] = useState({
    loginHistory: [],
    activeSessions: [],
    failedAttempts: [],
    auditLog: []
  });
  const [loadingSecurityData, setLoadingSecurityData] = useState(false);

  // Security audit log state
  const [securityAuditLogs, setSecurityAuditLogs] = useState([]);
  const [loadingAuditLogs, setLoadingAuditLogs] = useState(false);
  const [auditLogsError, setAuditLogsError] = useState(null);

  // Gmail integration state
  const [gmailStatus, setGmailStatus] = useState({
    connected: false,
    email: null,
    connected_at: null
  });
  const [loadingGmail, setLoadingGmail] = useState(false);

  // Microsoft/Outlook integration state
  const [microsoftStatus, setMicrosoftStatus] = useState({
    connected: false,
    email: null,
    connected_at: null,
    sync_enabled: false,
    last_sync_at: null
  });
  const [loadingMicrosoft, setLoadingMicrosoft] = useState(false);
  const [syncingMicrosoft, setSyncingMicrosoft] = useState(false);
  const [syncingCalendar, setSyncingCalendar] = useState(false);

  // Microsoft OAuth Configuration state
  const [microsoftOAuthConfig, setMicrosoftOAuthConfig] = useState({
    client_id: '',
    client_secret: '',
    tenant_id: 'common'
  });
  const [showMicrosoftConfig, setShowMicrosoftConfig] = useState(false);
  const [savingMicrosoftConfig, setSavingMicrosoftConfig] = useState(false);
  const [microsoftConfigMessage, setMicrosoftConfigMessage] = useState({ type: '', text: '' });

  // Email processing settings
  const [emailProcessingSettings, setEmailProcessingSettings] = useState({
    delete_from_inbox_after_processing: false
  });
  const [savingEmailSettings, setSavingEmailSettings] = useState(false);

  // Team members state
  const [teamMembers, setTeamMembers] = useState([]);
  const [availableRoles, setAvailableRoles] = useState([]);
  const [loadingTeam, setLoadingTeam] = useState(false);

  // User Profile state
  const [userProfile, setUserProfile] = useState({
    id: null,
    slug: '',
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    nmls_number: '',
    job_title: '',
    work_hours_start: '09:00',
    work_hours_end: '17:00',
    work_days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
    daily_hours: {},
    blocked_times: []
  });
  const [passwordData, setPasswordData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: ''
  });
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [profileMessage, setProfileMessage] = useState({ type: '', text: '' });

  // Calendly integration state
  const [calendlyApiKey, setCalendlyApiKey] = useState('');
  const [showCalendlyModal, setShowCalendlyModal] = useState(false);
  const [calendlyStatus, setCalendlyStatus] = useState({
    isConnected: false,
    userName: null,
    userEmail: null,
    selectedEventTypeName: null,
    connectedAt: null,
    syncToSmartScheduler: true,
    autoCreateContacts: true
  });
  const [calendlySettings, setCalendlySettings] = useState({
    selectedEventTypeUri: '',
    syncToSmartScheduler: true,
    autoCreateContacts: true
  });

  // Phone Integration state
  const [testPhoneNumber, setTestPhoneNumber] = useState('');
  const [testResults, setTestResults] = useState([]);

  // IT Helpdesk state
  const [itTickets, setItTickets] = useState([]);
  const [loadingTickets, setLoadingTickets] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [ticketStatusFilter, setTicketStatusFilter] = useState('all');
  const [newTicket, setNewTicket] = useState({
    title: '',
    description: '',
    category: 'dev_env',
    urgency: 'normal',
    affected_system: '',
    affected_project: '',
    logs_attached: []
  });
  const [submittingTicket, setSubmittingTicket] = useState(false);
  const [resolutionNotes, setResolutionNotes] = useState('');

  // Agent Governance Settings state
  const [agentGovernanceSettings, setAgentGovernanceSettings] = useState({
    // System Settings
    agentGovernanceEnabled: true,
    autoHealthChecks: true,
    costTrackingEnabled: true,

    // Performance Thresholds
    defaultSuccessRate: 90,
    defaultResponseTime: 15000,
    defaultMaxCost: 0.015,

    // Cost Budgets
    defaultDailyBudget: 50,
    systemMonthlyBudget: 30000,
    costAlertThreshold: 80,

    // Alerts
    alertChannel: 'Slack',
    slackWebhook: '',
    dailyDigest: true,
    digestTime: '8:00 AM',

    // Access Control
    requireApproval: false,
    viewPermissions: ['All Users'],
    modifyPermissions: ['Admins Only'],
    auditLogging: true,

    // Compliance
    enforceEliteForTier3: true,
    fairLendingMonitoring: true,
    auditRetentionDays: 2555,

    // Integrations
    anthropicApiKey: '',
    webhookUrl: '',
    websocketEnabled: true,

    // Gym
    autoDailyTesting: true,
    minPassRate: 95,
    blockOnFailedTests: false
  });
  const [loadingAgentSettings, setLoadingAgentSettings] = useState(false);
  const [savingAgentSettings, setSavingAgentSettings] = useState(false);
  const [agentSettingsMessage, setAgentSettingsMessage] = useState({ type: '', text: '' });

  // Load agent governance settings
  const loadAgentGovernanceSettings = async () => {
    setLoadingAgentSettings(true);
    try {
      const response = await agentAPI.getSettings();
      if (response) {
        setAgentGovernanceSettings(prev => ({ ...prev, ...response }));
      }
    } catch (error) {
      console.error('Failed to load agent governance settings:', error);
      // Keep defaults on error
    } finally {
      setLoadingAgentSettings(false);
    }
  };

  // Save agent governance settings
  const saveAgentGovernanceSettings = async () => {
    setSavingAgentSettings(true);
    setAgentSettingsMessage({ type: '', text: '' });
    try {
      await agentAPI.updateSettings(agentGovernanceSettings);
      setAgentSettingsMessage({ type: 'success', text: 'Agent governance settings saved successfully!' });
      setTimeout(() => setAgentSettingsMessage({ type: '', text: '' }), 3000);
    } catch (error) {
      console.error('Failed to save agent governance settings:', error);
      setAgentSettingsMessage({ type: 'error', text: 'Failed to save settings. Please try again.' });
    } finally {
      setSavingAgentSettings(false);
    }
  };

  // Toggle handler for agent governance settings
  const handleAgentSettingToggle = (key) => {
    setAgentGovernanceSettings(prev => ({ ...prev, [key]: !prev[key] }));
  };

  // Input change handler for agent governance settings
  const handleAgentSettingChange = (key, value) => {
    setAgentGovernanceSettings(prev => ({ ...prev, [key]: value }));
  };

  // Debug: Log when component mounts
  useEffect(() => {
    console.log('Settings component mounted');
    console.log('showCalendlyModal initial state:', showCalendlyModal);
  }, []);

  // Fetch security audit logs when account-management section is active
  useEffect(() => {
    if (activeSection === 'account-management') {
      fetchSecurityAuditLogs();
    }
  }, [activeSection]);

  // Function to fetch security audit logs from API
  const fetchSecurityAuditLogs = async () => {
    setLoadingAuditLogs(true);
    setAuditLogsError(null);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE}/api/v1/admin/account-management/security-audit-log?limit=10`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success' && data.data && data.data.logs) {
          setSecurityAuditLogs(data.data.logs);
        }
      } else {
        console.error('Failed to fetch security audit logs:', response.status);
        setAuditLogsError('Failed to load security events');
      }
    } catch (error) {
      console.error('Error fetching security audit logs:', error);
      setAuditLogsError('Error loading security events');
    } finally {
      setLoadingAuditLogs(false);
    }
  };

  // Helper function to get status badge style
  const getStatusBadgeStyle = (status) => {
    const styles = {
      'Success': { background: '#dcfce7', color: '#166534' },
      'Created': { background: '#dbeafe', color: '#1e40af' },
      'Modified': { background: '#fef3c7', color: '#92400e' },
      'Deleted': { background: '#fee2e2', color: '#991b1b' },
      'Enabled': { background: '#dcfce7', color: '#166534' },
      'Disabled': { background: '#fee2e2', color: '#991b1b' },
      'Completed': { background: '#dbeafe', color: '#1e40af' },
      'Sent': { background: '#e0e7ff', color: '#3730a3' },
      'Reset': { background: '#fef3c7', color: '#92400e' },
      'Changed': { background: '#fef3c7', color: '#92400e' },
      'Revoked': { background: '#fee2e2', color: '#991b1b' },
      'Suspended': { background: '#fee2e2', color: '#991b1b' },
      'Reinstated': { background: '#dcfce7', color: '#166534' },
      'Started': { background: '#e0e7ff', color: '#3730a3' },
      'Ended': { background: '#f1f5f9', color: '#475569' },
    };
    return styles[status] || { background: '#f1f5f9', color: '#475569' };
  };

  const toggleSection = (section) => {
    setExpandedSections({
      ...expandedSections,
      [section]: !expandedSections[section]
    });
  };

  // Load user profile
  const loadUserProfile = async () => {
    setLoadingProfile(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE}/api/v1/users/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        // Split full_name into first_name and last_name
        const nameParts = (data.full_name || '').trim().split(' ');
        const firstName = nameParts[0] || '';
        const lastName = nameParts.slice(1).join(' ') || '';
        setUserProfile({
          id: data.id || null,
          slug: data.slug || '',
          first_name: firstName,
          last_name: lastName,
          email: data.email || '',
          phone: data.phone || '',
          nmls_number: data.nmls_number || '',
          job_title: data.job_title || '',
          work_hours_start: data.work_hours_start || '09:00',
          work_hours_end: data.work_hours_end || '17:00',
          work_days: data.work_days || ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
          daily_hours: data.daily_hours || {},
          blocked_times: data.blocked_times || []
        });
      }
    } catch (error) {
      console.error('Error loading profile:', error);
      setProfileMessage({ type: 'error', text: 'Failed to load profile. Please try refreshing the page.' });
    } finally {
      setLoadingProfile(false);
    }
  };

  // Save user profile
  const saveUserProfile = async () => {
    setSavingProfile(true);
    setProfileMessage({ type: '', text: '' });
    try {
      const token = localStorage.getItem('token');
      // Combine first_name and last_name into full_name for the API
      const fullName = `${userProfile.first_name} ${userProfile.last_name}`.trim();
      const response = await fetch(`${API_BASE}/api/v1/users/me`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          full_name: fullName,
          phone: userProfile.phone,
          nmls_number: userProfile.nmls_number,
          job_title: userProfile.job_title,
          work_hours_start: userProfile.work_hours_start,
          work_hours_end: userProfile.work_hours_end,
          work_days: userProfile.work_days,
          daily_hours: userProfile.daily_hours,
          blocked_times: userProfile.blocked_times
        })
      });
      if (response.ok) {
        setProfileMessage({ type: 'success', text: 'Profile updated successfully!' });
        // Update localStorage user data
        const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
        localStorage.setItem('user', JSON.stringify({ ...storedUser, full_name: fullName }));
      } else {
        const error = await response.json();
        setProfileMessage({ type: 'error', text: error.detail || 'Failed to update profile' });
      }
    } catch (error) {
      console.error('Error saving profile:', error);
      setProfileMessage({ type: 'error', text: 'Failed to update profile' });
    } finally {
      setSavingProfile(false);
    }
  };

  // Change password
  const changePassword = async () => {
    if (passwordData.new_password !== passwordData.confirm_password) {
      setProfileMessage({ type: 'error', text: 'New passwords do not match' });
      return;
    }
    if (passwordData.new_password.length < 6) {
      setProfileMessage({ type: 'error', text: 'Password must be at least 6 characters' });
      return;
    }
    setChangingPassword(true);
    setProfileMessage({ type: '', text: '' });
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE}/api/v1/users/me/password`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          current_password: passwordData.current_password,
          new_password: passwordData.new_password
        })
      });
      if (response.ok) {
        setProfileMessage({ type: 'success', text: 'Password changed successfully!' });
        setPasswordData({ current_password: '', new_password: '', confirm_password: '' });
      } else {
        const error = await response.json();
        setProfileMessage({ type: 'error', text: error.detail || 'Failed to change password' });
      }
    } catch (error) {
      console.error('Error changing password:', error);
      setProfileMessage({ type: 'error', text: 'Failed to change password' });
    } finally {
      setChangingPassword(false);
    }
  };

  // Load profile when profile section is active
  useEffect(() => {
    if (activeSection === 'profile-info' || activeSection === 'account-settings' || activeSection === 'security' || activeSection === 'work-hours') {
      loadUserProfile();
    }
  }, [activeSection]);

  // Load agent governance settings when section is active
  useEffect(() => {
    if (activeSection === 'agent-governance-system' || activeSection === 'agent-governance-thresholds' ||
        activeSection === 'agent-governance-costs' || activeSection === 'agent-governance-alerts' ||
        activeSection === 'agent-governance-compliance' || activeSection === 'agent-governance-gym') {
      loadAgentGovernanceSettings();
    }
  }, [activeSection]);

  const loadTeamMembers = async () => {
    setLoadingTeam(true);
    try {
      const data = await teamAPI.getMembers();
      // API returns array directly from ensureArray, or handle object formats
      let members = [];
      if (Array.isArray(data)) {
        members = data;
      } else if (data && typeof data === 'object') {
        members = data.team_members || data.members || [];
      }
      // Map to expected format with name field for display
      const mappedMembers = members.map(m => ({
        ...m,
        name: m.full_name || `${m.first_name || ''} ${m.last_name || ''}`.trim() || 'Unknown',
        user_id: m.id,
        loan_count: m.tasks_count || 0
      }));
      setTeamMembers(mappedMembers);
      setAvailableRoles([]); // Team members don't use the old role system
    } catch (error) {
      console.error('Error loading team members:', error);
      setTeamMembers([]); // Set empty array on error to prevent crashes
    } finally {
      setLoadingTeam(false);
    }
  };

  useEffect(() => {
    if (activeSection === 'team-members') {
      loadTeamMembers();
    }
  }, [activeSection]);

  const leadStages = [
    // Lead Stages
    { value: 'new', label: 'New Lead' },
    { value: 'contacted', label: 'Contacted' },
    { value: 'qualified', label: 'Qualified' },
    { value: 'meeting_scheduled', label: 'Meeting Scheduled' },
    // Application & Processing
    { value: 'application_started', label: 'Application Started' },
    { value: 'disclosed', label: 'Disclosed' },
    { value: 'processing', label: 'Processing' },
    { value: 'submitted', label: 'Submitted to UW' },
    { value: 'uw_received', label: 'UW Received' },
    // Underwriting Outcomes
    { value: 'approved', label: 'Approved' },
    { value: 'approved_with_conditions', label: 'Approved with Conditions' },
    { value: 'suspended', label: 'Suspended' },
    // Last Mile - Clear to Close & Closing
    { value: 'last_mile', label: 'Last Mile' },
    { value: 'ctc', label: 'Clear to Close (CTC)' },
    { value: 'closing_scheduled', label: 'Closing Scheduled' },
    { value: 'closing_docs_sent', label: 'Closing Docs Sent' },
    { value: 'closing', label: 'At Closing' },
    { value: 'funded', label: 'Funded' },
    // Post-Close
    { value: 'post_close', label: 'Post-Close' },
    { value: 'closed', label: 'Closed (Complete)' },
    // Other
    { value: 'on_hold', label: 'On Hold' },
    { value: 'lost', label: 'Lost/Withdrawn' }
  ];

  // Fetch Calendly connection status
  const fetchCalendlyStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/status?user_id=${currentUser?.id}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        console.log('[Calendly] Status:', data);
        setCalendlyStatus({
          isConnected: data.is_connected,
          userName: data.calendly_user_name,
          userEmail: data.calendly_user_email,
          selectedEventTypeName: data.selected_event_type_name,
          connectedAt: data.connected_at,
          syncToSmartScheduler: data.sync_to_smart_scheduler,
          autoCreateContacts: data.auto_create_contacts
        });

        if (data.is_connected) {
          const newConnected = new Set(connectedIntegrations);
          newConnected.add('calendly');
          setConnectedIntegrations(newConnected);
          // Also fetch event types if connected
          await fetchCalendlyEventTypes();
        }
      }
    } catch (error) {
      console.error('[Calendly] Error fetching status:', error);
    }
  };

  const connectCalendly = async () => {
    console.log('Connect Calendly button clicked - initiating OAuth flow');
    setLoadingCalendly(true);

    try {
      // Get OAuth authorization URL from backend
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/connect?user_id=${currentUser?.id}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        // Store state in localStorage for callback verification
        localStorage.setItem('calendly_oauth_state', data.state);
        // Redirect to Calendly OAuth
        window.location.href = data.authorization_url;
      } else {
        const error = await response.json();
        console.error('[Calendly] OAuth init failed:', error);
        toast.error('Failed to initiate Calendly connection. Please try again.');
      }
    } catch (error) {
      console.error('[Calendly] Error initiating OAuth:', error);
      toast.error('Error connecting to Calendly: ' + error.message);
    } finally {
      setLoadingCalendly(false);
    }
  };

  const disconnectCalendly = async () => {
    if (!window.confirm('Are you sure you want to disconnect Calendly? This will remove your calendar sync.')) {
      return;
    }

    setLoadingCalendly(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/disconnect?user_id=${currentUser?.id}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        setCalendlyStatus({
          isConnected: false,
          userName: null,
          userEmail: null,
          selectedEventTypeName: null,
          connectedAt: null,
          syncToSmartScheduler: true,
          autoCreateContacts: true
        });
        setCalendlyEventTypes([]);

        const newConnected = new Set(connectedIntegrations);
        newConnected.delete('calendly');
        setConnectedIntegrations(newConnected);

        toast.success('Calendly disconnected successfully');
      } else {
        const error = await response.json();
        toast.error(`Failed to disconnect: ${error.detail || 'Please try again'}`);
      }
    } catch (error) {
      console.error('[Calendly] Error disconnecting:', error);
      toast.error('Error disconnecting Calendly: ' + error.message);
    } finally {
      setLoadingCalendly(false);
    }
  };

  const updateCalendlySettings = async (updates) => {
    setLoadingCalendly(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/settings?user_id=${currentUser?.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(updates)
      });

      if (response.ok) {
        const data = await response.json();
        setCalendlyStatus(prev => ({
          ...prev,
          selectedEventTypeName: data.selected_event_type_name,
          syncToSmartScheduler: data.sync_to_smart_scheduler,
          autoCreateContacts: data.auto_create_contacts
        }));
        toast.success('Settings updated successfully');
      } else {
        const error = await response.json();
        toast.error(`Failed to update settings: ${error.detail || 'Please try again'}`);
      }
    } catch (error) {
      console.error('[Calendly] Error updating settings:', error);
      toast.error('Error updating settings: ' + error.message);
    } finally {
      setLoadingCalendly(false);
    }
  };

  const saveCalendlyConnection = async () => {
    // Legacy function for API key - redirect to OAuth
    connectCalendly();
  };

  const fetchCalendlyEventTypes = async () => {
    setLoadingCalendly(true);
    try {
      console.log('[Calendly] Fetching event types...');
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/event-types?user_id=${currentUser?.id}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      console.log('[Calendly] Response status:', response.status);

      if (response.ok) {
        const data = await response.json();
        console.log('[Calendly] Event types data:', data);
        setCalendlyEventTypes(data.event_types || []);

        // Update connected integrations status
        const newConnected = new Set(connectedIntegrations);
        if (data.event_types && data.event_types.length > 0) {
          newConnected.add('calendly');
          console.log('[Calendly] ✓ Connected! Found', data.event_types.length, 'event types');
        } else {
          newConnected.delete('calendly');
          console.log('[Calendly] ✗ No event types found');
        }
        setConnectedIntegrations(newConnected);
      } else {
        const errorText = await response.text();
        console.error('[Calendly] Failed to fetch event types. Status:', response.status, 'Error:', errorText);
        setCalendlyEventTypes([]);

        // Mark as disconnected
        const newConnected = new Set(connectedIntegrations);
        newConnected.delete('calendly');
        setConnectedIntegrations(newConnected);
      }
    } catch (error) {
      console.error('[Calendly] Error fetching event types:', error);
      setCalendlyEventTypes([]);

      // Mark as disconnected on error
      const newConnected = new Set(connectedIntegrations);
      newConnected.delete('calendly');
      setConnectedIntegrations(newConnected);
    } finally {
      setLoadingCalendly(false);
    }
  };

  const fetchCalendarMappings = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/calendar-mappings`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      const data = await response.json();
      setCalendarMappings(data.mappings || []);
    } catch (error) {
      console.error('Error fetching calendar mappings:', error);
    }
  };

  const createCalendarMapping = async () => {
    if (!selectedStage || !selectedEventType) {
      toast.error('Please select both a lead stage and a calendar type');
      return;
    }

    const eventType = calendlyEventTypes.find(et => et.uri.includes(selectedEventType));
    if (!eventType) {
      toast.error('Event type not found');
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/calendar-mappings`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          stage: selectedStage,
          event_type_uuid: selectedEventType,
          event_type_name: eventType.name,
          event_type_url: eventType.scheduling_url
        })
      });

      if (response.ok) {
        toast.success('Calendar mapping saved successfully!');
        setSelectedStage('');
        setSelectedEventType('');
        fetchCalendarMappings();
      } else {
        toast.error('Failed to save calendar mapping');
      }
    } catch (error) {
      console.error('Error creating calendar mapping:', error);
      toast.error('Error saving calendar mapping');
    }
  };

  const fetchApiKeys = async () => {
    setLoadingApiKeys(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }

      const data = await response.json();

      // Ensure data is an array
      if (Array.isArray(data)) {
        setApiKeys(data);
      } else {
        console.error('API keys response is not an array:', data);
        setApiKeys([]);
      }
    } catch (error) {
      console.error('Error fetching API keys:', error);
      setApiKeys([]);
    } finally {
      setLoadingApiKeys(false);
    }
  };

  const createApiKey = async () => {
    if (!newApiKeyName.trim()) {
      toast.error('Please enter a name for the API key');
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name: newApiKeyName })
      });

      if (response.ok) {
        const data = await response.json();
        setCreatedKey(data.key);
        setNewApiKeyName('');
        fetchApiKeys();
        toast.success('API key created successfully! Make sure to copy it now - you won\'t be able to see it again.');
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        console.error('Failed to create API key:', response.status, errorData);
        toast.error(`Failed to create API key: ${errorData.detail || errorData.message || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error creating API key:', error);
      toast.error(`Error creating API key: ${error.message}`);
    }
  };

  const revokeApiKey = async (keyId, keyName) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys/${keyId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        toast.success('API key revoked successfully');
        fetchApiKeys();
      } else {
        toast.error('Failed to revoke API key');
      }
    } catch (error) {
      console.error('Error revoking API key:', error);
      toast.error('Error revoking API key');
    }
  };

  // API Base URL
  // Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE_URL = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

  const runDatabaseMigration = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/migrations/add-external-message-id`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        }
      });

      const data = await response.json();

      if (data.success) {
        toast.success(`✅ Migration Successful!\n\n${data.message}\n\nNow click "Sync Now" to pull in emails.`);
      } else {
        toast.error(`❌ Migration Failed:\n\n${data.message || data.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Migration error:', error);
      toast.error(`❌ Migration Error:\n\n${error.message}`);
    }
  };

  const createSampleTasks = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/create-sample-tasks`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        }
      });

      const data = await response.json();

      if (data.success) {
        toast.success(`✅ Success!\n\n${data.message}\n\nGo to Reconciliation tab to see the tasks.`);
      } else {
        toast.error(`❌ Failed:\n\n${data.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Create tasks error:', error);
      toast.error(`❌ Error:\n\n${error.message}`);
    }
  };

  // User Management Functions
  const loadUsers = async () => {
    setLoadingUsers(true);
    setUsersError(null);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        throw new Error(`Failed to load users: ${response.status}`);
      }

      const data = await response.json();
      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load users:', err);
      setUsersError('Failed to load users. Please try again.');
      setUsers([]);
    } finally {
      setLoadingUsers(false);
    }
  };

  const handleAddUser = async (e) => {
    e.preventDefault();
    if (!newUser.email || !newUser.first_name || !newUser.last_name) {
      toast.error('First name, last name, and email are required');
      return;
    }

    // Map frontend roles to backend permission_role values
    const roleMapping = {
      'loan_officer': 'sales',
      'admin': 'admin',
      'processor': 'processing',
      'underwriter': 'operations',
      'manager': 'management',
      'application_analyst': 'operations'
    };

    setAddingUser(true);
    try {
      const token = localStorage.getItem('token');
      const fullName = `${newUser.first_name} ${newUser.last_name}`.trim();
      const permissionRole = roleMapping[newUser.role] || 'sales';

      console.log('Inviting user to:', `${API_BASE_URL}/api/v1/invitations`);
      console.log('Request payload:', { email: newUser.email, full_name: fullName, role: permissionRole, send_email: true });

      const response = await fetch(`${API_BASE_URL}/api/v1/invitations`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email: newUser.email,
          full_name: fullName,
          role: permissionRole,
          send_email: true
        })
      });

      console.log('Response status:', response.status, response.statusText);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Error response:', errorText);
        let errorDetail = `Failed to invite user (${response.status})`;
        try {
          const errorData = JSON.parse(errorText);
          errorDetail = errorData.detail || errorData.error || errorData.message || errorDetail;
        } catch (e) {
          errorDetail = errorText || errorDetail;
        }
        throw new Error(errorDetail);
      }

      // Reset form and close modal
      setNewUser({
        email: '',
        first_name: '',
        last_name: '',
        role: 'loan_officer',
        is_active: true
      });
      setShowAddUserModal(false);

      // Reload users list
      await loadUsers();
      toast.success('Invitation sent! The user will receive an email to set up their account.');
    } catch (err) {
      console.error('Failed to invite user:', err);
      toast.error(err.message || 'Failed to invite user');
    } finally {
      setAddingUser(false);
    }
  };

  const handleSelectUser = (userId) => {
    setSelectedUsers(prev => {
      if (prev.includes(userId)) {
        return prev.filter(id => id !== userId);
      } else {
        return [...prev, userId];
      }
    });
  };

  const handleSelectAll = () => {
    const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
    const selectableUsers = users.filter(u => u.id !== currentUser.id).map(u => u.id);

    if (selectedUsers.length === selectableUsers.length) {
      setSelectedUsers([]);
    } else {
      setSelectedUsers(selectableUsers);
    }
  };

  const handleBulkDelete = async () => {
    if (selectedUsers.length === 0) {
      toast.error('No users selected');
      return;
    }

    const confirmDelete = window.confirm(
      `Are you sure you want to delete ${selectedUsers.length} user(s)? This action cannot be undone.\n\nNote: Deletion may take a few seconds per user.`
    );

    if (!confirmDelete) return;

    setDeletingUsers(true);
    try {
      const token = localStorage.getItem('token');
      let successCount = 0;
      let failCount = 0;
      const errors = [];

      for (const userId of selectedUsers) {
        try {
          // Use AbortController for timeout (60 seconds per user)
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 60000);

          const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` },
            signal: controller.signal
          });

          clearTimeout(timeoutId);

          if (response.ok) {
            successCount++;
          } else {
            // Check if user was actually deleted despite error response
            const checkResponse = await fetch(`${API_BASE_URL}/api/v1/admin/users`, {
              headers: { 'Authorization': `Bearer ${token}` }
            });
            if (checkResponse.ok) {
              const usersData = await checkResponse.json();
              const userList = usersData.users || usersData || [];
              const userStillExists = userList.some(u => u.id === userId);
              if (!userStillExists) {
                // User was deleted despite error response
                successCount++;
                continue;
              }
            }

            failCount++;
            try {
              const errorData = await response.json();
              errors.push(`User ${userId}: ${errorData.detail || response.statusText || 'Unknown error'}`);
            } catch {
              errors.push(`User ${userId}: ${response.statusText || 'Unknown error'}`);
            }
          }
        } catch (err) {
          // Check if it's a timeout
          if (err.name === 'AbortError') {
            // Request timed out - check if user was actually deleted
            try {
              const checkResponse = await fetch(`${API_BASE_URL}/api/v1/admin/users`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
              });
              if (checkResponse.ok) {
                const usersData = await checkResponse.json();
                const userList = usersData.users || usersData || [];
                const userStillExists = userList.some(u => u.id === userId);
                if (!userStillExists) {
                  successCount++;
                  continue;
                }
              }
            } catch {}
            failCount++;
            errors.push(`User ${userId}: Request timed out`);
          } else {
            failCount++;
            errors.push(`User ${userId}: ${err.message || 'Network error'}`);
          }
        }
      }

      if (errors.length > 0) {
        console.error('Delete errors:', errors);
      }

      setSelectedUsers([]);
      await loadUsers();

      if (failCount === 0) {
        toast.success(`Successfully deleted ${successCount} user(s)`);
      } else {
        const errorDetails = errors.length > 0 ? `\n\nErrors:\n${errors.slice(0, 5).join('\n')}${errors.length > 5 ? `\n...and ${errors.length - 5} more` : ''}` : '';
        toast.error(`Deleted ${successCount} user(s). Failed to delete ${failCount} user(s).${errorDetails}`);
      }
    } catch (err) {
      console.error('Bulk delete failed:', err);
      toast.error('Failed to delete users');
    } finally {
      setDeletingUsers(false);
    }
  };

  const handleToggleActive = async (userId, currentStatus) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ is_active: !currentStatus })
      });

      if (!response.ok) {
        throw new Error('Failed to update user status');
      }

      await loadUsers();
    } catch (err) {
      console.error('Failed to update user:', err);
      toast.error('Failed to update user status');
    }
  };

  const handleToggleVerified = async (userId, currentStatus) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email_verified: !currentStatus })
      });

      if (!response.ok) {
        throw new Error('Failed to update verification');
      }

      await loadUsers();
    } catch (err) {
      console.error('Failed to update user:', err);
      toast.error('Failed to update user verification');
    }
  };

  const handleUpdateRole = async (userId, newRole) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ role: newRole })
      });

      if (!response.ok) {
        throw new Error('Failed to update role');
      }

      await loadUsers();
      setEditingUser(null);
    } catch (err) {
      console.error('Failed to update role:', err);
      toast.error('Failed to update user role');
    }
  };

  const handleDeleteUser = async (userId) => {
    const currentUser = JSON.parse(localStorage.getItem('user') || '{}');

    if (currentUser.id === userId) {
      toast.error('You cannot delete your own account. Please contact another administrator.');
      return;
    }

    try {
      const token = localStorage.getItem('token');

      if (!token) {
        toast.error('You are not authenticated. Please log in again.');
        return;
      }

      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to delete user');
      }

      toast.success('User deleted successfully');
      await loadUsers();
    } catch (err) {
      console.error('Failed to delete user:', err);
      toast.error(err.message || 'Failed to delete user');
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  const testClickToCall = () => {
    if (!testPhoneNumber) {
      addTestResult('Click-to-Call', 'error', 'Please enter a phone number');
      return;
    }

    try {
      const cleanPhone = testPhoneNumber.replace(/[^0-9+]/g, '');
      window.open(`tel:${cleanPhone}`, '_self');
      addTestResult('Click-to-Call', 'success', `Dialer opened for ${testPhoneNumber}`);
    } catch (error) {
      addTestResult('Click-to-Call', 'error', `Failed: ${error.message}`);
    }
  };

  const testSMS = () => {
    if (!testPhoneNumber) {
      addTestResult('SMS', 'error', 'Please enter a phone number');
      return;
    }

    try {
      const cleanPhone = testPhoneNumber.replace(/[^0-9+]/g, '');
      window.open(`sms:${cleanPhone}`, '_blank');
      addTestResult('SMS', 'success', `Messaging app opened for ${testPhoneNumber}`);
    } catch (error) {
      addTestResult('SMS', 'error', `Failed: ${error.message}`);
    }
  };

  const addTestResult = (feature, status, message) => {
    const result = {
      feature,
      status,
      message,
      timestamp: new Date().toLocaleTimeString()
    };
    setTestResults(prev => [result, ...prev].slice(0, 5)); // Keep last 5 results
  };

  // IT Helpdesk Functions
  const fetchItTickets = async () => {
    setLoadingTickets(true);
    try {
      const token = localStorage.getItem('token');
      const statusParam = ticketStatusFilter !== 'all' ? `?status=${ticketStatusFilter}` : '';
      const response = await fetch(`${API_BASE_URL}/api/v1/it-helpdesk/tickets${statusParam}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setItTickets(data.tickets || []);
      } else {
        console.error('Failed to fetch IT tickets');
        setItTickets([]);
      }
    } catch (error) {
      console.error('Error fetching IT tickets:', error);
      setItTickets([]);
    } finally {
      setLoadingTickets(false);
    }
  };

  const submitItTicket = async () => {
    if (!newTicket.description.trim()) {
      toast.error('Please describe the problem');
      return;
    }

    setSubmittingTicket(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/it-helpdesk/submit`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(newTicket)
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(`Ticket created! AI diagnosis: ${data.root_cause}`);

        // Reset form
        setNewTicket({
          title: '',
          description: '',
          category: 'dev_env',
          urgency: 'normal',
          affected_system: '',
          affected_project: '',
          logs_attached: []
        });

        // Refresh ticket list
        fetchItTickets();
      } else {
        const error = await response.json();
        toast.error(`Failed to submit ticket: ${error.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error submitting ticket:', error);
      toast.error('Error submitting ticket. Please try again.');
    } finally {
      setSubmittingTicket(false);
    }
  };

  const approveTicket = async (ticketId) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/it-helpdesk/tickets/${ticketId}/approve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        toast.success('Fix approved! You can now execute the commands.');
        fetchItTickets();
      } else {
        toast.error('Failed to approve fix');
      }
    } catch (error) {
      console.error('Error approving ticket:', error);
      toast.error('Error approving ticket');
    }
  };

  const resolveTicket = async (ticketId) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/it-helpdesk/tickets/${ticketId}/resolve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          resolution_notes: resolutionNotes
        })
      });

      if (response.ok) {
        toast.success('Ticket marked as resolved!');
        setResolutionNotes('');
        setSelectedTicket(null);
        fetchItTickets();
      } else {
        toast.error('Failed to resolve ticket');
      }
    } catch (error) {
      console.error('Error resolving ticket:', error);
      toast.error('Error resolving ticket');
    }
  };

  const availableIntegrations = [
    {
      id: 'gmail',
      name: 'Gmail',
      description: 'Sync Gmail emails and contacts with your CRM',
      icon: '',
      color: '#ea4335',
      category: 'Email'
    },
    {
      id: 'outlook-email',
      name: 'Outlook Email',
      description: 'Sync your Microsoft 365 / Outlook emails with loan files',
      icon: '📧',
      color: '#0078d4',
      category: 'Email'
    },
    {
      id: 'outlook-calendar',
      name: 'Outlook Calendar',
      description: 'Sync your Microsoft 365 / Outlook calendar events',
      icon: '📅',
      color: '#0078d4',
      category: 'Calendar'
    },
    {
      id: 'teams',
      name: 'Microsoft Teams',
      description: 'Send messages, make calls, and collaborate with your team',
      icon: '',
      color: '#6264a7',
      category: 'Communication'
    },
    {
      id: 'zoom',
      name: 'Zoom',
      description: 'Host virtual meetings and consultations with clients',
      icon: '',
      color: '#2d8cff',
      category: 'Communication'
    },
    {
      id: 'calendly',
      name: 'Calendly',
      description: 'Automated scheduling for client meetings',
      icon: '',
      color: '#006bff',
      category: 'Scheduling'
    },
    {
      id: 'docusign',
      name: 'DocuSign',
      description: 'Send and sign loan documents electronically',
      icon: '',
      color: '#ffd500',
      category: 'Documents'
    },
    {
      id: 'salesforce',
      name: 'Salesforce',
      description: 'Sync contacts and deals with your Salesforce CRM',
      icon: '',
      color: '#00a1e0',
      category: 'CRM'
    },
    {
      id: 'hubspot',
      name: 'HubSpot',
      description: 'Marketing automation and lead nurturing',
      icon: '',
      color: '#ff7a59',
      category: 'Marketing'
    },
    {
      id: 'mailchimp',
      name: 'Mailchimp',
      description: 'Email marketing campaigns for your clients',
      icon: '',
      color: '#ffe01b',
      category: 'Marketing'
    },
    {
      id: 'ringcentral',
      name: 'RingCentral',
      description: 'Click-to-call and SMS via RingCentral phone system',
      icon: '',
      color: '#0073ae',
      category: 'Communication'
    },
    {
      id: 'slack',
      name: 'Slack',
      description: 'Get notifications and updates in your Slack workspace',
      icon: '',
      color: '#4a154b',
      category: 'Communication'
    },
    {
      id: 'zapier',
      name: 'Zapier',
      description: 'Connect with 5,000+ apps through automated workflows',
      icon: '',
      color: '#ff4a00',
      category: 'Automation'
    },
    {
      id: 'synthflow',
      name: 'Synthflow AI',
      description: 'AI-powered voice agents for automated client calls and lead qualification',
      icon: '',
      color: '#218D8D',
      category: 'AI & Automation'
    },
    {
      id: 'recallai',
      name: 'Recall.ai',
      description: 'Record and transcribe meetings from Zoom, Teams, and Google Meet with AI',
      icon: '🎙️',
      color: '#10b981',
      category: 'AI & Automation'
    },
    {
      id: 'stripe',
      name: 'Stripe',
      description: 'Collect payments and processing fees',
      icon: '💳',
      color: '#635bff',
      category: 'Payments'
    },
    {
      id: 'quickbooks',
      name: 'QuickBooks',
      description: 'Sync financial data and commission tracking',
      icon: '💰',
      color: '#2ca01c',
      category: 'Accounting'
    },
    {
      id: 'google-calendar',
      name: 'Google Calendar',
      description: 'Sync appointments with Google Calendar',
      icon: '📆',
      color: '#4285f4',
      category: 'Calendar'
    },
    {
      id: 'google-drive',
      name: 'Google Drive',
      description: 'Store and share loan documents in Google Drive',
      icon: '📂',
      color: '#4285f4',
      category: 'Documents'
    }
  ];

  // Gmail connection functions
  const checkGmailStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/gmail/status`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setGmailStatus(data);

        // Update connected integrations
        const newConnected = new Set(connectedIntegrations);
        if (data.connected) {
          newConnected.add('gmail');
        } else {
          newConnected.delete('gmail');
        }
        setConnectedIntegrations(newConnected);
      }
    } catch (error) {
      console.error('Error checking Gmail status:', error);
    }
  };

  const connectGmail = async () => {
    setLoadingGmail(true);
    try {
      // Get auth URL from backend
      const response = await fetch(`${API_BASE_URL}/api/v1/gmail/auth-url`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to get Gmail auth URL');
      }

      const data = await response.json();

      // Open OAuth popup
      const width = 600;
      const height = 700;
      const left = (window.screen.width / 2) - (width / 2);
      const top = (window.screen.height / 2) - (height / 2);

      const popup = window.open(
        data.auth_url,
        'Gmail Login',
        `width=${width},height=${height},top=${top},left=${left}`
      );

      if (!popup) {
        toast.error('Popup was blocked! Please allow popups for this site and try again.');
        setLoadingGmail(false);
        return;
      }

      // Clear any previous OAuth result
      localStorage.removeItem('oauth_result');

      // Listen for message from popup - may be blocked by COOP
      const handleMessage = (event) => {
        if (event.origin !== window.location.origin) return;

        if (event.data && (event.data.type === 'gmail_connected' || event.data.type === 'GMAIL_OAUTH_SUCCESS')) {
          clearInterval(checkPopup);
          window.removeEventListener('message', handleMessage);
          localStorage.removeItem('oauth_result');
          setGmailStatus({
            connected: true,
            email: event.data.email,
            connected_at: new Date().toISOString()
          });

          const newConnected = new Set(connectedIntegrations);
          newConnected.add('gmail');
          setConnectedIntegrations(newConnected);
          setLoadingGmail(false);
          if (popup && !popup.closed) {
            popup.close();
          }
          toast.success('Gmail connected successfully!');
        } else if (event.data && event.data.type === 'GMAIL_OAUTH_ERROR') {
          clearInterval(checkPopup);
          window.removeEventListener('message', handleMessage);
          localStorage.removeItem('oauth_result');
          setLoadingGmail(false);
          if (popup && !popup.closed) {
            popup.close();
          }
          toast.error('Failed to connect Gmail: ' + (event.data.error || 'Unknown error'));
        }
      };

      window.addEventListener('message', handleMessage);

      // Poll for popup close AND localStorage result (fallback when COOP blocks postMessage)
      const checkPopup = setInterval(async () => {
        // Check localStorage for OAuth result
        const storedResult = localStorage.getItem('oauth_result');
        if (storedResult) {
          try {
            const result = JSON.parse(storedResult);
            // Only process recent results (within last 30 seconds)
            if (Date.now() - result.timestamp < 30000) {
              clearInterval(checkPopup);
              localStorage.removeItem('oauth_result');
              window.removeEventListener('message', handleMessage);
              if (popup && !popup.closed) {
                popup.close();
              }
              setLoadingGmail(false);

              if (result.type === 'GMAIL_OAUTH_SUCCESS') {
                await checkGmailStatus();
                toast.success('Gmail connected successfully!');
              } else if (result.type === 'GMAIL_OAUTH_ERROR') {
                toast.error('Failed to connect Gmail: ' + (result.error || 'Unknown error'));
              }
              return;
            }
          } catch (e) {
            console.error('Error parsing OAuth result:', e);
          }
        }

        if (popup.closed) {
          clearInterval(checkPopup);
          window.removeEventListener('message', handleMessage);
          setLoadingGmail(false);
          checkGmailStatus();
        }
      }, 500);

    } catch (error) {
      console.error('Error connecting Gmail:', error);
      toast.error('Failed to connect Gmail: ' + error.message);
      setLoadingGmail(false);
    }
  };

  const disconnectGmail = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/gmail/disconnect`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        setGmailStatus({
          connected: false,
          email: null,
          connected_at: null
        });

        const newConnected = new Set(connectedIntegrations);
        newConnected.delete('gmail');
        setConnectedIntegrations(newConnected);
      } else {
        throw new Error('Failed to disconnect Gmail');
      }
    } catch (error) {
      console.error('Error disconnecting Gmail:', error);
      toast.error('Failed to disconnect Gmail');
    }
  };

  // Microsoft/Outlook connection functions
  const checkMicrosoftStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/status`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        // Map backend field names to frontend state shape
        setMicrosoftStatus({
          connected: data.connected || false,
          email: data.email_address || data.email || null,
          sync_enabled: data.sync_enabled || false,
          last_sync_at: data.last_sync_at || null,
          connected_at: data.connected_at || null,
        });

        const newConnected = new Set(connectedIntegrations);
        if (data.connected) {
          newConnected.add('outlook-email');
          newConnected.add('outlook-calendar');
        } else {
          newConnected.delete('outlook-email');
          newConnected.delete('outlook-calendar');
        }
        setConnectedIntegrations(newConnected);
      }
    } catch (error) {
      console.error('Error checking Microsoft status:', error);
    }
  };

  const connectMicrosoft365 = async () => {
    setLoadingMicrosoft(true);
    try {
      // Get the OAuth authorization URL - pass current origin for dynamic redirect URI
      const currentOrigin = window.location.origin;
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/auth-url?origin=${encodeURIComponent(currentOrigin)}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();

        // Open OAuth in a popup window instead of redirecting
        const width = 600;
        const height = 700;
        const left = window.screenX + (window.outerWidth - width) / 2;
        const top = window.screenY + (window.outerHeight - height) / 2;

        const popup = window.open(
          data.auth_url,
          'Microsoft365OAuth',
          `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,resizable=yes`
        );

        // Check if popup was blocked
        if (!popup || popup.closed || typeof popup.closed === 'undefined') {
          setLoadingMicrosoft(false);
          toast.error('Popup was blocked! Please allow popups for this site and try again.\n\nLook for a popup blocker icon in your browser\'s address bar.');
          return;
        }

        // Clear any previous OAuth result
        localStorage.removeItem('oauth_result');

        // Poll for popup closure AND localStorage result (fallback when COOP blocks postMessage)
        const pollTimer = setInterval(async () => {
          // Check localStorage for OAuth result (works even when COOP blocks window.opener)
          const storedResult = localStorage.getItem('oauth_result');
          if (storedResult) {
            try {
              const result = JSON.parse(storedResult);
              // Only process recent results (within last 30 seconds)
              if (Date.now() - result.timestamp < 30000) {
                clearInterval(pollTimer);
                localStorage.removeItem('oauth_result');
                window.removeEventListener('message', handleMessage);
                if (popup && !popup.closed) {
                  popup.close();
                }
                setLoadingMicrosoft(false);

                if (result.type === 'MICROSOFT_OAUTH_SUCCESS') {
                  await checkMicrosoftStatus();
                  toast.success('Microsoft 365 connected successfully!');
                } else if (result.type === 'MICROSOFT_OAUTH_ERROR') {
                  toast.error('Failed to connect Microsoft 365: ' + (result.error || 'Unknown error'));
                }
                return;
              }
            } catch (e) {
              console.error('Error parsing OAuth result:', e);
            }
          }

          // Also check if popup was closed without result
          if (popup.closed) {
            clearInterval(pollTimer);
            window.removeEventListener('message', handleMessage);
            setLoadingMicrosoft(false);
            // Check if connection was successful
            await checkMicrosoftStatus();
          }
        }, 500);

        // Listen for message from popup (OAuth callback page) - may be blocked by COOP
        const handleMessage = async (event) => {
          if (event.origin !== window.location.origin) return;

          if (event.data?.type === 'MICROSOFT_OAUTH_SUCCESS') {
            clearInterval(pollTimer);
            window.removeEventListener('message', handleMessage);
            localStorage.removeItem('oauth_result');
            if (popup && !popup.closed) {
              popup.close();
            }
            setLoadingMicrosoft(false);
            await checkMicrosoftStatus();
            toast.success('Microsoft 365 connected successfully!');
          } else if (event.data?.type === 'MICROSOFT_OAUTH_ERROR') {
            clearInterval(pollTimer);
            window.removeEventListener('message', handleMessage);
            localStorage.removeItem('oauth_result');
            if (popup && !popup.closed) {
              popup.close();
            }
            setLoadingMicrosoft(false);
            toast.error('Failed to connect Microsoft 365: ' + (event.data.error || 'Unknown error'));
          }
        };

        window.addEventListener('message', handleMessage);

        // Timeout after 5 minutes
        setTimeout(() => {
          clearInterval(pollTimer);
          window.removeEventListener('message', handleMessage);
          localStorage.removeItem('oauth_result');
          if (popup && !popup.closed) {
            popup.close();
          }
          setLoadingMicrosoft(false);
        }, 300000);

      } else {
        throw new Error('Failed to get Microsoft auth URL');
      }
    } catch (error) {
      console.error('Error connecting Microsoft:', error);
      toast.error('Failed to connect Microsoft 365: ' + error.message);
      setLoadingMicrosoft(false);
    }
  };

  const disconnectMicrosoft = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/disconnect`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        setMicrosoftStatus({
          connected: false,
          email: null,
          connected_at: null,
          sync_enabled: false,
          last_sync_at: null
        });

        const newConnected = new Set(connectedIntegrations);
        newConnected.delete('outlook-email');
        newConnected.delete('outlook-calendar');
        setConnectedIntegrations(newConnected);
      } else {
        throw new Error('Failed to disconnect Microsoft');
      }
    } catch (error) {
      console.error('Error disconnecting Microsoft:', error);
      toast.error('Failed to disconnect Microsoft 365');
    }
  };

  const syncMicrosoftNow = async () => {
    setSyncingMicrosoft(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/sync-now`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      const data = await response.json();

      if (response.ok) {
        toast.success(`Sync complete! ${data.processed_count || data.emails_synced || 0} emails processed.`);
        checkMicrosoftStatus();
      } else {
        // Show the actual error from backend
        const errorMsg = data.error || data.detail || 'Sync failed';
        if (errorMsg.includes('not connected')) {
          toast.error('Microsoft 365 is not connected. Please connect your account first.');
          checkMicrosoftStatus();
        } else if (errorMsg === 'needs_reauth' || (response.status === 401 && errorMsg.includes('reauth'))) {
          // Token refresh failed - automatically trigger reconnection
          const confirmReconnect = window.confirm(
            'Your Microsoft session has expired. Would you like to reconnect now?'
          );
          if (confirmReconnect) {
            connectMicrosoft365();
          }
        } else if (errorMsg.includes('token') || errorMsg.includes('expired')) {
          // Try to reconnect automatically
          const confirmReconnect = window.confirm(
            'Your Microsoft session has expired. Would you like to reconnect now?'
          );
          if (confirmReconnect) {
            connectMicrosoft365();
          }
        } else {
          toast.error(`Sync failed: ${errorMsg}`);
        }
      }
    } catch (error) {
      console.error('Error syncing Microsoft:', error);
      toast.error('Failed to sync Microsoft emails. Please check your connection and try again.');
    } finally {
      setSyncingMicrosoft(false);
    }
  };

  const syncMicrosoftCalendar = async () => {
    setSyncingCalendar(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/sync-calendar`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      const data = await response.json();

      if (response.ok) {
        toast.success(`Calendar sync complete! ${data.events_synced || 0} events processed.`);
      } else {
        // Show the actual error from backend
        const errorMsg = data.error || data.detail || 'Calendar sync failed';
        if (errorMsg.includes('not connected')) {
          toast.error('Microsoft 365 is not connected. Please connect your account first.');
          checkMicrosoftStatus();
        } else if (errorMsg === 'needs_reauth' || (response.status === 401 && errorMsg.includes('reauth'))) {
          // Token refresh failed - automatically trigger reconnection
          const confirmReconnect = window.confirm(
            'Your Microsoft session has expired. Would you like to reconnect now?'
          );
          if (confirmReconnect) {
            connectMicrosoft365();
          }
        } else if (errorMsg.includes('token') || errorMsg.includes('expired')) {
          // Try to reconnect automatically
          const confirmReconnect = window.confirm(
            'Your Microsoft session has expired. Would you like to reconnect now?'
          );
          if (confirmReconnect) {
            connectMicrosoft365();
          }
        } else {
          toast.error(`Calendar sync failed: ${errorMsg}`);
        }
      }
    } catch (error) {
      console.error('Error syncing calendar:', error);
      toast.error('Failed to sync Outlook calendar. Please check your connection and try again.');
    } finally {
      setSyncingCalendar(false);
    }
  };

  // Microsoft OAuth Configuration functions
  const fetchMicrosoftOAuthConfig = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/oauth-config`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setMicrosoftOAuthConfig({
          client_id: data.client_id || '',
          client_secret: '', // Never returned from server for security
          tenant_id: data.tenant_id || 'common'
        });
      }
    } catch (error) {
      console.error('Error fetching Microsoft OAuth config:', error);
    }
  };

  const saveMicrosoftOAuthConfig = async () => {
    setSavingMicrosoftConfig(true);
    setMicrosoftConfigMessage({ type: '', text: '' });

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/oauth-config`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(microsoftOAuthConfig)
      });

      if (response.ok) {
        setMicrosoftConfigMessage({
          type: 'success',
          text: 'Microsoft OAuth configuration saved! You can now connect your Outlook account.'
        });
        setShowMicrosoftConfig(false);
        // Re-fetch the config to show updated client_id
        await fetchMicrosoftOAuthConfig();
      } else {
        const error = await response.json();
        setMicrosoftConfigMessage({
          type: 'error',
          text: error.detail || 'Failed to save configuration'
        });
      }
    } catch (error) {
      console.error('Error saving Microsoft OAuth config:', error);
      setMicrosoftConfigMessage({
        type: 'error',
        text: 'Error saving configuration: ' + error.message
      });
    } finally {
      setSavingMicrosoftConfig(false);
    }
  };

  // Email Processing Settings functions
  const fetchEmailProcessingSettings = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/user-settings/email-processing`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setEmailProcessingSettings(data);
      }
    } catch (error) {
      console.error('Error fetching email processing settings:', error);
    }
  };

  const saveEmailProcessingSettings = async (newSettings) => {
    setSavingEmailSettings(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/user-settings/email-processing`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(newSettings)
      });
      if (response.ok) {
        setEmailProcessingSettings(newSettings);
      } else {
        console.error('Failed to save email processing settings');
      }
    } catch (error) {
      console.error('Error saving email processing settings:', error);
    } finally {
      setSavingEmailSettings(false);
    }
  };

  const toggleIntegration = (integrationId) => {
    // Navigate to the individual integration detail page
    // Map integration IDs to their detail page section names
    const sectionMapping = {
      'gmail': 'gmail',
      'outlook-email': 'outlook-email',
      'outlook-calendar': 'outlook-calendar',
      'teams': 'teams',
      'zoom': 'zoom',
      'calendly': 'calendly',
      'docusign': 'docusign',
      'salesforce': 'salesforce',
      'hubspot': 'hubspot',
      'mailchimp': 'mailchimp',
      'ringcentral': 'ringcentral',
      'slack': 'slack',
      'zapier': 'zapier',
      'synthflow': 'synthflow',
      'recallai': 'recallai',
      'stripe': 'stripe',
      'quickbooks': 'quickbooks',
      'google-calendar': 'google-calendar',
      'google-drive': 'google-drive'
    };

    const section = sectionMapping[integrationId] || integrationId;
    setActiveSection(section);
  };

  const filteredIntegrations = availableIntegrations.filter(integration =>
    integration.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    integration.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
    integration.category.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const featuredIntegrations = filteredIntegrations.filter(i =>
    ['gmail', 'outlook-email', 'teams', 'zoom', 'docusign', 'calendly'].includes(i.id)
  );

  useEffect(() => {
    if (activeSection === 'integration-marketplace') {
      checkGmailStatus();
      checkMicrosoftStatus();
    }
    if (activeSection === 'outlook-email' || activeSection === 'outlook-calendar') {
      checkMicrosoftStatus();
      fetchMicrosoftOAuthConfig();
      fetchEmailProcessingSettings();
    }
    if (activeSection === 'calendly') {
      fetchCalendlyStatus();
      fetchCalendarMappings();
    }
    if (activeSection === 'it-helpdesk') {
      fetchItTickets();
    }
  }, [activeSection, ticketStatusFilter]);

  const handleLogout = () => {
    if (window.confirm('Are you sure you want to log out?')) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      navigate('/login');
    }
  };

  return (
    <div className="settings-page">
      <div className="settings-header">
        <div className="settings-header-left">
          <h1>Settings</h1>
          <p>Manage your integrations and preferences</p>
        </div>
        <button className="logout-btn-settings" onClick={handleLogout}>
          Logout
        </button>
      </div>

      <div className="settings-content">
        {/* Sidebar - Draggable */}
        <div className="settings-sidebar">
          <div className="sidebar-header">
            <div className="drag-hint-container">
              <span className="drag-icon">☰</span>
              <span className="drag-hint">Drag to reorder</span>
            </div>
            <button className="reset-order-btn" onClick={resetSidebarOrder} title="Reset to default order">
              ↺
            </button>
          </div>
          {sidebarOrder.map((item) => {
            // While permissions are loading, don't hide adminOnly items yet
            // This prevents the race condition where tabs flash in after API responds
            const hideAdminItem = item.adminOnly && !isAdmin && !permissionsLoading;

            // Render User Profile parent with children
            if (item.id === 'user-profile') {
              return (
                <div key={item.id}>
                  <button
                    className={`sidebar-btn parent ${expandedSections.userProfile ? 'expanded' : ''} ${dragOverItem?.id === item.id ? 'drag-over' : ''}`}
                    onClick={() => toggleSection('userProfile')}
                    draggable
                    onDragStart={(e) => handleDragStart(e, item)}
                    onDragEnd={handleDragEnd}
                    onDragOver={(e) => handleDragOver(e, item)}
                    onDragLeave={handleDragLeave}
                    onDrop={(e) => handleDrop(e, item)}
                  >
                    <span>{item.label}</span>
                    <span className="expand-icon">{expandedSections.userProfile ? '▼' : '▶'}</span>
                  </button>
                  {expandedSections.userProfile && (
                    <div className="sidebar-children">
                      <button className={`sidebar-btn child ${activeSection === 'profile-info' ? 'active' : ''}`} onClick={() => setActiveSection('profile-info')}><span>Profile Info</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'account-settings' ? 'active' : ''}`} onClick={() => setActiveSection('account-settings')}><span>Account Settings</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'security' ? 'active' : ''}`} onClick={() => setActiveSection('security')}><span>Security</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'email-signature' ? 'active' : ''}`} onClick={() => setActiveSection('email-signature')}><span>Email Signature</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'work-hours' ? 'active' : ''}`} onClick={() => setActiveSection('work-hours')}><span>Work Hours</span></button>
                    </div>
                  )}
                </div>
              );
            }

            // Render Organizational Settings parent with children (admin-only)
            if (item.id === 'organizational') {
              if (hideAdminItem) return null;
              return (
                <div key={item.id}>
                  <button
                    className={`sidebar-btn parent ${expandedSections.organizational ? 'expanded' : ''} ${dragOverItem?.id === item.id ? 'drag-over' : ''}`}
                    onClick={() => toggleSection('organizational')}
                    draggable
                    onDragStart={(e) => handleDragStart(e, item)}
                    onDragEnd={handleDragEnd}
                    onDragOver={(e) => handleDragOver(e, item)}
                    onDragLeave={handleDragLeave}
                    onDrop={(e) => handleDrop(e, item)}
                  >
                    <span>{item.label}</span>
                    <span className="expand-icon">{expandedSections.organizational ? '▼' : '▶'}</span>
                  </button>
                  {expandedSections.organizational && (
                    <div className="sidebar-children">
                      <button className={`sidebar-btn child ${activeSection === 'account-mgmt' ? 'active' : ''}`} onClick={() => setActiveSection('account-mgmt')}><span>Account Management</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'company-info' ? 'active' : ''}`} onClick={() => setActiveSection('company-info')}><span>Company Info</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'team-members' ? 'active' : ''}`} onClick={() => navigate('/team-members')}><span>Team Members</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'add-team-member' ? 'active' : ''}`} onClick={() => navigate('/users/create')}><span>Add Team Member</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'bulk-upload' ? 'active' : ''}`} onClick={() => navigate('/users/bulk-upload')}><span>Bulk Upload Users</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'branding' ? 'active' : ''}`} onClick={() => setActiveSection('branding')}><span>Branding</span></button>
                    </div>
                  )}
                </div>
              );
            }

            // Render Agent Governance parent with children (admin-only)
            if (item.id === 'agent-governance') {
              if (hideAdminItem) return null;
              return (
                <div key={item.id}>
                  <button
                    className={`sidebar-btn parent ${expandedSections.agentGovernance ? 'expanded' : ''} ${dragOverItem?.id === item.id ? 'drag-over' : ''}`}
                    onClick={() => toggleSection('agentGovernance')}
                    draggable
                    onDragStart={(e) => handleDragStart(e, item)}
                    onDragEnd={handleDragEnd}
                    onDragOver={(e) => handleDragOver(e, item)}
                    onDragLeave={handleDragLeave}
                    onDrop={(e) => handleDrop(e, item)}
                  >
                    <span>{item.label}</span>
                    <span className="expand-icon">{expandedSections.agentGovernance ? '▼' : '▶'}</span>
                  </button>
                  {expandedSections.agentGovernance && (
                    <div className="sidebar-children">
                      <button className={`sidebar-btn child ${activeSection === 'agent-governance-system' ? 'active' : ''}`} onClick={() => setActiveSection('agent-governance-system')}><span>System Settings</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'agent-governance-thresholds' ? 'active' : ''}`} onClick={() => setActiveSection('agent-governance-thresholds')}><span>Performance Thresholds</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'agent-governance-costs' ? 'active' : ''}`} onClick={() => setActiveSection('agent-governance-costs')}><span>Cost Budgets</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'agent-governance-alerts' ? 'active' : ''}`} onClick={() => setActiveSection('agent-governance-alerts')}><span>Alerts & Notifications</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'agent-governance-compliance' ? 'active' : ''}`} onClick={() => setActiveSection('agent-governance-compliance')}><span>Compliance</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'agent-governance-gym' ? 'active' : ''}`} onClick={() => setActiveSection('agent-governance-gym')}><span>Agent Gym Settings</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'ai-email-training' ? 'active' : ''}`} onClick={() => setActiveSection('ai-email-training')}><span>AI Email Training</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'ai-email-setup' ? 'active' : ''}`} onClick={() => setActiveSection('ai-email-setup')}><span>AI Email Setup</span></button>
                    </div>
                  )}
                </div>
              );
            }

            // Render Production parent with children
            if (item.id === 'production') {
              return (
                <div key={item.id}>
                  <button
                    className={`sidebar-btn parent ${expandedSections.production ? 'expanded' : ''} ${dragOverItem?.id === item.id ? 'drag-over' : ''}`}
                    onClick={() => toggleSection('production')}
                    draggable
                    onDragStart={(e) => handleDragStart(e, item)}
                    onDragEnd={handleDragEnd}
                    onDragOver={(e) => handleDragOver(e, item)}
                    onDragLeave={handleDragLeave}
                    onDrop={(e) => handleDrop(e, item)}
                  >
                    <span>{item.label}</span>
                    <span className="expand-icon">{expandedSections.production ? '▼' : '▶'}</span>
                  </button>
                  {expandedSections.production && (
                    <div className="sidebar-children">
                      <button className={`sidebar-btn child`} onClick={() => navigate('/calendar-settings')}><span>Smart Calendar</span><i className="fas fa-external-link-alt" style={{ fontSize: '0.7em', marginLeft: 6, opacity: 0.5 }}></i></button>
                      <button className={`sidebar-btn child ${activeSection === 'video-meetings' ? 'active' : ''}`} onClick={() => setActiveSection('video-meetings')}><span>Video Meetings</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'dialer-settings' ? 'active' : ''}`} onClick={() => setActiveSection('dialer-settings')}><span>Power Dialer</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'voice-os' ? 'active' : ''}`} onClick={() => navigate('/voice-os-dashboard')}><span>Voice OS</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'ai-receptionist' ? 'active' : ''}`} onClick={() => setActiveSection('ai-receptionist')}><span>AI Receptionist</span></button>
                    </div>
                  )}
                </div>
              );
            }

            // Render Master Administrator parent with children (admin-only)
            if (item.id === 'master-admin') {
              if (hideAdminItem) return null;
              return (
                <div key={item.id}>
                  <button
                    className={`sidebar-btn parent ${expandedSections.masterAdmin ? 'expanded' : ''} ${dragOverItem?.id === item.id ? 'drag-over' : ''}`}
                    onClick={() => toggleSection('masterAdmin')}
                    draggable
                    onDragStart={(e) => handleDragStart(e, item)}
                    onDragEnd={handleDragEnd}
                    onDragOver={(e) => handleDragOver(e, item)}
                    onDragLeave={handleDragLeave}
                    onDrop={(e) => handleDrop(e, item)}
                  >
                    <span>{item.label}</span>
                    <span className="expand-icon">{expandedSections.masterAdmin ? '▼' : '▶'}</span>
                  </button>
                  {expandedSections.masterAdmin && (
                    <div className="sidebar-children">
                      <button className={`sidebar-btn child ${activeSection === 'account-mgmt' ? 'active' : ''}`} onClick={() => { setActiveSection('account-mgmt'); loadUsers(); }}><span>Account Management</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'integration-marketplace' ? 'active' : ''}`} onClick={() => setActiveSection('integration-marketplace')}><span>Integrations</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'clear-data' ? 'active' : ''}`} onClick={() => setActiveSection('clear-data')}><span>Clear Dummy Data</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'ai-feedback-log' ? 'active' : ''}`} onClick={() => setActiveSection('ai-feedback-log')}><span>AI Feedback Log</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'it-helpdesk-admin' ? 'active' : ''}`} onClick={() => setActiveSection('it-helpdesk-admin')}><span>IT Helpdesk Admin</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'api-keys' ? 'active' : ''}`} onClick={() => { setActiveSection('api-keys'); fetchApiKeys(); }}><span>API Keys</span></button>
                      <button className={`sidebar-btn child ${activeSection === 'business-ops' ? 'active' : ''}`} onClick={() => setActiveSection('business-ops')}><span>Business Operations</span></button>
                      <button className={`sidebar-btn child`} onClick={() => navigate('/settings/account-management')}><span>Account Management</span></button>
                    </div>
                  )}
                </div>
              );
            }

            // Skip adminOnly items if user is not admin/management
            if (hideAdminItem) {
              return null;
            }

            // Render other standalone items
            return (
              <button
                key={item.id}
                className={`sidebar-btn ${activeSection === item.section ? 'active' : ''} ${dragOverItem?.id === item.id ? 'drag-over' : ''}`}
                onClick={() => item.navigate ? navigate(item.navigate) : setActiveSection(item.section)}
                draggable
                onDragStart={(e) => handleDragStart(e, item)}
                onDragEnd={handleDragEnd}
                onDragOver={(e) => handleDragOver(e, item)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, item)}
              >
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>

        {/* Main Content */}
        <div className="settings-main">
          {activeSection === 'ai-receptionist' && (
            <AIReceptionist />
          )}

          {activeSection === 'email-monitor' && (
            <EmailMonitorDashboard />
          )}

          {activeSection === 'ai-email-training' && (
            <AIEmailTraining />
          )}

          {activeSection === 'ai-email-setup' && (
            <AIEmailSetup />
          )}

          {activeSection === 'email-signature' && (
            <EmailSignatureTab />
          )}

          {activeSection === 'document-intake' && (
            <DocumentIntakeManager />
          )}

          {activeSection === 'ai-feedback-log' && (
            <AIFeedbackLog />
          )}

          {activeSection === 'it-helpdesk-admin' && (
            <ITHelpdeskAdmin />
          )}

          {activeSection === 'business-ops' && (
            <BusinessOpsDashboard />
          )}

          {/* GMAIL */}
          {activeSection === 'gmail' && (
            <div className="integration-detail-section">
              <h2>Gmail Integration</h2>
              <p className="section-description">
                Sync Gmail emails and automatically extract lead information with AI
              </p>

              {gmailStatus.connected ? (
                <div className="connection-status-card connected gmail">
                  <div className="connection-status-header">
                    <div className="connection-status-indicator"></div>
                    <div className="connection-status-info">
                      <h3>Gmail Connected</h3>
                      <p className="connection-email">{gmailStatus.email}</p>
                    </div>
                    <div className="connection-actions">
                      <button className="btn-sync" onClick={async () => {
                        setLoadingGmail(true);
                        try {
                          const response = await fetch(`${API_BASE_URL}/api/v1/gmail/sync?days_back=7&max_results=100`, {
                            method: 'POST',
                            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                          });
                          const data = await response.json();
                          if (response.ok) {
                            toast.success(`Gmail sync complete! ${data.processed_count} emails processed.`);
                          } else {
                            toast.error(`Sync failed: ${data.detail || 'Unknown error'}`);
                          }
                        } catch (error) {
                          console.error('Gmail sync error:', error);
                          toast.error('Failed to sync Gmail');
                        } finally {
                          setLoadingGmail(false);
                        }
                      }} disabled={loadingGmail}>
                        {loadingGmail ? 'Syncing...' : 'Sync Now'}
                      </button>
                      <button className="btn-disconnect" onClick={disconnectGmail} disabled={loadingGmail}>
                        Disconnect
                      </button>
                    </div>
                  </div>
                  {gmailStatus.connected_at && (
                    <div className="connection-meta">Connected: {new Date(gmailStatus.connected_at).toLocaleString()}</div>
                  )}
                </div>
              ) : (
                <div className="connection-prompt-card">
                  <h3>Connect Gmail</h3>
                  <p>Connect your Gmail account to sync emails and extract lead information automatically</p>
                  <button className="btn-connect" onClick={connectGmail} disabled={loadingGmail}>
                    {loadingGmail ? 'Connecting...' : 'Connect Gmail'}
                  </button>
                </div>
              )}

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>Automatic email sync every 5 minutes</li>
                  <li>AI-powered lead extraction</li>
                  <li>Mortgage-related email detection</li>
                  <li>Auto-link to existing leads and loans</li>
                </ul>
              </div>
            </div>
          )}

          {/* OUTLOOK EMAIL */}
          {activeSection === 'outlook-email' && (
            <div className="integration-detail-section">
              <h2>Outlook Email Integration</h2>
              <p className="section-description">
                Sync your Microsoft 365 / Outlook emails and automatically link them to loan files
              </p>

              {/* Microsoft OAuth Configuration Section */}
              <div className="settings-card" style={{marginBottom: '24px'}}>
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px'}}>
                  <h3 style={{margin: 0}}>Microsoft Azure App Configuration</h3>
                  <button
                    className="btn-secondary"
                    onClick={() => setShowMicrosoftConfig(!showMicrosoftConfig)}
                  >
                    {showMicrosoftConfig ? 'Hide Configuration' : 'Configure Azure App'}
                  </button>
                </div>

                {microsoftOAuthConfig.client_id && !showMicrosoftConfig && (
                  <div style={{color: '#22c55e', fontSize: '14px'}}>
                    App configured (Client ID: {microsoftOAuthConfig.client_id.substring(0, 8)}...)
                  </div>
                )}

                {showMicrosoftConfig && (
                  <div className="oauth-config-form">
                    {microsoftConfigMessage.text && (
                      <div className={`message-banner ${microsoftConfigMessage.type}`} style={{marginBottom: '16px'}}>
                        {microsoftConfigMessage.text}
                      </div>
                    )}

                    <p style={{fontSize: '14px', color: '#666', marginBottom: '16px'}}>
                      Enter your Microsoft Azure App credentials. You can get these from the
                      <a href="https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade"
                         target="_blank" rel="noopener noreferrer" style={{marginLeft: '4px'}}>
                        Azure Portal App Registrations
                      </a>
                    </p>

                    <div className="form-group">
                      <label>Application (Client) ID *</label>
                      <input
                        type="text"
                        value={microsoftOAuthConfig.client_id}
                        onChange={(e) => setMicrosoftOAuthConfig({...microsoftOAuthConfig, client_id: e.target.value})}
                        placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                      />
                      <small>Found in Azure Portal &gt; App registrations &gt; Your App &gt; Overview</small>
                    </div>

                    <div className="form-group">
                      <label>Client Secret *</label>
                      <input
                        type="password"
                        value={microsoftOAuthConfig.client_secret}
                        onChange={(e) => setMicrosoftOAuthConfig({...microsoftOAuthConfig, client_secret: e.target.value})}
                        placeholder="Enter client secret (or leave blank to keep existing)"
                      />
                      <small>Found in Azure Portal &gt; App registrations &gt; Your App &gt; Certificates & secrets</small>
                    </div>

                    <div className="form-group">
                      <label>Tenant ID</label>
                      <input
                        type="text"
                        value={microsoftOAuthConfig.tenant_id}
                        onChange={(e) => setMicrosoftOAuthConfig({...microsoftOAuthConfig, tenant_id: e.target.value})}
                        placeholder="common (for multi-tenant apps)"
                      />
                      <small>Use "common" for multi-tenant apps, or your specific tenant ID</small>
                    </div>

                    <div style={{marginTop: '16px', padding: '12px', backgroundColor: '#f0f9ff', borderRadius: '8px', border: '1px solid #bae6fd'}}>
                      <h4 style={{margin: '0 0 8px 0', fontSize: '14px', color: '#0369a1'}}>Required Redirect URI</h4>
                      <p style={{margin: 0, fontSize: '13px', color: '#0c4a6e'}}>
                        Add this redirect URI to your Azure App:
                      </p>
                      <code style={{display: 'block', marginTop: '8px', padding: '8px', backgroundColor: '#fff', borderRadius: '4px', fontSize: '12px'}}>
                        {window.location.origin}/oauth/callback
                      </code>
                    </div>

                    <div style={{marginTop: '16px', display: 'flex', gap: '12px'}}>
                      <button
                        className="btn-primary"
                        onClick={saveMicrosoftOAuthConfig}
                        disabled={savingMicrosoftConfig || !microsoftOAuthConfig.client_id}
                      >
                        {savingMicrosoftConfig ? 'Saving...' : 'Save Configuration'}
                      </button>
                      <button
                        className="btn-secondary"
                        onClick={() => setShowMicrosoftConfig(false)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {microsoftStatus.connected ? (
                <div className="connection-status-card connected outlook">
                  <div className="connection-status-header">
                    <div className="connection-status-indicator"></div>
                    <div className="connection-status-info">
                      <h3>Outlook Connected</h3>
                      <p className="connection-email">{microsoftStatus.email}</p>
                    </div>
                    <div className="connection-actions">
                      <button className="btn-sync" onClick={syncMicrosoftNow} disabled={syncingMicrosoft}>
                        {syncingMicrosoft ? 'Syncing...' : 'Sync Now'}
                      </button>
                      <button className="btn-disconnect" onClick={disconnectMicrosoft} disabled={loadingMicrosoft}>
                        Disconnect
                      </button>
                    </div>
                  </div>
                  {microsoftStatus.last_sync_at && (
                    <div className="connection-meta">Last Sync: {new Date(microsoftStatus.last_sync_at).toLocaleString()}</div>
                  )}
                  {microsoftStatus.connected_at && (
                    <div className="connection-meta">Connected: {new Date(microsoftStatus.connected_at).toLocaleString()}</div>
                  )}
                </div>
              ) : (
                <div className="connection-prompt-card">
                  <h3>Connect Outlook</h3>
                  <p>Connect your Microsoft 365 / Outlook account to sync emails with loan files automatically</p>
                  {!microsoftOAuthConfig.client_id && (
                    <p style={{color: '#f59e0b', fontSize: '14px', marginBottom: '12px'}}>
                      Please configure your Azure App credentials above before connecting.
                    </p>
                  )}
                  <button
                    className="btn-connect"
                    onClick={connectMicrosoft365}
                    disabled={loadingMicrosoft || !microsoftOAuthConfig.client_id}
                  >
                    {loadingMicrosoft ? 'Connecting...' : 'Connect Microsoft 365'}
                  </button>
                </div>
              )}

              {/* Email Processing Settings */}
              <div className="email-processing-settings" style={{
                marginTop: '24px',
                padding: '20px',
                background: '#f9fafb',
                borderRadius: '12px',
                border: '1px solid #e5e7eb'
              }}>
                <h4 style={{margin: '0 0 16px 0', fontSize: '16px', fontWeight: '600', color: '#1f2937'}}>
                  Email Processing Settings
                </h4>

                <label style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '12px',
                  cursor: 'pointer',
                  padding: '12px',
                  background: 'white',
                  borderRadius: '8px',
                  border: '1px solid #e5e7eb'
                }}>
                  <input
                    type="checkbox"
                    checked={emailProcessingSettings.delete_from_inbox_after_processing}
                    onChange={(e) => {
                      const newSettings = {
                        ...emailProcessingSettings,
                        delete_from_inbox_after_processing: e.target.checked
                      };
                      saveEmailProcessingSettings(newSettings);
                    }}
                    disabled={savingEmailSettings}
                    style={{
                      width: '20px',
                      height: '20px',
                      marginTop: '2px',
                      accentColor: '#218D8D'
                    }}
                  />
                  <div>
                    <span style={{fontWeight: '500', color: '#1f2937', display: 'block'}}>
                      Delete emails from inbox after processing
                    </span>
                    <span style={{fontSize: '13px', color: '#6b7280', marginTop: '4px', display: 'block'}}>
                      When you approve or reject emails in the Reconciliation Center, they will also be moved to trash in your inbox.
                      You can override this per-email when processing.
                    </span>
                  </div>
                </label>

                {emailProcessingSettings.delete_from_inbox_after_processing && (
                  <div style={{
                    marginTop: '12px',
                    padding: '12px',
                    background: '#fef3c7',
                    borderRadius: '8px',
                    fontSize: '13px',
                    color: '#92400e',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '8px'
                  }}>
                    <span>⚠️</span>
                    <span>
                      Emails will be moved to your Trash folder (not permanently deleted).
                      You can recover them from Trash within 30 days.
                    </span>
                  </div>
                )}
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>Automatic email sync with loan files</li>
                  <li>AI-powered lead extraction</li>
                  <li>Auto-link emails to existing loans</li>
                  <li>Two-way email sync</li>
                </ul>
              </div>
            </div>
          )}

          {/* OUTLOOK CALENDAR */}
          {activeSection === 'outlook-calendar' && (
            <div className="integration-detail-section">
              <h2>Outlook Calendar Integration</h2>
              <p className="section-description">
                Sync your Microsoft 365 / Outlook calendar events
              </p>

              {microsoftStatus.connected ? (
                <div className="connection-status-card connected outlook">
                  <div className="connection-status-header">
                    <div className="connection-status-indicator"></div>
                    <div className="connection-status-info">
                      <h3>Calendar Connected</h3>
                      <p className="connection-email">{microsoftStatus.email}</p>
                    </div>
                    <div className="connection-actions">
                      <button className="btn-sync" onClick={syncMicrosoftCalendar} disabled={syncingCalendar}>
                        {syncingCalendar ? 'Syncing...' : 'Sync Calendar'}
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="connection-prompt-card">
                  <h3>Connect Outlook Calendar</h3>
                  <p>Connect your Microsoft 365 / Outlook account to sync calendar events</p>
                  <button className="btn-connect" onClick={connectMicrosoft365} disabled={loadingMicrosoft}>
                    {loadingMicrosoft ? 'Connecting...' : 'Connect Microsoft 365'}
                  </button>
                </div>
              )}

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>Sync calendar events with CRM</li>
                  <li>Schedule appointments with borrowers</li>
                  <li>Automatic reminders</li>
                </ul>
              </div>
            </div>
          )}

          {/* MICROSOFT TEAMS */}
          {activeSection === 'teams' && (
            <div className="integration-detail-section">
              <h2>Microsoft Teams Integration</h2>
              <p className="section-description">Send messages, make calls, and collaborate with your team</p>
              <div className="integration-coming-soon">
                <h3>Coming Soon</h3>
                <p>Microsoft Teams integration is currently in development</p>
              </div>
            </div>
          )}

          {/* CALENDLY */}
          {activeSection === 'calendly' && (
            <div className="calendar-settings-section">
              <h2>Calendly Integration</h2>
              <p className="section-description">
                Connect Calendly and configure AI scheduling for automatic appointment booking
              </p>

              {/* Calendly Connection Status */}
              <div className="calendly-connection-card">
                <div className="connection-header">
                  <div className="connection-icon" style={{background: '#006bff'}}>
                    🗓️
                  </div>
                  <div className="connection-info">
                    <h3>Calendly Connection</h3>
                    {calendlyStatus.isConnected ? (
                      <p>Connected as <strong>{calendlyStatus.userName}</strong> ({calendlyStatus.userEmail})</p>
                    ) : (
                      <p>Connect your Calendly account to sync calendars and manage appointments</p>
                    )}
                  </div>
                  <div className="connection-status">
                    {calendlyStatus.isConnected ? (
                      <span className="status-badge connected">Connected</span>
                    ) : (
                      <span className="status-badge disconnected">Not Connected</span>
                    )}
                  </div>
                </div>

                <div className="connection-actions">
                  {calendlyStatus.isConnected ? (
                    <>
                      <button
                        className="btn-refresh"
                        onClick={fetchCalendlyStatus}
                        disabled={loadingCalendly}
                      >
                        {loadingCalendly ? 'Refreshing...' : 'Refresh'}
                      </button>
                      <button
                        className="btn-disconnect"
                        onClick={disconnectCalendly}
                        disabled={loadingCalendly}
                        style={{ marginLeft: '8px', background: '#dc3545', color: '#fff' }}
                      >
                        Disconnect
                      </button>
                      <span className="connection-detail" style={{ marginLeft: '12px' }}>
                        {calendlyEventTypes.length} event types available
                      </span>
                    </>
                  ) : (
                    <button
                      className="btn-connect-calendly"
                      onClick={connectCalendly}
                      disabled={loadingCalendly}
                    >
                      {loadingCalendly ? 'Connecting...' : 'Connect with Calendly'}
                    </button>
                  )}
                </div>
              </div>

              {/* Calendly Settings - Only show when connected */}
              {calendlyStatus.isConnected && (
                <div className="calendly-settings-card" style={{ background: '#f8f9fa', padding: '20px', borderRadius: '8px', marginBottom: '24px' }}>
                  <h3 style={{ marginTop: 0, marginBottom: '16px' }}>Integration Settings</h3>

                  <div className="form-group" style={{ marginBottom: '16px' }}>
                    <label>Default Event Type for AI Scheduling</label>
                    <select
                      value={calendlySettings.selectedEventTypeUri || ''}
                      onChange={(e) => {
                        setCalendlySettings(prev => ({ ...prev, selectedEventTypeUri: e.target.value }));
                        updateCalendlySettings({ selected_event_type_uri: e.target.value });
                      }}
                      className="form-select"
                      disabled={loadingCalendly || calendlyEventTypes.length === 0}
                      style={{ width: '100%', padding: '10px', marginTop: '8px' }}
                    >
                      <option value="">Select default event type...</option>
                      {calendlyEventTypes.map(eventType => {
                        const uuid = eventType.uri.split('/').pop();
                        return (
                          <option key={uuid} value={eventType.uri}>
                            {eventType.name} ({eventType.duration} min)
                          </option>
                        );
                      })}
                    </select>
                    <p style={{ fontSize: '12px', color: '#666', marginTop: '4px' }}>
                      This event type will be used when the AI schedules appointments
                    </p>
                  </div>

                  <div className="form-group" style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={calendlyStatus.syncToSmartScheduler}
                        onChange={(e) => {
                          updateCalendlySettings({ sync_to_smart_scheduler: e.target.checked });
                        }}
                        style={{ marginRight: '8px' }}
                      />
                      Sync Calendly bookings to Smart Scheduler
                    </label>
                    <p style={{ fontSize: '12px', color: '#666', marginTop: '4px', marginLeft: '24px' }}>
                      Automatically create appointments in Smart Scheduler when bookings are made through Calendly
                    </p>
                  </div>

                  <div className="form-group">
                    <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={calendlyStatus.autoCreateContacts}
                        onChange={(e) => {
                          updateCalendlySettings({ auto_create_contacts: e.target.checked });
                        }}
                        style={{ marginRight: '8px' }}
                      />
                      Auto-create contacts from Calendly bookings
                    </label>
                    <p style={{ fontSize: '12px', color: '#666', marginTop: '4px', marginLeft: '24px' }}>
                      Create new contact records when someone books through Calendly
                    </p>
                  </div>
                </div>
              )}

              {/* How AI Scheduling Works */}
              <div className="info-card">
                                <div className="info-content">
                  <h3>How AI Scheduling Works</h3>
                  <p>When AI schedules appointments with leads, it automatically selects the right calendar based on the lead's current stage. For example:</p>
                  <ul>
                    <li><strong>New Lead</strong> → Discovery Call (30 min)</li>
                    <li><strong>Qualified</strong> → Consultation (60 min)</li>
                    <li><strong>Application Started</strong> → Application Review (45 min)</li>
                  </ul>
                  <p>Configure your mappings below to tell the AI which calendar to use for each stage.</p>
                </div>
              </div>

              {/* Create New Mapping */}
              <div className="mapping-form-card">
                <h3>Create Calendar Mapping</h3>
                <div className="mapping-form">
                  <div className="form-row">
                    <div className="form-group">
                      <label>Lead Stage</label>
                      <select
                        value={selectedStage}
                        onChange={(e) => setSelectedStage(e.target.value)}
                        className="form-select"
                      >
                        <option value="">Select a stage...</option>
                        {leadStages.map(stage => (
                          <option key={stage.value} value={stage.value}>
                            {stage.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label>Calendly Event Type</label>
                      {loadingCalendly ? (
                        <div className="loading-spinner">Loading calendars...</div>
                      ) : (
                        <select
                          value={selectedEventType}
                          onChange={(e) => setSelectedEventType(e.target.value)}
                          className="form-select"
                          disabled={calendlyEventTypes.length === 0}
                        >
                          <option value="">Select a calendar...</option>
                          {calendlyEventTypes.map(eventType => {
                            const uuid = eventType.uri.split('/').pop();
                            return (
                              <option key={uuid} value={uuid}>
                                {eventType.name} ({eventType.duration} min)
                              </option>
                            );
                          })}
                        </select>
                      )}
                    </div>

                    <div className="form-actions">
                      <button
                        onClick={createCalendarMapping}
                        disabled={!selectedStage || !selectedEventType}
                        className="btn-save-mapping"
                      >
                        Save Mapping
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Current Mappings */}
              <div className="current-mappings-card">
                <h3>Current Mappings</h3>
                {calendarMappings.length === 0 ? (
                  <div className="empty-state">
                                        <p>No calendar mappings configured yet.</p>
                    <p className="empty-hint">Create your first mapping above to get started.</p>
                  </div>
                ) : (
                  <div className="mappings-table">
                    <table>
                      <thead>
                        <tr>
                          <th>Lead Stage</th>
                          <th>Calendar Type</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {calendarMappings.map(mapping => {
                          const stageLabel = leadStages.find(s => s.value === mapping.stage)?.label || mapping.stage;
                          return (
                            <tr key={mapping.id}>
                              <td>
                                <div className="stage-cell">
                                  <span className="stage-badge">{stageLabel}</span>
                                </div>
                              </td>
                              <td>
                                <div className="calendar-cell">
                                  <strong>{mapping.event_type_name}</strong>
                                  <br />
                                  <span className="calendar-uuid">{mapping.event_type_uuid}</span>
                                </div>
                              </td>
                              <td>
                                <span className="status-badge active">Active</span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Help Section */}
              <div className="help-card">
                <h4>Need Help?</h4>
                <p>To get your Calendly event types:</p>
                <ol>
                  <li>Go to <a href="https://calendly.com/event_types/user/me" target="_blank" rel="noopener noreferrer">calendly.com/event_types</a></li>
                  <li>Create different event types for each stage (e.g., "Discovery Call", "Consultation")</li>
                  <li>Come back here and map each stage to the appropriate event type</li>
                  <li>The AI will automatically use the right calendar when scheduling!</li>
                </ol>
              </div>
            </div>
          )}

          {/* ZOOM */}
          {activeSection === 'zoom' && (
            <div className="integration-detail-section">
              <h2>Zoom Integration</h2>
              <p className="section-description">Host virtual meetings and consultations with clients</p>

              <div className="integration-connect-card">
                                <h3>Connect Zoom</h3>
                <p>Connect your Zoom account to schedule and host virtual meetings with clients</p>
                <div className="connect-form">
                  <div className="form-group">
                    <label>Zoom API Key</label>
                    <input type="text" className="form-input" placeholder="Enter your Zoom API Key" />
                  </div>
                  <div className="form-group">
                    <label>Zoom API Secret</label>
                    <input type="password" className="form-input" placeholder="Enter your Zoom API Secret" />
                  </div>
                  <button className="btn-connect">Connect Zoom</button>
                </div>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>Schedule Zoom meetings from CRM</li>
                  <li>Auto-generate meeting links for appointments</li>
                  <li>Send meeting invites to clients</li>
                  <li>Track meeting attendance and duration</li>
                </ul>
              </div>

              <div className="info-card" style={{marginTop: '24px'}}>
                                <div className="info-content">
                  <h3>How to get Zoom API credentials</h3>
                  <ol>
                    <li>Go to <a href="https://marketplace.zoom.us" target="_blank" rel="noopener noreferrer">Zoom App Marketplace</a></li>
                    <li>Create a Server-to-Server OAuth app</li>
                    <li>Copy your API Key and Secret</li>
                    <li>Paste them in the form above</li>
                  </ol>
                </div>
              </div>
            </div>
          )}

          {/* SALESFORCE */}
          {activeSection === 'salesforce' && (
            <div className="integration-detail-section">
              <h2>Salesforce Integration</h2>
              <p className="section-description">Sync contacts and deals with your Salesforce CRM</p>

              <div className="integration-connect-card">
                                <h3>Connect Salesforce</h3>
                <p>Connect your Salesforce account to sync contacts, leads, and opportunities</p>
                <div className="connect-form">
                  <div className="form-group">
                    <label>Salesforce Instance URL</label>
                    <input type="text" className="form-input" placeholder="https://yourcompany.salesforce.com" />
                  </div>
                  <div className="form-group">
                    <label>Consumer Key</label>
                    <input type="text" className="form-input" placeholder="Enter your Consumer Key" />
                  </div>
                  <div className="form-group">
                    <label>Consumer Secret</label>
                    <input type="password" className="form-input" placeholder="Enter your Consumer Secret" />
                  </div>
                  <button className="btn-connect">Connect Salesforce</button>
                </div>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>Two-way sync of contacts and leads</li>
                  <li>Sync opportunities and pipeline data</li>
                  <li>Map custom fields between systems</li>
                  <li>Real-time updates via webhooks</li>
                </ul>
              </div>
            </div>
          )}

          {/* HUBSPOT */}
          {activeSection === 'hubspot' && (
            <div className="integration-detail-section">
              <h2>HubSpot Integration</h2>
              <p className="section-description">Marketing automation and lead nurturing</p>

              <div className="integration-connect-card">
                                <h3>Connect HubSpot</h3>
                <p>Connect your HubSpot account to sync contacts and automate marketing</p>
                <div className="connect-form">
                  <div className="form-group">
                    <label>HubSpot API Key</label>
                    <input type="text" className="form-input" placeholder="Enter your HubSpot API Key" />
                  </div>
                  <div className="form-group">
                    <label>Portal ID</label>
                    <input type="text" className="form-input" placeholder="Enter your Portal ID" />
                  </div>
                  <button className="btn-connect">Connect HubSpot</button>
                </div>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>Sync email marketing campaigns</li>
                  <li>Lead scoring and nurturing</li>
                  <li>Marketing analytics integration</li>
                  <li>Contact and deal sync</li>
                </ul>
              </div>
            </div>
          )}

          {/* MAILCHIMP */}
          {activeSection === 'mailchimp' && (
            <div className="integration-detail-section">
              <h2>Mailchimp Integration</h2>
              <p className="section-description">Email marketing campaigns for your clients</p>

              <div className="integration-connect-card">
                                <h3>Connect Mailchimp</h3>
                <p>Connect your Mailchimp account to manage email campaigns</p>
                <div className="connect-form">
                  <div className="form-group">
                    <label>Mailchimp API Key</label>
                    <input type="text" className="form-input" placeholder="Enter your Mailchimp API Key" />
                  </div>
                  <div className="form-group">
                    <label>Server Prefix</label>
                    <input type="text" className="form-input" placeholder="e.g., us1, us2, etc." />
                  </div>
                  <button className="btn-connect">Connect Mailchimp</button>
                </div>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>Sync contacts to Mailchimp lists</li>
                  <li>Track email campaign performance</li>
                  <li>Segment audiences by lead stage</li>
                  <li>Automated email workflows</li>
                </ul>
              </div>
            </div>
          )}

          {/* RINGCENTRAL */}
          {activeSection === 'ringcentral' && (
            <div className="integration-detail-section">
              <h2>RingCentral Integration</h2>
              <p className="section-description">Click-to-call and SMS via RingCentral phone system</p>

              <div className="integration-connect-card">
                                <h3>Connect RingCentral</h3>
                <p>Connect your RingCentral account for click-to-call and SMS</p>
                <div className="connect-form">
                  <div className="form-group">
                    <label>RingCentral Client ID</label>
                    <input type="text" className="form-input" placeholder="Enter your Client ID" />
                  </div>
                  <div className="form-group">
                    <label>RingCentral Client Secret</label>
                    <input type="password" className="form-input" placeholder="Enter your Client Secret" />
                  </div>
                  <div className="form-group">
                    <label>Server URL</label>
                    <select className="form-select">
                      <option value="https://platform.ringcentral.com">Production</option>
                      <option value="https://platform.devtest.ringcentral.com">Sandbox</option>
                    </select>
                  </div>
                  <button className="btn-connect">Connect RingCentral</button>
                </div>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>Click-to-call from CRM</li>
                  <li>Send SMS via RingCentral</li>
                  <li>Call logging and analytics</li>
                  <li>Incoming call notifications</li>
                </ul>
              </div>
            </div>
          )}

          {/* SLACK */}
          {activeSection === 'slack' && (
            <div className="integration-detail-section">
              <h2>Slack Integration</h2>
              <p className="section-description">Get notifications and updates in your Slack workspace</p>

              <div className="integration-connect-card">
                                <h3>Connect Slack</h3>
                <p>Connect your Slack workspace to receive notifications</p>
                <div className="connect-form">
                  <div className="form-group">
                    <label>Slack Webhook URL</label>
                    <input type="text" className="form-input" placeholder="https://hooks.slack.com/services/..." />
                  </div>
                  <div className="form-group">
                    <label>Default Channel</label>
                    <input type="text" className="form-input" placeholder="#mortgage-leads" />
                  </div>
                  <button className="btn-connect">Connect Slack</button>
                </div>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Notification Types</h4>
                <ul>
                  <li>New lead notifications</li>
                  <li>Pipeline stage changes</li>
                  <li>Document uploads</li>
                  <li>✅ Task completions</li>
                  <li>💰 Loan closings</li>
                </ul>
              </div>
            </div>
          )}

          {/* ZAPIER */}
          {activeSection === 'zapier' && (
            <div className="integration-detail-section">
              <h2>Zapier Integration</h2>
              <p className="section-description">Connect with 5,000+ apps through automated workflows</p>

              <div className="integration-connect-card">
                                <h3>Connect Zapier</h3>
                <p>Use your API key to connect this CRM with Zapier</p>
                <div className="info-box">
                  <p>Go to <strong>Settings → API Keys</strong> to generate an API key for Zapier integration.</p>
                  <button className="btn-secondary" onClick={() => setActiveSection('api-keys')}>
                    Go to API Keys
                  </button>
                </div>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Popular Zaps</h4>
                <ul>
                  <li>Create lead from new email</li>
                  <li>Add lead to Google Sheets</li>
                  <li>Send SMS when lead stage changes</li>
                  <li>Create calendar event for appointments</li>
                  <li>Notify team on Slack for new leads</li>
                </ul>
              </div>

              <div className="info-card" style={{marginTop: '24px'}}>
                                <div className="info-content">
                  <h3>How to use with Zapier</h3>
                  <ol>
                    <li>Generate an API key in Settings → API Keys</li>
                    <li>Go to <a href="https://zapier.com" target="_blank" rel="noopener noreferrer">Zapier</a> and create a new Zap</li>
                    <li>Use "Webhooks by Zapier" as the trigger or action</li>
                    <li>Use your API key in the Authorization header</li>
                  </ol>
                </div>
              </div>
            </div>
          )}

          {/* SYNTHFLOW AI */}
          {activeSection === 'synthflow' && (
            <div className="integration-detail-section">
              <h2>Synthflow AI Integration</h2>
              <p className="section-description">AI-powered voice agents for automated client calls and lead qualification</p>

              <div className="integration-connect-card">
                                <h3>Connect Synthflow AI</h3>
                <p>Connect your Synthflow account to enable AI voice agents</p>
                <div className="connect-form">
                  <div className="form-group">
                    <label>Synthflow API Key</label>
                    <input type="text" className="form-input" placeholder="Enter your Synthflow API Key" />
                  </div>
                  <div className="form-group">
                    <label>Workspace ID</label>
                    <input type="text" className="form-input" placeholder="Enter your Workspace ID" />
                  </div>
                  <button className="btn-connect">Connect Synthflow</button>
                </div>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>AI voice agents for outbound calls</li>
                  <li>Automated lead qualification</li>
                  <li>Call transcription and analysis</li>
                  <li>CRM sync for call outcomes</li>
                  <li>Schedule appointments via AI</li>
                </ul>
              </div>
            </div>
          )}

          {/* RECALL.AI */}
          {activeSection === 'recallai' && (
            <div className="integration-detail-section">
              <h2>Recall.ai Integration</h2>
              <p className="section-description">Record and transcribe meetings from Zoom, Teams, and Google Meet with AI</p>

              <div className="integration-connect-card">
                                <h3>Connect Recall.ai</h3>
                <p>Connect your Recall.ai account to record and transcribe meetings</p>
                <div className="connect-form">
                  <div className="form-group">
                    <label>Recall.ai API Key</label>
                    <input type="text" className="form-input" placeholder="Enter your Recall.ai API Key" />
                  </div>
                  <button className="btn-connect">Connect Recall.ai</button>
                </div>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>🎙️ Auto-record Zoom, Teams, Meet calls</li>
                  <li>AI transcription</li>
                  <li>Meeting summaries and action items</li>
                  <li>🔍 Searchable meeting archives</li>
                  <li>Sync notes to CRM</li>
                </ul>
              </div>
            </div>
          )}

          {/* STRIPE */}
          {activeSection === 'stripe' && (
            <div className="integration-detail-section">
              <h2>💳 Stripe Integration</h2>
              <p className="section-description">Collect payments and processing fees</p>

              <div className="integration-connect-card">
                <div className="connect-icon" style={{background: '#635bff'}}>💳</div>
                <h3>Connect Stripe</h3>
                <p>Connect your Stripe account to collect payments</p>
                <div className="connect-form">
                  <div className="form-group">
                    <label>Stripe Publishable Key</label>
                    <input type="text" className="form-input" placeholder="pk_live_..." />
                  </div>
                  <div className="form-group">
                    <label>Stripe Secret Key</label>
                    <input type="password" className="form-input" placeholder="sk_live_..." />
                  </div>
                  <button className="btn-connect">Connect Stripe</button>
                </div>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>💳 Collect application fees</li>
                  <li>Track payment history</li>
                  <li>Automated payment receipts</li>
                  <li>Sync with accounting</li>
                </ul>
              </div>
            </div>
          )}

          {/* QUICKBOOKS */}
          {activeSection === 'quickbooks' && (
            <div className="integration-detail-section">
              <h2>💰 QuickBooks Integration</h2>
              <p className="section-description">Sync financial data and commission tracking</p>

              <div className="integration-connect-card">
                <div className="connect-icon" style={{background: '#2ca01c'}}>💰</div>
                <h3>Connect QuickBooks</h3>
                <p>Connect your QuickBooks account to sync financial data</p>
                <div className="connect-form">
                  <div className="form-group">
                    <label>QuickBooks Client ID</label>
                    <input type="text" className="form-input" placeholder="Enter your Client ID" />
                  </div>
                  <div className="form-group">
                    <label>QuickBooks Client Secret</label>
                    <input type="password" className="form-input" placeholder="Enter your Client Secret" />
                  </div>
                  <button className="btn-connect">Connect QuickBooks</button>
                </div>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>💰 Track commissions and income</li>
                  <li>Sync invoices and payments</li>
                  <li>Expense tracking</li>
                  <li>📈 Financial reporting</li>
                </ul>
              </div>
            </div>
          )}

          {/* GOOGLE CALENDAR */}
          {activeSection === 'google-calendar' && (
            <div className="integration-detail-section">
              <h2>📆 Google Calendar Integration</h2>
              <p className="section-description">Sync appointments with Google Calendar</p>

              <div className="integration-connect-card">
                <div className="connect-icon" style={{background: '#4285f4'}}>📆</div>
                <h3>Connect Google Calendar</h3>
                <p>Connect your Google account to sync calendar events</p>
                <button className="btn-connect">Connect with Google</button>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>📆 Two-way calendar sync</li>
                  <li>Appointment reminders</li>
                  <li>Schedule availability</li>
                  <li>Auto-add meeting links</li>
                </ul>
              </div>
            </div>
          )}

          {/* GOOGLE DRIVE */}
          {activeSection === 'google-drive' && (
            <div className="integration-detail-section">
              <h2>📂 Google Drive Integration</h2>
              <p className="section-description">Store and share loan documents in Google Drive</p>

              <div className="integration-connect-card">
                <div className="connect-icon" style={{background: '#4285f4'}}>📂</div>
                <h3>Connect Google Drive</h3>
                <p>Connect your Google account to store documents</p>
                <button className="btn-connect">Connect with Google</button>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>📂 Auto-upload loan documents</li>
                  <li>📁 Organized folder structure per loan</li>
                  <li>Share documents with clients</li>
                  <li>Version history tracking</li>
                </ul>
              </div>
            </div>
          )}

          {/* DOCUSIGN */}
          {activeSection === 'docusign' && (
            <div className="integration-detail-section">
              <h2>DocuSign Integration</h2>
              <p className="section-description">Send and sign loan documents electronically</p>

              <div className="integration-connect-card">
                                <h3>Connect DocuSign</h3>
                <p>Connect your DocuSign account for electronic signatures</p>
                <div className="connect-form">
                  <div className="form-group">
                    <label>DocuSign Integration Key</label>
                    <input type="text" className="form-input" placeholder="Enter your Integration Key" />
                  </div>
                  <div className="form-group">
                    <label>DocuSign Secret Key</label>
                    <input type="password" className="form-input" placeholder="Enter your Secret Key" />
                  </div>
                  <div className="form-group">
                    <label>Account ID</label>
                    <input type="text" className="form-input" placeholder="Enter your Account ID" />
                  </div>
                  <button className="btn-connect">Connect DocuSign</button>
                </div>
              </div>

              <div className="integration-features" style={{marginTop: '24px'}}>
                <h4>Features</h4>
                <ul>
                  <li>Send documents for signature</li>
                  <li>✅ Track signing status</li>
                  <li>Automated reminders</li>
                  <li>📁 Auto-save signed documents</li>
                </ul>
              </div>
            </div>
          )}

          {activeSection === 'integration-marketplace' && (
            <div className="integrations-marketplace">
              <div className="marketplace-header">
                <div className="header-text">
                  <h2>Integrations & Apps</h2>
                  <p className="section-description">
                    Discover ({availableIntegrations.length}) | Manage ({connectedIntegrations.size})
                  </p>
                </div>
                <div className="search-box">
                  <input
                    type="text"
                    placeholder="Find integrations, apps, and more"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="integration-search"
                  />
                </div>
              </div>

              {/* All Integrations Grid */}
              <div className="all-integrations-section">
                <div className="integrations-grid">
                  {filteredIntegrations.map(integration => (
                    <div
                      key={integration.id}
                      className="integration-grid-card"
                      onClick={() => toggleIntegration(integration.id)}
                    >
                      <div className="card-icon" style={{background: integration.color}}>
                        {integration.icon}
                      </div>
                      <div className="card-content">
                        <div className="card-header">
                          <h4>{integration.name}</h4>
                          {connectedIntegrations.has(integration.id) && (
                            <span className="connected-badge">Connected</span>
                          )}
                        </div>
                        <p className="card-description">{integration.description}</p>
                      </div>
                    </div>
                  ))}
                </div>

                {filteredIntegrations.length === 0 && (
                  <div className="no-results">
                    <p>No integrations found matching "{searchTerm}"</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeSection === 'phone-integration' && (
            <div className="phone-integration-section">
              <h2>Phone Integration</h2>
              <p className="section-description">
                Manage phone, SMS, and calling features for your CRM
              </p>

              {/* Integration Status Card */}
              <div className="phone-status-card">
                <div className="card-header">
                  <h3>Integration Status</h3>
                </div>

                <div className="status-grid">
                  {/* Native Phone Features */}
                  <div className="status-item">
                                        <div className="status-info">
                      <h4>Click-to-Call</h4>
                      <p>Native phone integration</p>
                      <span className="status-badge connected">Active</span>
                    </div>
                  </div>

                  <div className="status-item">
                                        <div className="status-info">
                      <h4>SMS/Text</h4>
                      <p>Native messaging integration</p>
                      <span className="status-badge connected">Active</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Test Features Card */}
              <div className="phone-test-card">
                <h3>Test Phone Features</h3>
                <p className="section-description">
                  Test your phone integration to make sure everything is working
                </p>

                <div className="test-form">
                  <div className="form-group">
                    <label>Test Phone Number</label>
                    <input
                      type="tel"
                      className="form-input"
                      placeholder="Enter phone number (e.g., 555-123-4567)"
                      value={testPhoneNumber}
                      onChange={(e) => setTestPhoneNumber(formatPhoneNumber(e.target.value))}
                    />
                  </div>

                  <div className="test-actions">
                    <button
                      className="btn-test call"
                      onClick={testClickToCall}
                      disabled={!testPhoneNumber}
                    >
                      Test Click-to-Call
                    </button>
                    <button
                      className="btn-test sms"
                      onClick={testSMS}
                      disabled={!testPhoneNumber}
                    >
                      Test SMS
                    </button>
                  </div>
                </div>

                {/* Test Results */}
                {testResults.length > 0 && (
                  <div className="test-results">
                    <h4>Recent Tests</h4>
                    <div className="results-list">
                      {testResults.map((result, index) => (
                        <div key={index} className={`result-item ${result.status}`}>
                          <span className="result-icon">
                            {result.status === 'success' ? '✅' : '❌'}
                          </span>
                          <div className="result-content">
                            <div className="result-feature">{result.feature}</div>
                            <div className="result-message">{result.message}</div>
                          </div>
                          <div className="result-time">{result.timestamp}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* How It Works Card */}
              <div className="info-card">
                                <div className="info-content">
                  <h3>How Phone Integration Works</h3>
                  <p><strong>Native Features (Always Active):</strong></p>
                  <ul>
                    <li><strong>Click-to-Call:</strong> Click any phone number in the CRM to open your phone dialer</li>
                    <li><strong>SMS/Text:</strong> Click the button to open your messaging app</li>
                    <li>Works with any carrier (Verizon, AT&T, T-Mobile, etc.)</li>
                    <li>No configuration required - works immediately!</li>
                  </ul>
                </div>
              </div>

              {/* Quick Links Card */}
              <div className="quick-links-card">
                <h3>Quick Links</h3>
                <div className="links-grid">
                  <a
                    href="/verizon-test"
                    className="link-item"
                    onClick={(e) => {
                      e.preventDefault();
                      navigate('/verizon-test');
                    }}
                  >
                    <div className="link-icon">🧪</div>
                    <div className="link-info">
                      <h4>Full Test Page</h4>
                      <p>Comprehensive testing interface</p>
                    </div>
                  </a>
                  <a
                    href="https://docs.claude.com"
                    className="link-item"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <div className="link-icon">📚</div>
                    <div className="link-info">
                      <h4>Setup Guide</h4>
                      <p>Step-by-step instructions</p>
                    </div>
                  </a>
                </div>
              </div>

            </div>
          )}

          {activeSection === 'api-keys' && (
            <div className="api-keys-section">
              <h2>API Keys</h2>
              <p className="section-description">
                Generate and manage API keys for integrations like Zapier
              </p>

              {/* Create New API Key */}
              <div className="api-key-create-card">
                <h3>Create New API Key</h3>
                <div className="form-group">
                  <input
                    type="text"
                    placeholder="Enter API key name (e.g., 'Zapier Integration')"
                    value={newApiKeyName}
                    onChange={(e) => setNewApiKeyName(e.target.value)}
                    className="input-field"
                  />
                  <button
                    onClick={createApiKey}
                    className="btn-create-key"
                    disabled={!newApiKeyName.trim()}
                  >
                    Generate API Key
                  </button>
                </div>

                {createdKey && (
                  <div className="key-created-alert">
                    <h4>🎉 API Key Created Successfully!</h4>
                    <p>Copy this key now - you won't be able to see it again:</p>
                    <div className="key-display">
                      <code>{createdKey}</code>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(createdKey);
                          toast.success('API key copied to clipboard!');
                        }}
                        className="btn-copy"
                      >
                        Copy
                      </button>
                    </div>
                    <button
                      onClick={() => setCreatedKey(null)}
                      className="btn-dismiss"
                    >
                      I've saved it
                    </button>
                  </div>
                )}
              </div>

              {/* Existing API Keys */}
              <div className="api-keys-list-card">
                <h3>Your API Keys</h3>
                {loadingApiKeys ? (
                  <p>Loading API keys...</p>
                ) : apiKeys.length === 0 ? (
                  <div className="empty-state">
                                        <p>No API keys yet.</p>
                    <p className="empty-hint">Create your first API key above to get started with integrations.</p>
                  </div>
                ) : (
                  <div className="api-keys-table">
                    <table>
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>Key</th>
                          <th>Created</th>
                          <th>Last Used</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {apiKeys.map((key) => (
                          <tr key={key.id}>
                            <td><strong>{key.name}</strong></td>
                            <td><code>sk_••••••••••••••••</code></td>
                            <td>{new Date(key.created_at).toLocaleDateString()}</td>
                            <td>{key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}</td>
                            <td>
                              <span className={`status-badge ${key.is_active ? 'active' : 'inactive'}`}>
                                {key.is_active ? 'Active' : 'Revoked'}
                              </span>
                            </td>
                            <td>
                              {key.is_active && (
                                <button
                                  onClick={() => revokeApiKey(key.id, key.name)}
                                  className="btn-revoke"
                                >
                                  Revoke
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Help Section */}
              <div className="help-card">
                <h4>How to use API Keys</h4>
                <ol>
                  <li>Generate an API key by entering a name and clicking "Generate API Key"</li>
                  <li>Copy the API key immediately - it will only be shown once</li>
                  <li>Use the API key in your integrations (e.g., Zapier) by adding it to the Authorization header:
                    <br/><code>Authorization: Bearer sk_your_api_key_here</code>
                  </li>
                  <li>The API key will work exactly like your login token for all API requests</li>
                  <li>Revoke an API key anytime if you suspect it's been compromised</li>
                </ol>
              </div>
            </div>
          )}

          {activeSection === 'it-helpdesk' && (
            <div className="it-helpdesk-section">
              <h2>AI IT Helpdesk</h2>
              <p className="section-description">
                Get AI-powered help for technical issues. Describe your problem and the AI will diagnose it and propose a fix.
              </p>

              {/* Submit New Ticket */}
              <div className="helpdesk-submit-card">
                <h3>Submit IT Issue</h3>

                <div className="form-group">
                  <label>Title (optional)</label>
                  <input
                    type="text"
                    placeholder="Brief summary of the issue"
                    value={newTicket.title}
                    onChange={(e) => setNewTicket({...newTicket, title: e.target.value})}
                    className="input-field"
                  />
                </div>

                <div className="form-group">
                  <label>Describe the problem *</label>
                  <textarea
                    placeholder="What's happening? Include any error messages you're seeing..."
                    value={newTicket.description}
                    onChange={(e) => setNewTicket({...newTicket, description: e.target.value})}
                    className="textarea-field"
                    rows="5"
                  />
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Category</label>
                    <select
                      value={newTicket.category}
                      onChange={(e) => setNewTicket({...newTicket, category: e.target.value})}
                      className="select-field"
                    >
                      <option value="dev_env">Development Environment</option>
                      <option value="build_deploy">Build & Deployment</option>
                      <option value="git">Git Issues</option>
                      <option value="vscode">VS Code</option>
                      <option value="os">Operating System</option>
                      <option value="network">Network Issues</option>
                      <option value="saas_config">SaaS Configuration</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label>Urgency</label>
                    <select
                      value={newTicket.urgency}
                      onChange={(e) => setNewTicket({...newTicket, urgency: e.target.value})}
                      className="select-field"
                    >
                      <option value="low">Low</option>
                      <option value="normal">Normal</option>
                      <option value="high">High</option>
                      <option value="critical">Critical</option>
                    </select>
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>System (optional)</label>
                    <input
                      type="text"
                      placeholder="e.g., Vercel, Railway, GitHub"
                      value={newTicket.affected_system}
                      onChange={(e) => setNewTicket({...newTicket, affected_system: e.target.value})}
                      className="input-field"
                    />
                  </div>

                  <div className="form-group">
                    <label>Project (optional)</label>
                    <input
                      type="text"
                      placeholder="e.g., mortgage-crm"
                      value={newTicket.affected_project}
                      onChange={(e) => setNewTicket({...newTicket, affected_project: e.target.value})}
                      className="input-field"
                    />
                  </div>
                </div>

                <button
                  onClick={submitItTicket}
                  className="btn-submit-ticket"
                  disabled={submittingTicket || !newTicket.description.trim()}
                >
                  {submittingTicket ? 'Analyzing...' : 'Submit Issue →'}
                </button>
              </div>

              {/* Ticket List */}
              <div className="helpdesk-tickets-card">
                <div className="tickets-header">
                  <h3>Your IT Tickets</h3>
                  <div className="ticket-filters">
                    <button
                      className={`filter-btn ${ticketStatusFilter === 'all' ? 'active' : ''}`}
                      onClick={() => setTicketStatusFilter('all')}
                    >
                      All
                    </button>
                    <button
                      className={`filter-btn ${ticketStatusFilter === 'awaiting_approval' ? 'active' : ''}`}
                      onClick={() => setTicketStatusFilter('awaiting_approval')}
                    >
                      Awaiting Approval
                    </button>
                    <button
                      className={`filter-btn ${ticketStatusFilter === 'approved' ? 'active' : ''}`}
                      onClick={() => setTicketStatusFilter('approved')}
                    >
                      Approved
                    </button>
                    <button
                      className={`filter-btn ${ticketStatusFilter === 'resolved' ? 'active' : ''}`}
                      onClick={() => setTicketStatusFilter('resolved')}
                    >
                      Resolved
                    </button>
                  </div>
                </div>

                {loadingTickets ? (
                  <p>Loading tickets...</p>
                ) : itTickets.length === 0 ? (
                  <div className="empty-state">
                                        <p>No IT tickets yet.</p>
                    <p className="empty-hint">Submit an issue above to get AI-powered help.</p>
                  </div>
                ) : (
                  <div className="tickets-list">
                    {itTickets.map((ticket) => (
                      <div
                        key={ticket.id}
                        className={`ticket-item ${selectedTicket?.id === ticket.id ? 'selected' : ''}`}
                        onClick={() => setSelectedTicket(ticket)}
                      >
                        <div className="ticket-header">
                          <div className="ticket-title">
                            {ticket.title || ticket.description.substring(0, 50) + '...'}
                          </div>
                          <span className={`ticket-status status-${ticket.status}`}>
                            {ticket.status === 'analyzing' && 'Analyzing'}
                            {ticket.status === 'awaiting_approval' && 'Awaiting Approval'}
                            {ticket.status === 'approved' && 'Approved'}
                            {ticket.status === 'resolved' && 'Resolved'}
                          </span>
                        </div>
                        <div className="ticket-meta">
                          <span>{new Date(ticket.created_at).toLocaleString()}</span>
                          {ticket.root_cause && <span> • {ticket.root_cause}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Ticket Details */}
              {selectedTicket && (
                <div className="helpdesk-details-card">
                  <h3>Ticket #{selectedTicket.id}: {selectedTicket.title || 'IT Issue'}</h3>

                  <div className="detail-section">
                    <h4>Problem Description</h4>
                    <p>{selectedTicket.description}</p>
                  </div>

                  {selectedTicket.ai_diagnosis && (
                    <div className="detail-section">
                      <h4>AI Diagnosis</h4>
                      <p><strong>Root Cause:</strong> {selectedTicket.root_cause}</p>
                      <p>{selectedTicket.ai_diagnosis}</p>
                    </div>
                  )}

                  {selectedTicket.proposed_fix && (
                    <div className="detail-section">
                      <h4>Proposed Fix ({selectedTicket.proposed_fix.risk_level} risk)</h4>

                      {selectedTicket.proposed_fix.steps && (
                        <div>
                          <p><strong>Steps:</strong></p>
                          <ol>
                            {selectedTicket.proposed_fix.steps.map((step, i) => (
                              <li key={i}>{step}</li>
                            ))}
                          </ol>
                        </div>
                      )}

                      {selectedTicket.proposed_fix.commands && selectedTicket.proposed_fix.commands.length > 0 && (
                        <div className="commands-section">
                          <p><strong>Commands to Run:</strong></p>
                          {selectedTicket.proposed_fix.commands.map((cmd, i) => (
                            <div key={i} className="command-block">
                              <p className="command-description">{cmd.description}</p>
                              <div className="command-display">
                                <code>{cmd.command}</code>
                                <button
                                  onClick={() => {
                                    navigator.clipboard.writeText(cmd.command);
                                    toast.success('Command copied!');
                                  }}
                                  className="btn-copy-cmd"
                                >
                                  Copy
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      {selectedTicket.status === 'awaiting_approval' && (
                        <div className="action-buttons">
                          <button
                            onClick={() => approveTicket(selectedTicket.id)}
                            className="btn-approve"
                          >
                            ✅ Approve Fix
                          </button>
                          <button
                            onClick={() => setSelectedTicket(null)}
                            className="btn-dismiss"
                          >
                            ❌ Dismiss
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {selectedTicket.status === 'approved' && (
                    <div className="detail-section">
                      <h4>Mark as Resolved</h4>
                      <p>After running the commands above, describe the result:</p>
                      <textarea
                        placeholder="What happened when you ran the commands? Did it fix the issue?"
                        value={resolutionNotes}
                        onChange={(e) => setResolutionNotes(e.target.value)}
                        className="textarea-field"
                        rows="3"
                      />
                      <button
                        onClick={() => resolveTicket(selectedTicket.id)}
                        className="btn-resolve"
                        disabled={!resolutionNotes.trim()}
                      >
                        Mark as Resolved
                      </button>
                    </div>
                  )}

                  {selectedTicket.status === 'resolved' && selectedTicket.resolution_notes && (
                    <div className="detail-section">
                      <h4>✅ Resolution</h4>
                      <p>{selectedTicket.resolution_notes}</p>
                      <p className="resolved-date">
                        Resolved on {new Date(selectedTicket.resolved_at).toLocaleString()}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {activeSection === 'dialer-settings' && (
            <DialerSettingsSection />
          )}

          {activeSection === 'client-portals' && (
            <PURLManager />
          )}

          {activeSection === 'integration-settings' && (
            <IntegrationSettings />
          )}

          {/* User Profile Sections */}
          {activeSection === 'profile-info' && (
            <div className="profile-section">
              <h2>Profile Information</h2>
              <p className="section-description">
                Manage your personal information and contact details
              </p>

              {profileMessage.text && (
                <div className={`profile-message ${profileMessage.type}`}>
                  {profileMessage.text}
                </div>
              )}

              {loadingProfile ? (
                <div className="loading-state">Loading profile...</div>
              ) : (
                <div className="profile-form">
                  <div className="form-group">
                    <label>First Name</label>
                    <input
                      type="text"
                      value={userProfile.first_name}
                      onChange={(e) => setUserProfile({ ...userProfile, first_name: e.target.value })}
                      placeholder="Enter your first name"
                    />
                  </div>

                  <div className="form-group">
                    <label>Last Name</label>
                    <input
                      type="text"
                      value={userProfile.last_name}
                      onChange={(e) => setUserProfile({ ...userProfile, last_name: e.target.value })}
                      placeholder="Enter your last name"
                    />
                  </div>

                  <div className="form-group">
                    <label>Email</label>
                    <input
                      type="email"
                      value={userProfile.email}
                      disabled
                      className="disabled-input"
                    />
                    <small className="form-hint">Email cannot be changed here. Contact administrator.</small>
                  </div>

                  <div className="form-group">
                    <label>Phone</label>
                    <input
                      type="tel"
                      value={userProfile.phone}
                      onChange={(e) => setUserProfile({ ...userProfile, phone: formatPhoneNumber(e.target.value) })}
                      placeholder="Enter your phone number"
                    />
                  </div>

                  <div className="form-group">
                    <label>Job Title</label>
                    <input
                      type="text"
                      value={userProfile.job_title}
                      onChange={(e) => setUserProfile({ ...userProfile, job_title: e.target.value })}
                      placeholder="Enter your job title"
                    />
                  </div>

                  <div className="form-group">
                    <label>NMLS Number</label>
                    <input
                      type="text"
                      value={userProfile.nmls_number}
                      onChange={(e) => setUserProfile({ ...userProfile, nmls_number: e.target.value })}
                      placeholder="Enter your NMLS number"
                    />
                  </div>

                  <button
                    className="btn-primary"
                    onClick={saveUserProfile}
                    disabled={savingProfile}
                    style={{ marginTop: '24px' }}
                  >
                    {savingProfile ? 'Saving...' : 'Save Profile'}
                  </button>
                </div>
              )}
            </div>
          )}

          {activeSection === 'account-settings' && (
            <div className="profile-section">
              <h2>Account Settings</h2>
              <p className="section-description">
                Manage your account preferences and settings
              </p>

              <div className="account-info-card">
                <h3>Account Information</h3>
                <div className="info-row">
                  <span className="info-label">Email:</span>
                  <span className="info-value">{userProfile.email}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Account Status:</span>
                  <span className="info-value status-active">Active</span>
                </div>
              </div>

              <div className="account-actions">
                <h3>Account Actions</h3>
                <p className="section-description">
                  Need to change your email? Contact your system administrator.
                </p>
              </div>
            </div>
          )}

          {activeSection === 'security' && (
            <div className="profile-section">
              <h2>Security</h2>
              <p className="section-description">
                Manage your password and security settings
              </p>

              {profileMessage.text && (
                <div className={`profile-message ${profileMessage.type}`}>
                  {profileMessage.text}
                </div>
              )}

              <div className="password-change-form">
                <h3>Change Password</h3>

                <div className="form-group">
                  <label>Current Password</label>
                  <input
                    type="password"
                    value={passwordData.current_password}
                    onChange={(e) => setPasswordData({ ...passwordData, current_password: e.target.value })}
                    placeholder="Enter current password"
                  />
                </div>

                <div className="form-group">
                  <label>New Password</label>
                  <input
                    type="password"
                    value={passwordData.new_password}
                    onChange={(e) => setPasswordData({ ...passwordData, new_password: e.target.value })}
                    placeholder="Enter new password"
                  />
                </div>

                <div className="form-group">
                  <label>Confirm New Password</label>
                  <input
                    type="password"
                    value={passwordData.confirm_password}
                    onChange={(e) => setPasswordData({ ...passwordData, confirm_password: e.target.value })}
                    placeholder="Confirm new password"
                  />
                </div>

                <button
                  className="btn-primary"
                  onClick={changePassword}
                  disabled={changingPassword || !passwordData.current_password || !passwordData.new_password || !passwordData.confirm_password}
                >
                  {changingPassword ? 'Changing...' : 'Change Password'}
                </button>
              </div>
            </div>
          )}

          {activeSection === 'work-hours' && (
            <div className="profile-section">
              <h2>Work Hours</h2>
              <p className="section-description">
                Set your available hours for scheduling appointments. All calendars will use these hours to determine your availability.
              </p>

              {profileMessage.text && (
                <div className={`profile-message ${profileMessage.type}`}>
                  {profileMessage.text}
                </div>
              )}

              {loadingProfile ? (
                <div className="loading-state">Loading work hours...</div>
              ) : (
                <div className="work-hours-form">
                  {/* Per-Day Schedule */}
                  <div className="work-hours-card" style={{
                    background: '#f9fafb',
                    borderRadius: '12px',
                    padding: '24px',
                    marginBottom: '24px'
                  }}>
                    <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '8px', color: '#1a1a1a' }}>Daily Schedule</h3>
                    <p style={{ fontSize: '14px', color: '#666', marginBottom: '20px' }}>
                      Set different hours for each day
                    </p>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].map(day => {
                        const isEnabled = (userProfile.work_days || []).includes(day);
                        const dayHours = (userProfile.daily_hours || {})[day] || {};
                        const dayStart = dayHours.start || userProfile.work_hours_start || '09:00';
                        const dayEnd = dayHours.end || userProfile.work_hours_end || '17:00';

                        return (
                          <div key={day} style={{
                            display: 'grid',
                            gridTemplateColumns: '120px 44px 1fr 1fr',
                            alignItems: 'center',
                            gap: '12px',
                            padding: '10px 14px',
                            background: isEnabled ? 'white' : '#f3f4f6',
                            borderRadius: '8px',
                            border: '1px solid',
                            borderColor: isEnabled ? '#d1d5db' : '#e5e7eb',
                            transition: 'all 0.15s ease'
                          }}>
                            <span style={{
                              fontSize: '14px',
                              fontWeight: isEnabled ? '600' : '400',
                              color: isEnabled ? '#1a1a1a' : '#9ca3af',
                              textTransform: 'capitalize'
                            }}>
                              {day}
                            </span>

                            <label style={{ position: 'relative', display: 'inline-block', width: '36px', height: '20px', cursor: 'pointer' }}>
                              <input
                                type="checkbox"
                                checked={isEnabled}
                                onChange={() => {
                                  const workDays = userProfile.work_days || [];
                                  if (workDays.includes(day)) {
                                    setUserProfile({ ...userProfile, work_days: workDays.filter(d => d !== day) });
                                  } else {
                                    setUserProfile({ ...userProfile, work_days: [...workDays, day] });
                                  }
                                }}
                                style={{ opacity: 0, width: 0, height: 0 }}
                              />
                              <span style={{
                                position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
                                backgroundColor: isEnabled ? '#217F8D' : '#d1d5db',
                                borderRadius: '20px', transition: 'background-color 0.2s'
                              }}>
                                <span style={{
                                  position: 'absolute', height: '16px', width: '16px', left: isEnabled ? '18px' : '2px', bottom: '2px',
                                  backgroundColor: 'white', borderRadius: '50%', transition: 'left 0.2s'
                                }} />
                              </span>
                            </label>

                            {isEnabled ? (
                              <>
                                <select
                                  value={dayStart}
                                  onChange={(e) => {
                                    const newDailyHours = { ...(userProfile.daily_hours || {}) };
                                    newDailyHours[day] = { ...(newDailyHours[day] || {}), start: e.target.value, end: dayEnd };
                                    setUserProfile({ ...userProfile, daily_hours: newDailyHours });
                                  }}
                                  style={{
                                    padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: '6px',
                                    fontSize: '13px', background: 'white'
                                  }}
                                >
                                  {Array.from({ length: 48 }, (_, i) => {
                                    const h = Math.floor(i / 2);
                                    const m = i % 2 === 0 ? '00' : '30';
                                    const val = `${h.toString().padStart(2, '0')}:${m}`;
                                    const display = h === 0 ? `12:${m} AM` : h < 12 ? `${h}:${m} AM` : h === 12 ? `12:${m} PM` : `${h - 12}:${m} PM`;
                                    return <option key={val} value={val}>{display}</option>;
                                  })}
                                </select>
                                <select
                                  value={dayEnd}
                                  onChange={(e) => {
                                    const newDailyHours = { ...(userProfile.daily_hours || {}) };
                                    newDailyHours[day] = { ...(newDailyHours[day] || {}), start: dayStart, end: e.target.value };
                                    setUserProfile({ ...userProfile, daily_hours: newDailyHours });
                                  }}
                                  style={{
                                    padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: '6px',
                                    fontSize: '13px', background: 'white'
                                  }}
                                >
                                  {Array.from({ length: 48 }, (_, i) => {
                                    const h = Math.floor(i / 2);
                                    const m = i % 2 === 0 ? '00' : '30';
                                    const val = `${h.toString().padStart(2, '0')}:${m}`;
                                    const display = h === 0 ? `12:${m} AM` : h < 12 ? `${h}:${m} AM` : h === 12 ? `12:${m} PM` : `${h - 12}:${m} PM`;
                                    return <option key={val} value={val}>{display}</option>;
                                  })}
                                </select>
                              </>
                            ) : (
                              <span style={{ gridColumn: 'span 2', fontSize: '13px', color: '#9ca3af', fontStyle: 'italic' }}>
                                Day off
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Blocked Time Slots */}
                  <div className="work-hours-card" style={{
                    background: '#f9fafb',
                    borderRadius: '12px',
                    padding: '24px',
                    marginBottom: '24px'
                  }}>
                    <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '8px', color: '#1a1a1a' }}>Blocked Time Slots</h3>
                    <p style={{ fontSize: '14px', color: '#666', marginBottom: '20px' }}>
                      Protect specific times from being scheduled (e.g., lunch, meetings)
                    </p>

                    {(userProfile.blocked_times || []).length > 0 && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '16px' }}>
                        {(userProfile.blocked_times || []).map((block, idx) => (
                          <div key={block.id || idx} style={{
                            display: 'grid',
                            gridTemplateColumns: '1fr 1fr 120px 120px 36px',
                            alignItems: 'center',
                            gap: '10px',
                            padding: '10px 14px',
                            background: 'white',
                            borderRadius: '8px',
                            border: '1px solid #d1d5db'
                          }}>
                            <input
                              type="text"
                              value={block.label || ''}
                              placeholder="Label (e.g., Lunch)"
                              onChange={(e) => {
                                const updated = [...(userProfile.blocked_times || [])];
                                updated[idx] = { ...updated[idx], label: e.target.value };
                                setUserProfile({ ...userProfile, blocked_times: updated });
                              }}
                              style={{
                                padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: '6px',
                                fontSize: '13px'
                              }}
                            />
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                              {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d, di) => {
                                const fullDay = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'][di];
                                const isSelected = (block.days || []).includes(fullDay);
                                return (
                                  <button
                                    key={d}
                                    type="button"
                                    onClick={() => {
                                      const updated = [...(userProfile.blocked_times || [])];
                                      const blockDays = updated[idx].days || [];
                                      updated[idx] = {
                                        ...updated[idx],
                                        days: isSelected ? blockDays.filter(x => x !== fullDay) : [...blockDays, fullDay]
                                      };
                                      setUserProfile({ ...userProfile, blocked_times: updated });
                                    }}
                                    style={{
                                      padding: '2px 6px', fontSize: '11px', borderRadius: '4px', cursor: 'pointer',
                                      border: '1px solid', transition: 'all 0.1s',
                                      borderColor: isSelected ? '#217F8D' : '#d1d5db',
                                      background: isSelected ? 'rgba(33, 127, 141, 0.1)' : 'white',
                                      color: isSelected ? '#217F8D' : '#999',
                                      fontWeight: isSelected ? '600' : '400'
                                    }}
                                  >
                                    {d}
                                  </button>
                                );
                              })}
                            </div>
                            <select
                              value={block.start || '12:00'}
                              onChange={(e) => {
                                const updated = [...(userProfile.blocked_times || [])];
                                updated[idx] = { ...updated[idx], start: e.target.value };
                                setUserProfile({ ...userProfile, blocked_times: updated });
                              }}
                              style={{
                                padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: '6px',
                                fontSize: '13px', background: 'white'
                              }}
                            >
                              {Array.from({ length: 48 }, (_, i) => {
                                const h = Math.floor(i / 2);
                                const m = i % 2 === 0 ? '00' : '30';
                                const val = `${h.toString().padStart(2, '0')}:${m}`;
                                const display = h === 0 ? `12:${m} AM` : h < 12 ? `${h}:${m} AM` : h === 12 ? `12:${m} PM` : `${h - 12}:${m} PM`;
                                return <option key={val} value={val}>{display}</option>;
                              })}
                            </select>
                            <select
                              value={block.end || '13:00'}
                              onChange={(e) => {
                                const updated = [...(userProfile.blocked_times || [])];
                                updated[idx] = { ...updated[idx], end: e.target.value };
                                setUserProfile({ ...userProfile, blocked_times: updated });
                              }}
                              style={{
                                padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: '6px',
                                fontSize: '13px', background: 'white'
                              }}
                            >
                              {Array.from({ length: 48 }, (_, i) => {
                                const h = Math.floor(i / 2);
                                const m = i % 2 === 0 ? '00' : '30';
                                const val = `${h.toString().padStart(2, '0')}:${m}`;
                                const display = h === 0 ? `12:${m} AM` : h < 12 ? `${h}:${m} AM` : h === 12 ? `12:${m} PM` : `${h - 12}:${m} PM`;
                                return <option key={val} value={val}>{display}</option>;
                              })}
                            </select>
                            <button
                              type="button"
                              onClick={() => {
                                const updated = (userProfile.blocked_times || []).filter((_, i) => i !== idx);
                                setUserProfile({ ...userProfile, blocked_times: updated });
                              }}
                              style={{
                                padding: '6px', background: 'none', border: '1px solid #e5e7eb', borderRadius: '6px',
                                cursor: 'pointer', color: '#ef4444', fontSize: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center'
                              }}
                              title="Remove"
                            >
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    <button
                      type="button"
                      onClick={() => {
                        const newBlock = {
                          id: Math.random().toString(36).substr(2, 8),
                          label: '',
                          days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
                          start: '12:00',
                          end: '13:00'
                        };
                        setUserProfile({
                          ...userProfile,
                          blocked_times: [...(userProfile.blocked_times || []), newBlock]
                        });
                      }}
                      style={{
                        padding: '10px 18px', background: 'white', border: '2px dashed #d1d5db',
                        borderRadius: '8px', cursor: 'pointer', fontSize: '14px', color: '#217F8D',
                        fontWeight: '500', transition: 'all 0.15s', display: 'flex', alignItems: 'center', gap: '8px'
                      }}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14"/></svg>
                      Add Time Block
                    </button>
                  </div>

                  <div style={{
                    background: '#e8f4f6',
                    borderRadius: '8px',
                    padding: '16px',
                    marginBottom: '24px',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px'
                  }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#217F8D" strokeWidth="2" style={{ flexShrink: 0, marginTop: '2px' }}>
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 16v-4" />
                      <path d="M12 8h.01" />
                    </svg>
                    <div>
                      <p style={{ fontSize: '14px', color: '#1a1a1a', fontWeight: '500', marginBottom: '4px' }}>
                        How this affects scheduling
                      </p>
                      <p style={{ fontSize: '13px', color: '#666', margin: 0 }}>
                        When clients or team members schedule appointments with you, they'll only see available time slots within your work hours and on your selected work days. Blocked time slots are excluded from availability.
                      </p>
                    </div>
                  </div>

                  <button
                    className="btn-primary"
                    onClick={saveUserProfile}
                    disabled={savingProfile}
                    style={{ padding: '12px 24px' }}
                  >
                    {savingProfile ? 'Saving...' : 'Save Work Hours'}
                  </button>
                </div>
              )}
            </div>
          )}


          {/* Organizational Settings Sections */}
          {activeSection === 'account-management' && (
            <div className="account-management-section">
              <div className="section-header">
                <div>
                  <h2>Account Management</h2>
                  <p className="section-description">
                    Manage company accounts, users, and system settings
                  </p>
                </div>
              </div>

              {/* KPI Dashboard */}
              <div className="account-kpi-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginBottom: '24px' }}>
                <div className="kpi-card" style={{ background: '#f8fafc', borderRadius: '12px', padding: '20px', textAlign: 'center' }}>
                  <div style={{ fontSize: '32px', fontWeight: '700', color: '#1e293b' }}>3</div>
                  <div style={{ fontSize: '14px', color: '#64748b' }}>Active Accounts</div>
                </div>
                <div className="kpi-card" style={{ background: '#f8fafc', borderRadius: '12px', padding: '20px', textAlign: 'center' }}>
                  <div style={{ fontSize: '32px', fontWeight: '700', color: '#1e293b' }}>25</div>
                  <div style={{ fontSize: '14px', color: '#64748b' }}>Total Users</div>
                </div>
                <div className="kpi-card" style={{ background: '#f8fafc', borderRadius: '12px', padding: '20px', textAlign: 'center' }}>
                  <div style={{ fontSize: '32px', fontWeight: '700', color: '#22c55e' }}>$12,450</div>
                  <div style={{ fontSize: '14px', color: '#64748b' }}>Monthly Revenue</div>
                </div>
                <div className="kpi-card" style={{ background: '#f8fafc', borderRadius: '12px', padding: '20px', textAlign: 'center' }}>
                  <div style={{ fontSize: '32px', fontWeight: '700', color: '#3b82f6' }}>98%</div>
                  <div style={{ fontSize: '14px', color: '#64748b' }}>System Health</div>
                </div>
              </div>

              {/* Quick Actions */}
              <div className="quick-actions" style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
                <button className="btn-primary" onClick={() => navigate('/users/create')}>
                  + Add New User
                </button>
                <button className="btn-secondary" onClick={() => navigate('/team-members')}>
                  View Team Members
                </button>
                <button className="btn-secondary" onClick={() => setActiveSection('integration-marketplace')}>
                  Manage Integrations
                </button>
              </div>

              {/* Accounts List */}
              <div className="accounts-section" style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0', marginBottom: '24px' }}>
                <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Accounts</h3>
                </div>
                <div style={{ padding: '20px' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                        <th style={{ textAlign: 'left', padding: '12px 0', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Account</th>
                        <th style={{ textAlign: 'left', padding: '12px 0', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Users</th>
                        <th style={{ textAlign: 'left', padding: '12px 0', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Status</th>
                        <th style={{ textAlign: 'left', padding: '12px 0', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Plan</th>
                        <th style={{ textAlign: 'right', padding: '12px 0', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '16px 0' }}>
                          <div style={{ fontWeight: '500', color: '#1e293b' }}>Primary Organization</div>
                          <div style={{ fontSize: '13px', color: '#64748b' }}>admin@perenniaai.com</div>
                        </td>
                        <td style={{ padding: '16px 0', color: '#1e293b' }}>25</td>
                        <td style={{ padding: '16px 0' }}>
                          <span style={{ background: '#dcfce7', color: '#166534', padding: '4px 12px', borderRadius: '20px', fontSize: '13px' }}>Active</span>
                        </td>
                        <td style={{ padding: '16px 0', color: '#1e293b' }}>Enterprise</td>
                        <td style={{ padding: '16px 0', textAlign: 'right' }}>
                          <button style={{ background: 'transparent', border: '1px solid #e2e8f0', padding: '6px 12px', borderRadius: '6px', cursor: 'pointer', marginRight: '8px' }}>View</button>
                          <button style={{ background: 'transparent', border: '1px solid #e2e8f0', padding: '6px 12px', borderRadius: '6px', cursor: 'pointer' }}>Edit</button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Security Overview - Expanded */}
              <div className="security-section" style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0', marginBottom: '24px' }}>
                <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Security Overview</h3>
                  <span style={{ background: '#dcfce7', color: '#166534', padding: '4px 12px', borderRadius: '20px', fontSize: '13px', fontWeight: '500' }}>All Systems Secure</span>
                </div>
                <div style={{ padding: '20px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ color: '#22c55e', fontSize: '20px' }}>✓</span>
                      <div>
                        <div style={{ fontWeight: '500', color: '#1e293b' }}>SSL Certificate</div>
                        <div style={{ fontSize: '13px', color: '#64748b' }}>Valid until Dec 2025</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ color: '#22c55e', fontSize: '20px' }}>✓</span>
                      <div>
                        <div style={{ fontWeight: '500', color: '#1e293b' }}>2FA Enabled</div>
                        <div style={{ fontSize: '13px', color: '#64748b' }}>All admin accounts</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ color: '#22c55e', fontSize: '20px' }}>✓</span>
                      <div>
                        <div style={{ fontWeight: '500', color: '#1e293b' }}>Data Encryption</div>
                        <div style={{ fontSize: '13px', color: '#64748b' }}>AES-256 at rest</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ color: '#22c55e', fontSize: '20px' }}>✓</span>
                      <div>
                        <div style={{ fontWeight: '500', color: '#1e293b' }}>Firewall Active</div>
                        <div style={{ fontSize: '13px', color: '#64748b' }}>WAF protection</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Access Control & Compliance */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px' }}>
                <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                  <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Access Control</h3>
                  </div>
                  <div style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: '#f8fafc', borderRadius: '8px' }}>
                        <div>
                          <div style={{ fontWeight: '500', color: '#1e293b' }}>Active Sessions</div>
                          <div style={{ fontSize: '13px', color: '#64748b' }}>Currently logged in users</div>
                        </div>
                        <div style={{ fontSize: '24px', fontWeight: '700', color: '#3b82f6' }}>12</div>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: '#f8fafc', borderRadius: '8px' }}>
                        <div>
                          <div style={{ fontWeight: '500', color: '#1e293b' }}>Failed Login Attempts</div>
                          <div style={{ fontSize: '13px', color: '#64748b' }}>Last 24 hours</div>
                        </div>
                        <div style={{ fontSize: '24px', fontWeight: '700', color: '#22c55e' }}>0</div>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: '#f8fafc', borderRadius: '8px' }}>
                        <div>
                          <div style={{ fontWeight: '500', color: '#1e293b' }}>Password Resets</div>
                          <div style={{ fontSize: '13px', color: '#64748b' }}>Last 7 days</div>
                        </div>
                        <div style={{ fontSize: '24px', fontWeight: '700', color: '#64748b' }}>2</div>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: '#f8fafc', borderRadius: '8px' }}>
                        <div>
                          <div style={{ fontWeight: '500', color: '#1e293b' }}>API Keys Active</div>
                          <div style={{ fontSize: '13px', color: '#64748b' }}>Third-party integrations</div>
                        </div>
                        <div style={{ fontSize: '24px', fontWeight: '700', color: '#64748b' }}>5</div>
                      </div>
                    </div>
                    <button style={{ marginTop: '16px', width: '100%', padding: '10px', background: '#f1f5f9', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: '500', color: '#475569' }}>
                      Manage Sessions
                    </button>
                  </div>
                </div>

                <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                  <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Compliance Status</h3>
                  </div>
                  <div style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <span style={{ fontSize: '20px' }}>🛡️</span>
                          <div>
                            <div style={{ fontWeight: '500', color: '#1e293b' }}>SOC 2 Type II</div>
                            <div style={{ fontSize: '13px', color: '#64748b' }}>Certified compliant</div>
                          </div>
                        </div>
                        <span style={{ background: '#dcfce7', color: '#166534', padding: '4px 10px', borderRadius: '20px', fontSize: '12px' }}>Verified</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <span style={{ fontSize: '20px' }}>🔒</span>
                          <div>
                            <div style={{ fontWeight: '500', color: '#1e293b' }}>GLBA Compliant</div>
                            <div style={{ fontSize: '13px', color: '#64748b' }}>Financial data protection</div>
                          </div>
                        </div>
                        <span style={{ background: '#dcfce7', color: '#166534', padding: '4px 10px', borderRadius: '20px', fontSize: '12px' }}>Verified</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <span style={{ fontSize: '20px' }}>🌐</span>
                          <div>
                            <div style={{ fontWeight: '500', color: '#1e293b' }}>CCPA Ready</div>
                            <div style={{ fontSize: '13px', color: '#64748b' }}>California privacy law</div>
                          </div>
                        </div>
                        <span style={{ background: '#dcfce7', color: '#166534', padding: '4px 10px', borderRadius: '20px', fontSize: '12px' }}>Verified</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <span style={{ fontSize: '20px' }}>📋</span>
                          <div>
                            <div style={{ fontWeight: '500', color: '#1e293b' }}>RESPA Compliant</div>
                            <div style={{ fontSize: '13px', color: '#64748b' }}>Real estate settlement</div>
                          </div>
                        </div>
                        <span style={{ background: '#dcfce7', color: '#166534', padding: '4px 10px', borderRadius: '20px', fontSize: '12px' }}>Verified</span>
                      </div>
                    </div>
                    <button style={{ marginTop: '16px', width: '100%', padding: '10px', background: '#f1f5f9', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: '500', color: '#475569' }}>
                      View Compliance Reports
                    </button>
                  </div>
                </div>
              </div>

              {/* Security Audit Log */}
              <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0', marginBottom: '24px' }}>
                <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Recent Security Events</h3>
                  <button
                    onClick={fetchSecurityAuditLogs}
                    style={{ background: 'transparent', border: '1px solid #e2e8f0', padding: '6px 12px', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}
                  >
                    {loadingAuditLogs ? 'Loading...' : 'Refresh'}
                  </button>
                </div>
                <div style={{ padding: '0' }}>
                  {loadingAuditLogs ? (
                    <div style={{ padding: '40px 20px', textAlign: 'center', color: '#64748b' }}>
                      Loading security events...
                    </div>
                  ) : auditLogsError ? (
                    <div style={{ padding: '40px 20px', textAlign: 'center', color: '#ef4444' }}>
                      {auditLogsError}
                    </div>
                  ) : securityAuditLogs.length === 0 ? (
                    <div style={{ padding: '40px 20px', textAlign: 'center', color: '#64748b' }}>
                      No security events recorded yet
                    </div>
                  ) : (
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ background: '#f8fafc' }}>
                          <th style={{ textAlign: 'left', padding: '12px 20px', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Event</th>
                          <th style={{ textAlign: 'left', padding: '12px 20px', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>User</th>
                          <th style={{ textAlign: 'left', padding: '12px 20px', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>IP Address</th>
                          <th style={{ textAlign: 'left', padding: '12px 20px', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Time</th>
                          <th style={{ textAlign: 'left', padding: '12px 20px', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {securityAuditLogs.map((log, index) => (
                          <tr key={log.id || index} style={{ borderBottom: index < securityAuditLogs.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                            <td style={{ padding: '14px 20px', color: '#1e293b' }}>{log.event}</td>
                            <td style={{ padding: '14px 20px', color: '#64748b' }}>{log.actorName || log.targetName || 'System'}</td>
                            <td style={{ padding: '14px 20px', color: '#64748b', fontFamily: 'monospace', fontSize: '13px' }}>{log.ipAddress}</td>
                            <td style={{ padding: '14px 20px', color: '#64748b' }}>{log.timeAgo}</td>
                            <td style={{ padding: '14px 20px' }}>
                              <span style={{
                                ...getStatusBadgeStyle(log.status),
                                padding: '2px 8px',
                                borderRadius: '4px',
                                fontSize: '12px'
                              }}>
                                {log.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              {/* Data Protection & Backup */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px' }}>
                <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                  <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Data Protection</h3>
                  </div>
                  <div style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ width: '40px', height: '40px', background: '#dbeafe', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '18px' }}>🔐</div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: '500', color: '#1e293b' }}>Encryption at Rest</div>
                          <div style={{ fontSize: '13px', color: '#64748b' }}>AES-256 encryption for all stored data</div>
                        </div>
                        <span style={{ color: '#22c55e', fontSize: '18px' }}>✓</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ width: '40px', height: '40px', background: '#dbeafe', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '18px' }}>🔒</div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: '500', color: '#1e293b' }}>Encryption in Transit</div>
                          <div style={{ fontSize: '13px', color: '#64748b' }}>TLS 1.3 for all connections</div>
                        </div>
                        <span style={{ color: '#22c55e', fontSize: '18px' }}>✓</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ width: '40px', height: '40px', background: '#dbeafe', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '18px' }}>🗝️</div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: '500', color: '#1e293b' }}>Key Management</div>
                          <div style={{ fontSize: '13px', color: '#64748b' }}>AWS KMS managed keys</div>
                        </div>
                        <span style={{ color: '#22c55e', fontSize: '18px' }}>✓</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ width: '40px', height: '40px', background: '#dbeafe', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '18px' }}>🛡️</div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: '500', color: '#1e293b' }}>PII Masking</div>
                          <div style={{ fontSize: '13px', color: '#64748b' }}>Sensitive data automatically masked</div>
                        </div>
                        <span style={{ color: '#22c55e', fontSize: '18px' }}>✓</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                  <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Backup & Recovery</h3>
                  </div>
                  <div style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div style={{ padding: '16px', background: '#f0fdf4', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                          <div style={{ fontWeight: '500', color: '#166534' }}>Last Backup</div>
                          <span style={{ color: '#22c55e', fontSize: '14px' }}>✓ Successful</span>
                        </div>
                        <div style={{ fontSize: '24px', fontWeight: '700', color: '#166534' }}>2 hours ago</div>
                        <div style={{ fontSize: '13px', color: '#15803d', marginTop: '4px' }}>Next backup in 4 hours</div>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', background: '#f8fafc', borderRadius: '8px' }}>
                        <div>
                          <div style={{ fontWeight: '500', color: '#1e293b' }}>Backup Frequency</div>
                          <div style={{ fontSize: '13px', color: '#64748b' }}>Automatic every 6 hours</div>
                        </div>
                        <button style={{ background: 'transparent', border: '1px solid #e2e8f0', padding: '4px 12px', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}>Configure</button>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', background: '#f8fafc', borderRadius: '8px' }}>
                        <div>
                          <div style={{ fontWeight: '500', color: '#1e293b' }}>Retention Period</div>
                          <div style={{ fontSize: '13px', color: '#64748b' }}>90 days of backup history</div>
                        </div>
                        <button style={{ background: 'transparent', border: '1px solid #e2e8f0', padding: '4px 12px', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}>Configure</button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Security Recommendations */}
              <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Security Recommendations</h3>
                </div>
                <div style={{ padding: '20px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '16px', background: '#fffbeb', borderRadius: '8px', border: '1px solid #fde68a' }}>
                      <span style={{ fontSize: '20px' }}>⚠️</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: '500', color: '#92400e' }}>Enable 2FA for 3 remaining users</div>
                        <div style={{ fontSize: '13px', color: '#a16207' }}>Some team members haven't enabled two-factor authentication</div>
                      </div>
                      <button style={{ background: '#f59e0b', color: 'white', border: 'none', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', fontWeight: '500' }}>Enable Now</button>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '16px', background: '#f0f9ff', borderRadius: '8px', border: '1px solid #bae6fd' }}>
                      <span style={{ fontSize: '20px' }}>💡</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: '500', color: '#0369a1' }}>Review API key permissions</div>
                        <div style={{ fontSize: '13px', color: '#0284c7' }}>2 API keys have full admin access - consider limiting scope</div>
                      </div>
                      <button style={{ background: '#0ea5e9', color: 'white', border: 'none', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', fontWeight: '500' }}>Review</button>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '16px', background: '#f0fdf4', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
                      <span style={{ fontSize: '20px' }}>✅</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: '500', color: '#166534' }}>Password policy is strong</div>
                        <div style={{ fontSize: '13px', color: '#15803d' }}>Minimum 12 characters with complexity requirements</div>
                      </div>
                      <span style={{ color: '#22c55e', fontWeight: '500' }}>Configured</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeSection === 'company-info' && (
            <div className="company-info-section">
              <h2>Company Information</h2>
              <p className="section-description">
                Manage your company profile and contact information
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'team-members' && (
            <div className="team-members-section">
              <div className="section-header">
                <div>
                  <h2>Team Members ({teamMembers.length})</h2>
                  <p className="section-description">
                    Team members involved in your loan workflow (processors, underwriters, loan officers, etc.)
                  </p>
                </div>
                <button
                  className="btn-primary"
                  onClick={() => navigate('/team-members')}
                >
                  Manage Team Members
                </button>
              </div>

              {loadingTeam ? (
                <div className="loading-state">Loading team members...</div>
              ) : (
                <>
                  {teamMembers.length === 0 ? (
                    <div className="empty-state">
                                            <p>No workflow team members found. Team members will appear once they are assigned to loans.</p>
                    </div>
                  ) : (
                    <div className="team-members-table-container">
                      <table className="team-members-table">
                        <thead>
                          <tr>
                            <th>Member</th>
                            <th>Role</th>
                            <th>Email</th>
                            <th>Loans</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {teamMembers.map((member, index) => (
                            <tr
                              key={member.id || `${member.name || 'unknown'}-${index}`}
                              className="team-member-row"
                              onClick={() => {
                                // Navigate to team member profile if they have a user_id
                                if (member.user_id) {
                                  navigate(`/team/${member.user_id}`);
                                }
                              }}
                              style={{ cursor: member.user_id ? 'pointer' : 'default' }}
                            >
                              <td>
                                <div className="member-info-cell">
                                  <div className="member-avatar-small">
                                    {(member.name || 'U').charAt(0).toUpperCase()}
                                  </div>
                                  <div>
                                    <div className="member-name">{member.name || 'Unknown'}</div>
                                  </div>
                                </div>
                              </td>
                              <td>
                                <span className="role-badge-inline">{member.role || 'N/A'}</span>
                              </td>
                              <td>
                                <span className="member-email-text">{member.email || 'N/A'}</span>
                              </td>
                              <td>
                                <span className="loan-count-badge">
                                  📋 {member.loan_count} {member.loan_count === 1 ? 'loan' : 'loans'}
                                </span>
                              </td>
                              <td>
                                <button
                                  className="btn-view-profile"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (member.user_id) {
                                      navigate(`/team/${member.user_id}`);
                                    }
                                  }}
                                  disabled={!member.user_id}
                                >
                                  View Profile
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {activeSection === 'branding' && (
            <div className="branding-section">
              <h2>Branding</h2>
              <p className="section-description">
                Customize your company's branding and appearance
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {/* Smart Scheduler — merged into Calendar Settings (sidebar navigates to /calendar-settings) */}

          {/* Video Meetings */}
          {activeSection === 'video-meetings' && (
            <VideoMeetings />
          )}

          {/* Master Administrator - Account Management */}
          {activeSection === 'account-mgmt' && (
            <div className="account-mgmt-section">
              <div className="page-header">
                <div>
                  <h2>Account Management</h2>
                  <p className="section-description">
                    Manage users, permissions, and security monitoring
                  </p>
                </div>
              </div>

              {/* Collapsible Cards Container */}
              <div className="collapsible-cards-container">

                {/* User Management Card */}
                <div
                  className={`collapsible-card ${expandedCards.userManagement ? 'expanded' : ''}`}
                  onClick={() => !expandedCards.userManagement && setExpandedCards(prev => ({ ...prev, userManagement: true, securityMonitoring: false }))}
                >
                  <div
                    className="collapsible-card-header"
                    onClick={(e) => { e.stopPropagation(); setExpandedCards(prev => ({ ...prev, userManagement: !prev.userManagement })); }}
                  >
                    <div className="card-header-content">
                      <div className="card-icon">👥</div>
                      <div>
                        <h3>User Management</h3>
                        <p>Manage registered users and permissions</p>
                      </div>
                    </div>
                    <div className="card-header-right">
                      <div className="card-stats">
                        <span className="stat">{users.length} users</span>
                        <span className="stat">{users.filter(u => u.is_active).length} active</span>
                      </div>
                      <span className="expand-arrow">{expandedCards.userManagement ? '▼' : '▶'}</span>
                    </div>
                  </div>

                  {expandedCards.userManagement && (
                    <div className="collapsible-card-content" onClick={(e) => e.stopPropagation()}>
                      <div className="card-actions-bar">
                        <button
                          className="btn-primary"
                          onClick={() => setShowAddUserModal(true)}
                        >
                          + Add User
                        </button>
                        {selectedUsers.length > 0 && (
                          <button
                            className="btn-danger"
                            onClick={handleBulkDelete}
                            disabled={deletingUsers}
                          >
                            {deletingUsers ? 'Deleting...' : `Delete Selected (${selectedUsers.length})`}
                          </button>
                        )}
                      </div>

                      {usersError && <div className="error-message">{usersError}</div>}

                      {loadingUsers ? (
                        <div className="loading">Loading users...</div>
                      ) : (
                        <div className="users-table-container">
                  <table className="users-table">
                    <thead>
                      <tr>
                        <th style={{ width: '40px' }}>
                          <input
                            type="checkbox"
                            onChange={handleSelectAll}
                            checked={selectedUsers.length > 0 && selectedUsers.length === users.filter(u => u.id !== JSON.parse(localStorage.getItem('user') || '{}').id).length}
                            style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                          />
                        </th>
                        <th>User</th>
                        <th>Role</th>
                        <th>Status</th>
                        <th>Verified</th>
                        <th>Onboarded</th>
                        <th>Registered</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((user) => {
                        const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
                        const isCurrentUser = user.id === currentUser.id;
                        return (
                          <tr
                            key={user.id}
                            className={`clickable-user-row ${!user.is_active ? 'inactive-user' : ''} ${selectedUsers.includes(user.id) ? 'selected-row' : ''}`}
                            onClick={() => navigate(`/users/${user.id}`)}
                            style={{ cursor: 'pointer' }}
                          >
                            <td onClick={(e) => e.stopPropagation()}>
                              <input
                                type="checkbox"
                                checked={selectedUsers.includes(user.id)}
                                onChange={() => handleSelectUser(user.id)}
                                disabled={isCurrentUser}
                                style={{ width: '18px', height: '18px', cursor: isCurrentUser ? 'not-allowed' : 'pointer' }}
                                title={isCurrentUser ? "Cannot select yourself" : "Select user"}
                              />
                            </td>
                            <td>
                              <div className="user-info">
                                <div className="user-avatar">{user.full_name?.charAt(0) || user.email.charAt(0)}</div>
                                <div>
                                  <div className="user-name">
                                    {user.full_name || 'Unnamed User'}
                                    {isCurrentUser && <span className="current-user-badge">You</span>}
                                  </div>
                                  <div className="user-email-small">{user.email}</div>
                                  <div className="user-id">ID: {user.id}</div>
                                </div>
                              </div>
                            </td>
                            <td>
                              {editingUser === user.id ? (
                                <select
                                  value={user.role}
                                  onChange={(e) => handleUpdateRole(user.id, e.target.value)}
                                  onBlur={() => setEditingUser(null)}
                                  onClick={(e) => e.stopPropagation()}
                                  autoFocus
                                  className="role-select"
                                >
                                  <option value="loan_officer">Loan Officer</option>
                                  <option value="admin">Admin</option>
                                  <option value="processor">Processor</option>
                                  <option value="underwriter">Underwriter</option>
                                  <option value="manager">Manager</option>
                                </select>
                              ) : (
                                <span
                                  className="role-badge"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setEditingUser(user.id);
                                  }}
                                  title="Click to edit"
                                >
                                  {user.role || 'loan_officer'}
                                </span>
                              )}
                            </td>
                            <td>
                              <button
                                className={`status-badge ${user.is_active ? 'active' : 'inactive'}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleToggleActive(user.id, user.is_active);
                                }}
                              >
                                {user.is_active ? 'Active' : 'Inactive'}
                              </button>
                            </td>
                            <td>
                              <button
                                className={`verify-badge ${user.email_verified ? 'verified' : 'unverified'}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleToggleVerified(user.id, user.email_verified);
                                }}
                              >
                                {user.email_verified ? 'Verified' : 'Not Verified'}
                              </button>
                            </td>
                            <td>
                              <span className={`onboarding-badge ${user.onboarding_completed ? 'completed' : 'pending'}`}>
                                {user.onboarding_completed ? 'Completed' : 'Pending'}
                              </span>
                            </td>
                            <td className="date-cell">{formatDate(user.created_at)}</td>
                            <td>
                              <button
                                className="btn-delete"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteUser(user.id);
                                }}
                                disabled={isCurrentUser}
                                title={isCurrentUser ? "You cannot delete your own account" : "Delete user"}
                              >
                                Delete
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>

                  {users.length === 0 && (
                            <div className="empty-state">
                              <p>No users found</p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Security Monitoring Card */}
                <div
                  className={`collapsible-card ${expandedCards.securityMonitoring ? 'expanded' : ''}`}
                  onClick={() => !expandedCards.securityMonitoring && setExpandedCards(prev => ({ ...prev, securityMonitoring: true, userManagement: false }))}
                >
                  <div
                    className="collapsible-card-header"
                    onClick={(e) => { e.stopPropagation(); setExpandedCards(prev => ({ ...prev, securityMonitoring: !prev.securityMonitoring })); }}
                  >
                    <div className="card-header-content">
                      <div className="card-icon">🔒</div>
                      <div>
                        <h3>Security Monitoring</h3>
                        <p>Login history, sessions, and audit logs</p>
                      </div>
                    </div>
                    <div className="card-header-right">
                      <div className="card-stats">
                        <span className="stat">{securityData.activeSessions?.length || 0} active sessions</span>
                      </div>
                      <span className="expand-arrow">{expandedCards.securityMonitoring ? '▼' : '▶'}</span>
                    </div>
                  </div>

                  {expandedCards.securityMonitoring && (
                    <div className="collapsible-card-content" onClick={(e) => e.stopPropagation()}>
                      {loadingSecurityData ? (
                        <div className="loading">Loading security data...</div>
                      ) : (
                        <div className="security-monitoring-content">
                          {/* Active Sessions */}
                          <div className="security-section">
                            <h4>Active Sessions</h4>
                            <div className="sessions-list">
                              {securityData.activeSessions?.length > 0 ? (
                                securityData.activeSessions.map((session, i) => (
                                  <div key={i} className="session-item">
                                    <div className="session-info">
                                      <span className="session-device">{session.device || 'Unknown Device'}</span>
                                      <span className="session-location">{session.location || 'Unknown'}</span>
                                    </div>
                                    <span className="session-time">{session.lastActive || 'Now'}</span>
                                  </div>
                                ))
                              ) : (
                                <div className="empty-state-small">
                                  <p>Current session is active</p>
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Recent Login History */}
                          <div className="security-section">
                            <h4>Recent Login History</h4>
                            <div className="login-history-list">
                              {securityData.loginHistory?.length > 0 ? (
                                securityData.loginHistory.slice(0, 5).map((login, i) => (
                                  <div key={i} className={`login-item ${login.success ? 'success' : 'failed'}`}>
                                    <div className="login-info">
                                      <span className={`login-status ${login.success ? 'success' : 'failed'}`}>
                                        {login.success ? '✓' : '✗'}
                                      </span>
                                      <span className="login-email">{login.email || 'Unknown'}</span>
                                    </div>
                                    <div className="login-meta">
                                      <span className="login-ip">{login.ip || '-'}</span>
                                      <span className="login-time">{login.timestamp || '-'}</span>
                                    </div>
                                  </div>
                                ))
                              ) : (
                                <div className="empty-state-small">
                                  <p>No recent login activity</p>
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Audit Log Preview */}
                          <div className="security-section">
                            <h4>Recent Audit Activity</h4>
                            <div className="audit-log-list">
                              {securityData.auditLog?.length > 0 ? (
                                securityData.auditLog.slice(0, 5).map((log, i) => (
                                  <div key={i} className="audit-item">
                                    <div className="audit-info">
                                      <span className="audit-action">{log.action}</span>
                                      <span className="audit-user">{log.user || 'System'}</span>
                                    </div>
                                    <span className="audit-time">{log.timestamp || '-'}</span>
                                  </div>
                                ))
                              ) : (
                                <div className="empty-state-small">
                                  <p>No recent audit activity</p>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

              </div>

              {/* Add User Modal - Outside collapsible cards */}
              {showAddUserModal && (
                <div className="modal-overlay" style={{
                  position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                  background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
                }}>
                  <div className="modal-content" style={{
                    background: 'white', borderRadius: '12px', padding: '24px', width: '100%', maxWidth: '500px', boxShadow: '0 4px 20px rgba(0,0,0,0.15)'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                      <h3 style={{ margin: 0 }}>Invite New User</h3>
                      <button onClick={() => setShowAddUserModal(false)} style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: '#666' }}>&times;</button>
                    </div>

                    <div style={{ background: '#eff6ff', padding: '12px 16px', borderRadius: '8px', marginBottom: '20px', fontSize: '13px', color: '#1d4ed8' }}>
                      <strong>Note:</strong> An invitation email will be sent to the user to create their account and set their password.
                    </div>

                    <form onSubmit={handleAddUser}>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
                        <div>
                          <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>First Name *</label>
                          <input
                            type="text"
                            value={newUser.first_name}
                            onChange={(e) => setNewUser({ ...newUser, first_name: e.target.value })}
                            placeholder="John"
                            required
                            style={{ width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: '6px', fontSize: '14px', boxSizing: 'border-box' }}
                          />
                        </div>
                        <div>
                          <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Last Name *</label>
                          <input
                            type="text"
                            value={newUser.last_name}
                            onChange={(e) => setNewUser({ ...newUser, last_name: e.target.value })}
                            placeholder="Doe"
                            required
                            style={{ width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: '6px', fontSize: '14px', boxSizing: 'border-box' }}
                          />
                        </div>
                      </div>

                      <div style={{ marginBottom: '16px' }}>
                        <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Email *</label>
                        <input
                          type="email"
                          value={newUser.email}
                          onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                          placeholder="john@example.com"
                          required
                          style={{ width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: '6px', fontSize: '14px', boxSizing: 'border-box' }}
                        />
                      </div>

                      <div style={{ marginBottom: '16px' }}>
                        <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Role</label>
                        <select
                          value={newUser.role}
                          onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                          style={{ width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: '6px', fontSize: '14px', boxSizing: 'border-box' }}
                        >
                          <option value="loan_officer">Loan Officer</option>
                          <option value="admin">Admin</option>
                          <option value="processor">Processor</option>
                          <option value="underwriter">Underwriter</option>
                          <option value="manager">Manager</option>
                          <option value="application_analyst">Application Analyst</option>
                        </select>
                      </div>

                      <div style={{ marginBottom: '20px' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={newUser.is_active}
                            onChange={(e) => setNewUser({ ...newUser, is_active: e.target.checked })}
                            style={{ width: '18px', height: '18px' }}
                          />
                          <span>Set as Active User</span>
                        </label>
                      </div>

                      <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          onClick={() => setShowAddUserModal(false)}
                          style={{ padding: '10px 20px', background: '#f3f4f6', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: '500' }}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          disabled={addingUser}
                          style={{ padding: '10px 20px', background: '#4f46e5', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: '500', opacity: addingUser ? 0.7 : 1 }}
                        >
                          {addingUser ? 'Sending Invite...' : 'Send Invitation'}
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Clear Dummy Data Section */}
          {activeSection === 'clear-data' && (
            <div className="clear-data-section">
              <div className="page-header">
                <div>
                  <h2>Clear Dummy Data</h2>
                  <p className="section-description">
                    Remove all sample/test data to prepare for workflow-based tasks
                  </p>
                </div>
              </div>

              <div className="warning-card" style={{background: '#fff3cd', border: '2px solid #ffc107', padding: '24px', borderRadius: '8px', marginBottom: '24px'}}>
                <div style={{display: 'flex', alignItems: 'start', gap: '16px'}}>
                                    <div>
                    <h3 style={{margin: '0 0 12px 0', color: '#856404'}}>Warning: This action cannot be undone!</h3>
                    <p style={{margin: '0 0 12px 0', color: '#856404'}}>This will permanently delete:</p>
                    <ul style={{margin: '0', paddingLeft: '20px', color: '#856404'}}>
                      <li>All outstanding tasks (AI tasks, regular tasks, process tasks)</li>
                      <li>All pending approval reconciliation events</li>
                      <li>All unified messages (SMS, Email, Teams)</li>
                      <li>All loans and leads</li>
                      <li>All activities, conversations, and referral partners</li>
                      <li>Client for Life data (closed loans)</li>
                    </ul>
                    <p style={{margin: '12px 0 0 0', fontWeight: 'bold', color: '#856404'}}>
                      Your user accounts and settings will be preserved.
                    </p>
                  </div>
                </div>
              </div>

              <div className="info-card" style={{marginBottom: '24px'}}>
                                <div className="info-content">
                  <h3>What happens after clearing?</h3>
                  <p>After clearing all dummy data, you'll have a clean slate to:</p>
                  <ul>
                    <li>Create tasks based on your actual loan workflow</li>
                    <li>Import real leads and loans</li>
                    <li>Start with production-ready data</li>
                    <li>Test your workflow from scratch</li>
                  </ul>
                </div>
              </div>

              <div style={{display: 'flex', gap: '16px', justifyContent: 'center', padding: '32px'}}>
                <button
                  className="btn-danger"
                  onClick={async () => {
                    try {
                      const response = await fetch(`${API_BASE_URL}/api/v1/admin/clear-sample-data`, {
                        method: 'POST',
                        headers: {
                          'Authorization': `Bearer ${localStorage.getItem('token')}`,
                          'Content-Type': 'application/json'
                        }
                      });

                      if (response.ok) {
                        const result = await response.json();
                        toast.success(`✅ Success! Cleared:\n` +
                              `- ${result.deleted.tasks || 0} tasks\n` +
                              `- ${result.deleted.ai_tasks || 0} AI tasks\n` +
                              `- ${result.deleted.process_tasks || 0} process tasks\n` +
                              `- ${result.deleted.reconciliation_events || 0} reconciliation events\n` +
                              `- ${result.deleted.sms_messages || 0} SMS messages\n` +
                              `- ${result.deleted.email_messages || 0} emails\n` +
                              `- ${result.deleted.teams_messages || 0} Teams messages\n` +
                              `- ${result.deleted.loans || 0} loans\n` +
                              `- ${result.deleted.leads || 0} leads\n` +
                              `- ${result.deleted.activities || 0} activities\n\n` +
                              `Your CRM is now ready for workflow-based tasks!`);
                      } else {
                        const error = await response.json();
                        toast.error(`❌ Error: ${error.detail || 'Failed to clear data'}`);
                      }
                    } catch (error) {
                      console.error('Error clearing data:', error);
                      toast.error(`❌ Error clearing data: ${error.message}`);
                    }
                  }}
                  style={{
                    padding: '16px 48px',
                    fontSize: '18px',
                    fontWeight: 'bold',
                    background: '#dc3545',
                    color: 'white',
                    border: 'none',
                    borderRadius: '8px',
                    cursor: 'pointer'
                  }}
                >
                  Clear All Dummy Data
                </button>
              </div>
            </div>
          )}

          {/* Agent Governance - System Settings */}
          {activeSection === 'agent-governance-system' && (
            <div className="agent-governance-section">
              <div className="page-header">
                <div>
                  <h2>Agent Governance - System Settings</h2>
                  <p className="section-description">Control system-wide agent features and monitoring</p>
                </div>
                <div className="header-actions">
                  <button className="btn-secondary" onClick={() => navigate('/agents')}>
                    View Agent Dashboard
                  </button>
                  <button className="btn-primary" onClick={saveAgentGovernanceSettings} disabled={savingAgentSettings}>
                    {savingAgentSettings ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </div>

              {agentSettingsMessage.text && (
                <div className={`message-banner ${agentSettingsMessage.type}`}>
                  {agentSettingsMessage.text}
                </div>
              )}

              {loadingAgentSettings ? (
                <div className="loading-state">Loading agent settings...</div>
              ) : (
                <div className="settings-grid">
                  <div className="settings-card">
                    <h3>Core Features</h3>
                    <div className="setting-row">
                      <div className="setting-info">
                        <label className="setting-label">Enable Agent Governance System</label>
                        <p className="setting-description">Turn on monitoring, testing, and compliance tracking for all agents</p>
                      </div>
                      <label className="toggle-switch">
                        <input type="checkbox" checked={agentGovernanceSettings.agentGovernanceEnabled} onChange={() => handleAgentSettingToggle('agentGovernanceEnabled')} />
                        <span className="toggle-slider"></span>
                      </label>
                    </div>

                    <div className="setting-row">
                      <div className="setting-info">
                        <label className="setting-label">Automatic Health Checks</label>
                        <p className="setting-description">Run health checks every hour and send alerts for issues</p>
                      </div>
                      <label className="toggle-switch">
                        <input type="checkbox" checked={agentGovernanceSettings.autoHealthChecks} onChange={() => handleAgentSettingToggle('autoHealthChecks')} />
                        <span className="toggle-slider"></span>
                      </label>
                    </div>

                    <div className="setting-row">
                      <div className="setting-info">
                        <label className="setting-label">Cost Tracking</label>
                        <p className="setting-description">Track and enforce cost budgets for agent operations</p>
                      </div>
                      <label className="toggle-switch">
                        <input type="checkbox" checked={agentGovernanceSettings.costTrackingEnabled} onChange={() => handleAgentSettingToggle('costTrackingEnabled')} />
                        <span className="toggle-slider"></span>
                      </label>
                    </div>

                    <div className="setting-row">
                      <div className="setting-info">
                        <label className="setting-label">Enable WebSocket Real-time Updates</label>
                        <p className="setting-description">Push live metrics to connected clients every 5 seconds</p>
                      </div>
                      <label className="toggle-switch">
                        <input type="checkbox" checked={agentGovernanceSettings.websocketEnabled} onChange={() => handleAgentSettingToggle('websocketEnabled')} />
                        <span className="toggle-slider"></span>
                      </label>
                    </div>

                    <div className="setting-row">
                      <div className="setting-info">
                        <label className="setting-label">Audit Log All Changes</label>
                        <p className="setting-description">Log all agent configuration changes with user attribution</p>
                      </div>
                      <label className="toggle-switch">
                        <input type="checkbox" checked={agentGovernanceSettings.auditLogging} onChange={() => handleAgentSettingToggle('auditLogging')} />
                        <span className="toggle-slider"></span>
                      </label>
                    </div>
                  </div>

                  <div className="settings-card">
                    <h3>Quick Actions</h3>
                    <div className="settings-action-grid">
                      <button className="btn-secondary" onClick={() => navigate('/agents')}>
                        View Agent Dashboard
                      </button>
                      <button className="btn-secondary" onClick={() => navigate('/agent-gym')}>
                        Open Agent Gym
                      </button>
                      <button className="btn-secondary" onClick={async () => {
                        try {
                          const health = await agentAPI.getSystemHealth();
                          toast.info(JSON.stringify(health, null, 2));
                        } catch (e) {
                          toast.error('Failed to fetch system health: ' + e.message);
                        }
                      }}>
                        Run Health Check
                      </button>
                      <button className="btn-secondary" onClick={() => {
                        const config = JSON.stringify(agentGovernanceSettings, null, 2);
                        const blob = new Blob([config], { type: 'application/json' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = 'agent-governance-config.json';
                        a.click();
                      }}>
                        Export Configuration
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Agent Governance - Performance Thresholds */}
          {activeSection === 'agent-governance-thresholds' && (
            <div className="agent-governance-section">
              <div className="page-header">
                <div>
                  <h2>Agent Governance - Performance Thresholds</h2>
                  <p className="section-description">Set default performance standards for all agents</p>
                </div>
                <button className="btn-primary" onClick={saveAgentGovernanceSettings} disabled={savingAgentSettings}>
                  {savingAgentSettings ? 'Saving...' : 'Save Changes'}
                </button>
              </div>

              {agentSettingsMessage.text && (
                <div className={`message-banner ${agentSettingsMessage.type}`}>
                  {agentSettingsMessage.text}
                </div>
              )}

              <div className="settings-card">
                <h3>Default Thresholds</h3>
                <p className="card-description">These defaults apply to all agents unless overridden individually.</p>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Minimum Success Rate</label>
                    <p className="setting-description">Agents below this rate will be flagged for review</p>
                  </div>
                  <div className="setting-input-wrapper">
                    <input
                      type="number"
                      className="setting-input"
                      value={agentGovernanceSettings.defaultSuccessRate}
                      onChange={(e) => handleAgentSettingChange('defaultSuccessRate', Number(e.target.value))}
                      min="80"
                      max="100"
                    />
                    <span className="input-suffix">%</span>
                  </div>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Maximum Response Time (P95)</label>
                    <p className="setting-description">95th percentile response time threshold</p>
                  </div>
                  <div className="setting-input-wrapper">
                    <input
                      type="number"
                      className="setting-input"
                      value={agentGovernanceSettings.defaultResponseTime}
                      onChange={(e) => handleAgentSettingChange('defaultResponseTime', Number(e.target.value))}
                      min="1000"
                      max="60000"
                    />
                    <span className="input-suffix">ms</span>
                  </div>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Maximum Cost Per Success</label>
                    <p className="setting-description">Cost efficiency threshold per successful execution</p>
                  </div>
                  <div className="setting-input-wrapper">
                    <span className="input-prefix">$</span>
                    <input
                      type="number"
                      className="setting-input"
                      value={agentGovernanceSettings.defaultMaxCost}
                      onChange={(e) => handleAgentSettingChange('defaultMaxCost', Number(e.target.value))}
                      step="0.001"
                      min="0"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Agent Governance - Cost Budgets */}
          {activeSection === 'agent-governance-costs' && (
            <div className="agent-governance-section">
              <div className="page-header">
                <div>
                  <h2>Agent Governance - Cost Budgets</h2>
                  <p className="section-description">Set cost limits and budgets for agent operations</p>
                </div>
                <button className="btn-primary" onClick={saveAgentGovernanceSettings} disabled={savingAgentSettings}>
                  {savingAgentSettings ? 'Saving...' : 'Save Changes'}
                </button>
              </div>

              {agentSettingsMessage.text && (
                <div className={`message-banner ${agentSettingsMessage.type}`}>
                  {agentSettingsMessage.text}
                </div>
              )}

              <div className="settings-card">
                <h3>Budget Settings</h3>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Daily Budget (per agent)</label>
                    <p className="setting-description">Maximum daily spend per individual agent</p>
                  </div>
                  <div className="setting-input-wrapper">
                    <span className="input-prefix">$</span>
                    <input
                      type="number"
                      className="setting-input"
                      value={agentGovernanceSettings.defaultDailyBudget}
                      onChange={(e) => handleAgentSettingChange('defaultDailyBudget', Number(e.target.value))}
                      min="0"
                    />
                  </div>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Monthly Budget (system-wide)</label>
                    <p className="setting-description">Total monthly budget across all agents</p>
                  </div>
                  <div className="setting-input-wrapper">
                    <span className="input-prefix">$</span>
                    <input
                      type="number"
                      className="setting-input"
                      value={agentGovernanceSettings.systemMonthlyBudget}
                      onChange={(e) => handleAgentSettingChange('systemMonthlyBudget', Number(e.target.value))}
                      min="0"
                    />
                  </div>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Cost Alert Threshold</label>
                    <p className="setting-description">Trigger alerts when spending reaches this percentage of budget</p>
                  </div>
                  <div className="setting-input-wrapper">
                    <input
                      type="number"
                      className="setting-input"
                      value={agentGovernanceSettings.costAlertThreshold}
                      onChange={(e) => handleAgentSettingChange('costAlertThreshold', Number(e.target.value))}
                      min="50"
                      max="100"
                    />
                    <span className="input-suffix">%</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Agent Governance - Alerts & Notifications */}
          {activeSection === 'agent-governance-alerts' && (
            <div className="agent-governance-section">
              <div className="page-header">
                <div>
                  <h2>Agent Governance - Alerts & Notifications</h2>
                  <p className="section-description">Configure how you receive agent alerts and notifications</p>
                </div>
                <button className="btn-primary" onClick={saveAgentGovernanceSettings} disabled={savingAgentSettings}>
                  {savingAgentSettings ? 'Saving...' : 'Save Changes'}
                </button>
              </div>

              {agentSettingsMessage.text && (
                <div className={`message-banner ${agentSettingsMessage.type}`}>
                  {agentSettingsMessage.text}
                </div>
              )}

              <div className="settings-card">
                <h3>Alert Configuration</h3>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Alert Routing</label>
                    <p className="setting-description">Where to send agent alerts</p>
                  </div>
                  <select
                    className="setting-select"
                    value={agentGovernanceSettings.alertChannel}
                    onChange={(e) => handleAgentSettingChange('alertChannel', e.target.value)}
                  >
                    <option value="Email">Email</option>
                    <option value="Slack">Slack</option>
                    <option value="Discord">Discord</option>
                    <option value="SMS">SMS</option>
                  </select>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Slack Webhook URL</label>
                    <p className="setting-description">Webhook for Slack notifications</p>
                  </div>
                  <input
                    type="url"
                    className="setting-input wide"
                    value={agentGovernanceSettings.slackWebhook}
                    onChange={(e) => handleAgentSettingChange('slackWebhook', e.target.value)}
                    placeholder="https://hooks.slack.com/services/..."
                  />
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Daily Digest Notifications</label>
                    <p className="setting-description">Receive daily digest of agent performance and issues</p>
                  </div>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={agentGovernanceSettings.dailyDigest} onChange={() => handleAgentSettingToggle('dailyDigest')} />
                    <span className="toggle-slider"></span>
                  </label>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Digest Time</label>
                    <p className="setting-description">When to send the daily digest</p>
                  </div>
                  <select
                    className="setting-select"
                    value={agentGovernanceSettings.digestTime}
                    onChange={(e) => handleAgentSettingChange('digestTime', e.target.value)}
                  >
                    <option value="8:00 AM">8:00 AM</option>
                    <option value="12:00 PM">12:00 PM</option>
                    <option value="6:00 PM">6:00 PM</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* Agent Governance - Compliance */}
          {activeSection === 'agent-governance-compliance' && (
            <div className="agent-governance-section">
              <div className="page-header">
                <div>
                  <h2>Agent Governance - Compliance</h2>
                  <p className="section-description">Configure compliance and governance rules for agents</p>
                </div>
                <button className="btn-primary" onClick={saveAgentGovernanceSettings} disabled={savingAgentSettings}>
                  {savingAgentSettings ? 'Saving...' : 'Save Changes'}
                </button>
              </div>

              {agentSettingsMessage.text && (
                <div className={`message-banner ${agentSettingsMessage.type}`}>
                  {agentSettingsMessage.text}
                </div>
              )}

              <div className="settings-card">
                <h3>Compliance Settings</h3>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Enforce Elite Status for Tier 3 Agents</label>
                    <p className="setting-description">Tier 3 agents must maintain Elite performance standards</p>
                  </div>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={agentGovernanceSettings.enforceEliteForTier3} onChange={() => handleAgentSettingToggle('enforceEliteForTier3')} />
                    <span className="toggle-slider"></span>
                  </label>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Fair Lending Monitoring</label>
                    <p className="setting-description">Track disparate impact across protected classes for compliance agents</p>
                  </div>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={agentGovernanceSettings.fairLendingMonitoring} onChange={() => handleAgentSettingToggle('fairLendingMonitoring')} />
                    <span className="toggle-slider"></span>
                  </label>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Require Approval for Agent Changes</label>
                    <p className="setting-description">All agent configuration changes require admin approval</p>
                  </div>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={agentGovernanceSettings.requireApproval} onChange={() => handleAgentSettingToggle('requireApproval')} />
                    <span className="toggle-slider"></span>
                  </label>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Audit Log Retention</label>
                    <p className="setting-description">Required: 7 years (2555 days) for Tier 3 agents</p>
                  </div>
                  <div className="setting-input-wrapper">
                    <input
                      type="number"
                      className="setting-input"
                      value={agentGovernanceSettings.auditRetentionDays}
                      onChange={(e) => handleAgentSettingChange('auditRetentionDays', Number(e.target.value))}
                      min="365"
                    />
                    <span className="input-suffix">days</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Agent Governance - Agent Gym Settings */}
          {activeSection === 'agent-governance-gym' && (
            <div className="agent-governance-section">
              <div className="page-header">
                <div>
                  <h2>Agent Governance - Agent Gym Settings</h2>
                  <p className="section-description">Configure agent training and testing settings</p>
                </div>
                <div className="header-actions">
                  <button className="btn-secondary" onClick={() => navigate('/agent-gym')}>
                    Open Agent Gym
                  </button>
                  <button className="btn-primary" onClick={saveAgentGovernanceSettings} disabled={savingAgentSettings}>
                    {savingAgentSettings ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </div>

              {agentSettingsMessage.text && (
                <div className={`message-banner ${agentSettingsMessage.type}`}>
                  {agentSettingsMessage.text}
                </div>
              )}

              <div className="settings-card">
                <h3>Training & Testing Configuration</h3>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Automatic Daily Testing</label>
                    <p className="setting-description">Run gym scenarios for all agents at 2 AM daily</p>
                  </div>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={agentGovernanceSettings.autoDailyTesting} onChange={() => handleAgentSettingToggle('autoDailyTesting')} />
                    <span className="toggle-slider"></span>
                  </label>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Minimum Pass Rate for Production</label>
                    <p className="setting-description">Agents below this pass rate are flagged for review</p>
                  </div>
                  <div className="setting-input-wrapper">
                    <input
                      type="number"
                      className="setting-input"
                      value={agentGovernanceSettings.minPassRate}
                      onChange={(e) => handleAgentSettingChange('minPassRate', Number(e.target.value))}
                      min="50"
                      max="100"
                    />
                    <span className="input-suffix">%</span>
                  </div>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <label className="setting-label">Block Deployment on Failed Tests</label>
                    <p className="setting-description">Prevent agent deployments if gym tests fail</p>
                  </div>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={agentGovernanceSettings.blockOnFailedTests} onChange={() => handleAgentSettingToggle('blockOnFailedTests')} />
                    <span className="toggle-slider"></span>
                  </label>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Calendly Connection Modal */}
      {showCalendlyModal && (
        <div className="connection-modal-overlay" onClick={() => setShowCalendlyModal(false)}>
          <div className="connection-modal" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close-modal" onClick={() => setShowCalendlyModal(false)}>×</button>
            <div className="modal-header">
              <span className="modal-icon">🗓️</span>
              <h3>Connect Calendly</h3>
              <p className="modal-description">Enter your Calendly API key to sync event types</p>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Calendly API Key</label>
                <input
                  type="password"
                  className="form-input"
                  placeholder="Enter your Calendly API key"
                  value={calendlyApiKey}
                  onChange={(e) => setCalendlyApiKey(e.target.value)}
                />
              </div>
              <div className="help-text">
                <h4>How to get your API key:</h4>
                <ol>
                  <li>Go to <a href="https://calendly.com/integrations/api_webhooks" target="_blank" rel="noopener noreferrer">Calendly Integrations</a></li>
                  <li>Click "Generate New Token"</li>
                  <li>Copy the token and paste it above</li>
                </ol>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowCalendlyModal(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={saveCalendlyConnection}
                disabled={!calendlyApiKey.trim()}
              >
                Connect
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Settings;
