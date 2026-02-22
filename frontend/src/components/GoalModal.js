import React, { useState, useEffect } from 'react';
import responsibilitiesApi from '../services/responsibilitiesApi';
import './GoalModal.css';
import { toast } from '../utils/toast';

const GoalModal = ({ goal, userId, onSave, onClose }) => {
  const [formData, setFormData] = useState({
    objective: '',
    start_date: '',
    end_date: '',
    key_results: [{ metric: '', target: '', unit: '' }],
    linked_responsibilities: []
  });

  const [responsibilities, setResponsibilities] = useState([]);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    // Load responsibilities for linking
    loadResponsibilities();

    // If editing, populate form
    if (goal) {
      setFormData({
        objective: goal.objective,
        start_date: goal.start_date,
        end_date: goal.end_date,
        key_results: goal.key_results.map(kr => ({
          id: kr.id,
          metric: kr.metric,
          target: kr.target,
          unit: kr.unit || ''
        })),
        linked_responsibilities: goal.linked_responsibilities?.map(r => r.id) || []
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [goal]);

  const loadResponsibilities = async () => {
    try {
      const response = await responsibilitiesApi.fetchResponsibilities(userId);
      setResponsibilities(response.responsibilities || []);
    } catch (err) {
      console.error('Error loading responsibilities:', err);
    }
  };

  const addKeyResult = () => {
    if (formData.key_results.length >= 5) {
      toast.error('Maximum 5 key results per goal');
      return;
    }
    setFormData({
      ...formData,
      key_results: [...formData.key_results, { metric: '', target: '', unit: '' }]
    });
  };

  const removeKeyResult = (index) => {
    if (formData.key_results.length <= 1) {
      toast.error('At least one key result is required');
      return;
    }
    const updated = formData.key_results.filter((_, i) => i !== index);
    setFormData({ ...formData, key_results: updated });
  };

  const updateKeyResult = (index, field, value) => {
    const updated = [...formData.key_results];
    updated[index][field] = value;
    setFormData({ ...formData, key_results: updated });
  };

  const validate = () => {
    const newErrors = {};

    if (!formData.objective.trim()) {
      newErrors.objective = 'Objective is required';
    }

    if (!formData.start_date) {
      newErrors.start_date = 'Start date is required';
    }

    if (!formData.end_date) {
      newErrors.end_date = 'End date is required';
    }

    if (formData.start_date && formData.end_date && formData.start_date >= formData.end_date) {
      newErrors.end_date = 'End date must be after start date';
    }

    formData.key_results.forEach((kr, i) => {
      if (!kr.metric.trim()) {
        newErrors[`kr_${i}_metric`] = 'Metric is required';
      }
      if (!kr.target || kr.target <= 0) {
        newErrors[`kr_${i}_target`] = 'Valid target required';
      }
    });

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validate()) return;

    setSaving(true);
    try {
      await onSave(formData);
    } catch (err) {
      toast.error('Failed to save goal. Please try again.');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const toggleResponsibility = (respId) => {
    const current = formData.linked_responsibilities;
    const updated = current.includes(respId)
      ? current.filter(id => id !== respId)
      : [...current, respId];
    setFormData({ ...formData, linked_responsibilities: updated });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content goal-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{goal ? 'Edit Goal' : 'Add New Goal'}</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Objective */}
          <div className="form-group">
            <label>Objective: *</label>
            <input
              type="text"
              value={formData.objective}
              onChange={(e) => setFormData({ ...formData, objective: e.target.value })}
              placeholder="E.g., Close 15 loans totaling $5M in Q4"
              maxLength={500}
            />
            {errors.objective && <span className="error-text">{errors.objective}</span>}
          </div>

          {/* Dates */}
          <div className="form-row">
            <div className="form-group">
              <label>Start Date: *</label>
              <input
                type="date"
                value={formData.start_date}
                onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
              />
              {errors.start_date && <span className="error-text">{errors.start_date}</span>}
            </div>
            <div className="form-group">
              <label>End Date: *</label>
              <input
                type="date"
                value={formData.end_date}
                onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                min={formData.start_date}
              />
              {errors.end_date && <span className="error-text">{errors.end_date}</span>}
            </div>
          </div>

          {/* Key Results */}
          <div className="form-section">
            <div className="section-header">
              <label>Key Results: * (1-5 measurable outcomes)</label>
              <button type="button" onClick={addKeyResult} className="btn-secondary btn-small">
                + Add Key Result
              </button>
            </div>

            {formData.key_results.map((kr, index) => (
              <div key={index} className="key-result-row">
                <div className="kr-number">{index + 1}.</div>
                <div className="kr-fields">
                  <input
                    type="text"
                    placeholder="Metric (e.g., Close loans)"
                    value={kr.metric}
                    onChange={(e) => updateKeyResult(index, 'metric', e.target.value)}
                    className="kr-metric"
                  />
                  <input
                    type="number"
                    placeholder="Target"
                    value={kr.target}
                    onChange={(e) => updateKeyResult(index, 'target', parseFloat(e.target.value))}
                    className="kr-target"
                    min="0"
                    step="any"
                  />
                  <input
                    type="text"
                    placeholder="Unit (e.g., loans)"
                    value={kr.unit}
                    onChange={(e) => updateKeyResult(index, 'unit', e.target.value)}
                    className="kr-unit"
                    maxLength={50}
                  />
                  {formData.key_results.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeKeyResult(index)}
                      className="btn-remove"
                      title="Remove key result"
                    >
                      ×
                    </button>
                  )}
                </div>
                {errors[`kr_${index}_metric`] && (
                  <span className="error-text">{errors[`kr_${index}_metric`]}</span>
                )}
                {errors[`kr_${index}_target`] && (
                  <span className="error-text">{errors[`kr_${index}_target`]}</span>
                )}
              </div>
            ))}
          </div>

          {/* Linked Responsibilities */}
          {responsibilities.length > 0 && (
            <div className="form-group">
              <label>Link to Responsibilities: (optional)</label>
              <div className="responsibilities-checkboxes">
                {responsibilities.map(resp => (
                  <label key={resp.id} className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={formData.linked_responsibilities.includes(resp.id)}
                      onChange={() => toggleResponsibility(resp.id)}
                    />
                    {resp.title}
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="modal-actions">
            <button type="button" onClick={onClose} className="btn-secondary" disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving...' : goal ? 'Update Goal' : 'Create Goal'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default GoalModal;
