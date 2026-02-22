import React, { useState, useEffect } from 'react';
import './SkillModal.css';
import { toast } from '../utils/toast';

const AssessSkillModal = ({ skill, userId, onSave, onClose }) => {
  const [formData, setFormData] = useState({
    current_proficiency: 3,
    assessment_notes: '',
    training_recommendations: [],
    next_assessment_date: ''
  });

  const [trainingInput, setTrainingInput] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (skill) {
      // Calculate suggested next assessment date (90 days from now)
      const suggestedDate = new Date();
      suggestedDate.setDate(suggestedDate.getDate() + 90);

      setFormData({
        current_proficiency: skill.current_proficiency || 3,
        assessment_notes: skill.assessment_notes || '',
        training_recommendations: skill.training_recommendations || [],
        next_assessment_date: skill.next_assessment_date || suggestedDate.toISOString().split('T')[0]
      });
    }
  }, [skill]);

  const addTraining = () => {
    if (!trainingInput.trim()) return;

    setFormData({
      ...formData,
      training_recommendations: [...formData.training_recommendations, trainingInput.trim()]
    });
    setTrainingInput('');
  };

  const removeTraining = (index) => {
    setFormData({
      ...formData,
      training_recommendations: formData.training_recommendations.filter((_, i) => i !== index)
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);

    try {
      await onSave(formData);
    } catch (err) {
      toast.error('Failed to save assessment');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const getProficiencyLabel = (level) => {
    const labels = {
      1: 'Basic (1/5)',
      2: 'Developing (2/5)',
      3: 'Proficient (3/5)',
      4: 'Advanced (4/5)',
      5: 'Expert (5/5)'
    };
    return labels[level] || '';
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content skill-modal assess-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Assess Skill</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="skill-context">
          <div className="context-row">
            <strong>Skill:</strong> {skill.skill_name}
          </div>
          <div className="context-row">
            <strong>Required Level:</strong> {'⭐'.repeat(skill.required_proficiency)}{'☆'.repeat(5 - skill.required_proficiency)} ({skill.required_proficiency}/5)
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Current Proficiency */}
          <div className="form-group">
            <label>Current Proficiency Level: *</label>
            <div className="proficiency-selector">
              {[1, 2, 3, 4, 5].map(level => (
                <label key={level} className="proficiency-option">
                  <input
                    type="radio"
                    value={level}
                    checked={formData.current_proficiency === level}
                    onChange={(e) => setFormData({ ...formData, current_proficiency: parseInt(e.target.value) })}
                  />
                  <span className="star-display">
                    {'⭐'.repeat(level)}{'☆'.repeat(5 - level)}
                  </span>
                  <span className="level-label">
                    {getProficiencyLabel(level)}
                  </span>
                </label>
              ))}
            </div>
          </div>

          {/* Assessment Notes */}
          <div className="form-group">
            <label>Assessment Notes:</label>
            <textarea
              value={formData.assessment_notes}
              onChange={(e) => setFormData({ ...formData, assessment_notes: e.target.value })}
              rows={4}
              placeholder="Observations, strengths, areas for improvement..."
            />
          </div>

          {/* Training Recommendations */}
          <div className="form-group">
            <label>Training Recommendations:</label>
            <div className="training-input-row">
              <input
                type="text"
                value={trainingInput}
                onChange={(e) => setTrainingInput(e.target.value)}
                placeholder="E.g., FHA Processing Advanced Course"
                onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addTraining())}
              />
              <button type="button" onClick={addTraining} className="btn-secondary btn-small">
                Add
              </button>
            </div>
            {formData.training_recommendations.length > 0 && (
              <ul className="training-list">
                {formData.training_recommendations.map((rec, index) => (
                  <li key={index}>
                    {rec}
                    <button
                      type="button"
                      onClick={() => removeTraining(index)}
                      className="btn-remove-training"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Next Assessment Date */}
          <div className="form-group">
            <label>Next Assessment Date:</label>
            <input
              type="date"
              value={formData.next_assessment_date}
              onChange={(e) => setFormData({ ...formData, next_assessment_date: e.target.value })}
            />
            <span className="help-text">Recommended: 90 days from now</span>
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

export default AssessSkillModal;
