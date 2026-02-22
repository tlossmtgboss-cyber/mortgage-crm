import React, { useState, useEffect } from 'react';
import './ResponsibilityModal.css';
import { toast } from '../utils/toast';

/**
 * ResponsibilityModal - Add/Edit responsibility modal
 *
 * Features:
 * - Form validation for all required fields
 * - Skills multi-select with ability to add new skills
 * - Time allocation slider
 * - Ownership radio buttons with tooltips
 * - Date validation (end date must be after effective date)
 * - Dirty state tracking for unsaved changes warning
 */

function ResponsibilityModal({ responsibility, onSave, onClose, availableSkills, onAddSkill }) {
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    ownership: 'primary',
    time_allocation: 0,
    priority: '',
    effective_date: new Date().toISOString().split('T')[0],
    end_date: '',
    required_skills: []
  });

  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [showAddSkillModal, setShowAddSkillModal] = useState(false);
  const [newSkill, setNewSkill] = useState({ name: '', category: 'technical' });
  const [addingSkill, setAddingSkill] = useState(false);

  useEffect(() => {
    if (responsibility) {
      setFormData({
        title: responsibility.title || '',
        description: responsibility.description || '',
        ownership: responsibility.ownership || 'primary',
        time_allocation: responsibility.time_allocation || 0,
        priority: responsibility.priority || '',
        effective_date: responsibility.effective_date || new Date().toISOString().split('T')[0],
        end_date: responsibility.end_date || '',
        required_skills: responsibility.required_skills?.map(s => s.id) || []
      });
    }
  }, [responsibility]);

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setIsDirty(true);
    // Clear error for this field
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: null }));
    }
  };

  const toggleSkill = (skillId) => {
    setFormData(prev => ({
      ...prev,
      required_skills: prev.required_skills.includes(skillId)
        ? prev.required_skills.filter(id => id !== skillId)
        : [...prev.required_skills, skillId]
    }));
    setIsDirty(true);
  };

  const validate = () => {
    const newErrors = {};

    if (!formData.title.trim()) {
      newErrors.title = 'Title is required';
    } else if (formData.title.length > 255) {
      newErrors.title = 'Title must be less than 255 characters';
    }

    if (!formData.ownership) {
      newErrors.ownership = 'Ownership type is required';
    }

    if (formData.time_allocation < 0 || formData.time_allocation > 100) {
      newErrors.time_allocation = 'Time allocation must be between 0 and 100';
    }

    if (!formData.priority) {
      newErrors.priority = 'Priority is required';
    }

    if (!formData.effective_date) {
      newErrors.effective_date = 'Effective date is required';
    }

    if (formData.end_date && formData.effective_date) {
      const effectiveDate = new Date(formData.effective_date);
      const endDate = new Date(formData.end_date);
      if (endDate <= effectiveDate) {
        newErrors.end_date = 'End date must be after effective date';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validate()) {
      return;
    }

    try {
      setSaving(true);
      await onSave(formData);
      setIsDirty(false);
      onClose();
    } catch (error) {
      console.error('Error saving responsibility:', error);
      setErrors({ submit: error.message || 'Failed to save responsibility' });
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    if (isDirty) {
      if (window.confirm('You have unsaved changes. Discard changes?')) {
        onClose();
      }
    } else {
      onClose();
    }
  };

  const handleAddSkill = async (e) => {
    e.preventDefault();

    if (!newSkill.name.trim()) {
      toast.error('Skill name is required');
      return;
    }

    try {
      setAddingSkill(true);
      const addedSkill = await onAddSkill(newSkill);

      // Auto-select the newly added skill
      setFormData(prev => ({
        ...prev,
        required_skills: [...prev.required_skills, addedSkill.id]
      }));

      setShowAddSkillModal(false);
      setNewSkill({ name: '', category: 'technical' });
      setIsDirty(true);
    } catch (error) {
      console.error('Error adding skill:', error);
      toast.error(error.message || 'Failed to add skill');
    } finally {
      setAddingSkill(false);
    }
  };

  return (
    <>
      <div className="modal-overlay" onClick={handleClose}>
        <div className="modal-content responsibility-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h3>{responsibility ? 'Edit' : 'Add'} Responsibility</h3>
            <button onClick={handleClose} className="btn-close">×</button>
          </div>

          <form onSubmit={handleSubmit} className="modal-body">
            {/* Title */}
            <div className="form-group">
              <label htmlFor="title">
                Title <span className="required">*</span>
              </label>
              <input
                id="title"
                type="text"
                value={formData.title}
                onChange={(e) => handleChange('title', e.target.value)}
                maxLength={255}
                placeholder="e.g., Originate residential mortgage loans"
                className={errors.title ? 'error' : ''}
              />
              {errors.title && <span className="error-message">{errors.title}</span>}
            </div>

            {/* Description */}
            <div className="form-group">
              <label htmlFor="description">Description</label>
              <textarea
                id="description"
                value={formData.description}
                onChange={(e) => handleChange('description', e.target.value)}
                rows={4}
                placeholder="Detailed description of this responsibility..."
              />
            </div>

            {/* Ownership */}
            <div className="form-group">
              <label>
                Ownership Type <span className="required">*</span>
              </label>
              <div className="radio-group">
                <label className="radio-label" title="Main person responsible for this duty">
                  <input
                    type="radio"
                    value="primary"
                    checked={formData.ownership === 'primary'}
                    onChange={(e) => handleChange('ownership', e.target.value)}
                  />
                  <span className="radio-text">
                    ⭐ Primary
                    <small>Main responsibility</small>
                  </span>
                </label>
                <label className="radio-label" title="Supporting role for this duty">
                  <input
                    type="radio"
                    value="secondary"
                    checked={formData.ownership === 'secondary'}
                    onChange={(e) => handleChange('ownership', e.target.value)}
                  />
                  <span className="radio-text">
                    ➕ Secondary
                    <small>Supporting role</small>
                  </span>
                </label>
                <label className="radio-label" title="Shared equally with others">
                  <input
                    type="radio"
                    value="shared"
                    checked={formData.ownership === 'shared'}
                    onChange={(e) => handleChange('ownership', e.target.value)}
                  />
                  <span className="radio-text">
                    🤝 Shared
                    <small>Shared with others</small>
                  </span>
                </label>
              </div>
              {errors.ownership && <span className="error-message">{errors.ownership}</span>}
            </div>

            {/* Time Allocation Slider */}
            <div className="form-group">
              <label htmlFor="time_allocation">
                Time Allocation: <strong>{formData.time_allocation}%</strong>
              </label>
              <input
                id="time_allocation"
                type="range"
                min="0"
                max="100"
                step="5"
                value={formData.time_allocation}
                onChange={(e) => handleChange('time_allocation', parseInt(e.target.value))}
                className="allocation-slider"
              />
              <div className="slider-markers">
                <span>0%</span>
                <span>25%</span>
                <span>50%</span>
                <span>75%</span>
                <span>100%</span>
              </div>
              {errors.time_allocation && <span className="error-message">{errors.time_allocation}</span>}
            </div>

            {/* Priority */}
            <div className="form-group">
              <label htmlFor="priority">
                Priority <span className="required">*</span>
              </label>
              <select
                id="priority"
                value={formData.priority}
                onChange={(e) => handleChange('priority', e.target.value)}
                className={errors.priority ? 'error' : ''}
              >
                <option value="">Select priority...</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
              {errors.priority && <span className="error-message">{errors.priority}</span>}
            </div>

            {/* Required Skills */}
            <div className="form-group">
              <label>Required Skills</label>
              <div className="skills-selector">
                {availableSkills.map(skill => (
                  <label key={skill.id} className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={formData.required_skills.includes(skill.id)}
                      onChange={() => toggleSkill(skill.id)}
                    />
                    <span className="checkbox-text">{skill.name}</span>
                  </label>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setShowAddSkillModal(true)}
                className="btn-secondary btn-add-skill"
              >
                + Add New Skill to Library
              </button>
            </div>

            {/* Dates */}
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="effective_date">
                  Effective Date <span className="required">*</span>
                </label>
                <input
                  id="effective_date"
                  type="date"
                  value={formData.effective_date}
                  onChange={(e) => handleChange('effective_date', e.target.value)}
                  className={errors.effective_date ? 'error' : ''}
                />
                {errors.effective_date && <span className="error-message">{errors.effective_date}</span>}
              </div>

              <div className="form-group">
                <label htmlFor="end_date">
                  End Date <small>(leave blank if ongoing)</small>
                </label>
                <input
                  id="end_date"
                  type="date"
                  value={formData.end_date}
                  onChange={(e) => handleChange('end_date', e.target.value)}
                  min={formData.effective_date}
                  className={errors.end_date ? 'error' : ''}
                />
                {errors.end_date && <span className="error-message">{errors.end_date}</span>}
              </div>
            </div>

            {/* Submit Error */}
            {errors.submit && (
              <div className="submit-error">
                {errors.submit}
              </div>
            )}

            {/* Actions */}
            <div className="modal-actions">
              <button type="button" onClick={handleClose} className="btn-cancel">
                Cancel
              </button>
              <button type="submit" className="btn-primary" disabled={saving}>
                {saving ? 'Saving...' : 'Save Responsibility'}
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Add Skill Sub-Modal */}
      {showAddSkillModal && (
        <div className="modal-overlay" onClick={() => setShowAddSkillModal(false)} style={{ zIndex: 1001 }}>
          <div className="modal-content add-skill-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Add New Skill to Library</h3>
              <button onClick={() => setShowAddSkillModal(false)} className="btn-close">×</button>
            </div>

            <form onSubmit={handleAddSkill} className="modal-body">
              <div className="form-group">
                <label htmlFor="skill_name">
                  Skill Name <span className="required">*</span>
                </label>
                <input
                  id="skill_name"
                  type="text"
                  value={newSkill.name}
                  onChange={(e) => setNewSkill(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="e.g., FHA Loan Processing"
                  autoFocus
                />
              </div>

              <div className="form-group">
                <label htmlFor="skill_category">Category</label>
                <select
                  id="skill_category"
                  value={newSkill.category}
                  onChange={(e) => setNewSkill(prev => ({ ...prev, category: e.target.value }))}
                >
                  <option value="technical">Technical</option>
                  <option value="soft_skill">Soft Skill</option>
                  <option value="domain_knowledge">Domain Knowledge</option>
                  <option value="other">Other</option>
                </select>
              </div>

              <div className="modal-actions">
                <button type="button" onClick={() => setShowAddSkillModal(false)} className="btn-cancel">
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={addingSkill}>
                  {addingSkill ? 'Adding...' : 'Add Skill'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

export default ResponsibilityModal;
