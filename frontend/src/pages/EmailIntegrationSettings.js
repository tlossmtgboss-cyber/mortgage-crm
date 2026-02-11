/**
 * Email Integration Settings Page
 * Comprehensive error handling pattern for email configuration
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAuthHeaders } from '../utils/auth';
import { useAsyncOperation, useFormSubmit, APIError } from '../utils/errorHandling';
import { toast } from '../utils/toast';
import { sanitizeHTML } from '../utils/sanitize';
import './EmailIntegrationSettings.css';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

// Tabs for the settings page
const TABS = [
  { id: 'identity', label: 'Identity', icon: 'fa-user-circle' },
  { id: 'behavior', label: 'Behavior', icon: 'fa-cogs' },
  { id: 'branding', label: 'Branding', icon: 'fa-paint-brush' },
  { id: 'microsoft', label: 'Microsoft 365', icon: 'fa-windows' },
];

const EmailIntegrationSettings = () => {
  const navigate = useNavigate();

  // Tab state
  const [activeTab, setActiveTab] = useState('identity');

  // Settings state
  const [settings, setSettings] = useState(null);
  const [originalSettings, setOriginalSettings] = useState(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // Status state
  const [emailStatus, setEmailStatus] = useState(null);
  const [dnsInstructions, setDnsInstructions] = useState(null);
  const [showDnsModal, setShowDnsModal] = useState(false);
  const [signaturePreview, setSignaturePreview] = useState(null);

  // Form validation
  const [fieldErrors, setFieldErrors] = useState({});
  const [warnings, setWarnings] = useState([]);

  // Test email
  const [testEmail, setTestEmail] = useState('');
  const [testResult, setTestResult] = useState(null);

  // Async operations - disable automatic toasts since we handle them manually
  const { loading, error, execute: fetchSettings } = useAsyncOperation({ showErrorToast: false });
  const { loading: saving, execute: saveSettings } = useFormSubmit({ showErrorToast: false, showSuccessToast: false });
  const { loading: testingEmail, execute: sendTestEmail } = useAsyncOperation({ showErrorToast: false });
  const { loading: verifyingDns, execute: verifyDns } = useAsyncOperation({ showErrorToast: false });

  // Fetch settings on mount
  useEffect(() => {
    loadSettings();
  }, []);

  // Track unsaved changes
  useEffect(() => {
    if (settings && originalSettings) {
      const changed = JSON.stringify(settings) !== JSON.stringify(originalSettings);
      setHasUnsavedChanges(changed);
    }
  }, [settings, originalSettings]);

  const loadSettings = async () => {
    try {
      const response = await fetchSettings(async () => {
        const res = await fetch(`${API_BASE}/api/v1/email-integration-settings`, {
          headers: getAuthHeaders()
        });
        if (!res.ok) {
          const err = await res.json();
          throw new APIError(err.message || 'Failed to load settings', res.status, err.field_errors);
        }
        return res.json();
      });

      if (response?.success && response.data) {
        const data = response.data;
        // Flatten the settings for easier form handling
        const flatSettings = {
          ...data.identity,
          ...data.behavior,
          quiet_hours_enabled: data.quiet_hours?.enabled || false,
          quiet_hours_start: data.quiet_hours?.start_time || '',
          quiet_hours_end: data.quiet_hours?.end_time || '',
          ...data.branding,
          microsoft_tenant_id: data.microsoft?.tenant_id || '',
          microsoft_mailbox_configured: data.microsoft?.mailbox_configured || false,
        };
        setSettings(flatSettings);
        setOriginalSettings(flatSettings);
        setWarnings(response.warnings || []);
      }

      // Also fetch email status
      loadEmailStatus();
    } catch (err) {
      console.error('Error loading settings:', err);
      toast.error('Failed to load email integration settings');
    }
  };

  const loadEmailStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/email-integration-settings/status`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setEmailStatus(data.data);
        }
      }
    } catch (err) {
      console.error('Error loading email status:', err);
    }
  };

  const handleSave = async () => {
    // Client-side validation
    const errors = validateSettings(settings);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    try {
      const response = await saveSettings(async () => {
        const res = await fetch(`${API_BASE}/api/v1/email-integration-settings`, {
          method: 'PUT',
          headers: getAuthHeaders(),
          body: JSON.stringify(settings)
        });

        const data = await res.json();
        if (!res.ok) {
          throw new APIError(data.message || 'Failed to save settings', res.status, data.field_errors);
        }
        return data;
      });

      if (response?.success) {
        setOriginalSettings({ ...settings });
        setHasUnsavedChanges(false);
        setFieldErrors({});
        setWarnings(response.warnings || []);
        loadEmailStatus(); // Refresh status after save
        toast.success('Email settings saved successfully');
      }
    } catch (err) {
      if (err.fieldErrors) {
        setFieldErrors(err.fieldErrors);
      }
      toast.error('Failed to save settings');
    }
  };

  const handleReset = () => {
    setSettings({ ...originalSettings });
    setFieldErrors({});
    setHasUnsavedChanges(false);
  };

  const validateSettings = (s) => {
    const errors = {};

    // Identity validation
    if (!s.assistant_name?.trim()) {
      errors.assistant_name = 'Assistant name is required';
    }
    if (!s.assistant_email?.trim()) {
      errors.assistant_email = 'Assistant email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.assistant_email)) {
      errors.assistant_email = 'Invalid email format';
    }
    if (!s.company_name?.trim()) {
      errors.company_name = 'Company name is required';
    }

    // Reply-to validation
    if (s.reply_to_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.reply_to_email)) {
      errors.reply_to_email = 'Invalid email format';
    }

    // Brand color validation
    if (s.brand_color && !/^#[0-9A-Fa-f]{6}$/.test(s.brand_color)) {
      errors.brand_color = 'Invalid hex color (e.g., #2563eb)';
    }

    // Logo URL validation
    if (s.logo_url && !s.logo_url.startsWith('http')) {
      errors.logo_url = 'Logo URL must start with http:// or https://';
    }

    // Quiet hours validation
    if (s.quiet_hours_enabled) {
      if (!s.quiet_hours_start) {
        errors.quiet_hours_start = 'Start time required when quiet hours enabled';
      }
      if (!s.quiet_hours_end) {
        errors.quiet_hours_end = 'End time required when quiet hours enabled';
      }
    }

    // Tenant ID validation
    if (s.microsoft_tenant_id && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s.microsoft_tenant_id)) {
      errors.microsoft_tenant_id = 'Invalid tenant ID format (UUID required)';
    }

    return errors;
  };

  const updateField = (field, value) => {
    setSettings(prev => ({ ...prev, [field]: value }));
    // Clear field error when user edits
    if (fieldErrors[field]) {
      setFieldErrors(prev => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  const handleSendTestEmail = async () => {
    if (!testEmail) {
      setTestResult({ success: false, message: 'Please enter an email address' });
      return;
    }

    try {
      const response = await sendTestEmail(async () => {
        const res = await fetch(`${API_BASE}/api/v1/email-integration-settings/test`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ to_email: testEmail, include_branding: true })
        });
        const data = await res.json();
        if (!res.ok) {
          throw new APIError(data.message || 'Failed to send test email', res.status);
        }
        return data;
      });

      if (response?.success) {
        setTestResult({ success: true, message: `Test email sent to ${testEmail}` });
        toast.success('Test email sent successfully');
      }
    } catch (err) {
      setTestResult({ success: false, message: err.message });
      toast.error('Failed to send test email');
    }
  };

  const handleVerifyDns = async () => {
    try {
      const response = await verifyDns(async () => {
        const res = await fetch(`${API_BASE}/api/v1/email-integration-settings/verify-dns`, {
          method: 'POST',
          headers: getAuthHeaders()
        });
        const data = await res.json();
        if (!res.ok) {
          throw new APIError(data.message || 'Failed to verify DNS', res.status);
        }
        return data;
      });

      if (response?.success) {
        setEmailStatus(prev => ({
          ...prev,
          ...response.data
        }));
        toast.success('DNS verification complete');
      }
    } catch (err) {
      console.error('DNS verification error:', err);
      toast.error('DNS verification failed');
    }
  };

  const loadDnsInstructions = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/email-integration-settings/dns-instructions`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setDnsInstructions(data.data);
          setShowDnsModal(true);
        }
      }
    } catch (err) {
      console.error('Error loading DNS instructions:', err);
    }
  };

  const loadSignaturePreview = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/email-integration-settings/preview-signature`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setSignaturePreview(data.data);
        }
      }
    } catch (err) {
      console.error('Error loading preview:', err);
    }
  };

  // Loading state
  if (loading && !settings) {
    return (
      <div className="email-settings-page">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading email settings...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !settings) {
    return (
      <div className="email-settings-page">
        <div className="error-state">
          <i className="fas fa-exclamation-circle"></i>
          <h2>Failed to Load Settings</h2>
          <p>{error}</p>
          <button className="btn-primary" onClick={loadSettings}>
            <i className="fas fa-redo"></i> Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="email-settings-page">
      {/* Header */}
      <div className="settings-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/settings')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div>
            <h1>Email Integration Settings</h1>
            <p className="subtitle">Configure your AI assistant's email identity and behavior</p>
          </div>
        </div>
        <div className="header-actions">
          <button
            className="btn-secondary"
            onClick={handleVerifyDns}
            disabled={verifyingDns}
          >
            {verifyingDns ? <><i className="fas fa-spinner fa-spin"></i> Verifying...</> : <><i className="fas fa-check-circle"></i> Verify DNS</>}
          </button>
          <button className="btn-secondary" onClick={loadDnsInstructions}>
            <i className="fas fa-info-circle"></i> DNS Instructions
          </button>
        </div>
      </div>

      {/* Warnings Banner */}
      {warnings.length > 0 && (
        <div className="warnings-banner">
          <i className="fas fa-exclamation-triangle"></i>
          <div>
            <strong>Configuration Warnings</strong>
            <ul>
              {warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          </div>
        </div>
      )}

      {/* Email Status Overview */}
      {emailStatus && (
        <div className="status-overview">
          <h3>Email Setup Status</h3>
          <div className="status-grid">
            <div className={`status-item ${emailStatus.mx_configured ? 'success' : 'error'}`}>
              <span className="status-icon">{emailStatus.mx_configured ? '✓' : '✗'}</span>
              <span className="status-label">MX Records</span>
            </div>
            <div className={`status-item ${emailStatus.spf_configured ? 'success' : 'warning'}`}>
              <span className="status-icon">{emailStatus.spf_configured ? '✓' : '!'}</span>
              <span className="status-label">SPF Record</span>
            </div>
            <div className={`status-item ${emailStatus.dkim_configured ? 'success' : 'neutral'}`}>
              <span className="status-icon">{emailStatus.dkim_configured ? '✓' : '○'}</span>
              <span className="status-label">DKIM</span>
            </div>
            <div className={`status-item ${emailStatus.mailbox_exists ? 'success' : 'error'}`}>
              <span className="status-icon">{emailStatus.mailbox_exists ? '✓' : '✗'}</span>
              <span className="status-label">Mailbox</span>
            </div>
            <div className={`status-item ${emailStatus.ready_to_receive ? 'success' : 'warning'}`}>
              <span className="status-icon">{emailStatus.ready_to_receive ? '✓' : '!'}</span>
              <span className="status-label">Ready to Receive</span>
            </div>
          </div>
          {emailStatus.issues?.length > 0 && (
            <div className="status-issues">
              <strong>Issues:</strong>
              <ul>
                {emailStatus.issues.map((issue, i) => <li key={i}>{issue}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Test Result */}
      {testResult && (
        <div className={`test-result ${testResult.success ? 'success' : 'warning'}`}>
          <div className="test-header">
            <i className={`fas ${testResult.success ? 'fa-check-circle' : 'fa-exclamation-circle'}`}></i>
            <strong>{testResult.success ? 'Test Email Sent' : 'Test Failed'}</strong>
          </div>
          <p>{testResult.message}</p>
        </div>
      )}

      {/* Tabs */}
      <div className="settings-tabs">
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <i className={`fas ${tab.icon}`}></i>
            {tab.label}
          </button>
        ))}
      </div>

      {settings && (
        <div className="settings-content">
          {/* Identity Tab */}
          {activeTab === 'identity' && (
            <div className="settings-section">
              <h2>AI Assistant Identity</h2>
              <p className="section-description">Configure how your AI assistant appears in emails</p>

              <div className="form-row two-col">
                <div className="form-group">
                  <label>Assistant Name *</label>
                  <input
                    type="text"
                    value={settings.assistant_name || ''}
                    onChange={(e) => updateField('assistant_name', e.target.value)}
                    className={fieldErrors.assistant_name ? 'has-error' : ''}
                    placeholder="Sarah"
                  />
                  {fieldErrors.assistant_name && <span className="field-error">{fieldErrors.assistant_name}</span>}
                  <span className="field-hint">The name your AI assistant will use</span>
                </div>
                <div className="form-group">
                  <label>Assistant Email *</label>
                  <input
                    type="email"
                    value={settings.assistant_email || ''}
                    onChange={(e) => updateField('assistant_email', e.target.value)}
                    className={fieldErrors.assistant_email ? 'has-error' : ''}
                    placeholder="sarah@perenniaai.com"
                  />
                  {fieldErrors.assistant_email && <span className="field-error">{fieldErrors.assistant_email}</span>}
                  <span className="field-hint">Email address for sending and receiving</span>
                </div>
              </div>

              <div className="form-row two-col">
                <div className="form-group">
                  <label>Assistant Title</label>
                  <input
                    type="text"
                    value={settings.assistant_title || ''}
                    onChange={(e) => updateField('assistant_title', e.target.value)}
                    placeholder="AI Assistant"
                  />
                </div>
                <div className="form-group">
                  <label>Company Name *</label>
                  <input
                    type="text"
                    value={settings.company_name || ''}
                    onChange={(e) => updateField('company_name', e.target.value)}
                    className={fieldErrors.company_name ? 'has-error' : ''}
                    placeholder="Perennia AI"
                  />
                  {fieldErrors.company_name && <span className="field-error">{fieldErrors.company_name}</span>}
                </div>
              </div>

              <div className="form-group">
                <label>Display Name (From Name)</label>
                <input
                  type="text"
                  value={settings.from_name || ''}
                  onChange={(e) => updateField('from_name', e.target.value)}
                  placeholder="Sarah from Perennia AI"
                />
                <span className="field-hint">How the sender name appears in emails (auto-generated if left blank)</span>
              </div>
            </div>
          )}

          {/* Behavior Tab */}
          {activeTab === 'behavior' && (
            <div className="settings-section">
              <h2>Email Behavior</h2>
              <p className="section-description">Control how your AI responds to emails</p>

              <div className="form-row checkbox-row">
                <label>
                  <input
                    type="checkbox"
                    checked={settings.auto_respond || false}
                    onChange={(e) => updateField('auto_respond', e.target.checked)}
                  />
                  <span>Auto-respond to incoming emails</span>
                </label>
                <span className="checkbox-hint">AI will automatically respond to new emails when enabled</span>
              </div>

              <div className="form-row checkbox-row">
                <label>
                  <input
                    type="checkbox"
                    checked={settings.include_calendar_links || false}
                    onChange={(e) => updateField('include_calendar_links', e.target.checked)}
                  />
                  <span>Include calendar scheduling links</span>
                </label>
                <span className="checkbox-hint">Add scheduling links when appropriate in responses</span>
              </div>

              <div className="form-row two-col">
                <div className="form-group">
                  <label>Response Delay (seconds)</label>
                  <input
                    type="number"
                    value={settings.response_delay_seconds || 0}
                    onChange={(e) => updateField('response_delay_seconds', parseInt(e.target.value) || 0)}
                    min="0"
                    max="300"
                  />
                  <span className="field-hint">Delay before sending (0-300 seconds)</span>
                </div>
                <div className="form-group">
                  <label>Max Auto-Responses Per Day</label>
                  <input
                    type="number"
                    value={settings.max_auto_responses_per_day || 100}
                    onChange={(e) => updateField('max_auto_responses_per_day', parseInt(e.target.value) || 100)}
                    min="1"
                    max="1000"
                  />
                  <span className="field-hint">Safety limit for auto-responses</span>
                </div>
              </div>

              <div className="form-group">
                <label>Reply-To Email (optional)</label>
                <input
                  type="email"
                  value={settings.reply_to_email || ''}
                  onChange={(e) => updateField('reply_to_email', e.target.value)}
                  className={fieldErrors.reply_to_email ? 'has-error' : ''}
                  placeholder="Leave blank to use assistant email"
                />
                {fieldErrors.reply_to_email && <span className="field-error">{fieldErrors.reply_to_email}</span>}
                <span className="field-hint">Override where replies are sent</span>
              </div>

              {/* Quiet Hours */}
              <div className="subsection">
                <h3>Quiet Hours</h3>
                <div className="form-row checkbox-row">
                  <label>
                    <input
                      type="checkbox"
                      checked={settings.quiet_hours_enabled || false}
                      onChange={(e) => updateField('quiet_hours_enabled', e.target.checked)}
                    />
                    <span>Enable quiet hours (no auto-responses)</span>
                  </label>
                </div>

                {settings.quiet_hours_enabled && (
                  <div className="form-row two-col">
                    <div className="form-group">
                      <label>Start Time</label>
                      <input
                        type="time"
                        value={settings.quiet_hours_start || ''}
                        onChange={(e) => updateField('quiet_hours_start', e.target.value)}
                        className={fieldErrors.quiet_hours_start ? 'has-error' : ''}
                      />
                      {fieldErrors.quiet_hours_start && <span className="field-error">{fieldErrors.quiet_hours_start}</span>}
                    </div>
                    <div className="form-group">
                      <label>End Time</label>
                      <input
                        type="time"
                        value={settings.quiet_hours_end || ''}
                        onChange={(e) => updateField('quiet_hours_end', e.target.value)}
                        className={fieldErrors.quiet_hours_end ? 'has-error' : ''}
                      />
                      {fieldErrors.quiet_hours_end && <span className="field-error">{fieldErrors.quiet_hours_end}</span>}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Branding Tab */}
          {activeTab === 'branding' && (
            <div className="settings-section">
              <h2>Email Branding</h2>
              <p className="section-description">Customize the look of your emails</p>

              <div className="form-row two-col">
                <div className="form-group">
                  <label>Brand Color</label>
                  <div className="color-input-wrapper">
                    <input
                      type="color"
                      value={settings.brand_color || '#2563eb'}
                      onChange={(e) => updateField('brand_color', e.target.value)}
                    />
                    <input
                      type="text"
                      value={settings.brand_color || '#2563eb'}
                      onChange={(e) => updateField('brand_color', e.target.value)}
                      className={fieldErrors.brand_color ? 'has-error' : ''}
                      placeholder="#2563eb"
                    />
                  </div>
                  {fieldErrors.brand_color && <span className="field-error">{fieldErrors.brand_color}</span>}
                </div>
                <div className="form-group">
                  <label>Logo URL</label>
                  <input
                    type="url"
                    value={settings.logo_url || ''}
                    onChange={(e) => updateField('logo_url', e.target.value)}
                    className={fieldErrors.logo_url ? 'has-error' : ''}
                    placeholder="https://..."
                  />
                  {fieldErrors.logo_url && <span className="field-error">{fieldErrors.logo_url}</span>}
                </div>
              </div>

              <div className="form-group">
                <label>Email Signature</label>
                <textarea
                  value={settings.email_signature || ''}
                  onChange={(e) => updateField('email_signature', e.target.value)}
                  placeholder="Custom signature to append to emails..."
                  rows={4}
                />
                <span className="field-hint">HTML or plain text signature</span>
              </div>

              <button className="btn-secondary" onClick={loadSignaturePreview}>
                <i className="fas fa-eye"></i> Preview Signature
              </button>

              {signaturePreview && (
                <div className="signature-preview">
                  <h4>Preview</h4>
                  <div dangerouslySetInnerHTML={{ __html: sanitizeHTML(signaturePreview.preview_html, { allowedTags: ['p', 'br', 'b', 'i', 'strong', 'em', 'a', 'img', 'div', 'span', 'table', 'tr', 'td', 'th', 'tbody', 'thead', 'hr', 'font', 'ul', 'ol', 'li'] }) }} />
                </div>
              )}
            </div>
          )}

          {/* Microsoft 365 Tab */}
          {activeTab === 'microsoft' && (
            <div className="settings-section">
              <h2>Microsoft 365 Integration</h2>
              <p className="section-description">Connect your Microsoft 365 account for email receiving</p>

              <div className="form-group">
                <label>Microsoft Tenant ID</label>
                <input
                  type="text"
                  value={settings.microsoft_tenant_id || ''}
                  onChange={(e) => updateField('microsoft_tenant_id', e.target.value)}
                  className={fieldErrors.microsoft_tenant_id ? 'has-error' : ''}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                />
                {fieldErrors.microsoft_tenant_id && <span className="field-error">{fieldErrors.microsoft_tenant_id}</span>}
                <span className="field-hint">Find this in Azure Portal &gt; Azure Active Directory</span>
              </div>

              <div className="form-row checkbox-row">
                <label>
                  <input
                    type="checkbox"
                    checked={settings.microsoft_mailbox_configured || false}
                    onChange={(e) => updateField('microsoft_mailbox_configured', e.target.checked)}
                  />
                  <span>I have created the mailbox in Microsoft 365</span>
                </label>
                <span className="checkbox-hint">
                  Check this after creating {settings.assistant_email || 'the assistant email'} in Microsoft 365 Admin Center
                </span>
              </div>

              <div className="info-card">
                <i className="fas fa-info-circle"></i>
                <div>
                  <strong>Setup Steps</strong>
                  <ol>
                    <li>Create a shared mailbox for {settings.assistant_email || 'your assistant'} in Microsoft 365 Admin Center</li>
                    <li>Configure DNS records for your domain (click DNS Instructions above)</li>
                    <li>Enter your Tenant ID and confirm mailbox creation</li>
                    <li>Click Verify DNS to check configuration</li>
                  </ol>
                </div>
              </div>
            </div>
          )}

          {/* Test Email Section */}
          <div className="settings-section test-section">
            <h2>Send Test Email</h2>
            <p className="section-description">Verify your configuration is working correctly</p>
            <div className="test-email-form">
              <input
                type="email"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                placeholder="Enter email address to send test to"
              />
              <button
                className="btn-primary"
                onClick={handleSendTestEmail}
                disabled={testingEmail || !testEmail}
              >
                {testingEmail ? <><i className="fas fa-spinner fa-spin"></i> Sending...</> : <><i className="fas fa-paper-plane"></i> Send Test</>}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Sticky Save Bar */}
      {hasUnsavedChanges && (
        <div className="sticky-save-bar">
          <div className="save-bar-content">
            <span>You have unsaved changes</span>
            <div className="save-bar-actions">
              <button className="btn-secondary" onClick={handleReset} disabled={saving}>
                Discard
              </button>
              <button className="btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? <><i className="fas fa-spinner fa-spin"></i> Saving...</> : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* DNS Instructions Modal */}
      {showDnsModal && dnsInstructions && (
        <div className="modal-overlay" onClick={() => setShowDnsModal(false)}>
          <div className="dns-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>DNS Setup Instructions for {dnsInstructions.domain}</h3>
              <button className="close-btn" onClick={() => setShowDnsModal(false)}>
                <i className="fas fa-times"></i>
              </button>
            </div>
            <div className="modal-content">
              <div className="dns-records">
                <h4>Required DNS Records</h4>
                <table>
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Host</th>
                      <th>Value</th>
                      <th>Priority</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>MX</td>
                      <td>{dnsInstructions.records?.mx?.host}</td>
                      <td className="value-cell">{dnsInstructions.records?.mx?.value}</td>
                      <td>{dnsInstructions.records?.mx?.priority}</td>
                    </tr>
                    <tr>
                      <td>TXT</td>
                      <td>{dnsInstructions.records?.spf?.host}</td>
                      <td className="value-cell">{dnsInstructions.records?.spf?.value}</td>
                      <td>-</td>
                    </tr>
                    <tr>
                      <td>CNAME</td>
                      <td>{dnsInstructions.records?.autodiscover?.host}</td>
                      <td className="value-cell">{dnsInstructions.records?.autodiscover?.value}</td>
                      <td>-</td>
                    </tr>
                    <tr>
                      <td>CNAME</td>
                      <td>{dnsInstructions.records?.dkim?.host}</td>
                      <td className="value-cell">{dnsInstructions.records?.dkim?.value}</td>
                      <td>-</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="setup-steps">
                <h4>Setup Steps</h4>
                <ol>
                  {dnsInstructions.steps?.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default EmailIntegrationSettings;
