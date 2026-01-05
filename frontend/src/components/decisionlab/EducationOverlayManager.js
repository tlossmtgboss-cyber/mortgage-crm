import React, { useState, useEffect, useCallback } from 'react';
import { decisionLabAPI } from '../../services/decisionLabApi';
import './EducationOverlayManager.css';

const TRIGGER_TYPES = [
  { value: 'question', label: 'Question-based', description: 'Shows when a specific question is displayed' },
  { value: 'category', label: 'Category-based', description: 'Shows for all questions in a category' },
  { value: 'keyword', label: 'Keyword-based', description: 'Shows when a keyword appears in the question' },
  { value: 'score_threshold', label: 'Score-based', description: 'Shows based on current confidence score' },
];

const CATEGORIES = [
  { value: 'FINANCIAL_READINESS', label: 'Financial Readiness' },
  { value: 'CREDIT_UNDERSTANDING', label: 'Credit Understanding' },
  { value: 'MORTGAGE_KNOWLEDGE', label: 'Mortgage Knowledge' },
  { value: 'PROCESS_UNDERSTANDING', label: 'Process Understanding' },
  { value: 'EMOTIONAL_READINESS', label: 'Emotional Readiness' },
];

const EMPTY_OVERLAY = {
  title: '',
  content: '',
  trigger_type: 'question',
  trigger_value: '',
  category: '',
  formula: '',
  example: '',
  tip: '',
  key_takeaway: '',
  is_active: true,
  display_order: 0,
};

function EducationOverlayManager() {
  const [overlays, setOverlays] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [editingOverlay, setEditingOverlay] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState(EMPTY_OVERLAY);
  const [saving, setSaving] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);

  // Fetch overlays and questions
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [overlaysData, questionsData] = await Promise.all([
        decisionLabAPI.getOverlays(),
        decisionLabAPI.getAllQuestions(),
      ]);
      setOverlays(overlaysData.overlays || overlaysData || []);
      setQuestions(questionsData.questions || questionsData || []);
    } catch (err) {
      setError('Failed to load data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Handle form changes
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));
  };

  // Open create form
  const handleCreate = () => {
    setEditingOverlay(null);
    setFormData(EMPTY_OVERLAY);
    setShowForm(true);
    setError('');
    setSuccess('');
  };

  // Open edit form
  const handleEdit = (overlay) => {
    setEditingOverlay(overlay);
    setFormData({
      title: overlay.title || '',
      content: overlay.content || '',
      trigger_type: overlay.trigger_type || 'question',
      trigger_value: overlay.trigger_value || '',
      category: overlay.category || '',
      formula: overlay.formula || '',
      example: overlay.example || '',
      tip: overlay.tip || '',
      key_takeaway: overlay.key_takeaway || '',
      is_active: overlay.is_active !== false,
      display_order: overlay.display_order || 0,
    });
    setShowForm(true);
    setError('');
    setSuccess('');
  };

  // Cancel form
  const handleCancel = () => {
    setShowForm(false);
    setEditingOverlay(null);
    setFormData(EMPTY_OVERLAY);
    setPreviewMode(false);
  };

  // Save overlay
  const handleSave = async (e) => {
    e.preventDefault();

    if (!formData.title.trim()) {
      setError('Title is required');
      return;
    }
    if (!formData.content.trim()) {
      setError('Content is required');
      return;
    }

    setSaving(true);
    setError('');

    try {
      if (editingOverlay) {
        await decisionLabAPI.updateOverlay(editingOverlay.id, formData);
        setSuccess('Overlay updated successfully');
      } else {
        await decisionLabAPI.createOverlay(formData);
        setSuccess('Overlay created successfully');
      }
      await fetchData();
      handleCancel();
    } catch (err) {
      setError(`Failed to ${editingOverlay ? 'update' : 'create'} overlay`);
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  // Delete overlay
  const handleDelete = async (overlayId) => {
    if (!window.confirm('Are you sure you want to delete this overlay?')) {
      return;
    }

    try {
      await decisionLabAPI.deleteOverlay(overlayId);
      setSuccess('Overlay deleted successfully');
      await fetchData();
    } catch (err) {
      setError('Failed to delete overlay');
      console.error(err);
    }
  };

  // Toggle preview
  const togglePreview = () => {
    setPreviewMode(!previewMode);
  };

  // Get trigger label
  const getTriggerLabel = (overlay) => {
    const type = TRIGGER_TYPES.find(t => t.value === overlay.trigger_type);
    if (overlay.trigger_type === 'question') {
      const question = questions.find(q => q.id === overlay.trigger_value);
      return question ? question.question_text.substring(0, 50) + '...' : overlay.trigger_value;
    }
    if (overlay.trigger_type === 'category') {
      const cat = CATEGORIES.find(c => c.value === overlay.trigger_value);
      return cat ? cat.label : overlay.trigger_value;
    }
    return overlay.trigger_value || type?.label || 'Unknown';
  };

  if (loading) {
    return (
      <div className="overlay-manager-loading">
        <div className="loading-spinner" />
        <p>Loading education content...</p>
      </div>
    );
  }

  return (
    <div className="education-overlay-manager">
      {/* Header */}
      <div className="manager-header">
        <div className="header-info">
          <h2>Education Overlays</h2>
          <p>Create and manage educational content that appears during the confidence assessment</p>
        </div>
        <button className="create-button" onClick={handleCreate}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 4v16m8-8H4" />
          </svg>
          Add New Overlay
        </button>
      </div>

      {/* Messages */}
      {error && (
        <div className="message error">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {error}
        </div>
      )}
      {success && (
        <div className="message success">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {success}
        </div>
      )}

      {/* Overlay List */}
      {!showForm && (
        <div className="overlays-list">
          {overlays.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
              </div>
              <h3>No Education Overlays Yet</h3>
              <p>Create your first overlay to help users learn during their assessment</p>
              <button className="create-button" onClick={handleCreate}>
                Create First Overlay
              </button>
            </div>
          ) : (
            <div className="overlays-grid">
              {overlays.map(overlay => (
                <div key={overlay.id} className={`overlay-card ${!overlay.is_active ? 'inactive' : ''}`}>
                  <div className="card-header">
                    <h3 className="card-title">{overlay.title}</h3>
                    <div className={`status-badge ${overlay.is_active ? 'active' : 'inactive'}`}>
                      {overlay.is_active ? 'Active' : 'Inactive'}
                    </div>
                  </div>
                  <p className="card-content">{overlay.content?.substring(0, 120)}...</p>
                  <div className="card-meta">
                    <span className="trigger-type">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      {TRIGGER_TYPES.find(t => t.value === overlay.trigger_type)?.label}
                    </span>
                    <span className="trigger-value">{getTriggerLabel(overlay)}</span>
                  </div>
                  <div className="card-features">
                    {overlay.formula && <span className="feature-tag">Formula</span>}
                    {overlay.example && <span className="feature-tag">Example</span>}
                    {overlay.tip && <span className="feature-tag">Tip</span>}
                    {overlay.key_takeaway && <span className="feature-tag">Takeaway</span>}
                  </div>
                  <div className="card-actions">
                    <button className="edit-button" onClick={() => handleEdit(overlay)}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                      Edit
                    </button>
                    <button className="delete-button" onClick={() => handleDelete(overlay.id)}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Create/Edit Form */}
      {showForm && (
        <div className="overlay-form-container">
          <div className="form-header">
            <h3>{editingOverlay ? 'Edit Overlay' : 'Create New Overlay'}</h3>
            <div className="form-header-actions">
              <button
                type="button"
                className={`preview-toggle ${previewMode ? 'active' : ''}`}
                onClick={togglePreview}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
                {previewMode ? 'Edit' : 'Preview'}
              </button>
            </div>
          </div>

          {previewMode ? (
            <div className="preview-container">
              <div className="preview-overlay">
                <div className="preview-badge">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                  </svg>
                  Learn
                </div>
                <h2>{formData.title || 'Overlay Title'}</h2>
                <p>{formData.content || 'Main content will appear here...'}</p>
                {formData.formula && (
                  <div className="preview-formula">
                    <strong>Formula:</strong> {formData.formula}
                  </div>
                )}
                {formData.example && (
                  <div className="preview-example">
                    <strong>Example:</strong> {formData.example}
                  </div>
                )}
                {formData.tip && (
                  <div className="preview-tip">
                    <strong>Pro Tip:</strong> {formData.tip}
                  </div>
                )}
                {formData.key_takeaway && (
                  <div className="preview-takeaway">
                    <strong>Key Takeaway:</strong> {formData.key_takeaway}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <form onSubmit={handleSave} className="overlay-form">
              {/* Basic Info */}
              <div className="form-section">
                <h4>Basic Information</h4>
                <div className="form-group">
                  <label htmlFor="title">Title *</label>
                  <input
                    type="text"
                    id="title"
                    name="title"
                    value={formData.title}
                    onChange={handleChange}
                    placeholder="e.g., Understanding Your DTI Ratio"
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="content">Main Content *</label>
                  <textarea
                    id="content"
                    name="content"
                    value={formData.content}
                    onChange={handleChange}
                    placeholder="The main educational content that explains the concept..."
                    rows={4}
                    required
                  />
                </div>
              </div>

              {/* Trigger Settings */}
              <div className="form-section">
                <h4>Trigger Settings</h4>
                <p className="section-description">
                  Configure when this overlay should appear during the assessment
                </p>

                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="trigger_type">Trigger Type</label>
                    <select
                      id="trigger_type"
                      name="trigger_type"
                      value={formData.trigger_type}
                      onChange={handleChange}
                    >
                      {TRIGGER_TYPES.map(type => (
                        <option key={type.value} value={type.value}>
                          {type.label}
                        </option>
                      ))}
                    </select>
                    <span className="form-help">
                      {TRIGGER_TYPES.find(t => t.value === formData.trigger_type)?.description}
                    </span>
                  </div>

                  <div className="form-group">
                    <label htmlFor="trigger_value">Trigger Value</label>
                    {formData.trigger_type === 'question' ? (
                      <select
                        id="trigger_value"
                        name="trigger_value"
                        value={formData.trigger_value}
                        onChange={handleChange}
                      >
                        <option value="">Select a question...</option>
                        {questions.map(q => (
                          <option key={q.id} value={q.id}>
                            {q.question_text.substring(0, 60)}...
                          </option>
                        ))}
                      </select>
                    ) : formData.trigger_type === 'category' ? (
                      <select
                        id="trigger_value"
                        name="trigger_value"
                        value={formData.trigger_value}
                        onChange={handleChange}
                      >
                        <option value="">Select a category...</option>
                        {CATEGORIES.map(cat => (
                          <option key={cat.value} value={cat.value}>
                            {cat.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="text"
                        id="trigger_value"
                        name="trigger_value"
                        value={formData.trigger_value}
                        onChange={handleChange}
                        placeholder={formData.trigger_type === 'keyword' ? 'e.g., credit score' : 'e.g., 50'}
                      />
                    )}
                  </div>
                </div>
              </div>

              {/* Enhanced Content */}
              <div className="form-section">
                <h4>Enhanced Content (Optional)</h4>
                <p className="section-description">
                  Add additional educational elements to make the content more engaging
                </p>

                <div className="form-group">
                  <label htmlFor="formula">Formula</label>
                  <input
                    type="text"
                    id="formula"
                    name="formula"
                    value={formData.formula}
                    onChange={handleChange}
                    placeholder="e.g., DTI = (Monthly Debt / Gross Monthly Income) × 100"
                  />
                  <span className="form-help">A formula or calculation to display</span>
                </div>

                <div className="form-group">
                  <label htmlFor="example">Example</label>
                  <textarea
                    id="example"
                    name="example"
                    value={formData.example}
                    onChange={handleChange}
                    placeholder="e.g., If you earn $6,000/month and have $2,000 in monthly debts, your DTI is 33%"
                    rows={3}
                  />
                  <span className="form-help">A practical example to illustrate the concept</span>
                </div>

                <div className="form-group">
                  <label htmlFor="tip">Pro Tip</label>
                  <textarea
                    id="tip"
                    name="tip"
                    value={formData.tip}
                    onChange={handleChange}
                    placeholder="e.g., Lenders generally prefer a DTI below 43% for conventional loans"
                    rows={2}
                  />
                  <span className="form-help">A helpful tip or best practice</span>
                </div>

                <div className="form-group">
                  <label htmlFor="key_takeaway">Key Takeaway</label>
                  <textarea
                    id="key_takeaway"
                    name="key_takeaway"
                    value={formData.key_takeaway}
                    onChange={handleChange}
                    placeholder="e.g., A lower DTI means more borrowing power and often better rates"
                    rows={2}
                  />
                  <span className="form-help">The main point you want users to remember</span>
                </div>
              </div>

              {/* Settings */}
              <div className="form-section">
                <h4>Settings</h4>
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="display_order">Display Order</label>
                    <input
                      type="number"
                      id="display_order"
                      name="display_order"
                      value={formData.display_order}
                      onChange={handleChange}
                      min="0"
                    />
                    <span className="form-help">Lower numbers appear first</span>
                  </div>

                  <div className="form-group checkbox-group">
                    <label>
                      <input
                        type="checkbox"
                        name="is_active"
                        checked={formData.is_active}
                        onChange={handleChange}
                      />
                      <span className="checkbox-label">Active</span>
                    </label>
                    <span className="form-help">Inactive overlays won't be shown to users</span>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="form-actions">
                <button type="button" className="cancel-button" onClick={handleCancel}>
                  Cancel
                </button>
                <button type="submit" className="save-button" disabled={saving}>
                  {saving ? 'Saving...' : editingOverlay ? 'Update Overlay' : 'Create Overlay'}
                </button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  );
}

export default EducationOverlayManager;
