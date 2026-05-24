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

const channelColors = {
  phone: { bg: '#DBEAFE', border: '#3B82F6', text: '#1E40AF', icon: '📞', label: 'Phone' },
  text: { bg: '#D1FAE5', border: '#10B981', text: '#065F46', icon: '💬', label: 'Text' },
  email: { bg: '#FEF3C7', border: '#F59E0B', text: '#92400E', icon: '✉️', label: 'Email' },
  referral_partner: { bg: '#FCE7F3', border: '#EC4899', text: '#9D174D', icon: '🤝', label: 'Partner' },
};

const roleMeta = {
  LO: { label: 'LO', color: '#1F3D2E', bg: '#E8F0EB' },
  Processor: { label: 'Proc', color: '#7C3AED', bg: '#EDE9FE' },
  Concierge: { label: 'Conc', color: '#B8924A', bg: '#FEF3C7' },
  AI: { label: 'AI', color: '#0EA5E9', bg: '#E0F2FE' },
};

const statusMeta = {
  healthy: { color: T.success, label: 'Healthy' },
  broken: { color: T.error, label: 'Broken' },
  disabled: { color: T.muted, label: 'Disabled' },
};

const columns = [
  { id: 'day1', label: 'Day 1', subtitle: 'First 24 Hours' },
  { id: 'day2', label: 'Day 2', subtitle: 'Follow-up' },
  { id: 'day3', label: 'Day 3', subtitle: 'Review' },
  { id: 'week1', label: 'Week 1', subtitle: 'Days 4-7' },
  { id: 'week2', label: 'Week 2', subtitle: 'Days 8-14' },
  { id: 'week3', label: 'Week 3', subtitle: 'Days 15-21' },
];

const initialCards = [
  { id: '1', columnId: 'day1', title: 'Welcome Call', channel: 'phone', description: 'Initial outreach call to confirm borrower intent, collect basic income and asset details, discuss loan options.', roles: ['LO'], status: 'healthy', time: 'AM' },
  { id: '2', columnId: 'day1', title: 'Intro Text Message', channel: 'text', description: 'Send welcome text with LO contact info and link to secure document upload portal.', roles: ['AI'], status: 'healthy', time: 'AM' },
  { id: '3', columnId: 'day1', title: 'Pre-Qual Checklist Email', channel: 'email', description: 'Automated email with full document checklist: pay stubs, W-2s, bank statements, photo ID.', roles: ['AI'], status: 'healthy', time: 'AM' },
  { id: '4', columnId: 'day2', title: 'Document Reminder', channel: 'text', description: 'Follow-up text if no documents received. Include direct upload link and deadline.', roles: ['Concierge'], status: 'healthy', time: 'AM' },
  { id: '5', columnId: 'day2', title: 'Missing Docs Email', channel: 'email', description: 'Detailed email listing specific missing documents with instructions for each.', roles: ['AI', 'Concierge'], status: 'healthy', time: 'PM' },
  { id: '6', columnId: 'day3', title: 'LO Review Call', channel: 'phone', description: 'Loan Officer reviews submitted documents with borrower, answers questions, clarifies discrepancies.', roles: ['LO'], status: 'healthy', time: 'PM' },
  { id: '7', columnId: 'day3', title: 'Partner Update', channel: 'referral_partner', description: 'Notify referral partner of application status and estimated timeline for pre-qual letter.', roles: ['LO'], status: 'healthy', time: 'PM' },
  { id: '8', columnId: 'week1', title: 'Credit Pull & Analysis', channel: 'email', description: 'Pull credit report, analyze scores, identify tradeline issues. Send summary to borrower.', roles: ['Processor', 'AI'], status: 'broken', time: 'AM' },
  { id: '9', columnId: 'week1', title: 'Pre-Qual Letter Draft', channel: 'email', description: 'Generate pre-qualification letter draft based on submitted docs and credit analysis.', roles: ['AI'], status: 'broken', time: 'PM' },
  { id: '10', columnId: 'week2', title: 'Two-Week Check-in', channel: 'phone', description: 'Check-in call to confirm borrower is actively searching. Discuss any rate changes or new programs.', roles: ['LO', 'Concierge'], status: 'healthy', time: 'PM' },
  { id: '11', columnId: 'week2', title: 'Status Text', channel: 'text', description: 'Quick text update on pre-qual status and any outstanding items needed.', roles: ['AI'], status: 'healthy', time: 'AM' },
  { id: '12', columnId: 'week2', title: 'Partner Progress Report', channel: 'referral_partner', description: 'Update referral partner with timeline and any buyer readiness concerns.', roles: ['LO'], status: 'healthy', time: 'PM' },
  { id: '13', columnId: 'week3', title: 'Final Summary Email', channel: 'email', description: 'Comprehensive pre-qualification summary with final letter, rate options, and next steps for full application.', roles: ['AI'], status: 'disabled', time: 'AM' },
  { id: '14', columnId: 'week3', title: 'Nurture Handoff', channel: 'text', description: 'If borrower non-responsive, send final outreach text before moving to nurture sequence.', roles: ['AI'], status: 'disabled', time: 'AM' },
];

let nextId = 200;

export default function WorkflowBuilderV2() {
  const navigate = useNavigate();
  const [cards, setCards] = useState(initialCards);
  const [editingCard, setEditingCard] = useState(null);
  const [movingCard, setMovingCard] = useState(null);
  const [previewRunning, setPreviewRunning] = useState(false);
  const [previewCol, setPreviewCol] = useState(-1);
  const [editingColLabel, setEditingColLabel] = useState(null);
  const [colLabels, setColLabels] = useState(Object.fromEntries(columns.map(c => [c.id, c.label])));

  const getColumnCards = (colId) => cards.filter(c => c.columnId === colId);

  const addCard = (colId) => {
    const newCard = {
      id: String(++nextId), columnId: colId, title: 'New Task', channel: 'email',
      description: '', roles: [], status: 'healthy', time: 'AM',
    };
    setCards(prev => [...prev, newCard]);
    setEditingCard(newCard);
  };

  const deleteCard = (id) => {
    setCards(prev => prev.filter(c => c.id !== id));
    if (editingCard?.id === id) setEditingCard(null);
  };

  const updateCard = (id, updates) => {
    setCards(prev => prev.map(c => c.id === id ? { ...c, ...updates } : c));
    if (editingCard?.id === id) setEditingCard(prev => ({ ...prev, ...updates }));
  };

  const moveCard = (cardId, targetColId) => {
    setCards(prev => prev.map(c => c.id === cardId ? { ...c, columnId: targetColId } : c));
    setMovingCard(null);
  };

  const runPreview = () => {
    setPreviewRunning(true);
    setPreviewCol(0);
    let i = 0;
    const interval = setInterval(() => {
      i++;
      if (i >= columns.length) {
        clearInterval(interval);
        setTimeout(() => { setPreviewRunning(false); setPreviewCol(-1); }, 1000);
      } else {
        setPreviewCol(i);
      }
    }, 1800);
  };

  const primaryChannel = (card) => {
    return channelColors[card.channel] || channelColors.email;
  };

  return (
    <div style={{ minHeight: '100vh', background: T.bg, fontFamily: T.fontB }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Geist+Mono&family=Inter:wght@400;500;600&display=swap');
        * { box-sizing: border-box; }
        .kb-card { transition: all 0.2s ease; cursor: pointer; }
        .kb-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); transform: translateY(-1px); }
        .kb-col { transition: background 0.3s ease; }
        .kb-add-btn { transition: all 0.15s ease; }
        .kb-add-btn:hover { background: ${T.primary} !important; color: white !important; }
        .kb-move-target { transition: all 0.15s ease; cursor: pointer; }
        .kb-move-target:hover { background: ${T.primary} !important; color: white !important; }
        .kb-preview-highlight { animation: colGlow 1.2s ease-in-out; }
        @keyframes colGlow { 0% { background: ${T.bg}; } 30% { background: #E8F0EB; } 100% { background: ${T.bg}; } }
        .kb-modal-overlay { animation: fadeIn 0.15s ease; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        textarea:focus, input:focus, select:focus { outline: 2px solid ${T.primary}; outline-offset: -1px; }
        .kb-col-header:hover .kb-col-edit { opacity: 1; }
        .kb-col-edit { opacity: 0; transition: opacity 0.15s; }
      `}</style>

      {/* Header */}
      <div style={{ background: T.card, borderBottom: `1px solid ${T.border}`, padding: '16px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: T.shadow }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.muted, fontSize: 14, fontFamily: T.fontB, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 18 }}>←</span> Back to Workflows
          </button>
          <div style={{ width: 1, height: 24, background: T.border }} />
          <h1 style={{ margin: 0, fontFamily: T.fontH, fontSize: 22, fontWeight: 700, color: T.text }}>Pre-Qualification Workflow</h1>
          <span style={{ fontSize: 11, fontFamily: T.fontM, background: '#EDE9FE', color: '#7C3AED', padding: '3px 10px', borderRadius: 20 }}>V2 — Card Kanban</span>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: T.muted, fontFamily: T.fontM }}>{cards.length} tasks</span>
          <button
            onClick={runPreview}
            disabled={previewRunning}
            style={{
              background: previewRunning ? T.muted : T.accent, color: 'white', border: 'none', borderRadius: 8,
              padding: '8px 20px', fontSize: 14, fontFamily: T.fontB, fontWeight: 600, cursor: previewRunning ? 'not-allowed' : 'pointer',
            }}
          >
            {previewRunning ? '⏳ Previewing...' : '▶ Preview Flow'}
          </button>
        </div>
      </div>

      {/* Board */}
      <div style={{ display: 'flex', gap: 16, padding: '24px 24px', overflowX: 'auto', minHeight: 'calc(100vh - 70px)' }}>
        {columns.map((col, colIdx) => {
          const colCards = getColumnCards(col.id);
          const isHighlighted = previewRunning && previewCol === colIdx;
          const isPast = previewRunning && previewCol > colIdx;

          return (
            <div
              key={col.id}
              className={`kb-col${isHighlighted ? ' kb-preview-highlight' : ''}`}
              style={{
                flex: '1 0 220px', maxWidth: 280, minWidth: 220,
                background: isHighlighted ? '#E8F0EB' : 'transparent',
                borderRadius: T.radius, padding: 8, transition: 'background 0.3s',
              }}
            >
              {/* Column header */}
              <div className="kb-col-header" style={{ padding: '8px 8px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  {editingColLabel === col.id ? (
                    <input
                      autoFocus
                      value={colLabels[col.id]}
                      onChange={(e) => setColLabels(prev => ({ ...prev, [col.id]: e.target.value }))}
                      onBlur={() => setEditingColLabel(null)}
                      onKeyDown={(e) => e.key === 'Enter' && setEditingColLabel(null)}
                      style={{ fontSize: 15, fontFamily: T.fontH, fontWeight: 700, color: T.text, border: `1px solid ${T.primary}`, borderRadius: 6, padding: '2px 6px', width: 100 }}
                    />
                  ) : (
                    <h3
                      style={{ margin: 0, fontSize: 15, fontFamily: T.fontH, fontWeight: 700, color: isPast ? T.primary : T.text, cursor: 'pointer' }}
                      onClick={() => setEditingColLabel(col.id)}
                      title="Click to rename"
                    >
                      {colLabels[col.id]}
                      <span className="kb-col-edit" style={{ fontSize: 10, marginLeft: 4, color: T.muted }}>✎</span>
                    </h3>
                  )}
                  <p style={{ margin: '2px 0 0', fontSize: 11, color: T.muted }}>{col.subtitle}</p>
                </div>
                <span style={{ fontSize: 11, fontFamily: T.fontM, color: T.muted, background: T.bg, padding: '2px 8px', borderRadius: 10 }}>{colCards.length}</span>
              </div>

              {/* Cards */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minHeight: 100 }}>
                {colCards.map(card => {
                  const ch = primaryChannel(card);
                  const sm = statusMeta[card.status];
                  const isMoving = movingCard === card.id;

                  return (
                    <div key={card.id} style={{ position: 'relative' }}>
                      <div
                        className="kb-card"
                        onClick={() => {
                          if (movingCard) return;
                          setEditingCard(card);
                        }}
                        style={{
                          background: T.card, borderRadius: 10,
                          borderLeft: `4px solid ${ch.border}`,
                          border: `1px solid ${isMoving ? T.primary : T.border}`,
                          borderLeftWidth: 4, borderLeftColor: ch.border,
                          boxShadow: T.shadow, padding: '12px 14px',
                          opacity: isMoving ? 0.7 : 1,
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                          <h4 style={{ margin: 0, fontSize: 13, fontWeight: 600, color: T.text }}>{card.title}</h4>
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: sm.color, flexShrink: 0, marginTop: 3 }} title={sm.label} />
                        </div>

                        <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
                          <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 8, background: ch.bg, color: ch.text, fontWeight: 600 }}>
                            {ch.icon} {ch.label}
                          </span>
                          <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 8, background: T.bg, color: T.muted, fontFamily: T.fontM }}>
                            {card.time}
                          </span>
                        </div>

                        <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                          {card.roles.map(r => (
                            <span key={r} style={{ fontSize: 9, padding: '1px 7px', borderRadius: 8, background: roleMeta[r].bg, color: roleMeta[r].color, fontWeight: 600 }}>
                              {roleMeta[r].label}
                            </span>
                          ))}
                        </div>

                        {/* Move button */}
                        <button
                          onClick={(e) => { e.stopPropagation(); setMovingCard(movingCard === card.id ? null : card.id); }}
                          style={{
                            position: 'absolute', top: 8, right: 8,
                            background: movingCard === card.id ? T.primary : 'transparent', color: movingCard === card.id ? 'white' : T.muted,
                            border: 'none', borderRadius: 4, padding: '2px 6px', fontSize: 11, cursor: 'pointer',
                          }}
                          title="Click to move to another column"
                        >
                          ↔
                        </button>
                      </div>

                      {/* Move targets */}
                      {isMoving && (
                        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10, background: T.card, borderRadius: 8, border: `1px solid ${T.border}`, boxShadow: '0 4px 12px rgba(0,0,0,0.12)', padding: 6, marginTop: 4 }}>
                          <p style={{ margin: '0 0 4px', fontSize: 10, color: T.muted, fontWeight: 600, textTransform: 'uppercase', padding: '0 4px' }}>Move to:</p>
                          {columns.filter(c => c.id !== col.id).map(tc => (
                            <button
                              key={tc.id}
                              className="kb-move-target"
                              onClick={(e) => { e.stopPropagation(); moveCard(card.id, tc.id); }}
                              style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 8px', border: 'none', background: 'transparent', borderRadius: 4, fontSize: 12, color: T.text, fontFamily: T.fontB }}
                            >
                              {colLabels[tc.id]}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Add card button */}
                <button
                  className="kb-add-btn"
                  onClick={() => addCard(col.id)}
                  style={{
                    width: '100%', padding: '10px', border: `2px dashed ${T.border}`, borderRadius: 10,
                    background: 'transparent', color: T.muted, fontSize: 13, cursor: 'pointer', fontFamily: T.fontB,
                  }}
                >
                  + Add Task
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Edit Modal */}
      {editingCard && (
        <div
          className="kb-modal-overlay"
          onClick={() => setEditingCard(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000, display: 'flex', justifyContent: 'flex-end' }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{ width: 440, maxWidth: '100%', background: T.card, height: '100%', overflowY: 'auto', boxShadow: '-4px 0 20px rgba(0,0,0,0.1)', padding: 28 }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
              <h2 style={{ margin: 0, fontFamily: T.fontH, fontSize: 20, color: T.text }}>Edit Task</h2>
              <button onClick={() => setEditingCard(null)} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: T.muted }}>×</button>
            </div>

            {/* Title */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Task Title</label>
              <input
                value={editingCard.title}
                onChange={e => { const v = e.target.value; updateCard(editingCard.id, { title: v }); }}
                style={{ width: '100%', marginTop: 4, padding: '10px 12px', border: `1px solid ${T.border}`, borderRadius: 8, fontSize: 14, fontFamily: T.fontB, color: T.text, background: T.bg }}
              />
            </div>

            {/* Description */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Description</label>
              <textarea
                value={editingCard.description}
                onChange={e => { const v = e.target.value; updateCard(editingCard.id, { description: v }); }}
                rows={4}
                style={{ width: '100%', marginTop: 4, padding: '10px 12px', border: `1px solid ${T.border}`, borderRadius: 8, fontSize: 13, fontFamily: T.fontB, color: T.text, resize: 'vertical', background: T.bg }}
              />
            </div>

            {/* Channel */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Channel</label>
              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                {Object.entries(channelColors).map(([ch, meta]) => (
                  <button
                    key={ch}
                    onClick={() => updateCard(editingCard.id, { channel: ch })}
                    style={{
                      flex: 1, padding: '8px 4px', borderRadius: 8, border: `2px solid ${editingCard.channel === ch ? meta.border : T.border}`,
                      background: editingCard.channel === ch ? meta.bg : T.bg, color: editingCard.channel === ch ? meta.text : T.muted,
                      fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: T.fontB, textAlign: 'center',
                    }}
                  >
                    {meta.icon}<br />{meta.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Roles */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Assigned Roles</label>
              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                {Object.entries(roleMeta).map(([role, meta]) => {
                  const active = editingCard.roles.includes(role);
                  return (
                    <button
                      key={role}
                      onClick={() => {
                        const roles = active ? editingCard.roles.filter(r => r !== role) : [...editingCard.roles, role];
                        updateCard(editingCard.id, { roles });
                      }}
                      style={{
                        padding: '8px 16px', borderRadius: 20, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: T.fontB,
                        background: active ? meta.bg : T.bg, color: active ? meta.color : T.muted,
                        border: `1.5px solid ${active ? meta.color : T.border}`,
                      }}
                    >
                      {meta.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Column (timing) */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Timing</label>
              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                <select
                  value={editingCard.columnId}
                  onChange={e => { const v = e.target.value; updateCard(editingCard.id, { columnId: v }); }}
                  style={{ flex: 1, padding: '10px 12px', border: `1px solid ${T.border}`, borderRadius: 8, fontSize: 14, fontFamily: T.fontB, color: T.text, background: T.bg }}
                >
                  {columns.map(c => <option key={c.id} value={c.id}>{colLabels[c.id]} — {c.subtitle}</option>)}
                </select>
                <select
                  value={editingCard.time}
                  onChange={e => { const v = e.target.value; updateCard(editingCard.id, { time: v }); }}
                  style={{ width: 80, padding: '10px 12px', border: `1px solid ${T.border}`, borderRadius: 8, fontSize: 14, fontFamily: T.fontB, color: T.text, background: T.bg }}
                >
                  <option value="AM">AM</option>
                  <option value="PM">PM</option>
                </select>
              </div>
            </div>

            {/* Status */}
            <div style={{ marginBottom: 24 }}>
              <label style={{ fontSize: 11, color: T.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Status</label>
              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                {Object.entries(statusMeta).map(([s, meta]) => (
                  <button
                    key={s}
                    onClick={() => updateCard(editingCard.id, { status: s })}
                    style={{
                      flex: 1, padding: '8px', borderRadius: 8, cursor: 'pointer', fontFamily: T.fontB, fontSize: 12, fontWeight: 600,
                      background: editingCard.status === s ? meta.color + '18' : T.bg,
                      color: editingCard.status === s ? meta.color : T.muted,
                      border: `1.5px solid ${editingCard.status === s ? meta.color : T.border}`,
                    }}
                  >
                    <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: meta.color, marginRight: 6 }} />
                    {meta.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: 12 }}>
              <button
                onClick={() => setEditingCard(null)}
                style={{ flex: 1, padding: '10px', borderRadius: 8, background: T.primary, color: 'white', border: 'none', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: T.fontB }}
              >
                Done
              </button>
              <button
                onClick={() => deleteCard(editingCard.id)}
                style={{ padding: '10px 20px', borderRadius: 8, background: `${T.error}0a`, color: T.error, border: `1px solid ${T.error}33`, fontSize: 14, cursor: 'pointer', fontFamily: T.fontB }}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Click-away dismiss for move targets */}
      {movingCard && (
        <div
          onClick={() => setMovingCard(null)}
          style={{ position: 'fixed', inset: 0, zIndex: 5 }}
        />
      )}
    </div>
  );
}
