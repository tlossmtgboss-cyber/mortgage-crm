import React, { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { workflowGraphApi } from '../../services/workflowGraphApi';
import { toast } from '../../utils/toast';
import './WorkflowSettings.css';

export default function WorkflowSettings() {
  const { workflows, onRefresh } = useOutletContext();
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const startEdit = (wf) => {
    setEditingId(wf.id);
    setEditForm({ name: wf.name, color: wf.color });
  };

  const saveEdit = async () => {
    try {
      await workflowGraphApi.updateDefinition(editingId, editForm);
      setEditingId(null);
      onRefresh();
      toast.success('Workflow updated');
    } catch (err) {
      toast.error('Failed to update workflow');
    }
  };

  const handleDelete = async (id) => {
    try {
      await workflowGraphApi.deleteDefinition(id);
      setDeleteConfirm(null);
      onRefresh();
      toast.success('Workflow removed');
    } catch (err) {
      toast.error('Failed to delete workflow');
    }
  };

  return (
    <div className="wf-settings">
      <h2>Workflow Settings</h2>
      <p className="wf-settings-subtitle">Manage your workflow definitions — add, rename, reorder, or remove.</p>

      <div className="wf-settings-list">
        {workflows.map((wf, i) => (
          <div key={wf.id || wf.key} className="wf-settings-row">
            <span className="wf-settings-dot" style={{ background: wf.color }} />
            {editingId === wf.id ? (
              <div className="wf-settings-edit">
                <input value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))} />
                <input type="color" value={editForm.color} onChange={e => setEditForm(f => ({ ...f, color: e.target.value }))} />
                <button onClick={saveEdit}>Save</button>
                <button className="cancel" onClick={() => setEditingId(null)}>Cancel</button>
              </div>
            ) : (
              <>
                <span className="wf-settings-name">{wf.name}</span>
                <span className="wf-settings-count">{wf.lead_count} leads</span>
                <button className="wf-settings-action" onClick={() => startEdit(wf)}>Edit</button>
                {deleteConfirm === wf.id ? (
                  <div className="wf-settings-confirm">
                    <span>Are you sure?</span>
                    <button className="danger" onClick={() => handleDelete(wf.id)}>Delete</button>
                    <button onClick={() => setDeleteConfirm(null)}>Cancel</button>
                  </div>
                ) : (
                  <button className="wf-settings-action danger" onClick={() => setDeleteConfirm(wf.id)}>Remove</button>
                )}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
