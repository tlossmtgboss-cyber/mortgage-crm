import React, { useState, useEffect } from 'react';
import goalsApi from '../services/goalsApi';
import './AssessmentModal.css';
import { toast } from '../utils/toast';

const SelfAssessmentModal = ({ goal, userId, onClose, onSave }) => {
  const [formData, setFormData] = useState({
    progress_percent: 50,
    status: 'on_track',
    achievements: '',
    challenges: '',
    support_needed: ''
  });

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (goal.employee_assessment) {
      setFormData({
        progress_percent: goal.employee_assessment.progress_percent || 50,
        status: goal.employee_assessment.status || 'on_track',
        achievements: goal.employee_assessment.achievements || '',
        challenges: goal.employee_assessment.challenges || '',
        support_needed: goal.employee_assessment.support_needed || ''
      });
    }
  }, [goal]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);

    try {
      await goalsApi.employeeSelfAssess(userId, goal.id, formData);
      onSave();
      onClose();
    } catch (err) {
      toast.error('Failed to save assessment');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content assessment-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Update Self-Assessment</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="goal-context">
          <strong>Goal:</strong> {goal.objective}
        </div>

        <form onSubmit={handleSubmit}>
          {/* Overall Progress */}
          <div className="form-group">
            <label>Overall Progress: {formData.progress_percent}%</label>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={formData.progress_percent}
              onChange={(e) => setFormData({ ...formData, progress_percent: parseInt(e.target.value) })}
              className="progress-slider"
            />
            <div className="slider-labels">
              <span>0%</span>
              <span>50%</span>
              <span>100%</span>
            </div>
          </div>

          {/* Status */}
          <div className="form-group">
            <label>Status:</label>
            <div className="radio-group">
              <label className="radio-label">
                <input
                  type="radio"
                  value="on_track"
                  checked={formData.status === 'on_track'}
                  onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                />
                <span>On Track</span>
              </label>
              <label className="radio-label">
                <input
                  type="radio"
                  value="at_risk"
                  checked={formData.status === 'at_risk'}
                  onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                />
                <span>At Risk</span>
              </label>
              <label className="radio-label">
                <input
                  type="radio"
                  value="blocked"
                  checked={formData.status === 'blocked'}
                  onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                />
                <span>Blocked</span>
              </label>
            </div>
          </div>

          {/* Achievements */}
          <div className="form-group">
            <label>Achievements: (What have you accomplished?)</label>
            <textarea
              value={formData.achievements}
              onChange={(e) => setFormData({ ...formData, achievements: e.target.value })}
              rows={4}
              placeholder="Describe what you've achieved toward this goal..."
            />
          </div>

          {/* Challenges */}
          <div className="form-group">
            <label>Challenges: (What obstacles are you facing?)</label>
            <textarea
              value={formData.challenges}
              onChange={(e) => setFormData({ ...formData, challenges: e.target.value })}
              rows={3}
              placeholder="Describe any challenges or roadblocks..."
            />
          </div>

          {/* Support Needed */}
          <div className="form-group">
            <label>Support Needed: (How can your manager help?)</label>
            <textarea
              value={formData.support_needed}
              onChange={(e) => setFormData({ ...formData, support_needed: e.target.value })}
              rows={3}
              placeholder="What support or resources would help you succeed?"
            />
          </div>

          {/* Actions */}
          <div className="modal-actions">
            <button type="button" onClick={onClose} className="btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving...' : 'Save Assessment'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default SelfAssessmentModal;
