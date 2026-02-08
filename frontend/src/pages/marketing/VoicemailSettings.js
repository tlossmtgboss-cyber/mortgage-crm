import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import { voicemailAPI } from '../../services/api';
import './MarketingSettings.css';

function VoicemailSettings() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessMarketing = isAdmin || hasAnyPermission(['marketing.view', 'marketing.manage', 'admin.manage']) || userRole === 'admin' || userRole === 'sales' || userRole === 'loan_officer';

  const [activeTab, setActiveTab] = useState('templates');
  const [templates, setTemplates] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Template form
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({ name: '', category: 'follow_up', message_text: '', variables: [] });
  const [saving, setSaving] = useState(false);

  const loadTemplates = useCallback(async () => {
    try {
      const res = await voicemailAPI.getTemplates();
      if (res.success) setTemplates(res.templates);
    } catch (err) {
      console.error('Error loading templates:', err);
    }
  }, []);

  const loadAnalytics = useCallback(async () => {
    try {
      const res = await voicemailAPI.getAnalytics();
      if (res.success) setAnalytics(res.analytics);
    } catch (err) {
      console.error('Error loading analytics:', err);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await voicemailAPI.getHistory({ limit: 50 });
      if (res.success) setHistory(res.voicemails);
    } catch (err) {
      console.error('Error loading history:', err);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!canAccessMarketing) return;
    Promise.all([loadTemplates(), loadAnalytics()]).finally(() => setLoading(false));
  }, [canAccessMarketing, loadTemplates, loadAnalytics]);

  useEffect(() => {
    if (activeTab === 'history' && history.length === 0) loadHistory();
  }, [activeTab, history.length, loadHistory]);

  const handleCreateTemplate = async (e) => {
    e.preventDefault();
    if (!formData.name.trim() || !formData.message_text.trim()) return;
    setSaving(true);
    try {
      const res = await voicemailAPI.createTemplate(formData);
      if (res.success) {
        await loadTemplates();
        setShowForm(false);
        setFormData({ name: '', category: 'follow_up', message_text: '', variables: [] });
      }
    } catch (err) {
      console.error('Error creating template:', err);
    } finally {
      setSaving(false);
    }
  };

  const extractVariables = (text) => {
    const matches = text.match(/\{\{(\w+)\}\}/g) || [];
    return [...new Set(matches.map(m => m.replace(/[{}]/g, '')))];
  };

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

  const statusColor = (status) => {
    switch (status) {
      case 'delivered': return '#10b981';
      case 'calling': case 'pending': case 'queued': return '#f59e0b';
      case 'failed': return '#ef4444';
      case 'human_answered': return '#3b82f6';
      case 'no_voicemail': return '#6b7280';
      default: return '#6b7280';
    }
  };

  const categoryLabels = {
    closing: 'Closing', follow_up: 'Follow Up', urgent: 'Urgent',
    scheduling: 'Scheduling', status_update: 'Status Update', custom: 'Custom'
  };

  return (
    <div className="marketing-settings-page">
      <div className="settings-header">
        <h2>Voicemail Drops</h2>
        <p>Manage templates, view delivery analytics, and track voicemail history</p>
      </div>

      {/* Analytics Cards */}
      {analytics && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '24px' }}>
          {[
            { label: 'Total Sent', value: analytics.total_sent, color: '#111827' },
            { label: 'Delivered', value: analytics.delivered, color: '#10b981' },
            { label: 'Failed', value: analytics.failed, color: '#ef4444' },
            { label: 'Callbacks', value: analytics.callbacks_received, color: '#3b82f6' },
            { label: 'Delivery Rate', value: `${analytics.delivery_rate}%`, color: '#10b981' },
            { label: 'Callback Rate', value: `${analytics.callback_rate}%`, color: '#3b82f6' },
          ].map((stat, i) => (
            <div key={i} style={{
              background: '#fff', border: '1px solid #e5e7eb', borderRadius: '10px',
              padding: '16px', textAlign: 'center'
            }}>
              <div style={{ fontSize: '24px', fontWeight: '700', color: stat.color }}>{stat.value}</div>
              <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>{stat.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '20px', borderBottom: '1px solid #e5e7eb', paddingBottom: '0' }}>
        {['templates', 'history'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '10px 20px', border: 'none', cursor: 'pointer',
              fontSize: '14px', fontWeight: activeTab === tab ? '600' : '400',
              color: activeTab === tab ? '#006B6B' : '#6b7280',
              borderBottom: activeTab === tab ? '2px solid #006B6B' : '2px solid transparent',
              background: 'none', textTransform: 'capitalize'
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>Loading...</div>
      ) : activeTab === 'templates' ? (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0, fontSize: '16px', color: '#111827' }}>
              Voicemail Templates ({templates.length})
            </h3>
            <button
              onClick={() => setShowForm(!showForm)}
              style={{
                padding: '8px 16px', background: '#006B6B', color: '#fff',
                border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: '500'
              }}
            >
              {showForm ? 'Cancel' : '+ New Template'}
            </button>
          </div>

          {/* Create Template Form */}
          {showForm && (
            <form onSubmit={handleCreateTemplate} style={{
              background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: '12px',
              padding: '20px', marginBottom: '20px'
            }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '4px' }}>
                    Template Name
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={e => setFormData({ ...formData, name: e.target.value })}
                    placeholder="e.g., Rate Lock Reminder"
                    required
                    style={{
                      width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
                      borderRadius: '8px', fontSize: '14px', boxSizing: 'border-box'
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '4px' }}>
                    Category
                  </label>
                  <select
                    value={formData.category}
                    onChange={e => setFormData({ ...formData, category: e.target.value })}
                    style={{
                      width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
                      borderRadius: '8px', fontSize: '14px', boxSizing: 'border-box'
                    }}
                  >
                    {Object.entries(categoryLabels).map(([val, label]) => (
                      <option key={val} value={val}>{label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '4px' }}>
                  Message Text
                </label>
                <textarea
                  value={formData.message_text}
                  onChange={e => {
                    const text = e.target.value;
                    setFormData({ ...formData, message_text: text, variables: extractVariables(text) });
                  }}
                  placeholder="Type your voicemail message. Use {{contact_name}} and {{loan_officer}} for personalization."
                  required
                  rows={4}
                  style={{
                    width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
                    borderRadius: '8px', fontSize: '14px', resize: 'vertical', boxSizing: 'border-box'
                  }}
                />
                {formData.variables.length > 0 && (
                  <div style={{ marginTop: '6px', fontSize: '12px', color: '#6b7280' }}>
                    Variables: {formData.variables.map(v => `{{${v}}}`).join(', ')}
                  </div>
                )}
              </div>
              <button
                type="submit"
                disabled={saving || !formData.name.trim() || !formData.message_text.trim()}
                style={{
                  padding: '8px 20px', background: saving ? '#9ca3af' : '#006B6B', color: '#fff',
                  border: 'none', borderRadius: '8px', cursor: saving ? 'not-allowed' : 'pointer',
                  fontSize: '13px', fontWeight: '500'
                }}
              >
                {saving ? 'Saving...' : 'Create Template'}
              </button>
            </form>
          )}

          {/* Templates List */}
          {templates.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280', background: '#f9fafb', borderRadius: '12px' }}>
              <div style={{ fontSize: '32px', marginBottom: '8px' }}>🎙️</div>
              <p style={{ margin: '0 0 4px 0', fontWeight: '500' }}>No templates yet</p>
              <p style={{ margin: 0, fontSize: '13px' }}>Create your first voicemail template to get started</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '12px' }}>
              {templates.map(t => (
                <div key={t.id} style={{
                  background: '#fff', border: '1px solid #e5e7eb', borderRadius: '12px', padding: '16px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <div>
                      <div style={{ fontWeight: '600', fontSize: '14px', color: '#111827' }}>{t.name}</div>
                      <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
                        {categoryLabels[t.category] || t.category}
                        {t.is_default && <span style={{ marginLeft: '8px', color: '#006B6B', fontWeight: '500' }}>Default</span>}
                      </div>
                    </div>
                    <div style={{ fontSize: '11px', color: '#9ca3af' }}>
                      Used {t.times_used || 0}x
                    </div>
                  </div>
                  <div style={{
                    fontSize: '13px', color: '#4b5563', lineHeight: '1.5',
                    background: '#f9fafb', borderRadius: '8px', padding: '10px',
                    maxHeight: '80px', overflow: 'hidden'
                  }}>
                    {t.message_text}
                  </div>
                  {t.variables && t.variables.length > 0 && (
                    <div style={{ marginTop: '8px', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                      {t.variables.map(v => (
                        <span key={v} style={{
                          fontSize: '11px', background: '#e0f2fe', color: '#0369a1',
                          padding: '2px 6px', borderRadius: '4px'
                        }}>
                          {`{{${v}}}`}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        /* History Tab */
        <div>
          <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', color: '#111827' }}>
            Recent Voicemail Drops
          </h3>
          {historyLoading ? (
            <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>Loading history...</div>
          ) : history.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280', background: '#f9fafb', borderRadius: '12px' }}>
              <p style={{ margin: 0 }}>No voicemail drops yet</p>
            </div>
          ) : (
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: '12px', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                <thead>
                  <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                    <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '500', color: '#6b7280' }}>Recipient</th>
                    <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '500', color: '#6b7280' }}>Phone</th>
                    <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '500', color: '#6b7280' }}>Status</th>
                    <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '500', color: '#6b7280' }}>Date</th>
                    <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '500', color: '#6b7280' }}>Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map(vm => (
                    <tr key={vm.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '10px 12px', color: '#111827' }}>
                        {vm.contact_name || 'Unknown'}
                      </td>
                      <td style={{ padding: '10px 12px', color: '#6b7280' }}>
                        {vm.phone_number}
                      </td>
                      <td style={{ padding: '10px 12px' }}>
                        <span style={{
                          display: 'inline-block', padding: '2px 8px', borderRadius: '4px',
                          fontSize: '12px', fontWeight: '500',
                          color: statusColor(vm.status), background: statusColor(vm.status) + '15'
                        }}>
                          {vm.status}
                        </span>
                      </td>
                      <td style={{ padding: '10px 12px', color: '#6b7280' }}>
                        {new Date(vm.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                      </td>
                      <td style={{ padding: '10px 12px', color: '#6b7280' }}>
                        {vm.call_duration ? `${vm.call_duration}s` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default VoicemailSettings;
