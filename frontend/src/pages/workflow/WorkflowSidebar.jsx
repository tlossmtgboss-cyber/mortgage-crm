import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { workflowGraphApi } from '../../services/workflowGraphApi';
import { toast } from '../../utils/toast';

export default function WorkflowSidebar({ workflows, onRefresh }) {
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState('');
  const [newColor, setNewColor] = useState('#3b82f6');

  const handleAdd = async () => {
    if (!newName.trim()) return;
    const key = newName.trim().toLowerCase().replace(/\s+/g, '_');
    try {
      await workflowGraphApi.createDefinition({ key, name: newName.trim(), color: newColor });
      setNewName('');
      setShowAdd(false);
      onRefresh();
      toast.success(`Workflow "${newName.trim()}" created`);
    } catch (err) {
      toast.error('Failed to create workflow');
    }
  };

  return (
    <div className="wf-sidebar">
      <div className="wf-sidebar-label">Workflows</div>
      {workflows.map(wf => (
        <NavLink
          key={wf.key}
          to={`/workflow/${wf.key}`}
          className={({ isActive }) => `wf-sidebar-item ${isActive ? 'active' : ''}`}
        >
          <span className="wf-sidebar-dot" style={{ background: wf.color }} />
          <span className="wf-sidebar-name">{wf.name}</span>
          <span className="wf-sidebar-count">{wf.lead_count}</span>
        </NavLink>
      ))}

      {showAdd ? (
        <div className="wf-sidebar-add-form">
          <input
            type="text"
            placeholder="Workflow name"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
            autoFocus
          />
          <input
            type="color"
            value={newColor}
            onChange={e => setNewColor(e.target.value)}
          />
          <div className="wf-sidebar-add-actions">
            <button onClick={handleAdd}>Add</button>
            <button onClick={() => setShowAdd(false)} className="cancel">Cancel</button>
          </div>
        </div>
      ) : (
        <button className="wf-sidebar-add-btn" onClick={() => setShowAdd(true)}>
          + Add Workflow
        </button>
      )}

      <NavLink to="/workflow/settings" className="wf-sidebar-settings">
        Settings
      </NavLink>
    </div>
  );
}
