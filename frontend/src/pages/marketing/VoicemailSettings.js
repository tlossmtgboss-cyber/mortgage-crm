import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import { voicemailAPI } from '../../services/api';
import './MarketingSettings.css';
import { toast } from '../../utils/toast';

const VOICE_OPTIONS = [
  { id: 'alloy', label: 'Alloy', desc: 'Neutral, balanced' },
  { id: 'echo', label: 'Echo', desc: 'Warm, conversational' },
  { id: 'fable', label: 'Fable', desc: 'Expressive, dynamic' },
  { id: 'onyx', label: 'Onyx', desc: 'Deep, authoritative' },
  { id: 'nova', label: 'Nova', desc: 'Friendly, professional' },
  { id: 'shimmer', label: 'Shimmer', desc: 'Clear, upbeat' },
];

function VoicemailSettings() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessMarketing = isAdmin || hasAnyPermission(['marketing.view', 'marketing.manage', 'admin.manage']) || userRole === 'admin' || userRole === 'sales' || userRole === 'loan_officer';

  const [activeTab, setActiveTab] = useState('templates');
  const [templates, setTemplates] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [history, setHistory] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [campaignsLoading, setCampaignsLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);

  // Template form
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    name: '', category: 'follow_up', message_text: '', variables: [],
    voice_provider: 'deepgram', voice_id: 'asteria', voice_speed: 1.0,
    delivery_method: 'vapi_ai',
  });
  const [saving, setSaving] = useState(false);

  // Campaign form
  const [showCampaignForm, setShowCampaignForm] = useState(false);
  const [campaignForm, setCampaignForm] = useState({
    name: '', description: '', template_id: '', contact_filter: { status: '' },
    throttle_rate: 50, scheduled_at: '',
  });
  const [campaignSaving, setCampaignSaving] = useState(false);

  // Audio preview
  const [previewingId, setPreviewingId] = useState(null);
  const audioRef = useRef(null);
  const previewUrlRef = useRef(null);
  const historyLoadedRef = useRef(false);
  const campaignsLoadedRef = useRef(false);

  const loadTemplates = useCallback(async () => {
    try {
      setLoadError(null);
      const res = await voicemailAPI.getTemplates();
      if (res.success) setTemplates(res.templates);
    } catch (err) {
      console.error('Error loading templates:', err);
      setLoadError('Failed to load templates. Please try refreshing the page.');
    }
  }, []);

  const loadAnalytics = useCallback(async () => {
    try {
      const res = await voicemailAPI.getAnalytics();
      if (res.success) setAnalytics(res.analytics);
    } catch (err) {
      console.error('Error loading analytics:', err);
      setLoadError(prev => prev || 'Failed to load analytics data.');
    }
  }, []);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    setLoadError(null);
    try {
      const res = await voicemailAPI.getHistory({ limit: 50 });
      if (res.success) setHistory(res.voicemails);
    } catch (err) {
      console.error('Error loading history:', err);
      setLoadError('Failed to load voicemail history.');
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const loadCampaigns = useCallback(async () => {
    setCampaignsLoading(true);
    setLoadError(null);
    try {
      const res = await voicemailAPI.getCampaigns();
      if (res.success) setCampaigns(res.campaigns);
    } catch (err) {
      console.error('Error loading campaigns:', err);
      setLoadError('Failed to load campaigns.');
    } finally {
      setCampaignsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!canAccessMarketing) return;
    Promise.all([loadTemplates(), loadAnalytics()])
      .catch(err => {
        console.error('Error loading initial data:', err);
        setLoadError('Failed to load data. Please refresh the page.');
      })
      .finally(() => setLoading(false));
  }, [canAccessMarketing, loadTemplates, loadAnalytics]);

  useEffect(() => {
    if (activeTab === 'history' && !historyLoadedRef.current) {
      historyLoadedRef.current = true;
      loadHistory();
    }
    if (activeTab === 'campaigns' && !campaignsLoadedRef.current) {
      campaignsLoadedRef.current = true;
      loadCampaigns();
    }
  }, [activeTab, loadHistory, loadCampaigns]);

  // Cleanup preview audio on unmount
  useEffect(() => {
    return () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, []);

  const handleCreateTemplate = async (e) => {
    e.preventDefault();
    if (!formData.name.trim() || !formData.message_text.trim()) return;
    setSaving(true);
    try {
      const res = await voicemailAPI.createTemplate(formData);
      if (res.success) {
        await loadTemplates();
        setShowForm(false);
        setFormData({
          name: '', category: 'follow_up', message_text: '', variables: [],
          voice_provider: 'deepgram', voice_id: 'asteria', voice_speed: 1.0,
          delivery_method: 'vapi_ai',
        });
      }
    } catch (err) {
      console.error('Error creating template:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteTemplate = async (templateId) => {
    if (!window.confirm('Delete this template?')) return;
    try {
      await voicemailAPI.deleteTemplate(templateId);
      await loadTemplates();
    } catch (err) {
      console.error('Error deleting template:', err);
    }
  };

  const handleAudioUpload = async (templateId, file) => {
    const fd = new FormData();
    fd.append('audio_file', file);
    try {
      await voicemailAPI.uploadTemplateAudio(templateId, fd);
      await loadTemplates();
    } catch (err) {
      console.error('Error uploading audio:', err);
      toast.error('Failed to upload audio. Max 10MB, formats: mp3, wav, ogg, m4a.');
    }
  };

  const handleDeleteAudio = async (templateId) => {
    try {
      await voicemailAPI.deleteTemplateAudio(templateId);
      await loadTemplates();
    } catch (err) {
      console.error('Error deleting audio:', err);
    }
  };

  const handlePreviewVoice = async (template) => {
    setPreviewingId(template.id);
    try {
      // Use OpenAI TTS voice name mapping
      const voiceMap = { asteria: 'nova', rachel: 'alloy', josh: 'onyx', paula: 'nova' };
      const voice = voiceMap[template.voice_id] || template.voice_id || 'nova';

      const blob = await voicemailAPI.previewVoice({
        message: template.message_text.substring(0, 500),
        voice,
        speed: template.voice_speed || 1.0,
      });

      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
      const url = URL.createObjectURL(blob);
      previewUrlRef.current = url;

      if (audioRef.current) {
        audioRef.current.src = url;
        audioRef.current.play();
      }
    } catch (err) {
      console.error('Error previewing voice:', err);
    } finally {
      setPreviewingId(null);
    }
  };

  const handleCreateCampaign = async (e) => {
    e.preventDefault();
    if (!campaignForm.name.trim()) return;
    setCampaignSaving(true);
    try {
      const payload = {
        ...campaignForm,
        template_id: campaignForm.template_id ? parseInt(campaignForm.template_id) : null,
        scheduled_at: campaignForm.scheduled_at || null,
      };
      const res = await voicemailAPI.createCampaign(payload);
      if (res.success) {
        await loadCampaigns();
        setShowCampaignForm(false);
        setCampaignForm({ name: '', description: '', template_id: '', contact_filter: { status: '' }, throttle_rate: 50, scheduled_at: '' });
      }
    } catch (err) {
      console.error('Error creating campaign:', err);
      setLoadError(err.response?.data?.detail || 'Failed to create campaign. Please try again.');
    } finally {
      setCampaignSaving(false);
    }
  };

  const handleCampaignAction = async (campaignId, action) => {
    try {
      if (action === 'start') {
        if (!window.confirm('Start this campaign? This will queue voicemail drops for all matching contacts.')) return;
        await voicemailAPI.startCampaign(campaignId);
      } else if (action === 'pause') {
        await voicemailAPI.pauseCampaign(campaignId);
      } else if (action === 'cancel') {
        if (!window.confirm('Cancel this campaign? Unsent drops will be removed.')) return;
        await voicemailAPI.cancelCampaign(campaignId);
      }
      await loadCampaigns();
    } catch (err) {
      console.error(`Error ${action} campaign:`, err);
      setLoadError(err.response?.data?.detail || `Failed to ${action} campaign. Please try again.`);
      toast.error(err.response?.data?.detail || `Failed to ${action} campaign`);
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
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>Return to Dashboard</button>
        </div>
      </div>
    );
  }

  const statusColor = (status) => {
    switch (status) {
      case 'delivered': return '#2D7A52';
      case 'calling': case 'pending': case 'queued': return '#f59e0b';
      case 'failed': case 'cancelled': return '#ef4444';
      case 'human_answered': return '#3b82f6';
      case 'running': return '#2D7A52';
      case 'paused': return '#f59e0b';
      case 'completed': return '#6b7280';
      case 'draft': case 'scheduled': return '#B8924A';
      default: return '#6b7280';
    }
  };

  const categoryLabels = {
    closing: 'Closing', follow_up: 'Follow Up', urgent: 'Urgent',
    scheduling: 'Scheduling', status_update: 'Status Update', custom: 'Custom'
  };

  const inputStyle = {
    width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
    borderRadius: '8px', fontSize: '14px', boxSizing: 'border-box'
  };
  const labelStyle = { display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '4px' };
  const btnPrimary = {
    padding: '8px 16px', background: '#006B6B', color: '#fff',
    border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: '500'
  };

  return (
    <div className="marketing-settings-page">
      <div className="settings-header">
        <h2>Voicemail Drops</h2>
        <p>Manage templates, campaigns, and track voicemail delivery</p>
      </div>

      {/* Hidden audio element for previews */}
      <audio ref={audioRef} style={{ display: 'none' }} />

      {/* Error Banner */}
      {loadError && (
        <div style={{
          background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px',
          padding: '12px 16px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px'
        }}>
          <span style={{ color: '#dc2626', fontWeight: '500' }}>{loadError}</span>
          <button
            onClick={() => { setLoadError(null); loadTemplates(); loadAnalytics(); }}
            style={{
              marginLeft: 'auto', background: '#dc2626', color: '#fff', border: 'none',
              borderRadius: '6px', padding: '4px 12px', cursor: 'pointer', fontSize: '12px'
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Analytics Cards */}
      {analytics && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '24px' }}>
          {[
            { label: 'Total Sent', value: analytics.total_sent, color: '#111827' },
            { label: 'Delivered', value: analytics.delivered, color: '#2D7A52' },
            { label: 'Failed', value: analytics.failed, color: '#ef4444' },
            { label: 'Callbacks', value: analytics.callbacks_received, color: '#3b82f6' },
            { label: 'Delivery Rate', value: `${analytics.delivery_rate}%`, color: '#2D7A52' },
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
        {['templates', 'campaigns', 'history'].map(tab => (
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
        /* ================================================================ */
        /* TEMPLATES TAB                                                    */
        /* ================================================================ */
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0, fontSize: '16px', color: '#111827' }}>
              Voicemail Templates ({templates.length})
            </h3>
            <button onClick={() => setShowForm(!showForm)} style={btnPrimary}>
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
                  <label style={labelStyle}>Template Name</label>
                  <input type="text" value={formData.name}
                    onChange={e => setFormData({ ...formData, name: e.target.value })}
                    placeholder="e.g., Rate Lock Reminder" required style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>Category</label>
                  <select value={formData.category}
                    onChange={e => setFormData({ ...formData, category: e.target.value })} style={inputStyle}>
                    {Object.entries(categoryLabels).map(([val, label]) => (
                      <option key={val} value={val}>{label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div style={{ marginBottom: '12px' }}>
                <label style={labelStyle}>Message Text</label>
                <textarea value={formData.message_text}
                  onChange={e => {
                    const text = e.target.value;
                    setFormData({ ...formData, message_text: text, variables: extractVariables(text) });
                  }}
                  placeholder="Type your voicemail message. Use {{contact_name}} and {{loan_officer}} for personalization."
                  required rows={4}
                  style={{ ...inputStyle, resize: 'vertical' }} />
                {formData.variables.length > 0 && (
                  <div style={{ marginTop: '6px', fontSize: '12px', color: '#6b7280' }}>
                    Variables: {formData.variables.map(v => `{{${v}}}`).join(', ')}
                  </div>
                )}
              </div>

              {/* Voice Settings */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div>
                  <label style={labelStyle}>Voice</label>
                  <select value={formData.voice_id}
                    onChange={e => setFormData({ ...formData, voice_id: e.target.value })} style={inputStyle}>
                    <option value="asteria">Asteria (Deepgram - Default)</option>
                    {VOICE_OPTIONS.map(v => (
                      <option key={v.id} value={v.id}>{v.label} - {v.desc}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Speed ({formData.voice_speed}x)</label>
                  <input type="range" min="0.5" max="2.0" step="0.1"
                    value={formData.voice_speed}
                    onChange={e => setFormData({ ...formData, voice_speed: parseFloat(e.target.value) })}
                    style={{ width: '100%', marginTop: '8px' }} />
                </div>
                <div>
                  <label style={labelStyle}>Delivery Method</label>
                  <select value={formData.delivery_method}
                    onChange={e => setFormData({ ...formData, delivery_method: e.target.value })} style={inputStyle}>
                    <option value="vapi_ai">AI Voice Call (Vapi)</option>
                    <option value="ringless">Ringless Voicemail (RVM)</option>
                  </select>
                </div>
              </div>

              <button type="submit" disabled={saving || !formData.name.trim() || !formData.message_text.trim()}
                style={{ ...btnPrimary, background: saving ? '#9ca3af' : '#006B6B', cursor: saving ? 'not-allowed' : 'pointer' }}>
                {saving ? 'Saving...' : 'Create Template'}
              </button>
            </form>
          )}

          {/* Templates List */}
          {templates.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280', background: '#f9fafb', borderRadius: '12px' }}>
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
                        {t.delivery_method === 'ringless' && (
                          <span style={{ marginLeft: '8px', color: '#B8924A', fontWeight: '500' }}>RVM</span>
                        )}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <span style={{ fontSize: '11px', color: '#9ca3af' }}>Used {t.times_used || 0}x</span>
                      {!t.is_default && (
                        <button onClick={() => handleDeleteTemplate(t.id)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '14px', color: '#9ca3af' }}
                          title="Delete">x</button>
                      )}
                    </div>
                  </div>

                  <div style={{
                    fontSize: '13px', color: '#4b5563', lineHeight: '1.5',
                    background: '#f9fafb', borderRadius: '8px', padding: '10px',
                    maxHeight: '80px', overflow: 'hidden'
                  }}>
                    {t.message_text}
                  </div>

                  {/* Voice info */}
                  <div style={{ marginTop: '8px', display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: '11px', background: '#f3f4f6', color: '#4b5563', padding: '2px 6px', borderRadius: '4px' }}>
                      {t.voice_id || 'asteria'} {t.voice_speed && t.voice_speed !== 1 ? `(${t.voice_speed}x)` : ''}
                    </span>
                    {t.audio_url && (
                      <span style={{ fontSize: '11px', background: '#dcfce7', color: '#166534', padding: '2px 6px', borderRadius: '4px' }}>
                        Audio uploaded
                      </span>
                    )}
                  </div>

                  {/* Variables */}
                  {t.variables && t.variables.length > 0 && (
                    <div style={{ marginTop: '6px', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                      {t.variables.map(v => (
                        <span key={v} style={{
                          fontSize: '11px', background: '#e0f2fe', color: '#0369a1',
                          padding: '2px 6px', borderRadius: '4px'
                        }}>{`{{${v}}}`}</span>
                      ))}
                    </div>
                  )}

                  {/* Actions */}
                  <div style={{ marginTop: '10px', display: 'flex', gap: '8px', borderTop: '1px solid #f3f4f6', paddingTop: '10px' }}>
                    <button onClick={() => handlePreviewVoice(t)} disabled={previewingId === t.id}
                      style={{ fontSize: '12px', background: 'none', border: '1px solid #d1d5db', borderRadius: '6px',
                        padding: '4px 10px', cursor: 'pointer', color: '#374151' }}>
                      {previewingId === t.id ? 'Generating...' : 'Preview Voice'}
                    </button>
                    {t.audio_url ? (
                      <button onClick={() => handleDeleteAudio(t.id)}
                        style={{ fontSize: '12px', background: 'none', border: '1px solid #fca5a5', borderRadius: '6px',
                          padding: '4px 10px', cursor: 'pointer', color: '#dc2626' }}>
                        Remove Audio
                      </button>
                    ) : (
                      <label style={{ fontSize: '12px', background: 'none', border: '1px solid #d1d5db', borderRadius: '6px',
                        padding: '4px 10px', cursor: 'pointer', color: '#374151', display: 'inline-block' }}>
                        Upload Audio
                        <input type="file" accept=".mp3,.wav,.ogg,.m4a" style={{ display: 'none' }}
                          onChange={e => { if (e.target.files[0]) handleAudioUpload(t.id, e.target.files[0]); }} />
                      </label>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : activeTab === 'campaigns' ? (
        /* ================================================================ */
        /* CAMPAIGNS TAB                                                    */
        /* ================================================================ */
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0, fontSize: '16px', color: '#111827' }}>
              Voicemail Campaigns ({campaigns.length})
            </h3>
            <button onClick={() => setShowCampaignForm(!showCampaignForm)} style={btnPrimary}>
              {showCampaignForm ? 'Cancel' : '+ New Campaign'}
            </button>
          </div>

          {/* Create Campaign Form */}
          {showCampaignForm && (
            <form onSubmit={handleCreateCampaign} style={{
              background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: '12px',
              padding: '20px', marginBottom: '20px'
            }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div>
                  <label style={labelStyle}>Campaign Name</label>
                  <input type="text" value={campaignForm.name}
                    onChange={e => setCampaignForm({ ...campaignForm, name: e.target.value })}
                    placeholder="e.g., Rate Lock Reminder Blast" required style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>Template</label>
                  <select value={campaignForm.template_id}
                    onChange={e => setCampaignForm({ ...campaignForm, template_id: e.target.value })} style={inputStyle}>
                    <option value="">Select a template...</option>
                    {templates.map(t => (
                      <option key={t.id} value={t.id}>{t.name} ({categoryLabels[t.category] || t.category})</option>
                    ))}
                  </select>
                </div>
              </div>

              <div style={{ marginBottom: '12px' }}>
                <label style={labelStyle}>Description</label>
                <textarea value={campaignForm.description}
                  onChange={e => setCampaignForm({ ...campaignForm, description: e.target.value })}
                  placeholder="What is this campaign for?" rows={2} style={{ ...inputStyle, resize: 'vertical' }} />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div>
                  <label style={labelStyle}>Target Lead Status</label>
                  <select value={campaignForm.contact_filter.status}
                    onChange={e => setCampaignForm({ ...campaignForm, contact_filter: { ...campaignForm.contact_filter, status: e.target.value } })}
                    style={inputStyle}>
                    <option value="">All leads</option>
                    <option value="new">New</option>
                    <option value="contacted">Contacted</option>
                    <option value="qualified">Qualified</option>
                    <option value="nurturing">Nurturing</option>
                    <option value="closing">Closing</option>
                    <option value="application">Application</option>
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Throttle (calls/hr)</label>
                  <input type="number" min="10" max="500" value={campaignForm.throttle_rate}
                    onChange={e => setCampaignForm({ ...campaignForm, throttle_rate: parseInt(e.target.value) || 50 })}
                    style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>Schedule (optional)</label>
                  <input type="datetime-local" value={campaignForm.scheduled_at}
                    onChange={e => setCampaignForm({ ...campaignForm, scheduled_at: e.target.value })}
                    style={inputStyle} />
                </div>
              </div>

              <button type="submit" disabled={campaignSaving || !campaignForm.name.trim()}
                style={{ ...btnPrimary, background: campaignSaving ? '#9ca3af' : '#006B6B', cursor: campaignSaving ? 'not-allowed' : 'pointer' }}>
                {campaignSaving ? 'Creating...' : 'Create Campaign'}
              </button>
            </form>
          )}

          {/* Campaigns List */}
          {campaignsLoading ? (
            <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>Loading campaigns...</div>
          ) : campaigns.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280', background: '#f9fafb', borderRadius: '12px' }}>
              <p style={{ margin: '0 0 4px 0', fontWeight: '500' }}>No campaigns yet</p>
              <p style={{ margin: 0, fontSize: '13px' }}>Create a campaign to send voicemails to multiple contacts at once</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: '12px' }}>
              {campaigns.map(c => (
                <div key={c.id} style={{
                  background: '#fff', border: '1px solid #e5e7eb', borderRadius: '12px', padding: '16px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <div style={{ fontWeight: '600', fontSize: '14px', color: '#111827' }}>{c.name}</div>
                      {c.description && (
                        <div style={{ fontSize: '13px', color: '#6b7280', marginTop: '2px' }}>{c.description}</div>
                      )}
                    </div>
                    <span style={{
                      display: 'inline-block', padding: '2px 10px', borderRadius: '4px',
                      fontSize: '12px', fontWeight: '500',
                      color: statusColor(c.status), background: statusColor(c.status) + '15',
                      textTransform: 'capitalize',
                    }}>
                      {c.status}
                    </span>
                  </div>

                  {/* Stats */}
                  <div style={{ display: 'flex', gap: '16px', marginTop: '12px', fontSize: '13px', color: '#6b7280' }}>
                    <span>Sent: <strong style={{ color: '#111827' }}>{c.sent_count}</strong></span>
                    <span>Delivered: <strong style={{ color: '#2D7A52' }}>{c.delivered_count}</strong></span>
                    <span>Failed: <strong style={{ color: '#ef4444' }}>{c.failed_count}</strong></span>
                    <span>Callbacks: <strong style={{ color: '#3b82f6' }}>{c.callback_count}</strong></span>
                    {c.scheduled_at && (
                      <span>Scheduled: <strong>{new Date(c.scheduled_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</strong></span>
                    )}
                  </div>

                  {/* Actions */}
                  <div style={{ marginTop: '12px', display: 'flex', gap: '8px', borderTop: '1px solid #f3f4f6', paddingTop: '10px' }}>
                    {(c.status === 'draft' || c.status === 'scheduled' || c.status === 'paused') && (
                      <button onClick={() => handleCampaignAction(c.id, 'start')}
                        style={{ fontSize: '12px', background: '#006B6B', color: '#fff', border: 'none',
                          borderRadius: '6px', padding: '5px 12px', cursor: 'pointer' }}>
                        {c.status === 'paused' ? 'Resume' : 'Start'}
                      </button>
                    )}
                    {c.status === 'running' && (
                      <button onClick={() => handleCampaignAction(c.id, 'pause')}
                        style={{ fontSize: '12px', background: '#f59e0b', color: '#fff', border: 'none',
                          borderRadius: '6px', padding: '5px 12px', cursor: 'pointer' }}>
                        Pause
                      </button>
                    )}
                    {!['completed', 'cancelled'].includes(c.status) && (
                      <button onClick={() => handleCampaignAction(c.id, 'cancel')}
                        style={{ fontSize: '12px', background: 'none', border: '1px solid #fca5a5',
                          borderRadius: '6px', padding: '4px 12px', cursor: 'pointer', color: '#dc2626' }}>
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        /* ================================================================ */
        /* HISTORY TAB                                                      */
        /* ================================================================ */
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
                      <td style={{ padding: '10px 12px', color: '#111827' }}>{vm.contact_name || 'Unknown'}</td>
                      <td style={{ padding: '10px 12px', color: '#6b7280' }}>{vm.phone_number}</td>
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
