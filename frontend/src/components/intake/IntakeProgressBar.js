/**
 * IntakeProgressBar - Shows progress through the intake session
 */

import React from 'react';
import './IntakeProgressBar.css';

function IntakeProgressBar({ progress }) {
  if (!progress) {
    return (
      <div className="intake-progress">
        <div className="progress-text">Loading...</div>
      </div>
    );
  }

  const {
    currentSection = 'Getting Started',
    questionsAnswered = 0,
    totalQuestions = 79,
    percentage = 0
  } = progress;

  // Format section name for display
  const formatSectionName = (section) => {
    if (!section) return 'Getting Started';
    return section
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  return (
    <div className="intake-progress">
      <div className="progress-info">
        <span className="progress-section">
          {formatSectionName(currentSection)}
        </span>
        <span className="progress-count">
          {questionsAnswered} of {totalQuestions} questions
        </span>
      </div>

      <div className="progress-bar-container">
        <div
          className="progress-bar-fill"
          style={{ width: `${percentage}%` }}
        />
      </div>

      <div className="progress-percentage">
        {percentage}%
      </div>
    </div>
  );
}

export default IntakeProgressBar;
