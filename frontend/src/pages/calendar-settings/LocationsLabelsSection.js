/**
 * LocationsLabelsSection - Calendar Settings
 *
 * Handles meeting locations, calendar labels (with auto-assign mappings),
 * and appointment templates.
 */
import React, { useState, useCallback } from 'react';
import LocationManager from '../../components/calendar/LocationManager';
import LabelManager from '../../components/calendar/LabelManager';
import { calendarSettingsAPI } from '../../services/api';
import { toast } from '../../utils/toast';

const DEFAULT_COLORS = ['#218D8D', '#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#ef4444', '#6366f1'];

const TEMPLATE_CATEGORIES = [
  { value: 'pre_approval', label: 'Pre-Approval', icon: 'fa-file-signature' },
  { value: 'consultation', label: 'Consultation', icon: 'fa-comments' },
  { value: 'application_review', label: 'Application Review', icon: 'fa-clipboard-check' },
  { value: 'closing', label: 'Closing', icon: 'fa-handshake' },
  { value: 'follow_up', label: 'Follow-up', icon: 'fa-redo' },
  { value: 'other', label: 'Other', icon: 'fa-ellipsis-h' },
];

const LOCATION_TYPE_ICONS = {
  office: 'fa-building',
  virtual: 'fa-video',
  phone: 'fa-phone',
  borrower_home: 'fa-home',
  in_person: 'fa-building',
  video: 'fa-video',
  custom: 'fa-map-pin',
};

function TemplateForm({ initialData, labels, locations, categories, onSubmit, onCancel }) {
  const isEdit = !!initialData;
  const [form, setForm] = useState({
    name: initialData?.name || '',
    description: initialData?.description || '',
    duration_minutes: initialData?.duration_minutes || 30,
    location_type: initialData?.location_type || '',
    location_id: initialData?.location_id || '',
    label_id: initialData?.label_id || '',
    category: initialData?.category || 'other',
    color: initialData?.color || '#218D8D',
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!form.name.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit(form);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="template-form-card">
      <h4>{isEdit ? 'Edit Template' : 'New Appointment Template'}</h4>
      <div className="form-grid template-form-grid">
        <div className="form-field">
          <label>Template Name</label>
          <input type="text" value={form.name} onChange={(e) => setForm(prev => ({ ...prev, name: e.target.value }))} placeholder="e.g. 30-min Pre-Approval Call" autoFocus />
        </div>
        <div className="form-field">
          <label>Category</label>
          <select value={form.category} onChange={(e) => setForm(prev => ({ ...prev, category: e.target.value }))}>
            {categories.map(cat => <option key={cat.value} value={cat.value}>{cat.label}</option>)}
          </select>
        </div>
        <div className="form-field">
          <label>Duration</label>
          <select value={form.duration_minutes} onChange={(e) => setForm(prev => ({ ...prev, duration_minutes: parseInt(e.target.value) }))}>
            <option value={15}>15 min</option>
            <option value={30}>30 min</option>
            <option value={45}>45 min</option>
            <option value={60}>1 hour</option>
            <option value={90}>1h 30m</option>
            <option value={120}>2 hours</option>
          </select>
        </div>
        <div className="form-field">
          <label>Default Location</label>
          <select value={form.location_id} onChange={(e) => { const loc = locations.find(l => l.id === e.target.value); setForm(prev => ({ ...prev, location_id: e.target.value, location_type: loc?.type || prev.location_type })); }}>
            <option value="">No default location</option>
            {locations.filter(l => l.is_active !== false).map(loc => <option key={loc.id} value={loc.id}>{loc.name}</option>)}
          </select>
        </div>
        <div className="form-field">
          <label>Default Label</label>
          <select value={form.label_id} onChange={(e) => setForm(prev => ({ ...prev, label_id: e.target.value }))}>
            <option value="">No label</option>
            {labels.map(label => <option key={label.id} value={label.id}>{label.name}</option>)}
          </select>
        </div>
        <div className="form-field">
          <label>Color</label>
          <div className="color-picker">
            {DEFAULT_COLORS.map(c => (
              <button key={c} type="button" className={`color-swatch ${form.color === c ? 'selected' : ''}`} style={{ backgroundColor: c }} onClick={() => setForm(prev => ({ ...prev, color: c }))} aria-label={`Color ${c}`} />
            ))}
          </div>
        </div>
        <div className="form-field full-width">
          <label>Description</label>
          <textarea value={form.description} onChange={(e) => setForm(prev => ({ ...prev, description: e.target.value }))} placeholder="Describe what this template is used for..." rows={2} />
        </div>
      </div>
      <div className="form-actions">
        <button className="btn-secondary btn-sm" onClick={onCancel} disabled={submitting}>Cancel</button>
        <button className="btn-primary btn-sm" onClick={handleSubmit} disabled={submitting || !form.name.trim()}>
          {submitting ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Template'}
        </button>
      </div>
    </div>
  );
}

export default function LocationsLabelsSection({
  locations,
  setLocations,
  locationsLoading,
  labels,
  setLabels,
  labelsLoading,
  templates,
  setTemplates,
  templatesLoading,
  autoAssignLabels,
  setAutoAssignLabels,
  labelMappings,
  setLabelMappings,
  defaultLabelId,
  setDefaultLabelId,
  appointmentTypes,
  loadTabData,
}) {
  const [locLabelsExpanded, setLocLabelsExpanded] = useState({
    locations: true,
    labels: true,
    templates: false,
  });
  const [locLabelsSearch, setLocLabelsSearch] = useState('');
  const [showNewTemplateForm, setShowNewTemplateForm] = useState(false);
  const [editingTemplateId, setEditingTemplateId] = useState(null);

  const toggleLocLabelsSection = useCallback((section) => {
    setLocLabelsExpanded(prev => ({ ...prev, [section]: !prev[section] }));
  }, []);

  // ---- Label handlers ----
  const handleCreateLabel = useCallback(async (labelData) => {
    try { await calendarSettingsAPI.createLabel(labelData); toast.success('Label created'); loadTabData('locations-labels'); } catch (err) { toast.error('Failed to create label'); }
  }, [loadTabData]);

  const handleUpdateLabel = useCallback(async (labelId, labelData) => {
    try { await calendarSettingsAPI.updateLabel(labelId, labelData); toast.success('Label updated'); loadTabData('locations-labels'); } catch (err) { toast.error('Failed to update label'); }
  }, [loadTabData]);

  const handleDeleteLabel = useCallback(async (labelId) => {
    try { await calendarSettingsAPI.deleteLabel(labelId); toast.success('Label deleted'); loadTabData('locations-labels'); } catch (err) { toast.error('Failed to delete label'); }
  }, [loadTabData]);

  const handleReorderLabels = useCallback(async (orderedIds) => {
    try {
      await calendarSettingsAPI.reorderLabels(orderedIds);
      const reordered = orderedIds.map(id => labels.find(l => l.id === id)).filter(Boolean);
      setLabels(reordered);
    } catch (err) { toast.error('Failed to reorder labels'); loadTabData('locations-labels'); }
  }, [labels, setLabels, loadTabData]);

  const handleToggleAutoAssign = useCallback(async (enabled) => {
    setAutoAssignLabels(enabled);
    try { await calendarSettingsAPI.updateLabelSettings({ auto_assign_enabled: enabled, label_mappings: labelMappings }); } catch (err) { toast.error('Failed to update auto-assign setting'); setAutoAssignLabels(!enabled); }
  }, [labelMappings, setAutoAssignLabels]);

  const handleUpdateLabelMapping = useCallback(async (appointmentTypeId, labelId) => {
    const newMappings = { ...labelMappings, [appointmentTypeId]: labelId };
    setLabelMappings(newMappings);
    try { await calendarSettingsAPI.updateLabelSettings({ auto_assign_enabled: autoAssignLabels, label_mappings: newMappings }); } catch (err) { toast.error('Failed to save label mapping'); }
  }, [labelMappings, autoAssignLabels, setLabelMappings]);

  const handleSetDefaultLabel = useCallback(async (labelId) => {
    try { await calendarSettingsAPI.setDefaultLabel(labelId); setDefaultLabelId(labelId); toast.success('Default label updated'); } catch (err) { toast.error('Failed to set default label'); }
  }, [setDefaultLabelId]);

  // ---- Location handlers ----
  const handleCreateLocation = useCallback(async (locData) => {
    try { await calendarSettingsAPI.createLocation(locData); toast.success('Location added'); loadTabData('locations-labels'); } catch (err) { toast.error('Failed to create location'); }
  }, [loadTabData]);

  const handleUpdateLocation = useCallback(async (locId, locData) => {
    try { await calendarSettingsAPI.updateLocation(locId, locData); toast.success('Location updated'); loadTabData('locations-labels'); } catch (err) { toast.error('Failed to update location'); }
  }, [loadTabData]);

  const handleDeleteLocation = useCallback(async (locId) => {
    try { await calendarSettingsAPI.deleteLocation(locId); toast.success('Location deleted'); setLocations(prev => prev.filter(l => l.id !== locId)); } catch (err) { toast.error('Failed to delete location'); }
  }, [setLocations]);

  const handleReorderLocations = useCallback(async (orderedIds) => {
    try {
      await calendarSettingsAPI.reorderLocations(orderedIds);
      const reordered = orderedIds.map(id => locations.find(l => l.id === id)).filter(Boolean);
      setLocations(reordered);
    } catch (err) { toast.error('Failed to reorder locations'); loadTabData('locations-labels'); }
  }, [locations, setLocations, loadTabData]);

  const handleSetDefaultLocation = useCallback(async (locId) => {
    try { await calendarSettingsAPI.setDefaultLocation(locId); setLocations(prev => prev.map(l => ({ ...l, is_default: l.id === locId }))); toast.success('Default location updated'); } catch (err) { toast.error('Failed to set default location'); }
  }, [setLocations]);

  // ---- Template handlers ----
  const handleCreateTemplate = useCallback(async (templateData) => {
    try { await calendarSettingsAPI.createTemplate(templateData); toast.success('Template created'); setShowNewTemplateForm(false); loadTabData('locations-labels'); } catch (err) { toast.error('Failed to create template'); }
  }, [loadTabData]);

  const handleUpdateTemplate = useCallback(async (templateId, templateData) => {
    try { await calendarSettingsAPI.updateTemplate(templateId, templateData); toast.success('Template updated'); setEditingTemplateId(null); loadTabData('locations-labels'); } catch (err) { toast.error('Failed to update template'); }
  }, [loadTabData]);

  const handleDeleteTemplate = useCallback(async (templateId) => {
    if (!window.confirm('Delete this appointment template?')) return;
    try { await calendarSettingsAPI.deleteTemplate(templateId); toast.success('Template deleted'); setTemplates(prev => prev.filter(t => t.id !== templateId)); } catch (err) { toast.error('Failed to delete template'); }
  }, [setTemplates]);

  const handleToggleDefaultTemplate = useCallback(async (templateId) => {
    try { await calendarSettingsAPI.setDefaultTemplate(templateId); setTemplates(prev => prev.map(t => ({ ...t, is_default: t.id === templateId }))); toast.success('Default template updated'); } catch (err) { toast.error('Failed to set default template'); }
  }, [setTemplates]);

  const handleDuplicateTemplate = useCallback(async (templateId) => {
    try { await calendarSettingsAPI.duplicateTemplate(templateId); toast.success('Template duplicated'); loadTabData('locations-labels'); } catch (err) { toast.error('Failed to duplicate template'); }
  }, [loadTabData]);

  const durationLabel = (min) => {
    if (min >= 60) { const h = Math.floor(min / 60); const m = min % 60; return m > 0 ? `${h}h ${m}m` : `${h} hour${h > 1 ? 's' : ''}`; }
    return `${min} min`;
  };

  // Filter by search
  const q = locLabelsSearch.toLowerCase().trim();
  const filteredLocations = q ? locations.filter(l => l.name?.toLowerCase().includes(q) || l.type?.toLowerCase().includes(q)) : locations;
  const filteredLabels = q ? labels.filter(l => l.name?.toLowerCase().includes(q) || l.description?.toLowerCase().includes(q)) : labels;
  const filteredTemplates = q ? templates.filter(t => t.name?.toLowerCase().includes(q) || t.category?.toLowerCase().includes(q) || t.description?.toLowerCase().includes(q)) : templates;

  return (
    <div role="tabpanel" id="panel-locations-labels" aria-labelledby="calnav-locations-labels">

      {/* ---- Quick Actions Bar ---- */}
      <div className="loc-labels-quick-actions">
        <div className="quick-actions-buttons">
          <button className="btn-secondary btn-sm" onClick={() => { setLocLabelsExpanded(prev => ({ ...prev, locations: true })); document.getElementById('loc-section-locations')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}>
            <i className="fas fa-map-marker-alt"></i> Add Location
          </button>
          <button className="btn-secondary btn-sm" onClick={() => { setLocLabelsExpanded(prev => ({ ...prev, labels: true })); document.getElementById('loc-section-labels')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}>
            <i className="fas fa-tag"></i> Add Label
          </button>
          <button className="btn-secondary btn-sm" onClick={() => { setLocLabelsExpanded(prev => ({ ...prev, templates: true })); setShowNewTemplateForm(true); setTimeout(() => { document.getElementById('loc-section-templates')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 100); }}>
            <i className="fas fa-copy"></i> Add Template
          </button>
        </div>
        <div className="quick-actions-search">
          <i className="fas fa-search"></i>
          <input type="text" value={locLabelsSearch} onChange={(e) => setLocLabelsSearch(e.target.value)} placeholder="Filter locations, labels, templates..." className="quick-search-input" />
          {locLabelsSearch && (
            <button className="quick-search-clear" onClick={() => setLocLabelsSearch('')} aria-label="Clear search">
              <i className="fas fa-times"></i>
            </button>
          )}
        </div>
      </div>

      {/* ---- Section 1: Meeting Locations ---- */}
      <section className="cal-settings-section loc-labels-section" id="loc-section-locations">
        <button type="button" className="collapsible-header" onClick={() => toggleLocLabelsSection('locations')} aria-expanded={locLabelsExpanded.locations}>
          <div className="collapsible-header-left">
            <i className={`fas fa-chevron-${locLabelsExpanded.locations ? 'down' : 'right'} collapsible-chevron`}></i>
            <div>
              <h2>Meeting Locations</h2>
              <p className="section-description">Define where appointments take place -- office, virtual, phone, or custom.</p>
            </div>
          </div>
          <div className="collapsible-header-right">
            <span className="collapsible-count">{locations.length}</span>
            <span className="collapsible-badge"><i className="fas fa-map-marker-alt"></i></span>
          </div>
        </button>
        {locLabelsExpanded.locations && (
          <div className="collapsible-body">
            <LocationManager
              locations={filteredLocations}
              onCreateLocation={handleCreateLocation}
              onUpdateLocation={handleUpdateLocation}
              onDeleteLocation={handleDeleteLocation}
              onReorderLocations={handleReorderLocations}
              onSetDefault={handleSetDefaultLocation}
              loading={locationsLoading}
            />
          </div>
        )}
      </section>

      {/* ---- Section 2: Calendar Labels ---- */}
      <section className="cal-settings-section loc-labels-section" id="loc-section-labels">
        <button type="button" className="collapsible-header" onClick={() => toggleLocLabelsSection('labels')} aria-expanded={locLabelsExpanded.labels}>
          <div className="collapsible-header-left">
            <i className={`fas fa-chevron-${locLabelsExpanded.labels ? 'down' : 'right'} collapsible-chevron`}></i>
            <div>
              <h2>Calendar Labels</h2>
              <p className="section-description">Color-coded labels to categorize and filter your appointments at a glance.</p>
            </div>
          </div>
          <div className="collapsible-header-right">
            <span className="collapsible-count">{labels.length}</span>
            <span className="collapsible-badge"><i className="fas fa-tags"></i></span>
          </div>
        </button>
        {locLabelsExpanded.labels && (
          <div className="collapsible-body">
            <LabelManager
              labels={filteredLabels}
              onCreateLabel={handleCreateLabel}
              onUpdateLabel={handleUpdateLabel}
              onDeleteLabel={handleDeleteLabel}
              onReorderLabels={handleReorderLabels}
              onSetDefaultLabel={handleSetDefaultLabel}
              defaultLabelId={defaultLabelId}
              loading={labelsLoading}
            />

            {labels.length > 0 && (
              <div className="default-label-section">
                <label className="default-label-row">
                  <span>Default label for new appointments:</span>
                  <select value={defaultLabelId || ''} onChange={(e) => handleSetDefaultLabel(e.target.value || null)} className="mapping-select">
                    <option value="">None</option>
                    {labels.map(label => <option key={label.id} value={label.id}>{label.name}</option>)}
                  </select>
                </label>
              </div>
            )}

            <div className="auto-assign-section">
              <label className="toggle-row auto-assign-toggle">
                <input type="checkbox" checked={autoAssignLabels} onChange={(e) => handleToggleAutoAssign(e.target.checked)} />
                <span>Auto-assign labels based on appointment type</span>
              </label>

              {autoAssignLabels && appointmentTypes.length > 0 && (
                <div className="label-mapping-grid">
                  {appointmentTypes.map(type => (
                    <div key={type.id} className="label-mapping-row">
                      <div className="mapping-type-name">
                        <div className="mapping-color-dot" style={{ backgroundColor: type.color || '#218D8D' }} />
                        <span>{type.type_name}</span>
                      </div>
                      <select value={labelMappings[type.id] || ''} onChange={(e) => handleUpdateLabelMapping(type.id, e.target.value || null)} className="mapping-select">
                        <option value="">No label</option>
                        {labels.map(label => <option key={label.id} value={label.id}>{label.name}</option>)}
                      </select>
                    </div>
                  ))}
                </div>
              )}

              {autoAssignLabels && appointmentTypes.length === 0 && (
                <p className="empty-hint" style={{ marginTop: 8 }}>
                  Create appointment types first to set up label mappings.
                </p>
              )}
            </div>
          </div>
        )}
      </section>

      {/* ---- Section 3: Appointment Templates ---- */}
      <section className="cal-settings-section loc-labels-section" id="loc-section-templates">
        <button type="button" className="collapsible-header" onClick={() => toggleLocLabelsSection('templates')} aria-expanded={locLabelsExpanded.templates}>
          <div className="collapsible-header-left">
            <i className={`fas fa-chevron-${locLabelsExpanded.templates ? 'down' : 'right'} collapsible-chevron`}></i>
            <div>
              <h2>Appointment Templates</h2>
              <p className="section-description">Pre-configured appointment setups for quick scheduling. Set a default for one-click booking.</p>
            </div>
          </div>
          <div className="collapsible-header-right">
            <span className="collapsible-count">{templates.length}</span>
            <span className="collapsible-badge"><i className="fas fa-copy"></i></span>
          </div>
        </button>
        {locLabelsExpanded.templates && (
          <div className="collapsible-body">
            <div className="template-category-tabs">
              {TEMPLATE_CATEGORIES.map(cat => {
                const count = filteredTemplates.filter(t => (t.category || 'other') === cat.value).length;
                return (
                  <span key={cat.value} className="template-category-chip" title={cat.label}>
                    <i className={`fas ${cat.icon}`}></i> {cat.label}
                    {count > 0 && <span className="chip-count">{count}</span>}
                  </span>
                );
              })}
            </div>

            {showNewTemplateForm && (
              <TemplateForm
                labels={labels}
                locations={locations}
                categories={TEMPLATE_CATEGORIES}
                onSubmit={handleCreateTemplate}
                onCancel={() => setShowNewTemplateForm(false)}
              />
            )}

            {templatesLoading ? (
              <div className="empty-hint">Loading templates...</div>
            ) : filteredTemplates.length === 0 && !showNewTemplateForm ? (
              <div className="empty-state">
                <i className="fas fa-layer-group"></i>
                <p>No appointment templates yet.</p>
                <p className="empty-hint">Templates help you quickly create common appointment types with pre-filled settings.</p>
                <button className="btn-primary btn-sm" onClick={() => setShowNewTemplateForm(true)}>
                  <i className="fas fa-plus"></i> Create Template
                </button>
              </div>
            ) : (
              <div className="template-list">
                {filteredTemplates.map(template => (
                  editingTemplateId === template.id ? (
                    <TemplateForm
                      key={template.id}
                      initialData={template}
                      labels={labels}
                      locations={locations}
                      categories={TEMPLATE_CATEGORIES}
                      onSubmit={(data) => handleUpdateTemplate(template.id, data)}
                      onCancel={() => setEditingTemplateId(null)}
                    />
                  ) : (
                    <div key={template.id} className={`template-card${template.is_default ? ' is-default' : ''}`}>
                      <div className="template-card-left">
                        <div className="template-card-header">
                          <strong>{template.name}</strong>
                          {template.category && (
                            <span className="template-category-tag">
                              <i className={`fas ${TEMPLATE_CATEGORIES.find(c => c.value === template.category)?.icon || 'fa-tag'}`}></i>
                              {TEMPLATE_CATEGORIES.find(c => c.value === template.category)?.label || template.category}
                            </span>
                          )}
                          {template.is_default && <span className="badge badge-default">Default</span>}
                        </div>
                        <div className="template-meta">
                          <span><i className="fas fa-clock"></i> {durationLabel(template.duration_minutes || 30)}</span>
                          {template.location_type && (
                            <span><i className={`fas ${LOCATION_TYPE_ICONS[template.location_type] || 'fa-map-pin'}`}></i> {template.location_type.replace(/_/g, ' ')}</span>
                          )}
                          {template.label_name && (
                            <span><span className="template-label-dot" style={{ backgroundColor: template.label_color || '#ccc' }} />{template.label_name}</span>
                          )}
                          {template.appointment_type_name && (
                            <span><i className="fas fa-tag"></i> {template.appointment_type_name}</span>
                          )}
                          {typeof template.use_count === 'number' && (
                            <span className="template-use-count" title="Times used"><i className="fas fa-chart-bar"></i> {template.use_count} uses</span>
                          )}
                        </div>
                        {template.description && <p className="template-desc">{template.description}</p>}
                      </div>
                      <div className="template-card-actions">
                        {!template.is_default && (
                          <button className="btn-secondary btn-sm" onClick={() => handleToggleDefaultTemplate(template.id)} title="Use as default">
                            <i className="fas fa-star"></i> Set Default
                          </button>
                        )}
                        <button className="icon-btn" onClick={() => setEditingTemplateId(template.id)} title="Edit template"><i className="fas fa-pen"></i></button>
                        <button className="icon-btn" onClick={() => handleDuplicateTemplate(template.id)} title="Duplicate template"><i className="fas fa-clone"></i></button>
                        <button className="icon-btn danger" onClick={() => handleDeleteTemplate(template.id)} title="Delete template"><i className="fas fa-trash"></i></button>
                      </div>
                    </div>
                  )
                ))}
              </div>
            )}

            {!showNewTemplateForm && filteredTemplates.length > 0 && (
              <button className="btn-add-template" onClick={() => setShowNewTemplateForm(true)}>
                <i className="fas fa-plus"></i> Create New Template
              </button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
