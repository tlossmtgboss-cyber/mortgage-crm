import React, { useState, useEffect } from 'react';
import { useAsyncOperation, useFormSubmit, APIError } from '../utils/errorHandling';
import { toast } from '../utils/toast';
import './CommunicationPreferences.css';
import { getToken } from '../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const CommunicationPreferences = () => {
  const [activeTab, setActiveTab] = useState('email');
  const [settings, setSettings] = useState(null);
  const [originalSettings, setOriginalSettings] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [templateVariables, setTemplateVariables] = useState({});
  const [eventTypes, setEventTypes] = useState([]);
  const [triggerEvents, setTriggerEvents] = useState([]);
  const [statistics, setStatistics] = useState(null);
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [testRecipient, setTestRecipient] = useState('');
  const [previewData, setPreviewData] = useState(null);

  // Hooks handle toast notifications automatically
  const { execute: fetchSettings, loading, error } = useAsyncOperation();
  const { execute: saveSettings, loading: saving } = useFormSubmit();

  useEffect(() => {
    loadSettings();
    loadTemplateVariables();
    loadEventTypes();
    loadTriggerEvents();
    loadStatistics();
  }, []);

  useEffect(() => {
    if (settings && originalSettings) {
      setHasChanges(JSON.stringify(settings) !== JSON.stringify(originalSettings));
    }
  }, [settings, originalSettings]);

  const loadSettings = async () => {
    try {
      const token = getToken();
      const response = await fetchSettings(async () => {
        const res = await fetch(`${API_URL}/api/v1/communication-preferences`, {
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

  const loadTemplateVariables = async () => {
    try {
      const token = getToken();
      const res = await fetch(`${API_URL}/api/v1/communication-preferences/template-variables`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setTemplateVariables(data.data || {});
      }
    } catch (err) {
      console.error('Failed to load template variables:', err);
    }
  };

  const loadEventTypes = async () => {
    try {
      const token = getToken();
      const res = await fetch(`${API_URL}/api/v1/communication-preferences/event-types`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setEventTypes(data.data || []);
      }
    } catch (err) {
      console.error('Failed to load event types:', err);
    }
  };

  const loadTriggerEvents = async () => {
    try {
      const token = getToken();
      const res = await fetch(`${API_URL}/api/v1/communication-preferences/trigger-events`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setTriggerEvents(data.data || []);
      }
    } catch (err) {
      console.error('Failed to load trigger events:', err);
    }
  };

  const loadStatistics = async () => {
    try {
      const token = getToken();
      const res = await fetch(`${API_URL}/api/v1/communication-preferences/statistics`, {
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
        const res = await fetch(`${API_URL}/api/v1/communication-preferences`, {
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

  const updateEmailSettings = (field, value) => {
    setSettings(prev => ({
      ...prev,
      email_settings: { ...prev.email_settings, [field]: value }
    }));
  };

  const updateSMSSettings = (field, value) => {
    setSettings(prev => ({
      ...prev,
      sms_settings: { ...prev.sms_settings, [field]: value }
    }));
  };

  const updateQuietHours = (field, value) => {
    setSettings(prev => ({
      ...prev,
      quiet_hours: { ...prev.quiet_hours, [field]: value }
    }));
  };

  const updateEmailTemplate = (id, field, value) => {
    setSettings(prev => ({
      ...prev,
      email_templates: prev.email_templates.map(t =>
        t.id === id ? { ...t, [field]: value } : t
      )
    }));
  };

  const updateSMSTemplate = (id, field, value) => {
    setSettings(prev => ({
      ...prev,
      sms_templates: prev.sms_templates.map(t =>
        t.id === id ? { ...t, [field]: value } : t
      )
    }));
  };

  const updateNotificationPref = (eventType, field, value) => {
    setSettings(prev => ({
      ...prev,
      notification_preferences: prev.notification_preferences.map(p =>
        p.event_type === eventType ? { ...p, [field]: value } : p
      )
    }));
  };

  const updateOutreachRule = (id, field, value) => {
    setSettings(prev => ({
      ...prev,
      outreach_rules: prev.outreach_rules.map(r =>
        r.id === id ? { ...r, [field]: value } : r
      )
    }));
  };

  const updateGlobal = (field, value) => {
    setSettings(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const previewTemplate = async (type, id) => {
    try {
      const token = getToken();
      const res = await fetch(`${API_URL}/api/v1/communication-preferences/preview-template?template_type=${type}&template_id=${id}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
      });

      if (res.ok) {
        const data = await res.json();
        setPreviewData(data.data);
      }
    } catch (err) {
      console.error('Failed to preview template:', err);
    }
  };

  const sendTest = async (channel, templateId) => {
    if (!testRecipient) {
      toast.error('Please enter a recipient');
      return;
    }

    try {
      const token = getToken();
      const res = await fetch(`${API_URL}/api/v1/communication-preferences/test-send?channel=${channel}&template_id=${templateId}&recipient=${encodeURIComponent(testRecipient)}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        toast.success(`Test ${channel} sent successfully`);
        setTestRecipient('');
      } else {
        const error = await res.json();
        toast.error(error.detail?.message || 'Failed to send test');
      }
    } catch (err) {
      toast.error('Failed to send test');
    }
  };

  if (loading) {
    return (
      <div className="communication-preferences">
        <div className="loading-state">Loading communication preferences...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="communication-preferences">
        <div className="error-state">
          <h3>Error Loading Preferences</h3>
          <p>{error.message}</p>
          <button onClick={loadSettings} className="btn-retry">Retry</button>
        </div>
      </div>
    );
  }

  if (!settings) return null;

  const tabs = [
    { id: 'email', label: 'Email Settings' },
    { id: 'sms', label: 'SMS Settings' },
    { id: 'templates', label: 'Templates' },
    { id: 'notifications', label: 'Notifications' },
    { id: 'outreach', label: 'Outreach Rules' },
    { id: 'global', label: 'Global Settings' }
  ];

  return (
    <div className="communication-preferences">
      <div className="page-header">
        <div className="header-content">
          <h1>Communication Preferences</h1>
          <p>Configure email templates, SMS messages, and automated outreach</p>
        </div>
        {statistics && (
          <div className="stats-summary">
            <div className="stat-item">
              <span className="stat-value">{statistics.email.open_rate}%</span>
              <span className="stat-label">Email Open Rate</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{statistics.sms.delivery_rate}%</span>
              <span className="stat-label">SMS Delivery</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{statistics.email.sent + statistics.sms.sent}</span>
              <span className="stat-label">Total Sent (30d)</span>
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
        {/* Email Settings Tab */}
        {activeTab === 'email' && (
          <div className="settings-section">
            <h2>Email Settings</h2>
            <p className="section-description">Configure email sending defaults and limits</p>

            <div className="settings-group">
              <h3>Sender Information</h3>
              <div className="form-grid">
                <div className="form-group">
                  <label>Default From Name</label>
                  <input
                    type="text"
                    value={settings.email_settings.default_from_name}
                    onChange={(e) => updateEmailSettings('default_from_name', e.target.value)}
                    maxLength={100}
                  />
                </div>

                <div className="form-group">
                  <label>Default From Email</label>
                  <input
                    type="email"
                    value={settings.email_settings.default_from_email}
                    onChange={(e) => updateEmailSettings('default_from_email', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label>Reply-To Email (optional)</label>
                  <input
                    type="email"
                    value={settings.email_settings.default_reply_to || ''}
                    onChange={(e) => updateEmailSettings('default_reply_to', e.target.value || null)}
                  />
                </div>
              </div>
            </div>

            <div className="settings-group">
              <h3>Email Footer</h3>
              <div className="toggle-list">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.email_settings.include_unsubscribe_link}
                    onChange={(e) => updateEmailSettings('include_unsubscribe_link', e.target.checked)}
                  />
                  <span>Include Unsubscribe Link</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.email_settings.include_company_footer}
                    onChange={(e) => updateEmailSettings('include_company_footer', e.target.checked)}
                  />
                  <span>Include Company Footer</span>
                </label>
              </div>

              {settings.email_settings.include_company_footer && (
                <div className="form-group">
                  <label>Company Footer HTML</label>
                  <textarea
                    value={settings.email_settings.company_footer_html || ''}
                    onChange={(e) => updateEmailSettings('company_footer_html', e.target.value || null)}
                    rows={4}
                    placeholder="<p>Company Name | Address | Phone</p>"
                  />
                </div>
              )}
            </div>

            <div className="settings-group">
              <h3>Tracking</h3>
              <div className="toggle-list">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.email_settings.track_opens}
                    onChange={(e) => updateEmailSettings('track_opens', e.target.checked)}
                  />
                  <span>Track Email Opens</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.email_settings.track_clicks}
                    onChange={(e) => updateEmailSettings('track_clicks', e.target.checked)}
                  />
                  <span>Track Link Clicks</span>
                </label>
              </div>
            </div>

            <div className="settings-group">
              <h3>Rate Limits</h3>
              <div className="form-grid">
                <div className="form-group">
                  <label>Hourly Send Limit</label>
                  <input
                    type="number"
                    value={settings.email_settings.send_limit_hourly}
                    onChange={(e) => updateEmailSettings('send_limit_hourly', parseInt(e.target.value) || 100)}
                    min={1}
                    max={10000}
                  />
                </div>

                <div className="form-group">
                  <label>Daily Send Limit</label>
                  <input
                    type="number"
                    value={settings.email_settings.send_limit_daily}
                    onChange={(e) => updateEmailSettings('send_limit_daily', parseInt(e.target.value) || 1000)}
                    min={1}
                    max={100000}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SMS Settings Tab */}
        {activeTab === 'sms' && (
          <div className="settings-section">
            <h2>SMS Settings</h2>
            <p className="section-description">Configure SMS sending defaults and compliance</p>

            <div className="settings-group">
              <h3>Sender Information</h3>
              <div className="form-group">
                <label>Default From Number</label>
                <input
                  type="tel"
                  value={settings.sms_settings.default_from_number || ''}
                  onChange={(e) => updateSMSSettings('default_from_number', e.target.value || null)}
                  placeholder="+1 (555) 123-4567"
                />
              </div>
            </div>

            <div className="settings-group">
              <h3>Compliance</h3>
              <label className="toggle-item">
                <input
                  type="checkbox"
                  checked={settings.sms_settings.include_opt_out_text}
                  onChange={(e) => updateSMSSettings('include_opt_out_text', e.target.checked)}
                />
                <span>Include Opt-Out Instructions</span>
              </label>

              <div className="form-group">
                <label>Opt-Out Keywords</label>
                <input
                  type="text"
                  value={settings.sms_settings.opt_out_keywords.join(', ')}
                  onChange={(e) => updateSMSSettings('opt_out_keywords', e.target.value.split(',').map(k => k.trim()).filter(k => k))}
                  placeholder="STOP, UNSUBSCRIBE, CANCEL"
                />
                <span className="field-hint">Comma-separated keywords</span>
              </div>
            </div>

            <div className="settings-group">
              <h3>Message Settings</h3>
              <div className="form-grid">
                <div className="form-group">
                  <label>Character Limit Warning</label>
                  <input
                    type="number"
                    value={settings.sms_settings.character_limit_warning}
                    onChange={(e) => updateSMSSettings('character_limit_warning', parseInt(e.target.value) || 140)}
                    min={100}
                    max={160}
                  />
                </div>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.sms_settings.enable_mms}
                    onChange={(e) => updateSMSSettings('enable_mms', e.target.checked)}
                  />
                  <span>Enable MMS (Picture Messages)</span>
                </label>
              </div>
            </div>

            <div className="settings-group">
              <h3>Rate Limits</h3>
              <div className="form-grid">
                <div className="form-group">
                  <label>Hourly Send Limit</label>
                  <input
                    type="number"
                    value={settings.sms_settings.send_limit_hourly}
                    onChange={(e) => updateSMSSettings('send_limit_hourly', parseInt(e.target.value) || 50)}
                    min={1}
                    max={1000}
                  />
                </div>

                <div className="form-group">
                  <label>Daily Send Limit</label>
                  <input
                    type="number"
                    value={settings.sms_settings.send_limit_daily}
                    onChange={(e) => updateSMSSettings('send_limit_daily', parseInt(e.target.value) || 500)}
                    min={1}
                    max={10000}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Templates Tab */}
        {activeTab === 'templates' && (
          <div className="settings-section">
            <h2>Message Templates</h2>
            <p className="section-description">Create and manage email and SMS templates</p>

            <div className="templates-tabs">
              <button
                className={`template-tab ${!editingTemplate || editingTemplate.type === 'email' ? 'active' : ''}`}
                onClick={() => setEditingTemplate(null)}
              >
                Email Templates ({settings.email_templates.length})
              </button>
              <button
                className={`template-tab ${editingTemplate?.type === 'sms' ? 'active' : ''}`}
                onClick={() => setEditingTemplate(null)}
              >
                SMS Templates ({settings.sms_templates.length})
              </button>
            </div>

            <div className="templates-list">
              <h3>Email Templates</h3>
              {settings.email_templates.map(template => (
                <div key={template.id} className="template-item">
                  <div className="template-header">
                    <div className="template-info">
                      <span className="template-name">{template.name}</span>
                      <span className={`template-category ${template.category}`}>{template.category}</span>
                    </div>
                    <div className="template-actions">
                      <label className="toggle-inline">
                        <input
                          type="checkbox"
                          checked={template.is_active}
                          onChange={(e) => updateEmailTemplate(template.id, 'is_active', e.target.checked)}
                        />
                        <span>Active</span>
                      </label>
                      <button
                        className="btn-sm"
                        onClick={() => previewTemplate('email', template.id)}
                      >
                        Preview
                      </button>
                    </div>
                  </div>

                  <div className="template-details">
                    <div className="form-group">
                      <label>Subject</label>
                      <input
                        type="text"
                        value={template.subject}
                        onChange={(e) => updateEmailTemplate(template.id, 'subject', e.target.value)}
                      />
                    </div>

                    <div className="form-group">
                      <label>Body (HTML)</label>
                      <textarea
                        value={template.body_html}
                        onChange={(e) => updateEmailTemplate(template.id, 'body_html', e.target.value)}
                        rows={6}
                      />
                    </div>

                    <div className="template-variables">
                      <label>Available Variables:</label>
                      <div className="variables-list">
                        {template.variables.map(v => (
                          <span key={v} className="variable-tag">{`{{${v}}}`}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ))}

              <h3 style={{ marginTop: '32px' }}>SMS Templates</h3>
              {settings.sms_templates.map(template => (
                <div key={template.id} className="template-item">
                  <div className="template-header">
                    <div className="template-info">
                      <span className="template-name">{template.name}</span>
                      <span className={`template-category ${template.category}`}>{template.category}</span>
                    </div>
                    <div className="template-actions">
                      <label className="toggle-inline">
                        <input
                          type="checkbox"
                          checked={template.is_active}
                          onChange={(e) => updateSMSTemplate(template.id, 'is_active', e.target.checked)}
                        />
                        <span>Active</span>
                      </label>
                    </div>
                  </div>

                  <div className="template-details">
                    <div className="form-group">
                      <label>Message ({template.message.length}/160 characters)</label>
                      <textarea
                        value={template.message}
                        onChange={(e) => updateSMSTemplate(template.id, 'message', e.target.value)}
                        rows={3}
                        maxLength={160}
                        className={template.message.length > 140 ? 'warning' : ''}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Template Variables Reference */}
            <div className="variables-reference">
              <h3>Template Variables Reference</h3>
              <div className="variables-grid">
                {Object.entries(templateVariables).map(([category, vars]) => (
                  <div key={category} className="variable-category">
                    <h4>{category.replace('_', ' ')}</h4>
                    <ul>
                      {vars.map(v => (
                        <li key={v.name}>
                          <code>{`{{${v.name}}}`}</code>
                          <span>{v.description}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>

            {/* Preview Modal */}
            {previewData && (
              <div className="preview-modal" onClick={() => setPreviewData(null)}>
                <div className="preview-content" onClick={e => e.stopPropagation()}>
                  <h3>Template Preview</h3>
                  {previewData.rendered_subject && (
                    <div className="preview-subject">
                      <label>Subject:</label>
                      <p>{previewData.rendered_subject}</p>
                    </div>
                  )}
                  <div className="preview-body">
                    <label>Body:</label>
                    <p>{previewData.rendered_body}</p>
                  </div>
                  <button className="btn-close" onClick={() => setPreviewData(null)}>Close</button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Notifications Tab */}
        {activeTab === 'notifications' && (
          <div className="settings-section">
            <h2>Notification Preferences</h2>
            <p className="section-description">Configure how and when to send notifications</p>

            <div className="settings-group">
              <h3>Quiet Hours</h3>
              <label className="toggle-item">
                <input
                  type="checkbox"
                  checked={settings.quiet_hours.enabled}
                  onChange={(e) => updateQuietHours('enabled', e.target.checked)}
                />
                <span>Enable Quiet Hours</span>
              </label>

              {settings.quiet_hours.enabled && (
                <div className="form-grid quiet-hours-config">
                  <div className="form-group">
                    <label>Start Time</label>
                    <input
                      type="time"
                      value={settings.quiet_hours.start_time}
                      onChange={(e) => updateQuietHours('start_time', e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label>End Time</label>
                    <input
                      type="time"
                      value={settings.quiet_hours.end_time}
                      onChange={(e) => updateQuietHours('end_time', e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label>Timezone</label>
                    <select
                      value={settings.quiet_hours.timezone}
                      onChange={(e) => updateQuietHours('timezone', e.target.value)}
                    >
                      <option value="America/New_York">Eastern Time</option>
                      <option value="America/Chicago">Central Time</option>
                      <option value="America/Denver">Mountain Time</option>
                      <option value="America/Los_Angeles">Pacific Time</option>
                    </select>
                  </div>
                </div>
              )}
            </div>

            <div className="settings-group">
              <h3>Event Notifications</h3>
              <div className="notification-list">
                {settings.notification_preferences.map(pref => {
                  const eventInfo = eventTypes.find(e => e.id === pref.event_type);
                  return (
                    <div key={pref.event_type} className="notification-item">
                      <div className="notification-header">
                        <label className="toggle-item">
                          <input
                            type="checkbox"
                            checked={pref.enabled}
                            onChange={(e) => updateNotificationPref(pref.event_type, 'enabled', e.target.checked)}
                          />
                          <span>{eventInfo?.name || pref.event_type}</span>
                        </label>
                      </div>

                      {pref.enabled && (
                        <div className="notification-config">
                          <div className="channels-config">
                            <label>Channels:</label>
                            <div className="channel-toggles">
                              {['email', 'sms', 'push'].map(channel => (
                                <label key={channel} className="channel-toggle">
                                  <input
                                    type="checkbox"
                                    checked={pref.channels.some(c => c.channel === channel && c.enabled)}
                                    onChange={(e) => {
                                      const channels = e.target.checked
                                        ? [...pref.channels, { channel, enabled: true, priority: pref.channels.length + 1 }]
                                        : pref.channels.filter(c => c.channel !== channel);
                                      updateNotificationPref(pref.event_type, 'channels', channels);
                                    }}
                                  />
                                  <span>{channel}</span>
                                </label>
                              ))}
                            </div>
                          </div>

                          <div className="notification-options">
                            <label className="toggle-inline">
                              <input
                                type="checkbox"
                                checked={pref.quiet_hours_enabled}
                                onChange={(e) => updateNotificationPref(pref.event_type, 'quiet_hours_enabled', e.target.checked)}
                              />
                              <span>Respect Quiet Hours</span>
                            </label>

                            <label className="toggle-inline">
                              <input
                                type="checkbox"
                                checked={pref.batch_notifications}
                                onChange={(e) => updateNotificationPref(pref.event_type, 'batch_notifications', e.target.checked)}
                              />
                              <span>Batch Notifications</span>
                            </label>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Outreach Rules Tab */}
        {activeTab === 'outreach' && (
          <div className="settings-section">
            <h2>Outreach Rules</h2>
            <p className="section-description">Configure automated outreach campaigns and triggers</p>

            <div className="outreach-list">
              {settings.outreach_rules.map(rule => {
                const triggerInfo = triggerEvents.find(t => t.id === rule.trigger_event);
                return (
                  <div key={rule.id} className="outreach-item">
                    <div className="outreach-header">
                      <div className="outreach-info">
                        <span className="outreach-name">{rule.name}</span>
                        <span className="outreach-trigger">{triggerInfo?.name || rule.trigger_event}</span>
                      </div>
                      <label className="toggle-inline">
                        <input
                          type="checkbox"
                          checked={rule.is_active}
                          onChange={(e) => updateOutreachRule(rule.id, 'is_active', e.target.checked)}
                        />
                        <span>Active</span>
                      </label>
                    </div>

                    <div className="outreach-config">
                      <div className="form-grid">
                        <div className="form-group">
                          <label>Delay (minutes)</label>
                          <input
                            type="number"
                            value={rule.delay_minutes}
                            onChange={(e) => updateOutreachRule(rule.id, 'delay_minutes', parseInt(e.target.value) || 0)}
                            min={0}
                          />
                        </div>

                        <div className="form-group">
                          <label>Channel</label>
                          <select
                            value={rule.channel}
                            onChange={(e) => updateOutreachRule(rule.id, 'channel', e.target.value)}
                          >
                            <option value="email">Email</option>
                            <option value="sms">SMS</option>
                            <option value="both">Both</option>
                          </select>
                        </div>

                        <div className="form-group">
                          <label>Template</label>
                          <select
                            value={rule.template_id}
                            onChange={(e) => updateOutreachRule(rule.id, 'template_id', e.target.value)}
                          >
                            {rule.channel !== 'sms' && settings.email_templates.map(t => (
                              <option key={t.id} value={t.id}>{t.name}</option>
                            ))}
                            {rule.channel !== 'email' && settings.sms_templates.map(t => (
                              <option key={t.id} value={t.id}>{t.name}</option>
                            ))}
                          </select>
                        </div>

                        <div className="form-group">
                          <label>Max Sends per Contact</label>
                          <input
                            type="number"
                            value={rule.max_sends_per_contact}
                            onChange={(e) => updateOutreachRule(rule.id, 'max_sends_per_contact', parseInt(e.target.value) || 1)}
                            min={1}
                            max={10}
                          />
                        </div>

                        <div className="form-group">
                          <label>Cooldown (hours)</label>
                          <input
                            type="number"
                            value={rule.cooldown_hours}
                            onChange={(e) => updateOutreachRule(rule.id, 'cooldown_hours', parseInt(e.target.value) || 24)}
                            min={1}
                          />
                        </div>
                      </div>
                    </div>
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
            <p className="section-description">Configure global communication preferences</p>

            <div className="settings-group">
              <h3>Language & Personalization</h3>
              <div className="form-grid">
                <div className="form-group">
                  <label>Default Language</label>
                  <select
                    value={settings.default_language}
                    onChange={(e) => updateGlobal('default_language', e.target.value)}
                  >
                    <option value="en">English</option>
                    <option value="es">Spanish</option>
                    <option value="fr">French</option>
                    <option value="zh">Chinese</option>
                  </select>
                </div>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.enable_ai_personalization}
                    onChange={(e) => updateGlobal('enable_ai_personalization', e.target.checked)}
                  />
                  <span>Enable AI Personalization</span>
                </label>
              </div>
            </div>

            <div className="settings-group">
              <h3>Consent & Compliance</h3>
              <div className="toggle-list">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.require_double_opt_in}
                    onChange={(e) => updateGlobal('require_double_opt_in', e.target.checked)}
                  />
                  <span>Require Double Opt-In</span>
                </label>

                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={settings.consent_tracking_enabled}
                    onChange={(e) => updateGlobal('consent_tracking_enabled', e.target.checked)}
                  />
                  <span>Enable Consent Tracking</span>
                </label>
              </div>
            </div>

            {/* Test Send Section */}
            <div className="settings-group">
              <h3>Test Communications</h3>
              <div className="test-send-form">
                <input
                  type="text"
                  value={testRecipient}
                  onChange={(e) => setTestRecipient(e.target.value)}
                  placeholder="Email or phone number"
                />
                <select id="test-template">
                  <option value="">Select template...</option>
                  <optgroup label="Email Templates">
                    {settings.email_templates.map(t => (
                      <option key={`email-${t.id}`} value={`email:${t.id}`}>{t.name}</option>
                    ))}
                  </optgroup>
                  <optgroup label="SMS Templates">
                    {settings.sms_templates.map(t => (
                      <option key={`sms-${t.id}`} value={`sms:${t.id}`}>{t.name}</option>
                    ))}
                  </optgroup>
                </select>
                <button
                  className="btn-test"
                  onClick={() => {
                    const select = document.getElementById('test-template');
                    if (select.value) {
                      const [channel, templateId] = select.value.split(':');
                      sendTest(channel, templateId);
                    }
                  }}
                >
                  Send Test
                </button>
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

export default CommunicationPreferences;
