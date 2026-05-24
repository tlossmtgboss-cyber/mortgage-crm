import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

// ── Theme ──
const T = {
  bg: '#FAF7F1', card: '#FFFFFF', primary: '#1F3D2E', accent: '#B8924A',
  border: '#ECE6D8', text: '#1A1F1B', muted: '#8B8A7E', success: '#2D7A52',
  error: '#9B2C2C', warning: '#B25F18',
  fontH: "'Fraunces', serif", fontB: "'Geist', 'Inter', sans-serif", fontM: "'Geist Mono', monospace",
  radius: 12, shadow: '0 1px 3px rgba(0,0,0,0.06)',
};

const timingOptions = [
  'First 24 Hours', 'Day 2', 'Day 3', 'Day 4', 'Day 5', 'Day 6', 'Day 7',
  'Week 2', 'Week 3', 'Week 4', 'Month 2', 'Month 3',
];

const actionOptions = [
  { value: 'send_text', label: 'Send Text', icon: '💬' },
  { value: 'make_call', label: 'Make Call', icon: '📞' },
  { value: 'send_email', label: 'Send Email', icon: '✉️' },
  { value: 'notify_partner', label: 'Notify Partner', icon: '🤝' },
];

const targetOptions = [
  { value: 'borrower', label: 'Borrower' },
  { value: 'co_borrower', label: 'Co-Borrower' },
  { value: 'referral_partner', label: 'Referral Partner' },
  { value: 'internal_team', label: 'Internal Team' },
];

const actorOptions = [
  { value: 'LO', label: 'Loan Officer' },
  { value: 'Processor', label: 'Processor' },
  { value: 'Concierge', label: 'Concierge' },
  { value: 'AI', label: 'AI Assistant' },
];

const conditionOptions = [
  'If no response after 24h',
  'If no response after 48h',
  'If docs incomplete',
  'If credit score < 620',
  'If borrower engaged',
  'If partner referred',
  'Always',
];

const actionColorMap = {
  send_text: { bg: '#D1FAE5', border: '#10B981', text: '#065F46' },
  make_call: { bg: '#DBEAFE', border: '#3B82F6', text: '#1E40AF' },
  send_email: { bg: '#FEF3C7', border: '#F59E0B', text: '#92400E' },
  notify_partner: { bg: '#FCE7F3', border: '#EC4899', text: '#9D174D' },
};

const initialRules = [
  {
    id: '1', timing: 'First 24 Hours', action: 'make_call', target: 'borrower', actor: 'LO',
    message: 'Hi {name}, this is {lo_name} from {company}. I received your pre-qualification request and wanted to personally connect. Do you have a few minutes to discuss your home purchase goals?',
    conditions: ['Always'], enabled: true,
  },
  {
    id: '2', timing: 'First 24 Hours', action: 'send_text', target: 'borrower', actor: 'AI',
    message: 'Hi {name}, thanks for your interest in getting pre-qualified! I\'m {lo_name}\'s assistant. Here\'s your secure doc upload link: {upload_url}',
    conditions: ['Always'], enabled: true,
  },
  {
    id: '3', timing: 'First 24 Hours', action: 'send_email', target: 'borrower', actor: 'AI',
    message: 'Subject: Your Pre-Qualification Checklist\n\nHi {name},\n\nTo get started, please upload the following:\n- Last 2 pay stubs\n- 2 years W-2s\n- 2 months bank statements\n- Photo ID\n\nUpload here: {upload_url}\n\nBest,\n{lo_name}',
    conditions: ['Always'], enabled: true,
  },
  {
    id: '4', timing: 'Day 2', action: 'send_text', target: 'borrower', actor: 'Concierge',
    message: 'Hi {name}, friendly reminder to upload your documents when you get a chance. Here\'s the link again: {upload_url}. Let me know if you need help!',
    conditions: ['If no response after 24h', 'If docs incomplete'], enabled: true,
  },
  {
    id: '5', timing: 'Day 3', action: 'make_call', target: 'borrower', actor: 'LO',
    message: 'Follow-up call to review any submitted documents, answer questions about the pre-qual process, and confirm the borrower is still actively looking.',
    conditions: ['If borrower engaged'], enabled: true,
  },
  {
    id: '6', timing: 'Day 3', action: 'notify_partner', target: 'referral_partner', actor: 'LO',
    message: 'Hi {partner_name}, update on your referral {name}: application is in progress, docs {doc_status}. Estimated pre-qual letter in {timeline}. I\'ll keep you posted.',
    conditions: ['If partner referred'], enabled: true,
  },
  {
    id: '7', timing: 'Day 7', action: 'send_email', target: 'borrower', actor: 'AI',
    message: 'Subject: Your Pre-Qualification Update\n\nHi {name},\n\nGreat news! We\'ve completed the initial review of your application. Your credit report has been pulled and analyzed.\n\nAttached: Draft Pre-Qualification Letter\n\nPlease review and let us know if you have questions.\n\nBest,\n{lo_name}',
    conditions: ['If docs incomplete'], enabled: true,
  },
  {
    id: '8', timing: 'Week 2', action: 'make_call', target: 'borrower', actor: 'LO',
    message: 'Two-week check-in: confirm borrower is actively searching, discuss any rate changes, review pre-qual letter details, offer to adjust loan amount if needed.',
    conditions: ['If borrower engaged'], enabled: true,
  },
  {
    id: '9', timing: 'Week 3', action: 'send_text', target: 'borrower', actor: 'AI',
    message: 'Hi {name}, just checking in. Your pre-qualification is valid for {days_remaining} more days. Finding the right home takes time - I\'m here when you need me! - {lo_name}',
    conditions: ['If no response after 48h'], enabled: false,
  },
];

let nextId = 300;

export default function WorkflowBuilderV3() {
  const navigate = useNavigate();
  const [rules, setRules] = useState(initialRules);
  const [showTimeline, setShowTimeline] = useState(false);
  const [dragIdx, setDragIdx] = useState(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);
  const [expandedId, setExpandedId] = useState(null);

  const updateRule = (id, field, value) => {
    setRules(prev => prev.map(r => r.id === id ? { ...r, [field]: value } : r));
  };

  const toggleEnabled = (id) => {
    setRules(prev => prev.map(r => r.id === id ? { ...r, enabled: !r.enabled } : r));
  };

  const toggleCondition = (id, cond) => {
    setRules(prev => prev.map(r => {
      if (r.id !== id) return r;
      const conditions = r.conditions.includes(cond) ? r.conditions.filter(c => c !== cond) : [...r.conditions, cond];
      return { ...r, conditions };
    }));
  };

  const deleteRule = (id) => {
    setRules(prev => prev.filter(r => r.id !== id));
    if (expandedId === id) setExpandedId(null);
  };

  const addRule = () => {
    const newRule = {
      id: String(++nextId), timing: 'Day 2', action: 'send_text', target: 'borrower', actor: 'AI',
      message: '', conditions: ['Always'], enabled: true,
    };
    setRules(prev => [...prev, newRule]);
    setExpandedId(newRule.id);
  };

  const duplicateRule = (id) => {
    const source = rules.find(r => r.id === id);
    if (!source) return;
    const newRule = { ...source, id: String(++nextId), message: source.message + ' (copy)' };
    const idx = rules.findIndex(r => r.id === id);
    setRules(prev => {
      const copy = [...prev];
      copy.splice(idx + 1, 0, newRule);
      return copy;
    });
  };

  const handleDragStart = (idx) => setDragIdx(idx);
  const handleDragOver = (e, idx) => { e.preventDefault(); setDragOverIdx(idx); };
  const handleDrop = (targetIdx) => {
    if (dragIdx === null || dragIdx === targetIdx) { setDragIdx(null); setDragOverIdx(null); return; }
    setRules(prev => {
      const copy = [...prev];
      const [moved] = copy.splice(dragIdx, 1);
      copy.splice(targetIdx, 0, moved);
      return copy;
    });
    setDragIdx(null);
    setDragOverIdx(null);
  };

  const getActionMeta = (action) => actionOptions.find(a => a.value === action) || actionOptions[0];
  const getTargetLabel = (target) => (targetOptions.find(t => t.value === target) || {}).label || target;
  const getActorLabel = (actor) => (actorOptions.find(a => a.value === actor) || {}).label || actor;

  // Group rules by timing for timeline view
  const timelineGroups = {};
  rules.forEach(rule => {
    if (!timelineGroups[rule.timing]) timelineGroups[rule.timing] = [];
    timelineGroups[rule.timing].push(rule);
  });

  return (
    <div style={{ minHeight: '100vh', background: T.bg, fontFamily: T.fontB }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Geist+Mono&family=Inter:wght@400;500;600&display=swap');
        * { box-sizing: border-box; }
        .rule-row { transition: all 0.2s ease; }
        .rule-row:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        .rule-select { appearance: none; -webkit-appearance: none; background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%238B8A7E' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e"); background-repeat: no-repeat; background-position: right 8px center; background-size: 14px; padding-right: 28px; }
        .rule-drag { cursor: grab; user-select: none; }
        .rule-drag:active { cursor: grabbing; }
        .cond-chip { transition: all 0.15s ease; cursor: pointer; }
        .cond-chip:hover { opacity: 0.85; }
        .toggle-track { transition: background 0.2s ease; cursor: pointer; }
        .toggle-knob { transition: transform 0.2s ease; }
        .dup-btn { transition: all 0.15s; }
        .dup-btn:hover { background: ${T.primary} !important; color: white !important; }
        .del-btn:hover { background: ${T.error} !important; color: white !important; }
        textarea:focus, input:focus, select:focus { outline: 2px solid ${T.primary}; outline-offset: -1px; }
        .tl-card { transition: all 0.2s ease; }
        .tl-card:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
      `}</style>

      {/* Header */}
      <div style={{ background: T.card, borderBottom: `1px solid ${T.border}`, padding: '16px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: T.shadow }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.muted, fontSize: 14, fontFamily: T.fontB, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 18 }}>←</span> Back to Workflows
          </button>
          <div style={{ width: 1, height: 24, background: T.border }} />
          <h1 style={{ margin: 0, fontFamily: T.fontH, fontSize: 22, fontWeight: 700, color: T.text }}>Pre-Qualification Workflow</h1>
          <span style={{ fontSize: 11, fontFamily: T.fontM, background: '#FEF3C7', color: T.warning, padding: '3px 10px', borderRadius: 20 }}>V3 — Rules Engine</span>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: T.muted, fontFamily: T.fontM }}>{rules.length} rules / {rules.filter(r => r.enabled).length} active</span>

          {/* Timeline toggle */}
          <button
            onClick={() => setShowTimeline(!showTimeline)}
            style={{
              background: showTimeline ? T.primary : T.bg, color: showTimeline ? 'white' : T.text,
              border: `1px solid ${showTimeline ? T.primary : T.border}`, borderRadius: 8,
              padding: '8px 16px', fontSize: 13, fontFamily: T.fontB, fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 6,
            }}
          >
            {showTimeline ? '☰ Rules View' : '📅 Preview as Timeline'}
          </button>

          <button
            onClick={addRule}
            style={{ background: T.primary, color: 'white', border: 'none', borderRadius: 8, padding: '8px 20px', fontSize: 14, fontFamily: T.fontB, fontWeight: 600, cursor: 'pointer' }}
          >
            + Add Rule
          </button>
        </div>
      </div>

      {showTimeline ? (
        /* ── TIMELINE VIEW ── */
        <div style={{ maxWidth: 800, margin: '32px auto', padding: '0 24px' }}>
          <div style={{ padding: '12px 16px', background: `${T.accent}12`, borderRadius: 8, border: `1px solid ${T.accent}33`, marginBottom: 24, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 14 }}>📅</span>
            <span style={{ fontSize: 13, color: T.accent, fontWeight: 600 }}>Timeline Preview</span>
            <span style={{ fontSize: 12, color: T.muted, marginLeft: 8 }}>Rules grouped by timing, showing only enabled rules</span>
          </div>

          {Object.entries(timelineGroups).map(([timing, groupRules], gi) => {
            const enabledRules = groupRules.filter(r => r.enabled);
            if (enabledRules.length === 0) return null;

            return (
              <div key={timing} style={{ display: 'flex', marginBottom: 24 }}>
                {/* Timeline rail */}
                <div style={{ width: 48, display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                  {gi > 0 && <div style={{ width: 2, height: 16, background: T.border }} />}
                  <div style={{ width: 14, height: 14, borderRadius: '50%', background: T.primary, border: `3px solid ${T.card}`, boxShadow: `0 0 0 2px ${T.primary}`, flexShrink: 0, zIndex: 1 }} />
                  <div style={{ width: 2, flex: 1, background: T.border }} />
                </div>

                {/* Group content */}
                <div style={{ flex: 1, marginLeft: 12 }}>
                  <h3 style={{ margin: '0 0 10px', fontFamily: T.fontH, fontSize: 16, color: T.text }}>{timing}</h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {enabledRules.map(rule => {
                      const actionMeta = getActionMeta(rule.action);
                      const colors = actionColorMap[rule.action];
                      return (
                        <div key={rule.id} className="tl-card" style={{ background: T.card, borderRadius: 10, border: `1px solid ${T.border}`, borderLeft: `4px solid ${colors.border}`, padding: '12px 16px', boxShadow: T.shadow }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <span style={{ fontSize: 16 }}>{actionMeta.icon}</span>
                            <span style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{actionMeta.label}</span>
                            <span style={{ fontSize: 12, color: T.muted }}>to</span>
                            <span style={{ fontSize: 12, fontWeight: 600, color: T.accent }}>{getTargetLabel(rule.target)}</span>
                            <span style={{ fontSize: 12, color: T.muted }}>from</span>
                            <span style={{ fontSize: 12, fontWeight: 600, color: T.primary }}>{getActorLabel(rule.actor)}</span>
                          </div>
                          {rule.conditions.length > 0 && rule.conditions[0] !== 'Always' && (
                            <div style={{ marginTop: 6, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                              {rule.conditions.map(c => (
                                <span key={c} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 8, background: '#FEF3C7', color: T.warning, fontWeight: 600 }}>
                                  {c}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* ── RULES VIEW ── */
        <div style={{ maxWidth: 960, margin: '24px auto', padding: '0 24px' }}>
          {/* Legend */}
          <div style={{ display: 'flex', gap: 16, marginBottom: 20, padding: '10px 16px', background: T.card, borderRadius: 8, border: `1px solid ${T.border}` }}>
            <span style={{ fontSize: 12, color: T.muted, fontWeight: 600 }}>Channels:</span>
            {actionOptions.map(a => (
              <span key={a.value} style={{ fontSize: 12, color: actionColorMap[a.value].text }}>
                {a.icon} {a.label}
              </span>
            ))}
          </div>

          {/* Rules list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {rules.map((rule, idx) => {
              const expanded = expandedId === rule.id;
              const actionMeta = getActionMeta(rule.action);
              const colors = actionColorMap[rule.action];

              return (
                <div
                  key={rule.id}
                  className="rule-row"
                  draggable
                  onDragStart={() => handleDragStart(idx)}
                  onDragOver={(e) => handleDragOver(e, idx)}
                  onDrop={() => handleDrop(idx)}
                  onDragEnd={() => { setDragIdx(null); setDragOverIdx(null); }}
                  style={{
                    background: T.card, borderRadius: T.radius, border: `1px solid ${dragOverIdx === idx ? T.primary : T.border}`,
                    boxShadow: T.shadow, overflow: 'hidden',
                    opacity: dragIdx === idx ? 0.5 : rule.enabled ? 1 : 0.55,
                  }}
                >
                  {/* Rule sentence */}
                  <div style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    {/* Drag handle */}
                    <span className="rule-drag" style={{ fontSize: 14, color: T.muted, flexShrink: 0 }}>⠿</span>

                    {/* Rule number */}
                    <span style={{ fontSize: 11, fontFamily: T.fontM, color: T.muted, background: T.bg, padding: '2px 8px', borderRadius: 6, flexShrink: 0 }}>
                      #{idx + 1}
                    </span>

                    {/* Sentence: On [timing] -> [action] to [target] from [actor] */}
                    <span style={{ fontSize: 13, color: T.muted, fontWeight: 500 }}>On</span>
                    <select
                      className="rule-select"
                      value={rule.timing}
                      onChange={e => updateRule(rule.id, 'timing', e.target.value)}
                      style={{ padding: '5px 28px 5px 10px', borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13, fontFamily: T.fontM, fontWeight: 600, color: T.accent, background: `${T.accent}08`, cursor: 'pointer' }}
                    >
                      {timingOptions.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>

                    <span style={{ fontSize: 16, color: T.muted }}>→</span>

                    <select
                      className="rule-select"
                      value={rule.action}
                      onChange={e => updateRule(rule.id, 'action', e.target.value)}
                      style={{ padding: '5px 28px 5px 10px', borderRadius: 8, border: `1px solid ${colors.border}`, fontSize: 13, fontWeight: 600, color: colors.text, background: colors.bg, cursor: 'pointer', fontFamily: T.fontB }}
                    >
                      {actionOptions.map(a => <option key={a.value} value={a.value}>{a.icon} {a.label}</option>)}
                    </select>

                    <span style={{ fontSize: 13, color: T.muted, fontWeight: 500 }}>to</span>
                    <select
                      className="rule-select"
                      value={rule.target}
                      onChange={e => updateRule(rule.id, 'target', e.target.value)}
                      style={{ padding: '5px 28px 5px 10px', borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13, fontWeight: 600, color: T.text, background: T.bg, cursor: 'pointer', fontFamily: T.fontB }}
                    >
                      {targetOptions.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                    </select>

                    <span style={{ fontSize: 13, color: T.muted, fontWeight: 500 }}>from</span>
                    <select
                      className="rule-select"
                      value={rule.actor}
                      onChange={e => updateRule(rule.id, 'actor', e.target.value)}
                      style={{ padding: '5px 28px 5px 10px', borderRadius: 8, border: `1px solid ${T.primary}20`, fontSize: 13, fontWeight: 600, color: T.primary, background: '#E8F0EB', cursor: 'pointer', fontFamily: T.fontB }}
                    >
                      {actorOptions.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                    </select>

                    {/* Condition badges (collapsed view) */}
                    {rule.conditions.length > 0 && rule.conditions[0] !== 'Always' && (
                      <div style={{ display: 'flex', gap: 3, marginLeft: 4 }}>
                        {rule.conditions.slice(0, 2).map(c => (
                          <span key={c} style={{ fontSize: 10, padding: '2px 6px', borderRadius: 6, background: '#FEF3C7', color: T.warning, fontWeight: 600, whiteSpace: 'nowrap' }}>
                            {c}
                          </span>
                        ))}
                        {rule.conditions.length > 2 && (
                          <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 6, background: T.bg, color: T.muted }}>
                            +{rule.conditions.length - 2}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Spacer */}
                    <div style={{ flex: 1 }} />

                    {/* Expand/collapse */}
                    <button
                      onClick={() => setExpandedId(expanded ? null : rule.id)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: T.muted, padding: '2px 6px', borderRadius: 4 }}
                      title="Edit message & conditions"
                    >
                      {expanded ? '▲' : '▼'}
                    </button>

                    {/* Duplicate */}
                    <button
                      className="dup-btn"
                      onClick={() => duplicateRule(rule.id)}
                      style={{ background: T.bg, border: `1px solid ${T.border}`, cursor: 'pointer', fontSize: 12, color: T.muted, padding: '3px 8px', borderRadius: 6 }}
                      title="Duplicate rule"
                    >
                      ⧉
                    </button>

                    {/* Delete */}
                    <button
                      className="del-btn"
                      onClick={() => deleteRule(rule.id)}
                      style={{ background: `${T.error}08`, border: `1px solid ${T.error}22`, cursor: 'pointer', fontSize: 12, color: T.error, padding: '3px 8px', borderRadius: 6 }}
                      title="Delete rule"
                    >
                      ×
                    </button>

                    {/* Enable toggle */}
                    <div
                      className="toggle-track"
                      onClick={() => toggleEnabled(rule.id)}
                      style={{
                        width: 40, height: 22, borderRadius: 11, padding: 2, flexShrink: 0,
                        background: rule.enabled ? T.success : T.border,
                      }}
                    >
                      <div
                        className="toggle-knob"
                        style={{
                          width: 18, height: 18, borderRadius: '50%', background: 'white',
                          boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                          transform: rule.enabled ? 'translateX(18px)' : 'translateX(0)',
                        }}
                      />
                    </div>
                  </div>

                  {/* Expanded: Message + Conditions */}
                  {expanded && (
                    <div style={{ padding: '0 16px 16px', borderTop: `1px solid ${T.border}` }}>
                      {/* Message template */}
                      <div style={{ marginTop: 14 }}>
                        <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Message Template</label>
                        <div style={{ position: 'relative', marginTop: 4 }}>
                          <textarea
                            value={rule.message}
                            onChange={e => updateRule(rule.id, 'message', e.target.value)}
                            rows={4}
                            style={{
                              width: '100%', padding: '10px 12px', border: `1px solid ${T.border}`, borderRadius: 8,
                              fontSize: 13, fontFamily: T.fontM, color: T.text, resize: 'vertical', background: T.bg, lineHeight: 1.5,
                            }}
                          />
                          <div style={{ marginTop: 4, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            <span style={{ fontSize: 10, color: T.muted }}>Variables:</span>
                            {['{name}', '{lo_name}', '{company}', '{upload_url}', '{partner_name}', '{doc_status}', '{timeline}', '{days_remaining}'].map(v => (
                              <button
                                key={v}
                                onClick={() => updateRule(rule.id, 'message', rule.message + ' ' + v)}
                                style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: '#E8F0EB', color: T.primary, border: `1px solid ${T.primary}22`, cursor: 'pointer', fontFamily: T.fontM }}
                              >
                                {v}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* Conditions */}
                      <div style={{ marginTop: 14 }}>
                        <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Conditions</label>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                          {conditionOptions.map(cond => {
                            const active = rule.conditions.includes(cond);
                            return (
                              <button
                                key={cond}
                                className="cond-chip"
                                onClick={() => toggleCondition(rule.id, cond)}
                                style={{
                                  padding: '5px 12px', borderRadius: 20, fontSize: 12, fontFamily: T.fontB, fontWeight: active ? 600 : 400,
                                  background: active ? '#FEF3C7' : T.bg,
                                  color: active ? T.warning : T.muted,
                                  border: `1.5px solid ${active ? T.warning : T.border}`,
                                  cursor: 'pointer',
                                }}
                              >
                                {active ? '✓ ' : ''}{cond}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Add rule button */}
          <button
            onClick={addRule}
            style={{
              width: '100%', marginTop: 12, padding: '14px', borderRadius: T.radius,
              border: `2px dashed ${T.border}`, background: 'transparent', color: T.muted,
              fontSize: 14, fontFamily: T.fontB, cursor: 'pointer',
            }}
          >
            + Add Rule
          </button>

          {/* Summary */}
          <div style={{ marginTop: 24, padding: 20, background: T.card, borderRadius: T.radius, border: `1px solid ${T.border}`, boxShadow: T.shadow }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ margin: 0, fontFamily: T.fontH, fontSize: 16, color: T.text }}>Workflow Summary</h3>
                <p style={{ margin: '4px 0 0', fontSize: 13, color: T.muted }}>
                  {rules.filter(r => r.enabled).length} active rules across {Object.keys(timelineGroups).length} time periods
                </p>
              </div>
              <div style={{ display: 'flex', gap: 14, fontFamily: T.fontM, fontSize: 12 }}>
                {actionOptions.map(a => {
                  const count = rules.filter(r => r.action === a.value && r.enabled).length;
                  return (
                    <span key={a.value} style={{ color: actionColorMap[a.value].text }}>
                      {a.icon} {count}
                    </span>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
