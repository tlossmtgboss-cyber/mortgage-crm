import React, { useState, useEffect } from 'react';
import goalsApi from '../services/goalsApi';
import './AssessmentModal.css';
import { toast } from '../utils/toast';

const ManagerAssessmentModal = ({ goal, userId, onClose, onSave }) => {
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (goal.manager_assessment) {
      setNotes(goal.manager_assessment.notes || '');
    }
  }, [goal]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!notes.trim()) {
      toast.error('Please enter feedback notes');
      return;
    }

    setSaving(true);
    try {
      await goalsApi.managerAssess(userId, goal.id, { notes });
      onSave();
      onClose();
    } catch (err) {
      toast.error('Failed to save feedback');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content assessment-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Manager Feedback</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="goal-context">
          <strong>Goal:</strong> {goal.objective}
        </div>

        {/* Show Employee Assessment if exists */}
        {goal.employee_assessment && (
          <div className="employee-context">
            <h4>Employee's Self-Assessment:</h4>
            <div className="context-item">
              <strong>Progress:</strong> {goal.employee_assessment.progress_percent}%
            </div>
            <div className="context-item">
              <strong>Status:</strong> <span className="status-text">{goal.employee_assessment.status}</span>
            </div>
            {goal.employee_assessment.achievements && (
              <div className="context-item">
                <strong>Achievements:</strong>
                <p>{goal.employee_assessment.achievements}</p>
              </div>
            )}
            {goal.employee_assessment.challenges && (
              <div className="context-item">
                <strong>Challenges:</strong>
                <p>{goal.employee_assessment.challenges}</p>
              </div>
            )}
            {goal.employee_assessment.support_needed && (
              <div className="context-item">
                <strong>Support Needed:</strong>
                <p>{goal.employee_assessment.support_needed}</p>
              </div>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Your Feedback: *</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={6}
              placeholder="Provide feedback on the employee's progress, recognize achievements, address challenges, and offer guidance..."
              required
            />
          </div>

          <div className="modal-actions">
            <button type="button" onClick={onClose} className="btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving...' : 'Save Feedback'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ManagerAssessmentModal;
