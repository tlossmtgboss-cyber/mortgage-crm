import React, { useState, useEffect, useRef } from 'react';
import { workflowGraphApi } from '../../services/workflowGraphApi';
import './NodeDetailDrawer.css';

const ROLES = ['LO', 'Processor', 'Concierge', 'AI', 'Manager', 'System'];
const CHANNELS = [
  { key: 'phone', label: 'Phone', icon: '📞' },
  { key: 'text', label: 'Text', icon: '📱' },
  { key: 'voicemail_drop', label: 'Voicemail Drop', icon: '📩' },
  { key: 'text_process', label: 'Text Process', icon: '💬' },
  { key: 'email', label: 'Email', icon: '✉️' },
  { key: 'referral_partner', label: 'Referral Partner', icon: '🤝' },
];

export default function NodeDetailDrawer({ workflowKey, node, onUpdate, onDelete, onClose }) {
  const [activeTab, setActiveTab] = useState('config');
  const [leads, setLeads] = useState(null);
  const [history, setHistory] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const debounceRef = useRef(null);

  const handleChange = (field, value) => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      onUpdate({ [field]: value });
    }, 400);
  };

  const handleChannelToggle = (channelKey) => {
    const updated = { ...(node.channels || {}), [channelKey]: !node.channels?.[channelKey] };
    onUpdate({ channels: updated });
  };

  useEffect(() => {
    if (activeTab === 'leads' && !leads) {
      workflowGraphApi.getNodeLeads(workflowKey, node.id).then(r => setLeads(r.data));
    }
    if (activeTab === 'history' && !history) {
      workflowGraphApi.getNodeHistory(workflowKey, node.id).then(r => setHistory(r.data.history));
    }
    if (activeTab === 'metrics' && !metrics) {
      workflowGraphApi.getNodeMetrics(workflowKey, node.id).then(r => setMetrics(r.data));
    }
  }, [activeTab, node.id, workflowKey, leads, history, metrics]);

  useEffect(() => {
    setLeads(null);
    setHistory(null);
    setMetrics(null);
  }, [node.id]);

  const tabs = [
    { key: 'config', label: 'Config' },
    { key: 'leads', label: `Leads (${node.lead_count || 0})` },
    { key: 'history', label: 'History' },
    { key: 'metrics', label: 'Metrics' },
  ];

  return (
    <div className="wf-drawer">
      <div className="wf-drawer-header">
        <span className="wf-drawer-title">{node.label}</span>
        <button className="wf-drawer-close" onClick={onClose}>×</button>
      </div>

      <div className="wf-drawer-tabs">
        {tabs.map(t => (
          <button
            key={t.key}
            className={`wf-drawer-tab ${activeTab === t.key ? 'active' : ''}`}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="wf-drawer-body">
        {activeTab === 'config' && (
          <div className="wf-drawer-config">
            <div className="wf-field">
              <label>Label</label>
              <input defaultValue={node.label} onChange={e => handleChange('label', e.target.value)} />
            </div>
            <div className="wf-field">
              <label>Description</label>
              <textarea defaultValue={node.description || ''} onChange={e => handleChange('description', e.target.value)} />
            </div>
            <div className="wf-field">
              <label>Channels</label>
              <div className="wf-channel-grid">
                {CHANNELS.map(ch => (
                  <label key={ch.key} className="wf-channel-toggle">
                    <input
                      type="checkbox"
                      checked={!!node.channels?.[ch.key]}
                      onChange={() => handleChannelToggle(ch.key)}
                    />
                    <span>{ch.icon} {ch.label}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="wf-field-row">
              <div className="wf-field">
                <label>Role</label>
                <select defaultValue={node.role || ''} onChange={e => handleChange('role', e.target.value)}>
                  <option value="">None</option>
                  {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
              <div className="wf-field">
                <label>Day</label>
                <input defaultValue={node.day_label || ''} onChange={e => handleChange('day_label', e.target.value)} />
              </div>
            </div>
            <div className="wf-field-row">
              <div className="wf-field">
                <label>Time of Day</label>
                <select defaultValue={node.time_of_day || ''} onChange={e => handleChange('time_of_day', e.target.value)}>
                  <option value="">Any</option>
                  <option value="AM">AM</option>
                  <option value="PM">PM</option>
                </select>
              </div>
              <div className="wf-field">
                <label>Repeat Weekly</label>
                <input type="checkbox" checked={node.repeat_weekly || false} onChange={e => onUpdate({ repeat_weekly: e.target.checked })} />
              </div>
            </div>

            {node.role === 'AI' && (
              <div className="wf-ai-guidance">
                <h4>AI Guidance</h4>
                <div className="wf-field">
                  <label>Objective</label>
                  <input
                    defaultValue={node.ai_guidance?.objective || ''}
                    onChange={e => handleChange('ai_guidance', { ...(node.ai_guidance || {}), objective: e.target.value })}
                  />
                </div>
                <div className="wf-field">
                  <label>Talking Points / Script</label>
                  <textarea
                    defaultValue={node.ai_guidance?.talking_points || ''}
                    onChange={e => handleChange('ai_guidance', { ...(node.ai_guidance || {}), talking_points: e.target.value })}
                    rows={4}
                  />
                </div>
                <div className="wf-field">
                  <label>Success Criteria</label>
                  <input
                    defaultValue={node.ai_guidance?.success_criteria || ''}
                    onChange={e => handleChange('ai_guidance', { ...(node.ai_guidance || {}), success_criteria: e.target.value })}
                  />
                </div>
                <div className="wf-field">
                  <label>Escalation Rules</label>
                  <textarea
                    defaultValue={node.ai_guidance?.escalation_rules || ''}
                    onChange={e => handleChange('ai_guidance', { ...(node.ai_guidance || {}), escalation_rules: e.target.value })}
                    rows={3}
                  />
                </div>
              </div>
            )}

            <button className="wf-delete-btn" onClick={onDelete}>Delete Node</button>
          </div>
        )}

        {activeTab === 'leads' && (
          <div className="wf-drawer-leads">
            {!leads ? <div className="wf-drawer-loading">Loading...</div> :
            leads.leads?.length === 0 ? <div className="wf-drawer-empty">No leads at this step</div> :
            leads.leads.map(l => (
              <div key={l.id} className="wf-lead-row">
                <span className="wf-lead-name">{l.first_name} {l.last_name}</span>
                <span className="wf-lead-detail">{l.email}</span>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'history' && (
          <div className="wf-drawer-history">
            {!history ? <div className="wf-drawer-loading">Loading...</div> :
            history.length === 0 ? <div className="wf-drawer-empty">No movement history</div> :
            history.map(h => (
              <div key={h.id} className="wf-history-row">
                <span className="wf-history-name">{h.lead_name}</span>
                <span className="wf-history-detail">
                  {h.direction === 'in' ? `from ${h.from_node_label || 'entry'}` : `to ${h.to_node_label}`}
                </span>
                <span className="wf-history-time">{new Date(h.moved_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'metrics' && (
          <div className="wf-drawer-metrics">
            {!metrics ? <div className="wf-drawer-loading">Loading...</div> : (
              <div className="wf-metrics-grid">
                <div className="wf-metric-card">
                  <div className="wf-metric-value">{metrics.current_leads}</div>
                  <div className="wf-metric-label">Current Leads</div>
                </div>
                <div className="wf-metric-card">
                  <div className="wf-metric-value">{metrics.total_entered}</div>
                  <div className="wf-metric-label">Total Entered</div>
                </div>
                <div className="wf-metric-card">
                  <div className="wf-metric-value">{metrics.total_exited}</div>
                  <div className="wf-metric-label">Total Exited</div>
                </div>
                <div className="wf-metric-card">
                  <div className="wf-metric-value">{metrics.completion_rate}%</div>
                  <div className="wf-metric-label">Completion Rate</div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
