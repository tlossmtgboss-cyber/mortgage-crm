import React, { useState, useEffect, useRef, useCallback } from 'react';

// ── Mock Data ──────────────────────────────────────────────────────────────────
const INITIAL_NODES = [
  {
    id: 'start',
    type: 'start',
    label: 'Lead Enters Pre-Qual',
    x: 380,
    y: 30,
    channels: {},
    role: 'System',
    status: 'healthy',
    description: 'New lead enters the pre-qualification workflow.',
    dayLabel: 'Trigger',
    timeOfDay: '',
    repeatWeekly: false,
  },
  {
    id: 'step1',
    type: 'task',
    label: 'Welcome Text + Call',
    x: 380,
    y: 170,
    channels: { phone: true, text: true, email: false, referral_partner: false },
    role: 'Concierge',
    status: 'healthy',
    description: 'Send a personalized welcome text and attempt a warm call within the first hour. Introduce yourself and confirm their interest.',
    dayLabel: 'First 24 Hours',
    timeOfDay: 'AM',
    repeatWeekly: false,
  },
  {
    id: 'cond1',
    type: 'condition',
    label: 'Lead Responded?',
    x: 380,
    y: 320,
    channels: {},
    role: 'AI',
    status: 'healthy',
    description: 'Check if the lead responded to the initial outreach via any channel.',
    dayLabel: 'Day 1',
    timeOfDay: '',
    repeatWeekly: false,
  },
  {
    id: 'step2a',
    type: 'task',
    label: 'Schedule Consultation',
    x: 160,
    y: 470,
    channels: { phone: true, text: false, email: true, referral_partner: false },
    role: 'LO',
    status: 'healthy',
    description: 'Book a consultation call. Send calendar invite with Zoom link and pre-qual checklist.',
    dayLabel: 'Day 2',
    timeOfDay: 'AM',
    repeatWeekly: false,
  },
  {
    id: 'step2b',
    type: 'task',
    label: 'Follow-Up Sequence',
    x: 600,
    y: 470,
    channels: { phone: true, text: true, email: true, referral_partner: false },
    role: 'AI',
    status: 'healthy',
    description: 'Automated follow-up: text on Day 2, email on Day 3, call attempt on Day 4. Include market rate update and urgency messaging.',
    dayLabel: 'Day 2-4',
    timeOfDay: 'PM',
    repeatWeekly: false,
  },
  {
    id: 'step3',
    type: 'task',
    label: 'Credit Pull Authorization',
    x: 160,
    y: 620,
    channels: { phone: false, text: false, email: true, referral_partner: false },
    role: 'Processor',
    status: 'healthy',
    description: 'Send credit authorization form via secure email. Collect SSN and consent for tri-merge pull.',
    dayLabel: 'Day 3',
    timeOfDay: 'AM',
    repeatWeekly: false,
  },
  {
    id: 'cond2',
    type: 'condition',
    label: 'Still No Response?',
    x: 600,
    y: 620,
    channels: {},
    role: 'AI',
    status: 'broken',
    description: 'Check if lead has responded after the follow-up sequence.',
    dayLabel: 'Day 7',
    timeOfDay: '',
    repeatWeekly: false,
  },
  {
    id: 'step4',
    type: 'notification',
    label: 'Referral Partner Alert',
    x: 780,
    y: 770,
    channels: { phone: false, text: true, email: true, referral_partner: true },
    role: 'AI',
    status: 'healthy',
    description: 'Notify the referring agent/partner that the lead is unresponsive. Ask them to re-engage.',
    dayLabel: 'Day 7',
    timeOfDay: 'AM',
    repeatWeekly: false,
  },
  {
    id: 'step5',
    type: 'task',
    label: 'Weekly Check-In Email',
    x: 430,
    y: 770,
    channels: { phone: false, text: false, email: true, referral_partner: false },
    role: 'AI',
    status: 'healthy',
    description: 'Automated weekly email with market updates, rate changes, and a soft CTA to re-engage. Personalized with their loan scenario.',
    dayLabel: 'Day 14',
    timeOfDay: 'AM',
    repeatWeekly: true,
  },
  {
    id: 'step6',
    type: 'task',
    label: 'Final Outreach / Nurture',
    x: 380,
    y: 920,
    channels: { phone: true, text: true, email: true, referral_partner: false },
    role: 'LO',
    status: 'disabled',
    description: 'Last personal touchpoint. If no response, move lead to Nurture workflow for long-term drip.',
    dayLabel: 'Day 21',
    timeOfDay: 'PM',
    repeatWeekly: false,
  },
];

const INITIAL_EDGES = [
  { from: 'start', to: 'step1' },
  { from: 'step1', to: 'cond1' },
  { from: 'cond1', to: 'step2a', label: 'Yes' },
  { from: 'cond1', to: 'step2b', label: 'No' },
  { from: 'step2a', to: 'step3' },
  { from: 'step2b', to: 'cond2' },
  { from: 'step3', to: 'step5' },
  { from: 'cond2', to: 'step4', label: 'No Response' },
  { from: 'cond2', to: 'step5', label: 'Responded' },
  { from: 'step4', to: 'step5' },
  { from: 'step5', to: 'step6' },
];

const NODE_TYPES = [
  { type: 'task', label: 'Task', icon: '☑' },
  { type: 'condition', label: 'Condition', icon: '◇' },
  { type: 'delay', label: 'Delay', icon: '⏱' },
  { type: 'notification', label: 'Notification', icon: '✉' },
];

const ROLES = ['LO', 'Processor', 'Concierge', 'AI', 'Manager', 'System'];

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
};

const channelIcons = { phone: '📞', text: '📱', email: '✉️', referral_partner: '🤝' };

const statusColor = (s) => s === 'healthy' ? T.success : s === 'broken' ? T.error : T.muted;
const nodeColor = (type) =>
  type === 'start' ? T.primary :
  type === 'condition' ? T.accent :
  type === 'notification' ? '#6366f1' :
  type === 'delay' ? T.warning : T.cardBg;

// ── Helpers ────────────────────────────────────────────────────────────────────
function getNodeCenter(node, zoom) {
  const w = node.type === 'condition' ? 180 : 220;
  const h = node.type === 'condition' ? 70 : 90;
  return { x: node.x + w / 2, y: node.y + h / 2 };
}

// ── Component ──────────────────────────────────────────────────────────────────
export default function WorkflowBuilderV4() {
  const [nodes, setNodes] = useState(INITIAL_NODES);
  const [edges, setEdges] = useState(INITIAL_EDGES);
  const [selectedId, setSelectedId] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(null);
  const [simulating, setSimulating] = useState(false);
  const [simStep, setSimStep] = useState(0);
  const [simPath, setSimPath] = useState([]);
  const [addingNode, setAddingNode] = useState(null);
  const canvasRef = useRef(null);
  const panStart = useRef(null);

  const selected = nodes.find((n) => n.id === selectedId);

  // Build simulation path
  useEffect(() => {
    if (!simulating) return;
    const path = [];
    let current = 'start';
    const visited = new Set();
    while (current && !visited.has(current)) {
      visited.add(current);
      path.push(current);
      const outEdges = edges.filter((e) => e.from === current);
      if (outEdges.length === 0) break;
      // prefer "Yes" or first edge
      const next = outEdges.find((e) => e.label === 'Yes') || outEdges[0];
      current = next.to;
    }
    setSimPath(path);
    setSimStep(0);
  }, [simulating, edges]);

  useEffect(() => {
    if (!simulating || simPath.length === 0) return;
    if (simStep >= simPath.length) {
      setTimeout(() => setSimulating(false), 1200);
      return;
    }
    const timer = setTimeout(() => setSimStep((s) => s + 1), 1100);
    return () => clearTimeout(timer);
  }, [simulating, simStep, simPath]);

  // Node drag
  const handleNodeMouseDown = (e, nodeId) => {
    e.stopPropagation();
    const node = nodes.find((n) => n.id === nodeId);
    setDragging({ id: nodeId, offsetX: e.clientX / zoom - node.x, offsetY: e.clientY / zoom - node.y });
  };

  const handleMouseMove = useCallback(
    (e) => {
      if (dragging) {
        setNodes((prev) =>
          prev.map((n) =>
            n.id === dragging.id
              ? { ...n, x: e.clientX / zoom - dragging.offsetX - pan.x / zoom, y: e.clientY / zoom - dragging.offsetY - pan.y / zoom }
              : n
          )
        );
      }
      if (panStart.current) {
        setPan({
          x: e.clientX - panStart.current.startX + panStart.current.panX,
          y: e.clientY - panStart.current.startY + panStart.current.panY,
        });
      }
    },
    [dragging, zoom, pan]
  );

  const handleMouseUp = useCallback(() => {
    setDragging(null);
    panStart.current = null;
  }, []);

  useEffect(() => {
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  const handleCanvasMouseDown = (e) => {
    if (e.target === canvasRef.current || e.target.tagName === 'svg') {
      if (addingNode) {
        const rect = canvasRef.current.getBoundingClientRect();
        const x = (e.clientX - rect.left - pan.x) / zoom;
        const y = (e.clientY - rect.top - pan.y) / zoom;
        const newId = 'node_' + Date.now();
        setNodes((prev) => [
          ...prev,
          {
            id: newId,
            type: addingNode,
            label: addingNode === 'condition' ? 'New Condition' : addingNode === 'delay' ? 'Wait Period' : addingNode === 'notification' ? 'Send Notification' : 'New Task',
            x,
            y,
            channels: { phone: false, text: false, email: false, referral_partner: false },
            role: 'LO',
            status: 'healthy',
            description: '',
            dayLabel: '',
            timeOfDay: 'AM',
            repeatWeekly: false,
          },
        ]);
        setAddingNode(null);
        setSelectedId(newId);
      } else {
        setSelectedId(null);
        panStart.current = { startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y };
      }
    }
  };

  const updateNode = (field, value) => {
    setNodes((prev) => prev.map((n) => (n.id === selectedId ? { ...n, [field]: value } : n)));
  };

  const deleteNode = (id) => {
    setNodes((prev) => prev.filter((n) => n.id !== id));
    setEdges((prev) => prev.filter((e) => e.from !== id && e.to !== id));
    if (selectedId === id) setSelectedId(null);
  };

  // ── Minimap ──────────────────────────────────────────────────────────────────
  const renderMinimap = () => {
    const mmW = 160;
    const mmH = 120;
    const minX = Math.min(...nodes.map((n) => n.x)) - 50;
    const maxX = Math.max(...nodes.map((n) => n.x)) + 270;
    const minY = Math.min(...nodes.map((n) => n.y)) - 50;
    const maxY = Math.max(...nodes.map((n) => n.y)) + 140;
    const rangeX = maxX - minX || 1;
    const rangeY = maxY - minY || 1;
    const scale = Math.min(mmW / rangeX, mmH / rangeY);

    return (
      <div
        style={{
          position: 'absolute',
          bottom: 16,
          right: 16,
          width: mmW,
          height: mmH,
          background: 'rgba(255,255,255,0.92)',
          border: `1px solid ${T.border}`,
          borderRadius: 8,
          overflow: 'hidden',
          zIndex: 20,
        }}
      >
        <svg width={mmW} height={mmH}>
          {edges.map((e, i) => {
            const from = nodes.find((n) => n.id === e.from);
            const to = nodes.find((n) => n.id === e.to);
            if (!from || !to) return null;
            const f = getNodeCenter(from);
            const t = getNodeCenter(to);
            return (
              <line
                key={i}
                x1={(f.x - minX) * scale}
                y1={(f.y - minY) * scale}
                x2={(t.x - minX) * scale}
                y2={(t.y - minY) * scale}
                stroke={T.border}
                strokeWidth={1}
              />
            );
          })}
          {nodes.map((n) => (
            <rect
              key={n.id}
              x={(n.x - minX) * scale}
              y={(n.y - minY) * scale}
              width={12}
              height={8}
              rx={2}
              fill={n.id === selectedId ? T.accent : nodeColor(n.type)}
              opacity={0.8}
            />
          ))}
        </svg>
      </div>
    );
  };

  // ── Render ───────────────────────────────────────────────────────────────────
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
              background: '#EDE9FE',
              color: '#6366f1',
              borderRadius: 6,
              fontWeight: 600,
            }}
          >
            V4 VISUAL FLOW
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={() => setSimulating(!simulating)}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: 'none',
              background: simulating ? T.error : T.primary,
              color: '#fff',
              fontFamily: T.fontBody,
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {simulating ? 'Stop Simulation' : 'Run Simulation'}
          </button>
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
            Save Workflow
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '10px 24px',
          borderBottom: `1px solid ${T.border}`,
          background: T.cardBg,
        }}
      >
        <span style={{ fontSize: 12, color: T.muted, marginRight: 4 }}>Add Node:</span>
        {NODE_TYPES.map((nt) => (
          <button
            key={nt.type}
            onClick={() => setAddingNode(addingNode === nt.type ? null : nt.type)}
            style={{
              padding: '5px 12px',
              borderRadius: 6,
              border: `1px solid ${addingNode === nt.type ? T.primary : T.border}`,
              background: addingNode === nt.type ? T.primary : T.cardBg,
              color: addingNode === nt.type ? '#fff' : T.text,
              fontSize: 12,
              fontWeight: 500,
              cursor: 'pointer',
              fontFamily: T.fontBody,
            }}
          >
            {nt.icon} {nt.label}
          </button>
        ))}
        {addingNode && (
          <span style={{ fontSize: 12, color: T.accent, marginLeft: 8 }}>
            Click on canvas to place the {addingNode} node
          </span>
        )}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: T.muted, fontFamily: T.fontMono }}>
          {nodes.length} nodes &middot; {edges.length} connections
        </span>
        <div style={{ display: 'flex', gap: 4, marginLeft: 8 }}>
          <button
            onClick={() => setZoom((z) => Math.min(z + 0.15, 2))}
            style={{
              width: 28,
              height: 28,
              borderRadius: 6,
              border: `1px solid ${T.border}`,
              background: T.cardBg,
              fontSize: 16,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            +
          </button>
          <span
            style={{
              fontSize: 11,
              fontFamily: T.fontMono,
              minWidth: 40,
              textAlign: 'center',
              lineHeight: '28px',
              color: T.muted,
            }}
          >
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={() => setZoom((z) => Math.max(z - 0.15, 0.3))}
            style={{
              width: 28,
              height: 28,
              borderRadius: 6,
              border: `1px solid ${T.border}`,
              background: T.cardBg,
              fontSize: 16,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            &minus;
          </button>
          <button
            onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}
            style={{
              padding: '0 8px',
              height: 28,
              borderRadius: 6,
              border: `1px solid ${T.border}`,
              background: T.cardBg,
              fontSize: 11,
              cursor: 'pointer',
              fontFamily: T.fontMono,
              color: T.muted,
            }}
          >
            Reset
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', height: 'calc(100vh - 114px)', overflow: 'hidden' }}>
        {/* Canvas */}
        <div
          ref={canvasRef}
          onMouseDown={handleCanvasMouseDown}
          style={{
            flex: 1,
            position: 'relative',
            overflow: 'hidden',
            cursor: addingNode ? 'crosshair' : dragging ? 'grabbing' : 'default',
          }}
        >
          <div
            style={{
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
              transformOrigin: '0 0',
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
            }}
          >
            {/* SVG Edges */}
            <svg
              style={{ position: 'absolute', top: 0, left: 0, width: 2000, height: 1400, pointerEvents: 'none' }}
            >
              <defs>
                <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
                  <polygon points="0 0, 10 3.5, 0 7" fill={T.muted} />
                </marker>
                <marker id="arrowhead-active" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
                  <polygon points="0 0, 10 3.5, 0 7" fill={T.accent} />
                </marker>
              </defs>
              {edges.map((e, i) => {
                const from = nodes.find((n) => n.id === e.from);
                const to = nodes.find((n) => n.id === e.to);
                if (!from || !to) return null;
                const f = getNodeCenter(from);
                const t = getNodeCenter(to);
                const isSimActive =
                  simulating &&
                  simPath.indexOf(e.from) !== -1 &&
                  simPath.indexOf(e.to) !== -1 &&
                  simPath.indexOf(e.from) < simStep &&
                  simPath.indexOf(e.to) <= simStep;
                const midX = (f.x + t.x) / 2;
                const midY = (f.y + t.y) / 2;
                return (
                  <g key={i}>
                    <line
                      x1={f.x}
                      y1={f.y}
                      x2={t.x}
                      y2={t.y}
                      stroke={isSimActive ? T.accent : T.border}
                      strokeWidth={isSimActive ? 3 : 1.5}
                      markerEnd={isSimActive ? 'url(#arrowhead-active)' : 'url(#arrowhead)'}
                      style={{ transition: 'stroke 0.3s, stroke-width 0.3s' }}
                    />
                    {e.label && (
                      <text
                        x={midX}
                        y={midY - 6}
                        textAnchor="middle"
                        fill={isSimActive ? T.accent : T.muted}
                        fontSize={11}
                        fontFamily={T.fontBody}
                        fontWeight={500}
                      >
                        {e.label}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>

            {/* Nodes */}
            {nodes.map((node) => {
              const isSelected = selectedId === node.id;
              const isSimNode = simulating && simPath.indexOf(node.id) < simStep && simPath.indexOf(node.id) !== -1;
              const isSimCurrent = simulating && simPath[simStep] === node.id;
              const isCondition = node.type === 'condition';
              const isStart = node.type === 'start';
              const w = isCondition ? 180 : 220;
              const h = isCondition ? 70 : 90;

              return (
                <div
                  key={node.id}
                  onMouseDown={(e) => handleNodeMouseDown(e, node.id)}
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedId(node.id);
                  }}
                  style={{
                    position: 'absolute',
                    left: node.x,
                    top: node.y,
                    width: w,
                    minHeight: h,
                    background: isStart ? T.primary : T.cardBg,
                    border: `2px solid ${isSimCurrent ? T.accent : isSelected ? T.primary : isSimNode ? T.accent + '88' : T.border}`,
                    borderRadius: isCondition ? '12px' : T.radius,
                    padding: '10px 14px',
                    cursor: 'grab',
                    boxShadow: isSimCurrent
                      ? `0 0 0 4px ${T.accent}44, ${T.shadow}`
                      : isSelected
                      ? `0 0 0 3px ${T.primary}33, ${T.shadow}`
                      : T.shadow,
                    transform: isCondition ? 'rotate(0deg)' : undefined,
                    transition: 'box-shadow 0.2s, border-color 0.2s',
                    userSelect: 'none',
                    zIndex: isSelected ? 10 : 1,
                    opacity: node.status === 'disabled' ? 0.5 : 1,
                  }}
                >
                  {/* Status dot */}
                  <div
                    style={{
                      position: 'absolute',
                      top: 8,
                      right: 8,
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: statusColor(node.status),
                    }}
                  />
                  {/* Day label */}
                  <div
                    style={{
                      fontSize: 10,
                      fontFamily: T.fontMono,
                      color: isStart ? 'rgba(255,255,255,0.7)' : T.muted,
                      marginBottom: 4,
                    }}
                  >
                    {node.dayLabel}
                  </div>
                  {/* Label */}
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      color: isStart ? '#fff' : T.text,
                      marginBottom: 6,
                      lineHeight: 1.2,
                      paddingRight: 12,
                    }}
                  >
                    {node.label}
                  </div>
                  {/* Bottom row */}
                  {!isStart && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      {/* Channel icons */}
                      {Object.entries(node.channels)
                        .filter(([, v]) => v)
                        .map(([ch]) => (
                          <span key={ch} style={{ fontSize: 12 }} title={ch}>
                            {channelIcons[ch]}
                          </span>
                        ))}
                      {/* Role badge */}
                      <span
                        style={{
                          fontSize: 10,
                          fontFamily: T.fontMono,
                          padding: '1px 6px',
                          borderRadius: 4,
                          background: node.role === 'AI' ? '#EDE9FE' : node.role === 'LO' ? '#DBEAFE' : '#F3F4F6',
                          color: node.role === 'AI' ? '#6366f1' : node.role === 'LO' ? '#2563EB' : T.text,
                          fontWeight: 600,
                        }}
                      >
                        {node.role}
                      </span>
                      {node.repeatWeekly && (
                        <span style={{ fontSize: 10, color: T.accent }} title="Repeats weekly">
                          &#x21BB;
                        </span>
                      )}
                    </div>
                  )}
                  {/* Simulation pulse */}
                  {isSimCurrent && (
                    <div
                      style={{
                        position: 'absolute',
                        top: -6,
                        left: -6,
                        right: -6,
                        bottom: -6,
                        border: `2px solid ${T.accent}`,
                        borderRadius: isCondition ? 14 : 14,
                        animation: 'pulse 1s ease-in-out infinite',
                        pointerEvents: 'none',
                      }}
                    />
                  )}
                </div>
              );
            })}
          </div>

          {renderMinimap()}

          {/* Simulation overlay */}
          {simulating && (
            <div
              style={{
                position: 'absolute',
                top: 16,
                left: '50%',
                transform: 'translateX(-50%)',
                background: T.accent,
                color: '#fff',
                padding: '6px 16px',
                borderRadius: 20,
                fontSize: 12,
                fontWeight: 600,
                fontFamily: T.fontMono,
                zIndex: 30,
              }}
            >
              Simulating step {simStep + 1} / {simPath.length} &mdash;{' '}
              {simPath[simStep] ? nodes.find((n) => n.id === simPath[simStep])?.label : 'Complete'}
            </div>
          )}
        </div>

        {/* Side Panel */}
        {selected && (
          <div
            style={{
              width: 340,
              borderLeft: `1px solid ${T.border}`,
              background: T.cardBg,
              overflowY: 'auto',
              padding: 20,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 style={{ fontFamily: T.fontHeader, fontSize: 16, margin: 0 }}>Edit Node</h3>
              <button
                onClick={() => setSelectedId(null)}
                style={{ background: 'none', border: 'none', fontSize: 18, cursor: 'pointer', color: T.muted }}
              >
                &times;
              </button>
            </div>

            {/* Status */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, color: T.muted, fontFamily: T.fontMono, display: 'block', marginBottom: 4 }}>
                STATUS
              </label>
              <div style={{ display: 'flex', gap: 6 }}>
                {['healthy', 'broken', 'disabled'].map((s) => (
                  <button
                    key={s}
                    onClick={() => updateNode('status', s)}
                    style={{
                      padding: '4px 10px',
                      borderRadius: 6,
                      border: `1px solid ${selected.status === s ? statusColor(s) : T.border}`,
                      background: selected.status === s ? statusColor(s) + '18' : 'transparent',
                      color: selected.status === s ? statusColor(s) : T.muted,
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: 'pointer',
                      textTransform: 'capitalize',
                      fontFamily: T.fontBody,
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            {/* Label */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 11, color: T.muted, fontFamily: T.fontMono, display: 'block', marginBottom: 4 }}>
                LABEL
              </label>
              <input
                value={selected.label}
                onChange={(e) => updateNode('label', e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: 8,
                  border: `1px solid ${T.border}`,
                  fontFamily: T.fontBody,
                  fontSize: 13,
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Day Label */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 11, color: T.muted, fontFamily: T.fontMono, display: 'block', marginBottom: 4 }}>
                DAY / MILESTONE
              </label>
              <input
                value={selected.dayLabel}
                onChange={(e) => updateNode('dayLabel', e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: 8,
                  border: `1px solid ${T.border}`,
                  fontFamily: T.fontBody,
                  fontSize: 13,
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Description */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 11, color: T.muted, fontFamily: T.fontMono, display: 'block', marginBottom: 4 }}>
                DESCRIPTION
              </label>
              <textarea
                value={selected.description}
                onChange={(e) => updateNode('description', e.target.value)}
                rows={3}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: 8,
                  border: `1px solid ${T.border}`,
                  fontFamily: T.fontBody,
                  fontSize: 13,
                  outline: 'none',
                  resize: 'vertical',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Channels */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 11, color: T.muted, fontFamily: T.fontMono, display: 'block', marginBottom: 6 }}>
                CHANNELS
              </label>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {Object.entries(channelIcons).map(([ch, icon]) => (
                  <button
                    key={ch}
                    onClick={() => updateNode('channels', { ...selected.channels, [ch]: !selected.channels[ch] })}
                    style={{
                      padding: '5px 10px',
                      borderRadius: 6,
                      border: `1px solid ${selected.channels[ch] ? T.primary : T.border}`,
                      background: selected.channels[ch] ? T.primary + '14' : 'transparent',
                      cursor: 'pointer',
                      fontSize: 12,
                      fontFamily: T.fontBody,
                      color: selected.channels[ch] ? T.primary : T.muted,
                      fontWeight: 500,
                    }}
                  >
                    {icon} {ch.replace('_', ' ')}
                  </button>
                ))}
              </div>
            </div>

            {/* Role */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 11, color: T.muted, fontFamily: T.fontMono, display: 'block', marginBottom: 4 }}>
                ASSIGNED ROLE
              </label>
              <select
                value={selected.role}
                onChange={(e) => updateNode('role', e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: 8,
                  border: `1px solid ${T.border}`,
                  fontFamily: T.fontBody,
                  fontSize: 13,
                  outline: 'none',
                  background: T.cardBg,
                  boxSizing: 'border-box',
                }}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>

            {/* Time of Day */}
            <div style={{ marginBottom: 14, display: 'flex', gap: 12 }}>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: 11, color: T.muted, fontFamily: T.fontMono, display: 'block', marginBottom: 4 }}>
                  TIME
                </label>
                <select
                  value={selected.timeOfDay}
                  onChange={(e) => updateNode('timeOfDay', e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 8,
                    border: `1px solid ${T.border}`,
                    fontFamily: T.fontBody,
                    fontSize: 13,
                    outline: 'none',
                    background: T.cardBg,
                    boxSizing: 'border-box',
                  }}
                >
                  <option value="">Any</option>
                  <option value="AM">Morning (AM)</option>
                  <option value="PM">Afternoon (PM)</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: 11, color: T.muted, fontFamily: T.fontMono, display: 'block', marginBottom: 4 }}>
                  REPEAT
                </label>
                <button
                  onClick={() => updateNode('repeatWeekly', !selected.repeatWeekly)}
                  style={{
                    padding: '8px 14px',
                    borderRadius: 8,
                    border: `1px solid ${selected.repeatWeekly ? T.success : T.border}`,
                    background: selected.repeatWeekly ? T.success + '14' : 'transparent',
                    color: selected.repeatWeekly ? T.success : T.muted,
                    cursor: 'pointer',
                    fontSize: 12,
                    fontWeight: 600,
                    fontFamily: T.fontBody,
                  }}
                >
                  {selected.repeatWeekly ? 'Weekly' : 'Once'}
                </button>
              </div>
            </div>

            {/* Delete */}
            {selected.type !== 'start' && (
              <button
                onClick={() => deleteNode(selected.id)}
                style={{
                  width: '100%',
                  padding: '8px 0',
                  borderRadius: 8,
                  border: `1px solid ${T.error}33`,
                  background: T.error + '0A',
                  color: T.error,
                  fontFamily: T.fontBody,
                  fontSize: 13,
                  fontWeight: 500,
                  cursor: 'pointer',
                  marginTop: 8,
                }}
              >
                Delete Node
              </button>
            )}
          </div>
        )}
      </div>

      {/* Pulse animation */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}
