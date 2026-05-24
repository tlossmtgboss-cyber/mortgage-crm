import React, { useState, useRef, useEffect, useCallback } from 'react';

// ── Theme ──────────────────────────────────────────────────────────────────────
const T = {
  pageBg: '#FAF7F1',
  cardBg: '#FFFFFF',
  primary: '#1F3D2E',
  accent: '#B8924A',
  border: '#ECE6D8',
  text: '#1A1F1B',
  muted: '#8B8A7E',
  success: '#2D7A52',
  error: '#9B2C2C',
  warning: '#B25F18',
  fontHeader: "'Fraunces', serif",
  fontBody: "'Geist', 'Inter', sans-serif",
  fontMono: "'Geist Mono', monospace",
  radius: '12px',
  shadow: '0 1px 3px rgba(0,0,0,0.06)',
  rowAlt: '#FDFBF7',
};

const CHANNELS = ['phone', 'text', 'email', 'referral_partner'];
const CHANNEL_ICONS = { phone: '📞', text: '📱', email: '✉️', referral_partner: '🤝' };
const ROLES = ['LO', 'Processor', 'Concierge', 'AI', 'Manager', 'System'];
const STATUSES = ['healthy', 'broken', 'disabled'];
const COLUMNS = [
  { key: '_select', label: '', width: 36 },
  { key: 'dayLabel', label: 'Day', width: 120 },
  { key: 'action', label: 'Action', width: 260 },
  { key: 'channels', label: 'Channels', width: 140 },
  { key: 'target', label: 'Target/Condition', width: 180 },
  { key: 'role', label: 'Assigned To', width: 110 },
  { key: 'template', label: 'Template', width: 160 },
  { key: 'status', label: 'Status', width: 90 },
  { key: 'timeOfDay', label: 'Time', width: 70 },
  { key: 'repeatWeekly', label: 'Repeat', width: 70 },
];

const statusColor = (s) => (s === 'healthy' ? T.success : s === 'broken' ? T.error : T.muted);

// ── Mock Data ──────────────────────────────────────────────────────────────────
const INITIAL_ROWS = [
  {
    id: 1,
    dayLabel: 'First 24 Hours',
    action: 'Welcome text + warm call attempt',
    channels: { phone: true, text: true, email: false, referral_partner: false },
    target: 'All new pre-qual leads',
    role: 'Concierge',
    template: 'welcome_prequal_v3',
    status: 'healthy',
    timeOfDay: 'AM',
    repeatWeekly: false,
    description: 'Send personalized welcome text and attempt a warm call within the first hour. Introduce yourself and confirm their interest in getting pre-qualified.',
  },
  {
    id: 2,
    dayLabel: 'Day 2',
    action: 'Follow-up call if no response',
    channels: { phone: true, text: false, email: false, referral_partner: false },
    target: 'No response to Day 1',
    role: 'LO',
    template: 'followup_call_script',
    status: 'healthy',
    timeOfDay: 'AM',
    repeatWeekly: false,
    description: 'Personal call from the loan officer. Leave voicemail with callback number. Mention current market rates as a hook.',
  },
  {
    id: 3,
    dayLabel: 'Day 3',
    action: 'Email pre-qual checklist + rate snapshot',
    channels: { phone: false, text: false, email: true, referral_partner: false },
    target: 'All active pre-qual leads',
    role: 'AI',
    template: 'prequal_checklist_email',
    status: 'healthy',
    timeOfDay: 'AM',
    repeatWeekly: false,
    description: 'Automated email with document checklist (pay stubs, W-2s, bank statements) and current rate snapshot for their estimated loan scenario.',
  },
  {
    id: 4,
    dayLabel: 'Day 7',
    action: 'Referral partner co-outreach',
    channels: { phone: false, text: true, email: true, referral_partner: true },
    target: 'Leads with referring agent',
    role: 'AI',
    template: 'referral_partner_nudge',
    status: 'broken',
    timeOfDay: 'PM',
    repeatWeekly: false,
    description: 'Alert the referring real estate agent that the lead hasn\'t responded. Ask them to re-engage. Send joint email showing LO + agent collaboration.',
  },
  {
    id: 5,
    dayLabel: 'Day 14',
    action: 'Weekly market update + soft CTA',
    channels: { phone: false, text: false, email: true, referral_partner: false },
    target: 'All non-converted leads',
    role: 'AI',
    template: 'weekly_market_update',
    status: 'healthy',
    timeOfDay: 'AM',
    repeatWeekly: true,
    description: 'Automated weekly email with personalized market updates, rate changes in their area, and a soft call-to-action to schedule a quick 15-minute consultation.',
  },
  {
    id: 6,
    dayLabel: 'Day 21',
    action: 'Final personal outreach or move to Nurture',
    channels: { phone: true, text: true, email: true, referral_partner: false },
    target: 'No engagement after 3 weeks',
    role: 'LO',
    template: 'final_outreach_v2',
    status: 'disabled',
    timeOfDay: 'PM',
    repeatWeekly: false,
    description: 'Last personal touchpoint from the LO. If no response after this, automatically transition lead to the long-term Nurture workflow for quarterly check-ins.',
  },
];

// ── Component ──────────────────────────────────────────────────────────────────
export default function WorkflowBuilderV5() {
  const [rows, setRows] = useState(INITIAL_ROWS);
  const [selectedRows, setSelectedRows] = useState(new Set());
  const [editingCell, setEditingCell] = useState(null); // { rowId, colKey }
  const [editValue, setEditValue] = useState('');
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState('asc');
  const [filterCol, setFilterCol] = useState(null);
  const [filterValue, setFilterValue] = useState('');
  const [contextMenu, setContextMenu] = useState(null); // { x, y, rowId }
  const [formulaContent, setFormulaContent] = useState('');
  const [selectedCell, setSelectedCell] = useState(null); // { rowId, colKey }
  const [showBulkBar, setShowBulkBar] = useState(false);
  const editRef = useRef(null);

  useEffect(() => {
    setShowBulkBar(selectedRows.size > 0);
  }, [selectedRows]);

  // Close context menu on outside click
  useEffect(() => {
    const handler = () => setContextMenu(null);
    if (contextMenu) {
      window.addEventListener('click', handler);
      return () => window.removeEventListener('click', handler);
    }
  }, [contextMenu]);

  // Focus edit input
  useEffect(() => {
    if (editRef.current) editRef.current.focus();
  }, [editingCell]);

  // ── Sorting ────────────────────────────────────────────────────────────────
  const sortedRows = React.useMemo(() => {
    let r = [...rows];
    if (filterCol && filterValue) {
      r = r.filter((row) => {
        const val = String(row[filterCol] || '').toLowerCase();
        return val.includes(filterValue.toLowerCase());
      });
    }
    if (sortCol) {
      r.sort((a, b) => {
        const av = String(a[sortCol] || '');
        const bv = String(b[sortCol] || '');
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      });
    }
    return r;
  }, [rows, sortCol, sortDir, filterCol, filterValue]);

  const handleSort = (colKey) => {
    if (colKey === '_select') return;
    if (sortCol === colKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(colKey);
      setSortDir('asc');
    }
  };

  // ── Cell Editing ───────────────────────────────────────────────────────────
  const startEdit = (rowId, colKey) => {
    if (colKey === '_select' || colKey === 'channels' || colKey === 'repeatWeekly') return;
    const row = rows.find((r) => r.id === rowId);
    setEditingCell({ rowId, colKey });
    setEditValue(String(row[colKey] || ''));
  };

  const commitEdit = () => {
    if (!editingCell) return;
    setRows((prev) =>
      prev.map((r) => (r.id === editingCell.rowId ? { ...r, [editingCell.colKey]: editValue } : r))
    );
    setEditingCell(null);
    setEditValue('');
  };

  const cancelEdit = () => {
    setEditingCell(null);
    setEditValue('');
  };

  const handleCellClick = (rowId, colKey) => {
    setSelectedCell({ rowId, colKey });
    const row = rows.find((r) => r.id === rowId);
    if (row) {
      const cellVal = colKey === 'channels'
        ? Object.entries(row.channels).filter(([, v]) => v).map(([k]) => k).join(', ')
        : String(row[colKey] || '');
      setFormulaContent(cellVal);
    }
  };

  // ── Row actions ────────────────────────────────────────────────────────────
  const toggleRowSelect = (id) => {
    setSelectedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    if (selectedRows.size === sortedRows.length) {
      setSelectedRows(new Set());
    } else {
      setSelectedRows(new Set(sortedRows.map((r) => r.id)));
    }
  };

  const handleContextMenu = (e, rowId) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, rowId });
  };

  const duplicateRow = (rowId) => {
    const row = rows.find((r) => r.id === rowId);
    if (!row) return;
    const newRow = { ...row, id: Date.now(), action: row.action + ' (copy)', channels: { ...row.channels } };
    const idx = rows.findIndex((r) => r.id === rowId);
    const newRows = [...rows];
    newRows.splice(idx + 1, 0, newRow);
    setRows(newRows);
  };

  const deleteRow = (rowId) => {
    setRows((prev) => prev.filter((r) => r.id !== rowId));
    setSelectedRows((prev) => {
      const next = new Set(prev);
      next.delete(rowId);
      return next;
    });
  };

  const moveRow = (rowId, dir) => {
    const idx = rows.findIndex((r) => r.id === rowId);
    if (idx === -1) return;
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= rows.length) return;
    const newRows = [...rows];
    [newRows[idx], newRows[newIdx]] = [newRows[newIdx], newRows[idx]];
    setRows(newRows);
  };

  const toggleChannel = (rowId, channel) => {
    setRows((prev) =>
      prev.map((r) =>
        r.id === rowId ? { ...r, channels: { ...r.channels, [channel]: !r.channels[channel] } } : r
      )
    );
  };

  const toggleRepeat = (rowId) => {
    setRows((prev) => prev.map((r) => (r.id === rowId ? { ...r, repeatWeekly: !r.repeatWeekly } : r)));
  };

  // ── Bulk actions ───────────────────────────────────────────────────────────
  const bulkDelete = () => {
    setRows((prev) => prev.filter((r) => !selectedRows.has(r.id)));
    setSelectedRows(new Set());
  };

  const bulkToggleStatus = (status) => {
    setRows((prev) => prev.map((r) => (selectedRows.has(r.id) ? { ...r, status } : r)));
  };

  const bulkDuplicate = () => {
    const newRows = [...rows];
    rows.forEach((r) => {
      if (selectedRows.has(r.id)) {
        const copy = { ...r, id: Date.now() + Math.random(), action: r.action + ' (copy)', channels: { ...r.channels } };
        newRows.push(copy);
      }
    });
    setRows(newRows);
    setSelectedRows(new Set());
  };

  // ── Quick-add ──────────────────────────────────────────────────────────────
  const [quickDay, setQuickDay] = useState('');
  const [quickAction, setQuickAction] = useState('');

  const addQuickRow = () => {
    if (!quickAction.trim()) return;
    const newRow = {
      id: Date.now(),
      dayLabel: quickDay || 'New Step',
      action: quickAction,
      channels: { phone: false, text: false, email: true, referral_partner: false },
      target: '',
      role: 'LO',
      template: '',
      status: 'healthy',
      timeOfDay: 'AM',
      repeatWeekly: false,
      description: quickAction,
    };
    setRows((prev) => [...prev, newRow]);
    setQuickDay('');
    setQuickAction('');
  };

  // ── Render Cell ────────────────────────────────────────────────────────────
  const renderCell = (row, col) => {
    const isEditing = editingCell?.rowId === row.id && editingCell?.colKey === col.key;
    const isSelected = selectedCell?.rowId === row.id && selectedCell?.colKey === col.key;

    if (col.key === '_select') {
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <input
            type="checkbox"
            checked={selectedRows.has(row.id)}
            onChange={() => toggleRowSelect(row.id)}
            style={{ accentColor: T.primary, cursor: 'pointer' }}
          />
        </div>
      );
    }

    if (col.key === 'channels') {
      return (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {CHANNELS.map((ch) => (
            <button
              key={ch}
              onClick={(e) => { e.stopPropagation(); toggleChannel(row.id, ch); }}
              title={ch.replace('_', ' ')}
              style={{
                width: 26,
                height: 26,
                borderRadius: 6,
                border: `1px solid ${row.channels[ch] ? T.primary : T.border}`,
                background: row.channels[ch] ? T.primary + '14' : 'transparent',
                cursor: 'pointer',
                fontSize: 13,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: 0,
              }}
            >
              {CHANNEL_ICONS[ch]}
            </button>
          ))}
        </div>
      );
    }

    if (col.key === 'status') {
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: statusColor(row.status),
              flexShrink: 0,
            }}
          />
          {isEditing ? (
            <select
              ref={editRef}
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onBlur={commitEdit}
              onKeyDown={(e) => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') cancelEdit(); }}
              style={{
                flex: 1,
                border: `1px solid ${T.accent}`,
                borderRadius: 4,
                padding: '2px 4px',
                fontSize: 12,
                fontFamily: T.fontBody,
                outline: 'none',
                background: T.cardBg,
              }}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          ) : (
            <span
              style={{
                fontSize: 11,
                textTransform: 'capitalize',
                color: statusColor(row.status),
                fontWeight: 600,
                fontFamily: T.fontMono,
              }}
            >
              {row.status}
            </span>
          )}
        </div>
      );
    }

    if (col.key === 'role') {
      if (isEditing) {
        return (
          <select
            ref={editRef}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') cancelEdit(); }}
            style={{
              width: '100%',
              border: `1px solid ${T.accent}`,
              borderRadius: 4,
              padding: '2px 4px',
              fontSize: 12,
              fontFamily: T.fontBody,
              outline: 'none',
              background: T.cardBg,
            }}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        );
      }
      return (
        <span
          style={{
            fontSize: 11,
            fontFamily: T.fontMono,
            padding: '2px 8px',
            borderRadius: 4,
            background: row.role === 'AI' ? '#EDE9FE' : row.role === 'LO' ? '#DBEAFE' : '#F3F4F6',
            color: row.role === 'AI' ? '#6366f1' : row.role === 'LO' ? '#2563EB' : T.text,
            fontWeight: 600,
          }}
        >
          {row.role}
        </span>
      );
    }

    if (col.key === 'repeatWeekly') {
      return (
        <button
          onClick={(e) => { e.stopPropagation(); toggleRepeat(row.id); }}
          style={{
            padding: '3px 8px',
            borderRadius: 6,
            border: `1px solid ${row.repeatWeekly ? T.success : T.border}`,
            background: row.repeatWeekly ? T.success + '14' : 'transparent',
            color: row.repeatWeekly ? T.success : T.muted,
            fontSize: 11,
            fontWeight: 600,
            cursor: 'pointer',
            fontFamily: T.fontMono,
          }}
        >
          {row.repeatWeekly ? 'Weekly' : 'Once'}
        </button>
      );
    }

    // Text cells
    if (isEditing) {
      return (
        <input
          ref={editRef}
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitEdit();
            if (e.key === 'Escape') cancelEdit();
            if (e.key === 'Tab') { e.preventDefault(); commitEdit(); }
          }}
          style={{
            width: '100%',
            border: `1px solid ${T.accent}`,
            borderRadius: 4,
            padding: '4px 6px',
            fontSize: 12,
            fontFamily: T.fontBody,
            outline: 'none',
            boxSizing: 'border-box',
            background: '#FFFEF8',
          }}
        />
      );
    }

    return (
      <span
        style={{
          fontSize: 12,
          color: col.key === 'dayLabel' ? T.primary : T.text,
          fontWeight: col.key === 'dayLabel' ? 600 : 400,
          fontFamily: col.key === 'dayLabel' || col.key === 'template' || col.key === 'timeOfDay' ? T.fontMono : T.fontBody,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          display: 'block',
        }}
      >
        {String(row[col.key] || '')}
      </span>
    );
  };

  // ── Main Render ────────────────────────────────────────────────────────────
  return (
    <div style={{ minHeight: '100vh', background: T.pageBg, fontFamily: T.fontBody, color: T.text }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 24px',
          borderBottom: `1px solid ${T.border}`,
          background: T.cardBg,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <a
            href="/workflows"
            onClick={(e) => { e.preventDefault(); window.history.back(); }}
            style={{ color: T.muted, textDecoration: 'none', fontSize: 14 }}
          >
            &larr; Back to Workflows
          </a>
          <div style={{ width: 1, height: 24, background: T.border }} />
          <h1 style={{ fontFamily: T.fontHeader, fontSize: 22, margin: 0, fontWeight: 600 }}>
            Pre-Qualification Workflow
          </h1>
          <span
            style={{
              fontSize: 11,
              fontFamily: T.fontMono,
              padding: '3px 8px',
              background: '#DBEAFE',
              color: '#2563EB',
              borderRadius: 6,
              fontWeight: 600,
            }}
          >
            V5 SPREADSHEET
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: T.muted, fontFamily: T.fontMono }}>
            {rows.length} steps
          </span>
          <button
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: `1px solid ${T.border}`,
              background: T.cardBg,
              color: T.text,
              fontFamily: T.fontBody,
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Export CSV
          </button>
          <button
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: 'none',
              background: T.primary,
              color: '#fff',
              fontFamily: T.fontBody,
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Save Workflow
          </button>
        </div>
      </div>

      {/* Formula Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 24px',
          borderBottom: `1px solid ${T.border}`,
          background: T.cardBg,
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontFamily: T.fontMono,
            color: T.muted,
            padding: '2px 8px',
            background: T.pageBg,
            borderRadius: 4,
            minWidth: 60,
            textAlign: 'center',
          }}
        >
          {selectedCell ? `${selectedCell.colKey.toUpperCase()}` : 'CELL'}
        </span>
        <span style={{ color: T.border }}>|</span>
        <div
          style={{
            flex: 1,
            fontSize: 12,
            fontFamily: T.fontMono,
            color: T.text,
            padding: '4px 8px',
            background: T.pageBg,
            borderRadius: 4,
            minHeight: 20,
            overflow: 'hidden',
            whiteSpace: 'nowrap',
            textOverflow: 'ellipsis',
          }}
        >
          {formulaContent || 'Select a cell to view its content'}
        </div>
        <div style={{ display: 'flex', gap: 4, marginLeft: 8 }}>
          <span style={{ fontSize: 10, color: T.muted, fontFamily: T.fontMono, padding: '2px 6px', background: T.pageBg, borderRadius: 3 }}>
            Double-click to edit
          </span>
          <span style={{ fontSize: 10, color: T.muted, fontFamily: T.fontMono, padding: '2px 6px', background: T.pageBg, borderRadius: 3 }}>
            ESC cancel
          </span>
          <span style={{ fontSize: 10, color: T.muted, fontFamily: T.fontMono, padding: '2px 6px', background: T.pageBg, borderRadius: 3 }}>
            Right-click menu
          </span>
        </div>
      </div>

      {/* Bulk Action Bar */}
      {showBulkBar && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '8px 24px',
            borderBottom: `1px solid ${T.accent}44`,
            background: T.accent + '0A',
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 600, color: T.accent }}>
            {selectedRows.size} row{selectedRows.size !== 1 ? 's' : ''} selected
          </span>
          <div style={{ width: 1, height: 20, background: T.accent + '33' }} />
          <button
            onClick={() => bulkToggleStatus('healthy')}
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              border: `1px solid ${T.success}44`,
              background: T.success + '14',
              color: T.success,
              fontSize: 11,
              fontWeight: 600,
              cursor: 'pointer',
              fontFamily: T.fontBody,
            }}
          >
            Enable
          </button>
          <button
            onClick={() => bulkToggleStatus('disabled')}
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              border: `1px solid ${T.muted}44`,
              background: T.muted + '14',
              color: T.muted,
              fontSize: 11,
              fontWeight: 600,
              cursor: 'pointer',
              fontFamily: T.fontBody,
            }}
          >
            Disable
          </button>
          <button
            onClick={bulkDuplicate}
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              border: `1px solid ${T.border}`,
              background: T.cardBg,
              color: T.text,
              fontSize: 11,
              fontWeight: 500,
              cursor: 'pointer',
              fontFamily: T.fontBody,
            }}
          >
            Duplicate
          </button>
          <button
            onClick={bulkDelete}
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              border: `1px solid ${T.error}44`,
              background: T.error + '0A',
              color: T.error,
              fontSize: 11,
              fontWeight: 600,
              cursor: 'pointer',
              fontFamily: T.fontBody,
            }}
          >
            Delete
          </button>
          <button
            onClick={() => setSelectedRows(new Set())}
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              border: `1px solid ${T.border}`,
              background: T.cardBg,
              color: T.muted,
              fontSize: 11,
              cursor: 'pointer',
              fontFamily: T.fontBody,
            }}
          >
            Clear Selection
          </button>
        </div>
      )}

      {/* Table */}
      <div style={{ padding: '16px 24px', overflowX: 'auto' }}>
        <div
          style={{
            background: T.cardBg,
            borderRadius: T.radius,
            border: `1px solid ${T.border}`,
            boxShadow: T.shadow,
            overflow: 'hidden',
          }}
        >
          {/* Header Row */}
          <div
            style={{
              display: 'flex',
              borderBottom: `2px solid ${T.border}`,
              background: T.pageBg,
            }}
          >
            {COLUMNS.map((col) => (
              <div
                key={col.key}
                onClick={() => handleSort(col.key)}
                style={{
                  width: col.width,
                  minWidth: col.width,
                  padding: '10px 12px',
                  fontSize: 11,
                  fontFamily: T.fontMono,
                  fontWeight: 700,
                  color: T.muted,
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                  cursor: col.key === '_select' ? 'default' : 'pointer',
                  userSelect: 'none',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  borderRight: `1px solid ${T.border}`,
                  position: 'relative',
                }}
              >
                {col.key === '_select' ? (
                  <input
                    type="checkbox"
                    checked={selectedRows.size === sortedRows.length && sortedRows.length > 0}
                    onChange={selectAll}
                    style={{ accentColor: T.primary, cursor: 'pointer' }}
                  />
                ) : (
                  <>
                    {col.label}
                    {sortCol === col.key && (
                      <span style={{ fontSize: 10 }}>{sortDir === 'asc' ? ' ▲' : ' ▼'}</span>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>

          {/* Data Rows */}
          {sortedRows.map((row, rowIdx) => (
            <div
              key={row.id}
              onContextMenu={(e) => handleContextMenu(e, row.id)}
              style={{
                display: 'flex',
                borderBottom: `1px solid ${T.border}`,
                background: selectedRows.has(row.id)
                  ? T.accent + '0C'
                  : rowIdx % 2 === 0
                  ? T.cardBg
                  : T.rowAlt,
                opacity: row.status === 'disabled' ? 0.55 : 1,
                transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => {
                if (!selectedRows.has(row.id)) e.currentTarget.style.background = T.accent + '08';
              }}
              onMouseLeave={(e) => {
                if (!selectedRows.has(row.id))
                  e.currentTarget.style.background = rowIdx % 2 === 0 ? T.cardBg : T.rowAlt;
              }}
            >
              {COLUMNS.map((col) => {
                const isSel = selectedCell?.rowId === row.id && selectedCell?.colKey === col.key;
                return (
                  <div
                    key={col.key}
                    onClick={() => handleCellClick(row.id, col.key)}
                    onDoubleClick={() => startEdit(row.id, col.key)}
                    style={{
                      width: col.width,
                      minWidth: col.width,
                      padding: '8px 12px',
                      borderRight: `1px solid ${T.border}`,
                      display: 'flex',
                      alignItems: 'center',
                      outline: isSel ? `2px solid ${T.accent}` : 'none',
                      outlineOffset: -2,
                      cursor: 'default',
                      boxSizing: 'border-box',
                    }}
                  >
                    {renderCell(row, col)}
                  </div>
                );
              })}
            </div>
          ))}

          {/* Quick-add row */}
          <div
            style={{
              display: 'flex',
              borderTop: `2px dashed ${T.border}`,
              background: T.pageBg,
            }}
          >
            <div style={{ width: 36, minWidth: 36, padding: '8px 12px', borderRight: `1px solid ${T.border}` }}>
              <span style={{ fontSize: 14, color: T.accent }}>+</span>
            </div>
            <div style={{ width: 120, minWidth: 120, padding: '6px 8px', borderRight: `1px solid ${T.border}` }}>
              <input
                value={quickDay}
                onChange={(e) => setQuickDay(e.target.value)}
                placeholder="Day..."
                style={{
                  width: '100%',
                  border: `1px solid ${T.border}`,
                  borderRadius: 4,
                  padding: '4px 6px',
                  fontSize: 12,
                  fontFamily: T.fontMono,
                  outline: 'none',
                  background: T.cardBg,
                  boxSizing: 'border-box',
                }}
              />
            </div>
            <div style={{ flex: 1, padding: '6px 8px', display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                value={quickAction}
                onChange={(e) => setQuickAction(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') addQuickRow(); }}
                placeholder="Add a new step... (press Enter)"
                style={{
                  flex: 1,
                  border: `1px solid ${T.border}`,
                  borderRadius: 4,
                  padding: '4px 8px',
                  fontSize: 12,
                  fontFamily: T.fontBody,
                  outline: 'none',
                  background: T.cardBg,
                }}
              />
              <button
                onClick={addQuickRow}
                style={{
                  padding: '4px 12px',
                  borderRadius: 6,
                  border: 'none',
                  background: T.primary,
                  color: '#fff',
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontFamily: T.fontBody,
                }}
              >
                Add
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Filter Popover */}
      {filterCol && (
        <div
          style={{
            position: 'fixed',
            top: 160,
            left: 200,
            background: T.cardBg,
            border: `1px solid ${T.border}`,
            borderRadius: 8,
            padding: 12,
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
            zIndex: 100,
          }}
        >
          <div style={{ fontSize: 11, fontFamily: T.fontMono, color: T.muted, marginBottom: 6 }}>
            Filter: {filterCol}
          </div>
          <input
            value={filterValue}
            onChange={(e) => setFilterValue(e.target.value)}
            placeholder="Type to filter..."
            style={{
              width: 180,
              padding: '6px 8px',
              border: `1px solid ${T.border}`,
              borderRadius: 4,
              fontSize: 12,
              fontFamily: T.fontBody,
              outline: 'none',
            }}
          />
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <button
              onClick={() => { setFilterCol(null); setFilterValue(''); }}
              style={{
                padding: '4px 10px',
                borderRadius: 4,
                border: `1px solid ${T.border}`,
                background: T.cardBg,
                fontSize: 11,
                cursor: 'pointer',
                fontFamily: T.fontBody,
              }}
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {/* Context Menu */}
      {contextMenu && (
        <div
          style={{
            position: 'fixed',
            top: contextMenu.y,
            left: contextMenu.x,
            background: T.cardBg,
            border: `1px solid ${T.border}`,
            borderRadius: 8,
            boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
            zIndex: 200,
            minWidth: 160,
            overflow: 'hidden',
          }}
        >
          {[
            { label: 'Edit Row', action: () => { startEdit(contextMenu.rowId, 'action'); setContextMenu(null); } },
            { label: 'Duplicate', action: () => { duplicateRow(contextMenu.rowId); setContextMenu(null); } },
            { label: 'Move Up', action: () => { moveRow(contextMenu.rowId, -1); setContextMenu(null); } },
            { label: 'Move Down', action: () => { moveRow(contextMenu.rowId, 1); setContextMenu(null); } },
            null, // divider
            { label: 'Toggle Status', action: () => {
              const row = rows.find((r) => r.id === contextMenu.rowId);
              if (row) {
                const next = row.status === 'healthy' ? 'disabled' : 'healthy';
                setRows((prev) => prev.map((r) => r.id === contextMenu.rowId ? { ...r, status: next } : r));
              }
              setContextMenu(null);
            }},
            null,
            { label: 'Delete', action: () => { deleteRow(contextMenu.rowId); setContextMenu(null); }, danger: true },
          ].map((item, i) =>
            item === null ? (
              <div key={`div-${i}`} style={{ height: 1, background: T.border }} />
            ) : (
              <button
                key={item.label}
                onClick={item.action}
                style={{
                  display: 'block',
                  width: '100%',
                  padding: '8px 14px',
                  border: 'none',
                  background: 'transparent',
                  textAlign: 'left',
                  fontSize: 12,
                  fontFamily: T.fontBody,
                  color: item.danger ? T.error : T.text,
                  cursor: 'pointer',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = T.pageBg)}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                {item.label}
              </button>
            )
          )}
        </div>
      )}
    </div>
  );
}
