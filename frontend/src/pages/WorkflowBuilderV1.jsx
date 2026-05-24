import React, { useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

// ── Theme ──
const T = {
  bg: '#FAF7F1', card: '#FFFFFF', primary: '#1F3D2E', accent: '#B8924A',
  border: '#ECE6D8', text: '#1A1F1B', muted: '#8B8A7E', success: '#2D7A52',
  error: '#9B2C2C', warning: '#B25F18',
  fontH: "'Fraunces', serif", fontB: "'Geist', 'Inter', sans-serif", fontM: "'Geist Mono', monospace",
  radius: 12, shadow: '0 1px 3px rgba(0,0,0,0.06)',
};

const channelMeta = {
  phone: { icon: '📞', label: 'Phone', color: '#3B82F6' },
  text: { icon: '💬', label: 'Text', color: '#10B981' },
  email: { icon: '✉️', label: 'Email', color: '#F59E0B' },
  referral_partner: { icon: '🤝', label: 'Partner', color: '#EC4899' },
};

const roleMeta = {
  LO: { label: 'Loan Officer', color: '#1F3D2E', bg: '#E8F0EB' },
  Processor: { label: 'Processor', color: '#7C3AED', bg: '#EDE9FE' },
  Concierge: { label: 'Concierge', color: '#B8924A', bg: '#FEF3C7' },
  AI: { label: 'AI Assistant', color: '#0EA5E9', bg: '#E0F2FE' },
};

const statusMeta = {
  healthy: { color: T.success, label: 'Healthy' },
  broken: { color: T.error, label: 'Broken' },
  disabled: { color: T.muted, label: 'Disabled' },
};

const initialSteps = [
  {
    id: '1', day_label: 'First 24 Hours', channels: { phone: true, text: true, email: true, referral_partner: false },
    description: 'Initial outreach: welcome call + intro text + pre-qual checklist email. Confirm borrower intent and collect basic income/asset info.',
    roles: ['LO', 'AI'], status: 'healthy', time: 'AM', repeat_weekly: false,
  },
  {
    id: '2', day_label: 'Day 2', channels: { phone: false, text: true, email: true, referral_partner: false },
    description: 'Send document checklist via email. Follow up with text reminder including secure upload link. AI verifies document receipt.',
    roles: ['AI', 'Concierge'], status: 'healthy', time: 'AM', repeat_weekly: false,
  },
  {
    id: '3', day_label: 'Day 3', channels: { phone: true, text: false, email: false, referral_partner: true },
    description: 'LO follow-up call to review submitted docs and answer questions. Notify referral partner of application progress.',
    roles: ['LO'], status: 'healthy', time: 'PM', repeat_weekly: false,
  },
  {
    id: '4', day_label: 'Day 7', channels: { phone: false, text: true, email: true, referral_partner: false },
    description: 'Credit report pulled and analyzed. Send pre-qualification letter draft for review. Flag any credit issues for LO attention.',
    roles: ['Processor', 'AI'], status: 'broken', time: 'AM', repeat_weekly: false,
  },
  {
    id: '5', day_label: 'Day 14', channels: { phone: true, text: true, email: false, referral_partner: true },
    description: 'Two-week check-in call. Confirm borrower is still actively searching. Update referral partner on timeline. Escalate if no engagement.',
    roles: ['LO', 'Concierge'], status: 'healthy', time: 'PM', repeat_weekly: true,
  },
  {
    id: '6', day_label: 'Day 21', channels: { phone: false, text: true, email: true, referral_partner: false },
    description: 'Final pre-qual status summary email. If borrower non-responsive, move to nurture sequence. Close loop with referral partner.',
    roles: ['AI'], status: 'disabled', time: 'AM', repeat_weekly: false,
  },
];

let nextId = 100;

export default function WorkflowBuilderV1() {
  const navigate = useNavigate();
  const [steps, setSteps] = useState(initialSteps);
  const [expandedId, setExpandedId] = useState(null);
  const [dragId, setDragId] = useState(null);
  const [dragOverId, setDragOverId] = useState(null);
  const [testRunning, setTestRunning] = useState(false);
  const [testStep, setTestStep] = useState(-1);
  const [showAddMenu, setShowAddMenu] = useState(null); // index to insert after

  const toggleExpand = (id) => setExpandedId(expandedId === id ? null : id);

  const updateStep = (id, field, value) => {
    setSteps(prev => prev.map(s => s.id === id ? { ...s, [field]: value } : s));
  };

  const toggleChannel = (id, ch) => {
    setSteps(prev => prev.map(s => s.id === id ? { ...s, channels: { ...s.channels, [ch]: !s.channels[ch] } } : s));
  };

  const toggleRole = (id, role) => {
    setSteps(prev => prev.map(s => {
      if (s.id !== id) return s;
      const roles = s.roles.includes(role) ? s.roles.filter(r => r !== role) : [...s.roles, role];
      return { ...s, roles };
    }));
  };

  const deleteStep = (id) => {
    setSteps(prev => prev.filter(s => s.id !== id));
    if (expandedId === id) setExpandedId(null);
  };

  const addStep = (afterIndex) => {
    const newStep = {
      id: String(++nextId), day_label: 'New Step', channels: { phone: false, text: false, email: false, referral_partner: false },
      description: '', roles: [], status: 'healthy', time: 'AM', repeat_weekly: false,
    };
    setSteps(prev => {
      const copy = [...prev];
      copy.splice(afterIndex + 1, 0, newStep);
      return copy;
    });
    setExpandedId(newStep.id);
    setShowAddMenu(null);
  };

  const handleDragStart = (id) => setDragId(id);
  const handleDragOver = (e, id) => { e.preventDefault(); setDragOverId(id); };
  const handleDrop = (targetId) => {
    if (!dragId || dragId === targetId) { setDragId(null); setDragOverId(null); return; }
    setSteps(prev => {
      const copy = [...prev];
      const fromIdx = copy.findIndex(s => s.id === dragId);
      const toIdx = copy.findIndex(s => s.id === targetId);
      const [moved] = copy.splice(fromIdx, 1);
      copy.splice(toIdx, 0, moved);
      return copy;
    });
    setDragId(null);
    setDragOverId(null);
  };

  const runTest = () => {
    setTestRunning(true);
    setTestStep(0);
    let i = 0;
    const interval = setInterval(() => {
      i++;
      if (i >= steps.length) {
        clearInterval(interval);
        setTimeout(() => { setTestRunning(false); setTestStep(-1); }, 1200);
      } else {
        setTestStep(i);
      }
    }, 1500);
  };

  const cycleStatus = (id) => {
    const order = ['healthy', 'broken', 'disabled'];
    setSteps(prev => prev.map(s => {
      if (s.id !== id) return s;
      const idx = order.indexOf(s.status);
      return { ...s, status: order[(idx + 1) % 3] };
    }));
  };

  return (
    <div style={{ minHeight: '100vh', background: T.bg, fontFamily: T.fontB }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Geist+Mono&family=Inter:wght@400;500;600&display=swap');
        * { box-sizing: border-box; }
        .wf-step-card { transition: all 0.2s ease; }
        .wf-step-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        .wf-channel-btn { transition: all 0.15s ease; cursor: pointer; border: none; outline: none; }
        .wf-channel-btn:hover { transform: scale(1.1); }
        .wf-role-chip { transition: all 0.15s ease; cursor: pointer; border: none; outline: none; }
        .wf-role-chip:hover { opacity: 0.85; }
        .wf-add-btn { transition: all 0.2s ease; cursor: pointer; }
        .wf-add-btn:hover { transform: scale(1.2); background: ${T.primary} !important; color: white !important; }
        .wf-drag-handle { cursor: grab; user-select: none; }
        .wf-drag-handle:active { cursor: grabbing; }
        .wf-timeline-dot { transition: all 0.3s ease; }
        .wf-test-pulse { animation: pulse 1s infinite; }
        @keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(31,61,46,0.4); } 50% { box-shadow: 0 0 0 12px rgba(31,61,46,0); } }
        .wf-delete-btn { transition: all 0.15s ease; }
        .wf-delete-btn:hover { background: ${T.error} !important; color: white !important; }
        textarea:focus, input:focus, select:focus { outline: 2px solid ${T.primary}; outline-offset: -1px; }
      `}</style>

      {/* Header */}
      <div style={{ background: T.card, borderBottom: `1px solid ${T.border}`, padding: '16px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: T.shadow }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.muted, fontSize: 14, fontFamily: T.fontB, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 18 }}>←</span> Back to Workflows
          </button>
          <div style={{ width: 1, height: 24, background: T.border }} />
          <h1 style={{ margin: 0, fontFamily: T.fontH, fontSize: 22, fontWeight: 700, color: T.text }}>Pre-Qualification Workflow</h1>
          <span style={{ fontSize: 11, fontFamily: T.fontM, background: '#E8F0EB', color: T.primary, padding: '3px 10px', borderRadius: 20 }}>V1 — Timeline Builder</span>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: T.muted, fontFamily: T.fontM }}>{steps.length} steps</span>
          <button
            onClick={runTest}
            disabled={testRunning}
            style={{
              background: testRunning ? T.muted : T.primary, color: 'white', border: 'none', borderRadius: 8,
              padding: '8px 20px', fontSize: 14, fontFamily: T.fontB, fontWeight: 600, cursor: testRunning ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 8,
            }}
          >
            {testRunning ? '⏳ Testing...' : '▶ Test Workflow'}
          </button>
        </div>
      </div>

      {/* Timeline */}
      <div style={{ maxWidth: 780, margin: '32px auto', padding: '0 24px' }}>
        {steps.map((step, idx) => {
          const expanded = expandedId === step.id;
          const isTesting = testRunning && testStep === idx;
          const isTestedPast = testRunning && testStep > idx;
          const sMeta = statusMeta[step.status];

          return (
            <React.Fragment key={step.id}>
              {/* Timeline connector + dot */}
              <div style={{ display: 'flex', alignItems: 'stretch' }}>
                {/* Left: timeline rail */}
                <div style={{ width: 48, display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                  {idx > 0 && <div style={{ width: 2, flex: 1, background: isTestedPast ? T.primary : T.border }} />}
                  <div
                    className={`wf-timeline-dot${isTesting ? ' wf-test-pulse' : ''}`}
                    style={{
                      width: isTesting ? 20 : 14, height: isTesting ? 20 : 14, borderRadius: '50%',
                      background: isTesting ? T.primary : isTestedPast ? T.primary : sMeta.color,
                      border: `3px solid ${T.card}`, boxShadow: `0 0 0 2px ${isTesting ? T.primary : sMeta.color}`,
                      flexShrink: 0, zIndex: 1,
                    }}
                  />
                  {idx < steps.length - 1 && <div style={{ width: 2, flex: 1, background: isTestedPast ? T.primary : T.border }} />}
                </div>

                {/* Right: card */}
                <div
                  className="wf-step-card"
                  draggable
                  onDragStart={() => handleDragStart(step.id)}
                  onDragOver={(e) => handleDragOver(e, step.id)}
                  onDrop={() => handleDrop(step.id)}
                  onDragEnd={() => { setDragId(null); setDragOverId(null); }}
                  style={{
                    flex: 1, marginLeft: 12, marginBottom: idx < steps.length - 1 ? 0 : 0,
                    background: T.card, borderRadius: T.radius, border: `1px solid ${dragOverId === step.id ? T.primary : T.border}`,
                    boxShadow: T.shadow, overflow: 'hidden',
                    opacity: dragId === step.id ? 0.5 : 1,
                    transform: isTesting ? 'scale(1.01)' : 'none',
                  }}
                >
                  {/* Collapsed header */}
                  <div
                    onClick={() => toggleExpand(step.id)}
                    style={{ padding: '14px 18px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 12 }}
                  >
                    <span className="wf-drag-handle" onClick={e => e.stopPropagation()} style={{ fontSize: 14, color: T.muted }}>⠿</span>

                    <div
                      onClick={(e) => { e.stopPropagation(); cycleStatus(step.id); }}
                      title={`Status: ${sMeta.label} (click to cycle)`}
                      style={{ width: 10, height: 10, borderRadius: '50%', background: sMeta.color, flexShrink: 0, cursor: 'pointer' }}
                    />

                    <span style={{ fontFamily: T.fontM, fontSize: 12, color: T.accent, fontWeight: 600, minWidth: 100 }}>{step.day_label}</span>

                    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                      {Object.entries(step.channels).filter(([, v]) => v).map(([ch]) => (
                        <span key={ch} title={channelMeta[ch].label} style={{ fontSize: 13 }}>{channelMeta[ch].icon}</span>
                      ))}
                    </div>

                    <p style={{ margin: 0, fontSize: 13, color: T.muted, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: expanded ? 'normal' : 'nowrap' }}>
                      {step.description || '(no description)'}
                    </p>

                    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                      {step.roles.map(r => (
                        <span key={r} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 10, background: roleMeta[r].bg, color: roleMeta[r].color, fontWeight: 600 }}>
                          {r}
                        </span>
                      ))}
                    </div>

                    <span style={{ fontSize: 16, color: T.muted, transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▾</span>
                  </div>

                  {/* Expanded details */}
                  {expanded && (
                    <div style={{ padding: '0 18px 18px', borderTop: `1px solid ${T.border}` }}>
                      {/* Day Label + Time + Repeat */}
                      <div style={{ display: 'flex', gap: 12, marginTop: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                        <div style={{ flex: 1, minWidth: 140 }}>
                          <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Day Label</label>
                          <input
                            value={step.day_label}
                            onChange={(e) => updateStep(step.id, 'day_label', e.target.value)}
                            style={{ width: '100%', marginTop: 4, padding: '8px 12px', border: `1px solid ${T.border}`, borderRadius: 8, fontSize: 14, fontFamily: T.fontB, color: T.text, background: T.bg }}
                          />
                        </div>
                        <div style={{ minWidth: 90 }}>
                          <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Time</label>
                          <select
                            value={step.time}
                            onChange={(e) => updateStep(step.id, 'time', e.target.value)}
                            style={{ width: '100%', marginTop: 4, padding: '8px 12px', border: `1px solid ${T.border}`, borderRadius: 8, fontSize: 14, fontFamily: T.fontB, color: T.text, background: T.bg }}
                          >
                            <option value="AM">AM</option>
                            <option value="PM">PM</option>
                          </select>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
                          <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13, color: T.text, paddingBottom: 4 }}>
                            <input
                              type="checkbox"
                              checked={step.repeat_weekly}
                              onChange={() => updateStep(step.id, 'repeat_weekly', !step.repeat_weekly)}
                              style={{ accentColor: T.primary }}
                            />
                            Repeat weekly
                          </label>
                        </div>
                      </div>

                      {/* Description */}
                      <div style={{ marginTop: 14 }}>
                        <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Task Description</label>
                        <textarea
                          value={step.description}
                          onChange={(e) => updateStep(step.id, 'description', e.target.value)}
                          rows={3}
                          style={{ width: '100%', marginTop: 4, padding: '10px 12px', border: `1px solid ${T.border}`, borderRadius: 8, fontSize: 13, fontFamily: T.fontB, color: T.text, resize: 'vertical', background: T.bg }}
                        />
                      </div>

                      {/* Channels */}
                      <div style={{ marginTop: 14 }}>
                        <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Communication Channels</label>
                        <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                          {Object.entries(channelMeta).map(([ch, meta]) => (
                            <button
                              key={ch}
                              className="wf-channel-btn"
                              onClick={() => toggleChannel(step.id, ch)}
                              style={{
                                padding: '6px 14px', borderRadius: 20, fontSize: 13,
                                background: step.channels[ch] ? meta.color + '18' : T.bg,
                                color: step.channels[ch] ? meta.color : T.muted,
                                border: `1.5px solid ${step.channels[ch] ? meta.color : T.border}`,
                                fontWeight: step.channels[ch] ? 600 : 400,
                              }}
                            >
                              {meta.icon} {meta.label}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Roles */}
                      <div style={{ marginTop: 14 }}>
                        <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Assigned Roles</label>
                        <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                          {Object.entries(roleMeta).map(([role, meta]) => (
                            <button
                              key={role}
                              className="wf-role-chip"
                              onClick={() => toggleRole(step.id, role)}
                              style={{
                                padding: '6px 14px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                                background: step.roles.includes(role) ? meta.bg : T.bg,
                                color: step.roles.includes(role) ? meta.color : T.muted,
                                border: `1.5px solid ${step.roles.includes(role) ? meta.color : T.border}`,
                              }}
                            >
                              {meta.label}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Status + Actions */}
                      <div style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                          <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Status</label>
                          <select
                            value={step.status}
                            onChange={(e) => updateStep(step.id, 'status', e.target.value)}
                            style={{ padding: '6px 10px', border: `1px solid ${T.border}`, borderRadius: 8, fontSize: 13, fontFamily: T.fontB, color: statusMeta[step.status].color, background: T.bg, fontWeight: 600 }}
                          >
                            <option value="healthy">Healthy</option>
                            <option value="broken">Broken</option>
                            <option value="disabled">Disabled</option>
                          </select>
                        </div>
                        <button
                          className="wf-delete-btn"
                          onClick={() => deleteStep(step.id)}
                          style={{ padding: '6px 14px', borderRadius: 8, border: `1px solid ${T.error}33`, background: `${T.error}0a`, color: T.error, fontSize: 13, fontFamily: T.fontB, cursor: 'pointer' }}
                        >
                          Delete Step
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Add button between steps */}
              <div style={{ display: 'flex', alignItems: 'center', height: 36 }}>
                <div style={{ width: 48, display: 'flex', justifyContent: 'center' }}>
                  <div style={{ width: 2, height: '100%', background: T.border }} />
                </div>
                <div style={{ flex: 1, display: 'flex', justifyContent: 'center', marginLeft: 12, position: 'relative' }}>
                  <button
                    className="wf-add-btn"
                    onClick={() => addStep(idx)}
                    title="Add step here"
                    style={{
                      width: 26, height: 26, borderRadius: '50%', border: `2px dashed ${T.border}`,
                      background: T.card, color: T.muted, fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      lineHeight: 1,
                    }}
                  >
                    +
                  </button>
                </div>
              </div>
            </React.Fragment>
          );
        })}

        {/* Summary footer */}
        <div style={{ marginTop: 24, padding: 20, background: T.card, borderRadius: T.radius, border: `1px solid ${T.border}`, boxShadow: T.shadow }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3 style={{ margin: 0, fontFamily: T.fontH, fontSize: 16, color: T.text }}>Workflow Summary</h3>
              <p style={{ margin: '4px 0 0', fontSize: 13, color: T.muted }}>
                {steps.length} steps across {steps.filter(s => s.status === 'healthy').length} active, {steps.filter(s => s.status === 'broken').length} broken, {steps.filter(s => s.status === 'disabled').length} disabled
              </p>
            </div>
            <div style={{ display: 'flex', gap: 16, fontFamily: T.fontM, fontSize: 12, color: T.muted }}>
              {Object.entries(channelMeta).map(([ch, meta]) => {
                const count = steps.filter(s => s.channels[ch]).length;
                return <span key={ch}>{meta.icon} {count}</span>;
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
