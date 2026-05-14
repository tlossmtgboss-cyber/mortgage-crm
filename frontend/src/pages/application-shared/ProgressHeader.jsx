import React from 'react';
import Icon from './Icon';

/**
 * Progress header bar showing stage navigation and completion percentage.
 * Shared between Purchase and Refinance applications.
 */
const ProgressHeader = ({
  visibleStages,
  currentStage,
  setCurrentStage,
  getProgress,
  onSave,
  allowClickAny = false, // Purchase allows clicking any stage; Refinance only completed
}) => {
  const currentIndex = visibleStages.findIndex(s => s.id === currentStage);

  return (
    <div className="progress-header">
      <div className="progress-chapters">
        {visibleStages.map((stage, index) => {
          const isComplete = index < currentIndex;
          const isCurrent = index === currentIndex;
          const canClick = allowClickAny || isComplete;
          return (
            <div
              key={stage.id}
              className={`progress-chapter ${isComplete ? 'complete' : ''} ${isCurrent ? 'current' : ''} ${canClick ? 'clickable' : ''}`}
              onClick={() => canClick && setCurrentStage(stage.id)}
              style={{ cursor: canClick ? 'pointer' : 'default' }}
            >
              <span className="chapter-icon">
                {isComplete ? <Icon name="check" size={20} /> : <Icon name={stage.icon} size={20} />}
              </span>
              <span className="chapter-label">{stage.label}</span>
            </div>
          );
        })}
      </div>
      <div className="progress-bar-container" style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div className="progress-bar" style={{ flex: 1 }}>
          <div className="progress-fill" style={{ width: `${getProgress()}%` }}></div>
        </div>
        <span className="progress-text">{getProgress()}% Complete</span>
        <button
          onClick={onSave}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 14px',
            background: 'white',
            border: '1px solid #e5e7eb',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: 500,
            color: '#374151',
            cursor: 'pointer',
            transition: 'all 0.2s'
          }}
          onMouseEnter={(e) => {
            e.target.style.background = '#f3f4f6';
            e.target.style.borderColor = '#d1d5db';
          }}
          onMouseLeave={(e) => {
            e.target.style.background = 'white';
            e.target.style.borderColor = '#e5e7eb';
          }}
        >
          <Icon name="save" size={16} />
          Save
        </button>
      </div>
    </div>
  );
};

export default ProgressHeader;
