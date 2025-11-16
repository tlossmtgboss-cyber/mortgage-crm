import React, { useState } from 'react';
import './KeyResultProgress.css';

const KeyResultProgress = ({ keyResult, index, isManager, onUpdate }) => {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(keyResult.current);

  const progress = Math.min((keyResult.current / keyResult.target) * 100, 100);

  const getStatusColor = () => {
    if (progress >= 100) return 'completed';
    if (progress >= 80) return 'on-track';
    if (progress >= 50) return 'progress';
    return 'behind';
  };

  const handleSave = () => {
    onUpdate(parseFloat(value));
    setEditing(false);
  };

  const handleCancel = () => {
    setValue(keyResult.current);
    setEditing(false);
  };

  return (
    <div className="key-result-item">
      <div className="kr-header">
        <span className="kr-number">{index + 1}.</span>
        <span className="kr-metric">{keyResult.metric}</span>
      </div>

      <div className="kr-progress-row">
        <div className="kr-values">
          {editing ? (
            <div className="kr-edit-controls">
              <input
                type="number"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                min="0"
                step="any"
                className="kr-input"
                autoFocus
              />
              <span className="kr-target">/ {keyResult.target} {keyResult.unit}</span>
              <button onClick={handleSave} className="btn-save">✓</button>
              <button onClick={handleCancel} className="btn-cancel">✕</button>
            </div>
          ) : (
            <>
              <span className="kr-current">{keyResult.current}</span>
              <span className="kr-separator">/</span>
              <span className="kr-target">{keyResult.target} {keyResult.unit}</span>
              <span className="kr-percent">({Math.round(progress)}%)</span>
              {isManager && (
                <button onClick={() => setEditing(true)} className="btn-edit-kr">
                  Edit
                </button>
              )}
            </>
          )}
        </div>

        <div className={`kr-progress-bar ${getStatusColor()}`}>
          <div className="kr-progress-fill" style={{ width: `${progress}%` }} />
        </div>

        <span className={`kr-status-badge ${getStatusColor()}`}>
          {progress >= 100 ? '✓ Complete' :
           progress >= 80 ? '✓ On Track' :
           progress >= 50 ? '→ In Progress' :
           '! Behind'}
        </span>
      </div>
    </div>
  );
};

export default KeyResultProgress;
