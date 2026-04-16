import React, { useState, useEffect, useCallback } from 'react';
import { useAsyncOperation, useFormSubmit, APIError } from '../utils/errorHandling';
import { toast } from '../utils/toast';
import './ClientPortalSettings.css';
import { getToken } from '../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const ClientPortalSettings = () => {
  const [activeTab, setActiveTab] = useState('branding');
  const [settings, setSettings] = useState(null);
  const [originalSettings, setOriginalSettings] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [defaultPages, setDefaultPages] = useState([]);
  const [timezones, setTimezones] = useState([]);
  const [statistics, setStatistics] = useState(null);
  const [testNotificationType, setTestNotificationType] = useState('email');
  const [testRecipient, setTestRecipient] = useState('');
  const [colorPreview, setColorPreview] = useState(null);

  // Hooks handle toast notifications automatically
  const { execute: fetchSettings, loading, error } = useAsyncOperation();
  const { execute: saveSettings, loading: saving } = useFormSubmit();

  // Fetch settings on mount
  useEffect(() => {
    loadSettings();
    loadDefaultPages();
    loadTimezones();
    loadStatistics();
  }, []);

  // Track changes
  useEffect(() => {
    if (settings && originalSettings) {
      setHasChanges(JSON.stringify(settings) !== JSON.stringify(originalSettings));
    }
  }, [settings, originalSettings]);

  const loadSettings = async () => {
    try {
      const token = getToken();
      const response = await fetchSettings(async () => {
        const res = await fetch(`${API_URL}/api/v1/client-portal-settings`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) {
          const error = await res.json();
          throw new APIError(error.detail?.message || 'Failed to load settings', res.status);
        }
        return res.json();
      });

      if (response?.data) {
        setSettings(response.data);
        setOriginalSettings(JSON.parse(JSON.stringify(response.data)));
      }
    } catch (err) {
      // Hook handles toast automatically
    }
  };

  const loadDefaultPages = async () => {
    try {
      const token = getToken();
      const res = await fetch(`${API_URL}/api/v1/client-portal-settings/default-pages`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setDefaultPages(data.data || []);
      }
    } catch (err) {
      console.error('Failed to load default pages:', err);
    }
  };

  const loadTimezones = async () => {
    try {
      const token = getToken();
      const res = await fetch(`${API_URL}/api/v1/client-portal-settings/timezones`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setTimezones(data.data || []);
      }
    } catch (err) {
      console.error('Failed to load timezones:', err);
    }
  };

  const loadStatistics = async () => {
    try {
      const token = getToken();
      const res = await fetch(`${API_URL}/api/v1/client-portal-settings/statistics`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setStatistics(data.data || null);
      }
    } catch (err) {
      console.error('Failed to load statistics:', err);
    }
  };

  const handleSave = async () => {
    try {
      const token = getToken();
      await saveSettings(async () => {
        const res = await fetch(`${API_URL}/api/v1/client-portal-settings`, {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(settings)
        });

        if (!res.ok) {
          const error = await res.json();
          if (error.detail?.errors) {
            const fieldErrors = error.detail.errors.map(e => `${e.field}: ${e.message}`).join('\n');
            throw new APIError(`Validation errors:\n${fieldErrors}`, res.status);
          }
          throw new APIError(error.detail?.message || 'Failed to save settings', res.status);
        }
        return res.json();
      });

      setOriginalSettings(JSON.parse(JSON.stringify(settings)));
      setHasChanges(false);
      // Hook handles success toast automatically
    } catch (err) {
      // Hook handles error toast automatically
    }
  };

  const handleReset = () => {
    if (originalSettings) {
      setSettings(JSON.parse(JSON.stringify(originalSettings)));
      setHasChanges(false);
      toast.success('Changes discarded');
    }
  };

  const updateBranding = (field, value) => {
    setSettings(prev => ({
      ...prev,
      branding: { ...prev.branding, [field]: value }
    }));
  };

  const updateAccessControl = (field, value) => {
    setSettings(prev => ({
      ...prev,
      access_control: { ...prev.access_control, [field]: value }
    }));
  };

  const updateNotifications = (field, value) => {
    setSettings(prev => ({
      ...prev,
      notifications: { ...prev.notifications, [field]: value }
    }));
  };

  const updateDocuments = (field, value) => {
    setSettings(prev => ({
      ...prev,
      documents: { ...prev.documents, [field]: value }
    }));
  };

  const updateMessaging = (field, value) => {
    setSettings(prev => ({
      ...prev,
      messaging: { ...prev.messaging, [field]: value }
    }));
  };

  const updateProgressTracking = (field, value) => {
    setSettings(prev => ({
      ...prev,
      progress_tracking: { ...prev.progress_tracking, [field]: value }
    }));
  };

  const updateGlobal = (field, value) => {
    setSettings(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const updatePage = (pageId, field, value) => {
    setSettings(prev => ({
      ...prev,
      pages: prev.pages.map(page =>
        page.page_id === pageId ? { ...page, [field]: value } : page
      )
    }));
  };

  const previewColors = async () => {
    try {
      const token = getToken();
      const params = new URLSearchParams({
        primary_color: settings.branding.primary_color,
        secondary_color: settings.branding.secondary_color,
        accent_color: settings.branding.accent_color,
        header_style: settings.branding.header_style
      });

      const res = await fetch(`${API_URL}/api/v1/client-portal-settings/branding-preview?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        const data = await res.json();
        setColorPreview(data.data);
      }
    } catch (err) {
      console.error('Failed to preview colors:', err);
    }
  };

  const sendTestNotification = async () => {
    if (!testRecipient) {
      toast.error('Please enter a recipient');
      return;
    }

    try {
      const token = getToken();
      const params = new URLSearchParams({ notification_type: testNotificationType });
      if (testNotificationType === 'email') {
        params.append('recipient_email', testRecipient);
      } else {
        params.append('recipient_phone', testRecipient);
      }

      const res = await fetch(`${API_URL}/api/v1/client-portal-settings/test-notification?${params}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        toast.success(`Test ${testNotificationType} sent successfully`);
      } else {
        const error = await res.json();
        toast.error(error.detail?.message || 'Failed to send test notification');
      }
    } catch (err) {
      toast.error('Failed to send test notification');
    }
  };

  if (loading) {
    return (
      <div className="client-portal-settings">
        <div className="loading-state">Loading portal settings...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="client-portal-settings">
        <div className="error-state">
          <h3>Error Loading Settings</h3>
          <p>{error.message}</p>
          <button onClick={loadSettings} className="btn-retry">Retry</button>
        </div>
      </div>
    );
  }

  if (!settings) return null;

  const tabs = [
    { id: 'branding', label: 'Branding' },
    { id: 'access', label: 'Access Control' },
    { id: 'notifications', label: 'Notifications' },
    { id: 'documents', label: 'Documents' },
    { id: 'messaging', label: 'Messaging' },
    { id: 'progress', label: 'Progress Tracking' },
    { id: 'pages', label: 'Portal Pages' },
    { id: 'global', label: 'Global Settings' }
  ];

  return (
    <div className="client-portal-settings">
      <div className="page-header">
        <div className="header-content">
          <h1>Client Portal Settings</h1>
          <p>Configure the borrower portal experience, branding, and access controls</p>
        </div>
        {statistics && (
          <div className="stats-summary">
            <div className="stat-item">
              <span className="stat-value">{statistics.unique_users}</span>
              <span className="stat-label">Active Users</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{statistics.documents_uploaded}</span>
              <span className="stat-label">Documents</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{statistics.satisfaction_score}</span>
              <span className="stat-label">Satisfaction</span>
            </div>
          </div>
        )}
      </div>

      <div className="tabs-container">
        <div className="tabs">
          {tabs.map(tab => (
            <button
              key={tab.id}
              className={`tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="settings-content">
        {/* Branding Tab */}
        {activeTab === 'branding' && (
          <div className="settings-section">
            <h2>Portal Branding</h2>
            <p className="section-description">Customize the look and feel of your client portal</p>

            <div className="form-grid">
              <div className="form-group">
                <label>Company Name</label>
                <input
                  type="text"
                  value={settings.branding.company_name}
                  onChange={(e) => updateBranding('company_name', e.target.value)}
                  maxLength={200}
                />
              </div>

              <div className="form-group">
                <label>Logo URL</label>
                <input
                  type="text"
                  value={settings.branding.logo_url || ''}
                  onChange={(e) => updateBranding('logo_url', e.target.value || null)}
                  placeholder="https://example.com/logo.png"
                />
              </div>

              <div className="form-group">
                <label>Favicon URL</label>
                <input
                  type="text"
                  value={settings.branding.favicon_url || ''}
                  onChange={(e) => updateBranding('favicon_url', e.target.value || null)}
                  placeholder="https://example.com/favicon.ico"
                />
              </div>

              <div className="form-group">
                <label>Header Style</label>
                <select
                  value={settings.branding.header_style}
                  onChange={(e) => updateBranding('header_style', e.target.value)}
                >
                  <option value="default">Default</option>
                  <option value="minimal">Minimal</option>
                  <option value="transparent">Transparent</option>
                </select>
              </div>
            </div>

            <div className="color-settings">
              <h3>Brand Colors</h3>
              <div className="color-grid">
                <div className="color-input">
                  <label>Primary Color</label>
                  <div className="color-picker-wrapper">
                    <input
                      type="color"
                      value={settings.branding.primary_color}
                      onChange={(e) => updateBranding('primary_color', e.target.value)}
                    />
                    <input
                      type="text"
                      value={settings.branding.primary_color}
                      onChange={(e) => updateBranding('primary_color', e.target.value)}
                      pattern="^#[0-9a-fA-F]{6}$"
                    />
                  </div>
                </div>

                <div className="color-input">
                  <label>Secondary Color</label>
                  <div className="color-picker-wrapper">
                    <input
                      type="color"
                      value={settings.branding.secondary_color}
                      onChange={(e) => updateBranding('secondary_color', e.target.value)}
                    />
                    <input
                      type="text"
                      value={settings.branding.secondary_color}
                      onChange={(e) => updateBranding('secondary_color', e.target.value)}
                      pattern="^#[0-9a-fA-F]{6}$"
                    />
                  </div>
                </div>

                <div className="color-input">
                  <label>Accent Color</label>
                  <div className="color-picker-wrapper">
                    <input
                      type="color"
                      value={settings.branding.accent_color}
                      onChange={(e) => updateBranding('accent_color', e.target.value)}
                    />
                    <input
                      type="text"
                      value={settings.branding.accent_color}
                      onChange={(e) => updateBranding('accent_color', e.target.value)}
                      pattern="^#[0-9a-fA-F]{6}$"
                    />
                  </div>
                </div>
              </div>

              <button className="btn-preview" onClick={previewColors}>
                Preview Colors
              </button>

              {colorPreview && (
                <div className="color-preview">
                  <h4>Color Preview</h4>
                  <div className="preview-box" style={{
                    '--preview-primary': colorPreview.css_variables['--primary-color'],
                    '--preview-secondary': colorPreview.css_variables['--secondary-color'],
                    '--preview-accent': colorPreview.css_variables['--accent-color']
                  }}>
                    <div className="preview-header">Header Preview</div>
                    <div className="preview-content">
                      <button className="preview-btn primary">Primary Button</button>
                      <button className="preview-btn accent">Accent Button</button>
                    </div>
                  </div>
                  <div className="contrast-info">
                    <span>Primary on White: <strong>{colorPreview.contrast_info.primary_on_white}</strong></span>
                    <span>Accent on Primary: <strong>{colorPreview.contrast_info.accent_on_primary}</strong></span>
                  </div>
                </div>
              )}
            </div>

            <div className="form-group full-width">
              <label>Footer Text</label>
              <input
                type="text"
                value={settings.branding.footer_text || ''}
                onChange={(e) => updateBranding('footer_text', e.target.value || null)}
                placeholder="e.g., © 2024 Your Company. All rights reserved."
                maxLength={500}
              />
            </div>

            <div className="form-group full-width">
              <label>Custom CSS (Advanced)</label>
              <textarea
                value={settings.branding.custom_css || ''}
                onChange={(e) => updateBranding('custom_css', e.target.value || null)}
                placeholder="/* Add custom CSS styles here */"
                rows={6}
              />
            </div>
          </div>
        )}

        {/* Access Control Tab */}
        {activeTab === 'access' && (
          <div className="settings-section">
            <h2>Access Control</h2>
            <p className="section-description">Configure authentication and security settings</p>

            <div className="settings-group">
              <h3>Authentication</h3>
              <div className="form-grid">
                <div className="form-group toggle-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={settings.access_control.require_login}
                      onChange={(e) => updateAccessControl('require_login', e.target.checked)}
                    />
                    <span>Require Login</span>
                  </label>
                  <p className="field-hint">Users must log in to access the portal</p>
                </div>

                <div className="form-group toggle-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={settings.access_control.allow_guest_access}
                      onChange={(e) => updateAccessControl('allow_guest_access', e.target.checked)}
                      disabled={settings.access_control.require_login}
                    />
                    <span>Allow Guest Access</span>
                  </label>
                  <p className="field-hint">Allow limited access without authentication</p>
                </div>

                <div className="form-group">
                  <label>Session Timeout (minutes)</label>
                  <input
                    type="number"
                    value={settings.access_control.session_timeout_minutes}
                    onChange={(e) => updateAccessControl('session_timeout_minutes', parseInt(e.target.value) || 60)}
                    min={5}
                    max={1440}
                  />
                </div>
              </div>
            </div>

            <div className="settings-group">
              <h3>Login Security</h3>
              <div className="form-grid">
                <div className="form-group">
                  <label>Max Login Attempts</label>
                  <input
                    type="number"
                    value={settings.access_control.max_login_attempts}
                    onChange={(e) => updateAccessControl('max_login_attempts', parseInt(e.target.value) || 5)}
                    min={1}
                    max={20}
                  />
                </div>

                <div className="form-group">
                  <label>Lockout Duration (minutes)</label>
                  <input
                    type="number"
                    value={settings.access_control.lockout_duration_minutes}
                    onChange={(e) => updateAccessControl('lockout_duration_minutes', parseInt(e.target.value) || 30)}
                    min={5}
                    max={1440}
                  />
                </div>
              </div>
            </div>

            <div className="settings-group">
              <h3>Verification Requirements</h3>
              <div className="toggle-list">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.access_control.require_email_verification}
                    onChange={(e) => updateAccessControl('require_email_verification', e.target.checked)}
                  />
                  <span>Require Email Verification</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.access_control.require_phone_verification}
                    onChange={(e) => updateAccessControl('require_phone_verification', e.target.checked)}
                  />
                  <span>Require Phone Verification</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.access_control.enable_mfa}
                    onChange={(e) => updateAccessControl('enable_mfa', e.target.checked)}
                  />
                  <span>Enable Multi-Factor Authentication (MFA)</span>
                </label>
              </div>

              {settings.access_control.enable_mfa && (
                <div className="mfa-methods">
                  <label>MFA Methods</label>
                  <div className="checkbox-group">
                    {['email', 'sms', 'authenticator'].map(method => (
                      <label key={method}>
                        <input
                          type="checkbox"
                          checked={settings.access_control.mfa_methods.includes(method)}
                          onChange={(e) => {
                            const methods = e.target.checked
                              ? [...settings.access_control.mfa_methods, method]
                              : settings.access_control.mfa_methods.filter(m => m !== method);
                            updateAccessControl('mfa_methods', methods);
                          }}
                        />
                        <span>{method.charAt(0).toUpperCase() + method.slice(1)}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Notifications Tab */}
        {activeTab === 'notifications' && (
          <div className="settings-section">
            <h2>Notification Settings</h2>
            <p className="section-description">Configure how and when to notify borrowers</p>

            <div className="settings-group">
              <h3>Notification Channels</h3>
              <div className="toggle-list">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.notifications.enable_email_notifications}
                    onChange={(e) => updateNotifications('enable_email_notifications', e.target.checked)}
                  />
                  <span>Email Notifications</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.notifications.enable_sms_notifications}
                    onChange={(e) => updateNotifications('enable_sms_notifications', e.target.checked)}
                  />
                  <span>SMS Notifications</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.notifications.enable_push_notifications}
                    onChange={(e) => updateNotifications('enable_push_notifications', e.target.checked)}
                  />
                  <span>Push Notifications</span>
                </label>
              </div>
            </div>

            <div className="settings-group">
              <h3>Email Configuration</h3>
              <div className="form-grid">
                <div className="form-group">
                  <label>From Email Address</label>
                  <input
                    type="email"
                    value={settings.notifications.notification_email_from}
                    onChange={(e) => updateNotifications('notification_email_from', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label>Reply-To Email (optional)</label>
                  <input
                    type="email"
                    value={settings.notifications.notification_email_reply_to || ''}
                    onChange={(e) => updateNotifications('notification_email_reply_to', e.target.value || null)}
                  />
                </div>
              </div>
            </div>

            <div className="settings-group">
              <h3>Notification Triggers</h3>
              <div className="trigger-grid">
                {[
                  { key: 'notify_on_document_upload', label: 'Document Uploaded' },
                  { key: 'notify_on_document_approved', label: 'Document Approved' },
                  { key: 'notify_on_document_rejected', label: 'Document Rejected' },
                  { key: 'notify_on_status_change', label: 'Loan Status Change' },
                  { key: 'notify_on_message_received', label: 'New Message Received' },
                  { key: 'notify_on_task_assigned', label: 'Task Assigned' },
                  { key: 'notify_on_milestone_reached', label: 'Milestone Reached' }
                ].map(trigger => (
                  <label key={trigger.key} className="trigger-item">
                    <input
                      type="checkbox"
                      checked={settings.notifications[trigger.key]}
                      onChange={(e) => updateNotifications(trigger.key, e.target.checked)}
                    />
                    <span>{trigger.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="settings-group">
              <h3>Daily Digest</h3>
              <div className="form-grid">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.notifications.enable_daily_digest}
                    onChange={(e) => updateNotifications('enable_daily_digest', e.target.checked)}
                  />
                  <span>Enable Daily Digest Email</span>
                </label>

                {settings.notifications.enable_daily_digest && (
                  <div className="form-group">
                    <label>Send Time</label>
                    <input
                      type="time"
                      value={settings.notifications.digest_send_time}
                      onChange={(e) => updateNotifications('digest_send_time', e.target.value)}
                    />
                  </div>
                )}
              </div>
            </div>

            <div className="settings-group">
              <h3>Test Notification</h3>
              <div className="test-notification">
                <select
                  value={testNotificationType}
                  onChange={(e) => setTestNotificationType(e.target.value)}
                >
                  <option value="email">Email</option>
                  <option value="sms">SMS</option>
                </select>
                <input
                  type={testNotificationType === 'email' ? 'email' : 'tel'}
                  value={testRecipient}
                  onChange={(e) => setTestRecipient(e.target.value)}
                  placeholder={testNotificationType === 'email' ? 'Email address' : 'Phone number'}
                />
                <button className="btn-test" onClick={sendTestNotification}>
                  Send Test
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Documents Tab */}
        {activeTab === 'documents' && (
          <div className="settings-section">
            <h2>Document Settings</h2>
            <p className="section-description">Configure document upload and handling options</p>

            <div className="settings-group">
              <h3>Upload Settings</h3>
              <div className="form-grid">
                <div className="form-group">
                  <label>Max File Size (MB)</label>
                  <input
                    type="number"
                    value={settings.documents.max_file_size_mb}
                    onChange={(e) => updateDocuments('max_file_size_mb', parseInt(e.target.value) || 25)}
                    min={1}
                    max={100}
                  />
                </div>

                <div className="form-group">
                  <label>Document Retention (days)</label>
                  <input
                    type="number"
                    value={settings.documents.document_retention_days}
                    onChange={(e) => updateDocuments('document_retention_days', parseInt(e.target.value) || 365)}
                    min={30}
                    max={3650}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Allowed File Types</label>
                <div className="file-types-grid">
                  {['pdf', 'jpg', 'jpeg', 'png', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt'].map(type => (
                    <label key={type} className="file-type-item">
                      <input
                        type="checkbox"
                        checked={settings.documents.allowed_file_types.includes(type)}
                        onChange={(e) => {
                          const types = e.target.checked
                            ? [...settings.documents.allowed_file_types, type]
                            : settings.documents.allowed_file_types.filter(t => t !== type);
                          updateDocuments('allowed_file_types', types);
                        }}
                      />
                      <span>.{type}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className="settings-group">
              <h3>Document Features</h3>
              <div className="toggle-list">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.documents.enable_document_preview}
                    onChange={(e) => updateDocuments('enable_document_preview', e.target.checked)}
                  />
                  <span>Enable Document Preview</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.documents.enable_document_download}
                    onChange={(e) => updateDocuments('enable_document_download', e.target.checked)}
                  />
                  <span>Enable Document Download</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.documents.require_document_descriptions}
                    onChange={(e) => updateDocuments('require_document_descriptions', e.target.checked)}
                  />
                  <span>Require Document Descriptions</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.documents.auto_categorize_documents}
                    onChange={(e) => updateDocuments('auto_categorize_documents', e.target.checked)}
                  />
                  <span>Auto-Categorize Documents (AI)</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.documents.enable_ocr_processing}
                    onChange={(e) => updateDocuments('enable_ocr_processing', e.target.checked)}
                  />
                  <span>Enable OCR Processing</span>
                </label>
              </div>
            </div>
          </div>
        )}

        {/* Messaging Tab */}
        {activeTab === 'messaging' && (
          <div className="settings-section">
            <h2>Messaging Settings</h2>
            <p className="section-description">Configure portal messaging and communication features</p>

            <div className="settings-group">
              <h3>General Settings</h3>
              <div className="toggle-list">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.messaging.enable_messaging}
                    onChange={(e) => updateMessaging('enable_messaging', e.target.checked)}
                  />
                  <span>Enable Messaging</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.messaging.enable_file_attachments}
                    onChange={(e) => updateMessaging('enable_file_attachments', e.target.checked)}
                    disabled={!settings.messaging.enable_messaging}
                  />
                  <span>Allow File Attachments</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.messaging.enable_read_receipts}
                    onChange={(e) => updateMessaging('enable_read_receipts', e.target.checked)}
                    disabled={!settings.messaging.enable_messaging}
                  />
                  <span>Enable Read Receipts</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.messaging.enable_typing_indicators}
                    onChange={(e) => updateMessaging('enable_typing_indicators', e.target.checked)}
                    disabled={!settings.messaging.enable_messaging}
                  />
                  <span>Enable Typing Indicators</span>
                </label>
              </div>

              {settings.messaging.enable_file_attachments && (
                <div className="form-group">
                  <label>Max Attachment Size (MB)</label>
                  <input
                    type="number"
                    value={settings.messaging.max_attachment_size_mb}
                    onChange={(e) => updateMessaging('max_attachment_size_mb', parseInt(e.target.value) || 10)}
                    min={1}
                    max={50}
                  />
                </div>
              )}
            </div>

            <div className="settings-group">
              <h3>Auto-Response</h3>
              <div className="form-grid">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.messaging.auto_response_enabled}
                    onChange={(e) => updateMessaging('auto_response_enabled', e.target.checked)}
                  />
                  <span>Enable Auto-Response</span>
                </label>

                {settings.messaging.auto_response_enabled && (
                  <>
                    <div className="form-group full-width">
                      <label>Auto-Response Message</label>
                      <textarea
                        value={settings.messaging.auto_response_message || ''}
                        onChange={(e) => updateMessaging('auto_response_message', e.target.value || null)}
                        placeholder="Thank you for your message. We'll respond as soon as possible."
                        rows={3}
                      />
                    </div>

                    <div className="form-group">
                      <label>Response Delay (seconds)</label>
                      <input
                        type="number"
                        value={settings.messaging.auto_response_delay_seconds}
                        onChange={(e) => updateMessaging('auto_response_delay_seconds', parseInt(e.target.value) || 0)}
                        min={0}
                        max={300}
                      />
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="settings-group">
              <h3>Business Hours</h3>
              <div className="form-grid">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.messaging.business_hours_only}
                    onChange={(e) => updateMessaging('business_hours_only', e.target.checked)}
                  />
                  <span>Limit Messaging to Business Hours</span>
                </label>

                {settings.messaging.business_hours_only && (
                  <>
                    <div className="form-group">
                      <label>Start Time</label>
                      <input
                        type="time"
                        value={settings.messaging.business_hours_start}
                        onChange={(e) => updateMessaging('business_hours_start', e.target.value)}
                      />
                    </div>

                    <div className="form-group">
                      <label>End Time</label>
                      <input
                        type="time"
                        value={settings.messaging.business_hours_end}
                        onChange={(e) => updateMessaging('business_hours_end', e.target.value)}
                      />
                    </div>

                    <div className="form-group">
                      <label>Timezone</label>
                      <select
                        value={settings.messaging.business_hours_timezone}
                        onChange={(e) => updateMessaging('business_hours_timezone', e.target.value)}
                      >
                        {timezones.map(tz => (
                          <option key={tz.value} value={tz.value}>{tz.label}</option>
                        ))}
                      </select>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Progress Tracking Tab */}
        {activeTab === 'progress' && (
          <div className="settings-section">
            <h2>Progress Tracking</h2>
            <p className="section-description">Configure how loan progress is displayed to borrowers</p>

            <div className="settings-group">
              <h3>Display Options</h3>
              <div className="toggle-list">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.progress_tracking.enable_progress_tracker}
                    onChange={(e) => updateProgressTracking('enable_progress_tracker', e.target.checked)}
                  />
                  <span>Enable Progress Tracker</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.progress_tracking.show_percentage_complete}
                    onChange={(e) => updateProgressTracking('show_percentage_complete', e.target.checked)}
                    disabled={!settings.progress_tracking.enable_progress_tracker}
                  />
                  <span>Show Percentage Complete</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.progress_tracking.show_estimated_completion}
                    onChange={(e) => updateProgressTracking('show_estimated_completion', e.target.checked)}
                    disabled={!settings.progress_tracking.enable_progress_tracker}
                  />
                  <span>Show Estimated Completion Date</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.progress_tracking.show_milestone_dates}
                    onChange={(e) => updateProgressTracking('show_milestone_dates', e.target.checked)}
                    disabled={!settings.progress_tracking.enable_progress_tracker}
                  />
                  <span>Show Milestone Dates</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.progress_tracking.show_next_steps}
                    onChange={(e) => updateProgressTracking('show_next_steps', e.target.checked)}
                    disabled={!settings.progress_tracking.enable_progress_tracker}
                  />
                  <span>Show Next Steps</span>
                </label>
              </div>
            </div>

            <div className="settings-group">
              <h3>Milestone Labels</h3>
              <div className="milestone-labels">
                {Object.entries(settings.progress_tracking.milestone_labels).map(([key, label]) => (
                  <div key={key} className="milestone-input">
                    <label>{key.replace('_', ' ').toUpperCase()}</label>
                    <input
                      type="text"
                      value={label}
                      onChange={(e) => {
                        const labels = { ...settings.progress_tracking.milestone_labels, [key]: e.target.value };
                        updateProgressTracking('milestone_labels', labels);
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Portal Pages Tab */}
        {activeTab === 'pages' && (
          <div className="settings-section">
            <h2>Portal Pages</h2>
            <p className="section-description">Configure which pages are available in the portal</p>

            <div className="pages-list">
              {settings.pages.map((page, index) => {
                const pageInfo = defaultPages.find(p => p.page_id === page.page_id);
                return (
                  <div key={page.page_id} className="page-item">
                    <div className="page-info">
                      <div className="page-header">
                        <label className="page-toggle">
                          <input
                            type="checkbox"
                            checked={page.enabled}
                            onChange={(e) => updatePage(page.page_id, 'enabled', e.target.checked)}
                            disabled={pageInfo?.required}
                          />
                          <span className="page-title">{page.title}</span>
                          {pageInfo?.required && <span className="required-badge">Required</span>}
                        </label>
                      </div>
                      {pageInfo && <p className="page-description">{pageInfo.description}</p>}
                    </div>

                    {page.enabled && (
                      <div className="page-settings">
                        <div className="form-group">
                          <label>Title</label>
                          <input
                            type="text"
                            value={page.title}
                            onChange={(e) => updatePage(page.page_id, 'title', e.target.value)}
                          />
                        </div>

                        <div className="form-group">
                          <label>Navigation Order</label>
                          <input
                            type="number"
                            value={page.navigation_order}
                            onChange={(e) => updatePage(page.page_id, 'navigation_order', parseInt(e.target.value) || 0)}
                            min={0}
                          />
                        </div>

                        <label className="toggle-inline">
                          <input
                            type="checkbox"
                            checked={page.show_in_navigation}
                            onChange={(e) => updatePage(page.page_id, 'show_in_navigation', e.target.checked)}
                          />
                          <span>Show in Navigation</span>
                        </label>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Global Settings Tab */}
        {activeTab === 'global' && (
          <div className="settings-section">
            <h2>Global Settings</h2>
            <p className="section-description">Configure portal-wide settings and maintenance options</p>

            <div className="settings-group">
              <h3>Portal Status</h3>
              <div className="toggle-list">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.portal_enabled}
                    onChange={(e) => updateGlobal('portal_enabled', e.target.checked)}
                  />
                  <span>Portal Enabled</span>
                </label>

                <label className="toggle-item warning">
                  <input
                    type="checkbox"
                    checked={settings.maintenance_mode}
                    onChange={(e) => updateGlobal('maintenance_mode', e.target.checked)}
                  />
                  <span>Maintenance Mode</span>
                </label>
              </div>

              {settings.maintenance_mode && (
                <div className="form-group">
                  <label>Maintenance Message</label>
                  <textarea
                    value={settings.maintenance_message || ''}
                    onChange={(e) => updateGlobal('maintenance_message', e.target.value || null)}
                    placeholder="The portal is currently under maintenance. Please check back later."
                    rows={3}
                  />
                </div>
              )}
            </div>

            <div className="settings-group">
              <h3>Welcome Message</h3>
              <div className="form-group">
                <label>Welcome Message (displayed on dashboard)</label>
                <textarea
                  value={settings.welcome_message || ''}
                  onChange={(e) => updateGlobal('welcome_message', e.target.value || null)}
                  placeholder="Welcome to your loan portal!"
                  rows={3}
                />
              </div>
            </div>

            <div className="settings-group">
              <h3>Support Contact</h3>
              <div className="form-grid">
                <div className="form-group">
                  <label>Support Email</label>
                  <input
                    type="email"
                    value={settings.support_email || ''}
                    onChange={(e) => updateGlobal('support_email', e.target.value || null)}
                    placeholder="support@example.com"
                  />
                </div>

                <div className="form-group">
                  <label>Support Phone</label>
                  <input
                    type="tel"
                    value={settings.support_phone || ''}
                    onChange={(e) => updateGlobal('support_phone', e.target.value || null)}
                    placeholder="(555) 123-4567"
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Sticky Save Bar */}
      {hasChanges && (
        <div className="save-bar">
          <span className="save-indicator">You have unsaved changes</span>
          <div className="save-actions">
            <button className="btn-cancel" onClick={handleReset} disabled={saving}>
              Discard
            </button>
            <button className="btn-save" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ClientPortalSettings;
