/**
 * AppointmentTypesSection - Calendar Settings
 *
 * Handles listing, creating, editing, reordering, and deleting appointment types.
 */
import React, { useState } from 'react';
import { calendarSettingsAPI } from '../../services/api.js';
import { toast } from '../../utils/toast';
import AIGenerateButton from '../../components/common/AIGenerateButton.js';

const DEFAULT_COLORS = ['#218D8D', '#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#ef4444', '#6366f1'];

function EditTypeForm({ type, onSave, onCancel }) {
  const [form, setForm] = useState({
    type_name: type.type_name || '',
    description: type.description || '',
    duration_minutes: type.duration_minutes || 30,
    color: type.color || '#218D8D',
    is_public: type.is_public !== false,
  });

  return (
    <div className="edit-type-form">
      <div className="form-grid">
        <div className="form-field">
          <label>Name</label>
          <input
            type="text"
            value={form.type_name}
            onChange={(e) => setForm(prev => ({ ...prev, type_name: e.target.value }))}
          />
        </div>
        <div className="form-field">
          <label>Duration</label>
          <select
            value={form.duration_minutes}
            onChange={(e) => setForm(prev => ({ ...prev, duration_minutes: parseInt(e.target.value) }))}
          >
            <option value={15}>15 min</option>
            <option value={30}>30 min</option>
            <option value={45}>45 min</option>
            <option value={60}>60 min</option>
            <option value={90}>90 min</option>
          </select>
        </div>
        <div className="form-field full-width">
          <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            Description
            <AIGenerateButton
              fieldType="appointment_description"
              context={{ name: form.type_name, duration: `${form.duration_minutes} minutes` }}
              currentValue={form.description}
              onGenerated={(text) => setForm(prev => ({ ...prev, description: text }))}
            />
          </label>
          <textarea
            value={form.description}
            onChange={(e) => setForm(prev => ({ ...prev, description: e.target.value }))}
            rows={2}
          />
        </div>
        <div className="form-field">
          <label>Color</label>
          <div className="color-picker">
            {DEFAULT_COLORS.map(c => (
              <button
                key={c}
                type="button"
                className={`color-swatch ${form.color === c ? 'selected' : ''}`}
                style={{ backgroundColor: c }}
                onClick={() => setForm(prev => ({ ...prev, color: c }))}
                aria-label={`Color ${c}`}
              />
            ))}
          </div>
        </div>
        <div className="form-field">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={form.is_public}
              onChange={(e) => setForm(prev => ({ ...prev, is_public: e.target.checked }))}
            />
            Public
          </label>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn-secondary btn-sm" onClick={onCancel}>Cancel</button>
        <button
          className="btn-primary btn-sm"
          disabled={!form.type_name.trim()}
          onClick={() => onSave(form)}
        >
          Save
        </button>
      </div>
    </div>
  );
}

export default function AppointmentTypesSection({
  appointmentTypes,
  setAppointmentTypes,
  loading,
  loadTabData,
}) {
  const [editingType, setEditingType] = useState(null);
  const [showNewTypeForm, setShowNewTypeForm] = useState(false);
  const [newType, setNewType] = useState({
    type_name: '', description: '', duration_minutes: 30, color: '#218D8D', icon: 'fa-calendar', is_public: true,
  });

  const handleCreateType = async () => {
    try {
      await calendarSettingsAPI.createAppointmentType(newType);
      toast.success('Appointment type created');
      setShowNewTypeForm(false);
      setNewType({ type_name: '', description: '', duration_minutes: 30, color: '#218D8D', icon: 'fa-calendar', is_public: true });
      loadTabData('appointment-types');
    } catch (err) {
      toast.error('Failed to create appointment type');
    }
  };

  const handleUpdateType = async (id, data) => {
    try {
      await calendarSettingsAPI.updateAppointmentType(id, data);
      toast.success('Appointment type updated');
      setEditingType(null);
      loadTabData('appointment-types');
    } catch (err) {
      toast.error('Failed to update appointment type');
    }
  };

  const handleDeleteType = async (id) => {
    if (!window.confirm('Remove this appointment type?')) return;
    try {
      await calendarSettingsAPI.deleteAppointmentType(id);
      toast.success('Appointment type removed');
      loadTabData('appointment-types');
    } catch (err) {
      toast.error('Failed to remove appointment type');
    }
  };

  const handleMoveType = async (index, direction) => {
    const newTypes = [...appointmentTypes];
    const swapIdx = index + direction;
    if (swapIdx < 0 || swapIdx >= newTypes.length) return;
    [newTypes[index], newTypes[swapIdx]] = [newTypes[swapIdx], newTypes[index]];
    setAppointmentTypes(newTypes);
    try {
      await calendarSettingsAPI.reorderAppointmentTypes(newTypes.map(t => t.id));
    } catch (err) {
      toast.error('Failed to reorder');
      loadTabData('appointment-types');
    }
  };

  return (
    <section className="cal-settings-section" role="tabpanel" id="panel-appointment-types" aria-labelledby="calnav-appointment-types">
      <div className="section-header-row">
        <div>
          <h2>Appointment Types</h2>
          <p className="section-description">Define the types of meetings clients can book.</p>
        </div>
        <button
          className="btn-primary btn-sm"
          onClick={() => setShowNewTypeForm(true)}
        >
          <i className="fas fa-plus"></i> Add Type
        </button>
      </div>

      {showNewTypeForm && (
        <div className="type-form-card">
          <h3>New Appointment Type</h3>
          <div className="form-grid">
            <div className="form-field">
              <label>Name</label>
              <input
                type="text"
                value={newType.type_name}
                onChange={(e) => setNewType(prev => ({ ...prev, type_name: e.target.value }))}
                placeholder="e.g., Initial Consultation"
              />
            </div>
            <div className="form-field">
              <label>Duration (min)</label>
              <select
                value={newType.duration_minutes}
                onChange={(e) => setNewType(prev => ({ ...prev, duration_minutes: parseInt(e.target.value) }))}
              >
                <option value={15}>15 minutes</option>
                <option value={30}>30 minutes</option>
                <option value={45}>45 minutes</option>
                <option value={60}>60 minutes</option>
                <option value={90}>90 minutes</option>
              </select>
            </div>
            <div className="form-field full-width">
              <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                Description
                <AIGenerateButton
                  fieldType="appointment_description"
                  context={{ name: newType.type_name, duration: `${newType.duration_minutes} minutes` }}
                  currentValue={newType.description}
                  onGenerated={(text) => setNewType(prev => ({ ...prev, description: text }))}
                />
              </label>
              <textarea
                value={newType.description || ''}
                onChange={(e) => setNewType(prev => ({ ...prev, description: e.target.value }))}
                placeholder="Brief description shown to clients"
                rows={2}
              />
            </div>
            <div className="form-field">
              <label>Color</label>
              <div className="color-picker">
                {DEFAULT_COLORS.map(c => (
                  <button
                    key={c}
                    type="button"
                    className={`color-swatch ${newType.color === c ? 'selected' : ''}`}
                    style={{ backgroundColor: c }}
                    onClick={() => setNewType(prev => ({ ...prev, color: c }))}
                    aria-label={`Color ${c}`}
                  />
                ))}
              </div>
            </div>
            <div className="form-field">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={newType.is_public}
                  onChange={(e) => setNewType(prev => ({ ...prev, is_public: e.target.checked }))}
                />
                Available on public booking page
              </label>
            </div>
          </div>
          <div className="form-actions">
            <button className="btn-secondary btn-sm" onClick={() => setShowNewTypeForm(false)}>Cancel</button>
            <button
              className="btn-primary btn-sm"
              disabled={!newType.type_name.trim()}
              onClick={handleCreateType}
            >
              Create
            </button>
          </div>
        </div>
      )}

      <div className="type-list">
        {appointmentTypes.length === 0 && !loading && (
          <div className="empty-state">
            <i className="fas fa-calendar-plus"></i>
            <p>No appointment types yet. Create one to get started.</p>
          </div>
        )}
        {appointmentTypes.map((type, idx) => (
          <div key={type.id} className="type-card">
            <div className="type-color-bar" style={{ backgroundColor: type.color || '#218D8D' }} />
            <div className="type-content">
              {editingType === type.id ? (
                <EditTypeForm
                  type={type}
                  onSave={(data) => handleUpdateType(type.id, data)}
                  onCancel={() => setEditingType(null)}
                />
              ) : (
                <>
                  <div className="type-info">
                    <h4>{type.type_name}</h4>
                    <span className="type-meta">
                      {type.duration_minutes} min
                      {type.is_public && <span className="badge badge-public">Public</span>}
                    </span>
                    {type.description && <p className="type-desc">{type.description}</p>}
                  </div>
                  <div className="type-actions">
                    <button
                      className="icon-btn"
                      onClick={() => handleMoveType(idx, -1)}
                      disabled={idx === 0}
                      aria-label="Move up"
                      title="Move up"
                    >
                      <i className="fas fa-chevron-up"></i>
                    </button>
                    <button
                      className="icon-btn"
                      onClick={() => handleMoveType(idx, 1)}
                      disabled={idx === appointmentTypes.length - 1}
                      aria-label="Move down"
                      title="Move down"
                    >
                      <i className="fas fa-chevron-down"></i>
                    </button>
                    <button className="icon-btn" onClick={() => setEditingType(type.id)} aria-label="Edit" title="Edit">
                      <i className="fas fa-pen"></i>
                    </button>
                    <button className="icon-btn danger" onClick={() => handleDeleteType(type.id)} aria-label="Delete" title="Delete">
                      <i className="fas fa-trash"></i>
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
