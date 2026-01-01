import React, { useState, useEffect } from 'react';
import './EditScoreCategoryModal.css';

// Score level descriptions for each category
const SCORE_LEVELS = [
  { value: 1, label: 'Poor', color: '#ef4444', description: 'Significant concerns, below expectations' },
  { value: 2, label: 'Below Average', color: '#f97316', description: 'Some gaps, needs improvement' },
  { value: 3, label: 'Average', color: '#eab308', description: 'Meets basic expectations' },
  { value: 4, label: 'Good', color: '#22c55e', description: 'Above average, solid performer' },
  { value: 5, label: 'Excellent', color: '#3b82f6', description: 'Outstanding, exceeds expectations' }
];

const EditScoreCategoryModal = ({ isOpen, onClose, category, currentScore, onSave }) => {
  const [score, setScore] = useState(currentScore || 3);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen && currentScore !== undefined) {
      setScore(currentScore);
    }
  }, [isOpen, currentScore]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await onSave(score, notes);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen || !category) return null;

  const selectedLevel = SCORE_LEVELS.find(l => l.value === score);

  return (
    <div className="edit-category-modal-overlay" onClick={onClose}>
      <div className="edit-category-modal" onClick={e => e.stopPropagation()}>
        <div className="edit-category-header">
          <h2>Edit Score: {category.label || category.name || 'Category'}</h2>
          <button className="edit-category-close" onClick={onClose}>&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="edit-category-form">
          {/* Category Description */}
          {category.description && (
            <p className="edit-category-description">{category.description}</p>
          )}

          {/* Score Selection */}
          <div className="edit-category-scores">
            {SCORE_LEVELS.map(level => (
              <button
                key={level.value}
                type="button"
                className={`edit-category-score-btn ${score === level.value ? 'selected' : ''}`}
                onClick={() => setScore(level.value)}
                style={{
                  '--score-color': level.color,
                  borderColor: score === level.value ? level.color : undefined
                }}
              >
                <span className="score-value">{level.value}</span>
                <span className="score-label">{level.label}</span>
              </button>
            ))}
          </div>

          {/* Selected Score Info */}
          {selectedLevel && (
            <div
              className="edit-category-selected-info"
              style={{ borderLeftColor: selectedLevel.color }}
            >
              <strong>{selectedLevel.label}</strong>
              <p>{selectedLevel.description}</p>
            </div>
          )}

          {/* Optional Notes */}
          <div className="edit-category-field">
            <label>Notes (optional)</label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Add any notes about this score..."
              rows={3}
            />
          </div>

          {/* Actions */}
          <div className="edit-category-actions">
            <button
              type="button"
              className="edit-category-btn-cancel"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="edit-category-btn-save"
              disabled={loading}
            >
              {loading ? 'Saving...' : 'Save Score'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default EditScoreCategoryModal;
