import React, { useState, useRef, useCallback, useEffect } from 'react';
import './FlowchartCanvas.css';

const NODE_TYPES = {
  start: { icon: '▶', color: 'var(--bt-primary, #1F3D2E)' },
  task: { icon: '☑', color: 'var(--bt-bg-surface, #FFFFFF)', border: 'var(--bt-border, #ECE6D8)' },
  condition: { icon: '◇', color: '#B8924A15', border: '#B8924A' },
  delay: { icon: '⏱', color: '#B25F1815', border: '#B25F18' },
  notification: { icon: '✉', color: '#6366f115', border: '#6366f1' },
  end: { icon: '⏹', color: '#9B2C2C', border: '#9B2C2C' },
};

const CHANNEL_ICONS = { phone: '📞', text: '📱', email: '✉️', referral_partner: '🤝' };

function getNodeSize(type) {
  return type === 'condition' ? { w: 180, h: 70 } : { w: 220, h: 90 };
}

function getNodeCenter(node) {
  const { w, h } = getNodeSize(node.type);
  return { x: node.x + w / 2, y: node.y + h / 2 };
}

function getNodeBottom(node) {
  const { w, h } = getNodeSize(node.type);
  return { x: node.x + w / 2, y: node.y + h };
}

function getNodeTop(node) {
  const { w } = getNodeSize(node.type);
  return { x: node.x + w / 2, y: node.y };
}

function bezierPath(from, to) {
  const dy = to.y - from.y;
  const cp = Math.max(Math.abs(dy) * 0.5, 40);
  return `M${from.x},${from.y} C${from.x},${from.y + cp} ${to.x},${to.y - cp} ${to.x},${to.y}`;
}

export default function FlowchartCanvas({
  nodes,
  edges,
  selectedId,
  onNodeSelect,
  onNodeDrag,
  onCanvasClick,
  placingNodeType,
  onPlaceNode,
  onEdgeCreate,
  zoom = 1,
  onZoomChange,
}) {
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(null);
  const [edgeDraft, setEdgeDraft] = useState(null);
  const canvasRef = useRef(null);
  const panStart = useRef(null);
  const mousePos = useRef({ x: 0, y: 0 });

  const handleWheel = useCallback((e) => {
    e.preventDefault();
    if (onZoomChange) {
      onZoomChange(z => Math.max(0.3, Math.min(2, z - e.deltaY * 0.001)));
    }
  }, [onZoomChange]);

  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, [handleWheel]);

  const canvasCoords = useCallback((clientX, clientY) => {
    const rect = canvasRef.current.getBoundingClientRect();
    return {
      x: (clientX - rect.left - pan.x) / zoom,
      y: (clientY - rect.top - pan.y) / zoom,
    };
  }, [pan, zoom]);

  const handleCanvasMouseDown = (e) => {
    if (e.target === canvasRef.current || e.target.closest('.wf-canvas-svg')) {
      if (placingNodeType) {
        onPlaceNode(canvasCoords(e.clientX, e.clientY));
        return;
      }
      panStart.current = { startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y };
      onCanvasClick();
    }
  };

  const handleMouseMove = useCallback((e) => {
    mousePos.current = { x: e.clientX, y: e.clientY };

    if (dragging) {
      const coords = canvasCoords(e.clientX, e.clientY);
      onNodeDrag(dragging.id, coords.x - dragging.offsetX, coords.y - dragging.offsetY);
    }
    if (edgeDraft) {
      const coords = canvasCoords(e.clientX, e.clientY);
      setEdgeDraft(prev => prev ? { ...prev, toX: coords.x, toY: coords.y } : null);
    }
    if (panStart.current) {
      setPan({
        x: e.clientX - panStart.current.startX + panStart.current.panX,
        y: e.clientY - panStart.current.startY + panStart.current.panY,
      });
    }
  }, [dragging, edgeDraft, canvasCoords, onNodeDrag]);

  const handleMouseUp = useCallback((e) => {
    if (edgeDraft) {
      const coords = canvasCoords(e.clientX, e.clientY);
      const target = nodes.find(n => {
        const { w, h } = getNodeSize(n.type);
        return n.id !== edgeDraft.fromId &&
          coords.x >= n.x && coords.x <= n.x + w &&
          coords.y >= n.y && coords.y <= n.y + h;
      });
      if (target && onEdgeCreate) {
        onEdgeCreate(edgeDraft.fromId, target.id);
      }
      setEdgeDraft(null);
    }
    setDragging(null);
    panStart.current = null;
  }, [edgeDraft, nodes, onEdgeCreate, canvasCoords]);

  useEffect(() => {
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  const handleNodeMouseDown = (e, nodeId) => {
    e.stopPropagation();
    const node = nodes.find(n => n.id === nodeId);
    const coords = canvasCoords(e.clientX, e.clientY);
    setDragging({
      id: nodeId,
      offsetX: coords.x - node.x,
      offsetY: coords.y - node.y,
    });
    onNodeSelect(nodeId);
  };

  const handlePortMouseDown = (e, nodeId) => {
    e.stopPropagation();
    const node = nodes.find(n => n.id === nodeId);
    const bottom = getNodeBottom(node);
    const coords = canvasCoords(e.clientX, e.clientY);
    setEdgeDraft({ fromId: nodeId, fromX: bottom.x, fromY: bottom.y, toX: coords.x, toY: coords.y });
  };

  const statusColor = (s) =>
    s === 'healthy' ? 'var(--bt-success, #2D7A52)' :
    s === 'broken' ? 'var(--bt-error, #9B2C2C)' :
    'var(--bt-text-muted, #8B8A7E)';

  return (
    <div
      className="wf-canvas"
      ref={canvasRef}
      onMouseDown={handleCanvasMouseDown}
      style={{ cursor: placingNodeType ? 'crosshair' : edgeDraft ? 'grabbing' : 'default' }}
    >
      <div
        className="wf-canvas-inner"
        style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: '0 0' }}
      >
        {/* SVG edges */}
        <svg className="wf-canvas-svg" style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
          <defs>
            <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="var(--bt-text-muted, #8B8A7E)" />
            </marker>
          </defs>
          {edges.map(edge => {
            const fromNode = nodes.find(n => n.id === edge.from_node_id);
            const toNode = nodes.find(n => n.id === edge.to_node_id);
            if (!fromNode || !toNode) return null;
            const from = getNodeBottom(fromNode);
            const to = getNodeTop(toNode);
            return (
              <g key={edge.id}>
                <path
                  d={bezierPath(from, to)}
                  fill="none"
                  stroke="var(--bt-border-strong, #D8D0BD)"
                  strokeWidth={2}
                  markerEnd="url(#arrowhead)"
                />
                {edge.label && (
                  <text
                    x={(from.x + to.x) / 2}
                    y={(from.y + to.y) / 2 - 8}
                    textAnchor="middle"
                    fill="var(--bt-text-muted, #8B8A7E)"
                    fontSize={11}
                    fontFamily="var(--bt-font-body, 'Inter', sans-serif)"
                  >
                    {edge.label}
                  </text>
                )}
              </g>
            );
          })}
          {/* Draft edge while dragging */}
          {edgeDraft && (
            <path
              d={bezierPath(
                { x: edgeDraft.fromX, y: edgeDraft.fromY },
                { x: edgeDraft.toX, y: edgeDraft.toY }
              )}
              fill="none"
              stroke="var(--bt-accent, #B8924A)"
              strokeWidth={2}
              strokeDasharray="6 4"
              markerEnd="url(#arrowhead)"
            />
          )}
        </svg>

        {/* HTML nodes */}
        {nodes.map(node => {
          const { w, h } = getNodeSize(node.type);
          const typeConfig = NODE_TYPES[node.type] || NODE_TYPES.task;
          const isSelected = selectedId === node.id;
          const channels = node.channels || {};
          const activeChannels = Object.entries(channels).filter(([, v]) => v);

          return (
            <div
              key={node.id}
              className={`wf-node wf-node-${node.type} ${isSelected ? 'selected' : ''}`}
              style={{
                transform: `translate(${node.x}px, ${node.y}px)`,
                width: w,
                borderColor: isSelected ? 'var(--bt-primary, #1F3D2E)' : (typeConfig.border || typeConfig.color),
                background: node.type === 'start' || node.type === 'end' ? typeConfig.color : (typeConfig.color || 'white'),
              }}
              onMouseDown={(e) => handleNodeMouseDown(e, node.id)}
            >
              {/* Input port (top) */}
              {node.type !== 'start' && (
                <div className="wf-port wf-port-in" />
              )}

              <div className="wf-node-header">
                <span className={`wf-node-label ${node.type === 'start' || node.type === 'end' ? 'light' : ''}`}>
                  {node.label}
                </span>
                {node.lead_count > 0 && (
                  <span className="wf-node-badge">{node.lead_count} leads</span>
                )}
              </div>
              {node.type !== 'start' && node.type !== 'end' && (
                <>
                  <div className="wf-node-meta">
                    {node.day_label}{node.time_of_day ? ` · ${node.time_of_day}` : ''}{node.role ? ` · ${node.role}` : ''}
                  </div>
                  <div className="wf-node-footer">
                    <div className="wf-node-channels">
                      {activeChannels.map(([ch]) => (
                        <span key={ch} className="wf-node-channel">{CHANNEL_ICONS[ch]}</span>
                      ))}
                    </div>
                    <span className="wf-node-status" style={{ background: statusColor(node.status) }} />
                  </div>
                </>
              )}

              {/* Output port (bottom) — drag to create edge */}
              {node.type !== 'end' && (
                <div
                  className="wf-port wf-port-out"
                  onMouseDown={(e) => handlePortMouseDown(e, node.id)}
                  title="Drag to connect"
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
