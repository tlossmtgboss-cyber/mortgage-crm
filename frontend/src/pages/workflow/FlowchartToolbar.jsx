import React from 'react';

const NODE_TYPES = [
  { type: 'task', label: 'Task', icon: '☑' },
  { type: 'condition', label: 'Condition', icon: '◇' },
  { type: 'delay', label: 'Delay', icon: '⏱' },
  { type: 'notification', label: 'Notify', icon: '✉' },
  { type: 'end', label: 'End', icon: '⏹' },
];

export default function FlowchartToolbar({
  workflowName,
  totalLeads,
  zoom,
  onZoomIn,
  onZoomOut,
  onZoomReset,
  placingNodeType,
  onSetPlacingNodeType,
  simulating,
  onSimulate,
}) {
  return (
    <div className="wf-toolbar">
      <div className="wf-toolbar-title">
        <h2>{workflowName}</h2>
        {totalLeads > 0 && <span className="wf-toolbar-count">{totalLeads} leads</span>}
      </div>

      <div className="wf-toolbar-actions">
        <div className="wf-toolbar-group">
          {NODE_TYPES.map(nt => (
            <button
              key={nt.type}
              className={`wf-toolbar-btn ${placingNodeType === nt.type ? 'active' : ''}`}
              onClick={() => onSetPlacingNodeType(placingNodeType === nt.type ? null : nt.type)}
              title={`Add ${nt.label}`}
            >
              <span>{nt.icon}</span> {nt.label}
            </button>
          ))}
        </div>

        <div className="wf-toolbar-divider" />

        <div className="wf-toolbar-group">
          <button className="wf-toolbar-btn" onClick={onZoomOut} title="Zoom out">−</button>
          <span className="wf-toolbar-zoom">{Math.round(zoom * 100)}%</span>
          <button className="wf-toolbar-btn" onClick={onZoomIn} title="Zoom in">+</button>
          <button className="wf-toolbar-btn" onClick={onZoomReset} title="Reset zoom">Reset</button>
        </div>

        <div className="wf-toolbar-divider" />

        <button
          className={`wf-toolbar-btn simulate ${simulating ? 'active' : ''}`}
          onClick={onSimulate}
        >
          {simulating ? 'Stop' : '▶ Simulate'}
        </button>
      </div>
    </div>
  );
}
